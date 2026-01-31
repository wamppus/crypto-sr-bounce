#!/usr/bin/env python3
"""
Crypto S/R Bounce - Live Strategy

Real-time trading strategy using Hyperliquid.
Based on backtest findings: 2:4 R:R with fixed targets (no trailing).
"""

import time
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from pathlib import Path

from config import StrategyConfig
from exchange_client import HyperliquidClient, ShadowClient, Position, OrderResult
from data import calculate_atr, get_session


@dataclass
class ActiveTrade:
    """Track an active trade"""
    coin: str
    direction: str  # 'long' or 'short'
    entry_price: float
    entry_time: datetime
    stop_price: float
    target_price: float
    size: float
    atr_at_entry: float


@dataclass
class BarData:
    """OHLCV bar"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


class LiveStrategy:
    """
    Live trading strategy for crypto S/R bounce.
    
    Uses hourly bars, checks every minute for trade management.
    """
    
    def __init__(
        self,
        client: HyperliquidClient,
        coin: str = 'BTC',
        config: StrategyConfig = None,
        shadow: bool = True,
        log_dir: str = 'logs',
    ):
        self.coin = coin.upper()
        self.config = config or self._default_config()
        self.shadow = shadow
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Wrap in shadow client if paper trading
        if shadow:
            self.client = ShadowClient(client, str(self.log_dir / 'shadow_trades.jsonl'))
        else:
            self.client = client
        
        # State
        self.bars: list[BarData] = []
        self.active_trade: Optional[ActiveTrade] = None
        self.current_atr: float = 0.0
        self.current_rsi: float = 50.0
        
        # Stats
        self.trades_today = 0
        self.daily_pnl = 0.0
        
        # Load state if exists
        self._load_state()
    
    def _default_config(self) -> StrategyConfig:
        """Best config from backtesting"""
        return StrategyConfig(
            sr_lookback=24,
            trend_lookback=72,
            atr_period=24,
            stop_atr_mult=2.0,      # 2x ATR stop
            target_atr_mult=4.0,    # 4x ATR target (2:4 R:R)
            max_hold_bars=48,       # 48 hours max
            min_gap_bars=6,
            rsi_exit_high=70,
            rsi_exit_low=30,
            use_trailing_stop=False,  # KEY: No trailing on crypto
            use_round_number_sr=False,
        )
    
    def _load_state(self):
        """Load persisted state"""
        state_file = self.log_dir / f'{self.coin}_state.json'
        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)
                
                if state.get('active_trade'):
                    t = state['active_trade']
                    self.active_trade = ActiveTrade(
                        coin=t['coin'],
                        direction=t['direction'],
                        entry_price=t['entry_price'],
                        entry_time=datetime.fromisoformat(t['entry_time']),
                        stop_price=t['stop_price'],
                        target_price=t['target_price'],
                        size=t['size'],
                        atr_at_entry=t['atr_at_entry'],
                    )
                
                self.bars = []  # Bars need to be refetched
                print(f"[{self.coin}] Loaded state: trade={'YES' if self.active_trade else 'NO'}")
                
            except Exception as e:
                print(f"[{self.coin}] Failed to load state: {e}")
    
    def _save_state(self):
        """Persist state for recovery"""
        state = {
            'coin': self.coin,
            'active_trade': asdict(self.active_trade) if self.active_trade else None,
            'current_atr': self.current_atr,
            'trades_today': self.trades_today,
            'daily_pnl': self.daily_pnl,
            'last_update': datetime.now(timezone.utc).isoformat(),
        }
        
        # Fix datetime serialization
        if state['active_trade']:
            state['active_trade']['entry_time'] = self.active_trade.entry_time.isoformat()
        
        state_file = self.log_dir / f'{self.coin}_state.json'
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def _log_event(self, event_type: str, **data):
        """Log an event"""
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'coin': self.coin,
            'event': event_type,
            **data,
        }
        
        log_file = self.log_dir / f'{self.coin}_events.jsonl'
        with open(log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')
        
        print(f"[{self.coin}] {event_type}: {data}")
    
    # === Indicators ===
    
    def _calculate_rsi(self, period: int = 14) -> float:
        """Calculate RSI"""
        if len(self.bars) < period + 1:
            return 50.0
        
        closes = [b.close for b in self.bars[-(period + 1):]]
        deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
        
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_atr(self, period: int = 24) -> float:
        """Calculate ATR"""
        if len(self.bars) < period + 1:
            return 0.0
        
        tr_values = []
        for i in range(-period, 0):
            bar = self.bars[i]
            prev_close = self.bars[i-1].close
            
            tr = max(
                bar.high - bar.low,
                abs(bar.high - prev_close),
                abs(bar.low - prev_close)
            )
            tr_values.append(tr)
        
        return sum(tr_values) / len(tr_values)
    
    def _get_sr_levels(self) -> tuple[Optional[float], Optional[float]]:
        """Get support/resistance from recent bars"""
        lookback = self.config.sr_lookback
        if len(self.bars) < lookback:
            return None, None
        
        recent = self.bars[-lookback:]
        support = min(b.low for b in recent)
        resistance = max(b.high for b in recent)
        
        return support, resistance
    
    def _get_trend(self) -> Optional[str]:
        """Determine trend"""
        lookback = self.config.trend_lookback
        if len(self.bars) < lookback:
            return None
        
        recent = self.bars[-lookback:]
        half = lookback // 2
        first_half = recent[:half]
        second_half = recent[half:]
        
        first_avg = sum(b.close for b in first_half) / len(first_half)
        second_avg = sum(b.close for b in second_half) / len(second_half)
        
        first_high = max(b.high for b in first_half)
        second_high = max(b.high for b in second_half)
        first_low = min(b.low for b in first_half)
        second_low = min(b.low for b in second_half)
        
        if second_high > first_high and second_low > first_low and second_avg > first_avg:
            return 'UP'
        if second_high < first_high and second_low < first_low and second_avg < first_avg:
            return 'DOWN'
        
        return None
    
    # === Signal Generation ===
    
    def check_entry_signal(self, current_price: float) -> Optional[str]:
        """Check for entry signal. Returns 'long', 'short', or None."""
        support, resistance = self._get_sr_levels()
        if support is None or resistance is None:
            return None
        
        if self.current_atr <= 0:
            return None
        
        # Tolerance based on ATR
        tolerance = self.current_atr * 0.5
        
        near_support = current_price <= support + tolerance
        near_resistance = current_price >= resistance - tolerance
        
        if not near_support and not near_resistance:
            return None
        
        trend = self._get_trend()
        
        if near_support:
            if trend == 'UP':
                return 'long'
            elif trend is None:
                # Contrarian check
                if len(self.bars) >= 2:
                    if self.bars[-1].close < self.bars[-2].open:
                        return 'long'
        
        if near_resistance:
            if trend == 'DOWN':
                return 'short'
            elif trend is None:
                if len(self.bars) >= 2:
                    if self.bars[-1].close > self.bars[-2].open:
                        return 'short'
        
        return None
    
    # === Trade Management ===
    
    def calculate_position_size(self, stop_distance: float) -> float:
        """Calculate position size based on risk"""
        balance = self.client.get_balance()
        if not balance:
            return 0.0
        
        equity = balance['equity']
        risk_amount = equity * (self.config.risk_per_trade_pct / 100)
        
        # Size = risk / stop distance (in price terms)
        current_price = self.client.get_price(self.coin)
        if not current_price:
            return 0.0
        
        # For perps, size is in base currency
        # stop_distance is in USD, so we need to convert
        stop_pct = stop_distance / current_price
        size_usd = risk_amount / stop_pct
        size = size_usd / current_price
        
        return round(size, 4)
    
    def enter_trade(self, direction: str):
        """Enter a new trade"""
        current_price = self.client.get_price(self.coin)
        if not current_price:
            self._log_event('ENTRY_FAILED', reason='No price')
            return
        
        atr = self.current_atr
        stop_distance = atr * self.config.stop_atr_mult
        target_distance = atr * self.config.target_atr_mult
        
        if direction == 'long':
            stop_price = current_price - stop_distance
            target_price = current_price + target_distance
        else:
            stop_price = current_price + stop_distance
            target_price = current_price - target_distance
        
        # Calculate size
        size = self.calculate_position_size(stop_distance)
        if size <= 0:
            self._log_event('ENTRY_FAILED', reason='Size too small')
            return
        
        # Execute entry
        if direction == 'long':
            result = self.client.market_buy(self.coin, size)
        else:
            result = self.client.market_sell(self.coin, size)
        
        if not result.success:
            self._log_event('ENTRY_FAILED', reason=result.error)
            return
        
        # Track trade
        self.active_trade = ActiveTrade(
            coin=self.coin,
            direction=direction,
            entry_price=result.filled_price or current_price,
            entry_time=datetime.now(timezone.utc),
            stop_price=stop_price,
            target_price=target_price,
            size=size,
            atr_at_entry=atr,
        )
        
        self._log_event('ENTRY', 
            direction=direction,
            price=self.active_trade.entry_price,
            size=size,
            stop=stop_price,
            target=target_price,
            atr=atr,
        )
        
        self.trades_today += 1
        self._save_state()
    
    def check_exit(self, current_price: float) -> Optional[str]:
        """Check if we should exit. Returns exit reason or None."""
        if not self.active_trade:
            return None
        
        trade = self.active_trade
        
        # Check stop
        if trade.direction == 'long':
            if current_price <= trade.stop_price:
                return 'stop'
            if current_price >= trade.target_price:
                return 'target'
        else:
            if current_price >= trade.stop_price:
                return 'stop'
            if current_price <= trade.target_price:
                return 'target'
        
        # Check RSI exit
        if trade.direction == 'long' and self.current_rsi > self.config.rsi_exit_high:
            return 'rsi'
        if trade.direction == 'short' and self.current_rsi < self.config.rsi_exit_low:
            return 'rsi'
        
        # Check time exit
        hours_held = (datetime.now(timezone.utc) - trade.entry_time).total_seconds() / 3600
        if hours_held >= self.config.max_hold_bars:
            return 'time'
        
        return None
    
    def exit_trade(self, reason: str):
        """Exit current trade"""
        if not self.active_trade:
            return
        
        trade = self.active_trade
        result = self.client.close_position(self.coin)
        
        if not result.success:
            self._log_event('EXIT_FAILED', reason=result.error)
            return
        
        exit_price = result.filled_price or self.client.get_price(self.coin)
        
        # Calculate P&L
        if trade.direction == 'long':
            pnl_pct = (exit_price - trade.entry_price) / trade.entry_price * 100
        else:
            pnl_pct = (trade.entry_price - exit_price) / trade.entry_price * 100
        
        pnl_usd = (pnl_pct / 100) * trade.size * trade.entry_price
        
        self._log_event('EXIT',
            reason=reason,
            entry_price=trade.entry_price,
            exit_price=exit_price,
            direction=trade.direction,
            size=trade.size,
            pnl_pct=round(pnl_pct, 2),
            pnl_usd=round(pnl_usd, 2),
            hours_held=round((datetime.now(timezone.utc) - trade.entry_time).total_seconds() / 3600, 1),
        )
        
        self.daily_pnl += pnl_usd
        self.active_trade = None
        self._save_state()
    
    # === Main Loop ===
    
    def update(self, bar: Optional[BarData] = None):
        """
        Main update function. Call with new bar data.
        If no bar provided, just checks current price for exit management.
        """
        # Update indicators if new bar
        if bar:
            self.bars.append(bar)
            # Keep enough history
            max_bars = max(self.config.sr_lookback, self.config.trend_lookback, 30) + 10
            if len(self.bars) > max_bars:
                self.bars.pop(0)
            
            self.current_atr = self._calculate_atr(self.config.atr_period)
            self.current_rsi = self._calculate_rsi(self.config.rsi_period)
        
        # Get current price
        current_price = self.client.get_price(self.coin)
        if not current_price:
            return
        
        # Check exit first
        if self.active_trade:
            exit_reason = self.check_exit(current_price)
            if exit_reason:
                self.exit_trade(exit_reason)
                return
        
        # Check entry (only on new bar, and if no position)
        if bar and not self.active_trade:
            signal = self.check_entry_signal(current_price)
            if signal:
                self.enter_trade(signal)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status"""
        price = self.client.get_price(self.coin)
        balance = self.client.get_balance()
        
        status = {
            'coin': self.coin,
            'price': price,
            'atr': round(self.current_atr, 2),
            'rsi': round(self.current_rsi, 1),
            'bars': len(self.bars),
            'balance': balance,
            'trades_today': self.trades_today,
            'daily_pnl': round(self.daily_pnl, 2),
            'shadow_mode': self.shadow,
        }
        
        if self.active_trade:
            trade = self.active_trade
            if price:
                if trade.direction == 'long':
                    unrealized_pnl = (price - trade.entry_price) / trade.entry_price * 100
                else:
                    unrealized_pnl = (trade.entry_price - price) / trade.entry_price * 100
            else:
                unrealized_pnl = 0
            
            status['position'] = {
                'direction': trade.direction,
                'entry': trade.entry_price,
                'stop': trade.stop_price,
                'target': trade.target_price,
                'size': trade.size,
                'unrealized_pnl': round(unrealized_pnl, 2),
            }
        else:
            status['position'] = None
        
        return status


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Crypto S/R Bounce Strategy')
    parser.add_argument('--coin', default='BTC', help='Coin to trade')
    parser.add_argument('--live', action='store_true', help='Live trading (default: shadow)')
    parser.add_argument('--status', action='store_true', help='Show status only')
    
    args = parser.parse_args()
    
    # Initialize client (read-only for now)
    client = HyperliquidClient(
        address='0x0000000000000000000000000000000000000000',
        testnet=True
    )
    
    strategy = LiveStrategy(
        client=client,
        coin=args.coin,
        shadow=not args.live,
    )
    
    if args.status:
        status = strategy.get_status()
        print(json.dumps(status, indent=2))
    else:
        print(f"Strategy ready for {args.coin}")
        print(f"Mode: {'LIVE' if args.live else 'SHADOW'}")
        print(f"Config: 2:4 R:R (no trailing)")
        print("\nCall strategy.update(bar) with new hourly bars")
