"""选择器：obj、obj#span、obj.part、obj.part[i]、obj.part[i:j]、obj[i]、obj[i:j]。"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SELECTOR = re.compile(
    r"^(?P<obj>[a-z][a-z0-9_]*)"
    r"(?:#(?P<span>[A-Za-z_][A-Za-z0-9_]*)"
    r"|\.(?P<part>[A-Za-z_][A-Za-z0-9_]*)(?:\[(?P<pindex>[0-9]+(?::[0-9]+)?)\])?"
    r"|\[(?P<index>[0-9]+(?::[0-9]+)?)\])?$"
)


@dataclass(frozen=True)
class Selector:
    obj: str
    span: str | None = None
    part: str | None = None
    index: tuple[int, int] | None = None  # 半开区间 [start, stop)

    @property
    def last(self) -> int | None:
        """用到的最大下标，越界检查用。"""
        return None if self.index is None else self.index[1] - 1


def _index(text: str | None) -> tuple[int, int] | None:
    if text is None:
        return None
    if ":" in text:
        start, stop = (int(x) for x in text.split(":"))
        return start, stop
    i = int(text)
    return i, i + 1


def parse(text: str) -> Selector | None:
    m = _SELECTOR.match(text)
    if not m:
        return None
    return Selector(
        obj=m.group("obj"),
        span=m.group("span"),
        part=m.group("part"),
        index=_index(m.group("pindex") or m.group("index")),
    )


def parse_slice(value: object) -> tuple[int, int] | None:
    """组件参数里的下标：整数或 "i:j" 字符串。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value, value + 1
    if isinstance(value, str) and re.fullmatch(r"[0-9]+(:[0-9]+)?", value):
        return _index(value)
    return None


MATCH_REPLACES = ("tex", "auto")  # 按片段配对的 transform 默认替换源对象


def transform_replaces(action: dict) -> bool:
    """transform 结束后源（from）是否被替换掉（淡出、不再可见）。

    replace 显式写了就按它；没写时 match: tex / auto 默认替换（配上的片段从源里"走"到目标里，源不该原样留着），
    其余（不写 match、match: shape）默认不替换：源保持不动，和以前一样。
    """
    if "replace" in action:
        return action["replace"] is True
    return action.get("match") in MATCH_REPLACES


def transform_replaced(action: dict) -> str | None:
    """被这个 transform 整个替换掉、之后不再可见的对象：from 是整个对象、且替换源时才有；否则 None。

    from 是片段或子元素时，替换只让这几项淡出，对象本身仍然可见。
    """
    if action.get("act") != "transform" or not isinstance(action.get("from"), str) or not transform_replaces(action):
        return None
    src = parse(action["from"])
    if src is None or src.span is not None or src.part is not None or src.index is not None:
        return None
    to = parse(action["to"]) if isinstance(action.get("to"), str) else None
    if to is not None and to.obj == src.obj:
        return None
    return src.obj
