"""受限 YAML（设计稿 §2）。"""

import pytest

from scene_spec.loader import SpecLoadError, load_text


def codes(text: str) -> list[str]:
    with pytest.raises(SpecLoadError) as info:
        load_text(text)
    return info.value.report.codes()


def test_plain_values():
    doc = load_text("a: true\nb: 3\nc: 1.5\nd: null\ne: hello\n")
    assert doc == {"a": True, "b": 3, "c": 1.5, "d": None, "e": "hello"}


@pytest.mark.parametrize("word", ["yes", "no", "on", "off", "Yes", "NO", "True", "FALSE"])
def test_yaml11_booleans_stay_strings(word):
    assert load_text(f"x: {word}\n") == {"x": word}


@pytest.mark.parametrize("value", ["16:9", "1:20:30", "0o17", "0x1F", "012", "2026-10-16", "1_000", ".5", "+1"])
def test_non_decimal_numbers_and_dates_stay_strings(value):
    assert load_text(f"x: {value}\n") == {"x": value}


def test_anchor_and_alias_rejected():
    assert codes("a: &base {x: 1}\nb: *base\n") == ["SS001", "SS001"]


def test_custom_tag_rejected():
    assert codes("a: !python/object x\n") == ["SS002"]


def test_merge_key_rejected():
    assert "SS003" in codes("a:\n  <<: {x: 1}\n  y: 2\n")


def test_duplicate_key_rejected():
    with pytest.raises(SpecLoadError) as info:
        load_text("a: 1\na: 2\n")
    assert "重复的键" in info.value.report.errors[0].message


def test_latex_in_double_quotes_gets_a_hint():
    with pytest.raises(SpecLoadError) as info:
        load_text('t: "$\\{A_n\\}$"\n')
    assert "单引号" in info.value.report.errors[0].message


def test_latex_in_single_quotes_is_fine():
    assert load_text("t: '$\\{A_n\\}$'\n") == {"t": "$\\{A_n\\}$"}
