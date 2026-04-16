"""Add changelog entries to the correct table."""
from datetime import datetime
from sqlalchemy import create_engine, text
from pathlib import Path

db_path = Path.home() / ".calsystem" / "calsystem.db"
engine = create_engine(f"sqlite:///{db_path}")

entries = [
    ("0.6.0", "Feature", "Reports", "Added PDF calibration report generator with professional formatting"),
    ("0.6.0", "Improvement", "Reports", "PDF reports show tolerance specs per test point group with proper grouping"),
    ("0.6.0", "Improvement", "Reports", "PDF decimal places now match procedure resolution settings"),
    ("0.6.0", "Improvement", "Reports", "PDF sections use KeepTogether to prevent splitting across pages"),
    ("0.6.0", "Improvement", "Reports", "PDF header layout improved with centered Model field"),
    ("0.6.0", "Improvement", "Reports", "Renamed 'Deviation' to 'Error' in PDF reports"),
    ("0.6.0", "Improvement", "Reports", "PDF reports handle FREQUENCY measurement target for limit calculations"),
    ("0.6.0", "Fix", "Reports", "Fixed status enum handling where status could be string or enum"),
    ("0.6.0", "Fix", "Reports", "Fixed test results loading using raw SQL to avoid enum mapping issues"),
    ("0.6.0", "Fix", "Execution", "Fixed InputMethod.MANUAL to InputMethod.KEYBOARD"),
]

with engine.connect() as conn:
    for version, change_type, category, description in entries:
        conn.execute(text("""
            INSERT INTO changelog_entries (version, timestamp, change_type, category, description, author, is_published)
            VALUES (:version, :timestamp, :change_type, :category, :description, :author, :is_published)
        """), {
            "version": version,
            "timestamp": datetime.now().isoformat(),
            "change_type": change_type,
            "category": category,
            "description": description,
            "author": "Claude",
            "is_published": 1,
        })
    conn.commit()
    print(f"Added {len(entries)} changelog entries to changelog_entries table")

    # Also publish the 0.5.0 entries while we're at it
    result = conn.execute(text("UPDATE changelog_entries SET is_published = 1 WHERE version = '0.5.0'"))
    conn.commit()
    print(f"Published {result.rowcount} v0.5.0 entries")
