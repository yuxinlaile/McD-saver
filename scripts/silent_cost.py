#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦省钱助手 —— 沉默成本体检。

回答一个省钱工具很少回答的问题：「你正在白扔多少钱？」

四部分（全部来自官方 MCP 只读工具，零风险）：

- 临期券扫描：7 天内到期的券按面值合计，列出优先处理清单；
- 用券排程（v1.6）：过期窗口 × 历史点单频率 → 推算窗口内实际能消耗的
  点单次数，把券按净价值排序排入点单——「可实现金额」与「注定过期金额」
  一次算清。券不是越多越好，用得上才算数；
- 消费画像：近 N 单的订单数 / 总支出 / 客单价 / 高频复购单品
  （复购 ≥2 次的单品提示改套餐的省钱方向）；
- 积分体检：可用积分与本月/下月即将过期积分。

券面值实测（--probe，v1.6）：无面值字段/标题无金额的券，把券自带的商品码
与 couponId 传给官方 calculate-price，返回的 discount 即该券精确价值——
实测优先、估算兜底，绝不虚构。

数据获取（Agent 按 SKILL.md 工作流执行，JSON 原样保存即可）：

    python scripts/mcd.py call query-my-coupons --raw > coupons.json
    python scripts/mcd.py call order-list --raw > orders.json
    python scripts/mcd.py call query-my-account --raw > points.json
    python scripts/silent_cost.py report --coupons coupons.json --orders orders.json \
        --points points.json

解析策略：对每个字段做宽容匹配（常见命名变体 + 标题正则兜底），
识别不到的字段明确标注"未识别"，绝不猜测编造。

示例::

    python scripts/silent_cost.py demo                          # 离线演示
    python scripts/silent_cost.py demo --html report.html       # 生成可分享单文件 HTML
    python scripts/silent_cost.py report --coupons c.json --probe --store-code ST001
退出码：0 成功 · 1 用法/数据错误
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from console import ensure_utf8_stdio

EXIT_OK = 0
EXIT_USAGE = 1

EXPIRING_DAYS = 7

# 常见字段命名变体（按优先级）
FACE_KEYS = ["parValue", "faceValue", "worth", "face", "discountValue"]
EXPIRE_KEYS = ["validityEndTime", "validUntil", "endTime", "expireTime", "expireDate",
               "tradeEndDateTime", "tradeDateTime"]
AMOUNT_KEYS = ["totalAmount", "payable", "payAmount", "amount", "totalPrice", "total"]
TIME_KEYS = ["createTime", "orderTime", "ctime", "time", "orderDate"]
NAME_KEYS = ["name", "title", "dishName", "productName"]
POINTS_AVAILABLE_KEYS = ["availablePoint", "availablePoints", "points", "balance"]
POINTS_EXPIRE_KEYS = ["currentMouthExpirePoint", "nextMouthExpirePoint",
                      "expirePoint", "expiringPoints"]


# ---------------------------------------------------------------------------
# 宽容字段提取
# ---------------------------------------------------------------------------
def _first_key(obj: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
    return None


def _parse_json_payload(text: str) -> Any:
    """从一段文本里取 JSON：支持纯 JSON，也支持 Markdown 包裹（``## Original Response`` 之后的真实 JSON）。"""
    candidate = text.strip()
    if "## Original Response" in candidate:
        candidate = candidate.rsplit("## Original Response", 1)[-1].strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if "\n" in candidate:
            candidate = candidate.split("\n", 1)[-1].strip()
    try:
        return json.loads(candidate)
    except (ValueError, TypeError):
        return None


def _unwrap(raw: Any) -> List[Dict[str, Any]]:
    """从工具原始响应中提取记录数组。

    兼容形态：``{"data": [...]}`` / ``{"data": {"list": [...]}}`` / ``{"coupons": [...]}`` /
    ``[...]`` / tools/call 的 ``{"content": [{"type": "text", "text": "..."}]}``（文本可能是纯 JSON，
    也可能是 ``## Original Response`` 包裹的 Markdown）。

    空数据的中文文案（如「暂无可用优惠券」）会被识别为**空列表**，而不是被当成一条记录。
    """
    data = raw
    if isinstance(raw, dict):
        # 官方 MCP 的结构化载荷优先：券的 couponId/couponCode 只在 structuredContent 里，
        # 文本 content 是给人看的 Markdown 表格（不含这些字段）。
        structured = raw.get("structuredContent")
        if isinstance(structured, dict) and structured.get("data") is not None:
            data = structured
        elif "content" in raw:
            texts = [c.get("text", "") for c in raw["content"] if isinstance(c, dict) and c.get("type") == "text"]
            for text in texts:
                parsed = _parse_json_payload(text)
                if parsed is not None:
                    data = parsed
                    break
            else:
                return []  # 空态文案或非 JSON 文本：没有记录
    if isinstance(data, dict):
        # 下探一层：官方常把记录放在 data.coupons / data.list 之类的一层嵌套里
        inner = data.get("data")
        if isinstance(inner, dict):
            data = inner
        for key in ("data", "coupons", "orders", "list", "records", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict) and isinstance(value.get("list"), list):
                return [x for x in value["list"] if isinstance(x, dict)]
        for key, value in data.items():
            if key == "content":
                continue
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
        return []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def _parse_amount(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # 保留负号：退款/冲正金额在订单里以负数出现，丢掉符号会被当成正常消费。
        # 负号与数字之间可能夹着货币符号（如 "-¥12.50"），需一起匹配。
        match = re.search(r"(-)?\s*[¥￥$]?\s*(\d+(?:\.\d+)?)", value.replace(",", ""))
        if match:
            number = float(match.group(2))
            return -number if match.group(1) else number
    return None


def _parse_expire_days(value: Any, today: datetime) -> Optional[int]:
    """解析有效期并返回距今天数；支持日期字符串与毫秒时间戳。"""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        # 毫秒时间戳（13 位）或秒时间戳（10 位）
        seconds = float(value) / 1000.0 if float(value) > 1e12 else float(value)
        try:
            end = datetime.fromtimestamp(seconds)
            return (end.date() - today.date()).days
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            end = datetime.strptime(text[: len(fmt) + 2].strip(), fmt)
            return (end.date() - today.date()).days
        except ValueError:
            continue
    match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if match:
        try:
            end = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            return (end.date() - today.date()).days
        except ValueError:
            return None
    return None


def _coupon_threshold(coupon: Dict[str, Any]) -> Optional[float]:
    """解析满减门槛（元）：字段优先，标题正则兜底（「满X减Y」）。"""
    threshold = _parse_amount(_first_key(coupon, ["spendLine", "threshold", "minSpend", "minOrderAmount"]))
    if threshold is not None and threshold > 0:
        return threshold
    title = str(coupon.get("title") or coupon.get("couponName") or "")
    match = re.search(r"满(\d+(?:\.\d+)?)减", title)
    if match:
        return float(match.group(1))
    return None


def _coupon_face(coupon: Dict[str, Any]) -> Optional[float]:
    face = _parse_amount(_first_key(coupon, FACE_KEYS))
    if face is None:
        # 官方 query-my-coupons 的结构：{"discountInfo": {"discountValue": "9.9", ...}}
        # discountValue 是「用券价格」（元），不是面额
        info = coupon.get("discountInfo")
        if isinstance(info, dict):
            face = _parse_amount(info.get("discountValue"))
    if face is not None:
        return face
    title = str(coupon.get("title") or coupon.get("couponName") or "")
    match = re.search(r"(?:减|抵)(\d+(?:\.\d+)?)", title)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*元", title)
    if match:
        return float(match.group(1))
    return None


# ---------------------------------------------------------------------------
# 分析逻辑
# ---------------------------------------------------------------------------
def analyze_coupons(coupons_raw: Any, today: Optional[datetime] = None) -> Dict[str, Any]:
    today = today or datetime.now()
    records = _unwrap(coupons_raw)
    expiring: List[Dict[str, Any]] = []
    unrecognized = 0
    for coupon in records:
        days = _parse_expire_days(_first_key(coupon, EXPIRE_KEYS), today)
        face = _coupon_face(coupon)
        if days is None:
            unrecognized += 1
            continue
        if 0 <= days <= EXPIRING_DAYS:
            title = str(coupon.get("title") or coupon.get("couponName") or coupon.get("couponId") or "未命名券")
            expiring.append({"title": title, "face": face, "days": days,
                             "threshold": _coupon_threshold(coupon),
                             "couponId": coupon.get("couponId"),
                             "productCode": _first_key(coupon, ["productCode", "itemCode", "goodsCode", "mealCode"])})
    expiring.sort(key=lambda c: c["days"])
    return {
        "total": len(records),
        "expiring": expiring,
        "expiring_face_total": sum(c["face"] or 0.0 for c in expiring),
        "unrecognized": unrecognized,
    }


def analyze_orders(orders_raw: Any, today: Optional[datetime] = None) -> Dict[str, Any]:
    today = today or datetime.now()
    records = _unwrap(orders_raw)
    amounts: List[float] = []
    order_days: List[datetime] = []
    item_counter: Dict[str, int] = {}
    unrecognized = 0
    free_count = 0
    refund_count = 0
    for order in records:
        amount = _parse_amount(_first_key(order, AMOUNT_KEYS))
        if amount is None:
            unrecognized += 1
        elif amount > 0:
            # 消费口径：0 元订单（券核销/积分兑换）不计入客单价——
            # 拿它当「不看券时的自然消费基准」是循环论证，会系统性拉低基准
            #（消费口径与点单口径分离）
            amounts.append(amount)
        elif amount < 0:
            # 退款/冲正：既不是消费也不是 0 元订单，单独计数并从客单价口径排除
            refund_count += 1
        else:
            free_count += 1
        when = _first_key(order, TIME_KEYS)
        if when is not None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    order_days.append(datetime.strptime(str(when)[:len(fmt) + 2].strip(), fmt))
                    break
                except ValueError:
                    continue
        items = order.get("items") or order.get("orderItems") or order.get("products") or []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    name = _first_key(item, NAME_KEYS)
                    qty = item.get("quantity") or item.get("count") or 1
                else:
                    name, qty = item, 1
                if name:
                    item_counter[str(name)] = item_counter.get(str(name), 0) + max(1, int(qty or 1))
    top_items = sorted(item_counter.items(), key=lambda kv: kv[1], reverse=True)[:3]
    total = sum(amounts)
    # 点单频率：以最早订单日为观测起点（含当天），单位：单/天
    frequency = None
    if order_days:
        span = max((today - min(order_days)).days, 1)
        frequency = len(order_days) / span
    return {
        "order_count": len(records),
        "amount_count": len(amounts),
        "free_order_count": free_count,
        "refund_order_count": refund_count,
        "total_spend": total if amounts else None,
        "avg_ticket": (total / len(amounts)) if amounts else None,
        "order_frequency": frequency,
        "top_items": [{"name": n, "count": c} for n, c in top_items if c >= 2],
        "unrecognized": unrecognized,
    }


# ---------------------------------------------------------------------------
# 用券排程（v1.6）：过期窗口 × 点单频率 → 可实现 vs 注定过期
# ---------------------------------------------------------------------------
def schedule_coupons(coupons: Dict[str, Any], orders: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """把临期券按**净价值**降序排入「过期窗口内的预期点单次数」。

    净价值 = 券面价值 − max(0, 满减门槛 − 自然消费基准)——
    满减门槛远超客单价的券是「纸面富贵」，名义面值再高也不排入。

    窗口 = 临期券中最早到期的天数；预期点单次数 = 点单频率 × 窗口
    （向下取整，至少 1）。净价值 ≤ 0 的券标记为 paper（劝退），
    排不进点单的标记为 missed——名义面值再高，用不上就不算钱。
    数据不足（无频率或无临期券）返回 None。
    """
    expiring = [c for c in coupons.get("expiring", []) if c.get("face") is not None]
    frequency = orders.get("order_frequency")
    avg_ticket = orders.get("avg_ticket")
    if not expiring or frequency is None:
        return None
    window = max(min(c["days"] for c in expiring), 1)
    expected_orders = max(1, int(frequency * window))
    # 净价值判定
    judged = []
    for coupon in expiring:
        entry = dict(coupon)
        threshold = coupon.get("threshold")
        if threshold and avg_ticket is not None and threshold > avg_ticket:
            entry["net_value"] = round(max(0.0, (coupon["face"] or 0.0) - (threshold - avg_ticket)), 2)
        else:
            entry["net_value"] = coupon["face"]  # 无门槛或门槛内：净价值=面值
        entry["category"] = "paper" if entry["net_value"] <= 0 else "worth"
        judged.append(entry)
    # 排程：净价值 > 0 的券按净价值降序排入点单次数
    worth = [c for c in judged if c["category"] == "worth"]
    worth.sort(key=lambda c: (c["net_value"] or 0.0), reverse=True)
    scheduled, missed = [], []
    for idx, coupon in enumerate(worth):
        entry = dict(coupon)
        if idx < expected_orders:
            entry["slot"] = "第 {0} 单".format(idx + 1)
            scheduled.append(entry)
        else:
            entry["slot"] = "排不上"
            missed.append(entry)
    # paper（纸面富贵）单独列出，计入 doomed 但不计入可实现
    for coupon in [c for c in judged if c["category"] == "paper"]:
        entry = dict(coupon)
        entry["slot"] = "纸面富贵"
        missed.append(entry)
    realizable = sum(c["net_value"] for c in scheduled)
    doomed = sum((c["face"] or 0.0) for c in missed)
    return {
        "window_days": window,
        "expected_orders": expected_orders,
        "frequency": frequency,
        "scheduled": scheduled,
        "missed": missed,
        "realizable": realizable,
        "doomed": doomed,
        "face_total": realizable + doomed,
    }


# ---------------------------------------------------------------------------
# 券面值实测（v1.6）：calculate-price 带 couponId 实测，估算兜底
# ---------------------------------------------------------------------------
def probe_coupon_value(client: Any, coupon: Dict[str, Any]) -> Optional[float]:
    """把券商品码（若有）与 couponId 传给官方 calculate-price，实测券精确价值。

    返回值口径：响应中的 discount 字段（券抵扣金额）。任何一步解析失败
    返回 None——调用方应保留估算值并标注「估算」，绝不虚构实测结果。
    """
    product_code = coupon.get("productCode")
    coupon_id = coupon.get("couponId")
    if not coupon_id:
        return None
    products = [{"mealCode": product_code, "quantity": 1}] if product_code else []
    args: Dict[str, Any] = {
        "storeCode": getattr(client, "_store_code", ""),
        "orderType": getattr(client, "_order_type", 1),
    }
    if products:
        args["products"] = products
    args["couponId"] = coupon_id
    try:
        result = client.call_tool("calculate-price", args)
    except Exception:  # noqa: BLE001 - 工具层任何失败都不应中断体检
        return None
    data = result.get("data", result) if isinstance(result, dict) else {}
    discount = None
    for key in ("discount", "couponDiscount", "discountAmount", "couponAmount"):
        value = _first_key(data, [key]) if isinstance(data, dict) else None
        parsed = _parse_amount(value)
        if parsed is not None:
            discount = parsed
            break
    return discount


def analyze_points(points_raw: Any) -> Dict[str, Any]:
    if not isinstance(points_raw, dict) and not isinstance(points_raw, list):
        return {"available": None, "unrecognized": 1}
    data: Any = points_raw
    if isinstance(points_raw, dict) and "content" in points_raw:
        data = _unwrap({"content": points_raw["content"], "keep": 1})  # 复用文本壳解包
        data = data[0] if data else points_raw
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return {"available": None, "unrecognized": 1}
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    available = _parse_amount(_first_key(inner, POINTS_AVAILABLE_KEYS))
    expiring_now = _parse_amount(_first_key(inner, ["currentMouthExpirePoint"]))
    expiring_next = _parse_amount(_first_key(inner, ["nextMouthExpirePoint"]))
    return {"available": available, "expiring_now": expiring_now,
            "expiring_next": expiring_next,
            "unrecognized": 0 if available is not None else 1}


def analyze_mall(mall_raw: Any) -> Dict[str, Any]:
    """积分商城影子价格：max(面值 ÷ 积分) = 这些积分最优兑换能换回的现金效率。

    mall_raw 兼容 {"data": [...]} 与 [...]，商品需含积分与面值字段
    （常见命名：points/needPoint 与 worth/price/faceValue）。
    """
    products = _unwrap(mall_raw) if mall_raw else []
    best: Optional[Dict[str, Any]] = None
    for p in products:
        pts = _parse_amount(_first_key(p, ["points", "needPoint", "point", "price2"]))
        worth = _parse_amount(_first_key(p, ["worth", "price", "faceValue", "value"]))
        name = _first_key(p, NAME_KEYS) or "未命名商品"
        if pts and pts > 0 and worth is not None:
            efficiency = worth / pts
            if best is None or efficiency > best["efficiency"]:
                best = {"name": str(name), "points": pts, "worth": worth, "efficiency": efficiency}
    return {"shadow_price": best["efficiency"] if best else None,
            "best_product": best, "products": len(products)}


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def _fmt(value: Optional[float]) -> str:
    return "¥{0:.2f}".format(value) if value is not None else "未识别"


def render_report(coupons: Dict[str, Any], orders: Dict[str, Any],
                  points: Dict[str, Any], mall: Optional[Dict[str, Any]] = None,
                  schedule: Optional[Dict[str, Any]] = None) -> str:
    lines: List[str] = []
    lines.append("=" * 68)
    lines.append("麦麦省钱助手 · 沉默成本体检报告")
    lines.append("=" * 68)

    lines.append("")
    lines.append("【一】临期券（{0} 天内到期）".format(EXPIRING_DAYS))
    if coupons["expiring"]:
        for c in coupons["expiring"]:
            if c.get("face_source") == "measured":
                face = "¥{0:.2f}（实测）".format(c["face"])
            else:
                face = "¥{0:.2f}".format(c["face"]) if c["face"] is not None else "面值未识别（可用 --probe 实测）"
            lines.append("  · {0} ｜ {1} ｜ 还剩 {2} 天".format(c["title"], face, c["days"]))
        lines.append("  合计面值：{0}".format(_fmt(coupons["expiring_face_total"])))
        lines.append("  建议：优先用掉临期券——过期即沉没，凑单达标也比浪费划算。")
    else:
        lines.append("  近 {0} 天内没有临期券。".format(EXPIRING_DAYS))
    if coupons["unrecognized"]:
        lines.append("  （{0} 张券的有效期字段未识别，已跳过）".format(coupons["unrecognized"]))

    if schedule:
        lines.append("")
        lines.append("【一·B】用券排程（窗口 {0} 天 × 频率 {1:.3f} 单/天 ≈ {2} 单）".format(
            schedule["window_days"], schedule["frequency"], schedule["expected_orders"]))
        lines.append("  券不是越多越好，用得上才算数：")
        for c in schedule["scheduled"]:
            lines.append("    {0} → {1} ｜ {2} ｜ 净价值 ¥{3:.2f}".format(
                c["slot"], c["title"], "还剩 {0} 天".format(c["days"]), c["net_value"]))
        paper = [c for c in schedule["missed"] if c.get("category") == "paper"]
        if paper:
            lines.append("  纸面富贵（门槛远超客单价，建议放弃）：")
            for c in paper:
                lines.append("    · {0} ｜ 面值 ¥{1:.2f} ｜ 净价值 ¥{2:.2f}".format(
                    c["title"], c["face"], c["net_value"]))
        if schedule["missed"]:
            lines.append("  排不上（注定随券过期浪费 ¥{0:.2f}）：".format(schedule["doomed"]))
            for c in schedule["missed"]:
                if c.get("category") != "paper":
                    lines.append("    · {0} ｜ ¥{1:.2f} ｜ 还剩 {2} 天".format(c["title"], c["face"], c["days"]))
        lines.append("  名义 ¥{0:.2f} → 可实现（净价值）¥{1:.2f}，注定过期 ¥{2:.2f}。".format(
            schedule["face_total"], schedule["realizable"], schedule["doomed"]))
        lines.append("  本月最该做的事：把排得上的券优先用掉——这笔钱不用就是纯损失。")

    lines.append("")
    lines.append("【二】消费画像（近 {0} 单）".format(orders["order_count"]))
    if orders["amount_count"]:
        lines.append("  订单数：{0} 单 ｜ 总支出：{1} ｜ 客单价：{2}".format(
            orders["order_count"], _fmt(orders["total_spend"]), _fmt(orders["avg_ticket"])))
        if orders.get("free_order_count"):
            lines.append("  （另有 {0} 笔 0 元订单——多为券核销或积分兑换，不计入客单价，但算一次点单机会）".format(
                orders["free_order_count"]))
        if orders["top_items"]:
            lines.append("  高频单品：")
            for item in orders["top_items"]:
                lines.append("    · {0} × {1} 次——若改点对应套餐，通常每单还能再省一些。".format(
                    item["name"], item["count"]))
    else:
        lines.append("  暂无可识别的历史订单金额。")
    if orders.get("refund_order_count"):
        lines.append("  （另有 {0} 笔退款/冲正订单：金额为负，不计入总支出与客单价）".format(
            orders["refund_order_count"]))
    if orders["unrecognized"]:
        lines.append("  （{0} 单金额字段未识别，已跳过）".format(orders["unrecognized"]))

    lines.append("")
    lines.append("【三】积分体检")
    if points["available"] is not None:
        lines.append("  可用积分：{0:.0f}".format(points["available"]))
        if points.get("expiring_now"):
            lines.append("  本月将过期：{0:.0f}（优先级最高，过期即清零）".format(points["expiring_now"]))
        if points.get("expiring_next"):
            lines.append("  下月将过期：{0:.0f}".format(points["expiring_next"]))
        lines.append("  建议：优先用积分兑换临期前会用到的餐品券。")
        if mall and mall.get("shadow_price"):
            shadow = mall["shadow_price"]
            lines.append("  积分价值估算：最优兑换「{0}」= {1:.4f} 元/积分"
                         "（口径：积分商城最优标的效率）".format(
                             mall["best_product"]["name"], shadow))
            lines.append("  可用积分折现 ≈ ¥{0:.2f}——用它判断「这单要不要动积分」的机会成本。".format(
                points["available"] * shadow))
    else:
        lines.append("  积分账户字段未识别（可先用 query-my-account 核对数据）。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 单文件 HTML 报告（v1.6）：零 CDN、双击打开即可截图分享
# ---------------------------------------------------------------------------
# HTML 渲染与等级逻辑已抽离至 silent_report.py（v2.1.2 拆分，保持向后兼容再导出）。
# 本模块只做再导出：不再重复定义 savings_grade，避免两份逻辑各自漂移。
try:  # 兼容“直接运行脚本”与“作为模块运行”两种方式
    from silent_report import render_html, savings_grade  # noqa: F401
except ImportError:  # pragma: no cover - 以模块方式导入时补脚本目录
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from silent_report import render_html, savings_grade  # noqa: F401


# ---------------------------------------------------------------------------
# 演示数据
# ---------------------------------------------------------------------------
DEMO_COUPONS = {"data": [
    {"title": "满50减12", "parValue": 12.0, "validityEndTime": "2026-10-13 23:59:59"},
    {"title": "免费脆薯饼", "parValue": 8.0, "validityEndTime": "2026-10-14 23:59:59"},
    {"title": "9.9元中杯冰美式", "parValue": 13.1, "validityEndTime": "2026-10-17 23:59:59"},
    {"title": "满30减5", "parValue": 5.0, "validityEndTime": "2026-12-31 23:59:59"},
]}
DEMO_ORDERS = {"data": [
    {"createTime": "2026-09-02", "totalAmount": 33.5,
     "items": [{"name": "麦辣鸡腿堡", "quantity": 1}]},
    {"createTime": "2026-09-11", "totalAmount": 36.0,
     "items": [{"name": "麦辣鸡腿堡", "quantity": 1}]},
    {"createTime": "2026-09-25", "totalAmount": 38.0,
     "items": [{"name": "麦辣鸡腿堡", "quantity": 1}, {"name": "中可乐", "quantity": 1}]},
    {"createTime": "2026-10-08", "totalAmount": 37.0,
     "items": [{"name": "麦辣鸡腿堡", "quantity": 1}]},
]}
DEMO_POINTS = {"data": {"availablePoint": 1200.0, "currentMouthExpirePoint": 300.0,
                        "nextMouthExpirePoint": 150.0}}
DEMO_MALL = {"data": [
    {"name": "中杯鲜煮咖啡券", "points": 500, "worth": 10.5},
    {"name": "麦辣鸡腿堡券", "points": 3000, "worth": 22.0},
    {"name": "巨无霸中套餐券", "points": 5000, "worth": 39.5},
]}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="silent_cost",
        description="麦麦省钱助手 · 沉默成本体检——临期券排程 + 消费画像 + 积分（数据来自官方 MCP 只读工具）。",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    report = sub.add_parser("report", help="生成体检报告")
    report.add_argument("--coupons", help="query-my-coupons 响应 JSON")
    report.add_argument("--orders", help="order-list 响应 JSON")
    report.add_argument("--points", help="query-my-account 响应 JSON")
    report.add_argument("--mall", help="积分商城商品列表 JSON（用于积分影子价格估算，可选）")
    report.add_argument("--html", metavar="PATH", help="同时输出单文件 HTML 报告（零依赖，可截图分享）")
    report.add_argument("--probe", action="store_true",
                        help="无面值券走 calculate-price 实测精确价值（需要 MCP Token）")
    report.add_argument("--store-code", default="", help="--probe 实测时的门店编码")
    demo = sub.add_parser("demo", help="离线演示（内嵌示例数据）")
    demo.add_argument("--html", metavar="PATH", help="同时输出单文件 HTML 报告（零依赖，可截图分享）")
    return parser


def _run_probe(coupons: Dict[str, Any], store_code: str) -> int:
    """对无面值临期券执行实测；成功则回填 face 并标记 face_source=measured。"""
    try:
        from mcd_client import McdMcpClient, load_token  # 延迟导入，离线路径零依赖
    except ImportError:  # pragma: no cover
        print("错误: 无法导入 mcd_client，请从项目根目录运行。", file=sys.stderr)
        return EXIT_USAGE
    token = load_token()
    if not token:
        print("提示: --probe 需要 MCP Token（MCD_MCP_TOKEN 环境变量），本次跳过实测。",
              file=sys.stderr)
        return EXIT_OK
    client = McdMcpClient(token=token)
    client._store_code = store_code
    client._order_type = 1
    probed = 0
    for coupon in coupons.get("expiring", []):
        if coupon.get("face") is not None:
            continue
        measured = probe_coupon_value(client, coupon)
        if measured is not None:
            coupon["face"] = measured
            coupon["face_source"] = "measured"
            probed += 1
    print("（实测完成：{0} 张券获得精确面值；其余保留估算或标注未识别）".format(probed),
          file=sys.stderr)
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "demo":
        coupons = analyze_coupons(DEMO_COUPONS, datetime(2026, 10, 12))
        orders = analyze_orders(DEMO_ORDERS, datetime(2026, 10, 12))
        points = analyze_points(DEMO_POINTS)
        schedule = schedule_coupons(coupons, orders)
        print(render_report(coupons, orders, points, analyze_mall(DEMO_MALL), schedule))
        if getattr(args, "html", None):
            _write_html(args.html, coupons, orders, points, schedule)
        return EXIT_OK

    if args.command == "report":
        try:
            coupons = analyze_coupons(_load_json(args.coupons) if args.coupons else {})
            orders = analyze_orders(_load_json(args.orders) if args.orders else {})
            points = analyze_points(_load_json(args.points) if args.points else {})
            mall = _load_json(args.mall) if args.mall else None
        except (OSError, ValueError) as exc:
            print("错误: 无法读取输入文件（{0}）：{1}".format(
                getattr(exc, "filename", "") or "输入文件", exc), file=sys.stderr)
            return EXIT_USAGE
        if getattr(args, "probe", None):
            code = _run_probe(coupons, getattr(args, "store_code", ""))
            if code != EXIT_OK:
                return code
        schedule = schedule_coupons(coupons, orders)
        print(render_report(coupons, orders, points, analyze_mall(mall), schedule))
        if getattr(args, "html", None):
            _write_html(args.html, coupons, orders, points, schedule)
        return EXIT_OK

    parser.print_help()
    return EXIT_OK


def _write_html(path: str, coupons: Dict[str, Any], orders: Dict[str, Any],
                points: Dict[str, Any], schedule: Optional[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_html(coupons, orders, points, None, schedule))
    print("HTML 报告已生成：{0}（双击打开即可截图分享）".format(path))


if __name__ == "__main__":
    sys.exit(main())
