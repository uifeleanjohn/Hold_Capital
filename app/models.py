"""Phase A data model. Parcels are derived from Trades by the engine, so we
store raw trades/dividends (the source of truth) plus journal notes and a
price cache."""
from datetime import datetime, date
from sqlalchemy import (Column, Integer, String, Float, Date, DateTime, ForeignKey, UniqueConstraint)
from sqlalchemy.orm import relationship
from .db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    other_income = Column(Float, nullable=True)        # for ATO-bracket tax estimate
    tier = Column(String(10), default="free")          # free | plus | pro
    stripe_customer_id = Column(String(64), nullable=True)
    subscription_status = Column(String(20), nullable=True)
    inbox_token = Column(String(32), unique=True, nullable=True)  # per-user email address token
    snaptrade_user_secret = Column(String(128), nullable=True)    # SnapTrade per-user secret
    created_at = Column(DateTime, default=datetime.utcnow)
    trades = relationship("Trade", back_populates="user", cascade="all, delete-orphan")
    dividends = relationship("Dividend", back_populates="user", cascade="all, delete-orphan")


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    date = Column(Date, nullable=False)
    ticker = Column(String(12), nullable=False)
    action = Column(String(4), nullable=False)         # BUY | SELL
    qty = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    brokerage = Column(Float, default=0.0)
    fx = Column(Float, default=1.0)                    # AUD per unit of local currency
    source = Column(String(24), default="manual")     # manual | commsec | email:commsec | ...
    source_ref = Column(String(80), nullable=True)    # broker confirmation ref (for dedup)
    account = Column(String(40), default="Default")   # portfolio / account name
    user = relationship("User", back_populates="trades")


class Dividend(Base):
    __tablename__ = "dividends"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    date = Column(Date, nullable=False)
    ticker = Column(String(12), nullable=False)
    cash = Column(Float, nullable=False)
    franking = Column(Float, default=0.0)              # 0..1 proportion
    franking_credit = Column(Float, nullable=True)     # explicit, from a statement
    withholding = Column(Float, default=0.0)
    fx = Column(Float, default=1.0)
    account = Column(String(40), default="Default")   # portfolio / account name
    user = relationship("User", back_populates="dividends")


class JournalNote(Base):
    __tablename__ = "journal_notes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    trade_key = Column(String(64), nullable=False)     # ticker|acquired|disposed
    setup = Column(String(40))
    confidence = Column(Integer)
    notes = Column(String(1000))
    __table_args__ = (UniqueConstraint("user_id", "trade_key", name="uq_user_tradekey"),)


class PriceCache(Base):
    __tablename__ = "price_cache"
    ticker = Column(String(12), primary_key=True)
    price = Column(Float, nullable=False)
    fx = Column(Float, default=1.0)
    currency = Column(String(4), default="AUD")
    asof = Column(DateTime, default=datetime.utcnow)
