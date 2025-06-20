import asyncio
import os
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from functools import wraps

import bittensor as bt
from supabase import create_client, Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes, 
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Conversation states
SUBNET_ID, AMOUNT, TOTAL_AMOUNT, FREQUENCY, CUSTOM_HOURS = range(5)

# Authorized users for DCA creation (usernames without @)
AUTHORIZED_CREATORS = {
    'mattslater',
    'fhd1466'
}

def dca_creation_only(func):
    """Decorator to restrict DCA creation commands to authorized users only."""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        username = user.username.lower() if user.username else None
        
        # Check if user is authorized for DCA creation
        if username not in AUTHORIZED_CREATORS:
            await update.message.reply_text(
                "🚫 **DCA Creation Restricted**\n\n"
                "DCA order creation is restricted to authorized users only.\n"
                f"Your username: @{username if username else 'none'}\n\n"
                "You can still use other bot commands like /list, /balance, and /help.\n"
                "If you believe this is an error, please contact the bot administrator.",
                parse_mode='Markdown'
            )
            print(f"🚫 Unauthorized DCA creation attempt from user: @{username if username else 'none'} (ID: {user.id})")
            return ConversationHandler.END if 'ConversationHandler' in str(type(self)) else None
        
        # User is authorized, proceed with the original function
        print(f"✅ Authorized user @{username} (ID: {user.id}) accessing DCA creation: {func.__name__}")
        return await func(self, update, context, *args, **kwargs)
    
    return wrapper

class SimpleDCABot:
    def __init__(self):
        # Initialize execution queue
        self.execution_queue: asyncio.Queue = asyncio.Queue()
        
        # Initialize Supabase client
        self.supabase: Client = create_client(
            os.getenv('SUPABASE_URL'),
            os.getenv('SUPABASE_KEY')
        )
        
        # Initialize Bittensor components
        self.wallet = bt.wallet()
        
        # Load wallet from environment - try mnemonic first, then private key
        wallet_loaded = False
        
        if os.getenv('BT_MNEMONIC'):
            try:
                # Use mnemonic phrase (preferred method for bittensor)
                mnemonic = os.getenv('BT_MNEMONIC').strip()
                print(f"🔑 Loading wallet from mnemonic phrase...")
                self.wallet.regenerate_coldkey(mnemonic=mnemonic, use_password=False, overwrite=True, suppress=True)
                print("✅ Wallet loaded successfully from mnemonic")
                print(f"💰 Wallet address: {self.wallet.coldkey.ss58_address}")
                wallet_loaded = True
            except Exception as e:
                print(f"⚠️ Warning: Could not load wallet from mnemonic: {e}")
                
        if not wallet_loaded and os.getenv('BT_PRIVATE_KEY'):
            try:
                # In bittensor 7.0.0, use regenerate_coldkey with seed parameter
                private_key = os.getenv('BT_PRIVATE_KEY')
                # Remove '0x' prefix if present
                if private_key.startswith('0x'):
                    private_key = private_key[2:]
                
                print(f"🔑 Loading wallet from private key...")
                self.wallet.regenerate_coldkey(seed=private_key, use_password=False, overwrite=True)
                print("✅ Wallet loaded successfully from private key")
                print(f"💰 Wallet address: {self.wallet.coldkey.ss58_address}")
                wallet_loaded = True
            except Exception as e:
                print(f"⚠️ Warning: Could not load private key from environment: {e}")
                
        if not wallet_loaded:
            print("⚠️ Warning: Using default wallet (no mnemonic or private key loaded)")
            print(f"💰 Default wallet address: {self.wallet.coldkey.ss58_address}")
        
        # Initialize subtensor for bittensor 7.0.0 (removed chain_endpoint parameter)
        network = os.getenv('BT_NETWORK', 'finney')
        self.subtensor = bt.subtensor(network=network)
        
        # Initialize Telegram bot
        self.app = Application.builder().token(os.getenv('TG_TOKEN')).build()
        self.setup_handlers()
    
    def setup_handlers(self) -> None:
        """Set up all command handlers for the Telegram bot."""
        # Basic commands
        self.app.add_handler(CommandHandler("start", self.start_cmd))
        self.app.add_handler(CommandHandler("help", self.help_cmd))
        self.app.add_handler(CommandHandler("list", self.list_cmd))
        self.app.add_handler(CommandHandler("cancel", self.cancel_cmd))
        self.app.add_handler(CommandHandler("balance", self.balance_cmd))
        
        # DCA order creation conversation (handles both buy and sell)
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("create", self.create_cmd),
                CommandHandler("sell", self.sell_cmd)
            ],
            states={
                SUBNET_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_subnet_id)],
                AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_amount)],
                TOTAL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_total_amount)],
                FREQUENCY: [CallbackQueryHandler(self.get_frequency)],
                CUSTOM_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_custom_hours)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)]
        )
        self.app.add_handler(conv_handler)
    
    async def start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command - register user."""
        telegram_id = update.effective_user.id
        
        try:
            # Check if user already exists
            result = self.supabase.table('users').select('*').eq('telegram_id', telegram_id).execute()
            
            if not result.data:
                # Register new user
                self.supabase.table('users').insert({
                    'telegram_id': telegram_id
                }).execute()
                
                await update.message.reply_text(
                    "🎉 Welcome to the Bittensor DCA Bot!\n\n"
                    "You've been successfully registered. Here's what you can do:\n\n"
                    "📊 /create - Create a new DCA order\n"
                    "📋 /list - View your active orders\n"
                    "❌ /cancel <id> - Cancel an order\n"
                    "💰 /balance - Check bot wallet balance\n"
                    "❓ /help - Show this help message\n\n"
                    "Start by creating your first DCA order with /create!"
                )
            else:
                await update.message.reply_text(
                    "👋 Welcome back! You're already registered.\n\n"
                    "Use /help to see available commands."
                )
                
        except Exception as e:
            await update.message.reply_text(f"❌ Error registering user: {str(e)}")
    
    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        help_text = """
🤖 **Bittensor DCA Bot Commands**

📊 `/create` - Create a new DCA buy order (stake TAO)
💰 `/sell` - Create a new DCA sell order (unstake alpha tokens)
📋 `/list` - View your active DCA orders with progress  
❌ `/cancel <order_id>` - Cancel a specific order
💰 `/balance` - Check bot wallet balance
❓ `/help` - Show this help message

**How DCA works:**
Dollar Cost Averaging (DCA) automatically executes transactions at regular intervals, helping to reduce the impact of volatility over time.

**Buy Orders (Staking):**
• Purchase and stake TAO to validators
• Converts TAO to alpha tokens
• Helps build your subnet positions

**Sell Orders (Unstaking):**
• Sell alpha tokens back to TAO
• Automatically unstakes from top validators
• Helps you take profits or rebalance

**Order Setup:**
• Choose a subnet to trade in
• Set amount per transaction (e.g., 1 TAO each time)
• Set total budget (e.g., 100 TAO total)
• Choose frequency from comprehensive options
• Order stops automatically when total budget is reached

**Supported frequencies:**
• **Minutes**: 1, 5, 15, 30 minute intervals
• **Hourly**: Any interval from 1-23 hours (2h, 6h, 12h, etc.)
• **Daily**: Every 24 hours
• **Weekly**: Every 7 days

**Popular frequency examples:**
• Every 5 minutes - High frequency trading
• Every 2 hours - Active DCA strategy  
• Every 6 hours - 4 times per day
• Daily - Traditional DCA approach
• Weekly - Long-term accumulation

**Examples:**
• Buy: Stake 1 TAO every 6 hours until you've spent 50 TAO total
• Sell: Unstake 1 Alpha every day until you've unstaked 20 Alpha total
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    @dca_creation_only
    async def create_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start DCA buy order creation conversation."""
        context.user_data['order_type'] = 'buy'
        await update.message.reply_text(
            "🎯 Let's create your DCA buy order!\n\n"
            "This will create a recurring order to buy (stake) TAO.\n\n"
            "First, which subnet would you like to invest in?\n"
            "Enter the subnet ID (e.g., 1 for subnet 1):\n\n"
            "💡 *Tip: Type 'exit' anytime to cancel order creation*"
        )
        return SUBNET_ID
    
    @dca_creation_only
    async def get_subnet_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get subnet ID from user."""
        user_input = update.message.text.strip().lower()
        order_type = context.user_data.get('order_type', 'buy')
        
        # Check if user wants to exit
        if user_input == "exit":
            await update.message.reply_text("❌ Order creation cancelled.")
            context.user_data.clear()
            return ConversationHandler.END
        
        try:
            subnet_id = int(update.message.text.strip())
            if subnet_id < 0:
                await update.message.reply_text("❌ Subnet ID must be a positive number. Please try again:")
                return SUBNET_ID
            
            context.user_data['subnet_id'] = subnet_id
            
            if order_type == 'buy':
                message = (
                    f"✅ Subnet ID: {subnet_id}\n\n"
                    "💰 How much TAO would you like to invest per execution?\n"
                    "Enter the amount (e.g., 0.1, 1.5, 10):\n\n"
                    "💡 *Tip: Type 'exit' to cancel order creation*"
                )
            else:  # sell
                message = (
                    f"✅ Subnet ID: {subnet_id}\n\n"
                    "💰 How many Alpha tokens would you like to unstake per execution?\n"
                    "Enter the amount in Alpha (e.g., 0.1, 1.5, 10):\n\n"
                    "💡 *Note: Alpha tokens represent your staked position*\n"
                    "💡 *Tip: Type 'exit' to cancel order creation*"
                )
            
            await update.message.reply_text(message)
            return AMOUNT
            
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number for subnet ID:")
            return SUBNET_ID
    
    @dca_creation_only
    async def get_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get TAO amount from user."""
        user_input = update.message.text.strip().lower()
        order_type = context.user_data.get('order_type', 'buy')
        
        # Check if user wants to exit
        if user_input == "exit":
            await update.message.reply_text("❌ Order creation cancelled.")
            context.user_data.clear()
            return ConversationHandler.END
        
        try:
            amount = float(update.message.text.strip())
            if amount <= 0:
                await update.message.reply_text("❌ Amount must be greater than 0. Please try again:")
                return AMOUNT
            
            context.user_data['amount'] = amount
            
            if order_type == 'buy':
                message = (
                    f"✅ Amount per buy: {amount} TAO\n\n"
                    "💰 What's your total DCA budget (total amount to spend)?\n"
                    "Enter the total amount (e.g., 10, 50, 100):\n\n"
                    "💡 *Tip: Type 'exit' to cancel order creation*"
                )
            else:  # sell
                message = (
                    f"✅ Amount per unstake: {amount} Alpha\n\n"
                    "💰 What's your total unstaking budget?\n"
                    "Enter the total amount in Alpha (e.g., 10, 50, 100):\n\n"
                    "💡 *Tip: Type 'exit' to cancel order creation*"
                )
            
            await update.message.reply_text(message)
            return TOTAL_AMOUNT
            
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number for the amount:")
            return AMOUNT
    
    @dca_creation_only
    async def get_total_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get total amount from user."""
        user_input = update.message.text.strip().lower()
        order_type = context.user_data.get('order_type', 'buy')
        
        # Check if user wants to exit
        if user_input == "exit":
            await update.message.reply_text("❌ Order creation cancelled.")
            context.user_data.clear()
            return ConversationHandler.END
        
        try:
            total_amount = float(update.message.text.strip())
            if total_amount <= 0:
                await update.message.reply_text("❌ Total amount must be greater than 0. Please try again:")
                return TOTAL_AMOUNT
            
            context.user_data['total_amount'] = total_amount
            
            # Create comprehensive frequency selection keyboard
            prefix = f"{order_type}_" if order_type == 'sell' else ""
            keyboard = [
                # Minute intervals
                [
                    InlineKeyboardButton("⚡ 1 min", callback_data=f"{prefix}1"),
                    InlineKeyboardButton("⏱️ 5 min", callback_data=f"{prefix}5"),
                    InlineKeyboardButton("⏰ 15 min", callback_data=f"{prefix}15"),
                    InlineKeyboardButton("🕐 30 min", callback_data=f"{prefix}30")
                ],
                # Hourly option
                [
                    InlineKeyboardButton("🕒 Hourly (1-23h)", callback_data=f"{prefix}hourly")
                ],
                # Daily and Weekly
                [
                    InlineKeyboardButton("📅 Daily", callback_data=f"{prefix}1440"),
                    InlineKeyboardButton("📊 Weekly", callback_data=f"{prefix}10080")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if order_type == 'buy':
                message = (
                    f"✅ Total Amount: {total_amount} TAO\n\n"
                    "⏰ How often would you like to execute this DCA order?\n\n"
                )
            else:  # sell
                message = (
                    f"✅ Total Unstaking Budget: {total_amount} Alpha\n\n"
                    "⏰ How often would you like to execute this DCA sell order?\n\n"
                )
            
            message += (
                "**Quick Options:**\n"
                "• **Minutes**: 1, 5, 15, 30 minute intervals\n"
                "• **Hourly**: Any interval from 1-23 hours\n" 
                "• **Daily**: Every 24 hours\n"
                "• **Weekly**: Every 7 days\n\n"
                "Choose your preferred frequency:"
            )
            
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
            return FREQUENCY
            
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number for the total amount:")
            return TOTAL_AMOUNT
    
    @dca_creation_only
    async def get_frequency(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get frequency from user and create the DCA order or ask for custom hours."""
        query = update.callback_query
        await query.answer()
        
        order_type = context.user_data.get('order_type', 'buy')
        
        # Handle hourly custom selection
        if query.data in ["hourly", "sell_hourly"]:
            action_text = "sell execution" if order_type == 'sell' else "DCA execution"
            await query.edit_message_text(
                "🕒 **Custom Hourly Frequency**\n\n"
                f"Please enter the number of hours between each {action_text}.\n\n"
                "**Examples:**\n"
                "• `2` = Every 2 hours\n"
                "• `6` = Every 6 hours  \n"
                "• `12` = Every 12 hours\n\n"
                "Enter a number between 1 and 23:",
                parse_mode='Markdown'
            )
            return CUSTOM_HOURS
        
        # Handle direct frequency selection
        frequency_minutes = int(query.data.replace('sell_', ''))
        return await self.create_dca_order(update, context, frequency_minutes)
    
    @dca_creation_only
    async def get_custom_hours(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get custom hourly frequency from user."""
        user_input = update.message.text.strip().lower()
        
        # Check if user wants to exit
        if user_input == "exit":
            await update.message.reply_text("❌ Order creation cancelled.")
            context.user_data.clear()
            return ConversationHandler.END
        
        try:
            hours = int(update.message.text.strip())
            if hours < 1 or hours > 23:
                await update.message.reply_text(
                    "❌ Please enter a number between 1 and 23 hours:\n\n"
                    "💡 *Tip: Type 'exit' to cancel order creation*"
                )
                return CUSTOM_HOURS
                
            # Convert hours to minutes
            frequency_minutes = hours * 60
            return await self.create_dca_order(update, context, frequency_minutes)
            
        except ValueError:
            await update.message.reply_text(
                "❌ Please enter a valid number between 1 and 23:\n\n"
                "💡 *Tip: Type 'exit' to cancel order creation*"
            )
            return CUSTOM_HOURS
    
    async def create_dca_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE, frequency_minutes: int) -> int:
        """Create the DCA order with the specified frequency."""
        # Get frequency text for display
        frequency_text = self.get_frequency_display_text(frequency_minutes)
        
        telegram_id = update.effective_user.id
        subnet_id = context.user_data['subnet_id']
        amount = context.user_data['amount']
        total_amount = context.user_data['total_amount']
        order_type = context.user_data.get('order_type', 'buy')
        
        try:
            # Calculate next run time
            now = datetime.now()
            current_minute = now.replace(second=0, microsecond=0)
            next_run = current_minute + timedelta(minutes=frequency_minutes)
            
            # Insert DCA order into database
            result = self.supabase.table('dca_orders').insert({
                'telegram_id': telegram_id,
                'subnet_id': subnet_id,
                'amount_tao': amount,
                'total_amount_tao': total_amount,
                'total_spent_tao': 0.0,
                'frequency_minutes': frequency_minutes,
                'next_run': next_run.isoformat(),
                'order_type': order_type
            }).execute()
            
            order_id = result.data[0]['id']
            
            # Create success message based on order type
            if order_type == 'buy':
                title = "🎉 **DCA Buy Order Created Successfully!**"
                type_desc = "📈 **Type:** Buy (Stake TAO)"
                amount_desc = f"💰 **Amount:** {amount} TAO per execution"
                budget_desc = f"💰 **Total Budget:** {total_amount} TAO"
            else:  # sell
                title = "🎉 **DCA Sell Order Created Successfully!**"
                type_desc = "📉 **Type:** Sell (Unstake Alpha)"
                amount_desc = f"💰 **Amount:** {amount} Alpha per execution"
                budget_desc = f"💰 **Total Budget:** {total_amount} Alpha"
            
            success_message = (
                f"{title}\n\n"
                f"📊 **Order ID:** {order_id}\n"
                f"🎯 **Subnet:** {subnet_id}\n"
                f"{type_desc}\n"
                f"{amount_desc}\n"
                f"{budget_desc}\n"
                f"⏰ **Frequency:** {frequency_text}\n"
                f"🚀 **Next Execution:** {next_run.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Your DCA order is now active! Use /list to view all your orders."
            )
            
            # Determine if this is a callback query or regular message
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(success_message, parse_mode='Markdown')
            else:
                await update.message.reply_text(success_message, parse_mode='Markdown')
            
        except Exception as e:
            error_msg = f"❌ Error creating DCA order: {str(e)}"
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(error_msg)
            else:
                await update.message.reply_text(error_msg)
        
        # Clear user data
        context.user_data.clear()
        return ConversationHandler.END
    
    def get_frequency_display_text(self, frequency_minutes: int) -> str:
        """Convert frequency in minutes to human-readable text."""
        if frequency_minutes == 1:
            return "Every minute"
        elif frequency_minutes < 60:
            return f"Every {frequency_minutes} minutes"
        elif frequency_minutes == 60:
            return "Every hour"
        elif frequency_minutes < 1440:
            hours = frequency_minutes // 60
            return f"Every {hours} hours"
        elif frequency_minutes == 1440:
            return "Daily (every 24 hours)"
        elif frequency_minutes == 10080:
            return "Weekly (every 7 days)"
        else:
            # Convert to days if it's a large number
            days = frequency_minutes // 1440
            if days == 1:
                return "Daily"
            else:
                return f"Every {days} days"
    
    @dca_creation_only
    async def sell_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start DCA sell order creation conversation."""
        context.user_data['order_type'] = 'sell'
        await update.message.reply_text(
            "📉 Let's create your DCA sell order!\n\n"
            "This will create a recurring order to unstake your Alpha tokens.\n\n"
            "First, which subnet would you like to sell from?\n"
            "Enter the subnet ID (e.g., 1 for subnet 1):\n\n"
            "💡 *Tip: Type 'exit' anytime to cancel order creation*"
        )
        return SUBNET_ID
    
    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation."""
        await update.message.reply_text("❌ Order creation cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
    
    async def list_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /list command - show user's DCA orders."""
        telegram_id = update.effective_user.id
        
        try:
            result = self.supabase.table('dca_orders').select('*').eq(
                'telegram_id', telegram_id
            ).eq('is_active', True).order('created_at', desc=True).execute()
            
            if not result.data:
                await update.message.reply_text("📋 You don't have any active DCA orders yet.\n\nUse /create to create your first order!")
                return
            
            message = "📋 **Your Active DCA Orders:**\n\n"
            
            for order in result.data:
                frequency_minutes = order['frequency_minutes']
                frequency_text = self.get_frequency_display_text(frequency_minutes)
                order_type = order.get('order_type', 'buy')
                
                next_run = datetime.fromisoformat(order['next_run'].replace('Z', '+00:00'))
                
                # Calculate progress
                total_spent = float(order.get('total_spent_tao', 0))
                total_amount = float(order['total_amount_tao'])
                remaining = total_amount - total_spent
                progress_percent = (total_spent / total_amount) * 100
                
                # Create progress bar
                progress_bars = int(progress_percent / 10)  # 10 bars total
                progress_bar = "█" * progress_bars + "░" * (10 - progress_bars)
                
                # Set display text based on order type
                if order_type == 'buy':
                    type_emoji = "📈"
                    type_text = "Buy (Stake)"
                    amount_text = f"💰 **Amount per buy:** {order['amount_tao']} TAO"
                    budget_text = f"💰 **Total budget:** {total_amount} TAO"
                    spent_text = f"💸 **Spent:** {total_spent:.4f} TAO"
                    remaining_text = f"💵 **Remaining:** {remaining:.4f} TAO"
                else:  # sell
                    type_emoji = "📉"
                    type_text = "Sell (Unstake)"
                    amount_text = f"💰 **Amount per sell:** {order['amount_tao']} Alpha"
                    budget_text = f"💰 **Total budget:** {total_amount} Alpha"
                    spent_text = f"💸 **Sold:** {total_spent:.4f} Alpha"
                    remaining_text = f"💵 **Remaining:** {remaining:.4f} Alpha"
                
                message += (
                    f"🆔 **ID:** {order['id']}\n"
                    f"🎯 **Subnet:** {order['subnet_id']}\n"
                    f"{type_emoji} **Type:** {type_text}\n"
                    f"{amount_text}\n"
                    f"{budget_text}\n"
                    f"📊 **Progress:** {progress_bar} {progress_percent:.1f}%\n"
                    f"{spent_text}\n"
                    f"{remaining_text}\n"
                    f"⏰ **Frequency:** {frequency_text}\n"
                    f"🚀 **Next Run:** {next_run.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📅 **Created:** {datetime.fromisoformat(order['created_at'].replace('Z', '+00:00')).strftime('%Y-%m-%d')}\n\n"
                    f"───────────────────\n\n"
                )
            
            message += "Use `/cancel <order_id>` to cancel an order."
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error fetching orders: {str(e)}")
    
    async def cancel_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /cancel command - cancel a specific DCA order."""
        if not context.args:
            await update.message.reply_text("❌ Please provide an order ID.\n\nUsage: `/cancel <order_id>`\n\nUse /list to see your order IDs.", parse_mode='Markdown')
            return
        
        try:
            order_id = int(context.args[0])
            telegram_id = update.effective_user.id
            
            # Check if order exists and belongs to user
            result = self.supabase.table('dca_orders').select('*').eq(
                'id', order_id
            ).eq('telegram_id', telegram_id).eq('is_active', True).execute()
            
            if not result.data:
                await update.message.reply_text(f"❌ Order {order_id} not found or already cancelled.")
                return
            
            # Cancel the order
            self.supabase.table('dca_orders').update({
                'is_active': False
            }).eq('id', order_id).execute()
            
            order = result.data[0]
            await update.message.reply_text(
                f"✅ **Order Cancelled Successfully!**\n\n"
                f"🆔 **Order ID:** {order_id}\n"
                f"🎯 **Subnet:** {order['subnet_id']}\n"
                f"💰 **Amount:** {order['amount_tao']} TAO\n"
                f"💰 **Total Amount:** {order['total_amount_tao']} TAO\n\n"
                f"This order will no longer execute.",
                parse_mode='Markdown'
            )
            
        except ValueError:
            await update.message.reply_text("❌ Please provide a valid order ID number.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error cancelling order: {str(e)}")
    
    async def balance_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /balance command - show bot wallet balance."""
        try:
            # Get wallet balance using coldkey (not hotkey)
            balance = self.subtensor.get_balance(self.wallet.coldkey.ss58_address)
            
            await update.message.reply_text(
                f"💰 **Bot Wallet Balance**\n\n"
                f"🔑 **Coldkey Address:** `{self.wallet.coldkey.ss58_address}`\n"
                f"💎 **Balance:** {balance.tao:.4f} TAO\n\n"
                f"*This is the wallet used to execute your DCA orders.*",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error fetching balance: {str(e)}")
    
    async def schedule_due_orders(self) -> None:
        """Check for orders that need to be executed and add them to the queue."""
        try:
            now = datetime.now()
            
            # Get orders that need to run
            result = self.supabase.table('dca_orders').select('*').filter(
                'next_run', 'lte', now.isoformat()
            ).filter('is_active', 'eq', True).execute()
            
            scheduled_count = 0
            for order in result.data:
                try:
                    # Add order to execution queue
                    await self.execution_queue.put({
                        'order': order,
                        'scheduled_at': now.isoformat()
                    })
                    scheduled_count += 1
                    
                    # Calculate next run time as exact minute boundary to prevent timing issues
                    current_minute = now.replace(second=0, microsecond=0)
                    next_run = current_minute + timedelta(minutes=order['frequency_minutes'])
                    
                    self.supabase.table('dca_orders').update({
                        'next_run': next_run.isoformat()
                    }).eq('id', order['id']).execute()
                    
                    print(f"📅 Scheduled order {order['id']} for execution (next run: {next_run.strftime('%H:%M:%S')})")
                    
                except Exception as e:
                    print(f"❌ Error scheduling order {order['id']}: {e}")
            
            if scheduled_count > 0:
                print(f"✅ Scheduled {scheduled_count} orders at {now.strftime('%H:%M:%S')}")
                    
        except Exception as e:
            print(f"❌ Error in schedule_due_orders: {e}")

    async def queue_executor(self) -> None:
        """Process orders from the execution queue."""
        print("🔄 Starting queue executor...")
        
        while True:
            try:
                # Wait for orders in the queue
                queue_item = await self.execution_queue.get()
                order = queue_item['order']
                scheduled_at = queue_item['scheduled_at']
                
                print(f"🎯 Executing order {order['id']} (scheduled at {scheduled_at})")
                
                # Execute the DCA operation (buy or sell)
                success, error_msg, tx_hash = await self.execute_dca_operation(order)
                
                # Log execution
                self.supabase.table('execution_history').insert({
                    'dca_order_id': order['id'],
                    'amount_tao': order['amount_tao'],
                    'success': success,
                    'error_message': error_msg,
                    'transaction_hash': tx_hash
                }).execute()
                
                if success:
                    print(f"✅ Order {order['id']} executed successfully")
                else:
                    print(f"❌ Order {order['id']} failed: {error_msg}")
                
                # Mark task as done
                self.execution_queue.task_done()
                
            except Exception as e:
                print(f"❌ Error in queue executor: {e}")
                # Still mark task as done to prevent queue from getting stuck
                try:
                    self.execution_queue.task_done()
                except:
                    pass

    async def scheduler_loop(self) -> None:
        """Main scheduler loop - runs every minute to queue due orders."""
        print("🔄 Starting scheduler loop (checking every minute)...")
        
        while True:
            try:
                # Schedule due orders
                await self.schedule_due_orders()
                
                # Calculate the next minute boundary AFTER scheduling work is done
                now = datetime.now()
                next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
                sleep_duration = (next_minute - now).total_seconds()
                
                # Ensure minimum 1-second delay and handle edge cases
                if sleep_duration <= 0:
                    # If we're already past the next minute, go to the following minute
                    next_minute = next_minute + timedelta(minutes=1)
                    sleep_duration = (next_minute - datetime.now()).total_seconds()
                
                # print(f"⏰ Scheduler sleeping {sleep_duration:.1f}s until {next_minute.strftime('%H:%M:%S')}")
                await asyncio.sleep(sleep_duration)
                
            except Exception as e:
                print(f"❌ Error in scheduler loop: {e}")
                # On error, still try to get back on schedule
                now = datetime.now()
                next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
                sleep_duration = (next_minute - now).total_seconds()
                if sleep_duration <= 0:
                    sleep_duration = 60
                await asyncio.sleep(sleep_duration)

    async def execute_dca_operation(self, order: Dict[str, Any]) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Execute a DCA operation (buy or sell) based on the order type.
        
        Returns:
            tuple: (success: bool, error_message: str, transaction_hash: str)
        """
        order_type = order.get('order_type', 'buy')
        
        if order_type == 'buy':
            return await self.execute_buy_operation(order)
        else:  # sell
            return await self.execute_sell_operation(order)
    
    async def execute_buy_operation(self, order: Dict[str, Any]) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Execute a DCA buy operation by staking TAO to the top validator in the subnet.
        
        Returns:
            tuple: (success: bool, error_message: str, transaction_hash: str)
        """
        max_retries = 3
        
        # Check if order has reached its total amount cap
        total_spent = float(order.get('total_spent_tao', 0))
        total_amount = float(order['total_amount_tao'])
        amount_per_buy = float(order['amount_tao'])
        
        if total_spent >= total_amount:
            # Order has reached its cap, deactivate it
            self.supabase.table('dca_orders').update({
                'is_active': False
            }).eq('id', order['id']).execute()
            print(f"Order {order['id']} has reached its total amount cap ({total_amount} TAO). Deactivating.")
            return False, f"Order completed - reached total amount cap of {total_amount} TAO", None
        
        # Check if this purchase would exceed the total amount
        if total_spent + amount_per_buy > total_amount:
            # Adjust the purchase amount to not exceed the cap
            amount_per_buy = total_amount - total_spent
            if amount_per_buy <= 0.0001:  # Minimum practical amount
                self.supabase.table('dca_orders').update({
                    'is_active': False
                }).eq('id', order['id']).execute()
                print(f"Order {order['id']} completed - remaining amount too small ({amount_per_buy:.6f} TAO)")
                return False, f"Order completed - remaining budget too small", None
        
        for attempt in range(max_retries):
            try:
                amount_tao = Decimal(str(amount_per_buy))
                subnet_id = order['subnet_id']
                print(f"Executing DCA purchase: {amount_tao} TAO to subnet {subnet_id} (attempt {attempt + 1}/{max_retries})")
                print(f"Progress: {total_spent:.4f}/{total_amount} TAO spent")
                
                # Use AsyncSubtensor for async operations
                async with bt.AsyncSubtensor(os.getenv('BT_NETWORK', 'finney')) as subtensor:
                    # Get metagraph to fetch validator hotkeys dynamically
                    print(f"Fetching metagraph for subnet {subnet_id}...")
                    metagraph = await subtensor.metagraph(netuid=subnet_id)
                    
                    # Get validators (neurons with validator_permit = True)
                    validators = [uid for uid, neuron in enumerate(metagraph.neurons) if neuron.validator_permit]
                    
                    if not validators:
                        return False, f"No validators found in subnet {subnet_id}", None
                    
                    # Select the top validator by stake
                    top_validator_uid = max(validators, key=lambda uid: metagraph.neurons[uid].stake.tao)
                    validator_hotkey_ss58 = metagraph.neurons[top_validator_uid].hotkey
                    validator_stake = metagraph.neurons[top_validator_uid].stake.tao
                    
                    print(f"Selected top validator UID {top_validator_uid} with hotkey: {validator_hotkey_ss58}")
                    print(f"Validator stake: {validator_stake} TAO")
                    print(f"Staking {amount_tao} TAO to subnet {subnet_id}...")
                    
                    # Execute the stake transaction
                    result = await subtensor.add_stake(
                        wallet=self.wallet,
                        hotkey_ss58=validator_hotkey_ss58,
                        netuid=subnet_id,
                        amount=bt.Balance.from_tao(amount_tao),
                        wait_for_inclusion=True,
                        wait_for_finalization=True
                    )
                    
                    if result is True:
                        print("✅ Stake successful!")
                        
                        # Update total spent amount
                        new_total_spent = total_spent + float(amount_tao)
                        update_data = {'total_spent_tao': new_total_spent}
                        
                        # Check if order is now complete
                        if new_total_spent >= total_amount:
                            update_data['is_active'] = False
                            print(f"Order {order['id']} completed! Total spent: {new_total_spent}/{total_amount} TAO")
                        
                        self.supabase.table('dca_orders').update(update_data).eq('id', order['id']).execute()
                        
                        return True, None, "success"
                    else:
                        print(f"❌ Stake failed - Result: {result}")
                        return False, f"Stake operation failed: {result}", None
                    
            except Exception as e:
                error_msg = f"Staking error: {str(e)}"
                print(f"Attempt {attempt + 1} failed: {error_msg}")
                
                # Retry with delay if not last attempt
                if attempt < max_retries - 1:
                    print(f"Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                else:
                    # All attempts failed - deactivate order in one place
                    self.supabase.table('dca_orders').update({
                        'is_active': False
                    }).eq('id', order['id']).execute()
                    print(f"Order {order['id']} deactivated after all retry attempts failed: {error_msg}")
                    return False, error_msg, None
        
        return False, "All retry attempts failed", None
    
    async def execute_sell_operation(self, order: Dict[str, Any]) -> tuple[bool, Optional[str], Optional[str]]:
        """
        Execute a DCA sell operation by unstaking alpha tokens from the top validator in the subnet.
        
        Returns:
            tuple: (success: bool, error_message: str, transaction_hash: str)
        """
        max_retries = 3
        
        # Check if order has reached its total amount cap
        total_spent = float(order.get('total_spent_tao', 0))
        total_amount = float(order['total_amount_tao'])
        amount_per_sell = float(order['amount_tao'])
        
        if total_spent >= total_amount:
            # Order has reached its cap, deactivate it
            self.supabase.table('dca_orders').update({
                'is_active': False
            }).eq('id', order['id']).execute()
            print(f"Sell order {order['id']} has reached its total amount cap ({total_amount} Alpha). Deactivating.")
            return False, f"Order completed - reached total amount cap of {total_amount} Alpha", None
        
        # Check if this sale would exceed the total amount
        if total_spent + amount_per_sell > total_amount:
            # Adjust the sale amount to not exceed the cap
            amount_per_sell = total_amount - total_spent
            if amount_per_sell <= 0.0001:  # Minimum practical amount
                self.supabase.table('dca_orders').update({
                    'is_active': False
                }).eq('id', order['id']).execute()
                print(f"Sell order {order['id']} completed - remaining amount too small ({amount_per_sell:.6f} Alpha)")
                return False, f"Order completed - remaining budget too small", None
        
        for attempt in range(max_retries):
            try:
                amount_alpha = Decimal(str(amount_per_sell))
                subnet_id = order['subnet_id']
                print(f"Executing DCA sell: {amount_alpha} Alpha from subnet {subnet_id} (attempt {attempt + 1}/{max_retries})")
                print(f"Progress: {total_spent:.4f}/{total_amount} Alpha sold")
                
                # Use AsyncSubtensor for async operations
                async with bt.AsyncSubtensor(os.getenv('BT_NETWORK', 'finney')) as subtensor:
                    # Get metagraph to fetch validator hotkeys dynamically
                    print(f"Fetching metagraph for subnet {subnet_id}...")
                    metagraph = await subtensor.metagraph(netuid=subnet_id)
                    
                    # Get validators with stake from our wallet
                    validators_with_stake = []
                    our_coldkey = self.wallet.coldkey.ss58_address
                    
                    for uid, neuron in enumerate(metagraph.neurons):
                        if neuron.validator_permit:
                            # Check if we have stake with this validator
                            stake_amount = await subtensor.get_stake(
                                coldkey_ss58=our_coldkey,
                                hotkey_ss58=neuron.hotkey,
                                netuid=subnet_id
                            )
                            if stake_amount > 0:
                                validators_with_stake.append((uid, neuron.hotkey, stake_amount))
                    
                    if not validators_with_stake:
                        return False, f"No staked validators found in subnet {subnet_id}", None
                    
                    # Select the validator with the most stake from our wallet
                    top_validator = max(validators_with_stake, key=lambda x: x[2])
                    validator_uid, validator_hotkey_ss58, our_stake = top_validator
                    
                    print(f"Selected validator UID {validator_uid} with hotkey: {validator_hotkey_ss58}")
                    print(f"Our stake with this validator: {our_stake} TAO")
                    
                    # Check if we have enough stake to sell (our_stake is in TAO, amount_alpha is alpha amount we want to unstake)
                    if our_stake < amount_alpha:
                        print(f"Insufficient stake: have {our_stake} TAO, need {amount_alpha} Alpha")
                        return False, f"Insufficient stake: have {our_stake} TAO, need {amount_alpha} Alpha", None
                    
                    print(f"Unstaking {amount_alpha} Alpha from subnet {subnet_id}...")
                    
                    # Execute the unstake transaction
                    result = await subtensor.unstake(
                        wallet=self.wallet,
                        hotkey_ss58=validator_hotkey_ss58,
                        netuid=subnet_id,
                        amount=bt.Balance.from_rao(float(amount_alpha)),
                        wait_for_inclusion=True,
                        wait_for_finalization=True
                    )
                    
                    if result is True:
                        print("✅ Unstake successful!")
                        
                        # Update total spent amount
                        new_total_spent = total_spent + float(amount_alpha)
                        update_data = {'total_spent_tao': new_total_spent}
                        
                        # Check if order is now complete
                        if new_total_spent >= total_amount:
                            update_data['is_active'] = False
                            print(f"Sell order {order['id']} completed! Total sold: {new_total_spent}/{total_amount} Alpha")
                        
                        self.supabase.table('dca_orders').update(update_data).eq('id', order['id']).execute()
                        
                        return True, None, "success"
                    else:
                        print(f"❌ Unstake failed - Result: {result}")
                        return False, f"Unstake operation failed: {result}", None
                    
            except Exception as e:
                error_msg = f"Unstaking error: {str(e)}"
                print(f"Attempt {attempt + 1} failed: {error_msg}")
                
                # Retry with delay if not last attempt
                if attempt < max_retries - 1:
                    print(f"Retrying in 5 seconds...")
                    await asyncio.sleep(5)
                else:
                    # All attempts failed - deactivate order
                    self.supabase.table('dca_orders').update({
                        'is_active': False
                    }).eq('id', order['id']).execute()
                    print(f"Sell order {order['id']} deactivated after all retry attempts failed: {error_msg}")
                    return False, error_msg, None
        
        return False, "All retry attempts failed", None
    
    async def run_forever(self) -> None:
        """Main bot loop - runs Telegram bot, scheduler, and queue executor."""
        print("🚀 Starting Bittensor DCA Bot...")
        
        # Initialize and start Telegram bot
        await self.app.initialize()
        await self.app.start()
        
        print("✅ Telegram bot started")
        print(f"💰 Bot coldkey address: {self.wallet.coldkey.ss58_address}")
        
        # Try to display hotkey address if available (for informational purposes only)
        try:
            hotkey_address = self.wallet.hotkey.ss58_address
            print(f"🔑 Bot hotkey address: {hotkey_address}")
        except Exception as e:
            print(f"🔑 Bot hotkey: Not available in container environment (this is normal)")
        
        # Check if we have a valid wallet
        try:
            balance = self.subtensor.get_balance(self.wallet.coldkey.ss58_address)
            print(f"💎 Bot wallet balance: {balance.tao:.4f} TAO")
        except Exception as e:
            print(f"⚠️ Warning: Could not get wallet balance: {e}")
        
        # Start polling for Telegram updates in background
        await self.app.updater.start_polling()
        
        print("🎯 Starting queue-based DCA system...")
        
        # Start both scheduler and executor concurrently
        scheduler_task = asyncio.create_task(self.scheduler_loop())
        executor_task = asyncio.create_task(self.queue_executor())
        
        try:
            # Run both tasks concurrently
            await asyncio.gather(scheduler_task, executor_task)
        except Exception as e:
            print(f"❌ Fatal error in main loop: {e}")
            # Cancel running tasks
            scheduler_task.cancel()
            executor_task.cancel()
            raise

if __name__ == "__main__":
    # Verify required environment variables
    required_vars = ['SUPABASE_URL', 'SUPABASE_KEY', 'TG_TOKEN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file or environment.")
        exit(1)
    
    # Create and run bot
    try:
        bot = SimpleDCABot()
        asyncio.run(bot.run_forever())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        exit(1)