"""
Command bank management for device-specific SCPI commands.
"""

from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
import json

from loguru import logger


@dataclass
class DeviceCommands:
    """Command set for a specific device model."""

    make: str
    model: str
    device_type: str = "unknown"  # calibrator, dmm, counter, dut
    description: str = ""

    # Standard commands
    idn: str = "*IDN?"
    reset: str = "*RST"
    clear: str = "*CLS"
    opc: str = "*OPC?"

    # Output control (for calibrators)
    output_on: str = "OPER"
    output_off: str = "STBY"

    # Measurement (for DMMs)
    measure_dc_voltage: str = "MEAS:VOLT:DC?"
    measure_ac_voltage: str = "MEAS:VOLT:AC?"
    measure_dc_current: str = "MEAS:CURR:DC?"
    measure_ac_current: str = "MEAS:CURR:AC?"
    measure_resistance: str = "MEAS:RES?"
    measure_frequency: str = "MEAS:FREQ?"

    # Source commands (for calibrators)
    source_dc_voltage: str = "OUT {value} V"
    source_ac_voltage: str = "OUT {value} V, {frequency} Hz"
    source_dc_current: str = "OUT {value} A"
    source_ac_current: str = "OUT {value} A, {frequency} Hz"
    source_resistance: str = "OUT {value} OHM"

    # Custom commands (for device-specific operations)
    custom_commands: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            "make": self.make,
            "model": self.model,
            "device_type": self.device_type,
            "description": self.description,
            "commands": {
                "idn": self.idn,
                "reset": self.reset,
                "clear": self.clear,
                "opc": self.opc,
                "output_on": self.output_on,
                "output_off": self.output_off,
                "measure_dc_voltage": self.measure_dc_voltage,
                "measure_ac_voltage": self.measure_ac_voltage,
                "measure_dc_current": self.measure_dc_current,
                "measure_ac_current": self.measure_ac_current,
                "measure_resistance": self.measure_resistance,
                "measure_frequency": self.measure_frequency,
                "source_dc_voltage": self.source_dc_voltage,
                "source_ac_voltage": self.source_ac_voltage,
                "source_dc_current": self.source_dc_current,
                "source_ac_current": self.source_ac_current,
                "source_resistance": self.source_resistance,
                "custom": self.custom_commands,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceCommands":
        """Create from dictionary."""
        commands = data.get("commands", {})
        return cls(
            make=data.get("make", ""),
            model=data.get("model", ""),
            device_type=data.get("device_type", "unknown"),
            description=data.get("description", ""),
            idn=commands.get("idn", "*IDN?"),
            reset=commands.get("reset", "*RST"),
            clear=commands.get("clear", "*CLS"),
            opc=commands.get("opc", "*OPC?"),
            output_on=commands.get("output_on", "OPER"),
            output_off=commands.get("output_off", "STBY"),
            measure_dc_voltage=commands.get("measure_dc_voltage", "MEAS:VOLT:DC?"),
            measure_ac_voltage=commands.get("measure_ac_voltage", "MEAS:VOLT:AC?"),
            measure_dc_current=commands.get("measure_dc_current", "MEAS:CURR:DC?"),
            measure_ac_current=commands.get("measure_ac_current", "MEAS:CURR:AC?"),
            measure_resistance=commands.get("measure_resistance", "MEAS:RES?"),
            measure_frequency=commands.get("measure_frequency", "MEAS:FREQ?"),
            source_dc_voltage=commands.get("source_dc_voltage", "OUT {value} V"),
            source_ac_voltage=commands.get("source_ac_voltage", "OUT {value} V, {frequency} Hz"),
            source_dc_current=commands.get("source_dc_current", "OUT {value} A"),
            source_ac_current=commands.get("source_ac_current", "OUT {value} A, {frequency} Hz"),
            source_resistance=commands.get("source_resistance", "OUT {value} OHM"),
            custom_commands=commands.get("custom", {}),
        )


class CommandBankManager:
    """Manages device command banks."""

    def __init__(self):
        self._cache: Dict[str, DeviceCommands] = {}
        self._load_builtin_commands()

    def _load_builtin_commands(self):
        """Load built-in command sets for common instruments."""
        # Fluke 5520A
        self._cache["FLUKE_5520A"] = DeviceCommands(
            make="FLUKE",
            model="5520A",
            device_type="calibrator",
            description="Fluke 5520A Multi-Product Calibrator",
            output_on="OPER",
            output_off="STBY",
            source_dc_voltage="OUT {value} V",
            source_ac_voltage="OUT {value} V, {frequency} HZ",
            source_dc_current="OUT {value} A",
            source_ac_current="OUT {value} A, {frequency} HZ",
            source_resistance="OUT {value} OHM",
        )

        # Fluke 5730A
        self._cache["FLUKE_5730A"] = DeviceCommands(
            make="FLUKE",
            model="5730A",
            device_type="calibrator",
            description="Fluke 5730A High-Performance Calibrator",
            output_on="OPER",
            output_off="STBY",
            source_dc_voltage="OUT {value} V",
            source_ac_voltage="OUT {value} V, {frequency} HZ",
        )

        # Agilent/Keysight 3458A
        self._cache["AGILENT_3458A"] = DeviceCommands(
            make="AGILENT",
            model="3458A",
            device_type="dmm",
            description="Agilent 3458A Reference Multimeter",
            measure_dc_voltage="DCV",
            measure_ac_voltage="ACV",
            measure_dc_current="DCI",
            measure_ac_current="ACI",
            measure_resistance="OHM",
            measure_frequency="FREQ",
        )

        # Keysight 34401A
        self._cache["KEYSIGHT_34401A"] = DeviceCommands(
            make="KEYSIGHT",
            model="34401A",
            device_type="dmm",
            description="Keysight 34401A Digital Multimeter",
            measure_dc_voltage="MEAS:VOLT:DC?",
            measure_ac_voltage="MEAS:VOLT:AC?",
            measure_dc_current="MEAS:CURR:DC?",
            measure_ac_current="MEAS:CURR:AC?",
            measure_resistance="MEAS:RES?",
            measure_frequency="MEAS:FREQ?",
        )

        logger.info(f"Loaded {len(self._cache)} built-in command sets")

    def _make_key(self, make: str, model: str) -> str:
        """Generate cache key from make and model."""
        return f"{make.upper()}_{model.upper()}"

    def get(self, make: str, model: str) -> Optional[DeviceCommands]:
        """
        Get command set for a device.

        Args:
            make: Device manufacturer.
            model: Device model.

        Returns:
            DeviceCommands if found, None otherwise.
        """
        key = self._make_key(make, model)
        return self._cache.get(key)

    def exists(self, make: str, model: str) -> bool:
        """Check if command set exists for device."""
        key = self._make_key(make, model)
        return key in self._cache

    def add(self, commands: DeviceCommands) -> bool:
        """
        Add or update a command set.

        Args:
            commands: DeviceCommands to add.

        Returns:
            True if added successfully.
        """
        key = self._make_key(commands.make, commands.model)
        self._cache[key] = commands
        logger.info(f"Added command set for {commands.make} {commands.model}")
        return True

    def remove(self, make: str, model: str) -> bool:
        """
        Remove a command set.

        Args:
            make: Device manufacturer.
            model: Device model.

        Returns:
            True if removed.
        """
        key = self._make_key(make, model)
        if key in self._cache:
            del self._cache[key]
            logger.info(f"Removed command set for {make} {model}")
            return True
        return False

    def list_all(self) -> List[tuple]:
        """
        Get list of all available command sets.

        Returns:
            List of (make, model, device_type) tuples.
        """
        return [
            (cmd.make, cmd.model, cmd.device_type)
            for cmd in self._cache.values()
        ]

    def export_to_json(self, filepath: str):
        """Export all command sets to JSON file."""
        data = {key: cmd.to_dict() for key, cmd in self._cache.items()}
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Exported {len(data)} command sets to {filepath}")

    def import_from_json(self, filepath: str):
        """Import command sets from JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)

        count = 0
        for key, cmd_data in data.items():
            commands = DeviceCommands.from_dict(cmd_data)
            self._cache[key] = commands
            count += 1

        logger.info(f"Imported {count} command sets from {filepath}")

    def get_command(
        self,
        make: str,
        model: str,
        command_name: str,
        **kwargs
    ) -> Optional[str]:
        """
        Get a formatted command string.

        Args:
            make: Device manufacturer.
            model: Device model.
            command_name: Name of the command (e.g., "source_dc_voltage").
            **kwargs: Parameters to format into the command.

        Returns:
            Formatted command string or None.
        """
        commands = self.get(make, model)
        if not commands:
            return None

        # Get the command template
        if hasattr(commands, command_name):
            template = getattr(commands, command_name)
        elif command_name in commands.custom_commands:
            template = commands.custom_commands[command_name]
        else:
            return None

        # Format with provided kwargs
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing parameter for command {command_name}: {e}")
            return template  # Return unformatted


# Global command bank manager
_command_bank: Optional[CommandBankManager] = None


def get_command_bank() -> CommandBankManager:
    """Get the global command bank manager."""
    global _command_bank
    if _command_bank is None:
        _command_bank = CommandBankManager()
    return _command_bank
