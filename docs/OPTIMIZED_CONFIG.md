# DOT Optimized Configuration

## Final Settings

```python
sr_lookback = 16        # 16h S/R lookback
trend_lookback = 72     # 3 day trend
atr_period = 24         # 24h ATR

stop_atr_mult = 2.5     # Stop at 2.5x ATR
target_atr_mult = 3.0   # Target at 3x ATR (2.5:3 R:R)

max_hold_bars = 24      # Exit after 24h max
min_gap_bars = 6        # 6h between trades

rsi_exit_high = 60      # Exit long when RSI > 60
rsi_exit_low = 40       # Exit short when RSI < 40

skip_friday = True      # No trades on Friday (UTC)
```

## Backtest Results (90 days)

| Metric | Value |
|--------|-------|
| Trades | 69 |
| Win Rate | 69.6% |
| P&L | +108.8% |
| Profit Factor | 3.75 |
| Monthly | ~36% |

## Key Optimizations

### 1. Shorter S/R Lookback (16h vs 24h)
DOT moves faster than BTC. 16h captures more relevant levels.

### 2. Tighter R:R (2.5:3 vs 2:4)
More frequent wins. The wider stop (2.5x ATR) survives noise, tighter target (3x ATR) captures moves before reversal.

### 3. Shorter Hold Time (24h vs 48h)
DOT mean-reverts quickly. Holding longer adds risk without reward.

### 4. Tighter RSI Exits (60/40 vs 70/30)
Take profits earlier. DOT rarely pushes to extreme RSI.

### 5. Skip Friday
Friday showed negative expectancy (-7.9% P&L vs +98% other days). Possibly due to weekend positioning/hedging.

## Day of Week Performance

| Day | Win Rate | P&L |
|-----|----------|-----|
| Sunday | 90% | +20.7% |
| Wednesday | 85% | +18.8% |
| Thursday | 62% | +23.1% |
| Monday | 67% | +20.5% |
| Saturday | 60% | +8.0% |
| Tuesday | 58% | +7.6% |
| **Friday** | **43%** | **-7.9%** ❌ |

## Usage

```bash
# Check status
python run_dot.py status

# Start shadow trading
python run_dot.py shadow

# The config auto-skips Friday
```

## Risk Management

With $100 account:
- Position: ~60 DOT
- Stop: ~$0.10 per DOT (2.5x ATR)
- Risk per trade: ~$6 (6% of account)
- Target: ~$0.12 per DOT (3x ATR)
- Expected win: ~$7.20

With 70% win rate:
- 10 trades: 7 wins ($50.40) + 3 losses ($18) = +$32.40 net
