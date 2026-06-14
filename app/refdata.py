"""Security reference: name / exchange / sector tag / currency per ticker, plus
a seed price used until a live EODHD price is cached. Mirrors the app universe."""
# ticker: (name, exchange, tag, currency, seed_price, fx)
REF = {
    "BHP":("BHP Group","ASX","Iron ore","AUD",57.0,1.0),
    "RIO":("Rio Tinto","ASX","Iron ore","AUD",118.0,1.0),
    "FMG":("Fortescue","ASX","Iron ore","AUD",21.0,1.0),
    "MIN":("Mineral Resources","ASX","Lithium","AUD",35.0,1.0),
    "PLS":("Pilbara Minerals","ASX","Lithium","AUD",2.30,1.0),
    "IGO":("IGO Ltd","ASX","Lithium","AUD",5.2,1.0),
    "LYC":("Lynas Rare Earths","ASX","Rare earths","AUD",7.5,1.0),
    "S32":("South32","ASX","Diversified","AUD",3.4,1.0),
    "NST":("Northern Star","ASX","Gold","AUD",16.5,1.0),
    "DEG":("De Grey Mining","ASX","Gold","AUD",1.62,1.0),
    "BOE":("Boss Energy","ASX","Uranium","AUD",4.20,1.0),
    "PDN":("Paladin Energy","ASX","Uranium","AUD",9.0,1.0),
    "SFR":("Sandfire Resources","ASX","Copper","AUD",11.0,1.0),
    "WDS":("Woodside Energy","ASX","Energy","AUD",24.0,1.0),
    "STO":("Santos","ASX","Energy","AUD",7.5,1.0),
    "CSL":("CSL Limited","ASX","AU Healthcare","AUD",250.0,1.0),
    "CBA":("Commonwealth Bank","ASX","AU Financials","AUD",130.0,1.0),
    "WES":("Wesfarmers","ASX","AU Consumer","AUD",75.0,1.0),
    "WTC":("WiseTech Global","ASX","AU Tech","AUD",120.0,1.0),
    "XRO":("Xero","ASX","AU Tech","AUD",170.0,1.0),
    "TLS":("Telstra","ASX","AU Telco","AUD",4.0,1.0),
    "NVDA":("NVIDIA","NASDAQ","US Tech","USD",175.0,1.52),
    "MSFT":("Microsoft","NASDAQ","US Tech","USD",480.0,1.52),
    "AAPL":("Apple","NASDAQ","US Tech","USD",230.0,1.52),
    "GOOGL":("Alphabet","NASDAQ","US Tech","USD",200.0,1.52),
    "AMZN":("Amazon","NASDAQ","US Tech","USD",220.0,1.52),
    "META":("Meta Platforms","NASDAQ","US Tech","USD",700.0,1.52),
    "TSLA":("Tesla","NASDAQ","US Tech","USD",340.0,1.52),
    "AMD":("AMD","NASDAQ","US Tech","USD",170.0,1.52),
    "MRNA":("Moderna","NASDAQ","US Pharma","USD",70.0,1.52),
    "PFE":("Pfizer","NYSE","US Pharma","USD",26.0,1.52),
    "LLY":("Eli Lilly","NYSE","US Pharma","USD",820.0,1.52),
    # crypto — priced directly in AUD (fx 1.0)
    "BTC":("Bitcoin","CRYPTO","Crypto","AUD",165000.0,1.0),
    "ETH":("Ethereum","CRYPTO","Crypto","AUD",5500.0,1.0),
    "SOL":("Solana","CRYPTO","Crypto","AUD",320.0,1.0),
    "XRP":("XRP","CRYPTO","Crypto","AUD",3.2,1.0),
    "BNB":("BNB","CRYPTO","Crypto","AUD",1100.0,1.0),
    "ADA":("Cardano","CRYPTO","Crypto","AUD",1.5,1.0),
    "DOGE":("Dogecoin","CRYPTO","Crypto","AUD",0.55,1.0),
    "LINK":("Chainlink","CRYPTO","Crypto","AUD",35.0,1.0),
    # precious metals — price per troy ounce in AUD
    "XAU":("Gold (per oz)","METAL","Precious metals","AUD",4200.0,1.0),
    "XAG":("Silver (per oz)","METAL","Precious metals","AUD",52.0,1.0),
    "XPT":("Platinum (per oz)","METAL","Precious metals","AUD",1800.0,1.0),
}

# EODHD ticker suffix by exchange (e.g. BHP.AU, NVDA.US)
EODHD_SUFFIX = {"ASX": "AU", "NASDAQ": "US", "NYSE": "US"}

# CoinGecko ids for live crypto prices (vs AUD)
COINGECKO_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple",
                 "BNB": "binancecoin", "ADA": "cardano", "DOGE": "dogecoin", "LINK": "chainlink"}


def meta(ticker: str):
    return REF.get(ticker, (ticker, "?", "Unknown", "AUD", 0.0, 1.0))
