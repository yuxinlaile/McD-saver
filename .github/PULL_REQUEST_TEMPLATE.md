## 变更说明

简要描述本次变更的内容与动机。

## 变更类型

- [ ] 新功能（feat）
- [ ] 修复（fix）
- [ ] 文档（docs）
- [ ] 重构（refactor）
- [ ] 测试（test）
- [ ] 其他

## 自检清单

- [ ] `python -m py_compile scripts/*.py` 通过
- [ ] `python -m pytest tests/ -v` 通过
- [ ] `python scripts/check_toc.py` 通过（README 中英目录锚点与章节一一对应）
- [ ] `python scripts/audit_readme.py` 通过（命令表 / 用例数 / Python 版本 / 许可证与仓库一致）
- [ ] `python scripts/sync_readme.py --check` 通过（「近期版本」区块与 CHANGELOG 同步）
- [ ] `python scripts/build_releases.py --verify` 通过（产物两件套、索引与 SHA-256）
- [ ] 未包含任何真实 Token、密码或个人凭证
- [ ] 涉及工具目录/工作流的变更已同步更新 `references/` 与 `SKILL.md`
- [ ] 如为用户可见变更，已在 `CHANGELOG.md` 顶部新增本次变更条目（版本号用 `python scripts/version.py` 递增）

## 补充

其他需要说明的信息。
