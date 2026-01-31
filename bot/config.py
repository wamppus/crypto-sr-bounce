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
    sr_lookback: int = 10  # Bars to look back for S/R levels
    sr_tolerance_pct: float = 0.1  # How close to S/R to trigger (% of price)
    
    # Trend Filter
    trend_lookback: int = 30  # Bars for trend detection
    use_trend_filter: bool = True
    
    # Contrarian (when no trend)
    ct_bars: int = 2  # Look back for contrarian direction
    use_ct_filter: bool = True
    
    # ATR-Based Stops (key difference from ES)
    atr_period: int = 14
    stop_atr_mult: float = 1.5  # Stop at 1.5x ATR
    target_atr_mult: float = 2.0  # Target at 2x ATR
    
    # Runner Mode (THE EDGE)
    use_trailing_stop: bool = True
    trail_activation_atr: float = 1.0  # Activate trail at 1x ATR profit
    trail_distance_atr: float = 0.3  # Trail 0.3x ATR behind
    
    # Time Exit
    max_hold_bars: int = 10  # Longer than ES due to 24/7 market
    min_gap_bars: int = 5  # Min bars between trades
    
    # RSI Exit
    rsi_period: int = 14
    rsi_exit_high: float = 70.0  # Exit longs above this
    rsi_exit_low: float = 30.0  # Exit shorts below this
    
    # Session Filters (optional)
    use_session_filter: bool = False
    allowed_sessions: List[str] = field(default_factory=lambda: ['europe', 'us', 'overlap'])
    
    # Round Number S/R (crypto-specific)
    use_round_number_sr: bool = True
    round_number_weight: float = 0.5  # How much to weight round numbers vs bar-based


@dataclass
class RiskConfig:
    """Risk management parameters"""
    
    # Position sizing
    risk_per_trade_pct: float = 0.5  # Risk 0.5% of account per trade (conservative for crypto)
    max_positions: int = 1  # Only one position at a time
    
    # Daily limits
    max_daily_loss_pct: float = 2.0  # Stop trading after 2% daily loss
    max_daily_trades: int = 10
    
    # Leverage (for perpetuals)
    max_leverage: float = 3.0  # Conservative leverage


@dataclass  
class ExchangeConfig:
    """Exchange connection settings"""
    
    exchange: str = 'hyperliquid'  # hyperliquid, binance, bybit
    symbol: str = 'BTC'
    
    # Hyperliquid specific
    wallet_address: Optional[str] = None
    private_key: Optional[str] = None
    
    # Binance specific
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    
    # Testnet
    testnet: bool = True


# Default configs
DEFAULT_STRATEGY = StrategyConfig()
DEFAULT_RISK = RiskConfig()
DEFAULT_EXCHANGE = ExchangeConfig()


# Validated config from ES V3 (adapted)
VALIDATED_CONFIG = StrategyConfig(
    sr_lookback=10,
    sr_tolerance_pct=0.15,  # ~0.15% = ~$100 on BTC at $65K
    trend_lookback=30,
    stop_atr_mult=1.5,
    target_atr_mult=2.0,
    trail_activation_atr=1.0,
    trail_distance_atr=0.3,
    max_hold_bars=10,
    rsi_exit_high=65,
    rsi_exit_low=35,
    use_trailing_stop=True,
    use_round_number_sr=True,
)
