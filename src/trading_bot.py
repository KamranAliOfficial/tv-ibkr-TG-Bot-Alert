"""
Main trading bot orchestrator that coordinates all components
"""

import asyncio
import signal
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from threading import Thread
import time

from .config import ConfigManager
from .logger import TradingLogger, setup_logging
from .webhook import WebhookServer, AlertParser
from .ibkr_client import IBKRClient
from .trading_engine import TradingEngine
from .order_manager import OrderResubmissionManager, OrderMonitor
from .telegram_notifier import TelegramNotifier
from .market_hours import TradingSessionManager


class TradingBot:
    """Main trading bot that orchestrates all components"""
    
    def __init__(self, config_path: str):
        """
        Initialize trading bot
        
        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config = ConfigManager(config_path)
        
        # Setup logging
        setup_logging(
            log_level=self.config.get('logging.level', 'INFO'),
            log_file=self.config.get('logging.file'),
            max_file_size=self.config.get('logging.max_file_size_mb', 10),
            backup_count=self.config.get('logging.backup_count', 5)
        )
        
        self.logger = TradingLogger(__name__)
        self.logger.info(f"Initializing trading bot with config: {config_path}")
        
        # Bot identification
        self.bot_name = self.config.get('bot.name', 'TradingBot')
        self.account_id = self.config.get('ibkr.account_id', '')
        
        # Initialize components
        self.ibkr_client: Optional[IBKRClient] = None
        self.trading_engine: Optional[TradingEngine] = None
        self.webhook_server: Optional[WebhookServer] = None
        self.order_manager: Optional[OrderResubmissionManager] = None
        self.order_monitor: Optional[OrderMonitor] = None
        self.telegram_notifier: Optional[TelegramNotifier] = None
        self.session_manager: Optional[TradingSessionManager] = None
        
        # State
        self.running = False
        self.webhook_thread: Optional[Thread] = None
        
        # Initialize components
        self._initialize_components()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.logger.info("Trading bot initialized successfully")
    
    def _initialize_components(self):
        """Initialize all bot components"""
        try:
            # Initialize Telegram notifier
            self._initialize_telegram()
            
            # Initialize market session manager
            self._initialize_session_manager()
            
            # Initialize IBKR client
            self._initialize_ibkr_client()
            
            # Initialize order monitor
            self.order_monitor = OrderMonitor()
            
            # Initialize trading engine
            self._initialize_trading_engine()
            
            # Initialize order resubmission manager
            self._initialize_order_manager()
            
            # Initialize webhook server
            self._initialize_webhook()
            
            self.logger.info("All components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {e}", exc_info=True)
            raise
    
    def _initialize_telegram(self):
        """Initialize Telegram notifier"""
        telegram_config = self.config.get('telegram', {})
        
        self.telegram_notifier = TelegramNotifier(
            bot_token=telegram_config.get('bot_token', ''),
            chat_id=telegram_config.get('chat_id', ''),
            enabled=telegram_config.get('enabled', False)
        )
        
        # Test connection if enabled
        if self.telegram_notifier.enabled:
            if self.telegram_notifier.test_connection_sync():
                self.logger.info("Telegram connection test successful")
            else:
                self.logger.warning("Telegram connection test failed")
    
    def _initialize_session_manager(self):
        """Initialize trading session manager"""
        market_config = self.config.get('market_hours', {})
        
        self.session_manager = TradingSessionManager(
            pre_market_start=market_config.get('pre_market_start', '04:00'),
            market_open=market_config.get('market_open', '09:30'),
            market_close=market_config.get('market_close', '16:00'),
            post_market_end=market_config.get('post_market_end', '20:00'),
            timezone=market_config.get('timezone', 'US/Eastern'),
            allow_pre_market=self.config.get('trading.allow_pre_market', True),
            allow_post_market=self.config.get('trading.allow_post_market', True)
        )
    
    def _initialize_ibkr_client(self):
        """Initialize IBKR client"""
        ibkr_config = self.config.get('ibkr', {})
        
        self.ibkr_client = IBKRClient(
            host=ibkr_config.get('host', '127.0.0.1'),
            port=ibkr_config.get('port', 7497),
            client_id=ibkr_config.get('client_id', 1),
            account_id=ibkr_config.get('account_id', ''),
            auto_reconnect=ibkr_config.get('auto_reconnect', True),
            reconnect_interval=ibkr_config.get('reconnect_interval', 30)
        )
        
        # Set up event handlers
        self.ibkr_client.on_connection_status = self._on_ibkr_connection_status
        self.ibkr_client.on_error = self._on_ibkr_error
        self.ibkr_client.on_order_fill = self._on_order_fill
        self.ibkr_client.on_order_status = self._on_order_status
    
    def _initialize_trading_engine(self):
        """Initialize trading engine"""
        trading_config = self.config.get('trading', {})
        
        self.trading_engine = TradingEngine(
            ibkr_client=self.ibkr_client,
            session_manager=self.session_manager,
            default_quantity=trading_config.get('default_quantity', 100),
            max_position_size=trading_config.get('max_position_size', 1000),
            enable_short_selling=trading_config.get('enable_short_selling', True),
            order_timeout_minutes=trading_config.get('order_timeout_minutes', 5)
        )
    
    def _initialize_order_manager(self):
        """Initialize order resubmission manager"""
        resubmission_interval = self.config.get('trading.resubmission_interval_minutes', 5)
        
        self.order_manager = OrderResubmissionManager(
            trading_engine=self.trading_engine,
            resubmission_interval_minutes=resubmission_interval
        )
    
    def _initialize_webhook(self):
        """Initialize webhook server"""
        webhook_config = self.config.get('webhook', {})
        security_config = self.config.get('security', {})
        
        self.webhook_server = WebhookServer(
            host=webhook_config.get('host', '0.0.0.0'),
            port=webhook_config.get('port', 5000),
            secret_key=security_config.get('webhook_secret', ''),
            allowed_ips=security_config.get('allowed_ips', []),
            callback=self._process_alert
        )
    
    def _process_alert(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming TradingView alert
        
        Args:
            alert_data: Alert data from TradingView
            
        Returns:
            Dict: Response data
        """
        try:
            self.logger.info(f"Processing alert: {alert_data}")
            
            # Notify about received alert
            if self.telegram_notifier:
                self.telegram_notifier.notify_alert_received(alert_data, self.account_id)
            
            # Parse and validate alert
            parser = AlertParser()
            parsed_alert = parser.parse_alert(alert_data)
            
            if not parsed_alert:
                error_msg = "Failed to parse alert data"
                self.logger.error(error_msg)
                if self.telegram_notifier:
                    self.telegram_notifier.notify_error("Alert Parsing", error_msg, account=self.account_id)
                return {'status': 'error', 'message': error_msg}
            
            # Process alert through trading engine
            result = asyncio.run(self.trading_engine.process_alert(parsed_alert))
            
            if result['success']:
                self.logger.info(f"Alert processed successfully: {result}")
                return {'status': 'success', 'message': 'Alert processed', 'data': result}
            else:
                error_msg = result.get('error', 'Unknown error')
                self.logger.error(f"Failed to process alert: {error_msg}")
                if self.telegram_notifier:
                    self.telegram_notifier.notify_error("Alert Processing", error_msg, 
                                                      parsed_alert.get('symbol', ''), self.account_id)
                return {'status': 'error', 'message': error_msg}
                
        except Exception as e:
            error_msg = f"Exception processing alert: {e}"
            self.logger.error(error_msg, exc_info=True)
            if self.telegram_notifier:
                self.telegram_notifier.notify_error("Alert Exception", str(e), account=self.account_id)
            return {'status': 'error', 'message': error_msg}
    
    def _on_ibkr_connection_status(self, connected: bool, details: str = ""):
        """Handle IBKR connection status changes"""
        status = "connected" if connected else "disconnected"
        self.logger.info(f"IBKR connection status: {status} - {details}")
        
        if self.telegram_notifier:
            self.telegram_notifier.notify_connection_status(status, details, self.account_id)
    
    def _on_ibkr_error(self, error_code: int, error_msg: str, contract_id: int = 0):
        """Handle IBKR errors"""
        self.logger.error(f"IBKR Error {error_code}: {error_msg} (Contract: {contract_id})")
        
        if self.telegram_notifier:
            self.telegram_notifier.notify_error("IBKR API", f"Code {error_code}: {error_msg}", 
                                              account=self.account_id)
    
    def _on_order_fill(self, order_id: str, symbol: str, action: str, 
                      quantity: int, price: float, timestamp: datetime):
        """Handle order fills"""
        self.logger.info(f"Order filled: {order_id} - {action} {quantity} {symbol} @ ${price:.2f}")
        
        # Record in order monitor
        if self.order_monitor:
            self.order_monitor.record_order_filled(order_id, price, timestamp)
        
        # Send Telegram notification
        if self.telegram_notifier:
            self.telegram_notifier.notify_trade_execution(symbol, action, quantity, 
                                                        price, order_id, self.account_id)
    
    def _on_order_status(self, order_id: str, status: str, filled_qty: int, 
                        remaining_qty: int, avg_price: float):
        """Handle order status changes"""
        self.logger.info(f"Order status: {order_id} - {status} (Filled: {filled_qty}, Remaining: {remaining_qty})")
        
        # Record status changes in order monitor
        if self.order_monitor:
            if status == 'Cancelled':
                self.order_monitor.record_order_cancelled(order_id)
            elif status in ['Rejected', 'Invalid']:
                self.order_monitor.record_order_rejected(order_id, status)
    
    def start(self):
        """Start the trading bot"""
        if self.running:
            self.logger.warning("Trading bot is already running")
            return
        
        try:
            self.logger.info("Starting trading bot...")
            self.running = True
            
            # Connect to IBKR
            if not self.ibkr_client.connect():
                raise Exception("Failed to connect to IBKR")
            
            # Start order resubmission manager
            if self.order_manager:
                self.order_manager.start()
            
            # Start webhook server in separate thread
            def run_webhook():
                self.webhook_server.run()
            
            self.webhook_thread = Thread(target=run_webhook, daemon=True)
            self.webhook_thread.start()
            
            # Wait for webhook to start
            time.sleep(2)
            
            # Send startup notification
            if self.telegram_notifier:
                self.telegram_notifier.notify_bot_startup(self.bot_name, self.account_id)
            
            self.logger.info(f"Trading bot '{self.bot_name}' started successfully")
            self.logger.info(f"Webhook server running on {self.webhook_server.host}:{self.webhook_server.port}")
            self.logger.info(f"IBKR account: {self.account_id}")
            
            # Keep main thread alive
            while self.running:
                time.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Failed to start trading bot: {e}", exc_info=True)
            if self.telegram_notifier:
                self.telegram_notifier.notify_error("Bot Startup", str(e), account=self.account_id)
            self.stop()
            raise
    
    def stop(self):
        """Stop the trading bot"""
        if not self.running:
            return
        
        self.logger.info("Stopping trading bot...")
        self.running = False
        
        try:
            # Send shutdown notification
            if self.telegram_notifier:
                self.telegram_notifier.notify_bot_shutdown(self.bot_name, self.account_id)
            
            # Stop order resubmission manager
            if self.order_manager:
                self.order_manager.stop()
            
            # Stop webhook server
            if self.webhook_server:
                self.webhook_server.stop()
            
            # Disconnect from IBKR
            if self.ibkr_client:
                self.ibkr_client.disconnect()
            
            # Wait for webhook thread to finish
            if self.webhook_thread and self.webhook_thread.is_alive():
                self.webhook_thread.join(timeout=5)
            
            self.logger.info("Trading bot stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}", exc_info=True)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)
    
    def get_status(self) -> Dict[str, Any]:
        """Get bot status information"""
        status = {
            'bot_name': self.bot_name,
            'account_id': self.account_id,
            'running': self.running,
            'timestamp': datetime.now().isoformat(),
            'components': {}
        }
        
        # IBKR status
        if self.ibkr_client:
            status['components']['ibkr'] = {
                'connected': self.ibkr_client.is_connected(),
                'account': self.ibkr_client.account_id
            }
        
        # Webhook status
        if self.webhook_server:
            status['components']['webhook'] = {
                'running': True,  # If we can get status, it's running
                'host': self.webhook_server.host,
                'port': self.webhook_server.port
            }
        
        # Order manager status
        if self.order_manager:
            status['components']['order_manager'] = self.order_manager.get_status()
        
        # Order statistics
        if self.order_monitor:
            status['order_statistics'] = self.order_monitor.get_performance_summary()
        
        # Trading engine status
        if self.trading_engine:
            status['components']['trading_engine'] = {
                'positions_count': len(self.trading_engine.positions),
                'pending_orders_count': len(self.trading_engine.pending_orders)
            }
        
        # Telegram status
        if self.telegram_notifier:
            status['components']['telegram'] = {
                'enabled': self.telegram_notifier.enabled
            }
        
        return status
    
    def get_positions(self) -> Dict[str, Any]:
        """Get current positions"""
        if self.trading_engine:
            return {symbol: pos.to_dict() for symbol, pos in self.trading_engine.positions.items()}
        return {}
    
    def get_recent_orders(self, limit: int = 50) -> list:
        """Get recent order history"""
        if self.order_monitor:
            return self.order_monitor.get_recent_orders(limit)
        return []