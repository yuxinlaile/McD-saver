#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布产物构建与校验（v2.2 起的统一产物策略）。

每个版本产出**恰好两个**文件，放在 ``releases/v<版本>/``：

- 英文名 → 压缩包：``mcd-saver-v<版本>.zip``
  由 ``git archive`` 打包对应 tag 的完整源码，解压后根目录为 ``McD-Saver-v<版本>/``。
- 中文名 → 配套说明：``麦麦省钱助手-v<版本>-发布说明.md``
  含版本信息、安装指引、该版 CHANGELOG 段落与压缩包 SHA-256。

同一套文件会挂载到同名 GitHub Release，保证「releases 目录 ↔ tag ↔ Release」三者一致。

用法::

    python scripts/build_releases.py --all        # 为全部 tag 构建（含索引）
    python scripts/build_releases.py --current    # 只构建当前版本
    python scripts/build_releases.py --index      # 只重建索引
    python scripts/build_releases.py --verify     # 校验命名、配对与压缩包完整性
    python scripts/build_releases.py --current --upload   # 构建并上传到同名 Release

压缩包为二进制产物，不纳入版本库（见 .gitignore）；中文说明与索引随仓库分发。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASES_DIR = REPO_ROOT / "releases"
REPO_URL = "https://github.com/yuxinlaile/McD-saver"

VERSION_RE = re.compile(r"^v(\d+\.\d+\.\d+)$")
SECTION_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\](?: - (\d{4}-\d{2}-\d{2}))?")


def git(*args: str) -> str:
    """在仓库根目录执行 git 命令，失败时抛出带 stderr 的异常。"""
    result = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("git {0} 失败：{1}".format(" ".join(args), result.stderr.strip()[:200]))
    return result.stdout


def pkg_name(version: str) -> str:
    """英文名产物：压缩包文件名。"""
    return "mcd-saver-v{0}.zip".format(version)


def doc_name(version: str) -> str:
    """中文名产物：配套说明文件名。"""
    return "麦麦省钱助手-v{0}-发布说明.md".format(version)


def version_dir(version: str) -> Path:
    return RELEASES_DIR / "v{0}".format(version)


def list_tags() -> List[str]:
    """返回仓库内全部 ``vX.Y.Z`` 形式的 tag（升序）。"""
    out = git("tag", "--sort=v:refname")
    return [line.strip() for line in out.splitlines() if VERSION_RE.match(line.strip())]


def tag_versions(tags: Optional[List[str]] = None) -> List[str]:
    return [VERSION_RE.match(t).group(1) for t in (tags if tags is not None else list_tags())]


def current_version() -> str:
    """从单一事实源 CLIENT_INFO 读取当前版本。"""
    text = (REPO_ROOT / "scripts" / "mcd_client.py").read_text(encoding="utf-8")
    match = re.search(r'"version":\s*"(\d+\.\d+\.\d+)"', text)
    if not match:
        raise RuntimeError("无法从 scripts/mcd_client.py 读取版本号")
    return match.group(1)


def changelog_section(version: str, ref: Optional[str] = None) -> Tuple[str, str]:
    """取指定版本在 CHANGELOG 中的正文与发布日期。

    ``ref`` 指定从某个 tag 读取（历史版本按其当时的 CHANGELOG），
    默认读取工作区当前 CHANGELOG。
    """
    if ref:
        text = git("show", "{0}:CHANGELOG.md".format(ref))
    else:
        text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    lines = text.splitlines()
    body: List[str] = []
    date = ""
    collecting = False
    for line in lines:
        match = SECTION_RE.match(line)
        if match:
            if collecting:
                break
            if match.group(1) == version:
                collecting = True
                date = match.group(2) or ""
            continue
        if collecting:
            body.append(line)
    if not collecting:
        raise RuntimeError("CHANGELOG 中找不到版本 {0}（ref={1}）".format(version, ref or "worktree"))
    return "\n".join(body).strip() + "\n", date


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_zip(version: str, tag: str) -> Path:
    """用 git archive 生成英文名压缩包（根目录 McD-Saver-v<版本>/）。"""
    out = version_dir(version) / pkg_name(version)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    git(
        "archive",
        "--format=zip",
        "--prefix=McD-Saver-v{0}/".format(version),
        "-o",
        str(out),
        tag,
    )
    return out


def render_doc(version: str, date: str, changelog: str, checksum: str) -> str:
    return """# 麦麦省钱助手 v{version} 发布说明

| 项目 | 内容 |
|---|---|
| 版本 | v{version} |
| 发布日期 | {date} |
| 英文发行包 | `{pkg}` |
| SHA-256 | `{checksum}` |
| 仓库 | <{repo}> |
| 许可证 | MIT |

## 安装

1. 解压 `{pkg}`，进入 `McD-Saver-v{version}/` 目录（仅需 Python 3.9+，无第三方运行依赖）。
2. 配置 MCP Token：`export MCD_MCP_TOKEN=<你的 Token>`（Windows PowerShell 用 `$env:MCD_MCP_TOKEN="..."`）。
3. 自检连通性：`python scripts/mcd.py check`；查看工具目录：`python scripts/mcd.py tools`。
4. 作为 Agent Skill 使用：把目录放到客户端的 skills 路径（详见 `references/agent-skill-installation.md`）。

> Token 申请：<https://open.mcd.cn/mcp>。本项目为社区开源作品，与麦当劳中国官方无隶属关系。

## 版本变更

{changelog}
## 校验

```bash
sha256sum {pkg}
# 期望：{checksum}
```

## 反馈

问题与建议请走仓库讨论区或 Issue：<{repo}/discussions>
""".format(
        version=version,
        date=date or "—",
        pkg=pkg_name(version),
        checksum=checksum,
        repo=REPO_URL,
        changelog=changelog,
    )


def build_version(version: str, tag: Optional[str] = None) -> Tuple[Path, Path]:
    """构建单个版本的两个产物，返回 (zip, doc)。"""
    tag = tag or "v{0}".format(version)
    zip_path = build_zip(version, tag)
    checksum = sha256_of(zip_path)
    # 说明文档优先取该 tag 当时的 CHANGELOG，保证历史版本描述不被后续编辑影响
    try:
        changelog, date = changelog_section(version, ref=tag)
    except RuntimeError:
        changelog, date = changelog_section(version)
    doc_path = version_dir(version) / doc_name(version)
    text = render_doc(version, date, changelog, checksum)
    with io.open(doc_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return zip_path, doc_path


def sort_key(version: str) -> Tuple[int, int, int]:
    return tuple(int(x) for x in version.split("."))  # type: ignore[return-value]


def read_date(version: str) -> str:
    doc = version_dir(version) / doc_name(version)
    if doc.exists():
        match = re.search(r"\| 发布日期 \| ([0-9-]+) \|", doc.read_text(encoding="utf-8"))
        if match:
            return match.group(1)
    return "—"


def build_index(versions: Optional[List[str]] = None) -> Path:
    """重建 releases/README.md 索引（版本 ↔ 产物 ↔ Release 一一对应）。"""
    if versions is None:
        versions = sorted(
            [p.name[1:] for p in RELEASES_DIR.glob("v*") if p.is_dir() and VERSION_RE.match("v" + p.name[1:])],
            key=sort_key,
            reverse=True,
        )
    rows = []
    for version in versions:
        release = "{0}/releases/tag/v{1}".format(REPO_URL, version)
        asset = "{0}/releases/download/v{1}/{2}".format(REPO_URL, version, pkg_name(version))
        rows.append(
            "| v{ver} | {date} | [`{pkg}`]({asset}) | [`{doc}`](v{ver}/{doc}) | [Release]({rel}) |".format(
                ver=version,
                date=read_date(version),
                pkg=pkg_name(version),
                asset=asset,
                doc=doc_name(version),
                rel=release,
            )
        )

    content = """# 发布产物（Releases Artifacts）

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
{rows}
""".format(rows="\n".join(rows))

    out = RELEASES_DIR / "README.md"
    with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    return out



def doc_asset_name(version: str) -> str:
    """Release 附件里的中文说明别名（GitHub 资产名只接受 ASCII）。"""
    return "mcd-saver-v{0}-release-notes-zh.md".format(version)


def _gh_json(path: str) -> Dict[str, Any]:
    result = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("gh api {0} 失败：{1}".format(path, result.stderr.strip()[:160]))
    return json.loads(result.stdout)


def _gh_token() -> str:
    result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("未找到 gh 登录令牌，请先执行 gh auth login")
    return result.stdout.strip()


def _upload_asset(repo: str, release_id: int, name: str, data: bytes, content_type: str, token: str) -> str:
    url = "https://uploads.github.com/repos/{0}/releases/{1}/assets?name={2}".format(
        repo, release_id, urllib.parse.quote(name))
    request = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": "Bearer " + token,
        "Content-Type": content_type,
        "Content-Length": str(len(data)),
        "User-Agent": "mcd-saver-release-bot",
    })
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))["name"]


def upload_release(version: str, repo: str = "yuxinlaile/McD-saver") -> None:
    """把某版本的两个产物挂到同名 Release（幂等：先删同名旧资产）。"""
    folder = version_dir(version)
    zip_path = folder / pkg_name(version)
    doc_path = folder / doc_name(version)
    if not zip_path.exists() or not doc_path.exists():
        raise RuntimeError("v{0} 产物不完整，先执行 --current / --all 构建".format(version))

    release = _gh_json("repos/{0}/releases/tags/v{1}".format(repo, version))
    release_id = release["id"]
    token = _gh_token()
    remove = {zip_path.name, doc_asset_name(version)}
    for asset in release.get("assets", []):
        if asset["name"] in remove:
            subprocess.run(
                ["gh", "api", "-X", "DELETE",
                 "repos/{0}/releases/assets/{1}".format(repo, asset["id"])],
                capture_output=True)
    _upload_asset(repo, release_id, zip_path.name, zip_path.read_bytes(), "application/zip", token)
    _upload_asset(repo, release_id, doc_asset_name(version), doc_path.read_bytes(), "text/markdown", token)

def verify(verbose: bool = True) -> List[str]:
    """校验产物：命名规范、两件套配对、压缩包完整性与索引覆盖。返回问题列表。"""
    problems: List[str] = []
    if not RELEASES_DIR.is_dir():
        return ["releases 目录不存在"]
    dirs = sorted([p for p in RELEASES_DIR.iterdir() if p.is_dir()], key=lambda p: p.name)
    if not dirs:
        problems.append("releases 目录下没有任何版本目录")

    for folder in dirs:
        version = folder.name[1:]
        if not VERSION_RE.match(folder.name):
            problems.append("目录命名不符合 v<X.Y.Z>：{0}".format(folder.name))
            continue
        expected = {pkg_name(version), doc_name(version)}
        actual = {p.name for p in folder.iterdir() if p.is_file()}
        extra = actual - expected
        if extra:
            problems.append("v{0} 存在多余产物：{1}".format(version, ", ".join(sorted(extra))))

        zip_path = folder / pkg_name(version)
        doc_path = folder / doc_name(version)
        if not doc_path.exists():
            problems.append("v{0} 缺少中文说明 {1}".format(version, doc_name(version)))
        else:
            doc = doc_path.read_text(encoding="utf-8")
            if "v{0}".format(version) not in doc:
                problems.append("v{0} 说明文档未标注版本号".format(version))
        if not zip_path.exists():
            problems.append("v{0} 缺少英文压缩包 {1}（本地构建，不入库）".format(version, pkg_name(version)))
            continue
        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                if not any(n.endswith("SKILL.md") for n in names):
                    problems.append("v{0} 压缩包缺少 SKILL.md".format(version))
                if not any(n.startswith("McD-Saver-v{0}/".format(version)) for n in names):
                    problems.append("v{0} 压缩包根目录前缀不符合 McD-Saver-v{0}/".format(version))
        except zipfile.BadZipFile:
            problems.append("v{0} 压缩包损坏".format(version))
            continue
        checksum = sha256_of(zip_path)
        if doc_path.exists() and checksum not in doc_path.read_text(encoding="utf-8"):
            problems.append("v{0} 说明文档中的 SHA-256 与压缩包不一致".format(version))

    index = RELEASES_DIR / "README.md"
    if not index.exists():
        problems.append("缺少 releases/README.md 索引")
    else:
        text = index.read_text(encoding="utf-8")
        for folder in dirs:
            if "({0}/".format(folder.name) not in text and folder.name[1:] not in text:
                problems.append("索引缺少版本 {0}".format(folder.name))

    if verbose:
        if problems:
            print("校验失败：{0} 项问题".format(len(problems)))
            for item in problems:
                print("  -", item)
        else:
            print("校验通过：{0} 个版本，每个版本两件产物（英文 zip + 中文说明），命名与校验和一致。".format(len(dirs)))
    return problems


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="构建/校验发布产物（英文名 zip + 中文名说明）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="为全部 tag 构建产物并重建索引")
    group.add_argument("--current", action="store_true", help="只构建当前版本（默认行为）")
    group.add_argument("--index", action="store_true", help="只重建索引")
    group.add_argument("--verify", action="store_true", help="只校验产物，不构建")
    parser.add_argument("--upload", action="store_true",
                        help="构建后上传到同名 GitHub Release（中文说明使用 ASCII 别名）")
    parser.add_argument("--version", help="指定版本号（如 2.1.3），覆盖默认当前版本")
    args = parser.parse_args(argv)

    if args.verify:
        return 1 if verify() else 0

    if args.index:
        path = build_index()
        print("索引已更新：{0}".format(path.relative_to(REPO_ROOT)))
        return 0

    if args.all:
        versions = tag_versions()
        for version in versions:
            zip_path, doc_path = build_version(version)
            print("构建 v{0}：{1} · {2}".format(version, zip_path.name, doc_path.name))
            if args.upload:
                upload_release(version)
                print("  已上传到 Release v{0}".format(version))
        path = build_index(versions)
        print("索引已更新：{0}（{1} 个版本）".format(path.relative_to(REPO_ROOT), len(versions)))
        return 0

    version = args.version or current_version()
    zip_path, doc_path = build_version(version)
    print("构建 v{0}：{1} · {2}".format(version, zip_path.name, doc_path.name))
    if args.upload:
        upload_release(version)
        print("已上传到 Release v{0}".format(version))
    build_index()
    return 0


if __name__ == "__main__":
    sys.exit(main())
