"""silent_cost 沉默成本体检单元测试。"""
from datetime import datetime

from silent_cost import (
    analyze_coupons,
    analyze_mall,
    analyze_orders,
    analyze_points,
    render_report,
)

TODAY = datetime(2026, 10, 12)
DEMO_POINTS_DATA = {"data": {"availablePoint": 1200.0, "currentMouthExpirePoint": 300.0,
                             "nextMouthExpirePoint": 150.0}}
DEMO_MALL_DATA = {"data": [{"name": "中杯鲜煮咖啡券", "points": 500, "worth": 10.5}]}


class TestCoupons:
    def test_expiring_within_window(self):
        raw = {"data": [
            {"title": "满50减12", "parValue": 12.0, "validityEndTime": "2026-10-13 23:59:59"},
            {"title": "远期券", "parValue": 5.0, "validityEndTime": "2026-12-31 23:59:59"},
        ]}
        result = analyze_coupons(raw, TODAY)
        assert result["total"] == 2
        assert len(result["expiring"]) == 1
        assert result["expiring"][0]["days"] == 1
        assert result["expiring_face_total"] == 12.0

    def test_face_fallback_to_title_regex(self):
        raw = [{"title": "满40减10", "endTime": "2026-10-14"}]
        result = analyze_coupons(raw, TODAY)
        assert result["expiring"][0]["face"] == 10.0

    def test_epoch_timestamp(self):
        # 2026-10-15 00:00:00 (本地时区近似，用日期差断言)
        import time
        ts = time.mktime(time.strptime("2026-10-15", "%Y-%m-%d")) * 1000
        result = analyze_coupons([{"title": "T", "expireTime": ts}], TODAY)
        assert 2 <= result["expiring"][0]["days"] <= 4

    def test_unrecognized_skipped(self):
        result = analyze_coupons([{"title": "无日期券"}], TODAY)
        assert result["expiring"] == [] and result["unrecognized"] == 1

    def test_expired_not_listed(self):
        raw = [{"title": "旧券", "parValue": 5.0, "validityEndTime": "2026-09-01"}]
        result = analyze_coupons(raw, TODAY)
        assert result["expiring"] == []


class TestOrders:
    def test_profile_stats(self):
        raw = {"data": [
            {"totalAmount": 30.0, "items": [{"name": "汉堡", "quantity": 1}]},
            {"totalAmount": 40.0, "items": [{"name": "汉堡", "quantity": 1}]},
            {"payable": "¥25.50", "items": [{"name": "可乐"}]},
        ]}
        result = analyze_orders(raw)
        assert result["order_count"] == 3
        assert result["amount_count"] == 3
        assert result["total_spend"] == 95.5
        assert abs(result["avg_ticket"] - 95.5 / 3) < 1e-9
        assert result["top_items"][0] == {"name": "汉堡", "count": 2}

    def test_top_items_excludes_single_purchase(self):
        raw = {"data": [
            {"totalAmount": 1, "items": [{"name": "只点一次"}]},
            {"totalAmount": 1, "items": [{"name": "复购A"}]},
            {"totalAmount": 1, "items": [{"name": "复购A"}]},
        ]}
        result = analyze_orders(raw)
        assert [i["name"] for i in result["top_items"]] == ["复购A"]

    def test_empty(self):
        result = analyze_orders({"data": []})
        assert result["total_spend"] is None and result["top_items"] == []

    def test_refund_is_signed_and_excluded_from_spend(self):
        """退款/冲正金额为负：既不能当正消费，也不算 0 元订单。"""
        raw = {"data": [
            {"totalAmount": 30.0},
            {"totalAmount": -20.0},
            {"totalAmount": 0},
        ]}
        result = analyze_orders(raw)
        assert result["refund_order_count"] == 1
        assert result["free_order_count"] == 1
        assert result["amount_count"] == 1
        assert result["total_spend"] == 30.0
        assert result["avg_ticket"] == 30.0

    def test_refund_string_keeps_sign(self):
        from silent_cost import _parse_amount
        assert _parse_amount("-¥12.50") == -12.5
        assert _parse_amount("-20") == -20.0
        assert _parse_amount("¥12.50") == 12.5

    def test_report_mentions_refunds(self):
        from silent_cost import analyze_coupons, render_report, schedule_coupons
        raw = {"data": [{"totalAmount": 30.0}, {"totalAmount": -20.0}]}
        orders = analyze_orders(raw)
        coupons = analyze_coupons({"data": []})
        text = render_report(coupons, orders, analyze_points({}), None,
                             schedule_coupons(coupons, orders))
        assert "退款/冲正" in text


class TestPoints:
    def test_full_fields(self):
        raw = {"data": {"availablePoint": 130.9, "currentMouthExpirePoint": 0,
                        "nextMouthExpirePoint": 0}}
        result = analyze_points(raw)
        assert result["available"] == 130.9
        assert result["unrecognized"] == 0

    def test_missing(self):
        assert analyze_points({})["unrecognized"] == 1


class TestReport:
    def test_render_contains_sections(self):
        coupons = analyze_coupons({"data": [
            {"title": "满50减12", "parValue": 12.0, "validityEndTime": "2026-10-13 23:59:59"}]},
            TODAY)
        orders = analyze_orders({"data": [
            {"totalAmount": 33.5, "items": [{"name": "麦辣鸡腿堡"}]}]})
        points = analyze_points({"data": {"availablePoint": 100.0}})
        out = render_report(coupons, orders, points)
        assert "临期券" in out and "消费画像" in out and "积分体检" in out

    def test_demo_runs(self, capsys):
        from silent_cost import main
        assert main(["demo"]) == 0
        assert "沉默成本体检报告" in capsys.readouterr().out


class TestMallShadowPrice:
    """v1.4.0 新增：积分商城影子价格。"""

    def test_shadow_price_is_max_efficiency(self):
        raw = {"data": [
            {"name": "咖啡券", "points": 500, "worth": 10.5},   # 0.021
            {"name": "套餐券", "points": 5000, "worth": 39.5},  # 0.0079
        ]}
        result = analyze_mall(raw)
        assert result["shadow_price"] == 10.5 / 500
        assert result["best_product"]["name"] == "咖啡券"

    def test_invalid_products_ignored(self):
        result = analyze_mall({"data": [
            {"name": "零分商品", "points": 0, "worth": 10.0},
            {"name": "无面值", "points": 100},
        ]})
        assert result["shadow_price"] is None

    def test_report_includes_shadow_price_line(self):
        from silent_cost import analyze_mall
        mall = analyze_mall({"data": [{"name": "咖啡券", "points": 500, "worth": 10.5}]})
        points = analyze_points({"data": {"availablePoint": 1000.0}})
        out = render_report(analyze_coupons([], TODAY), analyze_orders({"data": []}),
                            points, mall)
        assert "积分价值估算" in out and "0.0210" in out
        assert "¥21.00" in out


class TestCouponSchedule:
    """v1.6.0 新增：用券排程——过期窗口 × 点单频率。"""

    def test_schedule_assigns_by_face_desc(self):
        from silent_cost import analyze_coupons, analyze_orders, schedule_coupons
        coupons = analyze_coupons({"data": [
            {"title": "小券", "parValue": 3.0, "validityEndTime": "2026-10-14"},
            {"title": "大券", "parValue": 10.0, "validityEndTime": "2026-10-17"},
        ]}, today=datetime(2026, 10, 12))
        orders = analyze_orders({"data": [
            {"createTime": "2026-10-10", "totalAmount": 30.0},
            {"createTime": "2026-10-11", "totalAmount": 30.0},
        ]}, today=datetime(2026, 10, 12))
        schedule = schedule_coupons(coupons, orders)
        assert schedule is not None
        # 频率 1 单/天，窗口 2 天 → 2 单 → 两张都排得上
        assert len(schedule["scheduled"]) == 2 and not schedule["missed"]
        assert schedule["scheduled"][0]["title"] == "大券"  # 面值降序优先

    def test_doomed_coupons_sum_matches(self):
        from silent_cost import analyze_coupons, analyze_orders, schedule_coupons
        coupons = analyze_coupons({"data": [
            {"title": "大券", "parValue": 10.0, "validityEndTime": "2026-10-13"},
            {"title": "中券", "parValue": 6.0, "validityEndTime": "2026-10-13"},
            {"title": "小券", "parValue": 3.0, "validityEndTime": "2026-10-13"},
        ]}, today=datetime(2026, 10, 12))
        orders = analyze_orders({"data": [{"createTime": "2026-10-12", "totalAmount": 30.0}]},
                                today=datetime(2026, 10, 12))
        schedule = schedule_coupons(coupons, orders)
        # 窗口 1 天、频率 1 单/天 → 1 单 → 只有 1 张排得上
        assert schedule["expected_orders"] == 1
        assert schedule["scheduled"][0]["face"] == 10.0
        assert abs(schedule["doomed"] - 9.0) < 1e-9
        assert abs(schedule["realizable"] - 10.0) < 1e-9

    def test_no_orders_returns_none(self):
        from silent_cost import analyze_coupons, analyze_orders, schedule_coupons
        coupons = analyze_coupons({"data": [
            {"title": "券", "parValue": 5.0, "validityEndTime": "2026-10-13"}]},
            today=datetime(2026, 10, 12))
        orders = analyze_orders({"data": []}, today=datetime(2026, 10, 12))
        assert schedule_coupons(coupons, orders) is None


class TestProbeCouponValue:
    """v1.6.0 新增：无面值券经 calculate-price 实测，失败返回 None 绝不编造。"""

    class FakeClient:
        def __init__(self, discount):
            self.discount = discount
            self.calls = []
            self._store_code = "ST01"
            self._order_type = 1

        def call_tool(self, name, args):
            self.calls.append((name, args))
            if self.discount is None:
                raise RuntimeError("tool error")
            return {"data": {"discount": self.discount, "payAmount": 20.0}}

    def test_measured_discount_returned(self):
        from silent_cost import probe_coupon_value
        client = self.FakeClient(13.9)
        value = probe_coupon_value(client, {"couponId": "A1", "productCode": "M9"})
        assert value == 13.9
        assert client.calls[0][0] == "calculate-price"
        assert client.calls[0][1]["couponId"] == "A1"

    def test_tool_failure_returns_none(self):
        from silent_cost import probe_coupon_value
        assert probe_coupon_value(self.FakeClient(None), {"couponId": "A1"}) is None

    def test_no_coupon_id_returns_none(self):
        from silent_cost import probe_coupon_value
        assert probe_coupon_value(self.FakeClient(5.0), {"productCode": "M9"}) is None


class TestHtmlReport:
    """v1.6.0 新增：单文件 HTML 报告——零 CDN、可截图分享。"""

    def test_render_html_contains_sections(self):
        from silent_cost import (analyze_coupons, analyze_mall, analyze_orders,
                                 analyze_points, render_html, schedule_coupons)
        coupons = analyze_coupons({"data": [
            {"title": "满30减6", "parValue": 6.0, "validityEndTime": "2026-10-13"}]},
            today=datetime(2026, 10, 12))
        orders = analyze_orders({"data": [{"createTime": "2026-10-01", "totalAmount": 30.0}]},
                                today=datetime(2026, 10, 12))
        html = render_html(coupons, orders, analyze_points(DEMO_POINTS_DATA),
                           analyze_mall(DEMO_MALL_DATA), schedule_coupons(coupons, orders))
        assert "【一】临期券" in html and "【二】消费画像" in html and "【三】积分体检" in html
        assert "注定过期" in html and "mcd-saver" in html
        assert "http://" not in html.replace("http://www.w3.org", "")  # 零外部资源
        assert "<script" not in html  # 无脚本，纯静态


class TestSavingsGrade:
    """v1.7.1 新增：HTML 报告省钱等级（确定性分档）。"""

    def _schedule(self, realizable):
        return {"realizable": realizable, "doomed": 0.0, "face_total": realizable,
                "window_days": 1, "expected_orders": 1, "frequency": 1.0,
                "scheduled": [], "missed": []}

    def test_grade_thresholds(self):
        from silent_cost import savings_grade
        assert savings_grade(self._schedule(35.0))[0] == "S"
        assert savings_grade(self._schedule(20.0))[0] == "A"
        assert savings_grade(self._schedule(8.0))[0] == "B"
        assert savings_grade(self._schedule(2.0))[0] == "C"
        assert savings_grade(self._schedule(0.5))[0] == "D"

    def test_no_schedule_returns_dash(self):
        from silent_cost import savings_grade
        assert savings_grade(None) == ("—", "")

    def test_grade_note_contains_amount(self):
        from silent_cost import savings_grade
        grade, note = savings_grade(self._schedule(35.0))
        assert "35.00" in note

    def test_html_contains_grade_row(self):
        from silent_cost import (analyze_coupons, analyze_orders, analyze_points,
                                 render_html, schedule_coupons)
        coupons = analyze_coupons({"data": [
            {"title": "满30减6", "parValue": 30.0, "validityEndTime": "2026-10-13"}]},
            today=datetime(2026, 10, 12))
        orders = analyze_orders({"data": [{"createTime": "2026-10-12", "totalAmount": 30.0}]},
                                today=datetime(2026, 10, 12))
        schedule = schedule_coupons(coupons, orders)
        html = render_html(coupons, orders, analyze_points({}), None, schedule)
        assert "本期省钱等级" in html


class TestNetValueSchedule:
    """v1.7.2 新增：净价值模型（门槛与客单价不匹配时判为纸面富贵）。"""

    def _orders(self, amounts):
        data = [{"createTime": "2026-10-12", "totalAmount": a} for a in amounts]
        return analyze_orders({"data": data}, today=datetime(2026, 10, 12))

    def test_paper_coupon_discouraged(self):
        # 满50减12，客单价 13 → 净价值 12-(50-13) = -25 → paper，不计入可实现
        from silent_cost import analyze_coupons, schedule_coupons
        coupons = analyze_coupons({"data": [
            {"title": "满50减12", "parValue": 12.0, "validityEndTime": "2026-10-13"}]},
            today=datetime(2026, 10, 12))
        orders = self._orders([13.0])
        schedule = schedule_coupons(coupons, orders)
        paper = [c for c in schedule["missed"] if c["category"] == "paper"]
        assert paper and paper[0]["slot"] == "纸面富贵"
        assert paper[0]["net_value"] == 0.0
        assert schedule["scheduled"] == []  # 无净价值为正的券 → 不排入任何点单
        assert schedule["realizable"] == 0.0

    def test_stretch_coupon_partial_net(self):
        # 满40减10，客单价 36.12 → 净价值 10-(40-36.12) = 6.12 → stretch 仍排入
        from silent_cost import analyze_coupons, schedule_coupons
        coupons = analyze_coupons({"data": [
            {"title": "满40减10", "parValue": 10.0, "validityEndTime": "2026-10-13"}]},
            today=datetime(2026, 10, 12))
        orders = self._orders([36.12])
        schedule = schedule_coupons(coupons, orders)
        assert abs(schedule["scheduled"][0]["net_value"] - 6.12) < 0.01
        assert abs(schedule["realizable"] - 6.12) < 0.01

    def test_no_threshold_keeps_face(self):
        from silent_cost import analyze_coupons, schedule_coupons
        coupons = analyze_coupons({"data": [
            {"title": "免费脆薯饼", "parValue": 8.0, "validityEndTime": "2026-10-13"}]},
            today=datetime(2026, 10, 12))
        orders = self._orders([13.0])
        schedule = schedule_coupons(coupons, orders)
        assert schedule["scheduled"][0]["net_value"] == 8.0

    def test_spending_basis_excludes_zero_amount(self):
        # 0 元订单（券核销）不计入客单价，但计入点单频率（点单口径）
        orders = self._orders([30.0, 0.0, 30.0])
        assert orders["order_count"] == 3
        assert orders["free_order_count"] == 1
        assert orders["amount_count"] == 2
        assert abs(orders["avg_ticket"] - 30.0) < 1e-9  # 客单价不被 0 元单拉低
        assert abs(orders["order_frequency"] - 3 / 1) < 0.01

    def test_report_mentions_paper_category(self):
        from silent_cost import analyze_coupons, analyze_orders, render_report, schedule_coupons
        coupons = analyze_coupons({"data": [
            {"title": "满50减12", "parValue": 12.0, "validityEndTime": "2026-10-13"}]},
            today=datetime(2026, 10, 12))
        orders = self._orders([13.0])
        schedule = schedule_coupons(coupons, orders)
        text = render_report(coupons, orders, analyze_points({}), None, schedule)
        assert "纸面富贵" in text and "净价值" in text


class TestTimelineSchedule:
    """v2.6 新增：多单排程——把券按到期日排到未来每一次点单（日期粒度）。"""

    def _orders(self, amounts, dates=None, today=datetime(2026, 10, 12)):
        dates = dates or ["2026-10-10", "2026-10-11"]
        payload = [{"createTime": d, "totalAmount": a} for d, a in zip(dates, amounts)]
        return analyze_orders({"data": payload}, today=today)

    def test_book_keeps_coupon_beyond_expiring_window(self):
        from silent_cost import analyze_coupon_book
        raw = {"data": [
            {"title": "明天到期", "parValue": 5.0, "validityEndTime": "2026-10-13"},
            {"title": "二十天后", "parValue": 10.0, "validityEndTime": "2026-11-01"},
        ]}
        expiring = analyze_coupons(raw, TODAY)
        book = analyze_coupon_book(raw, TODAY)
        # 旧口径只留 7 天内到期的券，长有效期券被整体丢弃
        assert len(expiring["expiring"]) == 1
        assert len(book["coupons"]) == 2

    def test_optimal_assignment_beats_expiry_first(self):
        from silent_cost import analyze_coupon_book, plan_timeline
        # 十天一单（间隔 10 天）：下一次点单之后再没有机会核销 5 天内到期的券
        raw = {"data": [
            {"title": "大券", "parValue": 13.0, "validityEndTime": "2026-10-17"},
            {"title": "小券", "parValue": 8.0, "validityEndTime": "2026-10-14"},
        ]}
        book = analyze_coupon_book(raw, TODAY)
        orders = self._orders([30.0], dates=["2026-10-02"])
        plan = plan_timeline(book, orders, TODAY)
        # 先到期先用会选 8 元的小券；最优解选 13 元的大券，可实现金额多 5 元
        assert plan["realizable"] == 13.0
        assert plan["doomed"] == 8.0
        assert plan["orders"][0]["title"] == "大券"

    def test_assignment_compacts_towards_earlier_orders(self):
        from silent_cost import analyze_coupon_book, plan_timeline
        raw = {"data": [
            {"title": "大券", "parValue": 13.0, "validityEndTime": "2026-10-17"},
            {"title": "小券", "parValue": 8.0, "validityEndTime": "2026-10-14"},
            {"title": "远期券", "parValue": 5.0, "validityEndTime": "2026-12-26"},
        ]}
        book = analyze_coupon_book(raw, TODAY)
        plan = plan_timeline(book, self._orders([30.0, 30.0]), TODAY)
        assert plan["realizable"] == 26.0 and plan["doomed"] == 0.0
        # 每天都下单时三张券都该排上，且快过期的券排在更靠前的单次
        titles = [o["title"] for o in plan["orders"][:3]]
        assert titles[0] == "小券" and titles[1] == "大券"

    def test_coupon_expiring_before_next_order_is_wasted(self):
        from silent_cost import analyze_coupon_book, plan_timeline
        raw = {"data": [
            {"title": "快过期", "parValue": 6.0, "validityEndTime": "2026-10-14"},
            {"title": "已排上", "parValue": 4.0, "validityEndTime": "2026-10-12"},
        ]}
        book = analyze_coupon_book(raw, TODAY)
        orders = self._orders([30.0], dates=["2026-10-11"])
        plan = plan_timeline(book, orders, TODAY)
        # 频率 1 单/天 → 每天一单，两张券都该排上
        assert plan["doomed"] == 0.0
        assert plan["realizable"] == 10.0

    def test_paper_coupon_not_scheduled(self):
        from silent_cost import analyze_coupon_book, plan_timeline
        raw = {"data": [
            {"title": "满50减9", "parValue": 9.0, "validityEndTime": "2026-10-20"},
        ]}
        book = analyze_coupon_book(raw, TODAY)
        orders = self._orders([30.0, 30.0])
        plan = plan_timeline(book, orders, TODAY)
        # 门槛 50 − 客单 30 = 20 的额外付出 > 面值 9 → 纸面富贵
        assert plan["paper"] and not plan["used"]
        assert plan["realizable"] == 0.0

    def test_horizon_is_capped(self):
        from silent_cost import analyze_coupon_book, plan_timeline
        raw = {"data": [{"title": "券", "parValue": 5.0, "validityEndTime": "2026-12-31"}]}
        book = analyze_coupon_book(raw, TODAY)
        plan = plan_timeline(book, self._orders([30.0, 30.0]), TODAY, horizon_days=999)
        assert plan["horizon_days"] <= 60

    def test_no_frequency_returns_none(self):
        from silent_cost import analyze_coupon_book, plan_timeline
        book = analyze_coupon_book({"data": [
            {"title": "券", "parValue": 5.0, "validityEndTime": "2026-10-20"}]}, TODAY)
        assert plan_timeline(book, analyze_orders({"data": []}, today=TODAY), TODAY) is None

    def test_report_contains_timeline_section(self):
        from silent_cost import analyze_coupon_book, plan_timeline
        raw = {"data": [
            {"title": "满30减6", "parValue": 6.0, "validityEndTime": "2026-10-17"},
            {"title": "满40减10", "parValue": 10.0, "validityEndTime": "2026-10-30"},
        ]}
        coupons = analyze_coupons(raw, TODAY)
        orders = self._orders([30.0, 30.0])
        plan = plan_timeline(analyze_coupon_book(raw, TODAY), orders, TODAY)
        text = render_report(coupons, orders, analyze_points({}), None,
                             None, plan)
        assert "【一·C】多单排程" in text
        assert "到期浪费" in text
