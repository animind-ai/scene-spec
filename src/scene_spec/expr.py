"""函数表达式：graph 组件里 f: "x^2"、"abs(x)"、"sin(x)/2" 这样的字符串。

只认白名单里的东西，从不 eval：
- 数字（含小数）、自变量 x、常数 pi / e；
- + - * / ^（也可写 **），一元正负号，括号；数字紧跟 x、函数或括号时是隐式乘法（2x、3(x+1)）；
- 函数 sin cos tan exp ln log sqrt abs（log 和 ln 都是自然对数）；
- 场景参数（顶层 params 声明的名字，例如 k、b、t、theta、x_0）：parse(text, names={...}) 才认。
  参数名紧挨着写也算乘法：kx = k·x，2kx = 2·k·x（按已知名字拆开）。

parse() 把字符串变成元组语法树：("num", v)、("x",)、("var", 名字)、("neg", a)、
("add"|"sub"|"mul"|"div"|"pow", a, b)、("call", 名字, a)。evaluate() 求值，定义域外返回 nan。
kit 用同一棵树做前向自动微分（画精确的贝塞尔曲线）。
"""

from __future__ import annotations

import math
import re

FUNCTIONS = ("sin", "cos", "tan", "exp", "ln", "log", "sqrt", "abs")
CONSTANTS = {"pi": math.pi, "e": math.e}
MAX_LENGTH = 200

_TOKEN = re.compile(r"\s*(?:(?P<num>\d+(?:\.\d*)?|\.\d+)|(?P<name>[A-Za-z]+(?:_[A-Za-z0-9]+)?)|(?P<op>\*\*|[-+*/^()]))")
NAME = re.compile(r"^[A-Za-z]+(_[A-Za-z0-9]+)?$")  # 参数名的写法：k、theta、x_0、k_1
RESERVED = {"x", *CONSTANTS, *FUNCTIONS}
ANY = None  # parse(names=ANY)：不认识的名字一律当参数（只查语法，名字留给调用方核对）


class ExprError(ValueError):
    pass


class UnknownName(ExprError):
    """表达式里有没声明的名字（语法本身没问题）。"""

    def __init__(self, name: str, message: str):
        super().__init__(message)
        self.name = name


def _split(word: str, known: set[str]) -> list[str] | None:
    """把连写的名字拆成已知名字（kx → k, x）；拆法不止一种时取段数最少的，拆不开返回 None。"""
    best: dict[int, list[str]] = {0: []}
    for i in range(1, len(word) + 1):
        for j in range(i):
            if j in best and word[j:i] in known:
                cand = best[j] + [word[j:i]]
                if i not in best or len(cand) < len(best[i]):
                    best[i] = cand
    return best.get(len(word))


def tokenize(text: str, names=frozenset()) -> list[tuple[str, str]]:
    """names：认得的参数名；ANY 表示不认识的名字都当参数。"""
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
        pos = m.end()
        if kind == "name" and value not in RESERVED:
            if names is not ANY and value in names:
                tokens.append(("var", value))
                continue
            known = RESERVED | (set() if names is ANY else set(names))
            pieces = _split(value, known) if "_" not in value else None
            if pieces:
                tokens += [("var", p) if p not in RESERVED else ("name", p) for p in pieces]
                continue
            if names is ANY:
                tokens.append(("var", value))
                continue
            allowed = "、".join(("x", *CONSTANTS, *FUNCTIONS, *sorted(names)))
            raise UnknownName(value, f"不认识的名字 {value!r}（只能用 {allowed}）")
        tokens.append((kind, "^" if value == "**" else value))
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
            elif tok[0] in ("name", "num", "var") or tok[1] == "(":
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
        if kind == "var":
            return ("var", value)
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


def parse(text: str, names=frozenset(), allow_x: bool = True) -> tuple:
    """字符串 → 语法树；不合法时抛 ExprError（中文说明），有没声明的名字时抛 UnknownName。

    names：认得的参数名（默认没有，只认 x）；ANY：不认识的名字都当参数，只查语法。
    allow_x=False：表达式里不能出现 x（例如点的横坐标 x: "t+1" 只能由参数决定）。
    """
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return ("num", float(text))
    p = _Parser(tokenize(text, names))
    node = p.expr()
    if p.peek() is not None:
        raise ExprError(f"多出来 {p.peek()[1]!r}")
    if not allow_x and uses_x(node):
        raise ExprError("这里不能用 x（只能用数和参数）")
    return node


def free_names(node: tuple) -> set[str]:
    """语法树里用到的参数名。"""
    if node[0] == "var":
        return {node[1]}
    out: set[str] = set()
    for child in node[1:]:
        if isinstance(child, tuple):
            out |= free_names(child)
    return out


def uses_x(node: tuple) -> bool:
    return node[0] == "x" or any(isinstance(c, tuple) and uses_x(c) for c in node[1:])


def value(node: tuple, env: dict[str, float] | None = None, x: float = math.nan) -> float:
    """不含 x 的表达式在参数取 env 时的值；定义域外返回 nan。"""
    return evaluate(node, x, env)


_F = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp,
    "ln": math.log, "log": math.log, "sqrt": math.sqrt, "abs": abs,
}


def evaluate(node: tuple, x: float, env: dict[str, float] | None = None) -> float:
    """在 x 处、参数取 env 时求值；定义域外（除以零、负数开方、溢出）返回 nan。缺参数时抛 KeyError。"""
    try:
        return float(_eval(node, float(x), env or {}))
    except (ValueError, ZeroDivisionError, OverflowError):
        return math.nan


def _eval(node: tuple, x: float, env: dict[str, float]) -> float:
    op = node[0]
    if op == "num":
        return node[1]
    if op == "x":
        return x
    if op == "var":
        return float(env[node[1]])
    if op == "neg":
        return -_eval(node[1], x, env)
    if op == "call":
        return _F[node[1]](_eval(node[2], x, env))
    a, b = _eval(node[1], x, env), _eval(node[2], x, env)
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
