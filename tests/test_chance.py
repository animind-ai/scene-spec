"""随机试验组件：coin_flips、galton、outcomes。随机数和 kit 共用 scene_spec.chance；expect 按同一个 seed 重算核对。"""

import pytest

from scene_spec import check, widgets
from scene_spec.chance import binomial, coin_flips, galton_counts, galton_paths
from scene_spec.semantic import BUILTIN_ACTS


def add(doc, obj: dict, *actions: tuple[str, dict | None]) -> list[str]:
    doc["objects"]["w"] = {**obj, "in": "stage"}
    do = next(b for b in doc["beats"] if b["id"] == "Down")["do"]
    for act, args in actions:
        do.append({"after": "prev", "act": act, "target": "w", **({"args": args} if args is not None else {})})
    return [c for c in check(doc).codes() if c.startswith(("SS2", "SS33"))]


def test_random_streams_are_fixed():
    # 示例 ep36 / ep38 的旁白数字靠这几串；Python 的 Mersenne Twister 不变，它们就不变
    flips = coin_flips(8770, 1000)
    assert sum(flips[:10]) == 7 and flips[9:15] == [0] * 6 and sum(flips[:100]) == 46 and sum(flips) == 498
    assert galton_counts(3814, 128, 6) == [3, 12, 31, 39, 30, 11, 2]
    assert galton_paths(3814, 1, 6)[0] == [0, 1, 0, 0, 0, 1]
    assert binomial(6) == [1, 6, 15, 20, 15, 6, 1]


def test_no_widget_action_shadows_a_builtin():
    # 内置动作（clear、move、transform …）先匹配，组件里同名的动作永远不会被调用
    for name, w in widgets.REGISTRY.items():
        assert not set(w.actions) & BUILTIN_ACTS, (name, set(w.actions) & BUILTIN_ACTS)


COIN = {"widget": "coin_flips", "n": 1000, "seed": 8770, "runs": 2}
GALTON = {"widget": "galton", "rows": 6, "balls": 128, "seed": 3814}
GRID = {"widget": "outcomes", "rows": 2, "cols": 2, "labels": ["男男", "男女", "女男", "女女"]}


def test_coin_flips_pass(example):
    assert add(example, COIN, ("flip", {"to": 10, "expect": 7}), ("flip", {"to": 1000, "expect": 498}),
               ("runs", {"count": 2}), ("band", None)) == []


def test_galton_passes(example):
    assert add(example, GALTON, ("drop", {"count": 10, "expect": [0, 2, 4, 2, 0, 1, 1]}), ("path", {"ball": 3}),
               ("drop", {"count": 118, "expect": [3, 12, 31, 39, 30, 11, 2]}), ("pascal", None), ("expect", None),
               ("flat", None), ("erase", None)) == []


def test_outcomes_pass(example):
    assert add(example, GRID, ("shade", {"cells": ["男男"], "role": "HL"}), ("strike", {"cells": [3]}),
               ("frame", {"cells": ["男男", "男女", "女男"]}), ("restore", None), ("unshade", None), ("unframe", None)) == []


@pytest.mark.parametrize("obj,actions,code", [
    (COIN, [("flip", {"to": 10, "expect": 5})], "SS261"),  # 前十次是 7 个正面
    (COIN, [("flip", {"to": 100}), ("flip", {"to": 50})], "SS281"),  # 折线只能往后画
    (COIN, [("flip", {"to": 2000})], "SS281"),
    (COIN, [("runs", {"count": 3})], "SS281"),  # 只预留了 2 条
    (GALTON, [("drop", {"count": 10, "expect": [1, 2, 3, 2, 1, 1, 0]})], "SS261"),
    (GALTON, [("drop", {"count": 129})], "SS262"),
    (GALTON, [("path", {"ball": 0})], "SS281"),  # 还没落球
    (GRID, [("shade", {"cells": ["男"]})], "SS281"),
    (GRID, [("frame", {"cells": [4]})], "SS281"),
    ({**GRID, "labels": ["男男"]}, [], "SS202"),
])
def test_chance_widgets_are_checked(example, obj, actions, code):
    result = add(example, obj, *actions)
    assert any(c.startswith(code) for c in result), result
