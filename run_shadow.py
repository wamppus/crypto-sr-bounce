#!/usr/bin/env python3
"""
Shadow Trading Runner

Runs the crypto S/R bounce strategy in paper trading mode.
Fetches hourly bars and manages trades without real execution.
"""

import sys
import os
import time
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

from strategy import LiveStrategy, BarData
from exchange_client import HyperliquidClient
from config import StrategyConfig


def fetch_recent_bars(coin: str = 'BTC', hours: int = 100) -> list[BarData]:
    """Fetch recent hourly bars from CryptoCompare"""
    url = "https://min-api.cryptocompare.com/data/v2/histohour"
    params = {
        'fsym': coin.upper(),
        'tsym': 'USD',
        'limit': hours,
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('Response') == 'Error':
            print(f"API Error: {data.get('Message')}")
            return []
        
        bars = []
        for candle in data.get('Data', {}).get('Data', []):
            bars.append(BarData(
                timestamp=datetime.fromtimestamp(candle['time'], tz=timezone.utc),
                open=candle['open'],
                high=candle['high'],
                low=candle['low'],
                close=candle['close'],
                volume=candle.get('volumefrom', 0),
            ))
        
        return bars
        
    except Exception as e:
        print(f"Error fetching bars: {e}")
        return []


def run_shadow(coin: str = 'BTC', interval_minutes: int = 5):
    """
    Run shadow trading.
    
    - Fetches historical bars on startup
    - Checks for new hourly bar every interval
    - Manages position based on strategy signals
    """
    print("="*60)
    print(f"CRYPTO S/R BOUNCE - SHADOW TRADING")
    print(f"Coin: {coin}")
    print(f"Strategy: 2:4 R:R (no trailing)")
    print(f"Check interval: {interval_minutes} minutes")
    print("="*60)
    
    # Initialize
    client = HyperliquidClient(
        address='0x0000000000000000000000000000000000000000',
        testnet=True,
    )
    
    strategy = LiveStrategy(
        client=client,
        coin=coin,
        shadow=True,
        log_dir='logs',
    )
    
    # Fetch historical bars
    print(f"\nFetching historical bars...")
    bars = fetch_recent_bars(coin, hours=100)
    
    if not bars:
        print("Failed to fetch historical data!")
        return
    
    print(f"Loaded {len(bars)} hourly bars")
    print(f"Range: {bars[0].timestamp} to {bars[-1].timestamp}")
    
    # Warm up strategy with historical bars (except last one)
    for bar in bars[:-1]:
        strategy.bars.append(bar)
    
    # Keep max bars
    max_bars = 100
    if len(strategy.bars) > max_bars:
        strategy.bars = strategy.bars[-max_bars:]
    
    # Process most recent bar
    strategy.update(bars[-1])
    
    # Show initial status
    status = strategy.get_status()
    print(f"\n📊 Initial Status:")
    print(f"   Price: ${status['price']:,.2f}")
    print(f"   ATR: ${status['atr']:,.2f}")
    print(f"   RSI: {status['rsi']}")
    print(f"   Position: {status['position']}")
    
    # Track last bar time
    last_bar_time = bars[-1].timestamp
    
    print(f"\n🚀 Shadow trading started. Press Ctrl+C to stop.\n")
    
    try:
        while True:
            time.sleep(interval_minutes * 60)
            
            # Fetch latest bar
            new_bars = fetch_recent_bars(coin, hours=2)
            if not new_bars:
                continue
            
            latest = new_bars[-1]
            
            # Check if it's a new bar
            if latest.timestamp > last_bar_time:
                print(f"\n[{datetime.now(timezone.utc).strftime('%H:%M')}] New bar: {latest.timestamp}")
                strategy.update(latest)
                last_bar_time = latest.timestamp
                
                # Show status
                status = strategy.get_status()
                print(f"   Price: ${status['price']:,.2f} | RSI: {status['rsi']}")
                if status['position']:
                    pos = status['position']
                    print(f"   Position: {pos['direction'].upper()} @ ${pos['entry']:,.2f}")
                    print(f"   P&L: {pos['unrealized_pnl']:+.2f}%")
            else:
                # Just check current price for exit management
                current_price = client.get_price(coin)
                if current_price and strategy.active_trade:
                    exit_reason = strategy.check_exit(current_price)
                    if exit_reason:
                        strategy.exit_trade(exit_reason)
                        status = strategy.get_status()
                        print(f"\n💰 Trade closed: {exit_reason}")
                        print(f"   Daily P&L: ${status['daily_pnl']:,.2f}")
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Shadow trading stopped.")
        status = strategy.get_status()
        print(f"\nFinal Status:")
        print(f"   Trades today: {status['trades_today']}")
        print(f"   Daily P&L: ${status['daily_pnl']:,.2f}")
        if status['position']:
            print(f"   Open position: {status['position']}")


def show_status(coin: str = 'BTC'):
    """Show current strategy status (uses CryptoCompare for quick display)"""
    from strategy import BarData
    
    # Fetch bars directly (faster than going through exchange client)
    bars = fetch_recent_bars(coin, hours=100)
    if not bars:
        print("Failed to fetch data")
        return
    
    # Quick ATR/RSI calculation
    def calc_atr(bars, period=24):
        if len(bars) < period + 1:
            return 0
        tr_values = []
        for i in range(-period, 0):
            tr = max(
                bars[i].high - bars[i].low,
                abs(bars[i].high - bars[i-1].close),
                abs(bars[i].low - bars[i-1].close)
            )
            tr_values.append(tr)
        return sum(tr_values) / len(tr_values)
    
    def calc_rsi(bars, period=14):
        if len(bars) < period + 1:
            return 50
        closes = [b.close for b in bars[-(period+1):]]
        deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    current_price = bars[-1].close
    atr = calc_atr(bars)
    rsi = calc_rsi(bars)
    
    # S/R levels (24h lookback)
    recent = bars[-24:]
    support = min(b.low for b in recent)
    resistance = max(b.high for b in recent)
    
    # Trend (72h lookback)
    trend = None
    if len(bars) >= 72:
        trend_bars = bars[-72:]
        half = 36
        first_half = trend_bars[:half]
        second_half = trend_bars[half:]
        
        first_avg = sum(b.close for b in first_half) / len(first_half)
        second_avg = sum(b.close for b in second_half) / len(second_half)
        first_high = max(b.high for b in first_half)
        second_high = max(b.high for b in second_half)
        first_low = min(b.low for b in first_half)
        second_low = min(b.low for b in second_half)
        
        if second_high > first_high and second_low > first_low and second_avg > first_avg:
            trend = 'UP'
        elif second_high < first_high and second_low < first_low and second_avg < first_avg:
            trend = 'DOWN'
    
    print(f"\n{'='*50}")
    print(f"{coin} S/R BOUNCE STATUS")
    print(f"{'='*50}")
    print(f"Price:      ${current_price:,.2f}")
    print(f"ATR (24h):  ${atr:,.2f} ({atr/current_price*100:.2f}%)")
    print(f"RSI:        {rsi:.1f}")
    print(f"Trend:      {trend or 'NONE'}")
    print(f"\nS/R Levels (24h):")
    print(f"  Support:    ${support:,.2f}")
    print(f"  Resistance: ${resistance:,.2f}")
    
    range_pct = (resistance - support) / support * 100
    print(f"  Range:      {range_pct:.1f}%")
    
    # Distance to levels
    dist_support = (current_price - support) / current_price * 100
    dist_resistance = (resistance - current_price) / current_price * 100
    print(f"\n  Distance to support:    {dist_support:.2f}%")
    print(f"  Distance to resistance: {dist_resistance:.2f}%")
    
    # Check for signal
    tolerance = atr * 0.5
    near_support = current_price <= support + tolerance
    near_resistance = current_price >= resistance - tolerance
    
    signal = None
    if near_support and trend == 'UP':
        signal = 'LONG'
    elif near_resistance and trend == 'DOWN':
        signal = 'SHORT'
    elif near_support and trend is None:
        if bars[-1].close < bars[-2].open:
            signal = 'LONG (contrarian)'
    elif near_resistance and trend is None:
        if bars[-1].close > bars[-2].open:
            signal = 'SHORT (contrarian)'
    
    if signal:
        print(f"\n🚨 SIGNAL: {signal}")
        stop_dist = atr * 2.0
        target_dist = atr * 4.0
        if 'LONG' in signal:
            print(f"   Entry:  ${current_price:,.2f}")
            print(f"   Stop:   ${current_price - stop_dist:,.2f} (-{stop_dist/current_price*100:.1f}%)")
            print(f"   Target: ${current_price + target_dist:,.2f} (+{target_dist/current_price*100:.1f}%)")
        else:
            print(f"   Entry:  ${current_price:,.2f}")
            print(f"   Stop:   ${current_price + stop_dist:,.2f} (+{stop_dist/current_price*100:.1f}%)")
            print(f"   Target: ${current_price - target_dist:,.2f} (-{target_dist/current_price*100:.1f}%)")
    else:
        print(f"\n📊 No signal - waiting for S/R touch with trend alignment")
        if trend:
            if trend == 'UP':
                print(f"   Watching for bounce at support (${support:,.2f})")
            else:
                print(f"   Watching for rejection at resistance (${resistance:,.2f})")
    
    print()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Crypto S/R Bounce Shadow Trading')
    parser.add_argument('command', nargs='?', default='run', choices=['run', 'status'],
                       help='Command to execute')
    parser.add_argument('--coin', default='BTC', help='Coin to trade (BTC, ETH)')
    parser.add_argument('--interval', type=int, default=5, help='Check interval in minutes')
    
    args = parser.parse_args()
    
    if args.command == 'status':
        show_status(args.coin)
    else:
        run_shadow(args.coin, args.interval)
