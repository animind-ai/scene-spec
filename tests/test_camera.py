"""camera 动作的参数检查（SS334）。每个用例在示例的 Down beat 末尾加一个 camera 动作。"""

import pytest

from scene_spec import check


def _issues(doc, **action):
    beat = next(b for b in doc["beats"] if b["id"] == "Down")
    beat["do"].append({"after": "prev", "act": "camera", **action})
    return check(doc).issues


def with_camera(doc, **action) -> list[tuple[str, str]]:
    return [(i.level, i.code) for i in _issues(doc, **action) if i.code.startswith("SS33")]


@pytest.mark.parametrize("action", [
    {"target": "table", "args": {"zoom": 3}},
    {"target": "table", "args": {"zoom": 1.5}},
    {"target": "table", "args": {"fit": True}},
    {"target": "table", "args": {"fit": True, "margin": 0.3}},
    {"target": "table", "args": {"fit": True, "margin": 0}},
    {"args": {"zoom": 2}},
    {"args": {"reset": True}},
    {"args": {"reset": True}, "dur": 2},
])
def test_valid_camera_actions(example, action):
    assert with_camera(example, **action) == []


@pytest.mark.parametrize("action, message", [
    ({"target": "table", "args": {"zoom": 0}}, "zoom"),
    ({"target": "table", "args": {"zoom": -2}}, "zoom"),
    ({"target": "table", "args": {"zoom": True}}, "zoom"),
    ({"target": "table", "args": {"zoom": "big"}}, "zoom"),
    ({"target": "table", "args": {"fit": "yes"}}, "fit"),
    ({"target": "table", "args": {"fit": True, "zoom": 2}}, "二选一"),
    ({"args": {"fit": True}}, "fit 需要 target"),
    ({"target": "table", "args": {"fit": True, "margin": -1}}, "margin"),
    ({"target": "table", "args": {"zoom": 2, "margin": 0.3}}, "margin 只和 fit"),
    ({"target": "table", "args": {}}, "之一"),
    ({"target": "table"}, "之一"),
    ({"target": "table", "args": {"fit": False}}, "之一"),
    ({"target": "table", "args": {"zoom": 2, "speed": 1}}, "没有参数 speed"),
    ({"args": {"reset": False}}, "reset 只能写 true"),
    ({"target": "table", "args": {"reset": True}}, "target"),
    ({"args": {"reset": True, "zoom": 2}}, "zoom"),
])
def test_invalid_camera_actions(example, action, message):
    issues = _issues(example, **action)
    camera = [i for i in issues if i.code == "SS334" and i.level == "error"]
    assert camera, issues
    assert any(message in i.message for i in camera), [i.message for i in camera]


def test_camera_target_must_exist(example):
    assert ("error", "SS310") in [(i.level, i.code) for i in _issues(example, target="nope", args={"zoom": 2})]


@pytest.mark.parametrize("target", ["card", "plan"])
def test_aiming_at_pinned_or_footer_object_warns(example, target):
    assert with_camera(example, target=target, args={"zoom": 2}) == [("warning", "SS334")]
