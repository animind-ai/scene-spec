"""硬门槛：画面晚于书签、句间静音、旁白声音。"""

import pytest
from conftest import minimal_insight

from scene_spec import check, check_timing
from scene_spec.pauses import classify, silence_after
from scene_spec.quality import allowlist

NAN = float("nan")
INF = float("inf")
NINF = float("-inf")


def codes(doc, **kwargs):
    return check(doc, **kwargs).codes()


def test_published_voice_defaults_pass(insight):
    assert "SS482" not in codes(insight)
    insight["style"] = {"voice": {"persona": "teacher-hs", "model": "google/gemini-3.8-flash-tts", "voice": "Kore", "speed": 1}}
    assert codes(insight) == []


def test_voice_policy_rejects_other_model_voice_speed(insight):
    insight["style"] = {"voice": {"model": "google/gemini-2.5-pro-tts", "voice": "Kore", "speed": 1}}
    assert codes(insight) == ["SS482"]
    insight["style"]["voice"] = {"voice": "Aoede", "speed": 1}
    assert codes(insight) == ["SS482"]
    insight["style"]["voice"] = {"speed": 1.25}
    report = check(insight)
    assert report.codes() == ["SS482"]
    assert "1" in report.errors[0].message and "allowlist" in report.errors[0].message


def test_week1_series_is_allowlisted(insight):
    insight["meta"]["series"] = "week-1-competition"
    insight["style"] = {"voice": {"model": "google/gemini-2.5-flash-tts", "voice": "Puck", "speed": 1.15}}
    assert "SS482" not in codes(insight)
    insight["meta"]["series"] = "some-other-series"
    assert codes(insight) == ["SS482"]


def test_allowlist_file_names_the_exception_series_only():
    entries = allowlist()
    week1 = next(e for e in entries if e.get("series") == "week-1-competition")
    assert week1["name"] == "week-1 competition 20 problems"
    assert week1["codes"] == ["SS482"]
    assert "HOOK_MYTH_BY_S" not in week1["codes"]
    assert "SS362" not in week1["codes"] and "SS365" not in week1["codes"]


def test_hook_checks_still_fire_beside_new_gates(insight):
    """SS362 / SS365 是现有的钩子与预测检查，新门槛不取代它们。"""
    del next(b for b in insight["beats"] if b["id"] == "Hook")["shows"]
    assert "SS362" in codes(insight)
    doc = minimal_insight()
    doc["beats"] = [b for b in doc["beats"] if b["id"] != "Predict"]
    assert codes(doc) == ["SS365"]


def test_punctuation_table():
    assert classify("先想一想，") == "comma"
    assert classify("看这里。") == "period"
    assert classify("等于几？") == "question"
    assert classify("真的！") == "exclaim"
    assert classify("Wait...") == "ellipsis"
    assert classify("接着；") == "semicolon"
    assert classify("no mark") == "other"
    assert classify("书签在句号前。{@m}") == "period"
    assert silence_after("看这里。") == 0.45
    assert silence_after("看这里。", 0.5) == 0.5
    assert silence_after("看这里。", float("nan")) == 0.45
    assert silence_after("看这里。", float("inf")) == 0.45
    assert silence_after("Wait?") == 0.60
    assert silence_after("Done!") == 0.55
    assert silence_after("and,") == 0.22


def test_sentence_hold_must_match_punctuation(insight):
    sentence = insight["beats"][0]["say"][0]
    sentence["text"] = "先等一下，{@w}"
    sentence["hold"] = 0.2
    assert codes(insight) == []
    sentence["hold"] = 0.9
    report = check(insight)
    assert report.codes() == ["SS485"]
    assert "0.12" in report.errors[0].message
    sentence["text"] = "想一想……{@w}"
    sentence["hold"] = 1.2
    assert codes(insight) == []
    sentence["hold"] = 0.1
    assert codes(insight) == ["SS485"]


def test_pause_hold_range(insight):
    pause = next(b for b in insight["beats"] if b["id"] == "Predict")["pause"]
    pause["hold"] = 3
    assert codes(insight) == []
    pause["hold"] = 0.2
    assert codes(insight) == ["SS486"]
    pause["hold"] = 0.5
    assert codes(insight) == []
    insight["beats"].append({"id": "Break", "pause": {"type": "segment", "hold": 0}})
    assert codes(insight) == []
    insight["beats"][-1]["pause"]["hold"] = 12
    assert codes(insight) == ["SS486"]


def test_measured_gap_must_follow_punctuation(insight):
    say = insight["beats"][0]["say"]
    say.append({"id": "s2", "pace": "brisk", "text": "再看一眼。"})
    # 第一句原文以问号结尾，默认间隙 0.60
    good = {"beats": {"Hook": {"cues": [
        {"id": "s1", "start": 0.3, "end": 1.0},
        {"id": "s2", "start": 1.6, "end": 2.4},
    ]}}}
    assert "SS487" not in codes(insight, timing=good)
    bad = {"beats": {"Hook": {"cues": [
        {"start": 0.3, "end": 1.0},
        {"start": 1.2, "end": 2.4},
    ]}}}
    report = check(insight, timing=bad)
    assert report.codes() == ["SS487"]
    assert "0.600" in report.errors[0].message
    say[0]["hold"] = 0.5
    held = {"beats": {"Hook": {"cues": [
        {"start": 0.3, "end": 1.0},
        {"start": 1.5, "end": 2.4},
    ]}}}
    assert codes(insight, timing=held) == []


def test_cue_late_is_an_error_past_tolerance(insight):
    late = {"beats": {"Rearrange": {"actions": [{"at": 0, "want": 2.0, "start": 2.5}]}}}
    report = check(insight, timing=late)
    assert report.codes() == ["SS480"]
    assert "0.50" in report.errors[0].message
    close = {"beats": {"Rearrange": {"actions": [{"at": 0, "want": 2.0, "start": 2.3}]}}}
    assert codes(insight, timing=close) == []
    early = {"beats": {"Rearrange": {"actions": [{"at": 0, "want": 0.4, "start": 1.4}]}}}
    assert codes(insight, timing=early) == []
    insight["style"] = {"quality": {"cue_late": 0.2}}
    assert codes(insight, timing=close) == ["SS480"]


def test_allow_late_and_episode_waiver(insight):
    late = {"beats": {"Rearrange": {"actions": [{"at": 0, "want": 2.0, "start": 3.0}]}}}
    action = next(b for b in insight["beats"] if b["id"] == "Rearrange")["do"][0]
    action["allow_late"] = True
    assert codes(insight, timing=late) == []
    del action["allow_late"]
    waiver = [{"name": "one episode", "ids": ["ep21"], "codes": ["SS480"]}]
    assert codes(insight, timing=late, allowlist=waiver) == []
    assert check_timing(insight, late).codes() == ["SS480"]


def test_timing_report_shape(insight):
    assert check(insight, timing={"cues": []}).codes() == ["SS481"]
    assert check(insight, timing={"beats": {"Nope": {}}}).codes() == ["SS481"]
    short = {"beats": {"Hook": {"cues": []}}}
    assert "SS481" in codes(insight, timing=short)
    # Hook 只有一句，一份对得上的 cues 不报句间问题
    one = {"beats": {"Hook": {"cues": [{"start": 0.3, "end": 1.2}]}}}
    assert codes(insight, timing=one) == []


def test_nonfinite_timing_is_malformed_not_a_bypass(insight):
    nan = float("nan")
    inf = float("inf")
    late_nan = {"beats": {"Rearrange": {"actions": [{"at": 0, "want": nan, "start": 2.5}]}}}
    assert codes(insight, timing=late_nan) == ["SS481"]
    late_inf = {"beats": {"Rearrange": {"actions": [{"at": 0, "want": inf, "start": 2.5}]}}}
    assert codes(insight, timing=late_inf) == ["SS481"]
    start_inf = {"beats": {"Rearrange": {"actions": [{"at": "s1@d0", "want": 2.0, "start": inf}]}}}
    assert codes(insight, timing=start_inf) == ["SS481"]
    bad_at = {"beats": {"Rearrange": {"actions": [{"at": {}, "want": 2.0, "start": 3.0}]}}}
    assert codes(insight, timing=bad_at) == ["SS481"]
    mixed = {"beats": {"Rearrange": {"actions": [
        {"at": {}, "want": 2.0, "start": 3.0},
        {"at": 0, "want": 2.0, "start": 2.5},
    ]}}}
    assert codes(insight, timing=mixed) == ["SS481", "SS480"]
    assert codes(insight, timing={"beats": {"Rearrange": {"actions": [
        {"at": 0, "want": 2.0, "start": 2.5},
        {"at": "s1@d0+0.5", "want": 2.0, "start": 2.2},
    ]}}}) == ["SS480"]

    say = insight["beats"][0]["say"]
    say.append({"id": "s2", "pace": "normal", "text": "再看一眼。"})
    gap = {"beats": {"Hook": {"cues": [
        {"start": 0.3, "end": inf},
        {"start": inf, "end": inf},
    ]}}}
    assert codes(insight, timing=gap) == ["SS481"]


def _plate(doc, **fields):
    doc["objects"]["plate"] = {
        "type": "clip", "src": "hook.mp4", "kind": "video", "content_kind": "plate", "in": "side",
        **fields,
    }
    hook = next(b for b in doc["beats"] if b["id"] == "Hook")
    hook["do"].insert(0, {"at": "s1", "act": "show", "target": "plate"})


def _plant(doc, field, value):
    """把这一 PR 会读到的某个数写成 value。"""
    if field == "say.hold":
        doc["beats"][0]["say"][0]["hold"] = value
    elif field == "pause.hold":
        next(b for b in doc["beats"] if b["id"] == "Predict")["pause"]["hold"] = value
    elif field == "speed":
        doc["style"] = {"voice": {"speed": value}}
    elif field == "speed-waived":
        doc["meta"]["series"] = "week-1-competition"
        doc["style"] = {"voice": {"speed": value}}
    elif field == "cue_late":
        doc["style"] = {"quality": {"cue_late": value}}
    elif field == "cue_late_skip_before":
        doc["style"] = {"quality": {"cue_late_skip_before": value}}
    elif field == "fps":
        _plate(doc, kind="frames", src="frames", fps=value)
    elif field == "trim.in":
        _plate(doc, trim={"in": value})
    elif field == "trim.out":
        _plate(doc, trim={"in": 0, "out": value})
    elif field == "rate":
        _plate(doc, rate=value)
    elif field == "clip.start":
        _plate(doc, start=value)
    elif field == "opacity":
        _plate(doc, opacity=value)
    elif field == "z":
        _plate(doc, z=value)
    elif field == "size.max_width":
        _plate(doc, size={"max_width": value, "max_height": 0.4})
    elif field == "size.max_height":
        _plate(doc, size={"max_width": 0.4, "max_height": value})
    elif field == "cue.start":
        return {"beats": {"Hook": {"cues": [{"start": value, "end": 1.2}]}}}
    elif field == "cue.end":
        return {"beats": {"Hook": {"cues": [{"start": 0.3, "end": value}]}}}
    elif field == "action.want":
        return {"beats": {"Rearrange": {"actions": [{"at": 0, "want": value, "start": 2.5}]}}}
    elif field == "action.start":
        return {"beats": {"Rearrange": {"actions": [{"at": 0, "want": 2.0, "start": value}]}}}
    else:
        raise AssertionError(field)
    return None


# 这一 PR 读到的每一个数：NaN，以及结构层上下界接不住的 Infinity。
# forbid 是不该被这个坏值关掉或误开的门槛。
_NONFINITE = [
    ("say.hold", NAN, "SS485", (), None),
    ("say.hold", INF, "SS100", (), None),
    ("say.hold", NINF, "SS100", (), None),
    ("pause.hold", NAN, "SS486", (), None),
    ("pause.hold", INF, "SS486", (), None),
    ("pause.hold", NINF, "SS100", (), None),
    ("speed", NAN, "SS482", (), None),
    ("speed", INF, "SS100", (), None),
    ("speed", NINF, "SS100", (), None),
    ("speed-waived", NAN, "SS482", (), None),
    ("cue_late", NAN, "SS100", ("SS480",), {"beats": {"Rearrange": {"actions": [{"at": 0, "want": 2.0, "start": 2.3}]}}}),
    ("cue_late", INF, "SS100", (), None),
    ("cue_late", NINF, "SS100", (), None),
    ("cue_late_skip_before", NAN, "SS100", ("SS480",), {"beats": {"Rearrange": {"actions": [{"at": 0, "want": 0.4, "start": 2.0}]}}}),
    ("cue_late_skip_before", INF, "SS100", (), None),
    ("cue_late_skip_before", NINF, "SS100", (), None),
    ("fps", NAN, "SS470", (), None),
    ("fps", INF, "SS100", (), None),
    ("trim.in", NAN, "SS473", (), None),
    ("trim.in", INF, "SS473", (), None),
    ("trim.out", NAN, "SS473", (), None),
    ("trim.out", INF, "SS473", (), None),
    ("rate", NAN, "SS100", (), None),
    ("rate", INF, "SS100", (), None),
    ("clip.start", NAN, "SS100", (), None),
    ("clip.start", INF, "SS100", (), None),
    ("opacity", NAN, "SS100", (), None),
    ("opacity", INF, "SS100", (), None),
    ("z", NAN, "SS100", (), None),
    ("z", INF, "SS100", (), None),
    ("z", NINF, "SS100", (), None),
    ("size.max_width", NAN, "SS100", (), None),
    ("size.max_width", INF, "SS100", (), None),
    ("size.max_height", NAN, "SS100", (), None),
    ("size.max_height", INF, "SS100", (), None),
    ("cue.start", NAN, "SS481", ("SS487",), None),
    ("cue.start", INF, "SS481", ("SS487",), None),
    ("cue.end", NAN, "SS481", ("SS487",), None),
    ("cue.end", INF, "SS481", ("SS487",), None),
    ("action.want", NAN, "SS481", ("SS480",), None),
    ("action.want", INF, "SS481", ("SS480",), None),
    ("action.want", NINF, "SS481", ("SS480",), None),
    ("action.start", NAN, "SS481", ("SS480",), None),
    ("action.start", INF, "SS481", ("SS480",), None),
    ("action.start", NINF, "SS481", ("SS480",), None),
]


@pytest.mark.parametrize("field,value,code,forbid,timing", _NONFINITE, ids=[f"{f}-{v}" for f, v, *_ in _NONFINITE])
def test_every_numeric_this_pr_reads_rejects_nonfinite(insight, field, value, code, forbid, timing):
    produced = _plant(insight, field, value)
    report = check(insight, timing=produced if produced is not None else timing)
    found = report.codes()
    assert code in found, (field, value, found)
    for extra in forbid:
        assert extra not in found, (field, value, found)


def test_nan_hold_does_not_silence_a_long_gap(insight):
    say = insight["beats"][0]["say"]
    say[0]["hold"] = NAN
    say.append({"id": "s2", "pace": "normal", "text": "再看一眼。"})
    next(b for b in insight["beats"] if b["id"] == "Predict")["pause"]["hold"] = NAN
    timing = {"beats": {"Hook": {"cues": [
        {"start": 0.3, "end": 1.0},
        {"start": 10.0, "end": 11.0},
    ]}}}
    report = check(insight, timing=timing)
    assert set(report.codes()) >= {"SS485", "SS486", "SS487"}
    gap = next(i for i in report.errors if i.code == "SS487")
    assert "9.000" in gap.message and "0.600" in gap.message
    assert "nan" not in gap.message
