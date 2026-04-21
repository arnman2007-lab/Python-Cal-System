"""
Changelog tab for tracking application changes and version history.
"""

from datetime import datetime
from typing import Optional, List

from loguru import logger
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTextEdit,
    QScrollArea,
    QFrame,
    QInputDialog,
    QMessageBox,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from calsystem.database.connection import get_db
from calsystem.database.models import ChangelogEntry, DEFAULT_CHANGELOG_CATEGORIES
from calsystem.config.settings import get_settings


class AutoExpandingTextEdit(QTextEdit):
    """A QTextEdit that automatically expands as text is added."""

    def __init__(self, min_height: int = 60, max_height: int = 200):
        super().__init__()
        self._min_height = min_height
        self._max_height = max_height
        self.setMinimumHeight(min_height)
        self.setMaximumHeight(max_height)
        self.document().contentsChanged.connect(self._adjust_height)
        self.setPlaceholderText("Describe the change...")

    def _adjust_height(self):
        """Adjust height based on content."""
        doc_height = self.document().size().height() + 10
        new_height = max(self._min_height, min(int(doc_height), self._max_height))
        self.setMinimumHeight(new_height)


class ChangelogEntryWidget(QFrame):
    """Widget displaying a single changelog entry."""

    def __init__(self, entry: ChangelogEntry):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet("""
            ChangelogEntryWidget {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                margin: 4px;
                padding: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Header row: version and timestamp
        header_layout = QHBoxLayout()

        version_label = QLabel(f"v{entry.version}")
        version_font = QFont()
        version_font.setBold(True)
        version_font.setPointSize(11)
        version_label.setFont(version_font)
        version_label.setStyleSheet("color: #0066cc;")
        header_layout.addWidget(version_label)

        timestamp_str = entry.timestamp.strftime("%Y-%m-%d %H:%M") if entry.timestamp else ""
        timestamp_label = QLabel(timestamp_str)
        timestamp_label.setStyleSheet("color: #6c757d;")
        header_layout.addWidget(timestamp_label)

        header_layout.addStretch()

        if entry.author:
            author_label = QLabel(f"by {entry.author}")
            author_label.setStyleSheet("color: #6c757d; font-style: italic;")
            header_layout.addWidget(author_label)

        layout.addLayout(header_layout)

        # Type and category badges
        badge_layout = QHBoxLayout()

        # Color-code the change type
        type_colors = {
            "Feature": "#28a745",
            "Fix": "#dc3545",
            "Improvement": "#17a2b8",
            "Breaking Change": "#fd7e14",
        }
        type_color = type_colors.get(entry.change_type, "#6c757d")

        type_badge = QLabel(f"[{entry.change_type}]")
        type_badge.setStyleSheet(f"color: {type_color}; font-weight: bold;")
        badge_layout.addWidget(type_badge)

        category_label = QLabel(entry.category)
        category_label.setStyleSheet("color: #495057;")
        badge_layout.addWidget(category_label)

        badge_layout.addStretch()
        layout.addLayout(badge_layout)

        # Description
        desc_label = QLabel(entry.description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #212529; padding-top: 4px;")
        layout.addWidget(desc_label)


class ChangelogTab(QWidget):
    """Tab for viewing and adding changelog entries."""

    # Signal emitted when a new version is added (passes the version string)
    version_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._categories: List[str] = DEFAULT_CHANGELOG_CATEGORIES.copy()
        self._entry_form_visible = False
        self._init_ui()
        # Load changelog immediately to set current version
        self._load_changelog()

    def _init_ui(self):
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header with version and New Entry button
        header_layout = QHBoxLayout()

        self.version_label = QLabel("Current Version: 0.1.0")
        version_font = QFont()
        version_font.setPointSize(14)
        version_font.setBold(True)
        self.version_label.setFont(version_font)
        header_layout.addWidget(self.version_label)

        header_layout.addStretch()

        self.new_entry_btn = QPushButton("+ New Entry")
        self.new_entry_btn.setStyleSheet("""
            QPushButton {
                background-color: #0066cc;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0052a3;
            }
        """)
        self.new_entry_btn.clicked.connect(self._toggle_entry_form)
        header_layout.addWidget(self.new_entry_btn)

        layout.addLayout(header_layout)

        # Entry form (initially hidden)
        self.entry_form = QFrame()
        self.entry_form.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.entry_form.setStyleSheet("""
            QFrame {
                background-color: #e9ecef;
                border: 1px solid #ced4da;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        self.entry_form.setVisible(False)

        form_layout = QVBoxLayout(self.entry_form)
        form_layout.setSpacing(10)

        # Dropdowns row
        dropdowns_layout = QHBoxLayout()

        # Change type dropdown
        type_layout = QVBoxLayout()
        type_layout.addWidget(QLabel("Change Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Feature", "Fix", "Improvement", "Breaking Change"])
        self.type_combo.setMinimumWidth(150)
        type_layout.addWidget(self.type_combo)
        dropdowns_layout.addLayout(type_layout)

        # Category dropdown
        category_layout = QVBoxLayout()
        category_layout.addWidget(QLabel("Category:"))
        category_row = QHBoxLayout()
        self.category_combo = QComboBox()
        self._populate_categories()
        self.category_combo.setMinimumWidth(150)
        category_row.addWidget(self.category_combo)

        self.add_category_btn = QPushButton("+")
        self.add_category_btn.setFixedWidth(30)
        self.add_category_btn.setToolTip("Add new category")
        self.add_category_btn.clicked.connect(self._add_category)
        category_row.addWidget(self.add_category_btn)
        category_layout.addLayout(category_row)
        dropdowns_layout.addLayout(category_layout)

        dropdowns_layout.addStretch()
        form_layout.addLayout(dropdowns_layout)

        # Description text area
        form_layout.addWidget(QLabel("Description:"))
        self.description_edit = AutoExpandingTextEdit(min_height=60, max_height=150)
        form_layout.addWidget(self.description_edit)

        # Buttons row
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel_entry)
        buttons_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Entry")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.save_btn.clicked.connect(self._save_entry)
        buttons_layout.addWidget(self.save_btn)

        form_layout.addLayout(buttons_layout)
        layout.addWidget(self.entry_form)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #dee2e6;")
        layout.addWidget(separator)

        # Changelog history scroll area
        history_label = QLabel("Changelog History")
        history_font = QFont()
        history_font.setPointSize(12)
        history_font.setBold(True)
        history_label.setFont(history_font)
        layout.addWidget(history_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; }")

        self.history_widget = QWidget()
        self.history_layout = QVBoxLayout(self.history_widget)
        self.history_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.history_layout.setSpacing(8)
        self.scroll_area.setWidget(self.history_widget)

        layout.addWidget(self.scroll_area, stretch=1)

    def showEvent(self, event):
        """Called when tab becomes visible."""
        super().showEvent(event)
        self._load_changelog()

    def _populate_categories(self):
        """Populate the category dropdown."""
        self.category_combo.clear()
        self.category_combo.addItems(self._categories)

    def _toggle_entry_form(self):
        """Show or hide the entry form."""
        self._entry_form_visible = not self._entry_form_visible
        self.entry_form.setVisible(self._entry_form_visible)

        if self._entry_form_visible:
            self.new_entry_btn.setText("- Hide Form")
            self.description_edit.setFocus()
        else:
            self.new_entry_btn.setText("+ New Entry")

    def _add_category(self):
        """Add a new custom category."""
        text, ok = QInputDialog.getText(
            self,
            "Add Category",
            "Enter new category name:",
        )
        if ok and text.strip():
            category = text.strip()
            if category not in self._categories:
                self._categories.append(category)
                self._categories.sort()
                self._populate_categories()
                self.category_combo.setCurrentText(category)
                logger.info(f"Added new changelog category: {category}")

    def _cancel_entry(self):
        """Cancel entry and hide form."""
        self.description_edit.clear()
        self.type_combo.setCurrentIndex(0)
        self.category_combo.setCurrentIndex(0)
        self._toggle_entry_form()

    def _calculate_next_version(self, change_type: str) -> str:
        """Calculate the next version based on change type and current version."""
        db = get_db()
        current_version = "0.1.0"

        if db.is_connected:
            try:
                with db.session() as session:
                    # Get the latest version
                    latest = session.query(ChangelogEntry).order_by(
                        ChangelogEntry.id.desc()
                    ).first()
                    if latest:
                        current_version = latest.version
            except Exception as e:
                logger.error(f"Failed to get latest version: {e}")

        # Parse version
        try:
            parts = current_version.split(".")
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
        except (ValueError, IndexError):
            major, minor, patch = 0, 1, 0

        # Increment based on change type
        if change_type == "Breaking Change":
            major += 1
            minor = 0
            patch = 0
        elif change_type in ("Feature", "Improvement"):
            minor += 1
            patch = 0
        else:  # Fix
            patch += 1

        return f"{major}.{minor}.{patch}"

    def _save_entry(self):
        """Save the changelog entry."""
        description = self.description_edit.toPlainText().strip()
        if not description:
            QMessageBox.warning(self, "Missing Description", "Please enter a description.")
            return

        change_type = self.type_combo.currentText()
        category = self.category_combo.currentText()

        # Get author from settings
        settings = get_settings()
        author = getattr(settings, "technician_name", None) or "Unknown"

        # Calculate version
        new_version = self._calculate_next_version(change_type)

        db = get_db()
        if not db.is_connected:
            QMessageBox.warning(self, "Database Error", "Not connected to database.")
            return

        try:
            with db.session() as session:
                entry = ChangelogEntry(
                    version=new_version,
                    timestamp=datetime.now(),
                    change_type=change_type,
                    category=category,
                    description=description,
                    author=author,
                )
                session.add(entry)
                session.commit()
                logger.info(f"Added changelog entry: v{new_version} - {change_type}: {category}")

            # Clear form and refresh
            self.description_edit.clear()
            self.type_combo.setCurrentIndex(0)
            self._toggle_entry_form()
            self._load_changelog()

            # Emit signal so main window can update title
            self.version_changed.emit(new_version)

            QMessageBox.information(
                self, "Entry Saved", f"Changelog entry saved.\nNew version: {new_version}"
            )

        except Exception as e:
            logger.error(f"Failed to save changelog entry: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save entry: {e}")

    def _load_changelog(self):
        """Load and display changelog entries."""
        # Clear existing entries
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        db = get_db()
        if not db.is_connected:
            no_db_label = QLabel("Database not connected")
            no_db_label.setStyleSheet("color: #6c757d; font-style: italic;")
            self.history_layout.addWidget(no_db_label)
            return

        try:
            with db.session() as session:
                entries = session.query(ChangelogEntry).order_by(
                    ChangelogEntry.id.desc()
                ).all()

                if not entries:
                    no_entries = QLabel("No changelog entries yet. Click '+ New Entry' to add one.")
                    no_entries.setStyleSheet("color: #6c757d; font-style: italic; padding: 20px;")
                    self.history_layout.addWidget(no_entries)
                    self.version_label.setText("Current Version: 0.1.0")
                else:
                    # Update version display
                    self.version_label.setText(f"Current Version: {entries[0].version}")

                    for entry in entries:
                        # Detach from session to avoid lazy loading issues
                        session.expunge(entry)
                        widget = ChangelogEntryWidget(entry)
                        self.history_layout.addWidget(widget)

        except Exception as e:
            logger.error(f"Failed to load changelog: {e}")
            error_label = QLabel(f"Error loading changelog: {e}")
            error_label.setStyleSheet("color: #dc3545;")
            self.history_layout.addWidget(error_label)

    def add_entry_programmatically(
        self,
        change_type: str,
        category: str,
        description: str,
        author: str = "Claude",
    ) -> Optional[str]:
        """Add a changelog entry programmatically (for use by Claude or automated processes).

        Args:
            change_type: One of "Feature", "Fix", "Improvement", "Breaking Change"
            category: Category like "Standards", "DUTs", "Procedures", etc.
            description: Description of the change
            author: Who made the change (defaults to "Claude")

        Returns:
            The new version string, or None if failed
        """
        db = get_db()
        if not db.is_connected:
            logger.error("Cannot add changelog entry: database not connected")
            return None

        new_version = self._calculate_next_version(change_type)

        try:
            with db.session() as session:
                entry = ChangelogEntry(
                    version=new_version,
                    timestamp=datetime.now(),
                    change_type=change_type,
                    category=category,
                    description=description,
                    author=author,
                )
                session.add(entry)
                session.commit()
                logger.info(f"Programmatically added changelog: v{new_version} - {change_type}: {description}")
                return new_version

        except Exception as e:
            logger.error(f"Failed to add programmatic changelog entry: {e}")
            return None
