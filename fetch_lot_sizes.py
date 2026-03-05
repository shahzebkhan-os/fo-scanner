import json
import urllib.request
import re

url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
print("Downloading scrip master...")
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())

FO_STOCKS = [
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","SBIN","ADANIENT","WIPRO",
    "AXISBANK","BAJFINANCE","HCLTECH","LT","KOTAKBANK","TATAMOTORS","MARUTI",
    "SUNPHARMA","ITC","ONGC","POWERGRID","NTPC","BPCL","GRASIM","TITAN",
    "INDUSINDBK","ULTRACEMCO","HEROMOTOCO","ASIANPAINT","MM","DRREDDY",
    "BAJAJFINSV","HINDALCO","TATASTEEL", "DIVISLAB", "CIPLA", "TECHM",
    "NESTLEIND", "COALINDIA", "VEDL", "JSWSTEEL", "SAIL", "APOLLOHOSP",
    "PIDILITIND", "SIEMENS", "HAVELLS", "VOLTAS", "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"
]

lot_sizes = {}
for item in data:
    if item['exch_seg'] == 'NFO' and item['instrumenttype'] in ('FUTIDX', 'FUTSTK'):
        # Usually format is like "RELIANCE27JUN2024FUT" or such.
        # But Angel uses 'name' which is the base symbol.
        name = item.get('name')
        if name in FO_STOCKS and name not in lot_sizes:
            lot = int(item.get('lotsize', 0))
            if lot > 0:
                lot_sizes[name] = lot

print("Extracted Lot Sizes:")
for sym in FO_STOCKS:
    print(f'"{sym}": {lot_sizes.get(sym, "NOT_FOUND")},')

