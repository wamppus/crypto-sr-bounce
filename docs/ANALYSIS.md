# DOT S/R Bounce Analysis

## Why DOT?

DOT outperforms BTC and ETH for S/R bounce trading because:
1. **More volatile** = more S/R touches
2. **Cleaner bounces** at support/resistance
3. **Lower price** = more units per dollar (synthetic leverage)

## 90-Day Performance Comparison

| Asset | Price Move | Strategy P&L | Win Rate | Profit Factor |
|-------|------------|--------------|----------|---------------|
| **DOT** | -44% | **+68.5%** | 62.8% | **1.94** |
| BTC | -25% | +21.7% | 59.6% | 1.53 |
| ETH | -32% | +26.7% | 53.6% | 1.40 |

DOT generates **3x better returns** than BTC with this strategy.

## DOT Performance by Period

| Period | DOT Price | Strategy P&L | PF |
|--------|-----------|--------------|-----|
| Last 30d | -14% | +4.2% | 1.16 |
| Last 60d | -28% | +28.8% | 1.61 |
| Last 90d | -44% | +68.5% | 1.94 |
| Last 180d | -56% | +44.2% | 1.24 |
| Full year | -79% | -27.6% | 0.94 |

**Key insight:** Strategy works well even when DOT drops, capturing bounces.
The early 2024 period hurt because DOT was in freefall with few bounces.

## Optimized DOT Config

```python
sr_lookback = 12        # 12h S/R (DOT moves fast)
trend_lookback = 72     # 3 day trend
atr_period = 24
stop_atr_mult = 2.0     # 2x ATR stop
target_atr_mult = 4.0   # 4x ATR target (2:4 R:R)
rsi_exit_high = 60      # Tighter RSI exits
rsi_exit_low = 40
max_hold_bars = 48
min_gap_bars = 6
use_trailing_stop = False
```

## Timeframe

**Recommended:** 1-hour bars

Lower timeframes (5m, 15m) didn't improve results - more noise, similar P&L.
The 1h timeframe captures clean S/R levels while filtering noise.

## Risk Management

- Position size: Risk 1% of account per trade
- Stop: 2x ATR (~2.4% on DOT)
- Target: 4x ATR (~4.7% on DOT)
- Max hold: 48 hours
- Min gap between trades: 6 hours
