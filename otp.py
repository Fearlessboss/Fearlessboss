import asyncio
import json
import os
import re
import secrets
import string
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
from io import BytesIO

import aiohttp
from pyrogram import Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
import logging
import qrcode

# MongoDB
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============ CONFIGURATION ============
BOT_TOKEN = "8382836835:AAGpnIO5zX13Lv9fHjc8QpA-PSMhJXzQ5kA"
OWNER_ID = 7661825494
API_ID = 33628258
API_HASH = "0850762925b9c1715b9b122f7b753128"

# ============ MONGODB ============
MONGO_URL = "mongodb+srv://moderatorhelperorg_db_user:nze86usap2dYthZN@cluster0.uokrixs.mongodb.net/mydatabase?retryWrites=true&w=majority"
MONGO_DB_NAME = "mydatabase"

# Force Join Settings
SUPPORT_CHANNEL_ID = -1003782083448
SUPPORT_GROUP_ID = -1003857205137
LOGS_GROUP_ID = -1003764994914
SUPPORT_CHANNEL_LINK = "https://t.me/zudootp"
SUPPORT_GROUP_LINK = "https://t.me/zudootpsupport"

# Owner contact
OWNER_TG_LINK = "t.me/manwithoutego"
OWNER_TG_USERNAME = "manwithoutego"

# Resale buyer bot
RESALE_BUYER_BOT = "@zudobuyerbot"

# UPI Details
UPI_ID = "fearlessaditya@fam"
UPI_NAME = "Aditya"

# ===== CHECKING SERVER CONFIG =====
GMAIL_EMAIL = "deviramrani489@gmail.com"
GMAIL_PASSWORD = "eprrbxhaibzwwhqv"
GMAIL_IMAP_SERVER = "imap.gmail.com"
GMAIL_IMAP_PORT = 993

DB_FILE = "virtual_bot_data.json"

# Membership cache (1 hour)
membership_cache = {}
CACHE_DURATION = 3600

# ===== SERVER 2 =====
SERVICE_ADD_FEE = 10

# ===== PAYMENT VERIFICATION =====
MIN_DEPOSIT = 1
AUTO_VERIFY_TIMEOUT = 10
UTR_MAX_AGE_HOURS = 1

# ===== AI CONFIG =====
API_KEYS = [
    "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",
]
OPENROUTER_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL        = "llama-3.1-8b-instant"
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
MAX_IMAGES   = 5

# Country flags map (extended)
COUNTRY_FLAGS = {
    "USA": "🇺🇸", "US": "🇺🇸", "UK": "🇬🇧", "INDIA": "🇮🇳", "CANADA": "🇨🇦",
    "AUSTRALIA": "🇦🇺", "GERMANY": "🇩🇪", "FRANCE": "🇫🇷", "JAPAN": "🇯🇵",
    "KENYA": "🇰🇪", "NIGERIA": "🇳🇬", "PAKISTAN": "🇵🇰", "GHANA": "🇬🇭",
    "RUSSIA": "🇷🇺", "CHINA": "🇨🇳", "BRAZIL": "🇧🇷", "MEXICO": "🇲🇽",
    "ITALY": "🇮🇹", "SPAIN": "🇪🇸", "TURKEY": "🇹🇷", "INDONESIA": "🇮🇩",
    "BANGLADESH": "🇧🇩", "NEPAL": "🇳🇵", "SRILANKA": "🇱🇰", "PHILIPPINES": "🇵🇭",
    "VIETNAM": "🇻🇳", "THAILAND": "🇹🇭", "MALAYSIA": "🇲🇾", "SINGAPORE": "🇸🇬",
    "SOUTHAFRICA": "🇿🇦", "EGYPT": "🇪🇬", "UAE": "🇦🇪", "SAUDIARABIA": "🇸🇦",
    "IRAN": "🇮🇷", "IRAQ": "🇮🇶", "SOUTHKOREA": "🇰🇷", "KOREA": "🇰🇷",
    "POLAND": "🇵🇱", "UKRAINE": "🇺🇦", "NETHERLANDS": "🇳🇱", "BELGIUM": "🇧🇪",
    "SWEDEN": "🇸🇪", "NORWAY": "🇳🇴", "FINLAND": "🇫🇮", "DENMARK": "🇩🇰",
    "PORTUGAL": "🇵🇹", "GREECE": "🇬🇷", "IRELAND": "🇮🇪", "AUSTRIA": "🇦🇹",
    "SWITZERLAND": "🇨🇭", "ARGENTINA": "🇦🇷", "COLOMBIA": "🇨🇴", "CHILE": "🇨🇱",
    "PERU": "🇵🇪", "VENEZUELA": "🇻🇪"
}

def get_country_flag(country_name):
    """Get flag emoji for country. Country name may include year/tag suffix."""
    if not country_name:
        return "📱"
    # Try full name first
    upper = country_name.upper().strip()
    if upper in COUNTRY_FLAGS:
        return COUNTRY_FLAGS[upper]
    # Try first word
    first = upper.split()[0].split("(")[0].strip()
    if first in COUNTRY_FLAGS:
        return COUNTRY_FLAGS[first]
    # Try removing all non-alpha
    cleaned = re.sub(r'[^A-Z]', '', first)
    if cleaned in COUNTRY_FLAGS:
        return COUNTRY_FLAGS[cleaned]
    return "📱"

# Conversation States
(
    WAITING_FOR_AMOUNT,
    WAITING_FOR_COUPON,
    WAITING_FOR_SCREENSHOT,
    WAITING_FOR_COUNTRY,
    WAITING_FOR_PRICE,
    WAITING_FOR_SESSION,
    WAITING_FOR_DISCOUNT_AMOUNT,
    WAITING_FOR_COUPON_AMOUNT,
    WAITING_FOR_2FA,
    WAITING_FOR_LOGIN_STATUS,
    WAITING_FOR_DISCOUNT_CODE,
    WAITING_FOR_BOT_PHOTO,
    WAITING_FOR_QUANTITY,
    WAITING_FOR_ADD_MORE_SESSIONS,
    WAITING_FOR_BROADCAST_MESSAGE,
    WAITING_FOR_TARGET_USER_ID,
    WAITING_FOR_TARGET_AMOUNT,
    WAITING_FOR_UTR,
    WAITING_SERVICE_NAME,
    WAITING_SERVICE_PRICE,
    WAITING_SERVICE_CONTACT,
    WAITING_SERVICE_DESC,
    WAITING_FOR_UPI_SOURCE,
    WAITING_FOR_ADDACC_CHANNEL,
    WAITING_FOR_TRANSFER_USER,
    WAITING_FOR_TRANSFER_AMOUNT,
    WAITING_FOR_ADDBAL_AMOUNT
) = range(27)

# ============ MARKDOWN ESCAPE ============
def escape_markdown(text):
    if not text:
        return "Unknown"
    return (
        str(text)
        .replace('\\', '\\\\')
        .replace('*', '\\*')
        .replace('_', '\\_')
        .replace('[', '\\[')
        .replace('`', '\\`')
        .replace(']', '\\]')
    )

# ============ MONGO WRAPPER ============
class MongoStore:
    def __init__(self, url, db_name):
        self.client = MongoClient(url, serverSelectionTimeoutMS=15000)
        self.db = self.client[db_name]
        self.col = self.db["bot_state"]
        try:
            self.client.admin.command("ping")
            logger.info("[MONGO] Connected OK")
        except Exception as e:
            logger.error(f"[MONGO CONNECT ERROR] {e}")

    def load(self):
        doc = self.col.find_one({"_id": "state"})
        if doc:
            doc.pop("_id", None)
            return doc
        return None

    def save(self, data_dict):
        try:
            self.col.replace_one({"_id": "state"}, {"_id": "state", **data_dict}, upsert=True)
        except PyMongoError as e:
            logger.error(f"[MONGO SAVE ERROR] {e}")

mongo_store = MongoStore(MONGO_URL, MONGO_DB_NAME)

def _default_data():
    return {
        "users": {},
        "accounts": {},
        "resale_accounts": {},
        "discount_codes": {},
        "coupons": {},
        "pending_payments": {},
        "bot_photo": None,
        "states": {},
        "used_discounts": {},
        "used_utrs": {},
        "services": {},
        "service_seq": 0,
        "ai_enabled": True,
        "ai_memory": {},
        "sales_log": []  # track every sale for AI/analytics
    }

def load_data():
    m = mongo_store.load()
    if m:
        return m
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                legacy = json.load(f)
                logger.info("[MIGRATE] Loaded legacy JSON")
                mongo_store.save(legacy)
                return legacy
        except Exception as e:
            logger.error(f"[LOAD ERROR] {e}")
    return _default_data()

def save_data(d):
    try:
        mongo_store.save(d)
    except Exception as e:
        logger.error(f"[SAVE ERROR] {e}")

data = load_data()

# Force-correct types
_DICT_KEYS = [
    "users", "accounts", "resale_accounts", "discount_codes", "coupons", "pending_payments",
    "states", "used_discounts", "services", "used_utrs", "ai_memory"
]
for _k in _DICT_KEYS:
    if _k not in data or not isinstance(data.get(_k), dict):
        data[_k] = {}

if "used_txn_ids" in data and isinstance(data.get("used_txn_ids"), dict):
    for k, v in data["used_txn_ids"].items():
        data["used_utrs"][k] = v
    del data["used_txn_ids"]

if "service_seq" not in data or not isinstance(data.get("service_seq"), int):
    data["service_seq"] = 0

if "bot_photo" not in data:
    data["bot_photo"] = None

if "ai_enabled" not in data or not isinstance(data.get("ai_enabled"), bool):
    data["ai_enabled"] = True

if "sales_log" not in data or not isinstance(data.get("sales_log"), list):
    data["sales_log"] = []

save_data(data)

# ============ HELPERS ============
def generate_random_code(prefix: str, length: int = 10) -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        random_part = ''.join(secrets.choice(alphabet) for _ in range(length))
        code = f"{prefix}{random_part}"
        if code not in data.get("coupons", {}) and code not in data.get("discount_codes", {}):
            return code

def generate_upi_qr(amount: int) -> BytesIO:
    try:
        upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR&tn=VirtualAccountPayment"
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr.add_data(upi_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        bio.name = f'upi_qr_{amount}.png'
        img.save(bio, 'PNG')
        bio.seek(0)
        return bio
    except Exception as e:
        logger.error(f"[QR GENERATION ERROR] {e}")
        return None

def record_sale(user_id, username, country, quantity, price, channel):
    """Track every sale for AI analytics."""
    try:
        data["sales_log"].append({
            "user_id": user_id,
            "username": username,
            "country": country,
            "quantity": quantity,
            "price": price,
            "channel": channel,
            "timestamp": datetime.now().isoformat()
        })
        # keep last 500
        if len(data["sales_log"]) > 500:
            data["sales_log"] = data["sales_log"][-500:]
        save_data(data)
    except Exception as e:
        logger.error(f"[SALES LOG ERROR] {e}")

# ============ LOGGING → LOGS GROUP ============
async def send_log_to_support(context, log_message):
    try:
        await context.bot.send_message(
            chat_id=LOGS_GROUP_ID,
            text=log_message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"[LOG ERROR] {e}")
        try:
            await context.bot.send_message(
                chat_id=LOGS_GROUP_ID,
                text=log_message,
                disable_web_page_preview=True
            )
        except Exception as e2:
            logger.error(f"[LOG FALLBACK ERROR] {e2}")

async def send_user_log(context, user_id, log_message):
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=log_message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"[USER LOG ERROR] {e}")
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=log_message,
                disable_web_page_preview=True
            )
        except Exception as e2:
            logger.error(f"[USER LOG FALLBACK ERROR] {e2}")

async def log_user_registration(context, user_id, username):
    safe_username = escape_markdown(username)
    log = f"""
🆕 *NEW USER REGISTERED*

👤 User: {safe_username}
🆔 ID: `{user_id}`
⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

📊 Total Users: {len(data['users'])}
"""
    await send_log_to_support(context, log)

async def log_number_purchase(context, user_id, username, country, quantity, price, phone_numbers, channel="buy"):
    safe_username = escape_markdown(username)
    phones_text = "\n".join([f"   • `{phone}`" for phone in phone_numbers])
    log = f"""
✅ *NUMBER SOLD - SUCCESSFUL ({channel.upper()})*

👤 Buyer: {safe_username}
🆔 User ID: `{user_id}`
🌍 Country: {country.upper()}
📊 Quantity: {quantity}
💰 Amount: {price} INR

📱 Phone Numbers:
{phones_text}

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
💳 Remaining Balance: {data['users'][str(user_id)]['balance']} INR
"""
    await send_log_to_support(context, log)

async def log_session_added(context, country, quantity, price, phone_number="N/A", twofa=None, channel="buy"):
    twofa_line = f"\n🔐 2FA: `{twofa}`" if twofa else ""
    ch_dict = data["accounts"] if channel == "buy" else data["resale_accounts"]
    total_stock = ch_dict.get(country, {}).get('quantity', 0)
    log = f"""
➕ *SESSION ADDED ({channel.upper()})*

🌍 Country: {country.upper()}
📊 Added: {quantity} session(s)
💰 Price: {price} INR
📦 Total Stock: {total_stock}

📱 Phone Added: `{phone_number}`{twofa_line}

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_country_deleted(context, country, quantity, price, channel="buy"):
    log = f"""
🗑️ *COUNTRY DELETED ({channel.upper()})*

🌍 Country: {country.upper()}
📊 Removed: {quantity} session(s)
💰 Price: {price} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_coupon_redeemed(context, user_id, username, coupon_code, amount):
    safe_username = escape_markdown(username)
    safe_code = escape_markdown(coupon_code)
    log = f"""
🎟️ *COUPON REDEEMED*

👤 User: {safe_username}
🆔 ID: `{user_id}`
🎫 Coupon: `{safe_code}`
💰 Amount: {amount} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
💳 New Balance: {data['users'][str(user_id)]['balance']} INR
"""
    await send_log_to_support(context, log)

async def log_discount_applied(context, user_id, username, discount_code, discount):
    safe_username = escape_markdown(username)
    safe_code = escape_markdown(discount_code)
    log = f"""
🎟️ *DISCOUNT CODE APPLIED*

👤 User: {safe_username}
🆔 ID: `{user_id}`
🏷️ Code: `{safe_code}`
💰 Discount: {discount} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_payment_submitted(context, user_id, username, amount):
    safe_username = escape_markdown(username)
    log = f"""
💳 *PAYMENT SUBMITTED*

👤 User: {safe_username}
🆔 ID: `{user_id}`
💰 Amount: {amount} INR
📸 Screenshot: Received

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
⚠️ Status: Waiting for approval
"""
    await send_log_to_support(context, log)

async def log_payment_approved(context, user_id, username, amount, mode="MANUAL"):
    safe_username = escape_markdown(username)
    log = f"""
✅ *PAYMENT APPROVED ({mode})*

👤 User: {safe_username}
🆔 ID: `{user_id}`
💰 Amount: {amount} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
💳 New Balance: {data['users'][str(user_id)]['balance']} INR
"""
    await send_log_to_support(context, log)

async def log_payment_rejected(context, user_id, username, amount, reason="Invalid payment"):
    safe_username = escape_markdown(username)
    safe_reason = escape_markdown(reason)
    log = f"""
❌ *PAYMENT REJECTED*

👤 User: {safe_username}
🆔 ID: `{user_id}`
💰 Amount: {amount} INR
📝 Reason: {safe_reason}

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_auto_approve_attempt(context, user_id, username, amount, utr, status, reason="", id_type="ID"):
    safe_username = escape_markdown(username)
    safe_reason = escape_markdown(reason) if reason else ""
    safe_utr = escape_markdown(str(utr)) if utr else "N/A"
    safe_status = escape_markdown(str(status))
    safe_id_type = escape_markdown(str(id_type))
    reason_line = f"\n📝 Reason: {safe_reason}" if reason else ""
    log = f"""
🤖 *AUTO APPROVE ATTEMPT*

👤 User: {safe_username}
🆔 ID: `{user_id}`
💰 Amount: {amount} INR
🔢 {safe_id_type}: `{safe_utr}`
📊 Status: {safe_status}{reason_line}

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

    user_log = (
        f"🤖 *Auto Approve Update*\n\n"
        f"💰 Amount: ₹{amount}.00\n"
        f"🔢 {safe_id_type}: `{safe_utr}`\n"
        f"📊 Status: {safe_status}"
    )
    if reason:
        user_log += f"\n📝 Note: {safe_reason}"
    user_log += f"\n\n⏰ {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}"
    await send_user_log(context, user_id, user_log)

async def log_discount_created(context, discount_code, discount):
    safe_code = escape_markdown(discount_code)
    log = f"""
🏷️ *NEW DISCOUNT CREATED*

🎟️ Code: `{safe_code}`
💰 Discount: {discount} INR
📊 Usage: One-time per user

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_broadcast_sent(context, total, success, failed):
    log = f"""
📣 *BROADCAST COMPLETED*

👥 Total Users: {total}
✅ Sent: {success}
❌ Failed: {failed}
📊 Success Rate: {(success/total*100 if total else 0):.1f}%

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_otp_fetched(context, user_id, username, country, success_count, total):
    safe_username = escape_markdown(username)
    log = f"""
🔑 *OTP FETCH ATTEMPT*

👤 User: {safe_username}
🆔 ID: `{user_id}`
🌍 Country: {country.upper()}
✅ Found: {success_count}/{total}

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_insufficient_balance(context, user_id, username, required, current):
    safe_username = escape_markdown(username)
    log = f"""
⚠️ *INSUFFICIENT BALANCE*

👤 User: {safe_username}
🆔 ID: `{user_id}`
💰 Required: {required} INR
💳 Current: {current} INR
❌ Shortage: {required - current} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_owner_balance_change(context, action, target_user_id, amount, before, after, owner_id):
    log = f"""
👑 *OWNER BALANCE UPDATE*

🧾 Action: {action}
👤 Target User: `{target_user_id}`
💰 Amount: {amount} INR
📉 Before: {before} INR
📈 After: {after} INR
🆔 Owner: `{owner_id}`

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_session_logout(context, user_id, username, phone):
    safe_username = escape_markdown(username)
    log = f"""
🚪 *SESSION LOGOUT*

👤 User: {safe_username}
🆔 ID: `{user_id}`
📱 Phone: `{phone}`

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_transfer(context, from_user_id, from_username, to_user_id, amount, from_after, to_after):
    log = f"""
🔁 *BALANCE TRANSFER*

👤 From: {escape_markdown(from_username)} (`{from_user_id}`)
👤 To: `{to_user_id}`
💰 Amount: {amount} INR

💳 From new balance: {from_after} INR
💳 To new balance: {to_after} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

# ============ USER + STATE HELPERS ============
def get_user_data(user_id):
    user_id = str(user_id)
    if user_id not in data["users"]:
        data["users"][user_id] = {"balance": 0, "purchases": [], "username": f"User_{user_id}"}
        save_data(data)
    return data["users"][user_id]

def is_owner(user_id):
    return user_id == OWNER_ID

def set_user_state(user_id, state, extra_data=None):
    user_id = str(user_id)
    data["states"][user_id] = {"state": state, "data": extra_data or {}}
    save_data(data)

def get_user_state(user_id):
    user_id = str(user_id)
    return data["states"].get(user_id, {"state": -1, "data": {}})

def clear_user_state(user_id):
    user_id = str(user_id)
    if user_id in data["states"]:
        del data["states"][user_id]
        save_data(data)

def has_used_discount(user_id, discount_code):
    user_id = str(user_id)
    if user_id not in data["used_discounts"] or not isinstance(data["used_discounts"].get(user_id), list):
        data["used_discounts"][user_id] = []
    return discount_code in data["used_discounts"][user_id]

def mark_discount_used(user_id, discount_code):
    user_id = str(user_id)
    if user_id not in data["used_discounts"] or not isinstance(data["used_discounts"].get(user_id), list):
        data["used_discounts"][user_id] = []
    data["used_discounts"][user_id].append(discount_code)
    save_data(data)

# TXN / UTR helpers
def is_utr_used(utr: str) -> bool:
    used = data.get("used_utrs", {})
    if not isinstance(used, dict):
        data["used_utrs"] = {}
        return False
    return utr.upper() in used

def get_utr_used_info(utr: str):
    used = data.get("used_utrs", {})
    if not isinstance(used, dict):
        return None
    return used.get(utr.upper())

def mark_utr_used(utr: str, user_id: int, amount: int, mode: str = "auto"):
    if not isinstance(data.get("used_utrs"), dict):
        data["used_utrs"] = {}
    data["used_utrs"][utr.upper()] = {
        "user_id": user_id,
        "amount": amount,
        "used_at": datetime.now().isoformat(),
        "mode": mode
    }
    save_data(data)

def is_valid_txn_id_format(val: str) -> bool:
    if not val:
        return False
    val = val.strip()
    if len(val) < 8 or len(val) > 30:
        return False
    if not val.isalnum():
        return False
    has_letter = any(c.isalpha() for c in val)
    has_digit = any(c.isdigit() for c in val)
    return has_letter and has_digit

def is_valid_utr_format(val: str) -> bool:
    if not val:
        return False
    val = val.strip()
    if not val.isdigit():
        return False
    if len(val) < 10 or len(val) > 22:
        return False
    return True

def detect_id_type(val: str):
    if not val:
        return (None, None)
    v = val.strip()
    if is_valid_utr_format(v):
        return ("utr", v)
    if is_valid_txn_id_format(v):
        return ("txn", v.upper())
    return (None, None)

# ============ MEMBERSHIP ============
async def check_user_membership(context, user_id):
    current_time = datetime.now().timestamp()
    if user_id in membership_cache:
        cache_entry = membership_cache[user_id]
        if current_time - cache_entry["time"] < CACHE_DURATION:
            return cache_entry["is_member"]
    try:
        ch_member = await context.bot.get_chat_member(SUPPORT_CHANNEL_ID, user_id)
        gr_member = await context.bot.get_chat_member(SUPPORT_GROUP_ID, user_id)
        is_member = (
            ch_member.status in ["creator", "administrator", "member"] and
            gr_member.status in ["creator", "administrator", "member"]
        )
        membership_cache[user_id] = {"is_member": is_member, "time": current_time}
        return is_member
    except Exception as e:
        logger.error(f"[MEMBERSHIP CHECK ERROR] {e}")
        return False

async def show_force_join_message(update, context):
    text = """
🔒 *Access Restricted*

To use this bot, please join:

📢 Channel & 💬 Support Group

After joining, click *Verify*.
"""
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=SUPPORT_CHANNEL_LINK)],
        [InlineKeyboardButton("💬 Join Group", url=SUPPORT_GROUP_LINK)],
        [InlineKeyboardButton("✅ Verify", callback_data="verify_join")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except:
            await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def verify_join_handler(update, context):
    query = update.callback_query
    user_id = update.effective_user.id
    if user_id in membership_cache:
        del membership_cache[user_id]
    is_member = await check_user_membership(context, user_id)
    if is_member:
        await query.answer("✅ Verified!", show_alert=False)
        await main_menu(update, context)
    else:
        await query.answer("❌ Please join both channel & group first!", show_alert=True)

# ============ IMAP EMAIL VERIFICATION ============
def _id_in_text(idval, text):
    if not idval or not text:
        return False
    return str(idval).upper() in text.upper()

def _extract_amounts(text):
    if not text:
        return []
    found = []
    patterns = [
        r'(?:rs\.?|₹|inr)\s*([\d,]+(?:\.\d{1,2})?)',
        r'([\d,]+(?:\.\d{1,2})?)\s*(?:rs\.?|₹|inr)',
        r'amount\s*[:\-]?\s*(?:rs\.?|₹|inr)?\s*([\d,]+(?:\.\d{1,2})?)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            raw = m.group(1).replace(',', '')
            try:
                val = float(raw)
                if val > 0:
                    found.append(val)
            except:
                pass
    return found

def _decode_subject(subj):
    if not subj:
        return ""
    try:
        parts = decode_header(subj)
        out = ""
        for txt, enc in parts:
            if isinstance(txt, bytes):
                try:
                    out += txt.decode(enc or 'utf-8', errors='ignore')
                except:
                    out += txt.decode('utf-8', errors='ignore')
            else:
                out += str(txt)
        return out
    except:
        return str(subj)

def _get_email_body(msg):
    body = ""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get("Content-Disposition") or "")
                if ctype in ("text/plain", "text/html") and "attachment" not in disp:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body += payload.decode(errors='ignore')
                    except:
                        pass
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(errors='ignore')
    except Exception as e:
        logger.error(f"[BODY DECODE ERROR] {e}")
    return body

def _extract_txn_and_utr_from_text(text):
    txn_id = None
    utr = None
    if not text:
        return (txn_id, utr)
    m = re.search(r'transaction\s*id\s*[:\-]?\s*([A-Z0-9]{8,30})', text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        if is_valid_txn_id_format(candidate):
            txn_id = candidate.upper()
    m2 = re.search(r'\butr\b\s*[:\-]?\s*([0-9]{10,22})', text, re.IGNORECASE)
    if m2:
        candidate2 = m2.group(1).strip()
        if is_valid_utr_format(candidate2):
            utr = candidate2
    return (txn_id, utr)

def _email_search_id_sync(idval, id_type, expected_amount):
    result = {
        "found": False, "matched_amount": False, "found_amount": None,
        "too_old": False, "error": None, "txn_id": None, "utr": None
    }
    try:
        mail = imaplib.IMAP4_SSL(GMAIL_IMAP_SERVER, GMAIL_IMAP_PORT)
        mail.login(GMAIL_EMAIL, GMAIL_PASSWORD)
        mail.select("INBOX")

        since_dt = (datetime.now() - timedelta(hours=UTR_MAX_AGE_HOURS)).strftime("%d-%b-%Y")
        typ, msg_ids = mail.search(None, f'(SINCE "{since_dt}")')
        if typ != "OK":
            result["error"] = "imap_search_fail"
            try:
                mail.logout()
            except:
                pass
            return result

        ids = msg_ids[0].split()
        ids = list(reversed(ids))
        idval_str = str(idval)

        for mid in ids:
            try:
                typ, msg_data = mail.fetch(mid, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                subj = _decode_subject(msg.get("Subject", ""))
                body = _get_email_body(msg)
                full = f"{subj}\n{body}"

                if _id_in_text(idval_str, full):
                    date_hdr = msg.get("Date", "")
                    too_old = False
                    try:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(date_hdr)
                        if dt is not None:
                            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                            if (now - dt).total_seconds() > UTR_MAX_AGE_HOURS * 3600:
                                too_old = True
                    except:
                        pass

                    result["found"] = True
                    if too_old:
                        result["too_old"] = True

                    found_txn, found_utr = _extract_txn_and_utr_from_text(full)
                    result["txn_id"] = found_txn
                    result["utr"] = found_utr

                    found_amounts = _extract_amounts(full)
                    if found_amounts:
                        result["found_amount"] = found_amounts[0]
                        for amt in found_amounts:
                            if abs(amt - float(expected_amount)) < 0.5:
                                result["matched_amount"] = True
                                break
                    try:
                        mail.logout()
                    except:
                        pass
                    return result
            except Exception as e:
                logger.error(f"[EMAIL FETCH LOOP ERR] {e}")
                continue

        try:
            mail.logout()
        except:
            pass
        return result
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[EMAIL SEARCH ERROR] {e}")
        return result

async def verify_id_via_email(idval, id_type, expected_amount):
    return await asyncio.to_thread(_email_search_id_sync, idval, id_type, expected_amount)

# ============ PYROGRAM HELPERS ============
async def create_client(session_string, user_id_str):
    try:
        client = Client(
            f"session_{user_id_str}",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string,
            in_memory=True
        )
        await client.start()
        return client
    except Exception as e:
        logger.error(f"[CLIENT CREATE ERROR] {e}")
        return None

async def get_phone_number(client):
    try:
        me = await client.get_me()
        return f"+{me.phone_number}" if me.phone_number else "Unknown"
    except Exception as e:
        logger.error(f"[PHONE ERROR] {e}")
        return "Error"

async def get_otp_from_telegram(client):
    try:
        async for message in client.get_chat_history(777000, limit=5):
            if message.text:
                match = re.search(r'\b(\d{5,6})\b', message.text)
                if match:
                    msg_time = message.date
                    now = datetime.now(msg_time.tzinfo) if msg_time.tzinfo else datetime.now()
                    if (now - msg_time).total_seconds() < 300:
                        return match.group(1)
        return None
    except Exception as e:
        logger.error(f"[OTP ERROR] {e}")
        return None

async def logout_session(session_string, user_id_str):
    try:
        client = Client(
            f"logout_{user_id_str}",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string,
            in_memory=True
        )
        await client.start()
        await client.log_out()
        return True
    except Exception as e:
        logger.error(f"[LOGOUT ERROR] {e}")
        return False

# ============ START / MENU ============
async def start(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or f"User_{user_id}"
    new_user = str(user_id) not in data["users"]
    u = get_user_data(user_id)
    u["username"] = username
    save_data(data)
    if new_user:
        await log_user_registration(context, user_id, username)
    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return
    await main_menu(update, context)

async def main_menu(update, context):
    user_id = update.effective_user.id
    balance = get_user_data(user_id)["balance"]
    username = update.effective_user.username or update.effective_user.first_name or f"User_{user_id}"
    text = f"""
👋 *Welcome, {escape_markdown(username)}!*

💳 Balance: ₹{balance}.00

━━━━━━━━━━━━━━━━━━━━
🔥 *Zudo OTP Bot* 🔥
━━━━━━━━━━━━━━━━━━━━

Choose an option below:
"""
    keyboard = [
        [InlineKeyboardButton("📱 Buy Accounts", callback_data="virtual_accounts")],
        [InlineKeyboardButton("♻️ Resale Accounts", callback_data="resale_accounts")],
        [InlineKeyboardButton("🛒 Services", callback_data="server2_home")],
        [InlineKeyboardButton("💳 My Profile", callback_data=f"my_balance_{user_id}_"),
         InlineKeyboardButton("➕ Add Funds", callback_data="add_funds")],
        [InlineKeyboardButton("🎟 Discount", callback_data="discount"),
         InlineKeyboardButton("📊 History", callback_data="history_stats")],
        [InlineKeyboardButton("👥 Refer & Earn", callback_data="coming_soon_refer")]
    ]
    if is_owner(user_id):
        keyboard.append([InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    photo_id = data.get("bot_photo")
    if update.callback_query:
        try:
            if photo_id:
                await update.callback_query.message.delete()
                await context.bot.send_photo(chat_id=user_id, photo=photo_id, caption=text,
                                             reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except:
            await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        if photo_id:
            await update.message.reply_photo(photo=photo_id, caption=text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def coming_soon_handler(update, context):
    query = update.callback_query
    await query.answer("🚧 Coming Soon!", show_alert=True)

async def show_history_stats(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    u = get_user_data(user_id)
    purchases = u.get("purchases", [])
    text = "📊 *Your History*\n\n"
    if not purchases:
        text += "No purchases yet."
    else:
        for p in purchases[-10:]:
            ch = p.get("channel", "buy").upper()
            text += f"• {p['country'].upper()} × {p['quantity']} — ₹{p['price']}.00 [{ch}]\n"
    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def help_cmd(update, context):
    text = """
ℹ️ *Zudo OTP Bot Help*

Commands:
/start — Open main menu
/panel — Owner panel (owner only)
/add — Add balance to user (owner)
/deduct — Deduct balance (owner)
/transfer — Transfer balance to another user
/addaccount — Quick add account (owner)
/myservice — Your listed services
/allservices — All services
/ai on|off — Toggle AI in groups (owner)
/cancel — Cancel current action
"""
    await update.message.reply_text(text, parse_mode='Markdown')

async def cancel_cmd(update, context):
    user_id = update.effective_user.id
    clear_user_state(user_id)
    await update.message.reply_text("✅ Cancelled.", parse_mode='Markdown')
    return ConversationHandler.END

# ============ COUNTRY UI (BUY + RESALE) — NEW DESIGN ============
def _channel_dict(channel):
    return data["accounts"] if channel == "buy" else data["resale_accounts"]

def _channel_prefix(channel):
    return "" if channel == "buy" else "r"

async def show_countries(update, context, channel="buy"):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return
    keyboard = []
    ch = _channel_dict(channel)
    available = {c: info for c, info in ch.items() if info["quantity"] > 0}

    if channel == "resale":
        header = (
            "♻️ *Resale Accounts*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"ℹ️ Buy resale accounts (also listed on {RESALE_BUYER_BOT}).\n\n"
        )
        footer_prompt = "\n👇 *Select a country to purchase:*"
    else:
        header = "📍 *Available Accounts*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        footer_prompt = "\n👇 *Select a country to purchase:*"

    if available:
        text = header
        pfx = _channel_prefix(channel)
        items = list(available.items())
        for i, (country, info) in enumerate(items):
            flag = get_country_flag(country)
            # New design as requested
            text += f"📱 *{country.title()}* {flag}\n"
            text += f"📦 Stock: {info['quantity']}  •  💰 Price: ₹{info['price']}.00\n"
            if i < len(items) - 1:
                text += "────────────────────\n"
            keyboard.append([InlineKeyboardButton(
                f"{flag} {country.title()} — ₹{info['price']}",
                callback_data=f"{pfx}country_{country}"
            )])
        text += footer_prompt
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])
    else:
        text = header + "📭 No accounts available currently!"
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"[SHOW COUNTRIES] {e}")
        try:
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except:
            pass

async def show_countries_buy(update, context):
    await show_countries(update, context, channel="buy")

async def show_countries_resale(update, context):
    await show_countries(update, context, channel="resale")

async def show_account_details(update, context, channel="buy"):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split("_", 1)
    country = parts[1]
    ch = _channel_dict(channel)
    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return
    if country not in ch:
        await query.edit_message_text("❌ Country not found!", parse_mode='Markdown')
        return
    info = ch[country]
    balance = get_user_data(user_id)["balance"]
    label = "Virtual Account" if channel == "buy" else "Resale Account"
    flag = get_country_flag(country)
    text = f"""
📱 *{country.upper()} {label}* {flag}

━━━━━━━━━━━━━━━━━━━━
💰 Price: ₹{info['price']}.00
📊 Available: {info['quantity']}
💳 Your Balance: ₹{balance}.00
━━━━━━━━━━━━━━━━━━━━
"""
    pfx = _channel_prefix(channel)
    keyboard = [
        [InlineKeyboardButton("💳 BUY NUMBER", callback_data=f"{pfx}buy_number_{country}")],
        [InlineKeyboardButton("🎟 DISCOUNT CODE", callback_data="discount")],
        [InlineKeyboardButton("🔙 Back", callback_data=("virtual_accounts" if channel == "buy" else "resale_accounts"))],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def process_buy_number(update, context, channel="buy"):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    # Parse country properly — everything after "buy_number_"
    prefix = "buy_number_"
    country = query.data[query.data.index(prefix) + len(prefix):]
    ch = _channel_dict(channel)
    if country not in ch:
        await query.edit_message_text("❌ Country not found!", parse_mode='Markdown')
        return ConversationHandler.END
    info = ch[country]
    price = info["price"]
    balance = get_user_data(user_id)["balance"]
    available = info["quantity"]
    flag = get_country_flag(country)
    await query.edit_message_text(
        f"🛒 *Purchase {country.upper()}* {flag}\n\n"
        f"📊 Available: {available}\n💰 Price: ₹{price}.00\n💳 Balance: ₹{balance}.00\n\n"
        f"📝 How many? (1-{available}):",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_QUANTITY, {"country": country, "price": price, "available": available, "channel": channel})
    return WAITING_FOR_QUANTITY

async def handle_quantity_input(update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    try:
        quantity = int(text)
        state = get_user_state(user_id)
        country = state["data"]["country"]
        price = state["data"]["price"]
        available = state["data"]["available"]
        channel = state["data"].get("channel", "buy")
        if quantity <= 0:
            await update.message.reply_text("❌ Quantity must be > 0!")
            return WAITING_FOR_QUANTITY
        if quantity > available:
            await update.message.reply_text(f"❌ Only {available} available!")
            return WAITING_FOR_QUANTITY
        total_price = price * quantity
        balance = get_user_data(user_id)["balance"]
        username = data["users"][str(user_id)]["username"]
        if balance < total_price:
            await log_insufficient_balance(context, user_id, username, total_price, balance)
            keyboard = [
                [InlineKeyboardButton("➕ Add Funds", callback_data="add_funds")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ]
            await update.message.reply_text(
                f"❌ *Insufficient Balance!*\n\n"
                f"💰 Required: ₹{total_price}.00\n"
                f"💳 Balance: ₹{balance}.00\n"
                f"❌ Short: ₹{total_price - balance}.00",
                reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
            )
            clear_user_state(user_id)
            return ConversationHandler.END
        flag = get_country_flag(country)
        pfx = _channel_prefix(channel)
        keyboard = [
            [InlineKeyboardButton("✅ CONFIRM", callback_data=f"{pfx}confirm_buy_{country}_{quantity}"),
             InlineKeyboardButton("❌ CANCEL", callback_data="main_menu")]
        ]
        ch_label = "Buy" if channel == "buy" else "Resale"
        await update.message.reply_text(
            f"🛒 *Confirm Purchase* {flag}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌍 Country: {country.upper()}\n"
            f"📦 Channel: {ch_label}\n"
            f"📊 Quantity: {quantity}\n"
            f"💰 Total: ₹{total_price}.00\n"
            f"💳 Balance: ₹{balance}.00\n"
            f"━━━━━━━━━━━━━━━━━━━━",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number!")
        return WAITING_FOR_QUANTITY

# ---------- CONFIRM PURCHASE (shared internal) ----------
async def _do_confirm_purchase(update, context, channel):
    """Actual purchase logic — same for buy & resale."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    # data format: [r]confirm_buy_<country>_<qty>
    raw = query.data
    prefix = "confirm_buy_"
    payload = raw[raw.index(prefix) + len(prefix):]
    # last _NUM = quantity
    m = re.match(r'^(.+)_(\d+)$', payload)
    if not m:
        await query.edit_message_text("❌ Invalid confirm data!", parse_mode='Markdown')
        return
    country = m.group(1)
    quantity = int(m.group(2))
    username = data["users"][str(user_id)]["username"]

    ch = _channel_dict(channel)
    if country not in ch or ch[country]["quantity"] < quantity:
        await query.edit_message_text("❌ Not enough stock now!", parse_mode='Markdown')
        return

    info = ch[country]
    price = info["price"]
    total_price = price * quantity
    balance = get_user_data(user_id)["balance"]
    if balance < total_price:
        await query.edit_message_text("❌ Insufficient balance!", parse_mode='Markdown')
        return

    # Take sessions
    sessions_pool = info.get("sessions", [])
    if len(sessions_pool) < quantity:
        await query.edit_message_text("❌ Not enough sessions in stock!", parse_mode='Markdown')
        return

    taken = sessions_pool[:quantity]
    ch[country]["sessions"] = sessions_pool[quantity:]
    ch[country]["quantity"] = len(ch[country]["sessions"])

    # Deduct balance
    data["users"][str(user_id)]["balance"] -= total_price

    # Record purchase
    purchase = {
        "country": country,
        "quantity": quantity,
        "price": total_price,
        "channel": channel,
        "status": "completed",
        "date": datetime.now().isoformat(),
        "sessions": taken
    }
    data["users"][str(user_id)]["purchases"].append(purchase)
    save_data(data)

    record_sale(user_id, username, country, quantity, total_price, channel)

    # Fetch phones
    async def fetch_phone(i, sd):
        s = sd.get("session")
        if s:
            try:
                c = await create_client(s, f"{user_id}_{i}")
                if c:
                    p = await get_phone_number(c)
                    try:
                        await c.stop()
                    except:
                        pass
                    return p
            except Exception as e:
                logger.error(f"[FETCH PHONE ERR] {e}")
        return "Error"

    phones = await asyncio.gather(*[fetch_phone(i, s) for i, s in enumerate(taken)])
    for i, ph in enumerate(phones):
        try:
            purchase["sessions"][i]["phone_number"] = ph
        except:
            pass
    save_data(data)

    await log_number_purchase(context, user_id, username, country, quantity, total_price, phones, channel=channel)

    # ---- ✅ NEW FORMATTED SUCCESS MESSAGE (as requested) ----
    flag = get_country_flag(country)
    text = (
        f"📱 *Phone Numbers Retrieved!*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌍 Country: *{country.upper()}* {flag}\n"
        f"📦 Quantity: {quantity}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    for i, p in enumerate(phones, 1):
        text += f"*Account {i}:*\n📞 `{p}`\n\n"

    text += (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ *Next Steps:*\n"
        "1️⃣ Use the number above to login on Telegram\n"
        "2️⃣ Click *GET OTP* below when Telegram asks for code\n"
        "3️⃣ Enter the OTP in Telegram to complete login\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ *Note:* Do NOT click 'Login Complete' until you've entered the OTP,\n"
        "otherwise the account will be locked and you'll lose access."
    )

    # Get purchase index
    idx = len(data["users"][str(user_id)]["purchases"]) - 1

    # ✅ As requested: ONLY GET OTP button here (no login complete on this screen)
    keyboard = [
        [InlineKeyboardButton("🔍 GET OTP", callback_data=f"get_otp_{user_id}_{idx}")],
        [InlineKeyboardButton("🛒 Buy More", callback_data=("virtual_accounts" if channel == "buy" else "resale_accounts"))],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    try:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"[CONFIRM EDIT ERR] {e}")
        await context.bot.send_message(chat_id=user_id, text=text,
                                       reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def confirm_purchase_buy(update, context):
    await _do_confirm_purchase(update, context, "buy")

async def confirm_purchase_resale(update, context):
    await _do_confirm_purchase(update, context, "resale")

# ============ OTP HANDLER ============
async def get_number_handler(update, context):
    """Re-fetch phone numbers for an existing purchase."""
    query = update.callback_query
    await query.answer("📱 Fetching...")
    parts = query.data.split("_")
    user_id = int(parts[2])
    idx = int(parts[3])
    up = data["users"][str(user_id)]["purchases"]
    if idx >= len(up):
        await query.answer("❌ Not found", show_alert=True)
        return
    purchase = up[idx]
    sessions = purchase.get("sessions", [])
    if not sessions:
        await query.answer("❌ No sessions", show_alert=True)
        return

    async def fetch_phone(i, sd):
        s = sd.get("session")
        if s:
            try:
                c = await create_client(s, f"{user_id}_{i}")
                if c:
                    p = await get_phone_number(c)
                    try:
                        await c.stop()
                    except:
                        pass
                    return p
            except:
                pass
        return "Error"

    phones = await asyncio.gather(*[fetch_phone(i, s) for i, s in enumerate(sessions)])
    for i, ph in enumerate(phones):
        try:
            purchase["sessions"][i]["phone_number"] = ph
        except:
            pass
    save_data(data)

    flag = get_country_flag(purchase['country'])
    text = f"📱 *Phone Numbers*\n\n{purchase['country'].upper()} {flag} — {purchase['quantity']}\n"
    for i, p in enumerate(phones, 1):
        text += f"\n*Account {i}:* `{p}`"
    keyboard = [
        [InlineKeyboardButton("🔍 GET OTP", callback_data=f"get_otp_{user_id}_{idx}")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def get_otp_handler(update, context):
    query = update.callback_query
    await query.answer("🔍 Fetching OTP...")
    parts = query.data.split("_")
    user_id = int(parts[2])
    idx = int(parts[3])
    up = data["users"][str(user_id)]["purchases"]
    if idx >= len(up):
        return
    purchase = up[idx]
    sessions = purchase.get("sessions", [])
    if not sessions:
        return
    flag = get_country_flag(purchase['country'])
    await query.edit_message_text(f"🔍 Fetching OTP for *{purchase['country'].upper()}* {flag}...", parse_mode='Markdown')

    async def fetch_otp(i, sd):
        s = sd.get("session")
        phone = sd.get("phone_number", "N/A")
        twofa = sd.get("twofa")
        if s:
            client = None
            try:
                client = await create_client(s, f"{user_id}_{i}_otp")
                if client:
                    if phone in ["N/A", None, "Error"]:
                        try:
                            phone = await get_phone_number(client)
                        except:
                            pass
                    otp = await get_otp_from_telegram(client)
                    try:
                        await client.stop()
                    except:
                        pass
                    if otp:
                        msg = f"✅ OTP: `{otp}` — {phone}"
                        if twofa:
                            msg += f"\n🔐 2FA: `{twofa}`"
                        return {"status": "success", "message": msg}
                    return {"status": "not_found", "message": f"⏳ OTP not found — {phone}"}
            except Exception as e:
                if client:
                    try:
                        await client.stop()
                    except:
                        pass
                return {"status": "error", "message": "❌ Error"}
        return {"status": "error", "message": "❌ No session"}

    results = await asyncio.gather(*[fetch_otp(i, s) for i, s in enumerate(sessions)])
    text = f"🔑 *OTP Results*\n\n{purchase['country'].upper()} {flag}\n"
    success = 0
    for i, r in enumerate(results, 1):
        text += f"\n*Account {i}:* {r['message']}"
        if r["status"] == "success":
            success += 1
    await log_otp_fetched(context, user_id, data["users"][str(user_id)]["username"], purchase['country'], success, len(sessions))

    # ✅ Only GET OTP retry — LOGIN COMPLETE now only appears AFTER a successful OTP fetch,
    # and even then behind a small confirmation to prevent accidental logout.
    keyboard = [
        [InlineKeyboardButton("🔄 TRY AGAIN", callback_data=f"get_otp_{user_id}_{idx}")],
    ]
    if success > 0:
        keyboard.append([InlineKeyboardButton("✅ I've logged in — Finish", callback_data=f"login_complete_{user_id}_{idx}")])
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def login_complete(update, context):
    query = update.callback_query
    await query.answer("✅ Verified!")
    parts = query.data.split("_")
    user_id = int(parts[2])
    idx = int(parts[3])
    keyboard = [
        [InlineKeyboardButton("🚪 LOGOUT BOT", callback_data=f"logout_session_{user_id}_{idx}")],
        [InlineKeyboardButton("🛒 Buy More", callback_data="virtual_accounts")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    await query.edit_message_text(
        "🎉 *Login Complete!*\n\nYou can now logout the bot session below.",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )

async def logout_session_handler(update, context):
    query = update.callback_query
    await query.answer("🚪 Logging out...")
    parts = query.data.split("_")
    user_id = int(parts[2])
    idx = int(parts[3])
    username = data["users"][str(user_id)]["username"]
    up = data["users"][str(user_id)]["purchases"]
    if idx >= len(up):
        return
    purchase = up[idx]
    sessions = purchase.get("sessions", [])
    results = []
    for i, sd in enumerate(sessions):
        s = sd.get("session")
        phone = sd.get("phone_number", "N/A")
        if s:
            ok = await logout_session(s, f"{user_id}_{i}")
            results.append(f"{'✅' if ok else '❌'} `{phone}`")
            if ok:
                await log_session_logout(context, user_id, username, phone)
    await query.edit_message_text(
        "🚪 *Logout Results*\n\n" + "\n".join(results),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Buy More", callback_data="virtual_accounts")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]),
        parse_mode='Markdown'
    )

# End of Part 1 — continues in Part 2
# ============ CONTINUATION OF PART 1 — PASTE DIRECTLY AFTER PART 1 ============
# (Do NOT add imports again — everything is already imported in Part 1)

# ============ PROFILE ============
async def show_balance(update, context):
    query = update.callback_query
    await query.answer()
    try:
        user_id = int(query.data.split("_")[2])
    except:
        user_id = update.effective_user.id
    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return
    balance = get_user_data(user_id)["balance"]
    text = f"💳 *My Profile*\n\n💰 Balance: ₹{balance}.00\n\n📊 *Recent Transactions:*"
    purchases = data["users"][str(user_id)]["purchases"]
    if not purchases:
        text += "\n• No transactions"
    else:
        for p in purchases[-5:]:
            ch = p.get("channel", "buy").upper()
            text += f"\n• {p['country'].upper()} × {p['quantity']} — ₹{p['price']}.00 [{ch}]"
    keyboard = [
        [InlineKeyboardButton("➕ Add Funds", callback_data="add_funds")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============ ADD FUNDS FLOW ============
async def show_add_funds_options(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return
    clear_user_state(user_id)
    text = f"""
➕ *Add Funds*

💳 Choose method:

1️⃣ *Buy Funds (UPI)* — Instant
2️⃣ *Coupon Code* — Redeem

💡 Minimum: {MIN_DEPOSIT} INR
"""
    keyboard = [
        [InlineKeyboardButton("💸 Buy Funds (UPI)", callback_data="buy_fund")],
        [InlineKeyboardButton("🎟 Coupon Code", callback_data="coupon_code")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def ask_fund_amount(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await query.edit_message_text(
        f"💰 *Enter Amount*\n\n💡 Minimum ₹{MIN_DEPOSIT}\n\n📝 Reply with amount:",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_AMOUNT)
    return WAITING_FOR_AMOUNT

async def handle_amount_input(update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    try:
        amount = int(text)
        if amount < MIN_DEPOSIT:
            await update.message.reply_text(f"❌ Minimum ₹{MIN_DEPOSIT}!")
            return WAITING_FOR_AMOUNT
        # Store amount, then ask UPI source
        set_user_state(user_id, WAITING_FOR_UPI_SOURCE, {"amount": amount})
        keyboard = [
            [InlineKeyboardButton("💜 FamPay", callback_data="upisrc_fampay")],
            [InlineKeyboardButton("🏦 Other UPI (GPay/PhonePe/Paytm)", callback_data="upisrc_other")],
            [InlineKeyboardButton("🔙 Back", callback_data="upisrc_back")]
        ]
        await update.message.reply_text(
            f"💳 *Payment Method*\n\n"
            f"💰 Amount: ₹{amount}.00\n\n"
            f"Choose the UPI app you'll pay from:",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Enter valid number!")
        return WAITING_FOR_AMOUNT

async def handle_upi_source(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    st = get_user_state(user_id)
    amount = st["data"].get("amount")
    if not amount:
        await query.edit_message_text("❌ Session expired. Try again with /start", parse_mode='Markdown')
        return
    src = "fampay" if query.data == "upisrc_fampay" else "other"
    st["data"]["upi_source"] = src
    set_user_state(user_id, WAITING_FOR_SCREENSHOT, st["data"])

    # Send QR
    qr_bio = generate_upi_qr(amount)
    src_label = "FamPay" if src == "fampay" else "GPay / PhonePe / Paytm"
    caption = (
        f"💳 *UPI Payment* — {src_label}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Amount: ₹{amount}.00\n"
        f"🆔 UPI ID: `{UPI_ID}`\n"
        f"👤 Name: {UPI_NAME}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ Scan the QR OR pay to the UPI ID above\n"
        f"2️⃣ Pay *exactly* ₹{amount}.00\n"
        f"3️⃣ Send payment screenshot here\n\n"
        f"⚠️ Amount must match exactly, else auto-approve will fail."
    )
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]
    try:
        if qr_bio:
            await query.message.delete()
            await context.bot.send_photo(chat_id=user_id, photo=qr_bio, caption=caption,
                                         reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await query.edit_message_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"[UPI SRC ERR] {e}")
        await context.bot.send_message(chat_id=user_id, text=caption,
                                       reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_upi_source_back(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    clear_user_state(user_id)
    await show_add_funds_options(update, context)

async def handle_screenshot(update, context):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if state["state"] != WAITING_FOR_SCREENSHOT:
        return ConversationHandler.END
    amount = state["data"].get("amount")
    upi_source = state["data"].get("upi_source", "other")
    if not amount:
        await update.message.reply_text("❌ Session expired.")
        clear_user_state(user_id)
        return ConversationHandler.END
    photo = update.message.photo[-1]
    photo_id = photo.file_id
    username = data["users"][str(user_id)]["username"]

    data["pending_payments"][str(user_id)] = {
        "amount": amount,
        "photo_id": photo_id,
        "upi_source": upi_source,
        "status": "awaiting_utr",
        "timestamp": datetime.now().isoformat(),
        "utr": None,
        "id_type": None,
        "paired_txn": None,
        "paired_utr": None
    }
    save_data(data)
    await log_payment_submitted(context, user_id, username, amount)

    hint = (
        "📝 *Send your Transaction UTR / Ref ID*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Amount: ₹{amount}.00\n\n"
        "✅ *UTR* — 12 digits (all numbers)  → e.g. `123456789012`\n"
        "✅ *Transaction ID* — letters+numbers  → e.g. `T2401151234ABC`\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Just paste it here. I'll auto-verify or send it to owner for manual approval."
    )
    set_user_state(user_id, WAITING_FOR_UTR, state["data"])
    await update.message.reply_text(hint, parse_mode='Markdown')
    return WAITING_FOR_UTR

async def handle_utr_input(update, context):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if state["state"] != WAITING_FOR_UTR:
        return ConversationHandler.END
    val = update.message.text.strip()
    id_type, cleaned = detect_id_type(val)
    if not id_type:
        await update.message.reply_text(
            "❌ *Invalid format!*\n\n"
            "UTR must be 10-22 digits (numbers only).\n"
            "Transaction ID must be 8-30 alphanumeric characters.\n\n"
            "Please send again:",
            parse_mode='Markdown'
        )
        return WAITING_FOR_UTR

    amount = state["data"].get("amount")
    upi_source = state["data"].get("upi_source", "other")
    username = data["users"][str(user_id)]["username"]

    # Duplicate check
    if is_utr_used(cleaned):
        used_info = get_utr_used_info(cleaned)
        await update.message.reply_text(
            f"❌ *Duplicate {id_type.upper()}!*\n\n"
            f"This ID was already used earlier.\n"
            f"If this is a mistake, contact @{OWNER_TG_USERNAME}",
            parse_mode='Markdown'
        )
        await log_auto_approve_attempt(
            context, user_id, username, amount, cleaned, "REJECTED — DUPLICATE",
            reason=f"Already used by {used_info.get('user_id') if used_info else 'unknown'}",
            id_type=id_type.upper()
        )
        # Move to manual review anyway so owner can decide
        data["pending_payments"][str(user_id)]["utr"] = cleaned
        data["pending_payments"][str(user_id)]["id_type"] = id_type
        data["pending_payments"][str(user_id)]["status"] = "manual_review"
        save_data(data)
        clear_user_state(user_id)
        return ConversationHandler.END

    # Save immediately so we NEVER lose it
    data["pending_payments"][str(user_id)]["utr"] = cleaned
    data["pending_payments"][str(user_id)]["id_type"] = id_type
    data["pending_payments"][str(user_id)]["status"] = "verifying"
    save_data(data)

    processing_msg = await update.message.reply_text(
        f"🔎 *Verifying your payment...*\n\n"
        f"💰 Amount: ₹{amount}.00\n"
        f"🔢 {id_type.upper()}: `{cleaned}`\n\n"
        f"⏳ Please wait 10-15 seconds...",
        parse_mode='Markdown'
    )

    # Try email verification (wrapped so it NEVER crashes the flow)
    verification = None
    try:
        verification = await asyncio.wait_for(
            verify_id_via_email(cleaned, id_type, amount),
            timeout=AUTO_VERIFY_TIMEOUT * 3
        )
    except asyncio.TimeoutError:
        verification = {"found": False, "error": "timeout"}
    except Exception as e:
        logger.error(f"[UTR VERIFY ERR] {e}")
        verification = {"found": False, "error": str(e)}

    if not isinstance(verification, dict):
        verification = {"found": False}

    found = verification.get("found", False)
    matched_amount = verification.get("matched_amount", False)
    too_old = verification.get("too_old", False)
    found_amount = verification.get("found_amount")
    paired_txn = verification.get("txn_id")
    paired_utr = verification.get("utr")

    # ---- DECISION ----
    if found and matched_amount and not too_old:
        # ✅ AUTO APPROVE
        data["users"][str(user_id)]["balance"] += amount
        data["pending_payments"][str(user_id)]["status"] = "approved"
        data["pending_payments"][str(user_id)]["paired_txn"] = paired_txn
        data["pending_payments"][str(user_id)]["paired_utr"] = paired_utr
        mark_utr_used(cleaned, user_id, amount, mode="auto")
        if paired_txn and paired_txn != cleaned:
            mark_utr_used(paired_txn, user_id, amount, mode="auto_paired")
        if paired_utr and paired_utr != cleaned:
            mark_utr_used(paired_utr, user_id, amount, mode="auto_paired")
        save_data(data)

        await log_payment_approved(context, user_id, username, amount, mode="AUTO")
        await log_auto_approve_attempt(
            context, user_id, username, amount, cleaned,
            "APPROVED", reason="Amount matched in bank email", id_type=id_type.upper()
        )

        new_bal = data["users"][str(user_id)]["balance"]
        try:
            await processing_msg.edit_text(
                f"✅ *Payment Approved!*\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 Amount: ₹{amount}.00\n"
                f"🔢 {id_type.upper()}: `{cleaned}`\n"
                f"💳 New Balance: ₹{new_bal}.00\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📝 Verified: Amount matched in bank records.",
                parse_mode='Markdown'
            )
        except:
            pass
        clear_user_state(user_id)
        return ConversationHandler.END

    # ---- NEEDS MANUAL REVIEW ----
    if too_old:
        reason_txt = "Transaction is older than 1 hour"
    elif found and not matched_amount:
        reason_txt = f"ID found but amount didn't match (found ₹{found_amount})"
    elif verification.get("error"):
        reason_txt = "Bank email server not reachable — sent for manual review"
    else:
        reason_txt = "ID not found in recent bank emails"

    data["pending_payments"][str(user_id)]["status"] = "manual_review"
    save_data(data)

    await log_auto_approve_attempt(
        context, user_id, username, amount, cleaned,
        "MANUAL REVIEW", reason=reason_txt, id_type=id_type.upper()
    )

    # Notify owner with the payment card
    try:
        safe_username = escape_markdown(username)
        owner_text = (
            f"💳 *NEW PAYMENT — MANUAL REVIEW*\n\n"
            f"👤 User: {safe_username}\n"
            f"🆔 ID: `{user_id}`\n"
            f"💰 Amount: ₹{amount}.00\n"
            f"💜 Source: {upi_source.upper()}\n"
            f"🔢 {id_type.upper()}: `{cleaned}`\n"
            f"📝 Reason: {escape_markdown(reason_txt)}"
        )
        okb = [
            [InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_fund_{user_id}"),
             InlineKeyboardButton("❌ REJECT", callback_data=f"reject_fund_{user_id}")]
        ]
        await context.bot.send_photo(
            chat_id=OWNER_ID,
            photo=data["pending_payments"][str(user_id)]["photo_id"],
            caption=owner_text,
            reply_markup=InlineKeyboardMarkup(okb),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"[OWNER NOTIFY ERR] {e}")

    try:
        await processing_msg.edit_text(
            f"⏳ *Sent for Manual Review*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Amount: ₹{amount}.00\n"
            f"🔢 {id_type.upper()}: `{cleaned}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 *Reason:* {reason_txt}\n\n"
            f"👑 The owner has been notified. You'll get an approval message shortly.\n"
            f"💬 For urgent help: @{OWNER_TG_USERNAME}",
            parse_mode='Markdown'
        )
    except:
        pass

    clear_user_state(user_id)
    return ConversationHandler.END

async def ask_coupon_code(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await query.edit_message_text(
        "🎟 *Redeem Coupon*\n\n📝 Enter your coupon code:",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_COUPON)
    return WAITING_FOR_COUPON

async def handle_coupon_input(update, context):
    user_id = update.effective_user.id
    code = update.message.text.strip().upper()
    if code not in data["coupons"]:
        await update.message.reply_text("❌ Invalid coupon code!")
        clear_user_state(user_id)
        return ConversationHandler.END
    cinfo = data["coupons"][code]
    if cinfo.get("used"):
        await update.message.reply_text("❌ Coupon already used!")
        clear_user_state(user_id)
        return ConversationHandler.END
    amount = cinfo["amount"]
    data["users"][str(user_id)]["balance"] += amount
    data["coupons"][code]["used"] = True
    save_data(data)
    username = data["users"][str(user_id)]["username"]
    await log_coupon_redeemed(context, user_id, username, code, amount)
    new_bal = data["users"][str(user_id)]["balance"]
    await update.message.reply_text(
        f"✅ *Coupon Redeemed!*\n\n"
        f"🎫 Code: `{code}`\n💰 Added: ₹{amount}.00\n💳 New Balance: ₹{new_bal}.00",
        parse_mode='Markdown'
    )
    clear_user_state(user_id)
    return ConversationHandler.END

# ============ DISCOUNT APPLY ============
async def apply_discount(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await query.edit_message_text("🎟 *Apply Discount*\n\n💡 Enter code:", parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_DISCOUNT_CODE)
    return WAITING_FOR_DISCOUNT_CODE

async def handle_discount_code(update, context):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if state["state"] != WAITING_FOR_DISCOUNT_CODE:
        return ConversationHandler.END
    code = update.message.text.strip().upper()
    if code not in data["discount_codes"]:
        await update.message.reply_text("❌ Invalid code!")
        clear_user_state(user_id)
        return ConversationHandler.END
    if has_used_discount(user_id, code):
        await update.message.reply_text("❌ You already used this discount code!")
        clear_user_state(user_id)
        return ConversationHandler.END
    dinfo = data["discount_codes"][code]
    da = dinfo["discount"]
    mark_discount_used(user_id, code)
    await log_discount_applied(context, user_id, data["users"][str(user_id)]["username"], code, da)
    await update.message.reply_text(
        f"✅ *Discount Applied!*\n🎟 Code: `{code}`\n💰 ₹{da}.00",
        parse_mode='Markdown'
    )
    clear_user_state(user_id)
    return ConversationHandler.END

# ============ OWNER: ADD ACCOUNT FLOW ============
async def owner_add_number(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    # Ask channel first
    text = "📥 *Add Account* — Choose channel:\n\nWhere should this account be listed?"
    keyboard = [
        [InlineKeyboardButton("📱 Buy Channel", callback_data="addacc_ch_buy")],
        [InlineKeyboardButton("♻️ Resale Channel", callback_data="addacc_ch_resale")],
        [InlineKeyboardButton("🔙 Back", callback_data="owner_panel")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_ADDACC_CHANNEL)
    return WAITING_FOR_ADDACC_CHANNEL

async def addacc_pick_channel(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    channel = "buy" if query.data == "addacc_ch_buy" else "resale"
    set_user_state(user_id, WAITING_FOR_COUNTRY, {"channel": channel})
    label = "Buy" if channel == "buy" else "Resale"
    await query.edit_message_text(
        f"➕ *Add Account* ({label})\n\n🌍 Enter country name (e.g. `India`, `USA 2024`, `Japan (Fresh)`):",
        parse_mode='Markdown'
    )
    return WAITING_FOR_COUNTRY

async def addaccount_cmd(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return
    text = "📥 *Add Account* — Choose channel:"
    keyboard = [
        [InlineKeyboardButton("📱 Buy Channel", callback_data="addacc_ch_buy")],
        [InlineKeyboardButton("♻️ Resale Channel", callback_data="addacc_ch_resale")],
        [InlineKeyboardButton("🔙 Back", callback_data="owner_panel")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_country_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    country = update.message.text.strip()
    if len(country) < 2 or len(country) > 40:
        await update.message.reply_text("❌ Country name 2-40 chars.")
        return WAITING_FOR_COUNTRY
    st = get_user_state(user_id)
    st["data"]["country"] = country
    set_user_state(user_id, WAITING_FOR_PRICE, st["data"])
    await update.message.reply_text("💰 Enter price per account (INR):", parse_mode='Markdown')
    return WAITING_FOR_PRICE

async def handle_price_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    try:
        price = int(update.message.text.strip())
        if price <= 0:
            await update.message.reply_text("❌ Must be > 0.")
            return WAITING_FOR_PRICE
        st = get_user_state(user_id)
        st["data"]["price"] = price
        set_user_state(user_id, WAITING_FOR_SESSION, st["data"])
        await update.message.reply_text(
            "🔑 Send *session string* (Pyrogram string session):\n\n"
            "Send one session per message. After adding, you'll be asked to add more or finish.",
            parse_mode='Markdown'
        )
        return WAITING_FOR_SESSION
    except ValueError:
        await update.message.reply_text("❌ Numbers only.")
        return WAITING_FOR_PRICE

async def handle_session_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    session = update.message.text.strip()
    if len(session) < 50:
        await update.message.reply_text("❌ Session string too short. Send valid session.")
        return WAITING_FOR_SESSION
    st = get_user_state(user_id)
    st["data"]["session"] = session
    set_user_state(user_id, WAITING_FOR_2FA, st["data"])
    await update.message.reply_text(
        "🔐 Send *2FA password* for this session, or send `none` if not set:",
        parse_mode='Markdown'
    )
    return WAITING_FOR_2FA

async def handle_2fa_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    twofa_raw = update.message.text.strip()
    twofa = None if twofa_raw.lower() in ("none", "no", "-", "n/a") else twofa_raw
    st = get_user_state(user_id)
    d = st["data"]
    channel = d.get("channel", "buy")
    country = d["country"]
    price = d["price"]
    session_str = d["session"]

    ch = _channel_dict(channel)
    if country not in ch:
        ch[country] = {"price": price, "quantity": 0, "sessions": []}
    ch[country]["price"] = price  # allow price update
    ch[country]["sessions"].append({"session": session_str, "twofa": twofa, "phone_number": "N/A"})
    ch[country]["quantity"] = len(ch[country]["sessions"])
    save_data(data)

    # Try to fetch phone number instantly
    phone = "N/A"
    try:
        c = await create_client(session_str, f"add_{user_id}")
        if c:
            phone = await get_phone_number(c)
            try:
                await c.stop()
            except:
                pass
            # save phone number
            ch[country]["sessions"][-1]["phone_number"] = phone
            save_data(data)
    except Exception as e:
        logger.error(f"[ADD PHONE FETCH] {e}")

    await log_session_added(context, country, 1, price, phone, twofa, channel=channel)

    keyboard = [
        [InlineKeyboardButton("➕ Add More", callback_data="addmore_yes"),
         InlineKeyboardButton("✅ Done", callback_data="addmore_no")]
    ]
    label = "Buy" if channel == "buy" else "Resale"
    await update.message.reply_text(
        f"✅ *Added to {label}*\n\n"
        f"🌍 {country.upper()}\n"
        f"📱 Phone: `{phone}`\n"
        f"💰 ₹{price}.00\n"
        f"📦 Stock now: {ch[country]['quantity']}\n\n"
        f"Add another session for the same country?",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_ADD_MORE_SESSIONS, st["data"])
    return WAITING_FOR_ADD_MORE_SESSIONS

async def handle_add_more_choice(update, context):
    """Fallback for text-based yes/no."""
    user_id = update.effective_user.id
    txt = update.message.text.strip().lower()
    if txt in ("yes", "y", "add"):
        st = get_user_state(user_id)
        set_user_state(user_id, WAITING_FOR_SESSION, st["data"])
        await update.message.reply_text("🔑 Send next session string:", parse_mode='Markdown')
        return WAITING_FOR_SESSION
    else:
        clear_user_state(user_id)
        await update.message.reply_text("✅ Done adding sessions.", parse_mode='Markdown')
        return ConversationHandler.END

async def addmore_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    if query.data == "addmore_yes":
        st = get_user_state(user_id)
        set_user_state(user_id, WAITING_FOR_SESSION, st["data"])
        await query.edit_message_text("🔑 Send next session string:", parse_mode='Markdown')
    else:
        clear_user_state(user_id)
        await query.edit_message_text(
            "✅ Done adding sessions.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
            parse_mode='Markdown'
        )

# ============ OWNER: DELETE COUNTRY ============
async def owner_delete_country(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    keyboard = []
    for c, info in data["accounts"].items():
        keyboard.append([InlineKeyboardButton(f"📱 BUY {c} ({info['quantity']})",
                                              callback_data=f"delete_confirm_buy_{c}")])
    for c, info in data.get("resale_accounts", {}).items():
        keyboard.append([InlineKeyboardButton(f"♻️ RESALE {c} ({info['quantity']})",
                                              callback_data=f"delete_confirm_resale_{c}")])
    if not keyboard:
        await query.edit_message_text(
            "📭 No countries to delete.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
            parse_mode='Markdown'
        )
        return
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="owner_panel")])
    await query.edit_message_text("🗑 *Select country to delete:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def confirm_delete_country(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split("_")
    channel = parts[2]
    country = "_".join(parts[3:])
    if not is_owner(user_id):
        return
    ch = _channel_dict(channel)
    if country in ch:
        q = ch[country]["quantity"]
        p = ch[country]["price"]
        await log_country_deleted(context, country, q, p, channel=channel)
        del ch[country]
        save_data(data)
        text = f"✅ Deleted from {channel.upper()}: `{country}`"
    else:
        text = "❌ Not found."
    await query.edit_message_text(text,
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
                                  parse_mode='Markdown')

# ============ SET BOT PHOTO ============
async def set_bot_photo(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    if update.callback_query:
        await update.callback_query.edit_message_text("📸 Send bot picture:", parse_mode='Markdown')
    else:
        await update.message.reply_text("📸 Send bot picture:", parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_BOT_PHOTO)
    return WAITING_FOR_BOT_PHOTO

async def handle_photo_owner(update, context):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if state["state"] == WAITING_FOR_SCREENSHOT:
        return await handle_screenshot(update, context)
    if state["state"] != WAITING_FOR_BOT_PHOTO or not is_owner(user_id):
        return ConversationHandler.END
    photo = update.message.photo[-1]
    data["bot_photo"] = photo.file_id
    save_data(data)
    await update.message.reply_text("✅ Bot photo updated!", parse_mode='Markdown')
    clear_user_state(user_id)
    return ConversationHandler.END

# ============ TRANSFER ============
async def transfer_cmd(update, context):
    user_id = update.effective_user.id
    args = context.args
    if len(args) == 2:
        try:
            target_id = int(args[0])
            amount = int(args[1])
        except:
            await update.message.reply_text("❌ Usage: /transfer <user_id> <amount>")
            return
        await _do_transfer(update, context, user_id, target_id, amount)
        return
    set_user_state(user_id, WAITING_FOR_TRANSFER_USER)
    await update.message.reply_text("🔁 *Transfer Balance*\n\nEnter target user ID:", parse_mode='Markdown')

async def handle_transfer_user(update, context):
    user_id = update.effective_user.id
    try:
        target_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Numbers only.")
        return WAITING_FOR_TRANSFER_USER
    if target_id == user_id:
        await update.message.reply_text("❌ Can't transfer to yourself.")
        clear_user_state(user_id)
        return ConversationHandler.END
    st = get_user_state(user_id)
    st["data"]["target_id"] = target_id
    set_user_state(user_id, WAITING_FOR_TRANSFER_AMOUNT, st["data"])
    await update.message.reply_text("💰 Enter amount to transfer:", parse_mode='Markdown')
    return WAITING_FOR_TRANSFER_AMOUNT

async def handle_transfer_amount(update, context):
    user_id = update.effective_user.id
    try:
        amount = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Numbers only.")
        return WAITING_FOR_TRANSFER_AMOUNT
    st = get_user_state(user_id)
    target_id = st["data"]["target_id"]
    await _do_transfer(update, context, user_id, target_id, amount)
    clear_user_state(user_id)
    return ConversationHandler.END

async def _do_transfer(update, context, user_id, target_id, amount):
    u = get_user_data(user_id)
    bal = int(u.get("balance", 0))
    if amount <= 0:
        await update.message.reply_text("❌ Amount must be > 0.")
        return
    if amount > bal:
        await update.message.reply_text(f"❌ You only have ₹{bal}. Can't send ₹{amount}.")
        return
    # ensure target exists
    if str(target_id) not in data["users"]:
        data["users"][str(target_id)] = {"balance": 0, "purchases": [], "username": f"User_{target_id}"}

    data["users"][str(user_id)]["balance"] -= amount
    data["users"][str(target_id)]["balance"] = data["users"][str(target_id)].get("balance", 0) + amount
    save_data(data)

    from_after = data["users"][str(user_id)]["balance"]
    to_after = data["users"][str(target_id)]["balance"]
    username = data["users"][str(user_id)].get("username", f"User_{user_id}")
    await log_transfer(context, user_id, username, target_id, amount, from_after, to_after)

    await update.message.reply_text(
        f"✅ Transferred ₹{amount}.00 to `{target_id}`.\n💳 Your new balance: ₹{from_after}.00",
        parse_mode='Markdown'
    )
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(f"💰 *Balance Received!*\n\n"
                  f"👤 From: `{user_id}`\n"
                  f"💵 Amount: ₹{amount}.00\n"
                  f"💳 New Balance: ₹{to_after}.00"),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"[TRANSFER NOTIFY] {e}")

# ============ OWNER PANEL ============
async def owner_panel(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        if update.message:
            await update.message.reply_text("❌ Unauthorized!", parse_mode='Markdown')
        return
    text = """
👑 *OWNER PANEL*

Manage your bot from here:
"""
    keyboard = [
        [InlineKeyboardButton("➕ Add Account", callback_data="owner_addnumber"),
         InlineKeyboardButton("🗑 Delete Country", callback_data="owner_delete")],
        [InlineKeyboardButton("💳 Pending Payments", callback_data="owner_payments"),
         InlineKeyboardButton("📊 Stats", callback_data="owner_stats")],
        [InlineKeyboardButton("🏷 Create Discount", callback_data="owner_discount"),
         InlineKeyboardButton("🎟 Create Coupon", callback_data="owner_coupon")],
        [InlineKeyboardButton("📣 Broadcast", callback_data="owner_broadcast"),
         InlineKeyboardButton("💰 User Balances", callback_data="owner_userbal")],
        [InlineKeyboardButton("🖼 Set Bot DP", callback_data="owner_setdp")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ /add /deduct ============
async def owner_add_command(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized!", parse_mode='Markdown')
        return
    args = context.args
    if len(args) == 2:
        try:
            target_user_id = int(args[0])
            amount = int(args[1])
            if amount <= 0:
                await update.message.reply_text("❌ Amount must be > 0!")
                return
            if str(target_user_id) not in data["users"]:
                data["users"][str(target_user_id)] = {"balance": 0, "purchases": [], "username": f"User_{target_user_id}"}
            before = data["users"][str(target_user_id)]["balance"]
            data["users"][str(target_user_id)]["balance"] += amount
            after = data["users"][str(target_user_id)]["balance"]
            save_data(data)
            await log_owner_balance_change(context, "ADD", target_user_id, amount, before, after, user_id)
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"➕ *Balance Update*\n\n💰 ₹{amount}.00 added.\n💳 New: ₹{after}.00",
                    parse_mode='Markdown'
                )
            except:
                pass
            await update.message.reply_text(
                f"✅ Added ₹{amount} to `{target_user_id}` — new ₹{after}.",
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text("❌ Usage: /add <user_id> <amount>")
        return
    if len(args) == 1:
        try:
            target_user_id = int(args[0])
        except:
            await update.message.reply_text("❌ Usage: /add <user_id> [amount]")
            return
        if str(target_user_id) not in data["users"]:
            data["users"][str(target_user_id)] = {"balance": 0, "purchases": [], "username": f"User_{target_user_id}"}
        cur_bal = data["users"][str(target_user_id)]["balance"]
        set_user_state(user_id, WAITING_FOR_ADDBAL_AMOUNT, {"target_user_id": target_user_id})
        await update.message.reply_text(
            f"👤 Target: `{target_user_id}`\n"
            f"💳 Current balance: ₹{cur_bal}.00\n\n"
            f"💰 Enter amount to add:",
            parse_mode='Markdown'
        )
        return
    set_user_state(user_id, WAITING_FOR_TARGET_USER_ID, {"action": "add"})
    await update.message.reply_text("➕ Send target user ID:", parse_mode='Markdown')

async def owner_deduct_command(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized!", parse_mode='Markdown')
        return
    args = context.args
    if len(args) == 2:
        try:
            target_user_id = int(args[0])
            amount = int(args[1])
            if amount <= 0:
                await update.message.reply_text("❌ Amount must be > 0!")
                return
            if str(target_user_id) not in data["users"]:
                await update.message.reply_text("❌ User not found!")
                return
            before = data["users"][str(target_user_id)]["balance"]
            if amount > before:
                await update.message.reply_text(f"❌ User has only ₹{before}.")
                return
            data["users"][str(target_user_id)]["balance"] -= amount
            after = data["users"][str(target_user_id)]["balance"]
            save_data(data)
            await log_owner_balance_change(context, "DEDUCT", target_user_id, amount, before, after, user_id)
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"➖ *Balance Update*\n\n💰 ₹{amount}.00 deducted.\n💳 New: ₹{after}.00",
                    parse_mode='Markdown'
                )
            except:
                pass
            await update.message.reply_text(
                f"✅ Deducted ₹{amount} from `{target_user_id}` — new ₹{after}.",
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text("❌ Usage: /deduct <user_id> <amount>")
    else:
        set_user_state(user_id, WAITING_FOR_TARGET_USER_ID, {"action": "deduct"})
        await update.message.reply_text("➖ Send target user ID:", parse_mode='Markdown')

async def owner_handle_target_user_id(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    try:
        target_user_id = int(update.message.text.strip())
        if str(target_user_id) not in data["users"]:
            if get_user_state(user_id)["data"].get("action") == "deduct":
                await update.message.reply_text("❌ User not found!")
                clear_user_state(user_id)
                return ConversationHandler.END
            data["users"][str(target_user_id)] = {"balance": 0, "purchases": [], "username": f"User_{target_user_id}"}
            save_data(data)
        st = get_user_state(user_id)
        st["data"]["target_user_id"] = target_user_id
        action = st["data"].get("action", "add")
        cur_bal = data["users"][str(target_user_id)]["balance"]
        if action == "add":
            set_user_state(user_id, WAITING_FOR_ADDBAL_AMOUNT, st["data"])
            await update.message.reply_text(
                f"👤 Target: `{target_user_id}`\n💳 Current: ₹{cur_bal}.00\n\n💰 Enter amount to add:",
                parse_mode='Markdown'
            )
            return WAITING_FOR_ADDBAL_AMOUNT
        else:
            set_user_state(user_id, WAITING_FOR_TARGET_AMOUNT, st["data"])
            await update.message.reply_text(
                f"👤 Target: `{target_user_id}`\n💳 Current: ₹{cur_bal}.00\n\n💰 Enter amount to deduct:",
                parse_mode='Markdown'
            )
            return WAITING_FOR_TARGET_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Numbers only.")
        return WAITING_FOR_TARGET_USER_ID

async def owner_handle_addbal_amount(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    try:
        amount = int(update.message.text.strip())
        st = get_user_state(user_id)
        target_user_id = st["data"]["target_user_id"]
        if amount <= 0:
            await update.message.reply_text("❌ > 0!")
            return WAITING_FOR_ADDBAL_AMOUNT
        before = data["users"][str(target_user_id)]["balance"]
        data["users"][str(target_user_id)]["balance"] += amount
        after = data["users"][str(target_user_id)]["balance"]
        save_data(data)
        await log_owner_balance_change(context, "ADD", target_user_id, amount, before, after, user_id)
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"➕ *Balance Update*\n\n💰 ₹{amount}.00 added.\n💳 New Balance: ₹{after}.00",
                parse_mode='Markdown'
            )
        except:
            pass
        await update.message.reply_text(
            f"✅ Added ₹{amount} to `{target_user_id}`\n📉 Before: ₹{before}\n📈 After: ₹{after}",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Numbers only.")
        return WAITING_FOR_ADDBAL_AMOUNT

async def owner_handle_target_amount(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    try:
        amount = int(update.message.text.strip())
        st = get_user_state(user_id)
        target_user_id = st["data"]["target_user_id"]
        before = data["users"][str(target_user_id)]["balance"]
        if amount <= 0:
            await update.message.reply_text("❌ > 0!")
            return WAITING_FOR_TARGET_AMOUNT
        if amount > before:
            await update.message.reply_text(f"❌ User has only ₹{before}.00")
            return WAITING_FOR_TARGET_AMOUNT
        data["users"][str(target_user_id)]["balance"] -= amount
        after = data["users"][str(target_user_id)]["balance"]
        save_data(data)
        await log_owner_balance_change(context, "DEDUCT", target_user_id, amount, before, after, user_id)
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"➖ *Balance Update*\n\n💰 ₹{amount}.00 deducted.\n💳 New Balance: ₹{after}.00",
                parse_mode='Markdown'
            )
        except:
            pass
        await update.message.reply_text(
            f"✅ Deducted ₹{amount} from `{target_user_id}`\n📉 Before: ₹{before}\n📈 After: ₹{after}",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Numbers only.")
        return WAITING_FOR_TARGET_AMOUNT

# ============ DISCOUNT / COUPON CREATE ============
async def create_discount(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    await query.edit_message_text("🏷 *Create Discount*\n\n📝 Enter discount amount (INR):", parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_DISCOUNT_AMOUNT)
    return WAITING_FOR_DISCOUNT_AMOUNT

async def handle_discount_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    try:
        discount = int(update.message.text.strip())
        if discount <= 0:
            await update.message.reply_text("❌ > 0!")
            return WAITING_FOR_DISCOUNT_AMOUNT
        discount_code = generate_random_code("DSC", 10)
        data["discount_codes"][discount_code] = {"discount": discount, "created": datetime.now().isoformat()}
        save_data(data)
        await log_discount_created(context, discount_code, discount)
        await update.message.reply_text(
            f"✅ *Discount Created!*\n\n🎟 Code: `{discount_code}`\n💰 Discount: ₹{discount}.00",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Numbers only.")
        return WAITING_FOR_DISCOUNT_AMOUNT

async def create_coupon(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    await query.edit_message_text("🎟 *Create Coupon*\n\n📝 Enter coupon amount (INR):", parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_COUPON_AMOUNT)
    return WAITING_FOR_COUPON_AMOUNT

async def handle_coupon_input_owner(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            await update.message.reply_text("❌ > 0!")
            return WAITING_FOR_COUPON_AMOUNT
        coupon_code = generate_random_code("CPN", 12)
        data["coupons"][coupon_code] = {"amount": amount, "used": False, "created": datetime.now().isoformat()}
        save_data(data)
        await update.message.reply_text(
            f"✅ *Coupon Created!*\n\n🎫 Code: `{coupon_code}`\n💰 Amount: ₹{amount}.00",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Numbers only.")
        return WAITING_FOR_COUPON_AMOUNT

# ============ BROADCAST ============
async def broadcast_start(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    await query.edit_message_text(
        f"📣 *Broadcast Message*\n\n👥 Total Users: {len(data['users'])}\n\n📝 Type your message:",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_BROADCAST_MESSAGE)
    return WAITING_FOR_BROADCAST_MESSAGE

async def handle_broadcast_message(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    broadcast_message = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("✅ SEND", callback_data="broadcast_confirm")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="owner_panel")]
    ]
    await update.message.reply_text(
        f"📣 *Preview:*\n\n{broadcast_message[:800]}\n\n👥 Send to {len(data['users'])} users?",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_BROADCAST_MESSAGE, {"message": broadcast_message})
    return ConversationHandler.END

async def broadcast_confirm(update, context):
    query = update.callback_query
    await query.answer("📤 Sending...")
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    state = get_user_state(user_id)
    broadcast_message = state["data"].get("message", "")
    if not broadcast_message:
        await query.edit_message_text("❌ No message found!", parse_mode='Markdown')
        return
    total_users = len(data['users'])
    success_count = 0
    failed_count = 0
    await query.edit_message_text(f"📤 Broadcasting to {total_users} users...", parse_mode='Markdown')
    for user_id_str in list(data['users'].keys()):
        try:
            target_user_id = int(user_id_str)
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"📣 *Broadcast*\n\n{broadcast_message}",
                parse_mode='Markdown'
            )
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed_count += 1
    await log_broadcast_sent(context, total_users, success_count, failed_count)
    await query.edit_message_text(
        f"✅ *Broadcast Complete!*\n\n✅ Sent: {success_count}\n❌ Failed: {failed_count}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
        parse_mode='Markdown'
    )
    clear_user_state(user_id)

# ============ REVIEW / APPROVE / REJECT PAYMENT ============
async def review_payment(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    payment_user_id = int(query.data.split("_")[2])
    if not is_owner(user_id):
        return
    if str(payment_user_id) not in data["pending_payments"]:
        await query.answer("❌ Payment not found!", show_alert=True)
        return
    payment_info = data["pending_payments"][str(payment_user_id)]
    username = data["users"].get(str(payment_user_id), {}).get("username", f"User_{payment_user_id}")
    safe_username = escape_markdown(username)
    utr = payment_info.get("utr", "N/A")
    id_type = (payment_info.get("id_type") or "ID").upper()
    text = f"""
💳 *Payment Review*

👤 User: {safe_username}
🆔 ID: `{payment_user_id}`
💰 Amount: ₹{payment_info['amount']}.00
🔢 {id_type}: `{escape_markdown(str(utr))}`
    """
    keyboard = [
        [InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_fund_{payment_user_id}"),
         InlineKeyboardButton("❌ REJECT", callback_data=f"reject_fund_{payment_user_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="owner_payments")]
    ]
    try:
        await context.bot.send_photo(
            chat_id=user_id, photo=payment_info["photo_id"],
            caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
        )
        await query.message.delete()
    except:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def approve_fund(update, context):
    query = update.callback_query
    await query.answer("✅ Approving...")
    user_id = update.effective_user.id
    target_user_id = int(query.data.split("_")[2])
    if not is_owner(user_id):
        return
    if str(target_user_id) not in data["pending_payments"]:
        await query.answer("❌ Payment not found!", show_alert=True)
        return
    payment_info = data["pending_payments"][str(target_user_id)]
    if payment_info.get("status") not in ("submitted", "manual_review", "awaiting_utr", "verifying"):
        await query.answer("⚠️ Already processed!", show_alert=True)
        return
    amount = payment_info["amount"]
    username = data["users"].get(str(target_user_id), {}).get("username", f"User_{target_user_id}")
    utr = payment_info.get("utr", "")
    paired_txn = payment_info.get("paired_txn")
    paired_utr = payment_info.get("paired_utr")

    data["users"][str(target_user_id)]["balance"] += amount
    data["pending_payments"][str(target_user_id)]["status"] = "approved"
    if utr:
        mark_utr_used(utr, target_user_id, amount, mode="manual")
    if paired_txn:
        mark_utr_used(paired_txn, target_user_id, amount, mode="manual_paired")
    if paired_utr:
        mark_utr_used(paired_utr, target_user_id, amount, mode="manual_paired")
    save_data(data)

    await log_payment_approved(context, target_user_id, username, amount, mode="MANUAL")
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"✅ *Payment Approved!*\n\n💰 Amount: ₹{amount}.00\n"
                 f"💳 New Balance: ₹{data['users'][str(target_user_id)]['balance']}.00",
            parse_mode='Markdown'
        )
    except:
        pass
    try:
        await query.edit_message_caption(
            caption=f"✅ Approved!\n\n👤 `{target_user_id}`\n💰 ₹{amount}.00",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
            parse_mode='Markdown'
        )
    except:
        try:
            await query.edit_message_text(
                f"✅ Approved! `{target_user_id}` — ₹{amount}.00",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
                parse_mode='Markdown'
            )
        except:
            pass

async def reject_fund(update, context):
    query = update.callback_query
    await query.answer("❌ Rejecting...")
    user_id = update.effective_user.id
    target_user_id = int(query.data.split("_")[2])
    if not is_owner(user_id):
        return
    if str(target_user_id) not in data["pending_payments"]:
        await query.answer("❌ Payment not found!", show_alert=True)
        return
    payment_info = data["pending_payments"][str(target_user_id)]
    amount = payment_info["amount"]
    username = data["users"].get(str(target_user_id), {}).get("username", f"User_{target_user_id}")
    data["pending_payments"][str(target_user_id)]["status"] = "rejected"
    save_data(data)
    await log_payment_rejected(context, target_user_id, username, amount, "Manual reject by owner")
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"❌ *Payment Rejected!*\n\n💰 ₹{amount}.00\n📝 Reason: Invalid payment\n\n💡 Contact: @{OWNER_TG_USERNAME}",
            parse_mode='Markdown'
        )
    except:
        pass
    try:
        await query.edit_message_caption(
            caption=f"❌ Rejected!\n\n👤 `{target_user_id}`\n💰 ₹{amount}.00",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
            parse_mode='Markdown'
        )
    except:
        try:
            await query.edit_message_text(
                f"❌ Rejected! `{target_user_id}` — ₹{amount}.00",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
                parse_mode='Markdown'
            )
        except:
            pass

# ============ OWNER LISTS ============
async def owner_user_balance_list(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    users_with_balance = []
    for uid, u in data["users"].items():
        bal = u.get("balance", 0)
        if bal >= 1:
            users_with_balance.append({"user_id": uid, "username": u.get("username", f"User_{uid}"), "balance": bal})
    if not users_with_balance:
        await query.edit_message_text(
            "📭 No users with balance ≥ ₹1",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
            parse_mode='Markdown'
        )
        return
    users_with_balance.sort(key=lambda x: x["balance"], reverse=True)
    text = f"💰 *Users with Balance ≥ ₹1*\n\nTotal: {len(users_with_balance)}\n\n"
    for u in users_with_balance[:50]:
        text += f"• `{u['user_id']}` — {escape_markdown(u['username'])}: ₹{u['balance']}.00\n"
    if len(users_with_balance) > 50:
        text += f"\n... and {len(users_with_balance) - 50} more"
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
        parse_mode='Markdown'
    )

async def owner_view_payments(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    pending = {
        uid: info for uid, info in data["pending_payments"].items()
        if info.get("status") in ("submitted", "manual_review", "verifying", "awaiting_utr")
    }
    if not pending:
        await query.edit_message_text(
            "📭 No pending payments!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
            parse_mode='Markdown'
        )
        return
    text = "💳 *Pending Payments*\n\n"
    keyboard = []
    for pid, info in list(pending.items())[:5]:
        username = data["users"].get(str(pid), {}).get("username", f"User_{pid}")
        text += f"👤 {escape_markdown(username)}\n💰 ₹{info['amount']}\n\n"
        keyboard.append([InlineKeyboardButton(f"🔍 {username[:15]} — ₹{info['amount']}", callback_data=f"review_payment_{pid}")])
    keyboard.append([InlineKeyboardButton("👑 Panel", callback_data="owner_panel")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def owner_stats(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    total_users = len(data["users"])
    total_balance = sum(u["balance"] for u in data["users"].values())
    total_revenue = sum(
        p["price"] for u in data["users"].values()
        for p in u["purchases"] if p.get("status") == "completed"
    )
    buy_stock = sum(i["quantity"] for i in data["accounts"].values())
    resale_stock = sum(i["quantity"] for i in data.get("resale_accounts", {}).values())
    text = f"""
📊 *Bot Statistics*

👥 Users: {total_users}
💰 User Balance: ₹{total_balance}.00
💵 Revenue: ₹{total_revenue}.00

📱 Buy Stock: {buy_stock}
♻️ Resale Stock: {resale_stock}

🤖 AI in groups: {"ON ✅" if data.get("ai_enabled", True) else "OFF ❌"}
"""
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👑 Panel", callback_data="owner_panel")]]),
        parse_mode='Markdown'
    )

# ============ SERVER 2 (Services Marketplace) ============
async def server2_home(update, context):
    query = update.callback_query
    await query.answer()
    text = f"""
🛒 *Services Marketplace*

Browse or list your own services.

💡 Listing fee: ₹{SERVICE_ADD_FEE}
"""
    keyboard = [
        [InlineKeyboardButton("📋 Available Services", callback_data="srv2_available")],
        [InlineKeyboardButton("➕ Add My Service", callback_data="srv2_add_start")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def srv2_available(update, context):
    query = update.callback_query
    await query.answer()
    services = data.get("services", {})
    if not services:
        await query.edit_message_text(
            "📭 No services listed yet.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="server2_home")]]),
            parse_mode='Markdown'
        )
        return
    text = "📋 *Available Services*\n\n"
    keyboard = []
    for sid, s in list(services.items())[:15]:
        text += f"• {escape_markdown(s['name'])} — ₹{s['price']}\n"
        keyboard.append([InlineKeyboardButton(f"{s['name'][:20]} — ₹{s['price']}", callback_data=f"srv2_view_{sid}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="server2_home")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def srv2_view_service(update, context):
    query = update.callback_query
    await query.answer()
    sid = query.data.replace("srv2_view_", "")
    s = data.get("services", {}).get(sid)
    if not s:
        await query.edit_message_text("❌ Not found.", parse_mode='Markdown')
        return
    text = (
        f"🛒 *{escape_markdown(s['name'])}*\n\n"
        f"💰 Price: ₹{s['price']}\n"
        f"👤 Seller: {escape_markdown(s.get('contact', 'N/A'))}\n\n"
        f"📝 {escape_markdown(s.get('desc', ''))}"
    )
    keyboard = [
        [InlineKeyboardButton("💬 Contact Seller", url=f"https://t.me/{s.get('contact', '').lstrip('@')}")],
        [InlineKeyboardButton("🔙 Back", callback_data="srv2_available")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def srv2_buy_service(update, context):
    query = update.callback_query
    await query.answer("Contact seller directly.", show_alert=True)

async def srv2_add_start(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    u = get_user_data(user_id)
    if u.get("balance", 0) < SERVICE_ADD_FEE:
        await query.edit_message_text(
            f"❌ Need ₹{SERVICE_ADD_FEE} to list a service.\n💳 You have: ₹{u.get('balance', 0)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Funds", callback_data="add_funds")],
                [InlineKeyboardButton("🔙 Back", callback_data="server2_home")]
            ]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    set_user_state(user_id, WAITING_SERVICE_NAME, {})
    await query.edit_message_text(
        f"➕ *Add Service* (fee ₹{SERVICE_ADD_FEE})\n\n📝 Step 1/4: Send service name (2-60 chars):",
        parse_mode='Markdown'
    )
    return WAITING_SERVICE_NAME

def normalize_username(u):
    u = u.strip()
    if not u:
        return ""
    if u.startswith("http"):
        u = u.rsplit("/", 1)[-1]
    if not u.startswith("@"):
        u = "@" + u
    return u

async def srv2_service_name_input(update, context):
    user_id = update.effective_user.id
    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 60:
        await update.message.reply_text("❌ Name 2-60 chars. Try again.")
        return WAITING_SERVICE_NAME
    st = get_user_state(user_id)
    st["data"]["name"] = name
    set_user_state(user_id, WAITING_SERVICE_PRICE, st["data"])
    await update.message.reply_text("📝 Step 2/4: Send price in INR (number only).", parse_mode='Markdown')
    return WAITING_SERVICE_PRICE

async def srv2_service_price_input(update, context):
    user_id = update.effective_user.id
    try:
        price = int(update.message.text.strip())
        if price <= 0:
            raise ValueError()
    except:
        await update.message.reply_text("❌ Price must be integer > 0.")
        return WAITING_SERVICE_PRICE
    st = get_user_state(user_id)
    st["data"]["price"] = price
    set_user_state(user_id, WAITING_SERVICE_CONTACT, st["data"])
    await update.message.reply_text("📝 Step 3/4: Send your Telegram username (e.g. @yourname).", parse_mode='Markdown')
    return WAITING_SERVICE_CONTACT

async def srv2_service_contact_input(update, context):
    user_id = update.effective_user.id
    contact = normalize_username(update.message.text.strip())
    if not contact or len(contact) < 3:
        await update.message.reply_text("❌ Invalid username.")
        return WAITING_SERVICE_CONTACT
    st = get_user_state(user_id)
    st["data"]["contact"] = contact
    set_user_state(user_id, WAITING_SERVICE_DESC, st["data"])
    await update.message.reply_text("📝 Step 4/4: Send description (10-400 chars):", parse_mode='Markdown')
    return WAITING_SERVICE_DESC

async def srv2_service_desc_input(update, context):
    user_id = update.effective_user.id
    desc = update.message.text.strip()
    if len(desc) < 10 or len(desc) > 400:
        await update.message.reply_text("❌ Description 10-400 chars. Try again.")
        return WAITING_SERVICE_DESC
    st = get_user_state(user_id)
    sd = st["data"]

    u = get_user_data(user_id)
    bal = int(u.get("balance", 0))
    if bal < SERVICE_ADD_FEE:
        await update.message.reply_text("❌ Not enough balance for the listing fee anymore.")
        clear_user_state(user_id)
        return ConversationHandler.END
    data["users"][str(user_id)]["balance"] -= SERVICE_ADD_FEE
    data["service_seq"] = data.get("service_seq", 0) + 1
    sid = f"S{data['service_seq']:05d}"
    data["services"][sid] = {
        "id": sid,
        "owner_id": user_id,
        "name": sd["name"],
        "price": sd["price"],
        "contact": sd["contact"],
        "desc": desc,
        "created": datetime.now().isoformat()
    }
    save_data(data)
    await update.message.reply_text(
        f"✅ *Service Listed!*\n\n"
        f"🆔 `{sid}`\n"
        f"📛 {escape_markdown(sd['name'])}\n"
        f"💰 ₹{sd['price']}\n\n"
        f"Listing fee ₹{SERVICE_ADD_FEE} deducted.",
        parse_mode='Markdown'
    )
    clear_user_state(user_id)
    return ConversationHandler.END

async def myservice_cmd(update, context):
    user_id = update.effective_user.id
    services = [s for s in data.get("services", {}).values() if s.get("owner_id") == user_id]
    if not services:
        await update.message.reply_text("📭 You have no services listed.")
        return
    text = "🛒 *Your Services*\n\n"
    keyboard = []
    for s in services:
        text += f"• `{s['id']}` — {escape_markdown(s['name'])} — ₹{s['price']}\n"
        keyboard.append([InlineKeyboardButton(f"❌ Delete {s['id']}", callback_data=f"serv_del_{s['id']}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def allservices_cmd(update, context):
    services = data.get("services", {})
    if not services:
        await update.message.reply_text("📭 No services listed.")
        return
    text = "📋 *All Services*\n\n"
    for s in list(services.values())[:30]:
        text += f"• `{s['id']}` — {escape_markdown(s['name'])} — ₹{s['price']} — {escape_markdown(s.get('contact', ''))}\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def myserv_view(update, context):
    await update.callback_query.answer()

async def ownserv_view(update, context):
    await update.callback_query.answer()

async def serv_delete(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    sid = query.data.replace("serv_del_", "")
    s = data.get("services", {}).get(sid)
    if not s:
        await query.answer("Not found", show_alert=True)
        return
    if s.get("owner_id") != user_id and not is_owner(user_id):
        await query.answer("Not yours", show_alert=True)
        return
    del data["services"][sid]
    save_data(data)
    await query.edit_message_text(f"✅ Deleted `{sid}`", parse_mode='Markdown')

# ============ 🤖 AI (GROUPS) — FULL BOT ACCESS ============
async def ai_toggle(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("Unauthorized.")
        return
    args = context.args
    if not args:
        await update.message.reply_text(f"AI is currently {'ON' if data.get('ai_enabled', True) else 'OFF'}. Use /ai on or /ai off.")
        return
    val = args[0].strip().lower()
    if val == "on":
        data["ai_enabled"] = True
        save_data(data)
        await update.message.reply_text("AI turned ON for groups.")
    elif val == "off":
        data["ai_enabled"] = False
        save_data(data)
        await update.message.reply_text("AI turned OFF for groups.")
    else:
        await update.message.reply_text("Use /ai on or /ai off.")

def _ai_memory_get(user_id):
    mem = data.get("ai_memory", {})
    if not isinstance(mem, dict):
        data["ai_memory"] = {}
        mem = data["ai_memory"]
    entry = mem.get(str(user_id))
    if not entry or not isinstance(entry, dict):
        entry = {"history": []}
        mem[str(user_id)] = entry
    return entry

def _ai_memory_append(user_id, role, content):
    entry = _ai_memory_get(user_id)
    entry.setdefault("history", []).append({"role": role, "content": content, "ts": datetime.now().isoformat()})
    entry["history"] = entry["history"][-20:]  # keep last 20 turns
    data["ai_memory"][str(user_id)] = entry
    save_data(data)

def _build_full_bot_snapshot(user_id):
    """Give AI FULL knowledge of the bot: stock, sales, revenue, this user's data."""
    u = data["users"].get(str(user_id), {})
    purchases = u.get("purchases", [])
    last_purchases = []
    for p in purchases[-5:]:
        last_purchases.append({
            "country": p.get("country"),
            "quantity": p.get("quantity"),
            "price": p.get("price"),
            "channel": p.get("channel", "buy"),
            "date": p.get("date")
        })
    pending = data.get("pending_payments", {}).get(str(user_id))
    pending_summary = None
    if pending:
        pending_summary = {
            "amount": pending.get("amount"),
            "status": pending.get("status"),
            "utr": pending.get("utr"),
            "id_type": pending.get("id_type"),
            "upi_source": pending.get("upi_source"),
            "timestamp": pending.get("timestamp")
        }

    # Buy channel stock summary
    buy_stock = {}
    for c, info in data.get("accounts", {}).items():
        buy_stock[c] = {"stock": info.get("quantity", 0), "price": info.get("price", 0)}
    # Resale channel stock summary
    resale_stock = {}
    for c, info in data.get("resale_accounts", {}).items():
        resale_stock[c] = {"stock": info.get("quantity", 0), "price": info.get("price", 0)}

    # Sales analytics
    sales_log = data.get("sales_log", [])
    country_sales = {}
    total_sold = 0
    total_revenue = 0
    for s in sales_log:
        c = s.get("country", "?")
        qty = s.get("quantity", 0)
        rev = s.get("price", 0)
        total_sold += qty
        total_revenue += rev
        if c not in country_sales:
            country_sales[c] = {"count": 0, "revenue": 0}
        country_sales[c]["count"] += qty
        country_sales[c]["revenue"] += rev

    top_countries = sorted(country_sales.items(), key=lambda x: x[1]["count"], reverse=True)[:5]

    return {
        "you": {
            "user_id": user_id,
            "username": u.get("username", f"User_{user_id}"),
            "balance": u.get("balance", 0),
            "last_purchases": last_purchases,
            "pending_payment": pending_summary
        },
        "bot_inventory": {
            "buy_channel": buy_stock,
            "resale_channel": resale_stock,
            "total_buy_stock": sum(v["stock"] for v in buy_stock.values()),
            "total_resale_stock": sum(v["stock"] for v in resale_stock.values())
        },
        "bot_analytics": {
            "total_users": len(data.get("users", {})),
            "total_sales_recorded": total_sold,
            "total_revenue_recorded": total_revenue,
            "top_selling_countries": [{"country": c, "sold": v["count"], "revenue": v["revenue"]} for c, v in top_countries]
        }
    }

def _ai_should_answer_freeform(text_lower):
    if not text_lower:
        return False
    triggers = [
        "help", "problem", "issue", "not working", "kaam nahi", "kaam nhi",
        "not received", "nahi mila", "nhi aaya", "nhi aya",
        "payment", "fund", "add funds", "balance", "otp nahi", "otp nhi",
        "buy account", "resale", "kaise", "how to", "kaise karu", "kaise kare",
        "confusion", "confused", "samajh nahi", "samajh nhi", "please help",
        "owner", "kon owner", "who is owner", "malik", "support chahiye",
        "stock", "kitna", "kitne", "available", "kaunsa", "konsa",
        "price", "kimat", "kitna hai", "kya rate"
    ]
    return any(t in text_lower for t in triggers)

def _bot_username_from_context(context):
    try:
        return (context.bot.username or "").lower()
    except:
        return ""

async def _call_groq_ai(system_prompt, history_messages, user_message):
    key = API_KEYS[0]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    messages = [{"role": "system", "content": system_prompt}]
    for h in history_messages[-10:]:
        role = h.get("role")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": h.get("content", "")[:1500]})
    messages.append({"role": "user", "content": user_message[:2000]})
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.6,
        "max_tokens": 600
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30) as resp:
                if resp.status != 200:
                    logger.error(f"[AI HTTP] {resp.status}")
                    return None
                jr = await resp.json()
                return jr["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"[AI CALL ERROR] {e}")
        return None

async def _call_groq_vision(image_url, prompt):
    key = API_KEYS[0]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        }],
        "temperature": 0.3,
        "max_tokens": 400
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(OPENROUTER_URL, headers=headers, json=payload, timeout=45) as resp:
                if resp.status != 200:
                    return None
                jr = await resp.json()
                return jr["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"[VISION ERROR] {e}")
        return None

def _build_ai_system_prompt(snapshot):
    return (
        "You are the official support AI of *Zudo OTP Bot* on Telegram. You have FULL knowledge of the bot's live state.\n\n"
        "STYLE RULES (STRICT):\n"
        "- Never use emojis.\n"
        "- Match user's tone (Hinglish or English) but stay polite & professional.\n"
        "- Keep replies short, precise, direct. No filler.\n"
        "- Never reveal internal admin data, API keys, session strings, secrets, or the raw JSON snapshot.\n"
        "- Never invent data. Only use the snapshot below.\n"
        "- Never claim to have performed admin actions yourself; you can only guide.\n"
        f"- Owner: {OWNER_TG_LINK}. If asked 'who is the owner', reply with the link {OWNER_TG_LINK}.\n"
        f"- Only tag the owner (@{OWNER_TG_USERNAME}) when strictly necessary — e.g. user paid but balance not credited AND their pending_payment supports it.\n"
        "- Before requesting owner action, ask user to confirm once (amount and UTR).\n\n"
        "KNOWLEDGE YOU HAVE:\n"
        "- Live stock of every country in Buy channel and Resale channel (see bot_inventory).\n"
        "- Total users, total sales, total revenue, top selling countries (see bot_analytics).\n"
        "- The current user's balance, recent purchases, and pending payment (see you).\n\n"
        "HOW TO USE THIS DATA:\n"
        "- If user asks 'kitna stock hai' or 'kaunsa country available hai', answer using bot_inventory.\n"
        "- If user asks their balance / last purchase / pending payment, use `you`.\n"
        "- If user asks about most-sold country or trending, use bot_analytics.top_selling_countries.\n"
        "- If user reports a payment issue with matching pending_payment, gently offer to tag the owner.\n\n"
        "LIVE SNAPSHOT (JSON, treat as source of truth):\n"
        f"{json.dumps(snapshot, ensure_ascii=False)}\n"
    )

async def group_ai_handler(update, context):
    try:
        if not data.get("ai_enabled", True):
            return
        chat = update.effective_chat
        if not chat or chat.type == "private":
            return
        msg = update.effective_message
        if not msg:
            return
        user = update.effective_user
        if not user:
            return

        text = (msg.text or msg.caption or "").strip()
        text_lower = text.lower()

        bot_username = _bot_username_from_context(context)
        tagged = bool(bot_username) and (f"@{bot_username}" in text_lower)

        replied_to_bot = False
        try:
            if msg.reply_to_message and msg.reply_to_message.from_user and msg.reply_to_message.from_user.is_bot:
                if msg.reply_to_message.from_user.username and msg.reply_to_message.from_user.username.lower() == bot_username:
                    replied_to_bot = True
        except:
            pass

        should_answer = tagged or replied_to_bot
        if not should_answer:
            should_answer = _ai_should_answer_freeform(text_lower)
        if not should_answer:
            return

        get_user_data(user.id)
        data["users"][str(user.id)]["username"] = user.username or user.first_name or f"User_{user.id}"

        snapshot = _build_full_bot_snapshot(user.id)
        entry = _ai_memory_get(user.id)
        system_prompt = _build_ai_system_prompt(snapshot)

        photo_url = None
        try:
            if msg.photo:
                f = await context.bot.get_file(msg.photo[-1].file_id)
                photo_url = f.file_path if f.file_path.startswith("http") else None
                if not photo_url:
                    photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{f.file_path}"
        except Exception as e:
            logger.error(f"[AI PHOTO FETCH] {e}")

        if photo_url and any(k in text_lower for k in ["payment", "utr", "fund", "add", "screenshot", "paisa", "paid", "recharge"]):
            vision_note = await _call_groq_vision(
                photo_url,
                "Look at this UPI payment screenshot. Extract: amount paid (INR), UTR (12 digit) if visible, Transaction ID if visible, "
                "recipient UPI id/name if visible, and payment status (success/failed/pending). Reply as short JSON."
            )
            if vision_note:
                _ai_memory_append(user.id, "user", f"[SCREENSHOT SEEN] {vision_note}\nUser text: {text}")
            else:
                _ai_memory_append(user.id, "user", text or "[user sent screenshot]")
        else:
            _ai_memory_append(user.id, "user", text)

        history = entry.get("history", [])
        reply_text = await _call_groq_ai(system_prompt, history, text if text else "(no text)")
        if not reply_text:
            return

        _ai_memory_append(user.id, "assistant", reply_text)

        try:
            await msg.reply_text(reply_text, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"[AI REPLY SEND] {e}")

    except Exception as e:
        logger.error(f"[AI HANDLER ERROR] {e}")

# ============ GENERIC BUTTON HANDLER ============
async def button_handler(update, context):
    query = update.callback_query
    user_id = update.effective_user.id
    data_str = query.data
    try:
        if data_str in ["coming_soon_refer"]:
            await coming_soon_handler(update, context)
            return
        if data_str == "history_stats":
            await show_history_stats(update, context); return
        if data_str == "verify_join":
            await verify_join_handler(update, context); return

        if not is_owner(user_id) and data_str not in ("verify_join",):
            is_member = await check_user_membership(context, user_id)
            if not is_member:
                await query.answer("⚠️ Join channel & group first!", show_alert=True)
                await show_force_join_message(update, context); return

        # Server 2
        if data_str == "server2_home":
            await server2_home(update, context); return
        if data_str == "srv2_available":
            await srv2_available(update, context); return
        if data_str == "srv2_add_start":
            return await srv2_add_start(update, context)
        if data_str.startswith("srv2_view_"):
            await srv2_view_service(update, context); return
        if data_str.startswith("srv2_buy_"):
            await srv2_buy_service(update, context); return
        if data_str.startswith("serv_del_"):
            await serv_delete(update, context); return

        # Menu
        if data_str == "main_menu":
            await main_menu(update, context); return
        if data_str == "virtual_accounts":
            await show_countries_buy(update, context); return
        if data_str == "resale_accounts":
            await show_countries_resale(update, context); return
        if data_str.startswith("my_balance_"):
            await show_balance(update, context); return
        if data_str == "add_funds":
            await show_add_funds_options(update, context); return
        if data_str == "buy_fund":
            return await ask_fund_amount(update, context)
        if data_str == "coupon_code":
            return await ask_coupon_code(update, context)

        # UPI source selection
        if data_str in ("upisrc_fampay", "upisrc_other"):
            await handle_upi_source(update, context); return
        if data_str == "upisrc_back":
            await handle_upi_source_back(update, context); return

        # Buy channel
        if data_str.startswith("country_"):
            await show_account_details(update, context, channel="buy"); return
        if data_str.startswith("buy_number_"):
            return await process_buy_number(update, context, channel="buy")
        if data_str.startswith("confirm_buy_"):
            await confirm_purchase_buy(update, context); return

        # Resale channel — properly rewrite the callback data
        if data_str.startswith("rcountry_"):
            query.data = "country_" + data_str[len("rcountry_"):]
            await show_account_details(update, context, channel="resale"); return
        if data_str.startswith("rbuy_number_"):
            query.data = "buy_number_" + data_str[len("rbuy_number_"):]
            return await process_buy_number(update, context, channel="resale")
        if data_str.startswith("rconfirm_buy_"):
            query.data = "confirm_buy_" + data_str[len("rconfirm_buy_"):]
            await confirm_purchase_resale(update, context); return

        if data_str.startswith("get_number_"):
            await get_number_handler(update, context); return
        if data_str.startswith("get_otp_"):
            await get_otp_handler(update, context); return
        if data_str.startswith("login_complete_"):
            await login_complete(update, context); return
        if data_str.startswith("logout_session_"):
            await logout_session_handler(update, context); return

        # Owner
        if data_str == "owner_panel":
            await owner_panel(update, context); return
        if data_str == "owner_addnumber":
            return await owner_add_number(update, context)
        if data_str in ("addacc_ch_buy", "addacc_ch_resale"):
            return await addacc_pick_channel(update, context)
        if data_str in ("addmore_yes", "addmore_no"):
            await addmore_callback(update, context); return
        if data_str == "owner_delete":
            await owner_delete_country(update, context); return
        if data_str.startswith("delete_confirm_"):
            await confirm_delete_country(update, context); return
        if data_str == "owner_discount":
            return await create_discount(update, context)
        if data_str == "owner_coupon":
            return await create_coupon(update, context)
        if data_str == "owner_broadcast":
            return await broadcast_start(update, context)
        if data_str == "broadcast_confirm":
            await broadcast_confirm(update, context); return
        if data_str == "owner_payments":
            await owner_view_payments(update, context); return
        if data_str == "owner_stats":
            await owner_stats(update, context); return
        if data_str == "owner_userbal":
            await owner_user_balance_list(update, context); return
        if data_str == "owner_setdp":
            return await set_bot_photo(update, context)
        if data_str.startswith("approve_fund_"):
            await approve_fund(update, context); return
        if data_str.startswith("reject_fund_"):
            await reject_fund(update, context); return
        if data_str.startswith("review_payment_"):
            await review_payment(update, context); return
        if data_str == "discount":
            return await apply_discount(update, context)

        await query.answer("⚠️ Unknown action!", show_alert=True)
    except Exception as e:
        logger.error(f"[BUTTON ERROR] {type(e).__name__}('{str(e)}')")
        try:
            await query.answer("❌ Please try again", show_alert=True)
        except:
            pass

async def error_handler(update, context):
    logger.error(f"Error: {context.error}")

# ============ GLOBAL TEXT FALLBACK ============
async def global_text_fallback(update, context):
    if update.effective_chat and update.effective_chat.type != "private":
        await group_ai_handler(update, context)
        return

    user_id = update.effective_user.id
    st = get_user_state(user_id)
    cs = st["state"]
    if cs == WAITING_FOR_TARGET_USER_ID:
        return await owner_handle_target_user_id(update, context)
    if cs == WAITING_FOR_TARGET_AMOUNT:
        return await owner_handle_target_amount(update, context)
    if cs == WAITING_FOR_ADDBAL_AMOUNT:
        return await owner_handle_addbal_amount(update, context)
    if cs == WAITING_SERVICE_NAME:
        return await srv2_service_name_input(update, context)
    if cs == WAITING_SERVICE_PRICE:
        return await srv2_service_price_input(update, context)
    if cs == WAITING_SERVICE_CONTACT:
        return await srv2_service_contact_input(update, context)
    if cs == WAITING_SERVICE_DESC:
        return await srv2_service_desc_input(update, context)
    if cs == WAITING_FOR_AMOUNT:
        return await handle_amount_input(update, context)
    if cs == WAITING_FOR_UTR:
        return await handle_utr_input(update, context)
    if cs == WAITING_FOR_COUPON:
        return await handle_coupon_input(update, context)
    if cs == WAITING_FOR_COUNTRY:
        return await handle_country_input(update, context)
    if cs == WAITING_FOR_PRICE:
        return await handle_price_input(update, context)
    if cs == WAITING_FOR_SESSION:
        return await handle_session_input(update, context)
    if cs == WAITING_FOR_2FA:
        return await handle_2fa_input(update, context)
    if cs == WAITING_FOR_DISCOUNT_AMOUNT:
        return await handle_discount_input(update, context)
    if cs == WAITING_FOR_COUPON_AMOUNT:
        return await handle_coupon_input_owner(update, context)
    if cs == WAITING_FOR_DISCOUNT_CODE:
        return await handle_discount_code(update, context)
    if cs == WAITING_FOR_QUANTITY:
        return await handle_quantity_input(update, context)
    if cs == WAITING_FOR_ADD_MORE_SESSIONS:
        return await handle_add_more_choice(update, context)
    if cs == WAITING_FOR_BROADCAST_MESSAGE:
        return await handle_broadcast_message(update, context)
    if cs == WAITING_FOR_TRANSFER_USER:
        return await handle_transfer_user(update, context)
    if cs == WAITING_FOR_TRANSFER_AMOUNT:
        return await handle_transfer_amount(update, context)

# ============ CONVERSATION HANDLER ============
def get_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("panel", owner_panel),
            CommandHandler("add", owner_add_command),
            CommandHandler("deduct", owner_deduct_command),
            CommandHandler("transfer", transfer_cmd),
            CommandHandler("addaccount", addaccount_cmd),
            CallbackQueryHandler(button_handler)
        ],
        states={
            WAITING_FOR_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_amount_input)],
            WAITING_FOR_COUPON: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_coupon_input)],
            WAITING_FOR_SCREENSHOT: [MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_screenshot)],
            WAITING_FOR_UPI_SOURCE: [CallbackQueryHandler(button_handler)],
            WAITING_FOR_UTR: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_utr_input)],
            WAITING_FOR_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_country_input)],
            WAITING_FOR_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_price_input)],
            WAITING_FOR_SESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_session_input)],
            WAITING_FOR_2FA: [MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_2fa_input)],
            WAITING_FOR_DISCOUNT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_discount_input)],
            WAITING_FOR_COUPON_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_coupon_input_owner)],
            WAITING_FOR_DISCOUNT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_discount_code)],
            WAITING_FOR_BOT_PHOTO: [MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo_owner)],
            WAITING_FOR_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_quantity_input)],
            WAITING_FOR_ADD_MORE_SESSIONS: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_add_more_choice)
            ],
            WAITING_FOR_BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_broadcast_message)],
            WAITING_FOR_TARGET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, owner_handle_target_user_id)],
            WAITING_FOR_TARGET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, owner_handle_target_amount)],
            WAITING_FOR_ADDBAL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, owner_handle_addbal_amount)],
            WAITING_SERVICE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, srv2_service_name_input)],
            WAITING_SERVICE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, srv2_service_price_input)],
            WAITING_SERVICE_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, srv2_service_contact_input)],
            WAITING_SERVICE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, srv2_service_desc_input)],
            WAITING_FOR_ADDACC_CHANNEL: [CallbackQueryHandler(button_handler)],
            WAITING_FOR_TRANSFER_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_transfer_user)],
            WAITING_FOR_TRANSFER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_transfer_amount)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_cmd),
            CommandHandler("start", start),
            CallbackQueryHandler(button_handler)
        ],
        allow_reentry=True,
        per_user=True,
        per_chat=True
    )

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = get_conversation_handler()
    application.add_handler(conv_handler)

    application.add_handler(CommandHandler("myservice", myservice_cmd))
    application.add_handler(CommandHandler("allservices", allservices_cmd))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("cancel", cancel_cmd))
    application.add_handler(CommandHandler("ai", ai_toggle))

    # DM fallbacks
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, global_text_fallback))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_photo_owner))

    # Group AI
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO) & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        group_ai_handler
    ))

    application.add_error_handler(error_handler)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🔥 ZUDO OTP BOT — MongoDB + AI v7 (FIXED) 🔥")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"👑 Owner: {OWNER_ID}")
    print(f"📊 Users: {len(data['users'])}")
    print(f"🌍 Buy Countries: {len(data['accounts'])}")
    print(f"♻️ Resale Countries: {len(data.get('resale_accounts', {}))}")
    print(f"🤖 AI in groups: {'ON' if data.get('ai_enabled', True) else 'OFF'}")
    print(f"📝 Logs Group: {LOGS_GROUP_ID}")
    print("🚀 Bot LIVE. Ctrl+C to stop.\n")

    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
