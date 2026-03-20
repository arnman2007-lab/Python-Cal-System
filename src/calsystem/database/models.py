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


class ToleranceType(PyEnum):
    """Tolerance specification types."""

    PERCENT = "percent"
    ABSOLUTE = "absolute"
    PPM = "ppm"


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


# =============================================================================
# Standards / Workstation Models
# =============================================================================


class Standard(Base):
    """Calibration standard (reference equipment)."""

    __tablename__ = "standards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    serial_number = Column(String(100), nullable=False)
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

    # Relationships
    workstation = relationship("WorkstationConfig", back_populates="standards")
    standard = relationship("Standard", back_populates="workstation_assignments")

    __table_args__ = (
        UniqueConstraint("workstation_id", "standard_id", name="uq_workstation_standard"),
    )


# =============================================================================
# DUT Models
# =============================================================================


class DUT(Base):
    """Device Under Test."""

    __tablename__ = "duts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_number = Column(String(100), nullable=False, unique=True, index=True)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    serial_number = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    # Capabilities
    remote_capable = Column(Boolean, default=False)
    preferred_input_method = Column(Enum(InputMethod), default=InputMethod.KEYBOARD)
    ocr_mode = Column(String(20), default="standard", comment="standard or seven_segment")

    # Calibration tracking
    calibration_interval_days = Column(Integer, default=365)
    last_calibration_date = Column(DateTime, nullable=True)
    next_due_date = Column(DateTime, nullable=True)

    # Assigned procedure
    default_procedure_id = Column(Integer, ForeignKey("procedures.id"), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
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

    # Tolerance
    tolerance_value = Column(Float, nullable=True)
    tolerance_type = Column(Enum(ToleranceType), default=ToleranceType.PERCENT)

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

    description = Column(Text, nullable=True)

    # Relationships
    section = relationship("TestSection", back_populates="test_points")


class WiringDiagram(Base):
    """Wiring diagram images for procedures."""

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


# =============================================================================
# Command Bank Models
# =============================================================================


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

    # Tolerance info at time of test
    tolerance_value = Column(Float, nullable=True)
    tolerance_type = Column(String(20), nullable=True)

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
