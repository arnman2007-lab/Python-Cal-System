"""
Libraries tab - Manage wiring diagram images by calibrator + DUT combination.
"""

import os
import sys
from pathlib import Path
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
    QFileDialog,
    QDialog,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import QGraphicsOpacityEffect
from loguru import logger

from calsystem.database.connection import get_db
from calsystem.config import get_settings, save_settings
from calsystem.database.models import (
    Standard,
    DUT,
    WiringDiagramLibrary,
    DeviceGroupType,
    SectionType,
    STANDARD_SECTION_TYPES,
    get_all_section_types,
)


class DropZoneLabel(QLabel):
    """QLabel that accepts drag and drop of image files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._on_file_dropped = None  # Callback function

    def set_drop_callback(self, callback):
        """Set callback function to be called when a file is dropped."""
        self._on_file_dropped = callback

    def dragEnterEvent(self, event):
        """Handle drag enter - accept if it contains file URLs."""
        if event.mimeData().hasUrls():
            # Check if any URL is an image file
            for url in event.mimeData().urls():
                file_path = url.toLocalFile().lower()
                if file_path.endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    event.acceptProposedAction()
                    self.setStyleSheet(
                        "background-color: #d4edda; border: 2px dashed #28a745; border-radius: 5px;"
                    )
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        """Handle drag leave - reset style."""
        self.setStyleSheet(
            "background-color: #f0f0f0; border: 2px dashed #ccc; border-radius: 5px;"
        )

    def dropEvent(self, event):
        """Handle drop - load the dropped image file."""
        self.setStyleSheet(
            "background-color: #f0f0f0; border: 2px dashed #ccc; border-radius: 5px;"
        )

        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    if self._on_file_dropped:
                        self._on_file_dropped(file_path)
                    event.acceptProposedAction()
                    return
        event.ignore()


class AddImageDialog(QDialog):
    """Dialog for adding a new wiring diagram image."""

    def __init__(self, calibrator_model: str, dut_model: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Wiring Diagram")
        self.setMinimumWidth(500)

        self._calibrator_model = calibrator_model
        self._dut_model = dut_model
        self._image_data: Optional[bytes] = None
        self._mime_type: str = "image/png"

        layout = QVBoxLayout(self)

        # Info
        info_label = QLabel(f"Adding image for: {calibrator_model} + {dut_model}")
        info_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(info_label)

        # Form
        form_layout = QFormLayout()

        # Section type dropdown using all types (built-in + custom)
        self.section_combo = QComboBox()
        self.section_combo.addItem("-- Select Section Type --", "")
        for section_type in get_all_section_types():
            self.section_combo.addItem(section_type, section_type)
        form_layout.addRow("Section Type:", self.section_combo)

        # Filename preview
        self.filename_label = QLabel("--")
        self.filename_label.setStyleSheet("color: gray; font-style: italic;")
        form_layout.addRow("Filename:", self.filename_label)
        self.section_combo.currentTextChanged.connect(self._update_filename_preview)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Optional description")
        form_layout.addRow("Description:", self.description_input)

        layout.addLayout(form_layout)

        # Image selection
        image_group = QGroupBox("Image")
        image_layout = QVBoxLayout(image_group)

        btn_layout = QHBoxLayout()
        self.select_btn = QPushButton("Select Image File...")
        self.select_btn.clicked.connect(self._on_select_image)
        btn_layout.addWidget(self.select_btn)

        self.image_path_label = QLabel("No image selected")
        btn_layout.addWidget(self.image_path_label)
        btn_layout.addStretch()
        image_layout.addLayout(btn_layout)

        # Image preview with drag & drop support
        self.image_preview = DropZoneLabel()
        self.image_preview.setMinimumSize(400, 300)
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setStyleSheet(
            "background-color: #f0f0f0; border: 2px dashed #ccc; border-radius: 5px;"
        )
        self.image_preview.setText("Drag & drop image here\nor click 'Select Image File...'")
        self.image_preview.set_drop_callback(self._load_image_file)
        image_layout.addWidget(self.image_preview)

        layout.addWidget(image_group)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _update_filename_preview(self):
        """Update the filename preview based on section type."""
        section = self.section_combo.currentData()
        if section:
            # Sanitize for filename
            safe_section = "".join(c if c.isalnum() or c in " _-" else "_" for c in section)
            filename = f"{self._calibrator_model}_{self._dut_model}_{safe_section}.png"
            self.filename_label.setText(filename)
        else:
            self.filename_label.setText("--")

    def _on_select_image(self):
        """Open file dialog to select an image."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Wiring Diagram Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*)"
        )

        if file_path:
            self._load_image_file(file_path)

    def _load_image_file(self, file_path: str):
        """Load an image file (from file dialog or drag & drop)."""
        try:
            with open(file_path, "rb") as f:
                self._image_data = f.read()

            # Determine MIME type
            ext = os.path.splitext(file_path)[1].lower()
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".bmp": "image/bmp",
                ".gif": "image/gif",
            }
            self._mime_type = mime_map.get(ext, "image/png")

            # Show preview
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    400, 300,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_preview.setPixmap(scaled)

            self.image_path_label.setText(os.path.basename(file_path))

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load image:\n{e}")

    def _on_accept(self):
        """Validate and accept the dialog."""
        section = self.section_combo.currentData()
        if not section:
            QMessageBox.warning(self, "Validation Error", "Please select a section type.")
            return

        if not self._image_data:
            QMessageBox.warning(self, "Validation Error", "Please select an image file.")
            return

        self.accept()

    def get_data(self) -> Dict[str, Any]:
        """Get the entered data."""
        section = self.section_combo.currentData() or ""
        safe_section = "".join(c if c.isalnum() or c in " _-" else "_" for c in section)
        filename = f"{self._calibrator_model}_{self._dut_model}_{safe_section}.png"

        return {
            "section_name": section,
            "description": self.description_input.text().strip() or None,
            "image_data": self._image_data,
            "mime_type": self._mime_type,
            "filename": filename,
        }


class SectionTypesDialog(QDialog):
    """Dialog for managing section types."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Section Types")
        self.setMinimumSize(500, 400)
        self.setModal(True)

        self._init_ui()
        self._load_section_types()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Section Types")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            "Section types are used to categorize wiring diagrams and test sections.\n"
            "Built-in types cannot be deleted. Add custom types for your specific needs."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray;")
        layout.addWidget(desc)

        # Table
        self.types_table = QTableWidget()
        self.types_table.setColumnCount(3)
        self.types_table.setHorizontalHeaderLabels(["Name", "Description", "Built-in"])
        self.types_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.types_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.types_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.types_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.types_table)

        # Add new type
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("New Type:"))
        self.new_type_input = QLineEdit()
        self.new_type_input.setPlaceholderText("Enter new section type name...")
        self.new_type_input.returnPressed.connect(self._on_add_type)
        add_layout.addWidget(self.new_type_input)

        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self._on_add_type)
        add_layout.addWidget(self.add_btn)

        layout.addLayout(add_layout)

        # Buttons
        btn_layout = QHBoxLayout()

        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self._on_delete_type)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _load_section_types(self):
        """Load section types from database."""
        self.types_table.setRowCount(0)

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                types = session.query(SectionType).order_by(
                    SectionType.is_builtin.desc(),  # Built-in first
                    SectionType.name
                ).all()

                for st in types:
                    row = self.types_table.rowCount()
                    self.types_table.insertRow(row)

                    name_item = QTableWidgetItem(st.name)
                    name_item.setData(Qt.ItemDataRole.UserRole, st.id)
                    if st.is_builtin:
                        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.types_table.setItem(row, 0, name_item)

                    desc_item = QTableWidgetItem(st.description or "")
                    self.types_table.setItem(row, 1, desc_item)

                    builtin_item = QTableWidgetItem("Yes" if st.is_builtin else "No")
                    builtin_item.setFlags(builtin_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.types_table.setItem(row, 2, builtin_item)

        except Exception as e:
            logger.error(f"Failed to load section types: {e}")

    def _on_add_type(self):
        """Add a new section type."""
        name = self.new_type_input.text().strip()
        if not name:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                # Check if already exists
                existing = session.query(SectionType).filter(
                    SectionType.name.ilike(name)
                ).first()

                if existing:
                    QMessageBox.warning(
                        self, "Duplicate",
                        f"Section type '{name}' already exists."
                    )
                    return

                section_type = SectionType(
                    name=name,
                    is_builtin=False
                )
                session.add(section_type)

            self.new_type_input.clear()
            self._load_section_types()
            logger.info(f"Added section type: {name}")

        except Exception as e:
            logger.error(f"Failed to add section type: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add section type:\n{e}")

    def _on_delete_type(self):
        """Delete the selected section type."""
        selected = self.types_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a section type to delete.")
            return

        row = selected[0].row()
        name_item = self.types_table.item(row, 0)
        builtin_item = self.types_table.item(row, 2)

        if builtin_item.text() == "Yes":
            QMessageBox.warning(
                self, "Cannot Delete",
                "Built-in section types cannot be deleted."
            )
            return

        type_id = name_item.data(Qt.ItemDataRole.UserRole)
        type_name = name_item.text()

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete section type '{type_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                section_type = session.query(SectionType).filter(
                    SectionType.id == type_id
                ).first()

                if section_type:
                    session.delete(section_type)

            self._load_section_types()
            logger.info(f"Deleted section type: {type_name}")

        except Exception as e:
            logger.error(f"Failed to delete section type: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete section type:\n{e}")


class LibrariesTab(QWidget):
    """Tab for managing wiring diagram libraries."""

    def __init__(self):
        super().__init__()
        self._current_calibrator: Optional[str] = None
        self._current_calibrator_make: str = ""
        self._current_dut: Optional[str] = None
        self._init_ui()

    def showEvent(self, event):
        """Called when tab becomes visible."""
        super().showEvent(event)
        self._load_calibrators()
        self._load_duts()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Wiring Diagram Library")
        header.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        desc = QLabel(
            "Manage wiring diagram images organized by Calibrator + DUT combination. "
            "Images are automatically named: {calibrator}_{dut}_{section}.png"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: gray;")
        layout.addWidget(desc)

        # Selection area
        select_group = QGroupBox("Select Standard and DUT")
        select_layout = QHBoxLayout(select_group)

        # Standard type dropdown
        select_layout.addWidget(QLabel("Type:"))
        self.standard_type_combo = QComboBox()
        self.standard_type_combo.addItems(["Calibrator", "DMM", "Counter", "Other"])
        self.standard_type_combo.currentTextChanged.connect(self._on_standard_type_changed)
        select_layout.addWidget(self.standard_type_combo)

        select_layout.addSpacing(10)

        # Standard model dropdown (editable)
        select_layout.addWidget(QLabel("Standard Model:"))
        self.calibrator_combo = QComboBox()
        self.calibrator_combo.setMinimumWidth(200)
        self.calibrator_combo.setEditable(True)
        self.calibrator_combo.setPlaceholderText("Select or type model...")
        self.calibrator_combo.currentTextChanged.connect(self._on_calibrator_changed)
        select_layout.addWidget(self.calibrator_combo)

        select_layout.addSpacing(20)

        select_layout.addWidget(QLabel("DUT Model:"))
        self.dut_combo = QComboBox()
        self.dut_combo.setMinimumWidth(200)
        self.dut_combo.setEditable(True)
        self.dut_combo.setPlaceholderText("Select or type model...")
        self.dut_combo.currentTextChanged.connect(self._on_dut_changed)
        select_layout.addWidget(self.dut_combo)

        select_layout.addStretch()

        layout.addWidget(select_group)

        # Main content splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left - Image list
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        list_header = QLabel("Wiring Diagrams")
        list_header.setStyleSheet("font-weight: bold;")
        list_layout.addWidget(list_header)

        self.image_table = QTableWidget()
        self.image_table.setColumnCount(3)
        self.image_table.setHorizontalHeaderLabels(["Section", "Filename", "Description"])
        self.image_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.image_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.image_table.itemSelectionChanged.connect(self._on_image_selected)
        list_layout.addWidget(self.image_table)

        # Buttons
        btn_layout = QHBoxLayout()

        self.add_btn = QPushButton("Add Image...")
        self.add_btn.clicked.connect(self._on_add_image)
        btn_layout.addWidget(self.add_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._on_delete_image)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addSpacing(20)

        self.section_types_btn = QPushButton("Section Types...")
        self.section_types_btn.setToolTip("Manage custom section types for wiring diagrams")
        self.section_types_btn.clicked.connect(self._on_manage_section_types)
        btn_layout.addWidget(self.section_types_btn)

        self.migrate_btn = QPushButton("Migrate to Files...")
        self.migrate_btn.setToolTip("Extract database-stored images to files for better performance")
        self.migrate_btn.clicked.connect(self._on_migrate_images)
        btn_layout.addWidget(self.migrate_btn)

        btn_layout.addStretch()
        list_layout.addLayout(btn_layout)

        splitter.addWidget(list_widget)

        # Right - Preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        preview_header = QLabel("Preview")
        preview_header.setStyleSheet("font-weight: bold;")
        preview_layout.addWidget(preview_header)

        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(500, 400)
        self.preview_label.setMaximumSize(800, 600)  # Prevent infinite growth
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet(
            "background-color: #f5f5f5; border: 1px solid #ccc; border-radius: 5px;"
        )
        self.preview_label.setText("Select an image to preview")
        preview_layout.addWidget(self.preview_label)

        splitter.addWidget(preview_widget)
        splitter.setSizes([400, 500])

        layout.addWidget(splitter)

        # High Voltage Warning Preview Section
        hv_group = QGroupBox("High Voltage Warning Preview")
        hv_layout = QHBoxLayout(hv_group)

        # Load the high voltage image
        self.hv_warning_label = QLabel()
        self.hv_warning_label.setFixedSize(120, 120)
        self.hv_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Try to load the image
        import os
        import sys
        # Handle both development mode and PyInstaller bundled mode
        if getattr(sys, 'frozen', False):
            # Running as bundled exe - resources are in _MEIPASS
            base_path = sys._MEIPASS
        else:
            # Running in development - go up from libraries_tab.py to project root
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        hv_image_path = os.path.join(base_path, "resources", "images", "HighVoltage.png")
        if os.path.exists(hv_image_path):
            pixmap = QPixmap(hv_image_path)
            scaled = pixmap.scaled(
                QSize(120, 120),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.hv_warning_label.setPixmap(scaled)
            self._hv_pixmap = scaled
        else:
            self.hv_warning_label.setText("Image not found")
            self._hv_pixmap = None

        hv_layout.addWidget(self.hv_warning_label)

        # Controls
        ctrl_layout = QVBoxLayout()

        self.hv_start_btn = QPushButton("Start Blinking")
        self.hv_start_btn.clicked.connect(self._on_start_hv_blink)
        ctrl_layout.addWidget(self.hv_start_btn)

        self.hv_stop_btn = QPushButton("Stop")
        self.hv_stop_btn.clicked.connect(self._on_stop_hv_blink)
        self.hv_stop_btn.setEnabled(False)
        ctrl_layout.addWidget(self.hv_stop_btn)

        self.hv_save_btn = QPushButton("Save Speed")
        self.hv_save_btn.setToolTip("Save blink speed to use during test execution")
        self.hv_save_btn.clicked.connect(self._on_save_hv_speed)
        ctrl_layout.addWidget(self.hv_save_btn)

        # Blink speed slider
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Speed:"))
        from PyQt6.QtWidgets import QSlider
        self.hv_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.hv_speed_slider.setMinimum(100)
        self.hv_speed_slider.setMaximum(1000)
        # Load saved speed from settings
        settings = get_settings()
        saved_speed = settings.ui.high_voltage_blink_speed_ms
        self.hv_speed_slider.setValue(saved_speed)
        self.hv_speed_slider.setTickInterval(100)
        self.hv_speed_slider.valueChanged.connect(self._on_hv_speed_changed)
        speed_layout.addWidget(self.hv_speed_slider)
        self.hv_speed_label = QLabel(f"{saved_speed}ms")
        speed_layout.addWidget(self.hv_speed_label)
        ctrl_layout.addLayout(speed_layout)

        ctrl_layout.addStretch()
        hv_layout.addLayout(ctrl_layout)

        # Info
        info_layout = QVBoxLayout()
        info_label = QLabel(
            "This warning will appear during test execution\n"
            "when calibrator outputs ≥100V DC or AC.\n\n"
            "The image is scaled to 100x100 pixels."
        )
        info_label.setStyleSheet("color: gray;")
        info_layout.addWidget(info_label)
        info_layout.addStretch()
        hv_layout.addLayout(info_layout)

        hv_layout.addStretch()

        layout.addWidget(hv_group)

        # Opacity effect for fading
        self._hv_opacity_effect = QGraphicsOpacityEffect()
        self._hv_opacity_effect.setOpacity(1.0)
        self.hv_warning_label.setGraphicsEffect(self._hv_opacity_effect)

        # Animation for smooth fading
        self._hv_fade_out = QPropertyAnimation(self._hv_opacity_effect, b"opacity")
        self._hv_fade_out.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._hv_fade_in = QPropertyAnimation(self._hv_opacity_effect, b"opacity")
        self._hv_fade_in.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # Connect animations to chain them
        self._hv_fade_out.finished.connect(self._start_fade_in)
        self._hv_fade_in.finished.connect(self._start_fade_out_delayed)

        # Timer for delay between fades
        self._hv_delay_timer = QTimer()
        self._hv_delay_timer.setSingleShot(True)
        self._hv_delay_timer.timeout.connect(self._start_fade_out)

        self._hv_running = False

    # Common standard models by type
    COMMON_MODELS = {
        "Calibrator": [
            # Fluke Multifunction Calibrators
            "Fluke 5500A", "Fluke 5502A", "Fluke 5502E",
            "Fluke 5520A", "Fluke 5520A-PQ", "Fluke 5522A",
            "Fluke 5530A", "Fluke 5540A", "Fluke 5550A", "Fluke 5560A",
            # Fluke High-Performance Calibrators
            "Fluke 5700A", "Fluke 5720A", "Fluke 5730A",
            # Fluke Electrical Calibrators
            "Fluke 5080A", "Fluke 5180A",
            # Fluke Temperature Calibrators
            "Fluke 9100S", "Fluke 9102S", "Fluke 9103", "Fluke 9140", "Fluke 9141",
            "Fluke 6109A", "Fluke 7109A", "Fluke 7102", "Fluke 7103",
            # Fluke Pressure Calibrators
            "Fluke 2271A", "Fluke 6270A", "Fluke 729",
            # Fluke Process Calibrators
            "Fluke 725", "Fluke 726", "Fluke 754",
            # Other Brands
            "Transmille 3000", "Transmille 4000",
            "Wavetek 9100", "Datron 4700", "Datron 4708",
        ],
        "DMM": [
            # HP/Agilent/Keysight
            "HP 3458A", "Keysight 3458A", "Agilent 3458A",
            "HP 34401A", "Keysight 34401A", "Agilent 34401A",
            "Keysight 34461A", "Keysight 34465A", "Keysight 34470A",
            "HP 3478A", "HP 3457A",
            # Fluke
            "Fluke 8508A", "Fluke 8588A", "Fluke 8845A", "Fluke 8846A",
            "Fluke 87V", "Fluke 187", "Fluke 189", "Fluke 287", "Fluke 289",
            "Fluke 175", "Fluke 177", "Fluke 179",
            # Keithley
            "Keithley 2000", "Keithley 2001", "Keithley 2002",
            "Keithley 2010", "Keithley DMM6500", "Keithley DMM7510",
            # Other
            "Datron 1281", "Datron 1271",
        ],
        "Counter": [
            # HP/Agilent/Keysight
            "HP 53131A", "HP 53132A", "HP 53181A",
            "Keysight 53220A", "Keysight 53230A",
            "Agilent 53131A", "Agilent 53132A",
            # Fluke
            "Fluke PM6681", "Fluke PM6680",
            # Philips
            "Philips PM6681", "Philips PM6680",
            # Other
            "Pendulum CNT-90", "Pendulum CNT-91",
        ],
        "Other": [
            # Oscilloscopes
            "Keysight DSOX3054T", "Tektronix TDS3054",
            # Power Supplies
            "HP 6632A", "Keysight E3631A",
            # Signal Generators
            "HP 3325B", "Keysight 33500B",
            "HP 8656B", "Keysight N5181B",
            # Decade Boxes
            "Fluke 5450A", "IET RS-201",
        ],
    }

    def _on_standard_type_changed(self, type_name: str):
        """Handle standard type change - reload models list."""
        self._load_calibrators()

    def _load_calibrators(self):
        """Load standard models into combo based on selected type."""
        current_text = self.calibrator_combo.currentText()
        self.calibrator_combo.clear()

        # Get selected type
        std_type = self.standard_type_combo.currentText()
        device_group_map = {
            "Calibrator": DeviceGroupType.CALIBRATOR,
            "DMM": DeviceGroupType.DMM,
            "Counter": DeviceGroupType.COUNTER,
            "Other": DeviceGroupType.OTHER,
        }
        device_group = device_group_map.get(std_type, DeviceGroupType.OTHER)

        # Start with common models for this type
        seen = set()
        common = self.COMMON_MODELS.get(std_type, [])
        for model in common:
            self.calibrator_combo.addItem(model)
            seen.add(model.lower())

        # Add models from database
        db = get_db()
        if db.is_connected:
            try:
                with db.session() as session:
                    standards = session.query(Standard).filter(
                        Standard.device_group == device_group
                    ).order_by(Standard.make, Standard.model).all()

                    for std in standards:
                        model_key = f"{std.make} {std.model}"
                        if model_key.lower() not in seen:
                            self.calibrator_combo.addItem(model_key)
                            seen.add(model_key.lower())

                    # Also add from existing wiring diagrams
                    diagrams = session.query(
                        WiringDiagramLibrary.calibrator_make,
                        WiringDiagramLibrary.calibrator_model
                    ).distinct().all()

                    for make, model in diagrams:
                        model_key = f"{make} {model}" if make else model
                        if model_key.lower() not in seen:
                            self.calibrator_combo.addItem(model_key)
                            seen.add(model_key.lower())

            except Exception as e:
                logger.error(f"Failed to load standards: {e}")

        # Restore previous selection if it exists
        if current_text:
            idx = self.calibrator_combo.findText(current_text)
            if idx >= 0:
                self.calibrator_combo.setCurrentIndex(idx)
            else:
                self.calibrator_combo.setCurrentText(current_text)

    def _load_duts(self):
        """Load DUT models into combo."""
        current_text = self.dut_combo.currentText()
        self.dut_combo.clear()

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                duts = session.query(DUT).order_by(DUT.model).all()

                seen = set()
                for dut in duts:
                    if dut.model not in seen:
                        self.dut_combo.addItem(dut.model)
                        seen.add(dut.model)

                # Also add models from existing wiring diagrams
                diagrams = session.query(WiringDiagramLibrary.dut_model).distinct().all()
                for (model,) in diagrams:
                    if model not in seen:
                        self.dut_combo.addItem(model)
                        seen.add(model)

            # Restore text
            if current_text:
                self.dut_combo.setCurrentText(current_text)

        except Exception as e:
            logger.error(f"Failed to load DUTs: {e}")

    def _on_calibrator_changed(self, text: str):
        """Handle calibrator selection change."""
        # Extract model from text like "Fluke 5550A" -> "5550A"
        # Or use full text if it's just a model number
        text = text.strip()
        if text:
            # Try to extract just the model (last part after space)
            parts = text.split()
            if len(parts) >= 2:
                # Format is "Make Model" - use just the model
                self._current_calibrator = parts[-1]
                self._current_calibrator_make = " ".join(parts[:-1])
            else:
                # Just a model number
                self._current_calibrator = text
                self._current_calibrator_make = ""
        else:
            self._current_calibrator = None
            self._current_calibrator_make = ""
        self._refresh_image_list()

    def _on_dut_changed(self, text: str):
        """Handle DUT selection change."""
        self._current_dut = text.strip() if text else None
        self._refresh_image_list()

    def _refresh_image_list(self):
        """Refresh the image list based on selected calibrator and DUT."""
        self.image_table.setRowCount(0)
        self.preview_label.clear()
        self.preview_label.setText("Select an image to preview")

        if not self._current_calibrator or not self._current_dut:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                diagrams = session.query(WiringDiagramLibrary).filter(
                    WiringDiagramLibrary.calibrator_model.ilike(self._current_calibrator),
                    WiringDiagramLibrary.dut_model.ilike(self._current_dut)
                ).order_by(WiringDiagramLibrary.section_name).all()

                for diag in diagrams:
                    row = self.image_table.rowCount()
                    self.image_table.insertRow(row)

                    section_item = QTableWidgetItem(diag.section_name)
                    section_item.setData(Qt.ItemDataRole.UserRole, diag.id)
                    self.image_table.setItem(row, 0, section_item)

                    self.image_table.setItem(row, 1, QTableWidgetItem(diag.filename or ""))
                    self.image_table.setItem(row, 2, QTableWidgetItem(diag.description or ""))

                logger.debug(f"Loaded {len(diagrams)} diagrams for {self._current_calibrator} + {self._current_dut}")

        except Exception as e:
            logger.error(f"Failed to load wiring diagrams: {e}")

    def _find_diagram_file(self, image_path: str) -> str | None:
        """Find the diagram file, checking multiple locations."""
        if not image_path:
            return None

        # 1. Try the stored path directly
        if os.path.exists(image_path):
            return image_path

        # 2. Extract relative path and try other locations
        path_parts = Path(image_path).parts
        try:
            diagrams_idx = path_parts.index("diagrams")
            relative_path = os.path.join(*path_parts[diagrams_idx + 1:])
        except (ValueError, IndexError):
            relative_path = os.path.basename(image_path)

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

        return None

    def _on_image_selected(self):
        """Handle image selection - show preview."""
        selected = self.image_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        diagram_id = self.image_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

        if not diagram_id:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                diagram = session.query(WiringDiagramLibrary).filter(
                    WiringDiagramLibrary.id == diagram_id
                ).first()

                if not diagram:
                    self.preview_label.setText("Diagram not found")
                    return

                pixmap = None

                # Try loading from file path first (new method)
                file_path = self._find_diagram_file(diagram.image_path)
                if file_path:
                    pixmap = QPixmap(file_path)
                    if pixmap.isNull():
                        pixmap = None
                        logger.warning(f"Failed to load image from path: {file_path}")

                # Fall back to BLOB data (legacy method)
                if pixmap is None and diagram.image_data:
                    image = QImage()
                    image.loadFromData(diagram.image_data)
                    if not image.isNull():
                        pixmap = QPixmap.fromImage(image)

                if pixmap and not pixmap.isNull():
                    # Scale to fixed size to prevent container growth
                    scaled = pixmap.scaled(
                        500, 400,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.preview_label.setPixmap(scaled)
                else:
                    self.preview_label.setText("No image data")

        except Exception as e:
            logger.error(f"Failed to load image preview: {e}")
            self.preview_label.setText(f"Error: {e}")

    def _on_add_image(self):
        """Add a new wiring diagram image."""
        if not self._current_calibrator:
            QMessageBox.warning(self, "Select Calibrator", "Please select a calibrator first.")
            return

        if not self._current_dut:
            QMessageBox.warning(self, "Select DUT", "Please select or enter a DUT model first.")
            return

        dialog = AddImageDialog(self._current_calibrator, self._current_dut, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            self._save_image(data)

    def _get_diagrams_dir(self) -> Path:
        """Get the diagrams directory - resources/diagrams for dev, ~/.calsystem/diagrams for bundled."""
        if getattr(sys, 'frozen', False):
            # Running from bundled exe - save to user's local folder (bundled is read-only)
            settings = get_settings()
            return settings.diagrams_dir
        else:
            # Running from source - save to resources/diagrams for bundling
            project_root = Path(__file__).parent.parent.parent.parent.parent
            return project_root / "resources" / "diagrams"

    def _save_image(self, data: Dict[str, Any]):
        """Save a wiring diagram image to file and database."""
        db = get_db()
        if not db.is_connected:
            QMessageBox.critical(self, "Error", "Database not connected.")
            return

        try:
            # Get diagrams directory
            diagrams_dir = self._get_diagrams_dir()

            # Create subdirectory structure: diagrams/{dut_model}/{calibrator_model}/
            # Organized by DUT first (what you're calibrating), then by calibrator (what you're using)
            dut_dir = diagrams_dir / self._sanitize_filename(self._current_dut)
            cal_dir = dut_dir / self._sanitize_filename(self._current_calibrator)
            cal_dir.mkdir(parents=True, exist_ok=True)

            # Save image file
            filename = data["filename"]
            file_path = cal_dir / filename

            with open(file_path, "wb") as f:
                f.write(data["image_data"])

            logger.info(f"Saved wiring diagram file: {file_path}")

            # Save to database with file path (no BLOB data)
            with db.session() as session:
                diagram = WiringDiagramLibrary(
                    calibrator_make=self._current_calibrator_make,
                    calibrator_model=self._current_calibrator,
                    dut_model=self._current_dut,
                    section_name=data["section_name"],
                    image_data=None,  # Don't store BLOB
                    image_path=str(file_path),  # Store file path
                    mime_type=data["mime_type"],
                    filename=data["filename"],
                    description=data["description"],
                )
                session.add(diagram)

            logger.info(f"Saved wiring diagram to database: {data['filename']}")
            self._refresh_image_list()

            QMessageBox.information(
                self, "Image Added",
                f"Wiring diagram saved as:\n{data['filename']}"
            )

        except Exception as e:
            logger.error(f"Failed to save wiring diagram: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save image:\n{e}")

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use as a filename/directory name."""
        # Replace invalid characters with underscores
        invalid_chars = '<>:"/\\|?*'
        result = name
        for char in invalid_chars:
            result = result.replace(char, '_')
        return result.strip()

    def _on_delete_image(self):
        """Delete the selected wiring diagram."""
        selected = self.image_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select an image to delete.")
            return

        row = selected[0].row()
        diagram_id = self.image_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        section_name = self.image_table.item(row, 0).text()

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete wiring diagram for '{section_name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        db = get_db()
        if not db.is_connected:
            return

        try:
            with db.session() as session:
                diagram = session.query(WiringDiagramLibrary).filter(
                    WiringDiagramLibrary.id == diagram_id
                ).first()

                if diagram:
                    # Delete the file if it exists
                    if diagram.image_path and os.path.exists(diagram.image_path):
                        try:
                            os.remove(diagram.image_path)
                            logger.info(f"Deleted wiring diagram file: {diagram.image_path}")
                        except OSError as e:
                            logger.warning(f"Could not delete file {diagram.image_path}: {e}")

                    session.delete(diagram)
                    logger.info(f"Deleted wiring diagram from database: {diagram.filename}")

            self._refresh_image_list()

        except Exception as e:
            logger.error(f"Failed to delete wiring diagram: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete:\n{e}")

    def _on_manage_section_types(self):
        """Open the section types management dialog."""
        dialog = SectionTypesDialog(self)
        dialog.exec()

    def _on_migrate_images(self):
        """Migrate database-stored images to files."""
        db = get_db()
        if not db.is_connected:
            QMessageBox.warning(self, "Database Error", "Database not connected.")
            return

        # Count images that need migration
        try:
            with db.session() as session:
                # Find records with image_data but no image_path
                count = session.query(WiringDiagramLibrary).filter(
                    WiringDiagramLibrary.image_data.isnot(None),
                    (WiringDiagramLibrary.image_path.is_(None)) | (WiringDiagramLibrary.image_path == "")
                ).count()

            if count == 0:
                QMessageBox.information(
                    self, "Migration Complete",
                    "All wiring diagram images are already stored as files.\n"
                    "No migration needed."
                )
                return

            reply = QMessageBox.question(
                self, "Migrate Images",
                f"Found {count} wiring diagram image(s) stored in the database.\n\n"
                f"This will:\n"
                f"1. Extract images to files in your diagrams folder\n"
                f"2. Update database records to use file paths\n"
                f"3. Clear binary data from the database to save space\n\n"
                f"Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return

            # Perform migration - use same directory logic as _save_image
            diagrams_dir = self._get_diagrams_dir()
            migrated = 0
            errors = []

            with db.session() as session:
                diagrams = session.query(WiringDiagramLibrary).filter(
                    WiringDiagramLibrary.image_data.isnot(None),
                    (WiringDiagramLibrary.image_path.is_(None)) | (WiringDiagramLibrary.image_path == "")
                ).all()

                for diagram in diagrams:
                    try:
                        # Create directory structure: {dut_model}/{calibrator_model}/
                        dut_dir = diagrams_dir / self._sanitize_filename(diagram.dut_model or "Unknown")
                        cal_dir = dut_dir / self._sanitize_filename(diagram.calibrator_model or "Unknown")
                        cal_dir.mkdir(parents=True, exist_ok=True)

                        # Determine filename
                        if diagram.filename:
                            filename = diagram.filename
                        else:
                            ext = ".png"
                            if diagram.mime_type:
                                mime_ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif"}
                                ext = mime_ext.get(diagram.mime_type, ".png")
                            filename = f"{diagram.calibrator_model}_{diagram.dut_model}_{diagram.section_name}{ext}"
                            filename = self._sanitize_filename(filename)

                        file_path = cal_dir / filename

                        # Write file
                        with open(file_path, "wb") as f:
                            f.write(diagram.image_data)

                        # Update record
                        diagram.image_path = str(file_path)
                        diagram.image_data = None  # Clear BLOB to save space

                        migrated += 1
                        logger.info(f"Migrated: {file_path}")

                    except Exception as e:
                        errors.append(f"{diagram.filename or diagram.id}: {e}")
                        logger.error(f"Migration error: {e}")

                session.commit()

            # Show results
            msg = f"Successfully migrated {migrated} image(s) to files."
            if errors:
                msg += f"\n\n{len(errors)} error(s):\n" + "\n".join(errors[:5])
                if len(errors) > 5:
                    msg += f"\n... and {len(errors) - 5} more"
                QMessageBox.warning(self, "Migration Complete", msg)
            else:
                QMessageBox.information(self, "Migration Complete", msg)

            # Refresh the display
            self._refresh_image_list()

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            QMessageBox.critical(self, "Migration Error", f"Migration failed:\n{e}")

    def _on_start_hv_blink(self):
        """Start the high voltage warning fading animation."""
        if self._hv_pixmap:
            self._hv_running = True
            self._hv_opacity_effect.setOpacity(1.0)
            self.hv_warning_label.setPixmap(self._hv_pixmap)
            self.hv_start_btn.setEnabled(False)
            self.hv_stop_btn.setEnabled(True)
            self._start_fade_out()

    def _on_stop_hv_blink(self):
        """Stop the high voltage warning fading animation."""
        self._hv_running = False
        self._hv_fade_out.stop()
        self._hv_fade_in.stop()
        self._hv_delay_timer.stop()
        self._hv_opacity_effect.setOpacity(1.0)
        if self._hv_pixmap:
            self.hv_warning_label.setPixmap(self._hv_pixmap)
        self.hv_start_btn.setEnabled(True)
        self.hv_stop_btn.setEnabled(False)

    def _start_fade_out(self):
        """Start fading out."""
        if not self._hv_running:
            return
        duration = self.hv_speed_slider.value() // 2
        self._hv_fade_out.setDuration(duration)
        self._hv_fade_out.setStartValue(1.0)
        self._hv_fade_out.setEndValue(0.2)  # Don't go fully invisible
        self._hv_fade_out.start()

    def _start_fade_in(self):
        """Start fading in."""
        if not self._hv_running:
            return
        duration = self.hv_speed_slider.value() // 2
        self._hv_fade_in.setDuration(duration)
        self._hv_fade_in.setStartValue(0.2)
        self._hv_fade_in.setEndValue(1.0)
        self._hv_fade_in.start()

    def _start_fade_out_delayed(self):
        """Start fade out after a brief delay at full opacity."""
        if not self._hv_running:
            return
        # Small pause at full opacity before fading out again
        self._hv_delay_timer.start(100)

    def _on_hv_speed_changed(self, value: int):
        """Handle blink speed slider change."""
        self.hv_speed_label.setText(f"{value}ms")

    def _on_save_hv_speed(self):
        """Save the high voltage blink speed to settings."""
        settings = get_settings()
        settings.ui.high_voltage_blink_speed_ms = self.hv_speed_slider.value()
        if save_settings(settings):
            QMessageBox.information(
                self, "Saved",
                f"High voltage blink speed saved: {self.hv_speed_slider.value()}ms\n\n"
                "This will be used during test execution."
            )
        else:
            QMessageBox.warning(self, "Error", "Failed to save settings.")
