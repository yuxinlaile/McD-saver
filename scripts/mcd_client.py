#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦当劳中国 MCP Server 客户端核心模块。

通过 MCP Streamable HTTP 协议与麦当劳中国官方远程托管的 MCP Server
（默认地址 https://mcp.mcd.cn）通信，提供：

- MCP 会话生命周期管理（initialize / notifications/initialized / 会话 ID 保持）
- 工具发现（tools/list）
- 工具调用（tools/call）
- 完整错误处理：
    * 401  Token 无效 / 过期 / 未提供 -> AuthError
    * 429  触发限流（600 次/分钟）   -> 指数退避 + 抖动自动重试，尊重 Retry-After
    * 5xx  服务端错误               -> 自动重试
    * 网络错误 / 超时               -> 自动重试
    * JSON-RPC error / isError      -> McpToolError

仅依赖 Python 标准库（3.9+），无需安装任何第三方运行时依赖。

安全约定：本模块绝不会将 Token 打印到日志或异常消息中。

用法示例::

    from mcd_client import McdMcpClient

    client = McdMcpClient(token="YOUR_MCP_TOKEN")
    tools = client.list_tools()                      # 获取工具清单
    result = client.call_tool("query-nearby-stores", {"address": "北京市朝阳区xxx"})
    print(result_to_text(result))                    # 提取工具返回的文本内容
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from collections import deque
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

__all__ = [
    "McpError",
    "AuthError",
    "RateLimitError",
    "TransportError",
    "McpToolError",
    "McdMcpClient",
    "load_token",
    "result_to_text",
    "DEFAULT_BASE_URL",
]

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = os.environ.get("MCD_MCP_URL", "https://mcp.mcd.cn")
DEFAULT_TIMEOUT = 30.0          # 单次请求超时（秒）
DEFAULT_MAX_RETRIES = 3         # 可重试错误的最大自动重试次数
DEFAULT_RATE_LIMIT = 300        # 主动滑动窗口限速（次/分钟，官方上限 600 的一半）
MAX_BACKOFF_SECONDS = 30.0      # 单次退避等待上限（秒）
TOKEN_ENV_VAR = "MCD_MCP_TOKEN"
TOKEN_FILE_ENV_VAR = "MCD_MCP_TOKEN_FILE"
DEFAULT_TOKEN_FILE = "~/.mcd_mcp_token"

# MCP 协议版本（Streamable HTTP 传输规范）
PROTOCOL_VERSION = "2025-03-26"

CLIENT_INFO = {"name": "maimai-saver", "version": "2.2.3"}
USER_AGENT = "maimai-saver/2.2.3"


# ---------------------------------------------------------------------------
# 异常体系
# ---------------------------------------------------------------------------
class McpError(Exception):
    """麦当劳 MCP 技能所有异常的基类。"""


class AuthError(McpError):
    """401 —— MCP Token 无效、已过期或未提供。

    处理建议：引导用户前往 https://open.mcd.cn/mcp 重新申请 Token，
    并更新 MCD_MCP_TOKEN 环境变量或 --token 参数。
    """


class RateLimitError(McpError):
    """429 —— 触发限流（每个 Token 每分钟最多 600 次请求）。

    本客户端已内置指数退避重试；若重试后仍失败，应降低调用频率。
    """


class TransportError(McpError):
    """网络 / HTTP 层错误：超时、连接失败、5xx 等。"""


class McpToolError(McpError):
    """工具层错误：JSON-RPC error 响应，或工具结果中 isError=true。

    Attributes:
        data: 原始错误信息（dict 或任意 JSON 值），便于上层排查。
    """

    def __init__(self, message: str, data: Any = None):
        super().__init__(message)
        self.data = data


class EndpointNotAllowedError(McpError):
    """请求地址不在官方白名单内——防止带 MCP Token 的请求被发往任意主机。"""


# 官方 MCP Server 主机白名单：默认只允许这些地址携带 Token 通信
OFFICIAL_HOSTS = ("mcp.mcd.cn",)


def endpoint_host(url: str) -> str:
    """取 URL 的主机名（小写）；解析失败返回空串。"""
    try:
        import urllib.parse

        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001 - 解析失败按空串处理
        return ""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def load_token(cli_token: Optional[str] = None) -> Optional[str]:
    """按优先级解析 MCP Token：命令行参数 > 环境变量 > Token 文件。

    Token 文件路径默认为 ``~/.mcd_mcp_token``，可通过环境变量
    ``MCD_MCP_TOKEN_FILE`` 覆盖。文件内容应为纯 Token 文本（自动去除首尾空白）。
    """
    if cli_token:
        return cli_token.strip()
    env_token = os.environ.get(TOKEN_ENV_VAR)
    if env_token:
        return env_token.strip()
    token_file = os.environ.get(TOKEN_FILE_ENV_VAR, DEFAULT_TOKEN_FILE)
    path = os.path.expanduser(token_file)
    if os.path.isfile(path):
        # 权限检查（v2.1.2，安全）：Unix 上文件对其他用户可读时提示收紧；
        # Windows 无 POSIX mode 语义，跳过（依赖 NTFS ACL）
        if os.name == "posix":
            try:
                mode = os.stat(path).st_mode & 0o777
                if mode & 0o077:
                    print(
                        "警告: Token 文件 {0} 权限过宽（{1:o}），建议执行 chmod 600 {0} "
                        "以防其他用户读取。".format(path, mode),
                        file=sys.stderr,
                    )
            except OSError:
                pass
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read().strip()
            if content:
                return content.splitlines()[0].strip()
        except OSError:
            return None
    return None


def _compute_backoff(attempt: int, retry_after: float = 0.0) -> float:
    """计算第 attempt 次重试前的等待秒数（指数退避 + 随机抖动）。

    规则：``max(Retry-After, 2**attempt + jitter)``，封顶
    ``MAX_BACKOFF_SECONDS``。jitter 取 [0, 1) 均匀随机值。

    Args:
        attempt: 已失败次数（0 表示首次失败后）。
        retry_after: 服务器 Retry-After 响应头值（秒），无则传 0。
    """
    base = 2.0 ** attempt + random.uniform(0.0, 1.0)
    return min(max(retry_after, base), MAX_BACKOFF_SECONDS)


def _parse_retry_after(value: Optional[str]) -> float:
    """将 Retry-After 响应头解析为秒数；非法或缺失时返回 0。"""
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except ValueError:
        return 0.0


def _parse_sse(body: str) -> List[Dict[str, Any]]:
    """解析 text/event-stream 响应体，返回其中的 JSON-RPC 消息列表。

    Streamable HTTP 规范允许服务器以 SSE 帧返回 JSON-RPC 响应，
    每个事件块可能包含多行 ``data:`` 字段（需按换行拼接后再解析 JSON）。
    心跳注释行（以 ``:`` 开头）与空块会被忽略。
    换行符先做 CRLF/CR 归一化，兼容不同服务器的帧分隔风格。
    """
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    events: List[Dict[str, Any]] = []
    for block in body.split("\n\n"):
        data_lines = []
        for line in block.splitlines():
            if line.startswith(":"):
                continue  # SSE 注释/心跳帧
            if line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if not data_lines:
            continue
        try:
            events.append(json.loads("\n".join(data_lines)))
        except json.JSONDecodeError:
            continue
    return events


def result_to_text(result: Any) -> str:
    """将 tools/call 的结果转换为可读文本。

    优先拼接 content 数组中的 text 块；否则回退为格式化 JSON。
    """
    if isinstance(result, dict) and isinstance(result.get("content"), list):
        parts: List[str] = []
        for item in result["content"]:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]))
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        if parts:
            return "\n".join(parts)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _extract_json_object(text: str) -> Any:
    """从一段文本里取出第一个完整的 JSON 对象（花括号配对，跳过字符串内的括号）。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:index + 1])
                except (ValueError, TypeError):
                    return None
    return None


def _json_from_text(text: str) -> Any:
    """从文本中解析 JSON：整段 JSON → `## Original Response` 之后的 JSON → 内嵌 JSON 对象。"""
    candidate = text.strip()
    if "## Original Response" in candidate:
        candidate = candidate.rsplit("## Original Response", 1)[-1].strip()
    try:
        return json.loads(candidate)
    except (ValueError, TypeError):
        pass
    return _extract_json_object(candidate)


def tool_json(result: Any) -> Any:
    """从 tools/call 的结果里取出 JSON 载荷（取不到时返回 None）。

    优先级：
    1. ``structuredContent``——官方 MCP 的结构化载荷。**券的 couponId/couponCode
       等关键字段只在这里**（文本 content 是给人看的 Markdown 表格，不含这些字段）；
    2. 文本 content：常见形态是「Markdown 字段说明 + `## Original Response` 后的真实 JSON」，
       且 JSON 之后可能还跟着展示说明文字。

    调用方要拿结构化数据时应使用本函数，不要直接对 ``result["data"]`` 取值。
    """
    if isinstance(result, dict):
        structured = result.get("structuredContent")
        if isinstance(structured, dict) and structured.get("data") is not None:
            return structured
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                parsed = _json_from_text(str(item.get("text", "")))
                if parsed is not None:
                    return parsed
            return None
        return result
    if isinstance(result, str):
        return _json_from_text(result)
    return None


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------
class McdMcpClient:
    """麦当劳中国 MCP Server 的同步 Streamable HTTP 客户端。

    Args:
        token: MCP Token（必填）。推荐通过 :func:`load_token` 解析。
        base_url: MCP Server 地址，默认 ``https://mcp.mcd.cn``。
        timeout: 单次 HTTP 请求超时秒数。
        max_retries: 针对可重试错误（429/5xx/网络错误）的最大自动重试次数。
        verbose: 输出简要调试信息到 stderr（绝不包含 Token）。

    Raises:
        AuthError: Token 缺失或被服务器拒绝（401）。
        RateLimitError: 重试后仍被限流（429）。
        TransportError: 网络层错误。
        McpToolError: 工具调用返回错误。
    """

    def __init__(
        self,
        token: Optional[str],
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        verbose: bool = False,
        rate_limit: int = DEFAULT_RATE_LIMIT,
        allow_non_official_url: bool = False,
    ) -> None:
        if not token:
            raise AuthError(
                "缺少 MCP Token。请前往 https://open.mcd.cn/mcp 登录并申请 Token，"
                "然后通过环境变量 MCD_MCP_TOKEN、Token 文件（~/.mcd_mcp_token）"
                "或 --token 参数提供。"
            )
        # Token 只能发往官方主机：请求头里带着 Bearer Token，
        # 一次误配置的 --url / MCD_MCP_URL 就可能把凭证送到第三方手里。
        host = endpoint_host(base_url)
        if host and host not in OFFICIAL_HOSTS:
            if not allow_non_official_url:
                raise EndpointNotAllowedError(
                    "拒绝向非官方地址 {0} 发送请求：请求头中含 MCP Token。"
                    "官方地址为 https://mcp.mcd.cn；确需自建代理或本地调试时，"
                    "请显式加 --allow-non-official-url。".format(host)
                )
            print(
                "警告: 正在向非官方 MCP 地址 {0} 发送请求——请求头中包含你的 MCP Token，"
                "请确认该地址可信。".format(host),
                file=sys.stderr,
            )
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.verbose = verbose
        self.session_id: Optional[str] = None
        self._initialized = False
        self._request_id = 0
        # 主动滑动窗口限速：默认 300 次/分钟，
        # 为官方上限 600 留一半余量，避免批量比对场景触发 429 被动等待
        self._rate_limit = max(0, int(rate_limit))
        self._send_times: deque = deque()

    # -- 内部：日志 ---------------------------------------------------------
    def _log(self, message: str) -> None:
        if self.verbose:
            print("[mcd-mcp] {0}".format(message), file=sys.stderr)

    # -- 内部：主动限速 -----------------------------------------------------
    def _throttle(self) -> None:
        """滑动窗口限速：rate_limit 次/60s，超窗则等待最早请求滑出窗口。"""
        if not self._rate_limit:
            return
        now = time.monotonic()
        while self._send_times and now - self._send_times[0] >= 60.0:
            self._send_times.popleft()
        if len(self._send_times) >= self._rate_limit:
            wait = 60.0 - (now - self._send_times[0])
            self._log("主动限速：窗口已满，等待 {0:.1f}s".format(wait))
            time.sleep(max(0.0, wait))
        self._send_times.append(time.monotonic())

    # -- 内部：请求头 -------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer {0}".format(self.token),
            "User-Agent": USER_AGENT,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    # -- 内部：响应体解码 ---------------------------------------------------
    def _decode_payload(self, raw: str, content_type: str) -> Optional[Dict[str, Any]]:
        raw = raw.strip()
        if not raw:
            return None
        if "text/event-stream" in content_type.lower():
            events = _parse_sse(raw)
            if not events:
                return None
            # 服务器可能推送多个事件，取最后一个 JSON-RPC 消息作为本次响应
            return events[-1]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    # -- 内部：JSON-RPC 消息构造 --------------------------------------------
    def _jsonrpc(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        is_notification: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """构造并发送一条 JSON-RPC 消息，返回解码后的响应消息。

        通知类消息（无 id）无响应体，返回 None；其余消息必须携带 result，
        否则抛出 TransportError。

        Raises:
            TransportError: 服务器未返回有效 JSON-RPC 消息。
        """
        self._request_id += 1
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        message = self._post(payload, is_notification=is_notification)
        if is_notification:
            return None
        # JSON-RPC 的 error 响应没有 result，交由调用方（如 call_tool）按错误码处理，
        # 不能在这里当成「无结果」吞掉——否则会丢失 code/message，且错误分支不可达。
        if message is None or ("result" not in message and "error" not in message):
            raise TransportError("{0} 未返回有效结果".format(method))
        return message

    # -- 内部：带重试的 POST ------------------------------------------------
    def _post(
        self, payload: Dict[str, Any], *, is_notification: bool = False
    ) -> Optional[Dict[str, Any]]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error: Optional[McpError] = None
        self._throttle()

        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                self.base_url, data=body, headers=self._headers(), method="POST"
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    session_id = response.headers.get("Mcp-Session-Id")
                    if session_id:
                        self.session_id = session_id
                    raw = response.read().decode("utf-8", errors="replace")
                    content_type = response.headers.get("Content-Type", "")
                    if is_notification:
                        # 通知类消息（如 notifications/initialized）通常返回 202/空体
                        return None
                    decoded = self._decode_payload(raw, content_type)
                    if decoded is None:
                        raise TransportError(
                            "服务器返回了无法解析的响应体"
                            "（Content-Type: {0}）".format(content_type or "unknown")
                        )
                    return decoded

            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", errors="replace")[:160]
                except Exception:  # noqa: BLE001 - 读取错误详情失败不应中断流程
                    pass

                if exc.code == 401:
                    # 401 属于确定性错误，重试无意义，直接抛出
                    raise AuthError(
                        "MCP Token 无效、已过期或未提供（HTTP 401）。"
                        "请前往 https://open.mcd.cn/mcp 检查并重新申请 Token。"
                    ) from exc

                if exc.code == 429:
                    last_error = RateLimitError(
                        "触发限流（HTTP 429）：每个 Token 每分钟最多 600 次请求，"
                        "请降低调用频率。"
                    )
                    if attempt < self.max_retries:
                        wait = _compute_backoff(attempt, _parse_retry_after(
                            exc.headers.get("Retry-After") if exc.headers else None
                        ))
                        self._log("429 限流，{0:.1f}s 后进行第 {1} 次重试".format(wait, attempt + 1))
                        time.sleep(wait)
                        continue
                    raise last_error from exc

                if exc.code >= 500 and attempt < self.max_retries:
                    wait = _compute_backoff(attempt)
                    self._log("HTTP {0}，{1:.1f}s 后进行第 {2} 次重试".format(exc.code, wait, attempt + 1))
                    time.sleep(wait)
                    continue

                raise TransportError(
                    "HTTP {0}: {1}".format(exc.code, detail or "服务器返回错误")
                ) from exc

            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_error = TransportError("网络错误：{0}".format(exc))
                if attempt < self.max_retries:
                    wait = _compute_backoff(attempt)
                    self._log("网络错误，{0:.1f}s 后进行第 {1} 次重试".format(wait, attempt + 1))
                    time.sleep(wait)
                    continue
                raise last_error from exc

        raise last_error or TransportError("请求失败：未知错误")

    # -- 公开：会话生命周期 -------------------------------------------------
    def initialize(self) -> Dict[str, Any]:
        """执行 MCP 握手：initialize + notifications/initialized。

        Returns:
            initialize 结果（含 serverInfo、capabilities 等）。
        """
        message = self._jsonrpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        result = message.get("result") if message else None
        if not isinstance(result, dict):
            raise TransportError("initialize 未返回有效结果")
        # 发送 initialized 通知（无响应体）
        self._jsonrpc("notifications/initialized", is_notification=True)
        self._initialized = True
        self._log("会话已建立: {0}".format(result.get("serverInfo", {})))
        return result

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def close(self) -> None:
        """结束会话（尽力发送 DELETE；失败静默忽略，会话由服务端超时回收）。"""
        if not self.session_id:
            return
        request = urllib.request.Request(
            self.base_url, headers=self._headers(), method="DELETE"
        )
        try:
            urllib.request.urlopen(request, timeout=self.timeout)
        except Exception:  # noqa: BLE001 - 关闭失败无需上报
            pass
        self._initialized = False

    def __enter__(self) -> "McdMcpClient":
        self._ensure_initialized()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # -- 公开：工具发现与调用 -----------------------------------------------
    def list_tools(self) -> List[Dict[str, Any]]:
        """获取 MCP Server 支持的全部工具（含名称、描述与入参 schema）。"""
        self._ensure_initialized()
        message = self._jsonrpc("tools/list")
        result = message.get("result") if isinstance(message, dict) else None
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return tools if isinstance(tools, list) else []

    def get_tool_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """按名称查找工具定义（含 inputSchema）。未找到时返回 None。"""
        for tool in self.list_tools():
            if tool.get("name") == name:
                return tool
        return None

    def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """调用一个 MCP 工具并返回其结果。

        Args:
            name: 工具名，例如 ``query-nearby-stores``。
            arguments: 工具入参（dict）。未提供时传空对象。

        Returns:
            tools/call 的 result（通常为包含 ``content`` 数组的 dict）。

        Raises:
            McpToolError: 服务器返回 JSON-RPC error，或结果中 isError=true。
        """
        self._ensure_initialized()
        message = self._jsonrpc(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        if message is None:
            raise TransportError("服务器未返回任何 JSON-RPC 响应")

        if message.get("error"):
            error = message["error"]
            raise McpToolError(
                "工具调用失败 [code={0}]: {1}".format(
                    error.get("code"), error.get("message")
                ),
                data=error,
            )

        result = message.get("result")
        if isinstance(result, dict) and result.get("isError"):
            texts = [
                str(item.get("text", ""))
                for item in result.get("content", [])
                if isinstance(item, dict)
            ]
            detail = " ".join(t for t in texts if t) or "（服务器未提供错误详情）"
            raise McpToolError("工具 {0} 返回错误: {1}".format(name, detail), data=result)
        return result
