"""同一个场景的其他语言版本：画面和时间线不变，换旁白和画面上的字。

源语言是中文。要出英文版，文件里要有两样：

- 每句 `say` 都写 `en`，书签和 `text` 一样（每个 `{@名}` 放在动作要落上的那个英文词前面）；
- `i18n.en` 覆盖画面上的字，键和文档本身一样：

      i18n:
        en:
          meta: {title: "The Pythagorean Theorem"}
          objects:
            wrong: {text: '[$a+b=c$]{#w}?'}
            practice: {lines: ["[Try it]{.HL}", "Legs $3$ and $4$", "Long side $=$ ?"]}
          beats:
            Hook: {pause: {prompt: "How is c related to a and b?"}}
            Reveal: {do: {3: {args: {label: "mean $4$"}}}}   # 动作参数里的字：按 do 的下标只改 args

`localize(doc, "en")` 返回一份普通的英文场景文档（`say[].text` 换成英文句，`style.lang: en`，没有 `i18n`），
voice 和 kit 像读别的场景一样读它。
"""

from __future__ import annotations

import copy
import re

from .report import Report

SOURCE = "zh"
LANGS = ("zh", "en")
_BOOKMARK = re.compile(r"\{@([A-Za-z_][A-Za-z0-9_]*)\}")
_CJK = re.compile(r"[㐀-鿿＀-￯　-〿]")


class LocalizeError(ValueError):
    pass


def _merge(base, patch):
    """把 patch 深合并进 base：映射逐键合并，其他（包括列表）整个替换。"""
    if isinstance(base, dict) and isinstance(patch, dict):
        out = dict(base)
        for k, v in patch.items():
            out[k] = _merge(base[k], v) if k in base else copy.deepcopy(v)
        return out
    return copy.deepcopy(patch)


def bookmarks(text: str) -> list[str]:
    return _BOOKMARK.findall(text)


def localize(doc: dict, lang: str) -> dict:
    """lang 版本的场景。源语言只去掉 `i18n`。"""
    if lang not in LANGS:
        raise LocalizeError(f"不认识的语言 {lang!r}（可用：{'、'.join(LANGS)}）")
    out = copy.deepcopy(doc)
    overlays = out.pop("i18n", None) or {}
    if lang == SOURCE:
        return out
    missing = []
    for beat in out.get("beats", []):
        for i, s in enumerate(beat.get("say", [])):
            line = s.pop(lang, None)
            if not line:
                missing.append(f"{beat.get('id')}[{s.get('id', i)}]")
                continue
            s["text"] = line
    if missing:
        raise LocalizeError(f"这些句子没有 {lang}：{'、'.join(missing)}")
    overlay = overlays.get(lang) or {}
    for key in ("meta", "style"):
        if key in overlay:
            out[key] = _merge(out.get(key, {}), overlay[key])
    objects = out.get("objects", {})
    for oid, patch in (overlay.get("objects") or {}).items():
        if oid not in objects:
            raise LocalizeError(f"i18n.{lang}.objects.{oid}：没有这个对象")
        objects[oid] = _merge(objects[oid], patch)
    beats = {b["id"]: b for b in out.get("beats", [])}
    for bid, patch in (overlay.get("beats") or {}).items():
        if bid not in beats:
            raise LocalizeError(f"i18n.{lang}.beats.{bid}：没有这个 beat")
        patch = dict(patch)
        if "say" in patch:
            raise LocalizeError(f"i18n.{lang}.beats.{bid}：say 不能覆盖（旁白写在每句的 `{lang}` 里）")
        do = beats[bid].get("do", [])
        for index, change in (patch.pop("do", None) or {}).items():
            if not isinstance(index, int) or not 0 <= index < len(do):
                raise LocalizeError(f"i18n.{lang}.beats.{bid}.do.{index}：没有这个动作（按 do 的下标写，从 0 数）")
            if set(change) != {"args"} or "args" not in do[index]:
                raise LocalizeError(f"i18n.{lang}.beats.{bid}.do.{index}：只能改已有动作的 args")
            do[index] = _merge(do[index], change)
        beats[bid].update(_merge(beats[bid], patch))
    out.setdefault("style", {})["lang"] = lang
    return out


def _strings(x, path: str):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(x, str):
        yield path, x


def check(doc: dict, report: Report) -> None:
    """对 `i18n` 里的每种语言：每句都有译文、书签和中文一致、本地化后画面上不再有中文。"""
    for lang in doc.get("i18n") or {}:
        if lang == SOURCE or lang not in LANGS:
            report.error("SS501", f"i18n.{lang}", f"i18n 只放其他语言：{'、'.join(sorted(set(LANGS) - {SOURCE}))}")
            continue
        for b, beat in enumerate(doc.get("beats", [])):
            for i, s in enumerate(beat.get("say", [])):
                where = f"beats[{b}].say[{i}].{lang}"
                line = s.get(lang)
                if not line:
                    report.error("SS502", where, f"声明了 i18n.{lang}，这句却没有 {lang}")
                    continue
                want, got = bookmarks(s["text"]), bookmarks(line)
                if sorted(want) != sorted(got):
                    report.error("SS503", where, f"书签和 text 不一致：text 有 {want}，{lang} 有 {got}")
                elif want != got:
                    report.warning("SS504", where, f"书签顺序和 text 不同：{want} / {got}")
                if _CJK.search(_BOOKMARK.sub("", line)):
                    report.warning("SS505", where, f"{lang} 句里有中文")
        try:
            local = localize(doc, lang)
        except LocalizeError as exc:
            report.error("SS506", f"i18n.{lang}", str(exc))
            continue
        shown = {"meta.title": local.get("meta", {}).get("title", ""), "objects": local.get("objects", {}),
                 "beats": [{k: v for k, v in b.items() if k != "say"} for b in local.get("beats", [])]}
        for path, value in _strings(shown, ""):
            if _CJK.search(value):
                report.warning("SS507", path, f"{lang} 版里还是中文：{value[:30]!r}（写进 i18n.{lang}）")
