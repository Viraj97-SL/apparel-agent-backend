import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=30,              # Increased from 10
    max_overflow=50,           # Increased from 20
    pool_timeout=30,           # Increased from 5s → 30s
    pool_recycle=3600,         # 1 hour
    pool_pre_ping=True,        # Already good
    pool_use_lifo=True,        # Better for high concurrency
    echo=False                 # Set True only for debugging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()