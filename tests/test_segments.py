"""分段播放、残影和常驻公式（ghost / unghost / step / pin，SS440–SS459）。用 ep09 分段版做底稿。"""

import copy
from pathlib import Path

import pytest

from scene_spec import check, check_file, segments
from scene_spec.loader import load_file

EP09 = Path(__file__).resolve().parents[1] / "examples" / "ep09.scene.yaml"
BASE = load_file(EP09)


@pytest.fixture
def ep09() -> dict:
    return copy.deepcopy(BASE)


def beat(doc: dict, beat_id: str) -> dict:
    return next(b for b in doc["beats"] if b["id"] == beat_id)


def codes(doc: dict, prefix: str = "SS4") -> list[tuple[str, str]]:
    return [(i.level, i.code) for i in check(doc).issues if i.code.startswith(prefix)]


def test_ep09_segmented_passes():
    report = check_file(EP09)
    assert report.issues == []
    assert report.stats["steps"] == 6 and report.stats["ghosts"] == 2 and report.stats["pins"] == 1


def test_examples_without_segments_keep_their_stats():
    report = check_file(EP09.parent / "s67-p01.scene.yaml")
    assert "steps" not in report.stats and "ghosts" not in report.stats


def test_ghost_must_target_whole_object(ep09):
    beat(ep09, "Count")["do"].append({"after": "prev", "act": "ghost", "target": "eq1#x3"})
    assert ("error", "SS440") in codes(ep09)


def test_ghost_before_show_warns(ep09):
    beat(ep09, "Hook")["do"].insert(0, {"at": "s1", "act": "ghost", "target": "line"})
    assert ("warning", "SS442") in codes(ep09)


def test_ghost_stay_with_gap_warns(ep09):
    beat(ep09, "Count")["do"].append({"after": "prev", "act": "ghost", "target": "line", "args": {"gap": "sm"}})
    assert ("warning", "SS441") in codes(ep09)


def test_ghost_labels_flag(ep09):
    do = beat(ep09, "Count")["do"]
    do.append({"after": "prev", "act": "ghost", "target": "line", "args": {"labels": False}})
    assert not [c for c in codes(ep09, "SS1") if c[0] == "error"]
    do[-1]["args"]["labels"] = "no"
    assert ("error", "SS100") in codes(ep09, "SS1")


def test_too_many_ghosts_warn(ep09):
    do = beat(ep09, "Count")["do"]
    for _ in range(3):
        do.append({"after": "prev", "act": "ghost", "target": "line", "args": {"place": "above"}})
    assert ("warning", "SS452") in codes(ep09)


def test_unghost_without_ghost(ep09):
    beat(ep09, "Count")["do"].append({"after": "prev", "act": "unghost", "target": "line"})
    assert ("error", "SS443") in codes(ep09)


def test_hiding_original_drops_its_ghosts(ep09):
    """Leftover 留下的残影在 Compare 收掉；如果先把 line 整个 hide，残影随之消失，再 unghost 就是空的。"""
    compare = beat(ep09, "Compare")["do"]
    compare.insert(1, {"with": "prev", "act": "hide", "target": "line"})
    assert ("error", "SS443") in codes(ep09)


@pytest.mark.parametrize("extra, code", [
    ({"target": "line"}, "SS444"),
    ({"dur": 1}, "SS444"),
])
def test_step_takes_no_target_or_dur(ep09, extra, code):
    beat(ep09, "Count")["do"].append({"after": "prev", "act": "step", **extra})
    assert ("error", code) in codes(ep09)


def test_step_mid_sentence_warns(ep09):
    beat(ep09, "Count")["do"].append({"at": "s3@d", "act": "step"})
    assert ("warning", "SS446") in codes(ep09)


@pytest.mark.parametrize("anchor", [{"after": "prev"}, {"with": "prev"}])
def test_step_after_previous_action_warns(ep09, anchor):
    """挂在 after / with 上的定格落点取决于前面动作的时长，容易切进句子中间。"""
    assert ("warning", "SS447") not in codes(ep09)  # 样片里的子步都写在句子开头
    beat(ep09, "Count")["do"].append({**anchor, "act": "step"})
    assert ("warning", "SS447") in codes(ep09)


def test_step_without_segmented_warns(ep09):
    ep09["style"]["segmented"] = False
    found = codes(ep09)
    assert ("warning", "SS445") in found and ("warning", "SS451") in found  # step_hold 也没用了
    assert ("warning", "SS446") not in found


def test_too_many_steps_in_one_beat(ep09):
    beat(ep09, "Count")["do"] += [{"after": "prev", "act": "step"} for _ in range(4)]
    assert ("warning", "SS453") in codes(ep09)


def test_pinned_object_cannot_be_hidden_or_moved(ep09):
    beat(ep09, "Halves")["do"].insert(1, {"with": "prev", "act": "hide", "target": "law"})
    beat(ep09, "Close")["do"].append({"after": "prev", "act": "move", "target": "law", "args": {"in": "side"}})
    assert codes(ep09).count(("error", "SS448")) == 2


def test_hiding_part_of_pinned_object_is_also_an_error(ep09):
    beat(ep09, "Close")["do"].append({"after": "prev", "act": "hide", "target": "law#flip"})
    assert ("error", "SS448") in codes(ep09)


def test_clear_on_pinned_object_is_fine(ep09):
    beat(ep09, "Close")["do"].append({"after": "prev", "act": "clear", "target": "law"})
    assert codes(ep09) == []


def test_pin_rules(ep09):
    landing = beat(ep09, "Landing")["do"]
    landing.append({"after": "prev", "act": "pin", "target": "law#flip"})
    landing.append({"after": "prev", "act": "pin", "target": "law"})
    beat(ep09, "Hook")["do"].append({"after": "prev", "act": "pin", "target": "practice"})
    found = codes(ep09)
    assert ("error", "SS447") in found and ("warning", "SS449") in found and ("error", "SS450") in found


@pytest.mark.parametrize("action", [
    {"act": "ghost", "target": "line", "args": {"place": "behind"}},
    {"act": "ghost", "target": "line", "args": {"scale": 2}},
    {"act": "ghost", "target": "line", "args": {"opacity": 0.9}},
    {"act": "ghost", "target": "line", "args": {"role": "DIM"}},
    {"act": "step", "args": {"hold": -1}},
    {"act": "step", "args": {"seconds": 2}},
    {"act": "pin", "target": "law", "args": {"in": "side"}},
    {"act": "unghost", "target": "line", "args": {"all": True}},
])
def test_schema_rejects_bad_args(ep09, action):
    beat(ep09, "Close")["do"].append({"after": "prev", **action})
    assert ("error", "SS100") in codes(ep09, "SS1")


def test_schema_checks_step_hold(ep09):
    ep09["style"]["step_hold"] = 30
    assert ("error", "SS100") in codes(ep09, "SS1")


def test_step_hold_resolution(ep09):
    assert segments.step_hold(ep09, {"act": "step"}) == 1.0
    assert segments.step_hold(ep09, {"act": "step", "args": {"hold": 2.5}}) == 2.5
    ep09["style"]["step_hold"] = 0.6
    assert segments.step_hold(ep09, {"act": "step"}) == 0.6
    ep09["style"]["segmented"] = False
    assert segments.step_hold(ep09, {"act": "step", "args": {"hold": 2.5}}) == 0.0
