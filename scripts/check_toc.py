#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""README 目录锚点与中英结构校验（从工作区脚本迁入仓库，CI 与本地共用）。

校验三件事：

1. 中英 README 的目录链接全部能解析到真实标题（无死链）；
2. **每个章节都出现在目录里**（2026-10-19 审计发现「反馈与支持」正文有、目录漏）；
3. 中英章节一一对应（配对表 + 标题数量一致）。

用法::

    python scripts/check_toc.py                 # 默认校验仓库根的两份 README
    python scripts/check_toc.py README.md README_EN.md
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]

# 中英章节配对表：新增章节必须同步登记，否则英文缺失会在此暴露
PAIRS: List[Tuple[str, str]] = [
    ("项目简介", "Project overview"),
    ("功能特性", "Features"),
    ("快速开始", "Quick start"),
    ("30 秒体验（免 Token）", "30 seconds, no token"),
    ("安装步骤", "Installation"),
    ("使用说明", "Usage"),
    ("命令速查", "Command cheat sheet"),
    ("全渠道比价示例", "Cross-channel example"),
    ("配置说明", "Configuration"),
    ("项目结构", "Project layout"),
    ("工具能力总览", "Tool coverage"),
    ("常见问题", "FAQ"),
    ("更新说明", "Release notes"),
    ("发布产物与版本策略", "Release artifacts"),
    ("反馈与支持", "Feedback"),
    ("参与贡献", "Contributing"),
    ("免责声明", "Disclaimer"),
    ("许可证", "License"),
    ("Star History", "Star History"),
]

TOC_TITLES = ("目录", "Table of contents")


def github_slug(text: str) -> str:
    """近似 github-slugger：小写；删除非字母/数字/空格/连字符字符；空格→连字符。"""
    text = text.strip().lower()
    out = []
    for ch in text:
        if ch in (" ", "-"):
            out.append(ch)
            continue
        if unicodedata.category(ch)[0] in ("L", "N"):  # 字母与数字（含 CJK）
            out.append(ch)
    return "".join(out).replace(" ", "-")


def extract(md_path: Path) -> Tuple[List[str], List[str]]:
    """返回 (全部标题, 目录链接的 slug 列表)。"""
    lines = md_path.read_text(encoding="utf-8").splitlines()
    headings: List[str] = []
    toc_links: List[str] = []
    in_toc = False
    for line in lines:
        match = re.match(r"^(#{2,3})\s+(.*)$", line)
        if match:
            headings.append(match.group(2).strip())
        if re.match(r"^## 目录$|^## Table of contents$", line):
            in_toc = True
            continue
        if in_toc:
            if re.match(r"^\s*-\s+", line):
                link = re.search(r"\]\(#([^)]+)\)", line)
                if link:
                    toc_links.append(link.group(1))
            elif line.strip() == "":
                continue
            else:
                in_toc = False
    return headings, toc_links


def check(md_path: Path, name: str) -> Tuple[bool, List[str]]:
    """校验单个 README：目录无死链，且每个章节都被目录覆盖。"""
    headings, links = extract(md_path)
    ok = True
    slugs = {github_slug(heading): heading for heading in headings}
    for link in links:
        if link not in slugs:
            ok = False
            print("[{0}] 死链: #{1}".format(name, link))
    missing = [heading for heading in headings
               if heading not in TOC_TITLES and github_slug(heading) not in links]
    if missing:
        ok = False
        print("[{0}] 章节未出现在目录: {1}".format(name, " / ".join(missing)))
    print("[{0}] 标题 {1} 个，目录链接 {2} 个，全部可解析: {3}".format(
        name, len(headings), len(links), ok))
    return ok, headings


def _h2_titles(md_path: Path) -> List[str]:
    """返回二级标题（##）的顺序列表（不含目录标题）。"""
    out: List[str] = []
    for line in md_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^##\s+(.*)$", line)
        if match:
            title = match.group(1).strip()
            if title not in TOC_TITLES:
                out.append(title)
    return out


def _toc_titles(md_path: Path, all_titles: List[str]) -> List[str]:
    """返回目录条目按目录顺序排列的标题列表。"""
    by_slug = {github_slug(title): title for title in all_titles}
    return [by_slug.get(slug, slug) for slug in extract(md_path)[1]]


def main(argv: List[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    zh_path = Path(args[0]) if args else ROOT / "README.md"
    en_path = Path(args[1]) if len(args) > 1 else ROOT / "README_EN.md"

    ok_zh, zh = check(zh_path, "中文")
    ok_en, en = check(en_path, "英文")

    en_set = {heading.lower() for heading in en}
    missing = [zh_title for zh_title, en_title in PAIRS if en_title.lower() not in en_set]
    if len(zh) != len(en):
        print("标题数量不一致: 中文 {0} vs 英文 {1}".format(len(zh), len(en)))
        print("  中文: {0}".format(zh))
        print("  英文: {0}".format(en))
        return 1
    if missing:
        print("英文缺失章节: {0}".format(missing))
        return 1

    zh_h2 = _h2_titles(zh_path)
    en_h2 = _h2_titles(en_path)
    zh_toc = _toc_titles(zh_path, zh)
    en_toc = _toc_titles(en_path, en)

    # 1) 每份 README 自身：目录中的二级章节顺序必须与正文出现顺序一致
    for name, h2, toc in (("中文", zh_h2, zh_toc), ("英文", en_h2, en_toc)):
        h2_set = set(h2)
        toc_h2 = [t for t in toc if t in h2_set]
        if toc_h2 != h2:
            print("[{0}] 目录顺序与正文顺序不一致".format(name))
            print("  目录: {0}".format(" > ".join(toc_h2)))
            print("  正文: {0}".format(" > ".join(h2)))
            return 1

    # 2) 中英之间：正文与目录的章节顺序都要逐位对应
    en_to_zh = {en_title: zh_title for zh_title, en_title in PAIRS}
    if [en_to_zh.get(t, t) for t in en_h2] != zh_h2:
        print("中英正文章节顺序不一致：")
        print("  中文: {0}".format(" > ".join(zh_h2)))
        print("  英文: {0}".format(" > ".join(en_h2)))
        return 1
    if [en_to_zh.get(t, t) for t in en_toc] != zh_toc:
        print("中英目录顺序不一致：")
        print("  中文: {0}".format(" > ".join(zh_toc)))
        print("  英文: {0}".format(" > ".join(en_toc)))
        return 1

    print("[结构] 中英章节一一对应、目录与正文顺序一致，共 {0} 个二级/三级标题: OK".format(len(zh)))
    return 0 if ok_zh and ok_en else 1


if __name__ == "__main__":
    sys.exit(main())
