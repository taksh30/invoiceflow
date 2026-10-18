"""Database engine, declarative base, and session factory utilities."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy entities."""


def create_db_engine(url: str, echo: bool = False) -> Engine:
    """Create a configured SQLAlchemy engine for SQLite or PostgreSQL."""
    connect_args: dict[str, bool] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    if url == "sqlite:///:memory:":
        return create_engine(
            url,
            connect_args=connect_args,
            poolclass=StaticPool,
            echo=echo,
        )

    return create_engine(url, connect_args=connect_args, echo=echo)


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a thread-safe SQLAlchemy sessionmaker."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create all schema tables on the target engine."""
    Base.metadata.create_all(engine)
