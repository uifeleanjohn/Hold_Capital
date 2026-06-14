"""End-to-end smoke test: sign up -> import sample CSVs -> refresh prices ->
fetch the dashboard, and assert the engine's number flows through the API."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# use a throwaway sqlite db in the temp dir for the test
_dbpath = os.path.join(tempfile.gettempdir(), f"hc_smoke_{os.getpid()}.db")
os.environ["DATABASE_URL"] = "sqlite:///" + _dbpath
try:
    os.remove(_dbpath)
except OSError:
    pass

from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db
init_db()   # create tables for the test db

SAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "samples")
def read(f): return open(os.path.join(SAMPLES, f)).read()

c = TestClient(app)

tok = c.post("/auth/signup", json={"email": "john@example.com", "password": "hunter2pw"}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}
print("signed up + token issued")

c.post("/me/income", headers=H, json={"other_income": 120000})

imp = c.post("/portfolio/import", headers=H, json={"files": [
    read("commsec_transactions.csv"), read("stake_transactions.csv"), read("dividend_statement.csv")]}).json()
print(f"imported: {imp['trades_added']} trades, {imp['dividends_added']} dividends, {len(imp['review'])} flagged")

# add a crypto + a physical-bullion holding by hand (the "brother's gold" case)
c.post("/portfolio/trade", headers=H, json={"date": "2024-02-01", "ticker": "BTC", "action": "BUY", "qty": 0.5, "price": 90000, "fx": 1.0})
c.post("/portfolio/trade", headers=H, json={"date": "2023-06-01", "ticker": "XAU", "action": "BUY", "qty": 10, "price": 3000, "fx": 1.0})
print("added 0.5 BTC and 10 oz gold manually")

ref = c.post("/prices/refresh", headers=H).json()
print(f"prices refreshed: {ref['updated']} tickers (source: {ref['source']})")

d = c.get("/dashboard", headers=H).json()
tags = {t["tag"]: t["value"] for t in d["exposure"]["tags"]}
print(f"  exposure now includes: {', '.join(tags.keys())}")
print("\nDASHBOARD via API:")
print(f"  net capital gain : ${d['net_capital_gain']:,.2f}")
print(f"  franking credits : ${d['income']['franking']:,.2f}")
print(f"  estimated net tax: ${d['estimated_net_tax']:,.2f}")
print(f"  exposure total   : ${d['exposure']['total']:,.0f} ({d['exposure']['resources_weight']*100:.0f}% resources)")
print(f"  open positions   : {len(d['positions'])}, closed trades: {len(d['closed_trades'])}, actions: {len(d['actions'])}")

has_crypto = "Crypto" in tags and "Precious metals" in tags

# ---- billing + tiers + served front-end ----
print("\nBILLING + FRONT-END:")
who = c.get("/me", headers=H).json()
print(f"  starting tier: {who['tier']}")
co = c.post("/billing/checkout", headers=H, json={"tier": "pro"}).json()
print(f"  checkout ({co['mode']} mode) -> {co['url']}")
# in stub mode, follow the stub checkout to simulate a successful subscription
c.get("/billing/stub-checkout", headers=H, params={"tier": "pro"}, follow_redirects=False)
who2 = c.get("/me", headers=H).json()
print(f"  tier after checkout: {who2['tier']} ({who2['subscription_status']})")
edge = c.get("/pro/edge", headers=H).status_code     # gated endpoint, now allowed
root = c.get("/")                                     # served front-end
ptf = c.get("/portfolio", headers=H).json()
has_fields = all(k in ptf["trades"][0] for k in ("brokerage", "fx"))
print(f"  gated /pro/edge: {edge} | served '/' : {root.status_code} | portfolio has brokerage/fx: {has_fields}")

# ---- hardening checks: bcrypt + server-side journal notes ----
print("\nHARDENING:")
import app.auth as A
is_bcrypt = A.hash_password("x").startswith("$2")
wrong_pw = c.post("/auth/login", json={"email": "john@example.com", "password": "WRONGpass"}).status_code
key = d["closed_trades"][0]["ticker"] + "|" + d["closed_trades"][0]["acquired"] + "|" + d["closed_trades"][0]["disposed"]
c.post("/journal", headers=H, json={"trade_key": key, "setup": "US large-cap hold", "confidence": 5, "notes": "core position"})
notes = c.get("/journal", headers=H).json()
saved = any(n["trade_key"] == key and n["setup"] == "US large-cap hold" for n in notes)
print(f"  bcrypt hashing: {is_bcrypt} | wrong password rejected: {wrong_pw == 401} | journal note saved server-side: {saved}")

ok = (abs(d["net_capital_gain"] - 3668.68) < 0.01 and imp["trades_added"] == 16 and has_crypto
      and who2["tier"] == "pro" and edge == 200 and root.status_code == 200 and has_fields
      and is_bcrypt and wrong_pw == 401 and saved)
print("\nVERIFY (engine + crypto + billing + UI + hardening):", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
