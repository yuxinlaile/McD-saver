"""optimizer 券组合优化器单元测试。"""
import json

import pytest

from optimizer import (
    Cart,
    build_candidates,
    make_local_pricer,
    score_and_rank,
)

MENU = {
    "storeCode": "T01", "orderType": 1,
    "items": [
        {"mealCode": "A", "name": "主餐", "price": 25.0},
        {"mealCode": "B", "name": "小食", "price": 12.0},
        {"mealCode": "C", "name": "凑单品", "price": 7.0},
        {"mealCode": "D", "name": "贵凑单", "price": 20.0},
    ],
}
WANTS = [{"mealCode": "A", "quantity": 1}]  # 面值 25.0
COUPONS = [
    {"couponId": "C1", "title": "满25减6", "threshold": 25.0, "discount": 6.0},
    {"couponId": "C2", "title": "满40减10", "threshold": 40.0, "discount": 10.0},
]


class TestLocalPricer:
    def test_no_coupon_returns_face(self):
        price = make_local_pricer(MENU)
        assert price(Cart(WANTS), None) == 25.0

    def test_below_threshold_invalid(self):
        price = make_local_pricer(MENU)
        assert price(Cart(WANTS), COUPONS[1]) is None  # 25 < 40

    def test_threshold_boundary_valid(self):
        price = make_local_pricer(MENU)
        assert price(Cart(WANTS), COUPONS[0]) == 19.0  # 25 - 6

    def test_discount_capped_at_zero(self):
        menu = {"items": [{"mealCode": "A", "price": 5.0}]}
        price = make_local_pricer(menu)
        assert price(Cart(WANTS), {"threshold": 0, "discount": 100.0}) == 0.0


class TestCandidateGeneration:
    def test_always_includes_baseline(self):
        plans = build_candidates(WANTS, [], MENU)
        assert len(plans) == 1 and plans[0].coupon is None

    def test_addon_is_cheapest_sufficient(self):
        plans = build_candidates(WANTS, COUPONS, MENU)
        addon_plan = [p for p in plans if p.note.startswith("凑单")]
        assert len(addon_plan) == 1
        # 25 + 7(C) = 32 仍不达 40；只有 +20(D) 达标 → 选 D
        assert "贵凑单" in addon_plan[0].note

    def test_no_addon_when_threshold_reachable(self):
        plans = build_candidates(WANTS, [COUPONS[0]], MENU)
        assert all(not p.note for p in plans)

    def test_zero_threshold_coupon_no_addon(self):
        coupons = [{"couponId": "C0", "title": "无门槛", "threshold": 0.0, "discount": 2.0}]
        plans = build_candidates(WANTS, coupons, MENU)
        assert len(plans) == 2 and all(not p.note for p in plans)


class TestRanking:
    def _rank(self, wants=WANTS, coupons=COUPONS):
        plans = build_candidates(wants, coupons, MENU)
        return score_and_rank(plans, make_local_pricer(MENU), top=3)

    def test_best_plan_is_cheapest(self):
        result = self._rank()
        assert result["ranked"][0].payable == min(p.payable for p in result["ranked"])

    def test_baseline_is_no_coupon(self):
        result = self._rank()
        assert result["baseline"] == 25.0

    def test_tie_prefers_fewer_items(self):
        menu = {"items": [
            {"mealCode": "A", "price": 30.0},
            {"mealCode": "E", "price": 0.0},
        ]}
        coupons = [{"couponId": "X", "title": "满30减10", "threshold": 30.0, "discount": 10.0}]
        plans = build_candidates([{"mealCode": "A"}], coupons, menu)
        result = score_and_rank(plans, make_local_pricer(menu))
        # 30-10=20（2 件）与 30+0-10=20（3 件）同价时，少件者优先
        assert result["ranked"][0].cart.item_count() == 1

    def test_saving_math(self):
        result = self._rank()
        best = result["ranked"][0]
        assert abs((result["baseline"] - best.payable) - 6.0) < 1e-9


class TestCliSmoke:
    def test_demo_runs(self, capsys):
        from optimizer import main
        assert main(["demo"]) == 0
        out = capsys.readouterr().out
        assert "最优组合方案" in out and "凑单" in out

    def test_plan_requires_files(self):
        from optimizer import main
        assert main(["plan", "--wants", "nope.json", "--menu", "nope.json",
                     "--coupons", "nope.json"]) == 1


class TestConstraints:
    """v1.4.0 新增：热量/预算约束与套餐替换。"""

    MENU_KCAL = {"items": [
        {"mealCode": "A", "name": "主餐", "price": 25.0, "kcal": 550},
        {"mealCode": "B", "name": "小食", "price": 12.0, "kcal": 330},
        {"mealCode": "M", "name": "主餐套餐(含主餐)", "price": 23.0,
         "kcal": 520, "contains": ["A"]},
    ]}

    def test_kcal_computed_per_plan(self):
        plans = build_candidates(WANTS, [], self.MENU_KCAL)
        result = score_and_rank(plans, make_local_pricer(self.MENU_KCAL),
                                kcal_table={"A": 550.0, "M": 520.0})
        assert result["ranked"][0].kcal == 520.0  # 排名第一的是改点套餐方案

    def test_budget_flags_over_budget(self):
        plans = build_candidates(WANTS, [], MENU)
        result = score_and_rank(plans, make_local_pricer(MENU), budget=20.0)
        assert all(p.over_budget for p in result["ranked"] if (p.payable or 0) > 20.0)

    def test_over_kcal_ranked_last(self):
        plans = build_candidates(WANTS, [], self.MENU_KCAL)
        result = score_and_rank(plans, make_local_pricer(self.MENU_KCAL),
                                max_kcal=400, kcal_table={"A": 550})
        assert result["ranked"][-1].over_kcal

    def test_set_meal_swap_candidate(self):
        # wants=[主餐]，菜单里存在 contains 覆盖 A 的套餐 → 生成改点套餐候选
        plans = build_candidates([{"mealCode": "A"}], [], self.MENU_KCAL)
        swaps = [p for p in plans if p.note.startswith("改点套餐")]
        assert len(swaps) == 1
        assert swaps[0].cart.entries[0]["mealCode"] == "M"

    def test_swap_priced_cheaper_and_wins(self):
        # 套餐 23 元 < 单点 25 元 → 排名第一（改点套餐方案为无券，标签同基准）
        plans = build_candidates([{"mealCode": "A"}], [], self.MENU_KCAL)
        result = score_and_rank(plans, make_local_pricer(self.MENU_KCAL))
        assert result["ranked"][0].payable == 23.0
        assert result["ranked"][0].note.startswith("改点套餐")

    def test_swap_skipped_when_combo_is_want(self):
        plans = build_candidates([{"mealCode": "M"}], [], self.MENU_KCAL)
        assert all(not p.note.startswith("改点套餐") for p in plans)


class TestNutritionConstraints:
    """v1.5.0 新增：蛋白质下限与钠上限约束。"""

    MENU_NUTRI = {"items": [
        {"mealCode": "A", "name": "主餐", "price": 25.0, "kcal": 550,
         "protein": 25.0, "sodium": 1010.0},
        {"mealCode": "B", "name": "高蛋白小食", "price": 12.0, "kcal": 330,
         "protein": 20.0, "sodium": 300.0},
        {"mealCode": "C", "name": "低钠小食", "price": 12.0, "kcal": 200,
         "protein": 5.0, "sodium": 100.0},
        {"mealCode": "N", "name": "无营养数据单品", "price": 10.0},
    ]}
    NUTRI = {"A": {"protein": 25.0, "sodium": 1010.0},
             "B": {"protein": 20.0, "sodium": 300.0},
             "C": {"protein": 5.0, "sodium": 100.0}}

    def test_protein_and_sodium_computed_per_plan(self):
        plans = build_candidates(WANTS, [], self.MENU_NUTRI)
        result = score_and_rank(plans, make_local_pricer(self.MENU_NUTRI),
                                nutrition_table=self.NUTRI)
        top = result["ranked"][0]
        assert top.protein == 25.0 and top.sodium == 1010.0

    def test_min_protein_satisfied_not_flagged(self):
        plans = build_candidates(WANTS, [], self.MENU_NUTRI)
        result = score_and_rank(plans, make_local_pricer(self.MENU_NUTRI),
                                min_protein=20.0, nutrition_table=self.NUTRI)
        assert all(not p.under_protein for p in result["ranked"])

    def test_min_protein_deficient_ranked_last_and_flagged(self):
        # wants=低蛋白小食 C（蛋白 5g < 下限 20g）→ 违规排后并打标
        plans = build_candidates([{"mealCode": "C"}], [], self.MENU_NUTRI)
        result = score_and_rank(plans, make_local_pricer(self.MENU_NUTRI),
                                min_protein=20.0, nutrition_table=self.NUTRI)
        assert result["ranked"][0].under_protein

    def test_unknown_protein_counts_as_violation(self):
        # 菜单缺 N 的营养数据 → 含 N 的方案「蛋白质未知」，按不满足处理
        plans = build_candidates([{"mealCode": "N"}], [], self.MENU_NUTRI)
        result = score_and_rank(plans, make_local_pricer(self.MENU_NUTRI),
                                min_protein=5.0, nutrition_table=self.NUTRI)
        assert result["ranked"][0].under_protein
        assert result["ranked"][0].protein_unknown

    def test_over_sodium_ranked_last_and_flagged(self):
        # wants=A（钠 1010mg > 上限 800mg）→ 违规打标
        plans = build_candidates(WANTS, [], self.MENU_NUTRI)
        result = score_and_rank(plans, make_local_pricer(self.MENU_NUTRI),
                                max_sodium=800.0, nutrition_table=self.NUTRI)
        assert result["ranked"][0].over_sodium

    def test_sodium_within_limit_not_flagged(self):
        plans = build_candidates([{"mealCode": "C"}], [], self.MENU_NUTRI)
        result = score_and_rank(plans, make_local_pricer(self.MENU_NUTRI),
                                max_sodium=800.0, nutrition_table=self.NUTRI)
        assert not result["ranked"][0].over_sodium

    def test_combined_violations_rank_after_clean(self):
        # A 超钠且达蛋白；C 蛋白不足但钠达标 → 干净方案（B）排最前
        wants = [{"mealCode": "A"}]
        menu = dict(self.MENU_NUTRI)
        menu["items"] = self.MENU_NUTRI["items"] + [
            {"mealCode": "B2", "name": "均衡替代", "price": 24.0, "kcal": 400,
             "protein": 22.0, "sodium": 500.0},
        ]
        nutri = dict(self.NUTRI)
        nutri["B2"] = {"protein": 22.0, "sodium": 500.0}
        plans = build_candidates(wants, [], menu)
        # 加入 B2 的"改点套餐"式候选不存在，直接构造多方案：手工加一个 B2 直点
        from optimizer import Cart as C, Plan as P
        plans.append(P(C([{"mealCode": "B2", "quantity": 1}]), None, note="均衡替代"))
        result = score_and_rank(plans, make_local_pricer(menu),
                                min_protein=20.0, max_sodium=800.0,
                                nutrition_table=nutri)
        assert result["ranked"][0].payable == 24.0
        assert not result["ranked"][0].under_protein and not result["ranked"][0].over_sodium

    def test_report_mentions_nutrition_flags(self, capsys):
        from optimizer import render_report
        plans = build_candidates([{"mealCode": "C"}], [], self.MENU_NUTRI)
        result = score_and_rank(plans, make_local_pricer(self.MENU_NUTRI),
                                min_protein=20.0, nutrition_table=self.NUTRI)
        text = render_report(result, "估算模式（本地计价，未经验证）")
        assert "蛋白质不足" in text and "蛋白质下限" in text

    def test_explicit_sodium_cap_with_missing_data_flags_all(self):
        # score_and_rank 语义：显式设置 max_sodium 但菜单无 sodium 数据
        # → 所有方案按不满足处理（保守、如实）；CLI 层在无数据时不启用约束
        menu = {"items": [{"mealCode": "A", "name": "主餐", "price": 25.0}]}
        plans = build_candidates(WANTS, [], menu)
        result = score_and_rank(plans, make_local_pricer(menu),
                                max_sodium=800.0, nutrition_table={})
        assert result["ranked"][0].over_sodium


class TestCrossChannelSection:
    """v2.0.3 新增：optimizer 自动衔接团购终局建议。"""

    def _setup_deals(self, tmp_path, monkeypatch):
        import json
        deals = [{"id": "t1", "platform": "meituan", "title": "满40减14代金券",
                  "price": 25.9, "face_value": 40.0, "channel": "store",
                  "time": "limited", "valid_until": "2026-11-30", "notes": ""}]
        f = tmp_path / "deals.json"
        f.write_text(json.dumps(deals), encoding="utf-8")
        monkeypatch.setenv("MCD_DEALS_FILE", str(f))

    def _result(self, baseline, payable):
        class P:
            label = "测试方案"
            payable = None

        p = P()
        p.payable = payable
        return {"baseline": baseline, "ranked": [p]}

    def test_section_rendered_with_deals(self, tmp_path, monkeypatch):
        from optimizer import cross_channel_section
        self._setup_deals(tmp_path, monkeypatch)
        text = cross_channel_section(self._result(43.5, 33.5))
        assert "团购终局建议" in text and "官方最优" in text and "团购最优" in text
        # 折算：43.5 × (25.9/40) ≈ 28.17 < 33.5 → 建议团购
        assert "团购估算更低" in text

    def test_official_better_conclusion(self, tmp_path, monkeypatch):
        from optimizer import cross_channel_section
        deals = [{"id": "t1", "platform": "meituan", "title": "满40减14代金券",
                  "price": 38.0, "face_value": 40.0, "channel": "store",
                  "time": "limited", "valid_until": "2026-11-30", "notes": ""}]
        f = tmp_path / "deals.json"
        f.write_text(json.dumps(deals), encoding="utf-8")
        monkeypatch.setenv("MCD_DEALS_FILE", str(f))
        text = cross_channel_section(self._result(43.5, 30.0))
        assert "官方渠道（含券）已更优" in text

    def test_empty_deals_returns_empty(self, tmp_path, monkeypatch):
        from optimizer import cross_channel_section
        f = tmp_path / "deals.json"
        f.write_text('{"deals": []}', encoding="utf-8")
        monkeypatch.setenv("MCD_DEALS_FILE", str(f))
        assert cross_channel_section(self._result(43.5, 33.5)) == ""

    def test_no_deals_file_returns_empty(self, tmp_path, monkeypatch):
        from optimizer import cross_channel_section
        monkeypatch.setenv("MCD_DEALS_FILE", str(tmp_path / "none.json"))
        assert cross_channel_section(self._result(43.5, 33.5)) == ""

    def test_zero_baseline_returns_empty(self, tmp_path, monkeypatch):
        from optimizer import cross_channel_section
        self._setup_deals(tmp_path, monkeypatch)
        assert cross_channel_section(self._result(0, 0)) == ""


class TestPrefilterPlans:
    """v2.1.1 新增：两阶段计价预筛（估算排序取 Top-K）。"""

    def _plans_and_menu(self):
        menu = {"items": [
            {"mealCode": "A", "name": "汉堡", "price": 20.0},
            {"mealCode": "B", "name": "套餐", "price": 35.0},
        ]}
        wants = [{"mealCode": "A", "quantity": 1}]
        coupons = [
            {"couponId": "c1", "title": "满20减5", "threshold": 20, "discount": 5},
            {"couponId": "c2", "title": "满10减2", "threshold": 10, "discount": 2},
            {"couponId": "c3", "title": "无券"},
        ]
        plans = build_candidates(wants, coupons, menu)
        return plans, menu

    def test_topk_reduces_plans(self):
        from optimizer import prefilter_plans
        plans, menu = self._plans_and_menu()
        k = 2
        filtered = prefilter_plans(plans, menu, k)
        assert len(filtered) == min(k, len(plans))

    def test_k_zero_returns_all(self):
        from optimizer import prefilter_plans
        plans, menu = self._plans_and_menu()
        assert len(prefilter_plans(plans, menu, 0)) == len(plans)

    def test_cheapest_estimate_survives(self):
        from optimizer import prefilter_plans, make_local_pricer, score_and_rank
        plans, menu = self._plans_and_menu()
        fn = make_local_pricer(menu)
        full = score_and_rank(plans, fn, top=len(plans))
        best_label = full["ranked"][0].label
        filtered = prefilter_plans(plans, menu, 2)
        labels = [p.label for p in filtered]
        assert best_label in labels  # 估算最优必在 Top-K 内
