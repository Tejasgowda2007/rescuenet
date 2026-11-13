@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title RescueNet Station ALPHA-HARBOR -- Harbor Base Command (LAN)
color 1F
cls
echo ==============================================================================
echo   RESCUENET STATION: ALPHA-HARBOR (Harbor Base Command)
echo   TCP Port: 8001 | Strict Zero-Trust Enforced
echo   Security: Physical Private Key Isolated (Station alpha-harbor Only)
echo ==============================================================================
echo.

set PEER_ARG=beta-hospital=192.168.1.20:8002,gamma-mountain=192.168.1.30:8003

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
echo Starting station on interface 0.0.0.0:8001...
echo Connecting to peers: !PEER_ARG!
echo.
"%~dp0runtime\python.exe" "%~dp0src\run_node.py" --id alpha-harbor --host 0.0.0.0 --port 8001 --peers !PEER_ARG! --db "%~dp0data\alpha-harbor.db" --key-dir "%~dp0security" --strict-security
pause
