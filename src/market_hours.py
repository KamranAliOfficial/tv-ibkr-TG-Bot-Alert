"""
Market hours detection and trading session management
"""

from datetime import datetime, time
from typing import Tuple
import pytz
from enum import Enum

from .logger import TradingLogger


class MarketSession(Enum):
    """Market session types"""
    PRE_MARKET = "pre_market"
    MARKET = "market"
    POST_MARKET = "post_market"
    CLOSED = "closed"


class MarketHours:
    """Market hours manager for US stock market"""
    
    def __init__(self, config_hours: dict):
        """
        Initialize market hours
        
        Args:
            config_hours: Market hours configuration from config file
        """
        self.logger = TradingLogger(__name__)
        
        # Parse time strings from config
        self.pre_market_start = self._parse_time(config_hours['pre_market_start'])
        self.market_open = self._parse_time(config_hours['market_open'])
        self.market_close = self._parse_time(config_hours['market_close'])
        self.post_market_end = self._parse_time(config_hours['post_market_end'])
        
        # US Eastern timezone
        self.eastern_tz = pytz.timezone('US/Eastern')
        
        self.logger.info(f"Market hours configured:")
        self.logger.info(f"  Pre-market: {self.pre_market_start} - {self.market_open}")
        self.logger.info(f"  Market: {self.market_open} - {self.market_close}")
        self.logger.info(f"  Post-market: {self.market_close} - {self.post_market_end}")
    
    def _parse_time(self, time_str: str) -> time:
        """Parse time string in HH:MM format"""
        try:
            hour, minute = map(int, time_str.split(':'))
            return time(hour, minute)
        except ValueError:
            raise ValueError(f"Invalid time format: {time_str}. Expected HH:MM")
    
    def get_current_session(self, dt: datetime = None) -> MarketSession:
        """
        Get current market session
        
        Args:
            dt: Datetime to check (defaults to current time)
            
        Returns:
            Current market session
        """
        if dt is None:
            dt = datetime.now(self.eastern_tz)
        elif dt.tzinfo is None:
            # Assume UTC if no timezone info
            dt = pytz.utc.localize(dt).astimezone(self.eastern_tz)
        else:
            dt = dt.astimezone(self.eastern_tz)
        
        # Check if it's a weekend
        if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return MarketSession.CLOSED
        
        current_time = dt.time()
        
        # Determine session
        if self.pre_market_start <= current_time < self.market_open:
            return MarketSession.PRE_MARKET
        elif self.market_open <= current_time < self.market_close:
            return MarketSession.MARKET
        elif self.market_close <= current_time < self.post_market_end:
            return MarketSession.POST_MARKET
        else:
            return MarketSession.CLOSED
    
    def is_market_open(self, dt: datetime = None) -> bool:
        """
        Check if market is open (regular trading hours)
        
        Args:
            dt: Datetime to check (defaults to current time)
            
        Returns:
            True if market is open
        """
        return self.get_current_session(dt) == MarketSession.MARKET
    
    def is_extended_hours(self, dt: datetime = None) -> bool:
        """
        Check if in extended hours (pre or post market)
        
        Args:
            dt: Datetime to check (defaults to current time)
            
        Returns:
            True if in extended hours
        """
        session = self.get_current_session(dt)
        return session in [MarketSession.PRE_MARKET, MarketSession.POST_MARKET]
    
    def is_trading_allowed(self, dt: datetime = None) -> bool:
        """
        Check if trading is allowed (market or extended hours)
        
        Args:
            dt: Datetime to check (defaults to current time)
            
        Returns:
            True if trading is allowed
        """
        session = self.get_current_session(dt)
        return session in [MarketSession.PRE_MARKET, MarketSession.MARKET, MarketSession.POST_MARKET]
    
    def get_session_info(self, dt: datetime = None) -> dict:
        """
        Get detailed session information
        
        Args:
            dt: Datetime to check (defaults to current time)
            
        Returns:
            Dictionary with session information
        """
        if dt is None:
            dt = datetime.now(self.eastern_tz)
        elif dt.tzinfo is None:
            dt = pytz.utc.localize(dt).astimezone(self.eastern_tz)
        else:
            dt = dt.astimezone(self.eastern_tz)
        
        session = self.get_current_session(dt)
        
        return {
            'current_time': dt.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'session': session.value,
            'is_market_open': session == MarketSession.MARKET,
            'is_extended_hours': session in [MarketSession.PRE_MARKET, MarketSession.POST_MARKET],
            'is_trading_allowed': session != MarketSession.CLOSED,
            'is_weekend': dt.weekday() >= 5
        }
    
    def get_next_session_change(self, dt: datetime = None) -> Tuple[datetime, MarketSession]:
        """
        Get the next session change time
        
        Args:
            dt: Current datetime (defaults to now)
            
        Returns:
            Tuple of (next_change_time, next_session)
        """
        if dt is None:
            dt = datetime.now(self.eastern_tz)
        elif dt.tzinfo is None:
            dt = pytz.utc.localize(dt).astimezone(self.eastern_tz)
        else:
            dt = dt.astimezone(self.eastern_tz)
        
        current_session = self.get_current_session(dt)
        current_date = dt.date()
        
        # Define session transitions for the current day
        transitions = [
            (datetime.combine(current_date, self.pre_market_start, self.eastern_tz), MarketSession.PRE_MARKET),
            (datetime.combine(current_date, self.market_open, self.eastern_tz), MarketSession.MARKET),
            (datetime.combine(current_date, self.market_close, self.eastern_tz), MarketSession.POST_MARKET),
            (datetime.combine(current_date, self.post_market_end, self.eastern_tz), MarketSession.CLOSED),
        ]
        
        # Find next transition
        for transition_time, next_session in transitions:
            if dt < transition_time:
                return transition_time, next_session
        
        # If no transition today, get first transition tomorrow
        from datetime import timedelta
        next_date = current_date + timedelta(days=1)
        
        # Skip weekends
        while next_date.weekday() >= 5:
            next_date += timedelta(days=1)
        
        next_transition = datetime.combine(next_date, self.pre_market_start, self.eastern_tz)
        return next_transition, MarketSession.PRE_MARKET
    
    def should_use_limit_order(self, dt: datetime = None) -> bool:
        """
        Determine if limit orders should be used based on market session
        
        Args:
            dt: Datetime to check (defaults to current time)
            
        Returns:
            True if limit orders should be used (extended hours)
        """
        session = self.get_current_session(dt)
        return session in [MarketSession.PRE_MARKET, MarketSession.POST_MARKET]
    
    def should_use_market_order(self, dt: datetime = None) -> bool:
        """
        Determine if market orders should be used based on market session
        
        Args:
            dt: Datetime to check (defaults to current time)
            
        Returns:
            True if market orders should be used (regular hours)
        """
        return self.get_current_session(dt) == MarketSession.MARKET


class TradingSessionManager:
    """Manager for trading session logic and order type decisions"""
    
    def __init__(self, market_hours: MarketHours, enable_pre_market: bool = True, 
                 enable_post_market: bool = True):
        """
        Initialize trading session manager
        
        Args:
            market_hours: MarketHours instance
            enable_pre_market: Whether pre-market trading is enabled
            enable_post_market: Whether post-market trading is enabled
        """
        self.market_hours = market_hours
        self.enable_pre_market = enable_pre_market
        self.enable_post_market = enable_post_market
        self.logger = TradingLogger(__name__)
        
        self.logger.info(f"Trading session manager initialized:")
        self.logger.info(f"  Pre-market enabled: {enable_pre_market}")
        self.logger.info(f"  Post-market enabled: {enable_post_market}")
    
    def can_trade_now(self, dt: datetime = None) -> bool:
        """
        Check if trading is allowed at the current time
        
        Args:
            dt: Datetime to check (defaults to current time)
            
        Returns:
            True if trading is allowed
        """
        session = self.market_hours.get_current_session(dt)
        
        if session == MarketSession.MARKET:
            return True
        elif session == MarketSession.PRE_MARKET:
            return self.enable_pre_market
        elif session == MarketSession.POST_MARKET:
            return self.enable_post_market
        else:
            return False
    
    def get_order_type(self, dt: datetime = None) -> str:
        """
        Get recommended order type based on current session
        
        Args:
            dt: Datetime to check (defaults to current time)
            
        Returns:
            Order type: 'MKT' for market orders, 'LMT' for limit orders
        """
        session = self.market_hours.get_current_session(dt)
        
        if session == MarketSession.MARKET:
            return 'MKT'
        elif session in [MarketSession.PRE_MARKET, MarketSession.POST_MARKET]:
            return 'LMT'
        else:
            # Should not trade when market is closed
            return 'LMT'
    
    def get_trading_decision(self, dt: datetime = None) -> dict:
        """
        Get comprehensive trading decision information
        
        Args:
            dt: Datetime to check (defaults to current time)
            
        Returns:
            Dictionary with trading decision information
        """
        session_info = self.market_hours.get_session_info(dt)
        can_trade = self.can_trade_now(dt)
        order_type = self.get_order_type(dt) if can_trade else None
        
        return {
            **session_info,
            'can_trade': can_trade,
            'recommended_order_type': order_type,
            'reason': self._get_trading_reason(session_info['session'], can_trade)
        }
    
    def _get_trading_reason(self, session: str, can_trade: bool) -> str:
        """Get reason for trading decision"""
        if not can_trade:
            if session == 'closed':
                return "Market is closed"
            elif session == 'pre_market' and not self.enable_pre_market:
                return "Pre-market trading disabled"
            elif session == 'post_market' and not self.enable_post_market:
                return "Post-market trading disabled"
        else:
            if session == 'market':
                return "Regular market hours - using market orders"
            elif session in ['pre_market', 'post_market']:
                return f"Extended hours ({session}) - using limit orders"
        
        return "Unknown"