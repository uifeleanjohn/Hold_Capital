"""SnapTrade "connect your broker" — read-only aggregation.

Flow: register the user -> generate a connection-portal URL the user opens to
pick their broker and authenticate (we never see their password) -> pull their
account activities and turn them into trades.

Runs in STUB mode when SnapTrade keys are unset, so the whole flow (connect +
sync) is testable offline. Set SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY to
go live. NOTE: SnapTrade SDK response shapes vary by version — confirm the field
names in pull_trades() against your installed SDK before launch.
"""
from datetime import date, datetime

from . import config

STUB = not (config.SNAPTRADE_CLIENT_ID and config.SNAPTRADE_CONSUMER_KEY)


def _client():
    from snaptrade_client import SnapTrade
    return SnapTrade(client_id=config.SNAPTRADE_CLIENT_ID, consumer_key=config.SNAPTRADE_CONSUMER_KEY)


def _uid(user):
    return f"hc_{user.id}"


def register(user) -> str:
    """Return the user's SnapTrade userSecret, registering them if needed."""
    if user.snaptrade_user_secret:
        return user.snaptrade_user_secret
    if STUB:
        return f"stub-secret-{user.id}"
    resp = _client().authentication.register_snap_trade_user(body={"userId": _uid(user)})
    return resp.body["userSecret"]


def connect_url(user, user_secret: str) -> str:
    """Connection-portal URL the user opens to link their broker."""
    if STUB:
        return f"{config.PUBLIC_URL}/broker/stub-connect"
    resp = _client().authentication.login_snap_trade_user(
        query_params={"userId": _uid(user), "userSecret": user_secret})
    return resp.body.get("redirectURI")


def _parse_date(s):
    if isinstance(s, (date, datetime)):
        return s.date() if isinstance(s, datetime) else s
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(str(s)[:len("2025-01-01")], "%Y-%m-%d").date()
        except Exception:
            continue
    return date.today()


def pull_trades(user, user_secret: str) -> list:
    """Normalised trade dicts from the user's connected brokerage activities."""
    if STUB:
        return [
            {"date": date(2025, 11, 3), "ticker": "CBA", "action": "BUY", "qty": 50, "price": 130.0,
             "brokerage": 0.0, "fx": 1.0, "source_ref": "snaptrade-stub-1"},
            {"date": date(2026, 2, 10), "ticker": "WES", "action": "BUY", "qty": 30, "price": 75.0,
             "brokerage": 0.0, "fx": 1.0, "source_ref": "snaptrade-stub-2"},
        ]
    c = _client()
    qp = {"userId": _uid(user), "userSecret": user_secret}
    accounts = c.account_information.list_user_accounts(query_params=qp).body
    trades = []
    for acc in accounts:
        acts = c.account_information.get_user_account_activities(
            account_id=acc["id"], query_params=qp).body
        rows = acts.get("data", acts) if isinstance(acts, dict) else acts
        for a in rows:
            typ = (a.get("type") or "").upper()
            if typ not in ("BUY", "SELL"):
                continue
            sym = a.get("symbol")
            ticker = (sym.get("symbol") if isinstance(sym, dict) else sym) or "?"
            ticker = str(ticker).split(".")[0].upper()
            trades.append({
                "date": _parse_date(a.get("trade_date") or a.get("settlement_date")),
                "ticker": ticker, "action": typ, "qty": abs(float(a.get("units") or 0)),
                "price": float(a.get("price") or 0), "brokerage": abs(float(a.get("fee") or 0)),
                "fx": 1.0, "source_ref": "snaptrade-" + str(a.get("id")),
            })
    return trades
