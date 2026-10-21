"""品牌改名后的回归测试（2026-10-21）。

仓库已从 `maimai-saver` 更名为 `McD-saver`（包名 `mcd-saver`）。本文件锁定：
1. 当前身份字段（包名 / 技能名 / 客户端 UA）不再使用旧名；
2. 旧环境变量仍被兼容（不破坏用户既有配置），但新变量优先；
3. 旧名不得再出现在「当前身份字段」中（历史记录 CHANGELOG/workbuddy.md 除外）。
"""
import re
from pathlib import Path

import deal_compare
from mcd_client import CLIENT_INFO, USER_AGENT

REPO = Path(__file__).resolve().parent.parent
OLD_NAME = "maimai-saver"
OLD_BRAND = re.compile(r"maimai[-_]saver", re.IGNORECASE)
# 这些文件记录历史事实（改名过程），允许出现旧名
HISTORY_FILES = {"CHANGELOG.md", "workbuddy.md", "tests/test_brand_rename.py"}


class TestBrandIdentity:
    """当前身份字段。"""

    def test_client_info_uses_new_name(self):
        assert CLIENT_INFO["name"] == "mcd-saver"
        assert USER_AGENT.startswith("mcd-saver/")

    def test_package_name_uses_new_name(self):
        text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        assert 'name = "mcd-saver"' in text
        assert OLD_NAME not in text

    def test_skill_frontmatter_uses_new_name(self):
        text = (REPO / "SKILL.md").read_text(encoding="utf-8")
        assert re.search(r"^name:\s*mcd-saver\s*$", text, re.M)

    def test_no_old_brand_in_live_files(self):
        """当前身份字段中不应再出现旧品牌名（历史记录除外）。"""
        offenders = []
        for path in REPO.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".toml", ".html", ".ps1", ".yml"}:
                continue
            rel = path.relative_to(REPO).as_posix()
            if rel in HISTORY_FILES or rel.startswith("releases/") or rel.startswith(".git/"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            # 兼容期内允许的旧环境变量名（MAIMAI_DEALS_FILE / MAIMAI_DATA_DIR）
            cleaned = text.replace("MAIMAI_DEALS_FILE", "").replace("MAIMAI_DATA_DIR", "")
            if OLD_BRAND.search(cleaned):
                offenders.append(rel)
        assert not offenders, "仍有旧品牌名：{0}".format(offenders)


class TestEnvVarCompatibility:
    """新旧环境变量并存：新名优先，旧名仍被兼容。"""

    def test_new_env_var_is_primary(self, monkeypatch, tmp_path):
        new_target = tmp_path / "new.json"
        monkeypatch.setenv("MCD_DEALS_FILE", str(new_target))
        monkeypatch.setenv("MAIMAI_DEALS_FILE", str(tmp_path / "old.json"))
        args = deal_compare.build_parser().parse_args(["list"])
        assert args.file == str(new_target)

    def test_legacy_env_var_still_works(self, monkeypatch, tmp_path):
        old_target = tmp_path / "old.json"
        monkeypatch.delenv("MCD_DEALS_FILE", raising=False)
        monkeypatch.setenv("MAIMAI_DEALS_FILE", str(old_target))
        args = deal_compare.build_parser().parse_args(["list"])
        assert args.file == str(old_target)

    def test_default_data_dir_uses_new_name(self, monkeypatch):
        monkeypatch.delenv("MCD_DATA_DIR", raising=False)
        monkeypatch.delenv("MAIMAI_DATA_DIR", raising=False)
        assert ".mcd_saver" in deal_compare.DEFAULT_DEALS_FILE
