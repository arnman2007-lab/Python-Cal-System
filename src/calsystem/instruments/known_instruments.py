"""
Known instruments database with ID commands and device info.
"""

from dataclasses import dataclass
from typing import Optional, List
from enum import Enum


class DeviceType(Enum):
    CALIBRATOR = "Calibrator"
    DMM = "DMM"
    COUNTER = "Counter"
    OSCILLOSCOPE = "Oscilloscope"
    POWER_SUPPLY = "Power Supply"
    SIGNAL_GENERATOR = "Signal Generator"
    OTHER = "Other"


@dataclass
class KnownInstrument:
    """Definition of a known instrument model."""
    make: str
    model: str
    device_type: DeviceType
    id_command: str = "*IDN?"
    description: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.make} {self.model}"

    @property
    def search_key(self) -> str:
        """Key for searching (lowercase)."""
        return f"{self.make} {self.model} {self.description}".lower()


# Known instruments database
# Add more as needed - this is a starting list of common cal lab equipment
KNOWN_INSTRUMENTS: List[KnownInstrument] = [
    # Fluke Calibrators
    KnownInstrument("Fluke", "5500A", DeviceType.CALIBRATOR, "*IDN?", "Multi-Product Calibrator"),
    KnownInstrument("Fluke", "5502A", DeviceType.CALIBRATOR, "*IDN?", "Multi-Product Calibrator"),
    KnownInstrument("Fluke", "5520A", DeviceType.CALIBRATOR, "*IDN?", "Multi-Product Calibrator"),
    KnownInstrument("Fluke", "5522A", DeviceType.CALIBRATOR, "*IDN?", "Multi-Product Calibrator"),
    KnownInstrument("Fluke", "5550A", DeviceType.CALIBRATOR, "*IDN?", "Multi-Product Calibrator"),
    KnownInstrument("Fluke", "5560A", DeviceType.CALIBRATOR, "*IDN?", "Multi-Product Calibrator"),
    KnownInstrument("Fluke", "5700A", DeviceType.CALIBRATOR, "*IDN?", "Multi-Function Calibrator"),
    KnownInstrument("Fluke", "5720A", DeviceType.CALIBRATOR, "*IDN?", "Multi-Function Calibrator"),
    KnownInstrument("Fluke", "5730A", DeviceType.CALIBRATOR, "*IDN?", "High-Performance Calibrator"),
    KnownInstrument("Fluke", "5790A", DeviceType.CALIBRATOR, "*IDN?", "AC Measurement Standard"),
    KnownInstrument("Fluke", "5790B", DeviceType.CALIBRATOR, "*IDN?", "AC Measurement Standard"),
    KnownInstrument("Fluke", "6100A", DeviceType.CALIBRATOR, "*IDN?", "Electrical Power Standard"),
    KnownInstrument("Fluke", "6105A", DeviceType.CALIBRATOR, "*IDN?", "Electrical Power Standard"),
    KnownInstrument("Fluke", "6135A", DeviceType.CALIBRATOR, "*IDN?", "Electrical Power Standard"),
    KnownInstrument("Fluke", "9100", DeviceType.CALIBRATOR, "*IDN?", "Universal Calibration System"),

    # HP/Agilent/Keysight DMMs
    KnownInstrument("HP", "3455A", DeviceType.DMM, "ID?", "Digital Voltmeter"),
    KnownInstrument("HP", "3456A", DeviceType.DMM, "ID?", "Digital Voltmeter"),
    KnownInstrument("HP", "3457A", DeviceType.DMM, "ID?", "Digital Multimeter"),
    KnownInstrument("HP", "3458A", DeviceType.DMM, "ID?", "Digital Multimeter"),
    KnownInstrument("HP", "34401A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),
    KnownInstrument("Agilent", "34401A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),
    KnownInstrument("Agilent", "34410A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),
    KnownInstrument("Agilent", "34411A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),
    KnownInstrument("Agilent", "3458A", DeviceType.DMM, "ID?", "Digital Multimeter"),
    KnownInstrument("Keysight", "34460A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),
    KnownInstrument("Keysight", "34461A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),
    KnownInstrument("Keysight", "34465A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),
    KnownInstrument("Keysight", "34470A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),
    KnownInstrument("Keysight", "3458A", DeviceType.DMM, "ID?", "Digital Multimeter"),

    # Fluke DMMs
    KnownInstrument("Fluke", "8505A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),
    KnownInstrument("Fluke", "8506A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),
    KnownInstrument("Fluke", "8508A", DeviceType.DMM, "*IDN?", "Reference Multimeter"),
    KnownInstrument("Fluke", "8588A", DeviceType.DMM, "*IDN?", "Reference Multimeter"),
    KnownInstrument("Fluke", "8845A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),
    KnownInstrument("Fluke", "8846A", DeviceType.DMM, "*IDN?", "Digital Multimeter"),

    # Counters
    KnownInstrument("HP", "5334A", DeviceType.COUNTER, "*IDN?", "Universal Counter"),
    KnownInstrument("HP", "5335A", DeviceType.COUNTER, "*IDN?", "Universal Counter"),
    KnownInstrument("HP", "53131A", DeviceType.COUNTER, "*IDN?", "Universal Counter"),
    KnownInstrument("HP", "53132A", DeviceType.COUNTER, "*IDN?", "Universal Counter"),
    KnownInstrument("Agilent", "53131A", DeviceType.COUNTER, "*IDN?", "Universal Counter"),
    KnownInstrument("Agilent", "53132A", DeviceType.COUNTER, "*IDN?", "Universal Counter"),
    KnownInstrument("Keysight", "53220A", DeviceType.COUNTER, "*IDN?", "Universal Counter"),
    KnownInstrument("Keysight", "53230A", DeviceType.COUNTER, "*IDN?", "Universal Counter"),
    KnownInstrument("Philips", "PM6681", DeviceType.COUNTER, "*IDN?", "Timer/Counter"),
    KnownInstrument("Fluke", "PM6681", DeviceType.COUNTER, "*IDN?", "Timer/Counter"),

    # Signal Generators
    KnownInstrument("HP", "3325A", DeviceType.SIGNAL_GENERATOR, "*IDN?", "Synthesizer/Function Generator"),
    KnownInstrument("HP", "3325B", DeviceType.SIGNAL_GENERATOR, "*IDN?", "Synthesizer/Function Generator"),
    KnownInstrument("HP", "33120A", DeviceType.SIGNAL_GENERATOR, "*IDN?", "Function Generator"),
    KnownInstrument("Agilent", "33120A", DeviceType.SIGNAL_GENERATOR, "*IDN?", "Function Generator"),
    KnownInstrument("Agilent", "33220A", DeviceType.SIGNAL_GENERATOR, "*IDN?", "Function Generator"),
    KnownInstrument("Agilent", "33250A", DeviceType.SIGNAL_GENERATOR, "*IDN?", "Function Generator"),
    KnownInstrument("Keysight", "33500B", DeviceType.SIGNAL_GENERATOR, "*IDN?", "Waveform Generator"),
    KnownInstrument("Keysight", "33600A", DeviceType.SIGNAL_GENERATOR, "*IDN?", "Waveform Generator"),

    # Power Supplies
    KnownInstrument("HP", "6632A", DeviceType.POWER_SUPPLY, "*IDN?", "DC Power Supply"),
    KnownInstrument("HP", "6633A", DeviceType.POWER_SUPPLY, "*IDN?", "DC Power Supply"),
    KnownInstrument("HP", "6634A", DeviceType.POWER_SUPPLY, "*IDN?", "DC Power Supply"),
    KnownInstrument("Agilent", "E3631A", DeviceType.POWER_SUPPLY, "*IDN?", "DC Power Supply"),
    KnownInstrument("Agilent", "E3632A", DeviceType.POWER_SUPPLY, "*IDN?", "DC Power Supply"),
    KnownInstrument("Keysight", "E36313A", DeviceType.POWER_SUPPLY, "*IDN?", "DC Power Supply"),
]


def get_instruments_by_type(device_type: DeviceType) -> List[KnownInstrument]:
    """Get all instruments of a specific type."""
    return [i for i in KNOWN_INSTRUMENTS if i.device_type == device_type]


def search_instruments(query: str) -> List[KnownInstrument]:
    """Search instruments by make, model, or description."""
    query = query.lower()
    return [i for i in KNOWN_INSTRUMENTS if query in i.search_key]


def get_instrument(make: str, model: str) -> Optional[KnownInstrument]:
    """Get a specific instrument by make and model."""
    make_lower = make.lower()
    model_lower = model.lower()
    for inst in KNOWN_INSTRUMENTS:
        if inst.make.lower() == make_lower and inst.model.lower() == model_lower:
            return inst
    return None


def get_id_command(make: str, model: str) -> str:
    """Get the ID command for a specific instrument."""
    inst = get_instrument(make, model)
    return inst.id_command if inst else "*IDN?"
