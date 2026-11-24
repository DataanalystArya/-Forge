import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from app.core.config import settings

logger = logging.getLogger("forge.database")

Base = declarative_base()


def get_engine():
    """Create and return a resilient SQLAlchemy engine."""
    database_url = settings.DATABASE_URL
    
    # Check if configured for PostgreSQL
    if database_url.startswith("postgresql"):
        try:
            logger.info("Attempting connection to PostgreSQL database...")
            engine = create_engine(
                database_url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                connect_args={"connect_timeout": 3}
            )
            # Test immediate connectivity
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Connected successfully to PostgreSQL database.")
            return engine
        except Exception as e:
            logger.warning(
                f"PostgreSQL connection failed ({e}). Falling back to SQLite local database for development."
            )
            database_url = "sqlite:///./forge.db"

    # SQLite configuration
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create database tables if they do not exist."""
    from app.models import user, repository, session  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("Database schemas initialized.")


def get_db() -> Generator[Session, None, None]:
    """Dependency for yielding a transactional SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
