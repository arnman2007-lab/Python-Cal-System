"""
Dialog for adding a new standard to the workstation.
MetCal-style workflow: Search model -> Enter STD # -> Select GPIB address -> Save (with verify)
"""

from typing import Optional, List

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
    QLabel,
    QListWidget,
    QListWidgetItem,
)
from PyQt6.QtCore import Qt
from loguru import logger

from calsystem.database.connection import get_db
from calsystem.database.models import Standard, WorkstationConfig, WorkstationStandard, DeviceGroupType
from calsystem.config.settings import get_settings
from calsystem.instruments.known_instruments import (
    KNOWN_INSTRUMENTS,
    KnownInstrument,
    DeviceType,
)
from calsystem.instruments.visa_manager import get_visa_manager, PYVISA_AVAILABLE


# Map DeviceType to DeviceGroupType
DEVICE_TYPE_MAP = {
    DeviceType.CALIBRATOR: DeviceGroupType.CALIBRATOR,
    DeviceType.DMM: DeviceGroupType.DMM,
    DeviceType.COUNTER: DeviceGroupType.COUNTER,
    DeviceType.OSCILLOSCOPE: DeviceGroupType.OTHER,
    DeviceType.POWER_SUPPLY: DeviceGroupType.OTHER,
    DeviceType.SIGNAL_GENERATOR: DeviceGroupType.OTHER,
    DeviceType.OTHER: DeviceGroupType.OTHER,
}


class AddStandardDialog(QDialog):
    """Dialog for adding a new workstation standard."""

    def __init__(
        self,
        parent=None,
        available_addresses: List[str] = None,
        used_models: List[str] = None,
        # Legacy parameters for backward compatibility
        address: str = "",
        manufacturer: str = "",
        model: str = "",
        serial_number: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("Add Standard")
        self.setMinimumWidth(550)
        self.setMinimumHeight(500)
        self.setModal(True)

        self._available_addresses = available_addresses or []
        self._used_models = used_models or []
        self._selected_instrument: Optional[KnownInstrument] = None
        self._all_instruments: List[KnownInstrument] = []

        # Legacy pre-fill values
        self._legacy_address = address
        self._legacy_manufacturer = manufacturer
        self._legacy_model = model
        self._legacy_serial = serial_number

        self._init_ui()
        self._populate_models()
        self._populate_addresses()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Model Selection Group
        model_group = QGroupBox("1. Search and Select Instrument Model")
        model_layout = QVBoxLayout()

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to search (e.g., '3458', '5520', 'Fluke')...")
        self.search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_input)
        model_layout.addLayout(search_layout)

        # Model list
        self.model_list = QListWidget()
        self.model_list.setMinimumHeight(150)
        self.model_list.itemClicked.connect(self._on_model_clicked)
        self.model_list.itemDoubleClicked.connect(self._on_model_double_clicked)
        model_layout.addWidget(self.model_list)

        # Selected model info
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel("Selected:"))
        self.selected_label = QLabel("-")
        self.selected_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(self.selected_label)
        info_layout.addStretch()
        self.type_label = QLabel("")
        info_layout.addWidget(self.type_label)
        model_layout.addLayout(info_layout)

        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # Standard Info Group
        info_group = QGroupBox("2. Enter Standard Information")
        info_layout = QFormLayout()

        self.std_id_input = QLineEdit()
        self.std_id_input.setPlaceholderText("Enter STD # / Barcode / Asset ID (required)")
        info_layout.addRow("STD # (Barcode):", self.std_id_input)

        self.serial_input = QLineEdit()
        self.serial_input.setPlaceholderText("Serial number (optional)")
        info_layout.addRow("Serial Number:", self.serial_input)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Connection Group
        conn_group = QGroupBox("3. Select GPIB/VISA Address")
        conn_layout = QFormLayout()

        # Address dropdown
        addr_row = QHBoxLayout()
        self.address_combo = QComboBox()
        self.address_combo.setEditable(True)
        self.address_combo.setMinimumWidth(250)
        addr_row.addWidget(self.address_combo)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_addresses)
        addr_row.addWidget(self.refresh_btn)

        conn_layout.addRow("VISA Address:", addr_row)

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # Status label
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _populate_models(self):
        """Populate the model list with known instruments."""
        # Filter out already-used models
        self._all_instruments = [
            inst for inst in KNOWN_INSTRUMENTS
            if inst.display_name not in self._used_models
        ]

        # Show all initially
        self._update_model_list("")

        # Handle legacy pre-fill
        if self._legacy_manufacturer and self._legacy_model:
            search = f"{self._legacy_model}"
            self.search_input.setText(search)

    def _update_model_list(self, search_text: str):
        """Update the model list based on search text."""
        self.model_list.clear()

        search_lower = search_text.lower()

        # Filter instruments
        if search_lower:
            filtered = [
                inst for inst in self._all_instruments
                if search_lower in inst.search_key
            ]
        else:
            filtered = self._all_instruments

        # Group by device type
        by_type = {}
        for inst in filtered:
            type_name = inst.device_type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(inst)

        # Add items grouped by type
        for type_name in ["Calibrator", "DMM", "Counter", "Signal Generator", "Power Supply", "Oscilloscope", "Other"]:
            if type_name in by_type:
                # Add header
                header = QListWidgetItem(f"── {type_name} ──")
                header.setFlags(Qt.ItemFlag.NoItemFlags)  # Not selectable
                header.setForeground(Qt.GlobalColor.gray)
                self.model_list.addItem(header)

                for inst in sorted(by_type[type_name], key=lambda x: x.display_name):
                    item = QListWidgetItem(f"  {inst.display_name} - {inst.description}")
                    item.setData(Qt.ItemDataRole.UserRole, inst)
                    self.model_list.addItem(item)

    def _on_search_changed(self, text: str):
        """Handle search text change."""
        self._update_model_list(text)

    def _on_model_clicked(self, item: QListWidgetItem):
        """Handle model selection."""
        inst = item.data(Qt.ItemDataRole.UserRole)
        if inst:
            self._selected_instrument = inst
            self.selected_label.setText(inst.display_name)
            self.type_label.setText(f"({inst.device_type.value})")

    def _on_model_double_clicked(self, item: QListWidgetItem):
        """Handle model double-click - select and move to next field."""
        self._on_model_clicked(item)
        if self._selected_instrument:
            self.std_id_input.setFocus()

    def _populate_addresses(self):
        """Populate the address dropdown."""
        self.address_combo.clear()

        if self._available_addresses:
            for addr in self._available_addresses:
                self.address_combo.addItem(addr)

        # Handle legacy pre-fill
        if self._legacy_address:
            idx = self.address_combo.findText(self._legacy_address)
            if idx >= 0:
                self.address_combo.setCurrentIndex(idx)
            else:
                self.address_combo.setEditText(self._legacy_address)

        if self._legacy_serial:
            self.serial_input.setText(self._legacy_serial)

    def _refresh_addresses(self):
        """Refresh the list of available VISA addresses."""
        self.address_combo.clear()
        self.status_label.setText("Scanning...")
        self.status_label.setStyleSheet("color: blue;")

        try:
            visa = get_visa_manager()
            addresses = visa.scan()
            for addr in addresses:
                self.address_combo.addItem(addr)

            self.status_label.setText(f"Found {len(addresses)} addresses")
            self.status_label.setStyleSheet("color: green;")
        except Exception as e:
            logger.error(f"Failed to scan addresses: {e}")
            self.status_label.setText("Scan failed")
            self.status_label.setStyleSheet("color: red;")

    def _verify_connection(self, address: str) -> tuple[bool, str]:
        """
        Verify connection to the selected instrument.
        Returns (success, message).
        """
        if not self._selected_instrument:
            return False, "No model selected"

        if not PYVISA_AVAILABLE:
            return True, "VISA not available - skipping verification"

        try:
            visa = get_visa_manager()
            if not visa.is_initialized:
                visa.initialize()

            # Use the correct ID command for this instrument
            id_cmd = self._selected_instrument.id_command

            # Query the instrument
            inst = visa._rm.open_resource(address)
            inst.timeout = 5000

            # HP 3458A and similar older HP instruments need setup commands
            if id_cmd == "ID?":
                inst.write("RESET")
                inst.write("END ALWAYS")

            response = inst.query(id_cmd).strip()
            inst.close()

            # Check if response contains expected model
            model = self._selected_instrument.model.upper()
            if model in response.upper():
                return True, f"Verified: {response[:50]}"
            else:
                return True, f"Connected (response: {response[:30]})"

        except Exception as e:
            return False, f"Connection failed: {str(e)[:50]}"

    def _on_save(self):
        """Save the standard to the database (with verification)."""
        if not self._selected_instrument:
            QMessageBox.warning(self, "No Model", "Please select an instrument model.")
            return

        address = self.address_combo.currentText().strip()
        if not address:
            QMessageBox.warning(self, "No Address", "Please select or enter a VISA address.")
            return

        std_id = self.std_id_input.text().strip()
        if not std_id:
            QMessageBox.warning(self, "No STD #", "Please enter a STD # / Barcode.")
            return

        # Verify connection before saving
        self.status_label.setText("Verifying connection...")
        self.status_label.setStyleSheet("color: blue;")

        # Force UI update
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        verified, verify_msg = self._verify_connection(address)

        if not verified:
            reply = QMessageBox.question(
                self,
                "Connection Failed",
                f"Could not verify connection to instrument:\n{verify_msg}\n\n"
                "Do you want to add the standard anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.status_label.setText(verify_msg)
                self.status_label.setStyleSheet("color: red;")
                return

        self.status_label.setText(verify_msg)
        self.status_label.setStyleSheet("color: green;")

        # Save to database
        inst = self._selected_instrument
        device_group = DEVICE_TYPE_MAP.get(inst.device_type, DeviceGroupType.OTHER)

        db = get_db()
        if not db.is_connected:
            QMessageBox.critical(self, "Database Error", "Not connected to database.")
            return

        try:
            with db.session() as session:
                # Check if standard with same STD ID already exists
                existing = session.query(Standard).filter(
                    Standard.std_id == std_id
                ).first()

                if existing:
                    QMessageBox.warning(
                        self,
                        "Duplicate STD #",
                        f"A standard with STD # '{std_id}' already exists.",
                    )
                    return

                # Create new standard
                standard = Standard(
                    make=inst.make,
                    model=inst.model,
                    serial_number=self.serial_input.text().strip() or None,
                    std_id=std_id,
                    device_group=device_group,
                    visa_address=address,
                )
                session.add(standard)
                session.flush()
                logger.info(f"Created new standard: {inst.display_name} (STD# {std_id})")

                # Get or create workstation config
                settings = get_settings()
                workstation_name = settings.workstation_name or "Default Workstation"

                workstation = session.query(WorkstationConfig).filter(
                    WorkstationConfig.name == workstation_name
                ).first()

                if not workstation:
                    workstation = WorkstationConfig(name=workstation_name)
                    session.add(workstation)
                    session.flush()
                    logger.info(f"Created new workstation config: {workstation_name}")

                # Create association
                assoc = WorkstationStandard(
                    workstation_id=workstation.id,
                    standard_id=standard.id,
                    visa_address=address,
                )
                session.add(assoc)
                logger.info("Created workstation-standard association")

            QMessageBox.information(
                self,
                "Standard Added",
                f"Standard '{inst.display_name}' (STD# {std_id}) has been added.\n\n{verify_msg}",
            )
            self.accept()

        except Exception as e:
            logger.error(f"Failed to save standard: {e}")
            QMessageBox.critical(self, "Database Error", f"Failed to save standard:\n{e}")

    @property
    def standard_data(self) -> dict:
        """Get the entered standard data."""
        inst = self._selected_instrument
        return {
            "make": inst.make if inst else "",
            "model": inst.model if inst else "",
            "serial_number": self.serial_input.text().strip(),
            "std_id": self.std_id_input.text().strip(),
            "address": self.address_combo.currentText().strip(),
            "group": inst.device_type.value if inst else "Other",
        }
