"""Check database tables."""
from sqlalchemy import create_engine, text
from pathlib import Path

db_path = Path.home() / ".calsystem" / "calsystem.db"
engine = create_engine(f"sqlite:///{db_path}")

with engine.connect() as conn:
    result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")).fetchall()
    print("Tables:")
    for r in result:
        print(f"  - {r[0]}")

    # Check changelog_entries
    try:
        result = conn.execute(text("SELECT version, is_published, COUNT(*) FROM changelog_entries GROUP BY version, is_published")).fetchall()
        print("\nchangelog_entries:")
        for r in result:
            print(f"  {r}")
    except Exception as e:
        print(f"\nchangelog_entries error: {e}")
