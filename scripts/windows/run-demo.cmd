@echo off
REM scripts/windows/run-demo.cmd
REM 0.2.0 起：run-demo.ps1 的 .cmd 兜底转发（详见 install.cmd 注释）。

where pwsh >nul 2>nul
if %errorlevel% == 0 (
    pwsh -ExecutionPolicy Bypass -File "%~dp0run-demo.ps1" %*
) else (
    powershell -ExecutionPolicy Bypass -File "%~dp0run-demo.ps1" %*
)
