#!/usr/bin/env python3
"""
Parameter sweep for crypto S/R bounce.
Find optimal trail settings (or confirm fixed target is better).
"""

import pandas as pd
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

from backtest import run_backtest, Direction, Trade
from config import StrategyConfig
from data import load_data

def run_sweep(df: pd.DataFrame, symbol: str):
    """Sweep trail parameters"""
    
    results = []
    
    # Test configurations
    configs = [
        # Baseline: no trail
        {'use_trailing_stop': False, 'label': 'No Trail (baseline)'},
        
        # Trail variations
        {'use_trailing_stop': True, 'trail_activation_atr': 0.5, 'trail_distance_atr': 0.2, 'label': 'Trail 0.5/0.2'},
        {'use_trailing_stop': True, 'trail_activation_atr': 1.0, 'trail_distance_atr': 0.3, 'label': 'Trail 1.0/0.3'},
        {'use_trailing_stop': True, 'trail_activation_atr': 1.0, 'trail_distance_atr': 0.5, 'label': 'Trail 1.0/0.5'},
        {'use_trailing_stop': True, 'trail_activation_atr': 1.5, 'trail_distance_atr': 0.5, 'label': 'Trail 1.5/0.5'},
        {'use_trailing_stop': True, 'trail_activation_atr': 1.5, 'trail_distance_atr': 0.75, 'label': 'Trail 1.5/0.75'},
        {'use_trailing_stop': True, 'trail_activation_atr': 2.0, 'trail_distance_atr': 0.5, 'label': 'Trail 2.0/0.5 (at target)'},
        
        # Different stop/target ratios
        {'use_trailing_stop': False, 'stop_atr_mult': 1.0, 'target_atr_mult': 2.0, 'label': '1:2 R:R'},
        {'use_trailing_stop': False, 'stop_atr_mult': 1.0, 'target_atr_mult': 3.0, 'label': '1:3 R:R'},
        {'use_trailing_stop': False, 'stop_atr_mult': 1.5, 'target_atr_mult': 3.0, 'label': '1.5:3 R:R'},
        {'use_trailing_stop': False, 'stop_atr_mult': 2.0, 'target_atr_mult': 4.0, 'label': '2:4 R:R'},
        
        # Tighter S/R
        {'use_trailing_stop': False, 'sr_lookback': 12, 'label': '12h S/R'},
        {'use_trailing_stop': False, 'sr_lookback': 48, 'label': '48h S/R'},
        
        # No round number blend
        {'use_trailing_stop': False, 'use_round_number_sr': False, 'label': 'No round #s'},
    ]
    
    for cfg in configs:
        label = cfg.pop('label')
        
        # Base hourly config
        config = StrategyConfig(
            sr_lookback=24,
            trend_lookback=72,
            atr_period=24,
            stop_atr_mult=1.5,
            target_atr_mult=2.0,
            trail_activation_atr=1.0,
            trail_distance_atr=0.3,
            max_hold_bars=24,
            min_gap_bars=6,
            rsi_exit_high=65,
            rsi_exit_low=35,
            use_trailing_stop=True,
            use_round_number_sr=True,
        )
        
        # Apply overrides
        for k, v in cfg.items():
            setattr(config, k, v)
        
        trades, stats = run_backtest(df, config)
        
        if trades:
            wins = sum(1 for t in trades if t.pnl_pct > 0)
            total_pnl = sum(t.pnl_pct for t in trades)
            wr = wins / len(trades) * 100
            
            gp = sum(t.pnl_pct for t in trades if t.pnl_pct > 0)
            gl = abs(sum(t.pnl_pct for t in trades if t.pnl_pct < 0)) or 0.001
            pf = gp / gl
            
            results.append({
                'config': label,
                'trades': len(trades),
                'wr': wr,
                'pnl_pct': total_pnl,
                'pf': pf,
            })
        else:
            results.append({
                'config': label,
                'trades': 0,
                'wr': 0,
                'pnl_pct': 0,
                'pf': 0,
            })
    
    # Sort by P&L
    results = sorted(results, key=lambda x: -x['pnl_pct'])
    
    print(f"\n{'='*70}")
    print(f"{symbol} PARAMETER SWEEP")
    print(f"{'='*70}")
    print(f"{'Config':<25} {'Trades':>8} {'WR':>8} {'P&L':>12} {'PF':>8}")
    print("-" * 70)
    
    for r in results:
        print(f"{r['config']:<25} {r['trades']:>8} {r['wr']:>7.1f}% {r['pnl_pct']:>11.1f}% {r['pf']:>8.2f}")
    
    return results


def main():
    print("="*60)
    print("CRYPTO S/R BOUNCE - PARAMETER SWEEP")
    print("="*60)
    
    for filepath, symbol in [('data/BTCUSD_1h_730d.csv', 'BTC'), ('data/ETHUSD_1h_730d.csv', 'ETH')]:
        if not os.path.exists(filepath):
            print(f"Missing {filepath}")
            continue
        
        df = load_data(filepath)
        print(f"\n{symbol}: {len(df):,} bars")
        run_sweep(df, symbol)


if __name__ == '__main__':
    main()
