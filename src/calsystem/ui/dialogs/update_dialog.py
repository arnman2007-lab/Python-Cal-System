"""
Update available dialog for Calsystem.

Shows available update information and changelog.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QGroupBox,
    QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from loguru import logger


class UpdateDialog(QDialog):
    """Dialog showing available update with changelog."""

    def __init__(self, update_info, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self.setWindowTitle("Update Available")
        self.setMinimumSize(500, 400)
        self.setModal(True)

        self._init_ui()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Header
        header = QLabel("A new version of Calsystem is available!")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2196F3;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # Version info
        version_frame = QFrame()
        version_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        version_layout = QHBoxLayout(version_frame)

        current_label = QLabel(f"Current version: {self.update_info.current_version}")
        current_label.setStyleSheet("font-size: 14px;")
        version_layout.addWidget(current_label)

        arrow_label = QLabel(" → ")
        arrow_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        version_layout.addWidget(arrow_label)

        new_label = QLabel(f"New version: {self.update_info.new_version}")
        new_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #4CAF50;")
        version_layout.addWidget(new_label)

        version_layout.addStretch()
        layout.addWidget(version_frame)

        # Changelog
        changelog_group = QGroupBox("What's New")
        changelog_layout = QVBoxLayout(changelog_group)

        changelog_text = QTextEdit()
        changelog_text.setReadOnly(True)
        changelog_text.setMinimumHeight(200)

        # Format changelog
        html = "<style>body { font-family: sans-serif; }</style>"

        # Group by change type
        changes_by_type = {}
        for change in self.update_info.changelog:
            change_type = change.get("type", "Other")
            if change_type not in changes_by_type:
                changes_by_type[change_type] = []
            changes_by_type[change_type].append(change)

        # Order: Breaking Change, Feature, Improvement, Fix, Other
        type_order = ["Breaking Change", "Feature", "Improvement", "Fix", "Other"]
        type_colors = {
            "Breaking Change": "#f44336",
            "Feature": "#4CAF50",
            "Improvement": "#2196F3",
            "Fix": "#FF9800",
            "Other": "#9E9E9E",
        }

        for change_type in type_order:
            if change_type in changes_by_type:
                color = type_colors.get(change_type, "#9E9E9E")
                html += f"<h3 style='color: {color}; margin-bottom: 5px;'>{change_type}s</h3>"
                html += "<ul style='margin-top: 5px;'>"
                for change in changes_by_type[change_type]:
                    category = change.get("category", "")
                    description = change.get("description", "")
                    if category:
                        html += f"<li><b>{category}:</b> {description}</li>"
                    else:
                        html += f"<li>{description}</li>"
                html += "</ul>"

        if not self.update_info.changelog:
            html = "<p style='color: gray;'>No changelog information available.</p>"

        changelog_text.setHtml(html)
        changelog_layout.addWidget(changelog_text)
        layout.addWidget(changelog_group)

        # Buttons
        button_layout = QHBoxLayout()

        later_btn = QPushButton("Remind Me Later")
        later_btn.clicked.connect(self.reject)
        button_layout.addWidget(later_btn)

        button_layout.addStretch()

        update_btn = QPushButton("Update Now")
        update_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px 30px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        update_btn.clicked.connect(self.accept)
        button_layout.addWidget(update_btn)

        layout.addLayout(button_layout)
