"""
SQLAlchemy database models for Calsystem.
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
    LargeBinary,
    JSON,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class DeviceGroupType(PyEnum):
    """Device group types."""

    CALIBRATOR = "calibrator"
    DMM = "dmm"
    COUNTER = "counter"
    OTHER = "other"


class TestPointType(PyEnum):
    """Test point types."""

    MEASUREMENT = "measurement"
    PASS_FAIL = "pass_fail"
    CALCULATED = "calculated"
    DMM_MEASUREMENT = "dmm_measurement"  # 3458A measures (no calibrator output)
    CALIBRATOR_DMM = "calibrator_dmm"  # Calibrator outputs AND 3458A measures


class ToleranceType(PyEnum):
    """Tolerance specification types."""

    PERCENT = "percent"
    ABSOLUTE = "absolute"
    PPM = "ppm"


class MeasurementTarget(PyEnum):
    """What parameter to compare reading against."""

    PRIMARY = "PRIMARY"      # Compare to nominal_value (default)
    FREQUENCY = "FREQUENCY"  # Compare to frequency field
    CUSTOM = "CUSTOM"        # Compare to expected_value field


class InputMethod(PyEnum):
    """Data input methods."""

    REMOTE = "remote"
    KEYBOARD = "keyboard"
    WEBCAM = "webcam"


class TestStatus(PyEnum):
    """Test point status."""

    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


class SessionStatus(PyEnum):
    """Calibration session status."""

    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"


# Standard section types for wiring diagram lookup
# These are the internal standard names that link procedures to library images
STANDARD_SECTION_TYPES = [
    "DC Voltage",
    "AC Voltage",
    "DC Current",
    "AC Current",
    "Resistance 2W",
    "Resistance 4W",
    "Frequency",
    "Capacitance",
    "Temperature",
    "Thermocouple",
    "RTD",
    "Pressure",
    "DC Voltage Source",
    "AC Voltage Source",
    "DC Current Source",
    "AC Current Source",
    "Resistance Source",
    "Continuity",
    "Diode",
    "Other",
]


def get_all_section_types() -> List[str]:
    """Get all section types from database (built-in + custom).

    Returns list of section type names sorted alphabetically.
    Falls back to STANDARD_SECTION_TYPES if database not available.
    """
    try:
        # Import here to avoid circular imports
        from calsystem.database.connection import get_db

        db = get_db()
        if not db.is_connected:
            return STANDARD_SECTION_TYPES.copy()

        with db.session() as session:
            types = session.query(SectionType.name).order_by(SectionType.name).all()
            return [t[0] for t in types]

    except Exception:
        return STANDARD_SECTION_TYPES.copy()


# Standard generic command names for command bank
# Each calibrator's command bank maps these generic names to actual SCPI/GPIB commands
# Example: "OUTPUT" -> "OUT {value} {unit}" for Fluke, "SOURCE {value}{unit}" for others
STANDARD_COMMANDS = {
    # Identity & Control
    "IDENTITY": {
        "description": "Query instrument identity",
        "default": "*IDN?",
        "required": True,
    },
    "RESET": {
        "description": "Reset instrument to default state",
        "default": "*RST",
        "required": True,
    },
    "CLEAR": {
        "description": "Clear status/errors",
        "default": "*CLS",
        "required": False,
    },
    "OPC": {
        "description": "Operation complete query",
        "default": "*OPC?",
        "required": False,
    },

    # Output Control
    "OUTPUT": {
        "description": "Set output value - use {value}, {unit}, {frequency}, {freq_unit}",
        "default": "OUT {value} {unit}",
        "required": True,
    },
    "OPERATE": {
        "description": "Enable output (turn on)",
        "default": "OPER",
        "required": True,
    },
    "STANDBY": {
        "description": "Disable output (turn off/safe)",
        "default": "STBY",
        "required": True,
    },

    # AC-specific
    "OUTPUT_AC": {
        "description": "Set AC output with frequency - use {value}, {unit}, {frequency}, {freq_unit}",
        "default": "OUT {value} {unit}, {frequency} {freq_unit}",
        "required": False,
    },

    # Measurement (for DMMs)
    "MEASURE_DCV": {
        "description": "Measure DC voltage",
        "default": "DCV AUTO",
        "required": False,
    },
    "MEASURE_ACV": {
        "description": "Measure AC voltage",
        "default": "ACV AUTO",
        "required": False,
    },
    "MEASURE_DCI": {
        "description": "Measure DC current",
        "default": "DCI AUTO",
        "required": False,
    },
    "MEASURE_ACI": {
        "description": "Measure AC current",
        "default": "ACI AUTO",
        "required": False,
    },
    "MEASURE_OHM": {
        "description": "Measure resistance (2-wire)",
        "default": "OHM AUTO",
        "required": False,
    },
    "MEASURE_OHM4": {
        "description": "Measure resistance (4-wire)",
        "default": "OHMF AUTO",
        "required": False,
    },
    "TRIGGER": {
        "description": "Trigger a measurement",
        "default": "TRIG SGL",
        "required": False,
    },
    "READ": {
        "description": "Read measurement value",
        "default": "",
        "required": False,
    },
}


# =============================================================================
# Standards / Workstation Models
# =============================================================================


class Standard(Base):
    """Calibration standard (reference equipment)."""

    __tablename__ = "standards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    serial_number = Column(String(100), nullable=True)
    std_id = Column(String(50), nullable=True, comment="Standard ID for tracking")
    device_group = Column(Enum(DeviceGroupType), default=DeviceGroupType.OTHER)
    visa_address = Column(String(200), nullable=True, comment="GPIB/COM/USB address")
    description = Column(Text, nullable=True)
    calibration_due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    workstation_assignments = relationship(
        "WorkstationStandard", back_populates="standard"
    )
    command_bank = relationship("CommandBank", back_populates="standard", uselist=False)

    __table_args__ = (
        UniqueConstraint("make", "model", "serial_number", name="uq_standard_identity"),
        Index("ix_standard_std_id", "std_id"),
    )


class WorkstationConfig(Base):
    """Workstation configuration."""

    __tablename__ = "workstation_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    standards = relationship("WorkstationStandard", back_populates="workstation")


class WorkstationStandard(Base):
    """Association between workstations and standards."""

    __tablename__ = "workstation_standards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workstation_id = Column(Integer, ForeignKey("workstation_configs.id"), nullable=False)
    standard_id = Column(Integer, ForeignKey("standards.id"), nullable=False)
    visa_address = Column(String(200), nullable=True, comment="Address on this workstation")
    is_active = Column(Boolean, default=True, comment="Whether this standard is actively in use")

    # Relationships
    workstation = relationship("WorkstationConfig", back_populates="standards")
    standard = relationship("Standard", back_populates="workstation_assignments")

    __table_args__ = (
        UniqueConstraint("workstation_id", "standard_id", name="uq_workstation_standard"),
    )


# =============================================================================
# Model Database (Manufacturer, LabCode, DeviceModel)
# =============================================================================


class Manufacturer(Base):
    """Equipment manufacturer (e.g., Fluke, Keysight)."""

    __tablename__ = "manufacturers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    device_models = relationship("DeviceModel", back_populates="manufacturer")


class LabCode(Base):
    """Calibration lab codes (e.g., M=Meters, N=High Voltage)."""

    __tablename__ = "lab_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), nullable=False, unique=True)
    description = Column(String(200), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    device_models = relationship("DeviceModel", back_populates="lab_code")


class DeviceModel(Base):
    """Device model definition (e.g., Fluke 789 Processmeter)."""

    __tablename__ = "device_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manufacturer_id = Column(Integer, ForeignKey("manufacturers.id"), nullable=False)
    model_number = Column(String(100), nullable=False)
    description = Column(String(200), nullable=True, comment="e.g., Processmeter, True RMS DMM")
    lab_code_id = Column(Integer, ForeignKey("lab_codes.id"), nullable=True)
    remote_capable = Column(Boolean, default=False, comment="Can be automated via GPIB/USB")
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    manufacturer = relationship("Manufacturer", back_populates="device_models")
    lab_code = relationship("LabCode", back_populates="device_models")
    duts = relationship("DUT", back_populates="device_model")

    __table_args__ = (
        UniqueConstraint("manufacturer_id", "model_number", name="uq_device_model"),
        Index("ix_device_model_manufacturer", "manufacturer_id"),
    )


# =============================================================================
# DUT Models
# =============================================================================


class DUT(Base):
    """Device Under Test."""

    __tablename__ = "duts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_number = Column(String(100), nullable=False, unique=True, index=True)

    # Model reference (optional - can use this OR make/model fields)
    device_model_id = Column(Integer, ForeignKey("device_models.id"), nullable=True)

    # Legacy make/model fields (kept for backwards compatibility)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    serial_number = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    # Customer info (for reports)
    customer_id = Column(String(100), nullable=True, comment="Customer identifier")
    customer_serial = Column(String(100), nullable=True, comment="Customer's serial number for this unit")

    # Capabilities
    remote_capable = Column(Boolean, default=False)
    preferred_input_method = Column(Enum(InputMethod), default=InputMethod.KEYBOARD)
    ocr_mode = Column(String(20), default="standard", comment="standard or seven_segment")
    com_port = Column(String(20), nullable=True, comment="COM port for serial communication (e.g., COM3)")

    # Calibration tracking
    calibration_interval_days = Column(Integer, default=365)
    last_calibration_date = Column(DateTime, nullable=True)
    next_due_date = Column(DateTime, nullable=True)

    # Assigned procedure
    default_procedure_id = Column(Integer, ForeignKey("procedures.id"), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    device_model = relationship("DeviceModel", back_populates="duts")
    default_procedure = relationship("Procedure", back_populates="assigned_duts")
    calibration_sessions = relationship("CalibrationSession", back_populates="dut")
    command_bank = relationship("CommandBank", back_populates="dut", uselist=False)

    __table_args__ = (
        Index("ix_dut_make_model", "make", "model"),
    )


# =============================================================================
# Procedure Models
# =============================================================================


class Procedure(Base):
    """Calibration procedure."""

    __tablename__ = "procedures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    target_make = Column(String(100), nullable=True, comment="Target equipment make")
    target_model = Column(String(100), nullable=True, comment="Target equipment model")
    version = Column(String(20), default="1.0")
    is_active = Column(Boolean, default=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # CSP file support (new file-based procedure storage)
    file_path = Column(String(500), nullable=True, comment="Path to .csp procedure file")
    section_count = Column(Integer, nullable=True, comment="Quick reference: number of sections")
    test_point_count = Column(Integer, nullable=True, comment="Quick reference: total test points")
    file_hash = Column(String(64), nullable=True, comment="SHA-256 hash for change detection")

    # Relationships
    sections = relationship(
        "TestSection", back_populates="procedure", order_by="TestSection.order"
    )
    assigned_duts = relationship("DUT", back_populates="default_procedure")
    wiring_diagrams = relationship("WiringDiagram", back_populates="procedure")


class TestSection(Base):
    """Section within a procedure (e.g., DC Voltage, AC Voltage)."""

    __tablename__ = "test_sections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    order = Column(Integer, default=0)

    # Standard section type for wiring diagram lookup
    # Links this section to library images by standard name (e.g., "AC Voltage")
    # User can have custom 'name' (e.g., "AC Volts Test") but this field
    # determines which library images to use
    standard_section_type = Column(String(50), nullable=True, comment="Standard type for diagram lookup")

    # Command to execute when entering this section (e.g., STBY, *RST, etc.)
    # Runs before showing wiring diagram and before any test points
    section_command = Column(Text, nullable=True, comment="Command to run when entering section")

    # Operator prompt - instructions shown when entering this section
    section_prompt = Column(Text, nullable=True, comment="Instructions shown to tech when entering section")

    # Wiring diagram type override - if set, shows this diagram type instead of standard_section_type
    section_wiring_type = Column(String(100), nullable=True, comment="Library section_type for section wiring")

    # Relationships
    procedure = relationship("Procedure", back_populates="sections")
    test_points = relationship(
        "TestPoint", back_populates="section", order_by="TestPoint.order"
    )


class TestPoint(Base):
    """Individual test point within a section."""

    __tablename__ = "test_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    section_id = Column(Integer, ForeignKey("test_sections.id"), nullable=False)
    order = Column(Integer, default=0)

    # Test point definition
    test_type = Column(Enum(TestPointType), default=TestPointType.MEASUREMENT)
    nominal_value = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)
    frequency = Column(Float, nullable=True, comment="For AC measurements")
    frequency_unit = Column(String(10), default="Hz")

    # Pre-conditioning (optional step before actual test)
    pre_nominal_value = Column(Float, nullable=True, comment="Pre-conditioning value")
    pre_unit = Column(String(20), nullable=True)
    pre_frequency = Column(Float, nullable=True)
    pre_frequency_unit = Column(String(10), default="Hz")
    pre_delay_seconds = Column(Float, default=0, comment="Delay after pre-conditioning")
    # Additional pre-conditioning steps (JSON array)
    # Each step: {"value": 310, "unit": "OHM", "frequency": 0, "frequency_unit": "Hz", "delay": 2}
    pre_conditioning_steps = Column(JSON, nullable=True, comment="Additional pre-conditioning steps")

    # Pass/Fail prompt (for subjective tests like beeper check)
    pass_fail_prompt = Column(Text, nullable=True, comment="Prompt shown to tech for Pass/Fail tests")
    # Pass/Fail range check (for DMM value checks in Pass/Fail tests)
    pass_fail_min = Column(Float, nullable=True, comment="Minimum value for Pass/Fail range check")
    pass_fail_max = Column(Float, nullable=True, comment="Maximum value for Pass/Fail range check")
    pass_fail_range_unit = Column(String(20), nullable=True, comment="Unit for Pass/Fail range check")
    pass_fail_comparison_type = Column(String(10), nullable=True, comment="Comparison type: 'range', 'gt' (greater than), 'lt' (less than)")

    # Measurement target - what are we actually measuring?
    # PRIMARY = compare reading to nominal_value
    # FREQUENCY = compare reading to frequency field
    # CUSTOM = compare reading to expected_value
    measurement_target = Column(Enum(MeasurementTarget), default=MeasurementTarget.PRIMARY)
    expected_value = Column(Float, nullable=True, comment="Custom expected value if measurement_target=CUSTOM")
    expected_unit = Column(String(20), nullable=True, comment="Custom expected unit if measurement_target=CUSTOM")

    # Tolerance (legacy - kept for backward compatibility)
    tolerance_value = Column(Float, nullable=True)
    tolerance_type = Column(Enum(ToleranceType), default=ToleranceType.PERCENT)

    # Multi-component tolerance specification
    # Total tolerance = (nominal × pct_reading/100) + (range × pct_range/100) + (span × pct_span/100) + (digits × resolution) + absolute
    tol_pct_reading = Column(Float, nullable=True, default=0, comment="% of reading component")
    tol_pct_range = Column(Float, nullable=True, default=0, comment="% of range/full scale component")
    tol_pct_span = Column(Float, nullable=True, default=0, comment="% of span component")
    tol_digits = Column(Float, nullable=True, default=0, comment="Number of digits for floor value")
    tol_absolute = Column(Float, nullable=True, default=0, comment="Absolute tolerance in measurement units")
    tol_resolution = Column(Float, nullable=True, comment="Resolution for digit calculation (e.g., 0.001)")
    tol_range_value = Column(Float, nullable=True, comment="Range/full scale reference value")
    tol_span_value = Column(Float, nullable=True, comment="Span reference value (e.g., 16 for 4-20mA)")

    # For calculated test points
    formula = Column(Text, nullable=True, comment="Formula referencing other test points")

    # Commands
    source_command = Column(Text, nullable=True, comment="Command to send to calibrator")
    measure_command = Column(Text, nullable=True, comment="Command to read from DMM/DUT")
    operate_command = Column(Text, nullable=True, comment="Command to enable output")
    standby_command = Column(Text, nullable=True, comment="Command to disable output")

    # Excel mapping
    excel_workbook = Column(String(200), nullable=True)
    excel_sheet = Column(String(100), nullable=True)
    excel_cell = Column(String(20), nullable=True)

    # Test point specific wiring diagram (references WiringDiagramLibrary.section_type)
    # If set, shows this wiring diagram before the test point (overrides section diagram)
    wiring_diagram_type = Column(String(100), nullable=True, comment="Library section_type for test point wiring")

    # Operator instructions - prompt shown to technician before executing this test point
    operator_prompt = Column(Text, nullable=True, comment="Instructions shown to tech before test point")

    # DMM configuration - stored as JSON for flexibility across different DMM models
    # Structure: {"model": "3458A", "func": "DCV", "range": "AUTO", "nplc": "100", ...}
    dmm_config = Column(JSON, nullable=True, comment="DMM settings: func, range, nplc, ndig, azero, etc.")

    # DUT Remote Communication
    # Setup command - sent to DUT to configure it (e.g., change range, set mode)
    dut_setup_command = Column(String(50), nullable=True, comment="DUT command ref to send before test (e.g., Set Range)")
    dut_setup_param = Column(String(100), nullable=True, comment="Parameter value to substitute into setup command {value}")
    # Pre-check - query DUT to verify state before calibrator output
    dut_pre_check_command = Column(String(50), nullable=True, comment="DUT command ref for pre-check (e.g., Query Position)")
    dut_pre_check_param = Column(String(100), nullable=True, comment="Parameter value to substitute into pre-check command {value}")
    dut_pre_check_expected = Column(String(100), nullable=True, comment="Expected response pattern/value")
    # Post-read - read measurement from DUT after calibrator output
    dut_post_read_command = Column(String(50), nullable=True, comment="DUT command ref for post-read (e.g., Read Value)")
    dut_post_read_param = Column(String(100), nullable=True, comment="Parameter value to substitute into post-read command {value}")
    dut_post_read_parser = Column(String(50), nullable=True, comment="Parser type: numeric, string, regex")
    dut_post_read_index = Column(Integer, nullable=True, comment="For CSV responses, which field contains the value (0-based index)")

    description = Column(Text, nullable=True)

    # Relationships
    section = relationship("TestSection", back_populates="test_points")


class WiringDiagram(Base):
    """Wiring diagram images for procedures (legacy - per procedure)."""

    __tablename__ = "wiring_diagrams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id"), nullable=False)
    section_id = Column(Integer, ForeignKey("test_sections.id"), nullable=True)
    name = Column(String(200), nullable=False)
    image_data = Column(LargeBinary, nullable=True)
    image_path = Column(String(500), nullable=True, comment="Alternative: file path")
    mime_type = Column(String(50), default="image/png")
    order = Column(Integer, default=0)

    # Relationships
    procedure = relationship("Procedure", back_populates="wiring_diagrams")


class WiringDiagramLibrary(Base):
    """Library of wiring diagrams organized by calibrator + DUT + section."""

    __tablename__ = "wiring_diagram_library"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Calibrator info (which standard this diagram is for)
    calibrator_make = Column(String(100), nullable=False)
    calibrator_model = Column(String(100), nullable=False)

    # DUT info (which device under test this diagram is for)
    dut_make = Column(String(100), nullable=True)
    dut_model = Column(String(100), nullable=False)

    # Section/measurement type (e.g., "AC Voltage", "Resistance", "mA Source")
    section_name = Column(String(100), nullable=False)

    # Image data
    image_data = Column(LargeBinary, nullable=True)
    image_path = Column(String(500), nullable=True, comment="Alternative: file path")
    mime_type = Column(String(50), default="image/png")

    # Auto-generated filename: {calibrator_model}_{dut_model}_{section_name}.png
    filename = Column(String(300), nullable=True)

    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("calibrator_model", "dut_model", "section_name", name="uq_wiring_diagram_combo"),
        Index("ix_wiring_lib_calibrator", "calibrator_model"),
        Index("ix_wiring_lib_dut", "dut_model"),
    )


class SectionDiagramLink(Base):
    """Links a test section to a specific wiring diagram for a specific calibrator.

    This allows each section in a procedure to have different wiring diagrams
    for different calibrators. During execution, the system looks up the diagram
    based on section_id + calibrator_model.
    """

    __tablename__ = "section_diagram_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    section_id = Column(Integer, ForeignKey("test_sections.id"), nullable=False)
    calibrator_model = Column(String(100), nullable=False, comment="e.g., 5550A, 5520A")
    diagram_id = Column(Integer, ForeignKey("wiring_diagram_library.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    section = relationship("TestSection")
    diagram = relationship("WiringDiagramLibrary")

    __table_args__ = (
        # Each section can only have one diagram per calibrator
        UniqueConstraint("section_id", "calibrator_model", name="uq_section_calibrator_diagram"),
        Index("ix_section_diagram_lookup", "section_id", "calibrator_model"),
    )


class SectionType(Base):
    """Custom section types for wiring diagrams and procedures.

    These are user-defined types that extend STANDARD_SECTION_TYPES.
    Used for organizing wiring diagrams and test sections.
    """

    __tablename__ = "section_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    is_builtin = Column(Boolean, default=False, comment="True for standard types, False for user-added")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_section_type_name", "name"),
    )


# =============================================================================
# Command Bank Models
# =============================================================================


class CommandReference(Base):
    """Generic command reference names that get mapped to actual commands per model.

    Examples: "Source", "Measure", "Standby", "Reset"
    Each calibrator/DMM model maps these references to their actual SCPI commands.
    """

    __tablename__ = "command_references"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(String(200), nullable=True)
    default_command = Column(String(200), nullable=True, comment="Default SCPI command if common")
    is_builtin = Column(Boolean, default=False, comment="True for system-defined references")
    category = Column(String(50), nullable=True, comment="Group: output, measure, control, etc.")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_command_reference_name", "name"),
    )


# Default command references (seeded on first run)
DEFAULT_COMMAND_REFERENCES = [
    # Control
    {"name": "Reset", "description": "Reset instrument to default state", "default_command": "*RST", "category": "control"},
    {"name": "Clear", "description": "Clear status/errors", "default_command": "*CLS", "category": "control"},
    {"name": "Identity", "description": "Query instrument identity", "default_command": "*IDN?", "category": "control"},

    # Output (Calibrators)
    {"name": "Source", "description": "Output a value (voltage, current, etc.)", "default_command": "OUT {value} {unit}", "category": "output"},
    {"name": "Source AC", "description": "Output AC with frequency", "default_command": "OUT {value} {unit}, {frequency} {freq_unit}", "category": "output"},
    {"name": "Operate", "description": "Enable output (turn on)", "default_command": "OPER", "category": "output"},
    {"name": "Standby", "description": "Disable output (safe/off)", "default_command": "STBY", "category": "output"},

    # Measurement (DMMs)
    {"name": "Measure DCV", "description": "Set DMM to measure DC voltage", "default_command": "DCV AUTO", "category": "measure"},
    {"name": "Measure ACV", "description": "Set DMM to measure AC voltage", "default_command": "ACV AUTO", "category": "measure"},
    {"name": "Measure DCI", "description": "Set DMM to measure DC current", "default_command": "DCI AUTO", "category": "measure"},
    {"name": "Measure ACI", "description": "Set DMM to measure AC current", "default_command": "ACI AUTO", "category": "measure"},
    {"name": "Measure Ohms", "description": "Set DMM to measure resistance (2-wire)", "default_command": "OHM AUTO", "category": "measure"},
    {"name": "Measure Ohms 4W", "description": "Set DMM to measure resistance (4-wire)", "default_command": "OHMF AUTO", "category": "measure"},
    {"name": "Trigger", "description": "Trigger a measurement", "default_command": "TRIG SGL", "category": "measure"},
    {"name": "Read", "description": "Read measurement value", "default_command": "", "category": "measure"},
]


# Standard DUT command references for remote DUT communication
STANDARD_DUT_COMMANDS = [
    # Control commands
    {"name": "Identity", "description": "Query device identity", "default_command": "*IDN?", "category": "control"},
    {"name": "Reset", "description": "Reset device to default state", "default_command": "*RST", "category": "control"},
    {"name": "Clear", "description": "Clear status/errors", "default_command": "*CLS", "category": "control"},

    # State query commands - Pre-check
    {"name": "Query Position", "description": "Query knob/switch position", "default_command": "", "category": "state"},
    {"name": "Query Range", "description": "Query current range setting", "default_command": "", "category": "state"},
    {"name": "Query Mode", "description": "Query measurement mode (DC/AC)", "default_command": "", "category": "state"},
    {"name": "Query Function", "description": "Query current function (V/A/Ohm)", "default_command": "", "category": "state"},
    {"name": "Query Buttons", "description": "Query button states", "default_command": "", "category": "state"},
    {"name": "Query Status", "description": "Query device status", "default_command": "", "category": "state"},
    {"name": "Query Scale", "description": "Query scale/multiplier setting", "default_command": "", "category": "state"},
    {"name": "Query Input", "description": "Query which input is selected", "default_command": "", "category": "state"},
    {"name": "Query Terminal", "description": "Query terminal selection (front/rear)", "default_command": "", "category": "state"},

    # Set commands - with {value} placeholder
    {"name": "Set Position", "description": "Set knob/switch position (use {value})", "default_command": "PS {value}", "category": "set"},
    {"name": "Set Range", "description": "Set range (use {value})", "default_command": "", "category": "set"},
    {"name": "Set Mode", "description": "Set mode DC/AC (use {value})", "default_command": "", "category": "set"},
    {"name": "Set Function", "description": "Set function (use {value})", "default_command": "", "category": "set"},

    # Measurement commands - Post-read
    {"name": "Read Value", "description": "Read current measurement value", "default_command": "", "category": "measure"},
    {"name": "Read Primary", "description": "Read primary display value", "default_command": "", "category": "measure"},
    {"name": "Read Secondary", "description": "Read secondary display value", "default_command": "", "category": "measure"},
    {"name": "Trigger Read", "description": "Trigger measurement and read", "default_command": "", "category": "measure"},
    {"name": "Fetch", "description": "Fetch last measurement", "default_command": "FETCH?", "category": "measure"},
    {"name": "Read All", "description": "Read all display values", "default_command": "", "category": "measure"},

    # Fluke 789 specific (common process meter)
    {"name": "789 Query Position", "description": "Fluke 789 rotary switch position", "default_command": "QP", "category": "fluke789"},
    {"name": "789 Query Range", "description": "Fluke 789 range query", "default_command": "QR", "category": "fluke789"},
    {"name": "789 Read Value", "description": "Fluke 789 read measurement", "default_command": "VAL?", "category": "fluke789"},
    {"name": "789 Set Position", "description": "Fluke 789 set position (use {value})", "default_command": "PS R,{value}", "category": "fluke789"},
]


class CommandBank(Base):
    """Command set for a specific device model."""

    __tablename__ = "command_banks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    device_type = Column(String(50), nullable=True, comment="calibrator, dmm, dut, etc.")
    description = Column(Text, nullable=True)

    # Link to specific standard or DUT (optional)
    standard_id = Column(Integer, ForeignKey("standards.id"), nullable=True)
    dut_id = Column(Integer, ForeignKey("duts.id"), nullable=True)

    # Commands stored as JSON
    commands = Column(JSON, nullable=True, comment="Dict of command_name: command_string")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    standard = relationship("Standard", back_populates="command_bank")
    dut = relationship("DUT", back_populates="command_bank")

    __table_args__ = (
        UniqueConstraint("make", "model", name="uq_command_bank_device"),
        Index("ix_command_bank_make_model", "make", "model"),
    )


class DUTCommandBank(Base):
    """Command bank for DUT models - per make/model for remote communication."""

    __tablename__ = "dut_command_banks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    communication_type = Column(String(20), default="serial", comment="serial, gpib, usb")

    # Serial port settings (JSON): {baud_rate, data_bits, parity, stop_bits, timeout}
    serial_config = Column(JSON, nullable=True, comment="Serial port configuration")

    # Commands stored as JSON
    # Format: {"QUERY_POSITION": {"command": "QP", "delay_before": 0, "delay_after": 0.1}, ...}
    commands = Column(JSON, nullable=True, comment="Dict of command_name: {command, delay_before, delay_after}")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("make", "model", name="uq_dut_command_bank"),
        Index("ix_dut_command_bank_make_model", "make", "model"),
    )


# =============================================================================
# Calibration Session & Results Models
# =============================================================================


class CalibrationSession(Base):
    """A calibration session for a DUT."""

    __tablename__ = "calibration_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dut_id = Column(Integer, ForeignKey("duts.id"), nullable=False)
    procedure_id = Column(Integer, ForeignKey("procedures.id"), nullable=False)
    work_order = Column(String(100), nullable=False, index=True)
    asset_number = Column(String(100), nullable=False, index=True)

    # Session info
    technician_name = Column(String(100), nullable=True)
    technician_id = Column(String(50), nullable=True)
    workstation_name = Column(String(100), nullable=True)

    # Timing
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)

    # Status
    status = Column(String(20), default="in_progress")  # in_progress, completed, aborted
    overall_result = Column(String(20), nullable=True)  # pass, fail

    # Standards used (stored as JSON list of standard IDs/info)
    standards_used = Column(JSON, nullable=True)

    # Environmental conditions (optional)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    dut = relationship("DUT", back_populates="calibration_sessions")
    procedure = relationship("Procedure")
    results = relationship("TestResult", back_populates="session")

    __table_args__ = (
        Index("ix_session_asset_date", "asset_number", "started_at"),
    )


class TestResult(Base):
    """Result of a single test point."""

    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("calibration_sessions.id"), nullable=False)
    test_point_id = Column(Integer, ForeignKey("test_points.id"), nullable=False)

    # Test execution
    nominal_value = Column(Float, nullable=True)
    measured_value = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)
    deviation = Column(Float, nullable=True)
    deviation_percent = Column(Float, nullable=True)

    # Tolerance info at time of test (legacy)
    tolerance_value = Column(Float, nullable=True)
    tolerance_type = Column(String(20), nullable=True)

    # Multi-component tolerance recorded at test time
    tol_pct_reading = Column(Float, nullable=True)
    tol_pct_range = Column(Float, nullable=True)
    tol_pct_span = Column(Float, nullable=True)
    tol_digits = Column(Float, nullable=True)
    tol_absolute = Column(Float, nullable=True)
    tol_resolution = Column(Float, nullable=True)
    tol_range_value = Column(Float, nullable=True)
    tol_span_value = Column(Float, nullable=True)
    calculated_tolerance = Column(Float, nullable=True, comment="Actual tolerance value calculated at test time")

    # Result
    status = Column(Enum(TestStatus), default=TestStatus.PENDING)
    input_method = Column(Enum(InputMethod), nullable=True)

    # Redo tracking
    is_redo = Column(Boolean, default=False)
    previous_result_id = Column(Integer, ForeignKey("test_results.id"), nullable=True)
    redo_reason = Column(Text, nullable=True)

    # Timestamps
    executed_at = Column(DateTime, server_default=func.now())

    # Relationships
    session = relationship("CalibrationSession", back_populates="results")
    previous_result = relationship("TestResult", remote_side=[id])

    __table_args__ = (
        Index("ix_result_session_testpoint", "session_id", "test_point_id"),
    )


# =============================================================================
# Changelog Models
# =============================================================================


class ChangeType(PyEnum):
    """Types of changelog entries."""

    FEATURE = "Feature"
    FIX = "Fix"
    IMPROVEMENT = "Improvement"
    BREAKING = "Breaking Change"


class ChangelogEntry(Base):
    """Application changelog entry for tracking changes and version history."""

    __tablename__ = "changelog_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(20), nullable=True, comment="Semantic version e.g. 0.2.0 - NULL if unpublished")
    timestamp = Column(DateTime, server_default=func.now(), nullable=False)
    change_type = Column(String(30), nullable=False, comment="Feature, Fix, Improvement, Breaking Change")
    category = Column(String(50), nullable=False, comment="Standards, DUTs, Procedures, etc.")
    description = Column(Text, nullable=False)
    author = Column(String(100), nullable=True, comment="Technician name or Claude")
    is_published = Column(Boolean, default=False, nullable=False, comment="True once included in a release")

    __table_args__ = (
        Index("ix_changelog_version", "version"),
        Index("ix_changelog_timestamp", "timestamp"),
    )


# Default changelog categories
DEFAULT_CHANGELOG_CATEGORIES = [
    "Standards",
    "DUTs",
    "Procedures",
    "Execution",
    "Reports",
    "Libraries",
    "Settings",
    "UI",
    "Database",
    "General",
]
