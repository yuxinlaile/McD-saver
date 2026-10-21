#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 GitHub API 生成 Star 历史曲线（纯标准库，输出 SVG）。

用途：README 的 Star History 不再依赖第三方 star-history.com（其数据由对方
服务端缓存，滞后数小时到一天），改为仓库内自绘——随时可重算、离线可看。

用法::

    python scripts/gen_star_chart.py                      # 写入 docs/assets/star-history.svg
    python scripts/gen_star_chart.py --repo owner/name --out path.svg

注意：匿名调用 GitHub API 的速率上限较低；设置环境变量 ``GITHUB_TOKEN`` 可提高上限。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple

DEFAULT_REPO = "yuxinlaile/McD-saver"
DEFAULT_OUT = "docs/assets/star-history.svg"
API = "https://api.github.com"

# 品牌色（与 banner.svg / demo.html 一致）
C_LINE = "#FFC72C"
C_FILL = "#FFC72C"
C_TEXT = "#374151"
C_MUTED = "#9CA3AF"
C_GRID = "#E5E7EB"
C_DOT = "#DA291C"


def resolve_token() -> str:
    """取 API Token：环境变量 ``GITHUB_TOKEN`` 优先，其次复用 gh CLI 的登录态。"""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    try:
        import subprocess

        out = subprocess.check_output(["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL)
        return out.strip()
    except Exception:  # noqa: BLE001 - gh 不可用时返回空串
        return ""


def fetch_star_days(repo: str, token: str = "") -> List[date]:
    """取回所有打星日期（按时间升序）。"""
    days: List[date] = []
    page = 1
    while True:
        url = "{0}/repos/{1}/stargazers?per_page=100&page={2}".format(API, repo, page)
        request = urllib.request.Request(url)
        request.add_header("Accept", "application/vnd.github.star+json")
        request.add_header("User-Agent", "mcd-saver-star-chart")
        if token:
            request.add_header("Authorization", "Bearer {0}".format(token))
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise RuntimeError(
                    "GitHub API 需要鉴权（{0}）。请设置环境变量 GITHUB_TOKEN，"
                    "或先执行 gh auth login。".format(exc.code))
            raise RuntimeError("GitHub API 返回 {0}".format(exc.code))
        if not payload:
            break
        for item in payload:
            stamp = item.get("starred_at") or item.get("created_at")
            if stamp:
                days.append(datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").date())
        if len(payload) < 100:
            break
        page += 1
    return sorted(days)


def build_series(days: List[date], today: date) -> List[Tuple[date, int]]:
    """按天累计：返回 [(日期, 累计星数)]，覆盖首星到今天。"""
    if not days:
        return [(today, 0)]
    counter = Counter(days)
    first = min(days)
    series: List[Tuple[date, int]] = []
    running = 0
    current = first
    while current <= today:
        running += counter.get(current, 0)
        series.append((current, running))
        current += timedelta(days=1)
    return series


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(series: List[Tuple[date, int]], repo: str = DEFAULT_REPO,
               width: int = 800, height: int = 400) -> str:
    """把累计序列渲染成一张 SVG 折线图。"""
    pad_l, pad_r, pad_t, pad_b = 52, 96, 44, 40
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    total = series[-1][1] if series else 0
    top = max(10, int((total / 10 + 1)) * 10)  # y 轴上取整到 10 的倍数
    n = max(0, len(series) - 1)

    def x_of(index: int) -> float:
        return pad_l + plot_w * (index / n if n else 0)

    def y_of(value: int) -> float:
        return pad_t + plot_h * (1 - value / top)

    parts: List[str] = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}" '
        'viewBox="0 0 {0} {1}" role="img" aria-label="GitHub stars history">'.format(width, height))
    parts.append('<rect width="{0}" height="{1}" fill="#FFFFFF"/>'.format(width, height))

    # y 轴网格与刻度
    for step in range(0, top + 1, max(1, top // 4)):
        y = y_of(step)
        parts.append('<line x1="{0}" y1="{1:.1f}" x2="{2}" y2="{1:.1f}" stroke="{3}" stroke-width="1"/>'.format(
            pad_l, y, pad_l + plot_w, C_GRID))
        parts.append('<text x="{0}" y="{1:.1f}" font-family="ui-monospace,Consolas,monospace" font-size="12" '
                     'fill="{2}" text-anchor="end">{3}</text>'.format(pad_l - 8, y + 4, C_MUTED, step))

    # 面积 + 折线
    points = " ".join("{0:.1f},{1:.1f}".format(x_of(i), y_of(v)) for i, (_d, v) in enumerate(series))
    area = "{0:.1f},{1:.1f} {2} {3:.1f},{1:.1f}".format(x_of(0), y_of(0), points, x_of(len(series) - 1))
    parts.append('<polygon points="{0}" fill="{1}" fill-opacity="0.18"/>'.format(area, C_FILL))
    parts.append('<polyline points="{0}" fill="none" stroke="{1}" stroke-width="2.5" '
                 'stroke-linejoin="round" stroke-linecap="round"/>'.format(points, C_LINE))

    # x 轴日期（首、1/3、2/3、末）
    marks = sorted({0, n // 3, (2 * n) // 3, n}) if n else [0]
    for index in sorted(set(marks)):
        label = series[index][0].strftime("%m-%d")
        anchor = "start" if index == 0 else ("end" if index == n else "middle")
        parts.append('<text x="{0:.1f}" y="{1}" font-family="ui-monospace,Consolas,monospace" font-size="12" '
                     'fill="{2}" text-anchor="{3}">{4}</text>'.format(
                         x_of(index), height - 14, C_MUTED, anchor, label))

    # 末点与当前值
    last_x, last_y = x_of(len(series) - 1), y_of(total)
    parts.append('<circle cx="{0:.1f}" cy="{1:.1f}" r="4" fill="{2}"/>'.format(last_x, last_y, C_DOT))
    parts.append('<text x="{0:.1f}" y="{1:.1f}" font-family="ui-monospace,Consolas,monospace" font-size="15" '
                 'font-weight="bold" fill="{2}" text-anchor="end">{3} ★</text>'.format(
                     last_x - 8, last_y - 8, C_DOT, total))
    parts.append('<text x="{0}" y="24" font-family="ui-monospace,Consolas,monospace" font-size="13" '
                 'fill="{1}">{2} · {3}</text>'.format(pad_l, C_TEXT, _esc(repo), "GitHub Stars"))
    parts.append('<text x="{0}" y="24" font-family="ui-monospace,Consolas,monospace" font-size="12" '
                 'fill="{1}" text-anchor="end">{2}</text>'.format(width - pad_r, C_MUTED,
                                                                 "截至 " + series[-1][0].isoformat()))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 GitHub Star 历史曲线")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="仓库 owner/name")
    parser.add_argument("--out", default=DEFAULT_OUT, help="输出 SVG 路径")
    args = parser.parse_args(argv)
    try:
        days = fetch_star_days(args.repo, resolve_token())
    except RuntimeError as exc:
        print("错误: {0}".format(exc), file=sys.stderr)
        return 1
    series = build_series(days, date.today())
    svg = render_svg(series, args.repo)
    out = args.out
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print("已生成 {0}（{1} 天，{2} ★）".format(out, len(series), series[-1][1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
