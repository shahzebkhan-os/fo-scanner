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

LOT_SIZES = {
    "NIFTY": 75, "BANKNIFTY": 30, "FINNIFTY": 65, "MIDCPNIFTY": 120,
    "RELIANCE": 500, "TCS": 175, "INFY": 400, "HDFCBANK": 550, "ICICIBANK": 700,
    "SBIN": 750, "ADANIENT": 300, "WIPRO": 3000, "AXISBANK": 625, "BAJFINANCE": 750,
    "HCLTECH": 350, "LT": 175, "KOTAKBANK": 2000, "TATAMOTORS": 1425, "MARUTI": 50,
    "SUNPHARMA": 350, "ITC": 1600, "ONGC": 2250, "POWERGRID": 1900, "NTPC": 1500,
    "BPCL": 1975, "GRASIM": 250, "TITAN": 175, "INDUSINDBK": 700, "ULTRACEMCO": 50,
    "HEROMOTOCO": 150, "ASIANPAINT": 250, "MM": 350, "DRREDDY": 625,
    "BAJAJFINSV": 250, "HINDALCO": 700, "TATASTEEL": 5500, "DIVISLAB": 100, "CIPLA": 375,
    "TECHM": 600, "NESTLEIND": 500, "COALINDIA": 1350, "VEDL": 1150, "JSWSTEEL": 675, "SAIL": 4700,
    "APOLLOHOSP": 125, "PIDILITIND": 500, "SIEMENS": 175, "HAVELLS": 500, "VOLTAS": 375
}

NSE_HEADERS = {
    "User-Agent":       "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept":           "application/json, text/plain, */*",
    "Accept-Language":  "en-US,en;q=0.9",
    "Accept-Encoding":  "gzip, deflate, br",
    "Referer":          "https://www.nseindia.com/option-chain",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua":        '"Chromium";v="122","Not(A:Brand";v="24","Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest":   "empty",
    "sec-fetch-mode":   "cors",
    "sec-fetch-site":   "same-origin",
    "Connection":       "keep-alive",
    "Cache-Control":    "no-cache",
    "Pragma":           "no-cache",
}

SLUG_MAP = {
  "NIFTY": "nifty-50-share-price",
  "BANKNIFTY": "bank-nifty-share-price",
  "FINNIFTY": "nifty-financial-services-share-price",
  "RELIANCE": "reliance-industries-ltd-share-price",
  "TCS": "tata-consultancy-services-ltd-share-price",
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
  "VOLTAS": "voltas-ltd-share-price"
}

INDSTOCKS_BASE = "https://stocks.indmoney.com"
NSE_BASE = "https://www.nseindia.com"

MAX_DAILY_AUTO_TRADES = 10
MAX_SECTOR_TRADES = 3
