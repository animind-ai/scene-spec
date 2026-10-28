"""组件登记表。

组件本身由 kit / primitives 实现；这里只登记检查器需要知道的东西：
- 参数：哪些必填、类型对不对；
- 暴露的子元素：选择器 obj#span、obj.part[i]、obj[i] 能指向什么；
- 组件自带的动作和它们的参数；
- 数据自洽检查（例如差分表的下一行必须是上一行的逐项差）。

未登记的组件不报错，只给警告：引用和参数无法校验。kit 以后可以注册自己的组件。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from . import curves as _curves
from . import selectors
from .report import Report
from .textmarks import ROLES, parse_object_text


@dataclass
class Exposed:
    spans: set[str] = field(default_factory=set)  # obj#span
    parts: dict[str, int] = field(default_factory=dict)  # obj.part[i]：部件名 → 长度
    items: int | None = None  # obj[i]：列表长度
    state: dict = field(default_factory=dict)  # 组件自己的检查状态（例如 dissect 按动作顺序推演哪些块存在）


ParamCheck = Callable[[object], str | None]  # 返回问题描述，没问题返回 None
ActionCheck = Callable[[dict, "WidgetContext", Report, str], None]


@dataclass
class WidgetContext:
    obj_id: str
    definition: dict
    data: dict
    exposed: Exposed
    ex: object = None  # params.ExprChecker：解析参数表达式、给出参数的关键取值（检查器传入）


@dataclass
class Widget:
    name: str
    params: dict[str, tuple[bool, ParamCheck]]
    expose: Callable[[dict, dict], Exposed]
    actions: dict[str, ActionCheck] = field(default_factory=dict)
    validate: Callable[[WidgetContext, Report, str], None] | None = None


LAYOUT_KEYS = {
    "widget", "role", "in", "below", "above", "left_of", "right_of", "within", "over",
    "gap", "align", "size", "pin", "at", "allow",
}


def _str_list(value: object) -> str | None:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
        return "应为非空的字符串列表"
    return None


def _int_list(value: object) -> str | None:
    if not isinstance(value, list) or not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in value):
        return "应为非负整数列表"
    return None


def _str(value: object) -> str | None:
    return None if isinstance(value, str) and value else "应为非空字符串"


def _number_or_str(value: object) -> str | None:
    ok = isinstance(value, (int, float, str)) and not isinstance(value, bool)
    return None if ok else "应为数字或字符串"


def _positive_int(value: object) -> str | None:
    ok = isinstance(value, int) and not isinstance(value, bool) and value > 0
    return None if ok else "应为正整数"


def _positive_number(value: object) -> str | None:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
    return None if ok else "应为正数"


def _enum(*choices: str) -> ParamCheck:
    def check(value: object) -> str | None:
        return None if value in choices else f"应为 {' / '.join(choices)} 之一"

    return check


# ---------- 文字类组件：题卡、想一想框 ----------

def _expose_lines(definition: dict, data: dict) -> Exposed:
    exposed = Exposed()
    lines = definition.get("lines")
    if isinstance(lines, list):
        exposed.items = len(lines)
        for line in lines:
            if isinstance(line, str):
                exposed.spans |= {s.id for s in parse_object_text(line).spans if s.id}
    return exposed


def _validate_lines(ctx: WidgetContext, report: Report, path: str) -> None:
    lines = ctx.definition.get("lines")
    if not isinstance(lines, list):
        return
    seen: dict[str, int] = {}
    for n, line in enumerate(lines):
        if not isinstance(line, str):
            continue
        parsed = parse_object_text(line)
        for problem in parsed.problems:
            report.error("SS210", f"{path}.lines[{n}]", problem)
        for span in parsed.spans:
            if span.id:
                if span.id in seen:
                    report.error("SS211", f"{path}.lines[{n}]", f"片段 #{span.id} 与第 {seen[span.id]} 行重复")
                seen[span.id] = n


def _answers(value: object) -> str | None:
    if not isinstance(value, list) or not all(v is None or (isinstance(v, str) and v) for v in value):
        return "应为列表，每项是答案文字或 null（这一行没有答案）"
    return None


def _expose_card(definition: dict, data: dict) -> Exposed:
    exposed = _expose_lines(definition, data)
    answers = definition.get("answers")
    if isinstance(answers, list):
        exposed.parts["answer"] = len(answers)
    return exposed


def _validate_card(ctx: WidgetContext, report: Report, path: str) -> None:
    _validate_lines(ctx, report, path)
    answers, lines = ctx.definition.get("answers"), ctx.definition.get("lines")
    if isinstance(answers, list) and isinstance(lines, list) and len(answers) != len(lines):
        report.error("SS212", f"{path}.answers", f"answers 有 {len(answers)} 项，lines 有 {len(lines)} 行；没有答案的行写 null")


# ---------- 对齐的等式组 ----------

def _eq_rows(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return "应为非空列表"
    for row in value:
        if isinstance(row, str) and row:
            continue
        if isinstance(row, dict) and isinstance(row.get("tex"), str) and set(row) <= {"tex", "role"}:
            if "role" in row and row["role"] not in ROLES:
                return f"role 应为 {'/'.join(sorted(ROLES))} 之一"
            continue
        return "每行是 LaTeX 字符串（用 & 标出对齐点），或 {tex, role}"
    return None


# ---------- 数列格子 ----------

def _list_of_literals(value: object) -> str | None:
    if not isinstance(value, list) or not value or not all(isinstance(v, (int, float, str)) and not isinstance(v, bool) for v in value):
        return "应为非空列表，每项是数或 LaTeX 字符串"
    return None


def _nonneg_int(value: object) -> str | None:
    ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return None if ok else "应为非负整数"


def _bool(value: object) -> str | None:
    return None if isinstance(value, bool) else "应为 true / false"


def _expose_cells(definition: dict, data: dict) -> Exposed:
    values = definition.get("values")
    n = len(values) if isinstance(values, list) else 0
    return Exposed(parts={"value": n}, items=n)


def _validate_cells(ctx: WidgetContext, report: Report, path: str) -> None:
    values, labels = ctx.definition.get("values"), ctx.definition.get("labels")
    if isinstance(values, list) and isinstance(labels, list) and len(values) != len(labels):
        report.error("SS250", f"{path}.labels", f"labels 有 {len(labels)} 项，values 有 {len(values)} 项")
    known = ctx.definition.get("known")
    if isinstance(known, int) and isinstance(values, list) and known > len(values):
        report.error("SS250", f"{path}.known", f"known={known} 超过了 values 的个数 {len(values)}")


def _cells_fill(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    rng = selectors.parse_slice(args.get("index"))
    n = ctx.exposed.parts.get("value", 0)
    if rng is None:
        report.error("SS233", f"{path}.args.index", "index 应为非负整数或 \"i:j\"")
    elif rng[1] > n:
        report.error("SS234", f"{path}.args.index", f"只有 {n} 格，下标越界")


# ---------- 步骤胶囊、总结卡 ----------

def _chips_reveal(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    """reveal {index?}：露出若干胶囊（只在 reveal: true 的胶囊上有意义；默认全部）。"""
    if not ctx.definition.get("reveal"):
        report.warning("SS235", f"{path}", "chips 没有写 reveal: true，胶囊本来就都在，reveal 动作没有效果")
    if "index" not in args:
        return
    rng = selectors.parse_slice(args.get("index"))
    n = ctx.exposed.items or 0
    if rng is None:
        report.error("SS233", f"{path}.args.index", "index 应为非负整数或 \"i:j\"")
    elif rng[1] > n:
        report.error("SS234", f"{path}.args.index", f"只有 {n} 个胶囊，下标越界")


def _expose_items(key: str) -> Callable[[dict, dict], Exposed]:
    def expose(definition: dict, data: dict) -> Exposed:
        value = definition.get(key)
        return Exposed(items=len(value) if isinstance(value, list) else None)

    return expose


def _summary_rows(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return "应为非空列表"
    for row in value:
        if not (isinstance(row, dict) and isinstance(row.get("tag"), str) and isinstance(row.get("text"), str)):
            return "每行应为 {tag, text, role?}"
        if "role" in row and row["role"] not in ROLES:
            return f"role 应为 {'/'.join(sorted(ROLES))} 之一"
    return None


# ---------- 数例表 seq_table：几行带行头的格子，一列列露（kit 的 mx/table.py） ----------

def _table_rows(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return "应为非空列表"
    for row in value:
        if not (isinstance(row, dict) and isinstance(row.get("label"), str) and isinstance(row.get("values"), list)):
            return "每行应为 {label, values, role?}"
        if _list_of_literals(row["values"]):
            return "values 应为非空列表，每项是数或 LaTeX 字符串"
        if "role" in row and row["role"] not in ROLES:
            return f"role 应为 {'/'.join(sorted(ROLES))} 之一"
    return None


def _expose_table(definition: dict, data: dict) -> Exposed:
    rows = definition.get("rows")
    if not isinstance(rows, list):
        return Exposed()
    n = max((len(r.get("values", [])) for r in rows if isinstance(r, dict)), default=0)
    return Exposed(parts={"row": len(rows), "head": len(rows)}, items=n)


def _validate_table(ctx: WidgetContext, report: Report, path: str) -> None:
    rows = ctx.definition.get("rows")
    if not isinstance(rows, list):
        return
    lengths = {len(r["values"]) for r in rows if isinstance(r, dict) and isinstance(r.get("values"), list)}
    if len(lengths) > 1:
        report.error("SS250", f"{path}.rows", f"各行的 values 长度不一样（{sorted(lengths)}）")
    known = ctx.definition.get("known")
    if isinstance(known, int) and lengths and known > max(lengths):
        report.error("SS250", f"{path}.known", f"known={known} 超过了列数 {max(lengths)}")


def _table_shade(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    rows, cols = ctx.exposed.parts.get("row", 0), ctx.exposed.items or 0
    for key, n in (("row", rows), ("col", cols)):
        v = args.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            report.error("SS233", f"{path}.args.{key}", f"{key} 应为非负整数")
        elif v >= n:
            report.error("SS234", f"{path}.args.{key}", f"{key}={v} 越界（只有 {n} 个）")
    if "role" in args and args["role"] not in ROLES:
        report.error("SS233", f"{path}.args.role", f"role 应为 {'/'.join(sorted(ROLES))} 之一")


# ---------- 折线图 line_chart：几个量随项数的升降（kit 的 mx/chart.py） ----------

def _chart_series(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return "应为非空列表"
    for s in value:
        if not (isinstance(s, dict) and isinstance(s.get("values"), list)):
            return "每条线应为 {name?, values, role?}"
        if _list_of_literals(s["values"]):
            return "values 应为非空列表，每项是数"
        if "role" in s and s["role"] not in ROLES:
            return f"role 应为 {'/'.join(sorted(ROLES))} 之一"
    return None


def _expose_chart(definition: dict, data: dict) -> Exposed:
    series = definition.get("series")
    return Exposed(parts={"axes": 1, "series": len(series) if isinstance(series, list) else 0})


def _validate_chart(ctx: WidgetContext, report: Report, path: str) -> None:
    x, series = ctx.definition.get("x"), ctx.definition.get("series")
    if not (isinstance(x, list) and isinstance(series, list)):
        return
    for k, s in enumerate(series):
        if isinstance(s, dict) and isinstance(s.get("values"), list) and len(s["values"]) != len(x):
            report.error("SS250", f"{path}.series[{k}]", f"values 有 {len(s['values'])} 项，x 有 {len(x)} 项")


def _chart_ring(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    n_series = ctx.exposed.parts.get("series", 0)
    x = ctx.definition.get("x")
    n_x = len(x) if isinstance(x, list) else 0
    for key, n in (("series", n_series), ("index", n_x)):
        v = args.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            report.error("SS233", f"{path}.args.{key}", f"{key} 应为非负整数")
        elif v >= n:
            report.error("SS234", f"{path}.args.{key}", f"{key}={v} 越界（只有 {n} 个）")


# ---------- 差分表 ----------

def _diff_rows(value: object) -> str | None:
    if not isinstance(value, list) or len(value) < 2:
        return "应至少有两行"
    for row in value:
        if not isinstance(row, dict) or not isinstance(row.get("data"), str):
            return "每行应为 {data, role, label?, name?}，data 指向 data 段里的数列"
        if row.get("role") not in ROLES:
            return f"每行的 role 应为 {'/'.join(sorted(ROLES))} 之一"
        extra = set(row) - {"data", "role", "label", "name"}
        if extra:
            return f"不认识的字段 {sorted(extra)}"
    return None


def _expose_diff(definition: dict, data: dict) -> Exposed:
    exposed = Exposed()
    for row in definition.get("rows") or []:
        if isinstance(row, dict) and isinstance(row.get("data"), str):
            values = data.get(row["data"])
            if isinstance(values, _curves.Unavailable):  # {src} 读不出来 / 没给场景目录：长度未知，下标不查
                exposed.parts[row["data"]] = sys.maxsize
                continue
            exposed.parts[row["data"]] = len(values) if isinstance(values, list) else 0
    return exposed


def _validate_diff(ctx: WidgetContext, report: Report, path: str) -> None:
    rows = [r for r in ctx.definition.get("rows") or [] if isinstance(r, dict)]
    series: list[list] = []
    for n, row in enumerate(rows):
        name = row.get("data")
        values = ctx.data.get(name)
        if values is None:
            report.error("SS220", f"{path}.rows[{n}].data", f"data 段里没有 {name!r}")
            return
        if isinstance(values, _curves.Unavailable):
            return  # {src} 读不出来（已经报过），或没给场景目录、查不了
        if not isinstance(values, list) or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
            report.error("SS221", f"{path}.rows[{n}].data", f"{name!r} 应为数字列表")
            return
        series.append(values)
    for n in range(1, len(series)):
        upper, lower = series[n - 1], series[n]
        expected = [b - a for a, b in zip(upper, upper[1:])]
        if len(lower) > len(expected):
            report.error("SS222", f"{path}.rows[{n}]", f"第 {n + 1} 行比上一行的差多出 {len(lower) - len(expected)} 个数")
        for i, (got, want) in enumerate(zip(lower, expected)):
            if got != want:
                report.error(
                    "SS223", f"{path}.rows[{n}]",
                    f"{rows[n]['data']}[{i}] = {got}，但上一行相邻两项之差是 {want}",
                )
                break
    known = ctx.definition.get("known")
    if isinstance(known, list):
        if len(known) != len(rows):
            report.error("SS224", f"{path}.known", f"known 有 {len(known)} 项，rows 有 {len(rows)} 行")
        for n, (k, values) in enumerate(zip(known, series)):
            if isinstance(k, int) and k > len(values):
                report.error("SS224", f"{path}.known[{n}]", f"一开始显示 {k} 个数，但这一行只有 {len(values)} 个")


def _diff_derive(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    row, index = args.get("row"), args.get("index")
    if row not in ctx.exposed.parts:
        report.error("SS231", f"{path}.args.row", f"差分表 {ctx.obj_id} 没有名为 {row!r} 的行（有 {sorted(ctx.exposed.parts)}）")
        return
    names = list(ctx.exposed.parts)
    if names.index(row) == 0:
        report.error("SS232", f"{path}.args.row", f"第一行 {row!r} 是原数列，不能由做差得到，请用 extend")
    rng = selectors.parse_slice(index)
    if rng is None:
        report.error("SS233", f"{path}.args.index", "index 应为非负整数或 \"i:j\"")
    elif rng[1] > ctx.exposed.parts[row]:
        report.error("SS234", f"{path}.args.index", f"{row} 只有 {ctx.exposed.parts[row]} 个数，下标越界")


def _diff_extend(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    row, index = args.get("row"), args.get("index")
    if row not in ctx.exposed.parts:
        report.error("SS231", f"{path}.args.row", f"差分表 {ctx.obj_id} 没有名为 {row!r} 的行（有 {sorted(ctx.exposed.parts)}）")
        return
    rng = selectors.parse_slice(index)
    if rng is None:
        report.error("SS233", f"{path}.args.index", "index 应为非负整数或 \"i:j\"")
    elif rng[1] > ctx.exposed.parts[row]:
        report.error("SS234", f"{path}.args.index", f"{row} 只有 {ctx.exposed.parts[row]} 个数，下标越界")


def _diff_triangle(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    _diff_extend(args, ctx, report, path)


# ---------- 面积模型 ----------

AREA_LAYOUTS = ("four_around_c", "two_rectangles")


def _legs(value: object) -> str | None:
    ok = (isinstance(value, list) and len(value) == 2
          and all(isinstance(v, (int, float, str)) and not isinstance(v, bool) for v in value))
    if not ok:
        return "应为两个元素的列表：两条直角边的长度（right_triangles 要求正数，用来画图）"
    return None


def _angle(value: object) -> str | None:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < 180
    return None if ok else "应为 0 到 180 之间的角度（度）"


def _area_count(definition: dict) -> int | None:
    count = definition.get("count")
    if count is None and definition.get("kind") == "right_triangles":
        return 4
    return count if isinstance(count, int) and not isinstance(count, bool) else None


def _expose_area(definition: dict, data: dict) -> Exposed:
    count = _area_count(definition)
    exposed = Exposed(items=count)
    if definition.get("kind") == "right_triangles" and count is not None:
        # tri：每个三角形；hole / area：空白区域 [c², a², b²] 及其名字（只有四个三角形的拼图才有）；side：边长标注 [a, b, c]
        holes = 3 if count == 4 else 0
        exposed.parts = {"tri": count, "hole": holes, "area": holes, "side": 3}
    return exposed


def _validate_area(ctx: WidgetContext, report: Report, path: str) -> None:
    d = ctx.definition
    if d.get("kind") != "right_triangles":
        return
    legs = d.get("legs")
    if legs is None:
        report.error("SS243", path, "right_triangles 需要 legs：两条直角边的长度，例如 [2, 3]")
    elif isinstance(legs, list) and not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in legs):
        report.error("SS243", f"{path}.legs", "right_triangles 的 legs 要写成正数（按比例画图），例如 [2, 3]")
    count = _area_count(d)
    if count not in (1, 4):
        report.error("SS243", f"{path}.count", "right_triangles 只支持 count: 1（单个三角形）或 4（拼大正方形）")


def _area_slide(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    layout = args.get("layout")
    if not isinstance(layout, str):
        report.error("SS241", f"{path}.args.layout", "slide 需要 layout（目标摆法的名字）")
    elif ctx.definition.get("kind") == "right_triangles":
        if layout not in AREA_LAYOUTS:
            report.error("SS241", f"{path}.args.layout", f"right_triangles 的摆法只有 {' / '.join(AREA_LAYOUTS)}")
        if _area_count(ctx.definition) != 4:
            report.error("SS244", path, "只有四个三角形的拼图才能 slide")


def _area_bend(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    problem = _angle(args.get("angle"))
    if problem:
        report.error("SS245", f"{path}.args.angle", f"bend 需要 angle：{problem}")
    if ctx.definition.get("kind") != "right_triangles" or _area_count(ctx.definition) != 4:
        report.error("SS244", path, "bend 只用于四个三角形的拼图（kind: right_triangles）")


def _area_cut(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if args.get("direction") not in ("vertical", "horizontal"):
        report.error("SS242", f"{path}.args.direction", "cut 需要 direction: vertical / horizontal")


REGISTRY: dict[str, Widget] = {
    "problem_card": Widget(
        "problem_card",
        params={"lines": (True, _str_list), "answers": (False, _answers)},
        expose=_expose_card,
        validate=_validate_card,
    ),
    "equations": Widget(
        "equations",
        params={"rows": (True, _eq_rows)},
        expose=_expose_items("rows"),
    ),
    "seq_cells": Widget(
        "seq_cells",
        params={"values": (True, _list_of_literals), "labels": (True, _list_of_literals),
                "known": (False, _nonneg_int), "dots": (False, _bool)},
        expose=_expose_cells,
        actions={"fill": _cells_fill},
        validate=_validate_cells,
    ),
    "think_box": Widget(
        "think_box",
        params={"lines": (True, _str_list)},
        expose=_expose_lines,
        validate=_validate_lines,
    ),
    "chips": Widget(
        "chips",
        params={"items": (True, _str_list), "reveal": (False, _bool)},
        expose=_expose_items("items"),
        actions={"reveal": _chips_reveal},
    ),
    "summary": Widget(
        "summary",
        params={"rows": (True, _summary_rows)},
        expose=_expose_items("rows"),
    ),
    "seq_table": Widget(
        "seq_table",
        params={"rows": (True, _table_rows), "known": (False, _nonneg_int), "size": (False, _positive_number)},
        expose=_expose_table,
        actions={"shade": _table_shade, "unshade": _table_shade},
        validate=_validate_table,
    ),
    "line_chart": Widget(
        "line_chart",
        params={"x": (True, _list_of_literals), "series": (True, _chart_series), "ymax": (False, _positive_number),
                "yticks": (False, _list_of_literals), "x_label": (False, _str), "y_label": (False, _str),
                "width": (False, _positive_number), "height": (False, _positive_number)},
        expose=_expose_chart,
        actions={"ring": _chart_ring},
        validate=_validate_chart,
    ),
    "diff_table": Widget(
        "diff_table",
        params={"rows": (True, _diff_rows), "known": (False, _int_list)},
        expose=_expose_diff,
        actions={"derive": _diff_derive, "extend": _diff_extend, "triangle": _diff_triangle},
        validate=_validate_diff,
    ),
    "area_model": Widget(
        "area_model",
        params={
            "kind": (True, _enum("square", "rectangle", "right_triangles", "strip")),
            "side": (False, _number_or_str),
            "legs": (False, _legs),
            "count": (False, _positive_int),
            "layout": (False, _enum(*AREA_LAYOUTS)),
            "angle": (False, _angle),
            "pieces": (False, _enum("shown", "hidden")),
        },
        expose=_expose_area,
        actions={"slide": _area_slide, "bend": _area_bend, "cut": _area_cut},
        validate=_validate_area,
    ),
}


# ---------- 数轴（分数除法：里面有几个）----------
# 自成一节，登记在下面一行；跳几次、剩多少按 fractions.Fraction 精确算，和 kit 的 mx/numberline.py 一致。

NUMBER_LINE_POINTS = 8  # mark_point 最多点几个（erase 后重新计数）


def _nl_frac(value: object):
    """整数或 "p/q" 字符串 → Fraction；小数、布尔和写错的返回 None。"""
    from fractions import Fraction

    if isinstance(value, bool) or isinstance(value, float):
        return None
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value.replace(" ", ""))
        except (ValueError, ZeroDivisionError):
            return None
    return None


def _nl_range(value: object) -> str | None:
    ok = (isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
          and value[1] > value[0])
    return None if ok else "应为两个整数 [起点, 终点]，终点更大"


def _nl_measures(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return "应为非空列表：要拿来量的长度（整数或 \"2/3\" 这样的分数字符串）"
    for v in value:
        f = _nl_frac(v)
        if f is None or f <= 0:
            return f"{v!r} 不是正的整数或分数字符串（不要写小数）"
    return None


def _nl_bounds(definition: dict) -> tuple[int, int] | None:
    r = definition.get("range")
    return (r[0], r[1]) if _nl_range(r) is None else None


def _nl_max_jumps(definition: dict) -> int:
    import math

    bounds = _nl_bounds(definition)
    measures = definition.get("measures")
    if bounds is None or _nl_measures(measures) is not None:
        return 0
    return max(math.floor((bounds[1] - bounds[0]) / _nl_frac(m)) for m in measures)


def _expose_number_line(definition: dict, data: dict) -> Exposed:
    bounds = _nl_bounds(definition)
    n = bounds[1] - bounds[0] if bounds else 0
    slots = _nl_max_jumps(definition)
    # tick / label：整数刻度和数字；unit：每个单位一格；frac：第一格的分数标注；span：高亮段；
    # jump / count：跳跃弧和计数（按 measures 里最多的整跳数预留）；rest：剩余段；point：点
    return Exposed(parts={"tick": n + 1, "label": n + 1, "unit": n, "frac": 1, "span": 1,
                          "jump": slots, "count": slots, "rest": 1, "point": NUMBER_LINE_POINTS,
                          "strip": 1, "groups": 1, "arrows": 1, "turns": 1},
                   state={"arrow": None})


def _nl_value(args: dict, key: str, report: Report, path: str, ctx: WidgetContext, required: bool = True):
    if key not in args:
        if required:
            report.error("SS281", f"{path}.args", f"缺少参数 {key}")
        return None
    f = _nl_frac(args[key])
    if f is None:
        report.error("SS281", f"{path}.args.{key}", "应为整数或分数字符串（例如 \"2/3\"），不要写小数")
        return None
    bounds = _nl_bounds(ctx.definition)
    if bounds and not bounds[0] <= f <= bounds[1]:
        report.error("SS282", f"{path}.args.{key}", f"{args[key]} 不在数轴 {list(bounds)} 上")
    return f


def _nl_role(args: dict, report: Report, path: str) -> None:
    if "role" in args and args["role"] not in ROLES:
        report.error("SS281", f"{path}.args.role", f"role 应为 {'/'.join(sorted(ROLES))} 之一")


def _nl_flag(args: dict, key: str, report: Report, path: str) -> None:
    if key in args and not isinstance(args[key], bool):
        report.error("SS281", f"{path}.args.{key}", f"{key} 应为 true / false")


def _nl_jump(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    import math

    length = _nl_frac(args.get("length"))
    if length is None or length <= 0:
        report.error("SS283", f"{path}.args.length", "jump 需要 length：正的整数或分数字符串，例如 \"2/3\"")
        return
    measures = [_nl_frac(m) for m in ctx.definition.get("measures") or []]
    if length not in measures:
        report.error("SS284", f"{path}.args.length",
                     f"{args['length']} 不在 measures 里；把它加进 {ctx.obj_id}.measures，跳跃弧的引用才能按它预留")
    count = args.get("count")
    bounds = _nl_bounds(ctx.definition)
    origin = _nl_value(args, "from", report, path, ctx, required=False) if "from" in args else None
    if origin is None and bounds:
        origin = bounds[0]
    if count is not None:
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            report.error("SS283", f"{path}.args.count", "count 应为正整数（不写就跳到放不下为止）")
        elif bounds and count > math.floor((bounds[1] - origin) / length):
            report.error("SS285", f"{path}.args.count", f"长度 {args['length']} 从 {origin} 到 {bounds[1]} 最多跳 "
                         f"{math.floor((bounds[1] - origin) / length)} 次")
    _nl_role(args, report, path)
    _nl_flag(args, "keep", report, path)
    _nl_flag(args, "numbers", report, path)
    for key in sorted(set(args) - {"length", "count", "from", "keep", "role", "numbers"}):
        report.error("SS281", f"{path}.args.{key}", f"jump 没有参数 {key}（可用：length、count、from、keep、role、numbers）")


def _nl_subdivide(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    problem = _positive_int(args.get("parts"))
    if problem:
        report.error("SS286", f"{path}.args.parts", f"subdivide 需要 parts（每个单位分成几份）：{problem}")


def _nl_highlight(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    a = _nl_value(args, "from", report, path, ctx, required=False)
    b = _nl_value(args, "to", report, path, ctx)
    if a is not None and b is not None and b <= a:
        report.error("SS282", f"{path}.args", "highlight 的 to 要大于 from")
    _nl_role(args, report, path)
    _nl_flag(args, "keep", report, path)


def _nl_mark_point(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    _nl_value(args, "at", report, path, ctx)
    if "label" in args and _str(args["label"]):
        report.error("SS281", f"{path}.args.label", "label 应为非空的 LaTeX 字符串")
    _nl_role(args, report, path)


def _nl_needs_bars(ctx: WidgetContext, report: Report, path: str) -> None:
    if ctx.definition.get("bars") is not True:
        report.error("SS287", path, f"分数条动作要先在 {ctx.obj_id} 上写 bars: true（预留位置）")


def _nl_bar(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    _nl_needs_bars(ctx, report, path)
    problem = _positive_int(args.get("parts"))
    if problem:
        report.error("SS286", f"{path}.args.parts", f"bar 需要 parts（每个单位几格）：{problem}")


def _nl_fill(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    _nl_needs_bars(ctx, report, path)
    if selectors.parse_slice(args.get("cells")) is None:
        report.error("SS281", f"{path}.args.cells", "cells 应为非负整数或 \"a:b\"（从 0 数的格子）")
    _nl_role(args, report, path)


def _nl_group(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    _nl_needs_bars(ctx, report, path)
    problem = _positive_int(args.get("size"))
    if problem:
        report.error("SS286", f"{path}.args.size", f"group 需要 size（几格一组）：{problem}")


def _nl_no_args(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    for key in sorted(args):
        report.error("SS281", f"{path}.args.{key}", f"这个动作不带参数（多了 {key}）")


def _nl_needs_arrows(ctx: WidgetContext, report: Report, path: str) -> None:
    if ctx.definition.get("arrows") is not True:
        report.error("SS287", path, f"箭头动作要先在 {ctx.obj_id} 上写 arrows: true（给转半圈预留位置）")


def _nl_arrow(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    """arrow：从 0 指到 to 的箭头；keep 时上一支留一个淡影。"""
    _nl_needs_arrows(ctx, report, path)
    v = _nl_value(args, "to", report, path, ctx)
    if v == 0:
        report.error("SS282", f"{path}.args.to", "箭头要指到一个不是 0 的数")
    _nl_role(args, report, path)
    _nl_flag(args, "keep", report, path)
    _unknown_args(args, {"to", "role", "keep"}, "arrow", report, path)
    ctx.exposed.state["arrow"] = v if v else None


def _nl_stretch(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    """stretch：现在这支箭头拉长或缩短到 to（方向不变）。"""
    state = ctx.exposed.state
    v = _nl_value(args, "to", report, path, ctx)
    _unknown_args(args, {"to"}, "stretch", report, path)
    if state.get("arrow") is None:
        report.error("SS261", path, "还没有箭头：先用 arrow 画一支")
    elif v is not None:
        if v == 0 or (v > 0) != (state["arrow"] > 0):
            report.error("SS282", f"{path}.args.to", f"stretch 不改方向（现在指向 {state['arrow']}）；掉头用 turn")
        else:
            state["arrow"] = v


def _nl_turn(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    """turn：现在这支箭头绕 0 转半圈（乘 −1），从轴的上方扫过；label 写在半圆顶上。"""
    state = ctx.exposed.state
    if "label" in args and _str(args["label"]):
        report.error("SS281", f"{path}.args.label", "label 应为非空的 LaTeX 字符串")
    _unknown_args(args, {"label"}, "turn", report, path)
    v = state.get("arrow")
    if v is None:
        report.error("SS261", path, "还没有箭头：先用 arrow 画一支")
        return
    bounds = _nl_bounds(ctx.definition)
    if bounds and not bounds[0] <= -v <= bounds[1]:
        report.error("SS282", path, f"转过去指向 {-v}，不在数轴 {list(bounds)} 上")
    state["arrow"] = -v


def _nl_erase(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    _nl_no_args(args, ctx, report, path)
    ctx.exposed.state["arrow"] = None


REGISTRY["number_line"] = Widget(
    "number_line",
    params={
        "range": (True, _nl_range),
        "parts": (False, _positive_int),
        "measures": (False, _nl_measures),
        "fractions": (False, _bool),
        "unit": (False, _positive_number),
        "bars": (False, _bool),
        "arrows": (False, _bool),
    },
    expose=_expose_number_line,
    actions={"jump": _nl_jump, "remainder": _nl_no_args, "subdivide": _nl_subdivide, "highlight": _nl_highlight,
             "mark_point": _nl_mark_point, "erase": _nl_erase, "bar": _nl_bar, "fill": _nl_fill, "group": _nl_group,
             "arrow": _nl_arrow, "stretch": _nl_stretch, "turn": _nl_turn},
)

# ---------- 格子正方形（area_grid）：分数乘法的交叠格；rect 模式切长方形 ----------
# kit 的 mx/grid.py：cols × rows 格；cut 画切线，shade 涂列或行，overlap 标出交叠格。
# rect: true 时每格是小方格，整块是 cols × rows 的长方形：split 切段、apart / join 分开拼回、fill 涂块写格数、unfill 收起。
# 动作按顺序推演 split 的段数（exposed.state），fill 的 col / row 不能超出段数。

GRID_FRACTION_ACTS = {"cut", "shade", "overlap"}
GRID_RECT_ACTS = {"split", "apart", "join", "fill", "unfill"}


def _expose_area_grid(definition: dict, data: dict) -> Exposed:
    cols, rows = definition.get("cols"), definition.get("rows")
    n = cols * rows if isinstance(cols, int) and isinstance(rows, int) else 0
    if definition.get("rect") is True:
        return Exposed(parts={"cell": n, "cut": 1, "areas": 1}, state={"cols": [cols], "rows": [rows], "apart": False})
    return Exposed(parts={"cols": 1, "rows": 1, "overlap": 1, "cell": n})


def _grid_mode(act: str, ctx: WidgetContext, report: Report, path: str) -> bool:
    """动作和模式对得上返回 True；rect 模式只有切块的动作，正方形模式只有分数乘法的动作。"""
    rect = ctx.definition.get("rect") is True
    if rect and act in GRID_FRACTION_ACTS:
        report.error("SS264", f"{path}.act", f"{ctx.obj_id} 是 rect 模式，没有 {act}（可用：{'、'.join(sorted(GRID_RECT_ACTS))}）")
        return False
    if not rect and act in GRID_RECT_ACTS:
        report.error("SS264", f"{path}.act", f"{act} 只在 rect 模式下有：先在 {ctx.obj_id} 上写 rect: true")
        return False
    return True


def _grid_cut(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if not _grid_mode("cut", ctx, report, path):
        return
    if args.get("axis") not in ("cols", "rows"):
        report.error("SS281", f"{path}.args.axis", "cut 需要 axis: cols 或 rows")
    for key in sorted(set(args) - {"axis"}):
        report.error("SS281", f"{path}.args.{key}", f"cut 没有参数 {key}")


def _grid_shade(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if not _grid_mode("shade", ctx, report, path):
        return
    keys = {"cols", "rows"} & set(args)
    if len(keys) != 1:
        report.error("SS281", f"{path}.args", "shade 要写 cols 或 rows 其中一个（涂几列 / 几行）")
        return
    key = keys.pop()
    limit = ctx.definition.get(key)
    v = args[key]
    if _positive_int(v) or (isinstance(limit, int) and v > limit):
        report.error("SS281", f"{path}.args.{key}", f"应为 1 到 {limit} 的整数")
    _role_arg(args, report, path)
    for k in sorted(set(args) - {"cols", "rows", "role"}):
        report.error("SS281", f"{path}.args.{k}", f"shade 没有参数 {k}")


def _grid_overlap(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if _grid_mode("overlap", ctx, report, path):
        _no_args(args, ctx, report, path)


def _grid_split(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if not _grid_mode("split", ctx, report, path):
        return
    keys = {"cols", "rows"} & set(args)
    if not keys:
        report.error("SS281", f"{path}.args", "split 要写 cols 和 / 或 rows：各段的长度，例如 cols: [20, 3]")
    state = ctx.exposed.state
    if state.get("apart"):
        report.error("SS265", path, "块还分开着：先 join 拼回去再重新切")
    for key in sorted(keys):
        total = ctx.definition.get(key)
        pieces = args[key]
        if not isinstance(pieces, list) or not pieces or any(_positive_int(n) for n in pieces):
            report.error("SS281", f"{path}.args.{key}", "应为正整数列表（各段的长度）")
            continue
        if isinstance(total, int) and sum(pieces) != total:
            report.error("SS263", f"{path}.args.{key}", f"各段加起来是 {sum(pieces)}，{ctx.obj_id}.{key} 是 {total}")
            continue
        state[key] = pieces
    for k in sorted(set(args) - {"cols", "rows"}):
        report.error("SS281", f"{path}.args.{k}", f"split 没有参数 {k}")


def _grid_apart(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if not _grid_mode("apart", ctx, report, path):
        return
    state = ctx.exposed.state
    if len(state.get("cols", [])) * len(state.get("rows", [])) < 2:
        report.error("SS265", path, "还没切开（先 split），分不开")
    if "gap" in args and _positive_number(args["gap"]):
        report.error("SS281", f"{path}.args.gap", "gap 应为正数（画面单位，默认 0.35）")
    for k in sorted(set(args) - {"gap"}):
        report.error("SS281", f"{path}.args.{k}", f"apart 没有参数 {k}")
    state["apart"] = True


def _grid_join(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if not _grid_mode("join", ctx, report, path):
        return
    _no_args(args, ctx, report, path)
    ctx.exposed.state["apart"] = False


def _grid_fill(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if not _grid_mode("fill", ctx, report, path):
        return
    state = ctx.exposed.state
    if "cells" in args:
        sl = selectors.parse_slice(args["cells"])
        n = ctx.exposed.parts.get("cell", 0)
        if sl is None or sl[1] > n:
            report.error("SS281", f"{path}.args.cells", f"cells 应为 0 到 {n} 之间的 \"a:b\"（按行从左往右数的格子）")
        if {"col", "row"} & set(args):
            report.error("SS281", f"{path}.args", "cells 和 col / row 只写一种")
        if isinstance(args.get("label"), (bool, str)) and args.get("label"):
            report.error("SS281", f"{path}.args.label", "label 只给整块用（col / row），cells 涂的散格子不写数")
    for key, axis in (("col", "cols"), ("row", "rows")):
        if key in args:
            n = len(state.get(axis, [None]))
            v = args[key]
            if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < n:
                report.error("SS265", f"{path}.args.{key}", f"{key} 应为 0 到 {n - 1} 的整数（现在切成 {n} 段）")
    if "label" in args and not (isinstance(args["label"], bool) or (isinstance(args["label"], str) and args["label"])):
        report.error("SS281", f"{path}.args.label", "label 应为 true（写格数）或 LaTeX 字符串")
    _role_arg(args, report, path)
    for k in sorted(set(args) - {"cells", "col", "row", "role", "label"}):
        report.error("SS281", f"{path}.args.{k}", f"fill 没有参数 {k}")


def _grid_unfill(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if _grid_mode("unfill", ctx, report, path):
        _no_args(args, ctx, report, path)


def _role_arg(args: dict, report: Report, path: str, key: str = "role") -> None:
    if key in args and args[key] not in ROLES:
        report.error("SS281", f"{path}.args.{key}", f"{key} 应为 {'/'.join(sorted(ROLES))} 之一")


def _no_args(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    for key in sorted(args):
        report.error("SS281", f"{path}.args.{key}", f"这个动作不带参数（多了 {key}）")


def _count_arg(args: dict, report: Report, path: str, act: str) -> int | None:
    """动作的 count：必填的正整数（点的个数要是精确的整数，不收小数、布尔、表达式）。"""
    v = args.get("count")
    if _positive_int(v):
        report.error("SS281", f"{path}.args.count", f"{act} 需要 count：正整数（几个点）")
        return None
    return v


def _unknown_args(args: dict, allowed: set[str], act: str, report: Report, path: str) -> None:
    for k in sorted(set(args) - allowed):
        report.error("SS281", f"{path}.args.{k}", f"{act} 没有参数 {k}（可用：{'、'.join(sorted(allowed)) or '无'}）")


REGISTRY["area_grid"] = Widget(
    "area_grid",
    params={"cols": (True, _positive_int), "rows": (True, _positive_int), "rect": (False, _bool), "lines": (False, _bool)},
    expose=_expose_area_grid,
    actions={"cut": _grid_cut, "shade": _grid_shade, "overlap": _grid_overlap, "split": _grid_split,
             "apart": _grid_apart, "join": _grid_join, "fill": _grid_fill, "unfill": _grid_unfill},
)

# ---------- 十格框（ten_frame）：凑十 ----------
# kit 的 mx/dots.py：两排五格的框，框旁边一堆点。按动作顺序推演框里、框旁边各有几个点：
# 框里最多 10 个，旁边不超过参数 side（排版预留的地方），move_in 不能比旁边现有的点多、也不能比框里的空格多。

TEN_FRAME_GROUPS = ("side", "frame", "all")


def _expose_ten_frame(definition: dict, data: dict) -> Exposed:
    return Exposed(parts={"frame": 1, "cell": 10, "dots": 1}, state={"frame": 0, "side": 0})


def _tf_which(args: dict, report: Report, path: str, default: str, choices=TEN_FRAME_GROUPS) -> str:
    which = args.get("which", default)
    if which not in choices:
        report.error("SS281", f"{path}.args.which", f"which 应为 {' / '.join(choices)} 之一")
        return default
    return which


def _tf_fill(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    n = _count_arg(args, report, path, "fill")
    state = ctx.exposed.state
    if n is not None:
        if state["frame"] + n > 10:
            report.error("SS261", f"{path}.args.count", f"框里已经有 {state['frame']} 个点，只剩 {10 - state['frame']} 个空格")
            n = 10 - state["frame"]
        state["frame"] += n
    _role_arg(args, report, path)
    _unknown_args(args, {"count", "role"}, "fill", report, path)


def _tf_side(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    n = _count_arg(args, report, path, "side")
    state = ctx.exposed.state
    room = ctx.definition.get("side", 0)
    if n is not None:
        if isinstance(room, int) and state["side"] + n > room:
            report.error("SS261", f"{path}.args.count", f"框旁边要放 {state['side'] + n} 个点，{ctx.obj_id}.side 只预留了 "
                         f"{room} 个；把 side 写大一些")
        state["side"] += n
    _role_arg(args, report, path)
    _unknown_args(args, {"count", "role"}, "side", report, path)


def _tf_move_in(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    n = _count_arg(args, report, path, "move_in")
    state = ctx.exposed.state
    if n is not None:
        if n > state["side"]:
            report.error("SS261", f"{path}.args.count", f"框旁边只有 {state['side']} 个点")
        elif state["frame"] + n > 10:
            report.error("SS261", f"{path}.args.count", f"框里只剩 {10 - state['frame']} 个空格")
        else:
            state["side"] -= n
            state["frame"] += n
    _unknown_args(args, {"count"}, "move_in", report, path)


def _tf_count(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    which = _tf_which(args, report, path, "side", ("side", "frame"))
    if ctx.exposed.state[which] == 0:
        report.error("SS261", path, f"{which} 那边还没有点，没东西可数")
    if "start" in args and _nonneg_int(args["start"]):
        report.error("SS281", f"{path}.args.start", "start 应为非负整数（第一个点标几）")
    _unknown_args(args, {"which", "start"}, "count", report, path)


def _tf_recolor(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    _tf_which(args, report, path, "all")
    if "role" not in args:
        report.error("SS281", f"{path}.args", "recolor 需要 role")
    _role_arg(args, report, path)
    _unknown_args(args, {"which", "role"}, "recolor", report, path)


def _tf_remove(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    which = _tf_which(args, report, path, "all")
    state = ctx.exposed.state
    for k in ("side", "frame"):
        if which in (k, "all"):
            state[k] = 0
    _unknown_args(args, {"which"}, "remove", report, path)


REGISTRY["ten_frame"] = Widget(
    "ten_frame",
    params={"side": (False, _nonneg_int)},
    expose=_expose_ten_frame,
    actions={"fill": _tf_fill, "side": _tf_side, "move_in": _tf_move_in, "count": _tf_count,
             "recolor": _tf_recolor, "remove": _tf_remove},
)

# ---------- 点阵（dot_array）：转 90°、补满、淡出一列、点变方格 ----------
# kit 的 mx/dots.py：rows × cols 的点，中心不动。按动作顺序推演现在几排几列：rotate 交换排和列，extend 只能变多；
# 每个状态都要放得进 room（排版预留的 [排, 列]，默认 max(rows, cols) 的正方形）。


def _room(value: object) -> str | None:
    ok = isinstance(value, list) and len(value) == 2 and not any(_positive_int(v) for v in value)
    return None if ok else "应为两个正整数 [排, 列]：排版时给点阵预留多大"


def _da_room(definition: dict) -> tuple[int, int] | None:
    rows, cols = definition.get("rows"), definition.get("cols")
    if _room(definition.get("room")) is None:
        return tuple(definition["room"])
    if isinstance(rows, int) and isinstance(cols, int):
        return max(rows, cols), max(rows, cols)
    return None


def _expose_dot_array(definition: dict, data: dict) -> Exposed:
    return Exposed(parts={"dots": 1, "cells": 1},
                   state={"rows": definition.get("rows"), "cols": definition.get("cols")})


def _validate_dot_array(ctx: WidgetContext, report: Report, path: str) -> None:
    room = _da_room(ctx.definition)
    rows, cols = ctx.definition.get("rows"), ctx.definition.get("cols")
    if room and isinstance(rows, int) and isinstance(cols, int) and (rows > room[0] or cols > room[1]):
        report.error("SS262", f"{path}.room", f"{rows} × {cols} 的点阵放不进 room {list(room)}")


def _da_fits(ctx: WidgetContext, report: Report, path: str) -> None:
    room, state = _da_room(ctx.definition), ctx.exposed.state
    if room and isinstance(state["rows"], int) and isinstance(state["cols"], int) and (state["rows"] > room[0] or state["cols"] > room[1]):
        report.error("SS262", path, f"这一步之后是 {state['rows']} 排 × {state['cols']} 列，放不进 room {list(room)}；"
                     f"在 {ctx.obj_id} 上写 room: [{max(room[0], state['rows'])}, {max(room[1], state['cols'])}]")


def _da_ready(ctx: WidgetContext) -> bool:
    state = ctx.exposed.state
    return isinstance(state.get("rows"), int) and isinstance(state.get("cols"), int)


def _da_rotate(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if "dir" in args and args["dir"] not in ("ccw", "cw"):
        report.error("SS281", f"{path}.args.dir", "dir 应为 ccw（逆时针，默认）或 cw（顺时针）")
    _unknown_args(args, {"dir"}, "rotate", report, path)
    if _da_ready(ctx):
        state = ctx.exposed.state
        state["rows"], state["cols"] = state["cols"], state["rows"]
        _da_fits(ctx, report, path)


def _da_extend(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    keys = {"rows", "cols"} & set(args)
    if not keys:
        report.error("SS281", f"{path}.args", "extend 要写 cols 和 / 或 rows：补到几列 / 几排（新的总数）")
    state = ctx.exposed.state
    for key in sorted(keys):
        v = args[key]
        if _positive_int(v):
            report.error("SS281", f"{path}.args.{key}", f"{key} 应为正整数（新的总数）")
        elif isinstance(state.get(key), int):
            if v < state[key]:
                report.error("SS261", f"{path}.args.{key}", f"现在已经有 {state[key]}，extend 只能变多（拿掉用 fade_col）")
            else:
                state[key] = v
    _role_arg(args, report, path)
    _role_arg(args, report, path, "faded_role")
    _unknown_args(args, {"rows", "cols", "role", "faded_role"}, "extend", report, path)
    _da_fits(ctx, report, path)


def _da_index(args: dict, key: str, limit: object, report: Report, path: str) -> None:
    v = args[key]
    if not isinstance(v, int) or isinstance(v, bool) or (isinstance(limit, int) and not -limit <= v < limit):
        report.error("SS281", f"{path}.args.{key}", f"{key} 应为整数，从 0 数，负数从末尾数（现在有 {limit}）")


def _da_fade_col(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if "col" in args:
        _da_index(args, "col", ctx.exposed.state.get("cols"), report, path)
    o = args.get("opacity")
    if o is not None and (not isinstance(o, (int, float)) or isinstance(o, bool) or not 0 <= o < 1):
        report.error("SS281", f"{path}.args.opacity", "opacity 应为 0 到 1 之间（不含 1）的数，默认 0.3")
    _role_arg(args, report, path)
    _unknown_args(args, {"col", "role", "opacity"}, "fade_col", report, path)


def _da_squares(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    _role_arg(args, report, path, "fill")
    if "dots" in args and not isinstance(args["dots"], bool):
        report.error("SS281", f"{path}.args.dots", "dots 应为 true / false（false：圆点淡出，只剩方格）")
    _unknown_args(args, {"fill", "dots"}, "squares", report, path)


def _da_recolor(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if "role" not in args:
        report.error("SS281", f"{path}.args", "recolor 需要 role")
    _role_arg(args, report, path)
    for key, axis in (("row", "rows"), ("col", "cols")):
        if key in args:
            _da_index(args, key, ctx.exposed.state.get(axis), report, path)
    _unknown_args(args, {"role", "row", "col"}, "recolor", report, path)


REGISTRY["dot_array"] = Widget(
    "dot_array",
    params={"rows": (True, _positive_int), "cols": (True, _positive_int), "cells": (False, _bool), "room": (False, _room)},
    expose=_expose_dot_array,
    actions={"rotate": _da_rotate, "extend": _da_extend, "fade_col": _da_fade_col, "squares": _da_squares,
             "recolor": _da_recolor},
    validate=_validate_dot_array,
)

# ---------- 积木条形图（block_bars）：平均数削峰填谷 ----------
# kit 的 mx/bars.py：每列几块方块。按动作顺序推演每列现在几块：transfer 从一列顶上拿到另一列，add 在空位上长出新列；
# 每列都不能高过 room，列数不能多过 cols。


def _heights(value: object) -> str | None:
    ok = isinstance(value, list) and value and not any(_nonneg_int(v) for v in value)
    return None if ok else "应为非负整数的列表：每列几块，从左往右"


def _bb_room(definition: dict) -> int | None:
    room, heights = definition.get("room"), definition.get("heights")
    if isinstance(room, int) and not isinstance(room, bool):
        return room
    if _heights(heights) is None:
        return max(heights)
    return None


def _expose_block_bars(definition: dict, data: dict) -> Exposed:
    heights = definition.get("heights")
    cols = list(heights) if _heights(heights) is None else None
    total = definition.get("cols", len(cols) if cols else 0)
    return Exposed(parts={"bars": 1, "line": 1}, state={"cols": cols, "slots": total})


def _validate_block_bars(ctx: WidgetContext, report: Report, path: str) -> None:
    d = ctx.definition
    heights, room = d.get("heights"), _bb_room(d)
    if _heights(heights) is not None:
        return
    if isinstance(room, int) and max(heights) > room:
        report.error("SS262", f"{path}.room", f"最高的一列有 {max(heights)} 块，放不进 room {room}")
    slots = d.get("cols")
    if isinstance(slots, int) and slots < len(heights):
        report.error("SS262", f"{path}.cols", f"heights 有 {len(heights)} 列，cols 不能比它少")
    labels = d.get("labels")
    if labels is not None and (_str_list(labels) or (isinstance(slots, int) and len(labels) > slots)):
        report.error("SS281", f"{path}.labels", "labels 应为字符串列表，最多 cols 个")


def _bb_col(args: dict, key: str, ctx: WidgetContext, report: Report, path: str) -> int | None:
    v, cols = args.get(key), ctx.exposed.state["cols"]
    n = len(cols) if cols is not None else None
    if not isinstance(v, int) or isinstance(v, bool) or (n is not None and not 0 <= v < n):
        report.error("SS281", f"{path}.args.{key}", f"{key} 应为列号，从 0 数（现在有 {n} 列）")
        return None
    return v


def _bb_move(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    for key in ("from", "to"):
        if key not in args:
            report.error("SS281", f"{path}.args", f"transfer 需要 {key}（列号，从 0 数）")
    src, dst = _bb_col(args, "from", ctx, report, path), _bb_col(args, "to", ctx, report, path)
    count = args.get("count", 1)
    if _positive_int(count):
        report.error("SS281", f"{path}.args.count", "count 应为正整数（挪几块，默认 1）")
        count = None
    _unknown_args(args, {"from", "to", "count"}, "transfer", report, path)
    cols, room = ctx.exposed.state["cols"], _bb_room(ctx.definition)
    if cols is None or src is None or dst is None or count is None:
        return
    if src == dst:
        report.error("SS281", f"{path}.args", "from 和 to 是同一列")
    elif cols[src] < count:
        report.error("SS261", path, f"第 {src} 列现在只有 {cols[src]} 块，挪不出 {count} 块")
    else:
        cols[src] -= count
        cols[dst] += count
        if isinstance(room, int) and cols[dst] > room:
            report.error("SS262", path, f"挪完第 {dst} 列有 {cols[dst]} 块，高过 room {room}")


def _bb_add(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    h = args.get("height")
    if _positive_int(h):
        report.error("SS281", f"{path}.args.height", "add 需要 height（新的一列几块，正整数）")
    _role_arg(args, report, path)
    if "label" in args and not isinstance(args["label"], str):
        report.error("SS281", f"{path}.args.label", "label 应为字符串（新列底下的名字）")
    _unknown_args(args, {"height", "role", "label"}, "add", report, path)
    state, room = ctx.exposed.state, _bb_room(ctx.definition)
    if state["cols"] is None:
        return
    if len(state["cols"]) >= state["slots"]:
        report.error("SS262", path, f"已经有 {len(state['cols'])} 列，没有空位了；在 {ctx.obj_id} 上写 cols: {len(state['cols']) + 1}")
        return
    if isinstance(h, int) and not isinstance(h, bool):
        state["cols"].append(h)
        if isinstance(room, int) and h > room:
            report.error("SS262", path, f"新的一列 {h} 块，高过 room {room}")


def _bb_level(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    at, room = args.get("at"), _bb_room(ctx.definition)
    if not isinstance(at, (int, float)) or isinstance(at, bool) or at < 0 or (isinstance(room, int) and at > room):
        report.error("SS281", f"{path}.args.at", f"level 需要 at：横线画在几块高（0 到 room {room}）")
    if "label" in args and not isinstance(args["label"], str):
        report.error("SS281", f"{path}.args.label", "label 应为字符串（可以混排 $公式$）")
    _role_arg(args, report, path)
    _unknown_args(args, {"at", "label", "role"}, "level", report, path)


def _bb_recolor(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if "role" not in args:
        report.error("SS281", f"{path}.args", "recolor 需要 role")
    _role_arg(args, report, path)
    if "col" in args:
        _bb_col(args, "col", ctx, report, path)
    _unknown_args(args, {"role", "col"}, "recolor", report, path)


REGISTRY["block_bars"] = Widget(
    "block_bars",
    params={"heights": (True, _heights), "room": (False, _positive_int), "cols": (False, _positive_int),
            "labels": (False, _str_list), "numbers": (False, _bool)},
    expose=_expose_block_bars,
    actions={"transfer": _bb_move, "add": _bb_add, "level": _bb_level, "unlevel": _no_args, "recolor": _bb_recolor},
    validate=_validate_block_bars,
)

# ---------- 天平（balance）：解方程两边同时拿走 ----------
# kit 的 mx/balance.py：两个盘里放砝码（1）和最多一个未知盒子（"box"，重 box）。按动作顺序推演每个盘里几块砝码：
# remove 不能拿走比盘里多的砝码（盒子不能拿），add 之后不能超过 room。


def _pan_items(value: object) -> str | None:
    ok = isinstance(value, list) and all(v == 1 or v == "box" for v in value) and sum(v == "box" for v in value) <= 1
    return None if ok else '应为列表，每项是 1（一块砝码）或 "box"（未知盒子，最多一个）'


def _expose_balance(definition: dict, data: dict) -> Exposed:
    state = {}
    for side in ("left", "right"):
        items = definition.get(side)
        state[side] = sum(v == 1 for v in items) if _pan_items(items) is None else None
    has_box = any("box" in (definition.get(s) or []) for s in ("left", "right") if isinstance(definition.get(s), list))
    return Exposed(parts={"left": 1, "right": 1, "beam": 1, "box": 1}, state={**state, "box": has_box})


def _bal_room(definition: dict) -> int | None:
    room = definition.get("room")
    if isinstance(room, int) and not isinstance(room, bool):
        return room
    sizes = [len(definition[s]) for s in ("left", "right") if isinstance(definition.get(s), list)]
    return max(sizes) if sizes else None


def _validate_balance(ctx: WidgetContext, report: Report, path: str) -> None:
    room = _bal_room(ctx.definition)
    for side in ("left", "right"):
        items = ctx.definition.get(side)
        if isinstance(items, list) and isinstance(room, int) and len(items) > room:
            report.error("SS262", f"{path}.room", f"{side} 盘里有 {len(items)} 样东西，放不进 room {room}")


def _bal_sides(args: dict, report: Report, path: str) -> list[str]:
    side = args.get("side", "both")
    if side not in ("left", "right", "both"):
        report.error("SS281", f"{path}.args.side", "side 应为 left / right / both")
        return []
    return ["left", "right"] if side == "both" else [side]


def _bal_change(act: str):
    def check(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
        sides = _bal_sides(args, report, path)
        n = args.get("count", 1)
        if _positive_int(n):
            report.error("SS281", f"{path}.args.count", "count 应为正整数（几块砝码，默认 1）")
            n = None
        _role_arg(args, report, path)
        _unknown_args(args, {"side", "count", "role"} if act == "add" else {"side", "count"}, act, report, path)
        state, room = ctx.exposed.state, _bal_room(ctx.definition)
        for side in sides:
            if state.get(side) is None or n is None:
                continue
            if act == "remove":
                if state[side] < n:
                    report.error("SS261", path, f"{side} 盘里只有 {state[side]} 块砝码，拿不走 {n} 块（盒子不能拿）")
                    continue
                state[side] -= n
            else:
                state[side] += n
                items = int(state[side]) + (1 if "box" in (ctx.definition.get(side) or []) else 0)
                if isinstance(room, int) and items > room:
                    report.error("SS262", path, f"放完 {side} 盘里有 {items} 样东西，放不进 room {room}")
    return check


def _bal_label(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    if not ctx.exposed.state.get("box"):
        report.error("SS261", path, f"{ctx.obj_id} 里没有未知盒子（\"box\"），没有字可换")
    if not isinstance(args.get("text"), (str, int)) or isinstance(args.get("text"), bool):
        report.error("SS281", f"{path}.args.text", "label 需要 text（盒子上换成的字）")
    _unknown_args(args, {"text"}, "label", report, path)


REGISTRY["balance"] = Widget(
    "balance",
    params={"left": (True, _pan_items), "right": (True, _pan_items), "box": (True, _positive_int),
            "box_label": (False, _number_or_str), "room": (False, _positive_int)},
    expose=_expose_balance,
    actions={"remove": _bal_change("remove"), "add": _bal_change("add"), "label": _bal_label},
    validate=_validate_balance,
)

# ---------- 钱包（wallet）：现金和欠条，余额条 ----------
# kit 的 mx/wallet.py：两排卡片（现金 cash、欠条 iou），每张若干元；余额 = 现金 − 欠条。按动作顺序推演两排各有哪些卡片：
# take 不能拿走比那一排多的卡片，put 不能超过 slots，余额不能超出余额条的 range。


def _expose_wallet(definition: dict, data: dict) -> Exposed:
    value = definition.get("value", 3)
    rows = {k: [value] * definition.get(k, 0) if isinstance(definition.get(k, 0), int) else [] for k in ("cash", "iou")}
    return Exposed(parts={"cash": 1, "iou": 1, "balance": 1}, state={"rows": rows})


def _wallet_range_check(ctx: WidgetContext, report: Report, path: str) -> None:
    rows, rng = ctx.exposed.state["rows"], ctx.definition.get("range", 12)
    total = sum(rows["cash"]) - sum(rows["iou"])
    if isinstance(rng, int) and abs(total) > rng:
        report.error("SS262", path, f"余额 {total} 超出余额条的 range {rng}；在 {ctx.obj_id} 上写 range: {abs(total)}")


def _validate_wallet(ctx: WidgetContext, report: Report, path: str) -> None:
    slots = ctx.definition.get("slots", 4)
    for kind in ("cash", "iou"):
        n = ctx.definition.get(kind, 0)
        if isinstance(n, int) and isinstance(slots, int) and n > slots:
            report.error("SS262", f"{path}.{kind}", f"{kind} 一开始有 {n} 张，一排只有 {slots} 个位置")
    _wallet_range_check(ctx, report, path)


def _wallet_change(act: str):
    def check(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
        kind = args.get("kind")
        if kind not in ("cash", "iou"):
            report.error("SS281", f"{path}.args.kind", f"{act} 需要 kind：cash（现金）或 iou（欠条）")
            return
        n = args.get("count", 1)
        if _positive_int(n):
            report.error("SS281", f"{path}.args.count", "count 应为正整数（几张，默认 1）")
            return
        allowed = {"kind", "count", "value"} if act == "put" else {"kind", "count", "quiet"}
        if "quiet" in args and not isinstance(args["quiet"], bool):
            report.error("SS281", f"{path}.args.quiet", "quiet 应为 true / false（true：原地淡出，不演拿走）")
        _unknown_args(args, allowed, act, report, path)
        rows, slots = ctx.exposed.state["rows"], ctx.definition.get("slots", 4)
        if act == "put":
            value = args.get("value", ctx.definition.get("value", 3))
            if _positive_int(value):
                report.error("SS281", f"{path}.args.value", "value 应为正整数（每张多少元）")
                return
            if isinstance(slots, int) and len(rows[kind]) + n > slots:
                report.error("SS262", path, f"{kind} 那一排已经有 {len(rows[kind])} 张，放不下 {n} 张（slots {slots}）")
                return
            rows[kind] += [value] * n
        else:
            if len(rows[kind]) < n:
                report.error("SS261", path, f"{kind} 那一排只有 {len(rows[kind])} 张，拿不走 {n} 张")
                return
            del rows[kind][len(rows[kind]) - n:]
        _wallet_range_check(ctx, report, path)
    return check


REGISTRY["wallet"] = Widget(
    "wallet",
    params={"value": (False, _positive_int), "cash": (False, _nonneg_int), "iou": (False, _nonneg_int),
            "slots": (False, _positive_int), "range": (False, _positive_int)},
    expose=_expose_wallet,
    actions={"put": _wallet_change("put"), "take": _wallet_change("take")},
    validate=_validate_wallet,
)

# ---------- 函数图像（graph）：坐标轴、曲线、点、割线、切线 ----------
# 函数写成白名单表达式字符串（见 expr.py），这里检查语法、点是否在定义域里、切线处左右导数是否相等。

import math  # noqa: E402

from . import expr as _expr  # noqa: E402

GRAPH_LABEL_DIRS = ("u", "d", "l", "r", "ul", "ur", "dl", "dr")


def _num(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _graph_range(value: object) -> str | None:
    if not (isinstance(value, list) and len(value) == 2 and all(_num(v) for v in value) and value[0] < value[1]):
        return "应为 [最小值, 最大值]，两个数且前小后大"
    return None


def _graph_positive(value: object) -> str | None:
    return None if _num(value) and value > 0 else "应为正数"


def _graph_ticks(value: object) -> str | None:
    return None if value is False or (_num(value) and value > 0) else "应为刻度间隔（正数），或 false 不画刻度"


def _graph_axis_labels(value: object) -> str | None:
    ok = value is False or (isinstance(value, list) and len(value) == 2 and all(isinstance(v, str) and v for v in value))
    return None if ok else "应为两个 LaTeX 字符串 [横轴名, 纵轴名]，或 false"


def _graph_entries(fields: dict[str, Callable[[object], bool]], required: tuple[str, ...], what: str) -> ParamCheck:
    def check(value: object) -> str | None:
        if not isinstance(value, list):
            return f"应为列表，每项是{what}"
        for n, entry in enumerate(value):
            if not isinstance(entry, dict):
                return f"第 {n} 项应为 {{{', '.join(fields)}}}"
            extra = set(entry) - set(fields)
            if extra:
                return f"第 {n} 项有不认识的字段 {sorted(extra)}（可用：{', '.join(fields)}）"
            for key in required:
                if key not in entry:
                    return f"第 {n} 项缺少 {key}"
            for key, ok in fields.items():
                if key in entry and not ok(entry[key]):
                    return f"第 {n} 项的 {key} 不对"
        return None

    return check


def _is_role(v: object) -> bool:
    return v in ROLES


def _is_text(v: object) -> bool:
    return isinstance(v, str) and bool(v)


def _is_index(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _is_expr(v: object) -> bool:
    """只查语法（不认识的名字先当参数，名字对不对由 validate 按 params 核对）。"""
    try:
        _expr.parse(v, _expr.ANY)  # type: ignore[arg-type]
    except _expr.ExprError:
        return False
    return True


def _num_or_expr(v: object) -> bool:
    return _num(v) or (isinstance(v, str) and _is_expr(v))


_graph_plots = _graph_entries(
    {"f": lambda v: isinstance(v, str) and _is_expr(v), "data": _is_text, "role": _is_role, "label": _is_text,
     "domain": lambda v: _graph_range(v) is None, "progress": _num_or_expr, "along": lambda v: v in _curves.ALONG},
    (), "一条曲线 {f: \"x^2\", role?, label?, domain?}，或数据曲线 {data: 键, progress?, along?, role?, label?}")
_graph_points = _graph_entries(
    {"x": _num_or_expr, "plot": _is_index, "label": _is_text, "role": _is_role,
     "label_dir": lambda v: v in GRAPH_LABEL_DIRS},
    ("x",), "曲线上的一个点 {x（数或参数表达式）, plot?, label?, role?, label_dir?}")
_graph_secants = _graph_entries(
    {"point": _is_index, "h": lambda v: _num(v) and v != 0, "label": _is_text, "role": _is_role,
     "label_dir": lambda v: v in GRAPH_LABEL_DIRS, "readout": lambda v: isinstance(v, bool), "readout_text": _is_text},
    ("point", "h"), "一条割线 {point, h（≠0）, label?, role?, readout?}")
_graph_tangents = _graph_entries({"point": _is_index, "role": _is_role}, ("point",), "一条切线 {point, role?}")
_graph_lines = _graph_entries(
    {"x": _num_or_expr, "through": lambda v: isinstance(v, list) and len(v) == 2 and all(_num_or_expr(c) for c in v),
     "slope": _num_or_expr, "role": _is_role},
    (), "一条直线 {x}（竖线）或 {through: [x, y], slope}（都可以写参数表达式）")
_graph_triangles = _graph_entries(
    {"point": _is_index, "run": _num_or_expr, "role": _is_role, "labels": lambda v: isinstance(v, bool)},
    ("point",), "一个斜率三角形 {point, run?（横走多少，默认 1）, role?, labels?}")
GRAPH_EXPR_FIELDS = (("points", ("x",)), ("lines", ("x", "slope")), ("triangles", ("run",)))


def _graph_list(definition: dict, key: str) -> list:
    value = definition.get(key)
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _expose_graph(definition: dict, data: dict) -> Exposed:
    n = {k: len(_graph_list(definition, k)) for k in ("plots", "points", "secants", "tangents", "lines", "triangles")}
    readouts = sum(1 for s in _graph_list(definition, "secants") if s.get("readout"))
    parts = {
        "axes": 1, "plot": n["plots"], "plot_label": n["plots"], "point": n["points"], "dot": n["points"],
        "secant": n["secants"], "qpoint": n["secants"], "slope": readouts, "tangent": n["tangents"], "line": n["lines"],
        "triangle": n["triangles"],
    }
    return Exposed(parts=parts, items=sum(parts.values()) - n["points"])  # dot 和 point 是同一个点


def _tree(value: object, env: dict | None = None):
    """数或表达式 → 语法树，按 env 里的参数名解析（kx 拆成 k·x）；不合法返回 None（已经报过）。"""
    if _num(value):
        return ("num", float(value))
    if not isinstance(value, str):
        return None
    try:
        return _expr.parse(value, set(env or ()))
    except _expr.ExprError:
        return None


def _graph_fn(definition: dict, k: object, env: dict | None = None):
    plots = _graph_list(definition, "plots")
    if not _is_index(k) or k >= len(plots):
        return None
    return _tree(plots[k].get("f"), env)


def _graph_point_xy(definition: dict, i: int, env: dict | None = None):
    """第 i 个点的 (曲线语法树, 参数取 env 时的 x)；点或曲线不合法时返回 None（参数检查已经报过）。"""
    points = _graph_list(definition, "points")
    if i >= len(points):
        return None
    xt = _tree(points[i].get("x"), env)
    tree = _graph_fn(definition, points[i].get("plot", 0), env)
    if xt is None or tree is None:
        return None
    try:
        return tree, _expr.evaluate(xt, math.nan, env)
    except KeyError:  # 用了没声明的参数：已经报过 SS402
        return None


def _safe(tree: tuple, x: float, env: dict | None) -> float:
    try:
        return _expr.evaluate(tree, x, env)
    except KeyError:
        return math.nan


def _graph_check_exprs(ctx: WidgetContext, report: Report, path: str) -> bool:
    """按声明的参数核对表达式（SS401–SS403）；全部合法返回 True。"""
    ex, d, ok = ctx.ex, ctx.definition, True
    if ex is None:
        return True
    for n, plot in enumerate(_graph_list(d, "plots")):
        if isinstance(plot.get("f"), str):
            ok &= ex.parse(plot["f"], f"{path}.plots[{n}].f", allow_x=True) is not None
    for key, fields in GRAPH_EXPR_FIELDS:
        for n, entry in enumerate(_graph_list(d, key)):
            for field_ in fields:
                if field_ in entry:
                    ok &= ex.parse(entry[field_], f"{path}.{key}[{n}].{field_}") is not None
            if key == "lines" and isinstance(entry.get("through"), list):
                for c, v in enumerate(entry["through"]):
                    ok &= ex.parse(v, f"{path}.lines[{n}].through[{c}]") is not None
    return ok


def _graph_check_states(ctx: WidgetContext, report: Report, path: str) -> None:
    """参数取每组关键值时：点在横轴范围里、曲线在点处有定义，斜率三角形的另一端也是（SS411）。"""
    ex, d = ctx.ex, ctx.definition
    xr = d.get("x") if _graph_range(d.get("x")) is None else None
    states = ex.states_for(ctx.obj_id) if ex is not None and ex.names else []
    points = _graph_list(d, "points")
    for env in states:
        where = ex.describe(env)
        for n in range(len(points)):
            xy = _graph_point_xy(d, n, env)
            if xy is None:
                continue
            tree, x = xy
            if not math.isfinite(x) or (xr and not xr[0] - 1e-9 <= x <= xr[1] + 1e-9):
                report.error("SS411", f"{path}.points[{n}].x", f"参数取 {where} 时，点的 x={x:g} 出了横轴范围 {xr}")
            elif not math.isfinite(_safe(tree, x, env)):
                report.error("SS411", f"{path}.points[{n}].x", f"参数取 {where} 时，曲线在 x={x:g} 处没有定义")
        for n, tri in enumerate(_graph_list(d, "triangles")):
            xy = _graph_point_xy(d, tri.get("point", 0), env) if _is_index(tri.get("point", 0)) else None
            run = _tree(tri.get("run", 1), env)
            if xy is None or run is None:
                continue
            tree, x = xy
            x2 = x + _safe(run, math.nan, env)
            if not math.isfinite(_safe(tree, x2, env)) or (xr and not xr[0] - 1e-9 <= x2 <= xr[1] + 1e-9):
                report.error("SS411", f"{path}.triangles[{n}].run",
                             f"参数取 {where} 时，三角形的另一端 x={x2:g} 出了横轴范围或不在曲线定义域里")
        for n, ln in enumerate(_graph_list(d, "lines")):
            for field_ in ("x", "slope"):
                t = _tree(ln.get(field_), env) if field_ in ln else None
                if t is not None and not math.isfinite(_safe(t, math.nan, env)):
                    report.error("SS411", f"{path}.lines[{n}].{field_}", f"参数取 {where} 时没有定义")


def _graph_check_data(ctx: WidgetContext, report: Report, path: str) -> None:
    """数据曲线 {data: 键}：f 和 data 只写一个；点列合规、在坐标范围里；progress 在 [0, 1] 里（SS490–SS499）。"""
    d = ctx.definition
    xr, yr = (d.get(k) if _graph_range(d.get(k)) is None else None for k in ("x", "y"))
    box = (xr[0], yr[0], xr[1], yr[1]) if xr and yr else None
    for n, plot in enumerate(_graph_list(d, "plots")):
        ppath = f"{path}.plots[{n}]"
        if ("f" in plot) == ("data" in plot):
            report.error("SS496", ppath, "曲线写 {f: \"x^2\"}（函数）或 {data: 键}（数据点列），只写一个")
            continue
        if "data" not in plot:
            for key in ("progress", "along"):
                if key in plot:
                    report.error("SS496", f"{ppath}.{key}", f"{key} 只用于数据曲线 {{data: 键}}（函数曲线用 draw 动作画出来）")
            continue
        if "domain" in plot:
            report.error("SS496", f"{ppath}.domain", "数据曲线不写 domain：画的就是 data 里的全部点")
        _curves.check_data(plot, ppath, ctx.data, box, report)
        _curves.check_common(plot, ppath, ctx.ex, ctx.obj_id, report)


def _validate_graph(ctx: WidgetContext, report: Report, path: str) -> None:
    d = ctx.definition
    _graph_check_data(ctx, report, path)
    if not _graph_check_exprs(ctx, report, path):
        return
    env = ctx.ex.states[0] if ctx.ex is not None else None  # 参数的初值
    plots, points = _graph_list(d, "plots"), _graph_list(d, "points")
    xr = d.get("x") if _graph_range(d.get("x")) is None else None
    for n, p in enumerate(points):
        k = p.get("plot", 0)
        if _is_index(k) and k >= len(plots):
            report.error("SS291", f"{path}.points[{n}].plot", f"只有 {len(plots)} 条曲线，没有第 {k} 条（从 0 数）")
            continue
        if _is_index(k) and "data" in plots[k]:
            report.error("SS496", f"{path}.points[{n}].plot",
                         f"第 {k} 条是数据曲线：graph 的点只能放在函数曲线上；沿数据走的点请用 plane 的 curves + points")
            continue
        xy = _graph_point_xy(d, n, env)
        if xy is None:
            continue
        tree, x = xy
        if xr and not xr[0] <= x <= xr[1]:
            report.error("SS292", f"{path}.points[{n}].x", f"x={x:g} 不在横轴范围 {xr} 里")
        if not math.isfinite(_safe(tree, x, env)):
            report.error("SS292", f"{path}.points[{n}].x", f"{plots[k]['f']} 在 x={x:g} 处没有定义")
    for key in ("secants", "tangents", "triangles"):
        for n, s in enumerate(_graph_list(d, key)):
            i = s.get("point", 0)
            if _is_index(i) and i >= len(points):
                report.error("SS291", f"{path}.{key}[{n}].point", f"只有 {len(points)} 个点，没有第 {i} 个（从 0 数）")
                continue
            xy = _graph_point_xy(d, i, env) if _is_index(i) else None
            if xy is None:
                continue
            tree, x = xy
            if key == "secants" and _num(s.get("h")):
                _graph_check_h(tree, x, s["h"], report, f"{path}.secants[{n}].h", env)
            if key == "tangents":
                e = 1e-6 * max(1.0, abs(x))
                y = _safe(tree, x, env)
                right = (_safe(tree, x + e, env) - y) / e
                left = (y - _safe(tree, x - e, env)) / e
                if not (math.isfinite(left) and math.isfinite(right)) or abs(left - right) > 1e-3 * max(1.0, abs(left)):
                    report.error("SS293", f"{path}.tangents[{n}]",
                                 f"曲线在 x={x:g} 处左右导数不相等（约 {left:.3g} 和 {right:.3g}），没有切线；"
                                 "非例请用两条割线（h 一正一负）来演示")
    for n, ln in enumerate(_graph_list(d, "lines")):
        if ("x" in ln) == ("through" in ln or "slope" in ln) or ("through" in ln) != ("slope" in ln):
            report.error("SS294", f"{path}.lines[{n}]", "直线写 {x: c}（竖线），或 {through: [x, y], slope: k}")
    _graph_check_states(ctx, report, path)


def _graph_check_h(tree, x: float, h: float, report: Report, path: str, env: dict | None = None) -> None:
    if not math.isfinite(_safe(tree, x + h, env)):
        report.error("SS295", path, f"割线的第二个点 x={x + h:g} 不在曲线的定义域里")


def _graph_draw(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    k = args.get("plot", 0)
    n = len(_graph_list(ctx.definition, "plots"))
    if not _is_index(k) or k >= n:
        report.error("SS296", f"{path}.args.plot", f"draw 的 plot 应为 0 到 {n - 1} 的整数")


def _graph_approach(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    secants = _graph_list(ctx.definition, "secants")
    i = args.get("secant", 0)
    if not _is_index(i) or i >= len(secants):
        report.error("SS296", f"{path}.args.secant", f"approach 的 secant 应为 0 到 {len(secants) - 1} 的整数")
        return
    h = args.get("h")
    if not _num(h) or h == 0:
        report.error("SS296", f"{path}.args.h", "approach 需要 h：第二个点的目标偏移量，非零的数（h → 0 只能逼近，不能等于 0）")
        return
    point = secants[i].get("point")
    env = ctx.ex.states[0] if ctx.ex is not None else None
    xy = _graph_point_xy(ctx.definition, point, env) if _is_index(point) else None
    if xy is not None:
        if (h > 0) != (secants[i].get("h", h) > 0):
            report.warning("SS297", f"{path}.args.h", "h 换了符号：第二个点会穿过第一个点，割线会先乱转一下")
        _graph_check_h(xy[0], xy[1], h, report, f"{path}.args.h", env)


REGISTRY["graph"] = Widget(
    "graph",
    params={
        "x": (True, _graph_range),
        "y": (True, _graph_range),
        "plots": (True, _graph_plots),
        "points": (False, _graph_points),
        "secants": (False, _graph_secants),
        "tangents": (False, _graph_tangents),
        "lines": (False, _graph_lines),
        "triangles": (False, _graph_triangles),
        "unit": (False, _graph_positive),
        "ticks": (False, _graph_ticks),
        "tick_labels": (False, _bool),
        "axis_labels": (False, _graph_axis_labels),
        "readout_at": (False, lambda v: None if isinstance(v, list) and len(v) == 2 and all(_num(c) for c in v)
                       else "应为 [x, y]：第一个斜率读数左上角的数学坐标"),
    },
    expose=_expose_graph,
    actions={"draw": _graph_draw, "approach": _graph_approach},
    validate=_validate_graph,
)


# ---------- 剖分（dissect）：剪开、刚体移动、拼成另一个图形；几何和检查都在 dissect.py ----------

from .dissect import register as _register_dissect  # noqa: E402

_register_dissect(REGISTRY)

# ---------- 坐标平面（plane）：向量、复平面乘 i、矩阵变形；检查在 plane.py ----------

from .plane import register as _register_plane  # noqa: E402

_register_plane(REGISTRY, Widget, Exposed, _unknown_args)

# ---------- 随机试验：抛硬币频率（coin_flips）、高尔顿板（galton）、样本空间方格（outcomes）；检查在 chance.py ----------

from .chance import register as _register_chance  # noqa: E402

_register_chance(REGISTRY, Widget, Exposed, _unknown_args)


# ---------- 立体（solid）：轴测图、立方体剖成三个四棱锥、水平截面；检查在 solid.py ----------

from .solid import register as _register_solid  # noqa: E402

_register_solid(REGISTRY)

# ---------- 三维坐标空间（space）：向量、直线、平面、平行六面体、3×3 矩阵变形、投影；检查在 space.py ----------

from .space import register as _register_space  # noqa: E402

_register_space(REGISTRY, Widget, Exposed, _unknown_args)


# ---------- 编程课组件（代码面板、终端、调用栈……）：检查在 cs.py，设计见 docs/cs-lecture.md ----------

from .cs import register as _register_cs  # noqa: E402

_register_cs(REGISTRY)


# ---------- 综合几何图（geometry）：点由构造算出、断言数值验算；求解器和检查在 geometry.py ----------

from .geometry import register as _register_geometry  # noqa: E402

_register_geometry(REGISTRY, Widget, Exposed, _unknown_args)


def lookup(name: str) -> Widget | None:
    """按名字找组件，忽略 @版本。"""
    return REGISTRY.get(name.split("@", 1)[0])


def param_keys(definition: dict) -> set[str]:
    return set(definition) - LAYOUT_KEYS


def check_params(widget: Widget, definition: dict, report: Report, path: str) -> None:
    for key, (required, check) in widget.params.items():
        if key not in definition:
            if required:
                report.error("SS201", path, f"组件 {widget.name} 缺少参数 {key}")
            continue
        problem = check(definition[key])
        if problem:
            report.error("SS202", f"{path}.{key}", problem)
    for key in sorted(param_keys(definition) - set(widget.params)):
        report.error("SS203", f"{path}.{key}", f"组件 {widget.name} 没有参数 {key}")
