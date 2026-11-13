@echo off
setlocal
cd /d "%~dp0"
title RescueNet Station GAMMA -- Mountain Shelter Relay (Port 8003)
color 5F
cls
echo ==============================================================================
echo   RESCUENET STATION GAMMA: MOUNTAIN SHELTER RELAY (LOCAL LOOPBACK)
echo   Role: Mountain Relay | TCP Port: 8003 | Strict Zero-Trust Enforced
echo ==============================================================================
echo.
"%~dp0runtime\python.exe" "%~dp0src\run_node.py" --id gamma-mountain --port 8003 --peers alpha-harbor=127.0.0.1:8001,beta-hospital=127.0.0.1:8002 --db "%~dp0data\gamma.db" --key-dir "%~dp0security" --strict-security
pause
