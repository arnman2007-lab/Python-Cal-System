"""
Check section names for potential regex issues
"""
import sys
import re
sys.path.insert(0, 'src')

from calsystem.database.connection import get_db
from calsystem.database.models import Procedure, TestSection

db = get_db()
if not db.connect():
    print("Failed to connect")
    sys.exit(1)

with db.session() as session:
    sections = session.query(TestSection).all()

    print(f"Checking {len(sections)} section names for regex issues:\n")

    for section in sections:
        original_name = section.name
        clean_name = original_name

        # Test the cleaning loop
        iterations = 0
        max_iterations = 10

        while re.search(r'\s*\[[^\]]+\]\s*$', clean_name) and iterations < max_iterations:
            clean_name = re.sub(r'\s*\[[^\]]+\]\s*$', '', clean_name).strip()
            iterations += 1

        if iterations >= max_iterations:
            print(f"⚠ WARNING: Section '{original_name}' hit max iterations!")
            print(f"  This could cause an infinite loop in the app")
        elif iterations > 0:
            print(f"Section: '{original_name}' -> '{clean_name}' ({iterations} iterations)")

    print("\nDone checking section names")
