"""
Fix enum values to be uppercase in database
"""
import sqlite3
import os

db_path = os.path.expanduser("~/.calsystem/calsystem.db")

print(f"Fixing enum values in {db_path}...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Update test_type values to uppercase
cursor.execute("UPDATE test_points SET test_type = UPPER(test_type) WHERE test_type IS NOT NULL")
affected = cursor.rowcount
print(f"Updated {affected} test_type values to uppercase")

# Update tolerance_type values to uppercase
cursor.execute("UPDATE test_points SET tolerance_type = UPPER(tolerance_type) WHERE tolerance_type IS NOT NULL")
affected = cursor.rowcount
print(f"Updated {affected} tolerance_type values to uppercase")

# Update pass_fail_comparison_type values to uppercase
cursor.execute("UPDATE test_points SET pass_fail_comparison_type = UPPER(pass_fail_comparison_type) WHERE pass_fail_comparison_type IS NOT NULL")
affected = cursor.rowcount
print(f"Updated {affected} pass_fail_comparison_type values to uppercase")

conn.commit()
conn.close()

print("✓ Enum values fixed!")
