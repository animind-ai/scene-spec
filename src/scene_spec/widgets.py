"""组件登记表。

组件本身由 kit / primitives 实现；这里只登记检查器需要知道的东西：
- 参数：哪些必填、类型对不对；
- 暴露的子元素：选择器 obj#span、obj.part[i]、obj[i] 能指向什么；
- 组件自带的动作和它们的参数；
- 数据自洽检查（例如差分表的下一行必须是上一行的逐项差）。

未登记的组件不报错，只给警告：引用和参数无法校验。kit 以后可以注册自己的组件。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

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
    "gap", "align", "size", "pin", "at",
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
        params={"items": (True, _str_list)},
        expose=_expose_items("items"),
    ),
    "summary": Widget(
        "summary",
        params={"rows": (True, _summary_rows)},
        expose=_expose_items("rows"),
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

NUMBER_LINE_POINTS = 4  # mark_point 最多点几个（erase 后重新计数）


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
                          "jump": slots, "count": slots, "rest": 1, "point": NUMBER_LINE_POINTS})


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
    if count is not None:
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            report.error("SS283", f"{path}.args.count", "count 应为正整数（不写就跳到放不下为止）")
        elif bounds and count > math.floor((bounds[1] - bounds[0]) / length):
            report.error("SS285", f"{path}.args.count", f"长度 {args['length']} 在 {list(bounds)} 上最多跳 "
                         f"{math.floor((bounds[1] - bounds[0]) / length)} 次")
    for key in sorted(set(args) - {"length", "count"}):
        report.error("SS281", f"{path}.args.{key}", f"jump 没有参数 {key}（可用：length、count）")


def _nl_subdivide(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    problem = _positive_int(args.get("parts"))
    if problem:
        report.error("SS286", f"{path}.args.parts", f"subdivide 需要 parts（每个单位分成几份）：{problem}")


def _nl_highlight(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    a = _nl_value(args, "from", report, path, ctx, required=False)
    b = _nl_value(args, "to", report, path, ctx)
    if a is not None and b is not None and b <= a:
        report.error("SS282", f"{path}.args", "highlight 的 to 要大于 from")


def _nl_mark_point(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    _nl_value(args, "at", report, path, ctx)
    if "label" in args and _str(args["label"]):
        report.error("SS281", f"{path}.args.label", "label 应为非空的 LaTeX 字符串")


def _nl_no_args(args: dict, ctx: WidgetContext, report: Report, path: str) -> None:
    for key in sorted(args):
        report.error("SS281", f"{path}.args.{key}", f"这个动作不带参数（多了 {key}）")


REGISTRY["number_line"] = Widget(
    "number_line",
    params={
        "range": (True, _nl_range),
        "parts": (False, _positive_int),
        "measures": (False, _nl_measures),
        "fractions": (False, _bool),
    },
    expose=_expose_number_line,
    actions={"jump": _nl_jump, "remainder": _nl_no_args, "subdivide": _nl_subdivide, "highlight": _nl_highlight,
             "mark_point": _nl_mark_point, "erase": _nl_no_args},
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
    {"f": lambda v: isinstance(v, str) and _is_expr(v), "role": _is_role, "label": _is_text,
     "domain": lambda v: _graph_range(v) is None},
    ("f",), "一条曲线 {f: \"x^2\", role?, label?, domain?}")
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


def _validate_graph(ctx: WidgetContext, report: Report, path: str) -> None:
    d = ctx.definition
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
