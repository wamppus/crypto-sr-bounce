#!/usr/bin/env python3
"""
DOT Shadow/Live Trading Runner

Focused on Polkadot with 2:4 R:R strategy.
"""

import sys
import os
import time
import json
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

from dotenv import load_dotenv
load_dotenv()

from kraken_client import KrakenClient
from config import StrategyConfig


def get_dot_status():
    """Get current DOT trading status"""
    from config import DOT_OPTIMIZED
    
    client = KrakenClient(
        api_key=os.environ.get('KRAKEN_API_KEY'),
        api_secret=os.environ.get('KRAKEN_API_SECRET'),
    )
    
    # Get price and balance
    price = client.get_price('DOT')
    balance = client.get_balance()
    usd_balance = float(balance.get('ZUSD', 0)) if balance else 0
    dot_balance = float(balance.get('DOT', 0)) if balance else 0
    
    # Get OHLC for analysis
    bars = client.get_ohlc('DOTUSD', interval=60)
    
    if not bars or not price:
        return None
    
    # Calculate indicators
    recent_24h = bars[-24:]
    support = min(b['low'] for b in recent_24h)
    resistance = max(b['high'] for b in recent_24h)
    
    # ATR
    tr_vals = []
    for i in range(1, min(25, len(bars))):
        tr = max(
            bars[-i]['high'] - bars[-i]['low'],
            abs(bars[-i]['high'] - bars[-i-1]['close']),
            abs(bars[-i]['low'] - bars[-i-1]['close'])
        )
        tr_vals.append(tr)
    atr = sum(tr_vals) / len(tr_vals)
    
    # RSI
    closes = [b['close'] for b in bars[-15:]]
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains) / len(gains)
    avg_loss = sum(losses) / len(losses)
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    
    # Trend (72 bars)
    trend = None
    if len(bars) >= 72:
        trend_bars = bars[-72:]
        half = 36
        first_avg = sum(b['close'] for b in trend_bars[:half]) / half
        second_avg = sum(b['close'] for b in trend_bars[half:]) / half
        first_high = max(b['high'] for b in trend_bars[:half])
        second_high = max(b['high'] for b in trend_bars[half:])
        first_low = min(b['low'] for b in trend_bars[:half])
        second_low = min(b['low'] for b in trend_bars[half:])
        
        if second_high > first_high and second_low > first_low and second_avg > first_avg:
            trend = 'UP'
        elif second_high < first_high and second_low < first_low and second_avg < first_avg:
            trend = 'DOWN'
    
    # Check for signal
    tolerance = atr * 0.5
    near_support = price <= support + tolerance
    near_resistance = price >= resistance - tolerance
    
    signal = None
    if near_support and trend == 'UP':
        signal = 'LONG (trend)'
    elif near_resistance and trend == 'DOWN':
        signal = 'SHORT (trend)'
    elif near_support and trend is None:
        if len(bars) >= 2 and bars[-1]['close'] < bars[-2]['open']:
            signal = 'LONG (contrarian)'
    elif near_resistance and trend is None:
        if len(bars) >= 2 and bars[-1]['close'] > bars[-2]['open']:
            signal = 'SHORT (contrarian)'
    
    return {
        'price': price,
        'usd_balance': usd_balance,
        'dot_balance': dot_balance,
        'support': support,
        'resistance': resistance,
        'atr': atr,
        'rsi': rsi,
        'trend': trend,
        'signal': signal,
        'near_support': near_support,
        'near_resistance': near_resistance,
        'bars': len(bars),
    }


def show_status():
    """Display current DOT status"""
    status = get_dot_status()
    if not status:
        print("❌ Could not fetch DOT status")
        return
    
    print()
    print("=" * 50)
    print("DOT S/R BOUNCE STATUS")
    print("=" * 50)
    print(f"Price:      ${status['price']:.4f}")
    print(f"RSI:        {status['rsi']:.1f}")
    print(f"Trend:      {status['trend'] or 'NONE'}")
    print(f"ATR (24h):  ${status['atr']:.4f} ({status['atr']/status['price']*100:.2f}%)")
    print()
    print("💰 Account:")
    print(f"   USD: ${status['usd_balance']:.2f}")
    print(f"   DOT: {status['dot_balance']:.4f}")
    print()
    print("📊 S/R Levels (24h):")
    print(f"   Support:    ${status['support']:.4f}" + (" 👈 NEAR" if status['near_support'] else ""))
    print(f"   Resistance: ${status['resistance']:.4f}" + (" 👈 NEAR" if status['near_resistance'] else ""))
    
    dist_sup = (status['price'] - status['support']) / status['price'] * 100
    dist_res = (status['resistance'] - status['price']) / status['price'] * 100
    print(f"   Distance to support:    {dist_sup:.1f}%")
    print(f"   Distance to resistance: {dist_res:.1f}%")
    
    # Check if Friday (skip day)
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).weekday()
    if today == 4:
        print("⚠️  FRIDAY - No trades (skip day)")
        print()
        return
    
    print()
    if status['signal']:
        print(f"🚨 SIGNAL: {status['signal']}")
        stop_dist = status['atr'] * 2.0
        target_dist = status['atr'] * 4.0
        if 'LONG' in status['signal']:
            print(f"   Entry:  ${status['price']:.4f}")
            print(f"   Stop:   ${status['price'] - stop_dist:.4f} (-{stop_dist/status['price']*100:.1f}%)")
            print(f"   Target: ${status['price'] + target_dist:.4f} (+{target_dist/status['price']*100:.1f}%)")
        else:
            print(f"   Entry:  ${status['price']:.4f}")
            print(f"   Stop:   ${status['price'] + stop_dist:.4f} (+{stop_dist/status['price']*100:.1f}%)")
            print(f"   Target: ${status['price'] - target_dist:.4f} (-{target_dist/status['price']*100:.1f}%)")
    else:
        print("📊 No signal - waiting for S/R touch with trend alignment")
    print()


def run_shadow(interval_minutes: int = 5):
    """Run shadow trading - log signals without executing"""
    print("=" * 60)
    print("DOT S/R BOUNCE - SHADOW TRADING")
    print("Strategy: 2:4 R:R (no trailing)")
    print(f"Check interval: {interval_minutes} minutes")
    print("=" * 60)
    
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    last_signal = None
    
    try:
        while True:
            status = get_dot_status()
            if not status:
                print(f"[{datetime.now(timezone.utc).strftime('%H:%M')}] Error fetching status")
                time.sleep(interval_minutes * 60)
                continue
            
            now = datetime.now(timezone.utc).strftime('%H:%M')
            
            # Log if signal changed
            if status['signal'] and status['signal'] != last_signal:
                print(f"\n[{now}] 🚨 NEW SIGNAL: {status['signal']}")
                print(f"   Price: ${status['price']:.4f}")
                print(f"   RSI: {status['rsi']:.1f}")
                print(f"   Trend: {status['trend']}")
                
                # Log to file
                with open(log_dir / 'dot_signals.jsonl', 'a') as f:
                    f.write(json.dumps({
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'signal': status['signal'],
                        'price': status['price'],
                        'rsi': status['rsi'],
                        'trend': status['trend'],
                        'support': status['support'],
                        'resistance': status['resistance'],
                    }) + '\n')
                
                last_signal = status['signal']
            elif not status['signal']:
                last_signal = None
                print(f"[{now}] DOT ${status['price']:.4f} | RSI {status['rsi']:.0f} | No signal", end='\r')
            
            time.sleep(interval_minutes * 60)
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Shadow trading stopped.")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='DOT S/R Bounce Trading')
    parser.add_argument('command', nargs='?', default='status', 
                       choices=['status', 'shadow'],
                       help='Command: status or shadow')
    parser.add_argument('--interval', type=int, default=5,
                       help='Check interval in minutes (shadow mode)')
    
    args = parser.parse_args()
    
    if args.command == 'status':
        show_status()
    elif args.command == 'shadow':
        run_shadow(args.interval)
