import os
import sys
import time
import datetime
import random
import string
import secrets
import re
import imaplib
import email
import sqlite3
import threading
import urllib.parse
import requests
from flask import Flask, request, jsonify
import telebot
from telebot import types
from cryptography.fernet import Fernet

# ==========================================
# ⚙️ CONFIGURATION & CONSTANTS
# ==========================================
RENDER_PORT = int(os.environ.get("PORT", 8081))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
MASTER_BOT_TOKEN = os.environ.get("MASTER_BOT_TOKEN", "").strip()
SUPER_ADMIN_ID = 8585055903 # Pranav Patel (प्रणव जी)
MAIN_PANEL_URL = os.environ.get("MAIN_PANEL_URL", "https://pranavsmm.shop/api/v2")
MAIN_PANEL_API_KEY = os.environ.get("MAIN_PANEL_API_KEY", "").strip()

SECRET_KEY = os.environ.get("SECRET_KEY", Fernet.generate_key().decode())
if isinstance(SECRET_KEY, str):
    SECRET_KEY = SECRET_KEY.encode()
cipher_suite = Fernet(SECRET_KEY)

DB_PATH = "pranav_godmode_engine.db"
app = Flask(__name__)

bot_threads = {}
user_states = {}
keypad_amounts = {}
master_is_running = False

# ==========================================
# 🗄️ BULLETPROOF DATABASE MANAGER (NO LOCKS)
# ==========================================
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.row_factory = sqlite3.Row
    return conn

def execute_query(query, params=(), commit=True):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        if commit: conn.commit()
        return cur.lastrowid
    except Exception as e:
        print(f"[DB EXEC ERROR] {e}")
    finally:
        conn.close()

def fetch_query(query, params=(), fetchone=False):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchone() if fetchone else cur.fetchall()
    except Exception as e:
        print(f"[DB FETCH ERROR] {e}")
        return None
    finally:
        conn.close()

def init_db():
    queries = [
        """CREATE TABLE IF NOT EXISTS child_bots (bot_id INTEGER PRIMARY KEY, owner_id INTEGER, bot_token_enc TEXT UNIQUE, bot_username TEXT, bot_name TEXT, pro_mode INTEGER DEFAULT 1, log_channel TEXT DEFAULT '', force_channel TEXT DEFAULT '', support_wa TEXT DEFAULT '', support_tg TEXT DEFAULT '', active_gateway TEXT DEFAULT 'paytm', paytm_mid TEXT DEFAULT 'WWRYwl67445982860121', paytm_upi TEXT DEFAULT 'paytm.s2xzkgu@pty', bharatpe_mid TEXT DEFAULT '', bharatpe_token TEXT DEFAULT '', subscription_expiry TIMESTAMP, is_licensed INTEGER DEFAULT 0, status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS license_keys (key_code TEXT PRIMARY KEY, duration_days INTEGER DEFAULT 30, used_by_bot_id INTEGER DEFAULT NULL, used_by_user_id INTEGER DEFAULT NULL, is_used INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS key_pricing (duration_days INTEGER PRIMARY KEY, price REAL, label TEXT)""",
        """CREATE TABLE IF NOT EXISTS bot_clients (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, user_id INTEGER, username TEXT, balance REAL DEFAULT 0.0, total_deposit REAL DEFAULT 0.0, total_spent REAL DEFAULT 0.0, banned INTEGER DEFAULT 0, upi_pin TEXT DEFAULT '', failed_pin_attempts INTEGER DEFAULT 0, pin_locked_until TIMESTAMP DEFAULT NULL, UNIQUE(bot_id, user_id))""",
        """CREATE TABLE IF NOT EXISTS master_services (id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, sub_category TEXT, service_name TEXT, main_api_service_id TEXT UNIQUE, base_rate_per_100 REAL DEFAULT 1.0, min_qty INTEGER DEFAULT 100, max_qty INTEGER DEFAULT 1000000, description TEXT DEFAULT 'Live Fast Speed Non Drop')""",
        """CREATE TABLE IF NOT EXISTS child_services (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, master_service_id INTEGER, selling_price_per_100 REAL DEFAULT 3.0, custom_description TEXT DEFAULT '', is_published INTEGER DEFAULT 1, UNIQUE(bot_id, master_service_id))""",
        """CREATE TABLE IF NOT EXISTS bot_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, user_id INTEGER, service_name TEXT, link TEXT, quantity INTEGER, charge REAL, api_order_id TEXT, status TEXT DEFAULT 'Pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS transactions (tx_id TEXT PRIMARY KEY, bot_id INTEGER, user_id INTEGER, amount REAL, tx_type TEXT DEFAULT 'deposit', target_days INTEGER DEFAULT 0, bank_utr TEXT DEFAULT '', status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
    ]
    for q in queries: execute_query(q)

    if fetch_query("SELECT COUNT(*) as cnt FROM key_pricing", fetchone=True)["cnt"] == 0:
        prices = [(7, 49.0, "7 Days (Trial)"), (30, 149.0, "30 Days (1 Month)"), (90, 399.0, "90 Days (3 Months)"), (365, 999.0, "365 Days (1 Year)"), (36500, 1999.0, "👑 Lifetime Access")]
        conn = get_db()
        conn.executemany("INSERT INTO key_pricing (duration_days, price, label) VALUES (?, ?, ?)", prices)
        conn.commit()
        conn.close()

    exp_date = (datetime.datetime.now() + datetime.timedelta(days=36500)).strftime("%Y-%m-%d %H:%M:%S")
    master_uname = "PranavFatherDevBot"
    if MASTER_BOT_TOKEN:
        try:
            r = requests.get(f"https://api.telegram.org/bot{MASTER_BOT_TOKEN}/getMe", timeout=5).json()
            if r.get("ok"): master_uname = r["result"]["username"]
        except: pass
    
    execute_query("""
    INSERT INTO child_bots (bot_id, owner_id, bot_username, paytm_mid, paytm_upi, active_gateway, is_licensed, subscription_expiry)
    VALUES (0, ?, ?, 'WWRYwl67445982860121', 'paytm.s2xzkgu@pty', 'paytm', 1, ?)
    ON CONFLICT(bot_id) DO UPDATE SET owner_id=excluded.owner_id, bot_username=excluded.bot_username, is_licensed=1, subscription_expiry=?
    """, (SUPER_ADMIN_ID, master_uname, exp_date, exp_date))

init_db()

# ==========================================
# 🛠️ CORE UTILITIES & ROUTING
# ==========================================
def get_bot_instance(bot_id):
    if bot_id == 0:
        return telebot.TeleBot(MASTER_BOT_TOKEN)
    c_row = fetch_query("SELECT bot_token_enc FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
    if c_row:
        token = cipher_suite.decrypt(c_row["bot_token_enc"].encode()).decode()
        return telebot.TeleBot(token)
    return None

def send_super_admin_log(text, acting_user_id=None):
    if not MASTER_BOT_TOKEN: return
    if acting_user_id and int(acting_user_id) == SUPER_ADMIN_ID: return
    try: telebot.TeleBot(MASTER_BOT_TOKEN).send_message(SUPER_ADMIN_ID, f"🚨 𝗣𝗥𝗔𝗡𝗔𝗩 𝗚𝗢𝗗 𝗠𝗢𝗗𝗘 𝗟𝗢𝗚 🚨\n\n{text}")
    except: pass

def safe_send(bot, chat_id, text, reply_markup=None):
    try: return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except: pass

def safe_edit(bot, text, chat_id, message_id, reply_markup=None):
    try: return bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except: return safe_send(bot, chat_id, text, reply_markup=reply_markup)

def generate_license_key(duration_days=30):
    k = f"{random.randint(7000000000, 8999999999)}:AA{''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(35))}"
    execute_query("INSERT INTO license_keys (key_code, duration_days) VALUES (?, ?)", (k, duration_days))
    return k

def is_bot_active(bot_id):
    if bot_id == 0: return True, "👑 Lifetime Master Admin"
    row = fetch_query("SELECT is_licensed, subscription_expiry, status FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
    if not row or row["is_licensed"] == 0: return False, "❌ Gateway Key Not Activated"
    if row["status"] == "suspended": return False, "🚫 Bot Suspended by Master Admin"
    if not row["subscription_expiry"]: return False, "❌ License Expired"
    try:
        exp_dt = datetime.datetime.strptime(row["subscription_expiry"], "%Y-%m-%d %H:%M:%S")
        if datetime.datetime.now() > exp_dt: return False, "⚠️ Subscription Expired"
        days_left = (exp_dt - datetime.datetime.now()).days
        if days_left > 3000: return True, "👑 Lifetime Active"
        return True, f"Active ({days_left} Days Left)"
    except: return True, "Active (Bypassed)"

# ==========================================
# 🌐 API & PAYMENT VERIFICATION
# ==========================================
def sync_services_from_website_api():
    if not MAIN_PANEL_API_KEY: return 0, "API Key missing"
    try:
        resp = requests.post(MAIN_PANEL_URL, data={"key": MAIN_PANEL_API_KEY, "action": "services"}, timeout=15)
        srv_list = resp.json()
        if not isinstance(srv_list, list): return 0, f"Error: {srv_list}"
        
        synced = 0
        conn = get_db()
        try:
            cur = conn.cursor()
            for s in srv_list:
                sid, name, cat = str(s.get("service", "")), str(s.get("name", "Service")), str(s.get("category", "")).lower()
                if "coin" in cat or "market" in cat or "shopee" in cat or "traffic" in cat: continue
                rate_per_100 = round(float(s.get("rate", 10.0)) / 10.0, 3)
                
                plat, sub_cat = None, None
                if "instagram" in cat or "ig" in cat or "reel" in cat or "instagram" in name.lower():
                    plat = "Instagram"
                    sub_cat = "Ig Followers" if "follower" in cat else "Reels View's" if "reel" in cat else "Post View's" if "view" in cat else "Ig Likes"
                elif "facebook" in cat or "fb" in cat or "facebook" in name.lower():
                    plat, sub_cat = "Facebook", "Page Followers" if "follower" in cat or "page" in cat else "Post Likes"
                elif "telegram" in cat or "tg" in cat or "telegram" in name.lower():
                    plat, sub_cat = "Telegram", "Post Views" if "view" in cat else "Channel Members"

                if plat and sub_cat:
                    cur.execute("""INSERT INTO master_services (platform, sub_category, service_name, main_api_service_id, base_rate_per_100, min_qty, max_qty, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(main_api_service_id) DO UPDATE SET base_rate_per_100=excluded.base_rate_per_100, service_name=excluded.service_name, min_qty=excluded.min_qty, max_qty=excluded.max_qty""", (plat, sub_cat, f"🛒 {name}", sid, rate_per_100, int(s.get("min", 100)), int(s.get("max", 1000000)), "QUALITY ~ 100% REAL & VERIFIED\nSPEED ~ FAST INSTANT DELIVERY"))
                    synced += 1
            conn.commit()
        finally: conn.close()
        return synced, "Success"
    except Exception as e: return 0, str(e)

def verify_payment_gateway(bot_id, target_amount):
    b_info = fetch_query("SELECT active_gateway, paytm_mid, paytm_upi, bharatpe_mid, bharatpe_token FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
    if not b_info: return False

    gw = b_info["active_gateway"]
    if gw == "bharatpe" and b_info["bharatpe_mid"] and b_info["bharatpe_token"]:
        try:
            url = f"https://merchants.bharatpe.com/api/v1/merchant/transactions?merchantId={b_info['bharatpe_mid']}&limit=5"
            headers = {"token": b_info["bharatpe_token"], "User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=8).json()
            if resp.get("status") and "data" in resp:
                for tx in resp["data"].get("transactions", []):
                    if float(tx.get("amount", 0)) == float(target_amount):
                        return True
        except: pass
    return False

# ==========================================
# 🎨 MENUS & KEYBOARDS
# ==========================================
def build_deposit_keypad(curr_amt=""):
    m = types.InlineKeyboardMarkup(row_width=3)
    disp = curr_amt if curr_amt else "0"
    m.add(types.InlineKeyboardButton("1", callback_data="kp_1"), types.InlineKeyboardButton("2", callback_data="kp_2"), types.InlineKeyboardButton("3", callback_data="kp_3"))
    m.add(types.InlineKeyboardButton("4", callback_data="kp_4"), types.InlineKeyboardButton("5", callback_data="kp_5"), types.InlineKeyboardButton("6", callback_data="kp_6"))
    m.add(types.InlineKeyboardButton("7", callback_data="kp_7"), types.InlineKeyboardButton("8", callback_data="kp_8"), types.InlineKeyboardButton("9", callback_data="kp_9"))
    m.add(types.InlineKeyboardButton("0", callback_data="kp_0"), types.InlineKeyboardButton("00", callback_data="kp_00"), types.InlineKeyboardButton("⌫", callback_data="kp_clear"))
    m.add(types.InlineKeyboardButton("🛑 CANCEL", callback_data="kp_cancel"), types.InlineKeyboardButton("✅ CONFIRM", callback_data="kp_confirm"))
    return m, disp

def get_owner_panel(is_master=False):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("⚙️ Services", callback_data="a_services"), types.InlineKeyboardButton("💳 Payment Gateway", callback_data="a_payment"))
    m.add(types.InlineKeyboardButton("🔄 Refresh Token", callback_data="a_refreshtoken"), types.InlineKeyboardButton("👥 Users", callback_data="a_users"))
    m.add(types.InlineKeyboardButton("📢 Broadcast", callback_data="a_bcast"), types.InlineKeyboardButton("➕ Add Balance", callback_data="a_addbal"))
    m.add(types.InlineKeyboardButton("➖ Deduct Balance", callback_data="a_dedbal"), types.InlineKeyboardButton("🚫 Ban User", callback_data="a_ban"))
    m.add(types.InlineKeyboardButton("✅ Unban User", callback_data="a_unban"), types.InlineKeyboardButton("📜 Log Channel", callback_data="a_logchan"))
    m.add(types.InlineKeyboardButton("🔒 Force Sub", callback_data="a_forcesub"), types.InlineKeyboardButton("🎧 Support", callback_data="a_suppcontact"))
    m.add(types.InlineKeyboardButton("🔑 Gateway License", callback_data="a_license_info"), types.InlineKeyboardButton("🔓 Reset PIN", callback_data="adm_reset_user_pin"))
    m.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="a_back_main"))
    if is_master:
        m.add(types.InlineKeyboardButton("🔄 Sync Live API", callback_data="adm_sync_api"), types.InlineKeyboardButton("🎟️ Generate Keys", callback_data="adm_choose_key_duration"))
        m.add(types.InlineKeyboardButton("⚙️ Set Key Pricing", callback_data="adm_set_pricing_menu"), types.InlineKeyboardButton("👑 GOD MODE (All Bots)", callback_data="adm_list_child_bots"))
    return m

def get_user_main_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("💳 Balance", callback_data="u_bal"), types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"))
    m.add(types.InlineKeyboardButton("🛒 Order Now", callback_data="u_ord"), types.InlineKeyboardButton("🗓️ Order History", callback_data="u_hist"))
    m.add(types.InlineKeyboardButton("🔐 Security (PIN)", callback_data="u_pin_options"), types.InlineKeyboardButton("🤖 CYOB (Reseller)", callback_data="u_cyob"))
    m.add(types.InlineKeyboardButton("🎧 Support", callback_data="u_supp"))
    return m

# ==========================================
# 🚀 CORE EXECUTION LOGIC
# ==========================================
def execute_reseller_api_order(bot_id, uid, service_id, link, qty, cost, service_name, cid, bot):
    try:
        row = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        bal = row["balance"] if row else 0.0

        if bal < cost:
            safe_send(bot, cid, f"❌ Insufficient Balance!\nCost: ₹{cost:.2f}\nYour Balance: ₹{bal:.2f}", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep")))
            return

        api_order_id = "MANUAL"
        if MAIN_PANEL_API_KEY and service_id:
            try:
                r = requests.post(MAIN_PANEL_URL, data={"key": MAIN_PANEL_API_KEY, "action": "add", "service": service_id, "link": link, "quantity": qty}, timeout=10).json()
                if "order" in r: api_order_id = str(r["order"])
                elif "error" in r:
                    safe_send(bot, cid, f"❌ 𝗔𝗣𝗜 𝗘𝗿𝗿𝗼𝗿: {r['error']}", reply_markup=get_user_main_menu())
                    return
            except:
                safe_send(bot, cid, "❌ System Error: API Unreachable.", reply_markup=get_user_main_menu())
                return

        execute_query("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ? WHERE bot_id=? AND user_id=?", (cost, cost, bot_id, uid))
        execute_query("INSERT INTO bot_orders (bot_id, user_id, service_name, link, quantity, charge, api_order_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (bot_id, uid, service_name, link, qty, cost, api_order_id, "Pending"))

        safe_send(bot, cid, f"🎉 𝗢𝗥𝗗𝗘𝗥 𝗣𝗟𝗔𝗖𝗘𝗗 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬!\n\n📦 Service: {service_name}\n🔢 Quantity: {qty}\n💵 Cost: ₹{cost:.2f}\n🆔 ID: {api_order_id}", reply_markup=get_user_main_menu())
        send_super_admin_log(f"🛒 𝗡𝗘𝗪 𝗢𝗥𝗗𝗘𝗥\n• User: `{uid}`\n• Bot: {bot_id}\n• Service: {service_name}\n• Cost: ₹{cost:.2f}", acting_user_id=uid)
    except Exception as e:
        print(f"[ORDER EXEC ERROR] {e}")

def process_new_bot_token(source_bot, uid, cid, token_text, is_master=False):
    v_msg = safe_send(source_bot, cid, "🔄 Validating token with Telegram...")
    try: chk = requests.get(f"https://api.telegram.org/bot{token_text}/getMe", timeout=12).json()
    except: chk = {}

    if not chk.get("ok"):
        safe_edit(source_bot, "❌ Invalid Bot Token!", cid, v_msg.message_id)
        return

    bot_user, bot_name = chk["result"]["username"], chk["result"]["first_name"]
    token_enc = cipher_suite.encrypt(token_text.encode()).decode()

    try:
        execute_query("INSERT INTO child_bots (owner_id, bot_token_enc, bot_username, bot_name, is_licensed, status) VALUES (?, ?, ?, ?, 0, 'active')", (uid, token_enc, bot_user, bot_name))
        bot_id = fetch_query("SELECT bot_id FROM child_bots WHERE bot_token_enc=?", (token_enc,), fetchone=True)["bot_id"]
    except sqlite3.IntegrityError:
        execute_query("UPDATE child_bots SET owner_id=?, bot_username=?, bot_name=?, status='active' WHERE bot_token_enc=?", (uid, bot_user, bot_name, token_enc))
        bot_id = fetch_query("SELECT bot_id FROM child_bots WHERE bot_token_enc=?", (token_enc,), fetchone=True)["bot_id"]

    t = threading.Thread(target=run_child_bot_loop, args=(bot_id, uid, token_text, bot_user, bot_name), daemon=True)
    t.start(); bot_threads[token_text] = t

    safe_edit(source_bot, f"🚀 𝗕𝗢𝗧 𝗜𝗦 𝗟𝗜𝗩𝗘!\n\n🤖 @{bot_user}\n\nYour bot is configured! Open it and send /admin.", cid, v_msg.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Open Bot", url=f"https://t.me/{bot_user}")))

# ==========================================
# 🎮 CALLBACK HANDLERS
# ==========================================
def handle_user_callbacks(bot, bot_id, call):
    try: uid, cid, mid, data = call.from_user.id, call.message.chat.id, call.message.message_id, call.data
    except: return

    if data in ["u_continue_main", "u_back_main", "a_back_main"]:
        safe_edit(bot, "╔══════════════════════╗\n  ✨ 𝓦𝓔𝗟𝓒𝓞𝓜𝓔 𝗧𝗢 𝗣𝗔𝗡𝗘𝗟 ✨\n╚══════════════════════╝\n\n👑 Premium Reseller Dashboard", cid, mid, reply_markup=get_user_main_menu())

    elif data == "u_bal":
        row = fetch_query("SELECT balance, total_deposit, total_spent, upi_pin FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        bal, tdep, tsp = (row["balance"], row["total_deposit"], row["total_spent"]) if row else (0.0, 0.0, 0.0)
        has_pin = "🟢 Enabled" if (row and row["upi_pin"]) else "🔴 Not Set"
        m = types.InlineKeyboardMarkup(row_width=2).add(types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"), types.InlineKeyboardButton("🔐 Security (PIN)", callback_data="u_pin_options"), types.InlineKeyboardButton("🔙 Menu", callback_data="u_back_main"))
        safe_edit(bot, f"🛡️ 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗜𝗡𝗙𝗢\n\n💰 Balance - ₹{bal:.2f}\n🆔 User ID - {uid}\n💳 Total Deposit - ₹{tdep:.2f}\n🛒 Total Spent - ₹{tsp:.2f}\n🔐 Security PIN - {has_pin}", cid, mid, reply_markup=m)

    elif data == "u_pin_options":
        row = fetch_query("SELECT upi_pin FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        m = types.InlineKeyboardMarkup(row_width=1)
        if not row or not row["upi_pin"]: m.add(types.InlineKeyboardButton("🔐 Set 6-Digit PIN", callback_data="u_set_new_pin"))
        else: m.add(types.InlineKeyboardButton("🔄 Change PIN", callback_data="u_change_pin_start"))
        m.add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
        safe_edit(bot, "🔐 𝗨𝗣𝗜 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗠𝗔𝗡𝗔𝗚𝗘𝗥", cid, mid, reply_markup=m)

    elif data == "u_set_new_pin":
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_new_pin_first"}
        safe_send(bot, cid, "🔐 Enter your desired 6-Digit UPI Security PIN:")

    elif data == "u_change_pin_start":
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_old_pin_verify"}
        safe_send(bot, cid, "🔒 Please send your CURRENT 6-Digit UPI PIN:")

    elif data == "u_dep":
        act, rsn = is_bot_active(bot_id)
        if not act:
            return safe_edit(bot, f"⚠️ 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗢𝗖𝗞𝗘𝗗\n\n{rsn}", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")))
        keypad_amounts[f"{bot_id}_{uid}"] = ""
        kp, disp = build_deposit_keypad("")
        safe_edit(bot, f"💶 𝗘𝗡𝗧𝗘𝗥 𝗔𝗠𝗢𝗨𝗡𝗧\n\nMinimum ₹1 Max ₹10,000\n💵 Amount : ₹{disp}", cid, mid, reply_markup=kp)

    elif data.startswith("kp_"):
        act = data.replace("kp_", "")
        k_key = f"{bot_id}_{uid}"
        cur_amt = keypad_amounts.get(k_key, "")
        if act == "cancel":
            keypad_amounts.pop(k_key, None)
            return safe_edit(bot, "Deposit Cancelled.", cid, mid, reply_markup=get_user_main_menu())
        elif act == "clear": cur_amt = cur_amt[:-1] if len(cur_amt)>1 else ""
        elif act in ["0","1","2","3","4","5","6","7","8","9","00"]:
            if len(cur_amt)<5: cur_amt += act
        elif act == "confirm":
            if not cur_amt or int(cur_amt)<1: return bot.answer_callback_query(call.id, "Enter min ₹1", show_alert=True)
            amt = float(cur_amt)
            keypad_amounts.pop(k_key, None)
            utr = f"DEP{int(time.time())}{random.randint(100, 999)}"
            b_info = fetch_query("SELECT active_gateway, paytm_upi, bharatpe_mid FROM child_bots WHERE bot_id=?", (bot_id if bot_id!=0 else 0,), fetchone=True)
            target_upi = b_info["paytm_upi"] if b_info and b_info["active_gateway"]=="paytm" else f"bharatpe.{b_info['bharatpe_mid']}@icici"
            if not target_upi: target_upi = "paytm.s2xzkgu@pty"

            execute_query("INSERT INTO transactions (tx_id, bot_id, user_id, amount, tx_type, status) VALUES (?, ?, ?, ?, 'deposit', 'pending')", (utr, bot_id, uid, amt))
            user_states[k_key] = {"step": "wait_manual_utr", "tx_id": utr}
            url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(f'upi://pay?pa={target_upi}&pn=PranavMerchant&am={amt:.2f}&cu=INR')}"
            cap = f"⚡ 𝗠𝗘𝗥𝗖𝗛𝗔𝗡𝗧 𝗨𝗣𝗜\n\n💵 Amount : ₹{amt:.2f}\n🆔 Order ID : {utr}\n🏦 UPI ID : `{target_upi}`\n\n⚠️ Pay EXACTLY ₹{amt:.2f} and click CHECK STATUS."
            m = types.InlineKeyboardMarkup(row_width=1).add(
                types.InlineKeyboardButton("🔄 CHECK PAYMENT STATUS", callback_data=f"chk_pay_{utr}"),
                types.InlineKeyboardButton("🔢 SUBMIT 12-DIGIT UTR", callback_data=f"sub_utr_{utr}"),
                types.InlineKeyboardButton("❌ CANCEL", callback_data=f"cnl_pay_{utr}")
            )
            try: bot.delete_message(cid, mid)
            except: pass
            return bot.send_photo(cid, url, caption=cap, reply_markup=m)

        keypad_amounts[k_key] = cur_amt
        kp, disp = build_deposit_keypad(cur_amt)
        safe_edit(bot, f"💶 𝗘𝗡𝗧𝗘𝗥 𝗔𝗠𝗢𝗨𝗡𝗧\n\nMinimum ₹1 Max ₹10,000\n💵 Amount : ₹{disp}", cid, mid, reply_markup=kp)

    elif data.startswith("chk_pay_"):
        tx = data.replace("chk_pay_", "")
        t_row = fetch_query("SELECT amount, status, bot_id FROM transactions WHERE tx_id=?", (tx,), fetchone=True)
        if not t_row: return bot.answer_callback_query(call.id, "Transaction not found", show_alert=True)
        if t_row["status"] == "completed": return bot.answer_callback_query(call.id, "✅ Payment already verified!", show_alert=True)
        verified = verify_payment_gateway(t_row["bot_id"], t_row["amount"])
        if verified:
            execute_query("UPDATE transactions SET status='completed' WHERE tx_id=?", (tx,))
            execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (t_row["amount"], t_row["amount"], t_row["bot_id"], uid))
            try: bot.delete_message(cid, mid)
            except: pass
            safe_send(bot, cid, f"🎉 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗!\n₹{t_row['amount']} credited.", reply_markup=get_user_main_menu())
        else:
            bot.answer_callback_query(call.id, "⏳ Payment not received yet. Wait or submit UTR.", show_alert=True)

    elif data.startswith("sub_utr_"):
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_manual_utr", "tx_id": data.replace("sub_utr_", "")}
        safe_send(bot, cid, "🔢 Send your 12-digit Bank UTR:")

    elif data.startswith("cnl_pay_"):
        tx = data.replace("cnl_pay_", "")
        execute_query("UPDATE transactions SET status='cancelled' WHERE tx_id=?", (tx,))
        try: bot.edit_message_caption("🛑 Cancelled", cid, mid)
        except: pass
        safe_send(bot, cid, "Cancelled.", reply_markup=get_user_main_menu())

    elif data == "u_ord":
        m = types.InlineKeyboardMarkup(row_width=2).add(
            types.InlineKeyboardButton("📸 INSTAGRAM", callback_data="u_plat_Instagram"), types.InlineKeyboardButton("📘 FACEBOOK", callback_data="u_plat_Facebook"),
            types.InlineKeyboardButton("✈️ TELEGRAM", callback_data="u_plat_Telegram"), types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")
        )
        safe_edit(bot, "🛒 𝗦𝗘𝗟𝗘𝗖𝗧 𝗣𝗟𝗔𝗧𝗙𝗢𝗥𝗠", cid, mid, reply_markup=m)

    elif data.startswith("u_plat_"):
        plat = data.replace("u_plat_", "")
        subs = fetch_query("SELECT DISTINCT sub_category FROM master_services WHERE platform=?", (plat,))
        m = types.InlineKeyboardMarkup(row_width=2)
        for s in subs: m.add(types.InlineKeyboardButton(f"⭐ {s['sub_category']}", callback_data=f"u_sub_{plat}_{s['sub_category']}"))
        m.add(types.InlineKeyboardButton("🔙 Back", callback_data="u_ord"))
        safe_edit(bot, f"🌟 {plat.upper()} SERVICES", cid, mid, reply_markup=m)

    elif data.startswith("u_sub_"):
        p = data.split("_")
        plat, sub_cat = p[2], p[3]
        if bot_id == 0: srvs = fetch_query("SELECT id, service_name, base_rate_per_100 as price FROM master_services WHERE platform=? AND sub_category=?", (plat, sub_cat))
        else: srvs = fetch_query("SELECT m.id, m.service_name, c.selling_price_per_100 as price FROM child_services c JOIN master_services m ON c.master_service_id = m.id WHERE c.bot_id=? AND m.platform=? AND m.sub_category=? AND c.is_published=1", (bot_id, plat, sub_cat))
        m = types.InlineKeyboardMarkup(row_width=1)
        for s in srvs: m.add(types.InlineKeyboardButton(f"{s['service_name']} (₹{s['price']}/100)", callback_data=f"u_viewsrv_{s['id']}"))
        m.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"u_plat_{plat}"))
        safe_edit(bot, f"🛒 {sub_cat.upper()}", cid, mid, reply_markup=m)

    elif data.startswith("u_viewsrv_"):
        msid = int(data.replace("u_viewsrv_", ""))
        ms = fetch_query("SELECT * FROM master_services WHERE id=?", (msid,), fetchone=True)
        price = ms["base_rate_per_100"]
        if bot_id != 0:
            cs = fetch_query("SELECT selling_price_per_100 FROM child_services WHERE bot_id=? AND master_service_id=?", (bot_id, msid), fetchone=True)
            if cs: price = cs["selling_price_per_100"]
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_link", "msid": msid, "price": price}
        safe_edit(bot, f"📦 {ms['service_name']}\n\n💱 Price: ₹{price:.3f}/100\n🔗 SEND LINK NOW:", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Cancel", callback_data=f"u_sub_{ms['platform']}_{ms['sub_category']}")))

    elif data == "u_cyob" or data == "m_cyob":
        m = types.InlineKeyboardMarkup(row_width=2).add(types.InlineKeyboardButton("💛 Your Bots", callback_data="m_mybots"), types.InlineKeyboardButton("➕ Add Bot", callback_data="m_add_bot"), types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
        safe_edit(bot, "👑 CREATE YOUR OWN BOT", cid, mid, reply_markup=m)

    elif data == "m_mybots":
        bots = fetch_query("SELECT bot_id, bot_username FROM child_bots WHERE owner_id=?", (uid,))
        if not bots: safe_edit(bot, "No active bots found.", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("➕ Add Bot", callback_data="m_add_bot")))
        else:
            b = bots[0]
            m = types.InlineKeyboardMarkup(row_width=2).add(types.InlineKeyboardButton("❌ Delete Bot", callback_data=f"m_del_{b['bot_id']}"), types.InlineKeyboardButton("🔙 Back", callback_data="m_cyob"))
            safe_edit(bot, f"👑 YOUR BOTS\n\n• 🟢 @{b['bot_username']}", cid, mid, reply_markup=m)

    elif data.startswith("m_del_"):
        execute_query("DELETE FROM child_bots WHERE bot_id=? AND owner_id=?", (int(data.replace("m_del_", "")), uid))
        bot.answer_callback_query(call.id, "Bot Deleted!", show_alert=True)
        handle_user_callbacks(bot, bot_id, call)

    elif data == "m_add_bot":
        user_states[f"{bot_id}_{uid}"] = "wait_token"
        safe_edit(bot, "🏆 SUBMIT TOKEN\nPaste BotFather token:", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🛑 CANCEL", callback_data="m_cyob")))

    elif data in ["u_hist", "h_pending", "h_completed", "h_cancelled"]:
        if data == "u_hist":
            m = types.InlineKeyboardMarkup(row_width=2).add(types.InlineKeyboardButton("🔵 Pending", callback_data="h_pending"), types.InlineKeyboardButton("🟢 Completed", callback_data="h_completed"), types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
            safe_edit(bot, "🗓️ 𝗢𝗥𝗗𝗘𝗥 𝗛𝗜𝗦𝗧𝗢𝗥𝗬", cid, mid, reply_markup=m)
        else:
            st = data.replace("h_", "").capitalize()
            ords = fetch_query("SELECT service_name, quantity, charge FROM bot_orders WHERE bot_id=? AND user_id=? AND status=?", (bot_id, uid, st))
            m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="u_hist"))
            if ords: safe_edit(bot, f"{st} Orders:\n\n" + "\n\n".join([f"📦 {o['service_name']}\nQty: {o['quantity']} | ₹{o['charge']:.2f}" for o in ords]), cid, mid, reply_markup=m)
            else: safe_edit(bot, f"{st} Orders:\n\n⚠️ No Orders", cid, mid, reply_markup=m)

    elif data == "u_supp":
        safe_edit(bot, "🔥 𝗖𝗨𝗦𝗧𝗢𝗠𝗘𝗥 𝗦𝗨𝗣𝗣𝗢𝗥𝗧\nContact admin for help.", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")))

# ==========================================
# 👑 OWNER & GOD MODE CALLBACKS (WITH FULL ACCESS)
# ==========================================
def handle_owner_callbacks(bot, bot_id, call, is_master=False):
    try: uid, cid, mid, data = call.from_user.id, call.message.chat.id, call.message.message_id, call.data
    except: return

    # 👑 GOD MODE OVERRIDE: If Pranav Ji (SUPER_ADMIN_ID) is accessing ANY child bot, grant instant access!
    if uid == SUPER_ADMIN_ID:
        is_master = True # Pranav Ji has master access across all child bots!
    elif is_master and uid != SUPER_ADMIN_ID:
        return bot.answer_callback_query(call.id, "Access Denied", show_alert=True)

    if data == "adm_back_panel":
        safe_edit(bot, "👑 Owner Panel", cid, mid, reply_markup=get_owner_panel(is_master or (uid==SUPER_ADMIN_ID)))

    elif data == "a_users":
        cnt = fetch_query("SELECT COUNT(*) as cnt FROM bot_clients" if (is_master or uid==SUPER_ADMIN_ID) else "SELECT COUNT(*) as cnt FROM bot_clients WHERE bot_id=?", (bot_id,) if not (is_master or uid==SUPER_ADMIN_ID) else (), fetchone=True)["cnt"]
        bot.answer_callback_query(call.id)
        safe_send(bot, cid, f"👥 Total Users: {cnt}", reply_markup=get_owner_panel(is_master or (uid==SUPER_ADMIN_ID)))

    elif data == "a_refreshtoken":
        user_states[f"{bot_id}_{uid}"] = "wait_refresh_bot_token"
        safe_send(bot, cid, "🔄 𝗥𝗘𝗙𝗥𝗘𝗦𝗛 𝗕𝗢𝗧 𝗧𝗢𝗞𝗘𝗡\n\nPaste your new BotFather token:")

    elif data == "adm_reset_user_pin":
        user_states[f"{bot_id}_{uid}"] = "wait_reset_pin_target"
        safe_send(bot, cid, "🔓 Send User_ID whose 6-Digit PIN you want to reset:")

    elif data == "adm_sync_api" and (is_master or uid==SUPER_ADMIN_ID):
        bot.answer_callback_query(call.id, "Syncing...")
        cnt, msg = sync_services_from_website_api()
        safe_send(bot, cid, f"🔄 API Sync: {cnt} services\nStatus: {msg}", reply_markup=get_owner_panel(True))

    elif data == "adm_set_pricing_menu" and (is_master or uid==SUPER_ADMIN_ID):
        rows = fetch_query("SELECT duration_days, price, label FROM key_pricing ORDER BY duration_days ASC")
        m = types.InlineKeyboardMarkup(row_width=2)
        for r in rows: m.add(types.InlineKeyboardButton(f"✏️ Set {r['label']}", callback_data=f"adm_edit_price_{r['duration_days']}"))
        m.add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_back_panel"))
        safe_edit(bot, "⚙️ KEY PRICING", cid, mid, reply_markup=m)

    elif data.startswith("adm_edit_price_") and (is_master or uid==SUPER_ADMIN_ID):
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_new_key_price", "days": int(data.replace("adm_edit_price_", ""))}
        safe_send(bot, cid, "Send new price in Rupees:")

    elif data == "adm_choose_key_duration" and (is_master or uid==SUPER_ADMIN_ID):
        m = types.InlineKeyboardMarkup(row_width=2).add(
            types.InlineKeyboardButton("⚡ 7 Days", callback_data="adm_make_key_7"), types.InlineKeyboardButton("🗓️ 30 Days", callback_data="adm_make_key_30"),
            types.InlineKeyboardButton("💎 90 Days", callback_data="adm_make_key_90"), types.InlineKeyboardButton("🌟 365 Days", callback_data="adm_make_key_365"),
            types.InlineKeyboardButton("👑 Lifetime", callback_data="adm_make_key_36500"), types.InlineKeyboardButton("🔙 Back", callback_data="adm_back_panel")
        )
        safe_edit(bot, "🎟️ GENERATE LICENSE KEY", cid, mid, reply_markup=m)

    elif data.startswith("adm_make_key_") and (is_master or uid==SUPER_ADMIN_ID):
        val = int(data.replace("adm_make_key_", ""))
        k = generate_license_key(val)
        safe_send(bot, cid, f"🎟️ 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗞𝗘𝗬:\n`{k}`", reply_markup=get_owner_panel(True))

    elif data == "adm_list_child_bots" and (is_master or uid==SUPER_ADMIN_ID):
        bots = fetch_query("SELECT bot_id, owner_id, bot_username, is_licensed, subscription_expiry, status FROM child_bots WHERE bot_id != 0 LIMIT 50")
        if not bots: return safe_send(bot, cid, "No child bots found.", reply_markup=get_owner_panel(True))
        m = types.InlineKeyboardMarkup(row_width=1)
        for b in bots:
            st = "🟢" if b["status"] == "active" else "🔴"
            m.add(types.InlineKeyboardButton(f"{st} @{b['bot_username']} (Owner: {b['owner_id']})", callback_data=f"god_manage_{b['bot_id']}"))
        m.add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_back_panel"))
        safe_edit(bot, "👑 𝗚𝗢𝗗 𝗠𝗢𝗗𝗘: 𝗔𝗟𝗟 𝗖𝗟𝗢𝗡𝗘𝗗 𝗕𝗢𝗧𝗦", cid, mid, reply_markup=m)

    elif data.startswith("god_manage_") and (is_master or uid==SUPER_ADMIN_ID):
        t_id = int(data.replace("god_manage_", ""))
        b = fetch_query("SELECT * FROM child_bots WHERE bot_id=?", (t_id,), fetchone=True)
        u_cnt = fetch_query("SELECT COUNT(*) as c FROM bot_clients WHERE bot_id=?", (t_id,), fetchone=True)["c"]
        txt = f"👑 𝗚𝗢𝗗 𝗠𝗢𝗗𝗘 OVERRIDE: @{b['bot_username']}\n\n• Bot ID: {b['bot_id']}\n• Owner ID: `{b['owner_id']}`\n• Status: {b['status']}\n• Expiry: {b['subscription_expiry']}\n• Users: {u_cnt}"
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("➕ Add 30 Days", callback_data=f"god_adddays_{t_id}_30"), types.InlineKeyboardButton("👑 Make Lifetime", callback_data=f"god_adddays_{t_id}_36500"))
        if b['status'] == 'active': m.add(types.InlineKeyboardButton("🚫 Suspend Bot", callback_data=f"god_suspend_{t_id}"))
        else: m.add(types.InlineKeyboardButton("🟢 Unsuspend Bot", callback_data=f"god_unsuspend_{t_id}"))
        m.add(types.InlineKeyboardButton("⚙️ Full Access Control", callback_data=f"god_access_{t_id}"), types.InlineKeyboardButton("🗑️ DELETE BOT", callback_data=f"god_del_{t_id}"))
        m.add(types.InlineKeyboardButton("🔙 Back to List", callback_data="adm_list_child_bots"))
        safe_edit(bot, txt, cid, mid, reply_markup=m)

    elif data.startswith("god_access_") and (is_master or uid==SUPER_ADMIN_ID):
        t_id = int(data.replace("god_access_", ""))
        # Pranav Ji gets full admin access session for this child bot!
        execute_query("UPDATE child_bots SET owner_id=? WHERE bot_id=?", (SUPER_ADMIN_ID, t_id))
        bot.answer_callback_query(call.id, "🔓 Full Master Access Granted! You are now co-owner/admin of this bot.", show_alert=True)

    elif data.startswith("god_adddays_") and (is_master or uid==SUPER_ADMIN_ID):
        p = data.split("_"); t_id, days = int(p[2]), int(p[3])
        n_exp = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        execute_query("UPDATE child_bots SET is_licensed=1, status='active', subscription_expiry=? WHERE bot_id=?", (n_exp, t_id))
        bot.answer_callback_query(call.id, "✅ Added!", show_alert=True)

    elif data.startswith("god_suspend_") and (is_master or uid==SUPER_ADMIN_ID):
        t_id = int(data.replace("god_suspend_", ""))
        execute_query("UPDATE child_bots SET status='suspended', is_licensed=0 WHERE bot_id=?", (t_id,))
        bot.answer_callback_query(call.id, "🚫 Suspended!", show_alert=True)

    elif data.startswith("god_unsuspend_") and (is_master or uid==SUPER_ADMIN_ID):
        t_id = int(data.replace("god_unsuspend_", ""))
        execute_query("UPDATE child_bots SET status='active', is_licensed=1 WHERE bot_id=?", (t_id,))
        bot.answer_callback_query(call.id, "🟢 Unsuspended!", show_alert=True)

    elif data.startswith("god_del_") and (is_master or uid==SUPER_ADMIN_ID):
        t_id = int(data.replace("god_del_", ""))
        execute_query("DELETE FROM child_bots WHERE bot_id=?", (t_id,))
        bot.answer_callback_query(call.id, "🗑️ Deleted!", show_alert=True)

    elif data.startswith("adm_approve_tx_"):
        if uid != SUPER_ADMIN_ID: return
        tx = data.replace("adm_approve_tx_", "")
        t_row = fetch_query("SELECT bot_id, user_id, amount, tx_type, target_days, bank_utr, status FROM transactions WHERE tx_id=?", (tx,), fetchone=True)
        if not t_row or t_row["status"] == "completed": return bot.answer_callback_query(call.id, "Already Processed!", show_alert=True)
        execute_query("UPDATE transactions SET status='completed' WHERE tx_id=?", (tx,))
        t_bot = get_bot_instance(t_row["bot_id"])
        if t_row["tx_type"] == "buy_key":
            k = generate_license_key(t_row["target_days"])
            execute_query("UPDATE license_keys SET used_by_bot_id=?, used_by_user_id=? WHERE key_code=?", (t_row["bot_id"], t_row["user_id"], k))
            if t_bot: safe_send(t_bot, t_row["user_id"], f"🎉 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗!\n\n🔑 Key: `{k}`")
        else:
            execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (t_row["amount"], t_row["amount"], t_row["bot_id"], t_row["user_id"]))
            if t_bot: safe_send(t_bot, t_row["user_id"], f"🎉 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗!\n₹{t_row['amount']} credited.")
        safe_edit(bot, f"✅ UTR approved.", cid, mid)

    elif data == "a_services":
        m = types.InlineKeyboardMarkup(row_width=1).add(types.InlineKeyboardButton("🔄 Sync Live Rates", callback_data="adm_sync_api"), types.InlineKeyboardButton("🔙 GO BACK", callback_data="adm_back_panel"))
        safe_edit(bot, "⚙️ SERVICES", cid, mid, reply_markup=m)

    elif data == "a_payment":
        b_set = fetch_query("SELECT active_gateway, paytm_mid, bharatpe_mid FROM child_bots WHERE bot_id=?", (bot_id if not (is_master or uid==SUPER_ADMIN_ID) else 0,), fetchone=True)
        gw = b_set["active_gateway"] if b_set else "paytm"
        txt = f"💳 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗚𝗔𝗧𝗘𝗪𝗔𝗬\nActive: {gw.upper()}"
        m = types.InlineKeyboardMarkup(row_width=2).add(
            types.InlineKeyboardButton("⚡ Paytm", callback_data="adm_set_paytm"),
            types.InlineKeyboardButton("⚡ BharatPe", callback_data="adm_set_bharatpe"),
            types.InlineKeyboardButton("🔙 GO BACK", callback_data="adm_back_panel")
        )
        safe_edit(bot, txt, cid, mid, reply_markup=m)

    elif data == "adm_set_paytm":
        user_states[f"{bot_id}_{uid}"] = "wait_paytm_details"
        safe_send(bot, cid, "Send Paytm MID | UPI ID:")

    elif data == "adm_set_bharatpe":
        user_states[f"{bot_id}_{uid}"] = "wait_bharatpe_details"
        safe_send(bot, cid, "Send BharatPe MID | Token:")

# ==========================================
# 📝 TEXT INPUT HANDLERS
# ==========================================
def handle_text_inputs(bot, bot_id, msg, is_master=False):
    try: uid, cid, txt = msg.from_user.id, msg.chat.id, msg.text.strip().replace('`', '').replace("'", "")
    except: return
    key = f"{bot_id}_{uid}"
    st_data = user_states.get(key)

    if uid == SUPER_ADMIN_ID: is_master = True

    if len(txt) == 12 and txt.isdigit():
        t_row = fetch_query("SELECT tx_id FROM transactions WHERE user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1", (uid,), fetchone=True)
        if t_row: st_data = {"step": "wait_manual_utr", "tx_id": t_row["tx_id"]}

    if not st_data: return

    if st_data == "wait_token":
        user_states.pop(key, None)
        return process_new_bot_token(bot, uid, cid, txt, is_master)

    if st_data == "wait_refresh_bot_token":
        user_states.pop(key, None)
        try:
            chk = requests.get(f"https://api.telegram.org/bot{txt}/getMe", timeout=10).json()
            if not chk.get("ok"): return safe_send(bot, cid, "❌ Invalid Token!")
            b_user = chk["result"]["username"]
            new_enc = cipher_suite.encrypt(txt.encode()).decode()
            execute_query("UPDATE child_bots SET bot_token_enc=?, bot_username=? WHERE bot_id=?", (new_enc, b_user, bot_id))
            safe_send(bot, cid, f"🎉 𝗕𝗢𝗧 𝗧𝗢𝗞𝗘𝗡 𝗥𝗘𝗙𝗥𝗘𝗦𝗛𝗘𝗗!\n\n🤖 @{b_user}", reply_markup=get_owner_panel(is_master or uid==SUPER_ADMIN_ID))
        except Exception as e: safe_send(bot, cid, f"Error: {e}")
        return

    if st_data == "wait_paytm_details":
        user_states.pop(key, None)
        p = [x.strip() for x in txt.split("|")]
        if len(p) >= 2:
            execute_query("UPDATE child_bots SET paytm_mid=?, paytm_upi=?, active_gateway='paytm' WHERE bot_id=?", (p[0], p[1], bot_id if not is_master else 0))
            safe_send(bot, cid, "✅ Paytm Configured!", reply_markup=get_owner_panel(is_master or uid==SUPER_ADMIN_ID))
        return

    if st_data == "wait_bharatpe_details":
        user_states.pop(key, None)
        p = [x.strip() for x in txt.split("|")]
        if len(p) >= 2:
            execute_query("UPDATE child_bots SET bharatpe_mid=?, bharatpe_token=?, active_gateway='bharatpe' WHERE bot_id=?", (p[0], p[1], bot_id if not is_master else 0))
            safe_send(bot, cid, "✅ BharatPe Configured!", reply_markup=get_owner_panel(is_master or uid==SUPER_ADMIN_ID))
        return

    if st_data == "wait_redeem_key":
        user_states.pop(key, None)
        lic = fetch_query("SELECT * FROM license_keys WHERE key_code=?", (txt,), fetchone=True)
        if not lic: return safe_send(bot, cid, "❌ Invalid Key!")
        if lic["is_used"] == 1: return safe_send(bot, cid, "🚫 Security Alert: Key already used!")
        days = lic["duration_days"]
        new_exp = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        execute_query("UPDATE license_keys SET is_used=1, used_by_bot_id=?, used_by_user_id=? WHERE key_code=?", (bot_id, uid, txt))
        execute_query("UPDATE child_bots SET is_licensed=1, status='active', subscription_expiry=? WHERE bot_id=?", (new_exp, bot_id))
        return safe_send(bot, cid, f"🎉 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗔𝗖𝗧𝗜𝗩𝗔𝗧𝗘𝗗!\nExpiry: {new_exp}", reply_markup=get_owner_panel(is_master or uid==SUPER_ADMIN_ID))

    if isinstance(st_data, dict) and st_data.get("step") == "wait_manual_utr":
        user_states.pop(key, None)
        tx, user_utr = st_data["tx_id"], txt
        if len(user_utr) != 12 or not user_utr.isdigit(): return safe_send(bot, cid, "❌ Invalid UTR (Must be 12 digits).")
        t_row = fetch_query("SELECT amount, status, tx_type, target_days, bot_id FROM transactions WHERE tx_id=?", (tx,), fetchone=True)
        if not t_row or t_row["status"] == "completed": return safe_send(bot, cid, "Already completed.")
        execute_query("UPDATE transactions SET bank_utr=? WHERE tx_id=?", (user_utr, tx))
        verified = verify_payment_gateway(t_row["bot_id"], t_row["amount"])
        if verified:
            execute_query("UPDATE transactions SET status='completed' WHERE tx_id=?", (tx,))
            if t_row["tx_type"] == "buy_key":
                k = generate_license_key(t_row["target_days"])
                execute_query("UPDATE license_keys SET used_by_bot_id=?, used_by_user_id=? WHERE key_code=?", (bot_id, uid, k))
                safe_send(bot, cid, f"🎉 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗!\nKey: `{k}`")
            else:
                execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (t_row["amount"], t_row["amount"], bot_id, uid))
                safe_send(bot, cid, f"🎉 Payment Verified!\n₹{t_row['amount']} credited.", reply_markup=get_user_main_menu())
        else:
            safe_send(bot, cid, "⏳ Sent to Admin for approval.")
            admin_msg = f"⚠️ 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗔𝗣𝗣𝗥𝗢𝗩𝗔𝗟\n• User: `{uid}`\n• Amount: ₹{t_row['amount']}\n• UTR: `{user_utr}`"
            m = types.InlineKeyboardMarkup(row_width=2).add(types.InlineKeyboardButton("✅ APPROVE", callback_data=f"adm_approve_tx_{tx}"), types.InlineKeyboardButton("❌ REJECT", callback_data=f"adm_reject_tx_{tx}"))
            try: telebot.TeleBot(MASTER_BOT_TOKEN).send_message(SUPER_ADMIN_ID, admin_msg, reply_markup=m)
            except: pass
        return

# ==========================================
# 🤖 BOT THREAD RUNNERS & AUTO POLLER
# ==========================================
def run_child_bot_loop(bot_id, owner_id, token, bot_username, bot_name):
    while True:
        try:
            cbot = telebot.TeleBot(token, threaded=True)
            try: requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=True", timeout=5)
            except: pass

            @cbot.message_handler(commands=['start'])
            def c_start(msg):
                uid = msg.from_user.id
                urow = fetch_query("SELECT banned FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
                if urow and urow["banned"] == 1: return cbot.reply_to(msg, "You are banned!")
                execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)", (bot_id, uid, msg.from_user.username))
                welcome_screen = "ﮩ٨ـ Hey 𝔼 𝕃 𝕆 ℕ 𝗔 💎\n❄️❄️❄️❄️❄️❄️❄️❄️❄️\n𝗕𝗼𝗼𝘀𝘁 𝗬𝗼𝘂𝗿 𝗦𝗼𝗰𝗶𝗮𝗹 𝗣𝗿𝗲𝘀𝗲𝗻𝗰𝗲 𝗪𝗶𝘁𝗵 𝗜𝗻𝘀𝘁𝗮𝗻𝘁 𝗗𝗲𝗹𝗶𝘃𝗲𝗿𝘆 𝗔𝗻𝗱 𝗔𝘂𝘁𝗼𝗺𝗮𝘁𝗲𝗱 𝟮𝟰/𝟳 𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴. ⭐\n❄️❄️❄️❄️❄️❄️❄️❄️❄️\nPress Continue To Open The Menu"
                safe_send(cbot, msg.chat.id, welcome_screen, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("💎 Continue", callback_data="u_continue_main")))

            @cbot.message_handler(commands=['admin'])
            def c_admin(msg):
                uid = msg.from_user.id
                row = fetch_query("SELECT owner_id FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
                bot_owner = row["owner_id"] if row else 0
                if uid != bot_owner and uid != SUPER_ADMIN_ID: return cbot.reply_to(msg, "❌ Access Denied.")
                is_m = (uid == SUPER_ADMIN_ID)
                safe_send(cbot, msg.chat.id, f"👑 Owner Panel (God Mode Active)\n\n🤖 @{bot_username}", reply_markup=get_owner_panel(is_m))

            @cbot.callback_query_handler(func=lambda c: True)
            def c_cbs(call):
                if call.data.startswith("a_") or call.data.startswith("adm_") or call.data.startswith("c_"):
                    uid = call.from_user.id
                    row = fetch_query("SELECT owner_id FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
                    bot_owner = row["owner_id"] if row else 0
                    if uid != bot_owner and uid != SUPER_ADMIN_ID: return cbot.answer_callback_query(call.id, "Access Denied", show_alert=True)
                    handle_owner_callbacks(cbot, bot_id, call, is_master=(uid==SUPER_ADMIN_ID))
                else: handle_user_callbacks(cbot, bot_id, call)

            @cbot.message_handler(func=lambda m: True and not m.text.startswith('/'))
            def c_txts(m): handle_text_inputs(cbot, bot_id, m, is_master=(m.from_user.id==SUPER_ADMIN_ID))

            cbot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except: time.sleep(2)

def run_master_bot_loop():
    global master_is_running
    while True:
        try:
            if not MASTER_BOT_TOKEN: time.sleep(5); continue
            master_bot = telebot.TeleBot(MASTER_BOT_TOKEN, threaded=True)
            try: requests.get(f"https://api.telegram.org/bot{MASTER_BOT_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
            except: pass

            @master_bot.message_handler(commands=['start'])
            def m_start(msg):
                execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (0, ?, ?)", (msg.from_user.id, msg.from_user.username))
                txt = "╔══════════════════════╗\n  ✨ 𝓦𝓔𝗟𝓒𝓞𝓜𝓔 𝗧𝗢 𝗠𝗔𝗦𝗧𝗘𝗥 ✨\n╚══════════════════════╝\n\nChoose an option below:"
                safe_send(master_bot, msg.chat.id, txt, reply_markup=get_user_main_menu())

            @master_bot.message_handler(commands=['admin'])
            def m_admin(msg):
                if msg.from_user.id != SUPER_ADMIN_ID: return master_bot.reply_to(msg, "❌ Access Denied.")
                safe_send(master_bot, msg.chat.id, "👑 MASTER BOT ADMIN PANEL", reply_markup=get_owner_panel(is_master=True))

            @master_bot.callback_query_handler(func=lambda c: True)
            def m_cbs(c):
                if c.data.startswith("a_") or c.data.startswith("adm_") or c.data.startswith("c_") or c.data.startswith("god_"):
                    if c.from_user.id != SUPER_ADMIN_ID: return master_bot.answer_callback_query(c.id, "Access Denied", show_alert=True)
                    handle_owner_callbacks(master_bot, 0, c, is_master=True)
                else: handle_user_callbacks(master_bot, 0, c)

            @master_bot.message_handler(func=lambda m: True and not m.text.startswith('/'))
            def m_txts(msg): handle_text_inputs(master_bot, 0, msg, is_master=True)

            master_is_running = True
            master_bot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except:
            master_is_running = False
            time.sleep(2)

def autonomous_smm_payment_poller():
    time.sleep(5)
    while True:
        try:
            try: requests.get(f"http://127.0.0.1:{RENDER_PORT}/", timeout=3)
            except: pass
            txs = fetch_query("SELECT tx_id, bot_id, user_id, amount, tx_type, target_days FROM transactions WHERE status='pending' LIMIT 5")
            if txs:
                for p in txs:
                    if verify_payment_gateway(p["bot_id"], p["amount"]):
                        execute_query("UPDATE transactions SET status='completed' WHERE tx_id=?", (p["tx_id"],))
                        t_bot = get_bot_instance(p["bot_id"])
                        if p["tx_type"] == "buy_key":
                            k = generate_license_key(p["target_days"])
                            execute_query("UPDATE license_keys SET used_by_bot_id=?, used_by_user_id=? WHERE key_code=?", (p["bot_id"], p["user_id"], k))
                            if t_bot: safe_send(t_bot, p["user_id"], f"🎉 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗔𝗨𝗧𝗢-𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗!\nKey: `{k}`")
                        else:
                            execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (p["amount"], p["amount"], p["bot_id"], p["user_id"]))
                            if t_bot: safe_send(t_bot, p["user_id"], f"🎉 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗔𝗨𝗧𝗢-𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗!\n₹{p['amount']} credited.")
        except: pass
        time.sleep(5)

threading.Thread(target=run_master_bot_loop, daemon=True).start()
threading.Thread(target=autonomous_smm_payment_poller, daemon=True).start()

@app.route('/')
def home(): return "Pranav God Mode Engine v10.0 Active", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
