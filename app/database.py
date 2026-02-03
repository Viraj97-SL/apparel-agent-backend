import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Get DB URL
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# --- DATABASE CONFIG ---
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # Reduced to 10 to allow multiple processes to share the DB comfortably
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    pool_timeout=5,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()