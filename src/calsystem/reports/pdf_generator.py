"""
PDF report generator using ReportLab.
"""

from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

from loguru import logger

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        Image,
        PageBreak,
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("ReportLab not available - PDF generation disabled")


class PDFReportGenerator:
    """Generates PDF calibration reports."""

    def __init__(self):
        self._styles = None
        if REPORTLAB_AVAILABLE:
            self._styles = getSampleStyleSheet()
            self._add_custom_styles()

    def _add_custom_styles(self):
        """Add custom paragraph styles."""
        self._styles.add(ParagraphStyle(
            name="Title_Custom",
            parent=self._styles["Title"],
            fontSize=18,
            spaceAfter=20,
        ))

        self._styles.add(ParagraphStyle(
            name="Heading_Custom",
            parent=self._styles["Heading2"],
            fontSize=14,
            spaceBefore=12,
            spaceAfter=6,
        ))

        self._styles.add(ParagraphStyle(
            name="Normal_Custom",
            parent=self._styles["Normal"],
            fontSize=10,
        ))

    def generate(
        self,
        output_path: str,
        session_data: Dict[str, Any],
        test_results: List[Dict[str, Any]],
        template: str = "standard",
    ) -> bool:
        """
        Generate a PDF calibration report.

        Args:
            output_path: Path to save the PDF file.
            session_data: Calibration session information.
            test_results: List of test point results.
            template: Report template name.

        Returns:
            True if successful.
        """
        if not REPORTLAB_AVAILABLE:
            logger.error("ReportLab not available")
            return False

        try:
            doc = SimpleDocTemplate(
                output_path,
                pagesize=letter,
                rightMargin=0.75 * inch,
                leftMargin=0.75 * inch,
                topMargin=0.75 * inch,
                bottomMargin=0.75 * inch,
            )

            # Build document content
            story = []

            # Title
            story.append(Paragraph(
                "Calibration Report",
                self._styles["Title_Custom"]
            ))

            # Session info section
            story.append(Paragraph("Session Information", self._styles["Heading_Custom"]))
            story.extend(self._build_session_info(session_data))
            story.append(Spacer(1, 12))

            # Test results section
            story.append(Paragraph("Test Results", self._styles["Heading_Custom"]))
            story.append(self._build_results_table(test_results))
            story.append(Spacer(1, 12))

            # Summary section
            story.append(Paragraph("Summary", self._styles["Heading_Custom"]))
            story.extend(self._build_summary(session_data, test_results))

            # Signature section
            story.append(Spacer(1, 24))
            story.extend(self._build_signature_section())

            # Build PDF
            doc.build(story)
            logger.info(f"PDF report generated: {output_path}")
            return True

        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            return False

    def _build_session_info(self, session_data: Dict[str, Any]) -> List:
        """Build session information section."""
        elements = []

        info_data = [
            ["Asset Number:", session_data.get("asset_number", "N/A")],
            ["Device:", f"{session_data.get('make', '')} {session_data.get('model', '')}"],
            ["Serial Number:", session_data.get("serial_number", "N/A")],
            ["Work Order:", session_data.get("work_order", "N/A")],
            ["Date:", session_data.get("date", datetime.now().strftime("%Y-%m-%d"))],
            ["Technician:", session_data.get("technician", "N/A")],
            ["Procedure:", session_data.get("procedure_name", "N/A")],
        ]

        table = Table(info_data, colWidths=[1.5 * inch, 4 * inch])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        elements.append(table)
        return elements

    def _build_results_table(self, test_results: List[Dict[str, Any]]) -> Table:
        """Build test results table."""
        # Table header
        header = ["Test Point", "Nominal", "Measured", "Deviation", "Tolerance", "Status"]

        # Table data
        data = [header]
        for result in test_results:
            row = [
                result.get("test_point", ""),
                result.get("nominal", ""),
                result.get("measured", ""),
                result.get("deviation", ""),
                result.get("tolerance", ""),
                result.get("status", ""),
            ]
            data.append(row)

        table = Table(data, colWidths=[
            1.5 * inch, 1 * inch, 1 * inch, 0.8 * inch, 0.8 * inch, 0.6 * inch
        ])

        # Table styling
        style = TableStyle([
            # Header
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            # Body
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ])

        # Color code status column
        for i, result in enumerate(test_results, start=1):
            status = result.get("status", "").upper()
            if status == "PASS":
                style.add("BACKGROUND", (-1, i), (-1, i), colors.lightgreen)
            elif status == "FAIL":
                style.add("BACKGROUND", (-1, i), (-1, i), colors.lightcoral)

        table.setStyle(style)
        return table

    def _build_summary(
        self,
        session_data: Dict[str, Any],
        test_results: List[Dict[str, Any]]
    ) -> List:
        """Build summary section."""
        elements = []

        # Count pass/fail
        total = len(test_results)
        passed = sum(1 for r in test_results if r.get("status", "").upper() == "PASS")
        failed = total - passed

        overall = "PASS" if failed == 0 else "FAIL"

        summary_text = f"""
        Total Test Points: {total}<br/>
        Passed: {passed}<br/>
        Failed: {failed}<br/>
        <br/>
        <b>Overall Result: {overall}</b>
        """

        elements.append(Paragraph(summary_text, self._styles["Normal_Custom"]))
        return elements

    def _build_signature_section(self) -> List:
        """Build signature section."""
        elements = []

        sig_data = [
            ["Technician Signature:", "_" * 30, "Date:", "_" * 15],
            ["", "", "", ""],
            ["Supervisor Signature:", "_" * 30, "Date:", "_" * 15],
        ]

        table = Table(sig_data, colWidths=[1.5 * inch, 2.5 * inch, 0.5 * inch, 1.5 * inch])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))

        elements.append(table)
        return elements
