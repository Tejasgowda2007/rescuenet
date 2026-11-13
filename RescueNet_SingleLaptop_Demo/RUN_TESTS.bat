@echo off
setlocal
cd /d "%~dp0"
title RESCUENET FIELDMESH -- AUTOMATED TEST SUITE RUNNER
color 0A
cls
echo ==============================================================================
echo   RESCUENET FIELDMESH -- PORTABLE AUTOMATED TEST RUNNER
echo ==============================================================================
echo.
echo Executing all 75 automated unit and integration tests across crypto,
echo storage, sync, allocation, and 3D fieldmesh modules...
echo.
"%~dp0runtime\python.exe" -m pytest "%~dp0tests" -v --tb=short
echo.
echo ==============================================================================
echo   Test run completed. Press any key to close...
echo ==============================================================================
pause
