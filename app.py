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
                tb.send_message(user_id, f"✅ *Payment Success*\n\n💰 Deposited: `₹{credited_amt:.2f}`\n🆔 Ref ID: `{tx_id}`\nWallet balance updated automatically!", parse_mode="Markdown")
                if b_row["log_channel"]:
                    tb.send_message(b_row["log_channel"], f"🔔 *[DEPOSIT SUCCESS]*\nUser: `{user_id}`\nAmount: `₹{credited_amt}`\nRef: `{tx_id}`", parse_mode="Markdown")
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
            requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=True", timeout=5)

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
                    cbot.reply_to(msg, "🚫 *You are banned from using this bot!*", parse_mode="Markdown")
                    conn.close()
                    return

                if not is_user_subscribed(uid):
                    cur.execute("SELECT force_channel FROM child_bots WHERE bot_id=?", (bot_id,))
                    ch = cur.fetchone()["force_channel"]
                    conn.close()
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{ch.replace('@', '')}"))
                    m.add(types.InlineKeyboardButton("✅ Check Joined", callback_data="u_check_joined"))
                    cbot.send_message(msg.chat.id, f"⚠️ *Please join {ch} first to use this bot!*", reply_markup=m, parse_mode="Markdown")
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
                    cbot.reply_to(msg, "⛔ *Access Denied: You are not the owner of this bot.*", parse_mode="Markdown")
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
                        cbot.send_message(cid, "✅ *Channel verified successfully! Send /start*", parse_mode="Markdown")
                    else:
                        cbot.answer_callback_query(call.id, "❌ You have not joined yet!", show_alert=True)
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
                    cbot.edit_message_text(f"💳 *Account Balance:*\n\n• User ID: `{uid}`\n• Wallet: `₹{bal:.2f}`", cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")

                elif data == "u_dep":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT fampay_endpoint, fampay_apikey FROM child_bots WHERE bot_id=?", (bot_id,))
                    b_set = cur.fetchone()
                    conn.close()

                    if not b_set["fampay_endpoint"] or not b_set["fampay_apikey"]:
                        m = types.InlineKeyboardMarkup()
                        m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main"))
                        cbot.edit_message_text("⚠️ *Deposit Unavailable.* Owner has not configured payment gateway yet.", cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")
                        return

                    m = types.InlineKeyboardMarkup(row_width=1)
                    m.add(types.InlineKeyboardButton("⚡ Deposit (FamPay Instant Automated)", callback_data="u_dep_fampay_go"))
                    m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main"))
                    cbot.edit_message_text("💰 *Instant Automated Deposit via FamPay/UPI*\nSelect deposit to continue:", cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")

                elif data == "u_dep_fampay_go":
                    user_states[f"{bot_id}_{uid}"] = "wait_user_dep_amt"
                    cbot.send_message(cid, "💵 *Enter amount you want to deposit (e.g. 10):*", parse_mode="Markdown")

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
                    cbot.edit_message_text("🛒 *Select Platform:*", cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")

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
                    cbot.edit_message_text(f"🔥 *{plat} Categories:*", cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")

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
                            m.add(types.InlineKeyboardButton(f"{s['service_name']} - ₹{s['selling_price_per_100']}/100", callback_data=f"u_choose_srv_{s['id']}"))

                    m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data=f"u_plat_{plat}"))

                    if not has_active:
                        cbot.edit_message_text("⚠️ *No service available right now.* Owner has not published this service yet.", cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")
                    else:
                        cbot.edit_message_text(f"📦 *Available {sub_cat} Services:*", cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")

                elif data.startswith("u_choose_srv_"):
                    sid = int(data.replace("u_choose_srv_", ""))
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM bot_services WHERE id=?", (sid,))
                    srv = cur.fetchone()
                    conn.close()

                    user_states[f"{bot_id}_{uid}"] = {"step": "wait_order_link", "service_id": sid}
                    cbot.send_message(
                        cid,
                        f"✨ *Service:* `{srv['service_name
