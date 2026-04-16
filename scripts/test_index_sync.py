"""Test script to sync procedure index."""

import sys
from pathlib import Path

# Add src to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

from calsystem.database.connection import get_db
from calsystem.procedures import ProcedureIndex, sync_procedure_index


def main():
    print("=" * 50)
    print("  Procedure Index Sync Test")
    print("=" * 50)

    # Connect to database
    db = get_db()
    if not db.connect():
        print("ERROR: Could not connect to database")
        return

    print("Database connected\n")

    # Create index and scan folder
    index = ProcedureIndex()
    print(f"Procedures directory: {index.procedures_dir}")

    print("\nScanning procedures folder...")
    files = index.scan_procedures_folder()
    print(f"Found {len(files)} .csp file(s):")
    for f in files:
        print(f"  - {f['name']}: {f['section_count']} sections, {f['test_point_count']} test points")
        print(f"    Path: {f['file_path']}")
        print(f"    Hash: {f['file_hash'][:16]}...")

    print("\nSyncing index...")
    added, updated, removed = sync_procedure_index()
    print(f"Sync complete: {added} added, {updated} updated, {removed} removed")

    print("\nAll procedures:")
    procs = index.get_all_procedures()
    for p in procs:
        has_csp = "Yes" if p["has_csp"] else "No"
        print(f"  - [{p['id']}] {p['name']}")
        print(f"    Model: {p['target_model']}, Version: {p['version']}")
        print(f"    CSP: {has_csp}, Sections: {p['section_count']}, Test Points: {p['test_point_count']}")
        if p['file_path']:
            print(f"    File: {p['file_path']}")

    print("\n" + "=" * 50)
    print("  Test Complete")
    print("=" * 50)


if __name__ == "__main__":
    main()
