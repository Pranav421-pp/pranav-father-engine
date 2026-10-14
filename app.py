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

ADMIN_ID_ENV = os.environ.get("ADMIN_ID", "8585055903").strip()
try:
    SUPER_ADMIN_ID = int(ADMIN_ID_ENV)
except Exception:
    SUPER_ADMIN_ID = 8585055903

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
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
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
    CREATE TABLE IF NOT EXISTS master_services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        sub_category TEXT,
        service_name TEXT,
        main_api_service_id TEXT UNIQUE,
        base_rate_per_100 REAL DEFAULT 1.0,
        min_qty INTEGER DEFAULT 100,
        max_qty INTEGER DEFAULT 1000000,
        description TEXT DEFAULT 'Fast Speed High Quality'
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS child_services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id INTEGER,
        master_service_id INTEGER,
        selling_price_per_100 REAL DEFAULT 3.0,
        custom_description TEXT DEFAULT '',
        is_published INTEGER DEFAULT 1,
        UNIQUE(bot_id, master_service_id)
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

def seed_default_master_services():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as count FROM master_services")
    if cur.fetchone()["count"] == 0:
        defaults = [
            ("Instagram", "Ig Likes", "Ig Likes Indian Fast", "101", 1.0, 100, 1000000, "Fast speed drop safe"),
            ("Instagram", "Ig Followers", "Cheap Mix Followers", "102", 4.5, 100, 500000, "High speed mix profile"),
            ("Instagram", "Ig Followers", "HQ Indian Followers", "103", 25.0, 100, 200000, "HQ Real lifetime refill"),
            ("Instagram", "Reels View's", "Reel Views Instant", "104", 0.05, 100, 5000000, "Fast instant impressions"),
            ("Facebook", "Fb Followers", "Facebook Page Followers", "105", 15.0, 100, 100000, "Non drop guaranteed"),
            ("Telegram", "Tg Members", "Telegram Channel Members", "106", 8.0, 100, 100000, "0-1 hour fast start")
        ]
        for d in defaults:
            cur.execute("""
            INSERT OR IGNORE INTO master_services (platform, sub_category, service_name, main_api_service_id, base_rate_per_100, min_qty, max_qty, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, d)
        conn.commit()
    conn.close()

seed_default_master_services()

def sync_services_from_website_api():
    if not MAIN_PANEL_API_KEY:
        return 0, "No MAIN_PANEL_API_KEY configured"
    try:
        resp = requests.post(MAIN_PANEL_URL, data={"key": MAIN_PANEL_API_KEY, "action": "services"}, timeout=15)
        srv_list = resp.json()
        if not isinstance(srv_list, list):
            return 0, f"API error: {srv_list}"
        
        conn = get_db()
        cur = conn.cursor()
        synced = 0
        for s in srv_list:
            sid = str(s.get("service", ""))
            name = str(s.get("name", "Service"))
            cat = str(s.get("category", "General")).lower()
            rate_per_1k = float(s.get("rate", 10.0))
            rate_per_100 = round(rate_per_1k / 10.0, 3)
            min_q = int(s.get("min", 100))
            max_q = int(s.get("max", 1000000))

            plat = "Instagram"
            sub_cat = "Ig Likes"
            if "instagram" in cat or "ig" in cat:
                plat = "Instagram"
                if "follower" in cat or "follower" in name.lower():
                    sub_cat = "Ig Followers"
                elif "view" in cat or "view" in name.lower():
                    sub_cat = "Reels View's"
                else:
                    sub_cat = "Ig Likes"
            elif "facebook" in cat or "fb" in cat:
                plat = "Facebook"
                sub_cat = "Fb Followers"
            elif "telegram" in cat or "tg" in cat:
                plat = "Telegram"
                sub_cat = "Tg Members"

            cur.execute("""
            INSERT INTO master_services (platform, sub_category, service_name, main_api_service_id, base_rate_per_100, min_qty, max_qty, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(main_api_service_id) DO UPDATE SET
            base_rate_per_100=excluded.base_rate_per_100,
            service_name=excluded.service_name,
            min_qty=excluded.min_qty,
            max_qty=excluded.max_qty
            """, (plat, sub_cat, name, sid, rate_per_100, min_q, max_q, "Auto synced from pranavsmm.shop"))
            synced += 1

        conn.commit()
        conn.close()
        return synced, "Success"
    except Exception as e:
        return 0, str(e)

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
        types.InlineKeyboardButton("⌫", callback_data="kp_clear")
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

        target_token = None
        l_chan = ""
        if bot_id == 0:
            target_token = MASTER_BOT_TOKEN
        else:
            cur.execute("SELECT bot_token_enc, log_channel FROM child_bots WHERE bot_id=?", (bot_id,))
            b_row = cur.fetchone()
            if b_row:
                target_token = cipher_suite.decrypt(b_row["bot_token_enc"].encode()).decode()
                l_chan = b_row["log_channel"]
        conn.close()

        if target_token:
            try:
                tb = telebot.TeleBot(target_token)
                tb.send_message(user_id, f"✅ Payment Success!\n\nAmount: Rs {credited_amt:.2f}\nRef/UTR: {tx_id}\nWallet balance updated.")
                if l_chan:
                    tb.send_message(l_chan, f"🔔 [DEPOSIT SUCCESS]\nUser: {user_id}\nAmount: Rs {credited_amt}\nRef: {tx_id}")
            except Exception:
                pass

        return jsonify({"status": "success"}), 200

    conn.close()
    return jsonify({"status": "already_done"}), 200

def get_owner_panel(is_master=False):
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
    if is_master:
        m.add(types.InlineKeyboardButton("🔄 Sync pranavsmm.shop API", callback_data="adm_sync_api"))
    m.add(types.InlineKeyboardButton("Main Menu", callback_data="a_back_main"))
    return m

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

def handle_user_callbacks(bot, bot_id, call):
    uid = call.from_user.id
    cid = call.message.chat.id
    mid = call.message.message_id
    data = call.data

    if data in ["u_continue_main", "u_back_main", "a_back_main"]:
        menu_text = (
            "💎 MAIN MENU 💎 ~\n\n"
            "╔══════════════════════╗\n"
            "  ✨ 𝓦𝓔𝓛𝓒𝓞𝓜𝓔 ★ VIP ✨\n"
            "  ❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
            "  🥶 Choose An Option Below 🎀\n"
            "╚══════════════════════╝"
        )
        try:
            bot.edit_message_text(menu_text, cid, mid, reply_markup=get_user_main_menu())
        except Exception:
            bot.send_message(cid, menu_text, reply_markup=get_user_main_menu())

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
            "🛡️ ACCOUNT INFO PREMIUM\n\n"
            f"💰 Balance - ₹{bal:.2f}\n"
            f"🆔 User ID - {uid}\n"
            f"👤 User Name - @{call.from_user.username or 'User'}\n"
            f"💳 Total Deposit - ₹{tdep:.2f}\n"
            f"🛒 Total Spent - ₹{tsp:.2f}"
        )
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("💰 Deposit", callback_data="u_dep"), types.InlineKeyboardButton("🔙 Go Back", callback_data="u_back_main"))
        bot.edit_message_text(acc_text, cid, mid, reply_markup=m)

    elif data == "u_dep":
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("UPI Instant", callback_data="u_dep_method_upi"))
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_back_main"))
        bot.edit_message_text("💷 DEPOSIT FUNDS\n\nSelect A Method To Continue:", cid, mid, reply_markup=m)

    elif data == "u_dep_method_upi":
        keypad_amounts[f"{bot_id}_{uid}"] = ""
        kp, disp = build_deposit_keypad("")
        bot.edit_message_text(f"💶 DEPOSIT 💷\n\nMinimum ₹1 Max ₹10,000\n\n💵 Amount : ₹{disp}", cid, mid, reply_markup=kp)

    elif data.startswith("kp_"):
        act = data.replace("kp_", "")
        k_key = f"{bot_id}_{uid}"
        cur_amt = keypad_amounts.get(k_key, "")
        if act == "cancel":
            keypad_amounts.pop(k_key, None)
            bot.edit_message_text("Deposit Cancelled.", cid, mid, reply_markup=get_user_main_menu())
            return
        elif act == "clear":
            cur_amt = cur_amt[:-1] if len(cur_amt) > 1 else ""
        elif act in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "00"]:
            if len(cur_amt) < 5:
                cur_amt += act
        elif act == "confirm":
            if not cur_amt or int(cur_amt) < 1:
                bot.answer_callback_query(call.id, "Please enter at least ₹1", show_alert=True)
                return
            amt = float(cur_amt)
            keypad_amounts.pop(k_key, None)

            utr_num = f"388{random.randint(100000000, 999999999)}"
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO transactions (tx_id, bot_id, user_id, amount, status) VALUES (?, ?, ?, ?, ?)",
                        (utr_num, bot_id, uid, amt, "pending"))
            conn.commit()
            conn.close()

            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=upi://pay?pa=fam@upi&am={amt}&tr={utr_num}"
            qr_cap = f"SCAN & PAY\n\n💵 Amount : ₹{amt:.0f}\n🆔 UTR : {utr_num}\n⏱️ Valid : 15 Min"
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(types.InlineKeyboardButton("✅ VERIFY PAYMENT", callback_data=f"chk_pay_{utr_num}"))
            m.add(types.InlineKeyboardButton("❌ CANCEL", callback_data=f"cnl_pay_{utr_num}"))
            try:
                bot.delete_message(cid, mid)
            except Exception:
                pass
            bot.send_photo(cid, qr_url, caption=qr_cap, reply_markup=m)
            return

        keypad_amounts[k_key] = cur_amt
        kp, disp = build_deposit_keypad(cur_amt)
        bot.edit_message_text(f"💶 DEPOSIT 💷\n\nMinimum ₹1 Max ₹10,000\n\n💵 Amount : ₹{disp}", cid, mid, reply_markup=kp)

    elif data.startswith("chk_pay_"):
        utr = data.replace("chk_pay_", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT status, amount FROM transactions WHERE tx_id=?", (utr,))
        row = cur.fetchone()
        conn.close()
        if row and row["status"] == "completed":
            bot.answer_callback_query(call.id, f"Verified! ₹{row['amount']} credited.", show_alert=True)
            bot.send_message(cid, "Payment Received Successfully!", reply_markup=get_user_main_menu())
        else:
            bot.answer_callback_query(call.id, "Payment not received yet!\nPlease complete payment in your UPI app.", show_alert=True)

    elif data.startswith("cnl_pay_"):
        try:
            bot.edit_message_caption("🛑 Deposit Cancelled", cid, mid)
        except Exception:
            pass
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("⭐ Main Menu", callback_data="u_back_main"))
        bot.send_message(cid, "Deposit was cancelled.", reply_markup=m)

    elif data == "u_hist":
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("🔵 Pending", callback_data="h_pending"), types.InlineKeyboardButton("🟢 Completed", callback_data="h_completed"))
        m.add(types.InlineKeyboardButton("❌ Cancelled", callback_data="h_cancelled"), types.InlineKeyboardButton("🟣 Refund", callback_data="h_refund"))
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_back_main"))
        bot.edit_message_text("🗓️ Order History\n\nSelect type to check status:", cid, mid, reply_markup=m)

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
            t = "\n\n".join([f"📦 {o['service_name']}\nQty: {o['quantity']} | Cost: ₹{o['charge']:.2f}" for o in ords])
            bot.edit_message_text(f"{st} Orders:\n\n{t}", cid, mid, reply_markup=m)
        else:
            bot.edit_message_text(f"{st} Orders:\n\n⚠️ No Orders Found", cid, mid, reply_markup=m)

    elif data == "h_refund":
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_hist"))
        bot.edit_message_text("Refund:\nSend Cancelled Order ID to claim refund.", cid, mid, reply_markup=m)

    elif data == "u_ord":
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("📸 INSTAGRAM", callback_data="u_plat_Instagram"), types.InlineKeyboardButton("📘 FACEBOOK", callback_data="u_plat_Facebook"))
        m.add(types.InlineKeyboardButton("✈️ TELEGRAM", callback_data="u_plat_Telegram"))
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_back_main"))
        bot.edit_message_text("ORDER NOW 🖤\n\nSelect Platform:", cid, mid, reply_markup=m)

    elif data.startswith("u_plat_"):
        plat = data.replace("u_plat_", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT sub_category FROM master_services WHERE platform=?", (plat,))
        subs = cur.fetchall()
        conn.close()
        m = types.InlineKeyboardMarkup(row_width=2)
        for s in subs:
            m.add(types.InlineKeyboardButton(s["sub_category"], callback_data=f"u_sub_{plat}_{s['sub_category']}"))
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_ord"))
        bot.edit_message_text(f"Select {plat} Category:", cid, mid, reply_markup=m)

    elif data.startswith("u_sub_"):
        parts = data.split("_")
        plat = parts[2]
        sub_cat = parts[3]
        conn = get_db()
        cur = conn.cursor()
        if bot_id == 0:
            cur.execute("SELECT id, service_name, base_rate_per_100 as price FROM master_services WHERE platform=? AND sub_category=?", (plat, sub_cat))
        else:
            cur.execute("""
            SELECT m.id, m.service_name, c.selling_price_per_100 as price
            FROM child_services c
            JOIN master_services m ON c.master_service_id = m.id
            WHERE c.bot_id=? AND m.platform=? AND m.sub_category=? AND c.is_published=1
            """, (bot_id, plat, sub_cat))
        srvs = cur.fetchall()
        conn.close()

        m = types.InlineKeyboardMarkup(row_width=1)
        if srvs:
            for s in srvs:
                m.add(types.InlineKeyboardButton(f"{s['service_name']} (₹{s['price']}/100)", callback_data=f"u_viewsrv_{s['id']}"))
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data=f"u_plat_{plat}"))
        txt = f"🛒 {sub_cat}\n\nSelect Service:" if srvs else f"No services active under {sub_cat} currently."
        bot.edit_message_text(txt, cid, mid, reply_markup=m)

    elif data.startswith("u_viewsrv_"):
        msid = int(data.replace("u_viewsrv_", ""))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM master_services WHERE id=?", (msid,))
        ms = cur.fetchone()
        price = ms["base_rate_per_100"]
        desc = ms["description"]
        if bot_id != 0:
            cur.execute("SELECT selling_price_per_100, custom_description FROM child_services WHERE bot_id=? AND master_service_id=?", (bot_id, msid))
            cs = cur.fetchone()
            if cs:
                price = cs["selling_price_per_100"]
                if cs["custom_description"]:
                    desc = cs["custom_description"]
        conn.close()

        user_states[f"{bot_id}_{uid}"] = {"step": "wait_link", "msid": msid, "price": price}
        txt = (
            f"📦 {ms['service_name'].upper()}\n\n"
            f"💵 Price : ₹{price:.2f} / 100\n"
            f"🎯 Min : {ms['min_qty']} • Max : {ms['max_qty']}\n\n"
            f"📜 Details:\n{desc}\n\n"
            "🔗 Send Target Link in chat:"
        )
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data=f"u_sub_{ms['platform']}_{ms['sub_category']}"))
        bot.edit_message_text(txt, cid, mid, reply_markup=m)

    elif data == "u_supp":
        conn = get_db()
        cur = conn.cursor()
        if bot_id == 0:
            supp = "@pranavsmm"
        else:
            cur.execute("SELECT support_contact FROM child_bots WHERE bot_id=?", (bot_id,))
            supp = cur.fetchone()["support_contact"] or "@pranavsmm"
        conn.close()
        supp_url = f"https://wa.me/{supp.replace('+', '')}" if supp.isdigit() else f"https://t.me/{supp.replace('@', '')}"
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("💬 Chat with Support", url=supp_url))
        m.add(types.InlineKeyboardButton("🔙 Back", callback_data="u_back_main"))
        bot.edit_message_text(f"Customer Support:\n\nContact: {supp}", cid, mid, reply_markup=m)

    elif data == "u_cyob":
        cyob_text = (
            "👑 CREATE YOUR OWN BOT ★ PRO\n\n"
            "START YOUR OWN BRANDED RESELLER BUSINESS IN MINUTES.\n\n"
            "1️⃣ Open @BotFather\n"
            "2️⃣ Send /newbot and follow instructions\n"
            "3️⃣ Copy the API Token\n"
            "4️⃣ Send token to Master Bot\n\n"
            "Your Bot Goes Live Instantly!"
        )
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_back_main"))
        bot.edit_message_text(cyob_text, cid, mid, reply_markup=m)

def handle_owner_callbacks(bot, bot_id, call, is_master=False):
    uid = call.from_user.id
    cid = call.message.chat.id
    mid = call.message.message_id
    data = call.data

    if data == "adm_back_panel":
        bot.edit_message_text("👑 Owner Panel", cid, mid, reply_markup=get_owner_panel(is_master))

    elif data == "adm_sync_api" and is_master:
        bot.answer_callback_query(call.id, "Syncing from pranavsmm.shop...", show_alert=False)
        count, msg = sync_services_from_website_api()
        bot.send_message(cid, f"🔄 API Sync Finished!\n\nImported/Updated: {count} services from pranavsmm.shop\nStatus: {msg}", reply_markup=get_owner_panel(is_master))

    elif data == "a_services":
        if is_master:
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(
                types.InlineKeyboardButton("🔄 Sync from pranavsmm.shop API", callback_data="adm_sync_api"),
                types.InlineKeyboardButton("➕ Add Single Service Manually", callback_data="adm_add_single_srv"),
                types.InlineKeyboardButton("📋 View All Master Services", callback_data="adm_list_msrvs"),
                types.InlineKeyboardButton("🔙 Go Back", callback_data="adm_back_panel")
            )
            bot.edit_message_text("⚙️ MASTER SERVICES MANAGEMENT\n\nSync directly from your website or add manually:", cid, mid, reply_markup=m)
        else:
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(
                types.InlineKeyboardButton("📸 Instagram Services", callback_data="c_manage_plat_Instagram"),
                types.InlineKeyboardButton("📘 Facebook Services", callback_data="c_manage_plat_Facebook"),
                types.InlineKeyboardButton("✈️ Telegram Services", callback_data="c_manage_plat_Telegram"),
                types.InlineKeyboardButton("🔙 Go Back", callback_data="adm_back_panel")
            )
            bot.edit_message_text("⚙️ RESELLER SERVICE MANAGER\n\nSelect Platform to set your own selling price & publish:", cid, mid, reply_markup=m)

    elif data == "adm_add_single_srv" and is_master:
        user_states[f"{bot_id}_{uid}"] = "wait_m_single_srv"
        bot.send_message(cid, "Send details in format:\nPlatform | SubCategory | ServiceName | API_ServiceID | BaseCostPer100 | Min | Max\n\nExample:\nInstagram | Ig Likes | Ultra Fast Likes | 1024 | 1.2 | 100 | 50000")

    elif data == "adm_list_msrvs" and is_master:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, platform, service_name, base_rate_per_100, main_api_service_id FROM master_services LIMIT 20")
        rows = cur.fetchall()
        conn.close()
        txt = "\n".join([f"#{r['id']} [{r['platform']}] {r['service_name']} (ID:{r['main_api_service_id']}) - ₹{r['base_rate_per_100']}/100" for r in rows]) if rows else "No services in master DB."
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="a_services"))
        bot.send_message(cid, f"Master Services (Top 20):\n\n{txt}", reply_markup=m)

    elif data.startswith("c_manage_plat_"):
        plat = data.replace("c_manage_plat_", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, sub_category, service_name, base_rate_per_100 FROM master_services WHERE platform=?", (plat,))
        msrvs = cur.fetchall()
        conn.close()

        m = types.InlineKeyboardMarkup(row_width=1)
        for s in msrvs:
            m.add(types.InlineKeyboardButton(f"{s['service_name']} (Cost: ₹{s['base_rate_per_100']}/100)", callback_data=f"c_set_srv_{s['id']}"))
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="a_services"))
        bot.edit_message_text(f"Available {plat} Services from Master:\nClick any service to set your price & publish:", cid, mid, reply_markup=m)

    elif data.startswith("c_set_srv_"):
        msid = int(data.replace("c_set_srv_", ""))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM master_services WHERE id=?", (msid,))
        ms = cur.fetchone()
        cur.execute("SELECT selling_price_per_100, is_published FROM child_services WHERE bot_id=? AND master_service_id=?", (bot_id, msid))
        cs = cur.fetchone()
        conn.close()

        cur_sell = cs["selling_price_per_100"] if cs else ms["base_rate_per_100"] * 2.0
        st = "🟢 Published" if (cs and cs["is_published"] == 1) else "🔴 Not Published"

        txt = (
            f"📦 {ms['service_name'].upper()}\n\n"
            f"💵 Master Cost: ₹{ms['base_rate_per_100']:.2f} per 100\n"
            f"💰 Your Selling Price: ₹{cur_sell:.2f} per 100\n"
            f"📊 Status: {st}\n\n"
            f"{ms['description']}"
        )
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("💲 Set Price & Publish", callback_data=f"c_pub_{msid}"))
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data=f"c_manage_plat_{ms['platform']}"))
        bot.edit_message_text(txt, cid, mid, reply_markup=m)

    elif data.startswith("c_pub_"):
        msid = int(data.replace("c_pub_", ""))
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_resell_price", "msid": msid}
        bot.send_message(cid, "How much rupees do you want to sell per 100? (e.g. 3 or 5):")

    elif data == "a_payment":
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("SELECT fampay_endpoint, fampay_apikey FROM child_bots WHERE bot_id=?", (t_id,))
        row = cur.fetchone()
        conn.close()
        k = row["fampay_apikey"] if row else ""
        ep = row["fampay_endpoint"] if row else ""

        txt = (
            "💳 PAYMENT GATEWAY CONFIGURATION\n\n"
            f"API Endpoint: {ep or 'Default Flame/FamPay'}\n"
            f"API Key: {'Configured Securely ✅' if k else 'Not Set ❌'}\n\n"
            "Deposits will generate dynamic QR and credit automatically via this gateway."
        )
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("Edit API Key & Endpoint", callback_data="adm_edit_fampay"))
        m.add(types.InlineKeyboardButton("Create API (Gateway Portal)", url="https://fampay-flame.vercel.app/"))
        m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="adm_back_panel"))
        bot.edit_message_text(txt, cid, mid, reply_markup=m)

    elif data == "adm_edit_fampay":
        user_states[f"{bot_id}_{uid}"] = "wait_fampay_pair"
        bot.send_message(cid, "Send your Gateway details in format:\nEndpoint_URL | API_Key\n\nOr simply send your API_Key only to keep default endpoint.")

    elif data == "a_users":
        conn = get_db()
        cur = conn.cursor()
        if is_master:
            cur.execute("SELECT COUNT(*) as cnt FROM bot_clients")
        else:
            cur.execute("SELECT COUNT(*) as cnt FROM bot_clients WHERE bot_id=?", (bot_id,))
        cnt = cur.fetchone()["cnt"]
        conn.close()
        bot.answer_callback_query(call.id, f"Total Registered Users: {cnt}", show_alert=True)

    elif data == "a_addbal":
        user_states[f"{bot_id}_{uid}"] = "wait_add_bal"
        bot.send_message(cid, "Format: User_ID Amount\nExample: 8585055903 50")

    elif data == "a_dedbal":
        user_states[f"{bot_id}_{uid}"] = "wait_ded_bal"
        bot.send_message(cid, "Format: User_ID Amount\nExample: 8585055903 20")

    elif data == "a_ban":
        user_states[f"{bot_id}_{uid}"] = "wait_ban_user"
        bot.send_message(cid, "Send User_ID to ban:")

    elif data == "a_unban":
        user_states[f"{bot_id}_{uid}"] = "wait_unban_user"
        bot.send_message(cid, "Send User_ID to unban:")

    elif data == "a_logchan":
        user_states[f"{bot_id}_{uid}"] = "wait_log_chan"
        bot.send_message(cid, "Send Log Channel username (e.g. @MyLogChannel):")

    elif data == "a_forcesub":
        user_states[f"{bot_id}_{uid}"] = "wait_force_sub"
        bot.send_message(cid, "Send Force Sub Channel username (e.g. @MyChannel):")

    elif data == "a_suppcontact":
        user_states[f"{bot_id}_{uid}"] = "wait_supp_input"
        bot.send_message(cid, "Send Support Contact (WhatsApp number e.g. 919876543210 or @Username):")

    elif data == "a_promode":
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("SELECT pro_mode FROM child_bots WHERE bot_id=?", (t_id,))
        row = cur.fetchone()
        cur_m = row["pro_mode"] if row else 1
        new_m = 0 if cur_m == 1 else 1
        cur.execute("UPDATE child_bots SET pro_mode=? WHERE bot_id=?", (new_m, t_id))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, f"Pro Mode is now {'ON ✅' if new_m == 1 else 'OFF ❌'}", show_alert=True)

def handle_text_inputs(bot, bot_id, msg, is_master=False):
    uid = msg.from_user.id
    cid = msg.chat.id
    key = f"{bot_id}_{uid}"
    st_data = user_states.pop(key, None)
    txt = msg.text.strip()

    if isinstance(st_data, dict) and st_data.get("step") == "wait_link":
        msid = st_data["msid"]
        pr = st_data["price"]
        user_states[key] = {"step": "wait_qty", "msid": msid, "price": pr, "link": txt}
        bot.send_message(cid, f"Link received: {txt}\n\nEnter Quantity:")

    elif isinstance(st_data, dict) and st_data.get("step") == "wait_qty":
        if not txt.isdigit():
            bot.send_message(cid, "Please enter numbers only.")
            return
        qty = int(txt)
        msid = st_data["msid"]
        pr = st_data["price"]
        link = st_data["link"]

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM master_services WHERE id=?", (msid,))
        ms = cur.fetchone()
        cur.execute("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid))
        bal = cur.fetchone()["balance"]

        cost = (qty / 100.0) * pr
        if bal < cost:
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("💰 Deposit Now", callback_data="u_dep"))
            bot.send_message(cid, f"Insufficient Balance!\nCost: ₹{cost:.2f}\nYour Balance: ₹{bal:.2f}", reply_markup=m)
            conn.close()
        else:
            cur.execute("UPDATE bot_clients SET balance = balance - ?, total_spent = total_spent + ? WHERE bot_id=? AND user_id=?", (cost, cost, bot_id, uid))
            api_order_id = "MANUAL"
            if MAIN_PANEL_API_KEY and ms["main_api_service_id"]:
                try:
                    p_data = {"key": MAIN_PANEL_API_KEY, "action": "add", "service": ms["main_api_service_id"], "link": link, "quantity": qty}
                    r = requests.post(MAIN_PANEL_URL, data=p_data, timeout=10).json()
                    if "order" in r:
                        api_order_id = str(r["order"])
                except Exception:
                    pass

            cur.execute("INSERT INTO bot_orders (bot_id, user_id, service_name, link, quantity, charge, api_order_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (bot_id, uid, ms["service_name"], link, qty, cost, api_order_id, "Pending"))
            conn.commit()
            conn.close()
            bot.send_message(cid, f"🎉 Order Placed Successfully!\n\nService: {ms['service_name']}\nQty: {qty}\nCost: ₹{cost:.2f}\nOrder ID: {api_order_id}")

    elif isinstance(st_data, dict) and st_data.get("step") == "wait_resell_price":
        try:
            pr = float(txt)
            msid = st_data["msid"]
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO child_services (bot_id, master_service_id, selling_price_per_100, is_published)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(bot_id, master_service_id) DO UPDATE SET
            selling_price_per_100=excluded.selling_price_per_100,
            is_published=1
            """, (bot_id, msid, pr))
            conn.commit()
            conn.close()
            bot.send_message(cid, f"✅ Published! Your selling price is set to ₹{pr:.2f} per 100.", reply_markup=get_owner_panel(is_master))
        except Exception:
            bot.send_message(cid, "Invalid price number!")

    elif st_data == "wait_m_single_srv" and is_master:
        parts = [p.strip() for p in txt.split("|")]
        if len(parts) >= 7:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO master_services (platform, sub_category, service_name, main_api_service_id, base_rate_per_100, min_qty, max_qty)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(main_api_service_id) DO UPDATE SET
            base_rate_per_100=excluded.base_rate_per_100,
            service_name=excluded.service_name
            """, (parts[0], parts[1], parts[2], parts[3], float(parts[4]), int(parts[5]), int(parts[6])))
            conn.commit()
            conn.close()
            bot.send_message(cid, f"✅ Master Service '{parts[2]}' added/updated successfully!", reply_markup=get_owner_panel(is_master))
        else:
            bot.send_message(cid, "Invalid format! Make sure to provide all 7 fields separated by '|'")

    elif st_data == "wait_fampay_pair":
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        if "|" in txt:
            parts = [p.strip() for p in txt.split("|")]
            cur.execute("UPDATE child_bots SET fampay_endpoint=?, fampay_apikey=? WHERE bot_id=?", (parts[0], parts[1], t_id))
        else:
            cur.execute("UPDATE child_bots SET fampay_apikey=? WHERE bot_id=?", (txt, t_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, "✅ Payment Gateway API settings saved!", reply_markup=get_owner_panel(is_master))

    elif st_data == "wait_supp_input":
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("UPDATE child_bots SET support_contact=? WHERE bot_id=?", (txt, t_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"✅ Support contact updated to: {txt}", reply_markup=get_owner_panel(is_master))

    elif st_data == "wait_add_bal":
        parts = txt.split()
        if len(parts) >= 2:
            t_uid, amt = int(parts[0]), float(parts[1])
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE bot_clients SET balance = balance + ? WHERE bot_id=? AND user_id=?", (amt, bot_id, t_uid))
            conn.commit()
            conn.close()
            bot.send_message(cid, f"✅ Added ₹{amt} to User {t_uid}", reply_markup=get_owner_panel(is_master))

    elif st_data == "wait_ded_bal":
        parts = txt.split()
        if len(parts) >= 2:
            t_uid, amt = int(parts[0]), float(parts[1])
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE bot_clients SET balance = MAX(0.0, balance - ?) WHERE bot_id=? AND user_id=?", (amt, bot_id, t_uid))
            conn.commit()
            conn.close()
            bot.send_message(cid, f"✅ Deducted ₹{amt} from User {t_uid}", reply_markup=get_owner_panel(is_master))

    elif st_data == "wait_ban_user":
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE bot_clients SET banned=1 WHERE bot_id=? AND user_id=?", (int(txt), bot_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"✅ User {txt} banned.", reply_markup=get_owner_panel(is_master))

    elif st_data == "wait_unban_user":
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE bot_clients SET banned=0 WHERE bot_id=? AND user_id=?", (int(txt), bot_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"✅ User {txt} unbanned.", reply_markup=get_owner_panel(is_master))

    elif st_data == "wait_log_chan":
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE child_bots SET log_channel=? WHERE bot_id=?", (txt, bot_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"✅ Log channel set to {txt}", reply_markup=get_owner_panel(is_master))

    elif st_data == "wait_force_sub":
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE child_bots SET force_channel=? WHERE bot_id=?", (txt, bot_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"✅ Force sub channel set to {txt}", reply_markup=get_owner_panel(is_master))

def run_child_bot_loop(bot_id, owner_id, token, bot_username, bot_name):
    while True:
        try:
            cbot = telebot.TeleBot(token, threaded=True)
            try:
                requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=True", timeout=5)
            except Exception:
                pass

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
                    "Boost Your Social Presence With Instant Delivery And Automated 24/7 Processing. 🚀\n\n"
                    "Press Continue To Open The Menu"
                )
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("▶️ CONTINUE", callback_data="u_continue_main"))
                cbot.send_message(msg.chat.id, welcome_screen, reply_markup=m)

            @cbot.message_handler(commands=['admin'])
            def c_admin(msg):
                if msg.from_user.id != owner_id and msg.from_user.id != SUPER_ADMIN_ID:
                    cbot.reply_to(msg, f"Access Denied.\nYour User ID: `{msg.from_user.id}`\nOwner ID: `{owner_id}`", parse_mode="Markdown")
                    return
                cbot.send_message(msg.chat.id, f"👑 Owner Panel\n\n🤖 @{bot_username}", reply_markup=get_owner_panel(is_master=False))

            @cbot.callback_query_handler(func=lambda c: True)
            def c_cbs(call):
                if call.data.startswith("a_") or call.data.startswith("adm_") or call.data.startswith("c_"):
                    if call.from_user.id != owner_id and call.from_user.id != SUPER_ADMIN_ID:
                        cbot.answer_callback_query(call.id, "Access Denied", show_alert=True)
                        return
                    handle_owner_callbacks(cbot, bot_id, call, is_master=False)
                else:
                    handle_user_callbacks(cbot, bot_id, call)

            @cbot.message_handler(func=lambda m: f"{bot_id}_{m.from_user.id}" in user_states and not m.text.startswith('/'))
            def c_txts(m):
                handle_text_inputs(cbot, bot_id, m, is_master=False)

            print(f"[CHILD BOT ONLINE] @{bot_username}")
            cbot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
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
                conn = get_db()
                cur = conn.cursor()
                cur.execute("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (0, ?, ?)",
                            (msg.from_user.id, msg.from_user.username or 'User'))
                conn.commit()
                conn.close()

                menu_text = (
                    "💎 MAIN MENU 💎 ~\n\n"
                    "╔══════════════════════╗\n"
                    "  ✨ 𝓦𝓔𝓛𝓒𝓞𝓜𝓔 ★ VIP ✨\n"
                    "  ❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                    "  🥶 Choose An Option Below 🎀\n"
                    "╚══════════════════════╝"
                )
                master_bot.send_message(msg.chat.id, menu_text, reply_markup=get_user_main_menu())

            @master_bot.message_handler(commands=['admin'])
            def m_admin(msg):
                if msg.from_user.id != SUPER_ADMIN_ID:
                    master_bot.reply_to(msg, f"Access Denied: Only Super Admin can access Master Admin Panel.\nYour User ID: `{msg.from_user.id}`\nConfigured Admin ID: `{SUPER_ADMIN_ID}`", parse_mode="Markdown")
                    return
                master_bot.send_message(msg.chat.id, "👑 MASTER BOT ADMIN PANEL\n\nFull control over Master services, website API sync, payment gateway, and child bots.", reply_markup=get_owner_panel(is_master=True))

            @master_bot.callback_query_handler(func=lambda c: True)
            def m_cbs(c):
                data = c.data
                uid = c.from_user.id
                cid = c.message.chat.id
                mid = c.message.message_id

                if data == "u_cyob" or data == "m_cyob":
                    cyob_box = (
                        "👑 CREATE YOUR OWN BOT ★ PRO\n\n"
                        "1️⃣ Open @BotFather\n"
                        "2️⃣ Send /newbot & follow steps\n"
                        "3️⃣ Copy Bot Token\n"
                        "4️⃣ Press Add Bot and paste it here\n\n"
                        "Your bot goes live instantly with your own profit margin!"
                    )
                    m = types.InlineKeyboardMarkup(row_width=2)
                    m.add(types.InlineKeyboardButton("💛 Your Bots", callback_data="m_mybots"), types.InlineKeyboardButton("➕ Add Bot", callback_data="m_add_bot"))
                    m.add(types.InlineKeyboardButton("🔙 Go Back", callback_data="u_back_main"))
                    try:
                        master_bot.edit_message_text(cyob_box, cid, mid, reply_markup=m)
                    except Exception:
                        master_bot.send_message(cid, cyob_box, reply_markup=m)

                elif data == "m_mybots":
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("SELECT bot_id, bot_username FROM child_bots WHERE owner_id=?", (uid,))
                    bots = cur.fetchall()
                    conn.close()
                    if not bots:
                        m = types.InlineKeyboardMarkup()
                        m.add(types.InlineKeyboardButton("➕ Add Bot", callback_data="m_add_bot"))
                        master_bot.edit_message_text("No active bots found. Click Add Bot to create one!", cid, mid, reply_markup=m)
                    else:
                        b = bots[0]
                        txt = f"👑 YOUR CLONED BOTS\n\n• 🟢 @{b['bot_username']} (ONLINE)"
                        m = types.InlineKeyboardMarkup(row_width=2)
                        m.add(types.InlineKeyboardButton("❌ Delete Bot", callback_data=f"m_del_{b['bot_id']}"))
                        m.add(types.InlineKeyboardButton("🔙 Back to CYOB", callback_data="m_cyob"))
                        master_bot.edit_message_text(txt, cid, mid, reply_markup=m)

                elif data.startswith("m_del_"):
                    bid = int(data.replace("m_del_", ""))
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute("DELETE FROM child_bots WHERE bot_id=?", (bid,))
                    conn.commit()
                    conn.close()
                    master_bot.answer_callback_query(c.id, "Bot Deleted Successfully!", show_alert=True)
                    m_start(c.message)

                elif data == "m_add_bot":
                    user_states[f"0_{uid}"] = "wait_token"
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("🛑 CANCEL", callback_data="m_cyob"))
                    master_bot.edit_message_text("🏆 SUBMIT TOKEN\n\nPaste or forward your Bot Token from @BotFather now:", cid, mid, reply_markup=m)

                elif data.startswith("a_") or data.startswith("adm_") or data.startswith("c_"):
                    if uid != SUPER_ADMIN_ID:
                        master_bot.answer_callback_query(c.id, "Access Denied", show_alert=True)
                        return
                    handle_owner_callbacks(master_bot, 0, c, is_master=True)

                else:
                    handle_user_callbacks(master_bot, 0, c)

            @master_bot.message_handler(func=lambda m: f"0_{m.from_user.id}" in user_states and not m.text.startswith('/'))
            def m_txts(msg):
                uid = msg.from_user.id
                cid = msg.chat.id
                key = f"0_{uid}"
                st_data = user_states.get(key)
                txt = msg.text.strip()

                if st_data == "wait_token":
                    user_states.pop(key, None)
                    v_msg = master_bot.send_message(cid, "🔄 Connecting your bot... Validating token...")
                    chk = requests.get(f"https://api.telegram.org/bot{txt}/getMe", timeout=10)
                    data = chk.json()
                    if not data.get("ok"):
                        master_bot.edit_message_text("❌ Invalid Bot Token! Please provide a valid token from BotFather.", cid, v_msg.message_id)
                        return

                    bot_user = data["result"]["username"]
                    bot_name = data["result"]["first_name"]
                    token_enc = cipher_suite.encrypt(txt.encode()).decode()

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

                    t = threading.Thread(target=run_child_bot_loop, args=(bot_id, uid, txt, bot_user, bot_name), daemon=True)
                    t.start()
                    bot_threads[txt] = t

                    live_text = f"🚀 BOT IS LIVE\n\n🤖 @{bot_user}\nSend /admin inside your bot to configure services and payment!"
                    m = types.InlineKeyboardMarkup()
                    m.add(types.InlineKeyboardButton("Open Bot", url=f"https://t.me/{bot_user}"))
                    master_bot.edit_message_text(live_text, cid, v_msg.message_id, reply_markup=m)
                else:
                    handle_text_inputs(master_bot, 0, msg, is_master=True)

            print("[MASTER BOT] Polling started...")
            master_is_running = True
            master_bot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
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
    time.sleep(10)
    while True:
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT bot_id, owner_id, bot_token_enc, bot_username, bot_name FROM child_bots WHERE status='active' AND bot_id != 0")
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
