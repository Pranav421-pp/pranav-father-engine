import os
import sys
import time
import random
import sqlite3
import threading
import requests
from flask import Flask, request, jsonify
import telebot
from telebot import types
from cryptography.fernet import Fernet

RENDER_PORT = int(os.environ.get("PORT", 8081))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
MASTER_BOT_TOKEN = os.environ.get("MASTER_BOT_TOKEN", "").strip()
SUPER_ADMIN_ID = int(os.environ.get("ADMIN_ID", "8585055903"))

MAIN_PANEL_URL = os.environ.get("MAIN_PANEL_URL", "https://pranavsmm.shop/api/v2")
MAIN_PANEL_API_KEY = os.environ.get("MAIN_PANEL_API_KEY", "").strip()

SECRET_KEY = os.environ.get("SECRET_KEY", Fernet.generate_key().decode())
if isinstance(SECRET_KEY, str):
    SECRET_KEY = SECRET_KEY.encode()
cipher_suite = Fernet(SECRET_KEY)

DB_PATH = "father_master_engine.db"
app = Flask(__name__)

bot_threads = {}
user_states = {}
master_is_running = False

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS child_bots (
        bot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        bot_token_enc TEXT UNIQUE,
        bot_username TEXT,
        bot_name TEXT,
        pro_mode INTEGER DEFAULT 1,
        log_channel TEXT DEFAULT '',
        force_channel TEXT DEFAULT '',
        support_contact TEXT DEFAULT '@pranavsmm',
        fampay_endpoint TEXT DEFAULT '',
        fampay_apikey TEXT DEFAULT '',
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bot_clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id INTEGER,
        user_id INTEGER,
        username TEXT,
        balance REAL DEFAULT 0.0,
        banned INTEGER DEFAULT 0,
        UNIQUE(bot_id, user_id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bot_services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id INTEGER,
        platform TEXT,
        sub_category TEXT,
        service_name TEXT,
        cost_price REAL DEFAULT 1.0,
        selling_price_per_100 REAL DEFAULT 3.0,
        main_api_service_id TEXT DEFAULT '100',
        description TEXT DEFAULT 'Good Quality Speed Fast',
        is_published INTEGER DEFAULT 0
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bot_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id INTEGER,
        user_id INTEGER,
        service_name TEXT,
        link TEXT,
        quantity INTEGER,
        charge REAL,
        api_order_id TEXT,
        status TEXT DEFAULT 'Processing',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        tx_id TEXT PRIMARY KEY,
        bot_id INTEGER,
        user_id INTEGER,
        amount REAL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

init_db()

def seed_default_services(bot_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as count FROM bot_services WHERE bot_id=?", (bot_id,))
    if cur.fetchone()["count"] == 0:
        defaults = [
            ("Instagram", "IG Likes", "IG Like Indian", 1.0, 3.0, "101", "Quality: Good Quality | Speed: Fast"),
            ("Instagram", "IG Followers", "Cheap Followers", 4.0, 8.0, "102", "Quality: Real Mix | Speed: Superfast"),
            ("Instagram", "IG Views", "Reel Views Instant", 0.03, 0.5, "103", "Non-Drop Fast High Speed"),
            ("Facebook", "FB Followers", "FB Page Followers", 15.0, 30.0, "104", "Safe Non Drop High Retention"),
            ("Facebook", "FB Likes", "FB Post Likes", 5.0, 10.0, "105", "Fast Delivery Good Quality"),
            ("Telegram", "TG Members", "Telegram Channel Members", 8.0, 15.0, "106", "Real Members 0-1 Hour Start"),
            ("Telegram", "TG Views", "Telegram Post Views", 0.1, 0.5, "107", "Instant Speed Fast")
        ]
        for d in defaults:
            cur.execute("""
            INSERT INTO bot_services (bot_id, platform, sub_category, service_name, cost_price, selling_price_per_100, main_api_service_id, description, is_published)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (bot_id, d[0], d[1], d[2], d[3], d[4], d[5], d[6]))
        conn.commit()
    conn.close()

@app.route('/api/payment/webhook', methods=['POST'])
def payment_webhook():
    data = request.json or request.form.to_dict()
    tx_id = data.get("orderId") or data.get("tx_id")
    status = data.get("status", "").upper()
    amount = float(data.get("amount", 0.0))

    if not tx_id or status not in ["SUCCESS", "TXN_SUCCESS", "PAID"]:
        return jsonify({"status": "ignored"}), 200

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT bot_id, user_id, amount, status FROM transactions WHERE tx_id=?", (tx_id,))
    tx = cur.fetchone()

    if tx and tx["status"] == "pending":
        bot_id = tx["bot_id"]
        user_id = tx["user_id"]
        credited_amt = tx["amount"]

        cur.execute("UPDATE bot_clients SET balance = balance + ? WHERE bot_id=? AND user_id=?", 
                    (credited_amt, bot_id, user_id))
        cur.execute("UPDATE transactions SET status='completed' WHERE tx_id=?", (tx_id,))
        conn.commit()

        cur.execute("SELECT bot_token_enc, log_channel FROM child_bots WHERE bot_id=?", (bot_id,))
        b_row = cur.fetchone()
        conn.close()

        if b_row:
            try:
                dec_token = cipher_suite.decrypt(b_row["bot_token_enc"].encode()).decode()
                tb = telebot.TeleBot(dec_token)
                tb.send_message(user_id, f"Payment Success!\n\nDeposited: Rs {credited_amt:.2f}\nRef ID: {tx_id}\nWallet balance updated automatically!")
                if b_row["log_channel"]:
                    tb.send_message(b_row["log_channel"], f"[DEPOSIT SUCCESS]\nUser: {user_id}\nAmount: Rs {credited_amt}\nRef: {tx_id}")
            except Exception:
                pass

        return jsonify({"status": "success"}), 200

    conn.close()
    return jsonify({"status": "already_done"}), 200

def run_child_bot_loop(bot_id, owner_id, token, bot_username, bot_name):
    seed_default_services(bot_id)
    while True:
        try:
            cbot = telebot.TeleBot(token, threaded=True)
            try:
                requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=True", timeout=5)
            except Exception:
                pass

            def get_user_main_menu():
                m = types.InlineKeyboardMarkup(row_width=2)
                m.add(
                    types.InlineKeyboardButton("💳 𝗕𝗮𝗹𝗮𝗻𝗰𝗲", callback_data="u_bal"),
                    types.InlineKeyboardButton("💰 𝗗𝗲𝗽𝗼𝘀𝗶𝘁", callback_data="u_dep")
                )
                m.add(
                    types.InlineKeyboardButton("🗓️ 𝗛𝗶𝘀𝘁𝗼𝗿𝘆", callback_data="u_hist"),
                    types.InlineKeyboardButton("🛒 𝗢𝗿𝗱𝗲𝗿 𝗡𝗼𝘄", callback_data="u_ord")
                )
                m.add(
                    types.InlineKeyboardButton("💬 𝗦𝘂𝗽𝗽𝗼𝗿𝘁", callback_data="u_supp"),
                    types.InlineKeyboardButton("👑 𝗖𝗬𝗢𝗕", callback_data="u_cyob")
                )
                return m

            def get_owner_panel():
                m = types.InlineKeyboardMarkup(row_width=2)
                m.add(
                    types.InlineKeyboardButton("𝗦𝗲𝗿𝘃𝗶𝗰𝗲𝘀", callback_data="a_services"),
                    types.InlineKeyboardButton("𝗣𝗮𝘆𝗺𝗲𝗻𝘁", callback_data="a_payment")
                )
                m.add(
                    types.InlineKeyboardButton("𝗨𝘀𝗲𝗿𝘀", callback_data="a_users"),
                    types.InlineKeyboardButton("𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁", callback_data="a_bcast")
                )
                m.add(
                    types.InlineKeyboardButton("𝗔𝗱𝗱 𝗕𝗮𝗹𝗮𝗻𝗰𝗲", callback_data="a_addbal"),
                    types.InlineKeyboardButton("𝗗𝗲𝗱𝘂𝗰𝘁 𝗕𝗮𝗹𝗮𝗻𝗰𝗲", callback_data="a_dedbal")
                )
                m.add(
                    types.InlineKeyboardButton("𝗕𝗮𝗻 𝗨𝘀𝗲𝗿", callback_data="a_ban"),
                    types.InlineKeyboardButton("𝗨𝗻𝗯𝗮𝗻 𝗨𝘀𝗲𝗿", callback_data="a_unban")
                )
                m.add(
                    types.InlineKeyboardButton("𝗟𝗼𝗴 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", callback_data="a_logchan"),
                    types.InlineKeyboardButton("𝗙𝗼𝗿𝗰𝗲 𝗦𝘂𝗯", callback_data="a_forcesub")
                )
                m.add(
                    types.InlineKeyboardButton("𝗦𝘂𝗽𝗽𝗼𝗿𝘁 𝗖𝗼𝗻𝘁𝗮𝗰𝘁", callback_data="a_suppcontact"),
                    types.InlineKeyboardButton("𝗧𝘂𝗿𝗻 𝗢𝗳𝗳 𝗣𝗿𝗼 𝗠𝗼𝗱𝗲", callback_data="a_promode")
                )
                m.add(types.InlineKeyboardButton("𝗠𝗮𝗶𝗻 𝗠𝗲𝗻𝘂", callback_data="a_back_main"))
                return m

            def is_user_subscribed(uid):
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT force_channel FROM child_bots WHERE bot_id=?", (bot_id,))
                row = cur.fetchone()
                conn.close()
                if not row or not row["force_channel"]:
                    return True
                ch = row["force_channel"].strip()
                try:
                    res = cbot.get_chat_member(ch, uid)
                    return res.status in ['member', 'administrator', 'creator']
                except Exception:
                    return True

            @cbot.message_handler(commands=['start'])
            def c_start(msg):
                uid = msg.from_user.id
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT banned FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid))
                urow = cur.fetchone()
                if urow and urow["banned"] == 1:
                    cbot.reply_to(msg, "You are banned from using this bot!")
                    conn.close()
                    return

                if not is_user_subscribed(uid):
                    cur.execute("SELECT force_channel FROM child_bots WHERE bot_id=?", (bot_id,))
                    ch = cur.fetchone()["force_channel"]
                    conn.close()
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("Join Channel", url=f"https://t.me/{ch.replace('@', '')}"))
                    m.add(types.InlineKeyboardButton("Check Joined", callback_data="u_check_joined"))
                    cbot.send_message(msg.chat.id, f"Please join {ch} first to use this bot!", reply_markup=m)
                    return

                cur.execute("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)",
                            (bot_id, uid, msg.from_user.username or 'User'))
                conn.commit()
                conn.close()

                welcome_card = (
                    "💎*𝗠𝗔𝗜𝗡 𝗠𝗘𝗡𝗨*💎 ~\n\n"
                    "╭━━━━━━━━━━━━━━━━━━╮\n"
                    "  ✨ 𝓦𝓔𝓛𝓒𝓞𝓜𝓔  ★ 𝗩𝗜𝗣 ✨\n"
                    "  ❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                    "  🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍\n"
                    "  🥶  𝗖𝗵𝗼𝗼𝘀𝗲 𝗔𝗻 𝗢𝗽𝘁𝗶𝗼𝗻 𝗕𝗲𝗹𝗼𝘄 🎀\n"
                    "  🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍\n"
                    "  ❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                    "╰━━━━━━━━━━━━━━━━━━╯"
                )
                cbot.send_message(msg.chat.id, welcome_card, reply_markup=get_user_main_menu(), parse_mode="Markdown")

            @cbot.message_handler(commands=['admin'])
            def c_admin(msg):
                if msg.from_user.id != owner_id:
                    cbot.reply_to(msg, "Access Denied: You are not the owner of this bot.")
                    return
                admin_text = (
                    "╔════════════════════════════╗\n"
                    "   👑 𝗢𝗪𝗡𝗘𝗥 𝗣𝗔𝗡𝗘𝗟\n"
                    "╚════════════════════════════╝\n\n"
                    f"🤖 @{bot_username}\n\n"
                    "𝗠𝗮𝗻𝗮𝗴𝗲 𝗬𝗼𝘂𝗿 𝗕𝗼𝘁 𝗦𝗲𝘁𝘁𝗶𝗻𝗴𝘀: 𝗦𝗲𝘁 𝗬𝗼𝘂𝗿 𝗢𝘄𝗻 𝗦𝗲𝗿𝘃𝗶𝗰𝗲 𝗣𝗿𝗶𝗰𝗲𝘀, "
                    "𝗖𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗲 𝗬𝗼𝘂𝗿 𝗣𝗮𝘆𝗺𝗲𝗻𝘁 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 𝗔𝗣𝗜, 𝗔𝗻𝗱 𝗠𝗮𝗻𝗮𝗴𝗲 𝗬𝗼𝘂𝗿 𝗨𝘀𝗲𝗿𝘀.\n\n"
                    "☆━─━─━─━─━─━─━─━☆"
                )
                cbot.send_message(msg.chat.id, admin_text, reply_markup=get_owner_panel(), parse_mode="Markdown")

            @cbot.callback_query_handler(func=lambda c: True)
            def c_callbacks(call):
                uid = call.from_user.id
                cid = call.message.chat.id
                data = call.data

                if data == "u_check_joined":
                    if is_user_subscribed(uid):
                        cbot.delete_message(cid, call.message.message_id)
                        cbot.send_message(cid, "Channel verified successfully! Send /start")
                    else:
                        cbot.answer_callback_query(call.id, "You have not joined yet!", show_alert=True)
                    return

                if data == "u_back_main":
                    welcome_card = (
                        "💎*𝗠𝗔𝗜𝗡 𝗠𝗘𝗡𝗨*💎 ~\n\n"
                        "╭━━━━━━━━━━━━━━━━━━╮\n"
                        "  ✨ 𝓦𝓔𝓛𝓒𝓞𝓜𝓔  ★ 𝗩𝗜𝗣 ✨\n"
                        "  ❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                        "  🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍\n"
                        "  🥶  𝗖𝗵𝗼𝗼𝘀𝗲 𝗔𝗻 𝗢𝗽𝘁𝗶𝗼𝗻 𝗕𝗲𝗹𝗼𝘄 🎀\n"
                        "  🤍🤍🤍🤍🤍🤍🤍🤍🤍🤍\n"
                        "  ❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                        "╰━━━━━━━━━━━━━━━━━━╯"
                    )
                    cbot.edit_message_text(welcome_card, cid, call.message.message_id, reply_markup=get_user_main_menu(), parse_mode="Markdown")

                elif data == "u_bal":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid))
                    row = cur.fetchone()
                    conn.close()
                    bal = row["balance"] if row else 0.0
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("💰 𝗗𝗲𝗽𝗼𝘀𝗶𝘁", callback_data="u_dep"), types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main"))
                    cbot.edit_message_text(f"Account Balance:\n\nUser ID: {uid}\nWallet: Rs {bal:.2f}", cid, call.message.message_id, reply_markup=m)

                elif data == "u_dep":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT fampay_endpoint, fampay_apikey FROM child_bots WHERE bot_id=?", (bot_id,))
                    b_set = cur.fetchone()
                    conn.close()

                    if not b_set["fampay_endpoint"] or not b_set["fampay_apikey"]:
                        m = types.InlineKeyboardMarkup()
                        m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main"))
                        cbot.edit_message_text("Deposit Unavailable. Owner has not configured payment gateway yet.", cid, call.message.message_id, reply_markup=m)
                        return

                    m = types.InlineKeyboardMarkup(row_width=1)
                    m.add(types.InlineKeyboardButton("⚡ Deposit (FamPay Instant Automated)", callback_data="u_dep_fampay_go"))
                    m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main"))
                    cbot.edit_message_text("Instant Automated Deposit via FamPay/UPI\nSelect deposit to continue:", cid, call.message.message_id, reply_markup=m)

                elif data == "u_dep_fampay_go":
                    user_states[f"{bot_id}_{uid}"] = "wait_user_dep_amt"
                    cbot.send_message(cid, "Enter amount you want to deposit (e.g. 10):")

                elif data == "u_ord":
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(
                        types.InlineKeyboardButton("📸 Instagram", callback_data="u_plat_Instagram"),
                        types.InlineKeyboardButton("📘 Facebook", callback_data="u_plat_Facebook")
                    )
                    m.add(
                        types.InlineKeyboardButton("✈️ Telegram", callback_data="u_plat_Telegram"),
                        types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main")
                    )
                    cbot.edit_message_text("Select Platform:", cid, call.message.message_id, reply_markup=m)

                elif data.startswith("u_plat_"):
                    plat = data.replace("u_plat_", "")
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT DISTINCT sub_category FROM bot_services WHERE bot_id=? AND platform=?", (bot_id, plat))
                    subs = cur.fetchall()
                    conn.close()

                    m = types.InlineKeyboardMarkup(row_width=1)
                    for s in subs:
                        m.add(types.InlineKeyboardButton(s["sub_category"], callback_data=f"u_sub_{plat}_{s['sub_category']}"))
                    m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_ord"))
                    cbot.edit_message_text(f"{plat} Categories:", cid, call.message.message_id, reply_markup=m)

                elif data.startswith("u_sub_"):
                    parts = data.split("_")
                    plat = parts[2]
                    sub_cat = parts[3]

                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT id, service_name, selling_price_per_100, is_published FROM bot_services WHERE bot_id=? AND platform=? AND sub_category=?", (bot_id, plat, sub_cat))
                    srvs = cur.fetchall()
                    conn.close()

                    m = types.InlineKeyboardMarkup(row_width=1)
                    has_active = False
                    for s in srvs:
                        if s["is_published"] == 1:
                            has_active = True
                            m.add(types.InlineKeyboardButton(f"{s['service_name']} - Rs {s['selling_price_per_100']}/100", callback_data=f"u_choose_srv_{s['id']}"))

                    m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data=f"u_plat_{plat}"))

                    if not has_active:
                        cbot.edit_message_text("No service available right now. Owner has not published this service yet.", cid, call.message.message_id, reply_markup=m)
                    else:
                        cbot.edit_message_text(f"Available {sub_cat} Services:", cid, call.message.message_id, reply_markup=m)

                elif data.startswith("u_choose_srv_"):
                    sid = int(data.replace("u_choose_srv_", ""))
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT service_name, selling_price_per_100, description FROM bot_services WHERE id=?", (sid,))
                    srv = cur.fetchone()
                    conn.close()

                    user_states[f"{bot_id}_{uid}"] = {"step": "wait_order_link", "service_id": sid}
                    txt_details = (
                        f"Service: {srv['service_name']}\n"
                        f"Price: Rs {srv['selling_price_per_100']} per 100\n\n"
                        f"Details: {srv['description']}\n\n"
                        f"Send target post, reel, or profile link:"
                    )
                    cbot.send_message(cid, txt_details)

                elif data.startswith("u_qty_btn_"):
                    parts = data.split("_")
                    qty = int(parts[3])
                    sid = int(parts[4])
                    link = user_states.get(f"{bot_id}_{uid}", {}).get("link", "")
                    
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT service_name, selling_price_per_100, main_api_service_id FROM bot_services WHERE id=?", (sid,))
                    srv = cur.fetchone()
                    cur.execute("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid))
                    bal = cur.fetchone()["balance"]

                    cost = (qty / 100.0) * srv["selling_price_per_100"]
                    if bal < cost:
                        m = types.InlineKeyboardMarkup()
                        m.add(types.InlineKeyboardButton("💳 𝗗𝗲𝗽𝗼𝘀𝗶𝘁 𝗡𝗼𝘄", callback_data="u_dep"))
                        cbot.send_message(cid, f"Low Balance!\nOrder Cost: Rs {cost:.2f}\nWallet: Rs {bal:.2f}\nPlease deposit first.", reply_markup=m)
                        conn.close()
                    else:
                        cur.execute("UPDATE bot_clients SET balance = balance - ? WHERE bot_id=? AND user_id=?", (cost, bot_id, uid))
                        api_order_id = "MANUAL"
                        if MAIN_PANEL_API_KEY and srv["main_api_service_id"]:
                            try:
                                p_data = {"key": MAIN_PANEL_API_KEY, "action": "add", "service": srv["main_api_service_id"], "link": link, "quantity": qty}
                                r = requests.post(MAIN_PANEL_URL, data=p_data, timeout=10).json()
                                if "order" in r:
                                    api_order_id = str(r["order"])
                            except Exception:
                                pass

                        cur.execute("INSERT INTO bot_orders (bot_id, user_id, service_name, link, quantity, charge, api_order_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                    (bot_id, uid, srv["service_name"], link, qty, cost, api_order_id, "Processing"))
                        conn.commit()
                        cur.execute("SELECT log_channel FROM child_bots WHERE bot_id=?", (bot_id,))
                        lch = cur.fetchone()["log_channel"]
                        conn.close()

                        cbot.send_message(cid, f"Order Placed Successfully!\n\nService: {srv['service_name']}\nQty: {qty}\nCost: Rs {cost:.2f}\nStatus: Processing")
                        if lch:
                            try:
                                cbot.send_message(lch, f"[NEW ORDER]\nUser: {uid}\nService: {srv['service_name']}\nQty: {qty}")
                            except Exception:
                                pass

                elif data == "u_hist":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT service_name, quantity, charge, status FROM bot_orders WHERE bot_id=? AND user_id=? ORDER BY id DESC LIMIT 5", (bot_id, uid))
                    orders = cur.fetchall()
                    conn.close()
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main"))
                    txt = "\n\n".join([f"{o['service_name']}\nQty: {o['quantity']} | Cost: Rs {o['charge']:.2f}\nStatus: {o['status']}" for o in orders]) if orders else "No recent orders found."
                    cbot.edit_message_text(f"Order History:\n\n{txt}", cid, call.message.message_id, reply_markup=m)

                elif data == "u_supp":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT support_contact FROM child_bots WHERE bot_id=?", (bot_id,))
                    supp = cur.fetchone()["support_contact"] or "@pranavsmm"
                    conn.close()
                    m = types.InlineKeyboardMarkup(row_width=1)
                    m.add(types.InlineKeyboardButton("💬 Chat with Support", url=f"https://t.me/{supp.replace('@', '')}"), types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main"))
                    cbot.edit_message_text(f"Customer Support:\n\nDirect Contact: {supp}", cid, call.message.message_id, reply_markup=m)

                elif data == "u_cyob":
                    m = types.InlineKeyboardMarkup(row_width=1)
                    m.add(types.InlineKeyboardButton("🚀 Open BotFather", url="https://t.me/BotFather"), types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main"))
                    cyob_box = (
                        "👑 *𝗖𝗥𝗘𝗔𝗧𝗘 𝗬𝗢𝗨𝗥 𝗢𝗪𝗡 𝗕𝗢𝗧* ★ 𝗣𝗥𝗢\n\n"
                        "╭━━━━━━━━━━━━━━━━━━━╮\n"
                        " 𝗦𝗧𝗔𝗥𝗧 𝗬𝗢𝗨𝗥 𝗢𝗪𝗡 𝗕𝗥𝗔𝗡𝗗𝗘𝗗 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗕𝗨𝗦𝗜𝗡𝗘𝗦𝗦 𝗜𝗡 𝗠𝗜𝗡𝗨𝗧𝗘𝗦.\n\n"
                        " 1️⃣ 𝗢𝗣𝗘𝗡 ➔ @BotFather\n"
                        " 2️⃣ 𝗦𝗘𝗡𝗗 /newbot & 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗦𝗧𝗘𝗣𝗦\n"
                        " 3️⃣ 𝗖𝗢𝗣𝗬 𝗧𝗛𝗘 𝗕𝗢𝗧 𝗧𝗢𝗞𝗘𝗡 𝗜𝗧 𝗚𝗜𝗩𝗘𝗦 𝗬𝗢𝗨\n"
                        " 4️⃣ 𝗣𝗔𝗦𝗧𝗘 𝗜𝗧 𝗜𝗡 𝗠𝗔𝗦𝗧𝗘𝗥 𝗕𝗢𝗧\n"
                        " ❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                        " 𝗬𝗢𝗨𝗥 𝗕𝗢𝗧 𝗚𝗢𝗘𝗦 𝗟𝗜𝗩𝗘 𝗜𝗡𝗦𝗧𝗔𝗡𝗧𝗟𝗬 🖤\n"
                        "╰━━━━━━━━━━━━━━━━━━╯"
                    )
                    cbot.edit_message_text(cyob_box, cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")

                # ================= OWNER PANEL SUB-MENUS =================
                elif data.startswith("a_") or data.startswith("adm_"):
                    if uid != owner_id:
                        cbot.answer_callback_query(call.id, "Access Denied", show_alert=True)
                        return

                    if data == "a_back_main":
                        cbot.send_message(cid, "Main Menu:", reply_markup=get_user_main_menu())

                    elif data == "adm_back_panel":
                        admin_text = (
                            "╔════════════════════════════╗\n"
                            "   👑 𝗢𝗪𝗡𝗘𝗥 𝗣𝗔𝗡𝗘𝗟\n"
                            "╚════════════════════════════╝\n\n"
                            f"🤖 @{bot_username}\n\n"
                            "𝗠𝗮𝗻𝗮𝗴𝗲 𝗬𝗼𝘂𝗿 𝗕𝗼𝘁 𝗦𝗲𝘁𝘁𝗶𝗻𝗴𝘀: 𝗦𝗲𝘁 𝗬𝗼𝘂𝗿 𝗢𝘄𝗻 𝗦𝗲𝗿𝘃𝗶𝗰𝗲 𝗣𝗿𝗶𝗰𝗲𝘀, "
                            "𝗖𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗲 𝗬𝗼𝘂𝗿 𝗣𝗮𝘆𝗺𝗲𝗻𝘁 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 𝗔𝗣𝗜, 𝗔𝗻𝗱 𝗠𝗮𝗻𝗮𝗴𝗲 𝗬𝗼𝘂𝗿 𝗨𝘀𝗲𝗿𝘀.\n\n"
                            "☆━─━─━─━─━─━─━─━☆"
                        )
                        cbot.edit_message_text(admin_text, cid, call.message.message_id, reply_markup=get_owner_panel(), parse_mode="Markdown")

                    elif data == "a_services":
                        m = types.InlineKeyboardMarkup(row_width=2)
                        m.add(
                            types.InlineKeyboardButton("📸 Instagram", callback_data="adm_plat_Instagram"),
                            types.InlineKeyboardButton("📘 Facebook", callback_data="adm_plat_Facebook")
                        )
                        m.add(
                            types.InlineKeyboardButton("✈️ Telegram", callback_data="adm_plat_Telegram"),
                            types.InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_back_panel")
                        )
                        cbot.edit_message_text("Select Platform to Manage & Publish Services:", cid, call.message.message_id, reply_markup=m)

                    elif data.startswith("adm_plat_"):
                        plat = data.replace("adm_plat_", "")
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT DISTINCT sub_category FROM bot_services WHERE bot_id=? AND platform=?", (bot_id, plat))
                        subs = cur.fetchall()
                        conn.close()

                        m = types.InlineKeyboardMarkup(row_width=1)
                        for s in subs:
                            m.add(types.InlineKeyboardButton(s["sub_category"], callback_data=f"adm_sub_{plat}_{s['sub_category']}"))
                        m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="a_services"))
                        cbot.edit_message_text(f"Manage {plat} Sub-Categories:", cid, call.message.message_id, reply_markup=m)

                    elif data.startswith("adm_sub_"):
                        parts = data.split("_")
                        plat = parts[2]
                        sub_cat = parts[3]
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT id, service_name, cost_price, selling_price_per_100, is_published FROM bot_services WHERE bot_id=? AND platform=? AND sub_category=?", (bot_id, plat, sub_cat))
                        srvs = cur.fetchall()
                        conn.close()

                        m = types.InlineKeyboardMarkup(row_width=1)
                        for s in srvs:
                            st = "Published" if s["is_published"] == 1 else "Unpublished"
                            m.add(types.InlineKeyboardButton(f"{s['service_name']} (Cost: Rs {s['cost_price']}) [{st}]", callback_data=f"adm_manage_srv_{s['id']}"))
                        m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data=f"adm_plat_{plat}"))
                        cbot.edit_message_text(f"Services under {sub_cat}:", cid, call.message.message_id, reply_markup=m)

                    elif data.startswith("adm_manage_srv_"):
                        sid = int(data.replace("adm_manage_srv_", ""))
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT service_name, cost_price, selling_price_per_100, is_published, description, platform, sub_category FROM bot_services WHERE id=?", (sid,))
                        srv = cur.fetchone()
                        conn.close()

                        m = types.InlineKeyboardMarkup(row_width=1)
                        m.add(types.InlineKeyboardButton("Set Price & Publish", callback_data=f"adm_setprice_{sid}"))
                        m.add(types.InlineKeyboardButton("Back", callback_data=f"adm_sub_{srv['platform']}_{srv['sub_category']}"))

                        st_txt = "Published (Live in Bot)" if srv['is_published'] == 1 else "Unpublished"
                        details_txt = (
                            f"Service: {srv['service_name']}\n"
                            f"Main Panel Cost: Rs {srv['cost_price']} per 100\n"
                            f"Your Selling Price: Rs {srv['selling_price_per_100']} per 100\n"
                            f"Status: {st_txt}\n\n"
                            f"Details: {srv['description']}"
                        )
                        cbot.edit_message_text(details_txt, cid, call.message.message_id, reply_markup=m)

                    elif data.startswith("adm_setprice_"):
                        sid = int(data.replace("adm_setprice_", ""))
                        user_states[f"{bot_id}_{uid}"] = {"step": "wait_set_price", "service_id": sid}
                        cbot.send_message(cid, "How much rupees do you want to sell per 100? (e.g. 3 or 5):")

                    elif data == "a_payment":
                        m = types.InlineKeyboardMarkup(row_width=1)
                        m.add(
                            types.InlineKeyboardButton("FMP (FamPay)", callback_data="adm_pay_fmp"),
                            types.InlineKeyboardButton("Paytm", callback_data="adm_pay_paytm"),
                            types.InlineKeyboardButton("Back to Admin", callback_data="adm_back_panel")
                        )
                        cbot.edit_message_text("Select Payment Gateway to Configure:", cid, call.message.message_id, reply_markup=m)

                    elif data == "adm_pay_fmp":
                        m = types.InlineKeyboardMarkup(row_width=1)
                        m.add(
                            types.InlineKeyboardButton("Create API (Portal)", url="https://fampay-flame.vercel.app/"),
                            types.InlineKeyboardButton("Add API (Endpoint & Key)", callback_data="adm_fmp_add_api"),
                            types.InlineKeyboardButton("Back", callback_data="a_payment")
                        )
                        cbot.edit_message_text(
                            "FamPay (FMP) Gateway Integration:\n\n"
                            "1. Click Create API to setup your FMP merchant portal.\n"
                            "2. Click Add API to paste your live Endpoint URL & API Key here.",
                            cid, call.message.message_id, reply_markup=m
                        )

                    elif data == "adm_fmp_add_api":
                        user_states[f"{bot_id}_{uid}"] = "wait_fmp_endpoint"
                        cbot.send_message(cid, "Send your FamPay API URL Endpoint:")

                    elif data == "adm_pay_paytm":
                        cbot.send_message(cid, "Paytm Integration: Configure Paytm merchant inside FMP portal to get unified API key.")

                    elif data == "a_logchan":
                        m = types.InlineKeyboardMarkup(row_width=1)
                        m.add(
                            types.InlineKeyboardButton("Add Log Channel", callback_data="adm_add_logchan"),
                            types.InlineKeyboardButton("Verify Admin", callback_data="adm_verify_logchan"),
                            types.InlineKeyboardButton("Back to Admin", callback_data="adm_back_panel")
                        )
                        cbot.edit_message_text("Log Channel Settings:\nEvery order and deposit will be logged here.", cid, call.message.message_id, reply_markup=m)

                    elif data == "adm_add_logchan":
                        user_states[f"{bot_id}_{uid}"] = "wait_logchan_user"
                        cbot.send_message(cid, "Send your channel username (e.g. @MyLogChannel):")

                    elif data == "adm_verify_logchan":
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT log_channel FROM child_bots WHERE bot_id=?", (bot_id,))
                        ch = cur.fetchone()["log_channel"]
                        conn.close()
                        if not ch:
                            cbot.send_message(cid, "Please add a log channel username first!")
                        else:
                            try:
                                res = cbot.get_chat_member(ch, cbot.get_me().id)
                                if res.status in ['administrator', 'creator']:
                                    cbot.send_message(cid, f"Log Channel Connected! Bot is Verified Admin in {ch}")
                                else:
                                    cbot.send_message(cid, f"Verification Failed: Make sure @{bot_username} is an Admin in {ch}")
                            except Exception as e:
                                cbot.send_message(cid, f"Verification Failed: {e}")

                    elif data == "a_forcesub":
                        user_states[f"{bot_id}_{uid}"] = "wait_force_sub"
                        cbot.send_message(cid, "Send Force Sub Channel username (e.g. @MyChannel):")

                    elif data == "a_users":
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT COUNT(*) as total FROM bot_clients WHERE bot_id=?", (bot_id,))
                        t = cur.fetchone()["total"]
                        conn.close()
                        cbot.send_message(cid, f"Total Registered Users in Bot: {t}", reply_markup=get_owner_panel())

                    elif data == "a_bcast":
                        user_states[f"{bot_id}_{uid}"] = "wait_bcast_msg"
                        cbot.send_message(cid, "Send broadcast announcement text:")

                    elif data == "a_addbal":
                        user_states[f"{bot_id}_{uid}"] = "wait_add_bal"
                        cbot.send_message(cid, "Format: User_ID Amount\nExample: 8585055903 50")

                    elif data == "a_dedbal":
                        user_states[f"{bot_id}_{uid}"] = "wait_ded_bal"
                        cbot.send_message(cid, "Format: User_ID Amount\nExample: 8585055903 20")

                    elif data == "a_ban":
                        user_states[f"{bot_id}_{uid}"] = "wait_ban_user"
                        cbot.send_message(cid, "Send User_ID to ban:")

                    elif data == "a_unban":
                        user_states[f"{bot_id}_{uid}"] = "wait_unban_user"
                        cbot.send_message(cid, "Send User_ID to unban:")

                    elif data == "a_suppcontact":
                        user_states[f"{bot_id}_{uid}"] = "wait_supp_contact"
                        cbot.send_message(cid, "Send your support contact username (e.g. @pranavsmm):")

                    elif data == "a_promode":
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT pro_mode FROM child_bots WHERE bot_id=?", (bot_id,))
                        curr = cur.fetchone()["pro_mode"]
                        new_m = 0 if curr == 1 else 1
                        cur.execute("UPDATE child_bots SET pro_mode=? WHERE bot_id=?", (new_m, bot_id))
                        conn.commit()
                        conn.close()
                        cbot.send_message(cid, f"Pro Mode: {'Turned ON' if new_m == 1 else 'Turned OFF'}", reply_markup=get_owner_panel())

            # Text Inputs Handler
            @cbot.message_handler(func=lambda m: f"{bot_id}_{m.from_user.id}" in user_states and not m.text.startswith('/'))
            def c_text_inputs(m):
                uid = m.from_user.id
                cid = m.chat.id
                key = f"{bot_id}_{uid}"
                state_data = user_states.pop(key, None)
                txt = m.text.strip()

                if state_data == "wait_user_dep_amt":
                    try:
                        amt = float(txt)
                        tx_code = f"DEP{int(time.time())}{random.randint(100, 999)}"
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT fampay_endpoint, fampay_apikey FROM child_bots WHERE bot_id=?", (bot_id,))
                        bset = cur.fetchone()
                        cur.execute("INSERT INTO transactions (tx_id, bot_id, user_id, amount, status) VALUES (?, ?, ?, ?, ?)",
                                    (tx_code, bot_id, uid, amt, "pending"))
                        conn.commit()
                        conn.close()

                        ep = bset["fampay_endpoint"]
                        akey = bset["fampay_apikey"]
                        qr_url = ""

                        if ep and akey:
                            try:
                                post_body = {"api_key": akey, "amount": amt, "order_id": tx_code}
                                r = requests.post(ep, json=post_body, timeout=10).json()
                                qr_url = r.get("qr_url") or r.get("qr_image") or r.get("qr")
                            except Exception:
                                pass

                        if not qr_url:
                            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa=fam@upi&am={amt}&tr={tx_code}"

                        cbot.send_photo(
                            cid,
                            qr_url,
                            caption=f"FamPay Automated Deposit\n\nAmount: Rs {amt:.2f}\nRef: {tx_code}\n\nScan QR and pay. Payment auto-verifies within seconds without pressing any button!"
                        )
                    except Exception:
                        cbot.send_message(cid, "Invalid amount!")

                elif isinstance(state_data, dict) and state_data.get("step") == "wait_order_link":
                    sid = state_data["service_id"]
                    user_states[key] = {"link": txt, "service_id": sid}
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(
                        types.InlineKeyboardButton("100", callback_data=f"u_qty_btn_100_{sid}"),
                        types.InlineKeyboardButton("200", callback_data=f"u_qty_btn_200_{sid}")
                    )
                    m.add(
                        types.InlineKeyboardButton("400", callback_data=f"u_qty_btn_400_{sid}"),
                        types.InlineKeyboardButton("1000", callback_data=f"u_qty_btn_1000_{sid}")
                    )
                    cbot.send_message(cid, f"Link received: {txt}\n\nSelect quantity below:", reply_markup=m)

                elif isinstance(state_data, dict) and state_data.get("step") == "wait_set_price":
                    try:
                        pr = float(txt)
                        sid = state_data["service_id"]
                        user_states[key] = {"step": "wait_service_desc", "service_id": sid, "price": pr}
                        cbot.send_message(cid, "Send your own service details/description (or send 'same' to keep default):")
                    except Exception:
                        cbot.send_message(cid, "Invalid price number!")

                elif isinstance(state_data, dict) and state_data.get("step") == "wait_service_desc":
                    sid = state_data["service_id"]
                    pr = state_data["price"]
                    desc = "Good Quality Speed Fast" if txt.lower() == "same" else txt

                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE bot_services SET selling_price_per_100=?, description=?, is_published=1 WHERE id=?", (pr, desc, sid))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, f"Service published successfully with price Rs {pr} per 100!", reply_markup=get_owner_panel())

                elif state_data == "wait_fmp_endpoint":
                    user_states[key] = {"step": "wait_fmp_key", "endpoint": txt}
                    cbot.send_message(cid, "Now send your FamPay API Key:")

                elif isinstance(state_data, dict) and state_data.get("step") == "wait_fmp_key":
                    ep = state_data["endpoint"]
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE child_bots SET fampay_endpoint=?, fampay_apikey=? WHERE bot_id=?", (ep, txt, bot_id))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, "FamPay API Endpoint & Key connected successfully!", reply_markup=get_owner_panel())

                elif state_data == "wait_logchan_user":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE child_bots SET log_channel=? WHERE bot_id=?", (txt, bot_id))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, f"Log channel set to {txt}. Click 'Verify Admin' in Log Channel settings to complete verification.", reply_markup=get_owner_panel())

                elif state_data == "wait_force_sub":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE child_bots SET force_channel=? WHERE bot_id=?", (txt, bot_id))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, f"Force Sub Channel set to {txt}", reply_markup=get_owner_panel())

                elif state_data == "wait_add_bal":
                    parts = txt.split()
                    if len(parts) >= 2:
                        target_uid, amt = int(parts[0]), float(parts[1])
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("UPDATE bot_clients SET balance = balance + ? WHERE bot_id=? AND user_id=?", (amt, bot_id, target_uid))
                        conn.commit()
                        conn.close()
                        cbot.send_message(cid, f"Added Rs {amt} to User {target_uid}", reply_markup=get_owner_panel())

                elif state_data == "wait_ded_bal":
                    parts = txt.split()
                    if len(parts) >= 2:
                        target_uid, amt = int(parts[0]), float(parts[1])
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("UPDATE bot_clients SET balance = MAX(0.0, balance - ?) WHERE bot_id=? AND user_id=?", (amt, bot_id, target_uid))
                        conn.commit()
                        conn.close()
                        cbot.send_message(cid, f"Deducted Rs {amt} from User {target_uid}", reply_markup=get_owner_panel())

                elif state_data == "wait_ban_user":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE bot_clients SET banned=1 WHERE bot_id=? AND user_id=?", (int(txt), bot_id))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, f"Banned User {txt}", reply_markup=get_owner_panel())

                elif state_data == "wait_unban_user":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE bot_clients SET banned=0 WHERE bot_id=? AND user_id=?", (int(txt), bot_id))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, f"Unbanned User {txt}", reply_markup=get_owner_panel())

                elif state_data == "wait_supp_contact":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE child_bots SET support_contact=? WHERE bot_id=?", (txt, bot_id))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, f"Support contact set to {txt}", reply_markup=get_owner_panel())

                elif state_data == "wait_bcast_msg":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT user_id FROM bot_clients WHERE bot_id=?", (bot_id,))
                    users = cur.fetchall()
                    conn.close()
                    s_count = 0
                    for u in users:
                        try:
                            cbot.send_message(u["user_id"], f"Announcement:\n\n{txt}")
                            s_count += 1
                        except Exception:
                            pass
                    cbot.send_message(cid, f"Broadcast sent to {s_count} users.", reply_markup=get_owner_panel())

            print(f"[CHILD BOT ONLINE] @{bot_username}")
            cbot.infinity_polling(timeout=15, long_polling_timeout=10, skip_pending=True)
        except Exception as e:
            print(f"[CHILD BOT RESTARTING] @{bot_username} Error: {e}")
            time.sleep(3)

def run_master_bot_loop():
    global master_is_running
    while True:
        try:
            if not MASTER_BOT_TOKEN:
                time.sleep(5)
                continue

            master_bot = telebot.TeleBot(MASTER_BOT_TOKEN, threaded=True)
            try:
                requests.get(f"https://api.telegram.org/bot{MASTER_BOT_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)
            except Exception:
                pass

            @master_bot.message_handler(commands=['start'])
            def m_start(msg):
                m = types.InlineKeyboardMarkup(row_width=1)
                m.add(
                    types.InlineKeyboardButton("👑 𝗖𝗥𝗘𝗔𝗧𝗘 𝗬𝗢𝗨𝗥 𝗢𝗪𝗡 𝗕𝗢𝗧 (CYOB)", callback_data="m_cyob"),
                    types.InlineKeyboardButton("📂 𝗠𝘆 𝗖𝗿𝗲𝗮𝘁𝗲𝗱 𝗕𝗼𝘁𝘀", callback_data="m_mybots")
                )
                master_bot.send_message(
                    msg.chat.id,
                    "👑 *WELCOME TO PRANAV FATHER BOT ENGINE* 👑\n\n"
                    "Start Your Own Automated Telegram Reseller Bot in seconds!\n\n"
                    "Click CYOB to launch your bot:",
                    reply_markup=m,
                    parse_mode="Markdown"
                )

            @master_bot.callback_query_handler(func=lambda c: c.data.startswith("m_"))
            def m_calls(c):
                uid = c.from_user.id
                cid = c.message.chat.id
                if c.data == "m_cyob":
                    user_states[uid] = "wait_master_token"
                    master_bot.send_message(
                        cid,
                        "🤖 *Create Your Own Bot (CYOB)*\n\n"
                        "1. Open @BotFather\n"
                        "2. Send /newbot and create your bot\n"
                        "3. Copy HTTP API Token and send it here in chat:",
                        parse_mode="Markdown"
                    )
                elif c.data == "m_mybots":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT bot_username, bot_name FROM child_bots WHERE owner_id=?", (uid,))
                    bots = cur.fetchall()
                    conn.close()
                    if bots:
                        txt = "\n".join([f"• *{b['bot_name']}* (@{b['bot_username']})" for b in bots])
                        master_bot.send_message(cid, f"📂 *Your Bots:*\n\n{txt}\n\nSend /admin inside your bot to open settings.", parse_mode="Markdown")
                    else:
                        master_bot.send_message(cid, "❌ No active bots found. Click CYOB to create one!")

            @master_bot.message_handler(func=lambda m: m.from_user.id in user_states and not m.text.startswith('/'))
            def m_token_receiver(msg):
                uid = msg.from_user.id
                cid = msg.chat.id
                state = user_states.pop(uid, None)
                token = msg.text.strip()

                if state == "wait_master_token":
                    chk = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
                    data = chk.json()
                    if not data.get("ok"):
                        master_bot.send_message(cid, "❌ Invalid Bot Token! Please provide a valid token from BotFather.")
                        return

                    bot_user = data["result"]["username"]
                    bot_name = data["result"]["first_name"]
                    token_enc = cipher_suite.encrypt(token.encode()).decode()

                    conn = get_db()
                    cur = conn.cursor()
                    try:
                        cur.execute("INSERT INTO child_bots (owner_id, bot_token_enc, bot_username, bot_name, support_contact) VALUES (?, ?, ?, ?, ?)",
                                    (uid, token_enc, bot_user, bot_name, "@pranavsmm"))
                        conn.commit()
                        bot_id = cur.lastrowid
                    except sqlite3.IntegrityError:
                        master_bot.send_message(cid, "⚠️ This bot token is already registered in the system!")
                        conn.close()
                        return
                    conn.close()

                    t = threading.Thread(target=run_child_bot_loop, args=(bot_id, uid, token, bot_user, bot_name), daemon=True)
                    t.start()
                    bot_threads[token] = t

                    master_bot.send_message(
                        cid,
                        f"🎉 *Your Bot is Live Now!*\n\n"
                        f"🤖 Bot: @{bot_user}\n"
                        f"👑 Owner: `{uid}`\n\n"
                        f"Open @{bot_user} and send **/admin** to publish services and set payment!",
                        parse_mode="Markdown"
                    )

            print("[MASTER BOT] Polling started successfully...")
            master_is_running = True
            master_bot.infinity_polling(timeout=15, long_polling_timeout=10, skip_pending=True)
        except Exception as e:
            print(f"[MASTER BOT RESTARTING] Error: {e}")
            master_is_running = False
            time.sleep(3)

def self_ping_keepalive():
    while True:
        try:
            # 1. Local ping
            requests.get(f"http://127.0.0.1:{RENDER_PORT}/", timeout=5)
            # 2. External Render domain ping if configured
            if RENDER_EXTERNAL_URL:
                url = RENDER_EXTERNAL_URL.rstrip('/')
                if not url.startswith("http"):
                    url = f"https://{url}"
                requests.get(url, timeout=10)
        except Exception:
            pass
        time.sleep(150)

def watchdog_and_keepalive():
    time.sleep(5)
    while True:
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT bot_id, owner_id, bot_token_enc, bot_username, bot_name FROM child_bots WHERE status='active'")
            rows = cur.fetchall()
            conn.close()

            for r in rows:
                try:
                    token = cipher_suite.decrypt(r["bot_token_enc"].encode()).decode()
                    if token not in bot_threads or not bot_threads[token].is_alive():
                        print(f"[WATCHDOG] Resurrecting child bot @{r['bot_username']}...")
                        t = threading.Thread(target=run_child_bot_loop, args=(r["bot_id"], r["owner_id"], token, r["bot_username"], r["bot_name"]), daemon=True)
                        t.start()
                        bot_threads[token] = t
                except Exception:
                    pass

        except Exception as e:
            print(f"[WATCHDOG ERROR] {e}")

        time.sleep(30)

threading.Thread(target=run_master_bot_loop, daemon=True).start()
threading.Thread(target=watchdog_and_keepalive, daemon=True).start()
threading.Thread(target=self_ping_keepalive, daemon=True).start()

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "engine": "Pranav Father Dev Master Engine",
        "master_live": master_is_running,
        "child_bots_alive": len([t for t in bot_threads.values() if t.is_alive()])
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
