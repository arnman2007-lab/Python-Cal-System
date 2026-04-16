"""
CSP File Operations

Handles reading and writing .csp (CalSystem Procedure) files.
A .csp file is a ZIP archive containing:
- procedure.json: Full procedure definition
- metadata.json: Version and timestamp info
- images/: Wiring diagram images
"""

import json
import zipfile
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple
from loguru import logger

from calsystem.procedures.procedure_data import (
    ProcedureData,
    ProcedureMetadata,
)


class CSPFile:
    """Read/write .csp procedure files."""

    CSP_VERSION = "1.0"
    PROCEDURE_JSON = "procedure.json"
    METADATA_JSON = "metadata.json"
    IMAGES_DIR = "images"

    @classmethod
    def save(
        cls,
        procedure: ProcedureData,
        file_path: Path,
        created_by: Optional[str] = None,
        software_version: Optional[str] = None,
    ) -> bool:
        """
        Save procedure to .csp file.

        Args:
            procedure: Procedure data to save
            file_path: Path to save .csp file
            created_by: Author name for metadata
            software_version: Software version for metadata

        Returns:
            True if successful, False otherwise
        """
        try:
            file_path = Path(file_path)

            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if updating existing file
            existing_metadata = None
            if file_path.exists():
                try:
                    existing_metadata = cls.extract_metadata(file_path)
                except Exception:
                    pass

            # Create metadata
            now = datetime.now()
            metadata = ProcedureMetadata(
                csp_version=cls.CSP_VERSION,
                created_at=existing_metadata.created_at if existing_metadata else now,
                updated_at=now,
                created_by=created_by or (existing_metadata.created_by if existing_metadata else None),
                software_version=software_version,
            )

            # Write ZIP file
            with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Write procedure.json
                procedure_json = json.dumps(procedure.to_dict(), indent=2)
                zf.writestr(cls.PROCEDURE_JSON, procedure_json)

                # Write metadata.json
                metadata_json = json.dumps(metadata.to_dict(), indent=2)
                zf.writestr(cls.METADATA_JSON, metadata_json)

                # Write images
                for image_path, image_data in procedure.images.items():
                    # Normalize path separators
                    normalized_path = image_path.replace("\\", "/")
                    if not normalized_path.startswith(cls.IMAGES_DIR):
                        normalized_path = f"{cls.IMAGES_DIR}/{normalized_path}"
                    zf.writestr(normalized_path, image_data)

            logger.info(f"Saved procedure to {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save CSP file: {e}")
            return False

    @classmethod
    def load(cls, file_path: Path) -> Optional[ProcedureData]:
        """
        Load procedure from .csp file.

        Args:
            file_path: Path to .csp file

        Returns:
            ProcedureData if successful, None otherwise
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                logger.error(f"CSP file not found: {file_path}")
                return None

            with zipfile.ZipFile(file_path, 'r') as zf:
                # Read procedure.json
                if cls.PROCEDURE_JSON not in zf.namelist():
                    logger.error(f"Invalid CSP file: missing {cls.PROCEDURE_JSON}")
                    return None

                procedure_json = zf.read(cls.PROCEDURE_JSON).decode('utf-8')
                procedure_data = json.loads(procedure_json)
                procedure = ProcedureData.from_dict(procedure_data)

                # Load images
                for name in zf.namelist():
                    if name.startswith(cls.IMAGES_DIR + "/") and not name.endswith("/"):
                        image_data = zf.read(name)
                        procedure.images[name] = image_data

            logger.info(f"Loaded procedure from {file_path}: {procedure.name}")
            return procedure

        except Exception as e:
            logger.error(f"Failed to load CSP file: {e}")
            return None

    @classmethod
    def extract_metadata(cls, file_path: Path) -> Optional[ProcedureMetadata]:
        """
        Quick read of metadata without loading full procedure.

        Args:
            file_path: Path to .csp file

        Returns:
            ProcedureMetadata if successful, None otherwise
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                return None

            with zipfile.ZipFile(file_path, 'r') as zf:
                # Read metadata.json if present
                metadata = ProcedureMetadata()
                if cls.METADATA_JSON in zf.namelist():
                    metadata_json = zf.read(cls.METADATA_JSON).decode('utf-8')
                    metadata_data = json.loads(metadata_json)
                    metadata = ProcedureMetadata.from_dict(metadata_data)

                # Read basic info from procedure.json
                if cls.PROCEDURE_JSON in zf.namelist():
                    procedure_json = zf.read(cls.PROCEDURE_JSON).decode('utf-8')
                    procedure_data = json.loads(procedure_json)

                    metadata.name = procedure_data.get("name")
                    metadata.target_model = procedure_data.get("target_model")
                    metadata.version = procedure_data.get("version")

                    # Count sections and test points
                    sections = procedure_data.get("sections", [])
                    metadata.section_count = len(sections)
                    metadata.test_point_count = sum(
                        len(s.get("test_points", [])) for s in sections
                    )

            return metadata

        except Exception as e:
            logger.error(f"Failed to extract metadata: {e}")
            return None

    @classmethod
    def get_image(cls, file_path: Path, image_name: str) -> Optional[bytes]:
        """
        Extract single image from .csp without loading full procedure.

        Args:
            file_path: Path to .csp file
            image_name: Relative path to image within archive

        Returns:
            Image data as bytes if found, None otherwise
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                return None

            # Normalize path
            normalized_name = image_name.replace("\\", "/")
            if not normalized_name.startswith(cls.IMAGES_DIR):
                normalized_name = f"{cls.IMAGES_DIR}/{normalized_name}"

            with zipfile.ZipFile(file_path, 'r') as zf:
                if normalized_name in zf.namelist():
                    return zf.read(normalized_name)

                # Try without images/ prefix
                base_name = normalized_name.replace(f"{cls.IMAGES_DIR}/", "")
                for name in zf.namelist():
                    if name.endswith(base_name):
                        return zf.read(name)

            return None

        except Exception as e:
            logger.error(f"Failed to get image from CSP: {e}")
            return None

    @classmethod
    def list_images(cls, file_path: Path) -> list:
        """
        List all images in a .csp file.

        Args:
            file_path: Path to .csp file

        Returns:
            List of image paths within the archive
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                return []

            with zipfile.ZipFile(file_path, 'r') as zf:
                return [
                    name for name in zf.namelist()
                    if name.startswith(cls.IMAGES_DIR + "/") and not name.endswith("/")
                ]

        except Exception as e:
            logger.error(f"Failed to list images: {e}")
            return []

    @classmethod
    def compute_hash(cls, file_path: Path) -> Optional[str]:
        """
        Compute SHA-256 hash of .csp file for change detection.

        Args:
            file_path: Path to .csp file

        Returns:
            Hash string if successful, None otherwise
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                return None

            sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)

            return sha256.hexdigest()

        except Exception as e:
            logger.error(f"Failed to compute hash: {e}")
            return None

    @classmethod
    def validate(cls, file_path: Path) -> Tuple[bool, str]:
        """
        Validate a .csp file structure.

        Args:
            file_path: Path to .csp file

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                return False, f"File not found: {file_path}"

            if not file_path.suffix.lower() == ".csp":
                return False, "File must have .csp extension"

            with zipfile.ZipFile(file_path, 'r') as zf:
                # Check for required files
                if cls.PROCEDURE_JSON not in zf.namelist():
                    return False, f"Missing required file: {cls.PROCEDURE_JSON}"

                # Validate procedure.json structure
                procedure_json = zf.read(cls.PROCEDURE_JSON).decode('utf-8')
                procedure_data = json.loads(procedure_json)

                if "name" not in procedure_data:
                    return False, "procedure.json missing 'name' field"

                if "sections" not in procedure_data:
                    return False, "procedure.json missing 'sections' field"

                # Validate sections have test_points
                for i, section in enumerate(procedure_data.get("sections", [])):
                    if "name" not in section:
                        return False, f"Section {i} missing 'name' field"
                    if "test_points" not in section:
                        return False, f"Section '{section.get('name', i)}' missing 'test_points' field"

            return True, "Valid CSP file"

        except zipfile.BadZipFile:
            return False, "Invalid ZIP archive"
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"


def generate_csp_filename(
    target_model: str,
    procedure_name: Optional[str] = None,
    version: str = "1",
) -> str:
    """
    Generate a standardized .csp filename.

    Args:
        target_model: Target device model (e.g., "8845A")
        procedure_name: Optional procedure name suffix
        version: Version number

    Returns:
        Filename like "Fluke_8845A_Calibration_v1.csp"
    """
    # Clean model name
    model = target_model.replace(" ", "_").replace("/", "-")

    if procedure_name:
        name = procedure_name.replace(" ", "_").replace("/", "-")
        return f"{model}_{name}_v{version}.csp"
    else:
        return f"{model}_v{version}.csp"
