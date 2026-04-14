"""
Main application window for Calsystem.
"""

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QStatusBar,
    QMenuBar,
    QMenu,
    QToolBar,
    QLabel,
    QMessageBox,
)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import Qt, QSize
from loguru import logger

from calsystem.config.settings import get_settings
from calsystem.database.connection import get_db


class CalsystemApp(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Calsystem v0.1.0 - Calibration Management System")
        self.setMinimumSize(1200, 800)

        # Initialize components
        self._init_menu_bar()
        self._init_toolbar()
        self._init_central_widget()
        self._init_status_bar()

        # Load settings and try to connect to database
        self._load_settings_and_connect()

        logger.info("Main window initialized")

    def _load_settings_and_connect(self):
        """Load settings and attempt database connection on startup."""
        settings = get_settings()
        logger.info(f"Settings loaded from {settings.config_dir}")

        # Try to connect to database if settings are configured
        if settings.database.host and settings.database.database:
            db = get_db()
            try:
                if db.connect():
                    # Create tables on successful connection
                    try:
                        db.create_tables()
                        logger.info("Database tables created/verified")
                    except Exception as e:
                        logger.warning(f"Table creation warning: {e}")
                    self._update_db_status(True)
                else:
                    self._update_db_status(False)
            except Exception as e:
                logger.warning(f"Database connection on startup failed: {e}")
                self._update_db_status(False)

    def _update_db_status(self, connected: bool):
        """Update the database connection status in the status bar."""
        if connected:
            self.db_status_label.setText("Database: Connected")
            self.db_status_label.setStyleSheet("color: green;")
        else:
            self.db_status_label.setText("Database: Not Connected")
            self.db_status_label.setStyleSheet("color: red;")

    def _init_menu_bar(self):
        """Initialize the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        new_session_action = QAction("&New Calibration Session", self)
        new_session_action.setShortcut("Ctrl+N")
        new_session_action.triggered.connect(self._on_new_session)
        file_menu.addAction(new_session_action)

        file_menu.addSeparator()

        settings_action = QAction("&Settings...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._on_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Equipment menu
        equipment_menu = menubar.addMenu("&Equipment")

        scan_action = QAction("&Scan for Instruments", self)
        scan_action.setShortcut("F5")
        scan_action.triggered.connect(self._on_scan_instruments)
        equipment_menu.addAction(scan_action)

        equipment_menu.addSeparator()

        add_standard_action = QAction("Add &Standard...", self)
        add_standard_action.triggered.connect(self._on_add_standard)
        equipment_menu.addAction(add_standard_action)

        add_dut_action = QAction("Add &DUT...", self)
        add_dut_action.triggered.connect(self._on_add_dut)
        equipment_menu.addAction(add_dut_action)

        # Procedures menu
        procedures_menu = menubar.addMenu("&Procedures")

        new_procedure_action = QAction("&New Procedure...", self)
        new_procedure_action.triggered.connect(self._on_new_procedure)
        procedures_menu.addAction(new_procedure_action)

        import_procedure_action = QAction("&Import from Excel...", self)
        import_procedure_action.triggered.connect(self._on_import_procedure)
        procedures_menu.addAction(import_procedure_action)

        procedures_menu.addSeparator()

        command_bank_action = QAction("&Command Bank...", self)
        command_bank_action.triggered.connect(self._on_command_bank)
        procedures_menu.addAction(command_bank_action)

        # Reports menu
        reports_menu = menubar.addMenu("&Reports")

        generate_pdf_action = QAction("Generate &PDF Report...", self)
        generate_pdf_action.triggered.connect(self._on_generate_pdf)
        reports_menu.addAction(generate_pdf_action)

        export_excel_action = QAction("Export to &Excel...", self)
        export_excel_action.triggered.connect(self._on_export_excel)
        reports_menu.addAction(export_excel_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        view_logs_action = QAction("View &Logs...", self)
        view_logs_action.triggered.connect(self._on_view_logs)
        help_menu.addAction(view_logs_action)

        help_menu.addSeparator()

        about_action = QAction("&About Calsystem", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _init_toolbar(self):
        """Initialize the toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Add toolbar actions (icons would be added later)
        scan_action = QAction("Scan", self)
        scan_action.setToolTip("Scan for connected instruments (F5)")
        scan_action.triggered.connect(self._on_scan_instruments)
        toolbar.addAction(scan_action)

        toolbar.addSeparator()

        new_session_action = QAction("New Session", self)
        new_session_action.setToolTip("Start new calibration session (Ctrl+N)")
        new_session_action.triggered.connect(self._on_new_session)
        toolbar.addAction(new_session_action)

    def _init_central_widget(self):
        """Initialize the central widget with tabs."""
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West)
        self.tabs.setDocumentMode(True)

        # Import tab widgets (placeholders for now)
        from calsystem.ui.workstation.workstation_tab import WorkstationTab
        from calsystem.ui.dut.dut_tab import DUTTab
        from calsystem.ui.procedures.procedures_tab import ProceduresTab
        from calsystem.ui.execution.execution_tab import ExecutionTab
        from calsystem.ui.reports.reports_tab import ReportsTab
        from calsystem.ui.libraries.libraries_tab import LibrariesTab
        from calsystem.ui.changelog.changelog_tab import ChangelogTab

        # Add tabs
        self.workstation_tab = WorkstationTab()
        self.tabs.addTab(self.workstation_tab, "Standards")

        self.dut_tab = DUTTab()
        self.tabs.addTab(self.dut_tab, "DUTs")

        self.procedures_tab = ProceduresTab()
        self.tabs.addTab(self.procedures_tab, "Procedures")

        self.libraries_tab = LibrariesTab()
        self.tabs.addTab(self.libraries_tab, "Libraries")

        self.execution_tab = ExecutionTab()
        self.tabs.addTab(self.execution_tab, "Run Test")

        self.reports_tab = ReportsTab()
        self.tabs.addTab(self.reports_tab, "Reports")

        self.changelog_tab = ChangelogTab()
        self.tabs.addTab(self.changelog_tab, "Changelog")

        self.setCentralWidget(self.tabs)

    def _init_status_bar(self):
        """Initialize the status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Database connection status
        self.db_status_label = QLabel("Database: Not Connected")
        self.status_bar.addPermanentWidget(self.db_status_label)

        # Workstation status
        self.workstation_label = QLabel("Workstation: Not Configured")
        self.status_bar.addPermanentWidget(self.workstation_label)

        self.status_bar.showMessage("Ready")

    # Menu action handlers
    def _on_new_session(self):
        """Handle new calibration session."""
        logger.info("New session requested")
        self.tabs.setCurrentWidget(self.execution_tab)

    def _on_settings(self):
        """Open settings dialog."""
        logger.info("Settings dialog requested")
        from calsystem.ui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self)
        if dialog.exec():
            # Settings were saved, try to reconnect to database
            db = get_db()
            try:
                if db.connect():
                    self._update_db_status(True)
                    self.status_bar.showMessage("Database connection established", 3000)
                else:
                    self._update_db_status(False)
                    self.status_bar.showMessage("Database connection failed", 3000)
            except Exception as e:
                logger.error(f"Database connection failed: {e}")
                self._update_db_status(False)
                QMessageBox.warning(
                    self,
                    "Connection Error",
                    f"Failed to connect to database:\n{e}",
                )

    def _on_scan_instruments(self):
        """Scan for connected instruments."""
        logger.info("Instrument scan requested")
        self.status_bar.showMessage("Scanning for instruments...")
        # TODO: Implement instrument scanning

    def _on_add_standard(self):
        """Add a new standard."""
        logger.info("Add standard requested")
        self.tabs.setCurrentWidget(self.workstation_tab)

    def _on_add_dut(self):
        """Add a new DUT."""
        logger.info("Add DUT requested")
        self.tabs.setCurrentWidget(self.dut_tab)

    def _on_new_procedure(self):
        """Create a new procedure."""
        logger.info("New procedure requested")
        self.tabs.setCurrentWidget(self.procedures_tab)

    def _on_import_procedure(self):
        """Import procedure from Excel."""
        logger.info("Import procedure requested")
        # TODO: Implement Excel import

    def _on_command_bank(self):
        """Open command bank manager."""
        logger.info("Command bank requested")
        # TODO: Implement command bank dialog

    def _on_generate_pdf(self):
        """Generate PDF report."""
        logger.info("PDF generation requested")
        self.tabs.setCurrentWidget(self.reports_tab)

    def _on_export_excel(self):
        """Export to Excel."""
        logger.info("Excel export requested")
        # TODO: Implement Excel export

    def _on_view_logs(self):
        """View application logs."""
        logger.info("View logs requested")
        # TODO: Implement log viewer

    def _on_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About Calsystem",
            "Calsystem v0.1.0\n\n"
            "Calibration Management System\n\n"
            "A comprehensive tool for managing calibration laboratory "
            "equipment, procedures, and reports.",
        )

    def closeEvent(self, event):
        """Handle window close event."""
        reply = QMessageBox.question(
            self,
            "Exit Calsystem",
            "Are you sure you want to exit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            logger.info("Application closing")
            event.accept()
        else:
            event.ignore()
