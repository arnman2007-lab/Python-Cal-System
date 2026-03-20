"""
Test execution tab - where calibrations are performed.
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
    QProgressBar,
    QFrame,
    QTextEdit,
    QFormLayout,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from loguru import logger


class ExecutionTab(QWidget):
    """Tab for executing calibration procedures."""

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Session setup bar
        setup_group = QGroupBox("Session Setup")
        setup_layout = QHBoxLayout(setup_group)

        setup_layout.addWidget(QLabel("DUT:"))
        self.dut_combo = QComboBox()
        self.dut_combo.setMinimumWidth(200)
        self.dut_combo.setEditable(True)
        self.dut_combo.setPlaceholderText("Select or enter asset number...")
        setup_layout.addWidget(self.dut_combo)

        setup_layout.addWidget(QLabel("Work Order:"))
        self.workorder_input = QLineEdit()
        self.workorder_input.setMaximumWidth(150)
        setup_layout.addWidget(self.workorder_input)

        setup_layout.addWidget(QLabel("Procedure:"))
        self.procedure_combo = QComboBox()
        self.procedure_combo.setMinimumWidth(200)
        setup_layout.addWidget(self.procedure_combo)

        setup_layout.addStretch()

        self.start_btn = QPushButton("Start Session")
        self.start_btn.clicked.connect(self._on_start_session)
        setup_layout.addWidget(self.start_btn)

        layout.addWidget(setup_group)

        # Main execution area
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - Current test and status
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Current test point display
        current_group = QGroupBox("Current Test Point")
        current_layout = QVBoxLayout(current_group)

        # Big display for nominal value
        self.nominal_display = QLabel("-- V")
        self.nominal_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(36)
        font.setBold(True)
        self.nominal_display.setFont(font)
        self.nominal_display.setStyleSheet(
            "QLabel { background-color: #2d2d2d; color: #00ff00; "
            "padding: 20px; border-radius: 10px; }"
        )
        current_layout.addWidget(self.nominal_display)

        # Test info
        info_layout = QFormLayout()
        self.section_label = QLabel("--")
        info_layout.addRow("Section:", self.section_label)

        self.testpoint_label = QLabel("--")
        info_layout.addRow("Test Point:", self.testpoint_label)

        self.tolerance_label = QLabel("--")
        info_layout.addRow("Tolerance:", self.tolerance_label)

        current_layout.addLayout(info_layout)

        left_layout.addWidget(current_group)

        # Instrument status
        status_group = QGroupBox("Instrument Status")
        status_layout = QVBoxLayout(status_group)

        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setMaximumHeight(100)
        self.status_display.setPlaceholderText("Instrument status will appear here...")
        status_layout.addWidget(self.status_display)

        left_layout.addWidget(status_group)

        # Wiring diagram placeholder
        wiring_group = QGroupBox("Wiring Diagram")
        wiring_layout = QVBoxLayout(wiring_group)

        self.wiring_label = QLabel("No wiring diagram available")
        self.wiring_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wiring_label.setMinimumHeight(150)
        self.wiring_label.setStyleSheet(
            "QLabel { background-color: #f0f0f0; border: 1px solid #ccc; }"
        )
        wiring_layout.addWidget(self.wiring_label)

        left_layout.addWidget(wiring_group)

        # Input method selection and reading
        input_group = QGroupBox("Reading Input")
        input_layout = QVBoxLayout(input_group)

        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("Input Method:"))
        self.input_method_combo = QComboBox()
        self.input_method_combo.addItems(["Keyboard Entry", "Remote Reading", "Webcam OCR"])
        self.input_method_combo.currentTextChanged.connect(self._on_input_method_changed)
        method_layout.addWidget(self.input_method_combo)
        method_layout.addStretch()
        input_layout.addLayout(method_layout)

        # Reading entry
        reading_layout = QHBoxLayout()
        self.reading_input = QLineEdit()
        self.reading_input.setPlaceholderText("Enter reading...")
        font = QFont()
        font.setPointSize(18)
        self.reading_input.setFont(font)
        self.reading_input.returnPressed.connect(self._on_submit_reading)
        reading_layout.addWidget(self.reading_input)

        self.submit_btn = QPushButton("Submit")
        self.submit_btn.clicked.connect(self._on_submit_reading)
        reading_layout.addWidget(self.submit_btn)

        self.get_reading_btn = QPushButton("Get Remote")
        self.get_reading_btn.clicked.connect(self._on_get_remote_reading)
        self.get_reading_btn.setVisible(False)
        reading_layout.addWidget(self.get_reading_btn)

        self.capture_btn = QPushButton("Capture OCR")
        self.capture_btn.clicked.connect(self._on_capture_ocr)
        self.capture_btn.setVisible(False)
        reading_layout.addWidget(self.capture_btn)

        input_layout.addLayout(reading_layout)

        left_layout.addWidget(input_group)

        # Control buttons
        control_layout = QHBoxLayout()

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self._on_pause)
        control_layout.addWidget(self.pause_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("QPushButton { background-color: #ff6b6b; }")
        self.stop_btn.clicked.connect(self._on_stop)
        control_layout.addWidget(self.stop_btn)

        control_layout.addStretch()

        self.skip_btn = QPushButton("Skip")
        self.skip_btn.clicked.connect(self._on_skip)
        control_layout.addWidget(self.skip_btn)

        self.redo_btn = QPushButton("Redo")
        self.redo_btn.clicked.connect(self._on_redo)
        control_layout.addWidget(self.redo_btn)

        left_layout.addLayout(control_layout)

        main_splitter.addWidget(left_widget)

        # Right panel - Test point list and progress
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Progress bar
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFormat("%v / %m (%p%)")
        progress_layout.addWidget(self.progress_bar)

        progress_stats = QHBoxLayout()
        self.pass_label = QLabel("Pass: 0")
        self.pass_label.setStyleSheet("QLabel { color: green; font-weight: bold; }")
        progress_stats.addWidget(self.pass_label)

        self.fail_label = QLabel("Fail: 0")
        self.fail_label.setStyleSheet("QLabel { color: red; font-weight: bold; }")
        progress_stats.addWidget(self.fail_label)

        self.pending_label = QLabel("Pending: 0")
        progress_stats.addWidget(self.pending_label)

        progress_stats.addStretch()
        progress_layout.addLayout(progress_stats)

        right_layout.addWidget(progress_group)

        # Test points table
        points_group = QGroupBox("Test Points")
        points_layout = QVBoxLayout(points_group)

        self.testpoints_table = QTableWidget()
        self.testpoints_table.setColumnCount(5)
        self.testpoints_table.setHorizontalHeaderLabels(
            ["#", "Section / Test", "Nominal", "Measured", "Status"]
        )
        self.testpoints_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.testpoints_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.testpoints_table.itemDoubleClicked.connect(self._on_testpoint_double_clicked)
        points_layout.addWidget(self.testpoints_table)

        right_layout.addWidget(points_group)

        main_splitter.addWidget(right_widget)

        # Set splitter sizes
        main_splitter.setSizes([500, 400])

        layout.addWidget(main_splitter)

    def _on_start_session(self):
        """Start calibration session."""
        dut = self.dut_combo.currentText().strip()
        workorder = self.workorder_input.text().strip()
        procedure = self.procedure_combo.currentText()

        if not dut:
            QMessageBox.warning(self, "Validation Error", "Please select or enter a DUT.")
            return

        if not workorder:
            QMessageBox.warning(self, "Validation Error", "Work order is required.")
            return

        if not procedure:
            QMessageBox.warning(self, "Validation Error", "Please select a procedure.")
            return

        logger.info(f"Starting session: DUT={dut}, WO={workorder}, Procedure={procedure}")

        # Update UI for running state
        self.start_btn.setText("Session Running")
        self.start_btn.setEnabled(False)
        self.dut_combo.setEnabled(False)
        self.workorder_input.setEnabled(False)
        self.procedure_combo.setEnabled(False)

        # TODO: Load procedure and start execution
        self._load_sample_testpoints()

    def _load_sample_testpoints(self):
        """Load sample test points for demonstration."""
        # Sample data
        testpoints = [
            ("DC Voltage", "1.0 V", "", "Pending"),
            ("DC Voltage", "10.0 V", "", "Pending"),
            ("DC Voltage", "100.0 V", "", "Pending"),
            ("AC Voltage", "1.0 V 60 Hz", "", "Pending"),
            ("AC Voltage", "10.0 V 60 Hz", "", "Pending"),
        ]

        self.testpoints_table.setRowCount(len(testpoints))
        self.progress_bar.setMaximum(len(testpoints))
        self.progress_bar.setValue(0)
        self.pending_label.setText(f"Pending: {len(testpoints)}")

        for i, (section, nominal, measured, status) in enumerate(testpoints):
            self.testpoints_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.testpoints_table.setItem(i, 1, QTableWidgetItem(section))
            self.testpoints_table.setItem(i, 2, QTableWidgetItem(nominal))
            self.testpoints_table.setItem(i, 3, QTableWidgetItem(measured))
            self.testpoints_table.setItem(i, 4, QTableWidgetItem(status))

        # Select first test point
        self.testpoints_table.selectRow(0)
        self._update_current_display(0)

    def _update_current_display(self, row: int):
        """Update the current test point display."""
        section = self.testpoints_table.item(row, 1).text()
        nominal = self.testpoints_table.item(row, 2).text()

        self.section_label.setText(section)
        self.testpoint_label.setText(f"Point {row + 1}")
        self.nominal_display.setText(nominal)
        self.tolerance_label.setText("± 0.1%")

        self.status_display.append(f"Setting output: {nominal}")

    def _on_input_method_changed(self, method: str):
        """Handle input method change."""
        self.reading_input.setVisible(method == "Keyboard Entry")
        self.submit_btn.setVisible(method == "Keyboard Entry")
        self.get_reading_btn.setVisible(method == "Remote Reading")
        self.capture_btn.setVisible(method == "Webcam OCR")
        logger.debug(f"Input method changed to: {method}")

    def _on_submit_reading(self):
        """Submit keyboard reading."""
        reading = self.reading_input.text().strip()
        if not reading:
            return

        logger.info(f"Reading submitted: {reading}")
        self._process_reading(reading)
        self.reading_input.clear()

    def _on_get_remote_reading(self):
        """Get reading from remote device."""
        logger.info("Getting remote reading")
        # TODO: Implement remote reading
        self.status_display.append("Querying DUT for reading...")

    def _on_capture_ocr(self):
        """Capture reading via webcam OCR."""
        logger.info("Capturing OCR reading")
        # TODO: Implement OCR capture

    def _process_reading(self, reading: str):
        """Process a reading and determine pass/fail."""
        selected = self.testpoints_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()

        # Update table
        self.testpoints_table.setItem(row, 3, QTableWidgetItem(reading))

        # Determine pass/fail (simplified for demo)
        try:
            value = float(reading)
            status = "Pass"  # Would compare to tolerance
            color = QColor(144, 238, 144)  # Light green
        except ValueError:
            status = "Fail"
            color = QColor(255, 182, 193)  # Light red

        status_item = QTableWidgetItem(status)
        status_item.setBackground(color)
        self.testpoints_table.setItem(row, 4, status_item)

        # Update progress
        self.progress_bar.setValue(row + 1)

        # Check if pass or fail and handle accordingly
        if status == "Fail":
            self._show_fail_dialog(row, reading)
        else:
            self._advance_to_next(row)

    def _show_fail_dialog(self, row: int, reading: str):
        """Show dialog when test point fails."""
        reply = QMessageBox.question(
            self,
            "Test Point Failed",
            f"Test point {row + 1} failed.\n\n"
            f"Measured: {reading}\n\n"
            "What would you like to do?",
            QMessageBox.StandardButton.Retry
            | QMessageBox.StandardButton.Ignore
            | QMessageBox.StandardButton.Abort,
        )

        if reply == QMessageBox.StandardButton.Retry:
            # Redo this test point
            self.reading_input.setFocus()
        elif reply == QMessageBox.StandardButton.Ignore:
            # Continue to next
            self._advance_to_next(row)
        else:
            # Stop session
            self._on_stop()

    def _advance_to_next(self, current_row: int):
        """Advance to next test point."""
        next_row = current_row + 1
        if next_row < self.testpoints_table.rowCount():
            self.testpoints_table.selectRow(next_row)
            self._update_current_display(next_row)
        else:
            self._session_complete()

    def _session_complete(self):
        """Handle session completion."""
        logger.info("Calibration session complete")
        QMessageBox.information(
            self,
            "Session Complete",
            "All test points have been completed.\n\n"
            "You can now generate a report from the Reports tab.",
        )

    def _on_pause(self):
        """Pause the session."""
        if self.pause_btn.text() == "Pause":
            logger.info("Session paused")
            self.pause_btn.setText("Resume")
            self.status_display.append("Session paused")
        else:
            logger.info("Session resumed")
            self.pause_btn.setText("Pause")
            self.status_display.append("Session resumed")

    def _on_stop(self):
        """Stop the session."""
        reply = QMessageBox.question(
            self,
            "Stop Session",
            "Are you sure you want to stop this session?\n\n"
            "Progress will be saved and you can resume later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Session stopped")
            self.start_btn.setText("Start Session")
            self.start_btn.setEnabled(True)
            self.dut_combo.setEnabled(True)
            self.workorder_input.setEnabled(True)
            self.procedure_combo.setEnabled(True)

    def _on_skip(self):
        """Skip current test point."""
        selected = self.testpoints_table.selectedItems()
        if selected:
            row = selected[0].row()
            self.testpoints_table.setItem(row, 4, QTableWidgetItem("Skipped"))
            logger.info(f"Skipped test point {row + 1}")
            self._advance_to_next(row)

    def _on_redo(self):
        """Redo current or selected test point."""
        selected = self.testpoints_table.selectedItems()
        if selected:
            row = selected[0].row()
            logger.info(f"Redoing test point {row + 1}")
            self.testpoints_table.setItem(row, 3, QTableWidgetItem(""))
            self.testpoints_table.setItem(row, 4, QTableWidgetItem("Pending"))
            self._update_current_display(row)
            self.reading_input.setFocus()

    def _on_testpoint_double_clicked(self, item):
        """Handle double-click on test point."""
        row = item.row()
        logger.debug(f"Double-clicked test point {row + 1}")
        self._update_current_display(row)
