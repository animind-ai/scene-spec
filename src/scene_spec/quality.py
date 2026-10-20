"""把原来的软提示收成硬门槛。

三件事：

- 画面晚于旁白书签（kit 渲染日志里的 `CUE LATE`）超过容差就是 SS480。
  时刻不在本仓库算：kit 把排期结果写成时间报告，`check_timing` 消费它。
- 句间静音按标点，不再是一个固定值；写了的 hold / pause.hold 要落在区间里。
- 发布内容的旁白必须是 Gemini TTS `google/gemini-3.8-flash-tts`、声音 `Kore`、语速 1.0。
  例外只在 `schema/quality-allowlist.yaml`，按 meta.id 或 meta.series 匹配。

钩子检查不在这里。迷思要被某个 beat 标注（SS362）、insight 要有 predict 暂停（SS365）
仍由 semantic.py 报。外部流水线的 HOOK_MYTH_BY_S 一类代码本模块不产生、也不吞掉。
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from importlib import resources
from pathlib import Path

import yaml

from . import pauses
from .report import Report

REQUIRED_MODEL = "google/gemini-3.8-flash-tts"
REQUIRED_VOICE = "Kore"
REQUIRED_SPEED = 1.0
# 和 kit 的 CUE_LATE 一致：晚于书签超过 0.4 秒，且书签本身在 0.5 秒之后。
DEFAULT_CUE_LATE = 0.4
DEFAULT_SKIP_BEFORE = 0.5

ALLOWLIST_NAME = "quality-allowlist.yaml"
# 和 schema 的 timeRef 同一条：非负整数，或 s1、s1@d0、s1+0.5。
_TIME_REF = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*|[0-9]+)(@[A-Za-z_][A-Za-z0-9_]*)?(\+[0-9]+(\.[0-9]+)?)?$"
)


@lru_cache(maxsize=1)
def allowlist() -> tuple[dict, ...]:
    """仓库里的 schema/ 优先，安装成包之后读包内副本。"""
    repo_copy = Path(__file__).resolve().parents[2] / "schema" / ALLOWLIST_NAME
    if repo_copy.exists():
        text = repo_copy.read_text(encoding="utf-8")
    else:
        text = resources.files("scene_spec").joinpath("schema", ALLOWLIST_NAME).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    entries = data.get("entries") or []
    return tuple(entries)


def waived(doc: dict, code: str, entries: tuple[dict, ...] | list[dict] | None = None) -> bool:
    meta = doc.get("meta") or {}
    episode = meta.get("id")
    series = meta.get("series")
    for entry in allowlist() if entries is None else entries:
        if code not in (entry.get("codes") or []):
            continue
        if episode and episode in (entry.get("ids") or []):
            return True
        if series and entry.get("series") and series == entry["series"]:
            return True
    return False


def check_voice(doc: dict, report: Report, entries=None) -> None:
    voice = (doc.get("style") or {}).get("voice") or {}
    model = voice.get("model", REQUIRED_MODEL)
    name = voice.get("voice", REQUIRED_VOICE)
    speed = voice.get("speed", REQUIRED_SPEED)
    # NaN 过得了结构层，豁免名单只放行另一种有限语速，不放行 NaN / Infinity。
    if _nonfinite(speed):
        report.error(
            "SS482", "style.voice",
            f"speed 应为有限的 {REQUIRED_SPEED:g}，收到 {speed!r}。例外名单不覆盖 NaN / Infinity",
        )
    problems = []
    if model != REQUIRED_MODEL:
        problems.append(f"model 应为 {REQUIRED_MODEL}，收到 {model!r}")
    if name != REQUIRED_VOICE:
        problems.append(f"voice 应为 {REQUIRED_VOICE}，收到 {name!r}")
    if not _nonfinite(speed) and not _speed_ok(speed):
        problems.append(f"speed 应为 {REQUIRED_SPEED:g}，收到 {speed!r}")
    if problems and not waived(doc, "SS482", entries):
        report.error("SS482", "style.voice", "；".join(problems) + "。例外只写在 schema/quality-allowlist.yaml")


def check_tolerances(doc: dict, report: Report) -> None:
    """cue_late / cue_late_skip_before 的上下界比不出 NaN。坏值按默认容差继续查，不能把比较比没。"""
    quality = (doc.get("style") or {}).get("quality") or {}
    if not isinstance(quality, dict):
        return
    for name in ("cue_late", "cue_late_skip_before"):
        if name in quality and _nonfinite(quality[name]):
            report.error("SS100", f"style.quality.{name}", f"{name} 应为有限秒数，收到 {quality[name]!r}")


def check_pauses(doc: dict, report: Report) -> None:
    for n, beat in enumerate(doc.get("beats", [])):
        for i, sentence in enumerate(beat.get("say", [])):
            if "hold" not in sentence:
                continue
            hold = sentence["hold"]
            if not _real(hold):
                continue
            if not math.isfinite(hold) or not pauses.hold_in_range(sentence["text"], hold):
                default, lo, hi = pauses.range_for(sentence["text"])
                kind = pauses.classify(sentence["text"])
                if not math.isfinite(hold):
                    detail = f"hold 应为有限秒数，并落在 {lo:g}–{hi:g}（默认 {default:g}），收到 {hold!r}"
                else:
                    detail = f"句末是{_kind_zh(kind)}，hold 应在 {lo:g}–{hi:g} 秒（默认 {default:g}），收到 {hold:g}"
                report.error("SS485", f"beats[{n}].say[{i}].hold", detail)
        pause = beat.get("pause")
        if not pause or "hold" not in pause:
            continue
        hold = pause["hold"]
        if not _real(hold):
            continue
        bounds = pauses.PAUSE_HOLD.get(pause.get("type"))
        if bounds is None:
            continue
        lo, hi = bounds
        if not math.isfinite(hold) or not lo - 1e-9 <= float(hold) <= hi + 1e-9:
            if not math.isfinite(hold):
                detail = f"pause.hold 应为有限秒数（{lo:g}–{hi:g}），收到 {hold!r}"
            else:
                detail = f"pause.type {pause.get('type')!r} 的 hold 应在 {lo:g}–{hi:g} 秒，收到 {hold:g}"
            report.error("SS486", f"beats[{n}].pause.hold", detail)


def check_timing(doc: dict, timing: object, report: Report, entries=None) -> None:
    """消费 kit/voice 的时间报告。格式见设计稿 §7.8。"""
    if not isinstance(timing, dict) or not isinstance(timing.get("beats"), dict):
        report.error("SS481", "timing", "时间报告应为 {beats: {<beat id>: {cues?, actions?}}}")
        return
    by_id = {b["id"]: (n, b) for n, b in enumerate(doc.get("beats", [])) if isinstance(b, dict) and "id" in b}
    tolerance, skip_before = _cue_config(doc)
    for beat_id, payload in timing["beats"].items():
        if beat_id not in by_id:
            report.error("SS481", f"timing.beats.{beat_id}", f"场景里没有 beat {beat_id!r}")
            continue
        if not isinstance(payload, dict):
            report.error("SS481", f"timing.beats.{beat_id}", "每个 beat 应为映射，含 cues 和/或 actions")
            continue
        n, beat = by_id[beat_id]
        if "cues" in payload:
            _check_gaps(beat, n, payload["cues"], report)
        if "actions" in payload:
            _check_cues(doc, beat, n, payload["actions"], tolerance, skip_before, report, entries)


def _check_gaps(beat: dict, n: int, cues: object, report: Report) -> None:
    say = beat.get("say", [])
    path = f"timing.beats.{beat['id']}.cues"
    if not isinstance(cues, list):
        report.error("SS481", path, "cues 应为列表，每项 {start, end}")
        return
    if len(cues) != len(say):
        report.error("SS481", path, f"cues 有 {len(cues)} 句，场景里有 {len(say)} 句")
        return
    for i, cue in enumerate(cues):
        if not isinstance(cue, dict) or not _number(cue.get("start")) or not _number(cue.get("end")):
            report.error("SS481", f"{path}[{i}]", "每一句要有有限的 start 和 end（秒）")
            return
        if cue["end"] < cue["start"]:
            report.error("SS481", f"{path}[{i}]", "end 不能早于 start")
            return
    for i in range(len(cues) - 1):
        gap = float(cues[i + 1]["start"]) - float(cues[i]["end"])
        sentence = say[i]
        expected = pauses.silence_after(sentence["text"], sentence.get("hold"))
        if abs(gap - expected) > pauses.GAP_TOLERANCE:
            report.error(
                "SS487", f"beats[{n}].say[{i}]",
                f"句间静音是 {gap:.3f}s，按标点应为 {expected:.3f}s（容差 {pauses.GAP_TOLERANCE:g}s）",
            )


def _check_cues(doc, beat, n, actions, tolerance, skip_before, report, entries) -> None:
    path = f"timing.beats.{beat['id']}.actions"
    if not isinstance(actions, list):
        report.error("SS481", path, "actions 应为列表，每项 {at, want, start}")
        return
    allowed = _allow_late(beat)
    for i, item in enumerate(actions):
        if not isinstance(item, dict) or not _time_ref(item.get("at")) or not _number(item.get("want")) or not _number(item.get("start")):
            report.error(
                "SS481", f"{path}[{i}]",
                "每一条要有 at（非负整数或 s1@d0 这种时刻）、以及有限的 want 和 start（秒）",
            )
            continue
        want, start = float(item["want"]), float(item["start"])
        late = start - want
        if late <= tolerance or want <= skip_before:
            continue
        if _same_at(item["at"]) in allowed:
            continue
        if waived(doc, "SS480", entries):
            continue
        report.error(
            "SS480", f"beats[{n}].do",
            f"{beat['id']}[{item['at']}] 画面比旁白书签晚 {late:.2f}s，超过容差 {tolerance:g}s",
        )


def _allow_late(beat: dict) -> set[str]:
    found = set()
    for action in beat.get("do", []):
        if action.get("allow_late") is True and "at" in action:
            found.add(_same_at(action["at"]))
    return found


def _same_at(value: object) -> str:
    return str(value)


def _cue_config(doc: dict) -> tuple[float, float]:
    quality = (doc.get("style") or {}).get("quality") or {}
    tolerance = quality.get("cue_late", DEFAULT_CUE_LATE)
    skip = quality.get("cue_late_skip_before", DEFAULT_SKIP_BEFORE)
    if not _number(tolerance):
        tolerance = DEFAULT_CUE_LATE
    if not _number(skip):
        skip = DEFAULT_SKIP_BEFORE
    return float(tolerance), float(skip)


def _speed_ok(speed: object) -> bool:
    return _number(speed) and abs(float(speed) - REQUIRED_SPEED) <= 1e-6


def _time_ref(value: object) -> bool:
    if isinstance(value, bool) or isinstance(value, float):
        return False
    if isinstance(value, int):
        return value >= 0
    if isinstance(value, str):
        return _TIME_REF.fullmatch(value) is not None
    return False


def _real(value: object) -> bool:
    """整数或浮点，含 NaN / Infinity。布尔不算。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _nonfinite(value: object) -> bool:
    return _real(value) and not math.isfinite(value)


def _number(value: object) -> bool:
    return _real(value) and math.isfinite(value)


def _kind_zh(kind: str) -> str:
    return {
        "comma": "逗号", "semicolon": "分号", "period": "句号", "question": "问号",
        "exclaim": "叹号", "ellipsis": "省略号", "other": "其他符号",
    }.get(kind, kind)
