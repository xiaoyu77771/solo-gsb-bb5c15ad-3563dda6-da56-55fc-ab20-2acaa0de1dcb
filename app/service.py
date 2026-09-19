"""业务逻辑：名称分析与注册。

判定顺序（注册时）：
1. 混脚本违规（Latin/Cyrillic/Greek 出现两种及以上）-> 422
2. 与同命名空间已有名称逐条比较：规范名相同或 confusables 判定
   为同形 -> 409，并返回全部冲突记录
3. 落库；(namespace, normalized_name) 唯一约束兜底并发写入
"""
from __future__ import annotations

import sqlite3

from confusables import is_confusable

from .analysis import analyze_scripts, normalize_name

REASON_NORMALIZED_MATCH = "normalized_match"
REASON_CONFUSABLE = "confusable"


class NameConflictError(Exception):
    """数据库唯一约束冲突（并发下同规范名重复插入）。"""


def find_conflicts(conn: sqlite3.Connection, namespace: str, normalized_name: str) -> list[dict]:
    """与同命名空间内已有名称逐条做规范名相等 / 同形字符判定。"""
    rows = conn.execute(
        """
        SELECT id, original_name, normalized_name
        FROM display_names
        WHERE namespace = ?
        ORDER BY id
        """,
        (namespace,),
    ).fetchall()

    conflicts: list[dict] = []
    for row in rows:
        existing_normalized = row["normalized_name"]
        if existing_normalized == normalized_name:
            reason = REASON_NORMALIZED_MATCH
        elif is_confusable(normalized_name, existing_normalized):
            reason = REASON_CONFUSABLE
        else:
            continue
        conflicts.append(
            {
                "id": row["id"],
                "original_name": row["original_name"],
                "normalized_name": existing_normalized,
                "reason": reason,
            }
        )
    return conflicts


def analyze_name(conn: sqlite3.Connection, namespace: str, name: str) -> dict:
    """完整分析：规范名 + 脚本分析 + 冲突检测（只读，不落库）。"""
    normalized = normalize_name(name)
    return {
        "namespace": namespace,
        "original_name": name,
        "normalized_name": normalized,
        **analyze_scripts(name),
        "conflicts": find_conflicts(conn, namespace, normalized),
    }


def insert_name(conn: sqlite3.Connection, namespace: str, name: str, normalized_name: str) -> dict:
    """写入新名称，返回完整记录。唯一约束冲突时抛 NameConflictError。"""
    try:
        cursor = conn.execute(
            """
            INSERT INTO display_names (namespace, original_name, normalized_name)
            VALUES (?, ?, ?)
            """,
            (namespace, name, normalized_name),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise NameConflictError(normalized_name) from exc

    row = conn.execute(
        "SELECT * FROM display_names WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(row)


def list_names(conn: sqlite3.Connection, namespace: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM display_names WHERE namespace = ? ORDER BY id",
        (namespace,),
    ).fetchall()
    return [dict(row) for row in rows]
