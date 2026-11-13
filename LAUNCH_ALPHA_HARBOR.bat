@echo off
setlocal enabledelayedexpansion
title RescueNet - Laptop Alpha (alpha-harbor)

cd /d "%~dp0"

echo ===============================================================================
echo   RESCUENET DISASTER COORDINATION SYSTEM - LAPTOP ALPHA
echo   Node Identity: alpha-harbor (Harbor Command Center)
echo ===============================================================================
echo.

:: Detect Python
set PYTHON_CMD=python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    where py >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set PYTHON_CMD=py -3
    ) else (
        echo [ERROR] Python 3 was not found in PATH!
        echo Please install Python 3.10+ or add it to your system PATH.
        pause
        exit /b 1
    )
)

echo Starting RescueNet Alpha Node Server...
echo   * TCP Sync Port:      8001
echo   * UDP Discovery Port: 8002
echo   * Web Dashboard Port: 8000
echo.

:: Launch browser in 2 seconds
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000/"

:: Run Node Server
%PYTHON_CMD% -m api.node_server --node-id alpha-harbor --host 0.0.0.0 --tcp-port 8001 --web-port 8000 --discovery-port 8002 --strict-security

pause
