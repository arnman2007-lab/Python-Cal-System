"""
Test execution tab - where calibrations are performed.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

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

from calsystem.database.connection import get_db
from calsystem.database.models import (
    DUT,
    Procedure,
    CalibrationSession,
    TestSection,
    TestPoint,
    TestResult,
    SessionStatus,
)
from calsystem.config.settings import get_settings


class ExecutionTab(QWidget):
    """Tab for executing calibration procedures."""

    def __init__(self):
        super().__init__()
        self._current_session_id: Optional[int] = None
        self._current_dut_id: Optional[int] = None
        self._current_procedure_id: Optional[int] = None
        self._test_points: List[Dict[str, Any]] = []
        self._current_test_index: int = 0
        self._init_ui()
        self._connect_signals()

    def showEvent(self, event):
        """Called when tab becomes visible."""
        super().showEvent(event)
        self._load_duts()
        self._load_procedures()

    def _connect_signals(self):
        """Connect additional signals."""
        self.dut_combo.currentIndexChanged.connect(self._on_dut_selected)

    def _load_duts(self):
        """Load DUTs into combo."""
        current_text = self.dut_combo.currentText()
        self.dut_combo.clear()

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                duts = session.query(DUT).order_by(DUT.asset_number).all()
                for dut in duts:
                    label = f"{dut.asset_number} - {dut.make} {dut.model}"
                    self.dut_combo.addItem(label, dut.id)

                # Restore selection if text matches
                if current_text:
                    idx = self.dut_combo.findText(current_text, Qt.MatchFlag.MatchStartsWith)
                    if idx >= 0:
                        self.dut_combo.setCurrentIndex(idx)

        except Exception as e:
            logger.error(f"Failed to load DUTs: {e}")

    def _load_procedures(self):
        """Load procedures into combo."""
        current_data = self.procedure_combo.currentData()
        self.procedure_combo.clear()

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                procedures = session.query(Procedure).order_by(Procedure.name).all()
                for proc in procedures:
                    label = proc.name
                    if proc.target_make or proc.target_model:
                        label += f" ({proc.target_make or ''} {proc.target_model or ''})".strip()
                    self.procedure_combo.addItem(label, proc.id)

                # Restore selection
                if current_data:
                    for i in range(self.procedure_combo.count()):
                        if self.procedure_combo.itemData(i) == current_data:
                            self.procedure_combo.setCurrentIndex(i)
                            break

        except Exception as e:
            logger.error(f"Failed to load procedures: {e}")

    def _on_dut_selected(self, index: int):
        """Handle DUT selection - auto-select assigned procedure."""
        dut_id = self.dut_combo.currentData()
        if not dut_id:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                dut = session.query(DUT).filter(DUT.id == dut_id).first()
                if dut and dut.default_procedure_id:
                    # Select the assigned procedure
                    for i in range(self.procedure_combo.count()):
                        if self.procedure_combo.itemData(i) == dut.default_procedure_id:
                            self.procedure_combo.setCurrentIndex(i)
                            logger.debug(f"Auto-selected procedure for DUT {dut.asset_number}")
                            break

                    # Set input method based on DUT preference
                    if dut.preferred_input_method:
                        method_map = {
                            "keyboard": 0,
                            "remote": 1,
                            "webcam": 2,
                        }
                        idx = method_map.get(dut.preferred_input_method.value, 0)
                        self.input_method_combo.setCurrentIndex(idx)

        except Exception as e:
            logger.error(f"Failed to load DUT preferences: {e}")

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
        dut_id = self.dut_combo.currentData()
        workorder = self.workorder_input.text().strip()
        procedure_id = self.procedure_combo.currentData()

        if not dut_id:
            QMessageBox.warning(self, "Validation Error", "Please select a DUT.")
            return

        if not workorder:
            QMessageBox.warning(self, "Validation Error", "Work order is required.")
            return

        if not procedure_id:
            QMessageBox.warning(self, "Validation Error", "Please select a procedure.")
            return

        db = get_db()
        if not db.is_connected:
            QMessageBox.critical(self, "Database Error", "Not connected to database.")
            return

        try:
            with db.session() as session:
                # Get technician from settings
                settings = get_settings()
                technician = getattr(settings, 'technician_name', None) or 'Unknown'

                # Create calibration session
                cal_session = CalibrationSession(
                    dut_id=dut_id,
                    procedure_id=procedure_id,
                    work_order=workorder,
                    technician=technician,
                    started_at=datetime.now(),
                    status=SessionStatus.in_progress,
                )
                session.add(cal_session)
                session.flush()

                self._current_session_id = cal_session.id
                self._current_dut_id = dut_id
                self._current_procedure_id = procedure_id

                logger.info(f"Started session {cal_session.id}: DUT={dut_id}, WO={workorder}")

            # Update UI for running state
            self.start_btn.setText("Session Running")
            self.start_btn.setEnabled(False)
            self.dut_combo.setEnabled(False)
            self.workorder_input.setEnabled(False)
            self.procedure_combo.setEnabled(False)

            # Load test points and start execution
            self._load_test_points()

        except Exception as e:
            logger.error(f"Failed to start session: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start session:\n{e}")

    def _load_test_points(self):
        """Load test points from procedure into the table."""
        if not self._current_procedure_id:
            return

        db = get_db()
        if not db.is_connected:
            return

        self._test_points = []
        self.testpoints_table.setRowCount(0)

        try:
            with db.session() as session:
                procedure = session.query(Procedure).filter(
                    Procedure.id == self._current_procedure_id
                ).first()

                if not procedure:
                    QMessageBox.warning(self, "Error", "Procedure not found.")
                    return

                # Load all sections and test points
                for section in procedure.sections:
                    for tp in section.test_points:
                        self._test_points.append({
                            "id": tp.id,
                            "section_id": section.id,
                            "section_name": section.name,
                            "description": tp.description or f"{tp.nominal_value} {tp.unit}",
                            "nominal_value": tp.nominal_value,
                            "unit": tp.unit,
                            "frequency": tp.frequency,
                            "tolerance_value": tp.tolerance_value,
                            "tolerance_type": tp.tolerance_type.value if tp.tolerance_type else "percent",
                            "source_command": tp.source_command,
                            "operate_command": tp.operate_command,
                            "measure_command": tp.measure_command,
                        })

        except Exception as e:
            logger.error(f"Failed to load test points: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load test points:\n{e}")
            return

        if not self._test_points:
            QMessageBox.warning(self, "No Test Points", "This procedure has no test points.")
            return

        # Populate table
        self.testpoints_table.setRowCount(len(self._test_points))
        self.progress_bar.setMaximum(len(self._test_points))
        self.progress_bar.setValue(0)
        self.pending_label.setText(f"Pending: {len(self._test_points)}")
        self.pass_label.setText("Pass: 0")
        self.fail_label.setText("Fail: 0")

        for i, tp in enumerate(self._test_points):
            # Number
            self.testpoints_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))

            # Section / Test
            section_test = f"{tp['section_name']} / {tp['description']}"
            self.testpoints_table.setItem(i, 1, QTableWidgetItem(section_test))

            # Nominal
            nominal_str = f"{tp['nominal_value']} {tp['unit']}"
            if tp.get('frequency'):
                nominal_str += f" @ {tp['frequency']} Hz"
            self.testpoints_table.setItem(i, 2, QTableWidgetItem(nominal_str))

            # Measured (empty)
            self.testpoints_table.setItem(i, 3, QTableWidgetItem(""))

            # Status
            self.testpoints_table.setItem(i, 4, QTableWidgetItem("Pending"))

        # Select first test point
        self._current_test_index = 0
        self.testpoints_table.selectRow(0)
        self._update_current_display(0)

        self.status_display.clear()
        self.status_display.append(f"Session started with {len(self._test_points)} test points")

    def _load_sample_testpoints(self):
        """Load sample test points for demonstration (deprecated)."""
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
        self._current_test_index = row

        # Get test point data if available
        if row < len(self._test_points):
            tp = self._test_points[row]
            self.section_label.setText(tp['section_name'])
            self.testpoint_label.setText(tp['description'])

            # Format nominal display
            nominal_str = f"{tp['nominal_value']} {tp['unit']}"
            self.nominal_display.setText(nominal_str)

            # Format tolerance
            tol_symbol = {
                "percent": "%",
                "absolute": "",
                "ppm": " PPM",
            }.get(tp['tolerance_type'], "%")
            self.tolerance_label.setText(f"± {tp['tolerance_value']}{tol_symbol}")

            self.status_display.append(f"Setting output: {nominal_str}")
        else:
            # Fallback to table data
            section = self.testpoints_table.item(row, 1).text() if self.testpoints_table.item(row, 1) else "--"
            nominal = self.testpoints_table.item(row, 2).text() if self.testpoints_table.item(row, 2) else "--"

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
        """Get reading from remote device via VISA."""
        logger.info("Getting remote reading")

        row = self._current_test_index
        if row >= len(self._test_points):
            QMessageBox.warning(self, "Error", "No test point selected.")
            return

        tp = self._test_points[row]

        # First send source command to calibrator if available
        if tp.get('source_command'):
            self.status_display.append(f"Setting source: {tp['source_command']}")
            # TODO: Send via VISAManager when calibrator address is known

        if tp.get('operate_command'):
            self.status_display.append(f"Sending operate: {tp['operate_command']}")
            # TODO: Send via VISAManager

        # Query DUT for measurement
        measure_cmd = tp.get('measure_command')
        if not measure_cmd:
            QMessageBox.warning(self, "No Command", "No measure command configured for this test point.")
            return

        self.status_display.append(f"Querying DUT: {measure_cmd}")

        # Try to get reading via VISA
        try:
            from calsystem.instruments.visa_manager import VISAManager

            visa_mgr = VISAManager()

            # Get DUT address from database
            db = get_db()
            if db.is_connected and self._current_dut_id:
                with db.session() as session:
                    dut = session.query(DUT).filter(DUT.id == self._current_dut_id).first()
                    if dut and hasattr(dut, 'visa_address') and dut.visa_address:
                        # Query the device
                        response = visa_mgr.query(dut.visa_address, measure_cmd)
                        if response:
                            # Parse numeric value from response
                            try:
                                value = float(response.strip())
                                self.reading_input.setText(str(value))
                                self.status_display.append(f"Received: {value}")
                                # Auto-submit if successful
                                self._on_submit_reading()
                                return
                            except ValueError:
                                self.status_display.append(f"Could not parse: {response}")
                        else:
                            self.status_display.append("No response from device")
                    else:
                        self.status_display.append("DUT has no VISA address configured")

            # Fallback: simulate a reading for demo
            self.status_display.append("(Demo mode - enter reading manually)")

        except ImportError:
            self.status_display.append("PyVISA not available - enter reading manually")
        except Exception as e:
            logger.error(f"Remote reading failed: {e}")
            self.status_display.append(f"Error: {e}")

    def _on_capture_ocr(self):
        """Capture reading via webcam OCR."""
        logger.info("Capturing OCR reading")

        try:
            from calsystem.ocr.webcam import WebcamCapture
            from calsystem.ocr.reader import OCRReader, SevenSegmentReader
        except ImportError:
            QMessageBox.warning(
                self, "Not Available",
                "OCR modules not available.\n\n"
                "Required: opencv-python, pytesseract"
            )
            return

        # Get DUT OCR mode
        ocr_mode = "standard"
        if self._current_dut_id:
            db = get_db()
            if db.is_connected:
                try:
                    with db.session() as session:
                        dut = session.query(DUT).filter(DUT.id == self._current_dut_id).first()
                        if dut:
                            ocr_mode = dut.ocr_mode or "standard"
                except Exception as e:
                    logger.error(f"Failed to get DUT OCR mode: {e}")

        self.status_display.append("Opening webcam...")

        try:
            # Create webcam capture dialog
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
            from PyQt6.QtCore import QTimer
            from PyQt6.QtGui import QImage, QPixmap
            import cv2
            import numpy as np

            dialog = QDialog(self)
            dialog.setWindowTitle("Capture OCR Reading")
            dialog.setMinimumSize(640, 520)

            layout = QVBoxLayout(dialog)

            # Video display
            video_label = QLabel("Initializing camera...")
            video_label.setMinimumSize(640, 480)
            video_label.setStyleSheet("background-color: black;")
            layout.addWidget(video_label)

            # Buttons
            btn_layout = QHBoxLayout()
            capture_btn = QPushButton("Capture")
            cancel_btn = QPushButton("Cancel")
            btn_layout.addWidget(capture_btn)
            btn_layout.addWidget(cancel_btn)
            layout.addLayout(btn_layout)

            cancel_btn.clicked.connect(dialog.reject)

            # Camera setup
            cap = cv2.VideoCapture(0)
            captured_frame = [None]

            def update_frame():
                ret, frame = cap.read()
                if ret:
                    # Convert to RGB for Qt
                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb_frame.shape
                    bytes_per_line = ch * w
                    qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                    video_label.setPixmap(QPixmap.fromImage(qt_image).scaled(
                        video_label.size(), Qt.AspectRatioMode.KeepAspectRatio
                    ))

            def on_capture():
                ret, frame = cap.read()
                if ret:
                    captured_frame[0] = frame
                    timer.stop()
                    cap.release()
                    dialog.accept()

            capture_btn.clicked.connect(on_capture)

            timer = QTimer()
            timer.timeout.connect(update_frame)
            timer.start(33)  # ~30 fps

            def on_close():
                timer.stop()
                cap.release()

            dialog.rejected.connect(on_close)

            if dialog.exec() == QDialog.DialogCode.Accepted and captured_frame[0] is not None:
                # Process captured frame with OCR
                self._process_ocr_image(captured_frame[0], ocr_mode)
            else:
                self.status_display.append("Capture cancelled")

        except Exception as e:
            logger.error(f"OCR capture failed: {e}")
            self.status_display.append(f"Capture failed: {e}")

    def _process_ocr_image(self, frame, ocr_mode: str):
        """Process captured image with OCR."""
        self.status_display.append("Processing OCR...")

        try:
            from calsystem.ocr.reader import OCRReader, SevenSegmentReader

            # Choose reader based on mode
            if ocr_mode == "seven_segment":
                reader = SevenSegmentReader()
            else:
                reader = OCRReader()

            # Convert frame to grayscale
            import cv2
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Try to extract reading
            result = reader.read(gray)

            if result:
                self.status_display.append(f"OCR result: {result}")
                self.reading_input.setText(result)
                self.reading_input.setFocus()
                self.reading_input.selectAll()
            else:
                self.status_display.append("Could not read display - enter manually")
                QMessageBox.warning(
                    self, "OCR Failed",
                    "Could not extract reading from image.\n\n"
                    "Please enter the reading manually."
                )

        except Exception as e:
            logger.error(f"OCR processing failed: {e}")
            self.status_display.append(f"OCR error: {e}")

    def _process_reading(self, reading: str):
        """Process a reading and determine pass/fail."""
        selected = self.testpoints_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()

        # Parse reading value
        try:
            measured_value = float(reading)
        except ValueError:
            QMessageBox.warning(self, "Invalid Reading", "Please enter a numeric value.")
            return

        # Update table with measured value
        self.testpoints_table.setItem(row, 3, QTableWidgetItem(reading))

        # Get test point data
        tp = self._test_points[row] if row < len(self._test_points) else None
        passed = False
        deviation = 0.0

        if tp:
            nominal = tp['nominal_value'] or 0
            tolerance = tp['tolerance_value'] or 0
            tol_type = tp['tolerance_type']

            deviation = measured_value - nominal

            # Calculate pass/fail based on tolerance type
            if tol_type == "percent":
                if nominal != 0:
                    percent_dev = abs(deviation / nominal) * 100
                    passed = percent_dev <= tolerance
                else:
                    passed = abs(deviation) <= tolerance
            elif tol_type == "absolute":
                passed = abs(deviation) <= tolerance
            elif tol_type == "ppm":
                if nominal != 0:
                    ppm_dev = abs(deviation / nominal) * 1000000
                    passed = ppm_dev <= tolerance
                else:
                    passed = abs(deviation) <= tolerance
            else:
                passed = True  # Default to pass if unknown type
        else:
            passed = True  # No test point data, assume pass

        status = "Pass" if passed else "Fail"
        color = QColor(144, 238, 144) if passed else QColor(255, 182, 193)

        status_item = QTableWidgetItem(status)
        status_item.setBackground(color)
        self.testpoints_table.setItem(row, 4, status_item)

        # Create TestResult record
        self._save_test_result(row, measured_value, passed)

        # Update progress statistics
        self._update_progress_stats()

        # Check if pass or fail and handle accordingly
        if not passed:
            self._show_fail_dialog(row, reading, deviation, tp)
        else:
            self._advance_to_next(row)

    def _save_test_result(self, row: int, measured_value: float, passed: bool):
        """Save test result to database."""
        if not self._current_session_id:
            return

        tp = self._test_points[row] if row < len(self._test_points) else None
        if not tp:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                # Get input method
                input_method_map = {
                    0: "keyboard",
                    1: "remote",
                    2: "webcam",
                }
                input_method = input_method_map.get(self.input_method_combo.currentIndex(), "keyboard")

                result = TestResult(
                    session_id=self._current_session_id,
                    test_point_id=tp['id'],
                    measured_value=measured_value,
                    status="pass" if passed else "fail",
                    input_method=input_method,
                    measured_at=datetime.now(),
                )
                session.add(result)

                logger.debug(f"Saved test result for point {row + 1}: {measured_value} ({result.status})")

        except Exception as e:
            logger.error(f"Failed to save test result: {e}")

    def _update_progress_stats(self):
        """Update pass/fail/pending statistics."""
        pass_count = 0
        fail_count = 0
        pending_count = 0

        for i in range(self.testpoints_table.rowCount()):
            status_item = self.testpoints_table.item(i, 4)
            if status_item:
                status = status_item.text()
                if status == "Pass":
                    pass_count += 1
                elif status == "Fail":
                    fail_count += 1
                else:
                    pending_count += 1

        self.pass_label.setText(f"Pass: {pass_count}")
        self.fail_label.setText(f"Fail: {fail_count}")
        self.pending_label.setText(f"Pending: {pending_count}")
        self.progress_bar.setValue(pass_count + fail_count)

    def _show_fail_dialog(self, row: int, reading: str, deviation: float = 0, tp: dict = None):
        """Show dialog when test point fails."""
        nominal = tp['nominal_value'] if tp else 0
        tolerance = tp['tolerance_value'] if tp else 0
        tol_type = tp['tolerance_type'] if tp else "percent"

        tol_symbol = {"percent": "%", "absolute": "", "ppm": " PPM"}.get(tol_type, "%")

        msg = f"Test point {row + 1} failed.\n\n"
        msg += f"Nominal: {nominal} {tp['unit'] if tp else ''}\n"
        msg += f"Measured: {reading}\n"
        msg += f"Deviation: {deviation:+.6g}\n"
        msg += f"Tolerance: ± {tolerance}{tol_symbol}\n\n"
        msg += "What would you like to do?"

        reply = QMessageBox.question(
            self,
            "Test Point Failed",
            msg,
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
            self.reading_input.clear()
            self.reading_input.setFocus()
        else:
            self._session_complete()

    def _session_complete(self):
        """Handle session completion."""
        logger.info("Calibration session complete")

        # Calculate overall result
        fail_count = 0
        for i in range(self.testpoints_table.rowCount()):
            status_item = self.testpoints_table.item(i, 4)
            if status_item and status_item.text() == "Fail":
                fail_count += 1

        overall_result = "Pass" if fail_count == 0 else "Fail"

        # Update session in database
        self._complete_session(overall_result)

        # Re-enable UI
        self.start_btn.setText("Start Session")
        self.start_btn.setEnabled(True)
        self.dut_combo.setEnabled(True)
        self.workorder_input.setEnabled(True)
        self.procedure_combo.setEnabled(True)

        QMessageBox.information(
            self,
            "Session Complete",
            f"All test points have been completed.\n\n"
            f"Overall Result: {overall_result}\n\n"
            "You can now generate a report from the Reports tab.",
        )

    def _complete_session(self, overall_result: str):
        """Mark session as completed in database."""
        if not self._current_session_id:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                cal_session = session.query(CalibrationSession).filter(
                    CalibrationSession.id == self._current_session_id
                ).first()

                if cal_session:
                    cal_session.status = SessionStatus.completed
                    cal_session.completed_at = datetime.now()
                    cal_session.overall_result = overall_result.lower()

                    # Update DUT last calibration date if passed
                    if overall_result == "Pass" and self._current_dut_id:
                        dut = session.query(DUT).filter(DUT.id == self._current_dut_id).first()
                        if dut:
                            dut.last_calibration_date = datetime.now()
                            if dut.calibration_interval_days:
                                from datetime import timedelta
                                dut.next_due_date = datetime.now() + timedelta(days=dut.calibration_interval_days)

                    logger.info(f"Session {self._current_session_id} completed: {overall_result}")

        except Exception as e:
            logger.error(f"Failed to complete session: {e}")

    def _on_pause(self):
        """Pause or resume the session."""
        if self.pause_btn.text() == "Pause":
            self._pause_session()
        else:
            self._resume_session()

    def _pause_session(self):
        """Pause the session."""
        logger.info("Session paused")
        self.pause_btn.setText("Resume")
        self.status_display.append("Session paused")

        # Update database
        if self._current_session_id:
            db = get_db()
            if db.is_connected:
                try:
                    with db.session() as session:
                        cal_session = session.query(CalibrationSession).filter(
                            CalibrationSession.id == self._current_session_id
                        ).first()
                        if cal_session:
                            cal_session.status = SessionStatus.paused
                except Exception as e:
                    logger.error(f"Failed to pause session: {e}")

        # Disable input controls
        self.reading_input.setEnabled(False)
        self.submit_btn.setEnabled(False)
        self.get_reading_btn.setEnabled(False)
        self.capture_btn.setEnabled(False)

    def _resume_session(self):
        """Resume the session."""
        logger.info("Session resumed")
        self.pause_btn.setText("Pause")
        self.status_display.append("Session resumed")

        # Update database
        if self._current_session_id:
            db = get_db()
            if db.is_connected:
                try:
                    with db.session() as session:
                        cal_session = session.query(CalibrationSession).filter(
                            CalibrationSession.id == self._current_session_id
                        ).first()
                        if cal_session:
                            cal_session.status = SessionStatus.in_progress
                except Exception as e:
                    logger.error(f"Failed to resume session: {e}")

        # Enable input controls
        self.reading_input.setEnabled(True)
        self.submit_btn.setEnabled(True)
        self.get_reading_btn.setEnabled(True)
        self.capture_btn.setEnabled(True)
        self.reading_input.setFocus()

    def _on_stop(self):
        """Stop the session."""
        reply = QMessageBox.question(
            self,
            "Stop Session",
            "Are you sure you want to stop this session?\n\n"
            "Progress will be saved. The session will be marked as aborted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Session stopped/aborted")

            # Update database
            if self._current_session_id:
                db = get_db()
                if db.is_connected:
                    try:
                        with db.session() as session:
                            cal_session = session.query(CalibrationSession).filter(
                                CalibrationSession.id == self._current_session_id
                            ).first()
                            if cal_session:
                                cal_session.status = SessionStatus.aborted
                                cal_session.completed_at = datetime.now()
                    except Exception as e:
                        logger.error(f"Failed to abort session: {e}")

            # Reset session state
            self._current_session_id = None
            self._current_dut_id = None
            self._current_procedure_id = None
            self._test_points = []

            # Re-enable UI
            self.start_btn.setText("Start Session")
            self.start_btn.setEnabled(True)
            self.dut_combo.setEnabled(True)
            self.workorder_input.setEnabled(True)
            self.procedure_combo.setEnabled(True)
            self.pause_btn.setText("Pause")

            self.status_display.append("Session aborted")

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
        if not selected:
            return

        row = selected[0].row()
        logger.info(f"Redoing test point {row + 1}")

        # Clear previous result from table
        self.testpoints_table.setItem(row, 3, QTableWidgetItem(""))
        self.testpoints_table.setItem(row, 4, QTableWidgetItem("Redo"))

        # Update display
        self._update_current_display(row)
        self.reading_input.clear()
        self.reading_input.setFocus()

        self.status_display.append(f"Redoing test point {row + 1}")

    def _on_testpoint_double_clicked(self, item):
        """Handle double-click on test point."""
        row = item.row()
        logger.debug(f"Double-clicked test point {row + 1}")
        self._update_current_display(row)
