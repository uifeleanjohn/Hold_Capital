"""EODHD price client + cache refresh. With no API key it falls back to seed
prices so the app runs offline; with a key it pulls live (delayed) prices.
EODHD holds an ASX redistribution licence, which is why it's the chosen feed."""
from datetime import datetime

from .config import EODHD_API_KEY
from . import refdata
from .models import PriceCache


def fetch_live_price(ticker: str, exchange: str):
    if not EODHD_API_KEY:
        return None
    suffix = refdata.EODHD_SUFFIX.get(exchange)
    if not suffix:
        return None
    try:
        import httpx
        url = f"https://eodhd.com/api/real-time/{ticker}.{suffix}"
        r = httpx.get(url, params={"api_token": EODHD_API_KEY, "fmt": "json"}, timeout=10)
        r.raise_for_status()
        px = r.json().get("close")
        return float(px) if px not in (None, "NA", "") else None
    except Exception:
        return None


def fetch_crypto_price(ticker: str):
    """Live crypto price in AUD via CoinGecko (no API key required)."""
    cid = refdata.COINGECKO_IDS.get(ticker)
    if not cid:
        return None
    try:
        import httpx
        r = httpx.get("https://api.coingecko.com/api/v3/simple/price",
                      params={"ids": cid, "vs_currencies": "aud"}, timeout=10)
        r.raise_for_status()
        return float(r.json()[cid]["aud"])
    except Exception:
        return None


_METAL_SYMBOL = {"XAU": "XAUUSD.FOREX", "XAG": "XAGUSD.FOREX", "XPT": "XPTUSD.FOREX"}

def fetch_metal_price(ticker: str):
    """Spot metal price per oz in AUD via EODHD forex (USD spot / AUDUSD).
    Uses the existing EODHD key — no separate metals vendor needed."""
    sym = _METAL_SYMBOL.get(ticker)
    if not EODHD_API_KEY or not sym:
        return None
    try:
        import httpx
        def rt(s):
            r = httpx.get(f"https://eodhd.com/api/real-time/{s}",
                          params={"api_token": EODHD_API_KEY, "fmt": "json"}, timeout=10)
            r.raise_for_status()
            return r.json().get("close")
        usd = rt(sym)              # USD per oz
        audusd = rt("AUDUSD.FOREX")  # USD per 1 AUD
        if usd in (None, "NA", "") or audusd in (None, "NA", "", 0):
            return None
        return float(usd) / float(audusd)   # -> AUD per oz
    except Exception:
        return None


def refresh_prices(db, tickers):
    """Upsert a price for each ticker, routed to the right source by asset class
    (CoinGecko for crypto, EODHD for equities, metals provider for bullion).
    Falls back to seed prices when a source is unavailable."""
    updated = 0
    for tk in tickers:
        name, exch, tag, ccy, seed_px, seed_fx = refdata.meta(tk)
        if exch == "CRYPTO":
            live = fetch_crypto_price(tk)
        elif exch == "METAL":
            live = fetch_metal_price(tk)
        else:
            live = fetch_live_price(tk, exch)
        pc = db.get(PriceCache, tk) or PriceCache(ticker=tk)
        pc.price = live if live is not None else seed_px
        pc.fx = seed_fx          # TODO production: fetch live AUD/USD for equities
        pc.currency = ccy
        pc.asof = datetime.utcnow()
        db.add(pc)
        updated += 1
    db.commit()
    return {"updated": updated, "source": "eodhd+coingecko" if EODHD_API_KEY else "coingecko+seed"}
