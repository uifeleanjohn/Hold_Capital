-- HoldCapital Phase A — reference schema (Postgres).
-- The app creates these automatically via SQLAlchemy; this file documents the shape.

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    other_income    DOUBLE PRECISION,
    created_at      TIMESTAMP DEFAULT now()
);

CREATE TABLE trades (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    ticker      VARCHAR(12) NOT NULL,
    action      VARCHAR(4) NOT NULL,        -- BUY | SELL
    qty         DOUBLE PRECISION NOT NULL,
    price       DOUBLE PRECISION NOT NULL,
    brokerage   DOUBLE PRECISION DEFAULT 0,
    fx          DOUBLE PRECISION DEFAULT 1, -- AUD per unit local currency
    source      VARCHAR(20) DEFAULT 'manual'
);
CREATE INDEX ix_trades_user ON trades(user_id);

CREATE TABLE dividends (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date            DATE NOT NULL,
    ticker          VARCHAR(12) NOT NULL,
    cash            DOUBLE PRECISION NOT NULL,
    franking        DOUBLE PRECISION DEFAULT 0,
    franking_credit DOUBLE PRECISION,
    withholding     DOUBLE PRECISION DEFAULT 0,
    fx              DOUBLE PRECISION DEFAULT 1
);
CREATE INDEX ix_dividends_user ON dividends(user_id);

CREATE TABLE journal_notes (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trade_key   VARCHAR(64) NOT NULL,
    setup       VARCHAR(40),
    confidence  INTEGER,
    notes       VARCHAR(1000),
    UNIQUE (user_id, trade_key)
);

CREATE TABLE price_cache (
    ticker      VARCHAR(12) PRIMARY KEY,
    price       DOUBLE PRECISION NOT NULL,
    fx          DOUBLE PRECISION DEFAULT 1,
    currency    VARCHAR(4) DEFAULT 'AUD',
    asof        TIMESTAMP DEFAULT now()
);
