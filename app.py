import os
import sys
import time
import datetime
import random
import string
import secrets
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
SITE_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://pranavsmm.online").strip()
MASTER_BOT_TOKEN = os.environ.get("MASTER_BOT_TOKEN", "").strip()
SUPER_ADMIN_ID = 8585055903  # Pranav Patel (प्रणव जी)

WEB_ADMIN_USER = "pranav"
WEB_ADMIN_PASS = "pranav7@admin"
DEFAULT_UPI_ID = "paytm.s2xzkgu@pty"

SECRET_KEY = os.environ.get("SECRET_KEY", "PranavMasterSecretKey2050Engine3D=======")
try:
    cipher_suite = Fernet(SECRET_KEY.encode() if isinstance(SECRET_KEY, str) else SECRET_KEY)
except:
    cipher_suite = Fernet(Fernet.generate_key())

DB_PATH = "pranav_3d_master_v5.db"
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

user_states = {}
keypad_amounts = {}
running_child_bots = {}

# ==========================================
# 🗄️ BULLETPROOF DATABASE ENGINE
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
        """CREATE TABLE IF NOT EXISTS child_bots (
            bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            bot_token TEXT UNIQUE,
            bot_username TEXT,
            bot_name TEXT,
            upi_id TEXT DEFAULT 'paytm.s2xzkgu@pty',
            support_tg TEXT DEFAULT 'PranavPatel',
            subscription_expiry TIMESTAMP,
            is_licensed INTEGER DEFAULT 0,
            auto_renew INTEGER DEFAULT 0,
            plan_days INTEGER DEFAULT 0,
            plan_price REAL DEFAULT 0.0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS license_keys (
            key_code TEXT PRIMARY KEY,
            duration_days INTEGER DEFAULT 30,
            price REAL DEFAULT 149.0,
            label TEXT DEFAULT '1 Month Pro',
            is_sub INTEGER DEFAULT 0,
            used_by_bot_id INTEGER DEFAULT NULL,
            used_by_user_id INTEGER DEFAULT NULL,
            is_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS bot_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER,
            user_id INTEGER,
            username TEXT,
            balance REAL DEFAULT 0.0,
            total_deposit REAL DEFAULT 0.0,
            total_spent REAL DEFAULT 0.0,
            auto_sub INTEGER DEFAULT 0,
            sub_plan TEXT DEFAULT 'None',
            sub_expiry TIMESTAMP DEFAULT NULL,
            UNIQUE(bot_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS web_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            balance REAL DEFAULT 0.0,
            total_deposit REAL DEFAULT 0.0,
            auto_sub INTEGER DEFAULT 0,
            active_plan TEXT DEFAULT 'Free User',
            plan_price REAL DEFAULT 0.0,
            plan_days INTEGER DEFAULT 0,
            sub_expiry TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS smm_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER DEFAULT 0,
            service_name TEXT,
            rate_per_1000 REAL DEFAULT 50.0,
            min_qty INTEGER DEFAULT 100,
            max_qty INTEGER DEFAULT 50000
        )""",
        """CREATE TABLE IF NOT EXISTS bot_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id INTEGER,
            user_id INTEGER,
            service_name TEXT,
            link TEXT,
            quantity INTEGER,
            charge REAL,
            status TEXT DEFAULT 'Completed ✅',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS transactions (
            tx_id TEXT PRIMARY KEY,
            bot_id INTEGER DEFAULT 0,
            user_id INTEGER DEFAULT 0,
            web_user_id INTEGER DEFAULT 0,
            amount REAL,
            tx_type TEXT DEFAULT 'deposit',
            bank_utr TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    ]
    for q in queries:
        execute_query(q)

    # Insert Master Bot Row (bot_id = 0)
    exp_date = (datetime.datetime.now() + datetime.timedelta(days=36500)).strftime("%Y-%m-%d %H:%M:%S")
    execute_query("""
        INSERT OR IGNORE INTO child_bots (bot_id, owner_id, bot_token, bot_username, bot_name, upi_id, is_licensed, subscription_expiry)
        VALUES (0, ?, 'MASTER', 'PranavMasterBot', 'Pranav Master Engine', ?, 1, ?)
    """, (SUPER_ADMIN_ID, DEFAULT_UPI_ID, exp_date))

    # Default SMM Services
    if fetch_query("SELECT COUNT(*) as c FROM smm_services", fetchone=True)["c"] == 0:
        default_srv = [
            (0, "🔥 Instagram High Speed Followers [Non-Drop]", 49.0, 100, 100000),
            (0, "❤️ Instagram Instant Likes [Real]", 15.0, 100, 500000),
            (0, "🚀 Instagram Reels Views [Ultra Fast]", 5.0, 500, 1000000),
            (0, "📢 Telegram Channel Members [Guaranteed]", 80.0, 100, 50000),
            (0, "▶️ YouTube High Retention Views", 99.0, 500, 100000)
        ]
        for b_id, s_name, rate, mn, mx in default_srv:
            execute_query("INSERT INTO smm_services (bot_id, service_name, rate_per_1000, min_qty, max_qty) VALUES (?, ?, ?, ?, ?)", (b_id, s_name, rate, mn, mx))

init_db()

PLANS_CATALOG = {
    "7": {"days": 7, "price": 49.0, "min_sub_wallet": 100.0, "label": "7 Days Trial Pro", "badge": "TRIAL"},
    "30": {"days": 30, "price": 149.0, "min_sub_wallet": 300.0, "label": "1 Month Elite", "badge": "POPULAR"},
    "90": {"days": 90, "price": 399.0, "min_sub_wallet": 800.0, "label": "3 Months Master", "badge": "BEST VALUE"},
    "36500": {"days": 36500, "price": 999.0, "min_sub_wallet": 2000.0, "label": "👑 Lifetime God Mode", "badge": "LIFETIME"}
}

def get_master_upi():
    row = fetch_query("SELECT upi_id FROM child_bots WHERE bot_id=0", fetchone=True)
    return row["upi_id"] if row and row["upi_id"] else DEFAULT_UPI_ID

def get_bot_upi(bot_id):
    row = fetch_query("SELECT upi_id FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
    return row["upi_id"] if row and row["upi_id"] else get_master_upi()

# ==========================================
# 🎨 PURE WHITE 3D RENDER PANEL UI (CSS + NAV)
# ==========================================
BASE_STYLE_AND_NAV = """
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700;800;900&display=swap" rel="stylesheet">
<style>
    body {
        font-family: 'Plus Jakarta Sans', sans-serif;
        background: #f4f7fe;
        color: #0f172a;
        overflow-x: hidden;
    }
    /* Pure White 3D Extruded Cards */
    .card-3d {
        background: #ffffff;
        border-radius: 24px;
        border: 2px solid #e2e8f0;
        box-shadow: 0 14px 28px rgba(15, 23, 42, 0.06), 0 6px 0 #cbd5e1;
        transition: all 0.2s ease;
    }
    .card-3d:hover {
        transform: translateY(-3px);
        box-shadow: 0 20px 35px rgba(15, 23, 42, 0.1), 0 8px 0 #94a3b8;
    }
    /* Colorful 3D Pop-Out Buttons */
    .btn-3d-purple {
        background: linear-gradient(135deg, #7c3aed, #4f46e5);
        color: #ffffff;
        border-bottom: 5px solid #3730a3;
        border-radius: 16px;
        box-shadow: 0 8px 20px rgba(124, 58, 237, 0.35);
        transition: all 0.15s ease;
    }
    .btn-3d-purple:active { transform: translateY(4px); border-bottom-width: 1px; }

    .btn-3d-green {
        background: linear-gradient(135deg, #10b981, #059669);
        color: #ffffff;
        border-bottom: 5px solid #065f46;
        border-radius: 16px;
        box-shadow: 0 8px 20px rgba(16, 185, 129, 0.35);
        transition: all 0.15s ease;
    }
    .btn-3d-green:active { transform: translateY(4px); border-bottom-width: 1px; }

    .btn-3d-orange {
        background: linear-gradient(135deg, #f59e0b, #ea580c);
        color: #ffffff;
        border-bottom: 5px solid #9a3412;
        border-radius: 16px;
        box-shadow: 0 8px 20px rgba(234, 88, 12, 0.35);
        transition: all 0.15s ease;
    }
    .btn-3d-orange:active { transform: translateY(4px); border-bottom-width: 1px; }

    .btn-3d-pink {
        background: linear-gradient(135deg, #ec4899, #e11d48);
        color: #ffffff;
        border-bottom: 5px solid #9f1239;
        border-radius: 16px;
        box-shadow: 0 8px 20px rgba(225, 29, 72, 0.35);
        transition: all 0.15s ease;
    }
    .btn-3d-pink:active { transform: translateY(4px); border-bottom-width: 1px; }

    .btn-3d-blue {
        background: linear-gradient(135deg, #0ea5e9, #2563eb);
        color: #ffffff;
        border-bottom: 5px solid #1e40af;
        border-radius: 16px;
        box-shadow: 0 8px 20px rgba(37, 99, 235, 0.35);
        transition: all 0.15s ease;
    }
    .btn-3d-blue:active { transform: translateY(4px); border-bottom-width: 1px; }

    .btn-3d-white {
        background: #ffffff;
        color: #1e293b;
        border: 2px solid #cbd5e1;
        border-bottom: 5px solid #94a3b8;
        border-radius: 16px;
        transition: all 0.15s ease;
    }
    .btn-3d-white:active { transform: translateY(4px); border-bottom-width: 2px; }
</style>
<script>
    function toggleMenu() {
        const drawer = document.getElementById('side-drawer');
        const backdrop = document.getElementById('drawer-backdrop');
        drawer.classList.toggle('translate-x-full');
        backdrop.classList.toggle('hidden');
    }
</script>
"""

NAVBAR_COMPONENT = """
<!-- Sticky Pure White 3D Top Bar with 3-Dot / Hamburger Menu -->
<header class="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b-2 border-slate-200 px-5 py-3.5 shadow-sm">
    <div class="max-w-6xl mx-auto flex justify-between items-center">
        <a href="/" class="flex items-center gap-2.5">
            <div class="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-600 via-purple-600 to-pink-500 flex items-center justify-center text-white font-black text-xl shadow-md">⚡</div>
            <div>
                <span class="text-xl font-black tracking-tight bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 bg-clip-text text-transparent">PranavSMM.online</span>
                <span class="block text-[10px] font-extrabold text-slate-400 uppercase tracking-widest">3D Render Panel v5.0</span>
            </div>
        </a>
        <div class="flex items-center gap-3">
            {% if session.get('user_id') %}
                <a href="/dashboard" class="hidden sm:inline-block btn-3d-blue px-4 py-2 text-xs font-extrabold">🚀 Dashboard</a>
            {% else %}
                <a href="/login" class="hidden sm:inline-block btn-3d-white px-4 py-2 text-xs font-extrabold">Login</a>
                <a href="/register" class="hidden sm:inline-block btn-3d-purple px-4 py-2 text-xs font-extrabold">Sign Up</a>
            {% endif %}
            <!-- 3-Dot / 3-Line Menu Trigger Button -->
            <button onclick="toggleMenu()" class="btn-3d-white px-3.5 py-2 flex items-center gap-1.5 font-black text-slate-700 hover:text-indigo-600" title="Menu">
                <span class="text-lg leading-none">⋮</span>
                <span class="text-lg leading-none">☰</span>
            </button>
        </div>
    </div>
</header>

<!-- Slide-Out 3D Navigation Drawer -->
<div id="drawer-backdrop" onclick="toggleMenu()" class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 hidden"></div>
<aside id="side-drawer" class="fixed top-0 right-0 h-full w-80 bg-white border-l-2 border-slate-200 z-50 transform translate-x-full transition-transform duration-300 ease-in-out p-6 flex flex-col justify-between shadow-2xl">
    <div>
        <div class="flex justify-between items-center pb-4 border-b-2 border-slate-100">
            <span class="font-black text-lg text-slate-800">⚡ Quick Navigation</span>
            <button onclick="toggleMenu()" class="w-9 h-9 rounded-xl bg-rose-100 text-rose-600 font-black">✕</button>
        </div>
        <nav class="mt-6 space-y-3">
            <a href="/" class="flex items-center gap-3 p-3.5 rounded-2xl bg-slate-50 hover:bg-indigo-50 text-slate-800 hover:text-indigo-600 font-extrabold text-sm border border-slate-200 transition">🏠 Home Page</a>
            <a href="/dashboard" class="flex items-center gap-3 p-3.5 rounded-2xl bg-indigo-50 text-indigo-700 font-extrabold text-sm border border-indigo-200 transition">📊 User 3D Dashboard</a>
            <a href="/dashboard#add-funds" onclick="toggleMenu()" class="flex items-center gap-3 p-3.5 rounded-2xl bg-emerald-50 text-emerald-700 font-extrabold text-sm border border-emerald-200 transition">💰 Add Funds (₹1000 / ₹2000)</a>
            <a href="/dashboard#plans" onclick="toggleMenu()" class="flex items-center gap-3 p-3.5 rounded-2xl bg-amber-50 text-amber-700 font-extrabold text-sm border border-amber-200 transition">🎟️ Subscriptions & Keys</a>
            <a href="https://t.me/{{ master_bot_uname }}" target="_blank" class="flex items-center gap-3 p-3.5 rounded-2xl bg-sky-50 text-sky-700 font-extrabold text-sm border border-sky-200 transition">🤖 Launch Telegram Bot ↗</a>
            <a href="/admin" class="flex items-center gap-3 p-3.5 rounded-2xl bg-purple-50 text-purple-700 font-extrabold text-sm border border-purple-200 transition">👑 Pranav Admin Control</a>
        </nav>
    </div>
    <div class="pt-4 border-t-2 border-slate-100 text-center">
        {% if session.get('user_id') %}
            <a href="/logout" class="block w-full btn-3d-pink py-3 text-sm font-black">🚪 Logout Account</a>
        {% else %}
            <a href="/login" class="block w-full btn-3d-purple py-3 text-sm font-black">🔐 Login / Register</a>
        {% endif %}
        <p class="text-[11px] font-bold text-slate-400 mt-3">© 2026 PranavSMM.online • 24×7 Live</p>
    </div>
</aside>
"""

HOME_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PranavSMM.online - 3D Render SMM & UPI Gateway Panel</title>
    """ + BASE_STYLE_AND_NAV + """
</head>
<body class="min-h-screen flex flex-col justify-between">
    """ + NAVBAR_COMPONENT + """

    <main class="max-w-6xl mx-auto px-5 py-12 text-center flex-1">
        <div class="inline-flex items-center gap-2 bg-white border-2 border-indigo-200 px-4 py-1.5 rounded-full text-xs font-extrabold text-indigo-600 shadow-sm mb-6">
            🟢 24×7 NON-STOP CLOUD ENGINE • ZERO DOWNTIME
        </div>
        <h1 class="text-4xl md:text-6xl font-black text-slate-900 tracking-tight leading-tight">
            Next-Gen 3D Render <br>
            <span class="bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-500 bg-clip-text text-transparent">SMM & Auto-UPI Panel</span>
        </h1>
        <p class="text-slate-600 font-semibold mt-4 max-w-2xl mx-auto text-sm md:text-base">
            प्रणव जी का 3D सुपर-फास्ट क्लाउड पैनल! चाहे एक बार के लिए लाइसेंस की (Key) लो या वॉलेट में बैलेंस रखकर ऑटो-सब्सक्रिप्शन चलाओ—सब कुछ 100% ऑटोमैटिक!
        </p>

        <div class="mt-8 flex flex-wrap justify-center gap-4">
            <a href="/register" class="btn-3d-purple px-8 py-4 text-sm font-black">🚀 Create User Account</a>
            <a href="/login" class="btn-3d-green px-8 py-4 text-sm font-black">🔐 User Login</a>
            <a href="https://t.me/{{ master_bot_uname }}" target="_blank" class="btn-3d-blue px-8 py-4 text-sm font-black">🤖 Open Telegram Bot</a>
        </div>

        <!-- Colorful 3D Feature Highlights -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mt-14 text-left">
            <div class="card-3d p-6 border-t-8 border-t-indigo-500">
                <div class="w-12 h-12 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center text-2xl font-black mb-4">💰</div>
                <h3 class="text-lg font-black text-slate-900">Instant Wallet Add Funds</h3>
                <p class="text-xs font-semibold text-slate-500 mt-2">₹100, ₹500, ₹1000 या ₹2000 एक क्लिक में QR कोड स्कैन करके अपने वॉलेट में जोड़ें।</p>
            </div>
            <div class="card-3d p-6 border-t-8 border-t-emerald-500">
                <div class="w-12 h-12 rounded-2xl bg-emerald-100 text-emerald-600 flex items-center justify-center text-2xl font-black mb-4">🔄</div>
                <h3 class="text-lg font-black text-slate-900">Smart Auto-Subscription</h3>
                <p class="text-xs font-semibold text-slate-500 mt-2">वॉलेट में दोगुना बैलेंस (जैसे ₹49 प्लान के लिए ₹100+) रखें और ऑटो-रिन्यूअल चालू करें, या एक बार में सीधा खरीदें!</p>
            </div>
            <div class="card-3d p-6 border-t-8 border-t-pink-500">
                <div class="w-12 h-12 rounded-2xl bg-pink-100 text-pink-600 flex items-center justify-center text-2xl font-black mb-4">🤖</div>
                <h3 class="text-lg font-black text-slate-900">1-Click Child Bot Maker</h3>
                <p class="text-xs font-semibold text-slate-500 mt-2">बॉटफादर का टोकन डालें और अपना खुद का ऑटोमैटिक रीसेलर टेलीग्राम बॉट तुरंत 24×7 लाइव करें।</p>
            </div>
        </div>

        <!-- Pricing Preview -->
        <h2 class="text-2xl md:text-3xl font-black text-slate-900 mt-16 mb-8">💎 Choose Your 3D Power Plan</h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 text-left">
            {% for k, p in plans.items() %}
            <div class="card-3d p-6 flex flex-col justify-between relative overflow-hidden">
                <div>
                    <span class="inline-block bg-indigo-100 text-indigo-700 text-[10px] font-black px-3 py-1 rounded-full uppercase">{{ p.badge }}</span>
                    <h3 class="text-lg font-black text-slate-900 mt-3">{{ p.label }}</h3>
                    <div class="text-3xl font-black text-indigo-600 mt-2">₹{{ p.price|int }}</div>
                    <div class="mt-3 p-2.5 rounded-xl bg-slate-50 border border-slate-200 text-[11px] font-bold text-slate-600 space-y-1">
                        <div>⚡ <b>One-Time:</b> ₹{{ p.price|int }} Direct</div>
                        <div>🔄 <b>Auto-Sub:</b> Min ₹{{ p.min_sub_wallet|int }} in Wallet</div>
                    </div>
                </div>
                <a href="/dashboard#plans" class="mt-6 block text-center btn-3d-purple py-3 text-xs font-black">Activate Plan →</a>
            </div>
            {% endfor %}
        </div>
    </main>

    <footer class="bg-white border-t-2 border-slate-200 py-6 text-center text-xs font-bold text-slate-500">
        © 2026 PranavSMM.online • 3D Cloud Panel • Admin: <a href="/admin" class="text-indigo-600 underline">Pranav Ji Control</a>
    </footer>
</body>
</html>
"""

AUTH_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - PranavSMM.online</title>
    """ + BASE_STYLE_AND_NAV + """
</head>
<body class="min-h-screen flex flex-col justify-between">
    """ + NAVBAR_COMPONENT + """
    <main class="flex-1 flex items-center justify-center p-5">
        <div class="card-3d p-8 w-full max-w-md">
            <div class="text-center mb-6">
                <div class="w-14 h-14 mx-auto rounded-2xl bg-gradient-to-tr from-indigo-600 to-pink-500 text-white flex items-center justify-center text-2xl font-black shadow-lg mb-3">🔐</div>
                <h2 class="text-2xl font-black text-slate-900">{{ title }}</h2>
                <p class="text-xs font-bold text-slate-500 mt-1">{{ subtitle }}</p>
            </div>
            {% if error %}
            <div class="bg-rose-50 border-2 border-rose-300 text-rose-700 p-3 rounded-2xl text-xs font-extrabold mb-4 text-center">{{ error }}</div>
            {% endif %}
            <form method="POST" class="space-y-4">
                {% if is_register %}
                <div>
                    <label class="block text-xs font-extrabold text-slate-700 mb-1">YOUR FULL NAME</label>
                    <input type="text" name="name" required placeholder="Ex: Rahul Verma" class="w-full bg-slate-50 border-2 border-slate-300 rounded-xl px-4 py-3 text-slate-900 font-bold text-sm focus:outline-none focus:border-indigo-600">
                </div>
                {% endif %}
                <div>
                    <label class="block text-xs font-extrabold text-slate-700 mb-1">{{ 'ADMIN USERNAME' if is_admin else 'EMAIL ADDRESS' }}</label>
                    <input type="{{ 'text' if is_admin else 'email' }}" name="email" required placeholder="{{ 'Enter Admin Username' if is_admin else 'you@gmail.com' }}" class="w-full bg-slate-50 border-2 border-slate-300 rounded-xl px-4 py-3 text-slate-900 font-bold text-sm focus:outline-none focus:border-indigo-600">
                </div>
                <div>
                    <label class="block text-xs font-extrabold text-slate-700 mb-1">PASSWORD</label>
                    <input type="password" name="password" required placeholder="••••••••" class="w-full bg-slate-50 border-2 border-slate-300 rounded-xl px-4 py-3 text-slate-900 font-bold text-sm focus:outline-none focus:border-indigo-600">
                </div>
                <button type="submit" class="w-full btn-3d-purple py-3.5 text-sm font-black mt-2">{{ btn_text }} →</button>
            </form>
            {% if not is_admin %}
            <div class="text-center mt-6 text-xs font-bold text-slate-500">
                {% if is_register %}
                    Already have an account? <a href="/login" class="text-indigo-600 font-black underline">Login Here</a>
                {% else %}
                    New user? <a href="/register" class="text-indigo-600 font-black underline">Create Free Account</a>
                {% endif %}
            </div>
            {% endif %}
        </div>
    </main>
</body>
</html>
"""

USER_DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>3D User Dashboard - PranavSMM.online</title>
    """ + BASE_STYLE_AND_NAV + """
    <script>
        function setFundAmount(val) {
            document.getElementById('fund_amount_input').value = val;
        }
        function openPlanModal(planKey, label, price, minSub) {
            document.getElementById('modal_plan_key').value = planKey;
            document.getElementById('modal_plan_title').innerText = label;
            document.getElementById('modal_onetime_price').innerText = '₹' + price;
            document.getElementById('modal_sub_price').innerText = '₹' + price + ' (Min Wallet ₹' + minSub + ')';
            document.getElementById('plan_modal').classList.remove('hidden');
        }
        function closePlanModal() {
            document.getElementById('plan_modal').classList.add('hidden');
        }
    </script>
</head>
<body class="min-h-screen flex flex-col justify-between">
    """ + NAVBAR_COMPONENT + """

    <main class="max-w-6xl mx-auto px-5 py-8 w-full space-y-8 flex-1">
        {% if msg %}
        <div class="card-3d p-4 border-l-8 border-l-emerald-500 bg-emerald-50 text-emerald-900 font-extrabold text-sm flex justify-between items-center">
            <span>{{ msg }}</span>
        </div>
        {% endif %}
        {% if err %}
        <div class="card-3d p-4 border-l-8 border-l-rose-500 bg-rose-50 text-rose-900 font-extrabold text-sm flex justify-between items-center">
            <span>{{ err }}</span>
        </div>
        {% endif %}

        <!-- Top 3D Status Cards -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div class="card-3d p-6 border-b-8 border-b-emerald-500">
                <div class="flex justify-between items-center">
                    <span class="text-xs font-extrabold text-slate-400 uppercase">My Wallet Balance</span>
                    <span class="px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 text-xs font-black">LIVE</span>
                </div>
                <div class="text-4xl font-black text-slate-900 mt-2">₹{{ "%.2f"|format(user.balance) }}</div>
                <p class="text-xs font-bold text-slate-500 mt-2">Total Deposited: ₹{{ "%.2f"|format(user.total_deposit) }}</p>
            </div>

            <div class="card-3d p-6 border-b-8 border-b-indigo-500">
                <div class="flex justify-between items-center">
                    <span class="text-xs font-extrabold text-slate-400 uppercase">Current Active Plan</span>
                    {% if user.auto_sub == 1 %}
                        <span class="px-2.5 py-1 rounded-full bg-indigo-100 text-indigo-700 text-xs font-black">🔄 AUTO-SUB ON</span>
                    {% else %}
                        <span class="px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 text-xs font-black">⚡ ONE-TIME</span>
                    {% endif %}
                </div>
                <div class="text-2xl font-black text-indigo-600 mt-2">{{ user.active_plan }}</div>
                <p class="text-xs font-bold text-slate-500 mt-2">Expiry: {{ user.sub_expiry or 'No Active Plan' }}</p>
            </div>

            <div class="card-3d p-6 border-b-8 border-b-pink-500 flex flex-col justify-between">
                <div>
                    <span class="text-xs font-extrabold text-slate-400 uppercase">Telegram Master Bot</span>
                    <div class="text-lg font-black text-slate-900 mt-1">Connect & Run Child Bots</div>
                </div>
                <a href="https://t.me/{{ master_bot_uname }}" target="_blank" class="btn-3d-pink py-3 text-center text-xs font-black mt-4 block">🤖 Open @{{ master_bot_uname }} ↗</a>
            </div>
        </div>

        <!-- 💰 SEPARATE ADD FUNDS SECTION (₹100, ₹500, ₹1000, ₹2000) -->
        <div id="add-funds" class="card-3d p-6 md:p-8">
            <h2 class="text-2xl font-black text-slate-900 flex items-center gap-2">💰 Add Funds to Wallet (Separate Balance System)</h2>
            <p class="text-xs font-bold text-slate-500 mt-1">अपने वॉलेट में ₹1000, ₹2000 या मनचाहा बैलेंस ऐड करें। इसी वॉलेट से आप ऑटो-सब्सक्रिप्शन या वन-टाइम प्लान ले सकते हैं।</p>

            <!-- Quick 3D Amount Buttons -->
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5">
                <button type="button" onclick="setFundAmount(100)" class="btn-3d-blue py-3 font-black text-sm">+ ₹100</button>
                <button type="button" onclick="setFundAmount(500)" class="btn-3d-green py-3 font-black text-sm">+ ₹500</button>
                <button type="button" onclick="setFundAmount(1000)" class="btn-3d-orange py-3 font-black text-sm">🔥 + ₹1000</button>
                <button type="button" onclick="setFundAmount(2000)" class="btn-3d-purple py-3 font-black text-sm">💎 + ₹2000</button>
            </div>

            <form method="POST" action="/dashboard/add-funds" class="mt-5 grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                <div>
                    <label class="block text-xs font-extrabold text-slate-700 mb-1">ENTER AMOUNT (₹)</label>
                    <input type="number" id="fund_amount_input" name="amount" value="1000" min="10" required class="w-full bg-slate-50 border-2 border-slate-300 rounded-xl px-4 py-3 text-slate-900 font-black text-base focus:outline-none focus:border-indigo-600">
                </div>
                <div>
                    <label class="block text-xs font-extrabold text-slate-700 mb-1">12-DIGIT UPI UTR / REF NO.</label>
                    <input type="text" name="utr" pattern="\\d{12}" maxlength="12" required placeholder="Pay on QR below & enter 12-digit UTR" class="w-full bg-slate-50 border-2 border-slate-300 rounded-xl px-4 py-3 text-slate-900 font-bold text-sm focus:outline-none focus:border-indigo-600">
                </div>
                <button type="submit" class="btn-3d-green py-3.5 font-black text-sm">✅ Verify & Add Balance</button>
            </form>

            <div class="mt-5 p-4 rounded-2xl bg-slate-50 border-2 border-slate-200 flex flex-col sm:flex-row items-center gap-5">
                <img src="https://api.qrserver.com/v1/create-qr-code/?size=160x160&data={{ upi_qr_data }}" class="w-32 h-32 rounded-2xl border-2 border-white shadow-md" alt="UPI QR">
                <div class="text-xs font-bold text-slate-600 space-y-1.5 text-center sm:text-left">
                    <div class="text-sm font-black text-slate-900">📲 Scan QR with Any UPI App (PhonePe, Paytm, GPay, FamPay)</div>
                    <div>Merchant UPI ID: <span class="bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded font-mono font-black">{{ master_upi }}</span></div>
                    <div class="text-emerald-700 font-extrabold">💡 पेमेंट करने के बाद 12-अंकों का UTR नंबर ऊपर बॉक्स में डालकर Verify दबाएं, बैलेंस तुरंत जुड़ जाएगा!</div>
                </div>
            </div>
        </div>

        <!-- 🎟️ ACTIVATE PLAN (ONE-TIME vs AUTO-SUBSCRIPTION) -->
        <div id="plans" class="card-3d p-6 md:p-8">
            <h2 class="text-2xl font-black text-slate-900">🎟️ Activate Plan & Generate License Key</h2>
            <p class="text-xs font-bold text-slate-500 mt-1">किसी भी प्लान पर टैप करें—आपको <b>One-Time (तुरंत एक बार)</b> और <b>Auto-Subscription (वॉलेट में दोगुना बैलेंस/₹100+ होने पर ऑटो-कट)</b> दोनों ऑप्शन मिलेंगे!</p>

            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mt-6">
                {% for k, p in plans.items() %}
                <div class="card-3d p-5 flex flex-col justify-between border-2 border-slate-200">
                    <div>
                        <span class="bg-purple-100 text-purple-700 text-[10px] font-black px-2.5 py-1 rounded-full">{{ p.badge }}</span>
                        <h3 class="text-lg font-black text-slate-900 mt-2">{{ p.label }}</h3>
                        <div class="text-3xl font-black text-indigo-600 mt-1">₹{{ p.price|int }}</div>
                        <div class="mt-3 text-[11px] font-bold text-slate-600 bg-slate-50 p-2.5 rounded-xl border border-slate-200 space-y-1">
                            <div>⚡ <b>एक बार लें:</b> ₹{{ p.price|int }}</div>
                            <div>🔄 <b>सब्सक्रिप्शन शर्त:</b> वॉलेट में कम से कम <b>₹{{ p.min_sub_wallet|int }}</b> होना चाहिए</div>
                        </div>
                    </div>
                    <button type="button" onclick="openPlanModal('{{ k }}', '{{ p.label }}', {{ p.price|int }}, {{ p.min_sub_wallet|int }})" class="mt-5 w-full btn-3d-purple py-3 text-xs font-black">⚡ Select & Activate</button>
                </div>
                {% endfor %}
            </div>
        </div>

        <!-- 🔑 MY GENERATED LICENSE KEYS -->
        <div class="card-3d p-6 md:p-8">
            <h2 class="text-xl font-black text-slate-900 mb-4">🔑 My Purchased License Keys</h2>
            {% if my_keys %}
            <div class="space-y-3">
                {% for k in my_keys %}
                <div class="p-4 rounded-2xl bg-slate-50 border-2 border-slate-200 flex flex-col sm:flex-row justify-between items-center gap-3">
                    <div>
                        <span class="text-xs font-extrabold text-indigo-600 uppercase">{{ k.label }} ({{ '🔄 Auto-Sub' if k.is_sub else '⚡ One-Time' }})</span>
                        <div class="font-mono font-black text-sm text-slate-900 select-all mt-0.5">{{ k.key_code }}</div>
                    </div>
                    <span class="px-3 py-1 rounded-full text-xs font-black {{ 'bg-rose-100 text-rose-700' if k.is_used else 'bg-emerald-100 text-emerald-700' }}">
                        {{ 'Used on Bot' if k.is_used else '🟢 Ready to Activate in Bot' }}
                    </span>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <p class="text-xs font-bold text-slate-400">अभी तक कोई लाइसेंस की जनरेट नहीं की गई है। ऊपर दिए गए प्लान्स में से चुनें!</p>
            {% endif %}
        </div>
    </main>

    <!-- 3D MODAL FOR ONE-TIME VS AUTO-SUBSCRIPTION -->
    <div id="plan_modal" class="fixed inset-0 bg-slate-900/50 backdrop-blur-xs z-50 hidden flex items-center justify-center p-4">
        <div class="card-3d p-6 md:p-8 max-w-md w-full">
            <div class="flex justify-between items-center pb-3 border-b-2 border-slate-100">
                <h3 id="modal_plan_title" class="text-xl font-black text-slate-900">Activate Plan</h3>
                <button onclick="closePlanModal()" class="w-8 h-8 rounded-xl bg-rose-100 text-rose-600 font-black">✕</button>
            </div>
            <p class="text-xs font-bold text-slate-600 mt-3">प्रणव जी के स्मार्ट सिस्टम में चुनें कि आप यह प्लान कैसे लेना चाहते हैं:</p>

            <form method="POST" action="/dashboard/buy-plan" class="mt-5 space-y-4">
                <input type="hidden" name="plan_key" id="modal_plan_key" value="30">
                
                <!-- Option 1: Instant One-Time -->
                <button type="submit" name="buy_mode" value="onetime" class="w-full text-left p-4 rounded-2xl border-2 border-indigo-300 bg-indigo-50/70 hover:bg-indigo-100 transition flex justify-between items-center">
                    <div>
                        <div class="font-black text-sm text-indigo-950">⚡ 1. तुरंत एक ही बार लें (One-Time Buy)</div>
                        <div class="text-[11px] font-bold text-indigo-700 mt-0.5">सिर्फ एक बार पैसे कटेंगे, अपने आप रिन्यू नहीं होगा।</div>
                    </div>
                    <span id="modal_onetime_price" class="font-black text-base text-indigo-700">₹49</span>
                </button>

                <!-- Option 2: Auto-Subscription (2x Wallet Rule) -->
                <button type="submit" name="buy_mode" value="subscription" class="w-full text-left p-4 rounded-2xl border-2 border-emerald-300 bg-emerald-50/70 hover:bg-emerald-100 transition flex justify-between items-center">
                    <div>
                        <div class="font-black text-sm text-emerald-950">🔄 2. ऑटो-सब्सक्रिप्शन (Auto-Renew Mode)</div>
                        <div class="text-[11px] font-bold text-emerald-700 mt-0.5">वॉलेट में दोगुना बैलेंस (Min ₹100 / 2x) होना जरूरी। अपने आप रिन्यू होगा!</div>
                        <div id="modal_sub_price" class="text-xs font-black text-emerald-800 mt-1">₹49</div>
                    </div>
                    <span class="bg-emerald-600 text-white text-[10px] font-black px-2.5 py-1 rounded-lg">AUTO</span>
                </button>
            </form>
        </div>
    </div>
</body>
</html>
"""

ADMIN_DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>👑 Pranav Ji 3D Master Admin Control</title>
    """ + BASE_STYLE_AND_NAV + """
</head>
<body class="min-h-screen flex flex-col justify-between">
    """ + NAVBAR_COMPONENT + """

    <main class="max-w-6xl mx-auto px-5 py-8 w-full space-y-8 flex-1">
        <div class="card-3d p-6 bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 text-white flex flex-col sm:flex-row justify-between items-center gap-4">
            <div>
                <span class="bg-white/20 px-3 py-1 rounded-full text-xs font-black uppercase">GOD MASTER CONTROL</span>
                <h1 class="text-2xl md:text-3xl font-black mt-2">👑 स्वागत है प्रणव जी! (Full Control Panel)</h1>
                <p class="text-xs font-bold text-white/90">यहाँ से पूरी pranavsmm.online वेबसाइट, वॉलेट बैलेंस, UPI ID और टेलीग्राम बॉट्स आपके कंट्रोल में हैं।</p>
            </div>
            <a href="/admin/logout" class="btn-3d-white px-5 py-2.5 text-xs font-black shrink-0">🚪 Admin Logout</a>
        </div>

        {% if msg %}
        <div class="card-3d p-4 border-l-8 border-l-emerald-500 bg-emerald-50 text-emerald-900 font-extrabold text-sm">{{ msg }}</div>
        {% endif %}

        <!-- Stats Grid -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="card-3d p-5 border-b-4 border-b-indigo-500">
                <div class="text-xs font-extrabold text-slate-400">WEB USERS</div>
                <div class="text-3xl font-black text-slate-900 mt-1">{{ total_web_users }}</div>
            </div>
            <div class="card-3d p-5 border-b-4 border-b-emerald-500">
                <div class="text-xs font-extrabold text-slate-400">BOT CLIENTS</div>
                <div class="text-3xl font-black text-slate-900 mt-1">{{ total_bot_users }}</div>
            </div>
            <div class="card-3d p-5 border-b-4 border-b-purple-500">
                <div class="text-xs font-extrabold text-slate-400">CHILD BOTS</div>
                <div class="text-3xl font-black text-slate-900 mt-1">{{ total_bots }}</div>
            </div>
            <div class="card-3d p-5 border-b-4 border-b-amber-500">
                <div class="text-xs font-extrabold text-slate-400">24×7 STATUS</div>
                <div class="text-2xl font-black text-emerald-600 mt-1">ACTIVE ⚡</div>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- 🎟️ Generate License Keys (7D, 1M, 3M, Lifetime) -->
            <div class="card-3d p-6">
                <h3 class="text-lg font-black text-slate-900 mb-3">🎟️ Instant Free Key Generator (For Bot & Web)</h3>
                <form method="POST" action="/admin/action" class="space-y-4">
                    <input type="hidden" name="act" value="gen_key">
                    <div>
                        <label class="block text-xs font-extrabold text-slate-600 mb-1">SELECT PLAN DURATION</label>
                        <select name="duration" class="w-full bg-slate-50 border-2 border-slate-300 rounded-xl px-4 py-3 font-bold text-sm">
                            <option value="7">7 Days Trial (₹49)</option>
                            <option value="30" selected>1 Month Elite (₹149)</option>
                            <option value="90">3 Months Master (₹399)</option>
                            <option value="36500">👑 Lifetime God Mode (₹999)</option>
                        </select>
                    </div>
                    <button type="submit" class="w-full btn-3d-purple py-3 text-sm font-black">⚡ Generate License Key Now</button>
                </form>
                {% if gen_key %}
                <div class="mt-4 p-4 rounded-2xl bg-indigo-50 border-2 border-indigo-300 text-center">
                    <div class="text-xs font-extrabold text-indigo-600">NEW LICENSE KEY READY:</div>
                    <div class="font-mono text-base font-black text-slate-900 select-all mt-1">{{ gen_key }}</div>
                </div>
                {% endif %}
            </div>

            <!-- 💳 Update Master UPI & Add User Wallet Balance -->
            <div class="card-3d p-6 space-y-6">
                <form method="POST" action="/admin/action" class="space-y-3">
                    <input type="hidden" name="act" value="update_upi">
                    <h3 class="text-lg font-black text-slate-900">💳 Master UPI Gateway ID</h3>
                    <div class="flex gap-2">
                        <input type="text" name="upi_id" value="{{ master_upi }}" required class="flex-1 bg-slate-50 border-2 border-slate-300 rounded-xl px-4 py-2.5 font-bold text-sm">
                        <button type="submit" class="btn-3d-green px-5 py-2.5 text-xs font-black">Save UPI</button>
                    </div>
                </form>

                <form method="POST" action="/admin/action" class="space-y-3 pt-4 border-t-2 border-slate-100">
                    <input type="hidden" name="act" value="add_web_bal">
                    <h3 class="text-lg font-black text-slate-900">💰 Add Balance to Web User Email</h3>
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
                        <input type="email" name="email" placeholder="User Email" required class="sm:col-span-2 bg-slate-50 border-2 border-slate-300 rounded-xl px-3 py-2.5 font-bold text-xs">
                        <input type="number" name="amount" placeholder="₹ Amount" required class="bg-slate-50 border-2 border-slate-300 rounded-xl px-3 py-2.5 font-bold text-xs">
                    </div>
                    <button type="submit" class="w-full btn-3d-blue py-2.5 text-xs font-black">➕ Credit Balance Immediately</button>
                </form>
            </div>
        </div>
    </main>
</body>
</html>
"""

# ==========================================
# 🌐 FLASK ROUTES & CONTROLLERS
# ==========================================
def get_master_bot_uname():
    row = fetch_query("SELECT bot_username FROM child_bots WHERE bot_id=0", fetchone=True)
    return row["bot_username"] if row else "PranavFatherDevBot"

@app.route('/ping')
def ping():
    return jsonify({"status": "alive", "engine": "Pranav 3D v5.0", "time": str(datetime.datetime.now())})

@app.route('/')
def home():
    return render_template_string(HOME_HTML, plans=PLANS_CATALOG, master_bot_uname=get_master_bot_uname())

@app.route('/login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        email = request.form.get("email", "").strip().lower()
        pwd = request.form.get("password", "").strip()
        user = fetch_query("SELECT * FROM web_users WHERE email=? AND password=?", (email, pwd), fetchone=True)
        if user:
            session['user_id'] = user["id"]
            return redirect(url_for('user_dashboard'))
        return render_template_string(AUTH_HTML, title="User Login", subtitle="Access your 3D PranavSMM Panel", btn_text="Login Now", is_register=False, is_admin=False, error="❌ ईमेल या पासवर्ड गलत है!", master_bot_uname=get_master_bot_uname())
    return render_template_string(AUTH_HTML, title="User Login", subtitle="Access your 3D PranavSMM Panel", btn_text="Login Now", is_register=False, is_admin=False, master_bot_uname=get_master_bot_uname())

@app.route('/register', methods=['GET', 'POST'])
def user_register():
    if request.method == 'POST':
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        pwd = request.form.get("password", "").strip()
        existing = fetch_query("SELECT id FROM web_users WHERE email=?", (email,), fetchone=True)
        if existing:
            return render_template_string(AUTH_HTML, title="Create Account", subtitle="Join PranavSMM 3D Panel", btn_text="Create Account", is_register=True, is_admin=False, error="❌ यह ईमेल पहले से रजिस्टर है!", master_bot_uname=get_master_bot_uname())
        execute_query("INSERT INTO web_users (name, email, password, balance) VALUES (?, ?, ?, 0.0)", (name, email, pwd))
        user = fetch_query("SELECT * FROM web_users WHERE email=?", (email,), fetchone=True)
        session['user_id'] = user["id"]
        return redirect(url_for('user_dashboard'))
    return render_template_string(AUTH_HTML, title="Create Account", subtitle="Join PranavSMM 3D Panel", btn_text="Create Account", is_register=True, is_admin=False, master_bot_uname=get_master_bot_uname())

@app.route('/dashboard')
def user_dashboard():
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    user = fetch_query("SELECT * FROM web_users WHERE id=?", (session['user_id'],), fetchone=True)
    if not user:
        session.pop('user_id', None)
        return redirect(url_for('user_login'))
    my_keys = fetch_query("SELECT * FROM license_keys WHERE used_by_user_id=? ORDER BY created_at DESC", (user["id"],))
    m_upi = get_master_upi()
    qr_data = urllib.parse.quote(f"upi://pay?pa={m_upi}&pn=PranavSMM&cu=INR")
    msg = session.pop('dash_msg', None)
    err = session.pop('dash_err', None)
    return render_template_string(USER_DASHBOARD_HTML, user=user, plans=PLANS_CATALOG, my_keys=my_keys, master_upi=m_upi, upi_qr_data=qr_data, msg=msg, err=err, master_bot_uname=get_master_bot_uname())

@app.route('/dashboard/add-funds', methods=['POST'])
def web_add_funds():
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    uid = session['user_id']
    amt = float(request.form.get("amount", 0))
    utr = request.form.get("utr", "").strip()
    if amt < 10 or len(utr) != 12 or not utr.isdigit():
        session['dash_err'] = "❌ कृपया सही अमाउंट और 12-अंकों का UTR नंबर डालें!"
        return redirect(url_for('user_dashboard'))
    used = fetch_query("SELECT tx_id FROM transactions WHERE bank_utr=?", (utr,), fetchone=True)
    if used:
        session['dash_err'] = "❌ यह UTR नंबर पहले ही इस्तेमाल हो चुका है!"
        return redirect(url_for('user_dashboard'))
    tx_id = f"WEB{int(time.time())}{random.randint(100,999)}"
    execute_query("INSERT INTO transactions (tx_id, web_user_id, amount, tx_type, bank_utr, status) VALUES (?, ?, ?, 'web_deposit', ?, 'completed')", (tx_id, uid, amt, utr))
    execute_query("UPDATE web_users SET balance = balance + ?, total_deposit = total_deposit + ? WHERE id=?", (amt, amt, uid))
    session['dash_msg'] = f"🎉 ₹{amt:.2f} आपके वॉलेट में सफलतापूर्वक जुड़ गया है! (UTR: {utr})"
    return redirect(url_for('user_dashboard'))

@app.route('/dashboard/buy-plan', methods=['POST'])
def web_buy_plan():
    if not session.get('user_id'):
        return redirect(url_for('user_login'))
    uid = session['user_id']
    plan_key = request.form.get("plan_key", "30")
    buy_mode = request.form.get("buy_mode", "onetime")
    plan = PLANS_CATALOG.get(plan_key, PLANS_CATALOG["30"])

    user = fetch_query("SELECT * FROM web_users WHERE id=?", (uid,), fetchone=True)
    price = plan["price"]
    min_sub_wallet = plan["min_sub_wallet"]

    if buy_mode == "subscription":
        # Check 2x / Min ₹100 rule requested by Pranav
        if user["balance"] < min_sub_wallet:
            session['dash_err'] = f"⚠️ ऑटो-सब्सक्रिप्शन चालू करने के लिए आपके वॉलेट में कम से कम ₹{min_sub_wallet:.0f} (दोगुना बैलेंस) होना जरूरी है! अभी आपका बैलेंस ₹{user['balance']:.2f} है। कृपया पहले Add Funds करें या One-Time चुनें।"
            return redirect(url_for('user_dashboard'))
        is_sub_flag = 1
    else:
        if user["balance"] < price:
            session['dash_err'] = f"⚠️ आपके वॉलेट में पर्याप्त बैलेंस नहीं है! प्लान की कीमत ₹{price:.0f} है, कृपया ऊपर Add Funds से रिचार्ज करें।"
            return redirect(url_for('user_dashboard'))
        is_sub_flag = 0

    exp_dt = (datetime.datetime.now() + datetime.timedelta(days=plan["days"])).strftime("%Y-%m-%d %H:%M:%S")
    rand_str = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    key_code = f"PRANAV-{plan['days']}D-{rand_str}"

    execute_query("UPDATE web_users SET balance = balance - ?, auto_sub=?, active_plan=?, plan_price=?, plan_days=?, sub_expiry=? WHERE id=?",
                  (price, is_sub_flag, plan["label"], price, plan["days"], exp_dt, uid))
    execute_query("INSERT INTO license_keys (key_code, duration_days, price, label, is_sub, used_by_user_id, is_used) VALUES (?, ?, ?, ?, ?, ?, 0)",
                  (key_code, plan["days"], price, plan["label"], is_sub_flag, uid))

    mode_txt = "🔄 ऑटो-सब्सक्रिप्शन मोड" if is_sub_flag else "⚡ वन-टाइम मोड"
    session['dash_msg'] = f"🎉 बधाई हो! {plan['label']} ({mode_txt}) एक्टिवेट हो गया! आपकी नई Key नीचे जनरेट हो गई है: {key_code}"
    return redirect(url_for('user_dashboard'))

@app.route('/logout')
def user_logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        u = request.form.get("email", "").strip()
        p = request.form.get("password", "").strip()
        if u == WEB_ADMIN_USER and p == WEB_ADMIN_PASS:
            session['admin_logged'] = True
            return redirect(url_for('admin_panel'))
        return render_template_string(AUTH_HTML, title="👑 Pranav Admin Login", subtitle="Restricted Master Control", btn_text="Unlock Admin Panel", is_register=False, is_admin=True, error="❌ गलत एडमिन यूजरनेम या पासवर्ड!", master_bot_uname=get_master_bot_uname())

    if not session.get('admin_logged'):
        return render_template_string(AUTH_HTML, title="👑 Pranav Admin Login", subtitle="Restricted Master Control", btn_text="Unlock Admin Panel", is_register=False, is_admin=True, master_bot_uname=get_master_bot_uname())

    total_bots = fetch_query("SELECT COUNT(*) as c FROM child_bots WHERE bot_id > 0", fetchone=True)["c"]
    total_web_users = fetch_query("SELECT COUNT(*) as c FROM web_users", fetchone=True)["c"]
    total_bot_users = fetch_query("SELECT COUNT(*) as c FROM bot_clients", fetchone=True)["c"]
    gen_key = session.pop('adm_gen_key', None)
    msg = session.pop('adm_msg', None)
    return render_template_string(ADMIN_DASHBOARD_HTML, total_bots=total_bots, total_web_users=total_web_users, total_bot_users=total_bot_users, master_upi=get_master_upi(), gen_key=gen_key, msg=msg, master_bot_uname=get_master_bot_uname())

@app.route('/admin/action', methods=['POST'])
def admin_action():
    if not session.get('admin_logged'):
        return redirect(url_for('admin_panel'))
    act = request.form.get("act")
    if act == "gen_key":
        d = request.form.get("duration", "30")
        plan = PLANS_CATALOG.get(d, PLANS_CATALOG["30"])
        rand_str = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        k = f"PRANAV-{plan['days']}D-{rand_str}"
        execute_query("INSERT INTO license_keys (key_code, duration_days, price, label) VALUES (?, ?, ?, ?)", (k, plan["days"], plan["price"], plan["label"]))
        session['adm_gen_key'] = k
        session['adm_msg'] = f"✅ {plan['label']} की नई लाइसेंस Key जनरेट हो गई!"
    elif act == "update_upi":
        new_upi = request.form.get("upi_id", "").strip()
        execute_query("UPDATE child_bots SET upi_id=? WHERE bot_id=0", (new_upi,))
        session['adm_msg'] = f"✅ मास्टर UPI ID अपडेट हो गई: {new_upi}"
    elif act == "add_web_bal":
        em = request.form.get("email", "").strip().lower()
        amt = float(request.form.get("amount", 0))
        execute_query("UPDATE web_users SET balance = balance + ?, total_deposit = total_deposit + ? WHERE email=?", (amt, amt, em))
        session['adm_msg'] = f"✅ {em} के वॉलेट में ₹{amt:.2f} जोड़ दिया गया!"
    return redirect(url_for('admin_panel'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged', None)
    return redirect(url_for('admin_panel'))

# ==========================================
# 🤖 TELEGRAM BOT ENGINE (100% WORKING BUTTONS)
# ==========================================
def safe_send(bot, chat_id, text, reply_markup=None):
    try:
        return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception as e:
        print(f"[BOT SEND ERR] {e}")

def safe_edit(bot, text, chat_id, message_id, reply_markup=None):
    try:
        return bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except:
        return safe_send(bot, chat_id, text, reply_markup=reply_markup)

def is_bot_active(bot_id):
    if bot_id == 0:
        return True, "👑 Lifetime God Master"
    row = fetch_query("SELECT is_licensed, subscription_expiry, status FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
    if not row or row["is_licensed"] == 0:
        return False, "❌ Gateway License Not Activated! (/admin में जाकर Key डालें)"
    if row["status"] == "suspended":
        return False, "🚫 Bot Suspended by Master Admin"
    return True, f"🟢 Active (Exp: {row['subscription_expiry']})"

def get_user_main_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("💳 My Wallet", callback_data="u_bal"),
        types.InlineKeyboardButton("➕ Add Funds (₹1000/2000)", callback_data="u_dep")
    )
    m.add(
        types.InlineKeyboardButton("🎟️ Buy Plan / Key", callback_data="u_plans"),
        types.InlineKeyboardButton("🛒 Order SMM Service", callback_data="u_ord")
    )
    m.add(
        types.InlineKeyboardButton("🗓️ Order History", callback_data="u_hist"),
        types.InlineKeyboardButton("🤖 Create Child Bot", callback_data="u_cyob")
    )
    m.add(
        types.InlineKeyboardButton("🌐 Open PranavSMM.online ↗", url="https://pranavsmm.online"),
        types.InlineKeyboardButton("🎧 Support", callback_data="u_supp")
    )
    return m

def get_owner_panel(is_master=False):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("💳 Change UPI ID", callback_data="a_payment"),
        types.InlineKeyboardButton("⚙️ Add SMM Service", callback_data="a_services")
    )
    m.add(
        types.InlineKeyboardButton("👥 Add User Balance", callback_data="a_users"),
        types.InlineKeyboardButton("🔑 License Key Status", callback_data="a_license_info")
    )
    if is_master:
        m.add(
            types.InlineKeyboardButton("🎟️ Generate Free Keys", callback_data="adm_gen_menu"),
            types.InlineKeyboardButton("🤖 All Child Bots", callback_data="adm_list_bots")
        )
    m.add(types.InlineKeyboardButton("🌐 Open Admin Website ↗", url="https://pranavsmm.online/admin"))
    m.add(types.InlineKeyboardButton("🔙 Back to User Menu", callback_data="u_back_main"))
    return m

def build_deposit_keypad(curr_amt=""):
    m = types.InlineKeyboardMarkup(row_width=3)
    disp = curr_amt if curr_amt else "0"
    # Quick Add Buttons (₹100, ₹500, ₹1000, ₹2000)
    m.add(
        types.InlineKeyboardButton("⚡ ₹100", callback_data="qdep_100"),
        types.InlineKeyboardButton("⚡ ₹500", callback_data="qdep_500"),
        types.InlineKeyboardButton("🔥 ₹1000", callback_data="qdep_1000"),
        types.InlineKeyboardButton("💎 ₹2000", callback_data="qdep_2000")
    )
    m.add(types.InlineKeyboardButton("1", callback_data="kp_1"), types.InlineKeyboardButton("2", callback_data="kp_2"), types.InlineKeyboardButton("3", callback_data="kp_3"))
    m.add(types.InlineKeyboardButton("4", callback_data="kp_4"), types.InlineKeyboardButton("5", callback_data="kp_5"), types.InlineKeyboardButton("6", callback_data="kp_6"))
    m.add(types.InlineKeyboardButton("7", callback_data="kp_7"), types.InlineKeyboardButton("8", callback_data="kp_8"), types.InlineKeyboardButton("9", callback_data="kp_9"))
    m.add(types.InlineKeyboardButton("0", callback_data="kp_0"), types.InlineKeyboardButton("00", callback_data="kp_00"), types.InlineKeyboardButton("⌫", callback_data="kp_clear"))
    m.add(types.InlineKeyboardButton("🛑 CANCEL", callback_data="kp_cancel"), types.InlineKeyboardButton("✅ GENERATE QR", callback_data="kp_confirm"))
    return m, disp

def send_qr_for_amount(bot, bot_id, uid, cid, mid, amt):
    utr_id = f"DEP{int(time.time())}{random.randint(100, 999)}"
    target_upi = get_bot_upi(bot_id)
    execute_query("INSERT INTO transactions (tx_id, bot_id, user_id, amount, tx_type, status) VALUES (?, ?, ?, ?, 'deposit', 'pending')", (utr_id, bot_id, uid, amt))
    user_states[f"{bot_id}_{uid}"] = {"step": "wait_manual_utr", "tx_id": utr_id}
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(f'upi://pay?pa={target_upi}&pn=PranavSMM&am={amt:.2f}&cu=INR')}"
    try:
        bot.delete_message(cid, mid)
    except:
        pass
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔢 SUBMIT 12-DIGIT UTR", callback_data=f"sub_utr_{utr_id}"))
    kb.add(types.InlineKeyboardButton("🔙 Cancel", callback_data="u_back_main"))
    bot.send_photo(cid, qr_url, caption=f"⚡ 𝗔𝗨𝗧𝗢𝗠𝗔𝗧𝗘𝗗 𝗨𝗣𝗜 𝗚𝗔𝗧𝗘𝗪𝗔𝗬\n\n💵 Amount: ₹{amt:.2f}\n🏦 UPI ID: `{target_upi}`\n🆔 Order ID: `{utr_id}`\n\n📲 QR स्कैन करके पेमेंट करें और अपना 12-अंकों का UTR नंबर चैट में भेजें!", reply_markup=kb, parse_mode="Markdown")

def handle_user_callbacks(bot, bot_id, call):
    try:
        uid, cid, mid, data = call.from_user.id, call.message.chat.id, call.message.message_id, call.data
    except:
        return

    execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)", (bot_id, uid, call.from_user.username or "User"))

    if data in ["u_continue_main", "u_back_main", "a_back_main"]:
        user_states.pop(f"{bot_id}_{uid}", None)
        safe_edit(bot, "✨ 𝗣𝗥𝗔𝗡𝗔𝗩 𝗦𝗠𝗠 𝟯𝗗 𝗣𝗔𝗡𝗘𝗟 ✨\n\n👇 नीचे दिए गए रंग-बिरंगे मेन्यू से अपनी सर्विस चुनें:", cid, mid, reply_markup=get_user_main_menu())

    elif data == "u_bal":
        row = fetch_query("SELECT balance, total_deposit, total_spent, auto_sub, sub_plan, sub_expiry FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        bal = row["balance"] if row else 0.0
        tdep = row["total_deposit"] if row else 0.0
        tsp = row["total_spent"] if row else 0.0
        sub_mode = "🔄 Auto-Sub ON" if (row and row["auto_sub"] == 1) else "⚡ One-Time Mode"
        sub_pl = row["sub_plan"] if row else "None"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"), types.InlineKeyboardButton("🎟️ Buy Plan", callback_data="u_plans"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
        safe_edit(bot, f"🛡️ 𝗬𝗢𝗨𝗥 𝟯𝗗 𝗪𝗔𝗟𝗟𝗘𝗧 𝗜𝗡𝗙𝗢\n\n💰 Available Balance: ₹{bal:.2f}\n📈 Total Deposited: ₹{tdep:.2f}\n🛒 Total Spent: ₹{tsp:.2f}\n🎖️ Active Plan: {sub_pl} ({sub_mode})\n🆔 Your ID: `{uid}`", cid, mid, reply_markup=kb)

    elif data == "u_dep":
        act, rsn = is_bot_active(bot_id)
        if not act:
            return safe_edit(bot, f"⚠️ 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗢𝗖𝗞𝗘𝗗\n\n{rsn}", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")))
        keypad_amounts[f"{bot_id}_{uid}"] = ""
        kp, disp = build_deposit_keypad("")
        safe_edit(bot, f"💰 𝗔𝗗𝗗 𝗙𝗨𝗡𝗗𝗦 𝗧𝗢 𝗪𝗔𝗟𝗟𝗘𝗧\n\nऊपर दिए गए ₹100, ₹500, ₹1000, ₹2000 बटन दबाएं या कीपैड से अमाउंट टाइप करें:\n\n💵 Selected Amount: ₹{disp}", cid, mid, reply_markup=kp)

    elif data.startswith("qdep_"):
        amt = float(data.replace("qdep_", ""))
        send_qr_for_amount(bot, bot_id, uid, cid, mid, amt)

    elif data.startswith("kp_"):
        act = data.replace("kp_", "")
        k_key = f"{bot_id}_{uid}"
        cur_amt = keypad_amounts.get(k_key, "")
        if act == "cancel":
            keypad_amounts.pop(k_key, None)
            return safe_edit(bot, "❌ रिचार्ज कैंसिल कर दिया गया।", cid, mid, reply_markup=get_user_main_menu())
        elif act == "clear":
            cur_amt = cur_amt[:-1] if len(cur_amt) > 1 else ""
        elif act in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "00"]:
            if len(cur_amt) < 6:
                cur_amt += act
        elif act == "confirm":
            if not cur_amt or int(cur_amt) < 10:
                return bot.answer_callback_query(call.id, "⚠️ कम से कम ₹10 दर्ज करें!", show_alert=True)
            amt = float(cur_amt)
            keypad_amounts.pop(k_key, None)
            return send_qr_for_amount(bot, bot_id, uid, cid, mid, amt)
        keypad_amounts[k_key] = cur_amt
        kp, disp = build_deposit_keypad(cur_amt)
        safe_edit(bot, f"💰 𝗔𝗗𝗗 𝗙𝗨𝗡𝗗𝗦 𝗧𝗢 𝗪𝗔𝗟𝗟𝗘𝗧\n\n💵 Selected Amount: ₹{disp}", cid, mid, reply_markup=kp)

    elif data.startswith("sub_utr_"):
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_manual_utr", "tx_id": data.replace("sub_utr_", "")}
        safe_send(bot, cid, "🔢 कृपया अपना 12-अंकों का UTR / Ref नंबर चैट में भेजें:")

    # 🎟️ BUY PLANS (ONE-TIME VS SUBSCRIPTION)
    elif data == "u_plans":
        kb = types.InlineKeyboardMarkup(row_width=1)
        for k, p in PLANS_CATALOG.items():
            kb.add(types.InlineKeyboardButton(f"💎 {p['label']} - ₹{int(p['price'])}", callback_data=f"selplan_{k}"))
        kb.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="u_back_main"))
        safe_edit(bot, "🎟️ 𝗦𝗘𝗟𝗘𝗖𝗧 𝗣𝗟𝗔𝗡 / 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗞𝗘𝗬\n\nप्रणव जी के पैनल में आप किसी भी प्लान पर टैप करके उसे **एक बार (One-Time)** या **ऑटो-सब्सक्रिप्शन (Auto-Renew)** मोड में ले सकते हैं:", cid, mid, reply_markup=kb)

    elif data.startswith("selplan_"):
        pk = data.replace("selplan_", "")
        p = PLANS_CATALOG.get(pk, PLANS_CATALOG["30"])
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton(f"⚡ 1. तुरंत एक बार लें (₹{int(p['price'])})", callback_data=f"buyplan_one_{pk}"),
            types.InlineKeyboardButton(f"🔄 2. ऑटो-सब्सक्रिप्शन (Min Wallet ₹{int(p['min_sub_wallet'])})", callback_data=f"buyplan_sub_{pk}"),
            types.InlineKeyboardButton("🔙 Back to Plans", callback_data="u_plans")
        )
        safe_edit(bot, f"💎 **{p['label']}**\n💵 कीमत: ₹{int(p['price'])}\n\n👇 **अपना पेमेंट मोड चुनें:**\n1️⃣ **One-Time Buy:** वॉलेट से सिर्फ ₹{int(p['price'])} कटेगा और तुरंत Key मिलेगी।\n2️⃣ **Auto-Subscription:** वॉलेट में कम से कम दोगुना बैलेंस (**₹{int(p['min_sub_wallet'])}**) होना जरूरी है। समय पूरा होने पर अपने आप रिन्यू हो जाएगा!", cid, mid, reply_markup=kb)

    elif data.startswith("buyplan_"):
        parts = data.split("_")
        mode = parts[1]  # 'one' or 'sub'
        pk = parts[2]
        p = PLANS_CATALOG.get(pk, PLANS_CATALOG["30"])
        row = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        bal = row["balance"] if row else 0.0

        if mode == "sub":
            if bal < p["min_sub_wallet"]:
                return bot.answer_callback_query(call.id, f"⚠️ ऑटो-सब्सक्रिप्शन के लिए वॉलेट में कम से कम ₹{int(p['min_sub_wallet'])} (दोगुना बैलेंस) होना चाहिए! अभी ₹{bal:.0f} है। पहले Add Funds करें!", show_alert=True)
            is_sub_flag = 1
        else:
            if bal < p["price"]:
                return bot.answer_callback_query(call.id, f"⚠️ वॉलेट में ₹{int(p['price'])} नहीं है! कृपया पहले Add Funds से बैलेंस जोड़ें।", show_alert=True)
            is_sub_flag = 0

        exp_dt = (datetime.datetime.now() + datetime.timedelta(days=p["days"])).strftime("%Y-%m-%d %H:%M:%S")
        rand_str = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        key_code = f"PRANAV-{p['days']}D-{rand_str}"

        execute_query("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ?, auto_sub=?, sub_plan=?, sub_expiry=? WHERE bot_id=? AND user_id=?",
                      (p["price"], p["price"], is_sub_flag, p["label"], exp_dt, bot_id, uid))
        execute_query("INSERT INTO license_keys (key_code, duration_days, price, label, is_sub, used_by_user_id, is_used) VALUES (?, ?, ?, ?, ?, ?, 0)",
                      (key_code, p["days"], p["price"], p["label"], is_sub_flag, uid))

        m_label = "🔄 Auto-Subscription" if is_sub_flag else "⚡ One-Time"
        safe_edit(bot, f"🎉 **𝗣𝗟𝗔𝗡 𝗔𝗖𝗧𝗜𝗩𝗔𝗧𝗘𝗗 & 𝗞𝗘𝗬 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘𝗗!**\n\n📦 Plan: {p['label']} ({m_label})\n🔑 Your License Key:\n`{key_code}`\n\n💡 इस Key को कॉपी करें और अपने बॉट में `/admin` -> `🔑 License Key Status` में जाकर एक्टिवेट कर लें!", cid, mid, reply_markup=get_user_main_menu())

    # 🛒 ORDER SMM SERVICES
    elif data == "u_ord":
        srvs = fetch_query("SELECT * FROM smm_services WHERE bot_id=? OR bot_id=0", (bot_id,))
        kb = types.InlineKeyboardMarkup(row_width=1)
        for s in srvs:
            kb.add(types.InlineKeyboardButton(f"{s['service_name']} (₹{s['rate_per_1000']}/1k)", callback_data=f"ord_srv_{s['id']}"))
        kb.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="u_back_main"))
        safe_edit(bot, "🛒 **𝗦𝗘𝗟𝗘𝗖𝗧 𝗦𝗠𝗠 𝗦𝗘𝗥𝗩𝗜𝗖𝗘**\n\nनीचे दी गई लिस्ट में से अपनी सर्विस चुनें:", cid, mid, reply_markup=kb)

    elif data.startswith("ord_srv_"):
        sid = int(data.replace("ord_srv_", ""))
        srv = fetch_query("SELECT * FROM smm_services WHERE id=?", (sid,), fetchone=True)
        if not srv:
            return
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_ord_link", "srv_id": sid, "srv_name": srv["service_name"], "rate": srv["rate_per_1000"]}
        safe_edit(bot, f"🛒 **{srv['service_name']}**\n💵 Rate: ₹{srv['rate_per_1000']} per 1000\n\n🔗 **कृपया अपना Instagram/YouTube/Telegram पोस्ट या प्रोफाइल लिंक चैट में भेजें:**", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Cancel", callback_data="u_back_main")))

    # 🗓️ ORDER HISTORY
    elif data == "u_hist":
        ords = fetch_query("SELECT * FROM bot_orders WHERE bot_id=? AND user_id=? ORDER BY id DESC LIMIT 8", (bot_id, uid))
        if not ords:
            txt = "🗓️ **𝗢𝗥𝗗𝗘𝗥 𝗛𝗜𝗦𝗧𝗢𝗥𝗬**\n\nआपने अभी तक कोई ऑर्डर नहीं लगाया है।"
        else:
            txt = "🗓️ **𝗬𝗢𝗨𝗥 𝗥𝗘𝗖𝗘𝗡𝗧 𝗢𝗥𝗗𝗘𝗥𝗦:**\n\n"
            for o in ords:
                txt += f"🆔 `#{o['id']}` • {o['service_name']}\n🔢 Qty: {o['quantity']} | 💵 ₹{o['charge']:.2f} | {o['status']}\n\n"
        safe_edit(bot, txt, cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main")))

    # 🤖 CREATE CHILD BOT (CYOB)
    elif data == "u_cyob":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("➕ Add BotFather Token", callback_data="m_add_bot"))
        kb.add(types.InlineKeyboardButton("🎟️ Buy License Key", callback_data="u_plans"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
        safe_edit(bot, "🤖 **𝗖𝗥𝗘𝗔𝗧𝗘 𝗬𝗢𝗨𝗥 𝗢𝗪𝗡 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗕𝗢𝗧**\n\n1️⃣ @BotFather पर जाकर नया बॉट बनाएं और उसका API Token कॉपी करें।\n2️⃣ नीचे **Add BotFather Token** पर क्लिक करके टोकन भेजें—आपका बॉट 1 सेकंड में 24×7 लाइव हो जाएगा!", cid, mid, reply_markup=kb)

    elif data == "m_add_bot":
        user_states[f"{bot_id}_{uid}"] = "wait_token"
        safe_edit(bot, "🏆 **𝗦𝗨𝗕𝗠𝗜𝗧 𝗕𝗢𝗧𝗙𝗔𝗧𝗛𝗘𝗥 𝗧𝗢𝗞𝗘𝗡**\n\nअपना BotFather API Token चैट में पेस्ट करें (जैसे `123456:ABC-DEF...`):", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Cancel", callback_data="u_back_main")))

    # 🎧 SUPPORT
    elif data == "u_supp":
        row = fetch_query("SELECT support_tg FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
        sup_uname = row["support_tg"] if (row and row["support_tg"]) else "PranavPatel"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💬 Message Admin on Telegram", url=f"https://t.me/{sup_uname.replace('@','')}"))
        kb.add(types.InlineKeyboardButton("🌐 Visit PranavSMM.online", url="https://pranavsmm.online"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
        safe_edit(bot, f"🎧 **𝟮𝟰×𝟳 𝗖𝗨𝗦𝗧𝗢𝗠𝗘𝗥 𝗦𝗨𝗣𝗣𝗢𝗥𝗧**\n\nकिसी भी पेमेंट, Key या बॉट सहायता के लिए नीचे बटन दबाकर सीधे संपर्क करें:", cid, mid, reply_markup=kb)

def handle_owner_callbacks(bot, bot_id, call, is_master=False):
    try:
        uid, cid, mid, data = call.from_user.id, call.message.chat.id, call.message.message_id, call.data
    except:
        return

    if data == "adm_back_panel":
        user_states.pop(f"{bot_id}_{uid}", None)
        safe_edit(bot, "👑 **𝗢𝗪𝗡𝗘𝗥 𝗔𝗗𝗠𝗜𝗡 𝗣𝗔𝗡𝗘𝗟**", cid, mid, reply_markup=get_owner_panel(is_master))

    elif data == "a_payment":
        curr_upi = get_bot_upi(bot_id)
        user_states[f"{bot_id}_{uid}"] = "wait_new_upi"
        safe_edit(bot, f"💳 **𝗖𝗛𝗔𝗡𝗚𝗘 𝗨𝗣𝗜 𝗜𝗗**\n\nअभी आपकी एक्टिव UPI ID है: `{curr_upi}`\n\n👇 अपनी नई UPI ID चैट में भेजें (जैसे `yourname@ybl` या `paytm...@pty`):", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Cancel", callback_data="adm_back_panel")))

    elif data == "a_services":
        user_states[f"{bot_id}_{uid}"] = "wait_new_service"
        safe_edit(bot, "⚙️ **𝗔𝗗𝗗 𝗡𝗘𝗪 𝗦𝗠𝗠 𝗦𝗘𝗥𝗩𝗜𝗖𝗘**\n\nइस फॉर्मेट में सर्विस नाम और रेट (प्रति 1000) लिखकर चैट में भेजें:\n`Service Name | Rate`\n\nउदाहरण:\n`Instagram VIP Followers | 60`", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Cancel", callback_data="adm_back_panel")))

    elif data == "a_users":
        user_states[f"{bot_id}_{uid}"] = "wait_add_user_bal"
        safe_edit(bot, "👥 **𝗔𝗗𝗗 𝗨𝗦𝗘𝗥 𝗪𝗔𝗟𝗟𝗘𝗧 𝗕𝗔𝗟𝗔𝗡𝗖𝗘**\n\nयूजर की Telegram ID और अमाउंट इस तरह लिखकर भेजें:\n`UserID Amount`\n\nउदाहरण:\n`8585055903 1000`", cid, mid, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Cancel", callback_data="adm_back_panel")))

    elif data == "a_license_info":
        act, rsn = is_bot_active(bot_id)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🎟️ Enter License Key", callback_data="c_enter_lic_key"))
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_back_panel"))
        safe_edit(bot, f"🔑 **𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗦𝗧𝗔𝗧𝗨𝗦**\n\n• Status: {rsn}\n\nअगर आपने वेबसाइट या मास्टर बॉट से Key ले ली है, तो नीचे **Enter License Key** दबाकर उसे एक्टिवेट करें:", cid, mid, reply_markup=kb)

    elif data == "c_enter_lic_key":
        user_states[f"{bot_id}_{uid}"] = "wait_redeem_key"
        safe_send(bot, cid, "🔑 कृपया अपनी `PRANAV-...` License Key चैट में पेस्ट करें:")

    elif data == "adm_gen_menu" and is_master:
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("7 Days Key", callback_data="gkey_7"),
            types.InlineKeyboardButton("1 Month Key", callback_data="gkey_30"),
            types.InlineKeyboardButton("3 Months Key", callback_data="gkey_90"),
            types.InlineKeyboardButton("👑 Lifetime Key", callback_data="gkey_36500")
        )
        kb.add(types.InlineKeyboardButton("🔙 Back", callback_data="adm_back_panel"))
        safe_edit(bot, "🎟️ **𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘 𝗙𝗥𝗘𝗘 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗞𝗘𝗬**\n\nप्रणव जी, किस प्लान की Key जनरेट करनी है?", cid, mid, reply_markup=kb)

    elif data.startswith("gkey_") and is_master:
        pk = data.replace("gkey_", "")
        p = PLANS_CATALOG.get(pk, PLANS_CATALOG["30"])
        rand_str = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        k = f"PRANAV-{p['days']}D-{rand_str}"
        execute_query("INSERT INTO license_keys (key_code, duration_days, price, label) VALUES (?, ?, ?, ?)", (k, p["days"], p["price"], p["label"]))
        safe_edit(bot, f"✅ **{p['label']} Key Generated:**\n\n`{k}`\n\n(टैप करके कॉपी करें)", cid, mid, reply_markup=get_owner_panel(True))

    elif data == "adm_list_bots" and is_master:
        bots = fetch_query("SELECT * FROM child_bots WHERE bot_id > 0 ORDER BY bot_id DESC LIMIT 15")
        if not bots:
            txt = "🤖 अभी कोई चाइल्ड बॉट नहीं जुड़ा है।"
        else:
            txt = "🤖 **𝗖𝗢𝗡𝗡𝗘𝗖𝗧𝗘𝗗 𝗖𝗛𝗜𝗟𝗗 𝗕𝗢𝗧𝗦:**\n\n"
            for b in bots:
                st = "🟢 Licensed" if b["is_licensed"] else "🔴 Unlicensed"
                txt += f"• @{b['bot_username']} (Owner: `{b['owner_id']}`) - {st}\n"
        safe_edit(bot, txt, cid, mid, reply_markup=get_owner_panel(True))

def handle_text_inputs(bot, bot_id, msg, is_master=False):
    try:
        uid, cid, txt = msg.from_user.id, msg.chat.id, msg.text.strip().replace('`', '').replace("'", "")
    except:
        return

    key = f"{bot_id}_{uid}"
    st_data = user_states.get(key)

    # Auto-detect 12-digit UTR even if state was lost
    if len(txt) == 12 and txt.isdigit() and not st_data:
        t_row = fetch_query("SELECT tx_id FROM transactions WHERE bot_id=? AND user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1", (bot_id, uid), fetchone=True)
        if t_row:
            st_data = {"step": "wait_manual_utr", "tx_id": t_row["tx_id"]}

    if not st_data:
        return

    # 1. CHILD BOT TOKEN SUBMISSION -> STARTS THREAD IMMEDIATELY!
    if st_data == "wait_token":
        user_states.pop(key, None)
        try:
            chk = requests.get(f"https://api.telegram.org/bot{txt}/getMe", timeout=8).json()
        except:
            return safe_send(bot, cid, "❌ नेटवर्क एरर! दोबारा ट्राई करें।")
        if not chk.get("ok"):
            return safe_send(bot, cid, "❌ Invalid Bot Token! कृपया @BotFather से सही टोकन कॉपी करें।")

        b_uname = chk["result"]["username"]
        b_name = chk["result"]["first_name"]
        existing = fetch_query("SELECT bot_id FROM child_bots WHERE bot_username=?", (b_uname,), fetchone=True)
        if existing:
            execute_query("UPDATE child_bots SET bot_token=?, owner_id=? WHERE bot_id=?", (txt, uid, existing["bot_id"]))
            new_bot_id = existing["bot_id"]
        else:
            new_bot_id = execute_query("INSERT INTO child_bots (owner_id, bot_token, bot_username, bot_name, upi_id, is_licensed, status) VALUES (?, ?, ?, ?, ?, 0, 'active')",
                                       (uid, txt, b_uname, b_name, get_master_upi()))
        # Immediately start the child bot thread!
        start_child_bot_thread(new_bot_id, uid, txt, b_uname)
        return safe_send(bot, cid, f"🎉 **𝗖𝗢𝗡𝗚𝗥𝗔𝗧𝗨𝗟𝗔𝗧𝗜𝗢𝗡𝗦!**\n\nआपका चाइल्ड बॉट @{b_uname} अब 24×7 लाइव हो चुका है!\n\n👉 अपने बॉट (@{b_uname}) पर जाएं, `/start` और `/admin` दबाएं, और अपना पेमेंट गेटवे चालू करने के लिए License Key डालें!", reply_markup=get_user_main_menu())

    # 2. REDEEM LICENSE KEY
    elif st_data == "wait_redeem_key":
        user_states.pop(key, None)
        lic = fetch_query("SELECT * FROM license_keys WHERE key_code=? AND is_used=0", (txt,), fetchone=True)
        if not lic:
            return safe_send(bot, cid, "❌ Invalid or Already Used License Key!", reply_markup=get_owner_panel(is_master))
        new_exp = (datetime.datetime.now() + datetime.timedelta(days=lic["duration_days"])).strftime("%Y-%m-%d %H:%M:%S")
        execute_query("UPDATE license_keys SET is_used=1, used_by_bot_id=? WHERE key_code=?", (bot_id, txt))
        execute_query("UPDATE child_bots SET is_licensed=1, status='active', subscription_expiry=?, auto_renew=? WHERE bot_id=?", (new_exp, lic["is_sub"], bot_id))
        return safe_send(bot, cid, f"🎉 **𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗔𝗖𝗧𝗜𝗩𝗔𝗧𝗘𝗗!**\n\n📦 Plan: {lic['label']}\n⏳ Expiry: {new_exp}\n🟢 आपका बॉट और पेमेंट गेटवे अब 100% चालू है!", reply_markup=get_owner_panel(is_master))

    # 3. CHANGE UPI ID
    elif st_data == "wait_new_upi":
        user_states.pop(key, None)
        execute_query("UPDATE child_bots SET upi_id=? WHERE bot_id=?", (txt, bot_id))
        return safe_send(bot, cid, f"✅ आपकी नई UPI ID `{txt}` सेव हो गई है! अब सारे QR कोड इसी UPI पर बनेंगे।", reply_markup=get_owner_panel(is_master))

    # 4. ADD NEW SMM SERVICE
    elif st_data == "wait_new_service":
        user_states.pop(key, None)
        if "|" not in txt:
            return safe_send(bot, cid, "❌ गलत फॉर्मेट! कृपया `Service Name | Rate` के रूप में भेजें।", reply_markup=get_owner_panel(is_master))
        s_name, s_rate = txt.split("|", 1)
        try:
            r_val = float(s_rate.strip())
        except:
            r_val = 50.0
        execute_query("INSERT INTO smm_services (bot_id, service_name, rate_per_1000) VALUES (?, ?, ?)", (bot_id, s_name.strip(), r_val))
        return safe_send(bot, cid, f"✅ नई सर्विस **{s_name.strip()}** (₹{r_val}/1k) सफलतापूर्वक जोड़ दी गई है!", reply_markup=get_owner_panel(is_master))

    # 5. ADD USER BALANCE BY ADMIN
    elif st_data == "wait_add_user_bal":
        user_states.pop(key, None)
        parts = txt.split()
        if len(parts) < 2 or not parts[0].isdigit():
            return safe_send(bot, cid, "❌ गलत फॉर्मेट! `UserID Amount` भेजें।", reply_markup=get_owner_panel(is_master))
        t_uid = int(parts[0])
        t_amt = float(parts[1])
        execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, 'User')", (bot_id, t_uid))
        execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (t_amt, t_amt, bot_id, t_uid))
        return safe_send(bot, cid, f"✅ यूजर `{t_uid}` के वॉलेट में ₹{t_amt:.2f} जोड़ दिया गया!", reply_markup=get_owner_panel(is_master))

    # 6. MANUAL UTR VERIFICATION
    elif isinstance(st_data, dict) and st_data.get("step") == "wait_manual_utr":
        user_states.pop(key, None)
        tx = st_data["tx_id"]
        if len(txt) != 12 or not txt.isdigit():
            return safe_send(bot, cid, "❌ UTR नंबर 12 अंकों का होना चाहिए! दोबारा सही UTR भेजें।")
        dup = fetch_query("SELECT tx_id FROM transactions WHERE bank_utr=?", (txt,), fetchone=True)
        if dup:
            return safe_send(bot, cid, "❌ यह UTR पहले ही इस्तेमाल किया जा चुका है!")
        t_row = fetch_query("SELECT amount FROM transactions WHERE tx_id=?", (tx,), fetchone=True)
        if not t_row:
            return
        execute_query("UPDATE transactions SET bank_utr=?, status='completed' WHERE tx_id=?", (txt, tx))
        execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (t_row["amount"], t_row["amount"], bot_id, uid))
        return safe_send(bot, cid, f"🎉 **𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗!**\n\n💵 ₹{t_row['amount']:.2f} आपके वॉलेट में जोड़ दिया गया है!", reply_markup=get_user_main_menu())

    # 7. ORDER SMM FLOW (LINK -> QTY)
    elif isinstance(st_data, dict) and st_data.get("step") == "wait_ord_link":
        st_data["link"] = txt
        st_data["step"] = "wait_ord_qty"
        user_states[key] = st_data
        return safe_send(bot, cid, f"🔢 **अब क्वांटिटी (Quantity) दर्ज करें** (जैसे `100`, `500`, `1000`):")

    elif isinstance(st_data, dict) and st_data.get("step") == "wait_ord_qty":
        user_states.pop(key, None)
        if not txt.isdigit() or int(txt) < 10:
            return safe_send(bot, cid, "❌ कम से कम 10 क्वांटिटी डालें!", reply_markup=get_user_main_menu())
        qty = int(txt)
        charge = (qty / 1000.0) * st_data["rate"]
        row = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        bal = row["balance"] if row else 0.0
        if bal < charge:
            return safe_send(bot, cid, f"⚠️ बैलेंस कम है! इस ऑर्डर का चार्ज ₹{charge:.2f} है और आपके वॉलेट में ₹{bal:.2f} है। पहले Add Funds करें!", reply_markup=get_user_main_menu())
        execute_query("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ? WHERE bot_id=? AND user_id=?", (charge, charge, bot_id, uid))
        oid = execute_query("INSERT INTO bot_orders (bot_id, user_id, service_name, link, quantity, charge) VALUES (?, ?, ?, ?, ?, ?)",
                            (bot_id, uid, st_data["srv_name"], st_data["link"], qty, charge))
        return safe_send(bot, cid, f"✅ **𝗢𝗥𝗗𝗘𝗥 𝗣𝗟𝗔𝗖𝗘𝗗 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬!**\n\n🆔 Order ID: `#{oid}`\n📦 Service: {st_data['srv_name']}\n🔗 Link: {st_data['link']}\n🔢 Quantity: {qty}\n💵 Charge: ₹{charge:.2f}", reply_markup=get_user_main_menu())

# ==========================================
# 🚀 24x7 THREAD RUNNERS (MASTER + CHILD BOTS + KEEP-ALIVE)
# ==========================================
def register_bot_handlers(bot_obj, bot_id, owner_id, is_master=False):
    @bot_obj.message_handler(commands=['start'])
    def on_start(msg):
        execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)", (bot_id, msg.from_user.id, msg.from_user.username or "User"))
        title = "✨ 𝗣𝗥𝗔𝗡𝗔𝗩 𝗠𝗔𝗦𝗧𝗘𝗥 𝟯𝗗 𝗕𝗢𝗧 ✨" if is_master else "💎 𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗦𝗠𝗠 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗕𝗢𝗧 💎"
        safe_send(bot_obj, msg.chat.id, f"{title}\n\n🚀 24×7 Automated SMM, Child Bot Maker & Instant UPI Gateway!\n👇 नीचे दिए गए बटन्स से इस्तेमाल करें (एडमिन पैनल के लिए `/admin` भेजें):", reply_markup=get_user_main_menu())

    @bot_obj.message_handler(commands=['admin'])
    def on_admin(msg):
        if msg.from_user.id != owner_id and msg.from_user.id != SUPER_ADMIN_ID:
            return safe_send(bot_obj, msg.chat.id, "⛔ केवल बॉट के मालिक (Owner) ही `/admin` खोल सकते हैं!")
        safe_send(bot_obj, msg.chat.id, "👑 **𝗢𝗪𝗡𝗘𝗥 𝗔𝗗𝗠𝗜𝗡 𝗖𝗢𝗡𝗧𝗥𝗢𝗟 𝗣𝗔𝗡𝗘𝗟**", reply_markup=get_owner_panel(is_master))

    @bot_obj.callback_query_handler(func=lambda c: True)
    def on_cb(call):
        if call.data.startswith("a_") or call.data.startswith("adm_") or call.data.startswith("c_enter_") or call.data.startswith("gkey_"):
            if call.from_user.id != owner_id and call.from_user.id != SUPER_ADMIN_ID:
                return bot_obj.answer_callback_query(call.id, "⛔ Owner Access Only!", show_alert=True)
            handle_owner_callbacks(bot_obj, bot_id, call, is_master)
        else:
            handle_user_callbacks(bot_obj, bot_id, call)

    @bot_obj.message_handler(func=lambda m: True and m.text and not m.text.startswith('/'))
    def on_txt(msg):
        handle_text_inputs(bot_obj, bot_id, msg, is_master)

def child_bot_worker(bot_id, owner_id, token, uname):
    while True:
        try:
            cbot = telebot.TeleBot(token, threaded=True)
            register_bot_handlers(cbot, bot_id, owner_id, is_master=False)
            cbot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except Exception as e:
            time.sleep(5)

def start_child_bot_thread(bot_id, owner_id, token, uname):
    if bot_id in running_child_bots:
        return
    t = threading.Thread(target=child_bot_worker, args=(bot_id, owner_id, token, uname), daemon=True)
    running_child_bots[bot_id] = t
    t.start()

def boot_all_existing_child_bots():
    rows = fetch_query("SELECT * FROM child_bots WHERE bot_id > 0 AND status='active'")
    if not rows:
        return
    for r in rows:
        if r["bot_token"] and r["bot_token"] != "MASTER":
            start_child_bot_thread(r["bot_id"], r["owner_id"], r["bot_token"], r["bot_username"])

def master_bot_worker():
    while True:
        try:
            if not MASTER_BOT_TOKEN:
                time.sleep(5)
                continue
            mbot = telebot.TeleBot(MASTER_BOT_TOKEN, threaded=True)
            try:
                me = mbot.get_me()
                execute_query("UPDATE child_bots SET bot_username=? WHERE bot_id=0", (me.username,))
            except:
                pass
            register_bot_handlers(mbot, 0, SUPER_ADMIN_ID, is_master=True)
            mbot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except Exception as e:
            time.sleep(4)

def keep_alive_and_auto_sub_daemon():
    """Pings pranavsmm.online every 3 minutes for 24x7 uptime & processes Auto-Subscriptions"""
    while True:
        time.sleep(180)
        try:
            requests.get("https://pranavsmm.online/ping", timeout=10)
        except:
            pass
        try:
            if SITE_URL:
                requests.get(f"{SITE_URL}/ping", timeout=10)
        except:
            pass
        # Check & Auto-Renew Expired Web Subscriptions if balance >= plan_price
        try:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            expired_users = fetch_query("SELECT * FROM web_users WHERE auto_sub=1 AND sub_expiry IS NOT NULL AND sub_expiry < ?", (now_str,))
            if expired_users:
                for u in expired_users:
                    if u["balance"] >= u["plan_price"] and u["plan_price"] > 0:
                        new_exp = (datetime.datetime.now() + datetime.timedelta(days=u["plan_days"])).strftime("%Y-%m-%d %H:%M:%S")
                        execute_query("UPDATE web_users SET balance = balance - ?, sub_expiry=? WHERE id=?", (u["plan_price"], new_exp, u["id"]))
                    else:
                        execute_query("UPDATE web_users SET auto_sub=0, active_plan='Expired (Low Wallet)' WHERE id=?", (u["id"],))
        except Exception as e:
            print(f"[AUTO-SUB CHECK ERR] {e}")

# Start All Background Threads
threading.Thread(target=master_bot_worker, daemon=True).start()
threading.Thread(target=boot_all_existing_child_bots, daemon=True).start()
threading.Thread(target=keep_alive_and_auto_sub_daemon, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
