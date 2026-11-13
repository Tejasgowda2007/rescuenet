@echo off
setlocal
cd /d "%~dp0"
title RescueNet Offline Wi-Fi Distribution Server
color 0E
cls
echo ==============================================================================
echo   RESCUENET OFFLINE WI-FI DISTRIBUTION SERVER (NO USB REQUIRED)
echo ==============================================================================
echo.
echo Starting temporary HTTP server on port 8888...
echo.
echo 1. Verify your local IP address using 'ipconfig' (e.g. 192.168.43.10)
echo.
echo 2. On Laptop BETA, open PowerShell and run:
echo    Invoke-WebRequest -Uri "http://<Alpha-IP>:8888/RescueNet_Beta.zip" -OutFile "RescueNet_Beta.zip"
echo    Expand-Archive -Path "RescueNet_Beta.zip" -DestinationPath "C:\RescueNet"
echo.
echo 3. On Laptop GAMMA, open PowerShell and run:
echo    Invoke-WebRequest -Uri "http://<Alpha-IP>:8888/RescueNet_Gamma.zip" -OutFile "RescueNet_Gamma.zip"
echo    Expand-Archive -Path "RescueNet_Gamma.zip" -DestinationPath "C:\RescueNet"
echo.
echo Press Ctrl+C when all downloads complete to close the distribution server.
echo ==============================================================================
echo.
"%~dp0runtime\python.exe" -m http.server 8888 --bind 0.0.0.0
pause
