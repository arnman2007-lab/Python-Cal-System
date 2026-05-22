"""
Report generation utilities for calibration datasheets.

Generates PDF reports in a standard format that adapts to any procedure.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from loguru import logger


@dataclass
class ReportHeader:
    """Header information for calibration report."""
    company_name: str
    work_order: str
    manufacturer: str
    model: str
    description: str
    mfr_serial: str
    customer_id: str
    customer_serial: str
    calibration_date: datetime
    calibration_procedure: str
    software_version: str


@dataclass
class TestPointResult:
    """Single test point result."""
    nominal_value: float
    unit: str
    low_limit: float
    measured_value: float
    high_limit: float
    error: float  # Renamed from deviation - how far off from nominal
    result: str  # "Pass" or "Fail"
    tolerance_spec: str = ""  # Tolerance spec for this test point
    resolution: float = 0  # Resolution for decimal place formatting
    frequency: Optional[float] = None
    frequency_unit: Optional[str] = None
    measurement_target: str = "PRIMARY"  # PRIMARY or FREQUENCY
    test_type: str = "measurement"  # measurement, pass_fail, etc.
    description: Optional[str] = None  # Test description for pass/fail tests


@dataclass
class TestSectionResult:
    """Results for a test section."""
    section_name: str
    tolerance_spec: str  # e.g., "0.05% rdg + 3 dgt"
    test_points: List[TestPointResult]
    unit: str = ""  # Default unit for the section


def _get_decimal_places_from_resolution(resolution: float) -> int:
    """Determine decimal places from resolution value (e.g., 0.001 = 3 decimals)."""
    if not resolution or resolution <= 0:
        return 0
    # Count decimal places needed to represent the resolution
    if resolution >= 1:
        return 0
    str_val = f"{resolution:.10f}".rstrip('0')
    if '.' in str_val:
        return len(str_val.split('.')[1])
    return 0


def _get_decimal_places(value: float) -> int:
    """Determine the number of decimal places from a value's significant digits."""
    if value == 0:
        return 0
    # Convert to string and count decimal places (using :g strips trailing zeros)
    str_val = f"{value:g}"
    if '.' in str_val:
        # Check for scientific notation
        if 'e' in str_val.lower():
            return 0  # Handle separately
        return len(str_val.split('.')[1])
    return 0


def _format_nominal(value: float) -> str:
    """Format nominal value - clean format without unnecessary trailing zeros."""
    return f"{value:g}"


def _format_value(value: float, decimal_places: int) -> str:
    """Format a value with a specific number of decimal places."""
    return f"{value:.{decimal_places}f}"


def generate_calibration_report(
    output_path: Path,
    header: ReportHeader,
    sections: List[TestSectionResult],
) -> bool:
    """
    Generate a calibration datasheet PDF report.

    Args:
        output_path: Path to save the PDF
        header: Report header information
        sections: List of test section results

    Returns:
        True if successful, False otherwise
    """
    try:
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch,
        )

        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontSize=14,
            alignment=TA_CENTER,
            spaceAfter=6,
        )

        header_style = ParagraphStyle(
            'Header',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=2,
        )

        section_header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=11,
            alignment=TA_CENTER,
            spaceAfter=6,
            spaceBefore=12,
            textDecoration='underline',
        )

        small_style = ParagraphStyle(
            'Small',
            parent=styles['Normal'],
            fontSize=8,
            alignment=TA_CENTER,
        )

        elements = []

        # === HEADER SECTION ===
        # Top row: Company | Title | Work Order
        header_data = [
            [
                Paragraph(f"<b>{header.company_name}</b>", header_style),
                Paragraph("<b>Calibration Datasheet</b>", title_style),
                Paragraph(f"<b>Work Order: {header.work_order}</b>",
                         ParagraphStyle('Right', parent=header_style, alignment=TA_RIGHT)),
            ]
        ]
        header_table = Table(header_data, colWidths=[2.5*inch, 2.5*inch, 2.5*inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 6))

        # Info rows - 3 columns to match header layout
        info_data = [
            [
                Paragraph(f"Manufacturer: {header.manufacturer}", header_style),
                Paragraph(f"<b>Model: {header.model}</b>",
                         ParagraphStyle('Center', parent=header_style, alignment=TA_CENTER)),
                Paragraph("", header_style),
            ],
            [
                Paragraph(f"Description: {header.description}", header_style),
                Paragraph("", header_style),
                Paragraph("", header_style),
            ],
            [
                Paragraph(f"Mfr S/N: {header.mfr_serial}", header_style),
                Paragraph(f"Cust ID: {header.customer_id}",
                         ParagraphStyle('Center', parent=header_style, alignment=TA_CENTER)),
                Paragraph(f"Cust S/N: {header.customer_serial}",
                         ParagraphStyle('Right', parent=header_style, alignment=TA_RIGHT)),
            ],
        ]

        info_table = Table(info_data, colWidths=[2.5*inch, 2.5*inch, 2.5*inch])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ]))
        elements.append(info_table)

        # Horizontal line
        elements.append(Spacer(1, 6))
        line_data = [['_' * 95]]
        line_table = Table(line_data, colWidths=[7.5*inch])
        line_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 6),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ]))
        elements.append(line_table)
        elements.append(Spacer(1, 6))

        # Meta info
        date_str = header.calibration_date.strftime("%m/%d/%Y %I:%M:%S %p")
        meta_text = f"Data created on: {date_str}"
        elements.append(Paragraph(meta_text, header_style))

        proc_text = f"<i>Calibration Procedure: {header.calibration_procedure}</i>"
        elements.append(Paragraph(proc_text, header_style))

        sw_text = f"<i>Calsystem ver. {header.software_version}</i>"
        elements.append(Paragraph(sw_text, header_style))
        elements.append(Spacer(1, 12))

        # === TEST SECTIONS ===
        for section in sections:
            # Group test points by test type and tolerance spec
            # Format: [(test_type, tolerance_spec, [test_points])]
            groups = []
            current_group = []
            current_type = None
            current_tol = None

            for tp in section.test_points:
                if tp.test_type != current_type or tp.tolerance_spec != current_tol:
                    if current_group:
                        groups.append((current_type, current_tol, current_group))
                    current_group = [tp]
                    current_type = tp.test_type
                    current_tol = tp.tolerance_spec
                else:
                    current_group.append(tp)
            if current_group:
                groups.append((current_type, current_tol, current_group))

            # Render each group
            is_first_group = True
            for test_type, tol_spec, group_points in groups:
                # Collect group elements to keep together on same page
                group_elements = []

                # Add section title to first group to keep them together
                if is_first_group:
                    section_title = f"<u>{section.section_name}</u>"
                    group_elements.append(Paragraph(section_title, section_header_style))
                    group_elements.append(Spacer(1, 6))
                    is_first_group = False

                # Check if this is a pass/fail test group
                is_pass_fail = test_type == "pass_fail"

                # Tolerance header for this group (only for measurement tests)
                if tol_spec and not is_pass_fail:
                    tol_para = Paragraph(f"<i>Tolerance: {tol_spec}</i>",
                                        ParagraphStyle('TolSpec', parent=styles['Normal'],
                                                      fontSize=9, alignment=TA_CENTER))
                    group_elements.append(tol_para)
                    group_elements.append(Spacer(1, 3))

                # Results table - different format for pass/fail vs measurement
                if is_pass_fail:
                    # Simple table for pass/fail tests: Test Name | Result
                    table_data = [
                        ['Test', 'Result']
                    ]
                else:
                    # Full table for measurement tests
                    table_data = [
                        ['Nominal Value', 'Low Limit', 'UUT Reading', 'High Limit', 'Error', 'Result']
                    ]

                for tp in group_points:
                    if is_pass_fail:
                        # Pass/Fail row: just test name and result
                        row = [
                            tp.description or "Pass/Fail Test",
                            tp.result,
                        ]
                        table_data.append(row)
                    else:
                        # Measurement row: full details
                        # Determine decimal places: prefer resolution, fall back to nominal's natural decimals
                        if tp.resolution and tp.resolution > 0:
                            decimals = _get_decimal_places_from_resolution(tp.resolution)
                        else:
                            decimals = _get_decimal_places(tp.nominal_value)

                        # Format nominal with frequency if present (clean format - no trailing zeros)
                        if tp.frequency and tp.measurement_target != "FREQUENCY":
                            nominal_str = f"{_format_nominal(tp.nominal_value)} {tp.unit} @ {_format_nominal(tp.frequency)} {tp.frequency_unit or 'Hz'}"
                        elif tp.measurement_target == "FREQUENCY" and tp.frequency:
                            # For frequency measurements, show frequency as the nominal
                            nominal_str = f"{_format_nominal(tp.frequency)} {tp.frequency_unit or 'Hz'}"
                            if tp.resolution and tp.resolution > 0:
                                decimals = _get_decimal_places_from_resolution(tp.resolution)
                            else:
                                decimals = _get_decimal_places(tp.frequency)
                        else:
                            nominal_str = f"{_format_nominal(tp.nominal_value)} {tp.unit}"

                        row = [
                            nominal_str,
                            _format_value(tp.low_limit, decimals),
                            _format_value(tp.measured_value, decimals),
                            _format_value(tp.high_limit, decimals),
                            _format_value(tp.error, decimals),  # Same precision as other values
                            tp.result,
                        ]
                        table_data.append(row)

                # Table configuration based on test type
                if is_pass_fail:
                    # Pass/Fail table: 2 columns (Test Name, Result)
                    results_table = Table(table_data, colWidths=[5*inch, 1.5*inch])
                    result_col = 1  # Result is in column 1 for pass/fail
                else:
                    # Measurement table: 6 columns
                    results_table = Table(table_data, colWidths=[1.5*inch, 1*inch, 1.2*inch, 1*inch, 0.9*inch, 0.9*inch])
                    result_col = 5  # Result is in column 5 for measurements

                # Table styling
                style_commands = [
                    # Header row
                    ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

                    # Data rows
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('ALIGN', (0, 1), (-1, -1), 'CENTER'),

                    # Grid
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]

                # For pass/fail tables, left-align the test name column
                if is_pass_fail:
                    style_commands.append(('ALIGN', (0, 1), (0, -1), 'LEFT'))

                # Color code Pass/Fail results
                for i, tp in enumerate(group_points, start=1):
                    if tp.result.lower() == 'fail':
                        style_commands.append(('TEXTCOLOR', (result_col, i), (result_col, i), colors.red))
                        style_commands.append(('FONTNAME', (result_col, i), (result_col, i), 'Helvetica-Bold'))
                    else:
                        style_commands.append(('TEXTCOLOR', (result_col, i), (result_col, i), colors.green))

                results_table.setStyle(TableStyle(style_commands))
                group_elements.append(results_table)
                group_elements.append(Spacer(1, 6))

                # Keep the tolerance group together on the same page
                elements.append(KeepTogether(group_elements))

            elements.append(Spacer(1, 6))  # Extra space between sections

        # Build PDF
        doc.build(elements, onFirstPage=_add_page_number, onLaterPages=_add_page_number)
        logger.info(f"Report generated: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to generate report: {e}")
        return False


def _add_page_number(canvas, doc):
    """Add page number to the bottom of each page."""
    page_num = canvas.getPageNumber()
    text = f"Page {page_num}"
    canvas.saveState()
    canvas.setFont('Helvetica', 9)
    canvas.drawRightString(7.5*inch, 0.5*inch, text)
    canvas.restoreState()


def build_report_from_session(session_id: int) -> Optional[Dict[str, Any]]:
    """
    Build report data structure from a calibration session.

    Args:
        session_id: The calibration session ID

    Returns:
        Dict with 'header' and 'sections' keys, or None if failed
    """
    from calsystem.database.connection import get_db
    from calsystem.database.models import CalibrationSession, TestResult, TestPoint, TestSection
    from calsystem.config.settings import get_settings
    from calsystem.utils.tolerance import ToleranceSpec

    db = get_db()
    if not db.is_connected:
        logger.error("Database not connected")
        return None

    try:
        with db.session() as session:
            # Get calibration session
            cal_session = session.query(CalibrationSession).filter(
                CalibrationSession.id == session_id
            ).first()

            if not cal_session:
                logger.error(f"Session {session_id} not found")
                return None

            dut = cal_session.dut
            procedure = cal_session.procedure
            settings = get_settings()

            # Get version from changelog
            from calsystem.database.models import ChangelogEntry
            latest_version = session.query(ChangelogEntry).order_by(
                ChangelogEntry.id.desc()
            ).first()
            sw_version = latest_version.version if latest_version else "0.1.0"

            # Build header
            header = ReportHeader(
                company_name=settings.company_name or "Company Name",
                work_order=cal_session.work_order or "N/A",
                manufacturer=dut.make if dut else "Unknown",
                model=dut.model if dut else "Unknown",
                description=dut.description or "N/A",
                mfr_serial=dut.serial_number if dut else "N/A",
                customer_id=dut.customer_id if dut else "N/A",
                customer_serial=dut.customer_serial or "N/A" if dut else "N/A",
                calibration_date=cal_session.started_at or datetime.now(),
                calibration_procedure=procedure.name if procedure else "N/A",
                software_version=sw_version,
            )

            # Build sections from results using raw SQL to avoid enum issues
            sections = []

            from sqlalchemy import text
            results_query = text("""
                SELECT
                    tr.id, tr.test_point_id, tr.measured_value, tr.status,
                    tp.nominal_value, tp.unit, tp.frequency, tp.frequency_unit,
                    tp.tol_pct_reading, tp.tol_pct_range, tp.tol_pct_span,
                    tp.tol_digits, tp.tol_absolute, tp.tol_resolution,
                    tp.tol_range_value, tp.tol_span_value,
                    tp.tolerance_value, tp.tolerance_type,
                    tp.section_id, tp.measurement_target,
                    tp.test_type, tp.description, tp.operator_prompt,
                    ts.name as section_name, ts.id as sect_id
                FROM test_results tr
                JOIN test_points tp ON tr.test_point_id = tp.id
                JOIN test_sections ts ON tp.section_id = ts.id
                WHERE tr.session_id = :session_id
                ORDER BY ts."order", tp."order", tr.id
            """)
            results = session.execute(results_query, {"session_id": session_id}).fetchall()

            # Group results by section
            section_results = {}
            for row in results:
                section_id = row.sect_id
                if section_id not in section_results:
                    section_results[section_id] = {
                        'section_name': row.section_name,
                        'results': []
                    }
                section_results[section_id]['results'].append(row)

            # Build section data
            for section_id, data in section_results.items():
                section_name = data['section_name']
                result_rows = data['results']

                # Build test point results
                test_points = []
                section_unit = ""

                for row in result_rows:
                    # Get test type (normalize to lowercase)
                    test_type = str(row.test_type).lower() if row.test_type else "measurement"

                    # Get test description (use operator_prompt for pass/fail tests - this is the short "check name")
                    test_description = None
                    if test_type == "pass_fail":
                        test_description = row.operator_prompt or row.description or "Pass/Fail Test"
                    else:
                        test_description = row.description

                    # Build tolerance spec for this test point
                    tol_spec = ToleranceSpec(
                        pct_reading=row.tol_pct_reading or 0,
                        pct_range=row.tol_pct_range or 0,
                        pct_span=row.tol_pct_span or 0,
                        digits=row.tol_digits or 0,
                        absolute=row.tol_absolute or 0,
                        resolution=row.tol_resolution or 0,
                        range_value=row.tol_range_value or 0,
                        span_value=row.tol_span_value or 0,
                    )

                    # Fallback to legacy tolerance
                    if tol_spec.is_empty() and row.tolerance_value:
                        tol_spec = ToleranceSpec.from_legacy(
                            row.tolerance_value,
                            row.tolerance_type or "percent"
                        )

                    # Get tolerance spec string for this test point
                    tol_str = tol_spec.format_spec() if not tol_spec.is_empty() else ""

                    # Determine measurement target and reference value for limits
                    measurement_target = row.measurement_target or "PRIMARY"
                    if measurement_target == "FREQUENCY" and row.frequency:
                        # For frequency measurements, use frequency as the reference
                        reference_value = row.frequency
                        nominal = row.frequency
                    else:
                        # Normal measurement uses nominal value
                        reference_value = row.nominal_value or 0
                        nominal = row.nominal_value or 0

                    # Calculate tolerance limits
                    tolerance = tol_spec.calculate(reference_value)
                    low_limit = reference_value - tolerance
                    high_limit = reference_value + tolerance

                    measured = row.measured_value or 0
                    error = measured - reference_value  # Renamed from deviation

                    # Status is a string from raw query
                    status_str = str(row.status) if row.status else ""

                    test_points.append(TestPointResult(
                        nominal_value=nominal,
                        unit=row.unit or "",
                        low_limit=low_limit,
                        measured_value=measured,
                        high_limit=high_limit,
                        error=error,
                        result="Pass" if status_str.lower() == "pass" else "Fail",
                        tolerance_spec=tol_str,
                        resolution=row.tol_resolution or 0,
                        frequency=row.frequency,
                        frequency_unit=row.frequency_unit,
                        measurement_target=measurement_target,
                        test_type=test_type,
                        description=test_description,
                    ))

                    if not section_unit and row.unit:
                        section_unit = row.unit

                sections.append(TestSectionResult(
                    section_name=section_name,
                    tolerance_spec="",  # Tolerance is now per test point
                    test_points=test_points,
                    unit=section_unit,
                ))

            return {
                'header': header,
                'sections': sections,
            }

    except Exception as e:
        logger.error(f"Failed to build report data: {e}")
        return None
