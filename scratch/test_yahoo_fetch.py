import yfinance as yf
import json

tickers = {
    "MSE.PA": "Amundi Euro Stoxx 50",
    "ARKA.L": "Ark AI & Robotics",
    "EMIM.L": "SPDR/iShares MSCI EM",
    "LBUL.L": "WisdomTree Gold 2x",
    "XS2D.L": "Xtrackers S&P 500 2x",
    "VUAG.L": "Vanguard S&P 500 Acc",
    "VUKG.L": "Vanguard FTSE UK All Share Acc",
    "VERX.L": "Vanguard FTSE Dev Europe ex-UK Acc",
    "RBOT.L": "iShares Automation & Robotics (Pictet Proxy)",
    "VWRP.L": "Vanguard FTSE All-World Acc (HL Growth Proxy)"
}

try:
    gbpusd = yf.Ticker("GBPUSD=X").fast_info.get("last_price", 1.28)
    eurgbp = yf.Ticker("EURGBP=X").fast_info.get("last_price", 0.84)
    print(f"Rates - GBP/USD: {gbpusd}, EUR/GBP: {eurgbp}")
except Exception as e:
    gbpusd = 1.28
    eurgbp = 0.84
    print(f"Error fetching FX rates, using fallbacks: {e}")

results = {}
for ticker, name in tickers.items():
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = info.get("last_price")
        if price is None:
            hist = t.history(period="1d")
            if not hist.empty:
                price = hist["Close"].iloc[-1]
        
        currency = info.get("currency", "GBP")
        
        # Convert to GBp (pence)
        price_pence = None
        if price is not None:
            if currency == "GBp" or currency == "GBX":
                price_pence = price
            elif currency == "GBP":
                price_pence = price * 100.0
            elif currency == "USD":
                # Convert USD to GBP, then to pence
                price_pence = (price / gbpusd) * 100.0
            elif currency == "EUR":
                # Convert EUR to GBP, then to pence
                price_pence = (price * eurgbp) * 100.0
            else:
                # Default assume GBP
                price_pence = price * 100.0
        
        results[ticker] = {
            "name": name,
            "raw_price": price,
            "currency": currency,
            "price_pence": price_pence
        }
        print(f"{ticker} ({name}): Raw {price} {currency} -> Calculated {price_pence:.2f}p")
    except Exception as e:
        results[ticker] = {"error": str(e)}
        print(f"Error fetching {ticker}: {e}")

with open("calculated_pence_prices.json", "w") as f:
    json.dump(results, f, indent=2)
