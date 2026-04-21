"""
Database connection management.
"""

from typing import Optional, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from loguru import logger

from calsystem.config.settings import get_settings
from calsystem.database.models import Base, SectionType, STANDARD_SECTION_TYPES


class DatabaseManager:
    """Manages database connections and sessions."""

    _instance: Optional["DatabaseManager"] = None
    _engine = None
    _session_factory = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._engine is None:
            self._initialized = False
            self._is_sqlite = False

    def connect(self, connection_string: Optional[str] = None) -> bool:
        """
        Establish database connection.

        Args:
            connection_string: Optional custom connection string.
                             If not provided, uses settings.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            settings = get_settings()
            if connection_string is None:
                connection_string = settings.database.get_connection_string(settings.config_dir)

            # Detect database type from connection string
            is_sqlite = connection_string.startswith("sqlite")
            self._is_sqlite = is_sqlite

            # Configure engine based on database type
            if is_sqlite:
                # SQLite: simpler config, no pooling needed
                self._engine = create_engine(
                    connection_string,
                    echo=False,
                    connect_args={"check_same_thread": False},
                )
            else:
                # MySQL: connection pooling for server database
                self._engine = create_engine(
                    connection_string,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                    echo=False,
                )

            # Test connection
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            self._session_factory = sessionmaker(
                bind=self._engine,
                autocommit=False,
                autoflush=False,
            )

            self._initialized = True
            db_type = "SQLite" if is_sqlite else "MySQL"
            logger.info(f"Database connection established ({db_type})")
            return True

        except SQLAlchemyError as e:
            logger.error(f"Database connection failed: {e}")
            self._initialized = False
            return False

    def disconnect(self):
        """Close database connection."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._initialized = False
            logger.info("Database connection closed")

    def create_tables(self):
        """Create all database tables."""
        if not self._initialized:
            raise RuntimeError("Database not connected")

        Base.metadata.create_all(self._engine)
        logger.info("Database tables created")

        # Run migrations for new columns
        self._run_migrations()

        # Seed default section types
        self._seed_section_types()

    def _seed_section_types(self):
        """Seed default section types if table is empty."""
        if not self._initialized or not self._session_factory:
            return

        try:
            session = self._session_factory()
            try:
                # Check if any built-in types exist
                existing = session.query(SectionType).filter(
                    SectionType.is_builtin == True
                ).count()

                if existing == 0:
                    # Add standard section types
                    for type_name in STANDARD_SECTION_TYPES:
                        section_type = SectionType(
                            name=type_name,
                            is_builtin=True
                        )
                        session.add(section_type)
                    session.commit()
                    logger.info(f"Seeded {len(STANDARD_SECTION_TYPES)} default section types")
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Failed to seed section types: {e}")

    def _run_migrations(self):
        """Run any necessary database migrations."""
        if not self._initialized or not self._engine:
            return

        try:
            with self._engine.connect() as conn:
                if getattr(self, '_is_sqlite', False):
                    # SQLite migrations

                    # Ensure dut_command_banks table exists
                    result = conn.execute(text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='dut_command_banks'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("""
                            CREATE TABLE dut_command_banks (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                make VARCHAR(100) NOT NULL,
                                model VARCHAR(100) NOT NULL,
                                description TEXT,
                                communication_type VARCHAR(20) DEFAULT 'serial',
                                serial_config JSON,
                                commands JSON,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE(make, model)
                            )
                        """))
                        conn.commit()
                        logger.info("Created dut_command_banks table")

                    # Check is_active column in workstation_standards
                    result = conn.execute(text("PRAGMA table_info(workstation_standards)"))
                    columns = [row[1] for row in result.fetchall()]
                    if 'is_active' not in columns:
                        conn.execute(text("ALTER TABLE workstation_standards ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                        conn.commit()
                        logger.info("Added is_active column to workstation_standards")

                    # Check standard_section_type column in test_sections
                    result = conn.execute(text("PRAGMA table_info(test_sections)"))
                    columns = [row[1] for row in result.fetchall()]
                    if 'standard_section_type' not in columns:
                        conn.execute(text("ALTER TABLE test_sections ADD COLUMN standard_section_type VARCHAR(50)"))
                        conn.commit()
                        logger.info("Added standard_section_type column to test_sections")

                    # Check measurement_target columns in test_points
                    result = conn.execute(text("PRAGMA table_info(test_points)"))
                    columns = [row[1] for row in result.fetchall()]
                    if 'measurement_target' not in columns:
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN measurement_target VARCHAR(20) DEFAULT 'PRIMARY'"))
                        conn.commit()
                        logger.info("Added measurement_target column to test_points")
                    else:
                        # Fix any lowercase values from earlier migration
                        conn.execute(text("UPDATE test_points SET measurement_target = 'PRIMARY' WHERE measurement_target = 'primary'"))
                        conn.execute(text("UPDATE test_points SET measurement_target = 'FREQUENCY' WHERE measurement_target = 'frequency'"))
                        conn.execute(text("UPDATE test_points SET measurement_target = 'CUSTOM' WHERE measurement_target = 'custom'"))
                        conn.commit()
                    if 'expected_value' not in columns:
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN expected_value FLOAT"))
                        conn.commit()
                        logger.info("Added expected_value column to test_points")
                    if 'expected_unit' not in columns:
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN expected_unit VARCHAR(20)"))
                        conn.commit()
                        logger.info("Added expected_unit column to test_points")
                    if 'wiring_diagram_type' not in columns:
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN wiring_diagram_type VARCHAR(100)"))
                        conn.commit()
                        logger.info("Added wiring_diagram_type column to test_points")
                    if 'operator_prompt' not in columns:
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN operator_prompt TEXT"))
                        conn.commit()
                        logger.info("Added operator_prompt column to test_points")
                    if 'dmm_config' not in columns:
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN dmm_config TEXT"))
                        conn.commit()
                        logger.info("Added dmm_config column to test_points")
                    if 'pass_fail_min' not in columns:
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN pass_fail_min FLOAT"))
                        conn.commit()
                        logger.info("Added pass_fail_min column to test_points")
                    if 'pass_fail_max' not in columns:
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN pass_fail_max FLOAT"))
                        conn.commit()
                        logger.info("Added pass_fail_max column to test_points")
                    if 'pass_fail_range_unit' not in columns:
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN pass_fail_range_unit VARCHAR(20)"))
                        conn.commit()
                        logger.info("Added pass_fail_range_unit column to test_points")
                    if 'pre_conditioning_steps' not in columns:
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN pre_conditioning_steps TEXT"))
                        conn.commit()
                        logger.info("Added pre_conditioning_steps column to test_points")

                    # Multi-component tolerance columns for test_points
                    tol_columns = [
                        ('tol_pct_reading', 'FLOAT DEFAULT 0'),
                        ('tol_pct_range', 'FLOAT DEFAULT 0'),
                        ('tol_pct_span', 'FLOAT DEFAULT 0'),
                        ('tol_digits', 'FLOAT DEFAULT 0'),
                        ('tol_absolute', 'FLOAT DEFAULT 0'),
                        ('tol_resolution', 'FLOAT'),
                        ('tol_range_value', 'FLOAT'),
                        ('tol_span_value', 'FLOAT'),
                    ]
                    for col_name, col_type in tol_columns:
                        if col_name not in columns:
                            conn.execute(text(f"ALTER TABLE test_points ADD COLUMN {col_name} {col_type}"))
                            conn.commit()
                            logger.info(f"Added {col_name} column to test_points")

                    # Migrate existing tolerance data to new format
                    # percent -> tol_pct_reading, absolute -> tol_absolute
                    if 'tol_pct_reading' in columns or 'tol_pct_reading' not in columns:
                        conn.execute(text("""
                            UPDATE test_points
                            SET tol_pct_reading = tolerance_value
                            WHERE tolerance_type = 'percent'
                            AND (tol_pct_reading IS NULL OR tol_pct_reading = 0)
                            AND tolerance_value IS NOT NULL AND tolerance_value > 0
                        """))
                        conn.execute(text("""
                            UPDATE test_points
                            SET tol_absolute = tolerance_value
                            WHERE tolerance_type = 'absolute'
                            AND (tol_absolute IS NULL OR tol_absolute = 0)
                            AND tolerance_value IS NOT NULL AND tolerance_value > 0
                        """))
                        conn.execute(text("""
                            UPDATE test_points
                            SET tol_pct_reading = tolerance_value / 10000.0
                            WHERE tolerance_type = 'ppm'
                            AND (tol_pct_reading IS NULL OR tol_pct_reading = 0)
                            AND tolerance_value IS NOT NULL AND tolerance_value > 0
                        """))
                        conn.commit()

                    # Multi-component tolerance columns for test_results
                    result = conn.execute(text("PRAGMA table_info(test_results)"))
                    result_columns = [row[1] for row in result.fetchall()]
                    result_tol_columns = [
                        ('tol_pct_reading', 'FLOAT'),
                        ('tol_pct_range', 'FLOAT'),
                        ('tol_pct_span', 'FLOAT'),
                        ('tol_digits', 'FLOAT'),
                        ('tol_absolute', 'FLOAT'),
                        ('tol_resolution', 'FLOAT'),
                        ('tol_range_value', 'FLOAT'),
                        ('tol_span_value', 'FLOAT'),
                        ('calculated_tolerance', 'FLOAT'),
                    ]
                    for col_name, col_type in result_tol_columns:
                        if col_name not in result_columns:
                            conn.execute(text(f"ALTER TABLE test_results ADD COLUMN {col_name} {col_type}"))
                            conn.commit()
                            logger.info(f"Added {col_name} column to test_results")

                    # Check is_published column in changelog_entries
                    result = conn.execute(text("PRAGMA table_info(changelog_entries)"))
                    columns = [row[1] for row in result.fetchall()]
                    if 'is_published' not in columns:
                        conn.execute(text("ALTER TABLE changelog_entries ADD COLUMN is_published BOOLEAN DEFAULT 0"))
                        conn.commit()
                        # Mark all existing entries as published
                        conn.execute(text("UPDATE changelog_entries SET is_published = 1 WHERE version IS NOT NULL"))
                        conn.commit()
                        logger.info("Added is_published column to changelog_entries")

                    # Check customer fields in duts table
                    result = conn.execute(text("PRAGMA table_info(duts)"))
                    dut_columns = [row[1] for row in result.fetchall()]
                    if 'customer_id' not in dut_columns:
                        conn.execute(text("ALTER TABLE duts ADD COLUMN customer_id VARCHAR(100)"))
                        conn.commit()
                        logger.info("Added customer_id column to duts")
                    if 'customer_serial' not in dut_columns:
                        conn.execute(text("ALTER TABLE duts ADD COLUMN customer_serial VARCHAR(100)"))
                        conn.commit()
                        logger.info("Added customer_serial column to duts")

                    # Model database tables (manufacturers, lab_codes, device_models)
                    # These are created by create_all() but we check for device_model_id FK in duts
                    if 'device_model_id' not in dut_columns:
                        conn.execute(text("ALTER TABLE duts ADD COLUMN device_model_id INTEGER REFERENCES device_models(id)"))
                        conn.commit()
                        logger.info("Added device_model_id column to duts")

                    # DUT remote communication - com_port field
                    if 'com_port' not in dut_columns:
                        conn.execute(text("ALTER TABLE duts ADD COLUMN com_port VARCHAR(20)"))
                        conn.commit()
                        logger.info("Added com_port column to duts")

                    # DUT remote fields for test_points
                    result = conn.execute(text("PRAGMA table_info(test_points)"))
                    tp_columns = [row[1] for row in result.fetchall()]
                    dut_remote_columns = [
                        ('dut_setup_command', 'VARCHAR(50)'),
                        ('dut_setup_param', 'VARCHAR(100)'),
                        ('dut_pre_check_command', 'VARCHAR(50)'),
                        ('dut_pre_check_param', 'VARCHAR(100)'),
                        ('dut_pre_check_expected', 'VARCHAR(100)'),
                        ('dut_post_read_command', 'VARCHAR(50)'),
                        ('dut_post_read_param', 'VARCHAR(100)'),
                        ('dut_post_read_parser', 'VARCHAR(50)'),
                        ('dut_post_read_index', 'INTEGER'),
                    ]
                    for col_name, col_type in dut_remote_columns:
                        if col_name not in tp_columns:
                            conn.execute(text(f"ALTER TABLE test_points ADD COLUMN {col_name} {col_type}"))
                            conn.commit()
                            logger.info(f"Added {col_name} column to test_points")

                else:
                    # MySQL migrations
                    # Check is_active column
                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'workstation_standards' AND COLUMN_NAME = 'is_active'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE workstation_standards ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
                        conn.commit()
                        logger.info("Added is_active column to workstation_standards")

                    # Check standard_section_type column
                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'test_sections' AND COLUMN_NAME = 'standard_section_type'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE test_sections ADD COLUMN standard_section_type VARCHAR(50)"))
                        conn.commit()
                        logger.info("Added standard_section_type column to test_sections")

                    # Check measurement_target columns in test_points
                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = 'measurement_target'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN measurement_target VARCHAR(20) DEFAULT 'PRIMARY'"))
                        conn.commit()
                        logger.info("Added measurement_target column to test_points")
                    else:
                        # Fix any lowercase values from earlier migration
                        conn.execute(text("UPDATE test_points SET measurement_target = 'PRIMARY' WHERE measurement_target = 'primary'"))
                        conn.execute(text("UPDATE test_points SET measurement_target = 'FREQUENCY' WHERE measurement_target = 'frequency'"))
                        conn.execute(text("UPDATE test_points SET measurement_target = 'CUSTOM' WHERE measurement_target = 'custom'"))
                        conn.commit()

                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = 'expected_value'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN expected_value FLOAT"))
                        conn.commit()
                        logger.info("Added expected_value column to test_points")

                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = 'expected_unit'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN expected_unit VARCHAR(20)"))
                        conn.commit()
                        logger.info("Added expected_unit column to test_points")

                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = 'wiring_diagram_type'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN wiring_diagram_type VARCHAR(100)"))
                        conn.commit()
                        logger.info("Added wiring_diagram_type column to test_points")

                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = 'operator_prompt'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN operator_prompt TEXT"))
                        conn.commit()
                        logger.info("Added operator_prompt column to test_points")

                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = 'dmm_config'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN dmm_config JSON"))
                        conn.commit()
                        logger.info("Added dmm_config column to test_points")

                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = 'pass_fail_min'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN pass_fail_min FLOAT"))
                        conn.commit()
                        logger.info("Added pass_fail_min column to test_points")

                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = 'pass_fail_max'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN pass_fail_max FLOAT"))
                        conn.commit()
                        logger.info("Added pass_fail_max column to test_points")

                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = 'pass_fail_range_unit'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN pass_fail_range_unit VARCHAR(20)"))
                        conn.commit()
                        logger.info("Added pass_fail_range_unit column to test_points")

                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = 'pre_conditioning_steps'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE test_points ADD COLUMN pre_conditioning_steps JSON"))
                        conn.commit()
                        logger.info("Added pre_conditioning_steps column to test_points")

                    # Multi-component tolerance columns for test_points (MySQL)
                    mysql_tol_columns = [
                        ('tol_pct_reading', 'FLOAT DEFAULT 0'),
                        ('tol_pct_range', 'FLOAT DEFAULT 0'),
                        ('tol_pct_span', 'FLOAT DEFAULT 0'),
                        ('tol_digits', 'FLOAT DEFAULT 0'),
                        ('tol_absolute', 'FLOAT DEFAULT 0'),
                        ('tol_resolution', 'FLOAT'),
                        ('tol_range_value', 'FLOAT'),
                        ('tol_span_value', 'FLOAT'),
                    ]
                    for col_name, col_type in mysql_tol_columns:
                        result = conn.execute(text(
                            f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                            f"WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = '{col_name}'"
                        ))
                        if not result.fetchone():
                            conn.execute(text(f"ALTER TABLE test_points ADD COLUMN {col_name} {col_type}"))
                            conn.commit()
                            logger.info(f"Added {col_name} column to test_points")

                    # Migrate existing tolerance data to new format (MySQL)
                    conn.execute(text("""
                        UPDATE test_points
                        SET tol_pct_reading = tolerance_value
                        WHERE tolerance_type = 'percent'
                        AND (tol_pct_reading IS NULL OR tol_pct_reading = 0)
                        AND tolerance_value IS NOT NULL AND tolerance_value > 0
                    """))
                    conn.execute(text("""
                        UPDATE test_points
                        SET tol_absolute = tolerance_value
                        WHERE tolerance_type = 'absolute'
                        AND (tol_absolute IS NULL OR tol_absolute = 0)
                        AND tolerance_value IS NOT NULL AND tolerance_value > 0
                    """))
                    conn.execute(text("""
                        UPDATE test_points
                        SET tol_pct_reading = tolerance_value / 10000.0
                        WHERE tolerance_type = 'ppm'
                        AND (tol_pct_reading IS NULL OR tol_pct_reading = 0)
                        AND tolerance_value IS NOT NULL AND tolerance_value > 0
                    """))
                    conn.commit()

                    # Multi-component tolerance columns for test_results (MySQL)
                    mysql_result_tol_columns = [
                        ('tol_pct_reading', 'FLOAT'),
                        ('tol_pct_range', 'FLOAT'),
                        ('tol_pct_span', 'FLOAT'),
                        ('tol_digits', 'FLOAT'),
                        ('tol_absolute', 'FLOAT'),
                        ('tol_resolution', 'FLOAT'),
                        ('tol_range_value', 'FLOAT'),
                        ('tol_span_value', 'FLOAT'),
                        ('calculated_tolerance', 'FLOAT'),
                    ]
                    for col_name, col_type in mysql_result_tol_columns:
                        result = conn.execute(text(
                            f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                            f"WHERE TABLE_NAME = 'test_results' AND COLUMN_NAME = '{col_name}'"
                        ))
                        if not result.fetchone():
                            conn.execute(text(f"ALTER TABLE test_results ADD COLUMN {col_name} {col_type}"))
                            conn.commit()
                            logger.info(f"Added {col_name} column to test_results")

                    # Check is_published column in changelog_entries
                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'changelog_entries' AND COLUMN_NAME = 'is_published'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE changelog_entries ADD COLUMN is_published BOOLEAN DEFAULT FALSE"))
                        conn.commit()
                        # Mark all existing entries as published
                        conn.execute(text("UPDATE changelog_entries SET is_published = TRUE WHERE version IS NOT NULL"))
                        conn.commit()
                        logger.info("Added is_published column to changelog_entries")

                    # Check customer fields in duts table (MySQL)
                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'duts' AND COLUMN_NAME = 'customer_id'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE duts ADD COLUMN customer_id VARCHAR(100)"))
                        conn.commit()
                        logger.info("Added customer_id column to duts")
                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'duts' AND COLUMN_NAME = 'customer_serial'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE duts ADD COLUMN customer_serial VARCHAR(100)"))
                        conn.commit()
                        logger.info("Added customer_serial column to duts")

                    # Model database tables - check device_model_id FK in duts
                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'duts' AND COLUMN_NAME = 'device_model_id'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE duts ADD COLUMN device_model_id INTEGER"))
                        conn.commit()
                        logger.info("Added device_model_id column to duts")

                    # DUT remote communication - com_port field
                    result = conn.execute(text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'duts' AND COLUMN_NAME = 'com_port'"
                    ))
                    if not result.fetchone():
                        conn.execute(text("ALTER TABLE duts ADD COLUMN com_port VARCHAR(20)"))
                        conn.commit()
                        logger.info("Added com_port column to duts")

                    # DUT remote fields for test_points
                    dut_remote_columns = [
                        ('dut_setup_command', 'VARCHAR(50)'),
                        ('dut_setup_param', 'VARCHAR(100)'),
                        ('dut_pre_check_command', 'VARCHAR(50)'),
                        ('dut_pre_check_param', 'VARCHAR(100)'),
                        ('dut_pre_check_expected', 'VARCHAR(100)'),
                        ('dut_post_read_command', 'VARCHAR(50)'),
                        ('dut_post_read_param', 'VARCHAR(100)'),
                        ('dut_post_read_parser', 'VARCHAR(50)'),
                        ('dut_post_read_index', 'INTEGER'),
                    ]
                    for col_name, col_type in dut_remote_columns:
                        result = conn.execute(text(
                            f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                            f"WHERE TABLE_NAME = 'test_points' AND COLUMN_NAME = '{col_name}'"
                        ))
                        if not result.fetchone():
                            conn.execute(text(f"ALTER TABLE test_points ADD COLUMN {col_name} {col_type}"))
                            conn.commit()
                            logger.info(f"Added {col_name} column to test_points")

        except Exception as e:
            logger.warning(f"Migration check: {e}")

    def test_connection(self) -> tuple[bool, str]:
        """
        Test database connection.

        Returns:
            Tuple of (success, message)
        """
        if not self._initialized or not self._engine:
            return False, "Database not initialized"

        try:
            with self._engine.connect() as conn:
                if getattr(self, '_is_sqlite', False):
                    result = conn.execute(text("SELECT sqlite_version()"))
                    version = result.scalar()
                    return True, f"Connected to SQLite {version}"
                else:
                    result = conn.execute(text("SELECT VERSION()"))
                    version = result.scalar()
                    return True, f"Connected to MySQL {version}"
        except SQLAlchemyError as e:
            return False, str(e)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions.

        Usage:
            with db.session() as session:
                session.query(...)
        """
        if not self._initialized or not self._session_factory:
            raise RuntimeError("Database not connected")

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            session.close()

    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._initialized and self._engine is not None


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_db() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
