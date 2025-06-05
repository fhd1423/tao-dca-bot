# Bittensor DCA Telegram Bot

A simple Telegram bot that enables Dollar Cost Averaging (DCA) for Bittensor TAO investments across different subnets.

## Setup Instructions

### 1. Clone and Install Dependencies

```bash
git clone https://github.com/fhd1423/tao-dca-bot.git
cd tao-dca-bot
```

### 2. Configure Environment Variables

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
docker-compose build && docker-compose up
```

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
