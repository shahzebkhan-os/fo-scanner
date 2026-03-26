import yfinance as yf
import pandas as pd
import numpy as np

def test_single_ticker(symbol="RELIANCE.NS"):
    print(f"Testing {symbol}...")
    df = yf.download(symbol, period="5d", interval="1m", progress=False)
    print(f"Columns: {df.columns}")
    print(f"Index levels: {df.columns.nlevels}")
    
    # Simulate flattening from main.py
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        if "Close" in df.columns.get_level_values(0):
            df.columns = df.columns.get_level_values(0)
        else:
            df.columns = df.columns.get_level_values(1)
            
    print(f"Flattened columns: {df.columns}")
    
    try:
        df_2m = df.resample('2min').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        print("Resampling successful!")
        print(df_2m.head())
    except Exception as e:
        print(f"Resampling failed: {e}")

if __name__ == "__main__":
    test_single_ticker()
