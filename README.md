# Bittensor DCA Telegram Bot

A simple Telegram bot that enables Dollar Cost Averaging (DCA) for Bittensor TAO investments across different subnets.

## Features

- 🤖 **Telegram Interface**: Easy-to-use bot commands
- 📊 **DCA Orders**: Create automated recurring purchases
- 🎯 **Subnet Support**: Invest in specific Bittensor subnets
- ⏰ **Flexible Scheduling**: Every minute, daily, weekly, or monthly execution
- 💰 **Balance Tracking**: Monitor bot wallet balance
- 📋 **Order Management**: List and cancel active orders
- 🔔 **Notifications**: Get notified of successful/failed executions

## Architecture

- **Single Python Script**: Simple deployment with one main file
- **Supabase Database**: Cloud PostgreSQL for data storage
- **Minute-Level Execution**: Checks for pending orders every minute
- **Telegram Bot API**: User interaction via Telegram

## Prerequisites

1. **Supabase Account**: For database storage
2. **Telegram Bot Token**: Create a bot via @BotFather
3. **Bittensor Wallet**: For executing transactions
4. **Python 3.8+**: Runtime environment

## Setup Instructions

### 1. Clone and Install Dependencies

```bash
git clone <your-repo>
cd tao-dca
pip install -r requirements.txt
```

### 2. Set Up Supabase Database

1. Create a new Supabase project
2. Run the SQL commands from `database_schema.sql` in your Supabase SQL editor
3. Note your Supabase URL and anon key

**For existing users upgrading:** If you already have a database with `frequency_hours`, you need to migrate:

```sql
-- Run these commands in your Supabase SQL editor
ALTER TABLE dca_orders RENAME COLUMN frequency_hours TO frequency_minutes;
UPDATE dca_orders SET frequency_minutes = frequency_minutes * 60;
```

### 3. Create Telegram Bot

1. Message @BotFather on Telegram
2. Use `/newbot` command and follow instructions
3. Save the bot token

### 4. Configure Environment Variables

Copy `env.example` to `.env` and fill in your values:

```bash
cp env.example .env
```

Edit `.env`:

```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
BT_PRIVATE_KEY=your_bittensor_private_key
TG_TOKEN=your_telegram_bot_token
BT_NETWORK=finney
BT_CHAIN_ENDPOINT=wss://entrypoint-finney.opentensor.ai:443
```

### 5. Run the Bot

```bash
python bot.py
```

## Current Status

✅ **FULLY FUNCTIONAL** - The bot is ready for production use with:

- Real Bittensor staking integration
- Complete Telegram bot interface
- Supabase database integration
- Comprehensive error handling

## Bot Commands

| Command        | Description              |
| -------------- | ------------------------ |
| `/start`       | Register with the bot    |
| `/create`      | Create a new DCA order   |
| `/list`        | View your active orders  |
| `/cancel <id>` | Cancel a specific order  |
| `/balance`     | Check bot wallet balance |
| `/help`        | Show help message        |

## Usage Example

1. **Start the bot**: `/start`
2. **Create DCA order**: `/create`
   - Enter subnet ID (e.g., `1`)
   - Enter TAO amount (e.g., `0.5`)
   - Select frequency (Daily/Weekly/Monthly)
3. **Monitor orders**: `/list`
4. **Cancel if needed**: `/cancel 123`

## Database Schema

### Users Table

```sql
users (
    telegram_id: bigint PRIMARY KEY,
    created_at: timestamp DEFAULT now()
)
```

### DCA Orders Table

```sql
dca_orders (
    id: serial PRIMARY KEY,
    telegram_id: bigint REFERENCES users(telegram_id),
    subnet_id: integer NOT NULL,
    amount_tao: decimal(10,4) NOT NULL,
    frequency_minutes: integer NOT NULL,
    next_run: timestamp NOT NULL,
    is_active: boolean DEFAULT true,
    created_at: timestamp DEFAULT now()
)
```

### Execution History Table

```sql
execution_history (
    id: serial PRIMARY KEY,
    dca_order_id: integer REFERENCES dca_orders(id),
    executed_at: timestamp DEFAULT now(),
    amount_tao: decimal(10,4) NOT NULL,
    success: boolean NOT NULL,
    error_message: text,
    transaction_hash: text
)
```

## How It Works

1. **User Registration**: Users start with `/start` command
2. **Order Creation**: Interactive conversation to set up DCA parameters
3. **Execution Loop**: Bot checks every hour for orders due to execute
4. **Transaction Execution**: Performs the actual TAO purchase/stake
5. **Notifications**: Users get notified of execution results
6. **Scheduling**: Next execution time is calculated and stored

## Deployment Options

### Local Development

```bash
python bot.py
```

### Production (systemd service)

Create `/etc/systemd/system/tao-dca-bot.service`:

```ini
[Unit]
Description=Bittensor DCA Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/tao-dca
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10
Environment=PATH=/usr/bin:/usr/local/bin

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable tao-dca-bot
sudo systemctl start tao-dca-bot
```

### Docker (Optional)

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "bot.py"]
```

## Security Considerations

- **Private Keys**: Store securely, never commit to version control
- **Environment Variables**: Use `.env` file or secure environment management
- **Database Access**: Use Supabase RLS (Row Level Security) policies
- **Bot Token**: Keep Telegram bot token secure

## Customization

### Adding New Frequencies

Modify the frequency options in `get_amount()` method:

```python
keyboard = [
    [InlineKeyboardButton("📅 Daily (24h)", callback_data="24")],
    [InlineKeyboardButton("📅 Weekly (168h)", callback_data="168")],
    [InlineKeyboardButton("📅 Monthly (720h)", callback_data="720")],
    [InlineKeyboardButton("📅 Custom", callback_data="custom")]  # Add custom option
]
```

### Implementing Real Transactions

The bot uses **real Bittensor staking transactions** via the standard SDK. The `execute_dca_purchase()` method implements:

```python
def execute_dca_purchase(self, order: Dict[str, Any]) -> tuple[bool, Optional[str], Optional[str]]:
    # Real Bittensor staking implementation
    result = self.subtensor.add_stake(
        wallet=self.wallet,
        hotkey_ss58=target_hotkey,
        amount=bt.Balance.from_tao(float(amount_tao))
    )
```

**⚠️ Important**: This bot performs **real TAO staking transactions**. Always test with small amounts first!

## Troubleshooting

### Common Issues

1. **Bot not responding**: Check Telegram token and network connectivity
2. **Database errors**: Verify Supabase credentials and table setup
3. **Bittensor connection**: Check network and chain endpoint settings
4. **Missing dependencies**: Run `pip install -r requirements.txt`
5. **Insufficient balance**: Ensure wallet has enough TAO for DCA orders

### Logs

The bot prints execution logs to console. For production, consider using proper logging:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## ⚠️ Important Disclaimer

**This bot performs REAL Bittensor staking transactions with real TAO tokens.**

- 🚨 **Real Money**: All transactions use actual TAO from your wallet
- 🧪 **Test First**: Always test with small amounts before running large DCA orders
- 💸 **Risk Warning**: Cryptocurrency investments carry risk of loss
- 🔒 **Security**: Keep your private keys secure and never share them
- 📊 **No Financial Advice**: This is educational software, not financial advice

**Use at your own risk. The developers are not responsible for any financial losses.**

## Disclaimer

This bot is for educational and automation purposes. Always test with small amounts first. Cryptocurrency investments carry risk, and automated trading can lead to losses. Use at your own risk.

## Support

For issues and questions:

- Create an issue in the repository
- Check the troubleshooting section
- Review the logs for error messages
