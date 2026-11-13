@echo off
setlocal
cd /d "%~dp0"
title RESCUENET FIELDMESH -- AUTOMATED 3-NODE MESH DEMO
color 0B
cls
echo ==============================================================================
echo   RESCUENET FIELDMESH -- PORTABLE EVALUATOR AUTOMATED DEMO
echo   Tagline: "When infrastructure fails, coordination survives."
echo ==============================================================================
echo.
echo Running 3-node real TCP mesh convergence demonstration with strict security...
echo.
"%~dp0runtime\python.exe" "%~dp0src\scripts\demo_evaluator.py"
echo.
echo ==============================================================================
echo   Demonstration completed. Press any key to close...
echo ==============================================================================
pause
