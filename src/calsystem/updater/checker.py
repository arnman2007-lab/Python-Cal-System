"""
Update checker for Calsystem.

Checks network share for new versions and handles update process.
"""

import os
import sys
import json
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from loguru import logger

from calsystem.config.settings import get_settings
from calsystem.updater.version import get_current_version, parse_version


@dataclass
class UpdateInfo:
    """Information about an available update."""
    current_version: str
    new_version: str
    changelog: List[dict]
    update_path: str
    exe_path: str
    diagrams_path: str


def get_update_server_path() -> Optional[str]:
    """Get the configured update server path from settings."""
    settings = get_settings()
    return getattr(settings, 'update_server_path', None)


def check_for_updates() -> Optional[UpdateInfo]:
    """
    Check if updates are available on the network share.

    Returns:
        UpdateInfo if update available, None otherwise
    """
    update_path = get_update_server_path()
    if not update_path:
        logger.debug("No update server path configured")
        return None

    # Check if path is accessible
    if not os.path.exists(update_path):
        logger.debug(f"Update server path not accessible: {update_path}")
        return None

    # Look for version.json
    version_file = os.path.join(update_path, "version.json")
    if not os.path.exists(version_file):
        logger.debug(f"No version.json found at {update_path}")
        return None

    try:
        with open(version_file, 'r') as f:
            version_info = json.load(f)

        server_version = version_info.get("version", "0.0.0")
        current_version = get_current_version()

        # Compare versions
        server_parsed = parse_version(server_version)
        current_parsed = parse_version(current_version)

        if server_parsed <= current_parsed:
            logger.debug(f"No update needed: current={current_version}, server={server_version}")
            return None

        # Update available!
        logger.info(f"Update available: {current_version} -> {server_version}")

        exe_path = os.path.join(update_path, "Calsystem.exe")
        diagrams_path = os.path.join(update_path, "diagrams")

        return UpdateInfo(
            current_version=current_version,
            new_version=server_version,
            changelog=version_info.get("changelog", []),
            update_path=update_path,
            exe_path=exe_path if os.path.exists(exe_path) else "",
            diagrams_path=diagrams_path if os.path.exists(diagrams_path) else "",
        )

    except Exception as e:
        logger.error(f"Failed to check for updates: {e}")
        return None


def download_update(update_info: UpdateInfo, progress_callback=None) -> bool:
    """
    Download update files to temp location.

    Args:
        update_info: UpdateInfo from check_for_updates
        progress_callback: Optional callback(percent, message)

    Returns:
        True if successful
    """
    try:
        settings = get_settings()
        temp_dir = settings.data_dir / "update_temp"

        # Clean and create temp dir
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(10, "Preparing update...")

        # Copy exe
        if update_info.exe_path and os.path.exists(update_info.exe_path):
            if progress_callback:
                progress_callback(20, "Copying executable...")
            dest_exe = temp_dir / "Calsystem.exe"
            shutil.copy2(update_info.exe_path, dest_exe)
            logger.info(f"Copied exe to {dest_exe}")

        # Copy diagrams
        if update_info.diagrams_path and os.path.exists(update_info.diagrams_path):
            if progress_callback:
                progress_callback(50, "Copying wiring diagrams...")
            dest_diagrams = temp_dir / "diagrams"
            shutil.copytree(update_info.diagrams_path, dest_diagrams)
            logger.info(f"Copied diagrams to {dest_diagrams}")

        # Copy version.json
        version_file = os.path.join(update_info.update_path, "version.json")
        if os.path.exists(version_file):
            shutil.copy2(version_file, temp_dir / "version.json")

        if progress_callback:
            progress_callback(100, "Download complete!")

        return True

    except Exception as e:
        logger.error(f"Failed to download update: {e}")
        return False


def apply_update() -> bool:
    """
    Apply downloaded update.

    This creates a batch script that will:
    1. Wait for the app to close
    2. Replace the exe
    3. Copy diagrams to resources folder
    4. Restart the app

    Returns:
        True if update script created successfully
    """
    try:
        settings = get_settings()
        temp_dir = settings.data_dir / "update_temp"

        if not temp_dir.exists():
            logger.error("No update downloaded")
            return False

        # Get current exe path
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
        else:
            logger.warning("Cannot apply update when running from source")
            return False

        current_dir = os.path.dirname(current_exe)

        # Create updater batch script
        updater_script = temp_dir / "updater.bat"
        new_exe = temp_dir / "Calsystem.exe"
        new_diagrams = temp_dir / "diagrams"

        script_content = f'''@echo off
echo Calsystem Updater
echo =================
echo.
echo Waiting for application to close...
timeout /t 2 /nobreak >nul

:waitloop
tasklist /FI "IMAGENAME eq Calsystem.exe" 2>NUL | find /I /N "Calsystem.exe">NUL
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >nul
    goto waitloop
)

echo Application closed. Applying update...

if exist "{new_exe}" (
    echo Updating executable...
    copy /Y "{new_exe}" "{current_exe}"
)

if exist "{new_diagrams}" (
    echo Updating wiring diagrams...
    xcopy /E /Y /I "{new_diagrams}" "{current_dir}\\resources\\diagrams"
)

echo.
echo Update complete! Starting application...
timeout /t 2 /nobreak >nul
start "" "{current_exe}"

echo Cleaning up...
rmdir /S /Q "{temp_dir}"
exit
'''

        with open(updater_script, 'w') as f:
            f.write(script_content)

        logger.info(f"Created updater script: {updater_script}")

        # Run the updater script (it will wait for us to close)
        os.startfile(str(updater_script))

        return True

    except Exception as e:
        logger.error(f"Failed to apply update: {e}")
        return False
