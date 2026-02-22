import logging
from database import Database

logger = logging.getLogger(__name__)

def run_migrations(db: Database):
    if db.use_memory or not db._ensure_connection():
        logger.warning("Skipping migrations: using in-memory database or connection failed.")
        return

    try:
        with db.conn.cursor() as cur:
            # Create system_config table for LLM priority and cost ceilings
            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_config (
                    key VARCHAR(255) PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Initialize default LLM priority if not exists
            cur.execute("""
                INSERT INTO system_config (key, value)
                VALUES ('llm_priority', '["kimi", "gemini", "openai", "anthropic", "xai"]')
                ON CONFLICT (key) DO NOTHING
            """)
            
            # Initialize default cost ceiling if not exists
            cur.execute("""
                INSERT INTO system_config (key, value)
                VALUES ('llm_cost_ceiling', '{"max_daily_usd": 10.0, "current_daily_usd": 0.0, "last_reset": null}')
                ON CONFLICT (key) DO NOTHING
            """)
            
            logger.info("✅ Database migrations completed successfully.")
    except Exception as e:
        logger.error(f"Error running database migrations: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = Database()
    run_migrations(db)
