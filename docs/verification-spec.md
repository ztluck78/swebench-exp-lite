# Verification Spec — 本地集成测试 + 极简 CI 模式

> 2026-08-10 由 user 反馈触发的开发流程规范。完整背景与设计见 plan §11
> （`/Users/zhangtian/Library/Application Support/QoderCN/SharedClientCache/cache/plans/Windows_11_适配方案_task-b3f.md` §11）。
> 70+ 分钟 CI 调试教训留底见 [`docs/windows-11-port.md`](windows-11-port.md) §7。

## 1. 三层验证架构

| 层 | 角色 | 何时跑 | 耗时 | 谁负责 |
|---|---|---|---|---|
| **pre-commit hook**（` .githooks/pre-commit`，仓根入库）| spec §1 纪律的**强制落地**——挡快速项（< 1 min）| 每次 `git commit` 自动跑 | < 1 min | Git（本地）|
| **本地集成测试**（主）| 发布门禁 | 任何 commit 前必跑 | 5-10min 首次 / 1-2min 日常 | 开发者本地 |
| **CI 静态 + 单测**（辅）| PR 防线 | push / PR | 30s-1.5m | GitHub Actions |
| **真机红线**（plan §10 跟进）| 多平台验证 | Win11 真机手动 | 5-10min | 用户 / 团队 |

**pre-commit hook 是 spec §1 纪律的强制落地**——开发者首次 clone 仓根后执行 `git config core.hooksPath .githooks` 启用；之后每次 commit 都会自动跑 pip install + 14 单测 + bash 语法检查（< 1 min 快速门禁），挡住 import 错误 / 单测挂 / bash 语法错。**完整必跑**（`scripts/local-test.sh`，5-10min）仍靠自觉 + reviewer 兜底——pre-commit 不会跑（避免 commit 卡顿）。详见 §2。

启用方法（开发者首次 clone 后**只跑一次**）：
```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit   # 若 .githooks/ 仓根已有 +x 可省
```

## 2. Commit 前必跑（按改动类型分层）

`scripts/local-test.sh` 幂等设计——日常 1-2min 远低于之前 CI 17m。

| 改动类型 | 必跑 | 耗时 |
|---|---|---|
| `swebench_exp_lite/` Python 运行时 | `./scripts/local-test.sh` | 5-10min（首次）→ 1-2min（日常）|
| `scripts/windows/*.ps1` 或 `*.cmd` | `./scripts/local-test.sh` | 同上 |
| `start.sh` / `run_demo.sh` / `check-agents.sh` | `./scripts/local-test.sh --skip-install` | 1-2min |
| `swebench_exp_lite/tests/` | `python -m unittest swebench_exp_lite.tests.test_platform -v` | 30s |
| `AGENTS.md` / `README.md` / `GETTING-STARTED.md` / `docs/*.md` | 人眼 review | 0s |
| `.github/workflows/ci.yml` | 严禁扩展红线层（见 §4） | —— |
| 其他（`pyproject.toml` / `.gitattributes` / `.gitignore`）| `./scripts/local-test.sh --skip-install` | 1-2min |

## 3. CI 严禁清单

| 严禁 | 原因 |
|---|---|
| `install.ps1` / `run-demo.ps1` 红线 demo | 17m 太慢 + colima/qemu 脆弱 |
| colima + qemu + lima-additional-guestagents 装包 | 5-8min 装包，依赖 4 个 homebrew 包 |
| `docker load OSS tar` 降级路径 | Windows hosted runner 物理限制 |
| 任何"为追求 CI 通过率"的口径重新解读 | 已被批评"先改规则再自评"是错误模式 |
| cached homebrew / cached Docker 镜像层 | 1-2 分钟收益不值得 |
| 跑 `bash ./start.sh`（macOS 仓根入口）| 改用本地集成测试承担 |

**CI 改动禁区**：任何修改 `.github/workflows/ci.yml` 的 PR **必须**保留上面严禁清单。如必须突破（如加 self-hosted runner），单开 PR + 明确说明 ROI 评估。

## 4. spec §9 硬指标的诚实状态

0.2.0 现状（**不擅自重新解读**）：

| spec §9 验收项 | 状态 |
|---|---|
| [1-6, 8-9] 平台抽象 / Python / answer_evaluator / PowerShell / 目录 / 文档 / macOS 不回归 / 版本号 | ✓ 完全满足 |
| **[7] CI 4 项** | ⚠ **部分：CI 不再跑红线 demo**——红线由本地集成测试承担 |
| **[10] Windows 11 真机红线 3 项** | ✗ **未做（plan §10 跟进）**——用户在 Win11 真机跑 |

**关键原则**：
- spec 文字是 spec 文字——**不改写**
- 实际未达成的项**诚实标注**——不自评"满足"
- 替代方案（本地集成测试）**不替代** spec 硬指标，只**下放**给真正能跑的人

## 5. 严禁的 commit 流程

- 跳过本地测试直接 commit（即使改 .md）
- 在 CI 里加红线 demo 步骤
- 改 spec 口径凑"完成"自评
- 重新解读已无法满足的 spec 硬指标

**默认 commit 流程**：
```
[改代码] → [按改动类型选必跑] → [git add <精确路径>] → [git commit] → [git push] → [CI 30s 静态] → [merge]
```

## 6. 教训留底

[`docs/windows-11-port.md`](windows-11-port.md) §7 保留 v0.2.0 之前 70+ 分钟 CI 调试的完整记录：
- macos colima + qemu x86_64 模拟（CI run 31370934024 / 31379261939，~17m）
- windows docker load 物理限制（CI run 31377862695 等多次）
- 多次"先改规则再自评"的口径偏差

**不再用于 v0.2.0 验证**，仅作教训。

## 7. 未来加新平台（Ubuntu / Arch）纪律

1. 写 `scripts/<platform>/install.{sh,ps1}` + `run-demo.{sh,ps1}` + `check-agents.{sh,ps1}`
2. 写 `scripts/local-test.{sh,ps1}` 的对应分支
3. 写 `scripts/<platform>/README.md`
4. 跑本地集成测试（macOS 真机 + Linux 真机 / VM）
5. **不要把红线 demo 加到 CI**

## 8. 后续可能改进（仅当真有需要时评估）

| 改进 | 推荐度 |
|---|---|
| Self-hosted macOS runner（消除 colima/qemu 17m）| 长期值得 |
| Ubuntu 真机适配 | v0.3+ 路线 |
| Arch 真机适配 | v0.4+ 路线（暂不需要）|
| 自动化 cross-platform installer 验证 | 短期不推荐（仍是 colima/qemu 问题）|

**不在本 spec 范围**——只做记录。任何调整须重新评估 ROI。

## 互链

- **Plan 文件**（设计背景，cache 目录）：`Windows_11_适配方案_task-b3f.md` §11
- **CI 调试教训**：[`docs/windows-11-port.md`](windows-11-port.md) §7
- **本规范仓根入口**：`docs/verification-spec.md`（即本文件）
- **本地集成测试脚本**：`scripts/local-test.sh` / `scripts/windows/local-test.ps1`
