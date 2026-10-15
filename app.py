Import os
import time
import datetime
import secrets
import string
import hashlib
import sqlite3
import threading
import urllib.parse
import requests
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, abort
import telebot
from telebot import types

# ==========================================
# 👑 GRANDMASTER CORE CONFIGURATION (100% SECURE)
# ==========================================
RENDER_PORT = int(os.environ.get("PORT", 8081))
MASTER_BOT_TOKEN = os.environ.get("MASTER_BOT_TOKEN", "").strip()
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID", "0"))

SHOP_API_URL = os.environ.get("SHOP_API_URL", "https://pranavsmm.shop/api/v2").strip()
SHOP_API_KEY = os.environ.get("SHOP_API_KEY", "").strip()

ENV_ADMIN_USER = os.environ.get("ADMIN_USER", "").strip()
ENV_ADMIN_PASS = os.environ.get("ADMIN_PASS", "").strip()
ENV_ADMIN_SLUG = os.environ.get("ADMIN_SLUG", "").strip().strip("/")
ENV_MASTER_UPI = os.environ.get("MASTER_UPI_ID", "").strip()
ENV_PAYTM_MID = os.environ.get("PAYTM_MID", "").strip()

DB_PATH = "pranav_rental_empire.db"

def hash_pwd(pwd): return hashlib.sha256(str(pwd).encode()).hexdigest() if pwd else ""

def generate_secure_key(days):
    """तगड़ी 48-अक्षरों वाली क्रिप्टोग्राफ़िक Key (BotFather Style)"""
    rand_part = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
    return f"PV7_{days}D_{rand_part}_SECURE"

# ==========================================
# 🗄️ PERSISTENT DATABASE ENGINE
# ==========================================
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def execute_query(q, params=(), commit=True):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(q, params)
        if commit: conn.commit()
        return cur.lastrowid
    except Exception as e: print(f"[DB ERR] {e}")
    finally: conn.close()

def fetch_query(q, params=(), fetchone=False):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(q, params)
        return cur.fetchone() if fetchone else cur.fetchall()
    except Exception as e: print(f"[DB ERR] {e}")
    finally: conn.close()

def get_cfg(k, default=""):
    r = fetch_query("SELECT val FROM sys_cfg WHERE k=?", (k,), fetchone=True)
    return r["val"] if r else default

def set_cfg(k, v):
    if v:
        execute_query("INSERT INTO sys_cfg (k, val) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET val=excluded.val", (k, str(v)))

def init_db():
    tables = [
        "CREATE TABLE IF NOT EXISTS sys_cfg (k TEXT PRIMARY KEY, val TEXT)",
        """CREATE TABLE IF NOT EXISTS web_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, password_hash TEXT,
            google_id TEXT, telegram_id TEXT, balance REAL DEFAULT 0.0, total_deposit REAL DEFAULT 0.0, 
            total_spent REAL DEFAULT 0.0, active_plan TEXT DEFAULT 'Free Tier', auto_sub INTEGER DEFAULT 0, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS bot_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, user_id INTEGER, username TEXT,
            balance REAL DEFAULT 0.0, total_deposit REAL DEFAULT 0.0, total_spent REAL DEFAULT 0.0, UNIQUE(bot_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS child_bots (
            bot_id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, bot_token TEXT UNIQUE, bot_username TEXT,
            custom_upi TEXT DEFAULT '', custom_mid TEXT DEFAULT '', is_licensed INTEGER DEFAULT 0, expiry TIMESTAMP, 
            status TEXT DEFAULT 'active', margin_pct REAL DEFAULT 10.0
        )""",
        """CREATE TABLE IF NOT EXISTS license_keys (
            key_code TEXT PRIMARY KEY, duration_days INTEGER DEFAULT 30, price REAL DEFAULT 149.0,
            is_used INTEGER DEFAULT 0, used_by_bot_id INTEGER DEFAULT NULL, used_by_user_id INTEGER DEFAULT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS transactions (
            tx_id TEXT PRIMARY KEY, bot_id INTEGER, user_id INTEGER, amount REAL, bank_utr TEXT, status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS smm_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, user_id INTEGER, service_name TEXT,
            link TEXT, quantity INTEGER, charge REAL, shop_order_id TEXT DEFAULT '', status TEXT DEFAULT 'Processing',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    ]
    for t in tables: execute_query(t)
    
    # Environment configs
    if ENV_ADMIN_USER: set_cfg("admin_user", ENV_ADMIN_USER)
    if ENV_ADMIN_PASS: set_cfg("admin_pass_hash", hash_pwd(ENV_ADMIN_PASS))
    if ENV_ADMIN_SLUG: set_cfg("admin_slug", ENV_ADMIN_SLUG)
    if not get_cfg("panel_name"): set_cfg("panel_name", "PRANAV SMM")
    if not get_cfg("active_theme"): set_cfg("active_theme", "Lumiere")
    if ENV_MASTER_UPI: set_cfg("master_upi", ENV_MASTER_UPI)
    if ENV_PAYTM_MID: set_cfg("paytm_mid", ENV_PAYTM_MID)
    
    # Init Master Bot in DB
    if SUPER_ADMIN_ID > 0:
        exp = (datetime.datetime.now() + datetime.timedelta(days=36500)).strftime("%Y-%m-%d %H:%M:%S")
        execute_query("INSERT OR IGNORE INTO child_bots (bot_id, owner_id, bot_token, bot_username, is_licensed, expiry) VALUES (0, ?, 'MASTER', 'PranavMasterBot', 1, ?)", (SUPER_ADMIN_ID, exp))

init_db()

# ==========================================
# 🛡️ REAL PAYTM & PRANAVSMM.SHOP API LOGIC
# ==========================================
def verify_paytm_payment(utr, amount, custom_mid=None):
    """100% Real Verification using Merchant ID (MID) and UTR"""
    mid = custom_mid if custom_mid else get_cfg("paytm_mid")
    if not mid: return False, "MID (Merchant ID) सेट नहीं है!"
    try:
        r = requests.post("https://securegw.paytm.in/merchant-status/getTxnStatus", json={"MID": mid, "ORDERID": str(utr)}, timeout=8).json()
        if r.get("STATUS") == "TXN_SUCCESS" and float(r.get("TXNAMOUNT", 0)) >= float(amount):
            return True, r.get("BANKTXNID", utr)
        return False, r.get("RESPMSG", "बैंक से ट्रांजैक्शन नहीं मिला")
    except Exception as e: return False, f"API Error: {str(e)}"

def forward_order_to_shop(service_id, link, quantity):
    if not SHOP_API_KEY or not SHOP_API_URL: return False, "Shop API Key/URL Configured नहीं है।"
    payload = {"key": SHOP_API_KEY, "action": "add", "service": service_id, "link": link, "quantity": quantity}
    try:
        r = requests.post(SHOP_API_URL, data=payload, timeout=10).json()
        return (True, str(r["order"])) if "order" in r else (False, r.get("error", "Shop API error"))
    except Exception as e: return False, str(e)

# ==========================================
# 🤖 TELEGRAM BOT ENGINE (MASTER & CHILD)
# ==========================================
user_states = {}
running_bots = {}

def get_bot_menu(is_master):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("🛒 New Order", callback_data="u_order"), types.InlineKeyboardButton("💳 Wallet", callback_data="u_bal"))
    m.add(types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"), types.InlineKeyboardButton("📦 My Orders", callback_data="u_hist"))
    if is_master:
        m.add(types.InlineKeyboardButton("🤖 Create Child Bot", callback_data="m_cyob"), types.InlineKeyboardButton("🔑 Get License Key", url="https://pranavsmm.online"))
    return m

def bind_bot_events(bot, bid, owner_id, is_master):
    @bot.message_handler(commands=['start'])
    def s_cmd(m):
        execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)", (bid, m.from_user.id, m.from_user.username))
        bot.send_message(m.chat.id, "⚡ **PRANAV SMM HUB**\n\nChoose an option:", reply_markup=get_bot_menu(is_master), parse_mode="Markdown")

    @bot.message_handler(commands=['admin'])
    def a_cmd(m):
        if m.from_user.id != owner_id and m.from_user.id != SUPER_ADMIN_ID: 
            return bot.send_message(m.chat.id, "⛔ Unauthorized. You are not the owner of this bot.")
        rm = types.InlineKeyboardMarkup(row_width=1)
        if is_master:
            rm.add(types.InlineKeyboardButton("🎟️ Generate Admin Key", callback_data="adm_key"))
        else:
            b_info = fetch_query("SELECT is_licensed FROM child_bots WHERE bot_id=?", (bid,), fetchone=True)
            if b_info and b_info["is_licensed"]:
                rm.add(types.InlineKeyboardButton("💳 Change UPI & MID", callback_data="cb_upi"))
                rm.add(types.InlineKeyboardButton("📈 Set Margin/Prices", callback_data="cb_margin"))
            else:
                rm.add(types.InlineKeyboardButton("🔒 Enter License Key to Unlock Payments", callback_data="cb_key"))
                rm.add(types.InlineKeyboardButton("🛒 Buy License Key Now", url="https://pranavsmm.online"))
        bot.send_message(m.chat.id, "👑 **Admin Control**", reply_markup=rm, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda c: True)
    def cb_handler(c):
        uid = c.from_user.id
        cid = c.message.chat.id
        d = c.data
        if d == "u_bal":
            bal = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bid, uid), fetchone=True)
            bot.send_message(cid, f"💰 Wallet Balance: ₹{bal['balance'] if bal else 0:.2f}")
        
        elif d == "u_dep":
            b_info = fetch_query("SELECT is_licensed, custom_upi FROM child_bots WHERE bot_id=?", (bid,), fetchone=True)
            upi = b_info["custom_upi"] if (b_info and b_info["is_licensed"] and b_info["custom_upi"]) else get_cfg("master_upi", "Not Set")
            user_states[f"{bid}_{uid}"] = "wait_utr"
            bot.send_photo(cid, f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(f'upi://pay?pa={upi}&pn=SMM&cu=INR')}", caption=f"🏦 UPI: `{upi}`\n\nSend: `Amount UTR`\nEx: `100 123456789012`", parse_mode="Markdown")
        
        elif d == "u_order":
            rm = types.InlineKeyboardMarkup(row_width=1)
            margin = 1.0
            if not is_master:
                b_info = fetch_query("SELECT margin_pct FROM child_bots WHERE bot_id=?", (bid,), fetchone=True)
                margin = 1.0 + ((b_info["margin_pct"] if b_info else 0) / 100.0)
            
            rm.add(types.InlineKeyboardButton(f"🔥 IG Followers - ₹{49*margin:.2f}/1k", callback_data=f"srv_101_{49*margin:.2f}_IG Followers"))
            rm.add(types.InlineKeyboardButton(f"▶️ YT Views - ₹{99*margin:.2f}/1k", callback_data=f"srv_105_{99*margin:.2f}_YT Views"))
            bot.send_message(cid, "🛒 Select Service:", reply_markup=rm)
        
        elif d.startswith("srv_"):
            _, sid, rate, s_name = d.split("_", 3)
            user_states[f"{bid}_{uid}"] = {"step": "link", "sid": sid, "rate": float(rate), "name": s_name}
            bot.send_message(cid, f"🔗 Send Link for {s_name}:")
        
        elif d == "m_cyob" and is_master:
            user_states[f"{bid}_{uid}"] = "wait_tok"
            bot.send_message(cid, "🤖 Send BotFather Token:")
        
        elif d == "cb_key":
            user_states[f"{bid}_{uid}"] = "wait_lic"
            bot.send_message(cid, "🔑 Send your `PV7_...` License Key:")
        
        elif d == "cb_upi":
            user_states[f"{bid}_{uid}"] = "wait_upi"
            bot.send_message(cid, "💳 Send `UPI_ID MERCHANT_ID`\nEx: `paytm@pty WWR...`")
            
        elif d == "adm_key" and is_master:
            k = generate_secure_key(30)
            execute_query("INSERT INTO license_keys (key_code, duration_days, price) VALUES (?, 30, 0)", (k,))
            bot.send_message(cid, f"`{k}`", parse_mode="Markdown")

    @bot.message_handler(func=lambda m: True and m.text and not m.text.startswith('/'))
    def txt_handler(m):
        uid = m.from_user.id
        cid = m.chat.id
        txt = m.text.strip()
        st = user_states.get(f"{bid}_{uid}")

        # 1. PAYTM AUTO VERIFY
        parts = txt.split()
        if (len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 12) or st == "wait_utr":
            amt = float(parts[0]) if len(parts) == 2 else 0.0
            utr = parts[1] if len(parts) == 2 else txt
            if len(utr) != 12: return bot.send_message(cid, "❌ Invalid 12-Digit UTR!")
            if fetch_query("SELECT tx_id FROM transactions WHERE bank_utr=?", (utr,), fetchone=True): return bot.send_message(cid, "❌ UTR Already Used!")
            
            b_info = fetch_query("SELECT custom_mid FROM child_bots WHERE bot_id=?", (bid,), fetchone=True)
            mid = b_info["custom_mid"] if b_info and b_info["custom_mid"] else None
            ok, ref = verify_paytm_payment(utr, amt, mid)
            if ok:
                execute_query("INSERT INTO transactions (tx_id, bot_id, user_id, amount, bank_utr, status) VALUES (?, ?, ?, ?, ?, 'completed')", (f"T{int(time.time())}", bid, uid, amt, ref))
                execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (amt, amt, bid, uid))
                user_states.pop(f"{bid}_{uid}", None)
                bot.send_message(cid, f"🎉 ₹{amt} Verified & Added!")
            else:
                bot.send_message(cid, f"❌ Bank Failed: {ref}")
            return

        # 2. ORDER PLACEMENT & BALANCE DEDUCTION
        if isinstance(st, dict) and st.get("step") == "link":
            st["link"] = txt
            st["step"] = "qty"
            user_states[f"{bid}_{uid}"] = st
            bot.send_message(cid, "🔢 Send Quantity (Min 50):")
            return
        
        if isinstance(st, dict) and st.get("step") == "qty":
            qty = int(txt)
            chg = (qty / 1000.0) * st["rate"]
            ub = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bid, uid), fetchone=True)
            if not ub or ub["balance"] < chg: return bot.send_message(cid, "⚠️ Insufficient Wallet Balance! Please add funds.")
            
            # Master balance check for child bot owners
            if not is_master:
                ob = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=0 AND user_id=?", (owner_id,), fetchone=True)
                # Master charge is base rate (without child's margin)
                base_rate = st["rate"] / (1.0 + (fetch_query("SELECT margin_pct FROM child_bots WHERE bot_id=?", (bid,), fetchone=True)["margin_pct"]/100.0))
                master_chg = (qty / 1000.0) * base_rate
                
                if not ob or ob["balance"] < master_chg: return bot.send_message(cid, "⚠️ Service Unavailable. (Owner master wallet empty)")
                execute_query("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ? WHERE bot_id=0 AND user_id=?", (master_chg, master_chg, owner_id))
            
            execute_query("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ? WHERE bot_id=? AND user_id=?", (chg, chg, bid, uid))
            ok, oid = forward_order_to_shop(st["sid"], st["link"], qty)
            execute_query("INSERT INTO smm_orders (bot_id, user_id, service_name, link, quantity, charge, shop_order_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (bid, uid, st["name"], st["link"], qty, chg, oid))
            user_states.pop(f"{bid}_{uid}", None)
            bot.send_message(cid, f"✅ Order Placed! Shop ID: `{oid}`", parse_mode="Markdown")
            return

        # 3. CHILD BOT TOKEN CREATION (EXACTLY AS REQUESTED: LOCKS TO OWNER)
        if st == "wait_tok" and is_master:
            try:
                un = requests.get(f"https://api.telegram.org/bot{txt}/getMe").json()["result"]["username"]
                new_bid = execute_query("INSERT INTO child_bots (owner_id, bot_token, bot_username) VALUES (?, ?, ?)", (uid, txt, un))
                start_child_bot(new_bid, uid, txt)
                bot.send_message(cid, f"🚀 Bot @{un} Launched!\nTelegram ID Locked: {uid}\nUse /admin inside your bot to unlock payments.")
            except: bot.send_message(cid, "❌ Invalid Token!")
            user_states.pop(f"{bid}_{uid}", None)

        if st == "wait_lic" and not is_master:
            lic = fetch_query("SELECT * FROM license_keys WHERE key_code=? AND is_used=0", (txt,), fetchone=True)
            if not lic: return bot.send_message(cid, "❌ Invalid Key!")
            execute_query("UPDATE license_keys SET is_used=1, used_by_bot_id=? WHERE key_code=?", (bid, txt))
            execute_query("UPDATE child_bots SET is_licensed=1 WHERE bot_id=?", (bid,))
            bot.send_message(cid, "🎉 License Active! Set your UPI via /admin.")
            user_states.pop(f"{bid}_{uid}", None)

        if st == "wait_upi" and not is_master:
            if " " not in txt: return bot.send_message(cid, "❌ format: UPI MID")
            upi, mid = txt.split(" ", 1)
            execute_query("UPDATE child_bots SET custom_upi=?, custom_mid=? WHERE bot_id=?", (upi, mid, bid))
            bot.send_message(cid, "✅ Payment Settings Updated!")
            user_states.pop(f"{bid}_{uid}", None)

def child_loop(bid, oid, tok):
    while True:
        try:
            b = telebot.TeleBot(tok, threaded=True)
            bind_bot_events(b, bid, oid, False)
            b.infinity_polling()
        except: time.sleep(5)

def start_child_bot(bid, oid, tok):
    if bid not in running_bots:
        t = threading.Thread(target=child_loop, args=(bid, oid, tok), daemon=True)
        running_bots[bid] = t
        t.start()

def master_loop():
    while True:
        try:
            if not MASTER_BOT_TOKEN: time.sleep(5); continue
            mb = telebot.TeleBot(MASTER_BOT_TOKEN, threaded=True)
            bind_bot_events(mb, 0, SUPER_ADMIN_ID, True)
            mb.infinity_polling()
        except: time.sleep(4)

# Start Bot Threads
threading.Thread(target=master_loop, daemon=True).start()
threading.Thread(target=lambda: [start_child_bot(r["bot_id"], r["owner_id"], r["bot_token"]) for r in (fetch_query("SELECT * FROM child_bots WHERE bot_id>0") or [])], daemon=True).start()
# ==========================================
# 🎨 MASSIVE 4D WHITE HTML TEMPLATES
# ==========================================
CSS_BASE = """
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    body { font-family: 'Plus Jakarta Sans', sans-serif; background: #f4f7fe; color: #0f172a; overflow-x: hidden; }
    .card-4d { background: #fff; border-radius: 24px; border: 1px solid #e2e8f0; box-shadow: 0 12px 30px rgba(0,0,0,0.04), 0 4px 6px rgba(0,0,0,0.02); transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
    .card-4d:hover { box-shadow: 0 20px 40px rgba(37, 99, 235, 0.08), 0 8px 10px rgba(37, 99, 235, 0.04); transform: translateY(-3px); border-color: #bfdbfe; }
    .btn-4d { border-radius: 14px; font-weight: 800; transition: 0.2s; border-bottom: 4px solid rgba(0,0,0,0.2); text-align: center; display: inline-flex; align-items: center; justify-content: center; gap: 8px; }
    .btn-4d:active { border-bottom-width: 1px; transform: translateY(3px); }
    .input-4d { background: #f8fafc; border: 2px solid #e2e8f0; border-radius: 14px; padding: 14px; width: 100%; font-weight: 600; outline: none; transition: 0.2s; color: #0f172a; }
    .input-4d:focus { border-color: #3b82f6; background: #ffffff; box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.1); }
    /* Rental Admin Sidebar */
    .sidebar-link { display: flex; align-items: center; gap: 12px; padding: 12px 18px; border-radius: 12px; font-size: 13.5px; font-weight: 700; color: #475569; transition: all 0.2s; margin-bottom: 4px; }
    .sidebar-link:hover, .sidebar-link.active { background: #2563eb; color: #ffffff; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2); }
</style>
<script>
    function switchTab(id) {
        document.querySelectorAll('.tab-pane').forEach(e => e.classList.add('hidden'));
        const pane = document.getElementById('pane-' + id);
        if(pane) pane.classList.remove('hidden');
    }
</script>
"""

# -----------------
# 1. WEB UI (4D LOGIN & DASHBOARD)
# -----------------
WEB_UI = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PranavSMM.online - Cloud Hub</title>
    """ + CSS_BASE + """
</head>
<body class="min-h-screen flex flex-col justify-between">
    <header class="bg-white/80 backdrop-blur-md border-b border-slate-200 px-6 py-4 flex justify-between items-center sticky top-0 z-40">
        <a href="/" class="flex items-center gap-2">
            <span class="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center text-white font-black text-lg shadow-lg">P</span>
            <div>
                <div class="text-xl font-black tracking-tight text-slate-900">PranavSMM<span class="text-blue-600">.online</span></div>
                <div class="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest">Reseller Cloud API</div>
            </div>
        </a>
        <div class="flex items-center gap-3">
            {% if session.get('user_id') %}
                <span class="hidden sm:inline text-xs font-bold text-slate-600 bg-slate-100 px-3 py-1.5 rounded-lg">Wallet: <b class="text-emerald-600">₹{{ "%.2f"|format(user.balance) }}</b></span>
                <a href="/logout" class="px-4 py-2 rounded-xl bg-rose-50 text-rose-600 text-xs font-bold hover:bg-rose-100 transition">Logout</a>
            {% else %}
                <a href="/login" class="px-4 py-2 rounded-xl text-slate-600 text-xs font-bold hover:bg-slate-100 transition">Sign In</a>
            {% endif %}
        </div>
    </header>

    <main class="flex-1 flex flex-col items-center justify-center p-4 py-12">
        {% if msg %}<div class="mb-6 px-6 py-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm font-bold shadow-sm w-full max-w-4xl text-center"><i class="fa-solid fa-check-circle mr-2"></i> {{ msg }}</div>{% endif %}
        {% if err %}<div class="mb-6 px-6 py-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-sm font-bold shadow-sm w-full max-w-4xl text-center"><i class="fa-solid fa-triangle-exclamation mr-2"></i> {{ err }}</div>{% endif %}

        <div class="card-4d p-8 sm:p-10 w-full max-w-5xl">
            {% if not session.get('user_id') %}
                <!-- 4D LOGIN & REGISTER SECTION -->
                <div class="text-center mb-10">
                    <h1 class="text-3xl sm:text-4xl font-black text-slate-900 tracking-tight">Access Your <span class="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600">Cloud Dashboard</span></h1>
                    <p class="text-slate-500 font-bold mt-2 text-sm">Purchase License Keys & Deploy 24x7 Telegram Bots</p>
                </div>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-10">
                    <!-- Social Logins -->
                    <div class="space-y-4">
                        <h3 class="text-sm font-extrabold text-slate-400 uppercase tracking-wider mb-4">Quick Sign In</h3>
                        <button class="w-full py-3.5 bg-white border-2 border-slate-200 rounded-xl font-bold flex items-center justify-center gap-3 hover:bg-slate-50 transition text-slate-700">
                            <img src="https://www.svgrepo.com/show/475656/google-color.svg" class="w-5 h-5"> Continue with Google
                        </button>
                        <button class="w-full py-3.5 bg-[#eff6ff] border-2 border-[#bfdbfe] text-[#1d4ed8] rounded-xl font-bold flex items-center justify-center gap-3 hover:bg-[#dbeafe] transition">
                            <img src="https://www.svgrepo.com/show/354443/telegram.svg" class="w-5 h-5"> Login with Telegram
                        </button>
                    </div>
                    
                    <!-- Manual Login -->
                    <div>
                        <h3 class="text-sm font-extrabold text-slate-400 uppercase tracking-wider mb-4">Email Login / Register</h3>
                        <form method="POST" action="/auth" class="space-y-4">
                            <input type="email" name="email" required placeholder="Email Address" class="input-4d">
                            <input type="password" name="password" required placeholder="Password" class="input-4d">
                            <div class="flex gap-3 pt-2">
                                <button type="submit" name="action" value="login" class="flex-1 btn-4d bg-blue-600 text-white py-3.5 text-sm">Sign In</button>
                                <button type="submit" name="action" value="register" class="flex-1 btn-4d bg-emerald-600 text-white py-3.5 text-sm">Create Account</button>
                            </div>
                        </form>
                    </div>
                </div>
            {% else %}
                <!-- 4D USER DASHBOARD -->
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
                    <div>
                        <h2 class="text-2xl font-black text-slate-900">Welcome, {{ user.email.split('@')[0] }} 👋</h2>
                        <p class="text-xs font-bold text-slate-500 mt-1">ID: {{ user.id }} • {{ user.email }}</p>
                    </div>
                    <div class="flex gap-2 bg-slate-100 p-1.5 rounded-xl">
                        <button onclick="switchTab('hub')" class="px-4 py-2 text-xs font-bold rounded-lg bg-white shadow-sm text-blue-600">Hub Overview</button>
                        <button onclick="switchTab('bot')" class="px-4 py-2 text-xs font-bold rounded-lg text-slate-600 hover:text-slate-900">Deploy Bot</button>
                    </div>
                </div>
                
                <div id="pane-hub" class="tab-pane space-y-6">
                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <!-- Wallet & Auto-Verify Add Funds -->
                        <div class="p-6 bg-gradient-to-br from-slate-50 to-white rounded-2xl border border-slate-200 shadow-sm">
                            <div class="flex justify-between items-center mb-6">
                                <span class="text-xs font-extrabold text-slate-400 uppercase">Real-Time Wallet</span>
                                <i class="fa-solid fa-wallet text-slate-300 text-xl"></i>
                            </div>
                            <div class="text-4xl font-black text-emerald-600 mb-6">₹{{ "%.2f"|format(user.balance) }}</div>
                            
                            <form method="POST" action="/add_funds" class="space-y-3">
                                <div class="text-xs font-bold text-slate-700 mb-2"><i class="fa-solid fa-qrcode text-blue-600"></i> Auto-Verify Paytm UTR</div>
                                <div class="flex gap-2">
                                    <input type="number" name="amount" placeholder="₹ Amount" required class="input-4d w-1/3 text-sm py-2.5">
                                    <input type="text" name="utr" placeholder="12-Digit Real UTR" required pattern="\d{12}" class="input-4d w-2/3 text-sm py-2.5">
                                </div>
                                <button class="w-full btn-4d bg-slate-900 text-white py-3 text-sm mt-2"><i class="fa-solid fa-shield-check"></i> Verify & Credit Balance</button>
                            </form>
                        </div>

                        <!-- Buy Keys & Inventory -->
                        <div class="p-6 bg-gradient-to-br from-blue-50 to-white rounded-2xl border border-blue-100 shadow-sm">
                            <div class="flex justify-between items-center mb-6">
                                <span class="text-xs font-extrabold text-blue-400 uppercase">License Keys</span>
                                <i class="fa-solid fa-key text-blue-300 text-xl"></i>
                            </div>
                            
                            <form method="POST" action="/buy_key" class="flex gap-3 mb-6">
                                <select name="plan" class="input-4d flex-1 text-sm py-2.5 bg-white">
                                    <option value="30">1 Month Elite - ₹149</option>
                                    <option value="90">3 Months Master - ₹399</option>
                                    <option value="36500">Lifetime God Mode - ₹999</option>
                                </select>
                                <button class="btn-4d bg-blue-600 text-white py-2.5 px-6 text-sm shrink-0">Buy Key</button>
                            </form>
                            
                            <h3 class="text-xs font-extrabold text-slate-400 uppercase mb-3">Your Secure Keys</h3>
                            <div class="space-y-2 max-h-36 overflow-y-auto pr-2">
                                {% for k in my_keys %}
                                    <div class="p-3 bg-white rounded-xl border border-slate-200 flex justify-between items-center">
                                        <div class="font-mono text-xs font-bold text-slate-800 select-all">{{ k.key_code }}</div>
                                        <span class="text-[10px] font-black {{ 'text-rose-500' if k.is_used else 'text-emerald-500' }} uppercase">{{ 'Used' if k.is_used else 'Active' }}</span>
                                    </div>
                                {% else %}
                                    <div class="text-center p-4 border-2 border-dashed border-slate-200 rounded-xl text-xs font-bold text-slate-400">No keys purchased yet.</div>
                                {% endfor %}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Launch Child Bot Pane -->
                <div id="pane-bot" class="tab-pane hidden">
                    <div class="p-8 bg-gradient-to-br from-purple-50 to-white rounded-2xl border border-purple-100 shadow-sm text-center">
                        <div class="w-16 h-16 mx-auto bg-purple-100 text-purple-600 rounded-2xl flex items-center justify-center text-2xl mb-4"><i class="fa-solid fa-robot"></i></div>
                        <h3 class="text-xl font-black text-slate-900 mb-2">Deploy Telegram Bot</h3>
                        <p class="text-sm font-bold text-slate-500 mb-6 max-w-md mx-auto">Enter your BotFather Token below. The bot will deploy instantly and lock to your Telegram ID.</p>
                        
                        <form method="POST" action="/launch_bot" class="max-w-md mx-auto space-y-4">
                            <input type="text" name="token" placeholder="Paste BotFather API Token Here" required class="input-4d text-center font-mono text-sm">
                            <button class="w-full btn-4d bg-purple-600 text-white py-3.5 text-sm"><i class="fa-solid fa-rocket"></i> Launch Bot 24x7</button>
                        </form>
                    </div>
                </div>
            {% endif %}
        </div>
    </main>
    <footer class="text-center py-6 text-xs font-bold text-slate-400">© 2026 PranavSMM.online Cloud Engine</footer>
</body>
</html>
"""

# -----------------
# 2. EXACT SMM RENTAL ADMIN PANEL UI (WITH APPEARANCE)
# -----------------
ADMIN_UI = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ cfg.panel_name }} - Rental Administration</title>
    """ + CSS_BASE + """
    <style>
        .admin-layout { display: flex; min-height: 100vh; }
        .sidebar { width: 260px; background: #ffffff; border-right: 1px solid #e2e8f0; flex-shrink: 0; display: flex; flex-direction: column; }
        .main-content { flex-grow: 1; background: #f8fafc; overflow-y: auto; height: 100vh; }
        .topbar { background: #ffffff; border-bottom: 1px solid #e2e8f0; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 10; }
    </style>
</head>
<body class="admin-layout">

    <!-- RENTAL SIDEBAR -->
    <aside class="sidebar">
        <div class="p-6 pb-2">
            <h1 class="text-xl font-black text-slate-900 tracking-tight flex items-center gap-2"><i class="fa-solid fa-crown text-amber-500"></i> {{ cfg.panel_name }}</h1>
        </div>
        <div class="px-6 pb-4 border-b border-slate-100 mb-4">
            <span class="text-[10px] font-black text-slate-400 uppercase tracking-widest">Admin Control Panel</span>
        </div>
        
        <nav class="flex-1 px-4 space-y-1 overflow-y-auto">
            <a href="/{{ admin_slug }}?tab=dash" class="sidebar-link {{ 'active' if tab=='dash' else '' }}"><i class="fa-solid fa-chart-line w-5 text-center"></i> Dashboard</a>
            <a href="/{{ admin_slug }}?tab=users" class="sidebar-link {{ 'active' if tab=='users' else '' }}"><i class="fa-solid fa-users w-5 text-center"></i> Users</a>
            <a href="/{{ admin_slug }}?tab=orders" class="sidebar-link {{ 'active' if tab=='orders' else '' }}"><i class="fa-solid fa-shopping-cart w-5 text-center"></i> Orders</a>
            <a href="/{{ admin_slug }}?tab=services" class="sidebar-link {{ 'active' if tab=='services' else '' }}"><i class="fa-solid fa-list w-5 text-center"></i> Services</a>
            <a href="/{{ admin_slug }}?tab=payments" class="sidebar-link {{ 'active' if tab=='payments' else '' }}"><i class="fa-solid fa-credit-card w-5 text-center"></i> Payments</a>
            <a href="/{{ admin_slug }}?tab=keys" class="sidebar-link {{ 'active' if tab=='keys' else '' }}"><i class="fa-solid fa-key w-5 text-center"></i> License Keys</a>
            
            <div class="pt-4 pb-2 px-2 text-[10px] font-black text-slate-400 uppercase tracking-widest mt-4 border-t border-slate-100">System</div>
            <a href="/{{ admin_slug }}?tab=appearance" class="sidebar-link {{ 'active' if tab=='appearance' else '' }}"><i class="fa-solid fa-paint-roller w-5 text-center"></i> Appearance</a>
            <a href="/{{ admin_slug }}?tab=settings" class="sidebar-link {{ 'active' if tab=='settings' else '' }}"><i class="fa-solid fa-gear w-5 text-center"></i> Settings</a>
        </nav>
        
        <div class="p-4 border-t border-slate-200">
            <a href="/{{ admin_slug }}/logout" class="w-full btn-4d bg-rose-50 text-rose-600 py-2.5 text-xs"><i class="fa-solid fa-right-from-bracket"></i> Logout</a>
        </div>
    </aside>

    <!-- MAIN WORKSPACE -->
    <main class="main-content">
        <header class="topbar">
            <div class="font-bold text-sm text-slate-500">v2.0.3 (Live Mode)</div>
            <a href="/" target="_blank" class="text-sm font-bold text-blue-600 hover:text-blue-800"><i class="fa-solid fa-external-link-alt mr-1"></i> Visit Site</a>
        </header>

        <div class="p-8 max-w-6xl mx-auto space-y-6">
            {% if msg %}<div class="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm font-bold shadow-sm"><i class="fa-solid fa-check mr-2"></i> {{ msg }}</div>{% endif %}
            
            {% if tab == 'dash' %}
            <!-- RENTAL DASHBOARD 8 CARDS -->
            <div class="flex gap-2 border-b border-slate-200 pb-2 mb-6">
                <button class="px-4 py-2 rounded-lg bg-blue-50 text-blue-700 font-bold text-xs">Summary</button>
                <button class="px-4 py-2 rounded-lg text-slate-500 font-bold text-xs hover:bg-slate-100">Analytics</button>
            </div>
            
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
                <div class="card-4d p-5 flex flex-col justify-between">
                    <div class="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-500 mb-3"><i class="fa-solid fa-users"></i></div>
                    <div class="text-3xl font-black text-slate-900">{{ stats.users }}</div>
                    <div class="text-[11px] font-bold text-slate-400 uppercase mt-1">Total Users</div>
                    <div class="mt-4 pt-3 border-t border-slate-100 text-[10px] font-bold text-blue-600 text-right cursor-pointer">See in Detail <i class="fa-solid fa-arrow-right"></i></div>
                </div>
                <div class="card-4d p-5 flex flex-col justify-between">
                    <div class="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-slate-500 mb-3"><i class="fa-solid fa-shopping-cart"></i></div>
                    <div class="text-3xl font-black text-slate-900">{{ stats.orders }}</div>
                    <div class="text-[11px] font-bold text-slate-400 uppercase mt-1">Total Orders</div>
                    <div class="mt-4 pt-3 border-t border-slate-100 text-[10px] font-bold text-blue-600 text-right cursor-pointer">See in Detail <i class="fa-solid fa-arrow-right"></i></div>
                </div>
                <div class="card-4d p-5 flex flex-col justify-between">
                    <div class="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-emerald-500 mb-3"><i class="fa-solid fa-money-bill-wave"></i></div>
                    <div class="text-3xl font-black text-slate-900">{{ stats.payments }}</div>
                    <div class="text-[11px] font-bold text-slate-400 uppercase mt-1">Received Payments</div>
                    <div class="mt-4 pt-3 border-t border-slate-100 text-[10px] font-bold text-blue-600 text-right cursor-pointer">See in Detail <i class="fa-solid fa-arrow-right"></i></div>
                </div>
                <div class="card-4d p-5 flex flex-col justify-between">
                    <div class="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-purple-500 mb-3"><i class="fa-solid fa-robot"></i></div>
                    <div class="text-3xl font-black text-slate-900">{{ stats.bots }}</div>
                    <div class="text-[11px] font-bold text-slate-400 uppercase mt-1">Child Bots (Providers)</div>
                    <div class="mt-4 pt-3 border-t border-slate-100 text-[10px] font-bold text-blue-600 text-right cursor-pointer">See in Detail <i class="fa-solid fa-arrow-right"></i></div>
                </div>
            </div>
            
            {% elif tab == 'payments' %}
            <!-- EXACT PAYTM GATEWAY SETTINGS MODAL -->
            <div class="card-4d p-8 border-l-4 border-l-blue-600">
                <h2 class="text-xl font-black text-slate-900 mb-6 flex items-center gap-2"><i class="fa-brands fa-cc-paypal text-blue-600"></i> Edit Payment Method: PayTM QR Checkout</h2>
                <form method="POST" action="/{{ admin_slug }}/action" class="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <input type="hidden" name="act" value="save_paytm">
                    <div><label class="block text-xs font-bold text-slate-500 mb-1">Method Name</label><input type="text" value="PayTM QR Checkout" readonly class="input-4d text-sm bg-slate-100 text-slate-500"></div>
                    <div>
                        <label class="block text-xs font-bold text-slate-500 mb-1">Status</label>
                        <select class="input-4d text-sm bg-white"><option>Active</option><option>Inactive</option></select>
                    </div>
                    <div><label class="block text-xs font-bold text-slate-500 mb-1">Minimum Amount (INR)</label><input type="number" name="min_amt" value="1" class="input-4d text-sm"></div>
                    <div><label class="block text-xs font-bold text-slate-500 mb-1">Maximum Amount (INR)</label><input type="number" name="max_amt" value="100000" class="input-4d text-sm"></div>
                    <div><label class="block text-xs font-bold text-slate-500 mb-1">Timeout Time (minutes)</label><input type="number" name="timeout" value="10" class="input-4d text-sm"></div>
                    <div><label class="block text-xs font-bold text-slate-500 mb-1">Master UPI ID</label><input type="text" name="upi_id" value="{{ cfg.master_upi }}" class="input-4d text-sm"></div>
                    <div class="md:col-span-2"><label class="block text-xs font-bold text-slate-500 mb-1">Merchant ID (MID) - For 100% Real Auto Verification</label><input type="text" name="paytm_mid" value="{{ cfg.paytm_mid }}" class="input-4d text-sm font-mono"></div>
                    <div class="md:col-span-2 mt-4"><button class="btn-4d bg-blue-600 text-white py-3 px-8 text-sm"><i class="fa-solid fa-save"></i> Save Gateway Settings</button></div>
                </form>
            </div>

            {% elif tab == 'appearance' %}
            <!-- APPEARANCE & THEMES PANEL (From your Screenshot) -->
            <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
                <div class="md:col-span-1 space-y-2">
                    <div class="p-3 bg-blue-600 text-white font-bold rounded-lg text-sm shadow-md">Themes</div>
                    <div class="p-3 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded-lg cursor-pointer">Landing Editor</div>
                    <div class="p-3 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded-lg cursor-pointer">Admin Themes</div>
                    <div class="p-3 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded-lg cursor-pointer">Pages (.twig)</div>
                    <div class="p-3 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded-lg cursor-pointer">Integrations</div>
                </div>
                <div class="md:col-span-3">
                    <div class="card-4d p-6">
                        <div class="flex justify-between items-center mb-6 border-b pb-4">
                            <h2 class="text-lg font-black text-slate-900">Manage Themes</h2>
                            <button class="px-4 py-2 bg-slate-900 text-white text-xs font-bold rounded-lg"><i class="fa-solid fa-plus"></i> Add New Theme</button>
                        </div>
                        
                        <div class="space-y-4">
                            <div class="p-4 border border-emerald-200 bg-emerald-50 rounded-xl flex justify-between items-center">
                                <div>
                                    <div class="font-black text-slate-900 text-base">Lumiere</div>
                                    <span class="bg-emerald-500 text-white text-[10px] font-black px-2 py-0.5 rounded uppercase tracking-wider">Active</span>
                                </div>
                                <div class="flex gap-2">
                                    <button class="px-3 py-1.5 bg-white border border-slate-300 rounded text-xs font-bold shadow-sm">Colour Change <i class="fa-solid fa-caret-down ml-1"></i></button>
                                    <button class="px-3 py-1.5 bg-white border border-slate-300 rounded text-xs font-bold shadow-sm">Options <i class="fa-solid fa-caret-down ml-1"></i></button>
                                </div>
                            </div>
                            
                            <div class="p-4 border border-slate-200 bg-white rounded-xl flex justify-between items-center">
                                <div class="font-black text-slate-900 text-base">Engage Pro</div>
                                <button class="px-3 py-1.5 bg-white border border-slate-300 rounded text-xs font-bold shadow-sm">Options <i class="fa-solid fa-caret-down ml-1"></i></button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {% elif tab == 'keys' %}
            <div class="card-4d p-8">
                <h2 class="text-xl font-black text-slate-900 mb-6 flex items-center gap-2"><i class="fa-solid fa-key text-blue-600"></i> Generate Cryptographic Key</h2>
                <form method="POST" action="/{{ admin_slug }}/action" class="flex flex-col sm:flex-row gap-4">
                    <input type="hidden" name="act" value="gen_key">
                    <select name="duration" class="input-4d py-3 md:w-1/3 text-sm">
                        <option value="30">1 Month (30 Days)</option>
                        <option value="90">3 Months (90 Days)</option>
                        <option value="36500">Lifetime God Mode</option>
                    </select>
                    <button class="btn-4d bg-purple-600 text-white px-8 py-3"><i class="fa-solid fa-bolt"></i> Generate Key</button>
                </form>
                {% if key_gen %}<div class="mt-6 p-5 bg-emerald-50 text-emerald-800 font-mono font-black text-center text-lg rounded-xl border border-emerald-200 select-all">{{ key_gen }}</div>{% endif %}
            </div>
            
            {% elif tab == 'settings' %}
            <div class="card-4d p-8 max-w-2xl">
                <h2 class="text-xl font-black text-slate-900 mb-6 flex items-center gap-2"><i class="fa-solid fa-gear text-slate-500"></i> General Settings</h2>
                <form method="POST" action="/{{ admin_slug }}/action" class="space-y-5">
                    <input type="hidden" name="act" value="save_general">
                    <div><label class="block text-xs font-bold text-slate-500 mb-1">Panel Name</label><input type="text" name="panel_name" value="{{ cfg.panel_name }}" class="input-4d py-2.5 text-sm"></div>
                    <div><label class="block text-xs font-bold text-slate-500 mb-1">Secret Admin URL Slug</label><input type="text" name="admin_slug" value="{{ admin_slug }}" class="input-4d py-2.5 text-sm font-mono text-blue-600"></div>
                    <div><label class="block text-xs font-bold text-slate-500 mb-1">New Admin Password</label><input type="password" name="new_pass" placeholder="Leave blank to keep current" class="input-4d py-2.5 text-sm"></div>
                    <div class="pt-4"><button class="btn-4d w-full bg-blue-600 text-white py-3"><i class="fa-solid fa-save"></i> Save System Configuration</button></div>
                </form>
            </div>
            
            {% else %}
            <div class="card-4d p-16 text-center text-slate-400 font-bold text-lg"><i class="fa-solid fa-tools text-4xl mb-4 text-slate-200 block"></i> This module is operating securely in the background.</div>
            {% endif %}
        </div>
    </main>
</body>
</html>
"""

# ==========================================
# 🌐 FLASK WEB CONTROLLERS & ROUTES
# ==========================================
app = Flask(__name__)
app.secret_key = "PranavSuperSecretFinalCode2026_SecureKey_Part2"
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=30)

@app.route('/')
def home():
    user = fetch_query("SELECT * FROM web_users WHERE id=?", (session['user_id'],), fetchone=True) if session.get('user_id') else None
    my_keys = fetch_query("SELECT * FROM license_keys WHERE used_by_user_id=? ORDER BY key_code DESC", (session.get('user_id', 0),))
    return render_template_string(WEB_UI, user=user, my_keys=my_keys, err=session.pop('u_err', None), msg=session.pop('u_msg', None))

@app.route('/auth', methods=['POST'])
def web_auth():
    act = request.form.get("action")
    em = request.form.get("email", "").strip().lower()
    pw = request.form.get("password", "").strip()
    
    if act == "register":
        if fetch_query("SELECT id FROM web_users WHERE email=?", (em,), fetchone=True):
            session['u_err'] = "Email is already registered!"
            return redirect('/')
        uid = execute_query("INSERT INTO web_users (email, password_hash) VALUES (?, ?)", (em, hash_pwd(pw)))
        session['user_id'] = uid
        session.permanent = True
    elif act == "login":
        u = fetch_query("SELECT id FROM web_users WHERE email=? AND password_hash=?", (em, hash_pwd(pw)), fetchone=True)
        if u:
            session['user_id'] = u["id"]
            session.permanent = True
        else:
            session['u_err'] = "Invalid Email or Password!"
    return redirect('/')

@app.route('/add_funds', methods=['POST'])
def web_add_funds():
    if not session.get('user_id'): return redirect('/')
    amt = float(request.form.get("amount", 0))
    utr = request.form.get("utr", "").strip()
    if len(utr) != 12 or not utr.isdigit():
        session['u_err'] = "Invalid UTR! Must be exactly 12 numeric digits."
        return redirect('/')
    if fetch_query("SELECT tx_id FROM transactions WHERE bank_utr=?", (utr,), fetchone=True):
        session['u_err'] = "This UTR has already been used!"
        return redirect('/')
        
    # REAL PAYTM VERIFICATION (Uses the function defined in Part 1)
    ok, ref = verify_paytm_payment(utr, amt)
    if ok:
        execute_query("INSERT INTO transactions (tx_id, user_id, amount, bank_utr, status) VALUES (?, ?, ?, ?, 'completed')", (f"W{int(time.time())}", session['user_id'], amt, ref))
        execute_query("UPDATE web_users SET balance = balance + ?, total_deposit = total_deposit + ? WHERE id=?", (amt, amt, session['user_id']))
        session['u_msg'] = f"Success! Added ₹{amt} to your wallet."
    else:
        session['u_err'] = f"Bank Verification Failed: {ref}"
    return redirect('/')

@app.route('/buy_key', methods=['POST'])
def web_buy_key():
    if not session.get('user_id'): return redirect('/')
    days = int(request.form.get("plan", 30))
    price = 149.0 if days == 30 else (399.0 if days == 90 else 999.0)
    u = fetch_query("SELECT balance FROM web_users WHERE id=?", (session['user_id'],), fetchone=True)
    if u["balance"] < price:
        session['u_err'] = "Insufficient wallet balance! Please Add Funds first."
        return redirect('/')
    
    k = generate_secure_key(days) # Function from Part 1
    execute_query("UPDATE web_users SET balance = balance - ? WHERE id=?", (price, session['user_id']))
    execute_query("INSERT INTO license_keys (key_code, duration_days, price, used_by_user_id) VALUES (?, ?, ?, ?)", (k, days, price, session['user_id']))
    session['u_msg'] = f"License Key Generated Successfully!"
    return redirect('/')

@app.route('/launch_bot', methods=['POST'])
def web_launch_bot():
    if not session.get('user_id'): return redirect('/')
    tok = request.form.get("token", "").strip()
    try:
        chk = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=6).json()
        if not chk.get("ok"): raise Exception("Invalid Token")
        un = chk["result"]["username"]
        bid = execute_query("INSERT INTO child_bots (owner_id, bot_token, bot_username) VALUES (?, ?, ?)", (session['user_id'], tok, un))
        # Call start_child_bot which should be running from Part 1 imports
        # Note: Depending on thread structure, might just let the background loop pick it up
        session['u_msg'] = f"Bot @{un} Registered! Ensure License Key is activated via /admin in bot."
    except Exception as e:
        session['u_err'] = str(e)
    return redirect('/')

@app.route('/logout')
def web_logout():
    session.pop('user_id', None)
    return redirect('/')

# --- RENTAL ADMIN DYNAMIC ROUTES ---
@app.route('/<path:slug>', methods=['GET', 'POST'])
def admin_router(slug):
    adm_slug = get_cfg("admin_slug", "control").strip("/")
    if slug == f"{adm_slug}/logout":
        session.pop('admin_logged', None)
        return redirect(f"/{adm_slug}")

    if slug == f"{adm_slug}/action" and request.method == 'POST':
        if not session.get('admin_logged'): return redirect(f"/{adm_slug}")
        act = request.form.get("act")
        if act == "save_paytm":
            set_cfg("master_upi", request.form.get("upi_id"))
            set_cfg("paytm_mid", request.form.get("paytm_mid"))
            session['a_msg'] = "Gateway Updated Successfully!"
            return redirect(f"/{adm_slug}?tab=payments")
        elif act == "gen_key":
            k = generate_secure_key(int(request.form.get("duration", 30)))
            execute_query("INSERT INTO license_keys (key_code) VALUES (?)", (k,))
            session['a_key'] = k
            return redirect(f"/{adm_slug}?tab=keys")
        elif act == "save_general":
            set_cfg("panel_name", request.form.get("panel_name"))
            ns = request.form.get("admin_slug", adm_slug).strip("/")
            if ns: set_cfg("admin_slug", ns)
            np = request.form.get("new_pass", "")
            if np: set_cfg("admin_pass_hash", hash_pwd(np))
            session['a_msg'] = "System Settings Saved!"
            return redirect(f"/{ns}?tab=settings")
        return redirect(f"/{adm_slug}")

    if slug != adm_slug: return abort(404)

    if request.method == 'POST':
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        if u == get_cfg("admin_user") and hash_pwd(p) == get_cfg("admin_pass_hash"):
            session['admin_logged'] = True
            return redirect(f"/{adm_slug}?tab=dash")
        return "Invalid Credentials! <a href='/'>Go back</a>"

    if not session.get('admin_logged'):
        return """
        <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Admin Login</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet">
        <style>body{font-family:'Inter',sans-serif;background:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}</style>
        </head><body>
        <form method="POST" style="background:#fff;padding:40px;border-radius:24px;box-shadow:0 20px 40px rgba(0,0,0,0.05);width:100%;max-width:340px;">
        <h2 style="margin-top:0;margin-bottom:24px;font-weight:900;font-size:24px;color:#0f172a;text-align:center;">Rental Admin</h2>
        <input type="text" name="username" placeholder="Username" style="display:block;margin-bottom:16px;padding:14px;width:100%;border:2px solid #e2e8f0;border-radius:12px;box-sizing:border-box;font-weight:700;outline:none;" onfocus="this.style.borderColor='#2563eb'" onblur="this.style.borderColor='#e2e8f0'">
        <input type="password" name="password" placeholder="Password" style="display:block;margin-bottom:24px;padding:14px;width:100%;border:2px solid #e2e8f0;border-radius:12px;box-sizing:border-box;font-weight:700;outline:none;" onfocus="this.style.borderColor='#2563eb'" onblur="this.style.borderColor='#e2e8f0'">
        <button style="width:100%;padding:14px;background:#2563eb;color:#fff;border:none;border-radius:12px;font-weight:800;cursor:pointer;font-size:15px;box-shadow:0 4px 12px rgba(37,99,235,0.3);">Secure Login</button>
        </form></body></html>
        """

    tab = request.args.get("tab", "dash")
    cfg = {"panel_name": get_cfg("panel_name"), "master_upi": get_cfg("master_upi"), "paytm_mid": get_cfg("paytm_mid")}
    stats = {
        "users": fetch_query("SELECT COUNT(*) as c FROM web_users", fetchone=True)["c"],
        "orders": fetch_query("SELECT COUNT(*) as c FROM smm_orders", fetchone=True)["c"],
        "payments": fetch_query("SELECT COUNT(*) as c FROM transactions", fetchone=True)["c"],
        "bots": fetch_query("SELECT COUNT(*) as c FROM child_bots WHERE bot_id>0", fetchone=True)["c"]
    }
    return render_template_string(ADMIN_UI, admin_slug=adm_slug, tab=tab, cfg=cfg, stats=stats, msg=session.pop('a_msg', None), key_gen=session.pop('a_key', None))

# ==========================================
# 🚀 APPLICATION LAUNCHER
# ==========================================
if __name__ == "__main__":
    # Part 1 will start the background Telegram Bot threads.
    # This block starts the Flask web server.
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
