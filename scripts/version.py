#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""McD Saver 版本号递增工具 —— 自定义 z.x.y 版本格式。

版本格式与递增规则（本项目约定，非 SemVer）：

- 修订号 y：0 ≤ y ≤ 3
- 次版本号 x：0 ≤ x ≤ 6
- 主版本号 z：≥ 0，无上限

每次发布先递增 y；y 超过 3 时进位到 x 加 1 并将 y 重置为 0；
x 超过 6 时进位到主版本号 z 加 1，并将 x、y 重置为 0。

示例：
    0.0.0 → 0.0.1     （正常递增）
    1.5.3 → 1.6.0     （y=3 已达上限，进位到 x）
    1.6.3 → 2.0.0     （y 进位使 x 超限，进位到 z）
    1.7.4 → 2.0.0     （历史过渡版本 y=4 本就超限：归一化即得下一版本）

输入处理：
- 合法版本（分量均在范围内）：正常递增
- 历史过渡版本（y>3 或 x>6，如 1.7.4）：先按进位规则归一化——
  归一化结果即为下一个合法版本
- 非法输入（非数字、段数不为 3、负数、空串等）：抛出 ValueError

用法::

    python scripts/version.py                # 读取仓库当前版本，输出下一个版本
    python scripts/version.py 1.6.3          # 对指定版本递增
    python scripts/version.py --apply        # 递增并写回仓库四件套（CLIENT_INFO /
                                             # SKILL.md / README×2 Release 徽章）
                                             # CHANGELOG 需人工撰写，不自动生成

当前版本单一事实源：``scripts/mcd_client.py`` 的 ``CLIENT_INFO``。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MAX_MINOR = 6   # x 上限
MAX_PATCH = 3   # y 上限
REPO_ROOT = Path(__file__).resolve().parent.parent
_CURRENT_RE = re.compile(r'CLIENT_INFO\s*=\s*\{[^}]*"version":\s*"(\d+\.\d+\.\d+)"')


class VersionError(ValueError):
    """非法版本号输入。"""


def _write_text(path: Path, text: str) -> None:
    """兼容 Python 3.9 的写文件（3.9 的 Path.write_text 不支持 newline 参数）。"""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def parse_version(text: str) -> tuple[int, int, int]:
    """解析 z.x.y 字符串为整数三元组；非法输入抛 VersionError。"""
    if not isinstance(text, str) or not text.strip():
        raise VersionError("版本号不能为空")
    parts = text.strip().split(".")
    if len(parts) != 3:
        raise VersionError(f"版本号必须为三段式 z.x.y，收到：{text!r}")
    numbers: list[int] = []
    for part in parts:
        if not re.fullmatch(r"\d+", part):
            raise VersionError(f"版本号分段必须为非负整数，收到：{part!r}（整体 {text!r}）")
        numbers.append(int(part))
    z, x, y = numbers
    if z < 0 or x < 0 or y < 0:
        raise VersionError(f"版本号分段不能为负：{text!r}")
    return (z, x, y)


def normalize(version: tuple[int, int, int]) -> tuple[int, int, int]:
    """按进位规则归一化超限分量（规则字面语义：超限即进位并**重置为 0**）。

    - y > 3：x 加 1，y 重置为 0
    - x > 6：z 加 1，x、y 重置为 0

    合法版本归一化后保持不变；历史过渡版本（如 1.7.4）归一化后
    即为下一个合法版本。
    """
    z, x, y = version
    if y > MAX_PATCH:
        x += 1
        y = 0
    if x > MAX_MINOR:
        z += 1
        x = 0
        y = 0
    return (z, x, y)


def next_version(current: str) -> str:
    """返回 current 的下一个版本号。

    - 合法输入：递增修订号 y，按规则进位
    - 超限过渡输入（如 1.7.4）：归一化结果即为下一版本
    - 非法输入：抛 VersionError
    """
    z, x, y = parse_version(current)
    normalized = normalize((z, x, y))
    if normalized != (z, x, y):
        # 输入本身超限（历史过渡版本）：归一化结果即下一版本
        return ".".join(str(n) for n in normalized)
    # 合法输入：正常递增 y，再归一化处理进位
    return ".".join(str(n) for n in normalize((z, x, y + 1)))


def current_repo_version() -> str:
    """从单一事实源 scripts/mcd_client.py 读取当前版本。"""
    text = (REPO_ROOT / "scripts" / "mcd_client.py").read_text(encoding="utf-8")
    match = _CURRENT_RE.search(text)
    if not match:
        raise VersionError("无法从 scripts/mcd_client.py 解析 CLIENT_INFO 版本号")
    return match.group(1)


def apply_version(new_version: str) -> list[str]:
    """把新版本写回发布四件套（CHANGELOG 由人工撰写，不在此列）。

    返回已更新的文件相对路径列表。写入前校验 new_version 合法。
    """
    z, x, y = parse_version(new_version)
    normalized = normalize((z, x, y))
    if normalized != (z, x, y):
        raise VersionError(f"目标版本 {new_version} 超出 z.x.y 范围，不可发布")
    updated: list[str] = []

    # 1) CLIENT_INFO / USER_AGENT
    p = REPO_ROOT / "scripts" / "mcd_client.py"
    t = p.read_text(encoding="utf-8")
    old_v = current_repo_version()
    t = t.replace(f'"version": "{old_v}"', f'"version": "{new_version}"')
    t = t.replace(f"maimai-saver/{old_v}", f"maimai-saver/{new_version}")
    _write_text(p, t)
    updated.append("scripts/mcd_client.py")

    # 2) pyproject.toml 版本（此前为覆盖盲区）
    p = REPO_ROOT / "pyproject.toml"
    if p.exists():
        t = p.read_text(encoding="utf-8")
        t = re.sub(r'(?m)^version = "' + re.escape(old_v) + r'"$', f'version = "{new_version}"', t)
        _write_text(p, t)
        updated.append("pyproject.toml")

    # 3) SKILL.md frontmatter
    p = REPO_ROOT / "SKILL.md"
    t = p.read_text(encoding="utf-8")
    t = re.sub(r"(?m)^version: " + re.escape(old_v) + r"$", f"version: {new_version}", t)
    _write_text(p, t)
    updated.append("SKILL.md")

    # 3) README ×2：Release 徽章 URL + 「当前版本」句（测试锁定，防回退丢失）
    for name in ("README.md", "README_EN.md"):
        p = REPO_ROOT / name
        t = p.read_text(encoding="utf-8")
        t = t.replace(f"Release-v{old_v}-9a3412", f"Release-v{new_version}-9a3412")
        t = t.replace(f"releases/tag/v{old_v}", f"releases/tag/v{new_version}")
        t = t.replace(f"当前版本 **v{old_v}**", f"当前版本 **v{new_version}**")
        t = t.replace(f"Current version **v{old_v}**", f"Current version **v{new_version}**")
        _write_text(p, t)
        updated.append(name)
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="version",
        description="McD Saver 版本号递增工具（自定义 z.x.y 格式：y≤3、x≤6）")
    parser.add_argument("current", nargs="?", default=None,
                        help="当前版本号（缺省时自动读取仓库 CLIENT_INFO）")
    parser.add_argument("--apply", action="store_true",
                        help="递增并把新版本写回四件套（CLIENT_INFO/SKILL.md/README×2）")
    args = parser.parse_args(argv)

    current = args.current if args.current else current_repo_version()
    nxt = next_version(current)
    print(f"{current} → {nxt}")
    if args.apply:
        for f in apply_version(nxt):
            print("updated:", f)
        print("提醒：--apply 不覆盖测试计数。发版前请同步更新以下位置的用例数：")
        print("  docs/assets/banner.svg · README.md/README_EN.md（Tests 徽章与测试保障段）· SKILL.md 目录树")
        print("  并在 CHANGELOG 增加新版本条目、于 #275 同步版本进展。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
