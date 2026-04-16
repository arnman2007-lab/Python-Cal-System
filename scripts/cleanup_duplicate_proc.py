"""Clean up duplicate procedure entry created during testing."""

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
    print("  Cleanup Duplicate Procedure")
    print("=" * 50)

    db = get_db()
    if not db.connect():
        print("ERROR: Could not connect to database")
        return

    print("Database connected")

    with db.session() as session:
        # Delete the duplicate entry (ID 3) that was created by sync
        session.execute(text("DELETE FROM procedures WHERE id = 3"))

        # Update the original procedure (ID 2) with the file path
        csp_path = str(Path.home() / ".calsystem" / "procedures" / "789_Fluke__Processmeter_v1.0.csp")
        session.execute(text(
            "UPDATE procedures SET file_path = :path, section_count = 12, test_point_count = 54 WHERE id = 2"
        ), {"path": csp_path})

        session.commit()
        print("Cleaned up duplicate and updated original procedure")

    # Verify
    with db.session() as session:
        result = session.execute(text("SELECT id, name, file_path, section_count FROM procedures"))
        print("\nProcedures after cleanup:")
        for row in result:
            print(f"  [{row[0]}] {row[1]} - path: {row[2]}, sections: {row[3]}")

    print("\nDone!")


if __name__ == "__main__":
    main()
