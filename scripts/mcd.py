#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦省钱助手 —— 命令行入口。

提供五个子命令，覆盖 MCP Server 的全部工具（2026-10 实测为 35 个）：

    check              连通性 / Token 有效性检查
    tools              列出服务器支持的全部工具
    schema  <tool>     查看指定工具的名称、描述与入参 JSON Schema
    call    <tool>     调用指定工具并输出结果
    claim              查看并领取麦麦省可领券（交互确认，无定时无后台）

Token 解析优先级（与 mcd_client.load_token 一致）：
    1. --token 参数
    2. 环境变量 MCD_MCP_TOKEN
    3. Token 文件（默认 ~/.mcd_mcp_token，可用 MCD_MCP_TOKEN_FILE 覆盖）

示例::

    # 1. 检查 Token 与连通性
    export MCD_MCP_TOKEN="你的Token"
    python mcd.py check

    # 2. 查看全部工具
    python mcd.py tools

    # 3. 查看某个工具的入参结构
    python mcd.py schema query-nearby-stores

    # 4. 调用工具（两种传参方式）
    python mcd.py call query-nearby-stores --args '{"address": "北京市朝阳区xxx"}'
    python mcd.py call query-nearby-stores --arg address="北京市朝阳区xxx"

全局选项（--token/--url/--timeout/--retries/--verbose）既可放在子命令之前，
也可放在子命令之后，两种写法等价。

退出码约定（便于 Agent / 脚本编排）：
    0  成功
    1  工具层错误（McpToolError / 参数错误）
    2  鉴权失败（AuthError）
    3  触发限流且重试无效（RateLimitError）
    4  网络 / 传输层错误（TransportError）
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

try:  # 兼容“直接运行脚本”与“作为模块运行”两种方式
    from mcd_client import (
        AuthError,
        EndpointNotAllowedError,
        McpError,
        McpToolError,
        RateLimitError,
        TransportError,
        load_token,
        result_to_text,
        McdMcpClient,
    )
except ImportError:  # pragma: no cover - 直接以路径方式运行脚本时
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from mcd_client import (
        AuthError,
        EndpointNotAllowedError,
        McpError,
        McpToolError,
        RateLimitError,
        TransportError,
        load_token,
        result_to_text,
        McdMcpClient,
    )

EXIT_OK = 0
EXIT_TOOL_ERROR = 1
EXIT_AUTH = 2
EXIT_RATE_LIMIT = 3
EXIT_TRANSPORT = 4


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------
def _parse_arg_value(value: str) -> Any:
    """将 --arg 的值解析为 JSON 值；解析失败时按原始字符串处理。

    这使得 ``--arg count=3`` 传数字、``--arg flag=true`` 传布尔值成为可能，
    同时 ``--arg address=北京市朝阳区`` 这类纯文本也能正常工作。
    """
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


def _merge_arguments(
    args_json: Optional[str], arg_pairs: Optional[List[str]]
) -> Dict[str, Any]:
    """合并 --args（整体 JSON）与 --arg（键值对）两种传参方式。"""
    merged: Dict[str, Any] = {}
    if args_json:
        try:
            parsed = json.loads(args_json)
        except json.JSONDecodeError as exc:
            raise SystemExit(
                "错误: --args 不是合法的 JSON: {0}\n"
                '示例: --args \'{{"address": "北京市朝阳区xxx"}}\''.format(exc)
            )
        if not isinstance(parsed, dict):
            raise SystemExit("错误: --args 必须是一个 JSON 对象（dict）")
        merged.update(parsed)
    for pair in arg_pairs or []:
        if "=" not in pair:
            raise SystemExit(
                "错误: --arg 格式应为 key=value，收到: {0!r}".format(pair)
            )
        key, _, value = pair.partition("=")
        merged[key.strip()] = _parse_arg_value(value)
    return merged


def build_parser() -> argparse.ArgumentParser:
    # 公共选项同时挂到主解析器与各子命令上，使其在子命令之前或之后均可使用：
    #   mcd --token xxx check  与  mcd check --token xxx  等价
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--token",
        default=argparse.SUPPRESS,
        help="MCP Token（优先级最高；也可用环境变量 MCD_MCP_TOKEN 或文件 ~/.mcd_mcp_token）",
    )
    common.add_argument(
        "--url",
        default=argparse.SUPPRESS,
        help="MCP Server 地址（默认 https://mcp.mcd.cn；非官方地址需加 --allow-non-official-url）",
    )
    common.add_argument(
        "--allow-non-official-url",
        action="store_true",
        default=argparse.SUPPRESS,
        help="允许向非官方 MCP 地址发送请求（请求头含 Token，请确认地址可信）",
    )
    common.add_argument(
        "--timeout",
        type=float,
        default=argparse.SUPPRESS,
        help="单次请求超时秒数（默认 30）",
    )
    common.add_argument(
        "--retries",
        type=int,
        default=argparse.SUPPRESS,
        help="429/5xx/网络错误的最大自动重试次数（默认 3）",
    )
    common.add_argument(
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help="输出调试信息到 stderr（不包含 Token）",
    )

    parser = argparse.ArgumentParser(
        prog="mcd",
        description=(
            "麦麦省钱助手命令行工具 —— 通过麦当劳官方 MCP Server "
            "(https://mcp.mcd.cn) 查询门店、菜单、优惠券并完成点餐等操作。"
        ),
        parents=[common],
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    sub.add_parser("check", help="检查 Token 有效性与服务器连通性", parents=[common])

    sub.add_parser("tools", help="列出服务器支持的全部工具", parents=[common])

    schema_parser = sub.add_parser(
        "schema", help="查看指定工具的入参 JSON Schema", parents=[common]
    )
    schema_parser.add_argument("tool", help="工具名，例如 query-nearby-stores")

    call_parser = sub.add_parser("call", help="调用指定工具", parents=[common])
    call_parser.add_argument("tool", help="工具名，例如 query-nearby-stores")
    call_group = call_parser.add_mutually_exclusive_group()
    call_group.add_argument(
        "--args",
        dest="args_json",
        default=None,
        help='工具入参（整体 JSON 对象），例如 \'{"address": "..."}\'',
    )
    call_group.add_argument(
        "--arg",
        dest="arg_pairs",
        action="append",
        metavar="key=value",
        help="工具入参（键值对，可重复；值会尝试按 JSON 解析）",
    )
    call_parser.add_argument(
        "--raw",
        action="store_true",
        help="输出 tools/call 的原始 JSON 结果（默认输出可读文本）",
    )

    claim_parser = sub.add_parser(
        "claim",
        help="查看并领取麦麦省可领券（先展示清单，交互确认后一键领取）",
        parents=[common],
    )
    claim_parser.add_argument(
        "--yes", action="store_true",
        help="跳过交互确认直接领取（脚本场景用；默认必须按 y 确认）",
    )
    return parser


# ---------------------------------------------------------------------------
# 子命令实现
# ---------------------------------------------------------------------------
def cmd_check(client: McdMcpClient) -> int:
    server_info = client.initialize()
    tools = client.list_tools()
    server_name = server_info.get("serverInfo", {}).get("name", "unknown")
    server_version = server_info.get("serverInfo", {}).get("version", "unknown")
    print("[OK] 连接成功")
    print("  服务器: {0} v{1}".format(server_name, server_version))
    # 地址回显时去掉可能内嵌的凭据（https://user:pass@host 形态）
    safe_url = client.base_url
    if "@" in safe_url:
        safe_url = safe_url.split("//", 1)[0] + "//***@" + safe_url.split("@", 1)[1]
    print("  地址: {0}".format(safe_url))
    print("  可用工具数: {0}".format(len(tools)))
    return EXIT_OK


def cmd_tools(client: McdMcpClient) -> int:
    tools = client.list_tools()
    if not tools:
        print("（服务器未返回任何工具）")
        return EXIT_OK
    print("共 {0} 个工具：\n".format(len(tools)))
    for tool in tools:
        name = tool.get("name", "?")
        desc = (tool.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 100:
            desc = desc[:97] + "..."
        print("  {0:<32} {1}".format(name, desc))
    return EXIT_OK


def cmd_schema(client: McdMcpClient, tool_name: str) -> int:
    schema = client.get_tool_schema(tool_name)
    if schema is None:
        print("错误: 未找到工具 {0!r}，可先执行 `tools` 子命令查看全部工具。".format(tool_name), file=sys.stderr)
        return EXIT_TOOL_ERROR
    print(json.dumps(schema, ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_call(
    client: McdMcpClient, tool_name: str, arguments: Dict[str, Any], raw: bool
) -> int:
    result = client.call_tool(tool_name, arguments)
    if raw:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result_to_text(result))
    return EXIT_OK


def _looks_empty(text: str) -> bool:
    """判断可领券清单是否为空（宽容匹配常见的空态文案）。"""
    stripped = text.strip()
    if not stripped or stripped in ("[]", "{}", "null", "无", "暂无"):
        return True
    return any(kw in stripped for kw in ("暂无可领", "没有可领", "无可领取", "为空"))


def run_claim(client: McdMcpClient, yes: bool = False,
              confirm_fn=None, out=None) -> int:
    """一次性领券流程：列出可领券 → 用户确认 → auto-bind-coupons 一键领取。

    设计约束（与 SKILL.md 调用规范一致）：用户主动触发、单次执行、
    领取前必须展示清单并确认；不提供任何定时/后台模式。
    """
    out = out or (lambda s: print(s))
    confirm_fn = confirm_fn or input

    result = client.call_tool("available-coupons", {})
    listing = result_to_text(result)
    out("当前可领取的麦麦省券：")
    out(listing if listing.strip() else "（空）")

    if _looks_empty(listing):
        out("暂无可领取的优惠券。")
        return EXIT_OK

    if not yes:
        answer = confirm_fn("确认领取以上全部可领券？(y/N) ")
        if answer.strip().lower() not in ("y", "yes"):
            out("已取消，未执行任何领取操作。")
            return EXIT_OK

    claim_result = client.call_tool("auto-bind-coupons", {})
    out("")
    out("领取结果：")
    out(result_to_text(claim_result))
    out("提示：可在 App「我的优惠券」或用 query-my-coupons 查看券包。")
    return EXIT_OK


def cmd_claim(client: McdMcpClient, yes: bool) -> int:
    return run_claim(client, yes=yes)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return EXIT_OK

    # 公共选项使用 SUPPRESS 默认值，因此未提供时命名空间中不存在该属性
    token = load_token(getattr(args, "token", None))
    client_kwargs: Dict[str, Any] = {
        "token": token,
        "timeout": getattr(args, "timeout", 30.0),
        "max_retries": getattr(args, "retries", 3),
        "verbose": getattr(args, "verbose", False),
        "allow_non_official_url": bool(getattr(args, "allow_non_official_url", False)),
    }
    if getattr(args, "url", None):
        client_kwargs["base_url"] = args.url

    try:
        client = McdMcpClient(**client_kwargs)
    except AuthError as exc:
        print("鉴权错误: {0}".format(exc), file=sys.stderr)
        return EXIT_AUTH
    except EndpointNotAllowedError as exc:
        print("地址校验失败: {0}".format(exc), file=sys.stderr)
        return EXIT_TOOL_ERROR

    try:
        if args.command == "check":
            return cmd_check(client)
        if args.command == "tools":
            return cmd_tools(client)
        if args.command == "schema":
            return cmd_schema(client, args.tool)
        if args.command == "call":
            arguments = _merge_arguments(args.args_json, args.arg_pairs)
            return cmd_call(client, args.tool, arguments, args.raw)
        if args.command == "claim":
            return cmd_claim(client, yes=getattr(args, "yes", False))
        parser.error("未知命令: {0}".format(args.command))
        return EXIT_TOOL_ERROR
    except AuthError as exc:
        print("鉴权错误: {0}".format(exc), file=sys.stderr)
        return EXIT_AUTH
    except RateLimitError as exc:
        print("限流错误: {0}".format(exc), file=sys.stderr)
        return EXIT_RATE_LIMIT
    except TransportError as exc:
        print("传输错误: {0}".format(exc), file=sys.stderr)
        return EXIT_TRANSPORT
    except McpToolError as exc:
        print("工具错误: {0}".format(exc), file=sys.stderr)
        return EXIT_TOOL_ERROR
    except McpError as exc:
        print("MCP 错误: {0}".format(exc), file=sys.stderr)
        return EXIT_TOOL_ERROR
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
