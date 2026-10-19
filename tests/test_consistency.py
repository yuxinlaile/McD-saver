#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库规范一致性校验（v2.2 新增）。

把这些年反复手工检查、又反复漏掉的约定固化成断言：

- 版本号五处一致（CLIENT_INFO / pyproject / SKILL frontmatter / README 中英徽章与「当前版本」句）
- 测试计数四处一致（README 中英徽章、banner、SKILL 目录树）
- CHANGELOG 无重复版本条目，且顶部版本等于当前版本
- 两份 MCP 配置示例内容完全一致（参赛要求文件 vs 目录模板）
- releases/ 产物两件套命名与索引配对
- scripts/ 下每个脚本都出现在 SKILL 目录树中

这些断言不依赖 git 历史与网络，可在 CI 的浅克隆下直接运行。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def client_version() -> str:
    match = re.search(r'"version":\s*"(\d+\.\d+\.\d+)"', read("scripts/mcd_client.py"))
    assert match, "CLIENT_INFO 中找不到 version 字段"
    return match.group(1)


class TestVersionConsistency:
    """版本号必须五处一致——历史上多次出现只改一处的情况。"""

    def test_pyproject_matches_client_info(self):
        match = re.search(r'^version = "(\d+\.\d+\.\d+)"$', read("pyproject.toml"), re.M)
        assert match, "pyproject.toml 缺少 version 字段"
        assert match.group(1) == client_version()

    def test_skill_frontmatter_matches(self):
        match = re.search(r"^version:\s*(\d+\.\d+\.\d+)$", read("SKILL.md"), re.M)
        assert match, "SKILL.md frontmatter 缺少 version"
        assert match.group(1) == client_version()

    def test_readme_badges_match(self):
        version = client_version()
        for name in ("README.md", "README_EN.md"):
            badge = re.search(r"Release-v(\d+\.\d+\.\d+)-", read(name))
            assert badge, "{0} 缺少 Release 徽章".format(name)
            assert badge.group(1) == version, "{0} 徽章版本滞后".format(name)

    def test_readme_current_version_sentence_matches(self):
        version = client_version()
        assert "当前版本 **v{0}**".format(version) in read("README.md")
        assert "Current version **v{0}**".format(version) in read("README_EN.md")


class TestTestCountConsistency:
    """测试计数四处一致（README 中英 / banner / SKILL）。"""

    def test_counts_are_equal_everywhere(self):
        version = client_version()  # 仅为触发一次读取，失败信息更直观
        zh = re.findall(r"Tests-(\d+)%20passed", read("README.md"))
        en = re.findall(r"Tests-(\d+)%20passed", read("README_EN.md"))
        banner = re.findall(r"(\d+) unit tests", read("docs/assets/banner.svg"))
        skill = re.findall(r"（(\d+) 个用例", read("SKILL.md"))
        readme_body = re.findall(r"(\d+) 个单元测试", read("README.md"))
        assert zh and en and banner and skill, (
            "计数提取失败: zh={0} en={1} banner={2} skill={3}".format(zh, en, banner, skill))
        values = set(zh) | set(en) | set(banner) | set(skill) | set(readme_body)
        assert len(values) == 1, "测试计数不一致：{0}（当前版本 {1}）".format(sorted(values), version)
        assert int(values.pop()) >= 150, "测试数量异常偏低，疑似误改"


class TestChangelog:
    """CHANGELOG 结构与版本对齐。"""

    def test_no_duplicate_version_sections(self):
        headings = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", read("CHANGELOG.md"), re.M)
        duplicates = {v for v in headings if headings.count(v) > 1}
        assert not duplicates, "CHANGELOG 存在重复版本条目：{0}".format(sorted(duplicates))

    def test_top_section_is_current_version(self):
        headings = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", read("CHANGELOG.md"), re.M)
        assert headings, "CHANGELOG 缺少版本条目"
        assert headings[0] == client_version(), (
            "CHANGELOG 顶部版本 {0} 与当前版本 {1} 不一致".format(headings[0], client_version()))
        assert headings == sorted(headings, key=lambda v: tuple(int(x) for x in v.split(".")), reverse=True), \
            "CHANGELOG 版本未按从新到旧排列"


class TestConfigExamples:
    """两份配置示例必须完全一致（一份是参赛要求文件，一份是目录模板）。"""

    def test_root_and_config_examples_identical(self):
        root = read("mcp-config.example.json").strip()
        nested = read("config/mcp.example.json").strip()
        assert root == nested, "根目录与 config/ 下的 MCP 配置示例已漂移，请同步修改两份"

    def test_examples_contain_no_secret(self):
        for name in ("mcp-config.example.json", "config/mcp.example.json"):
            text = read(name)
            assert "${MCD_MCP_TOKEN}" in text, "{0} 应使用占位符而非真实 Token".format(name)
            assert not re.search(r"[A-Za-z0-9]{24,}", text.replace("${MCD_MCP_TOKEN}", "")), \
                "{0} 疑似包含真实凭据".format(name)


class TestReleaseArtifacts:
    """releases/ 目录的产物策略：每版两个文件、命名固定、索引齐全。"""

    def test_each_version_has_exactly_the_documented_doc(self):
        releases = ROOT / "releases"
        assert releases.is_dir(), "缺少 releases 目录"
        folders = [p for p in releases.iterdir() if p.is_dir()]
        assert folders, "releases 目录下没有版本目录"
        for folder in folders:
            match = re.match(r"^v(\d+\.\d+\.\d+)$", folder.name)
            assert match, "版本目录命名不符合 v<X.Y.Z>：{0}".format(folder.name)
            doc = folder / "麦麦省钱助手-v{0}-发布说明.md".format(match.group(1))
            assert doc.exists(), "v{0} 缺少中文发布说明".format(match.group(1))
            text = doc.read_text(encoding="utf-8")
            assert "v{0}".format(match.group(1)) in text
            assert "SHA-256" in text
            # 每个版本恰好两件产物：英文 zip（本地构建，不入库）+ 中文说明（入库）
            allowed = {doc.name, "mcd-saver-v{0}.zip".format(match.group(1))}
            loose = {p.name for p in folder.iterdir() if p.is_file()}
            assert loose <= allowed, "v{0} 出现两件套之外的产物：{1}".format(
                match.group(1), sorted(loose - allowed))

    def test_index_lists_every_version_folder(self):
        index = read("releases/README.md")
        folders = [p.name for p in (ROOT / "releases").iterdir() if p.is_dir()]
        missing = [name for name in folders if "({0}/".format(name) not in index and name[1:] not in index]
        assert not missing, "releases 索引缺少版本：{0}".format(sorted(missing))
        assert "mcd-saver-v<版本>.zip" in index and "麦麦省钱助手-v<版本>-发布说明.md" in index


class TestRepositoryLayout:
    """结构与文档对齐：脚本清单、README 章节。"""

    def test_skill_tree_lists_every_script(self):
        skill = read("SKILL.md")
        missing = [p.name for p in SCRIPTS.glob("*.py") if p.name not in skill]
        assert not missing, "SKILL.md 目录树缺少脚本：{0}".format(sorted(missing))

    def test_readme_has_structure_and_release_sections(self):
        zh = read("README.md")
        en = read("README_EN.md")
        assert "## 项目结构" in zh and "## 发布产物与版本策略" in zh
        assert "## Project layout" in en and "## Release artifacts" in en

    def test_no_python_files_at_repo_root_except_demo(self):
        strays = [p.name for p in ROOT.glob("*.py") if p.name != "demo.py"]
        assert not strays, "仓库根目录出现散落脚本：{0}".format(sorted(strays))


class TestDocumentationSync:
    """2026-10-19 审计漏项：目录漏章节、目录树漏文件、清单未链接。

    这三类问题此前完全靠人眼，现在全部变成断言。
    """

    def test_readme_toc_covers_every_section(self):
        """每个章节都必须出现在目录里（此前「反馈与支持」正文有、目录没有）。"""
        sys.path.insert(0, str(SCRIPTS))
        import check_toc

        assert check_toc.main([]) == 0

    def test_skill_tree_lists_every_reference(self):
        """references/ 下每份文档都要出现在 SKILL 目录树。"""
        skill = read("SKILL.md")
        missing = [p.name for p in (ROOT / "references").glob("*.md") if p.name not in skill]
        assert not missing, "SKILL.md 目录树缺少文档：{0}".format(sorted(missing))

    def test_skill_tree_lists_site_docs_and_tooling(self):
        skill = read("SKILL.md")
        expected = ["demo.html", "index.html", "sync-checklist.md",
                    "assets/banner.svg", "check_toc.py", "build_releases.py"]
        missing = [name for name in expected if name not in skill]
        assert not missing, "SKILL.md 目录树缺少：{0}".format(sorted(missing))

    def test_contributing_links_sync_checklist(self):
        assert "docs/sync-checklist.md" in read("CONTRIBUTING.md")

    def test_sync_checklist_records_known_misses(self):
        """清单必须保留审计出的漏项记录，避免「文档一改就丢历史」。"""
        text = read("docs/sync-checklist.md")
        for item in ("CHANGELOG", "SKILL.md 目录树", "README.md` 目录", "pyproject.toml", "releases/"):
            assert item.replace("`", "") in text.replace("`", ""), "清单缺少漏项：{0}".format(item)


class TestNeutralWording:
    """更新说明类文件不带来源表述（2026-10-19 规范，范围已收窄）。

    仅约束更新说明：CHANGELOG 与 releases/ 下的版本说明。
    README / SKILL / references / demo.html 等功能展示与介绍文档不受限制，
    可以按事实描述来源或致谢。
    """

    FORBIDDEN = ("借鉴", "致谢", "灵感", "参考")

    def _targets(self):
        files = [ROOT / "CHANGELOG.md"]
        files += sorted((ROOT / "releases").glob("v*/*.md"))
        return [f for f in files if f.exists()]

    def test_no_attribution_wording_in_release_notes(self):
        offenders = []
        for path in self._targets():
            text = path.read_text(encoding="utf-8")
            hits = [word for word in self.FORBIDDEN if word in text]
            if hits:
                offenders.append("{0}: {1}".format(path.relative_to(ROOT), "、".join(hits)))
        assert not offenders, "更新说明类文件仍含来源表述：{0}".format(offenders)

    def test_rule_scope_is_documented(self):
        checklist = read("docs/sync-checklist.md")
        assert "仅限「更新说明类」" in checklist
        assert "不受此限制" in checklist
