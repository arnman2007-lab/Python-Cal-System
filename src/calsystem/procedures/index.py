"""
Procedure Index Management

Manages the index of .csp procedure files in the database.
The database procedures table acts as a lightweight index pointing to
the actual .csp files on disk.
"""

from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from loguru import logger

from calsystem.database.connection import get_db
from calsystem.database.models import Procedure
from calsystem.procedures.csp_file import CSPFile
from calsystem.config.settings import get_settings


class ProcedureIndex:
    """Manage procedure index in database."""

    def __init__(self, procedures_dir: Optional[Path] = None):
        """
        Initialize procedure index.

        Args:
            procedures_dir: Directory containing .csp files.
                            Defaults to settings.procedures_dir
        """
        if procedures_dir:
            self.procedures_dir = Path(procedures_dir)
        else:
            settings = get_settings()
            self.procedures_dir = settings.procedures_dir

        self.procedures_dir.mkdir(parents=True, exist_ok=True)

    def scan_procedures_folder(self) -> List[Dict[str, Any]]:
        """
        Scan procedures folder and return list of .csp files with metadata.

        Returns:
            List of dicts with file info and metadata
        """
        results = []

        if not self.procedures_dir.exists():
            return results

        for csp_file in self.procedures_dir.glob("*.csp"):
            try:
                metadata = CSPFile.extract_metadata(csp_file)
                if metadata:
                    file_hash = CSPFile.compute_hash(csp_file)
                    results.append({
                        "file_path": str(csp_file),
                        "file_name": csp_file.name,
                        "name": metadata.name,
                        "target_model": metadata.target_model,
                        "version": metadata.version,
                        "section_count": metadata.section_count,
                        "test_point_count": metadata.test_point_count,
                        "csp_version": metadata.csp_version,
                        "created_at": metadata.created_at,
                        "updated_at": metadata.updated_at,
                        "created_by": metadata.created_by,
                        "file_hash": file_hash,
                    })
            except Exception as e:
                logger.warning(f"Failed to read metadata from {csp_file}: {e}")

        return results

    def sync_index(self) -> Tuple[int, int, int]:
        """
        Synchronize database index with .csp files on disk.

        - Adds new procedures found on disk
        - Updates procedures whose file hash changed
        - Marks procedures as inactive if file is missing

        Returns:
            Tuple of (added, updated, removed) counts
        """
        added = 0
        updated = 0
        removed = 0

        db = get_db()
        if not db.is_connected:
            logger.error("Database not connected")
            return (0, 0, 0)

        # Scan disk for .csp files
        disk_files = self.scan_procedures_folder()
        disk_paths = {f["file_path"] for f in disk_files}

        with db.session() as session:
            # Get existing procedures with file paths
            existing = session.query(Procedure).filter(
                Procedure.file_path.isnot(None)
            ).all()

            existing_by_path = {p.file_path: p for p in existing}
            existing_paths = set(existing_by_path.keys())

            # Get procedures without file paths (for matching by name/model)
            unlinked = session.query(Procedure).filter(
                Procedure.file_path.is_(None)
            ).all()
            unlinked_by_name_model = {
                (p.name, p.target_model): p for p in unlinked
            }

            # Find new files (on disk but not in DB)
            new_paths = disk_paths - existing_paths

            # Find removed files (in DB but not on disk)
            missing_paths = existing_paths - disk_paths

            # Process new files
            for file_info in disk_files:
                if file_info["file_path"] in new_paths:
                    # First, check if there's an unlinked procedure with same name/model
                    key = (file_info.get("name"), file_info.get("target_model"))
                    if key in unlinked_by_name_model:
                        # Link existing procedure to this file
                        proc = unlinked_by_name_model[key]
                        proc.file_path = file_info["file_path"]
                        proc.file_hash = file_info.get("file_hash")
                        proc.section_count = file_info.get("section_count", 0)
                        proc.test_point_count = file_info.get("test_point_count", 0)
                        proc.is_active = True
                        updated += 1
                        logger.info(f"Linked existing procedure to file: {proc.name}")
                        # Remove from unlinked dict to prevent double-linking
                        del unlinked_by_name_model[key]
                    else:
                        # Add new procedure
                        proc = Procedure(
                            name=file_info["name"] or Path(file_info["file_path"]).stem,
                            target_model=file_info.get("target_model"),
                            version=file_info.get("version", "1.0"),
                            file_path=file_info["file_path"],
                            section_count=file_info.get("section_count", 0),
                            test_point_count=file_info.get("test_point_count", 0),
                            file_hash=file_info.get("file_hash"),
                            created_by=file_info.get("created_by"),
                            is_active=True,
                        )
                        session.add(proc)
                        added += 1
                        logger.info(f"Added procedure: {proc.name}")

                elif file_info["file_path"] in existing_paths:
                    # Check if file changed
                    proc = existing_by_path[file_info["file_path"]]
                    if proc.file_hash != file_info.get("file_hash"):
                        # Update procedure metadata
                        proc.name = file_info["name"] or proc.name
                        proc.target_model = file_info.get("target_model") or proc.target_model
                        proc.version = file_info.get("version") or proc.version
                        proc.section_count = file_info.get("section_count", 0)
                        proc.test_point_count = file_info.get("test_point_count", 0)
                        proc.file_hash = file_info.get("file_hash")
                        proc.is_active = True
                        updated += 1
                        logger.info(f"Updated procedure: {proc.name}")

            # Mark missing files as inactive
            for path in missing_paths:
                proc = existing_by_path[path]
                if proc.is_active:
                    proc.is_active = False
                    removed += 1
                    logger.info(f"Marked as inactive (file missing): {proc.name}")

            session.commit()

        logger.info(f"Index sync complete: {added} added, {updated} updated, {removed} inactive")
        return (added, updated, removed)

    def get_procedures_for_model(self, model: str) -> List[Dict[str, Any]]:
        """
        Get procedures matching a DUT model.

        Args:
            model: Model name to match

        Returns:
            List of procedure info dicts
        """
        results = []
        db = get_db()
        if not db.is_connected:
            return results

        with db.session() as session:
            procedures = session.query(Procedure).filter(
                Procedure.target_model == model,
                Procedure.is_active == True,
                Procedure.file_path.isnot(None),
            ).all()

            for proc in procedures:
                results.append({
                    "id": proc.id,
                    "name": proc.name,
                    "target_model": proc.target_model,
                    "version": proc.version,
                    "file_path": proc.file_path,
                    "section_count": proc.section_count,
                    "test_point_count": proc.test_point_count,
                })

        return results

    def get_all_procedures(self) -> List[Dict[str, Any]]:
        """
        Get all active procedures.

        Returns:
            List of procedure info dicts
        """
        results = []
        db = get_db()
        if not db.is_connected:
            return results

        with db.session() as session:
            procedures = session.query(Procedure).filter(
                Procedure.is_active == True,
            ).order_by(Procedure.name).all()

            for proc in procedures:
                results.append({
                    "id": proc.id,
                    "name": proc.name,
                    "target_model": proc.target_model,
                    "version": proc.version,
                    "file_path": proc.file_path,
                    "section_count": proc.section_count,
                    "test_point_count": proc.test_point_count,
                    "has_csp": proc.file_path is not None,
                })

        return results

    def update_procedure_file_path(
        self,
        procedure_id: int,
        file_path: Path,
    ) -> bool:
        """
        Update procedure's file path and sync metadata from .csp.

        Args:
            procedure_id: Database procedure ID
            file_path: Path to .csp file

        Returns:
            True if successful
        """
        db = get_db()
        if not db.is_connected:
            return False

        try:
            metadata = CSPFile.extract_metadata(file_path)
            file_hash = CSPFile.compute_hash(file_path)

            with db.session() as session:
                proc = session.query(Procedure).filter(
                    Procedure.id == procedure_id
                ).first()

                if not proc:
                    logger.error(f"Procedure not found: {procedure_id}")
                    return False

                proc.file_path = str(file_path)
                proc.file_hash = file_hash
                if metadata:
                    proc.section_count = metadata.section_count
                    proc.test_point_count = metadata.test_point_count

                session.commit()
                logger.info(f"Updated file path for procedure {proc.name}")
                return True

        except Exception as e:
            logger.error(f"Failed to update procedure file path: {e}")
            return False


def sync_procedure_index() -> Tuple[int, int, int]:
    """
    Convenience function to sync procedure index.

    Returns:
        Tuple of (added, updated, removed) counts
    """
    index = ProcedureIndex()
    return index.sync_index()


def get_procedure_by_path(file_path: str) -> Optional[int]:
    """
    Get procedure ID by file path.

    Args:
        file_path: Path to .csp file

    Returns:
        Procedure ID if found, None otherwise
    """
    db = get_db()
    if not db.is_connected:
        return None

    with db.session() as session:
        proc = session.query(Procedure).filter(
            Procedure.file_path == file_path
        ).first()

        return proc.id if proc else None
