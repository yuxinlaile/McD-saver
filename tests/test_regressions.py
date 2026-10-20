"""2026-10-20 全仓巡检的回归测试：锁定五处真实缺陷与缺口。

1. verify_run 传 ``date`` 而非 ``datetime`` → analyze_coupons/analyze_orders 崩溃；
2. ``_unwrap`` 不支持 ``{"data": {"list": [...]}}`` → 真实响应被静默丢成空列表；
3. ``_unwrap`` 把 content 壳里的中文空态文案当成一条记录；
4. ``silent_cost report`` 缺文件时抛裸 traceback（Agent 拿到的是栈，不是错误提示）；
5. ``deal_compare clear`` 未确认时返回成功码；``compare_deals`` 抛 SystemExit 会终止宿主进程。
"""
import json
import os
import tempfile
from datetime import datetime

import pytest

import deal_compare
import silent_cost
from silent_cost import _unwrap, analyze_coupons, analyze_orders

TODAY = datetime(2026, 10, 12)
ONE_COUPON = {"data": [{"title": "满50减12", "parValue": 12.0,
                        "validityEndTime": "2026-10-13 23:59:59"}]}
ONE_ORDER = {"data": [{"createTime": "2026-09-02", "totalAmount": 33.5,
                       "items": [{"name": "麦辣鸡腿堡", "quantity": 1}]}]}


class TestUnwrapShapes:
    """真实 MCP 响应形态的解包（巡检 P0-2）。"""

    def test_nested_list_payload(self):
        raw = {"data": {"list": [{"couponId": "C1", "parValue": 12.0}]}}
        assert _unwrap(raw) == [{"couponId": "C1", "parValue": 12.0}]

    def test_markdown_wrapped_json(self):
        text = ("## 字段说明\n...\n\n## Original Response\n"
                '{"code":0,"data":{"list":[{"couponId":"C2"}]}}')
        raw = {"content": [{"type": "text", "text": text}]}
        assert _unwrap(raw) == [{"couponId": "C2"}]

    def test_empty_chinese_text_is_not_a_record(self):
        raw = {"content": [{"type": "text", "text": "暂无可用优惠券"}]}
        assert _unwrap(raw) == []

    def test_content_shell_with_json_text(self):
        raw = {"content": [{"type": "text", "text": json.dumps({"data": [{"couponId": "C3"}]})}]}
        assert _unwrap(raw) == [{"couponId": "C3"}]


class TestDatetimeContract:
    """analyze_* 统一以 datetime 为契约（巡检 P0-1）。"""

    def test_coupons_accept_datetime(self):
        result = analyze_coupons(ONE_COUPON, TODAY)
        assert result["total"] == 1
        assert result["expiring"][0]["days"] == 1

    def test_orders_accept_datetime(self):
        result = analyze_orders(ONE_ORDER, TODAY)
        assert result["order_count"] == 1


class TestCliErrorPaths:
    """错误路径必须给中文提示与正确退出码（巡检 P0-3 与 P2）。"""

    def test_report_missing_file_returns_usage_exit(self, capsys):
        missing = os.path.join(tempfile.gettempdir(), "mcd_missing_input_xyz.json")
        code = silent_cost.main(["report", "--coupons", missing])
        assert code == silent_cost.EXIT_USAGE
        assert "错误" in capsys.readouterr().err

    def test_clear_without_confirmation_is_not_success(self, tmp_path):
        lib = str(tmp_path / "deals.json")
        assert deal_compare.main(["--file", lib, "clear"]) == deal_compare.EXIT_USAGE

    def test_compare_deals_raises_value_error_not_system_exit(self):
        with pytest.raises(ValueError):
            deal_compare.compare_deals([], mcd_face=0, mcd_price=10.0)
