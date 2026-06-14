"""Database engine + session (SQLAlchemy)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import DATABASE_URL as _RAW_URL

# Managed Postgres (Render/Heroku/etc.) hands out a "postgres://" or
# "postgresql://" URL, which SQLAlchemy maps to the legacy psycopg2 driver.
# We ship psycopg (v3), so rewrite the URL to use it explicitly.
DATABASE_URL = _RAW_URL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models  # noqa: F401  (register models)
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns():
    """Lightweight forward-migration: add new columns to existing tables.
    Idempotent — errors (column already exists) are ignored. Avoids needing a
    full migration tool for this prototype."""
    stmts = [
        "ALTER TABLE users ADD COLUMN inbox_token VARCHAR(32)",
        "ALTER TABLE users ADD COLUMN snaptrade_user_secret VARCHAR(128)",
        "ALTER TABLE trades ADD COLUMN source_ref VARCHAR(80)",
        "ALTER TABLE trades ADD COLUMN account VARCHAR(40) DEFAULT 'All holdings'",
        "ALTER TABLE dividends ADD COLUMN account VARCHAR(40) DEFAULT 'All holdings'",
        "UPDATE trades SET account='All holdings' WHERE account='Default' OR account IS NULL",
        "UPDATE dividends SET account='All holdings' WHERE account='Default' OR account IS NULL",
    ]
    for s in stmts:
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql(s)
        except Exception:
            pass
