@echo off
REM ============================================================
REM Calsystem Publish Script
REM Publishes a new version to the network share
REM ============================================================

setlocal enabledelayedexpansion

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Set paths
set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%build_venv"

REM Use build venv if it exists
if exist "%VENV_DIR%\Scripts\activate.bat" (
    call "%VENV_DIR%\Scripts\activate.bat"
)

REM Run the publish script
python "%SCRIPT_DIR%scripts\publish.py"

if exist "%VENV_DIR%\Scripts\deactivate.bat" (
    call deactivate
)

pause
