"""
Remote tab - Manage COM ports and DUT command banks for remote DUT communication.
"""

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
    QComboBox,
    QFormLayout,
    QSplitter,
    QMessageBox,
    QSpinBox,
    QDoubleSpinBox,
    QTextEdit,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from loguru import logger

from calsystem.database.connection import get_db
from calsystem.database.models import DUTCommandBank, STANDARD_DUT_COMMANDS
from calsystem.instruments.serial_manager import (
    get_serial_manager,
    SerialConfig,
    SerialPortInfo,
)


class RemoteTab(QWidget):
    """Tab for managing COM ports and DUT command banks."""

    def __init__(self):
        super().__init__()
        self._current_bank_id: Optional[int] = None
        self._port_scan_timer: Optional[QTimer] = None
        self._init_ui()
        self._load_command_banks()
        self._start_port_scanning()

    def _init_ui(self):
        """Initialize the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - COM Port Manager
        left_panel = self._create_com_port_panel()
        splitter.addWidget(left_panel)

        # Right panel - DUT Command Banks
        right_panel = self._create_command_bank_panel()
        splitter.addWidget(right_panel)

        # Set initial splitter sizes (40% left, 60% right)
        splitter.setSizes([400, 600])

        layout.addWidget(splitter)

    def _create_com_port_panel(self) -> QWidget:
        """Create the COM port manager panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Header
        header = QLabel("COM Port Manager")
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        # Refresh button
        btn_layout = QHBoxLayout()
        self.refresh_ports_btn = QPushButton("Refresh Ports")
        self.refresh_ports_btn.clicked.connect(self._refresh_ports)
        btn_layout.addWidget(self.refresh_ports_btn)

        self.auto_refresh_label = QLabel("Auto-refresh: ON")
        self.auto_refresh_label.setStyleSheet("color: green; font-size: 10px;")
        btn_layout.addWidget(self.auto_refresh_label)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Port table
        self.port_table = QTableWidget()
        self.port_table.setColumnCount(4)
        self.port_table.setHorizontalHeaderLabels(["Port", "Description", "Status", "In Use By"])
        self.port_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.port_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.port_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.port_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.port_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.port_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.port_table.itemSelectionChanged.connect(self._on_port_selected)
        layout.addWidget(self.port_table)

        # Port settings group
        settings_group = QGroupBox("Port Settings")
        settings_layout = QFormLayout(settings_group)

        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        settings_layout.addRow("Baud Rate:", self.baud_combo)

        self.data_bits_combo = QComboBox()
        self.data_bits_combo.addItems(["8", "7", "6", "5"])
        settings_layout.addRow("Data Bits:", self.data_bits_combo)

        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["None (N)", "Even (E)", "Odd (O)"])
        settings_layout.addRow("Parity:", self.parity_combo)

        self.stop_bits_combo = QComboBox()
        self.stop_bits_combo.addItems(["1", "1.5", "2"])
        settings_layout.addRow("Stop Bits:", self.stop_bits_combo)

        layout.addWidget(settings_group)

        # Test connection button
        test_layout = QHBoxLayout()
        self.test_connection_btn = QPushButton("Test Connection")
        self.test_connection_btn.clicked.connect(self._on_test_connection)
        self.test_connection_btn.setEnabled(False)
        test_layout.addWidget(self.test_connection_btn)

        self.test_result_label = QLabel("")
        test_layout.addWidget(self.test_result_label)
        test_layout.addStretch()
        layout.addLayout(test_layout)

        # Test command area
        test_cmd_group = QGroupBox("Test Command")
        test_cmd_layout = QVBoxLayout(test_cmd_group)

        cmd_row = QHBoxLayout()
        self.test_cmd_input = QLineEdit()
        self.test_cmd_input.setPlaceholderText("Enter command to send (e.g., *IDN?)")
        cmd_row.addWidget(self.test_cmd_input)

        self.send_cmd_btn = QPushButton("Send")
        self.send_cmd_btn.clicked.connect(self._on_send_test_command)
        self.send_cmd_btn.setEnabled(False)
        cmd_row.addWidget(self.send_cmd_btn)
        test_cmd_layout.addLayout(cmd_row)

        self.cmd_response_text = QTextEdit()
        self.cmd_response_text.setReadOnly(True)
        self.cmd_response_text.setMaximumHeight(80)
        self.cmd_response_text.setPlaceholderText("Response will appear here...")
        test_cmd_layout.addWidget(self.cmd_response_text)

        layout.addWidget(test_cmd_group)

        return panel

    def _create_command_bank_panel(self) -> QWidget:
        """Create the DUT command bank manager panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Header
        header = QLabel("DUT Command Banks")
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        # Bank list section
        list_group = QGroupBox("Command Banks")
        list_layout = QVBoxLayout(list_group)

        # Search
        search_layout = QHBoxLayout()
        self.bank_search_input = QLineEdit()
        self.bank_search_input.setPlaceholderText("Search by make/model...")
        self.bank_search_input.textChanged.connect(self._filter_banks)
        search_layout.addWidget(self.bank_search_input)
        list_layout.addLayout(search_layout)

        # Bank table
        self.bank_table = QTableWidget()
        self.bank_table.setColumnCount(4)
        self.bank_table.setHorizontalHeaderLabels(["Make", "Model", "Commands", "Comm Type"])
        self.bank_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.bank_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.bank_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.bank_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.bank_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.bank_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.bank_table.itemSelectionChanged.connect(self._on_bank_selected)
        self.bank_table.setMaximumHeight(150)
        list_layout.addWidget(self.bank_table)

        # Bank buttons
        btn_layout = QHBoxLayout()
        self.new_bank_btn = QPushButton("New")
        self.new_bank_btn.clicked.connect(self._on_new_bank)
        btn_layout.addWidget(self.new_bank_btn)

        self.delete_bank_btn = QPushButton("Delete")
        self.delete_bank_btn.clicked.connect(self._on_delete_bank)
        self.delete_bank_btn.setEnabled(False)
        btn_layout.addWidget(self.delete_bank_btn)

        self.clone_bank_btn = QPushButton("Clone")
        self.clone_bank_btn.clicked.connect(self._on_clone_bank)
        self.clone_bank_btn.setEnabled(False)
        btn_layout.addWidget(self.clone_bank_btn)

        btn_layout.addStretch()
        list_layout.addLayout(btn_layout)
        layout.addWidget(list_group)

        # Editor section
        editor_group = QGroupBox("Command Bank Editor")
        editor_layout = QVBoxLayout(editor_group)

        # Device info
        info_layout = QFormLayout()

        self.bank_make_input = QLineEdit()
        self.bank_make_input.setPlaceholderText("e.g., Fluke")
        info_layout.addRow("Make:", self.bank_make_input)

        self.bank_model_input = QLineEdit()
        self.bank_model_input.setPlaceholderText("e.g., 789")
        info_layout.addRow("Model:", self.bank_model_input)

        self.comm_type_combo = QComboBox()
        self.comm_type_combo.addItems(["serial", "gpib", "usb"])
        info_layout.addRow("Comm Type:", self.comm_type_combo)

        self.bank_description_input = QLineEdit()
        self.bank_description_input.setPlaceholderText("Optional description")
        info_layout.addRow("Description:", self.bank_description_input)

        editor_layout.addLayout(info_layout)

        # Serial config (shown when comm_type is serial)
        self.serial_config_group = QGroupBox("Serial Configuration")
        serial_layout = QFormLayout(self.serial_config_group)

        self.serial_baud_combo = QComboBox()
        self.serial_baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        serial_layout.addRow("Baud Rate:", self.serial_baud_combo)

        self.serial_config_label = QLabel("8N1 (8 data bits, No parity, 1 stop bit)")
        self.serial_config_label.setStyleSheet("color: gray;")
        serial_layout.addRow("Format:", self.serial_config_label)

        editor_layout.addWidget(self.serial_config_group)

        # Commands table
        cmd_label = QLabel("Commands:")
        cmd_label.setStyleSheet("font-weight: bold;")
        editor_layout.addWidget(cmd_label)

        self.commands_table = QTableWidget()
        self.commands_table.setColumnCount(4)
        self.commands_table.setHorizontalHeaderLabels(["Name", "Command", "Delay Before", "Delay After"])
        self.commands_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.commands_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.commands_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.commands_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        editor_layout.addWidget(self.commands_table)

        # Command buttons
        cmd_btn_layout = QHBoxLayout()

        self.add_cmd_btn = QPushButton("Add Command")
        self.add_cmd_btn.clicked.connect(self._on_add_command)
        cmd_btn_layout.addWidget(self.add_cmd_btn)

        self.add_std_cmds_btn = QPushButton("Add Standard Commands")
        self.add_std_cmds_btn.clicked.connect(self._on_add_standard_commands)
        cmd_btn_layout.addWidget(self.add_std_cmds_btn)

        self.remove_cmd_btn = QPushButton("Remove")
        self.remove_cmd_btn.clicked.connect(self._on_remove_command)
        cmd_btn_layout.addWidget(self.remove_cmd_btn)

        cmd_btn_layout.addStretch()

        self.test_cmd_bank_btn = QPushButton("Test Command")
        self.test_cmd_bank_btn.clicked.connect(self._on_test_bank_command)
        cmd_btn_layout.addWidget(self.test_cmd_bank_btn)

        editor_layout.addLayout(cmd_btn_layout)

        # Save button
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        self.save_bank_btn = QPushButton("Save Command Bank")
        self.save_bank_btn.clicked.connect(self._on_save_bank)
        self.save_bank_btn.setStyleSheet("font-weight: bold;")
        save_layout.addWidget(self.save_bank_btn)
        editor_layout.addLayout(save_layout)

        layout.addWidget(editor_group)

        return panel

    def _start_port_scanning(self):
        """Start automatic port scanning."""
        self._port_scan_timer = QTimer(self)
        self._port_scan_timer.timeout.connect(self._check_port_changes)
        self._port_scan_timer.start(2000)  # Check every 2 seconds
        self._refresh_ports()

    def _check_port_changes(self):
        """Check for COM port changes."""
        serial_mgr = get_serial_manager()
        if not serial_mgr.is_available():
            return

        added, removed = serial_mgr.get_port_changes()
        if added or removed:
            self._refresh_ports()
            if added:
                logger.info(f"New COM ports detected: {[p.port for p in added]}")
            if removed:
                logger.info(f"COM ports removed: {[p.port for p in removed]}")

    def _refresh_ports(self):
        """Refresh the COM port list."""
        serial_mgr = get_serial_manager()
        ports = serial_mgr.scan()

        self.port_table.setRowCount(len(ports))

        for row, port_info in enumerate(ports):
            # Port name
            port_item = QTableWidgetItem(port_info.port)
            port_item.setData(Qt.ItemDataRole.UserRole, port_info)
            self.port_table.setItem(row, 0, port_item)

            # Description
            desc_item = QTableWidgetItem(port_info.description)
            self.port_table.setItem(row, 1, desc_item)

            # Status
            is_connected = serial_mgr.is_connected(port_info.port)
            status_item = QTableWidgetItem("Connected" if is_connected else "Available")
            status_item.setForeground(QColor("green") if is_connected else QColor("gray"))
            self.port_table.setItem(row, 2, status_item)

            # In use by (check DUTs)
            in_use = self._get_port_usage(port_info.port)
            use_item = QTableWidgetItem(in_use or "-")
            self.port_table.setItem(row, 3, use_item)

    def _get_port_usage(self, port: str) -> str:
        """Check if a port is assigned to a DUT."""
        db = get_db()
        if not db.is_connected:
            return ""

        try:
            from calsystem.database.models import DUT
            with db.session() as session:
                dut = session.query(DUT).filter(DUT.com_port == port).first()
                if dut:
                    return f"{dut.make} {dut.model}"
        except Exception:
            pass
        return ""

    def _on_port_selected(self):
        """Handle port selection."""
        selected = self.port_table.selectedItems()
        self.test_connection_btn.setEnabled(len(selected) > 0)
        self.send_cmd_btn.setEnabled(len(selected) > 0)

    def _on_test_connection(self):
        """Test connection to selected port."""
        selected = self.port_table.selectedItems()
        if not selected:
            return

        port_item = self.port_table.item(selected[0].row(), 0)
        port_info: SerialPortInfo = port_item.data(Qt.ItemDataRole.UserRole)
        port = port_info.port

        # Get config from UI
        config = SerialConfig(
            baud_rate=int(self.baud_combo.currentText()),
            data_bits=int(self.data_bits_combo.currentText()),
            parity=self.parity_combo.currentText()[0] if self.parity_combo.currentText() else "N",
            stop_bits=float(self.stop_bits_combo.currentText()),
        )

        serial_mgr = get_serial_manager()

        # Disconnect first if already connected
        if serial_mgr.is_connected(port):
            serial_mgr.disconnect(port)

        # Try to connect
        if serial_mgr.connect(port, config):
            self.test_result_label.setText(f"Connected to {port}")
            self.test_result_label.setStyleSheet("color: green;")
            self._refresh_ports()
        else:
            self.test_result_label.setText(f"Failed to connect to {port}")
            self.test_result_label.setStyleSheet("color: red;")

    def _on_send_test_command(self):
        """Send test command to selected port."""
        selected = self.port_table.selectedItems()
        if not selected:
            return

        port_item = self.port_table.item(selected[0].row(), 0)
        port_info: SerialPortInfo = port_item.data(Qt.ItemDataRole.UserRole)
        port = port_info.port

        command = self.test_cmd_input.text().strip()
        if not command:
            self.cmd_response_text.setText("Please enter a command")
            return

        serial_mgr = get_serial_manager()

        # Connect if not connected
        if not serial_mgr.is_connected(port):
            config = SerialConfig(
                baud_rate=int(self.baud_combo.currentText()),
                data_bits=int(self.data_bits_combo.currentText()),
                parity=self.parity_combo.currentText()[0] if self.parity_combo.currentText() else "N",
                stop_bits=float(self.stop_bits_combo.currentText()),
            )
            if not serial_mgr.connect(port, config):
                self.cmd_response_text.setText(f"Failed to connect to {port}")
                return

        # Send command and get response
        success, response = serial_mgr.query(port, command, delay_after=0.2)

        if success:
            self.cmd_response_text.setText(f"Command: {command}\nResponse: {response}")
        else:
            self.cmd_response_text.setText(f"Command failed: {command}\nNo response received")

    # =========================================================================
    # Command Bank Methods
    # =========================================================================

    def _load_command_banks(self):
        """Load all DUT command banks from database."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                banks = session.query(DUTCommandBank).order_by(
                    DUTCommandBank.make, DUTCommandBank.model
                ).all()

                self.bank_table.setRowCount(len(banks))

                for row, bank in enumerate(banks):
                    # Make
                    make_item = QTableWidgetItem(bank.make)
                    make_item.setData(Qt.ItemDataRole.UserRole, bank.id)
                    self.bank_table.setItem(row, 0, make_item)

                    # Model
                    model_item = QTableWidgetItem(bank.model)
                    self.bank_table.setItem(row, 1, model_item)

                    # Command count
                    cmd_count = len(bank.commands) if bank.commands else 0
                    count_item = QTableWidgetItem(str(cmd_count))
                    count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.bank_table.setItem(row, 2, count_item)

                    # Comm type
                    type_item = QTableWidgetItem(bank.communication_type or "serial")
                    self.bank_table.setItem(row, 3, type_item)

        except Exception as e:
            logger.error(f"Failed to load command banks: {e}")

    def _filter_banks(self, text: str):
        """Filter command banks by search text."""
        text = text.lower()
        for row in range(self.bank_table.rowCount()):
            make_item = self.bank_table.item(row, 0)
            model_item = self.bank_table.item(row, 1)

            if make_item and model_item:
                make = make_item.text().lower()
                model = model_item.text().lower()
                visible = text in make or text in model or not text
                self.bank_table.setRowHidden(row, not visible)

    def _on_bank_selected(self):
        """Handle bank selection."""
        selected = self.bank_table.selectedItems()
        has_selection = len(selected) > 0

        self.delete_bank_btn.setEnabled(has_selection)
        self.clone_bank_btn.setEnabled(has_selection)

        if has_selection:
            bank_id = self.bank_table.item(selected[0].row(), 0).data(Qt.ItemDataRole.UserRole)
            self._load_bank_into_editor(bank_id)

    def _load_bank_into_editor(self, bank_id: int):
        """Load a command bank into the editor."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                bank = session.query(DUTCommandBank).filter(DUTCommandBank.id == bank_id).first()
                if not bank:
                    return

                self._current_bank_id = bank.id
                self.bank_make_input.setText(bank.make or "")
                self.bank_model_input.setText(bank.model or "")
                self.bank_description_input.setText(bank.description or "")

                # Comm type
                idx = self.comm_type_combo.findText(bank.communication_type or "serial")
                if idx >= 0:
                    self.comm_type_combo.setCurrentIndex(idx)

                # Serial config
                if bank.serial_config:
                    baud = str(bank.serial_config.get("baud_rate", 9600))
                    idx = self.serial_baud_combo.findText(baud)
                    if idx >= 0:
                        self.serial_baud_combo.setCurrentIndex(idx)

                # Commands
                self._load_commands_into_table(bank.commands or {})

        except Exception as e:
            logger.error(f"Failed to load bank: {e}")

    def _load_commands_into_table(self, commands: dict):
        """Load commands into the commands table."""
        self.commands_table.setRowCount(len(commands))

        for row, (name, cmd_info) in enumerate(commands.items()):
            # Name
            name_item = QTableWidgetItem(name)
            self.commands_table.setItem(row, 0, name_item)

            # Command string
            if isinstance(cmd_info, dict):
                cmd_str = cmd_info.get("command", "")
                delay_before = cmd_info.get("delay_before", 0)
                delay_after = cmd_info.get("delay_after", 0.1)
            else:
                cmd_str = str(cmd_info)
                delay_before = 0
                delay_after = 0.1

            cmd_item = QTableWidgetItem(cmd_str)
            self.commands_table.setItem(row, 1, cmd_item)

            # Delay before
            before_item = QTableWidgetItem(str(delay_before))
            before_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.commands_table.setItem(row, 2, before_item)

            # Delay after
            after_item = QTableWidgetItem(str(delay_after))
            after_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.commands_table.setItem(row, 3, after_item)

    def _on_new_bank(self):
        """Create a new command bank."""
        self._current_bank_id = None
        self.bank_make_input.clear()
        self.bank_model_input.clear()
        self.bank_description_input.clear()
        self.comm_type_combo.setCurrentIndex(0)
        self.serial_baud_combo.setCurrentIndex(0)
        self.commands_table.setRowCount(0)
        self.bank_table.clearSelection()
        self.delete_bank_btn.setEnabled(False)
        self.clone_bank_btn.setEnabled(False)

    def _on_delete_bank(self):
        """Delete the selected command bank."""
        if self._current_bank_id is None:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete this command bank?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                bank = session.query(DUTCommandBank).filter(
                    DUTCommandBank.id == self._current_bank_id
                ).first()
                if bank:
                    session.delete(bank)
                    session.commit()

            self._on_new_bank()
            self._load_command_banks()
            logger.info(f"Deleted command bank ID {self._current_bank_id}")

        except Exception as e:
            logger.error(f"Failed to delete bank: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete: {e}")

    def _on_clone_bank(self):
        """Clone the selected command bank."""
        if self._current_bank_id is None:
            return

        # Clear the ID so save creates a new record
        self._current_bank_id = None
        self.bank_model_input.setText(self.bank_model_input.text() + " (Copy)")
        self.bank_table.clearSelection()

    def _on_add_command(self):
        """Add a new empty command row."""
        row = self.commands_table.rowCount()
        self.commands_table.insertRow(row)

        self.commands_table.setItem(row, 0, QTableWidgetItem(""))
        self.commands_table.setItem(row, 1, QTableWidgetItem(""))
        self.commands_table.setItem(row, 2, QTableWidgetItem("0"))
        self.commands_table.setItem(row, 3, QTableWidgetItem("0.1"))

    def _on_add_standard_commands(self):
        """Add all standard DUT commands."""
        for cmd_def in STANDARD_DUT_COMMANDS:
            name = cmd_def["name"]

            # Check if already exists
            exists = False
            for row in range(self.commands_table.rowCount()):
                item = self.commands_table.item(row, 0)
                if item and item.text() == name:
                    exists = True
                    break

            if not exists:
                row = self.commands_table.rowCount()
                self.commands_table.insertRow(row)

                name_item = QTableWidgetItem(name)
                name_item.setToolTip(cmd_def["description"])
                self.commands_table.setItem(row, 0, name_item)

                self.commands_table.setItem(row, 1, QTableWidgetItem(cmd_def.get("default_command", "")))
                self.commands_table.setItem(row, 2, QTableWidgetItem("0"))
                self.commands_table.setItem(row, 3, QTableWidgetItem("0.1"))

    def _on_remove_command(self):
        """Remove the selected command row."""
        selected = self.commands_table.selectedItems()
        if selected:
            row = selected[0].row()
            self.commands_table.removeRow(row)

    def _on_test_bank_command(self):
        """Test a command from the command bank."""
        selected = self.commands_table.selectedItems()
        if not selected:
            QMessageBox.information(self, "Test Command", "Please select a command row to test.")
            return

        row = selected[0].row()
        cmd_item = self.commands_table.item(row, 1)
        if not cmd_item or not cmd_item.text():
            QMessageBox.warning(self, "Test Command", "No command string defined.")
            return

        # Check if a port is selected
        port_selected = self.port_table.selectedItems()
        if not port_selected:
            QMessageBox.information(
                self,
                "Test Command",
                "Please select a COM port in the left panel first.",
            )
            return

        # Get the command
        command = cmd_item.text()

        # Use the test command input on the left
        self.test_cmd_input.setText(command)
        self._on_send_test_command()

    def _on_save_bank(self):
        """Save the current command bank."""
        make = self.bank_make_input.text().strip()
        model = self.bank_model_input.text().strip()

        if not make or not model:
            QMessageBox.warning(self, "Missing Data", "Make and Model are required.")
            return

        # Collect commands
        commands = {}
        for row in range(self.commands_table.rowCount()):
            name_item = self.commands_table.item(row, 0)
            cmd_item = self.commands_table.item(row, 1)
            before_item = self.commands_table.item(row, 2)
            after_item = self.commands_table.item(row, 3)

            if name_item and name_item.text():
                name = name_item.text()
                commands[name] = {
                    "command": cmd_item.text() if cmd_item else "",
                    "delay_before": float(before_item.text() or 0) if before_item else 0,
                    "delay_after": float(after_item.text() or 0.1) if after_item else 0.1,
                }

        # Serial config
        serial_config = {
            "baud_rate": int(self.serial_baud_combo.currentText()),
            "data_bits": 8,
            "parity": "N",
            "stop_bits": 1,
        }

        db = get_db()
        if not db.is_connected:
            QMessageBox.warning(self, "Database Error", "Not connected to database.")
            return

        try:
            with db.session() as session:
                if self._current_bank_id:
                    # Update existing
                    bank = session.query(DUTCommandBank).filter(
                        DUTCommandBank.id == self._current_bank_id
                    ).first()
                    if bank:
                        bank.make = make
                        bank.model = model
                        bank.description = self.bank_description_input.text()
                        bank.communication_type = self.comm_type_combo.currentText()
                        bank.serial_config = serial_config
                        bank.commands = commands
                else:
                    # Check for duplicate
                    existing = session.query(DUTCommandBank).filter(
                        DUTCommandBank.make.ilike(make),
                        DUTCommandBank.model.ilike(model),
                    ).first()

                    if existing:
                        reply = QMessageBox.question(
                            self,
                            "Duplicate Found",
                            f"A command bank for {make} {model} already exists. Update it?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        )
                        if reply == QMessageBox.StandardButton.Yes:
                            existing.description = self.bank_description_input.text()
                            existing.communication_type = self.comm_type_combo.currentText()
                            existing.serial_config = serial_config
                            existing.commands = commands
                            self._current_bank_id = existing.id
                        else:
                            return
                    else:
                        # Create new
                        bank = DUTCommandBank(
                            make=make,
                            model=model,
                            description=self.bank_description_input.text(),
                            communication_type=self.comm_type_combo.currentText(),
                            serial_config=serial_config,
                            commands=commands,
                        )
                        session.add(bank)
                        session.flush()
                        self._current_bank_id = bank.id

                session.commit()

            self._load_command_banks()
            QMessageBox.information(self, "Saved", f"Command bank for {make} {model} saved.")
            logger.info(f"Saved DUT command bank: {make} {model}")

        except Exception as e:
            logger.error(f"Failed to save bank: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
