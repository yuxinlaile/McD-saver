"""真实计价路径的回归测试（2026-10-20 用真实 Token 实测后新增）。

实测结论（官方 mcp.mcd.cn，storeCode=1990232）：
- 工具返回是「Markdown 字段说明 + `## Original Response` 后的真实 JSON」，
  且 JSON 之后可能还跟着展示说明文字；
- `calculate-price` 的请求体字段是 ``items``，必填 ``beType`` / ``needTableware`` /
  ``withOrder``，金额字段是 ``price``，**单位是分**（¥50.50 → 5050）；
- 而 ``query-meals`` 的 ``currentPrice`` 是**元**（"26.5"）。

在此之前，真实计价模式在真实环境下无法出任何结果（请求字段名错、金额键取不到、
单位差 100 倍、返回体未解析）。
"""
import json

import pytest

from mcd_client import tool_json
from optimizer import Cart, _to_yuan, make_mcp_pricer

MARKDOWN_PAYLOAD = (
    "# API Response Information\n\n字段说明……\n\n## Original Response\n"
    '{"success":true,"code":200,"data":{"price":5050,"discount":0}}\n'
    "## 展示结果时，每个门店的 storeCode 必须完整展示，\n"
)


class _FakeClient:
    """记录调用参数并返回固定文本的假客户端。"""

    def __init__(self, text):
        self.text = text
        self.calls = []
        self._store_code = "1990232"
        self._order_type = 1
        self._be_type = 1

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": self.text}]}


class TestToolJson:
    """tools/call 结果里的 JSON 载荷提取。"""

    def test_extracts_json_from_markdown_with_trailing_text(self):
        payload = tool_json({"content": [{"type": "text", "text": MARKDOWN_PAYLOAD}]})
        assert payload["data"]["price"] == 5050

    def test_returns_none_when_no_json(self):
        assert tool_json({"content": [{"type": "text", "text": "暂无可用优惠券"}]}) is None

    def test_plain_dict_passthrough(self):
        assert tool_json({"data": {"price": 1}}) == {"data": {"price": 1}}

    def test_plain_json_text(self):
        assert tool_json({"content": [{"type": "text", "text": '{"ok": true}'}]}) == {"ok": True}


class TestYuanConversion:
    """分 → 元 的折算与单位自检。"""

    def test_default_divides_by_100(self):
        assert _to_yuan(5050) == pytest.approx(50.50)

    def test_hint_picks_the_cent_interpretation(self):
        # 本地估算 50.50 元 → 官方返回 5050 必然是「分」
        assert _to_yuan(5050, hint=50.5) == pytest.approx(50.50)

    def test_hint_picks_the_yuan_interpretation(self):
        # 本地估算 50.50 元、官方返回 50.5 → 只能是「元」
        assert _to_yuan(50.5, hint=50.5) == pytest.approx(50.5)


class TestMcpPricer:
    """真实计价请求的字段与取价。"""

    def test_request_uses_official_field_names(self):
        client = _FakeClient(MARKDOWN_PAYLOAD)
        pricer = make_mcp_pricer(client)
        cart = Cart([{"mealCode": "1100", "quantity": 1}, {"mealCode": "4810", "quantity": 1}])
        pricer(cart, None)
        name, args = client.calls[0]
        assert name == "calculate-price"
        assert "items" in args and "products" not in args
        assert args["beType"] == 1
        assert args["needTableware"] is False
        assert args["withOrder"] == {}
        assert args["items"][0] == {"productCode": "1100", "quantity": 1}

    def test_price_is_converted_to_yuan(self):
        client = _FakeClient(MARKDOWN_PAYLOAD)
        pricer = make_mcp_pricer(client, local_fn=lambda cart, coupon: 50.50)
        cart = Cart([{"mealCode": "1100", "quantity": 1}])
        assert pricer(cart, None) == pytest.approx(50.50)

    def test_coupon_is_attached_to_items(self):
        client = _FakeClient(MARKDOWN_PAYLOAD)
        pricer = make_mcp_pricer(client)
        cart = Cart([{"mealCode": "1100", "quantity": 1}])
        coupon = {"couponId": "C1", "couponCode": "CC1",
                  "products": [{"productCode": "1100"}]}
        pricer(cart, coupon)
        _, args = client.calls[0]
        assert args["items"][0]["couponCode"] == "CC1"

    def test_missing_price_returns_none(self):
        client = _FakeClient("## Original Response\n{\"data\":{}}")
        pricer = make_mcp_pricer(client)
        assert pricer(Cart([{"mealCode": "1100", "quantity": 1}]), None) is None
