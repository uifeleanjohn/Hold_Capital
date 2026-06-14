"""
HoldCapital engine
==================
One canonical object — the Parcel — feeds every lens:
  * CGT engine        -> realised capital gains, 50% discount, loss ordering
  * Exposure x-ray    -> commodity / sector weighting of what you still hold
  * Pre-EOFY optimiser -> dated actions before 30 June

All money is normalised to AUD at trade-date FX as it enters the engine.
This is a prototype: assumptions are explicit and documented inline.
"""

from __future__ import annotations
import csv
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from collections import defaultdict

COMPANY_TAX_RATE = 0.30          # franking gross-up basis (standard franking rate)
MEDICARE_LEVY = 0.02
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Resident individual rates for FY2025-26 (the revised Stage-3 scale).
ATO_BRACKETS_2025_26 = [
    (0,      18200,    0.00),
    (18200,  45000,    0.16),
    (45000,  135000,   0.30),
    (135000, 190000,   0.37),
    (190000, float("inf"), 0.45),
]


def income_tax(taxable: float, brackets=ATO_BRACKETS_2025_26) -> float:
    """Progressive income tax (excl. Medicare levy)."""
    tax = 0.0
    for lo, hi, rate in brackets:
        if taxable > lo:
            tax += (min(taxable, hi) - lo) * rate
    return tax


# ----------------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------------
@dataclass
class Security:
    ticker: str
    exchange: str
    name: str
    asset_class: str
    tag: str                     # commodity / sector for the exposure x-ray
    currency: str
    current_price: float
    current_fx: float            # AUD per 1 unit of local currency


@dataclass
class Parcel:
    """An open buy lot. Quantity is reduced as it is matched to disposals."""
    ticker: str
    acquired: date
    qty: float
    unit_cost_aud: float         # cost base per share, in AUD (incl. apportioned brokerage)
    qty_open: float = field(init=False)

    def __post_init__(self):
        self.qty_open = self.qty


@dataclass
class Account:
    entity: str = "individual"   # individual | trust | smsf | company
    marginal_rate: float = 0.37
    medicare: float = MEDICARE_LEVY
    other_income: float = None   # salary etc.; if set, brackets are used instead of flat rate
    fy_start: date = date(2025, 7, 1)
    fy_end: date = date(2026, 6, 30)
    today: date = date(2026, 6, 13)

    @property
    def discount_rate(self) -> float:
        return {"individual": 0.5, "trust": 0.5, "smsf": 1/3, "company": 0.0}[self.entity]

    @property
    def effective_rate(self) -> float:
        return self.marginal_rate + self.medicare

    def marginal_tax_on(self, extra: float) -> float:
        """Tax on `extra` income stacked on top of other_income, using ATO
        brackets + Medicare. Falls back to the flat effective rate if no
        other_income is set."""
        if self.other_income is None:
            return extra * self.effective_rate
        base = self.other_income
        t0 = income_tax(base) + base * MEDICARE_LEVY
        t1 = income_tax(base + extra) + (base + extra) * MEDICARE_LEVY
        return t1 - t0


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------
def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def load(data_dir: str = DATA_DIR):
    secs = {}
    with open(os.path.join(data_dir, "securities.csv")) as f:
        for r in csv.DictReader(f):
            secs[r["ticker"]] = Security(
                r["ticker"], r["exchange"], r["name"], r["asset_class"], r["tag"],
                r["currency"], float(r["current_price"]), float(r["current_fx"]))
    trades = []
    with open(os.path.join(data_dir, "trades.csv")) as f:
        for r in csv.DictReader(f):
            trades.append(dict(date=_d(r["date"]), ticker=r["ticker"], action=r["action"],
                               qty=float(r["qty"]), price=float(r["price"]),
                               brokerage=float(r["brokerage"]), fx=float(r["fx"])))
    divs = []
    with open(os.path.join(data_dir, "dividends.csv")) as f:
        for r in csv.DictReader(f):
            divs.append(dict(date=_d(r["date"]), ticker=r["ticker"], cash=float(r["cash"]),
                             franking=float(r["franking"]), withholding=float(r["withholding"]),
                             fx=float(r["fx"])))
    trades.sort(key=lambda t: t["date"])
    return secs, trades, divs


# ----------------------------------------------------------------------------
# Parcel matching  ->  realised CGT events + remaining open parcels
# ----------------------------------------------------------------------------
@dataclass
class CGTEvent:
    ticker: str
    name: str
    acquired: date
    disposed: date
    qty: float
    cost_base: float
    proceeds: float
    gain: float
    days_held: int
    discountable: bool


def apply_split(parcels: deque, ratio: float):
    """A share split (ratio:1) multiplies units and divides unit cost.
    Total cost base and the original acquisition date are preserved — the
    12-month discount clock keeps running from the original purchase."""
    for p in parcels:
        p.qty *= ratio
        p.qty_open *= ratio
        p.unit_cost_aud /= ratio


def match_parcels(secs, trades, account, method="fifo", corporate_actions=None):
    """Consume buy parcels against sells. Returns (events, open_parcels).

    corporate_actions: optional list of {date, ticker, type:'split', ratio}.
    Trades and actions are processed together in date order so a split adjusts
    the parcels that exist at the split date before any later disposal."""
    open_parcels: dict[str, list] = defaultdict(list)
    events: list[CGTEvent] = []

    timeline = [("trade", t) for t in trades]
    timeline += [("action", a) for a in (corporate_actions or [])]
    timeline.sort(key=lambda x: x[1]["date"])

    for kind, t in timeline:
        if kind == "action":
            if t["type"] == "split":
                apply_split(open_parcels[t["ticker"]], t["ratio"])
            continue

        sec = secs[t["ticker"]]
        if t["action"] == "BUY":
            unit_cost = (t["qty"] * t["price"] + t["brokerage"]) * t["fx"] / t["qty"]
            open_parcels[t["ticker"]].append(
                Parcel(t["ticker"], t["date"], t["qty"], unit_cost))
            continue

        # SELL — apportion sale proceeds (net of brokerage) across matched lots
        qty_to_sell = t["qty"]
        net_unit_proceeds = t["price"] * t["fx"] - (t["brokerage"] * t["fx"]) / t["qty"]
        lots = open_parcels[t["ticker"]]

        def taxable_per_unit(lot):
            """After-discount taxable contribution per unit — losses are most
            negative, discounted gains count at half. Selling these first
            minimises the taxable gain (specific identification)."""
            held = (t["date"] - lot.acquired).days
            g = net_unit_proceeds - lot.unit_cost_aud
            if g > 0 and held > 365 and account.discount_rate > 0:
                return g * (1 - account.discount_rate)
            return g

        order = list(lots) if method == "fifo" else sorted(lots, key=taxable_per_unit)
        for lot in order:
            if qty_to_sell <= 1e-9:
                break
            take = min(lot.qty_open, qty_to_sell)
            cost = take * lot.unit_cost_aud
            proceeds = take * net_unit_proceeds
            held = (t["date"] - lot.acquired).days
            gain = proceeds - cost
            events.append(CGTEvent(
                ticker=t["ticker"], name=sec.name, acquired=lot.acquired,
                disposed=t["date"], qty=take, cost_base=cost, proceeds=proceeds,
                gain=gain, days_held=held,
                discountable=(held > 365 and gain > 0 and account.discount_rate > 0)))
            lot.qty_open -= take
            qty_to_sell -= take
        open_parcels[t["ticker"]] = [l for l in lots if l.qty_open > 1e-9]
    return events, open_parcels


# ----------------------------------------------------------------------------
# CGT engine  (ATO individual method)
# ----------------------------------------------------------------------------
def compute_cgt(events, account, carried_loss=0.0):
    fy = [e for e in events if account.fy_start <= e.disposed <= account.fy_end]

    disc_gains = sum(e.gain for e in fy if e.gain > 0 and e.discountable)
    nondisc_gains = sum(e.gain for e in fy if e.gain > 0 and not e.discountable)
    losses = -sum(e.gain for e in fy if e.gain < 0) + carried_loss
    gross_gains = disc_gains + nondisc_gains

    # Apply losses to NON-discount gains first to preserve the 50% discount.
    loss_pool = losses
    nondisc_after = nondisc_gains - min(loss_pool, nondisc_gains)
    loss_pool -= (nondisc_gains - nondisc_after)
    disc_after = disc_gains - min(loss_pool, disc_gains)
    loss_pool -= (disc_gains - disc_after)
    carry_forward = loss_pool                      # unused losses carry to next year

    discount = disc_after * account.discount_rate
    net_capital_gain = nondisc_after + (disc_after - discount)

    return dict(
        events=fy, disc_gains=disc_gains, nondisc_gains=nondisc_gains,
        gross_gains=gross_gains, losses=losses, gains_after_losses=nondisc_after + disc_after,
        disc_after=disc_after, discount=discount, net_capital_gain=net_capital_gain,
        carry_forward=carry_forward)


# ----------------------------------------------------------------------------
# Dividend income, franking & FITO
# ----------------------------------------------------------------------------
def _franking_credit(d):
    """Use the explicit franking credit from a tax statement when present;
    otherwise gross up from the franked proportion (default basis)."""
    if d.get("franking_credit") is not None:
        return d["franking_credit"]
    return d["cash"] * d["fx"] * d.get("franking", 0.0) * (COMPANY_TAX_RATE / (1 - COMPANY_TAX_RATE))


def compute_income(divs, account):
    fy = [d for d in divs if account.fy_start <= d["date"] <= account.fy_end]
    au_cash = sum(d["cash"] * d["fx"] for d in fy if d.get("withholding", 0) == 0 and d["fx"] == 1.0)
    franking = sum(_franking_credit(d) for d in fy if d["fx"] == 1.0)
    foreign_cash = sum(d["cash"] * d["fx"] for d in fy if d["fx"] != 1.0)
    fito = sum(d.get("withholding", 0) * d["fx"] for d in fy)
    return dict(au_cash=au_cash, franking=franking, foreign_cash=foreign_cash, fito=fito)


def estimate_tax(cgt, income, account):
    assessable = (cgt["net_capital_gain"] + income["au_cash"] + income["franking"] + income["foreign_cash"])
    gross_tax = account.marginal_tax_on(assessable)   # ATO brackets if other_income set, else flat
    offsets = income["franking"] + income["fito"]
    net_tax = gross_tax - offsets
    return dict(assessable=assessable, gross_tax=gross_tax, offsets=offsets, net_tax=net_tax)


# ----------------------------------------------------------------------------
# Exposure x-ray  (what you still hold, valued at current price)
# ----------------------------------------------------------------------------
def exposure_xray(secs, open_parcels):
    positions = []
    for ticker, lots in open_parcels.items():
        qty = sum(l.qty_open for l in lots)
        if qty <= 1e-9:
            continue
        sec = secs[ticker]
        value = qty * sec.current_price * sec.current_fx
        cost = sum(l.qty_open * l.unit_cost_aud for l in lots)
        positions.append(dict(ticker=ticker, name=sec.name, tag=sec.tag, exchange=sec.exchange,
                              qty=qty, value=value, cost=cost, unrealised=value - cost))
    total = sum(p["value"] for p in positions) or 1.0
    by_tag = defaultdict(float)
    for p in positions:
        by_tag[p["tag"]] += p["value"]
    tags = sorted(({"tag": k, "value": v, "weight": v / total} for k, v in by_tag.items()),
                  key=lambda x: -x["value"])
    resources = sum(v for k, v in by_tag.items()
                    if k in {"Iron ore", "Copper", "Gold", "Lithium", "Uranium"})
    return dict(positions=sorted(positions, key=lambda p: -p["value"]),
                total=total, tags=tags, resources_weight=resources / total)


# ----------------------------------------------------------------------------
# Pre-EOFY optimiser
# ----------------------------------------------------------------------------
def optimise(secs, open_parcels, cgt, account):
    actions = []
    # Pool of discount-eligible gain still exposed to fresh losses (pre-discount).
    pool = cgt["disc_after"]
    eff = account.marginal_tax_on(1000.0) / 1000.0   # marginal rate at the top of current income
    for ticker, lots in open_parcels.items():
        sec = secs[ticker]
        for lot in lots:
            if lot.qty_open <= 1e-9:
                continue
            value = lot.qty_open * sec.current_price * sec.current_fx
            cost = lot.qty_open * lot.unit_cost_aud
            unrealised = value - cost
            days_to_disc = (lot.acquired.replace(year=lot.acquired.year + 1) - account.today).days
            if unrealised < 0 and pool > 0:
                offset = min(-unrealised, pool)
                saving = offset * account.discount_rate * eff
                pool -= offset
                actions.append(dict(kind="harvest", ticker=ticker, name=sec.name,
                                    detail=f"Unrealised loss of {money(unrealised)}. Selling before 30 Jun "
                                           f"offsets discounted gains.", saving=saving))
            elif unrealised > 0 and 0 < days_to_disc <= 30:
                saving = unrealised * account.discount_rate * eff
                actions.append(dict(kind="wait", ticker=ticker, name=sec.name,
                                    detail=f"Crosses the 12-month line in {days_to_disc} days "
                                           f"({lot.acquired.replace(year=lot.acquired.year+1):%d %b %Y}). "
                                           f"Hold past it to unlock the 50% discount on ~{money(unrealised)}.",
                                    saving=saving))
    actions.sort(key=lambda a: -a["saving"])
    return actions


def money(x):
    return ("-$%s" % f"{abs(x):,.0f}") if x < 0 else ("$%s" % f"{x:,.0f}")


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------
def run(account=None, data_dir=DATA_DIR):
    account = account or Account()
    secs, trades, divs = load(data_dir)
    events, open_parcels = match_parcels(secs, trades, account)
    cgt = compute_cgt(events, account)
    income = compute_income(divs, account)
    tax = estimate_tax(cgt, income, account)
    xray = exposure_xray(secs, open_parcels)
    actions = optimise(secs, open_parcels, cgt, account)
    return dict(account=account, secs=secs, events=events, cgt=cgt, income=income,
                tax=tax, xray=xray, actions=actions)
