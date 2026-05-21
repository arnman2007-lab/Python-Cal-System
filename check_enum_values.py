"""
Check enum values in database
"""
import sqlite3
import os

db_path = os.path.expanduser("~/.calsystem/calsystem.db")

print(f"Checking enum values in {db_path}...\n")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check test_type values
cursor.execute("SELECT DISTINCT test_type FROM test_points WHERE test_type IS NOT NULL")
test_types = cursor.fetchall()
print("test_type values:")
for tt in test_types:
    print(f"  - {tt[0]}")

# Check tolerance_type values
cursor.execute("SELECT DISTINCT tolerance_type FROM test_points WHERE tolerance_type IS NOT NULL")
tol_types = cursor.fetchall()
print("\ntolerance_type values:")
for tt in tol_types:
    print(f"  - {tt[0]}")

# Check if any are lowercase
cursor.execute("SELECT COUNT(*) FROM test_points WHERE test_type != UPPER(test_type)")
lowercase_count = cursor.fetchone()[0]
print(f"\nLowercase test_type entries: {lowercase_count}")

conn.close()

if lowercase_count > 0:
    print("\n⚠ WARNING: Database has lowercase enum values - this will cause loading to hang!")
    print("Run fix_enum_case.py to fix")
else:
    print("\n✓ All enum values are uppercase")
