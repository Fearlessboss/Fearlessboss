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
BOT_TOKEN = "8309358322:AAFTTIQhHAIEy_7B42mspLUgBNClKFM1-ck"
OWNER_ID = 7661825494
API_ID = 33628258
API_HASH = "0850762925b9c1715b9b122f7b753128"

# ============ MONGODB ============
MONGO_URL = "mongodb+srv://moderatorhelperorg_db_user:nze86usap2dYthZN@cluster0.uokrixs.mongodb.net/mydatabase?retryWrites=true&w=majority"
MONGO_DB_NAME = "mydatabase"

# Force Join Settings
SUPPORT_CHANNEL_ID = -1003782083448
SUPPORT_GROUP_ID = -1003857205137           # user-facing support group (unchanged)
LOGS_GROUP_ID = -1003764994914              # ✅ NEW: logs group (bot logs go here)
SUPPORT_CHANNEL_LINK = "https://t.me/zudootp"
SUPPORT_GROUP_LINK = "https://t.me/zudootpsupport"

# Owner contact (used by AI to tag owner)
OWNER_TG_LINK = "t.me/manwithoutego"
OWNER_TG_USERNAME = "manwithoutego"

# Resale buyer bot (shown on resale list)
RESALE_BUYER_BOT = "@zudobuyerbot"

# UPI Details
UPI_ID = "fearlessaditya@fam"
UPI_NAME = "Aditya"

# ===== CHECKING SERVER CONFIG (HIDDEN) =====
GMAIL_EMAIL = "deviramrani489@gmail.com"
GMAIL_PASSWORD = "eprrbxhaibzwwhqv"
GMAIL_IMAP_SERVER = "imap.gmail.com"
GMAIL_IMAP_PORT = 993

# Legacy JSON DB (kept as fallback / migration source)
DB_FILE = "virtual_bot_data.json"

# Membership cache (1 hour)
membership_cache = {}
CACHE_DURATION = 3600

# ===== SERVER 2 (Services Marketplace) =====
SERVICE_ADD_FEE = 10

# ===== PAYMENT VERIFICATION SETTINGS =====
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

    # SERVER 2
    WAITING_SERVICE_NAME,
    WAITING_SERVICE_PRICE,
    WAITING_SERVICE_CONTACT,
    WAITING_SERVICE_DESC,

    # ✅ NEW: payment UPI-source selection
    WAITING_FOR_UPI_SOURCE,

    # ✅ NEW: add-account channel selection (buy vs resale)
    WAITING_FOR_ADDACC_CHANNEL,

    # ✅ NEW: /transfer
    WAITING_FOR_TRANSFER_USER,
    WAITING_FOR_TRANSFER_AMOUNT,

    # ✅ NEW: /add balance flow — enter amount (after user id)
    WAITING_FOR_ADDBAL_AMOUNT
) = range(27)

# ============ MARKDOWN ESCAPE ============
def escape_markdown(text):
    if not text:
        return "Unknown"
    return (
        str(text)
        .replace('*', '\\*')
        .replace('_', '\\_')
        .replace('[', '\\[')
        .replace('`', '\\`')
        .replace(']', '\\]')
    )

# ============ MONGO WRAPPER ============
class MongoStore:
    """
    Persistent JSON-like store backed by MongoDB.
    Keeps a hot in-memory `data` dict identical to the old JSON layout,
    so 99% of the old code keeps working. Every save_data() writes to Mongo.
    """
    def __init__(self, url, db_name):
        self.client = MongoClient(url, serverSelectionTimeoutMS=15000)
        self.db = self.client[db_name]
        self.col = self.db["bot_state"]
        # sanity ping
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
        "accounts": {},                # buy channel
        "resale_accounts": {},         # ✅ NEW resale channel
        "discount_codes": {},
        "coupons": {},
        "pending_payments": {},
        "bot_photo": None,
        "states": {},
        "used_discounts": {},
        "used_utrs": {},
        "services": {},
        "service_seq": 0,
        "ai_enabled": True,            # ✅ AI on/off (group only)
        "ai_memory": {}                # ✅ per-user AI memory
    }

def load_data():
    # Try Mongo first
    m = mongo_store.load()
    if m:
        return m
    # Fallback: old JSON file (migrate once)
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                legacy = json.load(f)
                logger.info("[MIGRATE] Loaded legacy JSON, saving to Mongo…")
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

# ============ LOGGING → LOGS GROUP ============
async def send_log_to_support(context, log_message):
    """All bot LOGS go to LOGS_GROUP_ID (new logs group)."""
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
✅ *NUMBER SOLD - SUCCESSFUL* ({channel.upper()})

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
➕ *SESSION ADDED* ({channel.upper()})

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
🗑️ *COUNTRY DELETED* ({channel.upper()})

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
    if is_valid_txn_id_format(v):
        return ("txn", v.upper())
    if is_valid_utr_format(v):
        return ("utr", v)
    return (None, None)

# ============ MEMBERSHIP ============
async def check_user_membership(context, user_id):
    current_time = datetime.now().timestamp()
    if user_id in membership_cache:
        cache_entry = membership_cache[user_id]
        if current_time - cache_entry["time"] < CACHE_DURATION:
            return cache_entry["is_member"]
    try:
        channel_member = await context.bot.get_chat_member(chat_id=SUPPORT_CHANNEL_ID, user_id=user_id)
        group_member = await context.bot.get_chat_member(chat_id=SUPPORT_GROUP_ID, user_id=user_id)
        is_member = (
            channel_member.status in ['member', 'administrator', 'creator'] and
            group_member.status in ['member', 'administrator', 'creator']
        )
        membership_cache[user_id] = {"is_member": is_member, "time": current_time}
        return is_member
    except Exception as e:
        logger.error(f"[MEMBERSHIP CHECK ERROR] {e}")
        return False

# ============ PYROGRAM HELPERS ============
async def create_client(session_string, name="temp_client"):
    try:
        client = Client(name=name, api_id=API_ID, api_hash=API_HASH, session_string=session_string, in_memory=True)
        await client.start()
        return client
    except Exception as e:
        logger.error(f"[CLIENT ERROR] {e}")
        return None

async def get_phone_number(client):
    try:
        me = await client.get_me()
        return me.phone_number if me.phone_number else "N/A"
    except Exception as e:
        logger.error(f"[PHONE ERROR] {e}")
        return "Error"

async def get_otp_from_telegram(client):
    try:
        async for message in client.get_chat_history(777000, limit=10):
            if message.text:
                otp_patterns = [
                    r'(?:code|otp|login code)[:\s]*([0-9]{4,8})',
                    r'\b([0-9]{4,8})\b',
                ]
                for pattern in otp_patterns:
                    match = re.search(pattern, message.text, re.IGNORECASE)
                    if match:
                        return match.group(1)
        return None
    except Exception as e:
        logger.error(f"[OTP ERROR] {e}")
        return None

async def logout_session(session_string, name="logout_client"):
    try:
        client = Client(name=name, api_id=API_ID, api_hash=API_HASH, session_string=session_string, in_memory=True)
        await client.start()
        await client.log_out()
        return True
    except Exception as e:
        logger.error(f"[LOGOUT ERROR] {e}")
        return False

# ============ CHECKING-SERVER (mailbox) HELPERS ============
def _id_in_text(idval, text):
    if not idval or not text:
        return False
    return idval.lower() in text.lower()

def _extract_amounts(text):
    found = []
    if not text:
        return found
    patterns = [
        r'(?:rs\.?|inr|₹)\s*([0-9]{1,7}(?:\.[0-9]{1,2})?)',
        r'\b([0-9]{1,7}(?:\.[0-9]{1,2})?)\s*(?:rs\.?|inr|₹|rupees)',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            try:
                val = float(m.group(1))
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
                            if abs(amt - float(expected_amount)) < 0.01:
                                result["matched_amount"] = True
                                result["found_amount"] = amt
                                break
                    break
            except Exception as e:
                logger.error(f"[MSG PARSE ERROR] {e}")
                continue
        try:
            mail.logout()
        except:
            pass
        return result
    except Exception as e:
        logger.error(f"[CHECKING SERVER ERROR] {e}")
        result["error"] = f"system:{str(e)[:60]}"
        return result

async def auto_verify_id(idval, id_type, expected_amount):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_email_search_id_sync, idval, id_type, expected_amount),
            timeout=AUTO_VERIFY_TIMEOUT
        )
    except asyncio.TimeoutError:
        return {
            "found": False, "matched_amount": False, "found_amount": None,
            "too_old": False, "error": "timeout", "txn_id": None, "utr": None
        }
    except Exception as e:
        logger.error(f"[AUTO VERIFY ERROR] {e}")
        return {
            "found": False, "matched_amount": False, "found_amount": None,
            "too_old": False, "error": f"system:{str(e)[:60]}", "txn_id": None, "utr": None
        }

# ============ FORCE JOIN ============
async def show_force_join_message(update, context):
    text = """
⚠️ *Access Restricted!*

🔒 Join our community first:

1️⃣ *Channel:* Updates & News
2️⃣ *Group:* Support & Help

✅ After joining, click *Verify*
    """
    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=SUPPORT_CHANNEL_LINK)],
        [InlineKeyboardButton("👥 Join Group", url=SUPPORT_GROUP_LINK)],
        [InlineKeyboardButton("✅ Verify Membership", callback_data="verify_join")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            if "not modified" not in str(e).lower():
                logger.error(f"[FORCE JOIN EDIT ERROR] {e}")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def verify_join_handler(update, context):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer("🔍 Verifying...")
    if user_id in membership_cache:
        del membership_cache[user_id]
    is_member = await check_user_membership(context, user_id)
    if is_member:
        await query.answer("✅ Verified! Welcome!", show_alert=True)
        await main_menu(update, context)
    else:
        await query.answer("❌ Please join both channel and group first!", show_alert=True)
        await show_force_join_message(update, context)

# ============ START / MAIN MENU ============
def _menu_keyboard(user_id):
    return [
        [InlineKeyboardButton("🛒 Buy Account", callback_data="virtual_accounts"),
         InlineKeyboardButton("♻️ Resale", callback_data="resale_accounts")],
        [InlineKeyboardButton("👤 Profile", callback_data=f"my_balance_{user_id}"),
         InlineKeyboardButton("💰 Deposit", callback_data="add_funds")],
        [InlineKeyboardButton("🆘 Support", url=SUPPORT_CHANNEL_LINK),
         InlineKeyboardButton("🎁 Refer & Earn", callback_data="coming_soon_refer")],
        [InlineKeyboardButton("🚀 Server 2", callback_data="server2_home")],
        [InlineKeyboardButton("📊 History & Stats", callback_data="history_stats")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]

async def start(update, context):
    # only handle DMs on /start (groups get their own AI)
    if update.effective_chat and update.effective_chat.type != "private":
        return
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or f"User_{user_id}"

    if str(user_id) not in data["users"]:
        data["users"][str(user_id)] = {"balance": 0, "purchases": [], "username": username}
        save_data(data)
        await log_user_registration(context, user_id, username)
    else:
        data["users"][str(user_id)]["username"] = username
        save_data(data)

    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return

    balance = get_user_data(user_id)["balance"]
    safe_username = escape_markdown(username)

    text = f"""👋 *Hello, {safe_username}*
━━━━━━━━━━━━━━━━━━
🚀 *Welcome to Premium Store*
Your one-stop shop for high-quality digital assets.

💎 *Wallet Balance:* ₹{balance}.00
━━━━━━━━━━━━━━━━━━
👇 *Explore our services below:*"""

    reply_markup = InlineKeyboardMarkup(_menu_keyboard(user_id))

    if data.get("bot_photo"):
        try:
            await update.message.reply_photo(
                photo=data["bot_photo"], caption=text,
                reply_markup=reply_markup, parse_mode='Markdown'
            )
            return
        except:
            pass
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def main_menu(update, context):
    user_id = update.effective_user.id
    username = data["users"].get(str(user_id), {}).get("username", f"User_{user_id}")
    balance = get_user_data(user_id)["balance"]
    safe_username = escape_markdown(username)

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        try:
            await query.message.delete()
        except:
            pass

    text = f"""👋 *Hello, {safe_username}*
━━━━━━━━━━━━━━━━━━
🚀 *Welcome to Premium Store*
Your one-stop shop for high-quality digital assets.

💎 *Wallet Balance:* ₹{balance}.00
━━━━━━━━━━━━━━━━━━
👇 *Explore our services below:*"""

    reply_markup = InlineKeyboardMarkup(_menu_keyboard(user_id))

    if update.callback_query:
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ HISTORY & STATS ============
async def show_history_stats(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    user_data = get_user_data(user_id)
    purchases = user_data.get("purchases", [])
    safe_username = escape_markdown(user_data['username'])

    text = f"""
📊 *History & Stats*

👤 User: {safe_username}
💳 Balance: ₹{user_data['balance']}.00
📦 Total Purchases: {len(purchases)}

"""
    if not purchases:
        text += "📭 No purchase history yet!\n\n🛒 Start shopping now!"
    else:
        total_spent = sum(p['price'] for p in purchases)
        text += f"💰 Total Spent: ₹{total_spent}.00\n\n📋 Recent Purchases:\n"
        for p in purchases[-5:]:
            date = datetime.fromisoformat(p['date']).strftime('%d/%m/%Y')
            text += f"\n• {p['country'].upper()} - {p['quantity']}x\n  💰 ₹{p['price']}.00 | 📅 {date}\n"

    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def coming_soon_handler(update, context):
    query = update.callback_query
    await query.answer("🚧 Coming Soon! Stay tuned...", show_alert=True)

# =========================================================
# =================== SERVER 2: SERVICES ==================
# =========================================================
def normalize_username(u):
    if not u:
        return ""
    u = u.strip()
    if u.startswith("@"):
        u = u[1:]
    return u

def next_service_id():
    data["service_seq"] = int(data.get("service_seq", 0)) + 1
    save_data(data)
    return f"S{data['service_seq']}"

def can_delete_service(requester_id, service):
    if not service:
        return False
    return requester_id == OWNER_ID or int(service.get("owner_id", 0)) == int(requester_id)

def get_active_services():
    services = []
    for sid, s in data.get("services", {}).items():
        if s and s.get("active", True):
            services.append(s)
    services.sort(key=lambda x: x.get("created", ""), reverse=True)
    return services

def get_user_services(user_id):
    uid = int(user_id)
    return [s for s in get_active_services() if int(s.get("owner_id", 0)) == uid]

async def server2_home(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    clear_user_state(user_id)

    text = (
        "*Disclaimer:*\n\n"
        "This server only connects buyers and sellers. The owner has no relation with the services listed here.\n"
        "If you get scammed, the owner is not responsible because this is only a buyer-seller connector.\n\n"
        "Choose an option below:"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Available Services", callback_data="srv2_available")],
        [InlineKeyboardButton(f"➕ Add Services (₹{SERVICE_ADD_FEE} Fee)", callback_data="srv2_add_start")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def srv2_available(update, context):
    query = update.callback_query
    await query.answer()
    services = get_active_services()
    if not services:
        await query.edit_message_text(
            "📭 No services available right now.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="server2_home")]]),
            parse_mode='Markdown'
        )
        return
    keyboard = []
    for s in services[:60]:
        name = s.get("name", "Unknown")
        price = int(s.get("price", 0))
        keyboard.append([InlineKeyboardButton(f"🛍 {name} — ₹{price}", callback_data=f"srv2_view_{s['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="server2_home")])
    await query.edit_message_text(
        "✅ *Available Services*\n\nSelect a service to explore:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )

async def srv2_view_service(update, context):
    query = update.callback_query
    await query.answer()
    sid = query.data.split("_", 2)[2]
    s = data.get("services", {}).get(sid)
    if not s or not s.get("active", True):
        await query.edit_message_text(
            "❌ Service not found / deleted.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="srv2_available")]]),
            parse_mode='Markdown'
        )
        return
    name = escape_markdown(s.get("name", "Unknown"))
    desc = escape_markdown(s.get("description", ""))
    contact = escape_markdown(s.get("contact", ""))
    price = int(s.get("price", 0))
    text = (
        f"🛍 *Service Details*\n\n"
        f"📌 Name: *{name}*\n"
        f"💰 Price: ₹{price}.00\n"
        f"👤 Seller Contact: @{contact}\n\n"
        f"📝 Description:\n{desc}\n\n"
        f"⚠️ *Disclaimer:* Owner is not responsible for any scam."
    )
    keyboard = [
        [InlineKeyboardButton("🛒 Buy Service", callback_data=f"srv2_buy_{sid}")],
        [InlineKeyboardButton("🔙 Back ↩️", callback_data="srv2_available")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def srv2_buy_service(update, context):
    query = update.callback_query
    await query.answer()
    buyer = update.effective_user
    buyer_id = buyer.id
    buyer_username = buyer.username or buyer.first_name or f"User_{buyer_id}"

    sid = query.data.split("_", 2)[2]
    s = data.get("services", {}).get(sid)
    if not s or not s.get("active", True):
        await query.edit_message_text(
            "❌ Service not found / deleted.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="srv2_available")]]),
            parse_mode='Markdown'
        )
        return

    await query.edit_message_text(
        "✅ *Request sent to service owner!*\n\n"
        "📩 Seller will contact you soon.\n"
        "💡 You can DM the seller too for faster response.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back ↩️", callback_data="srv2_available")]]),
        parse_mode='Markdown'
    )
    try:
        seller_id = int(s["owner_id"])
        safe_service = escape_markdown(s.get("name", "Unknown"))
        safe_buyer_user = escape_markdown(buyer_username)
        msg = (
            f"🛎 *New Service Request*\n\n"
            f"🛍 Service: *{safe_service}* (₹{int(s.get('price', 0))}.00)\n"
            f"👤 Buyer: {safe_buyer_user}\n"
            f"🆔 Buyer ID: `{buyer_id}`\n\n"
            f"✅ Please DM buyer and complete the deal."
        )
        await context.bot.send_message(chat_id=seller_id, text=msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"[SRV2 BUY DM ERROR] {e}")

async def srv2_add_start(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    clear_user_state(user_id)

    u = get_user_data(user_id)
    bal = int(u.get("balance", 0))
    if bal < SERVICE_ADD_FEE:
        await query.edit_message_text(
            f"❌ You need ₹{SERVICE_ADD_FEE} balance to add a service.\n💳 Current: ₹{bal}.00",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Funds", callback_data="add_funds")],
                [InlineKeyboardButton("🔙 Back", callback_data="server2_home")]
            ]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    set_user_state(user_id, WAITING_SERVICE_NAME, {})
    await query.edit_message_text(
        "📝 *Step 1/4:* Send service name (max 60 chars).",
        parse_mode='Markdown'
    )
    return WAITING_SERVICE_NAME

async def srv2_service_name_input(update, context):
    user_id = update.effective_user.id
    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 60:
        await update.message.reply_text("❌ Name 2-60 chars. Try again.")
        return WAITING_SERVICE_NAME
    st = get_user_state(user_id)
    st["data"]["name"] = name
    set_user_state(user_id, WAITING_SERVICE_PRICE, st["data"])
    await update.message.reply_text("📝 *Step 2/4:* Send price in INR (number only).", parse_mode='Markdown')
    return WAITING_SERVICE_PRICE

async def srv2_service_price_input(update, context):
    user_id = update.effective_user.id
    try:
        price = int(update.message.text.strip())
        if price < 1:
            raise ValueError
    except:
        await update.message.reply_text("❌ Price must be > 0.")
        return WAITING_SERVICE_PRICE
    st = get_user_state(user_id)
    st["data"]["price"] = price
    set_user_state(user_id, WAITING_SERVICE_CONTACT, st["data"])
    await update.message.reply_text("📝 *Step 3/4:* Send your Telegram username (e.g. @yourname).", parse_mode='Markdown')
    return WAITING_SERVICE_CONTACT

async def srv2_service_contact_input(update, context):
    user_id = update.effective_user.id
    contact = normalize_username(update.message.text.strip())
    if not contact or len(contact) < 3:
        await update.message.reply_text("❌ Invalid username. Try again (e.g. @yourname).")
        return WAITING_SERVICE_CONTACT
    st = get_user_state(user_id)
    st["data"]["contact"] = contact
    set_user_state(user_id, WAITING_SERVICE_DESC, st["data"])
    await update.message.reply_text("📝 *Step 4/4:* Send service description (10-400 chars).", parse_mode='Markdown')
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
        await update.message.reply_text(
            f"❌ Insufficient balance. Need ₹{SERVICE_ADD_FEE}, have ₹{bal}.",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END

    data["users"][str(user_id)]["balance"] = bal - SERVICE_ADD_FEE

    sid = next_service_id()
    data["services"][sid] = {
        "id": sid,
        "name": sd["name"],
        "price": sd["price"],
        "contact": sd["contact"],
        "description": desc,
        "owner_id": user_id,
        "active": True,
        "created": datetime.now().isoformat()
    }
    save_data(data)

    await update.message.reply_text(
        f"✅ *Service Added Successfully!*\n\n"
        f"🆔 ID: `{sid}`\n"
        f"📌 Name: {escape_markdown(sd['name'])}\n"
        f"💰 Price: ₹{sd['price']}.00\n"
        f"👤 Contact: @{escape_markdown(sd['contact'])}\n\n"
        f"💸 Fee Deducted: ₹{SERVICE_ADD_FEE}.00\n"
        f"💳 New Balance: ₹{data['users'][str(user_id)]['balance']}.00",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Server 2", callback_data="server2_home")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]),
        parse_mode='Markdown'
    )
    clear_user_state(user_id)
    return ConversationHandler.END

async def myservice_cmd(update, context):
    user_id = update.effective_user.id
    services = get_user_services(user_id)
    if not services:
        await update.message.reply_text("📭 You haven't added any services yet.")
        return
    keyboard = []
    for s in services:
        keyboard.append([InlineKeyboardButton(
            f"🛍 {s['name']} — ₹{int(s['price'])}",
            callback_data=f"myserv_view_{s['id']}"
        )])
    await update.message.reply_text(
        "📋 *Your Services:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def myserv_view(update, context):
    query = update.callback_query
    await query.answer()
    sid = query.data.split("_", 2)[2]
    s = data.get("services", {}).get(sid)
    if not s:
        await query.edit_message_text("❌ Service not found.")
        return
    name = escape_markdown(s.get("name", "Unknown"))
    desc = escape_markdown(s.get("description", ""))
    contact = escape_markdown(s.get("contact", ""))
    price = int(s.get("price", 0))
    text = (
        f"🛍 *Your Service*\n\n"
        f"📌 Name: *{name}*\n"
        f"💰 Price: ₹{price}.00\n"
        f"👤 Contact: @{contact}\n\n"
        f"📝 {desc}"
    )
    keyboard = [[InlineKeyboardButton("🗑 Delete", callback_data=f"serv_del_{sid}")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def allservices_cmd(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized!")
        return
    services = get_active_services()
    if not services:
        await update.message.reply_text("📭 No services.")
        return
    keyboard = []
    for s in services[:60]:
        keyboard.append([InlineKeyboardButton(
            f"🛍 {s['name']} — ₹{int(s['price'])}",
            callback_data=f"ownserv_view_{s['id']}"
        )])
    await update.message.reply_text("📋 *All Services:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def ownserv_view(update, context):
    query = update.callback_query
    await query.answer()
    sid = query.data.split("_", 2)[2]
    s = data.get("services", {}).get(sid)
    if not s:
        await query.edit_message_text("❌ Service not found.")
        return
    name = escape_markdown(s.get("name", "Unknown"))
    desc = escape_markdown(s.get("description", ""))
    contact = escape_markdown(s.get("contact", ""))
    price = int(s.get("price", 0))
    text = (
        f"🛍 *Service (Owner View)*\n\n"
        f"🆔 ID: `{sid}`\n"
        f"📌 Name: *{name}*\n"
        f"💰 Price: ₹{price}.00\n"
        f"👤 Contact: @{contact}\n"
        f"👤 Owner ID: `{s.get('owner_id')}`\n\n"
        f"📝 {desc}"
    )
    keyboard = [[InlineKeyboardButton("🗑 Delete", callback_data=f"serv_del_{sid}")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def serv_delete(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    sid = query.data.split("_", 2)[2]
    s = data.get("services", {}).get(sid)
    if not s:
        await query.edit_message_text("❌ Service not found.")
        return
    if not can_delete_service(user_id, s):
        await query.answer("❌ Not allowed!", show_alert=True)
        return
    s["active"] = False
    save_data(data)
    await query.edit_message_text(f"✅ Service `{sid}` deleted.", parse_mode='Markdown')

# ============ /help ============
async def help_cmd(update, context):
    text = (
        "🆘 *Help / Commands*\n\n"
        "*User:*\n"
        "/start - Start bot\n"
        "/transfer - Transfer balance to another user\n"
        "/cancel - Cancel any ongoing action\n"
        "/myservice - View your services\n"
        "/help - Show this help\n\n"
        "*Owner:*\n"
        "/panel - Owner panel\n"
        "/addaccount - Add account (choose Buy / Resale)\n"
        "/add - Add balance to user\n"
        "/deduct - Deduct balance from user\n"
        "/allservices - View all services\n"
        "/ai on - Enable AI in groups\n"
        "/ai off - Disable AI in groups\n"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

# ============ /cancel (universal) ============
async def cancel_cmd(update, context):
    user_id = update.effective_user.id
    st = get_user_state(user_id)
    if st.get("state", -1) != -1:
        clear_user_state(user_id)
        await update.message.reply_text("✅ Cancelled current action. You can start fresh now.")
    else:
        await update.message.reply_text("ℹ️ Nothing to cancel.")
    return ConversationHandler.END

# ============ /transfer ============
async def transfer_cmd(update, context):
    user_id = update.effective_user.id
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text("❌ Use /transfer in bot DM only.")
        return ConversationHandler.END
    bal = get_user_data(user_id)["balance"]
    if bal < 1:
        await update.message.reply_text(f"❌ Your balance is ₹{bal}.00. Nothing to transfer.")
        return ConversationHandler.END
    set_user_state(user_id, WAITING_FOR_TRANSFER_USER, {})
    await update.message.reply_text(
        f"🔁 *Transfer Balance*\n\n"
        f"💳 Your balance: ₹{bal}.00\n\n"
        f"👤 Send *target user's Telegram ID* (numbers only).\n"
        f"↩️ Or /cancel to abort.",
        parse_mode='Markdown'
    )
    return WAITING_FOR_TRANSFER_USER

async def handle_transfer_user(update, context):
    user_id = update.effective_user.id
    try:
        target_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Invalid ID. Send numbers only, or /cancel.")
        return WAITING_FOR_TRANSFER_USER
    if target_id == user_id:
        await update.message.reply_text("❌ You cannot transfer to yourself.")
        return WAITING_FOR_TRANSFER_USER
    if str(target_id) not in data["users"]:
        await update.message.reply_text("❌ Target user not found in bot. Ask them to /start first.")
        return WAITING_FOR_TRANSFER_USER
    st = get_user_state(user_id)
    st["data"]["target_id"] = target_id
    set_user_state(user_id, WAITING_FOR_TRANSFER_AMOUNT, st["data"])
    bal = get_user_data(user_id)["balance"]
    await update.message.reply_text(
        f"💰 Send amount to transfer (1 – {bal}). Or /cancel.",
        parse_mode='Markdown'
    )
    return WAITING_FOR_TRANSFER_AMOUNT

async def handle_transfer_amount(update, context):
    user_id = update.effective_user.id
    try:
        amount = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Numbers only. Try again or /cancel.")
        return WAITING_FOR_TRANSFER_AMOUNT
    st = get_user_state(user_id)
    target_id = st["data"].get("target_id")
    bal = get_user_data(user_id)["balance"]
    if amount < 1:
        await update.message.reply_text("❌ Amount must be > 0.")
        return WAITING_FOR_TRANSFER_AMOUNT
    if amount > bal:
        await update.message.reply_text(f"❌ You only have ₹{bal}.00. Can't send ₹{amount}.")
        return WAITING_FOR_TRANSFER_AMOUNT

    # do transfer
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

    clear_user_state(user_id)
    return ConversationHandler.END
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

# ============ /add (owner adds balance to user) ============
async def owner_add_command(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized!", parse_mode='Markdown')
        return
    args = context.args
    # /add <user_id> <amount>  → direct
    if len(args) == 2:
        try:
            target_user_id = int(args[0])
            amount = int(args[1])
            if amount < 1:
                await update.message.reply_text("❌ Amount must be > 0!")
                return
            if str(target_user_id) not in data["users"]:
                await update.message.reply_text("❌ User not found!")
                return
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

    # /add <user_id>  → ask amount, show current balance
    if len(args) == 1:
        try:
            target_user_id = int(args[0])
        except:
            await update.message.reply_text("❌ Usage: /add <user_id> [amount]")
            return
        if str(target_user_id) not in data["users"]:
            await update.message.reply_text("❌ User not found!")
            return
        cur_bal = data["users"][str(target_user_id)]["balance"]
        set_user_state(user_id, WAITING_FOR_ADDBAL_AMOUNT, {"target_user_id": target_user_id})
        await update.message.reply_text(
            f"👤 Target: `{target_user_id}`\n"
            f"💳 Current balance: ₹{cur_bal}.00\n\n"
            f"💰 Enter amount to add:",
            parse_mode='Markdown'
        )
        return

    # /add  → ask user id, then amount
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
            if amount < 1:
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
            await update.message.reply_text("❌ User not found!")
            clear_user_state(user_id)
            return ConversationHandler.END
        st = get_user_state(user_id)
        st["data"]["target_user_id"] = target_user_id
        action = st["data"].get("action", "add")
        cur_bal = data["users"][str(target_user_id)]["balance"]
        if action == "add":
            set_user_state(user_id, WAITING_FOR_ADDBAL_AMOUNT, st["data"])
            await update.message.reply_text(
                f"👤 Target: `{target_user_id}`\n"
                f"💳 Current balance: ₹{cur_bal}.00\n\n"
                f"💰 Enter amount to add:",
                parse_mode='Markdown'
            )
            return WAITING_FOR_ADDBAL_AMOUNT
        else:
            set_user_state(user_id, WAITING_FOR_TARGET_AMOUNT, st["data"])
            await update.message.reply_text(
                f"👤 Target: `{target_user_id}`\n"
                f"💳 Current balance: ₹{cur_bal}.00\n\n"
                f"💰 Enter amount to deduct:",
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
        if amount < 1:
            await update.message.reply_text("❌ Amount must be > 0!")
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
    # deduct flow
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    try:
        amount = int(update.message.text.strip())
        st = get_user_state(user_id)
        target_user_id = st["data"]["target_user_id"]
        before = data["users"][str(target_user_id)]["balance"]
        if amount < 1:
            await update.message.reply_text("❌ Amount must be > 0!")
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

# ============ DISCOUNT / COUPON CREATE (owner) ============
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
        if discount < 1:
            await update.message.reply_text("❌ Amount must be > 0!")
            return WAITING_FOR_DISCOUNT_AMOUNT
        discount_code = generate_random_code("DSC", 10)
        data["discount_codes"][discount_code] = {"discount": discount, "created": datetime.now().isoformat()}
        save_data(data)
        await log_discount_created(context, discount_code, discount)
        await update.message.reply_text(
            f"✅ Discount Created!\n\n🎟 Code: `{discount_code}`\n💰 Discount: ₹{discount}.00",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Invalid! Numbers only.")
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
        if amount < 1:
            await update.message.reply_text("❌ Amount must be > 0!")
            return WAITING_FOR_COUPON_AMOUNT
        coupon_code = generate_random_code("CPN", 12)
        data["coupons"][coupon_code] = {"amount": amount, "used": False, "created": datetime.now().isoformat()}
        save_data(data)
        await update.message.reply_text(
            f"✅ Coupon Created!\n\n🎫 Code: `{coupon_code}`\n💰 Amount: ₹{amount}.00",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Invalid! Numbers only.")
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
                text=f"📣 *Broadcast Message*\n\n{broadcast_message}",
                parse_mode='Markdown'
            )
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed_count += 1
    await log_broadcast_sent(context, total_users, success_count, failed_count)
    await query.edit_message_text(
        f"✅ Broadcast Complete!\n\n✅ Sent: {success_count}\n❌ Failed: {failed_count}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]),
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
    id_type = payment_info.get("id_type", "ID").upper()
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
    if payment_info.get("status") not in ("submitted", "manual_review", "awaiting_utr"):
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]),
            parse_mode='Markdown'
        )
    except:
        try:
            await query.edit_message_text(
                f"✅ Approved! `{target_user_id}` — ₹{amount}.00",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]),
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
            text=f"❌ *Payment Rejected!*\n\n💰 Amount: ₹{amount}.00\n📝 Reason: Invalid payment\n\n💡 Contact: @{OWNER_TG_USERNAME}",
            parse_mode='Markdown'
        )
    except:
        pass
    try:
        await query.edit_message_caption(
            caption=f"❌ Rejected!\n\n👤 `{target_user_id}`\n💰 ₹{amount}.00",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]),
            parse_mode='Markdown'
        )
    except:
        try:
            await query.edit_message_text(
                f"❌ Rejected! `{target_user_id}` — ₹{amount}.00",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]),
                parse_mode='Markdown'
            )
        except:
            pass

# ============ OWNER USER BALANCE LIST / PAYMENTS / STATS ============
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]),
            parse_mode='Markdown'
        )
        return
    users_with_balance.sort(key=lambda x: x["balance"], reverse=True)
    text = f"💰 *Users with Balance ≥ ₹1*\n\nTotal: {len(users_with_balance)}\n\n"
    for u in users_with_balance[:50]:
        text += f"• `{u['user_id']}` - {escape_markdown(u['username'])}: ₹{u['balance']}.00\n"
    if len(users_with_balance) > 50:
        text += f"\n... and {len(users_with_balance) - 50} more"
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]),
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
        if info.get("status") in ("submitted", "manual_review")
    }
    if not pending:
        await query.edit_message_text(
            "📭 No pending payments!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]),
            parse_mode='Markdown'
        )
        return
    text = "💳 *Pending Payments*\n\n"
    keyboard = []
    for pid, info in list(pending.items())[:5]:
        username = data["users"].get(str(pid), {}).get("username", f"User_{pid}")
        text += f"👤 {escape_markdown(username)}\n💰 ₹{info['amount']}\n\n"
        keyboard.append([InlineKeyboardButton(f"🔍 {username[:15]} - ₹{info['amount']}", callback_data=f"review_payment_{pid}")])
    keyboard.append([InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")])
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
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]),
        parse_mode='Markdown'
    )

# ============ COUNTRY UI (BUY + RESALE) ============
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
    country_flags = {
        "USA": "🇺🇸", "UK": "🇬🇧", "INDIA": "🇮🇳", "CANADA": "🇨🇦",
        "AUSTRALIA": "🇦🇺", "GERMANY": "🇩🇪", "FRANCE": "🇫🇷",
        "KENYA": "🇰🇪", "NIGERIA": "🇳🇬", "PAKISTAN": "🇵🇰"
    }
    ch = _channel_dict(channel)
    available = {c: info for c, info in ch.items() if info["quantity"] > 0}
    if channel == "resale":
        header = (
            "♻️ *Resale Accounts*\n\n"
            f"ℹ️ Here you can buy resale accounts that are being sold on {RESALE_BUYER_BOT}.\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
        )
    else:
        header = "📍 *Available Accounts*\n━━━━━━━━━━━━━━━━━━━━\n\n"

    if available:
        text = header
        pfx = _channel_prefix(channel)
        for country, info in available.items():
            flag = country_flags.get(country.upper(), "📱")
            text += f"{flag} *{country.title()}*  •  📦 {info['quantity']}  •  💰 ₹{info['price']}.00\n"
            keyboard.append([InlineKeyboardButton(
                f"{flag} {country.title()} — ₹{info['price']}",
                callback_data=f"{pfx}country_{country}"
            )])
        text += "\n👇 Select a country:"
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])
    else:
        text = header + "📭 *No accounts available currently!*"
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

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
    text = f"""
📱 *{country.upper()} {label}*

💰 Price: ₹{info['price']}.00
📊 Available: {info['quantity']}
💳 Your Balance: ₹{balance}.00
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
    country = query.data.split("_")[-1]
    ch = _channel_dict(channel)
    if country not in ch:
        return ConversationHandler.END
    info = ch[country]
    price = info["price"]
    balance = get_user_data(user_id)["balance"]
    available = info["quantity"]
    await query.edit_message_text(
        f"🛒 *Purchase {country.upper()}*\n\n"
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
        if quantity < 1:
            await update.message.reply_text("❌ Must be > 0!")
            return WAITING_FOR_QUANTITY
        if quantity > available:
            await update.message.reply_text(f"❌ Only {available} available!")
            return WAITING_FOR_QUANTITY
        total_price = price * quantity
        balance = get_user_data(user_id)["balance"]
        username = data["users"][str(user_id)]["username"]
        if balance < total_price:
            await log_insufficient_balance(context, user_id, username, total_price, balance)
            await update.message.reply_text(
                f"❌ Insufficient balance!\n💰 Need: ₹{total_price}\n💳 Have: ₹{balance}"
            )
            clear_user_state(user_id)
            return ConversationHandler.END
        pfx = _channel_prefix(channel)
        keyboard = [
            [InlineKeyboardButton("✅ CONFIRM", callback_data=f"{pfx}confirm_buy_{country}_{quantity}")],
            [InlineKeyboardButton("❌ CANCEL", callback_data=("virtual_accounts" if channel == "buy" else "resale_accounts"))]
        ]
        await update.message.reply_text(
            f"🛒 *Confirm Purchase*\n\n📱 {country.upper()} ({'Resale' if channel=='resale' else 'Buy'})\n"
            f"📊 Qty: {quantity}\n💰 Total: ₹{total_price}\n💳 Balance: ₹{balance}",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Numbers only!")
        return WAITING_FOR_QUANTITY

async def confirm_purchase(update, context, channel="buy"):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    # callback format: [r]confirm_buy_<country>_<qty>
    parts = query.data.split("_")
    country = parts[-2]
    quantity = int(parts[-1])
    username = data["users"][str(user_id)]["username"]
    ch = _channel_dict(channel)
    if country not in ch or ch[country]["quantity"] < quantity:
        await query.edit_message_text("❌ Out of stock!", parse_mode='Markdown')
        return
    price_each = ch[country]["price"]
    total_price = price_each * quantity
    balance = get_user_data(user_id)["balance"]
    if balance < total_price:
        await log_insufficient_balance(context, user_id, username, total_price, balance)
        await query.edit_message_text("❌ Insufficient!", parse_mode='Markdown')
        return
    sessions_to_assign = ch[country]["sessions"][:quantity]
    ch[country]["sessions"] = ch[country]["sessions"][quantity:]
    ch[country]["quantity"] -= quantity
    data["users"][str(user_id)]["balance"] -= total_price
    purchase = {
        "country": country, "quantity": quantity, "price": total_price,
        "sessions": sessions_to_assign, "date": datetime.now().isoformat(), "status": "completed",
        "channel": channel
    }
    data["users"][str(user_id)]["purchases"].append(purchase)
    save_data(data)
    idx = len(data["users"][str(user_id)]["purchases"]) - 1
    phones = [s.get("phone_number", "Unknown") for s in sessions_to_assign]
    await log_number_purchase(context, user_id, username, country, quantity, total_price, phones, channel=channel)
    keyboard = [
        [InlineKeyboardButton("📱 GET NUMBERS", callback_data=f"get_number_{user_id}_{idx}")],
        [InlineKeyboardButton("🛒 Buy More", callback_data=("virtual_accounts" if channel=="buy" else "resale_accounts"))],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    await query.edit_message_text(
        f"🎉 *Purchase Successful!*\n\n📱 {country.upper()}\n📊 Qty: {quantity}\n💰 ₹{total_price}\n"
        f"💳 New Balance: ₹{data['users'][str(user_id)]['balance']}",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )

async def confirm_purchase_buy(update, context):
    await confirm_purchase(update, context, channel="buy")

async def confirm_purchase_resale(update, context):
    await confirm_purchase(update, context, channel="resale")

# --- get numbers / OTP / logout (same for both channels since we saved channel in purchase) ---
async def get_number_handler(update, context):
    query = update.callback_query
    await query.answer("📱 Fetching...")
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

    async def fetch_phone(i, sd):
        s = sd.get("session")
        if s:
            try:
                c = await create_client(s, f"{user_id}_{i}")
                if c:
                    p = await get_phone_number(c)
                    await c.stop()
                    return p
            except:
                pass
        return "Error"

    phones = await asyncio.gather(*[fetch_phone(i, s) for i, s in enumerate(sessions)])
    for idxp, ph in enumerate(phones):
        try:
            purchase["sessions"][idxp]["phone_number"] = ph
        except:
            pass
    save_data(data)
    text = f"📱 *Phone Numbers*\n\n{purchase['country'].upper()} — {purchase['quantity']}\n"
    for i, p in enumerate(phones, 1):
        text += f"\n*Account {i}:* `{p}`"
    keyboard = [
        [InlineKeyboardButton("🔍 GET OTP", callback_data=f"get_otp_{user_id}_{idx}")],
        [InlineKeyboardButton("✅ LOGIN COMPLETE", callback_data=f"login_complete_{user_id}_{idx}")]
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
    await query.edit_message_text(f"🔍 Fetching OTP for {purchase['country'].upper()}...", parse_mode='Markdown')

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
                    await client.stop()
                    if otp:
                        msg = f"✅ OTP: `{otp}` - `{phone}`"
                        if twofa:
                            msg += f"\n🔐 2FA: `{twofa}`"
                        return {"status": "success", "message": msg}
                    return {"status": "not_found", "message": f"⏳ OTP not found - `{phone}`"}
            except Exception as e:
                if client:
                    try:
                        await client.stop()
                    except:
                        pass
                return {"status": "error", "message": f"❌ Error"}
        return {"status": "error", "message": "❌ No session"}

    results = await asyncio.gather(*[fetch_otp(i, s) for i, s in enumerate(sessions)])
    text = f"🔑 *OTP Results*\n\n{purchase['country'].upper()}\n"
    success = 0
    for i, r in enumerate(results, 1):
        text += f"\n*Account {i}:* {r['message']}"
        if r["status"] == "success":
            success += 1
    await log_otp_fetched(context, user_id, data["users"][str(user_id)]["username"], purchase['country'], success, len(sessions))
    keyboard = [
        [InlineKeyboardButton("🔄 TRY AGAIN", callback_data=f"get_otp_{user_id}_{idx}")],
        [InlineKeyboardButton("✅ LOGIN COMPLETE", callback_data=f"login_complete_{user_id}_{idx}")]
    ]
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
    await query.edit_message_text("🎉 *Login Complete!*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

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
            results.append(f"{'✅' if ok else '❌'} {phone}")
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

# ============ PROFILE ============
async def show_balance(update, context):
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split("_")[2])
    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return
    balance = get_user_data(user_id)["balance"]
    text = f"💳 *My Profile*\n\n💰 Balance: ₹{balance}.00\n\n📊 Recent Transactions:"
    purchases = data["users"][str(user_id)]["purchases"]
    if not purchases:
        text += "\n• No transactions"
    else:
        for p in purchases[-5:]:
            text += f"\n• {p['country'].upper()} - {p['quantity']}x - ₹{p['price']}.00"
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

1️⃣ Buy Funds (UPI) - Instant
2️⃣ Coupon Code - Redeem

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
        f"💰 *Enter Amount*\n\n💡 Minimum {MIN_DEPOSIT} INR\n\n📝 Reply with amount:",
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
        qr_image = generate_upi_qr(amount)
        caption = (
            f"💳 *Pay ₹{amount}.00 via UPI*\n\n"
            f"🆔 UPI ID: `{UPI_ID}`\n"
            f"👤 Name: {UPI_NAME}\n"
            f"💰 Amount: ₹{amount}.00\n\n"
            f"📱 Scan QR or copy UPI ID.\n\n"
            f"✅ After payment, send the *payment screenshot* here."
        )
        if qr_image:
            await update.message.reply_photo(photo=qr_image, caption=caption, parse_mode='Markdown')
        else:
            await update.message.reply_text(caption, parse_mode='Markdown')
        set_user_state(user_id, WAITING_FOR_SCREENSHOT, {"amount": amount})
        return WAITING_FOR_SCREENSHOT
    except ValueError:
        await update.message.reply_text("❌ Numbers only!")
        return WAITING_FOR_AMOUNT

# ✅ SCREENSHOT → ASK UPI SOURCE (FamPay / Other UPI)
async def handle_screenshot(update, context):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if state["state"] != WAITING_FOR_SCREENSHOT:
        return ConversationHandler.END
    amount = state["data"].get("amount", 0)
    if not amount:
        await update.message.reply_text("❌ Session expired. Try again.")
        clear_user_state(user_id)
        return ConversationHandler.END
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a photo (screenshot).")
        return WAITING_FOR_SCREENSHOT
    photo_id = update.message.photo[-1].file_id

    data["pending_payments"][str(user_id)] = {
        "amount": amount,
        "photo_id": photo_id,
        "timestamp": datetime.now().isoformat(),
        "status": "awaiting_utr",
        "utr": None
    }
    save_data(data)

    username = data["users"][str(user_id)]["username"]
    await log_payment_submitted(context, user_id, username, amount)

    keyboard = [
        [InlineKeyboardButton("💜 FamPay", callback_data="upisrc_fampay"),
         InlineKeyboardButton("💳 Other UPI", callback_data="upisrc_other")]
    ]
    await update.message.reply_text(
        f"✅ Screenshot received!\n\n"
        f"💰 Amount: ₹{amount}.00\n\n"
        f"❓ *From which app did you pay?*\n"
        f"Choose one:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_UPI_SOURCE, {"amount": amount, "photo_id": photo_id})
    return WAITING_FOR_UPI_SOURCE

# ✅ handle UPI source click → ask correct id
async def handle_upi_source(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    src = query.data.split("_", 1)[1]  # "fampay" or "other"
    st = get_user_state(user_id)
    if st["state"] not in (WAITING_FOR_UPI_SOURCE, WAITING_FOR_UTR):
        return
    d = st.get("data", {})
    d["upi_source"] = src
    set_user_state(user_id, WAITING_FOR_UTR, d)

    if src == "fampay":
        prompt = (
            "💜 *FamPay Selected*\n\n"
            "🔢 Please send your *Transaction ID*.\n"
            "💡 Example: `FMPIB5334310018` (letters + digits mixed)\n\n"
            "↩️ Send /cancel or click Back to change UPI app."
        )
    else:
        prompt = (
            "💳 *Other UPI Selected*\n\n"
            "🔢 Please send your *12 digit UTR number*.\n"
            "💡 Example: `612004984273` (12 digits)\n\n"
            "↩️ Send /cancel or click Back to change UPI app."
        )
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="upisrc_back")]]
    await query.edit_message_text(prompt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def handle_upi_source_back(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    st = get_user_state(user_id)
    d = st.get("data", {})
    d.pop("upi_source", None)
    set_user_state(user_id, WAITING_FOR_UPI_SOURCE, d)
    keyboard = [
        [InlineKeyboardButton("💜 FamPay", callback_data="upisrc_fampay"),
         InlineKeyboardButton("💳 Other UPI", callback_data="upisrc_other")]
    ]
    await query.edit_message_text(
        f"❓ *From which app did you pay?*\nChoose one:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ✅ Now handle UTR / Transaction ID input based on UPI source
async def handle_utr_input(update, context):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if state["state"] != WAITING_FOR_UTR:
        return ConversationHandler.END
    raw = update.message.text.strip()
    amount = state["data"].get("amount", 0)
    photo_id = state["data"].get("photo_id")
    src = state["data"].get("upi_source", "other")
    username = data["users"][str(user_id)].get("username", f"User_{user_id}")
    safe_username = escape_markdown(username)

    # Enforce format by source
    if src == "fampay":
        if not is_valid_txn_id_format(raw):
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="upisrc_back")]]
            await update.message.reply_text(
                "❌ Invalid *Transaction ID*.\n\n"
                "For FamPay, send an alphanumeric Transaction ID (letters + digits, 8–30 chars).\n"
                "💡 Example: `FMPIB5334310018`\n\n"
                "Or press Back to change UPI app.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return WAITING_FOR_UTR
        id_type, idval = ("txn", raw.upper())
    else:
        # Other UPI → must be 12 digit UTR
        v = raw.strip()
        if not (v.isdigit() and len(v) == 12):
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="upisrc_back")]]
            await update.message.reply_text(
                "❌ Invalid *UTR number*.\n\n"
                "For Other UPI, send a *12 digit* UTR (numbers only).\n"
                "💡 Example: `612004984273`\n\n"
                "Or press Back to change UPI app.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return WAITING_FOR_UTR
        id_type, idval = ("utr", v)

    pretty_type = "Transaction ID" if id_type == "txn" else "UTR"

    if is_utr_used(idval):
        await log_auto_approve_attempt(context, user_id, username, amount, idval,
                                       "REJECTED", f"{pretty_type} already used", id_type=pretty_type)
        await update.message.reply_text(
            f"❌ *This {pretty_type} has already been used!*\n\n"
            f"💡 Please make a fresh payment.\n"
            f"📞 Contact: @{OWNER_TG_USERNAME}",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END

    if str(user_id) not in data["pending_payments"]:
        data["pending_payments"][str(user_id)] = {}
    data["pending_payments"][str(user_id)].update({
        "amount": amount, "photo_id": photo_id, "utr": idval,
        "id_type": id_type, "upi_source": src,
        "timestamp": datetime.now().isoformat(), "status": "submitted"
    })
    save_data(data)

    verifying_msg = await update.message.reply_text(
        f"🤖 *Auto-verifying...*\n\n💰 ₹{amount}.00\n🔢 {pretty_type}: `{escape_markdown(idval)}`\n"
        f"⏳ Checking (max {AUTO_VERIFY_TIMEOUT}s)...",
        parse_mode='Markdown'
    )
    result = await auto_verify_id(idval, id_type, amount)
    paired_txn = result.get("txn_id")
    paired_utr = result.get("utr")
    if paired_txn or paired_utr:
        data["pending_payments"][str(user_id)]["paired_txn"] = paired_txn
        data["pending_payments"][str(user_id)]["paired_utr"] = paired_utr
        save_data(data)

    # CASE 1: found + match
    if result.get("found") and result.get("matched_amount") and not result.get("too_old"):
        data["users"][str(user_id)]["balance"] += amount
        data["pending_payments"][str(user_id)]["status"] = "approved"
        mark_utr_used(idval, user_id, amount, mode="auto")
        if paired_txn and paired_txn.upper() != idval.upper():
            mark_utr_used(paired_txn, user_id, amount, mode="auto_paired")
        if paired_utr and paired_utr != idval:
            mark_utr_used(paired_utr, user_id, amount, mode="auto_paired")
        save_data(data)
        await log_auto_approve_attempt(context, user_id, username, amount, idval, "AUTO APPROVED", "Match", id_type=pretty_type)
        await log_payment_approved(context, user_id, username, amount, mode="AUTO")
        try:
            await verifying_msg.edit_text(
                f"✅ *Payment Auto-Approved!*\n\n💰 ₹{amount}.00\n"
                f"💳 New Balance: ₹{data['users'][str(user_id)]['balance']}.00",
                parse_mode='Markdown'
            )
        except:
            pass
        clear_user_state(user_id)
        return ConversationHandler.END

    # CASE 2: found + mismatch
    if result.get("found") and not result.get("matched_amount") and not result.get("too_old"):
        found_amt = result.get("found_amount")
        mark_utr_used(idval, user_id, amount, mode="auto_failed_mismatch")
        data["pending_payments"][str(user_id)]["status"] = "rejected_mismatch"
        save_data(data)
        await log_auto_approve_attempt(context, user_id, username, amount, idval,
                                       "AMOUNT MISMATCH", f"Expected ₹{amount}, found ₹{found_amt}", id_type=pretty_type)
        try:
            await verifying_msg.edit_text(
                f"❌ *Amount Mismatch!*\n💰 Entered: ₹{amount}\n💰 Found: ₹{found_amt}\n\n"
                f"📞 Contact: @{OWNER_TG_USERNAME}",
                parse_mode='Markdown'
            )
        except:
            pass
        clear_user_state(user_id)
        return ConversationHandler.END

    # CASE 3: too old
    if result.get("too_old"):
        mark_utr_used(idval, user_id, amount, mode="auto_failed_too_old")
        data["pending_payments"][str(user_id)]["status"] = "rejected_old_utr"
        save_data(data)
        await log_auto_approve_attempt(context, user_id, username, amount, idval,
                                       "ID TOO OLD", f"Older than {UTR_MAX_AGE_HOURS}h", id_type=pretty_type)
        try:
            await verifying_msg.edit_text(
                f"❌ *Old {pretty_type}!*\nOnly last {UTR_MAX_AGE_HOURS}h accepted.\n\n"
                f"📞 Contact: @{OWNER_TG_USERNAME}",
                parse_mode='Markdown'
            )
        except:
            pass
        clear_user_state(user_id)
        return ConversationHandler.END

    # CASE 4: manual review
    data["pending_payments"][str(user_id)]["status"] = "manual_review"
    save_data(data)
    err = result.get("error")
    if err == "timeout":
        fail_reason = f"Auto verify timeout ({AUTO_VERIFY_TIMEOUT}s)"
    elif err:
        fail_reason = f"System error: {err}"
    else:
        fail_reason = f"{pretty_type} not found in last {UTR_MAX_AGE_HOURS}h"
    await log_auto_approve_attempt(context, user_id, username, amount, idval, "MANUAL REVIEW", fail_reason, id_type=pretty_type)

    try:
        keyboard_owner = [[
            InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_fund_{user_id}"),
            InlineKeyboardButton("❌ REJECT", callback_data=f"reject_fund_{user_id}")
        ]]
        await context.bot.send_photo(
            chat_id=OWNER_ID, photo=photo_id,
            caption=f"💳 *Manual Payment Review*\n\n"
                    f"👤 {safe_username}\n🆔 `{user_id}`\n"
                    f"💰 ₹{amount}.00\n🔢 {pretty_type}: `{escape_markdown(idval)}`\n"
                    f"📱 Source: {src}\n📝 {escape_markdown(fail_reason)}",
            reply_markup=InlineKeyboardMarkup(keyboard_owner), parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"[FORWARD ERROR] {e}")

    try:
        await verifying_msg.edit_text(
            f"⚠️ Auto verification failed.\n📝 {escape_markdown(fail_reason)}\n\n"
            f"📨 Sent to owner for manual approval.\n📞 Contact: @{OWNER_TG_USERNAME}",
            parse_mode='Markdown'
        )
    except:
        pass
    clear_user_state(user_id)
    return ConversationHandler.END

# ============ COUPON REDEEM ============
async def ask_coupon_code(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    await query.edit_message_text("🎟 *Redeem Coupon*\n\n💡 Enter code:", parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_COUPON)
    return WAITING_FOR_COUPON

async def handle_coupon_input(update, context):
    user_id = update.effective_user.id
    code = update.message.text.strip().upper()
    username = data["users"][str(user_id)]["username"]
    if code not in data["coupons"]:
        await update.message.reply_text("❌ Invalid coupon!", parse_mode='Markdown')
        clear_user_state(user_id)
        return ConversationHandler.END
    cinfo = data["coupons"][code]
    if cinfo["used"]:
        await update.message.reply_text("❌ Coupon already used!", parse_mode='Markdown')
        clear_user_state(user_id)
        return ConversationHandler.END
    amount = cinfo["amount"]
    data["coupons"][code]["used"] = True
    data["coupons"][code]["used_by"] = user_id
    data["coupons"][code]["used_at"] = datetime.now().isoformat()
    data["users"][str(user_id)]["balance"] += amount
    save_data(data)
    await log_coupon_redeemed(context, user_id, username, code, amount)
    await update.message.reply_text(
        f"✅ Coupon Redeemed!\n💰 ₹{amount}.00\n💳 New Balance: ₹{data['users'][str(user_id)]['balance']}.00",
        parse_mode='Markdown'
    )
    clear_user_state(user_id)
    return ConversationHandler.END

# ============ /addaccount FLOW (choose channel first) ============
async def addaccount_cmd(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized!")
        return ConversationHandler.END
    keyboard = [
        [InlineKeyboardButton("🛒 Buy Account", callback_data="addacc_ch_buy"),
         InlineKeyboardButton("♻️ Resale", callback_data="addacc_ch_resale")]
    ]
    await update.message.reply_text(
        "➕ *Add Account*\n\nSelect channel where this account should go:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_ADDACC_CHANNEL, {})
    return WAITING_FOR_ADDACC_CHANNEL

async def addacc_pick_channel(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    ch = "buy" if query.data.endswith("_buy") else "resale"
    set_user_state(user_id, WAITING_FOR_COUNTRY, {"channel": ch})
    await query.edit_message_text(
        f"✅ Channel: *{'Buy Account' if ch=='buy' else 'Resale'}*\n\n"
        f"📝 Enter country name (e.g. USA, INDIA):",
        parse_mode='Markdown'
    )

# owner_add_number (from panel button) → also asks channel
async def owner_add_number(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    keyboard = [
        [InlineKeyboardButton("🛒 Buy Account", callback_data="addacc_ch_buy"),
         InlineKeyboardButton("♻️ Resale", callback_data="addacc_ch_resale")]
    ]
    await query.edit_message_text(
        "➕ *Add Account*\n\nSelect channel:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_ADDACC_CHANNEL, {})
    return WAITING_FOR_ADDACC_CHANNEL

async def handle_country_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    country = update.message.text.strip().upper()
    st = get_user_state(user_id)
    channel = st.get("data", {}).get("channel", "buy")
    ch = _channel_dict(channel)
    if country in ch:
        existing = ch[country]
        await update.message.reply_text(
            f"⚠️ *'{country}' exists in {channel.upper()}!*\n"
            f"• Price: ₹{existing['price']}\n• Stock: {existing['quantity']}\n\n"
            f"Type `ADD` to add more, `NEW` to change price, `CANCEL` to abort.",
            parse_mode='Markdown'
        )
        set_user_state(user_id, WAITING_FOR_ADD_MORE_SESSIONS,
                       {"country": country, "price": existing['price'], "channel": channel})
        return WAITING_FOR_ADD_MORE_SESSIONS
    set_user_state(user_id, WAITING_FOR_PRICE, {"country": country, "channel": channel})
    await update.message.reply_text(f"💰 *Set Price for {country}*\n\n📝 Enter price in INR:", parse_mode='Markdown')
    return WAITING_FOR_PRICE

async def handle_add_more_choice(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    choice = update.message.text.strip().upper()
    st = get_user_state(user_id)
    country = st["data"]["country"]
    price = st["data"]["price"]
    channel = st["data"].get("channel", "buy")
    if choice == "CANCEL":
        await update.message.reply_text("❌ Cancelled!")
        clear_user_state(user_id)
        return ConversationHandler.END
    if choice == "ADD":
        set_user_state(user_id, WAITING_FOR_SESSION, {"country": country, "price": price, "channel": channel})
        await update.message.reply_text(f"🔗 Send session string for {country}:")
        return WAITING_FOR_SESSION
    if choice == "NEW":
        set_user_state(user_id, WAITING_FOR_PRICE, {"country": country, "channel": channel})
        await update.message.reply_text(f"💰 Enter new price:")
        return WAITING_FOR_PRICE
    await update.message.reply_text("❌ Type ADD, NEW, or CANCEL")
    return WAITING_FOR_ADD_MORE_SESSIONS

async def handle_price_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    try:
        price = int(update.message.text.strip())
        st = get_user_state(user_id)
        country = st["data"]["country"]
        channel = st["data"].get("channel", "buy")
        ch = _channel_dict(channel)
        if country not in ch:
            ch[country] = {"price": price, "quantity": 0, "sessions": []}
        else:
            ch[country]["price"] = price
        save_data(data)
        set_user_state(user_id, WAITING_FOR_SESSION, {"country": country, "price": price, "channel": channel})
        await update.message.reply_text(f"🔗 Send session string for {country} (channel: {channel}):")
        return WAITING_FOR_SESSION
    except ValueError:
        await update.message.reply_text("❌ Numbers only!")
        return WAITING_FOR_PRICE

async def handle_session_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    text = update.message.text.strip()
    st = get_user_state(user_id)
    country = st["data"]["country"]
    price = st["data"]["price"]
    channel = st["data"].get("channel", "buy")
    if text == "/skip":
        clear_user_state(user_id)
        await update.message.reply_text(f"✅ Done for {country} ({channel})!")
        return ConversationHandler.END
    if len(text) < 50:
        await update.message.reply_text("❌ Invalid session string.")
        return WAITING_FOR_SESSION
    st["data"]["pending_session"] = text
    set_user_state(user_id, WAITING_FOR_2FA, st["data"])
    await update.message.reply_text("🔐 Send 2FA password, or `/skip` if none.", parse_mode='Markdown')
    return WAITING_FOR_2FA

async def handle_2fa_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    text = update.message.text.strip()
    st = get_user_state(user_id)
    country = st["data"]["country"]
    price = st["data"]["price"]
    channel = st["data"].get("channel", "buy")
    session_str = st["data"].get("pending_session")
    twofa = None if text == "/skip" else text

    phone_number = "N/A"
    try:
        client = await create_client(session_str, f"add_{user_id}")
        if client:
            phone_number = await get_phone_number(client)
            await client.stop()
    except:
        pass

    ch = _channel_dict(channel)
    if country not in ch:
        ch[country] = {"price": price, "quantity": 0, "sessions": []}
    ch[country]["sessions"].append({"session": session_str, "phone_number": phone_number, "twofa": twofa})
    ch[country]["quantity"] += 1
    save_data(data)
    await log_session_added(context, country, 1, price, phone_number, twofa, channel=channel)
    await update.message.reply_text(
        f"✅ Session added to *{channel.upper()}*!\n"
        f"📱 Phone: `{phone_number}`\n📦 Stock: {ch[country]['quantity']}\n\n"
        f"📝 Send another session or `/skip` to finish.",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_SESSION, {"country": country, "price": price, "channel": channel})
    return WAITING_FOR_SESSION

# ============ DELETE COUNTRY (buy channel only for simplicity) ============
async def owner_delete_country(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    keyboard = []
    for c in data["accounts"].keys():
        keyboard.append([InlineKeyboardButton(f"🗑 BUY: {c}", callback_data=f"delete_confirm_buy_{c}")])
    for c in data.get("resale_accounts", {}).keys():
        keyboard.append([InlineKeyboardButton(f"🗑 RESALE: {c}", callback_data=f"delete_confirm_resale_{c}")])
    if not keyboard:
        await query.edit_message_text(
            "📭 Nothing to delete!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]),
            parse_mode='Markdown'
        )
        return
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="owner_panel")])
    await query.edit_message_text("🗑 *Delete Country*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def confirm_delete_country(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split("_")
    # delete_confirm_<channel>_<country>
    channel = parts[2]
    country = "_".join(parts[3:])
    if not is_owner(user_id):
        return
    ch = _channel_dict(channel)
    if country in ch:
        q = ch[country]["quantity"]; p = ch[country]["price"]
        await log_country_deleted(context, country, q, p, channel=channel)
        del ch[country]
        save_data(data)
        text = f"✅ Deleted from {channel.upper()}: {country}"
    else:
        text = "❌ Not found."
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]), parse_mode='Markdown')

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
        f"✅ Discount Applied!\n🎟 Code: `{code}`\n💰 ₹{da}.00",
        parse_mode='Markdown'
    )
    clear_user_state(user_id)
    return ConversationHandler.END

# =========================================================
# =============== 🤖 AI MANAGEMENT (GROUPS) ===============
# =========================================================
"""
AI runs ONLY in groups (not DM). Triggers:
  • Bot @username mentioned in the message
  • The message is a REPLY to any bot message
  • Free-form message that clearly needs help (heuristic keywords)

Owner controls: /ai on  |  /ai off
Memory: per-user (chat_id keyed by user id), stored in data['ai_memory']
AI never uses emojis. AI never spams owner tag — only when strictly needed.
"""

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

def _user_context_snapshot(user_id):
    u = data["users"].get(str(user_id), {})
    purchases = u.get("purchases", [])
    last_purchases = []
    for p in purchases[-3:]:
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
    return {
        "user_id": user_id,
        "username": u.get("username", f"User_{user_id}"),
        "balance": u.get("balance", 0),
        "last_purchases": last_purchases,
        "pending_payment": pending_summary
    }

def _ai_should_answer_freeform(text_lower):
    """Heuristic: message that clearly needs help, without tag/reply."""
    if not text_lower:
        return False
    triggers = [
        "help", "problem", "issue", "not working", "kaam nahi", "kaam nhi",
        "not received", "nahi mila", "nhi aaya", "nhi aya", "nhi mila",
        "payment", "fund", "add funds", "balance", "otp nahi", "otp nhi",
        "buy account", "resale", "kaise", "how to", "kaise karu", "kaise kare",
        "confusion", "confused", "samajh nahi", "samajh nhi", "please help",
        "owner", "kon owner", "who is owner", "malik", "support chahiye"
    ]
    return any(t in text_lower for t in triggers)

def _bot_username_from_context(context):
    try:
        return (context.bot.username or "").lower()
    except:
        return ""

async def _call_groq_ai(system_prompt, history_messages, user_message):
    """Call Groq chat completions. Returns text or None on failure."""
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
        "max_tokens": 500
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
    """Vision analysis (used when AI thinks it must look at a screenshot)."""
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

def _build_ai_system_prompt(user_snapshot):
    """Professional, no-emoji, memory-aware system prompt."""
    return (
        "You are a professional, calm, human-like support assistant for a Telegram bot called Zudo OTP Bot.\n"
        "Style rules (STRICT):\n"
        "- Never use emojis at all.\n"
        "- Match the user's tone (Hinglish or English) but stay polite and professional.\n"
        "- Keep replies short, precise, direct. No filler.\n"
        "- Never reveal internal admin data, API keys, session strings, or secrets.\n"
        "- Never invent user data. Only use the JSON snapshot provided.\n"
        "- Never claim you performed an admin action; you can only guide or, in urgent cases, tag the owner.\n"
        f"- The owner of this bot is available at {OWNER_TG_LINK}. If asked 'who is the owner', reply exactly with the link: {OWNER_TG_LINK}.\n"
        "- Only tag the owner (mention @" + OWNER_TG_USERNAME + ") when strictly necessary — for example: a user says they paid but did not get balance, and the pending_payment snapshot supports it, or a genuine urgent stuck-payment. Do not tag owner casually.\n"
        "- Before requesting owner action, tell the user to confirm once (e.g. 'Please confirm the amount and UTR once, I will forward to the owner.').\n"
        "- If the user asks their balance, use the snapshot below to answer.\n"
        "- If the user asks about a recent action (e.g. 'what did I just do'), use the snapshot's last_purchases and pending_payment.\n"
        "- If a screenshot might be needed to help (e.g. payment issue), you may ask the user to share the payment screenshot in the group.\n\n"
        "Live user snapshot (JSON):\n"
        f"{json.dumps(user_snapshot, ensure_ascii=False)}\n"
    )

async def group_ai_handler(update, context):
    """Group-only AI. Runs in groups, never in DM."""
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

        # ensure user exists in db (so AI can see their data)
        get_user_data(user.id)
        data["users"][str(user.id)]["username"] = user.username or user.first_name or f"User_{user.id}"

        snapshot = _user_context_snapshot(user.id)
        entry = _ai_memory_get(user.id)
        system_prompt = _build_ai_system_prompt(snapshot)

        # If message is a photo (screenshot) and clearly about payment → use vision
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
                "recipient UPI id/name if visible, and payment status (success/failed/pending). Reply as short JSON like "
                "{\"amount\":..,\"utr\":\"..\",\"txn_id\":\"..\",\"to\":\"..\",\"status\":\"..\"}"
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
        if data_str.startswith("myserv_view_"):
            await myserv_view(update, context); return
        if data_str.startswith("ownserv_view_"):
            await ownserv_view(update, context); return
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

        # Resale channel
        if data_str.startswith("rcountry_"):
            fake_data = data_str.replace("rcountry_", "country_", 1)
            query.data = fake_data
            await show_account_details(update, context, channel="resale"); return
        if data_str.startswith("rbuy_number_"):
            fake_data = data_str.replace("rbuy_number_", "buy_number_", 1)
            query.data = fake_data
            return await process_buy_number(update, context, channel="resale")
        if data_str.startswith("rconfirm_buy_"):
            fake_data = data_str.replace("rconfirm_buy_", "confirm_buy_", 1)
            query.data = fake_data
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
            await query.answer("❌ Error occurred! Try /start", show_alert=True)
        except:
            pass

async def error_handler(update, context):
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("❌ Error occurred! Try /start")
        except:
            pass

# ============ GLOBAL TEXT FALLBACK ============
async def global_text_fallback(update, context):
    # In groups → forward to AI handler
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
            WAITING_FOR_ADD_MORE_SESSIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_add_more_choice)],
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

    # DM fallbacks (text + photo)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, global_text_fallback))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_photo_owner))

    # ✅ Group AI: any message in groups (text or photo) → AI handler
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO) & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        group_ai_handler
    ))

    application.add_error_handler(error_handler)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🔥 ZUDO OTP BOT — MongoDB + AI v6 🔥")
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
