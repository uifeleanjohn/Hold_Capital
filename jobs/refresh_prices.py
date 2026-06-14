"""Daily price-refresh job. Schedule this (cron / platform scheduler) once a day:
    python -m jobs.refresh_prices
Refreshes cached prices for every ticker any user holds."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, init_db
from app.models import Trade, Dividend
from app import marketdata


def main():
    init_db()
    db = SessionLocal()
    try:
        tickers = {t.ticker for t in db.query(Trade).all()} | {d.ticker for d in db.query(Dividend).all()}
        result = marketdata.refresh_prices(db, tickers)
        print(f"Refreshed {result['updated']} tickers (source: {result['source']})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
