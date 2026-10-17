"""数轴上从 0 出发的箭头（#15 负负得正）：arrow / stretch / turn 按顺序推演箭头指向哪。"""

import pytest

from scene_spec import check


def add(doc, obj: dict, *actions: tuple[str, dict | None]) -> list[str]:
    doc["objects"]["w"] = {**obj, "in": "stage"}
    do = next(b for b in doc["beats"] if b["id"] == "Down")["do"]
    for act, args in actions:
        do.append({"after": "prev", "act": act, "target": "w", **({"args": args} if args is not None else {})})
    return [c for c in check(doc).codes() if c.startswith(("SS2", "SS33"))]


NL = {"widget": "number_line", "range": [-6, 6], "arrows": True}


def test_two_turns_land_on_plus_six(example):
    result = add(example, NL, ("arrow", {"to": 3}), ("turn", {"label": r"\times(-1)"}),
                 ("arrow", {"to": -3, "keep": True}), ("turn", {}),
                 ("arrow", {"to": 3, "role": "B"}), ("stretch", {"to": 6}), ("turn", {}), ("turn", {}), ("erase", None))
    assert result == []


@pytest.mark.parametrize("obj,actions,code", [
    ({"arrows": False}, [("arrow", {"to": 2})], "SS287"),  # 没预留位置
    ({}, [("turn", {})], "SS261"),  # 还没有箭头
    ({}, [("stretch", {"to": 2})], "SS261"),
    ({}, [("arrow", {"to": 3}), ("stretch", {"to": -2})], "SS282"),  # stretch 不掉头
    ({}, [("arrow", {"to": 0})], "SS282"),
    ({}, [("arrow", {"to": 9})], "SS282"),  # 不在数轴上
    ({"range": [-2, 6]}, [("arrow", {"to": 4}), ("turn", {})], "SS282"),  # 转过去是 -4，出轴
    ({}, [("arrow", {"to": 2}), ("erase", None), ("turn", {})], "SS261"),  # erase 收掉了箭头
    ({}, [("arrow", {"to": 2, "size": 3})], "SS281"),
])
def test_arrows_are_checked(example, obj, actions, code):
    result = add(example, {**NL, **obj}, *actions)
    assert code in result, result
