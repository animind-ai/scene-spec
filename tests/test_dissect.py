"""剖分组件 dissect：几何（切块、吸附、扇形排列、拼合轮廓）和检查（SS420–SS439）。"""

import copy
import math
from pathlib import Path

import pytest

from scene_spec import check, check_file
from scene_spec import dissect as G
from scene_spec.loader import load_file

EP11 = Path(__file__).resolve().parents[1] / "examples" / "ep11.scene.yaml"
PARA = [(0, 0), (6, 0), (9, 3), (3, 3)]


# ---------- 几何 ----------

def test_parallelogram_cut_along_height():
    faces, cuts = G.split_polygon(PARA, [(3, 3), (3, 0)], infinite=True)
    assert len(faces) == 2
    areas = sorted(abs(G.signed_area(f)) for f in faces)
    assert areas == pytest.approx([4.5, 13.5])
    assert len(cuts) == 1


def test_polyline_cuts_corner_square_out_of_square():
    square = [(0, 0), (5, 0), (5, 5), (0, 5)]
    faces, _ = G.split_polygon(square, [(5, 3), (3, 3), (3, 5)])
    assert sorted(abs(G.signed_area(f)) for f in faces) == pytest.approx([4, 21])


def test_cut_that_stops_inside_does_not_split():
    faces, cuts = G.split_polygon([(0, 0), (5, 0), (5, 5), (0, 5)], [(1, 1), (2, 3)])
    assert len(faces) == 1 and cuts == []


def test_straight_cut_through_u_shape_gives_three_pieces():
    u = [(0, 0), (6, 0), (6, 4), (4, 4), (4, 2), (2, 2), (2, 4), (0, 4)]
    faces, _ = G.split_polygon(u, [(-1, 3), (9, 3)], infinite=True)
    assert len(faces) == 3
    assert sum(abs(G.signed_area(f)) for f in faces) == pytest.approx(abs(G.signed_area(u)))


def test_cut_along_an_edge_is_ignored():
    l_shape = [(0, 0), (5, 0), (5, 3), (3, 3), (3, 5), (0, 5)]
    faces, cuts = G.split_polygon(l_shape, [(3, -1), (3, 9)], infinite=True)
    assert len(faces) == 2 and len(cuts) == 1  # x=3 上沿着边的那一段不算切口


def test_edge_map_is_rigid():
    m = G.edge_map((0, 0), (3, 3), (6, 0), (9, 3))
    assert m((0, 0)) == pytest.approx((6, 0)) and m((3, 0)) == pytest.approx((9, 0))
    m = G.edge_map((0, 0), (1, 0), (2, 2), (2, 3))
    assert m.det == pytest.approx(1) and m((1, 1)) == pytest.approx((1, 3))


def test_reflect_is_involution():
    r = G.reflect((0, 0), (1, 1))
    assert r((2, 0)) == pytest.approx((0, 2))
    assert (r @ r)((3, -1)) == pytest.approx((3, -1))


def test_union_outline_of_parallelogram_pieces_is_rectangle():
    t = [(6, 0), (9, 0), (9, 3)]
    q = [(3, 0), (6, 0), (9, 3), (3, 3)]
    segs = G.union_outline([t, q])
    assert sum(G.dist(p, q) for p, q in segs) == pytest.approx(18)  # 周长 2×(6+3)，斜边被抵消


@pytest.mark.parametrize("n", [8, 16, 64])
def test_alternate_sectors_approach_rectangle(n):
    r = 2.0
    plan = G.plan_of({"shapes": {"O": {"circle": r}}, "cuts": {"c": {"piece": "O", "sectors": n, "into": "s"}}})
    assert not plan.problems
    sectors = [plan.pieces[f"s{i}"] for i in range(n)]
    poses = G.alternate_poses(sectors, (0.0, 0.0))
    # 相邻两块共用一条半径、互不重叠：它们的重心在那条半径的两侧
    for k in range(n - 1):
        a, b = sectors[k], sectors[k + 1]
        tip = poses[k](a.points[0])
        assert any(G.same(tip, poses[k + 1](v)) for v in b.vertices())
    pts = [p(v) for p, s in zip(poses, sectors) for v in s.outline()]
    width = max(x for x, _ in pts) - min(x for x, _ in pts)
    height = max(y for _, y in pts) - min(y for _, y in pts)
    # 越切越接近 πr × r：宽多出约半块扇形的弦，高趋于 r
    chord = 2 * r * math.sin(math.pi / n)
    assert width == pytest.approx((n + 1) / 2 * chord)  # n/2 条弦，再加最后半块
    assert abs(width - math.pi * r) < chord  # 和 πr 只差不到一条弦，n 越大越接近
    assert height == pytest.approx(r, rel=0.1 if n == 8 else 0.02)
    area = sum(abs(G.signed_area([p(v) for v in s.outline()])) for p, s in zip(poses, sectors))
    assert area == pytest.approx(math.pi * r * r, rel=0.01)


def test_sectors_closer_with_more_pieces():
    gaps = []
    for n in (8, 16, 64):
        plan = G.plan_of({"shapes": {"O": {"circle": 1}}, "cuts": {"c": {"piece": "O", "sectors": n, "into": "s"}}})
        sectors = [plan.pieces[f"s{i}"] for i in range(n)]
        poses = G.alternate_poses(sectors)
        pts = [p(v) for p, s in zip(poses, sectors) for v in s.outline()]
        h = max(y for _, y in pts) - min(y for _, y in pts)
        gaps.append(h - 1)  # 上下边的"波浪"高度
    assert gaps[0] > gaps[1] > gaps[2] > 0


def test_into_names_follow_centroid_order():
    plan = G.plan_of({"shapes": {"P": {"polygon": [list(p) for p in PARA]}},
                      "cuts": {"c": {"piece": "P", "line": [[3, 3], [3, 0]], "into": ["T", "Q"]}}})
    assert G.signed_area(plan.pieces["T"].points) == pytest.approx(4.5)
    assert plan.pieces["T"].find_edge((0, 0), (3, 3)) is not None


def test_dots_cut_and_staircase():
    plan = G.plan_of({"shapes": {"D": {"dots": {"rows": [1, 2, 3, 4]}}},
                      "cuts": {"c": {"piece": "D", "line": [[1.5, -1], [1.5, 9]], "into": ["L", "R"]}}})
    assert not plan.problems
    assert len(plan.pieces["L"].points) == 7 and len(plan.pieces["R"].points) == 3


# ---------- 检查 ----------

@pytest.fixture
def ep11() -> dict:
    return copy.deepcopy(load_file(EP11))


def codes(doc) -> list[str]:
    return check(doc).codes()


def beat(doc, beat_id):
    return next(b for b in doc["beats"] if b["id"] == beat_id)


def para(doc):
    return doc["objects"]["para"]


def test_ep11_passes():
    report = check_file(EP11)
    assert report.issues == []


def test_degenerate_polygon(ep11):
    para(ep11)["shapes"]["P"]["polygon"] = [[0, 0], [1, 1], [2, 2]]
    assert "SS420" in codes(ep11)


def test_self_intersecting_polygon(ep11):
    para(ep11)["shapes"]["P"]["polygon"] = [[0, 0], [4, 4], [4, 0], [0, 4]]
    assert "SS420" in codes(ep11)


def test_duplicate_name(ep11):
    para(ep11)["guides"]["T"] = {"from": [0, 0], "to": [1, 0]}
    assert "SS421" in codes(ep11)


def test_cut_of_missing_piece(ep11):
    para(ep11)["cuts"]["c1"]["piece"] = "PP"
    assert "SS422" in codes(ep11)


def test_cut_that_misses_the_shape(ep11):
    para(ep11)["cuts"]["c1"]["line"] = [[20, 0], [20, 3]]
    assert "SS423" in codes(ep11)


def test_into_count_mismatch(ep11):
    para(ep11)["cuts"]["c1"]["into"] = ["T", "Q", "X"]
    assert "SS424" in codes(ep11)


def test_sectors_on_polygon(ep11):
    para(ep11)["cuts"]["c1"] = {"piece": "P", "sectors": 8, "into": "s"}
    assert "SS425" in codes(ep11)


def test_action_on_unknown_piece(ep11):
    beat(ep11, "Cut")["do"][3]["args"]["piece"] = "TT"
    assert "SS426" in codes(ep11)


def test_piece_used_before_its_cut(ep11):
    beat(ep11, "Hook")["do"].append({"after": "prev", "act": "shift", "target": "para", "args": {"piece": "T", "by": [1, 0]}})
    report = check(ep11)
    assert report.codes() == ["SS427"]
    assert "cut c1" in report.errors[0].message


def test_piece_used_after_it_was_cut(ep11):
    beat(ep11, "Landing")["do"].append({"after": "prev", "act": "rotate", "target": "para", "args": {"piece": "P", "angle": 90}})
    assert codes(ep11) == ["SS427"]


def test_snap_target_missing(ep11):
    snap = beat(ep11, "Cut")["do"][4]
    snap["args"]["to_edge"] = [[6, 0], [9, 2]]
    assert codes(ep11) == ["SS428"]
    snap["args"]["to"] = "nowhere"
    assert codes(ep11) == ["SS426"]


def test_snap_edge_lengths_must_match(ep11):
    snap = beat(ep11, "Cut")["do"][4]
    snap["args"]["to_edge"] = [[3, 0], [6, 0]]
    assert codes(ep11) == ["SS429"]


def test_degenerate_flip_axis(ep11):
    beat(ep11, "Landing")["do"].append(
        {"after": "prev", "act": "flip", "target": "para", "args": {"piece": "Q", "axis": [[1, 1], [1, 1]]}})
    assert codes(ep11) == ["SS430"]


def test_flip_about_own_edge_must_exist(ep11):
    beat(ep11, "Landing")["do"].append(
        {"after": "prev", "act": "flip", "target": "para", "args": {"piece": "Q", "axis": {"edge": [[3, 0], [9, 3]]}}})
    assert codes(ep11) == ["SS428"]


def test_rotate_needs_angle(ep11):
    beat(ep11, "Landing")["do"].append({"after": "prev", "act": "rotate", "target": "para", "args": {"piece": "Q"}})
    assert codes(ep11) == ["SS431"]


def test_move_needs_by_or_to(ep11):
    beat(ep11, "Cut")["do"][3]["args"] = {"piece": "T"}
    assert codes(ep11) == ["SS432"]


def test_merge_unknown_and_unmerge_before_merge(ep11):
    beat(ep11, "Cut")["do"][6]["args"]["name"] = "RR"
    assert "SS433" in codes(ep11)  # 也会让后面的 unmerge R 报 SS433


def test_arrange_needs_sector_cut(ep11):
    beat(ep11, "Landing")["do"].append({"after": "prev", "act": "arrange", "target": "para", "args": {"cut": "c1"}})
    assert codes(ep11) == ["SS434"]


def test_copy_must_be_declared(ep11):
    beat(ep11, "Landing")["do"].append({"after": "prev", "act": "copy", "target": "para", "args": {"piece": "Q2"}})
    assert codes(ep11) == ["SS435"]
    para(ep11)["copies"] = {"Q2": "Q"}
    assert codes(ep11) == []


def test_unknown_action_arg(ep11):
    beat(ep11, "Cut")["do"][3]["args"]["speed"] = 2
    assert codes(ep11) == ["SS436"]


def test_bad_guide(ep11):
    para(ep11)["guides"]["h"]["to"] = [3, 3]
    assert codes(ep11) == ["SS437"]


def test_schema_checks_dissect_fields(ep11):
    para(ep11)["guides"]["h"]["side"] = "inside"
    assert codes(ep11) == ["SS100"]
    del para(ep11)["guides"]["h"]["side"]
    para(ep11)["shapes"]["P"]["colour"] = "red"
    assert codes(ep11) == ["SS100"]


def test_style_for_missing_edge(ep11):
    para(ep11)["shapes"]["P"]["edges"][1]["at"] = [[0, 0], [9, 3]]
    assert codes(ep11) == ["SS439"]


def test_cut_twice(ep11):
    beat(ep11, "Landing")["do"].append({"after": "prev", "act": "cut", "target": "para", "args": {"cut": "c1"}})
    assert codes(ep11) == ["SS422"]


def test_sector_episode_snippet_passes():
    doc = copy.deepcopy(load_file(EP11))
    doc["objects"]["pizza"] = {
        "widget": "dissect", "in": "stage",
        "shapes": {"O": {"circle": 2}},
        "cuts": {"c8": {"piece": "O", "sectors": 8, "into": "s"}},
    }
    beat(doc, "Close")["do"] += [
        {"after": "prev", "act": "cut", "target": "pizza", "args": {"cut": "c8"}},
        {"after": "prev", "act": "arrange", "target": "pizza", "args": {"cut": "c8", "layout": "alternate"}},
        {"after": "prev", "act": "shift", "target": "pizza", "args": {"piece": "s3", "by": [0, 1]}},
    ]
    assert codes(doc) == []


# ---------- fold：沿一刀直线的切线把一侧翻过去（SS438） ----------

# 等腰直角三角形，直角在原点；沿 A 角的角平分线折，直角边 AC 落到斜边 AB 上
R2 = math.sqrt(2)
TRI = {
    "widget": "dissect", "in": "stage",
    "shapes": {"T": {"polygon": [[0, 0], [5, 0], [0, 5]]}},
    "cuts": {
        "f1": {"piece": "T", "line": [[0, 5], [5 * (R2 - 1), 0]], "into": ["flap", "rest"]},
        "c2": {"piece": "rest", "path": [[3, -1], [3, 1], [6, 1]], "into": ["x", "y"]},
    },
}


def fold_doc(*acts) -> dict:
    doc = copy.deepcopy(load_file(EP11))
    doc["objects"]["sheet"] = copy.deepcopy(TRI)
    beat(doc, "Close")["do"] += [{"after": "prev", "act": "fold", "target": "sheet", "args": a} for a in acts]
    return doc


def test_line_cut_records_its_crease():
    plan = G.plan_of(TRI)
    assert plan.problems == []
    assert plan.cuts["f1"].crease == ((0.0, 5.0), (5 * (R2 - 1), 0.0))
    assert set(plan.cuts["f1"].into) == {"flap", "rest"}


def test_fold_cuts_first_then_flap_can_fold_back():
    doc = fold_doc({"cut": "f1", "flap": "flap", "back": "B"}, {"cut": "f1", "flap": "flap"})
    assert codes(doc) == []
    beat(doc, "Close")["do"].append({"after": "prev", "act": "shift", "target": "sheet", "args": {"piece": "T", "by": [1, 0]}})
    assert codes(doc) == ["SS427"]  # fold 已经把 T 切开了


def test_fold_needs_a_straight_line_cut():
    doc = fold_doc({"cut": "c2", "flap": "x"})
    assert codes(doc) == ["SS438"]
    assert codes(fold_doc({"cut": "nope", "flap": "x"})) == ["SS422"]


@pytest.mark.parametrize("args", [
    {"cut": "f1"},
    {"cut": "f1", "flap": "x"},
    {"cut": "f1", "flap": ["flap", "rest"]},
    {"cut": "f1", "flap": "flap", "back": "red"},
])
def test_bad_fold_args(args):
    assert codes(fold_doc(args)) == ["SS438"]


def test_fold_of_a_piece_already_gone():
    doc = fold_doc({"cut": "f1", "flap": "flap"})
    doc["objects"]["sheet"]["cuts"]["c3"] = {"piece": "flap", "line": [[0, 1], [1, 1]], "into": ["p", "q"]}
    beat(doc, "Close")["do"] += [
        {"after": "prev", "act": "cut", "target": "sheet", "args": {"cut": "c3"}},
        {"after": "prev", "act": "fold", "target": "sheet", "args": {"cut": "f1", "flap": "flap"}},
    ]
    assert codes(doc) == ["SS427"]
