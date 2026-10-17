"""场景参数、tween 动作、readout 对象和参数表达式的检查（SS400–SS419）。"""

import pytest
from conftest import minimal_insight

from scene_spec import check, expr


def param_doc() -> dict:
    doc = minimal_insight()
    doc["params"] = {"k": {"value": 1, "min": -3, "max": 3}, "t": 0}
    doc["objects"]["g"] = {
        "widget": "graph", "x": [-2, 4], "y": [-3, 5], "in": "stage",
        "plots": [{"f": "kx+1", "label": "y=kx+1"}],
        "points": [{"x": "t", "label": "P"}],
        "triangles": [{"point": 0, "run": 1}],
        "lines": [{"through": [0, 1], "slope": "k"}],
    }
    doc["objects"]["kval"] = {"type": "readout", "label": "$k$ =", "value": "k", "digits": 1, "in": "side"}
    doc["beats"][2]["do"] = [
        {"at": 0, "act": "show", "target": "g"},
        {"with": "prev", "act": "show", "target": "kval"},
        {"after": "prev", "act": "tween", "args": {"k": 2, "t": 1.5}, "ease": "linear", "dur": 2},
    ]
    return doc


def codes(doc):
    return check(doc).codes()


def test_valid_param_doc_passes():
    report = check(param_doc())
    assert report.ok, report.errors
    assert "SS409" not in report.codes()


def test_expression_parser_knows_params():
    tree = expr.parse("2kx+b", {"k", "b"})
    assert expr.evaluate(tree, 3, {"k": 0.5, "b": 1}) == 4.0
    assert expr.free_names(tree) == {"k", "b"}
    with pytest.raises(expr.UnknownName):
        expr.parse("kx+b", {"k"})
    with pytest.raises(expr.ExprError):
        expr.parse("t+x", {"t"}, allow_x=False)
    # 没给参数名时和以前一样：只认 x
    with pytest.raises(expr.ExprError):
        expr.parse("kx")


@pytest.mark.parametrize("params,code", [
    ({"x": 1}, "SS400"), ({"pi": 1}, "SS400"), ({"k": {"value": 1, "min": 2, "max": 0}}, "SS400"),
    ({"k": {"value": 5, "max": 3}}, "SS400"),
])
def test_bad_declarations(params, code):
    doc = param_doc()
    doc["params"].update(params)
    assert code in codes(doc)


def test_schema_rejects_bad_param_shapes():
    doc = param_doc()
    doc["params"]["k"] = "1"
    assert "SS100" in codes(doc)
    doc = param_doc()
    doc["params"]["2k"] = 1
    assert "SS100" in codes(doc)


@pytest.mark.parametrize("field,value,code", [
    ("value", "k +", "SS401"), ("value", "q", "SS402"), ("value", "k*x", "SS403"),
])
def test_readout_expressions(field, value, code):
    doc = param_doc()
    doc["objects"]["kval"][field] = value
    assert code in codes(doc)


def test_graph_expressions():
    doc = param_doc()
    doc["objects"]["g"]["plots"][0]["f"] = "kx+c"
    assert "SS402" in codes(doc)
    doc = param_doc()
    doc["objects"]["g"]["points"][0]["x"] = "t+x"
    assert "SS403" in codes(doc)
    doc = param_doc()
    doc["objects"]["g"]["lines"][0]["slope"] = "k*"
    assert "SS202" in codes(doc)  # 语法错在参数检查这一层就拦下


@pytest.mark.parametrize("action,code", [
    ({"at": 0, "act": "tween"}, "SS404"),
    ({"at": 0, "act": "tween", "args": {"k": 1}, "target": "g"}, "SS404"),
    ({"at": 0, "act": "tween", "args": {"m": 1}}, "SS405"),
    ({"at": 0, "act": "tween", "args": {"k": "2"}}, "SS406"),
    ({"at": 0, "act": "tween", "args": {"k": True}}, "SS406"),
    ({"at": 0, "act": "tween", "args": {"k": 9}}, "SS407"),
    ({"at": 0, "act": "show", "target": "g", "ease": "linear"}, "SS408"),
])
def test_tween_errors(action, code):
    doc = param_doc()
    doc["beats"][2]["do"].append(action)
    assert code in codes(doc)


def test_unknown_ease_is_structural():
    doc = param_doc()
    doc["beats"][2]["do"][2]["ease"] = "bounce"
    assert "SS100" in codes(doc)


def test_unused_param_warns():
    doc = param_doc()
    doc["params"]["m"] = 2
    report = check(doc)
    assert report.ok and "SS409" in report.codes()


def test_readout_shape():
    doc = param_doc()
    del doc["objects"]["kval"]["value"]
    assert "SS410" in codes(doc)
    doc = param_doc()
    doc["objects"]["kval"]["format"] = "fraction"
    assert "SS410" in codes(doc)  # 和 digits 冲突
    doc = param_doc()
    doc["objects"]["wrong"]["digits"] = 2
    assert "SS410" in codes(doc)


def test_states_catch_out_of_range_geometry():
    doc = param_doc()
    doc["beats"][2]["do"][2]["args"] = {"t": 3.5}  # 三角形另一端到 x=4.5，出了 [-2, 4]
    assert "SS411" in codes(doc)
    doc = param_doc()
    doc["beats"][2]["do"][2]["args"] = {"t": 5}  # 点本身出界
    assert "SS411" in codes(doc)
    doc = param_doc()
    doc["objects"]["kval"]["value"] = "1/k"
    doc["beats"][2]["do"][2]["args"] = {"k": 0}
    assert "SS411" in codes(doc)


def test_states_only_count_while_visible():
    """截距读数 -b/k 在 k=0 时没有定义；但 k 补间到 0 时读数不在画面上，就不报。"""
    doc = param_doc()
    doc["params"]["b"] = 1
    doc["objects"]["xint"] = {"type": "readout", "label": "交点", "value": "-b/k", "in": "side", "below": "kval"}
    doc["beats"][2]["do"] = [
        {"at": 0, "act": "show", "target": "g"},
        {"after": "prev", "act": "tween", "args": {"k": 0}},
        {"after": "prev", "act": "tween", "args": {"k": 2}},
        {"after": "prev", "act": "show", "target": "xint"},
        {"with": "prev", "act": "show", "target": "kval"},
        {"after": "prev", "act": "tween", "args": {"b": -1, "t": 1}},
    ]
    report = check(doc)
    assert report.ok, report.errors
    doc["beats"][2]["do"].append({"after": "prev", "act": "tween", "args": {"k": 0}})
    assert "SS411" in codes(doc)
