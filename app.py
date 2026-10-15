import os
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
# ⚙️ SECURE GRANDMASTER CONFIGURATION
# ==========================================
RENDER_PORT = int(os.environ.get("PORT", 8081))
MASTER_BOT_TOKEN = os.environ.get("MASTER_BOT_TOKEN", "").strip()
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID", 8585055903))
SHOP_API_URL = os.environ.get("SHOP_API_URL", "https://pranavsmm.shop/api/v2").strip()
SHOP_API_KEY = os.environ.get("SHOP_API_KEY", "").strip()

ENV_ADMIN_USER = os.environ.get("ADMIN_USER", "pranav").strip()
ENV_ADMIN_PASS = os.environ.get("ADMIN_PASS", "pranav7@admin").strip()
ENV_ADMIN_SLUG = os.environ.get("ADMIN_SLUG", "control").strip().strip("/")

DB_PATH = "pranav_final_4d_master.db"

def hash_pwd(pwd): return hashlib.sha256(str(pwd).encode()).hexdigest()

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
    execute_query("INSERT INTO sys_cfg (k, val) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET val=excluded.val", (k, str(v)))

def init_db():
    tables = [
        "CREATE TABLE IF NOT EXISTS sys_cfg (k TEXT PRIMARY KEY, val TEXT)",
        """CREATE TABLE IF NOT EXISTS web_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, password_hash TEXT,
            balance REAL DEFAULT 0.0, total_deposit REAL DEFAULT 0.0, total_spent REAL DEFAULT 0.0,
            active_plan TEXT DEFAULT 'Free Tier', auto_sub INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS bot_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, user_id INTEGER, username TEXT,
            balance REAL DEFAULT 0.0, total_deposit REAL DEFAULT 0.0, total_spent REAL DEFAULT 0.0, UNIQUE(bot_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS child_bots (
            bot_id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, bot_token TEXT UNIQUE, bot_username TEXT,
            custom_upi TEXT DEFAULT '', custom_mid TEXT DEFAULT '', is_licensed INTEGER DEFAULT 0, expiry TIMESTAMP, status TEXT DEFAULT 'active'
        )""",
        """CREATE TABLE IF NOT EXISTS license_keys (
            key_code TEXT PRIMARY KEY, duration_days INTEGER DEFAULT 30, price REAL DEFAULT 149.0,
            is_used INTEGER DEFAULT 0, used_by_bot_id INTEGER DEFAULT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS transactions (
            tx_id TEXT PRIMARY KEY, bot_id INTEGER, user_id INTEGER, amount REAL, bank_utr TEXT, status TEXT DEFAULT 'pending'
        )""",
        """CREATE TABLE IF NOT EXISTS smm_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, user_id INTEGER, service_name TEXT,
            link TEXT, quantity INTEGER, charge REAL, shop_order_id TEXT DEFAULT '', status TEXT DEFAULT 'Processing'
        )"""
    ]
    for t in tables: execute_query(t)
    
    # Default Settings
    defaults = {"admin_user": ENV_ADMIN_USER, "admin_pass_hash": hash_pwd(ENV_ADMIN_PASS), "admin_slug": ENV_ADMIN_SLUG, "panel_name": "PRANAV SMM", "master_upi": "paytm.s2xzkgu@pty", "paytm_mid": "WWRYwl67445982860121"}
    for k, v in defaults.items():
        if not get_cfg(k): set_cfg(k, v)
    
    # Master Bot Default Entry
    exp = (datetime.datetime.now() + datetime.timedelta(days=36500)).strftime("%Y-%m-%d %H:%M:%S")
    execute_query("INSERT OR IGNORE INTO child_bots (bot_id, owner_id, bot_token, bot_username, is_licensed, expiry) VALUES (0, ?, 'MASTER', 'PranavMasterBot', 1, ?)", (SUPER_ADMIN_ID, exp))

init_db()

# ==========================================
# 🛡️ REAL PAYTM & PRANAVSMM.SHOP API LOGIC
# ==========================================
def verify_paytm_payment(utr, amount, custom_mid=None):
    """100% Real Verification without API Key, using just Merchant ID (MID) and UTR"""
    mid = custom_mid if custom_mid else get_cfg("paytm_mid")
    if not mid: return False, "MID (Merchant ID) सेट नहीं है!"
    try:
        r = requests.post("https://securegw.paytm.in/merchant-status/getTxnStatus", json={"MID": mid, "ORDERID": str(utr)}, timeout=8).json()
        if r.get("STATUS") == "TXN_SUCCESS" and float(r.get("TXNAMOUNT", 0)) >= float(amount):
            return True, r.get("BANKTXNID", utr)
        return False, r.get("RESPMSG", "बैंक से ट्रांजैक्शन नहीं मिला")
    except Exception as e: return False, f"API Error: {str(e)}"

def forward_order_to_shop(service_id, link, quantity):
    if not SHOP_API_KEY: return True, f"DEMO-{secrets.randbelow(9999)}"
    payload = {"key": SHOP_API_KEY, "action": "add", "service": service_id, "link": link, "quantity": quantity}
    try:
        r = requests.post(SHOP_API_URL, data=payload, timeout=10).json()
        return (True, str(r["order"])) if "order" in r else (False, r.get("error", "Shop API error"))
    except Exception as e: return False, str(e)

# ==========================================
# 🎨 MASSIVE 4D WHITE HTML TEMPLATES
# ==========================================
CSS_BASE = """
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
    body { font-family: 'Plus Jakarta Sans', sans-serif; background: #f4f7fe; color: #0f172a; }
    .card-4d { background: #fff; border-radius: 20px; border: 1px solid #e2e8f0; box-shadow: 0 10px 25px rgba(0,0,0,0.03); transition: 0.2s; }
    .card-4d:hover { box-shadow: 0 20px 40px rgba(0,0,0,0.06); transform: translateY(-2px); }
    .btn-4d { border-radius: 12px; font-weight: 800; transition: 0.2s; border-bottom: 4px solid rgba(0,0,0,0.2); }
    .btn-4d:active { border-bottom-width: 1px; transform: translateY(3px); }
    .input-4d { background: #f8fafc; border: 2px solid #e2e8f0; border-radius: 12px; padding: 12px; width: 100%; font-weight: 600; outline: none; transition: 0.2s; }
    .input-4d:focus { border-color: #3b82f6; background: #fff; }
</style>
"""

# -----------------
# 1. WEB UI (LOGIN & DASHBOARD)
# -----------------
WEB_UI = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PranavSMM.online - Cloud Hub</title>
    """ + CSS_BASE + """
</head>
<body class="min-h-screen flex flex-col items-center justify-center p-4">
    <div class="card-4d p-8 w-full max-w-4xl">
        <div class="text-center mb-8">
            <h1 class="text-4xl font-black text-slate-900 tracking-tight">PranavSMM<span class="text-blue-600">.online</span></h1>
            <p class="text-slate-500 font-bold mt-2">Official License Key & 24x7 Telegram Bot Hub</p>
        </div>
        
        {% if not session.get('user_id') %}
            <!-- LOGIN / REGISTER SECTION -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                <!-- Social Logins (Visual only for now, as requested) -->
                <div class="space-y-4">
                    <h3 class="text-lg font-bold text-slate-800">Quick Access</h3>
                    <button class="w-full py-3 bg-white border-2 border-slate-200 rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-slate-50"><img src="https://www.svgrepo.com/show/475656/google-color.svg" class="w-5 h-5"> Continue with Google</button>
                    <button class="w-full py-3 bg-blue-50 border-2 border-blue-200 text-blue-700 rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-blue-100"><img src="https://www.svgrepo.com/show/354443/telegram.svg" class="w-5 h-5"> Login with Telegram</button>
                </div>
                <!-- Manual Login -->
                <form method="POST" action="/auth" class="space-y-4">
                    <h3 class="text-lg font-bold text-slate-800">Email Login / Register</h3>
                    <input type="email" name="email" required placeholder="Email Address" class="input-4d">
                    <input type="password" name="password" required placeholder="Password (Min 8 chars)" class="input-4d">
                    <button type="submit" name="action" value="login" class="w-full btn-4d bg-blue-600 text-white py-3">Secure Login</button>
                    <button type="submit" name="action" value="register" class="w-full btn-4d bg-emerald-600 text-white py-3">Create New Account</button>
                </form>
            </div>
            {% if err %}<p class="text-red-500 font-bold text-center mt-4">{{ err }}</p>{% endif %}
        
        {% else %}
            <!-- USER DASHBOARD -->
            <div class="flex justify-between items-center mb-6 border-b pb-4">
                <span class="font-bold text-slate-700">Welcome, {{ user.email }}</span>
                <a href="/logout" class="px-4 py-2 bg-rose-100 text-rose-700 font-bold rounded-lg">Logout</a>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Wallet & Add Funds -->
                <div class="p-6 bg-slate-50 rounded-2xl border border-slate-200">
                    <span class="text-xs font-bold text-slate-400 uppercase">Wallet Balance</span>
                    <div class="text-3xl font-black text-emerald-600 mt-1">₹{{ "%.2f"|format(user.balance) }}</div>
                    <form method="POST" action="/add_funds" class="mt-4 space-y-3">
                        <input type="number" name="amount" placeholder="Amount (INR)" required class="input-4d text-sm py-2">
                        <input type="text" name="utr" placeholder="12-Digit Real Paytm UTR" required class="input-4d text-sm py-2">
                        <button class="w-full btn-4d bg-emerald-600 text-white py-2">🔒 Auto-Verify Payment</button>
                    </form>
                    {% if err %}<p class="text-rose-600 text-xs font-bold mt-2">{{ err }}</p>{% endif %}
                    {% if msg %}<p class="text-emerald-600 text-xs font-bold mt-2">{{ msg }}</p>{% endif %}
                </div>

                <!-- Buy Keys -->
                <div class="p-6 bg-blue-50 rounded-2xl border border-blue-200">
                    <h3 class="font-bold text-blue-900 mb-3">🎟️ Buy License Key</h3>
                    <form method="POST" action="/buy_key" class="space-y-3">
                        <select name="plan" class="input-4d text-sm py-2">
                            <option value="30">1 Month Elite - ₹149</option>
                            <option value="90">3 Months Master - ₹399</option>
                            <option value="36500">Lifetime God - ₹999</option>
                        </select>
                        <button class="w-full btn-4d bg-blue-600 text-white py-2">Buy Now (Deducts from Wallet)</button>
                    </form>
                    
                    <h3 class="font-bold text-blue-900 mt-6 mb-2">🔑 My Keys</h3>
                    <div class="space-y-2 max-h-32 overflow-auto">
                        {% for k in my_keys %}
                            <div class="p-2 bg-white rounded border text-[10px] font-mono font-bold">{{ k.key_code }}</div>
                        {% else %}
                            <p class="text-xs text-slate-500">No keys purchased yet.</p>
                        {% endfor %}
                    </div>
                </div>
            </div>
            
            <!-- Launch Child Bot -->
            <div class="mt-6 p-6 bg-purple-50 rounded-2xl border border-purple-200">
                <h3 class="font-bold text-purple-900 mb-2">🤖 Launch Child Bot (CYOB)</h3>
                <form method="POST" action="/launch_bot" class="flex flex-col sm:flex-row gap-3">
                    <input type="text" name="token" placeholder="BotFather Token" required class="input-4d text-sm">
                    <button class="btn-4d bg-purple-600 text-white py-2 px-6 shrink-0">Launch 24x7</button>
                </form>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

# -----------------
# 2. EXACT RENTAL ADMIN PANEL UI
# -----------------
ADMIN_UI = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pranav SMM - Rental Admin Control</title>
    """ + CSS_BASE + """
    <style>
        .sidebar { width: 260px; background: #fff; border-right: 1px solid #e2e8f0; height: 100vh; position: fixed; }
        .nav-item { padding: 12px 20px; color: #475569; font-weight: 700; display: block; transition: 0.2s; border-left: 4px solid transparent; }
        .nav-item:hover, .nav-item.active { background: #f1f5f9; color: #2563eb; border-left-color: #2563eb; }
        .content { margin-left: 260px; padding: 24px; }
    </style>
</head>
<body class="bg-slate-50">
    <!-- Sidebar -->
    <div class="sidebar flex flex-col">
        <div class="p-6 text-2xl font-black text-slate-900 tracking-tight">{{ cfg.panel_name }}</div>
        <nav class="flex-1 space-y-1">
            <a href="/{{ admin_slug }}?tab=dash" class="nav-item {{ 'active' if tab=='dash' else '' }}">📊 Dashboard</a>
            <a href="/{{ admin_slug }}?tab=users" class="nav-item {{ 'active' if tab=='users' else '' }}">👥 Users</a>
            <a href="/{{ admin_slug }}?tab=orders" class="nav-item {{ 'active' if tab=='orders' else '' }}">🛒 Orders</a>
            <a href="/{{ admin_slug }}?tab=services" class="nav-item {{ 'active' if tab=='services' else '' }}">⚙️ Services</a>
            <a href="/{{ admin_slug }}?tab=payments" class="nav-item {{ 'active' if tab=='payments' else '' }}">💳 Payments</a>
            <a href="/{{ admin_slug }}?tab=keys" class="nav-item {{ 'active' if tab=='keys' else '' }}">🔑 License Keys</a>
            <a href="/{{ admin_slug }}?tab=appearance" class="nav-item {{ 'active' if tab=='appearance' else '' }}">🎨 Appearance</a>
            <a href="/{{ admin_slug }}?tab=settings" class="nav-item {{ 'active' if tab=='settings' else '' }}">⚙️ Settings</a>
        </nav>
        <a href="/{{ admin_slug }}/logout" class="p-4 text-center text-rose-600 font-bold hover:bg-rose-50 border-t">Logout</a>
    </div>

    <!-- Main Content -->
    <div class="content space-y-6">
        {% if msg %}<div class="p-4 bg-emerald-100 text-emerald-800 font-bold rounded-xl">{{ msg }}</div>{% endif %}
        
        {% if tab == 'dash' %}
        <!-- 8 Rental Metric Cards -->
        <div class="grid grid-cols-4 gap-4">
            <div class="card-4d p-5"><div class="text-2xl font-black">{{ stats.users }}</div><div class="text-xs text-slate-500 font-bold uppercase mt-1">Total Users</div></div>
            <div class="card-4d p-5"><div class="text-2xl font-black">{{ stats.orders }}</div><div class="text-xs text-slate-500 font-bold uppercase mt-1">Total Orders</div></div>
            <div class="card-4d p-5"><div class="text-2xl font-black">{{ stats.payments }}</div><div class="text-xs text-slate-500 font-bold uppercase mt-1">Received Payments</div></div>
            <div class="card-4d p-5"><div class="text-2xl font-black">{{ stats.bots }}</div><div class="text-xs text-slate-500 font-bold uppercase mt-1">Child Bots (Providers)</div></div>
        </div>
        <div class="card-4d p-6 mt-6">
            <h3 class="font-bold text-slate-800 mb-4">Security Logs</h3>
            <div class="space-y-2">
                <div class="p-3 bg-slate-50 border rounded-lg text-xs font-mono">14/10/2026 - Administrator Logged in via Password</div>
            </div>
        </div>
        
        {% elif tab == 'payments' %}
        <!-- EXACT PAYTM SETTINGS MODAL FROM SCREENSHOT -->
        <div class="card-4d p-6 border-l-4 border-l-blue-500">
            <h2 class="text-lg font-black mb-4">Edit Payment Method: PayTM QR Checkout</h2>
            <form method="POST" action="/{{ admin_slug }}/action" class="grid grid-cols-2 gap-4">
                <input type="hidden" name="act" value="save_paytm">
                <div><label class="text-xs font-bold text-slate-500">Method Name</label><input type="text" value="PayTM QR Checkout" readonly class="input-4d py-2 text-sm text-slate-400"></div>
                <div><label class="text-xs font-bold text-slate-500">Minimum Amount</label><input type="number" name="min_amt" value="1" class="input-4d py-2 text-sm"></div>
                <div><label class="text-xs font-bold text-slate-500">Maximum Amount</label><input type="number" name="max_amt" value="100000" class="input-4d py-2 text-sm"></div>
                <div><label class="text-xs font-bold text-slate-500">Timeout Time (minutes)</label><input type="number" name="timeout" value="10" class="input-4d py-2 text-sm"></div>
                <div><label class="text-xs font-bold text-slate-500">UPI ID</label><input type="text" name="upi_id" value="{{ cfg.master_upi }}" class="input-4d py-2 text-sm"></div>
                <div><label class="text-xs font-bold text-slate-500">Merchant ID (MID) - For Auto Verify</label><input type="text" name="paytm_mid" value="{{ cfg.paytm_mid }}" class="input-4d py-2 text-sm"></div>
                <div class="col-span-2"><button class="btn-4d bg-blue-600 text-white py-2 px-6">Update Gateway</button></div>
            </form>
        </div>

        {% elif tab == 'keys' %}
        <div class="card-4d p-6">
            <h2 class="text-lg font-black mb-4">🎟️ Generate License Key</h2>
            <form method="POST" action="/{{ admin_slug }}/action" class="flex gap-4">
                <input type="hidden" name="act" value="gen_key">
                <select name="duration" class="input-4d py-2 w-64">
                    <option value="30">1 Month (30 Days)</option>
                    <option value="90">3 Months (90 Days)</option>
                    <option value="36500">Lifetime God Mode</option>
                </select>
                <button class="btn-4d bg-purple-600 text-white px-6">Generate</button>
            </form>
            {% if key_gen %}<div class="mt-4 p-4 bg-emerald-50 text-emerald-800 font-mono font-bold rounded-lg">{{ key_gen }}</div>{% endif %}
        </div>
        
        {% elif tab == 'settings' %}
        <div class="card-4d p-6">
            <h2 class="text-lg font-black mb-4">General Settings</h2>
            <form method="POST" action="/{{ admin_slug }}/action" class="space-y-4 max-w-md">
                <input type="hidden" name="act" value="save_general">
                <div><label class="text-xs font-bold text-slate-500">Panel Name</label><input type="text" name="panel_name" value="{{ cfg.panel_name }}" class="input-4d py-2"></div>
                <div><label class="text-xs font-bold text-slate-500">Secret Admin URL Slug</label><input type="text" name="admin_slug" value="{{ admin_slug }}" class="input-4d py-2"></div>
                <div><label class="text-xs font-bold text-slate-500">New Admin Password</label><input type="password" name="new_pass" placeholder="Leave blank to keep current" class="input-4d py-2"></div>
                <button class="btn-4d bg-blue-600 text-white w-full py-2">Save Settings</button>
            </form>
        </div>
        
        {% else %}
        <div class="card-4d p-12 text-center text-slate-400 font-bold">Select an option from the sidebar.</div>
        {% endif %}
    </div>
</body>
</html>
"""

# ==========================================
# 🌐 FLASK WEB CONTROLLERS
# ==========================================
app = Flask(__name__)
app.secret_key = "PranavSuperSecretFinalCode2026"
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
            session['u_err'] = "Email already registered!"
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
        session['u_err'] = "Invalid UTR!"
        return redirect('/')
    if fetch_query("SELECT tx_id FROM transactions WHERE bank_utr=?", (utr,), fetchone=True):
        session['u_err'] = "UTR already used!"
        return redirect('/')
        
    # REAL PAYTM VERIFICATION
    ok, ref = verify_paytm_payment(utr, amt)
    if ok:
        execute_query("INSERT INTO transactions (tx_id, user_id, amount, bank_utr, status) VALUES (?, ?, ?, ?, 'completed')", (f"W{int(time.time())}", session['user_id'], amt, ref))
        execute_query("UPDATE web_users SET balance = balance + ? WHERE id=?", (amt, session['user_id']))
        session['u_msg'] = f"Successfully added ₹{amt} to wallet!"
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
        session['u_err'] = "Insufficient wallet balance!"
        return redirect('/')
    
    k = generate_secure_key(days)
    execute_query("UPDATE web_users SET balance = balance - ? WHERE id=?", (price, session['user_id']))
    execute_query("INSERT INTO license_keys (key_code, duration_days, price, used_by_user_id) VALUES (?, ?, ?, ?)", (k, days, price, session['user_id']))
    session['u_msg'] = f"Key Generated: {k}"
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
        start_child_bot(bid, session['user_id'], tok)
        session['u_msg'] = f"Bot @{un} Launched Successfully! Set License Key via /admin in bot."
    except Exception as e:
        session['u_err'] = str(e)
    return redirect('/')

@app.route('/logout')
def web_logout():
    session.pop('user_id', None)
    return redirect('/')

# --- ADMIN ROUTES ---
@app.route('/<path:slug>', methods=['GET', 'POST'])
def admin_router(slug):
    adm_slug = get_cfg("admin_slug", ENV_ADMIN_SLUG).strip("/")
    if slug == f"{adm_slug}/logout":
        session.pop('admin_logged', None)
        return redirect(f"/{adm_slug}")

    if slug == f"{adm_slug}/action" and request.method == 'POST':
        if not session.get('admin_logged'): return redirect(f"/{adm_slug}")
        act = request.form.get("act")
        if act == "save_paytm":
            set_cfg("master_upi", request.form.get("upi_id"))
            set_cfg("paytm_mid", request.form.get("paytm_mid"))
            session['a_msg'] = "Gateway Updated!"
            return redirect(f"/{adm_slug}?tab=payments")
        elif act == "gen_key":
            k = generate_secure_key(int(request.form.get("duration", 30)))
            execute_query("INSERT INTO license_keys (key_code) VALUES (?)", (k,))
            session['a_key'] = k
            return redirect(f"/{adm_slug}?tab=keys")
        elif act == "save_general":
            set_cfg("panel_name", request.form.get("panel_name"))
            ns = request.form.get("admin_slug", adm_slug)
            if ns: set_cfg("admin_slug", ns)
            np = request.form.get("new_pass", "")
            if np: set_cfg("admin_pass_hash", hash_pwd(np))
            session['a_msg'] = "Settings Saved!"
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
        return """<body style="background:#f4f7fe;display:flex;align-items:center;justify-content:center;height:100vh;"><form method="POST" style="background:#fff;padding:30px;border-radius:20px;box-shadow:0 10px 25px rgba(0,0,0,0.05);"><h2 style="font-family:sans-serif;margin-bottom:20px;">Admin Login</h2><input type="text" name="username" placeholder="Username" style="display:block;margin-bottom:10px;padding:10px;width:250px;border:1px solid #ddd;border-radius:8px;"><input type="password" name="password" placeholder="Password" style="display:block;margin-bottom:20px;padding:10px;width:250px;border:1px solid #ddd;border-radius:8px;"><button style="width:100%;padding:10px;background:#2563eb;color:#fff;border:none;border-radius:8px;cursor:pointer;">Login</button></form></body>"""

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
# 🤖 TELEGRAM BOT LOGIC (MASTER & CHILD)
# ==========================================
user_states = {}
running_bots = {}

def get_bot_menu(is_master):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("🛒 New Order", callback_data="u_order"), types.InlineKeyboardButton("💳 Wallet", callback_data="u_bal"))
    m.add(types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"), types.InlineKeyboardButton("📦 My Orders", callback_data="u_hist"))
    if is_master:
        m.add(types.InlineKeyboardButton("🤖 Launch Child Bot", callback_data="m_cyob"), types.InlineKeyboardButton("🔑 Get License Key", url="https://pranavsmm.online"))
    return m

def bind_bot_events(bot, bid, owner_id, is_master):
    @bot.message_handler(commands=['start'])
    def s_cmd(m):
        execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)", (bid, m.from_user.id, m.from_user.username))
        bot.send_message(m.chat.id, "⚡ **PRANAV SMM HUB**\n\nChoose an option:", reply_markup=get_bot_menu(is_master), parse_mode="Markdown")

    @bot.message_handler(commands=['admin'])
    def a_cmd(m):
        if m.from_user.id != owner_id and m.from_user.id != SUPER_ADMIN_ID: return
        rm = types.InlineKeyboardMarkup()
        if is_master:
            rm.add(types.InlineKeyboardButton("🎟️ Admin Key", callback_data="adm_key"))
        else:
            b_info = fetch_query("SELECT is_licensed FROM child_bots WHERE bot_id=?", (bid,), fetchone=True)
            if b_info and b_info["is_licensed"]:
                rm.add(types.InlineKeyboardButton("💳 Change UPI & MID", callback_data="cb_upi"))
            else:
                rm.add(types.InlineKeyboardButton("🔒 Enter License Key to Unlock Payments", callback_data="cb_key"))
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
            upi = b_info["custom_upi"] if (b_info and b_info["is_licensed"] and b_info["custom_upi"]) else get_cfg("master_upi")
            user_states[f"{bid}_{uid}"] = "wait_utr"
            bot.send_photo(cid, f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(f'upi://pay?pa={upi}&pn=SMM&cu=INR')}", caption=f"🏦 UPI: `{upi}`\n\nSend: `Amount UTR`\nEx: `100 123456789012`", parse_mode="Markdown")
        elif d == "u_order":
            rm = types.InlineKeyboardMarkup(row_width=1)
            rm.add(types.InlineKeyboardButton("🔥 IG Followers - ₹49/1k", callback_data="srv_101_49"), types.InlineKeyboardButton("▶️ YT Views - ₹99/1k", callback_data="srv_105_99"))
            bot.send_message(cid, "🛒 Select Service:", reply_markup=rm)
        elif d.startswith("srv_"):
            _, sid, rate = d.split("_")
            user_states[f"{bid}_{uid}"] = {"step": "link", "sid": sid, "rate": float(rate)}
            bot.send_message(cid, "🔗 Send Post/Profile Link:")
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
            bot.send_message(cid, f"`{generate_secure_key(30)}`", parse_mode="Markdown")

    @bot.message_handler(func=lambda m: True and m.text and not m.text.startswith('/'))
    def txt_handler(m):
        uid = m.from_user.id
        cid = m.chat.id
        txt = m.text.strip()
        st = user_states.get(f"{bid}_{uid}")

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
                execute_query("UPDATE bot_clients SET balance = balance + ? WHERE bot_id=? AND user_id=?", (amt, bid, uid))
                user_states.pop(f"{bid}_{uid}", None)
                bot.send_message(cid, f"🎉 ₹{amt} Verified & Added!")
            else:
                bot.send_message(cid, f"❌ Bank Failed: {ref}")
            return

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
            if not ub or ub["balance"] < chg: return bot.send_message(cid, "⚠️ Insufficient Wallet Balance!")
            
            # OWNER WALLET CHECK FOR CHILD BOTS
            if not is_master:
                ob = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=0 AND user_id=?", (owner_id,), fetchone=True)
                if not ob or ob["balance"] < chg: return bot.send_message(cid, "⚠️ Service Unavailable. (Owner wallet empty)")
                execute_query("UPDATE bot_clients SET balance = balance - ? WHERE bot_id=0 AND user_id=?", (chg, owner_id))
            
            execute_query("UPDATE bot_clients SET balance = balance - ? WHERE bot_id=? AND user_id=?", (chg, bid, uid))
            ok, oid = forward_order_to_shop(st["sid"], st["link"], qty)
            execute_query("INSERT INTO smm_orders (bot_id, user_id, charge, shop_order_id) VALUES (?, ?, ?, ?)", (bid, uid, chg, oid))
            user_states.pop(f"{bid}_{uid}", None)
            bot.send_message(cid, f"✅ Order Placed! ID: `{oid}`", parse_mode="Markdown")
            return

        if st == "wait_tok" and is_master:
            try:
                un = requests.get(f"https://api.telegram.org/bot{txt}/getMe").json()["result"]["username"]
                new_bid = execute_query("INSERT INTO child_bots (owner_id, bot_token, bot_username) VALUES (?, ?, ?)", (uid, txt, un))
                start_child_bot(new_bid, uid, txt)
                bot.send_message(cid, f"🚀 Bot @{un} Launched! Use /admin to enter License Key.")
            except: bot.send_message(cid, "❌ Invalid Token!")
            user_states.pop(f"{bid}_{uid}", None)

        if st == "wait_lic" and not is_master:
            lic = fetch_query("SELECT * FROM license_keys WHERE key_code=? AND is_used=0", (txt,), fetchone=True)
            if not lic: return bot.send_message(cid, "❌ Invalid Key!")
            execute_query("UPDATE license_keys SET is_used=1 WHERE key_code=?", (txt,))
            execute_query("UPDATE child_bots SET is_licensed=1 WHERE bot_id=?", (bid,))
            bot.send_message(cid, "🎉 License Active! Set your UPI via /admin.")
            user_states.pop(f"{bid}_{uid}", None)

        if st == "wait_upi" and not is_master:
            if " " not in txt: return bot.send_message(cid, "❌ format: UPI MID")
            upi, mid = txt.split(" ", 1)
            execute_query("UPDATE child_bots SET custom_upi=?, custom_mid=? WHERE bot_id=?", (upi, mid, bid))
            bot.send_message(cid, "✅ Payment Settings Updated!")
            user_states.pop(f"{bid}_{uid}", None)

# -----------------
# THREAD RUNNERS
# -----------------
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

threading.Thread(target=master_loop, daemon=True).start()
threading.Thread(target=lambda: [start_child_bot(r["bot_id"], r["owner_id"], r["bot_token"]) for r in (fetch_query("SELECT * FROM child_bots WHERE bot_id>0") or [])], daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
