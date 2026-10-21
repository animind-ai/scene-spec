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


def test_segments_and_lines_pass(example):
    # 特征向量方向上的直线（span）跟着 warp：[[2, 0], [0, 3]] 的两条坐标轴方向不动，斜的那条转过去
    result = add(example, {**P, "mesh": True},
                 ("segment", {"name": "s", "from": [0, 0], "to": [2, 1], "role": "B", "label": "s"}),
                 ("line", {"name": "span", "dir": [1, 2], "role": "A", "label": r"\mathrm{span}", "dashed": True}),
                 ("line", {"name": "row", "eq": [1, 2, 3], "side": "r", "along": 0.8}),
                 ("line", {"name": "v", "dir": [0, 1], "through": [3, 0]}),
                 ("relabel", {"name": "span", "label": "L"}),
                 ("warp", {"matrix": [[1, 0.5], [0, 1]]}), ("reset", None), ("remove", {"name": ["s", "row"]}))
    assert result == []


@pytest.mark.parametrize("args,code", [
    ({"act": "segment", "name": "s", "from": [0, 0], "to": [6, 0]}, "SS262"),  # 线段伸出 x 范围
    ({"act": "segment", "name": "s", "from": [1, 1], "to": [1, 1]}, "SS281"),  # 两端重合
    ({"act": "segment", "name": "s", "from": [0, 0]}, "SS281"),
    ({"act": "line", "name": "l", "dir": [0, 0]}, "SS281"),  # 零方向
    ({"act": "line", "name": "l", "dir": [1, 0], "eq": [1, 0, 1]}, "SS281"),  # 二选一
    ({"act": "line", "name": "l", "eq": [0, 0, 1]}, "SS281"),
    ({"act": "line", "name": "l", "eq": [1, 0, 2], "through": [0, 0]}, "SS281"),
    ({"act": "line", "name": "l", "dir": [1, 0], "through": [0, 9]}, "SS262"),  # 不经过坐标范围
    ({"act": "line", "name": "l", "dir": [1, 0], "role": "Q"}, "SS281"),
    ({"act": "line", "name": "l", "dir": [1, 0], "points": [[0, 0]]}, "SS281"),  # 多余参数
])
def test_lines_are_checked(example, args, code):
    act = args.pop("act")
    result = add(example, P, (act, args))
    assert any(c.startswith(code) for c in result), result


def test_lines_cannot_slide(example):
    result = add(example, P, ("segment", {"name": "s", "from": [0, 0], "to": [1, 1]}), ("slide", {"name": "s", "at": [1, 0]}))
    assert "SS281" in result


def test_lines_follow_warps(example):
    # 直线跟着整个平面缩放：y = 3 放大两倍成了 y = 6，出了 y 范围 [-1, 4]
    result = add(example, P, ("line", {"name": "l", "eq": [0, 1, 3]}), ("scale", {"by": 2}))
    assert "SS262" in result
