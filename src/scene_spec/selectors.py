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
