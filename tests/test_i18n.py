"""英文版：每句的 en 带书签，i18n.en 覆盖画面上的字；localize 出一份普通的英文场景。"""

import copy
from pathlib import Path

import pytest

from scene_spec import LocalizeError, check, localize
from scene_spec.loader import load_file

ROOT = Path(__file__).resolve().parents[1]
EP21 = ROOT / "examples" / "ep21-pythagoras.scene.yaml"


@pytest.fixture
def ep21() -> dict:
    return copy.deepcopy(load_file(EP21))


def say(doc, beat: str, sid: str) -> dict:
    return next(s for s in next(b for b in doc["beats"] if b["id"] == beat)["say"] if s["id"] == sid)


def test_ep21_english_is_clean(ep21):
    assert check(ep21).issues == []


def test_localize_swaps_lines_and_overlays(ep21):
    en = localize(ep21, "en")
    assert "i18n" not in en and en["style"]["lang"] == "en"
    assert say(en, "Square", "s2")["text"].endswith("{@t2}three, {@t3}four.")
    assert "en" not in say(en, "Square", "s2")
    assert en["objects"]["practice"]["lines"][0] == "[Try it]{.HL}"
    assert en["objects"]["practice"]["widget"] == "think_box"  # 深合并：没覆盖的键还在
    assert en["beats"][0]["pause"]["hold"] == 3 and en["beats"][0]["pause"]["prompt"].startswith("The ladder")
    assert en["meta"]["title"].startswith("The Pythagorean") and en["meta"]["id"] == "ep21"


def test_source_language_only_drops_i18n(ep21):
    zh = localize(ep21, "zh")
    assert "i18n" not in zh and say(zh, "Hook", "s1")["text"].startswith("{@tri}师傅")
    assert "lang" not in zh["style"]


def test_missing_bookmark_is_an_error(ep21):
    s = say(ep21, "Square", "s2")
    s["en"] = s["en"].replace("{@t3}", "")
    report = check(ep21)
    assert "SS503" in report.codes()


def test_reordered_bookmarks_warn(ep21):
    s = say(ep21, "Setup", "s1")
    s["en"] = "In this triangle, {@b}side b is three and {@a}side a is two."
    assert "SS504" in check(ep21).codes()


def test_chinese_left_on_screen_warns(ep21):
    del ep21["i18n"]["en"]["objects"]["practice"]
    issues = [i for i in check(ep21).issues if i.code == "SS507"]
    assert issues and issues[0].path.startswith("objects.practice.lines")


def test_unknown_overlay_target_is_an_error(ep21):
    ep21["i18n"]["en"]["objects"]["nope"] = {"text": "x"}
    assert "SS506" in check(ep21).codes()
    with pytest.raises(LocalizeError):
        localize(ep21, "en")


def test_say_cannot_be_overridden(ep21):
    ep21["i18n"]["en"]["beats"]["Hook"]["say"] = []
    with pytest.raises(LocalizeError):
        localize(ep21, "en")


def test_english_without_en_lines_fails():
    doc = copy.deepcopy(load_file(ROOT / "examples" / "s67-p01.scene.yaml"))
    with pytest.raises(LocalizeError):
        localize(doc, "en")


def test_action_args_can_be_patched_by_index(ep21):
    ep21["beats"][1]["do"][0]["args"] = {"label": "徒弟"}  # Myth: show wrong
    assert "SS507" in check(ep21).codes()
    ep21["i18n"]["en"]["beats"]["Myth"] = {"do": {0: {"args": {"label": "apprentice"}}}}
    en = localize(ep21, "en")
    assert en["beats"][1]["do"][0] == {"at": "s1@w", "act": "show", "target": "wrong", "args": {"label": "apprentice"}}
    ep21["i18n"]["en"]["beats"]["Myth"] = {"do": {0: {"target": "one"}}}
    with pytest.raises(LocalizeError):
        localize(ep21, "en")


def english_first() -> dict:
    """直接用英文写的场景：style.lang: en，句子只有 text。"""
    doc = copy.deepcopy(load_file(ROOT / "examples" / "s67-p01.scene.yaml"))
    doc.setdefault("style", {})["lang"] = "en"
    for beat in doc["beats"]:
        for s in beat.get("say", []):
            s.pop("en", None)
    return doc


def test_english_first_file_localizes_to_itself():
    doc = english_first()
    en = localize(doc, "en")
    assert en["beats"] == doc["beats"] and en["style"]["lang"] == "en"


def test_english_first_file_has_no_chinese_version():
    with pytest.raises(LocalizeError):
        localize(english_first(), "zh")


def test_english_first_file_rejects_i18n_en():
    doc = english_first()
    doc["i18n"] = {"en": {}}
    assert "SS501" in check(doc).codes()
