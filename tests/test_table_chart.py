"""seq_table、line_chart 的参数和动作检查；chips 的 reveal。"""

import copy

from scene_spec import check

BASE = {
    "spec": "0.1",
    "meta": {"id": "t", "title": "t", "line": "contest", "author": "t", "license": "CC-BY-4.0"},
    "pedagogy": {"insight": "t", "status": "method"},
    "style": {"theme": "paper"},
    "objects": {
        "plan": {"widget": "chips", "in": "footer", "reveal": True, "items": ["a", "b"]},
        "table": {"widget": "seq_table", "in": "stage",
                  "rows": [{"label": "$a$", "values": [1, 2, 3]}, {"label": "$b$", "values": [4, 5, 6], "role": "HL"}]},
        "chart": {"widget": "line_chart", "below": "table", "x": [1, 2, 3],
                  "series": [{"name": "b", "values": [1, 2, 3]}, {"values": [3, 2, 1], "role": "A"}]},
    },
    "beats": [{
        "id": "One",
        "say": [{"id": "s1", "pace": "normal", "text": "看。"}],
        "do": [
            {"at": "s1", "act": "show", "target": "plan"},
            {"after": "prev", "act": "focus", "target": "plan[1]"},
            {"after": "prev", "act": "reveal", "target": "plan", "args": {"index": "0:2"}},
            {"after": "prev", "act": "show", "target": "table"},
            {"after": "prev", "act": "show", "target": "table[1:3]"},
            {"after": "prev", "act": "focus", "target": "table.row[1]"},
            {"after": "prev", "act": "shade", "target": "table", "args": {"row": 1, "col": 2}},
            {"after": "prev", "act": "show", "target": "chart"},
            {"after": "prev", "act": "show", "target": "chart.series[1]"},
            {"after": "prev", "act": "ring", "target": "chart", "args": {"series": 1, "index": 2}},
        ],
    }],
}


def codes(doc):
    return check(doc).codes()


def test_base_passes():
    assert codes(copy.deepcopy(BASE)) == []


def test_table_column_out_of_range():
    d = copy.deepcopy(BASE)
    d["beats"][0]["do"][4]["target"] = "table[3]"
    assert codes(d) != []


def test_table_rows_must_match():
    d = copy.deepcopy(BASE)
    d["objects"]["table"]["rows"][1]["values"] = [4, 5]
    assert "SS250" in codes(d)


def test_table_shade_bounds():
    d = copy.deepcopy(BASE)
    d["beats"][0]["do"][6]["args"] = {"row": 2, "col": 0}
    assert "SS234" in codes(d)


def test_chart_series_length_and_ring():
    d = copy.deepcopy(BASE)
    d["objects"]["chart"]["series"][0]["values"] = [1, 2]
    assert "SS250" in codes(d)
    d = copy.deepcopy(BASE)
    d["beats"][0]["do"][9]["args"] = {"series": 2, "index": 0}
    assert "SS234" in codes(d)


def test_chips_reveal_without_flag_warns():
    d = copy.deepcopy(BASE)
    del d["objects"]["plan"]["reveal"]
    report = check(d)
    assert not report.errors and any(w.code == "SS235" for w in report.warnings)
