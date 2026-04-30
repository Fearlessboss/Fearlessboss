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

from pyrogram import Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
import logging
import qrcode

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "8309358322:AAFTTIQhHAIEy_7B42mspLUgBNClKFM1-ck"
OWNER_ID = 7661825494
API_ID = 33628258
API_HASH = "0850762925b9c1715b9b122f7b753128"

# Force Join Settings
SUPPORT_CHANNEL_ID = -1003782083448
SUPPORT_GROUP_ID = -1003857205137
SUPPORT_CHANNEL_LINK = "https://t.me/zudootp"
SUPPORT_GROUP_LINK = "https://t.me/zudootpsupport"

# UPI Details
UPI_ID = "fearlessaditya@fam"
UPI_NAME = "Aditya"

# ===== CHECKING SERVER CONFIG (HIDDEN FROM USERS - DO NOT EXPOSE) =====
GMAIL_EMAIL = "deviramrani489@gmail.com"
GMAIL_PASSWORD = "eprrbxhaibzwwhqv"
GMAIL_IMAP_SERVER = "imap.gmail.com"
GMAIL_IMAP_PORT = 993

# Database file
DB_FILE = "virtual_bot_data.json"

# Membership cache (1 hour)
membership_cache = {}
CACHE_DURATION = 3600

# ===== SERVER 2 (Services Marketplace) Settings =====
SERVICE_ADD_FEE = 10  # ₹10 fee to add service (charged ONLY after full add success)

# ===== PAYMENT VERIFICATION SETTINGS =====
MIN_DEPOSIT = 1                  # ✅ minimum deposit ₹1
AUTO_VERIFY_TIMEOUT = 10         # ✅ 10 seconds timeout for auto verification
UTR_MAX_AGE_HOURS = 1            # ✅ only accept Transaction ID from checking server in last 1 hour

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
    WAITING_FOR_UTR,    # ✅ now used for Transaction ID (letters + numbers mixed)

    # ===== SERVER 2 ADD SERVICE FLOW =====
    WAITING_SERVICE_NAME,
    WAITING_SERVICE_PRICE,
    WAITING_SERVICE_CONTACT,
    WAITING_SERVICE_DESC
) = range(22)

# ✅ HELPER: Escape username for Markdown
def escape_markdown(text):
    """Escape special Markdown characters"""
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

# Load/Save Database
def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[LOAD ERROR] {e}")
    return {
        "users": {},
        "accounts": {},
        "discount_codes": {},
        "coupons": {},
        "pending_payments": {},
        "bot_photo": None,
        "states": {},
        "used_discounts": {},
        "used_utrs": {},        # ✅ used Transaction ID (one-time-use)
        "services": {},
        "service_seq": 0
    }

def save_data(data):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"[SAVE ERROR] {e}")

data = load_data()

# ✅ FIXED: Force-correct types of all dict-like keys (prevent list-vs-dict TypeError)
_DICT_KEYS = [
    "users", "accounts", "discount_codes", "coupons", "pending_payments",
    "states", "used_discounts", "services", "used_utrs"
]
for _k in _DICT_KEYS:
    if _k not in data or not isinstance(data.get(_k), dict):
        data[_k] = {}

# Backward compatibility: migrate old key 'used_txn_ids' if present
if "used_txn_ids" in data and isinstance(data.get("used_txn_ids"), dict):
    for k, v in data["used_txn_ids"].items():
        data["used_utrs"][k] = v
    del data["used_txn_ids"]

if "service_seq" not in data or not isinstance(data.get("service_seq"), int):
    data["service_seq"] = 0

if "bot_photo" not in data:
    data["bot_photo"] = None

save_data(data)

# ============ RANDOM CODE GENERATOR (HARD TO GUESS) ============
def generate_random_code(prefix: str, length: int = 10) -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        random_part = ''.join(secrets.choice(alphabet) for _ in range(length))
        code = f"{prefix}{random_part}"
        if code not in data.get("coupons", {}) and code not in data.get("discount_codes", {}):
            return code

# ============ QR CODE GENERATION ============
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

# ============ LOGGING SYSTEM ============
async def send_log_to_support(context, log_message):
    try:
        await context.bot.send_message(
            chat_id=SUPPORT_GROUP_ID,
            text=log_message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"[LOG ERROR] {e}")
        # ✅ fallback: try plain text (no markdown) so log never fails silently
        try:
            await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                text=log_message,
                disable_web_page_preview=True
            )
        except Exception as e2:
            logger.error(f"[LOG FALLBACK ERROR] {e2}")

# ✅ NEW HELPER: send small log to user too (always, never skip)
async def send_user_log(context, user_id, log_message):
    """Send a small auto-approve / status log to user's DM. Always try, never silent."""
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

async def log_number_purchase(context, user_id, username, country, quantity, price, phone_numbers):
    safe_username = escape_markdown(username)
    phones_text = "\n".join([f"   • `{phone}`" for phone in phone_numbers])
    log = f"""
✅ *NUMBER SOLD - SUCCESSFUL*

👤 Buyer: {safe_username}
🆔 User ID: `{user_id}`
🌍 Country: {country.upper()}
📊 Quantity: {quantity}
💰 Amount: {price} INR

📱 Phone Numbers:
{phones_text}

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
💳 Remaining Balance: {data['users'][str(user_id)]['balance']} INR
📦 Stock Left: {data['accounts'].get(country, {}).get('quantity', 0)}
"""
    await send_log_to_support(context, log)

async def log_session_added(context, country, quantity, price, phone_number="N/A", twofa=None):
    twofa_line = f"\n🔐 2FA: `{twofa}`" if twofa else ""
    log = f"""
➕ *SESSION ADDED*

🌍 Country: {country.upper()}
📊 Added: {quantity} session(s)
💰 Price: {price} INR
📦 Total Stock: {data['accounts'].get(country, {}).get('quantity', 0)}

📱 Phone Added: `{phone_number}`{twofa_line}

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_country_deleted(context, country, quantity, price):
    log = f"""
🗑️ *COUNTRY DELETED*

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

async def log_auto_approve_attempt(context, user_id, username, amount, utr, status, reason=""):
    safe_username = escape_markdown(username)
    safe_reason = escape_markdown(reason) if reason else ""
    safe_utr = escape_markdown(str(utr)) if utr else "N/A"
    safe_status = escape_markdown(str(status))
    reason_line = f"\n📝 Reason: {safe_reason}" if reason else ""
    log = f"""
🤖 *AUTO APPROVE ATTEMPT*

👤 User: {safe_username}
🆔 ID: `{user_id}`
💰 Amount: {amount} INR
🔢 Transaction ID: `{safe_utr}`
📊 Status: {safe_status}{reason_line}

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

    # ✅ ALSO send a small log to user (always, never skip)
    user_log = (
        f"🤖 *Auto Approve Update*\n\n"
        f"💰 Amount: ₹{amount}.00\n"
        f"🔢 Transaction ID: `{safe_utr}`\n"
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
📊 Success Rate: {(success/total*100):.1f}%

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

# Helper Functions
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

# ✅ SAFE Transaction ID HELPERS
def is_utr_used(utr: str) -> bool:
    """Safely check if Transaction ID already used"""
    used = data.get("used_utrs", {})
    if not isinstance(used, dict):
        data["used_utrs"] = {}
        return False
    return utr.upper() in used

def get_utr_used_info(utr: str):
    """Get info about a used Transaction ID (or None)"""
    used = data.get("used_utrs", {})
    if not isinstance(used, dict):
        return None
    return used.get(utr.upper())

def mark_utr_used(utr: str, user_id: int, amount: int, mode: str = "auto"):
    """Safely mark Transaction ID as used (one-time-use, then expired)"""
    if not isinstance(data.get("used_utrs"), dict):
        data["used_utrs"] = {}
    data["used_utrs"][utr.upper()] = {
        "user_id": user_id,
        "amount": amount,
        "used_at": datetime.now().isoformat(),
        "mode": mode
    }
    save_data(data)

# ✅ Transaction ID validation: MUST be letters + numbers MIXED (alphanumeric, both required)
def is_valid_utr_format(utr: str) -> bool:
    """Transaction ID MUST contain BOTH letters AND digits (mixed). Pure-digit UTRs are rejected."""
    if not utr:
        return False
    utr = utr.strip()
    if len(utr) < 8 or len(utr) > 30:
        return False
    # must be alphanumeric only
    if not utr.isalnum():
        return False
    has_letter = any(c.isalpha() for c in utr)
    has_digit = any(c.isdigit() for c in utr)
    if not (has_letter and has_digit):
        return False
    return True

# SPEED OPTIMIZED: Membership check with 1-hour cache
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

# Pyrogram Helpers
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

# ============ CHECKING SERVER (mailbox) HELPERS ============
def _utr_in_text(utr, text):
    if not utr or not text:
        return False
    return utr.lower() in text.lower()

def _extract_amounts(text):
    """Extract any rupee amounts from text. Return list of floats."""
    found = []
    if not text:
        return found
    # patterns like Rs.500, ₹500, INR 500, 500.00
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

def _email_search_utr_sync(utr, expected_amount):
    """
    Synchronous checking-server check for given Transaction ID.
    Returns dict:
      {found, matched_amount, found_amount, too_old, error}
    """
    result = {
        "found": False,
        "matched_amount": False,
        "found_amount": None,
        "too_old": False,
        "error": None
    }
    try:
        mail = imaplib.IMAP4_SSL(GMAIL_IMAP_SERVER, GMAIL_IMAP_PORT)
        mail.login(GMAIL_EMAIL, GMAIL_PASSWORD)
        mail.select("INBOX")

        # only last UTR_MAX_AGE_HOURS
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
        # iterate newest first
        ids = list(reversed(ids))

        utr_str = str(utr)

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

                if _utr_in_text(utr_str, full):
                    # check email date inside last UTR_MAX_AGE_HOURS
                    date_hdr = msg.get("Date", "")
                    too_old = False
                    try:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(date_hdr)
                        if dt is not None:
                            # compare in naive utc-ish way
                            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                            if (now - dt).total_seconds() > UTR_MAX_AGE_HOURS * 3600:
                                too_old = True
                    except:
                        pass

                    result["found"] = True
                    if too_old:
                        result["too_old"] = True

                    found_amounts = _extract_amounts(full)
                    if found_amounts:
                        # take amount nearest UTR occurrence
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

async def auto_verify_utr(utr, expected_amount):
    """Async wrapper with timeout."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_email_search_utr_sync, utr, expected_amount),
            timeout=AUTO_VERIFY_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.error(f"[AUTO VERIFY] timeout >{AUTO_VERIFY_TIMEOUT}s for Transaction ID {utr}")
        return {
            "found": False, "matched_amount": False, "found_amount": None,
            "too_old": False, "error": "timeout"
        }
    except Exception as e:
        logger.error(f"[AUTO VERIFY ERROR] {e}")
        return {
            "found": False, "matched_amount": False, "found_amount": None,
            "too_old": False, "error": f"system:{str(e)[:60]}"
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

# ============ START COMMAND ============
async def start(update, context):
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

    keyboard = [
        [InlineKeyboardButton("🛒 Buy Account", callback_data="virtual_accounts"),
         InlineKeyboardButton("📱 Get Sessions", callback_data="coming_soon_sessions")],
        [InlineKeyboardButton("👤 Profile", callback_data=f"my_balance_{user_id}"),
         InlineKeyboardButton("💰 Deposit", callback_data="add_funds")],
        [InlineKeyboardButton("🆘 Support", url=SUPPORT_CHANNEL_LINK),
         InlineKeyboardButton("🎁 Refer & Earn", callback_data="coming_soon_refer")],
        [InlineKeyboardButton("🚀 Server 2", callback_data="server2_home")],
        [InlineKeyboardButton("📊 History & Stats", callback_data="history_stats")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

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

# ============ MAIN MENU ============
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

    keyboard = [
        [InlineKeyboardButton("🛒 Buy Account", callback_data="virtual_accounts"),
         InlineKeyboardButton("📱 Get Sessions", callback_data="coming_soon_sessions")],
        [InlineKeyboardButton("👤 Profile", callback_data=f"my_balance_{user_id}"),
         InlineKeyboardButton("💰 Deposit", callback_data="add_funds")],
        [InlineKeyboardButton("🆘 Support", url=SUPPORT_CHANNEL_LINK),
         InlineKeyboardButton("🎁 Refer & Earn", callback_data="coming_soon_refer")],
        [InlineKeyboardButton("🚀 Server 2", callback_data="server2_home")],
        [InlineKeyboardButton("📊 History & Stats", callback_data="history_stats")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

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

    # deduct fee NOW (after full success path)
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
    keyboard = [
        [InlineKeyboardButton("🗑 Delete", callback_data=f"serv_del_{sid}")]
    ]
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
    keyboard = [
        [InlineKeyboardButton("🗑 Delete", callback_data=f"serv_del_{sid}")]
    ]
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
    await query.edit_message_text(
        f"✅ Service `{sid}` deleted.",
        parse_mode='Markdown'
    )

async def help_cmd(update, context):
    text = (
        "🆘 *Help / Commands*\n\n"
        "/start - Start bot\n"
        "/panel - Owner panel\n"
        "/myservice - View your services\n"
        "/allservices - Owner: all services\n"
        "/add <user_id> <amount> - Owner: add balance\n"
        "/deduct <user_id> <amount> - Owner: deduct balance\n"
    )
    await update.message.reply_text(text, parse_mode='Markdown')

# ============ OWNER COMMANDS ============
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
        [InlineKeyboardButton("➕ Add Numbers", callback_data="owner_addnumber"),
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
            if amount < 1:
                await update.message.reply_text("❌ Amount must be > 0!")
                return
            if str(target_user_id) not in data["users"]:
                await update.message.reply_text("❌ User not found!")
                return
            target_balance = data["users"][str(target_user_id)]["balance"]
            data["users"][str(target_user_id)]["balance"] += amount
            new_balance = data["users"][str(target_user_id)]["balance"]
            save_data(data)
            target_username = data["users"][str(target_user_id)].get("username", f"User_{target_user_id}")
            await log_owner_balance_change(context, "ADD", target_user_id, amount, target_balance, new_balance, user_id)
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"➕ *Balance Update*\n\n💰 ₹{amount}.00 added.\n💳 New: ₹{new_balance}.00",
                    parse_mode='Markdown'
                )
            except:
                pass
            await update.message.reply_text(
                f"✅ Added ₹{amount} to `{target_user_id}` — new ₹{new_balance}.",
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text("❌ Usage: /add <user_id> <amount>")
    else:
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
            target_balance = data["users"][str(target_user_id)]["balance"]
            if amount > target_balance:
                await update.message.reply_text(f"❌ User has only ₹{target_balance}.")
                return
            data["users"][str(target_user_id)]["balance"] -= amount
            new_balance = data["users"][str(target_user_id)]["balance"]
            save_data(data)
            await log_owner_balance_change(context, "DEDUCT", target_user_id, amount, target_balance, new_balance, user_id)
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"➖ *Balance Update*\n\n💰 ₹{amount}.00 deducted.\n💳 New: ₹{new_balance}.00",
                    parse_mode='Markdown'
                )
            except:
                pass
            await update.message.reply_text(
                f"✅ Deducted ₹{amount} from `{target_user_id}` — new ₹{new_balance}.",
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
        set_user_state(user_id, WAITING_FOR_TARGET_AMOUNT, st["data"])
        await update.message.reply_text("💰 Send amount:")
        return WAITING_FOR_TARGET_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Numbers only.")
        return WAITING_FOR_TARGET_USER_ID

async def owner_handle_target_amount(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    try:
        amount = int(update.message.text.strip())
        st = get_user_state(user_id)
        target_user_id = st["data"]["target_user_id"]
        action = st["data"]["action"]
        target_balance = data["users"][str(target_user_id)]["balance"]
        target_username = data["users"][str(target_user_id)].get("username", f"User_{target_user_id}")
        if amount < 1:
            await update.message.reply_text("❌ Amount must be > 0!")
            return WAITING_FOR_TARGET_AMOUNT
        if action == "deduct" and amount > target_balance:
            await update.message.reply_text(
                f"❌ Cannot deduct ₹{amount}!\n💳 User balance: ₹{target_balance}.00",
                parse_mode='Markdown'
            )
            return WAITING_FOR_TARGET_AMOUNT
        if action == "add":
            data["users"][str(target_user_id)]["balance"] += amount
            new_balance = data["users"][str(target_user_id)]["balance"]
            action_text = "added to"
            emoji = "➕"
        else:
            data["users"][str(target_user_id)]["balance"] -= amount
            new_balance = data["users"][str(target_user_id)]["balance"]
            action_text = "deducted from"
            emoji = "➖"
        save_data(data)
        await log_owner_balance_change(context, action.upper(), target_user_id, amount, target_balance, new_balance, user_id)
        try:
            user_dm_text = f"""
{emoji} *Balance Update*

💰 Amount: ₹{amount}.00 {action_text} your account
📉 Previous: ₹{target_balance}.00
📈 New Balance: ₹{new_balance}.00

⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            """
            await context.bot.send_message(chat_id=target_user_id, text=user_dm_text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"[DM ERROR] {e}")
        safe_target_username = escape_markdown(target_username)
        await update.message.reply_text(
            f"✅ Success!\n\n👤 User: {safe_target_username}\n🆔 ID: `{target_user_id}`\n"
            f"{emoji} {action.title()}: ₹{amount}.00\n📉 Before: ₹{target_balance}.00\n"
            f"📈 After: ₹{new_balance}.00\n\n💬 DM sent to user!",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Invalid amount! Numbers only.")
        return WAITING_FOR_TARGET_AMOUNT

# ============ CREATE DISCOUNT ============
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
        keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"✅ Discount Created!\n\n🎟 Code: `{discount_code}`\n💰 Discount: ₹{discount}.00\n📊 One-time per user",
            reply_markup=reply_markup, parse_mode='Markdown'
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
        keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"✅ Coupon Created!\n\n🎫 Code: `{coupon_code}`\n💰 Amount: ₹{amount}.00\n📊 One-time use (global)",
            reply_markup=reply_markup, parse_mode='Markdown'
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
    confirmation_text = f"""
📣 *Broadcast Preview*

{broadcast_message[:500] if len(broadcast_message) > 500 else broadcast_message}

👥 Send to {len(data['users'])} users?
    """
    keyboard = [
        [InlineKeyboardButton("✅ SEND", callback_data=f"broadcast_confirm")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="owner_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(confirmation_text, reply_markup=reply_markup, parse_mode='Markdown')
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
    progress_text = f"""
📤 *Broadcasting...*

👥 Total: {total_users}
✅ Sent: 0
❌ Failed: 0

⏳ Please wait...
    """
    await query.edit_message_text(progress_text, parse_mode='Markdown')
    for user_id_str in list(data['users'].keys()):
        try:
            target_user_id = int(user_id_str)
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"📣 *Broadcast Message*\n\n{broadcast_message}",
                parse_mode='Markdown'
            )
            success_count += 1
            if success_count % 10 == 0:
                progress_text = f"""
📤 *Broadcasting...*

👥 Total: {total_users}
✅ Sent: {success_count}
❌ Failed: {failed_count}

⏳ In progress...
                """
                try:
                    await query.edit_message_text(progress_text, parse_mode='Markdown')
                except:
                    pass
            await asyncio.sleep(0.05)
        except Exception as e:
            failed_count += 1
            logger.error(f"[BROADCAST ERROR] User {user_id_str}: {e}")
    await log_broadcast_sent(context, total_users, success_count, failed_count)
    final_text = f"""
✅ *Broadcast Complete!*

👥 Total: {total_users}
✅ Sent: {success_count}
❌ Failed: {failed_count}

📊 Success Rate: {(success_count/total_users*100):.1f}%
    """
    keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(final_text, reply_markup=reply_markup, parse_mode='Markdown')
    clear_user_state(user_id)

# ============ REVIEW PAYMENT (OWNER) ============
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
    utr = payment_info.get("utr", payment_info.get("txn_id", "N/A"))
    safe_utr = escape_markdown(str(utr))
    text = f"""
💳 *Payment Review*

👤 User: {safe_username}
🆔 ID: `{payment_user_id}`
💰 Amount: ₹{payment_info['amount']}.00
🔢 Transaction ID: `{safe_utr}`
⏰ Time: {datetime.fromisoformat(payment_info['timestamp']).strftime('%H:%M %d/%m/%Y')}

📸 Screenshot below ⬇️
    """
    keyboard = [
        [InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_fund_{payment_user_id}"),
         InlineKeyboardButton("❌ REJECT", callback_data=f"reject_fund_{payment_user_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="owner_payments")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await context.bot.send_photo(
            chat_id=user_id, photo=payment_info["photo_id"],
            caption=text, reply_markup=reply_markup, parse_mode='Markdown'
        )
        await query.message.delete()
    except:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ APPROVE / REJECT FUND (MANUAL) ============
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
    if payment_info.get("status") not in ("submitted", "manual_review"):
        await query.answer("⚠️ Already processed!", show_alert=True)
        return
    amount = payment_info["amount"]
    username = data["users"].get(str(target_user_id), {}).get("username", f"User_{target_user_id}")
    utr = payment_info.get("utr", payment_info.get("txn_id", ""))

    data["users"][str(target_user_id)]["balance"] += amount
    data["pending_payments"][str(target_user_id)]["status"] = "approved"
    if utr:
        mark_utr_used(utr, target_user_id, amount, mode="manual")
    save_data(data)

    await log_payment_approved(context, target_user_id, username, amount, mode="MANUAL")
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"✅ *Payment Approved (Manual)!*\n\n💰 Amount: ₹{amount}.00\n"
                 f"💳 New Balance: ₹{data['users'][str(target_user_id)]['balance']}.00\n\n🎉 Thank you!",
            parse_mode='Markdown'
        )
    except:
        pass
    safe_username = escape_markdown(username)
    keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_caption(
            caption=f"✅ Approved!\n\n👤 User: {safe_username}\n🆔 ID: `{target_user_id}`\n💰 Amount: ₹{amount}.00",
            reply_markup=reply_markup, parse_mode='Markdown'
        )
    except:
        try:
            await query.edit_message_text(
                f"✅ Approved!\n\n👤 User: {safe_username}\n🆔 ID: `{target_user_id}`\n💰 Amount: ₹{amount}.00",
                reply_markup=reply_markup, parse_mode='Markdown'
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
            text=f"❌ *Payment Rejected!*\n\n💰 Amount: ₹{amount}.00\n"
                 f"📝 Reason: Invalid payment\n\n💡 Contact: @lTZ_ME_ADITYA_02",
            parse_mode='Markdown'
        )
    except:
        pass
    safe_username = escape_markdown(username)
    keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_caption(
            caption=f"❌ Rejected!\n\n👤 User: {safe_username}\n🆔 ID: `{target_user_id}`\n💰 Amount: ₹{amount}.00",
            reply_markup=reply_markup, parse_mode='Markdown'
        )
    except:
        try:
            await query.edit_message_text(
                f"❌ Rejected!\n\n👤 User: {safe_username}\n🆔 ID: `{target_user_id}`\n💰 Amount: ₹{amount}.00",
                reply_markup=reply_markup, parse_mode='Markdown'
            )
        except:
            pass

# ============ OWNER USER BALANCE LIST ============
async def owner_user_balance_list(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    users_with_balance = []
    for uid, user_data in data["users"].items():
        bal = user_data.get("balance", 0)
        if bal >= 1:
            users_with_balance.append({
                "user_id": uid,
                "username": user_data.get("username", f"User_{uid}"),
                "balance": bal
            })
    if not users_with_balance:
        text = "📭 No users with balance ≥ ₹1"
        keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    users_with_balance.sort(key=lambda x: x["balance"], reverse=True)
    text = f"💰 *Users with Balance ≥ ₹1*\n\nTotal: {len(users_with_balance)}\n\n"
    for user in users_with_balance[:50]:
        safe_username = escape_markdown(user['username'])
        text += f"• `{user['user_id']}` - {safe_username}: ₹{user['balance']}.00\n"
    if len(users_with_balance) > 50:
        text += f"\n... and {len(users_with_balance) - 50} more"
    keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ SHOW COUNTRIES ============
async def show_countries(update, context):
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
    available_countries = {c: info for c, info in data["accounts"].items() if info["quantity"] > 0}
    if available_countries:
        text = "📍 *Available Accounts*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for country, info in available_countries.items():
            flag = country_flags.get(country.upper(), "📱")
            text += f"{flag} *{country.title()}*\n"
            text += f"📦 Stock: {info['quantity']}  •  💰 Price: ₹{info['price']}.00\n"
            text += "────────────────────\n"
            keyboard.append([InlineKeyboardButton(
                f"{flag} {country.title()} — ₹{info['price']}",
                callback_data=f"country_{country}"
            )])
        text += "👇 Select a country to purchase:"
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])
    else:
        text = "📭 *No accounts available currently!*\n\n⏰ Check back soon"
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_account_details(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    country = query.data.split("_")[1]
    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return
    if country not in data["accounts"]:
        await query.edit_message_text("❌ Country not found!", parse_mode='Markdown')
        return
    account_info = data["accounts"][country]
    price = account_info["price"]
    balance = get_user_data(user_id)["balance"]
    text = f"""
📱 *{country.upper()} Virtual Account*

💰 Price: ₹{price}.00
📊 Available: {account_info['quantity']}
💳 Your Balance: ₹{balance}.00

✨ 100% Working Sessions
⚡ Instant OTP Delivery
🔒 Secure & Confidential
    """
    keyboard = [
        [InlineKeyboardButton("💳 BUY NUMBER", callback_data=f"buy_number_{country}")],
        [InlineKeyboardButton("🎟 DISCOUNT CODE", callback_data="discount")],
        [InlineKeyboardButton("🔙 Back", callback_data="virtual_accounts")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def process_buy_number(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    country = query.data.split("_")[2]
    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return ConversationHandler.END
    account_info = data["accounts"][country]
    price = account_info["price"]
    balance = get_user_data(user_id)["balance"]
    available = account_info["quantity"]
    text = f"""
🛒 *Purchase {country.upper()}*

📊 Available: {available}
💰 Price: ₹{price}.00 each
💳 Your Balance: ₹{balance}.00

📝 How many accounts? (1-{available}):
    """
    await query.edit_message_text(text, parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_QUANTITY, {"country": country, "price": price, "available": available})
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
        if quantity < 1:
            await update.message.reply_text("❌ Must be > 0!", parse_mode='Markdown')
            return WAITING_FOR_QUANTITY
        if quantity > available:
            await update.message.reply_text(f"❌ Only {available} available!", parse_mode='Markdown')
            return WAITING_FOR_QUANTITY
        total_price = price * quantity
        balance = get_user_data(user_id)["balance"]
        username = data["users"][str(user_id)]["username"]
        if balance < total_price:
            await log_insufficient_balance(context, user_id, username, total_price, balance)
            await update.message.reply_text(
                f"❌ Insufficient balance!\n\n💰 Need: ₹{total_price}.00\n💳 Have: ₹{balance}.00",
                parse_mode='Markdown'
            )
            clear_user_state(user_id)
            return ConversationHandler.END
        keyboard = [
            [InlineKeyboardButton("✅ CONFIRM", callback_data=f"confirm_buy_{country}_{quantity}")],
            [InlineKeyboardButton("❌ CANCEL", callback_data="virtual_accounts")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🛒 *Confirm Purchase*\n\n📱 Country: {country.upper()}\n📊 Quantity: {quantity}\n"
            f"💰 Total: ₹{total_price}.00\n💳 Balance: ₹{balance}.00\n\n✅ Confirm?",
            reply_markup=reply_markup, parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Numbers only!", parse_mode='Markdown')
        return WAITING_FOR_QUANTITY

async def confirm_purchase(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split("_")
    country = parts[2]
    quantity = int(parts[3])
    username = data["users"][str(user_id)]["username"]
    if country not in data["accounts"] or data["accounts"][country]["quantity"] < quantity:
        await query.edit_message_text("❌ Out of stock!", parse_mode='Markdown')
        return
    price_each = data["accounts"][country]["price"]
    total_price = price_each * quantity
    balance = get_user_data(user_id)["balance"]
    if balance < total_price:
        await log_insufficient_balance(context, user_id, username, total_price, balance)
        await query.edit_message_text(f"❌ Insufficient!", parse_mode='Markdown')
        return
    sessions_to_assign = data["accounts"][country]["sessions"][:quantity]
    data["accounts"][country]["sessions"] = data["accounts"][country]["sessions"][quantity:]
    data["accounts"][country]["quantity"] -= quantity
    data["users"][str(user_id)]["balance"] -= total_price
    purchase = {
        "country": country, "quantity": quantity, "price": total_price,
        "sessions": sessions_to_assign, "date": datetime.now().isoformat(), "status": "completed"
    }
    data["users"][str(user_id)]["purchases"].append(purchase)
    save_data(data)
    purchase_index = len(data["users"][str(user_id)]["purchases"]) - 1
    phone_numbers = []
    for s in sessions_to_assign:
        phone = s.get("phone_number", "Unknown")
        phone_numbers.append(phone)
    await log_number_purchase(context, user_id, username, country, quantity, total_price, phone_numbers)
    text = f"""
🎉 *Purchase Successful!*

📱 Country: {country.upper()}
📊 Quantity: {quantity}
💰 Total: ₹{total_price}.00
💳 New Balance: ₹{data['users'][str(user_id)]['balance']}.00

📞 Click below to get phone numbers:
    """
    keyboard = [
        [InlineKeyboardButton("📱 GET NUMBERS", callback_data=f"get_number_{user_id}_{purchase_index}")],
        [InlineKeyboardButton("🛒 Buy More", callback_data="virtual_accounts")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def get_number_handler(update, context):
    query = update.callback_query
    await query.answer("📱 Fetching numbers...")
    parts = query.data.split("_")
    user_id = int(parts[2])
    purchase_index = int(parts[3])
    user_purchases = data["users"][str(user_id)]["purchases"]
    if purchase_index >= len(user_purchases):
        await query.answer("❌ Purchase not found!", show_alert=True)
        return
    purchase = user_purchases[purchase_index]
    sessions = purchase.get("sessions", [])
    if not sessions:
        await query.answer("❌ No sessions!", show_alert=True)
        return

    async def fetch_phone(i, session_data):
        session_string = session_data.get("session")
        if session_string:
            try:
                client = await create_client(session_string, f"{user_id}_{i}")
                if client:
                    phone = await get_phone_number(client)
                    await client.stop()
                    return phone
            except:
                pass
        return "Error"

    tasks = [fetch_phone(i, s) for i, s in enumerate(sessions)]
    phone_numbers = await asyncio.gather(*tasks)
    for idx, ph in enumerate(phone_numbers):
        try:
            purchase["sessions"][idx]["phone_number"] = ph
        except:
            pass
    save_data(data)
    text = f"""
📱 *Phone Numbers Retrieved!*

Country: {purchase['country'].upper()}
Quantity: {purchase['quantity']}

"""
    for i, phone in enumerate(phone_numbers, 1):
        text += f"\n*Account {i}:*\n📞 `{phone}`\n"
    text += f"""

⚡ Next Steps:
1️⃣ Use numbers to login on Telegram
2️⃣ Click "GET OTP" for verification
3️⃣ Complete login
    """
    keyboard = [
        [InlineKeyboardButton("🔍 GET OTP", callback_data=f"get_otp_{user_id}_{purchase_index}")],
        [InlineKeyboardButton("✅ LOGIN COMPLETE", callback_data=f"login_complete_{user_id}_{purchase_index}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def get_otp_handler(update, context):
    query = update.callback_query
    await query.answer("🔍 Searching OTP...")
    parts = query.data.split("_")
    user_id = int(parts[2])
    purchase_index = int(parts[3])
    username = data["users"][str(user_id)]["username"]
    user_purchases = data["users"][str(user_id)]["purchases"]
    if purchase_index >= len(user_purchases):
        await query.answer("❌ Purchase not found!", show_alert=True)
        return
    purchase = user_purchases[purchase_index]
    sessions = purchase.get("sessions", [])
    country = purchase.get("country", "Unknown")
    if not sessions:
        await query.answer("❌ No sessions!", show_alert=True)
        return
    loading_text = f"""
🔍 *Fetching OTP...*

Country: {purchase['country'].upper()}
Quantity: {purchase['quantity']}

⏳ Checking Telegram (777000)...
💡 Make sure you started login!
    """
    await query.edit_message_text(loading_text, parse_mode='Markdown')

    async def fetch_otp(i, session_data):
        session_string = session_data.get("session")
        phone = session_data.get("phone_number", "N/A")
        twofa = session_data.get("twofa")
        if session_string:
            client = None
            try:
                client = await create_client(session_string, f"{user_id}_{i}_otp")
                if client:
                    if phone in ["N/A", None, "Error"]:
                        try:
                            phone = await get_phone_number(client)
                        except:
                            phone = session_data.get("phone_number", "N/A")
                    otp = await get_otp_from_telegram(client)
                    await client.stop()
                    if otp:
                        msg = f"✅ OTP: `{otp}` - `{phone}`"
                        if twofa:
                            msg += f"\n🔐 2FA: `{twofa}`"
                        return {"status": "success", "otp": otp, "phone": phone, "twofa": twofa, "message": msg}
                    msg = "⏳ OTP not found yet"
                    return {"status": "not_found", "otp": None, "phone": phone, "twofa": twofa, "message": msg}
            except Exception as e:
                if client:
                    try:
                        await client.stop()
                    except:
                        pass
                return {"status": "error", "otp": None, "phone": phone, "twofa": twofa, "message": f"❌ Error: {str(e)[:30]}"}
        return {"status": "error", "otp": None, "phone": phone, "twofa": twofa, "message": "❌ No session"}

    tasks = [fetch_otp(i, s) for i, s in enumerate(sessions)]
    otp_results = await asyncio.gather(*tasks)
    text = f"""
🔑 *OTP Retrieval Results*

Country: {purchase['country'].upper()}
Quantity: {purchase['quantity']}

"""
    success_count = 0
    for i, result in enumerate(otp_results, 1):
        text += f"\n*Account {i}:*\n{result['message']}\n"
        if result['status'] == 'success':
            success_count += 1
    await log_otp_fetched(context, user_id, username, country, success_count, len(sessions))
    if success_count > 0:
        text += f"\n✅ Found {success_count} OTP(s)!\n⏰ Use quickly (expires soon)"
    else:
        text += f"\n⚠️ No OTP found yet!\n💡 Start login first, then try again"
    keyboard = [
        [InlineKeyboardButton("🔄 TRY AGAIN", callback_data=f"get_otp_{user_id}_{purchase_index}")],
        [InlineKeyboardButton("✅ LOGIN COMPLETE", callback_data=f"login_complete_{user_id}_{purchase_index}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def login_complete(update, context):
    query = update.callback_query
    await query.answer("✅ Verified!")
    parts = query.data.split("_")
    user_id = int(parts[2])
    purchase_index = int(parts[3])
    text = """
🎉 *Login Complete!*

✅ Account activated!
✅ Ready to use!

💡 Keep sessions secure

⭐ Thank you!
    """
    keyboard = [
        [InlineKeyboardButton("🚪 LOGOUT BOT", callback_data=f"logout_session_{user_id}_{purchase_index}")],
        [InlineKeyboardButton("🛒 Buy More", callback_data="virtual_accounts")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def logout_session_handler(update, context):
    query = update.callback_query
    await query.answer("🚪 Logging out...")
    parts = query.data.split("_")
    user_id = int(parts[2])
    purchase_index = int(parts[3])
    username = data["users"][str(user_id)]["username"]
    user_purchases = data["users"][str(user_id)]["purchases"]
    if purchase_index >= len(user_purchases):
        await query.answer("❌ Purchase not found!", show_alert=True)
        return
    purchase = user_purchases[purchase_index]
    sessions = purchase.get("sessions", [])
    if not sessions:
        await query.answer("❌ No sessions!", show_alert=True)
        return
    logout_results = []
    for i, session_data in enumerate(sessions):
        session_string = session_data.get("session")
        phone = session_data.get("phone_number", "N/A")
        if session_string:
            success = await logout_session(session_string, f"{user_id}_{i}")
            logout_results.append(f"✅ {phone} - Logout pass")
            await log_session_logout(context, user_id, username, phone)
        else:
            logout_results.append(f"❌ {phone} - No session")
    text = f"""
🚪 *Logout Results*

Country: {purchase['country'].upper()}
Quantity: {purchase['quantity']}

"""
    text += "\n".join(logout_results)
    text += "\n\n✅ Sessions are now expired!"
    keyboard = [
        [InlineKeyboardButton("🛒 Buy More", callback_data="virtual_accounts")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

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
    text = f"""
💳 *My Profile*

💰 Current Balance: ₹{balance}.00

📊 Recent Transactions:
"""
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
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

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
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def ask_fund_amount(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    text = f"""
💰 *Enter Amount*

💡 Minimum {MIN_DEPOSIT} INR

Example: 1 or 50 or 100

📝 Reply with amount:
    """
    await query.edit_message_text(text, parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_AMOUNT)
    return WAITING_FOR_AMOUNT

async def handle_amount_input(update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    try:
        amount = int(text)
        if amount < MIN_DEPOSIT:
            await update.message.reply_text(
                f"❌ Minimum deposit ₹{MIN_DEPOSIT}!", parse_mode='Markdown'
            )
            return WAITING_FOR_AMOUNT

        # send QR code + UPI details
        qr_image = generate_upi_qr(amount)
        text_caption = f"""
💳 *Pay ₹{amount}.00 via UPI*

🆔 UPI ID: `{UPI_ID}`
👤 Name: {UPI_NAME}
💰 Amount: ₹{amount}.00

📱 Scan QR or copy UPI ID.

✅ After payment, send the *payment screenshot* here.
        """
        if qr_image:
            await update.message.reply_photo(
                photo=qr_image,
                caption=text_caption,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(text_caption, parse_mode='Markdown')

        set_user_state(user_id, WAITING_FOR_SCREENSHOT, {"amount": amount})
        return WAITING_FOR_SCREENSHOT
    except ValueError:
        await update.message.reply_text("❌ Numbers only!")
        return WAITING_FOR_AMOUNT

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

    # save pending payment (without txn id yet)
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

    await update.message.reply_text(
        f"✅ Screenshot received!\n\n"
        f"💰 Amount: ₹{amount}.00\n\n"
        f"🔢 Now send your *Transaction ID* (letters + numbers mixed).\n\n"
        f"💡 Example: `T2501ABCD1234XYZ` (must contain BOTH letters and digits)\n"
        f"⚠️ Pure-number UTR will NOT be accepted.\n"
        f"⚠️ Transaction ID must be from a payment made within the last {UTR_MAX_AGE_HOURS} hour.",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_UTR, {"amount": amount, "photo_id": photo_id})
    return WAITING_FOR_UTR

async def handle_utr_input(update, context):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if state["state"] != WAITING_FOR_UTR:
        return ConversationHandler.END

    raw = update.message.text.strip()
    utr = raw.upper()
    amount = state["data"].get("amount", 0)
    photo_id = state["data"].get("photo_id")
    username = data["users"][str(user_id)].get("username", f"User_{user_id}")
    safe_username = escape_markdown(username)

    # ====== Validate format: must be alphanumeric MIXED (letters + digits) ======
    if not is_valid_utr_format(utr):
        await update.message.reply_text(
            "❌ *Invalid Transaction ID format!*\n\n"
            "🔢 Transaction ID must contain *BOTH letters AND digits* (mixed alphanumeric).\n"
            "📏 Length: 8-30 characters.\n\n"
            "💡 Example: `T2501ABCD1234XYZ`\n\n"
            "📝 Please send a valid Transaction ID:",
            parse_mode='Markdown'
        )
        return WAITING_FOR_UTR

    # ====== Already used (one-time-use) ======
    if is_utr_used(utr):
        info = get_utr_used_info(utr) or {}
        await log_auto_approve_attempt(
            context, user_id, username, amount, utr,
            "REJECTED", "Transaction ID already used / expired"
        )
        await update.message.reply_text(
            f"❌ *This Transaction ID has already been used!*\n\n"
            f"🔒 Transaction IDs are one-time-use only.\n"
            f"💡 Please send a fresh new payment with a new Transaction ID.\n\n"
            f"📞 Contact: @lTZ_ME_ADITYA_02",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END

    # store utr in pending
    if str(user_id) not in data["pending_payments"]:
        data["pending_payments"][str(user_id)] = {}
    data["pending_payments"][str(user_id)].update({
        "amount": amount,
        "photo_id": photo_id,
        "utr": utr,
        "timestamp": datetime.now().isoformat(),
        "status": "submitted"
    })
    save_data(data)

    # ====== Tell user we are auto-verifying via checking server ======
    verifying_msg = await update.message.reply_text(
        f"🤖 *Auto-verifying your payment...*\n\n"
        f"💰 Amount: ₹{amount}.00\n"
        f"🔢 Transaction ID: `{escape_markdown(utr)}`\n\n"
        f"⏳ Checking on our checking server (max {AUTO_VERIFY_TIMEOUT}s)...",
        parse_mode='Markdown'
    )

    # ====== Run auto verify ======
    result = await auto_verify_utr(utr, amount)

    # ====== CASE 1: Found + amount matches → AUTO APPROVE ======
    if result.get("found") and result.get("matched_amount") and not result.get("too_old"):
        data["users"][str(user_id)]["balance"] += amount
        data["pending_payments"][str(user_id)]["status"] = "approved"
        mark_utr_used(utr, user_id, amount, mode="auto")
        save_data(data)

        await log_auto_approve_attempt(
            context, user_id, username, amount, utr,
            "AUTO APPROVED", "Transaction ID + amount match in checking server"
        )
        await log_payment_approved(context, user_id, username, amount, mode="AUTO")

        try:
            await verifying_msg.edit_text(
                f"✅ *Payment Auto-Approved!*\n\n"
                f"💰 Amount: ₹{amount}.00\n"
                f"💳 New Balance: ₹{data['users'][str(user_id)]['balance']}.00\n\n"
                f"🎉 Thank you!",
                parse_mode='Markdown'
            )
        except:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ *Payment Auto-Approved!*\n\n💰 Amount: ₹{amount}.00\n"
                         f"💳 New Balance: ₹{data['users'][str(user_id)]['balance']}.00",
                    parse_mode='Markdown'
                )
            except:
                pass

        clear_user_state(user_id)
        return ConversationHandler.END

    # ====== CASE 2: Found but amount mismatch → REJECT (do NOT send to owner) ======
    if result.get("found") and not result.get("matched_amount") and not result.get("too_old"):
        found_amt = result.get("found_amount")
        await log_auto_approve_attempt(
            context, user_id, username, amount, utr,
            "AMOUNT MISMATCH",
            f"Expected ₹{amount}, found ₹{found_amt} for this Transaction ID"
        )
        # mark this UTR used so user can't retry
        mark_utr_used(utr, user_id, amount, mode="auto_failed_mismatch")
        data["pending_payments"][str(user_id)]["status"] = "rejected_mismatch"
        save_data(data)

        try:
            await verifying_msg.edit_text(
                f"❌ *Auto Approval Failed — Amount Mismatch!*\n\n"
                f"💰 You entered amount: ₹{amount}.00\n"
                f"💰 Found in checking server: ₹{found_amt}\n\n"
                f"📝 Reason: The amount you entered does not match the payment.\n"
                f"🔒 This Transaction ID is now expired.\n\n"
                f"💡 Please make a *fresh deposit with the correct amount* and send the new Transaction ID.\n"
                f"📞 Contact: @lTZ_ME_ADITYA_02",
                parse_mode='Markdown'
            )
        except:
            pass
        clear_user_state(user_id)
        return ConversationHandler.END

    # ====== CASE 3: Found but too old (>1h) → REJECT (old Transaction ID) ======
    if result.get("too_old"):
        await log_auto_approve_attempt(
            context, user_id, username, amount, utr,
            "TXN ID TOO OLD", f"Transaction ID found but older than {UTR_MAX_AGE_HOURS}h"
        )
        mark_utr_used(utr, user_id, amount, mode="auto_failed_too_old")
        data["pending_payments"][str(user_id)]["status"] = "rejected_old_utr"
        save_data(data)

        try:
            await verifying_msg.edit_text(
                f"❌ *Auto Approval Failed — Old Transaction ID!*\n\n"
                f"📝 Reason: This Transaction ID is older than {UTR_MAX_AGE_HOURS} hour. "
                f"We only accept Transaction IDs from payments made in the last {UTR_MAX_AGE_HOURS} hour.\n\n"
                f"🔒 Transaction ID has been marked expired.\n\n"
                f"💡 Please make a fresh new payment and send its Transaction ID.\n"
                f"📞 Contact: @lTZ_ME_ADITYA_02",
                parse_mode='Markdown'
            )
        except:
            pass
        clear_user_state(user_id)
        return ConversationHandler.END

    # ====== CASE 4: Not found / timeout / error → INSTANT MANUAL REVIEW BY OWNER (within 10s) ======
    data["pending_payments"][str(user_id)]["status"] = "manual_review"
    save_data(data)

    err = result.get("error")
    if err == "timeout":
        fail_reason = f"Auto verify timeout ({AUTO_VERIFY_TIMEOUT}s) — sent to owner"
    elif err:
        fail_reason = f"System error: {err} — sent to owner"
    else:
        fail_reason = f"Transaction ID not found in last {UTR_MAX_AGE_HOURS}h checking server — sent to owner"

    await log_auto_approve_attempt(
        context, user_id, username, amount, utr,
        "MANUAL REVIEW", fail_reason
    )

    # ✅ Forward to owner with screenshot + manual approve buttons (instantly, within 10s)
    try:
        keyboard_owner = [
            [InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_fund_{user_id}"),
             InlineKeyboardButton("❌ REJECT", callback_data=f"reject_fund_{user_id}")]
        ]
        reply_markup_owner = InlineKeyboardMarkup(keyboard_owner)
        await context.bot.send_photo(
            chat_id=OWNER_ID,
            photo=photo_id,
            caption=f"💳 *Manual Payment Review*\n\n"
                    f"👤 User: {safe_username}\n"
                    f"🆔 ID: `{user_id}`\n"
                    f"💰 Amount: ₹{amount}.00\n"
                    f"🔢 Transaction ID: `{escape_markdown(utr)}`\n"
                    f"📝 Reason: {escape_markdown(fail_reason)}",
            reply_markup=reply_markup_owner,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"[FORWARD ERROR] {e}")
        # fallback: send as text only
        try:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=f"💳 Manual Payment Review (no photo)\n\n"
                     f"User: {username}\nID: {user_id}\nAmount: ₹{amount}.00\nTransaction ID: {utr}\nReason: {fail_reason}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_fund_{user_id}"),
                     InlineKeyboardButton("❌ REJECT", callback_data=f"reject_fund_{user_id}")]
                ])
            )
        except Exception as e2:
            logger.error(f"[FORWARD FALLBACK ERROR] {e2}")

    # ✅ Tell user clearly in DM: reason + sent to owner for manual approve
    user_msg = (
        f"⚠️ *Auto verification could not confirm your payment.*\n\n"
        f"📝 Reason: {escape_markdown(fail_reason)}\n\n"
        f"📨 Your payment has been sent to the owner for manual approval.\n"
        f"🕐 You will be notified here once it is approved.\n\n"
        f"💡 Contact: @lTZ_ME_ADITYA_02"
    )
    try:
        await verifying_msg.edit_text(user_msg, parse_mode='Markdown')
    except:
        try:
            await context.bot.send_message(chat_id=user_id, text=user_msg, parse_mode='Markdown')
        except:
            pass

    clear_user_state(user_id)
    return ConversationHandler.END

# ============ COUPON CODE ============
async def ask_coupon_code(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    text = """
🎟 *Redeem Coupon*

💡 Enter coupon code:
    """
    await query.edit_message_text(text, parse_mode='Markdown')
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
    coupon_info = data["coupons"][code]
    if coupon_info["used"]:
        await update.message.reply_text(
            "❌ *Coupon already used!*\n\n💡 This coupon was redeemed by someone else.",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    amount = coupon_info["amount"]
    data["coupons"][code]["used"] = True
    data["coupons"][code]["used_by"] = user_id
    data["coupons"][code]["used_at"] = datetime.now().isoformat()
    data["users"][str(user_id)]["balance"] += amount
    save_data(data)
    await log_coupon_redeemed(context, user_id, username, code, amount)
    keyboard = [[InlineKeyboardButton("🛒 Shop Now", callback_data="virtual_accounts")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ Coupon Redeemed!\n\n🎫 Code: `{escape_markdown(code)}`\n💰 Amount: ₹{amount}.00\n"
        f"💳 New Balance: ₹{data['users'][str(user_id)]['balance']}.00\n\n🎉 Thank you!",
        reply_markup=reply_markup, parse_mode='Markdown'
    )
    clear_user_state(user_id)
    return ConversationHandler.END

# ============ OWNER ADD NUMBER ============
async def owner_add_number(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    text = """
➕ *Add Numbers*

📝 Enter country name:

Examples: USA, INDIA, KENYA
    """
    await query.edit_message_text(text, parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_COUNTRY)
    return WAITING_FOR_COUNTRY

async def handle_country_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    country = update.message.text.strip().upper()
    if country in data["accounts"]:
        existing_info = data["accounts"][country]
        text = f"""
⚠️ *'{country}' exists!*

📊 Current:
• Price: ₹{existing_info['price']}.00
• Available: {existing_info['quantity']}

💡 Type:
• `ADD` - Add more sessions
• `NEW` - Change price + add
• `CANCEL` - Cancel
        """
        await update.message.reply_text(text, parse_mode='Markdown')
        set_user_state(user_id, WAITING_FOR_ADD_MORE_SESSIONS, {"country": country, "price": existing_info['price']})
        return WAITING_FOR_ADD_MORE_SESSIONS
    set_user_state(user_id, WAITING_FOR_PRICE, {"country": country})
    text = f"""
💰 *Set Price for {country}*

💡 Enter price in INR:

Example: 60
    """
    await update.message.reply_text(text, parse_mode='Markdown')
    return WAITING_FOR_PRICE

async def handle_add_more_choice(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    choice = update.message.text.strip().upper()
    state = get_user_state(user_id)
    country = state["data"]["country"]
    old_price = state["data"]["price"]
    if choice == "CANCEL":
        await update.message.reply_text("❌ Cancelled!", parse_mode='Markdown')
        clear_user_state(user_id)
        return ConversationHandler.END
    elif choice == "ADD":
        text = f"""
🔗 *Add Sessions for {country}*

💰 Price: ₹{old_price}.00

📝 Send session string:
        """
        await update.message.reply_text(text, parse_mode='Markdown')
        set_user_state(user_id, WAITING_FOR_SESSION, {"country": country, "price": old_price, "mode": "add_more"})
        return WAITING_FOR_SESSION
    elif choice == "NEW":
        text = f"""
💰 *NEW Price for {country}*

💡 Old: ₹{old_price}.00
📝 Enter new price:
        """
        await update.message.reply_text(text, parse_mode='Markdown')
        set_user_state(user_id, WAITING_FOR_PRICE, {"country": country, "mode": "new_price"})
        return WAITING_FOR_PRICE
    else:
        await update.message.reply_text("❌ Type ADD, NEW, or CANCEL", parse_mode='Markdown')
        return WAITING_FOR_ADD_MORE_SESSIONS

async def handle_price_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        price = int(text)
        state = get_user_state(user_id)
        country = state["data"]["country"]
        if country not in data["accounts"]:
            data["accounts"][country] = {"price": price, "quantity": 0, "sessions": []}
        else:
            data["accounts"][country]["price"] = price
        save_data(data)
        set_user_state(user_id, WAITING_FOR_SESSION, {"country": country, "price": price})
        response_text = f"""
🔗 *Add Sessions for {country}*

💰 Price: ₹{price}.00

📝 Send session string:
        """
        await update.message.reply_text(response_text, parse_mode='Markdown')
        return WAITING_FOR_SESSION
    except ValueError:
        await update.message.reply_text("❌ Invalid! Numbers only.", parse_mode='Markdown')
        return WAITING_FOR_PRICE

async def handle_session_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    text = update.message.text.strip()
    state = get_user_state(user_id)
    country = state["data"]["country"]
    price = state["data"]["price"]
    if text == "/skip" and state["state"] == WAITING_FOR_SESSION:
        clear_user_state(user_id)
        await update.message.reply_text(
            f"✅ Completed for {country}!\n\n" +
            "\n".join([f"• {c}: {info['quantity']} - ₹{info['price']}.00"
                      for c, info in data["accounts"].items()]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    if len(text) < 50:
        await update.message.reply_text("❌ Invalid session string.", parse_mode='Markdown')
        return WAITING_FOR_SESSION
    # ask 2FA
    state["data"]["pending_session"] = text
    set_user_state(user_id, WAITING_FOR_2FA, state["data"])
    await update.message.reply_text(
        "🔐 Send 2FA password for this session, or send `/skip` if none.",
        parse_mode='Markdown'
    )
    return WAITING_FOR_2FA

async def handle_2fa_input(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END
    text = update.message.text.strip()
    state = get_user_state(user_id)
    country = state["data"]["country"]
    price = state["data"]["price"]
    session_str = state["data"].get("pending_session")
    twofa = None if text == "/skip" else text

    # try to extract phone from session
    phone_number = "N/A"
    try:
        client = await create_client(session_str, f"add_{user_id}")
        if client:
            phone_number = await get_phone_number(client)
            await client.stop()
    except:
        pass

    if country not in data["accounts"]:
        data["accounts"][country] = {"price": price, "quantity": 0, "sessions": []}
    data["accounts"][country]["sessions"].append({
        "session": session_str,
        "phone_number": phone_number,
        "twofa": twofa
    })
    data["accounts"][country]["quantity"] += 1
    save_data(data)
    await log_session_added(context, country, 1, price, phone_number, twofa)
    await update.message.reply_text(
        f"✅ Session added!\n\n📱 Phone: `{phone_number}`\n"
        f"📊 Stock: {data['accounts'][country]['quantity']}\n\n"
        f"📝 Send another session string or `/skip` to finish.",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_SESSION, {"country": country, "price": price})
    return WAITING_FOR_SESSION

async def owner_delete_country(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    countries = [c for c, info in data["accounts"].items() if info["quantity"] >= 0]
    if not countries:
        text = "📭 No countries to delete!"
        keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    keyboard = []
    for country in countries:
        keyboard.append([InlineKeyboardButton(f"🗑 {country.upper()}", callback_data=f"delete_confirm_{country}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="owner_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = """
🗑 *Delete Country*

⚠️ This removes all accounts!

Choose country:
    """
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def confirm_delete_country(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    country = query.data.split("_")[2]
    if not is_owner(user_id):
        return
    if country in data["accounts"]:
        quantity = data["accounts"][country]["quantity"]
        price = data["accounts"][country]["price"]
        await log_country_deleted(context, country, quantity, price)
        del data["accounts"][country]
        save_data(data)
        text = f"""
✅ *Deleted!*

📱 Country: {country.upper()}
📊 Removed: {quantity}
💰 Price: ₹{price}.00
        """
    else:
        text = f"❌ '{country}' not found!"
    keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def owner_view_payments(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    pending_payments = {
        uid: info for uid, info in data["pending_payments"].items()
        if info["status"] in ("submitted", "manual_review")
    }
    if not pending_payments:
        text = "📭 No pending payments!"
        keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return
    text = "💳 *Pending Payments*\n\n"
    keyboard = []
    for payment_user_id, info in list(pending_payments.items())[:5]:
        username = data["users"].get(str(payment_user_id), {}).get("username", f"User_{payment_user_id}")
        safe_username = escape_markdown(username)
        amount = info["amount"]
        time = datetime.fromisoformat(info["timestamp"]).strftime('%H:%M %d/%m')
        text += f"👤 {safe_username}\n💰 ₹{amount}.00 - {time}\n\n"
        keyboard.append([InlineKeyboardButton(
            f"🔍 {username[:15]} - ₹{amount}",
            callback_data=f"review_payment_{payment_user_id}"
        )])
    keyboard.append([InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def owner_stats(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return
    total_users = len(data["users"])
    total_balance = sum(user["balance"] for user in data["users"].values())
    total_revenue = sum(
        purchase["price"] for user in data["users"].values()
        for purchase in user["purchases"] if purchase.get("status") == "completed"
    )
    available_accounts = sum(info["quantity"] for info in data["accounts"].values())
    text = f"""
📊 *Bot Statistics*

👥 Total Users: {total_users}
💰 User Balance: ₹{total_balance}.00
💵 Revenue: ₹{total_revenue}.00

📱 Available: {available_accounts}

🌍 By Country:
"""
    for country, info in data["accounts"].items():
        if info["quantity"] > 0:
            text += f"\n• {country}: {info['quantity']} - ₹{info['price']}.00"
    text += f"\n\n⏰ {datetime.now().strftime('%H:%M %d/%m/%Y')}"
    keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def set_bot_photo(update, context):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        if update.message:
            await update.message.reply_text("❌ Unauthorized!", parse_mode='Markdown')
        return
    if update.message:
        await update.message.reply_text("📸 Send bot picture:\n\n💡 JPG/PNG, 512x512", parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            "📸 Send bot picture:\n\n💡 JPG/PNG, 512x512", parse_mode='Markdown'
        )
    set_user_state(user_id, WAITING_FOR_BOT_PHOTO)
    return WAITING_FOR_BOT_PHOTO

async def handle_photo_owner(update, context):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    # If user is in screenshot upload state, route to handle_screenshot
    if state["state"] == WAITING_FOR_SCREENSHOT:
        return await handle_screenshot(update, context)
    if state["state"] != WAITING_FOR_BOT_PHOTO or not is_owner(user_id):
        return ConversationHandler.END
    photo = update.message.photo[-1]
    data["bot_photo"] = photo.file_id
    save_data(data)
    panel_keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    panel_reply_markup = InlineKeyboardMarkup(panel_keyboard)
    await update.message.reply_text(
        "✅ Bot photo updated!\n\n📸 Restart bot to see",
        reply_markup=panel_reply_markup, parse_mode='Markdown'
    )
    clear_user_state(user_id)
    return ConversationHandler.END

# ============ DISCOUNT APPLICATION ============
async def apply_discount(update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    text = """
🎟 *Apply Discount*

💡 Enter code:
    """
    await query.edit_message_text(text, parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_DISCOUNT_CODE)
    return WAITING_FOR_DISCOUNT_CODE

async def handle_discount_code(update, context):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    username = data["users"][str(user_id)]["username"]
    if state["state"] != WAITING_FOR_DISCOUNT_CODE:
        return ConversationHandler.END
    code = update.message.text.strip().upper()
    if code not in data["discount_codes"]:
        await update.message.reply_text("❌ Invalid code!", parse_mode='Markdown')
        clear_user_state(user_id)
        return ConversationHandler.END
    if has_used_discount(user_id, code):
        await update.message.reply_text(
            "❌ *You already used this discount code!*\n\n💡 Each discount can only be used once per user.",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END
    discount_info = data["discount_codes"][code]
    discount_amount = discount_info["discount"]
    mark_discount_used(user_id, code)
    user_state = get_user_state(user_id)
    if "discount" not in user_state["data"]:
        user_state["data"]["discount"] = 0
    user_state["data"]["discount"] += discount_amount
    set_user_state(user_id, user_state["state"], user_state["data"])
    await log_discount_applied(context, user_id, username, code, discount_amount)
    text = f"""
✅ *Discount Applied!*

🎟 Code: `{escape_markdown(code)}`
💰 Discount: ₹{discount_amount}.00
💎 Total Discount: ₹{user_state["data"]["discount"]}.00

⚠️ This code is now used and cannot be applied again by you!
    """
    keyboard = [[InlineKeyboardButton("🛒 Shop", callback_data="virtual_accounts")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    clear_user_state(user_id)
    return ConversationHandler.END

async def no_accounts_handler(update, context):
    query = update.callback_query
    await query.answer()
    text = """
📭 *No Accounts Available*

😔 Out of stock!

⏰ Check back in 30 min
    """
    keyboard = [
        [InlineKeyboardButton("➕ Add Funds", callback_data="add_funds")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ GENERIC BUTTON HANDLER ============
async def button_handler(update, context):
    query = update.callback_query
    user_id = update.effective_user.id
    data_str = query.data
    try:
        if data_str in ["coming_soon_sessions", "coming_soon_refer"]:
            await coming_soon_handler(update, context)
            return
        if data_str == "history_stats":
            await show_history_stats(update, context)
            return
        if data_str == "verify_join":
            await verify_join_handler(update, context)
            return
        if not is_owner(user_id):
            is_member = await check_user_membership(context, user_id)
            if not is_member:
                await query.answer("⚠️ Join channel & group first!", show_alert=True)
                await show_force_join_message(update, context)
                return
        # ===== Server 2 =====
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

        if data_str == "main_menu":
            await main_menu(update, context)
        elif data_str == "virtual_accounts":
            await show_countries(update, context)
        elif data_str.startswith("my_balance_"):
            await show_balance(update, context)
        elif data_str == "add_funds":
            await show_add_funds_options(update, context)
        elif data_str == "buy_fund":
            return await ask_fund_amount(update, context)
        elif data_str == "coupon_code":
            return await ask_coupon_code(update, context)
        elif data_str.startswith("country_"):
            await show_account_details(update, context)
        elif data_str.startswith("buy_number_"):
            return await process_buy_number(update, context)
        elif data_str.startswith("confirm_buy_"):
            await confirm_purchase(update, context)
        elif data_str.startswith("get_number_"):
            await get_number_handler(update, context)
        elif data_str.startswith("get_otp_"):
            await get_otp_handler(update, context)
        elif data_str.startswith("login_complete_"):
            await login_complete(update, context)
        elif data_str.startswith("logout_session_"):
            await logout_session_handler(update, context)
        elif data_str == "no_accounts":
            await no_accounts_handler(update, context)
        elif data_str == "owner_panel":
            await owner_panel(update, context)
        elif data_str == "owner_addnumber":
            return await owner_add_number(update, context)
        elif data_str == "owner_delete":
            await owner_delete_country(update, context)
        elif data_str.startswith("delete_confirm_"):
            await confirm_delete_country(update, context)
        elif data_str == "owner_discount":
            return await create_discount(update, context)
        elif data_str == "owner_coupon":
            return await create_coupon(update, context)
        elif data_str == "owner_broadcast":
            return await broadcast_start(update, context)
        elif data_str == "broadcast_confirm":
            await broadcast_confirm(update, context)
        elif data_str == "owner_payments":
            await owner_view_payments(update, context)
        elif data_str == "owner_stats":
            await owner_stats(update, context)
        elif data_str == "owner_userbal":
            await owner_user_balance_list(update, context)
        elif data_str == "owner_setdp":
            return await set_bot_photo(update, context)
        elif data_str.startswith("approve_fund_"):
            await approve_fund(update, context)
        elif data_str.startswith("reject_fund_"):
            await reject_fund(update, context)
        elif data_str.startswith("review_payment_"):
            await review_payment(update, context)
        elif data_str == "discount":
            return await apply_discount(update, context)
        else:
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
            await update.effective_message.reply_text(
                "❌ Error occurred! Try /start\n\n💡 Or contact: @lTZ_ME_ADITYA_02"
            )
        except:
            pass

async def global_text_fallback(update, context):
    user_id = update.effective_user.id
    state_info = get_user_state(user_id)
    current_state = state_info["state"]
    if current_state == WAITING_FOR_TARGET_USER_ID:
        return await owner_handle_target_user_id(update, context)
    if current_state == WAITING_FOR_TARGET_AMOUNT:
        return await owner_handle_target_amount(update, context)
    if current_state == WAITING_SERVICE_NAME:
        return await srv2_service_name_input(update, context)
    if current_state == WAITING_SERVICE_PRICE:
        return await srv2_service_price_input(update, context)
    if current_state == WAITING_SERVICE_CONTACT:
        return await srv2_service_contact_input(update, context)
    if current_state == WAITING_SERVICE_DESC:
        return await srv2_service_desc_input(update, context)
    if current_state == WAITING_FOR_AMOUNT:
        return await handle_amount_input(update, context)
    elif current_state == WAITING_FOR_UTR:
        return await handle_utr_input(update, context)
    elif current_state == WAITING_FOR_COUPON:
        return await handle_coupon_input(update, context)
    elif current_state == WAITING_FOR_COUNTRY:
        return await handle_country_input(update, context)
    elif current_state == WAITING_FOR_PRICE:
        return await handle_price_input(update, context)
    elif current_state == WAITING_FOR_SESSION:
        return await handle_session_input(update, context)
    elif current_state == WAITING_FOR_2FA:
        return await handle_2fa_input(update, context)
    elif current_state == WAITING_FOR_DISCOUNT_AMOUNT:
        return await handle_discount_input(update, context)
    elif current_state == WAITING_FOR_COUPON_AMOUNT:
        return await handle_coupon_input_owner(update, context)
    elif current_state == WAITING_FOR_DISCOUNT_CODE:
        return await handle_discount_code(update, context)
    elif current_state == WAITING_FOR_QUANTITY:
        return await handle_quantity_input(update, context)
    elif current_state == WAITING_FOR_ADD_MORE_SESSIONS:
        return await handle_add_more_choice(update, context)
    elif current_state == WAITING_FOR_BROADCAST_MESSAGE:
        return await handle_broadcast_message(update, context)
    else:
        pass

def get_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("panel", owner_panel),
            CommandHandler("add", owner_add_command),
            CommandHandler("deduct", owner_deduct_command),
            CallbackQueryHandler(button_handler)
        ],
        states={
            WAITING_FOR_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount_input)],
            WAITING_FOR_COUPON: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_coupon_input)],
            WAITING_FOR_SCREENSHOT: [MessageHandler(filters.PHOTO, handle_screenshot)],
            WAITING_FOR_UTR: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_utr_input)],
            WAITING_FOR_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_country_input)],
            WAITING_FOR_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price_input)],
            WAITING_FOR_SESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_session_input)],
            WAITING_FOR_2FA: [MessageHandler(filters.TEXT, handle_2fa_input)],
            WAITING_FOR_DISCOUNT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_discount_input)],
            WAITING_FOR_COUPON_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_coupon_input_owner)],
            WAITING_FOR_DISCOUNT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_discount_code)],
            WAITING_FOR_BOT_PHOTO: [MessageHandler(filters.PHOTO, handle_photo_owner)],
            WAITING_FOR_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quantity_input)],
            WAITING_FOR_ADD_MORE_SESSIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_more_choice)],
            WAITING_FOR_BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_message)],
            WAITING_FOR_TARGET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_handle_target_user_id)],
            WAITING_FOR_TARGET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_handle_target_amount)],
            WAITING_SERVICE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, srv2_service_name_input)],
            WAITING_SERVICE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, srv2_service_price_input)],
            WAITING_SERVICE_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, srv2_service_contact_input)],
            WAITING_SERVICE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, srv2_service_desc_input)],
        },
        fallbacks=[
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_text_fallback))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo_owner))
    application.add_error_handler(error_handler)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🔥 VIRTUAL ACCOUNT BOT - FULLY FIXED v4 🔥")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"\n👑 Owner: {OWNER_ID}")
    print(f"📊 Users: {len(data['users'])}")
    print(f"🌍 Countries: {len(data['accounts'])}")
    print(f"\n✅ FIXES (v4):")
    print(f"   • Transaction ID = letters + digits MIXED (alnum) — pure numbers rejected")
    print(f"   • Auto-verify timeout {AUTO_VERIFY_TIMEOUT}s → INSTANT manual review to OWNER DM")
    print(f"   • Checking server window: last {UTR_MAX_AGE_HOURS}h only")
    print("   • Auto approve → user gets DM notification (always)")
    print("   • All small auto-approve logs sent to user too (always)")
    print("   • Manual review → user gets DM: 'sent to owner for manual approve'")
    print("   • Amount mismatch → user DM: 'fresh deposit with correct amount'")
    print("   • Used / old Transaction ID → user DM with reason")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🚀 Bot is LIVE! Press Ctrl+C to stop.")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
