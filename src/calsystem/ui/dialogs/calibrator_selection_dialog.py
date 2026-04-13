"""
Dialog for selecting which calibrator to use when multiple are detected.
"""

from typing import Optional, List, Dict, Any
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QAbstractItemView,
    QGroupBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from loguru import logger


class CalibratorSelectionDialog(QDialog):
    """Dialog for selecting a calibrator from detected instruments."""

    def __init__(
        self,
        calibrators: List[Dict[str, Any]],
        parent=None,
        title: str = "Select Calibrator",
        message: str = "Multiple calibrators detected. Please select one to use:",
    ):
        """
        Initialize the dialog.

        Args:
            calibrators: List of calibrator dicts with keys:
                - address: VISA address
                - make: Manufacturer
                - model: Model number
                - serial: Serial number (optional)
                - has_command_bank: Whether a command bank exists
            parent: Parent widget
            title: Dialog title
            message: Message to display
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(500, 300)

        self._calibrators = calibrators
        self._selected_index: Optional[int] = None

        self._init_ui(message)

    def _init_ui(self, message: str):
        """Initialize the UI."""
        layout = QVBoxLayout(self)

        # Message
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label)

        # Calibrators table
        group = QGroupBox("Detected Calibrators")
        group_layout = QVBoxLayout(group)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Address", "Make", "Model", "Serial", "Command Bank"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._on_double_click)

        # Populate table
        self.table.setRowCount(len(self._calibrators))
        for row, cal in enumerate(self._calibrators):
            self.table.setItem(row, 0, QTableWidgetItem(cal.get("address", "")))
            self.table.setItem(row, 1, QTableWidgetItem(cal.get("make", "")))
            self.table.setItem(row, 2, QTableWidgetItem(cal.get("model", "")))
            self.table.setItem(row, 3, QTableWidgetItem(cal.get("serial", "")))

            # Command bank status
            has_cb = cal.get("has_command_bank", False)
            cb_item = QTableWidgetItem("Yes" if has_cb else "No")
            if has_cb:
                cb_item.setForeground(QColor("green"))
            else:
                cb_item.setForeground(QColor("orange"))
                cb_item.setToolTip("No command bank found - commands may not work")
            self.table.setItem(row, 4, cb_item)

        # Select first row by default
        if self._calibrators:
            self.table.selectRow(0)

        group_layout.addWidget(self.table)
        layout.addWidget(group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.select_btn = QPushButton("Select")
        self.select_btn.setDefault(True)
        self.select_btn.clicked.connect(self._on_select)
        btn_layout.addWidget(self.select_btn)

        layout.addLayout(btn_layout)

    def _on_double_click(self):
        """Handle double-click on table row."""
        self._on_select()

    def _on_select(self):
        """Handle select button click."""
        selected = self.table.selectedItems()
        if not selected:
            return

        self._selected_index = selected[0].row()
        logger.info(f"Selected calibrator: {self._calibrators[self._selected_index]}")
        self.accept()

    def get_selected_calibrator(self) -> Optional[Dict[str, Any]]:
        """
        Get the selected calibrator.

        Returns:
            Selected calibrator dict, or None if cancelled.
        """
        if self._selected_index is not None and self._selected_index < len(self._calibrators):
            return self._calibrators[self._selected_index]
        return None
