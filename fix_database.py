"""
Comprehensive database migration and repair script.
Run this whenever procedures stop loading after a rebuild.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from calsystem.database.connection import get_db
from sqlalchemy import text

def check_and_fix_database():
    """Check and fix database schema issues."""
    db = get_db()

    if not db.connect():
        print("ERROR: Could not connect to database")
        return False

    try:
        with db.session() as session:
            print("Checking database schema...")
            print()

            # Check for pass_fail_image column
            result = session.execute(text(
                "SELECT COUNT(*) FROM pragma_table_info('test_points') WHERE name='pass_fail_image'"
            )).scalar()

            if result == 0:
                print("  [FIXING] Adding pass_fail_image column...")
                session.execute(text(
                    "ALTER TABLE test_points ADD COLUMN pass_fail_image VARCHAR(255)"
                ))
                session.commit()
                print("  ✓ Added pass_fail_image column")
            else:
                print("  ✓ pass_fail_image column exists")

            print()
            print("=" * 60)
            print("Database schema is up to date!")
            print()

            # Now test if we can actually load procedures
            print("Testing procedure loading...")
            from calsystem.database.models import Procedure, TestSection, TestPoint

            procedures = session.query(Procedure).all()
            print(f"  Found {len(procedures)} procedures")

            for proc in procedures:
                try:
                    sections = session.query(TestSection).filter(
                        TestSection.procedure_id == proc.id
                    ).all()

                    total_points = 0
                    for section in sections:
                        points = session.query(TestPoint).filter(
                            TestPoint.section_id == section.id
                        ).all()
                        total_points += len(points)

                    print(f"  ✓ {proc.name}: {len(sections)} sections, {total_points} test points")

                except Exception as e:
                    print(f"  ✗ {proc.name}: ERROR loading - {e}")
                    return False

            print()
            print("=" * 60)
            print("All procedures loaded successfully!")
            print("You can now run the application.")
            return True

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Calsystem Database Fix & Migration")
    print("=" * 60)
    print()

    db_path = os.path.expanduser("~/.calsystem/calsystem.db")
    if os.name == 'nt':  # Windows
        db_path = os.path.expanduser("~\\.calsystem\\calsystem.db")

    print(f"Database location: {db_path}")

    if not os.path.exists(db_path):
        print(f"\nERROR: Database not found at {db_path}")
        print("The application will create a new database on first run.")
        sys.exit(1)

    print(f"Database size: {os.path.getsize(db_path):,} bytes")
    print()

    if check_and_fix_database():
        print("\n✓✓✓ SUCCESS! Database is ready to use. ✓✓✓")
        sys.exit(0)
    else:
        print("\n✗✗✗ FAILED! Please check errors above. ✗✗✗")
        sys.exit(1)
