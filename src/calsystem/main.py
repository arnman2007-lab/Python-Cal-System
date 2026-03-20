"""
Main entry point for Calsystem application.
"""

import sys
from pathlib import Path

from loguru import logger

# Configure logging before importing other modules
LOG_DIR = Path.home() / ".calsystem" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger.add(
    LOG_DIR / "calsystem_{time}.log",
    rotation="10 MB",
    retention="30 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
)


def main():
    """Main entry point for the application."""
    logger.info("Starting Calsystem application")

    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt

        from calsystem.app import CalsystemApp
        from calsystem.config.settings import get_settings

        # Create Qt application
        app = QApplication(sys.argv)
        app.setApplicationName("Calsystem")
        app.setApplicationVersion("0.1.0")
        app.setOrganizationName("Calibration Lab")

        # Load settings
        settings = get_settings()
        logger.info(f"Loaded settings from {settings.config_dir}")

        # Create and show main window
        window = CalsystemApp()
        window.show()

        logger.info("Application window displayed")

        # Run event loop
        exit_code = app.exec()

        logger.info(f"Application exiting with code {exit_code}")
        sys.exit(exit_code)

    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
