#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 CHANGELOG.md 生成 README 的「近期版本」区块（自动同步，杜绝手写漂移）。

用法::

    python scripts/sync_readme.py --write    # 写入 README.md / README_EN.md
    python scripts/sync_readme.py --check    # 只校验是否已同步（CI 用，退出码 1 表示漂移）

规则：
- 中文 README：输出最近 N（默认 3）个版本的「版本 | 亮点」表格，亮点取自
  CHANGELOG 中该版本首个条目的加粗标题（缺失时取首句，截断到 60 字）；
- 英文 README：输出最近 N 个版本号列表（要点以中文 CHANGELOG 为准，不做机翻）。
- 区块由 ``<!-- release-highlights:start/end -->`` 标记，标记缺失则报错。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

START = "<!-- release-highlights:start -->"
END = "<!-- release-highlights:end -->"
DEFAULT_LIMIT = 3
MAX_HIGHLIGHT_LEN = 60

VERSION_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]\s*-\s*(\d{4}-\d{2}-\d{2})", re.M)
BOLD_RE = re.compile(r"^\s*[-*]\s+\*\*(.+?)\*\*")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def parse_changelog(text: str) -> List[Tuple[str, str, str]]:
    """返回 [(版本, 日期, 亮点)]，按 CHANGELOG 中的顺序（新→旧）。"""
    sections: List[Tuple[str, str, str]] = []
    marks = list(VERSION_RE.finditer(text))
    for index, mark in enumerate(marks):
        version, date = mark.group(1), mark.group(2)
        start = mark.end()
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = text[start:end]
        highlight = ""
        for line in body.splitlines():
            bold = BOLD_RE.match(line)
            if bold:
                highlight = bold.group(1).strip()
                break
            stripped = line.strip()
            if stripped.startswith(("- ", "* ")):
                candidate = stripped[2:].strip()
                highlight = candidate.split("。")[0][:MAX_HIGHLIGHT_LEN]
                break
        sections.append((version, date, highlight))
    return sections


def render_zh(sections: List[Tuple[str, str, str]], limit: int) -> str:
    rows = ["| 版本 | 亮点 |", "|---|---|"]
    for version, _date, highlight in sections[:limit]:
        rows.append("| **v{0}** | {1} |".format(version, highlight or "—"))
    return "\n".join(rows)


def render_en(sections: List[Tuple[str, str, str]], limit: int) -> str:
    versions = " · ".join("**v{0}**".format(v) for v, _d, _h in sections[:limit])
    return "Recent releases: {0}".format(versions)


def replace_region(text: str, block: str) -> str:
    if START not in text or END not in text:
        raise RuntimeError("README 中缺少 release-highlights 标记")
    head, rest = text.split(START, 1)
    _old, tail = rest.split(END, 1)
    return "{0}{1}\n{2}\n{3}{4}".format(head, START, block, END, tail)


def sync(root: Path, limit: int) -> Dict[str, str]:
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    sections = parse_changelog(changelog)
    if not sections:
        raise RuntimeError("CHANGELOG.md 中未解析到版本条目")
    blocks = {"README.md": render_zh(sections, limit),
              "README_EN.md": render_en(sections, limit)}
    out: Dict[str, str] = {}
    for name, block in blocks.items():
        path = root / name
        text = path.read_text(encoding="utf-8")
        out[name] = replace_region(text, block)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="同步 README 的近期版本区块")
    parser.add_argument("--write", action="store_true", help="写入 README")
    parser.add_argument("--check", action="store_true", help="只校验（漂移则退出码 1）")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="保留最近 N 个版本")
    args = parser.parse_args(argv)
    root = repo_root()
    try:
        rendered = sync(root, args.limit)
    except RuntimeError as exc:
        print("错误: {0}".format(exc), file=sys.stderr)
        return 1
    if args.write:
        for name, text in rendered.items():
            path = root / name
            if path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8")
                print("已更新: {0}".format(name))
            else:
                print("无需变更: {0}".format(name))
        return 0
    if args.check:
        drift = []
        for name, text in rendered.items():
            if (root / name).read_text(encoding="utf-8") != text:
                drift.append(name)
        if drift:
            print("README 近期版本区块与 CHANGELOG 不同步: {0}".format(", ".join(drift)), file=sys.stderr)
            print("请运行: python scripts/sync_readme.py --write", file=sys.stderr)
            return 1
        print("README 近期版本区块已与 CHANGELOG 同步。")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
