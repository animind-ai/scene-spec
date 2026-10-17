"""积木条形图 block_bars（平均数削峰填谷）：动作参数和按顺序推演的每列块数。"""

import pytest

from scene_spec import check


def codes(doc) -> list[str]:
    return check(doc).codes()


def add(doc, obj: dict, *actions: tuple[str, dict | None]) -> list[str]:
    """在示例里放一个组件 w，在 Down 段末尾依次做 actions，返回检查结果里组件相关的代码。"""
    doc["objects"]["w"] = {**obj, "in": "stage"}
    do = next(b for b in doc["beats"] if b["id"] == "Down")["do"]
    for act, args in actions:
        do.append({"after": "prev", "act": act, "target": "w", **({"args": args} if args is not None else {})})
    return [c for c in codes(doc) if c.startswith(("SS2", "SS33"))]


BB = {"widget": "block_bars", "heights": [5, 2, 6, 3], "cols": 5, "room": 14, "numbers": True}


def test_leveling_then_an_outlier_passes(example):
    result = add(example, BB, ("level", {"at": 3, "label": "平均？", "role": "NO"}),
                 ("transfer", {"from": 0, "to": 1}), ("transfer", {"from": 2, "to": 1}), ("transfer", {"from": 2, "to": 3}),
                 ("level", {"at": 4, "label": "平均 $4$"}), ("add", {"height": 14, "role": "NO", "label": "小郑"}),
                 ("transfer", {"from": 4, "to": 0, "count": 2}), ("recolor", {"col": 4, "role": "NO"}), ("unlevel", None))
    assert result == []


@pytest.mark.parametrize("obj,actions,code", [
    ({}, [("transfer", {"from": 1, "to": 0, "count": 3})], "SS261"),  # 第 1 列只有 2 块
    ({}, [("transfer", {"from": 0, "to": 0})], "SS281"),
    ({}, [("transfer", {"from": 0, "to": 7})], "SS281"),  # 没有第 7 列
    ({}, [("transfer", {"from": 0})], "SS281"),
    ({"room": 6}, [("transfer", {"from": 0, "to": 2})], "SS262"),  # 挪完 7 块高过 room
    ({"cols": 4}, [("add", {"height": 3})], "SS262"),  # 没有空位
    ({}, [("add", {"height": 0})], "SS281"),
    ({}, [("level", {"at": 20})], "SS281"),
    ({}, [("recolor", {"col": 1})], "SS281"),  # 缺 role
    ({}, [("unlevel", {"at": 1})], "SS281"),
    ({"heights": [5, 2.5]}, [], "SS2"),
    ({"room": 4}, [], "SS262"),  # 最高 6 块
])
def test_block_bars_are_checked(example, obj, actions, code):
    result = add(example, {**BB, **obj}, *actions)
    assert any(c.startswith(code) for c in result), result
