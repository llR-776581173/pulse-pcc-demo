@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem === Pulse 决策工作台 · 一键启动 8100 ===
rem Portable: uses whatever Python is on PATH; no pip install needed.
set "PYTHONUTF8=1"
set "PULSE_DATA=%~dp0data"
set "PULSE_CUT=2026-09-30"
set "PULSE_WEEK=13"

set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python 3.9+ not found on PATH. Install Python, or run: python pulse_app.py 8100
    pause
    exit /b 1
  )
  set "PY=py"
)

echo.
echo   ============================================================
echo    Pulse 决策工作台  R4  (interactive live system)
echo   ============================================================
echo    Data dir : %PULSE_DATA%
echo    Cut      : %PULSE_CUT%
echo.
echo    Open in browser:  http://127.0.0.1:8100/
echo    Stop server    :  Ctrl+C
echo   ============================================================
echo.

"%PY%" "%~dp0pulse_app.py" 8100
pause
