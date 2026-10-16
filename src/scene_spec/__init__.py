"""scene-spec：数学讲解视频的场景描述格式。

    from scene_spec import check_file
    report = check_file("examples/s67-p01.scene.yaml")
    report.ok, report.errors, report.warnings
"""

from __future__ import annotations

from pathlib import Path

from . import semantic, structure
from .loader import SpecLoadError, load_text
from .report import Issue, Report

__all__ = ["check", "check_file", "check_text", "Issue", "Report", "SPEC_VERSION"]
__version__ = "0.1.0"
SPEC_VERSION = "0.1"


def check(doc: object) -> Report:
    """对已经读成 Python 对象的文档做结构检查；通过后再做语义检查。"""
    report = Report()
    structure.check(doc, report)
    if report.ok:
        semantic.check(doc, report)
    return report


def check_text(text: str) -> Report:
    try:
        doc = load_text(text)
    except SpecLoadError as exc:
        return exc.report
    if isinstance(doc, dict) and doc.get("spec") not in (None, SPEC_VERSION):
        report = Report()
        report.error("SS010", "spec", f"本工具只认 scene-spec {SPEC_VERSION}，文件写的是 {doc.get('spec')!r}")
        return report
    return check(doc)


def check_file(path: str | Path) -> Report:
    return check_text(Path(path).read_text(encoding="utf-8"))
