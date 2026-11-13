@echo off
setlocal
cd /d "%~dp0"
title RescueNet Station GAMMA-MOUNTAIN -- Local Loopback
color 5F
cls
echo ==============================================================================
echo   RESCUENET STATION: GAMMA-MOUNTAIN (Mountain Shelter Relay) - LOCAL LOOPBACK
echo ==============================================================================
echo.
"%~dp0runtime\python.exe" "%~dp0src\run_node.py" --id gamma-mountain --host 127.0.0.1 --port 8003 --peers alpha-harbor=192.168.1.10:8001,beta-hospital=192.168.1.20:8002 --db "%~dp0data\gamma-mountain.db" --key-dir "%~dp0security" --strict-security
pause
