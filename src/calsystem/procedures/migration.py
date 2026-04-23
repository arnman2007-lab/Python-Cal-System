"""
Migration utilities for converting database procedures to .csp files.
"""

from pathlib import Path
from typing import Optional, List, Tuple, Dict
from loguru import logger

from calsystem.database.connection import get_db
from calsystem.database.models import (
    Procedure,
    TestSection,
    TestPoint,
    WiringDiagram,
    WiringDiagramLibrary,
    SectionDiagramLink,
)
from calsystem.procedures.procedure_data import (
    ProcedureData,
    TestSectionData,
    TestPointData,
)
from calsystem.procedures.csp_file import CSPFile, generate_csp_filename


def export_procedure_to_csp(
    procedure_id: int,
    output_dir: Path,
    include_images: bool = True,
    created_by: Optional[str] = None,
) -> Tuple[bool, str, Optional[Path]]:
    """
    Export a database procedure to a .csp file.

    Args:
        procedure_id: Database ID of procedure to export
        output_dir: Directory to save .csp file
        include_images: Whether to embed wiring images
        created_by: Author name for metadata

    Returns:
        Tuple of (success, message, file_path)
    """
    db = get_db()
    if not db.is_connected:
        return False, "Database not connected", None

    try:
        with db.session() as session:
            # Load procedure from database
            procedure = session.query(Procedure).filter(
                Procedure.id == procedure_id
            ).first()

            if not procedure:
                return False, f"Procedure not found: {procedure_id}", None

            logger.info(f"Exporting procedure: {procedure.name}")

            # Create ProcedureData
            proc_data = ProcedureData(
                name=procedure.name,
                version=procedure.version or "1.0",
                description=procedure.description,
                target_make=procedure.target_make,
                target_model=procedure.target_model,
                created_by=created_by or procedure.created_by,
            )

            # Load sections with test points
            sections = session.query(TestSection).filter(
                TestSection.procedure_id == procedure_id
            ).order_by(TestSection.order).all()

            for section in sections:
                section_data = _convert_section(section)

                # Get wiring image for section
                if include_images:
                    image_data, image_name = _get_section_wiring_image(
                        session, section, procedure.target_model
                    )
                    if image_data and image_name:
                        section_data.wiring_image = f"images/{image_name}"
                        proc_data.images[f"images/{image_name}"] = image_data

                proc_data.sections.append(section_data)

            # Also get ALL library images for this DUT model (all calibrators)
            if include_images and procedure.target_model:
                all_dut_images = _get_all_dut_images(session, procedure.target_model)
                for img_path, img_data in all_dut_images.items():
                    if img_path not in proc_data.images:  # Don't overwrite section-specific images
                        proc_data.images[img_path] = img_data
                logger.info(f"Total images in CSP: {len(proc_data.images)}")

            # Generate filename
            model = procedure.target_model or "Unknown"
            filename = generate_csp_filename(
                target_model=model,
                procedure_name=procedure.name.replace(model, "").strip(),
                version=procedure.version or "1",
            )
            output_path = Path(output_dir) / filename

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Get software version
            from calsystem import __version__
            software_version = __version__

            # Save to .csp
            success = CSPFile.save(
                procedure=proc_data,
                file_path=output_path,
                created_by=created_by,
                software_version=software_version,
            )

            if success:
                # Update procedure with file path and counts
                file_hash = CSPFile.compute_hash(output_path)
                procedure.file_path = str(output_path)
                procedure.file_hash = file_hash
                procedure.section_count = proc_data.section_count
                procedure.test_point_count = proc_data.test_point_count
                session.commit()

                msg = f"Exported to {output_path} ({proc_data.section_count} sections, {proc_data.test_point_count} test points)"
                logger.info(msg)
                return True, msg, output_path
            else:
                return False, "Failed to save CSP file", None

    except Exception as e:
        logger.error(f"Export failed: {e}")
        return False, f"Export failed: {e}", None


def _convert_section(section: TestSection) -> TestSectionData:
    """Convert database TestSection to TestSectionData."""
    section_data = TestSectionData(
        name=section.name,
        order=section.order or 0,
        description=section.description,
        standard_section_type=section.standard_section_type,
        section_prompt=section.section_prompt,
        section_command=section.section_command,
        section_wiring_type=getattr(section, 'section_wiring_type', None),
    )

    # Load test points
    for tp in sorted(section.test_points, key=lambda x: x.order or 0):
        tp_data = _convert_test_point(tp)
        section_data.test_points.append(tp_data)

    return section_data


def _convert_test_point(tp: TestPoint) -> TestPointData:
    """Convert database TestPoint to TestPointData."""
    # Get test type as string
    test_type = "measurement"
    if hasattr(tp.test_type, 'value'):
        test_type = tp.test_type.value.lower()
    elif tp.test_type:
        test_type = str(tp.test_type).lower()

    # Get measurement target as string
    measurement_target = "PRIMARY"
    if hasattr(tp, 'measurement_target') and tp.measurement_target:
        if hasattr(tp.measurement_target, 'value'):
            measurement_target = tp.measurement_target.value
        else:
            measurement_target = str(tp.measurement_target)

    # Get tolerance type as string
    tolerance_type = "PERCENT"
    if hasattr(tp, 'tolerance_type') and tp.tolerance_type:
        if hasattr(tp.tolerance_type, 'value'):
            tolerance_type = tp.tolerance_type.value
        else:
            tolerance_type = str(tp.tolerance_type)

    # Get pre-conditioning steps
    pre_steps = None
    if hasattr(tp, 'pre_conditioning_steps') and tp.pre_conditioning_steps:
        pre_steps = tp.pre_conditioning_steps

    # Get DMM config
    dmm_config = None
    if hasattr(tp, 'dmm_config') and tp.dmm_config:
        dmm_config = tp.dmm_config

    return TestPointData(
        order=tp.order or 0,
        description=tp.description,
        test_type=test_type,
        nominal_value=tp.nominal_value,
        unit=tp.unit,
        frequency=tp.frequency,
        frequency_unit=tp.frequency_unit or "Hz",

        # Pre-conditioning
        pre_nominal_value=getattr(tp, 'pre_nominal_value', None),
        pre_unit=getattr(tp, 'pre_unit', None),
        pre_frequency=getattr(tp, 'pre_frequency', None),
        pre_frequency_unit=getattr(tp, 'pre_frequency_unit', None) or "Hz",
        pre_delay_seconds=getattr(tp, 'pre_delay_seconds', 0) or 0,
        pre_conditioning_steps=pre_steps,

        # Tolerance - multi-component
        tol_pct_reading=getattr(tp, 'tol_pct_reading', 0) or 0,
        tol_pct_range=getattr(tp, 'tol_pct_range', 0) or 0,
        tol_pct_span=getattr(tp, 'tol_pct_span', 0) or 0,
        tol_digits=getattr(tp, 'tol_digits', 0) or 0,
        tol_absolute=getattr(tp, 'tol_absolute', 0) or 0,
        tol_resolution=getattr(tp, 'tol_resolution', None),
        tol_range_value=getattr(tp, 'tol_range_value', None),
        tol_span_value=getattr(tp, 'tol_span_value', None),

        # Legacy tolerance
        tolerance_value=tp.tolerance_value,
        tolerance_type=tolerance_type,

        # Measurement target
        measurement_target=measurement_target,
        expected_value=getattr(tp, 'expected_value', None),
        expected_unit=getattr(tp, 'expected_unit', None),

        # Pass/Fail
        pass_fail_prompt=getattr(tp, 'pass_fail_prompt', None),
        pass_fail_min=getattr(tp, 'pass_fail_min', None),
        pass_fail_max=getattr(tp, 'pass_fail_max', None),
        pass_fail_range_unit=getattr(tp, 'pass_fail_range_unit', None),
        pass_fail_comparison_type=getattr(tp, 'pass_fail_comparison_type', None),

        # Commands
        source_command=tp.source_command,
        measure_command=tp.measure_command,
        operate_command=tp.operate_command,
        standby_command=tp.standby_command,

        # Instructions
        operator_prompt=getattr(tp, 'operator_prompt', None),
        wiring_diagram_type=getattr(tp, 'wiring_diagram_type', None),

        # Calculated
        formula=tp.formula,

        # DMM
        dmm_config=dmm_config,

        # Excel
        excel_workbook=tp.excel_workbook,
        excel_sheet=tp.excel_sheet,
        excel_cell=tp.excel_cell,

        # DUT Remote Communication
        dut_setup_command=getattr(tp, 'dut_setup_command', None),
        dut_setup_param=getattr(tp, 'dut_setup_param', None),
        dut_pre_check_command=getattr(tp, 'dut_pre_check_command', None),
        dut_pre_check_param=getattr(tp, 'dut_pre_check_param', None),
        dut_pre_check_expected=getattr(tp, 'dut_pre_check_expected', None),
        dut_pre_check_prompt=getattr(tp, 'dut_pre_check_prompt', None),
        dut_pre_check_parser=getattr(tp, 'dut_pre_check_parser', None),
        dut_pre_check_index=getattr(tp, 'dut_pre_check_index', None),
        dut_post_read_command=getattr(tp, 'dut_post_read_command', None),
        dut_post_read_param=getattr(tp, 'dut_post_read_param', None),
        dut_post_read_parser=getattr(tp, 'dut_post_read_parser', None),
        dut_post_read_index=getattr(tp, 'dut_post_read_index', None),
    )


def _get_section_wiring_image(
    session,
    section: TestSection,
    target_model: Optional[str],
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Get wiring image for a section.

    Returns:
        Tuple of (image_data, filename) or (None, None)
    """
    try:
        # First try: SectionDiagramLink
        link = session.query(SectionDiagramLink).filter(
            SectionDiagramLink.section_id == section.id
        ).first()

        if link and link.diagram:
            diagram = link.diagram
            if diagram.image_data:
                filename = diagram.filename or f"{section.standard_section_type or section.name}.png"
                return diagram.image_data, _sanitize_filename(filename)
            elif diagram.image_path:
                # Try to read from file
                try:
                    with open(diagram.image_path, 'rb') as f:
                        data = f.read()
                    filename = Path(diagram.image_path).name
                    return data, _sanitize_filename(filename)
                except Exception:
                    pass

        # Second try: WiringDiagramLibrary by section type
        if section.standard_section_type:
            diagram = session.query(WiringDiagramLibrary).filter(
                WiringDiagramLibrary.section_name == section.standard_section_type
            ).first()

            if diagram:
                if diagram.image_data:
                    filename = diagram.filename or f"{section.standard_section_type}.png"
                    return diagram.image_data, _sanitize_filename(filename)
                elif diagram.image_path:
                    try:
                        with open(diagram.image_path, 'rb') as f:
                            data = f.read()
                        filename = Path(diagram.image_path).name
                        return data, _sanitize_filename(filename)
                    except Exception:
                        pass

        # Third try: Legacy WiringDiagram
        legacy = session.query(WiringDiagram).filter(
            WiringDiagram.section_id == section.id
        ).first()

        if legacy:
            if legacy.image_data:
                filename = legacy.name or f"section_{section.id}.png"
                return legacy.image_data, _sanitize_filename(filename)
            elif legacy.image_path:
                try:
                    with open(legacy.image_path, 'rb') as f:
                        data = f.read()
                    filename = Path(legacy.image_path).name
                    return data, _sanitize_filename(filename)
                except Exception:
                    pass

        return None, None

    except Exception as e:
        logger.error(f"Failed to get wiring image: {e}")
        return None, None


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename for use in archive."""
    # Remove/replace problematic characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename


def _get_all_dut_images(
    session,
    dut_model: str,
) -> Dict[str, bytes]:
    """
    Get ALL wiring images for a DUT model from the library.

    Includes all calibrator variations, organized by calibrator/section.

    Args:
        session: Database session
        dut_model: DUT model number (e.g., "789")

    Returns:
        Dict mapping image paths to image data
        e.g., {"images/5520A/DC_Voltage.png": bytes, ...}
    """
    images = {}

    try:
        # Query all library images for this DUT model
        diagrams = session.query(WiringDiagramLibrary).filter(
            WiringDiagramLibrary.dut_model.ilike(f"%{dut_model}%")
        ).all()

        logger.info(f"Found {len(diagrams)} library images for DUT model {dut_model}")

        for diagram in diagrams:
            # Get image data
            image_data = None
            if diagram.image_data:
                image_data = diagram.image_data
            elif diagram.image_path:
                try:
                    with open(diagram.image_path, 'rb') as f:
                        image_data = f.read()
                except Exception as e:
                    logger.warning(f"Could not read image file {diagram.image_path}: {e}")
                    continue

            if not image_data:
                continue

            # Build path: images/{calibrator_model}/{section_name}.png
            cal_model = _sanitize_filename(diagram.calibrator_model or "Unknown")
            section_name = _sanitize_filename(diagram.section_name or "Unknown")

            # Use original filename if available, otherwise generate
            if diagram.filename:
                filename = _sanitize_filename(diagram.filename)
            else:
                filename = f"{section_name}.png"

            image_path = f"images/{cal_model}/{filename}"
            images[image_path] = image_data

            logger.debug(f"Added library image: {image_path}")

    except Exception as e:
        logger.error(f"Failed to get DUT images: {e}")

    return images


def export_all_procedures(
    output_dir: Path,
    include_images: bool = True,
    created_by: Optional[str] = None,
) -> List[Tuple[str, bool, str]]:
    """
    Export all procedures to .csp files.

    Args:
        output_dir: Directory to save .csp files
        include_images: Whether to embed wiring images
        created_by: Author name for metadata

    Returns:
        List of (procedure_name, success, message) tuples
    """
    results = []
    db = get_db()

    if not db.is_connected:
        return [("Database", False, "Not connected")]

    try:
        with db.session() as session:
            procedures = session.query(Procedure).filter(
                Procedure.is_active == True
            ).all()

            for proc in procedures:
                success, msg, _ = export_procedure_to_csp(
                    procedure_id=proc.id,
                    output_dir=output_dir,
                    include_images=include_images,
                    created_by=created_by,
                )
                results.append((proc.name, success, msg))

    except Exception as e:
        logger.error(f"Export all failed: {e}")
        results.append(("Error", False, str(e)))

    return results
