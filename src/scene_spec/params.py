"""场景参数（顶层 params）和 tween 动作的检查，错误码 SS400–SS419。

参数是随时间连续变化的数：tween 动作把它们在动作时长内补间到目标值，组件属性和 readout 对象里
可以写引用参数的表达式（白名单语法，见 expr.py，从不 eval）。这里检查：

- SS400 参数声明不合法：名字和 x / pi / e / 函数名冲突，min > max，初值不在 [min, max] 里；
- SS401 表达式语法错；
- SS402 表达式引用了没声明的参数；
- SS403 这里不能用 x（只有曲线的 f 能用 x；点的横坐标、斜率、读数只能由数和参数决定）；
- SS404 tween 写法不对：没有 args、带了 target / from / to；
- SS405 tween 补间了没声明的参数；
- SS406 tween 的目标不是数；
- SS407 tween 的目标超出参数声明的 [min, max]；
- SS408 ease 只用于 tween；
- SS409 （警告）声明了参数但没有任何表达式用到它，补间它画面不会变；
- SS410 readout 对象写法不对（缺 value、format 和 digits 冲突）；
- SS411 参数取到某个关键值时，表达式没有定义或几何出了范围（按初值和每次补间的目标值逐个代入检查）。
"""

from __future__ import annotations

import math

from . import expr
from .report import Report

DEFAULT_TWEEN = 1.5  # tween 不写 dur 时的时长（秒），kit 用同一个值


def declared(doc: dict) -> dict[str, dict]:
    """参数名 → {value, min?, max?}（简写的初值展开成映射）。"""
    out: dict[str, dict] = {}
    for name, spec in (doc.get("params") or {}).items():
        out[name] = dict(spec) if isinstance(spec, dict) else {"value": spec}
    return out


def initial(doc: dict) -> dict[str, float]:
    return {k: float(v["value"]) for k, v in declared(doc).items()}


def tweens(doc: dict):
    """按文件顺序产出 (beat 序号, 动作序号, 动作) —— 所有 tween 动作。"""
    for n, beat in enumerate(doc.get("beats", [])):
        for i, action in enumerate(beat.get("do", [])):
            if action.get("act") == "tween":
                yield n, i, action


def _number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def states(doc: dict) -> list[dict[str, float]]:
    """参数会经过的关键取值：初值、每次补间之后的值，以及相邻两组之间的中点（补间是单调的插值）。"""
    env = initial(doc)
    known = set(env)
    out = [dict(env)]
    for _n, _i, action in tweens(doc):
        args = action.get("args") or {}
        nxt = dict(env)
        for k, v in args.items():
            if k in known and _number(v):
                nxt[k] = float(v)
        if nxt != env:
            out.append({k: (env[k] + nxt[k]) / 2 for k in env})
            out.append(dict(nxt))
        env = nxt
    return out


class ExprChecker:
    """在一份文档里检查表达式：记下用到的参数，给出语法树。"""

    def __init__(self, doc: dict, report: Report):
        self.r = report
        self.params = declared(doc)
        self.names = set(self.params)
        self.used: set[str] = set()
        self.states = states(doc)

    def parse(self, value: object, path: str, allow_x: bool = False) -> tuple | None:
        """数或表达式字符串 → 语法树；有问题时报错并返回 None。"""
        if _number(value):
            return ("num", float(value))
        if not isinstance(value, str) or not value.strip():
            self.r.error("SS401", path, f"应为数或表达式字符串，收到 {value!r}")
            return None
        try:
            tree = expr.parse(value, self.names)
        except expr.UnknownName as exc:
            known = "、".join(sorted(self.names)) or "无"
            self.r.error("SS402", path, f"{value!r} 里的 {exc.name!r} 不是声明过的参数（params 里有：{known}）")
            return None
        except expr.ExprError as exc:
            self.r.error("SS401", path, f"表达式 {value!r} 写得不对：{exc}")
            return None
        if not allow_x and expr.uses_x(tree):
            self.r.error("SS403", path, f"{value!r} 里不能用 x：这里的值只能由数和参数决定（x 只在曲线的 f 里用）")
            return None
        self.used |= expr.free_names(tree)
        return tree

    def values(self, tree: tuple, x: float = math.nan) -> list[tuple[dict[str, float], float]]:
        """在每组关键取值下求值：[(参数取值, 结果)]。"""
        return [(env, expr.evaluate(tree, x, env)) for env in self.states]

    @staticmethod
    def describe(env: dict[str, float]) -> str:
        return "，".join(f"{k}={v:g}" for k, v in env.items()) or "（无参数）"


def check_declarations(doc: dict, report: Report) -> None:
    for name, spec in declared(doc).items():
        path = f"params.{name}"
        if name in expr.RESERVED:
            report.error("SS400", path, f"参数名 {name!r} 和表达式里的保留名冲突（x、pi、e 和函数名不能当参数）")
        lo, hi, v = spec.get("min"), spec.get("max"), spec["value"]
        if lo is not None and hi is not None and lo > hi:
            report.error("SS400", path, f"min={lo:g} 大于 max={hi:g}")
        elif (lo is not None and v < lo) or (hi is not None and v > hi):
            report.error("SS400", f"{path}.value", f"初值 {v:g} 不在 [{lo if lo is not None else '-∞'}, {hi if hi is not None else '∞'}] 里")


def check_tween(action: dict, path: str, doc: dict, report: Report) -> None:
    params = declared(doc)
    for key in ("target", "from", "to"):
        if key in action:
            report.error("SS404", f"{path}.{key}", f"tween 改的是参数，不需要 {key}（画面上依赖参数的对象自己会跟着变）")
    args = action.get("args")
    if not args:
        report.error("SS404", path, "tween 需要 args：要补间的参数和目标值，例如 args: {k: 2}")
        return
    for name, target in args.items():
        apath = f"{path}.args.{name}"
        if name not in params:
            known = "、".join(sorted(params)) or "无"
            report.error("SS405", apath, f"没有声明参数 {name!r}（params 里有：{known}）")
            continue
        if not _number(target):
            report.error("SS406", apath, f"tween 的目标应为数，收到 {target!r}")
            continue
        lo, hi = params[name].get("min"), params[name].get("max")
        if (lo is not None and target < lo) or (hi is not None and target > hi):
            report.error("SS407", apath, f"目标 {target:g} 超出参数 {name} 的范围 [{lo}, {hi}]")


def check_readout(definition: dict, path: str, ex: ExprChecker, report: Report) -> None:
    if "value" not in definition:
        report.error("SS410", path, "readout 对象需要 value：要显示的值（数或表达式）")
        return
    if "text" in definition or "tex" in definition:
        report.error("SS410", path, "readout 用 label 写前面的文字，不用 text / tex")
    if definition.get("format") == "fraction" and "digits" in definition:
        report.error("SS410", f"{path}.digits", "format: fraction 时不用 digits（写不成分数时按 2 位小数）")
    tree = ex.parse(definition["value"], f"{path}.value")
    if tree is None:
        return
    for env, v in ex.values(tree):
        if not math.isfinite(v):
            report.error("SS411", f"{path}.value", f"参数取 {ex.describe(env)} 时，{definition['value']!r} 没有定义")
            break


def check_unused(ex: ExprChecker, doc: dict, report: Report) -> None:
    for name in sorted(ex.names - ex.used):
        tweened = any(name in (a.get("args") or {}) for _n, _i, a in tweens(doc))
        why = "补间它画面不会变" if tweened else "也没有被补间"
        report.warning("SS409", f"params.{name}", f"参数 {name} 没有被任何表达式用到，{why}")
