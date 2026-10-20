# WorkBuddy 对话上下文（开发过程记录）

本项目（麦麦省钱助手 MaiMai Saver）由作者于 2026 年 10 月 10 日
14:28 — 15:40（北京时间）在腾讯 WorkBuddy 智能体对话环境中完成**首轮设计**，
此后在 WorkBuddy 中持续迭代至 2026-10-20（累计 220 次提交、254 项单元测试、
22 个发布版本）。本文件为**首轮开发对话**的上下文要点记录，按实际时间顺序整理，
用于麦当劳程序员创意开发大赛 WorkBuddy 专项奖励核验；各版本的阶段细节见
`workbuddy.md` 的版本里程碑表与仓库 `CHANGELOG.md`。

> 说明：本记录为对话上下文的要点整理版；对话中出现的 MCP Token 等敏感凭证
> 已按《参赛声明》信息安全要求脱敏，以下不包含任何真实凭证。

> **状态：已冻结（2026-10-19）。** 本文件作为赛事核验材料保留阶段 1–6 的既有记录，
> 不再追加新内容；后续开发不再写入本文件。

## 阶段 1：上游能力分析

用户需求：基于麦当劳官方 MCP Server 集成指南仓库（M-China/mcd-mcp-server）
开发一个可开源的 Skill。

对话中通过 GitHub API 分析上游仓库并确认：

- 上游为纯文档仓库，实际能力由麦当劳中国远程托管的 MCP Server 提供；
- 接入方式：`https://mcp.mcd.cn`，Streamable HTTP 传输，Bearer Token 鉴权
  （open.mcd.cn/mcp 申请），限流 600 次/分钟/Token，错误码 401/429；
- 整理出工具清单与版本日志，作为 Skill 的能力地图依据。

## 阶段 2：Skill v1.0 开发

在对话中完成设计与代码生成：

- `scripts/mcd_client.py`：仅依赖 Python 标准库的 MCP Streamable HTTP 客户端，
  实现 initialize / tools/list / tools/call 完整生命周期、Mcp-Session-Id 会话
  保持、application/json 与 text/event-stream 双格式响应解析；
- 错误处理：401 快速失败不重试、429 指数退避 + 随机抖动并尊重 Retry-After、
  5xx/网络错误自动重试、工具层错误结构化为 McpToolError；
- `scripts/mcd.py`：CLI（check / tools / schema / call），退出码 0/1/2/3/4；
- `SKILL.md` 及 references 参考文档、GitHub Actions CI、MIT LICENSE。

验证：py_compile 通过；无 Token 场景优雅退出（退出码 2，含修复指引）。

## 阶段 3：真实环境端到端验证

作者在对话中提供其本人 MCP Token（此处已脱敏）用于实测：

- `check`：连接成功，服务器 mcd-mcp；
- `tools`：服务器实际返回 **35 个工具**，较上游文档（33 个）多出
  `query-survey-coupon` 与 `query-promotions`，全部文档据实同步；
- `call now-time-info`：tools/call 链路返回真实服务器时间；
- `schema query-nearby-stores`：入参 Schema 完整返回（beType 枚举等）。

## 阶段 4：定位重构为"省钱助手"（v1.1.0）

用户需求：将技能设计为"麦麦省钱助手"。对话中完成：

- 项目更名为 `maimai-saver`，SKILL.md 重写为省钱顾问方法论：
  省钱四步检查（领券→选券→双价比价→积分抵扣评估）、下单必确认、
  不虚构优惠等调用规范；
- 新增 `references/money-saving-strategies.md`（省钱策略库）；
- 实测 `query-my-account` 返回真实积分数据（可用/累计/过期积分）。

## 阶段 5：全渠道比价升级

用户需求：结合美团、抖音等团购平台的优惠信息进行比价与省钱推荐。
对话中的技术决策：团购平台无面向第三方的公开 API，故采用"手动录入 +
本地券库"的诚实设计，数据层预留自动化接入接口。

- 新增 `scripts/deal_compare.py`：券录入/管理与比价引擎，
  子命令 add / list / remove / clear / compare；
- 新增 `references/group-buy-comparison.md`：录入字段映射、折算口径、
  比价五原则、决策规则与合规免责；
- 功能实测：录入两张券后 compare 正确输出折扣率排序与推荐决策。

## 阶段 6：参赛准备与发布

- 按大赛官方要求（M-China/mcd-developer-innovation-challenge）补齐
  `CONTEST_DECLARATION.md`（官方原文）、`MCP_INTEGRATION.md`、
  `mcp-config.example.json`（仅环境变量占位符）与本文件；
- 提交前经 Token 泄漏扫描（本地与远程仓库内容均不含真实凭证）；
- 通过 gh CLI 将项目发布至公开仓库 github.com/yuxinlaile/McD-saver
  （仓库后由 `maimai-saver` 改名为 `McD-saver`，旧名仍自动重定向），
  并向活动仓库提交参赛 Issue。
