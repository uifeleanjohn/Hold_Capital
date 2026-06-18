"""Bridge between stored data and the verified engine. Builds engine inputs
from a user's trades/dividends + cached prices, runs the engine, and returns a
JSON-serialisable dashboard."""
from .core import engine
from . import refdata
from .models import PriceCache


def _securities(db, tickers):
    prices = {p.ticker: p for p in db.query(PriceCache).all()}
    secs = {}
    for tk in tickers:
        name, exch, tag, ccy, seed_px, seed_fx = refdata.meta(tk)
        pc = prices.get(tk)
        px = pc.price if pc else seed_px
        fx = pc.fx if pc else seed_fx
        secs[tk] = engine.Security(tk, exch, name, "Equity", tag, ccy, px, fx)
    return secs


def compute(db, user, account=None):
    """Raw engine result (objects, not JSON) for the PDF report. Optionally
    filter to one portfolio; otherwise all portfolios."""
    raw_t = [t for t in user.trades if account is None or (t.account or "All holdings") == account]
    raw_d = [d for d in user.dividends if account is None or (d.account or "All holdings") == account]
    trades = [{"date": t.date, "ticker": t.ticker, "action": t.action, "qty": t.qty,
               "price": t.price, "brokerage": t.brokerage or 0.0, "fx": t.fx or 1.0} for t in raw_t]
    divs = []
    for d in raw_d:
        row = {"date": d.date, "ticker": d.ticker, "cash": d.cash, "franking": d.franking or 0.0,
               "withholding": d.withholding or 0.0, "fx": d.fx or 1.0}
        if d.franking_credit is not None:
            row["franking_credit"] = d.franking_credit
        divs.append(row)
    statement = [d for d in divs if "franking_credit" in d]
    if statement:
        divs = statement + [d for d in divs if "franking_credit" not in d and d["fx"] != 1.0]
    secs = _securities(db, {t["ticker"] for t in trades} | {d["ticker"] for d in divs})
    acct = engine.Account(other_income=user.other_income)
    events, open_parcels = engine.match_parcels(secs, trades, acct)
    cgt = engine.compute_cgt(events, acct)
    income = engine.compute_income(divs, acct)
    tax = engine.estimate_tax(cgt, income, acct)
    xray = engine.exposure_xray(secs, open_parcels)
    actions = engine.optimise(secs, open_parcels, cgt, acct)
    return {"account": acct, "cgt": cgt, "income": income, "tax": tax, "xray": xray,
            "actions": actions, "portfolio_label": account or "All portfolios"}


def run_dashboard(db, user):
    trades = [{"date": t.date, "ticker": t.ticker, "action": t.action, "qty": t.qty,
               "price": t.price, "brokerage": t.brokerage or 0.0, "fx": t.fx or 1.0} for t in user.trades]
    divs = []
    for d in user.dividends:
        row = {"date": d.date, "ticker": d.ticker, "cash": d.cash, "franking": d.franking or 0.0,
               "withholding": d.withholding or 0.0, "fx": d.fx or 1.0}
        if d.franking_credit is not None:
            row["franking_credit"] = d.franking_credit
        divs.append(row)

    # An annual statement (explicit franking_credit) is authoritative for AU
    # dividends; keep statement rows + any foreign (fx != 1) broker rows, and
    # drop broker-derived AU rows to avoid double-counting.
    statement = [d for d in divs if "franking_credit" in d]
    if statement:
        divs = statement + [d for d in divs if "franking_credit" not in d and d["fx"] != 1.0]

    tickers = {t["ticker"] for t in trades} | {d["ticker"] for d in divs}
    secs = _securities(db, tickers)
    acct = engine.Account(other_income=user.other_income)

    events, open_parcels = engine.match_parcels(secs, trades, acct)
    cgt = engine.compute_cgt(events, acct)
    income = engine.compute_income(divs, acct)
    tax = engine.estimate_tax(cgt, income, acct)
    xray = engine.exposure_xray(secs, open_parcels)
    actions = engine.optimise(secs, open_parcels, cgt, acct)

    positions = []
    for tk, lots in open_parcels.items():
        qty = sum(l.qty_open for l in lots)
        if qty <= 1e-9:
            continue
        sec = secs[tk]
        value = qty * sec.current_price * sec.current_fx
        cost = sum(l.qty_open * l.unit_cost_aud for l in lots)
        positions.append({"ticker": tk, "name": sec.name, "qty": round(qty, 2),
                          "value": round(value, 2), "cost": round(cost, 2),
                          "unrealised": round(value - cost, 2)})

    return {
        "net_capital_gain": round(cgt["net_capital_gain"], 2),
        "gross_gains": round(cgt["gross_gains"], 2),
        "losses": round(cgt["losses"], 2),
        "discount": round(cgt["discount"], 2),
        "income": {k: round(v, 2) for k, v in income.items()},
        "estimated_net_tax": round(tax["net_tax"], 2),
        "exposure": {"total": round(xray["total"], 2),
                     "tags": [{"tag": t["tag"], "value": round(t["value"], 2),
                               "weight": round(t["weight"], 4)} for t in xray["tags"]],
                     "resources_weight": round(xray["resources_weight"], 4)},
        "positions": sorted(positions, key=lambda p: -p["value"]),
        "actions": [{"kind": a["kind"], "ticker": a["ticker"], "name": a["name"],
                     "saving": round(a["saving"], 2), "detail": a["detail"]} for a in actions],
        "closed_trades": [{"ticker": e.ticker, "name": e.name, "acquired": e.acquired.isoformat(),
                           "disposed": e.disposed.isoformat(), "days_held": e.days_held,
                           "pnl": round(e.gain, 2), "discountable": e.discountable} for e in events],
    }
