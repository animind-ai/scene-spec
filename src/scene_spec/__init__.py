"""scene-spec：数学讲解视频的场景描述格式。

    from scene_spec import check_file
    report = check_file("examples/s67-p01.scene.yaml")
    report.ok, report.errors, report.warnings
"""

from __future__ import annotations

from pathlib import Path

from . import i18n, quality, semantic, structure
from .i18n import LocalizeError, localize
from .loader import SpecLoadError, load_text
from .pauses import silence_after
from .report import Issue, Report

__all__ = [
    "check", "check_file", "check_text", "check_timing", "localize", "silence_after",
    "Issue", "LocalizeError", "Report", "SPEC_VERSION",
]
__version__ = "0.2.0"
SPEC_VERSION = "0.1"


def check(doc: object, *, root: Path | None = None, timing: dict | None = None, allowlist=None) -> Report:
    """对已经读成 Python 对象的文档做结构检查；通过后再做语义检查。

    root：素材相对路径的根。check_file 用场景文件所在目录。不传则不查 clip 的 src 在不在。
    timing：kit/voice 的时间报告，见 check_timing。不传则不查画面是否晚于书签、句间静音是否按标点。
    allowlist：豁免条目；不传则读 schema/quality-allowlist.yaml。

    写了 `i18n` 时，再查每种语言的译文（i18n.check），并把本地化后的文档也完整查一遍（问题前面标 [en]）。
    时间报告只对原文查一次：它属于一种语言的成片。
    """
    report = Report()
    structure.check(doc, report)
    if report.ok:
        semantic.check(doc, report, root=root, timing=timing, allowlist=allowlist)
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
                semantic.check(local, sub, root=root, allowlist=allowlist)
            for issue in sub.issues:
                report.issues.append(Issue(issue.level, issue.code, f"[{lang}] {issue.path}", issue.message))
    return report


def check_text(text: str, *, root: Path | None = None, timing: dict | None = None, allowlist=None) -> Report:
    try:
        doc = load_text(text)
    except SpecLoadError as exc:
        return exc.report
    if isinstance(doc, dict) and doc.get("spec") not in (None, SPEC_VERSION):
        report = Report()
        report.error("SS010", "spec", f"本工具只认 scene-spec {SPEC_VERSION}，文件写的是 {doc.get('spec')!r}")
        return report
    return check(doc, root=root, timing=timing, allowlist=allowlist)


def check_file(path: str | Path, *, timing: dict | None = None, allowlist=None) -> Report:
    path = Path(path)
    return check_text(path.read_text(encoding="utf-8"), root=path.parent, timing=timing, allowlist=allowlist)


def check_timing(doc: dict, timing: dict, report: Report | None = None, *, allowlist=None) -> Report:
    """只消费时间报告，不重复跑结构检查。kit 排完画面、voice 拼完句间静音之后把报告喂进来。

    报告里有 actions 才查画面是否晚于书签（SS480），有 cues 才查句间静音（SS487）。
    """
    own = report if report is not None else Report()
    quality.check_timing(doc, timing, own, allowlist)
    return own
