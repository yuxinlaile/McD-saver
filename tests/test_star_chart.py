"""Star 历史曲线的单元测试与资产守卫（2026-10-21）。

图表由 ``scripts/gen_star_chart.py`` 从 GitHub API 的打星时间生成，
本文件锁定其数据处理与渲染行为，并确保仓库内始终有一份可用图表。
"""
import re
from datetime import date
from pathlib import Path

import gen_star_chart

REPO = Path(__file__).resolve().parent.parent
CHART = REPO / "docs" / "assets" / "star-history.svg"


class TestSeries:
    """按天累计序列。"""

    def test_cumulative_counts(self):
        days = [date(2026, 10, 10), date(2026, 10, 10), date(2026, 10, 12)]
        series = gen_star_chart.build_series(days, date(2026, 10, 13))
        assert series == [
            (date(2026, 10, 10), 2),
            (date(2026, 10, 11), 2),
            (date(2026, 10, 12), 3),
            (date(2026, 10, 13), 3),
        ]

    def test_empty_series(self):
        series = gen_star_chart.build_series([], date(2026, 10, 21))
        assert series == [(date(2026, 10, 21), 0)]

    def test_series_starts_at_first_star_and_ends_today(self):
        days = [date(2026, 10, 19), date(2026, 10, 21)]
        series = gen_star_chart.build_series(days, date(2026, 10, 21))
        assert series[0][0] == date(2026, 10, 19)
        assert series[-1] == (date(2026, 10, 21), 2)
        assert all(a[1] <= b[1] for a, b in zip(series, series[1:])), "累计值必须单调不减"


class TestRender:
    """SVG 渲染。"""

    def _series(self):
        return gen_star_chart.build_series([date(2026, 10, 20), date(2026, 10, 21)], date(2026, 10, 21))

    def test_svg_contains_value_and_labels(self):
        svg = gen_star_chart.render_svg(self._series())
        assert svg.startswith("<svg")
        assert svg.rstrip().endswith("</svg>")
        assert "2 ★" in svg
        assert "2026-10-21" in svg
        assert "yuxinlaile/McD-saver" in svg

    def test_svg_has_one_point_per_day(self):
        series = self._series()
        svg = gen_star_chart.render_svg(series)
        polyline = re.search(r'<polyline[^>]*points="([^"]+)"', svg)
        assert polyline is not None
        assert len(polyline.group(1).split()) == len(series)

    def test_y_axis_top_is_rounded_up(self):
        series = gen_star_chart.build_series([date(2026, 10, 21)] * 7, date(2026, 10, 21))
        svg = gen_star_chart.render_svg(series)
        assert ">10<" in svg, "7 颗星时 y 轴上限应为 10"


class TestCommittedAsset:
    """仓库内必须有一份可用图表，且被 README 引用。"""

    def test_chart_file_exists(self):
        assert CHART.exists(), "缺少 docs/assets/star-history.svg（运行 scripts/gen_star_chart.py 生成）"

    def test_chart_file_is_valid_svg(self):
        text = CHART.read_text(encoding="utf-8")
        assert text.startswith("<svg") and text.rstrip().endswith("</svg>")
        assert "★" in text

    def test_readme_references_local_chart(self):
        for name in ("README.md", "README_EN.md"):
            text = (REPO / name).read_text(encoding="utf-8")
            assert "docs/assets/star-history.svg" in text, "{0} 未引用本仓库的 Star 图表".format(name)
