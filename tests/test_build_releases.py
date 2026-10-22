#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布产物工具（scripts/build_releases.py）单元测试。

覆盖命名规则、CHANGELOG 抽取、说明渲染、索引生成与产物校验，
不依赖 git tag 与网络（CI 浅克隆下也可运行）。
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_releases as br  # noqa: E402


class TestNaming:
    def test_package_and_doc_names(self):
        assert br.pkg_name("2.1.3") == "mcd-saver-v2.1.3.zip"
        assert br.doc_name("2.1.3") == "麦麦省钱助手-v2.1.3-发布说明.md"
        assert br.doc_asset_name("2.1.3") == "mcd-saver-v2.1.3-release-notes-zh.md"

    def test_version_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br, "RELEASES_DIR", tmp_path)
        assert br.version_dir("1.2.0") == tmp_path / "v1.2.0"

    def test_sort_key(self):
        versions = ["1.2.0", "2.1.3", "1.7.4", "2.0.0"]
        assert sorted(versions, key=br.sort_key) == ["1.2.0", "1.7.4", "2.0.0", "2.1.3"]


class TestChangelogSection:
    def test_extracts_version_and_date(self):
        body, date = br.changelog_section("2.1.3")
        assert date == "2026-10-19"
        assert "### 改进" in body
        assert "2.1.2" not in body  # 只取本版本段落，不串到下一版

    def test_missing_version_raises(self):
        with pytest.raises(RuntimeError):
            br.changelog_section("9.9.9")


class TestRenderDoc:
    def test_contains_required_fields(self):
        text = br.render_doc("2.1.3", "2026-10-19", "### 改进\n\n- 测试条目\n", "abc123")
        assert "v2.1.3" in text
        assert "mcd-saver-v2.1.3.zip" in text
        assert "abc123" in text
        assert "## 安装" in text and "## 版本变更" in text and "## 校验" in text
        assert "测试条目" in text


class TestIndexAndVerify:
    @staticmethod
    def _make_pair(root: Path, version: str, valid_zip: bool = True) -> None:
        folder = root / "v{0}".format(version)
        folder.mkdir(parents=True)
        (folder / br.doc_name(version)).write_text(
            "# 麦麦省钱助手 v{0} 发布说明\n\n| 发布日期 | 2026-10-19 |\n| SHA-256 | `deadbeef` |\n".format(version),
            encoding="utf-8")
        if valid_zip:
            with zipfile.ZipFile(folder / br.pkg_name(version), "w") as zf:
                zf.writestr("McD-Saver-v{0}/SKILL.md".format(version), "x")

    def test_index_lists_versions(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br, "RELEASES_DIR", tmp_path)
        self._make_pair(tmp_path, "1.2.0")
        self._make_pair(tmp_path, "2.1.3")
        out = br.build_index(["2.1.3", "1.2.0"])
        text = out.read_text(encoding="utf-8")
        assert "v2.1.3" in text and "v1.2.0" in text
        assert "(v2.1.3/" in text
        assert "mcd-saver-v<版本>.zip" in text

    def test_verify_passes_on_complete_set(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br, "RELEASES_DIR", tmp_path)
        self._make_pair(tmp_path, "2.1.3")
        br.build_index(["2.1.3"])
        # 说明中的校验和需与真实 zip 匹配
        doc = tmp_path / "v2.1.3" / br.doc_name("2.1.3")
        checksum = br.sha256_of(tmp_path / "v2.1.3" / br.pkg_name("2.1.3"))
        doc.write_text(doc.read_text(encoding="utf-8").replace("deadbeef", checksum), encoding="utf-8")
        assert br.verify(verbose=False) == []

    def test_verify_flags_missing_doc(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br, "RELEASES_DIR", tmp_path)
        self._make_pair(tmp_path, "2.1.3")
        (tmp_path / "v2.1.3" / br.doc_name("2.1.3")).unlink()
        problems = br.verify(verbose=False)
        assert any("缺少中文说明" in p for p in problems)

    def test_verify_without_zip_check_tolerates_missing_package(self, tmp_path, monkeypatch):
        """CI 浅克隆里没有 zip（不入库），--no-zip-check 只校验说明与索引。"""
        monkeypatch.setattr(br, "RELEASES_DIR", tmp_path)
        self._make_pair(tmp_path, "2.1.3", valid_zip=False)
        br.build_index(["2.1.3"])
        assert br.verify(verbose=False, require_zip=False) == []
        assert any("缺少英文压缩包" in p for p in br.verify(verbose=False))

    def test_verify_flags_bad_directory_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br, "RELEASES_DIR", tmp_path)
        (tmp_path / "release-1").mkdir()
        problems = br.verify(verbose=False)
        assert any("目录命名不符合" in p for p in problems)

    def test_verify_flags_extra_artifact(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br, "RELEASES_DIR", tmp_path)
        self._make_pair(tmp_path, "2.1.3")
        (tmp_path / "v2.1.3" / "debug.log").write_text("x", encoding="utf-8")
        problems = br.verify(verbose=False)
        assert any("多余产物" in p for p in problems)
