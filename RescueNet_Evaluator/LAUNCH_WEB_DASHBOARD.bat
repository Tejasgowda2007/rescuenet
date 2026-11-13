@echo off
setlocal
cd /d "%~dp0"
title RescueNet FieldMesh -- 3D Digital Twin Command Center (Port 8000)
color 0E
cls
echo ==============================================================================
echo   RESCUENET FIELDMESH -- 3D DIGITAL TWIN COMMAND CENTER
echo   Mounting 50km x 50km Himalayan Simulation & Live WebSocket Telemetry
echo ==============================================================================
echo.
echo Opening default web browser to http://localhost:8000 ...
start http://localhost:8000
echo Starting FastAPI + Uvicorn server on port 8000...
echo.
"%~dp0runtime\python.exe" "%~dp0src\run_fieldmesh.py" --port 8000 --host 0.0.0.0
pause
