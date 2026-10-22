#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTML 体检报告渲染与省钱等级（v2.1.2 从 silent_cost 拆分）。

纯函数模块：输入均为 analyze_* 产出的 dict，不发起任何网络请求。
silent_cost 通过再导出保持旧接口兼容（``from silent_cost import render_html``）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

# 与 silent_cost 保持一致的临期口径（7 天内到期）
EXPIRING_DAYS = 7


_HTML_TMPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>麦麦省钱助手 · 沉默成本体检报告</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif;
         background: #FFF8EE; color: #292321; margin: 0; padding: 32px 16px; }}
  .card {{ max-width: 720px; margin: 0 auto 16px; background: #fff; border-radius: 14px;
          padding: 22px 26px; box-shadow: 0 2px 10px rgba(191,124,26,.12); }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  h2 {{ font-size: 15px; margin: 0 0 10px; color: #B0720F; letter-spacing: .5px; }}
  .sub {{ color: #8a7a66; font-size: 12px; margin-bottom: 14px; }}
  .row {{ display: flex; justify-content: space-between; padding: 7px 0;
          border-bottom: 1px dashed #f0e4d0; font-size: 14px; gap: 12px; }}
  .row:last-child {{ border-bottom: none; }}
  .money {{ font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap; }}
  .good {{ color: #1a7f37; }} .bad {{ color: #c62828; }} .muted {{ color: #9a8b77; }}
  .stat {{ display: flex; gap: 10px; margin: 10px 0 2px; flex-wrap: wrap; }}
  .stat div {{ flex: 1; min-width: 130px; background: #FFF3DC; border-radius: 10px;
               padding: 10px 12px; text-align: center; }}
  .stat b {{ display: block; font-size: 20px; margin-top: 2px; }}
  footer {{ max-width: 720px; margin: 0 auto; text-align: center; color: #9a8b77;
            font-size: 11px; line-height: 1.8; }}
  footer a {{ color: #B0720F; }}
</style>
</head>
<body>
<div class="card">
  <h1>🍟 沉默成本体检报告</h1>
  <div class="sub">生成于 {generated} · 数据来自麦当劳官方 MCP 只读工具 · 金额为估算口径</div>
  {coupons_block}
</div>
<div class="card">
  <h2>【二】消费画像</h2>
  {orders_block}
</div>
<div class="card">
  <h2>【三】积分体检</h2>
  {points_block}
</div>
<footer>McD Saver (mcd-saver) · 社区开源项目，与麦当劳公司无关联<br>
<a href="https://github.com/yuxinlaile/McD-saver">GitHub 仓库</a> ·
<a href="https://yuxinlaile.github.io/McD-saver/demo.html">在线试算</a> · 卡号/Token 已脱敏，可安全截图</footer>
</body>
</html>
"""


def render_html(coupons: Dict[str, Any], orders: Dict[str, Any],
                points: Dict[str, Any], mall: Optional[Dict[str, Any]] = None,
                schedule: Optional[Dict[str, Any]] = None,
                generated: Optional[str] = None) -> str:
    """生成零依赖单文件 HTML 报告——可直接截图分享的「体检长图」。"""
    now = generated or datetime.now().strftime("%Y-%m-%d %H:%M")
    grade, grade_note = savings_grade(schedule)
    rows = []
    if coupons["expiring"]:
        for c in coupons["expiring"]:
            face = "¥{0:.2f}".format(c["face"]) if c["face"] is not None else "未识别"
            src = ' <span class="good">实测</span>' if c.get("face_source") == "measured" else ""
            rows.append('<div class="row"><span>{0}</span><span class="money">{1}{2} · 还剩 {3} 天</span></div>'.format(
                _esc(c["title"]), face, src, c["days"]))

        stat = '<div class="stat"><div>临期面值合计<b class="money">{0}</b></div>'.format(_fmt_html(coupons["expiring_face_total"]))
        if schedule:
            stat += ('<div>窗口内可实现<b class="money good">{0}</b></div>'
                     '<div>注定过期<b class="money bad">{1}</b></div>').format(
                _fmt_html(schedule["realizable"]), _fmt_html(schedule["doomed"]))
        stat += "</div>"
        rows.append(stat)
        if grade != "—":
            rows.append('<div class="row"><span>🏅 本期省钱等级 <b>{0}</b>{1}</span></div>'.format(
                grade, f' — {grade_note}' if grade_note else ''))
        if schedule:
            for c in schedule["scheduled"]:
                rows.append('<div class="row"><span>🥇 {0} → {1}</span><span class="money good">净价值 {2}</span></div>'.format(
                    _esc(c["title"]), c["slot"], _fmt_html(c["net_value"])))
            for c in schedule["missed"]:
                if c.get("category") == "paper":
                    rows.append('<div class="row"><span>📄 {0}（纸面富贵，建议放弃）</span><span class="money bad">{1}</span></div>'.format(
                        _esc(c["title"]), _fmt_html(c["face"])))
                else:
                    rows.append('<div class="row"><span>⌛ {0}（排不上）</span><span class="money bad">{1}</span></div>'.format(
                        _esc(c["title"]), _fmt_html(c["face"])))
    else:
        rows.append('<div class="row"><span class="muted">近 {0} 天内没有临期券。</span></div>'.format(EXPIRING_DAYS))
    coupons_block = "<h2>【一】临期券（{0} 天内到期）</h2>".format(EXPIRING_DAYS) + "".join(rows)

    orows = []
    if orders["amount_count"]:
        orows.append('<div class="stat"><div>订单数<b>{0}</b></div><div>总支出<b class="money">{1}</b></div>'
                     '<div>客单价<b class="money">{2}</b></div></div>'.format(
            orders["order_count"], _fmt_html(orders["total_spend"]), _fmt_html(orders["avg_ticket"])))
        for item in orders["top_items"]:
            orows.append('<div class="row"><span>🔁 {0}</span><span>× {1} 次——改点对应套餐通常更省</span></div>'.format(
                _esc(item["name"]), item["count"]))
    else:
        orows.append('<div class="row"><span class="muted">暂无可识别的历史订单金额。</span></div>')
    orders_block = "".join(orows)

    prows = []
    if points["available"] is not None:
        prows.append('<div class="row"><span>可用积分</span><span class="money">{0:.0f}</span></div>'.format(points["available"]))
        if points.get("expiring_now"):
            prows.append('<div class="row"><span>本月将过期（优先级最高）</span><span class="money bad">{0:.0f}</span></div>'.format(points["expiring_now"]))
        if points.get("expiring_next"):
            prows.append('<div class="row"><span>下月将过期</span><span class="money">{0:.0f}</span></div>'.format(points["expiring_next"]))
        if mall and mall.get("shadow_price"):
            prows.append('<div class="row"><span>积分影子价格（最优兑换「{0}」）</span><span class="money">{1:.4f} 元/积分</span></div>'.format(
                _esc(mall["best_product"]["name"]), mall["shadow_price"]))
            prows.append('<div class="row"><span>可用积分折现</span><span class="money">≈ ¥{0:.2f}</span></div>'.format(
                points["available"] * mall["shadow_price"]))
    else:
        prows.append('<div class="row"><span class="muted">积分账户字段未识别。</span></div>')
    points_block = "".join(prows)

    return _HTML_TMPL.format(generated=_esc(now), coupons_block=coupons_block,
                             orders_block=orders_block, points_block=points_block)


def _esc(text: Any) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _fmt_html(value: Optional[float]) -> str:
    return "¥{0:.2f}".format(value) if value is not None else "—"



# ---------------------------------------------------------------------------
# 省钱等级（v1.7.1）：确定性分档，基于排程可实现金额，供分享卡片展示
# ---------------------------------------------------------------------------
def savings_grade(schedule: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    """按排程「可实现金额」确定性分档：S≥30 / A≥15 / B≥5 / C≥1 / D<1。

    返回 (等级, 一句话说明)；无排程数据返回 ("—", "")。
    """
    if not schedule or schedule.get("realizable") is None:
        return ("—", "")
    value = float(schedule["realizable"])
    if value >= 30:
        return ("S", "本期可实现节省 ¥{0:.2f}，稳稳拿捏".format(value))
    if value >= 15:
        return ("A", "本期可实现节省 ¥{0:.2f}".format(value))
    if value >= 5:
        return ("B", "本期可实现节省 ¥{0:.2f}".format(value))
    if value >= 1:
        return ("C", "本期可实现节省 ¥{0:.2f}".format(value))
    return ("D", "本期可实现节省 ¥{0:.2f}——下期记得提前排程用券".format(value))


