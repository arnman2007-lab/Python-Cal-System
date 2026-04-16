"""
Version management for Calsystem.

Handles version calculation, publishing, and changelog management.
"""

import re
from typing import Optional, List, Tuple
from datetime import datetime
from loguru import logger

from calsystem.database.connection import get_db
from calsystem.database.models import ChangelogEntry


def parse_version(version_str: str) -> Tuple[int, int, int]:
    """Parse a semantic version string into (major, minor, patch)."""
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)', version_str or "0.0.0")
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    return 0, 0, 0


def format_version(major: int, minor: int, patch: int) -> str:
    """Format version tuple as string."""
    return f"{major}.{minor}.{patch}"


def get_latest_published_version() -> str:
    """Get the latest published version from the changelog."""
    db = get_db()
    if not db.is_connected:
        return "0.0.0"

    try:
        with db.session() as session:
            # Get all published versions and find the highest
            entries = session.query(ChangelogEntry.version).filter(
                ChangelogEntry.is_published == True,
                ChangelogEntry.version.isnot(None)
            ).distinct().all()

            if not entries:
                return "0.0.0"

            # Parse and find max version
            versions = [parse_version(e.version) for e in entries if e.version]
            if not versions:
                return "0.0.0"

            max_version = max(versions)
            return format_version(*max_version)

    except Exception as e:
        logger.error(f"Failed to get latest version: {e}")
        return "0.0.0"


def get_current_version() -> str:
    """Get the current application version (latest published)."""
    return get_latest_published_version()


def get_unpublished_changes() -> List[ChangelogEntry]:
    """Get all unpublished changelog entries."""
    db = get_db()
    if not db.is_connected:
        return []

    try:
        with db.session() as session:
            entries = session.query(ChangelogEntry).filter(
                ChangelogEntry.is_published == False
            ).order_by(ChangelogEntry.timestamp.desc()).all()

            # Detach from session
            result = []
            for e in entries:
                result.append({
                    "id": e.id,
                    "change_type": e.change_type,
                    "category": e.category,
                    "description": e.description,
                    "author": e.author,
                    "timestamp": e.timestamp,
                })
            return result

    except Exception as e:
        logger.error(f"Failed to get unpublished changes: {e}")
        return []


def calculate_next_version(unpublished_changes: List[dict] = None) -> str:
    """
    Calculate the next version based on unpublished changes.

    Rules:
    - Breaking Change -> bump major (1.0.0 -> 2.0.0)
    - Feature -> bump minor (1.0.0 -> 1.1.0)
    - Fix/Improvement -> bump patch (1.0.0 -> 1.0.1)
    """
    if unpublished_changes is None:
        unpublished_changes = get_unpublished_changes()

    if not unpublished_changes:
        return get_latest_published_version()

    current = get_latest_published_version()
    major, minor, patch = parse_version(current)

    # Determine bump type based on change types
    change_types = [c.get("change_type", "") for c in unpublished_changes]

    if "Breaking Change" in change_types:
        major += 1
        minor = 0
        patch = 0
    elif "Feature" in change_types:
        minor += 1
        patch = 0
    else:
        patch += 1

    return format_version(major, minor, patch)


def publish_version(new_version: str = None) -> Tuple[bool, str]:
    """
    Publish all unpublished changelog entries with the new version.

    Args:
        new_version: Version to assign. If None, auto-calculates.

    Returns:
        Tuple of (success, message)
    """
    db = get_db()
    if not db.is_connected:
        return False, "Database not connected"

    try:
        unpublished = get_unpublished_changes()
        if not unpublished:
            return False, "No unpublished changes to publish"

        if new_version is None:
            new_version = calculate_next_version(unpublished)

        with db.session() as session:
            # Update all unpublished entries
            count = session.query(ChangelogEntry).filter(
                ChangelogEntry.is_published == False
            ).update({
                "version": new_version,
                "is_published": True
            })

            session.commit()

        logger.info(f"Published version {new_version} with {count} changelog entries")
        return True, f"Published version {new_version} with {count} changes"

    except Exception as e:
        logger.error(f"Failed to publish version: {e}")
        return False, str(e)


def add_changelog_entry(
    change_type: str,
    category: str,
    description: str,
    author: str = "User"
) -> bool:
    """
    Add an unpublished changelog entry.

    Args:
        change_type: Feature, Fix, Improvement, or Breaking Change
        category: Standards, DUTs, Procedures, etc.
        description: What changed
        author: Who made the change

    Returns:
        True if successful
    """
    db = get_db()
    if not db.is_connected:
        return False

    try:
        with db.session() as session:
            entry = ChangelogEntry(
                version=None,  # Unpublished
                timestamp=datetime.now(),
                change_type=change_type,
                category=category,
                description=description,
                author=author,
                is_published=False,
            )
            session.add(entry)
            session.commit()

        logger.info(f"Added changelog entry: [{change_type}] {description}")
        return True

    except Exception as e:
        logger.error(f"Failed to add changelog entry: {e}")
        return False


def get_changelog_for_version(version: str) -> List[dict]:
    """Get all changelog entries for a specific version."""
    db = get_db()
    if not db.is_connected:
        return []

    try:
        with db.session() as session:
            entries = session.query(ChangelogEntry).filter(
                ChangelogEntry.version == version,
                ChangelogEntry.is_published == True
            ).order_by(ChangelogEntry.change_type, ChangelogEntry.category).all()

            result = []
            for e in entries:
                result.append({
                    "change_type": e.change_type,
                    "category": e.category,
                    "description": e.description,
                    "author": e.author,
                })
            return result

    except Exception as e:
        logger.error(f"Failed to get changelog: {e}")
        return []
