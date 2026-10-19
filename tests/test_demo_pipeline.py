"""demo.py 全链路离线演示回归测试——demo 即回归测试（复用 fixtures 数据）。

fixtures/*.json 的字段结构与真实 MCP 响应一致；demo.py 用同一套业务逻辑
跑四步检查，因此对 demo 输出的断言就是对业务流水线的断言。
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "fixtures")

REQUIRED_FIXTURES = [
    "available_coupons.json", "coupons.json", "menu.json",
    "orders.json", "points.json", "mall.json", "deals.json",
]


class TestFixtures:
    def test_all_fixtures_present_and_valid_json(self):
        for name in REQUIRED_FIXTURES:
            path = os.path.join(FIXTURES, name)
            assert os.path.exists(path), "缺少 fixtures/{0}".format(name)
            with open(path, "r", encoding="utf-8") as fh:
                json.load(fh)  # 能解析即合法

    def test_menu_fixture_matches_optimizer_schema(self):
        with open(os.path.join(FIXTURES, "menu.json"), "r", encoding="utf-8") as fh:
            menu = json.load(fh)
        assert isinstance(menu.get("items"), list) and menu["items"]
        for item in menu["items"]:
            assert "mealCode" in item and "price" in item


class TestDemoPipeline:
    """跑 python demo.py，对全链路关键输出断言。"""

    @classmethod
    def run_demo(cls, *args):
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, "demo.py"), *args],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )

    def test_demo_exits_zero(self):
        result = self.run_demo()
        assert result.returncode == 0, result.stderr

    def test_full_pipeline_key_sections(self):
        out = self.run_demo().stdout
        for section in ("【领券前置】", "【选券】", "【比价】", "【积分评估】",
                        "【沉默成本】", "【跨渠道】"):
            assert section in out, "缺少小节 {0}".format(section)

    def test_pricing_gap_is_real(self):
        # 比价段必须展示 套餐 33.5 vs 单点基准 43.5 的真实 gap
        out = self.run_demo("--section", "比价").stdout
        assert "¥43.50" in out and "¥33.50" in out and "省 ¥10.00" in out
        assert "改点套餐" in out

    def test_honest_unknown_coupons(self):
        # 菜单快照里没有的商品，价值必须标「无法判断」而不是编一个数
        out = self.run_demo("--section", "领券").stdout
        assert "【无法判断】" in out and "我们不猜" in out

    def test_silent_cost_schedule(self):
        out = self.run_demo("--section", "沉默成本").stdout
        assert "用券排程" in out and "注定过期" in out
        assert "可实现" in out

    def test_section_filter(self):
        out = self.run_demo("--section", "比价").stdout
        assert "【比价】" in out and "【领券前置】" not in out
