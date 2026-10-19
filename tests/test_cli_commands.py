#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI 命令层测试（v2.2 新增）。

此前 mcd.py 只有 `--help` 冒烟，真实命令处理逻辑（check/tools/schema/call/claim）
覆盖率为 28%。这里用桩客户端覆盖所有分支与退出码，不发起任何网络请求。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mcd  # noqa: E402
import verify_run  # noqa: E402
from mcd_client import AuthError, McpToolError, RateLimitError, TransportError  # noqa: E402


class StubClient:
    """最小 MCP 客户端桩：只实现 CLI 用到的接口。"""

    last_kwargs: dict = {}

    def __init__(self, **kwargs):
        StubClient.last_kwargs = kwargs
        self.base_url = kwargs.get("base_url", "https://mcp.example")
        self.closed = False
        self.raise_on_initialize = None
        self.tools = [{"name": "query-meals", "description": "查询菜单"},
                      {"name": "order-list", "description": "x" * 150}]
        self.call_result = {"content": [{"type": "text", "text": "ok"}]}
        self.schema = {"name": "query-meals", "inputSchema": {"type": "object"}}

    def initialize(self):
        if self.raise_on_initialize:
            raise self.raise_on_initialize
        return {"serverInfo": {"name": "mcd", "version": "9.9"}}

    def list_tools(self):
        return self.tools

    def get_tool_schema(self, name):
        return self.schema if name == "query-meals" else None

    def call_tool(self, name, arguments=None):
        self.called = (name, arguments)
        return self.call_result

    def close(self):
        self.closed = True


@pytest.fixture
def stub(monkeypatch):
    """返回唯一的桩实例——main() 内部构造的客户端就是它，便于断言调用。"""
    instance = StubClient()
    monkeypatch.setattr(mcd, "McdMcpClient", lambda **kwargs: instance)
    monkeypatch.setattr(mcd, "load_token", lambda cli=None: "token")
    return instance


class TestArgumentParsing:
    def test_parse_arg_value_types(self):
        assert mcd._parse_arg_value("3") == 3
        assert mcd._parse_arg_value("true") is True
        assert mcd._parse_arg_value("null") is None
        assert mcd._parse_arg_value("北京市朝阳区") == "北京市朝阳区"

    def test_merge_json_and_pairs(self):
        merged = mcd._merge_arguments('{"a": 1}', ["b=2", "c=text"])
        assert merged == {"a": 1, "b": 2, "c": "text"}

    def test_merge_rejects_non_object_json(self):
        with pytest.raises(SystemExit):
            mcd._merge_arguments("[1,2]", None)

    def test_merge_rejects_bad_pair(self):
        with pytest.raises(SystemExit):
            mcd._merge_arguments(None, ["novalue"])


class TestCommands:
    def test_no_command_prints_help(self, stub, capsys):
        assert mcd.main([]) == mcd.EXIT_OK
        assert "usage" in capsys.readouterr().out.lower()

    def test_check_prints_server_and_tools(self, stub, capsys):
        assert mcd.main(["check"]) == mcd.EXIT_OK
        out = capsys.readouterr().out
        assert "连接成功" in out and "mcd v9.9" in out and "可用工具数: 2" in out

    def test_tools_lists_and_truncates(self, stub, capsys):
        assert mcd.main(["tools"]) == mcd.EXIT_OK
        out = capsys.readouterr().out
        assert "query-meals" in out and "..." in out

    def test_tools_empty(self, stub, capsys):
        stub.tools = []
        assert mcd.main(["tools"]) == mcd.EXIT_OK
        assert "未返回任何工具" in capsys.readouterr().out

    def test_schema_found(self, stub, capsys):
        assert mcd.main(["schema", "query-meals"]) == mcd.EXIT_OK
        assert "inputSchema" in capsys.readouterr().out

    def test_schema_missing(self, stub, capsys):
        assert mcd.main(["schema", "nope"]) == mcd.EXIT_TOOL_ERROR
        assert "未找到工具" in capsys.readouterr().err

    def test_call_pretty_and_raw(self, stub, capsys):
        assert mcd.main(["call", "query-meals", "--raw"]) == mcd.EXIT_OK
        raw = capsys.readouterr().out
        assert json.loads(raw)["content"][0]["text"] == "ok"

        assert mcd.main(["call", "query-meals", "--arg", "count=2"]) == mcd.EXIT_OK
        assert stub.called[1] == {"count": 2}

    def test_claim_with_empty_listing(self, stub, capsys):
        stub.call_result = {"content": [{"type": "text", "text": "暂无可领取"}]}
        assert mcd.main(["claim", "--yes"]) == mcd.EXIT_OK
        assert "暂无可领取" in capsys.readouterr().out

    def test_claim_cancelled_by_user(self, stub, capsys, monkeypatch):
        stub.call_result = {"content": [{"type": "text", "text": "满30减6"}]}
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")
        assert mcd.main(["claim"]) == mcd.EXIT_OK
        assert "已取消" in capsys.readouterr().out


class TestExitCodes:
    def test_auth_error_from_constructor(self, monkeypatch, capsys):
        def boom(**kwargs):
            raise AuthError("no token")

        monkeypatch.setattr(mcd, "McdMcpClient", boom)
        monkeypatch.setattr(mcd, "load_token", lambda cli=None: None)
        assert mcd.main(["check"]) == mcd.EXIT_AUTH
        assert "鉴权错误" in capsys.readouterr().err

    @pytest.mark.parametrize("error,code_name", [
        (AuthError("x"), "EXIT_AUTH"),
        (RateLimitError("x"), "EXIT_RATE_LIMIT"),
        (TransportError("x"), "EXIT_TRANSPORT"),
        (McpToolError("x"), "EXIT_TOOL_ERROR"),
    ])
    def test_command_errors_map_to_exit_codes(self, stub, monkeypatch, error, code_name):
        monkeypatch.setattr(stub, "initialize", lambda: (_ for _ in ()).throw(error))
        assert mcd.main(["check"]) == getattr(mcd, code_name)


class TestVerifyRun:
    """verify_run：真实记录生成器，此前 0% 覆盖。"""

    def _stub(self, monkeypatch, tmp_path, raise_on_init=None):
        class FakeClient:
            def __init__(self, **kwargs):
                self.calls = []

            def initialize(self):
                if raise_on_init:
                    raise raise_on_init
                return {"serverInfo": {"name": "stub", "version": "1.0"}}

            def list_tools(self):
                return [{"name": "a"}, {"name": "b"}]

            def call_tool(self, name, args=None):
                self.calls.append(name)
                return {"data": []}

        monkeypatch.setattr(verify_run, "McdMcpClient", FakeClient)
        monkeypatch.setattr(verify_run, "load_token", lambda: "token")
        out = tmp_path / "verified-run.md"
        monkeypatch.setattr(verify_run, "OUT", out)
        return out

    def test_missing_token_returns_2(self, monkeypatch, capsys):
        monkeypatch.setattr(verify_run, "load_token", lambda: None)
        assert verify_run.main([]) == 2
        assert "未找到 Token" in capsys.readouterr().err

    def test_connectivity_failure_returns_1(self, tmp_path, monkeypatch, capsys):
        self._stub(monkeypatch, tmp_path, raise_on_init=RuntimeError("down"))
        assert verify_run.main([]) == 1
        assert "连通性检查失败" in capsys.readouterr().err

    def test_generates_markdown_and_html(self, tmp_path, monkeypatch, capsys):
        out = self._stub(monkeypatch, tmp_path)
        assert verify_run.main(["--html"]) == 0
        text = out.read_text(encoding="utf-8")
        assert "真实运行验证记录" in text
        assert "stub" in text
        assert (tmp_path / "verified-run-report.html").exists()
        assert "已写入" in capsys.readouterr().out
