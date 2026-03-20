"""
Application settings management using Pydantic.
"""

from pathlib import Path
from typing import Optional
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    host: str = "localhost"
    port: int = 3306
    username: str = "calsystem"
    password: str = ""
    database: str = "calsystem"

    @property
    def connection_string(self) -> str:
        """Get SQLAlchemy connection string."""
        return f"mysql+mysqlconnector://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class InstrumentSettings(BaseSettings):
    """Instrument communication settings."""

    visa_backend: str = "@ni"  # Use NI-VISA backend
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
    config_dir: Path = Field(default_factory=lambda: Path.home() / ".calsystem")
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".calsystem" / "data")
    log_dir: Path = Field(default_factory=lambda: Path.home() / ".calsystem" / "logs")

    # User info
    technician_name: str = ""
    technician_id: str = ""

    # Workstation
    workstation_name: str = ""

    def __init__(self, **kwargs):
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
