"""综合几何图 geometry：构造求解、断言验算、检查器的报错。"""

import math

import pytest

from scene_spec import check
from scene_spec.geometry import GeoError, check_asserts, elements, solve


def add(doc, obj: dict, *actions: tuple[str, dict | None]) -> list[str]:
    """在示例里放一个组件 w，在 Down 段末尾依次做 actions，返回检查结果里组件相关的代码。"""
    doc["objects"]["w"] = {**obj, "in": "stage"}
    do = next(b for b in doc["beats"] if b["id"] == "Down")["do"]
    do.append({"after": "prev", "act": "show", "target": "w"})
    for act, args in actions:
        do.append({"after": "prev", "act": act, "target": "w", **({"args": args} if args is not None else {})})
    return [c for c in check(doc).codes() if c.startswith(("SS2", "SS3"))]


TRI = {
    "widget": "geometry",
    "points": {
        "O": [0, 0],
        "A": {"on": "c", "angle": 100},
        "B": {"on": "c", "angle": 215},
        "C": {"on": "c", "angle": 330},
        "D": {"meet": [["A", "O"], "c"], "not": "A"},
    },
    "circles": {"c": {"center": "O", "radius": 2}},
    "draw": [{"segment": ["A", "B"]}, {"segment": ["A", "C"]}, {"segment": ["A", "D"], "aux": True, "hidden": True},
             {"angle": ["B", "A", "C"]}, {"tick": ["O", "B"]}],
    "assert": [{"collinear": ["A", "O", "D"]}, {"equal": [["O", "A"], ["O", "B"], ["O", "C"]]}],
}


def near(p, q) -> bool:
    return math.dist(p, q) < 1e-9


# ---------- 构造 ----------

def test_constructions_land_where_they_should():
    d = {"points": {
        "A": [0, 0], "B": [4, 0], "C": [1, 3],
        "M": {"mid": ["B", "C"]},
        "H": {"foot": "A", "to": ["B", "C"]},
        "R": {"reflect": "A", "over": ["B", "C"]},
        "S": {"reflect": "A", "over": "M"},
        "G": {"centroid": ["A", "B", "C"]},
        "O": {"circumcenter": ["A", "B", "C"]},
        "Hh": {"orthocenter": ["A", "B", "C"]},
        "I": {"incenter": ["A", "B", "C"]},
        "X": {"meet": [["A", "M"], ["B", "C"]]},
        "P": {"on": ["A", "B"], "t": 0.25},
    }}
    f = solve(d)
    P = f.points
    assert near(P["M"], (2.5, 1.5)) and near(P["X"], P["M"]) and near(P["P"], (1, 0))
    assert near(P["S"], (5, 3)) and near(P["G"], (5 / 3, 1))
    assert near(((P["A"][0] + P["R"][0]) / 2, (P["A"][1] + P["R"][1]) / 2), P["H"])
    # 外心到三点等距；欧拉线 O、G、H 共线且 OH = 3 OG
    oa = [math.dist(P["O"], P[k]) for k in "ABC"]
    assert max(oa) - min(oa) < 1e-12
    assert near((3 * P["G"][0] - 2 * P["O"][0], 3 * P["G"][1] - 2 * P["O"][1]), P["Hh"])
    # 内心到三边等距
    def to_line(p, a, b):
        return abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / math.dist(a, b)
    ds = [to_line(P["I"], P[a], P[b]) for a, b in ("AB", "BC", "CA")]
    assert max(ds) - min(ds) < 1e-12


def test_circle_intersections_and_tangents():
    d = {"points": {
        "O": [0, 0], "Q": [3, 0], "P": [5, 0],
        "E": {"meet": ["c", "w"], "index": 0},
        "F": {"meet": ["c", "w"], "not": "E"},
        "T": {"tangent": "P", "circle": "c", "index": 0},
        "U": {"tangent": "P", "circle": "c", "not": "T"},
        "B": {"on": "c", "angle": 200}, "C": {"on": "c", "angle": 340},
        "K": {"meet": [{"tangent_at": "B", "circle": "c"}, {"tangent_at": "C", "circle": "c"}]},
        "N": {"meet": [{"through": "P", "perp": ["O", "Q"]}, "c2"], "index": 1},
    }, "circles": {"c": {"center": "O", "radius": 2}, "w": {"center": "Q", "radius": 2}, "c2": {"center": "P", "radius": 1}}}
    f = solve(d)
    P = f.points
    assert P["E"][1] > 0 > P["F"][1] and abs(P["E"][0] - 1.5) < 1e-12  # 第 0 个在 c→w 连线左边（上面）
    for k in "TU":
        assert abs(math.dist(P[k], (0, 0)) - 2) < 1e-12
        assert abs((P[k][0] - 5) * P[k][0] + P[k][1] * P[k][1]) < 1e-9  # PT ⊥ OT
    assert P["T"][1] < 0 < P["U"][1]  # 从 P 看圆心，左边（下面）的是第 0 个
    assert abs(math.dist(P["K"], P["B"]) - math.dist(P["K"], P["C"])) < 1e-12 and abs(P["K"][0]) < 1e-12
    assert near(P["N"], (5, 1))


def test_dependencies_and_free_points():
    f = solve(TRI)
    assert f.free == {"A": "angle", "B": "angle", "C": "angle"}
    assert {"A", "O", "c"} <= f.deps["D"]
    g = solve(TRI, {"A": 140})
    assert near(g.points["A"], (2 * math.cos(math.radians(140)), 2 * math.sin(math.radians(140))))
    assert near(g.points["D"], (-g.points["A"][0], -g.points["A"][1]))


@pytest.mark.parametrize("points, circles, code, words", [
    ({"A": [0, 0], "B": [1, 0], "X": {"meet": [["A", "B"], ["A", "B"]]}}, {}, "SS272", "平行"),
    ({"A": [0, 0], "B": [1, 0], "X": {"meet": [["A", "B"], "c"]}}, {"c": {"center": "A", "radius": 1}}, "SS272", "两个交点"),
    ({"A": [0, 5], "B": [1, 5], "X": {"meet": [["A", "B"], "c"], "not": "A"}}, {"c": {"center": "Z", "radius": 1}}, "SS271", "没有点 Z"),
    ({"A": [0, 9], "B": [1, 9], "Z": [0, 0], "X": {"meet": [["A", "B"], "c"], "index": 0}},
     {"c": {"center": "Z", "radius": 1}}, "SS272", "没有交点"),
    ({"A": [0, 0], "B": [1, 1], "C": [2, 2], "O": {"circumcenter": ["A", "B", "C"]}}, {}, "SS272", "共线"),
    ({"A": {"mid": ["A", "B"]}, "B": [0, 0]}, {}, "SS271", "循环引用"),
    ({"A": {"mid": ["A2", "B"]}, "A2": {"mid": ["A", "B"]}, "B": [0, 0]}, {}, "SS271", "循环引用"),
    ({"A": {"midpoint": ["A2", "B"]}}, {}, "SS271", "恰好有一种构造"),
    ({"A": [0, 0], "T": {"tangent": "A", "circle": "c", "index": 0}}, {"c": {"center": "A", "radius": 1}}, "SS272", "点在圆内"),
])
def test_bad_constructions_raise(points, circles, code, words):
    with pytest.raises(GeoError) as err:
        solve({"points": points, "circles": circles})
    assert err.value.code == code and words in err.value.msg


# ---------- 断言 ----------

def test_asserts_pass_and_fail():
    d = {**TRI, "assert": TRI["assert"] + [
        {"concyclic": ["A", "B", "C", "D"]},
        {"equal_angle": [["B", "A", "C"], ["B", "D", "C"]]},  # D 在 BC 另一侧：互补，不相等
        {"perpendicular": [["A", "B"], ["B", "D"]]},  # AD 是直径
        {"on": ["D", "c"]},
        {"equal": [["A", "B"], ["A", "C"]]},
    ]}
    bad = check_asserts(solve(d), d)
    assert [p for p, _ in bad] == ["assert[3]", "assert[6]"]
    assert "∠BAC=57.5°" in bad[0][1] and "AB=" in bad[1][1]


def test_concurrent_and_parallel():
    d = {"points": {"A": [0, 0], "B": [4, 0], "C": [1, 3], "Ma": {"mid": ["B", "C"]}, "Mb": {"mid": ["A", "C"]},
                    "Mc": {"mid": ["A", "B"]}},
         "assert": [{"concurrent": [["A", "Ma"], ["B", "Mb"], ["C", "Mc"]]}, {"parallel": [["Ma", "Mb"], ["A", "B"]]}]}
    assert check_asserts(solve(d), d) == []


def test_element_names_default_and_clash():
    names = [e.name for e in elements(TRI)]
    assert names == ["c", "AB", "AC", "AD", "ang_BAC", "tick_OB", "O", "A", "B", "C", "D"]
    with pytest.raises(GeoError, match="重复"):
        elements({**TRI, "draw": [{"segment": ["A", "B"]}, {"segment": ["A", "B"]}]})


# ---------- 检查器 ----------

def test_geometry_widget_passes(example):
    assert add(example, TRI,
               ("draw", {"name": ["AD", "D"]}),
               ("shade", {"name": "ang_BAC"}),
               ("ring", {"name": "A", "role": "NO"}),
               ("dim", {"except": ["AB", "AC"]}),
               ("restore", None),
               ("trace", {"point": "A", "to": 140})) == []


def test_parts_can_be_shown(example):
    example["objects"]["w"] = {**TRI, "in": "stage"}
    do = next(b for b in example["beats"] if b["id"] == "Down")["do"]
    do.append({"after": "prev", "act": "show", "target": "w.AD"})
    do.append({"after": "prev", "act": "show", "target": "w.nope"})
    codes = check(example).codes()
    assert codes.count("SS311") + codes.count("SS312") >= 1


@pytest.mark.parametrize("change, code", [
    ({"assert": [{"equal": [["A", "B"], ["A", "C"]]}]}, "SS273"),
    ({"points": {**TRI["points"], "D": {"meet": [["A", "O"], "c"]}}}, "SS272"),
    ({"draw": [{"segment": ["A", "Q"]}]}, "SS271"),
    ({"draw": [{"angle": ["B", "A", "C"], "right": True}]}, "SS273"),
    ({"box": [-1, -1, 1, 1]}, "SS275"),
    ({"bogus": 1}, "SS203"),
])
def test_definition_errors(example, change, code):
    assert code in add(example, {**TRI, **change})


@pytest.mark.parametrize("act, args, code", [
    ("draw", {"name": "XY"}, "SS274"),
    ("shade", {"name": "AB"}, "SS274"),
    ("trace", {"point": "D", "to": 3}, "SS274"),
    ("dim", {}, "SS274"),
    ("ring", {"name": "A", "size": 2}, "SS281"),
    ("highlight", {"name": "A", "role": "PINK"}, "SS274"),
])
def test_action_errors(example, act, args, code):
    assert code in add(example, TRI, (act, args))


def test_trace_keeps_asserts_true_along_the_way(example):
    d = {**TRI, "assert": [{"equal_angle": [["B", "A", "C"], ["B", "P", "C"]]}],
         "points": {**TRI["points"], "P": {"on": "c", "angle": 150}}}
    assert add(example, d, ("trace", {"point": "A", "to": 60})) == []
    # 滑过 B 到劣弧上，圆周角变成补角：断言途中失效
    assert "SS273" in add(example, d, ("trace", {"point": "A", "to": 270}))


def test_construction_only_points_are_not_drawn_and_ignore_the_box(example):
    """draw: false 的点只参与构造：不画、不算进图框，伸出 box 也不报 SS275；断言照样能用它。"""
    pts = {**TRI["points"], "F": {"at": [9, 9], "draw": False},
           "G": {"mid": ["F", "O"], "draw": False}, "H": {"mid": ["G", "O"]}}
    d = {**TRI, "points": pts, "box": [-2.5, -2.5, 3.0, 3.0],
         "assert": [*TRI["assert"], {"collinear": ["O", "H", "F"]}]}
    assert add(example, d) == []
    names = {e.name for e in elements(d)}
    assert "H" in names and not {"F", "G"} & names
    # 不写 draw: false 时，伸出图框照样报错
    assert "SS275" in add(example, {**d, "points": {**pts, "F": [9, 9]}})
