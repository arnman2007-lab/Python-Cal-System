"""Mark 0.6.0 changelog entries as published."""
from sqlalchemy import create_engine, text
from pathlib import Path

db_path = Path.home() / ".calsystem" / "calsystem.db"
engine = create_engine(f"sqlite:///{db_path}")

with engine.connect() as conn:
    # Check if is_published column exists
    result = conn.execute(text("PRAGMA table_info(changelog)")).fetchall()
    columns = [r[1] for r in result]
    print(f"Columns: {columns}")

    if 'is_published' not in columns:
        print("Adding is_published column...")
        conn.execute(text("ALTER TABLE changelog ADD COLUMN is_published BOOLEAN DEFAULT 0"))
        conn.commit()

    # Mark all entries as published
    result = conn.execute(text("""
        UPDATE changelog
        SET is_published = 1
        WHERE version = '0.6.0'
    """))
    conn.commit()
    print(f"Published {result.rowcount} entries as version 0.6.0")
