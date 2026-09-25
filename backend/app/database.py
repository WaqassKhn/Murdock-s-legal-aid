from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Identified:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Identified, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)


class SessionToken(Identified, Base):
    __tablename__ = 'session_tokens'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Workspace(Identified, Base):
    __tablename__ = 'workspaces'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(160))
    objective: Mapped[str] = mapped_column(Text, default='')
    jurisdiction: Mapped[str] = mapped_column(String(160), default='Unknown')
    is_demo: Mapped[bool] = mapped_column(default=False)


class Document(Identified, Base):
    __tablename__ = 'documents'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(32), default='uploaded')
    storage_key: Mapped[str] = mapped_column(String(80))
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DocumentVersion(Identified, Base):
    __tablename__ = 'document_versions'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)


class DocumentPage(Identified, Base):
    __tablename__ = 'document_pages'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class DocumentSection(Identified, Base):
    __tablename__ = 'document_sections'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('document_versions.id', ondelete='CASCADE'))
    payload: Mapped[dict] = mapped_column(JSON)


class DocumentChunk(Identified, Base):
    __tablename__ = 'document_chunks'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('document_versions.id', ondelete='CASCADE'))
    payload: Mapped[dict] = mapped_column(JSON)


class Clause(Identified, Base):
    __tablename__ = 'clauses'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('document_versions.id', ondelete='CASCADE'))
    payload: Mapped[dict] = mapped_column(JSON)


class Entity(Identified, Base):
    __tablename__ = 'entities'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('document_versions.id', ondelete='CASCADE'))
    payload: Mapped[dict] = mapped_column(JSON)


class Obligation(Identified, Base):
    __tablename__ = 'obligations'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('document_versions.id', ondelete='CASCADE'))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default='open')
    user_action: Mapped[str] = mapped_column(Text, default='')
    user_notes: Mapped[str] = mapped_column(Text, default='')


class RiskFinding(Identified, Base):
    __tablename__ = 'risk_findings'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('document_versions.id', ondelete='CASCADE'))
    payload: Mapped[dict] = mapped_column(JSON)


class AnalysisRun(Identified, Base):
    __tablename__ = 'analysis_runs'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(32), default='uploaded')
    kind: Mapped[str] = mapped_column(String(16), default='ingest')
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Comparison(Identified, Base):
    __tablename__ = 'comparisons'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), index=True)
    left_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'))
    right_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'))
    payload: Mapped[dict] = mapped_column(JSON)


class ChatSession(Identified, Base):
    __tablename__ = 'chat_sessions'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), index=True)


class Message(Identified, Base):
    __tablename__ = 'messages'
    session_id: Mapped[str] = mapped_column(ForeignKey('chat_sessions.id', ondelete='CASCADE'), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Citation(Identified, Base):
    __tablename__ = 'citations'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('document_versions.id', ondelete='CASCADE'))
    payload: Mapped[dict] = mapped_column(JSON)


class GeneratedReport(Identified, Base):
    __tablename__ = 'generated_reports'
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(8))
    storage_key: Mapped[str] = mapped_column(String(80))
    document_ids: Mapped[list] = mapped_column(JSON)


def database(url: str, serverless: bool = False):
    engine = create_engine(
        url,
        connect_args={'check_same_thread': False} if url.startswith('sqlite') else {},
        pool_pre_ping=True,
        **({'poolclass': NullPool} if serverless else {}),
    )
    if url.startswith('sqlite'):

        @event.listens_for(engine, 'connect')
        def sqlite_config(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA busy_timeout=15000')
            connection.execute('PRAGMA journal_mode=WAL')

    return engine, sessionmaker(engine, expire_on_commit=False, info={'serverless': serverless})
