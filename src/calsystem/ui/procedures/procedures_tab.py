"""
Procedure builder tab.
"""

import os
import re
import time
from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QApplication,
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
    QTreeWidget,
    QTreeWidgetItem,
    QTextEdit,
    QFormLayout,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QMessageBox,
    QFileDialog,
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QScrollArea,
    QStackedWidget,
    QCheckBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QImage
from loguru import logger

from calsystem.database.connection import get_db
from calsystem.database.models import (
    Procedure, TestSection, TestPoint, CommandBank, ToleranceType, WiringDiagram,
    Standard, WorkstationStandard, WorkstationConfig, DeviceGroupType,
    WiringDiagramLibrary, SectionDiagramLink, STANDARD_SECTION_TYPES, get_all_section_types
)
from calsystem.config.settings import get_settings
from calsystem.procedures import export_procedure_to_csp
from calsystem.ui.dialogs.excel_import_dialog import ExcelImportDialog
from calsystem.ui.dialogs.calibrator_selection_dialog import CalibratorSelectionDialog
from calsystem.instruments.visa_manager import get_visa_manager, PYVISA_AVAILABLE, InstrumentInfo


class SectionEditDialog(QDialog):
    """Dialog for editing section name, standard type, and section command."""

    def __init__(self, name: str = "", standard_type: str = "", section_command: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Section")
        self.setMinimumWidth(450)

        self._name = name
        self._standard_type = standard_type
        self._section_command = section_command

        layout = QVBoxLayout(self)

        # Section name (custom display name)
        form_layout = QFormLayout()

        self.name_input = QLineEdit(name)
        self.name_input.setPlaceholderText("e.g., AC Volts Test")
        form_layout.addRow("Display Name:", self.name_input)

        # Standard type dropdown (built-in + custom types)
        self.type_combo = QComboBox()
        self.type_combo.addItem("-- Select Standard Type --", "")
        for section_type in get_all_section_types():
            self.type_combo.addItem(section_type, section_type)

        # Set current selection if provided
        if standard_type:
            idx = self.type_combo.findData(standard_type)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)

        form_layout.addRow("Standard Type:", self.type_combo)

        # Section command - runs when entering this section
        self.command_input = QLineEdit(section_command)
        self.command_input.setPlaceholderText("e.g., STBY, *RST, or leave blank")
        form_layout.addRow("Section Command:", self.command_input)

        layout.addLayout(form_layout)

        # Help text
        help_label = QLabel(
            "Standard Type: Determines which wiring diagram to show.\n"
            "Section Command: Sent to calibrator when entering this section\n"
            "(e.g., STBY to put in standby, *RST to reset). Runs before wiring diagram."
        )
        help_label.setStyleSheet("color: gray; font-size: 11px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        layout.addSpacing(10)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_accept(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Required", "Please enter a section name.")
            return
        self._name = name
        self._standard_type = self.type_combo.currentData() or ""
        self._section_command = self.command_input.text().strip()
        self.accept()

    def get_values(self) -> tuple:
        """Returns (name, standard_type, section_command)."""
        return self._name, self._standard_type, self._section_command


class WiringDiagramSelectionDialog(QDialog):
    """Dialog for selecting a wiring diagram from the library with calibrator selection."""

    # Common calibrator models for dropdown
    CALIBRATOR_MODELS = [
        "Fluke 5500A", "Fluke 5502A", "Fluke 5502E",
        "Fluke 5520A", "Fluke 5522A", "Fluke 5530A",
        "Fluke 5540A", "Fluke 5550A", "Fluke 5560A",
        "Fluke 5700A", "Fluke 5720A", "Fluke 5730A",
    ]

    def __init__(self, dut_model: str, section_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Link Wiring Diagram to Section")
        self.setMinimumSize(750, 550)

        self._dut_model = dut_model
        self._section_name = section_name
        self._selected: Optional[Dict[str, Any]] = None
        self._selected_calibrator: Optional[str] = None
        self._diagrams: List[Dict[str, Any]] = []

        self._init_ui()
        self._populate_calibrator_combo()

    def _init_ui(self):
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)

        # Info header
        info = QLabel(f"Link wiring diagram for DUT: {self._dut_model}, Section: {self._section_name}")
        info.setStyleSheet("font-weight: bold;")
        layout.addWidget(info)

        # Calibrator selection
        cal_layout = QHBoxLayout()
        cal_layout.addWidget(QLabel("Which calibrator is this diagram for:"))
        self.calibrator_combo = QComboBox()
        self.calibrator_combo.setMinimumWidth(200)
        self.calibrator_combo.currentTextChanged.connect(self._on_calibrator_changed)
        cal_layout.addWidget(self.calibrator_combo)
        cal_layout.addStretch()
        layout.addLayout(cal_layout)

        help_label = QLabel("This creates a direct link: when using this calibrator + this section, show this diagram.")
        help_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(help_label)

        layout.addSpacing(10)

        # Main content
        content_layout = QHBoxLayout()

        # List of diagrams
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        list_layout.addWidget(QLabel("Available Diagrams (filtered by calibrator):"))

        self.diagram_list = QListWidget()
        self.diagram_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.diagram_list.itemDoubleClicked.connect(self._on_double_click)
        list_layout.addWidget(self.diagram_list)

        content_layout.addWidget(list_widget)

        # Preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        preview_layout.addWidget(QLabel("Preview:"))

        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(400, 350)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #f5f5f5; border: 1px solid #ccc;")
        self.preview_label.setText("Select a calibrator, then select a diagram")
        preview_layout.addWidget(self.preview_label)

        content_layout.addWidget(preview_widget)

        layout.addLayout(content_layout)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _populate_calibrator_combo(self):
        """Populate calibrator dropdown with common models."""
        self.calibrator_combo.clear()
        self.calibrator_combo.addItem("-- Select Calibrator --")

        # Add common models
        for model in self.CALIBRATOR_MODELS:
            self.calibrator_combo.addItem(model)

        # Also check database for any calibrators in the library
        db = get_db()
        if db.is_connected:
            try:
                with db.session() as session:
                    existing_models = session.query(WiringDiagramLibrary.calibrator_model).distinct().all()
                    for (model,) in existing_models:
                        if model and self.calibrator_combo.findText(model) == -1:
                            self.calibrator_combo.addItem(model)
            except Exception as e:
                logger.error(f"Failed to load calibrator models: {e}")

    def _on_calibrator_changed(self, text: str):
        """Handle calibrator selection change - reload diagrams."""
        if text.startswith("--"):
            self._selected_calibrator = None
            self.diagram_list.clear()
            self.diagram_list.addItem("Select a calibrator first")
            self.preview_label.setText("Select a calibrator, then select a diagram")
            return

        self._selected_calibrator = text
        self._load_diagrams()

    def _load_diagrams(self):
        """Load diagrams matching the selected calibrator and DUT model."""
        self.diagram_list.clear()
        self._diagrams = []

        if not self._selected_calibrator:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            # Extract just the model number from calibrator (e.g., "Fluke 5550A" -> "5550A")
            cal_model = self._selected_calibrator.split()[-1] if self._selected_calibrator else ""

            with db.session() as session:
                # Find diagrams matching this calibrator model
                diagrams = session.query(WiringDiagramLibrary).filter(
                    WiringDiagramLibrary.calibrator_model.ilike(f"%{cal_model}%")
                ).order_by(
                    WiringDiagramLibrary.dut_model,
                    WiringDiagramLibrary.section_name
                ).all()

                for diag in diagrams:
                    # Build display text
                    item_text = f"{diag.dut_model} - {diag.section_name}"

                    # Highlight if DUT and section match
                    dut_match = self._dut_model.lower() in diag.dut_model.lower()
                    section_match = self._section_name.lower() in diag.section_name.lower()

                    if dut_match and section_match:
                        item_text = f"★ {item_text} (recommended)"
                    elif dut_match:
                        item_text = f"• {item_text} (DUT matches)"

                    item = QListWidgetItem(item_text)
                    item.setData(Qt.ItemDataRole.UserRole, len(self._diagrams))

                    self._diagrams.append({
                        "id": diag.id,
                        "calibrator_model": diag.calibrator_model,
                        "dut_model": diag.dut_model,
                        "section_name": diag.section_name,
                        "filename": diag.filename,
                        "image_path": diag.image_path,
                        "image_data": diag.image_data,
                        "mime_type": diag.mime_type,
                    })

                    self.diagram_list.addItem(item)

                if not diagrams:
                    self.diagram_list.addItem(f"No diagrams found for {self._selected_calibrator}")
                    self.diagram_list.addItem("Add diagrams in the Libraries tab first")

        except Exception as e:
            logger.error(f"Failed to load wiring diagrams: {e}")

    def _on_selection_changed(self):
        """Handle list selection change."""
        current = self.diagram_list.currentItem()
        if not current:
            return

        idx = current.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._diagrams):
            return

        diag = self._diagrams[idx]
        self._selected = diag

        # Show preview - try file path first, fall back to BLOB
        pixmap = None

        # Try loading from file path first (new method)
        if diag.get("image_path") and os.path.exists(diag["image_path"]):
            pixmap = QPixmap(diag["image_path"])
            if pixmap.isNull():
                pixmap = None

        # Fall back to BLOB data (legacy method)
        if pixmap is None and diag.get("image_data"):
            image = QImage()
            image.loadFromData(diag["image_data"])
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)

        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled)
        else:
            self.preview_label.setText("No image data")

    def _on_double_click(self, item):
        """Handle double-click to select and close."""
        self._on_selection_changed()
        if self._selected and self._selected_calibrator:
            self.accept()

    def _on_accept(self):
        """Accept the selection."""
        if not self._selected_calibrator:
            QMessageBox.warning(self, "No Calibrator", "Please select a calibrator first.")
            return
        if not self._selected:
            QMessageBox.warning(self, "No Diagram", "Please select a wiring diagram.")
            return
        self.accept()

    def get_selected(self) -> Optional[Dict[str, Any]]:
        """Get the selected diagram info including calibrator."""
        if self._selected and self._selected_calibrator:
            result = self._selected.copy()
            result['link_calibrator_model'] = self._selected_calibrator
            return result
        return None


class ProceduresTab(QWidget):
    """Tab for building and managing calibration procedures."""

    def __init__(self):
        super().__init__()
        self._current_procedure_id: Optional[int] = None
        # Cached calibrator selection for this session
        self._selected_calibrator: Optional[Dict[str, Any]] = None
        self._selected_calibrator_commands: Optional[Dict[str, str]] = None
        # Cached DMM selection for this session
        self._selected_dmm: Optional[Dict[str, Any]] = None
        self._init_ui()

    def showEvent(self, event):
        """Called when tab becomes visible."""
        super().showEvent(event)
        self._refresh_procedure_list()
        self._load_wiring_diagram_types()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Top toolbar
        toolbar = QHBoxLayout()

        self.new_btn = QPushButton("New Procedure")
        self.new_btn.clicked.connect(self._on_new_procedure)
        toolbar.addWidget(self.new_btn)

        self.import_btn = QPushButton("Import from Excel")
        self.import_btn.clicked.connect(self._on_import_excel)
        toolbar.addWidget(self.import_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._on_save)
        toolbar.addWidget(self.save_btn)

        self.export_csp_btn = QPushButton("Export CSP")
        self.export_csp_btn.clicked.connect(self._on_export_csp)
        self.export_csp_btn.setToolTip("Export procedure to .csp file")
        toolbar.addWidget(self.export_csp_btn)

        toolbar.addStretch()

        self.duplicate_btn = QPushButton("Duplicate")
        self.duplicate_btn.clicked.connect(self._on_duplicate)
        toolbar.addWidget(self.duplicate_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._on_delete)
        toolbar.addWidget(self.delete_btn)

        layout.addLayout(toolbar)

        # Main splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left - Procedure list
        list_group = QGroupBox("Procedures")
        list_layout = QVBoxLayout(list_group)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search procedures...")
        search_layout.addWidget(self.search_input)
        list_layout.addLayout(search_layout)

        self.procedure_list = QTableWidget()
        self.procedure_list.setColumnCount(3)
        self.procedure_list.setHorizontalHeaderLabels(["Name", "Target Model", "Version"])
        self.procedure_list.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.procedure_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.procedure_list.itemSelectionChanged.connect(self._on_procedure_selected)
        list_layout.addWidget(self.procedure_list)

        main_splitter.addWidget(list_group)

        # Center - Procedure structure
        structure_group = QGroupBox("Procedure Structure")
        structure_layout = QVBoxLayout(structure_group)

        # Procedure info
        info_layout = QFormLayout()
        self.name_input = QLineEdit()
        info_layout.addRow("Name:", self.name_input)

        target_layout = QHBoxLayout()
        self.target_make_input = QLineEdit()
        self.target_make_input.setPlaceholderText("Make")
        target_layout.addWidget(self.target_make_input)
        self.target_model_input = QLineEdit()
        self.target_model_input.setPlaceholderText("Model")
        target_layout.addWidget(self.target_model_input)
        info_layout.addRow("Target:", target_layout)

        structure_layout.addLayout(info_layout)

        # Section/Test point tree
        tree_toolbar = QHBoxLayout()
        self.add_section_btn = QPushButton("Add Section")
        self.add_section_btn.clicked.connect(self._on_add_section)
        tree_toolbar.addWidget(self.add_section_btn)

        self.add_testpoint_btn = QPushButton("Add Test Point")
        self.add_testpoint_btn.clicked.connect(self._on_add_testpoint)
        tree_toolbar.addWidget(self.add_testpoint_btn)

        self.edit_section_btn = QPushButton("Edit Section")
        self.edit_section_btn.clicked.connect(self._on_edit_section)
        tree_toolbar.addWidget(self.edit_section_btn)

        tree_toolbar.addStretch()

        self.move_up_btn = QPushButton("Move Up")
        self.move_up_btn.clicked.connect(self._on_move_up)
        tree_toolbar.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("Move Down")
        self.move_down_btn.clicked.connect(self._on_move_down)
        tree_toolbar.addWidget(self.move_down_btn)

        self.remove_item_btn = QPushButton("Remove")
        self.remove_item_btn.clicked.connect(self._on_remove_item)
        tree_toolbar.addWidget(self.remove_item_btn)

        structure_layout.addLayout(tree_toolbar)

        self.structure_tree = QTreeWidget()
        self.structure_tree.setHeaderLabels(["Section / Test Point", "Value", "Tolerance"])
        self.structure_tree.setColumnCount(3)
        self.structure_tree.itemSelectionChanged.connect(self._on_tree_item_selected)
        self.structure_tree.itemChanged.connect(self._on_tree_item_changed)
        structure_layout.addWidget(self.structure_tree)

        main_splitter.addWidget(structure_group)

        # Right - Stacked widget for Section/Test Point details
        self.details_stack = QStackedWidget()

        # Page 0: Section details
        self._create_section_details_panel()

        # Page 1: Test point details with tabbed interface
        details_group = QGroupBox("Test Point Details")
        details_main_layout = QVBoxLayout(details_group)

        # Test Type at the top (controls which tabs are visible)
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Test Type:"))
        self.test_type_combo = QComboBox()
        self.test_type_combo.addItems(["Measurement", "Pass/Fail", "Calculated", "DMM Measurement", "Calibrator + DMM"])
        self.test_type_combo.currentIndexChanged.connect(self._on_test_type_changed)
        type_layout.addWidget(self.test_type_combo)
        type_layout.addStretch()
        details_main_layout.addLayout(type_layout)

        # Tab widget for different sections
        self.details_tabs = QTabWidget()
        self._create_basic_tab()
        self._create_calibrator_tab()
        self._create_dmm_tab()
        self._create_prompt_tab()
        self._create_advanced_tab()
        details_main_layout.addWidget(self.details_tabs)

        # Save button and calibrator controls at bottom
        bottom_layout = QVBoxLayout()
        self.save_tp_btn = QPushButton("Save Test Point")
        self.save_tp_btn.clicked.connect(self._save_current_testpoint)
        bottom_layout.addWidget(self.save_tp_btn)

        # Test output buttons
        test_btn_layout = QHBoxLayout()
        self.test_output_btn = QPushButton("Test Output")
        self.test_output_btn.setToolTip("Send source command to calibrator to verify it works")
        self.test_output_btn.clicked.connect(self._on_test_output)
        test_btn_layout.addWidget(self.test_output_btn)

        self.test_passfail_btn = QPushButton("Test Pass/Fail")
        self.test_passfail_btn.setToolTip("Test the full Pass/Fail flow with pre-conditioning and dialog")
        self.test_passfail_btn.clicked.connect(self._on_test_pass_fail)
        test_btn_layout.addWidget(self.test_passfail_btn)

        self.standby_btn = QPushButton("Standby")
        self.standby_btn.setToolTip("Put calibrator in standby mode")
        self.standby_btn.clicked.connect(self._on_standby)
        test_btn_layout.addWidget(self.standby_btn)

        self.change_cal_btn = QPushButton("Change...")
        self.change_cal_btn.setToolTip("Change selected calibrator")
        self.change_cal_btn.clicked.connect(self._on_change_calibrator)
        test_btn_layout.addWidget(self.change_cal_btn)

        bottom_layout.addLayout(test_btn_layout)
        details_main_layout.addLayout(bottom_layout)

        self.details_stack.addWidget(details_group)  # Index 1: test point details

        main_splitter.addWidget(self.details_stack)

        # Set splitter sizes
        main_splitter.setSizes([250, 350, 300])

        layout.addWidget(main_splitter)

    def _create_section_details_panel(self):
        """Create the section details panel (shown when a section is selected)."""
        section_group = QGroupBox("Section Details")
        section_layout = QVBoxLayout(section_group)

        # Form for section properties
        form_layout = QFormLayout()

        # Section name
        self.section_name_input = QLineEdit()
        self.section_name_input.setPlaceholderText("e.g., AC Voltage Test")
        form_layout.addRow("Section Name:", self.section_name_input)

        # Standard type dropdown (for wiring diagram lookup)
        self.section_type_combo = QComboBox()
        self.section_type_combo.addItem("-- Select Standard Type --", "")
        for section_type in get_all_section_types():
            self.section_type_combo.addItem(section_type, section_type)
        form_layout.addRow("Standard Type:", self.section_type_combo)

        # Wiring diagram type override (optional, uses same types as standard)
        self.section_wiring_combo = QComboBox()
        self.section_wiring_combo.addItem("-- Use Standard Type --", "")
        for section_type in get_all_section_types():
            self.section_wiring_combo.addItem(section_type, section_type)
        form_layout.addRow("Wiring Diagram:", self.section_wiring_combo)

        section_layout.addLayout(form_layout)

        # Section Commands (dropdown + list for multiple commands)
        section_layout.addWidget(QLabel("Section Commands:"))

        cmd_row = QHBoxLayout()
        self.section_cmd_combo = QComboBox()
        self.section_cmd_combo.setMinimumWidth(150)
        self.section_cmd_combo.addItem("-- Select Command --", "")
        cmd_row.addWidget(self.section_cmd_combo)

        self.add_cmd_btn = QPushButton("+")
        self.add_cmd_btn.setFixedWidth(30)
        self.add_cmd_btn.setToolTip("Add command to list")
        self.add_cmd_btn.clicked.connect(self._add_section_command)
        cmd_row.addWidget(self.add_cmd_btn)

        self.refresh_cmd_btn = QPushButton("↻")
        self.refresh_cmd_btn.setFixedWidth(30)
        self.refresh_cmd_btn.setToolTip("Refresh command list from workstation calibrator")
        self.refresh_cmd_btn.clicked.connect(self._load_section_command_refs)
        cmd_row.addWidget(self.refresh_cmd_btn)

        cmd_row.addStretch()
        section_layout.addLayout(cmd_row)

        # List of added commands
        cmd_list_row = QHBoxLayout()
        self.section_cmd_list = QListWidget()
        self.section_cmd_list.setMaximumHeight(80)
        self.section_cmd_list.setToolTip("Commands will run in order when entering this section")
        cmd_list_row.addWidget(self.section_cmd_list)

        self.remove_cmd_btn = QPushButton("−")
        self.remove_cmd_btn.setFixedWidth(30)
        self.remove_cmd_btn.setToolTip("Remove selected command")
        self.remove_cmd_btn.clicked.connect(self._remove_section_command)
        cmd_list_row.addWidget(self.remove_cmd_btn, alignment=Qt.AlignmentFlag.AlignTop)

        section_layout.addLayout(cmd_list_row)

        # Operator prompt (multi-line text)
        section_layout.addWidget(QLabel("Operator Prompt:"))
        self.section_prompt_input = QTextEdit()
        self.section_prompt_input.setPlaceholderText("Instructions shown to technician when entering this section...")
        self.section_prompt_input.setMaximumHeight(100)
        section_layout.addWidget(self.section_prompt_input)

        # Help text
        help_label = QLabel(
            "Standard Type: Categorizes the section for organization.\n"
            "Wiring Diagram: Which diagram to show (defaults to Standard Type).\n"
            "Section Commands: Reference commands from Command Bank (run in order).\n"
            "Operator Prompt: Instructions shown before starting the section."
        )
        help_label.setStyleSheet("color: gray; font-size: 10px;")
        help_label.setWordWrap(True)
        section_layout.addWidget(help_label)

        section_layout.addSpacing(5)

        # Button row
        button_layout = QHBoxLayout()

        # Save button
        self.save_section_btn = QPushButton("Save Section")
        self.save_section_btn.clicked.connect(self._save_current_section)
        button_layout.addWidget(self.save_section_btn)

        # Test Section button
        self.test_section_btn = QPushButton("Test Section")
        self.test_section_btn.setToolTip("Preview section prompt and wiring diagram")
        self.test_section_btn.clicked.connect(self._on_test_section)
        button_layout.addWidget(self.test_section_btn)

        # Send Command checkbox
        self.send_command_checkbox = QCheckBox("Send Command")
        self.send_command_checkbox.setToolTip("Also send the Section Command to calibrator when testing")
        button_layout.addWidget(self.send_command_checkbox)

        section_layout.addLayout(button_layout)

        section_layout.addStretch()

        self.details_stack.addWidget(section_group)  # Index 0: section details
        self._current_section_id = None  # Track which section is being edited

    def _create_basic_tab(self):
        """Create the Basic tab - test type, nominal, tolerance, measurement target."""
        basic_widget = QWidget()
        basic_layout = QFormLayout(basic_widget)

        # Nominal value and unit
        value_layout = QHBoxLayout()
        self.nominal_input = QDoubleSpinBox()
        self.nominal_input.setRange(-999999999, 999999999)
        self.nominal_input.setDecimals(6)
        value_layout.addWidget(self.nominal_input)

        self.unit_combo = QComboBox()
        self.unit_combo.setEditable(True)
        self.unit_combo.addItems(["V", "mV", "µV", "A", "mA", "µA", "Ohm", "kOhm", "MOhm", "Hz", "kHz", "MHz"])
        value_layout.addWidget(self.unit_combo)
        basic_layout.addRow("Nominal:", value_layout)

        # Frequency
        freq_layout = QHBoxLayout()
        self.frequency_input = QDoubleSpinBox()
        self.frequency_input.setRange(0, 999999999)
        self.frequency_input.setDecimals(3)
        freq_layout.addWidget(self.frequency_input)

        self.freq_unit_combo = QComboBox()
        self.freq_unit_combo.addItems(["Hz", "kHz", "MHz"])
        freq_layout.addWidget(self.freq_unit_combo)
        basic_layout.addRow("Frequency:", freq_layout)

        # Tolerance (multi-component specification)
        # Keep legacy inputs hidden for backward compatibility
        self.tolerance_input = QDoubleSpinBox()
        self.tolerance_input.setRange(0, 999999)
        self.tolerance_input.setDecimals(6)
        self.tolerance_input.setVisible(False)
        self.tolerance_type_combo = QComboBox()
        self.tolerance_type_combo.addItems(["%", "Absolute", "PPM"])
        self.tolerance_type_combo.setVisible(False)

        # Multi-component tolerance group
        tol_group = QGroupBox("Tolerance Specification")
        tol_group_layout = QFormLayout(tol_group)
        tol_group_layout.setSpacing(5)

        # % of Reading
        pct_rdg_layout = QHBoxLayout()
        self.tol_pct_reading_input = QDoubleSpinBox()
        self.tol_pct_reading_input.setRange(0, 100)
        self.tol_pct_reading_input.setDecimals(6)
        self.tol_pct_reading_input.setSuffix(" %")
        self.tol_pct_reading_input.setToolTip("Percentage of the reading/nominal value")
        self.tol_pct_reading_input.valueChanged.connect(self._update_tolerance_preview)
        pct_rdg_layout.addWidget(self.tol_pct_reading_input)
        pct_rdg_layout.addWidget(QLabel("of reading"))
        pct_rdg_layout.addStretch()
        tol_group_layout.addRow("% Reading:", pct_rdg_layout)

        # % of Range/Full Scale
        pct_range_layout = QHBoxLayout()
        self.tol_pct_range_input = QDoubleSpinBox()
        self.tol_pct_range_input.setRange(0, 100)
        self.tol_pct_range_input.setDecimals(6)
        self.tol_pct_range_input.setSuffix(" %")
        self.tol_pct_range_input.setToolTip("Percentage of the full scale/range value")
        self.tol_pct_range_input.valueChanged.connect(self._update_tolerance_preview)
        pct_range_layout.addWidget(self.tol_pct_range_input)
        pct_range_layout.addWidget(QLabel("of Range:"))
        self.tol_range_value_input = QDoubleSpinBox()
        self.tol_range_value_input.setRange(0, 999999999)
        self.tol_range_value_input.setDecimals(6)
        self.tol_range_value_input.setToolTip("Full scale/range reference value")
        self.tol_range_value_input.valueChanged.connect(self._update_tolerance_preview)
        pct_range_layout.addWidget(self.tol_range_value_input)
        pct_range_layout.addStretch()
        tol_group_layout.addRow("% Range:", pct_range_layout)

        # % of Span (for 4-20mA and similar)
        pct_span_layout = QHBoxLayout()
        self.tol_pct_span_input = QDoubleSpinBox()
        self.tol_pct_span_input.setRange(0, 100)
        self.tol_pct_span_input.setDecimals(6)
        self.tol_pct_span_input.setSuffix(" %")
        self.tol_pct_span_input.setToolTip("Percentage of the span value (e.g., for 4-20mA, span = 16mA)")
        self.tol_pct_span_input.valueChanged.connect(self._update_tolerance_preview)
        pct_span_layout.addWidget(self.tol_pct_span_input)
        pct_span_layout.addWidget(QLabel("of Span:"))
        self.tol_span_value_input = QDoubleSpinBox()
        self.tol_span_value_input.setRange(0, 999999999)
        self.tol_span_value_input.setDecimals(6)
        self.tol_span_value_input.setToolTip("Span reference value (e.g., 16 for 4-20mA)")
        self.tol_span_value_input.valueChanged.connect(self._update_tolerance_preview)
        pct_span_layout.addWidget(self.tol_span_value_input)
        pct_span_layout.addStretch()
        tol_group_layout.addRow("% Span:", pct_span_layout)

        # Digits (floor)
        digits_layout = QHBoxLayout()
        self.tol_digits_input = QSpinBox()
        self.tol_digits_input.setRange(0, 100)
        self.tol_digits_input.setToolTip("Number of digits for floor value")
        self.tol_digits_input.valueChanged.connect(self._update_tolerance_preview)
        digits_layout.addWidget(self.tol_digits_input)
        digits_layout.addWidget(QLabel("digits @ Decimal Places:"))
        self.tol_decimal_places_input = QSpinBox()
        self.tol_decimal_places_input.setRange(0, 9)
        self.tol_decimal_places_input.setToolTip("Number of decimal places on DUT display (e.g., 3 for 100.000)")
        self.tol_decimal_places_input.valueChanged.connect(self._update_tolerance_preview)
        digits_layout.addWidget(self.tol_decimal_places_input)
        digits_layout.addStretch()
        tol_group_layout.addRow("Digits:", digits_layout)

        # Absolute tolerance
        abs_layout = QHBoxLayout()
        self.tol_absolute_input = QDoubleSpinBox()
        self.tol_absolute_input.setRange(0, 999999999)
        self.tol_absolute_input.setDecimals(9)
        self.tol_absolute_input.setToolTip("Absolute tolerance value in measurement units")
        self.tol_absolute_input.valueChanged.connect(self._update_tolerance_preview)
        abs_layout.addWidget(self.tol_absolute_input)
        self.tol_absolute_unit_label = QLabel("")
        abs_layout.addWidget(self.tol_absolute_unit_label)
        abs_layout.addStretch()
        tol_group_layout.addRow("Absolute:", abs_layout)

        # Tolerance preview/summary
        self.tol_preview_label = QLabel("Tolerance: ±0")
        self.tol_preview_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        tol_group_layout.addRow("Summary:", self.tol_preview_label)

        basic_layout.addRow(tol_group)

        # Measurement target
        basic_layout.addRow(QLabel(""))  # Spacer
        measure_layout = QHBoxLayout()
        self.measurement_target_combo = QComboBox()
        self.measurement_target_combo.addItems(["Primary Value", "Frequency", "Custom"])
        self.measurement_target_combo.setToolTip(
            "Primary Value: Compare reading to nominal value\n"
            "Frequency: Compare reading to frequency field\n"
            "Custom: Compare reading to custom expected value"
        )
        self.measurement_target_combo.currentTextChanged.connect(self._on_measurement_target_changed)
        measure_layout.addWidget(self.measurement_target_combo)

        # Custom expected value (shown when Custom is selected)
        self.expected_value_input = QDoubleSpinBox()
        self.expected_value_input.setRange(-999999999, 999999999)
        self.expected_value_input.setDecimals(6)
        self.expected_value_input.setVisible(False)
        measure_layout.addWidget(self.expected_value_input)

        self.expected_unit_combo = QComboBox()
        self.expected_unit_combo.setEditable(True)
        self.expected_unit_combo.addItems(["V", "mV", "µV", "A", "mA", "µA", "Ohm", "kOhm", "MOhm", "Hz", "kHz", "MHz"])
        self.expected_unit_combo.setVisible(False)
        measure_layout.addWidget(self.expected_unit_combo)

        # Connect signals for tolerance preview updates
        # These inputs affect the tolerance calculation
        self.nominal_input.valueChanged.connect(self._update_tolerance_preview)
        self.unit_combo.currentTextChanged.connect(self._update_tolerance_preview)
        self.frequency_input.valueChanged.connect(self._update_tolerance_preview)
        self.freq_unit_combo.currentTextChanged.connect(self._update_tolerance_preview)
        self.measurement_target_combo.currentTextChanged.connect(self._update_tolerance_preview)
        self.expected_value_input.valueChanged.connect(self._update_tolerance_preview)
        self.expected_unit_combo.currentTextChanged.connect(self._update_tolerance_preview)

        basic_layout.addRow("Measure:", measure_layout)

        measure_help = QLabel("What value should the reading be compared to?")
        measure_help.setStyleSheet("color: gray; font-size: 10px;")
        basic_layout.addRow("", measure_help)

        self.details_tabs.addTab(basic_widget, "Basic")
        self._basic_tab_index = self.details_tabs.count() - 1

    def _create_calibrator_tab(self):
        """Create the Calibrator tab - pre-conditioning, source commands."""
        cal_widget = QWidget()
        cal_layout = QFormLayout(cal_widget)

        # Pre-conditioning section
        pre_label = QLabel("Pre-conditioning (optional):")
        pre_label.setStyleSheet("font-weight: bold;")
        cal_layout.addRow(pre_label)

        pre_value_layout = QHBoxLayout()
        self.pre_nominal_input = QDoubleSpinBox()
        self.pre_nominal_input.setRange(-999999999, 999999999)
        self.pre_nominal_input.setDecimals(6)
        self.pre_nominal_input.setSpecialValueText("")
        pre_value_layout.addWidget(self.pre_nominal_input)

        self.pre_unit_combo = QComboBox()
        self.pre_unit_combo.setEditable(True)
        self.pre_unit_combo.addItems(["V", "mV", "µV", "A", "mA", "µA", "Ohm", "kOhm", "MOhm", "Hz", "kHz", "MHz"])
        pre_value_layout.addWidget(self.pre_unit_combo)
        cal_layout.addRow("Pre Value:", pre_value_layout)

        pre_freq_layout = QHBoxLayout()
        self.pre_frequency_input = QDoubleSpinBox()
        self.pre_frequency_input.setRange(0, 999999999)
        self.pre_frequency_input.setDecimals(3)
        pre_freq_layout.addWidget(self.pre_frequency_input)

        self.pre_freq_unit_combo = QComboBox()
        self.pre_freq_unit_combo.addItems(["Hz", "kHz", "MHz"])
        pre_freq_layout.addWidget(self.pre_freq_unit_combo)
        cal_layout.addRow("Pre Freq:", pre_freq_layout)

        delay_layout = QHBoxLayout()
        self.pre_delay_input = QDoubleSpinBox()
        self.pre_delay_input.setRange(0, 60)
        self.pre_delay_input.setDecimals(1)
        self.pre_delay_input.setSuffix(" sec")
        delay_layout.addWidget(self.pre_delay_input)
        delay_layout.addStretch()
        cal_layout.addRow("Delay:", delay_layout)

        # Additional pre-conditioning steps
        cal_layout.addRow(QLabel(""))  # Spacer
        add_steps_label = QLabel("Additional Pre-conditioning Steps:")
        add_steps_label.setStyleSheet("font-weight: bold;")
        cal_layout.addRow(add_steps_label)

        self.pre_steps_table = QTableWidget()
        self.pre_steps_table.setColumnCount(5)
        self.pre_steps_table.setHorizontalHeaderLabels(["Value", "Unit", "Frequency", "Freq Unit", "Delay (s)"])
        self.pre_steps_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pre_steps_table.setMaximumHeight(120)
        cal_layout.addRow(self.pre_steps_table)

        pre_steps_btn_layout = QHBoxLayout()
        self.add_pre_step_btn = QPushButton("Add Step")
        self.add_pre_step_btn.clicked.connect(self._on_add_pre_step)
        pre_steps_btn_layout.addWidget(self.add_pre_step_btn)
        self.remove_pre_step_btn = QPushButton("Remove Step")
        self.remove_pre_step_btn.clicked.connect(self._on_remove_pre_step)
        pre_steps_btn_layout.addWidget(self.remove_pre_step_btn)
        pre_steps_btn_layout.addStretch()
        cal_layout.addRow("", pre_steps_btn_layout)

        # Commands section
        cal_layout.addRow(QLabel(""))  # Spacer
        cmd_label = QLabel("Commands:")
        cmd_label.setStyleSheet("font-weight: bold;")
        cal_layout.addRow(cmd_label)

        template_layout = QHBoxLayout()
        self.cmd_template_combo = QComboBox()
        self.cmd_template_combo.addItem("-- Select Template --", None)
        self.cmd_template_combo.currentIndexChanged.connect(self._on_template_selected)
        template_layout.addWidget(self.cmd_template_combo)
        self.load_templates_btn = QPushButton("Refresh")
        self.load_templates_btn.clicked.connect(self._load_command_templates)
        template_layout.addWidget(self.load_templates_btn)
        cal_layout.addRow("Template:", template_layout)

        self.source_cmd_input = QLineEdit()
        self.source_cmd_input.setPlaceholderText("e.g., OUT {value}{unit}")
        cal_layout.addRow("Source:", self.source_cmd_input)

        self.operate_cmd_input = QLineEdit()
        self.operate_cmd_input.setPlaceholderText("e.g., OPER")
        cal_layout.addRow("Operate:", self.operate_cmd_input)

        self.measure_cmd_input = QLineEdit()
        self.measure_cmd_input.setPlaceholderText("e.g., MEAS:VOLT:DC?")
        cal_layout.addRow("Measure:", self.measure_cmd_input)

        placeholder_help = QLabel("Placeholders: {value}, {unit}, {frequency}, {freq_unit}, {freq_hz}")
        placeholder_help.setStyleSheet("color: gray; font-size: 10px;")
        cal_layout.addRow("", placeholder_help)

        self.details_tabs.addTab(cal_widget, "Calibrator")
        self._calibrator_tab_index = self.details_tabs.count() - 1

    # DMM Range options by function
    DMM_RANGES = {
        "DCV": ["AUTO", "0.1", "1", "10", "100", "1000"],
        "ACV": ["AUTO", "0.1", "1", "10", "100", "1000"],
        "OHM": ["AUTO", "10", "100", "1K", "10K", "100K", "1M", "10M", "100M", "1G"],
        "OHMF": ["AUTO", "10", "100", "1K", "10K", "100K", "1M", "10M", "100M", "1G"],
        "DCI": ["AUTO", "100uA", "1mA", "10mA", "100mA", "1A"],
        "ACI": ["AUTO", "100uA", "1mA", "10mA", "100mA", "1A"],
        "FREQ": ["AUTO"],
        "PER": ["AUTO"],
    }

    # Available optional DMM settings with their value options
    DMM_OPTIONAL_SETTINGS = {
        "NPLC": {
            "description": "Number of Power Line Cycles (integration time)",
            "values": ["0.0001", "0.001", "0.01", "0.1", "1", "10", "100"],
            "default": "10"
        },
        "NDIG": {
            "description": "Number of digits (resolution)",
            "values": ["4", "5", "6", "7", "8"],
            "default": "7"
        },
        "AZERO": {
            "description": "Auto-zero mode",
            "values": ["ON", "OFF", "ONCE"],
            "default": "ON"
        },
        "SETACV": {
            "description": "AC voltage settling (ANA=Analog, SYNC=Synchronous, RNDM=Random)",
            "values": ["ANA", "SYNC", "RNDM"],
            "default": "ANA"
        },
        "LFILTER": {
            "description": "Analog low-pass filter",
            "values": ["OFF", "ON"],
            "default": "OFF"
        },
        "OFORMAT": {
            "description": "Output format",
            "values": ["ASCII", "SINT", "DINT", "SREAL", "DREAL"],
            "default": "ASCII"
        },
        "TARM": {
            "description": "Trigger arm event",
            "values": ["AUTO", "EXT", "SGL", "HOLD", "SYN"],
            "default": "AUTO"
        },
        "TRIG": {
            "description": "Trigger event",
            "values": ["AUTO", "EXT", "SGL", "HOLD", "SYN", "LEVEL", "LINE"],
            "default": "AUTO"
        },
        "NRDGS": {
            "description": "Number of readings per trigger",
            "values": ["1", "2", "5", "10", "20", "50", "100"],
            "default": "1"
        },
    }

    def _create_dmm_tab(self):
        """Create the DMM tab - DMM measurement configuration."""
        dmm_widget = QWidget()
        dmm_layout = QVBoxLayout(dmm_widget)

        # Info label
        info_label = QLabel("DMM from workstation will be used at execution time.")
        info_label.setStyleSheet("color: gray; font-style: italic;")
        dmm_layout.addWidget(info_label)

        # === Core Settings Section ===
        core_group = QGroupBox("Core Settings")
        core_layout = QFormLayout(core_group)

        # Function
        self.dmm_func_combo = QComboBox()
        self.dmm_func_combo.addItems(["DCV", "ACV", "OHM", "OHMF", "DCI", "ACI", "FREQ", "PER"])
        self.dmm_func_combo.setToolTip("Measurement function")
        self.dmm_func_combo.currentTextChanged.connect(self._on_dmm_func_changed)
        core_layout.addRow("Function:", self.dmm_func_combo)

        # Range (updates based on function)
        self.dmm_range_combo = QComboBox()
        self.dmm_range_combo.addItems(self.DMM_RANGES["DCV"])
        self.dmm_range_combo.setToolTip("Measurement range (AUTO or specific)")
        core_layout.addRow("Range:", self.dmm_range_combo)

        # Delay
        delay_layout = QHBoxLayout()
        self.dmm_delay_input = QDoubleSpinBox()
        self.dmm_delay_input.setRange(0, 9999)
        self.dmm_delay_input.setDecimals(3)
        self.dmm_delay_input.setSuffix(" sec")
        self.dmm_delay_input.setToolTip("Trigger delay before measurement")
        delay_layout.addWidget(self.dmm_delay_input)
        delay_layout.addStretch()
        core_layout.addRow("Delay:", delay_layout)

        # Reading format (decimal places)
        self.dmm_reading_format_combo = QComboBox()
        self.dmm_reading_format_combo.addItems([
            "Match Test Point",
            "0.0 (1 decimal)",
            "0.00 (2 decimals)",
            "0.000 (3 decimals)",
            "0.0000 (4 decimals)",
            "0.00000 (5 decimals)",
            "0.000000 (6 decimals)",
        ])
        self.dmm_reading_format_combo.setToolTip("How to format the reading display")
        core_layout.addRow("Reading Format:", self.dmm_reading_format_combo)

        dmm_layout.addWidget(core_group)

        # === Optional Settings Section ===
        optional_group = QGroupBox("Optional Settings")
        optional_layout = QVBoxLayout(optional_group)

        optional_help = QLabel("Add only the settings you need. Commands sent in correct order.")
        optional_help.setStyleSheet("color: gray; font-size: 10px;")
        optional_layout.addWidget(optional_help)

        # Optional settings table
        self.dmm_optional_table = QTableWidget()
        self.dmm_optional_table.setColumnCount(3)
        self.dmm_optional_table.setHorizontalHeaderLabels(["Setting", "Value", ""])
        self.dmm_optional_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.dmm_optional_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.dmm_optional_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.dmm_optional_table.setColumnWidth(2, 60)
        self.dmm_optional_table.setMaximumHeight(150)
        optional_layout.addWidget(self.dmm_optional_table)

        # Add Setting button
        add_setting_layout = QHBoxLayout()
        self.dmm_add_setting_btn = QPushButton("Add Setting...")
        self.dmm_add_setting_btn.clicked.connect(self._on_add_dmm_setting)
        add_setting_layout.addWidget(self.dmm_add_setting_btn)
        add_setting_layout.addStretch()
        optional_layout.addLayout(add_setting_layout)

        dmm_layout.addWidget(optional_group)

        # === Custom Commands Section ===
        custom_group = QGroupBox("Custom Commands")
        custom_layout = QVBoxLayout(custom_group)

        custom_help = QLabel("Raw SCPI commands (sent after settings above)")
        custom_help.setStyleSheet("color: gray; font-size: 10px;")
        custom_layout.addWidget(custom_help)

        # Commands table with Order column
        self.dmm_commands_table = QTableWidget()
        self.dmm_commands_table.setColumnCount(3)
        self.dmm_commands_table.setHorizontalHeaderLabels(["Name", "Command", "Order"])
        self.dmm_commands_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.dmm_commands_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.dmm_commands_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.dmm_commands_table.setColumnWidth(2, 80)
        self.dmm_commands_table.setMaximumHeight(100)
        custom_layout.addWidget(self.dmm_commands_table)

        # Add/Remove buttons
        cmd_btn_layout = QHBoxLayout()
        self.dmm_add_cmd_btn = QPushButton("Add")
        self.dmm_add_cmd_btn.clicked.connect(self._on_add_dmm_command)
        cmd_btn_layout.addWidget(self.dmm_add_cmd_btn)

        self.dmm_remove_cmd_btn = QPushButton("Remove")
        self.dmm_remove_cmd_btn.clicked.connect(self._on_remove_dmm_command)
        cmd_btn_layout.addWidget(self.dmm_remove_cmd_btn)

        cmd_btn_layout.addStretch()
        custom_layout.addLayout(cmd_btn_layout)

        dmm_layout.addWidget(custom_group)

        # === Test Section ===
        test_layout = QHBoxLayout()
        self.test_dmm_btn = QPushButton("Test Reading")
        self.test_dmm_btn.setToolTip("Send settings to DMM and take a test reading")
        self.test_dmm_btn.clicked.connect(self._on_test_dmm_reading)
        test_layout.addWidget(self.test_dmm_btn)
        test_layout.addStretch()
        dmm_layout.addLayout(test_layout)

        dmm_layout.addStretch()

        self.details_tabs.addTab(dmm_widget, "DMM")
        self._dmm_tab_index = self.details_tabs.count() - 1

    def _on_dmm_func_changed(self, func: str):
        """Update range options based on selected DMM function."""
        self.dmm_range_combo.clear()
        ranges = self.DMM_RANGES.get(func, ["AUTO"])
        self.dmm_range_combo.addItems(ranges)

    def _on_add_dmm_setting(self):
        """Add an optional DMM setting."""
        # Get list of settings not already added
        existing_settings = set()
        for row in range(self.dmm_optional_table.rowCount()):
            label_item = self.dmm_optional_table.item(row, 0)
            if label_item:
                existing_settings.add(label_item.text())

        available = [s for s in self.DMM_OPTIONAL_SETTINGS.keys() if s not in existing_settings]

        if not available:
            QMessageBox.information(self, "No Settings Available", "All optional settings have been added.")
            return

        # Show selection dialog
        from PyQt6.QtWidgets import QInputDialog
        item, ok = QInputDialog.getItem(
            self, "Add DMM Setting",
            "Select setting to add:",
            available, 0, False
        )

        if ok and item:
            self._add_dmm_setting_row(item)

    def _add_dmm_setting_row(self, setting_name: str, value: str = None):
        """Add a row to the optional settings table."""
        if setting_name not in self.DMM_OPTIONAL_SETTINGS:
            return

        setting_info = self.DMM_OPTIONAL_SETTINGS[setting_name]
        row = self.dmm_optional_table.rowCount()
        self.dmm_optional_table.insertRow(row)

        # Setting name (read-only)
        name_item = QTableWidgetItem(setting_name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        name_item.setToolTip(setting_info["description"])
        self.dmm_optional_table.setItem(row, 0, name_item)

        # Value dropdown
        value_combo = QComboBox()
        value_combo.addItems(setting_info["values"])
        if value and value in setting_info["values"]:
            value_combo.setCurrentText(value)
        else:
            value_combo.setCurrentText(setting_info["default"])
        self.dmm_optional_table.setCellWidget(row, 1, value_combo)

        # Remove button
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda: self._remove_dmm_setting_row(setting_name))
        self.dmm_optional_table.setCellWidget(row, 2, remove_btn)

    def _remove_dmm_setting_row(self, setting_name: str):
        """Remove a row from the optional settings table."""
        for row in range(self.dmm_optional_table.rowCount()):
            item = self.dmm_optional_table.item(row, 0)
            if item and item.text() == setting_name:
                self.dmm_optional_table.removeRow(row)
                break

    def _on_add_dmm_command(self):
        """Add a new row to the custom DMM commands table."""
        row = self.dmm_commands_table.rowCount()
        self.dmm_commands_table.insertRow(row)
        self.dmm_commands_table.setItem(row, 0, QTableWidgetItem(""))
        self.dmm_commands_table.setItem(row, 1, QTableWidgetItem(""))

        # Order dropdown - Before sends before FUNC/RANGE, After sends after
        order_combo = QComboBox()
        order_combo.addItems(["Before", "After"])
        order_combo.setToolTip("Before: sent before FUNC/RANGE (e.g., RESET, END ALWAYS)\nAfter: sent after FUNC/RANGE")
        self.dmm_commands_table.setCellWidget(row, 2, order_combo)

        self.dmm_commands_table.editItem(self.dmm_commands_table.item(row, 0))

    def _on_remove_dmm_command(self):
        """Remove selected row from custom DMM commands table."""
        current_row = self.dmm_commands_table.currentRow()
        if current_row >= 0:
            self.dmm_commands_table.removeRow(current_row)

    def _on_add_pre_step(self):
        """Add a new pre-conditioning step row."""
        row = self.pre_steps_table.rowCount()
        self.pre_steps_table.insertRow(row)

        # Value
        value_item = QTableWidgetItem("0")
        self.pre_steps_table.setItem(row, 0, value_item)

        # Unit combo
        unit_combo = QComboBox()
        unit_combo.setEditable(True)
        unit_combo.addItems(["V", "mV", "µV", "A", "mA", "µA", "Ohm", "kOhm", "MOhm", "Hz", "kHz", "MHz"])
        self.pre_steps_table.setCellWidget(row, 1, unit_combo)

        # Frequency
        freq_item = QTableWidgetItem("0")
        self.pre_steps_table.setItem(row, 2, freq_item)

        # Freq Unit combo
        freq_unit_combo = QComboBox()
        freq_unit_combo.addItems(["Hz", "kHz", "MHz"])
        self.pre_steps_table.setCellWidget(row, 3, freq_unit_combo)

        # Delay
        delay_item = QTableWidgetItem("0")
        self.pre_steps_table.setItem(row, 4, delay_item)

        self.pre_steps_table.editItem(value_item)

    def _on_remove_pre_step(self):
        """Remove selected pre-conditioning step."""
        current_row = self.pre_steps_table.currentRow()
        if current_row >= 0:
            self.pre_steps_table.removeRow(current_row)

    def _load_pre_steps(self, steps: list):
        """Load pre-conditioning steps into the table."""
        self.pre_steps_table.setRowCount(0)
        if not steps:
            return

        for step in steps:
            row = self.pre_steps_table.rowCount()
            self.pre_steps_table.insertRow(row)

            # Value
            self.pre_steps_table.setItem(row, 0, QTableWidgetItem(str(step.get('value', 0))))

            # Unit combo
            unit_combo = QComboBox()
            unit_combo.setEditable(True)
            unit_combo.addItems(["V", "mV", "µV", "A", "mA", "µA", "Ohm", "kOhm", "MOhm", "Hz", "kHz", "MHz"])
            unit_combo.setCurrentText(step.get('unit', 'V'))
            self.pre_steps_table.setCellWidget(row, 1, unit_combo)

            # Frequency
            self.pre_steps_table.setItem(row, 2, QTableWidgetItem(str(step.get('frequency', 0))))

            # Freq Unit combo
            freq_unit_combo = QComboBox()
            freq_unit_combo.addItems(["Hz", "kHz", "MHz"])
            freq_unit_combo.setCurrentText(step.get('frequency_unit', 'Hz'))
            self.pre_steps_table.setCellWidget(row, 3, freq_unit_combo)

            # Delay
            self.pre_steps_table.setItem(row, 4, QTableWidgetItem(str(step.get('delay', 0))))

    def _save_pre_steps(self) -> list:
        """Save pre-conditioning steps from the table."""
        steps = []
        for row in range(self.pre_steps_table.rowCount()):
            value_item = self.pre_steps_table.item(row, 0)
            unit_combo = self.pre_steps_table.cellWidget(row, 1)
            freq_item = self.pre_steps_table.item(row, 2)
            freq_unit_combo = self.pre_steps_table.cellWidget(row, 3)
            delay_item = self.pre_steps_table.item(row, 4)

            try:
                value = float(value_item.text()) if value_item else 0
            except ValueError:
                value = 0

            try:
                frequency = float(freq_item.text()) if freq_item else 0
            except ValueError:
                frequency = 0

            try:
                delay = float(delay_item.text()) if delay_item else 0
            except ValueError:
                delay = 0

            # Only include if value is non-zero
            if value != 0:
                steps.append({
                    'value': value,
                    'unit': unit_combo.currentText() if unit_combo else 'V',
                    'frequency': frequency,
                    'frequency_unit': freq_unit_combo.currentText() if freq_unit_combo else 'Hz',
                    'delay': delay
                })
        return steps

    def _load_dmm_config(self, config: dict):
        """Load DMM configuration dict into form widgets."""
        # Clear existing optional settings
        self.dmm_optional_table.setRowCount(0)
        self.dmm_commands_table.setRowCount(0)

        if not config:
            # Set defaults for core settings only
            self.dmm_func_combo.setCurrentText("DCV")
            self._on_dmm_func_changed("DCV")
            self.dmm_range_combo.setCurrentText("AUTO")
            self.dmm_delay_input.setValue(0)
            return

        # Core settings
        func = config.get("func", "DCV")
        self.dmm_func_combo.setCurrentText(func)
        self._on_dmm_func_changed(func)

        range_val = config.get("range", "AUTO")
        idx = self.dmm_range_combo.findText(range_val)
        if idx >= 0:
            self.dmm_range_combo.setCurrentIndex(idx)
        else:
            self.dmm_range_combo.setCurrentText(range_val)

        self.dmm_delay_input.setValue(float(config.get("delay", 0)))

        # Reading format
        reading_format = config.get("reading_format", "Match Test Point")
        idx = self.dmm_reading_format_combo.findText(reading_format, Qt.MatchFlag.MatchStartsWith)
        if idx >= 0:
            self.dmm_reading_format_combo.setCurrentIndex(idx)
        else:
            self.dmm_reading_format_combo.setCurrentIndex(0)  # Default to "Match Test Point"

        # Optional settings - new format
        optional_settings = config.get("optional_settings", [])
        for setting_item in optional_settings:
            setting_name = setting_item.get("setting", "")
            setting_value = setting_item.get("value", "")
            if setting_name in self.DMM_OPTIONAL_SETTINGS:
                self._add_dmm_setting_row(setting_name, setting_value)

        # Backwards compatibility: migrate old flat format to optional settings
        old_settings_map = {
            "nplc": "NPLC",
            "ndig": "NDIG",
            "azero": "AZERO",
            "setacv": "SETACV",
            "lfilter": "LFILTER",
        }
        for old_key, new_name in old_settings_map.items():
            if old_key in config and "optional_settings" not in config:
                # Only migrate if this is an old-format config
                self._add_dmm_setting_row(new_name, config[old_key])

        # Custom commands
        custom_commands = config.get("custom_commands", [])
        for cmd_item in custom_commands:
            row = self.dmm_commands_table.rowCount()
            self.dmm_commands_table.insertRow(row)
            self.dmm_commands_table.setItem(row, 0, QTableWidgetItem(cmd_item.get("name", "")))
            self.dmm_commands_table.setItem(row, 1, QTableWidgetItem(cmd_item.get("command", "")))

            # Order dropdown
            order_combo = QComboBox()
            order_combo.addItems(["Before", "After"])
            order_combo.setToolTip("Before: sent before FUNC/RANGE\nAfter: sent after FUNC/RANGE")
            order = cmd_item.get("order", "After")
            order_combo.setCurrentText(order)
            self.dmm_commands_table.setCellWidget(row, 2, order_combo)

    def _save_dmm_config(self) -> dict:
        """Collect DMM settings into config dict for saving."""
        # Collect optional settings
        optional_settings = []
        for row in range(self.dmm_optional_table.rowCount()):
            name_item = self.dmm_optional_table.item(row, 0)
            value_widget = self.dmm_optional_table.cellWidget(row, 1)
            if name_item and value_widget and isinstance(value_widget, QComboBox):
                setting_name = name_item.text()
                setting_value = value_widget.currentText()
                optional_settings.append({"setting": setting_name, "value": setting_value})

        # Collect custom commands
        custom_commands = []
        for row in range(self.dmm_commands_table.rowCount()):
            name_item = self.dmm_commands_table.item(row, 0)
            cmd_item = self.dmm_commands_table.item(row, 1)
            order_widget = self.dmm_commands_table.cellWidget(row, 2)
            if name_item and cmd_item:
                name = name_item.text().strip()
                cmd = cmd_item.text().strip()
                order = "After"
                if order_widget and isinstance(order_widget, QComboBox):
                    order = order_widget.currentText()
                if name or cmd:
                    custom_commands.append({"name": name, "command": cmd, "order": order})

        config = {
            "func": self.dmm_func_combo.currentText(),
            "range": self.dmm_range_combo.currentText(),
            "delay": str(self.dmm_delay_input.value()),
            "reading_format": self.dmm_reading_format_combo.currentText(),
            "optional_settings": optional_settings,
            "custom_commands": custom_commands,
        }

        return config

    def _clear_dmm_config(self):
        """Clear DMM configuration form fields."""
        self.dmm_func_combo.setCurrentText("DCV")
        self._on_dmm_func_changed("DCV")
        self.dmm_range_combo.setCurrentText("AUTO")
        self.dmm_delay_input.setValue(0)
        self.dmm_reading_format_combo.setCurrentIndex(0)  # "Match Test Point"
        self.dmm_optional_table.setRowCount(0)
        self.dmm_commands_table.setRowCount(0)

    def _create_prompt_tab(self):
        """Create the Prompt tab for Pass/Fail tests."""
        prompt_widget = QWidget()
        prompt_layout = QVBoxLayout(prompt_widget)

        # Operational Check section - describes WHAT is being tested
        check_group = QGroupBox("Operational Check")
        check_layout = QFormLayout(check_group)

        check_help = QLabel("Describes what is being tested (shown in test point list)")
        check_help.setStyleSheet("color: gray; font-size: 10px;")
        check_layout.addRow(check_help)

        self.operational_check_input = QLineEdit()
        self.operational_check_input.setPlaceholderText(
            "e.g., 'Open Circuit Voltage', 'Loop Power', 'Beeper Test'"
        )
        check_layout.addRow("Check Name:", self.operational_check_input)

        prompt_layout.addWidget(check_group)

        # Technician Prompt section - the question asked to the tech
        prompt_group = QGroupBox("Technician Prompt")
        prompt_grp_layout = QFormLayout(prompt_group)

        prompt_help = QLabel("The question shown to the technician during execution")
        prompt_help.setStyleSheet("color: gray; font-size: 10px;")
        prompt_grp_layout.addRow(prompt_help)

        self.pass_fail_prompt_input = QTextEdit()
        self.pass_fail_prompt_input.setMaximumHeight(80)
        self.pass_fail_prompt_input.setPlaceholderText(
            "Enter the question for the technician...\n"
            "e.g., 'Does the display show 24-26V?'\n"
            "e.g., 'Can you hear the beeper?'"
        )
        prompt_grp_layout.addRow("Prompt:", self.pass_fail_prompt_input)

        prompt_layout.addWidget(prompt_group)

        # Range check section (for DMM value checks)
        range_group = QGroupBox("Range Check (Optional)")
        range_layout = QFormLayout(range_group)

        range_help = QLabel("If using DMM, check if reading falls within min/max range")
        range_help.setStyleSheet("color: gray; font-size: 10px;")
        range_layout.addRow(range_help)

        # Min value
        min_layout = QHBoxLayout()
        self.pass_fail_min_input = QDoubleSpinBox()
        self.pass_fail_min_input.setRange(-999999, 999999)
        self.pass_fail_min_input.setDecimals(6)
        self.pass_fail_min_input.setSpecialValueText("No minimum")
        self.pass_fail_min_input.setValue(self.pass_fail_min_input.minimum())
        min_layout.addWidget(self.pass_fail_min_input)
        min_layout.addStretch()
        range_layout.addRow("Min Value:", min_layout)

        # Max value
        max_layout = QHBoxLayout()
        self.pass_fail_max_input = QDoubleSpinBox()
        self.pass_fail_max_input.setRange(-999999, 999999)
        self.pass_fail_max_input.setDecimals(6)
        self.pass_fail_max_input.setSpecialValueText("No maximum")
        self.pass_fail_max_input.setValue(self.pass_fail_max_input.minimum())
        max_layout.addWidget(self.pass_fail_max_input)
        max_layout.addStretch()
        range_layout.addRow("Max Value:", max_layout)

        # Unit for range
        self.pass_fail_range_unit = QComboBox()
        self.pass_fail_range_unit.addItems(["V", "mV", "uV", "A", "mA", "uA", "Ohm", "kOhm", "MOhm", "Hz", "kHz", "MHz"])
        range_layout.addRow("Unit:", self.pass_fail_range_unit)

        range_example = QLabel("Example: Min=4.9, Max=5.1, Unit=V → Pass if reading is 4.9V to 5.1V")
        range_example.setStyleSheet("color: gray; font-size: 10px;")
        range_layout.addRow(range_example)

        prompt_layout.addWidget(range_group)

        # Preview button
        preview_layout = QHBoxLayout()
        self.preview_passfail_btn = QPushButton("Preview Pass/Fail Dialog")
        self.preview_passfail_btn.setToolTip("See how the Pass/Fail dialog will look to the technician")
        self.preview_passfail_btn.clicked.connect(self._on_preview_passfail)
        preview_layout.addWidget(self.preview_passfail_btn)
        preview_layout.addStretch()
        prompt_layout.addLayout(preview_layout)

        prompt_layout.addStretch()

        self.details_tabs.addTab(prompt_widget, "Prompt")
        self._prompt_tab_index = self.details_tabs.count() - 1

    def _create_advanced_tab(self):
        """Create the Advanced tab - formula, excel, wiring."""
        adv_widget = QWidget()
        adv_layout = QFormLayout(adv_widget)

        # Formula (for calculated test points)
        formula_label = QLabel("Calculated Test Point:")
        formula_label.setStyleSheet("font-weight: bold;")
        adv_layout.addRow(formula_label)

        self.formula_input = QLineEdit()
        self.formula_input.setPlaceholderText("e.g., (TP1 + TP2) / 2")
        adv_layout.addRow("Formula:", self.formula_input)

        formula_help = QLabel("Reference other test points by ID (e.g., TP1, TP2)")
        formula_help.setStyleSheet("color: gray; font-size: 10px;")
        adv_layout.addRow("", formula_help)

        # Excel mapping
        adv_layout.addRow(QLabel(""))  # Spacer
        excel_label = QLabel("Excel Export Mapping:")
        excel_label.setStyleSheet("font-weight: bold;")
        adv_layout.addRow(excel_label)

        self.excel_sheet_input = QLineEdit()
        adv_layout.addRow("Sheet:", self.excel_sheet_input)

        self.excel_cell_input = QLineEdit()
        self.excel_cell_input.setPlaceholderText("e.g., B15")
        adv_layout.addRow("Cell:", self.excel_cell_input)

        # Operator Instructions
        adv_layout.addRow(QLabel(""))  # Spacer
        instructions_label = QLabel("Operator Instructions:")
        instructions_label.setStyleSheet("font-weight: bold;")
        adv_layout.addRow(instructions_label)

        self.operator_prompt_edit = QTextEdit()
        self.operator_prompt_edit.setMaximumHeight(60)
        self.operator_prompt_edit.setPlaceholderText(
            "Instructions for technician (shown before test point)"
        )
        adv_layout.addRow("Prompt:", self.operator_prompt_edit)

        wiring_layout = QHBoxLayout()
        self.wiring_combo = QComboBox()
        self.wiring_combo.setMinimumWidth(150)
        self.wiring_combo.setToolTip("Optional wiring diagram from library")
        wiring_layout.addWidget(self.wiring_combo)

        self.refresh_wiring_btn = QPushButton("Refresh")
        self.refresh_wiring_btn.clicked.connect(self._load_wiring_diagram_types)
        self.refresh_wiring_btn.setMaximumWidth(70)
        wiring_layout.addWidget(self.refresh_wiring_btn)
        wiring_layout.addStretch()
        adv_layout.addRow("Wiring:", wiring_layout)

        self.details_tabs.addTab(adv_widget, "Advanced")

    def _on_test_type_changed(self, index: int):
        """Show/hide tabs based on selected test type."""
        # Tab visibility matrix:
        # MEASUREMENT (0):      Basic, Calibrator, Advanced
        # PASS_FAIL (1):        Calibrator, DMM, Prompt, Advanced
        # CALCULATED (2):       Basic, Advanced
        # DMM_MEASUREMENT (3):  Basic, DMM, Advanced
        # CALIBRATOR_DMM (4):   Basic, Calibrator, DMM, Advanced

        # Default: show Basic, hide Prompt
        self.details_tabs.setTabVisible(self._basic_tab_index, True)
        self.details_tabs.setTabVisible(self._calibrator_tab_index, True)
        self.details_tabs.setTabVisible(self._dmm_tab_index, True)
        self.details_tabs.setTabVisible(self._prompt_tab_index, False)

        if index == 0:  # Measurement
            self.details_tabs.setTabVisible(self._dmm_tab_index, False)
        elif index == 1:  # Pass/Fail
            # Hide Basic, show Calibrator, DMM, Prompt
            self.details_tabs.setTabVisible(self._basic_tab_index, False)
            self.details_tabs.setTabVisible(self._prompt_tab_index, True)
        elif index == 2:  # Calculated
            self.details_tabs.setTabVisible(self._calibrator_tab_index, False)
            self.details_tabs.setTabVisible(self._dmm_tab_index, False)
        elif index == 3:  # DMM Measurement
            self.details_tabs.setTabVisible(self._calibrator_tab_index, False)
        # index == 4 (Calibrator + DMM) shows Basic, Calibrator, DMM, Advanced

    def _on_new_procedure(self):
        """Create new procedure - clears form for new entry."""
        logger.info("Creating new procedure")
        self._current_procedure_id = None
        self.name_input.clear()
        self.target_make_input.clear()
        self.target_model_input.clear()
        self.structure_tree.clear()
        self._clear_test_point_form()
        self.name_input.setFocus()

    def _clear_test_point_form(self):
        """Clear the test point details form."""
        self.test_type_combo.setCurrentIndex(0)
        self._on_test_type_changed(0)  # Reset tab visibility
        self.nominal_input.setValue(0)
        self.unit_combo.setCurrentIndex(0)
        self.frequency_input.setValue(0)
        self.tolerance_input.setValue(0)
        self.pass_fail_prompt_input.clear()
        self.operational_check_input.clear()
        # Pass/Fail range check fields
        self.pass_fail_min_input.setValue(self.pass_fail_min_input.minimum())
        self.pass_fail_max_input.setValue(self.pass_fail_max_input.minimum())
        self.pass_fail_range_unit.setCurrentIndex(0)
        # Pre-conditioning fields
        self.pre_nominal_input.setValue(0)
        self.pre_unit_combo.setCurrentIndex(0)
        self.pre_frequency_input.setValue(0)
        self.pre_freq_unit_combo.setCurrentIndex(0)
        self.pre_delay_input.setValue(0)
        self.pre_steps_table.setRowCount(0)
        # Commands
        self.cmd_template_combo.setCurrentIndex(0)
        self.source_cmd_input.clear()
        self.operate_cmd_input.clear()
        self.measure_cmd_input.clear()
        self.excel_sheet_input.clear()
        self.excel_cell_input.clear()
        # Measurement target
        self.measurement_target_combo.setCurrentIndex(0)
        self.expected_value_input.setValue(0)
        self.expected_unit_combo.setCurrentIndex(0)
        self.expected_value_input.setVisible(False)
        self.expected_unit_combo.setVisible(False)
        # Wiring diagram and operator instructions
        self.wiring_combo.setCurrentIndex(0)
        self.operator_prompt_edit.clear()
        # Formula
        self.formula_input.clear()
        # DMM config
        self._clear_dmm_config()

    def _on_measurement_target_changed(self, text: str):
        """Show/hide custom expected value fields based on measurement target selection."""
        is_custom = (text == "Custom")
        self.expected_value_input.setVisible(is_custom)
        self.expected_unit_combo.setVisible(is_custom)

    def _update_tolerance_preview(self):
        """Update the tolerance preview label with calculated tolerance."""
        from calsystem.utils.tolerance import ToleranceSpec

        # Determine which value to use based on measurement target
        measurement_target = self.measurement_target_combo.currentText()
        if measurement_target == "Frequency":
            reading_value = self.frequency_input.value()
            unit = self.freq_unit_combo.currentText()
        elif measurement_target == "Custom":
            reading_value = self.expected_value_input.value()
            unit = self.expected_unit_combo.currentText()
        else:  # "Primary Value"
            reading_value = self.nominal_input.value()
            unit = self.unit_combo.currentText()

        # Convert decimal places to resolution (e.g., 3 -> 0.001)
        decimal_places = self.tol_decimal_places_input.value()
        resolution = 10 ** (-decimal_places) if decimal_places > 0 else 0

        # Build tolerance spec from inputs
        spec = ToleranceSpec(
            pct_reading=self.tol_pct_reading_input.value(),
            pct_range=self.tol_pct_range_input.value(),
            pct_span=self.tol_pct_span_input.value(),
            digits=self.tol_digits_input.value(),
            absolute=self.tol_absolute_input.value(),
            resolution=resolution,
            range_value=self.tol_range_value_input.value(),
            span_value=self.tol_span_value_input.value(),
        )

        # Update absolute unit label
        self.tol_absolute_unit_label.setText(unit)

        # Format the specification
        spec_str = spec.format_spec()

        # Calculate actual tolerance at current reading value
        if not spec.is_empty():
            calculated = spec.calculate(reading_value)
            preview = f"{spec_str} = ±{calculated:g} {unit}"
        else:
            preview = "No tolerance specified"

        self.tol_preview_label.setText(preview)

    def _load_command_templates(self):
        """Load available command bank templates into dropdown."""
        self.cmd_template_combo.clear()
        self.cmd_template_combo.addItem("-- Select Template --", None)

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                banks = session.query(CommandBank).order_by(
                    CommandBank.make, CommandBank.model
                ).all()

                for bank in banks:
                    label = f"{bank.make} {bank.model}"
                    # Store bank ID and commands dict
                    self.cmd_template_combo.addItem(label, (bank.id, bank.commands))

                logger.debug(f"Loaded {len(banks)} command templates")

        except Exception as e:
            logger.error(f"Failed to load command templates: {e}")

    def _load_wiring_diagram_types(self):
        """Load wiring diagram types from library into dropdown."""
        current_text = self.wiring_combo.currentText()
        self.wiring_combo.clear()
        self.wiring_combo.addItem("None", None)

        # Load all section types (built-in + custom)
        try:
            for section_type in get_all_section_types():
                self.wiring_combo.addItem(section_type, section_type)

            logger.debug(f"Loaded wiring diagram types")

            # Restore selection if possible
            if current_text:
                idx = self.wiring_combo.findText(current_text)
                if idx >= 0:
                    self.wiring_combo.setCurrentIndex(idx)

        except Exception as e:
            logger.error(f"Failed to load wiring diagram types: {e}")

    def _on_template_selected(self, index: int):
        """Apply selected command template to form."""
        if index <= 0:
            return

        data = self.cmd_template_combo.currentData()
        if not data:
            return

        bank_id, commands = data
        if not commands:
            return

        # Map common command names to fields
        # Support various common naming conventions
        source_keys = ["source", "out", "output", "set"]
        operate_keys = ["operate", "oper", "on", "enable"]
        measure_keys = ["measure", "meas", "read", "query", "fetch"]

        commands_lower = {k.lower(): v for k, v in commands.items()}

        for key in source_keys:
            if key in commands_lower:
                self.source_cmd_input.setText(commands_lower[key])
                break

        for key in operate_keys:
            if key in commands_lower:
                self.operate_cmd_input.setText(commands_lower[key])
                break

        for key in measure_keys:
            if key in commands_lower:
                self.measure_cmd_input.setText(commands_lower[key])
                break

        logger.debug(f"Applied command template from bank {bank_id}")

    def _on_import_excel(self):
        """Import procedure from Excel."""
        if not self._current_procedure_id:
            QMessageBox.warning(
                self, "No Procedure",
                "Please save the procedure first before importing test points."
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Procedure from Excel",
            "",
            "Excel Files (*.xlsx *.xls);;All Files (*)",
        )
        if not file_path:
            return

        logger.info(f"Importing from: {file_path}")

        dialog = ExcelImportDialog(file_path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        imported_data = dialog.get_imported_data()
        if not imported_data:
            return

        db = get_db()
        if not db.is_connected:
            QMessageBox.critical(self, "Database Error", "Not connected to database.")
            return

        try:
            with db.session() as session:
                # Group by section
                sections_map: dict = {}

                for row in imported_data:
                    section_name = row.get("section", "Default")

                    if section_name not in sections_map:
                        # Create or get section
                        existing = session.query(TestSection).filter(
                            TestSection.procedure_id == self._current_procedure_id,
                            TestSection.name == section_name
                        ).first()

                        if existing:
                            sections_map[section_name] = existing
                        else:
                            section = TestSection(
                                procedure_id=self._current_procedure_id,
                                name=section_name,
                                order=len(sections_map),
                            )
                            session.add(section)
                            session.flush()
                            sections_map[section_name] = section

                    section = sections_map[section_name]

                    # Get test point count for order
                    tp_count = session.query(TestPoint).filter(
                        TestPoint.section_id == section.id
                    ).count()

                    # Parse tolerance type
                    tol_type_str = row.get("tolerance_type", "percent").lower()
                    if tol_type_str in ("abs", "absolute"):
                        tol_type = ToleranceType.absolute
                    elif tol_type_str in ("ppm",):
                        tol_type = ToleranceType.ppm
                    else:
                        tol_type = ToleranceType.percent

                    # Create test point
                    tp = TestPoint(
                        section_id=section.id,
                        order=tp_count,
                        description=row.get("description", ""),
                        nominal_value=row.get("nominal", 0),
                        unit=row.get("unit", "V"),
                        tolerance_value=row.get("tolerance", 0),
                        tolerance_type=tol_type,
                    )
                    session.add(tp)

            logger.info(f"Imported {len(imported_data)} test points from Excel")
            QMessageBox.information(
                self, "Import Complete",
                f"Imported {len(imported_data)} test points into {len(sections_map)} sections."
            )

            # Reload procedure to show imported data
            self._load_procedure(self._current_procedure_id)

        except Exception as e:
            logger.error(f"Failed to import from Excel: {e}")
            QMessageBox.critical(self, "Import Error", f"Failed to import:\n{e}")

    def _on_save(self):
        """Save current procedure to database."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Procedure name is required.")
            return

        db = get_db()
        if not db.is_connected:
            QMessageBox.critical(self, "Database Error", "Not connected to database.")
            return

        try:
            with db.session() as session:
                if self._current_procedure_id:
                    procedure = session.query(Procedure).filter(
                        Procedure.id == self._current_procedure_id
                    ).first()
                else:
                    procedure = Procedure(name=name)
                    session.add(procedure)

                procedure.name = name
                procedure.target_make = self.target_make_input.text().strip() or None
                procedure.target_model = self.target_model_input.text().strip() or None

                session.flush()
                self._current_procedure_id = procedure.id

            logger.info(f"Saved procedure: {name} (ID: {self._current_procedure_id})")

            # Export to CSP file
            self._export_current_to_csp()

            QMessageBox.information(self, "Saved", f"Procedure '{name}' saved successfully.")
            self._refresh_procedure_list()

        except Exception as e:
            logger.error(f"Failed to save procedure: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

    def _export_current_to_csp(self, show_message: bool = False):
        """Export current procedure to .csp file.

        Args:
            show_message: If True, show success/failure message box
        """
        if not self._current_procedure_id:
            if show_message:
                QMessageBox.warning(self, "Export Error", "No procedure selected to export.")
            return False

        try:
            # Get procedures directory from settings
            settings = get_settings()
            procedures_dir = settings.procedures_dir

            # Export to CSP
            success, message, file_path = export_procedure_to_csp(
                procedure_id=self._current_procedure_id,
                output_dir=procedures_dir,
                include_images=True,
                created_by=settings.technician_name or "Calsystem",
            )

            if success:
                logger.info(f"Exported to CSP: {file_path}")
                if show_message:
                    QMessageBox.information(
                        self,
                        "Export Successful",
                        f"Procedure exported to:\n{file_path}"
                    )
                return True
            else:
                logger.warning(f"CSP export failed: {message}")
                if show_message:
                    QMessageBox.warning(self, "Export Failed", f"Export failed:\n{message}")
                return False

        except Exception as e:
            logger.error(f"Failed to export to CSP: {e}")
            if show_message:
                QMessageBox.critical(self, "Export Error", f"Failed to export:\n{e}")
            return False

    def _on_export_csp(self):
        """Handle explicit Export CSP button click."""
        self._export_current_to_csp(show_message=True)

    def _refresh_procedure_list(self):
        """Refresh the procedure list from database."""
        self.procedure_list.setRowCount(0)

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                procedures = session.query(Procedure).order_by(Procedure.name).all()

                for proc in procedures:
                    row = self.procedure_list.rowCount()
                    self.procedure_list.insertRow(row)

                    name_item = QTableWidgetItem(proc.name)
                    name_item.setData(Qt.ItemDataRole.UserRole, proc.id)
                    self.procedure_list.setItem(row, 0, name_item)

                    target = f"{proc.target_make or ''} {proc.target_model or ''}".strip()
                    self.procedure_list.setItem(row, 1, QTableWidgetItem(target))
                    self.procedure_list.setItem(row, 2, QTableWidgetItem(proc.version or "1.0"))

                logger.debug(f"Loaded {len(procedures)} procedures")

        except Exception as e:
            logger.error(f"Failed to load procedures: {e}")

    def _on_duplicate(self):
        """Duplicate selected procedure."""
        logger.info("Duplicating procedure")
        # TODO: Implement duplicate

    def _on_delete(self):
        """Delete selected procedure."""
        selected = self.procedure_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a procedure to delete.")
            return

        reply = QMessageBox.question(
            self,
            "Delete Procedure",
            "Are you sure you want to delete this procedure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Deleting procedure")
            # TODO: Delete from database

    def _on_procedure_selected(self):
        """Handle procedure selection - loads into builder view."""
        selected = self.procedure_list.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        name_item = self.procedure_list.item(row, 0)
        proc_id = name_item.data(Qt.ItemDataRole.UserRole)

        self._load_procedure(proc_id)

    def _load_procedure(self, proc_id: int):
        """Load a procedure into the builder view."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                procedure = session.query(Procedure).filter(Procedure.id == proc_id).first()
                if not procedure:
                    return

                self._current_procedure_id = proc_id
                self.name_input.setText(procedure.name)
                self.target_make_input.setText(procedure.target_make or "")
                self.target_model_input.setText(procedure.target_model or "")

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

                # Load sections and test points into tree
                # Block signals to prevent itemChanged from firing during programmatic updates
                self.structure_tree.blockSignals(True)
                try:
                    self.structure_tree.clear()
                    for section in procedure.sections:
                        section_item = QTreeWidgetItem(self.structure_tree)

                        # Show standard type if set
                        display_text = section.name
                        if section.standard_section_type:
                            display_text = f"{section.name} [{section.standard_section_type}]"

                        section_item.setText(0, display_text)
                        section_item.setData(0, Qt.ItemDataRole.UserRole, ("section", section.id))

                        for tp in section.test_points:
                            tp_item = QTreeWidgetItem(section_item)

                            # For Pass/Fail, show operational check text; for others show nominal value
                            if tp.test_type and tp.test_type.value == "pass_fail":
                                check_text = tp.operator_prompt or "Pass/Fail Check"
                                tp_item.setText(0, tp.description or check_text)
                                tp_item.setText(1, check_text)
                                tp_item.setText(2, "Pass/Fail")
                            else:
                                # Build nominal string with frequency if present
                                nominal_str = f"{tp.nominal_value or 0} {tp.unit or ''}"
                                if tp.frequency:
                                    nominal_str += f" @ {tp.frequency} {tp.frequency_unit or 'Hz'}"
                                tp_item.setText(0, tp.description or nominal_str)
                                tp_item.setText(1, nominal_str)
                                # Format tolerance using multi-component spec
                                from calsystem.utils.tolerance import ToleranceSpec
                                tol_spec = ToleranceSpec(
                                    pct_reading=tp.tol_pct_reading or 0,
                                    pct_range=tp.tol_pct_range or 0,
                                    pct_span=tp.tol_pct_span or 0,
                                    digits=tp.tol_digits or 0,
                                    absolute=tp.tol_absolute or 0,
                                    resolution=tp.tol_resolution or 0,
                                    range_value=tp.tol_range_value or 0,
                                    span_value=tp.tol_span_value or 0,
                                )
                                if tol_spec.is_empty():
                                    tol_spec = ToleranceSpec.from_legacy(
                                        tp.tolerance_value or 0,
                                        tp.tolerance_type.value if tp.tolerance_type else "percent"
                                    )
                                tp_item.setText(2, tol_spec.format_spec())

                            tp_item.setData(0, Qt.ItemDataRole.UserRole, ("testpoint", tp.id))

                    self.structure_tree.expandAll()
                finally:
                    self.structure_tree.blockSignals(False)
                logger.info(f"Loaded procedure: {procedure.name}")

        except Exception as e:
            logger.error(f"Failed to load procedure: {e}")

    def _on_add_section(self):
        """Add a new section to the current procedure."""
        if not self._current_procedure_id:
            QMessageBox.warning(
                self, "No Procedure", "Please save the procedure first before adding sections."
            )
            return

        # Show section edit dialog
        dialog = SectionEditDialog("New Section", "", self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name, standard_type = dialog.get_values()

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                # Get max order for this procedure
                max_order = session.query(TestSection).filter(
                    TestSection.procedure_id == self._current_procedure_id
                ).count()

                section = TestSection(
                    procedure_id=self._current_procedure_id,
                    name=name,
                    standard_section_type=standard_type or None,
                    order=max_order,
                )
                session.add(section)
                session.flush()

                # Add to tree - show standard type if set
                # Block signals to prevent itemChanged from firing
                self.structure_tree.blockSignals(True)
                try:
                    display_text = name
                    if standard_type:
                        display_text = f"{name} [{standard_type}]"

                    section_item = QTreeWidgetItem(self.structure_tree)
                    section_item.setText(0, display_text)
                    section_item.setData(0, Qt.ItemDataRole.UserRole, ("section", section.id))
                    self.structure_tree.setCurrentItem(section_item)
                finally:
                    self.structure_tree.blockSignals(False)

                logger.debug(f"Added new section: {section.id} ({name}, type={standard_type})")

        except Exception as e:
            logger.error(f"Failed to add section: {e}")

    def _on_edit_section(self):
        """Edit the selected section's name and standard type."""
        current = self.structure_tree.currentItem()
        if not current:
            QMessageBox.warning(self, "No Selection", "Please select a section to edit.")
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        # If test point selected, get parent section
        if data[0] == "testpoint":
            current = current.parent()
            if not current:
                return
            data = current.data(0, Qt.ItemDataRole.UserRole)

        if data[0] != "section":
            QMessageBox.warning(self, "Invalid Selection", "Please select a section.")
            return

        section_id = data[1]

        db = get_db()
        if not db.is_connected:
            return

        try:
            # Load current section data
            with db.session() as session:
                section = session.query(TestSection).filter(TestSection.id == section_id).first()
                if not section:
                    return

                current_name = section.name
                current_type = section.standard_section_type or ""
                current_command = section.section_command or ""

            # Show edit dialog
            dialog = SectionEditDialog(current_name, current_type, current_command, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            name, standard_type, section_command = dialog.get_values()

            # Save changes
            with db.session() as session:
                section = session.query(TestSection).filter(TestSection.id == section_id).first()
                if section:
                    section.name = name
                    section.standard_section_type = standard_type or None
                    section.section_command = section_command or None

            # Update tree display - block signals to prevent itemChanged from firing
            self.structure_tree.blockSignals(True)
            try:
                display_text = name
                if standard_type:
                    display_text = f"{name} [{standard_type}]"
                current.setText(0, display_text)
            finally:
                self.structure_tree.blockSignals(False)

            logger.info(f"Updated section {section_id}: {name} [{standard_type}]")

        except Exception as e:
            logger.error(f"Failed to edit section: {e}")
            QMessageBox.critical(self, "Error", f"Failed to edit section:\n{e}")

    def _on_add_testpoint(self):
        """Add a new test point to the selected section."""
        current = self.structure_tree.currentItem()
        if not current:
            QMessageBox.warning(self, "No Section", "Please select a section first.")
            return

        # Get section item (parent if test point is selected)
        section_item = current if current.parent() is None else current.parent()
        if section_item is None:
            QMessageBox.warning(self, "No Section", "Please select a section first.")
            return

        data = section_item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data[0] != "section":
            QMessageBox.warning(self, "Invalid Selection", "Please select a section.")
            return

        section_id = data[1]

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                # Get max order for this section
                max_order = session.query(TestPoint).filter(
                    TestPoint.section_id == section_id
                ).count()

                tp = TestPoint(
                    section_id=section_id,
                    order=max_order,
                    nominal_value=0,
                    unit="V",
                    tolerance_value=0.1,
                )
                session.add(tp)
                session.flush()

                # Add to tree
                tp_item = QTreeWidgetItem(section_item)
                tp_item.setText(0, "New Test Point")
                tp_item.setText(1, "0 V")
                tp_item.setText(2, "±0.1%")
                tp_item.setData(0, Qt.ItemDataRole.UserRole, ("testpoint", tp.id))
                self.structure_tree.setCurrentItem(tp_item)

                logger.debug(f"Added new test point: {tp.id}")

        except Exception as e:
            logger.error(f"Failed to add test point: {e}")

    def _on_set_wiring_diagram(self):
        """Set wiring diagram for the selected section."""
        current = self.structure_tree.currentItem()
        if not current:
            QMessageBox.warning(self, "No Selection", "Please select a section first.")
            return

        # Get section (if test point selected, get parent section)
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data[0] == "testpoint":
            # Get parent section
            section_item = current.parent()
            if section_item:
                data = section_item.data(0, Qt.ItemDataRole.UserRole)

        if not data or data[0] != "section":
            QMessageBox.warning(self, "No Section", "Please select a section.")
            return

        section_id = data[1]
        section_name = current.text(0) if data[0] == "section" else current.parent().text(0)

        # Get target model from procedure
        target_model = self.target_model_input.text().strip()
        if not target_model:
            QMessageBox.warning(
                self, "No Target Model",
                "Please set the Target Model in Procedure Structure.\n\n"
                "This is used to find matching wiring diagrams."
            )
            return

        # Show wiring diagram selection dialog
        dialog = WiringDiagramSelectionDialog(target_model, section_name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = dialog.get_selected()
            if selected:
                self._link_diagram_to_section(section_id, selected)

    def _link_diagram_to_section(self, section_id: int, diagram_info: dict):
        """Create a direct link between section + calibrator model -> library diagram."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            # Get the calibrator model for the link
            # e.g., "Fluke 5550A" -> "5550A"
            link_calibrator = diagram_info.get('link_calibrator_model', '')
            cal_model = link_calibrator.split()[-1] if link_calibrator else ''

            if not cal_model:
                QMessageBox.warning(self, "No Calibrator", "No calibrator model specified.")
                return

            diagram_id = diagram_info.get('id')
            if not diagram_id:
                QMessageBox.warning(self, "No Diagram", "No diagram ID found.")
                return

            with db.session() as session:
                # Check if a link already exists for this section + calibrator
                existing = session.query(SectionDiagramLink).filter(
                    SectionDiagramLink.section_id == section_id,
                    SectionDiagramLink.calibrator_model == cal_model
                ).first()

                if existing:
                    # Update existing link
                    existing.diagram_id = diagram_id
                    logger.info(f"Updated diagram link for section {section_id} + {cal_model}")
                else:
                    # Create new link
                    link = SectionDiagramLink(
                        section_id=section_id,
                        calibrator_model=cal_model,
                        diagram_id=diagram_id,
                    )
                    session.add(link)
                    logger.info(f"Created diagram link for section {section_id} + {cal_model}")

            QMessageBox.information(
                self, "Diagram Linked",
                f"Wiring diagram linked for:\n\n"
                f"  Section: {section_id}\n"
                f"  Calibrator: {link_calibrator}\n"
                f"  Diagram: {diagram_info.get('filename', 'Unknown')}\n\n"
                "During execution, when using this calibrator with this section,\n"
                "this diagram will be displayed automatically."
            )

        except Exception as e:
            logger.error(f"Failed to link wiring diagram: {e}")
            QMessageBox.critical(self, "Error", f"Failed to link diagram:\n{e}")

    def _on_tree_item_selected(self):
        """Handle tree item selection - loads details into form."""
        current = self.structure_tree.currentItem()
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data

        if item_type == "section":
            self._load_section_details(item_id)
            self.details_stack.setCurrentIndex(0)  # Show section details
        elif item_type == "testpoint":
            self._load_testpoint_details(item_id)
            self.details_stack.setCurrentIndex(1)  # Show test point details

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int):
        """Handle tree item changes - saves section name edits."""
        if column != 0:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        if item_type != "section":
            return

        new_name = item.text(0).strip()
        if not new_name:
            return

        # Strip any [standard_type] suffix from display text
        # Display format is "Section Name [Standard Type]" - we only want "Section Name"
        # Remove all trailing [...] suffixes that may have accumulated
        new_name = re.sub(r'\s*\[[^\]]+\]\s*$', '', new_name).strip()
        # Keep removing in case multiple suffixes accumulated
        while re.search(r'\s*\[[^\]]+\]\s*$', new_name):
            new_name = re.sub(r'\s*\[[^\]]+\]\s*$', '', new_name).strip()

        if not new_name:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                section = session.query(TestSection).filter(TestSection.id == item_id).first()
                if section:
                    section.name = new_name
                    logger.debug(f"Updated section name: {new_name}")
        except Exception as e:
            logger.error(f"Failed to update section name: {e}")

    def _load_section_details(self, section_id: int):
        """Load section details into the section form."""
        self._current_section_id = section_id

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                section = session.query(TestSection).filter(TestSection.id == section_id).first()
                if not section:
                    return

                # Populate fields
                self.section_name_input.setText(section.name or "")

                # Set standard type combo
                standard_type = section.standard_section_type or ""
                idx = self.section_type_combo.findData(standard_type)
                if idx >= 0:
                    self.section_type_combo.setCurrentIndex(idx)
                else:
                    self.section_type_combo.setCurrentIndex(0)

                # Set wiring diagram type combo
                wiring_type = section.section_wiring_type or ""
                idx = self.section_wiring_combo.findData(wiring_type)
                if idx >= 0:
                    self.section_wiring_combo.setCurrentIndex(idx)
                else:
                    self.section_wiring_combo.setCurrentIndex(0)

                # Set section commands (load from JSON)
                self._load_section_command_refs()  # Refresh dropdown
                self._set_section_commands_from_json(section.section_command)

                # Set operator prompt
                self.section_prompt_input.setPlainText(section.section_prompt or "")

        except Exception as e:
            logger.error(f"Failed to load section details: {e}")

    def _load_section_command_refs(self):
        """Load command references from active workstation calibrator's command bank."""
        self.section_cmd_combo.clear()
        self.section_cmd_combo.addItem("-- Select Command --", "")

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                # Get ACTIVE workstation calibrators
                from calsystem.database.models import Standard, CommandBank, DeviceGroupType, WorkstationStandard
                calibrators = session.query(Standard).join(
                    WorkstationStandard, WorkstationStandard.standard_id == Standard.id
                ).filter(
                    WorkstationStandard.is_active == True,
                    Standard.device_group == DeviceGroupType.CALIBRATOR
                ).all()

                commands_found = set()
                for cal in calibrators:
                    # Get command bank for this calibrator
                    cmd_bank = session.query(CommandBank).filter(
                        CommandBank.make == cal.make,
                        CommandBank.model == cal.model
                    ).first()

                    if cmd_bank and cmd_bank.commands:
                        for ref_name in cmd_bank.commands.keys():
                            commands_found.add(ref_name)

                # Add sorted commands to dropdown
                for cmd_ref in sorted(commands_found):
                    self.section_cmd_combo.addItem(cmd_ref, cmd_ref)

                logger.debug(f"Loaded {len(commands_found)} command references")

        except Exception as e:
            logger.error(f"Failed to load command references: {e}")

    def _add_section_command(self):
        """Add selected command to the section command list."""
        cmd_ref = self.section_cmd_combo.currentData()
        if not cmd_ref:
            return

        # Check if already in list
        for i in range(self.section_cmd_list.count()):
            if self.section_cmd_list.item(i).text() == cmd_ref:
                return  # Already added

        self.section_cmd_list.addItem(cmd_ref)

    def _remove_section_command(self):
        """Remove selected command from the list."""
        current = self.section_cmd_list.currentRow()
        if current >= 0:
            self.section_cmd_list.takeItem(current)

    def _get_section_commands_json(self) -> str:
        """Get section commands as JSON string for saving."""
        import json
        commands = []
        for i in range(self.section_cmd_list.count()):
            commands.append(self.section_cmd_list.item(i).text())
        return json.dumps(commands) if commands else None

    def _set_section_commands_from_json(self, json_str: str):
        """Load section commands from JSON string."""
        import json
        self.section_cmd_list.clear()
        if json_str:
            try:
                commands = json.loads(json_str)
                if isinstance(commands, list):
                    for cmd in commands:
                        self.section_cmd_list.addItem(cmd)
                elif isinstance(commands, str):
                    # Legacy: single command as string
                    self.section_cmd_list.addItem(commands)
            except json.JSONDecodeError:
                # Legacy: plain string command
                self.section_cmd_list.addItem(json_str)

    def _save_current_section(self):
        """Save the current section details from the form."""
        if not self._current_section_id:
            QMessageBox.warning(self, "No Section", "No section selected to save.")
            return

        name = self.section_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Required", "Please enter a section name.")
            return

        standard_type = self.section_type_combo.currentData() or None
        wiring_type = self.section_wiring_combo.currentData() or None
        section_command = self._get_section_commands_json()
        section_prompt = self.section_prompt_input.toPlainText().strip() or None

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                section = session.query(TestSection).filter(
                    TestSection.id == self._current_section_id
                ).first()
                if section:
                    section.name = name
                    section.standard_section_type = standard_type
                    section.section_wiring_type = wiring_type
                    section.section_command = section_command
                    section.section_prompt = section_prompt
                    logger.info(f"Saved section {self._current_section_id}: {name}")

            # Update tree display
            current = self.structure_tree.currentItem()
            if current:
                display_text = name
                if standard_type:
                    display_text += f" [{standard_type}]"
                self.structure_tree.blockSignals(True)
                current.setText(0, display_text)
                self.structure_tree.blockSignals(False)

            QMessageBox.information(self, "Saved", "Section saved successfully.")

        except Exception as e:
            logger.error(f"Failed to save section: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save section: {e}")

    def _on_test_section(self):
        """Test/preview the section prompt and wiring diagram, optionally send commands."""
        section_name = self.section_name_input.text().strip() or "Unnamed Section"
        section_prompt = self.section_prompt_input.toPlainText().strip()
        wiring_type = self.section_wiring_combo.currentData()
        send_command = self.send_command_checkbox.isChecked()

        # Get commands from list widget
        section_commands = []
        for i in range(self.section_cmd_list.count()):
            section_commands.append(self.section_cmd_list.item(i).text())

        # Fall back to standard type if no wiring override
        if not wiring_type:
            wiring_type = self.section_type_combo.currentData()

        # Check if there's anything to test
        has_commands = len(section_commands) > 0
        if not section_prompt and not wiring_type and not (send_command and has_commands):
            QMessageBox.information(
                self,
                "No Section Instructions",
                f"Section '{section_name}' has no prompt, wiring diagram, or commands configured.\n\n"
                "Add:\n"
                "  - Operator Prompt: Instructions for the technician\n"
                "  - Wiring Diagram: Select a type to display a diagram\n"
                "  - Section Commands: Add commands from dropdown (check 'Send Command' to test)"
            )
            return

        # Send commands if checkbox is checked
        command_results = []
        if send_command and has_commands:
            command_results = self._send_test_commands(section_commands)

        # Load wiring diagram image if specified
        wiring_image = None
        wiring_image_path = None
        if wiring_type:
            db = get_db()
            if db.is_connected:
                try:
                    with db.session() as session:
                        diagram = session.query(WiringDiagramLibrary).filter(
                            WiringDiagramLibrary.section_name == wiring_type
                        ).first()
                        if diagram:
                            # Try file path first, fall back to BLOB
                            if diagram.image_path and os.path.exists(diagram.image_path):
                                wiring_image_path = diagram.image_path
                            elif diagram.image_data:
                                wiring_image = diagram.image_data
                except Exception as e:
                    logger.warning(f"Failed to load wiring diagram: {e}")

        # Create preview dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Section Preview")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)

        # Title
        title = QLabel(f"Section: {section_name}")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("This is what the technician will see when entering this section")
        subtitle.setStyleSheet("color: gray; font-style: italic;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # Wiring diagram (if any)
        if wiring_image or wiring_image_path:
            wiring_group = QGroupBox("Wiring Diagram")
            wiring_layout = QVBoxLayout(wiring_group)

            image_label = QLabel()
            pixmap = None

            # Try file path first, then BLOB
            if wiring_image_path:
                pixmap = QPixmap(wiring_image_path)
                if pixmap.isNull():
                    pixmap = None
            if pixmap is None and wiring_image:
                pixmap = QPixmap()
                pixmap.loadFromData(wiring_image)

            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(450, 300, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                image_label.setPixmap(scaled)
                image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                image_label.setText("(Could not load image)")

            wiring_layout.addWidget(image_label)
            layout.addWidget(wiring_group)
        elif wiring_type:
            no_image_label = QLabel(f"Wiring diagram selected: {wiring_type}\n(Image not found in database)")
            no_image_label.setStyleSheet("color: orange;")
            layout.addWidget(no_image_label)

        # Operator prompt (if any)
        if section_prompt:
            prompt_group = QGroupBox("Operator Instructions")
            prompt_layout = QVBoxLayout(prompt_group)

            prompt_label = QLabel(section_prompt)
            prompt_label.setWordWrap(True)
            prompt_label.setStyleSheet("font-size: 14px; padding: 10px;")
            prompt_layout.addWidget(prompt_label)

            layout.addWidget(prompt_group)

        # Command results (if commands were sent)
        if command_results:
            cmd_group = QGroupBox("Section Commands")
            cmd_layout = QVBoxLayout(cmd_group)

            for ref_name, actual_cmd, success in command_results:
                if success:
                    cmd_text = f"✓ {ref_name} → {actual_cmd}"
                    cmd_label = QLabel(cmd_text)
                    cmd_label.setStyleSheet("color: green; font-weight: bold;")
                else:
                    cmd_text = f"✗ {ref_name} → {actual_cmd or '(not found)'}"
                    cmd_label = QLabel(cmd_text)
                    cmd_label.setStyleSheet("color: red; font-weight: bold;")
                cmd_layout.addWidget(cmd_label)

            layout.addWidget(cmd_group)

        # OK button
        button_box = QHBoxLayout()
        button_box.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        button_box.addWidget(ok_btn)
        layout.addLayout(button_box)

        dialog.exec()

    def _send_test_commands(self, command_refs: list) -> list:
        """Send test commands to the calibrator, looking up from Command Bank.

        Args:
            command_refs: List of command reference names (e.g., ["Standby", "Reset"])

        Returns:
            List of tuples: (ref_name, actual_command, success)
        """
        results = []

        # Get command bank for workstation calibrator
        command_bank = self._get_workstation_command_bank()

        # Get calibrator address
        visa = get_visa_manager()
        target = None

        try:
            resources = visa.scan()
            if resources:
                gpib_resources = [r for r in resources if 'GPIB' in r.upper()]
                target = gpib_resources[0] if gpib_resources else resources[0]
                logger.debug(f"Using VISA target: {target}")
        except Exception as e:
            logger.error(f"Failed to get VISA resources: {e}")

        for ref_name in command_refs:
            # Look up actual command from command bank
            actual_cmd = command_bank.get(ref_name) if command_bank else None

            # If not found by reference name, check if it's a direct SCPI command in the bank values
            if not actual_cmd and command_bank:
                # Maybe the ref_name IS the SCPI command (bank keys are SCPI commands)
                if ref_name in command_bank.keys():
                    actual_cmd = command_bank[ref_name]  # Get value (might be same or description)
                    if not actual_cmd or actual_cmd == ref_name:
                        actual_cmd = ref_name  # Use the key directly as command

            # Still not found? Use ref_name directly as command (user typed raw SCPI)
            if not actual_cmd:
                logger.warning(f"Command reference '{ref_name}' not in bank, using as raw command")
                actual_cmd = ref_name

            if not target:
                logger.warning(f"No calibrator connected for command: {actual_cmd}")
                results.append((ref_name, actual_cmd, False))
                continue

            # Send the command
            try:
                logger.info(f"Sending command '{actual_cmd}' ({ref_name}) to {target}")
                success = visa.write(target, actual_cmd)
                results.append((ref_name, actual_cmd, bool(success)))
                if success:
                    logger.info(f"Command sent successfully: {actual_cmd}")
                else:
                    logger.warning(f"Command failed: {actual_cmd}")
            except Exception as e:
                logger.error(f"Failed to send command {actual_cmd}: {e}")
                results.append((ref_name, actual_cmd, False))

        return results

    def _get_workstation_command_bank(self) -> dict:
        """Get merged command bank dictionary from active workstation calibrators."""
        db = get_db()
        if not db.is_connected:
            logger.warning("Database not connected for command bank lookup")
            return {}

        try:
            with db.session() as session:
                from calsystem.database.models import Standard, CommandBank, DeviceGroupType, WorkstationStandard

                # Get ACTIVE workstation calibrators only
                calibrators = session.query(Standard).join(
                    WorkstationStandard, WorkstationStandard.standard_id == Standard.id
                ).filter(
                    WorkstationStandard.is_active == True,
                    Standard.device_group == DeviceGroupType.CALIBRATOR
                ).all()

                if not calibrators:
                    logger.warning("No active workstation calibrators found")
                    return {}

                # Merge command banks from all calibrators
                merged_commands = {}
                for calibrator in calibrators:
                    cmd_bank = session.query(CommandBank).filter(
                        CommandBank.make == calibrator.make,
                        CommandBank.model == calibrator.model
                    ).first()

                    if cmd_bank and cmd_bank.commands:
                        logger.debug(f"Found {len(cmd_bank.commands)} commands from {calibrator.make} {calibrator.model}")
                        merged_commands.update(cmd_bank.commands)

                if merged_commands:
                    logger.debug(f"Merged command bank has {len(merged_commands)} commands: {list(merged_commands.keys())}")
                    return merged_commands

                logger.warning("No command banks found for any calibrators")
                return {}

        except Exception as e:
            logger.error(f"Failed to get command bank: {e}")
            return {}

    def _load_testpoint_details(self, tp_id: int):
        """Load test point details into the form."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                tp = session.query(TestPoint).filter(TestPoint.id == tp_id).first()
                if not tp:
                    return

                # Test type
                type_map = {"measurement": 0, "pass_fail": 1, "calculated": 2, "dmm_measurement": 3, "calibrator_dmm": 4}
                type_index = type_map.get(tp.test_type.value if tp.test_type else "measurement", 0)
                self.test_type_combo.setCurrentIndex(type_index)
                self._on_test_type_changed(type_index)  # Update tab visibility

                # Nominal value and unit
                self.nominal_input.setValue(tp.nominal_value or 0)
                idx = self.unit_combo.findText(tp.unit or "V")
                if idx >= 0:
                    self.unit_combo.setCurrentIndex(idx)
                else:
                    self.unit_combo.setCurrentText(tp.unit or "V")

                # Frequency
                self.frequency_input.setValue(tp.frequency or 0)
                # Set frequency unit
                freq_unit = tp.frequency_unit or "Hz"
                freq_idx = self.freq_unit_combo.findText(freq_unit)
                if freq_idx >= 0:
                    self.freq_unit_combo.setCurrentIndex(freq_idx)
                else:
                    self.freq_unit_combo.setCurrentIndex(0)  # Default to Hz

                # Tolerance (legacy fields - kept for backward compatibility)
                self.tolerance_input.setValue(tp.tolerance_value or 0)
                tol_map = {"percent": 0, "absolute": 1, "ppm": 2}
                self.tolerance_type_combo.setCurrentIndex(
                    tol_map.get(tp.tolerance_type.value if tp.tolerance_type else "percent", 0)
                )

                # Multi-component tolerance fields
                self.tol_pct_reading_input.setValue(tp.tol_pct_reading or 0)
                self.tol_pct_range_input.setValue(tp.tol_pct_range or 0)
                self.tol_range_value_input.setValue(tp.tol_range_value or 0)
                self.tol_pct_span_input.setValue(tp.tol_pct_span or 0)
                self.tol_span_value_input.setValue(tp.tol_span_value or 0)
                self.tol_digits_input.setValue(int(tp.tol_digits or 0))
                # Convert resolution to decimal places (e.g., 0.001 -> 3)
                resolution = tp.tol_resolution or 0
                if resolution > 0:
                    import math
                    decimal_places = max(0, int(round(-math.log10(resolution))))
                else:
                    decimal_places = 0
                self.tol_decimal_places_input.setValue(decimal_places)
                self.tol_absolute_input.setValue(tp.tol_absolute or 0)

                # Update tolerance preview
                self._update_tolerance_preview()

                # Pass/Fail prompt and range
                self.pass_fail_prompt_input.setText(tp.pass_fail_prompt or "")
                if tp.pass_fail_min is not None:
                    self.pass_fail_min_input.setValue(tp.pass_fail_min)
                else:
                    self.pass_fail_min_input.setValue(self.pass_fail_min_input.minimum())
                if tp.pass_fail_max is not None:
                    self.pass_fail_max_input.setValue(tp.pass_fail_max)
                else:
                    self.pass_fail_max_input.setValue(self.pass_fail_max_input.minimum())
                if tp.pass_fail_range_unit:
                    idx = self.pass_fail_range_unit.findText(tp.pass_fail_range_unit)
                    if idx >= 0:
                        self.pass_fail_range_unit.setCurrentIndex(idx)

                # Pre-conditioning
                self.pre_nominal_input.setValue(tp.pre_nominal_value or 0)
                pre_unit_idx = self.pre_unit_combo.findText(tp.pre_unit or "Ohm")
                if pre_unit_idx >= 0:
                    self.pre_unit_combo.setCurrentIndex(pre_unit_idx)
                else:
                    self.pre_unit_combo.setCurrentText(tp.pre_unit or "Ohm")
                self.pre_frequency_input.setValue(tp.pre_frequency or 0)
                pre_freq_idx = self.pre_freq_unit_combo.findText(tp.pre_frequency_unit or "Hz")
                if pre_freq_idx >= 0:
                    self.pre_freq_unit_combo.setCurrentIndex(pre_freq_idx)
                self.pre_delay_input.setValue(tp.pre_delay_seconds or 0)

                # Load additional pre-conditioning steps
                self._load_pre_steps(tp.pre_conditioning_steps or [])

                # Commands
                self.source_cmd_input.setText(tp.source_command or "")
                self.operate_cmd_input.setText(tp.operate_command or "")
                self.measure_cmd_input.setText(tp.measure_command or "")

                # Excel mapping
                self.excel_sheet_input.setText(tp.excel_sheet or "")
                self.excel_cell_input.setText(tp.excel_cell or "")

                # Measurement target
                mt_map = {"PRIMARY": 0, "FREQUENCY": 1, "CUSTOM": 2}
                mt_value = tp.measurement_target.value if tp.measurement_target else "PRIMARY"
                self.measurement_target_combo.setCurrentIndex(mt_map.get(mt_value, 0))
                self.expected_value_input.setValue(tp.expected_value or 0)
                if tp.expected_unit:
                    eu_idx = self.expected_unit_combo.findText(tp.expected_unit)
                    if eu_idx >= 0:
                        self.expected_unit_combo.setCurrentIndex(eu_idx)
                    else:
                        self.expected_unit_combo.setCurrentText(tp.expected_unit)
                # Show/hide custom fields
                self._on_measurement_target_changed(self.measurement_target_combo.currentText())

                # Operator prompt - for Pass/Fail, load into operational check; for others, load into Advanced tab
                if tp.test_type and tp.test_type.value == "pass_fail":
                    self.operational_check_input.setText(tp.operator_prompt or "")
                    self.operator_prompt_edit.clear()
                else:
                    self.operator_prompt_edit.setPlainText(tp.operator_prompt or "")
                    self.operational_check_input.clear()

                # Wiring diagram type
                if tp.wiring_diagram_type:
                    idx = self.wiring_combo.findText(tp.wiring_diagram_type)
                    if idx >= 0:
                        self.wiring_combo.setCurrentIndex(idx)
                    else:
                        # Type not in current list, add it temporarily
                        self.wiring_combo.addItem(tp.wiring_diagram_type, tp.wiring_diagram_type)
                        self.wiring_combo.setCurrentText(tp.wiring_diagram_type)
                else:
                    self.wiring_combo.setCurrentIndex(0)  # None

                # Formula (for calculated test points)
                self.formula_input.setText(tp.formula or "")

                # DMM configuration
                self._load_dmm_config(tp.dmm_config)

                logger.debug(f"Loaded test point: {tp_id}")

        except Exception as e:
            logger.error(f"Failed to load test point: {e}")

    def _save_current_testpoint(self):
        """Save the current test point from form to database."""
        current = self.structure_tree.currentItem()
        if not current:
            QMessageBox.warning(self, "No Selection", "Please select a test point to save.")
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data or data[0] != "testpoint":
            QMessageBox.warning(self, "Invalid Selection", "Please select a test point (not a section) to save.")
            return

        tp_id = data[1]

        db = get_db()
        if not db.is_connected:
            QMessageBox.critical(self, "Database Error", "Not connected to database.")
            return

        try:
            with db.session() as session:
                tp = session.query(TestPoint).filter(TestPoint.id == tp_id).first()
                if not tp:
                    QMessageBox.warning(self, "Not Found", "Test point not found in database.")
                    return

                # Update from form
                type_map = {0: "measurement", 1: "pass_fail", 2: "calculated", 3: "dmm_measurement", 4: "calibrator_dmm"}
                from calsystem.database.models import TestPointType, ToleranceType
                tp.test_type = TestPointType(type_map[self.test_type_combo.currentIndex()])

                tp.nominal_value = self.nominal_input.value()
                tp.unit = self.unit_combo.currentText()
                tp.frequency = self.frequency_input.value() if self.frequency_input.value() > 0 else None
                tp.frequency_unit = self.freq_unit_combo.currentText() if self.frequency_input.value() > 0 else "Hz"

                tp.tolerance_value = self.tolerance_input.value()
                tol_map = {0: "percent", 1: "absolute", 2: "ppm"}
                tp.tolerance_type = ToleranceType(tol_map[self.tolerance_type_combo.currentIndex()])

                # Multi-component tolerance fields
                tp.tol_pct_reading = self.tol_pct_reading_input.value() or None
                tp.tol_pct_range = self.tol_pct_range_input.value() or None
                tp.tol_range_value = self.tol_range_value_input.value() or None
                tp.tol_pct_span = self.tol_pct_span_input.value() or None
                tp.tol_span_value = self.tol_span_value_input.value() or None
                tp.tol_digits = self.tol_digits_input.value() or None
                # Convert decimal places to resolution (e.g., 3 -> 0.001)
                decimal_places = self.tol_decimal_places_input.value()
                tp.tol_resolution = (10 ** (-decimal_places)) if decimal_places > 0 else None
                tp.tol_absolute = self.tol_absolute_input.value() or None

                # Sync legacy tolerance field from new fields for backward compatibility
                # Use % reading as the primary legacy value if set
                if self.tol_pct_reading_input.value() > 0:
                    tp.tolerance_value = self.tol_pct_reading_input.value()
                    tp.tolerance_type = ToleranceType.PERCENT
                elif self.tol_absolute_input.value() > 0:
                    tp.tolerance_value = self.tol_absolute_input.value()
                    tp.tolerance_type = ToleranceType.ABSOLUTE

                # Pass/Fail prompt and range
                tp.pass_fail_prompt = self.pass_fail_prompt_input.toPlainText().strip() or None
                # Only save range if values are set (not at minimum/special value)
                min_val = self.pass_fail_min_input.value()
                max_val = self.pass_fail_max_input.value()
                if min_val > self.pass_fail_min_input.minimum():
                    tp.pass_fail_min = min_val
                else:
                    tp.pass_fail_min = None
                if max_val > self.pass_fail_max_input.minimum():
                    tp.pass_fail_max = max_val
                else:
                    tp.pass_fail_max = None
                # Only save unit if at least one range value is set
                if tp.pass_fail_min is not None or tp.pass_fail_max is not None:
                    tp.pass_fail_range_unit = self.pass_fail_range_unit.currentText()
                else:
                    tp.pass_fail_range_unit = None

                # Pre-conditioning
                pre_val = self.pre_nominal_input.value()
                tp.pre_nominal_value = pre_val if pre_val != 0 else None
                tp.pre_unit = self.pre_unit_combo.currentText() if pre_val != 0 else None
                pre_freq = self.pre_frequency_input.value()
                tp.pre_frequency = pre_freq if pre_freq > 0 else None
                tp.pre_frequency_unit = self.pre_freq_unit_combo.currentText() if pre_freq > 0 else "Hz"
                tp.pre_delay_seconds = self.pre_delay_input.value() if pre_val != 0 else 0

                # Save additional pre-conditioning steps
                pre_steps = self._save_pre_steps()
                tp.pre_conditioning_steps = pre_steps if pre_steps else None

                tp.source_command = self.source_cmd_input.text().strip() or None
                tp.operate_command = self.operate_cmd_input.text().strip() or None
                tp.measure_command = self.measure_cmd_input.text().strip() or None

                tp.excel_sheet = self.excel_sheet_input.text().strip() or None
                tp.excel_cell = self.excel_cell_input.text().strip() or None

                # Measurement target
                from calsystem.database.models import MeasurementTarget
                mt_map = {0: "PRIMARY", 1: "FREQUENCY", 2: "CUSTOM"}
                tp.measurement_target = MeasurementTarget(mt_map[self.measurement_target_combo.currentIndex()])
                if tp.measurement_target == MeasurementTarget.CUSTOM:
                    tp.expected_value = self.expected_value_input.value()
                    tp.expected_unit = self.expected_unit_combo.currentText()
                else:
                    tp.expected_value = None
                    tp.expected_unit = None

                # Operator prompt - for Pass/Fail, use operational check; for others, use Advanced tab prompt
                if tp.test_type.value == "pass_fail":
                    prompt_text = self.operational_check_input.text().strip()
                else:
                    prompt_text = self.operator_prompt_edit.toPlainText().strip()
                tp.operator_prompt = prompt_text if prompt_text else None

                # Wiring diagram type
                wiring_type = self.wiring_combo.currentData()
                tp.wiring_diagram_type = wiring_type if wiring_type else None

                # Formula (for calculated test points)
                formula_text = self.formula_input.text().strip()
                tp.formula = formula_text if formula_text else None

                # DMM configuration - save if test type uses DMM or Pass/Fail with range check
                test_type_index = self.test_type_combo.currentIndex()
                # Check if Pass/Fail has range check configured
                has_range_check = (
                    self.pass_fail_min_input.value() > self.pass_fail_min_input.minimum() or
                    self.pass_fail_max_input.value() > self.pass_fail_max_input.minimum()
                )
                if test_type_index in [1, 3, 4] or has_range_check:  # Pass/Fail, DMM Measurement, or Calibrator + DMM
                    tp.dmm_config = self._save_dmm_config()
                else:
                    tp.dmm_config = None

                # Update tree display - for Pass/Fail show operational check, for others show nominal
                if tp.test_type.value == "pass_fail":
                    # Pass/Fail: show operational check text instead of nominal value
                    check_text = tp.operator_prompt or "Pass/Fail Check"
                    current.setText(0, tp.description or check_text)
                    current.setText(1, check_text)
                    current.setText(2, "Pass/Fail")
                else:
                    # Other types: show nominal value with frequency if present
                    nominal_str = f"{tp.nominal_value} {tp.unit}"
                    if tp.frequency:
                        nominal_str += f" @ {tp.frequency} {tp.frequency_unit}"
                    current.setText(0, tp.description or nominal_str)
                    current.setText(1, nominal_str)
                    # Format tolerance using multi-component spec
                    from calsystem.utils.tolerance import ToleranceSpec
                    tol_spec = ToleranceSpec(
                        pct_reading=tp.tol_pct_reading or 0,
                        pct_range=tp.tol_pct_range or 0,
                        pct_span=tp.tol_pct_span or 0,
                        digits=tp.tol_digits or 0,
                        absolute=tp.tol_absolute or 0,
                        resolution=tp.tol_resolution or 0,
                        range_value=tp.tol_range_value or 0,
                        span_value=tp.tol_span_value or 0,
                    )
                    if tol_spec.is_empty():
                        tol_spec = ToleranceSpec.from_legacy(
                            tp.tolerance_value or 0,
                            tp.tolerance_type.value if tp.tolerance_type else "percent"
                        )
                    current.setText(2, tol_spec.format_spec())

                logger.info(f"Saved test point: {tp_id}")

            # Show brief confirmation in status bar if available, or message box
            self.window().statusBar().showMessage("Test point saved", 2000)

        except Exception as e:
            logger.error(f"Failed to save test point: {e}")
            QMessageBox.critical(self, "Save Error", f"Failed to save test point:\n{e}")

    def _on_remove_item(self):
        """Remove selected section or test point."""
        current = self.structure_tree.currentItem()
        if not current:
            QMessageBox.warning(self, "No Selection", "Please select an item to remove.")
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        item_name = current.text(0)

        reply = QMessageBox.question(
            self,
            f"Remove {item_type.title()}",
            f"Are you sure you want to remove '{item_name}'?"
            + (" This will also remove all test points in this section." if item_type == "section" else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                if item_type == "section":
                    section = session.query(TestSection).filter(TestSection.id == item_id).first()
                    if section:
                        session.delete(section)
                        logger.info(f"Deleted section: {item_name}")
                elif item_type == "testpoint":
                    tp = session.query(TestPoint).filter(TestPoint.id == item_id).first()
                    if tp:
                        session.delete(tp)
                        logger.info(f"Deleted test point: {item_name}")

            # Remove from tree
            parent = current.parent()
            if parent:
                parent.removeChild(current)
            else:
                index = self.structure_tree.indexOfTopLevelItem(current)
                self.structure_tree.takeTopLevelItem(index)

        except Exception as e:
            logger.error(f"Failed to remove item: {e}")
            QMessageBox.critical(self, "Error", f"Failed to remove: {e}")

    def _on_move_up(self):
        """Move selected item up."""
        current = self.structure_tree.currentItem()
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        parent = current.parent()

        if parent:
            # Moving test point within section
            index = parent.indexOfChild(current)
            if index > 0:
                parent.takeChild(index)
                parent.insertChild(index - 1, current)
                self.structure_tree.setCurrentItem(current)
                self._update_testpoint_order(parent)
        else:
            # Moving section
            index = self.structure_tree.indexOfTopLevelItem(current)
            if index > 0:
                self.structure_tree.takeTopLevelItem(index)
                self.structure_tree.insertTopLevelItem(index - 1, current)
                self.structure_tree.setCurrentItem(current)
                self._update_section_order()

    def _on_move_down(self):
        """Move selected item down."""
        current = self.structure_tree.currentItem()
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        parent = current.parent()

        if parent:
            # Moving test point within section
            index = parent.indexOfChild(current)
            if index < parent.childCount() - 1:
                parent.takeChild(index)
                parent.insertChild(index + 1, current)
                self.structure_tree.setCurrentItem(current)
                self._update_testpoint_order(parent)
        else:
            # Moving section
            index = self.structure_tree.indexOfTopLevelItem(current)
            if index < self.structure_tree.topLevelItemCount() - 1:
                self.structure_tree.takeTopLevelItem(index)
                self.structure_tree.insertTopLevelItem(index + 1, current)
                self.structure_tree.setCurrentItem(current)
                self._update_section_order()

    def _update_section_order(self):
        """Update section order in database."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                for i in range(self.structure_tree.topLevelItemCount()):
                    item = self.structure_tree.topLevelItem(i)
                    data = item.data(0, Qt.ItemDataRole.UserRole)
                    if data and data[0] == "section":
                        section = session.query(TestSection).filter(TestSection.id == data[1]).first()
                        if section:
                            section.order = i
                logger.debug("Updated section order")
        except Exception as e:
            logger.error(f"Failed to update section order: {e}")

    def _update_testpoint_order(self, section_item: QTreeWidgetItem):
        """Update test point order in database."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                for i in range(section_item.childCount()):
                    item = section_item.child(i)
                    data = item.data(0, Qt.ItemDataRole.UserRole)
                    if data and data[0] == "testpoint":
                        tp = session.query(TestPoint).filter(TestPoint.id == data[1]).first()
                        if tp:
                            tp.order = i
                logger.debug("Updated test point order")
        except Exception as e:
            logger.error(f"Failed to update test point order: {e}")

    def _on_add_wiring(self):
        """Add wiring diagram image."""
        if not self._current_procedure_id:
            QMessageBox.warning(
                self, "No Procedure",
                "Please save the procedure first before adding wiring diagrams."
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Wiring Diagram",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*)",
        )
        if not file_path:
            return

        logger.info(f"Adding wiring diagram: {file_path}")

        # Get section ID if a section is selected
        section_id = None
        current = self.structure_tree.currentItem()
        if current:
            data = current.data(0, Qt.ItemDataRole.UserRole)
            if data:
                item_type, item_id = data
                if item_type == "section":
                    section_id = item_id
                elif item_type == "testpoint" and current.parent():
                    parent_data = current.parent().data(0, Qt.ItemDataRole.UserRole)
                    if parent_data and parent_data[0] == "section":
                        section_id = parent_data[1]

        db = get_db()
        if not db.is_connected:
            QMessageBox.critical(self, "Database Error", "Not connected to database.")
            return

        try:
            # Read image file
            from pathlib import Path
            image_data = Path(file_path).read_bytes()
            image_name = Path(file_path).name

            with db.session() as session:
                wiring = WiringDiagram(
                    procedure_id=self._current_procedure_id,
                    section_id=section_id,
                    name=image_name,
                    image_data=image_data,
                )
                session.add(wiring)

            logger.info(f"Saved wiring diagram: {image_name}")
            QMessageBox.information(
                self, "Wiring Diagram Added",
                f"Wiring diagram '{image_name}' has been added."
                + (f"\n\nLinked to section." if section_id else "\n\nLinked to procedure.")
            )

        except Exception as e:
            logger.error(f"Failed to add wiring diagram: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add wiring diagram:\n{e}")

    def _get_workstation_calibrators(self) -> List[Dict[str, Any]]:
        """
        Get all calibrators from workstation standards.

        Returns:
            List of calibrator dicts with address, make, model, serial, has_command_bank.
        """
        db = get_db()
        if not db.is_connected:
            return []

        calibrators = []

        try:
            from calsystem.config.settings import get_settings
            settings = get_settings()
            workstation_name = settings.workstation_name or "Default Workstation"

            with db.session() as session:
                config = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == workstation_name
                ).first()

                if not config:
                    logger.warning(f"No workstation config found: {workstation_name}")
                    return []

                # Get all calibrators from workstation
                ws_standards = session.query(WorkstationStandard).filter(
                    WorkstationStandard.workstation_id == config.id
                ).all()

                # Get all command banks for lookup
                command_banks = session.query(CommandBank.make, CommandBank.model).all()
                cb_set = {(cb.make.lower(), cb.model.lower()) for cb in command_banks}

                for ws_std in ws_standards:
                    standard = session.query(Standard).filter(
                        Standard.id == ws_std.standard_id
                    ).first()

                    if standard and standard.device_group == DeviceGroupType.CALIBRATOR:
                        has_cb = (standard.make.lower(), standard.model.lower()) in cb_set
                        calibrators.append({
                            "standard_id": standard.id,
                            "address": ws_std.visa_address or standard.visa_address or "",
                            "make": standard.make,
                            "model": standard.model,
                            "serial": standard.serial_number or "",
                            "has_command_bank": has_cb,
                        })

                logger.info(f"Found {len(calibrators)} calibrators in workstation")
                return calibrators

        except Exception as e:
            logger.error(f"Failed to get workstation calibrators: {e}")
            return []

    def _detect_connected_calibrators(self) -> List[Dict[str, Any]]:
        """
        Scan VISA bus and match connected instruments to workstation calibrators.

        Returns:
            List of connected calibrators with their info.
        """
        if not PYVISA_AVAILABLE:
            return []

        # Get workstation calibrators
        workstation_cals = self._get_workstation_calibrators()
        if not workstation_cals:
            return []

        # Scan VISA instruments
        visa = get_visa_manager()
        detected = visa.scan_and_identify()

        logger.info(f"Detected {len(detected)} VISA instruments")

        connected_calibrators = []

        for cal in workstation_cals:
            cal_address = cal.get("address", "")
            cal_make = cal.get("make", "").lower()
            cal_model = cal.get("model", "").lower()

            # Check if this calibrator is connected
            for inst in detected:
                if not inst.is_connected:
                    continue

                # Match by address
                if cal_address and inst.address == cal_address:
                    cal["detected_address"] = inst.address
                    cal["detected_make"] = inst.manufacturer
                    cal["detected_model"] = inst.model
                    connected_calibrators.append(cal)
                    logger.info(f"Matched calibrator by address: {cal['make']} {cal['model']} at {inst.address}")
                    break

                # Match by make/model (fuzzy)
                inst_make = inst.manufacturer.lower()
                inst_model = inst.model.lower()

                if (cal_make in inst_make or inst_make in cal_make) and \
                   (cal_model in inst_model or inst_model in cal_model):
                    cal["detected_address"] = inst.address
                    cal["detected_make"] = inst.manufacturer
                    cal["detected_model"] = inst.model
                    connected_calibrators.append(cal)
                    logger.info(f"Matched calibrator by make/model: {cal['make']} {cal['model']} at {inst.address}")
                    break

        return connected_calibrators

    def _select_calibrator(self, force_reselect: bool = False) -> Optional[Dict[str, Any]]:
        """
        Select a calibrator to use. Uses cached selection if available.

        Args:
            force_reselect: If True, ignore cached selection and re-detect.

        Returns:
            Selected calibrator dict, or None if cancelled/not found.
        """
        # Use cached selection if available
        if self._selected_calibrator and not force_reselect:
            logger.debug(f"Using cached calibrator: {self._selected_calibrator['make']} {self._selected_calibrator['model']}")
            return self._selected_calibrator

        # Detect connected calibrators
        connected = self._detect_connected_calibrators()

        if not connected:
            QMessageBox.warning(
                self, "No Calibrator Connected",
                "No calibrators detected on the VISA bus.\n\n"
                "Please check that:\n"
                "1. Your calibrator is powered on\n"
                "2. It's connected via GPIB/USB/LAN\n"
                "3. It's added to your workstation standards (Workstation tab)\n"
                "4. The Group is set to 'Calibrator'"
            )
            return None

        if len(connected) == 1:
            # Auto-select the only calibrator
            self._selected_calibrator = connected[0]
            self._load_calibrator_commands()
            logger.info(f"Auto-selected calibrator: {connected[0]['make']} {connected[0]['model']}")

            QMessageBox.information(
                self, "Calibrator Detected",
                f"Using calibrator: {connected[0]['make']} {connected[0]['model']}\n"
                f"Address: {connected[0].get('detected_address', connected[0].get('address', 'Unknown'))}"
            )
            return self._selected_calibrator

        # Multiple calibrators - show selection dialog
        dialog = CalibratorSelectionDialog(connected, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._selected_calibrator = dialog.get_selected_calibrator()
            if self._selected_calibrator:
                self._load_calibrator_commands()
                logger.info(f"User selected calibrator: {self._selected_calibrator['make']} {self._selected_calibrator['model']}")
                return self._selected_calibrator

        return None

    def _load_calibrator_commands(self):
        """Load command bank for the selected calibrator."""
        if not self._selected_calibrator:
            self._selected_calibrator_commands = None
            return

        make = self._selected_calibrator.get("make", "")
        model = self._selected_calibrator.get("model", "")

        db = get_db()
        if not db.is_connected:
            self._selected_calibrator_commands = None
            return

        try:
            with db.session() as session:
                # Look up command bank by make/model (case-insensitive)
                command_bank = session.query(CommandBank).filter(
                    CommandBank.make.ilike(make),
                    CommandBank.model.ilike(model)
                ).first()

                if command_bank and command_bank.commands:
                    self._selected_calibrator_commands = command_bank.commands
                    logger.info(f"Loaded command bank for {make} {model}: {list(self._selected_calibrator_commands.keys())}")
                else:
                    self._selected_calibrator_commands = None
                    logger.warning(f"No command bank found for {make} {model}")

        except Exception as e:
            logger.error(f"Failed to load command bank: {e}")
            self._selected_calibrator_commands = None

    def _get_calibrator_command(self, command_name: str) -> Optional[str]:
        """
        Get a command from the selected calibrator's command bank.

        Args:
            command_name: Command name (e.g., 'OUT', 'OPER', 'STBY')

        Returns:
            Command string, or None if not found.
        """
        if not self._selected_calibrator_commands:
            return None

        # Try exact match first
        if command_name in self._selected_calibrator_commands:
            return self._selected_calibrator_commands[command_name]

        # Try case-insensitive match
        for key, value in self._selected_calibrator_commands.items():
            if key.lower() == command_name.lower():
                return value

        return None

    def _get_calibrator_address(self) -> Optional[str]:
        """Get the VISA address of the selected calibrator."""
        if not self._selected_calibrator:
            return None
        return self._selected_calibrator.get("detected_address") or self._selected_calibrator.get("address")

    def _substitute_placeholders(self, command: str) -> str:
        """
        Substitute placeholders in command.

        Placeholders:
            {value} - Nominal value (e.g., 10)
            {unit} - Unit string (e.g., V, mV, A, Ohm)
            {frequency} - Frequency value as entered (e.g., 1 if 1 kHz)
            {freq_unit} - Frequency unit string (e.g., Hz, kHz, MHz)
            {freq_hz} - Frequency converted to Hz (e.g., 1000 for 1 kHz)

        If frequency > 0 and command doesn't contain frequency placeholders,
        automatically appends ",{freq_hz} HZ" for AC outputs.
        """
        if not command:
            return ""

        value = self.nominal_input.value()
        unit = self.unit_combo.currentText()
        frequency = self.frequency_input.value()
        freq_unit = self.freq_unit_combo.currentText()

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

    # ==================== DMM Detection & Selection ====================

    def _get_workstation_dmms(self) -> List[Dict[str, Any]]:
        """
        Get all DMMs from workstation standards.

        Returns:
            List of DMM dicts with address, make, model, serial.
        """
        db = get_db()
        if not db.is_connected:
            return []

        dmms = []

        try:
            from calsystem.config.settings import get_settings
            settings = get_settings()
            workstation_name = settings.workstation_name or "Default Workstation"

            with db.session() as session:
                config = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == workstation_name
                ).first()

                if not config:
                    logger.warning(f"No workstation config found: {workstation_name}")
                    return []

                # Get all standards from workstation
                ws_standards = session.query(WorkstationStandard).filter(
                    WorkstationStandard.workstation_id == config.id
                ).all()

                for ws_std in ws_standards:
                    standard = session.query(Standard).filter(
                        Standard.id == ws_std.standard_id
                    ).first()

                    if standard and standard.device_group == DeviceGroupType.DMM:
                        dmms.append({
                            "standard_id": standard.id,
                            "address": ws_std.visa_address or standard.visa_address or "",
                            "make": standard.make,
                            "model": standard.model,
                            "serial": standard.serial_number or "",
                        })

                logger.info(f"Found {len(dmms)} DMMs in workstation")
                return dmms

        except Exception as e:
            logger.error(f"Failed to get workstation DMMs: {e}")
            return []

    def _select_dmm(self, force_reselect: bool = False) -> Optional[Dict[str, Any]]:
        """
        Select a DMM to use from workstation config. No VISA scanning.

        Args:
            force_reselect: If True, ignore cached selection.

        Returns:
            Selected DMM dict, or None if cancelled/not found.
        """
        # Use cached selection if available
        if self._selected_dmm and not force_reselect:
            logger.debug(f"Using cached DMM: {self._selected_dmm['make']} {self._selected_dmm['model']}")
            return self._selected_dmm

        # Get DMMs from workstation config (no scanning)
        workstation_dmms = self._get_workstation_dmms()

        if not workstation_dmms:
            QMessageBox.warning(
                self, "No DMM Configured",
                "No DMMs found in workstation configuration.\n\n"
                "Please add your DMM to workstation standards (Workstation tab)\n"
                "with Group set to 'DMM'."
            )
            return None

        if len(workstation_dmms) == 1:
            # Auto-select the only DMM
            self._selected_dmm = workstation_dmms[0]
            logger.info(f"Using DMM from workstation: {workstation_dmms[0]['make']} {workstation_dmms[0]['model']} at {workstation_dmms[0].get('address', 'Unknown')}")
            return self._selected_dmm

        # Multiple DMMs - show selection dialog
        from PyQt6.QtWidgets import QInputDialog
        items = [f"{d['make']} {d['model']} ({d.get('address', 'Unknown')})"
                 for d in workstation_dmms]
        item, ok = QInputDialog.getItem(
            self, "Select DMM",
            "Multiple DMMs in workstation. Select one:",
            items, 0, False
        )

        if ok and item:
            idx = items.index(item)
            self._selected_dmm = workstation_dmms[idx]
            logger.info(f"User selected DMM: {self._selected_dmm['make']} {self._selected_dmm['model']}")
            return self._selected_dmm

        return None

    def _get_dmm_address(self) -> Optional[str]:
        """Get the VISA address of the selected DMM from workstation config."""
        if not self._selected_dmm:
            return None
        return self._selected_dmm.get("address")

    def _on_test_dmm_reading(self):
        """Test the DMM settings by sending commands and taking a reading."""
        if not PYVISA_AVAILABLE:
            QMessageBox.warning(
                self, "PyVISA Not Available",
                "PyVISA is not installed. Cannot communicate with instruments."
            )
            return

        # Select DMM (auto-detect or from cache)
        dmm = self._select_dmm()
        if not dmm:
            return

        address = self._get_dmm_address()
        if not address:
            QMessageBox.warning(
                self, "No Address",
                "Selected DMM has no VISA address.\n\n"
                "Please check the workstation standard configuration."
            )
            return

        # Build command sequence from current DMM settings
        commands = []
        func = self.dmm_func_combo.currentText()
        range_val = self.dmm_range_combo.currentText()
        delay = self.dmm_delay_input.value()

        # Collect custom commands by order (Before/After)
        before_cmds = []
        after_cmds = []
        for row in range(self.dmm_commands_table.rowCount()):
            cmd_item = self.dmm_commands_table.item(row, 1)
            order_widget = self.dmm_commands_table.cellWidget(row, 2)
            if cmd_item:
                cmd = cmd_item.text().strip()
                if cmd:
                    order = "After"
                    if order_widget and isinstance(order_widget, QComboBox):
                        order = order_widget.currentText()
                    if order == "Before":
                        before_cmds.append(cmd)
                    else:
                        after_cmds.append(cmd)

        # 1. Custom "Before" commands (e.g., RESET, END ALWAYS)
        commands.extend(before_cmds)

        # 2. Core settings - using HP 3458A syntax (most common high-end DMM)
        commands.append(f"FUNC {func}")
        if range_val != "AUTO":
            commands.append(f"RANGE {range_val}")
        else:
            commands.append("ARANGE ON")  # Auto-range (3458A)

        # 3. Optional settings (only what's in the table)
        optional_count = self.dmm_optional_table.rowCount()
        logger.debug(f"Optional settings table has {optional_count} rows")
        for row in range(optional_count):
            name_item = self.dmm_optional_table.item(row, 0)
            value_widget = self.dmm_optional_table.cellWidget(row, 1)
            if name_item and value_widget and isinstance(value_widget, QComboBox):
                setting_name = name_item.text()
                setting_value = value_widget.currentText()
                logger.debug(f"  Row {row}: {setting_name} = {setting_value}")
                commands.append(f"{setting_name} {setting_value}")

        # 4. Delay
        if delay > 0:
            commands.append(f"DELAY {delay}")

        # 5. Custom "After" commands
        commands.extend(after_cmds)

        logger.info(f"Testing DMM reading at {address}")
        logger.info(f"Commands: {commands}")

        visa = get_visa_manager()
        errors = []
        success_cmds = []

        # Send all setup commands
        for cmd in commands:
            if visa.write(address, cmd):
                success_cmds.append(cmd)
            else:
                errors.append(f"Failed: {cmd}")

        if errors:
            QMessageBox.critical(
                self, "DMM Setup Failed",
                "Some commands failed:\n\n" + "\n".join(errors) +
                "\n\nSuccessful:\n" + "\n".join(success_cmds)
            )
            return

        # Take a reading
        import time
        time.sleep(0.1)  # Brief settle time

        # For 3458A: trigger and read
        reading = None

        # Try TRIG SGL first (3458A style)
        visa.write(address, "TRIG SGL")
        time.sleep(0.2)  # Wait for measurement

        # Query returns (success, response) tuple
        success, response = visa.query(address, "")
        if success and response:
            reading = response.strip()
        else:
            # Try explicit read command
            success, response = visa.query(address, "READ?")
            if success and response:
                reading = response.strip()

        if reading:
            dmm_info = f"{dmm['make']} {dmm['model']}"

            # Get expected unit from test point to format reading
            expected_value = self.nominal_input.value()
            expected_unit = self.unit_combo.currentText()

            # Convert reading to match test point unit
            try:
                raw_value = float(reading)

                # Unit conversion multipliers (from base unit to display unit)
                # DMM returns in base units (V, A, Ohm, Hz)
                unit_divisors = {
                    "mV": 0.001, "uV": 0.000001, "kV": 1000,
                    "mA": 0.001, "uA": 0.000001,
                    "kOhm": 1000, "MOhm": 1000000,
                    "kHz": 1000, "MHz": 1000000,
                    "V": 1, "A": 1, "Ohm": 1, "Hz": 1,
                }

                divisor = unit_divisors.get(expected_unit, 1.0)
                converted_value = raw_value / divisor

                # Get decimal places from dropdown
                format_selection = self.dmm_reading_format_combo.currentText()
                if format_selection.startswith("Match"):
                    # Auto-determine based on expected value magnitude
                    if expected_value >= 100:
                        decimals = 2
                    elif expected_value >= 10:
                        decimals = 3
                    elif expected_value >= 1:
                        decimals = 4
                    else:
                        decimals = 5
                else:
                    # Parse decimal count from selection (e.g., "0.0000 (4 decimals)" -> 4)
                    decimals = format_selection.count('0') - 1  # Count zeros after decimal

                formatted_reading = f"{converted_value:.{decimals}f} {expected_unit}"

                QMessageBox.information(
                    self, "DMM Test Reading",
                    f"DMM ({dmm_info}) returned:\n\n"
                    f"   {formatted_reading}\n"
                    f"   (raw: {reading})\n\n"
                    f"   Expected: {expected_value} {expected_unit}\n\n"
                    f"Setup commands sent:\n" + "\n".join(f"   {c}" for c in success_cmds)
                )
            except ValueError:
                # Can't parse, show raw
                QMessageBox.information(
                    self, "DMM Test Reading",
                    f"DMM ({dmm_info}) returned:\n\n"
                    f"   {reading}\n\n"
                    f"Setup commands sent:\n" + "\n".join(f"   {c}" for c in success_cmds)
                )
        else:
            QMessageBox.warning(
                self, "No Reading",
                "DMM setup commands sent successfully, but no reading was returned.\n\n"
                "The DMM may need a trigger or the read command may be different.\n\n"
                f"Commands sent:\n" + "\n".join(f"   {c}" for c in success_cmds)
            )

    def _on_test_output(self):
        """Test the current test point by sending commands to calibrator."""
        if not PYVISA_AVAILABLE:
            QMessageBox.warning(
                self, "PyVISA Not Available",
                "PyVISA is not installed. Cannot communicate with instruments."
            )
            return

        # Select calibrator (auto-detect or from cache)
        calibrator = self._select_calibrator()
        if not calibrator:
            return  # User cancelled or no calibrator found

        address = self._get_calibrator_address()
        if not address:
            QMessageBox.warning(
                self, "No Address",
                "Selected calibrator has no VISA address.\n\n"
                "Please check the workstation standard configuration."
            )
            return

        # Get commands - prefer form input, fall back to command bank
        source_cmd = self.source_cmd_input.text().strip()
        operate_cmd = self.operate_cmd_input.text().strip()

        # If no source command in form, try to get from command bank
        if not source_cmd:
            # Try common source command names from command bank
            for cmd_name in ["OUT", "SOURCE", "OUTPUT", "out", "source"]:
                bank_cmd = self._get_calibrator_command(cmd_name)
                if bank_cmd:
                    source_cmd = bank_cmd
                    logger.info(f"Using command bank source command: {source_cmd}")
                    break

        if not source_cmd:
            QMessageBox.warning(
                self, "No Source Command",
                "No source command defined.\n\n"
                "Either:\n"
                "1. Enter a source command in the form (e.g., 'OUT {value} {unit}')\n"
                "2. Or create a command bank for this calibrator with an 'OUT' command"
            )
            return

        # Apply placeholder substitution
        source_cmd = self._substitute_placeholders(source_cmd)

        # If no operate command, try command bank
        if not operate_cmd:
            operate_cmd = self._get_calibrator_command("OPER") or \
                          self._get_calibrator_command("OPERATE") or ""

        logger.info(f"Testing output: {source_cmd} to {address}")
        logger.info(f"Using calibrator: {calibrator['make']} {calibrator['model']}")

        visa = get_visa_manager()
        errors = []
        success_msgs = []

        # Send source command
        if visa.write(address, source_cmd):
            success_msgs.append(f"Source: {source_cmd}")
        else:
            errors.append(f"Failed to send source command: {source_cmd}")

        # Send operate command if defined
        if operate_cmd and not errors:
            if visa.write(address, operate_cmd):
                success_msgs.append(f"Operate: {operate_cmd}")
            else:
                errors.append(f"Failed to send operate command: {operate_cmd}")

        # Show result
        if errors:
            QMessageBox.critical(
                self, "Test Failed",
                "Errors occurred:\n\n" + "\n".join(errors)
            )
        else:
            value = self.nominal_input.value()
            unit = self.unit_combo.currentText()
            freq = self.frequency_input.value()
            freq_unit = self.freq_unit_combo.currentText()

            output_desc = f"{value} {unit}"
            if freq > 0:
                output_desc += f" @ {freq} {freq_unit}"

            cal_info = f"{calibrator['make']} {calibrator['model']}"

            QMessageBox.information(
                self, "Test Output Success",
                f"Calibrator ({cal_info}) is now outputting:\n\n"
                f"   {output_desc}\n\n"
                f"Commands sent:\n" + "\n".join(f"   {m}" for m in success_msgs) +
                f"\n\nClick 'Standby' when done to turn off the output."
            )

    def _on_preview_passfail(self):
        """Preview the Pass/Fail dialog as the technician would see it."""
        # Get prompt text
        prompt_text = self.pass_fail_prompt_input.toPlainText().strip()
        if not prompt_text:
            prompt_text = "(No prompt entered)"

        # Get range check info
        min_val = self.pass_fail_min_input.value()
        max_val = self.pass_fail_max_input.value()
        has_min = min_val > self.pass_fail_min_input.minimum()
        has_max = max_val > self.pass_fail_max_input.minimum()
        range_unit = self.pass_fail_range_unit.currentText()

        range_text = ""
        if has_min or has_max:
            if has_min and has_max:
                range_text = f"Expected range: {min_val} to {max_val} {range_unit}"
            elif has_min:
                range_text = f"Minimum: {min_val} {range_unit}"
            else:
                range_text = f"Maximum: {max_val} {range_unit}"

        # Get wiring diagram (from Advanced tab)
        wiring_type = self.wiring_combo.currentText()
        wiring_image = None
        wiring_image_path = None

        if wiring_type and wiring_type != "None" and not wiring_type.startswith("--"):
            # Try to load the wiring diagram image from library
            db = get_db()
            if db.is_connected:
                try:
                    with db.session() as session:
                        # Look up in WiringDiagramLibrary by section_name
                        diagram = session.query(WiringDiagramLibrary).filter(
                            WiringDiagramLibrary.section_name == wiring_type
                        ).first()

                        if diagram:
                            # Try file path first, fall back to BLOB
                            if diagram.image_path and os.path.exists(diagram.image_path):
                                wiring_image_path = diagram.image_path
                            elif diagram.image_data:
                                wiring_image = diagram.image_data
                except Exception as e:
                    logger.warning(f"Failed to load wiring diagram: {e}")

        # Create preview dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Pass/Fail Preview")
        dialog.setMinimumWidth(500)
        layout = QVBoxLayout(dialog)

        # Title
        title = QLabel("Pass/Fail Test Point Preview")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("This is what the technician will see during execution")
        subtitle.setStyleSheet("color: gray; font-style: italic;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # Wiring diagram (if any)
        if wiring_image or wiring_image_path:
            wiring_group = QGroupBox("Wiring Diagram")
            wiring_layout = QVBoxLayout(wiring_group)

            image_label = QLabel()
            pixmap = None

            # Try file path first, then BLOB
            if wiring_image_path:
                pixmap = QPixmap(wiring_image_path)
                if pixmap.isNull():
                    pixmap = None
            if pixmap is None and wiring_image:
                pixmap = QPixmap()
                pixmap.loadFromData(wiring_image)

            if pixmap and not pixmap.isNull():
                # Scale to fit
                scaled = pixmap.scaled(450, 300, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                image_label.setPixmap(scaled)
                image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                image_label.setText("(Could not load image)")

            wiring_layout.addWidget(image_label)
            layout.addWidget(wiring_group)
        elif wiring_type and not wiring_type.startswith("--"):
            no_image_label = QLabel(f"Wiring diagram selected: {wiring_type}\n(Image not found in database)")
            no_image_label.setStyleSheet("color: orange;")
            layout.addWidget(no_image_label)

        # Prompt
        prompt_group = QGroupBox("Technician Prompt")
        prompt_layout = QVBoxLayout(prompt_group)

        prompt_label = QLabel(prompt_text)
        prompt_label.setWordWrap(True)
        prompt_label.setStyleSheet("font-size: 14px; padding: 10px;")
        prompt_layout.addWidget(prompt_label)

        if range_text:
            range_label = QLabel(range_text)
            range_label.setStyleSheet("color: blue; font-weight: bold; padding: 5px;")
            prompt_layout.addWidget(range_label)

        layout.addWidget(prompt_group)

        # Sample Pass/Fail buttons (disabled, just for preview)
        btn_layout = QHBoxLayout()
        pass_btn = QPushButton("PASS")
        pass_btn.setStyleSheet("background-color: #4CAF50; color: white; font-size: 14px; padding: 10px 30px;")
        pass_btn.setEnabled(False)
        btn_layout.addWidget(pass_btn)

        fail_btn = QPushButton("FAIL")
        fail_btn.setStyleSheet("background-color: #f44336; color: white; font-size: 14px; padding: 10px 30px;")
        fail_btn.setEnabled(False)
        btn_layout.addWidget(fail_btn)

        layout.addLayout(btn_layout)

        # Close button
        layout.addSpacing(10)
        close_btn = QPushButton("Close Preview")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

    def _on_test_pass_fail(self):
        """Test the full Pass/Fail flow simulating execution session."""
        from PyQt6.QtWidgets import QProgressDialog

        if not PYVISA_AVAILABLE:
            QMessageBox.warning(
                self, "PyVISA Not Available",
                "PyVISA is not installed. Cannot communicate with instruments."
            )
            return

        visa = get_visa_manager()

        # ========== STEP 1: Show Wiring Diagram (if configured) ==========
        wiring_type = self.wiring_combo.currentText()
        wiring_image = None
        wiring_image_path = None

        if wiring_type and wiring_type != "None" and not wiring_type.startswith("--"):
            db = get_db()
            if db.is_connected:
                try:
                    with db.session() as session:
                        diagram = session.query(WiringDiagramLibrary).filter(
                            WiringDiagramLibrary.section_name == wiring_type
                        ).first()
                        if diagram:
                            # Try file path first, fall back to BLOB
                            if diagram.image_path and os.path.exists(diagram.image_path):
                                wiring_image_path = diagram.image_path
                            elif diagram.image_data:
                                wiring_image = diagram.image_data
                except Exception as e:
                    logger.warning(f"Failed to load wiring diagram: {e}")

            if wiring_image or wiring_image_path:
                # Show wiring diagram dialog first
                wiring_dialog = QDialog(self)
                wiring_dialog.setWindowTitle("Wiring Setup")
                wiring_dialog.setMinimumWidth(500)
                wiring_layout = QVBoxLayout(wiring_dialog)

                title = QLabel("Connect the DUT as shown:")
                title.setStyleSheet("font-size: 14px; font-weight: bold;")
                wiring_layout.addWidget(title)

                image_label = QLabel()
                pixmap = None

                # Try file path first, then BLOB
                if wiring_image_path:
                    pixmap = QPixmap(wiring_image_path)
                    if pixmap.isNull():
                        pixmap = None
                if pixmap is None and wiring_image:
                    pixmap = QPixmap()
                    pixmap.loadFromData(wiring_image)

                if pixmap and not pixmap.isNull():
                    scaled = pixmap.scaled(450, 350, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
                    image_label.setPixmap(scaled)
                    image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                wiring_layout.addWidget(image_label)

                btn_layout = QHBoxLayout()
                cancel_btn = QPushButton("Cancel")
                cancel_btn.clicked.connect(wiring_dialog.reject)
                btn_layout.addWidget(cancel_btn)
                btn_layout.addStretch()
                proceed_btn = QPushButton("Ready - Proceed")
                proceed_btn.setStyleSheet("font-weight: bold;")
                proceed_btn.clicked.connect(wiring_dialog.accept)
                btn_layout.addWidget(proceed_btn)
                wiring_layout.addLayout(btn_layout)

                if wiring_dialog.exec() != QDialog.DialogCode.Accepted:
                    return  # User cancelled

        # ========== STEP 2: Run Calibrator (if configured) ==========
        calibrator = None
        cal_address = None
        cal_info = ""
        source_cmd = self.source_cmd_input.text().strip()

        # Check if we have calibrator settings
        if source_cmd or self.pre_nominal_input.value() != 0:
            calibrator = self._select_calibrator()
            if calibrator:
                cal_address = self._get_calibrator_address()
                cal_info = f"{calibrator['make']} {calibrator['model']}"

                if not cal_address:
                    QMessageBox.warning(self, "No Address", "Selected calibrator has no VISA address.")
                    return

                # Get source command from bank if not set
                if not source_cmd:
                    for cmd_name in ["OUT", "SOURCE", "OUTPUT"]:
                        bank_cmd = self._get_calibrator_command(cmd_name)
                        if bank_cmd:
                            source_cmd = bank_cmd
                            break

                operate_cmd = self.operate_cmd_input.text().strip()
                if not operate_cmd:
                    operate_cmd = self._get_calibrator_command("OPER") or ""

                # Pre-conditioning
                pre_value = self.pre_nominal_input.value()
                if pre_value != 0 and source_cmd:
                    pre_cmd = self._substitute_pre_placeholders(source_cmd)
                    logger.info(f"Pre-conditioning: {pre_cmd}")

                    if not visa.write(cal_address, pre_cmd):
                        QMessageBox.critical(self, "Error", "Failed to send pre-conditioning command.")
                        return

                    if operate_cmd:
                        visa.write(cal_address, operate_cmd)

                    # Wait for delay
                    delay = self.pre_delay_input.value()
                    if delay > 0:
                        progress = QProgressDialog(f"Pre-conditioning delay: {delay}s", None, 0, int(delay * 10), self)
                        progress.setWindowTitle("Pre-conditioning")
                        progress.setWindowModality(Qt.WindowModality.WindowModal)
                        progress.setMinimumDuration(0)
                        progress.setValue(0)

                        start_time = time.time()
                        while time.time() - start_time < delay:
                            elapsed = time.time() - start_time
                            progress.setValue(int(elapsed * 10))
                            progress.setLabelText(f"Waiting {delay - elapsed:.1f} seconds...")
                            QApplication.processEvents()
                            time.sleep(0.05)
                        progress.close()

                # Send actual calibrator output
                if source_cmd:
                    actual_cmd = self._substitute_placeholders(source_cmd)
                    logger.info(f"Calibrator output: {actual_cmd}")

                    if not visa.write(cal_address, actual_cmd):
                        QMessageBox.critical(self, "Error", "Failed to send calibrator command.")
                        return

                    if operate_cmd:
                        visa.write(cal_address, operate_cmd)

        # ========== STEP 3: Take DMM Reading (if range check configured) ==========
        dmm_reading = None
        dmm_reading_str = None
        range_result = None  # "in_range", "out_of_range", or None

        min_val = self.pass_fail_min_input.value()
        max_val = self.pass_fail_max_input.value()
        has_min = min_val > self.pass_fail_min_input.minimum()
        has_max = max_val > self.pass_fail_max_input.minimum()
        range_unit = self.pass_fail_range_unit.currentText()

        if has_min or has_max:
            # Determine decimal places from range values
            def get_decimal_places(value: float) -> int:
                """Count decimal places in a float value."""
                s = str(value)
                if '.' in s:
                    return len(s.split('.')[1].rstrip('0')) or 0
                return 0

            # Use the max decimal places from min/max values
            decimals = 0
            if has_min:
                decimals = max(decimals, get_decimal_places(min_val))
            if has_max:
                decimals = max(decimals, get_decimal_places(max_val))
            # Ensure at least 1 decimal for readability
            decimals = max(decimals, 1)

            # Range check requires DMM reading
            dmm = self._select_dmm()
            if dmm:
                dmm_address = self._get_dmm_address()
                if dmm_address:
                    # Determine function from range unit
                    unit_lower = range_unit.lower()
                    if 'ohm' in unit_lower:
                        dmm_func = "OHM"
                    elif 'a' in unit_lower and 'ohm' not in unit_lower:
                        dmm_func = "DCI"
                    else:
                        dmm_func = "DCV"

                    # Build command sequence from saved DMM config
                    # Get custom commands separated by order
                    before_cmds = []
                    after_cmds = []
                    for row in range(self.dmm_commands_table.rowCount()):
                        cmd_item = self.dmm_commands_table.item(row, 1)
                        order_widget = self.dmm_commands_table.cellWidget(row, 2)
                        if cmd_item:
                            cmd = cmd_item.text().strip()
                            if cmd:
                                order = "After"
                                if order_widget and isinstance(order_widget, QComboBox):
                                    order = order_widget.currentText()
                                if order == "Before":
                                    before_cmds.append(cmd)
                                else:
                                    after_cmds.append(cmd)

                    # 1. Send "Before" commands (e.g., RESET, END ALWAYS)
                    for cmd in before_cmds:
                        logger.debug(f"DMM Before cmd: {cmd}")
                        visa.write(dmm_address, cmd)

                    # 2. Setup function and range
                    visa.write(dmm_address, f"FUNC {dmm_func}")
                    range_val = self.dmm_range_combo.currentText()
                    if range_val != "AUTO":
                        visa.write(dmm_address, f"RANGE {range_val}")
                    else:
                        visa.write(dmm_address, "ARANGE ON")

                    # 3. Optional settings
                    for row in range(self.dmm_optional_table.rowCount()):
                        name_item = self.dmm_optional_table.item(row, 0)
                        value_widget = self.dmm_optional_table.cellWidget(row, 1)
                        if name_item and value_widget and isinstance(value_widget, QComboBox):
                            setting_name = name_item.text()
                            setting_value = value_widget.currentText()
                            visa.write(dmm_address, f"{setting_name} {setting_value}")

                    # 4. Delay setting
                    delay = self.dmm_delay_input.value()
                    if delay > 0:
                        visa.write(dmm_address, f"DELAY {delay}")

                    # 5. Send "After" commands
                    for cmd in after_cmds:
                        logger.debug(f"DMM After cmd: {cmd}")
                        visa.write(dmm_address, cmd)

                    time.sleep(0.2)

                    # Take reading
                    visa.write(dmm_address, "TRIG SGL")
                    time.sleep(0.3)

                    success, response = visa.query(dmm_address, "")
                    if success and response:
                        try:
                            raw_value = float(response.strip())

                            # Convert to range unit
                            unit_divisors = {
                                "mV": 0.001, "uV": 0.000001,
                                "mA": 0.001, "uA": 0.000001,
                                "kOhm": 1000, "MOhm": 1000000,
                                "V": 1, "A": 1, "Ohm": 1,
                            }
                            divisor = unit_divisors.get(range_unit, 1.0)
                            dmm_reading = raw_value / divisor

                            # Format to match range value precision
                            dmm_reading_str = f"{dmm_reading:.{decimals}f} {range_unit}"

                            # Check against range
                            in_range = True
                            if has_min and dmm_reading < min_val:
                                in_range = False
                            if has_max and dmm_reading > max_val:
                                in_range = False
                            range_result = "in_range" if in_range else "out_of_range"

                        except ValueError:
                            dmm_reading_str = f"Error: {response}"
                else:
                    dmm_reading_str = "(No DMM address)"
            else:
                dmm_reading_str = "(No DMM configured)"

        # ========== STEP 4: Show Pass/Fail Dialog ==========
        operational_check = self.operational_check_input.text().strip()
        prompt = self.pass_fail_prompt_input.toPlainText().strip() or "Does this test point pass?"

        dialog = QDialog(self)
        dialog.setWindowTitle("Pass/Fail Test")
        dialog.setModal(True)
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)

        # Operational check name (if set)
        if operational_check:
            check_label = QLabel(operational_check)
            check_label.setStyleSheet("font-size: 18px; font-weight: bold;")
            check_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(check_label)
            layout.addSpacing(5)

        # Calibrator info (if used)
        if cal_info:
            cal_label = QLabel(f"Calibrator: {cal_info}")
            cal_label.setStyleSheet("color: #666;")
            layout.addWidget(cal_label)

        # Wiring diagram inline (smaller, if available)
        if wiring_image or wiring_image_path:
            image_label = QLabel()
            pixmap = None

            # Try file path first, then BLOB
            if wiring_image_path:
                pixmap = QPixmap(wiring_image_path)
                if pixmap.isNull():
                    pixmap = None
            if pixmap is None and wiring_image:
                pixmap = QPixmap()
                pixmap.loadFromData(wiring_image)

            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(300, 200, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                image_label.setPixmap(scaled)
                image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(image_label)

        layout.addSpacing(10)

        # DMM Reading (if taken)
        if dmm_reading_str:
            reading_group = QGroupBox("DMM Reading")
            reading_layout = QVBoxLayout(reading_group)

            reading_label = QLabel(dmm_reading_str)
            reading_label.setStyleSheet("font-size: 20px; font-weight: bold;")
            reading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            reading_layout.addWidget(reading_label)

            # Range check result
            if has_min or has_max:
                range_str = ""
                if has_min and has_max:
                    range_str = f"Expected: {min_val} to {max_val} {range_unit}"
                elif has_min:
                    range_str = f"Minimum: {min_val} {range_unit}"
                else:
                    range_str = f"Maximum: {max_val} {range_unit}"

                range_label = QLabel(range_str)
                range_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                reading_layout.addWidget(range_label)

                if range_result == "in_range":
                    result_label = QLabel("✓ IN RANGE")
                    result_label.setStyleSheet("color: #28a745; font-weight: bold; font-size: 14px;")
                elif range_result == "out_of_range":
                    result_label = QLabel("✗ OUT OF RANGE")
                    result_label.setStyleSheet("color: #dc3545; font-weight: bold; font-size: 14px;")
                else:
                    result_label = QLabel("? Could not check")
                    result_label.setStyleSheet("color: #ffc107; font-weight: bold;")
                result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                reading_layout.addWidget(result_label)

            layout.addWidget(reading_group)

        layout.addSpacing(10)

        # Prompt
        prompt_label = QLabel(prompt)
        prompt_label.setStyleSheet("font-size: 16px;")
        prompt_label.setWordWrap(True)
        prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(prompt_label)

        layout.addSpacing(20)

        # Pass/Fail buttons
        btn_layout = QHBoxLayout()

        fail_btn = QPushButton("FAIL")
        fail_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 40px;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #c82333; }
        """)
        fail_btn.clicked.connect(lambda: dialog.done(0))
        btn_layout.addWidget(fail_btn)

        btn_layout.addSpacing(20)

        # Suggest PASS if in range
        pass_text = "PASS"
        if range_result == "in_range":
            pass_text = "PASS (Recommended)"

        pass_btn = QPushButton(pass_text)
        pass_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 40px;
                border-radius: 5px;
            }
            QPushButton:hover { background-color: #218838; }
        """)
        pass_btn.clicked.connect(lambda: dialog.done(1))
        btn_layout.addWidget(pass_btn)

        layout.addLayout(btn_layout)

        result = dialog.exec()

        # ========== STEP 5: Cleanup ==========
        # Put calibrator in standby
        if cal_address:
            standby_cmd = self._get_calibrator_command("STBY") or "STBY"
            visa.write(cal_address, standby_cmd)

        # Show result
        result_str = "PASS" if result == 1 else "FAIL"
        summary = f"Result: {result_str}"
        if cal_info:
            summary += "\nCalibrator is now in standby."

        QMessageBox.information(self, "Test Complete", summary)

    def _substitute_pre_placeholders(self, command: str) -> str:
        """Substitute placeholders using pre-conditioning values."""
        if not command:
            return ""

        value = self.pre_nominal_input.value()
        unit = self.pre_unit_combo.currentText()
        frequency = self.pre_frequency_input.value()
        freq_unit = self.pre_freq_unit_combo.currentText()

        freq_hz = frequency
        if freq_unit == "kHz":
            freq_hz = frequency * 1000
        elif freq_unit == "MHz":
            freq_hz = frequency * 1000000

        result = command

        # Auto-append frequency for AC
        has_freq_placeholder = "{freq" in command or "{frequency}" in command
        if freq_hz > 0 and not has_freq_placeholder:
            result = result + ",{freq_hz} HZ"

        result = result.replace("{value}", str(value))
        result = result.replace("{unit}", unit)
        result = result.replace("{frequency}", str(frequency) if frequency > 0 else "")
        result = result.replace("{freq_unit}", freq_unit if frequency > 0 else "")
        result = result.replace("{freq_hz}", str(int(freq_hz)) if freq_hz > 0 else "")

        return result

    def _on_standby(self):
        """Put calibrator in standby mode."""
        if not PYVISA_AVAILABLE:
            return

        if not self._selected_calibrator:
            QMessageBox.warning(self, "No Calibrator", "No calibrator selected. Use 'Test Output' first.")
            return

        address = self._get_calibrator_address()
        if not address:
            QMessageBox.warning(self, "No Calibrator", "No calibrator address found.")
            return

        # Get standby command - check form, then command bank, then default
        standby_cmd = self._get_calibrator_command("STBY") or \
                      self._get_calibrator_command("STANDBY") or \
                      "STBY"

        logger.info(f"Sending standby to {address}: {standby_cmd}")

        visa = get_visa_manager()
        if visa.write(address, standby_cmd):
            cal_info = f"{self._selected_calibrator['make']} {self._selected_calibrator['model']}"
            QMessageBox.information(self, "Standby", f"Calibrator ({cal_info}) is now in standby mode.")
        else:
            QMessageBox.warning(self, "Standby Failed", "Failed to send standby command.")

    def _on_change_calibrator(self):
        """Allow user to change the selected calibrator."""
        if not PYVISA_AVAILABLE:
            QMessageBox.warning(
                self, "PyVISA Not Available",
                "PyVISA is not installed. Cannot communicate with instruments."
            )
            return

        # Force reselection by clearing cache first
        old_cal = self._selected_calibrator
        self._selected_calibrator = None
        self._selected_calibrator_commands = None

        # Detect and select
        calibrator = self._select_calibrator(force_reselect=True)

        if not calibrator and old_cal:
            # User cancelled, restore old selection
            self._selected_calibrator = old_cal
            self._load_calibrator_commands()
            logger.info("Calibrator change cancelled, restored previous selection")
