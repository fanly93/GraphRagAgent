"""SQLite 数据库初始化与 CRUD（aiosqlite）。"""

from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from typing import Optional

import config

DDL = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id           TEXT PRIMARY KEY,
    filename         TEXT NOT NULL,
    file_type        TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'UPLOADED',
    mineru_api_type  TEXT,
    mineru_batch_id  TEXT,
    mineru_task_id   TEXT,
    mineru_output_dir TEXT,
    vector_status    TEXT DEFAULT 'pending',
    kg_status        TEXT DEFAULT 'pending',
    chunk_count      INTEGER,
    entity_count     INTEGER,
    error_msg        TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def init_db() -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(DDL)
        await db.commit()


async def insert_document(
    doc_id: str,
    filename: str,
    file_type: str,
    status: str = "UPLOADED",
) -> None:
    now = _now()
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO documents
               (doc_id, filename, file_type, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (doc_id, filename, file_type, status, now, now),
        )
        await db.commit()


async def get_document(doc_id: str) -> Optional[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_documents(
    status_filter: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status_filter:
            count_row = await (
                await db.execute(
                    "SELECT COUNT(*) FROM documents WHERE status = ?", (status_filter,)
                )
            ).fetchone()
            total = count_row[0]
            async with db.execute(
                "SELECT * FROM documents WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status_filter, limit, offset),
            ) as cur:
                rows = await cur.fetchall()
        else:
            count_row = await (
                await db.execute("SELECT COUNT(*) FROM documents")
            ).fetchone()
            total = count_row[0]
            async with db.execute(
                "SELECT * FROM documents ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ) as cur:
                rows = await cur.fetchall()
        return total, [dict(r) for r in rows]


async def update_document(doc_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [doc_id]
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            f"UPDATE documents SET {set_clause} WHERE doc_id = ?", values
        )
        await db.commit()


async def delete_document(doc_id: str) -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        await db.commit()


async def count_by_status() -> dict:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status, COUNT(*) as cnt FROM documents GROUP BY status"
        ) as cur:
            rows = await cur.fetchall()
    result = {"total": 0, "ready": 0, "indexing": 0, "parsing": 0, "failed": 0}
    for row in rows:
        s = row["status"]
        cnt = row["cnt"]
        result["total"] += cnt
        if s == "READY":
            result["ready"] += cnt
        elif s in ("INDEXING", "PARSED"):
            result["indexing"] += cnt
        elif s in ("PARSING", "UPLOADED"):
            result["parsing"] += cnt
        elif s in ("PARSE_FAILED", "INDEX_FAILED"):
            result["failed"] += cnt
    return result
