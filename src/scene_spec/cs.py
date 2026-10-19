"""编程课组件的检查（docs/cs-lecture.md）：页眉、代码面板、终端、调用栈、名字 → 对象、卡片、胶囊标签、编号要点、
流程图、图片、排队的人。

画法在 kit 的 mx/cs.py；这里只检查参数、每个组件给选择器暴露什么，以及按动作顺序推演的状态（调用栈 push / pop）。

    fact:
      widget: code
      src: |
        def fact(n):
            if n == 0:
                return 1
            return n * fact(n - 1)
      spans: {call: {line: 3, text: "fact(n - 1)"}}     # fact#call 指第 3 行（从 0 数）里的这一段
    stack:
      widget: call_stack
      depth: 4                                          # 底帧上面留 4 个帧的位置

错误码 SS470–SS479。
"""

from __future__ import annotations

from .report import Report

SHAPES = ("box", "diamond", "pill")
IMAGE_TYPES = (".png", ".jpg", ".jpeg")


def code_lines(src: object) -> list[str]:
    return src.strip("\n").split("\n") if isinstance(src, str) else []


def register(registry: dict) -> None:
    from .textmarks import ROLES
    from .widgets import Exposed, Widget, _bool, _positive_int, _str, _str_list, _unknown_args

    def role_arg(args: dict, report: Report, path: str) -> None:
        if "role" in args and args["role"] not in ROLES:
            report.error("SS281", f"{path}.args.role", f"role 应为 {'/'.join(sorted(ROLES))} 之一")

    def no_args(act: str):
        def check(args: dict, ctx, report: Report, path: str) -> None:
            _unknown_args(args, set(), act, report, path)
        return check

    # ---------- 页眉、卡片、胶囊、要点、图片 ----------

    def heading_retitle(args: dict, ctx, report: Report, path: str) -> None:
        if not isinstance(args.get("text"), str) or not args["text"]:
            report.error("SS281", f"{path}.args.text", "retitle 需要 text：新标题")
        role_arg(args, report, path)
        _unknown_args(args, {"text", "role"}, "retitle", report, path)

    registry["heading"] = Widget(
        "heading", params={"text": (True, _str), "kicker": (False, _str)},
        expose=lambda d, data: Exposed(spans={"title", "kicker"} if "kicker" in d else {"title"}),
        actions={"retitle": heading_retitle})

    def _body(value: object) -> str | None:
        if isinstance(value, str) and value:
            return None
        return _str_list(value)

    registry["card"] = Widget(
        "card", params={"title": (True, _str), "body": (False, _body), "mono": (False, _bool),
                        "cols": (False, _positive_int), "rows": (False, _positive_int)},
        expose=lambda d, data: Exposed(spans={"title", "body"} if "body" in d else {"title"}))

    def _card_items(value: object) -> str | None:
        keys = {"title", "body", "role", "mono", "note"}
        if not isinstance(value, list) or not value:
            return "应为非空列表，每项 {title, body?, role?, mono?, note?}"
        for item in value:
            if not (isinstance(item, dict) and isinstance(item.get("title"), str) and set(item) <= keys):
                return "每项是 {title, body?, role?, mono?, note?}"
            if item.get("role", "A") not in ROLES:
                return f"role 应为 {'/'.join(sorted(ROLES))} 之一"
            if _body(item["body"]) if "body" in item else None:
                return "body 是字符串或字符串列表"
        return None

    def expose_cards(d: dict, data: dict) -> Exposed:
        n = len(d["items"]) if isinstance(d.get("items"), list) else 0
        return Exposed(parts={"note": n}, items=n)

    registry["cards"] = Widget(
        "cards", params={"items": (True, _card_items), "cols": (False, _positive_int), "rows": (False, _positive_int)},
        expose=expose_cards)

    registry["pill"] = Widget(
        "pill", params={"text": (True, _str), "filled": (False, _bool), "mono": (False, _bool)},
        expose=lambda d, data: Exposed())

    registry["bullets"] = Widget(
        "bullets", params={"items": (True, _str_list)},
        expose=lambda d, data: Exposed(items=len(d["items"]) if isinstance(d.get("items"), list) else None))

    def _image(value: object) -> str | None:
        if not isinstance(value, str) or not value.lower().endswith(IMAGE_TYPES):
            return f"应为 {' / '.join(IMAGE_TYPES)} 文件的路径（相对场景文件）"
        return None

    registry["image"] = Widget("image", params={"src": (True, _image)}, expose=lambda d, data: Exposed())

    # ---------- 代码面板 ----------

    def _spans(value: object) -> str | None:
        if not isinstance(value, dict) or not value:
            return "应为映射：片段 id → {line, text}"
        for k, v in value.items():
            if not (isinstance(v, dict) and set(v) == {"line", "text"} and isinstance(v["line"], int)
                    and not isinstance(v["line"], bool) and isinstance(v["text"], str) and v["text"]):
                return f"片段 {k} 应为 {{line: 行号（从 0 数）, text: 这一行里的文字}}"
        return None

    def expose_code(d: dict, data: dict) -> Exposed:
        n = len(code_lines(d.get("src")))
        spans = set(d["spans"]) if isinstance(d.get("spans"), dict) else set()
        return Exposed(spans=spans, parts={"line": n}, items=n)

    def validate_code(ctx, report: Report, path: str) -> None:
        lines = code_lines(ctx.definition.get("src"))
        spans = ctx.definition.get("spans")
        if not isinstance(spans, dict):
            return
        for k, v in spans.items():
            if not isinstance(v, dict) or not isinstance(v.get("line"), int):
                continue
            if not 0 <= v["line"] < len(lines):
                report.error("SS470", f"{path}.spans.{k}", f"第 {v['line']} 行越界（代码只有 {len(lines)} 行）")
            elif lines[v["line"]].count(str(v.get("text"))) != 1:
                report.error("SS470", f"{path}.spans.{k}",
                             f"{v.get('text')!r} 应在第 {v['line']} 行里恰好出现一次：{lines[v['line']].strip()!r}")

    def line_arg(args: dict, key: str, ctx, report: Report, path: str, required: bool = True) -> None:
        n = len(code_lines(ctx.definition.get("src")))
        if key not in args:
            if required:
                report.error("SS281", f"{path}.args.{key}", f"需要 {key}：行号（从 0 数）")
            return
        values = args[key] if isinstance(args[key], list) else [args[key]]
        for v in values:
            if not isinstance(v, int) or isinstance(v, bool):
                report.error("SS281", f"{path}.args.{key}", f"{key} 应为行号或行号列表")
            elif not 0 <= v < n:
                report.error("SS470", f"{path}.args.{key}", f"第 {v} 行越界（代码只有 {n} 行）")

    def code_highlight(args: dict, ctx, report: Report, path: str) -> None:
        line_arg(args, "lines", ctx, report, path)
        role_arg(args, report, path)
        _unknown_args(args, {"lines", "role"}, "highlight", report, path)

    def code_unhighlight(args: dict, ctx, report: Report, path: str) -> None:
        line_arg(args, "lines", ctx, report, path, required=False)
        _unknown_args(args, {"lines"}, "unhighlight", report, path)

    def code_point(args: dict, ctx, report: Report, path: str) -> None:
        line_arg(args, "line", ctx, report, path)
        role_arg(args, report, path)
        _unknown_args(args, {"line", "role"}, "point", report, path)

    def code_jump(args: dict, ctx, report: Report, path: str) -> None:
        line_arg(args, "from", ctx, report, path)
        line_arg(args, "to", ctx, report, path)
        role_arg(args, report, path)
        _unknown_args(args, {"from", "to", "role"}, "jump", report, path)

    registry["code"] = Widget(
        "code", params={"src": (True, _str), "numbers": (False, _bool), "spans": (False, _spans)},
        expose=expose_code, validate=validate_code,
        actions={"highlight": code_highlight, "unhighlight": code_unhighlight, "point": code_point,
                 "unpoint": no_args("unpoint"), "jump": code_jump, "unjump": no_args("unjump")})

    # ---------- 终端 ----------

    def _rows(value: object) -> str | None:
        if not isinstance(value, list) or not value:
            return "应为非空的行列表（字符串，或 {text, role}）"
        for row in value:
            if isinstance(row, str):
                continue
            if not (isinstance(row, dict) and isinstance(row.get("text"), str) and set(row) <= {"text", "role"}
                    and row.get("role", "FG") in ROLES):
                return "每一行是字符串或 {text, role}"
        return None

    registry["terminal"] = Widget(
        "terminal", params={"lines": (True, _rows), "cols": (False, _positive_int)},
        expose=lambda d, data: Exposed(items=len(d["lines"]) if isinstance(d.get("lines"), list) else None))

    # ---------- 调用栈 ----------

    def expose_stack(d: dict, data: dict) -> Exposed:
        depth = d.get("depth") if isinstance(d.get("depth"), int) else 0
        return Exposed(parts={"frame": depth, "value": depth, "note": depth, "base": 1}, state={"frames": 0})

    def stack_push(args: dict, ctx, report: Report, path: str) -> None:
        if not isinstance(args.get("name"), str) or not args["name"]:
            report.error("SS281", f"{path}.args.name", "push 需要 name：函数名")
        values = args.get("vars", {})
        if not isinstance(values, dict):
            report.error("SS281", f"{path}.args.vars", "vars 应为映射：变量名 → 值")
        role_arg(args, report, path)
        _unknown_args(args, {"name", "vars", "role"}, "push", report, path)
        st = ctx.exposed.state
        depth = ctx.definition.get("depth", 0)
        if st["frames"] >= depth:
            report.error("SS471", path, f"栈上已经有 {st['frames']} 个帧（depth {depth}）；把 depth 调大")
            return
        st["frames"] += 1

    def stack_pop(args: dict, ctx, report: Report, path: str) -> None:
        _unknown_args(args, set(), "pop", report, path)
        st = ctx.exposed.state
        if st["frames"] == 0:
            report.error("SS471", path, "栈是空的，不能 pop")
            return
        st["frames"] -= 1

    def stack_note(args: dict, ctx, report: Report, path: str) -> None:
        if not isinstance(args.get("text"), str) or not args["text"]:
            report.error("SS281", f"{path}.args.text", "note 需要 text")
        frame_arg(args, ctx, report, path)
        role_arg(args, report, path)
        if "mono" in args and not isinstance(args["mono"], bool):
            report.error("SS281", f"{path}.args.mono", "mono 应为 true / false")
        _unknown_args(args, {"text", "frame", "role", "mono"}, "note", report, path)

    def frame_arg(args: dict, ctx, report: Report, path: str) -> None:
        if "frame" not in args:
            if ctx.exposed.state["frames"] == 0:
                report.error("SS471", path, "栈是空的，没有栈顶帧")
            return
        f = args["frame"]
        if f == "base":
            return
        if not isinstance(f, int) or isinstance(f, bool) or not 0 <= f < ctx.exposed.state["frames"]:
            report.error("SS471", f"{path}.args.frame",
                         f"frame 应为 base 或 0..{ctx.exposed.state['frames'] - 1}（现在栈上的帧）")

    def stack_unnote(args: dict, ctx, report: Report, path: str) -> None:
        if "frame" in args:
            frame_arg(args, ctx, report, path)
        _unknown_args(args, {"frame"}, "unnote", report, path)

    registry["call_stack"] = Widget(
        "call_stack", params={"depth": (True, _positive_int), "base": (False, _str), "cols": (False, _positive_int),
                              "label": (False, _str), "note_cols": (False, _positive_int)},
        expose=expose_stack,
        actions={"push": stack_push, "pop": stack_pop, "note": stack_note, "unnote": stack_unnote})

    # ---------- 名字 → 对象 ----------

    def expose_bindings(d: dict, data: dict) -> Exposed:
        names = d.get("names") if isinstance(d.get("names"), list) else []
        objects = d.get("objects") if isinstance(d.get("objects"), dict) else {}
        bind = d.get("bind") if isinstance(d.get("bind"), dict) else {}
        return Exposed(parts={"name": len(names), "object": len(objects), "arrow": len(names)},
                       state={"bind": dict(bind)})

    def validate_bindings(ctx, report: Report, path: str) -> None:
        d = ctx.definition
        names, objects = d.get("names") or [], d.get("objects") or {}
        for name, obj in (d.get("bind") or {}).items():
            if name not in names:
                report.error("SS472", f"{path}.bind.{name}", f"{name!r} 不在 names 里")
            if obj not in objects:
                report.error("SS472", f"{path}.bind.{name}", f"没有对象 {obj!r}（有 {'、'.join(objects)}）")

    def _objects(value: object) -> str | None:
        if not isinstance(value, dict) or not value:
            return "应为映射：对象 id → 框里显示的值"
        return None if all(isinstance(v, (str, int, float)) and not isinstance(v, bool) for v in value.values()) \
            else "每个对象的值是字符串或数"

    def bind_rebind(args: dict, ctx, report: Report, path: str) -> None:
        d = ctx.definition
        _unknown_args(args, {"name", "to"}, "rebind", report, path)
        if args.get("name") not in (d.get("names") or []):
            report.error("SS472", f"{path}.args.name", f"rebind 需要 name：{d.get('names')} 之一")
        if args.get("to") not in (d.get("objects") or {}):
            report.error("SS472", f"{path}.args.to", f"rebind 需要 to：{list(d.get('objects') or {})} 之一")
        ctx.exposed.state["bind"][args.get("name")] = args.get("to")

    def bind_update(args: dict, ctx, report: Report, path: str) -> None:
        _unknown_args(args, {"object", "value"}, "update", report, path)
        if args.get("object") not in (ctx.definition.get("objects") or {}):
            report.error("SS472", f"{path}.args.object", "update 需要 object：组件里的对象之一")
        if not isinstance(args.get("value"), (str, int, float)) or isinstance(args.get("value"), bool):
            report.error("SS281", f"{path}.args.value", "update 需要 value：字符串或数")

    registry["bindings"] = Widget(
        "bindings", params={"names": (True, _str_list), "objects": (True, _objects), "bind": (False, lambda v: None if isinstance(v, dict) else "应为映射：名字 → 对象 id")},
        expose=expose_bindings, validate=validate_bindings, actions={"rebind": bind_rebind, "update": bind_update})

    # ---------- 流程图 ----------

    def _nodes(value: object) -> str | None:
        if not isinstance(value, dict) or not value:
            return "应为映射：节点 id → {text, row, col, shape, role}"
        for k, v in value.items():
            if not (isinstance(v, dict) and isinstance(v.get("text"), str) and isinstance(v.get("row"), int)
                    and isinstance(v.get("col"), int) and set(v) <= {"text", "row", "col", "shape", "role"}):
                return f"节点 {k} 需要 text、row、col（整数），可选 shape（{'/'.join(SHAPES)}）和 role"
            if v.get("shape", "box") not in SHAPES:
                return f"节点 {k} 的 shape 应为 {'/'.join(SHAPES)} 之一"
            if v.get("role", "A") not in ROLES:
                return f"节点 {k} 的 role 应为 {'/'.join(sorted(ROLES))} 之一"
        return None

    def _edges(value: object) -> str | None:
        if not isinstance(value, list):
            return "应为列表，每项 {from, to}，可选 label、via"
        for e in value:
            if not (isinstance(e, dict) and {"from", "to"} <= set(e) <= {"from", "to", "label", "via"}):
                return "每条边是 {from, to}，可选 label 和 via（left / right / up / down：从那一侧绕过去）"
            if e.get("via", "left") not in ("left", "right", "up", "down"):
                return "via 应为 left / right / up / down"
        return None

    def expose_flow(d: dict, data: dict) -> Exposed:
        nodes = d.get("nodes") if isinstance(d.get("nodes"), dict) else {}
        edges = d.get("edges") if isinstance(d.get("edges"), list) else []
        return Exposed(spans=set(nodes), parts={"edge": len(edges)}, items=len(nodes))

    def validate_flow(ctx, report: Report, path: str) -> None:
        nodes = ctx.definition.get("nodes") or {}
        cells: dict[tuple, str] = {}
        for k, v in nodes.items():
            if not isinstance(v, dict):
                continue
            cell = (v.get("row"), v.get("col"))
            if cell in cells:
                report.error("SS473", f"{path}.nodes.{k}", f"{k} 和 {cells[cell]} 在同一格 {cell}")
            cells[cell] = k
        for i, e in enumerate(ctx.definition.get("edges") or []):
            for end in ("from", "to"):
                if isinstance(e, dict) and e.get(end) not in nodes:
                    report.error("SS473", f"{path}.edges[{i}].{end}", f"没有节点 {e.get(end)!r}")

    registry["flow"] = Widget("flow", params={"nodes": (True, _nodes), "edges": (False, _edges)},
                              expose=expose_flow, validate=validate_flow)

    # ---------- 排队的人 ----------

    def queue_number(args: dict, ctx, report: Report, path: str) -> None:
        _unknown_args(args, set(), "number", report, path)

    registry["queue"] = Widget(
        "queue", params={"people": (True, _positive_int), "you": (False, lambda v: None if isinstance(v, int) else "应为「你」的位置（0 是队首）"), "label": (False, _str)},
        expose=lambda d, data: Exposed(parts={"person": d["people"] if isinstance(d.get("people"), int) else 0,
                                              "you": 1}),
        actions={"ask": no_args("ask"), "number": queue_number})
