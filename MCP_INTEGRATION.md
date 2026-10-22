# MCP 集成说明（MCP_INTEGRATION）

本文件说明"麦麦省钱助手"如何真实、完整地使用麦当劳官方 MCP 能力。

## 1. 使用的 MCP Server

| 项目 | 内容 |
|---|---|
| Server | 麦当劳中国官方 MCP Server |
| 地址 | `https://mcp.mcd.cn`（远程托管，Streamable HTTP 传输） |
| 鉴权 | `Authorization: Bearer ${MCD_MCP_TOKEN}`（Token 经环境变量注入，不落盘、不入库） |
| 配置示例 | 见仓库根目录 `mcp-config.example.json` 与 `config/mcp.example.json` |

## 2. 使用的 Tool 全景（35 个）

### 2.1 省钱决策类（本技能核心）

| Tool | 在技能中的角色 |
|---|---|
| `available-coupons` | 省钱第 1 步：查询麦麦省当前可领取的优惠券列表 |
| `auto-bind-coupons` | 省钱第 1 步：经用户确认后一键领取全部可领券 |
| `query-my-coupons` | 省钱第 2 步：查用户卡包全部券资产 |
| `query-store-coupons` | 省钱第 2 步：按门店 + 订单类型筛选当前订单可用券 |
| `calculate-price` | 省钱第 3 步：无券/带券双价试算，产出省钱明细（原价/优惠/实付） |
| `query-my-account` | 省钱第 4 步：积分余额与即将过期积分（临期主动提醒） |
| `mall-points-products` / `mall-product-detail` | 省钱第 4 步：检索积分兑换餐品券，与现金方案对比 |
| `query-promotions` | 团餐场景满减/满折促销规则 |
| `now-time-info` | 对齐服务器时间，判断活动/券有效期 |
| `campaign-calendar` | 当月营销活动日历，融入省钱建议 |
| `query-lottery-info` / `draw-lottery` / `query-my-prizes` | 积分抽奖：免费次数提醒（零成本机会）、经确认后抽奖 |

### 2.2 点餐执行类

| Tool | 在技能中的角色 |
|---|---|
| `query-nearby-stores` | 到店场景：按位置/收藏查门店（beType 区分自提/得来速） |
| `delivery-query-addresses` / `delivery-create-address` | 外送场景：地址管理 |
| `delivery-query-stores` | 外送场景：地址可配送门店 |
| `query-meals` / `query-meal-detail` | 菜单与套餐组成、可替换项（零成本替换建议） |
| `list-nutrition-foods` | 营养维度选品（热量/成分约束下的搭配） |
| `query-meal-assistance` | 团餐助餐服务 |
| `create-order` | 下单（经用户完整确认后），返回支付链接 |
| `query-order` / `cancel-order` / `order-list` | 订单跟踪 / 经确认取消 / 历史订单 |
| `query-survey-coupon` | 满意度答卷关联奖券核销状态回收 |
| `mall-create-order` / `mall-order-list` / `mall-order-detail` | 积分兑换下单与商城订单 |
| `query-party-city` → `query-party-store` → `query-partystore-date` → `query-partystore-session` → `party-order-create` | 主题活动五级级联查询与预约 |

### 2.3 非麦当劳 MCP 模块（明确声明）

`scripts/deal_compare.py`（外部团购比价引擎）**不调用任何麦当劳 MCP 工具以外的
第三方接口**：美团/抖音等平台无公开 API，团购数据由用户手动录入本地券库，
比价输出为估算参考。详见 `references/group-buy-comparison.md`。

## 3. 核心调用流程

### 省钱四步检查（任何下单前强制执行）

```
[1] 领券   available-coupons →（用户确认）auto-bind-coupons
[2] 选券   query-store-coupons（storeCode + orderType）⨯ query-my-coupons
[3] 比价   calculate-price（无券）⇄ calculate-price（最优券组合）
           → 输出省钱明细：原价 / 优惠 / 实付 / 节省比例
[4] 积分   query-my-account（临期积分提醒）→ mall-points-products 对比
[5] 可选   deal_compare.py compare —— 结合用户录入的团购券做全渠道估算比价
```

### 省钱版点餐主流程（外送示例）

```
delivery-query-addresses（无地址则 delivery-create-address）
→ delivery-query-stores
→ query-meals → query-meal-detail（零成本替换项）
→ [省钱四步检查 + 可选团购比价]
→ calculate-price（双价对比，展示省钱明细）
→（用户明确确认）create-order → 支付链接原样转交用户
→ query-order 跟踪
```

### 工程实现

- `scripts/mcd_client.py`：纯标准库 MCP Streamable HTTP 客户端，实现
  `initialize` / `tools/list` / `tools/call` 完整生命周期、`Mcp-Session-Id`
  会话保持、`application/json` 与 `text/event-stream` 双格式响应解析；
  401 快速失败、429 指数退避 + 抖动重试（尊重 `Retry-After`）、5xx/网络错误重试。
- `scripts/mcd.py`：CLI（check / tools / schema / call），结构化退出码（0/1/2/3/4）。
- `tests/`：328 个 pytest 单元测试（SSE 解析、Token 解析、比价决策、券组合优化、
  沉默成本、claim 领券流程、CLI 退出码），
  CI 在每次 push / PR 时自动执行。

## 4. 业务价值

1. **直接省钱**：官方券资产（可领/已领/门店可用）被系统性利用，
   下单前双价对比确保每一单都拿到当前可得的最优官方价格。
2. **积分不沉睡**：临期积分主动提醒；积分兑换与现金方案自动对比；
   抽奖免费次数零成本提醒。
3. **全渠道决策**：结合用户录入的团购券做全渠道估算比价，
   帮用户在"官方渠道 vs 团购"间做出内容可比、限制透明的购买决策。
4. **安全可控**：先查后改、下单必确认、支付链接仅转交不代付、
   优惠金额必须来自工具实际返回值（不虚构优惠）。
