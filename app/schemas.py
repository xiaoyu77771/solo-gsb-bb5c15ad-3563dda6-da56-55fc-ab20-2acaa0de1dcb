"""请求 / 响应模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class NameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64, description="待注册/检查的显示名")


class ScriptChar(BaseModel):
    character: str
    codepoint: str


class ConflictRecord(BaseModel):
    id: int
    name: str
    canonical_name: str
    reason: str = Field(description="canonical_match 或 confusable")


class RegisteredName(BaseModel):
    id: int
    namespace: str
    name: str
    canonical_name: str
    created_at: str


class CheckResponse(BaseModel):
    namespace: str
    name: str
    canonical_name: str
    scripts: dict[str, list[ScriptChar]]
    mixed_script: bool
    conflicts: list[ConflictRecord]
    registrable: bool
