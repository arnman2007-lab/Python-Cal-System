@echo off
REM ============================================================
REM Calsystem Single-File Build Script for Windows
REM Creates a single .exe file (larger but easier to distribute)
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   Calsystem Single-File Build
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

REM Set paths
set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%build_venv"

REM Create venv if it doesn't exist
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv "%VENV_DIR%"
    call "%VENV_DIR%\Scripts\activate.bat"
    python -m pip install --upgrade pip
    pip install -r "%SCRIPT_DIR%requirements-build.txt"
    pip install -e "%SCRIPT_DIR%"
) else (
    call "%VENV_DIR%\Scripts\activate.bat"
)

echo.
echo Building single-file executable...
echo This may take several minutes...
echo.

pyinstaller --onefile --windowed ^
    --name "Calsystem" ^
    --add-data "resources;resources" ^
    --hidden-import "pyvisa_py" ^
    --hidden-import "mysql.connector" ^
    --hidden-import "sqlalchemy.sql.default_comparator" ^
    --hidden-import "pydantic" ^
    --hidden-import "pydantic_settings" ^
    --hidden-import "cv2" ^
    --hidden-import "PIL" ^
    --hidden-import "openpyxl" ^
    --hidden-import "reportlab" ^
    --hidden-import "loguru" ^
    --exclude-module "tkinter" ^
    --exclude-module "matplotlib" ^
    --paths "src" ^
    "src\calsystem\main.py"

call deactivate

if exist "dist\Calsystem.exe" (
    echo.
    echo ========================================
    echo   Build Complete!
    echo ========================================
    echo.
    echo Single executable created at:
    echo   %SCRIPT_DIR%dist\Calsystem.exe
    echo.
    echo File size:
    for %%A in ("dist\Calsystem.exe") do echo   %%~zA bytes
    echo.
    echo You can copy this single file anywhere and run it!
    echo.
) else (
    echo.
    echo ERROR: Build failed - executable not created
    echo Check the output above for errors
    echo.
)

pause
