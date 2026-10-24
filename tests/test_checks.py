"""结构与语义检查的单项用例。每个用例从一份能通过的文档出发，只改一处。"""

from scene_spec import check
from scene_spec.textmarks import parse_object_text, parse_say_text


def codes(doc) -> list[str]:
    return check(doc).codes()


def beat(doc, beat_id):
    return next(b for b in doc["beats"] if b["id"] == beat_id)


# ---------- 结构层 ----------

def test_missing_meta_is_structural(example):
    del example["meta"]
    assert codes(example) == ["SS100"]


def test_action_needs_exactly_one_time_key(example):
    beat(example, "Down")["do"][0]["after"] = "prev"
    report = check(example)
    assert report.codes() == ["SS100"]
    assert "at、after、with" in report.errors[0].message


def test_unknown_role_is_structural(example):
    example["objects"]["title"]["role"] = "RED"
    assert codes(example) == ["SS100"]


def test_semantic_layer_skipped_when_structure_fails(example):
    example["spec"] = "0.2"
    example["objects"]["title"]["role"] = "#ff0000"  # 结构不过就不会再报 SS350
    assert set(codes(example)) == {"SS100"}


# ---------- 引用 ----------

def test_unknown_object(example):
    beat(example, "Down")["do"][1]["target"] = "tabel"
    assert codes(example) == ["SS310"]


def test_unknown_span(example):
    beat(example, "Problem")["do"][2]["target"] = "card#b_deff"
    report = check(example)
    assert report.codes() == ["SS311"]
    assert "#b_def" in report.errors[0].message  # 列出现有片段


def test_part_index_out_of_range(example):
    beat(example, "Down")["do"][7]["target"] = "table.C[0:7]"
    assert codes(example) == ["SS312"]


def test_unknown_part(example):
    beat(example, "Down")["do"][7]["target"] = "table.D[0]"
    assert codes(example) == ["SS312"]


def test_item_index_out_of_range(example):
    beat(example, "Translate")["do"][4]["target"] = "plan[3]"
    assert codes(example) == ["SS313"]


def test_layout_reference_must_exist(example):
    example["objects"]["sum_b"]["below"] = "f_x"
    assert codes(example) == ["SS310"]


def test_layout_self_reference(example):
    example["objects"]["sum_b"]["below"] = "sum_b"
    assert "SS341" in codes(example)


# ---------- 时间点 ----------

def test_unknown_sentence(example):
    beat(example, "Down")["do"][0]["at"] = "s9"
    assert codes(example) == ["SS320"]


def test_sentence_index_out_of_range(example):
    beat(example, "Down")["do"][0]["at"] = 4
    assert codes(example) == ["SS320"]


def test_unknown_bookmark(example):
    beat(example, "Down")["do"][2]["at"] = "s1@d9"
    report = check(example)
    assert report.codes() == ["SS321"]
    assert "@d0" in report.errors[0].message


def test_offset_time_is_accepted(example):
    beat(example, "Down")["do"][0]["at"] = "s1+0.5"
    assert codes(example) == []


def test_prev_on_first_action(example):
    first = beat(example, "Down")["do"][0]
    del first["at"]
    first["with"] = "prev"
    assert codes(example) == ["SS322"]


def test_beat_without_narration_only_allows_at_zero(insight):
    beat(insight, "Predict")["do"] = [{"at": "s1", "act": "hold", "dur": 1}]
    assert codes(insight) == ["SS320"]


# ---------- 动作 ----------

def test_unknown_action(example):
    beat(example, "Down")["do"][2]["act"] = "explode"
    assert codes(example) == ["SS330"]


def test_widget_action_on_wrong_widget(example):
    beat(example, "Down")["do"][2]["target"] = "plan"
    assert codes(example) == ["SS330"]


def test_widget_action_needs_whole_widget(example):
    beat(example, "Down")["do"][2]["target"] = "table.B[0]"
    assert codes(example) == ["SS333"]


def test_diff_table_unknown_row(example):
    beat(example, "Down")["do"][2]["args"]["row"] = "D"
    assert codes(example) == ["SS231"]


def test_diff_table_cannot_derive_first_row(example):
    beat(example, "Down")["do"][2]["args"]["row"] = "A"
    assert codes(example) == ["SS232"]


def test_diff_table_index_out_of_range(example):
    beat(example, "Down")["do"][2]["args"]["index"] = "0:8"
    assert codes(example) == ["SS234"]


def test_transform_needs_from_and_to(example):
    del beat(example, "GeneralTerm")["do"][9]["to"]
    assert codes(example) == ["SS331", "SS381"]  # sum_b 随之变成未引用的对象


def test_target_required_for_show(example):
    del beat(example, "Opening")["do"][0]["target"]
    assert codes(example) == ["SS331"]


def test_hold_needs_dur(example):
    del beat(example, "GeneralTerm")["do"][10]["dur"]
    assert codes(example) == ["SS331"]


# ---------- 组件与数据 ----------

def test_diff_table_data_must_be_consistent(example):
    example["data"]["B"][2] = 11  # 既不是 A 的差，也让 C 不再是 B 的差
    report = check(example)
    assert report.codes() == ["SS223", "SS223"]
    assert "B[2] = 11" in report.errors[0].message
    assert "C[1] = 4" in report.errors[1].message


def test_diff_table_unknown_data(example):
    example["objects"]["table"]["rows"][2]["data"] = "Z"
    assert "SS220" in codes(example)


def test_widget_missing_param(example):
    del example["objects"]["plan"]["items"]
    assert "SS201" in codes(example)


def test_widget_unknown_param(example):
    example["objects"]["plan"]["colour"] = "gold"
    assert codes(example) == ["SS203"]


def test_empty_plane_warns(example):
    example["objects"]["empty_plane"] = {
        "widget": "plane", "x": [-2, 2], "y": [-2, 2],
    }
    beat(example, "Opening")["do"].append(
        {"at": 0, "act": "show", "target": "empty_plane"}
    )
    assert "SS384" in codes(example)


def test_plane_axes_can_be_turned_off(example):
    example["objects"]["venn"] = {
        "widget": "plane", "x": [-2, 2], "y": [-2, 2], "grid": False, "axes": False,
    }
    beat(example, "Opening")["do"].append(
        {"at": 0, "act": "shape", "target": "venn", "args": {"name": "A", "points": [[0, 0], [1, 0], [1, 1]]}}
    )
    assert check(example).ok
    assert not [c for c in codes(example) if c.startswith("SS2")]


def test_empty_plane_can_be_explicit_background(example):
    example["objects"]["empty_plane"] = {
        "widget": "plane", "x": [-2, 2], "y": [-2, 2], "allow_empty": True,
    }
    beat(example, "Opening")["do"].append(
        {"at": 0, "act": "show", "target": "empty_plane"}
    )
    assert "SS384" not in codes(example)


def test_unregistered_widget_is_only_a_warning(example):
    example["objects"]["plan"]["widget"] = "fancy_chips"
    report = check(example)
    assert report.ok
    assert report.codes() == ["SS370"]
    assert report.stats["unregistered_widgets"] == 1


# ---------- 禁止项 ----------

def test_color_literal_rejected(example):
    beat(example, "Down")["do"][2]["args"]["tint"] = "#B5843A"
    assert "SS350" in codes(example)


def test_expression_rejected(example):
    example["objects"]["answer"]["tex"] = "${A[7]}"
    assert codes(example) == ["SS351"]


def test_absolute_coords_warn_on_worked_line(example):
    example["objects"]["answer"]["at"] = [1.0, 2.0]
    report = check(example)
    assert report.ok
    assert report.codes() == ["SS342"]
    assert report.stats["absolute_coords"] == 1


def test_absolute_coords_rejected_on_insight_line(insight):
    insight["objects"]["law"]["at"] = [1.0, 2.0]
    report = check(insight)
    assert not report.ok
    assert report.codes() == ["SS342"]


def test_allow_layout_exceptions(example):
    example["objects"]["answer"]["allow"] = {"cross": True, "overlap": ["table"], "small": True, "clip": True}
    example["objects"]["table"]["allow"] = {"cross": ["answer"]}  # 组件对象也可以写
    assert codes(example) == []


def test_allow_unknown_target_rejected(example):
    example["objects"]["answer"]["allow"] = {"cross": ["nope"]}
    assert codes(example) == ["SS343"]


def test_allow_bad_shape_is_structural(example):
    example["objects"]["answer"]["allow"] = {"small": False}
    assert "SS100" in codes(example)


# ---------- 教学信息 ----------

def test_insight_requires_full_card(insight):
    del insight["pedagogy"]["non_example"]
    assert set(codes(insight)) == {"SS360", "SS363"}


def test_insight_requires_episode(insight):
    insight["meta"]["episode"] = None
    assert codes(insight) == ["SS360"]


def test_insight_requires_predict_pause(insight):
    insight["beats"] = [b for b in insight["beats"] if b["id"] != "Predict"]
    assert codes(insight) == ["SS365"]


def test_non_example_must_be_shown(insight):
    del beat(insight, "NonExample")["shows"]
    assert codes(insight) == ["SS362"]


def test_landing_beat_must_be_marked(example):
    del beat(example, "GeneralTerm")["shows"]
    assert codes(example) == ["SS362"]


def test_demo_needs_disclaimer(insight):
    insight["pedagogy"]["status"] = "demo"
    assert codes(insight) == ["SS364"]
    beat(insight, "Landing")["say"][0]["text"] = "这只是演示，不是证明。"
    assert codes(insight) == []


def test_duplicate_beat_id(example):
    beat(example, "Up")["id"] = "Down"
    assert "SS301" in codes(example)


# ---------- 文字标注 ----------

def test_spans_and_math_brackets():
    parsed = parse_object_text("区间 $[2,4)$ 和 [$x$]{#x .A}，字面 \\[注\\]")
    assert parsed.problems == []
    assert [(s.id, s.classes) for s in parsed.spans] == [("x", ["A"])]


def test_unescaped_bracket_in_text():
    parsed = parse_object_text("见 [1] 号题")
    assert parsed.problems and "\\[" in parsed.problems[0]


def test_unknown_span_class():
    parsed = parse_object_text("[x]{.red}")
    assert parsed.problems


def test_bookmarks_and_stray_braces():
    names, problems = parse_say_text("先{@a}五减二，$\\{x\\}$ 不算，{b} 不行")
    assert names == ["a"]
    assert len(problems) == 1


def test_bad_text_in_object_is_reported(example):
    example["objects"]["title"]["text"] = "高阶 [等差 数列"
    assert codes(example) == ["SS210"]


def test_bad_say_text_is_reported(example):
    beat(example, "Down")["say"][0]["text"] = "先往下做差{d0}"
    assert codes(example) == ["SS303", "SS321"]


def test_number_line_unit_must_be_positive(example):
    example["objects"]["axis"] = {"widget": "number_line", "range": [0, 1], "unit": 9, "in": "stage"}
    assert "SS202" not in codes(example)
    example["objects"]["axis"]["unit"] = 0
    assert "SS202" in codes(example)


def test_area_grid_actions(example):
    example["objects"]["sq"] = {"widget": "area_grid", "cols": 4, "rows": 3, "in": "stage"}
    do = beat(example, "Down")["do"]
    do.append({"after": "prev", "act": "cut", "target": "sq", "args": {"axis": "cols"}})
    do.append({"after": "prev", "act": "shade", "target": "sq", "args": {"cols": 3, "role": "A"}})
    do.append({"after": "prev", "act": "overlap", "target": "sq"})
    assert not [c for c in codes(example) if c.startswith("SS28")]
    do.append({"after": "prev", "act": "shade", "target": "sq", "args": {"rows": 5}})
    assert "SS281" in codes(example)
