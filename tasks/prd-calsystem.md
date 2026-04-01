# PRD: Calsystem - Calibration Management System

## Introduction

Calsystem is a comprehensive Python-based calibration laboratory management application similar to Fluke MetCal. It provides calibration technicians with tools to manage test equipment (standards), devices under test (DUTs), build calibration procedures, execute tests with multiple input methods, and generate professional reports. The system uses PyQt6 for the GUI, PyVISA for instrument communication, and MySQL/MariaDB for shared database storage across multiple workstations.

## Goals

- Provide a unified interface for managing calibration lab equipment and procedures
- Support GPIB and COM port communication with test standards via PyVISA/NI-VISA
- Enable procedure creation that mirrors existing Excel-based workflows
- Support three data input methods: keyboard entry, remote instrument reading, and webcam OCR
- Store all calibration data in a centralized MySQL/MariaDB database
- Generate professional PDF reports and Excel exports
- Allow multiple technicians to work simultaneously on separate workstations

## User Stories

### Module 1: Workstation & Standards Setup

#### US-001: Database Connection Setup
**Description:** As an administrator, I want to configure the MySQL/MariaDB connection so that all workstations share the same data.

**Acceptance Criteria:**
- [ ] Settings dialog for database host, port, username, password, database name
- [ ] Test connection button with success/failure feedback
- [ ] Connection settings saved to local config file
- [ ] Application shows connection status in status bar
- [ ] Typecheck passes

#### US-002: Scan and Detect Connected Instruments
**Description:** As a technician, I want to scan for connected GPIB and COM port devices so I can quickly set up my workstation.

**Acceptance Criteria:**
- [ ] "Scan Instruments" button triggers PyVISA resource discovery
- [ ] Lists all detected VISA resources (GPIB, COM, USB, etc.)
- [ ] For each detected device, attempts *IDN? query
- [ ] Displays resource address, manufacturer, model, serial from IDN response
- [ ] Handles devices that don't respond to *IDN? gracefully
- [ ] Typecheck passes

#### US-003: Add Standard to Workstation
**Description:** As a technician, I want to add a detected or manual instrument as a standard so I can use it for calibrations.

**Acceptance Criteria:**
- [ ] Form fields: Make, Model, Serial Number, STD ID, GPIB Address/COM Port
- [ ] Dropdown to select device group: Calibrator, DMM, Counter, Other
- [ ] Auto-populate fields if device was detected via scan
- [ ] STD ID can be associated with serial number for recall
- [ ] Save button stores to database
- [ ] Typecheck passes

#### US-004: View and Manage Workstation Standards
**Description:** As a technician, I want to view all standards assigned to my workstation so I can manage my equipment.

**Acceptance Criteria:**
- [ ] Table view showing all workstation standards grouped by type
- [ ] Columns: Group, Make, Model, Serial, STD ID, Address, Status
- [ ] Edit button opens form to modify standard details
- [ ] Remove button removes standard from workstation (not from database)
- [ ] Status indicator shows if instrument is currently connected/responding
- [ ] Typecheck passes

#### US-005: Save and Load Workstation Configurations
**Description:** As a technician, I want to save my workstation setup so I can quickly restore it later.

**Acceptance Criteria:**
- [ ] Save workstation config with a name
- [ ] Load workstation config by name
- [ ] Config includes all standards and their addresses
- [ ] Validates that saved addresses still exist on load
- [ ] Typecheck passes

---

### Module 2: DUT (Device Under Test) Management

#### US-006: Add New DUT to System
**Description:** As a technician, I want to add a device under test so I can track and calibrate it.

**Acceptance Criteria:**
- [ ] Form fields: Make, Model, Serial Number, Asset Number
- [ ] Asset number auto-generates as Model-SerialNumber (e.g., 789-123456789)
- [ ] Option to override auto-generated asset number for rentals/no-serial units
- [ ] Checkbox: "Remote Control Capable" with input method preference
- [ ] If not remote capable, select preferred input: Keyboard or Webcam
- [ ] Save to database
- [ ] Typecheck passes

#### US-007: Search and Recall DUT
**Description:** As a technician, I want to search for a DUT by asset number so I can quickly load its information.

**Acceptance Criteria:**
- [ ] Search box with autocomplete for asset numbers
- [ ] Search also matches on make, model, serial number
- [ ] Results show asset number, make, model, serial, last calibration date
- [ ] Click result loads DUT into active session
- [ ] Typecheck passes

#### US-008: View DUT History
**Description:** As a technician, I want to view a DUT's calibration history so I can see past results.

**Acceptance Criteria:**
- [ ] History tab shows all past calibrations for selected DUT
- [ ] List shows: Date, Work Order, Technician, Pass/Fail status
- [ ] Click entry opens detailed results view
- [ ] Export history option
- [ ] Typecheck passes

#### US-009: Assign Procedure to DUT
**Description:** As a technician, I want to assign a default procedure to a DUT so it loads automatically.

**Acceptance Criteria:**
- [ ] Dropdown to select from saved procedures
- [ ] Procedure filters by compatible make/model if metadata available
- [ ] Assignment saved with DUT record
- [ ] When DUT loaded, associated procedure auto-loads
- [ ] Typecheck passes

#### US-010: Set Calibration Due Date
**Description:** As a technician, I want to set a calibration due date for a DUT so I know when it needs recalibration.

**Acceptance Criteria:**
- [ ] Due date field in DUT record
- [ ] Auto-calculate due date based on calibration interval (e.g., 12 months from last cal)
- [ ] Manual override of due date
- [ ] Calibration interval configurable per DUT or per model
- [ ] Due date updates automatically after successful calibration
- [ ] Typecheck passes

#### US-011: View Upcoming Calibrations Due
**Description:** As a technician, I want to see a list of DUTs coming due for calibration so I can plan my workload.

**Acceptance Criteria:**
- [ ] Dashboard widget or dedicated view showing upcoming due dates
- [ ] Filter by: Due this week, Due this month, Overdue
- [ ] Sort by due date
- [ ] Color coding: Red = overdue, Yellow = due within 7 days, Green = more than 7 days
- [ ] Click DUT to open its record
- [ ] Typecheck passes

---

### Module 3: Procedure Builder

#### US-012: Create New Procedure
**Description:** As a technician, I want to create a new calibration procedure so I can define test steps.

**Acceptance Criteria:**
- [ ] New procedure dialog with name, description, target make/model fields
- [ ] Procedure opens in builder view
- [ ] Saves to database with unique ID
- [ ] Typecheck passes

#### US-013: Import Procedure from Excel
**Description:** As a technician, I want to import test points from an existing Excel file so I can migrate current procedures.

**Acceptance Criteria:**
- [ ] Import wizard to select Excel file
- [ ] Column mapping interface: map Excel columns to test point fields
- [ ] Preview import results before confirming
- [ ] Creates sections based on Excel structure or user-defined breaks
- [ ] Typecheck passes

#### US-014: Add Test Section
**Description:** As a technician, I want to add named sections to organize test points (e.g., DC Voltage, AC Voltage).

**Acceptance Criteria:**
- [ ] Add section button creates new named section
- [ ] Section name is editable
- [ ] Sections can be reordered via drag-drop
- [ ] Sections can be collapsed/expanded in view
- [ ] Typecheck passes

#### US-015: Add Test Point
**Description:** As a technician, I want to add individual test points within a section.

**Acceptance Criteria:**
- [ ] Add test point button within section
- [ ] Fields: Nominal value, Unit, Frequency (if AC), Tolerance (+/-), Tolerance type (%, absolute)
- [ ] Test type dropdown: Measurement, Pass/Fail, Calculated
- [ ] For calculated: formula editor referencing other test points
- [ ] Test points numbered within section
- [ ] Typecheck passes

#### US-016: Configure Test Point Source and Output Commands
**Description:** As a technician, I want to define what commands to send to standards for each test point.

**Acceptance Criteria:**
- [ ] Select source standard (Calibrator) for test point
- [ ] Select measurement standard (DMM/Counter) if applicable
- [ ] Command builder with common SCPI templates
- [ ] Custom command entry option
- [ ] Output on/operate command configuration
- [ ] Typecheck passes

#### US-017: Add Wiring Diagram to Procedure
**Description:** As a technician, I want to upload wiring hookup images so technicians know how to connect equipment.

**Acceptance Criteria:**
- [ ] Upload image button (supports PNG, JPG)
- [ ] Image associated with procedure or specific section
- [ ] Can have multiple images (one per section if needed)
- [ ] Images stored in database or linked file storage
- [ ] Preview thumbnail in builder
- [ ] Typecheck passes

#### US-018: Configure Excel Export Mapping
**Description:** As a technician, I want to map test points to Excel cells so results can be exported to spreadsheets.

**Acceptance Criteria:**
- [ ] Each test point has optional Excel mapping: workbook name, sheet, cell address
- [ ] Mapping preview shows which cells will be populated
- [ ] Template Excel file can be uploaded
- [ ] Typecheck passes

#### US-019: Save and Manage Procedures
**Description:** As a technician, I want to save procedures and organize them in folders.

**Acceptance Criteria:**
- [ ] Save procedure with version tracking
- [ ] Procedure folder browser
- [ ] Copy/duplicate procedure option
- [ ] Delete procedure (with confirmation, checks for DUT assignments)
- [ ] Typecheck passes

---

### Module 4: Command Bank

#### US-020: Create Command Set for Device Model
**Description:** As a technician, I want to define a command set for a specific device model so the system knows how to control it.

**Acceptance Criteria:**
- [ ] Create command set linked to Make/Model
- [ ] Define commands: Set output, Operate on/off, Read measurement, Reset, etc.
- [ ] Each command has: name, SCPI string, parameter placeholders
- [ ] Test command button sends to connected device
- [ ] Typecheck passes

#### US-021: Browse and Edit Command Bank
**Description:** As a technician, I want to browse all command sets so I can reuse and modify them.

**Acceptance Criteria:**
- [ ] List view of all command sets by make/model
- [ ] Search/filter by manufacturer or model
- [ ] Edit existing command sets
- [ ] Import/export command sets as JSON
- [ ] Typecheck passes

#### US-022: Auto-Detect Missing Command Bank
**Description:** As a technician, I want the system to alert me when a connected device has no command bank so I can create one.

**Acceptance Criteria:**
- [ ] When adding a standard to workstation, check if command bank exists for that make/model
- [ ] If no command bank found, show warning: "No command bank found for [Make Model]"
- [ ] Offer button: "Create Command Bank" that opens new command bank form pre-filled with make/model
- [ ] Track which devices have/don't have command banks in standards list
- [ ] Typecheck passes

---

### Module 5: Test Execution

#### US-023: Start Calibration Session
**Description:** As a technician, I want to start a calibration session for a DUT so I can run the procedure.

**Acceptance Criteria:**
- [ ] Select DUT (or enter new)
- [ ] Enter Work Order number
- [ ] Procedure auto-loads if assigned, or select manually
- [ ] Verify required standards are connected
- [ ] Session start timestamp recorded
- [ ] Typecheck passes

#### US-024: Test Execution Main Screen
**Description:** As a technician, I want a clear execution interface showing current test and all test points.

**Acceptance Criteria:**
- [ ] Left panel: Current test point details, nominal value, tolerance, wiring diagram
- [ ] Center panel: Status display showing what calibrator/DMM is doing
- [ ] Right panel: Scrollable list of all test points with status (pending/pass/fail/skip)
- [ ] Current test highlighted in right panel
- [ ] Progress bar showing overall completion
- [ ] Typecheck passes

#### US-025: Execute Test Point - Remote Reading
**Description:** As a technician, I want the system to automatically read from a remote-capable DUT.

**Acceptance Criteria:**
- [ ] System sends output command to calibrator
- [ ] System sends operate/output-on command
- [ ] Status shows "Sourcing [value]"
- [ ] System queries DUT for reading via configured command
- [ ] Reading captured and compared to tolerance
- [ ] Pass/Fail automatically determined
- [ ] Advances to next test point
- [ ] Typecheck passes

#### US-026: Execute Test Point - Keyboard Entry
**Description:** As a technician, I want to manually enter the DUT reading via keyboard.

**Acceptance Criteria:**
- [ ] System sends output command to calibrator and operates
- [ ] Popup dialog prompts for reading entry
- [ ] Numeric input with unit display
- [ ] Enter/submit captures reading
- [ ] Pass/Fail calculated and displayed
- [ ] Advances to next test point
- [ ] Typecheck passes

#### US-027: Execute Test Point - Webcam OCR
**Description:** As a technician, I want to use a webcam to capture the DUT display reading.

**Acceptance Criteria:**
- [ ] Webcam preview window opens
- [ ] Region-of-interest selector for display area
- [ ] OCR mode selector: Standard text OCR or Seven-segment display OCR
- [ ] OCR mode preference saved per DUT
- [ ] Capture button or auto-capture on stability
- [ ] OCR processes image and extracts numeric reading
- [ ] Technician confirms or corrects extracted value
- [ ] Pass/Fail calculated
- [ ] Advances to next test point
- [ ] Typecheck passes

#### US-028: Pause, Stop, and Resume Testing
**Description:** As a technician, I want to pause or stop testing so I can handle interruptions.

**Acceptance Criteria:**
- [ ] Pause button suspends testing (calibrator goes to standby)
- [ ] Resume continues from current test point
- [ ] Stop button ends session with confirmation
- [ ] Partial results saved to database
- [ ] Session can be resumed later from database
- [ ] Typecheck passes

#### US-029: Revisit and Redo Test Point
**Description:** As a technician, I want to redo a test point so I can get a better reading.

**Acceptance Criteria:**
- [ ] Click any completed test point in list to select
- [ ] "Redo" button re-executes that test point
- [ ] New reading replaces old (old reading logged for audit)
- [ ] Pass/Fail recalculated
- [ ] Can redo multiple times
- [ ] Typecheck passes

#### US-030: Handle Calculated Test Points
**Description:** As a technician, I want calculated fields to auto-compute based on other readings.

**Acceptance Criteria:**
- [ ] Calculated test points show formula
- [ ] Auto-calculates when referenced test points complete
- [ ] Displays calculated value and pass/fail
- [ ] Formula errors shown clearly
- [ ] Typecheck passes

#### US-031: Handle Failed Test Points
**Description:** As a technician, I want to be prompted when a test point fails so I can decide what to do.

**Acceptance Criteria:**
- [ ] When reading is outside tolerance, show fail dialog
- [ ] Dialog displays: Nominal, Measured, Tolerance, Deviation
- [ ] Three buttons: "Continue" (proceed to next), "Redo" (repeat this test), "Stop" (halt session)
- [ ] Technician choice is logged
- [ ] If "Redo" selected, test point re-executes immediately
- [ ] Typecheck passes

---

### Module 6: Data Storage & Reporting

#### US-032: Save Calibration Results to Database
**Description:** As a technician, I want all calibration data saved automatically so nothing is lost.

**Acceptance Criteria:**
- [ ] Each reading saved immediately after capture
- [ ] Session record includes: Asset number, Work Order, Date/Time, Technician, Standards used
- [ ] All test point results linked to session
- [ ] Overall Pass/Fail status calculated and stored
- [ ] Typecheck passes

#### US-033: Generate PDF Calibration Report
**Description:** As a technician, I want to generate a professional PDF report for the customer.

**Acceptance Criteria:**
- [ ] Report template builder (separate feature or pre-defined)
- [ ] Report includes: Header with lab info, DUT details, Standards used with STD IDs
- [ ] Test results table with nominal, measured, tolerance, pass/fail
- [ ] Overall calibration status
- [ ] Signature/date fields
- [ ] Generate PDF button, opens save dialog
- [ ] Typecheck passes

#### US-034: Export Results to Excel
**Description:** As a technician, I want to export results to Excel using the configured cell mapping.

**Acceptance Criteria:**
- [ ] Export button available after session complete
- [ ] Uses template workbook if configured
- [ ] Populates mapped cells with readings
- [ ] Saves as new Excel file (doesn't overwrite template)
- [ ] Typecheck passes

#### US-035: Report Template Builder
**Description:** As an administrator, I want to design PDF report templates so reports match our lab branding.

**Acceptance Criteria:**
- [ ] Template editor with drag-drop fields
- [ ] Place logo, headers, footers
- [ ] Define data table layout
- [ ] Save multiple templates
- [ ] Assign default template to procedures or lab-wide
- [ ] Typecheck passes

---

### Module 7: Application Shell & Navigation

#### US-036: Main Application Window
**Description:** As a technician, I want a clean main window with easy navigation between modules.

**Acceptance Criteria:**
- [ ] PyQt6 main window with menu bar and toolbar
- [ ] Tab-based or sidebar navigation: Standards, DUTs, Procedures, Run Test, Reports
- [ ] Status bar showing: Database connection, Active workstation config
- [ ] Consistent styling throughout
- [ ] Typecheck passes

#### US-037: User Preferences
**Description:** As a technician, I want to set my preferences for the application.

**Acceptance Criteria:**
- [ ] Settings dialog accessible from menu
- [ ] Preferences: Default input method, Webcam device selection, UI theme
- [ ] Technician name/ID for logging
- [ ] Preferences saved locally per workstation
- [ ] Typecheck passes

#### US-038: Application Logging
**Description:** As an administrator, I want application logs for troubleshooting.

**Acceptance Criteria:**
- [ ] Log file written to local directory
- [ ] Logs include: instrument communication, errors, session events
- [ ] Log level configurable (Debug, Info, Warning, Error)
- [ ] Log viewer accessible from Help menu
- [ ] Typecheck passes

---

## Functional Requirements

### Standards & Workstation
- FR-1: The system must discover GPIB, COM, and USB instruments via PyVISA
- FR-2: The system must send *IDN? query and parse manufacturer, model, serial number
- FR-3: The system must store standards with: Make, Model, Serial, STD ID, Address, Group
- FR-4: The system must support device groups: Calibrator, DMM, Counter, Other
- FR-5: The system must save/load workstation configurations by name

### DUT Management
- FR-6: The system must auto-generate asset numbers as Model-SerialNumber
- FR-7: The system must allow manual asset number entry for rentals/no-serial units
- FR-8: The system must store DUT remote-control capability and preferred input method
- FR-9: The system must search DUTs by asset number, make, model, or serial number
- FR-10: The system must track and display DUT calibration history
- FR-11: The system must track calibration due dates per DUT
- FR-12: The system must auto-calculate due date based on configurable calibration interval
- FR-13: The system must display upcoming and overdue calibrations dashboard

### Procedure Builder
- FR-14: The system must import test points from Excel with column mapping
- FR-15: The system must support named test sections (e.g., DC Voltage, AC Voltage)
- FR-16: The system must support test point types: Measurement, Pass/Fail, Calculated
- FR-17: The system must store tolerance as value and type (% or absolute)
- FR-18: The system must store wiring diagram images with procedures
- FR-19: The system must map test points to Excel cell addresses for export
- FR-20: The system must support formula-based calculated test points

### Command Bank
- FR-21: The system must store command sets by make/model
- FR-22: The system must support parameterized command strings
- FR-23: The system must allow testing commands against connected instruments
- FR-24: The system must detect when a device has no command bank and prompt to create one
- FR-25: The system must auto-link command bank to workstation standard if make/model matches

### Test Execution
- FR-26: The system must control calibrators via SCPI commands through PyVISA
- FR-27: The system must support three input methods: Remote, Keyboard, Webcam OCR
- FR-28: The system must support two OCR modes: Standard text and Seven-segment display
- FR-29: The system must calculate pass/fail based on tolerance
- FR-30: The system must prompt technician on failed test point: Continue, Redo, or Stop
- FR-31: The system must allow pausing and resuming sessions
- FR-32: The system must allow redoing any test point
- FR-33: The system must show real-time status of instrument operations
- FR-34: The system must display all test points with current status during execution

### Data & Reporting
- FR-35: The system must save all readings immediately to MySQL/MariaDB
- FR-36: The system must store all data under asset number with date/time for historical lookup
- FR-37: The system must generate PDF reports with lab branding
- FR-38: The system must export to Excel using configured cell mappings
- FR-39: The system must store session data under asset number with work order reference

---

## Non-Goals (Out of Scope)

- User authentication and role-based permissions (all technicians have equal access)
- Automatic calibration scheduling (system tracks due dates but doesn't auto-schedule work)
- Inventory management beyond basic DUT/Standard tracking
- Integration with external LIMS or ERP systems
- Mobile or web-based interface (desktop only)
- Multi-language support (English only for initial release)
- Automatic firmware updates for connected instruments
- Cloud-based database hosting (on-premise MySQL only)

---

## Technical Considerations

### Technology Stack
- **GUI Framework:** PyQt6
- **Database:** MySQL/MariaDB (shared across workstations)
- **Instrument Control:** PyVISA with NI-VISA backend
- **OCR:** Tesseract via pytesseract or EasyOCR
- **PDF Generation:** ReportLab or WeasyPrint
- **Excel Handling:** openpyxl
- **Webcam:** OpenCV (cv2)
- **Packaging:** PyInstaller for EXE distribution

### Database Schema Considerations
- Standards table with workstation assignments (many-to-many)
- DUTs table with asset number as primary lookup
- Procedures table with sections and test points (hierarchical)
- Sessions table linking DUT, Work Order, Technician, DateTime
- Results table with all readings linked to session and test point
- Command bank table by make/model

### Integration Points
- NI-VISA must be pre-installed on all workstations
- MySQL/MariaDB server accessible on network
- Webcam drivers for OCR functionality

### Performance Requirements
- Instrument communication timeout: configurable, default 5 seconds
- UI must remain responsive during instrument operations (use threading)
- Database queries should complete in under 1 second for typical operations

---

## Success Metrics

- Technicians can set up a new workstation and detect instruments in under 5 minutes
- Procedures can be imported from Excel in under 10 minutes
- Test execution time matches or beats current manual process
- Zero data loss - all readings persisted immediately
- PDF reports generated in under 30 seconds
- System supports 5+ simultaneous workstations without database contention

---

## Resolved Questions

1. **Supervisor review step?** → No. Technician completes calibration and report is final.
2. **PDF report format?** → Start with basic table format, add template builder feature later.
3. **Priority calibrator models?** → All devices get their own command bank. System detects if a command bank exists for the connected device; if not, prompts to create one.
4. **Track calibration due dates?** → Yes, with reminders. Show upcoming due list.
5. **Data backup/export beyond Excel?** → Excel + PDF is sufficient. All data stored under asset number with date/time for historical lookup.
6. **Seven-segment OCR support?** → Both modes. Technician can choose standard OCR or seven-segment optimized mode per DUT.
7. **What happens on test fail?** → Prompt technician with options: Continue, Redo, or Stop.

## Open Questions

None at this time.

