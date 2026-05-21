"""
Database migration utilities.
Automatically applies schema changes on app startup.
"""

from sqlalchemy import text
from loguru import logger


def apply_migrations(db):
    """
    Apply all pending database migrations.

    This runs automatically on app startup and adds any missing columns
    to the database schema without affecting existing data.

    Args:
        db: DatabaseManager instance

    Returns:
        bool: True if migrations succeeded, False otherwise
    """
    if not db.is_connected:
        logger.warning("Cannot apply migrations - database not connected")
        return False

    try:
        with db.session() as session:
            migrations_applied = []

            # Migration: Add pass_fail_image column
            result = session.execute(text(
                "SELECT COUNT(*) FROM pragma_table_info('test_points') WHERE name='pass_fail_image'"
            )).scalar()

            if result == 0:
                logger.info("Applying migration: Adding pass_fail_image column")
                session.execute(text(
                    "ALTER TABLE test_points ADD COLUMN pass_fail_image VARCHAR(255)"
                ))
                session.commit()
                migrations_applied.append("pass_fail_image")
                logger.info("✓ Migration applied: pass_fail_image column added")

            # Migration: Add manual_setup column
            result = session.execute(text(
                "SELECT COUNT(*) FROM pragma_table_info('test_points') WHERE name='manual_setup'"
            )).scalar()

            if result == 0:
                logger.info("Applying migration: Adding manual_setup column")
                session.execute(text(
                    "ALTER TABLE test_points ADD COLUMN manual_setup BOOLEAN DEFAULT 0"
                ))
                session.commit()
                migrations_applied.append("manual_setup")
                logger.info("✓ Migration applied: manual_setup column added")

            # Migration: Add manual_setup_prompt column
            result = session.execute(text(
                "SELECT COUNT(*) FROM pragma_table_info('test_points') WHERE name='manual_setup_prompt'"
            )).scalar()

            if result == 0:
                logger.info("Applying migration: Adding manual_setup_prompt column")
                session.execute(text(
                    "ALTER TABLE test_points ADD COLUMN manual_setup_prompt TEXT"
                ))
                session.commit()
                migrations_applied.append("manual_setup_prompt")
                logger.info("✓ Migration applied: manual_setup_prompt column added")

            # Add future migrations here following the same pattern:
            # 1. Check if column/table exists
            # 2. If not, create it
            # 3. Commit the change
            # 4. Log what was done

            if migrations_applied:
                logger.info(f"Applied {len(migrations_applied)} migration(s): {', '.join(migrations_applied)}")
            else:
                logger.debug("Database schema is up to date, no migrations needed")

            return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
