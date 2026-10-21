#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP 客户端 HTTP 层测试（v2.2 新增）。

用假的 ``urlopen`` 覆盖真实网络分支：JSON / SSE 解码、会话头、401/429/5xx、
网络异常重试、无法解析的响应、工具错误与关闭会话——这些路径过去只能靠线上
真实 Token 验证，导致覆盖率长期停在 56%。
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mcd_client as mc  # noqa: E402


class FakeResponse:
    """模拟 urlopen 的上下文管理器返回值。"""

    def __init__(self, body: str = "", headers: dict | None = None):
        self._body = body.encode("utf-8")
        self.headers = headers or {"Content-Type": "application/json"}
        self.status = 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def json_rpc(result: dict) -> FakeResponse:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result})
    return FakeResponse(body, {"Content-Type": "application/json", "Mcp-Session-Id": "sess-1"})


def make_client(**kwargs) -> mc.McdMcpClient:
    kwargs.setdefault("token", "test-token")
    kwargs.setdefault("max_retries", 1)
    kwargs.setdefault("rate_limit", 0)
    return mc.McdMcpClient(**kwargs)


def patch_urlopen(monkeypatch, *responses):
    """按顺序返回响应；元素为 Exception 时抛出。"""
    calls = list(responses)

    def fake_urlopen(request, timeout=None):
        if not calls:
            raise AssertionError("urlopen 调用次数超出预期")
        item = calls.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(mc.urllib.request, "urlopen", fake_urlopen)
    return calls


class TestInitialize:
    def test_success_sets_session_and_initialized(self, monkeypatch):
        patch_urlopen(monkeypatch, json_rpc({"serverInfo": {"name": "mcd", "version": "1.0"}}), FakeResponse(""))
        client = make_client()
        info = client.initialize()
        assert info["serverInfo"]["name"] == "mcd"
        assert client.session_id == "sess-1"
        assert client._initialized is True

    def test_sse_body_is_decoded(self, monkeypatch):
        sse = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"serverInfo":{"name":"sse"}}}\n\n'
        patch_urlopen(monkeypatch, FakeResponse(sse, {"Content-Type": "text/event-stream"}), FakeResponse(""))
        client = make_client()
        assert client.initialize()["serverInfo"]["name"] == "sse"

    def test_unparsable_body_raises(self, monkeypatch):
        patch_urlopen(monkeypatch, FakeResponse("not-json", {"Content-Type": "text/plain"}))
        with pytest.raises(mc.TransportError):
            make_client().initialize()

    def test_missing_result_raises(self, monkeypatch):
        patch_urlopen(monkeypatch, FakeResponse('{"jsonrpc":"2.0","id":1}'))
        with pytest.raises(mc.TransportError):
            make_client().initialize()


class TestHttpErrors:
    def test_401_raises_auth_error_without_retry(self, monkeypatch):
        err = urllib.error.HTTPError("u", 401, "unauthorized", {}, io.BytesIO(b"denied"))
        patch_urlopen(monkeypatch, err)
        with pytest.raises(mc.AuthError):
            make_client().initialize()

    def test_429_retries_then_succeeds(self, monkeypatch):
        err = urllib.error.HTTPError("u", 429, "rate", {"Retry-After": "0"}, io.BytesIO(b"slow down"))
        patch_urlopen(monkeypatch, err, json_rpc({"serverInfo": {}}), FakeResponse(""))
        sleeps = []
        monkeypatch.setattr(mc.time, "sleep", lambda s: sleeps.append(s))
        client = make_client(max_retries=1)
        assert client.initialize()["serverInfo"] == {}
        assert len(sleeps) == 1

    def test_each_attempt_passes_through_throttle(self, monkeypatch):
        """重试同样占每分钟配额：每次实际发出的请求都要过限速器。"""
        err = urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b"oops"))
        patch_urlopen(monkeypatch, err, json_rpc({"ok": True}))
        monkeypatch.setattr(mc.time, "sleep", lambda s: None)
        client = make_client(max_retries=1)
        calls = []
        monkeypatch.setattr(client, "_throttle", lambda: calls.append(1))
        client._post({"jsonrpc": "2.0", "id": 1, "method": "x"})
        assert len(calls) == 2, "首次请求 + 一次重试，应各过一次限速器"

    def test_429_exhausted_raises_rate_limit(self, monkeypatch):
        err1 = urllib.error.HTTPError("u", 429, "rate", {}, io.BytesIO(b""))
        err2 = urllib.error.HTTPError("u", 429, "rate", {}, io.BytesIO(b""))
        patch_urlopen(monkeypatch, err1, err2)
        monkeypatch.setattr(mc.time, "sleep", lambda s: None)
        with pytest.raises(mc.RateLimitError):
            make_client(max_retries=1).initialize()

    def test_500_exhausted_raises_transport(self, monkeypatch):
        err1 = urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b"oops"))
        err2 = urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b"oops"))
        patch_urlopen(monkeypatch, err1, err2)
        monkeypatch.setattr(mc.time, "sleep", lambda s: None)
        with pytest.raises(mc.TransportError):
            make_client(max_retries=1).initialize()

    def test_network_error_exhausted_raises_transport(self, monkeypatch):
        patch_urlopen(monkeypatch, urllib.error.URLError("down"), urllib.error.URLError("down"))
        monkeypatch.setattr(mc.time, "sleep", lambda s: None)
        with pytest.raises(mc.TransportError):
            make_client(max_retries=1).initialize()

    def test_4xx_other_than_401_429_raises_transport(self, monkeypatch):
        err = urllib.error.HTTPError("u", 403, "forbidden", {}, io.BytesIO(b"no"))
        patch_urlopen(monkeypatch, err)
        with pytest.raises(mc.TransportError):
            make_client().initialize()


class TestTools:
    def test_list_tools_returns_list(self, monkeypatch):
        client = make_client()
        client._initialized = True
        patch_urlopen(monkeypatch, FakeResponse('{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"a"},{"name":"b"}]}}'))
        assert [t["name"] for t in client.list_tools()] == ["a", "b"]

    def test_list_tools_non_list_result_returns_empty(self, monkeypatch):
        client = make_client()
        client._initialized = True
        patch_urlopen(monkeypatch, FakeResponse('{"jsonrpc":"2.0","id":1,"result":{"tools":"bad"}}'))
        assert client.list_tools() == []

    def test_get_tool_schema_found_and_missing(self):
        client = make_client()
        client.list_tools = lambda: [{"name": "query-meals", "inputSchema": {}}]
        assert client.get_tool_schema("query-meals")["name"] == "query-meals"
        assert client.get_tool_schema("nope") is None

    def test_call_tool_success(self, monkeypatch):
        client = make_client()
        client._initialized = True
        patch_urlopen(monkeypatch, FakeResponse('{"jsonrpc":"2.0","id":1,"result":{"content":[{"text":"ok"}]}}'))
        assert client.call_tool("x", {"a": 1})["content"][0]["text"] == "ok"

    def test_call_tool_jsonrpc_error(self, monkeypatch):
        client = make_client()
        client._initialized = True
        patch_urlopen(monkeypatch, FakeResponse(
            '{"jsonrpc":"2.0","id":1,"error":{"code":-32602,"message":"bad args"}}'))
        with pytest.raises(mc.McpToolError) as exc:
            client.call_tool("x")
        assert "bad args" in str(exc.value)

    def test_call_tool_is_error_result(self, monkeypatch):
        client = make_client()
        client._initialized = True
        patch_urlopen(monkeypatch, FakeResponse(
            '{"jsonrpc":"2.0","id":1,"result":{"isError":true,"content":[{"text":"库存不足"}]}}'))
        with pytest.raises(mc.McpToolError) as exc:
            client.call_tool("x")
        assert "库存不足" in str(exc.value)


class TestSessionLifecycle:
    def test_close_without_session_is_noop(self):
        client = make_client()
        client.session_id = None
        client.close()  # 不应抛错

    def test_close_sends_delete_and_swallows_errors(self, monkeypatch):
        client = make_client()
        client.session_id = "sess-1"

        def boom(request, timeout=None):
            raise urllib.error.URLError("gone")

        monkeypatch.setattr(mc.urllib.request, "urlopen", boom)
        client.close()  # 静默忽略
        assert client._initialized is False

    def test_context_manager_initializes_and_closes(self, monkeypatch):
        patch_urlopen(monkeypatch, json_rpc({"serverInfo": {}}), FakeResponse(""))
        client = make_client()
        monkeypatch.setattr(client, "close", lambda: None)
        with client as entered:
            assert entered is client
            assert client._initialized is True
