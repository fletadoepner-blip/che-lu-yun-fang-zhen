@echo off
setlocal
cd /d "%~dp0"
if "%PYTHON_EXE%"=="" if exist "C:\Users\lauri\anaconda3\envs\project1\python.exe" set "PYTHON_EXE=C:\Users\lauri\anaconda3\envs\project1\python.exe"
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=python"
"%PYTHON_EXE%" "%~dp0run_experiment.py" --mode adaptive --gui --duration 7200
pause
