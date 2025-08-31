#!/usr/bin/env python3
"""
Whale Position Info Bot - Telegram Command Version
- Responds only to "go" command on Telegram
- Shows current positions for multiple whales
- STRICT: Only tracks BTC, ETH, and SOL
- Shows long/short, P&L, and position size
- Multiple whale addresses configurable via environment variables
"""

import asyncio
import json
import requests
from datetime import datetime
import os
import logging
import html

# Install with: pip install python-telegram-bot==13.7
from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# RAILWAY ENVIRONMENT VARIABLES
# Configure multiple whales like:
# WHALE_1_ADDRESS=0x...
# WHALE_1_NAME=Whale Name 1
# WHALE_2_ADDRESS=0x...
# WHALE_2_NAME=Whale Name 2
# etc.

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# Validate configuration
if not TELEGRAM_TOKEN:
    print("❌ ERROR: TELEGRAM_TOKEN environment variable not set!")
    exit(1)

if not TELEGRAM_CHAT_ID:
    print("❌ ERROR: TELEGRAM_CHAT_ID environment variable not set!")
    exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WhaleInfoBot:
    """
    Whale Position Info Bot - Responds to "go" command with position info
    """
    def __init__(self):
        # Load whale configurations from environment variables
        self.whales = self.load_whale_configs()
        
        if not self.whales:
            print("❌ ERROR: No whale configurations found!")
            print("Please set WHALE_1_ADDRESS and WHALE_1_NAME environment variables")
            exit(1)
        
        # WHITELIST - Only these tokens will be shown
        self.WHITELISTED_TOKENS = ['BTC', 'ETH', 'SOL']
        
        # Telegram bot setup
        self.updater = Updater(TELEGRAM_TOKEN, use_context=True)
        self.dispatcher = self.updater.dispatcher
        
        # Add handlers
        self.dispatcher.add_handler(MessageHandler(
            Filters.text & Filters.chat(int(TELEGRAM_CHAT_ID)), 
            self.handle_message
        ))
        
        print("=" * 60)
        print("WHALE POSITION INFO BOT - TELEGRAM COMMAND VERSION")
        print("=" * 60)
        print(f"Tracking {len(self.whales)} whale(s):")
        for whale in self.whales:
            print(f"  • {whale['name']}: {whale['address'][:8]}...{whale['address'][-6:]}")
        print(f"Tokens tracked: BTC, ETH, SOL only")
        print(f"Command: Type 'go' in Telegram to get positions")
        print(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
        print("=" * 60)
    
    def load_whale_configs(self):
        """Load all whale configurations from environment variables"""
        whales = []
        i = 1
        
        while True:
            address_key = f'WHALE_{i}_ADDRESS'
            name_key = f'WHALE_{i}_NAME'
            
            address = os.environ.get(address_key, '')
            name = os.environ.get(name_key, f'Whale {i}')
            
            if not address:
                break
            
            whales.append({
                'address': address,
                'name': name
            })
            i += 1
        
        return whales
    
    def handle_message(self, update: Update, context: CallbackContext):
        """Handle incoming messages"""
        message_text = update.message.text.strip().lower()
        
        if message_text == 'go':
            # Send typing action to show bot is working
            context.bot.send_chat_action(
                chat_id=update.effective_chat.id, 
                action='typing'
            )
            
            # Get and send whale positions
            positions_message = self.get_all_whale_positions()
            
            # Split message if too long (Telegram limit is 4096 characters)
            if len(positions_message) > 4000:
                # Split by whales
                messages = self.split_message(positions_message)
                for msg in messages:
                    update.message.reply_text(
                        msg, 
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
            else:
                update.message.reply_text(
                    positions_message, 
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
    
    def split_message(self, message):
        """Split long message into multiple messages"""
        # Split by double newlines (between whales)
        parts = message.split('\n\n')
        messages = []
        current_msg = ""
        
        for part in parts:
            if len(current_msg) + len(part) + 2 < 4000:
                if current_msg:
                    current_msg += "\n\n"
                current_msg += part
            else:
                if current_msg:
                    messages.append(current_msg)
                current_msg = part
        
        if current_msg:
            messages.append(current_msg)
        
        return messages
    
    def get_asset_price(self, coin):
        """Get current price for an asset"""
        url = "https://api.hyperliquid.xyz/info"
        payload = {"type": "allMids"}
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            if response.status_code == 200:
                prices = response.json()
                price = float(prices.get(coin, 0))
                if price > 0:
                    return price
        except:
            pass
        
        return 0
    
    def get_whale_positions(self, whale_address):
        """Get current positions for a specific whale"""
        try:
            url = "https://api.hyperliquid.xyz/info"
            payload = {"type": "clearinghouseState", "user": whale_address}
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                positions = []
                
                asset_positions = data.get('assetPositions', [])
                for asset_position in asset_positions:
                    position = asset_position.get('position', {})
                    if position:
                        coin = position.get('coin', '')
                        
                        # STRICT FILTER: Only process BTC, ETH, SOL
                        if coin not in self.WHITELISTED_TOKENS:
                            continue
                        
                        size = float(position.get('szi', 0))
                        if size != 0:
                            entry_px = float(position.get('entryPx', 0))
                            mark_px = float(position.get('markPx', entry_px))
                            unrealized_pnl = float(position.get('unrealizedPnl', 0))
                            
                            # Calculate position value
                            position_value = abs(size * mark_px)
                            
                            # Calculate P&L percentage
                            if size > 0:  # Long position
                                pnl_pct = ((mark_px - entry_px) / entry_px) * 100 if entry_px > 0 else 0
                            else:  # Short position
                                pnl_pct = ((entry_px - mark_px) / entry_px) * 100 if entry_px > 0 else 0
                            
                            positions.append({
                                'coin': coin,
                                'side': 'LONG' if size > 0 else 'SHORT',
                                'size': abs(size),
                                'value': position_value,
                                'entry_price': entry_px,
                                'mark_price': mark_px,
                                'pnl_usd': unrealized_pnl,
                                'pnl_pct': pnl_pct
                            })
                
                # Sort positions by value (largest first)
                positions.sort(key=lambda x: x['value'], reverse=True)
                return positions
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting positions for whale: {e}")
            return []
    
    def format_value(self, value):
        """Format value for display"""
        if value >= 1_000_000:
            return f"${value/1_000_000:.2f}M"
        elif value >= 1_000:
            return f"${value/1_000:.0f}K"
        else:
            return f"${value:.0f}"
    
    def format_price(self, price):
        """Format price for display"""
        if price >= 1000:
            return f"${price:,.0f}"
        elif price >= 1:
            return f"${price:,.2f}"
        else:
            return f"${price:.4f}"
    
    def get_pnl_emoji(self, pnl_pct):
        """Get emoji based on P&L percentage"""
        if pnl_pct >= 50:
            return "🚀🚀🚀"
        elif pnl_pct >= 20:
            return "🚀🚀"
        elif pnl_pct >= 10:
            return "🚀"
        elif pnl_pct >= 5:
            return "📈"
        elif pnl_pct > 0:
            return "✅"
        elif pnl_pct == 0:
            return "➖"
        elif pnl_pct > -5:
            return "📉"
        elif pnl_pct > -10:
            return "⚠️"
        elif pnl_pct > -20:
            return "🔻"
        else:
            return "💀"
    
    def get_all_whale_positions(self):
        """Get positions for all tracked whales and format as message"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Header
        message = f"<b>🐋 WHALE POSITIONS REPORT 🐋</b>\n"
        message += f"<code>Generated: {timestamp}</code>\n"
        message += f"<code>{'=' * 40}</code>\n\n"
        
        total_whales_with_positions = 0
        total_positions = 0
        total_value = 0
        
        # Get positions for each whale
        for whale in self.whales:
            positions = self.get_whale_positions(whale['address'])
            
            # Skip whales with no positions
            if not positions:
                continue
            
            total_whales_with_positions += 1
            whale_total_value = sum(p['value'] for p in positions)
            total_value += whale_total_value
            
            # Whale header
            coinglass_url = f"https://www.coinglass.com/hyperliquid/{whale['address']}"
            escaped_name = html.escape(whale['name'])
            
            message += f"<b>📊 <a href='{coinglass_url}'>{escaped_name}</a></b>\n"
            message += f"<code>Address: {whale['address'][:6]}...{whale['address'][-4:]}</code>\n"
            message += f"<code>Total Value: {self.format_value(whale_total_value)}</code>\n"
            message += f"<code>{'-' * 40}</code>\n"
            
            # Position details
            for pos in positions:
                total_positions += 1
                
                # Position line with emoji
                pnl_emoji = self.get_pnl_emoji(pos['pnl_pct'])
                
                # Format position info
                message += f"<b>{pos['coin']} {pos['side']}</b> {pnl_emoji}\n"
                message += f"  Size: {self.format_value(pos['value'])}\n"
                message += f"  Entry: {self.format_price(pos['entry_price'])}\n"
                message += f"  Mark: {self.format_price(pos['mark_price'])}\n"
                
                # P&L line with color coding through emoji
                if pos['pnl_usd'] >= 0:
                    message += f"  P&L: <b>+{self.format_value(abs(pos['pnl_usd']))}</b> "
                    message += f"(<b>+{abs(pos['pnl_pct']):.2f}%</b>)\n"
                else:
                    message += f"  P&L: <b>-{self.format_value(abs(pos['pnl_usd']))}</b> "
                    message += f"(<b>-{abs(pos['pnl_pct']):.2f}%</b>)\n"
                
                message += "\n"
            
            message += "\n"
        
        # Summary footer
        if total_whales_with_positions == 0:
            message += "<i>No active BTC/ETH/SOL positions found</i>\n"
        else:
            message += f"<code>{'=' * 40}</code>\n"
            message += f"<b>📈 SUMMARY</b>\n"
            message += f"Active Whales: {total_whales_with_positions}/{len(self.whales)}\n"
            message += f"Total Positions: {total_positions}\n"
            message += f"Total Value: {self.format_value(total_value)}\n"
        
        return message
    
    def start(self):
        """Start the bot"""
        print("\n✅ Bot started! Waiting for 'go' command in Telegram...")
        print("Press Ctrl+C to stop\n")
        
        # Send startup message
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            startup_msg = (
                "🤖 <b>Whale Position Info Bot Started!</b>\n\n"
                f"Tracking <b>{len(self.whales)}</b> whale(s)\n"
                "Tokens: <b>BTC, ETH, SOL only</b>\n\n"
                "Type <b>go</b> to get current positions"
            )
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": startup_msg,
                "parse_mode": "HTML"
            }
            requests.post(url, data=data)
        except Exception as e:
            logger.error(f"Failed to send startup message: {e}")
        
        # Start the bot
        self.updater.start_polling()
        self.updater.idle()

def main():
    bot = WhaleInfoBot()
    bot.start()

if __name__ == "__main__":
    main()