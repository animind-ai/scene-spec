r"""三维坐标空间（space）的检查：从原点出发的向量、直线（span）、过原点的平面、平行六面体、3×3 矩阵变形、
向量投影到平面 / 直线上（投影和误差向量）、相机 orbit。组件本身在 kit 的 mx/space.py。

    sp:
      widget: space
      x: [-3, 3]                    # 坐标范围：整数 [起, 止]，起 ≤ 0 < 止（同 plane）
      y: [-3, 3]
      z: [-2, 3]
      view: {azimuth: 30, elevation: 20}   # 同 solid：方位角绝对值 10°–80°，仰角 10°–50°
      floor: true                   # z = 0 上的淡单位网格（默认 true）
      mesh: true                    # z = 0 上另一层彩色网格，跟着 warp 变形（mesh_role，默认 B）
      axis_labels: [x, y, z]        # 三个轴名（公式，不加 $）；默认 x、y、z

画在空间里的东西都有名字（name），之后的动作按名字找；坐标都是数学坐标 [x, y, z]：
- vector {name, v, at?, role, label, dashed}：箭头，尾巴在 at（默认原点）；
- point {name, at, role, label}：一个点；
- line {name, dir, through?, role, label, dashed}：过 through（默认原点）沿 dir 的直线（span），裁在坐标范围里；
- plane {name, span: [u, w] 或 normal: [a, b, c], through?, role, label}：平面（默认过原点），裁在坐标范围里，半透明；
- box {name, edges: [u, v, w], at?, role, label}：三条棱 u、v、w 张成的平行六面体（体积 |det[u v w]|），
  edges 是 [[1,0,0],[0,1,0],[0,0,1]] 时就是单位正方体；
- project {name（一支向量）, onto（一个平面或一条直线，都要过原点）, as（投影的新名字）, error?（误差向量 v − p 的新名字）,
  role, label, error_role, error_label}：投影向量从原点长出来，误差向量（虚线）从投影的箭头尖连到原来那支的箭头尖，
  拐角画直角记号；
- warp {matrix: 3×3}：整个空间（彩色网格和所有东西）按矩阵变形，和之前的变换复合；按 (1−t)I + tM 渐变。
  矩阵可以是奇异的（列空间是一个平面或一条线：整个空间压上去）；
- reset：变回原样（之前所有 warp 的逆；之前的变换是奇异的时候没法撤回，SS479）；
- orbit {azimuth / elevation 或 d_azimuth / d_elevation}：同 solid（SS469）；
- relabel {name, label}：换名字（旧的淡出、新的淡入；例如变形之后把 \det = 1 换成 \det = 3）；
- remove {name}（一个或列表；不写 = 全部）：淡出。

检查（错误码 SS475–SS479；动作的多余参数报 SS281）：
- SS475：组件参数写错（x / y / z 范围、view、axis_labels）；
- SS476：动作参数写错（向量不是三个数、名字重复或不存在、零向量当方向、平面的两个方向平行、box 的 edges 不是三个向量）；
- SS477：向量、点、平行六面体的顶点、投影出的向量在动作之后（warp 途中按 16 步取样）伸出了坐标范围；
  直线和平面裁在范围里，只要求 through 在范围里；
- SS478：project 写错：name 不是向量、onto 不是平面或直线、onto 不过原点；
- SS479：warp 的 matrix 不是 3×3 的数，或在奇异的变换之后 reset。
"""

from __future__ import annotations

from .report import Report
from .solid import AZIMUTH, ELEVATION, VIEW, _orbit
from .textmarks import ROLES

Vec = tuple[float, float, float]
Mat = tuple[Vec, Vec, Vec]
EYE: Mat = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
KINDS = ("vector", "point", "line", "plane", "box")


def _num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _vec(v: object) -> bool:
    return isinstance(v, list) and len(v) == 3 and all(_num(x) for x in v)


def _range(value: object) -> str | None:
    ok = (isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
          and value[0] <= 0 < value[1])
    return None if ok else "应为 [起, 止]：整数，起 ≤ 0 < 止"


def _bool(value: object) -> str | None:
    return None if isinstance(value, bool) else "应为 true / false"


def _role(value: object) -> str | None:
    return None if value in ROLES else f"应为 {'/'.join(sorted(ROLES))} 之一"


def matrix(value: object) -> Mat | None:
    if isinstance(value, list) and len(value) == 3 and all(_vec(r) for r in value):
        return tuple(tuple(float(x) for x in r) for r in value)  # type: ignore[return-value]
    return None


def mul(m: Mat, n: Mat) -> Mat:
    return tuple(tuple(sum(m[i][k] * n[k][j] for k in range(3)) for j in range(3)) for i in range(3))  # type: ignore[return-value]


def act(m: Mat, p: Vec) -> Vec:
    return tuple(sum(m[i][k] * p[k] for k in range(3)) for i in range(3))  # type: ignore[return-value]


def cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a: Vec, b: Vec) -> float:
    return sum(x * y for x, y in zip(a, b))


def det(m: Mat) -> float:
    return dot(m[0], cross(m[1], m[2]))


def inv(m: Mat) -> Mat:
    d = det(m)
    cols = (cross(m[1], m[2]), cross(m[2], m[0]), cross(m[0], m[1]))  # 伴随矩阵的列
    return tuple(tuple(cols[j][i] / d for j in range(3)) for i in range(3))  # type: ignore[return-value]


def lerp(m: Mat, t: float) -> Mat:
    return tuple(tuple((1 - t) * EYE[i][j] + t * m[i][j] for j in range(3)) for i in range(3))  # type: ignore[return-value]


def plane_span(normal: Vec) -> tuple[Vec, Vec]:
    """法向 normal 的平面里两个互相垂直的方向（和 kit 一致：先取和法向最不平行的坐标轴）。"""
    k = min(range(3), key=lambda i: abs(normal[i]))
    axis = tuple(1.0 if i == k else 0.0 for i in range(3))
    u = cross(normal, axis)
    return u, cross(normal, u)


def project(v: Vec, onto: dict) -> Vec:
    """v 投影到过原点的直线（dir）或平面（u, w）上。"""
    if onto["kind"] == "line":
        d = onto["dir"]
        return tuple(dot(v, d) / dot(d, d) * x for x in d)  # type: ignore[return-value]
    n = cross(onto["u"], onto["w"])
    return tuple(x - dot(v, n) / dot(n, n) * y for x, y in zip(v, n))  # type: ignore[return-value]


def points(item: dict) -> list[Vec]:
    """要留在坐标范围里的点：向量的头尾、点、平行六面体的 8 个顶点、直线和平面经过的点。"""
    k = item["kind"]
    if k == "vector":
        return [item["at"], tuple(a + b for a, b in zip(item["at"], item["v"]))]  # type: ignore[list-item]
    if k == "box":
        o, (u, v, w) = item["at"], item["edges"]
        return [tuple(o[i] + a * u[i] + b * v[i] + c * w[i] for i in range(3))  # type: ignore[misc]
                for a in (0, 1) for b in (0, 1) for c in (0, 1)]
    return [item["at"]]


def moved(item: dict, m: Mat) -> dict:
    out = dict(item)
    for key in ("at", "v", "dir", "u", "w"):
        if key in item:
            out[key] = act(m, item[key])
    if "edges" in item:
        out["edges"] = [act(m, e) for e in item["edges"]]
    return out


def register(registry: dict, Widget, Exposed, unknown_args) -> None:  # noqa: N803
    def expose(definition: dict, data: dict) -> Exposed:
        view = definition.get("view") if isinstance(definition.get("view"), dict) else {}
        angles = [float(view.get(k, VIEW[i])) if _num(view.get(k, VIEW[i])) else VIEW[i]
                  for i, k in enumerate(("azimuth", "elevation"))]
        return Exposed(parts={"axes": 1, "floor": 1, "mesh": 1, "items": 1},
                       state={"items": {}, "M": EYE, "view": angles})

    def box(ctx):
        r = [ctx.definition.get(k) for k in ("x", "y", "z")]
        return None if any(_range(v) for v in r) else r

    def inside(ctx, report: Report, path: str, name: str, pts: list[Vec]) -> bool:
        b = box(ctx)
        if b is None:
            return True
        for p in pts:
            if any(p[i] < b[i][0] - 1e-9 or p[i] > b[i][1] + 1e-9 for i in range(3)):
                q = ", ".join(f"{x:.3g}" for x in p)
                report.error("SS477", path, f"{name} 伸到 ({q})，出了坐标范围 x {b[0]}、y {b[1]}、z {b[2]}")
                return False
        return True

    def new_name(args: dict, key: str, ctx, report: Report, path: str, taken: set[str] = frozenset()) -> str | None:
        name = args.get(key)
        if not isinstance(name, str) or not name:
            report.error("SS476", f"{path}.args.{key}", f"需要 {key}：名字（之后的动作按它找）")
            return None
        if name in ctx.exposed.state["items"] or name in taken:
            report.error("SS476", f"{path}.args.{key}", f"名字 {name} 已经用过了")
            return None
        return name

    def old_names(args: dict, ctx, report: Report, path: str) -> list[str] | None:
        v = args.get("name")
        items = ctx.exposed.state["items"]
        if v is None:
            return list(items)
        names = [v] if isinstance(v, str) else v
        if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
            report.error("SS476", f"{path}.args.name", "name 应为名字或名字列表")
            return None
        missing = [n for n in names if n not in items]
        if missing:
            report.error("SS476", f"{path}.args.name", f"空间里还没有 {'、'.join(missing)}（现在有 {'、'.join(items) or '无'}）")
            return None
        return names

    def common(args: dict, report: Report, path: str, prefix: str = "") -> None:
        if f"{prefix}role" in args and _role(args[f"{prefix}role"]):
            report.error("SS476", f"{path}.args.{prefix}role", _role(args[f"{prefix}role"]))
        if f"{prefix}label" in args and not isinstance(args[f"{prefix}label"], str):
            report.error("SS476", f"{path}.args.{prefix}label", "label 应为字符串（公式，不加 $）")
        if "dashed" in args and not prefix and _bool(args["dashed"]):
            report.error("SS476", f"{path}.args.dashed", "dashed 应为 true / false")

    def vec_arg(args: dict, key: str, report: Report, path: str, what: str, required: bool = True,
                nonzero: bool = False) -> Vec | None:
        if key not in args:
            if required:
                report.error("SS476", f"{path}.args.{key}", f"需要 {key}：{what}")
            return None
        v = args[key]
        if not _vec(v):
            report.error("SS476", f"{path}.args.{key}", f"{key} 应为 [x, y, z]：{what}")
            return None
        if nonzero and all(abs(x) < 1e-12 for x in v):
            report.error("SS476", f"{path}.args.{key}", f"{key} 不能是零向量")
            return None
        return tuple(float(x) for x in v)  # type: ignore[return-value]

    def put(ctx, report: Report, path: str, name: str | None, item: dict | None) -> None:
        if name and item:
            ctx.exposed.state["items"][name] = item
            inside(ctx, report, path, name, points(item))

    def vector(args: dict, ctx, report: Report, path: str) -> None:
        name = new_name(args, "name", ctx, report, path)
        v = vec_arg(args, "v", report, path, "分量")
        at = vec_arg(args, "at", report, path, "尾巴的位置", required=False) or (0.0, 0.0, 0.0)
        common(args, report, path)
        unknown_args(args, {"name", "v", "at", "role", "label", "dashed"}, "vector", report, path)
        put(ctx, report, path, name, v and {"kind": "vector", "v": v, "at": at})

    def point(args: dict, ctx, report: Report, path: str) -> None:
        name = new_name(args, "name", ctx, report, path)
        at = vec_arg(args, "at", report, path, "点的位置")
        common(args, report, path)
        unknown_args(args, {"name", "at", "role", "label"}, "point", report, path)
        put(ctx, report, path, name, at and {"kind": "point", "at": at})

    def line(args: dict, ctx, report: Report, path: str) -> None:
        name = new_name(args, "name", ctx, report, path)
        d = vec_arg(args, "dir", report, path, "直线的方向", nonzero=True)
        at = vec_arg(args, "through", report, path, "直线经过的点", required=False) or (0.0, 0.0, 0.0)
        common(args, report, path)
        unknown_args(args, {"name", "dir", "through", "role", "label", "dashed"}, "line", report, path)
        put(ctx, report, path, name, d and {"kind": "line", "dir": d, "at": at})

    def plane(args: dict, ctx, report: Report, path: str) -> None:
        name = new_name(args, "name", ctx, report, path)
        at = vec_arg(args, "through", report, path, "平面经过的点", required=False) or (0.0, 0.0, 0.0)
        common(args, report, path)
        unknown_args(args, {"name", "span", "normal", "through", "role", "label"}, "plane", report, path)
        if ("span" in args) == ("normal" in args):
            report.error("SS476", f"{path}.args", "plane 写 span: [u, w]（两个方向）或 normal: [a, b, c]（法向）之一")
            return
        if "normal" in args:
            n = vec_arg(args, "normal", report, path, "法向", nonzero=True)
            if n is None:
                return
            u, w = plane_span(n)
        else:
            span = args["span"]
            if not (isinstance(span, list) and len(span) == 2 and all(_vec(s) for s in span)):
                report.error("SS476", f"{path}.args.span", "span 应为两个 [x, y, z]：平面里的两个方向")
                return
            u, w = (tuple(float(x) for x in s) for s in span)
            if all(abs(x) < 1e-9 for x in cross(u, w)):
                report.error("SS476", f"{path}.args.span", "span 的两个方向平行（或有零向量）：张不成平面，用 line")
                return
        put(ctx, report, path, name, {"kind": "plane", "u": u, "w": w, "at": at})

    def box_(args: dict, ctx, report: Report, path: str) -> None:
        name = new_name(args, "name", ctx, report, path)
        edges = args.get("edges")
        at = vec_arg(args, "at", report, path, "起点（三条棱的公共端点）", required=False) or (0.0, 0.0, 0.0)
        common(args, report, path)
        unknown_args(args, {"name", "edges", "at", "role", "label"}, "box", report, path)
        if not (isinstance(edges, list) and len(edges) == 3 and all(_vec(e) for e in edges)):
            report.error("SS476", f"{path}.args.edges", "box 需要 edges：三条棱 [[x, y, z], [x, y, z], [x, y, z]]")
            return
        put(ctx, report, path, name, {"kind": "box", "edges": [tuple(float(x) for x in e) for e in edges], "at": at})

    def project_(args: dict, ctx, report: Report, path: str) -> None:
        items = ctx.exposed.state["items"]
        unknown_args(args, {"name", "onto", "as", "error", "role", "label", "error_role", "error_label"}, "project", report, path)
        common(args, report, path)
        common(args, report, path, "error_")
        src, onto = items.get(args.get("name")), items.get(args.get("onto"))
        if src is None or src["kind"] != "vector":
            report.error("SS478", f"{path}.args.name", "project 的 name 应为空间里已有的一支向量")
        if onto is None or onto["kind"] not in ("line", "plane"):
            report.error("SS478", f"{path}.args.onto", "onto 应为空间里已有的一个平面或一条直线")
        elif any(abs(x) > 1e-9 for x in onto["at"]):
            report.error("SS478", f"{path}.args.onto", "onto 要过原点（投影是线性变换）")
            onto = None
        p_name = new_name(args, "as", ctx, report, path)
        e_name = new_name(args, "error", ctx, report, path, {p_name} if p_name else set()) if "error" in args else None
        if src is None or src["kind"] != "vector" or onto is None or onto["kind"] not in ("line", "plane"):
            return
        if any(abs(x) > 1e-9 for x in src["at"]):
            report.error("SS478", f"{path}.args.name", "要投影的向量尾巴要在原点")
            return
        p = project(src["v"], {"kind": onto["kind"], "dir": onto.get("dir"), "u": onto.get("u"), "w": onto.get("w")})
        put(ctx, report, path, p_name, {"kind": "vector", "v": p, "at": (0.0, 0.0, 0.0)})
        if e_name:
            put(ctx, report, path, e_name, {"kind": "vector", "v": tuple(a - b for a, b in zip(src["v"], p)), "at": p})

    def apply(ctx, report: Report, path: str, m: Mat) -> None:
        state = ctx.exposed.state
        for n, item in state["items"].items():
            for k in range(1, 17):
                if not inside(ctx, report, path, n, points(moved(item, lerp(m, k / 16)))):
                    break
        state["items"] = {n: moved(item, m) for n, item in state["items"].items()}
        state["M"] = mul(m, state["M"])

    def warp(args: dict, ctx, report: Report, path: str) -> None:
        unknown_args(args, {"matrix"}, "warp", report, path)
        m = matrix(args.get("matrix"))
        if m is None:
            report.error("SS479", f"{path}.args.matrix", "warp 需要 matrix：[[a, b, c], [d, e, f], [g, h, i]]（3×3 的数）")
            return
        apply(ctx, report, path, m)

    def reset(args: dict, ctx, report: Report, path: str) -> None:
        unknown_args(args, set(), "reset", report, path)
        m = ctx.exposed.state["M"]
        if abs(det(m)) < 1e-9:
            report.error("SS479", path, "之前的变换是奇异的（空间压成了平面、直线或一点）：撤不回去；"
                         "要回到原样，先 remove 再重新画")
            return
        apply(ctx, report, path, inv(m))

    def orbit(args: dict, ctx, report: Report, path: str) -> None:
        unknown_args(args, {"azimuth", "elevation", "d_azimuth", "d_elevation"}, "orbit", report, path)
        _orbit(args, ctx.exposed.state, report, path)

    def relabel(args: dict, ctx, report: Report, path: str) -> None:
        unknown_args(args, {"name", "label"}, "relabel", report, path)
        names = old_names(args, ctx, report, path) if "name" in args else None
        if "name" not in args:
            report.error("SS476", f"{path}.args.name", "relabel 需要 name：一个东西的名字")
        elif names and len(names) != 1:
            report.error("SS476", f"{path}.args.name", "relabel 一次换一个名字")
        if not isinstance(args.get("label"), str):
            report.error("SS476", f"{path}.args.label", "relabel 需要 label：新名字（公式，不加 $）")

    def remove(args: dict, ctx, report: Report, path: str) -> None:
        unknown_args(args, {"name"}, "remove", report, path)
        for n in old_names(args, ctx, report, path) or []:
            ctx.exposed.state["items"].pop(n, None)

    def validate(ctx, report: Report, path: str) -> None:
        d = ctx.definition
        view = d.get("view")
        if view is None:
            return
        if not isinstance(view, dict) or set(view) - {"azimuth", "elevation"}:
            report.error("SS475", f"{path}.view", "view 应为 {azimuth?, elevation?}（度）")
            return
        az, el = view.get("azimuth", VIEW[0]), view.get("elevation", VIEW[1])
        if not _num(az) or not AZIMUTH[0] <= abs(az) <= AZIMUTH[1]:
            report.error("SS475", f"{path}.view.azimuth", f"azimuth 的绝对值应在 {AZIMUTH[0]:g}°–{AZIMUTH[1]:g}°"
                         "（太小或太大时有一根坐标轴看成一个点）")
        if not _num(el) or not ELEVATION[0] <= el <= ELEVATION[1]:
            report.error("SS475", f"{path}.view.elevation", f"elevation 应在 {ELEVATION[0]:g}°–{ELEVATION[1]:g}°")

    def labels(value: object) -> str | None:
        ok = isinstance(value, list) and len(value) == 3 and all(isinstance(v, str) for v in value)
        return None if ok else "应为三个字符串：x、y、z 轴的名字（公式，不加 $）"

    registry["space"] = Widget(
        "space",
        params={"x": (True, _range), "y": (True, _range), "z": (True, _range), "view": (False, lambda v: None),
                "floor": (False, _bool), "mesh": (False, _bool), "mesh_role": (False, _role),
                "axis_labels": (False, labels)},
        expose=expose,
        actions={"vector": vector, "point": point, "line": line, "plane": plane, "box": box_, "project": project_,
                 "warp": warp, "reset": reset, "orbit": orbit, "relabel": relabel, "remove": remove},
        validate=validate,
    )
