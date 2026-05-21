"""
Check procedure file paths and CSP availability
"""
import sys
import os
sys.path.insert(0, 'src')

from calsystem.database.connection import get_db
from calsystem.database.models import Procedure

db = get_db()
if not db.connect():
    print("Failed to connect")
    sys.exit(1)

with db.session() as session:
    procedures = session.query(Procedure).all()

    print("Checking procedure file paths:\n")
    for proc in procedures:
        print(f"Procedure: {proc.name} (ID: {proc.id})")
        print(f"  file_path: {proc.file_path}")
        if proc.file_path:
            exists = os.path.exists(proc.file_path)
            print(f"  File exists: {exists}")
            if not exists:
                print(f"  ⚠ WARNING: CSP file not found at {proc.file_path}")
                print(f"  This will cause the app to try to load from database instead")
        else:
            print(f"  No CSP file path set - will load from database")
        print()
