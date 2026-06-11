#!/usr/bin/env python3
import urllib.request
import urllib.parse
import json
import sys
from datetime import datetime, timezone

# Define all unique tickers used in the holdings dashboard
TICKERS = [
    "MSE.PA",  # Amundi Euro Stoxx 50
    "ARKA.L",  # Ark AI & Robotics
    "EMRD.L",  # SPDR MSCI EM (USD)
    "LBUL.L",  # WisdomTree Gold 2x (USD)
    "XS2D.L",  # Xtrackers S&P 500 2x (USD)
    "VUAG.L",  # Vanguard S&P 500 Acc
    "LQQ3.L",  # WisdomTree Nasdaq 3x
    "MIDD.L",  # iShares FTSE 250
    "EIMI.L",  # iShares MSCI EM IMI
    "SGLN.L",  # iShares Physical Gold
    "EMIM.L",  # iShares MSCI EM
    "GDGB.L",  # VanEck Gold Miners UCITS ETF
    "SEMI.L",  # iShares MSCI Global Semiconductor UCITS ETF
]

def fetch_ticker_price(ticker):
    encoded_ticker = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?interval=1m&range=1d"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
        result = payload["chart"]["result"][0]
        meta = result.get("meta", {})
        currency = meta.get("currency", "GBP")
        
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        valid_closes = [c for c in closes if c is not None and c > 0]
        
        if valid_closes:
            price = valid_closes[-1]
        else:
            price = meta.get("regularMarketPrice")
            
        if price is None:
            # Try 5d backup in case of no trading today yet
            url_backup = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?interval=1d&range=5d"
            req_backup = urllib.request.Request(url_backup, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_backup, timeout=15) as res_backup:
                payload_b = json.loads(res_backup.read().decode("utf-8"))
                result_b = payload_b["chart"]["result"][0]
                meta_b = result_b.get("meta", {})
                closes_b = result_b.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                valid_b = [c for c in closes_b if c is not None and c > 0]
                if valid_b:
                    price = valid_b[-1]
                else:
                    price = meta_b.get("regularMarketPrice")
                    
        return price, currency

def fetch_prices():
    print("Fetching currency exchange rates...", flush=True)
    try:
        gbpusd, _ = fetch_ticker_price("GBPUSD=X")
        eurgbp, _ = fetch_ticker_price("EURGBP=X")
        if not gbpusd: gbpusd = 1.28
        if not eurgbp: eurgbp = 0.84
    except Exception as e:
        print(f"Error fetching exchange rates, using defaults: {e}", flush=True)
        gbpusd = 1.28
        eurgbp = 0.84
    
    print(f"Rates - GBP/USD: {gbpusd}, EUR/GBP: {eurgbp}", flush=True)
    
    price_map = {
        "CASH": 100.0  # Cash is always 100 pence (1 GBP)
    }
    
    for ticker in TICKERS:
        try:
            print(f"Fetching {ticker}...", flush=True)
            price, currency = fetch_ticker_price(ticker)
            
            if price is None or price <= 0:
                print(f"Warning: No price found for {ticker}", flush=True)
                continue
                
            # Convert to pence (GBX/GBp) based on quote currency
            if currency in ["GBp", "GBX", "GBx"]:
                price_pence = float(price)
            elif currency == "GBP":
                price_pence = float(price) * 100.0
            elif currency == "USD":
                price_pence = (float(price) / gbpusd) * 100.0
            elif currency == "EUR":
                price_pence = (float(price) * eurgbp) * 100.0
            else:
                price_pence = float(price) * 100.0
                
            price_map[ticker] = round(price_pence, 4)
            print(f"Success: {ticker} = {price_map[ticker]}p ({currency} raw: {price})", flush=True)
            
        except Exception as e:
            print(f"Failed to fetch {ticker}: {e}", file=sys.stderr, flush=True)
            
    return price_map

if __name__ == "__main__":
    prices = fetch_prices()
    
    output_path = "holdings_prices.json"
    with open(output_path, "w") as f:
        json.dump({
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "prices": prices
        }, f, indent=2)
        
    print(f"Saved {len(prices)} prices to {output_path}", flush=True)
