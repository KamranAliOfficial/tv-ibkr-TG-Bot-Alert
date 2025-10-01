"""
Main entry point for the TradingView-IBKR Trading Bot
"""

import os
import sys
import argparse
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from trading_bot import TradingBot
from logger import TradingLogger


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='TradingView-IBKR Trading Bot')
    parser.add_argument('--config', '-c', 
                       default='config.yaml',
                       help='Path to configuration file (default: config.yaml)')
    parser.add_argument('--status', '-s',
                       action='store_true',
                       help='Show bot status and exit')
    
    args = parser.parse_args()
    
    # Check if config file exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Configuration file '{config_path}' not found")
        print("Please create a config.yaml file or specify a different config file with --config")
        print("You can copy config.yaml.template to config.yaml and modify it")
        sys.exit(1)
    
    try:
        # Initialize trading bot
        bot = TradingBot(str(config_path))
        
        # If status flag is set, show status and exit
        if args.status:
            status = bot.get_status()
            print(f"Bot Status: {status}")
            return
        
        logger = TradingLogger(__name__)
        logger.info("Starting TradingView-IBKR Trading Bot")
        logger.info(f"Configuration loaded from: {config_path}")
        
        # Start the bot
        bot.start()
        
    except KeyboardInterrupt:
        logger = TradingLogger(__name__)
        logger.info("Received keyboard interrupt, shutting down...")
        if 'bot' in locals():
            bot.stop()
    except Exception as e:
        print(f"Fatal error: {e}")
        if 'bot' in locals():
            bot.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()