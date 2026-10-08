"""Storage: SQLite at the edge, PostgreSQL at the centre, same models.

Each event row keeps the full IBVAPEvent as JSON (`payload`) plus indexed
copies of the fields operators filter and sort on.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class EventRow(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(64), index=True)
    camera_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    severity_rank: Mapped[int] = mapped_column(Integer, index=True)
    # Naive UTC throughout, so comparisons behave the same on SQLite and PostgreSQL.
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    object_type: Mapped[str | None] = mapped_column(String(32))
    tracking_id: Mapped[str | None] = mapped_column(String(64), index=True)
    plate_text: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    sync_status: Mapped[str] = mapped_column(String(16), index=True)
    payload: Mapped[dict] = mapped_column(JSON)

    # Pipeline timing (epoch seconds) for the frame-to-alert latency target.
    frame_ts: Mapped[float | None] = mapped_column(Float)
    received_ts: Mapped[float | None] = mapped_column(Float)
    stored_ts: Mapped[float | None] = mapped_column(Float)
    broadcast_ts: Mapped[float | None] = mapped_column(Float)


class AuditRow(Base):
    """Every alert lifecycle transition (CLAUDE.md §4)."""

    __tablename__ = "event_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.event_id"), index=True)
    from_status: Mapped[str] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(128))
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime)


class CameraRow(Base):
    __tablename__ = "cameras"

    camera_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(64))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        db_path = url.removeprefix("sqlite:///")
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_engine(url, pool_pre_ping=True)


def make_sessionmaker(engine: Engine) -> sessionmaker:
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
