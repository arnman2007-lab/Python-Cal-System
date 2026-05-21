"""
Check if test points have manual_setup flag set
"""
import sys
sys.path.insert(0, 'src')

from calsystem.database.connection import get_db
from calsystem.database.models import Procedure, TestSection, TestPoint

db = get_db()
if not db.connect():
    print("Failed to connect")
    sys.exit(1)

with db.session() as session:
    tps = session.query(TestPoint).all()

    print(f"Checking {len(tps)} test points for manual_setup flag:\n")

    for tp in tps:
        if tp.manual_setup:
            section = session.query(TestSection).get(tp.section_id)
            proc = session.query(Procedure).get(section.procedure_id) if section else None

            print(f"✓ Found manual setup test point:")
            print(f"  Procedure: {proc.name if proc else 'Unknown'}")
            print(f"  Section: {section.name if section else 'Unknown'}")
            print(f"  Test Point: {tp.description or tp.order}")
            print(f"  Manual Setup Prompt: {tp.manual_setup_prompt}")
            print()

    manual_count = sum(1 for tp in tps if tp.manual_setup)
    if manual_count == 0:
        print("No test points have manual_setup=True")
        print("\nMake sure to:")
        print("1. Check the 'Skip Calibrator Output' checkbox")
        print("2. Add instructions in the prompt field")
        print("3. Click 'Save Test Point' button")
