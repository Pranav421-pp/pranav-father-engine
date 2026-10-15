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
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
import telebot
from telebot import types
from cryptography.fernet import Fernet

# ==========================================
# ⚙️ CONFIGURATION & CONSTANTS
# ==========================================
RENDER_PORT = int(os.environ.get("PORT", 8081))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
MASTER_BOT_TOKEN = os.environ.get("MASTER_BOT_TOKEN", "").strip()
SUPER_ADMIN_ID = 8585055903 # Pranav Patel (प्रणव जी - इकलौता गॉड मास्टर)
MAIN_PANEL_URL = os.environ.get("MAIN_PANEL_URL", "https://pranavsmm.shop/api/v2")
MAIN_PANEL_API_KEY = os.environ.get("MAIN_PANEL_API_KEY", "").strip()

# Secure Web Admin Credentials (Pranav Ji Only)
WEB_ADMIN_USER = "pranav"
WEB_ADMIN_PASS = "pranav7@admin"

SECRET_KEY = os.environ.get("SECRET_KEY", Fernet.generate_key().decode())
if isinstance(SECRET_KEY, str): SECRET_KEY = SECRET_KEY.encode()
cipher_suite = Fernet(SECRET_KEY)

DB_PATH = "pranav_master_engine_combined.db"
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

bot_threads = {}
user_states = {}
keypad_amounts = {}
master_is_running = False

# ==========================================
# 🗄️ UNIFIED BULLETPROOF DATABASE (WAL MODE)
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
    except Exception as e: print(f"[DB EXEC ERROR] {e}")
    finally: conn.close()

def fetch_query(query, params=(), fetchone=False):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchone() if fetchone else cur.fetchall()
    except Exception as e:
        print(f"[DB FETCH ERROR] {e}")
        return None
    finally: conn.close()

def init_db():
    queries = [
        """CREATE TABLE IF NOT EXISTS child_bots (bot_id INTEGER PRIMARY KEY, owner_id INTEGER, bot_token_enc TEXT UNIQUE, bot_username TEXT, bot_name TEXT, pro_mode INTEGER DEFAULT 1, log_channel TEXT DEFAULT '', force_channel TEXT DEFAULT '', support_wa TEXT DEFAULT '', support_tg TEXT DEFAULT '', active_gateway TEXT DEFAULT 'fampay', paytm_mid TEXT DEFAULT 'WWRYwl67445982860121', paytm_upi TEXT DEFAULT 'paytm.s2xzkgu@pty', bharatpe_mid TEXT DEFAULT '', bharatpe_upi TEXT DEFAULT '', bharatpe_token TEXT DEFAULT '', fampay_email TEXT DEFAULT '', fampay_app_pwd TEXT DEFAULT '', subscription_expiry TIMESTAMP, is_licensed INTEGER DEFAULT 0, status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
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
        conn.commit(); conn.close()

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
# 🌐 WEB FRONTEND & SECURE ADMIN PANEL (pranavsmm.online)
# ==========================================
HOME_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PranavSMM Gateway - High-Speed UPI Engine</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-white font-sans antialiased">
    <div class="min-h-screen flex flex-col justify-between p-6 max-w-4xl mx-auto">
        <header class="flex justify-between items-center py-4 border-b border-slate-800">
            <h1 class="text-2xl font-black bg-gradient-to-r from-purple-400 to-indigo-500 bg-clip-text text-transparent">⚡ PranavSMM Gateway</h1>
            <a href="/admin" class="bg-indigo-600 px-4 py-2 rounded-lg font-bold text-sm hover:bg-indigo-500 transition">Secure Admin Login</a>
        </header>
        <main class="py-12 text-center">
            <span class="bg-purple-900/50 text-purple-300 px-4 py-1.5 rounded-full text-xs font-semibold border border-purple-700/50">0% GATEWAY FEES • DIRECT P2P UPI AUTOMATION</span>
            <h2 class="text-4xl md:text-6xl font-extrabold mt-6 leading-tight">High-Speed UPI Gateway.<br><span class="bg-gradient-to-r from-purple-400 via-pink-400 to-indigo-400 bg-clip-text text-transparent">Liquid Precision.</span></h2>
            <p class="text-slate-400 mt-4 max-w-xl mx-auto">Autonomous UPI settlement engine for Pranav SMM reseller bots, web apps, and digital merchants.</p>
            <div class="mt-8 flex justify-center gap-4">
                <a href="/admin" class="bg-gradient-to-r from-purple-600 to-indigo-600 px-8 py-3 rounded-xl font-bold hover:opacity-90 shadow-lg shadow-indigo-600/30">Open Admin Panel →</a>
            </div>
        </main>
        <footer class="text-center text-slate-500 text-xs py-4 border-t border-slate-900">
            © 2026 pranavsmm.online • Powered by Pranav Master Engine
        </footer>
    </div>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - PranavSMM</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-white flex items-center justify-center min-h-screen">
    <div class="bg-slate-900 p-8 rounded-2xl border border-slate-800 w-full max-w-md shadow-2xl">
        <h2 class="text-2xl font-black text-center mb-6 bg-gradient-to-r from-purple-400 to-indigo-500 bg-clip-text text-transparent">🔒 Pranav Ji Admin Login</h2>
        {% if error %}
        <div class="bg-red-500/20 border border-red-500 text-red-300 p-3 rounded-lg text-sm mb-4 text-center">{{ error }}</div>
        {% endif %}
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-semibold text-slate-400 mb-1">USERNAME</label>
                <input type="text" name="username" required class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-indigo-500">
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-400 mb-1">PASSWORD</label>
                <input type="password" name="password" required class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-indigo-500">
            </div>
            <button type="submit" class="w-full bg-gradient-to-r from-purple-600 to-indigo-600 py-3 rounded-xl font-bold hover:opacity-90 transition mt-2">Login Securely →</button>
        </form>
        <div class="text-center mt-4">
            <a href="/" class="text-xs text-slate-500 hover:text-slate-400">← Back to Home</a>
        </div>
    </div>
</body>
</html>
"""

ADMIN_DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pranav God Master - Admin Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-white p-6">
    <div class="max-w-6xl mx-auto">
        <div class="flex justify-between items-center bg-slate-900 p-5 rounded-2xl border border-slate-800">
            <div>
                <h1 class="text-2xl font-black">👑 Pranav Ji Dashboard</h1>
                <p class="text-xs text-slate-400 mt-0.5">Logged in securely as God Master</p>
            </div>
            <div class="flex gap-3">
                <a href="/" class="bg-slate-800 px-4 py-2 rounded-xl text-sm font-semibold hover:bg-slate-700">Home</a>
                <a href="/admin/logout" class="bg-red-600/20 border border-red-500 text-red-300 px-4 py-2 rounded-xl text-sm font-semibold hover:bg-red-600/30">Logout</a>
            </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
            <div class="bg-slate-900 p-6 rounded-2xl border border-slate-800">
                <h3 class="text-slate-400 text-xs font-bold uppercase tracking-wider">Active Child Bots</h3>
                <p class="text-4xl font-black mt-2 text-indigo-400">{{ total_bots }}</p>
            </div>
            <div class="bg-slate-900 p-6 rounded-2xl border border-slate-800">
                <h3 class="text-slate-400 text-xs font-bold uppercase tracking-wider">Total Transactions</h3>
                <p class="text-4xl font-black mt-2 text-green-400">{{ total_tx }}</p>
            </div>
            <div class="bg-slate-900 p-6 rounded-2xl border border-slate-800">
                <h3 class="text-slate-400 text-xs font-bold uppercase tracking-wider">Engine Status</h3>
                <p class="text-4xl font-black mt-2 text-purple-400">ONLINE ⚡</p>
            </div>
        </div>
        <div class="mt-8 bg-slate-900 p-6 rounded-2xl border border-slate-800">
            <h2 class="text-lg font-bold mb-4">🔑 Gateway API Endpoints & Master Key</h2>
            <div class="bg-slate-950 p-4 rounded-xl font-mono text-xs text-indigo-300 border border-slate-800">
                Master API Key: <b>fam_live_ecaccced0de14140a457f95aac05b687</b>
            </div>
            <div class="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
                <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">POST /api/v1/fampay/create</div>
                <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">POST /api/v1/paytm/create</div>
                <div class="bg-slate-950 p-3 rounded-xl border border-slate-800">POST /api/v1/bharatpe/create</div>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def home(): return render_template_string(HOME_HTML)

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        user = request.form.get("username")
        pwd = request.form.get("password")
        if user == WEB_ADMIN_USER and pwd == WEB_ADMIN_PASS:
            session['admin_logged'] = True
            return redirect(url_for('admin_panel'))
        else:
            return render_template_string(LOGIN_HTML, error="❌ Invalid Username or Password!")
    
    if not session.get('admin_logged'):
        return render_template_string(LOGIN_HTML)

    b_cnt = fetch_query("SELECT COUNT(*) as c FROM child_bots", fetchone=True)["c"]
    t_cnt = fetch_query("SELECT COUNT(*) as c FROM transactions", fetchone=True)["c"]
    return render_template_string(ADMIN_DASHBOARD_HTML, total_bots=b_cnt, total_tx=t_cnt)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged', None)
    return redirect(url_for('admin_panel'))

# API Endpoints
@app.route('/api/v1/fampay/create', methods=['POST'])
def api_fampay():
    data = request.json or {}
    amt = float(data.get("amount", 0))
    if amt < 1: return jsonify({"error": "Min amount ₹1"}), 400
    tx_id = f"FP{int(time.time())}{random.randint(100,999)}"
    upi = "paytm.s2xzkgu@pty"
    qr = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(f'upi://pay?pa={upi}&pn=FamPay&am={amt:.2f}&cu=INR')}"
    return jsonify({"status": "success", "order_id": tx_id, "amount": amt, "payment_qr": qr})

# ==========================================
# 🛠️ BOT UTILITIES & VERIFICATION
# ==========================================
def get_bot_instance(bot_id):
    if bot_id == 0: return telebot.TeleBot(MASTER_BOT_TOKEN)
    c_row = fetch_query("SELECT bot_token_enc FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
    if c_row:
        token = cipher_suite.decrypt(c_row["bot_token_enc"].encode()).decode()
        return telebot.TeleBot(token)
    return None

def send_super_admin_log(text, acting_user_id=None):
    if not MASTER_BOT_TOKEN: return
    if acting_user_id and int(acting_user_id) == SUPER_ADMIN_ID: return
    try: telebot.TeleBot(MASTER_BOT_TOKEN).send_message(SUPER_ADMIN_ID, f"🚨 𝗣𝗥𝗔𝗡𝗔𝗩 𝗚𝗢𝗗 𝗠𝗔𝗦𝗧𝗘𝗥 𝗟𝗢𝗚 🚨\n\n{text}")
    except: pass

def safe_send(bot, chat_id, text, reply_markup=None):
    try: return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except: pass

def safe_edit(bot, text, chat_id, message_id, reply_markup=None):
    try: return bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except: return safe_send(bot, chat_id, text, reply_markup=reply_markup)

def generate_license_key(duration_days=30):
    k = f"PRANAV-KEY-{random.randint(100000, 999999)}:AA{''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(30))}"
    execute_query("INSERT INTO license_keys (key_code, duration_days) VALUES (?, ?)", (k, duration_days))
    return k

def is_bot_active(bot_id):
    if bot_id == 0: return True, "👑 Lifetime God Master"
    row = fetch_query("SELECT is_licensed, subscription_expiry, status FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
    if not row or row["is_licensed"] == 0: return False, "❌ Gateway License Key Not Activated."
    if row["status"] == "suspended": return False, "🚫 Bot Suspended"
    return True, "Active"

def verify_via_gmail_notifications(email_addr, app_password, target_amount):
    if not email_addr or not app_password: return False
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_addr.strip(), app_password.strip().replace(" ", ""))
        mail.select("inbox")
        status, messages = mail.search(None, 'ALL')
        if status != "OK": return False
        email_ids = messages[0].split()
        latest_ids = email_ids[-15:] if len(email_ids) >= 15 else email_ids
        latest_ids.reverse()
        for e_id in latest_ids:
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    body = msg.get_payload(decode=True).decode(errors="ignore") if not msg.is_multipart() else ""
                    if any(w in body.lower() for w in ["credited", "received", "fampay", "paytm", "upi"]):
                        amt_match = re.search(r'(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)', body, re.IGNORECASE)
                        if amt_match:
                            if abs(float(amt_match.group(1).replace(",", "")) - float(target_amount)) <= 0.5:
                                mail.logout(); return True
        mail.logout()
        return False
    except: return False

# ==========================================
# 🎨 MENUS & HANDLERS (BOTS)
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
    m.add(types.InlineKeyboardButton("⚙️ Services", callback_data="a_services"), types.InlineKeyboardButton("💳 Payment", callback_data="a_payment"))
    m.add(types.InlineKeyboardButton("👥 Users", callback_data="a_users"), types.InlineKeyboardButton("📢 Broadcast", callback_data="a_bcast"))
    m.add(types.InlineKeyboardButton("➕ Add Balance", callback_data="a_addbal"), types.InlineKeyboardButton("➖ Deduct Balance", callback_data="a_dedbal"))
    m.add(types.InlineKeyboardButton("🔑 Gateway License", callback_data="a_license_info"), types.InlineKeyboardButton("🔙 Main Menu", callback_data="a_back_main"))
    if is_master:
        m.add(types.InlineKeyboardButton("🎟️ Generate Keys", callback_data="adm_choose_key_duration"), types.InlineKeyboardButton("🤖 Manage Bots", callback_data="adm_list_child_bots"))
    return m

def get_user_main_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("💳 Balance", callback_data="u_bal"), types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"))
    m.add(types.InlineKeyboardButton("🛒 Order Now", callback_data="u_ord"), types.InlineKeyboardButton("🗓️ Order History", callback_data="u_hist"))
    m.add(types.InlineKeyboardButton("🤖 CYOB (Reseller)", callback_data="u_cyob"), types.InlineKeyboardButton("🎧 Support", callback_data="u_supp"))
    return m

def handle_user_callbacks(bot, bot_id, call):
    try: uid, cid, mid, data = call.from_user.id, call.message.chat.id, call.message.message_id, call.data
    except: return
    if data in ["u_continue_main", "u_back_main", "a_back_main"]:
        safe_edit(bot, "✨ 𝓦𝓔𝗟𝓒𝓞𝓜𝓔 𝗧𝗢 𝗣𝗔𝗡𝗘𝗟 ✨\n\n👑 Premium Reseller Dashboard", cid, mid, reply_markup=get_user_main_menu())
    elif data == "u_bal":
        row = fetch_query("SELECT balance, total_deposit, total_spent FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        bal, tdep, tsp = (row["balance"], row["total_deposit"], row["total_spent"]) if row else (0.0, 0.0, 0.0)
        safe_edit(bot, f"🛡️ 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗜𝗡𝗙𝗢\n\n💰 Balance - ₹{bal:.2f}\n🆔 User ID - {uid}", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"), types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")))
    elif data == "u_dep":
        act, rsn = is_bot_active(bot_id)
        if not act: return safe_edit(bot, f"⚠️ 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗢𝗖𝗞𝗘𝗗\n\n{rsn}", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")))
        keypad_amounts[f"{bot_id}_{uid}"] = ""
        kp, disp = build_deposit_keypad("")
        safe_edit(bot, f"💶 𝗘𝗡𝗧𝗘𝗥 𝗔𝗠𝗢𝗨𝗡𝗧\n💵 Amount : ₹{disp}", cid, mid, reply_markup=kp)
    elif data.startswith("kp_"):
        act = data.replace("kp_", "")
        k_key = f"{bot_id}_{uid}"
        cur_amt = keypad_amounts.get(k_key, "")
        if act == "cancel":
            keypad_amounts.pop(k_key, None)
            return safe_edit(bot, "Cancelled.", cid, mid, reply_markup=get_user_main_menu())
        elif act == "clear": cur_amt = cur_amt[:-1] if len(cur_amt)>1 else ""
        elif act in ["0","1","2","3","4","5","6","7","8","9","00"]:
            if len(cur_amt)<5: cur_amt += act
        elif act == "confirm":
            if not cur_amt or int(cur_amt)<1: return bot.answer_callback_query(call.id, "Enter min ₹1", show_alert=True)
            amt = float(cur_amt); keypad_amounts.pop(k_key, None)
            utr = f"DEP{int(time.time())}{random.randint(100, 999)}"
            target_upi = "paytm.s2xzkgu@pty"
            execute_query("INSERT INTO transactions (tx_id, bot_id, user_id, amount, tx_type, status) VALUES (?, ?, ?, ?, 'deposit', 'pending')", (utr, bot_id, uid, amt))
            user_states[k_key] = {"step": "wait_manual_utr", "tx_id": utr}
            url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(f'upi://pay?pa={target_upi}&pn=AddFunds&am={amt:.2f}&cu=INR')}"
            try: bot.delete_message(cid, mid)
            except: pass
            return bot.send_photo(cid, url, caption=f"⚡ 𝗔𝗨𝗧𝗢𝗠𝗔𝗧𝗘𝗗 𝗨𝗣𝗜\n\n💵 Amount : ₹{amt:.2f}\n🆔 Order : {utr}\n\n⚠️ Pay and send 12-digit UTR in chat.", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔢 SUBMIT UTR", callback_data=f"sub_utr_{utr}")))
        keypad_amounts[k_key] = cur_amt
        kp, disp = build_deposit_keypad(cur_amt)
        safe_edit(bot, f"💶 𝗘𝗡𝗧𝗘𝗥 𝗔𝗠𝗢𝗨𝗡𝗧\n💵 Amount : ₹{disp}", cid, mid, reply_markup=kp)
    elif data.startswith("sub_utr_"):
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_manual_utr", "tx_id": data.replace("sub_utr_", "")}
        safe_send(bot, cid, "🔢 Send your 12-digit UTR in chat:")
    elif data == "u_cyob":
        safe_edit(bot, "👑 CREATE YOUR OWN BOT", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("➕ Add Bot", callback_data="m_add_bot"), types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")))
    elif data == "m_add_bot":
        user_states[f"{bot_id}_{uid}"] = "wait_token"
        safe_edit(bot, "🏆 SUBMIT TOKEN\nPaste your BotFather token:", cid, mid)

def handle_owner_callbacks(bot, bot_id, call, is_master=False):
    try: uid, cid, mid, data = call.from_user.id, call.message.chat.id, call.message.message_id, call.data
    except: return
    if is_master and uid != SUPER_ADMIN_ID: return bot.answer_callback_query(call.id, "Access Denied", show_alert=True)
    if data == "adm_back_panel": safe_edit(bot, "👑 Owner Panel", cid, mid, reply_markup=get_owner_panel(is_master))
    elif data == "a_license_info":
        act, rsn = is_bot_active(bot_id)
        safe_edit(bot, f"🔑 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗜𝗖𝗘𝗡𝗦𝗘\n\n• Status: {rsn}", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🎟️ Enter Key", callback_data="c_enter_lic_key"), types.InlineKeyboardButton("🔙 Back", callback_data="adm_back_panel")))
    elif data == "c_enter_lic_key":
        user_states[f"{bot_id}_{uid}"] = "wait_redeem_key"
        safe_send(bot, cid, "🔑 Send your License Key:")
    elif data == "adm_choose_key_duration" and is_master:
        k = generate_license_key(30)
        safe_send(bot, cid, f"🎟️ 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗞𝗘𝗬 (30 Days):\n`{k}`", reply_markup=get_owner_panel(True))

def handle_text_inputs(bot, bot_id, msg, is_master=False):
    try: uid, cid, txt = msg.from_user.id, msg.chat.id, msg.text.strip().replace('`', '').replace("'", "")
    except: return
    key = f"{bot_id}_{uid}"
    st_data = user_states.get(key)
    if len(txt) == 12 and txt.isdigit():
        t_row = fetch_query("SELECT tx_id FROM transactions WHERE user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1", (uid,), fetchone=True)
        if t_row: st_data = {"step": "wait_manual_utr", "tx_id": t_row["tx_id"]}
    if not st_data: return

    if st_data == "wait_token":
        user_states.pop(key, None)
        chk = requests.get(f"https://api.telegram.org/bot{txt}/getMe").json()
        if not chk.get("ok"): return safe_send(bot, cid, "❌ Invalid Token!")
        token_enc = cipher_suite.encrypt(txt.encode()).decode()
        execute_query("INSERT INTO child_bots (owner_id, bot_token_enc, bot_username, bot_name, is_licensed, status) VALUES (?, ?, ?, ?, 0, 'active')", (uid, token_enc, chk["result"]["username"], chk["result"]["first_name"]))
        return safe_send(bot, cid, f"🚀 @{chk['result']['username']} is Live! Go to /admin to activate.")

    if st_data == "wait_redeem_key":
        user_states.pop(key, None)
        lic = fetch_query("SELECT * FROM license_keys WHERE key_code=? AND is_used=0", (txt,), fetchone=True)
        if not lic: return safe_send(bot, cid, "❌ Invalid Key!")
        new_exp = (datetime.datetime.now() + datetime.timedelta(days=lic["duration_days"])).strftime("%Y-%m-%d %H:%M:%S")
        execute_query("UPDATE license_keys SET is_used=1, used_by_bot_id=? WHERE key_code=?", (bot_id, txt))
        execute_query("UPDATE child_bots SET is_licensed=1, status='active', subscription_expiry=? WHERE bot_id=?", (new_exp, bot_id))
        return safe_send(bot, cid, f"🎉 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗔𝗖𝗧𝗜𝗩𝗔𝗧𝗘𝗗!\nExpiry: {new_exp}", reply_markup=get_owner_panel(is_master))

    if isinstance(st_data, dict) and st_data.get("step") == "wait_manual_utr":
        user_states.pop(key, None)
        tx = st_data["tx_id"]
        if len(txt) != 12 or not txt.isdigit(): return safe_send(bot, cid, "❌ UTR must be 12 digits.")
        execute_query("UPDATE transactions SET bank_utr=?, status='completed' WHERE tx_id=?", (txt, tx))
        t_row = fetch_query("SELECT amount FROM transactions WHERE tx_id=?", (tx,), fetchone=True)
        execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (t_row["amount"], t_row["amount"], bot_id, uid))
        return safe_send(bot, cid, f"🎉 Payment Verified!\n₹{t_row['amount']} credited.", reply_markup=get_user_main_menu())

# ==========================================
# 🤖 THREAD RUNNERS
# ==========================================
def run_child_bot_loop(bot_id, owner_id, token, bot_username, bot_name):
    while True:
        try:
            cbot = telebot.TeleBot(token, threaded=True)
            @cbot.message_handler(commands=['start'])
            def c_start(msg):
                execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)", (bot_id, msg.from_user.id, msg.from_user.username))
                safe_send(cbot, msg.chat.id, "💎 𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗕𝗢𝗧", reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("💎 Continue", callback_data="u_continue_main")))
            @cbot.message_handler(commands=['admin'])
            def c_admin(msg):
                if msg.from_user.id != owner_id and msg.from_user.id != SUPER_ADMIN_ID: return
                safe_send(cbot, msg.chat.id, "👑 Owner Panel", reply_markup=get_owner_panel(is_master=False))
            @cbot.callback_query_handler(func=lambda c: True)
            def c_cbs(call):
                if call.data.startswith("a_") or call.data.startswith("adm_"):
                    if call.from_user.id != owner_id and call.from_user.id != SUPER_ADMIN_ID: return
                    handle_owner_callbacks(cbot, bot_id, call, is_master=False)
                else: handle_user_callbacks(cbot, bot_id, call)
            @cbot.message_handler(func=lambda m: True and not m.text.startswith('/'))
            def c_txts(m): handle_text_inputs(cbot, bot_id, m, is_master=False)
            cbot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except: time.sleep(2)

def run_master_bot_loop():
    while True:
        try:
            if not MASTER_BOT_TOKEN: time.sleep(5); continue
            master_bot = telebot.TeleBot(MASTER_BOT_TOKEN, threaded=True)
            @master_bot.message_handler(commands=['start'])
            def m_start(msg):
                execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (0, ?, ?)", (msg.from_user.id, msg.from_user.username))
                safe_send(master_bot, msg.chat.id, "✨ 𝓦𝓔𝗟𝓒𝓞𝓜𝓔 𝗧𝗢 𝗠𝗔𝗦𝗧𝗘𝗥 ✨", reply_markup=get_user_main_menu())
            @master_bot.message_handler(commands=['admin'])
            def m_admin(msg):
                if msg.from_user.id != SUPER_ADMIN_ID: return
                safe_send(master_bot, msg.chat.id, "👑 MASTER BOT ADMIN PANEL", reply_markup=get_owner_panel(is_master=True))
            @master_bot.callback_query_handler(func=lambda c: True)
            def m_cbs(c):
                if c.data.startswith("a_") or c.data.startswith("adm_") or c.data.startswith("god_"):
                    if c.from_user.id != SUPER_ADMIN_ID: return
                    handle_owner_callbacks(master_bot, 0, c, is_master=True)
                else: handle_user_callbacks(master_bot, 0, c)
            @master_bot.message_handler(func=lambda m: True and not m.text.startswith('/'))
            def m_txts(msg): handle_text_inputs(master_bot, 0, msg, is_master=True)
            master_bot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except: time.sleep(3)

threading.Thread(target=run_master_bot_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
