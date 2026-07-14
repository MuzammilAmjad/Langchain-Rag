from __future__ import annotations

import datetime
import os

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# Defaults to a local SQLite file for development. In production, set
# DATABASE_URL to a managed Postgres instance (e.g. Railway/Render addon) —
# unlike a local file or SQLite on an ephemeral disk, that survives redeploys.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    namespace = Column(String, primary_key=True)
    pdf_name = Column(String, nullable=False)
    content_signature = Column(String, nullable=False)
    source_count = Column(Integer, default=0)
    page_count = Column(Integer, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)  # list[{id, source, page, excerpt, namespace}]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()