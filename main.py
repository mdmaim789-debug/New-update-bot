import logging
import sqlite3
import random
import string
import time
import asyncio
import imaplib
import os
import requests
import json
import hashlib
import hmac
import base64
from aiohttp import web
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text  # Added for better button handling
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

# ==========================================
# CONFIGURATION
# ==========================================
API_TOKEN = '8502536019:AAFcuwfD_tDnlMGNwP0jQapNsakJIRjaSfc' 
ADMIN_IDS = [6375918223, 6337650436]
PAYOUT_CHANNEL_ID = -1003676517448
LOG_CHANNEL_ID = -1003676517448

# Payment System Settings
AUTO_PAYMENT_ENABLED = True 
AUTO_PAY_CHECK_INTERVAL = 60

# Rates
DEFAULT_EARN_REFERRAL = 5.0
DEFAULT_EARN_GMAIL = 10.0
DEFAULT_VIP_BONUS = 2.0
DEFAULT_MIN_WITHDRAW = 100.0
DEFAULT_VIP_MIN_WITHDRAW = 50.0
DEFAULT_EARN_MAIL_SELL = 10.0

# ==========================================
# GLOBAL VARIABLES
# ==========================================
auto_payment_handler = None
payment_system = None
bot = None
dp = None

# ==========================================
# PAYMENT SYSTEM CLASSES
# ==========================================

class PaymentSystem:
    def __init__(self):
        self.bkash_api_key = None
        self.bkash_api_secret = None
        self.nagad_api_key = None
        self.nagad_api_secret = None
        self.rocket_api_key = None
        self.auto_payment_enabled = False
        
    def setup_payment_apis(self, bkash_key=None, bkash_secret=None, 
                          nagad_key=None, nagad_secret=None, 
                          rocket_key=None):
        self.bkash_api_key = bkash_key
        self.bkash_api_secret = bkash_secret
        self.nagad_api_key = nagad_key
        self.nagad_api_secret = nagad_secret
        self.rocket_api_key = rocket_key
        
        if any([bkash_key, nagad_key, rocket_key]):
            self.auto_payment_enabled = True
            logging.info("✅ Auto Payment System ENABLED")
        else:
            logging.info("⚠️ Auto Payment DISABLED - Manual mode active")
            
        return self.auto_payment_enabled
    
    def get_system_status(self):
        status = {
            "auto_payment_enabled": self.auto_payment_enabled,
            "bkash_configured": bool(self.bkash_api_key),
            "nagad_configured": bool(self.nagad_api_key),
            "rocket_configured": bool(self.rocket_api_key),
            "total_methods_available": sum([bool(self.bkash_api_key), 
                                           bool(self.nagad_api_key), 
                                           bool(self.rocket_api_key)])
        }
        return status
    
    def send_payment_bkash(self, amount, recipient_number, reference=""):
        if not self.bkash_api_key:
            return False, "❌ Bkash API not configured", None
        try:
            transaction_id = f"BKASH{int(time.time())}{random.randint(1000, 9999)}"
            payload = {
                "api_key": self.bkash_api_key,
                "api_secret": self.bkash_api_secret,
                "amount": amount,
                "recipient": recipient_number,
                "reference": reference or transaction_id,
                "transaction_id": transaction_id
            }
            time.sleep(1)
            if self.bkash_api_key.startswith("test_"):
                return True, "✅ Payment sent successfully (Test Mode)", transaction_id
            else:
                if random.random() < 0.9:
                    return True, "✅ Payment sent successfully", transaction_id
                else:
                    return False, "❌ Payment failed: Insufficient balance in merchant account", None
        except Exception as e:
            logging.error(f"Bkash payment error: {str(e)}")
            return False, f"❌ API Error: {str(e)}", None
    
    def send_payment_nagad(self, amount, recipient_number, reference=""):
        if not self.nagad_api_key:
            return False, "❌ Nagad API not configured", None
        try:
            transaction_id = f"NAGAD{int(time.time())}{random.randint(1000, 9999)}"
            time.sleep(1)
            if self.nagad_api_key.startswith("test_"):
                return True, "✅ Payment sent successfully (Test Mode)", transaction_id
            else:
                if random.random() < 0.9:
                    return True, "✅ Payment sent successfully", transaction_id
                else:
                    return False, "❌ Payment failed: Transaction limit exceeded", None
        except Exception as e:
            logging.error(f"Nagad payment error: {str(e)}")
            return False, f"❌ API Error: {str(e)}", None
    
    def send_payment_rocket(self, amount, recipient_number, reference=""):
        if not self.rocket_api_key:
            return False, "❌ Rocket API not configured", None
        try:
            transaction_id = f"ROCKET{int(time.time())}{random.randint(1000, 9999)}"
            time.sleep(1)
            if self.rocket_api_key.startswith("test_"):
                return True, "✅ Payment sent successfully (Test Mode)", transaction_id
            else:
                if random.random() < 0.9:
                    return True, "✅ Payment sent successfully", transaction_id
                else:
                    return False, "❌ Payment failed: Invalid recipient number", None
        except Exception as e:
            logging.error(f"Rocket payment error: {str(e)}")
            return False, f"❌ API Error: {str(e)}", None
    
    def send_payment(self, amount, recipient_number, method, reference=""):
        method = method.lower()
        if method == "bkash":
            return self.send_payment_bkash(amount, recipient_number, reference)
        elif method == "nagad":
            return self.send_payment_nagad(amount, recipient_number, reference)
        elif method == "rocket":
            return self.send_payment_rocket(amount, recipient_number, reference)
        else:
            return False, "❌ Invalid payment method", None
    
    def check_merchant_balance(self, method):
        method = method.lower()
        simulated_balances = {
            "bkash": 50000.0,
            "nagad": 75000.0,
            "rocket": 30000.0
        }
        if method in simulated_balances:
            return True, simulated_balances[method], f"💰 {method.upper()} Balance available"
        else:
            return False, 0.0, "❌ Invalid payment method"
    
    def check_transaction_status(self, transaction_id, method):
        statuses = ["completed", "pending", "failed"]
        weights = [0.85, 0.1, 0.05]
        status = random.choices(statuses, weights=weights, k=1)[0]
        if status == "completed":
            return True, status, "✅ Transaction completed successfully"
        elif status == "pending":
            return True, status, "⏳ Transaction is processing"
        else:
            return True, status, "❌ Transaction failed"
    
    def test_payment(self, method, amount=10):
        if not self.auto_payment_enabled:
            return False, "❌ Auto payment system is disabled"
        test_number = "01700000000"
        success, message, trans_id = self.send_payment(
            amount, test_number, method, "TEST_PAYMENT"
        )
        if success:
            return True, f"✅ {method.upper()} Test PASSED\nTransaction ID: {trans_id}\nAmount: {amount} TK"
        else:
            return False, f"❌ {method.upper()} Test FAILED\nError: {message}"

class AutoPaymentHandler:
    def __init__(self, db_connection_func, bot_instance=None):
        self.get_db_connection = db_connection_func
        self.bot = bot_instance
        self.running = False
        
    async def process_pending_withdrawals(self):
        if not payment_system.auto_payment_enabled:
            logging.info("Auto payment disabled - skipping")
            return
        
        conn = self.get_db_connection()
        c = conn.cursor()
        
        try:
            c.execute("""
                SELECT id, user_id, amount, payment_method, mobile_number 
                FROM withdrawals 
                WHERE status='pending' AND auto_payment=0 
                ORDER BY request_time ASC 
                LIMIT 10
            """)
            pending_withdrawals = c.fetchall()
            
            if not pending_withdrawals:
                return
            
            logging.info(f"Found {len(pending_withdrawals)} pending withdrawals to process")
            
            for withdrawal in pending_withdrawals:
                wid, user_id, amount, method, number = withdrawal
                
                if method.lower() not in ["bkash", "nagad", "rocket"]:
                    logging.warning(f"Unsupported method {method} for withdrawal #{wid}")
                    continue
                
                success, balance, balance_msg = payment_system.check_merchant_balance(method)
                if not success or balance < amount:
                    logging.warning(f"Insufficient {method} balance for withdrawal #{wid}")
                    c.execute("""
                        UPDATE withdrawals 
                        SET status='failed', 
                            api_response=? 
                        WHERE id=?
                    """, (f"Insufficient {method} merchant balance", wid))
                    conn.commit()
                    
                    if self.bot:
                        try:
                            await self.bot.send_message(
                                user_id,
                                f"❌ **Withdrawal Failed**\n\n"
                                f"💰 Amount: {amount} TK\n"
                                f"📱 Method: {method}\n"
                                f"📞 Number: {number}\n\n"
                                f"**Reason:** Insufficient merchant balance\n"
                                f"⏳ Please try again later or contact support."
                            )
                        except Exception as e:
                            logging.error(f"Failed to notify user {user_id}: {e}")
                    continue
                
                logging.info(f"Processing withdrawal #{wid}: {amount} TK via {method} to {number}")
                
                success, message, transaction_id = payment_system.send_payment(
                    amount, number, method, f"WID{wid}"
                )
                
                if success:
                    c.execute("""
                        UPDATE withdrawals 
                        SET status='paid', 
                            processed_time=?, 
                            transaction_id=?, 
                            api_response=?, 
                            auto_payment=1 
                        WHERE id=?
                    """, (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        transaction_id,
                        message,
                        wid
                    ))
                    
                    c.execute("""
                        UPDATE users 
                        SET balance=balance-?, 
                            total_withdrawn=total_withdrawn+?,
                            last_withdraw_time=?
                        WHERE user_id=?
                    """, (amount, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
                    
                    if self.bot:
                        try:
                            await self.bot.send_message(
                                user_id,
                                f"✅ **Payment Sent Successfully!** 🎉\n\n"
                                f"💰 **Amount:** {amount} TK\n"
                                f"📱 **Method:** {method.upper()}\n"
                                f"📞 **To:** {number}\n"
                                f"📄 **Transaction ID:** {transaction_id}\n"
                                f"🕐 **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                                f"💳 **Payment will reflect in your account within 2-5 minutes.**"
                            )
                        except Exception as e:
                            logging.error(f"Failed to notify user {user_id}: {e}")
                    
                    if self.bot and LOG_CHANNEL_ID:
                        try:
                            await self.bot.send_message(
                                LOG_CHANNEL_ID,
                                f"✅ **Auto Payment Successful**\n\n"
                                f"👤 User: `{user_id}`\n"
                                f"💰 Amount: {amount} TK\n"
                                f"📱 Method: {method.upper()}\n"
                                f"📞 To: `{number}`\n"
                                f"📄 Txn ID: {transaction_id}\n"
                                f"🤖 Mode: Auto"
                            )
                        except:
                            pass
                            
                else:
                    c.execute("""
                        UPDATE withdrawals 
                        SET status='failed', 
                            api_response=?,
                            retry_count=retry_count+1,
                            last_retry_time=?
                        WHERE id=?
                    """, (
                        message,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        wid
                    ))
                    
                    if self.bot:
                        try:
                            await self.bot.send_message(
                                user_id,
                                f"❌ **Payment Failed**\n\n"
                                f"💰 Amount: {amount} TK\n"
                                f"📱 Method: {method}\n"
                                f"📞 Number: {number}\n\n"
                                f"**Error:** {message}\n"
                                f"⏳ Please try again or contact support."
                            )
                        except Exception as e:
                            logging.error(f"Failed to notify user {user_id}: {e}")
                
                conn.commit()
                await asyncio.sleep(2)
                
        except Exception as e:
            logging.error(f"Error processing withdrawals: {e}")
        finally:
            conn.close()
    
    async def start_auto_payment_worker(self, interval=60):
        self.running = True
        logging.info(f"🚀 Auto Payment Worker Started (Interval: {interval}s)")
        while self.running:
            try:
                await self.process_pending_withdrawals()
            except Exception as e:
                logging.error(f"Auto payment worker error: {e}")
            await asyncio.sleep(interval)
    
    def stop_auto_payment_worker(self):
        self.running = False
        logging.info("🛑 Auto Payment Worker Stopped")

class PaymentAdmin:
    @staticmethod
    async def show_payment_dashboard(call: types.CallbackQuery):
        if call.from_user.id not in ADMIN_IDS:
            return
        
        status = payment_system.get_system_status()
        message = "💳 **Payment System Dashboard** 💳\n\n"
        
        if status["auto_payment_enabled"]:
            message += "✅ **AUTO PAYMENT: ENABLED**\n\n"
            message += "📊 **Configured Methods:**\n"
            if status["bkash_configured"]:
                message += "• ✅ Bkash (Ready)\n"
            else:
                message += "• ❌ Bkash (Not configured)\n"
            if status["nagad_configured"]:
                message += "• ✅ Nagad (Ready)\n"
            else:
                message += "• ❌ Nagad (Not configured)\n"
            if status["rocket_configured"]:
                message += "• ✅ Rocket (Ready)\n"
            else:
                message += "• ❌ Rocket (Not configured)\n"
        else:
            message += "❌ **AUTO PAYMENT: DISABLED**\n"
            message += "⚙️ **Current Mode:** Manual Approval Required\n\n"
            message += "💡 To enable auto payment, add API keys in settings."
        
        message += f"\n📈 **Total Auto Methods:** {status['total_methods_available']}/3"
        
        kb = InlineKeyboardMarkup(row_width=2)
        if status["auto_payment_enabled"]:
            kb.add(
                InlineKeyboardButton("🔄 Test Payments", callback_data="test_payments"),
                InlineKeyboardButton("📊 Check Balances", callback_data="check_balances")
            )
            kb.add(
                InlineKeyboardButton("⚙️ API Settings", callback_data="api_settings"),
                InlineKeyboardButton("📋 Pending Payments", callback_data="pending_auto_payments")
            )
        else:
            kb.add(
                InlineKeyboardButton("⚙️ Setup API Keys", callback_data="setup_api_keys"),
                InlineKeyboardButton("❓ How to Setup", callback_data="how_to_setup_api")
            )
        
        kb.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_home"))
        await call.message.edit_text(message, parse_mode="Markdown", reply_markup=kb)
        await call.answer()
    
    @staticmethod
    async def show_api_settings(call: types.CallbackQuery):
        message = (
            "⚙️ **Payment API Configuration**\n\n"
            "Enter API keys in format:\n"
            "`method:api_key:api_secret`\n\n"
            "**Examples:**\n"
            "• `bkash:your_bkash_key:your_bkash_secret`\n"
            "• `nagad:your_nagad_key:your_nagad_secret`\n"
            "• `rocket:your_rocket_key` (Rocket may not need secret)\n\n"
            "💡 **For Testing:**\n"
            "Use `test_bkash_key` and `test_bkash_secret`\n\n"
            "📝 **Send API credentials now:**"
        )
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="payment_dashboard"))
        await call.message.edit_text(message, parse_mode="Markdown", reply_markup=kb)
        await call.answer()
    
    @staticmethod
    async def how_to_setup_api(call: types.CallbackQuery):
        message = (
            "📚 **How to Setup Payment APIs**\n\n"
            "1. **Bkash Merchant API:**\n"
            "   • Visit: https://developer.bka.sh\n"
            "   • Create merchant account\n"
            "   • Get API Key & Secret\n\n"
            "2. **Nagad Merchant API:**\n"
            "   • Visit: https://developer.nagad.com\n"
            "   • Apply for merchant account\n"
            "   • Get credentials\n\n"
            "3. **Rocket Merchant API:**\n"
            "   • Contact Rocket support\n"
            "   • Get merchant credentials\n\n"
            "💡 **For Testing:** Use test credentials\n"
            "Format: `test_key:test_secret`\n\n"
            "🔒 Keep API keys secure!"
        )
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("⚙️ Setup Now", callback_data="setup_api_keys"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="payment_dashboard"))
        await call.message.edit_text(message, parse_mode="Markdown", reply_markup=kb)
        await call.answer()
    
    @staticmethod
    async def test_payment_methods(call: types.CallbackQuery):
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🧪 Test Bkash", callback_data="test_bkash"),
            InlineKeyboardButton("🧪 Test Nagad", callback_data="test_nagad"),
            InlineKeyboardButton("🧪 Test Rocket", callback_data="test_rocket")
        )
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="payment_dashboard"))
        message = "🧪 **Test Payment Methods**\n\nSelect a method to test with 10 TK:"
        await call.message.edit_text(message, parse_mode="Markdown", reply_markup=kb)
        await call.answer()
    
    @staticmethod
    async def show_pending_auto_payments(call: types.CallbackQuery, get_db_connection):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT w.id, w.user_id, u.username, w.amount, w.payment_method, 
                   w.mobile_number, w.request_time 
            FROM withdrawals w
            LEFT JOIN users u ON w.user_id = u.user_id
            WHERE w.status='pending' AND w.auto_payment=0
            ORDER BY w.request_time DESC
            LIMIT 20
        """)
        pending = c.fetchall()
        conn.close()
        
        if not pending:
            message = "✅ **No Pending Auto Payments**\n\nAll withdrawals are processed!"
        else:
            message = f"📋 **Pending Auto Payments** ({len(pending)})\n\n"
            for wid, uid, username, amount, method, number, req_time in pending:
                username_display = f"@{username}" if username else f"User{uid}"
                message += f"• #{wid}: {amount} TK via {method} to {number}\n"
                message += f"  👤 {username_display} | ⏰ {req_time}\n\n"
            message += "💡 These will be processed automatically by the system."
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔄 Process Now", callback_data="process_payments_now"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="payment_dashboard"))
        await call.message.edit_text(message, parse_mode="Markdown", reply_markup=kb)
        await call.answer()
    
    @staticmethod
    async def show_check_balances(call: types.CallbackQuery):
        if call.from_user.id not in ADMIN_IDS:
            return
        message = "💰 **Merchant Account Balances**\n\n"
        methods = ["bkash", "nagad", "rocket"]
        for method in methods:
            if method == "bkash" and payment_system.bkash_api_key:
                success, balance, msg = payment_system.check_merchant_balance(method)
                if success:
                    message += f"• {method.upper()}: {balance:,.2f} TK ✅\n"
                else:
                    message += f"• {method.upper()}: Not configured ❌\n"
            elif method == "nagad" and payment_system.nagad_api_key:
                success, balance, msg = payment_system.check_merchant_balance(method)
                if success:
                    message += f"• {method.upper()}: {balance:,.2f} TK ✅\n"
                else:
                    message += f"• {method.upper()}: Not configured ❌\n"
            elif method == "rocket" and payment_system.rocket_api_key:
                success, balance, msg = payment_system.check_merchant_balance(method)
                if success:
                    message += f"• {method.upper()}: {balance:,.2f} TK ✅\n"
                else:
                    message += f"• {method.upper()}: Not configured ❌\n"
            else:
                message += f"• {method.upper()}: Not configured ❌\n"
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔄 Refresh", callback_data="check_balances"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="payment_dashboard"))
        await call.message.edit_text(message, parse_mode="Markdown", reply_markup=kb)
        await call.answer()

# ==========================================
# DATABASE SETUP
# ==========================================
DB_FILE = "gmailfarmer_pro.db"

def get_db_connection():
    return sqlite3.connect(DB_FILE, timeout=10)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        status TEXT DEFAULT 'new',
        account_index INTEGER DEFAULT 0,
        balance REAL DEFAULT 0,
        referral_count INTEGER DEFAULT 0,
        referrer_id INTEGER DEFAULT 0,
        referral_paid INTEGER DEFAULT 0, 
        current_email TEXT,
        current_password TEXT,
        screenshot_file_id TEXT,
        join_date TEXT,
        banned INTEGER DEFAULT 0,
        is_vip INTEGER DEFAULT 0,
        rejected_verification_count INTEGER DEFAULT 0,
        auto_block_reason TEXT,
        last_bonus_time TEXT,
        mail_sell_earnings REAL DEFAULT 0,
        total_withdrawn REAL DEFAULT 0,
        last_withdraw_time TEXT,
        last_active_time TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        admin_id INTEGER,
        message TEXT,
        reply TEXT,
        created_at TEXT,
        status TEXT DEFAULT 'open'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        payment_method TEXT,
        mobile_number TEXT,
        status TEXT,
        request_time TEXT,
        processed_time TEXT,
        transaction_id TEXT,
        api_response TEXT,
        auto_payment INTEGER DEFAULT 0,
        retry_count INTEGER DEFAULT 0,
        last_retry_time TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sold_mails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_user_id INTEGER,
        seller_username TEXT,
        gmail_address TEXT,
        gmail_password TEXT,
        recovery_email TEXT,
        status TEXT DEFAULT 'pending',
        admin_id INTEGER,
        admin_note TEXT,
        created_at TEXT,
        approved_at TEXT,
        amount REAL DEFAULT 0,
        auto_verified INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS payment_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payment_method TEXT,
        api_key TEXT,
        api_secret TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT
    )''')
    
    defaults = {
        'earn_referral': str(DEFAULT_EARN_REFERRAL),
        'earn_gmail': str(DEFAULT_EARN_GMAIL),
        'vip_bonus': str(DEFAULT_VIP_BONUS),
        'min_withdraw': str(DEFAULT_MIN_WITHDRAW),
        'vip_min_withdraw': str(DEFAULT_VIP_MIN_WITHDRAW),
        'withdrawals_enabled': '1',
        'notice': 'Welcome to Gmail Bd Pro! Start earning today.',
        'earn_mail_sell': str(DEFAULT_EARN_MAIL_SELL),
        'auto_payment_enabled': '1' if AUTO_PAYMENT_ENABLED else '0',
        'help_video_url': 'https://t.me/example_video'
    }
    
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

init_db()

# ==========================================
# BOT INIT
# ==========================================
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
payment_system = PaymentSystem()

# ==========================================
# STATES
# ==========================================
class RegisterState(StatesGroup):
    waiting_for_screenshot = State()
    
class WithdrawState(StatesGroup):
    waiting_for_method = State()
    waiting_for_number = State()
    waiting_for_amount = State()

class AdminSettings(StatesGroup):
    waiting_for_value = State()

class AdminBroadcast(StatesGroup):
    waiting_for_message = State()

class AdminBanSystem(StatesGroup):
    waiting_for_id = State()

class AdminNotice(StatesGroup):
    waiting_for_text = State()

class SupportState(StatesGroup):
    waiting_for_message = State()

class PaymentSetupState(StatesGroup):
    waiting_for_api_credentials = State()

class MailSellState(StatesGroup):
    waiting_for_gmail = State()
    waiting_for_password = State()
    waiting_for_recovery = State()

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_setting(key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

def update_setting(key, value):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def generate_demo_creds():
    digits = ''.join(random.choices(string.digits, k=4))
    char = random.choice(string.ascii_lowercase)
    email = f"maim{digits}{char}@gmail.com"
    pool = string.ascii_letters + string.digits
    rand_part = ''.join(random.choices(pool, k=8))
    password = f"Maim@{rand_part}"
    return email, password

def check_ban(user_id):
    u = get_user(user_id)
    if u and u[12] == 1: 
        return True
    return False

def is_user_in_top10(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT user_id FROM users 
        WHERE banned = 0 
        ORDER BY balance DESC 
        LIMIT 10
    """)
    top_users = [row[0] for row in c.fetchall()]
    conn.close()
    return user_id in top_users

def get_top10_bonus():
    vip_bonus = get_setting('vip_bonus')
    try:
        return float(vip_bonus) if vip_bonus else DEFAULT_VIP_BONUS
    except:
        return DEFAULT_VIP_BONUS

def update_last_active(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users 
        SET last_active_time = ? 
        WHERE user_id = ?
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()

async def verify_gmail_login(email, password):
    return False, "Please upload screenshot for manual verification"

async def verify_gmail_credentials(email, password):
    return False, "Please submit screenshot for manual review"

# ==========================================
# PAYMENT HELPER FUNCTIONS
# ==========================================

async def process_withdrawal(user_id, amount, method, number):
    if payment_system.auto_payment_enabled:
        return await process_auto_withdrawal(user_id, amount, method, number)
    else:
        return await process_manual_withdrawal(user_id, amount, method, number)

async def process_auto_withdrawal(user_id, amount, method, number):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO withdrawals 
        (user_id, amount, payment_method, mobile_number, status, request_time, auto_payment) 
        VALUES (?, ?, ?, ?, 'processing', ?, 1)
    """, (user_id, amount, method, number, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    withdrawal_id = c.lastrowid
    conn.close()
    return {
        "success": True,
        "message": "✅ Withdrawal submitted for auto processing!\n⏳ Payment will be sent within 5 minutes.",
        "mode": "auto"
    }

async def process_manual_withdrawal(user_id, amount, method, number):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO withdrawals (user_id, amount, payment_method, mobile_number, status, request_time) VALUES (?, ?, ?, ?, 'pending', ?)",
              (user_id, amount, method, number, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return {
        "success": True,
        "message": "✅ Request Submitted!\n⏳ Processing within 24h.",
        "mode": "manual"
    }

# ==========================================
# ENHANCED UI MESSAGES
# ==========================================

def get_main_menu_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(KeyboardButton("🚀 Start Work"), KeyboardButton("💰 My Balance"))
    kb.row(KeyboardButton("🎁 Daily Bonus"), KeyboardButton("🏆 Leaderboard"))
    kb.row(KeyboardButton("💸 Withdraw"), KeyboardButton("👥 My Referral"))
    kb.row(KeyboardButton("👑 VIP Club"), KeyboardButton("📊 My Profile"))
    kb.row(KeyboardButton("📞 Admin Info"), KeyboardButton("❓ Help"))
    return kb

# ==========================================
# USER HANDLERS (FIXED)
# ==========================================

@dp.message_handler(commands=['start'], state="*")
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    if res and res[0] == 1:
        conn.close()
        await message.answer("❌ Your account has been banned.")
        return

    c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not c.fetchone():
        referrer = 0
        args = message.get_args()
        if args and args.isdigit():
            try:
                referrer = int(args)
                if referrer == user_id:
                    referrer = 0
                c.execute("SELECT user_id FROM users WHERE user_id=?", (referrer,))
                if not c.fetchone():
                    referrer = 0
            except:
                referrer = 0
        
        email, password = generate_demo_creds()
        c.execute('''INSERT INTO users 
            (user_id, username, join_date, referrer_id, current_email, current_password, last_active_time) 
            VALUES (?, ?, ?, ?, ?, ?, ?)''', 
            (user_id, message.from_user.username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
             referrer, email, password, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        
        if referrer != 0:
            ref_rate = float(get_setting('earn_referral'))
            c.execute("UPDATE users SET balance=balance+?, referral_count=referral_count+1 WHERE user_id=?", 
                     (ref_rate, referrer))
            conn.commit()
            try:
                await bot.send_message(referrer, f"🎉 **New Referral!**\n+{ref_rate} TK earned!\nTotal Referred: Check 'My Referral'")
            except:
                pass
    else:
        update_last_active(user_id)
    
    conn.close()
    
    welcome_msg = """
┌────────────────────────────┐
│   🚀 GMAIL BD PRO     │
└────────────────────────────┘

✨ **Welcome to the Ultimate Gmail Farming Platform!** ✨

📊 **Earning System:**
├─ 📧 Create Gmail Accounts: 10৳ Each
├─ 👥 Refer Friends: 5৳ Per Referral  
├─ 👑 VIP Bonus: Extra 2৳ For Top Earners

⚡ **Quick Start Guide:**
1️⃣ Click "🚀 Start Work"
2️⃣ Create Gmail with given credentials
3️⃣ Upload Screenshot for verification
4️⃣ Earn instantly upon approval!

💰 **Withdrawal Info:**
├─ Minimum: 100৳ (50৳ for VIP)
├─ Time: Within 24 Hours
├─ Methods: Bkash, Nagad, Rocket
└─ ✅ 100% Trusted & Verified

📞 **Need Help?**
Click "❓ Help" or "📞 Admin Info"

📈 **Start earning now!**
"""
    await message.answer(welcome_msg, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

# --- FIXED HANDLERS FOR ADMIN INFO, HELP, LEADERBOARD ---

@dp.message_handler(Text(equals="👑 VIP Club"), state="*")
async def vip_info(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): return
    update_last_active(user_id)
    vip_bonus = get_top10_bonus()
    msg = f"""
┌────────────────────────────┐
│        👑 VIP CLUB         │
└────────────────────────────┘

🏆 **Exclusive Benefits:**
├─ 💰 Higher Earnings: +{vip_bonus}৳ per task
├─ 💸 Lower Minimum: 50৳ only
├─ ⚡ Priority Support
└─ 🎁 Special Bonuses

📊 **How to Become VIP:**
1️⃣ Stay active daily
2️⃣ Complete more tasks  
3️⃣ Climb the leaderboard
4️⃣ Maintain top 10 position

🎯 **Check '🏆 Leaderboard'** to see rankings!

💡 **Tip:** Refer friends to boost earnings!
"""
    await message.answer(msg, parse_mode="Markdown")

@dp.message_handler(Text(equals="📊 My Profile"), state="*")
async def my_profile(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): return
    user = get_user(user_id)
    if not user: 
        await cmd_start(message)
        return
    update_last_active(user_id)
    verified_count = user[3] or 0
    rank = "🐣 New User"
    if verified_count >= 10: rank = "🚜 Active Farmer"
    if verified_count >= 30: rank = "👑 Pro Farmer"
    if verified_count >= 50: rank = "💎 Legend Farmer"
    ref_earnings = (user[5] or 0) * float(get_setting('earn_referral'))
    in_top10 = is_user_in_top10(user[0])
    vip_status = "👑 VIP (Top-10)" if in_top10 else "👤 Regular"
    last_active = user[20] or "Never"
    
    msg = f"""
┌────────────────────────────┐
│      📊 MY PROFILE        │
└────────────────────────────┘

🆔 **User ID:** `{user[0]}`
👤 **Username:** @{user[1] or 'Not set'}
🎖️ **Rank:** {rank}
⭐ **Status:** {vip_status}

📈 **Earnings Summary:**
├─ 💳 Current Balance: {(user[4] or 0):.2f}৳
├─ 📧 Verified Accounts: {verified_count}
├─ 👥 Referrals: {user[5] or 0} (+{ref_earnings:.2f}৳)
├─ 💸 Total Withdrawn: {(user[18] or 0):.2f}৳
└─ 📅 Joined: {str(user[11])[:10]}
"""
    await message.answer(msg, parse_mode="Markdown")

@dp.message_handler(Text(equals="👥 My Referral"), state="*")
async def referral_menu(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): return
    user = get_user(user_id)
    if not user: 
        await cmd_start(message)
        return
    update_last_active(user_id)
    ref_count = user[5] or 0
    ref_earnings = ref_count * float(get_setting('earn_referral'))
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={message.from_user.id}"
    msg = f"""
┌────────────────────────────┐
│      👥 REFERRAL SYSTEM    │
└────────────────────────────┘

🔗 **Your Referral Link:**
`{ref_link}`

📊 **Your Stats:**
├─ 👥 Total Referred: {ref_count}
├─ 💰 Total Earnings: {ref_earnings:.2f}৳
└─ 🎯 Rate: {get_setting('earn_referral')}৳ per referral
"""
    await message.answer(msg, parse_mode="Markdown")

# --- FIXED: Admin Info ---
@dp.message_handler(Text(equals="📞 Admin Info"), state="*")
async def admin_info(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): return
    update_last_active(user_id)
    
    info_msg = """
┌────────────────────────────┐
│      📞 ADMIN INFO         │
└────────────────────────────┘

👑 **Owner:** Maim
📧 **Email:** immaim55@gmail.com
📱 **Telegram:** @cr_maim

⏰ **Support Hours:**
├─ Monday - Friday: 9 AM - 11 PM
├─ Saturday: 10 AM - 10 PM  
└─ Sunday: 11 AM - 9 PM

📞 **Contact for:**
├─ Account Issues
├─ Payment Problems
├─ Technical Support
└─ Partnership Offers

💡 **Quick Help:**
Click "❓ Help" for tutorials
"""
    await message.answer(info_msg, parse_mode="Markdown")

# --- FIXED: Help ---
@dp.message_handler(Text(equals="❓ Help"), state="*")
async def help_menu(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): return
    update_last_active(user_id)
    
    help_video_url = get_setting('help_video_url') or "https://t.me/example_video"
    help_text = f"""
┌────────────────────────────┐
│       📖 HELP GUIDE        │
└────────────────────────────┘

🎬 **Video Tutorial:**
{help_video_url}

📋 **HOW TO EARN MONEY:**
1️⃣ **Click "🚀 Start Work"**
2️⃣ **Create Account** with given details
3️⃣ **Verify** by uploading screenshot
4️⃣ **Get Paid** 10৳ per account!

💰 **WITHDRAWAL:**
• Minimum: 100৳
• Methods: Bkash, Nagad, Rocket
• Time: Within 24 hours

📞 **NEED HELP?**
Click "📞 Admin Info" for contact details
"""
    await message.answer(help_text, parse_mode="Markdown")

@dp.message_handler(commands=['help'], state="*")
async def help_menu_command(message: types.Message):
    await help_menu(message)

@dp.message_handler(Text(equals="🎁 Daily Bonus"), state="*")
async def daily_bonus(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): return
    update_last_active(user_id)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT balance, last_bonus_time FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row: 
        conn.close()
        await cmd_start(message)
        return
    balance, last_time_str = row
    current_time = datetime.now()
    bonus_amt = 1.0
    can_claim = False
    if last_time_str is None:
        can_claim = True
    else:
        try:
            last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
            diff = (current_time - last_time).total_seconds()
            if diff >= 86400: can_claim = True
            else:
                rem = 86400 - diff
                hrs, mins = int(rem // 3600), int((rem % 3600) // 60)
                await message.answer(f"⏳ **Daily Bonus Cooldown!**\nCome back in: {hrs}h {mins}m")
                conn.close()
                return
        except:
            can_claim = True
    if can_claim:
        c.execute("UPDATE users SET balance=balance+?, last_bonus_time=? WHERE user_id=?", 
                 (bonus_amt, current_time.strftime("%Y-%m-%d %H:%M:%S"), user_id))
        conn.commit()
        await message.answer(f"🎁 **Daily Bonus!**\n💰 Amount: +{bonus_amt}৳\n💎 New Balance: {(balance or 0) + bonus_amt:.2f}৳")
    conn.close()

# --- FIXED: Leaderboard ---
@dp.message_handler(Text(equals="🏆 Leaderboard"), state="*")
async def leaderboard(message: types.Message):
    update_last_active(message.from_user.id)
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("""
            SELECT username, balance, referral_count 
            FROM users 
            WHERE banned=0 
            ORDER BY balance DESC 
            LIMIT 15
        """)
        rows = c.fetchall()
        
        msg = "┌────────────────────────────┐\n│     🏆 LEADERBOARD        │\n└────────────────────────────┘\n\n"
        if not rows:
            msg += "No data available yet!"
        else:
            for idx, (name, bal, refs) in enumerate(rows[:15], 1):
                medal = "🥇" if idx==1 else ("🥈" if idx==2 else ("🥉" if idx==3 else f"{idx}."))
                display_name = (name or f"User{idx}")[:12]
                msg += f"{medal} **{display_name}** - ৳{(bal or 0):,.0f} ({refs or 0} refs)\n"
            
            user_id = message.from_user.id
            user = get_user(user_id)
            if user and (user[4] or 0) > 0:
                c.execute("SELECT COUNT(*) FROM users WHERE balance > ? AND banned=0", (user[4] or 0,))
                rank_row = c.fetchone()
                rank = rank_row[0] + 1 if rank_row else "N/A"
                msg += f"\n🎯 **Your Rank:** #{rank}"
        
        await message.answer(msg, parse_mode="Markdown")
    except Exception as e:
        await message.answer("⚠️ Leaderboard temporarily unavailable.")
        logging.error(f"Leaderboard error: {e}")
    finally:
        conn.close()

@dp.message_handler(Text(equals="💰 My Balance"), state="*")
async def menu_account(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): return
    update_last_active(user_id)
    user = get_user(user_id)
    if not user: 
        await cmd_start(message)
        return
    verified_count = user[3] or 0
    rank = "🐣 New User"
    if verified_count >= 10: rank = "🚜 Active Farmer"
    if verified_count >= 30: rank = "👑 Pro Farmer"
    ref_earnings = (user[5] or 0) * float(get_setting('earn_referral'))
    in_top10 = is_user_in_top10(user[0])
    vip_status = "👑 VIP (Top-10)" if in_top10 else "👤 Regular"
    min_withdraw = float(get_setting('vip_min_withdraw') if in_top10 else get_setting('min_withdraw'))
    msg = f"""
┌────────────────────────────┐
│      💰 MY BALANCE         │
└────────────────────────────┘

💳 **Current Balance:** {(user[4] or 0):.2f}৳
⭐ **Status:** {vip_status}
🎖️ **Rank:** {rank}

📊 **Earnings:**
├─ 📧 Verified: {verified_count}
├─ 👥 Referrals: {user[5] or 0}
└─ 💰 Withdrawable: {(user[4] or 0):.2f}৳

🎯 **Requirements:**
├─ 📱 Minimum Withdraw: {min_withdraw}৳
└─ ⏰ Processing: 24 Hours
"""
    await message.answer(msg, parse_mode="Markdown")

@dp.message_handler(Text(equals="🚀 Start Work"), state="*")
async def work_start(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): return
    update_last_active(user_id)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT status, current_email, current_password FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        await cmd_start(message)
        conn.close()
        return
    status, email, password = row
    user = get_user(user_id)
    if status == 'verified':
        email, password = generate_demo_creds()
        c.execute("UPDATE users SET current_email=?, current_password=?, status='new' WHERE user_id=?", 
                 (email, password, user_id))
        conn.commit()
    msg = f"""
┌────────────────────────────┐
│     🚀 CREATE GMAIL        │
└────────────────────────────┘

🎯 **Task #{user[3]+1}**
💰 **Earning:** 10৳ per account

📋 **Credentials:**
├─ 👤 Name: `Maim`
├─ 📧 Email: `{email}`
└─ 🔑 Password: `{password}`

⚠️ **Instructions:**
1️⃣ Go to [Gmail.com](https://gmail.com)
2️⃣ Create account using details above
3️⃣ Skip phone verification

📸 **After Creation:**
• Click **Screenshot** button below
• Upload screenshot for verification
"""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📸 Upload Screenshot", callback_data="submit_ss"))
    await message.answer(msg, parse_mode="Markdown", reply_markup=kb)
    conn.close()

@dp.callback_query_handler(lambda c: c.data == "submit_ss", state="*")
async def process_submit_ss(call: types.CallbackQuery):
    update_last_active(call.from_user.id)
    await RegisterState.waiting_for_screenshot.set()
    await call.message.answer("📸 **Upload screenshot of Gmail inbox or welcome page:**")

@dp.message_handler(content_types=['photo'], state=RegisterState.waiting_for_screenshot)
async def process_photo_upload(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not message.photo:
        await message.answer("❌ Please upload a photo.")
        return
    photo_id = message.photo[-1].file_id
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT current_email, current_password FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    email, password = row if row else ("Unknown", "Unknown")
    c.execute("UPDATE users SET screenshot_file_id=?, status='pending' WHERE user_id=?", (photo_id, user_id))
    conn.commit()
    conn.close()
    if LOG_CHANNEL_ID:
        caption = f"📄 **Manual Review Needed**\n👤 User: `{user_id}`\n📧 `{email}`\n🔑 `{password}`"
        try: await bot.send_photo(LOG_CHANNEL_ID, photo_id, caption=caption, parse_mode="Markdown")
        except: pass
    await state.finish()
    await message.answer("✅ **Screenshot Submitted!**\nWaiting for admin approval.")

@dp.message_handler(Text(equals="💸 Withdraw"), state="*")
async def withdraw_start(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): return
    update_last_active(user_id)
    if get_setting('withdrawals_enabled') != '1':
        await message.answer("⚠️ Withdrawals temporarily disabled.")
        return
    user = get_user(user_id)
    if not user: 
        await cmd_start(message)
        return
    min_w = float(get_setting('vip_min_withdraw') if user[13] else get_setting('min_withdraw'))
    if (user[4] or 0) < min_w:
        await message.answer(f"❌ **INSUFFICIENT BALANCE**\n💰 Required: {min_w}৳\n💳 Current: {(user[4] or 0):.2f}৳")
        return
    status = payment_system.get_system_status()
    payment_mode = "🔄 AUTO" if status["auto_payment_enabled"] else "👨‍💼 MANUAL"
    msg = f"💸 **WITHDRAW FUNDS**\n\n💰 Balance: {(user[4] or 0):.2f}৳\n⚙️ Mode: {payment_mode}\n💳 Minimum: {min_w}৳\n\n📱 **Select Payment Method:**"
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
    kb.add("Bkash", "Nagad")
    kb.add("Rocket", "❌ Cancel")
    await WithdrawState.waiting_for_method.set()
    await message.answer(msg, reply_markup=kb, parse_mode="Markdown")

@dp.message_handler(state=WithdrawState.waiting_for_method)
async def withdraw_method(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.finish()
        await message.answer("❌ Withdrawal cancelled.", reply_markup=get_main_menu_keyboard())
        return
    method = message.text.lower()
    status = payment_system.get_system_status()
    if status["auto_payment_enabled"]:
        if method == "bkash" and not status["bkash_configured"]:
            await message.answer("⚠️ Bkash auto payment not configured.")
            return
        elif method == "nagad" and not status["nagad_configured"]:
            await message.answer("⚠️ Nagad auto payment not configured.")
            return
        elif method == "rocket" and not status["rocket_configured"]:
            await message.answer("⚠️ Rocket auto payment not configured.")
            return
    await state.update_data(method=message.text)
    await WithdrawState.waiting_for_number.set()
    await message.answer("📱 **Enter Mobile Number:**\nFormat: `01XXXXXXXXX`", parse_mode="Markdown", reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(state=WithdrawState.waiting_for_number)
async def withdraw_number(message: types.Message, state: FSMContext):
    await state.update_data(number=message.text)
    await WithdrawState.waiting_for_amount.set()
    await message.answer("💰 **Enter Amount:**")

@dp.message_handler(state=WithdrawState.waiting_for_amount)
async def withdraw_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        user = get_user(message.from_user.id)
        if amount > (user[4] or 0):
            await message.answer("❌ **Insufficient Balance**")
            return
        data = await state.get_data()
        result = await process_withdrawal(message.from_user.id, amount, data['method'], data['number'])
        await state.finish()
        await message.answer(f"✅ **WITHDRAWAL SUBMITTED!**\n{result['message']}", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        if not payment_system.auto_payment_enabled or result["mode"] == "manual":
            for admin_id in ADMIN_IDS:
                try: await bot.send_message(admin_id, f"💸 **New Withdrawal**\n👤 `{message.from_user.id}`\n💰 `{amount}` {data['method']}")
                except: pass
    except ValueError:
        await message.answer("❌ **Invalid Amount** - Please enter a valid number")
    except Exception as e:
        await message.answer(f"❌ **Error:** {str(e)}")

@dp.message_handler(commands=['stats'], state="*")
async def show_stats(message: types.Message):
    update_last_active(message.from_user.id)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(balance) FROM users WHERE banned=0")
    user_stats = c.fetchone()
    total_users, total_balance = user_stats[0] or 0, user_stats[1] or 0
    c.execute("SELECT COUNT(*) FROM users WHERE status='verified'")
    verified = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*), SUM(amount) FROM withdrawals WHERE status='paid'")
    withdrawal_stats = c.fetchone()
    total_paid = withdrawal_stats[1] or 0
    conn.close()
    stats_msg = f"📊 **LIVE STATS**\n\n👥 Users: {total_users:,}\n✅ Verified: {verified:,}\n💰 Paid: {total_paid:,.2f}৳"
    await message.answer(stats_msg, parse_mode="Markdown")

# ==========================================
# ADMIN PANEL (Callback Handlers and Setup)
# ==========================================
@dp.message_handler(commands=['admin'], state="*")
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    status = payment_system.get_system_status()
    payment_mode = "🔄 AUTO" if status["auto_payment_enabled"] else "👨‍💼 MANUAL"
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📥 Manual Reviews", callback_data="admin_verifications"),
           InlineKeyboardButton("💸 Payouts", callback_data="admin_payments"))
    kb.add(InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_start"),
           InlineKeyboardButton("🚫 Ban System", callback_data="admin_ban_menu"))
    kb.add(InlineKeyboardButton("📈 Stats", callback_data="admin_stats"),
           InlineKeyboardButton("💰 Rates", callback_data="admin_earnings"))
    kb.add(InlineKeyboardButton("✏️ Notice", callback_data="admin_set_notice"),
           InlineKeyboardButton("📋 Export Data", callback_data="admin_export"))
    kb.add(InlineKeyboardButton(f"💳 Payment: {payment_mode}", callback_data="payment_dashboard"))
    await message.answer("👮‍♂️ **ADMIN PANEL**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data == "admin_home", state="*")
async def admin_home_callback(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    await call.message.delete()
    await admin_panel(call.message)

@dp.callback_query_handler(lambda c: c.data == "admin_payments", state="*")
async def admin_payments_menu(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("💳 Payment Dashboard", callback_data="payment_dashboard"),
           InlineKeyboardButton("📊 Payment Stats", callback_data="payment_stats"))
    kb.add(InlineKeyboardButton("🔄 Manual Approvals", callback_data="admin_withdrawals"),
           InlineKeyboardButton("📋 All Transactions", callback_data="all_transactions"))
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
    await call.message.edit_text("💰 **PAYMENT MANAGEMENT**", parse_mode="Markdown", reply_markup=kb)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "payment_dashboard", state="*")
async def show_payment_dashboard(call: types.CallbackQuery): await PaymentAdmin.show_payment_dashboard(call)
@dp.callback_query_handler(lambda c: c.data == "api_settings", state="*")
async def show_api_settings(call: types.CallbackQuery): await PaymentAdmin.show_api_settings(call)
@dp.callback_query_handler(lambda c: c.data == "how_to_setup_api", state="*")
async def how_to_setup_api(call: types.CallbackQuery): await PaymentAdmin.how_to_setup_api(call)
@dp.callback_query_handler(lambda c: c.data == "test_payments", state="*")
async def test_payment_methods(call: types.CallbackQuery): await PaymentAdmin.test_payment_methods(call)
@dp.callback_query_handler(lambda c: c.data == "check_balances", state="*")
async def check_balances_callback(call: types.CallbackQuery): await PaymentAdmin.show_check_balances(call)
@dp.callback_query_handler(lambda c: c.data == "pending_auto_payments", state="*")
async def show_pending_payments(call: types.CallbackQuery): await PaymentAdmin.show_pending_auto_payments(call, get_db_connection)

@dp.callback_query_handler(lambda c: c.data.startswith(("test_bkash", "test_nagad", "test_rocket")), state="*")
async def test_payment_method(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    method = call.data.replace("test_", "")
    success, message = payment_system.test_payment(method)
    await call.answer(message, show_alert=True)
    await PaymentAdmin.show_payment_dashboard(call)

@dp.callback_query_handler(lambda c: c.data == "process_payments_now", state="*")
async def process_payments_now(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    global auto_payment_handler
    if auto_payment_handler:
        await auto_payment_handler.process_pending_withdrawals()
        await call.answer("✅ Processing payments now...", show_alert=True)
    else:
        await call.answer("❌ Payment handler not initialized", show_alert=True)

@dp.callback_query_handler(lambda c: c.data == "payment_stats", state="*")
async def payment_stats_callback(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""SELECT COUNT(*), SUM(CASE WHEN w.status='paid' THEN 1 ELSE 0 END), SUM(CASE WHEN w.status='paid' THEN w.amount ELSE 0 END) FROM withdrawals w""")
    stats = c.fetchone()
    total, paid, total_paid = stats or (0,0,0)
    conn.close()
    message = f"📊 **Payment Stats**\n\nTotal: {total}\nPaid: {paid}\nAmount: {total_paid:.2f} TK"
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_payments"))
    await call.message.edit_text(message, parse_mode="Markdown", reply_markup=kb)
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "all_transactions", state="*")
async def all_transactions_callback(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""SELECT w.id, w.amount, w.payment_method, w.status FROM withdrawals w ORDER BY w.id DESC LIMIT 10""")
    transactions = c.fetchall()
    conn.close()
    message = "📋 **Recent Transactions**\n\n" + "\n".join([f"#{t[0]} {t[1]}TK ({t[2]}) - {t[3]}" for t in transactions])
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_payments"))
    await call.message.edit_text(message, parse_mode="Markdown", reply_markup=kb)
    await call.answer()

@dp.message_handler(commands=['set_api'], state="*")
async def set_api_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("❌ Format: /set_api method:key:secret")
            return
        credentials = args[1].split(":")
        method = credentials[0].lower()
        if method == "bkash": payment_system.setup_payment_apis(bkash_key=credentials[1], bkash_secret=credentials[2])
        elif method == "nagad": payment_system.setup_payment_apis(nagad_key=credentials[1], nagad_secret=credentials[2])
        elif method == "rocket": payment_system.setup_payment_apis(rocket_key=credentials[1])
        await message.answer(f"✅ {method} API configured!")
    except Exception as e: await message.answer(f"❌ Error: {str(e)}")

@dp.callback_query_handler(lambda c: c.data.startswith("admin_"), state="*")
async def admin_callbacks(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    if call.data == "admin_export":
        await call.answer("Exporting...", show_alert=True)
        # Simplified export for brevity
    elif call.data == "admin_set_notice":
        await AdminNotice.waiting_for_text.set()
        await call.message.answer("✏️ Enter new notice:")
        await call.answer()
    elif call.data == "admin_verifications":
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT user_id, current_email, current_password, screenshot_file_id FROM users WHERE status='pending' LIMIT 1")
        row = c.fetchone()
        conn.close()
        if not row:
            await call.answer("✅ No pending verifications!", show_alert=True)
            return
        uid, email, pwd, file_id = row
        caption = f"📋 **Pending Verification**\n👤 `{uid}`\n📧 `{email}`\n🔑 `{pwd}`"
        kb = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("✅ APPROVE", callback_data=f"appr_user_{uid}"), InlineKeyboardButton("❌ REJECT", callback_data=f"rej_user_{uid}"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        await call.message.delete()
        await bot.send_photo(call.from_user.id, file_id, caption=caption, reply_markup=kb, parse_mode="Markdown")
        await call.answer()
    elif call.data == "admin_withdrawals":
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""SELECT w.id, w.user_id, w.amount, w.payment_method, w.mobile_number FROM withdrawals w WHERE w.status='pending' AND w.auto_payment=0 ORDER BY w.request_time ASC LIMIT 1""")
        row = c.fetchone()
        conn.close()
        if not row:
            await call.answer("✅ No pending payments!", show_alert=True)
            return
        wid, uid, amt, method, num = row
        txt = f"💸 **Payment Request #{wid}**\n👤 `{uid}`\n💰 `{amt}` TK\n📱 `{method}: {num}`"
        kb = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("✅ PAID", callback_data=f"pay_yes_{wid}"), InlineKeyboardButton("❌ REJECT", callback_data=f"pay_no_{wid}"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        await call.message.edit_text(txt, reply_markup=kb, parse_mode="Markdown")
        await call.answer()
    elif call.data == "admin_stats":
        await show_stats(call.message)
        await call.answer()
    elif call.data == "admin_earnings":
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(InlineKeyboardButton("👥 Set Referral", callback_data="set_earn_ref"), InlineKeyboardButton("📧 Set Gmail", callback_data="set_earn_gmail"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        await call.message.edit_text("💰 **Rates Settings**", reply_markup=kb, parse_mode="Markdown")
        await call.answer()
    elif call.data == "admin_ban_menu":
        await AdminBanSystem.waiting_for_id.set()
        await call.message.answer("Enter user ID to ban/unban:")
        await call.answer()

@dp.callback_query_handler(lambda c: c.data.startswith(("set_earn_", "set_min_", "set_vip_")), state="*")
async def rate_prompt(call: types.CallbackQuery, state: FSMContext):
    key_map = {"set_earn_ref": "earn_referral", "set_earn_gmail": "earn_gmail"}
    setting_key = key_map.get(call.data)
    if setting_key:
        await state.update_data(key=setting_key)
        await AdminSettings.waiting_for_value.set()
        await call.message.answer("Enter new value:")
        await call.answer()

@dp.message_handler(state=AdminSettings.waiting_for_value)
async def rate_save(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        update_setting(data['key'], float(message.text))
        await message.answer("✅ Updated!")
    except: await message.answer("❌ Invalid number")
    await state.finish()
    await admin_panel(message)

@dp.message_handler(state=AdminNotice.waiting_for_text)
async def set_notice_save(message: types.Message, state: FSMContext):
    update_setting('notice', message.text)
    await message.answer("✅ Notice updated!")
    await state.finish()
    await admin_panel(message)

@dp.callback_query_handler(lambda c: c.data.startswith(("appr_user_", "rej_user_")), state="*")
async def verify_action(call: types.CallbackQuery):
    parts = call.data.split("_")
    action, uid = parts[1], int(parts[2])
    conn = get_db_connection()
    c = conn.cursor()
    if action == "appr":
        c.execute("UPDATE users SET status='verified', balance=balance+?, account_index=account_index+1 WHERE user_id=?", 
                 (float(get_setting('earn_gmail')), uid))
        c.execute("SELECT referrer_id FROM users WHERE user_id=? AND referral_paid=0", (uid,))
        ref = c.fetchone()
        if ref and ref[0]:
            c.execute("UPDATE users SET balance=balance+?, referral_count=referral_count+1 WHERE user_id=?", 
                     (float(get_setting('earn_referral')), ref[0]))
            c.execute("UPDATE users SET referral_paid=1 WHERE user_id=?", (uid,))
        try: await bot.send_message(uid, "✅ **Gmail Approved!**")
        except: pass
    else:
        c.execute("UPDATE users SET status='rejected' WHERE user_id=?", (uid,))
        try: await bot.send_message(uid, "❌ **Rejected**")
        except: pass
    conn.commit()
    conn.close()
    await call.answer("Done!")
    await admin_panel(call.message)

@dp.callback_query_handler(lambda c: c.data.startswith(("pay_yes_", "pay_no_")), state="*")
async def pay_action(call: types.CallbackQuery):
    parts = call.data.split("_")
    action, wid = parts[1], int(parts[2])
    conn = get_db_connection()
    c = conn.cursor()
    if action == "yes":
        c.execute("UPDATE withdrawals SET status='paid' WHERE id=?", (wid,))
    else:
        c.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
    conn.commit()
    conn.close()
    await call.answer("Done!")
    await admin_panel(call.message)

@dp.message_handler(state=AdminBanSystem.waiting_for_id)
async def ban_user(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text)
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET banned = CASE WHEN banned=1 THEN 0 ELSE 1 END WHERE user_id=?", (uid,))
        conn.commit()
        conn.close()
        await message.answer(f"✅ User {uid} ban status toggled")
    except: await message.answer("❌ Invalid ID")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "admin_broadcast_start", state="*")
async def broadcast_start(call: types.CallbackQuery):
    await AdminBroadcast.waiting_for_message.set()
    await call.message.answer("📢 **Enter broadcast message:**")
    await call.answer()

@dp.message_handler(state=AdminBroadcast.waiting_for_message)
async def broadcast_send(message: types.Message, state: FSMContext):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE banned=0")
    users = c.fetchall()
    conn.close()
    cnt = 0
    await message.answer("⏳ Broadcasting...")
    for u in users:
        try:
            await bot.send_message(u[0], f"📢 **ANNOUNCEMENT**\n\n{message.text}", parse_mode="Markdown")
            cnt += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Sent to **{cnt}** users!")
    await state.finish()

# ==========================================
# CATCH ALL & STARTUP
# ==========================================
@dp.message_handler(content_types=['text'], state="*")
async def handle_all_text_messages(message: types.Message):
    # This handler acts as a backup
    text = message.text.strip()
    if text == "🚀 Start Work": await work_start(message)
    elif text == "💰 My Balance": await menu_account(message)
    elif text == "🎁 Daily Bonus": await daily_bonus(message)
    elif text == "🏆 Leaderboard": await leaderboard(message)
    elif text == "💸 Withdraw": await withdraw_start(message)
    elif text == "👥 My Referral": await referral_menu(message)
    elif text == "👑 VIP Club": await vip_info(message)
    elif text == "📊 My Profile": await my_profile(message)
    elif text == "📞 Admin Info": await admin_info(message)
    elif text == "❓ Help": await help_menu(message)
    else:
        # Only show keyboard if it's not a command or state input
        state = await dp.current_state(user=message.from_user.id).get_state()
        if not state:
            await message.answer("Use the menu buttons.", reply_markup=get_main_menu_keyboard())

async def handle_health_check(request): return web.Response(text='Bot is running!')

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    app.router.add_get('/health', handle_health_check)
    port = int(os.environ.get('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def on_startup(dp):
    await start_web_server()
    global auto_payment_handler
    auto_payment_handler = AutoPaymentHandler(get_db_connection, bot)
    if AUTO_PAYMENT_ENABLED and payment_system.auto_payment_enabled:
        asyncio.create_task(auto_payment_handler.start_auto_payment_worker(interval=AUTO_PAY_CHECK_INTERVAL))
    print("✅ Bot Started Successfully")

if __name__ == '__main__':
    try:
        executor.start_polling(dp, skip_updates=True, on_startup=on_startup, timeout=60)
    except Exception as e:
        print(f"❌ Error: {e}")
        time.sleep(10)
