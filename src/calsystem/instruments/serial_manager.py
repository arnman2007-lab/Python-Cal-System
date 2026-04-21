"""
Serial (COM port) communication manager for DUT remote control.

Provides a singleton interface for serial communication with DUTs
that use COM ports (RS-232, USB-serial adapters, etc.).
"""

import time
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field

from loguru import logger

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False
    logger.warning("PySerial not available - serial communication disabled")


@dataclass
class SerialPortInfo:
    """Information about a serial port."""

    port: str
    description: str = ""
    hwid: str = ""
    manufacturer: str = ""
    vid: Optional[int] = None
    pid: Optional[int] = None
    serial_number: str = ""


@dataclass
class SerialConfig:
    """Serial port configuration."""

    baud_rate: int = 9600
    data_bits: int = 8
    parity: str = "N"  # N (None), E (Even), O (Odd), M (Mark), S (Space)
    stop_bits: float = 1  # 1, 1.5, or 2
    timeout: float = 1.0
    write_timeout: float = 1.0
    xonxoff: bool = False
    rtscts: bool = False
    dsrdtr: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            "baud_rate": self.baud_rate,
            "data_bits": self.data_bits,
            "parity": self.parity,
            "stop_bits": self.stop_bits,
            "timeout": self.timeout,
            "write_timeout": self.write_timeout,
            "xonxoff": self.xonxoff,
            "rtscts": self.rtscts,
            "dsrdtr": self.dsrdtr,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SerialConfig":
        """Create from dictionary."""
        return cls(
            baud_rate=data.get("baud_rate", 9600),
            data_bits=data.get("data_bits", 8),
            parity=data.get("parity", "N"),
            stop_bits=data.get("stop_bits", 1),
            timeout=data.get("timeout", 1.0),
            write_timeout=data.get("write_timeout", 1.0),
            xonxoff=data.get("xonxoff", False),
            rtscts=data.get("rtscts", False),
            dsrdtr=data.get("dsrdtr", False),
        )


# Parity mapping
PARITY_MAP = {
    "N": serial.PARITY_NONE if PYSERIAL_AVAILABLE else None,
    "E": serial.PARITY_EVEN if PYSERIAL_AVAILABLE else None,
    "O": serial.PARITY_ODD if PYSERIAL_AVAILABLE else None,
    "M": serial.PARITY_MARK if PYSERIAL_AVAILABLE else None,
    "S": serial.PARITY_SPACE if PYSERIAL_AVAILABLE else None,
}

# Stop bits mapping
STOPBITS_MAP = {
    1: serial.STOPBITS_ONE if PYSERIAL_AVAILABLE else None,
    1.5: serial.STOPBITS_ONE_POINT_FIVE if PYSERIAL_AVAILABLE else None,
    2: serial.STOPBITS_TWO if PYSERIAL_AVAILABLE else None,
}


class SerialManager:
    """
    Manages serial port communication for DUTs.

    Provides a singleton interface for:
    - Scanning available COM ports
    - Connecting/disconnecting from ports
    - Sending commands and receiving responses
    - Auto-detection of port changes
    """

    _instance: Optional["SerialManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._connections: Dict[str, "serial.Serial"] = {}  # port -> Serial connection
        self._configs: Dict[str, SerialConfig] = {}  # port -> config
        self._last_scan: List[SerialPortInfo] = []

    def is_available(self) -> bool:
        """Check if PySerial is available."""
        return PYSERIAL_AVAILABLE

    def scan(self) -> List[SerialPortInfo]:
        """
        Scan for available COM ports.

        Returns:
            List of SerialPortInfo objects for each detected port.
        """
        if not PYSERIAL_AVAILABLE:
            return []

        try:
            ports = []
            for port_info in serial.tools.list_ports.comports():
                ports.append(SerialPortInfo(
                    port=port_info.device,
                    description=port_info.description or "",
                    hwid=port_info.hwid or "",
                    manufacturer=port_info.manufacturer or "",
                    vid=port_info.vid,
                    pid=port_info.pid,
                    serial_number=port_info.serial_number or "",
                ))

            # Sort by port name
            ports.sort(key=lambda p: p.port)
            self._last_scan = ports

            logger.debug(f"Found {len(ports)} serial ports")
            return ports

        except Exception as e:
            logger.error(f"Failed to scan serial ports: {e}")
            return []

    def get_port_changes(self) -> Tuple[List[SerialPortInfo], List[SerialPortInfo]]:
        """
        Check for port changes since last scan.

        Returns:
            Tuple of (added_ports, removed_ports)
        """
        # Store old scan before calling scan() which updates _last_scan
        old_scan = self._last_scan.copy()
        old_ports = {p.port for p in old_scan}

        new_scan = self.scan()  # This updates _last_scan
        new_ports = {p.port for p in new_scan}

        added = [p for p in new_scan if p.port not in old_ports]
        removed = [p for p in old_scan if p.port not in new_ports]

        return added, removed

    def connect(self, port: str, config: Optional[SerialConfig] = None) -> bool:
        """
        Connect to a serial port.

        Args:
            port: Port name (e.g., "COM3" or "/dev/ttyUSB0")
            config: Serial configuration. If None, uses defaults.

        Returns:
            True if successful, False otherwise.
        """
        if not PYSERIAL_AVAILABLE:
            logger.error("PySerial not available")
            return False

        if port in self._connections:
            logger.warning(f"Already connected to {port}")
            return True

        if config is None:
            config = SerialConfig()

        try:
            ser = serial.Serial(
                port=port,
                baudrate=config.baud_rate,
                bytesize=config.data_bits,
                parity=PARITY_MAP.get(config.parity, serial.PARITY_NONE),
                stopbits=STOPBITS_MAP.get(config.stop_bits, serial.STOPBITS_ONE),
                timeout=config.timeout,
                write_timeout=config.write_timeout,
                xonxoff=config.xonxoff,
                rtscts=config.rtscts,
                dsrdtr=config.dsrdtr,
            )

            self._connections[port] = ser
            self._configs[port] = config

            logger.info(f"Connected to {port} at {config.baud_rate} baud")
            return True

        except serial.SerialException as e:
            logger.error(f"Failed to connect to {port}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to {port}: {e}")
            return False

    def disconnect(self, port: str) -> bool:
        """
        Disconnect from a serial port.

        Args:
            port: Port name to disconnect.

        Returns:
            True if successful, False otherwise.
        """
        if port not in self._connections:
            return True

        try:
            self._connections[port].close()
            del self._connections[port]
            if port in self._configs:
                del self._configs[port]

            logger.info(f"Disconnected from {port}")
            return True

        except Exception as e:
            logger.error(f"Error disconnecting from {port}: {e}")
            return False

    def disconnect_all(self):
        """Disconnect from all serial ports."""
        for port in list(self._connections.keys()):
            self.disconnect(port)

    def is_connected(self, port: str) -> bool:
        """Check if connected to a port."""
        if port not in self._connections:
            return False
        try:
            return self._connections[port].is_open
        except Exception:
            return False

    def write(self, port: str, command: str, delay_after: float = 0, terminator: str = "\r\n") -> bool:
        """
        Write a command to a serial port.

        Args:
            port: Port name.
            command: Command string to send.
            delay_after: Delay in seconds after sending.
            terminator: Line terminator to append.

        Returns:
            True if successful, False otherwise.
        """
        if port not in self._connections:
            logger.error(f"Not connected to {port}")
            return False

        try:
            ser = self._connections[port]
            full_command = command + terminator
            ser.write(full_command.encode("utf-8"))
            ser.flush()

            if delay_after > 0:
                time.sleep(delay_after)

            logger.debug(f"Sent to {port}: {command}")
            return True

        except Exception as e:
            logger.error(f"Failed to write to {port}: {e}")
            return False

    def read(self, port: str, timeout: Optional[float] = None) -> Tuple[bool, str]:
        """
        Read response from a serial port.

        Args:
            port: Port name.
            timeout: Read timeout (uses connection default if None).

        Returns:
            Tuple of (success, response_string).
        """
        if port not in self._connections:
            logger.error(f"Not connected to {port}")
            return False, ""

        try:
            ser = self._connections[port]

            # Set temporary timeout if specified
            original_timeout = ser.timeout
            if timeout is not None:
                ser.timeout = timeout

            # Read until no more data or timeout
            response = ser.read_until().decode("utf-8").strip()

            # Restore original timeout
            if timeout is not None:
                ser.timeout = original_timeout

            logger.debug(f"Received from {port}: {response}")
            return True, response

        except Exception as e:
            logger.error(f"Failed to read from {port}: {e}")
            return False, ""

    def read_all(self, port: str) -> Tuple[bool, str]:
        """
        Read all available data from a serial port.

        Args:
            port: Port name.

        Returns:
            Tuple of (success, response_string).
        """
        if port not in self._connections:
            logger.error(f"Not connected to {port}")
            return False, ""

        try:
            ser = self._connections[port]
            # Small delay to ensure all data is received
            time.sleep(0.05)
            response = ser.read(ser.in_waiting or 1).decode("utf-8").strip()
            logger.debug(f"Read all from {port}: {response}")
            return True, response

        except Exception as e:
            logger.error(f"Failed to read from {port}: {e}")
            return False, ""

    def query(
        self,
        port: str,
        command: str,
        delay_before: float = 0,
        delay_after: float = 0.1,
        terminator: str = "\r\n",
        timeout: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """
        Send a command and read the response.

        Args:
            port: Port name.
            command: Command string to send.
            delay_before: Delay before sending command.
            delay_after: Delay after sending, before reading.
            terminator: Line terminator to append to command.
            timeout: Read timeout.

        Returns:
            Tuple of (success, response_string).
        """
        if port not in self._connections:
            logger.error(f"Not connected to {port}")
            return False, ""

        try:
            ser = self._connections[port]

            # Delay before sending
            if delay_before > 0:
                time.sleep(delay_before)

            # Clear input buffer
            ser.reset_input_buffer()

            # Send command
            full_command = command + terminator
            ser.write(full_command.encode("utf-8"))
            ser.flush()

            # Delay after sending
            if delay_after > 0:
                time.sleep(delay_after)

            # Read response
            original_timeout = ser.timeout
            if timeout is not None:
                ser.timeout = timeout

            response = ser.read_until().decode("utf-8").strip()

            if timeout is not None:
                ser.timeout = original_timeout

            logger.debug(f"Query {port}: {command} -> {response}")
            return True, response

        except Exception as e:
            logger.error(f"Query failed on {port}: {e}")
            return False, ""

    def flush_input(self, port: str) -> bool:
        """Clear the input buffer for a port."""
        if port not in self._connections:
            return False

        try:
            self._connections[port].reset_input_buffer()
            return True
        except Exception:
            return False

    def flush_output(self, port: str) -> bool:
        """Clear the output buffer for a port."""
        if port not in self._connections:
            return False

        try:
            self._connections[port].reset_output_buffer()
            return True
        except Exception:
            return False

    def get_config(self, port: str) -> Optional[SerialConfig]:
        """Get the configuration for a connected port."""
        return self._configs.get(port)


# Global instance
_serial_manager: Optional[SerialManager] = None


def get_serial_manager() -> SerialManager:
    """Get the global serial manager instance."""
    global _serial_manager
    if _serial_manager is None:
        _serial_manager = SerialManager()
    return _serial_manager
