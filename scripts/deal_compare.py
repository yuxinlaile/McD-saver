#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦省钱助手 —— 外部团购比价引擎。

将用户从美团、抖音等团购平台查询到的麦当劳相关团购券信息录入本地券库，
并与麦当劳官方渠道（MCP calculate-price 计算出的最优实付价）进行比价，
输出"官方渠道 vs 团购"的推荐决策。

设计说明
--------
美团、抖音等平台**未提供面向第三方的公开 API**，因此本模块采用"人工录入 +
本地券库"的诚实设计：用户在团购 App 中查询到券的标题、价格、面值、限制条件后，
通过 `add` 子命令录入，`compare` 子命令负责折算与决策。

所有比价结果均为**估算值**，仅供购买决策辅助；实际价格、限制与可用性
以各平台页面与麦当劳官方渠道实时结果为准。

数据文件
--------
默认存储于 ``~/.maimai_saver/deals.json``，可用环境变量 ``MAIMAI_DEALS_FILE``
或 ``--file`` 参数覆盖。

子命令
------
    add      录入一条团购券
    list     列出券库（含有效性检查）
    remove   按 ID 删除
    clear    清空券库
    compare  与麦当劳官方渠道价格比价并给出推荐

示例
----
    # 1. 录入一张美团代金券：售价 25.9 元，可抵 40 元餐品，仅限堂食、非高峰时段
    python scripts/deal_compare.py add \\
        --platform meituan --title "麦当劳满40减14代金券" \\
        --price 25.9 --face 40 --channel store --time limited \\
        --valid-until 2026-11-30 --notes "每日限用1张"

    # 2. 比价：官方渠道商品合计原价 48.5 元，MCP 带券最优实付 38.5 元
    python scripts/deal_compare.py compare --mcd-face 48.5 --mcd-price 38.5

退出码：0 成功 · 1 用法/数据错误 · 2 券库为空
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_EMPTY = 2

DEFAULT_DEALS_FILE = os.path.join(
    os.path.expanduser(
        os.environ.get("MAIMAI_DATA_DIR", "~/.maimai_saver")
    ),
    "deals.json",
)

PLATFORMS = ("meituan", "douyin", "eleme", "other")
CHANNELS = ("store", "delivery", "both")
TIME_MODES = ("any", "limited")  # 全时段可用 / 限时段可用


# ---------------------------------------------------------------------------
# 券库读写
# ---------------------------------------------------------------------------
def _load_deals(path: str) -> List[Dict[str, Any]]:
    """加载团购券数据。

    数据源优先级：
    1. ``MAIMAI_DEALS_PROVIDER`` 环境变量指定的 provider 模块（.py 文件，
       需实现 ``load_deals() -> list[dict]``）——为未来美团/抖音等平台开放
       官方 API 时的自动化接入预留的插件接口，provider 异常时自动回退；
    2. 本地券库 JSON 文件（默认 ~/.maimai_saver/deals.json）。
    """
    provider_path = os.environ.get("MAIMAI_DEALS_PROVIDER")
    if provider_path:
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "maimai_deals_provider", provider_path
            )
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                provided = module.load_deals()
                if isinstance(provided, list):
                    return provided
                print(
                    "警告: 数据源 {0} 的 load_deals() 未返回列表，已忽略。".format(provider_path),
                    file=sys.stderr,
                )
        except Exception as exc:  # noqa: BLE001 - 外部数据源失败不应中断本地券库
            print(
                "警告: 加载团购数据源 {0} 失败: {1}，回退到本地券库。".format(provider_path, exc),
                file=sys.stderr,
            )

    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        print("警告: 券库文件 {0} 损坏或不可读，已按空券库处理。".format(path), file=sys.stderr)
        return []


def _save_deals(path: str, deals: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(deals, fh, ensure_ascii=False, indent=2)


def _new_id() -> str:
    return uuid.uuid4().hex[:6]


# ---------------------------------------------------------------------------
# 折算与决策
# ---------------------------------------------------------------------------
def _deal_validity(deal: Dict[str, Any], today: date) -> str:
    """返回券的有效性标记：ok / expiring / expired。"""
    valid_until = deal.get("valid_until")
    if not valid_until:
        return "ok"
    try:
        until = date.fromisoformat(str(valid_until))
    except ValueError:
        return "ok"
    if until < today:
        return "expired"
    if (until - today).days <= 7:
        return "expiring"
    return "ok"


def _fmt_money(value: float) -> str:
    return "¥{0:.2f}".format(value)


def _validity_badge(validity: str) -> str:
    """返回券有效性对应的展示徽标。"""
    return {
        "ok": "",
        "expiring": " [即将过期]",
        "expired": " [已过期]",
    }.get(validity, "")


def compare_deals(
    deals: List[Dict[str, Any]], mcd_face: float, mcd_price: float, today: Optional[date] = None
) -> Dict[str, Any]:
    """将券库与官方渠道方案比价，返回决策报告。

    折算口径（均为估算）：
    - 折扣率 = 券售价 / 券面值（覆盖商品合计原价）
    - 同内容估算到手价 = 官方渠道商品合计原价 × 券折扣率
      （前提假设：该券的适用范围能覆盖本次购买内容，需人工核对）
    """
    today = today or date.today()
    if mcd_face <= 0 or mcd_price < 0:
        raise ValueError("--mcd-face 必须大于 0，--mcd-price 不能为负。")

    entries: List[Dict[str, Any]] = []
    for deal in deals:
        face = float(deal.get("face_value") or 0)
        price = float(deal.get("price") or 0)
        if face <= 0 or price < 0:
            continue
        rate = price / face
        estimated = mcd_face * rate
        entry = dict(deal)
        entry["discount_rate"] = rate
        entry["estimated_price"] = estimated
        entry["estimated_saving_vs_mcd"] = mcd_price - estimated
        entry["validity"] = _deal_validity(deal, today)
        entries.append(entry)

    entries.sort(key=lambda e: (e["validity"] == "expired", e["estimated_price"]))
    return {
        "mcd_face": mcd_face,
        "mcd_price": mcd_price,
        "mcd_discount_rate": (mcd_price / mcd_face) if mcd_face else 0.0,
        "deals": entries,
        "today": today.isoformat(),
    }


def _print_report(report: Dict[str, Any]) -> int:
    mcd_face = report["mcd_face"]
    mcd_price = report["mcd_price"]
    print("=" * 72)
    print("麦麦省钱助手 · 全渠道比价报告（生成日期: {0}）".format(report["today"]))
    print("=" * 72)
    print("官方渠道方案：商品合计原价 {0}，MCP 带券最优实付 {1}（折扣率 {2:.1%}）".format(
        _fmt_money(mcd_face), _fmt_money(mcd_price), report["mcd_discount_rate"]))
    print()

    valid_entries = [e for e in report["deals"] if e["validity"] != "expired"]
    if not valid_entries:
        print("结论：券库中无有效团购券，建议走官方渠道下单（当前方案已含官方优惠）。")
        return EXIT_OK

    print("团购券比价（按估算到手价升序，所有金额均为估算值）：")
    print("-" * 72)
    for entry in report["deals"]:
        validity_badge = _validity_badge(entry["validity"])
        print("  [{0}] {1} | {2}{3}".format(
            entry.get("id", "?"), entry.get("platform", "?"), entry.get("title", ""), validity_badge))
        print("      售价 {0} / 面值 {1} = 折扣率 {2:.1%} | 同内容估算到手 {3} | 对比官方 {4:+.2f} 元".format(
            _fmt_money(float(entry["price"])),
            _fmt_money(float(entry["face_value"])),
            entry["discount_rate"],
            _fmt_money(entry["estimated_price"]),
            entry["estimated_saving_vs_mcd"],
        ))
        hints = []
        channel = entry.get("channel", "both")
        if channel == "store":
            hints.append("仅堂食核销")
        elif channel == "delivery":
            hints.append("仅外送可用")
        if entry.get("time_mode") == "limited":
            hints.append("限时段使用")
        if entry.get("quantity_limit"):
            hints.append("限购{0}张".format(entry["quantity_limit"]))
        if entry.get("valid_until"):
            hints.append("{0}前有效".format(entry["valid_until"]))
        if entry.get("notes"):
            hints.append(str(entry["notes"]))
        if hints:
            print("      限制: " + "；".join(hints))
    print("-" * 72)

    best = valid_entries[0]
    print()
    print("推荐决策（估算，实际以各平台页面与麦当劳官方渠道为准）：")
    if best["estimated_saving_vs_mcd"] > 0.5:
        print("  ✔ 建议使用团购券：{0}（{1}）".format(best.get("title", ""), best.get("platform", "")))
        print("    估算到手 {0}，较官方渠道方案节省约 {1}。".format(
            _fmt_money(best["estimated_price"]),
            _fmt_money(best["estimated_saving_vs_mcd"])))
        print("    注意：团购券通常不可叠加麦当劳官方优惠券，且需在适用门店/时段内核销；")
        print("    若本次订单内容未被该券覆盖，估算不成立，请以券详情页为准。")
    else:
        print("  ✔ 建议走麦当劳官方渠道下单（App/小程序/MCP 点餐）：")
        print("    当前官方带券实付 {0}，不劣于或接近最优团购估算 {1}；".format(
            _fmt_money(mcd_price), _fmt_money(best["estimated_price"])))
        print("    且官方渠道可叠加会员权益、积分抵扣，退改更灵活。")
    print()
    print("免责声明：本报告由本地录入数据估算生成，不与任何团购平台实时对接；")
    print("价格、库存与规则请以美团/抖音/麦当劳官方页面实时信息为准。")
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deal_compare",
        description=(
            "麦麦省钱助手 · 外部团购比价引擎 —— 将美团/抖音等平台手动查询到的"
            "麦当劳团购券录入本地券库，与官方渠道（MCP 计算价格）比价并给出推荐。"
        ),
    )
    parser.add_argument(
        "--file",
        default=os.environ.get("MAIMAI_DEALS_FILE", DEFAULT_DEALS_FILE),
        help="券库 JSON 文件路径（默认 ~/.maimai_saver/deals.json）",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    add_p = sub.add_parser("add", help="录入一条团购券")
    add_p.add_argument("--platform", required=True, choices=PLATFORMS, help="平台：meituan/douyin/eleme/other")
    add_p.add_argument("--title", required=True, help="券标题（从团购页复制）")
    add_p.add_argument("--price", type=float, required=True, help="券售价（元）")
    add_p.add_argument("--face", type=float, required=True, dest="face_value", help="面值：可抵扣/覆盖的商品合计原价（元）")
    add_p.add_argument("--channel", default="both", choices=CHANNELS, help="适用渠道：store/delivery/both（默认 both）")
    add_p.add_argument("--time", dest="time_mode", default="any", choices=TIME_MODES, help="可用时段：any=全时段 / limited=限时段")
    add_p.add_argument("--valid-until", dest="valid_until", default=None, help="有效期至（YYYY-MM-DD）")
    add_p.add_argument("--quantity-limit", dest="quantity_limit", type=int, default=None, help="限购张数")
    add_p.add_argument("--notes", default="", help="其他限制说明（如每日限用1张、指定门店等）")

    list_p = sub.add_parser("list", help="列出券库")
    list_p.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出")

    rm_p = sub.add_parser("remove", help="按 ID 删除一条团购券")
    rm_p.add_argument("deal_id", help="券 ID（add/list 时显示）")

    clear_p = sub.add_parser("clear", help="清空券库")
    clear_p.add_argument("--yes", action="store_true", help="跳过确认")

    cmp_p = sub.add_parser("compare", help="与官方渠道价格比价")
    cmp_p.add_argument("--mcd-face", type=float, required=True, help="官方渠道：本次商品合计原价（元）")
    cmp_p.add_argument("--mcd-price", type=float, required=True, help="官方渠道：MCP 带券最优实付（元）")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return EXIT_OK

    deals = _load_deals(args.file)

    if args.command == "add":
        if args.price < 0 or args.face_value <= 0:
            print("错误: --price 不能为负，--face 必须大于 0。", file=sys.stderr)
            return EXIT_USAGE
        if args.valid_until:
            try:
                date.fromisoformat(args.valid_until)
            except ValueError:
                print("错误: --valid-until 需为 YYYY-MM-DD 格式。", file=sys.stderr)
                return EXIT_USAGE
        deal = {
            "id": _new_id(),
            "platform": args.platform,
            "title": args.title,
            "price": args.price,
            "face_value": args.face_value,
            "channel": args.channel,
            "time_mode": args.time_mode,
            "valid_until": args.valid_until,
            "quantity_limit": args.quantity_limit,
            "notes": args.notes,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        deals.append(deal)
        _save_deals(args.file, deals)
        print("已录入团购券 [{0}] {1}（{2}）".format(deal["id"], deal["title"], deal["platform"]))
        return EXIT_OK

    if args.command == "list":
        if args.as_json:
            print(json.dumps(deals, ensure_ascii=False, indent=2))
            return EXIT_OK
        if not deals:
            print("券库为空。使用 `add` 子命令录入团购券。")
            return EXIT_OK
        today = date.today()
        for deal in deals:
            badge = _validity_badge(_deal_validity(deal, today))
            print("[{0}] {1} | {2}{3}".format(deal.get("id"), deal.get("platform"), deal.get("title"), badge))
            print("     售价 {0} / 面值 {1} | 渠道 {2} | 时段 {3}".format(
                _fmt_money(float(deal.get("price", 0))),
                _fmt_money(float(deal.get("face_value", 0))),
                deal.get("channel"), deal.get("time_mode")))
        return EXIT_OK

    if args.command == "remove":
        remaining = [d for d in deals if d.get("id") != args.deal_id]
        if len(remaining) == len(deals):
            print("错误: 未找到 ID 为 {0!r} 的团购券。".format(args.deal_id), file=sys.stderr)
            return EXIT_USAGE
        _save_deals(args.file, remaining)
        print("已删除 [{0}]，券库剩余 {1} 条。".format(args.deal_id, len(remaining)))
        return EXIT_OK

    if args.command == "clear":
        if not args.yes:
            print("此操作将清空券库，请追加 --yes 确认。", file=sys.stderr)
            return EXIT_USAGE
        _save_deals(args.file, [])
        print("券库已清空。")
        return EXIT_OK

    if args.command == "compare":
        if not deals:
            print("券库为空，无法比价。请先用 `add` 录入团购券。", file=sys.stderr)
            return EXIT_EMPTY
        report = compare_deals(deals, args.mcd_face, args.mcd_price)
        return _print_report(report)

    parser.error("未知命令")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
