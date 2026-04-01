# Building Calsystem for Windows

This guide explains how to create a standalone Windows executable.

## Prerequisites

1. **Python 3.10 or newer** - Download from https://python.org
   - During installation, check "Add Python to PATH"

2. **NI-VISA Runtime** (optional) - For GPIB/serial instrument communication
   - Download from National Instruments website
   - PyVISA-py (pure Python) works for basic TCP/IP instruments without NI-VISA

3. **Tesseract OCR** (optional) - For webcam OCR feature
   - Download from https://github.com/UB-Mannheim/tesseract/wiki
   - Install to default location or set TESSERACT_CMD environment variable

## Quick Build (Single File)

1. Open Command Prompt in the project folder
2. Run:
   ```
   build_onefile.bat
   ```
3. Wait 5-10 minutes for the build
4. Find `Calsystem.exe` in the `dist` folder

**Pros:** Single file, easy to copy
**Cons:** Larger file (~150-200MB), slower startup (unpacks to temp)

## Full Build (Folder)

1. Open Command Prompt in the project folder
2. Run:
   ```
   build.bat
   ```
3. Find `Calsystem.exe` in `dist\Calsystem\` folder

**Pros:** Faster startup, smaller individual files
**Cons:** Must copy entire folder to distribute

## Distribution

### Single-File Build
Copy `dist\Calsystem.exe` to the target machine. That's it!

### Folder Build
Copy the entire `dist\Calsystem\` folder to the target machine.

## First Run Setup

On first run, Calsystem will:
1. Create `~/.calsystem/` folder for settings and logs
2. Use SQLite database by default (no MySQL needed for testing)
3. Show the main window with all tabs

To configure MySQL:
1. Go to File > Settings
2. Enter your MySQL connection details
3. Click "Test Connection"
4. Click "Save"

## Troubleshooting

### "Python is not installed" error
- Install Python from https://python.org
- Make sure to check "Add Python to PATH" during installation
- Restart Command Prompt after installation

### Build fails with import errors
- Delete the `build_venv` folder and try again
- Check that all dependencies in `requirements-build.txt` are available

### Antivirus blocks the .exe
- PyInstaller executables are sometimes flagged as false positives
- Add an exception for the dist folder or the .exe file

### VISA instruments not found
- Install NI-VISA Runtime on the target machine
- Make sure instruments are connected and powered on
- Check instrument addresses with NI MAX or similar tool

### OCR not working
- Install Tesseract OCR
- Set TESSERACT_CMD environment variable if not in default location

## Files Created by Build

```
Calsystem/
├── build/              # Temporary build files (can delete)
├── dist/               # Output executables
│   ├── Calsystem.exe   # Single-file build
│   └── Calsystem/      # Folder build
│       ├── Calsystem.exe
│       └── ... (DLLs and data)
├── build_venv/         # Build virtual environment (can delete after build)
├── build.bat           # Folder build script
├── build_onefile.bat   # Single-file build script
├── calsystem.spec      # PyInstaller configuration
└── requirements-build.txt
```

## Updating the Build

After making code changes:
1. Run `build.bat` or `build_onefile.bat` again
2. The old build will be replaced

To do a clean build:
1. Delete `build/` and `dist/` folders
2. Optionally delete `build_venv/` to reinstall dependencies
3. Run the build script
