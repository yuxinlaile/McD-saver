#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦省钱助手 —— 券组合优化器。

确定性枚举「无券直点 / 单券 / 凑单达标」候选方案，按实付价排序输出最优组合
与 Top-N 备选。计价一律交给可插拔的 price_fn：

- 估算模式（默认）：本地用菜单价格与券的 threshold/discount 字段计价，
  输出明确标注「估算模式（本地计价，未经验证）」；
- 真实计价模式（--mcp）：调用官方 calculate-price 逐方案核价，
  结果可作为下单决策依据（延续"不虚构优惠"铁律）。

数据文件（JSON）：

- --wants   想吃清单:    [{"mealCode": "M1", "name": "巨无霸", "quantity": 1}]
- --menu    菜单与价格:  {"storeCode": "...", "orderType": 1,
                          "items": [{"mealCode": "M1", "name": "巨无霸",
                                     "price": 25.0, "category": "汉堡"}]}
- --coupons 可用券:      [{"couponId": "C1", "title": "满40减10",
                            "threshold": 40.0, "discount": 10.0}]

工作流（Agent 按 SKILL.md 执行）：
    query-meals / query-meal-detail  → 写 menu.json（含价格字段）
    query-store-coupons + query-my-coupons → 写 coupons.json（threshold/discount
        从券详情提取；不确定时宁可留空字段走 --mcp 真实计价）
    optimizer.py plan ... [--mcp] → 输出方案排名 → 用户确认后 create-order

示例::

    python scripts/optimizer.py demo                      # 离线演示（内嵌示例数据）
    python scripts/optimizer.py plan --wants wants.json --menu menu.json \
        --coupons coupons.json                          # 估算模式
    python scripts/optimizer.py plan --wants wants.json --menu menu.json \
        --coupons coupons.json --mcp                    # 真实计价模式
    python scripts/optimizer.py plan ... --top 5 --json # Top-N + JSON 输出

退出码：0 成功 · 1 用法/数据错误
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:  # 兼容“直接运行脚本”与“作为模块运行”两种方式
    from mcd_client import tool_json
except ImportError:  # pragma: no cover - 以模块方式导入时补脚本目录
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from mcd_client import tool_json

EXIT_OK = 0
EXIT_USAGE = 1

ADDON_HINT = "（凑单提示：仅当你本来就需要该商品才划算）"

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
class Item:
    def __init__(self, meal_code: str, name: str, price: float, category: str = ""):
        self.meal_code = meal_code
        self.name = name
        self.price = float(price)
        self.category = category

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return "Item({0}, {1})".format(self.meal_code, self.price)


class Cart:
    def __init__(self, entries: List[Dict[str, Any]]):
        # entries: [{"mealCode": ..., "quantity": int}]
        self.entries: List[Dict[str, Any]] = [
            {"mealCode": e["mealCode"], "quantity": max(1, int(e.get("quantity", 1)))}
            for e in entries
        ]

    def with_addon(self, meal_code: str) -> "Cart":
        entries = [dict(e) for e in self.entries]
        for e in entries:
            if e["mealCode"] == meal_code:
                e["quantity"] += 1
                return Cart(entries)
        entries.append({"mealCode": meal_code, "quantity": 1})
        return Cart(entries)

    def item_count(self) -> int:
        return sum(e["quantity"] for e in self.entries)


class Plan:
    def __init__(self, cart: Cart, coupon: Optional[Dict[str, Any]], note: str = ""):
        self.cart = cart
        self.coupon = coupon
        self.note = note
        self.payable: Optional[float] = None
        self.kcal: Optional[float] = None
        self.protein: Optional[float] = None
        self.sodium: Optional[float] = None
        self.valid = True
        self.over_budget = False
        self.over_kcal = False
        self.under_protein = False
        self.protein_unknown = False
        self.over_sodium = False

    @property
    def label(self) -> str:
        if self.coupon is None:
            return "无券直点"
        title = self.coupon.get("title") or self.coupon.get("couponId") or "优惠券"
        return str(title)


# ---------------------------------------------------------------------------
# 价格函数
# ---------------------------------------------------------------------------
def make_local_pricer(menu: Dict[str, Any]) -> Callable[[Cart, Optional[Dict[str, Any]]], Optional[float]]:
    """估算模式：本地价格表 + 券 threshold/discount 字段。"""
    price_table = {i.get("mealCode"): float(i.get("price", 0) or 0) for i in menu.get("items", []) if i.get("mealCode")}

    def price(cart: Cart, coupon: Optional[Dict[str, Any]]) -> Optional[float]:
        face = sum(price_table.get(e["mealCode"], 0.0) * e["quantity"] for e in cart.entries)
        if coupon is None:
            return face
        threshold = float(coupon.get("threshold") or 0.0)
        discount = float(coupon.get("discount") or 0.0)
        if face < threshold:
            return None  # 未达门槛，方案无效
        return max(0.0, face - discount)

    return price


def _to_yuan(raw: float, hint: Optional[float] = None) -> float:
    """把 calculate-price 返回的金额折算为「元」。

    实测（2026-10-20，官方 mcp.mcd.cn，storeCode=1990232）：
    ``calculate-price`` 的金额单位是**分**——巨无霸+中薯条+可乐（菜单合计 ¥50.50）
    返回 ``price=5050``、巨无霸三件套返回 ``3750``、精选超值随心配返回 ``1390``；
    而 ``query-meals`` 的 ``currentPrice`` 却是**元**（"26.5"）。两个接口单位不一致，
    不换算就会把实付金额放大 100 倍。

    为防上游改单位：当能拿到同一购物车的本地估算（hint，元）时，取更接近 hint 的那种解释。
    """
    if hint and hint > 0:
        as_yuan = raw / 100.0
        return as_yuan if abs(as_yuan - hint) <= abs(raw - hint) else raw
    return raw / 100.0


def make_mcp_pricer(
    client: Any,
    local_fn: Optional[Callable[[Cart, Optional[Dict[str, Any]]], Optional[float]]] = None,
    need_tableware: bool = False,
    with_order: Optional[Dict[str, Any]] = None,
    be_code: str = "",
) -> Callable[[Cart, Optional[Dict[str, Any]]], Optional[float]]:
    """真实计价模式：调用官方 calculate-price（含官方促销与配送费规则）。

    2026-10-20 / 10-21 按真实响应修正：
    - 请求体字段是 ``items``（不是 ``products``），且必填 ``beType`` / ``needTableware`` /
      ``withOrder``；漏字段服务端直接拒收；
    - 金额字段是 ``price``（旧实现只找 payable/payAmount/total 等，永远取不到值）；
    - 金额单位是分，见 :func:`_to_yuan`；
    - 券必须**同时**给出 ``couponId`` 与 ``couponCode`` 并挂在**商品条目**上
      （只给其一 → code 600010；挂在顶层 → 服务端静默忽略，券不生效）；
    - **外送（orderType=2）需 beType=2 + beCode，且菜单与到店不同**
      （实测同一门店：到店 99 项、外送 60 项，商品编码也不相同）。
    """

    def price(cart: Cart, coupon: Optional[Dict[str, Any]]) -> Optional[float]:
        items = [{"productCode": entry.get("mealCode"),
                  "quantity": max(1, int(entry.get("quantity", 1) or 1))}
                 for entry in cart.entries]
        if coupon and items:
            # 券必须**同时**给出 couponId 与 couponCode，并挂在**商品条目**上——
            # 2026-10-21 实测：只给其一或挂在顶层都会被服务端拒收（code 600010），
            # 顶层挂载虽然返回成功但券被忽略（价格不变）。
            coupon_code = str(coupon.get("couponCode") or coupon.get("code") or "")
            coupon_id = str(coupon.get("couponId") or coupon.get("id") or "")
            if coupon_code or coupon_id:
                scope = {p.get("productCode") for p in (coupon.get("products") or [])
                         if isinstance(p, dict)}
                target = None
                for item in items:
                    if not scope or item["productCode"] in scope:
                        target = item
                        break
                if target is None:
                    target = items[0]
                if coupon_id:
                    target["couponId"] = coupon_id
                if coupon_code:
                    target["couponCode"] = coupon_code
        order_type = getattr(client, "_order_type", 1) or 1
        args: Dict[str, Any] = {
            "storeCode": getattr(client, "_store_code", ""),
            "orderType": order_type,
            "beType": getattr(client, "_be_type", None) or (2 if int(order_type) == 2 else 1),
            "needTableware": bool(need_tableware),
            "withOrder": with_order if isinstance(with_order, dict) else {},
            "items": items,
        }
        if be_code:
            # 外送（orderType=2）与得来速（beType=5）必须带 beCode
            args["beCode"] = be_code
        result = client.call_tool("calculate-price", args)
        payload = tool_json(result)
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        for key in ("price", "payable", "totalPay", "payAmount", "payPrice",
                    "total", "totalPrice", "productPrice"):
            value = _dig(data, key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                hint = None
                if local_fn is not None:
                    try:
                        hint = local_fn(cart, coupon)
                    except Exception:  # noqa: BLE001 - 估算失败不影响真实价
                        hint = None
                return _to_yuan(float(value), hint)
        return None  # 解析不到应付金额时视为无效方案，绝不虚构

    return price


def prefilter_plans(plans: List[Any], menu: Dict[str, Any], k: int) -> List[Any]:
    """按本地估算价预筛前 K 个方案（两阶段计价的第一阶段，v2.1.1）。

    k<=0 或方案数不足时原样返回。估算价排序与真实价排序高度一致
    （价格同源），Top-K 之外方案的真实价通常不会翻盘；需要绝对严谨时
    传 ``--mcp-top-k 0`` 全量核价。
    """
    if k <= 0 or len(plans) <= k:
        return list(plans)
    local_fn = make_local_pricer(menu)
    est = []
    for i, plan in enumerate(plans):
        try:
            price = local_fn(plan.cart, plan.coupon)
        except Exception:
            price = None
        est.append((price if price is not None else float("inf"), i, plan))
    est.sort(key=lambda x: (x[0], x[1]))
    return [p for _, _, p in est[:k]]


def _dig(obj: Any, key: str) -> Any:
    """在嵌套 dict 中按 key 深度优先查找第一个匹配值。"""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _dig(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _dig(v, key)
            if found is not None:
                return found
    return None


# ---------------------------------------------------------------------------
# 候选方案生成与排序
# ---------------------------------------------------------------------------
def build_candidates(
    wants: List[Dict[str, Any]],
    coupons: List[Dict[str, Any]],
    menu: Dict[str, Any],
    addon_limit: int = 3,
) -> List[Plan]:
    """生成候选方案：无券直点 + 每券一方案（未达门槛则尝试最便宜凑单品）
    + 套餐替换（套餐 contains 覆盖全部想吃单品且更省时才会在排名中胜出）。"""
    base = Cart(wants)
    price_table = {i.get("mealCode"): float(i.get("price", 0) or 0) for i in menu.get("items", []) if i.get("mealCode")}
    face = sum(price_table.get(e["mealCode"], 0.0) * e["quantity"] for e in base.entries)
    wants_codes = {e["mealCode"] for e in base.entries}

    plans: List[Plan] = [Plan(base, None)]
    addons = sorted(
        (i for i in menu.get("items", []) if i["mealCode"] not in wants_codes),
        key=lambda i: float(i.get("price", 0) or 0),
    )[:addon_limit]

    for coupon in coupons:
        threshold = float(coupon.get("threshold") or 0.0)
        if threshold <= 0 or face >= threshold:
            plans.append(Plan(base, coupon))
            continue
        for addon in addons:
            addon_price = float(addon.get("price", 0) or 0)
            if face + addon_price >= threshold:
                plans.append(
                    Plan(base.with_addon(addon["mealCode"]), coupon,
                         note="凑单:{0}".format(addon.get("name", addon["mealCode"])))
                )
                break

    # 套餐替换：套餐 contains 覆盖全部想吃单品时，生成"改点套餐"候选。
    # 是否更省交给计价与排名判断——不预设结论。
    want_qty = {e["mealCode"]: int(e.get("quantity", 1)) for e in base.entries}
    for combo in menu.get("items", []):
        contains = combo.get("contains")
        if not isinstance(contains, list) or combo["mealCode"] in wants_codes:
            continue
        if set(contains) >= wants_codes:
            qty = max(1, max(want_qty.values()))
            swap = Cart([{"mealCode": combo["mealCode"], "quantity": qty}])
            plans.append(Plan(swap, None,
                              note="改点套餐:{0}（覆盖全部想吃单品）".format(combo.get("name", combo["mealCode"]))))
    return plans


def score_and_rank(
    plans: List[Plan],
    price_fn: Callable[[Cart, Optional[Dict[str, Any]]], Optional[float]],
    top: int = 3,
    budget: Optional[float] = None,
    max_kcal: Optional[float] = None,
    kcal_table: Optional[Dict[str, float]] = None,
    min_protein: Optional[float] = None,
    max_sodium: Optional[float] = None,
    nutrition_table: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """计价并排序；支持可选约束：实付预算、热量上限、蛋白质下限、钠上限。

    违反约束的方案不删除，而是排到满足约束的方案之后并打标——
    用户能看到"差多少"，而不是被静默过滤。蛋白质数据缺失时如实标注
    「蛋白质未知」并按不满足处理（保守排序，绝不虚构达标）。
    """
    for plan in plans:
        plan.payable = price_fn(plan.cart, plan.coupon)
        plan.valid = plan.payable is not None
        plan.kcal = None
        plan.protein = None
        plan.sodium = None
        if kcal_table and plan.valid:
            kcal = sum(
                kcal_table.get(e["mealCode"], 0.0) * e["quantity"] for e in plan.cart.entries
            )
            plan.kcal = kcal if kcal > 0 else None
            if max_kcal is not None and plan.kcal is not None:
                plan.over_kcal = plan.kcal > max_kcal
        if budget is not None and plan.payable is not None:
            plan.over_budget = plan.payable > budget
        if nutrition_table and plan.valid:
            protein = 0.0
            sodium = 0.0
            complete = True
            for e in plan.cart.entries:
                info = nutrition_table.get(e["mealCode"])
                if not info or info.get("protein") is None or info.get("sodium") is None:
                    complete = False
                    break
                protein += float(info["protein"]) * e["quantity"]
                sodium += float(info["sodium"]) * e["quantity"]
            if complete:
                plan.protein = protein
                plan.sodium = sodium
        if min_protein is not None:
            if plan.protein is None:
                plan.under_protein = True
                plan.protein_unknown = True
            else:
                plan.under_protein = plan.protein < min_protein
        if max_sodium is not None:
            if plan.sodium is None:
                plan.over_sodium = True  # 钠数据缺失同样按不满足处理
            else:
                plan.over_sodium = plan.sodium > max_sodium

    def sort_key(plan: Plan) -> Tuple[float, float, int]:
        violates = ((1 if plan.over_budget else 0) + (1 if plan.over_kcal else 0)
                    + (1 if plan.under_protein else 0) + (1 if plan.over_sodium else 0))
        return (violates, plan.payable or 0.0, plan.cart.item_count())

    valid = [p for p in plans if p.valid]
    baseline_candidates = [p for p in valid if p.coupon is None]
    baseline = baseline_candidates[0].payable if baseline_candidates else None
    if baseline is None and valid:
        baseline = min(p.payable for p in valid)

    ranked = sorted(valid, key=sort_key)[: max(1, top)]
    return {"baseline": baseline, "ranked": ranked, "invalid": len(plans) - len(valid),
            "budget": budget, "max_kcal": max_kcal,
            "min_protein": min_protein, "max_sodium": max_sodium}


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------
def _fmt(value: Optional[float]) -> str:
    return "¥{0:.2f}".format(value) if value is not None else "—"


def cross_channel_section(result: Dict[str, Any], deals_path: Optional[str] = None) -> str:
    """官方最优方案自动衔接团购终局建议（v2.0.3）。

    复用 deal_compare.compare_deals 的同口径折算：以无券直点为原价口径、
    最优实付为官方可比价基准；本地券库（MAIMAI_DEALS_FILE 或默认路径）
    存在且非空时输出「官方 vs 团购」结论，否则返回空串。估算标注不省略。
    """
    baseline = result.get("baseline")
    ranked = result.get("ranked") or []
    if not baseline or baseline <= 0 or not ranked:
        return ""
    best = ranked[0]
    if best.payable is None or best.payable <= 0:
        return ""
    try:
        from deal_compare import _load_deals, compare_deals
        deals = _load_deals(deals_path) if deals_path else _load_deals(
            os.environ.get("MAIMAI_DEALS_FILE", str(Path.home() / ".maimai_saver" / "deals.json")))
    except Exception:
        return ""
    if not deals:
        return ""
    report = compare_deals(deals, mcd_face=baseline, mcd_price=float(best.payable))
    entries = [e for e in report["deals"] if e["validity"] != "expired"]
    if not entries:
        return ""
    best_deal = entries[0]
    lines = ["",
             "---- 团购终局建议（估算口径，非下单依据）----",
             "官方最优：{0}（实付 {1}）".format(best.label or "无券直点", _fmt(best.payable)),
             "团购最优：[{0}] {1}（估算到手 {2}，券售价 {3}/面值 {4}）".format(
                 best_deal.get("platform", ""), best_deal.get("title", ""),
                 _fmt(best_deal["estimated_price"]), _fmt(best_deal["price"]), _fmt(best_deal["face_value"]))]
    if best_deal["estimated_saving_vs_mcd"] > 0:
        lines.append("结论：团购估算更低，约再省 {0}——记得核对适用门店/时段与不可叠加限制。".format(
            _fmt(best_deal["estimated_saving_vs_mcd"])))
    else:
        lines.append("结论：官方渠道（含券）已更优，无需动用团购券。")
    return "\n".join(lines)


def render_report(result: Dict[str, Any], mode_label: str) -> str:
    baseline = result["baseline"]
    ranked: List[Plan] = result["ranked"]
    lines: List[str] = []
    lines.append("=" * 68)
    lines.append("麦麦省钱助手 · 最优组合方案（{0}）".format(mode_label))
    lines.append("=" * 68)
    if baseline is None or not ranked:
        lines.append("无可行方案：请检查菜单/券数据，或改用 --mcp 真实计价模式。")
        return "\n".join(lines)

    lines.append("基准（无券直点）：{0}".format(_fmt(baseline)))
    if result.get("budget") is not None:
        lines.append("预算上限：{0}".format(_fmt(result["budget"])))
    if result.get("max_kcal") is not None:
        lines.append("热量上限：{0:.0f} kcal".format(result["max_kcal"]))
    if result.get("min_protein") is not None:
        lines.append("蛋白质下限：{0:.0f} g".format(result["min_protein"]))
    if result.get("max_sodium") is not None:
        lines.append("钠上限：{0:.0f} mg".format(result["max_sodium"]))
    lines.append("")
    lines.append("方案排名：")
    # 三档场景标签：经济 / 均衡 / 丰盛（v2.0.4）
    # 最便宜 → 最经济；kcal 最高 → 最丰盛；其余 → 均衡（仅 ranked≥2 且字段齐全时）
    scene_labels: Dict[int, str] = {}
    if len(ranked) >= 2 and all(p.payable is not None for p in ranked):
        cheapest = min(range(len(ranked)), key=lambda i: ranked[i].payable)
        richest = max(range(len(ranked)),
                      key=lambda i: (ranked[i].kcal if ranked[i].kcal is not None else -1))
        for i in range(len(ranked)):
            if i == cheapest:
                scene_labels[i] = "最经济"
            elif i == richest and i != cheapest:
                scene_labels[i] = "最丰盛"
            elif len(scene_labels) < 2 and i not in (cheapest, richest):
                scene_labels[i] = "均衡"
    for idx, plan in enumerate(ranked, 1):
        saving = baseline - (plan.payable or 0.0)
        ratio = (saving / baseline * 100.0) if baseline else 0.0
        mark = "  ← 最优" if idx == 1 else ""
        scene = scene_labels.get(idx - 1)
        if scene:
            mark += (" ｜ " if mark else " ｜ ") + scene
        flags = []
        if plan.over_budget:
            flags.append("超预算 {0}".format(_fmt((plan.payable or 0) - (result["budget"] or 0))))
        if plan.over_kcal:
            flags.append("超热量 {0:.0f} kcal".format((plan.kcal or 0) - (result["max_kcal"] or 0)))
        if plan.under_protein:
            if plan.protein_unknown:
                flags.append("蛋白质未知（菜单缺 nutrition 数据）")
            else:
                flags.append("蛋白质不足 {0:.0f} g".format((result["min_protein"] or 0) - (plan.protein or 0)))
        if plan.over_sodium:
            flags.append("超钠 {0:.0f} mg".format((plan.sodium or 0) - (result["max_sodium"] or 0)))
        lines.append("  {0}. {1}".format(idx, plan.label))
        kcal_part = " ｜ 热量 {0:.0f} kcal".format(plan.kcal) if plan.kcal is not None else ""
        nutri_part = ""
        if plan.protein is not None:
            nutri_part = " ｜ 蛋白 {0:.0f} g ｜ 钠 {1:.0f} mg".format(plan.protein, plan.sodium or 0)
        lines.append("     实付 {0}{1}{2} ｜ 省 {3}（{4:.0f}%）{5}".format(
            _fmt(plan.payable), kcal_part, nutri_part, _fmt(saving), ratio, mark))
        if flags:
            lines.append("     ⚠️ {0}".format("；".join(flags)))
        if plan.note:
            lines.append("     {0}{1}".format(plan.note, ADDON_HINT))
    if result.get("invalid"):
        lines.append("")
        lines.append("（另有 {0} 个候选方案因未达券门槛或计价失败被过滤）".format(result["invalid"]))
    lines.append("")
    lines.append("说明：{0}；最终价格以下单前 calculate-price 返回为准。".format(mode_label))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 演示数据
# ---------------------------------------------------------------------------
DEMO_MENU = {
    "storeCode": "DEMO01", "orderType": 1,
    "items": [
        {"mealCode": "M1", "name": "巨无霸", "price": 25.0, "category": "汉堡", "kcal": 550,
         "protein": 25.0, "sodium": 1010.0},
        {"mealCode": "M2", "name": "麦辣鸡腿堡", "price": 22.0, "category": "汉堡", "kcal": 520,
         "protein": 22.0, "sodium": 1130.0},
        {"mealCode": "M3", "name": "中薯条", "price": 12.0, "category": "小食", "kcal": 330,
         "protein": 4.0, "sodium": 270.0},
        {"mealCode": "M4", "name": "中可乐", "price": 9.5, "category": "饮品", "kcal": 210,
         "protein": 0.0, "sodium": 10.0},
        {"mealCode": "M5", "name": "麦辣鸡腿堡三件套(堡+中薯+中可)", "price": 33.5,
         "category": "套餐", "kcal": 940, "contains": ["M2", "M3", "M4"],
         "protein": 26.0, "sodium": 1410.0},
        {"mealCode": "M6", "name": "1+1随心配(任选两件)", "price": 13.5, "category": "套餐", "kcal": 480,
         "protein": 15.0, "sodium": 860.0},
        {"mealCode": "M7", "name": "脆薯饼", "price": 7.0, "category": "小食", "kcal": 280,
         "protein": 2.0, "sodium": 340.0},
    ],
}
DEMO_WANTS = [{"mealCode": "M5", "name": "麦辣鸡腿堡三件套", "quantity": 1}]
DEMO_COUPONS = [
    {"couponId": "C3", "title": "满30减6", "threshold": 30.0, "discount": 6.0},
    {"couponId": "C1", "title": "到店取餐9折券", "threshold": 0.0, "discount": 3.35},
    {"couponId": "C2", "title": "满40减10", "threshold": 40.0, "discount": 10.0},
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="optimizer",
        description="麦麦省钱助手 · 券组合优化器——枚举候选方案，真实/估算计价，输出最优组合。",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    plan = sub.add_parser("plan", help="生成并排序候选方案")
    plan.add_argument("--wants", required=True, help="想吃清单 JSON 文件")
    plan.add_argument("--menu", required=True, help="菜单与价格 JSON 文件")
    plan.add_argument("--coupons", required=True, help="可用券 JSON 文件")
    plan.add_argument("--mcp", action="store_true",
                      help="真实计价模式：调用官方 calculate-price（需要 MCP Token）")
    plan.add_argument("--store-code", default="", help="真实计价模式必填：门店编码")
    plan.add_argument("--order-type", type=int, default=1, help="1=到店(默认) 2=外送")
    plan.add_argument("--be-code", default="",
                      help="外送/得来速场景的业务编码（由 query-nearby-stores / "
                           "delivery-query-stores 返回；到店自取不需要）")
    plan.add_argument("--need-tableware", action="store_true",
                      help="需要餐具（默认不需要，官方计价结果按此计算）")
    plan.add_argument("--with-order", default="",
                      help="随单购参数（JSON 原文，如 "
                           "'{\"cardType\":2,\"cardId\":\"...\"}'）")
    plan.add_argument("--top", type=int, default=3, help="输出前 N 个方案（默认 3）")
    plan.add_argument("--no-deals", action="store_true",
                      help="不自动衔接团购终局建议（默认：本地券库非空时自动输出）")
    plan.add_argument("--mcp-top-k", type=int, default=8,
                      help="真实计价模式下用本地估算预筛前 K 个方案再核价（默认 8，0=全量核价）")
    plan.add_argument("--budget", type=float, default=None, help="实付预算上限（元），超支方案排后并打标")
    plan.add_argument("--max-kcal", type=float, default=None, help="热量上限（kcal），菜单含 kcal 字段时生效")
    plan.add_argument("--min-protein", type=float, default=None,
                      help="蛋白质下限（g），菜单含 protein 字段时生效；数据缺失的方案按不满足处理")
    plan.add_argument("--max-sodium", type=float, default=None,
                      help="钠上限（mg），菜单含 sodium 字段时生效；数据缺失的方案按不满足处理")
    plan.add_argument("--json", dest="as_json", action="store_true", help="JSON 输出")

    demo = sub.add_parser("demo", help="离线演示（内嵌示例数据，估算模式）")
    demo.add_argument("--no-deals", action="store_true",
                      help="不自动衔接团购终局建议")
    return parser


def run_plan(args: argparse.Namespace) -> int:
    try:
        wants = _load_json(args.wants)
        menu = _load_json(args.menu)
        coupons = _load_json(args.coupons)
    except (OSError, json.JSONDecodeError) as exc:
        print("错误: 无法读取数据文件：{0}".format(exc), file=sys.stderr)
        return EXIT_USAGE
    if not isinstance(wants, list) or not isinstance(menu, dict) or not isinstance(coupons, list):
        print("错误: 数据文件结构不正确（wants/coupons 应为数组，menu 应为对象）。", file=sys.stderr)
        return EXIT_USAGE

    if args.mcp:
        try:
            from mcd_client import McdMcpClient, load_token  # 延迟导入，估算模式零依赖
        except ImportError:  # pragma: no cover - 路径异常时提示
            print("错误: 无法导入 mcd_client，请从项目根目录运行。", file=sys.stderr)
            return EXIT_USAGE
        token = load_token()
        if not token:
            print("错误: 真实计价模式需要 MCP Token（MCD_MCP_TOKEN 环境变量）。", file=sys.stderr)
            return EXIT_USAGE
        client = McdMcpClient(token=token)
        client._store_code = args.store_code or menu.get("storeCode", "")
        client._order_type = args.order_type or menu.get("orderType", 1)
        client._be_type = 2 if int(client._order_type) == 2 else 1
        # 随单购参数：用户给 JSON 原文，非法则明确报错（不静默忽略）
        with_order = {}
        if getattr(args, "with_order", ""):
            try:
                with_order = json.loads(args.with_order)
            except (ValueError, TypeError):
                print("错误: --with-order 需为合法 JSON。", file=sys.stderr)
                return EXIT_USAGE
        # 传入本地估算函数：用于判定官方返回的金额单位是「分」还是「元」
        price_fn = make_mcp_pricer(
            client,
            local_fn=make_local_pricer(menu),
            need_tableware=bool(getattr(args, "need_tableware", False)),
            with_order=with_order,
            be_code=str(getattr(args, "be_code", "") or ""),
        )
        mode_label = "真实计价模式（官方 calculate-price）"
    else:
        price_fn = make_local_pricer(menu)
        mode_label = "估算模式（本地计价，未经验证）"

    plans = build_candidates(wants, coupons, menu)
    # 两阶段计价（v2.1.1）：真实核价按调用次数计延迟——先用本地估算排序预筛
    # Top-K，仅对前 K 个方案走 calculate-price，典型调用次数降 60%+；
    # K=0 时退化为全量核价（与原行为一致）
    if args.mcp and getattr(args, "mcp_top_k", 0) > 0 and len(plans) > args.mcp_top_k:
        total = len(plans)
        plans = prefilter_plans(plans, menu, args.mcp_top_k)
        mode_label = "真实计价模式（官方 calculate-price；本地估算预筛 Top-{0}，共 {1} 个候选）".format(
            args.mcp_top_k, total)
    kcal_table = {i["mealCode"]: float(i["kcal"]) for i in menu.get("items", [])
                  if isinstance(i.get("kcal"), (int, float))}
    nutrition_table = {
        i["mealCode"]: {"protein": i["protein"], "sodium": i["sodium"]}
        for i in menu.get("items", [])
        if isinstance(i.get("protein"), (int, float)) and isinstance(i.get("sodium"), (int, float))
    }
    result = score_and_rank(plans, price_fn, top=args.top,
                            budget=args.budget,
                            max_kcal=args.max_kcal if kcal_table else None,
                            kcal_table=kcal_table or None,
                            min_protein=args.min_protein if nutrition_table else None,
                            max_sodium=args.max_sodium if nutrition_table else None,
                            nutrition_table=nutrition_table or None)

    if args.as_json:
        print(json.dumps({
            "mode": "mcp" if args.mcp else "estimate",
            "baseline": result["baseline"],
            "plans": [
                {"label": p.label, "payable": p.payable, "note": p.note,
                 "saving": (result["baseline"] - p.payable) if result["baseline"] and p.payable else None,
                 "kcal": p.kcal, "protein": p.protein, "sodium": p.sodium,
                 "cart": p.cart.entries}
                for p in result["ranked"]
            ],
            "filtered": result["invalid"],
        }, ensure_ascii=False, indent=2))
    else:
        print(render_report(result, mode_label))
        if not args.no_deals:
            cc = cross_channel_section(result)
            if cc:
                print(cc)
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "plan":
        return run_plan(args)
    if args.command == "demo":
        plans = build_candidates(DEMO_WANTS, DEMO_COUPONS, DEMO_MENU)
        kcal_table = {i["mealCode"]: float(i["kcal"]) for i in DEMO_MENU["items"]}
        result = score_and_rank(plans, make_local_pricer(DEMO_MENU), top=3,
                                kcal_table=kcal_table)
        print(render_report(result, "估算模式（本地计价，未经验证）"))
        if not args.no_deals:
            cc = cross_channel_section(result)
            if cc:
                print(cc)
        return EXIT_OK
    parser.print_help()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
