"""
Apply manual_setup migration immediately
"""
from calsystem.database.connection import get_db
from calsystem.database.migrations import apply_migrations
from loguru import logger

logger.info("Applying manual_setup migration...")
db = get_db()
if db.connect():
    logger.info("Connected to database")
    success = apply_migrations(db)
    if success:
        logger.info("Migration applied successfully!")
    else:
        logger.error("Migration failed")
else:
    logger.error("Could not connect to database")
