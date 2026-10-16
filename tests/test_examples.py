"""第一个测试用例：设计稿 §11.1 和据此写成的完整示例。"""

from conftest import EXAMPLE, FIXTURES

from scene_spec import check, check_file
from scene_spec.cli import main


def test_full_example_passes_without_warnings():
    report = check_file(EXAMPLE)
    assert report.issues == []
    assert report.stats["beats"] == 9
    assert report.stats["sentences"] == 37  # 与 p01/audio 实际合成的句数一致
    assert report.stats["absolute_coords"] == 0
    assert report.stats["unregistered_widgets"] == 0


def test_design_snippet_as_written_is_caught_by_loader():
    """设计稿里的写法有两个 YAML 问题：双引号里的 LaTeX 反斜杠、流式映射里没加引号的 plan[0]。"""
    report = check_file(FIXTURES / "design-11-1-as-written.scene.yaml")
    assert report.codes() == ["SS000"]
    assert "单引号" in report.errors[0].message


def test_design_snippet_reports_exactly_the_missing_parts():
    report = check_file(FIXTURES / "design-11-1.scene.yaml")
    assert sorted(report.codes()) == ["SS361", "SS362"]
    assert {i.path for i in report.errors} == {"pedagogy.landing", "pedagogy.misconception"}


def test_minimal_insight_passes(insight):
    assert check(insight).issues == []


def test_cli_exit_codes(capsys):
    assert main(["check", str(EXAMPLE)]) == 0
    assert main(["check", str(FIXTURES / "design-11-1.scene.yaml")]) == 1
    out = capsys.readouterr().out
    assert "SS361" in out and "通过" in out
