"""命名空间内 Unicode 显示名防仿冒 API。"""
from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Path, status

from .analysis import canonicalize, find_conflicts, mixed_script_violation, script_report
from .database import get_connection, init_db
from .schemas import CheckResponse, NameRequest, RegisteredName

NamespaceParam = Path(min_length=1, max_length=64, description="命名空间")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # 启动时自动初始化数据库（幂等）
    yield


app = FastAPI(
    title="Unicode 显示名防仿冒 API",
    version="1.0.0",
    lifespan=lifespan,
)


def _load_namespace_names(namespace: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, original_name, canonical_name FROM display_names WHERE namespace = ?",
            (namespace,),
        ).fetchall()
    return [dict(row) for row in rows]


def _check_name(namespace: str, name: str) -> CheckResponse:
    """只分析不落库：规范化、脚本统计、混脚本判定与冲突检测。"""
    canonical = canonicalize(name)
    scripts = script_report(name)
    violation = mixed_script_violation(name)
    conflicts = find_conflicts(name, canonical, _load_namespace_names(namespace))
    return CheckResponse(
        namespace=namespace,
        name=name,
        canonical_name=canonical,
        scripts=scripts,
        mixed_script=violation is not None,
        conflicts=conflicts,
        registrable=violation is None and not conflicts,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/namespaces/{namespace}/names",
    response_model=RegisteredName,
    status_code=status.HTTP_201_CREATED,
    summary="注册显示名",
)
def register_name(namespace: str = NamespaceParam, *, body: NameRequest) -> RegisteredName:
    name = body.name
    canonical = canonicalize(name)

    # 1) 混脚本限制：忽略 Common/Inherited 后，同时含 Latin/Cyrillic/Greek 中两种及以上 -> 422
    violation = mixed_script_violation(name)
    if violation is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "名称同时包含 Latin/Cyrillic/Greek 中两种及以上脚本",
                "scripts": violation,
            },
        )

    # 2) 与同命名空间已有名称逐条比对：规范名相同或可混淆 -> 409
    conflicts = find_conflicts(name, canonical, _load_namespace_names(namespace))
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "名称与命名空间内已有显示名冲突",
                "canonical_name": canonical,
                "conflicts": conflicts,
            },
        )

    # 3) 落库（唯一约束兜底并发冲突）
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO display_names (namespace, original_name, canonical_name)"
                " VALUES (?, ?, ?)",
                (namespace, name, canonical),
            )
            row = conn.execute(
                "SELECT id, namespace, original_name, canonical_name, created_at"
                " FROM display_names WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "名称与命名空间内已有显示名冲突",
                "canonical_name": canonical,
                "conflicts": find_conflicts(name, canonical, _load_namespace_names(namespace)),
            },
        )

    return RegisteredName(
        id=row["id"],
        namespace=row["namespace"],
        name=row["original_name"],
        canonical_name=row["canonical_name"],
        created_at=row["created_at"],
    )


@app.post(
    "/namespaces/{namespace}/names/check",
    response_model=CheckResponse,
    summary="检查显示名（只分析，不落库）",
)
def check_name(namespace: str = NamespaceParam, *, body: NameRequest) -> CheckResponse:
    return _check_name(namespace, body.name)


@app.get(
    "/namespaces/{namespace}/names",
    response_model=list[RegisteredName],
    summary="列出命名空间内已注册显示名",
)
def list_names(namespace: str = NamespaceParam) -> list[RegisteredName]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, namespace, original_name, canonical_name, created_at"
            " FROM display_names WHERE namespace = ? ORDER BY id",
            (namespace,),
        ).fetchall()
    return [
        RegisteredName(
            id=row["id"],
            namespace=row["namespace"],
            name=row["original_name"],
            canonical_name=row["canonical_name"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
