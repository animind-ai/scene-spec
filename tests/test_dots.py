"""十格框、点阵和 area_grid 的 rect 模式（数的世界入门 #1–#5）：动作参数和按顺序推演的状态检查。"""

import pytest

from scene_spec import check


def codes(doc) -> list[str]:
    return check(doc).codes()


def add(doc, obj: dict, *actions: tuple[str, dict | None]) -> list[str]:
    """在示例里放一个组件 w，在 Down 段末尾依次做 actions，返回检查结果的代码。"""
    doc["objects"]["w"] = {**obj, "in": "stage"}
    do = next(b for b in doc["beats"] if b["id"] == "Down")["do"]
    for act, args in actions:
        do.append({"after": "prev", "act": act, "target": "w", **({"args": args} if args is not None else {})})
    return codes(doc)


def new_codes(result: list[str]) -> list[str]:
    return [c for c in result if c.startswith(("SS2", "SS33"))]


# ---------- ten_frame ----------

TF = {"widget": "ten_frame", "side": 5}


def test_make_ten_passes(example):
    result = add(example, TF, ("fill", {"count": 8}), ("side", {"count": 5}), ("count", {"start": 9}),
                 ("move_in", {"count": 2}), ("recolor", {"which": "frame", "role": "HL"}), ("remove", {"which": "side"}))
    assert new_codes(result) == []


@pytest.mark.parametrize("actions,code", [
    ([("fill", {"count": 11})], "SS261"),  # 框只有十格
    ([("fill", {"count": 8}), ("fill", {"count": 3})], "SS261"),
    ([("side", {"count": 6})], "SS261"),  # 旁边只预留了 5 个
    ([("side", {"count": 2}), ("move_in", {"count": 3})], "SS261"),  # 旁边只有 2 个
    ([("fill", {"count": 9}), ("side", {"count": 3}), ("move_in", {"count": 2})], "SS261"),  # 只剩 1 个空格
    ([("count", {})], "SS261"),  # 旁边还没有点
    ([("fill", {"count": 2.0})], "SS281"),  # 点数要是精确的整数
    ([("fill", {"count": True})], "SS281"),
    ([("fill", {"count": "8"})], "SS281"),
    ([("fill", {"count": 3, "role": "RED"})], "SS281"),
    ([("side", {"count": 1, "where": "left"})], "SS281"),
    ([("remove", {"which": "middle"})], "SS281"),
])
def test_ten_frame_counts_are_checked(example, actions, code):
    assert code in add(example, TF, *actions)


def test_clear_empties_the_frame_for_the_next_sum(example):
    result = add(example, TF, ("fill", {"count": 8}), ("remove", None), ("fill", {"count": 9}))
    assert new_codes(result) == []


# ---------- dot_array ----------

def test_series_arc_passes(example):
    """#2 → #3 → #4：3 × 4 转成 4 × 3，补满到 4 × 10，淡出最后一列，点变方格。"""
    da = {"widget": "dot_array", "rows": 3, "cols": 4, "room": [4, 10]}
    result = add(example, da, ("rotate", None), ("extend", {"cols": 10, "role": "B"}), ("fade_col", {"col": -1}),
                 ("recolor", {"row": 0, "role": "HL"}), ("squares", {"fill": "A", "dots": False}))
    assert new_codes(result) == []


def test_rotate_swaps_rows_and_cols(example):
    da = {"widget": "dot_array", "rows": 3, "cols": 4, "room": [4, 10]}
    # 转过以后是 4 × 3：col 3 不存在了，row 3 存在
    assert "SS281" in add(example, da, ("rotate", {"dir": "cw"}), ("fade_col", {"col": 3}))


def test_rotate_rejects_unknown_direction(example):
    assert "SS281" in add(example, {"widget": "dot_array", "rows": 2, "cols": 5}, ("rotate", {"dir": "left"}))


@pytest.mark.parametrize("obj,actions", [
    ({"widget": "dot_array", "rows": 4, "cols": 3}, [("extend", {"cols": 10})]),  # 默认 room 4 × 4 放不下 4 × 10
    ({"widget": "dot_array", "rows": 2, "cols": 5, "room": [2, 5]}, [("rotate", None)]),  # 转成 5 × 2 放不下
    ({"widget": "dot_array", "rows": 5, "cols": 3, "room": [4, 4]}, []),  # 一开始就放不下
])
def test_every_state_must_fit_the_room(example, obj, actions):
    assert "SS262" in add(example, obj, *actions)


def test_extend_only_grows(example):
    da = {"widget": "dot_array", "rows": 4, "cols": 10, "room": [4, 10]}
    assert "SS261" in add(example, da, ("extend", {"cols": 9}))


def test_dot_array_params(example):
    assert "SS202" in add(example, {"widget": "dot_array", "rows": 3, "cols": 4, "room": [3]})
    example["objects"].pop("w")
    assert "SS201" in add(example, {"widget": "dot_array", "rows": 3})


# ---------- area_grid rect 模式 ----------

GRID = {"widget": "area_grid", "cols": 23, "rows": 14, "rect": True, "lines": False}


def test_long_multiplication_cut_passes(example):
    result = add(example, GRID, ("split", {"cols": [20, 3], "rows": [10, 4]}), ("apart", {"gap": 0.4}),
                 ("fill", {"col": 1, "row": 0, "role": "HL", "label": True}), ("fill", {"col": 0, "label": True}),
                 ("join", None), ("unfill", None), ("fill", {"cells": "0:5", "role": "NO"}))
    assert new_codes(result) == []


@pytest.mark.parametrize("actions,code", [
    ([("split", {"cols": [20, 4]})], "SS263"),  # 加起来不是 23
    ([("split", {"cols": [20, 0, 3]})], "SS281"),
    ([("apart", None)], "SS265"),  # 还没切
    ([("split", {"cols": [20, 3]}), ("apart", None), ("split", {"rows": [10, 4]})], "SS265"),  # 分开着不能再切
    ([("split", {"cols": [20, 3]}), ("fill", {"col": 2})], "SS265"),  # 只有两段
    ([("fill", {"row": 1})], "SS265"),  # 行没切，只有一段
    ([("fill", {"cells": "0:400"})], "SS281"),
    ([("fill", {"cells": "0:3", "label": True})], "SS281"),
    ([("cut", {"axis": "cols"})], "SS264"),  # rect 模式没有分数乘法的动作
])
def test_rect_grid_actions_are_checked(example, actions, code):
    assert code in add(example, GRID, *actions)


def test_fraction_grid_has_no_rect_actions(example):
    assert "SS264" in add(example, {"widget": "area_grid", "cols": 4, "rows": 3}, ("split", {"cols": [2, 2]}))
