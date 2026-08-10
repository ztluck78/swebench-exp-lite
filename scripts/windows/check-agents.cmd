@echo off
REM scripts/windows/check-agents.cmd
REM 0.2.0 起：check-agents.ps1 的 .cmd 兜底转发（详见 install.cmd 注释）。

where pwsh >nul 2>nul
if %errorlevel% == 0 (
    pwsh -ExecutionPolicy Bypass -File "%~dp0check-agents.ps1" %*
) else (
    powershell -ExecutionPolicy Bypass -File "%~dp0check-agents.ps1" %*
)
