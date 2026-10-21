"""mcd_client 单元测试——全部用例不发起任何网络请求。"""
import json

import pytest

from mcd_client import (
    MAX_BACKOFF_SECONDS,
    MAX_RETRY_AFTER_SECONDS,
    AuthError,
    McdMcpClient,
    _compute_backoff,
    _parse_retry_after,
    _parse_sse,
    load_token,
    result_to_text,
)


# ---------------------------------------------------------------------------
# SSE 解析
# ---------------------------------------------------------------------------
class TestParseSse:
    def test_single_event(self):
        body = 'data: {"jsonrpc": "2.0", "id": 1}\n\n'
        assert _parse_sse(body) == [{"jsonrpc": "2.0", "id": 1}]

    def test_multiline_data_is_joined(self):
        # Streamable HTTP 规范：多行 data: 以换行拼接后再解析 JSON
        body = 'data: {"a":\ndata: 1}\n\n'
        assert _parse_sse(body) == [{"a": 1}]

    def test_comments_and_empty_blocks_ignored(self):
        body = ": ping\n\n: keep-alive\n\ndata: {\"id\": 2}\n\n"
        assert _parse_sse(body) == [{"id": 2}]

    def test_multiple_events_in_order(self):
        body = 'data: {"id": 1}\n\ndata: {"id": 2}\n\n'
        assert [e["id"] for e in _parse_sse(body)] == [1, 2]

    def test_invalid_json_skipped(self):
        body = 'data: not-json\n\ndata: {"ok": true}\n\n'
        assert _parse_sse(body) == [{"ok": True}]

    def test_empty_body(self):
        assert _parse_sse("") == []

    def test_crlf_line_endings(self):
        # 部分服务器以 CRLF 分隔 SSE 帧，解析前需归一化换行
        body = 'data: {"id": 1}\r\n\r\ndata: {"id": 2}\r\n\r\n'
        assert [e["id"] for e in _parse_sse(body)] == [1, 2]


# ---------------------------------------------------------------------------
# 重试退避计算
# ---------------------------------------------------------------------------
class TestBackoff:
    def test_grows_with_attempt(self):
        assert _compute_backoff(2) > _compute_backoff(0)

    def test_respects_retry_after(self):
        # Retry-After 大于指数退避基数时必须等待至少 Retry-After 秒
        assert _compute_backoff(0, retry_after=10.0) >= 10.0

    def test_capped_at_max(self):
        for attempt in (0, 2, 8):
            assert _compute_backoff(attempt, retry_after=999.0) <= MAX_RETRY_AFTER_SECONDS

    def test_retry_after_above_backoff_is_honored(self):
        # 服务器要求等待 120s 时不能截到 30s，否则必然再撞 429
        assert _compute_backoff(0, retry_after=120.0) == 120.0
        assert _compute_backoff(3, retry_after=60.0) == 60.0

    def test_non_negative(self):
        assert _compute_backoff(0) >= 0.0
        assert _compute_backoff(0, retry_after=-5.0) >= 0.0

    def test_parse_retry_after(self):
        assert _parse_retry_after("5") == 5.0
        assert _parse_retry_after("0.5") == 0.5
        assert _parse_retry_after(None) == 0.0
        assert _parse_retry_after("abc") == 0.0
        assert _parse_retry_after("-3") == 0.0


# ---------------------------------------------------------------------------
# Token 解析优先级：CLI 参数 > 环境变量 > Token 文件
# ---------------------------------------------------------------------------
class TestLoadToken:
    def test_cli_token_wins(self, monkeypatch):
        monkeypatch.setenv("MCD_MCP_TOKEN", "env-token")
        assert load_token("cli-token") == "cli-token"

    def test_env_token_stripped(self, monkeypatch):
        monkeypatch.setenv("MCD_MCP_TOKEN", " env-token ")
        assert load_token(None) == "env-token"

    def test_token_file_fallback(self, monkeypatch, tmp_path):
        token_file = tmp_path / "token.txt"
        token_file.write_text("file-token\n", encoding="utf-8")
        monkeypatch.delenv("MCD_MCP_TOKEN", raising=False)
        monkeypatch.setenv("MCD_MCP_TOKEN_FILE", str(token_file))
        assert load_token(None) == "file-token"

    def test_missing_everything_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MCD_MCP_TOKEN", raising=False)
        monkeypatch.setenv("MCD_MCP_TOKEN_FILE", str(tmp_path / "nope.txt"))
        assert load_token(None) is None


# ---------------------------------------------------------------------------
# 客户端（不联网）
# ---------------------------------------------------------------------------
class TestClient:
    def test_missing_token_raises_auth_error(self):
        with pytest.raises(AuthError) as exc_info:
            McdMcpClient(token=None)
        assert "open.mcd.cn" in str(exc_info.value)

    def test_headers_bearer_and_session(self):
        client = McdMcpClient(token="secret-token")
        client.session_id = "session-abc"
        headers = client._headers()
        assert headers["Authorization"] == "Bearer secret-token"
        assert headers["Mcp-Session-Id"] == "session-abc"
        assert "text/event-stream" in headers["Accept"]

    def test_no_session_header_before_initialize(self):
        headers = McdMcpClient(token="t")._headers()
        assert "Mcp-Session-Id" not in headers

    def test_decode_json_payload(self):
        client = McdMcpClient(token="t")
        raw = '{"jsonrpc": "2.0", "id": 1, "result": {}}'
        assert client._decode_payload(raw, "application/json")["id"] == 1

    def test_decode_sse_payload(self):
        client = McdMcpClient(token="t")
        assert client._decode_payload('data: {"id": 7}\n\n', "text/event-stream") == {"id": 7}

    def test_decode_empty_body_returns_none(self):
        client = McdMcpClient(token="t")
        assert client._decode_payload("", "application/json") is None

    def test_decode_unparseable_returns_none(self):
        client = McdMcpClient(token="t")
        assert client._decode_payload("hello", "text/plain") is None


# ---------------------------------------------------------------------------
# 结果转文本
# ---------------------------------------------------------------------------
class TestResultToText:
    def test_text_blocks_joined(self):
        result = {"content": [{"type": "text", "text": "A"}, {"type": "text", "text": "B"}]}
        assert result_to_text(result) == "A\nB"

    def test_non_text_blocks_serialized(self):
        result = {"content": [{"type": "image", "data": "x"}]}
        assert '"type": "image"' in result_to_text(result)

    def test_fallback_to_json(self):
        assert json.loads(result_to_text({"x": 1})) == {"x": 1}


class TestRateLimitThrottle:
    """v2.0.4 新增：主动滑动窗口限速（300 次/分钟滑动窗口）。"""

    def _client(self, rate_limit):
        from mcd_client import McdMcpClient as MCPClient
        return MCPClient(token="t", rate_limit=rate_limit)

    def test_disabled_when_zero(self):
        c = self._client(0)
        import time as _t
        orig = _t.sleep
        calls = []
        _t.sleep = lambda s: calls.append(s)
        try:
            for _ in range(5):
                c._throttle()
        finally:
            _t.sleep = orig
        assert calls == [] and len(c._send_times) == 0  # disabled = 零开销不追踪

    def test_sleep_called_when_window_full(self, monkeypatch):
        import time as _t
        c = self._client(2)
        now = _t.monotonic()
        c._send_times.extend([now - 1.0, now - 2.0])  # 窗口已满（2/2）
        sleeps = []
        monkeypatch.setattr(_t, "sleep", lambda s: sleeps.append(s))
        c._throttle()
        assert len(sleeps) == 1 and sleeps[0] > 0

    def test_no_sleep_when_window_not_full(self, monkeypatch):
        import time as _t
        c = self._client(3)
        monkeypatch.setattr(_t, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("should not sleep")))
        c._throttle()
        c._throttle()
        assert len(c._send_times) == 2

    def test_old_entries_slide_out(self):
        import time as _t
        c = self._client(2)
        now = _t.monotonic()
        c._send_times.extend([now - 120.0, now - 119.0])  # 远超窗口 → 全部滑出
        c._throttle()
        assert len(c._send_times) == 1


class TestTokenPermissionCheck:
    """v2.1.2 新增：Token 文件权限检查（仅 POSIX 生效）。"""

    def test_warns_on_loose_permissions(self, tmp_path, monkeypatch, capsys):
        import mcd_client
        f = tmp_path / "tok"
        f.write_text("abc123\n", encoding="utf-8")
        monkeypatch.setattr(mcd_client.os, "name", "posix")
        monkeypatch.setattr(mcd_client.os, "stat", lambda p: type("S", (), {"st_mode": 0o644})())
        monkeypatch.setattr(mcd_client.os.path, "isfile", lambda p: True)
        monkeypatch.setenv(mcd_client.TOKEN_FILE_ENV_VAR, str(f))
        monkeypatch.delenv(mcd_client.TOKEN_ENV_VAR, raising=False)
        token = mcd_client.load_token()
        assert token == "abc123"
        err = capsys.readouterr().err
        assert "权限过宽" in err

    def test_no_warn_on_private_permissions(self, tmp_path, monkeypatch, capsys):
        import mcd_client
        f = tmp_path / "tok"
        f.write_text("abc123\n", encoding="utf-8")
        monkeypatch.setattr(mcd_client.os, "name", "posix")
        monkeypatch.setattr(mcd_client.os, "stat", lambda p: type("S", (), {"st_mode": 0o600})())
        monkeypatch.setattr(mcd_client.os.path, "isfile", lambda p: True)
        monkeypatch.setenv(mcd_client.TOKEN_FILE_ENV_VAR, str(f))
        monkeypatch.delenv(mcd_client.TOKEN_ENV_VAR, raising=False)
        assert mcd_client.load_token() == "abc123"
        assert "权限过宽" not in capsys.readouterr().err
