# 更新同步清单（Update Sync Checklist）

> 本清单来自 2026-10-19 全仓审计：当时查出 **6 处「改了正文、漏了配套」** 的问题。
> 从此每次更新（功能、文档、品牌、发版）都按下表逐项过一遍；能在 CI 里守住的已写成断言，
> 剩下的人工项在发版前必须逐条确认。

## 一、本次审计发现的漏项（教训存档）

| # | 漏掉的位置 | 具体表现 | 根因 | 现在的守护方式 |
|---|---|---|---|---|
| 1 | `CHANGELOG.md` | 2.1.2 条目**重复两段**（内容完全相同） | 多轮编辑叠加，没有唯一性校验 | `test_consistency.py::TestChangelog` 断言无重复版本、版本降序 |
| 2 | `SKILL.md` 目录树 | 缺 9 个已存在文件（`silent_report.py`、`version.py`、`verify_run.py`、`build_releases.py`、`mcp-pitfalls.md`、`agent-skill-installation.md`、`demo.html`、`index.html`、`releases/`） | 新增文件时只改代码，没回写目录树 | `test_skill_tree_lists_every_script` + 文档与站点文件断言 |
| 3 | `README.md` 目录（TOC） | 正文有「反馈与支持」，**目录里没有**该条目 | 新增章节只补了正文与英文 TOC | `scripts/check_toc.py` 断言「每个章节都在目录里」 |
| 4 | 测试计数（4 处） | README 中英徽章与正文、`banner.svg`、`SKILL.md` 多次不同步（122/154/171 混用） | 计数散落 4 处，纯靠人工 | `test_counts_are_equal_everywhere` 断言四处一致 |
| 5 | `pyproject.toml` 版本 | 长期停留在 `1.6.0`，与 `CLIENT_INFO` 脱节 | `version.py --apply` 覆盖盲区 | `--apply` 已补 pyproject，并加 `test_pyproject_matches_client_info` |
| 6 | `releases/` 产物 | 此前没有任何产物；GitHub Release 也全部没有附件，且 v1.7.3 只有 tag 没有 Release | 无构建脚本，靠手工打包且未上传 | `scripts/build_releases.py --verify` + 产物一致性测试 |

## 二、自动项（CI 会红，无需人肉记忆）

| 检查点 | 落点 | 守护 |
|---|---|---|
| 版本号一致 | `scripts/mcd_client.py`（CLIENT_INFO）、`pyproject.toml`、`SKILL.md` frontmatter、`README.md`/`README_EN.md` 的 Release 徽章与「当前版本」句 | `tests/test_consistency.py` |
| 测试计数一致 | `README.md` 徽章 + 正文、`README_EN.md` 徽章 + 正文、`docs/assets/banner.svg`、`SKILL.md` 目录树 | 同上 |
| CHANGELOG 结构 | 无重复版本、按版本降序、顶部版本 = 当前版本 | 同上 |
| 目录完整 | 每个章节都出现在 TOC，TOC 无死链，中英章节逐位对应 | `scripts/check_toc.py`（CI 与本地共用） |
| 目录树完整 | `scripts/*.py`、`references/*.md`、站点文件都出现在 `SKILL.md` 目录树 | `tests/test_consistency.py` |
| 配置示例一致 | 根 `mcp-config.example.json` ≡ `config/mcp.example.json`，且只含 `${MCD_MCP_TOKEN}` 占位符 | 同上 |
| 发布产物 | `releases/v<版本>/` 恰好两件产物、命名固定、索引覆盖；说明中的 SHA-256 与 zip 一致 | `tests/test_consistency.py` + `build_releases.py --verify` |

本地一条命令跑完全部自动项：

```bash
python -m pytest tests/ -q
python scripts/check_toc.py
python scripts/build_releases.py --verify
```

## 三、手动项（发版前逐条确认）

| # | 落点 | 什么时候要改 | 怎么做 |
|---|---|---|---|
| 1 | Issue #275 版本进展 | **每次发版** | 按既有「## 📦 版本进展（当前 vX.Y.Z）」格式发评论，含要点、渠道、测试数；对外措辞零内部痕迹 |
| 2 | GitHub Release 资产 | **每次发版** | `python scripts/build_releases.py --current --upload`（英文 zip + 中文说明别名） |
| 3 | Agensi listing | **功能有变更的发版** | 重新打包并手动上传，标题保持 `McD Saver — McDonald's China Order Savings Check` |
| 4 | `docs/assets/banner.svg` | 品牌 / 测试数变更 | 文本与数字同步（测试数自动项会校验，但 SVG 内品牌文案需人工确认） |
| 5 | `social-preview.png` | 品牌 / banner 变更 | 用 headless Chrome 重新渲染 banner 后，手动上传仓库 Settings → Social preview |
| 6 | 仓库 About | 品牌 / 定位变更 | description 含能力清单，homepage 指向在线试算页 |
| 7 | `docs/development-log.md` | 新的开发阶段 | 追加记录（参赛核验材料，只增不删） |

## 四、按变更类型的最短路径

**功能 / 修 bug**
1. 改代码 + 补测试 → 2. `version.py --apply` → 3. 同步测试计数（四处）→ 4. 写 CHANGELOG →
5. `build_releases.py --current --upload` → 6. 打 tag、建 Release → 7. #275 评论。

**纯文档 / 教程**
1. 改文档 → 2. `check_toc.py`（锚点与章节覆盖）→ 3. 若新增章节，登记 `scripts/check_toc.py` 的 `PAIRS` →
4. 若新增文件，回写 `SKILL.md` 目录树与 README 项目结构 → 5. 一般不单独发版，随下次发版带走。

**品牌（名称 / 视觉）**
1. 文本落点：README 中英、`SKILL.md`、`CHANGELOG`、`docs/demo.html`、`config/`、`references/`；
2. 视觉落点：`docs/assets/banner.svg`、`social-preview.png`；
3. 外部落点：仓库 About、Issue #275 公告、Agensi listing 标题；
4. 收尾：全仓 grep 旧名（豁免 `docs/development-log.md` 历史记录）。

## 五、为什么这些位置容易漏

- **同一事实有多份副本**：版本号 5 处、测试数 4 处、配置示例 2 份——人脑记不住，必须靠断言。
- **新增文件不回写清单**：目录树、README 项目结构、`releases/` 索引都属于「元数据」，最容易漏。
- **正文与导航分离**：TOC 是独立维护的列表，新增章节必须同时加导航（本次就是这样漏的）。
- **产物与源码分离**：zip 是构建产物，改完源码忘了重建/重传，Release 里就是旧包。

因此原则是：**能自动断言的就不要靠记性；不能自动的，写进这张表，发版前照表打勾。**

## 六、对外表述规范（2026-10-19 修订）

**适用范围仅限「更新说明类」文件；功能展示与功能介绍不受此限制。**

| 范围 | 具体文件 / 位置 | 要求 |
|---|---|---|
| **受约束**（更新说明类） | `CHANGELOG.md`、`releases/v*/麦麦省钱助手-*-发布说明.md`、GitHub Release 说明、#275 版本进展评论 | 不出现「借鉴 / 参考 / 致谢 / 灵感」及「参考了 X」「思路来自 X」等来源表述；只陈述做了什么、口径是什么、结果如何 |
| **不受约束**（功能展示 / 介绍） | `README.md` / `README_EN.md`、`SKILL.md`、`references/*`、`docs/demo.html`、仓库 About、Agensi 文案 | 可按事实描述来源、引用或致谢；要求准确、不夸大，不强制中性化 |
| **豁免** | `docs/development-log.md`（历史记录）、`CONTEST_DECLARATION.md`（官方原文）、本规则文档 | 保持原样，不参与扫描 |

**执行要点**

- 更新说明中，技术事实（公式、阈值、行为）必须原样保留，只去掉来源表述；
- 版本号、测试数、产物命名等硬信息不得因改写而变化；
- 自动守卫 `tests/test_consistency.py::TestNeutralWording` **只扫描更新说明类文件**，功能文档出现来源表述不会触发 CI；
- 新增更新说明类文件时，需同步加入守卫的扫描列表。

## 七、仓库边界：哪些内容不进公开仓库（2026-10-19 新增）

公开仓库只放**用户可用的功能与文档**。以下内容一律留在本地 workspace，不入库、不推送：

| 类别 | 示例 | 存放位置 |
|---|---|---|
| 推广 / 运营方案 | 渠道矩阵、发帖排期、Star 目标、话术 | `promotion/`（仓库外） |
| 对话与协作记录 | 与 AI 的讨论、决策过程、未定稿草稿 | `.workbuddy/memory/` 或 `promotion/` |
| 内部复盘 | 流量数据、竞品拆解、指标看板 | 本地 |
| 素材原文件 | 海报、GIF、截图源文件 | `promotion/` |

**CI 守卫**：`.github/workflows/ci.yml` 的 `Internal materials must not be committed`
会在 `git ls-files` 中匹配 `promotion|internal|ops` 目录或文件名，命中即失败。

**唯一的例外**：`docs/development-log.md` 与 `CONTEST_DECLARATION.md` 是赛事核验材料，
按 2026-10-14 的约定保留在仓库中；大赛结束后如需移除，须单独确认。
