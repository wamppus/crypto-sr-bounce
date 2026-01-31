#!/usr/bin/env python3
"""
Kraken Exchange Client

US-legal crypto trading with good API.
Supports spot and futures (CFTC-regulated).
"""

import hmac
import hashlib
import base64
import urllib.parse
import time
import requests
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone


# API endpoints
KRAKEN_API_URL = "https://api.kraken.com"
KRAKEN_FUTURES_URL = "https://futures.kraken.com"


@dataclass
class Position:
    """Current position info"""
    symbol: str
    size: float
    entry_price: float
    unrealized_pnl: float
    side: str  # 'long' or 'short'


@dataclass
class OrderResult:
    """Result of an order execution"""
    success: bool
    order_id: Optional[str] = None
    filled_price: Optional[float] = None
    filled_size: Optional[float] = None
    error: Optional[str] = None


class KrakenClient:
    """
    Kraken API Client for spot and futures trading.
    
    For read-only (prices, OHLC): No API key needed
    For trading: Requires API key and secret
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        futures: bool = False,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.futures = futures
        self.base_url = KRAKEN_FUTURES_URL if futures else KRAKEN_API_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'CryptoSRBounce/1.0'
        })
    
    def _sign_request(self, uri_path: str, data: dict) -> dict:
        """Generate signature for private endpoints"""
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret required for private endpoints")
        
        # Add nonce
        data['nonce'] = str(int(time.time() * 1000))
        
        # Create signature
        post_data = urllib.parse.urlencode(data)
        encoded = (data['nonce'] + post_data).encode()
        message = uri_path.encode() + hashlib.sha256(encoded).digest()
        signature = hmac.new(
            base64.b64decode(self.api_secret),
            message,
            hashlib.sha512
        )
        
        return {
            'API-Key': self.api_key,
            'API-Sign': base64.b64encode(signature.digest()).decode()
        }
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        private: bool = False,
    ) -> Tuple[bool, Any]:
        """Make API request"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'GET':
                resp = self.session.get(url, params=params, timeout=30)
            else:
                headers = {}
                if private:
                    headers = self._sign_request(endpoint, params or {})
                resp = self.session.post(url, data=params, headers=headers, timeout=30)
            
            resp.raise_for_status()
            data = resp.json()
            
            # Kraken returns errors in 'error' array
            if data.get('error') and len(data['error']) > 0:
                return False, data['error'][0]
            
            return True, data.get('result', data)
            
        except requests.exceptions.RequestException as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)
    
    # === Public Endpoints (No Auth) ===
    
    def get_server_time(self) -> Optional[datetime]:
        """Get server time"""
        success, data = self._request('GET', '/0/public/Time')
        if success:
            return datetime.fromtimestamp(data['unixtime'], tz=timezone.utc)
        return None
    
    def get_ticker(self, pair: str) -> Optional[Dict]:
        """Get ticker info for a pair"""
        success, data = self._request('GET', '/0/public/Ticker', {'pair': pair})
        if success and data:
            # Returns dict with pair as key
            for key, ticker in data.items():
                return {
                    'ask': float(ticker['a'][0]),
                    'bid': float(ticker['b'][0]),
                    'last': float(ticker['c'][0]),
                    'volume': float(ticker['v'][1]),  # 24h volume
                    'vwap': float(ticker['p'][1]),    # 24h VWAP
                    'high': float(ticker['h'][1]),    # 24h high
                    'low': float(ticker['l'][1]),     # 24h low
                }
        return None
    
    def get_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol (BTC, ETH, etc.)"""
        # Map common symbols to Kraken pairs
        pair_map = {
            'BTC': 'XXBTZUSD',
            'ETH': 'XETHZUSD',
            'SOL': 'SOLUSD',
            'XRP': 'XXRPZUSD',
        }
        pair = pair_map.get(symbol.upper(), f'{symbol.upper()}USD')
        
        ticker = self.get_ticker(pair)
        if ticker:
            return ticker['last']
        return None
    
    def get_ohlc(
        self,
        pair: str,
        interval: int = 60,  # minutes: 1, 5, 15, 30, 60, 240, 1440, 10080, 21600
        since: Optional[int] = None,
    ) -> List[Dict]:
        """
        Get OHLC data.
        
        Note: Returns max 720 candles. For more history, use downloadable data.
        """
        params = {'pair': pair, 'interval': interval}
        if since:
            params['since'] = since
        
        success, data = self._request('GET', '/0/public/OHLC', params)
        if not success:
            return []
        
        bars = []
        for key, ohlc_list in data.items():
            if key == 'last':
                continue
            for candle in ohlc_list:
                bars.append({
                    'timestamp': datetime.fromtimestamp(candle[0], tz=timezone.utc),
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'vwap': float(candle[5]),
                    'volume': float(candle[6]),
                    'count': int(candle[7]),
                })
        
        return sorted(bars, key=lambda x: x['timestamp'])
    
    def get_asset_pairs(self) -> Dict:
        """Get tradeable asset pairs"""
        success, data = self._request('GET', '/0/public/AssetPairs')
        if success:
            return data
        return {}
    
    # === Private Endpoints (Auth Required) ===
    
    def get_balance(self) -> Optional[Dict[str, float]]:
        """Get account balance"""
        success, data = self._request('POST', '/0/private/Balance', {}, private=True)
        if success:
            return {k: float(v) for k, v in data.items()}
        return None
    
    def get_trade_balance(self, asset: str = 'ZUSD') -> Optional[Dict]:
        """Get trade balance (equity, margin, etc.)"""
        success, data = self._request(
            'POST', '/0/private/TradeBalance', 
            {'asset': asset}, 
            private=True
        )
        if success:
            return {
                'equity': float(data.get('eb', 0)),
                'trade_balance': float(data.get('tb', 0)),
                'margin': float(data.get('m', 0)),
                'unrealized_pnl': float(data.get('n', 0)),
                'free_margin': float(data.get('mf', 0)),
            }
        return None
    
    def get_open_orders(self) -> List[Dict]:
        """Get open orders"""
        success, data = self._request('POST', '/0/private/OpenOrders', {}, private=True)
        if success and data.get('open'):
            orders = []
            for oid, order in data['open'].items():
                orders.append({
                    'id': oid,
                    'pair': order['descr']['pair'],
                    'type': order['descr']['type'],  # buy/sell
                    'order_type': order['descr']['ordertype'],  # limit/market
                    'price': float(order['descr']['price']) if order['descr']['price'] else None,
                    'volume': float(order['vol']),
                    'filled': float(order['vol_exec']),
                    'status': order['status'],
                })
            return orders
        return []
    
    def get_open_positions(self) -> List[Position]:
        """Get open positions (margin/futures)"""
        success, data = self._request('POST', '/0/private/OpenPositions', {}, private=True)
        if not success:
            return []
        
        positions = []
        for pid, pos in data.items():
            positions.append(Position(
                symbol=pos['pair'],
                size=float(pos['vol']),
                entry_price=float(pos['cost']) / float(pos['vol']),
                unrealized_pnl=float(pos.get('net', 0)),
                side='long' if pos['type'] == 'buy' else 'short',
            ))
        return positions
    
    # === Order Execution ===
    
    def place_order(
        self,
        pair: str,
        side: str,  # 'buy' or 'sell'
        order_type: str,  # 'market' or 'limit'
        volume: float,
        price: Optional[float] = None,
        leverage: Optional[str] = None,
        validate: bool = False,  # If True, just validates without placing
    ) -> OrderResult:
        """Place an order"""
        params = {
            'pair': pair,
            'type': side,
            'ordertype': order_type,
            'volume': str(volume),
        }
        
        if price and order_type == 'limit':
            params['price'] = str(price)
        
        if leverage:
            params['leverage'] = leverage
        
        if validate:
            params['validate'] = 'true'
        
        success, data = self._request('POST', '/0/private/AddOrder', params, private=True)
        
        if not success:
            return OrderResult(success=False, error=str(data))
        
        return OrderResult(
            success=True,
            order_id=data.get('txid', [None])[0],
        )
    
    def market_buy(self, symbol: str, size: float) -> OrderResult:
        """Market buy"""
        pair = f'{symbol.upper()}USD'
        return self.place_order(pair, 'buy', 'market', size)
    
    def market_sell(self, symbol: str, size: float) -> OrderResult:
        """Market sell"""
        pair = f'{symbol.upper()}USD'
        return self.place_order(pair, 'sell', 'market', size)
    
    def limit_buy(self, symbol: str, size: float, price: float) -> OrderResult:
        """Limit buy"""
        pair = f'{symbol.upper()}USD'
        return self.place_order(pair, 'buy', 'limit', size, price)
    
    def limit_sell(self, symbol: str, size: float, price: float) -> OrderResult:
        """Limit sell"""
        pair = f'{symbol.upper()}USD'
        return self.place_order(pair, 'sell', 'limit', size, price)
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        success, _ = self._request(
            'POST', '/0/private/CancelOrder',
            {'txid': order_id},
            private=True
        )
        return success
    
    def cancel_all(self) -> bool:
        """Cancel all open orders"""
        success, _ = self._request('POST', '/0/private/CancelAll', {}, private=True)
        return success


def fetch_kraken_ohlc(
    symbol: str = 'BTC',
    interval: int = 60,
    limit: int = 720,
) -> List[Dict]:
    """
    Fetch OHLC data from Kraken (public, no auth needed).
    
    Args:
        symbol: BTC, ETH, etc.
        interval: Minutes (1, 5, 15, 30, 60, 240, 1440)
        limit: Max 720 from API
    """
    client = KrakenClient()
    
    pair_map = {
        'BTC': 'XXBTZUSD',
        'ETH': 'XETHZUSD',
        'SOL': 'SOLUSD',
    }
    pair = pair_map.get(symbol.upper(), f'{symbol.upper()}USD')
    
    return client.get_ohlc(pair, interval)


if __name__ == '__main__':
    # Test public endpoints
    print("Testing Kraken API...")
    
    client = KrakenClient()
    
    # Server time
    server_time = client.get_server_time()
    print(f"Server time: {server_time}")
    
    # BTC price
    btc_price = client.get_price('BTC')
    print(f"BTC: ${btc_price:,.2f}" if btc_price else "BTC: Error")
    
    # ETH price
    eth_price = client.get_price('ETH')
    print(f"ETH: ${eth_price:,.2f}" if eth_price else "ETH: Error")
    
    # Recent OHLC
    print("\nRecent BTC 1h candles:")
    bars = client.get_ohlc('XXBTZUSD', interval=60)
    for bar in bars[-5:]:
        print(f"  {bar['timestamp']}: O={bar['open']:.0f} H={bar['high']:.0f} L={bar['low']:.0f} C={bar['close']:.0f}")
