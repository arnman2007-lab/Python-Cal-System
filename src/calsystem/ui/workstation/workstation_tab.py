"""
Workstation and Standards management tab.
"""

from typing import List

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
    QMenu,
    QListWidget,
    QListWidgetItem,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from loguru import logger

from calsystem.instruments.visa_manager import (
    get_visa_manager,
    PYVISA_AVAILABLE,
)
from calsystem.database.connection import get_db
from calsystem.database.models import Standard, WorkstationConfig, WorkstationStandard, DeviceGroupType, CommandBank
from calsystem.config.settings import get_settings


class AddressScanWorker(QThread):
    """Worker thread for VISA address scanning (no IDN queries)."""

    finished = pyqtSignal(list, list)  # Emits (gpib_addresses, com_addresses)
    error = pyqtSignal(str)

    def run(self):
        """Perform the scan in background thread."""
        try:
            visa_manager = get_visa_manager()
            all_addresses = visa_manager.scan()

            # Separate into GPIB and COM/ASRL
            gpib_addresses = []
            com_addresses = []

            for addr in all_addresses:
                if addr.startswith("GPIB"):
                    gpib_addresses.append(addr)
                elif addr.startswith("ASRL") or addr.startswith("COM"):
                    com_addresses.append(addr)
                else:
                    # Other types (TCPIP, USB, etc.) go to GPIB column for now
                    gpib_addresses.append(addr)

            self.finished.emit(gpib_addresses, com_addresses)
        except Exception as e:
            logger.error(f"Scan worker error: {e}")
            self.error.emit(str(e))


class WorkstationTab(QWidget):
    """Tab for managing workstation standards."""

    def __init__(self):
        super().__init__()
        self._scan_worker: AddressScanWorker | None = None
        self._standards_data: List[dict] = []
        self._gpib_addresses: List[str] = []
        self._com_addresses: List[str] = []
        self._init_ui()

    def showEvent(self, event):
        """Called when tab becomes visible."""
        super().showEvent(event)
        self._load_config_dropdown()
        self._refresh_standards_table()

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
        self.save_config_btn.clicked.connect(self._on_save_config)
        workstation_layout.addWidget(self.save_config_btn)

        self.load_config_btn = QPushButton("Load")
        self.load_config_btn.clicked.connect(self._on_load_config)
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

        # Main content - Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - Detected addresses (two columns)
        detected_group = QGroupBox("Detected Addresses")
        detected_layout = QVBoxLayout(detected_group)

        # Two columns for GPIB and COM
        lists_layout = QHBoxLayout()

        # GPIB column
        gpib_layout = QVBoxLayout()
        gpib_layout.addWidget(QLabel("GPIB / USB / TCP:"))
        self.gpib_list = QListWidget()
        self.gpib_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        gpib_layout.addWidget(self.gpib_list)
        lists_layout.addLayout(gpib_layout)

        # COM column
        com_layout = QVBoxLayout()
        com_layout.addWidget(QLabel("COM / Serial Ports:"))
        self.com_list = QListWidget()
        self.com_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        com_layout.addWidget(self.com_list)
        lists_layout.addLayout(com_layout)

        detected_layout.addLayout(lists_layout)

        # Status label
        self.scan_status_label = QLabel("Click 'Scan for Instruments' to detect addresses")
        self.scan_status_label.setStyleSheet("color: gray; font-style: italic;")
        detected_layout.addWidget(self.scan_status_label)

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
        self.standards_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.standards_table.customContextMenuRequested.connect(self._on_standards_context_menu)
        standards_layout.addWidget(self.standards_table)

        standards_btn_layout = QHBoxLayout()

        self.add_manual_btn = QPushButton("Add Standard...")
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
        """Scan for connected instruments (addresses only, no IDN queries)."""
        if not PYVISA_AVAILABLE:
            QMessageBox.warning(
                self,
                "PyVISA Not Available",
                "PyVISA is not installed. Please install PyVISA and NI-VISA to scan for instruments.\n\n"
                "Install with: pip install pyvisa",
            )
            return

        logger.info("Scanning for instrument addresses")
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning...")
        self.gpib_list.clear()
        self.com_list.clear()
        self.scan_status_label.setText("Scanning...")
        self.scan_status_label.setStyleSheet("color: blue;")

        # Start scan in background thread
        self._scan_worker = AddressScanWorker()
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_finished(self, gpib_addresses: List[str], com_addresses: List[str]):
        """Handle scan completion."""
        self._gpib_addresses = gpib_addresses
        self._com_addresses = com_addresses

        # Populate GPIB list
        for addr in gpib_addresses:
            item = QListWidgetItem(addr)
            self.gpib_list.addItem(item)

        # Populate COM list
        for addr in com_addresses:
            item = QListWidgetItem(addr)
            self.com_list.addItem(item)

        total = len(gpib_addresses) + len(com_addresses)
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan for Instruments")
        self.scan_status_label.setText(
            f"Found {len(gpib_addresses)} GPIB/USB/TCP, {len(com_addresses)} COM ports"
        )
        self.scan_status_label.setStyleSheet("color: green;")
        logger.info(f"Scan complete: Found {total} addresses")

    def _on_scan_error(self, error_msg: str):
        """Handle scan error."""
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Scan for Instruments")
        self.scan_status_label.setText(f"Scan failed: {error_msg[:50]}")
        self.scan_status_label.setStyleSheet("color: red;")
        logger.error(f"Scan failed: {error_msg}")

    def _on_refresh(self):
        """Refresh status of workstation standards."""
        logger.info("Refreshing standard status")
        self._refresh_standards_table()

    def _get_all_addresses(self) -> List[str]:
        """Get all scanned addresses."""
        return self._gpib_addresses + self._com_addresses

    def _get_used_models(self) -> List[str]:
        """Get list of model names already added to workstation."""
        return [f"{d['make']} {d['model']}" for d in self._standards_data]

    def _on_add_manual(self):
        """Open dialog to add a standard."""
        logger.info("Opening add standard dialog")

        from calsystem.ui.dialogs.add_standard_dialog import AddStandardDialog
        dialog = AddStandardDialog(
            parent=self,
            available_addresses=self._get_all_addresses(),
            used_models=self._get_used_models(),
        )
        if dialog.exec():
            self._refresh_standards_table()

    def _on_filter_changed(self, filter_text: str):
        """Handle group filter change."""
        logger.debug(f"Filter changed to: {filter_text}")
        self._populate_standards_table()

    def _refresh_standards_table(self):
        """Refresh the standards table from the database."""
        logger.info("Refreshing standards table")

        db = get_db()
        if not db.is_connected:
            logger.warning("Database not connected - cannot load standards")
            return

        try:
            with db.session() as session:
                settings = get_settings()
                workstation_name = settings.workstation_name or "Default Workstation"

                workstation = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == workstation_name
                ).first()

                if not workstation:
                    logger.info(f"No workstation config found for: {workstation_name}")
                    self._standards_data = []
                    self._populate_standards_table()
                    return

                results = (
                    session.query(Standard, WorkstationStandard)
                    .join(WorkstationStandard, Standard.id == WorkstationStandard.standard_id)
                    .filter(WorkstationStandard.workstation_id == workstation.id)
                    .all()
                )

                command_banks = session.query(CommandBank.make, CommandBank.model).all()
                cb_set = {(cb.make.lower(), cb.model.lower()) for cb in command_banks}

                self._standards_data = []
                for standard, ws_standard in results:
                    has_command_bank = (standard.make.lower(), standard.model.lower()) in cb_set

                    self._standards_data.append({
                        "id": standard.id,
                        "ws_standard_id": ws_standard.id,
                        "group": standard.device_group.value if standard.device_group else "other",
                        "make": standard.make,
                        "model": standard.model,
                        "serial": standard.serial_number or "",
                        "std_id": standard.std_id or "",
                        "address": ws_standard.visa_address or standard.visa_address or "",
                        "has_command_bank": has_command_bank,
                    })

                self._populate_standards_table()
                logger.info(f"Loaded {len(self._standards_data)} standards for workstation")

        except Exception as e:
            logger.error(f"Failed to load standards: {e}")

    def _populate_standards_table(self):
        """Populate the standards table with filtered data."""
        self.standards_table.setRowCount(0)

        filter_text = self.group_filter.currentText()

        for data in self._standards_data:
            if filter_text != "All":
                group_map = {
                    "Calibrator": "calibrator",
                    "DMM": "dmm",
                    "Counter": "counter",
                    "Other": "other",
                }
                if data["group"] != group_map.get(filter_text, ""):
                    continue

            row = self.standards_table.rowCount()
            self.standards_table.insertRow(row)

            group_item = QTableWidgetItem(data["group"].title())
            group_item.setData(Qt.ItemDataRole.UserRole, data["ws_standard_id"])
            self.standards_table.setItem(row, 0, group_item)

            self.standards_table.setItem(row, 1, QTableWidgetItem(data["make"]))
            self.standards_table.setItem(row, 2, QTableWidgetItem(data["model"]))
            self.standards_table.setItem(row, 3, QTableWidgetItem(data["serial"]))
            self.standards_table.setItem(row, 4, QTableWidgetItem(data["std_id"]))
            self.standards_table.setItem(row, 5, QTableWidgetItem(data["address"]))

            if data.get("has_command_bank", True):
                status_item = QTableWidgetItem("OK")
                status_item.setForeground(QColor("green"))
            else:
                status_item = QTableWidgetItem("\u26A0 No Commands")
                status_item.setForeground(QColor("orange"))
                status_item.setToolTip(f"No command bank for {data['make']} {data['model']}")
            self.standards_table.setItem(row, 6, status_item)

    def _on_standards_context_menu(self, position):
        """Show context menu for standards table."""
        selected = self.standards_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        make = self.standards_table.item(row, 1).text()
        model = self.standards_table.item(row, 2).text()

        menu = QMenu(self)

        cmd_action = menu.addAction("Command Bank...")
        cmd_action.triggered.connect(self._on_command_bank)

        status_item = self.standards_table.item(row, 6)
        if status_item and "No Commands" in status_item.text():
            create_action = menu.addAction(f"Create Command Bank for {make} {model}...")
            create_action.triggered.connect(
                lambda: self._create_command_bank_for_standard(make, model)
            )

        menu.addSeparator()

        edit_action = menu.addAction("Edit Standard...")
        edit_action.triggered.connect(self._on_edit_standard)

        remove_action = menu.addAction("Remove from Workstation")
        remove_action.triggered.connect(self._on_remove_standard)

        menu.exec(self.standards_table.viewport().mapToGlobal(position))

    def _create_command_bank_for_standard(self, make: str, model: str):
        """Create a new command bank for a standard."""
        from calsystem.ui.dialogs.command_bank_dialog import CommandBankDialog
        dialog = CommandBankDialog(parent=self, make=make, model=model)
        if dialog.exec():
            self._refresh_standards_table()

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
            "Remove this standard from the workstation?\n\n"
            "(This only removes the workstation association, not the standard itself.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            row = selected[0].row()
            group_item = self.standards_table.item(row, 0)
            ws_standard_id = group_item.data(Qt.ItemDataRole.UserRole)

            if ws_standard_id:
                db = get_db()
                if db.is_connected:
                    try:
                        with db.session() as session:
                            ws_standard = session.query(WorkstationStandard).filter(
                                WorkstationStandard.id == ws_standard_id
                            ).first()
                            if ws_standard:
                                session.delete(ws_standard)
                                logger.info(f"Removed WorkstationStandard: {ws_standard_id}")
                    except Exception as e:
                        logger.error(f"Failed to remove standard: {e}")
                        QMessageBox.critical(self, "Error", f"Failed to remove standard:\n{e}")
                        return

            self._refresh_standards_table()

    def _on_command_bank(self):
        """Open command bank for selected standard."""
        selected = self.standards_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a standard to view command bank.")
            return

        row = selected[0].row()
        make = self.standards_table.item(row, 1).text()
        model = self.standards_table.item(row, 2).text()

        logger.info(f"Opening command bank dialog for {make} {model}")

        from calsystem.ui.dialogs.command_bank_dialog import CommandBankDialog
        dialog = CommandBankDialog(parent=self, make=make, model=model)
        dialog.exec()

    def _load_config_dropdown(self):
        """Load available workstation configs into the dropdown."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            current_text = self.config_combo.currentText()
            self.config_combo.clear()

            with db.session() as session:
                configs = session.query(WorkstationConfig).order_by(
                    WorkstationConfig.name
                ).all()

                for config in configs:
                    self.config_combo.addItem(config.name)

            if self.config_combo.count() == 0:
                self.config_combo.addItem("Default Workstation")

            index = self.config_combo.findText(current_text)
            if index >= 0:
                self.config_combo.setCurrentIndex(index)

        except Exception as e:
            logger.error(f"Failed to load config dropdown: {e}")
            self.config_combo.addItem("Default Workstation")

    def _on_save_config(self):
        """Save current workstation configuration with a name."""
        from PyQt6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(
            self,
            "Save Workstation Configuration",
            "Enter a name for this configuration:",
            text=self.config_combo.currentText(),
        )

        if not ok or not name.strip():
            return

        name = name.strip()
        db = get_db()

        if not db.is_connected:
            QMessageBox.critical(self, "Database Error", "Not connected to database.")
            return

        try:
            with db.session() as session:
                existing = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == name
                ).first()

                if existing:
                    reply = QMessageBox.question(
                        self,
                        "Overwrite Configuration",
                        f"Configuration '{name}' already exists. Overwrite?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        return

                    workstation = existing
                    session.query(WorkstationStandard).filter(
                        WorkstationStandard.workstation_id == workstation.id
                    ).delete()
                else:
                    workstation = WorkstationConfig(name=name)
                    session.add(workstation)
                    session.flush()

                for data in self._standards_data:
                    assoc = WorkstationStandard(
                        workstation_id=workstation.id,
                        standard_id=data["id"],
                        visa_address=data["address"] or None,
                    )
                    session.add(assoc)

                logger.info(f"Saved config: {name} with {len(self._standards_data)} standards")

            settings = get_settings()
            config_file = settings.config_dir / "config.json"
            import json
            config_data = {}
            if config_file.exists():
                try:
                    config_data = json.loads(config_file.read_text())
                except json.JSONDecodeError:
                    pass
            config_data["workstation_name"] = name
            config_file.write_text(json.dumps(config_data, indent=2))

            self._load_config_dropdown()

            QMessageBox.information(
                self,
                "Configuration Saved",
                f"Configuration '{name}' saved with {len(self._standards_data)} standards.",
            )

        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save configuration:\n{e}")

    def _on_load_config(self):
        """Load the selected workstation configuration."""
        config_name = self.config_combo.currentText()
        if not config_name:
            return

        db = get_db()
        if not db.is_connected:
            QMessageBox.critical(self, "Database Error", "Not connected to database.")
            return

        try:
            settings = get_settings()
            config_file = settings.config_dir / "config.json"
            import json
            config_data = {}
            if config_file.exists():
                try:
                    config_data = json.loads(config_file.read_text())
                except json.JSONDecodeError:
                    pass
            config_data["workstation_name"] = config_name
            config_file.write_text(json.dumps(config_data, indent=2))

            from calsystem.config.settings import reload_settings
            reload_settings()
            self._refresh_standards_table()

            logger.info(f"Loaded workstation config: {config_name}")

        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load configuration:\n{e}")
