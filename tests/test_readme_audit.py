"""README 事实一致性守卫（2026-10-21）。

实现见 ``scripts/audit_readme.py``：命令速查表、内联脚本路径、测试用例数、
Python 版本声明、许可证声明——五类可机械核对的事实，一旦与仓库不一致即失败。
"""
import audit_readme


def test_readme_audit_passes():
    problems = audit_readme.audit()
    assert not problems, "README 与仓库不一致：\n  - " + "\n  - ".join(problems)


def test_cli_subcommands_are_parsed():
    """多行 add_parser 注册也要能被解析到（schema / claim 曾经漏检）。"""
    found = audit_readme.cli_subcommands("mcd.py")
    assert {"check", "tools", "schema", "call", "claim"} <= found


def test_collected_count_is_positive():
    assert audit_readme.collected_test_count() > 100
