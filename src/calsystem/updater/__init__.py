"""
Calsystem auto-update system.

Handles version management, network update checks, and automatic updates.
"""

from .version import (
    get_current_version,
    get_latest_published_version,
    calculate_next_version,
    get_unpublished_changes,
    publish_version,
)
from .checker import check_for_updates, UpdateInfo

__all__ = [
    "get_current_version",
    "get_latest_published_version",
    "calculate_next_version",
    "get_unpublished_changes",
    "publish_version",
    "check_for_updates",
    "UpdateInfo",
]
