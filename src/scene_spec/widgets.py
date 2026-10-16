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


ParamCheck = Callable[[object], str | None]  # 返回问题描述，没问题返回 None
ActionCheck = Callable[[dict, "WidgetContext", Report, str], None]


@dataclass
class WidgetContext:
    obj_id: str
    definition: dict
    data: dict
    exposed: Exposed


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
