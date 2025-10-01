"""
Configuration management for the trading bot
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv


class Config:
    """Configuration manager for the trading bot"""
    
    def __init__(self, config_path: Path):
        """Initialize configuration from YAML file and environment variables"""
        # Load environment variables
        load_dotenv()
        
        # Load YAML configuration
        with open(config_path, 'r') as f:
            self._config = yaml.safe_load(f)
        
        # Override with environment variables if present
        self._apply_env_overrides()
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides"""
        env_mappings = {
            'IBKR_ACCOUNT': ['ibkr', 'account'],
            'IBKR_HOST': ['ibkr', 'host'],
            'IBKR_PORT': ['ibkr', 'port'],
            'IBKR_CLIENT_ID': ['ibkr', 'client_id'],
            'TELEGRAM_BOT_TOKEN': ['telegram', 'bot_token'],
            'TELEGRAM_CHAT_ID': ['telegram', 'chat_id'],
            'WEBHOOK_SECRET': ['security', 'webhook_secret'],
            'BOT_NAME': ['bot_name'],
            'WEBHOOK_PORT': ['webhook_port'],
            'DEFAULT_QUANTITY': ['trading', 'default_quantity'],
            'MAX_POSITION_SIZE': ['trading', 'max_position_size'],
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                # Convert to appropriate type
                if env_var in ['IBKR_PORT', 'IBKR_CLIENT_ID', 'WEBHOOK_PORT', 'DEFAULT_QUANTITY', 'MAX_POSITION_SIZE']:
                    value = int(value)
                elif env_var in ['TELEGRAM_CHAT_ID']:
                    try:
                        value = int(value)
                    except ValueError:
                        pass  # Keep as string if not a number
                
                # Set nested configuration
                current = self._config
                for key in config_path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]
                current[config_path[-1]] = value
    
    @property
    def bot_name(self) -> str:
        return self._config.get('bot_name', 'TradingBot')
    
    @property
    def webhook_port(self) -> int:
        return self._config.get('webhook_port', 5000)
    
    # IBKR Configuration
    @property
    def ibkr_host(self) -> str:
        return self._config['ibkr']['host']
    
    @property
    def ibkr_port(self) -> int:
        return self._config['ibkr']['port']
    
    @property
    def ibkr_client_id(self) -> int:
        return self._config['ibkr']['client_id']
    
    @property
    def ibkr_account(self) -> str:
        return self._config['ibkr']['account']
    
    # Trading Configuration
    @property
    def default_quantity(self) -> int:
        return self._config['trading']['default_quantity']
    
    @property
    def max_position_size(self) -> int:
        return self._config['trading']['max_position_size']
    
    @property
    def enable_pre_market(self) -> bool:
        return self._config['trading']['enable_pre_market']
    
    @property
    def enable_post_market(self) -> bool:
        return self._config['trading']['enable_post_market']
    
    @property
    def limit_order_timeout_minutes(self) -> int:
        return self._config['trading']['limit_order_timeout_minutes']
    
    @property
    def max_resubmissions(self) -> int:
        return self._config['trading']['max_resubmissions']
    
    # Market Hours
    @property
    def market_hours(self) -> Dict[str, str]:
        return self._config['market_hours']
    
    # Telegram Configuration
    @property
    def telegram_enabled(self) -> bool:
        return self._config['telegram']['enabled']
    
    @property
    def telegram_bot_token(self) -> str:
        return self._config['telegram']['bot_token']
    
    @property
    def telegram_chat_id(self) -> str:
        return str(self._config['telegram']['chat_id'])
    
    # Logging Configuration
    @property
    def logging_level(self) -> str:
        return self._config['logging']['level']
    
    @property
    def logging_file_path(self) -> str:
        return self._config['logging']['file_path']
    
    @property
    def logging_max_file_size_mb(self) -> int:
        return self._config['logging']['max_file_size_mb']
    
    @property
    def logging_backup_count(self) -> int:
        return self._config['logging']['backup_count']
    
    # Security Configuration
    @property
    def webhook_secret(self) -> str:
        return self._config['security']['webhook_secret']
    
    @property
    def allowed_ips(self) -> List[str]:
        return self._config['security']['allowed_ips']
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key"""
        keys = key.split('.')
        current = self._config
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default
        return current