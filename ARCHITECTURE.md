# Crypto S/R Bounce - Architecture

## Strategy Origin

Ported from ES S/R Bounce V3 (futures) with crypto-specific adaptations.

**Core Edge:** Runner mode with trailing stop at S/R bounces.

## Key Differences from ES

| Aspect | ES (V3) | Crypto |
|--------|---------|--------|
| Market Hours | RTH 9:30-16:00 ET | 24/7 |
| Stop/Target | Fixed points (3-4 pts) | Percentage-based (ATR-scaled) |
| Data Source | ProjectX/CME | Exchange APIs (Binance, Hyperliquid) |
| Session Edges | Opening range, lunch lull | Asia/Europe/US session overlaps |
| S/R Levels | Bar-based lookback | Round numbers + bar-based |
| Volatility | ~1% daily | 3-10% daily swings |

## File Structure

```
crypto-sr-bounce/
├── ARCHITECTURE.md          ← You are here
├── README.md
├── backtest.py              ← Core backtester (adapted from V3)
├── data/                    ← Historical OHLCV data
│   └── .gitkeep
├── bot/
│   ├── config.py            ← Strategy parameters
│   ├── strategy.py          ← Core strategy logic
│   ├── exchange_client.py   ← Exchange abstraction
│   └── data.py              ← Data fetching/processing
└── docs/
    └── CRYPTO_ADAPTATIONS.md
```

## Strategy Logic (V3 Port)

1. **S/R Detection:** Last N bars high/low (same as V3)
2. **Trend Filter:** 30-bar trend detection (same logic)
3. **Entry:** Touch S/R + trend alignment + optional candle confirmation
4. **Exit Priority:**
   - Trailing stop (runner mode) - THE EDGE
   - Fixed stop loss
   - RSI extreme exit
   - Time-based exit (bars held)

## Crypto-Specific Adaptations

### ATR-Scaled Stops
Instead of fixed 3pt stop, use ATR multiplier:
```python
stop_atr_mult = 1.5  # Stop at 1.5x ATR
target_atr_mult = 2.0  # Target at 2x ATR
trail_activation_atr = 1.0  # Trail activates at 1x ATR profit
```

### Session Filters (Optional)
- **Asia (00:00-08:00 UTC):** Often range-bound
- **Europe (08:00-16:00 UTC):** Trend initiation
- **US (14:00-22:00 UTC):** Volatility spike
- **Overlap (14:00-16:00 UTC):** Highest volume

### Round Number S/R
Crypto respects psychological levels:
- BTC: $60K, $65K, $70K, $100K
- ETH: $3000, $3500, $4000

Combine bar-based S/R with round number proximity.

## Data Sources

### Backtesting
- Binance historical klines (free, good quality)
- `ccxt` library for unified API

### Live Trading
- **Hyperliquid:** Perpetuals, no KYC, good for algos
- **Binance Futures:** Higher liquidity, requires KYC
- **Bybit:** Middle ground

## Quick Start

```bash
# Get historical data
python -m bot.data --symbol BTCUSDT --timeframe 5m --days 365

# Run backtest
python backtest.py

# (Future) Live trading
python -m bot.strategy --mode shadow
```

## Risk Management

Crypto is MORE volatile than ES. Adjust accordingly:
- Smaller position sizes (0.5-1% risk per trade vs 2% on ES)
- Wider stops (ATR-based, not fixed)
- Account for funding rates on perpetuals
- Watch for exchange-specific risks (liquidation cascades)

## Next Steps

1. ✅ Port backtest.py from V3
2. [ ] Get BTC/ETH historical data
3. [ ] Adapt for percentage-based stops
4. [ ] Backtest and validate
5. [ ] Build exchange client for live trading
