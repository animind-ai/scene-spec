"""编程课组件（docs/cs-lecture.md）：代码面板的行号和片段、调用栈的 push / pop、名字 → 对象、流程图。"""

import pytest

from scene_spec import check

FACT = "def fact(n):\n    if n == 0:\n        return 1\n    else:\n        return n * fact(n - 1)\n"


def lecture(objects: dict, actions: list[dict]) -> dict:
    return {
        "spec": "0.1",
        "meta": {"id": "l06-p1", "title": "Recursion", "line": "lecture", "author": "Boxi Yu", "license": "CC-BY-4.0"},
        "style": {"theme": "classroom", "layout": "lecture", "lang": "en",
                  "fonts": {"text": "Inter", "code": "Source Code Pro"}},
        "objects": {k: {"in": "stage", **v} for k, v in objects.items()},
        "beats": [{"id": "Stack", "say": [{"id": "s1", "pace": "normal", "text": "We call fact of three."}],
                   "do": [{"at": "s1", "act": "show", "target": k} for k in objects]
                   + [{"after": "prev", **a} for a in actions]}],
    }


def codes(doc: dict) -> list[str]:
    return check(doc).codes()


def test_a_lecture_passes():
    doc = lecture(
        {"title": {"widget": "heading", "text": "The call stack", "kicker": "AIE1001 · Lecture 6"},
         "fact": {"widget": "code", "src": FACT, "spans": {"call": {"line": 4, "text": "fact(n - 1)"}}},
         "stack": {"widget": "call_stack", "depth": 2},
         "out": {"widget": "terminal", "lines": ["fact(3)", {"text": "RecursionError", "role": "NO"}], "cols": 30},
         "env": {"widget": "bindings", "names": ["a", "b"], "objects": {"o1": "[1, 2]", "o2": "[3]"},
                 "bind": {"a": "o1", "b": "o1"}},
         "loop": {"widget": "flow", "nodes": {"go": {"text": "Start", "row": 0, "col": 0},
                                              "ask": {"text": "Tool use?", "row": 1, "col": 0, "shape": "diamond"}},
                  "edges": [{"from": "go", "to": "ask"}]},
         "rule": {"widget": "card", "title": "New call → new frame", "body": ["holds its parameters"]},
         "tag": {"widget": "pill", "text": "base case", "role": "A"},
         "plan": {"widget": "bullets", "items": ["What recursion is", "Three bugs"]},
         "line": {"widget": "queue", "people": 6, "you": 5}},
        [{"act": "highlight", "target": "fact", "args": {"lines": [1, 2]}},
         {"act": "circle", "target": "fact#call"},
         {"act": "push", "target": "stack", "args": {"name": "fact", "vars": {"n": 3}}},
         {"act": "note", "target": "stack", "args": {"text": "waiting"}},
         {"act": "push", "target": "stack", "args": {"name": "fact", "vars": {"n": 2}}},
         {"act": "focus", "target": "stack.value[0:2]"},
         {"act": "pop", "target": "stack"},
         {"act": "pop", "target": "stack"},
         {"act": "show", "target": "out[1]"},
         {"act": "rebind", "target": "env", "args": {"name": "b", "to": "o2"}},
         {"act": "mark", "target": "loop#ask"},
         {"act": "ask", "target": "line"},
         {"act": "number", "target": "line"}])
    assert [c for c in codes(doc) if not c.startswith("SS381")] == []


@pytest.mark.parametrize("obj,actions,code", [
    ({"widget": "code", "src": FACT, "spans": {"x": {"line": 7, "text": "n"}}}, [], "SS470"),
    ({"widget": "code", "src": FACT, "spans": {"x": {"line": 4, "text": "fact(n)"}}}, [], "SS470"),
    ({"widget": "code", "src": FACT}, [{"act": "highlight", "args": {"lines": [5]}}], "SS470"),
    ({"widget": "code", "src": FACT}, [{"act": "point", "args": {}}], "SS281"),
    ({"widget": "call_stack", "depth": 1}, [{"act": "push", "args": {"name": "f"}}] * 2, "SS471"),
    ({"widget": "call_stack", "depth": 1}, [{"act": "pop"}], "SS471"),
    ({"widget": "call_stack", "depth": 2}, [{"act": "note", "args": {"text": "waiting"}}], "SS471"),
    ({"widget": "call_stack", "depth": 2},
     [{"act": "push", "args": {"name": "f"}}, {"act": "note", "args": {"text": "x", "frame": 1}}], "SS471"),
    ({"widget": "bindings", "names": ["a"], "objects": {"o": 1}, "bind": {"b": "o"}}, [], "SS472"),
    ({"widget": "bindings", "names": ["a"], "objects": {"o": 1}}, [{"act": "rebind", "args": {"name": "a", "to": "p"}}],
     "SS472"),
    ({"widget": "flow", "nodes": {"a": {"text": "A", "row": 0, "col": 0}, "b": {"text": "B", "row": 0, "col": 0}}},
     [], "SS473"),
    ({"widget": "flow", "nodes": {"a": {"text": "A", "row": 0, "col": 0}}, "edges": [{"from": "a", "to": "z"}]}, [],
     "SS473"),
    ({"widget": "terminal", "lines": [{"text": "x", "role": "PINK"}]}, [], "SS202"),
    ({"widget": "image", "src": "slide.gif"}, [], "SS202"),
])
def test_cs_widgets_are_checked(obj, actions, code):
    doc = lecture({"w": obj}, [{"target": "w", **a} for a in actions])
    result = codes(doc)
    assert any(c.startswith(code) for c in result), result


def test_selectors_follow_the_exposed_parts():
    doc = lecture({"fact": {"widget": "code", "src": FACT}, "stack": {"widget": "call_stack", "depth": 2}},
                  [{"act": "mark", "target": "fact.line[5]"}, {"act": "mark", "target": "stack.frame[2]"}])
    assert codes(doc).count("SS312") == 2  # 代码只有 5 行；栈只有 2 个帧位


def test_lecture_line_needs_no_pedagogy_and_allows_at():
    doc = lecture({"tag": {"widget": "pill", "text": "x", "at": [1, 2]}}, [])
    result = codes(doc)
    assert "SS360" not in result and "SS342" in result and check(doc).ok
