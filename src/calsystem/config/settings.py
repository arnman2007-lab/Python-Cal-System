"""
Application settings management using Pydantic.
"""

import json
from pathlib import Path
from typing import Any, Optional
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from loguru import logger


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    # Database type: "sqlite" (default, file-based) or "mysql" (server-based)
    db_type: str = "sqlite"

    # SQLite settings
    sqlite_path: Optional[str] = None  # None = use default in config_dir

    # MySQL settings (only used if db_type="mysql")
    host: str = "localhost"
    port: int = 3306
    username: str = "calsystem"
    password: str = ""
    database: str = "calsystem"

    def get_connection_string(self, config_dir: Optional[Path] = None) -> str:
        """Get SQLAlchemy connection string."""
        if self.db_type == "sqlite":
            if self.sqlite_path:
                db_path = Path(self.sqlite_path)
            else:
                # Default to config_dir/calsystem.db
                if config_dir is None:
                    config_dir = Path.home() / ".calsystem"
                db_path = config_dir / "calsystem.db"
            return f"sqlite:///{db_path}"
        else:
            return f"mysql+mysqlconnector://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def connection_string(self) -> str:
        """Get SQLAlchemy connection string (for backward compatibility)."""
        return self.get_connection_string()


class InstrumentSettings(BaseSettings):
    """Instrument communication settings."""

    visa_backend: str = ""  # Auto-detect VISA backend (NI-VISA, Keysight, etc.)
    default_timeout_ms: int = 5000
    idn_timeout_ms: int = 2000
    auto_detect_on_startup: bool = False


class OCRSettings(BaseSettings):
    """OCR settings."""

    default_mode: str = "standard"  # "standard" or "seven_segment"
    webcam_device: int = 0
    capture_resolution: tuple[int, int] = (1280, 720)
    tesseract_path: Optional[str] = None


class UISettings(BaseSettings):
    """User interface settings."""

    theme: str = "system"  # "light", "dark", or "system"
    default_input_method: str = "keyboard"  # "keyboard", "remote", or "webcam"
    confirm_on_exit: bool = True
    show_tooltips: bool = True
    high_voltage_blink_speed_ms: int = 500  # Blink speed for high voltage warning


def _get_config_dir() -> Path:
    """Get the config directory path."""
    return Path.home() / ".calsystem"


def _load_config_from_file() -> dict[str, Any]:
    """Load configuration from JSON file if it exists."""
    config_file = _get_config_dir() / "config.json"
    if config_file.exists():
        try:
            return json.loads(config_file.read_text())
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load config file: {e}")
    return {}


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="CALSYSTEM_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Nested settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    instruments: InstrumentSettings = Field(default_factory=InstrumentSettings)
    ocr: OCRSettings = Field(default_factory=OCRSettings)
    ui: UISettings = Field(default_factory=UISettings)

    # Application paths
    config_dir: Path = Field(default_factory=_get_config_dir)
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".calsystem" / "data")
    log_dir: Path = Field(default_factory=lambda: Path.home() / ".calsystem" / "logs")

    # User info
    technician_name: str = ""
    technician_id: str = ""

    # Workstation
    workstation_name: str = ""

    def __init__(self, **kwargs):
        # Load config from file first
        file_config = _load_config_from_file()

        # Merge file config with any provided kwargs
        # File config has lower priority than explicit kwargs
        if "database" not in kwargs and "database" in file_config:
            kwargs["database"] = DatabaseSettings(**file_config["database"])
        if "instruments" not in kwargs and "instruments" in file_config:
            kwargs["instruments"] = InstrumentSettings(**file_config["instruments"])
        if "ocr" not in kwargs and "ocr" in file_config:
            kwargs["ocr"] = OCRSettings(**file_config["ocr"])
        if "ui" not in kwargs and "ui" in file_config:
            kwargs["ui"] = UISettings(**file_config["ui"])

        # Load top-level settings from file
        for key in ["technician_name", "technician_id", "workstation_name"]:
            if key not in kwargs and key in file_config:
                kwargs[key] = file_config[key]

        super().__init__(**kwargs)
        # Ensure directories exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


def reload_settings() -> Settings:
    """Reload settings (clears cache)."""
    get_settings.cache_clear()
    return get_settings()


def save_settings(settings: Settings) -> bool:
    """Save settings to config.json file."""
    config_file = _get_config_dir() / "config.json"
    try:
        # Build config dict
        config = {
            "database": {
                "db_type": settings.database.db_type,
                "sqlite_path": settings.database.sqlite_path,
                "host": settings.database.host,
                "port": settings.database.port,
                "username": settings.database.username,
                "password": settings.database.password,
                "database": settings.database.database,
            },
            "instruments": {
                "visa_backend": settings.instruments.visa_backend,
                "default_timeout_ms": settings.instruments.default_timeout_ms,
                "idn_timeout_ms": settings.instruments.idn_timeout_ms,
                "auto_detect_on_startup": settings.instruments.auto_detect_on_startup,
            },
            "ocr": {
                "default_mode": settings.ocr.default_mode,
                "webcam_device": settings.ocr.webcam_device,
                "capture_resolution": list(settings.ocr.capture_resolution),
                "tesseract_path": settings.ocr.tesseract_path,
            },
            "ui": {
                "theme": settings.ui.theme,
                "default_input_method": settings.ui.default_input_method,
                "confirm_on_exit": settings.ui.confirm_on_exit,
                "show_tooltips": settings.ui.show_tooltips,
                "high_voltage_blink_speed_ms": settings.ui.high_voltage_blink_speed_ms,
            },
            "technician_name": settings.technician_name,
            "technician_id": settings.technician_id,
            "workstation_name": settings.workstation_name,
        }

        config_file.write_text(json.dumps(config, indent=2))
        logger.info(f"Settings saved to {config_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return False
