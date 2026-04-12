"""MinerU 文档解析完整 Pipeline。

流程：
  本地文件扫描 → 格式路由 → 文件上传 → 云端解析 → 轮询等待 → 结果下载 → 本地解压保存
"""

import json
import time
import zipfile
from pathlib import Path
from typing import Any, Optional

from tqdm import tqdm

import config
from client import MinerUAPIError, MinerUClient
from models import ParseAPI, ParseJob, ParseResult, TaskState


# ─────────────────────────────────────────────────────────────────
# 文件格式路由
# ─────────────────────────────────────────────────────────────────

def route_file(file_path: Path) -> Optional[ParseAPI]:
    """根据文件扩展名决定使用哪个 API，不支持的格式返回 None。"""
    ext = file_path.suffix.lower()
    if ext in config.PRECISE_API_EXTENSIONS:
        return ParseAPI.PRECISE
    if ext in config.AGENT_API_EXTENSIONS:
        return ParseAPI.AGENT
    return None


def should_force_ocr(file_path: Path) -> bool:
    """图片格式强制开启 OCR。"""
    img_exts = {".png", ".jpg", ".jpeg", ".jp2", ".webp", ".gif", ".bmp"}
    return file_path.suffix.lower() in img_exts


# ─────────────────────────────────────────────────────────────────
# 精准解析 API Pipeline
# ─────────────────────────────────────────────────────────────────

def _precise_upload_and_submit(
    client: MinerUClient,
    job: ParseJob,
) -> ParseJob:
    """上传本地文件并启动精准解析任务，返回填充了 batch_id 的 job。

    正确 API 流程（实测确认）：
      1. POST /api/v4/file-urls/batch 时同时传入解析参数 → 返回 batch_id + 上传 URL
      2. PUT 文件到预签名 URL
      3. 直接用 batch_id 轮询 /api/v4/extract-results/batch/{batch_id}
         （无需单独提交步骤，文件上传完成后 MinerU 自动开始解析）
    """
    file_path = job.source_path
    file_size = file_path.stat().st_size
    file_name = file_path.name
    is_ocr = config.IS_OCR or should_force_ocr(file_path)

    print(f"  [1/3] 申请上传链接 + 提交解析参数: {file_name} ({file_size / 1024:.1f} KB)")
    upload_info = client.precise_request_upload_urls([{
        "name": file_name,
        "size": file_size,
        "model_version": config.MODEL_VERSION,
        "is_ocr": is_ocr,
        "enable_table": config.ENABLE_TABLE,
        "enable_formula": config.ENABLE_FORMULA,
        "language": config.LANGUAGE,
    }])

    batch_id = upload_info["batch_id"]
    presigned_url: str = upload_info["file_urls"][0]

    print(f"  [2/3] 上传文件到 OSS (model={config.MODEL_VERSION}, ocr={is_ocr})")
    client.precise_upload_file(presigned_url, file_path)

    print(f"  [3/3] 上传完成，自动开始解析，batch_id={batch_id}")
    job.batch_id = batch_id
    job.state = TaskState.PENDING
    return job


def _precise_poll(client: MinerUClient, job: ParseJob) -> ParseJob:
    """轮询批量任务直到完成或超时。"""
    deadline = time.time() + config.POLL_TIMEOUT
    pbar = tqdm(
        desc=f"  等待解析 {job.source_path.name}",
        unit="次",
        leave=False,
    )

    while time.time() < deadline:
        time.sleep(config.POLL_INTERVAL)
        pbar.update(1)

        try:
            batch_data = client.precise_get_batch_results(job.batch_id)
        except MinerUAPIError as e:
            pbar.close()
            job.state = TaskState.FAILED
            job.error = str(e)
            return job

        # 真实 API 返回 extract_result（非 results），file_name 为 OSS 内部 UUID 文件名
        # 提交时每批次仅一个文件，直接取第一项
        results = batch_data.get("extract_result", [])
        if results:
            r = results[0]
            state = TaskState.from_str(r.get("state", "unknown"))
            job.state = state
            pbar.set_postfix(state=state.value)

            if state.is_terminal():
                pbar.close()
                if state.is_success():
                    job.result_url = r.get("full_zip_url")
                else:
                    job.error = r.get("err_msg", "parse failed")
                return job

    pbar.close()
    job.state = TaskState.FAILED
    job.error = f"轮询超时（>{config.POLL_TIMEOUT}s）"
    return job


def _extract_zip_result(zip_path: Path, output_dir: Path) -> None:
    """解压 ZIP 到输出目录。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(output_dir)
    zip_path.unlink()  # 清理临时 ZIP


def _run_precise_job(client: MinerUClient, job: ParseJob) -> ParseResult:
    """精准解析 API 完整流程：上传 → 提交 → 轮询 → 下载 → 解压。"""
    # 上传 & 提交
    try:
        job = _precise_upload_and_submit(client, job)
    except Exception as e:
        return ParseResult(job=job, success=False, error=f"上传/提交失败: {e}")

    # 轮询
    job = _precise_poll(client, job)
    if not job.state.is_success():
        return ParseResult(job=job, success=False, error=job.error or "解析失败")

    # 下载 ZIP
    output_dir = config.OUTPUT_DIR / job.source_path.stem
    zip_path = output_dir / f"{job.source_path.stem}.zip"
    print(f"  [下载] {job.result_url}")
    try:
        client.download_file(job.result_url, zip_path)
    except Exception as e:
        return ParseResult(job=job, success=False, error=f"下载 ZIP 失败: {e}")

    # 解压
    print(f"  [解压] → {output_dir}/")
    _extract_zip_result(zip_path, output_dir)
    job.output_dir = output_dir

    # 整理结果路径
    return _build_precise_result(job, output_dir)


def _build_precise_result(job: ParseJob, output_dir: Path) -> ParseResult:
    """从解压后的目录中找到各输出文件路径。"""
    markdown_path = output_dir / "full.md"
    content_list_path = next(output_dir.glob("*_content_list.json"), None)
    middle_json_path = next(output_dir.glob("*_middle.json"), None)
    model_json_path = next(output_dir.glob("*_model.json"), None)
    images_dir = output_dir / "images"

    return ParseResult(
        job=job,
        success=True,
        markdown_path=markdown_path if markdown_path.exists() else None,
        content_list_path=content_list_path,
        middle_json_path=middle_json_path,
        model_json_path=model_json_path,
        images_dir=images_dir if images_dir.exists() else None,
    )


# ─────────────────────────────────────────────────────────────────
# Agent 轻量 API Pipeline
# ─────────────────────────────────────────────────────────────────

def _run_agent_job(client: MinerUClient, job: ParseJob) -> ParseResult:
    """Agent 轻量 API 完整流程：申请上传 → 上传 → 轮询 → 下载 Markdown。"""
    file_path = job.source_path
    file_size = file_path.stat().st_size
    file_name = file_path.name

    # 申请上传链接
    print(f"  [1/4] 申请 Agent 上传链接: {file_name} ({file_size / 1024:.1f} KB)")
    try:
        upload_info = client.agent_request_upload(file_name, file_size)
    except Exception as e:
        return ParseResult(job=job, success=False, error=f"申请上传链接失败: {e}")

    task_id = upload_info["task_id"]
    file_url = upload_info["file_url"]   # 真实 API 返回 file_url（非 upload_url）
    job.task_id = task_id

    # 上传文件
    print(f"  [2/4] 上传文件...")
    try:
        client.agent_upload_file(file_url, file_path)
    except Exception as e:
        return ParseResult(job=job, success=False, error=f"文件上传失败: {e}")

    print(f"  [3/4] 提交成功，task_id={task_id}")

    # 轮询
    print(f"  [4/4] 等待解析...")
    deadline = time.time() + config.POLL_TIMEOUT
    pbar = tqdm(desc=f"  等待 {file_name}", unit="次", leave=False)

    while time.time() < deadline:
        time.sleep(config.POLL_INTERVAL)
        pbar.update(1)

        try:
            task_data = client.agent_get_task(task_id)
        except MinerUAPIError as e:
            pbar.close()
            return ParseResult(job=job, success=False, error=str(e))

        state = TaskState.from_str(task_data.get("state", "unknown"))
        job.state = state
        pbar.set_postfix(state=state.value)

        if state.is_terminal():
            pbar.close()
            if not state.is_success():
                return ParseResult(
                    job=job,
                    success=False,
                    error=task_data.get("err_msg", "解析失败"),
                )
            job.result_url = task_data.get("markdown_url")
            break
    else:
        pbar.close()
        return ParseResult(job=job, success=False, error=f"轮询超时（>{config.POLL_TIMEOUT}s）")

    # 下载 Markdown（Agent API 只输出 Markdown）
    output_dir = config.OUTPUT_DIR / job.source_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    job.output_dir = output_dir

    markdown_path = output_dir / "full.md"
    print(f"  [下载] Markdown → {markdown_path}")
    try:
        client.download_file(job.result_url, markdown_path)
    except Exception as e:
        return ParseResult(job=job, success=False, error=f"下载 Markdown 失败: {e}")

    return ParseResult(
        job=job,
        success=True,
        markdown_path=markdown_path,
    )


# ─────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────

def scan_input_files() -> list[Path]:
    """扫描 input/ 目录，返回所有支持格式的文件列表（忽略隐藏文件）。"""
    config.INPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = [
        f for f in config.INPUT_DIR.iterdir()
        if f.is_file()
        and not f.name.startswith(".")
        and f.suffix.lower() in config.ALL_SUPPORTED_EXTENSIONS
    ]
    return sorted(files)


def run_pipeline(
    files: Optional[list[Path]] = None,
    api_token: Optional[str] = None,
) -> list[ParseResult]:
    """
    执行完整解析 Pipeline。

    Args:
        files: 要解析的文件列表，None 则自动扫描 input/ 目录
        api_token: 覆盖 .env 中的 MINERU_API_TOKEN

    Returns:
        每个文件对应的 ParseResult 列表
    """
    token = api_token or config.MINERU_API_TOKEN
    client = MinerUClient(api_token=token)

    # 文件发现
    if files is None:
        files = scan_input_files()

    if not files:
        print("input/ 目录中没有可解析的文件，请先将文件放入 input/ 文件夹。")
        return []

    # 格式路由
    jobs: list[ParseJob] = []
    skipped: list[Path] = []
    for f in files:
        api = route_file(f)
        if api is None:
            skipped.append(f)
            continue
        jobs.append(ParseJob(source_path=f, api=api))

    if skipped:
        print(f"跳过不支持的格式：{[s.name for s in skipped]}")

    print(f"\n共 {len(jobs)} 个文件待解析")
    print("=" * 60)

    results: list[ParseResult] = []
    for i, job in enumerate(jobs, 1):
        print(f"\n[{i}/{len(jobs)}] {job.source_path.name}  ({job.api.value} API)")
        print("-" * 40)

        if job.api == ParseAPI.PRECISE:
            result = _run_precise_job(client, job)
        else:
            result = _run_agent_job(client, job)

        results.append(result)
        print(result.summary())

    # 汇总
    print("\n" + "=" * 60)
    success_count = sum(1 for r in results if r.success)
    print(f"解析完成：{success_count}/{len(results)} 成功")
    if success_count < len(results):
        print("失败文件：")
        for r in results:
            if not r.success:
                print(f"  - {r.job.source_path.name}: {r.error}")

    return results


def verify_result(result: ParseResult) -> dict[str, bool]:
    """对解析结果执行规范文档要求的验证检查项。"""
    checks: dict[str, bool] = {}

    if not result.success:
        return {"解析成功": False}

    # full.md 非空且含标题
    if result.markdown_path and result.markdown_path.exists():
        md_text = result.markdown_path.read_text(encoding="utf-8")
        checks["full.md 非空（>100字符）"] = len(md_text) > 100
        checks["full.md 含标题 '#'"] = "#" in md_text
    else:
        checks["full.md 存在"] = False

    # content_list.json 验证（仅精准 API 有）
    if result.content_list_path and result.content_list_path.exists():
        with result.content_list_path.open(encoding="utf-8") as f:
            content_list: list[dict] = json.load(f)

        checks["content_list 非空"] = len(content_list) > 0

        if content_list:
            # bbox 坐标域验证
            all_bbox_valid = all(
                0 <= v <= 1000
                for block in content_list
                for v in block.get("bbox", [0])
            )
            checks["bbox 值域 0–1000"] = all_bbox_valid

            # image 的 img_path 为 SHA256 格式
            images = [b for b in content_list if b.get("type") == "image"]
            if images:
                img_path = Path(images[0].get("img_path", ""))
                checks["image img_path 为 SHA256.jpg"] = (
                    len(img_path.stem) == 64 and img_path.suffix == ".jpg"
                )

            # table 有 table_body HTML
            tables = [b for b in content_list if b.get("type") == "table"]
            if tables:
                checks["table 有 table_body HTML"] = (
                    "<table>" in tables[0].get("table_body", "")
                )

            # equation 有 LaTeX
            equations = [b for b in content_list if b.get("type") == "equation"]
            if equations:
                checks["equation text_format=latex"] = (
                    equations[0].get("text_format") == "latex"
                )
    else:
        checks["content_list.json 存在"] = False

    # images/ 目录
    if result.images_dir and result.images_dir.exists():
        img_files = list(result.images_dir.glob("*.jpg"))
        checks["images/ 目录有 jpg 文件"] = len(img_files) > 0

    return checks
