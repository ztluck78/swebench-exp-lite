# scripts/windows/run-demo.ps1
#
# 0.2.0 起：Windows 11 replay-agent 闭环演示入口（与 macOS run_demo.sh 一一对应）。
#
# replay-agent 是"回放已知 gold patch"的闭环自检：它不调用任何 LLM，
# 直接把官方答案写回评分链路，证明 出题→做题→打分 管道本身通畅。
# 结果 resolved=true 不代表任何模型的解题能力。
#
# 运行：
#   pwsh scripts/windows/run-demo.ps1
# 或
#   ./scripts/windows/run-demo.cmd
#
# 行尾：CRLF（见 .gitattributes）。

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "_common.ps1")

$py = Get-VenvPython

Write-Info "==> 六阶段闭环: $Script:DemoInstance (adapter=replay-agent)"

$startTime = Get-Date
& $py -m swebench_exp_lite run --instance $Script:DemoInstance --adapter replay-agent @args
if ($LASTEXITCODE -ne 0) {
    throw "replay-agent 运行失败 (exit=$LASTEXITCODE)"
}
$elapsed = (Get-Date) - $startTime

$result = Join-Path $Script:RepoRoot "output/$Script:DemoInstance/result.json"
Write-Host ""
Write-Info "==> result.json ($result)"
if (Test-Path $result) {
    Get-Content $result -Raw
} else {
    Write-Warn "未找到 $result（运行可能中途失败）"
}

Write-Host ""
Write-Info "==> 逐字段教学解读"
Write-Host @"
  instance_id / run_id / model   本次实验的身份三元组（report 路径由 run_id+model 拼出）
  adapter=replay-agent           作答方是"回放器"，不是真实模型
  resolved / resolved_pct        判定结论：gold 测试集（F2P 全过 ∧ P2P 全过）→ 100.0
  report_source                  resolved 的证据来源：instance_report=逐实例真实报告
                                 （若是 aggregated_report/report not found 则说明证据降级）
  fail_to_pass / pass_to_pass    修复验证测试 / 回归测试的通过明细
  baseline_resolved=null         0.2.0 不跑 baseline；resolved 相对 gold 测试集判定，与 baseline 无关
  image                          本次评分所用的 Docker 评测镜像
  stage_timings                  各阶段耗时（S6 评分占大头，首次需跑容器内测试）

  重要声明：replay-agent 是回放已知 gold patch 的闭环自检，证明链路通畅，
  不代表模型解题能力。换真实 Agent 请看 GETTING-STARTED.md 第 5 章。
"@
Write-Info "  本次流程本体耗时: $([int]$elapsed.TotalSeconds)s"
