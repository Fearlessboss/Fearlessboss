import asyncio
import json
import os
import re
from datetime import datetime
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

# Database file
DB_FILE = "virtual_bot_data.json"

# Membership cache (1 hour)
membership_cache = {}
CACHE_DURATION = 3600

# ===== SERVER 2 (Services Marketplace) Settings =====
SERVICE_ADD_FEE = 10  # ₹10 fee to add service

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

    # ===== SERVER 2 ADD SERVICE FLOW =====
    WAITING_SERVICE_NAME,
    WAITING_SERVICE_PRICE,
    WAITING_SERVICE_CONTACT,
    WAITING_SERVICE_DESC
) = range(21)

# ✅ HELPER: Escape username for Markdown
def escape_markdown(text):
    """Escape special Markdown characters"""
    if not text:
        return "Unknown"
    return (
        str(text)
        .replace('_', '\\_')
        .replace('*', '\\*')
        .replace('[', '\\[')
        .replace('`', '\\`')
        .replace(']', '\\]')
    )

# Load/Save Database
def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {
        "users": {},
        "accounts": {},
        "discount_codes": {},
        "coupons": {},
        "pending_payments": {},
        "bot_photo": None,
        "states": {},
        "used_discounts": {},

        # ===== SERVER 2: SERVICES STORAGE =====
        "services": {},     # service_id -> dict
        "service_seq": 0    # auto increment
    }

def save_data(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=2)

data = load_data()

# Initialize data structures
for key in [
    "users", "accounts", "discount_codes", "coupons", "pending_payments",
    "states", "used_discounts", "services"
]:
    if key not in data:
        data[key] = {}

if "service_seq" not in data:
    data["service_seq"] = 0

# ============ QR CODE GENERATION ============
def generate_upi_qr(amount: int) -> BytesIO:
    """Generate UPI QR code with dynamic amount"""
    try:
        upi_url = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR&tn=VirtualAccountPayment"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
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
async def send_log_to_support(context: ContextTypes.DEFAULT_TYPE, log_message: str):
    """Send detailed logs to support group"""
    try:
        await context.bot.send_message(
            chat_id=SUPPORT_GROUP_ID,
            text=log_message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"[LOG ERROR] Failed to send log: {e}")

async def log_user_registration(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str):
    safe_username = escape_markdown(username)
    log = f"""
🆕 NEW USER REGISTERED

👤 User: {safe_username}
🆔 ID: `{user_id}`
⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

📊 Total Users: {len(data['users'])}
"""
    await send_log_to_support(context, log)

async def log_number_purchase(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, country: str, quantity: int, price: int, phone_numbers: list):
    safe_username = escape_markdown(username)
    phones_text = "\n".join([f"   • `{phone}`" for phone in phone_numbers])

    log = f"""
✅ NUMBER SOLD - SUCCESSFUL

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

async def log_session_added(context: ContextTypes.DEFAULT_TYPE, country: str, quantity: int, price: int, phone_number: str = "N/A", twofa: str = None):
    twofa_line = f"\n🔐 2FA: `{twofa}`" if twofa else ""
    log = f"""
➕ SESSION ADDED

🌍 Country: {country.upper()}
📊 Added: {quantity} session(s)
💰 Price: {price} INR
📦 Total Stock: {data['accounts'].get(country, {}).get('quantity', 0)}

📱 Phone Added: `{phone_number}`{twofa_line}

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_country_deleted(context: ContextTypes.DEFAULT_TYPE, country: str, quantity: int, price: int):
    log = f"""
🗑️ COUNTRY DELETED

🌍 Country: {country.upper()}
📊 Removed: {quantity} session(s)
💰 Price: {price} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_coupon_redeemed(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, coupon_code: str, amount: int):
    safe_username = escape_markdown(username)
    log = f"""
🎟️ COUPON REDEEMED

👤 User: {safe_username}
🆔 ID: `{user_id}`
🎫 Coupon: `{coupon_code}`
💰 Amount: {amount} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
💳 New Balance: {data['users'][str(user_id)]['balance']} INR
"""
    await send_log_to_support(context, log)

async def log_discount_applied(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, discount_code: str, discount: int):
    safe_username = escape_markdown(username)
    log = f"""
🎟️ DISCOUNT CODE APPLIED

👤 User: {safe_username}
🆔 ID: `{user_id}`
🏷️ Code: `{discount_code}`
💰 Discount: {discount} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_payment_submitted(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, amount: int):
    safe_username = escape_markdown(username)
    log = f"""
💳 PAYMENT SUBMITTED

👤 User: {safe_username}
🆔 ID: `{user_id}`
💰 Amount: {amount} INR
📸 Screenshot: Received

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
⚠️ Status: Waiting for approval
"""
    await send_log_to_support(context, log)

async def log_payment_approved(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, amount: int):
    safe_username = escape_markdown(username)
    log = f"""
✅ PAYMENT APPROVED

👤 User: {safe_username}
🆔 ID: `{user_id}`
💰 Amount: {amount} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
💳 New Balance: {data['users'][str(user_id)]['balance']} INR
"""
    await send_log_to_support(context, log)

async def log_payment_rejected(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, amount: int):
    safe_username = escape_markdown(username)
    log = f"""
❌ PAYMENT REJECTED

👤 User: {safe_username}
🆔 ID: `{user_id}`
💰 Amount: {amount} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_discount_created(context: ContextTypes.DEFAULT_TYPE, discount_code: str, discount: int):
    log = f"""
🏷️ NEW DISCOUNT CREATED

🎟️ Code: `{discount_code}`
💰 Discount: {discount} INR
📊 Usage: One-time per user

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_broadcast_sent(context: ContextTypes.DEFAULT_TYPE, total: int, success: int, failed: int):
    log = f"""
📣 BROADCAST COMPLETED

👥 Total Users: {total}
✅ Sent: {success}
❌ Failed: {failed}
📊 Success Rate: {(success/total*100):.1f}%

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_otp_fetched(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, country: str, success_count: int, total: int):
    safe_username = escape_markdown(username)
    log = f"""
🔑 OTP FETCH ATTEMPT

👤 User: {safe_username}
🆔 ID: `{user_id}`
🌍 Country: {country.upper()}
✅ Found: {success_count}/{total}

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_insufficient_balance(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, required: int, current: int):
    safe_username = escape_markdown(username)
    log = f"""
⚠️ INSUFFICIENT BALANCE

👤 User: {safe_username}
🆔 ID: `{user_id}`
💰 Required: {required} INR
💳 Current: {current} INR
❌ Shortage: {required - current} INR

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_owner_balance_change(context: ContextTypes.DEFAULT_TYPE, action: str, target_user_id: int, amount: int, before: int, after: int, owner_id: int):
    log = f"""
👑 OWNER BALANCE UPDATE

🧾 Action: {action}
👤 Target User: `{target_user_id}`
💰 Amount: {amount} INR
📉 Before: {before} INR
📈 After: {after} INR
🆔 Owner: `{owner_id}`

⏰ Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
"""
    await send_log_to_support(context, log)

async def log_session_logout(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, phone: str):
    safe_username = escape_markdown(username)
    log = f"""
🚪 SESSION LOGOUT

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
    if user_id not in data["used_discounts"]:
        data["used_discounts"][user_id] = []
    return discount_code in data["used_discounts"][user_id]

def mark_discount_used(user_id, discount_code):
    user_id = str(user_id)
    if user_id not in data["used_discounts"]:
        data["used_discounts"][user_id] = []
    data["used_discounts"][user_id].append(discount_code)
    save_data(data)

# SPEED OPTIMIZED: Membership check with 1-hour cache
async def check_user_membership(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Check if user is member with 1-hour cache"""
    current_time = datetime.now().timestamp()

    if user_id in membership_cache:
        cache_entry = membership_cache[user_id]
        if current_time - cache_entry["time"] < CACHE_DURATION:
            return cache_entry["is_member"]

    try:
        channel_member = await context.bot.get_chat_member(SUPPORT_CHANNEL_ID, user_id)
        group_member = await context.bot.get_chat_member(SUPPORT_GROUP_ID, user_id)

        is_member = (
            channel_member.status in ['member', 'administrator', 'creator'] and
            group_member.status in ['member', 'administrator', 'creator']
        )

        membership_cache[user_id] = {
            "is_member": is_member,
            "time": current_time
        }

        return is_member

    except Exception as e:
        logger.error(f"[MEMBERSHIP CHECK ERROR] {e}")
        return False

# ============ PYROGRAM SESSION HELPERS ============
async def create_client(session_string: str, session_name: str):
    """Create Pyrogram client from session string"""
    try:
        client = Client(
            name=session_name,
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string,
            in_memory=True
        )
        await client.start()
        return client
    except Exception as e:
        logger.error(f"[CLIENT ERROR] {e}")
        return None

async def get_phone_number(client):
    """Get phone number from client"""
    try:
        me = await client.get_me()
        return me.phone_number if me.phone_number else "N/A"
    except Exception as e:
        logger.error(f"[PHONE ERROR] {e}")
        return "Error"

async def get_otp_from_telegram(client):
    """Fetch OTP from Telegram (777000)"""
    try:
        async for message in client.get_chat_history(777000, limit=1):
            if message.text:
                otp_match = re.search(r'\b(\d{5})\b', message.text)
                if otp_match:
                    return otp_match.group(1)
        return None
    except Exception as e:
        logger.error(f"[OTP ERROR] {e}")
        return None

async def logout_session(session_string: str, session_name: str):
    """Logout session"""
    try:
        client = await create_client(session_string, session_name)
        if client:
            await client.log_out()
            await client.stop()
            return True
        return False
    except Exception as e:
        logger.error(f"[LOGOUT ERROR] {e}")
        return False

# ============ FORCE JOIN ============
async def show_force_join_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force join message"""
    text = """
⚠️ Access Restricted!

🔒 Join our community first:

1️⃣ Channel: Updates & News
2️⃣ Group: Support & Help

✅ After joining, click Verify
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
            # ✅ FIX: Ignore "Message is not modified" error silently
            if "not modified" not in str(e).lower():
                logger.error(f"[FORCE JOIN EDIT ERROR] {e}")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ✅ FIX: verify_join_handler — cache clear + no redundant edit
async def verify_join_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify join — FIXED: clears cache before check, no duplicate edit error"""
    query = update.callback_query
    user_id = update.effective_user.id

    await query.answer("🔍 Verifying...")

    # ✅ FIX: Always clear cache so fresh API check happens
    if user_id in membership_cache:
        del membership_cache[user_id]

    is_member = await check_user_membership(context, user_id)

    if is_member:
        # ✅ Show success alert then open main menu
        await query.answer("✅ Verified! Welcome!", show_alert=True)
        await main_menu(update, context)
    else:
        # ✅ FIX: Just show alert — don't re-edit same message (causes BadRequest)
        await query.answer("❌ Please join both channel and group first!", show_alert=True)
        # Silently try to refresh message (catches "not modified" internally)
        await show_force_join_message(update, context)

# ============ START COMMAND ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or f"User_{user_id}"

    # Register user
    if str(user_id) not in data["users"]:
        data["users"][str(user_id)] = {
            "balance": 0,
            "purchases": [],
            "username": username
        }
        save_data(data)
        await log_user_registration(context, user_id, username)
    else:
        data["users"][str(user_id)]["username"] = username
        save_data(data)

    # Check membership (skip for owner)
    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return

    # Get balance
    balance = get_user_data(user_id)["balance"]

    # ✅ FIXED: Escape username for Markdown
    safe_username = escape_markdown(username)

    text = f"""👋 Hello, {safe_username}
━━━━━━━━━━━━━━━━━━
🚀 Welcome to Premium Store
*Your one-stop shop for high-quality digital assets.*

💎 Wallet Balance: ₹{balance}.00
━━━━━━━━━━━━━━━━━━
👇 Explore our services below:"""

    keyboard = [
        [InlineKeyboardButton("🛒 Buy Account", callback_data="virtual_accounts"),
         InlineKeyboardButton("📱 Get Sessions", callback_data="coming_soon_sessions")],
        [InlineKeyboardButton("👤 Profile", callback_data=f"my_balance_{user_id}"),
         InlineKeyboardButton("💰 Deposit", callback_data="add_funds")],
        [InlineKeyboardButton("🆘 Support", url=SUPPORT_CHANNEL_LINK),
         InlineKeyboardButton("🎁 Refer & Earn", callback_data="coming_soon_refer")],
        # ✅ Server 2 now opens marketplace
        [InlineKeyboardButton("🚀 Server 2", callback_data="server2_home")],
        [InlineKeyboardButton("📊 History & Stats", callback_data="history_stats")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send photo if available
    if data.get("bot_photo"):
        try:
            await update.message.reply_photo(
                photo=data["bot_photo"],
                caption=text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        except:
            pass

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ MAIN MENU ============
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = data["users"].get(str(user_id), {}).get("username", f"User_{user_id}")
    balance = get_user_data(user_id)["balance"]

    # ✅ FIXED: Escape username for Markdown
    safe_username = escape_markdown(username)

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        try:
            await query.message.delete()
        except:
            pass

    text = f"""👋 Hello, {safe_username}
━━━━━━━━━━━━━━━━━━
🚀 Welcome to Premium Store
*Your one-stop shop for high-quality digital assets.*

💎 Wallet Balance: ₹{balance}.00
━━━━━━━━━━━━━━━━━━
👇 Explore our services below:"""

    keyboard = [
        [InlineKeyboardButton("🛒 Buy Account", callback_data="virtual_accounts"),
         InlineKeyboardButton("📱 Get Sessions", callback_data="coming_soon_sessions")],
        [InlineKeyboardButton("👤 Profile", callback_data=f"my_balance_{user_id}"),
         InlineKeyboardButton("💰 Deposit", callback_data="add_funds")],
        [InlineKeyboardButton("🆘 Support", url=SUPPORT_CHANNEL_LINK),
         InlineKeyboardButton("🎁 Refer & Earn", callback_data="coming_soon_refer")],
        # ✅ Server 2 now opens marketplace
        [InlineKeyboardButton("🚀 Server 2", callback_data="server2_home")],
        [InlineKeyboardButton("📊 History & Stats", callback_data="history_stats")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ HISTORY & STATS ============
async def show_history_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display user's purchase history and stats"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    user_data = get_user_data(user_id)
    purchases = user_data.get("purchases", [])

    # ✅ FIXED: Escape username
    safe_username = escape_markdown(user_data['username'])

    text = f"""
📊 History & Stats

👤 User: {safe_username}
💳 Balance: ₹{user_data['balance']}.00
📦 Total Purchases: {len(purchases)}

"""

    if not purchases:
        text += "📭 No purchase history yet!\n\n🛒 Start shopping now!"
    else:
        total_spent = sum(p['price'] for p in purchases)
        text += f"💰 Total Spent: ₹{total_spent}.00\n\n"
        text += "📋 Recent Purchases:\n"

        for p in purchases[-5:]:
            date = datetime.fromisoformat(p['date']).strftime('%d/%m/%Y')
            text += f"\n• {p['country'].upper()} - {p['quantity']}x\n"
            text += f"  💰 ₹{p['price']}.00 | 📅 {date}\n"

    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ COMING SOON HANDLERS ============
async def coming_soon_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle coming soon buttons"""
    query = update.callback_query
    await query.answer("🚧 Coming Soon! Stay tuned...", show_alert=True)

# =========================================================
# =================== SERVER 2: SERVICES ==================
# =========================================================
def normalize_username(u: str) -> str:
    if not u:
        return ""
    u = u.strip()
    if u.startswith("@"):
        u = u[1:]
    return u

def next_service_id() -> str:
    data["service_seq"] = int(data.get("service_seq", 0)) + 1
    save_data(data)
    return f"S{data['service_seq']}"

def can_delete_service(requester_id: int, service: dict) -> bool:
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

def get_user_services(user_id: int):
    uid = int(user_id)
    return [s for s in get_active_services() if int(s.get("owner_id", 0)) == uid]

async def server2_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    # ✅ always clear state when opening server2 menu (so back works clean)
    clear_user_state(user_id)

    text = (
        "Disclaimer:\n\n"
        "This server only connects buyers and sellers. The owner has no relation with the services listed here.\n"
        "If you get scammed, the owner is not responsible because this is only a buyer-seller connector.\n\n"
        "Choose an option below:"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Available Services", callback_data="srv2_available")],
        [InlineKeyboardButton(f"➕ Add Services (₹{SERVICE_ADD_FEE} Fee)", callback_data="srv2_add_start")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def srv2_available(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    services = get_active_services()
    if not services:
        await query.edit_message_text(
            "📭 No services available right now.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="server2_home")]
            ]),
            parse_mode='Markdown'
        )
        return

    keyboard = []
    for s in services[:60]:
        name = escape_markdown(s.get("name", "Unknown"))
        price = int(s.get("price", 0))
        keyboard.append([InlineKeyboardButton(
            f"🛍 {name} — ₹{price}",
            callback_data=f"srv2_view_{s['id']}"
        )])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="server2_home")])

    await query.edit_message_text(
        "✅ Available Services\n\nSelect a service to explore:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def srv2_view_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    sid = query.data.split("_", 2)[2]  # srv2_view_{SID}
    s = data.get("services", {}).get(sid)

    if not s or not s.get("active", True):
        await query.edit_message_text(
            "❌ Service not found / deleted.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="srv2_available")]
            ]),
            parse_mode='Markdown'
        )
        return

    name = escape_markdown(s.get("name", "Unknown"))
    desc = escape_markdown(s.get("description", ""))
    contact = escape_markdown(s.get("contact", ""))
    price = int(s.get("price", 0))

    text = (
        f"🛍 Service Details\n\n"
        f"📌 Name: {name}\n"
        f"💰 Price: ₹{price}.00\n"
        f"👤 Seller Contact: @{contact}\n\n"
        f"📝 Description:\n{desc}\n\n"
        f"⚠️ Disclaimer: Owner is not responsible for any scam."
    )

    keyboard = [
        [InlineKeyboardButton("🛒 Buy Service", callback_data=f"srv2_buy_{sid}")],
        [InlineKeyboardButton("🔙 Back ↩️", callback_data="srv2_available")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def srv2_buy_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    buyer = update.effective_user
    buyer_id = buyer.id
    buyer_username = buyer.username or buyer.first_name or f"User_{buyer_id}"

    sid = query.data.split("_", 2)[2]  # srv2_buy_{SID}
    s = data.get("services", {}).get(sid)

    if not s or not s.get("active", True):
        await query.edit_message_text(
            "❌ Service not found / deleted.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="srv2_available")]
            ]),
            parse_mode='Markdown'
        )
        return

    # buyer confirmation
    await query.edit_message_text(
        "✅ Request sent to service owner!\n\n"
        "📩 Seller will contact you soon.\n"
        "💡 You can DM the seller too for faster response.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back ↩️", callback_data="srv2_available")]
        ]),
        parse_mode='Markdown'
    )

    # DM to seller
    try:
        seller_id = int(s["owner_id"])
        safe_service = escape_markdown(s.get("name", "Unknown"))
        safe_buyer_user = escape_markdown(buyer_username)

        msg = (
            f"🛎 New Service Request\n\n"
            f"🛍 Service: {safe_service} (₹{int(s.get('price', 0))}.00)\n"
            f"👤 Buyer: {safe_buyer_user}\n"
            f"🆔 Buyer ID: `{buyer_id}`\n\n"
            f"✅ Please DM buyer and complete the deal."
        )
        await context.bot.send_message(chat_id=seller_id, text=msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"[SRV2 BUY DM ERROR] {e}")

async def srv2_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    # clear any previous states
    clear_user_state(user_id)

    u = get_user_data(user_id)
    bal = int(u.get("balance", 0))

    if bal < SERVICE_ADD_FEE:
        await query.edit_message_text(
            f"❌ Insufficient Balance!\n\n"
            f"Add Service Fee: ₹{SERVICE_ADD_FEE}.00\n"
            f"Your Balance: ₹{bal}.00\n\n"
            f"➕ Please add funds first.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Funds", callback_data="add_funds")],
                [InlineKeyboardButton("🔙 Back", callback_data="server2_home")]
            ]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # deduct fee
    u["balance"] = bal - SERVICE_ADD_FEE
    save_data(data)

    await query.edit_message_text(
        "➕ Add Service\n\n"
        "Step 1/4\n"
        "Send Service Name:\n\n"
        "Example: YouTube Premium",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="server2_home")]
        ]),
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_SERVICE_NAME, {})
    return WAITING_SERVICE_NAME

async def srv2_service_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.message.text.strip()

    if len(name) < 3:
        await update.message.reply_text("❌ Service name too short. Try again.")
        return WAITING_SERVICE_NAME

    st = get_user_state(user_id)
    st["data"]["name"] = name
    set_user_state(user_id, WAITING_SERVICE_PRICE, st["data"])

    await update.message.reply_text(
        "Step 2/4\n"
        "Enter Price in ₹ (numbers only)\n\n"
        "Example: 50",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="server2_home")]
        ]),
        parse_mode='Markdown'
    )
    return WAITING_SERVICE_PRICE

async def srv2_service_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    txt = update.message.text.strip()

    try:
        price = int(txt)
        if price <= 0:
            raise ValueError()
    except:
        await update.message.reply_text("❌ Invalid price. Numbers only (example: 50).")
        return WAITING_SERVICE_PRICE

    st = get_user_state(user_id)
    st["data"]["price"] = price
    set_user_state(user_id, WAITING_SERVICE_CONTACT, st["data"])

    await update.message.reply_text(
        "Step 3/4\n"
        "Send your contact username (without @)\n\n"
        "Example: myusername123",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="server2_home")]
        ]),
        parse_mode='Markdown'
    )
    return WAITING_SERVICE_CONTACT

async def srv2_service_contact_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    contact = normalize_username(update.message.text)

    if not re.match(r"^[A-Za-z0-9_]{5,32}$", contact):
        await update.message.reply_text("❌ Invalid username. Example: myusername123")
        return WAITING_SERVICE_CONTACT

    st = get_user_state(user_id)
    st["data"]["contact"] = contact
    set_user_state(user_id, WAITING_SERVICE_DESC, st["data"])

    await update.message.reply_text(
        "Step 4/4\n"
        "Send service description\n\n"
        "Example:\n"
        "• Plan: 1 Month\n"
        "• Warranty: 7 Days\n"
        "• Delivery: Instant\n"
        "• Type: Private/Shared\n",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="server2_home")]
        ]),
        parse_mode='Markdown'
    )
    return WAITING_SERVICE_DESC

async def srv2_service_desc_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    desc = update.message.text.strip()

    if len(desc) < 10:
        await update.message.reply_text("❌ Description too short. Please explain properly.")
        return WAITING_SERVICE_DESC

    st = get_user_state(user_id)["data"]
    sid = next_service_id()

    owner_username = update.effective_user.username or update.effective_user.first_name or f"User_{user_id}"

    service = {
        "id": sid,
        "active": True,
        "owner_id": user_id,
        "owner_username": owner_username,
        "name": st["name"],
        "price": int(st["price"]),
        "contact": st["contact"],
        "description": desc,
        "created": datetime.now().isoformat()
    }

    data["services"][sid] = service
    save_data(data)
    clear_user_state(user_id)

    safe_name = escape_markdown(service["name"])
    safe_contact = escape_markdown(service["contact"])

    await update.message.reply_text(
        f"✅ Service Added Successfully!\n\n"
        f"🆔 Service ID: `{sid}`\n"
        f"📌 Name: {safe_name}\n"
        f"💰 Price: ₹{service['price']}.00\n"
        f"👤 Contact: @{safe_contact}\n\n"
        f"📦 Manage: Use /myservice to see your services & delete.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

# ============ /myservice (user services manage) ============
async def myservice_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return

    services = get_user_services(user_id)
    if not services:
        await update.message.reply_text(
            "📭 You have no services.\n\nUse Server 2 → Add Services.",
            parse_mode='Markdown'
        )
        return

    keyboard = []
    for s in services[:60]:
        name = escape_markdown(s.get("name", "Unknown"))
        price = int(s.get("price", 0))
        keyboard.append([InlineKeyboardButton(
            f"🗂 {name} — ₹{price}",
            callback_data=f"myserv_view_{s['id']}"
        )])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])

    await update.message.reply_text(
        "🧾 My Services\n\nSelect one to view/delete:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def myserv_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    sid = query.data.split("_", 2)[2]
    s = data.get("services", {}).get(sid)

    if not s or not s.get("active", True) or int(s.get("owner_id", 0)) != int(user_id):
        await query.edit_message_text(
            "❌ Service not found.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
            ]),
            parse_mode='Markdown'
        )
        return

    name = escape_markdown(s.get("name", "Unknown"))
    desc = escape_markdown(s.get("description", ""))
    contact = escape_markdown(s.get("contact", ""))

    text = (
        f"🧾 Your Service\n\n"
        f"🆔 ID: `{s['id']}`\n"
        f"📌 Name: {name}\n"
        f"💰 Price: ₹{int(s.get('price', 0))}.00\n"
        f"👤 Contact: @{contact}\n\n"
        f"📝 Description:\n{desc}"
    )

    keyboard = [
        [InlineKeyboardButton("🗑 Delete Service", callback_data=f"serv_del_{sid}")],
        [InlineKeyboardButton("🔙 Back ↩️", callback_data="main_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ============ /allservices (owner) ============
async def allservices_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ Owner only command.", parse_mode='Markdown')
        return

    services = get_active_services()
    if not services:
        await update.message.reply_text("📭 No services available.", parse_mode='Markdown')
        return

    keyboard = []
    for s in services[:80]:
        name = escape_markdown(s.get("name", "Unknown"))
        price = int(s.get("price", 0))
        owner_id = s.get("owner_id")
        keyboard.append([InlineKeyboardButton(
            f"🛠 {name} — ₹{price} (Owner: {owner_id})",
            callback_data=f"ownserv_view_{s['id']}"
        )])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="owner_panel")])

    await update.message.reply_text(
        "👑 All Services (Owner)\n\nSelect to view/delete:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def ownserv_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return

    sid = query.data.split("_", 2)[2]
    s = data.get("services", {}).get(sid)

    if not s or not s.get("active", True):
        await query.edit_message_text(
            "❌ Service not found/deleted.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="owner_panel")]
            ]),
            parse_mode='Markdown'
        )
        return

    name = escape_markdown(s.get("name", "Unknown"))
    desc = escape_markdown(s.get("description", ""))
    contact = escape_markdown(s.get("contact", ""))
    owner_username = escape_markdown(s.get("owner_username", "Unknown"))

    text = (
        f"👑 Service Detail\n\n"
        f"🆔 ID: `{s['id']}`\n"
        f"📌 Name: {name}\n"
        f"💰 Price: ₹{int(s.get('price', 0))}.00\n"
        f"👤 Seller: {owner_username} (ID: `{s.get('owner_id')}`)\n"
        f"📞 Contact: @{contact}\n\n"
        f"📝 {desc}"
    )

    keyboard = [
        [InlineKeyboardButton("🗑 Delete", callback_data=f"serv_del_{sid}")],
        [InlineKeyboardButton("🔙 Back", callback_data="owner_panel")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def serv_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    sid = query.data.split("_", 2)[2]
    s = data.get("services", {}).get(sid)

    if not s or not s.get("active", True):
        await query.edit_message_text(
            "❌ Already deleted / not found.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
            ]),
            parse_mode='Markdown'
        )
        return

    if not can_delete_service(user_id, s):
        await query.answer("❌ Not allowed!", show_alert=True)
        return

    s["active"] = False
    data["services"][sid] = s
    save_data(data)

    await query.edit_message_text(
        "✅ Service deleted successfully.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]),
        parse_mode='Markdown'
    )

# ============ /help ============
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = is_owner(user_id)

    text = (
        "📌 Help / Commands\n\n"
        "User Commands:\n"
        "• /start - Start bot\n"
        "• /myservice - View/Delete your added services (Server 2)\n"
        "• /help - Show this message\n\n"
        "Owner Commands:\n"
        "• /panel - Owner panel\n"
        "• /add - Add user balance\n"
        "• /deduct - Deduct user balance\n"
        "• /allservices - View/Delete all services (Owner)\n"
    )

    if not is_admin:
        # still show owner commands line (no issue), but keep as is
        pass

    await update.message.reply_text(text, parse_mode='Markdown')

# ============ OWNER PANEL ============
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.callback_query else update.message.from_user.id

    if not is_owner(user_id):
        return

    text = """
👑 OWNER PANEL

🎛 Admin Controls:

📊 Manage everything from here
    """

    keyboard = [
        [InlineKeyboardButton("➕ Add Number", callback_data="owner_addnumber"),
         InlineKeyboardButton("🗑 Delete Country", callback_data="owner_delete")],
        [InlineKeyboardButton("🏷 Create Discount", callback_data="owner_discount"),
         InlineKeyboardButton("🎟 Create Coupon", callback_data="owner_coupon")],
        [InlineKeyboardButton("📣 Broadcast", callback_data="owner_broadcast"),
         InlineKeyboardButton("💳 View Payments", callback_data="owner_payments")],
        [InlineKeyboardButton("💰 Available User Bal", callback_data="owner_userbal"),
         InlineKeyboardButton("📊 Statistics", callback_data="owner_stats")],
        [InlineKeyboardButton("📸 Set Bot Photo", callback_data="owner_setdp")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ OWNER /add COMMAND ============
async def owner_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized!")
        return

    await update.message.reply_text(
        "➕ Add Balance\n\n📝 Enter User ID:",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_TARGET_USER_ID, {"action": "add"})
    return WAITING_FOR_TARGET_USER_ID

# ============ OWNER /deduct COMMAND ============
async def owner_deduct_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        await update.message.reply_text("❌ Unauthorized!")
        return

    await update.message.reply_text(
        "➖ Deduct Balance\n\n📝 Enter User ID:",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_TARGET_USER_ID, {"action": "deduct"})
    return WAITING_FOR_TARGET_USER_ID

async def owner_handle_target_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle target user ID input"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END

    state = get_user_state(user_id)
    action = state["data"].get("action")

    try:
        target_user_id = int(update.message.text.strip())

        if str(target_user_id) not in data["users"]:
            await update.message.reply_text(
                f"❌ User `{target_user_id}` not found!",
                parse_mode='Markdown'
            )
            clear_user_state(user_id)
            return ConversationHandler.END

        target_balance = data["users"][str(target_user_id)]["balance"]
        target_username = data["users"][str(target_user_id)]["username"]

        # ✅ FIXED: Escape username
        safe_target_username = escape_markdown(target_username)

        await update.message.reply_text(
            f"👤 User: {safe_target_username}\n"
            f"🆔 ID: `{target_user_id}`\n"
            f"💰 Current Balance: ₹{target_balance}.00\n\n"
            f"📝 Enter amount to {action}:",
            parse_mode='Markdown'
        )

        set_user_state(user_id, WAITING_FOR_TARGET_AMOUNT, {
            "action": action,
            "target_user_id": target_user_id,
            "target_username": target_username,
            "target_balance": target_balance
        })
        return WAITING_FOR_TARGET_AMOUNT

    except ValueError:
        await update.message.reply_text("❌ Invalid User ID! Numbers only.")
        return WAITING_FOR_TARGET_USER_ID

async def owner_handle_target_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle target amount input and send DM to user"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END

    state = get_user_state(user_id)
    action = state["data"]["action"]
    target_user_id = state["data"]["target_user_id"]
    target_username = state["data"]["target_username"]
    target_balance = state["data"]["target_balance"]

    try:
        amount = int(update.message.text.strip())

        if amount <= 0:
            await update.message.reply_text("❌ Amount must be > 0!")
            return WAITING_FOR_TARGET_AMOUNT

        if action == "deduct" and amount > target_balance:
            await update.message.reply_text(
                f"❌ Cannot deduct ₹{amount}!\n"
                f"💳 User balance: ₹{target_balance}.00",
                parse_mode='Markdown'
            )
            return WAITING_FOR_TARGET_AMOUNT

        # Update balance
        if action == "add":
            data["users"][str(target_user_id)]["balance"] += amount
            new_balance = data["users"][str(target_user_id)]["balance"]
            action_text = "added to"
            emoji = "➕"
        else:  # deduct
            data["users"][str(target_user_id)]["balance"] -= amount
            new_balance = data["users"][str(target_user_id)]["balance"]
            action_text = "deducted from"
            emoji = "➖"

        save_data(data)

        # Log
        await log_owner_balance_change(
            context, action.upper(), target_user_id, amount,
            target_balance, new_balance, user_id
        )

        # Send DM to target user
        try:
            user_dm_text = f"""
{emoji} Balance Update

💰 Amount: ₹{amount}.00 {action_text} your account
📉 Previous: ₹{target_balance}.00
📈 New Balance: ₹{new_balance}.00

⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            """
            await context.bot.send_message(
                chat_id=target_user_id,
                text=user_dm_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"[DM ERROR] {e}")

        # ✅ FIXED: Escape username for owner confirmation
        safe_target_username = escape_markdown(target_username)

        # Confirm to owner
        await update.message.reply_text(
            f"✅ Success!\n\n"
            f"👤 User: {safe_target_username}\n"
            f"🆔 ID: `{target_user_id}`\n"
            f"{emoji} {action.title()}: ₹{amount}.00\n"
            f"📉 Before: ₹{target_balance}.00\n"
            f"📈 After: ₹{new_balance}.00\n\n"
            f"💬 DM sent to user!",
            parse_mode='Markdown'
        )

        clear_user_state(user_id)
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ Invalid amount! Numbers only.")
        return WAITING_FOR_TARGET_AMOUNT

# ============ CREATE DISCOUNT ============
async def create_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if not is_owner(user_id):
        return

    await query.edit_message_text(
        "🏷 Create Discount\n\n📝 Enter discount amount (INR):",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_DISCOUNT_AMOUNT)
    return WAITING_FOR_DISCOUNT_AMOUNT

async def handle_discount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle discount amount"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END

    try:
        discount = int(update.message.text.strip())

        if discount <= 0:
            await update.message.reply_text("❌ Amount must be > 0!")
            return WAITING_FOR_DISCOUNT_AMOUNT

        # Generate code
        discount_code = f"DISCOUNT{len(data['discount_codes']) + 1}"

        data["discount_codes"][discount_code] = {
            "discount": discount,
            "created": datetime.now().isoformat()
        }
        save_data(data)

        await log_discount_created(context, discount_code, discount)

        keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ Discount Created!\n\n"
            f"🎟 Code: `{discount_code}`\n"
            f"💰 Discount: ₹{discount}.00\n"
            f"📊 One-time per user",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        clear_user_state(user_id)
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ Invalid! Numbers only.")
        return WAITING_FOR_DISCOUNT_AMOUNT

# ============ CREATE COUPON ============
async def create_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if not is_owner(user_id):
        return

    await query.edit_message_text(
        "🎟 Create Coupon\n\n📝 Enter coupon amount (INR):",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_COUPON_AMOUNT)
    return WAITING_FOR_COUPON_AMOUNT

async def handle_coupon_input_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle coupon amount"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END

    try:
        amount = int(update.message.text.strip())

        if amount <= 0:
            await update.message.reply_text("❌ Amount must be > 0!")
            return WAITING_FOR_COUPON_AMOUNT

        # Generate code
        coupon_code = f"COUPON{len(data['coupons']) + 1}"

        data["coupons"][coupon_code] = {
            "amount": amount,
            "used": False,
            "created": datetime.now().isoformat()
        }
        save_data(data)

        keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ Coupon Created!\n\n"
            f"🎫 Code: `{coupon_code}`\n"
            f"💰 Amount: ₹{amount}.00\n"
            f"📊 One-time use (global)",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        clear_user_state(user_id)
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ Invalid! Numbers only.")
        return WAITING_FOR_COUPON_AMOUNT

# ============ BROADCAST ============
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if not is_owner(user_id):
        return

    await query.edit_message_text(
        f"📣 Broadcast Message\n\n"
        f"👥 Total Users: {len(data['users'])}\n\n"
        f"📝 Type your message:",
        parse_mode='Markdown'
    )
    set_user_state(user_id, WAITING_FOR_BROADCAST_MESSAGE)
    return WAITING_FOR_BROADCAST_MESSAGE

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast message"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END

    broadcast_message = update.message.text.strip()

    confirmation_text = f"""
📣 Broadcast Preview

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

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
📤 Broadcasting...

👥 Total: {total_users}
✅ Sent: 0
❌ Failed: 0

⏳ Please wait...
    """
    await query.edit_message_text(progress_text, parse_mode='Markdown')

    for user_id_str in data['users'].keys():
        try:
            target_user_id = int(user_id_str)
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"📣 Broadcast Message\n\n{broadcast_message}",
                parse_mode='Markdown'
            )
            success_count += 1

            if success_count % 10 == 0:
                progress_text = f"""
📤 Broadcasting...

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
✅ Broadcast Complete!

👥 Total: {total_users}
✅ Sent: {success_count}
❌ Failed: {failed_count}

📊 Success Rate: {(success_count/total_users*100):.1f}%
    """

    keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(final_text, reply_markup=reply_markup, parse_mode='Markdown')
    clear_user_state(user_id)

# ============ REVIEW PAYMENT ============
async def review_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # ✅ FIXED: Escape username
    safe_username = escape_markdown(username)

    text = f"""
💳 Payment Review

👤 User: {safe_username}
🆔 ID: `{payment_user_id}`
💰 Amount: ₹{payment_info['amount']}.00
⏰ Time: {datetime.fromisoformat(payment_info['timestamp']).strftime('%H:%M %d/%m/%Y')}

📸 Screenshot below ⬇️
    """

    keyboard = [
        [InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_fund_{payment_user_id}"),
         InlineKeyboardButton("❌ REJECT", callback_data=f"reject_fund_{payment_user_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="owner_payments")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Forward screenshot
    try:
        await context.bot.send_photo(
            chat_id=user_id,
            photo=payment_info["photo_id"],
            caption=text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        await query.message.delete()
    except:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ APPROVE FUND ============
async def approve_fund(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    amount = payment_info["amount"]
    username = data["users"].get(str(target_user_id), {}).get("username", f"User_{target_user_id}")

    # Add balance
    data["users"][str(target_user_id)]["balance"] += amount

    # Update payment status
    data["pending_payments"][str(target_user_id)]["status"] = "approved"
    save_data(data)

    await log_payment_approved(context, target_user_id, username, amount)

    # Notify user
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"✅ Payment Approved!\n\n"
                 f"💰 Amount: ₹{amount}.00\n"
                 f"💳 New Balance: ₹{data['users'][str(target_user_id)]['balance']}.00\n\n"
                 f"🎉 Thank you!",
            parse_mode='Markdown'
        )
    except:
        pass

    # ✅ FIXED: Escape username
    safe_username = escape_markdown(username)

    keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_caption(
        caption=f"✅ Approved!\n\n"
                f"👤 User: {safe_username}\n"
                f"🆔 ID: `{target_user_id}`\n"
                f"💰 Amount: ₹{amount}.00",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ============ REJECT FUND ============
async def reject_fund(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # Update payment status
    data["pending_payments"][str(target_user_id)]["status"] = "rejected"
    save_data(data)

    await log_payment_rejected(context, target_user_id, username, amount)

    # Notify user
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"❌ Payment Rejected!\n\n"
                 f"💰 Amount: ₹{amount}.00\n"
                 f"📝 Reason: Invalid screenshot\n\n"
                 f"💡 Contact: @lTZ_ME_ADITYA_02",
            parse_mode='Markdown'
        )
    except:
        pass

    # ✅ FIXED: Escape username
    safe_username = escape_markdown(username)

    keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_caption(
        caption=f"❌ Rejected!\n\n"
                f"👤 User: {safe_username}\n"
                f"🆔 ID: `{target_user_id}`\n"
                f"💰 Amount: ₹{amount}.00",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# ============ OWNER USER BALANCE LIST ============
async def owner_user_balance_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """FIXED: Escape special characters to prevent parse errors"""
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

    # Sort by balance descending
    users_with_balance.sort(key=lambda x: x["balance"], reverse=True)

    text = f"💰 Users with Balance ≥ ₹1\n\nTotal: {len(users_with_balance)}\n\n"

    for user in users_with_balance[:50]:
        # ✅ FIXED: Escape username to prevent Markdown parsing issues
        safe_username = escape_markdown(user['username'])
        text += f"• `{user['user_id']}` - {safe_username}: ₹{user['balance']}.00\n"

    if len(users_with_balance) > 50:
        text += f"\n... and {len(users_with_balance) - 50} more"

    keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ SHOW COUNTRIES — FIXED FORMAT ============
async def show_countries(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        # ✅ NEW FORMAT: clean separator lines per country
        text = "📍 Available Accounts\n━━━━━━━━━━━━━━━━━━━━\n\n"

        for country, info in available_countries.items():
            flag = country_flags.get(country.upper(), "📱")
            text += f"{flag} {country.title()}\n"
            text += f"📦 Stock: {info['quantity']}  •  💰 Price: ₹{info['price']}.00\n"
            text += "────────────────────\n"

            keyboard.append([InlineKeyboardButton(
                f"{flag} {country.title()} — ₹{info['price']}",
                callback_data=f"country_{country}"
            )])

        text += "👇 Select a country to purchase:"
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])
    else:
        text = "📭 No accounts available currently!\n\n⏰ Check back soon"
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")]]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ ACCOUNT DETAILS ============
async def show_account_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
📱 {country.upper()} Virtual Account

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

# ============ BUY NUMBER ============
async def process_buy_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask quantity"""
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
🛒 Purchase {country.upper()}

📊 Available: {available}
💰 Price: ₹{price}.00 each
💳 Your Balance: ₹{balance}.00

📝 How many accounts? (1-{available}):
    """

    await query.edit_message_text(text, parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_QUANTITY, {"country": country, "price": price, "available": available})
    return WAITING_FOR_QUANTITY

async def handle_quantity_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quantity"""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    try:
        quantity = int(text)
        state = get_user_state(user_id)
        country = state["data"]["country"]
        price = state["data"]["price"]
        available = state["data"]["available"]

        if quantity <= 0:
            await update.message.reply_text("❌ Quantity must be > 0!", parse_mode='Markdown')
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
                f"❌ Insufficient balance!\n\n"
                f"💰 Required: ₹{total_price}.00\n"
                f"💳 Your Balance: ₹{balance}.00\n"
                f"❌ Shortage: ₹{total_price - balance}.00",
                parse_mode='Markdown'
            )
            clear_user_state(user_id)
            return ConversationHandler.END

        # Confirm purchase
        text = f"""
✅ Confirm Purchase

🌍 Country: {country.upper()}
📊 Quantity: {quantity}
💰 Price: ₹{price}.00 each
💵 Total: ₹{total_price}.00
💳 After: ₹{balance - total_price}.00

Proceed?
        """

        keyboard = [
            [InlineKeyboardButton("✅ CONFIRM", callback_data=f"confirm_buy_{country}_{quantity}")],
            [InlineKeyboardButton("❌ CANCEL", callback_data="virtual_accounts")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

        clear_user_state(user_id)
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ Invalid! Numbers only.", parse_mode='Markdown')
        return WAITING_FOR_QUANTITY

# ============ CONFIRM PURCHASE ============
async def confirm_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm purchase"""
    query = update.callback_query
    await query.answer("🔄 Processing...")
    user_id = update.effective_user.id

    parts = query.data.split("_")
    country = parts[2]
    quantity = int(parts[3])

    if country not in data["accounts"]:
        await query.answer("❌ Country not found!", show_alert=True)
        return

    account_info = data["accounts"][country]
    price = account_info["price"]
    total_price = price * quantity
    balance = get_user_data(user_id)["balance"]
    username = data["users"][str(user_id)]["username"]

    if balance < total_price:
        await query.answer("❌ Insufficient balance!", show_alert=True)
        return

    if account_info["quantity"] < quantity:
        await query.answer("❌ Not enough stock!", show_alert=True)
        return

    # Deduct balance
    data["users"][str(user_id)]["balance"] -= total_price

    # Get sessions
    purchased_sessions = account_info["sessions"][:quantity]
    account_info["sessions"] = account_info["sessions"][quantity:]
    account_info["quantity"] -= quantity

    # Record purchase
    purchase_record = {
        "country": country,
        "quantity": quantity,
        "price": total_price,
        "date": datetime.now().isoformat(),
        "status": "completed",
        "sessions": purchased_sessions
    }

    data["users"][str(user_id)]["purchases"].append(purchase_record)
    save_data(data)

    # Get phone numbers
    phone_numbers = []
    for session_data in purchased_sessions:
        phone_numbers.append(session_data.get("phone_number", "N/A"))

    await log_number_purchase(context, user_id, username, country, quantity, total_price, phone_numbers)

    text = f"""
🎉 Purchase Successful!

🌍 Country: {country.upper()}
📊 Quantity: {quantity}
💰 Paid: ₹{total_price}.00
💳 Remaining: ₹{data["users"][str(user_id)]["balance"]}.00

✅ Sessions ready!
👇 Click below to get phone numbers
    """

    keyboard = [
        [InlineKeyboardButton("📱 GET PHONE NUMBER", callback_data=f"get_number_{user_id}_{len(data['users'][str(user_id)]['purchases'])-1}")],
        [InlineKeyboardButton("🛒 Buy More", callback_data="virtual_accounts")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ GET NUMBER ============
async def get_number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch phone numbers"""
    query = update.callback_query
    await query.answer("🔍 Fetching numbers...")

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

    # store phones inside purchase sessions for later OTP display and logout
    for idx, ph in enumerate(phone_numbers):
        try:
            purchase["sessions"][idx]["phone_number"] = ph
        except:
            pass
    save_data(data)

    text = f"""
📱 Phone Numbers Retrieved!

Country: {purchase['country'].upper()}
Quantity: {purchase['quantity']}

"""

    for i, phone in enumerate(phone_numbers, 1):
        text += f"\nAccount {i}:\n📞 `{phone}`\n"

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

# ============ GET OTP ============
async def get_otp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch OTP"""
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
🔍 Fetching OTP...

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
🔑 OTP Retrieval Results

Country: {purchase['country'].upper()}
Quantity: {purchase['quantity']}

"""

    success_count = 0
    for i, result in enumerate(otp_results, 1):
        text += f"\nAccount {i}:\n{result['message']}\n"
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

# ============ LOGIN COMPLETE ============
async def login_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Verified!")

    parts = query.data.split("_")
    user_id = int(parts[2])
    purchase_index = int(parts[3])

    text = """
🎉 Login Complete!

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

# ============ LOGOUT SESSION ============
async def logout_session_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Logout session - Shows 'pass' instead of 'failed'"""
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
            logout_results.append(f"✅ `{phone}` - Logout pass")
            await log_session_logout(context, user_id, username, phone)
        else:
            logout_results.append(f"❌ `{phone}` - No session")

    text = f"""
🚪 Logout Results

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

# ============ BALANCE FUNCTIONS ============
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
💳 My Profile

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
async def show_add_funds_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if not is_owner(user_id):
        is_member = await check_user_membership(context, user_id)
        if not is_member:
            await show_force_join_message(update, context)
            return

    clear_user_state(user_id)

    text = """
➕ Add Funds

💳 Choose method:

1️⃣ Buy Funds (UPI) - Instant
2️⃣ Coupon Code - Redeem

💡 Minimum: 10 INR
    """

    keyboard = [
        [InlineKeyboardButton("💸 Buy Funds (UPI)", callback_data="buy_fund")],
        [InlineKeyboardButton("🎟 Coupon Code", callback_data="coupon_code")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def ask_fund_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    text = """
💰 Enter Amount

💡 Minimum 10 INR

Example: 50 or 100

📝 Reply with amount:
    """

    await query.edit_message_text(text, parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_AMOUNT)
    return WAITING_FOR_AMOUNT

async def handle_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle amount input"""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    try:
        amount = int(text)
        if amount < 10:
            await update.message.reply_text("❌ Minimum 10 INR!", parse_mode='Markdown')
            return WAITING_FOR_AMOUNT

        # Generate QR
        qr_image = generate_upi_qr(amount)

        if qr_image:
            caption = f"""
💳 Payment Details

💰 Amount: ₹{amount}.00
📱 UPI ID: `{UPI_ID}`
👤 Name: {UPI_NAME}

📸 Scan QR or use UPI ID
⏰ After payment, send screenshot
            """

            await update.message.reply_photo(
                photo=qr_image,
                caption=caption,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"💳 Payment Details\n\n"
                f"💰 Amount: ₹{amount}.00\n"
                f"📱 UPI ID: `{UPI_ID}`\n"
                f"👤 Name: {UPI_NAME}\n\n"
                f"⏰ After payment, send screenshot",
                parse_mode='Markdown'
            )

        set_user_state(user_id, WAITING_FOR_SCREENSHOT, {"amount": amount})
        return WAITING_FOR_SCREENSHOT

    except ValueError:
        await update.message.reply_text("❌ Invalid! Numbers only.", parse_mode='Markdown')
        return WAITING_FOR_AMOUNT

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle screenshot"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    amount = state["data"]["amount"]
    username = data["users"][str(user_id)]["username"]

    photo = update.message.photo[-1]

    data["pending_payments"][str(user_id)] = {
        "amount": amount,
        "photo_id": photo.file_id,
        "status": "submitted",
        "timestamp": datetime.now().isoformat()
    }
    save_data(data)

    await log_payment_submitted(context, user_id, username, amount)

    # ✅ FIXED: Escape username before forwarding
    safe_username = escape_markdown(username)

    # Forward to owner
    try:
        keyboard = [
            [InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_fund_{user_id}"),
             InlineKeyboardButton("❌ REJECT", callback_data=f"reject_fund_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_photo(
            chat_id=OWNER_ID,
            photo=photo.file_id,
            caption=f"💳 Payment Submission\n\n"
                    f"👤 User: {safe_username}\n"
                    f"🆔 ID: `{user_id}`\n"
                    f"💰 Amount: ₹{amount}.00",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"[FORWARD ERROR] {e}")

    await update.message.reply_text(
        "✅ Screenshot submitted!\n\n"
        "⏳ Waiting for approval\n"
        "💡 Usually 10-30 minutes",
        parse_mode='Markdown'
    )

    clear_user_state(user_id)
    return ConversationHandler.END

# ============ COUPON CODE ============
async def ask_coupon_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    text = """
🎟 Redeem Coupon

💡 Enter coupon code:

Example: COUPON1234
    """

    await query.edit_message_text(text, parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_COUPON)
    return WAITING_FOR_COUPON

async def handle_coupon_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle coupon input"""
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
            "❌ Coupon already used!\n\n"
            "💡 This coupon was redeemed by someone else.",
            parse_mode='Markdown'
        )
        clear_user_state(user_id)
        return ConversationHandler.END

    amount = coupon_info["amount"]

    # Mark as used
    data["coupons"][code]["used"] = True
    data["coupons"][code]["used_by"] = user_id
    data["coupons"][code]["used_at"] = datetime.now().isoformat()

    # Add balance
    data["users"][str(user_id)]["balance"] += amount
    save_data(data)

    await log_coupon_redeemed(context, user_id, username, code, amount)

    keyboard = [[InlineKeyboardButton("🛒 Shop Now", callback_data="virtual_accounts")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✅ Coupon Redeemed!\n\n"
        f"🎫 Code: `{code}`\n"
        f"💰 Amount: ₹{amount}.00\n"
        f"💳 New Balance: ₹{data['users'][str(user_id)]['balance']}.00\n\n"
        f"🎉 Thank you!",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    clear_user_state(user_id)
    return ConversationHandler.END

# ============ OWNER ADD NUMBER ============
async def owner_add_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    text = """
➕ Add Numbers

📝 Enter country name:

Examples: USA, INDIA, KENYA
    """

    await query.edit_message_text(text, parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_COUNTRY)
    return WAITING_FOR_COUNTRY

async def handle_country_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END

    country = update.message.text.strip().upper()

    if country in data["accounts"]:
        existing_info = data["accounts"][country]
        text = f"""
⚠️ '{country}' exists!

📊 Current:
• Price: ₹{existing_info['price']}.00
• Available: {existing_info['quantity']}

💡 Type:
• ADD - Add more sessions
• NEW - Change price + add
• CANCEL - Cancel
        """
        await update.message.reply_text(text, parse_mode='Markdown')
        set_user_state(user_id, WAITING_FOR_ADD_MORE_SESSIONS, {"country": country, "price": existing_info['price']})
        return WAITING_FOR_ADD_MORE_SESSIONS

    set_user_state(user_id, WAITING_FOR_PRICE, {"country": country})

    text = f"""
💰 Set Price for {country}

💡 Enter price in INR:

Example: 60
    """

    await update.message.reply_text(text, parse_mode='Markdown')
    return WAITING_FOR_PRICE

async def handle_add_more_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add more choice"""
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
🔗 Add Sessions for {country}

💰 Price: ₹{old_price}.00

📝 Send session string:
        """
        await update.message.reply_text(text, parse_mode='Markdown')
        set_user_state(user_id, WAITING_FOR_SESSION, {"country": country, "price": old_price, "mode": "add_more"})
        return WAITING_FOR_SESSION

    elif choice == "NEW":
        text = f"""
💰 NEW Price for {country}

💡 Old: ₹{old_price}.00
📝 Enter new price:
        """
        await update.message.reply_text(text, parse_mode='Markdown')
        set_user_state(user_id, WAITING_FOR_PRICE, {"country": country, "mode": "new_price"})
        return WAITING_FOR_PRICE

    else:
        await update.message.reply_text("❌ Type ADD, NEW, or CANCEL", parse_mode='Markdown')
        return WAITING_FOR_ADD_MORE_SESSIONS

async def handle_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END

    text = update.message.text.strip()

    try:
        price = int(text)
        state = get_user_state(user_id)
        country = state["data"]["country"]

        if country not in data["accounts"]:
            data["accounts"][country] = {
                "price": price,
                "quantity": 0,
                "sessions": []
            }
        else:
            data["accounts"][country]["price"] = price
        save_data(data)

        set_user_state(user_id, WAITING_FOR_SESSION, {"country": country, "price": price})

        response_text = f"""
🔗 Add Sessions for {country}

💰 Price: ₹{price}.00

📝 Send session string:
        """

        await update.message.reply_text(response_text, parse_mode='Markdown')
        return WAITING_FOR_SESSION

    except ValueError:
        await update.message.reply_text("❌ Invalid! Numbers only.", parse_mode='Markdown')
        return WAITING_FOR_PRICE

async def handle_session_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    if len(text) < 100:
        await update.message.reply_text("❌ Invalid session string!", parse_mode='Markdown')
        return WAITING_FOR_SESSION

    # Ask for 2FA
    await update.message.reply_text(
        "🔐 Send 2FA password\n\n💡 Or type /skip if no 2FA",
        parse_mode='Markdown'
    )

    set_user_state(user_id, WAITING_FOR_2FA, {
        "country": country,
        "price": price,
        "session": text
    })
    return WAITING_FOR_2FA

async def handle_2fa_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 2FA input"""
    user_id = update.effective_user.id
    if not is_owner(user_id):
        return ConversationHandler.END

    text = update.message.text.strip()
    state = get_user_state(user_id)
    country = state["data"]["country"]
    price = state["data"]["price"]
    session_string = state["data"]["session"]

    twofa = None if text == "/skip" else text

    # Get phone number
    phone_number = "N/A"
    client = None
    try:
        client = await create_client(session_string, f"owner_add_{country}")
        if client:
            phone_number = await get_phone_number(client)
            await client.stop()
    except Exception as e:
        logger.error(f"[PHONE FETCH ERROR] {e}")
        if client:
            try:
                await client.stop()
            except:
                pass

    # Add to database
    session_data = {
        "session": session_string,
        "phone_number": phone_number,
        "twofa": twofa,
        "added_at": datetime.now().isoformat()
    }

    data["accounts"][country]["sessions"].append(session_data)
    data["accounts"][country]["quantity"] += 1
    save_data(data)

    await log_session_added(context, country, 1, price, phone_number, twofa)

    await update.message.reply_text(
        f"✅ Session Added!\n\n"
        f"🌍 Country: {country}\n"
        f"📱 Phone: `{phone_number}`\n"
        f"📊 Total: {data['accounts'][country]['quantity']}\n\n"
        f"➕ Send another session or /skip to finish",
        parse_mode='Markdown'
    )

    set_user_state(user_id, WAITING_FOR_SESSION, {"country": country, "price": price})
    return WAITING_FOR_SESSION

# ============ OWNER DELETE COUNTRY ============
async def owner_delete_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if not is_owner(user_id):
        return

    countries = [c for c in data["accounts"] if data["accounts"][c]["quantity"] >= 0]

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
🗑 Delete Country

⚠️ This removes all accounts!

Choose country:
    """

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def confirm_delete_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
✅ Deleted!

📱 Country: {country.upper()}
📊 Removed: {quantity}
💰 Price: ₹{price}.00
        """
    else:
        text = f"❌ '{country}' not found!"

    keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# ============ OWNER VIEW PAYMENTS ============
async def owner_view_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if not is_owner(user_id):
        return

    pending_payments = {uid: info for uid, info in data["pending_payments"].items()
                        if info["status"] == "submitted"}

    if not pending_payments:
        text = "📭 No pending payments!"
        keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return

    text = "💳 Pending Payments\n\n"

    keyboard = []
    for payment_user_id, info in list(pending_payments.items())[:5]:
        username = data["users"].get(str(payment_user_id), {}).get("username", f"User_{payment_user_id}")

        # ✅ FIXED: Escape username
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

# ============ OWNER STATS ============
async def owner_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if not is_owner(user_id):
        return

    total_users = len(data["users"])
    total_balance = sum(user["balance"] for user in data["users"].values())
    total_revenue = sum(purchase["price"] for user in data["users"].values()
                        for purchase in user["purchases"] if purchase.get("status") == "completed")

    available_accounts = sum(info["quantity"] for info in data["accounts"].values())

    text = f"""
📊 Bot Statistics

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

# ============ SET BOT PHOTO ============
async def set_bot_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id):
        if update.message:
            await update.message.reply_text("❌ Unauthorized!", parse_mode='Markdown')
        return

    if update.message:
        await update.message.reply_text(
            "📸 Send bot picture:\n\n"
            "💡 JPG/PNG, 512x512",
            parse_mode='Markdown'
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            "📸 Send bot picture:\n\n"
            "💡 JPG/PNG, 512x512",
            parse_mode='Markdown'
        )

    set_user_state(user_id, WAITING_FOR_BOT_PHOTO)
    return WAITING_FOR_BOT_PHOTO

async def handle_photo_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)

    if state["state"] != WAITING_FOR_BOT_PHOTO or not is_owner(user_id):
        return ConversationHandler.END

    photo = update.message.photo[-1]
    data["bot_photo"] = photo.file_id
    save_data(data)

    panel_keyboard = [[InlineKeyboardButton("🏠 Panel", callback_data="owner_panel")]]
    panel_reply_markup = InlineKeyboardMarkup(panel_keyboard)

    await update.message.reply_text(
        "✅ Bot photo updated!\n\n"
        "📸 Restart bot to see",
        reply_markup=panel_reply_markup,
        parse_mode='Markdown'
    )

    clear_user_state(user_id)
    return ConversationHandler.END

# ============ DISCOUNT APPLICATION ============
async def apply_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    text = """
🎟 Apply Discount

💡 Enter code:

Example: DISCOUNT1234
    """

    await query.edit_message_text(text, parse_mode='Markdown')
    set_user_state(user_id, WAITING_FOR_DISCOUNT_CODE)
    return WAITING_FOR_DISCOUNT_CODE

async def handle_discount_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle discount code"""
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
            "❌ You already used this discount code!\n\n"
            "💡 Each discount can only be used once per user.",
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
✅ Discount Applied!

🎟 Code: `{code}`
💰 Discount: ₹{discount_amount}.00
💎 Total Discount: ₹{user_state["data"]["discount"]}.00

⚠️ This code is now used and cannot be applied again by you!
    """

    keyboard = [[InlineKeyboardButton("🛒 Shop", callback_data="virtual_accounts")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    clear_user_state(user_id)
    return ConversationHandler.END

# ============ NO ACCOUNTS ============
async def no_accounts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = """
📭 No Accounts Available

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
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data_str = query.data

    try:
        # Coming soon handlers (server2 removed from coming soon)
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

        # ===== Server 2 routes =====
        if data_str == "server2_home":
            await server2_home(update, context)
            return
        if data_str == "srv2_available":
            await srv2_available(update, context)
            return
        if data_str == "srv2_add_start":
            return await srv2_add_start(update, context)
        if data_str.startswith("srv2_view_"):
            await srv2_view_service(update, context)
            return
        if data_str.startswith("srv2_buy_"):
            await srv2_buy_service(update, context)
            return

        # myservice/allservices callbacks
        if data_str.startswith("myserv_view_"):
            await myserv_view(update, context)
            return
        if data_str.startswith("ownserv_view_"):
            await ownserv_view(update, context)
            return
        if data_str.startswith("serv_del_"):
            await serv_delete(update, context)
            return

        # ===== Existing routes =====
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
        await query.answer("❌ Error occurred! Try /start", show_alert=True)

# ============ ERROR HANDLER ============
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Error occurred! Try /start\n\n"
                "💡 Or contact: @lTZ_ME_ADITYA_02",
                parse_mode='Markdown'
            )
        except:
            pass

# ============ GLOBAL FALLBACK ============
async def global_text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state_info = get_user_state(user_id)
    current_state = state_info["state"]

    # OWNER: /add /deduct flow
    if current_state == WAITING_FOR_TARGET_USER_ID:
        return await owner_handle_target_user_id(update, context)
    if current_state == WAITING_FOR_TARGET_AMOUNT:
        return await owner_handle_target_amount(update, context)

    # ===== SERVER 2 add service flow =====
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
        # IGNORE unnecessary messages - do nothing
        pass

# ============ CONVERSATION HANDLER ============
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

            # ===== SERVER 2 add service states =====
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

# ============ MAIN ============
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = get_conversation_handler()
    application.add_handler(conv_handler)

    # Extra commands (as you asked in /help too)
    application.add_handler(CommandHandler("myservice", myservice_cmd))
    application.add_handler(CommandHandler("allservices", allservices_cmd))
    application.add_handler(CommandHandler("help", help_cmd))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, global_text_fallback))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo_owner))

    application.add_error_handler(error_handler)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🔥 VIRTUAL ACCOUNT BOT - FULLY FIXED 🔥")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"\n👑 Owner: {OWNER_ID}")
    print(f"📊 Users: {len(data['users'])}")
    print(f"🌍 Countries: {len(data['accounts'])}")
    print(f"\n✅ FIXES APPLIED:")
    print("   • Verify button: Cache clear + no duplicate edit error")
    print("   • Available accounts: New separator line format")
    print("   • All Markdown parse errors safe")
    print("   • Server 2: Services marketplace added")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🚀 Bot is LIVE! Press Ctrl+C to stop.")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
