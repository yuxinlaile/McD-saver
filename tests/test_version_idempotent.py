"""版本递增的重复执行保护（2026-10-21）。

某些执行环境会把同一条命令跑两次（重试 / 双写）。此前 `version.py --apply`
会被连跳两位、留下空档版本号。本文件锁定「待发布标记」的幂等行为：
同一版本未打 tag 之前，重复执行只跳一格。
"""
from pathlib import Path

import pytest

import version

BASE = "2.3.3"


def _make_repo(root: Path) -> None:
    """构造一个最小可递增仓库（五件套 + 空 CHANGELOG）。"""
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "mcd_client.py").write_text(
        'CLIENT_INFO = {"name": "mcd-saver", "version": "%s"}\nUSER_AGENT = "mcd-saver/%s"\n' % (BASE, BASE),
        encoding="utf-8")
    (root / "pyproject.toml").write_text('version = "%s"\n' % BASE, encoding="utf-8")
    (root / "SKILL.md").write_text("---\nname: mcd-saver\nversion: %s\n---\n" % BASE, encoding="utf-8")
    for name in ("README.md", "README_EN.md"):
        (root / name).write_text(
            "Release-v{0}-9a3412 releases/tag/v{0}\n当前版本 **v{0}**\nCurrent version **v{0}**\n".format(BASE),
            encoding="utf-8")
    (root / "CHANGELOG.md").write_text("# 变更记录\n\n## [%s] - 2026-10-21\n\n- 初始\n" % BASE, encoding="utf-8")


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    _make_repo(tmp_path)
    monkeypatch.setattr(version, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(version, "PENDING_MARKER", tmp_path / ".git" / "RELEASE_PENDING")
    monkeypatch.setattr(version, "released_tag_exists", lambda v: False)
    return tmp_path


class TestIdempotentApply:
    """未发版前的重复执行不得再次递增。"""

    def test_second_apply_is_skipped(self, repo):
        assert version.main(["--apply"]) == 0
        first = version.current_repo_version()
        assert first == "2.4.0", "2.3.3 的修订号已达上限，应进位到 2.4.0"

        # 模拟同一条命令被执行第二次
        assert version.main(["--apply"]) == 0
        assert version.current_repo_version() == first, "重复执行不应再次递增"

    def test_pending_marker_written(self, repo):
        version.main(["--apply"])
        assert (repo / ".git" / "RELEASE_PENDING").read_text(encoding="utf-8").strip() == "2.4.0"

    def test_force_allows_next_bump(self, repo):
        version.main(["--apply"])
        assert version.main(["--apply", "--force"]) == 0
        assert version.current_repo_version() == "2.4.1"

    def test_after_release_bump_continues(self, repo, monkeypatch):
        version.main(["--apply"])
        assert version.current_repo_version() == "2.4.0"
        # 模拟 2.4.0 已发版（存在 tag）
        monkeypatch.setattr(version, "released_tag_exists", lambda v: v == "2.4.0")
        assert version.main(["--apply"]) == 0
        assert version.current_repo_version() == "2.4.1"

    def test_explicit_version_argument_bypasses_marker(self, repo):
        """显式传入版本号（对历史版本推算）时不做幂等拦截。"""
        assert version.main(["1.6.3", "--apply"]) == 0
        assert version.current_repo_version() == "2.0.0"


class TestPendingHelpers:
    """标记读写与清理。"""

    def test_clear_pending(self, repo):
        version.mark_pending("9.9.9")
        assert version.pending_version() == "9.9.9"
        version.clear_pending()
        assert version.pending_version() == ""

    def test_missing_marker_reads_empty(self, repo):
        assert version.pending_version() == ""
