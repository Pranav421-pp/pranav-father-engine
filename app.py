import os
import time
import datetime
import random
import string
import secrets
import hashlib
import sqlite3
import threading
import urllib.parse
import requests
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, abort
import telebot
from telebot import types

# ==========================================
# ⚙️ SECURE ENVIRONMENT CONFIG (NO OPEN PASSWORDS)
# ==========================================
# ==========================================
# ⚙️ 100% PURE ENVIRONMENT CONFIG (ZERO EXPOSURE)
# ==========================================
RENDER_PORT = int(os.environ.get("PORT", "8081"))
MASTER_BOT_TOKEN = os.environ.get("MASTER_BOT_TOKEN", "").strip()
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID", "0"))

ENV_ADMIN_USER = os.environ.get("ADMIN_USER", "").strip()
ENV_ADMIN_PASS = os.environ.get("ADMIN_PASS", "").strip()
ENV_ADMIN_SLUG = os.environ.get("ADMIN_SLUG", "").strip().strip("/")
ENV_MASTER_UPI = os.environ.get("MASTER_UPI_ID", "").strip()
ENV_PAYTM_MID = os.environ.get("PAYTM_MID", "").strip()


DB_PATH = "pranav_4d_grandmaster.db"

def hash_pwd(pwd):
    return hashlib.sha256(str(pwd).encode()).hexdigest()

# ==========================================
# 🗄️ BULLETPROOF SQLITE ENGINE
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
        if commit:
            conn.commit()
        return cur.lastrowid
    except Exception as e:
        print(f"[DB EXEC ERR] {e}")
    finally:
        conn.close()

def fetch_query(query, params=(), fetchone=False):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchone() if fetchone else cur.fetchall()
    except Exception as e:
        print(f"[DB FETCH ERR] {e}")
        return None
    finally:
        conn.close()

def get_cfg(key, default=""):
    row = fetch_query("SELECT val FROM sys_cfg WHERE k=?", (key,), fetchone=True)
    return row["val"] if row else default

def set_cfg(key, val):
    execute_query("INSERT INTO sys_cfg (k, val) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET val=excluded.val", (key, str(val)))

def init_db():
    tables = [
        "CREATE TABLE IF NOT EXISTS sys_cfg (k TEXT PRIMARY KEY, val TEXT)",
        """CREATE TABLE IF NOT EXISTS web_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, password_hash TEXT,
            recovery_pin TEXT DEFAULT '1234', balance REAL DEFAULT 0.0, total_deposit REAL DEFAULT 0.0,
            total_spent REAL DEFAULT 0.0, auto_sub INTEGER DEFAULT 0, active_plan TEXT DEFAULT 'Free User',
            plan_price REAL DEFAULT 0.0, plan_days INTEGER DEFAULT 0, sub_expiry TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS bot_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, user_id INTEGER, username TEXT,
            balance REAL DEFAULT 0.0, total_deposit REAL DEFAULT 0.0, total_spent REAL DEFAULT 0.0,
            auto_sub INTEGER DEFAULT 0, sub_plan TEXT DEFAULT 'None', sub_expiry TIMESTAMP DEFAULT NULL,
            UNIQUE(bot_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS child_bots (
            bot_id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, web_user_id INTEGER DEFAULT 0,
            bot_token TEXT UNIQUE, bot_username TEXT, bot_name TEXT, upi_id TEXT DEFAULT '',
            is_licensed INTEGER DEFAULT 0, subscription_expiry TIMESTAMP, status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS license_keys (
            key_code TEXT PRIMARY KEY, duration_days INTEGER DEFAULT 30, price REAL DEFAULT 149.0,
            label TEXT DEFAULT '1 Month Pro', is_sub INTEGER DEFAULT 0, used_by_bot_id INTEGER DEFAULT NULL,
            used_by_user_id INTEGER DEFAULT NULL, is_used INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS smm_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER DEFAULT 0, category TEXT DEFAULT 'Instagram',
            service_name TEXT, rate_per_1000 REAL DEFAULT 50.0
        )""",
        """CREATE TABLE IF NOT EXISTS smm_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER DEFAULT 0, user_id INTEGER DEFAULT 0,
            web_user_id INTEGER DEFAULT 0, service_name TEXT, link TEXT, quantity INTEGER,
            charge REAL, status TEXT DEFAULT 'Completed ✅', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS transactions (
            tx_id TEXT PRIMARY KEY, bot_id INTEGER DEFAULT 0, user_id INTEGER DEFAULT 0,
            web_user_id INTEGER DEFAULT 0, amount REAL, gateway TEXT DEFAULT 'Paytm',
            bank_utr TEXT DEFAULT '', status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    ]
    for t in tables:
        execute_query(t)

    defaults = {
        "flask_secret": os.environ.get("FLASK_SECRET_KEY", "Pranav4DGrandMasterFixedSecret2050Key"),
        "admin_user": ENV_ADMIN_USER,
        "admin_pass_hash": hash_pwd(ENV_ADMIN_PASS),
        "admin_slug": ENV_ADMIN_SLUG,
        "active_gw": "paytm",
        "auto_verify_utr": "1",
        "upi_paytm": ENV_MASTER_UPI,
        "paytm_mid": ENV_PAYTM_MID,
        "upi_bharatpe": ENV_MASTER_UPI,
        "bharatpe_mid": "",
        "bharatpe_token": "",
        "upi_fampay": ENV_MASTER_UPI,
        "upi_phonepe": ENV_MASTER_UPI,
        "upi_gpay": ENV_MASTER_UPI,
        "upi_amazon": ENV_MASTER_UPI,
        "webhook_secret": "pranav_auto_99"
    }
    for k, v in defaults.items():
        if not get_cfg(k):
            set_cfg(k, v)

    exp = (datetime.datetime.now() + datetime.timedelta(days=36500)).strftime("%Y-%m-%d %H:%M:%S")
    execute_query("""
        INSERT OR IGNORE INTO child_bots (bot_id, owner_id, bot_token, bot_username, bot_name, upi_id, is_licensed, subscription_expiry)
        VALUES (0, ?, 'MASTER', 'PranavMasterBot', 'Pranav 4D Engine', ?, 1, ?)
    """, (SUPER_ADMIN_ID, ENV_MASTER_UPI, exp))

    if fetch_query("SELECT COUNT(*) as c FROM smm_services", fetchone=True)["c"] == 0:
        srvs = [
            (0, "Instagram", "🔥 Instagram Indian Followers [Non-Drop]", 49.0),
            (0, "Instagram", "❤️ Instagram Instant Likes [Real]", 14.0),
            (0, "Instagram", "🚀 Instagram Reels Views [Ultra Fast]", 4.0),
            (0, "Telegram", "📢 Telegram Channel Members [Zero Drop]", 75.0),
            (0, "YouTube", "▶️ YouTube High Retention Views", 95.0)
        ]
        for b_id, cat, s_name, rate in srvs:
            execute_query("INSERT INTO smm_services (bot_id, category, service_name, rate_per_1000) VALUES (?, ?, ?, ?)", (b_id, cat, s_name, rate))

init_db()

# ==========================================
# 🔒 PERMANENT SESSION SETUP (NO AUTO-LOGOUT!)
# ==========================================
app = Flask(__name__)
app.secret_key = get_cfg("flask_secret", "Pranav4DGrandMasterFixedSecret2050Key")
app.config["SESSION_COOKIE_NAME"] = "pranav_4d_permanent_session"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=30)

user_states = {}
running_child_bots = {}

PLANS_CATALOG = {
    "7": {"days": 7, "price": 49.0, "min_sub_wallet": 100.0, "label": "7 Days Trial Pro", "badge": "TRIAL"},
    "30": {"days": 30, "price": 149.0, "min_sub_wallet": 300.0, "label": "1 Month Elite", "badge": "1 MONTH"},
    "90": {"days": 90, "price": 399.0, "min_sub_wallet": 800.0, "label": "3 Months Master", "badge": "3 MONTHS"},
    "36500": {"days": 36500, "price": 999.0, "min_sub_wallet": 2000.0, "label": "👑 Lifetime God Mode", "badge": "LIFETIME"}
}

def get_all_upis():
    gw = get_cfg("active_gw", "paytm")
    upis = {
        "paytm": get_cfg("upi_paytm", ENV_MASTER_UPI),
        "bharatpe": get_cfg("upi_bharatpe", ENV_MASTER_UPI),
        "fampay": get_cfg("upi_fampay", ENV_MASTER_UPI),
        "phonepe": get_cfg("upi_phonepe", ENV_MASTER_UPI),
        "gpay": get_cfg("upi_gpay", ENV_MASTER_UPI),
        "amazon": get_cfg("upi_amazon", ENV_MASTER_UPI)
    }
    return {"active_gw": gw, "primary": upis.get(gw, ENV_MASTER_UPI), "map": upis}

# ==========================================
# ⚡ UNIVERSAL AUTO-VERIFY ENGINE (WEB + BOT)
# ==========================================
def check_paytm_gateway(order_id, amount):
    mid = get_cfg("paytm_mid", "")
    if not mid:
        return False, ""
    try:
        r = requests.post("https://securegw.paytm.in/merchant-status/getTxnStatus", json={"MID": mid, "ORDERID": order_id}, timeout=5).json()
        if r.get("STATUS") == "TXN_SUCCESS" and float(r.get("TXNAMOUNT", 0)) >= float(amount):
            return True, r.get("BANKTXNID", order_id)
    except:
        pass
    return False, ""

def check_bharatpe_gateway(amount, utr_match=""):
    token = get_cfg("bharatpe_token", "")
    mid = get_cfg("bharatpe_mid", "")
    if not token or not mid:
        return False, ""
    try:
        url = f"https://payments-tesseract.bharatpe.in/api/v1/merchant/transactions?module=PAYMENT_QR&merchantId={mid}"
        r = requests.get(url, headers={"token": token, "user-agent": "Mozilla/5.0"}, timeout=5).json()
        for t in r.get("data", {}).get("transactions", []):
            if t.get("status") == "SUCCESS" and float(t.get("amount", 0)) == float(amount):
                ref = str(t.get("bankReferenceNo", ""))
                if not utr_match or ref == utr_match:
                    if ref and not fetch_query("SELECT tx_id FROM transactions WHERE bank_utr=? AND status='completed'", (ref,), fetchone=True):
                        return True, ref
    except:
        pass
    return False, ""

def complete_tx_and_notify(tx_id, utr):
    tx = fetch_query("SELECT * FROM transactions WHERE tx_id=?", (tx_id,), fetchone=True)
    if not tx or tx["status"] == "completed":
        return False
    execute_query("UPDATE transactions SET status='completed', bank_utr=? WHERE tx_id=?", (utr, tx_id))
    amt = float(tx["amount"])
    if int(tx["web_user_id"]) > 0:
        execute_query("UPDATE web_users SET balance = balance + ?, total_deposit = total_deposit + ? WHERE id=?", (amt, amt, tx["web_user_id"]))
    if int(tx["user_id"]) > 0:
        execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (amt, amt, tx["bot_id"], tx["user_id"]))
        # Send instant auto-verified alert on Telegram!
        try:
            b_tok = MASTER_BOT_TOKEN if int(tx["bot_id"]) == 0 else fetch_query("SELECT bot_token FROM child_bots WHERE bot_id=?", (tx["bot_id"],), fetchone=True)["bot_token"]
            if b_tok:
                tb = telebot.TeleBot(b_tok)
                tb.send_message(tx["user_id"], f"🎉 **𝗔𝗨𝗧𝗢-𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗 𝗣𝗔𝗬𝗠𝗘𝗡𝗧!**\n\n💵 Amount: ₹{amt:.2f}\n🧾 Ref/UTR: `{utr}`\n✅ आपका बैलेंस ऑटोमैटिक आपके वॉलेट में जोड़ दिया गया है!", parse_mode="Markdown")
        except:
            pass
    return True

# ==========================================
# 🎨 GRANDMASTER 4D PURE WHITE CSS (USER + ADMIN)
# ==========================================
STYLE_4D = """
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800;900&display=swap" rel="stylesheet">
<style>
    body {
        font-family: 'Plus Jakarta Sans', sans-serif;
        background: linear-gradient(135deg, #f0f4ff 0%, #ffffff 50%, #fdf2f8 100%);
        color: #0f172a;
        overflow-x: hidden;
    }
    .card-4d {
        background: #ffffff;
        border-radius: 26px;
        border: 2px solid #e2e8f0;
        box-shadow: 0 18px 38px -12px rgba(15, 23, 42, 0.08), 0 7px 0 0 #cbd5e1;
        transition: all 0.2s ease;
    }
    .card-4d:hover {
        transform: translateY(-3px);
        border-color: #a5b4fc;
        box-shadow: 0 24px 45px -12px rgba(79, 70, 229, 0.14), 0 9px 0 0 #94a3b8;
    }
    .btn-4d {
        display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem;
        font-weight: 800; border-radius: 16px; transition: all 0.12s ease; cursor: pointer;
    }
    .btn-4d:active { transform: translateY(4px) !important; border-bottom-width: 1px !important; }
    .btn-purple { background: linear-gradient(135deg, #6366f1, #8b5cf6, #d946ef); color: #fff; border-bottom: 5px solid #4338ca; box-shadow: 0 8px 20px rgba(99, 102, 241, 0.4); }
    .btn-emerald { background: linear-gradient(135deg, #10b981, #059669); color: #fff; border-bottom: 5px solid #065f46; box-shadow: 0 8px 20px rgba(16, 185, 129, 0.35); }
    .btn-amber { background: linear-gradient(135deg, #f59e0b, #ea580c); color: #fff; border-bottom: 5px solid #9a3412; box-shadow: 0 8px 20px rgba(234, 88, 12, 0.35); }
    .btn-sky { background: linear-gradient(135deg, #0ea5e9, #2563eb); color: #fff; border-bottom: 5px solid #1e40af; box-shadow: 0 8px 20px rgba(37, 99, 235, 0.35); }
    .btn-rose { background: linear-gradient(135deg, #f43f5e, #e11d48); color: #fff; border-bottom: 5px solid #881337; box-shadow: 0 8px 20px rgba(225, 29, 72, 0.35); }
    .btn-clean { background: #ffffff; color: #1e293b; border: 2px solid #cbd5e1; border-bottom: 5px solid #94a3b8; }
    .input-4d {
        background: #f8fafc; border: 2px solid #cbd5e1; border-bottom: 4px solid #94a3b8;
        border-radius: 14px; padding: 0.75rem 1rem; font-weight: 700; color: #0f172a; width: 100%;
    }
    .input-4d:focus { outline: none; background: #fff; border-color: #6366f1; border-bottom-color: #4338ca; }
</style>
<script>
    function toggleDrawer() {
        document.getElementById('side-drawer').classList.toggle('translate-x-full');
        document.getElementById('drawer-bg').classList.toggle('hidden');
    }
    function switchTab(id) {
        document.querySelectorAll('.tab-pane').forEach(e => e.classList.add('hidden'));
        document.querySelectorAll('.t-btn').forEach(e => { e.classList.remove('btn-purple'); e.classList.add('btn-clean'); });
        const pane = document.getElementById('pane-' + id);
        if (pane) pane.classList.remove('hidden');
        const btn = document.getElementById('btn-' + id);
        if (btn) { btn.classList.remove('btn-clean'); btn.classList.add('btn-purple'); }
    }
</script>
"""

# 100% PUBLIC NAVBAR (Zero Admin Links Here!)
NAVBAR_PUBLIC = """
<header class="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b-2 border-slate-200 px-4 sm:px-6 py-3.5 shadow-xs">
    <div class="max-w-7xl mx-auto flex justify-between items-center">
        <a href="/" class="flex items-center gap-2.5">
            <div class="w-10 h-10 rounded-2xl btn-purple flex items-center justify-center text-lg font-black">⚡</div>
            <div>
                <span class="text-xl font-black bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 bg-clip-text text-transparent">PranavSMM.online</span>
                <span class="block text-[10px] font-extrabold text-slate-400 uppercase tracking-widest">4D Pure White Cloud</span>
            </div>
        </a>
        <div class="flex items-center gap-2">
            {% if session.get('user_id') %}
                <a href="/dashboard" class="hidden sm:inline-flex btn-4d btn-emerald px-4 py-2 text-xs">🚀 Dashboard</a>
            {% else %}
                <a href="/login" class="hidden sm:inline-flex btn-4d btn-clean px-4 py-2 text-xs">Login</a>
                <a href="/register" class="hidden sm:inline-flex btn-4d btn-purple px-4 py-2 text-xs">Sign Up</a>
            {% endif %}
            <button onclick="toggleDrawer()" class="btn-4d btn-clean px-3 py-2 text-sm font-black">⋮ ☰</button>
        </div>
    </div>
</header>
<div id="drawer-bg" onclick="toggleDrawer()" class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 hidden"></div>
<aside id="side-drawer" class="fixed top-0 right-0 h-full w-72 bg-white border-l-2 border-slate-200 z-50 transform translate-x-full transition-transform duration-300 p-6 flex flex-col justify-between shadow-2xl">
    <div>
        <div class="flex justify-between items-center pb-4 border-b-2 border-slate-100">
            <span class="font-black text-base text-slate-900">⚡ 4D Quick Menu</span>
            <button onclick="toggleDrawer()" class="w-8 h-8 rounded-xl bg-rose-100 text-rose-600 font-black">✕</button>
        </div>
        <nav class="mt-4 space-y-2">
            <a href="/" class="block p-3 rounded-xl bg-slate-50 font-extrabold text-xs border border-slate-200">🏠 Home Page</a>
            {% if session.get('user_id') %}
                <a href="/dashboard?tab=overview" class="block p-3 rounded-xl bg-indigo-50 text-indigo-700 font-extrabold text-xs border border-indigo-200">📊 My 4D Dashboard</a>
                <a href="/dashboard?tab=order" class="block p-3 rounded-xl bg-pink-50 text-pink-700 font-extrabold text-xs border border-pink-200">🛒 New SMM Order</a>
                <a href="/dashboard?tab=funds" class="block p-3 rounded-xl bg-emerald-50 text-emerald-700 font-extrabold text-xs border border-emerald-200">💰 Add Funds (Auto-UPI)</a>
                <a href="/dashboard?tab=plans" class="block p-3 rounded-xl bg-amber-50 text-amber-700 font-extrabold text-xs border border-amber-200">🎟️ Plans & License Keys</a>
                <a href="/dashboard?tab=bots" class="block p-3 rounded-xl bg-sky-50 text-sky-700 font-extrabold text-xs border border-sky-200">🤖 Create Child Bot</a>
            {% else %}
                <a href="/login" class="block p-3 rounded-xl bg-indigo-50 text-indigo-700 font-extrabold text-xs border border-indigo-200">🔐 User Login</a>
                <a href="/register" class="block p-3 rounded-xl bg-emerald-50 text-emerald-700 font-extrabold text-xs border border-emerald-200">🚀 Create Account</a>
                <a href="/forgot-password" class="block p-3 rounded-xl bg-amber-50 text-amber-700 font-extrabold text-xs border border-amber-200">🔑 Forgot Password</a>
            {% endif %}
            <a href="https://t.me/{{ master_bot_uname }}" target="_blank" class="block p-3 rounded-xl bg-purple-50 text-purple-700 font-extrabold text-xs border border-purple-200">🤖 Open Telegram Bot ↗</a>
        </nav>
    </div>
    <div class="pt-4 border-t border-slate-200 text-center">
        {% if session.get('user_id') %}
            <a href="/logout" class="w-full btn-4d btn-rose py-2.5 text-xs">🚪 Logout</a>
        {% else %}
            <a href="/login" class="w-full btn-4d btn-purple py-2.5 text-xs">🔐 Sign In</a>
        {% endif %}
    </div>
</aside>
"""

HOME_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PranavSMM.online - 4D Automated SMM & All-UPI Cloud</title>
    """ + STYLE_4D + """
</head>
<body class="min-h-screen flex flex-col justify-between">
    """ + NAVBAR_PUBLIC + """
    <main class="max-w-7xl mx-auto px-4 py-12 text-center flex-1">
        <div class="inline-flex items-center gap-2 bg-white border-2 border-indigo-200 px-4 py-1.5 rounded-full text-xs font-black text-indigo-600 mb-6 shadow-xs">
            🟢 24×7 NON-STOP 4D ENGINE • 100% AUTO-VERIFIED UPI
        </div>
        <h1 class="text-4xl sm:text-6xl font-black text-slate-900 tracking-tight leading-tight">
            Next-Gen Pure White 4D <br>
            <span class="bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-500 bg-clip-text text-transparent">SMM & All-UPI Gateway</span>
        </h1>
        <p class="text-slate-600 font-bold mt-4 max-w-2xl mx-auto text-sm sm:text-base">
            तुरंत SMM ऑर्डर्स लगाएं, अपना खुद का 24×7 टेलीग्राम रीसेलर बॉट बनाएं, और Paytm, FamPay, BharatPe, PhonePe, GPay से ऑटो-वेरिफाइड रिचार्ज करें!
        </p>
        <div class="mt-8 flex flex-wrap justify-center gap-3.5">
            {% if session.get('user_id') %}
                <a href="/dashboard" class="btn-4d btn-purple px-8 py-4 text-sm">🚀 Open 4D Dashboard</a>
            {% else %}
                <a href="/register" class="btn-4d btn-purple px-8 py-4 text-sm">🚀 Create Free Account</a>
                <a href="/login" class="btn-4d btn-emerald px-8 py-4 text-sm">🔐 User Login</a>
            {% endif %}
            <a href="https://t.me/{{ master_bot_uname }}" target="_blank" class="btn-4d btn-sky px-8 py-4 text-sm">🤖 Launch Telegram Bot</a>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mt-14 text-left">
            {% for k, p in plans.items() %}
            <div class="card-4d p-6 flex flex-col justify-between">
                <div>
                    <span class="bg-indigo-100 text-indigo-700 text-[10px] font-black px-3 py-1 rounded-full">{{ p.badge }}</span>
                    <h3 class="text-lg font-black text-slate-900 mt-3">{{ p.label }}</h3>
                    <div class="text-3xl font-black text-indigo-600 mt-1">₹{{ p.price|int }}</div>
                    <div class="mt-3 p-2.5 rounded-xl bg-slate-50 border border-slate-200 text-[11px] font-bold text-slate-600 space-y-1">
                        <div>⚡ <b>One-Time:</b> ₹{{ p.price|int }} Direct</div>
                        <div>🔄 <b>Auto-Sub Min Wallet:</b> ₹{{ p.min_sub_wallet|int }}</div>
                    </div>
                </div>
                <a href="/dashboard?tab=plans" class="mt-5 w-full btn-4d btn-purple py-2.5 text-xs">Activate Plan →</a>
            </div>
            {% endfor %}
        </div>
    </main>
    <footer class="bg-white border-t-2 border-slate-200 py-5 text-center text-xs font-extrabold text-slate-400">
        © 2026 PranavSMM.online • 4D Enterprise Cloud
    </footer>
</body>
</html>
"""

AUTH_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - PranavSMM.online</title>
    """ + STYLE_4D + """
</head>
<body class="min-h-screen flex flex-col justify-between">
    """ + NAVBAR_PUBLIC + """
    <main class="flex-1 flex items-center justify-center p-4">
        <div class="card-4d p-7 sm:p-8 w-full max-w-md">
            <div class="text-center mb-5">
                <div class="w-14 h-14 mx-auto rounded-2xl btn-purple text-2xl flex items-center justify-center mb-2">🔐</div>
                <h2 class="text-2xl font-black text-slate-900">{{ title }}</h2>
                <p class="text-xs font-bold text-slate-500">{{ subtitle }}</p>
            </div>
            {% if error %}<div class="bg-rose-50 border-2 border-rose-300 text-rose-700 p-3 rounded-xl text-xs font-extrabold mb-4 text-center">{{ error }}</div>{% endif %}
            {% if success %}<div class="bg-emerald-50 border-2 border-emerald-300 text-emerald-700 p-3 rounded-xl text-xs font-extrabold mb-4 text-center">{{ success }}</div>{% endif %}
            <form method="POST" class="space-y-3.5">
                {% if mode == 'register' %}
                    <input type="text" name="name" required placeholder="Your Full Name" class="input-4d text-sm">
                    <input type="email" name="email" required placeholder="Email Address" class="input-4d text-sm">
                    <input type="password" name="password" required placeholder="Create Password" class="input-4d text-sm">
                    <input type="text" name="recovery_pin" pattern="\\d{4}" maxlength="4" required placeholder="4-Digit Recovery PIN (फॉरगॉट पासवर्ड के लिए)" class="input-4d text-sm">
                {% elif mode == 'forgot' %}
                    <input type="email" name="email" required placeholder="Registered Email Address" class="input-4d text-sm">
                    <input type="text" name="recovery_pin" pattern="\\d{4}" maxlength="4" required placeholder="Enter 4-Digit Recovery PIN" class="input-4d text-sm">
                    <input type="password" name="new_password" required placeholder="Enter New Password" class="input-4d text-sm">
                {% elif mode == 'admin' %}
                    <input type="text" name="username" required placeholder="Master Admin Username" class="input-4d text-sm">
                    <input type="password" name="password" required placeholder="Master Admin Password" class="input-4d text-sm">
                {% else %}
                    <input type="email" name="email" required placeholder="Email Address" class="input-4d text-sm">
                    <input type="password" name="password" required placeholder="Password" class="input-4d text-sm">
                    <div class="text-right"><a href="/forgot-password" class="text-xs font-extrabold text-indigo-600 underline">Forgot Password?</a></div>
                {% endif %}
                <button type="submit" class="w-full btn-4d btn-purple py-3.5 text-sm">{{ btn_text }} →</button>
            </form>
            {% if mode != 'admin' %}
            <div class="text-center mt-5 text-xs font-bold text-slate-500">
                {% if mode == 'login' %}
                    New here? <a href="/register" class="text-indigo-600 font-black underline">Create Free Account</a>
                {% else %}
                    Already have an account? <a href="/login" class="text-indigo-600 font-black underline">Login Here</a>
                {% endif %}
            </div>
            {% endif %}
        </div>
    </main>
</body>
</html>
"""

USER_DASH_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>4D User Panel - PranavSMM.online</title>
    """ + STYLE_4D + """
    <script>
        let pendingTx = "{{ pending_tx.tx_id if pending_tx else '' }}";
        function setAmt(v) { document.getElementById('f_amt').value = v; }
        function calcPrice() {
            const s = document.getElementById('s_sel');
            if (!s) return;
            const rate = parseFloat(s.options[s.selectedIndex].getAttribute('data-rate') || 0);
            const qty = parseFloat(document.getElementById('o_qty').value || 0);
            document.getElementById('o_chg').innerText = '₹' + ((qty / 1000.0) * rate).toFixed(2);
        }
        function openPlanModal(k, lbl, pr, msub) {
            document.getElementById('pm_key').value = k;
            document.getElementById('pm_title').innerText = lbl;
            document.getElementById('pm_one').innerText = '₹' + pr;
            document.getElementById('pm_sub').innerText = '₹' + pr + ' (Min Wallet ₹' + msub + ')';
            document.getElementById('plan_modal').classList.remove('hidden');
        }
        if (pendingTx) {
            setInterval(async () => {
                try {
                    const r = await fetch('/api/payment/status/' + pendingTx);
                    const d = await r.json();
                    if (d.status === 'completed') window.location.href = '/dashboard?tab=funds';
                } catch(e) {}
            }, 3000);
        }
        window.onload = () => {
            const t = new URLSearchParams(window.location.search).get('tab') || 'overview';
            switchTab(t);
            calcPrice();
        };
    </script>
</head>
<body class="min-h-screen flex flex-col justify-between">
    """ + NAVBAR_PUBLIC + """
    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-7 w-full space-y-6 flex-1">
        <!-- Header & 4D Tabs -->
        <div class="card-4d p-5 flex flex-col lg:flex-row justify-between items-center gap-4">
            <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-2xl btn-purple text-xl flex items-center justify-center font-black">{{ user.name[:1]|upper }}</div>
                <div>
                    <h1 class="text-lg font-black text-slate-900">नमस्ते, {{ user.name }}!</h1>
                    <p class="text-xs font-bold text-slate-500">{{ user.email }} • Recovery PIN: <b class="text-indigo-600">{{ user.recovery_pin }}</b></p>
                </div>
            </div>
            <div class="flex flex-wrap justify-center gap-2">
                <button id="btn-overview" onclick="switchTab('overview')" class="t-btn btn-4d btn-purple px-4 py-2 text-xs">📊 Overview</button>
                <button id="btn-order" onclick="switchTab('order')" class="t-btn btn-4d btn-clean px-4 py-2 text-xs">🛒 New Order</button>
                <button id="btn-funds" onclick="switchTab('funds')" class="t-btn btn-4d btn-clean px-4 py-2 text-xs">💰 Add Funds</button>
                <button id="btn-plans" onclick="switchTab('plans')" class="t-btn btn-4d btn-clean px-4 py-2 text-xs">🎟️ Plans & Keys</button>
                <button id="btn-bots" onclick="switchTab('bots')" class="t-btn btn-4d btn-clean px-4 py-2 text-xs">🤖 Child Bots</button>
            </div>
        </div>

        {% if msg %}<div class="card-4d p-4 border-l-8 border-l-emerald-500 bg-emerald-50 text-emerald-900 font-extrabold text-xs sm:text-sm">{{ msg }}</div>{% endif %}
        {% if err %}<div class="card-4d p-4 border-l-8 border-l-rose-500 bg-rose-50 text-rose-900 font-extrabold text-xs sm:text-sm">{{ err }}</div>{% endif %}

        <!-- PANE 1: OVERVIEW -->
        <div id="pane-overview" class="tab-pane space-y-6">
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
                <div class="card-4d p-6">
                    <span class="text-xs font-extrabold text-slate-400">WALLET BALANCE</span>
                    <div class="text-3xl font-black text-emerald-600 mt-1">₹{{ "%.2f"|format(user.balance) }}</div>
                    <button onclick="switchTab('funds')" class="mt-3 w-full btn-4d btn-emerald py-2 text-xs">➕ Add Funds</button>
                </div>
                <div class="card-4d p-6">
                    <span class="text-xs font-extrabold text-slate-400">TOTAL SPENT</span>
                    <div class="text-3xl font-black text-indigo-600 mt-1">₹{{ "%.2f"|format(user.total_spent) }}</div>
                    <button onclick="switchTab('order')" class="mt-3 w-full btn-4d btn-purple py-2 text-xs">🛒 New Order</button>
                </div>
                <div class="card-4d p-6">
                    <span class="text-xs font-extrabold text-slate-400">ACTIVE PLAN</span>
                    <div class="text-lg font-black text-slate-900 mt-1 truncate">{{ user.active_plan }}</div>
                    <span class="inline-block mt-2 px-2.5 py-1 rounded-full text-[10px] font-black {{ 'bg-emerald-100 text-emerald-700' if user.auto_sub else 'bg-indigo-100 text-indigo-700' }}">
                        {{ '🔄 Auto-Sub ON' if user.auto_sub else '⚡ One-Time Mode' }}
                    </span>
                </div>
                <div class="card-4d p-6">
                    <span class="text-xs font-extrabold text-slate-400">TELEGRAM BOT</span>
                    <div class="text-base font-black text-slate-900 mt-1">24×7 Automated</div>
                    <a href="https://t.me/{{ master_bot_uname }}" target="_blank" class="mt-3 w-full btn-4d btn-sky py-2 text-xs">🤖 Open Bot ↗</a>
                </div>
            </div>
        </div>

        <!-- PANE 2: ORDER SMM -->
        <div id="pane-order" class="tab-pane hidden grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div class="card-4d p-6">
                <h2 class="text-lg font-black text-slate-900 mb-4">🛒 Place Instant SMM Order</h2>
                <form method="POST" action="/dashboard/place-order" class="space-y-4">
                    <select id="s_sel" name="service_id" onchange="calcPrice()" class="input-4d text-xs sm:text-sm">
                        {% for s in services %}
                            <option value="{{ s.id }}" data-rate="{{ s.rate_per_1000 }}">{{ s.service_name }} — ₹{{ s.rate_per_1000 }}/1k</option>
                        {% endfor %}
                    </select>
                    <input type="url" name="link" required placeholder="https://instagram.com/..." class="input-4d text-sm">
                    <div class="grid grid-cols-2 gap-3">
                        <input type="number" id="o_qty" name="quantity" value="500" min="50" oninput="calcPrice()" required class="input-4d text-sm">
                        <div id="o_chg" class="input-4d bg-indigo-50 text-indigo-700 font-black text-center">₹24.50</div>
                    </div>
                    <button type="submit" class="w-full btn-4d btn-purple py-3.5 text-sm">🚀 Submit Order Now</button>
                </form>
            </div>
            <div class="card-4d p-6">
                <h2 class="text-lg font-black text-slate-900 mb-4">🗓️ Recent Orders</h2>
                {% if my_orders %}
                    <div class="space-y-2.5 max-h-80 overflow-y-auto">
                        {% for o in my_orders %}
                        <div class="p-3 rounded-2xl bg-slate-50 border border-slate-200 flex justify-between items-center text-xs font-bold">
                            <div>
                                <div class="font-black text-slate-900">#{{ o.id }} • {{ o.service_name }}</div>
                                <div class="text-indigo-600">Qty: {{ o.quantity }} • ₹{{ "%.2f"|format(o.charge) }}</div>
                            </div>
                            <span class="px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-black">{{ o.status }}</span>
                        </div>
                        {% endfor %}
                    </div>
                {% else %}
                    <p class="text-xs font-bold text-slate-400">अभी कोई ऑर्डर नहीं है।</p>
                {% endif %}
            </div>
        </div>

        <!-- PANE 3: ADD FUNDS (ALL UPI AUTO-VERIFY) -->
        <div id="pane-funds" class="tab-pane hidden space-y-6">
            <div class="card-4d p-6 sm:p-8">
                <h2 class="text-xl font-black text-slate-900">💰 Auto-Verified All-UPI Wallet Recharge</h2>
                <p class="text-xs font-bold text-slate-500 mt-1">₹100, ₹500, ₹1000 या ₹2000 चुनकर QR जनरेट करें। पेमेंट करते ही ऑटो-वेरिफाई हो जाएगा!</p>
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 my-4">
                    <button type="button" onclick="setAmt(100)" class="btn-4d btn-sky py-2.5 text-xs">+ ₹100</button>
                    <button type="button" onclick="setAmt(500)" class="btn-4d btn-emerald py-2.5 text-xs">+ ₹500</button>
                    <button type="button" onclick="setAmt(1000)" class="btn-4d btn-amber py-2.5 text-xs">🔥 + ₹1000</button>
                    <button type="button" onclick="setAmt(2000)" class="btn-4d btn-purple py-2.5 text-xs">💎 + ₹2000</button>
                </div>
                <form method="POST" action="/dashboard/create-qr" class="flex flex-col sm:flex-row gap-3">
                    <input type="number" id="f_amt" name="amount" value="{{ pending_tx.amount|int if pending_tx else 1000 }}" min="10" required class="input-4d text-base">
                    <button type="submit" class="btn-4d btn-purple px-8 py-3.5 text-xs sm:text-sm shrink-0">⚡ Generate Auto-Verify QR</button>
                </form>

                {% if pending_tx %}
                <div class="mt-6 p-5 rounded-3xl bg-indigo-50/80 border-2 border-indigo-300 grid grid-cols-1 md:grid-cols-2 gap-6 items-center">
                    <div class="text-center space-y-2.5">
                        <span class="inline-flex items-center gap-1.5 bg-white px-3 py-1 rounded-full text-[11px] font-black text-indigo-700 border border-indigo-200">
                            <span class="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span> LIVE AUTO-VERIFYING...
                        </span>
                        <img src="https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={{ pending_qr }}" class="w-44 h-44 mx-auto rounded-2xl border-4 border-white shadow-lg" alt="QR">
                        <div class="text-base font-black text-slate-900">Pay ₹{{ "%.2f"|format(pending_tx.amount) }}</div>
                        <div class="text-[11px] font-bold text-slate-600">UPI ID: <b class="font-mono text-indigo-700">{{ upis.primary }}</b></div>
                        <div class="flex flex-wrap justify-center gap-2 pt-1">
                            <a href="{{ pending_uri }}" class="btn-4d btn-emerald px-3 py-1.5 text-[11px]">📲 Open UPI App</a>
                            <a href="paytmmp://pay?pa={{ upis.map.paytm }}&pn=PranavSMM&am={{ pending_tx.amount }}&cu=INR" class="btn-4d btn-sky px-3 py-1.5 text-[11px]">Paytm</a>
                            <a href="phonepe://pay?pa={{ upis.map.phonepe }}&pn=PranavSMM&am={{ pending_tx.amount }}&cu=INR" class="btn-4d btn-purple px-3 py-1.5 text-[11px]">PhonePe</a>
                        </div>
                    </div>
                    <div class="bg-white p-5 rounded-2xl border-2 border-slate-200 space-y-3">
                        <h3 class="text-sm font-black text-slate-900">⚡ Instant UTR Auto-Verify</h3>
                        <p class="text-xs font-bold text-slate-500">Paytm/BharatPe API से यह पेज हर 3 सेकंड में अपने आप चेक हो रहा है। या नीचे 12-अंकों का UTR डालकर तुरंत बैलेंस पाएं:</p>
                        <form method="POST" action="/dashboard/verify-utr" class="space-y-3">
                            <input type="hidden" name="tx_id" value="{{ pending_tx.tx_id }}">
                            <input type="text" name="utr" pattern="\\d{12}" maxlength="12" required placeholder="Enter 12-Digit UTR Number" class="input-4d text-sm">
                            <button type="submit" class="w-full btn-4d btn-emerald py-3 text-xs">✅ Verify & Add ₹{{ pending_tx.amount|int }} Now</button>
                        </form>
                    </div>
                </div>
                {% endif %}
            </div>
        </div>

        <!-- PANE 4: PLANS & KEYS -->
        <div id="pane-plans" class="tab-pane hidden space-y-6">
            <div class="card-4d p-6">
                <h2 class="text-xl font-black text-slate-900">🎟️ Select Plan (One-Time vs Auto-Subscription)</h2>
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
                    {% for k, p in plans.items() %}
                    <div class="card-4d p-5 flex flex-col justify-between">
                        <div>
                            <span class="bg-indigo-100 text-indigo-700 text-[10px] font-black px-2.5 py-1 rounded-full">{{ p.badge }}</span>
                            <h3 class="text-base font-black text-slate-900 mt-2">{{ p.label }}</h3>
                            <div class="text-2xl font-black text-indigo-600 mt-1">₹{{ p.price|int }}</div>
                            <div class="text-[11px] font-bold text-slate-500 mt-2">🔄 Auto-Sub Min Wallet: ₹{{ p.min_sub_wallet|int }}</div>
                        </div>
                        <button type="button" onclick="openPlanModal('{{ k }}', '{{ p.label }}', {{ p.price|int }}, {{ p.min_sub_wallet|int }})" class="mt-4 w-full btn-4d btn-purple py-2.5 text-xs">⚡ Activate</button>
                    </div>
                    {% endfor %}
                </div>
            </div>
            <div class="card-4d p-6">
                <h3 class="text-base font-black text-slate-900 mb-3">🔑 My License Keys</h3>
                {% for k in my_keys %}
                    <div class="p-3 mb-2 rounded-xl bg-slate-50 border border-slate-200 flex justify-between items-center text-xs font-bold">
                        <span class="font-mono font-black text-indigo-700 select-all">{{ k.key_code }} ({{ k.label }})</span>
                        <span>{{ 'Used' if k.is_used else '🟢 Ready' }}</span>
                    </div>
                {% else %}
                    <p class="text-xs font-bold text-slate-400">कोई Key नहीं है।</p>
                {% endfor %}
            </div>
        </div>

        <!-- PANE 5: CHILD BOTS -->
        <div id="pane-bots" class="tab-pane hidden">
            <div class="card-4d p-6">
                <h2 class="text-lg font-black text-slate-900 mb-3">🤖 Launch 24×7 Child Bot</h2>
                <form method="POST" action="/dashboard/create-bot" class="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <input type="text" name="bot_token" required placeholder="BotFather Token" class="input-4d text-sm">
                    <input type="text" name="upi_id" required placeholder="Your UPI ID" class="input-4d text-sm">
                    <button type="submit" class="btn-4d btn-purple py-3 text-xs">🚀 Start Child Bot Now</button>
                </form>
            </div>
        </div>
    </main>

    <!-- MODAL -->
    <div id="plan_modal" class="fixed inset-0 bg-slate-900/50 backdrop-blur-xs z-50 hidden flex items-center justify-center p-4">
        <div class="card-4d p-6 max-w-md w-full">
            <div class="flex justify-between items-center pb-3 border-b border-slate-200">
                <h3 id="pm_title" class="text-lg font-black">Select Mode</h3>
                <button onclick="document.getElementById('plan_modal').classList.add('hidden')" class="w-8 h-8 rounded-lg bg-rose-100 text-rose-600 font-black">✕</button>
            </div>
            <form method="POST" action="/dashboard/buy-plan" class="mt-4 space-y-3">
                <input type="hidden" name="plan_key" id="pm_key" value="30">
                <button type="submit" name="buy_mode" value="onetime" class="w-full text-left p-3.5 rounded-2xl border-2 border-indigo-300 bg-indigo-50 flex justify-between items-center">
                    <div>
                        <div class="font-black text-xs text-indigo-950">⚡ 1. तुरंत एक बार लें (One-Time)</div>
                        <div class="text-[10px] font-bold text-indigo-700">सिर्फ एक बार पैसे कटेंगे।</div>
                    </div>
                    <span id="pm_one" class="font-black text-sm text-indigo-700">₹49</span>
                </button>
                <button type="submit" name="buy_mode" value="subscription" class="w-full text-left p-3.5 rounded-2xl border-2 border-emerald-300 bg-emerald-50 flex justify-between items-center">
                    <div>
                        <div class="font-black text-xs text-emerald-950">🔄 2. ऑटो-सब्सक्रिप्शन (Auto-Renew)</div>
                        <div class="text-[10px] font-bold text-emerald-700">वॉलेट में दोगुना बैलेंस (Min ₹100 / 2x) जरूरी!</div>
                        <div id="pm_sub" class="text-[11px] font-black text-emerald-800">₹49</div>
                    </div>
                    <span class="bg-emerald-600 text-white text-[10px] font-black px-2 py-1 rounded">AUTO</span>
                </button>
            </form>
        </div>
    </div>
</body>
</html>
"""

# ==========================================
# 👑 4D PURE WHITE GRANDMASTER ADMIN PANEL
# ==========================================
ADMIN_4D_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>👑 Pranav Ji 4D Master Admin</title>
    """ + STYLE_4D + """
</head>
<body class="min-h-screen pb-16">
    <header class="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b-2 border-slate-200 px-4 sm:px-6 py-3.5 shadow-xs">
        <div class="max-w-7xl mx-auto flex flex-wrap justify-between items-center gap-3">
            <div class="flex items-center gap-3">
                <div class="w-11 h-11 rounded-2xl btn-amber flex items-center justify-center text-xl">👑</div>
                <div>
                    <h1 class="text-lg font-black text-slate-900">प्रणव जी — 4D Grandmaster Admin</h1>
                    <p class="text-[11px] font-extrabold text-emerald-600">🔒 Secret URL: /{{ admin_slug }} (100% Hidden from Users)</p>
                </div>
            </div>
            <div class="flex flex-wrap items-center gap-2">
                <button id="btn-adm_upi" onclick="switchTab('adm_upi')" class="t-btn btn-4d btn-purple px-3.5 py-2 text-xs">💳 All UPI & Auto-Verify</button>
                <button id="btn-adm_tx" onclick="switchTab('adm_tx')" class="t-btn btn-4d btn-clean px-3.5 py-2 text-xs">💰 Payments & Users</button>
                <button id="btn-adm_keys" onclick="switchTab('adm_keys')" class="t-btn btn-4d btn-clean px-3.5 py-2 text-xs">🎟️ Keys & Services</button>
                <button id="btn-adm_sec" onclick="switchTab('adm_sec')" class="t-btn btn-4d btn-clean px-3.5 py-2 text-xs">🔐 Security & URL</button>
                <a href="/{{ admin_slug }}/logout" class="btn-4d btn-rose px-3.5 py-2 text-xs">🚪 Logout</a>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 sm:px-6 py-7 space-y-6">
        {% if msg %}<div class="card-4d p-4 border-l-8 border-l-emerald-500 bg-emerald-50 text-emerald-900 font-extrabold text-sm">{{ msg }}</div>{% endif %}

        <!-- 4D Admin Stats -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="card-4d p-5">
                <div class="text-[11px] font-extrabold text-slate-400">WEB USERS</div>
                <div class="text-3xl font-black text-indigo-600 mt-1">{{ web_users|length }}</div>
            </div>
            <div class="card-4d p-5">
                <div class="text-[11px] font-extrabold text-slate-400">CHILD BOTS</div>
                <div class="text-3xl font-black text-purple-600 mt-1">{{ total_bots }}</div>
            </div>
            <div class="card-4d p-5">
                <div class="text-[11px] font-extrabold text-slate-400">ACTIVE GATEWAY</div>
                <div class="text-2xl font-black text-emerald-600 mt-1 uppercase">{{ cfg.active_gw }}</div>
            </div>
            <div class="card-4d p-5">
                <div class="text-[11px] font-extrabold text-slate-400">AUTO-VERIFY ENGINE</div>
                <div class="text-xl font-black text-amber-600 mt-1">{{ '🟢 ON (INSTANT)' if cfg.auto_verify_utr=='1' else '🟡 MANUAL MODE' }}</div>
            </div>
        </div>

        <!-- ADMIN TAB 1: ALL UPI GATEWAYS & AUTO-VERIFY HUB -->
        <div id="pane-adm_upi" class="tab-pane space-y-6">
            <div class="card-4d p-6 sm:p-8">
                <h2 class="text-xl font-black text-slate-900 mb-1">💳 All-UPI Gateways & Auto-Verification Control</h2>
                <p class="text-xs font-bold text-slate-500 mb-5">यहाँ से Paytm, BharatPe, FamPay, PhonePe, Google Pay, Amazon Pay—सारी UPI IDs और Auto-Verify कंट्रोल करें:</p>
                <form method="POST" action="/{{ admin_slug }}/action" class="space-y-4">
                    <input type="hidden" name="act" value="save_upis">
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-xs font-extrabold text-slate-700 mb-1">PRIMARY ACTIVE UPI GATEWAY (वेब + बॉट QR के लिए)</label>
                            <select name="active_gw" class="input-4d text-sm">
                                <option value="paytm" {{ 'selected' if cfg.active_gw=='paytm' else '' }}>💙 Paytm Business QR</option>
                                <option value="bharatpe" {{ 'selected' if cfg.active_gw=='bharatpe' else '' }}>💚 BharatPe Merchant</option>
                                <option value="fampay" {{ 'selected' if cfg.active_gw=='fampay' else '' }}>🧡 FamPay Direct UPI</option>
                                <option value="phonepe" {{ 'selected' if cfg.active_gw=='phonepe' else '' }}>💜 PhonePe Merchant</option>
                                <option value="gpay" {{ 'selected' if cfg.active_gw=='gpay' else '' }}>❤️ Google Pay Business</option>
                                <option value="amazon" {{ 'selected' if cfg.active_gw=='amazon' else '' }}>💛 Amazon Pay UPI</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-extrabold text-slate-700 mb-1">UTR & API VERIFICATION MODE</label>
                            <select name="auto_verify_utr" class="input-4d text-sm">
                                <option value="1" {{ 'selected' if cfg.auto_verify_utr=='1' else '' }}>🟢 100% Auto-Verify (API + Instant UTR Credit)</option>
                                <option value="0" {{ 'selected' if cfg.auto_verify_utr=='0' else '' }}>🟡 Manual Admin Approval Only</option>
                            </select>
                        </div>
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
                        <div>
                            <label class="block text-[11px] font-extrabold text-indigo-700 mb-1">PAYTM UPI ID</label>
                            <input type="text" name="upi_paytm" value="{{ cfg.upi_paytm }}" class="input-4d text-xs">
                        </div>
                        <div>
                            <label class="block text-[11px] font-extrabold text-indigo-700 mb-1">PAYTM MERCHANT ID (MID)</label>
                            <input type="text" name="paytm_mid" value="{{ cfg.paytm_mid }}" class="input-4d text-xs">
                        </div>
                        <div>
                            <label class="block text-[11px] font-extrabold text-amber-700 mb-1">FAMPAY UPI ID</label>
                            <input type="text" name="upi_fampay" value="{{ cfg.upi_fampay }}" class="input-4d text-xs">
                        </div>
                        <div>
                            <label class="block text-[11px] font-extrabold text-emerald-700 mb-1">BHARATPE UPI ID</label>
                            <input type="text" name="upi_bharatpe" value="{{ cfg.upi_bharatpe }}" class="input-4d text-xs">
                        </div>
                        <div>
                            <label class="block text-[11px] font-extrabold text-emerald-700 mb-1">BHARATPE MID (Optional)</label>
                            <input type="text" name="bharatpe_mid" value="{{ cfg.bharatpe_mid }}" class="input-4d text-xs">
                        </div>
                        <div>
                            <label class="block text-[11px] font-extrabold text-emerald-700 mb-1">BHARATPE API TOKEN (Optional)</label>
                            <input type="text" name="bharatpe_token" value="{{ cfg.bharatpe_token }}" class="input-4d text-xs">
                        </div>
                        <div>
                            <label class="block text-[11px] font-extrabold text-purple-700 mb-1">PHONEPE UPI ID</label>
                            <input type="text" name="upi_phonepe" value="{{ cfg.upi_phonepe }}" class="input-4d text-xs">
                        </div>
                        <div>
                            <label class="block text-[11px] font-extrabold text-rose-700 mb-1">GOOGLE PAY UPI ID</label>
                            <input type="text" name="upi_gpay" value="{{ cfg.upi_gpay }}" class="input-4d text-xs">
                        </div>
                        <div>
                            <label class="block text-[11px] font-extrabold text-sky-700 mb-1">AMAZON PAY UPI ID</label>
                            <input type="text" name="upi_amazon" value="{{ cfg.upi_amazon }}" class="input-4d text-xs">
                        </div>
                    </div>
                    <button type="submit" class="w-full btn-4d btn-emerald py-3.5 text-sm">💾 Save All UPI Gateways & Auto-Verify Config</button>
                </form>
            </div>
        </div>

        <!-- ADMIN TAB 2: PAYMENTS, UTR MANAGER & USER BALANCE -->
        <div id="pane-adm_tx" class="tab-pane hidden space-y-6">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div class="card-4d p-6">
                    <h3 class="text-lg font-black text-slate-900 mb-3">👥 Manage Web User Wallet & Password</h3>
                    <form method="POST" action="/{{ admin_slug }}/action" class="space-y-3">
                        <input type="hidden" name="act" value="manage_web_user">
                        <input type="email" name="email" required placeholder="User Email Address" class="input-4d text-xs">
                        <div class="grid grid-cols-2 gap-3">
                            <input type="number" name="amount" step="0.01" value="1000" placeholder="Add/Deduct ₹ Balance" class="input-4d text-xs">
                            <input type="text" name="new_pwd" placeholder="Reset Password (Optional)" class="input-4d text-xs">
                        </div>
                        <button type="submit" class="w-full btn-4d btn-purple py-3 text-xs">✅ Update Web User Immediately</button>
                    </form>
                </div>
                <div class="card-4d p-6">
                    <h3 class="text-lg font-black text-slate-900 mb-3">🤖 Add Balance to Telegram Bot User</h3>
                    <form method="POST" action="/{{ admin_slug }}/action" class="space-y-3">
                        <input type="hidden" name="act" value="manage_bot_user">
                        <input type="number" name="tg_uid" required placeholder="Telegram User ID (Ex: 8585055903)" class="input-4d text-xs">
                        <input type="number" name="amount" step="0.01" value="1000" required placeholder="Amount (₹)" class="input-4d text-xs">
                        <button type="submit" class="w-full btn-4d btn-sky py-3 text-xs">➕ Credit Bot User Wallet</button>
                    </form>
                </div>
            </div>

            <div class="card-4d p-6">
                <h3 class="text-lg font-black text-slate-900 mb-4">💰 Recent Deposits & Manual UTR Approval</h3>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs font-bold">
                        <thead>
                            <tr class="border-b-2 border-slate-200 text-slate-400">
                                <th class="p-2">Order ID</th><th class="p-2">User</th><th class="p-2">Amount</th><th class="p-2">UTR</th><th class="p-2">Status</th><th class="p-2">Action</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100">
                            {% for t in recent_txs %}
                            <tr>
                                <td class="p-2 font-mono font-black">{{ t.tx_id }}</td>
                                <td class="p-2">Web:{{ t.web_user_id }} / TG:{{ t.user_id }}</td>
                                <td class="p-2 text-emerald-600 font-black">₹{{ "%.2f"|format(t.amount) }}</td>
                                <td class="p-2 font-mono">{{ t.bank_utr or 'Pending' }}</td>
                                <td class="p-2">{{ t.status|upper }}</td>
                                <td class="p-2">
                                    {% if t.status != 'completed' %}
                                    <form method="POST" action="/{{ admin_slug }}/action">
                                        <input type="hidden" name="act" value="approve_tx">
                                        <input type="hidden" name="tx_id" value="{{ t.tx_id }}">
                                        <button type="submit" class="btn-4d btn-emerald px-3 py-1 text-[10px]">✅ Approve</button>
                                    </form>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- ADMIN TAB 3: LICENSE KEYS & SMM SERVICES -->
        <div id="pane-adm_keys" class="tab-pane hidden grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div class="card-4d p-6">
                <h3 class="text-lg font-black text-slate-900 mb-3">🎟️ Instant License Key Generator</h3>
                <form method="POST" action="/{{ admin_slug }}/action" class="space-y-3">
                    <input type="hidden" name="act" value="gen_key">
                    <select name="duration" class="input-4d text-sm">
                        <option value="7">7 Days Trial Pro (₹49)</option>
                        <option value="30" selected>1 Month Elite (₹149)</option>
                        <option value="90">3 Months Master (₹399)</option>
                        <option value="36500">👑 Lifetime God Mode (₹999)</option>
                    </select>
                    <button type="submit" class="w-full btn-4d btn-purple py-3 text-xs">⚡ Generate Key Now</button>
                </form>
                {% if gen_key %}
                    <div class="mt-4 p-4 rounded-2xl bg-indigo-50 border-2 border-indigo-300 text-center font-mono font-black text-sm select-all">{{ gen_key }}</div>
                {% endif %}
            </div>

            <div class="card-4d p-6">
                <h3 class="text-lg font-black text-slate-900 mb-3">⚙️ Add New SMM Service</h3>
                <form method="POST" action="/{{ admin_slug }}/action" class="space-y-3">
                    <input type="hidden" name="act" value="add_service">
                    <input type="text" name="srv_name" required placeholder="Service Name (Ex: Instagram VIP Likes)" class="input-4d text-xs">
                    <input type="number" name="rate" step="0.1" required placeholder="Rate per 1000 (₹)" class="input-4d text-xs">
                    <button type="submit" class="w-full btn-4d btn-emerald py-3 text-xs">➕ Add Service to Web & Bot</button>
                </form>
            </div>
        </div>

        <!-- ADMIN TAB 4: SECURITY VAULT (CHANGE ADMIN URL & PASSWORD) -->
        <div id="pane-adm_sec" class="tab-pane hidden">
            <div class="card-4d p-6 sm:p-8 max-w-2xl mx-auto">
                <h2 class="text-xl font-black text-slate-900 mb-1">🔐 Security Vault: Change Admin URL & Password</h2>
                <p class="text-xs font-bold text-slate-500 mb-5">यहाँ से आप अपना सीक्रेट एडमिन लिंक (`/{{ admin_slug }}`), यूजरनेम और पासवर्ड जब चाहें बदल सकते हैं!</p>
                <form method="POST" action="/{{ admin_slug }}/action" class="space-y-4">
                    <input type="hidden" name="act" value="update_security">
                    <div>
                        <label class="block text-xs font-extrabold text-slate-700 mb-1">NEW SECRET ADMIN URL SLUG (बिना / के लिखें)</label>
                        <input type="text" name="new_slug" value="{{ admin_slug }}" required class="input-4d text-sm">
                    </div>
                    <div>
                        <label class="block text-xs font-extrabold text-slate-700 mb-1">NEW ADMIN USERNAME</label>
                        <input type="text" name="new_user" value="{{ admin_user }}" required class="input-4d text-sm">
                    </div>
                    <div>
                        <label class="block text-xs font-extrabold text-slate-700 mb-1">NEW ADMIN PASSWORD</label>
                        <input type="password" name="new_pass" placeholder="Enter New Strong Password" class="input-4d text-sm">
                    </div>
                    <button type="submit" class="w-full btn-4d btn-rose py-3.5 text-sm">🔒 Update Secret URL & Admin Password</button>
                </form>
            </div>
        </div>
    </main>
</body>
</html>
"""

# ==========================================
# 🌐 WEB ROUTES & CONTROLLERS
# ==========================================
def get_master_bot_uname():
    r = fetch_query("SELECT bot_username FROM child_bots WHERE bot_id=0", fetchone=True)
    return r["bot_username"] if r else "PranavMasterBot"

@app.route('/ping')
def ping():
    return jsonify({"status": "alive", "engine": "Pranav 4D Grandmaster"})

@app.route('/api/payment/status/<tx_id>')
def api_pay_status(tx_id):
    tx = fetch_query("SELECT * FROM transactions WHERE tx_id=?", (tx_id,), fetchone=True)
    if not tx:
        return jsonify({"status": "not_found"})
    if tx["status"] == "completed":
        return jsonify({"status": "completed"})
    ok, utr = check_paytm_gateway(tx_id, tx["amount"])
    if not ok:
        ok, utr = check_bharatpe_gateway(tx["amount"])
    if ok:
        complete_tx_and_notify(tx_id, utr)
        return jsonify({"status": "completed"})
    return jsonify({"status": "pending"})

@app.route('/api/webhook/upi', methods=['POST', 'GET'])
def webhook_upi():
    data = request.json or request.form or request.args
    if data.get("secret") != get_cfg("webhook_secret", "pranav_auto_99"):
        return jsonify({"error": "denied"}), 403
    amt = float(data.get("amount", 0))
    utr = str(data.get("utr", f"AUTO{int(time.time())}"))
    p = fetch_query("SELECT tx_id FROM transactions WHERE status='pending' AND amount=? ORDER BY created_at DESC LIMIT 1", (amt,), fetchone=True)
    if p:
        complete_tx_and_notify(p["tx_id"], utr)
        return jsonify({"status": "verified"})
    return jsonify({"status": "no_match"})

@app.route('/')
def home():
    return render_template_string(HOME_HTML, plans=PLANS_CATALOG, master_bot_uname=get_master_bot_uname())

@app.route('/login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        em = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "").strip()
        u = fetch_query("SELECT * FROM web_users WHERE email=? AND password_hash=?", (em, hash_pwd(pw)), fetchone=True)
        if u:
            session.permanent = True
            session['user_id'] = u["id"]
            return redirect(url_for('user_dashboard'))
        return render_template_string(AUTH_HTML, title="User Login", subtitle="Access your 4D Panel", btn_text="Login", mode="login", error="❌ ईमेल या पासवर्ड गलत है!", master_bot_uname=get_master_bot_uname())
    return render_template_string(AUTH_HTML, title="User Login", subtitle="Access your 4D Panel", btn_text="Login", mode="login", master_bot_uname=get_master_bot_uname())

@app.route('/register', methods=['GET', 'POST'])
def user_register():
    if request.method == 'POST':
        nm = request.form.get("name", "").strip()
        em = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "").strip()
        pin = request.form.get("recovery_pin", "1234").strip()
        if fetch_query("SELECT id FROM web_users WHERE email=?", (em,), fetchone=True):
            return render_template_string(AUTH_HTML, title="Create Account", subtitle="Join 4D Panel", btn_text="Register", mode="register", error="❌ यह ईमेल पहले से रजिस्टर है!", master_bot_uname=get_master_bot_uname())
        uid = execute_query("INSERT INTO web_users (name, email, password_hash, recovery_pin, balance) VALUES (?, ?, ?, ?, 0.0)", (nm, em, hash_pwd(pw), pin))
        session.permanent = True
        session['user_id'] = uid
        return redirect(url_for('user_dashboard'))
    return render_template_string(AUTH_HTML, title="Create Account", subtitle="Join 4D Panel", btn_text="Register", mode="register", master_bot_uname=get_master_bot_uname())

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_pwd():
    if request.method == 'POST':
        em = request.form.get("email", "").strip().lower()
        pin = request.form.get("recovery_pin", "").strip()
        npw = request.form.get("new_password", "").strip()
        u = fetch_query("SELECT id FROM web_users WHERE email=? AND recovery_pin=?", (em, pin), fetchone=True)
        if not u:
            return render_template_string(AUTH_HTML, title="Forgot Password", subtitle="Recover via 4-Digit PIN", btn_text="Reset Password", mode="forgot", error="❌ ईमेल या 4-अंकों का PIN गलत है!", master_bot_uname=get_master_bot_uname())
        execute_query("UPDATE web_users SET password_hash=? WHERE id=?", (hash_pwd(npw), u["id"]))
        return render_template_string(AUTH_HTML, title="User Login", subtitle="Password Updated!", btn_text="Login Now", mode="login", success="✅ आपका नया पासवर्ड सेट हो गया है!", master_bot_uname=get_master_bot_uname())
    return render_template_string(AUTH_HTML, title="Forgot Password", subtitle="Recover via 4-Digit PIN", btn_text="Reset Password", mode="forgot", master_bot_uname=get_master_bot_uname())

@app.route('/dashboard')
def user_dashboard():
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    user = fetch_query("SELECT * FROM web_users WHERE id=?", (session['user_id'],), fetchone=True)
    if not user:
        session.pop('user_id', None)
        return redirect(url_for('user_login'))
    upis = get_all_upis()
    ptx = fetch_query("SELECT * FROM transactions WHERE web_user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1", (user["id"],), fetchone=True)
    puri = f"upi://pay?pa={upis['primary']}&pn=PranavSMM&am={ptx['amount']:.2f}&cu=INR&tr={ptx['tx_id']}" if ptx else ""
    pqr = urllib.parse.quote(puri) if puri else ""
    return render_template_string(
        USER_DASH_HTML, user=user, upis=upis, pending_tx=ptx, pending_uri=puri, pending_qr=pqr,
        services=fetch_query("SELECT * FROM smm_services WHERE bot_id=0"),
        my_orders=fetch_query("SELECT * FROM smm_orders WHERE web_user_id=? ORDER BY id DESC LIMIT 12", (user["id"],)),
        my_keys=fetch_query("SELECT * FROM license_keys WHERE used_by_user_id=? ORDER BY created_at DESC", (user["id"],)),
        plans=PLANS_CATALOG, msg=session.pop('d_msg', None), err=session.pop('d_err', None), master_bot_uname=get_master_bot_uname()
    )

@app.route('/dashboard/create-qr', methods=['POST'])
def dash_create_qr():
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    amt = float(request.form.get("amount", 1000))
    tx_id = f"PSMM{int(time.time())}{random.randint(10,99)}"
    execute_query("INSERT INTO transactions (tx_id, web_user_id, amount, gateway, status) VALUES (?, ?, ?, ?, 'pending')",
                  (tx_id, session['user_id'], amt, get_cfg("active_gw", "paytm")))
    return redirect(url_for('user_dashboard') + "?tab=funds")

@app.route('/dashboard/verify-utr', methods=['POST'])
def dash_verify_utr():
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    tx_id = request.form.get("tx_id", "").strip()
    utr = request.form.get("utr", "").strip()
    if len(utr) != 12 or not utr.isdigit():
        session['d_err'] = "❌ 12-अंकों का सही UTR नंबर डालें!"
        return redirect(url_for('user_dashboard') + "?tab=funds")
    if fetch_query("SELECT tx_id FROM transactions WHERE bank_utr=? AND status='completed'", (utr,), fetchone=True):
        session['d_err'] = "❌ यह UTR पहले ही इस्तेमाल हो चुका है!"
        return redirect(url_for('user_dashboard') + "?tab=funds")
    if get_cfg("auto_verify_utr", "1") == "1":
        complete_tx_and_notify(tx_id, utr)
        session['d_msg'] = f"🎉 ऑटो-वेरिफिकेशन सफल! आपका बैलेंस वॉलेट में जुड़ गया है (UTR: {utr})।"
    else:
        execute_query("UPDATE transactions SET bank_utr=? WHERE tx_id=?", (utr, tx_id))
        session['d_msg'] = "⏳ UTR सबमिट हो गया! एडमिन अप्रूव होते ही बैलेंस जुड़ जाएगा।"
    return redirect(url_for('user_dashboard') + "?tab=funds")

@app.route('/dashboard/place-order', methods=['POST'])
def dash_place_order():
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    uid = session['user_id']
    srv = fetch_query("SELECT * FROM smm_services WHERE id=?", (int(request.form.get("service_id", 0)),), fetchone=True)
    qty = int(request.form.get("quantity", 100))
    link = request.form.get("link", "").strip()
    u = fetch_query("SELECT * FROM web_users WHERE id=?", (uid,), fetchone=True)
    chg = (qty / 1000.0) * float(srv["rate_per_1000"])
    if u["balance"] < chg:
        session['d_err'] = f"⚠️ वॉलेट बैलेंस कम है! चार्ज ₹{chg:.2f} है, पहले Add Funds करें।"
        return redirect(url_for('user_dashboard') + "?tab=funds")
    execute_query("UPDATE web_users SET balance = balance - ?, total_spent = total_spent + ? WHERE id=?", (chg, chg, uid))
    oid = execute_query("INSERT INTO smm_orders (web_user_id, service_name, link, quantity, charge) VALUES (?, ?, ?, ?, ?)", (uid, srv["service_name"], link, qty, chg))
    session['d_msg'] = f"🎉 Order #{oid} सफलतापूर्वक लग गया!"
    return redirect(url_for('user_dashboard') + "?tab=order")

@app.route('/dashboard/buy-plan', methods=['POST'])
def dash_buy_plan():
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    uid = session['user_id']
    p = PLANS_CATALOG.get(request.form.get("plan_key", "30"), PLANS_CATALOG["30"])
    mode = request.form.get("buy_mode", "onetime")
    u = fetch_query("SELECT * FROM web_users WHERE id=?", (uid,), fetchone=True)
    if mode == "subscription" and u["balance"] < p["min_sub_wallet"]:
        session['d_err'] = f"⚠️ ऑटो-सब्सक्रिप्शन के लिए वॉलेट में कम से कम ₹{p['min_sub_wallet']:.0f} (2x बैलेंस) होना जरूरी है!"
        return redirect(url_for('user_dashboard') + "?tab=funds")
    if mode == "onetime" and u["balance"] < p["price"]:
        session['d_err'] = f"⚠️ वॉलेट में ₹{p['price']:.0f} नहीं है! पहले Add Funds करें।"
        return redirect(url_for('user_dashboard') + "?tab=funds")
    is_sub = 1 if mode == "subscription" else 0
    exp = (datetime.datetime.now() + datetime.timedelta(days=p["days"])).strftime("%Y-%m-%d %H:%M:%S")
    k = f"PRANAV-{p['days']}D-{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))}"
    execute_query("UPDATE web_users SET balance = balance - ?, total_spent = total_spent + ?, auto_sub=?, active_plan=?, plan_price=?, plan_days=?, sub_expiry=? WHERE id=?",
                  (p["price"], p["price"], is_sub, p["label"], p["price"], p["days"], exp, uid))
    execute_query("INSERT INTO license_keys (key_code, duration_days, price, label, is_sub, used_by_user_id) VALUES (?, ?, ?, ?, ?, ?)",
                  (k, p["days"], p["price"], p["label"], is_sub, uid))
    session['d_msg'] = f"🎉 प्लान एक्टिवेट हो गया! आपकी Key: {k}"
    return redirect(url_for('user_dashboard') + "?tab=plans")

@app.route('/dashboard/create-bot', methods=['POST'])
def dash_create_bot():
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    tok = request.form.get("bot_token", "").strip()
    upi = request.form.get("upi_id", "").strip()
    try:
        chk = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=6).json()
    except:
        session['d_err'] = "❌ कनेक्शन एरर!"
        return redirect(url_for('user_dashboard') + "?tab=bots")
    if not chk.get("ok"):
        session['d_err'] = "❌ Invalid Bot Token!"
        return redirect(url_for('user_dashboard') + "?tab=bots")
    uname = chk["result"]["username"]
    bid = execute_query("INSERT INTO child_bots (owner_id, web_user_id, bot_token, bot_username, bot_name, upi_id, is_licensed, status) VALUES (?, ?, ?, ?, ?, ?, 0, 'active')",
                        (SUPER_ADMIN_ID, session['user_id'], tok, uname, chk["result"]["first_name"], upi))
    start_child_bot_thread(bid, SUPER_ADMIN_ID, tok, uname)
    session['d_msg'] = f"🚀 बॉट @{uname} 24×7 लाइव हो गया!"
    return redirect(url_for('user_dashboard') + "?tab=bots")

@app.route('/logout')
def user_logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

# ==========================================
# 👑 DYNAMIC SECRET ADMIN ROUTER
# ==========================================
@app.route('/<path:slug>', methods=['GET', 'POST'])
def secret_admin_router(slug):
    adm_slug = get_cfg("admin_slug", ENV_ADMIN_SLUG).strip("/")
    if slug == f"{adm_slug}/logout":
        session.pop('admin_logged', None)
        return redirect(f"/{adm_slug}")

    if slug == f"{adm_slug}/action" and request.method == 'POST':
        if not session.get('admin_logged'):
            return redirect(f"/{adm_slug}")
        act = request.form.get("act")
        if act == "save_upis":
            for k in ["active_gw", "auto_verify_utr", "upi_paytm", "paytm_mid", "upi_fampay", "upi_bharatpe", "bharatpe_mid", "bharatpe_token", "upi_phonepe", "upi_gpay", "upi_amazon"]:
                set_cfg(k, request.form.get(k, "").strip())
            execute_query("UPDATE child_bots SET upi_id=? WHERE bot_id=0", (get_all_upis()["primary"],))
            session['a_msg'] = "✅ सारे UPI Gateways और Auto-Verify सेटिंग्स सेव हो गईं!"
        elif act == "update_security":
            ns = request.form.get("new_slug", adm_slug).strip().strip("/")
            nu = request.form.get("new_user", "pranav").strip()
            np = request.form.get("new_pass", "").strip()
            if ns:
                set_cfg("admin_slug", ns)
            if nu:
                set_cfg("admin_user", nu)
            if np:
                set_cfg("admin_pass_hash", hash_pwd(np))
            session['a_msg'] = f"🔒 सिक्योरिटी अपडेट हो गई! नया लिंक: /{ns}"
            return redirect(f"/{ns}")
        elif act == "approve_tx":
            complete_tx_and_notify(request.form.get("tx_id", ""), "ADMIN-APPROVED")
            session['a_msg'] = "✅ पेमेंट अप्रूव हो गया!"
        elif act == "manage_web_user":
            em = request.form.get("email", "").strip().lower()
            amt = float(request.form.get("amount", 0) or 0)
            npw = request.form.get("new_pwd", "").strip()
            if amt != 0:
                execute_query("UPDATE web_users SET balance = balance + ? WHERE email=?", (amt, em))
            if npw:
                execute_query("UPDATE web_users SET password_hash=? WHERE email=?", (hash_pwd(npw), em))
            session['a_msg'] = f"✅ Web User ({em}) अपडेट हो गया!"
        elif act == "manage_bot_user":
            tuid = int(request.form.get("tg_uid", 0))
            amt = float(request.form.get("amount", 0))
            execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (0, ?, 'User')", (tuid,))
            execute_query("UPDATE bot_clients SET balance = balance + ? WHERE bot_id=0 AND user_id=?", (amt, tuid))
            session['a_msg'] = f"✅ Telegram User ({tuid}) में ₹{amt:.2f} जुड़ गया!"
        elif act == "gen_key":
            p = PLANS_CATALOG.get(request.form.get("duration", "30"), PLANS_CATALOG["30"])
            k = f"PRANAV-{p['days']}D-{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))}"
            execute_query("INSERT INTO license_keys (key_code, duration_days, price, label) VALUES (?, ?, ?, ?)", (k, p["days"], p["price"], p["label"]))
            session['a_key'] = k
            session['a_msg'] = "✅ नई License Key जनरेट हो गई!"
        elif act == "add_service":
            execute_query("INSERT INTO smm_services (bot_id, service_name, rate_per_1000) VALUES (0, ?, ?)",
                          (request.form.get("srv_name", "").strip(), float(request.form.get("rate", 50))))
            session['a_msg'] = "✅ नई SMM सर्विस जोड़ दी गई!"
        return redirect(f"/{adm_slug}")

    if slug != adm_slug:
        return abort(404)

    if request.method == 'POST':
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        if u == get_cfg("admin_user") and hash_pwd(p) == get_cfg("admin_pass_hash"):
            session.permanent = True
            session['admin_logged'] = True
            return redirect(f"/{adm_slug}")
        return render_template_string(AUTH_HTML, title="👑 Secret Master Login", subtitle="Pranav Ji Only", btn_text="Unlock 4D Admin", mode="admin", error="❌ गलत यूजरनेम या पासवर्ड!", master_bot_uname=get_master_bot_uname())

    if not session.get('admin_logged'):
        return render_template_string(AUTH_HTML, title="👑 Secret Master Login", subtitle="Pranav Ji Only", btn_text="Unlock 4D Admin", mode="admin", master_bot_uname=get_master_bot_uname())

    cfg_keys = ["active_gw", "auto_verify_utr", "upi_paytm", "paytm_mid", "upi_fampay", "upi_bharatpe", "bharatpe_mid", "bharatpe_token", "upi_phonepe", "upi_gpay", "upi_amazon"]
    cfg_data = {k: get_cfg(k) for k in cfg_keys}
    return render_template_string(
        ADMIN_4D_HTML, admin_slug=adm_slug, admin_user=get_cfg("admin_user"), cfg=cfg_data,
        web_users=fetch_query("SELECT * FROM web_users ORDER BY id DESC"),
        total_bots=fetch_query("SELECT COUNT(*) as c FROM child_bots WHERE bot_id > 0", fetchone=True)["c"],
        recent_txs=fetch_query("SELECT * FROM transactions ORDER BY created_at DESC LIMIT 20"),
        gen_key=session.pop('a_key', None), msg=session.pop('a_msg', None)
    )

# ==========================================
# 🤖 TELEGRAM BOT ENGINE (AUTO-VERIFY + ALL FEATURES)
# ==========================================
def safe_send(bot, cid, txt, reply_markup=None):
    try:
        return bot.send_message(cid, txt, reply_markup=reply_markup)
    except:
        pass

def safe_edit(bot, txt, cid, mid, reply_markup=None):
    try:
        return bot.edit_message_text(txt, cid, mid, reply_markup=reply_markup)
    except:
        return safe_send(bot, cid, txt, reply_markup=reply_markup)

def get_bot_upi(bot_id):
    if bot_id == 0:
        return get_all_upis()["primary"]
    r = fetch_query("SELECT upi_id FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
    return r["upi_id"] if (r and r["upi_id"]) else get_all_upis()["primary"]

def is_bot_active(bot_id):
    if bot_id == 0:
        return True, "👑 Lifetime God Master"
    r = fetch_query("SELECT is_licensed, subscription_expiry FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
    if not r or r["is_licensed"] == 0:
        return False, "❌ License Not Activated! (/admin में जाकर Key डालें)"
    return True, f"🟢 Active ({r['subscription_expiry']})"

def get_user_main_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("💳 My Wallet", callback_data="u_bal"), types.InlineKeyboardButton("➕ Add Funds (Auto-UPI)", callback_data="u_dep"))
    m.add(types.InlineKeyboardButton("🎟️ Buy Plan / Key", callback_data="u_plans"), types.InlineKeyboardButton("🛒 Order SMM", callback_data="u_ord"))
    m.add(types.InlineKeyboardButton("🗓️ History", callback_data="u_hist"), types.InlineKeyboardButton("🤖 Create Child Bot", callback_data="u_cyob"))
    m.add(types.InlineKeyboardButton("🌐 Open PranavSMM.online ↗", url="https://pranavsmm.online"))
    return m

def get_owner_panel(is_master=False):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("💳 Change UPI ID", callback_data="a_payment"), types.InlineKeyboardButton("⚙️ Add SMM Service", callback_data="a_services"))
    m.add(types.InlineKeyboardButton("👥 Add User Balance", callback_data="a_users"), types.InlineKeyboardButton("🔑 Activate Key", callback_data="a_license_info"))
    if is_master:
        m.add(types.InlineKeyboardButton("🎟️ Generate Free Key", callback_data="adm_gen_menu"))
    m.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="u_back_main"))
    return m

def send_bot_qr(bot, bot_id, uid, cid, mid, amt):
    tx_id = f"BOT{int(time.time())}{random.randint(10,99)}"
    t_upi = get_bot_upi(bot_id)
    execute_query("INSERT INTO transactions (tx_id, bot_id, user_id, amount, status) VALUES (?, ?, ?, ?, 'pending')", (tx_id, bot_id, uid, amt))
    user_states[f"{bot_id}_{uid}"] = {"step": "wait_utr", "tx_id": tx_id}
    qr = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(f'upi://pay?pa={t_upi}&pn=PranavSMM&am={amt:.2f}&cu=INR&tr={tx_id}')}"
    try:
        bot.delete_message(cid, mid)
    except:
        pass
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("⚡ Auto-Verify Payment Now", callback_data=f"chk_tx_{tx_id}"),
        types.InlineKeyboardButton("🔢 Enter 12-Digit UTR", callback_data=f"sub_utr_{tx_id}"),
        types.InlineKeyboardButton("🔙 Cancel", callback_data="u_back_main")
    )
    bot.send_photo(cid, qr, caption=f"⚡ **𝗔𝗨𝗧𝗢-𝗩𝗘𝗥𝗜𝗙𝗬 𝗨𝗣𝗜 𝗚𝗔𝗧𝗘𝗪𝗔𝗬**\n\n💵 Amount: ₹{amt:.2f}\n🏦 UPI: `{t_upi}`\n🆔 Order: `{tx_id}`\n\n📲 पेमेंट करते ही बॉट अपने आप वेरिफाई कर लेगा, या नीचे **Auto-Verify** दबाएं / 12-अंकों का UTR भेजें!", reply_markup=kb, parse_mode="Markdown")

def handle_user_callbacks(bot, bot_id, call):
    uid, cid, mid, data = call.from_user.id, call.message.chat.id, call.message.message_id, call.data
    execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)", (bot_id, uid, call.from_user.username or "User"))

    if data == "u_back_main":
        user_states.pop(f"{bot_id}_{uid}", None)
        safe_edit(bot, "✨ 𝗣𝗥𝗔𝗡𝗔𝗩 𝟰𝗗 𝗦𝗠𝗠 & 𝗨𝗣𝗜 𝗕𝗢𝗧 ✨", cid, mid, reply_markup=get_user_main_menu())
    elif data == "u_bal":
        r = fetch_query("SELECT * FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        safe_edit(bot, f"💳 **𝗪𝗔𝗟𝗟𝗘𝗧**\n\n💰 Balance: ₹{(r['balance'] if r else 0):.2f}\n🎖️ Plan: {r['sub_plan'] if r else 'None'}", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"), types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")))
    elif data == "u_dep":
        act, rsn = is_bot_active(bot_id)
        if not act:
            return safe_edit(bot, rsn, cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")))
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton("⚡ ₹100", callback_data="qdep_100"), types.InlineKeyboardButton("⚡ ₹500", callback_data="qdep_500"), types.InlineKeyboardButton("🔥 ₹1000", callback_data="qdep_1000"), types.InlineKeyboardButton("💎 ₹2000", callback_data="qdep_2000"))
        kb.add(types.InlineKeyboardButton("✍️ Custom Amount", callback_data="c_custom_amt"), types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
        safe_edit(bot, "💰 **𝗦𝗘𝗟𝗘𝗖𝗧 𝗔𝗠𝗢𝗨𝗡𝗧:**", cid, mid, reply_markup=kb)
    elif data.startswith("qdep_"):
        send_bot_qr(bot, bot_id, uid, cid, mid, float(data.replace("qdep_", "")))
    elif data == "c_custom_amt":
        user_states[f"{bot_id}_{uid}"] = "wait_custom_dep"
        safe_edit(bot, "💵 अमाउंट चैट में लिखकर भेजें (जैसे `200`, `1500`):", cid, mid)
    elif data.startswith("chk_tx_"):
        tx_id = data.replace("chk_tx_", "")
        tx = fetch_query("SELECT * FROM transactions WHERE tx_id=?", (tx_id,), fetchone=True)
        if tx and tx["status"] == "completed":
            return safe_send(bot, cid, "✅ पेमेंट पहले ही जुड़ चुका है!", reply_markup=get_user_main_menu())
        ok, utr = check_paytm_gateway(tx_id, tx["amount"])
        if not ok:
            ok, utr = check_bharatpe_gateway(tx["amount"])
        if ok:
            complete_tx_and_notify(tx_id, utr)
            return
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_utr", "tx_id": tx_id}
        safe_send(bot, cid, "🔢 तुरंत ऑटो-वेरिफाई करने के लिए अपना **12-अंकों का UTR / Ref No.** अभी चैट में भेजें:")
    elif data.startswith("sub_utr_"):
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_utr", "tx_id": data.replace("sub_utr_", "")}
        safe_send(bot, cid, "🔢 अपना 12-अंकों का UTR नंबर चैट में भेजें:")
    elif data == "u_plans":
        kb = types.InlineKeyboardMarkup(row_width=1)
        for k, p in PLANS_CATALOG.items():
            kb.add(types.InlineKeyboardButton(f"💎 {p['label']} — ₹{int(p['price'])}", callback_data=f"selplan_{k}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
        safe_edit(bot, "🎟️ **𝗦𝗘𝗟𝗘𝗖𝗧 𝗣𝗟𝗔𝗡:**", cid, mid, reply_markup=kb)
    elif data.startswith("selplan_"):
        pk = data.replace("selplan_", "")
        p = PLANS_CATALOG.get(pk, PLANS_CATALOG["30"])
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton(f"⚡ 1. One-Time (₹{int(p['price'])})", callback_data=f"buyplan_one_{pk}"),
            types.InlineKeyboardButton(f"🔄 2. Auto-Sub (Min Wallet ₹{int(p['min_sub_wallet'])})", callback_data=f"buyplan_sub_{pk}"),
            types.InlineKeyboardButton("🔙 Back", callback_data="u_plans")
        )
        safe_edit(bot, f"💎 {p['label']}\nअपना मोड चुनें:", cid, mid, reply_markup=kb)
    elif data.startswith("buyplan_"):
        _, mode, pk = data.split("_")
        p = PLANS_CATALOG.get(pk, PLANS_CATALOG["30"])
        r = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        bal = r["balance"] if r else 0.0
        if mode == "sub" and bal < p["min_sub_wallet"]:
            return bot.answer_callback_query(call.id, f"⚠️ ऑटो-सब्सक्रिप्शन के लिए वॉलेट में ₹{int(p['min_sub_wallet'])} होना जरूरी है!", show_alert=True)
        if mode == "one" and bal < p["price"]:
            return bot.answer_callback_query(call.id, f"⚠️ वॉलेट में ₹{int(p['price'])} नहीं है! पहले Add Funds करें।", show_alert=True)
        is_sub = 1 if mode == "sub" else 0
        exp = (datetime.datetime.now() + datetime.timedelta(days=p["days"])).strftime("%Y-%m-%d %H:%M:%S")
        k = f"PRANAV-{p['days']}D-{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))}"
        execute_query("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ?, auto_sub=?, sub_plan=?, sub_expiry=? WHERE bot_id=? AND user_id=?",
                      (p["price"], p["price"], is_sub, p["label"], exp, bot_id, uid))
        execute_query("INSERT INTO license_keys (key_code, duration_days, price, label, is_sub, used_by_user_id) VALUES (?, ?, ?, ?, ?, ?)",
                      (k, p["days"], p["price"], p["label"], is_sub, uid))
        safe_edit(bot, f"🎉 Plan Activated!\n🔑 Key: `{k}`", cid, mid, reply_markup=get_user_main_menu())
    elif data == "u_ord":
        srvs = fetch_query("SELECT * FROM smm_services WHERE bot_id=? OR bot_id=0", (bot_id,))
        kb = types.InlineKeyboardMarkup(row_width=1)
        for s in srvs:
            kb.add(types.InlineKeyboardButton(f"{s['service_name']} (₹{s['rate_per_1000']}/1k)", callback_data=f"ordsrv_{s['id']}"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
        safe_edit(bot, "🛒 **𝗦𝗘𝗟𝗘𝗖𝗧 𝗦𝗘𝗥𝗩𝗜𝗖𝗘:**", cid, mid, reply_markup=kb)
    elif data.startswith("ordsrv_"):
        srv = fetch_query("SELECT * FROM smm_services WHERE id=?", (int(data.replace("ordsrv_", "")),), fetchone=True)
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_ord_link", "srv_name": srv["service_name"], "rate": srv["rate_per_1000"]}
        safe_edit(bot, f"🛒 {srv['service_name']}\n🔗 लिंक चैट में भेजें:", cid, mid)
    elif data == "u_hist":
        ords = fetch_query("SELECT * FROM smm_orders WHERE bot_id=? AND user_id=? ORDER BY id DESC LIMIT 8", (bot_id, uid))
        txt = "🗓️ **𝗢𝗥𝗗𝗘𝗥𝗦:**\n\n" + ("\n".join([f"• #{o['id']} {o['service_name']} ({o['quantity']}) - ₹{o['charge']:.2f}" for o in ords]) if ords else "कोई ऑर्डर नहीं है।")
        safe_edit(bot, txt, cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")))
    elif data == "u_cyob":
        user_states[f"{bot_id}_{uid}"] = "wait_token"
        safe_edit(bot, "🤖 @BotFather का टोकन चैट में पेस्ट करें:", cid, mid)

def handle_owner_callbacks(bot, bot_id, call, is_master=False):
    uid, cid, mid, data = call.from_user.id, call.message.chat.id, call.message.message_id, call.data
    if data == "a_payment":
        user_states[f"{bot_id}_{uid}"] = "wait_new_upi"
        safe_edit(bot, f"💳 Current UPI: `{get_bot_upi(bot_id)}`\nनई UPI ID भेजें:", cid, mid)
    elif data == "a_services":
        user_states[f"{bot_id}_{uid}"] = "wait_new_srv"
        safe_edit(bot, "⚙️ Format: `Service Name | Rate`", cid, mid)
    elif data == "a_users":
        user_states[f"{bot_id}_{uid}"] = "wait_add_bal"
        safe_edit(bot, "👥 Format: `TelegramUserID Amount`", cid, mid)
    elif data == "a_license_info":
        act, rsn = is_bot_active(bot_id)
        user_states[f"{bot_id}_{uid}"] = "wait_redeem_key"
        safe_edit(bot, f"🔑 Status: {rsn}\nअपनी Key चैट में भेजें:", cid, mid)
    elif data == "adm_gen_menu" and is_master:
        k = f"PRANAV-30D-{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))}"
        execute_query("INSERT INTO license_keys (key_code, duration_days, price, label) VALUES (?, 30, 149.0, '1 Month Elite')", (k,))
        safe_edit(bot, f"✅ Key:\n`{k}`", cid, mid, reply_markup=get_owner_panel(True))

def handle_text_inputs(bot, bot_id, msg, is_master=False):
    uid, cid, txt = msg.from_user.id, msg.chat.id, msg.text.strip()
    key = f"{bot_id}_{uid}"
    st = user_states.get(key)

    # Instant Auto-Detect 12-Digit UTR in Telegram Bot
    if len(txt) == 12 and txt.isdigit() and not st:
        t_row = fetch_query("SELECT tx_id FROM transactions WHERE bot_id=? AND user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1", (bot_id, uid), fetchone=True)
        if t_row:
            st = {"step": "wait_utr", "tx_id": t_row["tx_id"]}
    if not st:
        return

    if st == "wait_custom_dep":
        user_states.pop(key, None)
        if txt.isdigit() and int(txt) >= 10:
            send_bot_qr(bot, bot_id, uid, cid, msg.message_id, float(txt))
    elif st == "wait_token":
        user_states.pop(key, None)
        try:
            chk = requests.get(f"https://api.telegram.org/bot{txt}/getMe", timeout=6).json()
        except:
            return safe_send(bot, cid, "❌ नेटवर्क एरर!")
        if not chk.get("ok"):
            return safe_send(bot, cid, "❌ Invalid Token!")
        uname = chk["result"]["username"]
        bid = execute_query("INSERT INTO child_bots (owner_id, bot_token, bot_username, bot_name, upi_id, is_licensed, status) VALUES (?, ?, ?, ?, ?, 0, 'active')",
                            (uid, txt, uname, chk["result"]["first_name"], get_bot_upi(0)))
        start_child_bot_thread(bid, uid, txt, uname)
        safe_send(bot, cid, f"🎉 बॉट @{uname} लाइव हो गया!", reply_markup=get_user_main_menu())
    elif st == "wait_redeem_key":
        user_states.pop(key, None)
        lic = fetch_query("SELECT * FROM license_keys WHERE key_code=? AND is_used=0", (txt,), fetchone=True)
        if not lic:
            return safe_send(bot, cid, "❌ Invalid Key!")
        exp = (datetime.datetime.now() + datetime.timedelta(days=lic["duration_days"])).strftime("%Y-%m-%d %H:%M:%S")
        execute_query("UPDATE license_keys SET is_used=1, used_by_bot_id=? WHERE key_code=?", (bot_id, txt))
        execute_query("UPDATE child_bots SET is_licensed=1, subscription_expiry=? WHERE bot_id=?", (exp, bot_id))
        safe_send(bot, cid, f"🎉 License Activated till {exp}!", reply_markup=get_owner_panel(is_master))
    elif st == "wait_new_upi":
        user_states.pop(key, None)
        execute_query("UPDATE child_bots SET upi_id=? WHERE bot_id=?", (txt, bot_id))
        if bot_id == 0:
            set_cfg("upi_paytm", txt)
        safe_send(bot, cid, f"✅ UPI `{txt}` सेव हो गई!", reply_markup=get_owner_panel(is_master))
    elif st == "wait_new_srv":
        user_states.pop(key, None)
        if "|" in txt:
            n, r = txt.split("|", 1)
            execute_query("INSERT INTO smm_services (bot_id, service_name, rate_per_1000) VALUES (?, ?, ?)", (bot_id, n.strip(), float(r.strip())))
            safe_send(bot, cid, "✅ Service Added!", reply_markup=get_owner_panel(is_master))
    elif st == "wait_add_bal":
        user_states.pop(key, None)
        p = txt.split()
        if len(p) >= 2 and p[0].isdigit():
            execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, 'User')", (bot_id, int(p[0])))
            execute_query("UPDATE bot_clients SET balance = balance + ? WHERE bot_id=? AND user_id=?", (float(p[1]), bot_id, int(p[0])))
            safe_send(bot, cid, "✅ Balance Added!", reply_markup=get_owner_panel(is_master))
    elif isinstance(st, dict) and st.get("step") == "wait_utr":
        user_states.pop(key, None)
        if len(txt) != 12 or not txt.isdigit():
            return safe_send(bot, cid, "❌ 12-अंकों का सही UTR भेजें!")
        if fetch_query("SELECT tx_id FROM transactions WHERE bank_utr=? AND status='completed'", (txt,), fetchone=True):
            return safe_send(bot, cid, "❌ यह UTR पहले ही इस्तेमाल हो चुका है!")
        if get_cfg("auto_verify_utr", "1") == "1":
            complete_tx_and_notify(st["tx_id"], txt)
        else:
            execute_query("UPDATE transactions SET bank_utr=? WHERE tx_id=?", (txt, st["tx_id"]))
            safe_send(bot, cid, "⏳ UTR सबमिट हो गया! एडमिन अप्रूव होते ही बैलेंस जुड़ जाएगा।", reply_markup=get_user_main_menu())
    elif isinstance(st, dict) and st.get("step") == "wait_ord_link":
        st["link"] = txt
        st["step"] = "wait_ord_qty"
        user_states[key] = st
        safe_send(bot, cid, "🔢 Quantity भेजें (जैसे `100`, `500`):")
    elif isinstance(st, dict) and st.get("step") == "wait_ord_qty":
        user_states.pop(key, None)
        if not txt.isdigit() or int(txt) < 10:
            return safe_send(bot, cid, "❌ कम से कम 10 डालें!")
        qty = int(txt)
        chg = (qty / 1000.0) * float(st["rate"])
        r = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        if not r or r["balance"] < chg:
            return safe_send(bot, cid, f"⚠️ बैलेंस कम है! चार्ज ₹{chg:.2f} है।", reply_markup=get_user_main_menu())
        execute_query("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ? WHERE bot_id=? AND user_id=?", (chg, chg, bot_id, uid))
        oid = execute_query("INSERT INTO smm_orders (bot_id, user_id, service_name, link, quantity, charge) VALUES (?, ?, ?, ?, ?, ?)", (bot_id, uid, st["srv_name"], st["link"], qty, chg))
        safe_send(bot, cid, f"✅ Order #{oid} Placed!", reply_markup=get_user_main_menu())

# ==========================================
# 🚀 24x7 THREAD RUNNERS & AUTO-VERIFY DAEMON
# ==========================================
def bind_bot(bot_obj, bot_id, owner_id, is_master=False):
    @bot_obj.message_handler(commands=['start'])
    def s_cmd(m):
        execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)", (bot_id, m.from_user.id, m.from_user.username or "User"))
        safe_send(bot_obj, m.chat.id, "✨ 𝗣𝗥𝗔𝗡𝗔𝗩 𝟰𝗗 𝗦𝗠𝗠 & 𝗨𝗣𝗜 𝗕𝗢𝗧 ✨", reply_markup=get_user_main_menu())

    @bot_obj.message_handler(commands=['admin'])
    def a_cmd(m):
        if m.from_user.id == owner_id or m.from_user.id == SUPER_ADMIN_ID:
            safe_send(bot_obj, m.chat.id, "👑 Owner Admin Panel", reply_markup=get_owner_panel(is_master))

    @bot_obj.callback_query_handler(func=lambda c: True)
    def cb_all(c):
        if c.data.startswith("a_") or c.data.startswith("adm_"):
            if c.from_user.id == owner_id or c.from_user.id == SUPER_ADMIN_ID:
                handle_owner_callbacks(bot_obj, bot_id, c, is_master)
        else:
            handle_user_callbacks(bot_obj, bot_id, c)

    @bot_obj.message_handler(func=lambda m: True and m.text and not m.text.startswith('/'))
    def tx_all(m):
        handle_text_inputs(bot_obj, bot_id, m, is_master)

def child_worker(bot_id, owner_id, tok, uname):
    while True:
        try:
            cb = telebot.TeleBot(tok, threaded=True)
            bind_bot(cb, bot_id, owner_id, False)
            cb.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except:
            time.sleep(5)

def start_child_bot_thread(bot_id, owner_id, tok, uname):
    if bot_id not in running_child_bots:
        t = threading.Thread(target=child_worker, args=(bot_id, owner_id, tok, uname), daemon=True)
        running_child_bots[bot_id] = t
        t.start()

def master_worker():
    while True:
        try:
            if not MASTER_BOT_TOKEN:
                time.sleep(5)
                continue
            mb = telebot.TeleBot(MASTER_BOT_TOKEN, threaded=True)
            try:
                execute_query("UPDATE child_bots SET bot_username=? WHERE bot_id=0", (mb.get_me().username,))
            except:
                pass
            bind_bot(mb, 0, SUPER_ADMIN_ID, True)
            mb.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except:
            time.sleep(4)

def auto_verify_background_daemon():
    """Checks pending Web + Bot payments every 20 seconds & keeps server awake 24x7"""
    while True:
        time.sleep(20)
        try:
            requests.get("https://pranavsmm.online/ping", timeout=6)
        except:
            pass
        try:
            pendings = fetch_query("SELECT * FROM transactions WHERE status='pending' ORDER BY created_at DESC LIMIT 15")
            for t in (pendings or []):
                ok, utr = check_paytm_gateway(t["tx_id"], t["amount"])
                if not ok:
                    ok, utr = check_bharatpe_gateway(t["amount"])
                if ok:
                    complete_tx_and_notify(t["tx_id"], utr)
        except:
            pass

threading.Thread(target=master_worker, daemon=True).start()
threading.Thread(target=lambda: [start_child_bot_thread(r["bot_id"], r["owner_id"], r["bot_token"], r["bot_username"]) for r in (fetch_query("SELECT * FROM child_bots WHERE bot_id>0 AND status='active'") or [])], daemon=True).start()
threading.Thread(target=auto_verify_background_daemon, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
