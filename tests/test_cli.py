"""CLI 端到端冒烟测试（不发起网络请求）。"""
import os
import subprocess
import sys

SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))


def _run(script, args, env_extra=None):
    env = os.environ.copy()
    # 确保用例不依赖真实 Token 与本机 Token 文件
    env["MCD_MCP_TOKEN"] = ""
    env["MCD_MCP_TOKEN_FILE"] = os.path.join(SCRIPTS, "__nonexistent_token__")
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, os.path.join(SCRIPTS, script)] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


class TestMcdCli:
    def test_help_ok(self):
        result = _run("mcd.py", ["--help"])
        assert result.returncode == 0
        assert "麦麦省钱助手" in result.stdout

    def test_missing_token_exits_2(self):
        result = _run("mcd.py", ["check"])
        assert result.returncode == 2
        assert "鉴权错误" in result.stderr

    def test_invalid_args_json_exits(self):
        result = _run("mcd.py", ["call", "query-meals", "--args", "not-json"])
        assert result.returncode != 0

    def test_call_requires_tool_name(self):
        result = _run("mcd.py", ["call"])
        assert result.returncode != 0


class TestDealCompareCli:
    def test_compare_empty_library_exits_2(self, tmp_path):
        deals_file = tmp_path / "deals.json"
        deals_file.write_text("[]", encoding="utf-8")
        result = _run(
            "deal_compare.py",
            ["compare", "--mcd-face", "48.5", "--mcd-price", "38.5"],
            {"MCD_DEALS_FILE": str(deals_file)},
        )
        assert result.returncode == 2

    def test_full_flow_add_list_compare(self, tmp_path):
        deals_file = tmp_path / "deals.json"
        env = {"MCD_DEALS_FILE": str(deals_file)}

        added = _run(
            "deal_compare.py",
            [
                "add", "--platform", "meituan", "--title", "满40减14代金券",
                "--price", "25.9", "--face", "40", "--channel", "store",
                "--time", "limited", "--valid-until", "2026-11-30",
            ],
            env,
        )
        assert added.returncode == 0

        listed = _run("deal_compare.py", ["list"], env)
        assert listed.returncode == 0
        assert "满40减14代金券" in listed.stdout

        report = _run(
            "deal_compare.py",
            ["compare", "--mcd-face", "48.5", "--mcd-price", "38.5"],
            env,
        )
        assert report.returncode == 0
        assert "推荐决策" in report.stdout
        assert "¥31.40" in report.stdout  # 48.5 × 25.9 / 40

    def test_remove_unknown_id_exits_1(self, tmp_path):
        env = {"MCD_DEALS_FILE": str(tmp_path / "deals.json")}
        result = _run("deal_compare.py", ["remove", "zzzzzz"], env)
        assert result.returncode == 1


class TestClaimFlow:
    """claim 子命令：一次性领券（展示清单 → 确认 → 领取）。"""

    class FakeClient:
        def __init__(self, listing):
            self.listing = listing
            self.calls = []

        def call_tool(self, name, arguments=None):
            self.calls.append(name)
            if name == "available-coupons":
                return {"content": [{"type": "text", "text": self.listing}]}
            if name == "auto-bind-coupons":
                return {"content": [{"type": "text", "text": "已成功领取 2 张"}]}
            return {}

    LISTING = "- 满30减5\n- 免费麦乐鸡(5块)"

    def test_yes_claims_directly(self, capsys):
        from mcd import run_claim
        client = self.FakeClient(self.LISTING)
        assert run_claim(client, yes=True) == 0
        assert client.calls == ["available-coupons", "auto-bind-coupons"]
        assert "已成功领取 2 张" in capsys.readouterr().out

    def test_confirm_y_claims(self, capsys):
        from mcd import run_claim
        client = self.FakeClient(self.LISTING)
        assert run_claim(client, yes=False, confirm_fn=lambda _: "y") == 0
        assert client.calls == ["available-coupons", "auto-bind-coupons"]

    def test_confirm_n_aborts(self, capsys):
        from mcd import run_claim
        client = self.FakeClient(self.LISTING)
        assert run_claim(client, yes=False, confirm_fn=lambda _: "n") == 0
        assert client.calls == ["available-coupons"]  # 未执行领取
        assert "已取消" in capsys.readouterr().out

    def test_empty_listing_skips_claim(self, capsys):
        from mcd import run_claim
        client = self.FakeClient("暂无可领取的优惠券")
        assert run_claim(client, yes=True) == 0
        assert client.calls == ["available-coupons"]
        assert "暂无可领取" in capsys.readouterr().out

    def test_uppercase_y_also_confirms(self):
        from mcd import run_claim
        client = self.FakeClient(self.LISTING)
        assert run_claim(client, yes=False, confirm_fn=lambda _: "YES") == 0
        assert client.calls == ["available-coupons", "auto-bind-coupons"]
