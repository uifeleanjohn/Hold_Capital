"""Configuration via environment (with safe local defaults)."""
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./holdcapital.db")
# In production set DATABASE_URL to a managed Postgres URL, e.g.
#   postgresql+psycopg://user:pass@host:5432/holdcapital
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_TTL_HOURS = int(os.environ.get("JWT_TTL_HOURS", "168"))
EODHD_API_KEY = os.environ.get("EODHD_API_KEY", "")   # blank -> seed prices used

# Stripe (blank -> billing runs in stub mode, no real charges)
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_PLUS = os.environ.get("STRIPE_PRICE_PLUS", "")   # Stripe Price id for Plus
STRIPE_PRICE_PRO = os.environ.get("STRIPE_PRICE_PRO", "")     # Stripe Price id for Pro
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://127.0.0.1:5055")

# CORS — comma-separated origins, or "*"
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

# SnapTrade "connect your broker" (read-only aggregation). Blank -> stub mode.
SNAPTRADE_CLIENT_ID = os.environ.get("SNAPTRADE_CLIENT_ID", "")
SNAPTRADE_CONSUMER_KEY = os.environ.get("SNAPTRADE_CONSUMER_KEY", "")

# Inbound email (trade-confirmation auto-sync). The per-user address is
#   {INBOUND_LOCALPART}+{token}@{INBOUND_DOMAIN}
# For Postmark's default domain set INBOUND_LOCALPART to your inbound server hash;
# for a custom inbound domain (MX -> provider) any localpart works.
INBOUND_LOCALPART = os.environ.get("INBOUND_LOCALPART", "holdcapital")
INBOUND_DOMAIN = os.environ.get("INBOUND_DOMAIN", "inbound.postmarkapp.com")
INBOUND_WEBHOOK_SECRET = os.environ.get("INBOUND_WEBHOOK_SECRET", "")

