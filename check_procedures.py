"""
Check what procedures and test points exist in the database.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from calsystem.database.connection import get_db
from calsystem.database.models import Procedure, TestSection, TestPoint

def check_database():
    """Check database contents."""
    db = get_db()

    if not db.connect():
        print("ERROR: Could not connect to database")
        return

    try:
        with db.session() as session:
            # Count procedures
            procedure_count = session.query(Procedure).count()
            print(f"Procedures: {procedure_count}")

            if procedure_count > 0:
                print("\nProcedure Details:")
                print("-" * 60)
                procedures = session.query(Procedure).all()
                for proc in procedures:
                    section_count = session.query(TestSection).filter(
                        TestSection.procedure_id == proc.id
                    ).count()
                    point_count = session.query(TestPoint).join(TestSection).filter(
                        TestSection.procedure_id == proc.id
                    ).count()

                    print(f"\n  ID: {proc.id}")
                    print(f"  Name: {proc.name}")
                    print(f"  Target Model: {proc.target_model or 'Not specified'}")
                    print(f"  Sections: {section_count}")
                    print(f"  Test Points: {point_count}")

                    if section_count > 0:
                        sections = session.query(TestSection).filter(
                            TestSection.procedure_id == proc.id
                        ).all()
                        print(f"  Section Names:")
                        for sec in sections:
                            points = session.query(TestPoint).filter(
                                TestPoint.section_id == sec.id
                            ).count()
                            print(f"    - {sec.name} ({points} points)")

            print("\n" + "=" * 60)
            print(f"Total Sections: {session.query(TestSection).count()}")
            print(f"Total Test Points: {session.query(TestPoint).count()}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("Calsystem Database Contents Check")
    print("=" * 60)
    print()

    db_path = os.path.expanduser("~/.calsystem/calsystem.db")
    if os.name == 'nt':  # Windows
        db_path = os.path.expanduser("~\\.calsystem\\calsystem.db")

    print(f"Database location: {db_path}")

    if not os.path.exists(db_path):
        print(f"\nERROR: Database not found at {db_path}")
        print("No procedures will be available.")
        sys.exit(1)

    print(f"Database size: {os.path.getsize(db_path):,} bytes")
    print()

    check_database()
