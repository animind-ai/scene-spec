"""第二层：语义检查。只在结构检查通过之后运行，所以可以放心假定字段类型正确。

检查内容（设计稿 §8）：
- 引用的对象、片段、子元素、句子、书签都存在；
- 动作是内置动作或目标组件提供的动作，参数齐全；
- 不出现色值，不出现 ${...} 表达式（参数表达式只能写在指定的属性里，见 params.py）；
- 场景参数、tween 动作、readout 对象（SS400–SS419，见 params.py）；
- 产品线要求的洞察卡片字段齐全，并且被 beat 的 shows 标注引用；
- 绝对坐标：insight 线报错，其余警告并计数。
"""

from __future__ import annotations

import re

from . import clips, curves, quality, segments, selectors, widgets
from . import params as P
from .report import Report
from .textmarks import parse_object_text, parse_say_text

BUILTIN_ACTS = {
    "show", "hide", "transform", "move", "focus", "unfocus", "mark", "unmark",
    "underline", "circle", "cross", "clear", "set", "camera", "hold", "tween",
} | segments.ACTS
NEEDS_TARGET = BUILTIN_ACTS - {"transform", "camera", "hold", "tween"} - segments.NO_TARGET
READOUT_KEYS = ("value", "label", "digits", "format")
SHAPE_KEYS = ("side", "radius", "points")
SHAPE_PARAMS = {  # 每种图形可用的几何参数（label、role 每种都能用）
    "circle": ("radius",), "dot": ("radius",), "square": ("side",), "rectangle": ("side",),
    "polygon": ("points",), "line": ("side", "points"), "arrow": ("side", "points"),
}


def shape_length(value: object) -> float | None:
    """side 的长度：正数或写成数字的字符串；不是就 None。"""
    if isinstance(value, bool):
        return None
    try:
        x = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return x if x > 0 and x == x and x != float("inf") else None


KNOWN_THEMES = {"paper", "chalk", "jade", "xuan", "blueprint", "riso", "classroom"}
LAYOUT_REFS = ("below", "above", "left_of", "right_of", "within", "over")
DEMO_WORDS = ("演示", "不是证明", "不算证明", "并非证明", "demonstration", "not a proof")  # 后两个给英文版（localize 成 en）
CAMERA_ARGS = {"zoom", "fit", "margin", "reset"}
CAMERA_EXEMPT_REGIONS = ("top", "footer")  # 这些区域和钉住的对象不跟镜头走

REQUIRED_PEDAGOGY = {
    "insight": ("insight", "misconception", "non_example", "status", "landing"),
    "worked": ("insight", "status"),
    "contest": ("status",),
    "lecture": (),  # 大学课程讲座（docs/cs-lecture.md）：一讲很长、讲很多点，不要求教学字段
}

_COLOR = re.compile(r"^(#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|(rgb|rgba|hsl|hsla)\(.*\))$")


class _Checker:
    def __init__(self, doc: dict, report: Report, root=None, timing=None, allowlist=None):
        self.doc = doc
        self.r = report
        self.root = root
        self.timing = timing
        self.allowlist = allowlist
        self.meta = doc["meta"]
        self.line = self.meta["line"]
        self.data = curves.resolve_data(doc.get("data", {}), root, report)  # {src} 项读成文件里的内容（SS490–SS492）
        self.objects: dict[str, dict] = doc.get("objects", {})
        self.beats: list[dict] = doc["beats"]
        self.exposed: dict[str, widgets.Exposed] = {}
        self.referenced: set[str] = set()
        # All actions addressed to a widget, used for semantic checks that
        # cannot be inferred from the widget definition alone (for example an
        # empty plane that only shows the renderer's default axes/grid).
        self.widget_actions: dict[str, list[str]] = {}
        self.ex = P.ExprChecker(doc, report)
        self.stats = {
            "beats": len(self.beats),
            "sentences": 0,
            "actions": 0,
            "custom_beats": 0,
            "absolute_coords": 0,
            "unregistered_widgets": 0,
        }

    # ---------- 全文扫描 ----------

    def scan_literals(self, node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                self.scan_literals(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                self.scan_literals(value, f"{path}[{i}]")
        elif isinstance(node, str):
            if _COLOR.match(node.strip()):
                self.r.error("SS350", path, f"不允许直接写颜色 {node!r}，请用语义角色（FG/A/B/C/HL/NO/DIM）")
            if "${" in node:
                self.r.error("SS351", path, "不支持表达式 ${...}；data 只放字面量，需要计算的内容请用脚本生成")

    # ---------- 对象 ----------

    def check_objects(self) -> None:
        # 先算出所有对象暴露的子元素，再检查布局引用（布局可以引用后声明的对象）
        for obj_id, definition in self.objects.items():
            path = f"objects.{obj_id}"
            if "widget" in definition:
                self.check_widget(obj_id, definition, path)
            else:
                self.check_basic(obj_id, definition, path)
        for obj_id, definition in self.objects.items():
            self.check_layout(obj_id, definition, f"objects.{obj_id}")
        self.check_groups()

    def check_groups(self) -> None:
        """group 嵌套不能成环；一个对象只能是一个 group 的成员（它在画面上只有一份）。"""
        owner: dict[str, str] = {}
        for obj_id, definition in self.objects.items():
            if definition.get("type") != "group" or "widget" in definition:
                continue
            children = definition.get("children") or []
            for child in sorted({c for c in children if children.count(c) > 1}):
                self.r.error("SS344", f"objects.{obj_id}.children", f"{child} 在 {obj_id} 的成员里重复出现；一个对象在画面上只有一份，只能写一次")
            for child in dict.fromkeys(children):
                if child in owner and child != obj_id:
                    self.r.error("SS344", f"objects.{obj_id}.children", f"{child} 已经是 {owner[child]} 的成员，不能再放进 {obj_id}")
                owner.setdefault(child, obj_id)
        for start in owner:
            seen, node = {start}, owner[start]
            while node in owner:
                if node in seen:
                    self.r.error("SS344", f"objects.{node}.children", f"group 嵌套成环（{node} 间接包含了自己）")
                    break
                seen.add(node)
                node = owner[node]

    def check_basic(self, obj_id: str, definition: dict, path: str) -> None:
        exposed = widgets.Exposed()
        kind = definition["type"]
        if kind != "readout":
            for key in READOUT_KEYS:
                if key in definition and not (kind == "shape" and key == "label"):
                    self.r.error("SS410", f"{path}.{key}", f"{key} 只用于 type: readout")
        if kind == "readout":
            P.check_readout(obj_id, definition, path, self.ex, self.r)
        elif kind == "text":
            if "text" not in definition:
                self.r.error("SS204", path, "text 对象需要 text")
            else:
                parsed = parse_object_text(definition["text"])
                for problem in parsed.problems:
                    self.r.error("SS210", f"{path}.text", problem)
                ids = [s.id for s in parsed.spans if s.id]
                for dup in {i for i in ids if ids.count(i) > 1}:
                    self.r.error("SS211", f"{path}.text", f"片段 #{dup} 重复")
                exposed.spans = set(ids)
        elif kind == "math" and "tex" not in definition:
            self.r.error("SS204", path, "math 对象需要 tex")
        elif kind == "shape":
            if "shape" not in definition:
                self.r.error("SS204", path, "shape 对象需要 shape")
            else:
                self.check_shape(definition, path)
        elif kind == "group":
            children = definition.get("children")
            if not children:
                self.r.error("SS204", path, "group 对象需要 children")
            else:
                for child in children:
                    if child not in self.objects:
                        self.r.error("SS310", f"{path}.children", f"没有对象 {child!r}")
                    elif child == obj_id:
                        self.r.error("SS341", f"{path}.children", "group 不能包含自己")
                    self.referenced.add(child)
                exposed.items = len(children)
        if kind != "shape":
            for key in SHAPE_KEYS:
                if key in definition:
                    self.r.error("SS205", f"{path}.{key}", f"{key} 只用于 type: shape")
        self.exposed[obj_id] = exposed

    def check_shape(self, definition: dict, path: str) -> None:
        """type: shape 的几何参数：每种图形只认自己的那几个，数值要能用。"""
        shape = definition["shape"]
        allowed = SHAPE_PARAMS.get(shape, ())
        for key in SHAPE_KEYS:
            if key in definition and key not in allowed:
                self.r.error("SS205", f"{path}.{key}", f"shape: {shape} 不用 {key}（可用：{'、'.join(allowed) or '无'}）")
        side = definition.get("side")
        if "side" in allowed and side is not None:
            if shape == "rectangle":
                if not (isinstance(side, list) and len(side) == 2):
                    self.r.error("SS205", f"{path}.side", "rectangle 的 side 写 [宽, 高]")
            elif shape_length(side) is None:
                self.r.error("SS205", f"{path}.side", f"side 要是正数，收到 {side!r}")
        points = definition.get("points")
        if "points" in allowed and points is not None:
            need = 3 if shape == "polygon" else 2
            if shape == "polygon" and len(points) < 3:
                self.r.error("SS205", f"{path}.points", "polygon 至少要三个顶点")
            elif shape != "polygon" and len(points) != 2:
                self.r.error("SS205", f"{path}.points", f"{shape} 的 points 是起点和终点两个点")
            elif len({tuple(p) for p in points}) < need:
                self.r.error("SS205", f"{path}.points", "points 里有重合的点")
            if "side" in definition and shape != "polygon":
                self.r.error("SS205", f"{path}.side", "points 和 side 只写一个")
        if shape == "polygon" and points is None:
            self.r.error("SS204", path, "polygon 需要 points")
        if "label" in definition:
            parsed = parse_object_text(definition["label"])
            for problem in parsed.problems:
                self.r.error("SS210", f"{path}.label", problem)

    def check_widget(self, obj_id: str, definition: dict, path: str) -> None:
        widget = widgets.lookup(definition["widget"])
        if widget is None:
            self.stats["unregistered_widgets"] += 1
            self.r.warning("SS370", f"{path}.widget", f"组件 {definition['widget']!r} 未登记，参数和引用无法校验")
            self.exposed[obj_id] = None  # 未知：放行所有子元素引用
            return
        widgets.check_params(widget, definition, self.r, path)
        exposed = widget.expose(definition, self.data)
        self.exposed[obj_id] = exposed
        if widget.validate:
            widget.validate(widgets.WidgetContext(obj_id, definition, self.data, exposed, self.ex), self.r, path)

    def check_layout(self, obj_id: str, definition: dict, path: str) -> None:
        for key in LAYOUT_REFS:
            if key in definition:
                self.resolve(definition[key], f"{path}.{key}", self_id=obj_id)
        for axis, ref in (definition.get("align") or {}).items():
            self.resolve(ref, f"{path}.align.{axis}", self_id=obj_id)
        if definition.get("pin"):
            self.referenced.add(obj_id)
        for kind in ("cross", "overlap"):
            targets = (definition.get("allow") or {}).get(kind)
            for i, other in enumerate(targets if isinstance(targets, list) else []):
                if other not in self.objects:
                    self.r.error("SS343", f"{path}.allow.{kind}[{i}]", f"没有对象 {other!r}")
        if "at" in definition:
            self.stats["absolute_coords"] += 1
            if self.line == "insight":
                self.r.error("SS342", f"{path}.at", "洞察系列不允许绝对坐标，请改用布局约束，或把这部分画面放进 custom beat")
            else:
                self.r.warning("SS342", f"{path}.at", "使用了绝对坐标，布局求解器不会管它")

    # ---------- 选择器 ----------

    def resolve(self, text: str, path: str, self_id: str | None = None) -> selectors.Selector | None:
        sel = selectors.parse(text)
        if sel is None:  # 结构层已经保证格式，这里只是保险
            self.r.error("SS310", path, f"选择器 {text!r} 格式不对")
            return None
        if sel.obj not in self.objects:
            self.r.error("SS310", path, f"没有对象 {sel.obj!r}")
            return None
        if self_id is not None and sel.obj == self_id:
            self.r.error("SS341", path, "布局约束不能引用自己")
        self.referenced.add(sel.obj)
        exposed = self.exposed.get(sel.obj, widgets.Exposed())
        if exposed is None:  # 未登记组件
            return sel
        if sel.span is not None and sel.span not in exposed.spans:
            known = "、".join(f"#{s}" for s in sorted(exposed.spans)) or "无"
            self.r.error("SS311", path, f"{sel.obj} 里没有片段 #{sel.span}（现有：{known}）")
        if sel.part is not None:
            if sel.part not in exposed.parts:
                known = "、".join(sorted(exposed.parts)) or "无"
                self.r.error("SS312", path, f"{sel.obj} 没有部件 .{sel.part}（现有：{known}）")
            elif sel.index is not None and sel.index[1] > exposed.parts[sel.part]:
                self.r.error("SS312", path, f"{sel.obj}.{sel.part} 只有 {exposed.parts[sel.part]} 个元素，下标越界")
        if sel.part is None and sel.index is not None:
            if exposed.items is None:
                self.r.error("SS313", path, f"{sel.obj} 不是列表，不能用下标")
            elif sel.index[1] > exposed.items:
                self.r.error("SS313", path, f"{sel.obj} 只有 {exposed.items} 项，下标越界")
        if sel.index is not None and sel.index[0] >= sel.index[1]:
            self.r.error("SS313", path, "切片 i:j 需要 i < j")
        return sel

    # ---------- beats ----------

    def check_beats(self) -> None:
        seen: dict[str, int] = {}
        for n, beat in enumerate(self.beats):
            path = f"beats[{n}]"
            if beat["id"] in seen:
                self.r.error("SS301", f"{path}.id", f"beat id {beat['id']!r} 与 beats[{seen[beat['id']]}] 重复")
            seen[beat["id"]] = n
            if not any(k in beat for k in ("say", "do", "pause", "custom")):
                self.r.warning("SS380", path, "这个 beat 是空的（没有 say、do、pause、custom）")
            if "custom" in beat:
                self.stats["custom_beats"] += 1
            sentences = self.check_say(beat, path)
            self.check_actions(beat, sentences, path)

    def check_say(self, beat: dict, path: str) -> list[tuple[str | None, set[str]]]:
        """返回每句的 (id, 书签集合)。"""
        out: list[tuple[str | None, set[str]]] = []
        ids: set[str] = set()
        for i, sentence in enumerate(beat.get("say", [])):
            self.stats["sentences"] += 1
            spath = f"{path}.say[{i}]"
            sid = sentence.get("id")
            if sid is not None:
                if sid in ids:
                    self.r.error("SS302", f"{spath}.id", f"句子 id {sid!r} 重复")
                if sid.isdigit():
                    self.r.error("SS302", f"{spath}.id", "句子 id 不能是纯数字（会和下标混淆）")
                ids.add(sid)
            marks, problems = parse_say_text(sentence["text"])
            for problem in problems:
                self.r.error("SS303", f"{spath}.text", problem)
            out.append((sid, set(marks)))
        return out

    def check_time(self, ref: object, sentences: list, path: str) -> None:
        if isinstance(ref, int):
            sentence_ref, mark = str(ref), None
        else:
            body = ref.split("+", 1)[0]
            sentence_ref, _, mark = body.partition("@")
            mark = mark or None
        if not sentences:
            if sentence_ref != "0" or mark is not None:
                self.r.error("SS320", path, "这个 beat 没有旁白，时间点只能写 at: 0（beat 开始）")
            return
        if sentence_ref.isdigit():
            index = int(sentence_ref)
            if index >= len(sentences):
                self.r.error("SS320", path, f"这个 beat 只有 {len(sentences)} 句旁白，没有第 {index} 句（从 0 数）")
                return
        else:
            matches = [i for i, (sid, _) in enumerate(sentences) if sid == sentence_ref]
            if not matches:
                known = "、".join(sid for sid, _ in sentences if sid) or "无"
                self.r.error("SS320", path, f"没有 id 为 {sentence_ref!r} 的句子（现有：{known}）")
                return
            index = matches[0]
        if mark is not None and mark not in sentences[index][1]:
            known = "、".join(f"@{m}" for m in sorted(sentences[index][1])) or "无"
            self.r.error("SS321", path, f"这一句里没有书签 @{mark}（现有：{known}）")

    def check_actions(self, beat: dict, sentences: list, path: str) -> None:
        for i, action in enumerate(beat.get("do", [])):
            self.stats["actions"] += 1
            apath = f"{path}.do[{i}]"
            if "at" in action:
                self.check_time(action["at"], sentences, f"{apath}.at")
            elif i == 0:
                key = "after" if "after" in action else "with"
                self.r.error("SS322", f"{apath}.{key}", "第一个动作前面没有动作，不能用 prev；请用 at")
            self.check_action(action, apath)

    def check_action(self, action: dict, path: str) -> None:
        act = action["act"]
        target = self.resolve(action["target"], f"{path}.target") if "target" in action else None
        if target is not None:
            self.widget_actions.setdefault(target.obj, []).append(act)
        for key in ("from", "to"):
            if key in action:
                self.resolve(action[key], f"{path}.{key}")

        if "ease" in action and act != "tween":
            self.r.error("SS408", f"{path}.ease", "ease 只用于 tween（补间参数时的缓动）")
        if act == "tween":
            P.check_tween(action, path, self.doc, self.r)
            return
        if act in BUILTIN_ACTS:
            if act in NEEDS_TARGET and "target" not in action:
                self.r.error("SS331", path, f"{act} 需要 target")
            if act == "transform":
                if "from" not in action or "to" not in action:
                    self.r.error("SS331", path, "transform 需要 from 和 to")
                if "target" in action:
                    self.r.error("SS331", f"{path}.target", "transform 用 from / to，不用 target")
            elif "from" in action or "to" in action:
                self.r.error("SS331", path, f"只有 transform 用 from / to，{act} 请用 target")
            if act == "hold":
                if "dur" not in action:
                    self.r.error("SS331", path, "hold 需要 dur")
                if "target" in action:
                    self.r.error("SS331", f"{path}.target", "hold 不需要 target")
            if "match" in action and act != "transform":
                self.r.error("SS331", f"{path}.match", "只有 transform 用 match")
            if "replace" in action and act != "transform":
                self.r.error("SS331", f"{path}.replace", "只有 transform 用 replace")
            if act == "camera":
                self.check_camera(action, target, path)
            return

        # 组件提供的动作
        if target is None:
            self.r.error("SS330", path, f"{act!r} 不是内置动作；组件动作需要 target 指向提供它的组件")
            return
        definition = self.objects[target.obj]
        widget = widgets.lookup(definition["widget"]) if "widget" in definition else None
        if "widget" in definition and widget is None:
            return  # 未登记组件：已经给过警告
        if widget is None or act not in widget.actions:
            provided = "、".join(sorted(widget.actions)) if widget and widget.actions else "无"
            self.r.error("SS330", f"{path}.act", f"{act!r} 不是内置动作，{target.obj} 也不提供它（它提供：{provided}）")
            return
        if target.span or target.part or target.index:
            self.r.error("SS333", f"{path}.target", f"组件动作 {act} 的 target 应指向整个组件 {target.obj}")
            return
        ctx = widgets.WidgetContext(target.obj, definition, self.data, self.exposed[target.obj], self.ex)
        widget.actions[act](action.get("args", {}), ctx, self.r, path)

    def check_camera(self, action: dict, target: selectors.Selector | None, path: str) -> None:
        """camera 的参数：{zoom: 倍数} / {fit: true, margin?} 对准 target；{reset: true} 复位。"""
        args = action.get("args", {})
        apath = f"{path}.args"
        for key in sorted(set(args) - CAMERA_ARGS):
            self.r.error("SS334", f"{apath}.{key}", f"camera 没有参数 {key}（可用：fit、margin、reset、zoom）")
        zoom, fit, margin, reset = (args.get(k) for k in ("zoom", "fit", "margin", "reset"))

        def number(v) -> bool:
            return isinstance(v, (int, float)) and not isinstance(v, bool)

        if reset is not None:
            if reset is not True:
                self.r.error("SS334", f"{apath}.reset", "reset 只能写 true")
            others = [k for k in ("zoom", "fit", "margin") if k in args] + (["target"] if "target" in action else [])
            if others:
                self.r.error("SS334", path, f"camera 复位（reset）时不能再写 {'、'.join(others)}")
            return
        if zoom is not None and (not number(zoom) or zoom <= 0):
            self.r.error("SS334", f"{apath}.zoom", f"zoom 应为大于 0 的数（放大倍数，1 = 原样），收到 {zoom!r}")
        if fit is not None and not isinstance(fit, bool):
            self.r.error("SS334", f"{apath}.fit", f"fit 应为 true / false，收到 {fit!r}")
        if margin is not None and (not number(margin) or margin < 0):
            self.r.error("SS334", f"{apath}.margin", f"margin 应为不小于 0 的数，收到 {margin!r}")
        if fit is True and zoom is not None:
            self.r.error("SS334", path, "fit 和 zoom 只能二选一：fit 自动算倍数，zoom 指定倍数")
        if fit is True and "target" not in action:
            self.r.error("SS334", path, "fit 需要 target：镜头要填满哪个对象")
        if margin is not None and fit is not True:
            self.r.error("SS334", f"{apath}.margin", "margin 只和 fit: true 一起用")
        if zoom is None and fit is not True:
            self.r.error("SS334", path, "camera 需要 zoom、fit: true 或 reset: true 之一")
        if target is not None and target.obj in self.objects:
            definition = self.objects[target.obj]
            if definition.get("pin") or definition.get("in") in CAMERA_EXEMPT_REGIONS:
                self.r.warning("SS334", f"{path}.target", f"{target.obj} 钉住或在 top / footer 区，不跟镜头走，对准它没有意义")

    # ---------- 教学信息 ----------

    def check_pedagogy(self) -> None:
        ped = self.doc.get("pedagogy", {})
        for key in REQUIRED_PEDAGOGY[self.line]:
            if key not in ped:
                self.r.error("SS360", "pedagogy", f"{self.line} 线必须填写 pedagogy.{key}")
        if self.line == "insight" and self.meta.get("episode") is None:
            self.r.error("SS360", "meta.episode", "insight 线必须填写选题编号 episode")

        shows: dict[str, list[str]] = {"misconception": [], "non_example": [], "landing": []}
        for beat in self.beats:
            kinds = beat.get("shows", [])
            for kind in [kinds] if isinstance(kinds, str) else kinds:
                shows[kind].append(beat["id"])

        for kind in ("misconception", "non_example"):
            if kind in ped and not shows[kind]:
                self.r.error("SS362", f"pedagogy.{kind}", f"填了 {kind}，但没有任何 beat 标注 shows: {kind}")
            if shows[kind] and kind not in ped:
                self.r.error("SS363", "pedagogy", f"beat {shows[kind]} 标注了 shows: {kind}，但 pedagogy.{kind} 没填")

        beat_ids = {b["id"] for b in self.beats}
        landing = ped.get("landing")
        if landing is not None:
            if landing not in beat_ids:
                self.r.error("SS361", "pedagogy.landing", f"没有 id 为 {landing!r} 的 beat")
            elif landing not in shows["landing"]:
                self.r.error("SS362", "pedagogy.landing", f"beat {landing} 需要标注 shows: landing")
        extra_landing = [b for b in shows["landing"] if b != landing]
        if extra_landing:
            self.r.error("SS363", "pedagogy.landing", f"beat {extra_landing} 标注了 shows: landing，但 pedagogy.landing 指向 {landing!r}")

        if ped.get("status") == "demo":
            spoken = "".join(s["text"] for b in self.beats for s in b.get("say", []))
            if not any(word in spoken for word in DEMO_WORDS):
                self.r.error("SS364", "pedagogy.status", "status 是 demo，但旁白里没有说明这是演示、不是证明")

        if self.line == "insight" and not any(b.get("pause", {}).get("type") == "predict" for b in self.beats):
            self.r.error("SS365", "beats", "insight 线至少要有一个 pause: {type: predict} 预测暂停")

    # ---------- 其他 ----------

    def check_misc(self) -> None:
        theme = self.doc.get("style", {}).get("theme")
        if theme and theme not in KNOWN_THEMES:
            self.r.warning("SS371", "style.theme", f"主题 {theme!r} 不在 palette 的公开主题里（{'、'.join(sorted(KNOWN_THEMES))}）")
        if self.line == "worked" and not self.meta.get("sources"):
            self.r.warning("SS372", "meta.sources", "例题讲解通常引用了题目，请在 meta.sources 写明来源")
        P.check_unused(self.ex, self.doc, self.r)
        for obj_id in self.objects:
            if obj_id not in self.referenced:
                self.r.warning("SS381", f"objects.{obj_id}", "这个对象没有被任何动作或布局引用，也没有钉住")
        content_actions = {"vector", "slide", "point", "shape", "segment", "line", "rotate", "scale", "warp", "reset",
                           "relabel", "highlight", "unhighlight", "remove"}
        for obj_id, definition in self.objects.items():
            if definition.get("widget") != "plane" or definition.get("allow_empty") is True:
                continue
            if definition.get("curves") or definition.get("points") or definition.get("matrix") is not None:
                continue
            actions = self.widget_actions.get(obj_id, [])
            if not any(act in content_actions for act in actions):
                self.r.warning(
                    "SS384",
                    f"objects.{obj_id}",
                    "plane 只有显示/隐藏动作，没有点、向量、图形或变形；会渲染成空坐标轴/网格。补真实内容，或明确写 allow_empty: true",
                )

    def run(self) -> None:
        P.check_declarations(self.doc, self.r)
        self.scan_literals(self.doc, "")
        self.check_objects()
        self.check_beats()
        self.check_pedagogy()
        self.check_misc()
        segments.check(self.doc, self.r, self.stats)
        clips.check(self.doc, self.r, self.root)
        quality.check_voice(self.doc, self.r, self.allowlist)
        quality.check_pauses(self.doc, self.r)
        quality.check_tolerances(self.doc, self.r)
        if self.timing is not None:
            quality.check_timing(self.doc, self.timing, self.r, self.allowlist)
        self.r.stats.update(self.stats)


def check(doc: dict, report: Report, *, root=None, timing=None, allowlist=None) -> None:
    _Checker(doc, report, root, timing, allowlist).run()
