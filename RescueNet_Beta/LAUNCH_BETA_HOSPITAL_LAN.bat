@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title RescueNet Station BETA-HOSPITAL -- Field Hospital Triage (LAN)
color 2F
cls
echo ==============================================================================
echo   RESCUENET STATION: BETA-HOSPITAL (Field Hospital Triage)
echo   TCP Port: 8002 | Strict Zero-Trust Enforced
echo   Security: Physical Private Key Isolated (Station beta-hospital Only)
echo ==============================================================================
echo.

set PEER_ARG=alpha-harbor=192.168.1.10:8001,gamma-mountain=192.168.1.30:8003

if exist "peer_ips.txt" (
    echo [OK] Reading custom peer configuration from peer_ips.txt...
    set /p PEER_ARG=<peer_ips.txt
) else (
    echo Default Peer Configuration: !PEER_ARG!
    echo To change, enter custom peer string or press Enter to accept:
    set /p USER_PEER="Peers [default: !PEER_ARG!]: "
    if not "!USER_PEER!"=="" set PEER_ARG=!USER_PEER!
)

echo.
echo Starting station on interface 0.0.0.0:8002...
echo Connecting to peers: !PEER_ARG!
echo.
"%~dp0runtime\python.exe" "%~dp0src\run_node.py" --id beta-hospital --host 0.0.0.0 --port 8002 --peers !PEER_ARG! --db "%~dp0data\beta-hospital.db" --key-dir "%~dp0security" --strict-security
pause
