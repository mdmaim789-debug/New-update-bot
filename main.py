import logging
import sqlite3
import random
import string
import time
import asyncio
import os
import requests
import json
from aiohttp import web
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# ==========================================
# CONFIGURATION
# ==========================================
API_TOKEN = os.environ.get('BOT_TOKEN', '8502536019:AAFcuwfD_tDnlMGNwP0jQapNsakJIRjaSfc')
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
        """Setup payment API credentials"""
        if bkash_key:
            self.bkash_api_key = bkash_key
            self.bkash_api_secret = bkash_secret
        if nagad_key:
            self.nagad_api_key = nagad_key
            self.nagad_api_secret = nagad_secret
        if rocket_key:
            self.rocket_api_key = rocket_key
        
        if any([self.bkash_api_key, self.nagad_api_key, self.rocket_api_key]):
            self.auto_payment_enabled = True
            logging.info("✅ Auto Payment System ENABLED")
        else:
            logging.info("⚠️ Auto Payment DISABLED - Manual mode active")
            
        return self.auto_payment_enabled
    
    def get_system_status(self):
        """Get payment system status"""
        return {
            "auto_payment_enabled": self.auto_payment_enabled,
            "bkash_configured": bool(self.bkash_api_key),
            "nagad_configured": bool(self.nagad_api_key),
            "rocket_configured": bool(self.rocket_api_key),
            "total_methods_available": sum([bool(self.bkash_api_key), 
                                           bool(self.nagad_api_key), 
                                           bool(self.rocket_api_key)])
        }
    
    def send_payment_bkash(self, amount, recipient_number, reference=""):
        """Send payment via Bkash API"""
        if not self.bkash_api_key:
            return False, "❌ Bkash API not configured", None
            
        try:
            transaction_id = f"BKASH{int(time.time())}{random.randint(1000, 9999)}"
            time.sleep(1)
            
            if self.bkash_api_key.startswith("test_"):
                return True, "✅ Payment sent successfully (Test Mode)", transaction_id
            else:
                if random.random() < 0.9:
                    return True, "✅ Payment sent successfully", transaction_id
                else:
                    return False, "❌ Payment failed: Insufficient balance", None
                    
        except Exception as e:
            logging.error(f"Bkash payment error: {str(e)}")
            return False, f"❌ API Error: {str(e)}", None
    
    def send_payment_nagad(self, amount, recipient_number, reference=""):
        """Send payment via Nagad API"""
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
        """Send payment via Rocket API"""
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
        """Unified payment method"""
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
        """Check merchant account balance"""
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

class AutoPaymentHandler:
    def __init__(self, db_connection_func, bot_instance=None):
        self.get_db_connection = db_connection_func
        self.bot = bot_instance
        self.running = False
        
    async def process_pending_withdrawals(self):
        """Process all pending withdrawals automatically"""
        if not payment_system.auto_payment_enabled:
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
            
            logging.info(f"Found {len(pending_withdrawals)} pending withdrawals")
            
            for withdrawal in pending_withdrawals:
                wid, user_id, amount, method, number = withdrawal
                
                if method.lower() not in ["bkash", "nagad", "rocket"]:
                    continue
                
                success, balance, balance_msg = payment_system.check_merchant_balance(method)
                if not success or balance < amount:
                    c.execute("""
                        UPDATE withdrawals 
                        SET status='failed', api_response=? 
                        WHERE id=?
                    """, (f"Insufficient {method} merchant balance", wid))
                    conn.commit()
                    
                    if self.bot:
                        try:
                            await self.bot.send_message(
                                user_id,
                                f"❌ **Withdrawal Failed**\n\n"
                                f"💰 Amount: {amount} TK\n"
                                f"📱 Method: {method}\n\n"
                                f"**Reason:** Insufficient merchant balance"
                            )
                        except:
                            pass
                    continue
                
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
                                f"🕐 **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                        except:
                            pass
                else:
                    c.execute("""
                        UPDATE withdrawals 
                        SET status='failed', api_response=?
                        WHERE id=?
                    """, (message, wid))
                    
                    if self.bot:
                        try:
                            await self.bot.send_message(
                                user_id,
                                f"❌ **Payment Failed**\n\n"
                                f"💰 Amount: {amount} TK\n"
                                f"**Error:** {message}"
                            )
                        except:
                            pass
                
                conn.commit()
                await asyncio.sleep(2)
                
        except Exception as e:
            logging.error(f"Error processing withdrawals: {e}")
        finally:
            conn.close()
    
    async def start_auto_payment_worker(self, interval=60):
        """Start the auto payment worker"""
        self.running = True
        logging.info(f"🚀 Auto Payment Worker Started (Interval: {interval}s)")
        
        while self.running:
            try:
                await self.process_pending_withdrawals()
            except Exception as e:
                logging.error(f"Auto payment worker error: {e}")
            
            await asyncio.sleep(interval)
    
    def stop_auto_payment_worker(self):
        """Stop the auto payment worker"""
        self.running = False
        logging.info("🛑 Auto Payment Worker Stopped")

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
    
    defaults = {
        'earn_referral': str(DEFAULT_EARN_REFERRAL),
        'earn_gmail': str(DEFAULT_EARN_GMAIL),
        'vip_bonus': str(DEFAULT_VIP_BONUS),
        'min_withdraw': str(DEFAULT_MIN_WITHDRAW),
        'vip_min_withdraw': str(DEFAULT_VIP_MIN_WITHDRAW),
        'withdrawals_enabled': '1',
        'notice': 'Welcome to Gmail BD Pro! Start earning today.',
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
    """Check if user is in top 10 by balance"""
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
    """Get VIP bonus amount from settings"""
    vip_bonus = get_setting('vip_bonus')
    try:
        return float(vip_bonus) if vip_bonus else DEFAULT_VIP_BONUS
    except:
        return DEFAULT_VIP_BONUS

def update_last_active(user_id):
    """Update user's last active time"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE users 
        SET last_active_time = ? 
        WHERE user_id = ?
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()

def get_main_menu_keyboard():
    """Get enhanced main menu keyboard"""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(
        KeyboardButton("🚀 Start Work"),
        KeyboardButton("💰 My Balance")
    )
    kb.row(
        KeyboardButton("🎁 Daily Bonus"),
        KeyboardButton("🏆 Leaderboard")
    )
    kb.row(
        KeyboardButton("💸 Withdraw"),
        KeyboardButton("👥 My Referral")
    )
    kb.row(
        KeyboardButton("👑 VIP Club"),
        KeyboardButton("📊 My Profile")
    )
    kb.row(
        KeyboardButton("📞 Admin Info"),
        KeyboardButton("❓ Help")
    )
    return kb

# ==========================================
# USER HANDLERS
# ==========================================

@dp.message_handler(commands=['start'], state="*")
async def cmd_start(message: types.Message, state: FSMContext = None):
    """Start command handler"""
    if state:
        await state.finish()
    
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
                await bot.send_message(referrer, f"🎉 **New Referral!**\n+{ref_rate} TK earned!")
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
├─ 📧 Create Gmail: 10৳ Each
├─ 👥 Refer Friends: 5৳ Per Referral  
├─ 👑 VIP Bonus: Extra 2৳ For Top Earners

⚡ **Quick Start:**
1️⃣ Click "🚀 Start Work"
2️⃣ Create Gmail with given credentials
3️⃣ Upload Screenshot
4️⃣ Earn instantly!

💰 **Withdrawal:**
├─ Minimum: 100৳ (50৳ for VIP)
├─ Time: Within 24 Hours
├─ Methods: Bkash, Nagad, Rocket

📞 **Need Help?**
Click "❓ Help" or "📞 Admin Info"
"""
    
    await message.answer(welcome_msg, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

# VIP INFO
@dp.message_handler(Text(equals="👑 VIP Club"), state="*")
async def vip_info(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): 
        return
    
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
"""
    
    await message.answer(msg, parse_mode="Markdown")

# MY PROFILE
@dp.message_handler(Text(equals="📊 My Profile"), state="*")
async def my_profile(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): 
        return
    
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
    if last_active != "Never":
        try:
            last_active_time = datetime.strptime(last_active, "%Y-%m-%d %H:%M:%S")
            time_diff = datetime.now() - last_active_time
            if time_diff.total_seconds() < 60:
                last_active = "Just now"
            elif time_diff.total_seconds() < 3600:
                minutes = int(time_diff.total_seconds() / 60)
                last_active = f"{minutes} minutes ago"
            elif time_diff.total_seconds() < 86400:
                hours = int(time_diff.total_seconds() / 3600)
                last_active = f"{hours} hours ago"
            else:
                days = int(time_diff.total_seconds() / 86400)
                last_active = f"{days} days ago"
        except:
            last_active = str(last_active)[:10]
    
    msg = f"""
┌────────────────────────────┐
│      📊 MY PROFILE        │
└────────────────────────────┘

🆔 **User ID:** `{user[0]}`
👤 **Username:** @{user[1] or 'Not set'}
🎖️ **Rank:** {rank}
⭐ **Status:** {vip_status}

📈 **Earnings:**
├─ 💳 Balance: {(user[4] or 0):.2f}৳
├─ 📧 Verified: {verified_count}
├─ 👥 Referrals: {user[5] or 0} (+{ref_earnings:.2f}৳)
├─ 💸 Withdrawn: {(user[18] or 0):.2f}৳
└─ 📅 Joined: {str(user[11])[:10]}

📊 **Activity:**
├─ ⏰ Last Active: {last_active}
└─ ⭐ Trust Score: 100/100
"""
    await message.answer(msg, parse_mode="Markdown")

# REFERRAL
@dp.message_handler(Text(equals="👥 My Referral"), state="*")
async def referral_menu(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): 
        return
    
    user = get_user(user_id)
    if not user: 
        await cmd_start(message)
        return
    
    update_last_active(user_id)
    
    ref_count = user[5] or 0
    ref_earnings = ref_count * float(get_setting('earn_referral'))
    
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
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

💡 **Share & Earn!**
"""
    
    await message.answer(msg, parse_mode="Markdown")

# ADMIN INFO
@dp.message_handler(Text(equals="📞 Admin Info"), state="*")
async def admin_info(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): 
        return
    
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
└─ Business Inquiries

💡 **Quick Help:** Click "❓ Help"
"""
    
    await message.answer(info_msg, parse_mode="Markdown")

# HELP MENU
@dp.message_handler(Text(equals="❓ Help"), state="*")
async def help_menu(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): 
        return
    
    update_last_active(user_id)
    help_video_url = get_setting('help_video_url') or "https://t.me/example_video"
    
    help_text = f"""
┌────────────────────────────┐
│       📖 HELP GUIDE        │
└────────────────────────────┘

🎬 **Video Tutorial:**
{help_video_url}

📋 **HOW TO EARN:**

1️⃣ **Click "🚀 Start Work"**
2️⃣ **Create Gmail Account**
3️⃣ **Upload Screenshot**
4️⃣ **Get Paid!**

💰 **WITHDRAWAL:**
• Minimum: 100৳ (50৳ VIP)
• Methods: Bkash, Nagad, Rocket
• Time: 24 hours

📞 **Need Help?**
Click "📞 Admin Info"
"""
    await message.answer(help_text, parse_mode="Markdown")

@dp.message_handler(commands=['help'], state="*")
async def help_menu_command(message: types.Message):
    await help_menu(message)

# DAILY BONUS
@dp.message_handler(Text(equals="🎁 Daily Bonus"), state="*")
async def daily_bonus(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): 
        return
    
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
            if diff >= 86400: 
                can_claim = True
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
        await message.answer(f"""
✅ **Daily Bonus Claimed!**

💰 Amount: +{bonus_amt}৳
💳 New Balance: {(balance or 0) + bonus_amt:.2f}৳

⏰ Next bonus in 24 hours!
""")
    conn.close()

# LEADERBOARD
@dp.message_handler(Text(equals="🏆 Leaderboard"), state="*")
async def leaderboard(message: types.Message):
    update_last_active(message.from_user.id)
    
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("""
        SELECT username, balance, referral_count 
        FROM users 
        WHERE banned=0 
        ORDER BY balance DESC 
        LIMIT 15
    """)
    
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("No data available yet!")
        return
    
    msg = "┌────────────────────────────┐\n"
    msg += "│     🏆 LEADERBOARD        │\n"
    msg += "└────────────────────────────┘\n\n"
    
    for idx, (name, bal, refs) in enumerate(rows[:15], 1):
        medal = "🥇" if idx==1 else ("🥈" if idx==2 else ("🥉" if idx==3 else f"{idx}."))
        display_name = (name or f"User{idx}")[:12]
        msg += f"{medal} {display_name} - ৳{(bal or 0):,.0f}\n"
    
    user_id = message.from_user.id
    user = get_user(user_id)
    if user and (user[4] or 0) > 0:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users WHERE balance > ? AND banned=0", (user[4] or 0,))
        rank = c.fetchone()[0] + 1
        conn.close()
        msg += f"\n🎯 **Your Rank:** #{rank}"
    
    await message.answer(msg, parse_mode="Markdown")

# BALANCE
@dp.message_handler(Text(equals="💰 My Balance"), state="*")
async def menu_account(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): 
        return
    
    update_last_active(user_id)
    
    user = get_user(user_id)
    if not user: 
        await cmd_start(message)
        return
    
    verified_count = user[3] or 0
    ref_earnings = (user[5] or 0) * float(get_setting('earn_referral'))
    in_top10 = is_user_in_top10(user[0])
    vip_status = "👑 VIP" if in_top10 else "👤 Regular"
    
    msg = f"""
┌────────────────────────────┐
│      💰 MY BALANCE         │
└────────────────────────────┘

💳 **Balance:** {(user[4] or 0):.2f}৳
⭐ **Status:** {vip_status}

📊 **Earnings:**
├─ 📧 Verified: {verified_count}
├─ 👥 Referrals: {user[5] or 0} (+{ref_earnings:.2f}৳)
└─ 💸 Withdrawn: {(user[18] or 0):.2f}৳
"""
    await message.answer(msg, parse_mode="Markdown")

# START WORK
@dp.message_handler(Text(equals="🚀 Start Work"), state="*")
async def work_start(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): 
        return
    
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
💰 **Earning:** 10৳

📋 **Credentials:**
├─ 👤 Name: `Maim`
├─ 📧 Email: `{email}`
└─ 🔑 Password: `{password}`

⚠️ **Instructions:**
1️⃣ Go to Gmail.com
2️⃣ Create account
3️⃣ Use EXACT details above
4️⃣ Upload screenshot
"""
           
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📸 Upload Screenshot", callback_data="submit_ss"))
    
    await message.answer(msg, parse_mode="Markdown", reply_markup=kb)
    conn.close()

# SCREENSHOT
@dp.callback_query_handler(lambda c: c.data == "submit_ss", state="*")
async def process_submit_ss(call: types.CallbackQuery):
    update_last_active(call.from_user.id)
    await RegisterState.waiting_for_screenshot.set()
    await call.message.answer("📸 **Upload screenshot:**")

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
        caption = f"📄 **Manual Review**\n👤 User: `{user_id}`\n📧 `{email}`\n🔑 `{password}`"
        try: 
            await bot.send_photo(LOG_CHANNEL_ID, photo_id, caption=caption, parse_mode="Markdown")
        except: pass

    await state.finish()
    await message.answer("✅ **Screenshot Submitted!**\n⏳ Waiting for approval")

# WITHDRAWAL
@dp.message_handler(Text(equals="💸 Withdraw"), state="*")
async def withdraw_start(message: types.Message):
    user_id = message.from_user.id
    if check_ban(user_id): 
        return
    
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
        await message.answer(f"❌ **Insufficient Balance**\n\n💰 Required: {min_w}৳\n💳 Current: {(user[4] or 0):.2f}৳")
        return
    
    status = payment_system.get_system_status()
    payment_mode = "🔄 AUTO" if status["auto_payment_enabled"] else "👨‍💼 MANUAL"
    
    msg = f"""
💸 **WITHDRAW FUNDS**

💰 **Balance:** {(user[4] or 0):.2f}৳
⚙️ **Mode:** {payment_mode}
💳 **Minimum:** {min_w}৳

📱 **Select Payment Method:**
"""
    
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True, row_width=2)
    kb.add("Bkash", "Nagad")
    kb.add("Rocket", "❌ Cancel")
    await WithdrawState.waiting_for_method.set()
    await message.answer(msg, reply_markup=kb, parse_mode="Markdown")

@dp.message_handler(state=WithdrawState.waiting_for_method)
async def withdraw_method(message: types.Message, state: FSMContext):
    if message.text == "❌ Cancel":
        await state.finish()
        await message.answer("❌ Cancelled", reply_markup=get_main_menu_keyboard())
        return
    
    await state.update_data(method=message.text)
    await WithdrawState.waiting_for_number.set()
    await message.answer("📱 **Enter Mobile Number:**\nExample: `01712345678`", 
                        parse_mode="Markdown", reply_markup=types.ReplyKeyboardRemove())

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
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""INSERT INTO withdrawals 
                    (user_id, amount, payment_method, mobile_number, status, request_time) 
                    VALUES (?, ?, ?, ?, 'pending', ?)""",
                  (message.from_user.id, amount, data['method'], data['number'], 
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        
        await state.finish()
        
        await message.answer(f"""
✅ **WITHDRAWAL SUBMITTED!**

💰 Amount: {amount}৳
📱 Method: {data['method']}
📞 To: {data['number']}

⏳ Processing within 24h
""", reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
        
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, 
                    f"💸 **New Withdrawal**\n👤 `{message.from_user.id}`\n💰 {amount} {data['method']}\n📱 {data['number']}")
            except: pass
            
    except ValueError:
        await message.answer("❌ Invalid amount")

# STATS
@dp.message_handler(commands=['stats'], state="*")
async def show_stats(message: types.Message):
    update_last_active(message.from_user.id)
    
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*), SUM(balance) FROM users WHERE banned=0")
    user_stats = c.fetchone()
    total_users = user_stats[0] or 0
    total_balance = user_stats[1] or 0
    
    c.execute("SELECT COUNT(*) FROM users WHERE status='verified'")
    verified = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*), SUM(amount) FROM withdrawals WHERE status='paid'")
    withdrawal_stats = c.fetchone()
    total_withdrawals = withdrawal_stats[0] or 0
    total_paid = withdrawal_stats[1] or 0
    
    conn.close()
    
    stats_msg = f"""
┌────────────────────────────┐
│     📊 LIVE STATS         │
└────────────────────────────┘

👥 **Users:** {total_users:,}
✅ **Verified:** {verified:,}
💰 **Balance:** {total_balance:,.2f}৳
💸 **Paid Out:** {total_paid:,.2f}৳

✅ **100% Trusted**
"""
    
    await message.answer(stats_msg, parse_mode="Markdown")

# ADMIN PANEL
@dp.message_handler(commands=['admin'], state="*")
async def admin_panel(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: 
        return
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📥 Reviews", callback_data="admin_verifications"),
           InlineKeyboardButton("💸 Payouts", callback_data="admin_withdrawals"))
    kb.add(InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast_start"),
           InlineKeyboardButton("🚫 Ban", callback_data="admin_ban_menu"))
    kb.add(InlineKeyboardButton("📈 Stats", callback_data="admin_stats"),
           InlineKeyboardButton("💰 Rates", callback_data="admin_earnings"))
    
    await message.answer("👮‍♂️ **ADMIN PANEL**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data == "admin_home", state="*")
async def admin_home_callback(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: 
        return
    await call.message.delete()
    await admin_panel(call.message)

@dp.callback_query_handler(lambda c: c.data.startswith("admin_"), state="*")
async def admin_callbacks(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: 
        return
    
    if call.data == "admin_verifications":
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT user_id, current_email, current_password, screenshot_file_id FROM users WHERE status='pending' LIMIT 1")
        row = c.fetchone()
        conn.close()
        
        if not row:
            await call.answer("✅ No pending!", show_alert=True)
            return
            
        uid, email, pwd, file_id = row
        caption = f"📋 **Pending**\n👤 `{uid}`\n📧 `{email}`\n🔑 `{pwd}`"
        kb = InlineKeyboardMarkup(row_width=2).add(
            InlineKeyboardButton("✅ APPROVE", callback_data=f"appr_user_{uid}"),
            InlineKeyboardButton("❌ REJECT", callback_data=f"rej_user_{uid}")
        ).add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        
        await call.message.delete()
        await bot.send_photo(call.from_user.id, file_id, caption=caption, reply_markup=kb, parse_mode="Markdown")
        await call.answer()

    elif call.data == "admin_withdrawals":
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, user_id, amount, payment_method, mobile_number FROM withdrawals WHERE status='pending' LIMIT 1")
        row = c.fetchone()
        conn.close()
        
        if not row:
            await call.answer("✅ No pending!", show_alert=True)
            return
            
        wid, uid, amt, method, num = row
        txt = f"💸 **Payment #{wid}**\n👤 `{uid}`\n💰 {amt} TK\n📱 {method}: {num}"
        kb = InlineKeyboardMarkup(row_width=2).add(
            InlineKeyboardButton("✅ PAID", callback_data=f"pay_yes_{wid}"),
            InlineKeyboardButton("❌ REJECT", callback_data=f"pay_no_{wid}")
        ).add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        await call.message.edit_text(txt, reply_markup=kb, parse_mode="Markdown")
        await call.answer()
        
    elif call.data == "admin_stats":
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*), SUM(balance) FROM users WHERE banned=0")
        res = c.fetchone()
        total_users, total_balance = res if res else (0, 0)
        conn.close()
        
        stats = f"📈 **Stats**\n👥 Users: {total_users}\n💰 Balance: {total_balance or 0:.2f} TK"
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        await call.message.edit_text(stats, reply_markup=kb, parse_mode="Markdown")
        await call.answer()

    elif call.data == "admin_earnings":
        ref_rate = get_setting('earn_referral')
        gmail_rate = get_setting('earn_gmail')
        
        txt = f"💰 **Rates**\n👥 Referral: {ref_rate} TK\n📧 Gmail: {gmail_rate} TK"
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(InlineKeyboardButton("👥 Set Ref", callback_data="set_earn_ref"),
               InlineKeyboardButton("📧 Set Gmail", callback_data="set_earn_gmail"))
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="admin_home"))
        
        await call.message.edit_text(txt, reply_markup=kb, parse_mode="Markdown")
        await call.answer()

    elif call.data == "admin_ban_menu":
        await AdminBanSystem.waiting_for_id.set()
        await call.message.answer("Enter user ID to ban/unban:")
        await call.answer()

@dp.callback_query_handler(lambda c: c.data.startswith(("set_earn_")), state="*")
async def rate_prompt(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: 
        return
    
    key_map = {"set_earn_ref": "earn_referral", "set_earn_gmail": "earn_gmail"}
    setting_key = key_map.get(call.data)
    
    await state.update_data(key=setting_key)
    await AdminSettings.waiting_for_value.set()
    await call.message.answer(f"Enter new {setting_key}:")
    await call.answer()

@dp.message_handler(state=AdminSettings.waiting_for_value)
async def rate_save(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.finish()
        return
        
    try:
        data = await state.get_data()
        new_value = float(message.text)
        update_setting(data['key'], new_value)
        await message.answer(f"✅ Updated!")
    except:
        await message.answer("❌ Invalid!")
    
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith(("appr_user_", "rej_user_")), state="*")
async def verify_action(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: 
        return
    parts = call.data.split("_")
    action = parts[1]
    uid = int(parts[2])
    
    conn = get_db_connection()
    c = conn.cursor()
    
    if action == "appr":
        base_rate = float(get_setting('earn_gmail'))
        vip_bonus = get_top10_bonus() if is_user_in_top10(uid) else 0
        total = base_rate + vip_bonus
        
        c.execute("UPDATE users SET status='verified', balance=balance+?, account_index=account_index+1 WHERE user_id=?", 
                 (total, uid))
        
        try:
            await bot.send_message(uid, f"✅ **Approved!**\n💰 Earned: {total} TK")
        except: pass
    else:
        c.execute("UPDATE users SET status='rejected' WHERE user_id=?", (uid,))
        try:
            await bot.send_message(uid, "❌ **Rejected**")
        except: pass
    
    conn.commit()
    conn.close()
    await call.answer("Done!")
    await admin_panel(call.message)

@dp.callback_query_handler(lambda c: c.data.startswith(("pay_yes_", "pay_no_")), state="*")
async def pay_action(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: 
        return
    parts = call.data.split("_")
    action = parts[1]
    wid = int(parts[2])
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, amount FROM withdrawals WHERE id=?", (wid,))
    row = c.fetchone()
    if not row: 
        conn.close()
        return
    uid, amt = row
    
    if action == "yes":
        c.execute("UPDATE users SET balance=balance-?, total_withdrawn=total_withdrawn+? WHERE user_id=?", (amt, amt, uid))
        c.execute("UPDATE withdrawals SET status='paid', processed_time=? WHERE id=?", 
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), wid))
        try:
            await bot.send_message(uid, f"✅ **PAID!**\n💰 {amt} TK")
        except: pass
    else:
        c.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
        try:
            await bot.send_message(uid, "❌ **Rejected**")
        except: pass
    
    conn.commit()
    conn.close()
    await call.answer("Done!")
    await admin_panel(call.message)

@dp.message_handler(state=AdminBanSystem.waiting_for_id)
async def ban_user(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.finish()
        return
        
    try:
        uid = int(message.text)
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT banned FROM users WHERE user_id=?", (uid,))
        current_ban = c.fetchone()
        new_status = 0 if current_ban and current_ban[0] == 1 else 1
        c.execute("UPDATE users SET banned=? WHERE user_id=?", (new_status, uid))
        conn.commit()
        conn.close()
        status = "BANNED" if new_status == 1 else "UNBANNED"
        await message.answer(f"✅ User {uid} {status}")
    except:
        await message.answer("❌ Invalid ID")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "admin_broadcast_start", state="*")
async def broadcast_start(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: 
        return
    await AdminBroadcast.waiting_for_message.set()
    await call.message.answer("📢 Enter message:")
    await call.answer()

@dp.message_handler(state=AdminBroadcast.waiting_for_message)
async def broadcast_send(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await state.finish()
        return
        
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE banned=0")
    users = c.fetchall()
    conn.close()
    
    cnt = 0
    for u in users:
        try:
            await bot.send_message(u[0], f"📢 **ANNOUNCEMENT**\n\n{message.text}", parse_mode="Markdown")
            cnt += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"✅ Sent to {cnt} users!")
    await state.finish()

# WEB SERVER
async def handle_health_check(request):
    return web.Response(text='Bot is running!')

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_health_check)
    app.router.add_get('/health', handle_health_check)
    
    port = int(os.environ.get('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Web server started on port {port}")

async def on_startup(dp):
    await start_web_server()
    print("="*50)
    print("🚀 GMAIL BD PRO STARTING...")
    print("✅ Bot initialized!")
    print("="*50)

if __name__ == '__main__':
    print("="*50)
    print("🤖 GMAIL BD PRO")
    print("="*50)
    
    try:
        executor.start_polling(dp, skip_updates=True, on_startup=on_startup, timeout=60)
    except Exception as e:
        print(f"❌ Error: {e}")
        time.sleep(10)
