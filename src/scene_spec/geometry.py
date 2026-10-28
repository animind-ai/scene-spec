"""综合几何图（geometry）：点由构造算出、整支视频图不动；组件本身在 kit 的 mx/geometry.py。

这里有两样东西：
1. 构造求解器 solve()（纯 Python，不依赖 numpy）：按定义算出每个点、每个圆的坐标。kit 画图用的是同一份代码，
   所以检查器算出来的图和渲染出来的图一定一致；
2. 检查器 register()：参数和名字、构造是否退化（平行线求交、直线和圆不相交……）、断言（共圆、共线、等长、等角……）
   在数值上是否成立（误差 < 1e-6）、动作引用的名字是否存在。

写法见 kit 的 mx/geometry.py 文档字符串（同一份语法）。错误码：
- SS271 参数 / 定义写错（类型、缺字段、名字重复、引用不存在、循环引用）；
- SS272 构造退化（求交没有交点、两根时没说取哪个、三点共线作外心……）；
- SS273 断言不成立（数值误差超过 1e-6）；
- SS274 动作参数写错；
- SS275 点、圆伸出了图框 box。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

TOL = 1e-6  # 断言的容许误差
EPS = 1e-9  # 判退化（平行、相切）的阈值
POINT_DIRS = ("u", "d", "l", "r", "ul", "ur", "dl", "dr")
POINT_OPTS = {"label", "dir", "dot", "hidden", "role", "aux", "draw"}
CIRCLE_OPTS = {"hidden", "role", "aux", "dashed", "draw", "width"}
ELEMENT_KINDS = ("segment", "line", "ray", "polygon", "arc", "angle", "tick")
ELEMENT_OPTS = {"name", "role", "aux", "dashed", "hidden", "width", "fill", "radius", "arcs", "right", "count", "ccw",
                "label"}
ASSERT_KINDS = ("concyclic", "collinear", "equal", "equal_angle", "parallel", "perpendicular", "on", "concurrent")
PICK_KEYS = ("not", "near", "far", "index")
CONSTRUCTIONS = ("at", "on", "mid", "foot", "reflect", "meet", "circumcenter", "incenter", "centroid", "orthocenter",
                 "tangent")

Pt = tuple[float, float]


class GeoError(Exception):
    """构造或定义有问题。path 是相对组件定义的位置（例如 points.D），code 是 SS27x。"""

    def __init__(self, code: str, path: str, msg: str):
        super().__init__(msg)
        self.code, self.path, self.msg = code, path, msg


# ---------- 向量小工具 ----------

def sub(a: Pt, b: Pt) -> Pt:
    return (a[0] - b[0], a[1] - b[1])


def add(a: Pt, b: Pt) -> Pt:
    return (a[0] + b[0], a[1] + b[1])


def mul(a: Pt, s: float) -> Pt:
    return (a[0] * s, a[1] * s)


def dot(a: Pt, b: Pt) -> float:
    return a[0] * b[0] + a[1] * b[1]


def cross(a: Pt, b: Pt) -> float:
    return a[0] * b[1] - a[1] * b[0]


def norm(a: Pt) -> float:
    return math.hypot(a[0], a[1])


def dist(a: Pt, b: Pt) -> float:
    return norm(sub(a, b))


def unit(a: Pt) -> Pt:
    n = norm(a)
    return (a[0] / n, a[1] / n)


def angle_at(b: Pt, a: Pt, c: Pt) -> float:
    """∠BAC（弧度，0…π）。"""
    u, v = sub(b, a), sub(c, a)
    return math.atan2(abs(cross(u, v)), dot(u, v))


@dataclass(frozen=True)
class Line:
    """直线 p + s·d（d 不必是单位向量）。"""

    p: Pt
    d: Pt


@dataclass(frozen=True)
class Circle:
    c: Pt
    r: float


def circumcircle(a: Pt, b: Pt, c: Pt) -> Circle | None:
    d = 2 * cross(sub(b, a), sub(c, a))
    if abs(d) < EPS:
        return None
    ba, ca = sub(b, a), sub(c, a)
    bb, cc = dot(ba, ba), dot(ca, ca)
    ux = (ca[1] * bb - ba[1] * cc) / d
    uy = (ba[0] * cc - ca[0] * bb) / d
    center = (a[0] + ux, a[1] + uy)
    return Circle(center, dist(center, a))


def meet_lines(l1: Line, l2: Line) -> Pt | None:
    den = cross(l1.d, l2.d)
    if abs(den) < EPS * max(1.0, norm(l1.d) * norm(l2.d)):
        return None
    s = cross(sub(l2.p, l1.p), l2.d) / den
    return add(l1.p, mul(l1.d, s))


def meet_line_circle(ln: Line, c: Circle) -> list[Pt]:
    """按沿 d 方向的先后排序；相切时一个点。"""
    d = unit(ln.d)
    f = sub(ln.p, c.c)
    b = dot(f, d)
    disc = b * b - (dot(f, f) - c.r * c.r)
    if disc < -EPS:
        return []
    if abs(disc) <= EPS:
        return [add(ln.p, mul(d, -b))]
    s = math.sqrt(disc)
    return [add(ln.p, mul(d, -b - s)), add(ln.p, mul(d, -b + s))]


def meet_circles(c1: Circle, c2: Circle) -> list[Pt]:
    """第 0 个在 c1→c2 圆心连线的左边（逆时针一侧）；相切时一个点。"""
    d = dist(c1.c, c2.c)
    if d < EPS or d > c1.r + c2.r + EPS or d < abs(c1.r - c2.r) - EPS:
        return []
    a = (c1.r ** 2 - c2.r ** 2 + d * d) / (2 * d)
    h2 = c1.r ** 2 - a * a
    u = unit(sub(c2.c, c1.c))
    m = add(c1.c, mul(u, a))
    if h2 <= EPS:
        return [m]
    h = math.sqrt(h2)
    n = (-u[1], u[0])
    return [add(m, mul(n, h)), add(m, mul(n, -h))]


def foot(p: Pt, ln: Line) -> Pt:
    d = ln.d
    s = dot(sub(p, ln.p), d) / dot(d, d)
    return add(ln.p, mul(d, s))


# ---------- 求解 ----------

@dataclass
class Figure:
    points: dict[str, Pt] = field(default_factory=dict)
    circles: dict[str, Circle] = field(default_factory=dict)
    free: dict[str, str] = field(default_factory=dict)  # 可以 trace 的点 → "angle"（圆上）/ "t"（线段上）
    deps: dict[str, set[str]] = field(default_factory=dict)  # 点 / 圆 → 它直接或间接用到的点和圆


def _is_num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_pair(v: object) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(_is_num(x) for x in v)


class _Solver:
    def __init__(self, definition: dict, overrides: dict | None = None):
        self.pdefs = definition.get("points") or {}
        self.cdefs = definition.get("circles") or {}
        if not isinstance(self.pdefs, dict):
            raise GeoError("SS271", "points", "points 应为 名字: 定义 的字典")
        if not isinstance(self.cdefs, dict):
            raise GeoError("SS271", "circles", "circles 应为 名字: 定义 的字典")
        both = set(self.pdefs) & set(self.cdefs)
        if both:
            raise GeoError("SS271", "circles", f"{'、'.join(sorted(both))} 既是点又是圆：名字要不同")
        self.fig = Figure()
        self.overrides = overrides or {}
        self.stack: list[str] = []
        self.used: set[str] = set()  # 当前构造用到的名字（算依赖）

    def run(self) -> Figure:
        for name in self.pdefs:
            self.point(name)
        for name in self.cdefs:
            self.circle(name)
        return self.fig

    def _enter(self, name: str, path: str) -> None:
        if name in self.stack:
            raise GeoError("SS271", path, "循环引用：" + " → ".join(self.stack[self.stack.index(name):] + [name]))
        self.stack.append(name)

    def point(self, name: object, path: str | None = None) -> Pt:
        if not isinstance(name, str):
            raise GeoError("SS271", path or "points", f"这里应写一个点的名字，不是 {name!r}")
        self.used.add(name)
        if name in self.fig.points:
            self.used |= self.fig.deps.get(name, set())
            return self.fig.points[name]
        if name not in self.pdefs:
            raise GeoError("SS271", path or f"points.{name}", f"没有点 {name}（points 里有 {'、'.join(self.pdefs) or '无'}）")
        here = f"points.{name}"
        self._enter(name, here)
        outer = self.used
        self.used = set()
        p = self._construct(name, self.pdefs[name], here)
        self.fig.deps[name] = self.used
        self.used = outer | self.used
        self.stack.pop()
        self.fig.points[name] = p
        return p

    def circle(self, name: object, path: str | None = None) -> Circle:
        if not isinstance(name, str):
            raise GeoError("SS271", path or "circles", f"这里应写一个圆的名字，不是 {name!r}")
        self.used.add(name)
        if name in self.fig.circles:
            self.used |= self.fig.deps.get(name, set())
            return self.fig.circles[name]
        if name not in self.cdefs:
            raise GeoError("SS271", path or f"circles.{name}", f"没有圆 {name}（circles 里有 {'、'.join(self.cdefs) or '无'}）")
        here = f"circles.{name}"
        self._enter(name, here)
        outer = self.used
        self.used = set()
        d = self.cdefs[name]
        if not isinstance(d, dict):
            raise GeoError("SS271", here, "圆写成 {center: O, radius: r} / {center: O, through: A} / {through: [A, B, C]} / {diameter: [A, B]}")
        _unknown(d, {"center", "radius", "through", "diameter"} | CIRCLE_OPTS, here)
        if "diameter" in d:
            a, b = self._two(d["diameter"], f"{here}.diameter")
            c = Circle(mul(add(a, b), 0.5), dist(a, b) / 2)
        elif "center" in d and "radius" in d:
            if not (_is_num(d["radius"]) and d["radius"] > 0):
                raise GeoError("SS271", f"{here}.radius", "radius 应为正数")
            c = Circle(self.point(d["center"], f"{here}.center"), float(d["radius"]))
        elif "center" in d and "through" in d:
            o = self.point(d["center"], f"{here}.center")
            c = Circle(o, dist(o, self.point(d["through"], f"{here}.through")))
        elif isinstance(d.get("through"), list) and len(d["through"]) == 3:
            a, b, cc = (self.point(n, f"{here}.through") for n in d["through"])
            got = circumcircle(a, b, cc)
            if got is None:
                raise GeoError("SS272", f"{here}.through", "三点共线，没有过这三点的圆")
            c = got
        else:
            raise GeoError("SS271", here, "圆写成 {center: O, radius: r} / {center: O, through: A} / {through: [A, B, C]} / {diameter: [A, B]}")
        if c.r < EPS:
            raise GeoError("SS272", here, "半径是 0")
        self.fig.deps[name] = self.used
        self.used = outer | self.used
        self.stack.pop()
        self.fig.circles[name] = c
        return c

    def _two(self, v: object, path: str) -> tuple[Pt, Pt]:
        if not (isinstance(v, list) and len(v) == 2):
            raise GeoError("SS271", path, "应为两个点的名字 [A, B]")
        return self.point(v[0], path), self.point(v[1], path)

    def _three(self, v: object, path: str) -> tuple[Pt, Pt, Pt]:
        if not (isinstance(v, list) and len(v) == 3):
            raise GeoError("SS271", path, "应为三个点的名字 [A, B, C]")
        a, b, c = (self.point(n, path) for n in v)
        if abs(cross(sub(b, a), sub(c, a))) < EPS:
            raise GeoError("SS272", path, f"{'、'.join(v)} 三点共线，不是三角形")
        return a, b, c

    def _construct(self, name: str, d: object, path: str) -> Pt:
        if _is_pair(d):
            return (float(d[0]), float(d[1]))
        if not isinstance(d, dict):
            raise GeoError("SS271", path, "点写成 [x, y]，或一个构造 {mid: [A, B]}、{meet: [...], pick}……")
        kinds = [k for k in CONSTRUCTIONS if k in d]
        if len(kinds) != 1:
            raise GeoError("SS271", path, f"点要恰好有一种构造（{' / '.join(CONSTRUCTIONS)}），现在是 {kinds or '无'}")
        kind = kinds[0]
        extra = {"at": set(), "on": {"angle", "t"}, "mid": set(), "foot": {"to"}, "reflect": {"over"},
                 "meet": set(PICK_KEYS), "circumcenter": set(), "incenter": set(), "centroid": set(),
                 "orthocenter": set(), "tangent": {"circle"} | set(PICK_KEYS)}[kind]
        _unknown(d, {kind} | extra | POINT_OPTS, path)
        v = d[kind]
        kp = f"{path}.{kind}"
        if kind == "at":
            if not _is_pair(v):
                raise GeoError("SS271", kp, "at 应为 [x, y]")
            return (float(v[0]), float(v[1]))
        if kind == "on":
            if isinstance(v, str):  # 圆上，按极角（度）
                if not _is_num(d.get("angle")):
                    raise GeoError("SS271", f"{path}.angle", "圆上的点要写 angle：从圆心看的方向角（度，逆时针，0 指向右）")
                c = self.circle(v, kp)
                a = math.radians(float(self.overrides.get(name, d["angle"])))
                self.fig.free[name] = "angle"
                return add(c.c, (c.r * math.cos(a), c.r * math.sin(a)))
            a, b = self._two(v, kp)
            if not _is_num(d.get("t")):
                raise GeoError("SS271", f"{path}.t", "线段上的点要写 t：A + t·(B − A)，0 在 A、1 在 B")
            self.fig.free[name] = "t"
            return add(a, mul(sub(b, a), float(self.overrides.get(name, d["t"]))))
        if kind == "mid":
            a, b = self._two(v, kp)
            return mul(add(a, b), 0.5)
        if kind == "foot":
            p = self.point(v, kp)
            return foot(p, self.line(d.get("to"), f"{path}.to"))
        if kind == "reflect":
            p = self.point(v, kp)
            over = d.get("over")
            if isinstance(over, str):
                o = self.point(over, f"{path}.over")
                return sub(mul(o, 2), p)
            f = foot(p, self.line(over, f"{path}.over"))
            return sub(mul(f, 2), p)
        if kind in ("circumcenter", "incenter", "centroid", "orthocenter"):
            a, b, c = self._three(v, kp)
            if kind == "centroid":
                return ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3)
            if kind == "circumcenter":
                return circumcircle(a, b, c).c  # type: ignore[union-attr]
            if kind == "orthocenter":
                o = circumcircle(a, b, c).c  # type: ignore[union-attr]
                return sub(add(add(a, b), c), mul(o, 2))  # H = A + B + C − 2O
            la, lb, lc = dist(b, c), dist(c, a), dist(a, b)
            s = la + lb + lc
            return ((la * a[0] + lb * b[0] + lc * c[0]) / s, (la * a[1] + lb * b[1] + lc * c[1]) / s)
        if kind == "meet":
            if not (isinstance(v, list) and len(v) == 2):
                raise GeoError("SS271", kp, "meet 写两样东西：直线 [A, B] / {through, perp | parallel} / {tangent_at, circle}，或圆的名字")
            objs = [self._curve(x, f"{kp}[{i}]") for i, x in enumerate(v)]
            lines = [o for o in objs if isinstance(o, Line)]
            if len(lines) == 2:
                p = meet_lines(*lines)
                if p is None:
                    raise GeoError("SS272", kp, "两条直线平行（或重合），没有交点")
                return p
            if len(lines) == 1:
                circ = next(o for o in objs if isinstance(o, Circle))
                roots = meet_line_circle(lines[0], circ)
                what = "直线和圆"
            else:
                roots = meet_circles(*objs)  # type: ignore[arg-type]
                what = "两圆"
            return self._pick(roots, d, path, what)
        # tangent：从 P 向圆作切线的切点
        p = self.point(v, kp)
        c = self.circle(d.get("circle"), f"{path}.circle")
        dd = dist(p, c.c)
        if dd < c.r - EPS:
            raise GeoError("SS272", kp, "点在圆内，作不出切线")
        if abs(dd - c.r) <= EPS:
            return p
        # 切点 = 以 PO 为直径的圆和原圆的交点；第 0 个：从 P 看圆心，在左边那条切线上
        roots = meet_circles(Circle(mul(add(p, c.c), 0.5), dd / 2), c)
        return self._pick(roots, d, path, "切点")

    def _pick(self, roots: list[Pt], d: dict, path: str, what: str) -> Pt:
        if not roots:
            raise GeoError("SS272", path, f"{what}没有交点")
        picks = [k for k in PICK_KEYS if k in d]
        if len(roots) == 1:
            return roots[0]
        if len(picks) != 1:
            raise GeoError("SS272", path, f"{what}有两个交点：写 not: A（取不是 A 的那个）、near: P / far: P（离 P 近 / 远的那个）或 index: 0 / 1 中的一个")
        k = picks[0]
        if k == "index":
            if d["index"] not in (0, 1):
                raise GeoError("SS271", f"{path}.index", "index 应为 0 或 1（直线和圆：沿直线方向的先后；两圆：圆心连线左边的是 0；切点：从点看圆心左边的是 0）")
            return roots[d["index"]]
        ref = self.point(d[k], f"{path}.{k}")
        ds = [dist(r, ref) for r in roots]
        if k == "not":
            if min(ds) > 1e-6:
                raise GeoError("SS272", f"{path}.not", f"{d[k]} 不是这两个交点之一，not 选不出来")
            return roots[1] if ds[0] < ds[1] else roots[0]
        if abs(ds[0] - ds[1]) < 1e-9:
            raise GeoError("SS272", f"{path}.{k}", f"两个交点离 {d[k]} 一样远，{k} 选不出来")
        closer = 0 if ds[0] < ds[1] else 1
        return roots[closer if k == "near" else 1 - closer]

    def _curve(self, spec: object, path: str) -> Line | Circle:
        if isinstance(spec, str):
            return self.circle(spec, path)
        return self.line(spec, path)

    def line(self, spec: object, path: str) -> Line:
        if isinstance(spec, list):
            a, b = self._two(spec, path)
            if dist(a, b) < EPS:
                raise GeoError("SS272", path, f"{spec[0]}、{spec[1]} 重合，定不出直线")
            return Line(a, sub(b, a))
        if isinstance(spec, dict):
            if "tangent_at" in spec:
                _unknown(spec, {"tangent_at", "circle"}, path)
                p = self.point(spec["tangent_at"], f"{path}.tangent_at")
                c = self.circle(spec.get("circle"), f"{path}.circle")
                if abs(dist(p, c.c) - c.r) > TOL:
                    raise GeoError("SS272", f"{path}.tangent_at", f"{spec['tangent_at']} 不在圆 {spec.get('circle')} 上")
                r = sub(p, c.c)
                return Line(p, (-r[1], r[0]))
            if "through" in spec:
                _unknown(spec, {"through", "perp", "parallel"}, path)
                p = self.point(spec["through"], f"{path}.through")
                if ("perp" in spec) == ("parallel" in spec):
                    raise GeoError("SS271", path, "{through: P, perp: [A, B]} 或 {through: P, parallel: [A, B]}，二选一")
                key = "perp" if "perp" in spec else "parallel"
                base = self.line(spec[key], f"{path}.{key}")
                return Line(p, (-base.d[1], base.d[0]) if key == "perp" else base.d)
        raise GeoError("SS271", path, "直线写成 [A, B]、{through: P, perp: [A, B]}、{through: P, parallel: [A, B]} 或 {tangent_at: A, circle: c}")


def _unknown(d: dict, allowed: set[str], path: str) -> None:
    extra = sorted(set(d) - allowed)
    if extra:
        raise GeoError("SS271", f"{path}.{extra[0]}", f"不认识的字段 {'、'.join(extra)}（可用：{'、'.join(sorted(allowed))}）")


def solve(definition: dict, overrides: dict | None = None) -> Figure:
    """按定义算出所有点和圆。overrides：{点名: angle 或 t}，trace 时换掉自由点的参数。出错抛 GeoError。"""
    return _Solver(definition, overrides).run()


def line_of(fig: Figure, definition: dict, spec: object, path: str) -> Line:
    """在已解出的图上解析一条直线（元素里的 line 用）。"""
    s = _Solver(definition)
    s.fig = fig
    return s.line(spec, path)


# ---------- 元素 ----------

@dataclass
class Element:
    name: str
    kind: str  # point / circle / segment / line / ray / polygon / arc / angle / tick
    spec: object  # 点名、圆名、点名列表、直线定义、{circle, from, to}
    opts: dict
    path: str


def _default_name(kind: str, spec: object) -> str | None:
    if kind in ("segment", "polygon") and isinstance(spec, list) and all(isinstance(n, str) for n in spec):
        return "".join(spec)
    if kind in ("line", "ray", "tick") and isinstance(spec, list) and all(isinstance(n, str) for n in spec):
        return f"{kind}_{''.join(spec)}"
    if kind == "angle" and isinstance(spec, list) and all(isinstance(n, str) for n in spec):
        return "ang_" + "".join(spec)
    if kind == "arc" and isinstance(spec, dict) and isinstance(spec.get("from"), str) and isinstance(spec.get("to"), str):
        return f"arc_{spec['from']}{spec['to']}"
    return None


def elements(definition: dict) -> list[Element]:
    """组件里画的全部东西（按画的先后）：先是圆、再是 draw 列表、最后是点（点和名字画在最上面）。"""
    out: list[Element] = []
    for name, d in (definition.get("circles") or {}).items():
        opts = d if isinstance(d, dict) else {}
        if opts.get("draw", True) is not False:
            out.append(Element(name, "circle", name, opts, f"circles.{name}"))
    draw = definition.get("draw") or []
    if not isinstance(draw, list):
        raise GeoError("SS271", "draw", "draw 应为列表：每项一个 {segment | line | ray | polygon | arc | angle | tick: …}")
    for i, d in enumerate(draw):
        path = f"draw[{i}]"
        if not isinstance(d, dict):
            raise GeoError("SS271", path, "每项写成 {segment: [A, B]} 这样的字典")
        kinds = [k for k in ELEMENT_KINDS if k in d]
        if len(kinds) != 1:
            raise GeoError("SS271", path, f"每项恰好一种：{' / '.join(ELEMENT_KINDS)}（现在是 {kinds or '无'}）")
        kind = kinds[0]
        _unknown(d, {kind} | ELEMENT_OPTS, path)
        name = d.get("name") or _default_name(kind, d[kind])
        if not isinstance(name, str) or not name:
            raise GeoError("SS271", path, "这一项要写 name（名字，之后 show / shade 按它找）")
        out.append(Element(name, kind, d[kind], d, path))
    for name, d in (definition.get("points") or {}).items():
        opts = d if isinstance(d, dict) else {}
        if opts.get("draw", True) is False:  # 只用来构造的点：不画、不算进图框（同圆的 draw: false）
            continue
        out.append(Element(name, "point", name, opts, f"points.{name}"))
    seen: dict[str, str] = {}
    for e in out:
        if not _ident(e.name):
            raise GeoError("SS271", e.path, f"名字 {e.name!r} 只能用字母、数字、下划线，且不以数字开头（选择器 fig.{e.name} 要用）")
        if e.name in seen:
            raise GeoError("SS271", e.path, f"名字 {e.name} 和 {seen[e.name]} 重复：给其中一个写 name")
        seen[e.name] = e.path
    return out


def _ident(s: str) -> bool:
    return bool(s) and (s[0].isalpha() or s[0] == "_") and all(ch.isalnum() and ch.isascii() or ch == "_" for ch in s)


def element_points(fig: Figure, definition: dict, e: Element) -> list[Pt]:
    """检查元素引用、返回它的关键点（检查图框用）；有问题抛 GeoError。"""
    o = e.opts
    for key in ("role",):
        if key in o and o[key] not in ROLES:
            raise GeoError("SS271", f"{e.path}.{key}", f"role 应为 {'/'.join(ROLES)} 之一")
    for key in ("aux", "dashed", "hidden", "fill", "ccw", "dot", "draw"):
        if key in o and not isinstance(o[key], bool):
            raise GeoError("SS271", f"{e.path}.{key}", f"{key} 应为 true / false")
    if "width" in o and not (_is_num(o["width"]) and o["width"] > 0):
        raise GeoError("SS271", f"{e.path}.width", "width 应为正数（线宽，1080p 像素）")
    if e.kind == "point":
        if "dir" in o and o["dir"] not in POINT_DIRS:
            raise GeoError("SS271", f"{e.path}.dir", f"dir 应为 {' / '.join(POINT_DIRS)} 之一")
        if "label" in o and not isinstance(o["label"], str):
            raise GeoError("SS271", f"{e.path}.label", "label 应为字符串（公式，不加 $；空串不写名字）")
        return [fig.points[e.name]]
    if e.kind == "circle":
        c = fig.circles[e.name]
        return [(c.c[0] - c.r, c.c[1] - c.r), (c.c[0] + c.r, c.c[1] + c.r)]
    s = e.spec

    def pts(names: object, n: int | None, what: str) -> list[Pt]:
        ok = isinstance(names, list) and all(isinstance(x, str) for x in names) and (n is None or len(names) == n)
        if not ok or (n is None and len(names) < 3):
            raise GeoError("SS271", f"{e.path}.{e.kind}", what)
        missing = [x for x in names if x not in fig.points]
        if missing:
            raise GeoError("SS271", f"{e.path}.{e.kind}", f"没有点 {'、'.join(missing)}")
        return [fig.points[x] for x in names]

    if e.kind == "segment":
        out = pts(s, 2, "segment 写两个点 [A, B]")
        if dist(*out) < EPS:
            raise GeoError("SS272", e.path, "线段两端重合")
        return out
    if e.kind == "tick":
        out = pts(s, 2, "tick 写两个点 [A, B]（等长记号画在线段 AB 中点）")
        if "count" in o and o["count"] not in (1, 2, 3):
            raise GeoError("SS271", f"{e.path}.count", "count 应为 1 / 2 / 3（几道短线）")
        return out
    if e.kind == "polygon":
        return pts(s, None, "polygon 写至少三个点 [A, B, C, …]")
    if e.kind in ("line", "ray"):
        if e.kind == "ray":
            return pts(s, 2, "ray 写两个点 [A, B]（从 A 出发经过 B）")
        line_of(fig, definition, s, f"{e.path}.line")
        return []
    if e.kind == "arc":
        if not (isinstance(s, dict) and set(s) <= {"circle", "from", "to"} and {"circle", "from", "to"} <= set(s)):
            raise GeoError("SS271", f"{e.path}.arc", "arc 写成 {circle: c, from: B, to: C}（从 B 逆时针到 C；ccw: false 顺时针）")
        if s["circle"] not in fig.circles:
            raise GeoError("SS271", f"{e.path}.arc.circle", f"没有圆 {s['circle']}")
        c = fig.circles[s["circle"]]
        out = []
        for key in ("from", "to"):
            if s[key] not in fig.points:
                raise GeoError("SS271", f"{e.path}.arc.{key}", f"没有点 {s[key]}")
            p = fig.points[s[key]]
            if abs(dist(p, c.c) - c.r) > TOL:
                raise GeoError("SS272", f"{e.path}.arc.{key}", f"{s[key]} 不在圆 {s['circle']} 上")
            out.append(p)
        return out
    # angle
    b, a, c = pts(s, 3, "angle 写三个点 [B, A, C]：顶点在中间，量从射线 AB 到射线 AC 的角")
    if dist(a, b) < EPS or dist(a, c) < EPS:
        raise GeoError("SS272", e.path, "角的边退化（顶点和另一点重合）")
    if "arcs" in o and o["arcs"] not in (1, 2, 3):
        raise GeoError("SS271", f"{e.path}.arcs", "arcs 应为 1 / 2 / 3（等角记号的弧线条数）")
    if "radius" in o and not (_is_num(o["radius"]) and o["radius"] > 0):
        raise GeoError("SS271", f"{e.path}.radius", "radius 应为正数（数学单位）")
    if "right" in o and not isinstance(o["right"], bool):
        raise GeoError("SS271", f"{e.path}.right", "right 应为 true / false（不写时 90° 自动画直角方块）")
    if o.get("right") is True and abs(angle_at(b, a, c) - math.pi / 2) > TOL:
        raise GeoError("SS273", f"{e.path}.right", f"画了直角记号，但 ∠{''.join(s)} = {math.degrees(angle_at(b, a, c)):.6f}°")
    return [a]


ROLES = ("FG", "A", "B", "C", "HL", "NO", "DIM")


# ---------- 断言 ----------

def check_asserts(fig: Figure, definition: dict, where: str = "") -> list[tuple[str, str]]:
    """断言逐条验算，返回 [(路径, 问题)]。where 附在问题后面（trace 途中的位置）。"""
    out: list[tuple[str, str]] = []
    items = definition.get("assert") or []
    if not isinstance(items, list):
        return [("assert", "assert 应为列表")]
    scale = _scale(fig)
    for i, a in enumerate(items):
        path = f"assert[{i}]"
        try:
            msg = _assert_one(fig, a, path, scale)
        except GeoError as err:
            out.append((err.path, err.msg))
            continue
        if msg:
            out.append((path, msg + where))
    return out


def _scale(fig: Figure) -> float:
    pts = list(fig.points.values())
    if len(pts) < 2:
        return 1.0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return max(1.0, max(xs) - min(xs), max(ys) - min(ys))


def _names(fig: Figure, v: object, n: int | None, path: str, what: str) -> list[Pt]:
    if not (isinstance(v, list) and all(isinstance(x, str) for x in v) and (len(v) == n if n else len(v) >= 3)):
        raise GeoError("SS271", path, what)
    missing = [x for x in v if x not in fig.points]
    if missing:
        raise GeoError("SS271", path, f"没有点 {'、'.join(missing)}")
    return [fig.points[x] for x in v]


def _pairs(v: object, path: str, k: int, what: str) -> list:
    if not (isinstance(v, list) and len(v) >= 2):
        raise GeoError("SS271", path, what)
    return v


def _assert_one(fig: Figure, a: object, path: str, scale: float) -> str | None:
    if not isinstance(a, dict) or len(a) != 1 or next(iter(a)) not in ASSERT_KINDS:
        raise GeoError("SS271", path, f"每条断言写成 {{种类: …}}，种类是 {' / '.join(ASSERT_KINDS)} 之一")
    kind, v = next(iter(a.items()))
    kp = f"{path}.{kind}"
    if kind == "collinear":
        ps = _names(fig, v, None, kp, "collinear 写至少三个点")
        a0, b0 = ps[0], max(ps[1:], key=lambda p: dist(p, ps[0]))
        d = unit(sub(b0, a0))
        worst = max(abs(cross(d, sub(p, a0))) for p in ps)
        return f"{'、'.join(v)} 不共线：偏离 {worst:.3g}" if worst > TOL * scale else None
    if kind == "concyclic":
        ps = _names(fig, v, None, kp, "concyclic 写至少四个点")
        if len(ps) < 4:
            raise GeoError("SS271", kp, "concyclic 写至少四个点")
        c = circumcircle(*ps[:3])
        if c is None:
            return f"{'、'.join(v[:3])} 共线，谈不上共圆"
        worst = max(abs(dist(p, c.c) - c.r) for p in ps[3:])
        return f"{'、'.join(v)} 不共圆：偏离 {worst:.3g}" if worst > TOL * scale else None
    if kind == "on":
        if not (isinstance(v, list) and len(v) == 2 and v[0] in fig.points and v[1] in fig.circles):
            raise GeoError("SS271", kp, "on 写 [点, 圆]")
        c = fig.circles[v[1]]
        off = abs(dist(fig.points[v[0]], c.c) - c.r)
        return f"{v[0]} 不在圆 {v[1]} 上：偏离 {off:.3g}" if off > TOL * scale else None
    if kind == "equal":
        segs = _pairs(v, kp, 2, "equal 写至少两条线段 [[A, B], [C, D]]")
        ls = [dist(*_names(fig, s, 2, kp, "equal 的每条线段写两个点")) for s in segs]
        spread = max(ls) - min(ls)
        txt = "、".join(f"{''.join(s)}={x:.6g}" for s, x in zip(segs, ls))
        return f"长度不相等：{txt}" if spread > TOL * scale else None
    if kind == "equal_angle":
        angs = _pairs(v, kp, 3, "equal_angle 写至少两个角 [[B, A, C], [E, D, F]]")
        vals = [angle_at(*_names(fig, s, 3, kp, "equal_angle 的每个角写三个点，顶点在中间")) for s in angs]
        spread = max(vals) - min(vals)
        txt = "、".join(f"∠{''.join(s)}={math.degrees(x):.6g}°" for s, x in zip(angs, vals))
        return f"角不相等：{txt}" if spread > TOL else None
    if kind in ("parallel", "perpendicular"):
        ls = _pairs(v, kp, 2, f"{kind} 写两条直线 [[A, B], [C, D]]")
        if len(ls) != 2:
            raise GeoError("SS271", kp, f"{kind} 写两条直线 [[A, B], [C, D]]")
        (a1, b1), (a2, b2) = (_names(fig, s, 2, kp, "每条直线写两个点") for s in ls)
        u, w = unit(sub(b1, a1)), unit(sub(b2, a2))
        off = abs(cross(u, w)) if kind == "parallel" else abs(dot(u, w))
        word = "不平行" if kind == "parallel" else "不垂直"
        return f"{''.join(ls[0])}、{''.join(ls[1])} {word}：偏离 {off:.3g}" if off > TOL else None
    # concurrent
    ls = _pairs(v, kp, 2, "concurrent 写至少三条直线 [[A, B], [C, D], [E, F]]")
    if len(ls) < 3:
        raise GeoError("SS271", kp, "concurrent 写至少三条直线")
    lines = [Line(p, sub(q, p)) for p, q in (_names(fig, s, 2, kp, "每条直线写两个点") for s in ls)]
    x = meet_lines(lines[0], lines[1])
    if x is None:
        return "前两条直线平行，谈不上共点"
    worst = max(abs(cross(unit(ln.d), sub(x, ln.p))) for ln in lines[2:])
    return f"{'、'.join(''.join(s) for s in ls)} 不共点：偏离 {worst:.3g}" if worst > TOL * scale else None


# ---------- 图框 ----------

def figure_box(fig: Figure, definition: dict, els: list[Element]) -> tuple[float, float, float, float]:
    """box 写了就用它；没写时取所有画出来的点、圆的包围盒，四周留 0.6。"""
    box = definition.get("box")
    if isinstance(box, list) and len(box) == 4 and all(_is_num(x) for x in box):
        return tuple(float(x) for x in box)  # type: ignore[return-value]
    xs, ys = [], []
    for e in els:
        for p in element_points(fig, definition, e):
            xs.append(p[0])
            ys.append(p[1])
    if not xs:
        return (-3.0, -3.0, 3.0, 3.0)
    m = 0.6
    return (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)


# ---------- 检查器 ----------

def register(registry: dict, Widget, Exposed, unknown_args) -> None:  # noqa: N803
    def solved(definition: dict) -> tuple[Figure, list[Element]] | None:
        try:
            fig = solve(definition)
            els = elements(definition)
            for e in els:
                element_points(fig, definition, e)
            return fig, els
        except GeoError:
            return None

    def expose(definition: dict, data: dict) -> Exposed:
        got = solved(definition)
        names = [e.name for e in got[1]] if got else []
        free = dict(got[0].free) if got else {}
        return Exposed(parts={n: 1 for n in names}, items=len(names) or None,
                       state={"names": set(names), "free": free})

    def validate(ctx, report, path: str) -> None:
        d = ctx.definition
        box = d.get("box")
        if box is not None and not (isinstance(box, list) and len(box) == 4 and all(_is_num(x) for x in box)
                                    and box[0] < box[2] and box[1] < box[3]):
            report.error("SS271", f"{path}.box", "box 应为 [x0, y0, x1, y1]（图框，数学坐标；直线裁在框里）")
            box = None
        try:
            fig = solve(d)
            els = elements(d)
            pts_all = [(e, element_points(fig, d, e)) for e in els]
        except GeoError as err:
            (report.error(err.code, f"{path}.{err.path}", err.msg))
            return
        for p, msg in check_asserts(fig, d):
            report.error("SS273", f"{path}.{p}", msg)
        if box is not None:
            for e, pts in pts_all:
                for p in pts:
                    if p[0] < box[0] - EPS or p[0] > box[2] + EPS or p[1] < box[1] - EPS or p[1] > box[3] + EPS:
                        report.error("SS275", f"{path}.{e.path}", f"{e.name} 伸到 ({p[0]:.3g}, {p[1]:.3g})，出了图框 box {box}")
                        break

    def names_arg(args: dict, ctx, report, path: str, key: str = "name", required: bool = True) -> list[str]:
        v = args.get(key)
        if v is None:
            if required:
                report.error("SS274", f"{path}.args", f"需要 {key}：一个名字或名字列表")
            return []
        names = [v] if isinstance(v, str) else v
        if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
            report.error("SS274", f"{path}.args.{key}", f"{key} 应为名字或名字列表")
            return []
        known = ctx.exposed.state.get("names", set())
        missing = [n for n in names if n not in known]
        if missing:
            report.error("SS274", f"{path}.args.{key}", f"图里没有 {'、'.join(missing)}（有 {'、'.join(sorted(known)) or '无'}）")
        return names

    def role_arg(args: dict, report, path: str) -> None:
        if "role" in args and args["role"] not in ROLES:
            report.error("SS274", f"{path}.args.role", f"role 应为 {'/'.join(ROLES)} 之一")

    def simple(act: str, extra: set[str] = frozenset(), required: bool = True):
        def check(args: dict, ctx, report, path: str) -> None:
            names_arg(args, ctx, report, path, required=required)
            role_arg(args, report, path)
            unknown_args(args, {"name"} | set(extra), act, report, path)
        return check

    def kinds_of(ctx) -> dict[str, str]:
        try:
            return {e.name: e.kind for e in elements(ctx.definition)}
        except GeoError:
            return {}

    def shade(args: dict, ctx, report, path: str) -> None:
        names = names_arg(args, ctx, report, path)
        role_arg(args, report, path)
        unknown_args(args, {"name", "role"}, "shade", report, path)
        kinds = kinds_of(ctx)
        bad = [n for n in names if kinds.get(n) not in (None, "angle", "polygon", "circle")]
        if bad:
            report.error("SS274", f"{path}.args.name", f"shade 只涂角、多边形和圆（{'、'.join(bad)} 不是）")

    def dim(args: dict, ctx, report, path: str) -> None:
        if ("name" in args) == ("except" in args):
            report.error("SS274", f"{path}.args", "dim 写 name（调淡这些）或 except（除了这些都调淡），二选一")
        names_arg(args, ctx, report, path, "name", required=False)
        names_arg(args, ctx, report, path, "except", required=False)
        unknown_args(args, {"name", "except"}, "dim", report, path)

    def trace(args: dict, ctx, report, path: str) -> None:
        unknown_args(args, {"point", "to"}, "trace", report, path)
        p = args.get("point")
        free = ctx.exposed.state.get("free", {})
        if p not in free:
            report.error("SS274", f"{path}.args.point", f"trace 的 point 要是圆上 {{on: c, angle}} 或线段上 {{on: [A, B], t}} 的点（可以动的有 {'、'.join(free) or '无'}）")
            return
        to = args.get("to")
        if not _is_num(to):
            report.error("SS274", f"{path}.args.to", "trace 需要 to：圆上的点写目标角（度），线段上的点写目标 t")
            return
        # 一路上（16 步取样）构造不能退化、断言要一直成立
        d = ctx.definition
        start = float((d.get("points") or {})[p].get("angle" if free[p] == "angle" else "t"))
        start = ctx.exposed.state.setdefault("at", {}).get(p, start)
        for k in range(1, 17):
            v = start + (float(to) - start) * k / 16
            try:
                fig = solve(d, {p: v})
            except GeoError as err:
                report.error("SS272", f"{path}.args.to", f"{p} 滑到 {v:.3g} 时构造退化：{err.msg}")
                return
            for ap, msg in check_asserts(fig, d, f"（{p} 在 {v:.3g}）"):
                report.error("SS273", f"{path}.args.to", f"{ap}：{msg}")
                return
        ctx.exposed.state["at"][p] = float(to)

    registry["geometry"] = Widget(
        "geometry",
        params={"points": (True, lambda v: None if isinstance(v, dict) and v else "应为 名字: 定义 的字典（至少一个点）"),
                "circles": (False, lambda v: None if isinstance(v, dict) else "应为 名字: 定义 的字典"),
                "draw": (False, lambda v: None if isinstance(v, list) else "应为列表"),
                "assert": (False, lambda v: None if isinstance(v, list) else "应为列表"),
                "box": (False, lambda v: None),
                "label_size": (False, lambda v: None if _is_num(v) and v > 0 else "应为正数")},
        expose=expose,
        actions={"draw": simple("draw"), "remove": simple("remove"), "shade": shade, "unshade": simple("unshade"),
                 "ring": simple("ring", {"role"}), "unring": simple("unring"), "highlight": simple("highlight", {"role"}),
                 "dim": dim, "restore": simple("restore", required=False), "trace": trace},
        validate=validate,
    )
