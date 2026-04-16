@echo off
REM ============================================================
REM Calsystem Build Script for Windows
REM Creates a standalone executable with all dependencies
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Calsystem Build Script
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM Get Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo Found Python %PYVER%

REM Set paths
set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%build_venv"
set "DIST_DIR=%SCRIPT_DIR%dist"

REM Clean previous build
if exist "%VENV_DIR%" (
    echo Removing old build environment...
    rmdir /s /q "%VENV_DIR%"
)

REM Create virtual environment
echo.
echo [1/5] Creating virtual environment...
python -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

REM Activate virtual environment
call "%VENV_DIR%\Scripts\activate.bat"

REM Upgrade pip
echo.
echo [2/5] Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo.
echo [3/5] Installing dependencies...
pip install -r "%SCRIPT_DIR%requirements-build.txt"
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

REM Install the package itself
echo.
echo [4/5] Installing Calsystem package...
pip install -e "%SCRIPT_DIR%."
if errorlevel 1 (
    echo ERROR: Failed to install Calsystem package
    pause
    exit /b 1
)

REM Build with PyInstaller
echo.
echo [5/5] Building executable with PyInstaller...
pyinstaller --clean --noconfirm "%SCRIPT_DIR%calsystem.spec"
if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    pause
    exit /b 1
)

REM Deactivate virtual environment
call deactivate

echo.
echo ========================================
echo   Build Complete!
echo ========================================
echo.
echo Executable created at:
echo   %DIST_DIR%\Calsystem\Calsystem.exe
echo.
echo To distribute, copy the entire 'Calsystem' folder from:
echo   %DIST_DIR%\Calsystem\
echo.
echo Or create a single-file executable by editing calsystem.spec
echo and setting onefile=True (larger file, slower startup)
echo.

pause
