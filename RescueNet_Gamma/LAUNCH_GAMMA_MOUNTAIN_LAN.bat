@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title RescueNet Station GAMMA-MOUNTAIN -- Mountain Shelter Relay (LAN)
color 5F
cls
echo ==============================================================================
echo   RESCUENET STATION: GAMMA-MOUNTAIN (Mountain Shelter Relay)
echo   TCP Port: 8003 | Strict Zero-Trust Enforced
echo   Security: Physical Private Key Isolated (Station gamma-mountain Only)
echo ==============================================================================
echo.

set PEER_ARG=alpha-harbor=192.168.1.10:8001,beta-hospital=192.168.1.20:8002

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
echo Starting station on interface 0.0.0.0:8003...
echo Connecting to peers: !PEER_ARG!
echo.
"%~dp0runtime\python.exe" "%~dp0src\run_node.py" --id gamma-mountain --host 0.0.0.0 --port 8003 --peers !PEER_ARG! --db "%~dp0data\gamma-mountain.db" --key-dir "%~dp0security" --strict-security
pause
