"""SQLite 存储层：建库建表与连接获取。

直接运行可初始化数据库：python -m app.database
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("APP_DB_PATH", "names.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS display_names (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace      TEXT NOT NULL,
    original_name  TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (namespace, canonical_name)
);
CREATE INDEX IF NOT EXISTS idx_display_names_namespace
    ON display_names (namespace);
"""


def init_db(db_path: Path = DB_PATH) -> Path:
    """创建数据库与表结构（幂等）。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
    return db_path


@contextmanager
def get_connection():
    """每次调用返回新连接，结束自动提交/关闭。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    path = init_db()
    print(f"数据库已初始化: {path.resolve()}")
