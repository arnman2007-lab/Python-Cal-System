"""
Reports tab - for generating PDF reports and Excel exports.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QComboBox,
    QTextEdit,
    QDateEdit,
    QFormLayout,
    QFileDialog,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QDate
from loguru import logger


class ReportsTab(QWidget):
    """Tab for generating reports and exporting data."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Search/filter bar
        filter_group = QGroupBox("Search Calibration Records")
        filter_layout = QHBoxLayout(filter_group)

        filter_layout.addWidget(QLabel("Asset Number:"))
        self.asset_filter = QLineEdit()
        self.asset_filter.setPlaceholderText("Enter asset number...")
        filter_layout.addWidget(self.asset_filter)

        filter_layout.addWidget(QLabel("Work Order:"))
        self.workorder_filter = QLineEdit()
        filter_layout.addWidget(self.workorder_filter)

        filter_layout.addWidget(QLabel("Date Range:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        filter_layout.addWidget(self.date_from)

        filter_layout.addWidget(QLabel("to"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(self.date_to)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._on_search)
        filter_layout.addWidget(self.search_btn)

        layout.addWidget(filter_group)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left - Session list
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        list_group = QGroupBox("Calibration Sessions")
        list_inner_layout = QVBoxLayout(list_group)

        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(5)
        self.sessions_table.setHorizontalHeaderLabels(
            ["Date", "Asset Number", "Work Order", "Technician", "Result"]
        )
        self.sessions_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.sessions_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.sessions_table.itemSelectionChanged.connect(self._on_session_selected)
        list_inner_layout.addWidget(self.sessions_table)

        list_layout.addWidget(list_group)
        splitter.addWidget(list_widget)

        # Right - Session details and report options
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)

        # Session details
        details_group = QGroupBox("Session Details")
        details_inner_layout = QFormLayout(details_group)

        self.detail_asset = QLabel("--")
        details_inner_layout.addRow("Asset Number:", self.detail_asset)

        self.detail_dut = QLabel("--")
        details_inner_layout.addRow("DUT:", self.detail_dut)

        self.detail_workorder = QLabel("--")
        details_inner_layout.addRow("Work Order:", self.detail_workorder)

        self.detail_date = QLabel("--")
        details_inner_layout.addRow("Date:", self.detail_date)

        self.detail_technician = QLabel("--")
        details_inner_layout.addRow("Technician:", self.detail_technician)

        self.detail_result = QLabel("--")
        details_inner_layout.addRow("Result:", self.detail_result)

        self.detail_procedure = QLabel("--")
        details_inner_layout.addRow("Procedure:", self.detail_procedure)

        details_layout.addWidget(details_group)

        # Test results summary
        results_group = QGroupBox("Test Results")
        results_layout = QVBoxLayout(results_group)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(
            ["Test Point", "Nominal", "Measured", "Deviation", "Status"]
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        results_layout.addWidget(self.results_table)

        details_layout.addWidget(results_group)

        # Report generation
        report_group = QGroupBox("Generate Report")
        report_layout = QVBoxLayout(report_group)

        template_layout = QHBoxLayout()
        template_layout.addWidget(QLabel("Template:"))
        self.template_combo = QComboBox()
        self.template_combo.addItems(["Standard Report", "Detailed Report", "Summary Only"])
        template_layout.addWidget(self.template_combo)
        template_layout.addStretch()
        report_layout.addLayout(template_layout)

        btn_layout = QHBoxLayout()

        self.pdf_btn = QPushButton("Generate PDF")
        self.pdf_btn.clicked.connect(self._on_generate_pdf)
        btn_layout.addWidget(self.pdf_btn)

        self.excel_btn = QPushButton("Export to Excel")
        self.excel_btn.clicked.connect(self._on_export_excel)
        btn_layout.addWidget(self.excel_btn)

        self.print_btn = QPushButton("Print")
        self.print_btn.clicked.connect(self._on_print)
        btn_layout.addWidget(self.print_btn)

        btn_layout.addStretch()
        report_layout.addLayout(btn_layout)

        details_layout.addWidget(report_group)

        splitter.addWidget(details_widget)

        # Set splitter sizes
        splitter.setSizes([400, 500])

        layout.addWidget(splitter)

    def _on_search(self):
        """Search for calibration sessions."""
        asset = self.asset_filter.text().strip()
        workorder = self.workorder_filter.text().strip()
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")

        logger.info(
            f"Searching sessions: asset={asset}, wo={workorder}, "
            f"from={date_from}, to={date_to}"
        )

        # TODO: Query database
        # For now, load sample data
        self._load_sample_sessions()

    def _load_sample_sessions(self):
        """Load sample session data for demonstration."""
        sessions = [
            ("2024-01-15", "789-123456789", "WO-2024-001", "John Smith", "Pass"),
            ("2024-01-14", "3458A-87654321", "WO-2024-002", "Jane Doe", "Pass"),
            ("2024-01-13", "5520A-11111111", "WO-2024-003", "John Smith", "Fail"),
        ]

        self.sessions_table.setRowCount(len(sessions))

        for i, (date, asset, wo, tech, result) in enumerate(sessions):
            self.sessions_table.setItem(i, 0, QTableWidgetItem(date))
            self.sessions_table.setItem(i, 1, QTableWidgetItem(asset))
            self.sessions_table.setItem(i, 2, QTableWidgetItem(wo))
            self.sessions_table.setItem(i, 3, QTableWidgetItem(tech))

            result_item = QTableWidgetItem(result)
            if result == "Pass":
                result_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                result_item.setForeground(Qt.GlobalColor.red)
            self.sessions_table.setItem(i, 4, result_item)

    def _on_session_selected(self):
        """Handle session selection."""
        selected = self.sessions_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        date = self.sessions_table.item(row, 0).text()
        asset = self.sessions_table.item(row, 1).text()
        wo = self.sessions_table.item(row, 2).text()
        tech = self.sessions_table.item(row, 3).text()
        result = self.sessions_table.item(row, 4).text()

        # Update details
        self.detail_asset.setText(asset)
        self.detail_dut.setText("Fluke 789 (example)")
        self.detail_workorder.setText(wo)
        self.detail_date.setText(date)
        self.detail_technician.setText(tech)
        self.detail_result.setText(result)
        self.detail_procedure.setText("Standard DMM Calibration (example)")

        # Load test results
        self._load_sample_results()

        logger.debug(f"Selected session: {wo}")

    def _load_sample_results(self):
        """Load sample test results."""
        results = [
            ("DC 1V", "1.0000 V", "1.0001 V", "+0.01%", "Pass"),
            ("DC 10V", "10.000 V", "10.002 V", "+0.02%", "Pass"),
            ("DC 100V", "100.00 V", "100.05 V", "+0.05%", "Pass"),
            ("AC 1V", "1.0000 V", "0.9998 V", "-0.02%", "Pass"),
        ]

        self.results_table.setRowCount(len(results))

        for i, (test, nominal, measured, dev, status) in enumerate(results):
            self.results_table.setItem(i, 0, QTableWidgetItem(test))
            self.results_table.setItem(i, 1, QTableWidgetItem(nominal))
            self.results_table.setItem(i, 2, QTableWidgetItem(measured))
            self.results_table.setItem(i, 3, QTableWidgetItem(dev))

            status_item = QTableWidgetItem(status)
            if status == "Pass":
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                status_item.setForeground(Qt.GlobalColor.red)
            self.results_table.setItem(i, 4, status_item)

    def _on_generate_pdf(self):
        """Generate PDF report."""
        selected = self.sessions_table.selectedItems()
        if not selected:
            QMessageBox.warning(
                self, "No Selection", "Please select a session to generate a report."
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF Report",
            f"calibration_report_{QDate.currentDate().toString('yyyyMMdd')}.pdf",
            "PDF Files (*.pdf)",
        )

        if file_path:
            logger.info(f"Generating PDF: {file_path}")
            # TODO: Generate actual PDF
            QMessageBox.information(
                self,
                "Report Generated",
                f"PDF report saved to:\n{file_path}",
            )

    def _on_export_excel(self):
        """Export to Excel."""
        selected = self.sessions_table.selectedItems()
        if not selected:
            QMessageBox.warning(
                self, "No Selection", "Please select a session to export."
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export to Excel",
            f"calibration_data_{QDate.currentDate().toString('yyyyMMdd')}.xlsx",
            "Excel Files (*.xlsx)",
        )

        if file_path:
            logger.info(f"Exporting to Excel: {file_path}")
            # TODO: Export to Excel
            QMessageBox.information(
                self,
                "Export Complete",
                f"Data exported to:\n{file_path}",
            )

    def _on_print(self):
        """Print report."""
        selected = self.sessions_table.selectedItems()
        if not selected:
            QMessageBox.warning(
                self, "No Selection", "Please select a session to print."
            )
            return

        logger.info("Printing report")
        # TODO: Implement print functionality
        QMessageBox.information(
            self,
            "Print",
            "Print functionality will be implemented.",
        )
