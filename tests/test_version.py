"""version.py 自定义版本递增规则测试（z.x.y：y≤3、x≤6）。

规则：每次发布先递增 y；y>3 进位到 x+1 并 y=0；x>6 进位到 z+1 并 x、y 归零。
历史过渡版本（分量超限，如 1.7.4）按归一化处理：归一化结果即下一版本。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from version import VersionError, next_version, normalize, parse_version


class TestParse:
    def test_valid_versions(self):
        assert parse_version("0.0.0") == (0, 0, 0)
        assert parse_version("1.6.3") == (1, 6, 3)
        assert parse_version(" 2.0.0 ") == (2, 0, 0)  # 允许首尾空白

    @pytest.mark.parametrize("bad", ["", "abc", "1.2", "1.2.3.4", "-1.0.0",
                                     "1.-2.3", "1.2.-3", "v1.0.0", "1.2.x", "1..3"])
    def test_invalid_inputs_raise(self, bad):
        with pytest.raises(VersionError):
            parse_version(bad)


class TestNormalize:
    def test_legal_version_unchanged(self):
        assert normalize((1, 6, 3)) == (1, 6, 3)
        assert normalize((2, 0, 0)) == (2, 0, 0)

    def test_patch_overflow_carries_to_minor(self):
        assert normalize((1, 5, 4)) == (1, 6, 0)   # y=4 → x+1, y 重置 0
        assert normalize((1, 5, 7)) == (1, 6, 0)   # y=7 超限 → x+1, y 重置 0

    def test_minor_overflow_carries_to_major(self):
        assert normalize((1, 7, 0)) == (2, 0, 0)   # x=7 → z+1
        assert normalize((1, 7, 4)) == (2, 0, 0)   # 双重进位

    def test_zero_boundary(self):
        assert normalize((0, 0, 0)) == (0, 0, 0)


class TestNextVersion:
    @pytest.mark.parametrize("current,expected", [
        ("0.0.0", "0.0.1"),      # 最小版本起步：正常递增 y
        ("1.0.0", "1.0.1"),
        ("1.0.3", "1.1.0"),      # y=3 达上限 → 进位 x
        ("1.5.3", "1.6.0"),      # 用户示例 1
        ("1.6.0", "1.6.1"),
        ("1.6.2", "1.6.3"),
        ("1.6.3", "2.0.0"),      # 用户示例 2：y 与 x 双进位
        ("0.6.3", "1.0.0"),      # z 进位从 0 起步
        ("2.0.0", "2.0.1"),      # 新格式起点正常递增
        ("2.6.3", "3.0.0"),      # 任意 z 均按同一规则
    ])
    def test_rule_table(self, current, expected):
        assert next_version(current) == expected

    def test_transition_version_normalizes_to_next(self):
        # 1.7.4 为历史过渡版本（y=4 超限）：归一化即得下一版本 2.0.0
        assert next_version("1.7.4") == "2.0.0"

    @pytest.mark.parametrize("bad", ["", "abc", "1.2", "1.2.3.4", "1.2.-3"])
    def test_invalid_input_raises(self, bad):
        with pytest.raises(VersionError):
            next_version(bad)

    def test_result_always_in_range(self):
        # 任意合法输入的输出必满足 y≤3、x≤6
        for z in range(3):
            for x in range(8):        # 故意包含 x>6 的过渡输入
                for y in range(5):    # 故意包含 y>3 的过渡输入
                    out = next_version(f"{z}.{x}.{y}")
                    oz, ox, oy = parse_version(out)
                    assert oy <= 3 and ox <= 6


class TestApplyVersion:
    """v2.1.2 新增：apply_version 文件同步（tmp 仓库结构 + pyproject 覆盖）。"""

    def _make_repo(self, tmp_path):
        import io as _io
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "mcd_client.py").write_text(
            'CLIENT_INFO = {"name": "m", "version": "2.1.1"}\nUA = "maimai-saver/2.1.1"\n', encoding="utf-8")
        (tmp_path / "SKILL.md").write_text("version: 2.1.1\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "Release-v2.1.1-9a3412 x releases/tag/v2.1.1 当前版本 **v2.1.1**\n", encoding="utf-8")
        (tmp_path / "README_EN.md").write_text(
            "Release-v2.1.1-9a3412 releases/tag/v2.1.1 Current version **v2.1.1**\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text('version = "2.1.1"\n', encoding="utf-8")

    def test_apply_updates_all_files(self, tmp_path, monkeypatch):
        import version as vmod
        self._make_repo(tmp_path)
        monkeypatch.setattr(vmod, "REPO_ROOT", tmp_path)
        updated = vmod.apply_version("2.1.2")
        assert "scripts/mcd_client.py" in updated
        assert "pyproject.toml" in updated
        cc = (tmp_path / "scripts" / "mcd_client.py").read_text(encoding="utf-8")
        assert "2.1.2" in cc and "2.1.1" not in cc
        pp = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
        assert 'version = "2.1.2"' in pp
        rd = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "当前版本 **v2.1.2**" in rd and "Release-v2.1.2" in rd

    def test_apply_rejects_out_of_range(self, tmp_path, monkeypatch):
        import version as vmod
        self._make_repo(tmp_path)
        monkeypatch.setattr(vmod, "REPO_ROOT", tmp_path)
        with pytest.raises(VersionError):
            vmod.apply_version("2.8.0")   # 次版本 8 超上限 6

    def test_current_repo_version_reads_client_info(self, tmp_path, monkeypatch):
        import version as vmod
        self._make_repo(tmp_path)
        monkeypatch.setattr(vmod, "REPO_ROOT", tmp_path)
        assert vmod.current_repo_version() == "2.1.1"

    def test_main_dry_run_prints_next_version(self, capsys):
        import version as vmod
        assert vmod.main(["2.1.3"]) == 0
        assert "2.1.3 → 2.2.0" in capsys.readouterr().out

    def test_main_apply_prints_release_steps(self, tmp_path, monkeypatch, capsys):
        """--apply 收尾提示曾因未定义变量抛 NameError，此处锁定退出码与输出。"""
        import version as vmod
        self._make_repo(tmp_path)
        monkeypatch.setattr(vmod, "REPO_ROOT", tmp_path)
        assert vmod.main(["--apply"]) == 0
        out = capsys.readouterr().out
        assert "2.1.1 → 2.1.2" in out
        assert "gh release upload v2.1.2" in out
