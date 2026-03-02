import asyncio
from duckduckgo_search import DDGS
import json
import time

FO_STOCKS = [
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","SBIN","ADANIENT","WIPRO",
    "AXISBANK","BAJFINANCE","HCLTECH","LT","KOTAKBANK","TATAMOTORS","MARUTI",
    "SUNPHARMA","ITC","ONGC","POWERGRID","NTPC","BPCL","GRASIM","TITAN",
    "INDUSINDBK","ULTRACEMCO","HEROMOTOCO","ASIANPAINT","MM","DRREDDY",
    "DIVISLAB","CIPLA","TECHM","TATASTEEL","BAJAJFINSV","NESTLEIND",
    "HINDALCO","COALINDIA","VEDL","JSWSTEEL","SAIL","APOLLOHOSP",
    "PIDILITIND","SIEMENS","HAVELLS","VOLTAS",
]
INDEX_SYMBOLS = ["NIFTY", "BANKNIFTY", "FINNIFTY"]

def search_slug(symbol):
    if symbol == "NIFTY": return "nifty-50-share-price"
    if symbol == "BANKNIFTY": return "nifty-bank-share-price"
    if symbol == "FINNIFTY": return "nifty-fin-service-share-price"
    
    query = f"site:indmoney.com/options {symbol} share price"
    try:
        results = DDGS().text(query, max_results=3)
        for r in results:
            url = r.get("href", "")
            if "indmoney.com/options/" in url:
                slug = url.split("indmoney.com/options/")[-1].split("/")[0].split("?")[0]
                return slug
    except Exception as e:
        print(f"Error for {symbol}: {e}")
    return ""

def main():
    slug_map = {}
    for symbol in INDEX_SYMBOLS + FO_STOCKS:
        slug = search_slug(symbol)
        if slug:
            slug_map[symbol] = slug
        print(f"{symbol} -> {slug}")
        time.sleep(1.5)
        
    with open("slugs.json", "w") as f:
        json.dump(slug_map, f, indent=2)

if __name__ == "__main__":
    main()
