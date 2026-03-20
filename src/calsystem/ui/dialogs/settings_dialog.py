"""
Settings dialog for database and application configuration.
"""

import json
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QMessageBox,
    QDialogButtonBox,
    QLabel,
)
from PyQt6.QtCore import Qt
from loguru import logger

from calsystem.config.settings import get_settings, reload_settings, DatabaseSettings
from calsystem.database.connection import DatabaseManager


class SettingsDialog(QDialog):
    """Dialog for configuring application settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)
        self.setModal(True)

        self._init_ui()
        self._load_current_settings()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Database settings group
        db_group = QGroupBox("Database Connection")
        db_layout = QFormLayout()

        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("localhost")
        db_layout.addRow("Host:", self.host_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(3306)
        db_layout.addRow("Port:", self.port_input)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("calsystem")
        db_layout.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        db_layout.addRow("Password:", self.password_input)

        self.database_input = QLineEdit()
        self.database_input.setPlaceholderText("calsystem")
        db_layout.addRow("Database Name:", self.database_input)

        db_group.setLayout(db_layout)
        layout.addWidget(db_group)

        # Test connection button
        test_layout = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._on_test_connection)
        test_layout.addStretch()
        test_layout.addWidget(self.test_btn)
        layout.addLayout(test_layout)

        # Connection status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Spacer
        layout.addStretch()

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_current_settings(self):
        """Load current settings into the dialog fields."""
        settings = get_settings()

        self.host_input.setText(settings.database.host)
        self.port_input.setValue(settings.database.port)
        self.username_input.setText(settings.database.username)
        self.password_input.setText(settings.database.password)
        self.database_input.setText(settings.database.database)

    def _get_connection_string(self) -> str:
        """Build connection string from current field values."""
        host = self.host_input.text() or "localhost"
        port = self.port_input.value()
        username = self.username_input.text() or "calsystem"
        password = self.password_input.text()
        database = self.database_input.text() or "calsystem"

        return f"mysql+mysqlconnector://{username}:{password}@{host}:{port}/{database}"

    def _on_test_connection(self):
        """Test the database connection with current settings."""
        self.status_label.setText("Testing connection...")
        self.status_label.setStyleSheet("")
        self.test_btn.setEnabled(False)

        # Force UI update
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            connection_string = self._get_connection_string()
            db_manager = DatabaseManager()

            # Try to connect
            success = db_manager.connect(connection_string)

            if success:
                # Test the connection
                result, message = db_manager.test_connection()
                if result:
                    self.status_label.setText(f"Success: {message}")
                    self.status_label.setStyleSheet("color: green; font-weight: bold;")
                    logger.info(f"Test connection successful: {message}")
                else:
                    self.status_label.setText(f"Connection test failed: {message}")
                    self.status_label.setStyleSheet("color: red; font-weight: bold;")
                    logger.error(f"Test connection failed: {message}")
            else:
                self.status_label.setText("Connection failed")
                self.status_label.setStyleSheet("color: red; font-weight: bold;")
                logger.error("Test connection failed")

        except Exception as e:
            error_msg = str(e)
            self.status_label.setText(f"Error: {error_msg[:50]}...")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            logger.error(f"Test connection error: {e}")

        finally:
            self.test_btn.setEnabled(True)

    def _on_save(self):
        """Save settings to config file."""
        try:
            settings = get_settings()
            config_file = settings.config_dir / "config.json"

            # Load existing config if it exists
            config_data = {}
            if config_file.exists():
                try:
                    config_data = json.loads(config_file.read_text())
                except json.JSONDecodeError:
                    config_data = {}

            # Update database settings
            config_data["database"] = {
                "host": self.host_input.text() or "localhost",
                "port": self.port_input.value(),
                "username": self.username_input.text() or "calsystem",
                "password": self.password_input.text(),
                "database": self.database_input.text() or "calsystem",
            }

            # Ensure config directory exists
            settings.config_dir.mkdir(parents=True, exist_ok=True)

            # Write config file
            config_file.write_text(json.dumps(config_data, indent=2))
            logger.info(f"Settings saved to {config_file}")

            # Reload settings to apply changes
            reload_settings()

            QMessageBox.information(
                self,
                "Settings Saved",
                f"Settings have been saved to:\n{config_file}",
            )
            self.accept()

        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save settings:\n{e}",
            )
