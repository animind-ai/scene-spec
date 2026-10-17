"""坐标平面（plane）的检查：向量、复平面乘 i、矩阵变形。组件本身在 kit 的 mx/plane.py。

按动作顺序推演平面上有哪些东西（名字 → 数学坐标）和到目前为止的整体变换，检查：
- 参数和动作参数的类型；名字不重复、引用的名字存在；
- 每个东西在每个动作之后都还在坐标范围 x、y 里（伸出去会盖住刻度、出了组件排版时预留的框），SS262；
- warp 的矩阵不能是奇异的（整个平面压成一条线，网格画不出来），SS281。
"""

from __future__ import annotations

import math

from .report import Report
from .textmarks import ROLES

POINT_DIRS = ("u", "d", "l", "r", "ul", "ur", "dl", "dr")


def _num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _pair(v: object) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(_num(x) for x in v)


def _range(value: object) -> str | None:
    ok = (isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
          and value[0] <= 0 < value[1])
    return None if ok else "应为 [起, 止]：整数，起 ≤ 0 < 止"


def _bool(value: object) -> str | None:
    return None if isinstance(value, bool) else "应为 true / false"


def _role(value: object) -> str | None:
    return None if value in ROLES else f"应为 {'/'.join(sorted(ROLES))} 之一"


def _labels(value: object) -> str | None:
    ok = isinstance(value, list) and len(value) == 2 and all(isinstance(v, str) for v in value)
    return None if ok else "应为两个字符串：横轴名、纵轴名"


# 2×2 矩阵写成 ((a, b), (c, d))，点写成 (x, y)：检查器不依赖 numpy

Mat = tuple[tuple[float, float], tuple[float, float]]
EYE: Mat = ((1.0, 0.0), (0.0, 1.0))


def _matrix(value: object) -> Mat | None:
    if isinstance(value, list) and len(value) == 2 and all(isinstance(r, list) and len(r) == 2 and all(_num(x) for x in r)
                                                           for r in value):
        return tuple(tuple(float(x) for x in r) for r in value)  # type: ignore[return-value]
    return None


def mul(m: Mat, n: Mat) -> Mat:
    return tuple(tuple(sum(m[i][k] * n[k][j] for k in range(2)) for j in range(2)) for i in range(2))  # type: ignore[return-value]


def det(m: Mat) -> float:
    return m[0][0] * m[1][1] - m[0][1] * m[1][0]


def inv(m: Mat) -> Mat:
    d = det(m)
    return ((m[1][1] / d, -m[0][1] / d), (-m[1][0] / d, m[0][0] / d))


def rot(radians: float) -> Mat:
    c, s = math.cos(radians), math.sin(radians)
    return ((c, -s), (s, c))


def lerp(m: Mat, t: float) -> Mat:
    return tuple(tuple((1 - t) * EYE[i][j] + t * m[i][j] for j in range(2)) for i in range(2))  # type: ignore[return-value]


def act(m: Mat, pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(m[0][0] * x + m[0][1] * y, m[1][0] * x + m[1][1] * y) for x, y in pts]


def rotation_angle(m: Mat) -> float | None:
    """纯旋转（正交、行列式 1）时返回转角（弧度），否则 None。"""
    mt = mul(m, ((m[0][0], m[1][0]), (m[0][1], m[1][1])))
    if all(abs(mt[i][j] - EYE[i][j]) < 1e-9 for i in range(2) for j in range(2)) and det(m) > 0:
        return math.atan2(m[1][0], m[0][0])
    return None


def register(registry: dict, Widget, Exposed, unknown_args) -> None:  # noqa: N803
    def expose(definition: dict, data: dict) -> Exposed:
        return Exposed(parts={"axes": 1, "grid": 1, "mesh": 1, "items": 1}, state={"items": {}, "M": EYE, "fixed": set()})

    def box(ctx):
        x, y = ctx.definition.get("x"), ctx.definition.get("y")
        if _range(x) or _range(y):
            return None
        return x[0], y[0], x[1], y[1]

    def inside(ctx, report: Report, path: str, name: str, pts: list[tuple[float, float]]) -> None:
        b = box(ctx)
        if b is None:
            return
        out = max(pts, key=lambda p: max(b[0] - p[0], p[0] - b[2], b[1] - p[1], p[1] - b[3]))
        if max(b[0] - out[0], out[0] - b[2], b[1] - out[1], out[1] - b[3]) > 1e-9:
            far = out
            report.error("SS262", path, f"{name} 伸到 ({far[0]:.3g}, {far[1]:.3g})，出了坐标范围 x {[b[0], b[2]]}、y {[b[1], b[3]]}")

    def new_name(args: dict, key: str, ctx, report: Report, path: str) -> str | None:
        name = args.get(key)
        if not isinstance(name, str) or not name:
            report.error("SS281", f"{path}.args.{key}", f"需要 {key}：名字（之后的动作按它找）")
            return None
        if name in ctx.exposed.state["items"]:
            report.error("SS281", f"{path}.args.{key}", f"名字 {name} 已经用过了")
            return None
        return name

    def old_names(args: dict, ctx, report: Report, path: str, required: bool) -> list[str] | None:
        """动作的 name：一个名字或名字列表，都要已经画上去；不写时（required 为假）是全部。"""
        v = args.get("name")
        items = ctx.exposed.state["items"]
        if v is None:
            if required:
                report.error("SS281", f"{path}.args", "需要 name")
                return None
            return [n for n in items if n not in ctx.exposed.state["fixed"]]
        names = [v] if isinstance(v, str) else v
        if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
            report.error("SS281", f"{path}.args.name", "name 应为名字或名字列表")
            return None
        missing = [n for n in names if n not in items]
        if missing:
            report.error("SS281", f"{path}.args.name", f"平面上还没有 {'、'.join(missing)}（现在有 {'、'.join(items) or '无'}）")
            return None
        return names

    def role(args: dict, report: Report, path: str) -> None:
        if "role" in args and _role(args["role"]):
            report.error("SS281", f"{path}.args.role", _role(args["role"]))

    def label(args: dict, report: Report, path: str, key: str = "label") -> None:
        if key in args and not isinstance(args[key], str):
            report.error("SS281", f"{path}.args.{key}", f"{key} 应为字符串（公式，不加 $）")

    def vector(args: dict, ctx, report: Report, path: str) -> None:
        name = new_name(args, "name", ctx, report, path)
        v, at = args.get("v"), args.get("at", [0, 0])
        if not _pair(v):
            report.error("SS281", f"{path}.args.v", "vector 需要 v：[x, y] 分量")
        if not _pair(at):
            report.error("SS281", f"{path}.args.at", "at 应为 [x, y]：尾巴的位置")
        if "side" in args and args["side"] not in ("l", "r"):
            report.error("SS281", f"{path}.args.side", "side 应为 l / r（名字在箭头的左边或右边）")
        if "along" in args and not (_num(args["along"]) and 0 <= args["along"] <= 1):
            report.error("SS281", f"{path}.args.along", "along 应为 0 到 1 的数（名字挨着箭杆的哪一处，0 尾 1 头）")
        if "dashed" in args and _bool(args["dashed"]):
            report.error("SS281", f"{path}.args.dashed", "dashed 应为 true / false")
        role(args, report, path)
        label(args, report, path)
        unknown_args(args, {"name", "v", "at", "role", "label", "side", "along", "dashed"}, "vector", report, path)
        if name and _pair(v) and _pair(at):
            pts = [(at[0], at[1]), (at[0] + v[0], at[1] + v[1])]
            ctx.exposed.state["items"][name] = pts
            inside(ctx, report, path, name, pts)

    def slide(args: dict, ctx, report: Report, path: str) -> None:
        names = old_names(args, ctx, report, path, True)
        at = args.get("at")
        if not _pair(at):
            report.error("SS281", f"{path}.args.at", "slide 需要 at：[x, y]，箭头的尾巴挪到这里")
        copy = new_name(args, "copy", ctx, report, path) if "copy" in args else None
        role(args, report, path)
        label(args, report, path)
        unknown_args(args, {"name", "at", "copy", "role", "label"}, "slide", report, path)
        if not names or not _pair(at):
            return
        if len(names) != 1:
            report.error("SS281", f"{path}.args.name", "slide 一次挪一支箭头")
            return
        items = ctx.exposed.state["items"]
        old = items[names[0]]
        if len(old) != 2:
            report.error("SS281", f"{path}.args.name", f"{names[0]} 不是箭头")
            return
        pts = [(at[0], at[1]), (at[0] + old[1][0] - old[0][0], at[1] + old[1][1] - old[0][1])]
        if copy:
            items[copy] = pts
        elif "copy" not in args:
            items[names[0]] = pts
        inside(ctx, report, path, copy or names[0], pts)

    def point(args: dict, ctx, report: Report, path: str) -> None:
        name = new_name(args, "name", ctx, report, path)
        if not _pair(args.get("at")):
            report.error("SS281", f"{path}.args.at", "point 需要 at：[x, y]")
        if "dir" in args and args["dir"] not in POINT_DIRS:
            report.error("SS281", f"{path}.args.dir", f"dir 应为 {' / '.join(POINT_DIRS)} 之一")
        role(args, report, path)
        label(args, report, path)
        if "fixed" in args and _bool(args["fixed"]):
            report.error("SS281", f"{path}.args.fixed", "fixed 应为 true / false")
        unknown_args(args, {"name", "at", "label", "role", "dir", "fixed"}, "point", report, path)
        if name and _pair(args.get("at")):
            ctx.exposed.state["items"][name] = pts = [tuple(args["at"])]
            if args.get("fixed") is True:
                ctx.exposed.state["fixed"].add(name)
            inside(ctx, report, path, name, pts)

    def shape(args: dict, ctx, report: Report, path: str) -> None:
        name = new_name(args, "name", ctx, report, path)
        pts = args.get("points")
        ok = isinstance(pts, list) and len(pts) >= 3 and all(_pair(p) for p in pts)
        if not ok:
            report.error("SS281", f"{path}.args.points", "shape 需要 points：至少三个 [x, y]")
        role(args, report, path)
        unknown_args(args, {"name", "points", "role"}, "shape", report, path)
        if name and ok:
            ctx.exposed.state["items"][name] = arr = [tuple(p) for p in pts]
            inside(ctx, report, path, name, arr)

    def apply(ctx, report: Report, path: str, names: list[str], m: Mat, whole: bool) -> None:
        """names 按 m 变换（和 kit 一样：纯旋转走圆弧，其他矩阵走 (1−t)I + tM），途中按 16 步取样检查范围。"""
        state = ctx.exposed.state
        angle = rotation_angle(m)
        for n in names:
            p0 = state["items"][n]
            for k in range(1, 17):
                mk = rot(angle * k / 16) if angle is not None else lerp(m, k / 16)
                inside(ctx, report, path, n, act(mk, p0))
            state["items"][n] = act(m, p0)
        if whole:
            state["M"] = mul(m, state["M"])

    def rotate(args: dict, ctx, report: Report, path: str) -> None:
        names = old_names(args, ctx, report, path, False)
        a = args.get("angle")
        if not _num(a) or a == 0:
            report.error("SS281", f"{path}.args.angle", "rotate 需要 angle：度，逆时针为正，不为 0")
        label(args, report, path)
        if "trace" in args and _bool(args["trace"]):
            report.error("SS281", f"{path}.args.trace", "trace 应为 true / false")
        unknown_args(args, {"name", "angle", "label", "trace"}, "rotate", report, path)
        if names is not None and _num(a) and a:
            apply(ctx, report, path, names, rot(math.radians(a)), "name" not in args)

    def scale(args: dict, ctx, report: Report, path: str) -> None:
        names = old_names(args, ctx, report, path, False)
        by = args.get("by")
        if not _num(by) or by == 0:
            report.error("SS281", f"{path}.args.by", "scale 需要 by：放大几倍（不为 0 的数）")
        unknown_args(args, {"name", "by"}, "scale", report, path)
        if names is not None and _num(by) and by:
            apply(ctx, report, path, names, ((by, 0.0), (0.0, by)), "name" not in args)

    def warp(args: dict, ctx, report: Report, path: str) -> None:
        m = _matrix(args.get("matrix"))
        unknown_args(args, {"matrix"}, "warp", report, path)
        if m is None:
            report.error("SS281", f"{path}.args.matrix", "warp 需要 matrix：[[a, b], [c, d]]")
            return
        if abs(det(m)) < 1e-9:
            report.error("SS281", f"{path}.args.matrix", "矩阵的行列式是 0：整个平面压成一条线，画不出网格")
            return
        apply(ctx, report, path, old_names({}, ctx, report, path, False), m, True)

    def reset(args: dict, ctx, report: Report, path: str) -> None:
        unknown_args(args, set(), "reset", report, path)
        apply(ctx, report, path, old_names({}, ctx, report, path, False), inv(ctx.exposed.state["M"]), True)

    def relabel(args: dict, ctx, report: Report, path: str) -> None:
        names = old_names(args, ctx, report, path, True)
        if not isinstance(args.get("label"), str):
            report.error("SS281", f"{path}.args.label", "relabel 需要 label：新名字（公式，不加 $）")
        unknown_args(args, {"name", "label"}, "relabel", report, path)
        if names and len(names) != 1:
            report.error("SS281", f"{path}.args.name", "relabel 一次换一个名字")

    def remove(args: dict, ctx, report: Report, path: str) -> None:
        state = ctx.exposed.state
        names = old_names(args, ctx, report, path, False) if "name" in args else list(state["items"])  # 不写 = 全部，钉住的点也收
        unknown_args(args, {"name"}, "remove", report, path)
        for n in names or []:
            state["items"].pop(n, None)
            state["fixed"].discard(n)

    def validate(ctx, report: Report, path: str) -> None:
        d = ctx.definition
        labels = d.get("axis_labels")
        if labels is not None and _labels(labels):
            report.error("SS202", f"{path}.axis_labels", _labels(labels))

    registry["plane"] = Widget(
        "plane",
        params={"x": (True, _range), "y": (True, _range), "grid": (False, _bool), "numbers": (False, _bool),
                "complex": (False, _bool), "mesh": (False, _bool), "mesh_role": (False, _role),
                "axis_labels": (False, _labels)},
        expose=expose,
        actions={"vector": vector, "slide": slide, "point": point, "shape": shape, "rotate": rotate, "scale": scale,
                 "warp": warp, "reset": reset, "relabel": relabel, "remove": remove},
        validate=validate,
    )
