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


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)  # list[{id, source, page, excerpt, namespace}]
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


def init_db() -> None:
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if "messages" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("messages")]
        if "conversation_id" not in columns:
            # Table is outdated; drop conversations & messages to reset schema.
            with engine.begin() as conn:
                if engine.url.drivername.startswith("sqlite"):
                    conn.execute(text("PRAGMA foreign_keys=OFF;"))
                conn.execute(text("DROP TABLE IF EXISTS messages;"))
                conn.execute(text("DROP TABLE IF EXISTS conversations;"))
    Base.metadata.create_all(engine)


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()