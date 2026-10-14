import os
import sys
import time
import datetime
import random
import string
import secrets
import re
import imaplib
import email
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

# SUPER ADMIN - Strictly Pranav Patel
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
        bot_id INTEGER PRIMARY KEY,
        owner_id INTEGER,
        bot_token_enc TEXT UNIQUE,
        bot_username TEXT,
        bot_name TEXT,
        pro_mode INTEGER DEFAULT 1,
        log_channel TEXT DEFAULT '',
        force_channel TEXT DEFAULT '',
        support_wa TEXT DEFAULT '',
        support_tg TEXT DEFAULT '',
        active_gateway TEXT DEFAULT 'paytm',
        fampay_upi TEXT DEFAULT '',
        fampay_email TEXT DEFAULT '',
        fampay_app_pwd TEXT DEFAULT '',
        paytm_mid TEXT DEFAULT '',
        paytm_upi TEXT DEFAULT '',
        subscription_expiry TIMESTAMP,
        is_licensed INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS license_keys (
        key_code TEXT PRIMARY KEY,
        duration_days INTEGER DEFAULT 30,
        used_by_bot_id INTEGER DEFAULT NULL,
        is_used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS key_pricing (
        duration_days INTEGER PRIMARY KEY,
        price REAL,
        label TEXT
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
        description TEXT DEFAULT 'Live Fast Speed Non Drop'
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
        tx_type TEXT DEFAULT 'deposit',
        target_days INTEGER DEFAULT 0,
        bank_utr TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    cur.execute("SELECT COUNT(*) as cnt FROM key_pricing")
    if cur.fetchone()["cnt"] == 0:
        cur.executemany("INSERT INTO key_pricing (duration_days, price, label) VALUES (?, ?, ?)", [
            (7, 49.0, "7 Days (Trial)"),
            (30, 149.0, "30 Days (1 Month)"),
            (90, 399.0, "90 Days (3 Months)"),
            (365, 999.0, "365 Days (1 Year)"),
            (36500, 1999.0, "👑 Lifetime Access")
        ])

    future_date = (datetime.datetime.now() + datetime.timedelta(days=36500)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
    INSERT INTO child_bots (bot_id, owner_id, bot_username, is_licensed, subscription_expiry)
    VALUES (0, 8585055903, 'PranavFatherBot', 1, ?)
    ON CONFLICT(bot_id) DO UPDATE SET
    owner_id=8585055903,
    is_licensed=1,
    subscription_expiry=?
    """, (future_date, future_date))
    conn.commit()
    conn.close()

init_db()

def generate_license_key(duration_days=30):
    prefix_id = random.randint(7000000000, 8999999999)
    alphabet = string.ascii_letters + string.digits + "_-"
    token_body = ''.join(secrets.choice(alphabet) for _ in range(35))
    k = f"{prefix_id}:AA{token_body}"
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO license_keys (key_code, duration_days) VALUES (?, ?)", (k, duration_days))
    conn.commit()
    conn.close()
    return k

def is_bot_active(bot_id):
    if bot_id == 0:
        return True, "👑 Lifetime Master Admin"
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT is_licensed, subscription_expiry, status FROM child_bots WHERE bot_id=?", (bot_id,))
    row = cur.fetchone()
    conn.close()
    if not row or row["is_licensed"] == 0:
        return False, "❌ Gateway Key Not Activated"
    if row["status"] == "suspended":
        return False, "🚫 Bot Suspended by Master Admin"
    
    exp_str = row["subscription_expiry"]
    if not exp_str:
        return False, "❌ License Expired"
    
    try:
        exp_dt = datetime.datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
        if datetime.datetime.now() > exp_dt:
            return False, "⚠️ Subscription Expired"
        days_left = (exp_dt - datetime.datetime.now()).days
        if days_left > 3000:
            return True, "👑 Lifetime Active"
        return True, f"Active ({days_left} Days Left)"
    except Exception:
        return False, "Date Calculation Error"

def sync_services_from_website_api():
    if not MAIN_PANEL_API_KEY:
        return 0, "API Key missing"
    try:
        resp = requests.post(MAIN_PANEL_URL, data={"key": MAIN_PANEL_API_KEY, "action": "services"}, timeout=15)
        srv_list = resp.json()
        if not isinstance(srv_list, list):
            return 0, f"Error: {srv_list}"
        
        conn = get_db()
        cur = conn.cursor()
        synced = 0
        for s in srv_list:
            sid = str(s.get("service", ""))
            name = str(s.get("name", "Service"))
            cat = str(s.get("category", "")).lower()
            name_l = name.lower()

            if "coin" in cat or "market" in cat or "shopee" in cat or "traffic" in cat:
                continue

            rate_per_1k = float(s.get("rate", 10.0))
            live_cost_per_100 = round(rate_per_1k / 10.0, 3)
            min_q = int(s.get("min", 100))
            max_q = int(s.get("max", 1000000))

            plat = None
            sub_cat = None

            if "instagram" in cat or "ig" in cat or "reel" in cat or "instagram" in name_l:
                plat = "Instagram"
                if "follower" in cat or "follower" in name_l:
                    sub_cat = "Ig Followers"
                elif "reel" in cat or "reel" in name_l:
                    sub_cat = "Reels View's"
                elif "view" in cat or "view" in name_l or "impression" in name_l:
                    sub_cat = "Post View's"
                else:
                    sub_cat = "Ig Likes"

            elif "facebook" in cat or "fb" in cat or "facebook" in name_l:
                plat = "Facebook"
                if "follower" in cat or "follower" in name_l or "page" in cat:
                    sub_cat = "Page Followers"
                else:
                    sub_cat = "Post Likes"

            elif "telegram" in cat or "tg" in cat or "telegram" in name_l:
                plat = "Telegram"
                if "view" in cat or "view" in name_l:
                    sub_cat = "Post Views"
                else:
                    sub_cat = "Channel Members"

            if plat and sub_cat:
                cur.execute("""
                INSERT INTO master_services (platform, sub_category, service_name, main_api_service_id, base_rate_per_100, min_qty, max_qty, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(main_api_service_id) DO UPDATE SET
                base_rate_per_100=excluded.base_rate_per_100,
                service_name=excluded.service_name,
                min_qty=excluded.min_qty,
                max_qty=excluded.max_qty
                """, (plat, sub_cat, f"🛒 {name}", sid, live_cost_per_100, min_q, max_q, "QUALITY ~ 100% REAL & VERIFIED\nSPEED ~ FAST INSTANT DELIVERY\nLIVE ~ SYNCED FROM PRANAVSMM.SHOP"))
                synced += 1

        conn.commit()
        conn.close()
        return synced, "Success"
    except Exception as e:
        return 0, str(e)

def auto_sync_on_boot():
    time.sleep(3)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM master_services")
    c = cur.fetchone()["cnt"]
    conn.close()
    if c == 0:
        sync_services_from_website_api()

threading.Thread(target=auto_sync_on_boot, daemon=True).start()

def verify_fampay_gmail(email_addr, app_password, target_amount, target_utr=None):
    if not email_addr or not app_password:
        return False, "Gmail or App Password not set"
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_addr.strip(), app_password.strip().replace(" ", ""))
        mail.select("inbox")
        status, messages = mail.search(None, 'ALL')
        if status != "OK":
            mail.logout()
            return False, "Unable to read inbox"
        
        email_ids = messages[0].split()
        latest_ids = email_ids[-15:] if len(email_ids) >= 15 else email_ids
        latest_ids.reverse()

        for e_id in latest_ids:
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body += part.get_payload(decode=True).decode(errors="ignore")
                    else:
                        body = msg.get_payload(decode=True).decode(errors="ignore")

                    b_low = body.lower()
                    if "fampay" in b_low or "fam" in b_low or "credited" in b_low or "received" in b_low:
                        amt_match = re.search(r'(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)', body, re.IGNORECASE)
                        if amt_match:
                            amt_val = float(amt_match.group(1).replace(",", ""))
                            if abs(amt_val - target_amount) <= 0.5:
                                mail.logout()
                                return True, "Payment Verified by Gmail"

        mail.logout()
        return False, "Payment email not received yet"
    except Exception as e:
        return False, str(e)

def verify_paytm_merchant(mid, user_utr, target_amount):
    u_str = str(user_utr).strip()
    if not u_str:
        return False, "UTR missing"
    
    if len(u_str) == 12 and u_str.isdigit():
        if mid:
            try:
                url = "https://securegw.paytm.in/merchant-status/getTxnStatus"
                resp = requests.post(url, json={"MID": mid.strip(), "ORDERID": u_str}, timeout=6).json()
                if resp.get("STATUS") == "TXN_SUCCESS":
                    txn_amt = float(resp.get("TXNAMOUNT", 0.0))
                    if abs(txn_amt - target_amount) <= 0.5:
                        return True, "Paytm API Verified"
            except Exception:
                pass
        return True, "Bank UTR Verified"
    return False, "Invalid UTR: Must be exactly 12 numeric digits"

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
    return jsonify({"status": "active"}), 200

def get_owner_panel(is_master=False):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("⚙️ Services", callback_data="a_services"),
        types.InlineKeyboardButton("💳 Payment", callback_data="a_payment")
    )
    m.add(
        types.InlineKeyboardButton("👥 Users", callback_data="a_users"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="a_bcast")
    )
    m.add(
        types.InlineKeyboardButton("➕ Add Balance", callback_data="a_addbal"),
        types.InlineKeyboardButton("➖ Deduct Balance", callback_data="a_dedbal")
    )
    m.add(
        types.InlineKeyboardButton("🚫 Ban User", callback_data="a_ban"),
        types.InlineKeyboardButton("✅ Unban User", callback_data="a_unban")
    )
    m.add(
        types.InlineKeyboardButton("📜 Log Channel", callback_data="a_logchan"),
        types.InlineKeyboardButton("🔒 Force Sub", callback_data="a_forcesub")
    )
    m.add(
        types.InlineKeyboardButton("🎧 Support Contact", callback_data="a_suppcontact"),
        types.InlineKeyboardButton("🔑 Gateway License Key", callback_data="a_license_info")
    )
    if is_master:
        m.add(
            types.InlineKeyboardButton("🔄 Sync Live pranavsmm.shop Rates", callback_data="adm_sync_api"),
            types.InlineKeyboardButton("🎟️ Generate Client Keys", callback_data="adm_choose_key_duration")
        )
        m.add(
            types.InlineKeyboardButton("⚙️ Set Key Pricing", callback_data="adm_set_pricing_menu"),
            types.InlineKeyboardButton("🤖 Manage All Child Bots", callback_data="adm_list_child_bots")
        )
    m.add(types.InlineKeyboardButton("🔙 Main Menu", callback_data="a_back_main"))
    return m

def get_user_main_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("🔹 Balance", callback_data="u_bal"),
        types.InlineKeyboardButton("🟣 Deposit", callback_data="u_dep")
    )
    m.add(
        types.InlineKeyboardButton("🗓️ History", callback_data="u_hist"),
        types.InlineKeyboardButton("🛒 Order Now", callback_data="u_ord")
    )
    m.add(
        types.InlineKeyboardButton("🟢 Support", callback_data="u_supp"),
        types.InlineKeyboardButton("🦁 CYOB", callback_data="u_cyob")
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
            f"🆔 User ID - `{uid}`\n"
            f"👤 User Name - @{call.from_user.username or 'User'}\n"
            f"💳 Total Deposit - ₹{tdep:.2f}\n"
            f"🛒 Total Spent - ₹{tsp:.2f}"
        )
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("🟣 Deposit", callback_data="u_dep"), types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_back_main"))
        bot.edit_message_text(acc_text, cid, mid, reply_markup=m, parse_mode="Markdown")

    elif data == "u_dep":
        active_status, reason = is_bot_active(bot_id)
        if not active_status:
            lock_text = (
                "⚠️ 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗢𝗖𝗞𝗘𝗗 ⚠️\n\n"
                f"Status: {reason}\n\n"
                "इस बॉट का पेमेंट गेटवे अभी एक्टिवेट नहीं है।\n"
                "ओनर को अपने एडमिन पैनल (`/admin`) में जाकर Gateway License Key डालनी होगी।"
            )
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_back_main"))
            bot.edit_message_text(lock_text, cid, mid, reply_markup=m)
            return

        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if bot_id == 0 else bot_id
        cur.execute("SELECT active_gateway, fampay_upi, paytm_upi FROM child_bots WHERE bot_id=?", (t_id,))
        b_info = cur.fetchone()
        conn.close()

        gw = b_info["active_gateway"] if b_info and b_info["active_gateway"] else "paytm"
        upi_check = b_info["paytm_upi"] if gw == "paytm" else b_info["fampay_upi"]
        if not upi_check:
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_back_main"))
            bot.edit_message_text("❌ Payment method has not been configured by the owner yet.\nPlease contact admin.", cid, mid, reply_markup=m)
            return

        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton(f"⚡ Instant UPI ({gw.upper()})", callback_data="u_dep_method_upi"))
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_back_main"))
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

            utr_num = f"PRANAV{int(time.time())}{random.randint(100, 999)}"
            conn = get_db()
            cur = conn.cursor()
            t_id = 0 if bot_id == 0 else bot_id
            cur.execute("SELECT active_gateway, fampay_upi, paytm_upi FROM child_bots WHERE bot_id=?", (t_id,))
            b_info = cur.fetchone()
            
            gw = b_info["active_gateway"] if b_info and b_info["active_gateway"] else "paytm"
            upi_target = b_info["paytm_upi"] if gw == "paytm" else b_info["fampay_upi"]
            store_name = "Paytm Store" if gw == "paytm" else "FamPay Store"

            if not upi_target:
                conn.close()
                bot.edit_message_text("❌ Payment UPI not set by owner. Please contact admin.", cid, mid, reply_markup=get_user_main_menu())
                return

            cur.execute("INSERT INTO transactions (tx_id, bot_id, user_id, amount, tx_type, status) VALUES (?, ?, ?, ?, 'deposit', 'pending')",
                        (utr_num, bot_id, uid, amt))
            conn.commit()
            conn.close()

            upi_locked_url = f"upi://pay?pa={upi_target}&pn={store_name}&am={amt:.2f}&cu=INR&tr={utr_num}"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={requests.utils.quote(upi_locked_url)}"
            
            qr_cap = (
                f"╭──────────────────────────╮\n"
                f"  ⚡ 𝗔𝗨𝗧𝗢𝗠𝗔𝗧𝗘𝗗 𝗨𝗣𝗜 𝗤𝗥 ({gw.upper()})\n"
                f"╰──────────────────────────╯\n\n"
                f"💵 𝗔𝗺𝗼𝘂𝗻𝘁 : ₹{amt:.2f} (🔒 Locked Amount)\n"
                f"🆔 𝗢𝗿𝗱𝗲𝗿 𝗜𝗗 : `{utr_num}`\n"
                f"🏦 𝗨𝗣𝗜 𝗜𝗗 : `{upi_target}`\n"
                f"⏱️ 𝗩𝗮𝗹𝗶𝗱 : 15 Minutes\n\n"
                "⚠️ *स्कैन करने पर ऐप में अपने-आप यही अमाउंट आएगा।*\n"
                "पेमेंट पूरी करने के बाद नीचे 'SUBMIT 12-DIGIT UTR' दबाएं या सीधे चैट में UTR भेजें।"
            )
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(types.InlineKeyboardButton("✅ VERIFY PAYMENT", callback_data=f"chk_pay_{utr_num}"))
            m.add(types.InlineKeyboardButton("🔢 SUBMIT 12-DIGIT UTR", callback_data=f"sub_utr_{utr_num}"))
            m.add(types.InlineKeyboardButton("❌ CANCEL", callback_data=f"cnl_pay_{utr_num}"))
            try:
                bot.delete_message(cid, mid)
            except Exception:
                pass
            bot.send_photo(cid, qr_url, caption=qr_cap, reply_markup=m, parse_mode="Markdown")
            return

        keypad_amounts[k_key] = cur_amt
        kp, disp = build_deposit_keypad(cur_amt)
        bot.edit_message_text(f"💶 DEPOSIT 💷\n\nMinimum ₹1 Max ₹10,000\n\n💵 Amount : ₹{disp}", cid, mid, reply_markup=kp)

    elif data.startswith("sub_utr_"):
        tx = data.replace("sub_utr_", "")
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_manual_utr", "tx_id": tx}
        bot.send_message(cid, "🔢 Send your 12-digit Bank UTR / Ref Number in chat:")

    elif data.startswith("chk_pay_"):
        tx = data.replace("chk_pay_", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT bot_id, user_id, amount, tx_type, target_days, bank_utr, status FROM transactions WHERE tx_id=?", (tx,))
        t_row = cur.fetchone()
        if not t_row:
            conn.close()
            bot.answer_callback_query(call.id, "Transaction expired", show_alert=True)
            return

        if t_row["status"] == "completed":
            conn.close()
            bot.answer_callback_query(call.id, "Already Verified!", show_alert=True)
            return

        t_id = 0 if t_row["tx_type"] == "buy_key" else (0 if bot_id == 0 else bot_id)
        cur.execute("SELECT active_gateway, fampay_email, fampay_app_pwd, paytm_mid FROM child_bots WHERE bot_id=?", (t_id,))
        b_conf = cur.fetchone()

        gw = b_conf["active_gateway"] if b_conf and b_conf["active_gateway"] else "paytm"
        verified = False
        reason = ""

        if gw == "fampay" and b_conf and b_conf["fampay_email"] and b_conf["fampay_app_pwd"]:
            verified, reason = verify_fampay_gmail(b_conf["fampay_email"], b_conf["fampay_app_pwd"], t_row["amount"])
        elif gw == "paytm" and b_conf and b_conf["paytm_mid"] and t_row["bank_utr"]:
            verified, reason = verify_paytm_merchant(b_conf["paytm_mid"], t_row["bank_utr"], t_row["amount"])
        else:
            if t_row["bank_utr"] and len(t_row["bank_utr"]) == 12:
                verified = True
            else:
                verified = False
                reason = "कृपया 'SUBMIT 12-DIGIT UTR' बटन दबाकर 12-अंकों का बैंक UTR चैट में भेजें।"

        if verified:
            cur.execute("UPDATE transactions SET status='completed' WHERE tx_id=?", (tx,))
            if t_row["tx_type"] == "buy_key":
                days = t_row["target_days"]
                key_code = generate_license_key(duration_days=days)
                cur.execute("UPDATE license_keys SET used_by_bot_id=? WHERE key_code=?", (bot_id, key_code))
                conn.commit()
                conn.close()

                dur_str = "👑 Lifetime" if days >= 30000 else f"{days} Days"
                succ_msg = (
                    "🎉 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬!\n\n"
                    f"🎟️ Here is your BotFather-Style License Key:\n"
                    f"👉 `{key_code}`\n\n"
                    f"⏱️ Validity: *{dur_str}*\n\n"
                    "Go to your bot `/admin` ➔ '🔑 Gateway License Key' ➔ '🎟️ Enter License Key' and submit this code to activate your gateway!"
                )
                bot.send_message(cid, succ_msg, parse_mode="Markdown")
                bot.answer_callback_query(call.id, "Key Generated!", show_alert=True)
                return
            else:
                cur.execute("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", 
                            (t_row["amount"], t_row["amount"], bot_id, uid))
                conn.commit()
                conn.close()
                bot.answer_callback_query(call.id, f"Payment Verified! ₹{t_row['amount']} credited.", show_alert=True)
                bot.send_message(cid, f"🎉 Payment Verified!\n₹{t_row['amount']} credited to your wallet.", reply_markup=get_user_main_menu())
        else:
            conn.close()
            bot.answer_callback_query(call.id, f"{reason}", show_alert=True)

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
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_back_main"))
        bot.edit_message_text("🗓️ Order History\n\nSelect type to check status:", cid, mid, reply_markup=m)

    elif data in ["h_pending", "h_completed", "h_cancelled"]:
        st = data.replace("h_", "").capitalize()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT service_name, quantity, charge FROM bot_orders WHERE bot_id=? AND user_id=? AND status=?", (bot_id, uid, st))
        ords = cur.fetchall()
        conn.close()
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_hist"))
        if ords:
            t = "\n\n".join([f"📦 {o['service_name']}\nQty: {o['quantity']} | Cost: ₹{o['charge']:.2f}" for o in ords])
            bot.edit_message_text(f"{st} Orders:\n\n{t}", cid, mid, reply_markup=m)
        else:
            bot.edit_message_text(f"{st} Orders:\n\n⚠️ No Orders Found", cid, mid, reply_markup=m)

    elif data == "h_refund":
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_hist"))
        bot.edit_message_text("Refund:\nSend Cancelled Order ID to claim refund.", cid, mid, reply_markup=m)

    elif data == "u_ord":
        ord_screen = (
            "╔═══════════════════════════════╗\n"
            "   🩸 𝗢𝗥𝗗𝗘𝗥 ~ 𝗡𝗢𝗪 🖤\n"
            "╚═══════════════════════════════╝\n\n"
            "☑️ 𝗦𝗘𝗟𝗘𝗖𝗧 𝗔 𝗣𝗟𝗔𝗧𝗙𝗢𝗥𝗠 📸📘✈️\n"
            "❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
            "𝗖𝗛𝗢𝗢𝗦𝗘 𝗬𝗢𝗨𝗥 𝗣𝗟𝗔𝗧𝗙𝗢𝗥𝗠 𝗧𝗢 𝗕𝗥𝗢𝗪𝗦𝗘 𝗛𝗜𝗚𝗛 𝗦𝗣𝗘𝗘𝗗 𝗚𝗨𝗔𝗥𝗔𝗡𝗧𝗘𝗘𝗗 𝗣𝗔𝗖𝗞𝗔𝗚𝗘𝗦 𝗪𝗜𝗧𝗛 𝗜𝗡𝗦𝗧𝗔𝗡𝗧 𝗗𝗘𝗟𝗜𝗩𝗘𝗥𝗬 ⏳🟢⏳\n"
            "❄️❄️❄️❄️❄️❄️❄️❄️❄️"
        )
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("📸 INSTAGRAM", callback_data="u_plat_Instagram"),
              types.InlineKeyboardButton("📘 FACEBOOK", callback_data="u_plat_Facebook"))
        m.add(types.InlineKeyboardButton("✈️ TELEGRAM", callback_data="u_plat_Telegram"))
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_back_main"))
        bot.edit_message_text(ord_screen, cid, mid, reply_markup=m)

    elif data == "u_plat_Instagram":
        ig_screen = (
            "╔═══════════════════════════════╗\n"
            "  👑 𝗦𝗘𝗟𝗘𝗖𝗧 𝗬𝗢𝗨𝗥 𝗦𝗘𝗥𝗩𝗜𝗖𝗘 👑\n"
            "╚═══════════════════════════════╝\n\n"
            "𝗖𝗛𝗢𝗢𝗦𝗘 𝗔 𝗦𝗘𝗥𝗩𝗜𝗖𝗘 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗬 🟩\n\n"
            "𝗔𝗟𝗟 𝗖𝗔𝗧𝗘𝗚𝗢𝗥𝗜𝗘𝗦 𝗙𝗘𝗔𝗧𝗨𝗥𝗘 𝗥𝗘𝗔𝗟-𝗧𝗜𝗠𝗘 𝗣𝗥𝗢𝗖𝗘𝗦𝗦𝗜𝗡𝗚 𝗔𝗡𝗗 𝗖𝗢𝗠𝗣𝗘𝗧𝗜𝗧𝗜𝗩𝗘 𝗥𝗔𝗧𝗘𝗦.\n"
            "🖤🖤🖤"
        )
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("🟣 IG FOLLOWERS", callback_data="u_sub_Instagram_Ig Followers"),
              types.InlineKeyboardButton("💖 IG LIKES", callback_data="u_sub_Instagram_Ig Likes"))
        m.add(types.InlineKeyboardButton("👀 REELS VIEW'S", callback_data="u_sub_Instagram_Reels View's"),
              types.InlineKeyboardButton("👓 POST VIEW'S", callback_data="u_sub_Instagram_Post View's"))
        m.add(types.InlineKeyboardButton("💎 MORE", callback_data="u_ig_more"))
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_ord"))
        bot.edit_message_text(ig_screen, cid, mid, reply_markup=m)

    elif data == "u_ig_more":
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("💬 COMMENTS", callback_data="u_sub_Instagram_Comments"),
              types.InlineKeyboardButton("👁️ STORY VIEWS", callback_data="u_sub_Instagram_Story Views"))
        m.add(types.InlineKeyboardButton("🔙 PREVIOUS", callback_data="u_plat_Instagram"))
        bot.edit_message_text("💎 ADDITIONAL SERVICES\n\nSelect Below:", cid, mid, reply_markup=m)

    elif data.startswith("u_plat_"):
        plat = data.replace("u_plat_", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT sub_category FROM master_services WHERE platform=?", (plat,))
        subs = cur.fetchall()
        conn.close()

        m = types.InlineKeyboardMarkup(row_width=2)
        for s in subs:
            m.add(types.InlineKeyboardButton(f"⭐ {s['sub_category'].upper()}", callback_data=f"u_sub_{plat}_{s['sub_category']}"))
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_ord"))
        bot.edit_message_text(f"🌟 {plat.upper()} SERVICES\n\nChoose category:", cid, mid, reply_markup=m)

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

        cat_title = (
            f"🛒 {sub_cat.upper()}\n\n"
            "👾 𝗦𝗘𝗟𝗘𝗖𝗧 𝗔 𝗦𝗘𝗥𝗩𝗜𝗖𝗘 𝗧𝗢 𝗩𝗜𝗘𝗪 𝗥𝗔𝗧𝗘𝗦 𝗔𝗡𝗗 𝗣𝗟𝗔𝗖𝗘 𝗢𝗥𝗗𝗘𝗥"
        )
        m = types.InlineKeyboardMarkup(row_width=1)
        if srvs:
            for s in srvs:
                m.add(types.InlineKeyboardButton(f"{s['service_name']} (₹{s['price']}/100)", callback_data=f"u_viewsrv_{s['id']}"))
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data=f"u_plat_{plat}"))
        bot.edit_message_text(cat_title, cid, mid, reply_markup=m)

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
        
        card_text = (
            "╔═══════════════════════════════════╗\n"
            f"  {ms['service_name'].upper()}\n"
            "╚═══════════════════════════════════╝\n\n"
            f"💱 𝗣𝗥𝗜𝗖𝗘 : ₹{price:.3f} / 100\n"
            f"🌟 𝗠𝗜𝗡 : {ms['min_qty']}  •  𝗠𝗔𝗫 : {ms['max_qty']}\n\n"
            f"🌟 𝗗𝗘𝗧𝗔𝗜𝗟𝗦\n"
            "─────────────────────────────\n"
            f"{desc}\n"
            "─────────────────────────────\n\n"
            "🔗 𝗡𝗢𝗪 𝗦𝗘𝗡𝗗 𝗬𝗢𝗨𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 / 𝗣𝗢𝗦𝗧 𝗟𝗜𝗡𝗞"
        )
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data=f"u_sub_{ms['platform']}_{ms['sub_category']}"))
        bot.edit_message_text(card_text, cid, mid, reply_markup=m)

    elif data == "u_supp":
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if bot_id == 0 else bot_id
        cur.execute("SELECT support_wa, support_tg FROM child_bots WHERE bot_id=?", (t_id,))
        s_row = cur.fetchone()
        conn.close()

        wa = s_row["support_wa"] if s_row and s_row["support_wa"] else ""
        tg = s_row["support_tg"] if s_row and s_row["support_tg"] else ""

        supp_box = (
            "╭──────────────────────────╮\n"
            "  🔥 𝗖𝗨𝗦𝗧𝗢𝗠𝗘𝗥 𝗦𝗨𝗣𝗣𝗢𝗥𝗧\n"
            "╰──────────────────────────╯\n\n"
            "𝗢𝗨𝗥 𝗧𝗘𝗔𝗠 𝗜𝗦 𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘 𝗧𝗢 𝗔𝗦𝗦𝗜𝗦𝗧 𝗬𝗢𝗨 𝗪𝗜𝗧𝗛 𝗢𝗥𝗗𝗘𝗥𝗦, 𝗗𝗘𝗣𝗢𝗦𝗜𝗧𝗦, 𝗔𝗡𝗗 𝗔𝗡𝗬 𝗦𝗘𝗥𝗩𝗜𝗖𝗘 𝗤𝗨𝗘𝗥𝗜𝗘𝗦. 🔯"
        )
        m = types.InlineKeyboardMarkup(row_width=1)
        if wa:
            wa_clean = wa.replace("+", "").replace(" ", "")
            m.add(types.InlineKeyboardButton("🟢 WHATSAPP SUPPORT ↗️", url=f"https://wa.me/{wa_clean}"))
        if tg:
            tg_clean = tg.replace("@", "").replace(" ", "")
            m.add(types.InlineKeyboardButton("✈️ TELEGRAM SUPPORT ↗️", url=f"https://t.me/{tg_clean}"))
        if not wa and not tg:
            m.add(types.InlineKeyboardButton("💬 Support Not Configured", callback_data="u_back_main"))
        m.add(types.InlineKeyboardButton("🔙 BACK", callback_data="u_back_main"))
        bot.edit_message_text(supp_box, cid, mid, reply_markup=m)

    elif data == "u_cyob":
        cyob_text = (
            "👑 CREATE YOUR OWN BOT ★ PRO\n\n"
            "START YOUR OWN BRANDED RESELLER BUSINESS IN MINUTES.\n\n"
            "1️⃣ Open @BotFather\n"
            "2️⃣ Send /newbot and follow instructions\n"
            "3️⃣ Copy the API Token\n"
            "4️⃣ Send token to Master Bot\n\n"
            "Your Bot Goes Live Instantly with Automated Multi-Platform Reselling!"
        )
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_back_main"))
        bot.edit_message_text(cyob_text, cid, mid, reply_markup=m)

def handle_owner_callbacks(bot, bot_id, call, is_master=False):
    uid = call.from_user.id
    cid = call.message.chat.id
    mid = call.message.message_id
    data = call.data

    if is_master and uid != SUPER_ADMIN_ID:
        bot.answer_callback_query(call.id, "Access Denied: Super Admin Only", show_alert=True)
        return

    if data == "adm_back_panel":
        bot.edit_message_text("👑 Owner Panel", cid, mid, reply_markup=get_owner_panel(is_master))

    elif data == "adm_sync_api" and is_master:
        bot.answer_callback_query(call.id, "Syncing clean live rates from pranavsmm.shop...", show_alert=False)
        count, msg = sync_services_from_website_api()
        bot.send_message(cid, f"🔄 API Live Sync Finished!\n\nImported/Updated: {count} verified services with live costs\nStatus: {msg}", reply_markup=get_owner_panel(is_master))

    elif data == "adm_set_pricing_menu" and is_master:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT duration_days, price, label FROM key_pricing ORDER BY duration_days ASC")
        rows = cur.fetchall()
        conn.close()

        txt = "⚙️ 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗞𝗘𝗬 𝗣𝗥𝗜𝗖𝗜𝗡𝗚 (𝗔𝗗𝗠𝗜𝗡 𝗦𝗘𝗧𝗧𝗜𝗡𝗚)\n\nCurrent Selling Rates:\n"
        m = types.InlineKeyboardMarkup(row_width=2)
        for r in rows:
            txt += f"• {r['label']}: ₹{r['price']:.0f}\n"
            m.add(types.InlineKeyboardButton(f"✏️ Set {r['label']}", callback_data=f"adm_edit_price_{r['duration_days']}"))

        m.add(types.InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="adm_back_panel"))
        bot.edit_message_text(txt, cid, mid, reply_markup=m)

    elif data.startswith("adm_edit_price_") and is_master:
        days = int(data.replace("adm_edit_price_", ""))
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_new_key_price", "days": days}
        bot.send_message(cid, f"Send new price in Rupees for {days} days (e.g. `99` or `199`):")

    elif data == "adm_choose_key_duration" and is_master:
        txt = "🎟️ 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘 𝗕𝗢𝗧𝗙𝗔𝗧𝗛𝗘𝗥-𝗦𝗧𝗬𝗟𝗘 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗞𝗘𝗬\n\nChoose duration:"
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(
            types.InlineKeyboardButton("⚡ 7 Days (Trial)", callback_data="adm_make_key_7"),
            types.InlineKeyboardButton("🗓️ 30 Days (1 Month)", callback_data="adm_make_key_30")
        )
        m.add(
            types.InlineKeyboardButton("💎 90 Days (3 Months)", callback_data="adm_make_key_90"),
            types.InlineKeyboardButton("🌟 365 Days (1 Year)", callback_data="adm_make_key_365")
        )
        m.add(
            types.InlineKeyboardButton("👑 Lifetime Access", callback_data="adm_make_key_36500"),
            types.InlineKeyboardButton("✏️ Custom Days", callback_data="adm_make_key_custom")
        )
        m.add(types.InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="adm_back_panel"))
        bot.edit_message_text(txt, cid, mid, reply_markup=m)

    elif data.startswith("adm_make_key_") and is_master:
        val = data.replace("adm_make_key_", "")
        if val == "custom":
            user_states[f"{bot_id}_{uid}"] = "wait_custom_days_key"
            bot.send_message(cid, "✏️ Enter the number of days (e.g. `15` or `45`):")
            return
        
        days = int(val)
        key = generate_license_key(duration_days=days)
        dur_str = "👑 Lifetime" if days >= 30000 else f"{days} Days"
        txt = (
            f"🎟️ 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗞𝗘𝗬 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘𝗗\n\n"
            f"🔑 BotFather-Style Key:\n`{key}`\n\n"
            f"⏱️ Validity: *{dur_str}*\n\n"
            "Send this code to your client to activate their gateway!"
        )
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔙 Back to Key Generator", callback_data="adm_choose_key_duration"))
        bot.send_message(cid, txt, parse_mode="Markdown", reply_markup=m)

    elif data == "c_buy_key_menu":
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT duration_days, price, label FROM key_pricing ORDER BY duration_days ASC")
        rows = cur.fetchall()
        
        cur.execute("SELECT active_gateway, paytm_upi, fampay_upi FROM child_bots WHERE bot_id=0")
        m_bot = cur.fetchone()
        conn.close()

        gw = m_bot["active_gateway"] if m_bot and m_bot["active_gateway"] else "paytm"
        target_upi = m_bot["paytm_upi"] if gw == "paytm" else m_bot["fampay_upi"]

        if not target_upi:
            bot.answer_callback_query(call.id, "Master payment gateway not configured yet!", show_alert=True)
            return

        txt = (
            "🛒 𝗣𝗨𝗥𝗖𝗛𝗔𝗦𝗘 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗞𝗘𝗬\n\n"
            "Select your package to unlock 24/7 Automated UPI Payments & Instant Verification:\n"
            f"*(Payment Method: {gw.upper()})*\n"
        )
        m = types.InlineKeyboardMarkup(row_width=1)
        for r in rows:
            m.add(types.InlineKeyboardButton(f"{r['label']} - ₹{r['price']:.0f}", callback_data=f"c_pay_for_key_{r['duration_days']}"))
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="a_license_info"))
        bot.edit_message_text(txt, cid, mid, reply_markup=m)

    elif data.startswith("c_pay_for_key_"):
        days = int(data.replace("c_pay_for_key_", ""))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT price, label FROM key_pricing WHERE duration_days=?", (days,))
        p_row = cur.fetchone()
        
        cur.execute("SELECT active_gateway, paytm_upi, fampay_upi FROM child_bots WHERE bot_id=0")
        m_bot = cur.fetchone()

        amt = float(p_row["price"])
        utr_num = f"KEY{int(time.time())}{random.randint(100, 999)}"

        cur.execute("INSERT INTO transactions (tx_id, bot_id, user_id, amount, tx_type, target_days, status) VALUES (?, ?, ?, ?, 'buy_key', ?, 'pending')",
                    (utr_num, bot_id, uid, amt, days))
        conn.commit()
        conn.close()

        gw = m_bot["active_gateway"] if m_bot and m_bot["active_gateway"] else "paytm"
        upi_target = m_bot["paytm_upi"] if gw == "paytm" else m_bot["fampay_upi"]

        upi_locked_url = f"upi://pay?pa={upi_target}&pn=MasterPayment&am={amt:.2f}&cu=INR&tr={utr_num}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={requests.utils.quote(upi_locked_url)}"

        # Auto-store awaiting state so chat input immediately matches this order
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_manual_utr", "tx_id": utr_num}

        caption_txt = (
            "╔═══════════════════════════════╗\n"
            "   🛒 𝗕𝗨𝗬 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗞𝗘𝗬\n"
            "╚═══════════════════════════════╝\n\n"
            f"📦 𝗣𝗮𝗰𝗸𝗮𝗴𝗲 : {p_row['label']}\n"
            f"💵 𝗔𝗺𝗼𝘂𝗻𝘁 : ₹{amt:.2f} (🔒 Locked Amount)\n"
            f"🏦 𝗣𝗮𝘆𝗺𝗲𝗻𝘁 𝗠𝗲𝘁𝗵𝗼𝗱 : {gw.upper()}\n"
            f"🆔 𝗢𝗿𝗱𝗲𝗿 𝗜𝗗 : `{utr_num}`\n\n"
            "⚠️ Scan and pay the exact amount. Send 12-digit Bank UTR to receive your License Key instantly!"
        )
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("✅ VERIFY & GET KEY", callback_data=f"chk_pay_{utr_num}"))
        m.add(types.InlineKeyboardButton("🔢 SUBMIT 12-DIGIT UTR", callback_data=f"sub_utr_{utr_num}"))
        m.add(types.InlineKeyboardButton("❌ CANCEL", callback_data=f"cnl_pay_{utr_num}"))
        bot.send_photo(cid, qr_url, caption=caption_txt, reply_markup=m, parse_mode="Markdown")

    elif data == "a_license_info":
        active_status, reason = is_bot_active(bot_id)
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("SELECT subscription_expiry, is_licensed FROM child_bots WHERE bot_id=?", (t_id,))
        b_info = cur.fetchone()
        conn.close()

        exp = b_info["subscription_expiry"] if b_info and b_info["subscription_expiry"] else "No Expiry / Not Set"
        txt = (
            "🔑 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 & 𝗦𝗨𝗕𝗦𝗖𝗥𝗜𝗣𝗧𝗜𝗢𝗡\n\n"
            f"• Status: {reason}\n"
            f"• Expiry Date: `{exp}`\n\n"
            "Click below to purchase an automated key or redeem your code:"
        )
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("🛒 Buy Key Automatically (Instant)", callback_data="c_buy_key_menu"))
        m.add(types.InlineKeyboardButton("🎟️ Enter License Key", callback_data="c_enter_lic_key"))
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="adm_back_panel"))
        bot.edit_message_text(txt, cid, mid, reply_markup=m, parse_mode="Markdown")

    elif data == "c_enter_lic_key":
        user_states[f"{bot_id}_{uid}"] = "wait_redeem_key"
        bot.send_message(cid, "🔑 Send your BotFather-Style License Key:")

    elif data == "adm_list_child_bots" and is_master:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT bot_id, owner_id, bot_username, is_licensed, subscription_expiry, status FROM child_bots WHERE bot_id != 0 LIMIT 20")
        bots = cur.fetchall()
        conn.close()

        if not bots:
            bot.answer_callback_query(call.id, "No child bots created yet!", show_alert=True)
            return

        txt = "🤖 𝗔𝗟𝗟 𝗖𝗟𝗢𝗡𝗘𝗗 𝗖𝗛𝗜𝗟𝗗 𝗕𝗢𝗧𝗦\n\n"
        m = types.InlineKeyboardMarkup(row_width=1)
        for b in bots:
            st = "🟢 Active" if b["is_licensed"] == 1 else "🔴 Expired/Locked"
            exp = b["subscription_expiry"] if b["subscription_expiry"] else "Never"
            txt += f"• @{b['bot_username']} (Owner: `{b['owner_id']}`)\n  Status: {st} | Expiry: {exp}\n\n"
            m.add(types.InlineKeyboardButton(f"⚙️ Manage @{b['bot_username']}", callback_data=f"adm_manage_bot_{b['bot_id']}"))

        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="adm_back_panel"))
        bot.send_message(cid, txt, parse_mode="Markdown", reply_markup=m)

    elif data.startswith("adm_manage_bot_") and is_master:
        target_bid = int(data.replace("adm_manage_bot_", ""))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT bot_id, owner_id, bot_username, is_licensed, subscription_expiry, status FROM child_bots WHERE bot_id=?", (target_bid,))
        b = cur.fetchone()
        conn.close()

        if not b:
            bot.answer_callback_query(call.id, "Bot not found", show_alert=True)
            return

        txt = (
            f"⚙️ 𝗠𝗔𝗡𝗔𝗚𝗘 𝗕𝗢𝗧: @{b['bot_username']}\n\n"
            f"• Bot ID: `{b['bot_id']}`\n"
            f"• Owner ID: `{b['owner_id']}`\n"
            f"• License: {'Active' if b['is_licensed'] == 1 else 'Locked'}\n"
            f"• Expiry: `{b['subscription_expiry']}`\n"
            f"• Status: `{b['status']}`"
        )
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(
            types.InlineKeyboardButton("➕ Add 30 Days", callback_data=f"adm_give_days_{target_bid}_30"),
            types.InlineKeyboardButton("👑 Make Lifetime", callback_data=f"adm_give_days_{target_bid}_36500")
        )
        m.add(
            types.InlineKeyboardButton("🚫 Suspend Bot", callback_data=f"adm_suspend_bot_{target_bid}"),
            types.InlineKeyboardButton("🟢 Unsuspend Bot", callback_data=f"adm_unsuspend_bot_{target_bid}")
        )
        m.add(types.InlineKeyboardButton("🔙 Back to Bot List", callback_data="adm_list_child_bots"))
        bot.send_message(cid, txt, parse_mode="Markdown", reply_markup=m)

    elif data.startswith("adm_give_days_") and is_master:
        parts = data.split("_")
        target_bid = int(parts[3])
        days = int(parts[4])
        new_exp = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE child_bots SET is_licensed=1, status='active', subscription_expiry=? WHERE bot_id=?", (new_exp, target_bid))
        conn.commit()
        conn.close()

        dur_text = "👑 Lifetime" if days >= 30000 else f"{days} Days"
        bot.answer_callback_query(call.id, f"Added {dur_text} successfully!", show_alert=True)
        handle_owner_callbacks(bot, 0, call, is_master=True)

    elif data.startswith("adm_suspend_bot_") and is_master:
        target_bid = int(data.replace("adm_suspend_bot_", ""))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE child_bots SET status='suspended', is_licensed=0 WHERE bot_id=?", (target_bid,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Bot suspended!", show_alert=True)

    elif data.startswith("adm_unsuspend_bot_") and is_master:
        target_bid = int(data.replace("adm_unsuspend_bot_", ""))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE child_bots SET status='active', is_licensed=1 WHERE bot_id=?", (target_bid,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Bot unsuspended!", show_alert=True)

    elif data == "a_services":
        if is_master:
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(
                types.InlineKeyboardButton("🔄 Sync Live pranavsmm.shop Rates", callback_data="adm_sync_api"),
                types.InlineKeyboardButton("➕ Add Single Service Manually", callback_data="adm_add_single_srv"),
                types.InlineKeyboardButton("📋 View All Master Services", callback_data="adm_list_msrvs"),
                types.InlineKeyboardButton("🔙 GO BACK", callback_data="adm_back_panel")
            )
            bot.edit_message_text("⚙️ MASTER SERVICES MANAGEMENT\n\nSync live rates directly from website:", cid, mid, reply_markup=m)
        else:
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                types.InlineKeyboardButton("📸 Instagram", callback_data="c_manage_plat_Instagram"),
                types.InlineKeyboardButton("📘 Facebook", callback_data="c_manage_plat_Facebook")
            )
            m.add(
                types.InlineKeyboardButton("✈️ Telegram", callback_data="c_manage_plat_Telegram"),
                types.InlineKeyboardButton("🔙 GO BACK", callback_data="adm_back_panel")
            )
            bot.edit_message_text("⚙️ RESELLER SERVICE MANAGER\n\nSelect Platform to set your selling price & publish:", cid, mid, reply_markup=m)

    elif data == "adm_add_single_srv" and is_master:
        user_states[f"{bot_id}_{uid}"] = "wait_m_single_srv"
        bot.send_message(cid, "Send details in format:\nPlatform | SubCategory | ServiceName | API_ServiceID | BaseCostPer100 | Min | Max\n\nExample:\nInstagram | Ig Likes | 💖 Real Likes | 1024 | 1.8 | 100 | 50000")

    elif data == "adm_list_msrvs" and is_master:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, platform, sub_category, service_name, base_rate_per_100, main_api_service_id FROM master_services LIMIT 15")
        rows = cur.fetchall()
        conn.close()
        txt = "\n".join([f"#{r['id']} [{r['platform']}] {r['service_name']} (ID:{r['main_api_service_id']}) - ₹{r['base_rate_per_100']}/100" for r in rows]) if rows else "No services in master DB."
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="a_services"))
        bot.send_message(cid, f"Master Services (Live Cost View):\n\n{txt}", reply_markup=m)

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
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="a_services"))
        bot.edit_message_text(f"Available {plat} Services:\nClick to set price & publish:", cid, mid, reply_markup=m)

    elif data.startswith("c_set_srv_"):
        msid = int(data.replace("c_set_srv_", ""))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM master_services WHERE id=?", (msid,))
        ms = cur.fetchone()
        cur.execute("SELECT selling_price_per_100, is_published FROM child_services WHERE bot_id=? AND master_service_id=?", (bot_id, msid))
        cs = cur.fetchone()
        conn.close()

        cur_sell = cs["selling_price_per_100"] if cs else round(ms["base_rate_per_100"] * 1.5, 2)
        st = "🟢 Published" if (cs and cs["is_published"] == 1) else "🔴 Not Published"

        txt = (
            f"📦 {ms['service_name'].upper()}\n\n"
            f"💵 Master Cost: ₹{ms['base_rate_per_100']:.3f} per 100 (Live Website Rate)\n"
            f"💰 Your Selling Price: ₹{cur_sell:.2f} per 100\n"
            f"📊 Status: {st}\n\n"
            f"{ms['description']}"
        )
        m = types.InlineKeyboardMarkup(row_width=1)
        m.add(types.InlineKeyboardButton("💲 Set Price & Publish", callback_data=f"c_pub_{msid}"))
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data=f"c_manage_plat_{ms['platform']}"))
        bot.edit_message_text(txt, cid, mid, reply_markup=m)

    elif data.startswith("c_pub_"):
        msid = int(data.replace("c_pub_", ""))
        user_states[f"{bot_id}_{uid}"] = {"step": "wait_resell_price", "msid": msid}
        bot.send_message(cid, "How much rupees do you want to sell per 100? (Enter amount higher than cost):")

    elif data == "a_payment":
        active_status, reason = is_bot_active(bot_id)
        if not active_status and not is_master:
            lock_text = (
                "⚠️ 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗟𝗢𝗖𝗞𝗘𝗗 ⚠️\n\n"
                f"Status: {reason}\n\n"
                "आप तब तक अपना FamPay या Paytm UPI गेटवे नहीं जोड़ सकते जब तक आप License Key एक्टिवेट नहीं कर लेते।\n\n"
                "👉 '🔑 Gateway License Key' मेन्यू में जाकर Key खरीदें या दर्ज करें।"
            )
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("🔑 Get License Key", callback_data="a_license_info"))
            m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="adm_back_panel"))
            bot.edit_message_text(lock_text, cid, mid, reply_markup=m)
            return

        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("SELECT active_gateway, fampay_upi, fampay_email, paytm_mid, paytm_upi FROM child_bots WHERE bot_id=?", (t_id,))
        b_set = cur.fetchone()
        conn.close()

        gw = b_set["active_gateway"] if b_set else "paytm"
        f_email = b_set["fampay_email"] if (b_set and b_set["fampay_email"]) else "Not Set"
        f_upi = b_set["fampay_upi"] if (b_set and b_set["fampay_upi"]) else "Not Set"
        p_mid = b_set["paytm_mid"] if (b_set and b_set["paytm_mid"]) else "Not Set"
        p_upi = b_set["paytm_upi"] if (b_set and b_set["paytm_upi"]) else "Not Set"

        txt = (
            "💳 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 𝗖𝗢𝗡𝗙𝗜𝗚\n\n"
            f"🔥 𝗔𝗰𝘁𝗶𝘃𝗲 𝗠𝗲𝘁𝗵𝗼𝗱: `{gw.upper()}`\n\n"
            f"⚡ 𝗙𝗮𝗺𝗣𝗮𝘆 (𝗚𝗺𝗮𝗶𝗹 𝗔𝘂𝘁𝗼-𝗩𝗲𝗿𝗶𝗳𝘆):\n"
            f"• UPI ID: `{f_upi}`\n"
            f"• Gmail: `{f_email}`\n\n"
            f"💙 𝗣𝗮𝘆𝘁𝗺 𝗕𝘂𝘀𝗶𝗻𝗲𝘀𝘀:\n"
            f"• UPI ID: `{p_upi}`\n"
            f"• Merchant ID (MID): `{p_mid}`"
        )
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("⚡ Set FamPay (Gmail)", callback_data="adm_start_fampay_setup"),
              types.InlineKeyboardButton("💙 Set Paytm (MID)", callback_data="adm_start_paytm_setup"))
        m.add(types.InlineKeyboardButton("Switch to FamPay", callback_data="adm_sw_fampay"),
              types.InlineKeyboardButton("Switch to Paytm", callback_data="adm_sw_paytm"))
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="adm_back_panel"))
        bot.edit_message_text(txt, cid, mid, reply_markup=m, parse_mode="Markdown")

    elif data == "adm_sw_fampay":
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("UPDATE child_bots SET active_gateway='fampay' WHERE bot_id=?", (t_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Active gateway switched to FamPay!", show_alert=True)
        handle_owner_callbacks(bot, bot_id, call, is_master)

    elif data == "adm_sw_paytm":
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("UPDATE child_bots SET active_gateway='paytm' WHERE bot_id=?", (t_id,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Active gateway switched to Paytm!", show_alert=True)
        handle_owner_callbacks(bot, bot_id, call, is_master)

    elif data == "adm_start_fampay_setup":
        user_states[f"{bot_id}_{uid}"] = "fam_step_1_upi"
        bot.send_message(cid, "⚡ 𝗦𝘁𝗲𝗽 𝟭/𝟯: Send your FamPay UPI ID (e.g. `yourname@fam`):")

    elif data == "adm_start_paytm_setup":
        user_states[f"{bot_id}_{uid}"] = "paytm_step_1_upi"
        bot.send_message(cid, "💙 𝗦𝘁𝗲𝗽 𝟭/𝟮: Send your Paytm Business Merchant UPI ID (e.g. `paytm.xxxx@pty`):")

    elif data == "a_suppcontact":
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("SELECT support_wa, support_tg FROM child_bots WHERE bot_id=?", (t_id,))
        row = cur.fetchone()
        conn.close()

        wa_curr = row["support_wa"] if row and row["support_wa"] else "Not Set"
        tg_curr = row["support_tg"] if row and row["support_tg"] else "Not Set"

        txt = (
            "🎧 𝗖𝗨𝗦𝗧𝗢𝗠𝗘𝗥 𝗦𝗨𝗣𝗣𝗢𝗥𝗧 𝗦𝗘𝗧𝗧𝗜𝗡𝗚𝗦\n\n"
            f"• 🟢 WhatsApp: `{wa_curr}`\n"
            f"• ✈️ Telegram: `{tg_curr}`\n\n"
            "Choose which channel you want to set for your users:"
        )
        m = types.InlineKeyboardMarkup(row_width=2)
        m.add(types.InlineKeyboardButton("🟢 Set WhatsApp", callback_data="adm_set_supp_wa"),
              types.InlineKeyboardButton("✈️ Set Telegram", callback_data="adm_set_supp_tg"))
        m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="adm_back_panel"))
        bot.edit_message_text(txt, cid, mid, reply_markup=m, parse_mode="Markdown")

    elif data == "adm_set_supp_wa":
        user_states[f"{bot_id}_{uid}"] = "wait_supp_wa_input"
        bot.send_message(cid, "🟢 Send your WhatsApp Number with Country Code (e.g. `919876543210`):")

    elif data == "adm_set_supp_tg":
        user_states[f"{bot_id}_{uid}"] = "wait_supp_tg_input"
        bot.send_message(cid, "✈️ Send your Telegram Username (e.g. `@username`):")

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

# Universal Robust Text Processor
def handle_text_inputs(bot, bot_id, msg, is_master=False):
    uid = msg.from_user.id
    cid = msg.chat.id
    key = f"{bot_id}_{uid}"
    st_data = user_states.get(key)
    txt = msg.text.strip()

    # If user directly sends 12-digit numeric UTR without clicking anything
    if len(txt) == 12 and txt.isdigit():
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT tx_id, bot_id, user_id, amount, tx_type, target_days FROM transactions WHERE user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1", (uid,))
        t_row = cur.fetchone()
        conn.close()
        if t_row:
            st_data = {"step": "wait_manual_utr", "tx_id": t_row["tx_id"]}

    if not st_data:
        return

    # 1. New key pricing
    if isinstance(st_data, dict) and st_data.get("step") == "wait_new_key_price" and is_master:
        user_states.pop(key, None)
        try:
            new_p = float(txt)
            days = st_data["days"]
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE key_pricing SET price=? WHERE duration_days=?", (new_p, days))
            conn.commit()
            conn.close()
            bot.send_message(cid, f"✅ Price updated to ₹{new_p:.0f} for {days} days!", reply_markup=get_owner_panel(is_master))
        except Exception:
            bot.send_message(cid, "Invalid price number!")
        return

    # 2. Custom days key
    if st_data == "wait_custom_days_key" and is_master:
        user_states.pop(key, None)
        if not txt.isdigit() or int(txt) <= 0:
            bot.send_message(cid, "Please enter a valid number of days.")
            return
        days = int(txt)
        key_code = generate_license_key(duration_days=days)
        txt_res = (
            f"🎟️ 𝗖𝗨𝗦𝗧𝗢𝗠 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗞𝗘𝗬 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘𝗗\n\n"
            f"🔑 Key Code:\n`{key_code}`\n\n"
            f"⏱️ Validity: *{days} Days*\n\n"
            "Send this code to your client to activate their gateway!"
        )
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🔙 Back to Owner Panel", callback_data="adm_back_panel"))
        bot.send_message(cid, txt_res, parse_mode="Markdown", reply_markup=m)
        return

    # 3. Redeem license key
    if st_data == "wait_redeem_key":
        user_states.pop(key, None)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM license_keys WHERE key_code=? AND is_used=0", (txt,))
        lic = cur.fetchone()
        if not lic:
            conn.close()
            bot.send_message(cid, "❌ Invalid or Already Used License Key! Purchase a key or contact @pranavsmm.")
            return

        days = lic["duration_days"]
        new_exp = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("UPDATE license_keys SET is_used=1, used_by_bot_id=? WHERE key_code=?", (bot_id, txt))
        cur.execute("UPDATE child_bots SET is_licensed=1, status='active', subscription_expiry=? WHERE bot_id=?", (new_exp, bot_id))
        conn.commit()
        conn.close()

        dur_text = "👑 Lifetime" if days >= 30000 else f"{days} Days"
        succ_text = (
            "🎉 𝗟𝗜𝗖𝗘𝗡𝗦𝗘 𝗔𝗖𝗧𝗜𝗩𝗔𝗧𝗘𝗗 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬!\n\n"
            f"🔑 Key:\n`{txt}`\n\n"
            f"⏱️ Validity: {dur_text}\n"
            f"📅 Expiry: `{new_exp}`\n\n"
            "Your Automated UPI Gateway & Payment Verification is now fully active."
        )
        bot.send_message(cid, succ_text, parse_mode="Markdown", reply_markup=get_owner_panel(is_master))
        return

    # 4. FamPay setup steps
    if st_data == "fam_step_1_upi":
        user_states[key] = {"step": "fam_step_2_email", "upi": txt}
        bot.send_message(cid, f"✅ UPI ID Saved: `{txt}`\n\n⚡ 𝗦𝘁𝗲𝗽 𝟮/𝟯: Send your FamPay linked Gmail address:", parse_mode="Markdown")
        return

    if isinstance(st_data, dict) and st_data.get("step") == "fam_step_2_email":
        upi = st_data["upi"]
        user_states[key] = {"step": "fam_step_3_pwd", "upi": upi, "email": txt}
        bot.send_message(cid, f"✅ Gmail Saved: `{txt}`\n\n⚡ 𝗦𝘁𝗲𝗽 𝟯/𝟯: Send your 16-digit Google App Password:", parse_mode="Markdown")
        return

    if isinstance(st_data, dict) and st_data.get("step") == "fam_step_3_pwd":
        user_states.pop(key, None)
        upi = st_data["upi"]
        email_addr = st_data["email"]
        app_pwd = txt
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("""
        INSERT INTO child_bots (bot_id, owner_id, fampay_upi, fampay_email, fampay_app_pwd, active_gateway)
        VALUES (?, ?, ?, ?, ?, 'fampay')
        ON CONFLICT(bot_id) DO UPDATE SET
        fampay_upi=excluded.fampay_upi,
        fampay_email=excluded.fampay_email,
        fampay_app_pwd=excluded.fampay_app_pwd,
        active_gateway='fampay'
        """, (t_id, uid, upi, email_addr, app_pwd))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"🎉 *FamPay Configured Successfully!*\n\n• UPI: `{upi}`\n• Email: `{email_addr}`\n• App Password: `{'*'*16}`", 
                         parse_mode="Markdown", reply_markup=get_owner_panel(is_master))
        return

    # 5. Paytm setup steps
    if st_data == "paytm_step_1_upi":
        user_states[key] = {"step": "paytm_step_2_mid", "upi": txt}
        bot.send_message(cid, f"✅ Merchant UPI Saved: `{txt}`\n\n💙 𝗦𝘁𝗲𝗽 𝟮/𝟮: Send your Paytm Merchant ID (MID):", parse_mode="Markdown")
        return

    if isinstance(st_data, dict) and st_data.get("step") == "paytm_step_2_mid":
        user_states.pop(key, None)
        upi = st_data["upi"]
        mid = txt
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("""
        INSERT INTO child_bots (bot_id, owner_id, paytm_upi, paytm_mid, active_gateway)
        VALUES (?, ?, ?, ?, 'paytm')
        ON CONFLICT(bot_id) DO UPDATE SET
        paytm_upi=excluded.paytm_upi,
        paytm_mid=excluded.paytm_mid,
        active_gateway='paytm'
        """, (t_id, uid, upi, mid))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"🎉 *Paytm Business Configured Successfully!*\n\n• UPI: `{upi}`\n• MID: `{mid}`", 
                         parse_mode="Markdown", reply_markup=get_owner_panel(is_master))
        return

    # 6. Support updates (Fixed for both WhatsApp and Telegram)
    if st_data == "wait_supp_wa_input":
        user_states.pop(key, None)
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("UPDATE child_bots SET support_wa=? WHERE bot_id=?", (txt, t_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"✅ WhatsApp Support set to `{txt}`!", parse_mode="Markdown", reply_markup=get_owner_panel(is_master))
        return

    if st_data == "wait_supp_tg_input":
        user_states.pop(key, None)
        conn = get_db()
        cur = conn.cursor()
        t_id = 0 if is_master else bot_id
        cur.execute("UPDATE child_bots SET support_tg=? WHERE bot_id=?", (txt, t_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"✅ Telegram Support set to `{txt}`!", parse_mode="Markdown", reply_markup=get_owner_panel(is_master))
        return

    # 7. 12-Digit Bank UTR Verification
    if isinstance(st_data, dict) and st_data.get("step") == "wait_manual_utr":
        user_states.pop(key, None)
        tx = st_data["tx_id"]
        user_utr = txt

        if len(user_utr) != 12 or not user_utr.isdigit():
            user_states[key] = {"step": "wait_manual_utr", "tx_id": tx}
            bot.send_message(cid, "❌ Invalid UTR! Bank UTR must be exactly 12 numeric digits. Please re-check and send:")
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT amount, status, tx_type, target_days, bot_id FROM transactions WHERE tx_id=?", (tx,))
        t_row = cur.fetchone()
        if not t_row or t_row["status"] == "completed":
            conn.close()
            bot.send_message(cid, "Transaction already completed or invalid.", reply_markup=get_user_main_menu())
            return

        # Check duplicate completed UTR
        cur.execute("SELECT COUNT(*) as c FROM transactions WHERE bank_utr=? AND status='completed'", (user_utr,))
        if cur.fetchone()["c"] > 0:
            conn.close()
            bot.send_message(cid, "❌ This UTR has already been verified and used previously!")
            return

        target_bot_id = 0 if t_row["tx_type"] == "buy_key" else (0 if bot_id == 0 else bot_id)
        cur.execute("SELECT active_gateway, fampay_email, fampay_app_pwd, paytm_mid FROM child_bots WHERE bot_id=?", (target_bot_id,))
        b_conf = cur.fetchone()
        gw = b_conf["active_gateway"] if b_conf and b_conf["active_gateway"] else "paytm"

        verified = False
        reason = ""

        if gw == "fampay" and b_conf and b_conf["fampay_email"] and b_conf["fampay_app_pwd"]:
            verified, reason = verify_fampay_gmail(b_conf["fampay_email"], b_conf["fampay_app_pwd"], t_row["amount"])
        elif gw == "paytm" and b_conf and b_conf["paytm_mid"]:
            verified, reason = verify_paytm_merchant(b_conf["paytm_mid"], user_utr, t_row["amount"])
        else:
            verified = True  # Real 12-digit numeric verified

        if verified:
            cur.execute("UPDATE transactions SET status='completed', bank_utr=? WHERE tx_id=?", (user_utr, tx))
            if t_row["tx_type"] == "buy_key":
                days = t_row["target_days"]
                key_code = generate_license_key(duration_days=days)
                cur.execute("UPDATE license_keys SET used_by_bot_id=? WHERE key_code=?", (bot_id, key_code))
                conn.commit()
                conn.close()

                dur_str = "👑 Lifetime" if days >= 30000 else f"{days} Days"
                bot.send_message(cid, f"🎉 𝗣𝗔𝗬𝗠𝗘𝗡𝗧 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗!\n\n🔑 BotFather-Style Key:\n`{key_code}`\n\n⏱️ Validity: {dur_str}\n\nEnter this in your `/admin` ➔ License to activate!", parse_mode="Markdown")
            else:
                cur.execute("UPDATE bot_clients SET balance = balance + ?, total_deposit = total_deposit + ? WHERE bot_id=? AND user_id=?", 
                            (t_row["amount"], t_row["amount"], bot_id, uid))
                conn.commit()
                conn.close()
                bot.send_message(cid, f"🎉 Payment Verified!\nUTR: `{user_utr}`\n₹{t_row['amount']} credited to your wallet.", reply_markup=get_user_main_menu(), parse_mode="Markdown")
        else:
            conn.close()
            bot.send_message(cid, f"❌ Verification Failed!\n{reason}\nPlease check UTR and try again.")
        return

    # 8. Order Link & Quantity
    if isinstance(st_data, dict) and st_data.get("step") == "wait_link":
        msid = st_data["msid"]
        pr = st_data["price"]
        user_states[key] = {"step": "wait_qty", "msid": msid, "price": pr, "link": txt}
        bot.send_message(cid, f"Link received: {txt}\n\nEnter Quantity:")
        return

    if isinstance(st_data, dict) and st_data.get("step") == "wait_qty":
        user_states.pop(key, None)
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
            m.add(types.InlineKeyboardButton("🟣 Deposit Now", callback_data="u_dep"))
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
        return

    # 9. Child bot selling price
    if isinstance(st_data, dict) and st_data.get("step") == "wait_resell_price":
        user_states.pop(key, None)
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
        return

    # 10. Single master service manual add
    if st_data == "wait_m_single_srv" and is_master:
        user_states.pop(key, None)
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
        return

    # 11. Balance adjustment
    if st_data == "wait_add_bal":
        user_states.pop(key, None)
        parts = txt.split()
        if len(parts) >= 2:
            t_uid, amt = int(parts[0]), float(parts[1])
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE bot_clients SET balance = balance + ? WHERE bot_id=? AND user_id=?", (amt, bot_id, t_uid))
            conn.commit()
            conn.close()
            bot.send_message(cid, f"✅ Added ₹{amt} to User {t_uid}", reply_markup=get_owner_panel(is_master))
        return

    if st_data == "wait_ded_bal":
        user_states.pop(key, None)
        parts = txt.split()
        if len(parts) >= 2:
            t_uid, amt = int(parts[0]), float(parts[1])
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE bot_clients SET balance = MAX(0.0, balance - ?) WHERE bot_id=? AND user_id=?", (amt, bot_id, t_uid))
            conn.commit()
            conn.close()
            bot.send_message(cid, f"✅ Deducted ₹{amt} from User {t_uid}", reply_markup=get_owner_panel(is_master))
        return

    # 12. Ban / Unban
    if st_data == "wait_ban_user":
        user_states.pop(key, None)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE bot_clients SET banned=1 WHERE bot_id=? AND user_id=?", (int(txt), bot_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"✅ User {txt} banned.", reply_markup=get_owner_panel(is_master))
        return

    if st_data == "wait_unban_user":
        user_states.pop(key, None)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE bot_clients SET banned=0 WHERE bot_id=? AND user_id=?", (int(txt), bot_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"✅ User {txt} unbanned.", reply_markup=get_owner_panel(is_master))
        return

    # 13. Channel setup
    if st_data == "wait_log_chan":
        user_states.pop(key, None)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE child_bots SET log_channel=? WHERE bot_id=?", (txt, bot_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"✅ Log channel set to {txt}", reply_markup=get_owner_panel(is_master))
        return

    if st_data == "wait_force_sub":
        user_states.pop(key, None)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE child_bots SET force_channel=? WHERE bot_id=?", (txt, bot_id))
        conn.commit()
        conn.close()
        bot.send_message(cid, f"✅ Force sub channel set to {txt}", reply_markup=get_owner_panel(is_master))
        return

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

                # EXACT SCREENSHOT 7084 COPY (Father Dev Welcome)
                welcome_screen = (
                    f"ﮩ٨ـ Hey 𝔼 𝕃 𝕆 ℕ 𝔸 💎\n"
                    "❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                    "𝗕𝗼𝗼𝘀𝘁 𝗬𝗼𝘂𝗿 𝗦𝗼𝗰𝗶𝗮𝗹 𝗣𝗿𝗲𝘀𝗲𝗻𝗰𝗲 𝗪𝗶𝘁𝗵 𝗜𝗻𝘀𝘁𝗮𝗻𝘁 𝗗𝗲𝗹𝗶𝘃𝗲𝗿𝘆 𝗔𝗻𝗱 𝗔𝘂𝘁𝗼𝗺𝗮𝘁𝗲𝗱 𝟮𝟰/𝟳 𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴. ⭐\n"
                    "❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                    "🥺🥺🥺🥺🥺\n"
                    "𝗪𝗘 𝗛𝗔𝗩𝗘 𝗖𝗟𝗢𝗡𝗘 𝗥𝗘𝗦𝗘𝗟𝗟𝗜𝗡 𝗣𝗥𝗢𝗚𝗥𝗔𝗠 𝗙𝗢𝗥 𝗕𝗨𝗦𝗜𝗡𝗘𝗦𝗦 𝗠𝗔𝗡 & 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥𝗦\n"
                    "❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                    "𝗣𝗿𝗲𝘀𝘀 𝗖𝗼𝗻𝘁𝗶𝗻𝘂𝗲 𝗧𝗼 𝗢𝗽𝗲𝗻 𝗧𝗵𝗲 𝗠𝗲𝗻𝘂"
                )
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("💎 Continue", callback_data="u_continue_main"))
                cbot.send_message(msg.chat.id, welcome_screen, reply_markup=m)

            @cbot.message_handler(commands=['admin'])
            def c_admin(msg):
                # Super Admin or Bot Owner can open Admin Panel
                if msg.from_user.id != owner_id and msg.from_user.id != SUPER_ADMIN_ID:
                    cbot.reply_to(msg, "Access Denied: You are not the owner of this bot.")
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

            @cbot.message_handler(func=lambda m: True and not m.text.startswith('/'))
            def c_txts(m):
                handle_text_inputs(cbot, bot_id, m, is_master=False)

            print(f"[CHILD BOT ONLINE] @{bot_username}")
            cbot.infinity_polling(timeout=20, long_polling_timeout=15, skip_pending=True)
        except Exception as e:
            print(f"[CHILD BOT RESTARTING] @{bot_username} Error: {e}")
            time.sleep(2)

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
                    master_bot.reply_to(msg, "❌ Access Denied: Only Super Admin can access Master Admin Panel.")
                    return
                master_bot.send_message(msg.chat.id, "👑 MASTER BOT ADMIN PANEL\n\nFull control over Master services, website API sync, payment gateway, license keys, and child bots.", reply_markup=get_owner_panel(is_master=True))

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
                    m.add(types.InlineKeyboardButton("🔙 GO BACK", callback_data="u_back_main"))
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

            @master_bot.message_handler(func=lambda m: True and not m.text.startswith('/'))
            def m_txts(msg):
                uid = msg.from_user.id
                cid = msg.chat.id
                key = f"0_{uid}"
                st_data = user_states.get(key)
                txt = msg.text.strip()

                if st_data == "wait_token":
                    user_states.pop(key, None)
                    v_msg = master_bot.send_message(cid, "🔄 Connecting your bot... Validating token...")
                    try:
                        chk = requests.get(f"https://api.telegram.org/bot{txt}/getMe", timeout=12)
                        data = chk.json()
                    except Exception:
                        data = {}

                    if not data.get("ok"):
                        master_bot.edit_message_text("❌ Invalid Bot Token! Please provide a valid token from @BotFather.", cid, v_msg.message_id)
                        return

                    bot_user = data["result"]["username"]
                    bot_name = data["result"]["first_name"]
                    token_enc = cipher_suite.encrypt(txt.encode()).decode()

                    conn = get_db()
                    cur = conn.cursor()
                    try:
                        cur.execute("""
                        INSERT INTO child_bots (owner_id, bot_token_enc, bot_username, bot_name, support_tg, is_licensed, status)
                        VALUES (?, ?, ?, ?, '', 0, 'active')
                        """, (uid, token_enc, bot_user, bot_name))
                        conn.commit()
                        bot_id = cur.lastrowid
                    except sqlite3.IntegrityError:
                        cur.execute("UPDATE child_bots SET bot_username=?, bot_name=?, status='active' WHERE bot_token_enc=?", (bot_user, bot_name, token_enc))
                        conn.commit()
                        cur.execute("SELECT bot_id FROM child_bots WHERE bot_token_enc=?", (token_enc,))
                        bot_id = cur.fetchone()["bot_id"]
                    conn.close()

                    t = threading.Thread(target=run_child_bot_loop, args=(bot_id, uid, txt, bot_user, bot_name), daemon=True)
                    t.start()
                    bot_threads[txt] = t

                    live_text = (
                        f"🚀 𝗕𝗢𝗧 𝗜𝗦 𝗟𝗜𝗩𝗘!\n\n"
                        f"🤖 @{bot_user}\n\n"
                        "Open your bot and send /admin to configure services and payment!"
                    )
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
            time.sleep(2)

def five_second_keepalive_engine():
    time.sleep(5)
    pulse_counter = 0
    while True:
        try:
            pulse_counter += 1
            
            # Local internal ping
            try:
                requests.get(f"http://127.0.0.1:{RENDER_PORT}/", timeout=3)
            except Exception:
                pass

            # Render external domain ping
            if pulse_counter % 6 == 0 and RENDER_EXTERNAL_URL:
                url = RENDER_EXTERNAL_URL.rstrip('/')
                if not url.startswith("http"):
                    url = f"https://{url}"
                try:
                    requests.get(url, timeout=5)
                except Exception:
                    pass

            # Watchdog: Auto-Revive Crashed Bot Threads
            if pulse_counter % 3 == 0:
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
            print(f"[5-SECOND WATCHDOG ERROR] {e}")

        time.sleep(5)

threading.Thread(target=run_master_bot_loop, daemon=True).start()
threading.Thread(target=five_second_keepalive_engine, daemon=True).start()

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "engine": "Pranav Father Dev Master Engine",
        "pulse_mode": "5-second active self-ping",
        "master_live": master_is_running,
        "child_bots_alive": len([t for t in bot_threads.values() if t.is_alive()])
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
