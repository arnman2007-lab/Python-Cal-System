"""
Procedure builder tab.
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
    QTreeWidget,
    QTreeWidgetItem,
    QTextEdit,
    QFormLayout,
    QComboBox,
    QDoubleSpinBox,
    QMessageBox,
    QFileDialog,
)
from PyQt6.QtCore import Qt
from loguru import logger


class ProceduresTab(QWidget):
    """Tab for building and managing calibration procedures."""

    def __init__(self):
        super().__init__()
        self._init_ui()

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

        structure_layout.addLayout(tree_toolbar)

        self.structure_tree = QTreeWidget()
        self.structure_tree.setHeaderLabels(["Section / Test Point", "Value", "Tolerance"])
        self.structure_tree.setColumnCount(3)
        self.structure_tree.itemSelectionChanged.connect(self._on_tree_item_selected)
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

        self.source_cmd_input = QLineEdit()
        self.source_cmd_input.setPlaceholderText("e.g., OUT 1.0V")
        details_layout.addRow("Source:", self.source_cmd_input)

        self.operate_cmd_input = QLineEdit()
        self.operate_cmd_input.setPlaceholderText("e.g., OPER")
        details_layout.addRow("Operate:", self.operate_cmd_input)

        self.measure_cmd_input = QLineEdit()
        self.measure_cmd_input.setPlaceholderText("e.g., MEAS:VOLT:DC?")
        details_layout.addRow("Measure:", self.measure_cmd_input)

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

        main_splitter.addWidget(details_group)

        # Set splitter sizes
        main_splitter.setSizes([250, 350, 300])

        layout.addWidget(main_splitter)

    def _on_new_procedure(self):
        """Create new procedure."""
        logger.info("Creating new procedure")
        self.name_input.clear()
        self.target_make_input.clear()
        self.target_model_input.clear()
        self.structure_tree.clear()
        self.name_input.setFocus()

    def _on_import_excel(self):
        """Import procedure from Excel."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Procedure from Excel",
            "",
            "Excel Files (*.xlsx *.xls);;All Files (*)",
        )
        if file_path:
            logger.info(f"Importing from: {file_path}")
            # TODO: Implement Excel import wizard

    def _on_save(self):
        """Save current procedure."""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation Error", "Procedure name is required.")
            return

        logger.info(f"Saving procedure: {name}")
        # TODO: Save to database

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
        """Handle procedure selection."""
        selected = self.procedure_list.selectedItems()
        if selected:
            row = selected[0].row()
            name = self.procedure_list.item(row, 0).text()
            logger.debug(f"Selected procedure: {name}")
            # TODO: Load procedure

    def _on_add_section(self):
        """Add a new section."""
        section_item = QTreeWidgetItem(self.structure_tree)
        section_item.setText(0, "New Section")
        section_item.setFlags(
            section_item.flags() | Qt.ItemFlag.ItemIsEditable
        )
        self.structure_tree.setCurrentItem(section_item)
        self.structure_tree.editItem(section_item, 0)
        logger.debug("Added new section")

    def _on_add_testpoint(self):
        """Add a new test point."""
        current = self.structure_tree.currentItem()

        # If no selection or selected is a test point, add to root
        parent = current if current and current.parent() is None else None

        if parent is None and current is not None:
            parent = current.parent()

        if parent is None:
            QMessageBox.warning(
                self,
                "No Section",
                "Please select a section first, or create one.",
            )
            return

        testpoint_item = QTreeWidgetItem(parent)
        testpoint_item.setText(0, "New Test Point")
        testpoint_item.setText(1, "0 V")
        testpoint_item.setText(2, "±0.1%")
        self.structure_tree.setCurrentItem(testpoint_item)
        logger.debug("Added new test point")

    def _on_tree_item_selected(self):
        """Handle tree item selection."""
        current = self.structure_tree.currentItem()
        if current:
            logger.debug(f"Selected: {current.text(0)}")
            # TODO: Load item details into form

    def _on_move_up(self):
        """Move selected item up."""
        logger.debug("Moving item up")
        # TODO: Implement move up

    def _on_move_down(self):
        """Move selected item down."""
        logger.debug("Moving item down")
        # TODO: Implement move down

    def _on_add_wiring(self):
        """Add wiring diagram image."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Wiring Diagram",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*)",
        )
        if file_path:
            logger.info(f"Adding wiring diagram: {file_path}")
            # TODO: Save wiring diagram
