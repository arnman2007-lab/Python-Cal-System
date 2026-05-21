"""
Database migration script to add pass_fail_image column.
Run this before using the new exe if you have existing data.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from calsystem.database.connection import get_db
from sqlalchemy import text

def migrate():
    """Add pass_fail_image column if it doesn't exist."""
    db = get_db()

    if not db.connect():
        print("ERROR: Could not connect to database")
        return False

    try:
        with db.session() as session:
            # Check if column exists
            result = session.execute(text(
                "SELECT COUNT(*) FROM pragma_table_info('test_points') WHERE name='pass_fail_image'"
            )).scalar()

            if result == 0:
                # Column doesn't exist, add it
                print("Adding pass_fail_image column to test_points table...")
                session.execute(text(
                    "ALTER TABLE test_points ADD COLUMN pass_fail_image VARCHAR(255)"
                ))
                session.commit()
                print("✓ Migration complete!")
            else:
                print("✓ pass_fail_image column already exists")

        return True

    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Calsystem Database Migration")
    print("=" * 60)
    print()

    db_path = os.path.expanduser("~/.calsystem/calsystem.db")
    if os.name == 'nt':  # Windows
        db_path = os.path.expanduser("~\\.calsystem\\calsystem.db")

    print(f"Database location: {db_path}")

    if not os.path.exists(db_path):
        print(f"WARNING: Database not found at {db_path}")
        print("The application will create a new database on first run.")
    else:
        print(f"Database found ({os.path.getsize(db_path)} bytes)")

    print()

    if migrate():
        print()
        print("Migration successful! You can now run the application.")
    else:
        print()
        print("Migration failed. Please check the error above.")
        sys.exit(1)
