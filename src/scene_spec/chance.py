"""随机试验的组件：抛硬币的频率折线（coin_flips）、高尔顿板（galton）、样本空间方格（outcomes）。

随机数只从这里来：kit 画的和检查器核的是同一串（random.Random(seed)，Mersenne Twister 在各 Python 版本里给出同样的
random() 序列）。场景文件写 seed，旁白里说的数（前十次几个正面、每个格子落了几个球）用动作的 expect 参数写出来，
检查器按同一个 seed 重算，对不上就报 SS261。
"""

from __future__ import annotations

import random
from math import comb

from .report import Report
from .textmarks import ROLES


def coin_flips(seed: int, n: int, p: float = 0.5) -> list[int]:
    """n 次抛掷，1 = 正面。"""
    rng = random.Random(seed)
    return [1 if rng.random() < p else 0 for _ in range(n)]


def galton_paths(seed: int, balls: int, rows: int) -> list[list[int]]:
    """每个球在 rows 层钉子上各往左（0）或往右（1）；落进第 sum(path) 个格子。"""
    rng = random.Random(seed)
    return [[1 if rng.random() < 0.5 else 0 for _ in range(rows)] for _ in range(balls)]


def galton_counts(seed: int, balls: int, rows: int, first: int = 0) -> list[int]:
    """第 first 个球起、balls 个球落进各格的个数。"""
    paths = galton_paths(seed, first + balls, rows)[first:]
    counts = [0] * (rows + 1)
    for path in paths:
        counts[sum(path)] += 1
    return counts


def binomial(rows: int) -> list[int]:
    """走到每个格子的路径数（杨辉三角的第 rows 行）。"""
    return [comb(rows, k) for k in range(rows + 1)]


# ---------- 检查器登记 ----------

def _int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def register(registry: dict, Widget, Exposed, unknown_args) -> None:  # noqa: N803
    def pos_int(v: object) -> str | None:
        return None if _int(v) and v > 0 else "应为正整数"

    def nonneg_int(v: object) -> str | None:
        return None if _int(v) and v >= 0 else "应为非负整数"

    def prob(v: object) -> str | None:
        return None if _num(v) and 0 < v < 1 else "应为 0 到 1 之间的数"

    def role_of(args: dict, report: Report, path: str) -> None:
        if "role" in args and args["role"] not in ROLES:
            report.error("SS281", f"{path}.args.role", f"role 应为 {'/'.join(sorted(ROLES))} 之一")

    # ---- coin_flips：频率折线 ----
    # 参数 n（最多抛几次）、seed、p（默认 0.5）、runs（另外几条折线最多几条，默认 0）。横轴是抛的次数（对数刻度）、纵轴是正面的频率。
    # 动作 flip {to, expect}：折线画到第 to 次（只能往后），expect 是到这时的正面数，右上角写出"正面 h / to"；
    # runs {count}：再画 count 条 seed+1、seed+2 … 的折线（淡色，一次画到 n）；band：画出 p ± 1/√k 的漏斗（大多数折线落在里面）。

    def coin_expose(definition: dict, data: dict) -> Exposed:
        return Exposed(parts={"line": 1, "runs": 1, "band": 1, "axes": 1}, state={"at": 0, "runs": 0})

    def flips(ctx) -> list[int] | None:
        d = ctx.definition
        if pos_int(d.get("n")) or not _int(d.get("seed")):
            return None
        return coin_flips(d["seed"], d["n"], d.get("p", 0.5))

    def flip(args: dict, ctx, report: Report, path: str) -> None:
        to, n = args.get("to"), ctx.definition.get("n")
        unknown_args(args, {"to", "expect"}, "flip", report, path)
        if not _int(to) or to < 1 or (_int(n) and to > n):
            report.error("SS281", f"{path}.args.to", f"flip 需要 to：画到第几次（1 到 n {n}）")
            return
        state = ctx.exposed.state
        if to <= state["at"]:
            report.error("SS281", f"{path}.args.to", f"折线已经画到第 {state['at']} 次，to 要更大")
        state["at"] = max(state["at"], to)
        seq = flips(ctx)
        if "expect" in args and seq is not None and sum(seq[:to]) != args["expect"]:
            report.error("SS261", f"{path}.args.expect", f"seed {ctx.definition['seed']} 前 {to} 次有 {sum(seq[:to])} 个正面，不是 {args['expect']}")

    def runs(args: dict, ctx, report: Report, path: str) -> None:
        count, room = args.get("count"), ctx.definition.get("runs", 0)
        unknown_args(args, {"count"}, "runs", report, path)
        state = ctx.exposed.state
        if not _int(count) or count < 1 or (_int(room) and state["runs"] + count > room):
            report.error("SS281", f"{path}.args.count", f"runs 需要 count：再画几条（一共不超过参数 runs {room}）")
            return
        state["runs"] += count

    def band(args: dict, ctx, report: Report, path: str) -> None:
        unknown_args(args, set(), "band", report, path)

    registry["coin_flips"] = Widget(
        "coin_flips",
        params={"n": (True, pos_int), "seed": (True, nonneg_int), "p": (False, prob), "runs": (False, nonneg_int)},
        expose=coin_expose,
        actions={"flip": flip, "runs": runs, "band": band},
    )

    # ---- galton：高尔顿板 ----
    # 参数 rows（几层钉子）、balls（最多落几个球，排版按它的期望高度留地方）、seed。
    # 动作 drop {count, expect}：接着落 count 个球（expect 是这一批之后各格累计的个数）；path {ball, role}：把第 ball 个球
    # （从 0 数，要已经落下）走过的路描出来；pascal：在钉子和格子下面写路径数（杨辉三角）；expect：按二项分布画出每格的期望高度；
    # flat：画出"每格一样多"的那条水平线（非例）；erase：收起描线、数字和轮廓（clear 是内置动作）。

    def galton_expose(definition: dict, data: dict) -> Exposed:
        return Exposed(parts={"board": 1, "balls": 1, "marks": 1}, state={"dropped": 0})

    def drop(args: dict, ctx, report: Report, path: str) -> None:
        d, state = ctx.definition, ctx.exposed.state
        count = args.get("count")
        unknown_args(args, {"count", "expect"}, "drop", report, path)
        if not _int(count) or count < 1:
            report.error("SS281", f"{path}.args.count", "drop 需要 count：再落几个球（正整数）")
            return
        total = state["dropped"] + count
        if _int(d.get("balls")) and total > d["balls"]:
            report.error("SS262", f"{path}.args.count", f"一共落 {total} 个球，超过参数 balls {d['balls']}")
        state["dropped"] = total
        exp = args.get("expect")
        if exp is not None:
            if not (isinstance(exp, list) and all(_int(x) for x in exp)):
                report.error("SS281", f"{path}.args.expect", "expect 应为每格累计的球数（整数列表）")
            elif _int(d.get("seed")) and _int(d.get("rows")):
                got = galton_counts(d["seed"], total, d["rows"])
                if got != exp:
                    report.error("SS261", f"{path}.args.expect", f"seed {d['seed']} 落 {total} 个球，各格是 {got}，不是 {exp}")

    def gpath(args: dict, ctx, report: Report, path: str) -> None:
        ball = args.get("ball")
        unknown_args(args, {"ball", "role"}, "path", report, path)
        role_of(args, report, path)
        if not _int(ball) or not 0 <= ball < ctx.exposed.state["dropped"]:
            report.error("SS281", f"{path}.args.ball", f"path 需要 ball：已经落下的第几个球（0 到 {ctx.exposed.state['dropped'] - 1}）")

    def no_args(act: str):
        def check(args: dict, ctx, report: Report, path: str) -> None:
            unknown_args(args, set(), act, report, path)
        return check

    registry["galton"] = Widget(
        "galton",
        params={"rows": (True, pos_int), "balls": (True, pos_int), "seed": (True, nonneg_int)},
        expose=galton_expose,
        actions={"drop": drop, "path": gpath, "pascal": no_args("pascal"), "expect": no_args("expect"),
                 "flat": no_args("flat"), "erase": no_args("erase")},
    )

    # ---- outcomes：样本空间方格 ----
    # 参数 rows、cols、labels（每格的字，按行从上往下、每行从左往右；可以混排公式）、row_labels / col_labels（可选，表头）。
    # 格子用编号（0 起，按读的顺序）或格子里的字指。动作 shade {cells, role}：垫色；unshade {cells}（不写 = 全部）；
    # strike {cells}：这几格淡下去并打叉（"已知"把它们排除出样本空间）；restore {cells}：取消；frame {cells, role}：把这几格（剩下的样本空间）
    # 框起来，一次一个框，新的替换旧的；unframe。

    def outcomes_expose(definition: dict, data: dict) -> Exposed:
        n = definition.get("rows", 0) * definition.get("cols", 0) if _int(definition.get("rows")) and _int(definition.get("cols")) else 0
        return Exposed(parts={"cell": n, "frame": 1}, state={"struck": set()})

    def cells_arg(args: dict, ctx, report: Report, path: str, required: bool = True) -> list[int] | None:
        d = ctx.definition
        n = d["rows"] * d["cols"] if _int(d.get("rows")) and _int(d.get("cols")) else None
        labels = d.get("labels") or []
        v = args.get("cells")
        if v is None:
            if required:
                report.error("SS281", f"{path}.args", "需要 cells：格子编号或格子里的字，列表")
            return None
        items = v if isinstance(v, list) else [v]
        out = []
        for c in items:
            if _int(c) and n is not None and 0 <= c < n:
                out.append(c)
            elif isinstance(c, str) and c in labels:
                out.append(labels.index(c))
            else:
                report.error("SS281", f"{path}.args.cells", f"没有格子 {c!r}（编号 0 到 {None if n is None else n - 1}，或格子里的字）")
                return None
        return out

    def shade(args: dict, ctx, report: Report, path: str) -> None:
        cells_arg(args, ctx, report, path)
        role_of(args, report, path)
        unknown_args(args, {"cells", "role"}, "shade", report, path)

    def unshade(args: dict, ctx, report: Report, path: str) -> None:
        cells_arg(args, ctx, report, path, required=False)
        unknown_args(args, {"cells"}, "unshade", report, path)

    def strike(args: dict, ctx, report: Report, path: str) -> None:
        cells = cells_arg(args, ctx, report, path)
        unknown_args(args, {"cells"}, "strike", report, path)
        ctx.exposed.state["struck"].update(cells or [])

    def restore(args: dict, ctx, report: Report, path: str) -> None:
        cells = cells_arg(args, ctx, report, path, required=False)
        unknown_args(args, {"cells"}, "restore", report, path)
        if cells is None:
            ctx.exposed.state["struck"].clear()
        else:
            ctx.exposed.state["struck"].difference_update(cells)

    def frame(args: dict, ctx, report: Report, path: str) -> None:
        cells_arg(args, ctx, report, path)
        role_of(args, report, path)
        unknown_args(args, {"cells", "role"}, "frame", report, path)

    def outcomes_validate(ctx, report: Report, path: str) -> None:
        d = ctx.definition
        if not (_int(d.get("rows")) and _int(d.get("cols"))):
            return
        labels = d.get("labels")
        if labels is not None and (not isinstance(labels, list) or len(labels) != d["rows"] * d["cols"]
                                   or not all(isinstance(x, str) for x in labels)):
            report.error("SS202", f"{path}.labels", f"labels 应为 {d['rows'] * d['cols']} 个字符串（按行，每行从左往右）")
        for key, size in (("row_labels", d["rows"]), ("col_labels", d["cols"])):
            v = d.get(key)
            if v is not None and (not isinstance(v, list) or len(v) != size or not all(isinstance(x, str) for x in v)):
                report.error("SS202", f"{path}.{key}", f"{key} 应为 {size} 个字符串")

    registry["outcomes"] = Widget(
        "outcomes",
        params={"rows": (True, pos_int), "cols": (True, pos_int), "labels": (False, lambda v: None),
                "row_labels": (False, lambda v: None), "col_labels": (False, lambda v: None)},
        expose=outcomes_expose,
        actions={"shade": shade, "unshade": unshade, "strike": strike, "restore": restore, "frame": frame,
                 "unframe": no_args("unframe")},
        validate=outcomes_validate,
    )
