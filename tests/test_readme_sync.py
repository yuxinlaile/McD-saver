"""README 与文档同步守卫（2026-10-21）。

把「README 经常匹配不上更新」这件事固化为 CI 断言，覆盖六类易漂移点：
1. 「近期版本」区块与 CHANGELOG 同步（由 ``scripts/sync_readme.py`` 生成）；
2. 环境变量：README 表格里的每个变量都必须被代码读取，代码读取的每个变量都必须在 README 中出现
   （仅用于打印迁移提示的已退役变量除外）；
3. ``SKILL.md`` 目录树中的每个路径都真实存在（改名/删除后不留旧路径）；
4. README「工具能力总览」与 ``references/tools.md`` 的工具集合一致；
5. 全部 Markdown 的相对链接可达（文件移动/改名不留死链）；
6. 试算页示例数据条数与 README 的表述一致。
"""
import re
from pathlib import Path

import pytest

import sync_readme

REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"releases", ".git", ".workbuddy", "__pycache__"}
# 已退役、仅用于打印迁移提示的环境变量：不应出现在 README 配置表里
RETIRED_ENV_VARS = {"MAIMAI_DEALS_PROVIDER"}


def _md_files():
    for path in REPO.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def _tree_entries(text):
    """解析 SKILL.md 的目录树，返回 [(深度, 名称, 是否目录)]。"""
    entries = []
    for line in text.splitlines():
        m = re.match(r"^([\s│]*)[├└]──\s*(.+?)\s*$", line)
        if not m:
            continue
        prefix, rest = m.group(1), m.group(2)
        name = rest.split("#")[0].strip()
        if not name:
            continue
        depth = len(prefix) // 4
        is_dir = name.endswith("/")
        entries.append((depth, name.rstrip("/"), is_dir))
    return entries


class TestReleaseHighlights:
    """「近期版本」区块与 CHANGELOG 同步。"""

    def test_highlights_block_matches_changelog(self):
        rendered = sync_readme.sync(REPO, sync_readme.DEFAULT_LIMIT)
        for name, text in rendered.items():
            current = (REPO / name).read_text(encoding="utf-8")
            assert current == text, "{0} 的近期版本区块与 CHANGELOG 不同步（运行 scripts/sync_readme.py --write）".format(name)

    def test_highlights_block_is_bounded(self):
        """区块只保留最近 N 个版本，不会随发版无限增长。"""
        text = (REPO / "README.md").read_text(encoding="utf-8")
        block = text.split(sync_readme.START, 1)[1].split(sync_readme.END, 1)[0]
        rows = [line for line in block.splitlines() if line.startswith("| **v")]
        assert 1 <= len(rows) <= sync_readme.DEFAULT_LIMIT

    def test_changelog_parser_finds_versions(self):
        sections = sync_readme.parse_changelog((REPO / "CHANGELOG.md").read_text(encoding="utf-8"))
        assert len(sections) >= 10
        assert all(highlight for _v, _d, highlight in sections[:3])


class TestEnvVarTable:
    """环境变量表与代码一致（两个方向）。"""

    @staticmethod
    def _code_env_vars():
        """代码实际读取的环境变量：os.environ.get("X") 与常量赋值 X_ENV = "X"。"""
        found = set()
        for path in sorted((REPO / "scripts").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            found.update(re.findall(r"os\.environ(?:\.get)?\(?\s*[\"']([A-Z][A-Z0-9_]{3,})[\"']", text))
            found.update(re.findall(r"(?m)^\s*[A-Z][A-Z0-9_]*\s*=\s*[\"']([A-Z][A-Z0-9_]{3,})[\"']", text))
        return found - RETIRED_ENV_VARS

    @staticmethod
    def _readme_table_vars(name):
        text = (REPO / name).read_text(encoding="utf-8")
        return set(re.findall(r"^\|\s*`([A-Z][A-Z0-9_]+)`\s*\|", text, re.M))

    def test_table_vars_are_read_by_code(self):
        code_vars = self._code_env_vars()
        for name in ("README.md", "README_EN.md"):
            stale = self._readme_table_vars(name) - code_vars
            assert not stale, "{0} 列了代码不再读取的环境变量: {1}".format(name, sorted(stale))

    def test_code_vars_are_documented(self):
        code_vars = self._code_env_vars()
        for name in ("README.md", "README_EN.md"):
            text = (REPO / name).read_text(encoding="utf-8")
            missing = sorted(v for v in code_vars if v not in text)
            assert not missing, "{0} 未说明代码读取的环境变量: {1}".format(name, missing)


class TestSkillTree:
    """SKILL.md 目录树里的路径必须真实存在。"""

    def test_tree_paths_exist(self):
        text = (REPO / "SKILL.md").read_text(encoding="utf-8")
        entries = _tree_entries(text)
        assert len(entries) > 20, "目录树解析异常"
        stack = {}
        missing = []
        for depth, name, is_dir in entries:
            if is_dir:
                stack[depth] = name
                for deeper in [d for d in stack if d > depth]:
                    del stack[deeper]
                continue
            prefixes = [stack[d] for d in sorted(stack) if d < depth]
            for part in [p for p in name.split(" / ") if p]:
                candidate = "/".join(prefixes + [part])
                if not (REPO / candidate).exists():
                    missing.append(candidate)
        assert not missing, "目录树中的路径不存在: {0}".format(missing)


class TestToolLists:
    """README 工具清单与 references/tools.md 一致。"""

    @staticmethod
    def _readme_tools():
        text = (REPO / "README.md").read_text(encoding="utf-8")
        start = text.find("## 工具能力总览")
        end = text.find("\n## ", start + 1)
        section = text[start:end if end > 0 else len(text)]
        return set(re.findall(r"`([a-z][a-z0-9-]{4,})`", section))

    @staticmethod
    def _tools_doc():
        text = (REPO / "references" / "tools.md").read_text(encoding="utf-8")
        return set(re.findall(r"^\|\s*`([a-z][a-z0-9-]{4,})`\s*\|", text, re.M))

    def test_readme_and_tools_doc_agree(self):
        readme_tools = self._readme_tools()
        doc_tools = self._tools_doc()
        assert readme_tools, "README 未解析到工具清单"
        assert readme_tools == doc_tools, "工具清单不一致：README 独有 {0}；tools.md 独有 {1}".format(
            sorted(readme_tools - doc_tools), sorted(doc_tools - readme_tools))

    def test_tool_count_matches_documented_number(self):
        assert len(self._tools_doc()) == 35


class TestRelativeLinks:
    """Markdown 相对链接可达。"""

    def test_no_dead_relative_links(self):
        dead = []
        for path in _md_files():
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
                link = match.group(1)
                if link.startswith(("http://", "https://", "mailto:")):
                    continue
                if not (path.parent / link).exists():
                    dead.append("{0} -> {1}".format(path.relative_to(REPO).as_posix(), link))
        assert not dead, "存在死链: {0}".format(dead)


class TestDemoSampleCounts:
    """试算页示例数据条数与 README 表述一致。"""

    @staticmethod
    def _count(marker):
        """统计 JS 数组的顶层元素个数（正确处理尾逗号）。"""
        html = (REPO / "docs" / "demo.html").read_text(encoding="utf-8")
        i = html.find(marker)
        j = html.find("[", i)
        depth, in_str, esc, commas, last = 0, False, False, 0, ""
        for k in range(j, len(html)):
            ch = html[k]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
                if depth == 0:
                    return commas if last == "," else commas + 1
            elif ch == "," and depth == 1:
                commas += 1
            if not ch.isspace():
                last = ch
        return commas

    def test_readme_states_actual_counts(self):
        menu = self._count("let MENU = [")
        coupons = self._count("const COUPONS = [")
        deals = self._count("const DEALS = [")
        text = (REPO / "README.md").read_text(encoding="utf-8")
        assert "{0} 项菜单".format(menu) in text, "README 未写明菜单条数 {0}".format(menu)
        assert "{0} 张券".format(coupons) in text, "README 未写明券条数 {0}".format(coupons)
        assert "{0} 条团购".format(deals) in text, "README 未写明团购条数 {0}".format(deals)
