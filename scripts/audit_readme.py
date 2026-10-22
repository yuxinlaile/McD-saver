#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""README 与仓库事实的一致性审计（2026-10-21 新增）。

用户的痛点是「README 经常匹配不上更新」。本脚本把可机械核对的事实做成检查项，
既可手工运行（输出报告），也被 ``tests/test_readme_audit.py`` 引入做 CI 守卫：

    python scripts/audit_readme.py          # 打印审计结果，发现问题时退出码 1

检查项：
1. 命令速查表：README 提到的 ``mcd.py <子命令>`` 必须真实存在，且所有子命令都被文档提到；
2. 内联脚本路径：README 反引号里的 ``scripts/xxx.py`` 必须存在于仓库；
3. 测试计数：README 徽章 / 目录树里的用例数必须等于实际收集到的用例数；
4. Python 版本：README 声明与 ``pyproject.toml`` 的 requires-python、CI 矩阵一致；
5. 许可证：README 声明的许可证类型必须出现在 ``LICENSE`` 中。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Set

from console import ensure_utf8_stdio

REPO = Path(__file__).resolve().parent.parent


def _read(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def cli_subcommands(script: str) -> Set[str]:
    """解析脚本里注册的子命令（兼容多行 add_parser 调用）。"""
    text = (REPO / "scripts" / script).read_text(encoding="utf-8")
    return set(re.findall(r"add_parser\(\s*[\"']([a-z][a-z0-9-]*)[\"']", text))


def check_command_table() -> List[str]:
    """命令速查表与 CLI 子命令一致。"""
    problems: List[str] = []
    documented = set(re.findall(r"scripts/mcd\.py\s+([a-z][a-z0-9-]*)", _read("README.md")))
    actual = cli_subcommands("mcd.py")
    for cmd in sorted(documented - actual):
        problems.append("README 写了不存在的子命令: mcd.py {0}（实际: {1}）".format(cmd, ", ".join(sorted(actual))))
    for cmd in sorted(actual - documented):
        problems.append("CLI 子命令未进 README 命令表: mcd.py {0}".format(cmd))
    return problems


def check_inline_script_paths() -> List[str]:
    """README 反引号中提到的 scripts/*.py 必须存在。"""
    problems: List[str] = []
    for name in ("README.md", "README_EN.md"):
        for rel in set(re.findall(r"`(scripts/[A-Za-z0-9_]+\.py)", _read(name))):
            if not (REPO / rel).exists():
                problems.append("{0} 提到的脚本不存在: {1}".format(name, rel))
    return problems


def collected_test_count() -> int:
    """实际收集到的用例数（pytest --collect-only）。"""
    out = subprocess.run([sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
                         cwd=str(REPO), capture_output=True, text=True, timeout=300)
    match = re.search(r"(\d+)\s+tests?\s+collected", out.stdout)
    return int(match.group(1)) if match else -1


def check_test_counts() -> List[str]:
    """README 中的用例数必须等于实际收集数。"""
    actual = collected_test_count()
    if actual < 0:
        return ["无法获取实际用例数（pytest --collect-only 失败）"]
    problems: List[str] = []
    zh = _read("README.md")
    en = _read("README_EN.md")
    for label, text, pattern in (
        ("README.md 徽章", zh, r"Tests-(\d+)%20passed"),
        ("README.md 测试保障段", zh, r"(\d+) 个单元测试"),
        ("README.md 目录树", zh, r"tests/\s+(\d+) 项单元测试"),
        ("README_EN.md 徽章", en, r"Tests-(\d+)%20passed"),
        ("README_EN.md 测试保障段", en, r"(\d+) unit tests"),
        ("README_EN.md 目录树", en, r"tests/\s+(\d+) unit tests"),
    ):
        found = re.findall(pattern, text)
        if not found:
            problems.append("{0}: 未找到用例数声明".format(label))
            continue
        for value in found:
            if int(value) != actual:
                problems.append("{0} 写 {1}，实际 {2}".format(label, value, actual))
    skill = _read("SKILL.md")
    for value in re.findall(r"（(\d+) 个用例", skill):
        if int(value) != actual:
            problems.append("SKILL.md 目录树写 {0}，实际 {1}".format(value, actual))
    return problems


def check_python_version() -> List[str]:
    """Python 版本声明三方一致：README / pyproject / CI 矩阵。"""
    problems: List[str] = []
    readme = _read("README.md")
    # 兼容两种写法：徽章里的 `Python-3.9%2B` 与正文里的 `Python 3.9+`
    declared = set(re.findall(r"Python[\s\-]*(3\.\d+)", readme))
    pyproject = _read("pyproject.toml")
    requires = re.search(r'requires-python\s*=\s*">=\s*(3\.\d+)"', pyproject)
    ci = _read(".github/workflows/ci.yml")
    matrix = set(re.findall(r'"(3\.\d+)"', ci))
    if not declared:
        problems.append("README 未声明 Python 版本")
    if not requires:
        problems.append("pyproject.toml 未声明 requires-python")
    if declared and requires and requires.group(1) not in declared:
        problems.append("README 声明 Python {0}+，pyproject 要求 >={1}".format(
            sorted(declared), requires.group(1)))
    if requires and matrix and requires.group(1) not in matrix:
        problems.append("pyproject 要求 >={0}，CI 矩阵未覆盖: {1}".format(requires.group(1), sorted(matrix)))
    return problems


def check_license() -> List[str]:
    """README 的许可证声明必须与 LICENSE 文件一致。"""
    problems: List[str] = []
    readme = _read("README.md")
    if "MIT" in readme or "MIT License" in readme:
        license_text = _read("LICENSE")
        if "MIT License" not in license_text and "MIT" not in license_text:
            problems.append("README 声明 MIT，但 LICENSE 中未见 MIT 字样")
    return problems


CHECKS = (
    ("命令速查表 ↔ CLI 子命令", check_command_table),
    ("内联脚本路径存在", check_inline_script_paths),
    ("测试用例数一致", check_test_counts),
    ("Python 版本声明一致", check_python_version),
    ("许可证声明一致", check_license),
)


def audit() -> List[str]:
    """执行全部检查，返回问题清单（空列表表示通过）。"""
    problems: List[str] = []
    for _label, func in CHECKS:
        problems.extend(func())
    return problems


def main() -> int:
    ensure_utf8_stdio()
    problems = audit()
    if not problems:
        print("README 审计通过：命令表 / 脚本路径 / 用例数 / Python 版本 / 许可证 均与仓库一致。")
        return 0
    print("README 审计发现 {0} 处不一致：".format(len(problems)))
    for item in problems:
        print("  - " + item)
    return 1


if __name__ == "__main__":
    sys.exit(main())
