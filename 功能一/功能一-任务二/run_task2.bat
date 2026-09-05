@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_task2.ps1"
if errorlevel 1 (
    echo.
    echo Run failed. Review the error message above.
    pause
    exit /b 1
)
echo.
echo Run completed. Output files are in the results folder.
pause
