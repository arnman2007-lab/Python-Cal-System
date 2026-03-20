"""
Procedure builder tab.
"""

from typing import Optional

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
    QTreeWidget,
    QTreeWidgetItem,
    QTextEdit,
    QFormLayout,
    QComboBox,
    QDoubleSpinBox,
    QMessageBox,
    QFileDialog,
    QDialog,
)
from PyQt6.QtCore import Qt
from loguru import logger

from calsystem.database.connection import get_db
from calsystem.database.models import Procedure, TestSection, TestPoint, CommandBank, ToleranceType, WiringDiagram
from calsystem.ui.dialogs.excel_import_dialog import ExcelImportDialog


class ProceduresTab(QWidget):
    """Tab for building and managing calibration procedures."""

    def __init__(self):
        super().__init__()
        self._current_procedure_id: Optional[int] = None
        self._init_ui()

    def showEvent(self, event):
        """Called when tab becomes visible."""
        super().showEvent(event)
        self._refresh_procedure_list()

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

        # Right - Test point details
        details_group = QGroupBox("Test Point Details")
        details_layout = QFormLayout(details_group)

        self.test_type_combo = QComboBox()
        self.test_type_combo.addItems(["Measurement", "Pass/Fail", "Calculated"])
        details_layout.addRow("Test Type:", self.test_type_combo)

        value_layout = QHBoxLayout()
        self.nominal_input = QDoubleSpinBox()
        self.nominal_input.setRange(-999999999, 999999999)
        self.nominal_input.setDecimals(6)
        value_layout.addWidget(self.nominal_input)

        self.unit_combo = QComboBox()
        self.unit_combo.setEditable(True)
        self.unit_combo.addItems(["V", "mV", "A", "mA", "Ohm", "Hz", "kHz", "MHz"])
        value_layout.addWidget(self.unit_combo)
        details_layout.addRow("Nominal:", value_layout)

        freq_layout = QHBoxLayout()
        self.frequency_input = QDoubleSpinBox()
        self.frequency_input.setRange(0, 999999999)
        self.frequency_input.setDecimals(3)
        freq_layout.addWidget(self.frequency_input)

        self.freq_unit_combo = QComboBox()
        self.freq_unit_combo.addItems(["Hz", "kHz", "MHz"])
        freq_layout.addWidget(self.freq_unit_combo)
        details_layout.addRow("Frequency:", freq_layout)

        tol_layout = QHBoxLayout()
        self.tolerance_input = QDoubleSpinBox()
        self.tolerance_input.setRange(0, 999999)
        self.tolerance_input.setDecimals(6)
        tol_layout.addWidget(self.tolerance_input)

        self.tolerance_type_combo = QComboBox()
        self.tolerance_type_combo.addItems(["%", "Absolute", "PPM"])
        tol_layout.addWidget(self.tolerance_type_combo)
        details_layout.addRow("Tolerance:", tol_layout)

        # Commands section
        details_layout.addRow(QLabel(""))  # Spacer
        details_layout.addRow(QLabel("Commands:"))

        # Command bank template selector
        template_layout = QHBoxLayout()
        self.cmd_template_combo = QComboBox()
        self.cmd_template_combo.addItem("-- Select Template --", None)
        self.cmd_template_combo.currentIndexChanged.connect(self._on_template_selected)
        template_layout.addWidget(self.cmd_template_combo)
        self.load_templates_btn = QPushButton("Refresh")
        self.load_templates_btn.clicked.connect(self._load_command_templates)
        template_layout.addWidget(self.load_templates_btn)
        details_layout.addRow("Template:", template_layout)

        self.source_cmd_input = QLineEdit()
        self.source_cmd_input.setPlaceholderText("e.g., OUT {value}{unit}")
        details_layout.addRow("Source:", self.source_cmd_input)

        self.operate_cmd_input = QLineEdit()
        self.operate_cmd_input.setPlaceholderText("e.g., OPER")
        details_layout.addRow("Operate:", self.operate_cmd_input)

        self.measure_cmd_input = QLineEdit()
        self.measure_cmd_input.setPlaceholderText("e.g., MEAS:VOLT:DC?")
        details_layout.addRow("Measure:", self.measure_cmd_input)

        # Placeholder help text
        placeholder_help = QLabel("Use {value}, {unit}, {frequency} as placeholders")
        placeholder_help.setStyleSheet("color: gray; font-size: 10px;")
        details_layout.addRow("", placeholder_help)

        # Excel mapping
        details_layout.addRow(QLabel(""))  # Spacer
        details_layout.addRow(QLabel("Excel Export Mapping:"))

        self.excel_sheet_input = QLineEdit()
        details_layout.addRow("Sheet:", self.excel_sheet_input)

        self.excel_cell_input = QLineEdit()
        self.excel_cell_input.setPlaceholderText("e.g., B15")
        details_layout.addRow("Cell:", self.excel_cell_input)

        # Wiring diagram
        details_layout.addRow(QLabel(""))  # Spacer

        wiring_layout = QHBoxLayout()
        self.wiring_btn = QPushButton("Add Wiring Diagram...")
        self.wiring_btn.clicked.connect(self._on_add_wiring)
        wiring_layout.addWidget(self.wiring_btn)
        wiring_layout.addStretch()
        details_layout.addRow("Wiring:", wiring_layout)

        # Save test point button
        details_layout.addRow(QLabel(""))  # Spacer
        self.save_tp_btn = QPushButton("Save Test Point")
        self.save_tp_btn.clicked.connect(self._save_current_testpoint)
        details_layout.addRow("", self.save_tp_btn)

        main_splitter.addWidget(details_group)

        # Set splitter sizes
        main_splitter.setSizes([250, 350, 300])

        layout.addWidget(main_splitter)

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
        self.nominal_input.setValue(0)
        self.unit_combo.setCurrentIndex(0)
        self.frequency_input.setValue(0)
        self.tolerance_input.setValue(0)
        self.cmd_template_combo.setCurrentIndex(0)
        self.source_cmd_input.clear()
        self.operate_cmd_input.clear()
        self.measure_cmd_input.clear()
        self.excel_sheet_input.clear()
        self.excel_cell_input.clear()

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
            QMessageBox.information(self, "Saved", f"Procedure '{name}' saved successfully.")
            self._refresh_procedure_list()

        except Exception as e:
            logger.error(f"Failed to save procedure: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

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

                # Load sections and test points into tree
                self.structure_tree.clear()
                for section in procedure.sections:
                    section_item = QTreeWidgetItem(self.structure_tree)
                    section_item.setText(0, section.name)
                    section_item.setData(0, Qt.ItemDataRole.UserRole, ("section", section.id))
                    section_item.setFlags(section_item.flags() | Qt.ItemFlag.ItemIsEditable)

                    for tp in section.test_points:
                        tp_item = QTreeWidgetItem(section_item)
                        tp_item.setText(0, tp.description or f"{tp.nominal_value} {tp.unit}")
                        tp_item.setText(1, f"{tp.nominal_value or 0} {tp.unit or ''}")
                        tp_item.setText(2, f"±{tp.tolerance_value or 0}{tp.tolerance_type.value if tp.tolerance_type else '%'}")
                        tp_item.setData(0, Qt.ItemDataRole.UserRole, ("testpoint", tp.id))

                self.structure_tree.expandAll()
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
                    name="New Section",
                    order=max_order,
                )
                session.add(section)
                session.flush()

                # Add to tree
                section_item = QTreeWidgetItem(self.structure_tree)
                section_item.setText(0, section.name)
                section_item.setData(0, Qt.ItemDataRole.UserRole, ("section", section.id))
                section_item.setFlags(section_item.flags() | Qt.ItemFlag.ItemIsEditable)
                self.structure_tree.setCurrentItem(section_item)
                self.structure_tree.editItem(section_item, 0)

                logger.debug(f"Added new section: {section.id}")

        except Exception as e:
            logger.error(f"Failed to add section: {e}")

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

    def _on_tree_item_selected(self):
        """Handle tree item selection - loads details into form."""
        current = self.structure_tree.currentItem()
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data

        if item_type == "testpoint":
            self._load_testpoint_details(item_id)

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
                type_map = {"measurement": 0, "pass_fail": 1, "calculated": 2}
                self.test_type_combo.setCurrentIndex(
                    type_map.get(tp.test_type.value if tp.test_type else "measurement", 0)
                )

                # Nominal value and unit
                self.nominal_input.setValue(tp.nominal_value or 0)
                idx = self.unit_combo.findText(tp.unit or "V")
                if idx >= 0:
                    self.unit_combo.setCurrentIndex(idx)
                else:
                    self.unit_combo.setCurrentText(tp.unit or "V")

                # Frequency
                self.frequency_input.setValue(tp.frequency or 0)

                # Tolerance
                self.tolerance_input.setValue(tp.tolerance_value or 0)
                tol_map = {"percent": 0, "absolute": 1, "ppm": 2}
                self.tolerance_type_combo.setCurrentIndex(
                    tol_map.get(tp.tolerance_type.value if tp.tolerance_type else "percent", 0)
                )

                # Commands
                self.source_cmd_input.setText(tp.source_command or "")
                self.operate_cmd_input.setText(tp.operate_command or "")
                self.measure_cmd_input.setText(tp.measure_command or "")

                # Excel mapping
                self.excel_sheet_input.setText(tp.excel_sheet or "")
                self.excel_cell_input.setText(tp.excel_cell or "")

                logger.debug(f"Loaded test point: {tp_id}")

        except Exception as e:
            logger.error(f"Failed to load test point: {e}")

    def _save_current_testpoint(self):
        """Save the current test point from form to database."""
        current = self.structure_tree.currentItem()
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data or data[0] != "testpoint":
            return

        tp_id = data[1]

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                tp = session.query(TestPoint).filter(TestPoint.id == tp_id).first()
                if not tp:
                    return

                # Update from form
                type_map = {0: "measurement", 1: "pass_fail", 2: "calculated"}
                from calsystem.database.models import TestPointType, ToleranceType
                tp.test_type = TestPointType(type_map[self.test_type_combo.currentIndex()])

                tp.nominal_value = self.nominal_input.value()
                tp.unit = self.unit_combo.currentText()
                tp.frequency = self.frequency_input.value() if self.frequency_input.value() > 0 else None

                tp.tolerance_value = self.tolerance_input.value()
                tol_map = {0: "percent", 1: "absolute", 2: "ppm"}
                tp.tolerance_type = ToleranceType(tol_map[self.tolerance_type_combo.currentIndex()])

                tp.source_command = self.source_cmd_input.text().strip() or None
                tp.operate_command = self.operate_cmd_input.text().strip() or None
                tp.measure_command = self.measure_cmd_input.text().strip() or None

                tp.excel_sheet = self.excel_sheet_input.text().strip() or None
                tp.excel_cell = self.excel_cell_input.text().strip() or None

                # Update tree display
                current.setText(0, tp.description or f"{tp.nominal_value} {tp.unit}")
                current.setText(1, f"{tp.nominal_value} {tp.unit}")
                current.setText(2, f"±{tp.tolerance_value}{tp.tolerance_type.value}")

                logger.debug(f"Saved test point: {tp_id}")

        except Exception as e:
            logger.error(f"Failed to save test point: {e}")

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
