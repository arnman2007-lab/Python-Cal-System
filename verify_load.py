"""
Verify that procedures can be loaded properly using SQLAlchemy
"""
import sys
sys.path.insert(0, 'src')

from calsystem.database.connection import get_db
from calsystem.database.models import Procedure, TestSection, TestPoint
from loguru import logger

db = get_db()
if not db.connect():
    print("Failed to connect to database")
    sys.exit(1)

print("Testing procedure loading...\n")

with db.session() as session:
    procedures = session.query(Procedure).all()

    for proc in procedures:
        print(f"Procedure: {proc.name} (ID: {proc.id})")
        print(f"  Target: {proc.target_make} {proc.target_model}")
        print(f"  Sections: {len(proc.sections)}")

        for section in proc.sections:
            print(f"    Section: {section.name} (ID: {section.id}, Order: {section.order})")
            print(f"      Test Points: {len(section.test_points)}")

            for tp in section.test_points:
                print(f"        TP {tp.order}: {tp.test_type} - {tp.nominal_value} {tp.unit or ''}")

        print()

print("✓ All data loaded successfully via SQLAlchemy!")
