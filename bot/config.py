"""
Crypto S/R Bounce - Configuration

Optimized for DOT trading on Kraken.
"""

from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class StrategyConfig:
    """Core strategy parameters"""
    
    # S/R Detection
    sr_lookback: int = 16  # 16h lookback (optimized for DOT)
    sr_tolerance_pct: float = 0.1
    
    # Trend Filter
    trend_lookback: int = 72  # 3 day trend
    use_trend_filter: bool = True
    
    # Contrarian (when no trend)
    ct_bars: int = 2
    use_ct_filter: bool = True
    
    # ATR-Based Stops
    atr_period: int = 24
    stop_atr_mult: float = 2.5   # 2.5x ATR stop (optimized)
    target_atr_mult: float = 3.0  # 3x ATR target (optimized)
    
    # Trailing (disabled for DOT)
    use_trailing_stop: bool = False
    trail_activation_atr: float = 1.5
    trail_distance_atr: float = 0.5
    
    # Time Exit
    max_hold_bars: int = 24  # 24h max hold (optimized)
    min_gap_bars: int = 6
    
    # RSI Exit
    rsi_period: int = 14
    rsi_exit_high: float = 60.0  # Tighter (optimized)
    rsi_exit_low: float = 40.0   # Tighter (optimized)
    
    # Day Filter
    skip_days: List[int] = field(default_factory=lambda: [4])  # Skip Friday (day 4)
    
    # Session Filters (optional)
    use_session_filter: bool = False
    allowed_sessions: List[str] = field(default_factory=lambda: ['europe', 'us', 'overlap'])
    
    # Round Number S/R
    use_round_number_sr: bool = False
    round_number_weight: float = 0.5
    
    # Risk
    risk_per_trade_pct: float = 1.0


# === OPTIMIZED CONFIGS ===

# BEST CONFIG FOR DOT (from deep optimization)
# 90-day backtest: +109% P&L, 70% WR, 3.75 PF
DOT_OPTIMIZED = StrategyConfig(
    sr_lookback=16,         # 16h S/R
    trend_lookback=72,
    atr_period=24,
    stop_atr_mult=2.5,      # Wider stop
    target_atr_mult=3.0,    # Tighter target (2.5:3 R:R)
    max_hold_bars=24,       # 24h max hold
    min_gap_bars=6,
    rsi_exit_high=60,       # Tighter
    rsi_exit_low=40,        # Tighter
    skip_days=[4],          # Skip Friday!
    use_trailing_stop=False,
)

# Previous DOT config (still good)
DOT_CONFIG = StrategyConfig(
    sr_lookback=12,
    trend_lookback=72,
    atr_period=24,
    stop_atr_mult=2.0,
    target_atr_mult=4.0,
    max_hold_bars=48,
    min_gap_bars=6,
    rsi_exit_high=60,
    rsi_exit_low=40,
    use_trailing_stop=False,
)

# BTC config (different characteristics)
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
)

# Default = best DOT config
DEFAULT_CONFIG = DOT_OPTIMIZED
VALIDATED_CONFIG = DOT_OPTIMIZED
