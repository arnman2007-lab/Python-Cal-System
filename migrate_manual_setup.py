"""
Apply manual_setup migration directly using sqlite3
"""
import sqlite3
import os

# Use WSL path
db_path = os.path.expanduser("~/.calsystem/calsystem.db")

print(f"Connecting to {db_path}...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check if columns exist
cursor.execute("PRAGMA table_info(test_points)")
columns = [row[1] for row in cursor.fetchall()]

if 'manual_setup' not in columns:
    print("Adding manual_setup column...")
    cursor.execute("ALTER TABLE test_points ADD COLUMN manual_setup BOOLEAN DEFAULT 0")
    conn.commit()
    print("✓ manual_setup column added")
else:
    print("manual_setup column already exists")

if 'manual_setup_prompt' not in columns:
    print("Adding manual_setup_prompt column...")
    cursor.execute("ALTER TABLE test_points ADD COLUMN manual_setup_prompt TEXT")
    conn.commit()
    print("✓ manual_setup_prompt column added")
else:
    print("manual_setup_prompt column already exists")

conn.close()
print("Migration complete!")
