"""Unicode 显示名分析：规范化、脚本检测与同形字符（confusable）判定。"""
from __future__ import annotations

import unicodedataplus
from confusables import is_confusable

# 脚本统计时忽略的脚本
IGNORED_SCRIPTS = frozenset({"Common", "Inherited"})

# 触发 422 混脚本限制的脚本集合：同一名称中出现其中两种及以上即拒绝
RESTRICTED_SCRIPTS = frozenset({"Latin", "Cyrillic", "Greek"})


def canonicalize(name: str) -> str:
    """计算规范名：NFKC 规范化 + casefold。"""
    return unicodedataplus.normalize("NFKC", name).casefold()


def script_report(name: str) -> dict[str, list[dict[str, str]]]:
    """逐字符统计脚本（忽略 Common / Inherited）。

    返回 {脚本名: [{"character": 字符, "codepoint": "U+XXXX"}, ...]}，
    字符按名称中出现顺序排列。
    """
    report: dict[str, list[dict[str, str]]] = {}
    for char in name:
        script = unicodedataplus.script(char)
        if script in IGNORED_SCRIPTS:
            continue
        report.setdefault(script, []).append(
            {"character": char, "codepoint": f"U+{ord(char):04X}"}
        )
    return report


def mixed_script_violation(name: str) -> dict[str, list[dict[str, str]]] | None:
    """若名称同时含 Latin/Cyrillic/Greek 中两种及以上脚本，返回对应脚本与码点；否则返回 None。"""
    report = script_report(name)
    present = sorted(set(report) & RESTRICTED_SCRIPTS)
    if len(present) >= 2:
        return {script: report[script] for script in present}
    return None


def find_conflicts(
    name: str,
    canonical_name: str,
    existing: list[dict],
) -> list[dict]:
    """与同命名空间已有名称逐条比对。

    规范名相同记为 canonical_match；原名经 Unicode 同形字符逐条判定
    可混淆记为 confusable。
    """
    conflicts: list[dict] = []
    for row in existing:
        if row["canonical_name"] == canonical_name:
            reason = "canonical_match"
        elif is_confusable(name, row["original_name"]):
            reason = "confusable"
        else:
            continue
        conflicts.append(
            {
                "id": row["id"],
                "name": row["original_name"],
                "canonical_name": row["canonical_name"],
                "reason": reason,
            }
        )
    return conflicts
