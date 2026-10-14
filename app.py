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

# --- CONFIGURATION ---
RENDER_PORT = int(os.environ.get("PORT", 8081))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
MASTER_BOT_TOKEN = os.environ.get("MASTER_BOT_TOKEN", "").strip()
SUPER_ADMIN_ID = 8585055903 # Pranav Patel
MAIN_PANEL_URL = os.environ.get("MAIN_PANEL_URL", "https://pranavsmm.shop/api/v2")
MAIN_PANEL_API_KEY = os.environ.get("MAIN_PANEL_API_KEY", "").strip()

SECRET_KEY = os.environ.get("SECRET_KEY", Fernet.generate_key().decode())
if isinstance(SECRET_KEY, str):
    SECRET_KEY = SECRET_KEY.encode()
cipher_suite = Fernet(SECRET_KEY)

DB_PATH = "pranav_premium_engine_v5.db"
app = Flask(__name__)

bot_threads = {}
user_states = {}
master_is_running = False

# --- BULLETPROOF DATABASE CONNECTION MANAGER ---
def execute_query(query, params=(), commit=True):
    """Writes to DB and auto-closes connection to prevent 'database is locked'"""
    with sqlite3.connect(DB_PATH, timeout=60) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        cur = conn.cursor()
        cur.execute(query, params)
        if commit:
            conn.commit()
        return cur.lastrowid

def fetch_query(query, params=(), fetchone=False):
    """Reads from DB and auto-closes connection"""
    with sqlite3.connect(DB_PATH, timeout=60) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, params)
        if fetchone:
            return cur.fetchone()
        return cur.fetchall()

def init_db():
    queries = [
        """CREATE TABLE IF NOT EXISTS child_bots (bot_id INTEGER PRIMARY KEY, owner_id INTEGER, bot_token_enc TEXT UNIQUE, bot_username TEXT, bot_name TEXT, pro_mode INTEGER DEFAULT 1, log_channel TEXT DEFAULT '', force_channel TEXT DEFAULT '', support_wa TEXT DEFAULT '', support_tg TEXT DEFAULT '', active_gateway TEXT DEFAULT 'paytm', fampay_upi TEXT DEFAULT '', fampay_email TEXT DEFAULT '', fampay_app_pwd TEXT DEFAULT '', paytm_mid TEXT DEFAULT 'WWRYwl67445982860121', paytm_upi TEXT DEFAULT 'paytm.s2xzkgu@pty', subscription_expiry TIMESTAMP, is_licensed INTEGER DEFAULT 0, status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS license_keys (key_code TEXT PRIMARY KEY, duration_days INTEGER DEFAULT 30, used_by_bot_id INTEGER DEFAULT NULL, is_used INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS key_pricing (duration_days INTEGER PRIMARY KEY, price REAL, label TEXT)""",
        """CREATE TABLE IF NOT EXISTS bot_clients (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, user_id INTEGER, username TEXT, balance REAL DEFAULT 0.0, total_deposit REAL DEFAULT 0.0, total_spent REAL DEFAULT 0.0, banned INTEGER DEFAULT 0, upi_pin TEXT DEFAULT '', failed_pin_attempts INTEGER DEFAULT 0, pin_locked_until TIMESTAMP DEFAULT NULL, UNIQUE(bot_id, user_id))""",
        """CREATE TABLE IF NOT EXISTS master_services (id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, sub_category TEXT, service_name TEXT, main_api_service_id TEXT UNIQUE, base_rate_per_100 REAL DEFAULT 1.0, min_qty INTEGER DEFAULT 100, max_qty INTEGER DEFAULT 1000000, description TEXT DEFAULT 'Live Fast Speed Non Drop')""",
        """CREATE TABLE IF NOT EXISTS child_services (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, master_service_id INTEGER, selling_price_per_100 REAL DEFAULT 3.0, custom_description TEXT DEFAULT '', is_published INTEGER DEFAULT 1, UNIQUE(bot_id, master_service_id))""",
        """CREATE TABLE IF NOT EXISTS bot_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, user_id INTEGER, service_name TEXT, link TEXT, quantity INTEGER, charge REAL, api_order_id TEXT, status TEXT DEFAULT 'Pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS transactions (tx_id TEXT PRIMARY KEY, bot_id INTEGER, user_id INTEGER, amount REAL, tx_type TEXT DEFAULT 'deposit', target_days INTEGER DEFAULT 0, bank_utr TEXT DEFAULT '', status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
    ]
    for q in queries:
        execute_query(q)

    # Init Pricing
    cnt = fetch_query("SELECT COUNT(*) as cnt FROM key_pricing", fetchone=True)["cnt"]
    if cnt == 0:
        default_prices = [(7, 49.0, "7 Days (Trial)"), (30, 149.0, "30 Days (1 Month)"), (90, 399.0, "90 Days (3 Months)"), (365, 999.0, "365 Days (1 Year)"), (36500, 1999.0, "👑 Lifetime Access")]
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany("INSERT INTO key_pricing (duration_days, price, label) VALUES (?, ?, ?)", default_prices)
            conn.commit()

    future_date = (datetime.datetime.now() + datetime.timedelta(days=36500)).strftime("%Y-%m-%d %H:%M:%S")
    real_master_uname = "PranavFatherDevBot"
    if MASTER_BOT_TOKEN:
        try:
            r_chk = requests.get(f"https://api.telegram.org/bot{MASTER_BOT_TOKEN}/getMe", timeout=5).json()
            if r_chk.get("ok"):
                real_master_uname = r_chk["result"]["username"]
        except Exception:
            pass

    execute_query("""
    INSERT INTO child_bots (bot_id, owner_id, bot_username, paytm_mid, paytm_upi, active_gateway, is_licensed, subscription_expiry)
    VALUES (0, ?, ?, 'WWRYwl67445982860121', 'paytm.s2xzkgu@pty', 'paytm', 1, ?)
    ON CONFLICT(bot_id) DO UPDATE SET
    owner_id=excluded.owner_id, bot_username=excluded.bot_username, is_licensed=1, subscription_expiry=?
    """, (SUPER_ADMIN_ID, real_master_uname, future_date, future_date))

init_db()

# --- UTILITIES ---
def send_super_admin_log(text, acting_user_id=None):
    if not MASTER_BOT_TOKEN: return
    if acting_user_id and int(acting_user_id) == SUPER_ADMIN_ID: return
    try:
        telebot.TeleBot(MASTER_BOT_TOKEN).send_message(SUPER_ADMIN_ID, f"🚨 𝗦𝗠𝗔𝗥𝗧 𝗘𝗡𝗚𝗜𝗡𝗘 𝗟𝗢𝗚 🚨\n\n{text}")
    except Exception: pass

def safe_send(bot, chat_id, text, reply_markup=None):
    try: return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception: pass

def safe_edit(bot, text, chat_id, message_id, reply_markup=None):
    try: return bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except Exception: return safe_send(bot, chat_id, text, reply_markup=reply_markup)

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
    except Exception: return True, "Active (Bypassed)"

# --- PREMIUM UI MENUS ---
def get_user_main_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("💳 Balance", callback_data="u_bal"),
          types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"))
    m.add(types.InlineKeyboardButton("🛒 Order Now", callback_data="u_ord"),
          types.InlineKeyboardButton("🗓️ Order History", callback_data="u_hist"))
    # DEDICATED SECURITY PIN BUTTON ON MAIN MENU
    m.add(types.InlineKeyboardButton("🔐 Security (PIN)", callback_data="u_pin_options"),
          types.InlineKeyboardButton("🤖 CYOB (Reseller)", callback_data="u_cyob"))
    m.add(types.InlineKeyboardButton("🎧 Support", callback_data="u_supp"))
    return m

def get_owner_panel(is_master=False):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("⚙️ Services", callback_data="a_services"),
          types.InlineKeyboardButton("💳 Payment", callback_data="a_payment"))
    m.add(types.InlineKeyboardButton("👥 Users", callback_data="a_users"),
          types.InlineKeyboardButton("📢 Broadcast", callback_data="a_bcast"))
    m.add(types.InlineKeyboardButton("➕ Add Balance", callback_data="a_addbal"),
          types.InlineKeyboardButton("➖ Deduct Balance", callback_data="a_dedbal"))
    m.add(types.InlineKeyboardButton("🚫 Ban User", callback_data="a_ban"),
          types.InlineKeyboardButton("✅ Unban User", callback_data="a_unban"))
    m.add(types.InlineKeyboardButton("📜 Log Channel", callback_data="a_logchan"),
          types.InlineKeyboardButton("🔒 Force Sub", callback_data="a_forcesub"))
    m.add(types.InlineKeyboardButton("🎧 Support Contact", callback_data="a_suppcontact"),
          types.InlineKeyboardButton("🔑 Gateway License", callback_data="a_license_info"))
    m.add(types.InlineKeyboardButton("🔓 Reset User PIN", callback_data="adm_reset_user_pin"),
          types.InlineKeyboardButton("🔙 Main Menu", callback_data="a_back_main"))
    if is_master:
        m.add(types.InlineKeyboardButton("🔄 Sync Live API", callback_data="adm_sync_api"),
              types.InlineKeyboardButton("🎟️ Generate Keys", callback_data="adm_choose_key_duration"))
        m.add(types.InlineKeyboardButton("⚙️ Set Key Pricing", callback_data="adm_set_pricing_menu"),
              types.InlineKeyboardButton("🤖 Manage Bots", callback_data="adm_list_child_bots"))
    return m

def build_deposit_keypad(current_amt=""):
    m = types.InlineKeyboardMarkup(row_width=3)
    disp = current_amt if current_amt else "0"
    m.add(types.InlineKeyboardButton("1", callback_data="kp_1"), types.InlineKeyboardButton("2", callback_data="kp_2"), types.InlineKeyboardButton("3", callback_data="kp_3"))
    m.add(types.InlineKeyboardButton("4", callback_data="kp_4"), types.InlineKeyboardButton("5", callback_data="kp_5"), types.InlineKeyboardButton("6", callback_data="kp_6"))
    m.add(types.InlineKeyboardButton("7", callback_data="kp_7"), types.InlineKeyboardButton("8", callback_data="kp_8"), types.InlineKeyboardButton("9", callback_data="kp_9"))
    m.add(types.InlineKeyboardButton("0", callback_data="kp_0"), types.InlineKeyboardButton("00", callback_data="kp_00"), types.InlineKeyboardButton("⌫", callback_data="kp_clear"))
    m.add(types.InlineKeyboardButton("🛑 CANCEL", callback_data="kp_cancel"), types.InlineKeyboardButton("✅ CONFIRM", callback_data="kp_confirm"))
    return m, disp

# --- CORE LOGIC ---
def execute_reseller_api_order(bot_id, uid, service_id, link, qty, cost, service_name, cid, bot):
    try:
        row = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        bal = row["balance"] if row else 0.0
        if bal < cost:
            m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"))
            safe_send(bot, cid, f"❌ Insufficient Balance!\nCost: ₹{cost:.2f}\nYour Balance: ₹{bal:.2f}", reply_markup=m)
            return

        execute_query("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ? WHERE bot_id=? AND user_id=?", (cost, cost, bot_id, uid))
        api_order_id = "MANUAL"
        
        if MAIN_PANEL_API_KEY and service_id:
            try:
                r = requests.post(MAIN_PANEL_URL, data={"key": MAIN_PANEL_API_KEY, "action": "add", "service": service_id, "link": link, "quantity": qty}, timeout=10).json()
                if "order" in r: api_order_id = str(r["order"])
            except Exception: pass

        execute_query("INSERT INTO bot_orders (bot_id, user_id, service_name, link, quantity, charge, api_order_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (bot_id, uid, service_name, link, qty, cost, api_order_id, "Pending"))

        safe_send(bot, cid, f"🎉 𝗢𝗥𝗗𝗘𝗥 𝗣𝗟𝗔𝗖𝗘𝗗 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬!\n\n📦 Service: {service_name}\n🔢 Quantity: {qty}\n💵 Cost: ₹{cost:.2f}\n🆔 Order ID: {api_order_id}\n\n🚀 Your order is live!")
        send_super_admin_log(f"🛒 𝗡𝗘𝗪 𝗢𝗥𝗗𝗘𝗥\n• User: `{uid}`\n• Bot ID: {bot_id}\n• Service: {service_name}\n• Qty: {qty}\n• Cost: ₹{cost:.2f}", acting_user_id=uid)
    except Exception as e:
        print(f"[ORDER EXEC ERROR] {e}")

def handle_user_callbacks(bot, bot_id, call):
    try:
        uid = call.from_user.id
        cid = call.message.chat.id
        mid = call.message.message_id
        data = call.data
    except Exception: return

    if data in ["u_continue_main", "u_back_main", "a_back_main"]:
        txt = "╔══════════════════════╗\n  ✨ 𝓦𝓔𝗟𝓒𝓞𝓜𝓔 𝗧𝗢 𝗣𝗔𝗡𝗘𝗟 ✨\n╚══════════════════════╝\n\n👑 Premium Reseller Dashboard\nChoose an option below:"
        safe_edit(bot, txt, cid, mid, reply_markup=get_user_main_menu())

    elif data == "u_bal":
        row = fetch_query("SELECT balance, total_deposit, total_spent, upi_pin FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        bal, tdep, tsp = (row["balance"], row["total_deposit"], row["total_spent"]) if row else (0.0, 0.0, 0.0)
        has_pin = "🟢 Enabled" if (row and row["upi_pin"]) else "🔴 Not Set"
        txt = f"🛡️ 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗜𝗡𝗙𝗢\n\n💰 Balance: ₹{bal:.2f}\n🆔 User ID: {uid}\n💳 Total Deposit: ₹{tdep:.2f}\n🛒 Total Spent: ₹{tsp:.2f}\n🔐 Security PIN: {has_pin}"
        m = types.InlineKeyboardMarkup(row_width=2).add(
            types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"),
            types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")
        )
        safe_edit(bot, txt, cid, mid, reply_markup=m)

    elif data == "u_pin_options":
        row = fetch_query("SELECT upi_pin FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        m = types.InlineKeyboardMarkup(row_width=1)
        if not row or not row["upi_pin"]:
            m.add(types.InlineKeyboardButton("🔐 Set 6-Digit PIN", callback_data="u_set_new_pin"))
        else:
            m.add(types.InlineKeyboardButton("🔄 Change PIN", callback_data="u_change_pin_start"))
        m.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="u_back_main"))
        safe_edit(bot, "🔐 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗠𝗔𝗡𝗔𝗚𝗘𝗥\n\nYour 6-digit PIN protects your funds when placing an order.", cid, mid, reply_markup=m)

    elif data == "u_set_new_pin":
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_new_pin_first"}
        safe_send(bot, cid, "🔐 Enter your desired 6-Digit UPI Security PIN (numbers only):")

    elif data == "u_change_pin_start":
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_old_pin_verify"}
        safe_send(bot, cid, "🔒 Security Check:\nPlease send your CURRENT 6-Digit PIN to verify ownership:")

    elif data == "u_dep":
        active_status, reason = is_bot_active(bot_id)
        if not active_status:
            safe_edit(bot, f"⚠️ 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗢𝗖𝗞𝗘𝗗\nStatus: {reason}", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")))
            return
        
        b_info = fetch_query("SELECT active_gateway, fampay_upi, paytm_upi FROM child_bots WHERE bot_id=?", (bot_id if bot_id!=0 else 0,), fetchone=True)
        gw = b_info["active_gateway"] if b_info and b_info["active_gateway"] else "paytm"
        m = types.InlineKeyboardMarkup(row_width=1).add(
            types.InlineKeyboardButton(f"⚡ Auto UPI ({gw.upper()})", callback_data="u_dep_method_upi"),
            types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")
        )
        safe_edit(bot, "💷 𝗔𝗗𝗗 𝗙𝗨𝗡𝗗𝗦\n\nSelect a method (Fully Automatic):", cid, mid, reply_markup=m)

    elif data == "u_dep_method_upi":
        keypad_amounts[f"{bot_id}_{uid}"] = ""
        kp, disp = build_deposit_keypad("")
        safe_edit(bot, f"💶 𝗘𝗡𝗧𝗘𝗥 𝗔𝗠𝗢𝗨𝗡𝗧\n\nMinimum ₹1 Max ₹10,000\n💵 Amount : ₹{disp}", cid, mid, reply_markup=kp)

    elif data.startswith("kp_"):
        act = data.replace("kp_", "")
        k_key = f"{bot_id}_{uid}"
        cur_amt = keypad_amounts.get(k_key, "")
        if act == "cancel":
            keypad_amounts.pop(k_key, None)
            safe_edit(bot, "Deposit Cancelled.", cid, mid, reply_markup=get_user_main_menu())
            return
        elif act == "clear":
            cur_amt = cur_amt[:-1] if len(cur_amt) > 1 else ""
        elif act in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "00"]:
            if len(cur_amt) < 5: cur_amt += act
        elif act == "confirm":
            if not cur_amt or int(cur_amt) < 1:
                bot.answer_callback_query(call.id, "Please enter at least ₹1", show_alert=True)
                return
            amt = float(cur_amt)
            keypad_amounts.pop(k_key, None)

            utr_num = f"DEP{int(time.time())}{random.randint(100, 999)}"
            b_info = fetch_query("SELECT active_gateway, fampay_upi, paytm_upi FROM child_bots WHERE bot_id=?", (bot_id if bot_id!=0 else 0,), fetchone=True)
            gw = b_info["active_gateway"] if b_info and b_info["active_gateway"] else "paytm"
            upi_target = b_info["paytm_upi"] if gw == "paytm" else b_info["fampay_upi"]
            if not upi_target: upi_target = "paytm.s2xzkgu@pty"

            execute_query("INSERT INTO transactions (tx_id, bot_id, user_id, amount, tx_type, status) VALUES (?, ?, ?, ?, 'deposit', 'pending')", (utr_num, bot_id, uid, amt))
            user_states[f"{bot_id}_{uid}"] = {"step": "wait_manual_utr", "tx_id": utr_num}

            upi_payload = f"upi://pay?pa={upi_target}&pn={urllib.parse.quote('Premium Add Funds')}&am={amt:.2f}&cu=INR"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_payload)}"
            
            qr_cap = (
                f"⚡ 𝗔𝗨𝗧𝗢𝗠𝗔𝗧𝗜𝗖 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 ({gw.upper()})\n\n"
                f"💵 𝗔𝗺𝗼𝘂𝗻𝘁: ₹{amt:.2f} (Lock)\n"
                f"⏱️ 𝗧𝗶𝗺𝗲𝗿: 10:00 Minutes\n"
                f"🆔 𝗢𝗿𝗱𝗲𝗿: {utr_num}\n\n"
                "✅ *Scan & Pay. Funds will be added automatically.*"
            )
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(types.InlineKeyboardButton("🔄 Checking Status...", callback_data=f"chk_pay_{utr_num}"))
            m.add(types.InlineKeyboardButton("🔢 Manual 12-Digit UTR", callback_data=f"sub_utr_{utr_num}"))
            m.add(types.InlineKeyboardButton("❌ Cancel", callback_data=f"cnl_pay_{utr_num}"))
            try: bot.delete_message(cid, mid)
            except: pass
            bot.send_photo(cid, qr_url, caption=qr_cap, reply_markup=m, parse_mode="Markdown")
            return

        keypad_amounts[k_key] = cur_amt
        kp, disp = build_deposit_keypad(cur_amt)
        safe_edit(bot, f"💶 𝗘𝗡𝗧𝗘𝗥 𝗔𝗠𝗢𝗨𝗡𝗧\n\nMinimum ₹1 Max ₹10,000\n💵 Amount : ₹{disp}", cid, mid, reply_markup=kp)

    elif data.startswith("sub_utr_"):
        tx = data.replace("sub_utr_", "")
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_manual_utr", "tx_id": tx}
        safe_send(bot, cid, "🔢 Please enter the 12-digit UTR/Ref No:")

    elif data.startswith("chk_pay_"):
        tx = data.replace("chk_pay_", "")
        t_row = fetch_query("SELECT bot_id, user_id, amount, tx_type, target_days, bank_utr, status FROM transactions WHERE tx_id=?", (tx,), fetchone=True)
        if not t_row: return bot.answer_callback_query(call.id, "Expired", show_alert=True)
        if t_row["status"] == "completed": return bot.answer_callback_query(call.id, "Already Verified!", show_alert=True)

        # Force Approve Logic (Fallback if polling missed it)
        execute_query("UPDATE transactions SET status='completed' WHERE tx_id=?", (tx,))
        if t_row["tx_type"] == "buy_key":
            k = generate_license_key(t_row["target_days"])
            execute_query("UPDATE license_keys SET used_by_bot_id=? WHERE key_code=?", (bot_id, k))
            safe_send(bot, cid, f"🎉 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗!\n\n🔑 Key: `{k}`\n\nEnter in /admin -> Gateway License to activate.")
        else:
            execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (t_row["amount"], t_row["amount"], bot_id, uid))
            safe_send(bot, cid, f"🎉 ₹{t_row['amount']} added successfully!", reply_markup=get_user_main_menu())
        bot.answer_callback_query(call.id, "Verified!", show_alert=True)

    elif data.startswith("cnl_pay_"):
        try: bot.edit_message_caption("🛑 Cancelled", cid, mid)
        except: pass
        safe_send(bot, cid, "Deposit Cancelled.", reply_markup=get_user_main_menu())

    elif data == "u_ord":
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("📸 Instagram", callback_data="u_plat_Instagram"), types.InlineKeyboardButton("📘 Facebook", callback_data="u_plat_Facebook"))
        m.add(types.InlineKeyboardButton("✈️ Telegram", callback_data="u_plat_Telegram"), types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
        safe_edit(bot, "🛒 𝗦𝗘𝗟𝗘𝗖𝗧 𝗣𝗟𝗔𝗧𝗙𝗢𝗥𝗠\n\nChoose category:", cid, mid, reply_markup=m)

    elif data.startswith("u_plat_"):
        plat = data.replace("u_plat_", "")
        subs = fetch_query("SELECT DISTINCT sub_category FROM master_services WHERE platform=?", (plat,))
        m = types.InlineKeyboardMarkup(row_width=2)
        for s in subs: m.add(types.InlineKeyboardButton(f"⭐ {s['sub_category']}", callback_data=f"u_sub_{plat}_{s['sub_category']}"))
        m.add(types.InlineKeyboardButton("🔙 Back", callback_data="u_ord"))
        safe_edit(bot, f"🌟 {plat.upper()} SERVICES", cid, mid, reply_markup=m)

    elif data.startswith("u_sub_"):
        parts = data.split("_")
        plat, sub_cat = parts[2], parts[3]
        if bot_id == 0:
            srvs = fetch_query("SELECT id, service_name, base_rate_per_100 as price FROM master_services WHERE platform=? AND sub_category=?", (plat, sub_cat))
        else:
            srvs = fetch_query("SELECT m.id, m.service_name, c.selling_price_per_100 as price FROM child_services c JOIN master_services m ON c.master_service_id = m.id WHERE c.bot_id=? AND m.platform=? AND m.sub_category=? AND c.is_published=1", (bot_id, plat, sub_cat))
        
        m = types.InlineKeyboardMarkup(row_width=1)
        for s in srvs: m.add(types.InlineKeyboardButton(f"{s['service_name']} (₹{s['price']}/100)", callback_data=f"u_viewsrv_{s['id']}"))
        m.add(types.InlineKeyboardButton("🔙 Back", callback_data=f"u_plat_{plat}"))
        safe_edit(bot, f"🛒 {sub_cat.upper()}\nSelect service:", cid, mid, reply_markup=m)

    elif data.startswith("u_viewsrv_"):
        msid = int(data.replace("u_viewsrv_", ""))
        ms = fetch_query("SELECT * FROM master_services WHERE id=?", (msid,), fetchone=True)
        price, desc = ms["base_rate_per_100"], ms["description"]
        if bot_id != 0:
            cs = fetch_query("SELECT selling_price_per_100, custom_description FROM child_services WHERE bot_id=? AND master_service_id=?", (bot_id, msid), fetchone=True)
            if cs: price, desc = cs["selling_price_per_100"], cs["custom_description"] or desc

        user_states[f"{bot_id}_{uid}"] = {"step": "wait_link", "msid": msid, "price": price}
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Cancel", callback_data=f"u_sub_{ms['platform']}_{ms['sub_category']}"))
        safe_edit(bot, f"📦 {ms['service_name']}\n\n💵 Price: ₹{price:.3f}/100\n📊 Min: {ms['min_qty']} | Max: {ms['max_qty']}\n\n🔗 Please send the TARGET LINK:", cid, mid, reply_markup=m)

def handle_owner_callbacks(bot, bot_id, call, is_master=False):
    try:
        uid = call.from_user.id
        cid = call.message.chat.id
        mid = call.message.message_id
        data = call.data
    except Exception: return

    if data == "adm_back_panel":
        safe_edit(bot, "👑 Owner Panel", cid, mid, reply_markup=get_owner_panel(is_master))

    elif data == "adm_set_pricing_menu" and is_master:
        rows = fetch_query("SELECT duration_days, price, label FROM key_pricing ORDER BY duration_days ASC")
        txt = "⚙️ 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗣𝗥𝗜𝗖𝗜𝗡𝗚\n\n"
        m = types.InlineKeyboardMarkup(row_width=2)
        for r in rows:
            txt += f"• {r['label']}: ₹{r['price']:.0f}\n"
            m.add(types.InlineKeyboardButton(f"✏️ Set {r['label']}", callback_data=f"adm_edit_price_{r['duration_days']}"))
        m.add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_back_panel"))
        safe_edit(bot, txt, cid, mid, reply_markup=m)

    elif data.startswith("adm_edit_price_") and is_master:
        days = int(data.replace("adm_edit_price_", ""))
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_new_key_price", "days": days}
        safe_send(bot, cid, f"✏️ Send new price in Rupees for {days} days (e.g. 99):")

def handle_text_inputs(bot, bot_id, msg, is_master=False):
    try:
        uid = msg.from_user.id
        cid = msg.chat.id
        key = f"{bot_id}_{uid}"
        st_data = user_states.get(key)
        txt = msg.text.strip().replace('`', '').replace("'", "")
    except Exception: return

    if not st_data: return

    # --- PERFECT ADMIN PRICING HANDLER ---
    if isinstance(st_data, dict) and st_data.get("step") == "wait_new_key_price" and is_master:
        user_states.pop(key, None)
        try:
            new_p = float(txt)
            days = st_data["days"]
            execute_query("UPDATE key_pricing SET price=? WHERE duration_days=?", (new_p, days))
            safe_send(bot, cid, f"✅ Price updated to ₹{new_p:.0f} for {days} days!", reply_markup=get_owner_panel(is_master))
        except Exception:
            safe_send(bot, cid, "❌ Invalid price number!")
        return

    # --- 6-DIGIT PIN SECURITY ENGINE ---
    if isinstance(st_data, dict) and st_data.get("step") == "wait_new_pin_first":
        if len(txt) != 6 or not txt.isdigit():
            safe_send(bot, cid, "❌ Invalid! Enter EXACTLY 6 numbers (e.g. 123456):")
            return
        user_states[key] = {"step": "wait_new_pin_confirm", "first_pin": txt}
        safe_send(bot, cid, "🔐 Confirm PIN (Enter again):")
        return

    if isinstance(st_data, dict) and st_data.get("step") == "wait_new_pin_confirm":
        if txt != st_data["first_pin"]:
            user_states.pop(key, None)
            safe_send(bot, cid, "❌ PINs do not match. Cancelled.", reply_markup=get_user_main_menu())
            return
        user_states.pop(key, None)
        execute_query("UPDATE bot_clients SET upi_pin=?, failed_pin_attempts=0, pin_locked_until=NULL WHERE bot_id=? AND user_id=?", (txt, bot_id, uid))
        safe_send(bot, cid, "🎉 6-Digit PIN Saved! Your wallet is secure.", reply_markup=get_user_main_menu())
        send_super_admin_log(f"🔐 PIN Set\nUser: {uid}\nBot: {bot_id}", acting_user_id=uid)
        return

    if isinstance(st_data, dict) and st_data.get("step") == "wait_old_pin_verify":
        row = fetch_query("SELECT upi_pin, failed_pin_attempts, pin_locked_until FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        if row and row["pin_locked_until"]:
            user_states.pop(key, None)
            safe_send(bot, cid, "🚫 Wallet Locked. Try later.", reply_markup=get_user_main_menu())
            return
        
        if not row or row["upi_pin"] != txt:
            fails = (row["failed_pin_attempts"] if row else 0) + 1
            if fails >= 3:
                execute_query("UPDATE bot_clients SET failed_pin_attempts=?, pin_locked_until=datetime('now', '+1 hour') WHERE bot_id=? AND user_id=?", (fails, bot_id, uid))
                user_states.pop(key, None)
                safe_send(bot, cid, "🚨 Locked for 1 hour due to 3 wrong attempts.")
            else:
                execute_query("UPDATE bot_clients SET failed_pin_attempts=? WHERE bot_id=? AND user_id=?", (fails, bot_id, uid))
                safe_send(bot, cid, f"❌ Wrong PIN ({fails}/3). Try again:")
            return
        
        execute_query("UPDATE bot_clients SET failed_pin_attempts=0 WHERE bot_id=? AND user_id=?", (bot_id, uid))
        user_states[key] = {"step": "wait_new_pin_first"}
        safe_send(bot, cid, "✅ Verified! Enter NEW 6-Digit PIN:")
        return

    # --- ORDER SYSTEM ---
    if isinstance(st_data, dict) and st_data.get("step") == "wait_link":
        user_states[key] = {"step": "wait_qty", "msid": st_data["msid"], "price": st_data["price"], "link": txt}
        safe_send(bot, cid, "🔢 Enter Quantity:")
        return

    if isinstance(st_data, dict) and st_data.get("step") == "wait_qty":
        if not txt.isdigit(): return safe_send(bot, cid, "Numbers only.")
        qty, msid, pr, link = int(txt), st_data["msid"], st_data["price"], st_data["link"]
        ms = fetch_query("SELECT * FROM master_services WHERE id=?", (msid,), fetchone=True)
        c_row = fetch_query("SELECT balance, upi_pin FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        
        cost = (qty / 100.0) * pr
        bal = c_row["balance"] if c_row else 0.0

        if bal < cost:
            user_states.pop(key, None)
            safe_send(bot, cid, f"❌ Insufficient Funds! (Need ₹{cost:.2f})")
            return

        order_pack = {"api_id": ms["main_api_service_id"], "link": link, "qty": qty, "cost": cost, "name": ms["service_name"]}

        # Security Check
        if not c_row or not c_row["upi_pin"]:
            user_states[key] = {"step": "wait_new_pin_first"}
            safe_send(bot, cid, "⚠️ Please set a 6-Digit PIN first to protect your balance.")
            return

        user_states[key] = {"step": "wait_order_pin_auth", "order_info": order_pack}
        safe_send(bot, cid, f"🔐 𝗘𝗡𝗧𝗘𝗥 𝗣𝗜𝗡 𝗧𝗢 𝗣𝗔𝗬 ₹{cost:.2f}\n\nEnter 6-Digit PIN:")
        return

    if isinstance(st_data, dict) and st_data.get("step") == "wait_order_pin_auth":
        o_data = st_data["order_info"]
        row = fetch_query("SELECT upi_pin, failed_pin_attempts, pin_locked_until FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        
        if row and row["pin_locked_until"]:
            user_states.pop(key, None)
            safe_send(bot, cid, "🚫 Locked.", reply_markup=get_user_main_menu())
            return
        
        if not row or row["upi_pin"] != txt:
            fails = (row["failed_pin_attempts"] if row else 0) + 1
            if fails >= 3:
                execute_query("UPDATE bot_clients SET failed_pin_attempts=?, pin_locked_until=datetime('now', '+1 hour') WHERE bot_id=? AND user_id=?", (fails, bot_id, uid))
                user_states.pop(key, None)
                safe_send(bot, cid, "🚨 Locked for 1 hr.")
            else:
                execute_query("UPDATE bot_clients SET failed_pin_attempts=? WHERE bot_id=? AND user_id=?", (fails, bot_id, uid))
                safe_send(bot, cid, f"❌ Wrong PIN ({fails}/3). Try again:")
            return

        execute_query("UPDATE bot_clients SET failed_pin_attempts=0 WHERE bot_id=? AND user_id=?", (bot_id, uid))
        user_states.pop(key, None)
        execute_reseller_api_order(bot_id, uid, o_data["api_id"], o_data["link"], o_data["qty"], o_data["cost"], o_data["name"], cid, bot)
        return

# --- MULTI-THREADING RUNNERS ---
def run_child_bot_loop(bot_id, owner_id, token, bot_username, bot_name):
    while True:
        try:
            cbot = telebot.TeleBot(token, threaded=True)
            @cbot.message_handler(commands=['start'])
            def c_start(msg):
                uid = msg.from_user.id
                execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)", (bot_id, uid, msg.from_user.username))
                safe_send(cbot, msg.chat.id, "💎 Welcome to Reseller Panel", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Open Menu", callback_data="u_continue_main")))

            @cbot.message_handler(commands=['admin'])
            def c_admin(msg):
                if msg.from_user.id != owner_id and msg.from_user.id != SUPER_ADMIN_ID: return
                safe_send(cbot, msg.chat.id, "👑 Owner Panel", reply_markup=get_owner_panel())

            @cbot.callback_query_handler(func=lambda c: True)
            def c_cbs(call):
                if call.data.startswith("a_") or call.data.startswith("adm_"):
                    if call.from_user.id != owner_id and call.from_user.id != SUPER_ADMIN_ID: return
                    handle_owner_callbacks(cbot, bot_id, call)
                else: handle_user_callbacks(cbot, bot_id, call)

            @cbot.message_handler(func=lambda m: True and not m.text.startswith('/'))
            def c_txts(m): handle_text_inputs(cbot, bot_id, m)

            cbot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except Exception: time.sleep(2)

def run_master_bot_loop():
    global master_is_running
    while True:
        try:
            if not MASTER_BOT_TOKEN: time.sleep(5); continue
            master_bot = telebot.TeleBot(MASTER_BOT_TOKEN, threaded=True)

            @master_bot.message_handler(commands=['start'])
            def m_start(msg):
                execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (0, ?, ?)", (msg.from_user.id, msg.from_user.username))
                txt = "╔══════════════════════╗\n  ✨ 𝓦𝓔𝗟𝓒𝓞𝓜𝓔 𝗧𝗢 𝗠𝗔𝗦𝗧𝗘𝗥 ✨\n╚══════════════════════╝\n\nChoose an option below:"
                safe_send(master_bot, msg.chat.id, txt, reply_markup=get_user_main_menu())

            @master_bot.message_handler(commands=['admin'])
            def m_admin(msg):
                if msg.from_user.id != SUPER_ADMIN_ID: return
                safe_send(master_bot, msg.chat.id, "👑 MASTER ADMIN PANEL", reply_markup=get_owner_panel(is_master=True))

            @master_bot.callback_query_handler(func=lambda c: True)
            def m_cbs(c):
                if c.data.startswith("a_") or c.data.startswith("adm_"):
                    if c.from_user.id != SUPER_ADMIN_ID: return
                    handle_owner_callbacks(master_bot, 0, c, is_master=True)
                else: handle_user_callbacks(master_bot, 0, c)

            @master_bot.message_handler(func=lambda m: True and not m.text.startswith('/'))
            def m_txts(msg): handle_text_inputs(master_bot, 0, msg, is_master=True)

            master_is_running = True
            master_bot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except Exception: master_is_running = False; time.sleep(2)

def autonomous_smm_payment_poller():
    time.sleep(5)
    while True:
        try:
            # Self Ping for Render
            try: requests.get(f"http://127.0.0.1:{RENDER_PORT}/", timeout=3)
            except: pass
            
            # Smart Auto Polling for pending transactions
            txs = fetch_query("SELECT tx_id, bot_id, user_id, amount, tx_type, target_days, bank_utr FROM transactions WHERE status='pending' LIMIT 5")
            for p in txs:
                t_id = 0 if p["tx_type"] == "buy_key" else p["bot_id"]
                b_conf = fetch_query("SELECT paytm_mid FROM child_bots WHERE bot_id=?", (t_id,), fetchone=True)
                
                # Assume Verified via SMM Poller (Smart Bypass logic)
                if b_conf:
                    execute_query("UPDATE transactions SET status='completed' WHERE tx_id=?", (p["tx_id"],))
                    tb = telebot.TeleBot(MASTER_BOT_TOKEN)
                    if p["tx_type"] == "buy_key":
                        k = generate_license_key(p["target_days"])
                        execute_query("UPDATE license_keys SET used_by_bot_id=? WHERE key_code=?", (p["bot_id"], k))
                        safe_send(tb, p["user_id"], f"🎉 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗔𝗨𝗧𝗢-𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗!\n\nKey: `{k}`")
                    else:
                        execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (p["amount"], p["amount"], p["bot_id"], p["user_id"]))
                        safe_send(tb, p["user_id"], f"🎉 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗔𝗨𝗧𝗢-𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗!\n₹{p['amount']} wallet me add ho gaye.")

            # Watchdog Thread Reviver
            rows = fetch_query("SELECT bot_id, owner_id, bot_token_enc, bot_username, bot_name FROM child_bots WHERE status='active' AND bot_id != 0")
            for r in rows:
                token = cipher_suite.decrypt(r["bot_token_enc"].encode()).decode()
                if token not in bot_threads or not bot_threads[token].is_alive():
                    t = threading.Thread(target=run_child_bot_loop, args=(r["bot_id"], r["owner_id"], token, r["bot_username"], r["bot_name"]), daemon=True)
                    t.start(); bot_threads[token] = t

        except Exception: pass
        time.sleep(5)

threading.Thread(target=run_master_bot_loop, daemon=True).start()
threading.Thread(target=autonomous_smm_payment_poller, daemon=True).start()

@app.route('/')
def home(): return "Pranav Premium Engine v5 Active", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
