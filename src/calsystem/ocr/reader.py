"""
OCR reader module with support for standard text and seven-segment displays.
"""

from typing import Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum
import re

from loguru import logger

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract not available - standard OCR disabled")

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    logger.warning("EasyOCR not available - advanced OCR disabled")

from calsystem.config.settings import get_settings


class OCRMode(Enum):
    """OCR processing modes."""

    STANDARD = "standard"
    SEVEN_SEGMENT = "seven_segment"


@dataclass
class OCRResult:
    """Result from OCR processing."""

    text: str
    confidence: float
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    raw_text: str = ""

    @property
    def has_value(self) -> bool:
        """Check if a numeric value was extracted."""
        return self.numeric_value is not None


class OCRReader:
    """Standard text OCR reader using Tesseract."""

    def __init__(self):
        self._settings = get_settings()

        # Configure Tesseract path if specified
        if self._settings.ocr.tesseract_path and TESSERACT_AVAILABLE:
            pytesseract.pytesseract.tesseract_cmd = self._settings.ocr.tesseract_path

    def preprocess_image(self, image: "np.ndarray") -> "np.ndarray":
        """
        Preprocess image for better OCR accuracy.

        Args:
            image: Input image (BGR or grayscale).

        Returns:
            Preprocessed grayscale image.
        """
        if not CV2_AVAILABLE:
            return image

        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        # Denoise
        denoised = cv2.fastNlMeansDenoising(thresh, None, 10, 7, 21)

        return denoised

    def read(self, image: "np.ndarray", preprocess: bool = True) -> OCRResult:
        """
        Read text from image using Tesseract OCR.

        Args:
            image: Input image.
            preprocess: Whether to preprocess the image.

        Returns:
            OCRResult with extracted text.
        """
        if not TESSERACT_AVAILABLE:
            return OCRResult(text="", confidence=0.0, raw_text="OCR not available")

        try:
            if preprocess:
                processed = self.preprocess_image(image)
            else:
                processed = image

            # Get text with confidence
            data = pytesseract.image_to_data(
                processed, output_type=pytesseract.Output.DICT
            )

            # Combine text and calculate average confidence
            texts = []
            confidences = []

            for i, conf in enumerate(data["conf"]):
                if int(conf) > 0:  # Valid detection
                    texts.append(data["text"][i])
                    confidences.append(int(conf))

            raw_text = " ".join(texts).strip()
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            # Extract numeric value
            numeric_value, unit = self._extract_numeric(raw_text)

            return OCRResult(
                text=raw_text,
                confidence=avg_confidence / 100.0,  # Normalize to 0-1
                numeric_value=numeric_value,
                unit=unit,
                raw_text=raw_text,
            )

        except Exception as e:
            logger.error(f"OCR error: {e}")
            return OCRResult(text="", confidence=0.0, raw_text=str(e))

    def _extract_numeric(self, text: str) -> Tuple[Optional[float], Optional[str]]:
        """
        Extract numeric value and unit from text.

        Args:
            text: OCR text output.

        Returns:
            Tuple of (numeric_value, unit).
        """
        # Common patterns for measurement readings
        patterns = [
            r"([+-]?\d+\.?\d*)\s*(V|mV|A|mA|Ohm|kOhm|MOhm|Hz|kHz|MHz)?",
            r"([+-]?\d+\.?\d*[Ee][+-]?\d+)\s*(V|mV|A|mA|Ohm)?",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1))
                    unit = match.group(2) if len(match.groups()) > 1 else None
                    return value, unit
                except ValueError:
                    continue

        return None, None


class SevenSegmentReader:
    """
    Seven-segment display OCR reader.

    Uses specialized image processing for LCD/LED digital displays.
    """

    # Seven-segment digit patterns (segments: a,b,c,d,e,f,g)
    DIGIT_PATTERNS = {
        (1, 1, 1, 1, 1, 1, 0): "0",
        (0, 1, 1, 0, 0, 0, 0): "1",
        (1, 1, 0, 1, 1, 0, 1): "2",
        (1, 1, 1, 1, 0, 0, 1): "3",
        (0, 1, 1, 0, 0, 1, 1): "4",
        (1, 0, 1, 1, 0, 1, 1): "5",
        (1, 0, 1, 1, 1, 1, 1): "6",
        (1, 1, 1, 0, 0, 0, 0): "7",
        (1, 1, 1, 1, 1, 1, 1): "8",
        (1, 1, 1, 1, 0, 1, 1): "9",
    }

    def __init__(self):
        self._settings = get_settings()
        self._easyocr_reader = None

        # Initialize EasyOCR if available (good for seven-segment)
        if EASYOCR_AVAILABLE:
            try:
                self._easyocr_reader = easyocr.Reader(["en"], gpu=False)
                logger.info("EasyOCR initialized for seven-segment reading")
            except Exception as e:
                logger.warning(f"Failed to initialize EasyOCR: {e}")

    def preprocess_image(self, image: "np.ndarray") -> "np.ndarray":
        """
        Preprocess image for seven-segment display recognition.

        Args:
            image: Input image (BGR).

        Returns:
            Preprocessed binary image.
        """
        if not CV2_AVAILABLE:
            return image

        # Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Increase contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Threshold - may need inversion for dark displays with light digits
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Check if we need to invert (more white than black suggests inverted)
        white_ratio = np.sum(binary == 255) / binary.size
        if white_ratio > 0.5:
            binary = cv2.bitwise_not(binary)

        # Morphological operations to clean up segments
        kernel = np.ones((2, 2), np.uint8)
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        return cleaned

    def read(self, image: "np.ndarray", preprocess: bool = True) -> OCRResult:
        """
        Read seven-segment display from image.

        Args:
            image: Input image.
            preprocess: Whether to preprocess the image.

        Returns:
            OCRResult with extracted value.
        """
        if preprocess:
            processed = self.preprocess_image(image)
        else:
            processed = image

        # Try EasyOCR first (generally better for seven-segment)
        if self._easyocr_reader:
            result = self._read_with_easyocr(processed)
            if result.has_value:
                return result

        # Fallback to custom seven-segment detection
        result = self._read_segments(processed)
        return result

    def _read_with_easyocr(self, image: "np.ndarray") -> OCRResult:
        """Use EasyOCR for seven-segment reading."""
        try:
            results = self._easyocr_reader.readtext(image)

            if not results:
                return OCRResult(text="", confidence=0.0, raw_text="No text detected")

            # Combine results
            texts = []
            confidences = []

            for (bbox, text, conf) in results:
                # Filter for numeric-like text
                if re.search(r"[\d.+-]", text):
                    texts.append(text)
                    confidences.append(conf)

            if not texts:
                return OCRResult(text="", confidence=0.0, raw_text="No numbers detected")

            raw_text = " ".join(texts)
            avg_conf = sum(confidences) / len(confidences)

            # Extract numeric value
            numeric_value, unit = self._extract_numeric(raw_text)

            return OCRResult(
                text=raw_text,
                confidence=avg_conf,
                numeric_value=numeric_value,
                unit=unit,
                raw_text=raw_text,
            )

        except Exception as e:
            logger.error(f"EasyOCR error: {e}")
            return OCRResult(text="", confidence=0.0, raw_text=str(e))

    def _read_segments(self, binary_image: "np.ndarray") -> OCRResult:
        """
        Custom seven-segment detection using contour analysis.

        This is a fallback method that analyzes segment shapes.
        """
        if not CV2_AVAILABLE:
            return OCRResult(text="", confidence=0.0, raw_text="OpenCV not available")

        try:
            # Find contours
            contours, _ = cv2.findContours(
                binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            if not contours:
                return OCRResult(text="", confidence=0.0, raw_text="No contours found")

            # Sort contours left to right (for digit order)
            contours = sorted(contours, key=lambda c: cv2.boundingRect(c)[0])

            # Simple heuristic: count major contours as digits
            # This is a simplified approach - full implementation would
            # analyze segment patterns within each digit bounding box

            digit_count = 0
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 100:  # Minimum area threshold
                    digit_count += 1

            # For now, return placeholder
            # Full implementation would decode actual digit patterns
            return OCRResult(
                text=f"[{digit_count} digits detected]",
                confidence=0.5,
                numeric_value=None,
                raw_text="Segment analysis mode",
            )

        except Exception as e:
            logger.error(f"Segment analysis error: {e}")
            return OCRResult(text="", confidence=0.0, raw_text=str(e))

    def _extract_numeric(self, text: str) -> Tuple[Optional[float], Optional[str]]:
        """Extract numeric value from text."""
        # Clean up common OCR errors in seven-segment displays
        text = text.replace("O", "0").replace("o", "0")
        text = text.replace("l", "1").replace("I", "1")
        text = text.replace("S", "5").replace("s", "5")
        text = text.replace("B", "8")

        # Look for numeric patterns
        patterns = [
            r"([+-]?\d+\.?\d*)",
            r"([+-]?\d+\.?\d*)\s*([A-Za-z]+)?",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    value = float(match.group(1))
                    unit = match.group(2) if len(match.groups()) > 1 else None
                    return value, unit
                except (ValueError, IndexError):
                    continue

        return None, None


def create_reader(mode: OCRMode = OCRMode.STANDARD):
    """
    Factory function to create appropriate OCR reader.

    Args:
        mode: OCR mode to use.

    Returns:
        OCRReader or SevenSegmentReader instance.
    """
    if mode == OCRMode.SEVEN_SEGMENT:
        return SevenSegmentReader()
    return OCRReader()
