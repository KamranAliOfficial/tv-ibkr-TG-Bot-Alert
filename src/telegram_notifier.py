"""
Telegram notification system for trading bot alerts and updates
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
import telegram
from telegram.error import TelegramError
import json

from .logger import TradingLogger


class TelegramNotifier:
    """Handles Telegram notifications for trading events"""
    
    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        """
        Initialize Telegram notifier
        
        Args:
            bot_token: Telegram bot token
            chat_id: Chat ID to send messages to
            enabled: Whether notifications are enabled
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self.logger = TradingLogger(__name__)
        
        self.bot: Optional[telegram.Bot] = None
        
        if self.enabled and self.bot_token and self.chat_id:
            try:
                self.bot = telegram.Bot(token=self.bot_token)
                self.logger.info("Telegram notifier initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize Telegram bot: {e}")
                self.enabled = False
        else:
            self.logger.warning("Telegram notifications disabled - missing token or chat ID")
            self.enabled = False
    
    async def send_message(self, message: str, parse_mode: str = 'HTML') -> bool:
        """
        Send a message via Telegram
        
        Args:
            message: Message to send
            parse_mode: Parse mode for formatting (HTML or Markdown)
            
        Returns:
            bool: True if message sent successfully
        """
        if not self.enabled or not self.bot:
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode
            )
            self.logger.debug("Telegram message sent successfully")
            return True
            
        except TelegramError as e:
            self.logger.error(f"Telegram error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error sending Telegram message: {e}")
            return False
    
    def send_message_sync(self, message: str, parse_mode: str = 'HTML') -> bool:
        """
        Send a message synchronously
        
        Args:
            message: Message to send
            parse_mode: Parse mode for formatting
            
        Returns:
            bool: True if message sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            # Create new event loop for sync operation
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                return loop.run_until_complete(self.send_message(message, parse_mode))
            finally:
                loop.close()
                
        except Exception as e:
            self.logger.error(f"Error in sync message send: {e}")
            return False
    
    def notify_trade_execution(self, symbol: str, action: str, quantity: int, 
                             price: float, order_id: str, account: str = "") -> bool:
        """
        Notify about trade execution
        
        Args:
            symbol: Trading symbol
            action: Trade action (BUY, SELL, etc.)
            quantity: Quantity traded
            price: Execution price
            order_id: Order ID
            account: Account identifier
            
        Returns:
            bool: True if notification sent successfully
        """
        emoji_map = {
            'BUY': '🟢',
            'SELL': '🔴',
            'SHORT': '🟠',
            'COVER': '🔵'
        }
        
        emoji = emoji_map.get(action.upper(), '⚪')
        account_text = f" ({account})" if account else ""
        
        message = f"""
{emoji} <b>TRADE EXECUTED</b>{account_text}

<b>Symbol:</b> {symbol}
<b>Action:</b> {action.upper()}
<b>Quantity:</b> {quantity:,}
<b>Price:</b> ${price:.2f}
<b>Total:</b> ${price * quantity:,.2f}
<b>Order ID:</b> {order_id}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        return self.send_message_sync(message)
    
    def notify_order_placed(self, symbol: str, action: str, quantity: int, 
                          order_type: str, price: Optional[float] = None, 
                          order_id: str = "", account: str = "") -> bool:
        """
        Notify about order placement
        
        Args:
            symbol: Trading symbol
            action: Trade action
            quantity: Quantity
            order_type: Order type (MKT, LMT, etc.)
            price: Order price (for limit orders)
            order_id: Order ID
            account: Account identifier
            
        Returns:
            bool: True if notification sent successfully
        """
        account_text = f" ({account})" if account else ""
        price_text = f" @ ${price:.2f}" if price else ""
        
        message = f"""
📋 <b>ORDER PLACED</b>{account_text}

<b>Symbol:</b> {symbol}
<b>Action:</b> {action.upper()}
<b>Quantity:</b> {quantity:,}
<b>Type:</b> {order_type}{price_text}
<b>Order ID:</b> {order_id}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        return self.send_message_sync(message)
    
    def notify_order_cancelled(self, symbol: str, order_id: str, 
                             reason: str = "", account: str = "") -> bool:
        """
        Notify about order cancellation
        
        Args:
            symbol: Trading symbol
            order_id: Order ID
            reason: Cancellation reason
            account: Account identifier
            
        Returns:
            bool: True if notification sent successfully
        """
        account_text = f" ({account})" if account else ""
        reason_text = f"\n<b>Reason:</b> {reason}" if reason else ""
        
        message = f"""
❌ <b>ORDER CANCELLED</b>{account_text}

<b>Symbol:</b> {symbol}
<b>Order ID:</b> {order_id}{reason_text}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        return self.send_message_sync(message)
    
    def notify_order_resubmitted(self, symbol: str, old_order_id: str, 
                               new_order_id: str, new_price: float, 
                               account: str = "") -> bool:
        """
        Notify about order resubmission
        
        Args:
            symbol: Trading symbol
            old_order_id: Original order ID
            new_order_id: New order ID
            new_price: New order price
            account: Account identifier
            
        Returns:
            bool: True if notification sent successfully
        """
        account_text = f" ({account})" if account else ""
        
        message = f"""
🔄 <b>ORDER RESUBMITTED</b>{account_text}

<b>Symbol:</b> {symbol}
<b>Old Order:</b> {old_order_id}
<b>New Order:</b> {new_order_id}
<b>New Price:</b> ${new_price:.2f}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        return self.send_message_sync(message)
    
    def notify_error(self, error_type: str, message: str, 
                    symbol: str = "", account: str = "") -> bool:
        """
        Notify about errors
        
        Args:
            error_type: Type of error
            message: Error message
            symbol: Related symbol (if any)
            account: Account identifier
            
        Returns:
            bool: True if notification sent successfully
        """
        account_text = f" ({account})" if account else ""
        symbol_text = f"\n<b>Symbol:</b> {symbol}" if symbol else ""
        
        error_message = f"""
🚨 <b>ERROR</b>{account_text}

<b>Type:</b> {error_type}{symbol_text}
<b>Message:</b> {message}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        return self.send_message_sync(error_message)
    
    def notify_connection_status(self, status: str, details: str = "", 
                               account: str = "") -> bool:
        """
        Notify about connection status changes
        
        Args:
            status: Connection status (connected, disconnected, reconnecting)
            details: Additional details
            account: Account identifier
            
        Returns:
            bool: True if notification sent successfully
        """
        status_emoji = {
            'connected': '🟢',
            'disconnected': '🔴',
            'reconnecting': '🟡',
            'error': '🚨'
        }
        
        emoji = status_emoji.get(status.lower(), '⚪')
        account_text = f" ({account})" if account else ""
        details_text = f"\n<b>Details:</b> {details}" if details else ""
        
        message = f"""
{emoji} <b>CONNECTION {status.upper()}</b>{account_text}

<b>IBKR API Status:</b> {status.title()}{details_text}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        return self.send_message_sync(message)
    
    def notify_alert_received(self, alert_data: Dict[str, Any], account: str = "") -> bool:
        """
        Notify about received TradingView alert
        
        Args:
            alert_data: Alert data from TradingView
            account: Account identifier
            
        Returns:
            bool: True if notification sent successfully
        """
        account_text = f" ({account})" if account else ""
        
        message = f"""
📡 <b>ALERT RECEIVED</b>{account_text}

<b>Symbol:</b> {alert_data.get('symbol', 'N/A')}
<b>Action:</b> {alert_data.get('action', 'N/A').upper()}
<b>Quantity:</b> {alert_data.get('quantity', 'N/A')}
<b>Price:</b> ${alert_data.get('price', 0):.2f}
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        return self.send_message_sync(message)
    
    def notify_bot_startup(self, bot_name: str, account: str = "") -> bool:
        """
        Notify about bot startup
        
        Args:
            bot_name: Name of the bot
            account: Account identifier
            
        Returns:
            bool: True if notification sent successfully
        """
        account_text = f" ({account})" if account else ""
        
        message = f"""
🚀 <b>BOT STARTED</b>{account_text}

<b>Bot:</b> {bot_name}
<b>Status:</b> Online and ready
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        return self.send_message_sync(message)
    
    def notify_bot_shutdown(self, bot_name: str, account: str = "") -> bool:
        """
        Notify about bot shutdown
        
        Args:
            bot_name: Name of the bot
            account: Account identifier
            
        Returns:
            bool: True if notification sent successfully
        """
        account_text = f" ({account})" if account else ""
        
        message = f"""
🛑 <b>BOT STOPPED</b>{account_text}

<b>Bot:</b> {bot_name}
<b>Status:</b> Shutdown
<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip()
        
        return self.send_message_sync(message)
    
    def notify_daily_summary(self, summary_data: Dict[str, Any], account: str = "") -> bool:
        """
        Send daily trading summary
        
        Args:
            summary_data: Summary statistics
            account: Account identifier
            
        Returns:
            bool: True if notification sent successfully
        """
        account_text = f" ({account})" if account else ""
        
        message = f"""
📊 <b>DAILY SUMMARY</b>{account_text}

<b>Total Orders:</b> {summary_data.get('total_orders', 0)}
<b>Filled Orders:</b> {summary_data.get('filled_orders', 0)}
<b>Success Rate:</b> {summary_data.get('success_rate', 0):.1%}
<b>Total Volume:</b> ${summary_data.get('total_volume', 0):,.2f}
<b>Avg Fill Time:</b> {summary_data.get('avg_fill_time_minutes', 0):.1f}m
<b>Resubmissions:</b> {summary_data.get('resubmitted_orders', 0)}

<b>Date:</b> {datetime.now().strftime('%Y-%m-%d')}
        """.strip()
        
        return self.send_message_sync(message)
    
    async def test_connection(self) -> bool:
        """
        Test Telegram connection
        
        Returns:
            bool: True if connection successful
        """
        if not self.enabled or not self.bot:
            return False
        
        try:
            await self.bot.get_me()
            test_message = "🤖 Trading Bot - Connection Test Successful"
            return await self.send_message(test_message)
            
        except Exception as e:
            self.logger.error(f"Telegram connection test failed: {e}")
            return False
    
    def test_connection_sync(self) -> bool:
        """
        Test Telegram connection synchronously
        
        Returns:
            bool: True if connection successful
        """
        if not self.enabled:
            return False
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                return loop.run_until_complete(self.test_connection())
            finally:
                loop.close()
                
        except Exception as e:
            self.logger.error(f"Error in sync connection test: {e}")
            return False