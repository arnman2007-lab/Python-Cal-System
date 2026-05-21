"""
Script to add changelog entry for Line Terminator feature.
Run this once after starting the app to add the changelog entry.
Delete this file after running.
"""
import sys
sys.path.insert(0, 'src')

from calsystem.database.connection import get_db
from calsystem.database.models import ChangelogEntry
from datetime import datetime

def add_changelog():
    db = get_db()
    if not db.is_connected:
        print("Database not connected!")
        return False

    try:
        with db.session() as session:
            # Check if entry already exists
            existing = session.query(ChangelogEntry).filter(
                ChangelogEntry.version == "0.10.0"
            ).first()

            if existing:
                print("Changelog entry for 0.10.0 already exists")
                return True

            entry = ChangelogEntry(
                version="0.10.0",
                timestamp=datetime.now(),
                change_type="Feature",
                category="Remote",
                description="Added configurable line terminator for DUT command banks. Fixes issue where Fluke 789 and similar devices respond with extra '1' when sent CR+LF instead of CR only.",
                author="Claude",
            )
            session.add(entry)
            session.commit()
            print("Added changelog entry for v0.10.0 - Line Terminator feature")
            return True

    except Exception as e:
        print(f"Error adding changelog: {e}")
        return False

if __name__ == "__main__":
    add_changelog()
