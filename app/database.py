import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Get DB URL
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# --- CRITICAL FIX: CONNECTION POOL SETTINGS ---
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # Increase pool size (was 5, now 20) to handle multiple questions
    pool_size=20,
    # Allow temporary spikes (was 10, now 40)
    max_overflow=40,
    # Recycle connections every 30 mins to prevent stale errors
    pool_recycle=1800,
    # Wait only 2 seconds for a connection (fail fast instead of hanging 30s)
    pool_timeout=5,
    # Check connection health before using
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()