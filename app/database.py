import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

_is_sqlite = (SQLALCHEMY_DATABASE_URL or "").startswith("sqlite")

_engine_kwargs = {
    "pool_recycle": 3600,
    "pool_pre_ping": True,
    "echo": False,
}
if not _is_sqlite:
    _engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 10,
        "pool_use_lifo": True,
    })

engine = create_engine(SQLALCHEMY_DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()