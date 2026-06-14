"""HoldCapital API — Phase A.
Auth, portfolio (import/manual), price refresh, and an engine-backed dashboard."""
import os
import secrets
import tempfile
from datetime import date

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from .db import get_db, init_db
from .models import User, Trade, Dividend, PriceCache, JournalNote
from . import auth, bridge, marketdata, billing, config, email_parser, broker
from .core import importer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE, "web")

app = FastAPI(title="HoldCapital API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if config.CORS_ORIGINS == "*" else config.CORS_ORIGINS.split(","),
    allow_methods=["*"], allow_headers=["*"], allow_credentials=False,
)
if os.path.isdir(WEB_DIR):
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/")
def index():
    idx = os.path.join(WEB_DIR, "index.html")
    return FileResponse(idx) if os.path.exists(idx) else {"app": "HoldCapital API", "docs": "/docs"}


def require_tier(*allowed):
    def dep(user: User = Depends(auth.current_user)) -> User:
        if user.tier not in allowed:
            raise HTTPException(402, f"Requires {' or '.join(allowed)} plan")
        return user
    return dep


# ---------- schemas ----------
class Credentials(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    token: str

class TradeIn(BaseModel):
    date: date
    ticker: str
    action: str
    qty: float
    price: float
    brokerage: float = 0.0
    fx: float = 1.0

class ImportIn(BaseModel):
    files: list[str]          # raw CSV texts (broker exports / statement)

class IncomeIn(BaseModel):
    other_income: float | None = None


# ---------- auth ----------
@app.post("/auth/signup", response_model=TokenOut)
def signup(c: Credentials, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == c.email).first():
        raise HTTPException(400, "Email already registered")
    u = User(email=c.email, password_hash=auth.hash_password(c.password))
    db.add(u); db.commit(); db.refresh(u)
    return {"token": auth.create_token(u.id)}


@app.post("/auth/login", response_model=TokenOut)
def login(c: Credentials, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == c.email).first()
    if not u or not auth.verify_password(c.password, u.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return {"token": auth.create_token(u.id)}


@app.get("/me")
def me(user: User = Depends(auth.current_user)):
    return {"id": user.id, "email": user.email, "other_income": user.other_income,
            "tier": user.tier, "subscription_status": user.subscription_status}


@app.post("/me/income")
def set_income(body: IncomeIn, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    user.other_income = body.other_income; db.add(user); db.commit()
    return {"other_income": user.other_income}


# ---------- portfolio ----------
@app.post("/portfolio/trade")
def add_trade(t: TradeIn, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    db.add(Trade(user_id=user.id, date=t.date, ticker=t.ticker.upper(), action=t.action.upper(),
                 qty=t.qty, price=t.price, brokerage=t.brokerage, fx=t.fx, source="manual"))
    db.commit()
    return {"ok": True}


@app.post("/portfolio/import")
def import_csv(body: ImportIn, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    added_t = added_d = 0
    review = []
    for text in body.files:
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(text); path = f.name
        try:
            res = importer.import_file(path)
        finally:
            os.unlink(path)
        for tr in res.trades:
            db.add(Trade(user_id=user.id, date=tr["date"], ticker=tr["ticker"], action=tr["action"],
                         qty=tr["qty"], price=tr["price"], brokerage=tr.get("brokerage", 0.0),
                         fx=tr.get("fx", 1.0), source=res.broker)); added_t += 1
        for dv in res.dividends:
            db.add(Dividend(user_id=user.id, date=dv["date"], ticker=dv["ticker"], cash=dv["cash"],
                            franking=dv.get("franking", 0.0), franking_credit=dv.get("franking_credit"),
                            withholding=dv.get("withholding", 0.0), fx=dv.get("fx", 1.0))); added_d += 1
        review += [{"broker": res.broker, **r} for r in res.review]
    db.commit()
    return {"trades_added": added_t, "dividends_added": added_d, "review": review}


@app.get("/portfolio")
def portfolio(user: User = Depends(auth.current_user)):
    return {
        "trades": [{"date": t.date.isoformat(), "ticker": t.ticker, "action": t.action,
                    "qty": t.qty, "price": t.price, "brokerage": t.brokerage or 0.0,
                    "fx": t.fx or 1.0, "source": t.source} for t in user.trades],
        "dividends": [{"date": d.date.isoformat(), "ticker": d.ticker, "cash": d.cash,
                       "franking": d.franking or 0.0, "franking_credit": d.franking_credit,
                       "withholding": d.withholding or 0.0, "fx": d.fx or 1.0} for d in user.dividends],
    }


# ---------- billing ----------
class CheckoutIn(BaseModel):
    tier: str          # plus | pro

@app.post("/billing/checkout")
def billing_checkout(body: CheckoutIn, user: User = Depends(auth.current_user)):
    try:
        return billing.create_checkout(user, body.tier)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/billing/status")
def billing_status(user: User = Depends(auth.current_user)):
    return {"tier": user.tier, "status": user.subscription_status, "stub_mode": billing.STUB}

@app.get("/billing/stub-checkout")
def billing_stub(tier: str, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    """Stub-mode only: simulate a successful subscription so the flow is testable."""
    if not billing.STUB:
        raise HTTPException(404, "Not available")
    user.tier = tier if tier in ("plus", "pro") else user.tier
    user.subscription_status = "active"
    db.add(user); db.commit()
    return RedirectResponse(url=f"/?upgraded={tier}")

@app.post("/billing/webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        info = billing.parse_webhook(payload, sig)
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {e}")
    if info.get("user_id"):
        u = db.get(User, int(info["user_id"]))
        if u:
            if info.get("tier"):
                u.tier = info["tier"]
            u.subscription_status = info.get("status")
            if info.get("customer_id"):
                u.stripe_customer_id = info["customer_id"]
            db.add(u); db.commit()
    return {"received": True}


# ---------- example gated (Pro) endpoint ----------
@app.get("/pro/edge")
def pro_edge(user: User = Depends(require_tier("plus", "pro")), db: Session = Depends(get_db)):
    """Demonstrates feature gating — Pro/Plus only."""
    d = bridge.run_dashboard(db, user)
    return {"actions": d["actions"], "note": "parcel optimiser + pre-EOFY actions (paid tier)"}


# ---------- broker auto-sync (email forwarding) ----------
def _user_address(user) -> str:
    return f"{config.INBOUND_LOCALPART}+{user.inbox_token}@{config.INBOUND_DOMAIN}"

@app.get("/inbox/address")
def inbox_address(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    if not user.inbox_token:
        user.inbox_token = secrets.token_hex(8); db.add(user); db.commit()
    recent = (db.query(Trade).filter(Trade.user_id == user.id, Trade.source.like("email:%"))
              .order_by(Trade.id.desc()).limit(10).all())
    return {
        "address": _user_address(user),
        "instructions": ("Forward your broker trade-confirmation emails to this address, or set it as a "
                         "CC/notification address in your broker so new contract notes arrive automatically."),
        "recent": [{"date": t.date.isoformat(), "ticker": t.ticker, "action": t.action,
                    "qty": t.qty, "price": t.price, "source": t.source} for t in recent],
    }

@app.post("/inbox/webhook")
async def inbox_webhook(request: Request, db: Session = Depends(get_db)):
    """Inbound-email provider (e.g. Postmark) posts parsed emails here."""
    if config.INBOUND_WEBHOOK_SECRET and request.query_params.get("secret") != config.INBOUND_WEBHOOK_SECRET:
        raise HTTPException(403, "bad secret")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "expected a JSON inbound-email payload")
    token = payload.get("MailboxHash") or ""
    if not token:                                  # fall back to parsing the To address
        to = payload.get("To") or (payload.get("ToFull") or [{}])[0].get("Email", "")
        m = __import__("re").search(r"\+([0-9a-f]{8,32})@", to or "")
        token = m.group(1) if m else ""
    user = db.query(User).filter_by(inbox_token=token).first()
    if not user:
        raise HTTPException(404, "unknown inbox address")
    subject = payload.get("Subject", "")
    text = payload.get("TextBody") or payload.get("StrippedTextReply") or payload.get("HtmlBody", "")
    from_email = (payload.get("FromFull") or {}).get("Email") or payload.get("From", "")
    res = email_parser.parse(subject, text, from_email)
    added = skipped = 0
    for t in res["trades"]:
        ref = t.get("source_ref")
        if ref and db.query(Trade).filter_by(user_id=user.id, source_ref=ref).first():
            skipped += 1; continue
        db.add(Trade(user_id=user.id, date=t["date"], ticker=t["ticker"], action=t["action"],
                     qty=t["qty"], price=t["price"], brokerage=t.get("brokerage", 0.0),
                     fx=t.get("fx", 1.0), source="email:" + res["broker"], source_ref=ref))
        added += 1
    db.commit()
    return {"broker": res["broker"], "added": added, "skipped": skipped, "review": res["review"]}


# ---------- connect your broker (SnapTrade) ----------
@app.get("/broker/status")
def broker_status(user: User = Depends(auth.current_user)):
    return {"connected": bool(user.snaptrade_user_secret), "stub_mode": broker.STUB}

@app.post("/broker/connect")
def broker_connect(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    """Register the user with SnapTrade and return the connection-portal URL."""
    secret = broker.register(user)
    if user.snaptrade_user_secret != secret:
        user.snaptrade_user_secret = secret; db.add(user); db.commit()
    return {"url": broker.connect_url(user, secret), "stub_mode": broker.STUB}

@app.post("/broker/sync")
def broker_sync(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    """Pull read-only activities from the connected broker and import as trades."""
    secret = user.snaptrade_user_secret or broker.register(user)
    user.snaptrade_user_secret = secret
    added = skipped = 0
    for t in broker.pull_trades(user, secret):
        ref = t.get("source_ref")
        if ref and db.query(Trade).filter_by(user_id=user.id, source_ref=ref).first():
            skipped += 1; continue
        db.add(Trade(user_id=user.id, date=t["date"], ticker=t["ticker"], action=t["action"],
                     qty=t["qty"], price=t["price"], brokerage=t.get("brokerage", 0.0),
                     fx=t.get("fx", 1.0), source="snaptrade", source_ref=ref))
        added += 1
    db.add(user); db.commit()
    return {"added": added, "skipped": skipped}

@app.get("/broker/stub-connect")
def broker_stub_connect():
    if not broker.STUB:
        raise HTTPException(404)
    return FileResponse(os.path.join(WEB_DIR, "stub_connect.html")) if os.path.exists(
        os.path.join(WEB_DIR, "stub_connect.html")) else {"message": "Demo broker connected — go back and click Sync."}


# ---------- prices ----------
@app.post("/prices/refresh")
def refresh(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    tickers = {t.ticker for t in user.trades} | {d.ticker for d in user.dividends}
    return marketdata.refresh_prices(db, tickers)


@app.get("/prices")
def prices(db: Session = Depends(get_db), user: User = Depends(auth.current_user)):
    return [{"ticker": p.ticker, "price": p.price, "fx": p.fx, "currency": p.currency,
             "asof": p.asof.isoformat()} for p in db.query(PriceCache).all()]


# ---------- journal notes (server-side) ----------
class JournalIn(BaseModel):
    trade_key: str
    setup: str | None = None
    confidence: int | None = None
    notes: str | None = None

@app.get("/journal")
def get_journal(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    notes = db.query(JournalNote).filter(JournalNote.user_id == user.id).all()
    return [{"trade_key": n.trade_key, "setup": n.setup, "confidence": n.confidence, "notes": n.notes} for n in notes]

@app.post("/journal")
def upsert_journal(body: JournalIn, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    n = db.query(JournalNote).filter_by(user_id=user.id, trade_key=body.trade_key).first()
    if n is None:
        n = JournalNote(user_id=user.id, trade_key=body.trade_key)
        db.add(n)
    n.setup, n.confidence, n.notes = body.setup, body.confidence, body.notes
    db.commit()
    return {"ok": True}


# ---------- dashboard ----------
@app.get("/dashboard")
def dashboard(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    return bridge.run_dashboard(db, user)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
