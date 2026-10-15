import os
import sys
import time
import datetime
import random
import string
import secrets
import re
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
MASTER_BOT_TOKEN = os.environ.get("MASTER_BOT_TOKEN", "").strip()
SUPER_ADMIN_ID = 8585055903 # Pranav Patel (प्रणव जी)

WEB_ADMIN_USER = "pranav"
WEB_ADMIN_PASS = "pranav7@admin"

SECRET_KEY = os.environ.get("SECRET_KEY", Fernet.generate_key().decode())
if isinstance(SECRET_KEY, str): SECRET_KEY = SECRET_KEY.encode()
cipher_suite = Fernet(SECRET_KEY)

DB_PATH = "pranav_master_engine_pro.db"
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

user_states = {}
keypad_amounts = {}

# ==========================================
# 🗄️ ADVANCED BULLETPROOF DATABASE
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
        """CREATE TABLE IF NOT EXISTS child_bots (bot_id INTEGER PRIMARY KEY, owner_id INTEGER, bot_token_enc TEXT UNIQUE, bot_username TEXT, bot_name TEXT, pro_mode INTEGER DEFAULT 1, active_gateway TEXT DEFAULT 'paytm', paytm_mid TEXT DEFAULT 'WWRYwl67445982860121', paytm_upi TEXT DEFAULT 'paytm.s2xzkgu@pty', subscription_expiry TIMESTAMP, is_licensed INTEGER DEFAULT 0, status TEXT DEFAULT 'active', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS license_keys (key_code TEXT PRIMARY KEY, duration_days INTEGER DEFAULT 30, price REAL DEFAULT 0.0, label TEXT DEFAULT '30 Days', used_by_bot_id INTEGER DEFAULT NULL, used_by_user_id INTEGER DEFAULT NULL, is_used INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS bot_clients (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id INTEGER, user_id INTEGER, username TEXT, balance REAL DEFAULT 0.0, total_deposit REAL DEFAULT 0.0, total_spent REAL DEFAULT 0.0, banned INTEGER DEFAULT 0, UNIQUE(bot_id, user_id))""",
        """CREATE TABLE IF NOT EXISTS web_users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, password TEXT, balance REAL DEFAULT 0.0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS transactions (tx_id TEXT PRIMARY KEY, bot_id INTEGER, user_id INTEGER, amount REAL, tx_type TEXT DEFAULT 'deposit', status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""
    ]
    for q in queries: execute_query(q)

    # Default pricing keys if empty
    if fetch_query("SELECT COUNT(*) as cnt FROM license_keys", fetchone=True)["cnt"] == 0:
        default_keys = [
            ("PRANAV-7DAYS-PRO99", 7, 49.0, "7 Days Trial"),
            ("PRANAV-1MONTH-PRO149", 30, 149.0, "1 Month Pro"),
            ("PRANAV-3MONTH-PRO399", 90, 399.0, "3 Months Elite"),
            ("PRANAV-LIFETIME-GOD999", 36500, 999.0, "👑 Lifetime God Access")
        ]
        for k, days, pr, lbl in default_keys:
            execute_query("INSERT OR IGNORE INTO license_keys (key_code, duration_days, price, label) VALUES (?, ?, ?, ?)", (k, days, pr, lbl))

    exp_date = (datetime.datetime.now() + datetime.timedelta(days=36500)).strftime("%Y-%m-%d %H:%M:%S")
    master_uname = "PranavFatherDevBot"
    if MASTER_BOT_TOKEN:
        try:
            r = requests.get(f"https://api.telegram.org/bot{MASTER_BOT_TOKEN}/getMe", timeout=5).json()
            if r.get("ok"): master_uname = r["result"]["username"]
        except: pass
    
    execute_query("""
    INSERT INTO child_bots (bot_id, owner_id, bot_username, is_licensed, subscription_expiry)
    VALUES (0, ?, ?, 1, ?)
    ON CONFLICT(bot_id) DO UPDATE SET owner_id=excluded.owner_id, bot_username=excluded.bot_username, is_licensed=1, subscription_expiry=?
    """, (SUPER_ADMIN_ID, master_uname, exp_date, exp_date))

init_db()

# ==========================================
# 🌟 3D FUTURISTIC GLASSMORPHISM FRONTEND & UI
# ==========================================
HOME_HTML = """
<!DOCTYPE html>
<html lang="hi" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PranavSMM.online - Next-Gen Gateway & Engine</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800;900&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: #030712; color: #f9fafb; overflow-x: hidden; }
        .glass-card { background: rgba(17, 24, 39, 0.7); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.08); box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7); }
        .glow-effect { text-shadow: 0 0 40px rgba(168, 85, 247, 0.5); }
        .btn-3d { transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 10px 25px -5px rgba(147, 51, 234, 0.5); }
        .btn-3d:hover { transform: translateY(-3px); box-shadow: 0 20px 35px -5px rgba(147, 51, 234, 0.7); }
    </style>
</head>
<body class="min-h-screen flex flex-col justify-between selection:bg-purple-500 selection:text-white">
    <!-- Navbar -->
    <header class="sticky top-0 z-50 glass-card border-b border-white/10 px-6 py-4 flex justify-between items-center">
        <div class="flex items-center gap-3">
            <span class="text-2xl font-black bg-gradient-to-r from-purple-400 via-pink-500 to-indigo-400 bg-clip-text text-transparent glow-effect">⚡ PranavSMM</span>
            <span class="bg-purple-900/60 text-purple-300 text-xs px-3 py-1 rounded-full border border-purple-500/30 font-bold hidden sm:inline-block">2050 ENGINE v3.0</span>
        </div>
        <div class="flex items-center gap-3">
            <a href="/login" class="text-sm font-semibold px-4 py-2 rounded-xl hover:bg-white/5 transition">Login</a>
            <a href="/register" class="bg-gradient-to-r from-purple-600 to-indigo-600 text-sm font-bold px-5 py-2.5 rounded-xl btn-3D">Get Started</a>
        </div>
    </header>

    <!-- Hero Section -->
    <main class="flex-1 max-w-6xl mx-auto px-6 py-16 text-center flex flex-col justify-center">
        <div class="inline-flex items-center gap-2 bg-gradient-to-r from-purple-500/10 to-pink-500/10 border border-purple-500/20 px-4 py-2 rounded-full text-xs font-bold text-purple-300 mx-auto mb-6">
            ✨ AUTOMATED P2P UPI & RESELLER BOT ECOSYSTEM
        </div>
        <h1 class="text-4xl md:text-7xl font-black tracking-tight leading-tight">
            Autonomous Next-Gen <br>
            <span class="bg-gradient-to-r from-purple-400 via-pink-400 to-indigo-400 bg-clip-text text-transparent glow-effect">Digital SMM & Gateway</span>
        </h1>
        <p class="text-slate-400 mt-6 max-w-2xl mx-auto text-base md:text-lg">
            प्रणव जी का पावरफुल इंजन। सुरक्षित ऑटो-पेमेंट्स, चाइल्ड बॉट्स क्रिएशन, और इंस्टेंट लाइसेंस की जनरेशन सीधे आपके कंट्रोल में।
        </p>

        <!-- Pricing Cards Showcase -->
        <div class="mt-16 grid grid-cols-1 md:grid-cols-3 gap-6 text-left">
            <div class="glass-card p-6 rounded-3xl relative overflow-hidden group hover:border-purple-500/50 transition">
                <div class="absolute top-0 right-0 bg-purple-500/20 text-purple-300 text-xs font-bold px-3 py-1 rounded-bl-2xl">7 DAYS</div>
                <h3 class="text-xl font-black text-white">Trial Pro</h3>
                <div class="text-3xl font-black text-purple-400 mt-4">₹49 <span class="text-xs text-slate-500 font-normal">/7 days</span></div>
                <p class="text-xs text-slate-400 mt-2">Perfect for trying out the master engine features.</p>
                <a href="/register" class="mt-6 block text-center bg-white/10 hover:bg-white/20 py-3 rounded-xl font-bold text-sm transition">Activate Now →</a>
            </div>
            <div class="glass-card p-6 rounded-3xl relative overflow-hidden border-purple-500/40 group shadow-2xl shadow-purple-500/10">
                <div class="absolute top-0 right-0 bg-gradient-to-r from-purple-600 to-indigo-600 text-white text-xs font-bold px-3 py-1 rounded-bl-2xl">POPULAR</div>
                <h3 class="text-xl font-black text-white">1 Month Elite</h3>
                <div class="text-3xl font-black text-purple-400 mt-4">₹149 <span class="text-xs text-slate-500 font-normal">/month</span></div>
                <p class="text-xs text-slate-400 mt-2">Full reseller child bot automation & live gateway access.</p>
                <a href="/register" class="mt-6 block text-center bg-gradient-to-r from-purple-600 to-indigo-600 py-3 rounded-xl font-bold text-sm btn-3D">Activate Now →</a>
            </div>
            <div class="glass-card p-6 rounded-3xl relative overflow-hidden group hover:border-purple-500/50 transition">
                <div class="absolute top-0 right-0 bg-pink-500/20 text-pink-300 text-xs font-bold px-3 py-1 rounded-bl-2xl">LIFETIME</div>
                <h3 class="text-xl font-black text-white">👑 God Master</h3>
                <div class="text-3xl font-black text-purple-400 mt-4">₹999 <span class="text-xs text-slate-500 font-normal">/lifetime</span></div>
                <p class="text-xs text-slate-400 mt-2">Unlimited power, zero limits, absolute master control.</p>
                <a href="/register" class="mt-6 block text-center bg-white/10 hover:bg-white/20 py-3 rounded-xl font-bold text-sm transition">Activate Now →</a>
            </div>
        </div>
    </main>

    <!-- Footer -->
    <footer class="glass-card border-t border-white/10 text-center text-slate-500 text-xs py-6">
        © 2026 pranavsmm.online • Built with Pranav Master Engine
    </footer>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="hi" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - PranavSMM</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;850&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: #030712; color: #f9fafb; }
        .glass-card { background: rgba(17, 24, 39, 0.8); backdrop-filter: blur(25px); border: 1px solid rgba(255, 255, 255, 0.08); }
    </style>
</head>
<body class="min-h-screen flex items-center justify-center p-6">
    <div class="glass-card p-8 rounded-3xl w-full max-w-md shadow-2xl">
        <h2 class="text-3xl font-black text-center mb-2 bg-gradient-to-r from-purple-400 to-indigo-500 bg-clip-text text-transparent">Welcome Back</h2>
        <p class="text-center text-slate-400 text-xs mb-6">Sign in to your PranavSMM account</p>
        {% if error %}
        <div class="bg-red-500/20 border border-red-500/50 text-red-300 p-3 rounded-xl text-xs mb-4 text-center font-bold">{{ error }}</div>
        {% endif %}
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">EMAIL ADDRESS</label>
                <input type="email5" name="email" required class="w-full bg-slate-950/80 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-purple-500 text-sm">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">PASSWORD</label>
                <input type="password" name="password" required class="w-full bg-slate-950/80 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-purple-500 text-sm">
            </div>
            <button type="submit" class="w-full bg-gradient-to-r from-purple-600 to-indigo-600 py-3.5 rounded-xl font-bold text-sm hover:opacity-90 transition shadow-lg shadow-purple-600/30">Secure Login →</button>
        </form>
        <div class="text-center mt-6 text-xs text-slate-400">
            Don't have an account? <a href="/register" class="text-purple-400 font-bold hover:underline">Register</a> | <a href="/" class="text-slate-500 hover:text-white">Home</a>
        </div>
    </div>
</body>
</html>
"""

REGISTER_HTML = """
<!DOCTYPE html>
<html lang="hi" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Register - PranavSMM</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;850&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: #030712; color: #f9fafb; }
        .glass-card { background: rgba(17, 24, 39, 0.8); backdrop-filter: blur(25px); border: 1px solid rgba(255, 255, 255, 0.08); }
    </style>
</head>
<body class="min-h-screen flex items-center justify-center p-6">
    <div class="glass-card p-8 rounded-3xl w-full max-w-md shadow-2xl">
        <h2 class="text-3xl font-black text-center mb-2 bg-gradient-to-r from-purple-400 to-indigo-500 bg-clip-text text-transparent">Create Account</h2>
        <p class="text-center text-slate-400 text-xs mb-6">Join PranavSMM Gateway & SMM Platform</p>
        {% if error %}
        <div class="bg-red-500/20 border border-red-500/50 text-red-300 p-3 rounded-xl text-xs mb-4 text-center font-bold">{{ error }}</div>
        {% endif %}
        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">YOUR NAME</label>
                <input type="text" name="name" required class="w-full bg-slate-950/80 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-purple-500 text-sm">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">EMAIL ADDRESS</label>
                <input type="email" name="email" required class="w-full bg-slate-950/80 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-purple-500 text-sm">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 mb-1">PASSWORD</label>
                <input type="password" name="password" required class="w-full bg-slate-950/80 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-purple-500 text-sm">
            </div>
            <button type="submit" class="w-full bg-gradient-to-r from-purple-600 to-indigo-600 py-3.5 rounded-xl font-bold text-sm hover:opacity-90 transition shadow-lg shadow-purple-600/30">Register Free →</button>
        </form>
        <div class="text-center mt-6 text-xs text-slate-400">
            Already have an account? <a href="/login" class="text-purple-400 font-bold hover:underline">Login</a> | <a href="/" class="text-slate-500 hover:text-white">Home</a>
        </div>
    </div>
</body>
</html>
"""

USER_DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="hi" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>User Dashboard - PranavSMM</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;850&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: #030712; color: #f9fafb; }
        .glass-card { background: rgba(17, 24, 39, 0.8); backdrop-filter: blur(25px); border: 1px solid rgba(255, 255, 255, 0.08); }
    </style>
</head>
<body class="min-h-screen flex flex-col">
    <header class="glass-card border-b border-white/10 px-6 py-4 flex justify-between items-center">
        <div class="flex items-center gap-3">
            <span class="text-xl font-black bg-gradient-to-r from-purple-400 to-indigo-400 bg-clip-text text-transparent">⚡ PranavSMM</span>
            <span class="bg-purple-900/50 text-purple-300 text-xs px-3 py-1 rounded-full border border-purple-500/30 font-bold">User Hub</span>
        </div>
        <div class="flex items-center gap-4 text-sm">
            <span class="text-slate-400">Hello, <b class="text-white">{{ user.name }}</b></span>
            <a href="/logout" class="bg-red-500/20 text-red-300 px-3 py-1.5 rounded-xl font-bold border border-red-500/30 hover:bg-red-500/30 transition text-xs">Logout</a>
        </div>
    </header>
    <main class="flex-1 max-w-5xl mx-auto p-6 w-full">
        <h1 class="text-3xl font-black mb-6">Your Dashboard</h1>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div class="glass-card p-6 rounded-3xl">
                <div class="text-xs font-bold text-slate-400 uppercase">Account Balance</div>
                <div class="text-3xl font-black text-purple-400 mt-2">₹{{ "%.2f"|format(user.balance) }}</div>
            </div>
            <div class="glass-card p-6 rounded-3xl">
                <div class="text-xs font-bold text-slate-400 uppercase">Account Email</div>
                <div class="text-sm font-bold text-white mt-3 truncate">{{ user.email }}</div>
            </div>
            <div class="glass-card p-6 rounded-3xl">
                <div class="text-xs font-bold text-slate-400 uppercase">Gateway Status</div>
                <div class="text-lg font-black text-green-400 mt-2">🟢 Active & Connected</div>
            </div>
        </div>
    </main>
</body>
</html>
"""

ADMIN_DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="hi" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>👑 Pranav Ji Master Admin Panel</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;850&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; background: #030712; color: #f9fafb; }
        .glass-card { background: rgba(17, 24, 39, 0.85); backdrop-filter: blur(25px); border: 1px solid rgba(255, 255, 255, 0.08); }
    </style>
</head>
<body class="min-h-screen flex flex-col">
    <!-- Top Admin Header -->
    <header class="glass-card border-b border-white/10 px-8 py-4 flex justify-between items-center sticky top-0 z-50">
        <div class="flex items-center gap-3">
            <span class="text-2xl font-black bg-gradient-to-r from-amber-400 to-purple-500 bg-clip-text text-transparent">👑 Pranav Ji Admin Panel</span>
            <span class="bg-amber-500/20 text-amber-300 text-xs px-3 py-1 rounded-full border border-amber-500/30 font-bold">God Master Access</span>
        </div>
        <div class="flex items-center gap-4">
            <a href="/" target="_blank" class="text-sm text-slate-400 hover:text-white">View Site ↗</a>
            <a href="/admin/logout" class="bg-red-500/20 text-red-300 px-4 py-2 rounded-xl text-xs font-bold border border-red-500/30 hover:bg-red-500/30 transition">Logout</a>
        </div>
    </header>

    <main class="flex-1 max-w-6xl mx-auto p-6 md:p-8 w-full space-y-8">
        <!-- Stats Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <div class="glass-card p-6 rounded-3xl border-l-4 border-l-purple-500">
                <div class="text-slate-400 text-xs font-bold uppercase">Active Child Bots</div>
                <div class="text-4xl font-black mt-2 text-white">{{ total_bots }}</div>
            </div>
            <div class="glass-card p-6 rounded-3xl border-l-4 border-l-green-500">
                <div class="text-slate-400 text-xs font-bold uppercase">Total Web Users</div>
                <div class="text-4xl font-black mt-2 text-white">{{ total_web_users }}</div>
            </div>
            <div class="glass-card p-6 rounded-3xl border-l-4 border-l-amber-500">
                <div class="text-slate-400 text-xs font-bold uppercase">Engine Status</div>
                <div class="text-3xl font-black mt-2 text-green-400">ONLINE ⚡</div>
            </div>
        </div>

        <!-- License Key Generator Box -->
        <div class="glass-card p-8 rounded-3xl shadow-2xl">
            <h3 class="text-xl font-black mb-4 flex items-center gap-2">🎟️ License Key Generator (1 Month / 3 Months / Lifetime)</h3>
            <p class="text-xs text-slate-400 mb-6">चाइल्ड बॉट्स और प्रीमियम मर्चेंट्स के लिए सिक्योर लाइसेंस की यहाँ से जनरेट करें।</p>
            
            <form method="POST" action="/admin/generate-key" class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                    <label class="block text-xs font-bold text-slate-400 mb-1">SELECT PLAN / DURATION</label>
                    <select name="duration" class="w-full bg-slate-950 border border-white/10 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-purple-500">
                        <option value="7">7 Days Trial (₹49)</option>
                        <option value="30" selected>1 Month Pro (₹149)</option>
                        <option value="90">3 Months Elite (₹399)</option>
                        <option value="36500">👑 Lifetime God (₹999)</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-400 mb-1">PRICE (INR)</label>
                    <input type="number" name="price" value="149" class="w-full bg-slate-950 border border-white/10 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-purple-500">
                </div>
                <div class="flex items-end">
                    <button type="submit" class="w-full bg-gradient-to-r from-purple-600 to-indigo-600 py-3 rounded-xl font-bold text-sm hover:opacity-90 transition shadow-lg shadow-purple-600/30">Generate Key ⚡</button>
                </div>
            </form>

            {% if generated_key %}
            <div class="mt-6 bg-slate-950 p-4 rounded-2xl border border-purple-500/40 flex justify-between items-center">
                <div>
                    <div class="text-xs text-purple-400 font-bold">SUCCESSFULLY GENERATED KEY:</div>
                    <div class="text-sm font-mono text-white mt-1 select-all font-black">{{ generated_key }}</div>
                </div>
            </div>
            {% endif %}
        </div>

        <!-- Master API Credentials -->
        <div class="glass-card p-8 rounded-3xl">
            <h3 class="text-xl font-black mb-4">🔑 Master Gateway API Endpoints</h3>
            <div class="bg-slate-950 p-4 rounded-2xl border border-white/10 font-mono text-xs text-purple-300 break-all mb-4">
                MASTER API KEY: <b>fam_live_ecaccced0de14140a457f95aac05b687</b>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
                <div class="bg-slate-950 p-3 rounded-xl border border-white/10 text-indigo-300">POST /api/v1/fampay/create</div>
                <div class="bg-slate-950 p-3 rounded-xl border border-white/10 text-indigo-300">POST /api/v1/paytm/create</div>
                <div class="bg-slate-950 p-3 rounded-xl border border-white/10 text-indigo-300">POST /api/v1/bharatpe/create</div>
            </div>
        </div>
    </main>
</body>
</html>
"""

# ==========================================
# 🌐 WEB ROUTES (FRONTEND & ADMIN SEPARATION)
# ==========================================
@app.route('/')
def home():
    return render_template_string(HOME_HTML)

@app.route('/login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        email = request.form.get("email")
        pwd = request.form.get("password")
        user = fetch_query("SELECT * FROM web_users WHERE email=? AND password=?", (email, pwd), fetchone=True)
        if user:
            session['user_id'] = user["id"]
            return redirect(url_for('user_dashboard'))
        return render_template_string(LOGIN_HTML, error="❌ Invalid Email or Password!")
    return render_template_string(LOGIN_HTML)

@app.route('/register', methods=['GET', 'POST'])
def user_register():
    if request.method == 'POST':
        name = request.form.get("name")
        email = request.form.get("email")
        pwd = request.form.get("password")
        try:
            execute_query("INSERT INTO web_users (name, email, password, balance) VALUES (?, ?, ?, 0.0)", (name, email, pwd))
            user = fetch_query("SELECT * FROM web_users WHERE email=?", (email,), fetchone=True)
            session['user_id'] = user["id"]
            return redirect(url_for('user_dashboard'))
        except:
            return render_template_string(REGISTER_HTML, error="❌ Email already registered!")
    return render_template_string(REGISTER_HTML)

@app.route('/dashboard')
def user_dashboard():
    if not session.get('user_id'): return redirect(url_for('user_login'))
    user = fetch_query("SELECT * FROM web_users WHERE id=?", (session['user_id'],), fetchone=True)
    return render_template_string(USER_DASHBOARD_HTML, user=user)

@app.route('/logout')
def user_logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

# --- SEPARATE SECURE ADMIN PANEL (PRANAV JI ONLY) ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        user = request.form.get("username")
        pwd = request.form.get("password")
        if user == WEB_ADMIN_USER and pwd == WEB_ADMIN_PASS:
            session['admin_logged'] = True
            return redirect(url_for('admin_panel'))
        return render_template_string(LOGIN_HTML, error="❌ Invalid Admin Credentials!")
    
    if not session.get('admin_logged'):
        return render_template_string(LOGIN_HTML)

    b_cnt = fetch_query("SELECT COUNT(*) as c FROM child_bots", fetchone=True)["c"]
    u_cnt = fetch_query("SELECT COUNT(*) as c FROM web_users", fetchone=True)["c"]
    gen_key = session.pop('last_gen_key', None)
    return render_template_string(ADMIN_DASHBOARD_HTML, total_bots=b_cnt, total_web_users=u_cnt, generated_key=gen_key)

@app.route('/admin/generate-key', methods=['POST'])
def admin_gen_key():
    if not session.get('admin_logged'): return redirect(url_for('admin_panel'))
    days = int(request.form.get("duration", 30))
    price = float(request.form.get("price", 149.0))
    
    lbl = f"{days} Days Pro"
    if days == 7: lbl = "7 Days Trial"
    elif days == 90: lbl = "3 Months Elite"
    elif days >= 36500: lbl = "👑 Lifetime God"

    rand_str = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    key_code = f"PRANAV-PRO-{days}D-{rand_str}"
    
    execute_query("INSERT INTO license_keys (key_code, duration_days, price, label) VALUES (?, ?, ?, ?)", (key_code, days, price, lbl))
    session['last_gen_key'] = key_code
    return redirect(url_for('admin_panel'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged', None)
    return redirect(url_for('admin_panel'))

# ==========================================
# 🤖 TELEGRAM BOT UTILITIES & ENGINE
# ==========================================
def get_bot_instance(bot_id):
    if bot_id == 0: return telebot.TeleBot(MASTER_BOT_TOKEN)
    c_row = fetch_query("SELECT bot_token_enc FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
    if c_row:
        token = cipher_suite.decrypt(c_row["bot_token_enc"].encode()).decode()
        return telebot.TeleBot(token)
    return None

def safe_send(bot, chat_id, text, reply_markup=None):
    try: return bot.send_message(chat_id, text, reply_markup=reply_markup)
    except: pass

def safe_edit(bot, text, chat_id, message_id, reply_markup=None):
    try: return bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except: return safe_send(bot, chat_id, text, reply_markup=reply_markup)

def is_bot_active(bot_id):
    if bot_id == 0: return True, "👑 Lifetime God Master"
    row = fetch_query("SELECT is_licensed, subscription_expiry, status FROM child_bots WHERE bot_id=?", (bot_id,), fetchone=True)
    if not row or row["is_licensed"] == 0: return False, "❌ License Not Activated. Enter valid key."
    if row["status"] == "suspended": return False, "🚫 Bot Suspended"
    return True, "Active"

# Bot Keypads & Handlers
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
    m.add(types.InlineKeyboardButton("👥 Users", callback_data="a_users"), types.InlineKeyboardButton("🔑 License Info", callback_data="a_license_info"), types.InlineKeyboardButton("🔙 Main Menu", callback_data="a_back_main"))
    if is_master: m.add(types.InlineKeyboardButton("🎟️ Generate Keys", callback_data="adm_gen_key"))
    return m

def get_user_main_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("💳 Balance", callback_data="u_bal"), types.InlineKeyboardButton("➕ Add Funds", callback_data="u_dep"))
    m.add(types.InlineKeyboardButton("🛒 Order Now", callback_data="u_ord"), types.InlineKeyboardButton("🗓️ History", callback_data="u_hist"))
    m.add(types.InlineKeyboardButton("🤖 Create Bot", callback_data="u_cyob"), types.InlineKeyboardButton("🎧 Support", callback_data="u_supp"))
    return m

def handle_user_callbacks(bot, bot_id, call):
    try: uid, cid, mid, data = call.from_user.id, call.message.chat.id, call.message.message_id, call.data
    except: return
    if data in ["u_continue_main", "u_back_main", "a_back_main"]:
        safe_edit(bot, "✨ 𝓦𝓔𝗟𝓒𝓞𝓜𝓔 𝗧𝗢 𝗣𝗔𝗡𝗘𝗟 ✨\n\n👑 Premium Reseller Dashboard", cid, mid, reply_markup=get_user_main_menu())
    elif data == "u_bal":
        row = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid), fetchone=True)
        bal = row["balance"] if row else 0.0
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
    elif data == "adm_gen_key" and is_master:
        rand_str = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        k = f"PRANAV-PRO-30D-{rand_str}"
        execute_query("INSERT INTO license_keys (key_code, duration_days, price, label) VALUES (?, 30, 149.0, '1 Month Pro')", (k,))
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
        return safe_send(bot, cid, f"🚀 @{chk['result']['username']} is Live! Go to website admin or /admin to activate.")

    if st_data == "wait_redeem_key":
        user_states.pop(key, None)
        lic = fetch_query("SELECT * FROM license_keys WHERE key_code=? AND is_used=0", (txt,), fetchone=True)
        if not lic: return safe_send(bot, cid, "❌ Invalid or Already Used Key!")
        new_exp = (datetime.datetime.now() + datetime.timedelta(days=lic["duration_days"])).strftime("%Y-%m-%d %H:%M:%S")
        execute_query("UPDATE license_keys SET is_used=1, used_by_bot_id=? WHERE key_code=?", (bot_id, txt))
        execute_query("UPDATE child_bots SET is_licensed=1, status='active', subscription_expiry=? WHERE bot_id=?", (new_exp, bot_id))
        return safe_send(bot, cid, f"🎉 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗔𝗖𝗧𝗜𝗩𝗔𝗧𝗘𝗗!\nExpiry: {new_exp}", reply_markup=get_owner_panel(is_master))

    if isinstance(st_data, dict) and st_data.get("step") == "wait_manual_utr":
        user_states.pop(key, None)
        tx = st_data["tx_id"]
        if len(txt) != 12 or not txt.isdigit(): return safe_send(bot, cid, "❌ UTR must be 12 digits.")
        execute_query("UPDATE transactions SET status='completed' WHERE tx_id=?", (tx,))
        t_row = fetch_query("SELECT amount FROM transactions WHERE tx_id=?", (tx,), fetchone=True)
        execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (t_row["amount"], t_row["amount"], bot_id, uid))
        return safe_send(bot, cid, f"🎉 Payment Verified!\n₹{t_row['amount']} credited.", reply_markup=get_user_main_menu())

# ==========================================
# 🤖 THREAD RUNNERS
# ==========================================
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
                if c.data.startswith("a_") or c.data.startswith("adm_"):
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
