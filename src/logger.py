"""
Logging configuration for the trading bot
"""

import logging
import logging.handlers
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config


def setup_logging(config: 'Config'):
    """Setup logging configuration"""
    
    # Create logs directory if it doesn't exist
    log_file_path = Path(config.logging_file_path)
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure logging level
    level = getattr(logging, config.logging_level.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path,
        maxBytes=config.logging_max_file_size_mb * 1024 * 1024,
        backupCount=config.logging_backup_count
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Reduce noise from external libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    
    logging.info("Logging configured successfully")


class TradingLogger:
    """Specialized logger for trading operations"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def trade_executed(self, action: str, symbol: str, quantity: int, price: float, order_id: str):
        """Log trade execution"""
        self.logger.info(
            f"TRADE EXECUTED - Action: {action}, Symbol: {symbol}, "
            f"Quantity: {quantity}, Price: ${price:.2f}, Order ID: {order_id}"
        )
    
    def trade_failed(self, action: str, symbol: str, quantity: int, reason: str):
        """Log trade failure"""
        self.logger.error(
            f"TRADE FAILED - Action: {action}, Symbol: {symbol}, "
            f"Quantity: {quantity}, Reason: {reason}"
        )
    
    def alert_received(self, alert_data: dict):
        """Log received TradingView alert"""
        self.logger.info(f"ALERT RECEIVED - {alert_data}")
    
    def position_update(self, symbol: str, position: int, avg_cost: float):
        """Log position update"""
        self.logger.info(
            f"POSITION UPDATE - Symbol: {symbol}, Position: {position}, "
            f"Avg Cost: ${avg_cost:.2f}"
        )
    
    def order_resubmitted(self, order_id: str, symbol: str, new_price: float, attempt: int):
        """Log order resubmission"""
        self.logger.info(
            f"ORDER RESUBMITTED - Order ID: {order_id}, Symbol: {symbol}, "
            f"New Price: ${new_price:.2f}, Attempt: {attempt}"
        )
    
    def connection_status(self, status: str, details: str = ""):
        """Log connection status changes"""
        self.logger.info(f"CONNECTION - Status: {status}, Details: {details}")
    
    def error(self, message: str, exc_info: bool = False):
        """Log error message"""
        self.logger.error(message, exc_info=exc_info)
    
    def warning(self, message: str):
        """Log warning message"""
        self.logger.warning(message)
    
    def info(self, message: str):
        """Log info message"""
        self.logger.info(message)
    
    def debug(self, message: str):
        """Log debug message"""
        self.logger.debug(message)