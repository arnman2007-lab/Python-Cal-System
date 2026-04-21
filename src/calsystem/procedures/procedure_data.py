"""
Data classes for in-memory procedure representation.

These classes represent the structure of a procedure loaded from a .csp file,
independent of the database models.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class TestPointData:
    """Single test point within a section."""

    # Identification & ordering
    order: int = 0
    description: Optional[str] = None

    # Test type
    test_type: str = "measurement"  # measurement, pass_fail, calculated, dmm_measurement, calibrator_dmm

    # Main test values
    nominal_value: Optional[float] = None
    unit: Optional[str] = None
    frequency: Optional[float] = None
    frequency_unit: str = "Hz"

    # Pre-conditioning
    pre_nominal_value: Optional[float] = None
    pre_unit: Optional[str] = None
    pre_frequency: Optional[float] = None
    pre_frequency_unit: str = "Hz"
    pre_delay_seconds: float = 0
    pre_conditioning_steps: Optional[List[Dict[str, Any]]] = None

    # Tolerance - multi-component
    tol_pct_reading: float = 0
    tol_pct_range: float = 0
    tol_pct_span: float = 0
    tol_digits: float = 0
    tol_absolute: float = 0
    tol_resolution: Optional[float] = None
    tol_range_value: Optional[float] = None
    tol_span_value: Optional[float] = None

    # Legacy tolerance (for backward compatibility)
    tolerance_value: Optional[float] = None
    tolerance_type: str = "PERCENT"  # PERCENT, ABSOLUTE, PPM

    # Measurement target
    measurement_target: str = "PRIMARY"  # PRIMARY, FREQUENCY, CUSTOM
    expected_value: Optional[float] = None
    expected_unit: Optional[str] = None

    # Pass/Fail test fields
    pass_fail_prompt: Optional[str] = None
    pass_fail_min: Optional[float] = None
    pass_fail_max: Optional[float] = None
    pass_fail_range_unit: Optional[str] = None
    pass_fail_comparison_type: Optional[str] = None  # 'range', 'gt', 'lt'

    # Commands
    source_command: Optional[str] = None
    measure_command: Optional[str] = None
    operate_command: Optional[str] = None
    standby_command: Optional[str] = None

    # Operator instructions
    operator_prompt: Optional[str] = None
    wiring_diagram_type: Optional[str] = None

    # Calculated test
    formula: Optional[str] = None

    # DMM configuration
    dmm_config: Optional[Dict[str, Any]] = None

    # Excel integration
    excel_workbook: Optional[str] = None
    excel_sheet: Optional[str] = None
    excel_cell: Optional[str] = None

    # DUT Remote Communication
    # Setup command - sent to DUT to configure it (e.g., change range, set mode)
    dut_setup_command: Optional[str] = None
    dut_setup_param: Optional[str] = None  # Parameter value to substitute into command {value}
    # Pre-check - query DUT to verify state
    dut_pre_check_command: Optional[str] = None
    dut_pre_check_param: Optional[str] = None  # Parameter value to substitute into command {value}
    dut_pre_check_expected: Optional[str] = None
    # Post-read - read measurement from DUT
    dut_post_read_command: Optional[str] = None
    dut_post_read_param: Optional[str] = None  # Parameter value to substitute into command {value}
    dut_post_read_parser: Optional[str] = None
    dut_post_read_index: Optional[int] = None  # For CSV responses, which field contains the value (0-based)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "order": self.order,
            "description": self.description,
            "test_type": self.test_type,
            "nominal_value": self.nominal_value,
            "unit": self.unit,
            "frequency": self.frequency,
            "frequency_unit": self.frequency_unit,
            "pre_nominal_value": self.pre_nominal_value,
            "pre_unit": self.pre_unit,
            "pre_frequency": self.pre_frequency,
            "pre_frequency_unit": self.pre_frequency_unit,
            "pre_delay_seconds": self.pre_delay_seconds,
            "pre_conditioning_steps": self.pre_conditioning_steps,
            "tol_pct_reading": self.tol_pct_reading,
            "tol_pct_range": self.tol_pct_range,
            "tol_pct_span": self.tol_pct_span,
            "tol_digits": self.tol_digits,
            "tol_absolute": self.tol_absolute,
            "tol_resolution": self.tol_resolution,
            "tol_range_value": self.tol_range_value,
            "tol_span_value": self.tol_span_value,
            "tolerance_value": self.tolerance_value,
            "tolerance_type": self.tolerance_type,
            "measurement_target": self.measurement_target,
            "expected_value": self.expected_value,
            "expected_unit": self.expected_unit,
            "pass_fail_prompt": self.pass_fail_prompt,
            "pass_fail_min": self.pass_fail_min,
            "pass_fail_max": self.pass_fail_max,
            "pass_fail_range_unit": self.pass_fail_range_unit,
            "pass_fail_comparison_type": self.pass_fail_comparison_type,
            "source_command": self.source_command,
            "measure_command": self.measure_command,
            "operate_command": self.operate_command,
            "standby_command": self.standby_command,
            "operator_prompt": self.operator_prompt,
            "wiring_diagram_type": self.wiring_diagram_type,
            "formula": self.formula,
            "dmm_config": self.dmm_config,
            "excel_workbook": self.excel_workbook,
            "excel_sheet": self.excel_sheet,
            "excel_cell": self.excel_cell,
            "dut_setup_command": self.dut_setup_command,
            "dut_setup_param": self.dut_setup_param,
            "dut_pre_check_command": self.dut_pre_check_command,
            "dut_pre_check_param": self.dut_pre_check_param,
            "dut_pre_check_expected": self.dut_pre_check_expected,
            "dut_post_read_command": self.dut_post_read_command,
            "dut_post_read_param": self.dut_post_read_param,
            "dut_post_read_parser": self.dut_post_read_parser,
            "dut_post_read_index": self.dut_post_read_index,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestPointData":
        """Create from dictionary (JSON deserialization)."""
        return cls(
            order=data.get("order", 0),
            description=data.get("description"),
            test_type=data.get("test_type", "measurement"),
            nominal_value=data.get("nominal_value"),
            unit=data.get("unit"),
            frequency=data.get("frequency"),
            frequency_unit=data.get("frequency_unit", "Hz"),
            pre_nominal_value=data.get("pre_nominal_value"),
            pre_unit=data.get("pre_unit"),
            pre_frequency=data.get("pre_frequency"),
            pre_frequency_unit=data.get("pre_frequency_unit", "Hz"),
            pre_delay_seconds=data.get("pre_delay_seconds", 0),
            pre_conditioning_steps=data.get("pre_conditioning_steps"),
            tol_pct_reading=data.get("tol_pct_reading", 0),
            tol_pct_range=data.get("tol_pct_range", 0),
            tol_pct_span=data.get("tol_pct_span", 0),
            tol_digits=data.get("tol_digits", 0),
            tol_absolute=data.get("tol_absolute", 0),
            tol_resolution=data.get("tol_resolution"),
            tol_range_value=data.get("tol_range_value"),
            tol_span_value=data.get("tol_span_value"),
            tolerance_value=data.get("tolerance_value"),
            tolerance_type=data.get("tolerance_type", "PERCENT"),
            measurement_target=data.get("measurement_target", "PRIMARY"),
            expected_value=data.get("expected_value"),
            expected_unit=data.get("expected_unit"),
            pass_fail_prompt=data.get("pass_fail_prompt"),
            pass_fail_min=data.get("pass_fail_min"),
            pass_fail_max=data.get("pass_fail_max"),
            pass_fail_range_unit=data.get("pass_fail_range_unit"),
            pass_fail_comparison_type=data.get("pass_fail_comparison_type"),
            source_command=data.get("source_command"),
            measure_command=data.get("measure_command"),
            operate_command=data.get("operate_command"),
            standby_command=data.get("standby_command"),
            operator_prompt=data.get("operator_prompt"),
            wiring_diagram_type=data.get("wiring_diagram_type"),
            formula=data.get("formula"),
            dmm_config=data.get("dmm_config"),
            excel_workbook=data.get("excel_workbook"),
            excel_sheet=data.get("excel_sheet"),
            excel_cell=data.get("excel_cell"),
            dut_setup_command=data.get("dut_setup_command"),
            dut_setup_param=data.get("dut_setup_param"),
            dut_pre_check_command=data.get("dut_pre_check_command"),
            dut_pre_check_param=data.get("dut_pre_check_param"),
            dut_pre_check_expected=data.get("dut_pre_check_expected"),
            dut_post_read_command=data.get("dut_post_read_command"),
            dut_post_read_param=data.get("dut_post_read_param"),
            dut_post_read_parser=data.get("dut_post_read_parser"),
            dut_post_read_index=data.get("dut_post_read_index"),
        )


@dataclass
class TestSectionData:
    """Test section containing multiple test points."""

    name: str
    order: int = 0
    description: Optional[str] = None
    standard_section_type: Optional[str] = None

    # Section-level instructions
    section_prompt: Optional[str] = None
    section_command: Optional[str] = None  # JSON array of command refs
    section_wiring_type: Optional[str] = None

    # Embedded wiring image (relative path within .csp)
    wiring_image: Optional[str] = None

    # Test points in this section
    test_points: List[TestPointData] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "order": self.order,
            "description": self.description,
            "standard_section_type": self.standard_section_type,
            "section_prompt": self.section_prompt,
            "section_command": self.section_command,
            "section_wiring_type": self.section_wiring_type,
            "wiring_image": self.wiring_image,
            "test_points": [tp.to_dict() for tp in self.test_points],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestSectionData":
        """Create from dictionary (JSON deserialization)."""
        test_points = [
            TestPointData.from_dict(tp) for tp in data.get("test_points", [])
        ]
        return cls(
            name=data.get("name", "Unnamed Section"),
            order=data.get("order", 0),
            description=data.get("description"),
            standard_section_type=data.get("standard_section_type"),
            section_prompt=data.get("section_prompt"),
            section_command=data.get("section_command"),
            section_wiring_type=data.get("section_wiring_type"),
            wiring_image=data.get("wiring_image"),
            test_points=test_points,
        )


@dataclass
class ProcedureData:
    """Complete procedure with all sections and test points."""

    name: str
    version: str = "1.0"
    description: Optional[str] = None
    target_make: Optional[str] = None
    target_model: Optional[str] = None
    created_by: Optional[str] = None

    # Sections
    sections: List[TestSectionData] = field(default_factory=list)

    # Image data (populated when loading from .csp)
    # Key: relative path (e.g., "images/dc_voltage.png"), Value: bytes
    images: Dict[str, bytes] = field(default_factory=dict)

    @property
    def section_count(self) -> int:
        """Number of sections in procedure."""
        return len(self.sections)

    @property
    def test_point_count(self) -> int:
        """Total number of test points across all sections."""
        return sum(len(s.test_points) for s in self.sections)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization (excludes images)."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "target_make": self.target_make,
            "target_model": self.target_model,
            "created_by": self.created_by,
            "sections": [s.to_dict() for s in self.sections],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcedureData":
        """Create from dictionary (JSON deserialization)."""
        sections = [
            TestSectionData.from_dict(s) for s in data.get("sections", [])
        ]
        return cls(
            name=data.get("name", "Unnamed Procedure"),
            version=data.get("version", "1.0"),
            description=data.get("description"),
            target_make=data.get("target_make"),
            target_model=data.get("target_model"),
            created_by=data.get("created_by"),
            sections=sections,
        )

    def get_image(self, path: str) -> Optional[bytes]:
        """Get image data by relative path."""
        return self.images.get(path)

    def add_image(self, path: str, data: bytes) -> None:
        """Add or update an image."""
        self.images[path] = data

    def get_all_wiring_images(self) -> List[str]:
        """Get list of all wiring image paths referenced in sections."""
        paths = []
        for section in self.sections:
            if section.wiring_image:
                paths.append(section.wiring_image)
        return paths


@dataclass
class ProcedureMetadata:
    """Metadata about a .csp file (for quick reads without full load)."""

    csp_version: str = "1.0"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    software_version: Optional[str] = None

    # Quick info from procedure.json
    name: Optional[str] = None
    target_model: Optional[str] = None
    version: Optional[str] = None
    section_count: int = 0
    test_point_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "csp_version": self.csp_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "software_version": self.software_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcedureMetadata":
        """Create from dictionary (JSON deserialization)."""
        created_at = None
        updated_at = None
        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError):
                pass
        if data.get("updated_at"):
            try:
                updated_at = datetime.fromisoformat(data["updated_at"])
            except (ValueError, TypeError):
                pass

        return cls(
            csp_version=data.get("csp_version", "1.0"),
            created_at=created_at,
            updated_at=updated_at,
            created_by=data.get("created_by"),
            software_version=data.get("software_version"),
        )
