# WorkBuddy 开发上下文（workbuddy.md）

> 本文件记录「麦麦省钱助手（McD Saver）」使用腾讯 WorkBuddy 开发过程中的关键对话与决策，
> 用于核验本项目符合麦当劳程序员创意开发大赛 WorkBuddy 专项奖励的联动条件。
> 内容仅描述开发过程与技术决策；对话中出现的 MCP Token、手机号、订单等敏感凭证
> 已按《参赛声明》的信息安全要求脱敏，本文件不含任何真实凭证。
>
> **合并说明（2026-10-21）**：原 `docs/development-log.md`（首轮六阶段记录）已并入本文件，
> 重复表述已合并、章节重新组织；原文件已删除，仓库内统一以本文件为 WorkBuddy 专项核验入口。

## 一、开发环境与赛事背景

| 项 | 内容 |
|---|---|
| 开发工具 | 腾讯 WorkBuddy（智能体） |
| 工作目录 | `~/Documents/WorkBuddy/<工作区>/mcd-saver`（本机绝对路径，提交前已脱敏） |
| 运行时 | Python 3.9+，纯标准库、零第三方依赖；前端为单文件 `docs/demo.html`（无 CDN、无构建） |
| MCP 依赖 | 麦当劳中国官方 MCP Server（`https://mcp.mcd.cn`，Streamable HTTP，Bearer Token 鉴权，限流 600 次/分钟/Token，错误码 401/429） |
| 赛事 | 麦当劳程序员创意开发大赛（报名 Issue #275） |
| 参赛必备文件 | `README.md` / `CONTEST_DECLARATION.md` / `MCP_INTEGRATION.md` / `mcp-config.example.json` / 本文件 |

## 二、首轮开发对话（2026-10-10 14:28—15:40，北京时间）

首轮在 72 分钟内完成从需求理解到首版可运行的 Skill；此后在 WorkBuddy 中持续迭代至
2026-10-20（累计 220+ 次提交、265 项单元测试、23 个发布版本）。本章记录**决策与理由**，
各阶段的产出与验证证据见第三章。

### 2.1 摸清赛事规则与 MCP 能力边界

- 拉取官方 `activityGuidelines.md` 与 MCP 工具清单，整理必交文件：
  `README.md` / `CONTEST_DECLARATION.md` / `MCP_INTEGRATION.md` / `mcp-config.example.json`；
  `workbuddy.md` 为 WorkBuddy 专项加分所需的过程上下文。
- 实测官方 MCP 返回体特性并据此设计解析层：tool 返回为 Markdown 文本
  （真实 JSON 在 `## Original Response` 之后）、营养数据为逗号分隔文本表格、
  空数据返回中文文案而非空数组——解析器对三种形态都有兜底。
- 工具清单以服务器实测为准：实际返回 **35 个工具**，较上游文档多出
  `query-survey-coupon` 与 `query-promotions`，全部文档据实同步。

### 2.2 确定方向与架构

- 选题理由：优惠券组合是「用户懒得算、大模型算不准」的典型场景，
  价格必须由确定性代码计算，不能交给模型口算。
- 架构决策：**取数交给 MCP，算术交给代码，表达交给 Agent**。
- 客户端实现要点：MCP Streamable HTTP 生命周期与会话保持、401 快速失败不重试、
  429 指数退避并尊重 `Retry-After`、Token 三通道解析（环境变量 / 文件 / 参数）且绝不写入日志。

### 2.3 省钱方法论成型

- 「省钱四步检查」：领券 → 门店选券 → 无券/带券双价对比 → 积分抵扣评估，
  每笔优惠金额必须来自官方工具实际返回值，不虚构。
- 券组合优化器：确定性枚举「无券直点 / 单券 / 凑单达标 / 改点套餐」候选并逐方案计价，
  叠加预算、热量、蛋白、钠四维约束；违规方案排后并标注差多少，数据缺失按不满足处理。
- 反凑单设计：以「不凑单」为基准，主动提示凑单陷阱——为用券多买常常反而更贵。

### 2.4 差异化：全渠道比价与沉默成本

- 只算官方券不够——用户囤的美团/抖音团购券也是钱。新增全渠道比价引擎：
  团购券手动录入（平台无公开 API，不做爬虫），与官方价同口径折算，输出终局建议。
- 「券越多越省钱」是错的。新增沉默成本体检：临期券扫描 + 用券排程
  （过期窗口 × 点单频率 →「可实现 vs 注定过期」）+ 消费画像 + 积分影子价格。
- 无面值券不猜价格：券码 + couponId 传 `calculate-price` 实测，失败如实标注。

### 2.5 可传播性与工程化

- 在线试算页（`docs/demo.html`）：纯前端免登录，支持一键导入真实菜单；
  试算完成可导出 1080×1350 分享卡（Canvas 绘制，零第三方依赖）。
- 质量门禁：单元测试、demo 全链路输出即回归测试、CI 三版本矩阵 + 覆盖率门槛 70%、
  README 中英目录锚点校验、版本号五处与测试计数四处一致性断言。
- 范围边界正面表述：聚焦下单前的省钱决策，不含自动下单与无人值守定时领券；
  订单创建需用户明确确认，支付始终在麦当劳官方页面完成。

## 三、首轮六阶段的产出与验证

### 阶段 1：上游能力分析

上游 `M-China/mcd-mcp-server` 为纯文档仓库，实际能力由麦当劳中国远程托管的 MCP Server 提供；
接入方式、鉴权、限流与错误码见第一章。整理出的工具清单与版本日志成为 Skill 的能力地图依据。

### 阶段 2：Skill v1.0 开发

产出 `scripts/mcd_client.py`（仅依赖标准库的 MCP 客户端）、`scripts/mcd.py`
（CLI：check / tools / schema / call，退出码 0/1/2/3/4）、`SKILL.md` 与 references 参考文档、
GitHub Actions CI、MIT LICENSE。

验证：`py_compile` 通过；无 Token 场景优雅退出（退出码 2，含修复指引）。

### 阶段 3：真实环境端到端验证

作者在对话中提供其本人 MCP Token（此处已脱敏）用于实测：

- `check`：连接成功，服务器 `mcd-mcp v1.0.0`；
- `tools`：服务器实际返回 35 个工具（见 2.1），全部文档据实同步；
- `call now-time-info`：tools/call 链路返回真实服务器时间；
- `schema query-nearby-stores`：入参 Schema 完整返回（beType 枚举等）。

### 阶段 4：定位重构为「省钱助手」（v1.1.0）

项目更名为 `maimai-saver`，SKILL.md 重写为省钱顾问方法论（省钱四步检查、下单必确认、
不虚构优惠等调用规范）；新增 `references/money-saving-strategies.md`（省钱策略库）；
实测 `query-my-account` 返回真实积分数据（可用 / 累计 / 过期积分）。

### 阶段 5：全渠道比价升级

用户需求：结合美团、抖音等团购平台的优惠信息进行比价与省钱推荐。

技术决策：团购平台无面向第三方的公开 API，故采用「手动录入 + 本地券库」的诚实设计；
数据层另提供**显式可选**的外部数据源入口（`deal_compare.py --provider`，
详见 `references/group-buy-comparison.md`），为将来平台开放官方 API 时预留，不做爬虫。

产出 `scripts/deal_compare.py`（add / list / remove / clear / compare）与
`references/group-buy-comparison.md`（录入字段映射、折算口径、比价五原则、决策规则与合规免责）。
功能实测：录入两张券后 compare 正确输出折扣率排序与推荐决策。

### 阶段 6：参赛准备与发布

- 按大赛官方要求补齐 `CONTEST_DECLARATION.md`（官方原文）、`MCP_INTEGRATION.md`、
  `mcp-config.example.json`（仅环境变量占位符）与本文件；
- 提交前经 Token 泄漏扫描（本地与远程仓库内容均不含真实凭证）；
- 通过 gh CLI 将项目发布至公开仓库 `github.com/yuxinlaile/McD-saver`
  （仓库后由 `maimai-saver` 改名为 `McD-saver`，旧名仍自动重定向），
  并向活动仓库提交参赛 Issue #275。

## 四、版本里程碑

| 版本 | 内容 |
|---|---|
| v1.0–v1.1 | MCP 客户端与省钱四步检查（2026-10-10） |
| v1.2–v1.7 | 券组合优化器、四维约束、沉默成本体检、积分影子价格（10-10 至 10-15） |
| v1.7.1–v1.7.4 | 省钱等级（S/A/B/C/D）、口味记忆、菜单缓存、移动端适配 |
| v2.0–v2.2 | Agent Skill 标准化、在线试算页与分享卡、文档一致性 CI（10-15 至 10-19） |
| v2.2.1 | 真实计价链路修复（请求字段 / 金额键 / 分元单位）、全仓巡检整改 24 条、分享卡数据驱动（10-20） |
| v2.2.2 | 核验文档合并（`workbuddy.md` ← `docs/development-log.md`）、外部数据源入口改造、试算页真实菜单导入修复（10-21） |
| v2.2.3 | 带券核价打通（两个 id + 挂商品条目）、Token 外发白名单、Agensi 链接修正（10-21） |
| v2.3.0 | 品牌统一（包名/技能名/安装路径/数据目录/环境变量旧名退役）、Star History 滞后说明 + 实时星数徽章（10-21） |

## 五、2026-10-20 的真实环境复验与全仓巡检

在 WorkBuddy 中用作者的真实 Token 复验整条链路，发现并修复三个此前未暴露的根因
（真实计价模式在真实环境下**完全不可用**，输出「无可行方案」）：

1. `calculate-price` 的请求体字段是 `items`（此前写的是 `products`），且必填
   `beType` / `needTableware` / `withOrder`；
2. 金额字段是 `price`（此前只找 payable / payAmount / total，永远取不到值）；
3. **金额单位不统一**：菜单价是「元」（`"26.5"`），而 `calculate-price` 的 `price` 是「分」
   （¥50.50 的订单返回 `5050`）——不换算会把实付金额放大 100 倍。

同时完成一次全仓巡检整改 24 条（三项 P0 全部修复：日期类型传错导致真实账户必崩、
`_unwrap` 不支持嵌套响应形态导致真实数据被静默丢成空列表、`report` 缺文件抛裸 traceback），
并新增「目录顺序 == 正文顺序」的中英一致性守卫；测试 245 → 265 项全绿。

2026-10-21 再次用真实 Token 复验：发现**带券核价此前从未真正生效**——券必须同时给出
`couponId` 与 `couponCode` 并挂在商品条目上（只给其一被服务端拒收；挂在顶层则券被静默忽略），
且券的结构化字段只在 MCP 响应的 `structuredContent` 里。修正后实测：
麦咖啡™冰美式中杯无券 ¥11.90 → 用券 **¥9.90**（与券面价一致）。同轮还确认了外送场景的
参数链（`delivery-query-addresses` → `delivery-query-stores` → `query-meals`/`calculate-price`
需带 `beCode`），以及外送菜单与到店菜单不同（60 项 vs 99 项）。

## 六、核验入口

- 阶段过程记录与版本里程碑：本文件第二、三、四章
- MCP 实际使用清单：`MCP_INTEGRATION.md`
- 离线可复现算例：`examples/three-ways.md`（一单三种买法）、`examples/silent-cost-example.md`（沉默成本体检读法）
- 完整变更历史：`CHANGELOG.md`
