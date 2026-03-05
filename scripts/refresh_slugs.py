import argparse
import asyncio
import json
import time
import os

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

STATIC_SLUGS = {
    "RELIANCE": "reliance-industries-ltd-share-price",
    "TCS": "tcs-share-price",
    "INFY": "infosys-ltd-share-price",
    "HDFCBANK": "hdfc-bank-ltd-share-price",
    "ICICIBANK": "icici-bank-ltd-share-price",
    "SBIN": "state-bank-of-india-share-price",
    "ADANIENT": "adani-enterprises-ltd-share-price",
    "WIPRO": "wipro-ltd-share-price",
    "AXISBANK": "axis-bank-ltd-share-price",
    "BAJFINANCE": "bajaj-finance-ltd-share-price",
    "HCLTECH": "hcl-technologies-ltd-share-price",
    "LT": "larsen-and-toubro-ltd-share-price",
    "KOTAKBANK": "kotak-mahindra-bank-ltd-share-price",
    "TATAMOTORS": "tata-motors-ltd-share-price",
    "MARUTI": "maruti-suzuki-india-ltd-share-price",
    "SUNPHARMA": "sun-pharmaceutical-industries-ltd-share-price",
    "ITC": "itc-ltd-share-price",
    "ONGC": "oil-and-natural-gas-corporation-ltd-share-price",
    "POWERGRID": "power-grid-corporation-of-india-ltd-share-price",
    "NTPC": "ntpc-ltd-share-price",
    "BPCL": "bharat-petroleum-corporation-ltd-share-price",
    "GRASIM": "grasim-industries-ltd-share-price",
    "TITAN": "titan-company-ltd-share-price",
    "INDUSINDBK": "indusind-bank-ltd-share-price",
    "ULTRACEMCO": "ultratech-cement-ltd-share-price",
    "HEROMOTOCO": "hero-motocorp-ltd-share-price",
    "ASIANPAINT": "asian-paints-ltd-share-price",
    "MM": "mahindra-and-mahindra-ltd-share-price",
    "DRREDDY": "dr-reddy-s-laboratories-ltd-share-price",
    "DIVISLAB": "divi-s-laboratories-ltd-share-price",
    "CIPLA": "cipla-ltd-share-price",
    "TECHM": "tech-mahindra-ltd-share-price",
    "TATASTEEL": "tata-steel-ltd-share-price",
    "BAJAJFINSV": "bajaj-finserv-ltd-share-price",
    "NESTLEIND": "nestle-india-ltd-share-price",
    "HINDALCO": "hindalco-industries-ltd-share-price",
    "COALINDIA": "coal-india-ltd-share-price",
    "VEDL": "vedanta-ltd-share-price",
    "JSWSTEEL": "jsw-steel-ltd-share-price",
    "SAIL": "steel-authority-of-india-ltd-share-price",
    "APOLLOHOSP": "apollo-hospitals-enterprise-ltd-share-price",
    "PIDILITIND": "pidilite-industries-ltd-share-price",
    "SIEMENS": "siemens-ltd-share-price",
    "HAVELLS": "havells-india-ltd-share-price",
    "VOLTAS": "voltas-ltd-share-price",
    "NIFTY": "nifty-50-share-price",
    "BANKNIFTY": "nifty-bank-share-price",
    "FINNIFTY": "nifty-fin-service-share-price"
}

def save_slugs(slug_map):
    output_path = os.path.join(os.path.dirname(__file__), "..", "backend", "slugs.json")
    with open(output_path, "w") as f:
        json.dump(slug_map, f, indent=2)
    print(f"Generated {output_path}")

def method_static():
    save_slugs(STATIC_SLUGS)

def method_ddg():
    from duckduckgo_search import DDGS

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

    slug_map = {}
    for symbol in INDEX_SYMBOLS + FO_STOCKS:
        slug = search_slug(symbol)
        if slug:
            slug_map[symbol] = slug
        print(f"{symbol} -> {slug}")
        time.sleep(1.5)
    save_slugs(slug_map)

async def method_html():
    from curl_cffi.requests import AsyncSession
    from bs4 import BeautifulSoup

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "referer": "https://www.google.com/"
    }

    async def fetch_slug(client, symbol):
        if symbol == "NIFTY": return "nifty-50-share-price"
        if symbol == "BANKNIFTY": return "nifty-bank-share-price"
        if symbol == "FINNIFTY": return "nifty-fin-service-share-price"
        
        url = f"https://www.indmoney.com/search?q={symbol}"
        try:
            r = await client.get(url, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "")
                    if "/stocks/" in href and "-share-price" in href:
                        slug = href.split("/stocks/")[-1].split("?")[0].strip("/")
                        return slug
        except Exception as e:
            print(f"Error {symbol}: {e}")
        return ""

    slug_map = {}
    async with AsyncSession(impersonate="chrome120", headers=HEADERS) as client:
        for symbol in FO_STOCKS:
            slug = await fetch_slug(client, symbol)
            if slug:
                slug_map[symbol] = slug
            print(f"{symbol} -> {slug}")
            await asyncio.sleep(0.5)
            
    slug_map["NIFTY"] = "nifty-50-share-price"
    slug_map["BANKNIFTY"] = "nifty-bank-share-price"
    slug_map["FINNIFTY"] = "nifty-fin-service-share-price"
    save_slugs(slug_map)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refresh INDmoney slugs for F&O Scanner")
    parser.add_argument("--method", choices=["static", "ddg", "html"], default="static", help="Method to fetch slugs (static, ddg, or html)")
    args = parser.parse_args()

    if args.method == "static":
        method_static()
    elif args.method == "ddg":
        method_ddg()
    elif args.method == "html":
        asyncio.run(method_html())
