"""Parse a broker trade-confirmation email into trades.

Real contract notes vary by broker and are sometimes PDF attachments; this
handles the common text/HTML confirmation formats and, true to the rest of the
app, FLAGS anything it can't read with confidence rather than guessing. Adding a
broker = adding a pattern here (or a PDF extractor for attachment-only brokers).
"""
from __future__ import annotations
import hashlib
import re
from datetime import date, datetime

_WS = re.compile(r"\s+")
# action  qty  TICKER  (shares)?  at|@|for  $price
_TRADE = re.compile(
    r"\b(bought|sold|buy|sell|purchased)\b\s+([\d,]+)\s+([A-Z]{1,6})\b(?:\s+shares?|\s+units?)?\s+(?:at|@|for)\s+\$?([\d,]+(?:\.\d+)?)",
    re.I)
_BROKERAGE = re.compile(r"brokerage[^$]*\$?\s*([\d,]+(?:\.\d+)?)", re.I)
_REF = re.compile(r"(?:confirmation|reference|contract\s*note|order)\s*(?:no\.?|number|id|#)?\s*[:#]?\s*([A-Z0-9\-]{4,})", re.I)
_DATE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")


def detect_broker(from_email: str, subject: str) -> str:
    s = ((from_email or "") + " " + (subject or "")).lower()
    for b in ("commsec", "stake", "selfwealth", "pearler", "superhero", "nabtrade"):
        if b in s:
            return b
    return "email"


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _parse_date(body: str, fallback: date | None):
    m = _DATE.search(body)
    if m:
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(m.group(1), fmt).date()
            except ValueError:
                continue
    return fallback or date.today()


def parse(subject: str, text: str, from_email: str, received: date | None = None) -> dict:
    broker = detect_broker(from_email, subject)
    body = _WS.sub(" ", text or "").strip()
    review, trades = [], []

    if not body:
        return {"broker": broker, "trades": [], "review": [{"reason": "empty email body"}]}

    found = list(_TRADE.finditer(body))
    if not found:
        return {"broker": broker, "trades": [],
                "review": [{"reason": "no recognisable buy/sell line — needs manual review", "subject": subject}]}

    dt = _parse_date(body, received)
    bm = _BROKERAGE.search(body)
    brokerage = _num(bm.group(1)) if bm else 0.0
    rm = _REF.search(body)

    for i, m in enumerate(found):
        word, qty, ticker, price = m.group(1).lower(), _num(m.group(2)), m.group(3).upper(), _num(m.group(4))
        action = "BUY" if word in ("bought", "buy", "purchased") else "SELL"
        ref = rm.group(1) if rm else hashlib.sha1(
            f"{broker}|{dt}|{ticker}|{action}|{qty}|{price}|{i}".encode()).hexdigest()[:16]
        trades.append({"date": dt, "ticker": ticker, "action": action, "qty": qty,
                       "price": price, "brokerage": brokerage if i == 0 else 0.0,
                       "fx": 1.0, "source_ref": ref})
    return {"broker": broker, "trades": trades, "review": review}
