#!/usr/bin/env python3
"""
Hyperliquid Exchange Client

Wraps the hyperliquid skill scripts for use with the crypto S/R bounce bot.
Supports both testnet and mainnet.
"""

import subprocess
import json
import os
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

# Path to hyperliquid scripts
HYPERLIQUID_SCRIPTS = os.path.expanduser(
    "~/clawd/skills/hyperliquid-trading/scripts"
)


@dataclass
class Position:
    """Current position info"""
    coin: str
    size: float  # Positive = long, negative = short
    entry_price: float
    unrealized_pnl: float
    liquidation_price: Optional[float] = None


@dataclass
class OrderResult:
    """Result of an order execution"""
    success: bool
    order_id: Optional[str] = None
    filled_price: Optional[float] = None
    filled_size: Optional[float] = None
    error: Optional[str] = None


class HyperliquidClient:
    """
    Client for Hyperliquid perpetual futures.
    
    Read-only operations need HYPERLIQUID_ADDRESS.
    Trading operations need HYPERLIQUID_PRIVATE_KEY.
    """
    
    def __init__(
        self,
        address: Optional[str] = None,
        private_key: Optional[str] = None,
        testnet: bool = True,
    ):
        self.address = address or os.environ.get('HYPERLIQUID_ADDRESS')
        self.private_key = private_key or os.environ.get('HYPERLIQUID_PRIVATE_KEY')
        self.testnet = testnet
        
        if not self.address and not self.private_key:
            raise ValueError("Need HYPERLIQUID_ADDRESS or HYPERLIQUID_PRIVATE_KEY")
    
    def _run_command(self, *args) -> Tuple[bool, str]:
        """Run a hyperliquid.mjs command"""
        env = os.environ.copy()
        
        if self.private_key:
            env['HYPERLIQUID_PRIVATE_KEY'] = self.private_key
        elif self.address:
            env['HYPERLIQUID_ADDRESS'] = self.address
        
        if self.testnet:
            env['HYPERLIQUID_TESTNET'] = '1'
        
        cmd = ['node', 'hyperliquid.mjs'] + list(args)
        
        try:
            result = subprocess.run(
                cmd,
                cwd=HYPERLIQUID_SCRIPTS,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            
            if result.returncode != 0:
                return False, result.stderr or result.stdout
            
            return True, result.stdout.strip()
            
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)
    
    # === Read Operations ===
    
    def get_price(self, coin: str) -> Optional[float]:
        """Get current price for a coin"""
        success, output = self._run_command('price', coin.upper())
        if success:
            try:
                return float(output)
            except ValueError:
                return None
        return None
    
    def get_balance(self) -> Optional[Dict[str, float]]:
        """Get account balance"""
        success, output = self._run_command('balance')
        if success:
            try:
                data = json.loads(output)
                return {
                    'equity': float(data.get('accountValue', 0)),
                    'available': float(data.get('withdrawable', 0)),
                    'margin_used': float(data.get('marginUsed', 0)),
                }
            except (json.JSONDecodeError, ValueError):
                return None
        return None
    
    def get_positions(self) -> list[Position]:
        """Get all open positions"""
        success, output = self._run_command('positions')
        if not success:
            return []
        
        try:
            data = json.loads(output)
            positions = []
            for p in data:
                if float(p.get('szi', 0)) != 0:
                    positions.append(Position(
                        coin=p.get('coin', ''),
                        size=float(p.get('szi', 0)),
                        entry_price=float(p.get('entryPx', 0)),
                        unrealized_pnl=float(p.get('unrealizedPnl', 0)),
                        liquidation_price=float(p.get('liquidationPx', 0)) if p.get('liquidationPx') else None,
                    ))
            return positions
        except (json.JSONDecodeError, ValueError):
            return []
    
    def get_position(self, coin: str) -> Optional[Position]:
        """Get position for specific coin"""
        positions = self.get_positions()
        for p in positions:
            if p.coin.upper() == coin.upper():
                return p
        return None
    
    # === Trading Operations ===
    
    def market_buy(self, coin: str, size: float) -> OrderResult:
        """Market buy (long)"""
        if not self.private_key:
            return OrderResult(success=False, error="Private key required for trading")
        
        success, output = self._run_command('market-buy', coin.upper(), str(size))
        
        if success:
            try:
                data = json.loads(output)
                return OrderResult(
                    success=True,
                    order_id=str(data.get('oid', '')),
                    filled_price=float(data.get('avgPx', 0)) if data.get('avgPx') else None,
                    filled_size=size,
                )
            except (json.JSONDecodeError, ValueError):
                return OrderResult(success=True, filled_size=size)
        
        return OrderResult(success=False, error=output)
    
    def market_sell(self, coin: str, size: float) -> OrderResult:
        """Market sell (short or close long)"""
        if not self.private_key:
            return OrderResult(success=False, error="Private key required for trading")
        
        success, output = self._run_command('market-sell', coin.upper(), str(size))
        
        if success:
            try:
                data = json.loads(output)
                return OrderResult(
                    success=True,
                    order_id=str(data.get('oid', '')),
                    filled_price=float(data.get('avgPx', 0)) if data.get('avgPx') else None,
                    filled_size=size,
                )
            except (json.JSONDecodeError, ValueError):
                return OrderResult(success=True, filled_size=size)
        
        return OrderResult(success=False, error=output)
    
    def limit_buy(self, coin: str, size: float, price: float) -> OrderResult:
        """Place limit buy order"""
        if not self.private_key:
            return OrderResult(success=False, error="Private key required for trading")
        
        success, output = self._run_command('buy', coin.upper(), str(size), str(price))
        
        if success:
            try:
                data = json.loads(output)
                return OrderResult(
                    success=True,
                    order_id=str(data.get('oid', '')),
                )
            except (json.JSONDecodeError, ValueError):
                return OrderResult(success=True)
        
        return OrderResult(success=False, error=output)
    
    def limit_sell(self, coin: str, size: float, price: float) -> OrderResult:
        """Place limit sell order"""
        if not self.private_key:
            return OrderResult(success=False, error="Private key required for trading")
        
        success, output = self._run_command('sell', coin.upper(), str(size), str(price))
        
        if success:
            try:
                data = json.loads(output)
                return OrderResult(
                    success=True,
                    order_id=str(data.get('oid', '')),
                )
            except (json.JSONDecodeError, ValueError):
                return OrderResult(success=True)
        
        return OrderResult(success=False, error=output)
    
    def cancel_order(self, coin: str, order_id: str) -> bool:
        """Cancel specific order"""
        if not self.private_key:
            return False
        
        success, _ = self._run_command('cancel', coin.upper(), order_id)
        return success
    
    def cancel_all(self, coin: Optional[str] = None) -> bool:
        """Cancel all orders (optionally for specific coin)"""
        if not self.private_key:
            return False
        
        if coin:
            success, _ = self._run_command('cancel-all', coin.upper())
        else:
            success, _ = self._run_command('cancel-all')
        return success
    
    def close_position(self, coin: str) -> OrderResult:
        """Close entire position for a coin"""
        position = self.get_position(coin)
        if not position:
            return OrderResult(success=True)  # No position to close
        
        if position.size > 0:
            return self.market_sell(coin, abs(position.size))
        else:
            return self.market_buy(coin, abs(position.size))


# === Shadow Trading Mode ===

class ShadowClient:
    """
    Fake client for shadow trading (paper trading).
    Logs trades without executing them.
    """
    
    def __init__(self, real_client: HyperliquidClient, log_path: str = 'shadow_trades.jsonl'):
        self.real = real_client  # For reading prices
        self.log_path = log_path
        self.paper_positions: Dict[str, Position] = {}
        self.paper_balance = 10000.0  # Start with $10K
    
    def _log_trade(self, action: str, coin: str, size: float, price: float, **extra):
        """Log a paper trade"""
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'action': action,
            'coin': coin,
            'size': size,
            'price': price,
            'paper_balance': self.paper_balance,
            **extra,
        }
        
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')
        
        print(f"[SHADOW] {action} {size} {coin} @ ${price:,.2f}")
    
    def get_price(self, coin: str) -> Optional[float]:
        return self.real.get_price(coin)
    
    def get_balance(self) -> Dict[str, float]:
        return {'equity': self.paper_balance, 'available': self.paper_balance, 'margin_used': 0}
    
    def get_positions(self) -> list[Position]:
        return list(self.paper_positions.values())
    
    def get_position(self, coin: str) -> Optional[Position]:
        return self.paper_positions.get(coin.upper())
    
    def market_buy(self, coin: str, size: float) -> OrderResult:
        price = self.get_price(coin)
        if not price:
            return OrderResult(success=False, error="Couldn't get price")
        
        coin = coin.upper()
        
        # Update paper position
        if coin in self.paper_positions:
            pos = self.paper_positions[coin]
            # Average in
            total_size = pos.size + size
            if total_size != 0:
                avg_price = (pos.size * pos.entry_price + size * price) / total_size
                pos.size = total_size
                pos.entry_price = avg_price
        else:
            self.paper_positions[coin] = Position(
                coin=coin,
                size=size,
                entry_price=price,
                unrealized_pnl=0,
            )
        
        self._log_trade('BUY', coin, size, price)
        return OrderResult(success=True, filled_price=price, filled_size=size)
    
    def market_sell(self, coin: str, size: float) -> OrderResult:
        price = self.get_price(coin)
        if not price:
            return OrderResult(success=False, error="Couldn't get price")
        
        coin = coin.upper()
        
        # Update paper position
        if coin in self.paper_positions:
            pos = self.paper_positions[coin]
            pnl = (price - pos.entry_price) * min(size, pos.size)
            self.paper_balance += pnl
            pos.size -= size
            
            if abs(pos.size) < 0.0001:
                del self.paper_positions[coin]
        else:
            # Opening short
            self.paper_positions[coin] = Position(
                coin=coin,
                size=-size,
                entry_price=price,
                unrealized_pnl=0,
            )
        
        self._log_trade('SELL', coin, size, price)
        return OrderResult(success=True, filled_price=price, filled_size=size)
    
    def close_position(self, coin: str) -> OrderResult:
        pos = self.get_position(coin)
        if not pos:
            return OrderResult(success=True)
        
        if pos.size > 0:
            return self.market_sell(coin, abs(pos.size))
        else:
            return self.market_buy(coin, abs(pos.size))


if __name__ == '__main__':
    # Quick test
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        print("Testing Hyperliquid connection...")
        
        # Read-only test (no keys needed for price)
        client = HyperliquidClient(address='0x0000000000000000000000000000000000000000', testnet=True)
        
        btc_price = client.get_price('BTC')
        eth_price = client.get_price('ETH')
        
        print(f"BTC: ${btc_price:,.2f}" if btc_price else "BTC: Error")
        print(f"ETH: ${eth_price:,.2f}" if eth_price else "ETH: Error")
