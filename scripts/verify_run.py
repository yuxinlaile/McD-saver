#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实运行验证记录生成器（verified-run）。

在**真实 Token 环境**下运行一次，自动把四步检查的实测证据写成 Markdown 记录。
默认写到 ``examples/verified-run.local.md``（已在 ``.gitignore`` 中，不会污染仓库）；
需要更新入库样例时用 ``--out examples/verified-run.md`` 显式指定。

安全约定：
- Token 与手机号绝不写入输出（本脚本输出的内容已脱敏）；
- 门店编码保留（可追溯但不敏感）；
- 生成后请人工过目一遍再提交。

用法::

    export MCD_MCP_TOKEN=你的token   # 或写入 ~/.mcd_mcp_token
    python scripts/verify_run.py               # 写本地文件（不入库）
    python scripts/verify_run.py --html        # 同时生成 HTML 体检报告
    python scripts/verify_run.py --out examples/verified-run.md   # 更新入库样例
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcd_client import McdMcpClient, load_token  # noqa: E402
import silent_cost  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
# 默认写本地文件：该文件被 .gitignore 排除，避免一次误运行就覆写入库样例
OUT = EXAMPLES / "verified-run.local.md"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _display_path(path: Path) -> str:
    """仓库内路径显示为相对路径，仓库外显示绝对路径（便于在记录里定位）。"""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_run", description="生成真实运行验证记录")
    parser.add_argument("--html", action="store_true", help="同时生成 HTML 体检报告")
    parser.add_argument("--store-code", default="", help="门店编码（默认取菜单数据）")
    parser.add_argument("--out", default=None,
                        help="输出路径（默认 examples/verified-run.local.md；"
                             "更新入库样例请传 examples/verified-run.md）")
    args = parser.parse_args(argv)

    out = Path(args.out) if args.out else OUT
    if not out.is_absolute():
        out = Path(__file__).resolve().parent.parent / out

    token = load_token()
    if not token:
        print("错误：未找到 Token。请设置 MCD_MCP_TOKEN 或写入 ~/.mcd_mcp_token。", file=sys.stderr)
        return 2

    client = McdMcpClient(token=token, verbose=False)
    today = dt.datetime.now()  # analyze_coupons / analyze_orders 需要 datetime（内部取 .date() 并做日期相减）

    # 1) 连通性（等价 mcd.py check：initialize + tools/list）
    try:
        info = client.initialize()
        tools = len(client.list_tools())
        server = info.get("serverInfo", {})
    except Exception as exc:  # noqa: BLE001
        print("错误：连通性检查失败：{0}".format(str(exc)[:120]), file=sys.stderr)
        return 1

    # 2) 拉取数据（券/订单/积分）
    raw_coupons = client.call_tool("query-my-coupons", {})
    raw_orders = client.call_tool("order-list", {"pageSize": 20})
    raw_points = client.call_tool("query-my-account", {})

    coupons = silent_cost.analyze_coupons(raw_coupons, today=today)
    orders = silent_cost.analyze_orders(raw_orders, today=today)
    points = silent_cost.analyze_points(raw_points)
    schedule = silent_cost.schedule_coupons(coupons, orders)

    # 3) 可选 HTML 报告（与记录同目录，均不入库）
    html_path = None
    if args.html:
        html_path = out.parent / "verified-run-report.html"
        html_path.write_text(
            silent_cost.render_html(coupons, orders, points, None, schedule,
                                    generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M")),
            encoding="utf-8")

    # 4) 生成脱敏记录
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 真实运行验证记录（verified-run）",
        "",
        "> 本文件由 `python scripts/verify_run.py` 在真实 Token 环境生成（{0}）。".format(now),
        "> Token 与手机号已由脚本排除，门店编码保留用于追溯。",
        "",
        "## 环境",
        "",
        "| 项 | 值 |",
        "|---|---|",
        "| 生成时间 | {0} |".format(now),
        "| Python | {0} |".format(sys.version.split()[0]),
        "| 平台 | {0} |".format(sys.platform),
        "",
        "## 连通性检查（mcd.py check 等价）",
        "",
        "| 指标 | 实测值 |",
        "|---|---|",
        "| 连接状态 | ✅ 成功 |",
        "| 服务器 | {0} v{1} |".format(server.get("name", "unknown"), server.get("version", "unknown")),
        "| 可用工具数 | {0} |".format(tools),
        "",
        "## 券与消费数据（脱敏摘要）",
        "",
        "| 指标 | 实测值 |",
        "|---|---|",
        "| 临期券张数 | {0} |".format(len(coupons.get("expiring", []))),
        "| 临期面值合计 | {0:.2f} 元 |".format(coupons.get("expiring_face_total") or 0.0),
        "| 近 20 单消费合计 | {0} |".format(
            "{0:.2f} 元".format(orders["total_spend"]) if orders.get("total_spend") else "—"),
        "| 客单价（消费口径） | {0} |".format(
            "{0:.2f} 元".format(orders["avg_ticket"]) if orders.get("avg_ticket") else "—"),
        "| 0 元订单数 | {0} |".format(orders.get("free_order_count", 0)),
        "| 积分余额 | {0} |".format(points.get("available", "—") if isinstance(points, dict) else "—"),
        "",
    ]
    if schedule:
        lines += [
            "## 用券排程（净价值模型）",
            "",
            "| 指标 | 实测值 |",
            "|---|---|",
            "| 窗口 | {0} 天 |".format(schedule["window_days"]),
            "| 预期点单次数 | {0} |".format(schedule["expected_orders"]),
            "| 可实现（净价值） | {0:.2f} 元 |".format(schedule["realizable"]),
            "| 注定过期 | {0:.2f} 元 |".format(schedule["doomed"]),
            "",
        ]
    if html_path:
        lines += ["## HTML 体检报告", "",
                  "- 文件：`{0}`（本地生成，不入库）".format(_display_path(html_path)), ""]
    lines += ["---", "",
              "> 复核方式：`python scripts/verify_run.py` 可随时重新生成；",
              "> 所有金额均为 MCP 实时返回，脚本不估算。", ""]

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("已写入：{0}".format(out))
    if html_path:
        print("HTML 报告：{0}".format(html_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
