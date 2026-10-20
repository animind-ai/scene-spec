"""数据曲线和参数曲线：顶层 data 里的点列（可以写在外部 JSON 里）、graph 的 {data} 曲线、plane 的 curves 和沿曲线走的点。

数据：data 段的一项可以直接写字面量，也可以写 {src: "相对场景文件的路径.json"}，从 JSON 文件读（只认 JSON；
路径不能是绝对路径，也不能用 .. 或符号链接跑出场景文件所在的目录）。kit 渲染时用这里的 load_data 读同一份数据。
当曲线用的点列是 [[x0, y0], [x1, y1], …]：至少两个点，坐标是有限的数，最多 MAX_POINTS 个。

曲线：
- 数据曲线 {data: 键}：按顺序连成折线；
- 参数曲线 {x: "x(t)", y: "y(t)", domain: [t0, t1]}：t 是曲线自己的变量（白名单表达式，可以再引用场景参数），
  在 domain 上等分取 PARAM_SAMPLES 个点连成折线。

progress（数或参数表达式，0 到 1）：只画曲线的前一部分，0 什么都不画、1 画完，补间它就是一条平滑长出来的轨迹。
沿曲线走的点 {curve: i, at: 0 到 1}：和 progress 同一把尺子，所以 at 和 progress 写同一个参数时，点正好在轨迹的头上。
这把尺子由 along 定：
- length（默认）：按弧长，0.5 是走过一半路程的地方，点匀速走；
- param：按参数，数据曲线是点的序号（0.5 是中间那个下标），参数曲线是 t（0.5 是 t 走到 domain 的一半）。
  模拟数据按等时间间隔采样时用它，点的快慢就是真实的快慢。
两种都是分段线性插值（不做样条：数据曲线本来就该采得够密）。

错误码 SS490–SS499：
- SS490 data 的 {src} 写法不对：不是字符串、绝对路径、用 .. 跑出场景目录、不是 .json、多了别的字段；
- SS491 数据文件找不到、读不了，或大于 MAX_BYTES；
- SS492 数据文件不是合法的 JSON；
- SS493 当曲线用的数据不是 [[x, y], …]：不是列表、点不是两个数、少于两个点；
- SS494 坐标不是有限数（JSON 里的 NaN、Infinity、1e999）；
- SS495 点数超过 MAX_POINTS；
- SS496 曲线写法不对：引用的 data 不存在、f 和 data 都写或都没写、参数曲线缺 x / y / domain、
  曲线变量 t 和场景参数重名、点引用的曲线不存在、graph 的点放在数据曲线上、平面整体变换时有 curves；
- SS497 曲线出了坐标范围 x / y（数据曲线逐点查；参数曲线按取样的点、在参数的每组关键取值下查）；
- SS498 参数曲线在某个取样的 t 处没有定义；
- SS499 progress / at 在参数的某组关键取值下不在 [0, 1] 里。
"""

from __future__ import annotations

import bisect
import json
import math
from pathlib import Path

from . import expr

MAX_POINTS = 4096
MAX_BYTES = 4 * 1024 * 1024
PARAM_SAMPLES = 512  # 参数曲线取样的段数
ALONG = ("length", "param")
CURVE_VAR = "t"

Point = tuple[float, float]


class DataError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class Unavailable:
    """data 里读不出来的一项（文件有问题，已经报过；或者没给场景目录，查不了）。用到它的曲线跳过检查。"""

    def __init__(self, src: str, reported: bool):
        self.src, self.reported = src, reported

    def __repr__(self) -> str:
        return f"Unavailable({self.src!r})"


# ---------- 读数据 ----------

def is_ref(value: object) -> bool:
    """data 的一项是不是外部文件引用 {src: …}。"""
    return isinstance(value, dict) and "src" in value


def resolve_src(root: Path, src: object) -> Path:
    """{src} 的路径 → 文件；不合规时抛 DataError（SS490 / SS491）。"""
    if not isinstance(src, str) or not src.strip() or "\x00" in src:
        raise DataError("SS490", f"src 应为相对场景文件的路径字符串，收到 {src!r}")
    rel = Path(src)
    if rel.is_absolute() or src.startswith(("/", "\\")) or (len(src) > 1 and src[1] == ":"):
        raise DataError("SS490", f"src 不能是绝对路径：{src!r}（写相对场景文件的路径）")
    if ".." in rel.parts:
        raise DataError("SS490", f"src 不能用 .. 跑出场景文件所在的目录：{src!r}")
    if rel.suffix.lower() != ".json":
        raise DataError("SS490", f"数据文件只认 .json，{src!r} 是 {rel.suffix or '无后缀'}")
    base = root.resolve()
    target = (base / rel).resolve()
    if not target.is_relative_to(base):
        raise DataError("SS490", f"{src!r} 指到了场景目录外面（符号链接？）")
    if not target.is_file():
        raise DataError("SS491", f"找不到数据文件 {src!r}（相对 {root}）")
    if target.stat().st_size > MAX_BYTES:
        raise DataError("SS491", f"数据文件 {src!r} 大于 {MAX_BYTES // (1024 * 1024)} MB")
    return target


def _no_constant(name: str):
    raise DataError("SS494", f"JSON 里有 {name}：坐标必须是有限数")


def load_src(root: Path, entry: dict) -> object:
    """读 {src} 指向的 JSON；抛 DataError（SS490–SS492、SS494）。"""
    extra = sorted(set(entry) - {"src"})
    if extra:
        raise DataError("SS490", f"外部数据只写 {{src: 路径}}，多了 {extra}")
    target = resolve_src(root, entry["src"])
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DataError("SS491", f"读不了数据文件 {entry['src']!r}：{exc}") from exc
    try:
        return json.loads(text, parse_constant=_no_constant)
    except json.JSONDecodeError as exc:
        raise DataError("SS492", f"{entry['src']!r} 不是合法的 JSON：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}") from exc
    except RecursionError as exc:
        raise DataError("SS492", f"{entry['src']!r} 嵌套太深") from exc


def resolve_data(data: object, root: Path | None, report=None) -> dict:
    """data 段 → 读好外部文件的 dict。读不出来的项换成 Unavailable；给了 report 就把原因报上（每项一次）。
    root 为 None（不知道场景文件在哪）时不读文件，{src} 项都是 Unavailable（不报错，和 clip 的 src 一样）。"""
    out: dict = {}
    for key, value in (data or {}).items() if isinstance(data, dict) else ():
        if not is_ref(value):
            out[key] = value
            continue
        src = str(value.get("src"))
        if root is None:
            out[key] = Unavailable(src, False)
            continue
        try:
            out[key] = load_src(root, value)
        except DataError as exc:
            if report is not None:
                report.error(exc.code, f"data.{key}.src", exc.message)
            out[key] = Unavailable(src, True)
    return out


def load_data(doc: dict, root: Path) -> dict:
    """kit 用：读好 data 段（含外部文件）；有任何一项读不出来就抛 DataError（消息里带键名）。"""
    out = {}
    for key, value in (doc.get("data") or {}).items():
        try:
            out[key] = load_src(root, value) if is_ref(value) else value
        except DataError as exc:
            raise DataError(exc.code, f"data.{key}：{exc.message}") from exc
    return out


def points(value: object, what: str = "数据") -> list[Point]:
    """当曲线用的点列 → [(x, y)]；不合规时抛 DataError（SS493–SS495）。"""
    if not isinstance(value, list):
        raise DataError("SS493", f"{what}应为点列 [[x0, y0], [x1, y1], …]，收到 {type(value).__name__}")
    if len(value) < 2:
        raise DataError("SS493", f"{what}至少要两个点，只有 {len(value)} 个")
    if len(value) > MAX_POINTS:
        raise DataError("SS495", f"{what}有 {len(value)} 个点，最多 {MAX_POINTS} 个")
    out: list[Point] = []
    for i, p in enumerate(value):
        if not (isinstance(p, list) and len(p) == 2
                and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in p)):
            raise DataError("SS493", f"{what}的第 {i} 个点应为 [x, y] 两个数，收到 {p!r}")
        x, y = float(p[0]), float(p[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            raise DataError("SS494", f"{what}的第 {i} 个点 {p!r} 不是有限数")
        out.append((x, y))
    return out


# ---------- 参数曲线 ----------

def parse_param(text: object, names) -> tuple:
    """参数曲线的 x(t) / y(t)：白名单表达式，变量是 t（不能用 x），可以引用 names 里的场景参数。抛 expr.ExprError。"""
    tree = expr.parse(text, set(names) | {CURVE_VAR}, allow_x=False)  # type: ignore[arg-type]
    return tree


def sample(xt: tuple, yt: tuple, domain, env: dict | None = None, n: int = PARAM_SAMPLES) -> list[Point]:
    """参数曲线在 domain 上等分取 n + 1 个点；没有定义的点是 (nan, nan)。"""
    t0, t1 = float(domain[0]), float(domain[1])
    base = dict(env or {})
    out = []
    for k in range(n + 1):
        base[CURVE_VAR] = t0 + (t1 - t0) * k / n
        out.append((expr.evaluate(xt, math.nan, base), expr.evaluate(yt, math.nan, base)))
    return out


# ---------- 沿曲线的位置 ----------

def ruler(pts: list[Point], along: str = "length") -> list[float]:
    """每个点在 [0, 1] 尺子上的位置（单调不减，首 0 尾 1）。按弧长时整条曲线长度为 0 就退回按序号。"""
    n = len(pts)
    if n < 2:
        return [0.0] * n
    if along == "length":
        acc, cum = 0.0, [0.0]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            acc += math.hypot(bx - ax, by - ay)
            cum.append(acc)
        if acc > 0:
            return [c / acc for c in cum[:-1]] + [1.0]
    return [k / (n - 1) for k in range(n)]


def _locate(cum: list[float], s: float) -> tuple[int, float]:
    """尺子上 s 处落在第几段（i：pts[i] → pts[i+1]）、段内比例。"""
    i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(cum) - 2)
    span = cum[i + 1] - cum[i]
    return i, (0.0 if span <= 0 else (s - cum[i]) / span)


def clamp(s: float) -> float:
    return 0.0 if not math.isfinite(s) else min(1.0, max(0.0, s))


def point_at(pts: list[Point], cum: list[float], s: float) -> Point:
    """尺子上 s（夹在 [0, 1]）处的点：分段线性插值。"""
    s = clamp(s)
    if s >= 1.0:
        return pts[-1]
    i, u = _locate(cum, s)
    (ax, ay), (bx, by) = pts[i], pts[i + 1]
    return ax + (bx - ax) * u, ay + (by - ay) * u


def prefix(pts: list[Point], cum: list[float], s: float) -> list[Point]:
    """曲线从起点画到尺子上 s 处的那一段（末点就是 point_at(s)）；s ≤ 0 时是空的。"""
    s = clamp(s)
    if s <= 0.0:
        return []
    if s >= 1.0:
        return list(pts)
    i, _u = _locate(cum, s)
    return list(pts[: i + 1]) + [point_at(pts, cum, s)]


def outside(pts: list[Point], box: tuple[float, float, float, float], tol: float = 1e-9) -> tuple[int, Point] | None:
    """第一个出了 box=(x0, y0, x1, y1) 的点（下标, 点）；都在里面时 None。"""
    x0, y0, x1, y1 = box
    for i, (x, y) in enumerate(pts):
        if not (x0 - tol <= x <= x1 + tol and y0 - tol <= y <= y1 + tol):
            return i, (x, y)
    return None


# ---------- 检查（graph 和 plane 共用） ----------

CURVE_FIELDS = ("data", "x", "y", "domain", "progress", "along", "role")
POINT_FIELDS = ("curve", "at", "label", "role", "dir")


def _value(tree: tuple, env: dict) -> float:
    try:
        return expr.evaluate(tree, math.nan, env)
    except KeyError:  # 用了没声明的参数：已经报过 SS402
        return math.nan


def check_fraction(value: object, path: str, ex, obj_id: str, report, what: str) -> None:
    """progress / at：数或参数表达式，参数取每组关键值（对象在画面上时）都在 [0, 1] 里（SS499）。"""
    if ex is None:
        return
    tree = ex.parse(value, path)
    if tree is None:
        return
    for env in ex.states_for(obj_id):
        v = _value(tree, env)
        if not (math.isfinite(v) and -1e-9 <= v <= 1 + 1e-9):
            report.error("SS499", path, f"参数取 {ex.describe(env)} 时 {what} = {v:g}，应在 0 到 1 之间")
            return


def _range_text(box: tuple[float, float, float, float]) -> str:
    return f"x [{box[0]:g}, {box[2]:g}]、y [{box[1]:g}, {box[3]:g}]"


def check_data(entry: dict, path: str, data: dict, box, report) -> list[Point] | None:
    """{data: 键}：键存在、点列合规、每个点都在 box 里。返回点列（不能用时 None）。"""
    key = entry.get("data")
    if not isinstance(key, str) or key not in data:
        known = "、".join(sorted(data)) or "无"
        report.error("SS496", f"{path}.data", f"data 段里没有 {key!r}（现有：{known}）")
        return None
    value = data[key]
    if isinstance(value, Unavailable):
        return None  # 文件有问题已经报过；不知道场景目录时查不了
    try:
        pts = points(value, f"data.{key} ")
    except DataError as exc:
        report.error(exc.code, f"{path}.data", exc.message)
        return None
    if box is not None:
        hit = outside(pts, box)
        if hit is not None:
            i, (x, y) = hit
            report.error("SS497", f"{path}.data",
                         f"data.{key} 的第 {i} 个点 ({x:g}, {y:g}) 出了坐标范围 {_range_text(box)}")
    return pts


def check_parametric(entry: dict, path: str, ex, obj_id: str, box, report) -> None:
    """{x: "x(t)", y: "y(t)", domain: [t0, t1]}：写法对、取样的点都有定义、都在 box 里（参数取每组关键值）。"""
    missing = [k for k in ("x", "y", "domain") if k not in entry]
    if missing:
        report.error("SS496", path, f"参数曲线缺 {'、'.join(missing)}：写 {{x: \"x(t)\", y: \"y(t)\", domain: [t0, t1]}}")
        return
    dom = entry["domain"]
    if not (isinstance(dom, list) and len(dom) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in dom)
            and dom[0] < dom[1]):
        report.error("SS496", f"{path}.domain", "domain 应为 [t0, t1]：两个有限数，前小后大")
        return
    names = ex.names if ex is not None else set()
    if CURVE_VAR in names:
        report.error("SS496", path, f"场景参数里有 {CURVE_VAR}，和参数曲线的变量 {CURVE_VAR} 重名；把场景参数换个名字")
        return
    trees = []
    for key in ("x", "y"):
        try:
            tree = parse_param(entry[key], names)
        except expr.UnknownName as exc:
            known = "、".join(sorted(names)) or "无"
            report.error("SS402", f"{path}.{key}", f"{entry[key]!r} 里的 {exc.name!r} 不是 {CURVE_VAR}，也不是声明过的参数（params 里有：{known}）")
            return
        except expr.ExprError as exc:
            report.error("SS401", f"{path}.{key}", f"表达式 {entry[key]!r} 写得不对：{exc}（参数曲线的变量是 {CURVE_VAR}，不能用 x）")
            return
        if ex is not None:
            ex.used |= expr.free_names(tree) - {CURVE_VAR}
        trees.append(tree)
    envs = ex.states_for(obj_id) if ex is not None else [{}]
    for env in envs:
        where = f"参数取 {ex.describe(env)} 时，" if ex is not None and ex.names else ""
        try:
            pts = sample(trees[0], trees[1], dom, env)
        except KeyError:
            return
        for k, (x, y) in enumerate(pts):
            if not (math.isfinite(x) and math.isfinite(y)):
                t = dom[0] + (dom[1] - dom[0]) * k / PARAM_SAMPLES
                report.error("SS498", path, f"{where}参数曲线在 t={t:g} 处没有定义")
                return
        hit = outside(pts, box) if box is not None else None
        if hit is not None:
            k, (x, y) = hit
            t = dom[0] + (dom[1] - dom[0]) * k / PARAM_SAMPLES
            report.error("SS497", path, f"{where}参数曲线在 t={t:g} 处到了 ({x:g}, {y:g})，出了坐标范围 {_range_text(box)}")
            return


def check_common(entry: dict, path: str, ex, obj_id: str, report) -> None:
    if "along" in entry and entry["along"] not in ALONG:
        report.error("SS496", f"{path}.along", f"along 应为 {' / '.join(ALONG)} 之一")
    if "progress" in entry:
        check_fraction(entry["progress"], f"{path}.progress", ex, obj_id, report, "progress")
