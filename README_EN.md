<div align="center">

# 🍟 McD Saver

<img src="docs/assets/banner.svg" alt="McD Saver" width="720" />

**Let AI get you McDonald's for less** — Agent Skill + standalone CLI in one repo

[![Live Demo](https://img.shields.io/badge/%F0%9F%8E%AE_Live_Demo-no_sign--in-FFC72C?style=flat-square)](https://yuxinlaile.github.io/McD-saver/demo.html)
[![Release](https://img.shields.io/badge/Release-v2.2.0-9a3412?style=flat-square)](https://github.com/yuxinlaile/McD-saver/releases/tag/v2.2.0)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Dependencies](https://img.shields.io/badge/Dependencies-None%20(stdlib)-green)
![Tests](https://img.shields.io/badge/Tests-245%20passed-brightgreen)
![License](https://img.shields.io/badge/License-MIT-orange)
![MCP](https://img.shields.io/badge/MCP-Streamable%20HTTP-purple)

**[🎮 30-sec online demo (no sign-in)](https://yuxinlaile.github.io/McD-saver/demo.html) · [📦 Quick start](#quick-start) · [💬 Discussions](https://github.com/yuxinlaile/McD-saver/discussions) · [🛍️ Also on Agensi](https://www.agensi.io/creators/creator-571) · [简体中文](README.md)**

</div>

---

## Table of contents

- [Project overview](#project-overview)
- [Features](#features)
- [Quick start](#quick-start)
  - [30 seconds, no token](#30-seconds-no-token)
  - [Installation](#installation)
- [Usage](#usage)
  - [Command cheat sheet](#command-cheat-sheet)
  - [Cross-channel example](#cross-channel-example)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [Tool coverage](#tool-coverage)
- [FAQ](#faq)
- [Release notes](#release-notes)
- [Release artifacts](#release-artifacts)
- [Feedback](#feedback)
- [Contributing](#contributing)
- [Disclaimer](#disclaimer)
- [License](#license)
- [Star History](#star-history)

## Project overview

McD Saver (package name `maimai-saver`) is a McDonald's China ordering assistant with one goal — saving money.
**It does not order for you; it enforces a savings check before every order**:
claim all claimable coupons, pick the best coupon for your cart, run a
dual-price comparison via the official `calculate-price`, evaluate points
redemption, then show the full savings breakdown (list price / discount /
payable / saved) for your confirmation.

One repo, three ways to use it:

- **Agent Skill**: a `SKILL.md` following the open standard — drop into
  WorkBuddy / Claude Code / Cursor / Codex;
- **Standalone CLI**: `scripts/mcd.py` talks to the official MCP Server
  (integration guide: [M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server)),
  no client required;
- **Online calculator**: pure front-end, no sign-in, one-click real-menu import.

**Design principles** — deliberate departures from common practice among similar tools:

| Common approach | This project's approach | Why it matters |
|---|---|---|
| Official coupons only | **Official + Meituan/Douyin group-buys + points mall**, same-basis cross-channel final call | Vouchers sitting in your group-buy apps are part of the decision |
| Encourage add-ons to reach thresholds | Baseline is "no add-on"; **add-on traps flagged proactively** | Buying more just to use a coupon is often more expensive |
| Coupons are resources | Coupons are **perishable money**: scheduling computes realizable vs doomed value | A ¥150 coupon pack may only be worth ¥60 in practice |
| Guess faceless coupon values | Probe via calculate-price with the coupon's product code + couponId; **fail honestly** | Models can't produce real prices — they guess |
| Manual nutrition math | **4-dimension constraints**: budget / kcal / protein floor / sodium cap; missing data flagged as non-compliant | Hard requirement for fitness-conscious users |
| Cron-style auto-claiming | `claim` is a one-shot interactive confirmation; **no automation or scheduling** | Lower risk of platform rate-limiting and account bans |
| Re-type the menu | Online calculator with **one-click real-menu import** (paste MCP output) | The compliant path to full official-menu sync |

> **Design core: put the official app, Meituan, Douyin and the points mall on the
> same table and compute the endgame — instead of optimizing within a single channel.**

**Order safety**: no order is created without explicit user confirmation;
order created ≠ paid — payment always happens on McDonald's official page.

## Features

**💰 4-step savings check** (core methodology, agent-driven)

- Claim first → store-level coupon selection → dual-price comparison → points evaluation
- Every discount must come from actual official tool responses — **never fabricated**

**🧮 Coupon combination optimizer** (`optimizer.py`)

- Deterministic enumeration of "no-coupon / single-coupon / add-on / set-meal-swap" candidates, priced and ranked per plan
- 4-dimension constraints: `--budget` / `--max-kcal` / `--min-protein` / `--max-sodium`
- Violators ranked last with the gap shown; missing data honestly flagged as unknown — **never silently filtered**

**📉 Cross-channel comparison engine** (`deal_compare.py`)

- User-entered Meituan/Douyin deals (those platforms have no public APIs — no scraping) compared against official prices on the same basis
- Final "official vs group-buy" call with stacking rules and restrictions spelled out

**🩺 Silent-cost check** (`silent_cost.py`)

- Expiring-coupon scan + **coupon scheduling** (expiry window × order frequency → realizable vs doomed value)
- Order-history profile (avg ticket / repeat items) + points shadow price
- Faceless coupons probed via `--probe`; `--html` generates a shareable single-file report

**🛡️ Security & compliance**

- Token resolved from env var / file / CLI arg, never logged
- 401 fails fast; 429 exponential backoff honoring `Retry-After`; 5xx/network auto-retry
- Scope boundary: focused on pre-order savings decisions — no scraping, auto-ordering or unattended scheduling capabilities

**🧪 Tested**: 245 unit tests covering SSE parsing, token resolution, backoff math,
comparison decisions, combination optimization and CLI exit codes; the full
`demo.py` pipeline is asserted by `tests/test_demo_pipeline.py` — **the demo
doubles as a regression test**.

## Quick start

### 30 seconds, no token

```bash
git clone https://github.com/yuxinlaile/McD-saver.git
cd McD-saver
python demo.py          # offline full pipeline: claim → pick → price → points → schedule → cross-channel
```

Or open the [online calculator](https://yuxinlaile.github.io/McD-saver/demo.html)
(no sign-in; 31 menu items / 9 coupons / 11 group-buy samples; **token quick-import**
— desktop generates the command, mobile imports via agent paste or a menu.json file —
to sync the full real McDonald's App menu).

### Installation

**Step 1 · Get an MCP Token** (needed for options 1–2; the offline demo and the
online calculator don't need one)

1. Open <https://open.mcd.cn/mcp>, sign in (phone verification, mainland China only)
2. Console → Activate → accept the agreement → copy the MCP Token

**Step 2 · Pick one option**

| Option | Best for | How |
|---|---|---|
| **Option 1 · MCP client** | WorkBuddy / Cursor / Claude Code users | Replace `${MCD_MCP_TOKEN}` in [`config/mcp.example.json`](config/mcp.example.json) with your token, paste into your client's MCP settings (locations under [Configuration](#configuration)), enable `mcd-mcp` |
| **Option 2 · Agent Skill** | Agent-triggered savings checks | `git clone https://github.com/yuxinlaile/McD-saver.git ~/.claude/skills/maimai-saver` (Cursor: `~/.cursor/skills/` · Codex: `~/.agents/skills/` · WorkBuddy: `~/.workbuddy/skills/`, or run the bundled `install.ps1` on Windows), plus the MCP connection from option 1; per-platform details in [agent-skill-installation.md](references/agent-skill-installation.md) |
| **Option 3 · Standalone CLI** | Scripts and debugging, no client | `export MCD_MCP_TOKEN="your-token"` (or write it to `~/.mcd_mcp_token`), then `python scripts/mcd.py check` |

Once installed, the agent follows `SKILL.md` and obeys four conduct rules:
**query before write / confirm before ordering / always run the savings check /
never fabricate discounts**.

## Usage

### Command cheat sheet

| Command | What it does |
|---|---|
| `python demo.py` | **30-sec offline full pipeline** (no token; `--section price` for one section) |
| `python scripts/mcd.py check` | Verify token & connectivity |
| `python scripts/mcd.py tools` | List all 35 official tools |
| `python scripts/mcd.py schema <tool>` | Inspect a tool's input schema |
| `python scripts/mcd.py call <tool> --arg k=v` | Call an official tool (`--raw` for raw output) |
| `python scripts/mcd.py claim` | Claim available coupons (list → confirm → bind) |
| `python scripts/optimizer.py plan --wants w.json --menu m.json --coupons c.json [--mcp]` | Combination optimizer; `--budget/--max-kcal/--min-protein/--max-sodium` constraints; auto group-buy final call when the deal library is non-empty (`--no-deals` to disable) |
| `python scripts/deal_compare.py add/list/compare` | Record group-buys & cross-channel comparison |
| `python scripts/silent_cost.py report --coupons c.json --orders o.json --points p.json` | Silent-cost check; `--probe` measures coupon value / `--html` generates a shareable report |

**CLI exit codes** (mcd.py): `0` ok · `1` tool error · `2` auth · `3` rate-limited · `4` network
(deal_compare.py: `0` ok · `1` usage/data error · `2` empty library)

**Global options**: `--token`, `--url`, `--timeout` (default 30s), `--retries` (default 3), `--verbose`.

> **`claim` safety boundary**: user-initiated, single-shot, always confirms with `y`
> (`--yes` for scripting); no cron jobs or unattended background mode, in line with
> platform risk-control requirements.

### Cross-channel example

```bash
# Record a group-buy deal you found on Meituan
python scripts/deal_compare.py add \
    --platform meituan --title "McDonald's ¥40-14 voucher" \
    --price 25.9 --face 40 --channel store --time limited \
    --valid-until 2026-11-30 --notes "1 per day"

# Same-basis comparison against the official price (face 48.5 / payable 38.5)
python scripts/deal_compare.py compare --mcd-face 48.5 --mcd-price 38.5
```

> Results are local estimates (group-buy platforms have no public APIs);
> methodology in [group-buy-comparison.md](references/group-buy-comparison.md).
> The data layer reserves the `MAIMAI_DEALS_PROVIDER` env var as a plug-in point.

## Configuration

**Config files**

| File | Purpose |
|---|---|
| `config/mcp.example.json` | MCP client template (`${MCD_MCP_TOKEN}` placeholder) |
| `mcp-config.example.json` | Root sanitized config (contest requirement) |

**Environment variables**

| Variable | Description |
|---|---|
| `MCD_MCP_TOKEN` | MCP Token (highest priority) |
| `MCD_MCP_TOKEN_FILE` | Token file path, default `~/.mcd_mcp_token` |
| `MCD_MCP_URL` | MCP Server URL, default `https://mcp.mcd.cn` |
| `MAIMAI_DEALS_FILE` | Deal library path, default `~/.maimai_saver/deals.json` |
| `MAIMAI_DEALS_PROVIDER` | External data-source module path (implements `load_deals()`), optional |

**MCP client locations**: WorkBuddy `~/.workbuddy/mcp.json` · Cursor Settings → Tools & MCP ·
Cherry Studio / Trae / VSCode / Kiro own MCP settings pages · Codex `[mcp_servers.mcd-mcp]`
in `~/.codex/config.toml`.

**Token security**: provide the token via env var, token file or `--token` only;
never commit it, never let it appear in logs. If leaked, re-apply at open.mcd.cn/mcp immediately.

## Project layout

```
scripts/     Core: MCP client, CLI, coupon optimizer, silent-cost audit, version & release tooling
references/  Playbooks: tool catalog, savings strategies, group-buy comparison, workflows, pitfalls
docs/        Online calculator and brand assets (demo.html / index.html / banner.svg)
tests/       245 unit tests plus repository-consistency checks
fixtures/    Offline regression data (menu, coupons, orders, points, mall, deals)
releases/    Release artifacts: English zip + Chinese notes + index per version
```

Full file-level tree: [`SKILL.md`](SKILL.md#directory-structure).

## Tool coverage

| Domain | Tools |
|---|---|
| Nutrition | `list-nutrition-foods` |
| Addresses & stores | `delivery-query-addresses` `delivery-create-address` `delivery-query-stores` `query-nearby-stores` `query-meal-assistance` |
| Menu & pricing | `query-meals` `query-meal-detail` `calculate-price` `query-promotions` |
| Ordering & orders | `create-order` `cancel-order` `query-order` `order-list` `query-survey-coupon` |
| Coupons | `query-store-coupons` `available-coupons` `auto-bind-coupons` `query-my-coupons` |
| Points & mall | `query-my-account` `mall-points-products` `mall-product-detail` `mall-create-order` `mall-order-list` `mall-order-detail` |
| Points lottery | `query-lottery-info` `draw-lottery` `query-my-prizes` |
| Themed events | `query-party-city` `query-party-store` `query-partystore-date` `query-partystore-session` `party-order-create` |
| Utilities | `now-time-info` `campaign-calendar` |

Full catalog: [`references/tools.md`](references/tools.md); workflows:
[`references/workflows.md`](references/workflows.md) and [`SKILL.md`](SKILL.md);
integration pitfalls (response shapes / units / polymorphic fields / snapshot
freshness): [`references/mcp-pitfalls.md`](references/mcp-pitfalls.md).

## FAQ

**Q1: HTTP 401?** Token invalid/expired/missing. 401 is never retried; check the
three channels and re-apply at [open.mcd.cn/mcp](https://open.mcd.cn/mcp).

**Q2: HTTP 429?** 600 requests/min per token. The CLI retries with exponential
backoff (honoring Retry-After); slow down and check for `query-meal-detail` loops.

**Q3: Empty `tools` list?** Run `check` first; make sure `--url` / `MCD_MCP_URL` is correct.

**Q4: Tool argument errors?** Don't guess — `python scripts/mcd.py schema <tool>`;
pass codes (storeCode, meal codes, couponId) through from previous responses unchanged.

**Q5: Estimate mode vs `--mcp`?** Estimate mode computes locally, marked
"unverified" — for quick comparison only; `--mcp` walks official calculate-price
per plan (delivery fee and stacking included) and is the only mode that can
guide an order.

**Q6: Where does comparison data come from?** Meituan/Douyin have no public APIs;
deals are user-entered, results are estimates. External sources plug in via
`MAIMAI_DEALS_PROVIDER`.

**Q7: Which agents?** WorkBuddy, Claude Code, Cursor, OpenAI Codex (same SKILL.md).

**Q8: Usage restrictions?** Mainland China only (excluding Hong Kong, Macao and
Taiwan), personal non-commercial use — see the disclaimer below.

More troubleshooting: [`references/error-handling.md`](references/error-handling.md)
(no tokens in issues, please).

## Release notes

Current version **v2.2.0**. Recent highlights:
| Version | Highlights |
|---|---|
| **v2.2.0** | 171→245 tests · 76% coverage · docs consistency in CI · JSON-RPC error-code fix |
| **v2.1.3** | Sliders accept typed values · mobile card clipping fixed |
| **v2.1.2** | Demo 4D constraint sliders · verified-run record · CI coverage gate |
| **v2.1.1** | Two-phase real pricing (Top-K prefilter, -60% calls) |
| **v2.1.0** | Proactive rate limiting (300/min) · scene labels for plan ranking |
| **v2.0.3** | optimizer auto-links group-buy final call (official vs deals in one pass) |
| **v2.0.2** | Mobile copy adaptation + floating calc FAB (result reachability) |
| **v2.0.1** | Mobile import paths (agent paste / menu.json file) |
| **v2.0.0** | Auto version-bump tool (custom z.x.y scheme: y≤3, x≤6) |
| **v1.7.4** | Mobile optimization (44px touch targets / iOS zoom fix / result card on top) |
| **v1.7.3** | Demo token-import card pinned to top · group-buy samples 6→11 |
| **v1.7.1** | Savings grade (S/A/B/C/D) · parameter-chaining guide |
| **v1.7.0** | Swap suggestions ordered by kcal cost · taste memory · MCP pitfalls guide · capability status disclosure |
| v1.6.0 | Coupon scheduling (realizable vs doomed) · coupon-value probing · shareable HTML report · offline full-pipeline demo |
| v1.5.0 | Nutrition constraints: protein floor / sodium cap, violators flagged honestly |
| v1.4.x | Multi-dimension constraints + set-meal swap + points shadow price + one-shot claiming |

Full history in [CHANGELOG.md](CHANGELOG.md); downloads on the
[Releases](https://github.com/yuxinlaile/McD-saver/releases) page.

## Contributing

Issues / PRs / Discussions welcome: workflow docs, translation proofreading,
tool catalog updates (the `tools` subcommand output is authoritative). Full
process in [CONTRIBUTING.md](CONTRIBUTING.md); real-run evidence template in
[examples/verified-run.md](examples/verified-run.md).

Before submitting: pytest passes · no tokens or credentials · `references/` and
`SKILL.md` updated · CHANGELOG noted · **README zh & en in sync**.

## Disclaimer

This is a **community open-source project with no affiliation with, nor
endorsement from, McDonald's Corporation or its affiliates**. Using the
McDonald's MCP service is subject to McDonald's China Terms of Use and the
McDonald's MCP Service Rules — **mainland China only (excluding Hong Kong,
Macao and Taiwan), personal non-commercial use**. Savings figures come from
actual official tool responses and constitute no price promise.
"McDonald's", "麦当劳", "麦乐送", "麦麦" and related marks belong to McDonald's
Corporation.

## License

This project's code is released under the [MIT](LICENSE) license; running it
relies on the McDonald's China MCP service and the upstream integration guide
([M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server)) — using
those services is subject to their terms and upstream restrictions.

## Release artifacts

Every version ships one pair of artifacts — in [`releases/`](releases/README.md) and on the matching GitHub Release:

| Type | Naming | Form | Contents |
|---|---|---|---|
| English | `mcd-saver-v<version>.zip` | Archive | Full source at that tag; extracts to `McD-Saver-v<version>/` |
| Chinese | `麦麦省钱助手-v<version>-发布说明.md` | Notes | Version info, install steps, changes for that version, SHA-256 |

- Versions follow the project's custom `z.x.y` scheme (patch ≤3, minor ≤6, carry on overflow), bumped and synced by `scripts/version.py`
- `scripts/build_releases.py` builds and verifies artifacts: `--all` for every tag, `--verify` for naming, pairing and archive integrity
- Each tag maps to exactly one release, and every release carries the same two files — tag ↔ release ↔ `releases/` stay in lockstep
  (GitHub asset names reject non-ASCII, so the Chinese notes appear as `mcd-saver-v<version>-release-notes-zh.md`
  with identical content; the original Chinese filename lives in `releases/`)

## Feedback

Questions or suggestions? Leave a note in [Discussions](https://github.com/yuxinlaile/McD-saver/discussions),
or pick by scenario: 🐛 [Bug report](https://github.com/yuxinlaile/McD-saver/issues/new?template=bug_report.md) ·
💡 [Feature request](https://github.com/yuxinlaile/McD-saver/issues/new?template=feature_request.md) ·
🤝 [Share group-buy deals](https://github.com/yuxinlaile/McD-saver/discussions) (help the deal library grow).
Every piece of feedback gets read — it is exactly how the calculator keeps improving for real-world use.

## Star History

If you find this useful, a ⭐ helps more McDonald's regulars discover it:

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=yuxinlaile/McD-saver&type=Date)](https://star-history.com/#yuxinlaile/McD-saver&Date)

</div>

---

<details><summary>🔍 Search keywords</summary>
<br>

McDonald's China, coupon optimizer, deal comparison, group-buy (Meituan/Douyin), points valuation, nutrition budget, silent cost audit, MCP agent skill, Claude, WorkBuddy, Cursor, Codex, CLI, online calculator, McD Saver, 麦当劳, 省钱, 优惠券, 团购, 积分, 组合优化

</details>
