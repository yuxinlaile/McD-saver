"""console.ensure_utf8_stdio 单元测试。

真实故障复现：`windows-latest`（en-US）的控制台编码是 cp1252，`python demo.py`
输出中文时抛 `UnicodeEncodeError`，整条命令失败。入口统一调用本函数兜底。
"""
import re
from pathlib import Path

import console

ROOT = Path(__file__).resolve().parent.parent
MAIN_RE = re.compile(r"^def main\(", re.M)


class FakeStream:
    def __init__(self, encoding):
        self.encoding = encoding
        self.calls = []

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)
        self.encoding = kwargs.get("encoding", self.encoding)


class NoReconfigure:
    """不支持 reconfigure 的流（如被包装过的 stdout）。"""

    encoding = "cp1252"


class NoEncoding:
    """没有 encoding 属性的流。"""


class TestEnsureUtf8:
    def test_switches_non_utf8_streams(self):
        out, err = FakeStream("cp1252"), FakeStream("cp936")
        console.ensure_utf8_stdio([out, err])
        assert out.calls == [{"encoding": "utf-8", "errors": "replace"}]
        assert err.calls == [{"encoding": "utf-8", "errors": "replace"}]

    def test_leaves_utf8_streams_untouched(self):
        out = FakeStream("utf-8")
        console.ensure_utf8_stdio([out])
        assert out.calls == []

    def test_tolerates_missing_encoding_or_reconfigure(self):
        console.ensure_utf8_stdio([None, NoEncoding(), NoReconfigure()])

    def test_reconfigure_error_is_swallowed(self):
        class Exploding(FakeStream):
            def reconfigure(self, **kwargs):
                raise ValueError("closed")

        console.ensure_utf8_stdio([Exploding("cp1252")])


class TestEntryPoints:
    """所有带 ``main()`` 的入口都必须做一次控制台编码兜底。"""

    def test_every_entry_point_calls_ensure_utf8_stdio(self):
        entry_points = sorted((ROOT / "scripts").glob("*.py")) + [ROOT / "demo.py"]
        missing = []
        for path in entry_points:
            if path.name == "console.py":
                continue
            text = path.read_text(encoding="utf-8")
            if MAIN_RE.search(text) and "ensure_utf8_stdio()" not in text:
                missing.append(path.name)
        assert not missing, "入口未做控制台编码兜底：{0}".format(missing)
