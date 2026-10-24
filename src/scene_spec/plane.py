"""坐标平面（plane）的检查：向量、复平面乘 i、矩阵变形。组件本身在 kit 的 mx/plane.py。

按动作顺序推演平面上有哪些东西（名字 → 数学坐标）和到目前为止的整体变换，检查：
- 参数和动作参数的类型；名字不重复、引用的名字存在；
- 每个东西在每个动作之后都还在坐标范围 x、y 里（伸出去会盖住刻度、出了组件排版时预留的框），SS262；
  直线（line）是无穷长的，画的时候裁在坐标范围里：只要求它一直穿过坐标范围；
- segment / line 是线段和直线：线段两端、直线上的一点和方向都跟着 rotate / scale / warp / reset 变换，
  所以特征向量方向上的直线（span）在 warp 时一直盖着那支特征向量；
- highlight / unhighlight 的名字存在，不重复高亮、不取消没高亮的；
- warp 的矩阵不能是奇异的（整个平面压成一条线，网格画不出来），SS281；path: flip（翻面）只用于行列式为负的矩阵；
- curves（数据曲线、参数曲线）和沿曲线走的 points：引用的 data 存在、点列合规、整条曲线在坐标范围里，
  progress / at 在 [0, 1] 里（SS490–SS499，见 curves.py）；有 curves 的平面不能整体 rotate / scale / warp / reset
  （曲线不跟着变换），SS496；
- matrix（参数驱动的变形）：[[a, b], [c, d]]，每一项是数或参数表达式；整个平面（网格、箭头、点、多边形，钉住的点除外）
  再按它变形，tween 参数时平面连续地跟着变（行列式、矩阵元素的读数用 readout 对象）。参数取每组关键值时
  这个矩阵都不能是奇异的（SS411）；不能和 curves 同时写（曲线不跟着变换，SS496）。
"""

from __future__ import annotations

import math

from . import curves as C
from . import expr
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


def _entries(fields: tuple[str, ...], what: str):
    def check(value: object) -> str | None:
        if not isinstance(value, list) or not value:
            return f"应为非空列表，每项是{what}"
        for n, entry in enumerate(value):
            if not isinstance(entry, dict):
                return f"第 {n} 项应为映射：{what}"
            extra = set(entry) - set(fields)
            if extra:
                return f"第 {n} 项有不认识的字段 {sorted(extra)}（可用：{', '.join(fields)}）"
        return None

    return check


_curves = _entries(C.CURVE_FIELDS, "{data: 键} 或 {x: \"x(t)\", y: \"y(t)\", domain: [t0, t1]}，可加 progress、along、role")
_points = _entries(C.POINT_FIELDS, "沿曲线走的点 {curve: i, at: 0 到 1, label?, role?, dir?}")


def _live_matrix(value: object) -> str | None:
    ok = (isinstance(value, list) and len(value) == 2
          and all(isinstance(r, list) and len(r) == 2 and all(_num(x) or (isinstance(x, str) and x.strip()) for x in r) for r in value))
    return None if ok else "应为 [[a, b], [c, d]]：每一项是数或参数表达式（字符串）"


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


def crosses(p: tuple[float, float], d: tuple[float, float], b: tuple[float, float, float, float]) -> bool:
    """直线 p + s·d 是否穿过矩形 b（x0, y0, x1, y1），只碰到一个角不算。"""
    lo, hi = -math.inf, math.inf
    for k, (a, c) in enumerate(((b[0], b[2]), (b[1], b[3]))):
        if abs(d[k]) < 1e-12:
            if not a - 1e-9 <= p[k] <= c + 1e-9:
                return False
            continue
        s0, s1 = (a - p[k]) / d[k], (c - p[k]) / d[k]
        lo, hi = max(lo, min(s0, s1)), min(hi, max(s0, s1))
    return hi - lo > 1e-9


def polar_flip(m: Mat) -> tuple[Mat, tuple[float, float]]:
    """行列式为负的 m = Q S：S = sqrt(mᵀm) 是对称正定的伸缩，Q 是沿直线 u 的镜面反射。返回 (S, u)。"""
    a = mul(((m[0][0], m[1][0]), (m[0][1], m[1][1])), m)  # mᵀm
    r = math.sqrt(det(a))
    k = math.sqrt(a[0][0] + a[1][1] + 2 * r)
    S = (((a[0][0] + r) / k, a[0][1] / k), (a[1][0] / k, (a[1][1] + r) / k))
    q = mul(m, inv(S))  # [[cos φ, sin φ], [sin φ, −cos φ]]：沿 φ/2 方向的直线反射
    half = math.atan2(q[1][0], q[0][0]) / 2
    return S, (math.cos(half), math.sin(half))


def flip_at(S: Mat, u: tuple[float, float], t: float) -> Mat:
    """翻面路径的第 t（0 到 1）处：前一半按 (1−s)I + sS 伸缩，后一半绕镜面直线 u 在空中转半圈
    （正投影到平面上：uuᵀ + cos θ (I − uuᵀ)，θ 从 0 到 π）。"""
    if t <= 0.5:
        return lerp(S, 2 * t)
    c = math.cos(math.pi * (2 * t - 1))
    uu = ((u[0] * u[0], u[0] * u[1]), (u[1] * u[0], u[1] * u[1]))
    F = tuple(tuple(uu[i][j] + c * (EYE[i][j] - uu[i][j]) for j in range(2)) for i in range(2))
    return mul(F, S)  # type: ignore[arg-type]


def register(registry: dict, Widget, Exposed, unknown_args) -> None:  # noqa: N803
    def expose(definition: dict, data: dict) -> Exposed:
        n = {k: len(v) if isinstance(v := definition.get(k), list) else 0 for k in ("curves", "points")}
        return Exposed(parts={"axes": 1, "grid": 1, "mesh": 1, "items": 1, "curve": n["curves"], "point": n["points"]},
                       state={"items": {}, "M": EYE, "fixed": set(), "kinds": {}, "lit": set()})

    def box(ctx):
        x, y = ctx.definition.get("x"), ctx.definition.get("y")
        if _range(x) or _range(y):
            return None
        return x[0], y[0], x[1], y[1]

    def inside(ctx, report: Report, path: str, name: str, pts: list[tuple[float, float]]) -> None:
        b = box(ctx)
        if b is None:
            return
        if ctx.exposed.state["kinds"].get(name) == "line":
            (px, py), (qx, qy) = pts
            if not crosses((px, py), (qx - px, qy - py), b):
                report.error("SS262", path, f"直线 {name} 不经过坐标范围 x {[b[0], b[2]]}、y {[b[1], b[3]]}")
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
            ctx.exposed.state["kinds"][name] = "vector"
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
        if len(old) != 2 or ctx.exposed.state["kinds"].get(names[0], "vector") != "vector":
            report.error("SS281", f"{path}.args.name", f"{names[0]} 不是箭头")
            return
        pts = [(at[0], at[1]), (at[0] + old[1][0] - old[0][0], at[1] + old[1][1] - old[0][1])]
        if copy:
            items[copy] = pts
            ctx.exposed.state["kinds"][copy] = "vector"
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
        label(args, report, path)
        if "fill" in args and _bool(args["fill"]):
            report.error("SS281", f"{path}.args.fill", "fill 应为 true / false（false 只描边）")
        unknown_args(args, {"name", "points", "role", "label", "fill"}, "shape", report, path)
        if name and ok:
            ctx.exposed.state["items"][name] = arr = [tuple(p) for p in pts]
            inside(ctx, report, path, name, arr)

    def segment(args: dict, ctx, report: Report, path: str) -> None:
        name = new_name(args, "name", ctx, report, path)
        a, b = args.get("from"), args.get("to")
        ok = _pair(a) and _pair(b)
        if not ok:
            report.error("SS281", f"{path}.args", "segment 需要 from、to：两端 [x, y]")
        elif a == b:
            report.error("SS281", f"{path}.args.to", "segment 的两端重合")
            ok = False
        lines_common(args, report, path, "segment", {"name", "from", "to"})
        if name and ok:
            ctx.exposed.state["items"][name] = pts = [tuple(a), tuple(b)]
            ctx.exposed.state["kinds"][name] = "segment"
            inside(ctx, report, path, name, pts)

    def line(args: dict, ctx, report: Report, path: str) -> None:
        """直线：dir（方向，through 是线上一点，默认原点 = span）或 eq: [p, q, r]（p x + q y = r）。"""
        name = new_name(args, "name", ctx, report, path)
        pts = line_points(args, report, path)
        lines_common(args, report, path, "line", {"name", "dir", "through", "eq"})
        if name and pts:
            ctx.exposed.state["items"][name] = pts
            ctx.exposed.state["kinds"][name] = "line"
            inside(ctx, report, path, name, pts)

    def lines_common(args: dict, report: Report, path: str, act: str, own: set[str]) -> None:
        role(args, report, path)
        label(args, report, path)
        if "dashed" in args and _bool(args["dashed"]):
            report.error("SS281", f"{path}.args.dashed", "dashed 应为 true / false")
        if "side" in args and args["side"] not in ("l", "r"):
            report.error("SS281", f"{path}.args.side", "side 应为 l / r（名字在线的左边或右边，顺着方向看）")
        if "along" in args and not (_num(args["along"]) and 0 <= args["along"] <= 1):
            report.error("SS281", f"{path}.args.along", "along 应为 0 到 1 的数（名字挨着画出来的那段线的哪一处）")
        unknown_args(args, own | {"role", "label", "dashed", "side", "along"}, act, report, path)

    def line_points(args: dict, report: Report, path: str) -> list[tuple[float, float]] | None:
        if ("eq" in args) == ("dir" in args):
            report.error("SS281", f"{path}.args", "line 写 dir: [dx, dy]（可加 through: [x, y]，默认过原点）或 eq: [p, q, r]（p x + q y = r），二选一")
            return None
        if "eq" in args:
            eq = args["eq"]
            if "through" in args:
                report.error("SS281", f"{path}.args.through", "eq 已经定下直线，不再写 through")
            if not (isinstance(eq, list) and len(eq) == 3 and all(_num(x) for x in eq) and (eq[0] or eq[1])):
                report.error("SS281", f"{path}.args.eq", "eq 应为 [p, q, r]：p x + q y = r，p、q 不同时为 0")
                return None
            p, q, r = (float(x) for x in eq)
            n2 = p * p + q * q
            base = (p * r / n2, q * r / n2)  # 离原点最近的点
            return [base, (base[0] - q, base[1] + p)]
        d, at = args.get("dir"), args.get("through", [0, 0])
        if not _pair(d) or not (d[0] or d[1]):
            report.error("SS281", f"{path}.args.dir", "dir 应为 [dx, dy]：直线的方向，不为零向量")
            return None
        if not _pair(at):
            report.error("SS281", f"{path}.args.through", "through 应为 [x, y]：直线经过的一点")
            return None
        return [(float(at[0]), float(at[1])), (at[0] + d[0], at[1] + d[1])]

    def apply(ctx, report: Report, path: str, names: list[str], m: Mat, whole: bool, how: str = "lerp") -> None:
        """names 按 m 变换（和 kit 一样：纯旋转走圆弧，其他矩阵走 (1−t)I + tM），途中按 16 步取样检查范围。"""
        state = ctx.exposed.state
        if whole and ctx.definition.get("curves"):
            report.error("SS496", path, "这个平面有 curves：曲线和沿曲线走的点不跟着整体变换，"
                         "不能整体 rotate / scale / warp / reset（写 name 只转、只缩放某几个东西）")
            return
        angle = rotation_angle(m)
        flip = polar_flip(m) if how == "flip" else None
        for n in names:
            p0 = state["items"][n]
            for k in range(1, 17):
                if flip is not None:
                    mk = flip_at(*flip, k / 16)
                else:
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
        unknown_args(args, {"matrix", "path"}, "warp", report, path)
        if m is None:
            report.error("SS281", f"{path}.args.matrix", "warp 需要 matrix：[[a, b], [c, d]]")
            return
        if abs(det(m)) < 1e-9:
            report.error("SS281", f"{path}.args.matrix", "矩阵的行列式是 0：整个平面压成一条线，画不出网格")
            return
        how = args.get("path", "lerp")
        if how not in ("lerp", "flip"):
            report.error("SS281", f"{path}.args.path", "path 应为 lerp（默认：(1−t)I + tM）/ flip（先伸缩，再沿镜面直线翻面）")
            return
        if how == "flip" and det(m) > 0:
            report.error("SS281", f"{path}.args.path", "path: flip 用于行列式为负的矩阵（带反射）；行列式为正的矩阵用默认的 lerp")
            return
        apply(ctx, report, path, old_names({}, ctx, report, path, False), m, True, how)

    def reset(args: dict, ctx, report: Report, path: str) -> None:
        unknown_args(args, {"path"}, "reset", report, path)
        m = inv(ctx.exposed.state["M"])
        how = args.get("path", "lerp")
        if how not in ("lerp", "flip") or (how == "flip" and det(m) > 0):
            report.error("SS281", f"{path}.args.path", "reset 的 path: flip 只在现在的变换带反射（行列式为负）时用；否则不写")
            return
        apply(ctx, report, path, old_names({}, ctx, report, path, False), m, True, how)

    def relabel(args: dict, ctx, report: Report, path: str) -> None:
        names = old_names(args, ctx, report, path, True)
        if not isinstance(args.get("label"), str):
            report.error("SS281", f"{path}.args.label", "relabel 需要 label：新名字（公式，不加 $）")
        unknown_args(args, {"name", "label"}, "relabel", report, path)
        if names and len(names) != 1:
            report.error("SS281", f"{path}.args.name", "relabel 一次换一个名字")

    def highlight(args: dict, ctx, report: Report, path: str) -> None:
        """highlight {name, pulse?}：给平面上的东西加一圈同色光晕、描边加粗（取代 mark 的金色方块）。"""
        names = old_names(args, ctx, report, path, True)
        if "pulse" in args and _bool(args["pulse"]):
            report.error("SS281", f"{path}.args.pulse", "pulse 应为 true / false（光晕亮起时跳两下）")
        unknown_args(args, {"name", "pulse"}, "highlight", report, path)
        lit = ctx.exposed.state["lit"]
        for n in names or []:
            if n in lit:
                report.error("SS281", f"{path}.args.name", f"{n} 已经高亮了（先 unhighlight）")
            lit.add(n)

    def unhighlight(args: dict, ctx, report: Report, path: str) -> None:
        lit = ctx.exposed.state["lit"]
        unknown_args(args, {"name"}, "unhighlight", report, path)
        if "name" not in args:
            lit.clear()
            return
        for n in old_names(args, ctx, report, path, True) or []:
            if n not in lit:
                report.error("SS281", f"{path}.args.name", f"{n} 没有高亮")
            lit.discard(n)

    def remove(args: dict, ctx, report: Report, path: str) -> None:
        state = ctx.exposed.state
        names = old_names(args, ctx, report, path, False) if "name" in args else list(state["items"])  # 不写 = 全部，钉住的点也收
        unknown_args(args, {"name"}, "remove", report, path)
        for n in names or []:
            state["items"].pop(n, None)
            state["kinds"].pop(n, None)
            state["fixed"].discard(n)
            state["lit"].discard(n)

    def check_live_matrix(ctx, report: Report, path: str) -> None:
        """matrix 的每一项能解析；参数取每组关键值时矩阵不奇异；不和 curves 同时写。"""
        if ctx.definition.get("curves"):
            report.error("SS496", path, "这个平面有 curves：曲线不跟着变形，不能再写参数驱动的 matrix")
        ex = ctx.ex
        trees = []
        for i, row in enumerate(ctx.definition["matrix"]):
            for j, v in enumerate(row):
                if _num(v):
                    trees.append(("num", float(v)))
                    continue
                if ex is None:
                    report.error("SS402", f"{path}[{i}][{j}]", f"{v!r}：场景没有声明 params，矩阵元素只能写数")
                    return
                tree = ex.parse(v, f"{path}[{i}][{j}]")
                if tree is None:
                    return
                trees.append(tree)
        for env in (ex.states_for(ctx.obj_id) if ex is not None else [{}]):
            a, b_, c, d = (expr.evaluate(t, math.nan, env) for t in trees)
            if not all(math.isfinite(v) for v in (a, b_, c, d)):
                report.error("SS411", path, f"参数取 {ex.describe(env)} 时矩阵有一项没有定义")
                return
            if abs(a * d - b_ * c) < 1e-9:
                report.error("SS411", path, f"参数取 {ex.describe(env)} 时矩阵的行列式是 0：整个平面压成一条线，画不出网格")
                return

    def validate(ctx, report: Report, path: str) -> None:
        d = ctx.definition
        labels = d.get("axis_labels")
        if labels is not None and _labels(labels):
            report.error("SS202", f"{path}.axis_labels", _labels(labels))
        b = box(ctx)
        if "matrix" in d and _live_matrix(d["matrix"]) is None:
            check_live_matrix(ctx, report, f"{path}.matrix")
        cs = d.get("curves") if _curves(d.get("curves")) is None else []
        for n, entry in enumerate(cs):
            cpath = f"{path}.curves[{n}]"
            if "data" in entry:
                stray = [k for k in ("x", "y", "domain") if k in entry]
                if stray:
                    report.error("SS496", cpath, f"数据曲线不写 {'、'.join(stray)}（参数曲线才写 x、y、domain）")
                C.check_data(entry, cpath, ctx.data, b, report)
            else:
                C.check_parametric(entry, cpath, ctx.ex, ctx.obj_id, b, report)
            C.check_common(entry, cpath, ctx.ex, ctx.obj_id, report)
            if "role" in entry and _role(entry["role"]):
                report.error("SS202", f"{cpath}.role", _role(entry["role"]))
        ps = d.get("points") if _points(d.get("points")) is None else []
        for n, entry in enumerate(ps):
            ppath = f"{path}.points[{n}]"
            k = entry.get("curve")
            if not (isinstance(k, int) and not isinstance(k, bool) and 0 <= k < len(cs)):
                report.error("SS496", f"{ppath}.curve", f"curve 应为 0 到 {len(cs) - 1} 的整数（第几条曲线，从 0 数）"
                             if cs else "这个平面没有 curves，点没有曲线可走")
            if "at" not in entry:
                report.error("SS496", ppath, "沿曲线走的点需要 at：在曲线上的位置，0 起点 … 1 终点（数或参数表达式）")
            else:
                C.check_fraction(entry["at"], f"{ppath}.at", ctx.ex, ctx.obj_id, report, "at")
            if "dir" in entry and entry["dir"] not in POINT_DIRS:
                report.error("SS202", f"{ppath}.dir", f"dir 应为 {' / '.join(POINT_DIRS)} 之一")
            if "role" in entry and _role(entry["role"]):
                report.error("SS202", f"{ppath}.role", _role(entry["role"]))
            if "label" in entry and not isinstance(entry["label"], str):
                report.error("SS202", f"{ppath}.label", "label 应为字符串（公式，不加 $）")

    registry["plane"] = Widget(
        "plane",
        params={"x": (True, _range), "y": (True, _range), "grid": (False, _bool), "axes": (False, _bool), "numbers": (False, _bool),
                "complex": (False, _bool), "mesh": (False, _bool), "mesh_role": (False, _role),
                "axis_labels": (False, _labels), "curves": (False, _curves), "points": (False, _points),
                "matrix": (False, _live_matrix), "allow_empty": (False, _bool)},
        expose=expose,
        actions={"vector": vector, "slide": slide, "point": point, "shape": shape, "segment": segment, "line": line,
                 "rotate": rotate, "scale": scale, "warp": warp, "reset": reset, "relabel": relabel,
                 "highlight": highlight, "unhighlight": unhighlight, "remove": remove},
        validate=validate,
    )
