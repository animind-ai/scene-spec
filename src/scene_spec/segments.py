"""分段播放、残影和常驻公式的语义检查（设计稿 §7.5，错误码 SS440–SS459）。

四个动作：
- ghost：把目标此刻的样子留下一个淡色副本（DIM 色、低不透明度），原对象继续变形；
- unghost：收掉目标留下的所有残影；
- step：子步结束。style.segmented 为真时在这里定格 style.step_hold 秒（旁白在此插入同样长的静音）；
- pin：从此刻起目标常驻：之后不能 hide / move，clear 只清它之后加的装饰，布局求解器把它当作固定占位。

检查按 beats 和动作的书写顺序走一遍，粗略推算每个对象此刻是否可见（show / transform 的目标 / set opacity > 0
算显示，hide 整个对象算隐藏）。组件动作可能自己让东西出现，所以"看不见"只给警告，pin 例外：
常驻的公式必须先出现在画面上。
"""

from __future__ import annotations

from . import selectors
from .report import Report

ACTS = {"ghost", "unghost", "step", "pin"}
NO_TARGET = {"step"}
MAX_GHOSTS = 2  # 同时在画面上的残影超过这个数就警告：残影是"上一步"，不是全部历史
MAX_STEPS = 5  # 一个 beat 里子步超过这个数就警告：核心变形建议拆成 3–5 个子步
DEFAULT_STEP_HOLD = 1.0


def _whole(sel: selectors.Selector) -> bool:
    return sel.span is None and sel.part is None and sel.index is None


def _positive(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def check(doc: dict, report: Report, stats: dict | None = None) -> None:
    style = doc.get("style", {})
    segmented = bool(style.get("segmented", False))
    objects = doc.get("objects", {})
    visible: set[str] = set()
    pinned: dict[str, str] = {k: "top" for k, d in objects.items() if d.get("pin")}  # 对象 → 在哪钉住的
    ghosts: dict[str, int] = {}
    counts = {"steps": 0, "ghosts": 0, "pins": 0}
    step_paths: list[str] = []

    if "step_hold" in style and not segmented:
        report.warning("SS451", "style.step_hold", "step_hold 只在 segmented: true 时起作用")

    for n, beat in enumerate(doc.get("beats", [])):
        beat_steps = 0
        for i, action in enumerate(beat.get("do", [])):
            act = action["act"]
            path = f"beats[{n}].do[{i}]"
            sel = selectors.parse(action["target"]) if "target" in action else None
            if sel is not None and sel.obj not in objects:
                continue  # 引用错误已经由 SS310 报过
            obj = sel.obj if sel else None

            if act == "show" and obj:
                visible.add(obj)
            elif act == "transform" and "to" in action:
                to = selectors.parse(action["to"])
                if to is not None:
                    visible.add(to.obj)
                gone = selectors.transform_replaced(action)
                if gone is not None and gone in pinned:
                    report.error("SS448", f"{path}.from", f"{gone} 已经常驻（{pinned[gone]}），transform 不能替换掉它")
                elif gone is not None and gone in objects:
                    visible.discard(gone)
                    ghosts.pop(gone, None)  # 和 hide 一样：原对象被替换掉，残影跟着收掉
            elif act == "set" and obj and _positive(action.get("args", {}).get("opacity")):
                visible.add(obj)
            elif act in ("hide", "move") and obj:
                if obj in pinned:
                    report.error("SS448", f"{path}.target",
                                 f"{obj} 已经常驻（{pinned[obj]}），不能再 {act}；要换位置请在 pin 之前做")
                    continue
                if act == "hide" and _whole(sel):
                    visible.discard(obj)
                    ghosts.pop(obj, None)  # 原对象收掉，残影跟着收掉
            elif act == "ghost":
                counts["ghosts"] += 1
                if not _whole(sel):
                    report.error("SS440", f"{path}.target", "ghost 的 target 要指向整个对象，不能是片段或子元素")
                    continue
                if obj not in visible:
                    report.warning("SS442", f"{path}.target", f"{obj} 这时可能还没显示，留下的残影会是空的")
                args = action.get("args", {})
                if args.get("place", "stay") == "stay" and ("gap" in args or "scale" in args):
                    report.warning("SS441", f"{path}.args",
                                   "place: stay 时残影和原对象重合，gap / scale 没有意义；要并排对比请写 place")
                ghosts[obj] = ghosts.get(obj, 0) + 1
                live = sum(ghosts.values())
                if live > MAX_GHOSTS:
                    report.warning("SS452", path, f"画面上同时有 {live} 个残影；残影只留上一步，旧的请先 unghost")
            elif act == "unghost":
                if not _whole(sel):
                    report.error("SS440", f"{path}.target", "unghost 的 target 要指向整个对象")
                    continue
                if not ghosts.get(obj):
                    report.error("SS443", f"{path}.target", f"{obj} 现在没有残影可以收")
                ghosts.pop(obj, None)
            elif act == "step":
                counts["steps"] += 1
                beat_steps += 1
                step_paths.append(path)
                if "target" in action:
                    report.error("SS444", f"{path}.target", "step 标记子步结束，不需要 target")
                if "dur" in action:
                    report.error("SS444", f"{path}.dur", "step 的定格时长写在 args.hold 或 style.step_hold，不用 dur")
                at = action.get("at")
                if segmented and isinstance(at, str) and ("@" in at or "+" in at):
                    report.warning("SS446", f"{path}.at",
                                   "定格会在书签或句中某一刻插入静音，把一句话切开；子步边界最好放在句子开头（at: s2）")
                if segmented and ("after" in action or "with" in action):
                    key = "after" if "after" in action else "with"
                    report.warning("SS447", f"{path}.{key}",
                                   "定格挂在 after / with 上，落点由前面动作的时长决定，常常切在句子中间（画面定住、旁白停一秒）；"
                                   "写成 at: s2（下一句开头），这一段最后一句之后的定格可以删掉（段尾本来就是分段点）")
            elif act == "pin":
                counts["pins"] += 1
                if not _whole(sel):
                    report.error("SS447", f"{path}.target", "pin 的 target 要指向整个对象")
                    continue
                if obj in pinned:
                    report.warning("SS449", f"{path}.target", f"{obj} 已经常驻了")
                    continue
                if obj not in visible:
                    report.error("SS450", f"{path}.target", f"{obj} 这时还没显示；常驻的公式要先出现在画面上再 pin")
                    continue
                pinned[obj] = f"beat {beat['id']}"
        if beat_steps > MAX_STEPS:
            report.warning("SS453", f"beats[{n}]",
                           f"这个 beat 有 {beat_steps} 个子步；核心变形拆成 3–5 步就够，太碎反而记不住")

    if step_paths and not segmented:
        report.warning("SS445", step_paths[0],
                       "style.segmented 不是 true：step 只记进 chapters.json，不会定格")
    if stats is not None:
        stats.update({k: v for k, v in counts.items() if v})  # 没用到分段功能的文件统计不变


def step_hold(doc: dict, action: dict) -> float:
    """这个 step 实际定格多久：不分段时为 0；args.hold 优先，其次 style.step_hold，默认 1 秒。"""
    style = doc.get("style", {})
    if not style.get("segmented", False):
        return 0.0
    return float(action.get("args", {}).get("hold", style.get("step_hold", DEFAULT_STEP_HOLD)))
