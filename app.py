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

# Configuration and Environment Variables
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

# Database Initialization
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
        pro_mode INTEGER DEFAULT 0,
        log_channel TEXT DEFAULT '',
        force_channel TEXT DEFAULT '',
        support_contact TEXT DEFAULT '@pranavsmm',
        fampay_endpoint TEXT DEFAULT '',
        fampay_apikey TEXT DEFAULT '',
        paytm_mid TEXT DEFAULT 'pranavpatel@upi',
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
        category TEXT,
        service_name TEXT,
        main_api_service_id TEXT,
        selling_price_per_100 REAL DEFAULT 3.0,
        description TEXT
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

# Payment Webhook Handler
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
                tb.send_message(user_id, f"Payment Success!\n\nDeposited: Rs {credited_amt:.2f}\nRef ID: {tx_id}\nBalance added to wallet.")
                if b_row["log_channel"]:
                    tb.send_message(b_row["log_channel"], f"[DEPOSIT LOG]\nUser: {user_id}\nAmount: Rs {credited_amt}\nStatus: Auto Verified")
            except Exception:
                pass

        return jsonify({"status": "success"}), 200

    conn.close()
    return jsonify({"status": "already_done"}), 200

# Child Bot Engine
def run_child_bot_loop(bot_id, owner_id, token, bot_username, bot_name):
    while True:
        try:
            cbot = telebot.TeleBot(token, threaded=True)
            requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=True", timeout=5)

            def get_user_main_menu():
                m = types.InlineKeyboardMarkup(row_width=2)
                m.add(
                    types.InlineKeyboardButton("Balance", callback_data="u_bal"),
                    types.InlineKeyboardButton("Deposit", callback_data="u_dep")
                )
                m.add(
                    types.InlineKeyboardButton("History", callback_data="u_hist"),
                    types.InlineKeyboardButton("Order Now", callback_data="u_ord")
                )
                m.add(
                    types.InlineKeyboardButton("Support", callback_data="u_supp"),
                    types.InlineKeyboardButton("CYOB", callback_data="u_cyob")
                )
                return m

            def get_owner_panel():
                m = types.InlineKeyboardMarkup(row_width=2)
                m.add(
                    types.InlineKeyboardButton("Services", callback_data="a_services"),
                    types.InlineKeyboardButton("Payment", callback_data="a_payment")
                )
                m.add(
                    types.InlineKeyboardButton("Users", callback_data="a_users"),
                    types.InlineKeyboardButton("Broadcast", callback_data="a_bcast")
                )
                m.add(
                    types.InlineKeyboardButton("Add Balance", callback_data="a_addbal"),
                    types.InlineKeyboardButton("Deduct Balance", callback_data="a_dedbal")
                )
                m.add(
                    types.InlineKeyboardButton("Ban User", callback_data="a_ban"),
                    types.InlineKeyboardButton("Unban User", callback_data="a_unban")
                )
                m.add(
                    types.InlineKeyboardButton("Log Channel", callback_data="a_logchan"),
                    types.InlineKeyboardButton("Force Sub", callback_data="a_forcesub")
                )
                m.add(
                    types.InlineKeyboardButton("Support Contact", callback_data="a_suppcontact"),
                    types.InlineKeyboardButton("Turn On Pro Mode", callback_data="a_promode")
                )
                m.add(types.InlineKeyboardButton("Main Menu", callback_data="a_back_main"))
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

                welcome_text = (
                    "MAIN MENU ~\n\n"
                    "WELCOME VIP\n"
                    "Choose An Option Below:"
                )
                cbot.send_message(msg.chat.id, welcome_text, reply_markup=get_user_main_menu())

            @cbot.message_handler(commands=['admin'])
            def c_admin(msg):
                if msg.from_user.id != owner_id:
                    cbot.reply_to(msg, "Access Denied: You are not the owner of this bot.")
                    return

                admin_text = (
                    f"OWNER PANEL\n\n"
                    f"Bot: @{bot_username}\n\n"
                    f"Manage Your Bot Settings: Set Your Own Service Prices, "
                    f"Configure Your Payment Gateway API, And Manage Your Users."
                )
                cbot.send_message(msg.chat.id, admin_text, reply_markup=get_owner_panel())

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
                        cbot.answer_callback_query(call.id, "You have not joined the channel yet!", show_alert=True)
                    return

                if data == "u_back_main":
                    cbot.edit_message_text("MAIN MENU ~\n\nChoose an option below:", cid, call.message.message_id, reply_markup=get_user_main_menu())

                elif data == "u_bal":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid))
                    row = cur.fetchone()
                    conn.close()
                    bal = row["balance"] if row else 0.0
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("Deposit", callback_data="u_dep"), types.InlineKeyboardButton("Back", callback_data="u_back_main"))
                    cbot.edit_message_text(f"YOUR WALLET BALANCE\n\nUser ID: {uid}\nBalance: Rs {bal:.2f}", cid, call.message.message_id, reply_markup=m)

                elif data == "u_dep":
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("FamPay Instant", callback_data="sub_dep_fampay"), types.InlineKeyboardButton("Paytm / UPI QR", callback_data="sub_dep_qr"))
                    m.add(types.InlineKeyboardButton("Rules", callback_data="sub_dep_rules"), types.InlineKeyboardButton("Back", callback_data="u_back_main"))
                    cbot.edit_message_text("AUTOMATED DEPOSIT HUB\n\nSelect Payment Method:", cid, call.message.message_id, reply_markup=m)

                elif data == "sub_dep_qr":
                    tx_code = f"DEP{int(time.time())}{random.randint(100, 999)}"
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT paytm_mid FROM child_bots WHERE bot_id=?", (bot_id,))
                    brow = cur.fetchone()
                    cur.execute("INSERT INTO transactions (tx_id, bot_id, user_id, amount, status) VALUES (?, ?, ?, ?, ?)",
                                (tx_code, bot_id, uid, 10.0, "pending"))
                    conn.commit()
                    conn.close()

                    upi_id = brow["paytm_mid"] if (brow and brow["paytm_mid"]) else "pranavpatel@upi"
                    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa={upi_id}&pn={bot_name}&am=10&tr={tx_code}"
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("Back", callback_data="u_dep"))
                    cbot.send_photo(cid, qr_url, caption=f"Instant QR Deposit\n\nUPI: {upi_id}\nRef: {tx_code}\n\nAuto-verification takes 10 seconds after payment.", reply_markup=m)

                elif data == "sub_dep_fampay":
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("Back", callback_data="u_dep"))
                    cbot.edit_message_text("FamPay Instant Gateway\n\nEnter amount in chat (e.g. 10 or 50):", cid, call.message.message_id, reply_markup=m)
                    user_states[f"{bot_id}_{uid}"] = "wait_fampay_amt"

                elif data == "sub_dep_rules":
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("Back", callback_data="u_dep"))
                    cbot.edit_message_text("Payment Rules:\n1. Minimum deposit Rs 10.\n2. Balance adds automatically upon successful payment.", cid, call.message.message_id, reply_markup=m)

                elif data == "u_ord":
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("Instagram", callback_data="cat_instagram"), types.InlineKeyboardButton("YouTube", callback_data="cat_youtube"))
                    m.add(types.InlineKeyboardButton("Telegram", callback_data="cat_telegram"), types.InlineKeyboardButton("Facebook", callback_data="cat_facebook"))
                    m.add(types.InlineKeyboardButton("Back", callback_data="u_back_main"))
                    cbot.edit_message_text("ORDER SERVICES\n\nSelect Platform:", cid, call.message.message_id, reply_markup=m)

                elif data.startswith("cat_"):
                    cat_name = data.replace("cat_", "").capitalize()
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT id, service_name, selling_price_per_100 FROM bot_services WHERE bot_id=? AND category=?", (bot_id, cat_name))
                    srvs = cur.fetchall()
                    conn.close()

                    m = types.InlineKeyboardMarkup(row_width=1)
                    if srvs:
                        for s in srvs:
                            m.add(types.InlineKeyboardButton(f"{s['service_name']} - Rs {s['selling_price_per_100']}/100", callback_data=f"buy_{s['id']}"))
                    m.add(types.InlineKeyboardButton("Back to Categories", callback_data="u_ord"))
                    txt = f"{cat_name} Services:\n\nSelect service:" if srvs else f"No services currently active in {cat_name}."
                    cbot.edit_message_text(txt, cid, call.message.message_id, reply_markup=m)

                elif data.startswith("buy_"):
                    srv_id = data.replace("buy_", "")
                    user_states[f"{bot_id}_{uid}"] = {"step": "wait_link", "service_id": srv_id}
                    cbot.send_message(cid, "Send target post, reel, or profile link:")

                elif data == "u_hist":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT service_name, quantity, charge, status FROM bot_orders WHERE bot_id=? AND user_id=? ORDER BY id DESC LIMIT 5", (bot_id, uid))
                    orders = cur.fetchall()
                    conn.close()
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("Back", callback_data="u_back_main"))
                    txt = "\n\n".join([f"{o['service_name']}\nQty: {o['quantity']} | Cost: Rs {o['charge']:.2f}\nStatus: {o['status']}" for o in orders]) if orders else "No recent orders found."
                    cbot.edit_message_text(f"YOUR RECENT ORDERS\n\n{txt}", cid, call.message.message_id, reply_markup=m)

                elif data == "u_supp":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT support_contact FROM child_bots WHERE bot_id=?", (bot_id,))
                    supp = cur.fetchone()["support_contact"] or "@pranavsmm"
                    conn.close()
                    m = types.InlineKeyboardMarkup(row_width=1)
                    m.add(types.InlineKeyboardButton("Telegram Support", url=f"https://t.me/{supp.replace('@', '')}"), types.InlineKeyboardButton("Back", callback_data="u_back_main"))
                    cbot.edit_message_text(f"CUSTOMER SUPPORT\n\nDirect Contact:\n{supp}", cid, call.message.message_id, reply_markup=m)

                elif data == "u_cyob":
                    m = types.InlineKeyboardMarkup(row_width=1)
                    m.add(types.InlineKeyboardButton("Open BotFather", url="https://t.me/BotFather"), types.InlineKeyboardButton("Back", callback_data="u_back_main"))
                    cyob_text = (
                        "CREATE YOUR OWN BOT PRO\n\n"
                        "1. Open @BotFather\n"
                        "2. Send /newbot and follow instructions\n"
                        "3. Copy HTTP API Token\n"
                        "4. Send token to Master Bot\n\n"
                        "Your Bot goes live instantly!"
                    )
                    cbot.edit_message_text(cyob_text, cid, call.message.message_id, reply_markup=m)

                elif data.startswith("a_") or data.startswith("sub_"):
                    if uid != owner_id:
                        cbot.answer_callback_query(call.id, "Access Denied", show_alert=True)
                        return

                    if data == "a_back_main":
                        cbot.send_message(cid, "Main Menu:", reply_markup=get_user_main_menu())
                    elif data == "sub_back_adm":
                        cbot.edit_message_text("Owner Panel:", cid, call.message.message_id, reply_markup=get_owner_panel())
                    elif data == "a_services":
                        m = types.InlineKeyboardMarkup(row_width=2)
                        m.add(types.InlineKeyboardButton("Add Service", callback_data="sub_add_srv"), types.InlineKeyboardButton("List Services", callback_data="sub_list_srv"))
                        m.add(types.InlineKeyboardButton("Back to Admin", callback_data="sub_back_adm"))
                        cbot.edit_message_text("SERVICES MANAGER", cid, call.message.message_id, reply_markup=m)
                    elif data == "sub_add_srv":
                        user_states[f"{bot_id}_{uid}"] = "wait_srv_details"
                        cbot.send_message(cid, "Send details in format:\nCategory | Service Name | Selling Price (per 100) | Main API Service ID\n\nExample:\nInstagram | IG Likes India | 3.0 | 1024")
                    elif data == "sub_list_srv":
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT id, category, service_name, selling_price_per_100 FROM bot_services WHERE bot_id=?", (bot_id,))
                        rows = cur.fetchall()
                        conn.close()
                        txt = "\n".join([f"ID {r['id']}: [{r['category']}] {r['service_name']} (Rs {r['selling_price_per_100']}/100)" for r in rows]) if rows else "No services added."
                        cbot.send_message(cid, f"Active Services:\n\n{txt}", reply_markup=get_owner_panel())
                    elif data == "a_payment":
                        m = types.InlineKeyboardMarkup(row_width=1)
                        m.add(types.InlineKeyboardButton("Set UPI ID", callback_data="sub_set_upi"), types.InlineKeyboardButton("Connect FamPay API", callback_data="sub_set_fampay"), types.InlineKeyboardButton("Back to Admin", callback_data="sub_back_adm"))
                        cbot.edit_message_text("PAYMENT GATEWAY CONFIG", cid, call.message.message_id, reply_markup=m)
                    elif data == "sub_set_upi":
                        user_states[f"{bot_id}_{uid}"] = "wait_upi_id"
                        cbot.send_message(cid, "Send new UPI ID (e.g. pranavpatel@upi):")
                    elif data == "sub_set_fampay":
                        user_states[f"{bot_id}_{uid}"] = "wait_fampay_creds"
                        cbot.send_message(cid, "Send FamPay credentials:\nEndpoint | API_Key")
                    elif data == "a_users":
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT COUNT(*) as total FROM bot_clients WHERE bot_id=?", (bot_id,))
                        t = cur.fetchone()["total"]
                        conn.close()
                        cbot.send_message(cid, f"Total Registered Users: {t}", reply_markup=get_owner_panel())
                    elif data == "a_bcast":
                        user_states[f"{bot_id}_{uid}"] = "wait_bcast_msg"
                        cbot.send_message(cid, "Send broadcast message text:")
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
                    elif data == "a_logchan":
                        user_states[f"{bot_id}_{uid}"] = "wait_log_chan"
                        cbot.send_message(cid, "Send channel username for logs (e.g. @MyLogChannel):")
                    elif data == "a_forcesub":
                        user_states[f"{bot_id}_{uid}"] = "wait_force_sub"
                        cbot.send_message(cid, "Send channel username for Force Sub (e.g. @MyChannel):")
                    elif data == "a_suppcontact":
                        user_states[f"{bot_id}_{uid}"] = "wait_supp_contact"
                        cbot.send_message(cid, "Send support contact username:")
                    elif data == "a_promode":
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT pro_mode FROM child_bots WHERE bot_id=?", (bot_id,))
                        curr = cur.fetchone()["pro_mode"]
                        new_m = 0 if curr == 1 else 1
                        cur.execute("UPDATE child_bots SET pro_mode=? WHERE bot_id=?", (new_m, bot_id))
                        conn.commit()
                        conn.close()
                        cbot.send_message(cid, f"Pro Mode toggled: {new_m}", reply_markup=get_owner_panel())

            @cbot.message_handler(func=lambda m: f"{bot_id}_{m.from_user.id}" in user_states and not m.text.startswith('/'))
            def c_text_inputs(m):
                uid = m.from_user.id
                cid = m.chat.id
                key = f"{bot_id}_{uid}"
                state_data = user_states.pop(key, None)
                txt = m.text.strip()

                if isinstance(state_data, dict) and state_data.get("step") == "wait_link":
                    srv_id = state_data["service_id"]
                    user_states[key] = {"step": "wait_qty", "service_id": srv_id, "link": txt}
                    cbot.send_message(cid, f"Link received: {txt}\n\nEnter Quantity (e.g. 100 or 500):")

                elif isinstance(state_data, dict) and state_data.get("step") == "wait_qty":
                    if not txt.isdigit():
                        cbot.send_message(cid, "Error: Please send numbers only.")
                        return
                    qty = int(txt)
                    srv_id = state_data["service_id"]
                    link = state_data["link"]

                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT service_name, selling_price_per_100, main_api_service_id FROM bot_services WHERE id=?", (srv_id,))
                    srv = cur.fetchone()
                    cur.execute("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid))
                    bal = cur.fetchone()["balance"]

                    cost = (qty / 100.0) * srv["selling_price_per_100"]
                    if bal < cost:
                        cbot.send_message(cid, f"Insufficient Balance!\nCost: Rs {cost:.2f}\nYour Balance: Rs {bal:.2f}\nPlease deposit first.")
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
                        l_chan = cur.fetchone()["log_channel"]
                        conn.close()

                        cbot.send_message(cid, f"Order Placed Successfully!\n\nService: {srv['service_name']}\nQuantity: {qty}\nCost: Rs {cost:.2f}\nRemaining: Rs {bal - cost:.2f}")
                        if l_chan:
                            try:
                                cbot.send_message(l_chan, f"[NEW ORDER]\nUser: {uid}\nService: {srv['service_name']}\nQty: {qty}")
                            except Exception:
                                pass

                elif state_data == "wait_srv_details":
                    parts = [p.strip() for p in txt.split("|")]
                    if len(parts) >= 3:
                        cat = parts[0].capitalize()
                        s_name = parts[1]
                        price = float(parts[2])
                        api_sid = parts[3] if len(parts) > 3 else ""
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("INSERT INTO bot_services (bot_id, category, service_name, selling_price_per_100, main_api_service_id) VALUES (?, ?, ?, ?, ?)",
                            (bot_id, cat, s_name, price, api_sid))
                        conn.commit()
                        conn.close()
                        cbot.send_message(cid, f"Service {s_name} published successfully!", reply_markup=get_owner_panel())

                elif state_data == "wait_upi_id":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE child_bots SET paytm_mid=? WHERE bot_id=?", (txt, bot_id))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, f"UPI ID set: {txt}", reply_markup=get_owner_panel())

                elif state_data == "wait_fampay_creds":
                    parts = [p.strip() for p in txt.split("|")]
                    if len(parts) >= 2:
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("UPDATE child_bots SET fampay_endpoint=?, fampay_apikey=? WHERE bot_id=?", (parts[0], parts[1], bot_id))
                        conn.commit()
                        conn.close()
                        cbot.send_message(cid, "FamPay API Connected!", reply_markup=get_owner_panel())

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

                elif state_data == "wait_log_chan":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE child_bots SET log_channel=? WHERE bot_id=?", (txt, bot_id))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, f"Log Channel updated: {txt}", reply_markup=get_owner_panel())

                elif state_data == "wait_force_sub":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE child_bots SET force_channel=? WHERE bot_id=?", (txt, bot_id))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, f"Force Sub Channel updated: {txt}", reply_markup=get_owner_panel())

                elif state_data == "wait_supp_contact":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE child_bots SET support_contact=? WHERE bot_id=?", (txt, bot_id))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, f"Support Contact set: {txt}", reply_markup=get_owner_panel())

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

# Master Father Bot Engine
def run_master_bot_loop():
    global master_is_running
    while True:
        try:
            if not MASTER_BOT_TOKEN:
                time.sleep(5)
                continue

            master_bot = telebot.TeleBot(MASTER_BOT_TOKEN, threaded=True)
            requests.get(f"https://api.telegram.org/bot{MASTER_BOT_TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=5)

            @master_bot.message_handler(commands=['start'])
            def m_start(msg):
                m = types.InlineKeyboardMarkup(row_width=1)
                m.add(
                    types.InlineKeyboardButton("CREATE YOUR OWN BOT (CYOB)", callback_data="m_cyob"),
                    types.InlineKeyboardButton("My Created Bots", callback_data="m_mybots")
                )
                master_bot.send_message(
                    msg.chat.id,
                    "WELCOME TO PRANAV FATHER BOT ENGINE\n\n"
                    "Start Your Own Automated Telegram Reseller Bot in seconds!\n\n"
                    "Click CYOB to launch your bot:",
                    reply_markup=m
                )

            @master_bot.callback_query_handler(func=lambda c: c.data.startswith("m_"))
            def m_calls(c):
                uid = c.from_user.id
                cid = c.message.chat.id
                if c.data == "m_cyob":
                    user_states[uid] = "wait_master_token"
                    master_bot.send_message(
                        cid,
                        "Create Your Own Bot (CYOB)\n\n"
                        "1. Open @BotFather\n"
                        "2. Send /newbot and create a bot\n"
                        "3. Copy HTTP API Token and send it here in chat:"
                    )
                elif c.data == "m_mybots":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT bot_username, bot_name FROM child_bots WHERE owner_id=?", (uid,))
                    bots = cur.fetchall()
                    conn.close()
                    if bots:
                        txt = "\n".join([f"- {b['bot_name']} (@{b['bot_username']})" for b in bots])
                        master_bot.send_message(cid, f"Your Bots:\n\n{txt}\n\nSend /admin inside your bot to open settings.")
                    else:
                        master_bot.send_message(cid, "No active bots found. Click CYOB to create one!")

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
                        master_bot.send_message(cid, "Invalid Bot Token! Please provide a valid token from BotFather.")
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
                        master_bot.send_message(cid, "This bot token is already registered in the system!")
                        conn.close()
                        return
                    conn.close()

                    t = threading.Thread(target=run_child_bot_loop, args=(bot_id, uid, token, bot_user, bot_name), daemon=True)
                    t.start()
                    bot_threads[token] = t

                    master_bot.send_message(
                        cid,
                        f"Your Bot is Live Now!\n\n"
                        f"Bot: @{bot_user}\n"
                        f"Owner: {uid}\n\n"
                        f"Open @{bot_user} and send /admin to configure services and payment!"
                    )

            print("[MASTER BOT] Polling started successfully...")
            master_is_running = True
            master_bot.infinity_polling(timeout=15, long_polling_timeout=10, skip_pending=True)
        except Exception as e:
            print(f"[MASTER BOT RESTARTING] Error: {e}")
            master_is_running = False
            time.sleep(3)

# 30-Second Self-Healing Watchdog
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

            try:
                requests.get(f"http://127.0.0.1:{RENDER_PORT}/", timeout=5)
            except Exception:
                pass

        except Exception as e:
            print(f"[WATCHDOG ERROR] {e}")

        time.sleep(30)

# Entry Point Threads
threading.Thread(target=run_master_bot_loop, daemon=True).start()
threading.Thread(target=watchdog_and_keepalive, daemon=True).start()

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
