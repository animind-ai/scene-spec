"""钱包 wallet（负负得正 #15）：按动作顺序推演两排卡片和余额。"""

import pytest

from scene_spec import check


def add(doc, obj: dict, *actions: tuple[str, dict | None]) -> list[str]:
    doc["objects"]["w"] = {**obj, "in": "stage"}
    do = next(b for b in doc["beats"] if b["id"] == "Down")["do"]
    for act, args in actions:
        do.append({"after": "prev", "act": act, "target": "w", **({"args": args} if args is not None else {})})
    return [c for c in check(doc).codes() if c.startswith(("SS2", "SS33"))]


WAL = {"widget": "wallet", "cash": 2, "iou": 2}


def test_four_cases_and_the_sum(example):
    result = add(example, WAL, ("put", {"kind": "cash", "count": 2}), ("take", {"kind": "cash", "count": 2}),
                 ("put", {"kind": "iou", "count": 2}), ("take", {"kind": "iou", "count": 2}),
                 ("take", {"kind": "cash", "count": 2}), ("put", {"kind": "cash", "count": 2}),
                 ("take", {"kind": "iou", "count": 2}), ("put", {"kind": "iou", "count": 2}),
                 ("put", {"kind": "iou", "value": 2}))
    assert result == []


@pytest.mark.parametrize("obj,actions,code", [
    ({}, [("take", {"kind": "iou", "count": 3})], "SS261"),  # 只有 2 张欠条
    ({}, [("put", {"kind": "cash", "count": 3})], "SS262"),  # 一排 4 个位置
    ({"range": 5}, [("put", {"kind": "cash", "count": 2})], "SS262"),  # 余额 6 超出 range 5
    ({}, [("put", {"kind": "coin"})], "SS281"),
    ({}, [("take", {"kind": "iou", "value": 3})], "SS281"),  # take 没有 value
    ({"cash": 5}, [], "SS262"),
])
def test_wallet_is_checked(example, obj, actions, code):
    result = add(example, {**WAL, **obj}, *actions)
    assert any(c.startswith(code) for c in result), result
