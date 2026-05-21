"""
Test execution tab - where calibrations are performed.
"""

import os
import re
import time
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
    QDialog,
    QSizePolicy,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QButtonGroup,
)
from PyQt6.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QPixmap
from PyQt6.QtWidgets import QGraphicsOpacityEffect
from loguru import logger

from calsystem.database.connection import get_db
from calsystem.database.models import (
    DUT,
    Procedure,
    CalibrationSession,
    TestSection,
    TestPoint,
    TestResult,
    TestStatus,
    InputMethod,
    SessionStatus,
    Standard,
    WorkstationStandard,
    WorkstationConfig,
    DeviceGroupType,
    CommandBank,
    DUTCommandBank,
    WiringDiagram,
    WiringDiagramLibrary,
    SectionDiagramLink,
)
from calsystem.config.settings import get_settings
from calsystem.ui.dialogs.calibrator_selection_dialog import CalibratorSelectionDialog
from calsystem.instruments.visa_manager import get_visa_manager, PYVISA_AVAILABLE
from calsystem.instruments.serial_manager import get_serial_manager, SerialConfig
from calsystem.procedures import CSPFile, ProcedureData


class SessionStartDialog(QDialog):
    """
    Dialog shown at session start to select COM port and input method.

    - Shows available COM ports (excludes COM1)
    - Default selection is "None"
    - If COM port selected: Remote automation mode
    - If None: Choose Keyboard or OCR input method
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session Setup - Reading Input")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.setMinimumHeight(350)

        self._selected_port: Optional[str] = None
        self._input_method: str = "keyboard"  # keyboard, remote, ocr

        layout = QVBoxLayout(self)

        # Title
        title = QLabel("How will readings be captured?")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(15)

        # COM Port section
        port_group = QGroupBox("DUT Serial Connection")
        port_layout = QVBoxLayout(port_group)

        port_info = QLabel(
            "If the DUT has a serial adapter cable, select the COM port.\n"
            "This enables automatic state checking and reading capture."
        )
        port_info.setStyleSheet("color: #666; font-size: 11px;")
        port_info.setWordWrap(True)
        port_layout.addWidget(port_info)

        self.port_list = QListWidget()
        self.port_list.setMaximumHeight(120)
        # Note: Signal connected later after all widgets are created
        port_layout.addWidget(self.port_list)

        layout.addWidget(port_group)
        layout.addSpacing(10)

        # Input method section (only visible when None is selected)
        self.method_group = QGroupBox("Manual Input Method")
        method_layout = QVBoxLayout(self.method_group)

        method_info = QLabel(
            "Without a serial connection, how should readings be entered?"
        )
        method_info.setStyleSheet("color: #666; font-size: 11px;")
        method_layout.addWidget(method_info)

        self.method_button_group = QButtonGroup(self)

        self.keyboard_radio = QRadioButton("Keyboard Entry")
        self.keyboard_radio.setToolTip("Tech manually types readings from DUT display")
        self.keyboard_radio.setChecked(True)
        self.method_button_group.addButton(self.keyboard_radio)
        method_layout.addWidget(self.keyboard_radio)

        self.ocr_radio = QRadioButton("Webcam OCR (Coming Soon)")
        self.ocr_radio.setToolTip("Camera captures readings from DUT display")
        self.ocr_radio.setEnabled(False)  # Not implemented yet
        self.method_button_group.addButton(self.ocr_radio)
        method_layout.addWidget(self.ocr_radio)

        layout.addWidget(self.method_group)

        layout.addStretch()

        # Summary label
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet(
            "background-color: #e7f3ff; padding: 10px; border-radius: 5px; font-size: 12px;"
        )
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self._update_summary()

        layout.addSpacing(15)

        # Buttons
        button_layout = QHBoxLayout()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        button_layout.addStretch()

        self.start_btn = QPushButton("Start Session")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 10px 30px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.start_btn.clicked.connect(self._on_start)
        button_layout.addWidget(self.start_btn)

        layout.addLayout(button_layout)

        # Now that all widgets are created, populate ports and connect signal
        self._populate_ports()
        self.port_list.itemSelectionChanged.connect(self._on_port_selection_changed)

    def _populate_ports(self):
        """Scan and populate available COM ports."""
        self.port_list.clear()

        # Add "None" option first (default)
        none_item = QListWidgetItem("None - No serial connection")
        none_item.setData(Qt.ItemDataRole.UserRole, None)
        self.port_list.addItem(none_item)

        # Scan for COM ports (with error handling)
        try:
            serial_mgr = get_serial_manager()
            ports = serial_mgr.scan()

            for port_info in ports:
                port = port_info.port  # SerialPortInfo is a dataclass, not a dict
                # Skip COM1 (usually reserved/unused)
                if port.upper() == 'COM1':
                    continue

                desc = port_info.description or ''
                display_text = f"{port} - {desc}" if desc else port
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, port)
                self.port_list.addItem(item)
        except Exception as e:
            logger.error(f"Failed to scan COM ports: {e}")

        # Select "None" by default
        self.port_list.setCurrentRow(0)

    def _on_port_selection_changed(self):
        """Handle port selection change."""
        current = self.port_list.currentItem()
        if current:
            self._selected_port = current.data(Qt.ItemDataRole.UserRole)

        # Show/hide input method selection based on port
        has_port = self._selected_port is not None
        self.method_group.setVisible(not has_port)

        self._update_summary()

    def _update_summary(self):
        """Update the summary label."""
        if self._selected_port:
            self.summary_label.setText(
                f"<b>Remote Automation Mode</b><br>"
                f"Using {self._selected_port} for DUT communication.<br>"
                f"Readings will be captured automatically via serial commands."
            )
            self.summary_label.setStyleSheet(
                "background-color: #d4edda; padding: 10px; border-radius: 5px; font-size: 12px;"
            )
        else:
            method = "Keyboard Entry" if self.keyboard_radio.isChecked() else "Webcam OCR"
            self.summary_label.setText(
                f"<b>Manual Mode - {method}</b><br>"
                f"No serial connection. Tech will enter readings manually."
            )
            self.summary_label.setStyleSheet(
                "background-color: #e7f3ff; padding: 10px; border-radius: 5px; font-size: 12px;"
            )

    def _on_start(self):
        """Handle start button click."""
        if self._selected_port:
            self._input_method = "remote"
        elif self.keyboard_radio.isChecked():
            self._input_method = "keyboard"
        else:
            self._input_method = "ocr"
        self.accept()

    def get_selected_port(self) -> Optional[str]:
        """Return the selected COM port or None."""
        return self._selected_port

    def get_input_method(self) -> str:
        """Return the selected input method: 'remote', 'keyboard', or 'ocr'."""
        return self._input_method


class PassFailDialog(QDialog):
    """Dialog for Pass/Fail test point verification."""

    def __init__(self, prompt: str, test_info: str, operator_prompt: Optional[str] = None,
                 image_name: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pass/Fail Verification")
        self.setModal(True)
        self.setMinimumWidth(450)

        self._result: Optional[bool] = None

        layout = QVBoxLayout(self)

        # Test info
        info_label = QLabel(test_info)
        info_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addSpacing(10)

        # Operator instructions (if provided)
        if operator_prompt:
            op_label = QLabel(operator_prompt)
            op_label.setStyleSheet("font-size: 13px; color: #333;")
            op_label.setWordWrap(True)
            layout.addWidget(op_label)
            layout.addSpacing(10)

            # Separator line
            separator = QLabel("━" * 60)
            separator.setStyleSheet("color: #ccc;")
            layout.addWidget(separator)
            layout.addSpacing(10)

        # Reference image (if provided)
        if image_name:
            image_pixmap = self._load_image_from_library(image_name)
            if image_pixmap:
                image_label = QLabel()
                image_label.setPixmap(image_pixmap)
                image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                image_label.setStyleSheet("border: 1px solid #ccc; padding: 5px;")
                layout.addWidget(image_label)
                layout.addSpacing(10)

        # Prompt message
        prompt_label = QLabel(prompt or "Does this test point pass?")
        prompt_label.setStyleSheet("font-size: 16px;")
        prompt_label.setWordWrap(True)
        prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(prompt_label)

        layout.addSpacing(20)

        # Pass/Fail buttons
        button_layout = QHBoxLayout()

        self.fail_btn = QPushButton("FAIL")
        self.fail_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 40px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        self.fail_btn.clicked.connect(self._on_fail)
        button_layout.addWidget(self.fail_btn)

        button_layout.addSpacing(20)

        self.pass_btn = QPushButton("PASS")
        self.pass_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 40px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.pass_btn.clicked.connect(self._on_pass)
        button_layout.addWidget(self.pass_btn)

        layout.addLayout(button_layout)

    def _load_image_from_library(self, diagram_name: str) -> Optional[QPixmap]:
        """Load image from wiring diagram library by name."""
        from calsystem.database.models import WiringDiagramLibrary
        from calsystem.database.connection import get_db

        db = get_db()
        if not db.is_connected:
            return None

        try:
            with db.session() as session:
                diagram = session.query(WiringDiagramLibrary).filter(
                    WiringDiagramLibrary.diagram_name == diagram_name
                ).first()

                if diagram and diagram.image_data:
                    # Convert binary image data to QPixmap
                    image = QImage.fromData(diagram.image_data)
                    if not image.isNull():
                        pixmap = QPixmap.fromImage(image)
                        # Scale image to fit dialog (max 400px wide)
                        if pixmap.width() > 400:
                            pixmap = pixmap.scaledToWidth(400, Qt.TransformationMode.SmoothTransformation)
                        return pixmap
        except Exception as e:
            logger.error(f"Failed to load image from library: {e}")

        return None

    def _on_pass(self):
        self._result = True
        self.accept()

    def _on_fail(self):
        self._result = False
        self.accept()

    def get_result(self) -> Optional[bool]:
        """Returns True for Pass, False for Fail, None if cancelled."""
        return self._result


class PassFailWithReadingDialog(QDialog):
    """Dialog for Pass/Fail test with DMM reading and limits checking."""

    def __init__(self, prompt: str, test_info: str, reading: Optional[float],
                 min_val: Optional[float], max_val: Optional[float],
                 unit: str = "", comparison_type: str = "range", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pass/Fail Verification")
        self.setModal(True)
        self.setMinimumWidth(450)

        self._result: Optional[bool] = None
        self._reading = reading

        layout = QVBoxLayout(self)

        # Test info
        info_label = QLabel(test_info)
        info_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addSpacing(10)

        # Prompt message
        prompt_label = QLabel(prompt or "Verify the reading is within limits:")
        prompt_label.setStyleSheet("font-size: 14px;")
        prompt_label.setWordWrap(True)
        layout.addWidget(prompt_label)

        layout.addSpacing(10)

        # DMM Reading display
        reading_frame = QFrame()
        reading_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        reading_layout = QVBoxLayout(reading_frame)

        if reading is not None:
            reading_str = f"{reading:.6g} {unit}".strip()
            reading_label = QLabel(reading_str)
            reading_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #0066cc;")
            reading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            reading_label = QLabel("No DMM Reading")
            reading_label.setStyleSheet("font-size: 18px; color: #999;")
            reading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reading_layout.addWidget(reading_label)

        # Show limits based on comparison type
        limits_str = "Limits: "
        if comparison_type == 'gt':
            limits_str += f"> {min_val:.6g} {unit}".strip() if min_val is not None else "None specified"
        elif comparison_type == 'lt':
            limits_str += f"< {max_val:.6g} {unit}".strip() if max_val is not None else "None specified"
        elif min_val is not None and max_val is not None:
            limits_str += f"{min_val:.6g} to {max_val:.6g} {unit}".strip()
        elif min_val is not None:
            limits_str += f">= {min_val:.6g} {unit}".strip()
        elif max_val is not None:
            limits_str += f"<= {max_val:.6g} {unit}".strip()
        else:
            limits_str += "None specified"

        limits_label = QLabel(limits_str)
        limits_label.setStyleSheet("font-size: 12px; color: #666;")
        limits_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reading_layout.addWidget(limits_label)

        # Auto-determined result based on comparison type
        auto_pass = None
        if reading is not None:
            in_range = True
            if comparison_type == 'gt':
                # Greater Than: must be strictly greater
                if min_val is not None and reading <= min_val:
                    in_range = False
            elif comparison_type == 'lt':
                # Less Than: must be strictly less
                if max_val is not None and reading >= max_val:
                    in_range = False
            else:
                # Range: between min and max (inclusive)
                if min_val is not None and reading < min_val:
                    in_range = False
                if max_val is not None and reading > max_val:
                    in_range = False
            auto_pass = in_range

            auto_label = QLabel(f"Auto Result: {'PASS' if auto_pass else 'FAIL'}")
            auto_label.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {'#28a745' if auto_pass else '#dc3545'};"
            )
            auto_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            reading_layout.addWidget(auto_label)

        layout.addWidget(reading_frame)
        layout.addSpacing(15)

        # Pass/Fail buttons
        button_layout = QHBoxLayout()

        self.fail_btn = QPushButton("FAIL")
        self.fail_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 40px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        self.fail_btn.clicked.connect(self._on_fail)
        button_layout.addWidget(self.fail_btn)

        button_layout.addSpacing(20)

        self.pass_btn = QPushButton("PASS")
        self.pass_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 40px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.pass_btn.clicked.connect(self._on_pass)
        button_layout.addWidget(self.pass_btn)

        layout.addLayout(button_layout)

        # If auto-determined, pre-select the appropriate button
        if auto_pass is not None:
            if auto_pass:
                self.pass_btn.setFocus()
            else:
                self.fail_btn.setFocus()

    def _on_pass(self):
        self._result = True
        self.accept()

    def _on_fail(self):
        self._result = False
        self.accept()

    def get_result(self) -> Optional[bool]:
        """Returns True for Pass, False for Fail, None if cancelled."""
        return self._result

    def get_reading(self) -> Optional[float]:
        """Returns the DMM reading."""
        return self._reading


class WiringPromptDialog(QDialog):
    """Dialog showing wiring instructions before a measurement."""

    def __init__(self, prompt: str, test_info: str, wiring_image: Optional[QPixmap] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wiring Instructions")
        self.setModal(True)
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Test info header
        info_label = QLabel(test_info)
        info_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addSpacing(10)

        # Wiring image (if provided)
        if wiring_image and not wiring_image.isNull():
            image_label = QLabel()
            # Scale image to fit dialog
            scaled = wiring_image.scaledToWidth(450, Qt.TransformationMode.SmoothTransformation)
            image_label.setPixmap(scaled)
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(image_label)
            layout.addSpacing(10)

        # Instructions
        prompt_label = QLabel(prompt or "Wire the DUT to the DMM as shown, then click Next.")
        prompt_label.setStyleSheet("font-size: 14px;")
        prompt_label.setWordWrap(True)
        prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(prompt_label)

        layout.addSpacing(20)

        # Next button
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.next_btn = QPushButton("Next (Wiring Complete)")
        self.next_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 12px 30px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        self.next_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.next_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)


class ManualReadingDialog(QDialog):
    """Dialog for manual pass/fail when DMM is not connected."""

    def __init__(self, prompt: str, test_info: str, min_val: Optional[float],
                 max_val: Optional[float], unit: str = "", comparison_type: str = "range",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Verify DMM Reading")
        self.setModal(True)
        self.setMinimumWidth(450)

        self._result: Optional[bool] = None

        layout = QVBoxLayout(self)

        # Test info
        info_label = QLabel(test_info)
        info_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addSpacing(10)

        # Show expected range
        range_frame = QFrame()
        range_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        range_layout = QVBoxLayout(range_frame)

        range_label = QLabel("Check the DMM display:")
        range_label.setStyleSheet("font-size: 14px;")
        range_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        range_layout.addWidget(range_label)

        # Show limits based on comparison type
        if comparison_type == 'gt':
            limits_str = f"Reading must be > {min_val:.6g} {unit}".strip() if min_val is not None else prompt or "Check reading"
        elif comparison_type == 'lt':
            limits_str = f"Reading must be < {max_val:.6g} {unit}".strip() if max_val is not None else prompt or "Check reading"
        elif min_val is not None and max_val is not None:
            limits_str = f"Reading should be between {min_val:.6g} and {max_val:.6g} {unit}".strip()
        elif min_val is not None:
            limits_str = f"Reading should be >= {min_val:.6g} {unit}".strip()
        elif max_val is not None:
            limits_str = f"Reading should be <= {max_val:.6g} {unit}".strip()
        else:
            limits_str = prompt or "Does the reading match the expected value?"

        limits_label = QLabel(limits_str)
        limits_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #0066cc;")
        limits_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        limits_label.setWordWrap(True)
        range_layout.addWidget(limits_label)

        layout.addWidget(range_frame)
        layout.addSpacing(15)

        # Question
        question_label = QLabel("Does the DMM reading meet the requirement?")
        question_label.setStyleSheet("font-size: 14px;")
        question_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(question_label)

        layout.addSpacing(15)

        # Pass/Fail buttons
        button_layout = QHBoxLayout()

        self.fail_btn = QPushButton("NO - FAIL")
        self.fail_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 40px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        self.fail_btn.clicked.connect(self._on_fail)
        button_layout.addWidget(self.fail_btn)

        button_layout.addSpacing(20)

        self.pass_btn = QPushButton("YES - PASS")
        self.pass_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 40px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.pass_btn.clicked.connect(self._on_pass)
        button_layout.addWidget(self.pass_btn)

        layout.addLayout(button_layout)

    def _on_pass(self):
        self._result = True
        self.accept()

    def _on_fail(self):
        self._result = False
        self.accept()

    def get_result(self) -> Optional[bool]:
        return self._result


class DUTStateMismatchDialog(QDialog):
    """Dialog shown when DUT is not in the expected state."""

    def __init__(
        self,
        command_name: str,
        expected: str,
        actual: str,
        test_info: str,
        prompt: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("DUT State Mismatch")
        self.setModal(True)
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # Test info header
        info_label = QLabel(test_info)
        info_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addSpacing(10)

        # Warning message
        warning_frame = QFrame()
        warning_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        warning_frame.setStyleSheet("background-color: #fff3cd; border: 1px solid #ffc107;")
        warning_layout = QVBoxLayout(warning_frame)

        warning_label = QLabel("DUT is not in the expected state!")
        warning_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #856404;")
        warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning_layout.addWidget(warning_label)

        layout.addWidget(warning_frame)
        layout.addSpacing(10)

        # State comparison
        state_frame = QFrame()
        state_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        state_layout = QVBoxLayout(state_frame)

        cmd_label = QLabel(f"Query: {command_name}")
        cmd_label.setStyleSheet("color: gray;")
        state_layout.addWidget(cmd_label)

        expected_label = QLabel(f"Expected: {expected}")
        expected_label.setStyleSheet("font-size: 14px; color: #28a745; font-weight: bold;")
        state_layout.addWidget(expected_label)

        actual_label = QLabel(f"Actual: {actual}")
        actual_label.setStyleSheet("font-size: 14px; color: #dc3545; font-weight: bold;")
        state_layout.addWidget(actual_label)

        layout.addWidget(state_frame)
        layout.addSpacing(10)

        # Instructions - use custom prompt if provided
        if prompt:
            instruction_text = f"{prompt}\n\nThen click 'Re-Check' to verify."
        else:
            instruction_text = (
                "Please adjust the DUT to the expected state,\n"
                "then click 'Re-Check' to verify."
            )
        instructions = QLabel(instruction_text)
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setStyleSheet("font-size: 12px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        layout.addSpacing(15)

        # Buttons - only Cancel and Continue (which triggers recheck)
        button_layout = QHBoxLayout()

        self.cancel_btn = QPushButton("Cancel Test")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-size: 14px;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        # Spacer to push Continue button to the right
        button_layout.addStretch()

        self.continue_btn = QPushButton("Continue")
        self.continue_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 30px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.continue_btn.setToolTip("Click after adjusting DUT - will verify the state")
        self.continue_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.continue_btn)

        layout.addLayout(button_layout)


class ExecutionTab(QWidget):
    """Tab for executing calibration procedures."""

    def __init__(self):
        super().__init__()
        self._current_session_id: Optional[int] = None
        self._current_dut_id: Optional[int] = None
        self._current_procedure_id: Optional[int] = None
        self._current_csp_data: Optional[ProcedureData] = None  # Loaded .csp procedure data
        self._test_points: List[Dict[str, Any]] = []
        self._current_test_index: int = 0
        self._current_section_id: Optional[int] = None  # Track section for wiring confirmation
        # Calibrator selection for this session
        self._selected_calibrator: Optional[Dict[str, Any]] = None
        self._calibrator_commands: Optional[Dict[str, str]] = None
        # Reference DMM for automated measurements
        self._selected_dmm: Optional[Dict[str, Any]] = None
        # DUT Remote Communication
        self._dut_com_port: Optional[str] = None
        self._dut_commands: Optional[Dict[str, Any]] = None
        self._dut_serial_config: Optional[Dict[str, Any]] = None
        self._dut_line_terminator: str = "\r\n"  # Default, loaded from command bank
        self._dut_serial_connected: bool = False
        # Session input method (set by SessionStartDialog)
        self._session_input_method: str = "keyboard"  # keyboard, remote, ocr
        self._session_com_port: Optional[str] = None
        self._init_ui()
        self._connect_signals()

    def showEvent(self, event):
        """Called when tab becomes visible."""
        super().showEvent(event)
        self._load_duts()
        self._load_procedures()
        self._load_dmms()

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

    def _load_dmms(self):
        """Load DMMs from workstation standards into combo."""
        current_data = self.dmm_combo.currentData()
        self.dmm_combo.clear()
        self.dmm_combo.addItem("-- Select DMM --", None)

        db = get_db()
        if not db.is_connected:
            return

        try:
            from calsystem.config.settings import get_settings
            settings = get_settings()
            workstation_name = settings.workstation_name or "Default Workstation"

            with db.session() as session:
                config = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == workstation_name
                ).first()

                if not config:
                    return

                # Only get ACTIVE standards
                ws_standards = session.query(WorkstationStandard).filter(
                    WorkstationStandard.workstation_id == config.id,
                    WorkstationStandard.is_active != False  # Include True and NULL
                ).all()

                for ws_std in ws_standards:
                    standard = session.query(Standard).filter(
                        Standard.id == ws_std.standard_id
                    ).first()

                    # Only show active DMMs
                    if standard and standard.device_group == DeviceGroupType.DMM:
                        address = ws_std.visa_address or standard.visa_address or ""
                        label = f"{standard.make} {standard.model}"
                        if address:
                            label += f" ({address})"
                        self.dmm_combo.addItem(label, {
                            "standard_id": standard.id,
                            "make": standard.make,
                            "model": standard.model,
                            "address": address,
                        })

                # Restore selection
                if current_data:
                    for i in range(self.dmm_combo.count()):
                        data = self.dmm_combo.itemData(i)
                        if data and data.get("standard_id") == current_data.get("standard_id"):
                            self.dmm_combo.setCurrentIndex(i)
                            break

        except Exception as e:
            logger.error(f"Failed to load DMMs: {e}")

    def _on_dmm_selected(self, index: int):
        """Handle DMM selection."""
        data = self.dmm_combo.currentData()
        if data:
            self._selected_dmm = data
            logger.info(f"Selected DMM: {data['make']} {data['model']} at {data['address']}")
        else:
            self._selected_dmm = None

    def _get_workstation_dmm(self) -> Optional[Dict[str, Any]]:
        """Get the first active DMM from workstation setup with a GPIB address.

        Returns:
            DMM info dict with make, model, address, or None if not available.
        """
        db = get_db()
        if not db.is_connected:
            return None

        try:
            from calsystem.config.settings import get_settings
            settings = get_settings()
            workstation_name = settings.workstation_name or "Default Workstation"

            with db.session() as session:
                config = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == workstation_name
                ).first()

                if not config:
                    return None

                # Get active DMMs from workstation
                ws_standards = session.query(WorkstationStandard).filter(
                    WorkstationStandard.workstation_id == config.id,
                    WorkstationStandard.is_active != False
                ).all()

                for ws_std in ws_standards:
                    standard = session.query(Standard).filter(
                        Standard.id == ws_std.standard_id
                    ).first()

                    if standard and standard.device_group == DeviceGroupType.DMM:
                        address = ws_std.visa_address or standard.visa_address or ""
                        if address:  # Only return if it has a GPIB/VISA address
                            return {
                                "standard_id": standard.id,
                                "make": standard.make,
                                "model": standard.model,
                                "address": address,
                            }

        except Exception as e:
            logger.error(f"Failed to get workstation DMM: {e}")

        return None

    def _check_dmm_responding(self, dmm_info: Dict[str, Any]) -> bool:
        """Check if the DMM is responding to GPIB commands.

        For HP/Agilent 3458A, sends RESET and END ALWAYS first since
        the 3458A often won't respond to queries without initialization.

        Args:
            dmm_info: DMM info dict with address

        Returns:
            True if DMM responds, False otherwise.
        """
        address = dmm_info.get("address")
        if not address:
            return False

        visa = get_visa_manager()
        if not visa:
            return False

        model = dmm_info.get("model", "").lower()

        try:
            # For 3458A, send initialization commands first
            if "3458" in model:
                logger.info(f"Initializing 3458A at {address}...")
                # RESET first
                visa.write(address, "RESET")
                # END ALWAYS - critical for GPIB communication
                visa.write(address, "END ALWAYS")
                # Small delay for reset to complete
                import time
                time.sleep(0.3)
                # Now try ID? (3458A-specific) instead of *IDN?
                success, response = visa.query(address, "ID?")
                if success and response:
                    logger.info(f"DMM responding: {response.strip()[:50]}")
                    return True
            else:
                # Try to query identity - most instruments respond to *IDN?
                success, response = visa.query(address, "*IDN?")
                if success and response:
                    logger.info(f"DMM responding: {response.strip()[:50]}")
                    return True
        except Exception as e:
            logger.debug(f"DMM not responding: {e}")

        return False

    def _on_init_dmm(self):
        """Initialize the selected DMM with RESET and END ALWAYS."""
        if not self._selected_dmm:
            QMessageBox.warning(self, "No DMM", "Please select a Reference DMM first.")
            return

        address = self._selected_dmm.get("address")
        if not address:
            QMessageBox.warning(self, "No Address", "Selected DMM has no VISA address.")
            return

        visa = get_visa_manager()
        make = self._selected_dmm.get("make", "").lower()
        model = self._selected_dmm.get("model", "").lower()

        self.status_display.append(f"Initializing {self._selected_dmm['make']} {self._selected_dmm['model']}...")

        # HP/Agilent/Keysight 3458A specific initialization
        if "3458" in model:
            # RESET - returns to power-on state
            if visa.write(address, "RESET"):
                self.status_display.append("  RESET - OK")
            else:
                self.status_display.append("  RESET - FAILED")
                return

            # END ALWAYS - send EOI with every reading (critical for GPIB)
            if visa.write(address, "END ALWAYS"):
                self.status_display.append("  END ALWAYS - OK")
            else:
                self.status_display.append("  END ALWAYS - FAILED")
                return

            # OFORMAT ASCII - ASCII output format
            if visa.write(address, "OFORMAT ASCII"):
                self.status_display.append("  OFORMAT ASCII - OK")
            else:
                self.status_display.append("  OFORMAT ASCII - FAILED")

            # Verify communication with ID query
            success, response = visa.query(address, "ID?")
            if success:
                self.status_display.append(f"  ID: {response.strip()}")
                QMessageBox.information(
                    self, "DMM Initialized",
                    f"3458A initialized successfully!\n\nID: {response.strip()}"
                )
            else:
                self.status_display.append("  ID query failed")
        else:
            # Generic SCPI initialization for other DMMs
            if visa.write(address, "*RST"):
                self.status_display.append("  *RST - OK")
            if visa.write(address, "*CLS"):
                self.status_display.append("  *CLS - OK")

            success, response = visa.query(address, "*IDN?")
            if success:
                self.status_display.append(f"  IDN: {response.strip()}")
                QMessageBox.information(
                    self, "DMM Initialized",
                    f"DMM initialized successfully!\n\n{response.strip()}"
                )

    def _convert_to_test_unit(self, value: float, target_unit: str) -> float:
        """
        Convert a reading from base units to the test point's unit.

        The 3458A returns values in base units (V, A, Ohm).
        This converts to mV, µV, mA, µA, kOhm, MOhm, etc.

        Args:
            value: Reading in base units from DMM
            target_unit: The unit specified in the test point

        Returns:
            Value converted to the target unit
        """
        # Define conversion multipliers (from base unit to target)
        conversions = {
            # Voltage
            "V": 1,
            "mV": 1000,           # 1 V = 1000 mV
            "µV": 1000000,        # 1 V = 1000000 µV
            "uV": 1000000,        # alternate spelling
            # Current
            "A": 1,
            "mA": 1000,           # 1 A = 1000 mA
            "µA": 1000000,        # 1 A = 1000000 µA
            "uA": 1000000,        # alternate spelling
            # Resistance
            "Ohm": 1,
            "kOhm": 0.001,        # 1 Ohm = 0.001 kOhm
            "MOhm": 0.000001,     # 1 Ohm = 0.000001 MOhm
            # Frequency (if ever needed)
            "Hz": 1,
            "kHz": 0.001,
            "MHz": 0.000001,
        }

        multiplier = conversions.get(target_unit, 1)
        return value * multiplier

    def _query_dmm(self, function: str = "DCV") -> Optional[float]:
        """
        Query the selected DMM for a reading.

        Args:
            function: Measurement function (DCV, ACV, OHM, OHMF)

        Returns:
            Reading as float (in base units), or None if failed.
        """
        if not self._selected_dmm:
            return None

        address = self._selected_dmm.get("address")
        if not address:
            return None

        visa = get_visa_manager()
        model = self._selected_dmm.get("model", "").lower()

        # HP/Agilent/Keysight 3458A commands
        if "3458" in model:
            # Set function with auto-range
            func_cmd = f"{function} AUTO"
            if not visa.write(address, func_cmd):
                logger.error(f"Failed to set function: {func_cmd}")
                return None

            # Trigger single reading
            success, response = visa.query(address, "TRIG SGL")
            if success and response:
                try:
                    return float(response.strip())
                except ValueError:
                    logger.error(f"Could not parse reading: {response}")
                    return None
        else:
            # Generic SCPI DMM commands
            func_map = {
                "DCV": "MEAS:VOLT:DC?",
                "ACV": "MEAS:VOLT:AC?",
                "OHM": "MEAS:RES?",
                "OHMF": "MEAS:FRES?",
            }
            cmd = func_map.get(function, "MEAS:VOLT:DC?")
            success, response = visa.query(address, cmd)
            if success and response:
                try:
                    return float(response.strip())
                except ValueError:
                    logger.error(f"Could not parse reading: {response}")
                    return None

        return None

    def _query_dmm_with_config(self, function: str, dmm_config: Dict[str, Any]) -> Optional[float]:
        """
        Query the DMM using configuration from test point including custom commands.

        Args:
            function: Measurement function (DCV, ACV, OHM, OHMF)
            dmm_config: DMM configuration dict with custom_commands, range, etc.

        Returns:
            Reading as float (in base units), or None if failed.
        """
        if not self._selected_dmm:
            return None

        address = self._selected_dmm.get("address")
        if not address:
            return None

        visa = get_visa_manager()
        model = self._selected_dmm.get("model", "").lower()

        # Get custom commands
        custom_commands = dmm_config.get('custom_commands', [])
        before_commands = [c for c in custom_commands if c.get('order', 'Before') == 'Before']
        after_commands = [c for c in custom_commands if c.get('order') == 'After']

        # Send "Before" custom commands
        for cmd_info in before_commands:
            cmd = cmd_info.get('command', '')
            if cmd:
                self.status_display.append(f"DMM: {cmd}")
                if not visa.write(address, cmd):
                    logger.warning(f"DMM command may have failed: {cmd}")

        # HP/Agilent/Keysight 3458A commands
        if "3458" in model:
            # Set function - use range from config or AUTO
            dmm_range = dmm_config.get('range', 'AUTO')
            if dmm_range == 'AUTO':
                func_cmd = f"{function} AUTO"
            else:
                func_cmd = f"{function} {dmm_range}"

            self.status_display.append(f"DMM: {func_cmd}")
            if not visa.write(address, func_cmd):
                logger.error(f"Failed to set function: {func_cmd}")
                return None

            # Apply delay if configured
            delay = dmm_config.get('delay', 0)
            try:
                delay = float(delay) if delay else 0
            except (ValueError, TypeError):
                delay = 0
            if delay > 0:
                import time
                self.status_display.append(f"Waiting {delay}s for settling...")
                time.sleep(delay)

            # Trigger single reading
            self.status_display.append("DMM: TRIG SGL")
            success, response = visa.query(address, "TRIG SGL")

            # Send "After" custom commands
            for cmd_info in after_commands:
                cmd = cmd_info.get('command', '')
                if cmd:
                    self.status_display.append(f"DMM: {cmd}")
                    visa.write(address, cmd)

            if success and response:
                try:
                    reading = float(response.strip())
                    logger.info(f"DMM reading: {reading}")
                    return reading
                except ValueError:
                    logger.error(f"Could not parse reading: {response}")
                    return None
        else:
            # Generic SCPI DMM - send custom commands then standard query
            func_map = {
                "DCV": "MEAS:VOLT:DC?",
                "ACV": "MEAS:VOLT:AC?",
                "OHM": "MEAS:RES?",
                "OHMF": "MEAS:FRES?",
            }
            cmd = func_map.get(function, "MEAS:VOLT:DC?")
            success, response = visa.query(address, cmd)

            # Send "After" custom commands
            for cmd_info in after_commands:
                cmd_str = cmd_info.get('command', '')
                if cmd_str:
                    visa.write(address, cmd_str)

            if success and response:
                try:
                    return float(response.strip())
                except ValueError:
                    logger.error(f"Could not parse reading: {response}")
                    return None

        return None

    # -------------------------------------------------------------------------
    # Calibrator Detection and Selection
    # -------------------------------------------------------------------------

    def _get_workstation_calibrators(self) -> List[Dict[str, Any]]:
        """Get active calibrators from workstation standards."""
        db = get_db()
        if not db.is_connected:
            return []

        calibrators = []

        try:
            settings = get_settings()
            workstation_name = settings.workstation_name or "Default Workstation"

            with db.session() as session:
                config = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == workstation_name
                ).first()

                if not config:
                    return []

                # Only get ACTIVE standards (is_active = True or NULL for backwards compat)
                ws_standards = session.query(WorkstationStandard).filter(
                    WorkstationStandard.workstation_id == config.id,
                    WorkstationStandard.is_active != False  # Include True and NULL
                ).all()

                command_banks = session.query(CommandBank.make, CommandBank.model).all()
                cb_set = {(cb.make.lower(), cb.model.lower()) for cb in command_banks}

                for ws_std in ws_standards:
                    standard = session.query(Standard).filter(
                        Standard.id == ws_std.standard_id
                    ).first()

                    if standard:
                        if standard.device_group == DeviceGroupType.CALIBRATOR:
                            has_cb = (standard.make.lower(), standard.model.lower()) in cb_set
                            addr = ws_std.visa_address or standard.visa_address or ""
                            calibrators.append({
                                "standard_id": standard.id,
                                "address": addr,
                                "make": standard.make,
                                "model": standard.model,
                                "serial": standard.serial_number or "",
                                "has_command_bank": has_cb,
                            })

                logger.info(f"Found {len(calibrators)} active calibrators in workstation")
                return calibrators

        except Exception as e:
            logger.error(f"Failed to get workstation calibrators: {e}")
            return []

    def _detect_connected_calibrators(self) -> List[Dict[str, Any]]:
        """Check if active workstation calibrators are connected (fast - only checks known addresses)."""
        if not PYVISA_AVAILABLE:
            return []

        workstation_cals = self._get_workstation_calibrators()
        if not workstation_cals:
            return []

        visa = get_visa_manager()
        if not visa:
            return []

        connected_calibrators = []

        # Only check the specific addresses we know about (much faster than scanning all)
        for cal in workstation_cals:
            cal_address = cal.get("address", "")
            if not cal_address:
                continue

            logger.info(f"Checking calibrator at {cal_address}...")

            # Try to identify this specific address
            try:
                info = visa.identify(cal_address)
                if info and info.is_connected:
                    cal["detected_address"] = info.address
                    cal["detected_make"] = info.manufacturer
                    cal["detected_model"] = info.model
                    connected_calibrators.append(cal)
                    logger.info(f"Found: {info.manufacturer} {info.model} at {cal_address}")
                else:
                    logger.info(f"No response from {cal_address}")
            except Exception as e:
                logger.error(f"Exception identifying {cal_address}: {e}")

        return connected_calibrators

    def _select_calibrator(self) -> Optional[Dict[str, Any]]:
        """Select a calibrator for this session."""
        # Use cached if available
        if self._selected_calibrator:
            return self._selected_calibrator

        connected = self._detect_connected_calibrators()

        if not connected:
            QMessageBox.warning(
                self, "No Calibrator Connected",
                "No calibrators detected on the VISA bus.\n\n"
                "Please check that:\n"
                "1. Your calibrator is powered on\n"
                "2. It's connected via GPIB/USB/LAN\n"
                "3. It's added to your workstation standards\n"
                "4. The Group is set to 'Calibrator'"
            )
            return None

        if len(connected) == 1:
            self._selected_calibrator = connected[0]
            self._load_calibrator_commands()
            logger.info(f"Auto-selected calibrator: {connected[0]['make']} {connected[0]['model']}")
            return self._selected_calibrator

        # Multiple - show selection dialog
        dialog = CalibratorSelectionDialog(connected, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._selected_calibrator = dialog.get_selected_calibrator()
            if self._selected_calibrator:
                self._load_calibrator_commands()
                return self._selected_calibrator

        return None

    def _load_calibrator_commands(self):
        """Load command bank for the selected calibrator."""
        if not self._selected_calibrator:
            self._calibrator_commands = None
            return

        make = self._selected_calibrator.get("make", "")
        model = self._selected_calibrator.get("model", "")

        db = get_db()
        if not db.is_connected:
            self._calibrator_commands = None
            return

        try:
            with db.session() as session:
                command_bank = session.query(CommandBank).filter(
                    CommandBank.make.ilike(make),
                    CommandBank.model.ilike(model)
                ).first()

                if command_bank and command_bank.commands:
                    self._calibrator_commands = command_bank.commands
                    cmd_list = list(self._calibrator_commands.keys())
                    logger.info(f"Loaded command bank for {make} {model}: {cmd_list}")
                    self.status_display.append(f"Command bank loaded: {', '.join(cmd_list)}")
                else:
                    self._calibrator_commands = None
                    logger.warning(f"No command bank found for {make} {model}")
                    self.status_display.append(f"WARNING: No command bank for {make} {model}")

        except Exception as e:
            logger.error(f"Failed to load command bank: {e}")
            self._calibrator_commands = None

    def _get_calibrator_command(self, command_name: str) -> Optional[str]:
        """Get a command from the calibrator's command bank."""
        if not self._calibrator_commands:
            return None

        if command_name in self._calibrator_commands:
            return self._calibrator_commands[command_name]

        for key, value in self._calibrator_commands.items():
            if key.lower() == command_name.lower():
                return value

        return None

    # =========================================================================
    # DUT Remote Communication Methods
    # =========================================================================

    def _load_dut_commands(self):
        """Load command bank for the current DUT's make/model."""
        self._dut_commands = None
        self._dut_serial_config = None
        self._dut_com_port = None
        self._dut_line_terminator = "\r\n"  # Reset to default

        # Use COM port selected in session dialog (not from DUT record)
        if self._session_input_method == "remote" and self._session_com_port:
            self._dut_com_port = self._session_com_port
        else:
            # Not using remote mode - skip DUT command loading
            return

        if not self._current_dut_id:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                dut = session.query(DUT).filter(DUT.id == self._current_dut_id).first()
                if not dut:
                    return

                # Find command bank for this make/model
                cmd_bank = session.query(DUTCommandBank).filter(
                    DUTCommandBank.make.ilike(dut.make),
                    DUTCommandBank.model.ilike(dut.model)
                ).first()

                if cmd_bank and cmd_bank.commands:
                    self._dut_commands = cmd_bank.commands
                    self._dut_serial_config = cmd_bank.serial_config

                    # Load line terminator (convert escaped to actual chars)
                    terminator_escaped = cmd_bank.line_terminator or "\\r\\n"
                    self._dut_line_terminator = terminator_escaped.replace("\\r", "\r").replace("\\n", "\n")

                    cmd_list = list(self._dut_commands.keys())
                    terminator_display = terminator_escaped.replace("\\r", "CR").replace("\\n", "LF")
                    logger.info(f"Loaded DUT command bank for {dut.make} {dut.model}: {cmd_list}, terminator: {terminator_display}")
                    self.status_display.append(f"DUT commands loaded: {', '.join(cmd_list)}")
                    self.status_display.append(f"DUT COM port: {self._dut_com_port} (terminator: {terminator_display})")

                    # Try to connect to DUT serial port now
                    if self._connect_dut_serial():
                        self.status_display.append(f"DUT serial connected on {self._dut_com_port}")
                    else:
                        self.status_display.append(f"WARNING: Could not connect to DUT on {self._dut_com_port}")
                else:
                    logger.info(f"No DUT command bank for {dut.make} {dut.model}")
                    self.status_display.append(f"WARNING: No command bank found for {dut.make} {dut.model}")
                    self.status_display.append("Remote readings will require manual entry")

        except Exception as e:
            logger.error(f"Failed to load DUT commands: {e}")

    def _connect_dut_serial(self) -> bool:
        """Connect to the DUT's serial port if not already connected."""
        if not self._dut_com_port:
            return False

        serial_mgr = get_serial_manager()

        if serial_mgr.is_connected(self._dut_com_port):
            return True

        # Build config from stored settings
        config = SerialConfig()
        if self._dut_serial_config:
            config = SerialConfig.from_dict(self._dut_serial_config)

        if serial_mgr.connect(self._dut_com_port, config):
            self._dut_serial_connected = True
            self.status_display.append(f"Connected to DUT on {self._dut_com_port}")
            return True
        else:
            self.status_display.append(f"FAILED to connect to DUT on {self._dut_com_port}")
            return False

    def _disconnect_dut_serial(self):
        """Disconnect from the DUT's serial port."""
        if self._dut_com_port and self._dut_serial_connected:
            serial_mgr = get_serial_manager()
            serial_mgr.disconnect(self._dut_com_port)
            self._dut_serial_connected = False

    def _get_dut_command(self, command_name: str) -> Optional[Dict[str, Any]]:
        """Get a command info dict from the DUT command bank."""
        if not self._dut_commands:
            return None

        # Direct match
        if command_name in self._dut_commands:
            cmd_info = self._dut_commands[command_name]
            if isinstance(cmd_info, dict):
                return cmd_info
            else:
                return {"command": str(cmd_info), "delay_before": 0, "delay_after": 0.1}

        # Normalize for comparison: lowercase and remove spaces
        name_normalized = command_name.lower().replace(" ", "")

        # Case-insensitive and space-insensitive match
        for key, value in self._dut_commands.items():
            key_normalized = key.lower().replace(" ", "")
            if key_normalized == name_normalized:
                if isinstance(value, dict):
                    return value
                else:
                    return {"command": str(value), "delay_before": 0, "delay_after": 0.1}

        return None

    def _query_dut(self, command_name: str, param: Optional[str] = None) -> Optional[str]:
        """Send a query command to the DUT and return the response.

        Args:
            command_name: Name of the command from the DUT command bank.
            param: Optional parameter value to substitute for {value} placeholder.
        """
        cmd_info = self._get_dut_command(command_name)
        if not cmd_info:
            logger.warning(f"DUT command not found: {command_name}")
            return None

        if not self._dut_com_port:
            logger.warning("No COM port assigned to DUT")
            return None

        if not self._connect_dut_serial():
            return None

        serial_mgr = get_serial_manager()
        command = cmd_info.get("command", "")

        # Substitute parameter value if provided
        if param and "{value}" in command:
            command = command.replace("{value}", param)

        delay_before = cmd_info.get("delay_before", 0)
        delay_after = cmd_info.get("delay_after", 0.1)

        self.status_display.append(f"DUT Query: {command}")

        success, response = serial_mgr.query(
            self._dut_com_port,
            command,
            delay_before=delay_before,
            delay_after=delay_after,
            terminator=self._dut_line_terminator,
        )

        if success:
            self.status_display.append(f"DUT Response: {response}")
            return response
        else:
            self.status_display.append("DUT Query failed - no response")
            return None

    def _send_dut_command(self, command_name: str, param: Optional[str] = None) -> bool:
        """Send a command to the DUT (no response expected).

        Args:
            command_name: Name of the command from the DUT command bank.
            param: Optional parameter value to substitute for {value} placeholder.
        """
        cmd_info = self._get_dut_command(command_name)
        if not cmd_info:
            logger.warning(f"DUT command not found: {command_name}")
            return False

        if not self._dut_com_port:
            return False

        if not self._connect_dut_serial():
            return False

        serial_mgr = get_serial_manager()
        command = cmd_info.get("command", "")

        # Substitute parameter value if provided
        if param and "{value}" in command:
            command = command.replace("{value}", param)

        delay_after = cmd_info.get("delay_after", 0.1)

        self.status_display.append(f"DUT Command: {command}")

        return serial_mgr.write(
            self._dut_com_port,
            command,
            delay_after=delay_after,
            terminator=self._dut_line_terminator
        )

    def _execute_dut_setup(self, tp: Dict[str, Any]) -> bool:
        """
        Execute DUT setup command to configure the DUT before the test.

        Returns True if successful or not configured, False if failed.
        """
        setup_cmd = tp.get('dut_setup_command')
        setup_param = tp.get('dut_setup_param')  # Parameter for {value} substitution

        if not setup_cmd:
            return True  # No setup command configured

        if not self._dut_commands or not self._dut_com_port:
            # No DUT remote configured, skip setup
            return True

        self.status_display.append(f"Configuring DUT: {setup_cmd}" + (f" ({setup_param})" if setup_param else ""))

        # Send the setup command to the DUT
        success = self._send_dut_command(setup_cmd, param=setup_param)

        if success:
            self.status_display.append("DUT setup command sent successfully")
            return True
        else:
            # Setup failed - ask if user wants to continue
            reply = QMessageBox.question(
                self,
                "DUT Setup Failed",
                f"Failed to send setup command to DUT ({setup_cmd}).\n\n"
                "Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            return reply == QMessageBox.StandardButton.Yes

    def _execute_dut_precheck(self, tp: Dict[str, Any]) -> bool:
        """
        Execute DUT pre-check before calibrator output.

        Returns True if OK to proceed, False if cancelled.
        """
        precheck_cmd = tp.get('dut_pre_check_command')
        precheck_param = tp.get('dut_pre_check_param')  # Parameter for {value} substitution
        expected = tp.get('dut_pre_check_expected')
        precheck_prompt = tp.get('dut_pre_check_prompt')  # Custom message for tech if mismatch
        precheck_parser = tp.get('dut_pre_check_parser', 'string')  # string or csv_field
        precheck_index = tp.get('dut_pre_check_index', 1)  # For CSV, which field to compare

        # Debug: show what's loaded from test point
        self.status_display.append(f"[DEBUG] Pre-check: cmd={precheck_cmd}, expected={expected}, parser={precheck_parser}, index={precheck_index}")

        if not precheck_cmd or not expected:
            return True  # No pre-check configured

        if not self._dut_commands or not self._dut_com_port:
            # No DUT remote configured, skip pre-check
            return True

        # Get test info for dialog
        nominal = tp.get('nominal_value', '')
        unit = tp.get('unit', '')
        test_info = f"Test Point: {nominal} {unit}"

        while True:
            # Query DUT (pass parameter for {value} substitution)
            response = self._query_dut(precheck_cmd, param=precheck_param)

            if response is None:
                # Query failed - ask if user wants to continue
                reply = QMessageBox.question(
                    self,
                    "DUT Query Failed",
                    f"Failed to query DUT state ({precheck_cmd}).\n\n"
                    "Continue without pre-check?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                return reply == QMessageBox.StandardButton.Yes

            # Check if response matches expected
            response_clean = response.strip()
            expected_clean = expected.strip()

            # Parse response based on parser type
            compare_value = response_clean
            if precheck_parser == 'csv_field':
                # Handle multi-line responses (some devices send status line before data)
                # Extract the line containing commas (the actual CSV data line)
                response_line = response_clean
                if '\n' in response_clean:
                    lines = [l.strip() for l in response_clean.split('\n') if l.strip()]
                    # Find line with commas (CSV data), prefer last such line
                    csv_lines = [l for l in lines if ',' in l]
                    if csv_lines:
                        response_line = csv_lines[-1]  # Use last CSV line
                        self.status_display.append(f"[DEBUG] Multi-line response, using: '{response_line}'")
                    else:
                        response_line = lines[-1]  # Use last line if no CSV found

                # Extract value from comma-separated response
                # Example: "QS F,0" with index=1 → "0"
                parts = response_line.split(',')
                if precheck_index < len(parts):
                    compare_value = parts[precheck_index].strip()
                    self.status_display.append(f"[DEBUG] CSV field {precheck_index}: '{compare_value}' from '{response_line}'")
                else:
                    self.status_display.append(f"[DEBUG] CSV index {precheck_index} out of range for: '{response_line}'")

            # Try numeric comparison if both are numbers
            try:
                if float(compare_value) == float(expected_clean):
                    self.status_display.append(f"DUT state OK: {compare_value} == {expected_clean}")
                    return True
            except ValueError:
                pass

            # String comparison (case-insensitive)
            if compare_value.lower() == expected_clean.lower():
                self.status_display.append(f"DUT state OK: {compare_value}")
                return True

            # State mismatch - show dialog (show parsed value, not raw response)
            dialog = DUTStateMismatchDialog(
                command_name=precheck_cmd,
                expected=expected,
                actual=compare_value,
                test_info=test_info,
                prompt=precheck_prompt,
                parent=self,
            )

            if dialog.exec() != QDialog.DialogCode.Accepted:
                # User cancelled
                self.status_display.append("Pre-check cancelled by user")
                return False

            # User clicked Continue - loop back and recheck DUT state
            self.status_display.append("Rechecking DUT state...")

    def _execute_dut_postread(self, tp: Dict[str, Any]) -> Optional[float]:
        """
        Execute DUT post-read to capture measurement value.

        Returns the reading if successful, None otherwise.
        """
        postread_cmd = tp.get('dut_post_read_command')
        postread_param = tp.get('dut_post_read_param')  # Parameter for {value} substitution
        if not postread_cmd:
            return None  # No post-read configured

        if not self._dut_commands or not self._dut_com_port:
            return None

        # Query DUT for reading (pass parameter for {value} substitution)
        response = self._query_dut(postread_cmd, param=postread_param)
        if response is None:
            return None

        # Parse response based on parser type
        parser = tp.get('dut_post_read_parser', 'numeric')
        csv_index = tp.get('dut_post_read_index', 1)  # Default to position 1

        try:
            if parser == 'csv_field':
                # Handle multi-line responses (some devices send status line before data)
                response_line = response.strip()
                if '\n' in response_line:
                    lines = [l.strip() for l in response_line.split('\n') if l.strip()]
                    # Find line with commas (CSV data), prefer last such line
                    csv_lines = [l for l in lines if ',' in l]
                    if csv_lines:
                        response_line = csv_lines[-1]  # Use last CSV line
                        self.status_display.append(f"Multi-line response, using: {response_line}")
                    else:
                        response_line = lines[-1]  # Use last line if no CSV found

                # Extract value from comma-separated response
                # Example: "QM,+0.000E+00,VDC,AUTO" with index=1 → "+0.000E+00"
                fields = [f.strip() for f in response_line.split(',')]
                if csv_index < len(fields):
                    value_str = fields[csv_index]
                    self.status_display.append(f"CSV field {csv_index}: {value_str}")
                    # Try to convert to float
                    return float(value_str)
                else:
                    logger.warning(f"CSV index {csv_index} out of range (only {len(fields)} fields)")
                    self.status_display.append(f"CSV index {csv_index} out of range")
                    return None
            elif parser == 'numeric':
                # Handle multi-line responses for numeric parser too
                response_clean = response.strip()
                if '\n' in response_clean:
                    lines = [l.strip() for l in response_clean.split('\n') if l.strip()]
                    csv_lines = [l for l in lines if ',' in l]
                    if csv_lines:
                        response_clean = csv_lines[-1]

                # Extract first number from response
                import re
                match = re.search(r'-?\d+\.?\d*[eE]?[+-]?\d*', response_clean)
                if match:
                    return float(match.group())
            elif parser == 'string':
                # Return raw string (caller handles conversion)
                return response
            else:
                # Default to float conversion
                return float(response.strip())
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse DUT response '{response}': {e}")
            self.status_display.append(f"Could not parse DUT response: {response}")

        return None

    def _get_calibrator_address(self) -> Optional[str]:
        """Get the VISA address of the selected calibrator."""
        if not self._selected_calibrator:
            return None
        return self._selected_calibrator.get("detected_address") or self._selected_calibrator.get("address")

    def _send_calibrator_commands(self, source_cmd: str, operate_cmd: Optional[str] = None) -> bool:
        """Send source and operate commands to calibrator."""
        address = self._get_calibrator_address()
        if not address:
            return False

        visa = get_visa_manager()
        success = True

        if source_cmd:
            if visa.write(address, source_cmd):
                self.status_display.append(f"Sent to calibrator: {source_cmd}")
            else:
                self.status_display.append(f"FAILED: {source_cmd}")
                success = False

        if operate_cmd and success:
            if visa.write(address, operate_cmd):
                self.status_display.append(f"Sent: {operate_cmd}")
            else:
                self.status_display.append(f"FAILED: {operate_cmd}")
                success = False

        return success

    def _execute_section_command(self, command: str):
        """Execute a section command when entering a new section.

        Tries to look up the command in the command bank first (for generic names
        like STANDBY, RESET). If not found, sends the raw command string.
        """
        if not command:
            return

        address = self._get_calibrator_address()
        if not address:
            self.status_display.append(f"Section command: {command} (no calibrator connected)")
            return

        visa = get_visa_manager()

        # Try to look up in command bank first (e.g., "STANDBY" -> "STBY")
        actual_command = self._get_calibrator_command(command.upper())
        if not actual_command:
            # Not found in bank, use raw command
            actual_command = command

        self.status_display.append(f"Executing section command: {actual_command}")

        if visa.write(address, actual_command):
            self.status_display.append(f"Section command sent successfully")
        else:
            self.status_display.append(f"WARNING: Section command failed to send")

    def _safe_shutdown_calibrator(self):
        """Put calibrator into standby and reset for safe shutdown."""
        if not self._selected_calibrator:
            return

        address = self._get_calibrator_address()
        if not address:
            return

        visa = get_visa_manager()

        self.status_display.append("Shutting down calibrator...")

        # Use standard command names: STANDBY, RESET
        stby_cmd = self._get_calibrator_command("STANDBY") or self._get_calibrator_command("STBY")
        if stby_cmd:
            if visa.write(address, stby_cmd):
                self.status_display.append(f"Sent STANDBY: {stby_cmd}")
            else:
                self.status_display.append(f"WARNING: Failed to send STANDBY")

        # Use RESET command from command bank, fallback to *RST
        reset_cmd = self._get_calibrator_command("RESET") or "*RST"
        if visa.write(address, reset_cmd):
            self.status_display.append(f"Sent RESET: {reset_cmd}")
        else:
            self.status_display.append("WARNING: Failed to send RESET")

        self.status_display.append("Calibrator in standby mode")

    def _reset_all_workstation_standards(self):
        """Send Reset command to ALL workstation standards for safety when jumping test points."""
        logger.info("SAFETY: Resetting all workstation standards before jump")
        self.status_display.append("SAFETY: Resetting workstation standards...")

        visa = get_visa_manager()
        if not visa:
            logger.warning("VISA manager not available for reset")
            return

        db = get_db()
        if not db.is_connected:
            logger.warning("Database not connected for reset")
            return

        try:
            settings = get_settings()
            workstation_name = settings.workstation_name or "Default Workstation"

            with db.session() as session:
                config = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == workstation_name
                ).first()

                if not config:
                    logger.warning(f"No workstation config found for '{workstation_name}'")
                    return

                # Get ALL active workstation standards
                ws_standards = session.query(WorkstationStandard).filter(
                    WorkstationStandard.workstation_id == config.id,
                    WorkstationStandard.is_active != False
                ).all()

                logger.info(f"Found {len(ws_standards)} active workstation standards to reset")

                reset_count = 0
                for ws_std in ws_standards:
                    standard = session.query(Standard).filter(
                        Standard.id == ws_std.standard_id
                    ).first()

                    if not standard:
                        continue

                    # Get address
                    address = ws_std.visa_address or standard.visa_address
                    if not address:
                        continue

                    # Try to get Reset command from command bank
                    command_bank = session.query(CommandBank).filter(
                        CommandBank.make.ilike(standard.make),
                        CommandBank.model.ilike(standard.model)
                    ).first()

                    reset_cmd = "*RST"  # Default
                    if command_bank and command_bank.commands:
                        import json
                        try:
                            commands = json.loads(command_bank.commands) if isinstance(command_bank.commands, str) else command_bank.commands
                            for ref_name, cmd in commands.items():
                                # Check for Reset Reference, Reset, or RST
                                ref_upper = ref_name.upper()
                                if 'RESET' in ref_upper or ref_upper == 'RST':
                                    reset_cmd = cmd
                                    logger.debug(f"Found reset command '{ref_name}' -> '{cmd}'")
                                    break
                        except Exception as e:
                            logger.warning(f"Error parsing command bank: {e}")

                    # Send reset command
                    try:
                        logger.info(f"Sending reset '{reset_cmd}' to {standard.make} {standard.model} at {address}")
                        if visa.write(address, reset_cmd):
                            reset_count += 1
                            logger.info(f"Reset sent successfully to {standard.make} {standard.model}")
                        else:
                            logger.warning(f"Reset write returned False for {standard.make} {standard.model}")
                    except Exception as e:
                        logger.warning(f"Failed to reset {standard.make} {standard.model}: {e}")

                if reset_count > 0:
                    self.status_display.append(f"SAFETY: Reset sent to {reset_count} instrument(s)")

        except Exception as e:
            logger.error(f"Error resetting workstation standards: {e}")

    def _substitute_placeholders(self, command: str, tp: Dict[str, Any]) -> str:
        """
        Substitute placeholders in command with test point values.

        Placeholders:
            {value} - Nominal value (e.g., 10)
            {unit} - Unit string (e.g., V, mV, A, Ohm)
            {frequency} - Frequency value as stored (e.g., 1 if 1 kHz)
            {freq_unit} - Frequency unit string (e.g., Hz, kHz, MHz)
            {freq_hz} - Frequency converted to Hz (e.g., 1000 for 1 kHz)

        If frequency > 0 and command doesn't contain frequency placeholders,
        automatically appends ",{freq_hz} HZ" for AC outputs.
        """
        if not command:
            return ""

        value = tp.get("nominal_value", 0)
        unit = tp.get("unit", "")
        frequency = tp.get("frequency", 0) or 0
        freq_unit = tp.get("frequency_unit", "Hz")

        # Calculate frequency in Hz
        freq_hz = frequency
        if freq_unit == "kHz":
            freq_hz = frequency * 1000
        elif freq_unit == "MHz":
            freq_hz = frequency * 1000000

        result = command

        # Auto-append frequency for AC outputs if command doesn't have frequency placeholder
        has_freq_placeholder = "{freq" in command or "{frequency}" in command
        if freq_hz > 0 and not has_freq_placeholder:
            # Append frequency in Fluke-style format: OUT 1 V,60 HZ
            result = result + ",{freq_hz} HZ"

        result = result.replace("{value}", str(value))
        result = result.replace("{unit}", unit)
        result = result.replace("{frequency}", str(frequency) if frequency > 0 else "")
        result = result.replace("{freq_unit}", freq_unit if frequency > 0 else "")
        result = result.replace("{freq_hz}", str(int(freq_hz)) if freq_hz > 0 else "")

        return result

    def _substitute_pre_placeholders(self, command: str, tp: Dict[str, Any]) -> str:
        """
        Substitute placeholders using pre-conditioning values.
        Used to build the pre-conditioning command.
        """
        if not command:
            return ""

        value = tp.get("pre_nominal_value", 0) or 0
        unit = tp.get("pre_unit", "") or ""
        frequency = tp.get("pre_frequency", 0) or 0
        freq_unit = tp.get("pre_frequency_unit", "Hz") or "Hz"

        # Calculate frequency in Hz
        freq_hz = frequency
        if freq_unit == "kHz":
            freq_hz = frequency * 1000
        elif freq_unit == "MHz":
            freq_hz = frequency * 1000000

        result = command

        # Auto-append frequency for AC outputs if command doesn't have frequency placeholder
        has_freq_placeholder = "{freq" in command or "{frequency}" in command
        if freq_hz > 0 and not has_freq_placeholder:
            result = result + ",{freq_hz} HZ"

        result = result.replace("{value}", str(value))
        result = result.replace("{unit}", unit)
        result = result.replace("{frequency}", str(frequency) if frequency > 0 else "")
        result = result.replace("{freq_unit}", freq_unit if frequency > 0 else "")
        result = result.replace("{freq_hz}", str(int(freq_hz)) if freq_hz > 0 else "")

        return result

    def _has_preconditioning(self, tp: Dict[str, Any]) -> bool:
        """Check if test point has pre-conditioning configured."""
        pre_val = tp.get("pre_nominal_value")
        return pre_val is not None and pre_val != 0

    # -------------------------------------------------------------------------

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

        # Session setup bar - compact single row
        setup_layout = QHBoxLayout()
        setup_layout.setContentsMargins(5, 2, 5, 2)
        setup_layout.setSpacing(10)

        setup_layout.addWidget(QLabel("DUT:"))
        self.dut_combo = QComboBox()
        self.dut_combo.setMinimumWidth(180)
        self.dut_combo.setEditable(True)
        self.dut_combo.setPlaceholderText("Select DUT...")
        setup_layout.addWidget(self.dut_combo)

        setup_layout.addWidget(QLabel("WO:"))
        self.workorder_input = QLineEdit()
        self.workorder_input.setMaximumWidth(120)
        self.workorder_input.setPlaceholderText("Work order")
        setup_layout.addWidget(self.workorder_input)

        setup_layout.addWidget(QLabel("Procedure:"))
        self.procedure_combo = QComboBox()
        self.procedure_combo.setMinimumWidth(180)
        setup_layout.addWidget(self.procedure_combo)

        setup_layout.addStretch()

        self.start_btn = QPushButton("Start Session")
        self.start_btn.clicked.connect(self._on_start_session)
        setup_layout.addWidget(self.start_btn)

        self.continue_btn = QPushButton("Continue Session")
        self.continue_btn.clicked.connect(self._on_continue_session)
        self.continue_btn.setToolTip("Resume a previous incomplete session")
        setup_layout.addWidget(self.continue_btn)

        layout.addLayout(setup_layout)

        # Main execution area
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - Current test and status
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Current test point display
        current_group = QGroupBox("Current Test Point")
        current_layout = QVBoxLayout(current_group)
        current_layout.setContentsMargins(5, 10, 5, 5)

        # Layout for the display + high voltage warning side by side
        nominal_hv_layout = QHBoxLayout()

        # Combined display showing Section / Test Point and Nominal value
        display_widget = QWidget()
        display_layout = QVBoxLayout(display_widget)
        display_layout.setContentsMargins(15, 10, 15, 10)
        display_layout.setSpacing(5)
        display_widget.setStyleSheet(
            "QWidget { background-color: #2d2d2d; border-radius: 10px; }"
        )

        # Section / Test Point line (auto-sized)
        self.section_testpoint_label = QLabel("-- / --")
        self.section_testpoint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.section_testpoint_label.setWordWrap(True)
        self.section_testpoint_label.setStyleSheet(
            "QLabel { color: #00ff00; font-size: 22px; font-weight: bold; background: transparent; }"
        )
        display_layout.addWidget(self.section_testpoint_label)

        # Nominal value line
        self.nominal_display = QLabel("-- V")
        self.nominal_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nominal_display.setWordWrap(True)
        self.nominal_display.setStyleSheet(
            "QLabel { color: #ffff00; font-size: 32px; font-weight: bold; background: transparent; }"
        )
        display_layout.addWidget(self.nominal_display)

        # Tolerance line (smaller)
        self.tolerance_display = QLabel("")
        self.tolerance_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tolerance_display.setStyleSheet(
            "QLabel { color: #aaaaaa; font-size: 14px; background: transparent; }"
        )
        display_layout.addWidget(self.tolerance_display)

        display_widget.setMinimumHeight(120)
        nominal_hv_layout.addWidget(display_widget, stretch=1)

        # High Voltage Warning - hidden by default
        self.hv_warning_label = QLabel()
        self.hv_warning_label.setFixedSize(100, 100)
        self.hv_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hv_warning_label.setVisible(False)

        # Load the high voltage image
        import os
        import sys
        # Handle both development mode and PyInstaller bundled mode
        if getattr(sys, 'frozen', False):
            # Running as bundled exe - resources are in _MEIPASS
            base_path = sys._MEIPASS
        else:
            # Running in development - go up from execution_tab.py to project root
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        hv_image_path = os.path.join(base_path, "resources", "images", "HighVoltage.png")
        if os.path.exists(hv_image_path):
            pixmap = QPixmap(hv_image_path)
            self._hv_pixmap = pixmap.scaled(
                QSize(120, 120),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.hv_warning_label.setPixmap(self._hv_pixmap)
        else:
            self._hv_pixmap = None
            self.hv_warning_label.setText("⚡HV⚡")
            self.hv_warning_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")

        # Opacity effect for fading animation
        self._hv_opacity_effect = QGraphicsOpacityEffect()
        self._hv_opacity_effect.setOpacity(1.0)
        self.hv_warning_label.setGraphicsEffect(self._hv_opacity_effect)

        # Fade animations
        self._hv_fade_out = QPropertyAnimation(self._hv_opacity_effect, b"opacity")
        self._hv_fade_out.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._hv_fade_in = QPropertyAnimation(self._hv_opacity_effect, b"opacity")
        self._hv_fade_in.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # Chain animations
        self._hv_fade_out.finished.connect(self._start_hv_fade_in)
        self._hv_fade_in.finished.connect(self._start_hv_fade_out_delayed)

        # Delay timer
        self._hv_delay_timer = QTimer()
        self._hv_delay_timer.setSingleShot(True)
        self._hv_delay_timer.timeout.connect(self._start_hv_fade_out)

        self._hv_warning_active = False

        nominal_hv_layout.addWidget(self.hv_warning_label)

        current_layout.addLayout(nominal_hv_layout)

        # Hidden labels for backwards compatibility (used by other methods)
        self.section_label = QLabel("--")
        self.section_label.setVisible(False)
        self.testpoint_label = QLabel("--")
        self.testpoint_label.setVisible(False)
        self.tolerance_label = QLabel("--")
        self.tolerance_label.setVisible(False)

        left_layout.addWidget(current_group)

        # Instrument status - compact
        status_group = QGroupBox("Instrument Status")
        status_layout = QVBoxLayout(status_group)
        status_layout.setContentsMargins(5, 5, 5, 5)

        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setMaximumHeight(80)
        self.status_display.setPlaceholderText("Status messages...")
        status_layout.addWidget(self.status_display)

        left_layout.addWidget(status_group, stretch=0)

        # Wiring diagram - larger display
        wiring_group = QGroupBox("Wiring Diagram")
        wiring_layout = QVBoxLayout(wiring_group)
        wiring_layout.setContentsMargins(5, 5, 5, 5)

        self.wiring_label = QLabel("No wiring diagram available")
        self.wiring_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wiring_label.setMinimumHeight(250)
        self.wiring_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.wiring_label.setStyleSheet(
            "QLabel { background-color: #f5f5f5; border: 1px solid #ccc; border-radius: 5px; }"
        )
        self.wiring_label.setScaledContents(False)  # We'll handle scaling in _display_diagram_image
        wiring_layout.addWidget(self.wiring_label)

        left_layout.addWidget(wiring_group, stretch=2)  # Give wiring diagram more space

        # Hidden widgets for compatibility with existing code
        # (Input method and DMM are now selected via SessionStartDialog)
        self.input_method_combo = QComboBox()
        self.input_method_combo.addItems(["Keyboard Entry", "Remote Reading", "Webcam OCR"])
        self.input_method_combo.setVisible(False)

        self.dmm_combo = QComboBox()
        self.dmm_combo.addItem("-- Select DMM --", None)
        self.dmm_combo.setVisible(False)

        self.init_dmm_btn = QPushButton("Init")
        self.init_dmm_btn.setVisible(False)

        # Reading entry - simplified (input method selected at session start)
        input_group = QGroupBox("Reading")
        input_layout = QVBoxLayout(input_group)

        # Input mode indicator (shows what was selected at session start)
        self.input_mode_label = QLabel("Mode: Keyboard Entry")
        self.input_mode_label.setStyleSheet("color: #666; font-size: 11px;")
        input_layout.addWidget(self.input_mode_label)

        # Large reading entry field
        self.reading_input = QLineEdit()
        self.reading_input.setPlaceholderText("Enter reading...")
        font = QFont()
        font.setPointSize(24)  # Larger font for easier reading
        self.reading_input.setFont(font)
        self.reading_input.setMinimumHeight(50)
        self.reading_input.returnPressed.connect(self._on_submit_reading)
        input_layout.addWidget(self.reading_input)

        # Buttons row
        reading_layout = QHBoxLayout()

        self.submit_btn = QPushButton("Submit")
        self.submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
            }
            QPushButton:hover { background-color: #0056b3; }
        """)
        self.submit_btn.clicked.connect(self._on_submit_reading)
        reading_layout.addWidget(self.submit_btn)

        reading_layout.addStretch()

        # Hidden buttons for compatibility (kept for existing code references)
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

        # Primary action - Advance to next test point
        self.advance_btn = QPushButton("▶ Advance")
        self.advance_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
            }
            QPushButton:hover { background-color: #218838; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.advance_btn.clicked.connect(self._on_advance)
        self.advance_btn.setEnabled(False)
        control_layout.addWidget(self.advance_btn)

        control_layout.addSpacing(20)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self._on_pause)
        self.pause_btn.setEnabled(False)
        control_layout.addWidget(self.pause_btn)

        self.skip_btn = QPushButton("Skip")
        self.skip_btn.clicked.connect(self._on_skip)
        self.skip_btn.setEnabled(False)
        control_layout.addWidget(self.skip_btn)

        self.redo_btn = QPushButton("Redo")
        self.redo_btn.clicked.connect(self._on_redo)
        self.redo_btn.setEnabled(False)
        control_layout.addWidget(self.redo_btn)

        control_layout.addStretch()

        # Terminate session button
        self.stop_btn = QPushButton("■ Terminate Session")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                padding: 8px 15px;
            }
            QPushButton:hover { background-color: #c82333; }
            QPushButton:disabled { background-color: #6c757d; }
        """)
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

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
        self.testpoints_table.cellClicked.connect(self._on_testpoint_clicked)
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

        logger.info(f"Starting session: DUT={dut_id}, WO={workorder}, Proc={procedure_id}")
        self.status_display.clear()
        self.status_display.append("Starting session...")

        if not dut_id:
            QMessageBox.warning(self, "Validation Error", "Please select a DUT.")
            self.status_display.append("ERROR: No DUT selected")
            return

        if not workorder:
            QMessageBox.warning(self, "Validation Error", "Work order is required.")
            self.status_display.append("ERROR: No work order")
            return

        if not procedure_id:
            QMessageBox.warning(self, "Validation Error", "Please select a procedure.")
            self.status_display.append("ERROR: No procedure selected")
            return

        self.status_display.append(f"DUT ID: {dut_id}")
        self.status_display.append(f"Procedure ID: {procedure_id}")
        self.status_display.append("Detecting calibrators...")

        # Select calibrator before starting session
        self._selected_calibrator = None  # Clear any previous selection
        self._calibrator_commands = None
        calibrator = self._select_calibrator()

        if not calibrator:
            # User cancelled or no calibrator found
            self.status_display.append("No calibrator detected")
            reply = QMessageBox.question(
                self, "Continue Without Calibrator?",
                "No calibrator was selected.\n\n"
                "Do you want to continue without automatic calibrator control?\n"
                "(You'll need to set the calibrator manually)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.status_display.append("Session cancelled - no calibrator")
                return
            self.status_display.append("Continuing without calibrator...")

        # Show session start dialog for COM port / input method selection
        try:
            session_dialog = SessionStartDialog(self)
            result = session_dialog.exec()
            if result != QDialog.DialogCode.Accepted:
                self.status_display.append("Session cancelled by user")
                return

            # Store the selected input method and COM port
            self._session_input_method = session_dialog.get_input_method()
            self._session_com_port = session_dialog.get_selected_port()
        except Exception as e:
            logger.error(f"Session dialog error: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Session dialog failed:\n{e}")
            return

        # Log the selection
        self.status_display.append(f"[DEBUG] _session_input_method = {self._session_input_method}")
        self.status_display.append(f"[DEBUG] _session_com_port = {self._session_com_port}")
        if self._session_com_port:
            self.status_display.append(f"DUT Serial Port: {self._session_com_port}")
            self.status_display.append("Input Mode: Remote Automation")
        else:
            self.status_display.append(f"Input Mode: {self._session_input_method.title()}")

        db = get_db()
        if not db.is_connected:
            QMessageBox.critical(self, "Database Error", "Not connected to database.")
            return

        try:
            with db.session() as session:
                # Get technician from settings
                settings = get_settings()
                technician = getattr(settings, 'technician_name', None) or 'Unknown'

                # Get asset number from DUT
                dut = session.query(DUT).filter(DUT.id == dut_id).first()
                asset_number = dut.asset_number if dut else workorder

                # Create calibration session
                cal_session = CalibrationSession(
                    dut_id=dut_id,
                    procedure_id=procedure_id,
                    work_order=workorder,
                    asset_number=asset_number,
                    technician_name=technician,
                    started_at=datetime.now(),
                    status="in_progress",
                )
                session.add(cal_session)
                session.flush()

                self._current_session_id = cal_session.id
                self._current_dut_id = dut_id
                self._current_procedure_id = procedure_id

                logger.info(f"Started session {cal_session.id}: DUT={dut_id}, WO={workorder}")
                if self._selected_calibrator:
                    logger.info(f"Using calibrator: {self._selected_calibrator['make']} {self._selected_calibrator['model']}")

            # Update UI for running state
            self.start_btn.setText("Session Running")
            self.start_btn.setEnabled(False)
            self.dut_combo.setEnabled(False)
            self.workorder_input.setEnabled(False)
            self.procedure_combo.setEnabled(False)

            # Update input mode display
            if self._session_input_method == "remote":
                self.input_mode_label.setText(f"Mode: Remote ({self._session_com_port})")
                self.input_mode_label.setStyleSheet("color: #28a745; font-size: 11px; font-weight: bold;")
                # For remote, reading will auto-populate - show but disable manual entry
                self.reading_input.setPlaceholderText("Reading will auto-populate...")
            elif self._session_input_method == "ocr":
                self.input_mode_label.setText("Mode: Webcam OCR")
                self.input_mode_label.setStyleSheet("color: #17a2b8; font-size: 11px; font-weight: bold;")
                self.reading_input.setPlaceholderText("Reading will be captured...")
            else:
                self.input_mode_label.setText("Mode: Keyboard Entry")
                self.input_mode_label.setStyleSheet("color: #666; font-size: 11px;")
                self.reading_input.setPlaceholderText("Enter reading...")

            # Show calibrator info in status
            if self._selected_calibrator:
                cal_info = f"{self._selected_calibrator['make']} {self._selected_calibrator['model']}"
                self.status_display.append(f"Calibrator: {cal_info}")
                self.status_display.append(f"Address: {self._get_calibrator_address()}")

            # Load DUT commands for remote communication
            self._load_dut_commands()

            # Load test points and start execution
            self._load_test_points()

        except Exception as e:
            logger.error(f"Failed to start session: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start session:\n{e}")

    def _on_continue_session(self):
        """Continue a previous incomplete session."""
        # Get selected DUT
        dut_id = self.dut_combo.currentData()
        if not dut_id:
            QMessageBox.warning(self, "No DUT", "Please select a DUT first.")
            return

        db = get_db()
        if not db.is_connected:
            QMessageBox.warning(self, "Database Error", "Database not connected.")
            return

        try:
            with db.session() as session:
                # Find incomplete/aborted sessions for this DUT
                # Use string values for SQLite compatibility
                incomplete_sessions = session.query(CalibrationSession).filter(
                    CalibrationSession.dut_id == dut_id,
                    CalibrationSession.status.in_([
                        SessionStatus.IN_PROGRESS.value,
                        SessionStatus.ABORTED.value,
                        SessionStatus.PAUSED.value
                    ])
                ).order_by(CalibrationSession.started_at.desc()).limit(10).all()

                if not incomplete_sessions:
                    QMessageBox.information(
                        self, "No Sessions",
                        "No incomplete sessions found for this DUT.\n\n"
                        "Use 'Start Session' to begin a new calibration."
                    )
                    return

                # Build list for selection dialog
                # Count results with a separate query to avoid enum loading issues
                session_items = []
                for s in incomplete_sessions:
                    proc_name = s.procedure.name if s.procedure else "Unknown"
                    started = s.started_at.strftime("%Y-%m-%d %H:%M") if s.started_at else "Unknown"
                    # Handle both enum and string (SQLite returns string)
                    status = s.status.value if hasattr(s.status, 'value') else (s.status or "unknown")
                    # Count results with separate query
                    result_count = session.query(TestResult).filter(
                        TestResult.session_id == s.id
                    ).count()
                    session_items.append(
                        f"Session {s.id}: {proc_name} - Started {started} - {status} ({result_count} readings)"
                    )

                # Show selection dialog
                from PyQt6.QtWidgets import QInputDialog
                selected, ok = QInputDialog.getItem(
                    self,
                    "Continue Session",
                    "Select a session to continue:",
                    session_items,
                    0,
                    False
                )

                if not ok or not selected:
                    return

                # Get selected session
                selected_idx = session_items.index(selected)
                selected_session = incomplete_sessions[selected_idx]

                # Store session info
                self._current_session_id = selected_session.id
                self._current_dut_id = selected_session.dut_id
                self._current_procedure_id = selected_session.procedure_id

                # Update workorder if set
                if selected_session.work_order:
                    self.workorder_input.setText(selected_session.work_order)

                # Set procedure combo to match
                for i in range(self.procedure_combo.count()):
                    if self.procedure_combo.itemData(i) == selected_session.procedure_id:
                        self.procedure_combo.setCurrentIndex(i)
                        break

                # Update session status to in_progress (use string for SQLite)
                selected_session.status = SessionStatus.IN_PROGRESS.value
                session.commit()

                logger.info(f"Continuing session {self._current_session_id}")

        except Exception as e:
            logger.error(f"Failed to find sessions: {e}")
            QMessageBox.critical(self, "Error", f"Failed to find sessions:\n{e}")
            return

        # Select calibrator
        if not self._select_calibrator():
            self.status_display.append("Session resumed without calibrator")

        # Enable control buttons
        self.advance_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)
        self.redo_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)

        # Disable start controls
        self.start_btn.setText("Session Running")
        self.start_btn.setEnabled(False)
        self.continue_btn.setEnabled(False)
        self.dut_combo.setEnabled(False)
        self.workorder_input.setEnabled(False)
        self.procedure_combo.setEnabled(False)

        self.status_display.append("=" * 40)
        self.status_display.append(f"CONTINUING SESSION {self._current_session_id}")

        # Show calibrator info
        if self._selected_calibrator:
            cal_info = f"{self._selected_calibrator['make']} {self._selected_calibrator['model']}"
            self.status_display.append(f"Calibrator: {cal_info}")

        # Load test points WITH existing results
        self._load_test_points_with_results()

    def _load_test_points_with_results(self):
        """Load test points and restore previous session results."""
        if not self._current_procedure_id or not self._current_session_id:
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

                # Get existing results for this session using raw query to avoid enum issues
                existing_results = {}
                from sqlalchemy import text
                raw_results = session.execute(text(
                    "SELECT test_point_id, measured_value, status FROM test_results "
                    "WHERE session_id = :sid ORDER BY id"
                ), {"sid": self._current_session_id}).fetchall()
                for r in raw_results:
                    # Keep only the latest result for each test point
                    # r is (test_point_id, measured_value, status)
                    existing_results[r[0]] = {
                        "measured_value": r[1],
                        "status": r[2]  # This is the raw string value
                    }

                # Load all sections and test points
                for section in procedure.sections:
                    for tp in section.test_points:
                        self._test_points.append({
                            "id": tp.id,
                            "section_id": section.id,
                            "section_name": section.name,
                            "standard_section_type": section.standard_section_type,
                            "section_command": section.section_command,
                            "section_prompt": section.section_prompt,
                            "section_wiring_type": section.section_wiring_type,
                            "description": tp.description or f"{tp.nominal_value} {tp.unit}",
                            "nominal_value": tp.nominal_value,
                            "unit": tp.unit,
                            "frequency": tp.frequency,
                            "frequency_unit": tp.frequency_unit or "Hz",
                            "tolerance_value": tp.tolerance_value,
                            "tolerance_type": tp.tolerance_type.value if tp.tolerance_type else "percent",
                            "tol_pct_reading": tp.tol_pct_reading,
                            "tol_pct_range": tp.tol_pct_range,
                            "tol_digits": tp.tol_digits,
                            "tol_absolute": tp.tol_absolute,
                            "tol_resolution": tp.tol_resolution,
                            "tol_range_value": tp.tol_range_value,
                            "source_command": tp.source_command,
                            "operate_command": tp.operate_command,
                            "measure_command": tp.measure_command,
                            "test_type": tp.test_type.value if tp.test_type else "measurement",
                            "pass_fail_prompt": tp.pass_fail_prompt,
                            "pass_fail_image": tp.pass_fail_image,
                            "operator_prompt": tp.operator_prompt,
                            "pre_nominal_value": tp.pre_nominal_value,
                            "pre_unit": tp.pre_unit,
                            "pre_frequency": tp.pre_frequency,
                            "pre_frequency_unit": tp.pre_frequency_unit or "Hz",
                            "pre_delay_seconds": tp.pre_delay_seconds or 0,
                            "manual_setup": tp.manual_setup or False,
                            "manual_setup_prompt": tp.manual_setup_prompt,
                            "pre_conditioning_steps": tp.pre_conditioning_steps or [],
                            "measurement_target": tp.measurement_target.value if tp.measurement_target else "PRIMARY",
                            "expected_value": tp.expected_value,
                            "expected_unit": tp.expected_unit,
                            "wiring_diagram_type": tp.wiring_diagram_type,
                            # Pass/Fail range check fields
                            "pass_fail_min": tp.pass_fail_min,
                            "pass_fail_max": tp.pass_fail_max,
                            "pass_fail_range_unit": tp.pass_fail_range_unit,
                            "pass_fail_comparison_type": tp.pass_fail_comparison_type,
                            # DMM configuration
                            "dmm_config": tp.dmm_config,
                        })

            # Populate table with results
            self.testpoints_table.setRowCount(len(self._test_points))
            self.progress_bar.setMaximum(len(self._test_points))

            completed_count = 0
            first_pending_row = None

            for i, tp in enumerate(self._test_points):
                # Number
                self.testpoints_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))

                # Section / Test
                section_test = f"{tp['section_name']} / {tp['description']}"
                self.testpoints_table.setItem(i, 1, QTableWidgetItem(section_test))

                # Nominal
                nominal_str = f"{tp['nominal_value']} {tp['unit']}"
                if tp.get('frequency'):
                    nominal_str += f" @ {tp['frequency']} {tp.get('frequency_unit', 'Hz')}"
                self.testpoints_table.setItem(i, 2, QTableWidgetItem(nominal_str))

                # Check for existing result
                result = existing_results.get(tp['id'])
                if result:
                    # Measured value
                    if result['measured_value'] is not None:
                        measured_str = f"{result['measured_value']}"
                        self.testpoints_table.setItem(i, 3, QTableWidgetItem(measured_str))
                    else:
                        self.testpoints_table.setItem(i, 3, QTableWidgetItem(""))

                    # Status with color - handle both enum and string values
                    status_raw = result['status']
                    if status_raw:
                        # Handle both "pass"/"fail" strings and "PASS"/"FAIL" enum values
                        status_text = str(status_raw).lower()
                    else:
                        status_text = "pending"
                    status_item = QTableWidgetItem(status_text.capitalize())
                    if status_text == "pass":
                        status_item.setBackground(QColor(200, 255, 200))
                        completed_count += 1
                    elif status_text == "fail":
                        status_item.setBackground(QColor(255, 200, 200))
                        completed_count += 1
                    self.testpoints_table.setItem(i, 4, status_item)
                else:
                    # No result - pending
                    self.testpoints_table.setItem(i, 3, QTableWidgetItem(""))
                    self.testpoints_table.setItem(i, 4, QTableWidgetItem("Pending"))
                    if first_pending_row is None:
                        first_pending_row = i

            # Update progress
            self.progress_bar.setValue(completed_count)

            # Select first pending test point, or first if all complete
            start_row = first_pending_row if first_pending_row is not None else 0
            self._current_test_index = start_row
            self.testpoints_table.selectRow(start_row)

            self.status_display.append(f"Loaded {len(self._test_points)} test points")
            self.status_display.append(f"Previous results: {completed_count} completed")
            if first_pending_row is not None:
                self.status_display.append(f"Resuming from test point {first_pending_row + 1}")
            else:
                self.status_display.append("All test points completed - review or redo as needed")

            self.status_display.append("SESSION RESUMED - Ready to continue")

        except Exception as e:
            logger.error(f"Failed to load test points with results: {e}")
            self.status_display.append(f"ERROR: {e}")

    def _load_test_points(self):
        """Load test points from procedure into the table.

        Loads from .csp file if available, otherwise falls back to database.
        """
        if not self._current_procedure_id:
            self.status_display.append("ERROR: No procedure ID set")
            return

        db = get_db()
        if not db.is_connected:
            self.status_display.append("ERROR: Database not connected")
            return

        self.status_display.append("Loading test points...")

        self._test_points = []
        self._current_csp_data = None  # Clear any previous CSP data
        self.testpoints_table.setRowCount(0)

        try:
            with db.session() as session:
                procedure = session.query(Procedure).filter(
                    Procedure.id == self._current_procedure_id
                ).first()

                if not procedure:
                    QMessageBox.warning(self, "Error", "Procedure not found.")
                    return

                # Check if procedure has a CSP file
                if procedure.file_path and os.path.exists(procedure.file_path):
                    self.status_display.append(f"Loading from CSP: {os.path.basename(procedure.file_path)}")
                    self._load_test_points_from_csp(procedure.file_path)
                    return  # CSP loading handles the rest

                # Fall back to database loading
                self.status_display.append("Loading from database...")

                # Clean up any corrupted section names (with accumulated [type] suffixes)
                sections_cleaned = False
                for section in procedure.sections:
                    original_name = section.name
                    clean_name = original_name
                    # Remove all trailing [...] suffixes that may have accumulated
                    while re.search(r'\s*\[[^\]]+\]\s*$', clean_name):
                        clean_name = re.sub(r'\s*\[[^\]]+\]\s*$', '', clean_name).strip()
                    if clean_name != original_name:
                        section.name = clean_name
                        sections_cleaned = True
                        logger.info(f"Cleaned corrupted section name: '{original_name}' -> '{clean_name}'")

                if sections_cleaned:
                    session.commit()

                # Load all sections and test points from database
                for section in procedure.sections:
                    for tp in section.test_points:
                        self._test_points.append({
                            "id": tp.id,
                            "section_id": section.id,
                            "section_name": section.name,
                            "standard_section_type": section.standard_section_type,
                            "section_command": section.section_command,
                            "section_prompt": section.section_prompt,
                            "section_wiring_type": section.section_wiring_type,
                            "description": tp.description or f"{tp.nominal_value} {tp.unit}",
                            "nominal_value": tp.nominal_value,
                            "unit": tp.unit,
                            "frequency": tp.frequency,
                            "frequency_unit": tp.frequency_unit or "Hz",
                            "tolerance_value": tp.tolerance_value,
                            "tolerance_type": tp.tolerance_type.value if tp.tolerance_type else "percent",
                            "tol_pct_reading": tp.tol_pct_reading,
                            "tol_pct_range": tp.tol_pct_range,
                            "tol_digits": tp.tol_digits,
                            "tol_absolute": tp.tol_absolute,
                            "tol_resolution": tp.tol_resolution,
                            "tol_range_value": tp.tol_range_value,
                            "source_command": tp.source_command,
                            "operate_command": tp.operate_command,
                            "measure_command": tp.measure_command,
                            "test_type": tp.test_type.value if tp.test_type else "measurement",
                            "pass_fail_prompt": tp.pass_fail_prompt,
                            "pass_fail_image": tp.pass_fail_image,
                            "operator_prompt": tp.operator_prompt,
                            # Pre-conditioning
                            "pre_nominal_value": tp.pre_nominal_value,
                            "pre_unit": tp.pre_unit,
                            "pre_frequency": tp.pre_frequency,
                            "pre_frequency_unit": tp.pre_frequency_unit or "Hz",
                            "pre_delay_seconds": tp.pre_delay_seconds or 0,
                            "manual_setup": tp.manual_setup or False,
                            "manual_setup_prompt": tp.manual_setup_prompt,
                            "pre_conditioning_steps": tp.pre_conditioning_steps or [],
                            # Measurement target - what value to compare reading against
                            "measurement_target": tp.measurement_target.value if tp.measurement_target else "PRIMARY",
                            "expected_value": tp.expected_value,
                            "expected_unit": tp.expected_unit,
                            # Test point specific wiring diagram
                            "wiring_diagram_type": tp.wiring_diagram_type,
                            # Pass/Fail range check fields
                            "pass_fail_min": tp.pass_fail_min,
                            "pass_fail_max": tp.pass_fail_max,
                            "pass_fail_range_unit": tp.pass_fail_range_unit,
                            "pass_fail_comparison_type": tp.pass_fail_comparison_type,
                            # DMM configuration
                            "dmm_config": tp.dmm_config,
                        })

        except Exception as e:
            logger.error(f"Failed to load test points: {e}")
            self.status_display.append(f"ERROR loading test points: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load test points:\n{e}")
            return

        if not self._test_points:
            self.status_display.append("ERROR: Procedure has no test points!")
            QMessageBox.warning(self, "No Test Points", "This procedure has no test points.\n\nAdd test points in the Procedures tab first.")
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
                nominal_str += f" @ {tp['frequency']} {tp.get('frequency_unit', 'Hz')}"
            self.testpoints_table.setItem(i, 2, QTableWidgetItem(nominal_str))

            # Measured (empty)
            self.testpoints_table.setItem(i, 3, QTableWidgetItem(""))

            # Status
            self.testpoints_table.setItem(i, 4, QTableWidgetItem("Pending"))

        # Select first test point
        self._current_test_index = 0
        self.testpoints_table.selectRow(0)
        self._update_current_display(0)

        self.status_display.append(f"Loaded {len(self._test_points)} test points")
        self.status_display.append("=" * 40)
        self.status_display.append("SESSION STARTED - Ready for first test point")
        self.status_display.append("Enter reading and press Submit, or click 'Get Remote'")

        # Enable control buttons
        self.advance_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)
        self.redo_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)

        # Flash the nominal display to draw attention
        self.nominal_display.setStyleSheet(
            "QLabel { background-color: #2d2d2d; color: #00ff00; "
            "padding: 20px; border-radius: 10px; border: 3px solid #00ff00; }"
        )

        # Focus reading input if keyboard entry is selected
        self._focus_reading_input()

    def _focus_reading_input(self):
        """Focus the reading input box if keyboard entry is selected."""
        if self._session_input_method == "keyboard":
            self.reading_input.setFocus()
            self.reading_input.selectAll()

    def _load_test_points_from_csp(self, csp_file_path: str):
        """Load test points from a .csp file.

        Args:
            csp_file_path: Path to the .csp file
        """
        from pathlib import Path

        try:
            # Load procedure data from CSP
            self._current_csp_data = CSPFile.load(Path(csp_file_path))

            if not self._current_csp_data:
                self.status_display.append("ERROR: Failed to load CSP file")
                QMessageBox.critical(self, "Error", f"Failed to load procedure from:\n{csp_file_path}")
                return

            logger.info(f"Loaded CSP: {self._current_csp_data.name} with {self._current_csp_data.section_count} sections")

            # Convert CSP data to test points list
            section_id = 0  # Use sequential IDs for sections
            for section in self._current_csp_data.sections:
                section_id += 1
                for tp in section.test_points:
                    self._test_points.append({
                        "id": None,  # No database ID for CSP-loaded test points
                        "section_id": section_id,
                        "section_name": section.name,
                        "standard_section_type": section.standard_section_type,
                        "section_command": section.section_command,
                        "section_prompt": section.section_prompt,
                        "section_wiring_type": section.section_wiring_type,
                        "section_wiring_image": section.wiring_image,  # CSP embedded image path
                        "description": tp.description or f"{tp.nominal_value} {tp.unit}",
                        "nominal_value": tp.nominal_value,
                        "unit": tp.unit,
                        "frequency": tp.frequency,
                        "frequency_unit": tp.frequency_unit or "Hz",
                        "tolerance_value": tp.tolerance_value,
                        "tolerance_type": tp.tolerance_type or "PERCENT",
                        "tol_pct_reading": tp.tol_pct_reading,
                        "tol_pct_range": tp.tol_pct_range,
                        "tol_digits": tp.tol_digits,
                        "tol_absolute": tp.tol_absolute,
                        "tol_resolution": tp.tol_resolution,
                        "tol_range_value": tp.tol_range_value,
                        "source_command": tp.source_command,
                        "operate_command": tp.operate_command,
                        "measure_command": tp.measure_command,
                        "test_type": tp.test_type or "measurement",
                        "pass_fail_prompt": tp.pass_fail_prompt,
                        "operator_prompt": tp.operator_prompt,
                        # Pre-conditioning
                        "pre_nominal_value": tp.pre_nominal_value,
                        "pre_unit": tp.pre_unit,
                        "pre_frequency": tp.pre_frequency,
                        "pre_frequency_unit": tp.pre_frequency_unit or "Hz",
                        "pre_delay_seconds": tp.pre_delay_seconds or 0,
                        "pre_conditioning_steps": tp.pre_conditioning_steps or [],
                        # Measurement target
                        "measurement_target": tp.measurement_target or "PRIMARY",
                        "expected_value": tp.expected_value,
                        "expected_unit": tp.expected_unit,
                        # Test point specific wiring diagram
                        "wiring_diagram_type": tp.wiring_diagram_type,
                        # Pass/Fail range check fields
                        "pass_fail_min": tp.pass_fail_min,
                        "pass_fail_max": tp.pass_fail_max,
                        "pass_fail_range_unit": tp.pass_fail_range_unit,
                        "pass_fail_comparison_type": tp.pass_fail_comparison_type,
                        # DMM configuration
                        "dmm_config": tp.dmm_config,
                        # DUT Remote Communication
                        "dut_setup_command": tp.dut_setup_command,
                        "dut_setup_param": tp.dut_setup_param,
                        "dut_pre_check_command": tp.dut_pre_check_command,
                        "dut_pre_check_param": tp.dut_pre_check_param,
                        "dut_pre_check_expected": tp.dut_pre_check_expected,
                        "dut_pre_check_prompt": tp.dut_pre_check_prompt,
                        "dut_pre_check_parser": tp.dut_pre_check_parser,
                        "dut_pre_check_index": tp.dut_pre_check_index,
                        "dut_post_read_command": tp.dut_post_read_command,
                        "dut_post_read_param": tp.dut_post_read_param,
                        "dut_post_read_parser": tp.dut_post_read_parser,
                        "dut_post_read_index": tp.dut_post_read_index,
                    })

            if not self._test_points:
                self.status_display.append("ERROR: CSP file has no test points!")
                QMessageBox.warning(self, "No Test Points", "This procedure has no test points.")
                return

            # Populate table (same as database loading)
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
                    nominal_str += f" @ {tp['frequency']} {tp.get('frequency_unit', 'Hz')}"
                self.testpoints_table.setItem(i, 2, QTableWidgetItem(nominal_str))

                # Measured (empty)
                self.testpoints_table.setItem(i, 3, QTableWidgetItem(""))

                # Status
                self.testpoints_table.setItem(i, 4, QTableWidgetItem("Pending"))

            # Select first test point
            self._current_test_index = 0
            self.testpoints_table.selectRow(0)
            self._update_current_display(0)

            self.status_display.append(f"Loaded {len(self._test_points)} test points from CSP")
            self.status_display.append("=" * 40)
            self.status_display.append("SESSION STARTED - Ready for first test point")
            self.status_display.append("Enter reading and press Submit, or click 'Get Remote'")

            # Enable control buttons
            self.advance_btn.setEnabled(True)
            self.pause_btn.setEnabled(True)
            self.skip_btn.setEnabled(True)
            self.redo_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)

            # Flash the nominal display to draw attention
            self.nominal_display.setStyleSheet(
                "QLabel { background-color: #2d2d2d; color: #00ff00; "
                "padding: 20px; border-radius: 10px; border: 3px solid #00ff00; }"
            )

            # Focus reading input
            self._focus_reading_input()

        except Exception as e:
            logger.error(f"Failed to load test points from CSP: {e}")
            self.status_display.append(f"ERROR loading CSP: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load procedure from CSP:\n{e}")

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
        """Update the current test point display and send calibrator output."""
        self._current_test_index = row

        # Get test point data if available
        if row < len(self._test_points):
            tp = self._test_points[row]
            section_id = tp.get('section_id')

            # Check if we're entering a new section
            section_changed = (section_id != self._current_section_id)

            self.section_label.setText(tp['section_name'])
            self.testpoint_label.setText(tp['description'])
            # Update combined display
            self.section_testpoint_label.setText(f"{tp['section_name']}  /  {tp['description']}")
            self._auto_size_section_label()

            # Format nominal display - show what we're expecting based on measurement_target
            measurement_target = tp.get('measurement_target', 'PRIMARY')
            if measurement_target == 'FREQUENCY':
                # We're measuring frequency
                expected_str = f"{tp.get('frequency', 0)} {tp.get('frequency_unit', 'Hz')}"
                cal_out_str = f"(CAL: {tp['nominal_value']} {tp['unit']})"
                nominal_str = f"{expected_str}\n{cal_out_str}"
            elif measurement_target == 'CUSTOM':
                # Custom expected value
                expected_str = f"{tp.get('expected_value', 0)} {tp.get('expected_unit', '')}"
                cal_out_str = f"(CAL: {tp['nominal_value']} {tp['unit']}"
                if tp.get('frequency'):
                    cal_out_str += f" @ {tp['frequency']} {tp.get('frequency_unit', 'Hz')}"
                cal_out_str += ")"
                nominal_str = f"{expected_str}\n{cal_out_str}"
            else:  # 'primary' - default
                # We're measuring the nominal value
                nominal_str = f"{tp['nominal_value']} {tp['unit']}"
                if tp.get('frequency'):
                    nominal_str += f" @ {tp['frequency']} {tp.get('frequency_unit', 'Hz')}"
            self.nominal_display.setText(nominal_str)

            # Check for high voltage warning (>= 100V)
            self._check_high_voltage(tp['nominal_value'], tp['unit'])

            # Format tolerance using multi-component spec
            from calsystem.utils.tolerance import ToleranceSpec

            spec = ToleranceSpec(
                pct_reading=tp.get('tol_pct_reading') or 0,
                pct_range=tp.get('tol_pct_range') or 0,
                pct_span=tp.get('tol_pct_span') or 0,
                digits=tp.get('tol_digits') or 0,
                absolute=tp.get('tol_absolute') or 0,
                resolution=tp.get('tol_resolution') or 0,
                range_value=tp.get('tol_range_value') or 0,
                span_value=tp.get('tol_span_value') or 0,
            )

            # Fallback to legacy tolerance if no multi-component values set
            if spec.is_empty():
                legacy_tol = tp.get('tolerance_value') or 0
                legacy_type = tp.get('tolerance_type', 'percent')
                spec = ToleranceSpec.from_legacy(legacy_tol, legacy_type)

            # Calculate and display tolerance
            nominal = tp['nominal_value'] or 0
            calculated = spec.calculate(nominal)
            spec_str = spec.format_spec()
            unit = tp.get('unit', '')

            if not spec.is_empty():
                tol_text = f"±{calculated:g} {unit}  ({spec_str})"
                self.tolerance_label.setText(tol_text)
                self.tolerance_display.setText(tol_text)
            else:
                self.tolerance_display.setText("")

            # Load wiring diagram for this section
            self._load_wiring_diagram(
                section_id,
                tp.get('section_name'),
                tp.get('standard_section_type')
            )

            # If section changed, show wiring confirmation before outputting
            if section_changed:
                self._current_section_id = section_id
                self.status_display.append("=" * 40)
                self.status_display.append(f"NEW SECTION: {tp['section_name']}")

                # Execute section command if specified (before wiring dialog)
                # Skip if this test point uses manual setup (shorts, nulls, physical setups)
                section_command = tp.get('section_command')
                if section_command and not tp.get('manual_setup'):
                    self._execute_section_command(section_command)

                # Show section prompt if specified
                section_prompt = tp.get('section_prompt')
                section_wiring_type = tp.get('section_wiring_type')

                if section_prompt or section_wiring_type:
                    # Show section instructions/wiring dialog
                    if not self._confirm_section_instructions(tp, section_prompt, section_wiring_type):
                        self.status_display.append("Waiting for section confirmation...")
                        return
                else:
                    self.status_display.append("Check wiring diagram and confirm connections")
                    # Show wiring confirmation dialog
                    if not self._confirm_wiring(tp):
                        # User cancelled - don't output
                        self.status_display.append("Waiting for wiring confirmation...")
                        return

            # Check for test point-specific instructions (prompt and/or wiring)
            # Skip this for pass_fail tests since the Pass/Fail dialog will show all the info
            test_type = tp.get('test_type', 'measurement')
            tp_wiring_type = tp.get('wiring_diagram_type')
            operator_prompt = tp.get('operator_prompt')

            if (operator_prompt or tp_wiring_type) and test_type != 'pass_fail':
                # Load test point-specific wiring diagram if specified
                if tp_wiring_type:
                    self._load_testpoint_wiring_diagram(tp_wiring_type)
                    self.status_display.append(f"Test point wiring: {tp_wiring_type}")

                # Show instructions/wiring confirmation dialog
                if not self._confirm_testpoint_instructions(tp, operator_prompt, tp_wiring_type):
                    self.status_display.append("Waiting for operator confirmation...")
                    return

            # Check for manual setup (shorts, nulls, physical setups - no calibrator output)
            if tp.get('manual_setup'):
                manual_prompt = tp.get('manual_setup_prompt') or "Perform manual setup as instructed"
                reply = QMessageBox.information(
                    self,
                    "Manual Setup Required",
                    f"{manual_prompt}\n\nClick OK when setup is complete and ready to measure.",
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
                )
                if reply == QMessageBox.StandardButton.Ok:
                    self.status_display.append(f"Manual setup: {manual_prompt}")
                else:
                    self.status_display.append("Manual setup cancelled")
                    return
            else:
                # Send calibrator output command (normal operation)
                self._set_calibrator_output(tp)
        else:
            # Fallback to table data
            section = self.testpoints_table.item(row, 1).text() if self.testpoints_table.item(row, 1) else "--"
            nominal = self.testpoints_table.item(row, 2).text() if self.testpoints_table.item(row, 2) else "--"

            self.section_label.setText(section)
            self.testpoint_label.setText(f"Point {row + 1}")
            self.section_testpoint_label.setText(f"{section}  /  Point {row + 1}")
            self._auto_size_section_label()
            self.nominal_display.setText(nominal)
            self.tolerance_label.setText("No tolerance specified")
            self.tolerance_display.setText("")

            self.status_display.append(f"Manual mode: {nominal}")
            self.wiring_label.setText("No wiring diagram available")

            # Hide high voltage warning in manual mode
            self._hide_hv_warning()

    def _confirm_section_instructions(
        self,
        tp: Dict[str, Any],
        section_prompt: Optional[str],
        section_wiring_type: Optional[str]
    ) -> bool:
        """Show section instructions and/or wiring diagram dialog.

        Args:
            tp: Test point data (contains section info)
            section_prompt: Operator instructions for this section
            section_wiring_type: Wiring diagram type to show

        Returns:
            True if user confirmed, False if cancelled
        """
        section_name = tp.get('section_name', 'Unknown')

        # Load section wiring diagram if specified
        if section_wiring_type:
            self._load_testpoint_wiring_diagram(section_wiring_type)
            self.status_display.append(f"Section wiring diagram: {section_wiring_type}")

        # Build dialog message
        msg = f"Entering section: {section_name}\n\n"

        if section_prompt:
            msg += f"Instructions:\n{section_prompt}\n\n"

        if section_wiring_type:
            msg += f"Wiring diagram type: {section_wiring_type}\n"
            msg += "Please verify connections match the diagram.\n\n"

        msg += "Click 'OK' when ready to proceed.\n"
        msg += "Click 'Cancel' to pause."

        reply = QMessageBox.question(
            self,
            "Section Instructions",
            msg,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok
        )

        if reply == QMessageBox.StandardButton.Ok:
            self.status_display.append("Section confirmed - proceeding")
            self._focus_reading_input()
            return True
        else:
            return False

    def _confirm_wiring(self, tp: Dict[str, Any]) -> bool:
        """Show wiring confirmation dialog for new section."""
        section_name = tp.get('section_name', 'Unknown')
        standard_type = tp.get('standard_section_type', '')

        msg = f"Entering new test section:\n\n"
        msg += f"   Section: {section_name}\n"
        if standard_type:
            msg += f"   Type: {standard_type}\n"
        msg += f"\nPlease verify the wiring connections match the diagram.\n\n"
        msg += "Click 'OK' when ready to begin testing this section.\n"
        msg += "Click 'Cancel' to pause and check wiring."

        reply = QMessageBox.question(
            self,
            "Confirm Wiring",
            msg,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok
        )

        if reply == QMessageBox.StandardButton.Ok:
            self.status_display.append("Wiring confirmed - proceeding with test")
            # Focus reading input for keyboard entry
            self._focus_reading_input()
            return True
        else:
            return False

    def _load_testpoint_wiring_diagram(self, wiring_type: str):
        """Load test point-specific wiring diagram from library."""
        if not wiring_type:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            # Get calibrator model from workstation
            cal_model = ""
            if self._selected_calibrator:
                cal_model = self._selected_calibrator.get('model', '')

            with db.session() as session:
                # Try to find matching diagram in library
                diagram = session.query(WiringDiagramLibrary).filter(
                    WiringDiagramLibrary.section_name == wiring_type
                ).first()

                # If calibrator specific exists, prefer that
                if cal_model:
                    specific = session.query(WiringDiagramLibrary).filter(
                        WiringDiagramLibrary.section_name == wiring_type,
                        WiringDiagramLibrary.calibrator_model.ilike(f"%{cal_model}%")
                    ).first()
                    if specific:
                        diagram = specific

                if diagram and self._display_diagram(diagram):
                    self.status_display.append(f"Loaded wiring diagram: {wiring_type}")
                else:
                    self.wiring_label.setText(f"No diagram found for: {wiring_type}")

        except Exception as e:
            logger.error(f"Failed to load test point wiring diagram: {e}")

    def _confirm_testpoint_wiring(self, tp: Dict[str, Any], wiring_type: str) -> bool:
        """Show wiring confirmation dialog for test point-specific wiring.
        Legacy method - use _confirm_testpoint_instructions for new code.
        """
        return self._confirm_testpoint_instructions(tp, None, wiring_type)

    def _confirm_testpoint_instructions(
        self,
        tp: Dict[str, Any],
        operator_prompt: Optional[str],
        wiring_type: Optional[str]
    ) -> bool:
        """Show operator instructions dialog before executing test point.

        Handles three cases:
        1. Prompt only - show text message
        2. Wiring only - show wiring diagram info
        3. Both - show prompt text + wiring diagram info
        """
        section_name = tp.get('section_name', 'Unknown')
        description = tp.get('description', '')

        # Build dialog message
        if operator_prompt and wiring_type:
            # Both prompt and wiring
            title = "Operator Instructions"
            msg = f"Test Point: {description}\n"
            msg += f"Section: {section_name}\n\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"{operator_prompt}\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            msg += f"Wiring Diagram: {wiring_type}\n"
            msg += "Please verify connections match the diagram.\n\n"
            msg += "Click 'OK' when ready to proceed."
        elif operator_prompt:
            # Prompt only
            title = "Operator Instructions"
            msg = f"Test Point: {description}\n"
            msg += f"Section: {section_name}\n\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"{operator_prompt}\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            msg += "Click 'OK' when ready to proceed."
        else:
            # Wiring only
            title = "Confirm Test Point Wiring"
            msg = f"Test point requires specific wiring:\n\n"
            msg += f"   Section: {section_name}\n"
            msg += f"   Test Point: {description}\n"
            msg += f"   Wiring Type: {wiring_type}\n\n"
            msg += "Please verify the wiring connections match the diagram.\n\n"
            msg += "Click 'OK' when ready to proceed."

        reply = QMessageBox.question(
            self,
            title,
            msg,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok
        )

        if reply == QMessageBox.StandardButton.Ok:
            if operator_prompt:
                self.status_display.append("Operator instructions acknowledged")
            if wiring_type:
                self.status_display.append("Test point wiring confirmed")
            self._focus_reading_input()
            return True
        else:
            return False

    def _set_calibrator_output(self, tp: Dict[str, Any]):
        """Send output command to calibrator for the test point."""
        # Check for manual setup - skip all calibrator output if manual setup is enabled
        if tp.get('manual_setup'):
            manual_prompt = tp.get('manual_setup_prompt') or "Perform manual setup as instructed"
            self.status_display.append(f"Manual Setup: {manual_prompt}")
            self.status_display.append("(No calibrator output - manual setup mode)")
            return

        test_type = tp.get('test_type', 'measurement')

        # DUT Pre-Check: Verify DUT is in expected state FIRST (before setup)
        # This ensures tech sets knob position before we configure range
        if tp.get('dut_pre_check_command') and tp.get('dut_pre_check_expected'):
            if not self._execute_dut_precheck(tp):
                # User cancelled or pre-check failed
                return

        # DUT Setup Command: Send command to configure DUT AFTER pre-check passes
        if tp.get('dut_setup_command'):
            if not self._execute_dut_setup(tp):
                # User cancelled or setup failed
                return

        # For Pass/Fail tests, check if we need to do pre-conditioning first
        if test_type == 'pass_fail':
            # Execute pre-conditioning if defined and we have a calibrator
            if self._selected_calibrator and self._has_preconditioning(tp):
                self._execute_passfail_preconditioning(tp)
            # Then show the Pass/Fail dialog
            self._execute_pass_fail_test(tp)
            return

        # Don't output for DMM-only tests
        if test_type == 'dmm_measurement':
            self.status_display.append("DMM Measurement - no calibrator output needed")
            return

        # Check if we have a calibrator
        if not self._selected_calibrator:
            nominal_str = f"{tp['nominal_value']} {tp['unit']}"
            self.status_display.append(f"No calibrator - set manually: {nominal_str}")
            return

        # Debug: Show calibrator command bank status
        if self._calibrator_commands:
            logger.info(f"Command bank loaded with {len(self._calibrator_commands)} commands")
        else:
            logger.warning("No command bank loaded!")
            self.status_display.append("WARNING: No command bank for this calibrator")

        # Get source command - from test point or command bank
        # Priority: test point specific > OUTPUT_AC (if freq) > OUTPUT > legacy names
        source_cmd = tp.get('source_command')
        logger.info(f"Test point source_command: {source_cmd}")

        if not source_cmd and self._calibrator_commands:
            # Check if this is an AC test (has frequency)
            has_frequency = tp.get('frequency') and float(tp.get('frequency', 0)) > 0

            if has_frequency:
                # Try OUTPUT_AC first for AC tests
                source_cmd = self._get_calibrator_command("OUTPUT_AC")
                if source_cmd:
                    logger.info(f"Using OUTPUT_AC command: {source_cmd}")

            if not source_cmd:
                # Try standard OUTPUT command
                for cmd_name in ["OUTPUT", "OUT", "SOURCE"]:
                    bank_cmd = self._get_calibrator_command(cmd_name)
                    if bank_cmd:
                        source_cmd = bank_cmd
                        logger.info(f"Using {cmd_name} command: {source_cmd}")
                        break

        if not source_cmd:
            nominal_str = f"{tp['nominal_value']} {tp['unit']}"
            self.status_display.append(f"No OUTPUT command - set manually: {nominal_str}")
            self.status_display.append("(Add 'OUTPUT' command to command bank)")
            return

        # Get operate command - use standard name OPERATE
        operate_cmd = tp.get('operate_command')
        if not operate_cmd:
            operate_cmd = self._get_calibrator_command("OPERATE") or self._get_calibrator_command("OPER")

        # Check for pre-conditioning
        if self._has_preconditioning(tp):
            pre_cmd = self._substitute_pre_placeholders(source_cmd, tp)
            delay = tp.get('pre_delay_seconds', 0) or 0

            self.status_display.append(f"Pre-conditioning: {pre_cmd}")
            if not self._send_calibrator_commands(pre_cmd, operate_cmd):
                self.status_display.append("WARNING: Pre-conditioning command failed")
            elif delay > 0:
                self.status_display.append(f"Waiting {delay} seconds...")
                # Process events to keep UI responsive during wait
                from PyQt6.QtWidgets import QApplication
                end_time = time.time() + delay
                while time.time() < end_time:
                    QApplication.processEvents()
                    time.sleep(0.1)

        # Send the actual test point output command
        final_cmd = self._substitute_placeholders(source_cmd, tp)
        self.status_display.append(f"Calibrator: {final_cmd}")

        if self._send_calibrator_commands(final_cmd, operate_cmd):
            self.status_display.append("Output set - ready for reading")

            # Debug: Show current input method
            self.status_display.append(f"[DEBUG] Input method: {self._session_input_method}")
            self.status_display.append(f"[DEBUG] Post-read cmd: {tp.get('dut_post_read_command')}")

            # DUT Post-Read: Automatically capture reading from DUT if configured
            if self._session_input_method == "remote":
                if tp.get('dut_post_read_command'):
                    # Small delay to let DUT settle
                    time.sleep(0.3)
                    self.status_display.append(f"Querying DUT for reading...")
                    dut_reading = self._execute_dut_postread(tp)
                    if dut_reading is not None:
                        # Auto-populate the reading input field
                        self.reading_input.setText(str(dut_reading))
                        self.status_display.append(f"DUT Reading captured: {dut_reading}")
                        # Auto-submit the reading in remote mode
                        QTimer.singleShot(500, self._on_submit_reading)
                    else:
                        self.status_display.append("DUT read failed - enter reading manually")
                        self.reading_input.setFocus()
                else:
                    # Remote mode but no post-read command configured for this test point
                    self.status_display.append("No DUT read command configured - enter reading manually")
                    self.reading_input.setFocus()
        else:
            self.status_display.append("WARNING: Calibrator command failed!")

    def _load_wiring_diagram(
        self,
        section_id: Optional[int],
        section_name: Optional[str],
        standard_section_type: Optional[str] = None
    ):
        """Load and display wiring diagram for the current section.

        Priority:
        0. CSP embedded image (if loaded from .csp file) - HIGHEST PRIORITY
        1. Auto-lookup: calibrator_model + standard_section_type in library
        2. Direct link via SectionDiagramLink (manual linking)
        3. Legacy WiringDiagram entry (direct section link)
        4. Fuzzy match from WiringDiagramLibrary (fallback)
        """
        # 0. Check for CSP embedded image first
        if self._current_csp_data and self._current_test_index >= 0:
            tp = self._test_points[self._current_test_index]

            # Get calibrator model for image lookup
            cal_model = ""
            if self._selected_calibrator:
                cal_model = self._selected_calibrator.get('model', '')

            # Try to find image by calibrator + section type
            section_type = tp.get('standard_section_type') or tp.get('section_name')
            if cal_model and section_type:
                # Look for images/{cal_model}/{cal_model}_{dut}_{section}.png pattern
                for img_path in self._current_csp_data.images.keys():
                    # Check if image path matches calibrator and section
                    if f"/{cal_model}/" in img_path or f"\\{cal_model}\\" in img_path:
                        # Check section type match (case-insensitive, partial match)
                        section_clean = section_type.replace(" ", "_").replace(" ", "")
                        if section_clean.lower() in img_path.lower().replace(" ", "_"):
                            image_data = self._current_csp_data.get_image(img_path)
                            if image_data:
                                logger.debug(f"Using CSP image by calibrator lookup: {img_path}")
                                self._display_diagram_image(image_data)
                                return

            # Fall back to section-specific image
            wiring_image_path = tp.get('section_wiring_image')
            if wiring_image_path:
                image_data = self._current_csp_data.get_image(wiring_image_path)
                if image_data:
                    logger.debug(f"Using CSP embedded image: {wiring_image_path}")
                    self._display_diagram_image(image_data)
                    return
        self.wiring_label.clear()
        self.wiring_label.setText("No wiring diagram available")

        if not section_id:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                cal_model = ""
                if self._selected_calibrator:
                    cal_model = self._selected_calibrator.get('model', '')

                # 1. AUTO-LOOKUP: calibrator_model + standard_section_type (best approach)
                # This requires no manual linking - just match by calibrator and standard type
                if cal_model and standard_section_type:
                    # Get DUT model for more specific matching if available
                    dut_model = ""
                    if self._current_dut_id:
                        from calsystem.database.models import DUT
                        dut = session.query(DUT).filter(DUT.id == self._current_dut_id).first()
                        if dut:
                            dut_model = dut.model or ""

                    # Try exact match: calibrator + section_type + dut_model
                    if dut_model:
                        lib_diagram = session.query(WiringDiagramLibrary).filter(
                            WiringDiagramLibrary.calibrator_model.ilike(cal_model),
                            WiringDiagramLibrary.section_name == standard_section_type,
                            WiringDiagramLibrary.dut_model.ilike(f"%{dut_model}%")
                        ).first()

                        if lib_diagram:
                            logger.debug(f"Auto-lookup found: {lib_diagram.filename} (exact match)")
                            if self._display_diagram(lib_diagram):
                                return

                    # Try calibrator + section_type only (any DUT)
                    lib_diagram = session.query(WiringDiagramLibrary).filter(
                        WiringDiagramLibrary.calibrator_model.ilike(cal_model),
                        WiringDiagramLibrary.section_name == standard_section_type
                    ).first()

                    if lib_diagram:
                        logger.debug(f"Auto-lookup found: {lib_diagram.filename}")
                        if self._display_diagram(lib_diagram):
                            return

                # 2. Check for direct link via SectionDiagramLink (manual linking)
                if cal_model:
                    link = session.query(SectionDiagramLink).filter(
                        SectionDiagramLink.section_id == section_id,
                        SectionDiagramLink.calibrator_model.ilike(f"%{cal_model}%")
                    ).first()

                    if link and link.diagram:
                        logger.debug(f"Using linked diagram: {link.diagram.filename}")
                        if self._display_diagram(link.diagram):
                            return

                # 3. Check for legacy WiringDiagram entry
                diagram = session.query(WiringDiagram).filter(
                    WiringDiagram.section_id == section_id
                ).first()

                if diagram:
                    logger.debug(f"Using legacy diagram: {diagram.name}")
                    if self._display_diagram(diagram):
                        return

                # 4. Fuzzy match from library (fallback)
                if cal_model and section_name:
                    lib_diagram = session.query(WiringDiagramLibrary).filter(
                        WiringDiagramLibrary.calibrator_model.ilike(f"%{cal_model}%"),
                        WiringDiagramLibrary.section_name.ilike(f"%{section_name}%")
                    ).first()

                    if lib_diagram:
                        logger.debug(f"Using fuzzy match diagram: {lib_diagram.filename}")
                        if self._display_diagram(lib_diagram):
                            return

        except Exception as e:
            logger.error(f"Failed to load wiring diagram: {e}")

    def _find_diagram_file(self, diagram) -> str | None:
        """Find the diagram file, checking multiple locations.

        Handles:
        - Direct path (if exists)
        - Bundled resources folder (for distributed exe)
        - User's local diagrams folder
        """
        import sys
        from pathlib import Path

        if not hasattr(diagram, 'image_path') or not diagram.image_path:
            return None

        stored_path = diagram.image_path

        # 1. Try the stored path directly
        if os.path.exists(stored_path):
            return stored_path

        # 2. Try to find in bundled resources or local diagrams folder
        # Extract relative path from stored path (e.g., "87V/5520A/filename.png")
        # Look for patterns like .../diagrams/DUT/CAL/file.png
        path_parts = Path(stored_path).parts
        try:
            diagrams_idx = path_parts.index("diagrams")
            relative_path = os.path.join(*path_parts[diagrams_idx + 1:])
        except (ValueError, IndexError):
            # Couldn't find 'diagrams' in path, try just filename
            relative_path = os.path.basename(stored_path)

        # Check bundled resources folder
        if getattr(sys, 'frozen', False):
            bundled_path = os.path.join(sys._MEIPASS, "resources", "diagrams", relative_path)
            if os.path.exists(bundled_path):
                return bundled_path

        # Check development resources folder
        project_root = Path(__file__).parent.parent.parent.parent.parent
        dev_path = project_root / "resources" / "diagrams" / relative_path
        if dev_path.exists():
            return str(dev_path)

        # Check user's local diagrams folder
        settings = get_settings()
        local_path = settings.diagrams_dir / relative_path
        if local_path.exists():
            return str(local_path)

        logger.warning(f"Diagram file not found: {stored_path} (tried multiple locations)")
        return None

    def _display_diagram(self, diagram) -> bool:
        """Display wiring diagram from a diagram object.

        Tries file path first (new method), falls back to BLOB data (legacy).
        Returns True if successfully displayed, False otherwise.
        """
        from PyQt6.QtGui import QImage

        pixmap = None

        # Try loading from file path first (new method)
        file_path = self._find_diagram_file(diagram)
        if file_path:
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                pixmap = None
                logger.warning(f"Failed to load diagram from path: {file_path}")

        # Fall back to BLOB data (legacy method)
        if pixmap is None and hasattr(diagram, 'image_data') and diagram.image_data:
            image = QImage()
            image.loadFromData(diagram.image_data)
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)

        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                self.wiring_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.wiring_label.setPixmap(scaled)
            return True
        else:
            self.wiring_label.setText("Failed to load diagram image")
            return False

    def _display_diagram_image(self, image_data: bytes):
        """Display wiring diagram image from bytes (legacy method)."""
        from PyQt6.QtGui import QImage

        image = QImage()
        image.loadFromData(image_data)

        if not image.isNull():
            pixmap = QPixmap.fromImage(image)
            scaled = pixmap.scaled(
                self.wiring_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.wiring_label.setPixmap(scaled)
        else:
            self.wiring_label.setText("Failed to load diagram image")

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
        test_type = tp.get('test_type', 'measurement')

        # Determine if we need calibrator output based on test type
        # dmm_measurement: DMM only (no calibrator)
        # calibrator_dmm: Calibrator + DMM
        # measurement: Manual entry or DUT query (calibrator optional)
        use_calibrator = test_type not in ['dmm_measurement']
        use_dmm = test_type in ['dmm_measurement', 'calibrator_dmm'] or self._selected_dmm

        # Get source command - from test point or command bank
        source_cmd = tp.get('source_command')
        if not source_cmd and self._calibrator_commands:
            # Try to get default source command from bank and substitute
            for cmd_name in ["OUT", "SOURCE", "OUTPUT"]:
                bank_cmd = self._get_calibrator_command(cmd_name)
                if bank_cmd:
                    source_cmd = bank_cmd
                    break

        # Get operate command - use standard name OPERATE
        operate_cmd = tp.get('operate_command')
        if not operate_cmd:
            operate_cmd = self._get_calibrator_command("OPERATE") or self._get_calibrator_command("OPER")

        # Send calibrator commands if needed and we have a calibrator
        if use_calibrator and self._selected_calibrator and source_cmd:
            # Check for pre-conditioning
            if self._has_preconditioning(tp):
                pre_cmd = self._substitute_pre_placeholders(source_cmd, tp)
                delay = tp.get('pre_delay_seconds', 0) or 0

                self.status_display.append(f"Pre-conditioning: {pre_cmd}")
                if not self._send_calibrator_commands(pre_cmd, operate_cmd):
                    QMessageBox.warning(
                        self, "Calibrator Error",
                        "Failed to send pre-conditioning command.\n"
                        "Check connection and try again."
                    )
                    return

                if delay > 0:
                    self.status_display.append(f"Waiting {delay} seconds...")
                    # Process events to keep UI responsive during wait
                    from PyQt6.QtWidgets import QApplication
                    end_time = time.time() + delay
                    while time.time() < end_time:
                        QApplication.processEvents()
                        time.sleep(0.1)

            # Now send the actual test command
            source_cmd = self._substitute_placeholders(source_cmd, tp)

            self.status_display.append(f"Setting calibrator: {source_cmd}")

            if not self._send_calibrator_commands(source_cmd, operate_cmd):
                QMessageBox.warning(
                    self, "Calibrator Error",
                    "Failed to send commands to calibrator.\n"
                    "Check connection and try again."
                )
                return
        elif use_calibrator and not self._selected_calibrator:
            self.status_display.append("No calibrator selected - set source manually")
        elif not use_calibrator:
            self.status_display.append("DMM Measurement mode - no calibrator output needed")

        # Check if we need to use the Reference DMM
        if test_type in ['dmm_measurement', 'calibrator_dmm'] and not self._selected_dmm:
            QMessageBox.warning(
                self, "No DMM Selected",
                f"This test point requires a Reference DMM ({test_type}).\n\n"
                "Please select a DMM from the 'Reference DMM' dropdown and click 'Init'."
            )
            return

        # Use DMM if selected or required by test type
        if self._selected_dmm:
            # Determine measurement function from unit
            unit = tp.get('unit', '').lower()
            frequency = tp.get('frequency', 0) or 0

            # Map unit to DMM function
            if 'ohm' in unit:
                dmm_function = "OHM"
            elif frequency > 0 or 'ac' in unit:
                dmm_function = "ACV"
            else:
                dmm_function = "DCV"  # Default to DC Voltage

            self.status_display.append(f"Querying {self._selected_dmm['make']} {self._selected_dmm['model']}: {dmm_function} AUTO")

            # Query the Reference DMM
            reading_base = self._query_dmm(dmm_function)

            if reading_base is not None:
                # Convert from base units to test point's unit
                target_unit = tp.get('unit', 'V')
                reading = self._convert_to_test_unit(reading_base, target_unit)

                self.status_display.append(f"Received: {reading_base} (base units)")
                self.status_display.append(f"Converted: {reading} {target_unit}")
                self.reading_input.setText(str(reading))
                # Auto-submit the reading
                self._on_submit_reading()
                return
            else:
                self.status_display.append("Failed to get reading from DMM")
                self.status_display.append("Enter reading manually or check DMM connection")
                return

        # Fallback: Query DUT directly (if no Reference DMM selected)
        measure_cmd = tp.get('measure_command')
        if not measure_cmd:
            self.status_display.append("No Reference DMM selected and no measure command configured")
            self.status_display.append("Select a Reference DMM or enter reading manually")
            return

        self.status_display.append(f"Querying DUT: {measure_cmd}")

        # Try to get reading via VISA from DUT
        try:
            visa_mgr = get_visa_manager()

            # Get DUT address from database
            db = get_db()
            if db.is_connected and self._current_dut_id:
                with db.session() as session:
                    dut = session.query(DUT).filter(DUT.id == self._current_dut_id).first()
                    if dut and hasattr(dut, 'visa_address') and dut.visa_address:
                        # Query the device
                        success, response = visa_mgr.query(dut.visa_address, measure_cmd)
                        if success and response:
                            # Parse numeric value from response
                            try:
                                value = float(response.strip().split()[0])
                                self.reading_input.setText(str(value))
                                self.status_display.append(f"Received: {value}")
                                # Auto-submit if successful
                                self._on_submit_reading()
                                return
                            except (ValueError, IndexError):
                                self.status_display.append(f"Could not parse: {response}")
                        else:
                            self.status_display.append(f"No response from device: {response}")
                    else:
                        self.status_display.append("DUT has no VISA address configured")

            # Fallback: manual entry
            self.status_display.append("Enter reading manually")

        except Exception as e:
            logger.error(f"Remote reading failed: {e}")
            self.status_display.append(f"Error: {e}")

    def _execute_passfail_preconditioning(self, tp: Dict[str, Any]):
        """Execute pre-conditioning steps for Pass/Fail tests before showing the dialog."""
        from PyQt6.QtWidgets import QApplication

        # Get source command from command bank
        source_cmd = tp.get('source_command')
        if not source_cmd and self._calibrator_commands:
            for cmd_name in ["OUTPUT", "OUT", "SOURCE"]:
                bank_cmd = self._get_calibrator_command(cmd_name)
                if bank_cmd:
                    source_cmd = bank_cmd
                    break

        if not source_cmd:
            self.status_display.append("No OUTPUT command for pre-conditioning")
            return

        # Get operate command
        operate_cmd = tp.get('operate_command')
        if not operate_cmd:
            operate_cmd = self._get_calibrator_command("OPERATE") or self._get_calibrator_command("OPER")

        # Execute single pre-conditioning (existing field)
        if self._has_preconditioning(tp):
            pre_cmd = self._substitute_pre_placeholders(source_cmd, tp)
            delay = tp.get('pre_delay_seconds', 0) or 0

            self.status_display.append(f"Pre-conditioning: {pre_cmd}")
            if self._send_calibrator_commands(pre_cmd, operate_cmd):
                if delay > 0:
                    self.status_display.append(f"Waiting {delay} seconds...")
                    end_time = time.time() + delay
                    while time.time() < end_time:
                        QApplication.processEvents()
                        time.sleep(0.1)
            else:
                self.status_display.append("WARNING: Pre-conditioning command failed")

        # Execute additional pre-conditioning steps if defined (JSON array)
        additional_steps = tp.get('pre_conditioning_steps', [])
        if additional_steps:
            for i, step in enumerate(additional_steps):
                step_value = step.get('value', 0)
                step_unit = step.get('unit', '')
                step_freq = step.get('frequency', 0)
                step_freq_unit = step.get('frequency_unit', 'Hz')
                step_delay = step.get('delay', 0)

                # Build command with step values
                step_cmd = source_cmd
                step_cmd = step_cmd.replace('{value}', str(step_value))
                step_cmd = step_cmd.replace('{unit}', step_unit)
                if step_freq:
                    step_cmd = step_cmd.replace('{frequency}', str(step_freq))
                    step_cmd = step_cmd.replace('{freq_hz}', str(step_freq))
                else:
                    # Remove frequency placeholder if not used
                    step_cmd = step_cmd.replace(',{frequency} {freq_unit}', '')
                    step_cmd = step_cmd.replace(',{frequency} HZ', '')
                    step_cmd = step_cmd.replace(',{freq_hz} HZ', '')

                self.status_display.append(f"Pre-conditioning step {i+2}: {step_cmd}")
                if self._send_calibrator_commands(step_cmd, operate_cmd):
                    if step_delay > 0:
                        self.status_display.append(f"Waiting {step_delay} seconds...")
                        end_time = time.time() + step_delay
                        while time.time() < end_time:
                            QApplication.processEvents()
                            time.sleep(0.1)
                else:
                    self.status_display.append(f"WARNING: Pre-conditioning step {i+2} failed")

        # Now output the main nominal value (if different from pre-conditioning)
        nominal_value = tp.get('nominal_value', 0)
        unit = tp.get('unit', '')
        frequency = tp.get('frequency', 0)

        # Build main output command
        main_cmd = source_cmd
        main_cmd = main_cmd.replace('{value}', str(nominal_value))
        main_cmd = main_cmd.replace('{unit}', unit)
        if frequency:
            main_cmd = main_cmd.replace('{frequency}', str(frequency))
            main_cmd = main_cmd.replace('{freq_hz}', str(frequency))
        else:
            main_cmd = main_cmd.replace(',{frequency} {freq_unit}', '')
            main_cmd = main_cmd.replace(',{frequency} HZ', '')
            main_cmd = main_cmd.replace(',{freq_hz} HZ', '')

        self.status_display.append(f"Setting calibrator: {main_cmd}")
        if not self._send_calibrator_commands(main_cmd, operate_cmd):
            self.status_display.append("WARNING: Main output command failed")

    def _execute_pass_fail_test(self, tp: Dict[str, Any]):
        """Execute a Pass/Fail test with two-step flow:

        Step 1: Show wiring prompt/diagram - tech wires DUT to DMM
        Step 2a (DMM connected): Auto-query DMM, compare to limits, auto-advance if pass
        Step 2b (No DMM): Show manual dialog asking if reading is in range
        """
        prompt = tp.get('pass_fail_prompt') or "Wire the DUT to the DMM as shown."

        # Build test info string - for Pass/Fail, just use section name
        # Don't include test point description as it's often just nominal value (e.g., "0.0V")
        # which isn't relevant for Pass/Fail checks
        test_info = f"{tp.get('section_name', '')}"

        # Get limits and comparison type
        min_val = tp.get('pass_fail_min')
        max_val = tp.get('pass_fail_max')
        comparison_type = tp.get('pass_fail_comparison_type', 'range')  # Default to range for backwards compat
        unit = tp.get('unit', '')
        # For display, prefer pass_fail_range_unit if set (the actual measurement unit)
        display_unit = tp.get('pass_fail_range_unit') or unit
        measured_value = None
        row = self._current_test_index

        # Check if this is a pass/fail with limits (requires DMM reading)
        has_limits = min_val is not None or max_val is not None

        if not has_limits:
            # No limits - simple manual Pass/Fail (no DMM needed)
            self.status_display.append(f"Pass/Fail Test (Manual): {prompt}")
            operator_prompt = tp.get('operator_prompt')
            image_name = tp.get('pass_fail_image')
            dialog = PassFailDialog(prompt, test_info, operator_prompt, image_name, self)
            dialog.exec()
            result = dialog.get_result()

            if result is None:
                self.status_display.append("Test cancelled")
                return

            self._finalize_pass_fail_result(tp, row, result, None)
            return

        # Has limits - need DMM reading
        self.status_display.append(f"Pass/Fail Test: {test_info}")

        # STEP 1: Show wiring prompt
        # Try to get wiring image for this test point
        wiring_image = self._get_pass_fail_wiring_image(tp)

        wiring_prompt = prompt
        if min_val is not None and max_val is not None:
            wiring_prompt += f"\n\nExpected reading: {min_val:.6g} to {max_val:.6g} {unit}"
        elif min_val is not None:
            wiring_prompt += f"\n\nExpected reading: >= {min_val:.6g} {unit}"
        elif max_val is not None:
            wiring_prompt += f"\n\nExpected reading: <= {max_val:.6g} {unit}"

        wiring_dialog = WiringPromptDialog(wiring_prompt, test_info, wiring_image, self)
        if wiring_dialog.exec() != QDialog.DialogCode.Accepted:
            self.status_display.append("Test cancelled")
            return

        self.status_display.append("Wiring confirmed by technician")

        # STEP 2: Check for DMM and take reading
        # First try the selected DMM, then try workstation DMM
        dmm_info = self._selected_dmm
        if not dmm_info or not dmm_info.get("address"):
            dmm_info = self._get_workstation_dmm()

        dmm_connected = False

        if dmm_info and dmm_info.get("address"):
            # Check if DMM is actually responding
            self.status_display.append(f"Checking DMM: {dmm_info.get('make', '')} {dmm_info.get('model', '')}...")
            dmm_connected = self._check_dmm_responding(dmm_info)

        if dmm_connected:
            # AUTOMATED MODE: Read from DMM
            self.status_display.append("DMM connected - taking automated reading...")

            # Get DMM config from test point if available
            dmm_config = tp.get('dmm_config')
            if isinstance(dmm_config, str):
                import json
                try:
                    dmm_config = json.loads(dmm_config)
                except:
                    dmm_config = None

            # Determine DMM function - prefer dmm_config, then pass_fail_range_unit, then unit
            dmm_func = "DCV"  # Default
            if dmm_config and dmm_config.get('func'):
                dmm_func = dmm_config['func']
                self.status_display.append(f"Using configured function: {dmm_func}")
            else:
                # Determine from pass_fail_range_unit first, then unit
                range_unit = tp.get('pass_fail_range_unit', '') or unit or ''
                range_unit_lower = range_unit.lower()
                if 'ohm' in range_unit_lower or range_unit_lower in ['ω', 'kohm', 'mohm']:
                    dmm_func = "OHM"
                elif range_unit_lower in ['vac', 'v ac']:
                    dmm_func = "ACV"

            # Store DMM info temporarily for query
            original_dmm = self._selected_dmm
            self._selected_dmm = dmm_info

            # Use config-aware query if we have dmm_config
            if dmm_config:
                measured_value = self._query_dmm_with_config(dmm_func, dmm_config)
            else:
                measured_value = self._query_dmm(dmm_func)

            self._selected_dmm = original_dmm  # Restore

            if measured_value is not None:
                # Apply reading format multiplier if configured
                raw_value = measured_value
                if dmm_config:
                    reading_format = dmm_config.get('reading_format', 'x1')
                    multiplier = 1.0
                    if reading_format.startswith('x'):
                        try:
                            mult_str = reading_format.split()[0][1:]  # Remove 'x' prefix
                            multiplier = float(mult_str)
                        except:
                            multiplier = 1.0
                    elif reading_format.startswith('/'):
                        try:
                            div_str = reading_format.split()[0][1:]  # Remove '/' prefix
                            multiplier = 1.0 / float(div_str)
                        except:
                            multiplier = 1.0

                    if multiplier != 1.0:
                        measured_value = raw_value * multiplier
                        self.status_display.append(f"DMM Raw: {raw_value:.6g}, Multiplier: {reading_format.split()[0]}")

                self.status_display.append(f"DMM Reading: {measured_value:.6g} {display_unit}")

                # Check if reading passes based on comparison type
                in_range = True
                if comparison_type == 'gt':
                    # Greater Than: measured must be > threshold (stored in min_val)
                    if min_val is not None and measured_value <= min_val:
                        in_range = False
                    self.status_display.append(f"Check: {measured_value:.6g} > {min_val} ? {'Yes' if in_range else 'No'}")
                elif comparison_type == 'lt':
                    # Less Than: measured must be < threshold (stored in max_val)
                    if max_val is not None and measured_value >= max_val:
                        in_range = False
                    self.status_display.append(f"Check: {measured_value:.6g} < {max_val} ? {'Yes' if in_range else 'No'}")
                else:
                    # Range: measured must be between min and max (inclusive)
                    if min_val is not None and measured_value < min_val:
                        in_range = False
                    if max_val is not None and measured_value > max_val:
                        in_range = False

                if in_range:
                    # AUTO-PASS: Reading is within limits
                    self.status_display.append("Reading within limits - AUTO PASS")
                    self._finalize_pass_fail_result(tp, row, True, measured_value)
                    return
                else:
                    # AUTO-FAIL: Reading out of limits - but show dialog to confirm/override
                    self.status_display.append("Reading OUT OF LIMITS - confirm result")
                    dialog = PassFailWithReadingDialog(
                        "Reading is outside limits. Confirm result:",
                        test_info, measured_value, min_val, max_val, display_unit,
                        comparison_type, self
                    )
                    dialog.exec()
                    result = dialog.get_result()
                    if result is None:
                        self.status_display.append("Test cancelled")
                        return
                    self._finalize_pass_fail_result(tp, row, result, measured_value)
                    return
            else:
                self.status_display.append("DMM read failed - switching to manual mode")

        # MANUAL MODE: No DMM or read failed
        self.status_display.append("Manual verification required - check DMM display")
        dialog = ManualReadingDialog(prompt, test_info, min_val, max_val, display_unit, comparison_type, self)
        dialog.exec()
        result = dialog.get_result()

        if result is None:
            self.status_display.append("Test cancelled")
            return

        self._finalize_pass_fail_result(tp, row, result, None)

    def _finalize_pass_fail_result(self, tp: Dict[str, Any], row: int, passed: bool, measured_value: Optional[float]):
        """Finalize and record a pass/fail result, update UI, and advance."""
        if passed:
            self.status_display.append("Result: PASS")
            if measured_value is not None:
                self.reading_input.setText(f"{measured_value:.6g}")
            else:
                self.reading_input.setText("PASS")
            self._record_pass_fail_result(tp, True, measured_value)
            # Update table
            reading_display = f"{measured_value:.6g}" if measured_value is not None else "PASS"
            self.testpoints_table.setItem(row, 3, QTableWidgetItem(reading_display))
            status_item = QTableWidgetItem("Pass")
            status_item.setBackground(QColor(200, 255, 200))
            self.testpoints_table.setItem(row, 4, status_item)
        else:
            self.status_display.append("Result: FAIL")
            if measured_value is not None:
                self.reading_input.setText(f"{measured_value:.6g}")
            else:
                self.reading_input.setText("FAIL")
            self._record_pass_fail_result(tp, False, measured_value)
            # Update table
            reading_display = f"{measured_value:.6g}" if measured_value is not None else "FAIL"
            self.testpoints_table.setItem(row, 3, QTableWidgetItem(reading_display))
            status_item = QTableWidgetItem("Fail")
            status_item.setBackground(QColor(255, 200, 200))
            self.testpoints_table.setItem(row, 4, status_item)

        # Update progress bar
        completed = self.progress_bar.value() + 1
        self.progress_bar.setValue(completed)

        # Advance to next test point
        self._advance_to_next(row)

    def _get_pass_fail_wiring_image(self, tp: Dict[str, Any]) -> Optional[QPixmap]:
        """Get wiring diagram image for a pass/fail test point if available."""
        # Check if test point has a wiring diagram type specified
        wiring_type = tp.get('wiring_diagram_type')
        if not wiring_type:
            return None

        # Try to get from CSP if loaded
        if self._current_csp_data and self._current_csp_data.images:
            # Look for matching image in CSP
            for img_path, img_data in self._current_csp_data.images.items():
                if wiring_type.lower() in img_path.lower():
                    pixmap = QPixmap()
                    pixmap.loadFromData(img_data)
                    if not pixmap.isNull():
                        return pixmap

        return None

    def _record_pass_fail_result(self, tp: Dict[str, Any], passed: bool, measured_value: Optional[float] = None):
        """Record a Pass/Fail test result to the database.

        Args:
            tp: Test point data dictionary
            passed: Whether the test passed
            measured_value: Actual measured value from DMM (if available)
        """
        if not self._current_session_id:
            return

        # CSP-loaded test points don't have database IDs - skip DB recording for those
        test_point_id = tp.get('id')
        if test_point_id is None:
            if measured_value is not None:
                logger.info(f"Pass/Fail result (CSP session, not saved to DB): {'PASS' if passed else 'FAIL'} ({measured_value:.6g})")
            else:
                logger.info(f"Pass/Fail result (CSP session, not saved to DB): {'PASS' if passed else 'FAIL'}")
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            # If we have a measured value from DMM, use it; otherwise use 1/0 for pass/fail
            value_to_record = measured_value if measured_value is not None else (1.0 if passed else 0.0)
            input_method = InputMethod.REMOTE if measured_value is not None else InputMethod.KEYBOARD

            with db.session() as session:
                result = TestResult(
                    session_id=self._current_session_id,
                    test_point_id=test_point_id,
                    measured_value=value_to_record,
                    status=TestStatus.PASS if passed else TestStatus.FAIL,
                    input_method=input_method,
                )
                session.add(result)

            if measured_value is not None:
                logger.info(f"Recorded Pass/Fail result: {'PASS' if passed else 'FAIL'} ({measured_value:.6g}) for test point {test_point_id}")
            else:
                logger.info(f"Recorded Pass/Fail result: {'PASS' if passed else 'FAIL'} for test point {test_point_id}")

        except Exception as e:
            logger.error(f"Failed to record Pass/Fail result: {e}")

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
            # Determine what value to compare against based on measurement_target
            measurement_target = tp.get('measurement_target', 'PRIMARY')
            if measurement_target == 'FREQUENCY':
                # Compare reading to frequency field
                nominal = tp.get('frequency') or 0
            elif measurement_target == 'CUSTOM':
                # Compare reading to custom expected_value
                nominal = tp.get('expected_value') or 0
            else:  # 'primary' or default
                # Compare reading to nominal_value
                nominal = tp['nominal_value'] or 0

            # Use multi-component tolerance if available, fallback to legacy
            from calsystem.utils.tolerance import ToleranceSpec, check_tolerance

            spec = ToleranceSpec(
                pct_reading=tp.get('tol_pct_reading') or 0,
                pct_range=tp.get('tol_pct_range') or 0,
                pct_span=tp.get('tol_pct_span') or 0,
                digits=tp.get('tol_digits') or 0,
                absolute=tp.get('tol_absolute') or 0,
                resolution=tp.get('tol_resolution') or 0,
                range_value=tp.get('tol_range_value') or 0,
                span_value=tp.get('tol_span_value') or 0,
            )

            # Fallback to legacy tolerance if no multi-component values set
            if spec.is_empty():
                legacy_tol = tp.get('tolerance_value') or 0
                legacy_type = tp.get('tolerance_type', 'percent')
                spec = ToleranceSpec.from_legacy(legacy_tol, legacy_type)

            # Calculate pass/fail using the tolerance spec
            passed, deviation, calculated_tolerance = check_tolerance(measured_value, nominal, spec)

            # Store calculated tolerance for reporting
            tp['_calculated_tolerance'] = calculated_tolerance
            tp['_tolerance_spec'] = spec
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
                # Use session input method (set at session start)
                input_method = self._session_input_method

                result = TestResult(
                    session_id=self._current_session_id,
                    test_point_id=tp['id'],
                    measured_value=measured_value,
                    status="pass" if passed else "fail",
                    input_method=input_method,
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
        from calsystem.utils.tolerance import ToleranceSpec

        nominal = tp['nominal_value'] if tp else 0
        unit = tp.get('unit', '') if tp else ''

        # Build tolerance spec
        if tp:
            spec = ToleranceSpec(
                pct_reading=tp.get('tol_pct_reading') or 0,
                pct_range=tp.get('tol_pct_range') or 0,
                pct_span=tp.get('tol_pct_span') or 0,
                digits=tp.get('tol_digits') or 0,
                absolute=tp.get('tol_absolute') or 0,
                resolution=tp.get('tol_resolution') or 0,
                range_value=tp.get('tol_range_value') or 0,
                span_value=tp.get('tol_span_value') or 0,
            )
            if spec.is_empty():
                legacy_tol = tp.get('tolerance_value') or 0
                legacy_type = tp.get('tolerance_type', 'percent')
                spec = ToleranceSpec.from_legacy(legacy_tol, legacy_type)
        else:
            spec = ToleranceSpec()

        calculated_tolerance = spec.calculate(nominal)
        spec_str = spec.format_spec()

        msg = f"Test point {row + 1} failed.\n\n"
        msg += f"Nominal: {nominal} {unit}\n"
        msg += f"Measured: {reading}\n"
        msg += f"Deviation: {deviation:+.6g}\n"
        msg += f"Tolerance: {spec_str} (±{calculated_tolerance:g} {unit})\n\n"
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

        # Hide high voltage warning if active
        self._hide_hv_warning()

        # Put calibrator into standby
        self._safe_shutdown_calibrator()

        # Calculate overall result
        fail_count = 0
        for i in range(self.testpoints_table.rowCount()):
            status_item = self.testpoints_table.item(i, 4)
            if status_item and status_item.text() == "Fail":
                fail_count += 1

        overall_result = "Pass" if fail_count == 0 else "Fail"

        # Update session in database
        self._complete_session(overall_result)

        # Reset session state (but keep test points for preview)
        self._current_session_id = None
        self._current_section_id = None

        # Re-enable UI
        self.start_btn.setText("Start Session")
        self.start_btn.setEnabled(True)
        self.continue_btn.setEnabled(True)
        self.dut_combo.setEnabled(True)
        self.workorder_input.setEnabled(True)
        self.procedure_combo.setEnabled(True)

        # Disable control buttons
        self.advance_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.redo_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

        # Reset display style
        self.nominal_display.setStyleSheet(
            "QLabel { background-color: #2d2d2d; color: #00ff00; "
            "padding: 20px; border-radius: 10px; }"
        )

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
                    cal_session.status = "completed"
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

            # Disconnect DUT serial if connected
            self._disconnect_dut_serial()

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
                            cal_session.status = "paused"
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
                            cal_session.status = "in_progress"
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
            "Terminate Session",
            "Are you sure you want to terminate this session?\n\n"
            "The calibrator will be put into STANDBY mode.\n"
            "Progress will be saved. The session will be marked as aborted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Session stopped/aborted")

            # Hide high voltage warning if active
            self._hide_hv_warning()

            # Put calibrator into standby and reset
            self._safe_shutdown_calibrator()

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
                                cal_session.status = "aborted"
                                cal_session.completed_at = datetime.now()
                    except Exception as e:
                        logger.error(f"Failed to abort session: {e}")

            # Reset session state (but keep test points for preview)
            self._current_session_id = None
            self._current_dut_id = None
            self._current_procedure_id = None
            self._current_section_id = None
            # Keep self._test_points so user can still preview wiring diagrams

            # Re-enable UI
            self.start_btn.setText("Start Session")
            self.start_btn.setEnabled(True)
            self.continue_btn.setEnabled(True)
            self.dut_combo.setEnabled(True)
            self.workorder_input.setEnabled(True)
            self.procedure_combo.setEnabled(True)
            self.pause_btn.setText("Pause")

            # Disable control buttons
            self.advance_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.skip_btn.setEnabled(False)
            self.redo_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)

            # Reset display style
            self.nominal_display.setStyleSheet(
                "QLabel { background-color: #2d2d2d; color: #00ff00; "
                "padding: 20px; border-radius: 10px; }"
            )

            self.status_display.append("Session aborted")

    def _on_advance(self):
        """Manually advance to the next test point without recording a reading."""
        row = self._current_test_index
        if row >= len(self._test_points):
            return

        # Mark current as passed manually (no reading recorded)
        status_item = self.testpoints_table.item(row, 4)
        if status_item and status_item.text() == "Pending":
            status_item.setText("Manual")
            status_item.setBackground(QColor(255, 255, 200))  # Light yellow

        self.status_display.append(f"Advanced past test point {row + 1}")
        self._advance_to_next(row)

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

        if not self._test_points or row >= len(self._test_points):
            logger.debug(f"Redo row {row} but no test points loaded")
            return

        tp = self._test_points[row]
        logger.info(f"Redoing test point {row + 1}: {tp.get('description', '')}")

        # Clear previous result from table
        self.testpoints_table.setItem(row, 3, QTableWidgetItem(""))
        self.testpoints_table.setItem(row, 4, QTableWidgetItem("Redo"))

        # Update current index
        self._current_test_index = row

        self.status_display.append("=" * 40)
        self.status_display.append(f"REDOING TEST POINT {row + 1}")

        # Clear reading input
        self.reading_input.clear()
        self.reading_input.setFocus()

        # Execute the test point (this will show Pass/Fail dialog for pass_fail tests)
        self._update_current_display(row)

    def _on_testpoint_clicked(self, row: int, column: int):
        """Handle single-click on test point - select and prepare for execution."""
        if not self._test_points or row >= len(self._test_points):
            logger.debug(f"Clicked row {row} but no test points loaded")
            return

        # Update selection and current index
        self._current_test_index = row
        logger.info(f"Selected test point {row + 1}: {self._test_points[row].get('description', '')}")
        self.status_display.append(f"Selected test point {row + 1}")

    def _on_testpoint_double_clicked(self, item):
        """Handle double-click on test point - safety-aware jump to test point."""
        row = item.row()

        if not self._test_points or row >= len(self._test_points):
            logger.debug(f"Double-clicked row {row} but no test points loaded")
            return

        tp = self._test_points[row]
        section_id = tp.get('section_id')
        section_name = tp.get('section_name', 'Unknown')
        standard_section_type = tp.get('standard_section_type', '')

        logger.info(f"Double-clicked test point {row + 1}: {tp.get('description', '')}")

        # SAFETY CHECK 1: Not in session - just show wiring diagram, don't execute
        if not self._current_session_id:
            self.status_display.append("=" * 40)
            self.status_display.append(f"PREVIEW: {section_name} / {tp.get('description', '')}")
            self.status_display.append("(Not in session - showing wiring diagram only)")

            # Update display info without executing
            self.section_label.setText(section_name)
            self.testpoint_label.setText(tp.get('description', ''))
            self.section_testpoint_label.setText(f"{section_name}  /  {tp.get('description', '')}")
            self._auto_size_section_label()
            nominal_str = f"{tp.get('nominal_value', 0)} {tp.get('unit', '')}"
            if tp.get('frequency'):
                nominal_str += f" @ {tp['frequency']} {tp.get('frequency_unit', 'Hz')}"
            self.nominal_display.setText(nominal_str)
            self.tolerance_display.setText("")

            # Load and show wiring diagram
            self._load_wiring_diagram(section_id, section_name, standard_section_type)

            # Select the row but don't execute
            self._current_test_index = row
            self.testpoints_table.selectRow(row)
            return

        # SAFETY FIRST: Reset all workstation standards IMMEDIATELY when jumping
        # This prevents shock hazard if calibrator is sourcing high voltage
        # Do this BEFORE any dialogs so the tech is safe while reading/confirming
        self._reset_all_workstation_standards()

        # SAFETY CHECK 2: Different section - show wiring confirmation first
        if section_id != self._current_section_id:
            self.status_display.append("=" * 40)
            self.status_display.append(f"SECTION CHANGE: {section_name}")

            # Load wiring diagram for the new section
            self._load_wiring_diagram(section_id, section_name, standard_section_type)

            # Show confirmation dialog with wiring info
            reply = QMessageBox.question(
                self,
                "Section Change - Verify Wiring",
                f"You are jumping to a different section:\n\n"
                f"Section: {section_name}\n"
                f"Test Point: {tp.get('description', '')}\n"
                f"Nominal: {tp.get('nominal_value', 0)} {tp.get('unit', '')}\n\n"
                f"Please verify the wiring diagram matches your setup.\n\n"
                f"Do you want to proceed and execute this test point?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                self.status_display.append("Jump cancelled - verify wiring before proceeding")
                # Still select the row so they can see the wiring
                self._current_test_index = row
                self.testpoints_table.selectRow(row)
                return

        # SAFE TO EXECUTE: In session and same section (or user confirmed section change)
        logger.info(f"Jumping to test point {row + 1}: {tp.get('description', '')}")

        # Clear previous result for redo
        self.testpoints_table.setItem(row, 3, QTableWidgetItem(""))
        self.testpoints_table.setItem(row, 4, QTableWidgetItem("Redo"))

        # Update current index
        self._current_test_index = row

        self.status_display.append("=" * 40)
        self.status_display.append(f"JUMPING TO TEST POINT {row + 1}")
        self.status_display.append(f"{section_name} / {tp.get('description', '')}")

        # Clear reading input
        self.reading_input.clear()

        # Execute the test point (this will show Pass/Fail dialog for pass_fail tests)
        self._update_current_display(row)

    # -------------------------------------------------------------------------
    # Auto-size Section/Test Point Label
    # -------------------------------------------------------------------------

    def _auto_size_section_label(self):
        """Auto-size the section/testpoint label font based on text length."""
        text = self.section_testpoint_label.text()
        text_len = len(text)

        # Scale font size based on text length
        # Short text (< 25 chars) = 28px (bigger font)
        # Medium text (25-40 chars) = 22px (default)
        # Long text (40-60 chars) = 18px
        # Very long text (> 60 chars) = 14px (minimum)

        if text_len < 25:
            font_size = 28
        elif text_len < 40:
            font_size = 22
        elif text_len < 60:
            font_size = 18
        else:
            font_size = 14

        self.section_testpoint_label.setStyleSheet(
            f"QLabel {{ color: #00ff00; font-size: {font_size}px; font-weight: bold; background: transparent; }}"
        )

    # -------------------------------------------------------------------------
    # High Voltage Warning
    # -------------------------------------------------------------------------

    def _check_high_voltage(self, nominal_value: float, unit: str):
        """Check if voltage is >= 100V and show/hide warning accordingly."""
        # Convert to volts for comparison
        voltage_in_volts = nominal_value
        unit_lower = unit.lower()

        if 'mv' in unit_lower:
            voltage_in_volts = nominal_value / 1000
        elif 'uv' in unit_lower or 'µv' in unit_lower:
            voltage_in_volts = nominal_value / 1000000
        elif 'kv' in unit_lower:
            voltage_in_volts = nominal_value * 1000

        # Only check voltage units (V, mV, kV, etc.)
        is_voltage = 'v' in unit_lower and 'ohm' not in unit_lower

        if is_voltage and voltage_in_volts >= 100:
            self._show_hv_warning()
        else:
            self._hide_hv_warning()

    def _show_hv_warning(self):
        """Show and start the high voltage warning animation."""
        if self._hv_warning_active:
            return  # Already showing

        self._hv_warning_active = True
        self.hv_warning_label.setVisible(True)

        if self._hv_pixmap:
            self.hv_warning_label.setPixmap(self._hv_pixmap)

        self._hv_opacity_effect.setOpacity(1.0)
        self._start_hv_fade_out()
        logger.info("High voltage warning activated (>= 100V)")

    def _hide_hv_warning(self):
        """Hide and stop the high voltage warning animation."""
        if not self._hv_warning_active:
            return  # Already hidden

        self._hv_warning_active = False
        self._hv_fade_out.stop()
        self._hv_fade_in.stop()
        self._hv_delay_timer.stop()
        self.hv_warning_label.setVisible(False)

    def _start_hv_fade_out(self):
        """Start fading out the warning."""
        if not self._hv_warning_active:
            return

        # Get speed from settings
        settings = get_settings()
        speed = settings.ui.high_voltage_blink_speed_ms
        duration = speed // 2

        self._hv_fade_out.setDuration(duration)
        self._hv_fade_out.setStartValue(1.0)
        self._hv_fade_out.setEndValue(0.2)
        self._hv_fade_out.start()

    def _start_hv_fade_in(self):
        """Start fading in the warning."""
        if not self._hv_warning_active:
            return

        settings = get_settings()
        speed = settings.ui.high_voltage_blink_speed_ms
        duration = speed // 2

        self._hv_fade_in.setDuration(duration)
        self._hv_fade_in.setStartValue(0.2)
        self._hv_fade_in.setEndValue(1.0)
        self._hv_fade_in.start()

    def _start_hv_fade_out_delayed(self):
        """Start fade out after brief pause at full opacity."""
        if not self._hv_warning_active:
            return
        self._hv_delay_timer.start(100)
