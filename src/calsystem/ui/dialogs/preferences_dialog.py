"""
User preferences dialog.
"""

import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QComboBox,
    QPushButton,
    QMessageBox,
    QDialogButtonBox,
    QTabWidget,
    QWidget,
    QLabel,
)
from loguru import logger

from calsystem.config.settings import get_settings, reload_settings


class PreferencesDialog(QDialog):
    """Dialog for configuring user preferences."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(450)
        self.setModal(True)

        self._init_ui()
        self._load_current_preferences()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # General tab
        general_tab = QWidget()
        general_layout = QFormLayout(general_tab)

        self.technician_name_input = QLineEdit()
        self.technician_name_input.setPlaceholderText("Enter your name")
        general_layout.addRow("Technician Name:", self.technician_name_input)

        self.technician_id_input = QLineEdit()
        self.technician_id_input.setPlaceholderText("Employee ID")
        general_layout.addRow("Technician ID:", self.technician_id_input)

        self.workstation_name_input = QLineEdit()
        self.workstation_name_input.setPlaceholderText("e.g., Station 1")
        general_layout.addRow("Workstation Name:", self.workstation_name_input)

        self.default_input_method = QComboBox()
        self.default_input_method.addItems(["Keyboard Entry", "Remote Reading", "Webcam OCR"])
        general_layout.addRow("Default Input Method:", self.default_input_method)

        self.tabs.addTab(general_tab, "General")

        # Webcam tab
        webcam_tab = QWidget()
        webcam_layout = QFormLayout(webcam_tab)

        self.camera_combo = QComboBox()
        self._populate_cameras()
        webcam_layout.addRow("Camera Device:", self.camera_combo)

        self.refresh_cameras_btn = QPushButton("Refresh")
        self.refresh_cameras_btn.clicked.connect(self._populate_cameras)
        webcam_layout.addRow("", self.refresh_cameras_btn)

        self.ocr_mode_combo = QComboBox()
        self.ocr_mode_combo.addItems(["Standard OCR", "Seven-Segment OCR"])
        webcam_layout.addRow("Default OCR Mode:", self.ocr_mode_combo)

        self.tabs.addTab(webcam_tab, "Webcam")

        # Display tab
        display_tab = QWidget()
        display_layout = QFormLayout(display_tab)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System Default", "Light", "Dark"])
        display_layout.addRow("Theme:", self.theme_combo)

        self.font_size_combo = QComboBox()
        self.font_size_combo.addItems(["Small", "Medium", "Large"])
        self.font_size_combo.setCurrentIndex(1)
        display_layout.addRow("Font Size:", self.font_size_combo)

        self.tabs.addTab(display_tab, "Display")

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _populate_cameras(self):
        """Populate camera combo with available devices."""
        self.camera_combo.clear()
        self.camera_combo.addItem("Default Camera (0)", 0)

        try:
            import cv2
            # Check for multiple cameras
            for i in range(1, 5):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    self.camera_combo.addItem(f"Camera {i}", i)
                    cap.release()
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Error detecting cameras: {e}")

    def _load_current_preferences(self):
        """Load current preferences into dialog fields."""
        settings = get_settings()
        config_file = settings.config_dir / "config.json"

        if config_file.exists():
            try:
                config_data = json.loads(config_file.read_text())
                prefs = config_data.get("preferences", {})

                self.technician_name_input.setText(prefs.get("technician_name", ""))
                self.technician_id_input.setText(prefs.get("technician_id", ""))
                self.workstation_name_input.setText(config_data.get("workstation_name", ""))

                input_method = prefs.get("default_input_method", 0)
                self.default_input_method.setCurrentIndex(input_method)

                camera_idx = prefs.get("camera_device", 0)
                for i in range(self.camera_combo.count()):
                    if self.camera_combo.itemData(i) == camera_idx:
                        self.camera_combo.setCurrentIndex(i)
                        break

                ocr_mode = prefs.get("ocr_mode", 0)
                self.ocr_mode_combo.setCurrentIndex(ocr_mode)

                theme = prefs.get("theme", 0)
                self.theme_combo.setCurrentIndex(theme)

                font_size = prefs.get("font_size", 1)
                self.font_size_combo.setCurrentIndex(font_size)

            except Exception as e:
                logger.error(f"Failed to load preferences: {e}")

    def _on_save(self):
        """Save preferences to config file."""
        try:
            settings = get_settings()
            config_file = settings.config_dir / "config.json"

            # Load existing config
            config_data = {}
            if config_file.exists():
                try:
                    config_data = json.loads(config_file.read_text())
                except json.JSONDecodeError:
                    config_data = {}

            # Update preferences
            config_data["preferences"] = {
                "technician_name": self.technician_name_input.text(),
                "technician_id": self.technician_id_input.text(),
                "default_input_method": self.default_input_method.currentIndex(),
                "camera_device": self.camera_combo.currentData(),
                "ocr_mode": self.ocr_mode_combo.currentIndex(),
                "theme": self.theme_combo.currentIndex(),
                "font_size": self.font_size_combo.currentIndex(),
            }

            config_data["workstation_name"] = self.workstation_name_input.text()

            # Ensure config directory exists
            settings.config_dir.mkdir(parents=True, exist_ok=True)

            # Write config file
            config_file.write_text(json.dumps(config_data, indent=2))
            logger.info(f"Preferences saved to {config_file}")

            # Reload settings
            reload_settings()

            QMessageBox.information(
                self,
                "Preferences Saved",
                "Your preferences have been saved.",
            )
            self.accept()

        except Exception as e:
            logger.error(f"Failed to save preferences: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save preferences:\n{e}",
            )
