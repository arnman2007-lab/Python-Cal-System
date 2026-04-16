"""
Publish script for Calsystem.

This script:
1. Checks for unpublished changelog entries
2. Calculates the new version number
3. Archives the current version on the network share
4. Builds the new exe
5. Publishes to the network share
6. Marks changelog entries as published
"""

import os
import sys
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

# Add src to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

from calsystem.database.connection import get_db
from calsystem.database.models import ChangelogEntry
from calsystem.updater.version import (
    get_latest_published_version,
    get_unpublished_changes,
    calculate_next_version,
    publish_version,
    get_changelog_for_version,
)


def get_network_path() -> str:
    """Get the network path from config or prompt."""
    config_file = Path.home() / ".calsystem" / "config.json"
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
                path = config.get("update_server_path", "")
                if path:
                    return path
        except:
            pass

    # Prompt for path
    print("\nNo update server path configured.")
    print("Enter the network share path (e.g., \\\\server\\calsystem):")
    path = input("> ").strip()
    return path


def archive_current_version(network_path: str, current_version: str) -> bool:
    """Archive the current version on the network share."""
    if not os.path.exists(network_path):
        print(f"Network path not accessible: {network_path}")
        return False

    archive_dir = os.path.join(network_path, "archive", current_version)

    # Check if already archived
    if os.path.exists(archive_dir):
        print(f"Archive already exists for version {current_version}")
        return True

    try:
        os.makedirs(archive_dir, exist_ok=True)

        # Archive exe
        current_exe = os.path.join(network_path, "Calsystem.exe")
        if os.path.exists(current_exe):
            shutil.copy2(current_exe, os.path.join(archive_dir, "Calsystem.exe"))
            print(f"  Archived exe")

        # Archive diagrams
        current_diagrams = os.path.join(network_path, "diagrams")
        if os.path.exists(current_diagrams):
            shutil.copytree(current_diagrams, os.path.join(archive_dir, "diagrams"))
            print(f"  Archived diagrams")

        # Archive version.json
        current_version_file = os.path.join(network_path, "version.json")
        if os.path.exists(current_version_file):
            shutil.copy2(current_version_file, os.path.join(archive_dir, "version.json"))
            print(f"  Archived version.json")

        print(f"Archived version {current_version} to {archive_dir}")
        return True

    except Exception as e:
        print(f"Failed to archive: {e}")
        return False


def build_exe() -> bool:
    """Run the build script."""
    print("\nBuilding executable...")
    build_script = project_root / "build_onefile.bat"

    if not build_script.exists():
        print(f"Build script not found: {build_script}")
        return False

    try:
        # Run build script
        result = subprocess.run(
            ["cmd", "/c", str(build_script)],
            cwd=str(project_root),
            capture_output=False,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Build failed: {e}")
        return False


def publish_to_network(network_path: str, new_version: str, changelog: list) -> bool:
    """Publish the new version to the network share."""
    try:
        os.makedirs(network_path, exist_ok=True)

        # Copy exe
        dist_exe = project_root / "dist" / "Calsystem.exe"
        if dist_exe.exists():
            dest_exe = os.path.join(network_path, "Calsystem.exe")
            shutil.copy2(dist_exe, dest_exe)
            print(f"  Published exe")
        else:
            print(f"WARNING: Exe not found at {dist_exe}")

        # Copy diagrams
        resource_diagrams = project_root / "resources" / "diagrams"
        if resource_diagrams.exists() and any(resource_diagrams.iterdir()):
            dest_diagrams = os.path.join(network_path, "diagrams")
            if os.path.exists(dest_diagrams):
                shutil.rmtree(dest_diagrams)
            shutil.copytree(resource_diagrams, dest_diagrams)
            print(f"  Published diagrams")

        # Create version.json
        version_info = {
            "version": new_version,
            "published_at": datetime.now().isoformat(),
            "changelog": changelog,
        }
        version_file = os.path.join(network_path, "version.json")
        with open(version_file, 'w') as f:
            json.dump(version_info, f, indent=2)
        print(f"  Published version.json")

        return True

    except Exception as e:
        print(f"Failed to publish: {e}")
        return False


def main():
    print("=" * 50)
    print("  Calsystem Publish Script")
    print("=" * 50)

    # Initialize and connect to database
    db = get_db()
    if not db.connect():
        print("ERROR: Database not connected")
        print("Check your database settings in ~/.calsystem/config.json")
        sys.exit(1)

    print(f"Database connected")

    # Get current version and unpublished changes
    current_version = get_latest_published_version()
    unpublished = get_unpublished_changes()

    print(f"\nCurrent published version: {current_version}")
    print(f"Unpublished changes: {len(unpublished)}")

    if not unpublished:
        print("\nNo unpublished changes found!")
        print("Add changelog entries before publishing.")
        sys.exit(1)

    # Calculate new version
    new_version = calculate_next_version(unpublished)
    print(f"New version will be: {new_version}")

    # Show changes
    print("\nChanges to be published:")
    print("-" * 40)
    for change in unpublished:
        print(f"  [{change['change_type']}] {change['category']}: {change['description']}")
    print("-" * 40)

    # Get network path
    network_path = get_network_path()
    if not network_path:
        print("No network path provided. Exiting.")
        sys.exit(1)

    # Confirm
    print(f"\nThis will:")
    print(f"  1. Archive current version ({current_version}) to {network_path}\\archive\\")
    print(f"  2. Build new exe")
    print(f"  3. Publish version {new_version} to {network_path}")
    print(f"  4. Mark {len(unpublished)} changelog entries as published")
    print()

    confirm = input("Continue? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        sys.exit(0)

    # Step 1: Archive current version
    print(f"\n[1/4] Archiving version {current_version}...")
    if current_version != "0.0.0":
        archive_current_version(network_path, current_version)

    # Step 2: Build exe
    print(f"\n[2/4] Building executable...")
    if not build_exe():
        print("Build failed! Aborting publish.")
        sys.exit(1)

    # Step 3: Publish to network
    print(f"\n[3/4] Publishing to network...")
    changelog = [
        {"type": c['change_type'], "category": c['category'], "description": c['description']}
        for c in unpublished
    ]
    if not publish_to_network(network_path, new_version, changelog):
        print("Publish failed!")
        sys.exit(1)

    # Step 4: Mark as published in database
    print(f"\n[4/4] Marking changelog entries as published...")
    success, msg = publish_version(new_version)
    if success:
        print(f"  {msg}")
    else:
        print(f"  WARNING: {msg}")

    print("\n" + "=" * 50)
    print(f"  Version {new_version} published successfully!")
    print("=" * 50)
    print(f"\nTechnicians will see the update when they:")
    print(f"  1. Have access to {network_path}")
    print(f"  2. Open Calsystem")


if __name__ == "__main__":
    main()
