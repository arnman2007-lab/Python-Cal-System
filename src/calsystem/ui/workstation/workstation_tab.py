"""
Workstation and Standards management tab with inline Command Bank.
"""

from typing import List, Optional, Dict

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QLineEdit,
    QFormLayout,
    QSplitter,
    QMessageBox,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QInputDialog,
    QTabWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from loguru import logger

from calsystem.instruments.visa_manager import (
    get_visa_manager,
    PYVISA_AVAILABLE,
)
from calsystem.database.connection import get_db
from calsystem.database.models import (
    Standard, WorkstationConfig, WorkstationStandard, DeviceGroupType,
    CommandBank, CommandReference, DEFAULT_COMMAND_REFERENCES,
)
from calsystem.config.settings import get_settings


class AddressScanWorker(QThread):
    """Worker thread for VISA address scanning."""

    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def run(self):
        try:
            visa_manager = get_visa_manager()
            all_addresses = visa_manager.scan()
            self.finished.emit(all_addresses)
        except Exception as e:
            logger.error(f"Scan worker error: {e}")
            self.error.emit(str(e))


class WorkstationTab(QWidget):
    """Tab for managing workstation standards with inline command bank."""

    def __init__(self):
        super().__init__()
        self._scan_worker: AddressScanWorker | None = None
        self._all_standards: List[dict] = []
        self._scanned_addresses: List[str] = []
        self._selected_standard_id: Optional[int] = None
        self._updating_ui = False
        self._command_references: List[dict] = []
        self._current_commands: Dict[str, str] = {}
        self._init_ui()

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_command_references()
        self._load_command_references()
        self._load_all_standards()

    def _ensure_command_references(self):
        """Ensure default command references exist in database."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                existing = session.query(CommandReference).count()
                if existing == 0:
                    # Seed default references
                    for ref in DEFAULT_COMMAND_REFERENCES:
                        cmd_ref = CommandReference(
                            name=ref["name"],
                            description=ref["description"],
                            default_command=ref["default_command"],
                            category=ref.get("category"),
                            is_builtin=True,
                        )
                        session.add(cmd_ref)
                    logger.info(f"Seeded {len(DEFAULT_COMMAND_REFERENCES)} command references")
        except Exception as e:
            logger.error(f"Failed to seed command references: {e}")

    def _load_command_references(self):
        """Load all command references from database."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                refs = session.query(CommandReference).order_by(
                    CommandReference.category, CommandReference.name
                ).all()

                self._command_references = []
                for ref in refs:
                    self._command_references.append({
                        "id": ref.id,
                        "name": ref.name,
                        "description": ref.description or "",
                        "default_command": ref.default_command or "",
                        "category": ref.category or "",
                        "is_builtin": ref.is_builtin,
                    })

                self._populate_reference_combo()
        except Exception as e:
            logger.error(f"Failed to load command references: {e}")

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Main content - Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - Available Standards list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        standards_label = QLabel("Available Standards")
        standards_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        left_layout.addWidget(standards_label)

        # Filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self.group_filter = QComboBox()
        self.group_filter.addItems(["All", "Calibrator", "DMM", "Counter", "Other"])
        self.group_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.group_filter)
        filter_layout.addStretch()
        left_layout.addLayout(filter_layout)

        # Standards list with checkboxes
        self.standards_list = QListWidget()
        self.standards_list.itemClicked.connect(self._on_standard_selected)
        self.standards_list.itemChanged.connect(self._on_standard_checked)
        left_layout.addWidget(self.standards_list)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        self.add_standard_btn = QPushButton("Add New...")
        self.add_standard_btn.clicked.connect(self._on_add_standard)
        btn_layout.addWidget(self.add_standard_btn)

        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self._on_scan)
        btn_layout.addWidget(self.scan_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._on_refresh)
        btn_layout.addWidget(self.refresh_btn)

        left_layout.addLayout(btn_layout)
        splitter.addWidget(left_widget)

        # Right side - Tabbed interface for Standard Details and Command Bank
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Title for selected standard
        self.detail_title = QLabel("Select a standard")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self.detail_title.setFont(title_font)
        right_layout.addWidget(self.detail_title)

        # Tab widget for Details and Command Bank
        self.tab_widget = QTabWidget()

        # Tab 1: Standard Details
        details_tab = QWidget()
        details_layout = QVBoxLayout(details_tab)

        # Form fields
        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.make_input = QLineEdit()
        self.make_input.setPlaceholderText("e.g., Fluke, Keysight, HP")
        form_layout.addRow("Make:", self.make_input)

        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("e.g., 5700A, 3458A")
        form_layout.addRow("Model:", self.model_input)

        self.serial_input = QLineEdit()
        self.serial_input.setPlaceholderText("Serial number")
        form_layout.addRow("Serial:", self.serial_input)

        self.std_id_input = QLineEdit()
        self.std_id_input.setPlaceholderText("e.g., CAL-001")
        form_layout.addRow("STD ID:", self.std_id_input)

        self.group_combo = QComboBox()
        self.group_combo.addItems(["Calibrator", "DMM", "Counter", "Other"])
        form_layout.addRow("Group:", self.group_combo)

        self.address_combo = QComboBox()
        self.address_combo.setEditable(True)
        self.address_combo.setMinimumWidth(200)
        self.address_combo.setPlaceholderText("Select or enter address")
        form_layout.addRow("Address:", self.address_combo)

        self.status_label = QLabel("--")
        self.status_label.setStyleSheet("font-weight: bold;")
        form_layout.addRow("Status:", self.status_label)

        details_layout.addLayout(form_layout)
        details_layout.addStretch()

        # Save/Remove buttons
        btn_layout2 = QHBoxLayout()
        self.save_btn = QPushButton("Save Changes")
        self.save_btn.clicked.connect(self._on_save_standard)
        self.save_btn.setEnabled(False)
        btn_layout2.addWidget(self.save_btn)

        self.remove_btn = QPushButton("Remove from Database")
        self.remove_btn.clicked.connect(self._on_remove_standard)
        self.remove_btn.setEnabled(False)
        self.remove_btn.setStyleSheet("background-color: #ffcccc;")
        btn_layout2.addWidget(self.remove_btn)
        details_layout.addLayout(btn_layout2)

        self.tab_widget.addTab(details_tab, "Details")

        # Tab 2: Command Bank
        cmd_tab = QWidget()
        cmd_layout = QVBoxLayout(cmd_tab)

        # Help text
        help_label = QLabel(
            "Map generic command references to this model's actual SCPI commands.\n"
            "Use {value}, {unit}, {frequency}, {freq_unit} as placeholders."
        )
        help_label.setStyleSheet("color: gray; font-size: 11px;")
        help_label.setWordWrap(True)
        cmd_layout.addWidget(help_label)

        # Reference management row
        ref_layout = QHBoxLayout()
        ref_layout.addWidget(QLabel("References:"))
        self.ref_combo = QComboBox()
        self.ref_combo.setMinimumWidth(150)
        ref_layout.addWidget(self.ref_combo)

        self.add_ref_btn = QPushButton("Add New Reference...")
        self.add_ref_btn.clicked.connect(self._on_add_reference)
        ref_layout.addWidget(self.add_ref_btn)

        self.add_mapping_btn = QPushButton("Add to Mappings")
        self.add_mapping_btn.clicked.connect(self._on_add_mapping)
        ref_layout.addWidget(self.add_mapping_btn)

        ref_layout.addStretch()
        cmd_layout.addLayout(ref_layout)

        # Command mappings table
        self.cmd_table = QTableWidget()
        self.cmd_table.setColumnCount(3)
        self.cmd_table.setHorizontalHeaderLabels(["Reference", "SCPI Command", "Description"])
        self.cmd_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.cmd_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.cmd_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.cmd_table.cellChanged.connect(self._on_cmd_cell_changed)
        cmd_layout.addWidget(self.cmd_table)

        # Command bank buttons
        cmd_btn_layout = QHBoxLayout()

        self.populate_defaults_btn = QPushButton("Add All References")
        self.populate_defaults_btn.clicked.connect(self._on_populate_defaults)
        cmd_btn_layout.addWidget(self.populate_defaults_btn)

        self.remove_cmd_btn = QPushButton("Remove Selected")
        self.remove_cmd_btn.clicked.connect(self._on_remove_command)
        cmd_btn_layout.addWidget(self.remove_cmd_btn)

        cmd_btn_layout.addStretch()

        self.save_cmd_btn = QPushButton("Save Command Bank")
        self.save_cmd_btn.clicked.connect(self._on_save_command_bank)
        self.save_cmd_btn.setStyleSheet("font-weight: bold;")
        cmd_btn_layout.addWidget(self.save_cmd_btn)

        cmd_layout.addLayout(cmd_btn_layout)

        self.tab_widget.addTab(cmd_tab, "Command Bank")

        right_layout.addWidget(self.tab_widget)
        splitter.addWidget(right_widget)

        # Set splitter sizes
        splitter.setSizes([280, 520])
        layout.addWidget(splitter)

        # Connect input changes
        self.make_input.textChanged.connect(self._on_detail_changed)
        self.model_input.textChanged.connect(self._on_detail_changed)
        self.serial_input.textChanged.connect(self._on_detail_changed)
        self.std_id_input.textChanged.connect(self._on_detail_changed)
        self.group_combo.currentTextChanged.connect(self._on_detail_changed)
        self.address_combo.currentTextChanged.connect(self._on_detail_changed)

    def _populate_reference_combo(self):
        """Populate the reference dropdown."""
        self.ref_combo.clear()
        for ref in self._command_references:
            display = f"{ref['name']} - {ref['description'][:30]}..." if len(ref['description']) > 30 else f"{ref['name']} - {ref['description']}"
            self.ref_combo.addItem(display, ref['name'])

    def _on_add_reference(self):
        """Add a new command reference."""
        name, ok = QInputDialog.getText(
            self, "Add Reference", "Enter reference name (e.g., 'Source', 'Measure'):"
        )
        if not ok or not name.strip():
            return

        name = name.strip()

        # Check if exists
        for ref in self._command_references:
            if ref["name"].lower() == name.lower():
                QMessageBox.warning(self, "Exists", f"Reference '{name}' already exists.")
                return

        desc, ok = QInputDialog.getText(
            self, "Description", "Enter a description for this reference:"
        )
        if not ok:
            desc = ""

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                cmd_ref = CommandReference(
                    name=name,
                    description=desc.strip(),
                    is_builtin=False,
                )
                session.add(cmd_ref)
                logger.info(f"Added command reference: {name}")

            self._load_command_references()
            QMessageBox.information(self, "Added", f"Reference '{name}' added.")

        except Exception as e:
            logger.error(f"Failed to add reference: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add:\n{e}")

    def _on_add_mapping(self):
        """Add selected reference to the command mappings table."""
        ref_name = self.ref_combo.currentData()
        if not ref_name:
            return

        # Check if already in table
        for row in range(self.cmd_table.rowCount()):
            item = self.cmd_table.item(row, 0)
            if item and item.text() == ref_name:
                QMessageBox.information(self, "Exists", f"'{ref_name}' is already in the mappings.")
                return

        # Find reference details
        ref_data = None
        for ref in self._command_references:
            if ref["name"] == ref_name:
                ref_data = ref
                break

        if not ref_data:
            return

        # Add row
        self._updating_ui = True
        row = self.cmd_table.rowCount()
        self.cmd_table.insertRow(row)

        name_item = QTableWidgetItem(ref_name)
        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.cmd_table.setItem(row, 0, name_item)

        self.cmd_table.setItem(row, 1, QTableWidgetItem(ref_data["default_command"]))

        desc_item = QTableWidgetItem(ref_data["description"])
        desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        desc_item.setForeground(QColor(128, 128, 128))
        self.cmd_table.setItem(row, 2, desc_item)

        self._updating_ui = False

    def _on_populate_defaults(self):
        """Add all references to the mappings table."""
        for ref in self._command_references:
            ref_name = ref["name"]

            # Check if already exists
            exists = False
            for row in range(self.cmd_table.rowCount()):
                item = self.cmd_table.item(row, 0)
                if item and item.text() == ref_name:
                    exists = True
                    break

            if not exists:
                self._updating_ui = True
                row = self.cmd_table.rowCount()
                self.cmd_table.insertRow(row)

                name_item = QTableWidgetItem(ref_name)
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.cmd_table.setItem(row, 0, name_item)

                self.cmd_table.setItem(row, 1, QTableWidgetItem(ref["default_command"]))

                desc_item = QTableWidgetItem(ref["description"])
                desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                desc_item.setForeground(QColor(128, 128, 128))
                self.cmd_table.setItem(row, 2, desc_item)

                self._updating_ui = False

    def _on_remove_command(self):
        """Remove selected command mapping."""
        selected = self.cmd_table.selectedItems()
        if selected:
            self.cmd_table.removeRow(selected[0].row())

    def _on_cmd_cell_changed(self, row: int, col: int):
        """Handle cell changes in command table."""
        pass  # Could track dirty state here

    def _on_save_command_bank(self):
        """Save the command bank for the current model."""
        make = self.make_input.text().strip()
        model = self.model_input.text().strip()

        if not make or not model:
            QMessageBox.warning(self, "Error", "Please select a standard with Make and Model first.")
            return

        # Collect commands
        commands = {}
        for row in range(self.cmd_table.rowCount()):
            ref_item = self.cmd_table.item(row, 0)
            cmd_item = self.cmd_table.item(row, 1)
            if ref_item and cmd_item:
                ref_name = ref_item.text().strip()
                scpi_cmd = cmd_item.text().strip()
                if ref_name and scpi_cmd:
                    commands[ref_name] = scpi_cmd

        if not commands:
            QMessageBox.warning(self, "Empty", "No command mappings to save.")
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                # Find or create command bank
                bank = session.query(CommandBank).filter(
                    CommandBank.make == make,
                    CommandBank.model == model,
                ).first()

                if not bank:
                    bank = CommandBank(make=make, model=model)
                    session.add(bank)

                # Get device type from group
                group_map = {0: "calibrator", 1: "dmm", 2: "counter", 3: "other"}
                bank.device_type = group_map.get(self.group_combo.currentIndex(), "other")
                bank.commands = commands

                logger.info(f"Saved command bank for {make} {model} with {len(commands)} mappings")

            # Update local standards data
            for std in self._all_standards:
                if std["id"] == self._selected_standard_id:
                    std["has_command_bank"] = True
                    break

            self._populate_standards_list()
            QMessageBox.information(
                self, "Saved",
                f"Command bank for {make} {model} saved with {len(commands)} mappings."
            )

        except Exception as e:
            logger.error(f"Failed to save command bank: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

    def _load_command_bank_for_model(self, make: str, model: str):
        """Load command bank for a specific model into the table."""
        self._updating_ui = True
        self.cmd_table.setRowCount(0)

        if not make or not model:
            self._updating_ui = False
            return

        db = get_db()
        if not db.is_connected:
            self._updating_ui = False
            return

        try:
            with db.session() as session:
                bank = session.query(CommandBank).filter(
                    CommandBank.make == make,
                    CommandBank.model == model,
                ).first()

                if bank and bank.commands:
                    for ref_name, scpi_cmd in bank.commands.items():
                        row = self.cmd_table.rowCount()
                        self.cmd_table.insertRow(row)

                        name_item = QTableWidgetItem(ref_name)
                        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.cmd_table.setItem(row, 0, name_item)

                        self.cmd_table.setItem(row, 1, QTableWidgetItem(scpi_cmd))

                        # Find description
                        desc = ""
                        for ref in self._command_references:
                            if ref["name"] == ref_name:
                                desc = ref["description"]
                                break

                        desc_item = QTableWidgetItem(desc)
                        desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        desc_item.setForeground(QColor(128, 128, 128))
                        self.cmd_table.setItem(row, 2, desc_item)

        except Exception as e:
            logger.error(f"Failed to load command bank: {e}")

        self._updating_ui = False

    def _on_detail_changed(self):
        """Enable save button when details change."""
        if self._selected_standard_id and not self._updating_ui:
            self.save_btn.setEnabled(True)

    def _on_scan(self):
        """Scan for connected instruments."""
        if not PYVISA_AVAILABLE:
            QMessageBox.warning(
                self, "PyVISA Not Available",
                "PyVISA is not installed.\nInstall with: pip install pyvisa",
            )
            return

        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning...")

        self._scan_worker = AddressScanWorker()
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_finished(self, addresses: List[str]):
        """Handle scan completion."""
        self._scanned_addresses = addresses
        current_text = self.address_combo.currentText()
        self.address_combo.clear()
        self.address_combo.addItems(addresses)
        if current_text:
            idx = self.address_combo.findText(current_text)
            if idx >= 0:
                self.address_combo.setCurrentIndex(idx)
            else:
                self.address_combo.setEditText(current_text)

        self.scan_btn.setEnabled(True)
        self.scan_btn.setText(f"Scan ({len(addresses)})")

    def _on_scan_error(self, error_msg: str):
        """Handle scan error."""
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan")
        QMessageBox.warning(self, "Scan Failed", f"Failed to scan:\n{error_msg}")

    def _on_refresh(self):
        """Refresh standards list."""
        self._load_all_standards()

    def _load_all_standards(self):
        """Load all standards from database."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                settings = get_settings()
                workstation_name = settings.workstation_name or "Default Workstation"

                workstation = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == workstation_name
                ).first()

                workstation_standard_ids = set()
                ws_standard_map = {}
                if workstation:
                    ws_standards = session.query(WorkstationStandard).filter(
                        WorkstationStandard.workstation_id == workstation.id
                    ).all()
                    for ws in ws_standards:
                        workstation_standard_ids.add(ws.standard_id)
                        ws_standard_map[ws.standard_id] = {
                            "address": ws.visa_address,
                            "is_active": ws.is_active if ws.is_active is not None else True,
                        }

                standards = session.query(Standard).order_by(
                    Standard.device_group, Standard.make, Standard.model
                ).all()

                command_banks = session.query(CommandBank.make, CommandBank.model).all()
                cb_set = {(cb.make.lower(), cb.model.lower()) for cb in command_banks}

                self._all_standards = []
                for std in standards:
                    has_command_bank = (std.make.lower(), std.model.lower()) in cb_set
                    ws_data = ws_standard_map.get(std.id, {})

                    self._all_standards.append({
                        "id": std.id,
                        "make": std.make,
                        "model": std.model,
                        "serial": std.serial_number or "",
                        "std_id": std.std_id or "",
                        "group": std.device_group.value if std.device_group else "other",
                        "address": ws_data.get("address") or std.visa_address or "",
                        "in_workstation": std.id in workstation_standard_ids,
                        "has_command_bank": has_command_bank,
                    })

                self._populate_standards_list()

        except Exception as e:
            logger.error(f"Failed to load standards: {e}")

    def _populate_standards_list(self):
        """Populate the standards list with checkboxes."""
        self._updating_ui = True
        self.standards_list.clear()

        filter_text = self.group_filter.currentText()

        for std in self._all_standards:
            if filter_text != "All":
                group_map = {"Calibrator": "calibrator", "DMM": "dmm", "Counter": "counter", "Other": "other"}
                if std["group"] != group_map.get(filter_text, ""):
                    continue

            display_text = f"{std['make']} {std['model']}"
            if std['serial']:
                display_text += f" ({std['serial']})"

            # Add command bank indicator
            if std['has_command_bank']:
                display_text += " [CMD]"

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, std["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if std["in_workstation"] else Qt.CheckState.Unchecked)

            if not std["has_command_bank"]:
                item.setToolTip("No command bank configured")

            self.standards_list.addItem(item)

        self._updating_ui = False

    def _on_filter_changed(self, filter_text: str):
        """Handle filter change."""
        self._populate_standards_list()

    def _on_standard_selected(self, item: QListWidgetItem):
        """Handle standard selection - show details."""
        standard_id = item.data(Qt.ItemDataRole.UserRole)
        self._load_standard_details(standard_id)

    def _on_standard_checked(self, item: QListWidgetItem):
        """Handle checkbox state change."""
        if self._updating_ui:
            return

        standard_id = item.data(Qt.ItemDataRole.UserRole)
        is_checked = item.checkState() == Qt.CheckState.Checked

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                settings = get_settings()
                workstation_name = settings.workstation_name or "Default Workstation"

                workstation = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == workstation_name
                ).first()

                if not workstation:
                    workstation = WorkstationConfig(name=workstation_name)
                    session.add(workstation)
                    session.flush()

                ws_standard = session.query(WorkstationStandard).filter(
                    WorkstationStandard.workstation_id == workstation.id,
                    WorkstationStandard.standard_id == standard_id
                ).first()

                if is_checked and not ws_standard:
                    standard = session.query(Standard).get(standard_id)
                    ws_standard = WorkstationStandard(
                        workstation_id=workstation.id,
                        standard_id=standard_id,
                        visa_address=standard.visa_address if standard else None,
                        is_active=True,
                    )
                    session.add(ws_standard)

                    for std in self._all_standards:
                        if std["id"] == standard_id:
                            std["in_workstation"] = True
                            break

                elif not is_checked and ws_standard:
                    session.delete(ws_standard)

                    for std in self._all_standards:
                        if std["id"] == standard_id:
                            std["in_workstation"] = False
                            break

        except Exception as e:
            logger.error(f"Failed to update workstation standard: {e}")

    def _load_standard_details(self, standard_id: int):
        """Load details for selected standard."""
        self._updating_ui = True
        self._selected_standard_id = standard_id

        std_data = None
        for std in self._all_standards:
            if std["id"] == standard_id:
                std_data = std
                break

        if not std_data:
            self._updating_ui = False
            return

        self.detail_title.setText(f"{std_data['make']} {std_data['model']}")

        self.make_input.setText(std_data["make"])
        self.model_input.setText(std_data["model"])
        self.serial_input.setText(std_data["serial"])
        self.std_id_input.setText(std_data["std_id"])

        group_map = {"calibrator": 0, "dmm": 1, "counter": 2, "other": 3}
        self.group_combo.setCurrentIndex(group_map.get(std_data["group"], 3))

        self.address_combo.setEditText(std_data.get("address", ""))

        if std_data["in_workstation"]:
            self.status_label.setText("In Workstation")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText("Not in Workstation")
            self.status_label.setStyleSheet("color: gray; font-weight: bold;")

        self.save_btn.setEnabled(False)
        self.remove_btn.setEnabled(True)

        # Load command bank for this model
        self._load_command_bank_for_model(std_data["make"], std_data["model"])

        self._updating_ui = False

    def _on_save_standard(self):
        """Save changes to the selected standard."""
        if not self._selected_standard_id:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                standard = session.query(Standard).get(self._selected_standard_id)
                if not standard:
                    return

                standard.make = self.make_input.text().strip()
                standard.model = self.model_input.text().strip()
                standard.serial_number = self.serial_input.text().strip() or None
                standard.std_id = self.std_id_input.text().strip() or None

                group_map = {0: "calibrator", 1: "dmm", 2: "counter", 3: "other"}
                group_value = group_map.get(self.group_combo.currentIndex(), "other")
                standard.device_group = DeviceGroupType(group_value)
                standard.visa_address = self.address_combo.currentText().strip() or None

                settings = get_settings()
                workstation_name = settings.workstation_name or "Default Workstation"
                workstation = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == workstation_name
                ).first()

                if workstation:
                    ws_standard = session.query(WorkstationStandard).filter(
                        WorkstationStandard.workstation_id == workstation.id,
                        WorkstationStandard.standard_id == self._selected_standard_id
                    ).first()
                    if ws_standard:
                        ws_standard.visa_address = standard.visa_address

            for std in self._all_standards:
                if std["id"] == self._selected_standard_id:
                    std["make"] = self.make_input.text().strip()
                    std["model"] = self.model_input.text().strip()
                    std["serial"] = self.serial_input.text().strip()
                    std["std_id"] = self.std_id_input.text().strip()
                    std["group"] = group_value
                    std["address"] = self.address_combo.currentText().strip()
                    break

            self._populate_standards_list()
            self.save_btn.setEnabled(False)
            QMessageBox.information(self, "Saved", "Standard updated.")

        except Exception as e:
            logger.error(f"Failed to save standard: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

    def _on_remove_standard(self):
        """Remove selected standard from database."""
        if not self._selected_standard_id:
            return

        reply = QMessageBox.question(
            self, "Remove Standard",
            "Remove this standard from the database?\nThis also removes it from all workstations.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                session.query(WorkstationStandard).filter(
                    WorkstationStandard.standard_id == self._selected_standard_id
                ).delete()

                standard = session.query(Standard).get(self._selected_standard_id)
                if standard:
                    session.delete(standard)

            self._selected_standard_id = None
            self.detail_title.setText("Select a standard")
            self.make_input.clear()
            self.model_input.clear()
            self.serial_input.clear()
            self.std_id_input.clear()
            self.address_combo.setEditText("")
            self.status_label.setText("--")
            self.cmd_table.setRowCount(0)
            self.save_btn.setEnabled(False)
            self.remove_btn.setEnabled(False)

            self._load_all_standards()

        except Exception as e:
            logger.error(f"Failed to remove standard: {e}")
            QMessageBox.critical(self, "Error", f"Failed to remove:\n{e}")

    def _on_add_standard(self):
        """Open dialog to add a new standard."""
        from calsystem.ui.dialogs.add_standard_dialog import AddStandardDialog
        dialog = AddStandardDialog(
            parent=self,
            available_addresses=self._scanned_addresses,
            used_models=[],
        )
        if dialog.exec():
            self._load_all_standards()
