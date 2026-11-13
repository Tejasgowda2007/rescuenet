@echo off
setlocal enabledelayedexpansion
title RescueNet - 3-Node Single Laptop Local Simulation

cd /d "%~dp0"

echo ===============================================================================
echo   RESCUENET - 3-NODE LOCAL TEST LAUNCHER (SINGLE LAPTOP)
echo   Spawns Alpha (8000), Beta (8080), and Gamma (8090) simultaneously
echo ===============================================================================
echo.

set PYTHON_CMD=python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    where py >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set PYTHON_CMD=py -3
    ) else (
        echo [ERROR] Python 3 was not found in PATH!
        pause
        exit /b 1
    )
)

echo Starting Node Alpha (Port 8000, TCP 18001)...
start "RescueNet - Alpha Harbor" %PYTHON_CMD% -m api.node_server --node-id alpha-harbor --host 127.0.0.1 --tcp-port 18001 --web-port 8000 --peers beta-hospital=127.0.0.1:18002,gamma-mountain=127.0.0.1:18003 --no-discovery --strict-security

timeout /t 2 /nobreak >nul

echo Starting Node Beta (Port 8080, TCP 18002)...
start "RescueNet - Beta Hospital" %PYTHON_CMD% -m api.node_server --node-id beta-hospital --host 127.0.0.1 --tcp-port 18002 --web-port 8080 --peers alpha-harbor=127.0.0.1:18001,gamma-mountain=127.0.0.1:18003 --no-discovery --strict-security

timeout /t 2 /nobreak >nul

echo Starting Node Gamma (Port 8090, TCP 18003)...
start "RescueNet - Gamma Mountain" %PYTHON_CMD% -m api.node_server --node-id gamma-mountain --host 127.0.0.1 --tcp-port 18003 --web-port 8090 --peers alpha-harbor=127.0.0.1:18001,beta-hospital=127.0.0.1:18002 --no-discovery --strict-security

timeout /t 2 /nobreak >nul

echo.
echo All 3 Nodes are running!
echo Opening browser to Alpha Harbor (http://localhost:8000/)...
start http://localhost:8000/
start http://localhost:8080/
start http://localhost:8090/

echo.
echo Press any key to stop all 3 nodes...
pause >nul

taskkill /FI "WINDOWTITLE eq RescueNet - Alpha Harbor*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq RescueNet - Beta Hospital*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq RescueNet - Gamma Mountain*" /F >nul 2>&1
echo Done.
