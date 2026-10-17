"""天平 balance（解方程就是天平 #19）：按动作顺序推演每个盘里几块砝码。"""

import pytest

from scene_spec import check


def add(doc, obj: dict, *actions: tuple[str, dict | None]) -> list[str]:
    doc["objects"]["w"] = {**obj, "in": "stage"}
    do = next(b for b in doc["beats"] if b["id"] == "Down")["do"]
    for act, args in actions:
        do.append({"after": "prev", "act": act, "target": "w", **({"args": args} if args is not None else {})})
    return [c for c in check(doc).codes() if c.startswith(("SS2", "SS33"))]


BAL = {"widget": "balance", "left": [1] * 7, "right": ["box", 1, 1, 1, 1, 1], "box": 2, "box_label": "?"}


def test_solve_by_taking_from_both_sides(example):
    result = add(example, BAL, ("remove", {"side": "left", "count": 2}), ("add", {"side": "left", "count": 2, "role": "C"}),
                 ("remove", {"side": "both", "count": 5}), ("label", {"text": "2"}))
    assert result == []


@pytest.mark.parametrize("obj,actions,code", [
    ({}, [("remove", {"side": "right", "count": 6})], "SS261"),  # 右盘只有 5 块砝码，盒子不能拿
    ({}, [("remove", {"side": "both", "count": 5}), ("remove", {"side": "right"})], "SS261"),
    ({}, [("add", {"side": "left", "count": 1})], "SS262"),  # room 默认 7
    ({}, [("remove", {"side": "middle"})], "SS281"),
    ({"right": [1] * 7}, [("label", {"text": "2"})], "SS261"),  # 没有盒子
    ({"left": ["box", "box"]}, [], "SS2"),
])
def test_balance_is_checked(example, obj, actions, code):
    result = add(example, {**BAL, **obj}, *actions)
    assert any(c.startswith(code) for c in result), result
