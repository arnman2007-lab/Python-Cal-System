"""Fix CSP file paths to use Windows paths."""

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
    print("  Fix CSP Paths for Windows")
    print("=" * 50)

    db = get_db()
    if not db.connect():
        print("ERROR: Could not connect to database")
        return

    print("Database connected")

    with db.session() as session:
        # Get procedures with Linux paths
        result = session.execute(text("SELECT id, name, file_path FROM procedures WHERE file_path IS NOT NULL"))
        procs = result.fetchall()

        for proc_id, name, file_path in procs:
            if file_path and '/home/' in file_path:
                # Convert Linux path to Windows path
                # /home/paula/.calsystem/procedures/... -> C:\Users\paula\.calsystem\procedures\...
                win_path = file_path.replace('/home/paula/', 'C:\\Users\\paula\\')
                win_path = win_path.replace('/', '\\')

                print(f"Fixing [{proc_id}] {name}:")
                print(f"  Old: {file_path}")
                print(f"  New: {win_path}")

                session.execute(text(
                    "UPDATE procedures SET file_path = :path WHERE id = :id"
                ), {"path": win_path, "id": proc_id})

        session.commit()
        print("\nDone!")

    # Verify
    with db.session() as session:
        result = session.execute(text("SELECT id, name, file_path FROM procedures WHERE file_path IS NOT NULL"))
        print("\nCurrent paths:")
        for row in result:
            print(f"  [{row[0]}] {row[1]}: {row[2]}")


if __name__ == "__main__":
    main()
