"""
Database configuration for Capstone 2 Phase 1
Implements: SQLAlchemy connection, session management, and migrations
"""

import os
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
import logging

logger = logging.getLogger(__name__)

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ids_user:ids_password@localhost:5432/smart_city_ids"
)

# Engine configuration
engine_kwargs = {
    "echo": os.getenv("SQL_ECHO", "false").lower() == "true",  # Log SQL statements
    "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
    "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "3600")),
}

# Use NullPool for serverless/Lambda environments
if os.getenv("DB_USE_NULL_POOL", "false").lower() == "true":
    engine_kwargs["poolclass"] = NullPool

try:
    engine = create_engine(DATABASE_URL, **engine_kwargs)
    logger.info(f"Database engine created: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'unknown'}")
except Exception as e:
    logger.error(f"Failed to create database engine: {e}")
    raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency: Get database session"""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Initialize database (create tables)"""
    from src.ids_api.infrastructure.database import Base
    
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialization complete")


def run_migrations():
    """Run SQL migrations from files"""
    migrations_dir = "/home/aka/smart-city-ids/infrastructure/database/migrations"
    
    if not os.path.exists(migrations_dir):
        logger.warning(f"Migrations directory not found: {migrations_dir}")
        return
    
    # Get migration files in order
    migration_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith('.sql')])
    
    with engine.connect() as conn:
        for migration_file in migration_files:
            migration_path = os.path.join(migrations_dir, migration_file)
            
            try:
                with open(migration_path, 'r') as f:
                    sql = f.read()
                    logger.info(f"Running migration: {migration_file}")
                    conn.execute(sql)
                    conn.commit()
                    logger.info(f"Completed migration: {migration_file}")
            except Exception as e:
                logger.error(f"Failed to run migration {migration_file}: {e}")
                conn.rollback()
                raise


def health_check() -> bool:
    """Check database connectivity"""
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        logger.info("Database health check: OK")
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
