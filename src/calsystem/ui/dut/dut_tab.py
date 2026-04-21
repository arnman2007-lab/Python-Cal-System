"""
DUT (Device Under Test) management tab.
"""

from datetime import datetime
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
    QTextEdit,
    QTabWidget,
    QFormLayout,
    QComboBox,
    QCheckBox,
    QSpinBox,
    QDateEdit,
    QMessageBox,
    QCompleter,
    QListView,
)
from PyQt6.QtCore import Qt, QDate, QStringListModel
from loguru import logger

from calsystem.database.connection import get_db
from calsystem.database.models import DUT, InputMethod, Procedure, CalibrationSession, DeviceModel


class DUTTab(QWidget):
    """Tab for managing Devices Under Test."""

    def __init__(self):
        super().__init__()
        self._current_dut_id: Optional[int] = None  # ID of DUT being edited, None for new
        self._selected_device_model_id: Optional[int] = None  # ID of DeviceModel if selected from autocomplete
        self._init_ui()
        self._connect_signals()

    def showEvent(self, event):
        """Called when tab becomes visible."""
        super().showEvent(event)
        # Refresh tables when tab is shown
        self._refresh_due_table()
        self._refresh_dut_table()
        self._load_procedures()
        self._load_device_models()  # Refresh model dropdown

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Enter asset number, make, model, or serial number..."
        )
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._on_search_click)
        search_layout.addWidget(self.search_btn)

        layout.addLayout(search_layout)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left - DUT list
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        # Upcoming due section
        due_group = QGroupBox("Calibrations Due")
        due_layout = QVBoxLayout(due_group)

        due_filter = QHBoxLayout()
        due_filter.addWidget(QLabel("Show:"))
        self.due_filter_combo = QComboBox()
        self.due_filter_combo.addItems(["Overdue", "Due This Week", "Due This Month", "All"])
        due_filter.addWidget(self.due_filter_combo)
        due_filter.addStretch()
        due_layout.addLayout(due_filter)

        self.due_table = QTableWidget()
        self.due_table.setColumnCount(4)
        self.due_table.setHorizontalHeaderLabels(
            ["Asset Number", "Make/Model", "Due Date", "Status"]
        )
        self.due_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.due_table.setMaximumHeight(150)
        self.due_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.due_table.itemDoubleClicked.connect(self._on_due_item_double_clicked)
        due_layout.addWidget(self.due_table)

        list_layout.addWidget(due_group)

        # All DUTs section
        all_group = QGroupBox("All Devices Under Test")
        all_layout = QVBoxLayout(all_group)

        self.dut_table = QTableWidget()
        self.dut_table.setColumnCount(6)
        self.dut_table.setHorizontalHeaderLabels(
            ["Asset Number", "Make", "Model", "Serial", "Last Cal", "Due Date"]
        )
        self.dut_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.dut_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.dut_table.itemSelectionChanged.connect(self._on_dut_selected)
        self.dut_table.itemDoubleClicked.connect(self._on_dut_double_clicked)
        all_layout.addWidget(self.dut_table)

        btn_layout = QHBoxLayout()
        self.add_dut_btn = QPushButton("Add New DUT")
        self.add_dut_btn.clicked.connect(self._on_add_dut)
        btn_layout.addWidget(self.add_dut_btn)

        self.delete_dut_btn = QPushButton("Delete")
        self.delete_dut_btn.clicked.connect(self._on_delete_dut)
        btn_layout.addWidget(self.delete_dut_btn)

        btn_layout.addStretch()

        self.start_cal_btn = QPushButton("Start Calibration")
        self.start_cal_btn.clicked.connect(self._on_start_calibration)
        btn_layout.addWidget(self.start_cal_btn)

        all_layout.addLayout(btn_layout)

        list_layout.addWidget(all_group)

        splitter.addWidget(list_widget)

        # Right - DUT details
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)

        self.details_tabs = QTabWidget()

        # Info tab
        info_tab = QWidget()
        info_layout = QFormLayout(info_tab)

        # Asset number with manual override
        asset_layout = QHBoxLayout()
        self.asset_input = QLineEdit()
        self.asset_input.setPlaceholderText("Auto-generated from Model-Serial")
        self.asset_input.setReadOnly(True)
        asset_layout.addWidget(self.asset_input)
        self.manual_asset_check = QCheckBox("Manual")
        self.manual_asset_check.setToolTip("Check to manually enter asset number")
        asset_layout.addWidget(self.manual_asset_check)
        info_layout.addRow("Asset Number:", asset_layout)

        # Model search with autocomplete - type model number to search
        self.model_search_input = QLineEdit()
        self.model_search_input.setPlaceholderText("Type model number to search (e.g., 789, 87V)...")
        self.model_search_input.setToolTip("Start typing a model number to see matching devices from the library")
        info_layout.addRow("Find Model:", self.model_search_input)

        # Autocomplete setup - will be populated in _load_device_models
        self._model_data = {}  # Maps display string to model info dict
        self.model_completer = QCompleter()
        self.model_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.model_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.model_completer.setMaxVisibleItems(10)
        # Use popup to show full text
        popup = QListView()
        popup.setMinimumWidth(350)
        self.model_completer.setPopup(popup)
        self.model_search_input.setCompleter(self.model_completer)

        # Make input (auto-filled from model search or manual entry)
        self.make_input = QLineEdit()
        self.make_input.setPlaceholderText("e.g., Fluke, Keysight")
        info_layout.addRow("Make:", self.make_input)

        # Model input (auto-filled from model search or manual entry)
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("e.g., 87V, 34401A")
        info_layout.addRow("Model:", self.model_input)

        self.serial_input = QLineEdit()
        self.serial_input.setPlaceholderText("Serial number")
        info_layout.addRow("Serial Number:", self.serial_input)

        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(80)
        info_layout.addRow("Description:", self.description_input)

        # Customer info (for reports) - default to N/A
        self.customer_id_input = QLineEdit()
        self.customer_id_input.setPlaceholderText("Customer identifier")
        self.customer_id_input.setText("N/A")
        info_layout.addRow("Customer ID:", self.customer_id_input)

        self.customer_serial_input = QLineEdit()
        self.customer_serial_input.setPlaceholderText("Customer's serial number (if different)")
        self.customer_serial_input.setText("N/A")
        info_layout.addRow("Customer S/N:", self.customer_serial_input)

        self.details_tabs.addTab(info_tab, "Information")

        # Capabilities tab
        cap_tab = QWidget()
        cap_layout = QFormLayout(cap_tab)

        self.remote_capable_check = QCheckBox("Device supports remote control")
        cap_layout.addRow("Remote Capable:", self.remote_capable_check)

        self.input_method_combo = QComboBox()
        self.input_method_combo.addItems(["Keyboard Entry", "Remote Reading", "Webcam OCR"])
        cap_layout.addRow("Preferred Input:", self.input_method_combo)

        self.ocr_mode_combo = QComboBox()
        self.ocr_mode_combo.addItems(["Standard OCR", "Seven-Segment OCR"])
        cap_layout.addRow("OCR Mode:", self.ocr_mode_combo)

        self.details_tabs.addTab(cap_tab, "Capabilities")

        # Calibration tab
        cal_tab = QWidget()
        cal_layout = QFormLayout(cal_tab)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 3650)
        self.interval_spin.setValue(365)
        self.interval_spin.setSuffix(" days")
        cal_layout.addRow("Cal Interval:", self.interval_spin)

        self.last_cal_date = QDateEdit()
        self.last_cal_date.setCalendarPopup(True)
        self.last_cal_date.setDate(QDate.currentDate())
        cal_layout.addRow("Last Calibration:", self.last_cal_date)

        self.due_date = QDateEdit()
        self.due_date.setCalendarPopup(True)
        cal_layout.addRow("Next Due:", self.due_date)

        self.procedure_combo = QComboBox()
        self.procedure_combo.addItem("(No procedure assigned)")
        cal_layout.addRow("Assigned Procedure:", self.procedure_combo)

        self.details_tabs.addTab(cal_tab, "Calibration")

        # History tab
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(
            ["Date", "Work Order", "Technician", "Result"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        history_layout.addWidget(self.history_table)

        history_btn_layout = QHBoxLayout()
        self.view_report_btn = QPushButton("View Report")
        history_btn_layout.addWidget(self.view_report_btn)
        history_btn_layout.addStretch()
        history_layout.addLayout(history_btn_layout)

        self.details_tabs.addTab(history_tab, "History")

        details_layout.addWidget(self.details_tabs)

        # Save/Cancel buttons
        save_layout = QHBoxLayout()
        save_layout.addStretch()

        self.save_btn = QPushButton("Save Changes")
        self.save_btn.clicked.connect(self._on_save)
        save_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        save_layout.addWidget(self.cancel_btn)

        details_layout.addLayout(save_layout)

        splitter.addWidget(details_widget)

        # Set splitter sizes
        splitter.setSizes([400, 400])

        layout.addWidget(splitter)

    def _connect_signals(self):
        """Connect signals for auto-generation and visibility toggles."""
        # Auto-generate asset number when model or serial changes
        self.model_input.textChanged.connect(self._update_asset_number)
        self.serial_input.textChanged.connect(self._update_asset_number)

        # Manual override checkbox toggles asset input editability
        self.manual_asset_check.toggled.connect(self._on_manual_asset_toggled)

        # Model autocomplete - when user selects from list, fill in fields
        self.model_completer.activated.connect(self._on_model_selected_from_completer)

        # Remote capable checkbox toggles input method visibility
        self.remote_capable_check.toggled.connect(self._on_remote_capable_toggled)

        # Auto-calculate due date when interval or last cal date changes
        self.interval_spin.valueChanged.connect(self._update_due_date)
        self.last_cal_date.dateChanged.connect(self._update_due_date)

        # Due filter dropdown
        self.due_filter_combo.currentTextChanged.connect(self._on_due_filter_changed)

        # Initially hide input method if not remote capable
        self._on_remote_capable_toggled(False)

        # Load models into autocomplete
        self._load_device_models()

    def _load_procedures(self):
        """Load procedures into the procedure combo."""
        current_selection = self.procedure_combo.currentData()
        self.procedure_combo.clear()
        self.procedure_combo.addItem("(No procedure assigned)", None)

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                # Get current DUT make/model for filtering
                dut_make = self.make_input.text().strip().lower() if self.make_input else ""
                dut_model = self.model_input.text().strip().lower() if self.model_input else ""

                procedures = session.query(Procedure).order_by(Procedure.name).all()

                matching_procs = []
                other_procs = []

                for proc in procedures:
                    # Check if procedure targets this DUT make/model
                    proc_make = (proc.target_make or "").lower()
                    proc_model = (proc.target_model or "").lower()

                    matches = False
                    if proc_make and proc_model and dut_make and dut_model:
                        matches = proc_make == dut_make and proc_model == dut_model
                    elif proc_make and dut_make:
                        matches = proc_make == dut_make

                    if matches:
                        matching_procs.append(proc)
                    else:
                        other_procs.append(proc)

                # Add matching procedures first
                if matching_procs:
                    self.procedure_combo.addItem("--- Matching Procedures ---", None)
                    for proc in matching_procs:
                        label = f"{proc.name}"
                        if proc.target_make or proc.target_model:
                            label += f" ({proc.target_make or ''} {proc.target_model or ''})".strip()
                        self.procedure_combo.addItem(label, proc.id)

                # Add other procedures
                if other_procs:
                    self.procedure_combo.addItem("--- Other Procedures ---", None)
                    for proc in other_procs:
                        label = f"{proc.name}"
                        if proc.target_make or proc.target_model:
                            label += f" ({proc.target_make or ''} {proc.target_model or ''})".strip()
                        self.procedure_combo.addItem(label, proc.id)

                # Restore selection if valid
                if current_selection:
                    for i in range(self.procedure_combo.count()):
                        if self.procedure_combo.itemData(i) == current_selection:
                            self.procedure_combo.setCurrentIndex(i)
                            break

                logger.debug(f"Loaded {len(procedures)} procedures")

        except Exception as e:
            logger.error(f"Failed to load procedures: {e}")

    def _load_device_models(self):
        """Load device models into the autocomplete."""
        self._model_data = {}  # Clear existing data

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                models = session.query(DeviceModel).join(
                    DeviceModel.manufacturer
                ).order_by(
                    DeviceModel.model_number
                ).all()

                completion_list = []
                for model in models:
                    make = model.manufacturer.name if model.manufacturer else "Unknown"
                    # Display format: "789 - Fluke Processmeter" (model first for easy typing)
                    label = f"{model.model_number} - {make}"
                    if model.description:
                        label += f" {model.description}"

                    completion_list.append(label)
                    # Store model data for lookup when selected
                    self._model_data[label] = {
                        "id": model.id,
                        "make": make,
                        "model": model.model_number,
                        "description": model.description or "",
                        "remote_capable": model.remote_capable or False,
                    }

                # Set up completer with the list
                string_model = QStringListModel(completion_list)
                self.model_completer.setModel(string_model)

                logger.debug(f"Loaded {len(models)} device models into autocomplete")

        except Exception as e:
            logger.error(f"Failed to load device models: {e}")

    def _on_model_selected_from_completer(self, text: str):
        """Handle selection from model autocomplete."""
        if text not in self._model_data:
            return

        model_info = self._model_data[text]

        # Auto-fill the fields
        self.make_input.setText(model_info["make"])
        self.model_input.setText(model_info["model"])
        self.description_input.setPlainText(model_info["description"])
        self.remote_capable_check.setChecked(model_info["remote_capable"])

        # Clear the search field after selection
        self.model_search_input.clear()

        # Update asset number
        self._update_asset_number()

        # Store the selected model ID for saving
        self._selected_device_model_id = model_info["id"]

        logger.debug(f"Selected model from autocomplete: {model_info['make']} {model_info['model']}")

    def _update_asset_number(self):
        """Auto-generate asset number from Model-SerialNumber."""
        if self.manual_asset_check.isChecked():
            return  # Don't auto-update if manual override is enabled

        serial = self.serial_input.text().strip()
        model = self.model_input.text().strip()

        if model and serial:
            asset = f"{model}-{serial}"
            self.asset_input.setText(asset)
        elif model:
            self.asset_input.setText(f"{model}-")
        elif serial:
            self.asset_input.setText(f"-{serial}")
        else:
            self.asset_input.clear()

    def _on_manual_asset_toggled(self, checked: bool):
        """Handle manual asset number override toggle."""
        self.asset_input.setReadOnly(not checked)
        if checked:
            self.asset_input.setPlaceholderText("Enter custom asset number")
            self.asset_input.setFocus()
        else:
            self.asset_input.setPlaceholderText("Auto-generated from Model-Serial")
            self._update_asset_number()

    def _on_remote_capable_toggled(self, checked: bool):
        """Show/hide input method dropdown based on remote capability."""
        self.input_method_combo.setVisible(checked)
        # Find the label for input method and hide it too
        for i in range(self.input_method_combo.parent().layout().rowCount()):
            item = self.input_method_combo.parent().layout().itemAt(i, QFormLayout.ItemRole.LabelRole)
            if item and item.widget():
                label = item.widget()
                if isinstance(label, QLabel) and "Input" in label.text():
                    label.setVisible(checked)
                    break

    def _update_due_date(self):
        """Auto-calculate due date as Last Cal + Interval."""
        last_cal = self.last_cal_date.date()
        interval = self.interval_spin.value()
        due = last_cal.addDays(interval)
        self.due_date.setDate(due)

    def _on_due_filter_changed(self, filter_text: str):
        """Handle due filter dropdown change."""
        logger.debug(f"Due filter changed to: {filter_text}")
        self._refresh_due_table()

    def _refresh_due_table(self):
        """Refresh the due table with DUTs sorted by due date."""
        db = get_db()
        if not db.is_connected:
            return

        self.due_table.setRowCount(0)
        filter_text = self.due_filter_combo.currentText()
        today = datetime.now().date()

        try:
            with db.session() as session:
                query = session.query(DUT).filter(DUT.next_due_date.isnot(None))

                # Apply filter
                if filter_text == "Overdue":
                    query = query.filter(DUT.next_due_date < datetime.now())
                elif filter_text == "Due This Week":
                    week_end = datetime.now() + __import__('datetime').timedelta(days=7)
                    query = query.filter(DUT.next_due_date <= week_end)
                elif filter_text == "Due This Month":
                    month_end = datetime.now() + __import__('datetime').timedelta(days=30)
                    query = query.filter(DUT.next_due_date <= month_end)
                # "All" shows everything

                results = query.order_by(DUT.next_due_date).limit(50).all()

                for dut in results:
                    row = self.due_table.rowCount()
                    self.due_table.insertRow(row)

                    # Store DUT ID
                    asset_item = QTableWidgetItem(dut.asset_number)
                    asset_item.setData(Qt.ItemDataRole.UserRole, dut.id)
                    self.due_table.setItem(row, 0, asset_item)

                    self.due_table.setItem(row, 1, QTableWidgetItem(f"{dut.make} {dut.model}"))

                    due_date = dut.next_due_date
                    due_str = due_date.strftime("%Y-%m-%d") if due_date else ""
                    due_item = QTableWidgetItem(due_str)
                    self.due_table.setItem(row, 2, due_item)

                    # Determine status and color
                    if due_date:
                        due_date_only = due_date.date() if hasattr(due_date, 'date') else due_date
                        days_until = (due_date_only - today).days

                        if days_until < 0:
                            status = "OVERDUE"
                            color = Qt.GlobalColor.red
                        elif days_until <= 7:
                            status = f"Due in {days_until}d"
                            color = Qt.GlobalColor.darkYellow
                        else:
                            status = f"Due in {days_until}d"
                            color = Qt.GlobalColor.darkGreen
                    else:
                        status = "Unknown"
                        color = Qt.GlobalColor.gray

                    status_item = QTableWidgetItem(status)
                    status_item.setForeground(color)
                    self.due_table.setItem(row, 3, status_item)

                logger.debug(f"Due table showing {len(results)} DUTs")

        except Exception as e:
            logger.error(f"Failed to refresh due table: {e}")

    def _on_search(self, text: str):
        """Handle search text change - filters as user types."""
        self._search_duts(text)

    def _on_search_click(self):
        """Handle search button click."""
        search_text = self.search_input.text()
        logger.info(f"Searching for: {search_text}")
        self._search_duts(search_text)

    def _search_duts(self, search_text: str):
        """Search DUTs in database with partial matching."""
        db = get_db()
        if not db.is_connected:
            return

        self.dut_table.setRowCount(0)

        try:
            with db.session() as session:
                query = session.query(DUT)

                if search_text.strip():
                    # Use LIKE for partial matching on multiple fields
                    pattern = f"%{search_text}%"
                    query = query.filter(
                        (DUT.asset_number.ilike(pattern)) |
                        (DUT.make.ilike(pattern)) |
                        (DUT.model.ilike(pattern)) |
                        (DUT.serial_number.ilike(pattern))
                    )

                # Order by asset number
                results = query.order_by(DUT.asset_number).limit(100).all()

                for dut in results:
                    row = self.dut_table.rowCount()
                    self.dut_table.insertRow(row)

                    # Store DUT ID in first item for later reference
                    asset_item = QTableWidgetItem(dut.asset_number)
                    asset_item.setData(Qt.ItemDataRole.UserRole, dut.id)
                    self.dut_table.setItem(row, 0, asset_item)

                    self.dut_table.setItem(row, 1, QTableWidgetItem(dut.make or ""))
                    self.dut_table.setItem(row, 2, QTableWidgetItem(dut.model or ""))
                    self.dut_table.setItem(row, 3, QTableWidgetItem(dut.serial_number or ""))

                    # Format dates
                    last_cal = ""
                    if dut.last_calibration_date:
                        last_cal = dut.last_calibration_date.strftime("%Y-%m-%d")
                    self.dut_table.setItem(row, 4, QTableWidgetItem(last_cal))

                    due_date = ""
                    if dut.next_due_date:
                        due_date = dut.next_due_date.strftime("%Y-%m-%d")
                    self.dut_table.setItem(row, 5, QTableWidgetItem(due_date))

                logger.debug(f"Search found {len(results)} DUTs")

        except Exception as e:
            logger.error(f"Search failed: {e}")

    def _on_due_item_double_clicked(self, item):
        """Handle double-click on due item - loads DUT details."""
        row = item.row()
        asset_item = self.due_table.item(row, 0)
        if asset_item:
            dut_id = asset_item.data(Qt.ItemDataRole.UserRole)
            if dut_id:
                self._load_dut_details(dut_id)

    def _on_dut_selected(self):
        """Handle DUT selection change."""
        selected = self.dut_table.selectedItems()
        if selected:
            row = selected[0].row()
            asset_item = self.dut_table.item(row, 0)
            if asset_item:
                dut_id = asset_item.data(Qt.ItemDataRole.UserRole)
                logger.debug(f"Selected DUT ID: {dut_id}")

    def _on_dut_double_clicked(self, item):
        """Handle double-click on DUT - loads details into form."""
        row = item.row()
        asset_item = self.dut_table.item(row, 0)
        if asset_item:
            dut_id = asset_item.data(Qt.ItemDataRole.UserRole)
            if dut_id:
                self._load_dut_details(dut_id)

    def _load_dut_details(self, dut_id: int):
        """Load DUT details into the form."""
        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                dut = session.query(DUT).filter(DUT.id == dut_id).first()
                if not dut:
                    QMessageBox.warning(self, "Not Found", "DUT not found in database.")
                    return

                self._current_dut_id = dut.id
                self._selected_device_model_id = dut.device_model_id  # Preserve model link if any

                # Populate Information tab
                self.manual_asset_check.setChecked(True)  # Enable editing
                self.asset_input.setText(dut.asset_number)
                self.model_search_input.clear()  # Clear search field
                self.make_input.setText(dut.make or "")
                self.model_input.setText(dut.model or "")
                self.serial_input.setText(dut.serial_number or "")
                self.description_input.setPlainText(dut.description or "")

                # Customer fields - show N/A if empty
                self.customer_id_input.setText(dut.customer_id or "N/A")
                self.customer_serial_input.setText(dut.customer_serial or "N/A")

                # Populate Capabilities tab
                self.remote_capable_check.setChecked(dut.remote_capable or False)

                # Map InputMethod enum to combo index
                input_method_index = {
                    InputMethod.KEYBOARD: 0,
                    InputMethod.REMOTE: 1,
                    InputMethod.WEBCAM: 2,
                }.get(dut.preferred_input_method, 0)
                self.input_method_combo.setCurrentIndex(input_method_index)

                # OCR mode
                ocr_index = 0 if dut.ocr_mode == "standard" else 1
                self.ocr_mode_combo.setCurrentIndex(ocr_index)

                # Populate Calibration tab
                self.interval_spin.setValue(dut.calibration_interval_days or 365)

                if dut.last_calibration_date:
                    self.last_cal_date.setDate(QDate(
                        dut.last_calibration_date.year,
                        dut.last_calibration_date.month,
                        dut.last_calibration_date.day,
                    ))

                if dut.next_due_date:
                    self.due_date.setDate(QDate(
                        dut.next_due_date.year,
                        dut.next_due_date.month,
                        dut.next_due_date.day,
                    ))

                # Select assigned procedure
                self._load_procedures()  # Refresh list based on DUT make/model
                if dut.default_procedure_id:
                    for i in range(self.procedure_combo.count()):
                        if self.procedure_combo.itemData(i) == dut.default_procedure_id:
                            self.procedure_combo.setCurrentIndex(i)
                            break

                # Load calibration history
                self._load_calibration_history(dut_id)

                logger.info(f"Loaded DUT: {dut.asset_number}")

        except Exception as e:
            logger.error(f"Failed to load DUT: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load DUT:\n{e}")

    def _on_add_dut(self):
        """Add a new DUT - clears form for new entry."""
        logger.info("Adding new DUT")
        self._current_dut_id = None  # Mark as new DUT
        self._selected_device_model_id = None  # No model selected yet

        # Clear all form fields
        self.asset_input.clear()
        self.model_search_input.clear()
        self.make_input.clear()
        self.model_input.clear()
        self.serial_input.clear()
        self.description_input.clear()

        # Set customer fields to N/A by default
        self.customer_id_input.setText("N/A")
        self.customer_serial_input.setText("N/A")

        # Reset checkboxes and combos
        self.manual_asset_check.setChecked(False)
        self.remote_capable_check.setChecked(False)
        self.input_method_combo.setCurrentIndex(0)  # Keyboard Entry
        self.ocr_mode_combo.setCurrentIndex(0)  # Standard OCR

        # Reset calibration fields
        self.interval_spin.setValue(365)
        self.last_cal_date.setDate(QDate.currentDate())
        self.due_date.setDate(QDate.currentDate().addDays(365))
        self.procedure_combo.setCurrentIndex(0)

        # Clear history table
        self.history_table.setRowCount(0)

        # Focus on model search field to start entry
        self.model_search_input.setFocus()
        self.details_tabs.setCurrentIndex(0)  # Show Information tab

    def _on_delete_dut(self):
        """Delete selected DUT."""
        selected = self.dut_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a DUT to delete.")
            return

        row = selected[0].row()
        asset = self.dut_table.item(row, 0).text()

        reply = QMessageBox.question(
            self,
            "Delete DUT",
            f"Are you sure you want to delete DUT {asset}?\n\n"
            "This will also delete all calibration history for this device.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info(f"Deleting DUT: {asset}")
            # TODO: Delete from database

    def _on_start_calibration(self):
        """Start calibration for selected DUT."""
        selected = self.dut_table.selectedItems()
        if not selected:
            QMessageBox.warning(
                self, "No Selection", "Please select a DUT to calibrate."
            )
            return

        row = selected[0].row()
        asset = self.dut_table.item(row, 0).text()
        logger.info(f"Starting calibration for: {asset}")
        # TODO: Switch to execution tab with this DUT

    def _on_save(self):
        """Save DUT to database."""
        # Validate required fields
        asset = self.asset_input.text().strip()
        make = self.make_input.text().strip()
        model = self.model_input.text().strip()

        # Get device_model_id if user selected from autocomplete
        device_model_id = getattr(self, '_selected_device_model_id', None)

        if not asset:
            QMessageBox.warning(self, "Validation Error", "Asset number is required.")
            return

        if not make or not model:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Make and Model are required fields.",
            )
            return

        db = get_db()
        if not db.is_connected:
            QMessageBox.critical(
                self,
                "Database Error",
                "Not connected to database. Please configure database settings.",
            )
            return

        # Map input method combo to enum
        input_method_map = {
            0: InputMethod.KEYBOARD,
            1: InputMethod.REMOTE,
            2: InputMethod.WEBCAM,
        }
        input_method = input_method_map.get(
            self.input_method_combo.currentIndex(),
            InputMethod.KEYBOARD,
        )

        # Map OCR mode
        ocr_mode = "standard" if self.ocr_mode_combo.currentIndex() == 0 else "seven_segment"

        try:
            with db.session() as session:
                if self._current_dut_id:
                    # Update existing DUT
                    dut = session.query(DUT).filter(DUT.id == self._current_dut_id).first()
                    if not dut:
                        QMessageBox.warning(self, "Error", "DUT not found in database.")
                        return
                else:
                    # Check for duplicate asset number
                    existing = session.query(DUT).filter(DUT.asset_number == asset).first()
                    if existing:
                        QMessageBox.warning(
                            self,
                            "Duplicate Asset Number",
                            f"A DUT with asset number '{asset}' already exists.",
                        )
                        return

                    dut = DUT(asset_number=asset)
                    session.add(dut)

                # Update DUT fields
                dut.asset_number = asset
                dut.make = make
                dut.model = model
                dut.device_model_id = device_model_id  # Link to DeviceModel if using dropdown
                dut.serial_number = self.serial_input.text().strip() or None
                dut.description = self.description_input.toPlainText().strip() or None
                dut.customer_id = self.customer_id_input.text().strip() or None
                dut.customer_serial = self.customer_serial_input.text().strip() or None
                dut.remote_capable = self.remote_capable_check.isChecked()
                dut.preferred_input_method = input_method
                dut.ocr_mode = ocr_mode
                dut.calibration_interval_days = self.interval_spin.value()

                # Convert QDate to datetime
                last_cal = self.last_cal_date.date()
                dut.last_calibration_date = datetime(
                    last_cal.year(), last_cal.month(), last_cal.day()
                )

                due = self.due_date.date()
                dut.next_due_date = datetime(due.year(), due.month(), due.day())

                # Save assigned procedure
                procedure_id = self.procedure_combo.currentData()
                dut.default_procedure_id = procedure_id if procedure_id else None

                session.flush()
                self._current_dut_id = dut.id

            logger.info(f"Saved DUT: {asset} (ID: {self._current_dut_id})")
            QMessageBox.information(
                self,
                "DUT Saved",
                f"Device '{make} {model}' saved successfully.\n\nAsset Number: {asset}",
            )

            # Refresh the DUT table
            self._refresh_dut_table()

        except Exception as e:
            logger.error(f"Failed to save DUT: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save DUT:\n{e}",
            )

    def _refresh_dut_table(self):
        """Refresh the DUT table from database."""
        logger.info("Refreshing DUT table")
        # Use current search text or show all
        self._search_duts(self.search_input.text())

    def _on_cancel(self):
        """Cancel changes."""
        logger.debug("Canceling DUT changes")
        # Reload original data if editing existing DUT
        if self._current_dut_id:
            self._load_dut_details(self._current_dut_id)

    def _load_calibration_history(self, dut_id: int):
        """Load calibration history for a DUT."""
        self.history_table.setRowCount(0)

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                sessions = session.query(CalibrationSession).filter(
                    CalibrationSession.dut_id == dut_id
                ).order_by(CalibrationSession.started_at.desc()).limit(50).all()

                for cal_session in sessions:
                    row = self.history_table.rowCount()
                    self.history_table.insertRow(row)

                    # Date
                    date_str = cal_session.started_at.strftime("%Y-%m-%d") if cal_session.started_at else "--"
                    date_item = QTableWidgetItem(date_str)
                    date_item.setData(Qt.ItemDataRole.UserRole, cal_session.id)
                    self.history_table.setItem(row, 0, date_item)

                    # Work Order
                    self.history_table.setItem(row, 1, QTableWidgetItem(cal_session.work_order or "--"))

                    # Technician
                    self.history_table.setItem(row, 2, QTableWidgetItem(cal_session.technician_name or "--"))

                    # Result - handle status being either enum or string
                    status_val = cal_session.status.value if hasattr(cal_session.status, 'value') else str(cal_session.status or "")
                    result = (cal_session.overall_result or status_val).title()
                    result_item = QTableWidgetItem(result)
                    if result.lower() == "pass":
                        result_item.setForeground(Qt.GlobalColor.darkGreen)
                    elif result.lower() == "fail":
                        result_item.setForeground(Qt.GlobalColor.red)
                    self.history_table.setItem(row, 3, result_item)

                logger.debug(f"Loaded {len(sessions)} calibration history records")

        except Exception as e:
            logger.error(f"Failed to load calibration history: {e}")
