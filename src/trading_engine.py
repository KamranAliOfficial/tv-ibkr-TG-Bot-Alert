"""
Sequential trading engine with position tracking
Handles buy → sell → short → cover logic
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

from .ibkr_client import IBKRClient
from .market_hours import TradingSessionManager
from .logger import TradingLogger


class PositionState(Enum):
    """Position states for sequential trading"""
    FLAT = "flat"           # No position
    LONG = "long"           # Long position (bought)
    SHORT = "short"         # Short position (shorted)


@dataclass
class PositionInfo:
    """Position information tracking"""
    symbol: str
    state: PositionState
    quantity: int
    avg_price: float
    last_updated: datetime
    
    def __post_init__(self):
        if self.quantity == 0:
            self.state = PositionState.FLAT


@dataclass
class PendingOrder:
    """Pending order information for resubmission"""
    trade_id: str
    symbol: str
    action: str
    quantity: int
    original_price: Optional[float]
    submitted_time: datetime
    resubmission_count: int = 0
    last_resubmission: Optional[datetime] = None


class TradingEngine:
    """Sequential trading engine with position tracking"""
    
    def __init__(self, ibkr_client: IBKRClient, session_manager: TradingSessionManager, 
                 config: dict):
        """
        Initialize trading engine
        
        Args:
            ibkr_client: IBKR client instance
            session_manager: Trading session manager
            config: Trading configuration
        """
        self.ibkr = ibkr_client
        self.session_manager = session_manager
        self.config = config
        self.logger = TradingLogger(__name__)
        
        # Position tracking
        self.positions: Dict[str, PositionInfo] = {}
        
        # Pending orders for resubmission
        self.pending_orders: Dict[str, PendingOrder] = {}
        
        # Configuration
        self.default_quantity = config.get('default_quantity', 100)
        self.max_position_size = config.get('max_position_size', 1000)
        self.limit_order_timeout = config.get('limit_order_timeout_minutes', 5)
        self.max_resubmissions = config.get('max_resubmissions', 3)
        
        # Setup callbacks
        self._setup_callbacks()
        
        self.logger.info("Trading engine initialized")
        self.logger.info(f"Default quantity: {self.default_quantity}")
        self.logger.info(f"Max position size: {self.max_position_size}")
    
    def _setup_callbacks(self):
        """Setup IBKR client callbacks"""
        self.ibkr.set_fill_callback(self._on_fill)
        self.ibkr.set_order_status_callback(self._on_order_status)
    
    async def process_alert(self, alert: Dict) -> bool:
        """
        Process TradingView alert and execute trade
        
        Args:
            alert: Parsed alert data
            
        Returns:
            True if trade was processed successfully
        """
        try:
            symbol = alert['symbol']
            action = alert['action']
            quantity = alert.get('quantity', self.default_quantity)
            
            self.logger.info(f"Processing alert: {action} {quantity} {symbol}")
            
            # Check if trading is allowed
            trading_decision = self.session_manager.get_trading_decision()
            if not trading_decision['can_trade']:
                self.logger.warning(f"Trading not allowed: {trading_decision['reason']}")
                return False
            
            # Get current position
            await self._update_position(symbol)
            current_position = self.positions.get(symbol, PositionInfo(
                symbol=symbol, state=PositionState.FLAT, quantity=0, 
                avg_price=0.0, last_updated=datetime.utcnow()
            ))
            
            # Validate sequential trading logic
            if not self._validate_sequential_action(current_position, action):
                return False
            
            # Execute trade
            success = await self._execute_trade(symbol, action, quantity, trading_decision)
            
            if success:
                self.logger.info(f"Alert processed successfully: {action} {quantity} {symbol}")
            else:
                self.logger.error(f"Failed to process alert: {action} {quantity} {symbol}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error processing alert: {e}", exc_info=True)
            return False
    
    def _validate_sequential_action(self, position: PositionInfo, action: str) -> bool:
        """
        Validate if the action is allowed based on current position state
        
        Sequential logic:
        - FLAT → BUY (go long)
        - LONG → SELL (close long, go flat)
        - FLAT → SHORT (go short)
        - SHORT → COVER (close short, go flat)
        
        Args:
            position: Current position info
            action: Requested action
            
        Returns:
            True if action is valid
        """
        action = action.upper()
        
        valid_transitions = {
            PositionState.FLAT: ['BUY', 'SHORT'],
            PositionState.LONG: ['SELL'],
            PositionState.SHORT: ['COVER']
        }
        
        if action not in valid_transitions.get(position.state, []):
            self.logger.error(
                f"Invalid action '{action}' for position state '{position.state.value}' "
                f"on {position.symbol}. Valid actions: {valid_transitions.get(position.state, [])}"
            )
            return False
        
        return True
    
    async def _execute_trade(self, symbol: str, action: str, quantity: int, 
                           trading_decision: dict) -> bool:
        """
        Execute a trade
        
        Args:
            symbol: Stock symbol
            action: Trade action
            quantity: Quantity to trade
            trading_decision: Trading session decision
            
        Returns:
            True if trade was executed successfully
        """
        try:
            # Get contract
            contract = await self.ibkr.get_contract(symbol)
            if not contract:
                self.logger.error(f"Could not get contract for {symbol}")
                return False
            
            # Convert action to IBKR format
            ibkr_action = self._convert_action_to_ibkr(action)
            
            # Validate quantity
            if quantity > self.max_position_size:
                self.logger.error(f"Quantity {quantity} exceeds max position size {self.max_position_size}")
                return False
            
            # Determine order type and price
            order_type = trading_decision['recommended_order_type']
            limit_price = None
            
            if order_type == 'LMT':
                # Get current market price for limit orders
                market_price = await self.ibkr.get_market_price(contract)
                if market_price is None:
                    self.logger.error(f"Could not get market price for {symbol}")
                    return False
                
                # Add buffer for limit price (0.1% above for buys, below for sells)
                buffer = 0.001
                if ibkr_action == 'BUY':
                    limit_price = market_price * (1 + buffer)
                else:
                    limit_price = market_price * (1 - buffer)
                
                limit_price = round(limit_price, 2)
            
            # Place order
            trade = await self.ibkr.place_order(
                contract=contract,
                action=ibkr_action,
                quantity=quantity,
                order_type=order_type,
                limit_price=limit_price
            )
            
            if trade:
                # Track pending order for potential resubmission
                if order_type == 'LMT':
                    self._track_pending_order(trade, symbol, action, quantity, limit_price)
                
                return True
            else:
                return False
                
        except Exception as e:
            self.logger.error(f"Error executing trade: {e}", exc_info=True)
            return False
    
    def _convert_action_to_ibkr(self, action: str) -> str:
        """Convert TradingView action to IBKR action"""
        action_map = {
            'BUY': 'BUY',
            'SELL': 'SELL',
            'SHORT': 'SELL',  # Short selling is SELL action
            'COVER': 'BUY'    # Covering short is BUY action
        }
        return action_map.get(action.upper(), action.upper())
    
    def _track_pending_order(self, trade, symbol: str, action: str, quantity: int, 
                           limit_price: float):
        """Track pending order for resubmission"""
        pending_order = PendingOrder(
            trade_id=str(trade.order.orderId),
            symbol=symbol,
            action=action,
            quantity=quantity,
            original_price=limit_price,
            submitted_time=datetime.utcnow()
        )
        
        self.pending_orders[pending_order.trade_id] = pending_order
        self.logger.info(f"Tracking pending order: {pending_order.trade_id}")
    
    async def _update_position(self, symbol: str):
        """Update position information from IBKR"""
        try:
            position = await self.ibkr.get_position(symbol)
            
            if position and position.position != 0:
                # Determine position state
                if position.position > 0:
                    state = PositionState.LONG
                else:
                    state = PositionState.SHORT
                
                position_info = PositionInfo(
                    symbol=symbol,
                    state=state,
                    quantity=abs(position.position),
                    avg_price=position.avgCost,
                    last_updated=datetime.utcnow()
                )
            else:
                # No position or flat
                position_info = PositionInfo(
                    symbol=symbol,
                    state=PositionState.FLAT,
                    quantity=0,
                    avg_price=0.0,
                    last_updated=datetime.utcnow()
                )
            
            self.positions[symbol] = position_info
            self.logger.position_update(symbol, position_info.quantity, position_info.avg_price)
            
        except Exception as e:
            self.logger.error(f"Error updating position for {symbol}: {e}", exc_info=True)
    
    def _on_fill(self, fill):
        """Handle order fill callback"""
        try:
            symbol = fill.contract.symbol
            self.logger.info(f"Order filled: {symbol}")
            
            # Update position after fill
            asyncio.create_task(self._update_position(symbol))
            
            # Remove from pending orders if it was tracked
            order_id = str(fill.execution.orderId)
            if order_id in self.pending_orders:
                del self.pending_orders[order_id]
                self.logger.info(f"Removed filled order from pending: {order_id}")
                
        except Exception as e:
            self.logger.error(f"Error handling fill: {e}", exc_info=True)
    
    def _on_order_status(self, trade):
        """Handle order status change callback"""
        try:
            order_id = str(trade.order.orderId)
            status = trade.orderStatus.status
            
            # Remove cancelled or rejected orders from pending
            if status in ['Cancelled', 'ApiCancelled', 'Rejected']:
                if order_id in self.pending_orders:
                    del self.pending_orders[order_id]
                    self.logger.info(f"Removed {status.lower()} order from pending: {order_id}")
                    
        except Exception as e:
            self.logger.error(f"Error handling order status: {e}", exc_info=True)
    
    async def check_and_resubmit_orders(self):
        """Check for expired limit orders and resubmit them"""
        try:
            current_time = datetime.utcnow()
            orders_to_resubmit = []
            
            for order_id, pending_order in self.pending_orders.items():
                # Check if order has timed out
                time_since_submission = current_time - pending_order.submitted_time
                time_since_last_resubmission = (
                    current_time - pending_order.last_resubmission 
                    if pending_order.last_resubmission else time_since_submission
                )
                
                timeout_minutes = timedelta(minutes=self.limit_order_timeout)
                
                if (time_since_last_resubmission >= timeout_minutes and 
                    pending_order.resubmission_count < self.max_resubmissions):
                    orders_to_resubmit.append(pending_order)
            
            # Resubmit expired orders
            for pending_order in orders_to_resubmit:
                await self._resubmit_order(pending_order)
                
        except Exception as e:
            self.logger.error(f"Error checking orders for resubmission: {e}", exc_info=True)
    
    async def _resubmit_order(self, pending_order: PendingOrder):
        """Resubmit a pending order with current market price"""
        try:
            # Get current contract and market price
            contract = await self.ibkr.get_contract(pending_order.symbol)
            if not contract:
                self.logger.error(f"Could not get contract for resubmission: {pending_order.symbol}")
                return
            
            market_price = await self.ibkr.get_market_price(contract)
            if market_price is None:
                self.logger.error(f"Could not get market price for resubmission: {pending_order.symbol}")
                return
            
            # Cancel existing order first
            open_orders = await self.ibkr.get_open_orders()
            for trade in open_orders:
                if str(trade.order.orderId) == pending_order.trade_id:
                    await self.ibkr.cancel_order(trade)
                    break
            
            # Calculate new limit price
            ibkr_action = self._convert_action_to_ibkr(pending_order.action)
            buffer = 0.001
            
            if ibkr_action == 'BUY':
                new_limit_price = market_price * (1 + buffer)
            else:
                new_limit_price = market_price * (1 - buffer)
            
            new_limit_price = round(new_limit_price, 2)
            
            # Place new order
            new_trade = await self.ibkr.place_order(
                contract=contract,
                action=ibkr_action,
                quantity=pending_order.quantity,
                order_type='LMT',
                limit_price=new_limit_price
            )
            
            if new_trade:
                # Update pending order tracking
                old_order_id = pending_order.trade_id
                pending_order.trade_id = str(new_trade.order.orderId)
                pending_order.resubmission_count += 1
                pending_order.last_resubmission = datetime.utcnow()
                
                # Update tracking dictionary
                del self.pending_orders[old_order_id]
                self.pending_orders[pending_order.trade_id] = pending_order
                
                self.logger.order_resubmitted(
                    pending_order.trade_id, 
                    pending_order.symbol, 
                    new_limit_price, 
                    pending_order.resubmission_count
                )
            else:
                self.logger.error(f"Failed to resubmit order for {pending_order.symbol}")
                
        except Exception as e:
            self.logger.error(f"Error resubmitting order: {e}", exc_info=True)
    
    def get_position_summary(self) -> Dict[str, Dict]:
        """Get summary of all positions"""
        summary = {}
        for symbol, position in self.positions.items():
            summary[symbol] = {
                'state': position.state.value,
                'quantity': position.quantity,
                'avg_price': position.avg_price,
                'last_updated': position.last_updated.isoformat()
            }
        return summary
    
    def get_pending_orders_summary(self) -> Dict[str, Dict]:
        """Get summary of pending orders"""
        summary = {}
        for order_id, order in self.pending_orders.items():
            summary[order_id] = {
                'symbol': order.symbol,
                'action': order.action,
                'quantity': order.quantity,
                'original_price': order.original_price,
                'submitted_time': order.submitted_time.isoformat(),
                'resubmission_count': order.resubmission_count
            }
        return summary