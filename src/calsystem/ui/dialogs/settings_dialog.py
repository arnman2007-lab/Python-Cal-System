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
    QComboBox,
    QFileDialog,
    QWidget,
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

        # Database type selector
        self.db_type_combo = QComboBox()
        self.db_type_combo.addItem("SQLite (Local File)", "sqlite")
        self.db_type_combo.addItem("MySQL/MariaDB (Server)", "mysql")
        self.db_type_combo.currentIndexChanged.connect(self._on_db_type_changed)
        db_layout.addRow("Database Type:", self.db_type_combo)

        # SQLite settings (shown by default)
        self.sqlite_widget = QWidget()
        sqlite_layout = QHBoxLayout(self.sqlite_widget)
        sqlite_layout.setContentsMargins(0, 0, 0, 0)
        self.sqlite_path_input = QLineEdit()
        self.sqlite_path_input.setPlaceholderText("Default: ~/.calsystem/calsystem.db")
        self.sqlite_path_input.setReadOnly(True)
        sqlite_layout.addWidget(self.sqlite_path_input)
        self.sqlite_browse_btn = QPushButton("Browse...")
        self.sqlite_browse_btn.clicked.connect(self._on_browse_sqlite)
        sqlite_layout.addWidget(self.sqlite_browse_btn)
        db_layout.addRow("Database File:", self.sqlite_widget)

        # MySQL settings (hidden by default)
        self.mysql_widget = QWidget()
        mysql_layout = QFormLayout(self.mysql_widget)
        mysql_layout.setContentsMargins(0, 0, 0, 0)

        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("localhost")
        mysql_layout.addRow("Host:", self.host_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(3306)
        mysql_layout.addRow("Port:", self.port_input)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("calsystem")
        mysql_layout.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        mysql_layout.addRow("Password:", self.password_input)

        self.database_input = QLineEdit()
        self.database_input.setPlaceholderText("calsystem")
        mysql_layout.addRow("Database Name:", self.database_input)

        db_layout.addRow(self.mysql_widget)
        self.mysql_widget.setVisible(False)

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

        # Company info group (for reports)
        company_group = QGroupBox("Company Information")
        company_layout = QFormLayout()

        self.company_name_input = QLineEdit()
        self.company_name_input.setPlaceholderText("Your company name (appears on reports)")
        company_layout.addRow("Company Name:", self.company_name_input)

        company_group.setLayout(company_layout)
        layout.addWidget(company_group)

        # Update settings group
        update_group = QGroupBox("Automatic Updates")
        update_layout = QFormLayout()

        self.update_server_input = QLineEdit()
        self.update_server_input.setPlaceholderText("\\\\server\\calsystem")
        update_layout.addRow("Update Server Path:", self.update_server_input)

        from PyQt6.QtWidgets import QCheckBox
        self.check_updates_checkbox = QCheckBox("Check for updates on startup")
        self.check_updates_checkbox.setChecked(True)
        update_layout.addRow("", self.check_updates_checkbox)

        update_group.setLayout(update_layout)
        layout.addWidget(update_group)

        # Spacer
        layout.addStretch()

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_db_type_changed(self, index: int):
        """Handle database type selection change."""
        db_type = self.db_type_combo.currentData()
        self.sqlite_widget.setVisible(db_type == "sqlite")
        self.mysql_widget.setVisible(db_type == "mysql")

    def _on_browse_sqlite(self):
        """Browse for SQLite database file."""
        settings = get_settings()
        default_path = str(settings.config_dir / "calsystem.db")

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Database File",
            default_path,
            "SQLite Database (*.db);;All Files (*)",
        )
        if file_path:
            self.sqlite_path_input.setText(file_path)

    def _load_current_settings(self):
        """Load current settings into the dialog fields."""
        settings = get_settings()

        # Set database type
        db_type = settings.database.db_type
        index = self.db_type_combo.findData(db_type)
        if index >= 0:
            self.db_type_combo.setCurrentIndex(index)
        self._on_db_type_changed(self.db_type_combo.currentIndex())

        # SQLite settings
        if settings.database.sqlite_path:
            self.sqlite_path_input.setText(settings.database.sqlite_path)
        else:
            self.sqlite_path_input.setText("")
            self.sqlite_path_input.setPlaceholderText(
                f"Default: {settings.config_dir / 'calsystem.db'}"
            )

        # MySQL settings
        self.host_input.setText(settings.database.host)
        self.port_input.setValue(settings.database.port)
        self.username_input.setText(settings.database.username)
        self.password_input.setText(settings.database.password)
        self.database_input.setText(settings.database.database)

        # Company settings
        self.company_name_input.setText(settings.company_name or "")

        # Update settings
        self.update_server_input.setText(settings.update_server_path or "")
        self.check_updates_checkbox.setChecked(settings.check_updates_on_startup)

    def _get_connection_string(self) -> str:
        """Build connection string from current field values."""
        db_type = self.db_type_combo.currentData()

        if db_type == "sqlite":
            sqlite_path = self.sqlite_path_input.text()
            if not sqlite_path:
                settings = get_settings()
                sqlite_path = str(settings.config_dir / "calsystem.db")
            return f"sqlite:///{sqlite_path}"
        else:
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
            db_type = self.db_type_combo.currentData()
            sqlite_path = self.sqlite_path_input.text() or None

            config_data["database"] = {
                "db_type": db_type,
                "sqlite_path": sqlite_path,
                "host": self.host_input.text() or "localhost",
                "port": self.port_input.value(),
                "username": self.username_input.text() or "calsystem",
                "password": self.password_input.text(),
                "database": self.database_input.text() or "calsystem",
            }

            # Company settings
            config_data["company_name"] = self.company_name_input.text().strip()

            # Update settings
            config_data["update_server_path"] = self.update_server_input.text().strip()
            config_data["check_updates_on_startup"] = self.check_updates_checkbox.isChecked()

            # Ensure config directory exists
            settings.config_dir.mkdir(parents=True, exist_ok=True)

            # Write config file
            config_file.write_text(json.dumps(config_data, indent=2))
            logger.info(f"Settings saved to {config_file}")

            # Reload settings to apply changes
            reload_settings()

            db_desc = "SQLite (local file)" if db_type == "sqlite" else "MySQL/MariaDB"
            QMessageBox.information(
                self,
                "Settings Saved",
                f"Settings saved.\nDatabase type: {db_desc}",
            )
            self.accept()

        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save settings:\n{e}",
            )
