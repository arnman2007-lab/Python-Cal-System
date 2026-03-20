"""
Workstation and Standards management tab.
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
    QComboBox,
    QLineEdit,
    QFormLayout,
    QSplitter,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from loguru import logger


class WorkstationTab(QWidget):
    """Tab for managing workstation standards."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Top section - Workstation config and scan
        top_layout = QHBoxLayout()

        # Workstation selector
        workstation_group = QGroupBox("Workstation Configuration")
        workstation_layout = QHBoxLayout(workstation_group)

        workstation_layout.addWidget(QLabel("Configuration:"))
        self.config_combo = QComboBox()
        self.config_combo.setMinimumWidth(200)
        self.config_combo.addItem("Default Workstation")
        workstation_layout.addWidget(self.config_combo)

        self.save_config_btn = QPushButton("Save As...")
        workstation_layout.addWidget(self.save_config_btn)

        self.load_config_btn = QPushButton("Load")
        workstation_layout.addWidget(self.load_config_btn)

        workstation_layout.addStretch()
        top_layout.addWidget(workstation_group)

        # Scan controls
        scan_group = QGroupBox("Instrument Discovery")
        scan_layout = QHBoxLayout(scan_group)

        self.scan_btn = QPushButton("Scan for Instruments")
        self.scan_btn.clicked.connect(self._on_scan)
        scan_layout.addWidget(self.scan_btn)

        self.refresh_btn = QPushButton("Refresh Status")
        self.refresh_btn.clicked.connect(self._on_refresh)
        scan_layout.addWidget(self.refresh_btn)

        top_layout.addWidget(scan_group)

        layout.addLayout(top_layout)

        # Main content - Splitter with tables
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - Detected instruments
        detected_group = QGroupBox("Detected Instruments")
        detected_layout = QVBoxLayout(detected_group)

        self.detected_table = QTableWidget()
        self.detected_table.setColumnCount(5)
        self.detected_table.setHorizontalHeaderLabels(
            ["Address", "Manufacturer", "Model", "Serial", "Status"]
        )
        self.detected_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.detected_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        detected_layout.addWidget(self.detected_table)

        detected_btn_layout = QHBoxLayout()
        self.add_detected_btn = QPushButton("Add Selected to Workstation")
        self.add_detected_btn.clicked.connect(self._on_add_detected)
        detected_btn_layout.addWidget(self.add_detected_btn)

        self.query_idn_btn = QPushButton("Query *IDN?")
        self.query_idn_btn.clicked.connect(self._on_query_idn)
        detected_btn_layout.addWidget(self.query_idn_btn)

        detected_layout.addLayout(detected_btn_layout)

        splitter.addWidget(detected_group)

        # Right side - Workstation standards
        standards_group = QGroupBox("Workstation Standards")
        standards_layout = QVBoxLayout(standards_group)

        # Group filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter by Group:"))
        self.group_filter = QComboBox()
        self.group_filter.addItems(["All", "Calibrator", "DMM", "Counter", "Other"])
        self.group_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.group_filter)
        filter_layout.addStretch()
        standards_layout.addLayout(filter_layout)

        self.standards_table = QTableWidget()
        self.standards_table.setColumnCount(7)
        self.standards_table.setHorizontalHeaderLabels(
            ["Group", "Make", "Model", "Serial", "STD ID", "Address", "Status"]
        )
        self.standards_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.standards_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        standards_layout.addWidget(self.standards_table)

        standards_btn_layout = QHBoxLayout()

        self.add_manual_btn = QPushButton("Add Manual...")
        self.add_manual_btn.clicked.connect(self._on_add_manual)
        standards_btn_layout.addWidget(self.add_manual_btn)

        self.edit_btn = QPushButton("Edit...")
        self.edit_btn.clicked.connect(self._on_edit_standard)
        standards_btn_layout.addWidget(self.edit_btn)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._on_remove_standard)
        standards_btn_layout.addWidget(self.remove_btn)

        self.command_bank_btn = QPushButton("Command Bank...")
        self.command_bank_btn.clicked.connect(self._on_command_bank)
        standards_btn_layout.addWidget(self.command_bank_btn)

        standards_layout.addLayout(standards_btn_layout)

        splitter.addWidget(standards_group)

        layout.addWidget(splitter)

    def _on_scan(self):
        """Scan for connected instruments."""
        logger.info("Scanning for instruments")
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning...")

        # TODO: Implement actual VISA scan
        # For now, add placeholder data
        self.detected_table.setRowCount(0)

        # Placeholder - would be replaced with actual scan results
        sample_data = [
            ("GPIB0::22::INSTR", "FLUKE", "5520A", "1234567", "Connected"),
            ("GPIB0::24::INSTR", "Agilent", "3458A", "MY12345678", "Connected"),
        ]

        for address, mfr, model, serial, status in sample_data:
            row = self.detected_table.rowCount()
            self.detected_table.insertRow(row)
            self.detected_table.setItem(row, 0, QTableWidgetItem(address))
            self.detected_table.setItem(row, 1, QTableWidgetItem(mfr))
            self.detected_table.setItem(row, 2, QTableWidgetItem(model))
            self.detected_table.setItem(row, 3, QTableWidgetItem(serial))
            self.detected_table.setItem(row, 4, QTableWidgetItem(status))

        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan for Instruments")
        logger.info(f"Found {self.detected_table.rowCount()} instruments")

    def _on_refresh(self):
        """Refresh status of workstation standards."""
        logger.info("Refreshing standard status")
        # TODO: Implement status refresh

    def _on_add_detected(self):
        """Add selected detected instrument to workstation."""
        selected = self.detected_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select an instrument to add.")
            return

        row = selected[0].row()
        address = self.detected_table.item(row, 0).text()
        mfr = self.detected_table.item(row, 1).text()
        model = self.detected_table.item(row, 2).text()
        serial = self.detected_table.item(row, 3).text()

        logger.info(f"Adding standard: {mfr} {model} ({serial}) at {address}")
        # TODO: Open dialog to complete standard info and save

    def _on_query_idn(self):
        """Query *IDN? for selected instrument."""
        selected = self.detected_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select an instrument to query.")
            return

        row = selected[0].row()
        address = self.detected_table.item(row, 0).text()
        logger.info(f"Querying *IDN? at {address}")
        # TODO: Implement actual query

    def _on_filter_changed(self, filter_text: str):
        """Handle group filter change."""
        logger.debug(f"Filter changed to: {filter_text}")
        # TODO: Filter standards table

    def _on_add_manual(self):
        """Open dialog to manually add a standard."""
        logger.info("Opening add standard dialog")
        # TODO: Implement add dialog

    def _on_edit_standard(self):
        """Edit selected standard."""
        selected = self.standards_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a standard to edit.")
            return

        logger.info("Opening edit standard dialog")
        # TODO: Implement edit dialog

    def _on_remove_standard(self):
        """Remove selected standard from workstation."""
        selected = self.standards_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a standard to remove.")
            return

        reply = QMessageBox.question(
            self,
            "Remove Standard",
            "Remove this standard from the workstation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            row = selected[0].row()
            self.standards_table.removeRow(row)
            logger.info("Standard removed from workstation")

    def _on_command_bank(self):
        """Open command bank for selected standard."""
        selected = self.standards_table.selectedItems()
        if not selected:
            QMessageBox.warning(
                self, "No Selection", "Please select a standard to view command bank."
            )
            return

        logger.info("Opening command bank dialog")
        # TODO: Implement command bank dialog
