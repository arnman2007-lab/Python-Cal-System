"""Fix changelog entries to use correct version."""
from sqlalchemy import create_engine, text
from pathlib import Path

db_path = Path.home() / ".calsystem" / "calsystem.db"
engine = create_engine(f"sqlite:///{db_path}")

with engine.connect() as conn:
    # Update entries we just added (they have author='Claude' and version='0.5.0')
    result = conn.execute(text("""
        UPDATE changelog
        SET version = '0.6.0'
        WHERE version = '0.5.0' AND author = 'Claude'
    """))
    conn.commit()
    print(f"Updated {result.rowcount} changelog entries to version 0.6.0")
