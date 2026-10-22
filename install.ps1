#requires -version 5.1
<#
.SYNOPSIS
  麦麦省钱助手一键安装脚本（Windows）

.DESCRIPTION
  将本仓库的 Skill 文件复制到指定 Agent 的技能目录。
  只复制 SKILL.md / README / CHANGELOG / scripts / references / config / examples / docs / LICENSE，
  不读取 Token、不修改 MCP 连接器、不安装任何软件。
  已存在的同名技能会先备份为 <name>.bak。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install.ps1                 # 安装到 WorkBuddy
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target claude  # 安装到 Claude Code
#>
param(
    [ValidateSet('workbuddy', 'claude', 'cursor', 'codex')]
    [string]$Target = 'workbuddy'
)

$ErrorActionPreference = 'Stop'

$skillName  = 'mcd-saver'
$sourceDir  = $PSScriptRoot
$targetRoot = @{
    workbuddy = Join-Path $HOME '.workbuddy\skills'
    claude    = Join-Path $HOME '.claude\skills'
    cursor    = Join-Path $HOME '.cursor\skills'
    codex     = Join-Path $HOME '.agents\skills'
}[$Target]

$items = @('SKILL.md', 'README.md', 'CHANGELOG.md', 'scripts', 'references', 'config', 'examples', 'docs', 'LICENSE')
$missing = $items | Where-Object { -not (Test-Path (Join-Path $sourceDir $_)) }
if ($missing) {
    Write-Error "仓库文件不完整，缺少：$($missing -join ', ')。请重新克隆仓库。"
}

$targetDir = Join-Path $targetRoot $skillName
New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null

if (Test-Path $targetDir) {
    $backup = "{0}.bak" -f $targetDir
    if (Test-Path $backup) { Remove-Item -Recurse -Force $backup }
    Rename-Item -Path $targetDir -NewName (Split-Path $backup -Leaf)
    Write-Host "已备份旧版本到 $backup" -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
foreach ($item in $items) {
    Copy-Item -Recurse -Force (Join-Path $sourceDir $item) (Join-Path $targetDir $item)
}

Write-Host ""
Write-Host "✔ 安装完成：$targetDir" -ForegroundColor Green
Write-Host ""
Write-Host "下一步：" -ForegroundColor Cyan
Write-Host "  1. 在 $Target 中按 README 的方式一配置 mcd-mcp MCP 连接（需要 MCP Token）"
Write-Host "  2. 新开一个会话，输入需求即可触发技能（如：怎么点麦当劳最划算）"
