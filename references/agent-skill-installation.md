# 各平台 Agent Skill 安装指南

本技能遵循开放的 [Agent Skills 标准](https://agentskills.io)（SKILL.md 格式），
同一份仓库可以在 WorkBuddy、Claude Code、Cursor、OpenAI Codex 等主流
Agent 中直接安装使用，无需修改任何文件。

> 无论哪个平台，技能本体只负责"方法论"；实际工具调用依赖麦当劳官方
> MCP Server。安装技能后，请同时按 `config/mcp.example.json` 配置
> `mcd-mcp` MCP 连接（Token 用环境变量注入），技能才能执行真实查询与下单。

## 安装速查表

| 平台 | 项目级（仅当前仓库） | 用户级（本机全局） | 显式调用方式 |
|---|---|---|---|
| WorkBuddy | 项目 `.workbuddy/skills/` | `~/.workbuddy/skills/` | 对话中提及麦当劳相关需求自动触发 |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` | `/maimai-saver` 或按描述自动触发 |
| Cursor | `.cursor/skills/` 或 `.agents/skills/` | `~/.cursor/skills/` 或 `~/.agents/skills/` | `/maimai-saver` 或按描述自动匹配 |
| OpenAI Codex | `.agents/skills/` | `~/.agents/skills/` | `$maimai-saver`、`/skills` 选择器或自动匹配 |

安装到任意一个标准目录后重启/新开会话即可被识别。Cursor 与 Codex 还会
交叉兼容读取彼此及 Claude 的技能目录（`.claude/skills/`、`.codex/skills/`）。

## 通用安装命令（项目级，团队共享推荐）

```bash
# 在你的项目仓库根目录执行
git clone https://github.com/yuxinlaile/McD-saver.git /tmp/maimai-saver

# Claude Code
mkdir -p .claude/skills && cp -R /tmp/maimai-saver .claude/skills/maimai-saver

# Cursor（或使用 .agents/skills/，效果相同）
mkdir -p .cursor/skills && cp -R /tmp/maimai-saver .cursor/skills/maimai-saver

# OpenAI Codex
mkdir -p .agents/skills && cp -R /tmp/maimai-saver .agents/skills/maimai-saver
```

用户级全局安装则把目标路径换为各平台表格中的全局目录（如
`~/.claude/skills/maimai-saver`）。

> 注意：目标目录中直接包含 `SKILL.md` 的那层文件夹名必须为 `maimai-saver`，
> 不要多套一层目录，否则 Agent 无法识别。

## WorkBuddy

1. 克隆本仓库到 `~/.workbuddy/skills/maimai-saver`（用户级，所有会话可用）
2. 在 WorkBuddy【连接器】中按 `config/mcp.example.json` 配置并启用 `mcd-mcp`
3. 对话中说"帮我用最划算的方式点麦当劳"即可自动触发

本次开发全程在腾讯 WorkBuddy 智能体对话环境中完成，仓库根目录的 `workbuddy.md`
记录了开发对话上下文、阶段产出与版本里程碑，可用于大赛 WorkBuddy 专项的核验。

## Claude Code

```bash
git clone https://github.com/yuxinlaile/McD-saver.git ~/.claude/skills/maimai-saver
```

- 新开会话后，技能按 frontmatter `description` 自动触发；
- 显式调用：输入 `/maimai-saver`；
- MCP 配置写入 `~/.claude.json` 或项目 `.mcp.json`（内容同
  `config/mcp.example.json`）。

## Cursor

```bash
git clone https://github.com/yuxinlaile/McD-saver.git .cursor/skills/maimai-saver
# 团队共享可选 .agents/skills/（开放标准目录）；全局安装用 ~/.cursor/skills/
```

- 在 Agent 对话中输入 `/maimai-saver` 显式调用，或让 Agent 依据描述自动匹配；
- 可在 Cursor 设置 → Rules 中确认技能已被识别；
- MCP 配置写入 `.cursor/mcp.json`（内容同 `config/mcp.example.json`）。

## OpenAI Codex

```bash
git clone https://github.com/yuxinlaile/McD-saver.git .agents/skills/maimai-saver
# 全局安装用 ~/.agents/skills/maimai-saver
```

- 输入 `$maimai-saver` 显式调用，或 `/skills` 浏览可用技能；
- 描述匹配时 Codex 也会自动激活技能；
- MCP 配置写入 `~/.codex/config.toml` 的 `[mcp_servers.mcd-mcp]` 段
  （地址与请求头同 `config/mcp.example.json`）。

## 验证安装

1. 新开一个 Agent 会话，输入显式调用命令（见速查表）确认技能被识别；
2. 执行 `python scripts/mcd.py check` 验证 MCP Token 与连通性（方式 B）；
3. 问一句"麦当劳现在有什么优惠"——Agent 应按 SKILL.md 的省钱四步检查
   流程先查询 `available-coupons` 等工具，而不是直接回答。

## 安全提示

- 安装任何第三方技能前，先阅读其 `SKILL.md` 与 `scripts/` 内容；
- 本技能的 Token 一律通过环境变量/文件注入，任何对话与日志中都不应出现
  真实凭证；若发现技能要求你提交明文凭证，请立即停止使用。
