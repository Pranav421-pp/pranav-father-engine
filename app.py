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
keypad_amounts = {}
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
        fampay_endpoint TEXT DEFAULT 'https://fampay-flame.vercel.app/api/pay',
        fampay_apikey TEXT DEFAULT '',
        paytm_active INTEGER DEFAULT 1,
        fampay_active INTEGER DEFAULT 1,
        bharatpe_active INTEGER DEFAULT 0,
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
        total_deposit REAL DEFAULT 0.0,
        total_spent REAL DEFAULT 0.0,
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
        min_qty INTEGER DEFAULT 100,
        max_qty INTEGER DEFAULT 1000000,
        main_api_service_id TEXT DEFAULT '100',
        description TEXT DEFAULT 'QUALITY - GOOD QUALITY\nSPEED - FAST INSTANT\nDATA - PROFILE + 2 POST\nDROP - HIGH DROP POSSIBLE\nREFILL - NO REFILL',
        is_published INTEGER DEFAULT 1
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
        status TEXT DEFAULT 'Pending',
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
            ("Instagram", "Ig Likes", "Ig Likes ❤️", 1.0, 3.0, 100, 3949494, "101", "QUALITY - GOOD QUALITY\nSPEED - FAST INSTANT\nDROP - ALMOST NON DROP\nREFILL - 365 DAY REFILL"),
            ("Instagram", "Ig Followers", "Cheap Followers", 4.5, 8.0, 100, 1000000, "102", "QUALITY - GOOD QUALITY\nSPEED - FAST INSTANT\nDATA - PROFILE + 2 POST\nDROP - HIGH DROP POSSIBLE\nREFILL - NO REFILL"),
            ("Instagram", "Ig Followers", "Ig Followers HQ", 25.0, 35.0, 100, 500000, "103", "QUALITY - HIGH QUALITY\nSPEED - SUPERFAST\nREFILL - LIFETIME GUARANTEE"),
            ("Instagram", "Reels View's", "Reel Views Instant", 0.03, 0.5, 100, 10000000, "104", "NON DROP FAST HIGH SPEED INSTANT START"),
            ("Instagram", "Post View's", "Post Impressions & Reach", 0.05, 0.8, 100, 5000000, "105", "INSTANT REAL IMPRESSIONS"),
            ("Facebook", "Fb Followers", "Fb Page Followers", 15.0, 30.0, 100, 200000, "106", "SAFE NON DROP HIGH RETENTION"),
            ("Telegram", "Tg Members", "Telegram Channel Members", 8.0, 15.0, 100, 100000, "107", "REAL ACTIVE 0-1 HOUR START")
        ]
        for d in defaults:
            cur.execute("""
            INSERT INTO bot_services (bot_id, platform, sub_category, service_name, cost_price, selling_price_per_100, min_qty, max_qty, main_api_service_id, description, is_published)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (bot_id, d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8]))
        conn.commit()
    conn.close()

# Keypad Markup Generator for Deposit
def build_deposit_keypad(current_amount_str):
    m = types.InlineKeyboardMarkup(row_width=3)
    display_amt = current_amount_str if current_amount_str else "0"
    m.add(
        types.InlineKeyboardButton("1", callback_data="kp_1"),
        types.InlineKeyboardButton("2", callback_data="kp_2"),
        types.InlineKeyboardButton("3", callback_data="kp_3")
    )
    m.add(
        types.InlineKeyboardButton("4", callback_data="kp_4"),
        types.InlineKeyboardButton("5", callback_data="kp_5"),
        types.InlineKeyboardButton("6", callback_data="kp_6")
    )
    m.add(
        types.InlineKeyboardButton("7", callback_data="kp_7"),
        types.InlineKeyboardButton("8", callback_data="kp_8"),
        types.InlineKeyboardButton("9", callback_data="kp_9")
    )
    m.add(
        types.InlineKeyboardButton("0", callback_data="kp_0"),
        types.InlineKeyboardButton("00", callback_data="kp_00"),
        types.InlineKeyboardButton("🗑️", callback_data="kp_clear")
    )
    m.add(
        types.InlineKeyboardButton("🛑 CANCEL", callback_data="kp_cancel"),
        types.InlineKeyboardButton("✅ CONFIRM", callback_data="kp_confirm")
    )
    return m, display_amt

@app.route('/api/payment/webhook', methods=['POST'])
def payment_webhook():
    data = request.json or request.form.to_dict()
    tx_id = data.get("orderId") or data.get("tx_id") or data.get("utr")
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

        cur.execute("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", 
                    (credited_amt, credited_amt, bot_id, user_id))
        cur.execute("UPDATE transactions SET status='completed' WHERE tx_id=?", (tx_id,))
        conn.commit()

        cur.execute("SELECT bot_token_enc, log_channel FROM child_bots WHERE bot_id=?", (bot_id,))
        b_row = cur.fetchone()
        conn.close()

        if b_row:
            try:
                dec_token = cipher_suite.decrypt(b_row["bot_token_enc"].encode()).decode()
                tb = telebot.TeleBot(dec_token)
                tb.send_message(user_id, f"✅ Payment Success\n\nAmount: Rs {credited_amt:.2f}\nRef/UTR: {tx_id}\nFunds added to wallet.")
                if b_row["log_channel"]:
                    tb.send_message(b_row["log_channel"], f"🔔 [DEPOSIT SUCCESS]\nUser: {user_id}\nAmount: Rs {credited_amt}\nRef: {tx_id}")
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
                    types.InlineKeyboardButton("💳 Balance", callback_data="u_bal"),
                    types.InlineKeyboardButton("💰 Deposit", callback_data="u_dep")
                )
                m.add(
                    types.InlineKeyboardButton("🗓️ History", callback_data="u_hist"),
                    types.InlineKeyboardButton("🛒 Order Now", callback_data="u_ord")
                )
                m.add(
                    types.InlineKeyboardButton("💬 Support", callback_data="u_supp"),
                    types.InlineKeyboardButton("👑 CYOB", callback_data="u_cyob")
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

                cur.execute("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)",
                            (bot_id, uid, msg.from_user.username or 'User'))
                conn.commit()
                conn.close()

                welcome_screen = (
                    "╔═══════════════════════════╗\n"
                    "   ✨ 𝓦𝓔𝓛𝓒𝓞𝓜𝓔 ✨\n"
                    "╚═══════════════════════════╝\n\n"
                    f"❣️ Hey @{msg.from_user.username or 'User'} ❄️\n\n"
                    "Boost Your Social Presence With Instant Delivery And Automated 24/7 Processing. 🚀\n"
                    "❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                    "We Have Clone Reseller Program For Business Men & Developers 👑\n\n"
                    "Press Continue To Open The Menu"
                )
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("▶️ CONTINUE", callback_data="u_continue_main"))
                cbot.send_message(msg.chat.id, welcome_screen, reply_markup=m)

            @cbot.message_handler(commands=['admin'])
            def c_admin(msg):
                if msg.from_user.id != owner_id:
                    cbot.reply_to(msg, "Access Denied: You are not the owner of this bot.")
                    return
                admin_text = (
                    "👑 Owner Panel\n\n"
                    f"🤖 @{bot_username}\n\n"
                    "Manage Your Bot Settings: Set Your Own Service Prices, Configure Your Payment Gateway API, And Manage Your Users.\n\n"
                    "☆━─━─━─━─━─━─━─━☆"
                )
                cbot.send_message(msg.chat.id, admin_text, reply_markup=get_owner_panel())

            @cbot.callback_query_handler(func=lambda c: True)
            def c_callbacks(call):
                uid = call.from_user.id
                cid = call.message.chat.id
                mid = call.message.message_id
                data = call.data

                if data == "u_continue_main" or data == "u_back_main":
                    menu_text = (
                        "💎 MAIN MENU 💎 ~\n\n"
                        "╔══════════════════════╗\n"
                        "  ✨ 𝓦𝓔𝓛𝓒𝓞𝓜𝓔 ★ VIP ✨\n"
                        "  ❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                        "  🥶 Choose An Option Below 🎀\n"
                        "╚══════════════════════╝"
                    )
                    cbot.edit_message_text(menu_text, cid, mid, reply_markup=get_user_main_menu())

                elif data == "u_bal":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT balance, total_deposit, total_spent FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid))
                    row = cur.fetchone()
                    conn.close()
                    bal = row["balance"] if row else 0.0
                    tdep = row["total_deposit"] if row else 0.0
                    tsp = row["total_spent"] if row else 0.0

                    acc_text = (
                        "🛡️ ACCOUNT INFO  PREMIUM\n\n"
                        f"💰 Balance - ₹{bal:.2f}\n"
                        f"🆔 User ID - {uid}\n"
                        f"👤 User Name - @{call.from_user.username or 'User'}\n"
                        f"💳 Total Deposit - ₹{tdep:.2f}\n"
                        f"🛒 Total Spent - ₹{tsp:.2f}\n\n"
                        "Funds Are Stored Securely And Ready For Automated Orders."
                    )
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("💰 Deposit", callback_data="u_dep"), types.InlineKeyboardButton("🔙 Go Back", callback_data="u_back_main"))
                    cbot.edit_message_text(acc_text, cid, mid, reply_markup=m)

                elif data == "u_dep":
                    dep_screen = (
                        "╭──────────────────────────╮\n"
                        "  💷 DEPOSIT FUNDS\n"
                        "╰──────────────────────────╯\n\n"
                        "Select A Method To Continue"
                    )
                    m = types.InlineKeyboardMarkup(row_width=1)
                    m.add(types.InlineKeyboardButton("UPI", callback_data="u_dep_method_upi"))
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_back_main"))
                    cbot.edit_message_text(dep_screen, cid, mid, reply_markup=m)

                elif data == "u_dep_method_upi":
                    keypad_amounts[uid] = ""
                    kp, disp = build_deposit_keypad("")
                    kp_screen = (
                        "╭──────────────────────────╮\n"
                        "  💶 DEPOSIT 💷\n"
                        "╰──────────────────────────╯\n"
                        "  Enter The Amount Below\n\n"
                        "😊 Minimum ₹1 Max ₹10,000\n\n"
                        f"💵 Amount : ₹{disp}"
                    )
                    cbot.edit_message_text(kp_screen, cid, mid, reply_markup=kp)

                elif data.startswith("kp_"):
                    act = data.replace("kp_", "")
                    cur_amt = keypad_amounts.get(uid, "")
                    if act == "cancel":
                        keypad_amounts.pop(uid, None)
                        cbot.edit_message_text("Deposit Cancelled.", cid, mid, reply_markup=get_user_main_menu())
                        return
                    elif act == "clear":
                        cur_amt = cur_amt[:-1] if len(cur_amt) > 1 else ""
                    elif act in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "00"]:
                        if len(cur_amt) < 5:
                            cur_amt += act
                    elif act == "confirm":
                        if not cur_amt or int(cur_amt) < 1:
                            cbot.answer_callback_query(call.id, "Please enter at least ₹1", show_alert=True)
                            return
                        amt = float(cur_amt)
                        keypad_amounts.pop(uid, None)

                        utr_num = f"388{random.randint(100000000, 999999999)}"
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT fampay_endpoint, fampay_apikey FROM child_bots WHERE bot_id=?", (bot_id,))
                        bset = cur.fetchone()
                        cur.execute("INSERT INTO transactions (tx_id, bot_id, user_id, amount, status) VALUES (?, ?, ?, ?, ?)",
                                    (utr_num, bot_id, uid, amt, "pending"))
                        conn.commit()
                        conn.close()

                        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa=fam@upi&am={amt}&tr={utr_num}"
                        qr_cap = (
                            "╭──────────────────────────╮\n"
                            "  SCAN & PAY\n"
                            "╰──────────────────────────╯\n\n"
                            f"💵 Amount : ₹{amt:.0f}\n"
                            f"🆔 Utr : {utr_num}\n"
                            "⏱️ Valid : 15 Min"
                        )
                        m = types.InlineKeyboardMarkup(row_width=1)
                        m.add(types.InlineKeyboardButton("✅ VERIFY PAYMENT", callback_data=f"chk_pay_{utr_num}"))
                        m.add(types.InlineKeyboardButton("❌ CANCEL", callback_data=f"cnl_pay_{utr_num}"))
                        cbot.delete_message(cid, mid)
                        cbot.send_photo(cid, qr_url, caption=qr_cap, reply_markup=m)
                        return

                    keypad_amounts[uid] = cur_amt
                    kp, disp = build_deposit_keypad(cur_amt)
                    kp_screen = (
                        "╭──────────────────────────╮\n"
                        "  💶 DEPOSIT 💷\n"
                        "╰──────────────────────────╯\n"
                        "  Enter The Amount Below\n\n"
                        "😊 Minimum ₹1 Max ₹10,000\n\n"
                        f"💵 Amount : ₹{disp}"
                    )
                    cbot.edit_message_text(kp_screen, cid, mid, reply_markup=kp)

                elif data.startswith("chk_pay_"):
                    utr = data.replace("chk_pay_", "")
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT status, amount FROM transactions WHERE tx_id=?", (utr,))
                    row = cur.fetchone()
                    conn.close()
                    if row and row["status"] == "completed":
                        cbot.answer_callback_query(call.id, f"Payment Verified! ₹{row['amount']} credited.", show_alert=True)
                        cbot.send_message(cid, "Payment Received Successfully!", reply_markup=get_user_main_menu())
                    else:
                        cbot.answer_callback_query(call.id, "Payment not received yet!\n\nPlease complete the payment on your UPI app and click Verify again.", show_alert=True)

                elif data.startswith("cnl_pay_"):
                    cbot.edit_message_caption("🛑 Deposit CANCELLED", cid, mid)
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("⭐ Main Menu", callback_data="u_back_main"))
                    cbot.send_message(cid, "Deposit was cancelled.", reply_markup=m)

                elif data == "u_hist":
                    hist_screen = (
                        "🗓️ Your Order History\n\n"
                        "Select Order Type To Track Delivery Status.\n\n"
                        "Completed Orders Update Automatically, Cancelled Orders Are Eligible For Instant Refunds 💎"
                    )
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("🔵 Pending", callback_data="h_pending"), types.InlineKeyboardButton("🟢 Completed", callback_data="h_completed"))
                    m.add(types.InlineKeyboardButton("❌ Cancelled", callback_data="h_cancelled"), types.InlineKeyboardButton("🟣 Refund", callback_data="h_refund"))
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_back_main"))
                    cbot.edit_message_text(hist_screen, cid, mid, reply_markup=m)

                elif data in ["h_pending", "h_completed", "h_cancelled"]:
                    st = data.replace("h_", "").capitalize()
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT service_name, quantity, charge FROM bot_orders WHERE bot_id=? AND user_id=? AND status=?", (bot_id, uid, st))
                    ords = cur.fetchall()
                    conn.close()
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_hist"))
                    if ords:
                        t = "\n\n".join([f"📦 {o['service_name']}\nQty: {o['quantity']} | Cost: ₹{o['charge']}" for o in ords])
                        cbot.edit_message_text(f"{st} Orders:\n\n{t}", cid, mid, reply_markup=m)
                    else:
                        cbot.edit_message_text(f"╭──────────────────────────╮\n  {st} Orders\n╰──────────────────────────╯\n\n⚠️ No Orders Found In This Section", cid, mid, reply_markup=m)

                elif data == "h_refund":
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_hist"))
                    ref_text = (
                        "Refund\n\n"
                        "👾 Send The Order Id You Want To Refund\n\n"
                        "👾 Refund Is Given Only If The Order Is Cancelled"
                    )
                    cbot.edit_message_text(ref_text, cid, mid, reply_markup=m)

                elif data == "u_ord":
                    ord_screen = (
                        "╭──────────────────────────╮\n"
                        "  ORDER NOW 🖤\n"
                        "╰──────────────────────────╯\n\n"
                        "✅ SELECT A PLATFORM\n"
                        "Choose Your Platform To Browse High Speed Guaranteed Packages With Instant Delivery ⏳\n"
                        "❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️"
                    )
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("📸 INSTAGRAM", callback_data="u_plat_Instagram"), types.InlineKeyboardButton("📘 FACEBOOK", callback_data="u_plat_Facebook"))
                    m.add(types.InlineKeyboardButton("✈️ TELEGRAM", callback_data="u_plat_Telegram"))
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_back_main"))
                    cbot.edit_message_text(ord_screen, cid, mid, reply_markup=m)

                elif data == "u_plat_Instagram":
                    ig_screen = (
                        "👑 Select Your Service 👑\n\n"
                        "Choose A Service Category 💵\n"
                        "All Categories Feature Real-Time Processing And Competitive Rates.\n"
                        "🖤🖤🖤"
                    )
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("👥 Ig Followers", callback_data="u_sub_Instagram_Ig Followers"), types.InlineKeyboardButton("💖 Ig Likes", callback_data="u_sub_Instagram_Ig Likes"))
                    m.add(types.InlineKeyboardButton("🎬 Reels View's", callback_data="u_sub_Instagram_Reels View's"), types.InlineKeyboardButton("👁️ Post View's", callback_data="u_sub_Instagram_Post View's"))
                    m.add(types.InlineKeyboardButton("⏩ MORE", callback_data="u_ig_more"))
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_ord"))
                    cbot.edit_message_text(ig_screen, cid, mid, reply_markup=m)

                elif data == "u_ig_more":
                    ig_more = (
                        "👑 Select Your Service 👑\n\n"
                        "Choose A Service Category 💵\n"
                        "All Categories Feature Real-Time Processing And Competitive Rates.\n"
                        "🖤🖤🖤"
                    )
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("🚀 Post Share", callback_data="u_sub_Instagram_Post Share"), types.InlineKeyboardButton("🔁 Repost", callback_data="u_sub_Instagram_Repost"))
                    m.add(types.InlineKeyboardButton("💬 Comment", callback_data="u_sub_Instagram_Comment"), types.InlineKeyboardButton("👀 Story View's", callback_data="u_sub_Instagram_Story View's"))
                    m.add(types.InlineKeyboardButton("⏮️ PREVIOUS", callback_data="u_plat_Instagram"))
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_ord"))
                    cbot.edit_message_text(ig_more, cid, mid, reply_markup=m)

                elif data.startswith("u_sub_"):
                    parts = data.split("_")
                    plat = parts[2]
                    sub_cat = parts[3]
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT id, service_name, selling_price_per_100 FROM bot_services WHERE bot_id=? AND platform=? AND sub_category=? AND is_published=1", (bot_id, plat, sub_cat))
                    srvs = cur.fetchall()
                    conn.close()

                    m = types.InlineKeyboardMarkup(row_width=1)
                    for s in srvs:
                        m.add(types.InlineKeyboardButton(f"{s['service_name']}", callback_data=f"u_view_srv_{s['id']}"))
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data=f"u_plat_{plat}"))
                    cbot.edit_message_text(f"🛒 {sub_cat.upper()}\n\n👾 Select A Service To View Rates And Place Order", cid, mid, reply_markup=m)

                elif data.startswith("u_view_srv_"):
                    sid = int(data.replace("u_view_srv_", ""))
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM bot_services WHERE id=?", (sid,))
                    srv = cur.fetchone()
                    conn.close()

                    user_states[f"{bot_id}_{uid}"] = {"step": "wait_link", "service_id": sid}
                    srv_desc = (
                        f"╭──────────────────────────╮\n"
                        f"  {srv['service_name'].upper()}\n"
                        f"╰──────────────────────────╯\n\n"
                        f"💵 Price : ₹{srv['selling_price_per_100']} / 100\n"
                        f"🎯 Min : {srv['min_qty']} • Max : {srv['max_qty']}\n\n"
                        f"📜 DETAILS\n\n"
                        f"{srv['description']}\n\n"
                        f"🔗 Now Send Your Profile / Post Link"
                    )
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data=f"u_sub_{srv['platform']}_{srv['sub_category']}"))
                    cbot.edit_message_text(srv_desc, cid, mid, reply_markup=m)

                elif data == "u_supp":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT support_contact FROM child_bots WHERE bot_id=?", (bot_id,))
                    supp = cur.fetchone()["support_contact"] or "@pranavsmm"
                    conn.close()
                    supp_url = f"https://wa.me/{supp.replace('+', '')}" if supp.isdigit() else f"https://t.me/{supp.replace('@', '')}"
                    m = types.InlineKeyboardMarkup(row_width=1)
                    m.add(types.InlineKeyboardButton("💬 Chat with Support", url=supp_url))
                    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
                    cbot.edit_message_text(f"Customer Support:\n\nDirect Contact: {supp}", cid, mid, reply_markup=m)

                elif data == "u_cyob":
                    cyob_text = (
                        "👑 CREATE YOUR OWN BOT ★ PRO\n\n"
                        "START YOUR OWN BRANDED RESELLER BUSINESS IN MINUTES.\n\n"
                        "1️⃣ OPEN ➔ @BotFather\n"
                        "2️⃣ SEND /newbot & FOLLOW THE STEPS\n"
                        "3️⃣ COPY THE BOT TOKEN IT GIVES YOU\n"
                        "4️⃣ PRESS ADD BOT AND PASTE IT HERE\n"
                        "❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                        "YOUR BOT GOES LIVE INSTANTLY WITH ALL FEATURES 🖤"
                    )
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("💛 Your Bots", callback_data="m_mybots"), types.InlineKeyboardButton("➕ Add Bot", callback_data="m_add_bot"))
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_back_main"))
                    cbot.edit_message_text(cyob_text, cid, mid, reply_markup=m)

                # ================= OWNER PANEL (/admin) =================
                elif data.startswith("a_") or data.startswith("adm_"):
                    if uid != owner_id:
                        cbot.answer_callback_query(call.id, "Access Denied", show_alert=True)
                        return

                    if data == "a_back_main":
                        cbot.send_message(cid, "Main Menu:", reply_markup=get_user_main_menu())

                    elif data == "adm_back_panel":
                        admin_text = (
                            "👑 Owner Panel\n\n"
                            f"🤖 @{bot_username}\n\n"
                            "Manage Your Bot Settings: Set Your Own Service Prices, Configure Your Payment Gateway API, And Manage Your Users.\n\n"
                            "☆━─━─━─━─━─━─━─━☆"
                        )
                        cbot.edit_message_text(admin_text, cid, mid, reply_markup=get_owner_panel())

                    elif data == "a_services":
                        srv_menu = (
                            "📦 SERVICES\n\n"
                            "📱 SELECT PLATFORM TO MANAGE SERVICES\n\n"
                            "CHOOSE A PLATFORM TO VIEW MASTER SERVICES, SET YOUR OWN SELLING PRICE, AND PUBLISH THEM TO YOUR BOT.\n\n"
                            "☆━─━─━─━─━─━─━─━☆"
                        )
                        m = types.InlineKeyboardMarkup(row_width=1)
                        m.add(
                            types.InlineKeyboardButton("INSTAGRAM", callback_data="adm_plat_Instagram"),
                            types.InlineKeyboardButton("FACEBOOK", callback_data="adm_plat_Facebook"),
                            types.InlineKeyboardButton("TELEGRAM", callback_data="adm_plat_Telegram"),
                            types.InlineKeyboardButton("Go Back", callback_data="adm_back_panel")
                        )
                        cbot.edit_message_text(srv_menu, cid, mid, reply_markup=m)

                    elif data.startswith("adm_plat_"):
                        plat = data.replace("adm_plat_", "")
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT id, service_name, cost_price, selling_price_per_100, is_published FROM bot_services WHERE bot_id=? AND platform=?", (bot_id, plat))
                        srvs = cur.fetchall()
                        conn.close()

                        m = types.InlineKeyboardMarkup(row_width=1)
                        for s in srvs:
                            m.add(types.InlineKeyboardButton(f"{s['service_name']} • ₹{s['cost_price']}", callback_data=f"adm_manage_srv_{s['id']}"))
                        m.add(types.InlineKeyboardButton("Go Back", callback_data="a_services"))
                        cbot.edit_message_text(f"📱 {plat} Services:\n\nTap A Service To Set Your Price And Publish", cid, mid, reply_markup=m)

                    elif data.startswith("adm_manage_srv_"):
                        sid = int(data.replace("adm_manage_srv_", ""))
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT * FROM bot_services WHERE id=?", (sid,))
                        srv = cur.fetchone()
                        conn.close()

                        srv_info = (
                            f"📦 {srv['service_name'].upper()}\n\n"
                            f"💵 Base Price : ₹{srv['cost_price']} / 100 (Your Cost)\n"
                            f"💰 Your Price : ₹{srv['selling_price_per_100']}\n"
                            f"🎯 {srv['min_qty']} - {srv['max_qty']}\n\n"
                            f"{srv['description']}\n\n"
                            "SET YOUR PRICE HIGHER THAN BASE TO EARN PROFIT ON EVERY AUTOMATED ORDER.\n\n"
                            "☆━─━─━─━─━─━─━─━☆"
                        )
                        m = types.InlineKeyboardMarkup(row_width=1)
                        m.add(types.InlineKeyboardButton("Set Price & Publish", callback_data=f"adm_setprice_{sid}"))
                        m.add(types.InlineKeyboardButton("Go Back", callback_data=f"adm_plat_{srv['platform']}"))
                        cbot.edit_message_text(srv_info, cid, mid, reply_markup=m)

                    elif data.startswith("adm_setprice_"):
                        sid = int(data.replace("adm_setprice_", ""))
                        user_states[f"{bot_id}_{uid}"] = {"step": "wait_price_input", "sid": sid}
                        m = types.InlineKeyboardMarkup()
                        m.add(types.InlineKeyboardButton("Cancel", callback_data="adm_back_panel"))
                        cbot.send_message(cid, "✍️ INPUT\n\n🪙 Send Your Selling Price Per 100", reply_markup=m)

                    elif data == "a_payment":
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT fampay_active, paytm_active, bharatpe_active, fampay_apikey FROM child_bots WHERE bot_id=?", (bot_id,))
                        bset = cur.fetchone()
                        conn.close()

                        f_st = "Active ✅" if bset["fampay_active"] == 1 else "Disabled ❌"
                        p_st = "Active ✅" if bset["paytm_active"] == 1 else "Disabled ❌"
                        bp_st = "Active ✅" if bset["bharatpe_active"] == 1 else "NOT CONFIGURED ❌"
                        k_st = "(Configured Securely)" if bset["fampay_apikey"] else "Not Set"

                        pay_screen = (
                            "💳 MANAGE DEPOSIT GATEWAYS\n\n"
                            "Configure FamPay, Paytm, Or BharatPe To Let Your Users Deposit Via Automated Upi Qr.\n\n"
                            f"⚡ FamPay : {f_st}\n"
                            f"💙 Paytm : {p_st}\n"
                            f"🧡 BharatPe : {bp_st}\n\n"
                            f"🔑 Api Key : ************\n"
                            f"{k_st}"
                        )
                        m = types.InlineKeyboardMarkup(row_width=2)
                        m.add(types.InlineKeyboardButton("⚡ FamPay ➕", callback_data="adm_tgl_fampay"), types.InlineKeyboardButton("💙 Paytm ➕", callback_data="adm_tgl_paytm"))
                        m.add(types.InlineKeyboardButton("🧡 BharatPe ➕", callback_data="adm_tgl_bp"))
                        m.add(types.InlineKeyboardButton("Edit Api", callback_data="adm_edit_api"), types.InlineKeyboardButton("Delete Api", callback_data="adm_del_api"))
                        m.add(types.InlineKeyboardButton("Create Api", url="https://fampay-flame.vercel.app/"))
                        m.add(types.InlineKeyboardButton("Go Back", callback_data="adm_back_panel"))
                        cbot.edit_message_text(pay_screen, cid, mid, reply_markup=m)

                    elif data == "adm_edit_api":
                        user_states[f"{bot_id}_{uid}"] = "wait_api_key_only"
                        cbot.send_message(cid, "🔑 Send your new API Key from FMP Portal:")

                    elif data == "adm_del_api":
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("UPDATE child_bots SET fampay_apikey='' WHERE bot_id=?", (bot_id,))
                        conn.commit()
                        conn.close()
                        cbot.answer_callback_query(call.id, "API Key Deleted!", show_alert=True)

                    elif data == "a_suppcontact":
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT support_contact FROM child_bots WHERE bot_id=?", (bot_id,))
                        curr = cur.fetchone()["support_contact"] or "@pranavsmm"
                        conn.close()

                        supp_cfg = (
                            "🎧 SUPPORT CONTACT\n\n"
                            f"Current: ({curr})\n\n"
                            "Users Clicking Support On Your Bot Will Be Directed To This Contact.\n"
                            "You Can Enter A WhatsApp Number (E.G. 919876543210), Telegram Username (@Username), Or Custom Link."
                        )
                        m = types.InlineKeyboardMarkup(row_width=1)
                        m.add(types.InlineKeyboardButton("Set / Edit Support", callback_data="adm_edit_supp"))
                        m.add(types.InlineKeyboardButton("Reset To Default", callback_data="adm_reset_supp"))
                        m.add(types.InlineKeyboardButton("Owner Home", callback_data="adm_back_panel"))
                        cbot.edit_message_text(supp_cfg, cid, mid, reply_markup=m)

                    elif data == "adm_edit_supp":
                        user_states[f"{bot_id}_{uid}"] = "wait_supp_input"
                        m = types.InlineKeyboardMarkup()
                        m.add(types.InlineKeyboardButton("Cancel", callback_data="adm_back_panel"))
                        cbot.send_message(cid, "✍️ Support Contact\n\nSend Your WhatsApp Number (E.g. 919876543210), Telegram Username (@username), Or Custom Link.", reply_markup=m)

                    elif data == "adm_reset_supp":
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("UPDATE child_bots SET support_contact='@pranavsmm' WHERE bot_id=?", (bot_id,))
                        conn.commit()
                        conn.close()
                        cbot.answer_callback_query(call.id, "Reset to @pranavsmm", show_alert=True)

                    elif data == "a_promode":
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("SELECT pro_mode FROM child_bots WHERE bot_id=?", (bot_id,))
                        cur_m = cur.fetchone()["pro_mode"]
                        new_m = 0 if cur_m == 1 else 1
                        cur.execute("UPDATE child_bots SET pro_mode=? WHERE bot_id=?", (new_m, bot_id))
                        conn.commit()
                        conn.close()
                        cbot.answer_callback_query(call.id, f"Pro Mode is now {'ON ✅' if new_m == 1 else 'OFF ❌'}", show_alert=True)

            # Text Handler
            @cbot.message_handler(func=lambda m: f"{bot_id}_{m.from_user.id}" in user_states and not m.text.startswith('/'))
            def c_text_inputs(m):
                uid = m.from_user.id
                cid = m.chat.id
                key = f"{bot_id}_{uid}"
                st_data = user_states.pop(key, None)
                txt = m.text.strip()

                if isinstance(st_data, dict) and st_data.get("step") == "wait_link":
                    sid = st_data["service_id"]
                    user_states[key] = {"step": "wait_qty", "service_id": sid, "link": txt}
                    cbot.send_message(cid, f"Link Received: {txt}\n\nEnter Quantity:")

                elif isinstance(st_data, dict) and st_data.get("step") == "wait_qty":
                    if not txt.isdigit():
                        cbot.send_message(cid, "Please enter numbers only.")
                        return
                    qty = int(txt)
                    sid = st_data["service_id"]
                    link = st_data["link"]

                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM bot_services WHERE id=?", (sid,))
                    srv = cur.fetchone()
                    cur.execute("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid))
                    bal = cur.fetchone()["balance"]

                    cost = (qty / 100.0) * srv["selling_price_per_100"]
                    if bal < cost:
                        m = types.InlineKeyboardMarkup()
                        m.add(types.InlineKeyboardButton("💰 Deposit Now", callback_data="u_dep"))
                        cbot.send_message(cid, f"Low Balance!\nOrder Cost: ₹{cost:.2f}\nYour Balance: ₹{bal:.2f}", reply_markup=m)
                        conn.close()
                    else:
                        cur.execute("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ? WHERE bot_id=? AND user_id=?", (cost, cost, bot_id, uid))
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
                                    (bot_id, uid, srv["service_name"], link, qty, cost, api_order_id, "Pending"))
                        conn.commit()
                        conn.close()
                        cbot.send_message(cid, f"🎉 Order Placed Successfully!\n\nService: {srv['service_name']}\nQty: {qty}\nCost: ₹{cost:.2f}")

                elif isinstance(st_data, dict) and st_data.get("step") == "wait_price_input":
                    try:
                        pr = float(txt)
                        sid = st_data["sid"]
                        conn = get_db()
                        cur = conn.cursor()
                        cur.execute("UPDATE bot_services SET selling_price_per_100=? WHERE id=?", (pr, sid))
                        conn.commit()
                        conn.close()
                        cbot.send_message(cid, f"Price Updated to ₹{pr} per 100! Service is published.", reply_markup=get_owner_panel())
                    except Exception:
                        cbot.send_message(cid, "Invalid number!")

                elif st_data == "wait_supp_input":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE child_bots SET support_contact=? WHERE bot_id=?", (txt, bot_id))
                    conn.commit()
                    conn.close()
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("Owner Panel", callback_data="adm_back_panel"))
                    cbot.send_message(cid, f"╭──────────────────────────╮\n  SUPPORT UPDATED\n╰──────────────────────────╯\n\nYour Clone Bot Support Contact Has Been Updated To:\n{txt}", reply_markup=m)

                elif st_data == "wait_api_key_only":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("UPDATE child_bots SET fampay_apikey=? WHERE bot_id=?", (txt, bot_id))
                    conn.commit()
                    conn.close()
                    cbot.send_message(cid, "FamPay API Key Updated Successfully!", reply_markup=get_owner_panel())

            print(f"[CHILD BOT ONLINE] @{bot_username}")
            cbot.infinity_polling(timeout=15, long_polling_timeout=10, skip_pending=True)
        except Exception as e:
            print(f"[CHILD BOT RESTARTING] @{bot_username} Error: {e}")
            time.sleep(3)

# Master Father Engine (Cloner)
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
                m = types.InlineKeyboardMarkup(row_width=2)
                m.add(
                    types.InlineKeyboardButton("💳 Balance", callback_data="u_bal"),
                    types.InlineKeyboardButton("💰 Deposit", callback_data="u_dep")
                )
                m.add(
                    types.InlineKeyboardButton("🗓️ History", callback_data="u_hist"),
                    types.InlineKeyboardButton("🛒 Order Now", callback_data="u_ord")
                )
                m.add(
                    types.InlineKeyboardButton("💬 Support", callback_data="u_supp"),
                    types.InlineKeyboardButton("👑 CYOB", callback_data="m_cyob")
                )
                menu_text = (
                    "💎 MAIN MENU 💎 ~\n\n"
                    "╔══════════════════════╗\n"
                    "  ✨ 𝓦𝓔𝓛𝓒𝓞𝓜𝓔 ★ VIP ✨\n"
                    "  ❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                    "  🥶 Choose An Option Below 🎀\n"
                    "╚══════════════════════╝"
                )
                master_bot.send_message(msg.chat.id, menu_text, reply_markup=m)

            @master_bot.callback_query_handler(func=lambda c: c.data.startswith("m_"))
            def m_calls(c):
                uid = c.from_user.id
                cid = c.message.chat.id
                mid = c.message.message_id

                if c.data == "m_cyob":
                    cyob_box = (
                        "👑 CREATE YOUR OWN BOT ★ PRO\n\n"
                        "START YOUR OWN BRANDED RESELLER BUSINESS IN MINUTES.\n\n"
                        "1️⃣ OPEN ➔ @BotFather\n"
                        "2️⃣ SEND /newbot & FOLLOW THE STEPS\n"
                        "3️⃣ COPY THE BOT TOKEN IT GIVES YOU\n"
                        "4️⃣ PRESS ADD BOT AND PASTE IT HERE\n"
                        "❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                        "YOUR BOT GOES LIVE INSTANTLY WITH ALL FEATURES 🖤"
                    )
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("💛 Your Bots", callback_data="m_mybots"), types.InlineKeyboardButton("➕ Add Bot", callback_data="m_add_bot"))
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="m_start_back"))
                    master_bot.edit_message_text(cyob_box, cid, mid, reply_markup=m)

                elif c.data == "m_start_back":
                    m_start(c.message)

                elif c.data == "m_mybots":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT bot_id, bot_username, bot_name FROM child_bots WHERE owner_id=?", (uid,))
                    bots = cur.fetchall()
                    conn.close()

                    if not bots:
                        m = types.InlineKeyboardMarkup()
                        m.add(types.InlineKeyboardButton("➕ Add Bot", callback_data="m_add_bot"))
                        master_bot.edit_message_text("No active bots found. Click Add Bot to create one!", cid, mid, reply_markup=m)
                    else:
                        b = bots[0]
                        txt = (
                            "👑 YOUR CLONED BOTS\n\n"
                            "MANAGE YOUR CLONED BOTS BELOW:\n\n"
                            f"• 🟢 @{b['bot_username']} (ONLINE) (ID: {b['bot_id']})"
                        )
                        m = types.InlineKeyboardMarkup(row_width=2)
                        m.add(types.InlineKeyboardButton("🔄 Replace Token", callback_data=f"m_rep_{b['bot_id']}"), types.InlineKeyboardButton("❌ Delete Bot", callback_data=f"m_del_{b['bot_id']}"))
                        m.add(types.InlineKeyboardButton("🔙 Back to CYOB", callback_data="m_cyob"))
                        master_bot.edit_message_text(txt, cid, mid, reply_markup=m)

                elif c.data.startswith("m_del_"):
                    bid = int(c.data.replace("m_del_", ""))
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT bot_username FROM child_bots WHERE bot_id=?", (bid,))
                    b_u = cur.fetchone()["bot_username"]
                    cur.execute("DELETE FROM child_bots WHERE bot_id=?", (bid,))
                    conn.commit()
                    conn.close()

                    del_txt = (
                        f"❌ BOT DELETED\n\n"
                        f"BOT @{b_u} HAS BEEN STOPPED AND REMOVED.\n\n"
                        "👾 YOUR CUSTOMER BALANCES, SERVICES, AND GATEWAY SETTINGS ARE SAFELY SAVED WITH YOUR ACCOUNT.\n"
                        "IF YOU RECONNECT A NEW BOT ANYTIME, ALL YOUR DATA WILL BE AUTOMATICALLY RESTORED!"
                    )
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("💛 Your Bots", callback_data="m_mybots"), types.InlineKeyboardButton("👑 CYOB Menu", callback_data="m_cyob"))
                    master_bot.edit_message_text(del_txt, cid, mid, reply_markup=m)

                elif c.data == "m_add_bot":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) as cnt FROM child_bots WHERE owner_id=?", (uid,))
                    cnt = cur.fetchone()["cnt"]
                    conn.close()

                    if cnt >= 1:
                        lim_txt = (
                            "╭──────────────────────────╮\n"
                            "  ⚠️ LIMIT REACHED\n"
                            "╰──────────────────────────╯\n\n"
                            "⚠️ MAXIMUM 1 BOT ALLOWED PER USER\n\n"
                            "YOU ALREADY HAVE 1 ACTIVE CLONE BOT RUNNING.\n\n"
                            "👾 TO USE A DIFFERENT BOT, YOU CAN REPLACE YOUR BOT TOKEN OR DELETE YOUR EXISTING BOT FROM YOUR BOTS."
                        )
                        m = types.InlineKeyboardMarkup(row_width=1)
                        m.add(types.InlineKeyboardButton("💛 Your Bots", callback_data="m_mybots"), types.InlineKeyboardButton("⭐ Main Menu", callback_data="m_start_back"))
                        master_bot.edit_message_text(lim_txt, cid, mid, reply_markup=m)
                    else:
                        user_states[uid] = "wait_token"
                        sub_text = (
                            "🏆 SUBMIT TOKEN\n\n"
                            "👾 PASTE OR FORWARD YOUR BOT TOKEN NOW"
                        )
                        m = types.InlineKeyboardMarkup()
                        m.add(types.InlineKeyboardButton("🛑 CANCEL", callback_data="m_cyob"))
                        master_bot.edit_message_text(sub_text, cid, mid, reply_markup=m)

            @master_bot.message_handler(func=lambda m: m.from_user.id in user_states and not m.text.startswith('/'))
            def m_token_receiver(msg):
                uid = msg.from_user.id
                cid = msg.chat.id
                state = user_states.pop(uid, None)
                token = msg.text.strip()

                if state == "wait_token":
                    v_msg = master_bot.send_message(cid, "🔄 CONNECTING YOUR BOT...\n\nVALIDATING TOKEN AND INITIALIZING YOUR CLONE BOT. PLEASE WAIT A FEW MOMENTS...")
                    chk = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
                    data = chk.json()
                    if not data.get("ok"):
                        master_bot.edit_message_text("❌ INVALID BOT TOKEN! PLEASE PROVIDE A VALID TOKEN FROM BOTFATHER.", cid, v_msg.message_id)
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
                        cur.execute("UPDATE child_bots SET bot_username=?, bot_name=? WHERE bot_token_enc=?", (bot_user, bot_name, token_enc))
                        conn.commit()
                        cur.execute("SELECT bot_id FROM child_bots WHERE bot_token_enc=?", (token_enc,))
                        bot_id = cur.fetchone()["bot_id"]
                    conn.close()

                    t = threading.Thread(target=run_child_bot_loop, args=(bot_id, uid, token, bot_user, bot_name), daemon=True)
                    t.start()
                    bot_threads[token] = t

                    live_text = (
                        "╭──────────────────────────╮\n"
                        "  🚀 BOT IS LIVE\n"
                        "╰──────────────────────────╯\n\n"
                        f"🤖 @{bot_user}\n\n"
                        f"👾 YOU ARE THE OWNER, SEND /admin IN YOUR BOT\n"
                        "👾 ADD SERVICES AND SET YOUR PRICES THERE\n"
                        "👾 KEEP BALANCE HERE, ORDERS ON YOUR BOT ARE CHARGED FROM IT"
                    )
                    m = types.InlineKeyboardMarkup(row_width=1)
                    m.add(types.InlineKeyboardButton("Open My Bot", url=f"https://t.me/{bot_user}"))
                    m.add(types.InlineKeyboardButton("Main Menu", callback_data="m_start_back"))
                    master_bot.edit_message_text(live_text, cid, v_msg.message_id, reply_markup=m)

            print("[MASTER BOT] Polling started...")
            master_is_running = True
            master_bot.infinity_polling(timeout=15, long_polling_timeout=10, skip_pending=True)
        except Exception as e:
            print(f"[MASTER BOT RESTARTING] Error: {e}")
            master_is_running = False
            time.sleep(3)

def self_ping_keepalive():
    while True:
        try:
            requests.get(f"http://127.0.0.1:{RENDER_PORT}/", timeout=5)
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
