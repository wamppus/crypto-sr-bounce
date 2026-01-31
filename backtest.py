#!/usr/bin/env python3
"""
Crypto S/R Bounce Backtester

Ported from ES S/R Bounce V3 with crypto-specific adaptations:
- ATR-based stops (not fixed points)
- 24/7 market (no RTH filter)
- Round number S/R awareness
- Session-based filtering (optional)

The EDGE: Runner mode with trailing stop at S/R bounces.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import sys
import os

# Add bot to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))
from config import StrategyConfig, VALIDATED_CONFIG
from data import calculate_atr, get_round_levels, get_session


class Direction(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass 
class Trade:
    entry_time: datetime
    exit_time: datetime
    direction: str
    entry: float
    exit: float
    pnl_pct: float  # Percentage P&L (crypto standard)
    pnl_usd: float  # USD P&L (for $10K account reference)
    reason: str
    atr_at_entry: float


class CryptoSRBounce:
    """
    Crypto S/R Bounce Strategy
    
    Core logic ported from ES V3, adapted for crypto markets.
    """
    
    def __init__(self, config: StrategyConfig = None):
        self.config = config or VALIDATED_CONFIG
        self.bars: List[dict] = []
        self.current_atr: float = 0.0
        self.current_rsi: float = 50.0
        
        # Stats
        self.signals_generated = 0
        self.filtered_by_trend = 0
        self.filtered_by_session = 0
    
    def _calculate_rsi(self) -> float:
        """Calculate RSI from recent closes"""
        period = self.config.rsi_period
        if len(self.bars) < period + 1:
            return 50.0
        
        closes = [b['close'] for b in self.bars[-(period + 1):]]
        deltas = np.diff(closes)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_atr(self) -> float:
        """Calculate ATR from recent bars"""
        period = self.config.atr_period
        if len(self.bars) < period + 1:
            return 0.0
        
        recent = self.bars[-(period + 1):]
        tr_values = []
        
        for i in range(1, len(recent)):
            high = recent[i]['high']
            low = recent[i]['low']
            prev_close = recent[i-1]['close']
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)
        
        return np.mean(tr_values)
    
    def _get_sr_levels(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Get support and resistance from last N bars.
        Optionally blend with round number levels.
        """
        if len(self.bars) < self.config.sr_lookback:
            return None, None
        
        recent = self.bars[-self.config.sr_lookback:]
        bar_support = min(b['low'] for b in recent)
        bar_resistance = max(b['high'] for b in recent)
        
        if not self.config.use_round_number_sr:
            return bar_support, bar_resistance
        
        # Blend with round numbers
        current_price = self.bars[-1]['close']
        round_levels = get_round_levels(current_price)
        
        # Find nearest round support (below price) and resistance (above price)
        round_supports = [l['level'] for l in round_levels if l['level'] < current_price]
        round_resistances = [l['level'] for l in round_levels if l['level'] > current_price]
        
        # Weighted blend
        w = self.config.round_number_weight
        if round_supports:
            nearest_round_support = max(round_supports)
            support = bar_support * (1 - w) + nearest_round_support * w
        else:
            support = bar_support
            
        if round_resistances:
            nearest_round_resistance = min(round_resistances)
            resistance = bar_resistance * (1 - w) + nearest_round_resistance * w
        else:
            resistance = bar_resistance
        
        return support, resistance
    
    def _get_trend(self) -> Optional[str]:
        """
        Determine trend from last N bars.
        Returns 'UP', 'DOWN', or None (no clear trend)
        """
        if len(self.bars) < self.config.trend_lookback:
            return None
        
        recent = self.bars[-self.config.trend_lookback:]
        half = self.config.trend_lookback // 2
        first_half = recent[:half]
        second_half = recent[half:]
        
        first_avg = np.mean([b['close'] for b in first_half])
        second_avg = np.mean([b['close'] for b in second_half])
        
        first_high = max(b['high'] for b in first_half)
        second_high = max(b['high'] for b in second_half)
        first_low = min(b['low'] for b in first_half)
        second_low = min(b['low'] for b in second_half)
        
        # Trend UP: higher highs AND higher lows AND price rising
        if second_high > first_high and second_low > first_low and second_avg > first_avg:
            return 'UP'
        
        # Trend DOWN: lower highs AND lower lows AND price falling
        if second_high < first_high and second_low < first_low and second_avg < first_avg:
            return 'DOWN'
        
        return None
    
    def _get_contrarian_direction(self) -> Optional[str]:
        """Get direction of last N bars for contrarian trade."""
        if len(self.bars) < self.config.ct_bars:
            return None
        
        bar1 = self.bars[-self.config.ct_bars]
        bar2 = self.bars[-1]
        
        move = bar2['close'] - bar1['open']
        
        if move > 0:
            return 'UP'
        elif move < 0:
            return 'DOWN'
        return None
    
    def check_signal(self, bar: dict) -> Optional[Direction]:
        """Check for entry signal based on S/R touch + trend filter."""
        support, resistance = self._get_sr_levels()
        if support is None or resistance is None:
            return None
        
        if self.current_atr <= 0:
            return None
        
        # Session filter
        if self.config.use_session_filter:
            session = get_session(bar['timestamp'].hour)
            if session not in self.config.allowed_sessions:
                self.filtered_by_session += 1
                return None
        
        close = bar['close']
        low = bar['low']
        high = bar['high']
        
        # Tolerance based on percentage of price
        tolerance = close * (self.config.sr_tolerance_pct / 100)
        
        near_support = low <= support + tolerance
        near_resistance = high >= resistance - tolerance
        
        if not near_support and not near_resistance:
            return None
        
        # Get trend
        trend = self._get_trend() if self.config.use_trend_filter else None
        
        direction = None
        
        if near_support:
            if trend == 'UP':
                direction = Direction.LONG
            elif trend == 'DOWN':
                self.filtered_by_trend += 1
                direction = None
            elif self.config.use_ct_filter:
                last_dir = self._get_contrarian_direction()
                if last_dir == 'DOWN':
                    direction = Direction.LONG
        
        if near_resistance:
            if trend == 'DOWN':
                direction = Direction.SHORT
            elif trend == 'UP':
                self.filtered_by_trend += 1
                direction = None
            elif self.config.use_ct_filter:
                last_dir = self._get_contrarian_direction()
                if last_dir == 'UP':
                    direction = Direction.SHORT
        
        if direction:
            self.signals_generated += 1
        
        return direction
    
    def check_rsi_exit(self, direction: str) -> bool:
        """Check if RSI signals exit"""
        if direction == 'long' and self.current_rsi > self.config.rsi_exit_high:
            return True
        if direction == 'short' and self.current_rsi < self.config.rsi_exit_low:
            return True
        return False
    
    def on_bar(self, bar: dict):
        """Process a bar and update state"""
        self.bars.append(bar)
        max_bars = max(
            self.config.sr_lookback,
            self.config.trend_lookback,
            self.config.rsi_period,
            self.config.atr_period
        ) + 20
        
        if len(self.bars) > max_bars:
            self.bars.pop(0)
        
        self.current_rsi = self._calculate_rsi()
        self.current_atr = self._calculate_atr()


def run_backtest(
    df: pd.DataFrame,
    config: StrategyConfig = None,
    account_size: float = 10000.0,
    verbose: bool = False,
) -> Tuple[List[Trade], dict]:
    """
    Run backtest with crypto S/R bounce strategy.
    
    Args:
        df: DataFrame with OHLCV data
        config: Strategy configuration
        account_size: Reference account size for USD P&L
        verbose: Print progress
        
    Returns:
        List of trades and stats dict
    """
    config = config or VALIDATED_CONFIG
    strategy = CryptoSRBounce(config)
    
    trades = []
    active_trade = None
    last_trade_bar = -config.min_gap_bars
    
    # Exit reason counts
    exit_counts = {'trail': 0, 'target': 0, 'stop': 0, 'time': 0, 'rsi': 0}
    
    for bar_idx, row in enumerate(df.itertuples()):
        bar = {
            'timestamp': row.timestamp,
            'open': row.open,
            'high': row.high,
            'low': row.low,
            'close': row.close,
            'volume': getattr(row, 'volume', 0),
        }
        
        strategy.on_bar(bar)
        
        # Need ATR before trading
        if strategy.current_atr <= 0:
            continue
        
        # --- Exit Logic ---
        if active_trade:
            exit_price = None
            exit_reason = None
            
            current_price = bar['close']
            atr = active_trade['atr']
            
            if active_trade['direction'] == 'long':
                current_profit = current_price - active_trade['entry']
            else:
                current_profit = active_trade['entry'] - current_price
            
            # Runner Mode: Trailing stop
            if config.use_trailing_stop:
                trail_activation = atr * config.trail_activation_atr
                trail_distance = atr * config.trail_distance_atr
                
                # Activate trail
                if not active_trade.get('trail_active') and current_profit >= trail_activation:
                    active_trade['trail_active'] = True
                    if active_trade['direction'] == 'long':
                        active_trade['stop'] = current_price - trail_distance
                    else:
                        active_trade['stop'] = current_price + trail_distance
                
                # Update trail
                if active_trade.get('trail_active'):
                    if active_trade['direction'] == 'long':
                        new_stop = current_price - trail_distance
                        if new_stop > active_trade['stop']:
                            active_trade['stop'] = new_stop
                    else:
                        new_stop = current_price + trail_distance
                        if new_stop < active_trade['stop']:
                            active_trade['stop'] = new_stop
                    
                    # Full runner mode after target hit
                    target_profit = atr * config.target_atr_mult
                    if current_profit >= target_profit:
                        active_trade['runner_mode'] = True
            
            # RSI exit (not in runner mode)
            if not active_trade.get('runner_mode'):
                if strategy.check_rsi_exit(active_trade['direction']):
                    exit_price = bar['close']
                    exit_reason = 'rsi'
            
            # Stop/Target check
            if not exit_price:
                if active_trade['direction'] == 'long':
                    if bar['low'] <= active_trade['stop']:
                        exit_price = active_trade['stop']
                        exit_reason = 'trail' if active_trade.get('trail_active') else 'stop'
                    elif not active_trade.get('runner_mode') and bar['high'] >= active_trade['target']:
                        exit_price = active_trade['target']
                        exit_reason = 'target'
                else:
                    if bar['high'] >= active_trade['stop']:
                        exit_price = active_trade['stop']
                        exit_reason = 'trail' if active_trade.get('trail_active') else 'stop'
                    elif not active_trade.get('runner_mode') and bar['low'] <= active_trade['target']:
                        exit_price = active_trade['target']
                        exit_reason = 'target'
            
            # Time exit (not in runner mode)
            if not active_trade.get('runner_mode'):
                if not exit_price and bar_idx - active_trade['entry_bar'] >= config.max_hold_bars:
                    exit_price = bar['close']
                    exit_reason = 'time'
            
            if exit_price:
                if active_trade['direction'] == 'long':
                    pnl_pct = (exit_price - active_trade['entry']) / active_trade['entry'] * 100
                else:
                    pnl_pct = (active_trade['entry'] - exit_price) / active_trade['entry'] * 100
                
                pnl_usd = account_size * (pnl_pct / 100)
                
                trades.append(Trade(
                    entry_time=active_trade['entry_time'],
                    exit_time=bar['timestamp'],
                    direction=active_trade['direction'],
                    entry=active_trade['entry'],
                    exit=exit_price,
                    pnl_pct=pnl_pct,
                    pnl_usd=pnl_usd,
                    reason=exit_reason,
                    atr_at_entry=active_trade['atr'],
                ))
                exit_counts[exit_reason] = exit_counts.get(exit_reason, 0) + 1
                active_trade = None
                last_trade_bar = bar_idx
        
        # --- Entry Logic ---
        if active_trade:
            continue
        
        if bar_idx - last_trade_bar < config.min_gap_bars:
            continue
        
        signal = strategy.check_signal(bar)
        if signal:
            entry_price = bar['close']
            atr = strategy.current_atr
            
            if signal == Direction.LONG:
                stop = entry_price - (atr * config.stop_atr_mult)
                target = entry_price + (atr * config.target_atr_mult)
            else:
                stop = entry_price + (atr * config.stop_atr_mult)
                target = entry_price - (atr * config.target_atr_mult)
            
            active_trade = {
                'entry_time': bar['timestamp'],
                'entry_bar': bar_idx,
                'direction': signal.value,
                'entry': entry_price,
                'stop': stop,
                'target': target,
                'atr': atr,
            }
    
    stats = {
        'signals': strategy.signals_generated,
        'trades': len(trades),
        'filtered_trend': strategy.filtered_by_trend,
        'filtered_session': strategy.filtered_by_session,
        'exit_counts': exit_counts,
    }
    
    return trades, stats


def analyze(trades: List[Trade], label: str, stats: dict) -> Optional[dict]:
    """Analyze and print backtest results"""
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"Signals: {stats['signals']}, Trades: {stats['trades']}")
    
    if not trades:
        print("No trades!")
        return None
    
    # Convert to DataFrame
    df = pd.DataFrame([{
        'pnl_pct': t.pnl_pct,
        'pnl_usd': t.pnl_usd,
        'direction': t.direction,
        'reason': t.reason,
    } for t in trades])
    
    total = len(df)
    wins = len(df[df['pnl_pct'] > 0])
    wr = wins / total * 100
    
    total_pnl_pct = df['pnl_pct'].sum()
    total_pnl_usd = df['pnl_usd'].sum()
    
    gp = df[df['pnl_pct'] > 0]['pnl_pct'].sum() if wins else 0
    gl = abs(df[df['pnl_pct'] < 0]['pnl_pct'].sum()) if total - wins else 0.001
    pf = gp / gl
    
    equity = df['pnl_usd'].cumsum()
    drawdown = equity - equity.cummax()
    max_dd = drawdown.min()
    
    print(f"\nTrades: {total} (W: {wins}, L: {total - wins})")
    print(f"Win Rate: {wr:.1f}%")
    print(f"Total P&L: {total_pnl_pct:.1f}% (${total_pnl_usd:,.0f} on $10K)")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Max Drawdown: ${max_dd:,.0f}")
    
    print(f"\nBy Exit Reason:")
    for reason in ['trail', 'target', 'stop', 'time', 'rsi']:
        subset = df[df['reason'] == reason]
        if len(subset) > 0:
            r_pnl = subset['pnl_pct'].sum()
            r_wr = len(subset[subset['pnl_pct'] > 0]) / len(subset) * 100
            print(f"  {reason}: {len(subset)} trades, {r_pnl:.1f}%, {r_wr:.0f}% WR")
    
    print(f"\nBy Direction:")
    for direction in ['long', 'short']:
        subset = df[df['direction'] == direction]
        if len(subset) > 0:
            d_pnl = subset['pnl_pct'].sum()
            d_wr = len(subset[subset['pnl_pct'] > 0]) / len(subset) * 100
            print(f"  {direction}: {len(subset)} trades, {d_pnl:.1f}%, {d_wr:.0f}% WR")
    
    return {
        'trades': total,
        'wr': wr,
        'pnl_pct': total_pnl_pct,
        'pnl_usd': total_pnl_usd,
        'pf': pf,
        'max_dd': max_dd,
    }


def main():
    """Main entry point"""
    print("="*60)
    print("CRYPTO S/R BOUNCE BACKTESTER")
    print("Ported from ES V3 with crypto adaptations")
    print("="*60)
    
    # Check for data
    data_path = 'data/BTCUSDT_5m_365d.csv'
    
    if not os.path.exists(data_path):
        print(f"\n⚠️  No data found at {data_path}")
        print("\nTo fetch data, run:")
        print("  pip install ccxt")
        print("  python -m bot.data --symbol BTC/USDT --timeframe 5m --days 365")
        print("\nOr provide your own CSV with columns: timestamp, open, high, low, close, volume")
        return
    
    print(f"\nLoading data from {data_path}...")
    from data import load_data
    df = load_data(data_path)
    
    print(f"Bars: {len(df):,}")
    print(f"Range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"Price: ${df['close'].iloc[0]:,.0f} → ${df['close'].iloc[-1]:,.0f}")
    
    # Run with validated config
    print(f"\nConfig: {VALIDATED_CONFIG}")
    
    trades, stats = run_backtest(df, VALIDATED_CONFIG)
    result = analyze(trades, "VALIDATED CONFIG (V3 Port)", stats)
    
    # Compare with/without trailing stop
    if result:
        print(f"\n{'='*60}")
        print("TRAILING STOP COMPARISON")
        print(f"{'='*60}")
        
        no_trail_config = StrategyConfig(use_trailing_stop=False)
        trades_nt, stats_nt = run_backtest(df, no_trail_config)
        result_nt = analyze(trades_nt, "NO TRAILING (baseline)", stats_nt)
        
        if result_nt:
            print(f"\n📊 Trail Impact:")
            print(f"  Win Rate: {result_nt['wr']:.1f}% → {result['wr']:.1f}%")
            print(f"  P&L: ${result_nt['pnl_usd']:,.0f} → ${result['pnl_usd']:,.0f}")
            print(f"  PF: {result_nt['pf']:.2f} → {result['pf']:.2f}")


if __name__ == '__main__':
    main()
