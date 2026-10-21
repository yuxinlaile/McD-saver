# 安全策略（Security Policy）

本项目会接触 MCP Token 与订单信息，安全问题按以下流程处理。

## 支持范围

只维护**最新发布版本**（见 [Releases](https://github.com/yuxinlaile/McD-saver/releases)）。
历史版本不再单独修复，请升级到最新版。

## 报告方式

**不要通过公开 Issue / Discussion 报告安全问题。**

请使用 GitHub 的私密通道：
仓库首页 **Security** → **Report a vulnerability**
（即 <https://github.com/yuxinlaile/McD-saver/security/advisories/new>）

报告中请包含：

- 受影响的版本或 commit；
- 复现步骤（命令、输入、环境）；
- 影响判断（Token 泄露 / 越权 / 数据外泄 / 拒绝服务）；
- 如可能，给出修复建议。

**请勿附带真实 Token、手机号、订单号或地址**；需要示例时用占位符替换。

## 处理时限

| 阶段 | 目标 |
|---|---|
| 确认收到 | 48 小时内 |
| 初步评估 | 5 个工作日内 |
| 修复与披露 | 视严重程度协商，修复后同步 CHANGELOG 并致谢（如你同意署名） |

## 重点关注的问题类型

- Token 读取、存储或日志中的泄露（含 CI 输出、异常堆栈、示例文件）；
- 请求构造导致的注入或 SSRF；
- 越权访问他人订单 / 地址；
- 依赖与构建链风险（本项目运行时零第三方依赖，风险面主要在测试依赖）；
- 文档中诱导用户关闭安全校验的表述。

## 已知边界（非漏洞）

- 项目不提供自动下单、自动支付能力，也不存储用户凭证；
- 所有价格与库存以麦当劳官方接口返回为准，估算偏差不属于安全问题；
- 第三方团购券数据由用户手动录入，其真实性由用户自行判断；
- **外部数据源插件会执行本机代码**：用 `deal_compare.py --provider <模块路径>`
  指向一个 `.py` 文件后，比价引擎会用 `exec_module()` **执行该文件的全部代码**
  （插件机制的固有代价，类似 `pip install` 运行安装脚本）。它默认关闭、不读环境变量
  （避免环境残留导致外部代码被静默执行），且加载前必定在终端打印风险警告。
  只应指向你自己写的、或来源明确可信的模块；工具不校验模块签名。
- 金额单位随接口不同：菜单价是「元」，`calculate-price` 返回「分」，
  仓库在解析层统一折算，并用本地估算交叉校验（见 `references/mcp-pitfalls.md` 第 3 条）。

---

**English summary**: This project handles MCP tokens and order data. Please report
security issues privately via GitHub Security Advisories
(<https://github.com/yuxinlaile/McD-saver/security/advisories/new>) — never in public
issues. We aim to acknowledge within 48 hours. Do not include real tokens, phone
numbers, or order IDs in reports.
