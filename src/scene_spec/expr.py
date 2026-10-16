"""函数表达式：graph 组件里 f: "x^2"、"abs(x)"、"sin(x)/2" 这样的字符串。

只认白名单里的东西，从不 eval：
- 数字（含小数）、自变量 x、常数 pi / e；
- + - * / ^（也可写 **），一元正负号，括号；数字紧跟 x、函数或括号时是隐式乘法（2x、3(x+1)）；
- 函数 sin cos tan exp ln log sqrt abs（log 和 ln 都是自然对数）。

parse() 把字符串变成元组语法树：("num", v)、("x",)、("neg", a)、("add"|"sub"|"mul"|"div"|"pow", a, b)、
("call", 名字, a)。evaluate() 求值，定义域外返回 nan。kit 用同一棵树做前向自动微分（画精确的贝塞尔曲线）。
"""

from __future__ import annotations

import math
import re

FUNCTIONS = ("sin", "cos", "tan", "exp", "ln", "log", "sqrt", "abs")
CONSTANTS = {"pi": math.pi, "e": math.e}
MAX_LENGTH = 200

_TOKEN = re.compile(r"\s*(?:(?P<num>\d+(?:\.\d*)?|\.\d+)|(?P<name>[A-Za-z]+)|(?P<op>\*\*|[-+*/^()]))")


class ExprError(ValueError):
    pass


def tokenize(text: str) -> list[tuple[str, str]]:
    if not isinstance(text, str) or not text.strip():
        raise ExprError("表达式是空的")
    if len(text) > MAX_LENGTH:
        raise ExprError(f"表达式太长（超过 {MAX_LENGTH} 个字符）")
    tokens: list[tuple[str, str]] = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ExprError(f"看不懂第 {pos + 1} 个字符起的 {text[pos:pos + 8]!r}")
        kind = m.lastgroup
        value = m.group(kind)
        if kind == "name" and value not in FUNCTIONS and value not in CONSTANTS and value != "x":
            allowed = "、".join(("x", *CONSTANTS, *FUNCTIONS))
            raise ExprError(f"不认识的名字 {value!r}（只能用 {allowed}）")
        tokens.append((kind, "^" if value == "**" else value))
        pos = m.end()
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens, self.i = tokens, 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self, value: str | None = None) -> tuple[str, str]:
        tok = self.peek()
        if tok is None or (value is not None and tok[1] != value):
            raise ExprError(f"这里应该是 {value!r}" if value else "表达式没写完")
        self.i += 1
        return tok

    def expr(self) -> tuple:
        node = self.term()
        while (tok := self.peek()) and tok[1] in "+-" and tok[0] == "op":
            self.take()
            node = ("add" if tok[1] == "+" else "sub", node, self.term())
        return node

    def term(self) -> tuple:
        node = self.unary()
        while (tok := self.peek()) is not None:
            if tok[0] == "op" and tok[1] in "*/":
                self.take()
                node = ("mul" if tok[1] == "*" else "div", node, self.unary())
            elif tok[0] in ("name", "num") or tok[1] == "(":
                node = ("mul", node, self.power())  # 隐式乘法：2x、3(x+1)、2sin(x)
            else:
                break
        return node

    def unary(self) -> tuple:
        tok = self.peek()
        if tok and tok[0] == "op" and tok[1] in "+-":
            self.take()
            inner = self.unary()
            return ("neg", inner) if tok[1] == "-" else inner
        return self.power()

    def power(self) -> tuple:
        base = self.atom()
        tok = self.peek()
        if tok and tok[1] == "^":
            self.take()
            return ("pow", base, self.unary())  # 右结合：2^-x、x^2^3 = x^(2^3)
        return base

    def atom(self) -> tuple:
        kind, value = self.take()
        if kind == "num":
            return ("num", float(value))
        if kind == "name":
            if value == "x":
                return ("x",)
            if value in CONSTANTS:
                return ("num", CONSTANTS[value])
            self.take("(")
            arg = self.expr()
            self.take(")")
            return ("call", value, arg)
        if value == "(":
            node = self.expr()
            self.take(")")
            return node
        raise ExprError(f"这里不能是 {value!r}")


def parse(text: str) -> tuple:
    """字符串 → 语法树；不合法时抛 ExprError（中文说明）。"""
    p = _Parser(tokenize(text))
    node = p.expr()
    if p.peek() is not None:
        raise ExprError(f"多出来 {p.peek()[1]!r}")
    return node


_F = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp,
    "ln": math.log, "log": math.log, "sqrt": math.sqrt, "abs": abs,
}


def evaluate(node: tuple, x: float) -> float:
    """在 x 处求值；定义域外（除以零、负数开方、溢出）返回 nan。"""
    try:
        return float(_eval(node, float(x)))
    except (ValueError, ZeroDivisionError, OverflowError):
        return math.nan


def _eval(node: tuple, x: float) -> float:
    op = node[0]
    if op == "num":
        return node[1]
    if op == "x":
        return x
    if op == "neg":
        return -_eval(node[1], x)
    if op == "call":
        return _F[node[1]](_eval(node[2], x))
    a, b = _eval(node[1], x), _eval(node[2], x)
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mul":
        return a * b
    if op == "div":
        return a / b
    result = a ** b
    if isinstance(result, complex):
        raise ValueError("负数的非整数次幂")
    return result
