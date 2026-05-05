@echo off
setlocal
cd /d "%~dp0"

python build_auto_py_to_exe_config.py
if errorlevel 1 (
    pause
    exit /b 1
)

python -m auto_py_to_exe -c "%~dp0auto_py_to_exe_config.json"
