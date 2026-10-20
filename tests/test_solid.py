"""立体组件 solid（洞察 #14 圆锥体积）：参数、名字、按动作顺序推演的状态。"""

import copy

import pytest

from scene_spec import check

SOLID = {
    "widget": "solid",
    "bodies": {
        "C": {"cube": 2, "at": [-3, 0, 0]},
        "P": {"pyramid": {"base": 2, "h": 2}, "role": "B"},
        "K": {"cone": {"r": 1.13, "h": 2}, "at": [3, 0, 0], "label": "$V$"},
    },
    "splits": {"s": {"body": "C", "into": ["P1", "P2", "P3"]}},
    "plane": {"bodies": ["P", "K"], "z": 0.5, "compare": "right", "labels": ["$S_1$", "$S_2$"]},
}


def add(doc, obj: dict, *actions: tuple[str, dict | None]) -> list[str]:
    """在示例里放一个组件 w，在 Down 段末尾依次做 actions，返回检查结果里组件相关的代码。"""
    doc["objects"]["w"] = {**copy.deepcopy(obj), "in": "stage"}
    do = next(b for b in doc["beats"] if b["id"] == "Down")["do"]
    for act, args in actions:
        do.append({"after": "prev", "act": act, "target": "w", **({"args": args} if args is not None else {})})
    return [c for c in check(doc).codes() if c.startswith(("SS2", "SS46"))]


def with_(**changes) -> dict:
    obj = copy.deepcopy(SOLID)
    for key, value in changes.items():
        if value is None:
            obj.pop(key, None)
        else:
            obj[key] = value
    return obj


def test_full_story_passes(example):
    result = add(example, SOLID,
                 ("split", {"split": "s"}), ("apart", {"split": "s"}), ("join", {"split": "s"}),
                 ("unsplit", {"split": "s"}), ("sweep", {"z": 1.5}), ("compare", None), ("sweep", {"z": 0.2}))
    assert result == []


def test_parts_and_spans_are_exposed(example):
    example["objects"]["w"] = {**copy.deepcopy(SOLID), "in": "stage"}
    do = next(b for b in example["beats"] if b["id"] == "Down")["do"]
    do += [{"after": "prev", "act": "set", "target": "w#P2", "args": {"role": "HL"}},
           {"after": "prev", "act": "mark", "target": "w.section[1]"},
           {"after": "prev", "act": "focus", "target": "w#K"},
           {"after": "prev", "act": "show", "target": "w.flat[0]"}]
    assert [c for c in check(example).codes() if c.startswith(("SS2", "SS3", "SS46"))] == []
    do.append({"after": "prev", "act": "mark", "target": "w.section[2]"})
    assert check(example).codes()


@pytest.mark.parametrize("obj,code", [
    (with_(bodies={"C": {"cube": 0}}), "SS460"),
    (with_(bodies={"C": {"cube": 2, "cone": {"r": 1, "h": 1}}}), "SS460"),  # 两种立体
    (with_(bodies={"C": {"sphere": 1}}), "SS460"),
    (with_(bodies={"C": {"cone": {"r": 1}}}), "SS460"),
    (with_(bodies={"C": {"pyramid": {"base": [2], "h": 1}}}), "SS460"),
    (with_(bodies={"C": {"cube": 2, "at": [0, 0]}}), "SS460"),
    (with_(bodies={"C": {"cube": 2, "role": "RED"}}), "SS460"),
    (with_(bodies={"C": {"cube": 2, "colour": "A"}}), "SS460"),
    (with_(splits={"s": {"body": "C", "into": ["P1", "P2", "P-3"]}}), "SS461"),
    (with_(splits={"s": {"body": "C", "into": ["P1", "P2", "K"]}}), "SS461"),  # 和立体重名
    (with_(splits={"s": {"body": "P", "into": ["P1", "P2", "P3"]}}), "SS462"),  # 四棱锥剖不了
    (with_(splits={"s": {"body": "X", "into": ["P1", "P2", "P3"]}}), "SS462"),
    (with_(splits={"s": {"body": "C", "into": ["P1", "P2"]}}), "SS462"),
    (with_(splits={"s": {"body": "C", "into": ["P1", "P2", "P3"], "gap": 9}}), "SS462"),
    (with_(splits={"s": {"body": "C", "into": ["P1", "P2", "P3"], "roles": ["A", "B"]}}), "SS462"),
    (with_(plane={"bodies": ["P", "P1"]}), "SS463"),  # 剖出来的块不能截
    (with_(plane={"bodies": ["P", "K"], "z": 3}), "SS463"),  # 截平面碰不到
    (with_(plane={"bodies": ["P", "K"], "compare": "left"}), "SS463"),
    (with_(plane={"bodies": ["P", "K"], "compare": "right", "labels": ["$S$"]}), "SS463"),
    (with_(plane={"bodies": ["P", "K"], "labels": ["a", "b"]}), "SS463"),  # labels 要配 compare
    (with_(view={"azimuth": 45, "elevation": 0}), "SS464"),
    (with_(view={"azimuth": 0}), "SS464"),  # 正对着看，侧面成了一条线
])
def test_bad_definitions(example, obj, code):
    assert code in add(example, obj)


@pytest.mark.parametrize("actions,code", [
    ([("apart", {"split": "s"})], "SS466"),  # 还没剖开
    ([("split", {"split": "s"}), ("split", {"split": "s"})], "SS466"),
    ([("split", {"split": "s"}), ("apart", {"split": "s"}), ("unsplit", {"split": "s"})], "SS466"),  # 先 join
    ([("split", {"split": "t"})], "SS465"),
    ([("split", None)], "SS465"),
    ([("split", {"split": "s", "gap": 1})], "SS281"),  # gap 写在 splits 里
    ([("sweep", {"z": 5})], "SS467"),
    ([("sweep", {})], "SS467"),
    ([("compare", None)], "SS468"),  # 截平面还没出现
    ([("sweep", {"z": 1}), ("compare", None), ("compare", None)], "SS468"),
])
def test_actions_follow_the_order(example, actions, code):
    assert code in add(example, SOLID, *actions)


def test_sweep_needs_a_plane(example):
    assert "SS467" in add(example, with_(plane=None), ("sweep", {"z": 1}))


def test_compare_needs_room(example):
    obj = with_(plane={"bodies": ["P", "K"]})
    assert "SS468" in add(example, obj, ("sweep", {"z": 1}), ("compare", None))


@pytest.mark.parametrize("actions", [
    [("orbit", {"azimuth": 65, "elevation": 28})],
    [("orbit", {"d_azimuth": 360})],  # 相对增量可以转一整圈
    [("orbit", {"azimuth": -120, "elevation": -40}), ("split", {"split": "s"}), ("sweep", {"z": 1}), ("compare", None)],
    [("orbit", {"d_elevation": 60}), ("orbit", {"d_elevation": -140})],  # 20 → 80 → -60
])
def test_orbit_passes(example, actions):
    assert add(example, SOLID, *actions) == []


@pytest.mark.parametrize("actions,code", [
    ([("orbit", {"azimuth": 65, "elevation": 95})], "SS469"),
    ([("orbit", {"elevation": -86})], "SS469"),
    ([("orbit", {"d_elevation": 70})], "SS469"),  # 默认仰角 20°，转完 90°
    ([("orbit", {"d_elevation": 60}), ("orbit", {"d_elevation": 10})], "SS469"),  # 按顺序推演：80 → 90
    ([("orbit", {"azimuth": 60, "d_azimuth": 10})], "SS469"),  # 绝对和相对只能写一个
    ([("orbit", {"elevation": "high"})], "SS469"),
    ([("orbit", {})], "SS469"),
    ([("orbit", None)], "SS469"),
    ([("orbit", {"azimuth": 60, "roll": 10})], "SS281"),
])
def test_bad_orbits(example, actions, code):
    assert code in add(example, SOLID, *actions)


def test_orbit_starts_from_the_declared_view(example):
    obj = with_(view={"azimuth": 30, "elevation": 50})
    assert "SS469" in add(copy.deepcopy(example), obj, ("orbit", {"d_elevation": 40}))
    assert add(example, obj, ("orbit", {"d_elevation": -130})) == []


def test_scene_spec_check_cli_on_orbit(tmp_path, example):
    import yaml

    from scene_spec.cli import main

    doc = copy.deepcopy(example)
    doc["objects"]["w"] = {**copy.deepcopy(SOLID), "in": "stage"}
    do = next(b for b in doc["beats"] if b["id"] == "Down")["do"]
    do.append({"after": "prev", "act": "orbit", "target": "w", "args": {"azimuth": 65, "elevation": 28}})
    good = tmp_path / "good.scene.yaml"
    good.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    assert main(["check", str(good)]) == 0
    do[-1]["args"] = {"elevation": 95}
    bad = tmp_path / "bad.scene.yaml"
    bad.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    assert main(["check", str(bad)]) != 0
