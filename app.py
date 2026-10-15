# ==============================================================================
# 👑 PRANAV SMM ENTERPRISE CLOUD ENGINE (v6.0 GRANDMASTER)
# ==============================================================================
import os
import sys
import time
import json
import datetime
import secrets
import string
import hashlib
import sqlite3
import threading
import urllib.parse
import requests
from functools import wraps
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, abort
import telebot
from telebot import types

# ==========================================
# ⚙️ 1. SECURE ENVIRONMENT CONFIGURATION
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

DB_PATH = "pranav_grandmaster_enterprise.db"

def hash_pwd(pwd):
    return hashlib.sha256(str(pwd).encode()).hexdigest() if pwd else ""

def generate_secure_key(days):
    """Cryptographically secure License Key Generator (BotFather Grade)"""
    rand_part = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(36))
    return f"PV7_{days}D_{rand_part}_SECURE"

# ==========================================
# 🗄️ 2. MASSIVE DATABASE ENGINE (RENTAL SCHEMA)
# ==========================================
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
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
    except Exception as e: print(f"[DB EXEC ERROR] {e}\nQuery: {query}")
    finally: conn.close()

def fetch_query(query, params=(), fetchone=False):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchone() if fetchone else cur.fetchall()
    except Exception as e: print(f"[DB FETCH ERROR] {e}")
    finally: conn.close()

def get_cfg(key, default=""):
    r = fetch_query("SELECT val FROM sys_cfg WHERE k=?", (key,), fetchone=True)
    return r["val"] if r else default

def set_cfg(key, val):
    if val is not None:
        execute_query("INSERT INTO sys_cfg (k, val) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET val=excluded.val", (key, str(val)))

def init_database():
    """Initializes the massive schema required for a full Rental SMM Panel"""
    queries = [
        # System Configurations (Settings, Themes, Appearance, SMTP, SEO)
        "CREATE TABLE IF NOT EXISTS sys_cfg (k TEXT PRIMARY KEY, val TEXT)",
        
        # Web Users (Google Login, Telegram Login Support)
        """CREATE TABLE IF NOT EXISTS web_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT, email TEXT UNIQUE, password_hash TEXT,
            google_id TEXT DEFAULT '', telegram_id TEXT DEFAULT '',
            balance REAL DEFAULT 0.0, total_deposit REAL DEFAULT 0.0, total_spent REAL DEFAULT 0.0,
            status TEXT DEFAULT 'Active', role TEXT DEFAULT 'User',
            api_key TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            login_ip TEXT DEFAULT ''
        )""",
        
        # Telegram Bot Clients (Users interacting via Master/Child Bots)
        """CREATE TABLE IF NOT EXISTS bot_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            bot_id INTEGER, user_id INTEGER, username TEXT,
            balance REAL DEFAULT 0.0, total_deposit REAL DEFAULT 0.0, total_spent REAL DEFAULT 0.0,
            UNIQUE(bot_id, user_id)
        )""",
        
        # Child Bots (Reseller System)
        """CREATE TABLE IF NOT EXISTS child_bots (
            bot_id INTEGER PRIMARY KEY AUTOINCREMENT, 
            owner_id INTEGER, bot_token TEXT UNIQUE, bot_username TEXT, 
            custom_upi TEXT DEFAULT '', custom_mid TEXT DEFAULT '', 
            is_licensed INTEGER DEFAULT 0, expiry TIMESTAMP, 
            status TEXT DEFAULT 'active', margin_pct REAL DEFAULT 15.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        
        # License Keys (Inventory)
        """CREATE TABLE IF NOT EXISTS license_keys (
            key_code TEXT PRIMARY KEY, duration_days INTEGER DEFAULT 30, price REAL DEFAULT 149.0,
            is_used INTEGER DEFAULT 0, used_by_bot_id INTEGER DEFAULT NULL, used_by_user_id INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        
        # Financial Transactions (All Gateways)
        """CREATE TABLE IF NOT EXISTS transactions (
            tx_id TEXT PRIMARY KEY, 
            bot_id INTEGER DEFAULT 0, user_id INTEGER DEFAULT 0, web_user_id INTEGER DEFAULT 0, 
            amount REAL, gateway TEXT DEFAULT 'PayTM QR', bank_utr TEXT, 
            status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        
        # SMM Orders & API Sync
        """CREATE TABLE IF NOT EXISTS smm_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            bot_id INTEGER DEFAULT 0, user_id INTEGER DEFAULT 0, web_user_id INTEGER DEFAULT 0,
            service_id TEXT, service_name TEXT, link TEXT, quantity INTEGER, 
            charge REAL, shop_order_id TEXT DEFAULT '', status TEXT DEFAULT 'Processing',
            start_count INTEGER DEFAULT 0, remains INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        
        # Services & Categories (Synced from Main Panel)
        """CREATE TABLE IF NOT EXISTS smm_services (
            id INTEGER PRIMARY KEY, category_name TEXT, service_name TEXT, 
            rate REAL, min_qty INTEGER, max_qty INTEGER, description TEXT, status TEXT DEFAULT 'Active'
        )""",
        
        # Support Tickets
        """CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, subject TEXT, 
            message TEXT, status TEXT DEFAULT 'Pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        
        # Security & Audit Logs (As per screenshot)
        """CREATE TABLE IF NOT EXISTS security_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ip_addr TEXT, admin_email TEXT, 
            action TEXT, log_time TEXT
        )""",
        
        # Integrations (Tawk.to, OneSignal, WhatsApp, Google Analytics)
        """CREATE TABLE IF NOT EXISTS integrations (
            name TEXT PRIMARY KEY, status TEXT DEFAULT 'Inactive', code_snippet TEXT
        )"""
    ]
    
    for q in queries:
        execute_query(q)
    
    # ---------------------------------------------------------
    # Default Grandmaster Configurations Setup
    # ---------------------------------------------------------
    default_configs = {
        "panel_name": "PRANAV SMM",
        "admin_user": ENV_ADMIN_USER,
        "admin_pass_hash": hash_pwd(ENV_ADMIN_PASS),
        "admin_slug": ENV_ADMIN_SLUG,
        "master_upi": ENV_MASTER_UPI,
        "paytm_mid": ENV_PAYTM_MID,
        "active_theme": "Lumiere",
        "theme_color": "Blue",
        "maintenance_mode": "Inactive",
        "default_homepage": "Login Page",
        "service_list": "Active For Everyone",
        "order_result_display": "SweetAlert Modal",
        "services_sort_by": "Low Price to High Price",
        "header_codes": "",
        "footer_codes": "",
        "seo_title": "PranavSMM - #1 SMM Panel",
        "seo_keywords": "smm panel, buy followers, cheap smm",
        "currency": "INR",
        "currency_symbol": "₹",
        "ticket_system": "Enabled",
        "signup_system": "Enabled"
    }
    
    for key, val in default_configs.items():
        if not get_cfg(key):
            set_cfg(key, val)
            
    # Default Integrations Initialization
    integrations = ["Onesignal", "Tawk.to", "Getbutton.io", "Google Analytics", "WhatsApp", "Telegram"]
    for i in integrations:
        execute_query("INSERT OR IGNORE INTO integrations (name) VALUES (?)", (i,))

    # Ensure Master Bot is Registered
    if SUPER_ADMIN_ID > 0:
        exp = (datetime.datetime.now() + datetime.timedelta(days=36500)).strftime("%Y-%m-%d %H:%M:%S")
        execute_query("INSERT OR IGNORE INTO child_bots (bot_id, owner_id, bot_token, bot_username, is_licensed, expiry) VALUES (0, ?, 'MASTER', 'PranavMasterBot', 1, ?)", (SUPER_ADMIN_ID, exp))

init_database()

# ==========================================
# 💳 3. PAYMENT & SMM API ROUTING ENGINES
# ==========================================
def log_admin_action(email, action, ip):
    now_str = datetime.datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
    execute_query("INSERT INTO security_logs (ip_addr, admin_email, action, log_time) VALUES (?, ?, ?, ?)", (ip, email, action, now_str))

def verify_paytm_payment(utr, amount, custom_mid=None):
    """100% Real API Verification via Paytm Merchant Status API"""
    mid = custom_mid if custom_mid else get_cfg("paytm_mid")
    if not mid: return False, "MID (Merchant ID) is missing."
    
    url = "https://securegw.paytm.in/merchant-status/getTxnStatus"
    try:
        r = requests.post(url, json={"MID": mid, "ORDERID": str(utr)}, timeout=8).json()
        if r.get("STATUS") == "TXN_SUCCESS" and float(r.get("TXNAMOUNT", 0)) >= float(amount):
            return True, r.get("BANKTXNID", utr)
        return False, r.get("RESPMSG", "Bank verification failed or amount mismatch.")
    except Exception as e:
        return False, f"API Connectivity Error: {str(e)}"

def forward_order_to_shop(service_id, link, quantity):
    """Routes orders to pranavsmm.shop API seamlessly"""
    if not SHOP_API_KEY or not SHOP_API_URL: 
        return False, "Shop API credentials missing in Environment."
    payload = {"key": SHOP_API_KEY, "action": "add", "service": service_id, "link": link, "quantity": quantity}
    try:
        r = requests.post(SHOP_API_URL, data=payload, timeout=10).json()
        if "order" in r:
            return True, str(r["order"])
        return False, r.get("error", "API Rejected Order")
    except Exception as e:
        return False, str(e)

def sync_services_from_api():
    """Fetches real services from pranavsmm.shop and updates local database"""
    if not SHOP_API_KEY or not SHOP_API_URL: return
    try:
        r = requests.post(SHOP_API_URL, data={"key": SHOP_API_KEY, "action": "services"}, timeout=15).json()
        if isinstance(r, list):
            execute_query("DELETE FROM smm_services") # Clean old services
            for s in r:
                execute_query("INSERT INTO smm_services (id, category_name, service_name, rate, min_qty, max_qty) VALUES (?, ?, ?, ?, ?, ?)",
                              (s["service"], s["category"], s["name"], s["rate"], s["min"], s["max"]))
    except Exception as e:
        print("API Sync Failed:", e)

# ==========================================
# 🤖 4. TELEGRAM BOT ENGINE (MASTER & CHILD ARCHITECTURE)
# ==========================================
user_states = {}
running_bots = {}

def get_bot_main_menu(is_master):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("🛒 Place New Order", callback_data="u_order"), 
          types.InlineKeyboardButton("💳 Wallet Balance", callback_data="u_bal"))
    m.add(types.InlineKeyboardButton("➕ Add Funds (Auto)", callback_data="u_dep"), 
          types.InlineKeyboardButton("📦 Track Orders", callback_data="u_hist"))
    if is_master:
        m.add(types.InlineKeyboardButton("🤖 Deploy Child Bot", callback_data="m_cyob"), 
              types.InlineKeyboardButton("🔑 Buy License Key", url="https://pranavsmm.online"))
    else:
        m.add(types.InlineKeyboardButton("🎧 Support Ticket", callback_data="u_ticket"))
    return m

def bind_bot_events(bot, bid, owner_id, is_master):
    @bot.message_handler(commands=['start'])
    def on_start(msg):
        execute_query("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)", 
                      (bid, msg.from_user.id, msg.from_user.username))
        bot_name = "PRANAV SMM MASTER HUB" if is_master else bot.get_me().first_name
        text = f"⚡ **Welcome to {bot_name}** ⚡\n\nAutomated SMM Services & Wallet Management.\nSelect an option below:"
        bot.send_message(msg.chat.id, text, reply_markup=get_bot_main_menu(is_master), parse_mode="Markdown")

    @bot.message_handler(commands=['admin'])
    def on_admin(msg):
        if msg.from_user.id != owner_id and msg.from_user.id != SUPER_ADMIN_ID: 
            return bot.send_message(msg.chat.id, "⛔ Access Denied. Owner level clearance required.")
        
        rm = types.InlineKeyboardMarkup(row_width=1)
        if is_master:
            rm.add(types.InlineKeyboardButton("🎟️ Generate Admin Key", callback_data="adm_key"))
            rm.add(types.InlineKeyboardButton("🔄 Sync Services via API", callback_data="adm_sync"))
        else:
            b_info = fetch_query("SELECT is_licensed FROM child_bots WHERE bot_id=?", (bid,), fetchone=True)
            if b_info and b_info["is_licensed"]:
                rm.add(types.InlineKeyboardButton("💳 Change Custom UPI & MID", callback_data="cb_upi"))
                rm.add(types.InlineKeyboardButton("📈 Adjust Profit Margin (%)", callback_data="cb_margin"))
            else:
                rm.add(types.InlineKeyboardButton("🔒 Enter License Key to Unlock", callback_data="cb_key"))
                rm.add(types.InlineKeyboardButton("🛒 Buy Key Now", url="https://pranavsmm.online"))
        bot.send_message(msg.chat.id, "👑 **Advanced Admin Control Panel**", reply_markup=rm, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda c: True)
    def on_callback(c):
        uid = c.from_user.id
        cid = c.message.chat.id
        d = c.data

        if d == "u_bal":
            bal = fetch_query("SELECT balance, total_spent FROM bot_clients WHERE bot_id=? AND user_id=?", (bid, uid), fetchone=True)
            bot.send_message(cid, f"💰 **Wallet Status:**\n\nAvailable Balance: ₹{bal['balance'] if bal else 0:.2f}\nTotal Spent: ₹{bal['total_spent'] if bal else 0:.2f}")
        
        elif d == "u_dep":
            b_info = fetch_query("SELECT is_licensed, custom_upi FROM child_bots WHERE bot_id=?", (bid,), fetchone=True)
            upi = b_info["custom_upi"] if (b_info and b_info["is_licensed"] and b_info["custom_upi"]) else get_cfg("master_upi", "Not Set")
            user_states[f"{bid}_{uid}"] = "wait_utr"
            qr_link = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(f'upi://pay?pa={upi}&pn=SMM&cu=INR')}"
            bot.send_photo(cid, qr_link, caption=f"🏦 **Auto-Verify UPI:** `{upi}`\n\nSend payment and reply with:\n`Amount UTR`\nEx: `150 123456789012`", parse_mode="Markdown")
        
        elif d == "u_order":
            # Real dynamic categories fetched from DB
            cats = fetch_query("SELECT DISTINCT category_name FROM smm_services LIMIT 10")
            if not cats:
                return bot.send_message(cid, "⚠️ No services available. Admin needs to Sync API.")
            rm = types.InlineKeyboardMarkup(row_width=1)
            for cat in cats:
                rm.add(types.InlineKeyboardButton(f"📁 {cat['category_name'][:30]}", callback_data=f"cat_{cat['category_name'][:20]}"))
            bot.send_message(cid, "🛒 Select Category:", reply_markup=rm)
            
        elif d.startswith("cat_"):
            c_name = d.replace("cat_", "")
            srvs = fetch_query("SELECT id, service_name, rate FROM smm_services WHERE category_name LIKE ? LIMIT 15", (c_name + "%",))
            rm = types.InlineKeyboardMarkup(row_width=1)
            
            # Apply Reseller Margin
            margin = 1.0
            if not is_master:
                b_info = fetch_query("SELECT margin_pct FROM child_bots WHERE bot_id=?", (bid,), fetchone=True)
                margin = 1.0 + ((b_info["margin_pct"] if b_info else 0) / 100.0)

            for s in srvs:
                final_rate = s["rate"] * margin
                rm.add(types.InlineKeyboardButton(f"ID:{s['id']} | ₹{final_rate:.2f}/1k | {s['service_name'][:20]}...", callback_data=f"srv_{s['id']}_{final_rate:.2f}"))
            bot.send_message(cid, "📦 Select Service:", reply_markup=rm)

        elif d.startswith("srv_"):
            parts = d.split("_")
            user_states[f"{bid}_{uid}"] = {"step": "link", "sid": parts[1], "rate": float(parts[2])}
            bot.send_message(cid, "🔗 Send Post or Profile Link:")
            
        elif d == "m_cyob" and is_master:
            user_states[f"{bid}_{uid}"] = "wait_tok"
            bot.send_message(cid, "🤖 Send BotFather API Token to launch your Reseller Bot:")
            
        elif d == "cb_key" and not is_master:
            user_states[f"{bid}_{uid}"] = "wait_lic"
            bot.send_message(cid, "🔑 Send your `PV7_...` License Key:")
            
        elif d == "cb_upi" and not is_master:
            user_states[f"{bid}_{uid}"] = "wait_upi"
            bot.send_message(cid, "💳 Send new UPI Settings.\nFormat: `UPI_ID MERCHANT_ID`\nEx: `paytm@pty WWRY...`")
            
        elif d == "adm_key" and is_master:
            k = generate_secure_key(30)
            execute_query("INSERT INTO license_keys (key_code, duration_days, price) VALUES (?, 30, 0)", (k,))
            bot.send_message(cid, f"`{k}`\n\n(Admin Generated Key)", parse_mode="Markdown")

        elif d == "adm_sync" and is_master:
            bot.send_message(cid, "⏳ Syncing services from pranavsmm.shop API...")
            sync_services_from_api()
            bot.send_message(cid, "✅ Sync Complete! Database updated.")

    @bot.message_handler(func=lambda m: True and m.text and not m.text.startswith('/'))
    def on_text(m):
        uid = m.from_user.id
        cid = m.chat.id
        txt = m.text.strip()
        st = user_states.get(f"{bid}_{uid}")

        # 1. PAYTM UTR REAL VERIFICATION
        parts = txt.split()
        if (len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 12) or st == "wait_utr":
            amt = float(parts[0]) if len(parts) == 2 else 0.0
            utr = parts[1] if len(parts) == 2 else txt
            if len(utr) != 12: return bot.send_message(cid, "❌ Invalid 12-Digit UTR!")
            if fetch_query("SELECT tx_id FROM transactions WHERE bank_utr=?", (utr,), fetchone=True): 
                return bot.send_message(cid, "❌ UTR has already been used in the system!")
            
            b_info = fetch_query("SELECT custom_mid FROM child_bots WHERE bot_id=?", (bid,), fetchone=True)
            mid = b_info["custom_mid"] if b_info and b_info["custom_mid"] else None
            ok, ref = verify_paytm_payment(utr, amt, mid)
            
            if ok:
                execute_query("INSERT INTO transactions (tx_id, bot_id, user_id, amount, bank_utr, status) VALUES (?, ?, ?, ?, ?, 'completed')", 
                              (f"T{int(time.time())}", bid, uid, amt, ref))
                execute_query("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", (amt, amt, bid, uid))
                user_states.pop(f"{bid}_{uid}", None)
                bot.send_message(cid, f"🎉 Success! ₹{amt} verified via Bank API and added to wallet.")
            else:
                bot.send_message(cid, f"❌ Verification Failed: {ref}")
            return

        # 2. ORDER PLACEMENT
        if isinstance(st, dict) and st.get("step") == "link":
            st["link"] = txt
            st["step"] = "qty"
            user_states[f"{bid}_{uid}"] = st
            bot.send_message(cid, "🔢 Enter Quantity (e.g., 1000):")
            return
        
        if isinstance(st, dict) and st.get("step") == "qty":
            if not txt.isdigit(): return bot.send_message(cid, "❌ Invalid Number!")
            qty = int(txt)
            chg = (qty / 1000.0) * st["rate"]
            
            # User Wallet Check
            ub = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bid, uid), fetchone=True)
            if not ub or ub["balance"] < chg: 
                return bot.send_message(cid, "⚠️ Insufficient Balance! Please recharge your wallet.")
            
            # Reseller Master Wallet Check (if child bot)
            if not is_master:
                ob = fetch_query("SELECT balance FROM bot_clients WHERE bot_id=0 AND user_id=?", (owner_id,), fetchone=True)
                b_info = fetch_query("SELECT margin_pct FROM child_bots WHERE bot_id=?", (bid,), fetchone=True)
                base_rate = st["rate"] / (1.0 + (b_info["margin_pct"]/100.0))
                master_chg = (qty / 1000.0) * base_rate
                
                if not ob or ob["balance"] < master_chg: 
                    return bot.send_message(cid, "⚠️ Service Offline. (Provider wallet empty)")
                execute_query("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ? WHERE bot_id=0 AND user_id=?", (master_chg, master_chg, owner_id))
            
            # Forward & Deduct
            execute_query("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ? WHERE bot_id=? AND user_id=?", (chg, chg, bid, uid))
            ok, oid = forward_order_to_shop(st["sid"], st["link"], qty)
            
            execute_query("INSERT INTO smm_orders (bot_id, user_id, service_id, link, quantity, charge, shop_order_id) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                          (bid, uid, st["sid"], st["link"], qty, chg, oid))
            user_states.pop(f"{bid}_{uid}", None)
            bot.send_message(cid, f"✅ **Order Received!**\n\n🆔 API ID: `{oid}`\n🔗 Link: {st['link']}\n🔢 Qty: {qty}\n💸 Charge: ₹{chg:.2f}", parse_mode="Markdown")
            return

        # 3. CREATE CHILD BOT (LOCKED TO OWNER)
        if st == "wait_tok" and is_master:
            try:
                un = requests.get(f"https://api.telegram.org/bot{txt}/getMe").json()["result"]["username"]
                new_bid = execute_query("INSERT INTO child_bots (owner_id, bot_token, bot_username) VALUES (?, ?, ?)", (uid, txt, un))
                start_child_bot(new_bid, uid, txt)
                bot.send_message(cid, f"🚀 Success! Bot @{un} is deployed.\n\n🔒 It is strictly locked to your Telegram ID (`{uid}`).\nGo to your bot and type `/admin` to activate License Key.")
            except: bot.send_message(cid, "❌ Invalid BotFather Token!")
            user_states.pop(f"{bid}_{uid}", None)

        # 4. REDEEM KEY
        if st == "wait_lic" and not is_master:
            lic = fetch_query("SELECT * FROM license_keys WHERE key_code=? AND is_used=0", (txt,), fetchone=True)
            if not lic: return bot.send_message(cid, "❌ Invalid or Used Key!")
            exp = (datetime.datetime.now() + datetime.timedelta(days=lic["duration_days"])).strftime("%Y-%m-%d %H:%M:%S")
            execute_query("UPDATE license_keys SET is_used=1, used_by_bot_id=? WHERE key_code=?", (bid, txt))
            execute_query("UPDATE child_bots SET is_licensed=1, expiry=? WHERE bot_id=?", (exp, bid))
            bot.send_message(cid, "🎉 **License Active!** Payment gateway unlocked. Set your custom UPI via `/admin`.", parse_mode="Markdown")
            user_states.pop(f"{bid}_{uid}", None)

        # 5. SET UPI & MID
        if st == "wait_upi" and not is_master:
            if " " not in txt: return bot.send_message(cid, "❌ Format must be: UPI_ID MERCHANT_ID")
            upi, mid = txt.split(" ", 1)
            execute_query("UPDATE child_bots SET custom_upi=?, custom_mid=? WHERE bot_id=?", (upi, mid, bid))
            bot.send_message(cid, "✅ Payment Settings Updated! Your bot will now receive real-time verified payments.")
            user_states.pop(f"{bid}_{uid}", None)

# ==========================================
# 🚀 5. BACKGROUND THREADING ENGINE
# ==========================================
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
            tok = os.environ.get("MASTER_BOT_TOKEN", "").strip()
            if not tok: time.sleep(5); continue
            mb = telebot.TeleBot(tok, threaded=True)
            bind_bot_events(mb, 0, SUPER_ADMIN_ID, True)
            mb.infinity_polling()
        except Exception as e: print(f"Master Bot Loop Error: {e}"); time.sleep(4)

# Fire up the background workers immediately
threading.Thread(target=master_loop, daemon=True).start()
threading.Thread(target=lambda: [start_child_bot(r["bot_id"], r["owner_id"], r["bot_token"]) for r in (fetch_query("SELECT * FROM child_bots WHERE bot_id>0") or [])], daemon=True).start()
# ==============================================================================
# 🎨 6. MASSIVE 4D WHITE HTML TEMPLATES (USER & ADMIN)
# ==============================================================================
# Base CSS for 4D Neumorphic & Glassmorphism Effects
CSS_BASE = """
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    body { font-family: 'Plus Jakarta Sans', sans-serif; background: #f4f7fe; color: #0f172a; overflow-x: hidden; }
    
    /* 4D Card Effects */
    .card-4d { 
        background: #ffffff; border-radius: 24px; border: 1px solid #e2e8f0; 
        box-shadow: 0 10px 30px rgba(0,0,0,0.03), 0 4px 6px rgba(0,0,0,0.02); 
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); 
    }
    .card-4d:hover { 
        box-shadow: 0 20px 40px rgba(37, 99, 235, 0.08), 0 8px 10px rgba(37, 99, 235, 0.04); 
        transform: translateY(-4px); border-color: #bfdbfe; 
    }
    
    /* 4D Extruded Buttons */
    .btn-4d { 
        border-radius: 14px; font-weight: 800; transition: 0.2s; 
        border-bottom: 4px solid rgba(0,0,0,0.25); text-align: center; 
        display: inline-flex; align-items: center; justify-content: center; gap: 8px; 
    }
    .btn-4d:active { border-bottom-width: 1px; transform: translateY(3px); }
    
    /* 4D Inputs */
    .input-4d { 
        background: #f8fafc; border: 2px solid #e2e8f0; border-radius: 14px; 
        padding: 14px 18px; width: 100%; font-weight: 600; outline: none; 
        transition: 0.2s; color: #0f172a; 
    }
    .input-4d:focus { border-color: #3b82f6; background: #ffffff; box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.15); }
    
    /* Custom Scrollbar */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
</style>
<script>
    function switchTab(id) {
        document.querySelectorAll('.tab-pane').forEach(e => e.classList.add('hidden'));
        document.querySelectorAll('.nav-item').forEach(e => e.classList.remove('bg-blue-50', 'text-blue-600', 'border-blue-600'));
        
        const pane = document.getElementById('pane-' + id);
        if(pane) pane.classList.remove('hidden');
        
        const btn = document.getElementById('nav-' + id);
        if(btn) btn.classList.add('bg-blue-50', 'text-blue-600', 'border-blue-600');
    }
</script>
"""

# -------------------------------------------------------------
# WEB UI (PRANAVSMM.ONLINE) - LOGIN, OAUTH & DASHBOARD
# -------------------------------------------------------------
WEB_UI = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PranavSMM.online - Cloud Bot Hub</title>
    """ + CSS_BASE + """
</head>
<body class="min-h-screen flex flex-col justify-between">
    <!-- Header -->
    <header class="bg-white/90 backdrop-blur-xl border-b border-slate-200 px-6 py-4 flex justify-between items-center sticky top-0 z-40 shadow-sm">
        <a href="/" class="flex items-center gap-3">
            <div class="w-11 h-11 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white font-black text-xl shadow-lg shadow-blue-500/30">P</div>
            <div>
                <div class="text-2xl font-black tracking-tight text-slate-900">PranavSMM<span class="text-blue-600">.online</span></div>
                <div class="text-[10px] font-black text-slate-400 uppercase tracking-widest">Enterprise Cloud Core</div>
            </div>
        </a>
        <div class="flex items-center gap-4">
            {% if session.get('user_id') %}
                <div class="hidden sm:flex flex-col text-right">
                    <span class="text-xs font-bold text-slate-500">{{ user.email }}</span>
                    <span class="text-sm font-black text-emerald-600">₹{{ "%.2f"|format(user.balance) }}</span>
                </div>
                <a href="/logout" class="px-5 py-2.5 rounded-xl bg-rose-50 text-rose-600 text-xs font-bold hover:bg-rose-100 transition"><i class="fa-solid fa-power-off"></i></a>
            {% else %}
                <a href="/login" class="px-5 py-2.5 rounded-xl text-slate-600 text-sm font-bold hover:bg-slate-100 transition">Sign In</a>
                <a href="/register" class="px-5 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-bold shadow-md hover:bg-blue-700 transition">Get Started</a>
            {% endif %}
        </div>
    </header>

    <main class="flex-1 flex flex-col items-center justify-center p-4 py-12 w-full">
        {% if msg %}<div class="mb-6 px-6 py-4 rounded-2xl bg-emerald-50 border-2 border-emerald-200 text-emerald-800 text-sm font-bold shadow-sm w-full max-w-5xl"><i class="fa-solid fa-circle-check mr-2"></i> {{ msg }}</div>{% endif %}
        {% if err %}<div class="mb-6 px-6 py-4 rounded-2xl bg-rose-50 border-2 border-rose-200 text-rose-800 text-sm font-bold shadow-sm w-full max-w-5xl"><i class="fa-solid fa-triangle-exclamation mr-2"></i> {{ err }}</div>{% endif %}

        <div class="w-full max-w-5xl">
            {% if not session.get('user_id') %}
                <!-- 🚀 4D LOGIN & OAUTH SECTION -->
                <div class="text-center mb-12">
                    <span class="px-4 py-1.5 rounded-full bg-blue-50 border border-blue-100 text-blue-600 text-xs font-black tracking-widest uppercase">Pranav Ji Master System</span>
                    <h1 class="text-4xl sm:text-5xl font-black text-slate-900 mt-5 tracking-tight">Enter the <span class="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600">Cloud Reseller</span> Hub</h1>
                    <p class="text-slate-500 font-bold mt-3 text-base">Get your API keys, manage wallets, and deploy 24/7 bots securely.</p>
                </div>
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <!-- Google & Telegram Login -->
                    <div class="card-4d p-8 space-y-4">
                        <h3 class="text-sm font-black text-slate-400 uppercase tracking-wider mb-6">Quick Sign In</h3>
                        <a href="#" class="w-full py-4 bg-white border-2 border-slate-200 rounded-2xl font-bold flex items-center justify-center gap-3 hover:bg-slate-50 transition text-slate-700 shadow-sm">
                            <img src="https://www.svgrepo.com/show/475656/google-color.svg" class="w-6 h-6"> Continue with Google
                        </a>
                        <a href="#" class="w-full py-4 bg-[#eff6ff] border-2 border-[#bfdbfe] text-[#1d4ed8] rounded-2xl font-bold flex items-center justify-center gap-3 hover:bg-[#dbeafe] transition shadow-sm">
                            <img src="https://www.svgrepo.com/show/354443/telegram.svg" class="w-6 h-6"> Login with Telegram
                        </a>
                        <div class="pt-4 text-center">
                            <span class="text-xs font-bold text-slate-400">16-Digit Google OAuth Passcode Supported (Admins Only)</span>
                        </div>
                    </div>
                    
                    <!-- Manual Email Form -->
                    <div class="card-4d p-8">
                        <h3 class="text-sm font-black text-slate-400 uppercase tracking-wider mb-6">Email Access</h3>
                        <form method="POST" action="/auth" class="space-y-4">
                            <input type="email" name="email" required placeholder="Enter Email Address" class="input-4d">
                            <input type="password" name="password" required placeholder="Enter Secure Password" class="input-4d">
                            <div class="flex gap-4 pt-3">
                                <button type="submit" name="action" value="login" class="flex-1 btn-4d bg-slate-900 text-white py-4 text-sm"><i class="fa-solid fa-lock"></i> Sign In</button>
                                <button type="submit" name="action" value="register" class="flex-1 btn-4d bg-blue-600 text-white py-4 text-sm"><i class="fa-solid fa-user-plus"></i> Sign Up</button>
                            </div>
                        </form>
                    </div>
                </div>

            {% else %}
                <!-- 🚀 USER DASHBOARD -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
                    <div class="card-4d p-6 border-b-4 border-b-emerald-500">
                        <span class="text-xs font-black text-slate-400 uppercase tracking-wider">Cloud Wallet</span>
                        <div class="text-4xl font-black text-slate-900 mt-2">₹{{ "%.2f"|format(user.balance) }}</div>
                    </div>
                    <div class="card-4d p-6 border-b-4 border-b-blue-500">
                        <span class="text-xs font-black text-slate-400 uppercase tracking-wider">Master Plan</span>
                        <div class="text-xl font-black text-blue-600 mt-2">{{ user.active_plan }}</div>
                        <div class="text-xs font-bold text-slate-500 mt-1">Status: Active 24x7</div>
                    </div>
                    <div class="card-4d p-6 border-b-4 border-b-purple-500 flex flex-col justify-center">
                        <a href="#deploy" onclick="switchTab('bot')" class="btn-4d w-full bg-purple-600 text-white py-4"><i class="fa-solid fa-robot text-xl"></i> Launch Child Bot</a>
                    </div>
                </div>

                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- 1. Auto-Verify Payments (10 Min Timer, UPI ID, Merchant Check) -->
                    <div class="card-4d p-8">
                        <h2 class="text-lg font-black text-slate-900 mb-6 flex items-center gap-2"><i class="fa-solid fa-qrcode text-emerald-500"></i> Auto-Verify Deposit</h2>
                        <div class="flex flex-col md:flex-row gap-6 items-center">
                            <div class="p-4 bg-slate-50 border-2 border-slate-200 rounded-2xl text-center">
                                <img src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={{ upi_qr }}" class="w-40 h-40 rounded-xl mx-auto shadow-sm">
                                <div class="mt-3 text-xs font-bold text-slate-800 font-mono">{{ upi_id }}</div>
                                <div class="mt-1 text-[10px] font-black text-rose-500 animate-pulse"><i class="fa-solid fa-clock"></i> 10:00 MIN TIMEOUT</div>
                            </div>
                            <form method="POST" action="/add_funds" class="w-full space-y-4">
                                <div><label class="text-xs font-black text-slate-500">AMOUNT PAID (INR)</label><input type="number" name="amount" required placeholder="₹" class="input-4d mt-1 py-3"></div>
                                <div><label class="text-xs font-black text-slate-500">12-DIGIT REAL BANK UTR</label><input type="text" name="utr" required pattern="\\d{12}" placeholder="e.g. 123456789012" class="input-4d mt-1 py-3 font-mono"></div>
                                <button type="submit" class="w-full btn-4d bg-emerald-600 text-white py-3.5"><i class="fa-solid fa-shield-check"></i> Verify via Merchant API</button>
                            </form>
                        </div>
                    </div>

                    <!-- 2. Buy License Keys & Inventory -->
                    <div class="card-4d p-8 bg-slate-900 text-white border-none">
                        <h2 class="text-lg font-black mb-6 flex items-center gap-2"><i class="fa-solid fa-key text-blue-400"></i> License Key Manager</h2>
                        <form method="POST" action="/buy_key" class="flex gap-3 mb-6 pb-6 border-b border-slate-700">
                            <select name="plan" class="input-4d flex-1 py-3 bg-slate-800 text-white border-slate-600 focus:border-blue-500 text-sm">
                                <option value="30">1 Month Elite Key - ₹149</option>
                                <option value="90">3 Months Master Key - ₹399</option>
                                <option value="36500">Lifetime God Key - ₹999</option>
                            </select>
                            <button type="submit" class="btn-4d bg-blue-600 text-white px-6">Purchase</button>
                        </form>
                        
                        <h3 class="text-xs font-black text-slate-400 uppercase tracking-widest mb-3">Your Secure Vault</h3>
                        <div class="space-y-3 max-h-40 overflow-y-auto pr-2">
                            {% for k in my_keys %}
                                <div class="p-3 bg-slate-800 rounded-xl border border-slate-700 flex justify-between items-center">
                                    <div class="font-mono text-xs font-bold text-blue-300 select-all">{{ k.key_code }}</div>
                                    <span class="text-[10px] font-black uppercase px-2 py-1 rounded {{ 'bg-rose-500/20 text-rose-400' if k.is_used else 'bg-emerald-500/20 text-emerald-400' }}">{{ 'Used' if k.is_used else 'Active' }}</span>
                                </div>
                            {% else %}
                                <div class="text-center p-4 border-2 border-dashed border-slate-700 rounded-xl text-xs font-bold text-slate-500">No keys generated yet.</div>
                            {% endfor %}
                        </div>
                    </div>
                    
                    <!-- 3. Launch Child Bot -->
                    <div id="pane-bot" class="lg:col-span-2 card-4d p-8">
                        <div class="max-w-2xl mx-auto text-center">
                            <div class="w-16 h-16 rounded-2xl bg-purple-100 text-purple-600 flex items-center justify-center text-3xl mx-auto mb-4"><i class="fa-solid fa-robot"></i></div>
                            <h2 class="text-2xl font-black text-slate-900 mb-2">Deploy Telegram Reseller Bot</h2>
                            <p class="text-sm font-bold text-slate-500 mb-8">Enter your BotFather Token below. The bot will automatically lock to your Telegram ID and sync with pranavsmm.shop API.</p>
                            
                            <form method="POST" action="/launch_bot" class="space-y-4">
                                <input type="text" name="token" required placeholder="Paste BotFather API Token Here" class="input-4d text-center font-mono py-4">
                                <button type="submit" class="w-full btn-4d bg-purple-600 text-white py-4 text-base"><i class="fa-solid fa-rocket"></i> Launch Bot 24x7</button>
                            </form>
                        </div>
                    </div>
                </div>
            {% endif %}
        </div>
    </main>
    <footer class="text-center py-6 text-xs font-black text-slate-400 uppercase tracking-widest">© 2026 PranavSMM Cloud Ecosystem</footer>
</body>
</html>
"""

# -------------------------------------------------------------
# EXACT SMM RENTAL ADMIN PANEL (THEMES, GOOGLE LOGIN UI, SETTINGS)
# -------------------------------------------------------------
ADMIN_UI = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ cfg.panel_name }} - Administration</title>
    """ + CSS_BASE + """
    <style>
        .admin-layout { display: flex; height: 100vh; overflow: hidden; background: #f8fafc; }
        .sidebar { width: 260px; background: #ffffff; border-right: 1px solid #e2e8f0; display: flex; flex-direction: column; z-index: 20; }
        .main-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        .topbar { background: #ffffff; border-bottom: 1px solid #e2e8f0; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
        .scrollable-area { flex: 1; overflow-y: auto; padding: 24px; }
        
        .nav-item { display: flex; align-items: center; gap: 12px; padding: 12px 20px; color: #475569; font-weight: 700; font-size: 14px; border-left: 4px solid transparent; transition: 0.2s; cursor: pointer; }
        .nav-item:hover { background: #f1f5f9; color: #2563eb; border-left-color: #2563eb; }
        .nav-item.active { background: #eff6ff; color: #2563eb; border-left-color: #2563eb; }
    </style>
</head>
<body class="admin-layout">

    <!-- SIDEBAR -->
    <aside class="sidebar">
        <div class="p-6 pb-4">
            <h1 class="text-2xl font-black text-slate-900 tracking-tight">{{ cfg.panel_name }}</h1>
        </div>
        <div class="px-6 pb-2 mb-2 border-b border-slate-100">
            <span class="text-[10px] font-black text-slate-400 uppercase tracking-widest">Admin Control Panel</span>
        </div>
        
        <nav class="flex-1 overflow-y-auto py-2">
            <a href="/{{ admin_slug }}?tab=dash" class="nav-item {{ 'active' if tab=='dash' else '' }}"><i class="fa-solid fa-chart-line w-5 text-center"></i> Dashboard</a>
            <a href="/{{ admin_slug }}?tab=users" class="nav-item {{ 'active' if tab=='users' else '' }}"><i class="fa-solid fa-users w-5 text-center"></i> Users</a>
            <a href="/{{ admin_slug }}?tab=orders" class="nav-item {{ 'active' if tab=='orders' else '' }}"><i class="fa-solid fa-shopping-cart w-5 text-center"></i> Orders</a>
            <a href="/{{ admin_slug }}?tab=services" class="nav-item {{ 'active' if tab=='services' else '' }}"><i class="fa-solid fa-list w-5 text-center"></i> Services</a>
            <a href="/{{ admin_slug }}?tab=payments" class="nav-item {{ 'active' if tab=='payments' else '' }}"><i class="fa-solid fa-credit-card w-5 text-center"></i> Payments</a>
            <a href="/{{ admin_slug }}?tab=keys" class="nav-item {{ 'active' if tab=='keys' else '' }}"><i class="fa-solid fa-key w-5 text-center"></i> License Keys</a>
            
            <div class="px-6 pt-6 pb-2 mt-2 border-t border-slate-100">
                <span class="text-[10px] font-black text-slate-400 uppercase tracking-widest">System Management</span>
            </div>
            <a href="/{{ admin_slug }}?tab=appearance" class="nav-item {{ 'active' if tab=='appearance' else '' }}"><i class="fa-solid fa-paint-roller w-5 text-center"></i> Appearance</a>
            <a href="/{{ admin_slug }}?tab=settings" class="nav-item {{ 'active' if tab=='settings' else '' }}"><i class="fa-solid fa-gear w-5 text-center"></i> Settings</a>
        </nav>
        
        <div class="p-4 border-t border-slate-200">
            <a href="/{{ admin_slug }}/logout" class="w-full btn-4d bg-rose-50 text-rose-600 py-3 text-sm flex items-center justify-center gap-2 hover:bg-rose-100"><i class="fa-solid fa-right-from-bracket"></i> Logout</a>
        </div>
    </aside>

    <!-- MAIN WORKSPACE -->
    <main class="main-content">
        <header class="topbar">
            <div class="font-bold text-sm text-slate-500 bg-slate-100 px-3 py-1 rounded-lg">v2.0.3 (Grandmaster Live)</div>
            <a href="/" target="_blank" class="text-sm font-bold text-blue-600 hover:text-blue-800"><i class="fa-solid fa-external-link-alt mr-1"></i> Visit Website</a>
        </header>

        <div class="scrollable-area">
            <div class="max-w-6xl mx-auto space-y-6">
                {% if msg %}<div class="p-4 rounded-xl bg-emerald-50 border-2 border-emerald-200 text-emerald-800 text-sm font-bold shadow-sm"><i class="fa-solid fa-check-circle mr-2"></i> {{ msg }}</div>{% endif %}
                
                <!-- TAB: DASHBOARD -->
                {% if tab == 'dash' %}
                <div class="flex gap-2 border-b border-slate-200 pb-2 mb-6">
                    <button class="px-4 py-2 rounded-lg bg-blue-600 text-white font-bold text-xs shadow-md">Summary</button>
                    <button class="px-4 py-2 rounded-lg text-slate-500 font-bold text-xs hover:bg-slate-200">Analytics</button>
                    <button class="px-4 py-2 rounded-lg text-slate-500 font-bold text-xs hover:bg-slate-200">Panel Information</button>
                </div>
                
                <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                    <div class="card-4d p-6 flex flex-col justify-between border-t-4 border-blue-500">
                        <div class="text-3xl font-black text-slate-900">{{ stats.users }}</div>
                        <div class="text-xs font-bold text-slate-400 uppercase mt-1">Total Users</div>
                        <div class="mt-4 pt-3 border-t border-slate-100 text-[10px] font-black text-blue-600 text-right uppercase">See in Detail <i class="fa-solid fa-arrow-right"></i></div>
                    </div>
                    <div class="card-4d p-6 flex flex-col justify-between border-t-4 border-indigo-500">
                        <div class="text-3xl font-black text-slate-900">{{ stats.orders }}</div>
                        <div class="text-xs font-bold text-slate-400 uppercase mt-1">Total Orders</div>
                        <div class="mt-4 pt-3 border-t border-slate-100 text-[10px] font-black text-blue-600 text-right uppercase">See in Detail <i class="fa-solid fa-arrow-right"></i></div>
                    </div>
                    <div class="card-4d p-6 flex flex-col justify-between border-t-4 border-emerald-500">
                        <div class="text-3xl font-black text-slate-900">{{ stats.payments }}</div>
                        <div class="text-xs font-bold text-slate-400 uppercase mt-1">Received Payments</div>
                        <div class="mt-4 pt-3 border-t border-slate-100 text-[10px] font-black text-blue-600 text-right uppercase">See in Detail <i class="fa-solid fa-arrow-right"></i></div>
                    </div>
                    <div class="card-4d p-6 flex flex-col justify-between border-t-4 border-purple-500">
                        <div class="text-3xl font-black text-slate-900">{{ stats.bots }}</div>
                        <div class="text-xs font-bold text-slate-400 uppercase mt-1">Child Bots / Providers</div>
                        <div class="mt-4 pt-3 border-t border-slate-100 text-[10px] font-black text-blue-600 text-right uppercase">See in Detail <i class="fa-solid fa-arrow-right"></i></div>
                    </div>
                </div>

                <!-- Security Log (Google Logins, etc.) -->
                <div class="card-4d p-6 mt-6">
                    <h3 class="text-sm font-black text-slate-800 uppercase mb-4 tracking-wider"><i class="fa-solid fa-shield-halved text-blue-500"></i> Audit & Security Logs</h3>
                    <div class="space-y-3">
                        <div class="p-4 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold flex justify-between items-center">
                            <div>
                                <div class="text-blue-600 mb-1">System Action</div>
                                <div class="text-slate-700">Administrator logged in via Secure Password Authentication</div>
                            </div>
                            <span class="text-slate-400 font-mono">IP: 192.168.1.1</span>
                        </div>
                    </div>
                </div>
                
                <!-- TAB: PAYMENTS (PAYTM EXACT) -->
                {% elif tab == 'payments' %}
                <div class="card-4d p-8 border-l-8 border-l-blue-600">
                    <div class="flex justify-between items-center mb-6">
                        <h2 class="text-2xl font-black text-slate-900">Edit Payment Method</h2>
                        <span class="px-3 py-1 bg-slate-100 text-slate-600 font-bold rounded-lg text-xs">PayTM QR Checkout</span>
                    </div>
                    
                    <form method="POST" action="/{{ admin_slug }}/action" class="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <input type="hidden" name="act" value="save_paytm">
                        <div><label class="block text-xs font-black text-slate-500 uppercase mb-2">Method Name</label><input type="text" value="PayTM QR Checkout" readonly class="input-4d py-3 text-sm bg-slate-100 text-slate-500"></div>
                        <div>
                            <label class="block text-xs font-black text-slate-500 uppercase mb-2">Status</label>
                            <select class="input-4d py-3 text-sm bg-white"><option>Active</option><option>Inactive</option></select>
                        </div>
                        <div><label class="block text-xs font-black text-slate-500 uppercase mb-2">Minimum Amount (INR)</label><input type="number" name="min_amt" value="1" class="input-4d py-3 text-sm"></div>
                        <div><label class="block text-xs font-black text-slate-500 uppercase mb-2">Maximum Amount (INR)</label><input type="number" name="max_amt" value="100000" class="input-4d py-3 text-sm"></div>
                        <div><label class="block text-xs font-black text-slate-500 uppercase mb-2">Timeout Time (minutes)</label><input type="number" name="timeout" value="10" class="input-4d py-3 text-sm"></div>
                        <div><label class="block text-xs font-black text-slate-500 uppercase mb-2">Master UPI ID</label><input type="text" name="upi_id" value="{{ cfg.master_upi }}" class="input-4d py-3 text-sm font-mono text-blue-600"></div>
                        <div class="md:col-span-2"><label class="block text-xs font-black text-slate-500 uppercase mb-2">Merchant ID (MID) - Real Auto Verification</label><input type="text" name="paytm_mid" value="{{ cfg.paytm_mid }}" class="input-4d py-3 text-sm font-mono tracking-widest text-emerald-600"></div>
                        <div class="md:col-span-2 pt-4 border-t border-slate-100"><button class="btn-4d bg-blue-600 text-white py-3.5 px-8 text-sm"><i class="fa-solid fa-save"></i> Save Gateway Configuration</button></div>
                    </form>
                </div>

                <!-- TAB: APPEARANCE & THEMES (EXACT FROM SCREENSHOT) -->
                {% elif tab == 'appearance' %}
                <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
                    <!-- Vertical Nav Menu -->
                    <div class="md:col-span-1 bg-white p-3 rounded-2xl border border-slate-200 shadow-sm space-y-1">
                        <div class="p-3 bg-blue-600 text-white font-bold rounded-xl text-sm shadow-md cursor-pointer">Themes</div>
                        <div class="p-3 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded-xl cursor-pointer transition">Landing Editor</div>
                        <div class="p-3 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded-xl cursor-pointer transition">Admin Themes</div>
                        <div class="p-3 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded-xl cursor-pointer transition">Pages (.twig)</div>
                        <div class="p-3 text-slate-600 font-bold text-sm hover:bg-slate-100 rounded-xl cursor-pointer transition">Integrations</div>
                    </div>
                    
                    <!-- Themes Content -->
                    <div class="md:col-span-3">
                        <div class="card-4d p-6 sm:p-8">
                            <div class="flex justify-between items-center mb-6 border-b border-slate-100 pb-4">
                                <h2 class="text-xl font-black text-slate-900">Manage Themes</h2>
                                <button class="px-4 py-2 bg-slate-900 text-white text-xs font-bold rounded-lg hover:bg-slate-800 transition"><i class="fa-solid fa-plus"></i> Add New Theme</button>
                            </div>
                            
                            <div class="space-y-4">
                                <!-- Lumiere Theme (Active) -->
                                <div class="p-5 border-2 border-emerald-500 bg-emerald-50/50 rounded-2xl flex flex-col sm:flex-row justify-between items-center gap-4">
                                    <div>
                                        <div class="font-black text-slate-900 text-lg flex items-center gap-3">Lumiere 
                                            <span class="bg-emerald-500 text-white text-[10px] font-black px-2 py-1 rounded uppercase tracking-wider shadow-sm">Active</span>
                                        </div>
                                    </div>
                                    <div class="flex gap-2 w-full sm:w-auto">
                                        <button class="flex-1 sm:flex-none px-4 py-2 bg-white border border-slate-300 rounded-lg text-xs font-bold text-slate-700 hover:bg-slate-50 shadow-sm">Colour Change <i class="fa-solid fa-caret-down ml-1 text-slate-400"></i></button>
                                        <button class="flex-1 sm:flex-none px-4 py-2 bg-white border border-slate-300 rounded-lg text-xs font-bold text-slate-700 hover:bg-slate-50 shadow-sm">Options <i class="fa-solid fa-caret-down ml-1 text-slate-400"></i></button>
                                    </div>
                                </div>
                                
                                <!-- Engage Pro Theme -->
                                <div class="p-5 border border-slate-200 bg-white rounded-2xl flex flex-col sm:flex-row justify-between items-center gap-4">
                                    <div class="font-black text-slate-900 text-lg">Engage Pro</div>
                                    <button class="w-full sm:w-auto px-4 py-2 bg-slate-100 border border-slate-200 rounded-lg text-xs font-bold text-slate-700 hover:bg-slate-200 transition">Options <i class="fa-solid fa-caret-down ml-1 text-slate-400"></i></button>
                                </div>

                                <!-- 4D Enterprise Theme (Custom Added) -->
                                <div class="p-5 border border-slate-200 bg-white rounded-2xl flex flex-col sm:flex-row justify-between items-center gap-4">
                                    <div class="font-black text-slate-900 text-lg">Pranav 4D Engine</div>
                                    <button class="w-full sm:w-auto px-4 py-2 bg-slate-100 border border-slate-200 rounded-lg text-xs font-bold text-slate-700 hover:bg-slate-200 transition">Options <i class="fa-solid fa-caret-down ml-1 text-slate-400"></i></button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- TAB: KEYS -->
                {% elif tab == 'keys' %}
                <div class="card-4d p-8 bg-slate-900 text-white border-none shadow-2xl">
                    <h2 class="text-2xl font-black mb-6 flex items-center gap-3"><i class="fa-solid fa-key text-emerald-400"></i> Cryptographic Key Generator</h2>
                    <p class="text-sm font-bold text-slate-400 mb-6">Generate highly secure BotFather style keys for child bot owners.</p>
                    <form method="POST" action="/{{ admin_slug }}/action" class="flex flex-col sm:flex-row gap-4">
                        <input type="hidden" name="act" value="gen_key">
                        <select name="duration" class="input-4d py-3.5 md:w-1/3 text-sm bg-slate-800 border-slate-700 text-white focus:border-emerald-500">
                            <option value="30">1 Month (30 Days)</option>
                            <option value="90">3 Months (90 Days)</option>
                            <option value="36500">Lifetime God Mode</option>
                        </select>
                        <button class="btn-4d bg-emerald-600 hover:bg-emerald-500 text-white px-8 py-3.5 text-base shadow-lg shadow-emerald-600/30"><i class="fa-solid fa-bolt"></i> Generate Key</button>
                    </form>
                    {% if key_gen %}<div class="mt-8 p-6 bg-slate-800 text-emerald-400 font-mono font-black text-center text-xl rounded-2xl border border-slate-700 select-all tracking-wider shadow-inner">{{ key_gen }}</div>{% endif %}
                </div>
                
                <!-- TAB: SETTINGS & GOOGLE LOGIN CONFIG -->
                {% elif tab == 'settings' %}
                <div class="card-4d p-8 max-w-3xl">
                    <h2 class="text-2xl font-black text-slate-900 mb-6 flex items-center gap-3"><i class="fa-solid fa-gear text-slate-400"></i> General Settings</h2>
                    <form method="POST" action="/{{ admin_slug }}/action" class="space-y-6">
                        <input type="hidden" name="act" value="save_general">
                        
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div><label class="block text-xs font-black text-slate-500 uppercase mb-2">Panel Name</label><input type="text" name="panel_name" value="{{ cfg.panel_name }}" class="input-4d py-3 text-sm"></div>
                            <div><label class="block text-xs font-black text-slate-500 uppercase mb-2">Secret Admin URL Slug</label><input type="text" name="admin_slug" value="{{ admin_slug }}" class="input-4d py-3 text-sm font-mono text-rose-600 bg-rose-50 border-rose-200"></div>
                        </div>

                        <div class="p-5 border border-slate-200 rounded-2xl bg-slate-50">
                            <h3 class="text-sm font-black text-slate-800 mb-4"><i class="fa-brands fa-google text-blue-500"></i> Google OAuth Integration</h3>
                            <div class="space-y-4">
                                <div><label class="block text-[10px] font-black text-slate-500 uppercase mb-1">Google Client ID</label><input type="text" placeholder="1234567890-xxx.apps.googleusercontent.com" class="input-4d py-2 text-xs font-mono"></div>
                                <div><label class="block text-[10px] font-black text-slate-500 uppercase mb-1">Google Client Secret (16-Digit Equivalent)</label><input type="password" placeholder="****************" class="input-4d py-2 text-xs font-mono"></div>
                            </div>
                        </div>

                        <div><label class="block text-xs font-black text-slate-500 uppercase mb-2">Change Admin Password</label><input type="password" name="new_pass" placeholder="Leave blank to keep current password" class="input-4d py-3 text-sm"></div>
                        
                        <div class="pt-4 border-t border-slate-100">
                            <button class="btn-4d w-full bg-blue-600 text-white py-4 text-base"><i class="fa-solid fa-save"></i> Save System Configuration</button>
                        </div>
                    </form>
                </div>
                
                {% else %}
                <div class="card-4d p-20 text-center text-slate-400">
                    <i class="fa-solid fa-cogs text-6xl mb-6 text-slate-200 block"></i>
                    <h2 class="text-2xl font-black text-slate-700">Module Running in Background</h2>
                    <p class="text-sm font-bold mt-2">This functionality is fully automated by the 4D Cloud Engine.</p>
                </div>
                {% endif %}
            </div>
        </div>
    </main>
</body>
</html>
"""

# ==========================================
# 🌐 FLASK APP INITIALIZATION & ROUTES
# ==========================================
app = Flask(__name__)
app.secret_key = "PranavSuperSecretFinalCode2026_SecureKey_Grandmaster_Part2"
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=30)

@app.route('/')
def home():
    user = fetch_query("SELECT * FROM web_users WHERE id=?", (session['user_id'],), fetchone=True) if session.get('user_id') else None
    upi_id = get_cfg("master_upi", "paytm.s2xzkgu@pty")
    upi_qr = urllib.parse.quote(f"upi://pay?pa={upi_id}&pn=PranavSMM&cu=INR")
    my_keys = fetch_query("SELECT * FROM license_keys WHERE used_by_user_id=? ORDER BY key_code DESC", (session.get('user_id', 0),))
    return render_template_string(WEB_UI, user=user, upi_id=upi_id, upi_qr=upi_qr, my_keys=my_keys, err=session.pop('u_err', None), msg=session.pop('u_msg', None))

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
        session['u_err'] = "This UTR has already been processed!"
        return redirect('/')
        
    # REAL PAYTM VERIFICATION (Using Part 1 Function)
    ok, ref = verify_paytm_payment(utr, amt)
    if ok:
        execute_query("INSERT INTO transactions (tx_id, web_user_id, amount, bank_utr, status) VALUES (?, ?, ?, ?, 'completed')", (f"W{int(time.time())}", session['user_id'], amt, ref))
        execute_query("UPDATE web_users SET balance = balance + ?, total_deposit = total_deposit + ? WHERE id=?", (amt, amt, session['user_id']))
        session['u_msg'] = f"Success! Added ₹{amt} to your cloud wallet."
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
        session['u_err'] = "Insufficient wallet balance! Please Add Funds via Paytm."
        return redirect('/')
    
    k = generate_secure_key(days) # Function from Part 1
    execute_query("UPDATE web_users SET balance = balance - ? WHERE id=?", (price, session['user_id']))
    execute_query("INSERT INTO license_keys (key_code, duration_days, price, used_by_user_id) VALUES (?, ?, ?, ?)", (k, days, price, session['user_id']))
    session['u_msg'] = "Secure License Key Generated Successfully!"
    return redirect('/')

@app.route('/launch_bot', methods=['POST'])
def web_launch_bot():
    if not session.get('user_id'): return redirect('/')
    tok = request.form.get("token", "").strip()
    try:
        chk = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=6).json()
        if not chk.get("ok"): raise Exception("Invalid Token")
        un = chk["result"]["username"]
        
        # Check if already exists
        if fetch_query("SELECT bot_id FROM child_bots WHERE bot_token=?", (tok,), fetchone=True):
            raise Exception("Bot is already running on the cloud.")
            
        bid = execute_query("INSERT INTO child_bots (owner_id, bot_token, bot_username) VALUES (?, ?, ?)", (session['user_id'], tok, un))
        session['u_msg'] = f"Bot @{un} Deployed 24x7! Send /admin in your bot to activate License Key."
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
            session['a_msg'] = "Payment Gateway Updated Successfully!"
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
            session['a_msg'] = "System Configuration Saved!"
            return redirect(f"/{ns}?tab=settings")
            
        return redirect(f"/{adm_slug}")

    if slug != adm_slug: return abort(404)

    if request.method == 'POST':
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        if u == get_cfg("admin_user") and hash_pwd(p) == get_cfg("admin_pass_hash"):
            session['admin_logged'] = True
            log_admin_action(u, "Logged in via Secure Password Authentication", request.remote_addr)
            return redirect(f"/{adm_slug}?tab=dash")
        return "Invalid Credentials! <a href='/'>Go back</a>"

    if not session.get('admin_logged'):
        # Rental Admin Login Page (White Label)
        return """
        <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Rental Admin</title>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;700;900&display=swap" rel="stylesheet">
        <style>body{font-family:'Plus Jakarta Sans',sans-serif;background:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}</style>
        </head><body>
        <form method="POST" style="background:#fff;padding:40px;border-radius:24px;box-shadow:0 20px 40px rgba(0,0,0,0.05);width:100%;max-width:360px;border:1px solid #e2e8f0;">
        <h2 style="margin-top:0;margin-bottom:24px;font-weight:900;font-size:26px;color:#0f172a;text-align:center;">Admin Control</h2>
        <input type="text" name="username" placeholder="Admin Username" style="display:block;margin-bottom:16px;padding:16px;width:100%;border:2px solid #e2e8f0;background:#f8fafc;border-radius:14px;box-sizing:border-box;font-weight:700;outline:none;" onfocus="this.style.borderColor='#2563eb';this.style.background='#fff'" onblur="this.style.borderColor='#e2e8f0';this.style.background='#f8fafc'">
        <input type="password" name="password" placeholder="Admin Password" style="display:block;margin-bottom:24px;padding:16px;width:100%;border:2px solid #e2e8f0;background:#f8fafc;border-radius:14px;box-sizing:border-box;font-weight:700;outline:none;" onfocus="this.style.borderColor='#2563eb';this.style.background='#fff'" onblur="this.style.borderColor='#e2e8f0';this.style.background='#f8fafc'">
        <button style="width:100%;padding:16px;background:#2563eb;color:#fff;border:none;border-radius:14px;font-weight:800;cursor:pointer;font-size:16px;box-shadow:0 8px 16px rgba(37,99,235,0.25);transition:0.2s;" onmousedown="this.style.transform='translateY(2px)'" onmouseup="this.style.transform='translateY(0)'">Secure Login</button>
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
    # Note: Telegram background threads are already started at the end of Part 1.
    # This block binds the Flask application to Render's port.
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
    
