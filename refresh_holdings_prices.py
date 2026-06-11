#!/usr/bin/env python3
import yfinance as yf
import json
import os
import sys

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
]

def fetch_prices():
    print("Fetching currency exchange rates...", flush=True)
    try:
        gbpusd = yf.Ticker("GBPUSD=X").fast_info.get("last_price", 1.28)
        eurgbp = yf.Ticker("EURGBP=X").fast_info.get("last_price", 0.84)
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
            t = yf.Ticker(ticker)
            
            # Try fast_info first
            info = t.fast_info
            price = info.get("last_price")
            
            # Fallback to history if last_price is None or invalid
            if price is None or price <= 0:
                hist = t.history(period="5d")
                if not hist.empty:
                    price = hist["Close"].iloc[-1]
            
            if price is None or price <= 0:
                print(f"Warning: No price found for {ticker}", flush=True)
                continue
                
            currency = info.get("currency", "GBP")
            
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
                # Default fallback
                price_pence = float(price) * 100.0
                
            price_map[ticker] = round(price_pence, 4)
            print(f"Success: {ticker} = {price_map[ticker]}p ({currency} raw: {price})", flush=True)
            
        except Exception as e:
            print(f"Failed to fetch {ticker}: {e}", file=sys.stderr, flush=True)
            
    return price_map

if __name__ == "__main__":
    prices = fetch_prices()
    
    from datetime import datetime, timezone
    output_path = "holdings_prices.json"
    with open(output_path, "w") as f:
        json.dump({
            "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "prices": prices
        }, f, indent=2)
        
    print(f"Saved {len(prices)} prices to {output_path}", flush=True)
