"""流程图生成请求的用户约束提示词。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


DETAIL_LEVEL_CONSTRAINTS = {
    "concise": "简要：只保留主流程和必要的关键判断，节点文案简短，避免展开次要步骤。",
    "standard": "标准：覆盖主要步骤、角色和关键判断，在完整性与可读性之间保持平衡。",
    "detailed": "详细：展开角色、输入输出、分支、异常路径和结束条件，尽可能完整表达业务流程。",
}

THEME_CONSTRAINTS = {
    "blue": "商务蓝：流程图节点使用清晰、克制的蓝色系配色。",
    "purple": "科技紫：流程图节点使用统一的紫色系配色。",
    "green": "清新绿：流程图节点使用统一的绿色系配色。",
}


def _first_value(request: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in request and request[name] is not None:
            return request[name]
    return None


def is_thinking_enabled(request: Mapping[str, Any]) -> bool:
    """读取用户的深度思考开关，兼容 API 的 camelCase 别名。"""

    value = _first_value(request, "thinking_enabled", "thinkingEnabled", "deepThinking")
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value is True


def build_generation_prompt(request: Mapping[str, Any]) -> str:
    """把用户描述和受控生成选项合并为供应商的用户提示词。"""

    prompt = request.get("prompt")
    if not isinstance(prompt, str):
        return ""
    prompt = prompt.strip()

    direction = request.get("direction")
    if direction == "AUTO":
        direction_note = "请自行判断最适合的流程图方向，并在 direction 和 mermaidSource 中使用同一个 TB 或 LR。"
    elif direction in {"TB", "LR"}:
        direction_note = f"流程图方向必须是 {direction}。"
    else:
        direction_note = ""

    detail_level = str(_first_value(request, "detail_level", "detailLevel") or "standard").lower()
    theme = str(_first_value(request, "diagram_theme", "diagramTheme", "theme") or "blue").lower()
    constraints = [
        "请严格遵守以下生成约束，并让返回的 JSON、节点结构和 mermaidSource 一致：",
        DETAIL_LEVEL_CONSTRAINTS.get(detail_level, DETAIL_LEVEL_CONSTRAINTS["standard"]),
        THEME_CONSTRAINTS.get(theme, THEME_CONSTRAINTS["blue"]),
        "节点 style 可包含 fill 和 stroke；如果返回节点样式，必须只使用 #RGB 或 #RRGGBB 颜色值。",
    ]
    if direction_note:
        constraints.insert(0, direction_note)
    return f"{prompt}\n\n【生成约束】\n" + "\n".join(f"- {item}" for item in constraints)


__all__ = [
    "DETAIL_LEVEL_CONSTRAINTS",
    "THEME_CONSTRAINTS",
    "build_generation_prompt",
    "is_thinking_enabled",
]
