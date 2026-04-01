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
from calsystem.database.models import Base


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
