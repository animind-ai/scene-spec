"""剖分组件 dissect：图形剪开、刚体移动、拼成另一个图形（规划 §2 的 #4 #5 #11 #12 #13 #17 #18 #20 #21 #23 #29 #37）。

这里放两样东西，kit 渲染时直接复用，保证检查器和渲染器算的是同一份几何：

1. 纯几何（不依赖 numpy）：多边形按直线 / 折线切成若干块（平面剖分 + 找面）、把一条边吸附到另一条边的
   刚体变换、扇形交错排列、几块拼起来的外轮廓；
2. 检查：参数是否成立（多边形退化、切线没切开、名字重复……），以及动作按时间顺序引用的块当时是否存在。

坐标约定：对象里写的所有坐标都是"图形坐标"（y 向上，单位任意，kit 按画面自动缩放）。
每一块记住自己"出生时"的坐标（剪出来的块就是被剪那块的原坐标）；动作里 edge / vertex 用块的原坐标点名，
其余坐标（shift 的 to、rotate 的 about、flip 的 axis）是当前的图形坐标。

错误码 SS420–SS439（见设计稿 §6.6）。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

Pt = tuple[float, float]
EPS = 1e-7
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ARC_STEP = 3.0  # 扇形算面积、重心、外轮廓时，弧按每 3° 一段折线近似（画图时用三次贝塞尔）
LAYOUTS = ("alternate",)
GUIDE_SIDES = ("above", "below", "left", "right")


# ---------- 仿射变换（2×3，x' = a x + b y + c，y' = d x + e y + f）----------

@dataclass(frozen=True)
class Aff:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 0.0
    e: float = 1.0
    f: float = 0.0

    def __call__(self, p: Pt) -> Pt:
        return (self.a * p[0] + self.b * p[1] + self.c, self.d * p[0] + self.e * p[1] + self.f)

    def __matmul__(self, o: Aff) -> Aff:
        return Aff(
            self.a * o.a + self.b * o.d, self.a * o.b + self.b * o.e, self.a * o.c + self.b * o.f + self.c,
            self.d * o.a + self.e * o.d, self.d * o.b + self.e * o.e, self.d * o.c + self.e * o.f + self.f,
        )

    @property
    def det(self) -> float:
        return self.a * self.e - self.b * self.d

    @property
    def angle(self) -> float:
        """旋转角（度）；对反射也给出 (a, d) 列向量的方向。"""
        return math.degrees(math.atan2(self.d, self.a))

    def rows(self) -> list[list[float]]:
        return [[self.a, self.b, self.c], [self.d, self.e, self.f], [0.0, 0.0, 1.0]]


def translate(dx: float, dy: float) -> Aff:
    return Aff(c=dx, f=dy)


def rotate(degrees: float, about: Pt = (0.0, 0.0)) -> Aff:
    r = math.radians(degrees)
    c, s = math.cos(r), math.sin(r)
    x, y = about
    return Aff(c, -s, x - c * x + s * y, s, c, y - s * x - c * y)


def reflect(p: Pt, q: Pt) -> Aff:
    """关于直线 pq 的反射。"""
    ux, uy = q[0] - p[0], q[1] - p[1]
    n = math.hypot(ux, uy)
    ux, uy = ux / n, uy / n
    a, b, e = 2 * ux * ux - 1, 2 * ux * uy, 2 * uy * uy - 1
    m = Aff(a, b, 0.0, b, e, 0.0)
    x, y = m(p)
    return Aff(a, b, p[0] - x, b, e, p[1] - y)


def edge_map(p0: Pt, p1: Pt, q0: Pt, q1: Pt) -> Aff:
    """把线段 p0→p1 刚体移动（旋转 + 平移，不翻面）到 q0→q1。长度要相等，调用方负责检查。"""
    ang = math.degrees(math.atan2(q1[1] - q0[1], q1[0] - q0[0]) - math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
    r = rotate(ang)
    x, y = r(p0)
    return translate(q0[0] - x, q0[1] - y) @ r


def dist(p: Pt, q: Pt) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])


def same(p: Pt, q: Pt, eps: float = 1e-6) -> bool:
    return dist(p, q) <= eps


# ---------- 多边形工具 ----------

def signed_area(poly: list[Pt]) -> float:
    n = len(poly)
    return sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n)) / 2


def centroid(poly: list[Pt]) -> Pt:
    a = signed_area(poly)
    if abs(a) < 1e-12:
        return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))
    n = len(poly)
    cx = cy = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        w = x0 * y1 - x1 * y0
        cx += (x0 + x1) * w
        cy += (y0 + y1) * w
    return (cx / (6 * a), cy / (6 * a))


def _cross(o: Pt, a: Pt, b: Pt) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def on_segment(p: Pt, a: Pt, b: Pt, eps: float = 1e-7) -> bool:
    if dist(a, b) < eps:
        return same(p, a, eps)
    if abs(_cross(a, b, p)) / dist(a, b) > eps:
        return False
    t = ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / dist(a, b) ** 2
    return -eps <= t <= 1 + eps


def point_in_polygon(p: Pt, poly: list[Pt]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        if (y0 > p[1]) != (y1 > p[1]):
            x = x0 + (p[1] - y0) * (x1 - x0) / (y1 - y0)
            if x > p[0]:
                inside = not inside
    return inside


def simplify(poly: list[Pt]) -> list[Pt]:
    """去掉重复点和共线的中间点。"""
    pts = [p for i, p in enumerate(poly) if not same(p, poly[i - 1], 1e-9)]
    changed = True
    while changed and len(pts) > 3:
        changed = False
        for i in range(len(pts)):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            if abs(_cross(a, b, c)) < 1e-9 * max(1.0, dist(a, c)):
                del pts[i]
                changed = True
                break
    return pts


def self_intersects(poly: list[Pt]) -> bool:
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or j == (i + 1) % n:
                continue
            c, d = poly[j], poly[(j + 1) % n]
            if _segments_cross(a, b, c, d):
                return True
    return False


def _segments_cross(a: Pt, b: Pt, c: Pt, d: Pt) -> bool:
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    if ((d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS)) and ((d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS)):
        return True
    return any(on_segment(p, s, t) for p, s, t in ((a, c, d), (b, c, d), (c, a, b), (d, a, b)))


def _intersection(a: Pt, b: Pt, c: Pt, d: Pt) -> Pt | None:
    """两条线段的交点（不平行时）；不相交返回 None。"""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / den
    u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return (a[0] + t * rx, a[1] + t * ry)
    return None


class _Points:
    """按容差合并的点表：坐标相差不到 eps 的看成同一个点。"""

    def __init__(self, eps: float = 1e-7):
        self.eps, self.pts = eps, []

    def key(self, p: Pt) -> int:
        for i, q in enumerate(self.pts):
            if same(p, q, self.eps):
                return i
        self.pts.append(p)
        return len(self.pts) - 1


def split_polygon(poly: list[Pt], cut: list[Pt], infinite: bool = False) -> tuple[list[list[Pt]], list[tuple[Pt, Pt]]]:
    """把简单多边形 poly 沿折线 cut 切开。infinite=True 时 cut 是过两点的整条直线。

    做法：多边形的边和切线放在一起做平面剖分（两两求交、在交点处断开），去掉落在多边形外面的切线段、
    以及一头悬空的切线段（切到一半停在里面的不算切开），剩下的图里每个有界的面就是一块。
    返回 (各块的顶点表（逆时针，去掉共线点）, 实际起作用的切口线段)。只得到一块说明没切开。
    """
    if signed_area(poly) < 0:
        poly = poly[::-1]
    if infinite:
        (x0, y0), (x1, y1) = cut[0], cut[1]
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        span = (max(xs) - min(xs) + max(ys) - min(ys) + 1) * 4
        n = dist(cut[0], cut[1])
        ux, uy = (x1 - x0) / n, (y1 - y0) / n
        cut = [(x0 - ux * span, y0 - uy * span), (x0 + ux * span, y0 + uy * span)]
    segments: list[tuple[Pt, Pt, bool]] = [(poly[i], poly[(i + 1) % len(poly)], False) for i in range(len(poly))]
    segments += [(cut[i], cut[i + 1], True) for i in range(len(cut) - 1) if not same(cut[i], cut[i + 1])]
    stops: list[list[Pt]] = [[s[0], s[1]] for s in segments]
    for i, (a, b, _) in enumerate(segments):
        for j in range(i + 1, len(segments)):
            c, d, _ = segments[j]
            x = _intersection(a, b, c, d)
            if x is not None:
                stops[i].append(x)
                stops[j].append(x)
            for p in (c, d):
                if on_segment(p, a, b):
                    stops[i].append(p)
            for p in (a, b):
                if on_segment(p, c, d):
                    stops[j].append(p)
    table = _Points()
    edges: dict[frozenset[int], bool] = {}  # 无向边 → 是不是切线
    for (a, b, is_cut), pts in zip(segments, stops):
        length = dist(a, b)
        pts = sorted(pts, key=lambda p: dist(a, p) / length)
        for p, q in zip(pts, pts[1:]):
            i, j = table.key(p), table.key(q)
            if i == j:
                continue
            key = frozenset((i, j))
            if is_cut:
                mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
                on_boundary = any(on_segment(mid, poly[k], poly[(k + 1) % len(poly)]) for k in range(len(poly)))
                if on_boundary or not point_in_polygon(mid, poly):
                    continue
                edges.setdefault(key, True)
            else:
                edges[key] = False
    # 去掉悬空的切线段（一头的度为 1）
    changed = True
    while changed:
        changed = False
        degree: dict[int, int] = {}
        for key in edges:
            for v in key:
                degree[v] = degree.get(v, 0) + 1
        for key in [k for k, is_cut in edges.items() if is_cut and any(degree[v] == 1 for v in k)]:
            del edges[key]
            changed = True
    pts = table.pts
    neighbours: dict[int, list[int]] = {}
    for key in edges:
        i, j = tuple(key)
        neighbours.setdefault(i, []).append(j)
        neighbours.setdefault(j, []).append(i)
    for v, ns in neighbours.items():
        ns.sort(key=lambda w: math.atan2(pts[w][1] - pts[v][1], pts[w][0] - pts[v][0]))
    used: set[tuple[int, int]] = set()
    faces: list[list[Pt]] = []
    for key in edges:
        for u, v in (tuple(key), tuple(key)[::-1]):
            if (u, v) in used:
                continue
            face, a, b = [], u, v
            while (a, b) not in used:
                used.add((a, b))
                face.append(pts[a])
                ns = neighbours[b]
                k = ns.index(a)
                a, b = b, ns[k - 1]  # 到 b 后，从来路方向顺时针转到的下一条边：面始终在左手边
            if signed_area(face) > 1e-9:
                faces.append(simplify(face))
    cuts = [(pts[tuple(k)[0]], pts[tuple(k)[1]]) for k, is_cut in edges.items() if is_cut]
    return faces, cuts


# ---------- 块 ----------

@dataclass
class Piece:
    name: str
    kind: str  # poly | sector | dots
    points: list[Pt]  # poly：逆时针顶点；dots：各点；sector：[圆心]
    r: float = 0.0
    a0: float = 0.0  # sector：起止角（度，逆时针），整圆是 a0..a0+360
    a1: float = 0.0
    born: str | None = None  # 由哪个 cut / copy 产生；None 是一开始就有的
    hidden: bool = False  # 一开始的块：先藏着，等 show obj#块名 时再出现

    @property
    def full(self) -> bool:
        return self.kind == "sector" and abs(self.a1 - self.a0 - 360) < 1e-9

    def vertices(self) -> list[Pt]:
        """可以被 vertex / edge 点名的点：多边形顶点；扇形的圆心和弧的两端；点阵的各点。"""
        if self.kind == "sector":
            if self.full:
                return [self.points[0]]
            c = self.points[0]
            return [c, polar(c, self.r, self.a0), polar(c, self.r, self.a1)]
        return list(self.points)

    def edges(self) -> list[tuple[Pt, Pt]]:
        """直边（首尾相接）：多边形的边；扇形的两条半径（圆心→弧起点，弧终点→圆心）。"""
        if self.kind == "poly":
            n = len(self.points)
            return [(self.points[i], self.points[(i + 1) % n]) for i in range(n)]
        if self.kind == "sector" and not self.full:
            c, p, q = self.vertices()
            return [(c, p), (q, c)]
        return []

    def outline(self) -> list[Pt]:
        """轮廓折线（扇形的弧按 ARC_STEP 取点）；点阵返回各点。"""
        if self.kind != "sector":
            return list(self.points)
        c = self.points[0]
        steps = max(2, math.ceil((self.a1 - self.a0) / ARC_STEP))
        arc = [polar(c, self.r, self.a0 + (self.a1 - self.a0) * k / steps) for k in range(steps + 1)]
        return arc[:-1] if self.full else [c, *arc]

    def area(self) -> float:
        if self.kind == "dots":
            return 0.0
        if self.kind == "sector":
            return math.pi * self.r ** 2 * (self.a1 - self.a0) / 360
        return abs(signed_area(self.points))

    def center(self) -> Pt:
        pts = self.outline()
        if self.kind == "dots":
            return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        return centroid(pts)

    def find_edge(self, p: Pt, q: Pt) -> tuple[Pt, Pt] | None:
        """p、q 是不是这块的一条边（两个方向都算）；是就返回按 p→q 方向的端点。"""
        for a, b in self.edges():
            if (same(a, p) and same(b, q)) or (same(a, q) and same(b, p)):
                return (p, q)
        return None

    def has_vertex(self, p: Pt) -> bool:
        return any(same(v, p) for v in self.vertices())


def polar(c: Pt, r: float, degrees: float) -> Pt:
    t = math.radians(degrees)
    return (c[0] + r * math.cos(t), c[1] + r * math.sin(t))


def order_by_position(pieces: list[list[Pt]]) -> list[int]:
    """切出来的块怎么对上 into 里的名字：按重心从左到右，横坐标相同的从下到上。"""
    centers = [centroid(p) if len(p) > 2 else p[0] for p in pieces]
    return sorted(range(len(pieces)), key=lambda i: (round(centers[i][0], 6), round(centers[i][1], 6)))


# ---------- 拼起来的外轮廓 ----------

def union_outline(polys: list[list[Pt]], eps: float = 1e-6) -> list[tuple[Pt, Pt]]:
    """几块拼在一起后的外轮廓线段：每块的边在别的块的顶点处断开，两块共有的边（方向相反）抵消。"""
    segs = [(p[i], p[(i + 1) % len(p)]) for p in polys for i in range(len(p))]
    verts = [v for p in polys for v in p]
    pieces: list[tuple[Pt, Pt]] = []
    for a, b in segs:
        stops = [a, b] + [v for v in verts if on_segment(v, a, b, eps) and not same(v, a, eps) and not same(v, b, eps)]
        length = dist(a, b)
        stops.sort(key=lambda p: dist(a, p) / length)
        pieces += [(p, q) for p, q in zip(stops, stops[1:]) if not same(p, q, eps)]
    table = _Points(eps * 10)
    count: dict[frozenset[int], int] = {}
    keyed = []
    for p, q in pieces:
        key = frozenset((table.key(p), table.key(q)))
        count[key] = count.get(key, 0) + 1
        keyed.append((key, p, q))
    return [(p, q) for key, p, q in keyed if count[key] == 1]


# ---------- 扇形交错排列（圆面积 #13）----------

def alternate_poses(sectors: list[Piece], at: Pt | None = None) -> list[Aff]:
    """n 个扇形（按角度顺序、拼成一个圆）交错排成一排，一个尖朝上、一个尖朝下，相邻两块共用一条半径。

    第 0 块尖朝上（弧在下），以后每块用"左边那条半径"吸附到前一块"右边那条半径"上、尖和弧端互换。
    整排的中心放在 at（默认圆心）。n 越大，越接近长 πr、宽 r 的长方形。
    """
    poses: list[Aff] = []
    first = sectors[0]
    c = first.points[0]
    mid = (first.a0 + first.a1) / 2
    poses.append(rotate(-90 - mid, c))
    for k in range(1, len(sectors)):
        prev, cur = sectors[k - 1], sectors[k]
        pose = poses[-1]
        up = k % 2 == 1  # 前一块尖朝上？
        # 前一块右边的半径（图形坐标里从尖到弧端）：尖朝上的是终边，尖朝下的是始边
        tip, end = pose(prev.points[0]), pose(polar(prev.points[0], prev.r, prev.a1 if up else prev.a0))
        # 这一块左边的半径：尖朝下的是终边，尖朝上的是始边；它的尖落在前一块的弧端
        cc = cur.points[0]
        arc = polar(cc, cur.r, cur.a1 if up else cur.a0)
        poses.append(edge_map(cc, arc, end, tip))
    pts = [pose(p) for pose, s in zip(poses, sectors) for p in s.outline()]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    target = at if at is not None else c
    dx, dy = target[0] - (min(xs) + max(xs)) / 2, target[1] - (min(ys) + max(ys)) / 2
    return [translate(dx, dy) @ p for p in poses]


# ---------- 读定义：所有块、切法、复制、参考线、合并 ----------

@dataclass
class Cut:
    name: str
    piece: str
    into: list[str]
    lines: list[tuple[Pt, Pt]] = field(default_factory=list)  # 切口线段（被切那块的原坐标），画虚线用
    sectors: int = 0


@dataclass
class Plan:
    pieces: dict[str, Piece] = field(default_factory=dict)
    initial: list[str] = field(default_factory=list)
    cuts: dict[str, Cut] = field(default_factory=dict)
    copies: dict[str, str] = field(default_factory=dict)
    guides: dict[str, dict] = field(default_factory=dict)
    merges: dict[str, dict] = field(default_factory=dict)
    styles: dict[str, dict] = field(default_factory=dict)  # 块名 → {role, label, edges}
    problems: list[tuple[str, str, str]] = field(default_factory=list)  # (代码, 相对路径, 说明)
    declared: set[str] = field(default_factory=set)  # 声明过的所有名字（定义有错的也算，免得引用处再连带报错）

    def names(self) -> set[str]:
        return set(self.pieces) | set(self.guides) | set(self.merges) | self.declared

    def error(self, code: str, path: str, message: str) -> None:
        self.problems.append((code, path, message))


def _pt(v: object) -> Pt | None:
    if (isinstance(v, list) and len(v) == 2
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)):
        return (float(v[0]), float(v[1]))
    return None


def _pts(v: object, at_least: int) -> list[Pt] | None:
    if not isinstance(v, list) or len(v) < at_least:
        return None
    pts = [_pt(x) for x in v]
    return None if any(p is None for p in pts) else pts  # type: ignore[return-value]


def _num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


SHAPE_KINDS = ("polygon", "rect", "circle", "sector", "dots")
STYLE_KEYS = {"role", "label", "edges"}
ROLES = ("FG", "A", "B", "C", "HL", "NO", "DIM")


def _shape(name: str, spec: object, plan: Plan, path: str) -> Piece | None:
    if not isinstance(spec, dict):
        plan.error("SS420", path, "每个图形是一个映射，例如 {polygon: [[0,0],[4,0],[5,2],[1,2]]}")
        return None
    kinds = [k for k in SHAPE_KINDS if k in spec]
    if len(kinds) != 1:
        plan.error("SS420", path, f"每个图形要写且只写 {' / '.join(SHAPE_KINDS)} 其中一个")
        return None
    extra = set(spec) - {*SHAPE_KINDS, "at", "hidden", *STYLE_KEYS}
    for key in sorted(extra):
        plan.error("SS420", f"{path}.{key}", f"图形没有字段 {key}")
    kind = kinds[0]
    v = spec[kind]
    at = (0.0, 0.0)
    if "at" in spec:
        at = _pt(spec["at"]) or at
        if _pt(spec["at"]) is None:
            plan.error("SS420", f"{path}.at", "at 应为 [x, y]")
    hidden = spec.get("hidden") is True
    if kind == "polygon":
        pts = _pts(v, 3)
        if pts is None:
            plan.error("SS420", f"{path}.polygon", "polygon 应为至少三个 [x, y] 顶点")
            return None
        pts = [(x + at[0], y + at[1]) for x, y in pts]
        if self_intersects(pts):
            plan.error("SS420", f"{path}.polygon", "多边形的边自相交")
            return None
        if abs(signed_area(pts)) < 1e-9:
            plan.error("SS420", f"{path}.polygon", "多边形面积为 0（顶点共线）")
            return None
        if signed_area(pts) < 0:
            pts = pts[::-1]
        return Piece(name, "poly", simplify(pts), hidden=hidden)
    if kind == "rect":
        if not (isinstance(v, list) and len(v) == 2 and all(_num(x) and x > 0 for x in v)):
            plan.error("SS420", f"{path}.rect", "rect 应为 [宽, 高]，都是正数（左下角在 at，默认原点）")
            return None
        w, h = float(v[0]), float(v[1])
        x, y = at
        return Piece(name, "poly", [(x, y), (x + w, y), (x + w, y + h), (x, y + h)], hidden=hidden)
    if kind == "circle":
        if not (_num(v) and v > 0):
            plan.error("SS420", f"{path}.circle", "circle 应为半径（正数），圆心在 at")
            return None
        return Piece(name, "sector", [at], r=float(v), a0=0.0, a1=360.0, hidden=hidden)
    if kind == "sector":
        ok = isinstance(v, dict) and set(v) <= {"r", "from", "to"} and _num(v.get("r")) and v["r"] > 0 \
            and _num(v.get("from")) and _num(v.get("to")) and 0 < v["to"] - v["from"] <= 360
        if not ok:
            plan.error("SS420", f"{path}.sector", "sector 应为 {r: 半径, from: 起始角, to: 终止角}（度，to - from 在 0 到 360 之间）")
            return None
        return Piece(name, "sector", [at], r=float(v["r"]), a0=float(v["from"]), a1=float(v["to"]), hidden=hidden)
    # dots：{rows: [每行几个点]}（阶梯点阵，从下往上、左端对齐）或 {points: [[x, y], ...]}
    if isinstance(v, dict) and set(v) == {"rows"} and isinstance(v["rows"], list) and v["rows"] \
            and all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in v["rows"]) and sum(v["rows"]) > 0:
        pts = [(at[0] + j, at[1] + i) for i, n in enumerate(v["rows"]) for j in range(n)]
    elif isinstance(v, dict) and set(v) == {"points"} and _pts(v["points"], 1):
        pts = [(x + at[0], y + at[1]) for x, y in _pts(v["points"], 1)]  # type: ignore[union-attr]
    else:
        plan.error("SS420", f"{path}.dots", "dots 应为 {rows: [1, 2, 3]}（阶梯点阵）或 {points: [[x, y], ...]}")
        return None
    return Piece(name, "dots", pts, hidden=hidden)


def _add_name(plan: Plan, name: object, path: str, taken: set[str]) -> bool:
    if not isinstance(name, str) or not NAME.match(name):
        plan.error("SS421", path, f"名字 {name!r} 不合法：要以字母或下划线开头，只含字母、数字、下划线（选择器写成 obj#名字）")
        return False
    if name in taken:
        plan.error("SS421", path, f"名字 {name} 重复（块、参考线、合并轮廓共用一个名字空间）")
        return False
    taken.add(name)
    return True


def _cut_pieces(plan: Plan, name: str, spec: dict, parent: Piece, path: str) -> list[tuple[list[Pt], str]] | None:
    """按 cut 的写法切 parent，返回 [(块的几何, 种类)]；出错时登记问题并返回 None。"""
    kinds = [k for k in ("line", "path", "sectors") if k in spec]
    if len(kinds) != 1:
        plan.error("SS425", path, "cut 要写且只写 line（过两点的直线）、path（折线）、sectors（把圆切成 n 个扇形）其中一个")
        return None
    kind = kinds[0]
    if kind == "sectors":
        return []  # 由调用方处理
    pts = _pts(spec[kind], 2)
    if pts is None or (kind == "line" and len(pts) != 2):
        plan.error("SS425", f"{path}.{kind}", "line 应为两个点 [[x, y], [x, y]]，path 应为至少两个点的折线")
        return None
    if any(same(p, q) for p, q in zip(pts, pts[1:])):
        plan.error("SS425", f"{path}.{kind}", "切线上有重合的相邻点")
        return None
    if parent.kind == "sector":
        plan.error("SS425", f"{path}.{kind}", f"{parent.name} 是圆 / 扇形，只能用 sectors 切")
        return None
    if parent.kind == "dots":
        if kind != "line":
            plan.error("SS425", f"{path}.{kind}", "点阵只能用 line（一条直线）分成两份")
            return None
        a, b = pts
        left = [p for p in parent.points if _cross(a, b, p) > 1e-9]
        right = [p for p in parent.points if _cross(a, b, p) < -1e-9]
        if len(left) + len(right) != len(parent.points):
            plan.error("SS423", f"{path}.line", "有点正好落在切线上，分不清归哪一边")
            return None
        groups = [g for g in (left, right) if g]
        if len(groups) < 2:
            plan.error("SS423", f"{path}.line", f"切线没有把 {parent.name} 分开：所有点都在同一边")
            return None
        return [(g, "dots") for g in groups]
    faces, used = split_polygon(parent.points, pts, infinite=kind == "line")
    if len(faces) < 2:
        plan.error("SS423", f"{path}.{kind}", f"切线没有把 {parent.name} 切开（只得到 1 块）；折线两端要落在边上或边外")
        return None
    plan.cuts[name].lines = used
    return [(f, "poly") for f in faces]


def plan_of(definition: dict) -> Plan:
    plan = Plan()
    taken: set[str] = set()
    shapes = definition.get("shapes")
    if not isinstance(shapes, dict) or not shapes:
        plan.error("SS420", "shapes", "dissect 需要 shapes：一开始的图形，名字 → {polygon / rect / circle / sector / dots}")
        return plan
    for name, spec in shapes.items():
        path = f"shapes.{name}"
        if not _add_name(plan, name, path, taken):
            continue
        piece = _shape(name, spec, plan, path)
        if piece is not None:
            plan.pieces[name] = piece
            plan.initial.append(name)
            style = {k: spec[k] for k in STYLE_KEYS if k in spec}
            if style:
                plan.styles[name] = style
    cuts = definition.get("cuts") or {}
    copies = definition.get("copies") or {}
    if not isinstance(cuts, dict):
        plan.error("SS422", "cuts", "cuts 应为映射：切法名 → {piece, line / path / sectors, into}")
        cuts = {}
    if not isinstance(copies, dict):
        plan.error("SS435", "copies", "copies 应为映射：新块名 → 被复制的块名")
        copies = {}
    # 复制品先登记（cut 可以切复制品；复制品也可以复制 cut 出来的块），顺序上按"先写先有"处理：
    # 先处理所有 cut 的来源都已存在的，剩下的再试，直到不再前进
    pending_cuts = dict(cuts)
    pending_copies = dict(copies)
    progress = True
    while progress and (pending_cuts or pending_copies):
        progress = False
        for new, src in list(pending_copies.items()):
            if isinstance(src, str) and src in plan.pieces:
                path = f"copies.{new}"
                del pending_copies[new]
                progress = True
                if _add_name(plan, new, path, taken):
                    p = plan.pieces[src]
                    plan.pieces[new] = Piece(new, p.kind, list(p.points), p.r, p.a0, p.a1, born=new)
                    plan.copies[new] = src
        for cname, spec in list(pending_cuts.items()):
            path = f"cuts.{cname}"
            if not isinstance(spec, dict):
                del pending_cuts[cname]
                plan.error("SS422", path, "每个切法是一个映射 {piece, line / path / sectors, into}")
                continue
            src = spec.get("piece")
            if not (isinstance(src, str) and src in plan.pieces):
                continue
            del pending_cuts[cname]
            progress = True
            _plan_cut(plan, cname, spec, path, taken)
    for cname, spec in pending_cuts.items():
        src = spec.get("piece") if isinstance(spec, dict) else None
        plan.error("SS422", f"cuts.{cname}.piece", f"cut 要切的块 {src!r} 不存在（块来自 shapes、别的 cut 的 into 或 copies）")
    for new, src in pending_copies.items():
        plan.error("SS435", f"copies.{new}", f"被复制的块 {src!r} 不存在")
    _plan_guides(plan, definition.get("guides"), taken)
    _plan_merges(plan, definition.get("merges"), taken)
    _plan_styles(plan, definition.get("pieces"))
    plan.declared = taken
    return plan


def _plan_cut(plan: Plan, cname: str, spec: dict, path: str, taken: set[str]) -> None:
    extra = set(spec) - {"piece", "line", "path", "sectors", "into", "from"}
    for key in sorted(extra):
        plan.error("SS425", f"{path}.{key}", f"cut 没有字段 {key}")
    parent = plan.pieces[spec["piece"]]
    into = spec.get("into")
    plan.cuts[cname] = Cut(cname, parent.name, [])
    if "sectors" in spec:
        n = spec["sectors"]
        if parent.kind != "sector":
            plan.error("SS425", f"{path}.sectors", f"sectors 只能切圆或扇形，{parent.name} 不是")
            return
        if not (isinstance(n, int) and not isinstance(n, bool) and 2 <= n <= 360):
            plan.error("SS425", f"{path}.sectors", "sectors 应为 2 到 360 之间的整数")
            return
        if not (isinstance(into, str) and NAME.match(into)):
            plan.error("SS424", f"{path}.into", "sectors 的 into 是名字前缀（字符串），块名依次是 前缀0、前缀1……")
            return
        start = parent.a0 if "from" not in spec else spec["from"]
        if not _num(start):
            plan.error("SS425", f"{path}.from", "from 应为起始角（度）")
            return
        span = (parent.a1 - parent.a0) / n
        names = [f"{into}{i}" for i in range(n)]
        cut = plan.cuts[cname]
        cut.sectors = n
        c = parent.points[0]
        for i, nm in enumerate(names):
            if not _add_name(plan, nm, f"{path}.into", taken):
                return
            a0 = float(start) + i * span
            plan.pieces[nm] = Piece(nm, "sector", [c], parent.r, a0, a0 + span, born=cname)
            if i or not parent.full:
                cut.lines.append((c, polar(c, parent.r, a0)))
        if not parent.full:
            cut.lines.append((c, polar(c, parent.r, parent.a1)))
        cut.into = names
        return
    result = _cut_pieces(plan, cname, spec, parent, path)
    if result is None:
        return
    if not (isinstance(into, list) and all(isinstance(x, str) for x in into)):
        plan.error("SS424", f"{path}.into", f"into 应为块名列表；这一刀切出 {len(result)} 块（按重心从左到右、再从下到上排）")
        return
    if len(into) != len(result):
        plan.error("SS424", f"{path}.into", f"这一刀把 {parent.name} 切成 {len(result)} 块，into 给了 {len(into)} 个名字"
                   "（按重心从左到右、再从下到上对应）")
        return
    order = order_by_position([g for g, _ in result])
    names = []
    for nm, k in zip(into, order):
        if _add_name(plan, nm, f"{path}.into", taken):
            geom, kind = result[k]
            plan.pieces[nm] = Piece(nm, kind, geom, born=cname)
            names.append(nm)
    plan.cuts[cname].into = names


def _plan_guides(plan: Plan, guides: object, taken: set[str]) -> None:
    if guides is None:
        return
    if not isinstance(guides, dict):
        plan.error("SS437", "guides", "guides 应为映射：名字 → {from: [x, y], to: [x, y], label?, role?}")
        return
    for name, spec in guides.items():
        path = f"guides.{name}"
        if not _add_name(plan, name, path, taken):
            continue
        ok = isinstance(spec, dict) and _pt(spec.get("from")) and _pt(spec.get("to"))
        if not ok:
            plan.error("SS437", path, "参考线要写 from: [x, y] 和 to: [x, y]")
            continue
        for key in sorted(set(spec) - {"from", "to", "label", "role", "solid", "side"}):
            plan.error("SS437", f"{path}.{key}", f"参考线没有字段 {key}")
        if "side" in spec and spec["side"] not in GUIDE_SIDES:
            plan.error("SS437", f"{path}.side", f"side（标签放在线的哪一边）应为 {' / '.join(GUIDE_SIDES)} 之一")
        if same(_pt(spec["from"]), _pt(spec["to"])):  # type: ignore[arg-type]
            plan.error("SS437", path, "参考线的两端重合")
            continue
        if "role" in spec and spec["role"] not in ROLES:
            plan.error("SS437", f"{path}.role", f"role 应为 {' / '.join(ROLES)} 之一")
        if "label" in spec and not (isinstance(spec["label"], str) and spec["label"]):
            plan.error("SS437", f"{path}.label", "label 应为非空文字")
        plan.guides[name] = spec


def _plan_merges(plan: Plan, merges: object, taken: set[str]) -> None:
    if merges is None:
        return
    if not isinstance(merges, dict):
        plan.error("SS433", "merges", "merges 应为映射：轮廓名 → {pieces: [块名, ...], label?, role?}")
        return
    for name, spec in merges.items():
        path = f"merges.{name}"
        if not _add_name(plan, name, path, taken):
            continue
        pieces = spec.get("pieces") if isinstance(spec, dict) else None
        if not (isinstance(pieces, list) and len(pieces) >= 1 and all(isinstance(p, str) for p in pieces)):
            plan.error("SS433", path, "合并轮廓要写 pieces: [块名, ...]")
            continue
        for key in sorted(set(spec) - {"pieces", "label", "role"}):
            plan.error("SS433", f"{path}.{key}", f"合并轮廓没有字段 {key}")
        missing = [p for p in pieces if p not in plan.pieces]
        if missing:
            plan.error("SS433", f"{path}.pieces", f"没有块 {'、'.join(missing)}")
            continue
        if any(plan.pieces[p].kind == "dots" for p in pieces):
            plan.error("SS433", f"{path}.pieces", "点阵没有轮廓，不能合并")
            continue
        if "role" in spec and spec["role"] not in ROLES:
            plan.error("SS433", f"{path}.role", f"role 应为 {' / '.join(ROLES)} 之一")
        plan.merges[name] = spec


def _plan_styles(plan: Plan, styles: object) -> None:
    if styles is not None and not isinstance(styles, dict):
        plan.error("SS439", "pieces", "pieces 应为映射：块名 → {role?, label?, edges?}")
        styles = None
    styles = styles or {}
    for name, spec in styles.items():
        path = f"pieces.{name}"
        if name not in plan.pieces:
            plan.error("SS439", path, f"没有块 {name}（pieces 只给已有的块配颜色和标签）")
            continue
        if not isinstance(spec, dict):
            plan.error("SS439", path, "应为 {role?, label?, edges?}")
            continue
        plan.styles[name] = {**plan.styles.get(name, {}), **spec}
    for new, src in plan.copies.items():  # 复制品和原块长得一样：没单独配样式就沿用原块的颜色和标签
        if new not in plan.styles and src in plan.styles:
            plan.styles[new] = dict(plan.styles[src])
    for name, spec in plan.styles.items():
        path = f"pieces.{name}" if name in styles else f"shapes.{name}"
        _check_style(plan, plan.pieces[name], spec, path)


def _check_style(plan: Plan, piece: Piece, spec: dict, path: str) -> None:
    for key in sorted(set(spec) - STYLE_KEYS):
        plan.error("SS439", f"{path}.{key}", f"块的样式没有字段 {key}（有 role、label、edges）")
    if "role" in spec and spec["role"] not in ROLES:
        plan.error("SS439", f"{path}.role", f"role 应为 {' / '.join(ROLES)} 之一")
    if "label" in spec and not (isinstance(spec["label"], str) and spec["label"]):
        plan.error("SS439", f"{path}.label", "label 应为非空文字（面积标签，写在块的重心处）")
    edges = spec.get("edges")
    if edges is None:
        return
    if not isinstance(edges, list):
        plan.error("SS439", f"{path}.edges", "edges 应为列表，每项 {at: [[x, y], [x, y]], text: 文字}")
        return
    for i, e in enumerate(edges):
        at = _pts(e.get("at"), 2) if isinstance(e, dict) else None
        if at is None or len(at) != 2 or not (isinstance(e.get("text"), str) and e["text"]) or set(e) - {"at", "text"}:
            plan.error("SS439", f"{path}.edges[{i}]", "每项写 {at: [[x, y], [x, y]], text: 文字}")
            continue
        if piece.find_edge(*at) is None:
            plan.error("SS439", f"{path}.edges[{i}].at", f"{piece.name} 没有从 {at[0]} 到 {at[1]} 的边")


# ---------- 动作参数检查（按时间顺序模拟哪些块存在）----------

ACTION_ARGS = {
    "cut": {"cut", "spread"},
    "shift": {"piece", "by", "to"},
    "rotate": {"piece", "angle", "about"},
    "flip": {"piece", "axis"},
    "snap": {"piece", "edge", "vertex", "to", "to_edge", "to_vertex"},
    "copy": {"piece", "by"},
    "merge": {"name"},
    "unmerge": {"name"},
    "arrange": {"cut", "layout", "at"},
    "labels": {"piece", "show"},
}


@dataclass
class State:
    """检查时按动作顺序推演的状态：现在有哪些块，哪些切法已经切过、哪些轮廓正显示着。"""

    plan: Plan
    alive: set[str] = field(default_factory=set)
    done: set[str] = field(default_factory=set)  # "cut:名字" / "copy:名字"
    merged: set[str] = field(default_factory=set)

    @classmethod
    def start(cls, plan: Plan) -> State:
        return cls(plan, alive=set(plan.initial))


def _alive(state: State, name: object, path: str, report, what: str = "piece") -> Piece | None:
    plan = state.plan
    if not isinstance(name, str) or name not in plan.pieces:
        known = "、".join(sorted(plan.pieces)) or "无"
        report.error("SS426", path, f"没有块 {name!r}（现有：{known}）")
        return None
    if name not in state.alive:
        piece = plan.pieces[name]
        if piece.born is not None and name not in state.alive and _born_later(state, piece):
            how = f"cut {piece.born}" if piece.born in plan.cuts else f"copy {name}"
            report.error("SS427", path, f"块 {name} 这时还不存在：要先做 {how}")
        else:
            report.error("SS427", path, f"块 {name} 这时已经不存在了（被切开了）")
        return None
    return plan.pieces[name]


def _born_later(state: State, piece: Piece) -> bool:
    if piece.born in state.plan.cuts:
        return f"cut:{piece.born}" not in state.done
    return f"copy:{piece.name}" not in state.done


def _point_arg(value: object, path: str, report, what: str) -> Pt | None:
    p = _pt(value)
    if p is None:
        report.error("SS432", path, f"{what} 应为 [x, y]")
    return p


def check_action(act: str, args: dict, state: State, report, path: str) -> None:
    plan = state.plan
    for key in sorted(set(args) - ACTION_ARGS[act]):
        report.error("SS436", f"{path}.args.{key}", f"{act} 没有参数 {key}（有 {'、'.join(sorted(ACTION_ARGS[act]))}）")
    a = f"{path}.args"
    if act == "cut":
        name = args.get("cut")
        if name not in plan.cuts:
            report.error("SS422", f"{a}.cut", f"没有切法 {name!r}（在对象的 cuts 里定义）")
            return
        if f"cut:{name}" in state.done:
            report.error("SS422", f"{a}.cut", f"切法 {name} 已经切过了")
            return
        if "spread" in args and not (_num(args["spread"]) and args["spread"] >= 0):
            report.error("SS432", f"{a}.spread", "spread 应为非负数：切开后各块沿离开切口的方向分开多远")
        cut = plan.cuts[name]
        if _alive(state, cut.piece, f"{a}.cut", report) is None:
            return
        state.alive.discard(cut.piece)
        state.alive |= set(cut.into)
        state.done.add(f"cut:{name}")
        return
    if act == "copy":
        name = args.get("piece")
        if name not in plan.copies:
            report.error("SS435", f"{a}.piece", f"{name!r} 不是在 copies 里定义的复制品")
            return
        if f"copy:{name}" in state.done:
            report.error("SS435", f"{a}.piece", f"{name} 已经复制过了")
            return
        if "by" in args:
            _point_arg(args["by"], f"{a}.by", report, "by")
        if _alive(state, plan.copies[name], f"{a}.piece", report) is None:
            return
        state.alive.add(name)
        state.done.add(f"copy:{name}")
        return
    if act in ("merge", "unmerge"):
        name = args.get("name")
        if name not in plan.merges:
            report.error("SS433", f"{a}.name", f"没有合并轮廓 {name!r}（在对象的 merges 里定义）")
            return
        if act == "merge":
            for p in plan.merges[name]["pieces"]:
                _alive(state, p, f"{a}.name", report)
            state.merged.add(name)
        elif name not in state.merged:
            report.error("SS433", f"{a}.name", f"轮廓 {name} 还没有 merge，不能 unmerge")
        else:
            state.merged.discard(name)
        return
    if act == "arrange":
        name = args.get("cut")
        cut = plan.cuts.get(name) if isinstance(name, str) else None
        if cut is None or not cut.sectors:
            report.error("SS434", f"{a}.cut", "arrange 需要 cut：一个 sectors 切法的名字（排的是它切出的全部扇形）")
            return
        if args.get("layout", "alternate") not in LAYOUTS:
            report.error("SS434", f"{a}.layout", f"layout 只有 {' / '.join(LAYOUTS)}")
        if "at" in args:
            _point_arg(args["at"], f"{a}.at", report, "at")
        for p in cut.into:
            if _alive(state, p, f"{a}.cut", report) is None:
                break
        return
    piece = _alive(state, args.get("piece"), f"{a}.piece", report)
    if act == "labels":
        if not isinstance(args.get("show"), bool):
            report.error("SS436", f"{a}.show", "labels 需要 show: true / false")
        return
    if act == "shift":
        if ("by" in args) == ("to" in args):
            report.error("SS432", a, "shift 要写 by: [dx, dy]（平移多少）或 to: [x, y]（重心移到哪），二选一")
        for key in ("by", "to"):
            if key in args:
                _point_arg(args[key], f"{a}.{key}", report, key)
        return
    if act == "rotate":
        if not (_num(args.get("angle")) and args["angle"] != 0):
            report.error("SS431", f"{a}.angle", "rotate 需要 angle：转多少度（逆时针为正，不能为 0）")
        about = args.get("about", "center")
        if about == "center":
            return
        if isinstance(about, dict) and set(about) == {"vertex"}:
            v = _pt(about["vertex"])
            if v is None:
                report.error("SS431", f"{a}.about.vertex", "vertex 应为 [x, y]（块的原坐标）")
            elif piece is not None and not piece.has_vertex(v):
                report.error("SS428", f"{a}.about.vertex", f"{piece.name} 没有顶点 {list(v)}")
            return
        if _pt(about) is None:
            report.error("SS431", f"{a}.about", "about 应为 center、[x, y]（图形坐标）或 {vertex: [x, y]}（块的原坐标）")
        return
    if act == "flip":
        axis = args.get("axis")
        if isinstance(axis, dict) and set(axis) == {"edge"}:
            pts = _pts(axis["edge"], 2)
            if pts is None or len(pts) != 2:
                report.error("SS430", f"{a}.axis.edge", "edge 应为两个点 [[x, y], [x, y]]（块的原坐标）")
            elif same(*pts):
                report.error("SS430", f"{a}.axis.edge", "翻折轴退化：两点重合")
            elif piece is not None and piece.find_edge(*pts) is None:
                report.error("SS428", f"{a}.axis.edge", f"{piece.name} 没有从 {list(pts[0])} 到 {list(pts[1])} 的边")
            return
        pts = _pts(axis, 2)
        if pts is None or len(pts) != 2:
            report.error("SS430", f"{a}.axis", "flip 需要 axis：两个点 [[x, y], [x, y]]（图形坐标），或 {edge: ...}（沿块自己的一条边翻）")
        elif same(*pts):
            report.error("SS430", f"{a}.axis", "翻折轴退化：两点重合，定不出一条直线")
        return
    if act == "snap":
        _check_snap(args, piece, state, report, a)


def _check_snap(args: dict, piece: Piece | None, state: State, report, a: str) -> None:
    plan = state.plan
    by_edge, by_vertex = "edge" in args, "vertex" in args
    if by_edge == by_vertex:
        report.error("SS428", a, "snap 要写 edge（边对边）或 vertex（点对点），二选一")
        return
    if "to" not in args:
        report.error("SS428", a, "snap 需要 to：吸附到哪一块（或参考线、或图形坐标里的一个点）")
        return
    to = args["to"]
    target = None
    if isinstance(to, str):
        if to in plan.guides:
            target = "guide"
        else:
            target = _alive(state, to, f"{a}.to", report)
            if target is None:
                return
            if to == args.get("piece"):
                report.error("SS428", f"{a}.to", "不能吸附到自己")
                return
    elif _pt(to) is None:
        report.error("SS428", f"{a}.to", "to 应为块名、参考线名或 [x, y]")
        return
    if by_edge:
        pts = _pts(args["edge"], 2)
        if pts is None or len(pts) != 2:
            report.error("SS428", f"{a}.edge", "edge 应为两个点 [[x, y], [x, y]]（块的原坐标）")
            return
        if piece is not None and piece.find_edge(*pts) is None:
            report.error("SS428", f"{a}.edge", f"{piece.name} 没有从 {list(pts[0])} 到 {list(pts[1])} 的边")
            return
        if target == "guide":
            g = plan.guides[to]
            dst = (_pt(g["from"]), _pt(g["to"]))
            if "to_edge" in args:
                report.error("SS428", f"{a}.to_edge", "吸附到参考线时不写 to_edge（就是参考线本身，from → to）")
        elif isinstance(target, Piece):
            dst = _pts(args.get("to_edge"), 2)
            if dst is None or len(dst) != 2:
                report.error("SS428", f"{a}.to_edge", "边对边吸附需要 to_edge：目标块的一条边（它的原坐标）")
                return
            if target.find_edge(*dst) is None:
                report.error("SS428", f"{a}.to_edge", f"{target.name} 没有从 {list(dst[0])} 到 {list(dst[1])} 的边")
                return
        else:
            report.error("SS428", f"{a}.to", "边对边吸附的目标要是一块或一条参考线")
            return
        if abs(dist(*pts) - dist(*dst)) > 1e-6:
            report.error("SS429", f"{a}.edge", f"两条边不一样长（{dist(*pts):.4g} 和 {dist(*dst):.4g}），刚体移动对不上")
        return
    v = _pt(args["vertex"])
    if v is None:
        report.error("SS428", f"{a}.vertex", "vertex 应为 [x, y]（块的原坐标）")
        return
    if piece is not None and not piece.has_vertex(v):
        report.error("SS428", f"{a}.vertex", f"{piece.name} 没有顶点 {list(v)}")
        return
    if isinstance(target, Piece):
        tv = _pt(args.get("to_vertex"))
        if tv is None:
            report.error("SS428", f"{a}.to_vertex", "点对点吸附到一块时需要 to_vertex：它的一个顶点（原坐标）")
        elif not target.has_vertex(tv):
            report.error("SS428", f"{a}.to_vertex", f"{target.name} 没有顶点 {list(tv)}")
    elif target == "guide":
        report.error("SS428", f"{a}.to", "点对点吸附的目标要是一块或一个点 [x, y]")


# ---------- 登记到 widgets.REGISTRY ----------

def register(registry: dict) -> None:
    from .widgets import Exposed, Widget

    def _dict(what: str):
        def check(value: object) -> str | None:
            return None if isinstance(value, dict) else f"应为映射（{what}）"

        return check

    def expose(definition: dict, data: dict) -> Exposed:
        plan = plan_of(definition)
        exposed = Exposed(spans=plan.names(), items=len(plan.initial))
        exposed.state["plan"] = plan
        return exposed

    def validate(ctx, report, path: str) -> None:
        plan = ctx.exposed.state["plan"]
        for code, sub, message in plan.problems:
            report.error(code, f"{path}.{sub}", message)

    def action(act: str):
        def check(args: dict, ctx, report, path: str) -> None:
            state = ctx.exposed.state.setdefault("sim", State.start(ctx.exposed.state["plan"]))
            check_action(act, args, state, report, path)

        return check

    registry["dissect"] = Widget(
        "dissect",
        params={
            "shapes": (True, _dict("名字 → 图形")),
            "cuts": (False, _dict("切法名 → {piece, line / path / sectors, into}")),
            "copies": (False, _dict("复制品名 → 原块名")),
            "guides": (False, _dict("参考线名 → {from, to, label?, role?}")),
            "merges": (False, _dict("轮廓名 → {pieces, label?, role?}")),
            "pieces": (False, _dict("块名 → {role?, label?, edges?}")),
            "view": (False, lambda v: None if _pts(v, 2) and len(v) == 2 else "应为 [[x0, y0], [x1, y1]]：要给图形留出的范围（图形坐标）"),
        },
        expose=expose,
        actions={act: action(act) for act in ACTION_ARGS},
        validate=validate,
    )
