"""Add CSP file support columns to procedures table."""

import sys
from pathlib import Path

# Add src to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import text
from calsystem.database.connection import get_db


def main():
    print("=" * 50)
    print("  Add CSP Columns to Procedures Table")
    print("=" * 50)

    db = get_db()
    if not db.connect():
        print("ERROR: Could not connect to database")
        return

    print("Database connected")

    # Columns to add
    columns = [
        ("file_path", "VARCHAR(500)"),
        ("section_count", "INTEGER"),
        ("test_point_count", "INTEGER"),
        ("file_hash", "VARCHAR(64)"),
    ]

    with db.session() as session:
        for col_name, col_type in columns:
            try:
                session.execute(
                    text(f"ALTER TABLE procedures ADD COLUMN {col_name} {col_type}")
                )
                print(f"Added column: {col_name}")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    print(f"Column already exists: {col_name}")
                else:
                    print(f"Warning adding {col_name}: {e}")
        session.commit()

    print("\nDone!")


if __name__ == "__main__":
    main()
