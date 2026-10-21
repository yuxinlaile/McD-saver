"""2026-10-21 安全与真实契约的回归测试。

覆盖本轮三件事：
1. **Token 不外泄**：非官方 MCP 地址默认被拒绝（只有显式 --allow-non-official-url 才放行）；
2. **带券核价的真实契约**：券必须同时给 couponId + couponCode，并挂在商品条目上
   （2026-10-21 实测：只给其一 → code 600010；挂顶层 → 券被静默忽略）；
3. **结构化载荷优先**：券的 couponId/couponCode 只存在于 MCP 响应的 structuredContent，
   文本 content 是给人看的 Markdown 表格；解析层必须优先读 structuredContent。
"""
import json

import pytest

import deal_compare
import silent_cost
from mcd_client import EndpointNotAllowedError, McdMcpClient, tool_json
from optimizer import Cart, make_mcp_pricer

COUPON_ID = "264B97DBE02BE6CF996AA6914151C4A9"
COUPON_CODE = "MCD6W9S051R001XX80Z40"


class _FakeClient:
    """记录调用参数并返回固定响应体的假客户端。"""

    def __init__(self, text="", structured=None):
        self.text = text
        self.structured = structured
        self.calls = []
        self._store_code = "1990232"
        self._order_type = 1
        self._be_type = 1

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        result = {}
        if self.text:
            result["content"] = [{"type": "text", "text": self.text}]
        if self.structured is not None:
            result["structuredContent"] = self.structured
        return result


class TestEndpointAllowlist:
    """Token 只能发往官方主机。"""

    def test_non_official_url_is_rejected(self):
        with pytest.raises(EndpointNotAllowedError):
            McdMcpClient(token="t", base_url="https://evil.example.com/mcp")

    def test_official_url_is_allowed(self):
        client = McdMcpClient(token="t", base_url="https://mcp.mcd.cn/mcp")
        assert client.base_url == "https://mcp.mcd.cn/mcp"

    def test_non_official_url_allowed_with_explicit_opt_in(self, capsys):
        McdMcpClient(token="t", base_url="https://proxy.example.com/mcp",
                     allow_non_official_url=True)
        assert "非官方" in capsys.readouterr().err

    def test_error_message_does_not_leak_token(self):
        with pytest.raises(EndpointNotAllowedError) as excinfo:
            McdMcpClient(token="SECRET-TOKEN-VALUE", base_url="https://evil.example.com/mcp")
        assert "SECRET-TOKEN-VALUE" not in str(excinfo.value)


class TestCouponContract:
    """带券核价的请求契约（2026-10-21 真实实测）。"""

    def test_both_identifiers_attached_to_matching_item(self):
        client = _FakeClient(text="## Original Response\n{\"data\":{\"price\":990}}")
        pricer = make_mcp_pricer(client)
        cart = Cart([{"mealCode": "1100", "quantity": 1},
                     {"mealCode": "507411", "quantity": 1}])
        coupon = {"couponId": COUPON_ID, "couponCode": COUPON_CODE,
                  "products": [{"productCode": "507411"}]}
        pricer(cart, coupon)
        _, args = client.calls[0]
        target = [i for i in args["items"] if "couponCode" in i]
        assert len(target) == 1
        assert target[0]["productCode"] == "507411"
        assert target[0]["couponId"] == COUPON_ID
        assert target[0]["couponCode"] == COUPON_CODE

    def test_accepts_real_api_field_names(self):
        """官方 query-my-coupons 用 id / code 字段。"""
        client = _FakeClient(text="## Original Response\n{\"data\":{\"price\":990}}")
        pricer = make_mcp_pricer(client)
        cart = Cart([{"mealCode": "507411", "quantity": 1}])
        pricer(cart, {"id": COUPON_ID, "code": COUPON_CODE})
        _, args = client.calls[0]
        assert args["items"][0]["couponId"] == COUPON_ID
        assert args["items"][0]["couponCode"] == COUPON_CODE

    def test_coupon_is_not_sent_as_top_level_argument(self):
        client = _FakeClient(text="## Original Response\n{\"data\":{\"price\":990}}")
        pricer = make_mcp_pricer(client)
        pricer(Cart([{"mealCode": "507411", "quantity": 1}]),
               {"couponId": COUPON_ID, "couponCode": COUPON_CODE})
        _, args = client.calls[0]
        assert "couponId" not in args
        assert "couponCode" not in args

    def test_optional_fields_pass_through(self):
        client = _FakeClient(text="## Original Response\n{\"data\":{\"price\":990}}")
        pricer = make_mcp_pricer(client, need_tableware=True,
                                 with_order={"cardType": 2, "cardId": "x"},
                                 be_code="BECODE123")
        pricer(Cart([{"mealCode": "1100", "quantity": 1}]), None)
        _, args = client.calls[0]
        assert args["needTableware"] is True
        assert args["withOrder"] == {"cardType": 2, "cardId": "x"}
        assert args["beCode"] == "BECODE123"


class TestStructuredContent:
    """结构化载荷优先于文本。"""

    def test_tool_json_prefers_structured_content(self):
        result = {"content": [{"type": "text", "text": "## Original Response\n{\"data\":{\"price\":5050}}"}],
                  "structuredContent": {"success": True, "data": {"price": 990, "coupons": []}}}
        payload = tool_json(result)
        assert payload["data"]["price"] == 990

    def test_tool_json_falls_back_to_text(self):
        result = {"content": [{"type": "text", "text": "## Original Response\n{\"data\":{\"price\":5050}}"}]}
        assert tool_json(result)["data"]["price"] == 5050

    def test_unwrap_reads_structured_coupons(self):
        """真实 query-my-coupons：structuredContent.data.coupons"""
        result = {"content": [{"type": "text", "text": "# 您的优惠券列表\n共 5 张"}],
                  "structuredContent": {"success": True, "data": {"coupons": [
                      {"id": COUPON_ID, "code": COUPON_CODE, "title": "9.9元中杯冰美式",
                       "tradeEndDateTime": "2026-10-27 23:59:59",
                       "discountInfo": {"discountValue": "9.9"}}]}}}
        records = silent_cost._unwrap(result)
        assert len(records) == 1
        assert records[0]["id"] == COUPON_ID

    def test_coupon_face_reads_nested_discount_info(self):
        assert silent_cost._coupon_face({"title": "9.9元中杯冰美式",
                                         "discountInfo": {"discountValue": "9.9"}}) == 9.9

    def test_coupon_expiry_reads_trade_end_time(self):
        from datetime import datetime

        days = silent_cost._parse_expire_days("2026-10-27 23:59:59", datetime(2026, 10, 21))
        assert days == 6


class TestClearSafety:
    """clear 只允许作用于本工具创建的券库。"""

    def test_clear_refuses_foreign_json(self, tmp_path):
        target = tmp_path / "other.json"
        target.write_text('{"hello": "world"}', encoding="utf-8")
        code = deal_compare.main(["--file", str(target), "clear", "--yes"])
        assert code == deal_compare.EXIT_USAGE
        assert target.read_text(encoding="utf-8") == '{"hello": "world"}'

    def test_clear_refuses_non_list_json(self, tmp_path):
        target = tmp_path / "arr.json"
        target.write_text("[1, 2, 3]", encoding="utf-8")
        assert deal_compare.main(["--file", str(target), "clear", "--yes"]) == deal_compare.EXIT_USAGE

    def test_clear_works_on_real_library(self, tmp_path):
        target = tmp_path / "deals.json"
        deal_compare._save_deals(str(target), [{"id": "x1", "title": "券", "price": 1.0, "face_value": 2.0}])
        code = deal_compare.main(["--file", str(target), "clear", "--yes"])
        assert code == deal_compare.EXIT_OK
        assert json.loads(target.read_text(encoding="utf-8")) == []
