@echo off
REM scripts/windows/install.cmd
REM
REM 0.2.0 起：install.ps1 的 .cmd 兜底转发。
REM
REM 优先用 PowerShell 7+（pwsh），缺失则降级到 PowerShell 5.1（Windows 默认自带）。
REM
REM 行尾：CRLF（见 .gitattributes）。

where pwsh >nul 2>nul
if %errorlevel% == 0 (
    pwsh -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
) else (
    powershell -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
)
