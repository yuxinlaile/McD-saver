# 贡献指南（Contributing）

感谢关注麦麦省钱助手！无论是提 Issue、分享比价数据还是提交代码，都非常欢迎。
本文档说明各种参与方式与规范，提交前请花一分钟过一遍。

> English speakers: see the "Quick start for contributors" section below —
> PRs in English are welcome.

## 参与方式总览

| 想做的事 | 去哪里 | 说明 |
|---|---|---|
| 报告 Bug | [Issues](https://github.com/yuxinlaile/McD-saver/issues/new/choose) | 用 Bug 模板，附复现步骤与报错截图 |
| 功能建议 | Issues（Feature 模板） | 先搜一下是否已有同类建议 |
| 使用咨询 / 心得分享 | [Discussions](https://github.com/yuxinlaile/McD-saver/discussions) | General 分享战果，Q&A 提问 |
| 分享美团/抖音团购价格 | Discussions（General） | 贴出券面值/售价/限制，可充实券库示例 |
| 提交代码 | Fork + PR | 见下方流程与自检清单 |
| 改进文档 / 翻译校对 | Fork + PR | README 中英同步是硬要求（见自检清单） |

## 行为准则

- 友善交流，尊重每一位参与者（麦门一家亲）；
- **切勿在任何 Issue / PR / Discussion 中粘贴 MCP Token、密码或个人凭证**；
  如不慎泄露，立即到 [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 重新申请；
- 讨论以技术和省钱方法论为主，避免无关内容。

## 开发环境

```bash
git clone https://github.com/<你的用户名>/maimai-saver.git
cd maimai-saver

# 运行时零依赖（Python 3.9+ 标准库），仅测试需要 pytest
pip install -r requirements-dev.txt
python -m pytest tests/ -v          # 当前 89 个用例

# 语法检查（与 CI 一致，覆盖全部 5 个脚本）
python -m py_compile scripts/mcd_client.py scripts/mcd.py \
    scripts/deal_compare.py scripts/optimizer.py scripts/silent_cost.py
```

代码约定：

- 运行时**仅使用 Python 标准库**（这是徽章里 "Dependencies: None" 的承诺）；
- Python 3.9+ 兼容（CI 矩阵 3.9 / 3.11 / 3.13）；
- 错误处理遵循现有风格：401 快速失败、429 指数退避尊重 `Retry-After`、
  工具层错误抛 `McpToolError`；
- 不引入新的网络端点，所有请求走官方 MCP Server（`mcp.mcd.cn`）。

## 提交 PR 流程

1. Fork 仓库并从 `main` 拉出功能分支（如 `feat/min-protein`）；
2. 小步提交，commit message 用中文或英文均可，讲清楚"为什么"；
3. 确保测试与语法检查全绿，新增功能**必须附带测试**；
4. 关联对应 Issue（`Closes #123`）。

## 提交自检清单

- [ ] `python -m pytest tests/` 全部通过；
- [ ] 语法检查覆盖所有改动脚本；
- [ ] 未包含任何真实 Token、密码或个人凭证；
- [ ] 涉及工具目录/工作流的变更已同步 `references/` 与 `SKILL.md`；
- [ ] **README.md 与 README_EN.md 同步更新**（章节、命令、目录树、徽章数字）；
- [ ] 用户可见变更已写入 `CHANGELOG.md`（遵循 Keep a Changelog 格式）；
- [ ] `docs/demo.html` 有改动时已用浏览器验证（或至少 `node --check` 校验内联 JS）。

## 发布流程

版本号遵循项目自定义 `z.x.y` 规则（修订号 ≤3、次版本号 ≤6，超限进位），
一次完整发布包含五步，缺一不可。逐项同步点（含历史漏项与手动项）见
[`docs/sync-checklist.md`](docs/sync-checklist.md)——提交前照表打勾：

```bash
python scripts/version.py                    # 1. 预览下一版本号
python scripts/version.py --apply            # 2. 写回 CLIENT_INFO / pyproject / SKILL / README 徽章与「当前版本」
# 3. 补 CHANGELOG 条目、推送、打 tag 并创建同名 Release（gh release create）
python scripts/build_releases.py --current --upload   # 4. 生成两个产物并挂到同名 Release（幂等，可重复执行）
python scripts/build_releases.py --verify             # 5. 校验命名、配对、压缩包完整性与 SHA-256
```

产物命名固定，不接受自定义：

| 类型 | 命名 | 形式 |
|---|---|---|
| 英文名 | `mcd-saver-v<版本>.zip` | 压缩包（tag 源码，解压根目录 `McD-Saver-v<版本>/`） |
| 中文名 | `麦麦省钱助手-v<版本>-发布说明.md` | 说明文档（含安装、变更与 SHA-256） |

`tests/test_consistency.py` 会校验版本号、测试计数、配置示例、`releases/` 产物与索引的一致性——
CI 变红时优先看它，而不是怀疑业务代码。

## 合规红线（不可协商）

以下内容无论以何种形式提交都会被拒绝：

- 爬取美团/抖音等平台数据（比价数据只走手动录入或 `MAIMAI_DEALS_PROVIDER` 插件）；
- 自动下单、无人值守定时领券、绕过交互确认的任何自动化；
- 刷 Star、多账号、机器人等操纵排名的行为。

## 许可

提交即表示你同意贡献内容以 [MIT](LICENSE) 许可证随本项目发布。
