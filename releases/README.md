# 发布产物（Releases Artifacts）

本目录与 GitHub Releases、git tag **一一对应**，每个版本恰好两个产物；命名与打包规则如下。

## 产物规则

| 类型 | 命名 | 形式 | 说明 |
|---|---|---|---|
| 英文名 | `mcd-saver-v<版本>.zip` | 压缩包 | 对应 tag 的完整源码包，解压后根目录 `McD-Saver-v<版本>/` |
| 中文名 | `麦麦省钱助手-v<版本>-发布说明.md` | 说明文档 | 版本信息、安装指引、该版变更记录与 SHA-256 校验 |

- 压缩包为二进制产物，**不纳入版本库**（见 `.gitignore`），由脚本重建后挂载到同名 GitHub Release。
- 说明文档与索引随仓库分发，历史版本内容取自该 tag 当时的 `CHANGELOG.md`，不会被后续编辑覆盖。
- GitHub Releases 的资产名只接受 ASCII：中文说明在 Release 附件中另存为
  `mcd-saver-v<版本>-release-notes-zh.md`（内容与本目录中文文件完全一致）；
  **中文原名以本目录为准**，附件别名仅为平台限制下的分发兼容。
- 新版本发布：先 `python scripts/version.py --apply`，再 `python scripts/build_releases.py --current`，
  然后上传两个产物到 Release，最后 `python scripts/build_releases.py --verify` 校验。

## 重建与校验

```bash
python scripts/build_releases.py --all       # 为全部 tag 构建产物与索引
python scripts/build_releases.py --current   # 只构建当前版本
python scripts/build_releases.py --index     # 只重建本索引
python scripts/build_releases.py --verify    # 校验命名、配对、压缩包完整性
```

## 版本索引

| 版本 | 发布日期 | 英文发行包（压缩包） | 中文说明（文档） | Release |
|---|---|---|---|---|
| v2.2.0 | 2026-10-19 | [`mcd-saver-v2.2.0.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v2.2.0/mcd-saver-v2.2.0.zip) | [`麦麦省钱助手-v2.2.0-发布说明.md`](v2.2.0/麦麦省钱助手-v2.2.0-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v2.2.0) |
| v2.1.3 | 2026-10-19 | [`mcd-saver-v2.1.3.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v2.1.3/mcd-saver-v2.1.3.zip) | [`麦麦省钱助手-v2.1.3-发布说明.md`](v2.1.3/麦麦省钱助手-v2.1.3-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v2.1.3) |
| v2.1.2 | 2026-10-19 | [`mcd-saver-v2.1.2.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v2.1.2/mcd-saver-v2.1.2.zip) | [`麦麦省钱助手-v2.1.2-发布说明.md`](v2.1.2/麦麦省钱助手-v2.1.2-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v2.1.2) |
| v2.1.1 | 2026-10-19 | [`mcd-saver-v2.1.1.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v2.1.1/mcd-saver-v2.1.1.zip) | [`麦麦省钱助手-v2.1.1-发布说明.md`](v2.1.1/麦麦省钱助手-v2.1.1-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v2.1.1) |
| v2.1.0 | 2026-10-19 | [`mcd-saver-v2.1.0.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v2.1.0/mcd-saver-v2.1.0.zip) | [`麦麦省钱助手-v2.1.0-发布说明.md`](v2.1.0/麦麦省钱助手-v2.1.0-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v2.1.0) |
| v2.0.3 | 2026-10-15 | [`mcd-saver-v2.0.3.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v2.0.3/mcd-saver-v2.0.3.zip) | [`麦麦省钱助手-v2.0.3-发布说明.md`](v2.0.3/麦麦省钱助手-v2.0.3-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v2.0.3) |
| v2.0.2 | 2026-10-15 | [`mcd-saver-v2.0.2.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v2.0.2/mcd-saver-v2.0.2.zip) | [`麦麦省钱助手-v2.0.2-发布说明.md`](v2.0.2/麦麦省钱助手-v2.0.2-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v2.0.2) |
| v2.0.1 | 2026-10-15 | [`mcd-saver-v2.0.1.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v2.0.1/mcd-saver-v2.0.1.zip) | [`麦麦省钱助手-v2.0.1-发布说明.md`](v2.0.1/麦麦省钱助手-v2.0.1-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v2.0.1) |
| v2.0.0 | 2026-10-15 | [`mcd-saver-v2.0.0.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v2.0.0/mcd-saver-v2.0.0.zip) | [`麦麦省钱助手-v2.0.0-发布说明.md`](v2.0.0/麦麦省钱助手-v2.0.0-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v2.0.0) |
| v1.7.4 | 2026-10-15 | [`mcd-saver-v1.7.4.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.7.4/mcd-saver-v1.7.4.zip) | [`麦麦省钱助手-v1.7.4-发布说明.md`](v1.7.4/麦麦省钱助手-v1.7.4-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.7.4) |
| v1.7.3 | 2026-10-15 | [`mcd-saver-v1.7.3.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.7.3/mcd-saver-v1.7.3.zip) | [`麦麦省钱助手-v1.7.3-发布说明.md`](v1.7.3/麦麦省钱助手-v1.7.3-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.7.3) |
| v1.7.2 | 2026-10-15 | [`mcd-saver-v1.7.2.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.7.2/mcd-saver-v1.7.2.zip) | [`麦麦省钱助手-v1.7.2-发布说明.md`](v1.7.2/麦麦省钱助手-v1.7.2-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.7.2) |
| v1.7.1 | 2026-10-15 | [`mcd-saver-v1.7.1.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.7.1/mcd-saver-v1.7.1.zip) | [`麦麦省钱助手-v1.7.1-发布说明.md`](v1.7.1/麦麦省钱助手-v1.7.1-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.7.1) |
| v1.7.0 | 2026-10-14 | [`mcd-saver-v1.7.0.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.7.0/mcd-saver-v1.7.0.zip) | [`麦麦省钱助手-v1.7.0-发布说明.md`](v1.7.0/麦麦省钱助手-v1.7.0-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.7.0) |
| v1.6.0 | 2026-10-14 | [`mcd-saver-v1.6.0.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.6.0/mcd-saver-v1.6.0.zip) | [`麦麦省钱助手-v1.6.0-发布说明.md`](v1.6.0/麦麦省钱助手-v1.6.0-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.6.0) |
| v1.5.0 | 2026-10-13 | [`mcd-saver-v1.5.0.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.5.0/mcd-saver-v1.5.0.zip) | [`麦麦省钱助手-v1.5.0-发布说明.md`](v1.5.0/麦麦省钱助手-v1.5.0-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.5.0) |
| v1.4.2 | 2026-10-12 | [`mcd-saver-v1.4.2.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.4.2/mcd-saver-v1.4.2.zip) | [`麦麦省钱助手-v1.4.2-发布说明.md`](v1.4.2/麦麦省钱助手-v1.4.2-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.4.2) |
| v1.4.1 | 2026-10-12 | [`mcd-saver-v1.4.1.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.4.1/mcd-saver-v1.4.1.zip) | [`麦麦省钱助手-v1.4.1-发布说明.md`](v1.4.1/麦麦省钱助手-v1.4.1-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.4.1) |
| v1.4.0 | 2026-10-12 | [`mcd-saver-v1.4.0.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.4.0/mcd-saver-v1.4.0.zip) | [`麦麦省钱助手-v1.4.0-发布说明.md`](v1.4.0/麦麦省钱助手-v1.4.0-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.4.0) |
| v1.3.0 | 2026-10-12 | [`mcd-saver-v1.3.0.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.3.0/mcd-saver-v1.3.0.zip) | [`麦麦省钱助手-v1.3.0-发布说明.md`](v1.3.0/麦麦省钱助手-v1.3.0-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.3.0) |
| v1.2.1 | 2026-10-10 | [`mcd-saver-v1.2.1.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.2.1/mcd-saver-v1.2.1.zip) | [`麦麦省钱助手-v1.2.1-发布说明.md`](v1.2.1/麦麦省钱助手-v1.2.1-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.2.1) |
| v1.2.0 | 2026-10-10 | [`mcd-saver-v1.2.0.zip`](https://github.com/yuxinlaile/McD-saver/releases/download/v1.2.0/mcd-saver-v1.2.0.zip) | [`麦麦省钱助手-v1.2.0-发布说明.md`](v1.2.0/麦麦省钱助手-v1.2.0-发布说明.md) | [Release](https://github.com/yuxinlaile/McD-saver/releases/tag/v1.2.0) |
