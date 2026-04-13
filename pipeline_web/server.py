"""
MinerU + LangExtract Web 网关（与 docs/mineru-langextract-pipeline-v1.0.md 数据契约对齐）。

运行（建议在 langextract_pipeline 的 venv 中安装本目录 requirements.txt 后执行）：

  cd /path/to/GraphRagAgent/pipeline_web
  uvicorn server:app --host 127.0.0.1 --port 8765

浏览器打开 http://127.0.0.1:8765/
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[1]
MINERU_ROOT = REPO_ROOT / "mineru_parser"
LANGEXTRACT_ROOT = REPO_ROOT / "langextract_pipeline"
MINERU_OUTPUT = (MINERU_ROOT / "output").resolve()
LANGEXTRACT_OUTPUT = (LANGEXTRACT_ROOT / "output").resolve()
WEB_UPLOAD_ROOT = MINERU_ROOT / "input" / "web_uploads"

# MinerU 支持的扩展（与 mineru_parser/config.py 一致）；纯文本走本地写入 full.md
MINERU_PRECISE_EXT = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".html",
    ".png", ".jpg", ".jpeg", ".jp2", ".webp", ".gif", ".bmp",
}
MINERU_AGENT_EXT = {".xls", ".xlsx"}
PLAIN_TEXT_EXT = {".txt", ".md"}

_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def _python_for(cwd: Path) -> str:
    venv_py = cwd / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    win = cwd / ".venv" / "Scripts" / "python.exe"
    if win.is_file():
        return str(win)
    return os.environ.get("PYTHON", "python3")


def _safe_filename(name: str, max_len: int = 80) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w\u4e00-\u9fff.\-()+]", "_", base, flags=re.UNICODE)
    if not base or base.strip("._") == "":
        base = "upload"
    return base[:max_len]


def _append_log(job_id: str, stage: str, message: str) -> None:
    entry = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stage": stage,
        "message": message,
    }
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["logs"].append(entry)


def _set_job(job_id: str, **kwargs: Any) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def _materialize_plain_text(doc_key: str, source: Path) -> None:
    out_dir = MINERU_OUTPUT / doc_key
    out_dir.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8", errors="replace")
    (out_dir / "full.md").write_text(text, encoding="utf-8")


def _run_mineru_subprocess(file_path: Path) -> None:
    py = _python_for(MINERU_ROOT)
    cmd = [py, str(MINERU_ROOT / "run_parser.py"), str(file_path)]
    proc = subprocess.run(
        cmd,
        cwd=str(MINERU_ROOT),
        capture_output=True,
        text=True,
        timeout=int(os.environ.get("MINERU_SUBPROCESS_TIMEOUT", "3600")),
        env={**os.environ},
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-4000:]
        raise RuntimeError(f"MinerU 子进程失败 (exit={proc.returncode}): {tail}")


def _find_jsonl_with_document(doc_key: str, candidates: list[Path]) -> Path | None:
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if doc.get("document_id") == doc_key:
                return path
    return None


def _run_langextract_subprocess(doc_filter: str) -> Path:
    before = time.time() - 2.0
    py = _python_for(LANGEXTRACT_ROOT)
    cmd = [py, str(LANGEXTRACT_ROOT / "run_pipeline.py"), doc_filter]
    proc = subprocess.run(
        cmd,
        cwd=str(LANGEXTRACT_ROOT),
        capture_output=True,
        text=True,
        timeout=int(os.environ.get("LANGEXTRACT_SUBPROCESS_TIMEOUT", "7200")),
        env={**os.environ},
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-4000:]
        raise RuntimeError(f"LangExtract 子进程失败 (exit={proc.returncode}): {tail}")

    jsonls = sorted(
        LANGEXTRACT_OUTPUT.glob("kg_extraction_*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    fresh = [p for p in jsonls if p.stat().st_mtime >= before]
    hit = _find_jsonl_with_document(doc_filter, fresh)
    if hit:
        return hit
    hit = _find_jsonl_with_document(doc_filter, jsonls)
    if hit:
        return hit
    raise RuntimeError(
        f"未在输出目录找到含 document_id={doc_filter!r} 的 kg_extraction_*.jsonl。"
    )


def _read_jsonl_for_doc(path: Path, doc_key: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("JSONL 为空")
    for line in lines:
        doc = json.loads(line)
        if doc.get("document_id") == doc_key:
            return doc
    return json.loads(lines[0])


def _mineru_char_count(doc_key: str) -> int | None:
    md = MINERU_OUTPUT / doc_key / "full.md"
    if not md.is_file():
        return None
    return len(md.read_text(encoding="utf-8"))


def _run_pipeline_thread(job_id: str, saved_path: Path, doc_key: str) -> None:
    ext = saved_path.suffix.lower()
    try:
        _set_job(job_id, status="mineru")
        if ext in PLAIN_TEXT_EXT:
            _append_log(job_id, "parse", "检测到纯文本，已按规范写入 mineru_parser/output/{文档名}/full.md，跳过 MinerU API。")
            _materialize_plain_text(doc_key, saved_path)
            n = _mineru_char_count(doc_key)
            _append_log(job_id, "parse", f"full.md 已生成，约 {n} 字符。")
        else:
            if ext in MINERU_AGENT_EXT:
                _append_log(job_id, "mineru", "路由：Agent 轻量 API（/api/v1/agent/），适用于 Excel。")
            elif ext in MINERU_PRECISE_EXT:
                _append_log(job_id, "mineru", "路由：精准解析 API（/api/v4/）。")
            _append_log(job_id, "mineru", "正在调用 MinerU 解析（子进程），请等待云端完成…")
            _run_mineru_subprocess(saved_path)
            n = _mineru_char_count(doc_key)
            _append_log(job_id, "mineru", f"MinerU 完成。full.md 约 {n} 字符（目录名 document_id = {doc_key}）。")

        _set_job(job_id, status="extracting")
        _append_log(
            job_id,
            "extract",
            "开始 LangExtract 抽取（lx.extract，参数见 langextract_pipeline/.env）…",
        )
        jsonl_path = _run_langextract_subprocess(doc_key)
        doc = _read_jsonl_for_doc(jsonl_path, doc_key)
        # 与规范 7.2–7.4 一致：AnnotatedDocument 行 JSON
        _append_log(
            job_id,
            "extract",
            f"抽取完成，结果文件：{jsonl_path.name}（JSONL 每行一个 AnnotatedDocument）。",
        )
        _set_job(job_id, status="done", document=doc, error=None)
    except Exception as e:
        _append_log(job_id, "error", str(e))
        _set_job(job_id, status="error", error=str(e))


class JobView(BaseModel):
    job_id: str
    status: str
    logs: list[dict[str, Any]]
    document: dict[str, Any] | None
    doc_key: str
    error: str | None = None


app = FastAPI(title="GraphRag Pipeline Web", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def index() -> FileResponse:
    index_path = static_dir / "index.html"
    if not index_path.is_file():
        raise HTTPException(500, "static/index.html 缺失")
    return FileResponse(index_path, media_type="text/html; charset=utf-8")


@app.post("/api/v1/process")
async def start_process(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename:
        raise HTTPException(400, "缺少文件名")

    raw = Path(file.filename)
    ext = raw.suffix.lower()
    allowed = MINERU_PRECISE_EXT | MINERU_AGENT_EXT | PLAIN_TEXT_EXT
    if ext not in allowed:
        raise HTTPException(
            400,
            f"不支持的扩展名 {ext}。允许：{sorted(allowed)}",
        )

    job_id = str(uuid.uuid4())
    stem = _safe_filename(raw.stem)
    doc_key = f"{job_id[:10]}_{stem}"
    if len(doc_key) > 120:
        doc_key = doc_key[:120]

    WEB_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    job_dir = WEB_UPLOAD_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / f"{doc_key}{ext}"

    content = await file.read()
    max_bytes = int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(400, f"文件过大（>{max_bytes // 1024 // 1024} MB）")

    dest.write_bytes(content)

    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "logs": [],
            "document": None,
            "doc_key": doc_key,
            "error": None,
        }

    _append_log(job_id, "upload", f"已接收文件 {file.filename}，document_id（目录名）= {doc_key}")

    t = threading.Thread(
        target=_run_pipeline_thread,
        args=(job_id, dest, doc_key),
        daemon=True,
    )
    t.start()

    return JSONResponse({"job_id": job_id, "doc_key": doc_key})


@app.get("/api/v1/jobs/{job_id}", response_model=JobView)
def get_job(job_id: str) -> JobView:
    with _jobs_lock:
        if job_id not in _jobs:
            raise HTTPException(404, "job 不存在")
        j = dict(_jobs[job_id])
    return JobView(**j)
