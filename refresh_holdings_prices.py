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

def fetch_history_raw(ticker, range_str="3y"):
    encoded_ticker = urllib.parse.quote(ticker)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}?interval=1d&range={range_str}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp", [])
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        meta = result.get("meta", {})
        currency = meta.get("currency", "GBP")
        
        history = {}
        for t, c in zip(timestamps, closes):
            if t and c is not None and c > 0:
                date_str = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
                history[date_str] = c
        return history, currency

def get_exchange_rate_hist(history_map, date, default_val=1.0):
    cur_date = date
    for _ in range(10):
        if cur_date in history_map:
            return history_map[cur_date]
        dt = datetime.strptime(cur_date, "%Y-%m-%d")
        dt = datetime.fromordinal(dt.toordinal() - 1)
        cur_date = dt.strftime("%Y-%m-%d")
    return default_val

def build_historical_database():
    print("Fetching historical exchange rates for database...", flush=True)
    try:
        gbpusd_hist, _ = fetch_history_raw("GBPUSD=X")
        eur2gbp_hist, _ = fetch_history_raw("EURGBP=X")
    except Exception as e:
        print(f"Error fetching historical exchange rates: {e}", file=sys.stderr, flush=True)
        gbpusd_hist = {}
        eur2gbp_hist = {}
        
    all_dates = set(gbpusd_hist.keys()).union(eur2gbp_hist.keys())
    
    ticker_data = {}
    currencies = {}
    for ticker in TICKERS:
        try:
            print(f"Fetching history for {ticker}...", flush=True)
            hist, curr = fetch_history_raw(ticker)
            ticker_data[ticker] = hist
            currencies[ticker] = curr
            all_dates = all_dates.union(hist.keys())
        except Exception as e:
            print(f"Failed to fetch history for {ticker}: {e}", file=sys.stderr, flush=True)

    sorted_dates = sorted(list(all_dates))
    if not sorted_dates:
        print("Warning: No historical dates found.", file=sys.stderr, flush=True)
        return None
        
    output_prices = {t: [] for t in TICKERS}
    output_prices["CASH"] = [100.0] * len(sorted_dates)
    last_known_pence = {t: None for t in TICKERS}
    
    for date in sorted_dates:
        usd_rate = get_exchange_rate_hist(gbpusd_hist, date, 1.28)
        eur_rate = get_exchange_rate_hist(eur2gbp_hist, date, 0.84)
        
        for ticker in TICKERS:
            if ticker not in ticker_data:
                output_prices[ticker].append(0.0)
                continue
                
            raw_val = ticker_data[ticker].get(date)
            currency = currencies.get(ticker, "GBP")
            
            if raw_val is not None:
                if currency in ["GBp", "GBX", "GBx"]:
                    pence = float(raw_val)
                elif currency == "GBP":
                    pence = float(raw_val) * 100.0
                elif currency == "USD":
                    pence = (float(raw_val) / usd_rate) * 100.0
                elif currency == "EUR":
                    pence = (float(raw_val) * eur_rate) * 100.0
                else:
                    pence = float(raw_val) * 100.0
                last_known_pence[ticker] = round(pence, 4)
                
            val_to_append = last_known_pence[ticker]
            if val_to_append is None:
                future_dates = [d for d in sorted_dates if ticker_data[ticker].get(d) is not None]
                if future_dates:
                    first_date = future_dates[0]
                    first_val = ticker_data[ticker][first_date]
                    if currency in ["GBp", "GBX", "GBx"]:
                        pence = float(first_val)
                    elif currency == "GBP":
                        pence = float(first_val) * 100.0
                    elif currency == "USD":
                        pence = (float(first_val) / get_exchange_rate_hist(gbpusd_hist, first_date, 1.28)) * 100.0
                    elif currency == "EUR":
                        pence = (float(first_val) * get_exchange_rate_hist(eur2gbp_hist, first_date, 0.84)) * 100.0
                    else:
                        pence = float(first_val) * 100.0
                    last_known_pence[ticker] = round(pence, 4)
                    val_to_append = last_known_pence[ticker]
                else:
                    val_to_append = 0.0
            output_prices[ticker].append(val_to_append)
            
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dates": sorted_dates,
        "prices": output_prices
    }

if __name__ == "__main__":
    import os
    
    # 1. Fetch current prices
    prices = fetch_prices()
    
    # Save holdings_prices.json
    for path in ["holdings_prices.json", os.path.join("holdings_web", "holdings_prices.json")]:
        try:
            with open(path, "w") as f:
                json.dump({
                    "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "prices": prices
                }, f, indent=2)
            print(f"Saved current prices to {path}", flush=True)
        except Exception as e:
            print(f"Failed to save to {path}: {e}", file=sys.stderr, flush=True)

    # 2. Fetch historical prices
    print("Building historical database...", flush=True)
    hist_db = build_historical_database()
    if hist_db:
        # Save holdings_historical_prices.json
        for path in ["holdings_historical_prices.json", os.path.join("holdings_web", "holdings_historical_prices.json")]:
            try:
                with open(path, "w") as f:
                    json.dump(hist_db, f, indent=2)
                print(f"Saved historical prices to {path}", flush=True)
            except Exception as e:
                print(f"Failed to save to {path}: {e}", file=sys.stderr, flush=True)
    else:
        print("Failed to build historical price database.", file=sys.stderr, flush=True)
