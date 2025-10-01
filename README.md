# TradingView-IBKR Trading Bot

A comprehensive trading bot that connects TradingView alerts to Interactive Brokers (IBKR) for automated trade execution. The bot supports pre-market, market, and post-market trading sessions with sequential trading logic and multi-account support.

## Features

- 🔗 **TradingView Integration**: Webhook listener for TradingView alerts
- 📈 **IBKR API Integration**: Direct connection to Interactive Brokers for trade execution
- 🔄 **Sequential Trading Logic**: Supports buy → sell → short → cover sequences with position tracking
- ⏰ **Market Hours Support**: Pre-market, market, and post-market execution
- 🔁 **Order Resubmission**: Automatic resubmission of unfilled limit orders every 3-5 minutes
- 🏢 **Multi-Bot Support**: One bot per IBKR account for easy scaling
- 📱 **Telegram Notifications**: Real-time alerts for all transactions and errors
- 🔌 **Auto-Reconnect**: Automatic reconnection to IBKR API if disconnected
- 📊 **Comprehensive Logging**: Detailed logging of all activities and performance metrics
- 🛡️ **Security**: IP whitelisting and HMAC signature validation for webhooks

## Quick Start

### 1. Prerequisites

- Python 3.8 or higher
- Interactive Brokers account with API access
- TradingView account with alert capabilities
- Telegram bot (optional, for notifications)

### 2. Installation

```bash
# Clone or download the project
cd ibkr-tradingview-alert-project

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

1. Copy the configuration template:
```bash
cp config.yaml config.yaml
```

2. Copy the environment template:
```bash
cp .env.template .env
```

3. Edit `config.yaml` and `.env` with your settings (see [Configuration](#configuration) section)

### 4. IBKR Setup

1. Install and configure Interactive Brokers TWS or IB Gateway
2. Enable API connections in TWS/Gateway:
   - Go to File → Global Configuration → API → Settings
   - Enable "Enable ActiveX and Socket Clients"
   - Set Socket port (default: 7497 for paper trading, 7496 for live)
   - Add your IP to trusted IPs if needed

### 5. Run the Bot

```bash
# Start the trading bot
python main.py

# Or with custom config file
python main.py --config my_config.yaml

# Check bot status
python main.py --status
```

## Configuration

### Main Configuration File (config.yaml)

```yaml
# Bot identification
bot:
  name: "TradingBot_Account1"
  description: "Trading bot for IBKR account 1"

# Interactive Brokers connection
ibkr:
  host: "127.0.0.1"
  port: 7497  # 7497 for paper, 7496 for live
  client_id: 1
  account_id: "DU123456"  # Your IBKR account ID
  auto_reconnect: true
  reconnect_interval: 30

# Webhook server settings
webhook:
  host: "0.0.0.0"
  port: 5000
  path: "/webhook"

# Trading parameters
trading:
  default_quantity: 100
  max_position_size: 1000
  enable_short_selling: true
  allow_pre_market: true
  allow_post_market: true
  order_timeout_minutes: 5
  resubmission_interval_minutes: 5

# Market hours (US Eastern Time)
market_hours:
  pre_market_start: "04:00"
  market_open: "09:30"
  market_close: "16:00"
  post_market_end: "20:00"
  timezone: "US/Eastern"

# Telegram notifications
telegram:
  enabled: true
  bot_token: ""  # Set in .env file
  chat_id: ""    # Set in .env file

# Security settings
security:
  webhook_secret: ""  # Set in .env file
  allowed_ips: []     # Empty = allow all

# Logging configuration
logging:
  level: "INFO"
  file: "logs/trading_bot.log"
  max_file_size_mb: 10
  backup_count: 5
```

### Environment Variables (.env)

```bash
# IBKR Account Details
IBKR_ACCOUNT_ID=DU123456
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1

# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Webhook Security
WEBHOOK_SECRET=your_webhook_secret_key

# Bot Configuration
BOT_NAME=TradingBot_Account1

# Trading Settings
DEFAULT_QUANTITY=100
MAX_POSITION_SIZE=1000
```

## TradingView Alert Setup

### Alert Message Format

Configure your TradingView alerts to send JSON data in this format:

```json
{
  "action": "buy",
  "symbol": "AAPL",
  "quantity": 100,
  "price": 150.50,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Required Fields

- `action`: "buy", "sell", "short", or "cover"
- `symbol`: Stock symbol (e.g., "AAPL", "TSLA")
- `quantity`: Number of shares (integer)

### Optional Fields

- `price`: Limit price (if not provided, uses market order)
- `timestamp`: Alert timestamp (ISO format)

### TradingView Webhook URL

Set your TradingView webhook URL to:
```
http://your-server-ip:5000/webhook
```

For local testing:
```
http://localhost:5000/webhook
```

## Multi-Bot Setup

To run multiple bots for different IBKR accounts:

1. Create separate config files:
```bash
cp config.yaml config_account1.yaml
cp config.yaml config_account2.yaml
```

2. Modify each config file with different:
   - Bot name
   - IBKR account ID
   - IBKR client ID
   - Webhook port
   - Log file paths

3. Run each bot separately:
```bash
python main.py --config config_account1.yaml
python main.py --config config_account2.yaml
```

## Trading Logic

### Sequential Trading

The bot enforces sequential trading logic:

1. **Buy** → **Sell** (Long position)
2. **Short** → **Cover** (Short position)

### Position Tracking

- Tracks current position for each symbol
- Prevents invalid sequences (e.g., selling without owning)
- Maintains position state across bot restarts

### Order Types by Market Session

- **Market Hours**: Market orders (MKT)
- **Pre/Post Market**: Limit orders (LMT)
- **Order Resubmission**: Unfilled limit orders are automatically resubmitted at current ask price

## Telegram Notifications

The bot sends notifications for:

- ✅ Trade executions
- 📋 Order placements
- ❌ Order cancellations
- 🔄 Order resubmissions
- 🚨 Errors and warnings
- 🔌 Connection status changes
- 📊 Daily summaries

### Setting Up Telegram

1. Create a Telegram bot:
   - Message @BotFather on Telegram
   - Use `/newbot` command
   - Get your bot token

2. Get your chat ID:
   - Message your bot
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find your chat ID in the response

3. Add credentials to `.env` file

## Logging

### Log Levels

- **DEBUG**: Detailed debugging information
- **INFO**: General information about bot operations
- **WARNING**: Warning messages for potential issues
- **ERROR**: Error messages for failures

### Log Files

- Main log: `logs/trading_bot.log`
- Automatic rotation when file size exceeds limit
- Configurable backup count

### Log Format

```
2024-01-15 10:30:00,123 - INFO - trading_engine - Order executed: BUY 100 AAPL @ $150.50
2024-01-15 10:30:01,456 - ERROR - ibkr_client - Connection lost, attempting reconnect...
```

## API Endpoints

The bot exposes several HTTP endpoints:

### Webhook Endpoint
- **POST** `/webhook` - Receive TradingView alerts

### Status Endpoints
- **GET** `/health` - Health check
- **GET** `/status` - Bot status and statistics

## Security

### Webhook Security

1. **IP Whitelisting**: Restrict access to specific IP addresses
2. **HMAC Signature**: Validate webhook authenticity using secret key
3. **Content-Type Validation**: Only accept JSON content

### Best Practices

- Use strong webhook secrets
- Run bot behind firewall
- Monitor logs for suspicious activity
- Use paper trading for testing

## Troubleshooting

### Common Issues

1. **IBKR Connection Failed**
   - Check TWS/Gateway is running
   - Verify API settings enabled
   - Check port numbers match
   - Ensure client ID is unique

2. **Webhook Not Receiving Alerts**
   - Check firewall settings
   - Verify webhook URL is accessible
   - Check TradingView alert configuration
   - Review webhook logs

3. **Orders Not Executing**
   - Check account permissions
   - Verify sufficient buying power
   - Check market hours settings
   - Review trading permissions

4. **Telegram Notifications Not Working**
   - Verify bot token and chat ID
   - Check internet connectivity
   - Test with `/test` command

### Debug Mode

Run with debug logging:
```bash
python main.py --config config.yaml
# Then edit config.yaml to set logging.level: "DEBUG"
```

### Log Analysis

Check logs for detailed information:
```bash
tail -f logs/trading_bot.log
```

## Performance Monitoring

### Order Statistics

The bot tracks:
- Total orders placed
- Fill rate percentage
- Average fill time
- Resubmission rate
- Success/failure rates

### Position Tracking

- Current positions by symbol
- Position history
- P&L tracking (when available)

## Development

### Project Structure

```
ibkr-tradingview-alert-project/
├── main.py                 # Main entry point
├── requirements.txt        # Python dependencies
├── config.yaml            # Configuration template
├── .env.template          # Environment variables template
├── README.md              # This file
├── src/                   # Source code
│   ├── __init__.py
│   ├── trading_bot.py     # Main bot orchestrator
│   ├── config.py          # Configuration management
│   ├── logger.py          # Logging utilities
│   ├── webhook.py         # Webhook server
│   ├── ibkr_client.py     # IBKR API client
│   ├── trading_engine.py  # Trading logic
│   ├── order_manager.py   # Order management
│   ├── telegram_notifier.py # Telegram notifications
│   └── market_hours.py    # Market hours management
└── logs/                  # Log files (created automatically)
```

### Testing

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

## Support

For issues and questions:

1. Check the troubleshooting section
2. Review log files for error details
3. Ensure all configuration is correct
4. Test with paper trading first

## Disclaimer

This software is for educational and informational purposes only. Trading involves risk, and you should carefully consider your investment objectives and risk tolerance before trading. The authors are not responsible for any financial losses incurred through the use of this software.

Always test thoroughly with paper trading before using with real money.

## License

This project is provided as-is for educational purposes. Please ensure compliance with all applicable regulations and broker terms of service.