"""Database engine/session setup and UTC-aware timestamp storage."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import String, TypeDecorator, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Overridable so the test suite can point at a throwaway database.
DB_PATH = Path(os.environ.get("SIGNALDESK_DB", Path(__file__).resolve().parent / "signaldesk.db"))

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},  # FastAPI serves requests from a threadpool
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """The one true 'now' — always timezone-aware UTC."""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores timezone-aware datetimes as ISO-8601 strings in UTC.

    - Rejects naive datetimes on write (fail loudly rather than guess).
    - Normalizes any zone to UTC before storage, so the stored text always
      carries a ``+00:00`` offset.
    - Returns timezone-aware UTC datetimes on read.
    """

    impl = String(35)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"expected datetime, got {type(value).__name__}")
        if value.tzinfo is None:
            raise ValueError("naive datetime rejected — timestamps must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:  # defensive: should never happen for rows we wrote
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)


def get_session():
    """FastAPI dependency: one session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
