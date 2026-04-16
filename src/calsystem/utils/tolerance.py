"""
Tolerance calculation and formatting utilities for calibration specifications.

Supports multi-component tolerances like:
- "0.05% of reading + 0.02% of range + 3 digits"

Formula:
    total = (nominal × %rdg/100) + (range × %range/100) + (digits × resolution) + absolute
"""

from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class ToleranceSpec:
    """
    Multi-component tolerance specification.

    Attributes:
        pct_reading: Percentage of reading (e.g., 0.05 for 0.05%)
        pct_range: Percentage of range/full scale (e.g., 0.02 for 0.02%)
        pct_span: Percentage of span (e.g., 0.1 for 0.1% of span)
        digits: Number of digits for floor value
        absolute: Absolute tolerance value in measurement units
        resolution: Display resolution for digit calculation (e.g., 0.001)
        range_value: Range/full scale reference value for % range calculation
        span_value: Span reference value for % span calculation (e.g., 16 for 4-20mA)
    """
    pct_reading: float = 0.0
    pct_range: float = 0.0
    pct_span: float = 0.0
    digits: float = 0.0
    absolute: float = 0.0
    resolution: float = 0.0
    range_value: float = 0.0
    span_value: float = 0.0

    def calculate(self, nominal: float) -> float:
        """
        Calculate total tolerance value for a given nominal/reading.

        Args:
            nominal: The nominal or measured value to calculate tolerance for

        Returns:
            Total tolerance value in measurement units

        Formula:
            total = (nominal × pct_reading/100) +
                    (range_value × pct_range/100) +
                    (span_value × pct_span/100) +
                    (digits × resolution) +
                    absolute
        """
        total = 0.0

        # % of reading component
        if self.pct_reading > 0:
            total += abs(nominal) * (self.pct_reading / 100.0)

        # % of range/full scale component
        if self.pct_range > 0 and self.range_value > 0:
            total += self.range_value * (self.pct_range / 100.0)

        # % of span component
        if self.pct_span > 0 and self.span_value > 0:
            total += self.span_value * (self.pct_span / 100.0)

        # Digits floor component
        if self.digits > 0 and self.resolution > 0:
            total += self.digits * self.resolution

        # Absolute component
        if self.absolute > 0:
            total += self.absolute

        return total

    def format_spec(self, include_values: bool = True) -> str:
        """
        Format tolerance specification as human-readable string.

        Args:
            include_values: If True, include numeric values; if False, just show types

        Returns:
            Formatted string like "±0.05% rdg + ±3 dgt" or "% rdg + dgt"
        """
        parts = []

        if self.pct_reading > 0:
            if include_values:
                # Format nicely - remove trailing zeros
                val = f"{self.pct_reading:g}"
                parts.append(f"±{val}% rdg")
            else:
                parts.append("% rdg")

        if self.pct_range > 0:
            if include_values:
                val = f"{self.pct_range:g}"
                parts.append(f"±{val}% FS")
            else:
                parts.append("% FS")

        if self.pct_span > 0:
            if include_values:
                val = f"{self.pct_span:g}"
                parts.append(f"±{val}% span")
            else:
                parts.append("% span")

        if self.digits > 0:
            if include_values:
                parts.append(f"±{int(self.digits)} dgt")
            else:
                parts.append("dgt")

        if self.absolute > 0:
            if include_values:
                val = f"{self.absolute:g}"
                parts.append(f"±{val}")
            else:
                parts.append("abs")

        return " + ".join(parts) if parts else "±0"

    def is_empty(self) -> bool:
        """Check if all tolerance components are zero/empty."""
        return (
            self.pct_reading == 0 and
            self.pct_range == 0 and
            self.pct_span == 0 and
            self.digits == 0 and
            self.absolute == 0
        )

    @classmethod
    def from_legacy(cls, tolerance_value: float, tolerance_type: str) -> "ToleranceSpec":
        """
        Create ToleranceSpec from legacy single-value tolerance.

        Args:
            tolerance_value: The legacy tolerance value
            tolerance_type: One of "percent", "absolute", "ppm"

        Returns:
            ToleranceSpec with appropriate component set
        """
        spec = cls()

        if tolerance_type == "percent":
            spec.pct_reading = tolerance_value
        elif tolerance_type == "absolute":
            spec.absolute = tolerance_value
        elif tolerance_type == "ppm":
            # Convert PPM to percentage (1 ppm = 0.0001%)
            spec.pct_reading = tolerance_value / 10000.0

        return spec


def check_tolerance(
    measured: float,
    nominal: float,
    spec: ToleranceSpec
) -> Tuple[bool, float, float]:
    """
    Check if measured value is within tolerance.

    Args:
        measured: The measured/actual value
        nominal: The expected/nominal value
        spec: Tolerance specification

    Returns:
        Tuple of:
            - passed: True if within tolerance
            - deviation: measured - nominal
            - tolerance_limit: calculated tolerance value
    """
    deviation = measured - nominal
    tolerance_limit = spec.calculate(nominal)
    passed = abs(deviation) <= tolerance_limit

    return passed, deviation, tolerance_limit


def format_tolerance_with_value(
    spec: ToleranceSpec,
    nominal: float,
    unit: str = ""
) -> str:
    """
    Format tolerance showing both spec and calculated value.

    Args:
        spec: Tolerance specification
        nominal: Nominal value for calculation
        unit: Unit string to append

    Returns:
        String like "±0.05% rdg + ±3 dgt (±0.027 V)"
    """
    spec_str = spec.format_spec()
    calculated = spec.calculate(nominal)

    if unit:
        return f"{spec_str} (±{calculated:g} {unit})"
    else:
        return f"{spec_str} (±{calculated:g})"
