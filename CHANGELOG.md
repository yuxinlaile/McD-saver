# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，
版本号遵循项目自定义 `z.x.y` 规则（修订号 ≤3、次版本号 ≤6，超限进位），由 `scripts/version.py` 递增并同步发布文件。

## [2.3.2] - 2026-10-21

Star 曲线改为仓库内自绘，参与贡献段落重写。

### 改进

- **Star 曲线改为自绘**：新增 `scripts/gen_star_chart.py`，从 GitHub API 的打星时间渲染
  `docs/assets/star-history.svg`（纯标准库，无第三方依赖），README 的 Star History 段落改用该本地图，
  不再依赖第三方 star-history.com 的服务端缓存。随时可用 `python scripts/gen_star_chart.py` 重算。
- **参与贡献段落重写**（中英各一处）：改为三类可直接上手的方向（工作流与文档 / 中英校对 / 测试与算例），
  每项给出具体入口与命令，并保留提交前自查清单。

### 质量

- 300 → 309 项测试全过（新增 9 项：按天累计序列、SVG 渲染、仓库内图表资产与 README 引用守卫）

## [2.3.1] - 2026-10-21

README 精简与同步守卫。

### 改进

- **「近期版本」区块改为自动生成**：新增 `scripts/sync_readme.py`，从 CHANGELOG 提取最近 3 个版本的
  要点写入 README 中英的 `<!-- release-highlights -->` 标记区，发版时由 `scripts/version.py --apply`
  自动刷新；区块长度固定 3 行，不再随发版增长。
- **移除 README 中的内部流程说明**：「发布产物与版本策略 / Release artifacts」整节删除（中英各一处），
  相关内容保留在 `releases/README.md` 与 `CONTRIBUTING.md`。
- **新增 README 同步守卫**（`tests/test_readme_sync.py`，10 项）：近期版本区块与 CHANGELOG 一致、
  环境变量表与代码双向互校、`SKILL.md` 目录树中的路径真实存在、README 与 `references/tools.md`
  工具集合一致、全部 Markdown 相对链接可达、试算页示例数据条数与 README 表述一致。
- `references/tools.md` 的「主题活动」表统一为三列格式（原为带序号的四列表格），使工具清单可被自动比对。

### 质量

- 290 → 300 项测试全过

## [2.3.0] - 2026-10-21

品牌统一与徽章调整。

### 改进

- **包名 / 技能名 / 客户端标识统一为 `mcd-saver`**：包名（`pyproject.toml`）、技能名
  （`SKILL.md` frontmatter）、`mcd_client.CLIENT_INFO` 与 `USER_AGENT`、各平台安装路径示例
  （`references/agent-skill-installation.md`）、试算页导出图文件名、报告页脚。
- **数据目录与券库环境变量统一**：数据目录 `~/.mcd_saver`；环境变量 `MCD_DEALS_FILE`、
  `MCD_DATA_DIR`。旧名 `MAIMAI_DEALS_FILE` / `MAIMAI_DATA_DIR` 仍然生效，优先级低于新名。
- **README 顶部新增实时 Stars 徽章**（shields.io，每次读取为真值）；Star History 曲线由
  star-history.com 服务端缓存生成、数据存在滞后，图表下方已注明。
- 新增 `tests/test_brand_rename.py`（7 项）：身份字段用新名、新旧环境变量优先级、旧名扫描守卫。

### 清理

- 移除内部出图脚本与产物（分享卡图片不入库，投放素材不随源码分发）。

## [2.2.3] - 2026-10-21

真实 Token 实测打通带券核价，收紧 Token 外发边界，并修正 Agensi 链接。

### 修复

- **带券核价打通**（此前券从未真正生效；用真实 Token 实测定位）：
  - 券必须**同时**给出 `couponId` 与 `couponCode`，且挂在 `items[].productCode` 对应条目上
    （只给其一 → 服务端 code 600010「使用优惠券需要couponId和couponCode」；
    挂在顶层 → 返回成功但**券被静默忽略**，价格不变）；
  - 实测：麦咖啡™冰美式中杯 无券 ¥11.90 → 用券 **¥9.90**（与券面价一致）；
  - 券的结构化字段只在 MCP 响应的 `structuredContent` 里（`id`/`code`/`tradeEndDateTime`/
    `discountInfo.discountValue`），文本 content 是给人看的 Markdown 表格、不含这些字段；
    `tool_json()` 与 `_unwrap()` 改为**优先读 structuredContent**（并支持 `data.coupons` 一层嵌套）。
- **Token 外发边界收紧**：非官方 MCP 地址默认被拒绝（`--url` / `MCD_MCP_URL`），
  需显式 `--allow-non-official-url` 才会放行并打印告警；官方地址 `mcp.mcd.cn` 放行。
  此前一次误配置即可把 Bearer Token 发往任意主机。
- `deal_compare clear --yes` 只允许作用于本工具创建的券库（含 id 的券记录数组），
  否则拒绝执行并说明原因——避免路径写错把任意 JSON 覆写成空数组；确认时打印绝对路径。

### 新增

- `optimizer plan` 新增 `--be-code` / `--need-tableware` / `--with-order`：
  外送与得来速场景必须带 beCode，餐具与随单购不再写死默认值。
- 外送场景实测结论写入 `references/mcp-pitfalls.md`：同一门店到店菜单 99 项、外送仅 60 项，
  商品编码也不同——用错菜单会得到「商品已售罄或不可售」。

### 文档

- Agensi 链接修正为 `https://www.agensi.io/skills/mcd-saver-mcdonald-s-china-order-savings-check`
  （README 中英各一处，原链接指向错误的创作者页）；
- README 的语言切换链接前置：中文版首行以 [English] 开头，英文版以 [简体中文] 开头。

### 质量

- 267 → 283 项测试全过（新增 16 项：地址白名单、带券契约、结构化载荷优先、clear 保护）

## [2.2.2] - 2026-10-21

核验材料合并、外部数据源入口改造、试算页真实菜单导入修复。

### 改进

- **核验材料合并为单一文档**：`workbuddy.md` 并入原 `docs/development-log.md` 的首轮六阶段记录，
  重复表述合并、章节按「环境与赛事背景 → 首轮对话决策 → 阶段产出与验证 → 版本里程碑 →
  真实环境复验与巡检 → 核验入口」重新组织；`docs/development-log.md` 已删除，
  仓库内统一以 `workbuddy.md` 为 WorkBuddy 专项核验入口（文件名保持赛事要求不变）
- **外部数据源入口改造**：`MAIMAI_DEALS_PROVIDER` 环境变量 → `deal_compare.py --provider <模块路径>`
  显式参数。环境变量属于「环境态开关」，容易被遗忘或被无关进程继承，导致外部代码被静默执行；
  改为显式参数后，每次执行都必须主动声明。该 `.py` 仍会在本机执行，执行前必定打印风险提示；
  旧环境变量若仍被设置会打印一次迁移提示（不再生效），不会让人误以为它还在工作
- **试算页真实菜单导入修复**：页面的解包函数此前只认整段 JSON 文本，遇官方
  「Markdown 字段说明 + `## Original Response` 之后的真实 JSON」形态解析失败，
  真实菜单导入**恒为 0 项**；现改为花括号配对扫描 + 识别 `categories`/`meals` 双层结构 +
  价格字符串归一，实测可从官方真实响应摊平出 **99 个在售餐品**

### 修复

- `references/agent-skill-installation.md` 删除「WorkBuddy 是麦当劳程序员创意开发大赛的官方合作伙伴」
  这一失实表述（与 README 免责声明直接矛盾），改为如实说明开发环境与核验入口
- `workbuddy.md` 中的本机绝对路径改为 `~` 形式，避免公开仓库暴露本机用户名

### 质量

- 265 → 267 项测试全过（新增 2 项：旧环境变量不再触发外部代码执行、CLI `--provider` 链路打通）
- 文档一致性：README 中英逐位对应（20 标题 / 19 链接）+ 目录顺序 == 正文顺序

## [2.2.1] - 2026-10-20

本版把「真实计价」这条主链路修到可用，并用真实门店数据重做了分享卡；另附一次全仓巡检的整改（24 条）。

### 新增

- **一键分享卡（真实核价版）**：卡片改为数据驱动（外部可注入 `window.MCD_CARD`），
  版式重排为大字钩子 + 三行明细 + 可领券 + 核价门店 + CTA + 底栏，
  可直接渲染官方 `calculate-price` 实时核价的真实结果
  （同店两种买法：直点 ¥50.50 → 官方套餐 ¥37.50，省 ¥13.00 / 26%）。
  卡片是**试算页的运行时导出功能**，图片文件不入库（投放用素材留在仓库外），
  README 首屏不再内嵌某一张门店快照。
- **`mcd_client.tool_json(result)`**：统一从 tools/call 结果里提取 JSON 载荷
  （官方返回常是「Markdown 字段说明 + `## Original Response` 之后的真实 JSON」，
  且 JSON 之后可能还跟着展示说明文字），取不到时返回 None，绝不臆测。
- **回归测试 254 → 265**：新增 `tests/test_real_pricing.py`（11 项）与
  `tests/test_regressions.py`（8 项）。

### 修复

- **真实计价模式此前在真实环境下完全不可用**（用真实 Token 实测定位到三个根因）：
  - 请求体字段应为 `items`（原为 `products`），且必填 `beType` / `needTableware` / `withOrder`；
  - 金额字段是 `price`（原只找 payable / payAmount / total 等，永远取不到值）；
  - **金额单位是「分」**——`query-meals` 的 `currentPrice` 是元（"26.5"），
    而 `calculate-price` 的 `price` 是分（¥50.50 → 5050），不换算会放大 100 倍。
    现统一按分折算为元，并以同一购物车的本地估算做交叉校验，防止上游改单位。
- **全仓巡检整改 24 条**（三项 P0 全部修复）：
  - `verify_run.py` 传 `date` 而非 `datetime` → 真实账户必崩；积分余额键名修正；
  - `silent_cost._unwrap` 不支持 `{"data":{"list":[...]}}` → 真实响应被静默丢成空列表；
    content 壳里的中文空态文案不再被当成一条记录；`report` 缺文件改为中文错误 + 退出码；
  - 另修：`savings_grade` 重复定义、模块导入兜底、`check` 地址回显脱敏、错误体截断、
    `list_tools` 兜底、菜单缺 `mealCode` 兜底、`compare_deals` 改抛 `ValueError`、
    `clear` 未确认改用退出码 1、试算页 Token 改走环境变量并加字符白名单校验。

### 文档

- **README 中英正文顺序对齐**，并新增「目录顺序 == 正文顺序」CI 守卫
  （此前只校验章节存在性与数量，顺序漂移测不出来）。
- `references/mcp-pitfalls.md` 第 3 条按实测更正（此前声称「已在读取金额处统一 ÷100」，
  实际并不成立），并补充 `## Original Response` 包裹的解析说明。
- `docs/development-log.md` 更正两处失准表述（「72 分钟完成全部开发」与旧仓库地址）。
- `SECURITY.md` 与 README 补充 `MAIMAI_DEALS_PROVIDER` 风险说明：
  该 `.py` 文件会被本机执行，仅应在完全信任时设置。
- 其余事实性偏差一并修正：CHANGELOG 的 SemVer 声明、`docs/index.html` 与
  `MCP_INTEGRATION.md` 的测试计数、examples 算例与脚本真实输出的冒号与路径、
  `install.ps1` 补拷 `docs/` 与 `LICENSE`、`SKILL.md` 目录树补 `SECURITY.md`，
  并移除一次性快照图片（分享卡图片不入库）。

## [2.2.0] - 2026-10-19

本版不发新功能，把"结论可复现"这件事补齐：测试、覆盖率、文档一致性守卫，
以及两个会静默出错的缺陷。

### 改进

- **测试与覆盖率**：171 → 245 项测试，`scripts/` 覆盖率 62% → 76%。新增
  HTTP 客户端（SSE / JSON 双解码、会话头、401/429/5xx 重试、网络异常）与
  CLI 命令层（`check` / `tools` / `schema` / `call` / `claim` 退出码）用例；
  CI 覆盖率门槛保持 70%，为波动预留 5pp 空间
- **文档一致性进入 CI**：新增 `scripts/check_toc.py`，校验 README 中英目录锚点
  与章节覆盖（20 个标题逐位对应）；版本号 5 处、测试计数 4 处由测试断言，
  文档漂移在 CI 阶段失败，而不是发版后才发现
- **更新同步清单**：新增 `docs/sync-checklist.md`（内部流程材料，2026-10-20 起已移出公开仓库，
  自动检查项由 `scripts/check_toc.py` 与 `tests/test_consistency.py` 承担），记录 6 类历史漏项、
  自动检查项与发版前手动项，把"靠记性"换成"照表打勾"
- **版本工具**：`--apply` 收尾提示补全构建、上传、校验三条命令，并新增 2 项
  测试锁定退出码与输出

### 修复

- **JSON-RPC `error` 响应被误判为"无结果"**：`mcd_client` 此前对含 `error`
  的响应抛出 `TransportError` 并丢失错误码，导致工具错误无法定位；现交由
  调用方按 `error` 处理，错误信息与错误码可正常返回
- **`version.py --apply` 结尾抛 `NameError`**：变量名笔误使版本已写回但脚本
  非零退出，自动化流程会误判为失败；已修复并补测试

## [2.1.3] - 2026-10-19

### 改进

- **在线试算页四维约束支持直接输入数值**：预算 / 热量 / 蛋白质 / 钠四条滑杆
  旁新增数值输入框，与滑杆双向联动——可键入精确值（支持小数、也可超出滑杆
  原量程），留空或 0 表示不限，非法输入标红且不生效，失焦自动归一化；
  约束变更后若已有计算结果会即时重算，无需再点计算按钮
- **移动端数值框触控优化**：输入框高度 40px、滑杆占满整行，单手操作更稳
- **修复窄屏卡片右侧被裁切**：菜单网格轨道改用 `minmax(0, 1fr)`，375px 视口下
  卡片宽度回归容器宽度（实测 343px、内部零溢出），桌面双列布局不受影响

## [2.1.2] - 2026-10-19

### 新功能

- **在线试算页四维约束滑杆**：预算 / 热量上限 / 蛋白质下限 / 钠上限四条滑杆，
  31 项示例菜单全部补充营养数据（示例值，真实数据以官方 nutrition 接口为准）；
  违规方案排后并标注差多少（与 CLI 同一语义，绝不静默剔除）
- **真实运行验证记录**：新增 `scripts/verify_run.py` 一键生成脱敏验证记录写入
  `examples/verified-run.md`——真实 Token 环境实测：35 工具连通、完整调用链跑通，
  Token 与手机号自动排除

### 改进

- **CI 覆盖率门槛**：pytest-cov 接入，`--cov-fail-under=55`（当前 64%）
- **Token 文件权限检查**：Unix 上 `~/.mcd_mcp_token` 权限过宽时提示 chmod 600
- **代码拆分**：HTML 渲染与省钱等级抽离为 `silent_report.py`（silent_cost 保持
  向后兼容再导出）
- 版本工具补 pyproject.toml 同步（此前为覆盖盲区）

### 修复

- pyproject.toml 版本号长期滞后（1.6.0 → 2.1.1）已修正并纳入自动同步
## [2.1.1] - 2026-10-19

### 改进

- **真实计价两阶段优化**：`--mcp` 模式先用本地估算排序预筛 Top-K（默认 8），
  仅对前 K 个方案走官方 calculate-price——典型调用次数降低 60%+，端到端延迟
  随之下降；报告标注预筛信息（「本地估算预筛 Top-8，共 N 个候选」），
  `--mcp-top-k 0` 可恢复全量核价。新增 `prefilter_plans()` 与 3 项测试

### 说明

- 估算与真实计价价格同源，Top-K 外方案真实价翻转概率低；对绝对严谨场景
  保留全量核价开关

## [2.1.0] - 2026-10-19

### 新功能

- **主动滑动窗口限速**（`scripts/mcd_client.py`）：
  默认 300 次/分钟（官方上限 600 的一半），批量比对场景不再触发 429 被动等待；
  `rate_limit=0` 可禁用。新增 4 项测试（禁用/窗口满等待/窗口未满/滑出）
- **方案排名场景标签**（经济 / 均衡 / 丰盛）：
  Top-N 方案自动标注「最经济 / 均衡 / 最丰盛」，排名可读性提升

### 文档

- README 新增 **dependencies stdlib-only 徽章** 与搜索关键词区
- Pages 根路径新增索引页（原根路径 404，现自动进入在线试算）

## [2.0.3] - 2026-10-15

### 新功能

- **官方最优方案自动衔接团购终局建议**（feasibility 早期提案落地）：
  `optimizer plan` / `demo` 输出后，若本地券库（MAIMAI_DEALS_FILE 或
  默认路径）非空，自动以「无券直点=原价口径、最优实付=官方基准」调用
  deal_compare 同口径折算，输出「官方最优 vs 团购最优」结论与适用限制——
  用户无需再手动跑两个工具；`--no-deals` 可关闭
  - 新增 `cross_channel_section()` 与 5 项测试（团购更低/官方更优/
    空券库/无券库/零基线）
  - 团购比价为全赛道独有功能（已验证 10 个竞品均未实现）

## [2.0.2] - 2026-10-15

### 改进

- **在线试算页移动端文案与结果可达性优化**：
  - Token 卡片标题与说明按平台适配——移动端显示「手机版 · 两种方式，
    无需电脑」专属标题，桌面命令生成的说明文字不再出现在手机上
  - 新增**悬浮计算按钮**（🧮，56px 圆形，贴屏幕右缘不遮挡勾选）：
    移动端任意位置点击即计算并平滑滚动到结果区
  - 优化结果卡恢复至页面底部（撤销此前的置顶方案）
- 双视口实测：375px（悬浮按钮显示、桌面文案隐藏、无横向滚动）与
  1366px（桌面流程不变）全部通过

## [2.0.1] - 2026-10-15

### 新功能

- **在线试算页移动端导入路径**（客户以手机使用为主，手机无终端无法执行命令）：
  - 移动端显示专属引导——两条无需电脑的导入路径：已安装 AI Agent 的
    「说一句导入真实菜单 → 复制输出 → 粘贴回页」；以及
    **menu.json 文件选择导入**（新增文件按钮，FileReader 本地读取）
  - 桌面命令生成流程保留（窄屏自动隐藏，桌面自动显示），互不干扰
- 该功能经 375px 移动视口与 1366px 桌面视口双端实测：文件导入成功、
  无横向溢出、团购列表渲染正常

## [2.0.0] - 2026-10-15

### 新功能

- **版本号自动递增工具**（`scripts/version.py`）：实现本项目自定义
  z.x.y 版本格式与递增规则——修订号 y 上限 3、次版本号 x 上限 6，
  每次发布先递增 y，y 超限进位到 x 并重置，x 超限进位到 z 并将 x、y
  重置（示例：1.5.3 → 1.6.0，1.6.3 → 2.0.0，历史过渡版本 1.7.4 → 2.0.0）
  - CLI：自动读取仓库当前版本（单一事实源 CLIENT_INFO）输出下一版本；
    `--apply` 一键写回发布四件套（CLIENT_INFO / SKILL.md / README×2 徽章）
  - 边界处理：0.0.0 起步递增、超限分量归一化进位、非法输入
    （非数字/段数错误/负数/空串）抛出明确错误
  - 单元测试 32 项：规则表、进位链、边界与非法输入全覆盖
- **版本格式切换说明**：自本版本起采用 z.x.y 自定义格式，
  v1.7.4 之后进入 2.0.0

## [1.7.4] - 2026-10-15

### 改进

- **在线试算页移动端优化**（客户以手机使用为主）：
  - 触控：按钮最小高度 44px，移动端卡片间距压缩（18px → 14px）
  - 表单：输入类字号统一 16px，规避 iOS Safari 聚焦时的页面强制缩放
  - 布局：Token 卡两输入框窄屏纵向堆叠，消除 375px 宽度下的横向滚动；
    优化结果卡在移动端置顶（order:-1），选完餐品即见结果
  - 视觉：新增 theme-color，移动浏览器地址栏与页面配色一致
- 桌面端布局与字号不受影响（全部改动限定在 ≤640px 媒体查询内，回归验证通过）

## [1.7.3] - 2026-10-15

### 新功能

- **在线试算页「🔑 导入你的真实菜单」卡片置顶**：输入 MCP Token 一键生成
  现成命令（Windows / macOS-Linux 双版本，内嵌 `--token`，无需预设环境变量），
  复制到本地终端执行后把输出粘贴回页面，即可用实时全量菜单跑同一套优化算法。
  Token 仅在浏览器内存中拼接命令，不上传任何服务器（浏览器直连 MCP 受
  CORS 限制，此为实测后最安全便捷的路径）
- **团购示例扩充 6 → 11 条**：新增板烧鸡腿堡中套餐券、早餐组合两件套券、
  抖音巨无霸中套餐单次券、满 30 减 8 代金券、双层吉士中套餐单次券，
  覆盖套餐单次券 / 满减代金券 / 双人餐 / 随心配 / 甜品 / 早餐六类

### 文档

- CHANGELOG 历史条目措辞规范化，开发过程记录统一归档至 `docs/`

## [1.7.2] - 2026-10-15

### 改进

- **用券排程升级为净价值模型**（净价值 = 券面价值 − max(0, 满减门槛 −
  自然消费基准)）：门槛远超客单价的满减券判定为
  「纸面富贵」并建议放弃，不再计入可实现金额——修正了此前
  按面值排程导致的系统性高估
- 排程建议展示从「面值」改为「净价值」，超出客单价的门槛部分如实说明

### 修复

- **客单价口径修正**：0 元订单（券核销/积分兑换）此前被计入客单价分母，
  会系统性拉低「自然消费基准」——现改为消费口径（客单价剔除 0 元单）
  与点单口径（频率含全部订单）分离，并新增 `free_order_count` 字段
  与报告披露（消费口径与点单口径分离）

## [1.7.1] - 2026-10-15

### 新功能

- **省钱等级**：HTML 体检报告新增确定性分档（S/A/B/C/D，按排程可实现金额
  ≥30/≥15/≥5/≥1 划分），附一句话说明——报告更适合截图分享

### 文档

- MCP 踩坑指南新增**参数自动串联**技巧：上游响应中的 storeCode / orderId /
  spuId / couponId 可直接喂给下游工具，无需人工查文档即可跑通全部只读工具
  （实测 27/28 只读工具跑通，写操作按需跳过）

## [1.7.0] - 2026-10-14

### 新功能

- **点餐替换建议**：当最优方案仍超出热量或钠上限时，按「热量代价从小到大」
  逐项给出替换选项（如 中可乐 → 无糖可乐），表达喜爱的单品最后才动，
  每处替换说明营养变化
- **口味记忆**：去酸黄瓜、可乐去冰等个人偏好只需说明一次，会话内自动
  记忆并写入后续点餐的特调参数

### 改进

- 点餐工作流（SKILL.md）与上述两项行为对齐，Agent 在营养约束触发时
  主动给出替换路线而非仅提示超限
- 在线试算页文案表述规范化

### 文档

- 新增 **MCP 实战踩坑指南**（`references/mcp-pitfalls.md`）：响应格式、
  金额单位、券字段多态、菜单时效性等 8 条实测经验，帮助接入者少走弯路
- README 新增**「能力现状」**披露：已验证 / 待真实环境复核 / 已知限制，
  一张表说明项目成熟度
- README 明确**订单安全边界**：用户确认前不创建订单，创建订单不等于支付成功
- 全仓库文案与目录整理：开发过程记录归档至 `docs/`，移除未使用的示意图资源
- 品牌定稿：英文展示名 **McD Saver**、中文展示名「麦麦省钱助手」，仓库更名 `McD-saver`（包名 `maimai-saver` 不变）

## [1.6.0] - 2026-10-14

### Added
- **用券排程**（silent_cost）：临期券过期窗口 × 历史点单频率 →
  把券按面值降序排入窗口内预期点单次数，一次算清
  「名义面值 → 可实现 → 注定过期」——券不是越多越好，用得上才算数
- **券面值实测**（silent_cost `--probe`）：无面值字段/标题无金额的券，
  券商品码 + couponId 传官方 calculate-price 实测精确价值——
  实测优先、估算兜底、失败如实标注（与社区同类工具的实测口径对齐）
- **单文件 HTML 报告**（silent_cost `--html`）：零 CDN、零脚本、
  双击打开即可截图分享的「体检长图」，卡号类敏感字段不输出
- **30 秒离线全链路演示**（根目录 `demo.py` + `fixtures/`）：
  与真实 MCP 响应同格式的数据快照，原样跑通四步检查全链路——
  **demo 即回归测试**（tests/test_demo_pipeline.py 断言其输出）
- **真实性资产**：真实运行输出渲染的终端截图入 README（标注日期与「未美化」）、
  「还可以这样问」指令映射表、mermaid 全渠道架构图、README 差异化对比表
- **examples/verified-run.md**：真实 Token 运行验证记录的留档模板与流程
- pyproject.toml：包元数据与 pytest 配置（`pip install .` 可用，运行时仍零依赖）

### Testing
- 单元测试 98 → 113（用券排程 / 券面值实测 / HTML 报告 / demo 全链路回归）

## [1.5.0] - 2026-10-13

### Added
- optimizer.py：**营养约束**——`--min-protein`（蛋白质下限，g）与
  `--max-sodium`（钠上限，mg），配合菜单条目的 `protein`/`sodium` 字段
  （来自 list-nutrition-foods）生效；违规方案排后并如实标注
  「蛋白质不足 xx g / 超钠 xx mg」；**营养数据缺失的方案按不满足处理**
  并标注「蛋白质未知」——延续"算不出如实披露"原则，绝不虚构达标。
  健身增肌与控盐人群场景
- demo.html 页脚增加 GitHub Star 引导链接
- 单元测试 89 → 98（新增营养约束用例：达标不打标 / 不足排后 /
  数据缺失保守处理 / 组合约束排序 / 报告文案）

## [1.4.2] - 2026-10-12

### Added
- demo.html 试算页大幅扩充：31 项菜单（7 大类，含早餐段）、9 张券、
  6 单美团/抖音团购示例（费率计价）、跨渠道终局建议区块、分享按钮
- demo.html 新增**导入真实菜单**：粘贴 MCP `query-meals` 原始输出即可全量
  替换示例数据（宽容字段解析 + 逐条校验），作为官方菜单全量同步的合规路径
- 新增 GitHub Issue 模板（bug 反馈 / 功能建议 / 引导讨论区）

## [1.4.1] - 2026-10-12

### Added
- `mcd.py` 新增 `claim` 子命令：列出麦麦省可领券（available-coupons）→
  展示清单 → 交互确认（y/N，`--yes` 供脚本场景）→ auto-bind-coupons 一键领取。
  安全边界：用户主动触发、单次执行；**明确不提供定时轮询与无人值守后台**
  （此类自动化有 Token 风控封禁风险，与 SKILL.md「下单必确认」规范一致）
- 单元测试 84 → 89（claim 流程用例：直接领取/确认领取/取消/空清单/大小写）

## [1.4.0] - 2026-10-12

### Added
- optimizer.py：**多约束支持**——`--budget` 实付预算上限与 `--max-kcal` 热量上限
  （菜单含 kcal 字段时生效），违反约束的方案排后并标注"超预算/超热量 xx"，
  不静默删除；**套餐替换枚举**——套餐含 `contains` 字段覆盖全部想吃单品时
  自动生成"改点套餐"候选，是否更省交给计价排名判断
- silent_cost.py：**积分影子价格**——`--mall` 传入积分商城商品列表后，
  按 max(面值÷积分) 估算最优兑换效率并给出可用积分折现值
  （统一成本口径）
- 单元测试 75 → 89（新增约束/套餐替换/影子价格用例）

### Changed
- SKILL.md 工作流 5 补充约束参数说明；README 中英运行与命令同步

## [1.3.0] - 2026-10-12

### Added
- 券组合优化器 `scripts/optimizer.py`：确定性枚举「无券直点 / 单券 /
  凑单达标」候选方案，输出最优组合与 Top-N 备选；计价可插拔——估算模式
  （本地价格表）或 `--mcp` 真实计价模式（官方 calculate-price 逐方案核价）；
  凑单方案强制标注"仅当你本来就需要该商品才划算"，并以"不凑单"为基准排序
- 沉默成本体检 `scripts/silent_cost.py`：临期券扫描（7 天内到期按面值合计）+
  消费画像（订单数/总支出/客单价/高频复购单品）+ 积分体检（可用与即将过期），
  字段宽容匹配、识别不到明确标注"未识别"
- GitHub Pages 在线试算器 `docs/demo.html`：optimizer 算法前端复刻 + 内嵌示例
  数据，免登录免 Token 开箱即验；界面采用双栏卡片式布局（桌面端左选右算、
  移动端自适应），整卡点选 + 数量步进器，凑单陷阱独立警示样式，支持一键重置
- `install.ps1`：Windows 一键安装脚本（备份旧版本，不触碰 Token 与连接器）
- 预览图 `docs/assets/optimizer-report.svg`；单元测试 49 → 84（新增优化器与
  体检模块用例）
- README（中英）头部新增在线试算与 Release 徽章

### Changed
- SKILL.md：工具地图与标准工作流新增"最优组合点单"与"沉默成本体检"两条
  工作流；版本号升至 1.3.0
- README（中英）：核心功能、运行与命令、目录结构、效果预览同步更新

## [1.2.1] - 2026-10-10

### Added
- `requirements-dev.txt`：声明开发与测试依赖（pytest）；CI 改为安装该文件
- 单元测试新增：SSE 流 CRLF 换行兼容用例、重试退避计算边界用例

### Changed
- `mcd_client.py` 内部重构（公开接口与行为完全兼容）：提取 `_jsonrpc()` 消除
  initialize/tools/list/tools/call 三处的重复消息构造；提取 `_compute_backoff()`
  与 `_parse_retry_after()` 统一 429/5xx/网络错误的退避计算；`import sys` 归位模块顶部
- `_parse_sse()` 增加 CRLF/CR 换行归一化，兼容不同服务器的 SSE 帧分隔风格
- `deal_compare.py`：券有效期徽标逻辑收敛为 `_validity_badge()`，消除两处重复

### Fixed
- 修正 `McdMcpClient` docstring 中默认地址的笔误（mcd.mcd.cn -> mcp.mcd.cn）
- 清理 `mcd_client.py` 未使用的 `Union` 类型导入

## [1.2.0] - 2026-10-10

### Added
- 单元测试套件 `tests/`（43 个用例）：SSE 解析、Token 三通道解析、客户端
  请求头与响应解码、比价折算/排序/有效期判定、provider 数据源接口、
  CLI 退出码与全流程冒烟；CI 增加 pytest 步骤
- `deal_compare.py` 数据源 provider 接口：通过环境变量
  `MAIMAI_DEALS_PROVIDER` 指定外部数据源模块（需实现 `load_deals()`），
  为团购平台未来开放官方 API 预留自动化接入点，失败自动回退本地券库
- 英文说明文档 `README_EN.md`、版本变更记录 `CHANGELOG.md`
- 各主流 Agent 安装指南 `references/agent-skill-installation.md`
  （WorkBuddy / Claude Code / Cursor / OpenAI Codex，基于开放 Agent Skills 标准）
- README 效果预览：横幅与比价报告图（`docs/assets/*.svg`）
- GitHub Issue 模板（Bug 报告 / 功能建议）与 PR 模板（含自检清单）

### Changed
- 仓库内容整理：新增开发过程记录文件（大赛专项奖励核验材料，现位于 `docs/development-log.md`）
  （敏感凭证脱敏）；README 移除悬空链接；MCP 配置示例的 Token 占位符
  统一为 `${MCD_MCP_TOKEN}` 环境变量形式；CI 语法检查纳入 `deal_compare.py`

## [1.1.0] - 2026-10-10

### Added
- 技能定位重构为"麦麦省钱助手"（maimai-saver）：省钱顾问方法论——
  下单前省钱四步检查（领券→选券→双价比价→积分抵扣评估），
  "先查后改 / 下单必确认 / 不虚构优惠"调用规范
- 全渠道比价引擎 `scripts/deal_compare.py`：美团/抖音等团购券手动录入
  本地券库，与官方渠道（MCP calculate-price）同口径估算比价并输出推荐
- 相关文档：`references/money-saving-strategies.md`（十一大策略）、
  `references/group-buy-comparison.md`（比价方法论）
- 大赛参赛文件：`CONTEST_DECLARATION.md`、`MCP_INTEGRATION.md`、
  `mcp-config.example.json`、`workbuddy.md`

### Changed
- 工具目录按实测校准为 35 个（新增 `query-survey-coupon`、`query-promotions`）

## [1.0.0] - 2026-10-10

### Added
- 首个版本：基于麦当劳中国官方 MCP Server（https://mcp.mcd.cn，
  Streamable HTTP）的技能包
- 纯标准库 MCP 客户端：完整 JSON-RPC 生命周期、Mcp-Session-Id 会话保持、
  JSON/SSE 双格式响应解析；401 快速失败、429 指数退避 + 抖动重试
  （尊重 Retry-After）、5xx/网络错误自动重试
- CLI（check / tools / schema / call），结构化退出码 0/1/2/3/4
- Agent Skill 入口 `SKILL.md` 与 references 文档（工具目录、工作流、
  错误排查）、GitHub Actions CI、MIT LICENSE（含第三方条款声明）
