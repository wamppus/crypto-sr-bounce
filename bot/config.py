"""
Crypto S/R Bounce - Configuration

Adapted from ES V3 with crypto-specific parameters.
"""

from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class StrategyConfig:
    """Core strategy parameters"""
    
    # S/R Detection
    sr_lookback: int = 24  # Bars to look back for S/R levels
    sr_tolerance_pct: float = 0.1  # How close to S/R to trigger (% of price)
    
    # Trend Filter
    trend_lookback: int = 72  # Bars for trend detection
    use_trend_filter: bool = True
    
    # Contrarian (when no trend)
    ct_bars: int = 2  # Look back for contrarian direction
    use_ct_filter: bool = True
    
    # ATR-Based Stops (key difference from ES)
    atr_period: int = 14
    stop_atr_mult: float = 2.0  # Stop at 2x ATR
    target_atr_mult: float = 4.0  # Target at 4x ATR (2:4 R:R)
    
    # Runner Mode (optional - works for some coins)
    use_trailing_stop: bool = False
    trail_activation_atr: float = 1.5  # Activate trail at 1.5x ATR profit
    trail_distance_atr: float = 0.5  # Trail 0.5x ATR behind
    
    # Time Exit
    max_hold_bars: int = 48  # Max bars to hold
    min_gap_bars: int = 6  # Min bars between trades
    
    # RSI Exit
    rsi_period: int = 14
    rsi_exit_high: float = 70.0  # Exit longs above this
    rsi_exit_low: float = 30.0  # Exit shorts below this
    
    # Session Filters (optional)
    use_session_filter: bool = False
    allowed_sessions: List[str] = field(default_factory=lambda: ['europe', 'us', 'overlap'])
    
    # Round Number S/R (crypto-specific)
    use_round_number_sr: bool = False
    round_number_weight: float = 0.5
    
    # Risk (for position sizing)
    risk_per_trade_pct: float = 1.0  # Risk 1% per trade


@dataclass
class RiskConfig:
    """Risk management parameters"""
    
    # Position sizing
    risk_per_trade_pct: float = 1.0  # Risk 1% of account per trade
    max_positions: int = 1  # Only one position at a time
    
    # Daily limits
    max_daily_loss_pct: float = 3.0  # Stop trading after 3% daily loss
    max_daily_trades: int = 10


# === OPTIMIZED CONFIGS ===

# Best for BTC (from 2-year backtest)
BTC_CONFIG = StrategyConfig(
    sr_lookback=24,
    trend_lookback=72,
    atr_period=24,
    stop_atr_mult=2.0,
    target_atr_mult=4.0,
    max_hold_bars=48,
    min_gap_bars=6,
    rsi_exit_high=70,
    rsi_exit_low=30,
    use_trailing_stop=False,
    use_round_number_sr=False,
)

# Best for DOT (from optimization)
DOT_CONFIG = StrategyConfig(
    sr_lookback=12,       # Shorter - DOT moves faster
    trend_lookback=72,
    atr_period=24,
    stop_atr_mult=2.0,
    target_atr_mult=4.0,
    max_hold_bars=48,
    min_gap_bars=6,
    rsi_exit_high=60,     # Tighter RSI exits
    rsi_exit_low=40,      # Tighter RSI exits
    use_trailing_stop=False,
    use_round_number_sr=False,
)

# DOT with trailing (alternative - higher WR, slightly less P&L)
DOT_TRAIL_CONFIG = StrategyConfig(
    sr_lookback=12,
    trend_lookback=72,
    atr_period=24,
    stop_atr_mult=2.0,
    target_atr_mult=4.0,
    max_hold_bars=48,
    min_gap_bars=6,
    rsi_exit_high=60,
    rsi_exit_low=40,
    use_trailing_stop=True,
    trail_activation_atr=1.5,
    trail_distance_atr=0.5,
)

# Default
DEFAULT_CONFIG = DOT_CONFIG
VALIDATED_CONFIG = DOT_CONFIG
