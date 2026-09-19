"""FastAPI 应用入口。

接口一览：
- POST /namespaces/{namespace}/names   注册显示名（201 / 409 / 422）
- POST /namespaces/{namespace}/check   只分析不落库（200）
- GET  /namespaces/{namespace}/names   列出命名空间内已注册名称
- GET  /health                         健康检查
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, status

from . import database, service
from .schemas import AnalysisResult, NameRecord, NameRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时自动初始化数据库（建库建表，幂等）
    database.init_db()
    yield


app = FastAPI(
    title="Unicode Display Name Anti-Spoofing API",
    version="1.0.0",
    description=(
        "命名空间内的显示名防仿冒：NFKC+casefold 规范名查重、"
        "confusables 同形字符判定、Latin/Cyrillic/Greek 混脚本拦截。"
    ),
    lifespan=lifespan,
)


def get_db() -> Iterator[sqlite3.Connection]:
    conn = database.get_connection()
    try:
        yield conn
    finally:
        conn.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/namespaces/{namespace}/names",
    status_code=status.HTTP_201_CREATED,
    response_model=NameRecord,
    responses={
        409: {"description": "规范名相同或与已有名称同形（confusable）"},
        422: {"description": "混用 Latin/Cyrillic/Greek 中两种及以上脚本"},
    },
)
def register_name(namespace: str, payload: NameRequest, conn=Depends(get_db)) -> dict:
    analysis = service.analyze_name(conn, namespace, payload.name)

    if analysis["mixed_script_violation"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "mixed_script_violation",
                "message": (
                    "名称同时使用了 Latin/Cyrillic/Greek 中的 "
                    f"{len(analysis['restricted_scripts_used'])} 种脚本，"
                    "存在仿冒风险，已拒绝注册"
                ),
                "restricted_scripts_used": analysis["restricted_scripts_used"],
                "script_details": analysis["script_details"],
            },
        )

    if analysis["conflicts"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "name_conflict",
                "message": "规范名相同或与命名空间内已有名称同形",
                "normalized_name": analysis["normalized_name"],
                "conflicts": analysis["conflicts"],
            },
        )

    try:
        return service.insert_name(
            conn, namespace, payload.name, analysis["normalized_name"]
        )
    except service.NameConflictError:
        # 并发下唯一约束兜底：重新查出冲突记录返回
        conflicts = service.find_conflicts(conn, namespace, analysis["normalized_name"])
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "name_conflict",
                "message": "规范名相同或与命名空间内已有名称同形",
                "normalized_name": analysis["normalized_name"],
                "conflicts": conflicts,
            },
        )


@app.post(
    "/namespaces/{namespace}/check",
    response_model=AnalysisResult,
)
def check_name(namespace: str, payload: NameRequest, conn=Depends(get_db)) -> dict:
    """只分析不落库：返回规范名、脚本分析与潜在冲突。"""
    return service.analyze_name(conn, namespace, payload.name)


@app.get(
    "/namespaces/{namespace}/names",
    response_model=list[NameRecord],
)
def list_names(namespace: str, conn=Depends(get_db)) -> list[dict]:
    return service.list_names(conn, namespace)
