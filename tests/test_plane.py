"""坐标平面 plane：动作参数、名字、按顺序推演的坐标是否出了范围。"""

import pytest

from scene_spec import check


def add(doc, obj: dict, *actions: tuple[str, dict | None]) -> list[str]:
    """在示例里放一个组件 w，在 Down 段末尾依次做 actions，返回检查结果里组件相关的代码。"""
    doc["objects"]["w"] = {**obj, "in": "stage"}
    do = next(b for b in doc["beats"] if b["id"] == "Down")["do"]
    for act, args in actions:
        do.append({"after": "prev", "act": act, "target": "w", **({"args": args} if args is not None else {})})
    return [c for c in check(doc).codes() if c.startswith(("SS2", "SS33"))]


P = {"widget": "plane", "x": [-2, 5], "y": [-1, 4]}
C = {"widget": "plane", "x": [-4, 4], "y": [-4, 4], "complex": True, "mesh": True}


def test_tip_to_tail_and_warp_pass(example):
    result = add(example, {**P, "mesh": True},
                 ("vector", {"name": "a", "v": [3, 1], "label": r"\vec a"}),
                 ("vector", {"name": "b", "v": [1, 2], "role": "B", "side": "r"}),
                 ("slide", {"name": "b", "at": [3, 1], "copy": "b2"}),
                 ("vector", {"name": "s", "v": [4, 3], "role": "HL"}),
                 ("remove", {"name": ["b2", "s"]}),
                 ("shape", {"name": "sq", "points": [[0, 0], [1, 0], [1, 1], [0, 1]]}),
                 ("warp", {"matrix": [[1, 0.5], [0, 1]]}), ("reset", None))
    assert result == []


def test_quarter_turns_pass(example):
    result = add(example, C, ("vector", {"name": "z", "v": [3, 1], "label": "z"}),
                 ("rotate", {"name": "z", "angle": 90, "label": r"\times i"}), ("relabel", {"name": "z", "label": "iz"}),
                 ("rotate", {"angle": 90}), ("point", {"name": "o", "at": [1, 0], "dir": "d"}))
    assert result == []


@pytest.mark.parametrize("obj,actions,code", [
    ({}, [("vector", {"name": "a", "v": [6, 1]})], "SS262"),  # 伸出 x 范围
    ({}, [("vector", {"name": "a", "v": [3, 1]}), ("vector", {"name": "a", "v": [1, 1]})], "SS281"),  # 名字重复
    ({}, [("slide", {"name": "b", "at": [1, 1]})], "SS281"),  # 没有 b
    ({}, [("vector", {"name": "a", "v": [3, 1]}), ("slide", {"name": "a", "at": [3, 3]})], "SS262"),
    ({}, [("vector", {"name": "a", "v": [4, 0]}), ("rotate", {"name": "a", "angle": 180})], "SS262"),  # 途中 y 超过 4、终点 x = −4
    ({}, [("warp", {"matrix": [[1, 2], [2, 4]]})], "SS281"),  # 奇异
    ({}, [("vector", {"name": "a", "v": [3, 1], "side": "x"})], "SS281"),
    ({}, [("rotate", {"angle": 0})], "SS281"),
    ({"x": [1, 5]}, [], "SS202"),  # 范围要含 0
    ({"axis_labels": ["x"]}, [], "SS202"),
])
def test_plane_is_checked(example, obj, actions, code):
    result = add(example, {**P, **obj}, *actions)
    assert any(c.startswith(code) for c in result), result


def test_fixed_points_stay_put(example):
    # 钉住的点 (4, 3) 在 warp 时不跟着走（跟着走就伸出 x 范围了）
    result = add(example, {**P, "mesh": True}, ("point", {"name": "o", "at": [4, 3], "fixed": True}),
                 ("vector", {"name": "e", "v": [1, 0]}), ("warp", {"matrix": [[2, 0], [0, 1]]}), ("reset", None),
                 ("remove", None), ("point", {"name": "o", "at": [1, 1]}))
    assert result == []


def test_shape_takes_a_label(example):
    assert add(example, P, ("shape", {"name": "sq", "points": [[0, 0], [1, 0], [1, 1]], "label": "a^2"})) == []
    assert "SS281" in add(example, P, ("shape", {"name": "sq2", "points": [[0, 0], [1, 0], [1, 1]], "label": 3}))
    assert "SS281" in add(example, P, ("shape", {"name": "sq3", "points": [[0, 0], [1, 0], [1, 1]], "fill": "no"}))


def test_highlight_pass(example):
    result = add(example, P, ("vector", {"name": "a", "v": [3, 1]}), ("shape", {"name": "sq", "points": [[0, 0], [1, 0], [1, 1]]}),
                 ("highlight", {"name": "a", "pulse": True}), ("highlight", {"name": ["sq"]}),
                 ("warp", {"matrix": [[1, 0.5], [0, 1]]}), ("unhighlight", {"name": "a"}), ("unhighlight", None),
                 ("highlight", {"name": "a"}), ("remove", {"name": "a"}))
    assert result == []


@pytest.mark.parametrize("actions", [
    [("highlight", {"name": "nope"})],
    [("highlight", None)],  # 要写 name
    [("vector", {"name": "a", "v": [1, 1]}), ("highlight", {"name": "a", "pulse": 2})],
    [("vector", {"name": "a", "v": [1, 1]}), ("highlight", {"name": "a", "role": "A"})],
    [("vector", {"name": "a", "v": [1, 1]}), ("highlight", {"name": "a"}), ("highlight", {"name": "a"})],
    [("vector", {"name": "a", "v": [1, 1]}), ("unhighlight", {"name": "a"})],
])
def test_highlight_is_checked(example, actions):
    assert "SS281" in add(example, P, *actions)
