#!/usr/bin/env python3
"""
Fetch historical crypto data from multiple sources.
Tries CryptoCompare (free, good history) first.
"""

import pandas as pd
import requests
from datetime import datetime, timezone
from pathlib import Path
import time

def fetch_cryptocompare(symbol: str = 'BTC', timeframe: str = '5m', days: int = 365) -> pd.DataFrame:
    """
    Fetch from CryptoCompare API (free tier: 100K calls/month)
    
    Timeframes: 1m (histominute), 5m, 15m, 1h (histohour), 1d (histoday)
    """
    # Map timeframe to API endpoint and aggregate
    tf_map = {
        '1m': ('histominute', 1),
        '5m': ('histominute', 5),
        '15m': ('histominute', 15),
        '1h': ('histohour', 1),
        '4h': ('histohour', 4),
        '1d': ('histoday', 1),
    }
    
    endpoint, aggregate = tf_map.get(timeframe, ('histominute', 5))
    
    base_url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
    
    all_data = []
    to_ts = int(datetime.now(timezone.utc).timestamp())
    
    # Calculate how many candles we need
    minutes_per_candle = {'histominute': 1, 'histohour': 60, 'histoday': 1440}[endpoint] * aggregate
    total_candles_needed = (days * 24 * 60) // minutes_per_candle
    
    print(f"Fetching {symbol} {timeframe} data from CryptoCompare...")
    print(f"Need ~{total_candles_needed:,} candles for {days} days")
    
    fetched = 0
    while fetched < total_candles_needed:
        params = {
            'fsym': symbol.upper(),
            'tsym': 'USD',
            'limit': 2000,  # Max per request
            'toTs': to_ts,
            'aggregate': aggregate,
        }
        
        try:
            resp = requests.get(base_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get('Response') == 'Error':
                print(f"API Error: {data.get('Message')}")
                break
            
            candles = data.get('Data', {}).get('Data', [])
            if not candles:
                break
            
            all_data.extend(candles)
            fetched += len(candles)
            
            # Move timestamp back for next batch
            to_ts = candles[0]['time'] - 1
            
            print(f"  Fetched {fetched:,} candles...", end='\r')
            time.sleep(0.2)  # Rate limiting
            
        except Exception as e:
            print(f"\nError: {e}")
            break
    
    print(f"\nTotal candles: {len(all_data):,}")
    
    if not all_data:
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame(all_data)
    df['timestamp'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df = df.rename(columns={
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close',
        'volumefrom': 'volume',
    })
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    df = df.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)
    
    # Filter out zero-volume/price candles
    df = df[(df['close'] > 0) & (df['volume'] > 0)]
    
    return df


def fetch_and_save(symbol: str, timeframe: str, days: int, output_dir: str = 'data'):
    """Fetch and save data to CSV"""
    df = fetch_cryptocompare(symbol, timeframe, days)
    
    if df.empty:
        print(f"No data fetched for {symbol}")
        return None
    
    # Add derived columns
    df['hour'] = df['timestamp'].dt.hour
    df['range'] = df['high'] - df['low']
    
    # Save
    Path(output_dir).mkdir(exist_ok=True)
    filename = f"{output_dir}/{symbol}USD_{timeframe}_{days}d.csv"
    df.to_csv(filename, index=False)
    
    print(f"\n✅ Saved to {filename}")
    print(f"   Range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"   Price: ${df['close'].iloc[0]:,.0f} → ${df['close'].iloc[-1]:,.0f}")
    
    return df


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='BTC', help='Crypto symbol (BTC, ETH)')
    parser.add_argument('--timeframe', default='5m', help='Timeframe (1m, 5m, 15m, 1h, 4h, 1d)')
    parser.add_argument('--days', type=int, default=365, help='Days of history')
    args = parser.parse_args()
    
    fetch_and_save(args.symbol, args.timeframe, args.days)
