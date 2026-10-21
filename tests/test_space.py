"""三维坐标空间 space：动作参数、名字、按顺序推演的坐标是否出了范围、投影、3×3 变形。"""

import pytest

from scene_spec import check
from scene_spec.space import det, inv, mul, plane_span, project

S = {"widget": "space", "x": [-3, 3], "y": [-3, 3], "z": [-2, 3], "mesh": True}
I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def add(doc, obj: dict, *actions: tuple[str, dict | None]) -> list[str]:
    """在示例里放一个组件 w，在 Down 段末尾依次做 actions，返回检查结果里组件相关的代码。"""
    doc["objects"]["w"] = {**obj, "in": "stage"}
    do = next(b for b in doc["beats"] if b["id"] == "Down")["do"]
    for act, args in actions:
        do.append({"after": "prev", "act": act, "target": "w", **({"args": args} if args is not None else {})})
    return [c for c in check(doc).codes() if c.startswith(("SS2", "SS46", "SS47"))]


def test_projection_story_passes(example):
    assert add(example, S,
               ("plane", {"name": "P", "span": [[1, 0, 0], [0, 1, 0.5]], "role": "B", "label": r"C(A)"}),
               ("vector", {"name": "b", "v": [1, 1, 2.5], "label": r"\mathbf b"}),
               ("project", {"name": "b", "onto": "P", "as": "p", "error": "e", "label": r"\mathbf p", "error_label": r"\mathbf e"}),
               ("orbit", {"d_azimuth": 40}), ("remove", {"name": ["p", "e"]})) == []


def test_determinant_and_column_space_story_passes(example):
    assert add(example, S,
               ("box", {"name": "Q", "edges": I3, "role": "C", "label": r"\det = 1"}),
               ("line", {"name": "N", "dir": [1, -1, 0], "role": "HL", "dashed": True}),
               ("warp", {"matrix": [[1, 1, 0], [0, 1, 0], [0, 0, 2]]}), ("relabel", {"name": "Q", "label": r"\det = 2"}),
               ("reset", None),
               ("warp", {"matrix": [[1, 1, 0], [1, 1, 0], [0, 0, 1]]}),  # 奇异：秩 2，列空间是一个平面
               ("orbit", {"azimuth": 60, "elevation": 35})) == []


@pytest.mark.parametrize("actions,code", [
    ([("vector", {"name": "v", "v": [1, 2]})], "SS476"),
    ([("vector", {"name": "v", "v": [1, 2, 3]}), ("vector", {"name": "v", "v": [1, 0, 0]})], "SS476"),
    ([("vector", {"name": "v", "v": [1, 2, 4]})], "SS477"),
    ([("line", {"name": "l", "dir": [0, 0, 0]})], "SS476"),
    ([("plane", {"name": "P", "span": [[1, 0, 0], [2, 0, 0]]})], "SS476"),
    ([("plane", {"name": "P", "span": [[1, 0, 0], [0, 1, 0]], "normal": [0, 0, 1]})], "SS476"),
    ([("box", {"name": "B", "edges": [[1, 0, 0], [0, 1, 0]]})], "SS476"),
    ([("box", {"name": "B", "edges": [[3, 0, 0], [0, 1, 0], [0, 0, 1]], "at": [1, 0, 0]})], "SS477"),
    ([("vector", {"name": "v", "v": [1, 1, 1]}), ("warp", {"matrix": [[3, 0, 0], [0, 1, 0], [0, 0, 1]]}),
      ("warp", {"matrix": [[2, 0, 0], [0, 1, 0], [0, 0, 1]]})], "SS477"),
    ([("warp", {"matrix": [[1, 0], [0, 1]]})], "SS479"),
    ([("warp", {"matrix": [[1, 0, 0], [0, 0, 0], [0, 0, 1]]}), ("reset", None)], "SS479"),
    ([("vector", {"name": "v", "v": [1, 1, 1]}), ("project", {"name": "v", "onto": "v", "as": "p"})], "SS478"),
    ([("vector", {"name": "v", "v": [1, 1, 1]}), ("plane", {"name": "P", "normal": [0, 0, 1], "through": [0, 0, 1]}),
      ("project", {"name": "v", "onto": "P", "as": "p"})], "SS478"),
    ([("vector", {"name": "v", "v": [1, 1, 1]}), ("line", {"name": "l", "dir": [1, 0, 0]}),
      ("project", {"name": "v", "onto": "l", "as": "p", "error": "p"})], "SS476"),
    ([("orbit", {"elevation": 90})], "SS469"),
    ([("vector", {"name": "v", "v": [1, 1, 1], "colour": "A"})], "SS281"),
    ([("remove", {"name": "nope"})], "SS476"),
    ([("vector", {"name": "v", "v": [1, 1, 1]}), ("relabel", {"name": "v"})], "SS476"),
    ([("relabel", {"label": "x"})], "SS476"),
])
def test_rejects(example, actions, code):
    assert code in add(example, S, *actions)


def test_bad_view_and_ranges(example):
    assert "SS475" in add(example, {**S, "view": {"azimuth": 0}})
    assert "SS202" in add(example, {**S, "z": [1, 3]})
    assert "SS202" in add(example, {**S, "axis_labels": ["x", "y"]})


def test_projection_math():
    p = project((1.0, 2.0, 3.0), {"kind": "plane", "u": (1.0, 0.0, 0.0), "w": (0.0, 1.0, 0.0)})
    assert p == pytest.approx((1, 2, 0))
    p = project((1.0, 2.0, 3.0), {"kind": "line", "dir": (1.0, 1.0, 0.0)})
    assert p == pytest.approx((1.5, 1.5, 0))
    u, w = plane_span((0.0, 0.0, 2.0))
    assert abs(u[2]) < 1e-12 and abs(w[2]) < 1e-12


def test_matrix_helpers():
    m = ((2.0, 1.0, 0.0), (0.0, 1.0, 3.0), (1.0, 0.0, 1.0))
    assert det(m) == pytest.approx(5)
    eye = mul(m, inv(m))
    assert all(eye[i][j] == pytest.approx(1.0 if i == j else 0.0) for i in range(3) for j in range(3))
