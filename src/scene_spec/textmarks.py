"""解析对象文字里的片段标注和旁白里的书签。

对象文字（设计稿 §6.2）：
    '令 [$b_n=A_{n+1}-A_n$]{#b_def .B}，则 ...'
- `$...$` 内部是数学内容，方括号、花括号都不参与标注；
- `$...$` 外面的 `[` 必须开启一个片段 `[...]{...}`，字面方括号写 `\\[`、`\\]`；
- `{...}` 里是空格分隔的属性：`#id` 最多一个，`.类` 可以是语义角色或排版样式。

旁白（设计稿 §7.1）：
    '按定义，后一项减前一项：{@d0}五减二，得三。'
- `{@name}` 是书签；`$...$` 外面的其他花括号都是错误。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ROLES = {"FG", "A", "B", "C", "HL", "NO", "DIM"}
STYLE_CLASSES = {"bold", "italic"}
_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class Span:
    text: str
    id: str | None = None
    classes: list[str] = field(default_factory=list)


@dataclass
class ParsedText:
    spans: list[Span] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _math_mask(text: str) -> tuple[list[bool], list[str]]:
    """标出每个字符是否在 $...$ 里。返回 (mask, 问题列表)。"""
    mask = [False] * len(text)
    problems: list[str] = []
    inside = False
    start = -1
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            mask[i] = mask[i + 1] = inside
            i += 2
            continue
        if ch == "$":
            inside = not inside
            start = i if inside else start
            mask[i] = True
        else:
            mask[i] = inside
        i += 1
    if inside:
        problems.append(f"第 {start + 1} 个字符处的 $ 没有闭合")
    return mask, problems


def parse_object_text(text: str) -> ParsedText:
    result = ParsedText()
    mask, result.problems = _math_mask(text)
    i = 0
    while i < len(text):
        ch = text[i]
        if mask[i]:
            i += 1
            continue
        if ch == "\\" and i + 1 < len(text) and text[i + 1] in "[]{}":
            i += 2
            continue
        if ch == "]":
            result.problems.append(f"第 {i + 1} 个字符处有多余的 ]（字面方括号请写 \\]）")
            i += 1
            continue
        if ch in "{}":
            result.problems.append(f"第 {i + 1} 个字符处有多余的花括号（只能用在 [...]{{...}} 里）")
            i += 1
            continue
        if ch != "[":
            i += 1
            continue
        # 找与之配对的 ]，跳过数学内容和转义
        j = i + 1
        while j < len(text) and not (text[j] == "]" and not mask[j] and text[j - 1] != "\\"):
            if text[j] == "[" and not mask[j] and text[j - 1] != "\\":
                break
            j += 1
        if j >= len(text) or text[j] != "]":
            result.problems.append(f"第 {i + 1} 个字符处的 [ 没有配对（字面方括号请写 \\[）")
            i += 1
            continue
        if j + 1 >= len(text) or text[j + 1] != "{":
            result.problems.append(f"第 {i + 1} 个字符处的 [...] 后面缺少 {{...}} 属性（字面方括号请写 \\[ \\]）")
            i = j + 1
            continue
        k = text.find("}", j + 2)
        if k < 0:
            result.problems.append(f"第 {j + 2} 个字符处的 {{ 没有闭合")
            break
        body = text[i + 1 : j]
        if not body.strip():
            result.problems.append(f"第 {i + 1} 个字符处的片段是空的")
        span = Span(text=body)
        for token in text[j + 2 : k].split():
            if token.startswith("#") and _ID.match(token[1:]):
                if span.id is not None:
                    result.problems.append(f"片段 [{body}] 有多个 #id")
                span.id = token[1:]
            elif token.startswith(".") and token[1:] in ROLES | STYLE_CLASSES:
                span.classes.append(token[1:])
            else:
                result.problems.append(
                    f"片段 [{body}] 的属性 {token!r} 不认识（可用 #id、"
                    f".{'/.'.join(sorted(ROLES))}、.{'/.'.join(sorted(STYLE_CLASSES))}）"
                )
        roles = [c for c in span.classes if c in ROLES]
        if len(roles) > 1:
            result.problems.append(f"片段 [{body}] 同时有多个角色 {roles}")
        result.spans.append(span)
        i = k + 1
    return result


_BOOKMARK = re.compile(r"\{@([A-Za-z_][A-Za-z0-9_]*)\}")


def parse_say_text(text: str) -> tuple[list[str], list[str]]:
    """返回 (书签名列表, 问题列表)。"""
    mask, problems = _math_mask(text)
    names: list[str] = []
    i = 0
    while i < len(text):
        if mask[i]:
            i += 1
            continue
        ch = text[i]
        if ch == "{":
            m = _BOOKMARK.match(text, i)
            if m:
                names.append(m.group(1))
                i = m.end()
                continue
            problems.append(f"第 {i + 1} 个字符处的花括号不是书签（书签写成 {{@名字}}）")
            close = text.find("}", i)
            if close >= 0:  # 整段跳过，同一处只报一次
                i = close + 1
                continue
        elif ch == "}":
            problems.append(f"第 {i + 1} 个字符处有多余的 }}")
        elif ch == "[" or ch == "]":
            problems.append(f"第 {i + 1} 个字符处有方括号：旁白里不支持片段标注")
        i += 1
    seen: set[str] = set()
    for name in names:
        if name in seen:
            problems.append(f"书签 @{name} 在同一句里出现了不止一次")
        seen.add(name)
    return names, problems
