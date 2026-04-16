"""Add changelog entries for today's work."""
from datetime import datetime
from sqlalchemy import create_engine, text
from pathlib import Path

# Connect directly to the SQLite database
db_path = Path.home() / ".calsystem" / "calsystem.db"
engine = create_engine(f"sqlite:///{db_path}")

# Create table if it doesn't exist
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS changelog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version VARCHAR(20) NOT NULL,
            timestamp DATETIME NOT NULL,
            change_type VARCHAR(50) NOT NULL,
            category VARCHAR(50) NOT NULL,
            description TEXT NOT NULL,
            author VARCHAR(100)
        )
    """))
    conn.commit()
    print("Changelog table ready")

entries = [
    ("0.5.0", "Feature", "Reports", "Added PDF calibration report generator with professional formatting"),
    ("0.5.0", "Improvement", "Reports", "PDF reports show tolerance specs per test point group with proper grouping"),
    ("0.5.0", "Improvement", "Reports", "PDF decimal places now match procedure resolution settings"),
    ("0.5.0", "Improvement", "Reports", "PDF sections use KeepTogether to prevent splitting across pages"),
    ("0.5.0", "Improvement", "Reports", "PDF header layout improved with centered Model field"),
    ("0.5.0", "Improvement", "Reports", "Renamed 'Deviation' column to 'Error' in PDF reports"),
    ("0.5.0", "Improvement", "Reports", "PDF reports handle FREQUENCY measurement target for limit calculations"),
    ("0.5.0", "Fix", "Reports", "Fixed status enum handling where status could be string or enum"),
    ("0.5.0", "Fix", "Reports", "Fixed test results loading using raw SQL to avoid enum mapping issues"),
    ("0.5.0", "Fix", "Execution", "Fixed InputMethod.MANUAL to InputMethod.KEYBOARD"),
]

with engine.connect() as conn:
    for version, change_type, category, description in entries:
        conn.execute(text("""
            INSERT INTO changelog (version, timestamp, change_type, category, description, author)
            VALUES (:version, :timestamp, :change_type, :category, :description, :author)
        """), {
            "version": version,
            "timestamp": datetime.now().isoformat(),
            "change_type": change_type,
            "category": category,
            "description": description,
            "author": "Claude",
        })
    conn.commit()
    print(f"Added {len(entries)} changelog entries")
