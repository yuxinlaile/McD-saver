# 覆盖率报告（`--cov=scripts`）

> 生成于 2026-10-19，最近更新 v2.5.0（2026-10-22）。覆盖率口径：`pytest --cov=scripts`
> （仅统计 `scripts/` 下的运行时代码，不含 `demo.py`、测试自身与 `__main__` 保护块）。
> 复现命令：`python -m pytest tests/ -q --cov=scripts --cov-report=term-missing`。

## 一、覆盖率为什么不是 100%

### 1.1 现状

| 时点 | 测试数 | 覆盖率 | 说明 |
|---|---|---|---|
| 2026-10-19 分析前 | 201 | **61.9%**（报表四舍五入显示 62%） | CLI 命令层与网络层几乎未测 |
| 补齐 P0 后（v2.2.0） | 245 | **76%** | `mcd.py` 28%→94%、`mcd_client.py` 56%→95%、`version.py` 80%→97% |
| 当前（v2.5.0） | **328** | **79%**（498 / 2406 语句） | CI 门槛 70% → **78%**；新增 `windows-latest` job |

### 1.2 未覆盖明细（498 行）

| 文件 | 未覆盖/总语句 | 覆盖率 | 主要未覆盖内容 | 原因归类 |
|---|---|---|---|---|
| `build_releases.py` | 111 / 237 | 53% | `build_zip`（`git archive`）、`upload_release`（HTTP 上传）、`main` 的 `--all` 分支 | B + C |
| `deal_compare.py` | 94 / 251 | 63% | `add` / `list` / `compare` 的部分分支与格式化输出 | B |
| `sync_readme.py` | 36 / 98 | 63% | `--write` 落盘分支、标记缺失时的报错路径 | A + B |
| `audit_readme.py` | 21 / 96 | 78% | 各项检查的失败分支（命令缺失、版本不一致等） | E |
| `check_toc.py` | 23 / 111 | 79% | `main` 的失败分支（标题数不一致、英文缺章节） | A + E |
| `optimizer.py` | 83 / 401 | 79% | `main`、`--mcp` 真实计价分支、若干渲染分支 | A + B |
| `silent_cost.py` | 73 / 419 | 83% | `main`、`--probe` 实测分支、部分空数据分支 | A + B |
| `version.py` | 13 / 150 | 91% | `main` 的少数退出路径 | A |
| `mcd.py` | 14 / 175 | 92% | `parser.error` 分支、`claim` 少数分支 | E |
| `mcd_client.py` | 23 / 321 | 93% | POSIX 权限告警（Windows 不执行）、极少数异常分支 | D |
| `silent_report.py` | 4 / 67 | 94% | 纸面富贵/无排程等渲染分支 | E |
| `verify_run.py` | 3 / 66 | 95% | `--store-code` 分支、`--out` 指向仓库外时的显示路径 | D |
| `console.py` | 0 / 14 | 100% | — | — |

### 1.3 五类根因

- **A 进程入口**：`main(argv)` 与 `if __name__ == "__main__"` 只在命令行触发，pytest 直接 import 不会执行。
- **B 命令主干**：`deal_compare` / `optimizer` / `silent_cost` / `version` / `build_releases` 的 CLI 分支此前只有 `--help` 冒烟。
- **C 外部依赖**：真实 HTTP（MCP Server）、`git archive`、`gh api` 上传——CI 不应访问生产服务。
- **D 平台分支**：POSIX 文件权限检查在 Windows runner 上不执行；`os.name` 判断天然单侧覆盖。
- **E 防御分支**：IO 失败、JSON 解析失败、空数据、参数错误等，需要专门构造异常输入。

### 1.4 为什么不应追求 100%

| 不可达/不该测的部分 | 原因 | 替代验证 |
|---|---|---|
| `if __name__ == "__main__"`、argparse 帮助/错误文本 | 执行即 `SystemExit`，断言价值低 | CLI 冒烟（`--help` 退出码）+ 子进程测试 |
| 真实 MCP 网络调用、`gh` 上传 | CI 不应依赖外部服务与凭据 | 假 `urlopen` 测试分支 + `examples/verified-run.md` 真实留档 |
| `git archive` 打包路径 | 依赖 tag 与 git 环境 | 本地 `--verify` + Release 资产校验 |
| 平台专属分支 | Windows/Linux 只能覆盖其一 | CI 双平台（`ubuntu-latest` 矩阵 + `windows-latest`）覆盖平台差异 |

**合理目标：85%–90%，且关键路径（金额计算、券排程、错误映射、CLI 退出码）要求 100%。**

## 二、继续提升的路线

### 已完成

- `tests/test_client_http.py`：假 `urlopen` 覆盖 JSON/SSE 解码、会话头、401/429/5xx 重试、网络异常、工具错误、关闭会话。
- `tests/test_cli_commands.py`：桩客户端覆盖 `check` / `tools` / `schema` / `call` / `claim` 与四类错误退出码；
  `verify_run` 的 Token 缺失、连通失败、Markdown/HTML 生成、`--out` 指定路径。
- `tests/test_readme_sync.py` / `test_readme_audit.py`：把 README 与仓库事实的一致性固化成了断言。

### 待补（按性价比排序）

| 任务 | 当前 → 目标 | 做法 |
|---|---|---|
| `deal_compare` CLI | 63% → 85% | `tmp_path` 建券库，跑 `add` / `list` / `compare`，断言排序与退出码 0/1/2 |
| `sync_readme` | 63% → 90% | 临时 README/CHANGELOG 跑 `--write`，覆盖标记缺失与区块不一致两条失败路径 |
| `build_releases` | 53% → 70% | `--index` / `--verify` 失败分支；`git` 与 `urlopen` 打桩，**不发起真实上传** |
| `check_toc` / `audit_readme` 失败分支 | 77%–79% → 95% | 临时 README 制造死链、章节缺失、中英数量不一致、命令缺失 |
| `optimizer --mcp` | 79% → 90% | `prefilter_plans` + 假 pricer 跑通真实计价分支，不联网 |

### 门槛策略

- CI 当前门槛 **78%**（低于实测 79%，留 1pp 余量避免抖动误杀）；提升到 85% 需先补上表前两项。
- 验收命令：`python -m pytest tests/ -q --cov=scripts --cov-fail-under=78` + `python scripts/check_toc.py`。
