@echo off
setlocal
cd /d "%~dp0"
title RescueNet Station BETA -- Field Hospital Triage (Port 8002)
color 2F
cls
echo ==============================================================================
echo   RESCUENET STATION BETA: FIELD HOSPITAL TRIAGE (LOCAL LOOPBACK)
echo   Role: Medical Triage | TCP Port: 8002 | Strict Zero-Trust Enforced
echo ==============================================================================
echo.
"%~dp0runtime\python.exe" "%~dp0src\run_node.py" --id beta-hospital --port 8002 --peers alpha-harbor=127.0.0.1:8001,gamma-mountain=127.0.0.1:8003 --db "%~dp0data\beta.db" --key-dir "%~dp0security" --strict-security
pause
