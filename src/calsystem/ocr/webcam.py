"""
Webcam capture module for OCR reading.
"""

from typing import Optional, Tuple, List
from dataclasses import dataclass
import threading

from loguru import logger

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV not available - webcam capture disabled")

from calsystem.config.settings import get_settings


@dataclass
class CaptureRegion:
    """Region of interest for OCR capture."""

    x: int
    y: int
    width: int
    height: int

    def to_tuple(self) -> Tuple[int, int, int, int]:
        """Get as (x, y, w, h) tuple."""
        return (self.x, self.y, self.width, self.height)


class WebcamCapture:
    """Manages webcam capture for OCR reading."""

    def __init__(self, device_id: Optional[int] = None):
        """
        Initialize webcam capture.

        Args:
            device_id: Camera device ID. If None, uses settings default.
        """
        self._settings = get_settings()
        self._device_id = device_id or self._settings.ocr.webcam_device
        self._capture: Optional["cv2.VideoCapture"] = None
        self._region: Optional[CaptureRegion] = None
        self._is_running = False
        self._lock = threading.Lock()

    def open(self) -> bool:
        """
        Open the webcam device.

        Returns:
            True if successful.
        """
        if not CV2_AVAILABLE:
            logger.error("OpenCV not available")
            return False

        try:
            self._capture = cv2.VideoCapture(self._device_id)

            if not self._capture.isOpened():
                logger.error(f"Failed to open camera {self._device_id}")
                return False

            # Set resolution
            width, height = self._settings.ocr.capture_resolution
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

            logger.info(f"Webcam {self._device_id} opened ({width}x{height})")
            return True

        except Exception as e:
            logger.error(f"Error opening webcam: {e}")
            return False

    def close(self):
        """Close the webcam device."""
        if self._capture:
            self._capture.release()
            self._capture = None
            logger.info("Webcam closed")

    def is_open(self) -> bool:
        """Check if webcam is open."""
        return self._capture is not None and self._capture.isOpened()

    def capture_frame(self) -> Optional["np.ndarray"]:
        """
        Capture a single frame.

        Returns:
            Frame as numpy array, or None on failure.
        """
        if not self.is_open():
            return None

        with self._lock:
            ret, frame = self._capture.read()

            if not ret:
                logger.warning("Failed to capture frame")
                return None

            return frame

    def capture_region(self, region: Optional[CaptureRegion] = None) -> Optional["np.ndarray"]:
        """
        Capture a frame and extract region of interest.

        Args:
            region: Region to extract. Uses stored region if None.

        Returns:
            Cropped frame or None.
        """
        frame = self.capture_frame()
        if frame is None:
            return None

        roi = region or self._region
        if roi is None:
            return frame

        # Extract region
        x, y, w, h = roi.to_tuple()
        cropped = frame[y:y+h, x:x+w]
        return cropped

    def set_region(self, region: CaptureRegion):
        """Set the region of interest for captures."""
        self._region = region
        logger.debug(f"Set capture region: {region}")

    def get_region(self) -> Optional[CaptureRegion]:
        """Get the current region of interest."""
        return self._region

    def preview_frame(self, window_name: str = "Webcam Preview") -> bool:
        """
        Show preview window with current frame.

        Args:
            window_name: Window title.

        Returns:
            True if frame was displayed.
        """
        if not CV2_AVAILABLE:
            return False

        frame = self.capture_frame()
        if frame is None:
            return False

        # Draw region rectangle if set
        if self._region:
            x, y, w, h = self._region.to_tuple()
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

        cv2.imshow(window_name, frame)
        return True

    def select_region_interactive(self) -> Optional[CaptureRegion]:
        """
        Allow user to select region interactively.

        Returns:
            Selected region or None if cancelled.
        """
        if not CV2_AVAILABLE:
            return None

        frame = self.capture_frame()
        if frame is None:
            return None

        # Use OpenCV's selectROI
        roi = cv2.selectROI("Select Display Region", frame, fromCenter=False)
        cv2.destroyWindow("Select Display Region")

        if roi[2] > 0 and roi[3] > 0:  # Valid selection
            region = CaptureRegion(
                x=int(roi[0]),
                y=int(roi[1]),
                width=int(roi[2]),
                height=int(roi[3])
            )
            self._region = region
            logger.info(f"Selected region: {region}")
            return region

        return None

    def list_cameras(self) -> List[int]:
        """
        List available camera devices.

        Returns:
            List of available camera indices.
        """
        if not CV2_AVAILABLE:
            return []

        available = []
        for i in range(10):  # Check first 10 indices
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                available.append(i)
                cap.release()

        logger.info(f"Found {len(available)} cameras: {available}")
        return available

    @property
    def frame_size(self) -> Optional[Tuple[int, int]]:
        """Get current frame size (width, height)."""
        if not self.is_open():
            return None

        width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (width, height)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
