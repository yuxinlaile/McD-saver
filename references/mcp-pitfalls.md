# 麦当劳 MCP 实战踩坑记录

> 来源：本仓库开发与测试过程中实际遇到并已在代码中处理的问题，
> 以及社区公开分享的实测发现（致谢 mcd-wrapped 的 MCP 能力探测器报告）。
> 逐条给出「现象 → 原因 → 本仓库的处理位置」，供后续接入者少走弯路。

## 1. 响应体不一定是纯 JSON

**现象**：`tools/call` 的响应可能是 `application/json`，也可能是
`text/event-stream`（SSE 帧），且 SSE 帧的 `data:` 行内可能再包一层 Markdown。

**处理**：`scripts/mcd_client.py` 同时解析两种 Content-Type；SSE 场景取末个
`data:` 事件再 `json.loads`。`silent_cost.py` 的 `_unwrap()` 额外对
`{"content":[{"type":"text","text":"..."}]}` 标准壳做宽容解包，并对
`## Original Response` 包裹的 Markdown 取其后的真实 JSON 再解析；
空数据中文文案会被识别为空列表，不会被当成一条记录。

## 2. 空数据返回中文文案，不是空数组

**现象**：无数据时返回 `{"data": "暂无可用优惠券"}` 之类的中文提示字符串，
而不是 `{"data": []}`。

**处理**：所有 `data` 字段解析前先判断类型——字符串一律视为「无数据」，
绝不当列表遍历（见 `_unwrap()`）。判断依据是字段类型而非是否为真值。

## 3. calculate-price 的金额单位需实测确认（本仓库按「元」处理）

**现象**：社区实测反馈 `calculate-price` 可能返回 `"price": 2500` 这样的分单位数值。

**处理（重要）**：本仓库**不做分/元自动换算**——`optimizer.py` / `silent_cost.py`
按响应原值参与计算，报告层以元展示。**首次接入真实账户时必须用一次真实核价确认
单位**（例如菜单价 ¥25.00，对比返回的是 25 还是 2500）：若确为分单位，需在解析层
统一 ÷100，否则实付金额会放大 100 倍。跨工具对账前务必先统一单位。

## 4. 券的字段命名高度多态

**现象**：面值可能叫 `parValue` / `faceValue` / `worth` / `discountValue`，
有效期可能叫 `validityEndTime` / `validUntil` / `expireTime`……

**处理**：`silent_cost.py` 用 `FACE_KEYS` / `EXPIRE_KEYS` 等常量数组做
宽容匹配 + 标题正则兜底（「减 X 元」「X 元」）；全部未命中标注
「面值未识别」，配合 `--probe` 走 calculate-price 实测。

## 5. 菜单快照有时效性

**现象**：夜间快照里没有早餐/部分小食单品，用券匹配会「找不到对应商品」——
这不是解析失败，是数据事实。

**处理**：价值无法推算的券如实标注「无法判断」，不为 demo 好看而造数据；
需要精确价值时领取后用「带券计价」实测。

## 6. 会话必须保持：Mcp-Session-Id

**现象**：initialize 返回的 `Mcp-Session-Id` 丢失会导致后续 tools/call 404/401。

**处理**：`mcd_client.py` 在会话内持久化该 Header，所有请求复用；
`check` 命令即验证「initialize → tools/list」完整生命周期。

## 7. 限流与错误语义

- 限流：600 次/分钟/Token；429 时服务器返回 `Retry-After`，必须尊重
- 401 鉴权失败：重试无意义，快速失败引导重新申请 Token
- 5xx / 网络错误：指数退避 + 随机抖动重试（默认 3 次）

**处理**：`mcd_client.py` 统一实现；CLI 退出码区分 `1/2/3/4` 四类失败，
脚本可按码分支处理。

## 8. 参数自动串联：从已有响应里找下一个工具的入参

手动逐个查工具参数很痛苦。实测规律：**上游响应里就藏着下游工具需要的参数**：

- `order-list` 返回的 `storeCode` → 喂给 `query-meals` / `calculate-price`
- `order-list` 返回的 `orderId` → 喂给 `query-order`
- 积分商城列表返回的 `spuId` → 喂给 `mall-product-detail`
- `query-my-coupons` 返回的 `couponId`（及券自带商品码）→ 喂给 calculate-price 实测券价值

把「提取 → 串联 → 调用」写成循环，35 个只读工具无需人工查文档即可全部跑通
（社区探测器实测 27 个成功、7 个写操作按需跳过、1 个缺可选参数——致谢
mcd-wrapped 的 MCP 能力探测器报告）。

## 9. 工具数量与文档不一致

官方文档口径 33 个工具，服务端实际暴露 **35 个**（以 `tools/list` 实时
返回为准）。本仓库 README 的工具总览基于实测，勿按文档硬编码工具清单。

---

> 以上每一条在本仓库都有对应测试或代码位置；发现新的坑欢迎
> 提 Issue / PR 补充，让后来者少踩一次。
