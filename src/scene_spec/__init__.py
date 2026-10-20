"""scene-spec：数学讲解视频的场景描述格式。

    from scene_spec import check_file
    report = check_file("examples/s67-p01.scene.yaml")
    report.ok, report.errors, report.warnings
"""

from __future__ import annotations

from pathlib import Path

from . import i18n, semantic, structure
from .i18n import LocalizeError, localize, source_lang
from .loader import SpecLoadError, load_text
from .report import Issue, Report

__all__ = ["check", "check_file", "check_text", "localize", "source_lang", "Issue", "LocalizeError", "Report", "SPEC_VERSION"]
__version__ = "0.1.0"
SPEC_VERSION = "0.1"


def check(doc: object) -> Report:
    """对已经读成 Python 对象的文档做结构检查；通过后再做语义检查。

    写了 `i18n` 时，再查每种语言的译文（i18n.check），并把本地化后的文档也完整查一遍（问题前面标 [en]）。
    """
    report = Report()
    structure.check(doc, report)
    if report.ok:
        semantic.check(doc, report)
    if report.ok and isinstance(doc, dict) and doc.get("i18n"):
        i18n.check(doc, report)
        for lang in doc["i18n"]:
            try:
                local = localize(doc, lang)
            except LocalizeError:
                continue  # i18n.check 已经报过
            sub = Report()
            structure.check(local, sub)
            if sub.ok:
                semantic.check(local, sub)
            for issue in sub.issues:
                report.issues.append(Issue(issue.level, issue.code, f"[{lang}] {issue.path}", issue.message))
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
