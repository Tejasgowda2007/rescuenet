@echo off
setlocal
cd /d "%~dp0"
title RescueNet Station ALPHA-HARBOR -- Local Loopback
color 1F
cls
echo ==============================================================================
echo   RESCUENET STATION: ALPHA-HARBOR (Harbor Base Command) - LOCAL LOOPBACK
echo ==============================================================================
echo.
"%~dp0runtime\python.exe" "%~dp0src\run_node.py" --id alpha-harbor --host 127.0.0.1 --port 8001 --peers beta-hospital=192.168.1.20:8002,gamma-mountain=192.168.1.30:8003 --db "%~dp0data\alpha-harbor.db" --key-dir "%~dp0security" --strict-security
pause
