"""Check changelog versions."""
from sqlalchemy import create_engine, text
from pathlib import Path

db_path = Path.home() / ".calsystem" / "calsystem.db"
engine = create_engine(f"sqlite:///{db_path}")

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT version, is_published, COUNT(*) as count
        FROM changelog
        GROUP BY version, is_published
        ORDER BY version
    """)).fetchall()
    print("Version | Published | Count")
    print("-" * 30)
    for r in result:
        print(f"{r[0]:8} | {r[1]:9} | {r[2]}")
