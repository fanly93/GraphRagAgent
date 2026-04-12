"""数据模型：任务状态、解析作业、解析结果。"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ParseAPI(Enum):
    """使用哪个 MinerU API。"""
    PRECISE = "precise"   # /api/v4/  精准解析
    AGENT = "agent"       # /api/v1/agent/  轻量 Agent


class TaskState(Enum):
    """任务状态（精准 API + Agent API 均覆盖）。"""
    # 精准解析 API
    PENDING = "pending"
    CONVERTING = "converting"   # Office 文档转换中
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    # Agent API 额外状态
    WAITING_FILE = "waiting-file"
    UPLOADING = "uploading"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, s: str) -> "TaskState":
        try:
            return cls(s)
        except ValueError:
            return cls.UNKNOWN

    def is_terminal(self) -> bool:
        return self in (TaskState.DONE, TaskState.FAILED)

    def is_success(self) -> bool:
        return self == TaskState.DONE


@dataclass
class ParseJob:
    """描述一个文件的完整解析作业。"""
    source_path: Path                   # 原始文件路径
    api: ParseAPI                       # 使用哪个 API

    # 上传阶段
    file_id: Optional[str] = None       # Precise API 文件 ID
    presigned_url: Optional[str] = None # 预签名上传 URL

    # 任务阶段
    task_id: Optional[str] = None       # 任务 ID（Precise 单任务 / Agent）
    batch_id: Optional[str] = None      # 批量任务 ID（Precise 批量）

    # 结果阶段
    state: TaskState = TaskState.UNKNOWN
    result_url: Optional[str] = None    # full_zip_url（精准）或 markdown_url（Agent）
    output_dir: Optional[Path] = None   # 本地输出目录
    error: Optional[str] = None


@dataclass
class ParseResult:
    """一个文件的完整解析结果，包含本地落盘路径。"""
    job: ParseJob
    success: bool

    # 落盘文件路径
    markdown_path: Optional[Path] = None
    content_list_path: Optional[Path] = None
    middle_json_path: Optional[Path] = None
    model_json_path: Optional[Path] = None
    images_dir: Optional[Path] = None

    error: Optional[str] = None

    def summary(self) -> str:
        if not self.success:
            return f"[FAIL] {self.job.source_path.name}: {self.error}"
        parts = [f"[OK]  {self.job.source_path.name}"]
        if self.markdown_path:
            parts.append(f"  markdown      → {self.markdown_path}")
        if self.content_list_path:
            parts.append(f"  content_list  → {self.content_list_path}")
        if self.images_dir:
            imgs = list(self.images_dir.glob("*.jpg")) if self.images_dir.exists() else []
            parts.append(f"  images/       → {len(imgs)} 张")
        return "\n".join(parts)
