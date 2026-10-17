"""立体组件 solid 的检查：正方体、长方体、四棱锥、圆柱、圆锥的轴测图，立方体剖成三个四棱锥，水平截面（祖暅原理）。

画法（投影、消隐、截面）在 kit 的 mx/solid.py；这里只检查参数、名字、按动作顺序推演的状态。

    solids:
      widget: solid
      bodies:                       # 名字 → 立体；坐标 x 向右、y 向里、z 向上，at 是底面中心（默认原点）
        C: {cube: 2, at: [-3, 0, 0]}
        P: {pyramid: {base: 2, h: 2}, role: B}          # base: 边长或 [宽, 深]；apex: [dx, dy] 顶点相对底面中心的偏移
        Y: {cylinder: {r: 1, h: 2}, label: '$V$'}
        K: {cone: {r: 1, h: 2}, hidden: true}
      splits:                       # 立方体剖成三个全等的四棱锥：公共顶点是左后上角，底面依次是下、前、右三个面
        s: {body: C, into: [P1, P2, P3], gap: 1, roles: [A, B, C]}
      plane: {bodies: [P, K], z: 0.5, compare: right, labels: ['$S_1$', '$S_2$']}
      view: {azimuth: 30, elevation: 20}

动作：split / apart / join / unsplit（按 splits 的名字），sweep {z}（截平面移到高度 z），compare（截面平铺到旁边比大小）。
错误码 SS460–SS469。
"""

from __future__ import annotations

import re

from .report import Report

KINDS = ("cube", "box", "pyramid", "cylinder", "cone")
BODY_KEYS = {"at", "role", "label", "hidden"}
SPLIT_KEYS = {"body", "into", "gap", "roles"}
PLANE_KEYS = {"bodies", "z", "compare", "labels"}
VIEW_KEYS = {"azimuth", "elevation"}
COMPARE = ("right", "below")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ACTION_ARGS = {
    "split": {"split"}, "apart": {"split"}, "join": {"split"}, "unsplit": {"split"},
    "sweep": {"z"}, "compare": set(),
}
AZIMUTH = (10.0, 80.0)  # 方位角的绝对值：太小侧面看成一条线，太大正面看成一条线
ELEVATION = (10.0, 50.0)


def _num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _pos(v: object) -> bool:
    return _num(v) and v > 0


def _vec(v: object, n: int) -> bool:
    return isinstance(v, list) and len(v) == n and all(_num(c) for c in v)


def body_size(body: dict) -> tuple[str, float, float, float] | None:
    """(种类, 底面宽, 底面深, 高)；写错时返回 None（problems 里已经报过）。"""
    kinds = [k for k in KINDS if k in body]
    if len(kinds) != 1:
        return None
    kind, v = kinds[0], body[kinds[0]]
    if kind == "cube":
        return (kind, v, v, v) if _pos(v) else None
    if kind == "box":
        return (kind, *v) if _vec(v, 3) and all(c > 0 for c in v) else None
    if not isinstance(v, dict):
        return None
    if kind == "pyramid":
        base, h = v.get("base"), v.get("h")
        if _pos(base):
            base = [base, base]
        if not (_vec(base, 2) and all(c > 0 for c in base) and _pos(h)):
            return None
        return kind, base[0], base[1], h
    r, h = v.get("r"), v.get("h")
    return (kind, 2 * r, 2 * r, h) if _pos(r) and _pos(h) else None


def _body_problems(name: str, body: object, path: str) -> list[tuple[str, str, str]]:
    out = []
    if not isinstance(body, dict):
        return [("SS460", path, "立体应为映射，例如 {cube: 2} 或 {cone: {r: 1, h: 2}}")]
    kinds = [k for k in KINDS if k in body]
    if len(kinds) != 1:
        return [("SS460", path, f"要写恰好一种立体：{' / '.join(KINDS)}（现在是 {kinds or '没有'}）")]
    kind = kinds[0]
    extra = set(body) - BODY_KEYS - {kind}
    if extra:
        out.append(("SS460", path, f"不认识的字段 {sorted(extra)}（可用：{kind}、{'、'.join(sorted(BODY_KEYS))}）"))
    v = body[kind]
    hints = {
        "cube": "cube 应为正数（棱长）", "box": "box 应为三个正数 [宽, 深, 高]",
        "pyramid": "pyramid 应为 {base: 边长或 [宽, 深], h: 高, apex?: [dx, dy]}",
        "cylinder": "cylinder 应为 {r: 半径, h: 高}", "cone": "cone 应为 {r: 半径, h: 高}",
    }
    allowed = {"pyramid": {"base", "h", "apex"}, "cylinder": {"r", "h"}, "cone": {"r", "h"}}.get(kind, set())
    if body_size(body) is None or (isinstance(v, dict) and set(v) - allowed):
        out.append(("SS460", f"{path}.{kind}", hints[kind]))
    elif kind == "pyramid" and "apex" in v and not _vec(v["apex"], 2):
        out.append(("SS460", f"{path}.{kind}.apex", "apex 应为 [dx, dy]：顶点相对底面中心的水平偏移"))
    if "at" in body and not _vec(body["at"], 3):
        out.append(("SS460", f"{path}.at", "at 应为 [x, y, z]：底面中心的位置"))
    if "label" in body and not (isinstance(body["label"], str) and body["label"]):
        out.append(("SS460", f"{path}.label", "label 应为非空字符串"))
    if "hidden" in body and not isinstance(body["hidden"], bool):
        out.append(("SS460", f"{path}.hidden", "hidden 应为 true / false"))
    return out


def problems(definition: dict, roles: set[str]) -> list[tuple[str, str, str]]:
    """参数之间的问题：(错误码, 相对对象的路径, 说明)。"""
    out: list[tuple[str, str, str]] = []
    bodies = definition.get("bodies") if isinstance(definition.get("bodies"), dict) else {}
    names: dict[str, str] = {}
    for name, body in bodies.items():
        path = f"bodies.{name}"
        if not isinstance(name, str) or not NAME.match(name):
            out.append(("SS461", path, "名字要以字母或下划线开头，只含字母、数字、下划线"))
        names[name] = path
        out += _body_problems(name, body, path)
        if isinstance(body, dict) and "role" in body and body["role"] not in roles:
            out.append(("SS460", f"{path}.role", f"role 应为 {'/'.join(sorted(roles))} 之一"))

    splits = definition.get("splits") if isinstance(definition.get("splits"), dict) else {}
    used: dict[str, str] = {}
    for sname, sp in splits.items():
        path = f"splits.{sname}"
        if not isinstance(sp, dict):
            out.append(("SS462", path, "应为 {body, into: [三个名字], gap?}"))
            continue
        if set(sp) - SPLIT_KEYS:
            out.append(("SS462", path, f"不认识的字段 {sorted(set(sp) - SPLIT_KEYS)}"))
        body = sp.get("body")
        size = body_size(bodies[body]) if body in bodies and isinstance(bodies[body], dict) else None
        if body not in bodies:
            out.append(("SS462", f"{path}.body", f"没有立体 {body}"))
        elif size is not None and size[0] != "cube":
            out.append(("SS462", f"{path}.body", f"{body} 是 {size[0]}；只有正方体能剖成三个全等的四棱锥"))
        elif body in used:
            out.append(("SS462", f"{path}.body", f"{body} 已经在 {used[body]} 里剖过"))
        else:
            used[body] = path
        into = sp.get("into")
        if not (isinstance(into, list) and len(into) == 3 and all(isinstance(n, str) for n in into)):
            out.append(("SS462", f"{path}.into", "into 应为三个名字（底面依次是下、前、右三个面的四棱锥）"))
        else:
            for n in into:
                if not NAME.match(n):
                    out.append(("SS461", f"{path}.into", f"名字 {n!r} 不合法"))
                elif n in names:
                    out.append(("SS461", f"{path}.into", f"名字 {n} 和 {names[n]} 重复（立体和剖出来的块共用名字）"))
                names[n] = f"{path}.into"
        roles_ = sp.get("roles")
        if roles_ is not None and not (isinstance(roles_, list) and len(roles_) == 3 and all(r in roles for r in roles_)):
            out.append(("SS462", f"{path}.roles", f"roles 应为三个角色（{'/'.join(sorted(roles))}），默认 [A, B, C]"))
        if "gap" in sp and not _pos(sp["gap"]):
            out.append(("SS462", f"{path}.gap", "gap 应为正数：apart 时每块沿底面法向挪开多远（立体坐标，默认半个棱长）"))
        elif "gap" in sp and size is not None and sp["gap"] > 2 * size[1]:
            out.append(("SS462", f"{path}.gap", f"gap 太大（棱长 {size[1]:g}，最多 {2 * size[1]:g}）：排版要为挪开的块留位置"))

    plane = definition.get("plane")
    if plane is not None:
        out += _plane_problems(plane, bodies)

    view = definition.get("view")
    if view is not None:
        if not isinstance(view, dict) or set(view) - VIEW_KEYS:
            out.append(("SS464", "view", "view 应为 {azimuth?, elevation?}（度）"))
        else:
            az, el = view.get("azimuth", 30), view.get("elevation", 20)
            if not _num(az) or not AZIMUTH[0] <= abs(az) <= AZIMUTH[1]:
                out.append(("SS464", "view.azimuth", f"azimuth 的绝对值应在 {AZIMUTH[0]:g}°–{AZIMUTH[1]:g}°"
                            "（太小或太大时有的面看成一条线，棱会叠在一起）"))
            if not _num(el) or not ELEVATION[0] <= el <= ELEVATION[1]:
                out.append(("SS464", "view.elevation", f"elevation 应在 {ELEVATION[0]:g}°–{ELEVATION[1]:g}°"))
    return out


def z_range(definition: dict) -> tuple[float, float] | None:
    """截平面能走的高度范围：plane.bodies 里最低的底面到最高的顶。"""
    plane, bodies = definition.get("plane"), definition.get("bodies")
    if not isinstance(plane, dict) or not isinstance(bodies, dict) or not isinstance(plane.get("bodies"), list):
        return None
    lo, hi = [], []
    for name in plane["bodies"]:
        body = bodies.get(name) if isinstance(name, str) else None
        size = body_size(body) if isinstance(body, dict) else None
        if size is None:
            return None
        z0 = body["at"][2] if _vec(body.get("at"), 3) else 0.0
        lo.append(z0)
        hi.append(z0 + size[3])
    return (min(lo), max(hi)) if lo else None


def _plane_problems(plane: object, bodies: dict) -> list[tuple[str, str, str]]:
    if not isinstance(plane, dict):
        return [("SS463", "plane", "plane 应为 {bodies: [名字…], z?, compare?, labels?}")]
    out = []
    if set(plane) - PLANE_KEYS:
        out.append(("SS463", "plane", f"不认识的字段 {sorted(set(plane) - PLANE_KEYS)}"))
    names = plane.get("bodies")
    if not (isinstance(names, list) and names and all(isinstance(n, str) for n in names)):
        return out + [("SS463", "plane.bodies", "bodies 应为非空的立体名字列表（截平面扫过哪几个立体）")]
    for n in names:
        if n not in bodies:
            out.append(("SS463", "plane.bodies", f"没有立体 {n}（剖出来的块不能放进 plane）"))
    if len(set(names)) != len(names):
        out.append(("SS463", "plane.bodies", "有重复的名字"))
    if "compare" in plane and plane["compare"] not in COMPARE:
        out.append(("SS463", "plane.compare", f"compare 应为 {' / '.join(COMPARE)} 之一：截面平铺在立体的哪一边"))
    labels = plane.get("labels")
    if labels is not None:
        if not (isinstance(labels, list) and all(isinstance(s, str) and s for s in labels)):
            out.append(("SS463", "plane.labels", "labels 应为字符串列表，每个截面一个"))
        elif len(labels) != len(names):
            out.append(("SS463", "plane.labels", f"labels 有 {len(labels)} 个，bodies 有 {len(names)} 个"))
        elif "compare" not in plane:
            out.append(("SS463", "plane.labels", "labels 写在平铺的截面下面：要同时写 compare"))
    if "z" in plane and not _num(plane["z"]):
        out.append(("SS463", "plane.z", "z 应为数：截平面一开始的高度"))
    elif not out:
        zr = z_range({"plane": plane, "bodies": bodies})
        if zr and "z" in plane and not zr[0] <= plane["z"] <= zr[1]:
            out.append(("SS463", "plane.z", f"z={plane['z']:g} 不在 {zr[0]:g} 到 {zr[1]:g} 之间（截平面碰不到立体）"))
    return out


# ---------- 动作：按顺序推演 ----------

def start_state(definition: dict) -> dict:
    splits = definition.get("splits") if isinstance(definition.get("splits"), dict) else {}
    return {"split": {name: "whole" for name in splits}, "plane": False, "compared": False}


def check_action(act: str, args: dict, definition: dict, state: dict, report: Report, path: str) -> None:
    allowed = ACTION_ARGS[act]
    for key in sorted(set(args) - allowed):
        report.error("SS281", f"{path}.args.{key}", f"{act} 没有参数 {key}（可用：{'、'.join(sorted(allowed)) or '无'}）")
    if act in ("split", "apart", "join", "unsplit"):
        name = args.get("split")
        if name not in state["split"]:
            known = "、".join(state["split"]) or "没有"
            report.error("SS465", f"{path}.args.split", f"{act} 要写 split：splits 里的名字（现在有：{known}）")
            return
        now = state["split"][name]
        need = {"split": ("whole",), "apart": ("joined",), "join": ("apart",), "unsplit": ("joined",)}[act]
        hint = {
            "whole": "还没剖开（先 split）", "joined": "三块现在拼在一起",
            "apart": "三块现在分开着（先 join）",
        }
        if now not in need:
            report.error("SS466", path, f"{act} {name}：{hint[now]}")
            return
        state["split"][name] = {"split": "joined", "apart": "apart", "join": "joined", "unsplit": "whole"}[act]
        return
    if not isinstance(definition.get("plane"), dict):
        report.error("SS467", path, f"{act} 要先在对象上写 plane: {{bodies: [...]}}")
        return
    if act == "sweep":
        z = args.get("z")
        zr = z_range(definition)
        if not _num(z):
            report.error("SS467", f"{path}.args.z", "sweep 需要 z：截平面移到的高度（立体坐标）")
        elif zr and not zr[0] <= z <= zr[1]:
            report.error("SS467", f"{path}.args.z", f"z={z:g} 不在 {zr[0]:g} 到 {zr[1]:g} 之间（截平面碰不到立体）")
        state["plane"] = True
        return
    # compare
    if "compare" not in definition["plane"]:
        report.error("SS468", path, "compare 要在 plane 里写 compare: right / below（排版时给平铺的截面留位置）")
    elif not state["plane"]:
        report.error("SS468", path, "截平面还没出现：先 sweep 到一个高度")
    elif state["compared"]:
        report.error("SS468", path, "截面已经平铺出来了；之后的 sweep 会让它们跟着变")
    state["compared"] = True


def register(registry: dict) -> None:
    from .textmarks import ROLES
    from .widgets import Exposed, Widget

    def _dict(what: str):
        def check(value: object) -> str | None:
            return None if isinstance(value, dict) and value else f"应为非空映射（{what}）"

        return check

    def expose(definition: dict, data: dict) -> Exposed:
        bodies = definition.get("bodies") if isinstance(definition.get("bodies"), dict) else {}
        splits = definition.get("splits") if isinstance(definition.get("splits"), dict) else {}
        spans = {n for n in bodies if isinstance(n, str)}
        for sp in splits.values():
            if isinstance(sp, dict) and isinstance(sp.get("into"), list):
                spans |= {n for n in sp["into"] if isinstance(n, str)}
        exposed = Exposed(spans=spans, items=len(bodies))
        plane = definition.get("plane")
        if isinstance(plane, dict) and isinstance(plane.get("bodies"), list):
            n = len(plane["bodies"])
            exposed.parts = {"plane": 1, "section": n}
            if "compare" in plane:
                exposed.parts["flat"] = n
        exposed.state = start_state(definition)
        return exposed

    def validate(ctx, report: Report, path: str) -> None:
        for code, sub, message in problems(ctx.definition, set(ROLES)):
            report.error(code, f"{path}.{sub}", message)

    def action(act: str):
        def check(args: dict, ctx, report: Report, path: str) -> None:
            check_action(act, args, ctx.definition, ctx.exposed.state, report, path)

        return check

    registry["solid"] = Widget(
        "solid",
        params={
            "bodies": (True, _dict("名字 → 立体")),
            "splits": (False, _dict("名字 → {body, into, gap?, roles?}")),
            "plane": (False, lambda v: None if isinstance(v, dict) else "应为 {bodies, z?, compare?, labels?}"),
            "view": (False, lambda v: None if isinstance(v, dict) else "应为 {azimuth?, elevation?}"),
        },
        expose=expose,
        actions={act: action(act) for act in ACTION_ARGS},
        validate=validate,
    )
