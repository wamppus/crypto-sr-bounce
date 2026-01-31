#!/usr/bin/env python3
"""
Shadow Trading: Donchian Breakout + Runner Mode

Monitors multiple assets, logs signals, tracks paper P&L.
Does NOT execute real trades.

Usage:
    python shadow_donchian.py [--assets DOT,BTC,ETH] [--interval 60]
"""

import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

from donchian_strategy import DonchianStrategy, VALIDATED_CONFIG, DonchianConfig

# Config
DEFAULT_ASSETS = ['DOT', 'BTC', 'ETH']
KRAKEN_PAIRS = {
    'DOT': 'DOTUSD',
    'BTC': 'XBTUSD',
    'ETH': 'ETHUSD',
    'SOL': 'SOLUSD',
    'XRP': 'XRPUSD',
}

LOG_DIR = Path(__file__).parent / 'logs' / 'shadow'
STATE_FILE = Path(__file__).parent / 'logs' / 'shadow_state.json'


class ShadowTrader:
    """Shadow trader for multiple assets"""
    
    def __init__(self, assets: list, config: DonchianConfig = None):
        self.assets = assets
        self.config = config or VALIDATED_CONFIG
        
        # Strategy instance per asset
        self.strategies = {asset: DonchianStrategy(self.config) for asset in assets}
        
        # Paper trading state
        self.positions = {}  # asset -> position dict
        self.trades = []     # completed trades
        self.equity = 10000  # Starting paper equity
        
        # Setup logging
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        # Load saved state
        self._load_state()
    
    def _load_state(self):
        """Load state from file"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
                self.trades = state.get('trades', [])
                self.equity = state.get('equity', 10000)
                print(f"Loaded state: {len(self.trades)} trades, ${self.equity:.2f} equity")
            except Exception as e:
                print(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Save state to file"""
        try:
            state = {
                'trades': self.trades[-1000:],  # Keep last 1000
                'equity': self.equity,
                'last_update': datetime.now(timezone.utc).isoformat()
            }
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Failed to save state: {e}")
    
    def fetch_ohlc(self, asset: str, interval: int = 60) -> list:
        """Fetch OHLC data from Kraken"""
        pair = KRAKEN_PAIRS.get(asset, f'{asset}USD')
        
        try:
            url = 'https://api.kraken.com/0/public/OHLC'
            params = {'pair': pair, 'interval': interval}
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            
            if data.get('error'):
                print(f"Kraken error for {asset}: {data['error']}")
                return []
            
            # Find the right key in result
            result_key = None
            for key in data.get('result', {}):
                if key != 'last':
                    result_key = key
                    break
            
            if not result_key:
                return []
            
            bars = []
            for row in data['result'][result_key]:
                bars.append({
                    'timestamp': datetime.fromtimestamp(row[0], tz=timezone.utc),
                    'open': float(row[1]),
                    'high': float(row[2]),
                    'low': float(row[3]),
                    'close': float(row[4]),
                    'volume': float(row[6])
                })
            
            return bars
            
        except Exception as e:
            print(f"Error fetching {asset}: {e}")
            return []
    
    def process_asset(self, asset: str) -> dict:
        """Process one asset, return any signal"""
        bars = self.fetch_ohlc(asset)
        
        if not bars:
            return None
        
        strategy = self.strategies[asset]
        last_ts = self.last_bar_ts.get(asset)
        
        # Only process NEW bars
        signal = None
        for bar in bars:
            if last_ts and bar['timestamp'] <= last_ts:
                continue  # Skip already-processed bars
            
            sig = strategy.add_bar(bar)
            if sig:
                signal = sig
                signal['asset'] = asset
                signal['timestamp'] = bar['timestamp'].isoformat()
            
            self.last_bar_ts[asset] = bar['timestamp']
        
        return signal
    
    def log_signal(self, signal: dict):
        """Log signal to file and console"""
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        asset = signal['asset']
        action = signal['action'].upper()
        direction = signal.get('direction', '').upper()
        price = signal.get('price', 0)
        
        if action == 'ENTRY':
            stop = signal.get('stop', 0)
            reason = signal.get('reason', '')
            msg = f"[{ts}] 🚀 {asset} {direction} ENTRY @ ${price:.4f} | Stop: ${stop:.4f} | {reason}"
            
            # Track paper position
            self.positions[asset] = {
                'direction': direction,
                'entry': price,
                'stop': stop,
                'time': ts
            }
            
        elif action == 'EXIT':
            pnl_pct = signal.get('pnl_pct', 0)
            reason = signal.get('reason', '')
            emoji = '✅' if pnl_pct > 0 else '❌'
            msg = f"[{ts}] {emoji} {asset} {direction} EXIT @ ${price:.4f} | P&L: {pnl_pct:+.2f}% | {reason}"
            
            # Update paper equity
            if asset in self.positions:
                # Simple: risk 1% per trade
                risk_amt = self.equity * 0.01
                pnl_amt = risk_amt * (pnl_pct / 100) * (self.config.stop_atr_mult)
                self.equity += pnl_amt
                
                self.trades.append({
                    'asset': asset,
                    'direction': direction,
                    'entry': self.positions[asset]['entry'],
                    'exit': price,
                    'pnl_pct': pnl_pct,
                    'pnl_amt': pnl_amt,
                    'reason': reason,
                    'time': ts
                })
                
                del self.positions[asset]
        else:
            msg = f"[{ts}] {asset}: {signal}"
        
        print(msg)
        
        # Log to file
        log_file = LOG_DIR / f"shadow_{datetime.now().strftime('%Y-%m-%d')}.log"
        with open(log_file, 'a') as f:
            f.write(msg + '\n')
        
        self._save_state()
    
    def get_summary(self) -> str:
        """Get current status summary"""
        lines = [
            f"\n{'='*50}",
            f"SHADOW TRADING STATUS - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            f"{'='*50}",
            f"Paper Equity: ${self.equity:,.2f}",
            f"Total Trades: {len(self.trades)}",
        ]
        
        if self.trades:
            wins = sum(1 for t in self.trades if t['pnl_pct'] > 0)
            total_pnl = sum(t['pnl_pct'] for t in self.trades)
            lines.append(f"Win Rate: {wins/len(self.trades)*100:.1f}%")
            lines.append(f"Total P&L: {total_pnl:+.1f}%")
        
        lines.append(f"\nOpen Positions:")
        if self.positions:
            for asset, pos in self.positions.items():
                lines.append(f"  {asset}: {pos['direction']} @ ${pos['entry']:.4f}")
        else:
            lines.append("  (none)")
        
        lines.append(f"\nStrategy Status:")
        for asset, strat in self.strategies.items():
            status = strat.get_status()
            lines.append(f"  {asset}: {status['bars_loaded']} bars, {status['signals_generated']} signals")
        
        lines.append(f"{'='*50}\n")
        
        return '\n'.join(lines)
    
    def run(self, interval_minutes: int = 60):
        """Main loop"""
        print(f"Starting shadow trading: {', '.join(self.assets)}")
        print(f"Interval: {interval_minutes} minutes")
        print(f"Config: entry={self.config.entry_period}h, exit={self.config.exit_period}h, "
              f"stop={self.config.stop_atr_mult}x ATR, trail={self.config.trail_atr_mult}x ATR")
        print()
        
        # Initial load (silent - don't log historical signals)
        self.last_bar_ts = {}
        for asset in self.assets:
            print(f"Loading {asset} history...")
            bars = self.fetch_ohlc(asset)
            if bars:
                for bar in bars:
                    self.strategies[asset].add_bar(bar)  # Build up state, ignore signals
                self.last_bar_ts[asset] = bars[-1]['timestamp']
                print(f"  Loaded {len(bars)} bars, last: {self.last_bar_ts[asset]}")
        
        print(self.get_summary())
        
        while True:
            try:
                for asset in self.assets:
                    signal = self.process_asset(asset)
                    if signal:
                        self.log_signal(signal)
                
                # Summary every hour
                if datetime.now().minute == 0:
                    print(self.get_summary())
                
                # Sleep until next check
                time.sleep(interval_minutes * 60)
                
            except KeyboardInterrupt:
                print("\nShutting down...")
                self._save_state()
                print(self.get_summary())
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description='Shadow trade Donchian breakout strategy')
    parser.add_argument('--assets', type=str, default='DOT,BTC,ETH',
                       help='Comma-separated assets to trade')
    parser.add_argument('--interval', type=int, default=60,
                       help='Check interval in minutes (default: 60)')
    parser.add_argument('--status', action='store_true',
                       help='Show status and exit')
    
    args = parser.parse_args()
    assets = [a.strip().upper() for a in args.assets.split(',')]
    
    trader = ShadowTrader(assets)
    
    if args.status:
        print(trader.get_summary())
        return
    
    trader.run(args.interval)


if __name__ == '__main__':
    main()
