"""命令行：scene-spec check 文件...

退出码：0 全部通过（可以有警告）；1 有错误；2 用法错误。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, check_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scene-spec", description="检查 scene-spec 场景描述文件")
    parser.add_argument("--version", action="version", version=f"scene-spec {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="结构 + 语义检查")
    check.add_argument("files", nargs="+")
    check.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    check.add_argument("--strict", action="store_true", help="警告也算失败")
    check.add_argument("--timing", type=Path, help="kit/voice 的时间报告 JSON（画面是否晚于书签、句间静音）")
    args = parser.parse_args(argv)

    timing = None
    if args.timing is not None:
        try:
            timing = json.loads(args.timing.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{args.timing}: 无法读取时间报告：{exc}", file=sys.stderr)
            return 2

    failed = False
    results = {}
    for name in args.files:
        try:
            report = check_file(name, timing=timing)
        except OSError as exc:
            print(f"{name}: 无法读取：{exc}", file=sys.stderr)
            return 2
        results[name] = report.to_dict()
        bad = not report.ok or (args.strict and report.warnings)
        failed = failed or bool(bad)
        if args.json:
            continue
        status = "通过" if not bad else "未通过"
        print(f"{name}: {status}（{len(report.errors)} 个错误，{len(report.warnings)} 个警告）")
        for issue in report.issues:
            print(f"  {issue}")
        if report.stats:
            print("  统计：" + "，".join(f"{k}={v}" for k, v in report.stats.items()))
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
