"""MinerU REST API 客户端。

封装精准解析 API（/api/v4/）与 Agent 轻量 API（/api/v1/agent/）的所有 HTTP 交互。
对外暴露每个端点对应的方法，不含业务轮询逻辑（轮询在 pipeline.py 中）。
"""

from pathlib import Path
from typing import Any

import requests

from config import MINERU_API_TOKEN, MINERU_BASE_URL


class MinerUAPIError(Exception):
    """API 返回非 0 错误码时抛出。"""
    def __init__(self, code: int | str, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"MinerU API error [{code}]: {msg}")


class MinerUClient:
    """MinerU HTTP 客户端（同步，复用 Session）。"""

    def __init__(
        self,
        api_token: str = MINERU_API_TOKEN,
        base_url: str = MINERU_BASE_URL,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = api_token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        })

    # ─────────────────────────────────────────────────────────────
    # 内部工具方法
    # ─────────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @staticmethod
    def _check(resp: requests.Response) -> dict[str, Any]:
        """检查 HTTP 状态码 + API code 字段，失败时抛出 MinerUAPIError。"""
        resp.raise_for_status()
        data = resp.json()
        code = data.get("code", data.get("err_code", 0))
        if code != 0:
            msg = data.get("msg", data.get("message", "unknown error"))
            raise MinerUAPIError(code, msg)
        return data.get("data", data)

    # ─────────────────────────────────────────────────────────────
    # 精准解析 API  /api/v4/
    # ─────────────────────────────────────────────────────────────

    def precise_request_upload_urls(
        self,
        files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """申请本地文件批量上传链接，同时指定解析参数。

        ⚠️ 正确流程：解析参数（model_version/is_ocr 等）必须在此步一并传入，
           上传文件后无需单独提交，直接用此 batch_id 轮询结果即可。

        Args:
            files: [
              {
                "name": "xxx.pdf",
                "size": 1024,
                "model_version": "vlm",   # 解析参数放这里
                "is_ocr": False,
                "enable_table": True,
                "enable_formula": True,
                "language": "ch",
              }
            ]

        Returns:
            {
              "batch_id": "...",         # 同时作为轮询 batch_id，无需再次提交
              "file_urls": ["presigned_upload_url_string", ...]
            }
        """
        payload = {"files": files}
        resp = self.session.post(self._url("/api/v4/file-urls/batch"), json=payload)
        return self._check(resp)

    def precise_upload_file(self, presigned_url: str, file_path: Path) -> None:
        """将本地文件 PUT 到预签名 OSS URL。

        注意：
        - 不携带 Content-Type，否则 OSS 预签名签名校验失败(403)
        - 必须设置 Content-Length，否则 OSS 接收到截断内容导致文件损坏
        """
        file_bytes = file_path.read_bytes()
        resp = requests.put(
            presigned_url,
            data=file_bytes,
            headers={"Content-Length": str(len(file_bytes))},
            timeout=300,
        )
        resp.raise_for_status()

    def precise_get_batch_results(self, batch_id: str) -> dict[str, Any]:
        """查询批量任务结果。

        Returns:
            {
              "batch_id": "...",
              "extract_result": [
                {
                  "file_name": "uuid.pdf",   # OSS 内部 UUID 文件名（非原始名）
                  "state": "done",
                  "full_zip_url": "https://...",
                  "err_msg": ""
                }
              ]
            }
        """
        resp = self.session.get(self._url(f"/api/v4/extract-results/batch/{batch_id}"))
        return self._check(resp)

    def precise_submit_url_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        """单文件 URL 提交（公网可访问的文件）。

        Args:
            payload: {"url": "...", "model_version": "vlm", ...}

        Returns:
            {"task_id": "..."}
        """
        resp = self.session.post(self._url("/api/v4/extract/task"), json=payload)
        return self._check(resp)

    def precise_get_task(self, task_id: str) -> dict[str, Any]:
        """查询单个任务状态。

        Returns:
            {"task_id": "...", "state": "done", "full_zip_url": "...", "err_msg": ""}
        """
        resp = self.session.get(self._url(f"/api/v4/extract/task/{task_id}"))
        return self._check(resp)

    # ─────────────────────────────────────────────────────────────
    # Agent 轻量 API  /api/v1/agent/
    # ─────────────────────────────────────────────────────────────

    def agent_request_upload(
        self,
        file_name: str,
        file_size: int,
    ) -> dict[str, Any]:
        """申请 Agent API 文件上传链接。

        Args:
            file_name: 文件名（含扩展名）
            file_size: 文件字节数

        Returns:
            {"task_id": "...", "file_url": "https://..."}   # 注意字段名是 file_url
        """
        payload = {"file_name": file_name, "file_size": file_size}   # 注意：file_name / file_size
        resp = self.session.post(self._url("/api/v1/agent/parse/file"), json=payload)
        return self._check(resp)

    def agent_upload_file(self, file_url: str, file_path: Path) -> None:
        """将本地文件 PUT 到 Agent API 预签名 OSS URL。

        注意：
        - 不携带 Content-Type，否则 OSS 预签名签名校验失败(403)
        - 必须设置 Content-Length，否则 OSS 接收到截断内容导致文件损坏
        """
        file_bytes = file_path.read_bytes()
        resp = requests.put(
            file_url,
            data=file_bytes,
            headers={"Content-Length": str(len(file_bytes))},
            timeout=300,
        )
        resp.raise_for_status()

    def agent_get_task(self, task_id: str) -> dict[str, Any]:
        """查询 Agent 任务状态。

        Returns:
            {
              "task_id": "...",
              "state": "done",
              "markdown_url": "https://...",
              "err_msg": ""
            }
        """
        resp = self.session.get(self._url(f"/api/v1/agent/parse/{task_id}"))
        return self._check(resp)

    # ─────────────────────────────────────────────────────────────
    # 通用下载
    # ─────────────────────────────────────────────────────────────

    def download_file(self, url: str, dest: Path, chunk_size: int = 8192) -> None:
        """流式下载任意 URL 到本地文件。"""
        dest.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    f.write(chunk)
