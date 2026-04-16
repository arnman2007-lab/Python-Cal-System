"""Test script to export existing procedure to .csp format."""

import sys
from pathlib import Path

# Add src to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

from calsystem.database.connection import get_db
from calsystem.database.models import Procedure
from calsystem.procedures import export_procedure_to_csp, CSPFile


def main():
    print("=" * 50)
    print("  CSP Export Test")
    print("=" * 50)

    # Connect to database
    db = get_db()
    if not db.connect():
        print("ERROR: Could not connect to database")
        return

    print("Database connected")

    # Get all procedures
    proc_info = []
    with db.session() as session:
        procedures = session.query(Procedure).all()
        print(f"\nFound {len(procedures)} procedure(s):")
        for proc in procedures:
            section_count = len(proc.sections) if proc.sections else 0
            tp_count = sum(len(s.test_points) for s in proc.sections) if proc.sections else 0
            print(f"  - [{proc.id}] {proc.name} ({section_count} sections, {tp_count} test points)")
            proc_info.append({
                "id": proc.id,
                "name": proc.name,
                "sections": section_count,
                "test_points": tp_count,
            })

    if not proc_info:
        print("\nNo procedures to export")
        return

    # Find the procedure with test points (not the empty one)
    proc_to_export = None
    for p in proc_info:
        if p["test_points"] > 0:
            proc_to_export = p
            break

    if not proc_to_export:
        proc_to_export = proc_info[0]

    print(f"\nExporting procedure: {proc_to_export['name']}")

    # Create output directory
    output_dir = Path.home() / ".calsystem" / "procedures"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")

    # Export
    success, message, file_path = export_procedure_to_csp(
        procedure_id=proc_to_export["id"],
        output_dir=output_dir,
        include_images=True,
        created_by="Migration Test",
    )

    print(f"\nExport result: {'SUCCESS' if success else 'FAILED'}")
    print(f"Message: {message}")

    if success and file_path:
        print(f"\nFile created: {file_path}")

        # Validate the file
        is_valid, validation_msg = CSPFile.validate(file_path)
        print(f"Validation: {'PASSED' if is_valid else 'FAILED'} - {validation_msg}")

        # Read metadata
        metadata = CSPFile.extract_metadata(file_path)
        if metadata:
            print(f"\nMetadata:")
            print(f"  Name: {metadata.name}")
            print(f"  Model: {metadata.target_model}")
            print(f"  Version: {metadata.version}")
            print(f"  Sections: {metadata.section_count}")
            print(f"  Test Points: {metadata.test_point_count}")
            print(f"  CSP Version: {metadata.csp_version}")
            print(f"  Created: {metadata.created_at}")

        # List images
        images = CSPFile.list_images(file_path)
        print(f"\nImages ({len(images)}):")
        for img in images:
            print(f"  - {img}")

        # Test full load
        print("\nTesting full load...")
        loaded = CSPFile.load(file_path)
        if loaded:
            print(f"Loaded procedure: {loaded.name}")
            print(f"Sections: {loaded.section_count}")
            print(f"Test points: {loaded.test_point_count}")
            print(f"Images loaded: {len(loaded.images)}")

            # Show first section details
            if loaded.sections:
                s = loaded.sections[0]
                print(f"\nFirst section: {s.name}")
                print(f"  Type: {s.standard_section_type}")
                print(f"  Test points: {len(s.test_points)}")
                if s.test_points:
                    tp = s.test_points[0]
                    print(f"  First test point: {tp.nominal_value} {tp.unit}")
        else:
            print("ERROR: Failed to load exported file")

    print("\n" + "=" * 50)
    print("  Test Complete")
    print("=" * 50)


if __name__ == "__main__":
    main()
