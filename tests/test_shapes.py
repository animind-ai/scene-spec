"""基础图形 type: shape、组合 type: group，以及 transform 的 replace。"""

import pytest

from scene_spec import check, selectors

SHAPES = {
    "c": {"type": "shape", "shape": "circle", "radius": 0.8, "label": "$r$"},
    "s": {"type": "shape", "shape": "square", "side": 1.5, "role": "A"},
    "r": {"type": "shape", "shape": "rectangle", "side": [2, 1]},
    "p": {"type": "shape", "shape": "polygon", "points": [[0, 0], [2, 0], [1, 1.5]], "label": "三角形"},
    "l": {"type": "shape", "shape": "line", "points": [[0, 0], [2, 1]]},
    "a": {"type": "shape", "shape": "arrow", "side": 2, "label": "$v$", "role": "B"},
    "d": {"type": "shape", "shape": "dot", "role": "HL"},
    "row": {"type": "group", "children": ["c", "s", "r", "p", "l", "a", "d"], "in": "stage"},
}


def with_shapes(doc: dict, objects: dict | None = None, actions: list | None = None) -> dict:
    doc["objects"].update(objects if objects is not None else SHAPES)
    actions = actions if actions is not None else [{"after": "prev", "act": "show", "target": "row"},
                                                   {"after": "prev", "act": "show", "target": "row[2]"}]
    do = doc["beats"][-1].setdefault("do", [])
    if not do:  # 这个 beat 原来没有动作：第一个动作不能 after: prev
        actions = [{k: v for k, v in actions[0].items() if k != "after"} | {"at": 0}] + actions[1:]
    do.extend(actions)
    return doc


def codes(doc) -> list[str]:
    return check(doc).codes()


def test_all_seven_shapes_in_a_group_pass(example):
    assert codes(with_shapes(example)) == []


@pytest.mark.parametrize("obj, code", [
    ({"type": "shape", "shape": "circle", "side": 1}, "SS205"),  # circle 不用 side
    ({"type": "shape", "shape": "square", "radius": 1}, "SS205"),
    ({"type": "shape", "shape": "square", "side": "很长"}, "SS205"),
    ({"type": "shape", "shape": "rectangle", "side": 2}, "SS205"),  # 要 [宽, 高]
    ({"type": "shape", "shape": "polygon"}, "SS204"),
    ({"type": "shape", "shape": "polygon", "points": [[0, 0], [1, 0]]}, "SS205"),
    ({"type": "shape", "shape": "line", "points": [[0, 0], [1, 0], [2, 0]]}, "SS205"),
    ({"type": "shape", "shape": "line", "points": [[1, 1], [1, 1]]}, "SS205"),
    ({"type": "shape", "shape": "arrow", "points": [[0, 0], [1, 0]], "side": 2}, "SS205"),
    ({"type": "text", "text": "x", "radius": 1}, "SS205"),  # 几何参数只用于 shape
    ({"type": "shape", "shape": "dot", "label": "[$x$]{#a"}, "SS210"),
    ({"type": "math", "tex": "x", "label": "y"}, "SS410"),  # label 仍然只给 readout 和 shape
])
def test_bad_shape_parameters(example, obj, code):
    doc = with_shapes(example, {"x": obj}, [{"after": "prev", "act": "show", "target": "x"}])
    assert code in codes(doc)


def test_schema_rejects_unknown_shape_and_bad_radius(example):
    for obj in ({"type": "shape", "shape": "star"}, {"type": "shape", "shape": "circle", "radius": 0}):
        doc = with_shapes(example, {"x": obj}, [{"after": "prev", "act": "show", "target": "x"}])
        assert codes(doc) == ["SS100"]


def test_group_cycles_and_shared_children(example):
    objs = {"u": {"type": "shape", "shape": "dot"},
            "g1": {"type": "group", "children": ["u", "g2"]}, "g2": {"type": "group", "children": ["g1"]}}
    doc = with_shapes(example, objs, [{"after": "prev", "act": "show", "target": "g1"}])
    assert "SS344" in codes(doc)
    objs = {"u": {"type": "shape", "shape": "dot"},
            "g1": {"type": "group", "children": ["u"]}, "g2": {"type": "group", "children": ["u"]}}
    doc = with_shapes(example, objs, [{"after": "prev", "act": "show", "target": "g1"},
                                      {"after": "prev", "act": "show", "target": "g2"}])
    assert "SS344" in codes(doc)


def test_group_index_out_of_range(example):
    doc = with_shapes(example, actions=[{"after": "prev", "act": "show", "target": "row[7]"}])
    assert "SS313" in codes(doc)


# ---------- transform: replace ----------

EQ = {"e1": {"type": "text", "text": "[$x^2$]{#a} $+$ [$2x$]{#b} $=0$"},
      "e2": {"type": "text", "text": "[$x^2$]{#a} $+$ [$2x$]{#b} $+$ [$1$]{#c} $=$ [$1$]{#d}"}}


def test_replace_is_accepted_on_transform_only(example):
    doc = with_shapes(example, EQ, [{"after": "prev", "act": "show", "target": "e1"},
                                    {"after": "prev", "act": "transform", "from": "e1", "to": "e2", "replace": True},
                                    {"after": "prev", "act": "transform", "from": "e2", "to": "e1", "match": "tex"}])
    assert codes(doc) == []
    doc["beats"][-1]["do"][-1] = {"after": "prev", "act": "hide", "target": "e1", "replace": True}
    assert codes(doc) == ["SS331"]
    doc["beats"][-1]["do"][-1] = {"after": "prev", "act": "transform", "from": "e2", "to": "e1", "replace": "yes"}
    assert codes(doc) == ["SS100"]


@pytest.mark.parametrize("action, gone", [
    ({"act": "transform", "from": "e1", "to": "e2"}, None),  # 默认不替换：源保持不动
    ({"act": "transform", "from": "e1", "to": "e2", "match": "shape"}, None),
    ({"act": "transform", "from": "e1", "to": "e2", "replace": True}, "e1"),
    ({"act": "transform", "from": "e1", "to": "e2", "match": "tex"}, "e1"),  # match: tex / auto 默认替换
    ({"act": "transform", "from": "e1", "to": "e2", "match": "auto"}, "e1"),
    ({"act": "transform", "from": "e1", "to": "e2", "match": "tex", "replace": False}, None),
    ({"act": "transform", "from": "e1#a", "to": "e2", "replace": True}, None),  # 片段：对象本身还在
    ({"act": "transform", "from": "e1", "to": "e1", "replace": True}, None),
])
def test_transform_replaced(action, gone):
    assert selectors.transform_replaced(action) == gone


def test_replaced_source_is_no_longer_visible_to_segment_checks(example):
    # 被替换掉的源之后不在画面上：给它留残影时提醒"可能还没显示"（SS442），和 hide 之后一样
    doc = with_shapes(example, EQ, [{"after": "prev", "act": "show", "target": "e1"},
                                    {"after": "prev", "act": "transform", "from": "e1", "to": "e2", "replace": True},
                                    {"after": "prev", "act": "ghost", "target": "e1"}])
    found = [i.code for i in check(doc).issues]
    assert "SS442" in found
    doc["beats"][-1]["do"][1].pop("replace")
    assert "SS442" not in [i.code for i in check(doc).issues]
