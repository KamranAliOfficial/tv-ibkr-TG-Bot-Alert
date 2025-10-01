"""
Interactive Brokers API client with connection management and auto-reconnect
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from ib_insync import IB, Stock, Order, Trade, Position, Contract
from ib_insync.objects import Fill

from .logger import TradingLogger


class IBKRClient:
    """Interactive Brokers API client with enhanced connection management"""
    
    def __init__(self, host: str, port: int, client_id: int, account: str):
        """
        Initialize IBKR client
        
        Args:
            host: IBKR Gateway/TWS host
            port: IBKR Gateway/TWS port
            client_id: Unique client ID
            account: IBKR account number
        """
        self.host = host
        self.port = port
        self.client_id = client_id
        self.account = account
        
        self.ib = IB()
        self.logger = TradingLogger(__name__)
        
        # Connection management
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5  # seconds
        
        # Callbacks
        self.on_fill_callback: Optional[Callable[[Fill], None]] = None
        self.on_order_status_callback: Optional[Callable[[Trade], None]] = None
        self.on_error_callback: Optional[Callable[[str], None]] = None
        
        # Setup event handlers
        self._setup_event_handlers()
    
    def _setup_event_handlers(self):
        """Setup IB event handlers"""
        
        def on_connected():
            """Handle connection established"""
            self.connected = True
            self.reconnect_attempts = 0
            self.logger.connection_status("Connected", f"Client ID: {self.client_id}")
        
        def on_disconnected():
            """Handle disconnection"""
            self.connected = False
            self.logger.connection_status("Disconnected", "Connection lost")
            
            # Schedule reconnection
            asyncio.create_task(self._auto_reconnect())
        
        def on_error(reqId, errorCode, errorString, contract):
            """Handle API errors"""
            error_msg = f"Error {errorCode}: {errorString}"
            if contract:
                error_msg += f" (Contract: {contract})"
            
            self.logger.error(f"IBKR API Error: {error_msg}")
            
            if self.on_error_callback:
                self.on_error_callback(error_msg)
            
            # Handle specific error codes
            if errorCode in [1100, 1101, 1102]:  # Connection lost errors
                self.connected = False
        
        def on_fill(trade, fill):
            """Handle order fills"""
            self.logger.trade_executed(
                action=trade.order.action,
                symbol=trade.contract.symbol,
                quantity=fill.execution.shares,
                price=fill.execution.price,
                order_id=str(trade.order.orderId)
            )
            
            if self.on_fill_callback:
                self.on_fill_callback(fill)
        
        def on_order_status(trade):
            """Handle order status changes"""
            self.logger.info(
                f"Order Status Update - ID: {trade.order.orderId}, "
                f"Status: {trade.orderStatus.status}, "
                f"Filled: {trade.orderStatus.filled}/{trade.order.totalQuantity}"
            )
            
            if self.on_order_status_callback:
                self.on_order_status_callback(trade)
        
        # Connect event handlers
        self.ib.connectedEvent += on_connected
        self.ib.disconnectedEvent += on_disconnected
        self.ib.errorEvent += on_error
        self.ib.fillEvent += on_fill
        self.ib.orderStatusEvent += on_order_status
    
    async def connect(self) -> bool:
        """
        Connect to IBKR Gateway/TWS
        
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            self.logger.info(f"Connecting to IBKR at {self.host}:{self.port}")
            
            await self.ib.connectAsync(
                host=self.host,
                port=self.port,
                clientId=self.client_id,
                timeout=10
            )
            
            # Wait for connection to be established
            await asyncio.sleep(1)
            
            if self.ib.isConnected():
                self.connected = True
                self.logger.connection_status("Connected", f"Account: {self.account}")
                return True
            else:
                self.logger.error("Failed to establish connection")
                return False
                
        except Exception as e:
            self.logger.error(f"Connection failed: {e}", exc_info=True)
            return False
    
    async def disconnect(self):
        """Disconnect from IBKR"""
        try:
            if self.ib.isConnected():
                self.ib.disconnect()
                self.connected = False
                self.logger.connection_status("Disconnected", "Manual disconnect")
        except Exception as e:
            self.logger.error(f"Disconnect error: {e}", exc_info=True)
    
    async def _auto_reconnect(self):
        """Automatic reconnection logic"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            self.logger.error("Max reconnection attempts reached")
            return
        
        self.reconnect_attempts += 1
        self.logger.info(f"Attempting reconnection {self.reconnect_attempts}/{self.max_reconnect_attempts}")
        
        await asyncio.sleep(self.reconnect_delay)
        
        success = await self.connect()
        if not success:
            # Exponential backoff
            self.reconnect_delay = min(self.reconnect_delay * 2, 60)
            await self._auto_reconnect()
        else:
            self.reconnect_delay = 5  # Reset delay on successful connection
    
    def is_connected(self) -> bool:
        """Check if connected to IBKR"""
        return self.connected and self.ib.isConnected()
    
    async def get_contract(self, symbol: str, exchange: str = "SMART") -> Optional[Contract]:
        """
        Get contract for a symbol
        
        Args:
            symbol: Stock symbol
            exchange: Exchange (default: SMART)
            
        Returns:
            Contract object or None if not found
        """
        try:
            stock = Stock(symbol, exchange, "USD")
            contracts = await self.ib.qualifyContractsAsync(stock)
            
            if contracts:
                return contracts[0]
            else:
                self.logger.error(f"Contract not found for symbol: {symbol}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting contract for {symbol}: {e}", exc_info=True)
            return None
    
    async def get_market_price(self, contract: Contract) -> Optional[float]:
        """
        Get current market price for a contract
        
        Args:
            contract: Contract to get price for
            
        Returns:
            Current market price or None if unavailable
        """
        try:
            ticker = self.ib.reqMktData(contract)
            await asyncio.sleep(2)  # Wait for market data
            
            # Try different price fields
            price = ticker.marketPrice()
            if price and price > 0:
                return price
            
            # Fallback to bid/ask midpoint
            if ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
                return (ticker.bid + ticker.ask) / 2
            
            # Fallback to last price
            if ticker.last and ticker.last > 0:
                return ticker.last
            
            self.logger.warning(f"No valid price data for {contract.symbol}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting market price for {contract.symbol}: {e}", exc_info=True)
            return None
        finally:
            # Cancel market data subscription
            try:
                self.ib.cancelMktData(contract)
            except:
                pass
    
    async def place_order(self, contract: Contract, action: str, quantity: int, 
                         order_type: str = "MKT", limit_price: float = None) -> Optional[Trade]:
        """
        Place an order
        
        Args:
            contract: Contract to trade
            action: BUY or SELL
            quantity: Number of shares
            order_type: Order type (MKT, LMT)
            limit_price: Limit price for LMT orders
            
        Returns:
            Trade object or None if failed
        """
        try:
            if not self.is_connected():
                self.logger.error("Not connected to IBKR")
                return None
            
            # Create order
            order = Order()
            order.action = action.upper()
            order.totalQuantity = quantity
            order.orderType = order_type
            order.account = self.account
            
            if order_type == "LMT" and limit_price:
                order.lmtPrice = limit_price
            
            # Place order
            trade = self.ib.placeOrder(contract, order)
            
            self.logger.info(
                f"Order placed - ID: {trade.order.orderId}, "
                f"Action: {action}, Symbol: {contract.symbol}, "
                f"Quantity: {quantity}, Type: {order_type}"
                + (f", Limit: ${limit_price:.2f}" if limit_price else "")
            )
            
            return trade
            
        except Exception as e:
            self.logger.error(f"Error placing order: {e}", exc_info=True)
            return None
    
    async def cancel_order(self, trade: Trade) -> bool:
        """
        Cancel an order
        
        Args:
            trade: Trade object to cancel
            
        Returns:
            True if cancellation was successful
        """
        try:
            self.ib.cancelOrder(trade.order)
            self.logger.info(f"Order cancelled - ID: {trade.order.orderId}")
            return True
        except Exception as e:
            self.logger.error(f"Error cancelling order {trade.order.orderId}: {e}", exc_info=True)
            return False
    
    async def get_positions(self) -> List[Position]:
        """
        Get current positions
        
        Returns:
            List of Position objects
        """
        try:
            if not self.is_connected():
                return []
            
            positions = self.ib.positions(account=self.account)
            return [pos for pos in positions if pos.position != 0]
            
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}", exc_info=True)
            return []
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a specific symbol
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Position object or None if no position
        """
        positions = await self.get_positions()
        for pos in positions:
            if pos.contract.symbol == symbol:
                return pos
        return None
    
    async def get_open_orders(self) -> List[Trade]:
        """
        Get open orders
        
        Returns:
            List of open Trade objects
        """
        try:
            if not self.is_connected():
                return []
            
            trades = self.ib.openTrades()
            return [trade for trade in trades if trade.orderStatus.status in ['Submitted', 'PreSubmitted']]
            
        except Exception as e:
            self.logger.error(f"Error getting open orders: {e}", exc_info=True)
            return []
    
    def set_fill_callback(self, callback: Callable[[Fill], None]):
        """Set callback for order fills"""
        self.on_fill_callback = callback
    
    def set_order_status_callback(self, callback: Callable[[Trade], None]):
        """Set callback for order status changes"""
        self.on_order_status_callback = callback
    
    def set_error_callback(self, callback: Callable[[str], None]):
        """Set callback for errors"""
        self.on_error_callback = callback