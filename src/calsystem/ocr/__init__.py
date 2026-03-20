"""OCR module for Calsystem - webcam and image recognition."""

from calsystem.ocr.webcam import WebcamCapture
from calsystem.ocr.reader import OCRReader, SevenSegmentReader

__all__ = ["WebcamCapture", "OCRReader", "SevenSegmentReader"]
