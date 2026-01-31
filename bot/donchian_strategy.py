"""
Donchian Channel Breakout + Runner Mode Strategy

Validated config v2 (2026-01-31):
- 0.50x ATR breakout filter: +61% total (was +40%)
- 79.2% win rate (was 69.4%)
- Filters marginal breakouts that fail
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Dict
from enum import Enum


class Direction(Enum):
    LONG = 1
    SHORT = -1


@dataclass
class DonchianConfig:
    """Strategy configuration"""
    # Channel periods (in bars/hours)
    entry_period: int = 10      # Breakout of N-bar high/low
    exit_period: int = 5        # Exit on N-bar channel break
    
    # Breakout filter - require price to punch THROUGH channel
    breakout_atr_mult: float = 0.50  # Must exceed channel by 0.5x ATR (filters weak breakouts)
    
    # Risk management
    stop_atr_mult: float = 3.0  # Initial stop distance
    atr_period: int = 14
    
    # Runner mode (trailing stop)
    use_runner: bool = True
    trail_activation_pct: float = 75  # Activate trail after X% of risk
    trail_atr_mult: float = 0.5       # Trail distance (tight!)
    
    # Position sizing
    risk_per_trade_pct: float = 1.0   # Risk 1% per trade


# Validated config from backtest (v2 with breakout filter)
VALIDATED_CONFIG = DonchianConfig(
    entry_period=10,
    exit_period=5,
    breakout_atr_mult=0.50,  # Require strong breakout (filters weak signals)
    stop_atr_mult=3.0,
    atr_period=14,
    use_runner=True,
    trail_activation_pct=75,
    trail_atr_mult=0.5,
    risk_per_trade_pct=1.0
)


@dataclass
class Position:
    direction: Direction
    entry_price: float
    stop_price: float
    initial_risk: float
    trail_stop: Optional[float] = None
    entry_time: Optional[str] = None
    
    def update_trail(self, current_high: float, current_low: float, 
                     atr: float, config: DonchianConfig) -> bool:
        """Update trailing stop. Returns True if trail was updated."""
        if not config.use_runner:
            return False
        
        if self.direction == Direction.LONG:
            profit = current_high - self.entry_price
            activation = self.initial_risk * config.trail_activation_pct / 100
            
            if profit >= activation:
                new_trail = current_high - config.trail_atr_mult * atr
                if self.trail_stop is None or new_trail > self.trail_stop:
                    self.trail_stop = new_trail
                    return True
        else:
            profit = self.entry_price - current_low
            activation = self.initial_risk * config.trail_activation_pct / 100
            
            if profit >= activation:
                new_trail = current_low + config.trail_atr_mult * atr
                if self.trail_stop is None or new_trail < self.trail_stop:
                    self.trail_stop = new_trail
                    return True
        
        return False
    
    @property
    def effective_stop(self) -> float:
        """Get current effective stop (trail or initial)"""
        if self.trail_stop is not None:
            if self.direction == Direction.LONG:
                return max(self.trail_stop, self.stop_price)
            else:
                return min(self.trail_stop, self.stop_price)
        return self.stop_price


class DonchianStrategy:
    """
    Donchian Channel Breakout with Runner Mode
    
    Entry: Break of N-period high (long) or low (short)
    Exit: Break of M-period channel OR trailing stop
    """
    
    def __init__(self, config: DonchianConfig = None):
        self.config = config or VALIDATED_CONFIG
        self.bars: List[Dict] = []
        self.position: Optional[Position] = None
        
        # Stats
        self.signals_generated = 0
        self.trades_closed = 0
    
    def add_bar(self, bar: Dict) -> Optional[Dict]:
        """
        Add a new bar and check for signals.
        
        bar format: {'timestamp', 'open', 'high', 'low', 'close', 'volume'}
        
        Returns signal dict if action needed:
        {'action': 'entry'|'exit', 'direction': 'long'|'short', 
         'price': float, 'stop': float, 'reason': str}
        """
        self.bars.append(bar)
        
        # Need enough history
        min_bars = max(self.config.entry_period, self.config.exit_period, 
                       self.config.atr_period) + 5
        if len(self.bars) < min_bars:
            return None
        
        # Trim old bars (keep 200)
        if len(self.bars) > 200:
            self.bars = self.bars[-200:]
        
        # Calculate indicators
        atr = self._calc_atr()
        if atr is None or atr == 0:
            return None
        
        # Donchian channels
        entry_high = max(b['high'] for b in self.bars[-self.config.entry_period-1:-1])
        entry_low = min(b['low'] for b in self.bars[-self.config.entry_period-1:-1])
        exit_high = max(b['high'] for b in self.bars[-self.config.exit_period-1:-1])
        exit_low = min(b['low'] for b in self.bars[-self.config.exit_period-1:-1])
        
        price = bar['close']
        
        # Check exit first if in position
        if self.position:
            # Update trailing stop
            self.position.update_trail(bar['high'], bar['low'], atr, self.config)
            
            exit_signal = self._check_exit(bar, exit_high, exit_low)
            if exit_signal:
                self.position = None
                self.trades_closed += 1
                return exit_signal
        
        # Check entry if flat
        if not self.position:
            entry_signal = self._check_entry(bar, entry_high, entry_low, atr)
            if entry_signal:
                self.signals_generated += 1
                return entry_signal
        
        return None
    
    def _calc_atr(self) -> Optional[float]:
        """Calculate ATR from recent bars"""
        period = self.config.atr_period
        if len(self.bars) < period + 1:
            return None
        
        recent = self.bars[-(period + 1):]
        trs = []
        
        for i in range(1, len(recent)):
            h = recent[i]['high']
            l = recent[i]['low']
            pc = recent[i-1]['close']
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        
        return np.mean(trs)
    
    def _check_entry(self, bar: Dict, entry_high: float, entry_low: float, 
                     atr: float) -> Optional[Dict]:
        """Check for breakout entry with strength filter"""
        price = bar['close']
        
        # Breakout strength filter - require price to PUNCH through, not just touch
        min_breakout = self.config.breakout_atr_mult * atr
        
        # Long breakout - require CLOSE above level + min breakout distance
        if bar['close'] > entry_high + min_breakout:
            risk = self.config.stop_atr_mult * atr
            stop = price - risk
            
            self.position = Position(
                direction=Direction.LONG,
                entry_price=price,
                stop_price=stop,
                initial_risk=risk,
                trail_stop=stop if self.config.use_runner else None,
                entry_time=str(bar.get('timestamp', ''))
            )
            
            return {
                'action': 'entry',
                'direction': 'long',
                'price': price,
                'stop': stop,
                'reason': f'breakout above {entry_high:.4f}',
                'atr': atr
            }
        
        # Short breakout - require CLOSE below level - min breakout distance
        if bar['close'] < entry_low - min_breakout:
            risk = self.config.stop_atr_mult * atr
            stop = price + risk
            
            self.position = Position(
                direction=Direction.SHORT,
                entry_price=price,
                stop_price=stop,
                initial_risk=risk,
                trail_stop=stop if self.config.use_runner else None,
                entry_time=str(bar.get('timestamp', ''))
            )
            
            return {
                'action': 'entry',
                'direction': 'short',
                'price': price,
                'stop': stop,
                'reason': f'breakout below {entry_low:.4f}',
                'atr': atr
            }
        
        return None
    
    def _check_exit(self, bar: Dict, exit_high: float, exit_low: float) -> Optional[Dict]:
        """Check for exit conditions"""
        if not self.position:
            return None
        
        price = bar['close']
        stop = self.position.effective_stop
        
        if self.position.direction == Direction.LONG:
            # Stop hit
            if bar['low'] <= stop:
                pnl_pct = (stop - self.position.entry_price) / self.position.entry_price * 100
                reason = 'trail_stop' if self.position.trail_stop and stop == self.position.trail_stop else 'stop'
                return {
                    'action': 'exit',
                    'direction': 'long',
                    'price': stop,
                    'pnl_pct': pnl_pct,
                    'reason': reason
                }
            
            # Exit channel break
            if bar['low'] <= exit_low:
                pnl_pct = (exit_low - self.position.entry_price) / self.position.entry_price * 100
                return {
                    'action': 'exit',
                    'direction': 'long',
                    'price': exit_low,
                    'pnl_pct': pnl_pct,
                    'reason': 'exit_channel'
                }
        
        else:  # SHORT
            # Stop hit
            if bar['high'] >= stop:
                pnl_pct = (self.position.entry_price - stop) / self.position.entry_price * 100
                reason = 'trail_stop' if self.position.trail_stop and stop == self.position.trail_stop else 'stop'
                return {
                    'action': 'exit',
                    'direction': 'short',
                    'price': stop,
                    'pnl_pct': pnl_pct,
                    'reason': reason
                }
            
            # Exit channel break
            if bar['high'] >= exit_high:
                pnl_pct = (self.position.entry_price - exit_high) / self.position.entry_price * 100
                return {
                    'action': 'exit',
                    'direction': 'short',
                    'price': exit_high,
                    'pnl_pct': pnl_pct,
                    'reason': 'exit_channel'
                }
        
        return None
    
    def get_status(self) -> Dict:
        """Get current strategy status"""
        return {
            'in_position': self.position is not None,
            'direction': self.position.direction.name if self.position else None,
            'entry_price': self.position.entry_price if self.position else None,
            'current_stop': self.position.effective_stop if self.position else None,
            'trail_active': self.position.trail_stop is not None if self.position else False,
            'signals_generated': self.signals_generated,
            'trades_closed': self.trades_closed,
            'bars_loaded': len(self.bars)
        }
