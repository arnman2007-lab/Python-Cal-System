"""
Dialog for managing command banks (SCPI command sets for devices).
"""

import json
from typing import Optional, List, Dict

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QComboBox,
    QPushButton,
    QDialogButtonBox,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QSplitter,
    QWidget,
    QLabel,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from loguru import logger

from calsystem.database.connection import get_db
from calsystem.database.models import CommandBank, STANDARD_COMMANDS


class CommandBankDialog(QDialog):
    """Dialog for creating and editing command banks."""

    def __init__(self, parent=None, make: str = "", model: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Command Bank Manager")
        self.setMinimumSize(700, 500)
        self.setModal(True)

        self._current_bank_id: Optional[int] = None
        self._pre_fill_make = make
        self._pre_fill_model = model

        self._init_ui()
        self._load_command_banks()

        # If pre-filled, try to load existing or create new
        if make and model:
            self._select_or_create_bank(make, model)

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QHBoxLayout(self)

        # Left side - Command bank list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        list_group = QGroupBox("Command Banks")
        list_layout = QVBoxLayout(list_group)

        # Filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Make or model...")
        self.filter_input.textChanged.connect(self._filter_banks)
        filter_layout.addWidget(self.filter_input)
        list_layout.addLayout(filter_layout)

        # Bank list
        self.bank_table = QTableWidget()
        self.bank_table.setColumnCount(3)
        self.bank_table.setHorizontalHeaderLabels(["Make", "Model", "Type"])
        self.bank_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bank_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.bank_table.itemSelectionChanged.connect(self._on_bank_selected)
        list_layout.addWidget(self.bank_table)

        # List buttons
        btn_layout = QHBoxLayout()
        self.new_bank_btn = QPushButton("New")
        self.new_bank_btn.clicked.connect(self._on_new_bank)
        btn_layout.addWidget(self.new_bank_btn)

        self.delete_bank_btn = QPushButton("Delete")
        self.delete_bank_btn.clicked.connect(self._on_delete_bank)
        btn_layout.addWidget(self.delete_bank_btn)
        list_layout.addLayout(btn_layout)

        left_layout.addWidget(list_group)
        layout.addWidget(left_widget, 1)

        # Right side - Command bank editor
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Device info
        info_group = QGroupBox("Device Information")
        info_layout = QFormLayout(info_group)

        self.make_input = QLineEdit()
        self.make_input.setPlaceholderText("e.g., Fluke, Keysight")
        info_layout.addRow("Make:", self.make_input)

        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("e.g., 5520A, 3458A")
        info_layout.addRow("Model:", self.model_input)

        self.device_type_combo = QComboBox()
        self.device_type_combo.addItems(["calibrator", "dmm", "counter", "dut", "other"])
        info_layout.addRow("Device Type:", self.device_type_combo)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Optional description")
        info_layout.addRow("Description:", self.description_input)

        right_layout.addWidget(info_group)

        # Commands
        cmd_group = QGroupBox("Commands (Generic Name → Actual SCPI Command)")
        cmd_layout = QVBoxLayout(cmd_group)

        # Help text
        help_label = QLabel(
            "Map Calsystem's generic command names to this device's actual SCPI commands.\n"
            "Use {value}, {unit}, {frequency}, {freq_unit} as placeholders in OUTPUT commands."
        )
        help_label.setStyleSheet("color: gray; font-size: 11px;")
        help_label.setWordWrap(True)
        cmd_layout.addWidget(help_label)

        self.cmd_table = QTableWidget()
        self.cmd_table.setColumnCount(3)
        self.cmd_table.setHorizontalHeaderLabels(["Generic Name", "SCPI Command", "Description"])
        self.cmd_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.cmd_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.cmd_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        cmd_layout.addWidget(self.cmd_table)

        cmd_btn_layout = QHBoxLayout()
        self.add_cmd_btn = QPushButton("Add Command")
        self.add_cmd_btn.clicked.connect(self._on_add_command)
        cmd_btn_layout.addWidget(self.add_cmd_btn)

        self.remove_cmd_btn = QPushButton("Remove")
        self.remove_cmd_btn.clicked.connect(self._on_remove_command)
        cmd_btn_layout.addWidget(self.remove_cmd_btn)

        self.populate_defaults_btn = QPushButton("Add Standard Commands")
        self.populate_defaults_btn.clicked.connect(self._on_populate_defaults)
        cmd_btn_layout.addWidget(self.populate_defaults_btn)

        cmd_btn_layout.addStretch()
        cmd_layout.addLayout(cmd_btn_layout)

        right_layout.addWidget(cmd_group)

        # Save button
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        self.save_btn = QPushButton("Save Command Bank")
        self.save_btn.clicked.connect(self._on_save)
        save_layout.addWidget(self.save_btn)
        right_layout.addLayout(save_layout)

        layout.addWidget(right_widget, 2)

        # Dialog close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

    def _load_command_banks(self):
        """Load all command banks from database."""
        self._all_banks: List[Dict] = []

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                banks = session.query(CommandBank).order_by(
                    CommandBank.make, CommandBank.model
                ).all()

                for bank in banks:
                    self._all_banks.append({
                        "id": bank.id,
                        "make": bank.make,
                        "model": bank.model,
                        "device_type": bank.device_type or "",
                        "description": bank.description or "",
                        "commands": bank.commands or {},
                    })

            self._populate_bank_table()

        except Exception as e:
            logger.error(f"Failed to load command banks: {e}")

    def _populate_bank_table(self, filter_text: str = ""):
        """Populate the bank list table."""
        self.bank_table.setRowCount(0)

        for bank in self._all_banks:
            # Apply filter
            if filter_text:
                if (filter_text.lower() not in bank["make"].lower() and
                    filter_text.lower() not in bank["model"].lower()):
                    continue

            row = self.bank_table.rowCount()
            self.bank_table.insertRow(row)

            make_item = QTableWidgetItem(bank["make"])
            make_item.setData(Qt.ItemDataRole.UserRole, bank["id"])
            self.bank_table.setItem(row, 0, make_item)
            self.bank_table.setItem(row, 1, QTableWidgetItem(bank["model"]))
            self.bank_table.setItem(row, 2, QTableWidgetItem(bank["device_type"]))

    def _filter_banks(self, text: str):
        """Filter the bank table."""
        self._populate_bank_table(text)

    def _on_bank_selected(self):
        """Handle bank selection."""
        selected = self.bank_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        make_item = self.bank_table.item(row, 0)
        bank_id = make_item.data(Qt.ItemDataRole.UserRole)

        # Find the bank data
        for bank in self._all_banks:
            if bank["id"] == bank_id:
                self._load_bank_into_form(bank)
                break

    def _load_bank_into_form(self, bank: Dict):
        """Load a command bank into the editor form."""
        self._current_bank_id = bank["id"]
        self.make_input.setText(bank["make"])
        self.model_input.setText(bank["model"])
        self.description_input.setText(bank["description"])

        # Set device type
        idx = self.device_type_combo.findText(bank["device_type"])
        if idx >= 0:
            self.device_type_combo.setCurrentIndex(idx)

        # Load commands
        self.cmd_table.setRowCount(0)
        commands = bank.get("commands", {})
        for name, scpi in commands.items():
            row = self.cmd_table.rowCount()
            self.cmd_table.insertRow(row)
            self.cmd_table.setItem(row, 0, QTableWidgetItem(name))
            self.cmd_table.setItem(row, 1, QTableWidgetItem(scpi))
            # Add description from STANDARD_COMMANDS if available
            desc = ""
            if name in STANDARD_COMMANDS:
                desc = STANDARD_COMMANDS[name].get("description", "")
            desc_item = QTableWidgetItem(desc)
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # Read-only
            self.cmd_table.setItem(row, 2, desc_item)

    def _on_new_bank(self):
        """Create a new command bank."""
        self._current_bank_id = None
        self.make_input.clear()
        self.model_input.clear()
        self.description_input.clear()
        self.device_type_combo.setCurrentIndex(0)
        self.cmd_table.setRowCount(0)
        self.make_input.setFocus()

    def _on_delete_bank(self):
        """Delete the selected command bank."""
        if not self._current_bank_id:
            QMessageBox.warning(self, "No Selection", "Please select a command bank to delete.")
            return

        reply = QMessageBox.question(
            self,
            "Delete Command Bank",
            f"Delete command bank for {self.make_input.text()} {self.model_input.text()}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                bank = session.query(CommandBank).filter(
                    CommandBank.id == self._current_bank_id
                ).first()
                if bank:
                    session.delete(bank)
                    logger.info(f"Deleted command bank: {self._current_bank_id}")

            self._on_new_bank()
            self._load_command_banks()

        except Exception as e:
            logger.error(f"Failed to delete command bank: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete:\n{e}")

    def _on_add_command(self):
        """Add a new command row."""
        row = self.cmd_table.rowCount()
        self.cmd_table.insertRow(row)
        self.cmd_table.setItem(row, 0, QTableWidgetItem(""))
        self.cmd_table.setItem(row, 1, QTableWidgetItem(""))
        self.cmd_table.setItem(row, 2, QTableWidgetItem("Custom command"))
        self.cmd_table.editItem(self.cmd_table.item(row, 0))

    def _on_remove_command(self):
        """Remove the selected command row."""
        selected = self.cmd_table.selectedItems()
        if selected:
            self.cmd_table.removeRow(selected[0].row())

    def _on_populate_defaults(self):
        """Add all standard commands to the table with their default values."""
        for name, info in STANDARD_COMMANDS.items():
            # Check if already exists
            exists = False
            for row in range(self.cmd_table.rowCount()):
                item = self.cmd_table.item(row, 0)
                if item and item.text() == name:
                    exists = True
                    break

            if not exists:
                row = self.cmd_table.rowCount()
                self.cmd_table.insertRow(row)

                # Name (read-only for standard commands)
                name_item = QTableWidgetItem(name)
                self.cmd_table.setItem(row, 0, name_item)

                # Default SCPI command (editable - user customizes for their device)
                self.cmd_table.setItem(row, 1, QTableWidgetItem(info.get("default", "")))

                # Description (read-only)
                desc_item = QTableWidgetItem(info.get("description", ""))
                desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.cmd_table.setItem(row, 2, desc_item)

                # Highlight required commands
                if info.get("required"):
                    name_item.setBackground(QColor(255, 255, 200))  # Light yellow

    def _on_save(self):
        """Save the current command bank."""
        make = self.make_input.text().strip()
        model = self.model_input.text().strip()

        if not make or not model:
            QMessageBox.warning(self, "Validation Error", "Make and Model are required.")
            return

        # Collect commands
        commands = {}
        for row in range(self.cmd_table.rowCount()):
            name_item = self.cmd_table.item(row, 0)
            scpi_item = self.cmd_table.item(row, 1)
            if name_item and scpi_item:
                name = name_item.text().strip()
                scpi = scpi_item.text().strip()
                if name and scpi:
                    commands[name] = scpi

        db = get_db()
        if not db.is_connected:
            QMessageBox.critical(self, "Database Error", "Not connected to database.")
            return

        try:
            with db.session() as session:
                if self._current_bank_id:
                    bank = session.query(CommandBank).filter(
                        CommandBank.id == self._current_bank_id
                    ).first()
                else:
                    # Check for duplicate
                    existing = session.query(CommandBank).filter(
                        CommandBank.make == make,
                        CommandBank.model == model,
                    ).first()

                    if existing:
                        reply = QMessageBox.question(
                            self,
                            "Existing Bank",
                            f"A command bank for {make} {model} already exists. Update it?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        )
                        if reply == QMessageBox.StandardButton.Yes:
                            bank = existing
                            self._current_bank_id = bank.id
                        else:
                            return
                    else:
                        bank = CommandBank(make=make, model=model)
                        session.add(bank)

                bank.make = make
                bank.model = model
                bank.device_type = self.device_type_combo.currentText()
                bank.description = self.description_input.text().strip() or None
                bank.commands = commands

                session.flush()
                self._current_bank_id = bank.id

            logger.info(f"Saved command bank: {make} {model}")
            QMessageBox.information(
                self,
                "Saved",
                f"Command bank for {make} {model} saved with {len(commands)} commands.",
            )
            self._load_command_banks()

        except Exception as e:
            logger.error(f"Failed to save command bank: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

    def _select_or_create_bank(self, make: str, model: str):
        """Select existing bank or prepare to create new one."""
        # Look for existing
        for i, bank in enumerate(self._all_banks):
            if bank["make"].lower() == make.lower() and bank["model"].lower() == model.lower():
                # Select in table
                for row in range(self.bank_table.rowCount()):
                    if self.bank_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == bank["id"]:
                        self.bank_table.selectRow(row)
                        return

        # Not found - prepare new
        self._on_new_bank()
        self.make_input.setText(make)
        self.model_input.setText(model)
        self._on_populate_defaults()
