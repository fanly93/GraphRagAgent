"""MinerU Cloud API 封装：文件上传、解析轮询、结果下载。"""

from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

import httpx

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from database import update_document


# ── 格式路由 ──────────────────────────────────────────────────────

def route_api(file_type: str) -> str:
    """根据文件类型返回 MinerU API 类型：'agent' 或 'precision'。"""
    return "agent" if file_type in config.AGENT_EXTENSIONS else "precision"


# ── Precision API ────────────────────────────────────────────────

async def _precision_upload(file_path: Path, file_type: str, enable_ocr: bool) -> str:
    """Precision API: 获取预签名 URL + batch_id，然后 PUT 文件。返回 batch_id。"""
    headers = {"Authorization": f"Bearer {config.MINERU_API_TOKEN}"}
    filename = file_path.name
    file_size = file_path.stat().st_size

    async with httpx.AsyncClient(timeout=60) as client:
        # Step 1: 获取 presigned_url
        # 注意：files 数组内字段为 name/size（非 file_name/file_size）
        payload = {
            "enable_formula": False,
            "enable_table": True,
            "files": [{"name": filename, "size": file_size, "is_ocr": enable_ocr}],
        }
        resp = await client.post(
            f"{config.MINERU_BASE_URL}/api/v4/file-urls/batch",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

        # 响应结构：data.data.batch_id + data.data.file_urls (string[])
        batch_id = data["data"]["batch_id"]
        file_url = data["data"]["file_urls"][0]

        # Step 2: PUT 文件（不加 Content-Type，必须加 Content-Length）
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        put_resp = await client.put(
            file_url,
            content=file_bytes,
            headers={"Content-Length": str(file_size)},
        )
        put_resp.raise_for_status()

    return batch_id


async def _precision_poll(batch_id: str) -> dict:
    """轮询 Precision API 解析状态。返回文件结果 dict。"""
    headers = {"Authorization": f"Bearer {config.MINERU_API_TOKEN}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{config.MINERU_BASE_URL}/api/v4/extract-results/batch/{batch_id}",
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def _precision_download(zip_url: str, output_dir: Path) -> None:
    """下载 ZIP 并解压到 output_dir。"""
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(zip_url)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            zf.extractall(output_dir)
    print(f"  [MinerU] 解压到 {output_dir}")


# ── Agent API (Excel) ────────────────────────────────────────────

async def _agent_upload(file_path: Path) -> str:
    """Agent API: 获取上传 URL + task_id，然后 PUT 文件。返回 task_id。"""
    headers = {"Authorization": f"Bearer {config.MINERU_API_TOKEN}"}
    filename = file_path.name
    file_size = file_path.stat().st_size

    async with httpx.AsyncClient(timeout=60) as client:
        payload = {"file_name": filename, "file_size": file_size, "is_ocr": False}
        resp = await client.post(
            f"{config.MINERU_BASE_URL}/api/v1/agent/parse/file",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

        task_id = data["data"]["task_id"]
        file_url = data["data"]["file_url"]

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        put_resp = await client.put(
            file_url,
            content=file_bytes,
            headers={"Content-Length": str(file_size)},
        )
        put_resp.raise_for_status()

    return task_id


async def _agent_poll(task_id: str) -> dict:
    """轮询 Agent API 解析状态。"""
    headers = {"Authorization": f"Bearer {config.MINERU_API_TOKEN}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{config.MINERU_BASE_URL}/api/v1/agent/parse/{task_id}",
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def _agent_download_markdown(markdown_url: str, output_dir: Path) -> None:
    """下载 Markdown 内容写入 full.md。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(markdown_url)
        resp.raise_for_status()
        (output_dir / "full.md").write_bytes(resp.content)
    print(f"  [MinerU] Agent 结果已下载到 {output_dir / 'full.md'}")


# ── 主流程 ───────────────────────────────────────────────────────

async def submit_parse(
    doc_id: str,
    file_path: Path,
    file_type: str,
    enable_ocr: bool = True,
) -> None:
    """提交 MinerU 解析任务，更新 DB，然后后台轮询直到完成。"""
    api_type = route_api(file_type)

    try:
        if api_type == "agent":
            task_id = await _agent_upload(file_path)
            await update_document(doc_id, mineru_api_type="agent", mineru_task_id=task_id, status="PARSING")
            print(f"  [MinerU] Agent task_id={task_id}")
        else:
            batch_id = await _precision_upload(file_path, file_type, enable_ocr)
            await update_document(doc_id, mineru_api_type="precision", mineru_batch_id=batch_id, status="PARSING")
            print(f"  [MinerU] Precision batch_id={batch_id}")
    except Exception as e:
        error_msg = f"MinerU 提交失败：{e}"
        print(f"  [MinerU] {error_msg}")
        await update_document(doc_id, status="PARSE_FAILED", error_msg=error_msg)
        return

    # 后台轮询
    asyncio.create_task(poll_until_done(doc_id))


async def poll_until_done(doc_id: str) -> None:
    """持续轮询 MinerU 直到解析完成或超时。"""
    from database import get_document
    from services.index_service import build_both

    doc = await get_document(doc_id)
    if not doc:
        return

    api_type = doc.get("mineru_api_type")
    task_id = doc.get("mineru_task_id")
    batch_id = doc.get("mineru_batch_id")

    output_dir = config.MINERU_OUTPUT_DIR / doc_id

    elapsed = 0
    interval = config.POLL_INTERVAL_SEC
    timeout = config.POLL_TIMEOUT_SEC

    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval

        try:
            if api_type == "agent":
                result = await _agent_poll(task_id)
                state = result.get("data", {}).get("state", "")
                if state == "done":
                    markdown_url = result["data"].get("full_md_url") or result["data"].get("markdown_url", "")
                    if markdown_url:
                        await _agent_download_markdown(markdown_url, output_dir)
                    await update_document(
                        doc_id, status="PARSED",
                        mineru_output_dir=str(output_dir),
                    )
                    print(f"  [MinerU] doc_id={doc_id} PARSED (agent)")
                    asyncio.create_task(build_both(doc_id))
                    return
                elif state in ("failed", "error"):
                    raise RuntimeError(f"Agent API 解析失败：{result}")
            else:
                result = await _precision_poll(batch_id)
                # 响应结构：data.data.extract_result (list)
                extract_result = result.get("data", {}).get("extract_result", [])
                if extract_result:
                    file_info = extract_result[0]
                    state = file_info.get("state", "")
                    if state == "done":
                        zip_url = file_info.get("full_zip_url", "")
                        if zip_url:
                            output_dir.mkdir(parents=True, exist_ok=True)
                            await _precision_download(zip_url, output_dir)
                        await update_document(
                            doc_id, status="PARSED",
                            mineru_output_dir=str(output_dir),
                        )
                        print(f"  [MinerU] doc_id={doc_id} PARSED (precision)")
                        asyncio.create_task(build_both(doc_id))
                        return
                    elif state in ("failed", "error"):
                        err_detail = file_info.get("err_msg", "未知错误")
                        raise RuntimeError(f"Precision API 解析失败：{err_detail}")
        except Exception as e:
            if elapsed >= timeout:
                break
            print(f"  [MinerU] 轮询异常（{elapsed}s）：{e}")
            continue

    # 超时
    error_msg = f"MinerU 解析超时（{timeout}s）"
    print(f"  [MinerU] {error_msg}")
    await update_document(doc_id, status="PARSE_FAILED", error_msg=error_msg)
