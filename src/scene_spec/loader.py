"""受限 YAML 读取器。

和普通 YAML 的区别（见设计稿 §2）：
- 禁用锚点、别名、合并键和自定义标签；
- 布尔只认 true / false，yes、no、on、off 都是字符串；
- 整数、小数只认十进制写法，16:9 这类六十进制、0o17 这类八进制、日期一律是字符串；
- 同一个映射里出现重复的键直接报错（普通 YAML 会静默覆盖）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from yaml.nodes import MappingNode

from .report import Report


class SpecLoadError(Exception):
    """文件无法作为受限 YAML 读取。issues 里是具体原因。"""

    def __init__(self, report: Report):
        self.report = report
        super().__init__("; ".join(str(i) for i in report.issues))


class _Resolver(yaml.resolver.BaseResolver):
    pass


_Resolver.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf")
)
_Resolver.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"^-?(?:0|[1-9][0-9]*)$"), list("-0123456789")
)
_Resolver.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]+(?:[eE][-+]?[0-9]+)?$"),
    list("-0123456789"),
)
_Resolver.add_implicit_resolver(
    "tag:yaml.org,2002:null", re.compile(r"^(?:null|~|)$"), ["n", "~", ""]
)


class _Constructor(yaml.constructor.SafeConstructor):
    def construct_mapping(self, node, deep=False):
        if isinstance(node, MappingNode):
            seen: dict = {}
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=True)
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        None, None, f"重复的键 {key!r}", key_node.start_mark
                    )
                seen[key] = True
        return super().construct_mapping(node, deep=deep)

    def construct_yaml_bool(self, node):
        return self.construct_scalar(node) == "true"


_Constructor.add_constructor("tag:yaml.org,2002:bool", _Constructor.construct_yaml_bool)


class _Loader(
    yaml.reader.Reader,
    yaml.scanner.Scanner,
    yaml.parser.Parser,
    yaml.composer.Composer,
    _Constructor,
    _Resolver,
):
    def __init__(self, stream):
        yaml.reader.Reader.__init__(self, stream)
        yaml.scanner.Scanner.__init__(self)
        yaml.parser.Parser.__init__(self)
        yaml.composer.Composer.__init__(self)
        _Constructor.__init__(self)
        _Resolver.__init__(self)


def _line(mark) -> str:
    return f"第 {mark.line + 1} 行" if mark is not None else ""


def _scan_forbidden(text: str, report: Report) -> None:
    """在构造之前扫一遍事件流，找锚点、别名、标签和合并键。"""
    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        where = _line(event.start_mark)
        if isinstance(event, yaml.AliasEvent):
            report.error("SS001", where, f"不允许使用别名 *{event.anchor}")
            continue
        anchor = getattr(event, "anchor", None)
        if anchor:
            report.error("SS001", where, f"不允许使用锚点 &{anchor}")
        tag = getattr(event, "tag", None)
        implicit = getattr(event, "implicit", None)
        explicit_tag = tag and (implicit is False or implicit == (False, False))
        if explicit_tag and tag not in ("tag:yaml.org,2002:str",):
            report.error("SS002", where, f"不允许使用自定义标签 {tag}")
        if isinstance(event, yaml.ScalarEvent) and event.value == "<<" and event.style is None:
            report.error("SS003", where, "不允许使用合并键 <<")


def load_text(text: str) -> object:
    """读取受限 YAML 文本，返回普通的 dict / list / 标量。失败时抛 SpecLoadError。"""
    report = Report()
    try:
        _scan_forbidden(text, report)
    except yaml.YAMLError as exc:
        report.error("SS000", _line(getattr(exc, "problem_mark", None)), f"YAML 语法错误：{_problem(exc)}")
        raise SpecLoadError(report) from exc
    if report.errors:
        raise SpecLoadError(report)
    loader = _Loader(text)
    try:
        return loader.get_single_data()
    except yaml.YAMLError as exc:
        report.error("SS000", _line(getattr(exc, "problem_mark", None)), f"YAML 语法错误：{_problem(exc)}")
        raise SpecLoadError(report) from exc
    finally:
        loader.dispose()


def load_file(path: str | Path) -> object:
    return load_text(Path(path).read_text(encoding="utf-8"))


def _problem(exc: yaml.YAMLError) -> str:
    problem = getattr(exc, "problem", None) or str(exc)
    hint = ""
    if "unknown escape character" in problem:
        hint = "（双引号字符串里的反斜杠会被当成转义；含 LaTeX 的文字请用单引号）"
    return f"{problem}{hint}"
