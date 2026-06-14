"""
HoldCapital broker importer
===========================
Normalises messy real-world broker exports into the engine's trade/dividend
shape. Design principles:

  * Tolerant     — case-insensitive headers, multiple date formats, aliases.
  * Adaptered    — one adapter per broker; auto-detected from the header row.
  * Non-lossy    — rows that can't be parsed are collected in `review` with a
                   reason, never silently dropped. This is what keeps a real
                   import trustworthy.

Output of `import_file()`:
    ImportResult(trades=[...], dividends=[...], review=[...], broker="commsec")
where each trade is the exact dict the engine consumes:
    {date, ticker, action, qty, price, brokerage, fx}
and each dividend is:
    {date, ticker, cash, franking, withholding, fx}
"""

from __future__ import annotations
import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, date


# ----------------------------------------------------------------------------
@dataclass
class ImportResult:
    broker: str
    trades: list = field(default_factory=list)
    dividends: list = field(default_factory=list)
    review: list = field(default_factory=list)   # {row, reason, raw}

    def flag(self, rownum, reason, raw, severity="review"):
        self.review.append(dict(row=rownum, reason=reason, raw=raw, severity=severity))


def parse_date(s: str) -> date:
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %b %Y", "%d-%b-%Y", "%d/%m/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date '{s}'")


def _num(s):
    if s is None:
        return 0.0
    s = str(s).replace("$", "").replace(",", "").strip()
    if s in ("", "-"):
        return 0.0
    return float(s)


def _norm_headers(headers):
    return [h.strip().lower() for h in headers]


# ----------------------------------------------------------------------------
# Format detection
# ----------------------------------------------------------------------------
def detect(headers) -> str:
    h = set(_norm_headers(headers))
    if "franking credit" in h or "franked %" in h or "franked amount" in h:
        return "statement"
    if "details" in h and any(c.startswith("debit") for c in h):
        return "commsec"
    if "symbol" in h and ("side" in h or "fx rate" in h):
        return "stake"
    if "instrument code" in h or ("trade date" in h and "transaction type" in h):
        return "sharesight"
    if "code" in h and "units" in h and ("type" in h or "buy/sell" in h):
        return "selfwealth"
    return "unknown"


# ----------------------------------------------------------------------------
# Adapters
# ----------------------------------------------------------------------------
_CS_TRADE = re.compile(r"^\s*([BS])\s+([\d,]+)\s+([A-Z0-9]{2,6})\s+@\s+\$?([\d.]+)", re.I)
_CS_DIV = re.compile(r"\bDIV(?:IDEND)?\b\s+([A-Z0-9]{2,6})", re.I)
_CS_DRP_ALLOT = re.compile(r"\bDRP\b.*?([\d,]+)\s+([A-Z0-9]{2,6})\s+@\s+\$?([\d.]+)", re.I)
_CS_DRP = re.compile(r"\bDRP\b", re.I)


def _adapt_commsec(rows, res: ImportResult):
    """CommSec transaction export: Date, Reference, Details, Debit($), Credit($), Balance($).
    Brokerage is not a separate column — it is embedded in the cash amount, so we
    derive it: buy brokerage = debit - qty*price; sell brokerage = qty*price - credit."""
    for i, r in enumerate(rows, start=2):
        details = (r.get("details") or "").strip()
        debit, credit = _num(r.get("debit($)") or r.get("debit")), _num(r.get("credit($)") or r.get("credit"))
        try:
            dt = parse_date(r.get("date"))
        except ValueError as e:
            res.flag(i, str(e), details); continue

        m = _CS_TRADE.match(details)
        if m:
            side, qty, code, price = m.group(1).upper(), _num(m.group(2)), m.group(3).upper(), float(m.group(4))
            if side == "B":
                brokerage = round(debit - qty * price, 2)
                action = "BUY"
            else:
                brokerage = round(qty * price - credit, 2)
                action = "SELL"
            if brokerage < -0.01:
                res.flag(i, f"negative implied brokerage ({brokerage}) — check row", details)
            res.trades.append(dict(date=dt, ticker=code, action=action, qty=qty,
                                   price=price, brokerage=max(brokerage, 0.0), fx=1.0))
            continue
        md_drp = _CS_DRP_ALLOT.search(details)
        if md_drp:
            qty, code, price = _num(md_drp.group(1)), md_drp.group(2).upper(), float(md_drp.group(3))
            res.trades.append(dict(date=dt, ticker=code, action="BUY", qty=qty,
                                   price=price, brokerage=0.0, fx=1.0, note="DRP"))
            res.flag(i, f"DRP allotment imported as new parcel: {qty:.0f} {code} @ {price} "
                        f"(cost base ${qty*price:,.2f}, acquired {dt:%d/%m/%Y})", details, severity="info")
            continue
        if _CS_DRP.search(details):
            res.flag(i, "DRP line found but allotment qty/price not parseable", details)
            continue
        md = _CS_DIV.search(details)
        if md and credit > 0:
            franked = 1.0 if re.search(r"fully\s+franked", details, re.I) else 1.0
            res.dividends.append(dict(date=dt, ticker=md.group(1).upper(), cash=credit,
                                      franking=franked, withholding=0.0, fx=1.0))
            if not re.search(r"franked", details, re.I):
                res.flag(i, f"dividend franking % not in export — assumed fully franked ({md.group(1)})", details)
            continue
        if debit or credit:
            res.flag(i, "unrecognised cash movement (fee/interest/transfer?)", details)


def _adapt_stake(rows, res: ImportResult):
    """Stake (US) export: Date, Type, Side, Symbol, Units, Price (USD), Brokerage (USD),
    FX Rate, ... Amounts in USD; FX Rate converts to AUD."""
    for i, r in enumerate(rows, start=2):
        try:
            dt = parse_date(r.get("date"))
        except ValueError as e:
            res.flag(i, str(e), str(r)); continue
        typ = (r.get("type") or "").strip().lower()
        sym = (r.get("symbol") or "").strip().upper()
        fx = _num(r.get("fx rate") or r.get("fx")) or 1.0
        if typ in ("trade", "buy", "sell", "order") or (r.get("side") or "").strip():
            side = (r.get("side") or typ).strip().lower()
            action = "BUY" if "buy" in side else "SELL" if "sell" in side else None
            if action is None:
                res.flag(i, f"could not determine buy/sell ('{side}')", str(r)); continue
            res.trades.append(dict(date=dt, ticker=sym, action=action,
                                   qty=_num(r.get("units") or r.get("quantity")),
                                   price=_num(r.get("price (usd)") or r.get("price")),
                                   brokerage=_num(r.get("brokerage (usd)") or r.get("brokerage")),
                                   fx=fx))
        elif "div" in typ:
            res.dividends.append(dict(date=dt, ticker=sym,
                                      cash=_num(r.get("amount (usd)") or r.get("amount") or r.get("price")),
                                      franking=0.0,
                                      withholding=_num(r.get("withholding (usd)") or r.get("withholding")),
                                      fx=fx))
        else:
            res.flag(i, f"unhandled Stake row type '{typ}'", str(r))


def _adapt_sharesight(rows, res: ImportResult):
    """Canonical Sharesight-style template: Trade Date, Instrument Code, Market Code,
    Quantity, Price, Transaction Type, Brokerage, Exchange Rate."""
    for i, r in enumerate(rows, start=2):
        try:
            dt = parse_date(r.get("trade date") or r.get("date"))
        except ValueError as e:
            res.flag(i, str(e), str(r)); continue
        action = (r.get("transaction type") or "").strip().upper()
        if action not in ("BUY", "SELL"):
            res.flag(i, f"unknown transaction type '{action}'", str(r)); continue
        ex_rate = _num(r.get("exchange rate") or r.get("fx")) or 1.0
        res.trades.append(dict(date=dt, ticker=(r.get("instrument code") or r.get("code")).strip().upper(),
                               action=action, qty=_num(r.get("quantity")), price=_num(r.get("price")),
                               brokerage=_num(r.get("brokerage")), fx=ex_rate))


def _adapt_selfwealth(rows, res: ImportResult):
    """SelfWealth trades export: Date, Type, Code, Units, Price, Brokerage, ... (AUD)."""
    for i, r in enumerate(rows, start=2):
        try:
            dt = parse_date(r.get("date") or r.get("trade date"))
        except ValueError as e:
            res.flag(i, str(e), str(r)); continue
        typ = (r.get("type") or r.get("buy/sell") or "").strip().upper()
        action = "BUY" if typ.startswith("B") else "SELL" if typ.startswith("S") else None
        if action is None:
            res.flag(i, f"unknown trade type '{typ}'", str(r)); continue
        res.trades.append(dict(date=dt, ticker=(r.get("code")).strip().upper(), action=action,
                               qty=_num(r.get("units") or r.get("quantity")), price=_num(r.get("price")),
                               brokerage=_num(r.get("brokerage")), fx=1.0))


def _adapt_statement(rows, res: ImportResult):
    """Annual dividend / tax statement — the authoritative source of franking.
    Columns: Date, Code, Cash, Franked %, Franking Credit. The franking credit
    is taken directly when present, otherwise grossed up from the franked %."""
    GROSS = 0.30 / 0.70
    for i, r in enumerate(rows, start=2):
        try:
            dt = parse_date(r.get("date"))
        except ValueError as e:
            res.flag(i, str(e), str(r)); continue
        cash = _num(r.get("cash") or r.get("amount") or r.get("net dividend"))
        fc_col = r.get("franking credit") or r.get("franking credits")
        franked_pct = r.get("franked %")
        if fc_col not in (None, ""):
            franking_credit = _num(fc_col)
        elif franked_pct not in (None, ""):
            franking_credit = cash * (_num(franked_pct) / 100.0) * GROSS
        else:
            franking_credit = 0.0
            res.flag(i, "no franking data on statement row", str(r))
        res.dividends.append(dict(date=dt, ticker=(r.get("code") or r.get("ticker")).strip().upper(),
                                  cash=cash, franking=0.0, withholding=0.0, fx=1.0,
                                  franking_credit=round(franking_credit, 2)))


_ADAPTERS = {"commsec": _adapt_commsec, "stake": _adapt_stake,
             "sharesight": _adapt_sharesight, "selfwealth": _adapt_selfwealth,
             "statement": _adapt_statement}


# ----------------------------------------------------------------------------
def import_file(path: str, broker: str = None) -> ImportResult:
    with open(path, newline="") as f:
        reader = csv.reader(f)
        rows = [row for row in reader if any(c.strip() for c in row)]
    if not rows:
        return ImportResult("empty")
    headers = rows[0]
    broker = broker or detect(headers)
    res = ImportResult(broker)
    if broker == "unknown":
        res.flag(1, "could not detect broker format from headers", ", ".join(headers))
        return res
    keys = _norm_headers(headers)
    dict_rows = [dict(zip(keys, r)) for r in rows[1:]]
    _ADAPTERS[broker](dict_rows, res)
    res.trades.sort(key=lambda t: t["date"])
    return res


def merge(*results: ImportResult) -> ImportResult:
    out = ImportResult("merged")
    for r in results:
        out.trades += r.trades
        out.dividends += r.dividends
        out.review += [{**x, "broker": r.broker} for x in r.review]
    out.trades.sort(key=lambda t: t["date"])
    return out
