"""
DUT (Device Under Test) management tab.
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
    QTextEdit,
    QTabWidget,
    QFormLayout,
    QComboBox,
    QCheckBox,
    QSpinBox,
    QDateEdit,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QDate
from loguru import logger


class DUTTab(QWidget):
    """Tab for managing Devices Under Test."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Enter asset number, make, model, or serial number..."
        )
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._on_search_click)
        search_layout.addWidget(self.search_btn)

        layout.addLayout(search_layout)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left - DUT list
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        # Upcoming due section
        due_group = QGroupBox("Calibrations Due")
        due_layout = QVBoxLayout(due_group)

        due_filter = QHBoxLayout()
        due_filter.addWidget(QLabel("Show:"))
        self.due_filter_combo = QComboBox()
        self.due_filter_combo.addItems(["Overdue", "Due This Week", "Due This Month", "All"])
        due_filter.addWidget(self.due_filter_combo)
        due_filter.addStretch()
        due_layout.addLayout(due_filter)

        self.due_table = QTableWidget()
        self.due_table.setColumnCount(4)
        self.due_table.setHorizontalHeaderLabels(
            ["Asset Number", "Make/Model", "Due Date", "Status"]
        )
        self.due_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.due_table.setMaximumHeight(150)
        self.due_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.due_table.itemDoubleClicked.connect(self._on_due_item_double_clicked)
        due_layout.addWidget(self.due_table)

        list_layout.addWidget(due_group)

        # All DUTs section
        all_group = QGroupBox("All Devices Under Test")
        all_layout = QVBoxLayout(all_group)

        self.dut_table = QTableWidget()
        self.dut_table.setColumnCount(6)
        self.dut_table.setHorizontalHeaderLabels(
            ["Asset Number", "Make", "Model", "Serial", "Last Cal", "Due Date"]
        )
        self.dut_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.dut_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.dut_table.itemSelectionChanged.connect(self._on_dut_selected)
        all_layout.addWidget(self.dut_table)

        btn_layout = QHBoxLayout()
        self.add_dut_btn = QPushButton("Add New DUT")
        self.add_dut_btn.clicked.connect(self._on_add_dut)
        btn_layout.addWidget(self.add_dut_btn)

        self.delete_dut_btn = QPushButton("Delete")
        self.delete_dut_btn.clicked.connect(self._on_delete_dut)
        btn_layout.addWidget(self.delete_dut_btn)

        btn_layout.addStretch()

        self.start_cal_btn = QPushButton("Start Calibration")
        self.start_cal_btn.clicked.connect(self._on_start_calibration)
        btn_layout.addWidget(self.start_cal_btn)

        all_layout.addLayout(btn_layout)

        list_layout.addWidget(all_group)

        splitter.addWidget(list_widget)

        # Right - DUT details
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)

        self.details_tabs = QTabWidget()

        # Info tab
        info_tab = QWidget()
        info_layout = QFormLayout(info_tab)

        self.asset_input = QLineEdit()
        info_layout.addRow("Asset Number:", self.asset_input)

        self.make_input = QLineEdit()
        info_layout.addRow("Make:", self.make_input)

        self.model_input = QLineEdit()
        info_layout.addRow("Model:", self.model_input)

        self.serial_input = QLineEdit()
        info_layout.addRow("Serial Number:", self.serial_input)

        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(80)
        info_layout.addRow("Description:", self.description_input)

        self.details_tabs.addTab(info_tab, "Information")

        # Capabilities tab
        cap_tab = QWidget()
        cap_layout = QFormLayout(cap_tab)

        self.remote_capable_check = QCheckBox("Device supports remote control")
        cap_layout.addRow("Remote Capable:", self.remote_capable_check)

        self.input_method_combo = QComboBox()
        self.input_method_combo.addItems(["Keyboard Entry", "Remote Reading", "Webcam OCR"])
        cap_layout.addRow("Preferred Input:", self.input_method_combo)

        self.ocr_mode_combo = QComboBox()
        self.ocr_mode_combo.addItems(["Standard OCR", "Seven-Segment OCR"])
        cap_layout.addRow("OCR Mode:", self.ocr_mode_combo)

        self.details_tabs.addTab(cap_tab, "Capabilities")

        # Calibration tab
        cal_tab = QWidget()
        cal_layout = QFormLayout(cal_tab)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 3650)
        self.interval_spin.setValue(365)
        self.interval_spin.setSuffix(" days")
        cal_layout.addRow("Cal Interval:", self.interval_spin)

        self.last_cal_date = QDateEdit()
        self.last_cal_date.setCalendarPopup(True)
        self.last_cal_date.setDate(QDate.currentDate())
        cal_layout.addRow("Last Calibration:", self.last_cal_date)

        self.due_date = QDateEdit()
        self.due_date.setCalendarPopup(True)
        cal_layout.addRow("Next Due:", self.due_date)

        self.procedure_combo = QComboBox()
        self.procedure_combo.addItem("(No procedure assigned)")
        cal_layout.addRow("Assigned Procedure:", self.procedure_combo)

        self.details_tabs.addTab(cal_tab, "Calibration")

        # History tab
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(
            ["Date", "Work Order", "Technician", "Result"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        history_layout.addWidget(self.history_table)

        history_btn_layout = QHBoxLayout()
        self.view_report_btn = QPushButton("View Report")
        history_btn_layout.addWidget(self.view_report_btn)
        history_btn_layout.addStretch()
        history_layout.addLayout(history_btn_layout)

        self.details_tabs.addTab(history_tab, "History")

        details_layout.addWidget(self.details_tabs)

        # Save/Cancel buttons
        save_layout = QHBoxLayout()
        save_layout.addStretch()

        self.save_btn = QPushButton("Save Changes")
        self.save_btn.clicked.connect(self._on_save)
        save_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        save_layout.addWidget(self.cancel_btn)

        details_layout.addLayout(save_layout)

        splitter.addWidget(details_widget)

        # Set splitter sizes
        splitter.setSizes([400, 400])

        layout.addWidget(splitter)

    def _on_search(self, text: str):
        """Handle search text change."""
        # TODO: Implement search filtering
        pass

    def _on_search_click(self):
        """Handle search button click."""
        search_text = self.search_input.text()
        logger.info(f"Searching for: {search_text}")
        # TODO: Implement search

    def _on_due_item_double_clicked(self, item):
        """Handle double-click on due item."""
        row = item.row()
        asset = self.due_table.item(row, 0).text()
        logger.info(f"Loading DUT: {asset}")
        # TODO: Load DUT details

    def _on_dut_selected(self):
        """Handle DUT selection change."""
        selected = self.dut_table.selectedItems()
        if selected:
            row = selected[0].row()
            asset = self.dut_table.item(row, 0).text()
            logger.debug(f"Selected DUT: {asset}")
            # TODO: Load DUT details into form

    def _on_add_dut(self):
        """Add a new DUT."""
        logger.info("Adding new DUT")
        # Clear form for new entry
        self.asset_input.clear()
        self.make_input.clear()
        self.model_input.clear()
        self.serial_input.clear()
        self.description_input.clear()
        self.asset_input.setFocus()

    def _on_delete_dut(self):
        """Delete selected DUT."""
        selected = self.dut_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a DUT to delete.")
            return

        row = selected[0].row()
        asset = self.dut_table.item(row, 0).text()

        reply = QMessageBox.question(
            self,
            "Delete DUT",
            f"Are you sure you want to delete DUT {asset}?\n\n"
            "This will also delete all calibration history for this device.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info(f"Deleting DUT: {asset}")
            # TODO: Delete from database

    def _on_start_calibration(self):
        """Start calibration for selected DUT."""
        selected = self.dut_table.selectedItems()
        if not selected:
            QMessageBox.warning(
                self, "No Selection", "Please select a DUT to calibrate."
            )
            return

        row = selected[0].row()
        asset = self.dut_table.item(row, 0).text()
        logger.info(f"Starting calibration for: {asset}")
        # TODO: Switch to execution tab with this DUT

    def _on_save(self):
        """Save DUT changes."""
        asset = self.asset_input.text().strip()
        if not asset:
            QMessageBox.warning(self, "Validation Error", "Asset number is required.")
            return

        logger.info(f"Saving DUT: {asset}")
        # TODO: Save to database

    def _on_cancel(self):
        """Cancel changes."""
        logger.debug("Canceling DUT changes")
        # TODO: Reload original data
