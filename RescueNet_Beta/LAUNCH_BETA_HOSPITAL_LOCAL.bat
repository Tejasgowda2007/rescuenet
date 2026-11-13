@echo off
setlocal
cd /d "%~dp0"
title RescueNet Station BETA-HOSPITAL -- Local Loopback
color 2F
cls
echo ==============================================================================
echo   RESCUENET STATION: BETA-HOSPITAL (Field Hospital Triage) - LOCAL LOOPBACK
echo ==============================================================================
echo.
"%~dp0runtime\python.exe" "%~dp0src\run_node.py" --id beta-hospital --host 127.0.0.1 --port 8002 --peers alpha-harbor=192.168.1.10:8001,gamma-mountain=192.168.1.30:8003 --db "%~dp0data\beta-hospital.db" --key-dir "%~dp0security" --strict-security
pause
