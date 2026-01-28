import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Ensure we get the Database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Fallback for local testing if needed
    DATABASE_URL = "sqlite:///./test.db"

# 🛠️ FIX: Add pool_pre_ping=True to prevent SSL EOF errors
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Checks connection life before using it
    pool_recycle=1800    # Recycles connections every 30 mins
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# This Base is used for models
Base = declarative_base()