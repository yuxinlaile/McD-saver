#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦省钱助手 —— 30 秒离线全链路演示（零 Token、零联网、零依赖）。

读取 fixtures/ 下与真实 MCP 响应**同格式**的 JSON 快照，原样跑通
「省钱四步检查 + 用券排程 + 跨渠道比价」全部业务逻辑：

    【领券前置】fixtures/available_coupons.json → 可领券清单（含价值未知券的如实标注）
    【选券】    fixtures/coupons.json          → 账户当前可用券
    【比价】    fixtures/menu.json             → optimizer 逐方案估算（套餐 vs 单点 vs 凑单）
    【积分评估】fixtures/points.json + mall.json → 影子价格与积分折现
    【沉默成本】fixtures/coupons+orders        → 临期券排程（可实现 vs 注定过期）
    【跨渠道】  fixtures/deals.json            → 美团/抖音团购同口径估算对比

数据来源说明（诚实声明）：fixtures 是**示例数据**，字段结构与真实 MCP 响应一致；
真实运行时同样的响应由 `python scripts/mcd.py call ...` 实时获取，
业务逻辑一字未改——因此本 demo 同时是全链路的回归测试
（tests/test_demo_pipeline.py 会对输出做断言）。

用法::

    python demo.py                 # 直接运行
    python demo.py --section 比价   # 只看某一段

退出码：0 成功
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))

from console import ensure_utf8_stdio  # noqa: E402
from optimizer import build_candidates, make_local_pricer, score_and_rank  # noqa: E402
from silent_cost import (  # noqa: E402
    analyze_coupons, analyze_mall, analyze_orders, analyze_points,
    render_report, schedule_coupons,
)

TODAY = datetime(2026, 10, 12)  # fixtures 采集基准日，保证输出稳定可复现
SNAPSHOT_DATE = "2026-10-12"

WANTS_COMBO = [
    {"mealCode": "M2", "name": "麦辣鸡腿堡", "quantity": 1},
    {"mealCode": "M3", "name": "中薯条", "quantity": 1},
    {"mealCode": "M4", "name": "中可乐", "quantity": 1},
]  # 单点组合：面值 22+12+9.5 = ¥43.5 → 套餐替换候选 ¥33.5


def _load(name: str) -> Any:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", name)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def section_claim(available: Dict[str, Any], menu: Dict[str, Any]) -> List[str]:
    codes = {i["mealCode"] for i in menu.get("items", [])}
    lines = ["【领券前置】可领取的券（免费领取，零成本）"]
    records = available.get("data", [])
    lines.append("  共 {0} 张可领：".format(len(records)))
    for c in records:
        name = c.get("couponName", "未命名券")
        if c.get("productCode") and c["productCode"] in codes:
            lines.append("    · {0}（商品码 {1}，菜单可匹配，领取后可实测价值）".format(name, c["productCode"]))
        else:
            lines.append("    · {0}（【无法判断】菜单快照中无对应商品——我们不猜，"
                         "领取后可用「带券计价」实测）".format(name))
    lines.append("  真实运行时此清单来自 auto-bind-coupons / available-coupons 实时返回。")
    return lines


def section_pick(coupons: Dict[str, Any]) -> List[str]:
    records = coupons.get("data", [])
    lines = ["【选券】账户当前可用券 {0} 张：".format(len(records))]
    for c in records:
        lines.append("    · {0} ｜ 面值 ¥{1:.2f} ｜ 有效期至 {2}".format(
            c.get("couponName", "未命名券"), float(c.get("parValue") or 0),
            str(c.get("validityEndTime", ""))[:10]))
    return lines


def section_price(menu: Dict[str, Any]) -> List[str]:
    plans = build_candidates(WANTS_COMBO, [], menu)
    result = score_and_rank(plans, make_local_pricer(menu), top=3)
    lines = ["【比价】想吃「堡+薯+可乐」——估算模式（本地计价，未经验证）"]
    baseline = result["baseline"]
    lines.append("  基准（无券直点单点组合）：¥{0:.2f}".format(baseline))
    for idx, plan in enumerate(result["ranked"], 1):
        saving = baseline - (plan.payable or 0.0)
        mark = "  ← 最优" if idx == 1 else ""
        note = "（{0}）".format(plan.note) if plan.note else ""
        lines.append("  {0}. {1}{2} ｜ 实付 ¥{3:.2f} ｜ 省 ¥{4:.2f}{5}".format(
            idx, plan.label or "无券直点", note, plan.payable or 0.0, saving, mark))
    lines.append("  同样吃到「堡+薯+可乐」：单点 ¥43.5，改点套餐 ¥33.5，差 ¥10——这就是算法要找的 gap。")
    lines.append("  真实运行时每个候选都经官方 calculate-price 逐方案核价后才能作为下单依据。")
    return lines


def section_points(points: Dict[str, Any], mall: Dict[str, Any]) -> List[str]:
    account = analyze_points(points)
    shadow = analyze_mall(mall)
    lines = ["【积分评估】"]
    if account.get("available") is not None:
        lines.append("  可用积分 {0:.0f}，本月将过期 {1:.0f}。".format(
            account["available"], account.get("expiring_now") or 0))
    if shadow.get("shadow_price"):
        lines.append("  积分影子价格：最优「{0}」= {1:.4f} 元/积分 → 可用积分折现 ≈ ¥{2:.2f}。".format(
            shadow["best_product"]["name"], shadow["shadow_price"],
            (account.get("available") or 0) * shadow["shadow_price"]))
        lines.append("  用它判断「这一单要不要动积分」——机会成本一目了然。")
    return lines


def section_silent_cost(coupons: Dict[str, Any], orders: Dict[str, Any],
                        points: Dict[str, Any], mall: Dict[str, Any]) -> List[str]:
    ca = analyze_coupons(coupons, TODAY)
    oa = analyze_orders(orders, TODAY)
    pa = analyze_points(points)
    ma = analyze_mall(mall)
    schedule = schedule_coupons(ca, oa)
    text = render_report(ca, oa, pa, ma, schedule)
    lines = ["【沉默成本】临期券排程——回答「你正在白扔多少钱」"]
    # 跳过 silent_cost 报告自带的标题与分隔线（前 3 行），保留正文
    body = [ln for ln in text.splitlines()[3:] if not set(ln.strip()) <= {"="}]
    lines.extend(body if body else ["  近 7 天内没有临期券。"])
    return lines


def section_cross_channel() -> List[str]:
    lines = ["【跨渠道】美团/抖音团购 vs 官方（同口径估算）"]
    deals_list = _load("deals.json").get("deals", [])
    if not deals_list:
        return lines + ["  （券库为空，跳过）"]
    best = deals_list[0]
    mcd_face, mcd_price = 46.5, 46.5
    discount_rate = (best["price"] / best["face"]) * 100.0
    est = mcd_face * (best["price"] / best["face"])
    lines.append("  [{0}] {1} ｜ 售价 ¥{2:.2f} / 面值 ¥{3:.2f} = 折扣率 {4:.1f}%".format(
        best["platform"], best["title"], best["price"], best["face"], discount_rate))
    lines.append("  同内容估算到手 ¥{0:.2f} ｜ 对比官方单点 ¥{1:.2f} ｜ {2}".format(
        est, mcd_price, "建议用团购券（记得核对适用门店/时段与不可叠加限制）" if est < mcd_price else "官方渠道更优"))
    lines.append("  估算口径：按面值比例折算到当前购物车内容；真实决策以各平台页面为准。")
    return lines


def build_report(only: str = "") -> str:
    available = _load("available_coupons.json")
    coupons = _load("coupons.json")
    menu = _load("menu.json")
    orders = _load("orders.json")
    points = _load("points.json")
    mall = _load("mall.json")

    sections = {
        "领券": section_claim(available, menu),
        "选券": section_pick(coupons),
        "比价": section_price(menu),
        "积分": section_points(points, mall),
        "沉默成本": section_silent_cost(coupons, orders, points, mall),
        "跨渠道": section_cross_channel(),
    }
    order = ["领券", "选券", "比价", "积分", "沉默成本", "跨渠道"]

    lines: List[str] = []
    lines.append("=" * 68)
    lines.append("麦麦省钱助手 · 省钱四步检查 全链路演示（离线 fixtures 模式）")
    lines.append("数据快照：{0} · 字段结构与真实 MCP 响应一致 · 业务逻辑零改动".format(SNAPSHOT_DATE))
    lines.append("=" * 68)
    for name in order:
        if only and only not in name:
            continue
        lines.append("")
        lines.extend(sections[name])
    lines.append("")
    lines.append("本演示输出由 tests/test_demo_pipeline.py 断言——demo 即回归测试。")
    lines.append("真实运行：配置 Token 后 `python scripts/mcd.py check` 开始，四步检查自动执行。")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(prog="demo", description="麦麦省钱助手 30 秒离线全链路演示")
    parser.add_argument("--section", default="", help="只看某一段（领券/选券/比价/积分/沉默成本/跨渠道）")
    args = parser.parse_args(argv)
    print(build_report(args.section))
    return 0


if __name__ == "__main__":
    sys.exit(main())
