"""clip 对象：外部画面（视频或帧序列）当背景板。

画面上的字和公式必须是矢量对象。clip 只承载没有可读文字的素材。
讲解 beat 里，clip 不能占住主讲区，除非这一条 clip 写了 explain: allow，或这个 beat 写了 plate: allow。

错误码：
- SS470  frames 没写 fps
- SS471  content_kind 是文字/公式，或不是 plate / simulation / broll
- SS472  src 不存在，或文件类型和 kind 不符（只有给出素材根目录时才查是否存在）
- SS473  trim 的入点不小于出点，或探得到时长时落在时长外面
- SS474  讲解 beat 里 clip 占住了主讲区
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import selectors
from .report import Report

CONTENT_KINDS = {"plate", "simulation", "broll"}
# 这些名字表示作者想用素材承载画面上的字。一律拒绝，字必须是 text / math。
TEXT_KINDS = {"text", "formula", "math", "tex", "caption", "subtitle", "title", "label", "narration"}
VIDEO_SUFFIXES = {".mp4", ".mov"}
FRAME_SUFFIXES = {".png", ".jpg", ".jpeg"}
INSET_MAX = 0.5  # size 的宽和高都不超过这个比例，算角落里的小窗，不算占住主讲区
STAGE_REGIONS = {"top", "footer", "side"}
# 和 moxian collect_frames() 同一把钥匙：frame_2 排在 frame_10 前面。
_NATURAL = re.compile(r"(\d+)")


def check(doc: dict, report: Report, root: Path | None) -> None:
    objects: dict = doc.get("objects", {})
    clips = {oid: d for oid, d in objects.items() if d.get("type") == "clip"}
    for oid, definition in clips.items():
        _check_one(oid, definition, report, root)
    if clips:
        _check_stage(doc, clips, report)


def _check_one(oid: str, definition: dict, report: Report, root: Path | None) -> None:
    path = f"objects.{oid}"
    kind = definition.get("kind")
    _check_content_kind(definition.get("content_kind"), f"{path}.content_kind", report)
    if kind == "frames" and "fps" not in definition:
        report.error("SS470", f"{path}.fps", "kind: frames 需要 fps：这串帧每秒几张")
    if kind == "frames" and "fps" in definition:
        fps = definition["fps"]
        if isinstance(fps, bool) or not isinstance(fps, (int, float)) or fps <= 0:
            report.error("SS470", f"{path}.fps", f"fps 应为大于 0 的数，收到 {fps!r}")
    _check_trim(definition, path, report, root)
    _check_src(definition, path, report, root)


def _check_content_kind(value: object, path: str, report: Report) -> None:
    if not isinstance(value, str):
        return  # 结构层会报
    key = value.strip().lower()
    if key in TEXT_KINDS:
        report.error(
            "SS471", path,
            f"content_kind 是 {value!r}：clip 不能承载画面上的字或公式，请改用 text / math 矢量对象",
        )
        return
    if key not in CONTENT_KINDS:
        known = "、".join(sorted(CONTENT_KINDS))
        report.error("SS471", path, f"content_kind 应为 {known} 之一，收到 {value!r}")


def _check_src(definition: dict, path: str, report: Report, root: Path | None) -> None:
    src = definition.get("src")
    kind = definition.get("kind")
    if not isinstance(src, str) or kind not in ("video", "frames"):
        return
    if root is None:
        return  # 没有素材根：不查文件在不在
    target = _resolve(root, src)
    spath = f"{path}.src"
    if target is None:
        report.error("SS472", spath, f"路径 {src!r} 不合法")
        return
    if kind == "video":
        if not target.is_file():
            report.error("SS472", spath, f"找不到视频 {src!r}（相对 {root}）")
            return
        if target.suffix.lower() not in VIDEO_SUFFIXES:
            report.error("SS472", spath, f"kind: video 只接受 .mp4 / .mov，这是 {target.suffix or '无后缀'}")
        return
    if not target.is_dir():
        report.error("SS472", spath, f"kind: frames 的 src 应是 PNG/JPEG 目录，{src!r} 不是目录")
        return
    frames = _frames(target)
    if not frames:
        report.error("SS472", spath, f"{src!r} 里没有 PNG/JPEG 帧")


def _check_trim(definition: dict, path: str, report: Report, root: Path | None) -> None:
    trim = definition.get("trim") or {}
    if not isinstance(trim, dict):
        return
    start = trim.get("in", 0)
    end = trim.get("out")
    tpath = f"{path}.trim"
    if not _number(start) or start < 0:
        report.error("SS473", f"{tpath}.in", f"trim.in 应为不小于 0 的秒数，收到 {start!r}")
        return
    if end is not None and (not _number(end) or end <= start):
        report.error("SS473", f"{tpath}.out", f"trim.out 应大于 trim.in（{start:g}），收到 {end!r}")
        return
    duration = _duration(definition, root)
    if duration is None:
        return
    if start >= duration:
        report.error("SS473", f"{tpath}.in", f"trim.in {start:g}s 不小于素材时长 {duration:.3f}s")
    if end is not None and end > duration + 1e-3:
        report.error("SS473", f"{tpath}.out", f"trim.out {end:g}s 超过素材时长 {duration:.3f}s")


def _duration(definition: dict, root: Path | None) -> float | None:
    """探得到才返回秒数。探不到（没有 ffprobe、没有素材根）返回 None，trim 只查入点出点的先后。"""
    if root is None:
        return None
    src = definition.get("src")
    if not isinstance(src, str):
        return None
    target = _resolve(root, src)
    if target is None or not target.exists():
        return None
    kind = definition.get("kind")
    if kind == "frames":
        fps = definition.get("fps")
        if not _number(fps) or fps <= 0:
            return None
        count = len(_frames(target)) if target.is_dir() else 0
        if count == 0:
            return None
        return count / float(fps)
    if kind == "video" and target.is_file():
        return ffprobe_duration(target)
    return None


def ffprobe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        value = float(out.stdout.strip())
    except ValueError:
        return None
    return value if value > 0 else None


def _resolve(root: Path, src: str) -> Path | None:
    if "\x00" in src:
        return None
    path = Path(src)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def _frames(directory: Path) -> list[Path]:
    """目录里的 PNG/JPEG，按文件名自然排序（1.png、2.png、10.png）。

    与 moxian `collect_frames()` 的 `_natural_key` 一致：数字段按整数比，其余按小写字符串。
    时长是张数 ÷ fps，顺序不改变时长，但和渲染用的是同一列帧。
    """
    frames = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in FRAME_SUFFIXES]
    frames.sort(key=_natural_key)
    return frames


def _natural_key(path: Path) -> tuple:
    parts = _NATURAL.split(path.name)
    return tuple(int(part) if part.isdigit() else part.lower() for part in parts)


def occupies_stage(definition: dict) -> bool:
    """占住主讲区：放在 stage 里且不是小窗，或者没写区域、又不是小窗（整幅底板）。"""
    if definition.get("pin") == "top":
        return False
    region = definition.get("in")
    if region in STAGE_REGIONS:
        return False
    if _inset(definition):
        return False
    if region == "stage" or region is None:
        return True
    return False


def _inset(definition: dict) -> bool:
    size = definition.get("size") or {}
    width, height = size.get("max_width"), size.get("max_height")
    return _number(width) and _number(height) and width <= INSET_MAX and height <= INSET_MAX


def _check_stage(doc: dict, clips: dict, report: Report) -> None:
    """讲解段的可见性看动作做完的结果，不看继承下来、还没被开头动作改掉的那一帧。

    开头连续的 `at: 0`（含紧跟的 `with: prev`，以及同样写着 `at: 0` 的下一批）先全部做完再判断。
    同一时刻的一批只看最终状态：先 show 再在 `with: prev` 里 hide，等于没占住。
    更晚的书签（`at: s1`）才 hide，开场那段仍然算占住。
    """
    objects = doc.get("objects", {})
    visible: set[str] = set()
    for n, beat in enumerate(doc.get("beats", [])):
        actions = beat.get("do") if isinstance(beat.get("do"), list) else []
        if not _explanation(beat):
            for action in actions:
                _apply(visible, action, objects)
            continue
        flagged: set[str] = set()
        groups = _time_groups(actions)
        index = 0
        while index < len(groups) and _zero_time(groups[index]):
            for action in groups[index]:
                _apply(visible, action, objects)
            index += 1
        _flag(visible, clips, beat, n, report, flagged)
        while index < len(groups):
            for action in groups[index]:
                _apply(visible, action, objects)
            _flag(visible, clips, beat, n, report, flagged)
            index += 1


def _time_groups(actions: list) -> list[list[dict]]:
    """一批是头动作加上紧跟的 `with: prev`。连续几批的 `at` 相同，就合成同一时刻。

    `after: prev` 是更晚的时刻，不并进上一批。
    """
    batches: list[list[dict]] = []
    current: list[dict] = []
    for action in actions:
        if not isinstance(action, dict):
            if current:
                batches.append(current)
                current = []
            continue
        if action.get("with") == "prev" and current:
            current.append(action)
            continue
        if current:
            batches.append(current)
        current = [action]
    if current:
        batches.append(current)

    groups: list[list[dict]] = []
    for batch in batches:
        key = _at_key(batch[0])
        if groups and key is not None and _at_key(groups[-1][0]) == key:
            groups[-1].extend(batch)
        else:
            groups.append(list(batch))
    return groups


def _at_key(action: dict) -> str | None:
    if "at" not in action or action.get("with") == "prev":
        return None
    value = action["at"]
    if _zero_at(value):
        return "0"
    return str(value)


def _zero_time(group: list[dict]) -> bool:
    head = group[0]
    return "at" in head and head.get("with") != "prev" and _zero_at(head.get("at"))


def _zero_at(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value == 0
    return value == "0"


def _explanation(beat: dict) -> bool:
    if not beat.get("say"):
        return False
    if beat.get("id") == "Hook" or beat.get("role") == "hook":
        return False
    return True


def _flag(visible: set[str], clips: dict, beat: dict, n: int, report: Report, flagged: set[str]) -> None:
    if beat.get("plate") == "allow":
        return
    for oid in sorted(visible):
        if oid in flagged:
            continue
        definition = clips.get(oid)
        if definition is None or definition.get("explain") == "allow":
            continue
        if occupies_stage(definition):
            flagged.add(oid)
            report.error(
                "SS474", f"beats[{n}]",
                f"讲解 beat {beat.get('id')!r} 里 clip {oid} 占住了主讲区。"
                f"钩子段可以。讲解段请在开头用 at: 0 先 hide（同一时刻的 with: prev 一起算），"
                f"或在 clip 上写 explain: allow，或在这个 beat 上写 plate: allow",
            )


def _apply(visible: set[str], action: dict, objects: dict) -> None:
    if not isinstance(action, dict):
        return
    act = action.get("act")
    if act == "show" and "target" in action:
        _reveal(visible, _obj(action["target"]), objects)
    elif act == "transform" and "to" in action:
        _reveal(visible, _obj(action["to"]), objects)
    elif act == "hide" and "target" in action:
        sel = selectors.parse(action["target"]) if isinstance(action["target"], str) else None
        if sel is not None and sel.span is None and sel.part is None and sel.index is None:
            _conceal(visible, sel.obj, objects)


def _reveal(visible: set[str], oid: str | None, objects: dict) -> None:
    if oid is None or oid in visible:
        return
    visible.add(oid)
    definition = objects.get(oid) or {}
    if definition.get("type") == "group":
        for child in definition.get("children") or []:
            _reveal(visible, child, objects)


def _conceal(visible: set[str], oid: str, objects: dict) -> None:
    visible.discard(oid)
    definition = objects.get(oid) or {}
    if definition.get("type") == "group":
        for child in definition.get("children") or []:
            if isinstance(child, str):
                _conceal(visible, child, objects)


def _obj(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    sel = selectors.parse(text)
    return None if sel is None else sel.obj


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
