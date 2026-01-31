# Crypto S/R Bounce

**Strategy:** Support/Resistance bounce with runner mode trailing stop.

Ported from ES S/R Bounce V3 (validated 60% WR on ES futures) with crypto-specific adaptations.

## The Edge

Same core principle as ES V3: **Let winners run with a trailing stop.**

- Enter at S/R levels with trend confirmation
- Trail stop activates after 1x ATR profit
- Lock in gains, cut losses short
- 24/7 crypto markets = more opportunities

## Quick Start

```bash
# Install dependencies
pip install pandas numpy ccxt

# Fetch historical data (1 year of BTC 5m candles)
python -m bot.data --symbol BTC/USDT --timeframe 5m --days 365

# Run backtest
python backtest.py
```

## Key Differences from ES Version

| Aspect | ES (V3) | Crypto |
|--------|---------|--------|
| Stop/Target | Fixed points (3-4 pts) | ATR-based (1.5x/2x ATR) |
| Market Hours | RTH only (9:30-16:00) | 24/7 |
| S/R Levels | Bar-based | Bar-based + round numbers |
| Volatility | ~1% daily | 3-10% daily |
| Position Size | 2% risk | 0.5% risk (more volatile) |

## Configuration

See `bot/config.py` for all parameters. Key settings:

```python
# ATR-based stops (adapts to volatility)
stop_atr_mult = 1.5      # Stop at 1.5x ATR from entry
target_atr_mult = 2.0    # Target at 2x ATR

# Runner mode (THE EDGE)
trail_activation_atr = 1.0  # Start trailing at 1x ATR profit
trail_distance_atr = 0.3    # Trail 0.3x ATR behind price
```

## Project Structure

```
crypto-sr-bounce/
├── backtest.py          # Main backtester
├── bot/
│   ├── config.py        # Strategy parameters
│   ├── data.py          # Data fetching (ccxt)
│   └── strategy.py      # (TODO) Live trading logic
├── data/                # Historical OHLCV data
└── docs/                # Documentation
```

## Roadmap

- [x] Port backtest from ES V3
- [x] ATR-based stop/target adaptation
- [x] Round number S/R blending
- [ ] Fetch and backtest BTC/ETH data
- [ ] Hyperliquid exchange client
- [ ] Shadow trading mode
- [ ] Live trading

## Risk Warning

Crypto is volatile. This strategy is experimental. Never risk more than you can afford to lose.

## Origin

Derived from `es-sr-bounce-v3` which achieved 60% WR on ES futures with:
- 21,142 trades over 4 years
- +$141K profit ($35K/year)
- Max DD $5,838
- All years profitable

Whether this translates to crypto remains to be validated.
