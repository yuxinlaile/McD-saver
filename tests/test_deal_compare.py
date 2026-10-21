"""deal_compare 比价决策单元测试。"""
from datetime import date

import pytest

from deal_compare import (
    _deal_validity,
    _load_deals,
    _save_deals,
    compare_deals,
    main,
)

TODAY = date(2026, 10, 10)


def _deal(**kwargs):
    base = {
        "id": "x1",
        "platform": "meituan",
        "title": "测试券",
        "price": 25.9,
        "face_value": 40.0,
        "channel": "store",
        "time_mode": "limited",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# 有效期判定
# ---------------------------------------------------------------------------
class TestDealValidity:
    def test_ok(self):
        assert _deal_validity({"valid_until": "2026-12-31"}, TODAY) == "ok"

    def test_expiring_within_7_days(self):
        assert _deal_validity({"valid_until": "2026-10-14"}, TODAY) == "expiring"

    def test_expired(self):
        assert _deal_validity({"valid_until": "2026-10-01"}, TODAY) == "expired"

    def test_missing_date_treated_ok(self):
        assert _deal_validity({}, TODAY) == "ok"

    def test_invalid_date_treated_ok(self):
        assert _deal_validity({"valid_until": "not-a-date"}, TODAY) == "ok"


# ---------------------------------------------------------------------------
# 比价折算与排序
# ---------------------------------------------------------------------------
class TestCompareDeals:
    def test_estimated_price_and_saving(self):
        report = compare_deals([_deal()], mcd_face=48.5, mcd_price=38.5)
        entry = report["deals"][0]
        assert entry["discount_rate"] == pytest.approx(25.9 / 40.0)
        assert entry["estimated_price"] == pytest.approx(48.5 * 25.9 / 40.0)
        assert entry["estimated_saving_vs_mcd"] == pytest.approx(
            38.5 - entry["estimated_price"]
        )

    def test_sorted_by_estimated_price_expired_last(self):
        deals = [
            _deal(id="cheap", price=20.0, face_value=40.0),
            _deal(id="costly", price=30.0, face_value=40.0),
            _deal(id="expired", price=10.0, face_value=40.0, valid_until="2026-01-01"),
        ]
        report = compare_deals(deals, mcd_face=48.5, mcd_price=38.5, today=TODAY)
        ids = [e["id"] for e in report["deals"]]
        assert ids[0] == "cheap"  # 有效券中估算到手价最低者排最前
        assert ids[1] == "costly"
        assert ids[-1] == "expired"  # 过期券沉底，不参与推荐

    def test_mcd_discount_rate(self):
        report = compare_deals([], mcd_face=100.0, mcd_price=80.0)
        assert report["mcd_discount_rate"] == pytest.approx(0.8)

    def test_invalid_mcd_face_raises(self):
        # 2026-10-20 巡检整改：库函数改抛 ValueError，不再用 SystemExit 终止宿主进程
        with pytest.raises(ValueError):
            compare_deals([_deal()], mcd_face=0, mcd_price=10.0)

    def test_invalid_deal_rows_skipped(self):
        deals = [_deal(id="bad", price=25.9, face_value=0), _deal(id="good")]
        report = compare_deals(deals, mcd_face=48.5, mcd_price=38.5)
        assert [e["id"] for e in report["deals"]] == ["good"]


# ---------------------------------------------------------------------------
# 券库读写与 provider 数据源
# ---------------------------------------------------------------------------
class TestStorageAndProvider:
    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "deals.json")
        _save_deals(path, [_deal(id="r1")])
        assert _load_deals(path)[0]["id"] == "r1"

    def test_load_missing_file_returns_empty(self, tmp_path):
        assert _load_deals(str(tmp_path / "nope.json")) == []

    def test_load_corrupted_file_returns_empty(self, tmp_path):
        path = tmp_path / "deals.json"
        path.write_text("{broken json", encoding="utf-8")
        assert _load_deals(str(path)) == []

    def test_provider_hook(self, tmp_path):
        provider = tmp_path / "provider.py"
        provider.write_text(
            "def load_deals():\n"
            "    return [{'id': 'p1', 'price': 20.0, 'face_value': 40.0}]\n",
            encoding="utf-8",
        )
        deals = _load_deals(str(tmp_path / "deals.json"), str(provider))
        assert [d["id"] for d in deals] == ["p1"]

    def test_provider_failure_falls_back_to_file(self, tmp_path):
        provider = tmp_path / "bad_provider.py"
        provider.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
        local_file = tmp_path / "deals.json"
        _save_deals(str(local_file), [_deal(id="local")])
        deals = _load_deals(str(local_file), str(provider))
        assert [d["id"] for d in deals] == ["local"]

    def test_provider_invalid_return_falls_back(self, tmp_path):
        provider = tmp_path / "wrong_provider.py"
        provider.write_text("def load_deals():\n    return 'not-a-list'\n", encoding="utf-8")
        local_file = tmp_path / "deals.json"
        _save_deals(str(local_file), [_deal(id="local")])
        deals = _load_deals(str(local_file), str(provider))
        assert [d["id"] for d in deals] == ["local"]

    def test_legacy_env_var_is_ignored(self, monkeypatch, tmp_path, capsys):
        """环境变量不再触发外部代码执行（2026-10-21 改造）。"""
        provider = tmp_path / "provider.py"
        provider.write_text(
            "def load_deals():\n"
            "    return [{'id': 'p1', 'price': 20.0, 'face_value': 40.0}]\n",
            encoding="utf-8",
        )
        local_file = tmp_path / "deals.json"
        _save_deals(str(local_file), [_deal(id="local")])
        monkeypatch.setenv("MAIMAI_DEALS_PROVIDER", str(provider))
        deals = _load_deals(str(local_file))
        assert [d["id"] for d in deals] == ["local"]
        assert "MAIMAI_DEALS_PROVIDER" in capsys.readouterr().err

    def test_provider_flag_is_wired_to_cli(self, tmp_path, capsys):
        provider = tmp_path / "provider.py"
        provider.write_text(
            "def load_deals():\n"
            "    return [{'id': 'p1', 'title': '插件券', 'price': 20.0, 'face_value': 40.0}]\n",
            encoding="utf-8",
        )
        code = main(["--provider", str(provider), "--file", str(tmp_path / "d.json"), "list"])
        assert code == 0
        assert "p1" in capsys.readouterr().out
