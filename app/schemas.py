"""请求 / 响应模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class NameRequest(BaseModel):
    """注册 / 检查请求体。"""

    name: str = Field(min_length=1, max_length=64, examples=["Аdmin"])

    @field_validator("name")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class ScriptDetail(BaseModel):
    script: str
    characters: list[str]
    code_points: list[str]


class ConflictRecord(BaseModel):
    id: int
    original_name: str
    normalized_name: str
    reason: Literal["normalized_match", "confusable"]


class AnalysisResult(BaseModel):
    """名称分析结果（检查接口的响应，也是注册前的内部判定结果）。"""

    namespace: str
    original_name: str
    normalized_name: str
    scripts: list[str]
    script_details: list[ScriptDetail]
    restricted_scripts_used: list[str]
    mixed_script_violation: bool
    conflicts: list[ConflictRecord]


class NameRecord(BaseModel):
    id: int
    namespace: str
    original_name: str
    normalized_name: str
    created_at: str


class ErrorDetail(BaseModel):
    error: str
    message: str
