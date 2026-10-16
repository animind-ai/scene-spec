"""检查结果：每条问题有级别、代码、位置和中文说明。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Issue:
    level: str  # "error" | "warning"
    code: str  # 稳定的问题代码，例如 SS201
    path: str  # 出问题的位置，例如 beats[0].do[2].target
    message: str

    def __str__(self) -> str:
        where = self.path or "(文件)"
        return f"{self.level.upper():7} {self.code} {where}: {self.message}"


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def error(self, code: str, path: str, message: str) -> None:
        self.issues.append(Issue("error", code, path, message))

    def warning(self, code: str, path: str, message: str) -> None:
        self.issues.append(Issue("warning", code, path, message))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def codes(self) -> list[str]:
        return [i.code for i in self.issues]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "issues": [i.__dict__ for i in self.issues],
            "stats": self.stats,
        }
