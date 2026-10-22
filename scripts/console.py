#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""控制台编码修正。

Windows 的默认控制台编码取决于区域设置：英文 / 其他区域是 cp1252，输出中文会抛
``UnicodeEncodeError`` 并让命令整体失败。各 CLI 入口在 ``main()`` 开头调用一次，
把无法表示中文的 stdout/stderr 切到 UTF-8。

原则：
- 已经是 UTF-8 的流不动（避免影响重定向与测试捕获）；
- 切换失败时静默跳过（某些流不支持 ``reconfigure``）；
- 用 ``errors="replace"`` 兜底：终端显示不了中文时退化为占位符，但不会中断业务。
"""
from __future__ import annotations

import sys


def _needs_fix(stream) -> bool:
    encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "").replace("_", "")
    return bool(encoding) and not encoding.startswith("utf")


def ensure_utf8_stdio(streams=None) -> None:
    """把非 UTF-8 的流切到 UTF-8（幂等、失败静默）。

    Args:
        streams: 需要处理的流序列；缺省为 ``(sys.stdout, sys.stderr)``（便于测试注入）。
    """
    targets = streams if streams is not None else (sys.stdout, sys.stderr)
    for stream in targets:
        if stream is None or not _needs_fix(stream):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            continue
