"""数据曲线和参数曲线：data 的 {src} 外部 JSON、graph 的 {data} 曲线、plane 的 curves / points（SS490–SS499）。"""

import copy
import json
import math
import os
import sys
from pathlib import Path

import pytest
import yaml
from conftest import ROOT

from scene_spec import check, check_file, curves
from scene_spec.loader import load_file

PHASE = ROOT / "examples" / "phase-portrait.scene.yaml"
DAMPED = json.loads((ROOT / "examples" / "assets" / "damped-phase.json").read_text())


@pytest.fixture
def phase() -> dict:
    """示例 phase-portrait 的副本，data 改成内联（不需要场景目录）。"""
    doc = copy.deepcopy(load_file(PHASE))
    doc["data"] = {"damped": copy.deepcopy(DAMPED)}
    return doc


def codes(doc: dict, root: Path | None = None) -> list[str]:
    return check(doc, root=root).codes()


def write_scene(tmp_path: Path, doc: dict, files: dict[str, str] | None = None) -> Path:
    for name, text in (files or {}).items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    scene = tmp_path / "s.scene.yaml"
    scene.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return scene


def plane(doc: dict) -> dict:
    return doc["objects"]["phase"]


# ---------- 示例：500 个点的阻尼振子相轨线 ----------

def test_example_with_src_passes():
    report = check_file(PHASE)
    assert report.issues == [], report.issues
    assert len(DAMPED) == 500


def test_inline_data_passes(phase):
    assert check(phase).issues == []


def test_src_is_skipped_without_a_scene_dir():
    """check(doc) 不知道场景文件在哪：{src} 不读，用到它的曲线跳过检查，不报错（和 clip 的 src 一样）。"""
    assert check(load_file(PHASE)).issues == []


def test_src_and_inline_load_the_same_points(tmp_path):
    doc = load_file(PHASE)
    assert curves.load_data(doc, PHASE.parent)["damped"] == DAMPED
    resolved = curves.resolve_data(doc["data"], None)
    assert isinstance(resolved["damped"], curves.Unavailable)


# ---------- 越界 ----------

def test_out_of_range_data_in_plane(phase):
    plane(phase)["y"] = [-2, 2]
    report = check(phase)
    assert report.codes() == ["SS497"]
    assert "第 14 个点" in report.errors[0].message and "y [-2, 2]" in report.errors[0].message


def test_out_of_range_data_in_graph(phase):
    phase["objects"]["phase"] = {"widget": "graph", "x": [-3, 3], "y": [-2, 2], "in": "stage",
                                 "plots": [{"data": "damped", "progress": "p"}]}
    assert codes(phase) == ["SS497"]
    phase["objects"]["phase"]["y"] = [-3, 3]
    assert codes(phase) == []


def test_out_of_range_src_data_reports_through_check_file(tmp_path, phase):
    phase["data"] = {"damped": {"src": "traj.json"}}
    plane(phase)["x"] = [-2, 2]
    scene = write_scene(tmp_path, phase, {"traj.json": json.dumps(DAMPED)})
    assert check_file(scene).codes() == ["SS497"]


def test_out_of_range_parametric(phase):
    plane(phase)["curves"].append({"x": "3.5cos(t)", "y": "3.5sin(t)", "domain": [0, 6.3]})
    assert codes(phase) == ["SS497"]
    plane(phase)["curves"][1] = {"x": "2cos(t)", "y": "2sin(t)", "domain": [0, 6.3], "progress": "p"}
    assert codes(phase) == []


def test_parametric_with_scene_params_is_checked_at_every_state(phase):
    """参数曲线引用场景参数：p 补间到 1 时半径 1+2p = 3 出了 y 范围 [-3, 3]？刚好在边上不算；放大到 1+3p 才算。"""
    plane(phase)["curves"].append({"x": "(1+2p)cos(t)", "y": "(1+2p)sin(t)", "domain": [0, 3.2]})
    assert codes(phase) == []
    plane(phase)["curves"][1]["y"] = "(1+3p)sin(t)"
    report = check(phase)
    assert report.codes() == ["SS497"] and "p=1" in report.errors[0].message


# ---------- 数据不对 ----------

@pytest.mark.parametrize("value,code", [
    ([], "SS493"),
    ([[0, 0]], "SS493"),  # 少于两个点
    ([[0, 0], [1]], "SS493"),
    ([[0, 0], [1, "a"]], "SS493"),
    ([[0, 0], [True, 1]], "SS493"),
    ([1, 2, 3], "SS493"),
    ({"a": 1}, "SS493"),
    ([[0, 0]] * 4097, "SS495"),
])
def test_bad_inline_data(phase, value, code):
    phase["data"]["damped"] = value
    assert codes(phase) == [code]


def test_4096_points_are_allowed(phase):
    phase["data"]["damped"] = [[math.cos(k / 600), math.sin(k / 600)] for k in range(4096)]
    assert codes(phase) == []


@pytest.mark.parametrize("text,code", [
    ("[[0, 0], [1, NaN]]", "SS494"),
    ("[[0, 0], [1, Infinity]]", "SS494"),
    ("[[0, 0], [1, 1e999]]", "SS494"),
    ("[[0, 0], [1, 1]", "SS492"),
    ("{\"points\": []}", "SS493"),
    ("[]", "SS493"),
])
def test_bad_json_files(tmp_path, phase, text, code):
    phase["data"] = {"damped": {"src": "traj.json"}}
    scene = write_scene(tmp_path, phase, {"traj.json": text})
    assert check_file(scene).codes() == [code]


@pytest.mark.parametrize("src,code", [
    ("missing.json", "SS491"),
    ("/etc/passwd.json", "SS490"),
    ("../outside.json", "SS490"),
    ("sub/../traj.json", "SS490"),
    ("traj.csv", "SS490"),
    ("", "SS490"),
    (3, "SS490"),
])
def test_bad_src_paths(tmp_path, phase, src, code):
    phase["data"] = {"damped": {"src": src}}
    scene = write_scene(tmp_path, phase, {"traj.json": json.dumps(DAMPED), "traj.csv": "0,0"})
    report = check_file(scene)
    assert report.codes() == [code], report.issues
    assert report.errors[0].path == "data.damped.src"


def test_src_with_extra_keys(tmp_path, phase):
    phase["data"] = {"damped": {"src": "traj.json", "scale": 2}}
    scene = write_scene(tmp_path, phase, {"traj.json": json.dumps(DAMPED)})
    assert check_file(scene).codes() == ["SS490"]


@pytest.mark.skipif(sys.platform == "win32", reason="符号链接")
def test_symlink_out_of_the_scene_dir(tmp_path, phase):
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(DAMPED))
    scene_dir = tmp_path / "scene"
    scene_dir.mkdir()
    os.symlink(outside, scene_dir / "traj.json")
    phase["data"] = {"damped": {"src": "traj.json"}}
    assert check_file(write_scene(scene_dir, phase)).codes() == ["SS490"]


def test_too_big_file(tmp_path, phase, monkeypatch):
    monkeypatch.setattr(curves, "MAX_BYTES", 100)
    phase["data"] = {"damped": {"src": "traj.json"}}
    scene = write_scene(tmp_path, phase, {"traj.json": json.dumps(DAMPED)})
    assert check_file(scene).codes() == ["SS491"]


def test_kit_loader_raises_with_the_same_codes(tmp_path):
    (tmp_path / "bad.json").write_text("[[0, NaN]]")
    with pytest.raises(curves.DataError) as exc:
        curves.load_data({"data": {"k": {"src": "bad.json"}}}, tmp_path)
    assert exc.value.code == "SS494" and "data.k" in exc.value.message
    with pytest.raises(curves.DataError) as exc:
        curves.load_data({"data": {"k": {"src": "nope.json"}}}, tmp_path)
    assert exc.value.code == "SS491"


def test_src_data_feeds_other_widgets(tmp_path, example):
    """{src} 是通用的：差分表的数列也可以放在 JSON 里。"""
    example["data"]["A"] = {"src": "a.json"}
    scene = write_scene(tmp_path, example, {"a.json": "[2, 5, 11, 21, 36, 57, 85, 121]"})
    assert check_file(scene).issues == []
    scene = write_scene(tmp_path, example, {"a.json": "[2, 5, 11, 21, 36, 57, 85, 120]"})
    assert check_file(scene).codes() == ["SS223"]


# ---------- 写法不对 ----------

@pytest.mark.parametrize("change,code", [
    (lambda w: w["curves"][0].update(data="nope"), "SS496"),
    (lambda w: w["curves"][0].update(x="t", y="t"), "SS496"),  # 数据曲线又写了 x、y
    (lambda w: w["curves"].append({"x": "t", "y": "t"}), "SS496"),  # 参数曲线缺 domain
    (lambda w: w["curves"].append({"x": "t", "y": "t", "domain": [1, 0]}), "SS496"),
    (lambda w: w["curves"].append({"x": "t", "y": "x", "domain": [0, 1]}), "SS401"),  # 参数曲线不能用 x
    (lambda w: w["curves"].append({"x": "t", "y": "q*t", "domain": [0, 1]}), "SS402"),
    (lambda w: w["curves"].append({"x": "t", "y": "sqrt(t)", "domain": [-1, 1]}), "SS498"),
    (lambda w: w["curves"][0].update(along="time"), "SS496"),
    (lambda w: w["curves"][0].update(progress="2p"), "SS499"),
    (lambda w: w["curves"][0].update(progress="q"), "SS402"),
    (lambda w: w["curves"][0].update(role="pink"), "SS202"),
    (lambda w: w["curves"][0].update(color="A"), "SS202"),  # 不认识的字段
    (lambda w: w["points"][0].update(curve=1), "SS496"),
    (lambda w: w["points"][0].pop("at"), "SS496"),
    (lambda w: w["points"][0].update(at="p-1"), "SS499"),
    (lambda w: w["points"][0].update(dir="up"), "SS202"),
    (lambda w: w.pop("curves"), "SS496"),  # 点没有曲线可走
])
def test_bad_curve_specs(phase, change, code):
    change(plane(phase))
    assert code in codes(phase)


def test_curve_var_t_clashes_with_a_scene_param(phase):
    phase["params"]["t"] = 0
    plane(phase)["curves"].append({"x": "cos(t)", "y": "sin(t)", "domain": [0, 1]})
    assert "SS496" in codes(phase)


def test_whole_plane_transforms_are_refused_with_curves(phase):
    phase["beats"][1]["do"].append({"after": "prev", "act": "warp", "target": "phase", "args": {"matrix": [[1, 0.5], [0, 1]]}})
    assert codes(phase) == ["SS496"]
    phase["beats"][1]["do"][-1] = {"after": "prev", "act": "rotate", "target": "phase", "args": {"angle": 90}}
    assert codes(phase) == ["SS496"]


def test_graph_data_plot_specs(phase):
    g = {"widget": "graph", "x": [-3, 3], "y": [-3, 3], "in": "stage"}
    for plots, code in [
        ([{"data": "damped", "f": "x"}], "SS496"),
        ([{}], "SS496"),
        ([{"data": "damped", "domain": [0, 1]}], "SS496"),
        ([{"f": "x", "progress": "p"}], "SS496"),  # progress 只用于数据曲线
        ([{"data": "nope"}], "SS496"),
        ([{"data": "damped", "progress": 1.5}], "SS499"),
    ]:
        phase["objects"]["phase"] = {**g, "plots": plots}
        assert code in codes(phase), plots
    phase["objects"]["phase"] = {**g, "plots": [{"data": "damped", "progress": "p", "label": "v(x)"}], "points": [{"x": 1}]}
    assert "SS496" in codes(phase)  # 点不能放在数据曲线上
    phase["objects"]["phase"] = {**g, "plots": [{"f": "x/2"}, {"data": "damped", "progress": "p", "along": "param"}],
                                 "points": [{"x": 1}]}
    assert codes(phase) == []


def test_parts_are_exposed(phase):
    phase["beats"][1]["do"].append({"after": "prev", "act": "mark", "target": "phase.point[0]"})
    phase["beats"][1]["do"].append({"after": "prev", "act": "focus", "target": "phase.curve[0]"})
    assert codes(phase) == []
    phase["beats"][1]["do"].append({"after": "prev", "act": "mark", "target": "phase.curve[1]"})
    assert codes(phase) == ["SS312"]


# ---------- 几何 ----------

def test_ruler_and_interpolation():
    pts = [(0.0, 0.0), (3.0, 0.0), (3.0, 1.0)]  # 长 3 + 1
    assert curves.ruler(pts) == [0.0, 0.75, 1.0]
    assert curves.ruler(pts, "param") == [0.0, 0.5, 1.0]
    assert curves.point_at(pts, curves.ruler(pts), 0.5) == (2.0, 0.0)
    assert curves.point_at(pts, curves.ruler(pts, "param"), 0.75) == (3.0, 0.5)
    assert curves.point_at(pts, curves.ruler(pts), 2.0) == (3.0, 1.0)  # 夹在 [0, 1]
    assert curves.prefix(pts, curves.ruler(pts), 0.0) == []
    assert curves.prefix(pts, curves.ruler(pts), 0.875) == [(0.0, 0.0), (3.0, 0.0), (3.0, 0.5)]
    assert curves.ruler([(1.0, 1.0), (1.0, 1.0)]) == [0.0, 1.0]  # 长度为 0：按序号


def test_trail_head_is_the_moving_point_and_grows_monotonically():
    pts = curves.points(DAMPED)
    for along in curves.ALONG:
        cum = curves.ruler(pts, along)
        last = -1.0
        for k in range(101):
            s = k / 100
            trail = curves.prefix(pts, cum, s)
            if trail:
                assert trail[-1] == curves.point_at(pts, cum, s)
            length = sum(math.dist(a, b) for a, b in zip(trail, trail[1:]))
            assert length >= last - 1e-12
            last = length


def test_src_data_for_other_widgets_is_skipped_without_a_scene_dir(example):
    example["data"]["A"] = {"src": "a.json"}
    assert check(example).issues == []
