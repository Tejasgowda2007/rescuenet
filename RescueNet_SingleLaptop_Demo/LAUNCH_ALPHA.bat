@echo off
setlocal
cd /d "%~dp0"
title RescueNet Station ALPHA -- Harbor Base Command (Port 8001)
color 1F
cls
echo ==============================================================================
echo   RESCUENET STATION ALPHA: HARBOR BASE COMMAND (LOCAL LOOPBACK)
echo   Role: Coordinator | TCP Port: 8001 | Strict Zero-Trust Enforced
echo ==============================================================================
echo.
"%~dp0runtime\python.exe" "%~dp0src\run_node.py" --id alpha-harbor --port 8001 --peers beta-hospital=127.0.0.1:8002,gamma-mountain=127.0.0.1:8003 --db "%~dp0data\alpha.db" --key-dir "%~dp0security" --strict-security
pause
