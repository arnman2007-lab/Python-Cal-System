"""
PyVISA instrument communication manager.
"""

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from functools import lru_cache

from loguru import logger

try:
    import pyvisa
    PYVISA_AVAILABLE = True
except ImportError:
    PYVISA_AVAILABLE = False
    logger.warning("PyVISA not available - instrument communication disabled")

from calsystem.config.settings import get_settings


@dataclass
class InstrumentInfo:
    """Information about a detected instrument."""

    address: str
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    firmware: str = ""
    is_connected: bool = False
    error: Optional[str] = None

    @property
    def idn_string(self) -> str:
        """Get formatted IDN string."""
        return f"{self.manufacturer},{self.model},{self.serial_number},{self.firmware}"


class VISAManager:
    """Manages VISA instrument communication."""

    _instance: Optional["VISAManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._rm: Optional["pyvisa.ResourceManager"] = None
        self._instruments: Dict[str, Any] = {}  # address -> instrument object
        self._settings = get_settings()

    def initialize(self) -> bool:
        """
        Initialize the VISA resource manager.

        Returns:
            True if successful, False otherwise.
        """
        if not PYVISA_AVAILABLE:
            logger.error("PyVISA is not installed")
            return False

        try:
            backend = self._settings.instruments.visa_backend
            self._rm = pyvisa.ResourceManager(backend)
            logger.info(f"VISA Resource Manager initialized with backend: {backend}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize VISA: {e}")
            return False

    def close(self):
        """Close all instrument connections and resource manager."""
        for address in list(self._instruments.keys()):
            self.disconnect(address)

        if self._rm:
            self._rm.close()
            self._rm = None
            logger.info("VISA Resource Manager closed")

    def scan(self) -> List[str]:
        """
        Scan for available VISA resources.

        Returns:
            List of resource addresses.
        """
        if not self._rm:
            if not self.initialize():
                return []

        try:
            resources = self._rm.list_resources()
            logger.info(f"Found {len(resources)} VISA resources")
            return list(resources)
        except Exception as e:
            logger.error(f"Error scanning for resources: {e}")
            return []

    def identify(self, address: str) -> InstrumentInfo:
        """
        Query instrument identification (*IDN?).

        Args:
            address: VISA resource address.

        Returns:
            InstrumentInfo with device details.
        """
        info = InstrumentInfo(address=address)

        if not self._rm:
            if not self.initialize():
                info.error = "VISA not initialized"
                return info

        try:
            timeout = self._settings.instruments.idn_timeout_ms

            inst = self._rm.open_resource(address)
            inst.timeout = timeout

            # Query *IDN?
            response = inst.query("*IDN?").strip()
            inst.close()

            # Parse response (format: Manufacturer,Model,Serial,Firmware)
            parts = response.split(",")
            if len(parts) >= 1:
                info.manufacturer = parts[0].strip()
            if len(parts) >= 2:
                info.model = parts[1].strip()
            if len(parts) >= 3:
                info.serial_number = parts[2].strip()
            if len(parts) >= 4:
                info.firmware = parts[3].strip()

            info.is_connected = True
            logger.info(f"Identified {address}: {info.manufacturer} {info.model}")

        except Exception as e:
            info.error = str(e)
            logger.warning(f"Failed to identify {address}: {e}")

        return info

    def scan_and_identify(self) -> List[InstrumentInfo]:
        """
        Scan for resources and identify each one.

        Returns:
            List of InstrumentInfo for all detected instruments.
        """
        addresses = self.scan()
        instruments = []

        for address in addresses:
            info = self.identify(address)
            instruments.append(info)

        return instruments

    def connect(self, address: str) -> bool:
        """
        Connect to an instrument.

        Args:
            address: VISA resource address.

        Returns:
            True if connected successfully.
        """
        if address in self._instruments:
            return True  # Already connected

        if not self._rm:
            if not self.initialize():
                return False

        try:
            inst = self._rm.open_resource(address)
            inst.timeout = self._settings.instruments.default_timeout_ms
            self._instruments[address] = inst
            logger.info(f"Connected to {address}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to {address}: {e}")
            return False

    def disconnect(self, address: str):
        """
        Disconnect from an instrument.

        Args:
            address: VISA resource address.
        """
        if address in self._instruments:
            try:
                self._instruments[address].close()
            except Exception as e:
                logger.warning(f"Error closing {address}: {e}")
            finally:
                del self._instruments[address]
                logger.info(f"Disconnected from {address}")

    def write(self, address: str, command: str) -> bool:
        """
        Write a command to an instrument.

        Args:
            address: VISA resource address.
            command: Command string to send.

        Returns:
            True if successful.
        """
        if address not in self._instruments:
            if not self.connect(address):
                return False

        try:
            self._instruments[address].write(command)
            logger.debug(f"[{address}] WRITE: {command}")
            return True
        except Exception as e:
            logger.error(f"Write error on {address}: {e}")
            return False

    def query(self, address: str, command: str) -> Tuple[bool, str]:
        """
        Send a query and read response from an instrument.

        Args:
            address: VISA resource address.
            command: Query command string.

        Returns:
            Tuple of (success, response).
        """
        if address not in self._instruments:
            if not self.connect(address):
                return False, ""

        try:
            response = self._instruments[address].query(command).strip()
            logger.debug(f"[{address}] QUERY: {command} -> {response}")
            return True, response
        except Exception as e:
            logger.error(f"Query error on {address}: {e}")
            return False, str(e)

    def read(self, address: str) -> Tuple[bool, str]:
        """
        Read from an instrument (without sending a command).

        Args:
            address: VISA resource address.

        Returns:
            Tuple of (success, response).
        """
        if address not in self._instruments:
            if not self.connect(address):
                return False, ""

        try:
            response = self._instruments[address].read().strip()
            logger.debug(f"[{address}] READ: {response}")
            return True, response
        except Exception as e:
            logger.error(f"Read error on {address}: {e}")
            return False, str(e)

    def set_output(
        self,
        address: str,
        value: float,
        unit: str,
        frequency: Optional[float] = None,
        command_template: Optional[str] = None,
    ) -> bool:
        """
        Set calibrator output (convenience method).

        Args:
            address: Calibrator VISA address.
            value: Output value.
            unit: Unit (V, A, Ohm, etc.).
            frequency: Optional frequency for AC outputs.
            command_template: Optional custom command template.

        Returns:
            True if successful.
        """
        if command_template:
            # Use custom template with placeholders
            command = command_template.format(value=value, unit=unit, frequency=frequency)
        else:
            # Default SCPI-like command
            if frequency:
                command = f"OUT {value} {unit}, {frequency} Hz"
            else:
                command = f"OUT {value} {unit}"

        return self.write(address, command)

    def operate(self, address: str, on: bool = True, command: Optional[str] = None) -> bool:
        """
        Enable or disable calibrator output.

        Args:
            address: Calibrator VISA address.
            on: True to enable, False to disable.
            command: Optional custom command.

        Returns:
            True if successful.
        """
        if command:
            cmd = command
        else:
            cmd = "OPER" if on else "STBY"

        return self.write(address, cmd)

    def measure(self, address: str, command: Optional[str] = None) -> Tuple[bool, float]:
        """
        Get measurement reading from DMM or DUT.

        Args:
            address: DMM/DUT VISA address.
            command: Optional custom query command.

        Returns:
            Tuple of (success, reading).
        """
        if command:
            cmd = command
        else:
            cmd = "MEAS?"

        success, response = self.query(address, cmd)

        if not success:
            return False, 0.0

        try:
            # Parse numeric value from response
            value = float(response.split()[0])
            return True, value
        except (ValueError, IndexError) as e:
            logger.error(f"Failed to parse measurement: {response} - {e}")
            return False, 0.0

    @property
    def is_initialized(self) -> bool:
        """Check if VISA manager is initialized."""
        return self._rm is not None

    @property
    def connected_instruments(self) -> List[str]:
        """Get list of connected instrument addresses."""
        return list(self._instruments.keys())


# Global VISA manager instance
_visa_manager: Optional[VISAManager] = None


def get_visa_manager() -> VISAManager:
    """Get the global VISA manager instance."""
    global _visa_manager
    if _visa_manager is None:
        _visa_manager = VISAManager()
    return _visa_manager
