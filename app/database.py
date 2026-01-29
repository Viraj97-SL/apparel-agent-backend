import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Ensure we get the Database URL
DATABASE_URL = os.getenv("DATABASE_URL")

# 🛠️ FIX: Add pool_pre_ping=True to prevent SSL EOF errors
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()