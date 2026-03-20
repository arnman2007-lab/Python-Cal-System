"""
Log viewer dialog for viewing application logs.
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QComboBox,
    QLabel,
    QFileDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from loguru import logger

from calsystem.config.settings import get_settings


class LogViewerDialog(QDialog):
    """Dialog for viewing application logs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Viewer")
        self.setMinimumSize(800, 600)

        self._log_file = None
        self._init_ui()
        self._load_log_files()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Log File:"))
        self.file_combo = QComboBox()
        self.file_combo.setMinimumWidth(300)
        self.file_combo.currentIndexChanged.connect(self._on_file_changed)
        toolbar.addWidget(self.file_combo)

        toolbar.addWidget(QLabel("Level:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(["All", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.level_combo.currentTextChanged.connect(self._on_level_changed)
        toolbar.addWidget(self.level_combo)

        toolbar.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_log)
        toolbar.addWidget(self.refresh_btn)

        self.clear_btn = QPushButton("Clear Display")
        self.clear_btn.clicked.connect(self._clear_display)
        toolbar.addWidget(self.clear_btn)

        layout.addLayout(toolbar)

        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas", 10))
        self.log_display.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.log_display)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.export_btn = QPushButton("Export...")
        self.export_btn.clicked.connect(self._on_export)
        btn_layout.addWidget(self.export_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def _load_log_files(self):
        """Load available log files."""
        settings = get_settings()
        log_dir = settings.config_dir / "logs"

        self.file_combo.clear()

        if log_dir.exists():
            log_files = sorted(log_dir.glob("*.log"), reverse=True)
            for log_file in log_files[:20]:  # Limit to 20 most recent
                self.file_combo.addItem(log_file.name, log_file)

        # Also check current working directory
        cwd_logs = sorted(Path(".").glob("*.log"), reverse=True)
        for log_file in cwd_logs[:5]:
            self.file_combo.addItem(f"[cwd] {log_file.name}", log_file)

        if self.file_combo.count() == 0:
            self.file_combo.addItem("No log files found", None)

    def _on_file_changed(self, index: int):
        """Handle log file selection change."""
        self._log_file = self.file_combo.currentData()
        self._refresh_log()

    def _on_level_changed(self, level: str):
        """Handle log level filter change."""
        self._refresh_log()

    def _refresh_log(self):
        """Refresh the log display."""
        if not self._log_file or not self._log_file.exists():
            self.log_display.setPlainText("No log file selected or file not found.")
            return

        try:
            content = self._log_file.read_text(errors='replace')
            lines = content.split('\n')

            # Apply level filter
            level_filter = self.level_combo.currentText()
            if level_filter != "All":
                filtered_lines = []
                levels = {
                    "DEBUG": ["DEBUG"],
                    "INFO": ["INFO"],
                    "WARNING": ["WARNING", "WARN"],
                    "ERROR": ["ERROR"],
                    "CRITICAL": ["CRITICAL", "FATAL"],
                }
                filter_terms = levels.get(level_filter, [])
                for line in lines:
                    for term in filter_terms:
                        if term in line.upper():
                            filtered_lines.append(line)
                            break
                lines = filtered_lines

            self.log_display.setPlainText('\n'.join(lines[-1000:]))  # Last 1000 lines

            # Scroll to bottom
            scrollbar = self.log_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        except Exception as e:
            logger.error(f"Failed to read log file: {e}")
            self.log_display.setPlainText(f"Error reading log file:\n{e}")

    def _clear_display(self):
        """Clear the log display."""
        self.log_display.clear()

    def _on_export(self):
        """Export log to file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Log",
            "calsystem_log.txt",
            "Text Files (*.txt);;All Files (*)",
        )

        if file_path:
            try:
                Path(file_path).write_text(self.log_display.toPlainText())
                logger.info(f"Log exported to {file_path}")
            except Exception as e:
                logger.error(f"Failed to export log: {e}")
