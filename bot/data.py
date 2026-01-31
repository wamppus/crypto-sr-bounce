#!/usr/bin/env python3
"""
Crypto Data Fetching

Fetch historical OHLCV data from exchanges for backtesting.
Uses ccxt for unified API access.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import time
import argparse

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    print("[WARNING] ccxt not installed. Run: pip install ccxt")


# Session definitions (UTC)
SESSIONS = {
    'asia': (0, 8),      # 00:00-08:00 UTC
    'europe': (8, 16),   # 08:00-16:00 UTC  
    'us': (14, 22),      # 14:00-22:00 UTC
    'overlap': (14, 16), # EU/US overlap
}


def get_session(hour: int) -> str:
    """Get session name for a given UTC hour"""
    if 14 <= hour < 16:
        return 'overlap'
    elif 0 <= hour < 8:
        return 'asia'
    elif 8 <= hour < 16:
        return 'europe'
    elif 14 <= hour < 22:
        return 'us'
    else:
        return 'asia'  # Late night = early asia


def fetch_ohlcv(
    symbol: str = 'BTC/USDT',
    timeframe: str = '5m',
    days: int = 365,
    exchange_id: str = 'binance',
    save_path: str = None,
) -> pd.DataFrame:
    """
    Fetch historical OHLCV data from exchange.
    
    Args:
        symbol: Trading pair (e.g., 'BTC/USDT')
        timeframe: Candle timeframe ('1m', '5m', '15m', '1h', '4h', '1d')
        days: Number of days of history
        exchange_id: Exchange to use ('binance', 'bybit', etc.)
        save_path: Optional path to save CSV
        
    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
    """
    if not CCXT_AVAILABLE:
        raise ImportError("ccxt required. Install with: pip install ccxt")
    
    # Initialize exchange
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({
        'enableRateLimit': True,
    })
    
    print(f"Fetching {days} days of {symbol} {timeframe} from {exchange_id}...")
    
    # Calculate timestamps
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)
    
    # Fetch in chunks (most exchanges limit to 1000-1500 candles per request)
    all_ohlcv = []
    since = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)
    
    while since < end_ms:
        try:
            ohlcv = exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                since=since,
                limit=1000
            )
            
            if not ohlcv:
                break
                
            all_ohlcv.extend(ohlcv)
            since = ohlcv[-1][0] + 1  # Next candle after last
            
            print(f"  Fetched {len(all_ohlcv):,} candles...", end='\r')
            time.sleep(exchange.rateLimit / 1000)  # Rate limiting
            
        except Exception as e:
            print(f"\nError fetching data: {e}")
            break
    
    print(f"\nTotal candles: {len(all_ohlcv):,}")
    
    # Convert to DataFrame
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    
    # Add session info
    df['hour'] = df['timestamp'].dt.hour
    df['session'] = df['hour'].apply(get_session)
    
    # Add derived columns
    df['range'] = df['high'] - df['low']
    df['body'] = abs(df['close'] - df['open'])
    df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
    
    # Sort and dedupe
    df = df.sort_values('timestamp').drop_duplicates('timestamp').reset_index(drop=True)
    
    # Save if path provided
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(save_path, index=False)
        print(f"Saved to {save_path}")
    
    return df


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range"""
    high = df['high']
    low = df['low']
    close = df['close'].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close)
    tr3 = abs(low - close)
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    
    return atr


def get_round_levels(price: float, asset: str = 'BTC') -> list:
    """
    Get nearby round number levels for S/R.
    
    Crypto respects psychological levels more than traditional markets.
    """
    if asset.upper() in ['BTC', 'BITCOIN']:
        # BTC: $1000 levels, with $5000 being major
        base = 1000
        major = 5000
    elif asset.upper() in ['ETH', 'ETHEREUM']:
        # ETH: $100 levels, with $500 being major
        base = 100
        major = 500
    else:
        # Default: 1% of price
        base = round(price * 0.01, -int(np.log10(price * 0.01)))
        major = base * 5
    
    # Find nearest round levels
    lower_base = (price // base) * base
    upper_base = lower_base + base
    lower_major = (price // major) * major
    upper_major = lower_major + major
    
    levels = [
        {'level': lower_base, 'type': 'minor'},
        {'level': upper_base, 'type': 'minor'},
        {'level': lower_major, 'type': 'major'},
        {'level': upper_major, 'type': 'major'},
    ]
    
    return sorted(levels, key=lambda x: abs(x['level'] - price))


def load_data(filepath: str) -> pd.DataFrame:
    """Load saved OHLCV data"""
    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    return df


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fetch crypto OHLCV data')
    parser.add_argument('--symbol', default='BTC/USDT', help='Trading pair')
    parser.add_argument('--timeframe', default='5m', help='Candle timeframe')
    parser.add_argument('--days', type=int, default=365, help='Days of history')
    parser.add_argument('--exchange', default='binance', help='Exchange to use')
    parser.add_argument('--output', default=None, help='Output CSV path')
    
    args = parser.parse_args()
    
    if args.output is None:
        symbol_clean = args.symbol.replace('/', '')
        args.output = f'data/{symbol_clean}_{args.timeframe}_{args.days}d.csv'
    
    df = fetch_ohlcv(
        symbol=args.symbol,
        timeframe=args.timeframe,
        days=args.days,
        exchange_id=args.exchange,
        save_path=args.output,
    )
    
    print(f"\nData summary:")
    print(f"  Range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"  Candles: {len(df):,}")
    print(f"  Price range: ${df['low'].min():,.0f} - ${df['high'].max():,.0f}")
