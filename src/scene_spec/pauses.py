"""句间静音：按句末标点，不再用一个固定间隙。

voice 现在按语气取一个固定值（normal 0.35、brisk 0.25、slow 0.6、ask 0.55）。
发布内容改为看这一句说完时的标点。`say[].hold` 可以覆盖默认值，但必须落在该标点的区间里。
beat 的 `pause.hold` 是给学生看的停顿，另有区间。

voice 应调用 `silence_after(text, hold)` 决定拼进 `<beat>.wav` 的句间静音，不要再读 GAP 表。
"""

from __future__ import annotations

import re

_BOOKMARK = re.compile(r"\{@[A-Za-z_][A-Za-z0-9_]*\}")
_TRAILING = " \t\n\"'“”‘’」』）)」"

# 句末标点 → 默认静音、允许的最小值、最大值（秒）。
# 只认这些标点和它们的英文对应；别的句末（包括没有标点）走 other。
PUNCT: dict[str, dict] = {
    "comma": {"marks": "，,", "default": 0.22, "min": 0.12, "max": 0.40},
    "semicolon": {"marks": "；;", "default": 0.35, "min": 0.20, "max": 0.60},
    "period": {"marks": "。.", "default": 0.45, "min": 0.25, "max": 0.80},
    "question": {"marks": "？?", "default": 0.60, "min": 0.35, "max": 1.00},
    "exclaim": {"marks": "！!", "default": 0.55, "min": 0.30, "max": 0.95},
    "ellipsis": {"marks": "…", "default": 0.75, "min": 0.40, "max": 1.40},
    "other": {"marks": "", "default": 0.35, "min": 0.15, "max": 0.70},
}

# beat.pause.hold 的闭区间（秒）。predict / think 给学生反应时间；segment 可以是 0。
PAUSE_HOLD: dict[str, tuple[float, float]] = {
    "predict": (0.5, 8.0),
    "think": (0.5, 8.0),
    "segment": (0.0, 10.0),
}

# 时间报告里的实测间隙和规则值相差超过这个数就报错（voice 把时刻圆到毫秒）。
GAP_TOLERANCE = 0.05

_MARK_CLASS = {ch: name for name, spec in PUNCT.items() for ch in spec["marks"]}


def classify(text: str) -> str:
    """句末标点的类别。书签和收尾引号不算。"""
    plain = _BOOKMARK.sub("", text).rstrip(_TRAILING)
    if plain.endswith("...") or plain.endswith("…"):
        return "ellipsis"
    if not plain:
        return "other"
    return _MARK_CLASS.get(plain[-1], "other")


def silence_after(text: str, hold: float | None = None) -> float:
    """这一句之后应插入的静音秒数。最后一句 voice 不插入；调用方自己判断。

    hold 给了就用 hold（调用方应先用 `hold_in_range` 确认它落在区间里）。
    """
    if hold is not None:
        return float(hold)
    return PUNCT[classify(text)]["default"]


def hold_in_range(text: str, hold: float) -> bool:
    spec = PUNCT[classify(text)]
    return spec["min"] - 1e-9 <= float(hold) <= spec["max"] + 1e-9


def range_for(text: str) -> tuple[float, float, float]:
    """(default, min, max)。"""
    spec = PUNCT[classify(text)]
    return spec["default"], spec["min"], spec["max"]
