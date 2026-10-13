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

# ==============================================================================
# 1. कॉन्फ़िगरेशन एवं पर्यावरण चर
# ==============================================================================
RENDER_PORT = int(os.environ.get("PORT", 8081))
MASTER_BOT_TOKEN = os.environ.get("MASTER_BOT_TOKEN", "").strip()
SUPER_ADMIN_ID = int(os.environ.get("ADMIN_ID", "8585055903"))

# आपकी मुख्य वेबसाइट (Master SMM Provider)
MAIN_PANEL_URL = os.environ.get("MAIN_PANEL_URL", "https://pranavsmm.shop/api/v2")
MAIN_PANEL_API_KEY = os.environ.get("MAIN_PANEL_API_KEY", "").strip()

# टोकन एन्क्रिप्शन (चोरी से 100% सुरक्षा)
SECRET_KEY = os.environ.get("SECRET_KEY", Fernet.generate_key().decode())
cipher_suite = Fernet(SECRET_KEY.encode() if isinstance(SECRET_KEY, str) else SECRET_KEY)

DB_PATH = "father_master_engine.db"
app = Flask(__name__)

active_child_bots = {}
user_states = {}

# ==============================================================================
# 2. डेटाबेस इनिशियलाइज़ेशन (चाइल्ड बॉट्स, यूज़र्स, सर्विसेज़, ऑर्डर्स)
# ==============================================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # 1. चाइल्ड बॉट्स
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
    # 2. क्लाइंट्स
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
    # 3. सर्विसेज़
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bot_services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id INTEGER,
        category TEXT,
        service_name TEXT,
        main_api_service_id TEXT,
        cost_price REAL DEFAULT 1.0,
        selling_price_per_100 REAL DEFAULT 3.0,
        description TEXT
    )
    """)
    # 4. ऑर्डर्स
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
    # 5. ट्रांजैक्शन्स (ऑटो-डिपॉजिट)
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

# ==============================================================================
# 3. ऑटो-पेमेंट वेबहुक (FamPay / Paytm API)
# ==============================================================================
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
                tb.send_message(user_id, f"✅ *Payment Success!*\n\n💰 Deposited: `₹{credited_amt:.2f}`\n🆔 Ref: `{tx_id}`\nवॉलेट में बैलेंस तुरंत क्रेडिट हो चुका है।", parse_mode="Markdown")
                if b_row["log_channel"]:
                    tb.send_message(b_row["log_channel"], f"🔔 *[DEPOSIT LOG]*\nUser: `{user_id}`\nAmount: `₹{credited_amt}`\nStatus: Auto Verified")
            except Exception:
                pass

        return jsonify({"status": "success"}), 200

    conn.close()
    return jsonify({"status": "already_done"}), 200

# ==============================================================================
# 4. चाइल्ड बॉट रनर (पूरी तरह वीडियो जैसा फ़्लो)
# ==============================================================================
def run_child_bot(bot_id, owner_id, token, bot_username, bot_name):
    try:
        cbot = telebot.TeleBot(token, threaded=True)
        requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=True", timeout=5)
    except Exception as e:
        print(f"[CHILD BOT START ERROR] {e}")
        return

    # 1. यूजर मेन्यू
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

    # 2. ऑनर एडमिन पैनल (/admin)
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
            types.InlineKeyboardButton("𝗧𝘂𝗿𝗻 𝗢𝗻 𝗣𝗿𝗼 𝗠𝗼𝗱𝗲", callback_data="a_promode")
        )
        m.add(types.InlineKeyboardButton("𝗠𝗮𝗶𝗻 𝗠𝗲𝗻𝘂", callback_data="a_back_main"))
        return m

    # Force Sub चेक करने का फंक्शन
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

    # /start कमांड
    @cbot.message_handler(commands=['start'])
    def c_start(msg):
        uid = msg.from_user.id

        # 1. बैन चेक
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT banned FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid))
        urow = cur.fetchone()
        if urow and urow["banned"] == 1:
            cbot.reply_to(msg, "🚫 *You are banned from using this bot!*", parse_mode="Markdown")
            conn.close()
            return

        # 2. Force Sub चेक
        if not is_user_subscribed(uid):
            cur.execute("SELECT force_channel FROM child_bots WHERE bot_id=?", (bot_id,))
            ch = cur.fetchone()["force_channel"]
            conn.close()
            m = types.InlineKeyboardMarkup()
            m.add(types.InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{ch.replace('@', '')}"))
            m.add(types.InlineKeyboardButton("✅ Check Joined", callback_data="u_check_joined"))
            cbot.send_message(msg.chat.id, f"⚠️ *बॉट का उपयोग करने के लिए पहले हमारे चैनल {ch} को जॉइन करें!*", reply_markup=m, parse_mode="Markdown")
            return

        cur.execute("INSERT OR IGNORE INTO bot_clients (bot_id, user_id, username) VALUES (?, ?, ?)",
                    (bot_id, uid, msg.from_user.username or 'User'))
        conn.commit()
        conn.close()

        welcome_text = (
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
        cbot.send_message(msg.chat.id, welcome_text, reply_markup=get_user_main_menu(), parse_mode="Markdown")

    # /admin कमांड (केवल मालिक)
    @cbot.message_handler(commands=['admin'])
    def c_admin(msg):
        if msg.from_user.id != owner_id:
            cbot.reply_to(msg, "⛔ आप इस बॉट के मालिक (Owner) नहीं हैं!")
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

    # ==================== कॉलबैक हैंडलर ====================
    @cbot.callback_query_handler(func=lambda c: True)
    def c_callbacks(call):
        uid = call.from_user.id
        cid = call.message.chat.id
        data = call.data

        # --- Force Sub Check Button ---
        if data == "u_check_joined":
            if is_user_subscribed(uid):
                cbot.delete_message(cid, call.message.message_id)
                cbot.send_message(cid, "✅ चैनल वेरिफिकेशन सफल हुआ! /start दबाएँ।")
            else:
                cbot.answer_callback_query(call.id, "❌ आपने अभी तक चैनल जॉइन नहीं किया है!", show_alert=True)
            return

        # --- 1. USER BUTTONS ---
        if data == "u_back_main":
            cbot.edit_message_text(
                "💎*𝗠𝗔𝗜𝗡 𝗠𝗘𝗡𝗨*💎 ~\n\nकृपया नीचे दिए गए विकल्पों में से चुनें:",
                cid, call.message.message_id,
                reply_markup=get_user_main_menu(),
                parse_mode="Markdown"
            )

        elif data == "u_bal":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT balance FROM bot_clients WHERE bot_id=? AND user_id=?", (bot_id, uid))
            row = cur.fetchone()
            conn.close()
            bal = row["balance"] if row else 0.0

            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                types.InlineKeyboardButton("💰 𝗗𝗲𝗽𝗼𝘀𝗶𝘁", callback_data="u_dep"),
                types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main")
            )
            cbot.edit_message_text(
                f"💳 *𝗬𝗢𝗨𝗥 𝗪𝗔𝗟𝗟𝗘𝗧 𝗕𝗔𝗟𝗔𝗡𝗖𝗘*\n\n"
                f"• User ID: `{uid}`\n"
                f"• Current Balance: `₹{bal:.2f}`\n\n"
                f"ऑर्डर लगाने के लिए पर्याप्त बैलेंस होना आवश्यक है।",
                cid, call.message.message_id,
                reply_markup=m,
                parse_mode="Markdown"
            )

        elif data == "u_dep":
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                types.InlineKeyboardButton("⚡ FamPay Instant", callback_data="sub_dep_fampay"),
                types.InlineKeyboardButton("💳 Paytm / UPI QR", callback_data="sub_dep_qr")
            )
            m.add(
                types.InlineKeyboardButton("📜 Payment Rules", callback_data="sub_dep_rules"),
                types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main")
            )
            cbot.edit_message_text(
                "💰 *𝗔𝗨𝗧𝗢𝗠𝗔𝗧𝗘𝗗 𝗗𝗘𝗣𝗢𝗦𝗜𝗧 𝗛𝗨𝗕*\n\n"
                "भुगतान का माध्यम चुनें (भुगतान होते ही बैलेंस 5-10 सेकंड में अपने आप जुड़ जाता है):",
                cid, call.message.message_id,
                reply_markup=m,
                parse_mode="Markdown"
            )

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

            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(types.InlineKeyboardButton("🔙 Back to Deposit", callback_data="u_dep"))

            cbot.send_photo(
                cid,
                qr_url,
                caption=f"💳 *Paytm / UPI Instant QR*\n\n"
                        f"• UPI ID: `{upi_id}`\n"
                        f"• Ref ID: `{tx_code}`\n\n"
                        f"पेमेंट पूरा होने पर सिस्टम ऑटो-वेरीफाई कर लेगा।",
                reply_markup=m,
                parse_mode="Markdown"
            )

        elif data == "sub_dep_fampay":
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(types.InlineKeyboardButton("🔙 Back to Deposit", callback_data="u_dep"))
            cbot.edit_message_text(
                "⚡ *FamPay Instant Gateway*\n\n"
                "डिपॉजिट करने के लिए राशि चैट में लिखकर भेजें (उदा. `10` या `50`):",
                cid, call.message.message_id,
                reply_markup=m,
                parse_mode="Markdown"
            )
            user_states[f"{bot_id}_{uid}"] = "wait_fampay_amt"

        elif data == "sub_dep_rules":
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(types.InlineKeyboardButton("🔙 Back to Deposit", callback_data="u_dep"))
            cbot.edit_message_text(
                "📜 *पेमेंट नियम:*\n\n"
                "1. न्यूनतम डिपॉजिट राशि ₹10 है।\n"
                "2. QR कोड पर भुगतान करने के बाद 10-15 सेकंड में बैलेंस स्वतः जुड़ जाता है।",
                cid, call.message.message_id,
                reply_markup=m,
                parse_mode="Markdown"
            )

        elif data == "u_ord":
            m = types.InlineKeyboardMarkup(row_width=2)
            m.add(
                types.InlineKeyboardButton("📸 Instagram", callback_data="cat_instagram"),
                types.InlineKeyboardButton("▶️ YouTube", callback_data="cat_youtube")
            )
            m.add(
                types.InlineKeyboardButton("✈️ Telegram", callback_data="cat_telegram"),
                types.InlineKeyboardButton("📘 Facebook", callback_data="cat_facebook")
            )
            m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main"))
            cbot.edit_message_text(
                "🛒 *𝗢𝗥𝗗𝗘𝗥 𝗦𝗘𝗥𝗩𝗜𝗖𝗘𝗦*\n\nकृपया सोशल मीडिया प्लेटफॉर्म चुनें:",
                cid, call.message.message_id,
                reply_markup=m,
                parse_mode="Markdown"
            )

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
                    m.add(types.InlineKeyboardButton(f"⚡ {s['service_name']} - ₹{s['selling_price_per_100']}/100", callback_data=f"buy_{s['id']}"))
            m.add(types.InlineKeyboardButton("🔙 Back to Categories", callback_data="u_ord"))

            txt = f"📦 *{cat_name} Services List:*\n\nसर्विस चुनें और तुरंत ऑर्डर लगाएँ:" if srvs else f"⚠️ *{cat_name}* में फिलहाल कोई सर्विस सक्रिय नहीं है। एडमिन जल्द जोड़ेगा।"
            cbot.edit_message_text(txt, cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")

        elif data.startswith("buy_"):
            srv_id = data.replace("buy_", "")
            user_states[f"{bot_id}_{uid}"] = {"step": "wait_link", "service_id": srv_id}
            cbot.send_message(cid, "🔗 कृपया अपनी पोस्ट, रील या प्रोफाइल का **Link** भेजें:")

        elif data == "u_hist":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT service_name, quantity, charge, status, created_at FROM bot_orders WHERE bot_id=? AND user_id=? ORDER BY id DESC LIMIT 5", (bot_id, uid))
            orders = cur.fetchall()
            conn.close()

            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main"))

            if orders:
                txt = "\n\n".join([f"📦 *{o['service_name']}*\nQty: `{o['quantity']}` | Charge: `₹{o['charge']:.2f}`\nStatus: `{o['status']}`" for o in orders])
                cbot.edit_message_text(f"🗓️ *𝗬𝗢𝗨𝗥 𝗥𝗘𝗖𝗘𝗡𝗧 𝗢𝗥𝗗𝗘𝗥𝗦*\n\n{txt}", cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")
            else:
                cbot.edit_message_text("🗓️ *𝗬𝗢𝗨𝗥 𝗢𝗥𝗗𝗘𝗥 𝗛𝗜𝗦𝗧𝗢𝗥𝗬*\n\nफिलहाल कोई ऑर्डर नहीं मिला।", cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")

        elif data == "u_supp":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT support_contact FROM child_bots WHERE bot_id=?", (bot_id,))
            supp = cur.fetchone()["support_contact"] or "@pranavsmm"
            conn.close()

            clean_user = supp.replace("@", "")
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(
                types.InlineKeyboardButton("💬 Telegram Support", url=f"https://t.me/{clean_user}"),
                types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main")
            )
            cbot.edit_message_text(
                f"💬 *𝗖𝗨𝗦𝗧𝗢𝗠𝗘𝗥 𝗦𝗨𝗣𝗣𝗢𝗥𝗧*\n\n"
                f"किसी भी समस्या या सवाल के लिए हमारे सपोर्ट से सीधे संपर्क करें:\n\n"
                f"👉 **Telegram:** `{supp}`",
                cid, call.message.message_id,
                reply_markup=m,
                parse_mode="Markdown"
            )

        elif data == "u_cyob":
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(
                types.InlineKeyboardButton("🚀 Open BotFather", url="https://t.me/BotFather"),
                types.InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="u_back_main")
            )
            cyob_promo = (
                "👑 *𝗖𝗥𝗘𝗔𝗧𝗘 𝗬𝗢𝗨𝗥 𝗢𝗪𝗡 𝗕𝗢𝗧* ★ 𝗣𝗥𝗢\n\n"
                "╭━━━━━━━━━━━━━━━━━━━╮\n"
                " 𝗦𝗧𝗔𝗥𝗧 𝗬𝗢𝗨𝗥 𝗢𝗪𝗡 𝗕𝗥𝗔𝗡𝗗𝗘𝗗 𝗥𝗘𝗦𝗘𝗟𝗟𝗘𝗥 𝗕𝗨𝗦𝗜𝗡𝗘𝗦𝗦 𝗜𝗡 𝗠𝗜𝗡𝗨𝗧𝗘𝗦.\n\n"
                " 1️⃣ 𝗢𝗣𝗘𝗡 ➔ @BotFather\n"
                " 2️⃣ 𝗦𝗘𝗡𝗗 /newbot & 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗦𝗧𝗘𝗣𝗦\n"
                " 3️⃣ 𝗖𝗢𝗣𝗬 𝗧𝗛𝗘 𝗕𝗢𝗧 𝗧𝗢𝗞𝗘𝗡 𝗜𝗧 𝗚𝗜𝗩𝗘𝗦 𝗬𝗢𝗨\n"
                " 4️⃣ 𝗣𝗔𝗦𝗧𝗘 𝗜𝗧 𝗜𝗡 𝗠𝗔𝗦𝗧𝗘𝗥 𝗕𝗢𝗧\n"
                " ❄️❄️❄️❄️❄️❄️❄️❄️❄️\n"
                " 𝗬𝗢𝗨𝗥 𝗕𝗢𝗧 𝗚𝗢𝗘𝗦 𝗟𝗜𝗩𝗘 𝗜𝗡𝗦𝗧𝗔𝗡𝗧𝗟𝗬 𝗪𝗜𝗧𝗛 𝗔𝗟𝗟 𝗙𝗘𝗔𝗧𝗨𝗥𝗘𝗦 🖤\n"
                "╰━━━━━━━━━━━━━━━━━━━╯"
            )
            cbot.edit_message_text(cyob_promo, cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")

        # --- 2. OWNER PANEL ACTIONS (/admin) ---
        elif data.startswith("a_") or data.startswith("sub_"):
            if uid != owner_id:
                cbot.answer_callback_query(call.id, "अनुमति नहीं है!", show_alert=True)
                return

            if data == "a_back_main":
                cbot.send_message(cid, "💎 *Main Menu:*", reply_markup=get_user_main_menu(), parse_mode="Markdown")

            elif data == "sub_back_adm":
                cbot.edit_message_text("👑 *Owner Panel:*", cid, call.message.message_id, reply_markup=get_owner_panel(), parse_mode="Markdown")

            elif data == "a_services":
                m = types.InlineKeyboardMarkup(row_width=2)
                m.add(
                    types.InlineKeyboardButton("➕ नई सर्विस जोड़ें", callback_data="sub_add_srv"),
                    types.InlineKeyboardButton("📋 लिस्ट व मैनेज", callback_data="sub_list_srv")
                )
                m.add(types.InlineKeyboardButton("🔙 वापस एडमिन", callback_data="sub_back_adm"))
                cbot.edit_message_text("⚙️ *SERVICES MANAGER*\n\nअपनी सर्विस और सेलिंग प्राइस मैनेज करें:", cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")

            elif data == "sub_add_srv":
                user_states[f"{bot_id}_{uid}"] = "wait_srv_details"
                cbot.send_message(cid, "📝 सर्विस जोड़ने के लिए भेजें:\n`Category | Service Name | Selling Price (per 100) | Main API Service ID`\n\nउदा:\n`Instagram | IG Likes India | 3.0 | 1024`", parse_mode="Markdown")

            elif data == "sub_list_srv":
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT id, category, service_name, selling_price_per_100 FROM bot_services WHERE bot_id=?", (bot_id,))
                rows = cur.fetchall()
                conn.close()
                txt = "\n".join([f"• ID `{r['id']}`: [{r['category']}] {r['service_name']} (₹{r['selling_price_per_100']}/100)" for r in rows]) if rows else "कोई सर्विस नहीं मिली।"
                cbot.send_message(cid, f"📋 *आपकी सर्विसेज:*\n\n{txt}\n\nहटाने के लिए भेजें: `/del ID`", reply_markup=get_owner_panel(), parse_mode="Markdown")

            elif data == "a_payment":
                m = types.InlineKeyboardMarkup(row_width=1)
                m.add(
                    types.InlineKeyboardButton("💳 UPI ID बदलें", callback_data="sub_set_upi"),
                    types.InlineKeyboardButton("⚡ FamPay API एंडपॉइंट जोड़ें", callback_data="sub_set_fampay"),
                    types.InlineKeyboardButton("🔙 वापस एडमिन", callback_data="sub_back_adm")
                )
                cbot.edit_message_text("💳 *PAYMENT GATEWAY CONFIG*\n\nपेमेंट सेटिंग्स चुनें:", cid, call.message.message_id, reply_markup=m, parse_mode="Markdown")

            elif data == "sub_set_upi":
                user_states[f"{bot_id}_{uid}"] = "wait_upi_id"
                cbot.send_message(cid, "💳 अपनी नई UPI ID भेजें (उदा. `pranavpatel@upi`):")

            elif data == "sub_set_fampay":
                user_states[f"{bot_id}_{uid}"] = "wait_fampay_creds"
                cbot.send_message(cid, "⚡ FamPay एंडपॉइंट व API Key भेजें:\n`Endpoint | API_Key`")

            elif data == "a_users":
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) as total FROM bot_clients WHERE bot_id=?", (bot_id,))
                t = cur.fetchone()["total"]
                conn.close()
                cbot.send_message(cid, f"👥 *कुल रजिस्टर्ड यूज़र्स:* `{t}`", reply_markup=get_owner_panel(), parse_mode="Markdown")

            elif data == "a_bcast":
                user_states[f"{bot_id}_{uid}"] = "wait_bcast_msg"
                cbot.send_message(cid, "📢 ब्रॉडकास्ट मैसेज टाइप करके भेजें:")

            elif data == "a_addbal":
                user_states[f"{bot_id}_{uid}"] = "wait_add_bal"
                cbot.send_message(cid, "➕ बैलेंस जोड़ने के लिए भेजें:\n`User_ID Amount`\n\nउदा: `8585055903 50`", parse_mode="Markdown")

            elif data == "a_dedbal":
                user_states[f"{bot_id}_{uid}"] = "wait_ded_bal"
                cbot.send_message(cid, "➖ बैलेंस काटने के लिए भेजें:\n`User_ID Amount`\n\nउदा: `8585055903 20`", parse_mode="Markdown")

            elif data == "a_ban":
                user_states[f"{bot_id}_{uid}"] = "wait_ban_user"
                cbot.send_message(cid, "🚫 बैन करने के लिए `User_ID` भेजें:")

            elif data == "a_unban":
                user_states[f"{bot_id}_{uid}"] = "wait_unban_user"
                cbot.send_message(cid, "✅ अनबैन करने के लिए `User_ID` भेजें:")

            elif data == "a_logchan":
                user_states[f"{bot_id}_{uid}"] = "wait_log_chan"
                cbot.send_message(cid, "📡 लॉग चैनल का यूजरनेम भेजें (उदा. `@MyLogChannel`):")

            elif data == "a_forcesub":
                user_states[f"{bot_id}_{uid}"] = "wait_force_sub"
                cbot.send_message(cid, "🔒 Force Sub चैनल का यूजरनेम भेजें (उदा. `@MyChannel`):")

            elif data == "a_suppcontact":
                user_states[f"{bot_id}_{uid}"] = "wait_supp_contact"
                cbot.send_message(cid, "💬 अपना सपोर्ट यूजरनेम भेजें (डिफ़ॉल्ट: `@pranavsmm`):")

            elif data == "a_promode":
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT pro_mode FROM child_bots WHERE bot_id=?", (bot_id,))
                curr = cur.fetchone()["pro_mode"]
                new_m = 0 if curr == 1 else 1
                cur.execute("UPDATE child_bots SET pro_mode=? WHERE bot_id=?", (new_m, bot_id))
                conn.commit()
                conn.close()
                txt = "✅ Pro Mode turned ON (VIP Emojis Active)!" if new_m == 1 else "❌ Pro Mode turned OFF!"
                cbot.send_message(cid, txt, reply_markup=get_owner_panel())

    # ------------------ टेक्स्ट इनपुट हैंडलर ------------------
    @cbot.message_handler(func=lambda m: f"{bot_id}_{m.from_user.id}" in user_states and not m.text.startswith('/'))
    def c_text_inputs(m):
        uid = m.from_user.id
        cid = m.chat.id
        key = f"{bot_id}_{uid}"
        state_data = user_states.pop(key, None)
        txt = m.text.strip()

        # 1. ऑर्डर फ़्लो (Link & Quantity)
        if isinstance(state_data, dict) and state_data.get("step") == "wait_link":
            srv_id = state_data["service_id"]
            user_states[key] = {"step": "wait_qty", "service_id": srv_id, "link": txt}
            cbot.send_message(cid, f"🔗 लिंक दर्ज हुआ: `{txt}`\n\n🔢 अब **मात्रा (Quantity)** लिखकर भेजें (उदा. `100` या `500`):", parse_mode="Markdown")

        elif isinstance(state_data, dict) and state_data.get("step") == "wait_qty":
            if not txt.isdigit():
                cbot.send_message(cid, "❌ कृपया केवल संख्या भेजें!")
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
                cbot.send_message(cid, f"❌ अपर्याप्त बैलेंस!\nकुल लागत: `₹{cost:.2f}`\nआपका बैलेंस: `₹{bal:.2f}`\nकृपया पहले डिपॉजिट करें।", parse_mode="Markdown")
                conn.close()
            else:
                # यूज़र के वॉलेट से बैलेंस काटना
                cur.execute("UPDATE bot_clients SET balance = balance - ? WHERE bot_id=? AND user_id=?", (cost, bot_id, uid))
                
                # मुख्य वेबसाइट (MAIN_PANEL_URL) पर ऑर्डर ऑटो-फॉरवर्ड करना
                api_order_id = "MANUAL"
                if MAIN_PANEL_API_KEY and srv["main_api_service_id"]:
                    try:
                        p_data = {
                            "key": MAIN_PANEL_API_KEY,
                            "action": "add",
                            "service": srv["main_api_service_id"],
                            "link": link,
                            "quantity": qty
                        }
                        r = requests.post(MAIN_PANEL_URL, data=p_data, timeout=10).json()
                        if "order" in r:
                            api_order_id = str(r["order"])
                    except Exception:
                        pass

                cur.execute("""
                INSERT INTO bot_orders (bot_id, user_id, service_name, link, quantity, charge, api_order_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (bot_id, uid, srv["service_name"], link, qty, cost, api_order_id, "Processing"))
                conn.commit()

                cur.execute("SELECT log_channel FROM child_bots WHERE bot_id=?", (bot_id,))
                l_chan = cur.fetchone()["log_channel"]
                conn.close()

                cbot.send_message(cid, f"🎉 *ऑर्डर सफल!*\n\n• सर्विस: `{srv['service_name']}`\n• मात्रा: `{qty}`\n• काटा गया बैलेंस: `₹{cost:.2f}`\n• शेष बैलेंस: `₹{bal - cost:.2f}`\n• स्थिति: `Processing`", parse_mode="Markdown")

                if l_chan:
                    try:
                        cbot.send_message(l_chan, f"📦 *[NEW ORDER]*\nUser: `{uid}`\nService: `{srv['service_name']}`\nQty: `{qty}`\nStatus: Processing")
                    except Exception:
                        pass

        # 2. एडमिन सेटिंग्स फ़्लो
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
                cbot.send_message(cid, f"✅ सर्विस `{s_name}` (₹{price}/100) सफलतापूर्वक पब्लिश हुई!", reply_markup=get_owner_panel(), parse_mode="Markdown")

        elif state_data == "wait_upi_id":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE child_bots SET paytm_mid=? WHERE bot_id=?", (txt, bot_id))
            conn.commit()
            conn.close()
            cbot.send_message(cid, f"✅ UPI ID अपडेट हो गई: `{txt}`", reply_markup=get_owner_panel(), parse_mode="Markdown")

        elif state_data == "wait_fampay_creds":
            parts = [p.strip() for p in txt.split("|")]
            if len(parts) >= 2:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("UPDATE child_bots SET fampay_endpoint=?, fampay_apikey=? WHERE bot_id=?", (parts[0], parts[1], bot_id))
                conn.commit()
                conn.close()
                cbot.send_message(cid, "✅ FamPay ऑटो-गेटवे सफलतापूर्वक कनेक्ट हुआ!", reply_markup=get_owner_panel())

        elif state_data == "wait_add_bal":
            parts = txt.split()
            if len(parts) >= 2:
                target_uid = int(parts[0])
                amt = float(parts[1])
                conn = get_db()
                cur = conn.cursor()
                cur.execute("UPDATE bot_clients SET balance = balance + ? WHERE bot_id=? AND user_id=?", (amt, bot_id, target_uid))
                conn.commit()
                conn.close()
                cbot.send_message(cid, f"✅ यूज़र `{target_uid}` के खाते में ₹{amt} जोड़ दिए गए!", reply_markup=get_owner_panel(), parse_mode="Markdown")

        elif state_data == "wait_ded_bal":
            parts = txt.split()
            if len(parts) >= 2:
                target_uid = int(parts[0])
                amt = float(parts[1])
                conn = get_db()
                cur = conn.cursor()
                cur.execute("UPDATE bot_clients SET balance = MAX(0.0, balance - ?) WHERE bot_id=? AND user_id=?", (amt, bot_id, target_uid))
                conn.commit()
                conn.close()
                cbot.send_message(cid, f"✅ यूज़र `{target_uid}` के खाते से ₹{amt} काट लिए गए!", reply_markup=get_owner_panel(), parse_mode="Markdown")

        elif state_data == "wait_ban_user":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE bot_clients SET banned=1 WHERE bot_id=? AND user_id=?", (int(txt), bot_id))
            conn.commit()
            conn.close()
            cbot.send_message(cid, f"🚫 यूज़र `{txt}` को बैन कर दिया गया!", reply_markup=get_owner_panel(), parse_mode="Markdown")

        elif state_data == "wait_unban_user":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE bot_clients SET banned=0 WHERE bot_id=? AND user_id=?", (int(txt), bot_id))
            conn.commit()
            conn.close()
            cbot.send_message(cid, f"✅ यूज़र `{txt}` को अनबैन कर दिया गया!", reply_markup=get_owner_panel(), parse_mode="Markdown")

        elif state_data == "wait_log_chan":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE child_bots SET log_channel=? WHERE bot_id=?", (txt, bot_id))
            conn.commit()
            conn.close()
            cbot.send_message(cid, f"📡 लॉग चैनल सेट हुआ: `{txt}`", reply_markup=get_owner_panel(), parse_mode="Markdown")

        elif state_data == "wait_force_sub":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE child_bots SET force_channel=? WHERE bot_id=?", (txt, bot_id))
            conn.commit()
            conn.close()
            cbot.send_message(cid, f"🔒 Force Sub चैनल सेट हुआ: `{txt}`", reply_markup=get_owner_panel(), parse_mode="Markdown")

        elif state_data == "wait_supp_contact":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE child_bots SET support_contact=? WHERE bot_id=?", (txt, bot_id))
            conn.commit()
            conn.close()
            cbot.send_message(cid, f"💬 सपोर्ट यूजरनेम सेट हुआ: `{txt}`", reply_markup=get_owner_panel(), parse_mode="Markdown")

        elif state_data == "wait_bcast_msg":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM bot_clients WHERE bot_id=?", (bot_id,))
            users = cur.fetchall()
            conn.close()
            s_count = 0
            for u in users:
                try:
                    cbot.send_message(u["user_id"], f"📢 *Important Announcement:*\n\n{txt}", parse_mode="Markdown")
                    s_count += 1
                except Exception:
                    pass
            cbot.send_message(cid, f"📢 ब्रॉडकास्ट पूरा हुआ! `{s_count}` यूज़र्स को भेजा गया।", reply_markup=get_owner_panel(), parse_mode="Markdown")

    print(f"[CHILD BOT LIVE] @{bot_username} चल रहा है (Owner: {owner_id})")
    while True:
        try:
            cbot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
        except Exception:
            time.sleep(3)

# ==============================================================================
# 5. मास्टर "फादर" बॉट (CYOB ENGINE)
# ==============================================================================
master_bot = telebot.TeleBot(MASTER_BOT_TOKEN, threaded=True) if MASTER_BOT_TOKEN else None

@master_bot.message_handler(commands=['start'])
def m_start(msg):
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(
        types.InlineKeyboardButton("👑 𝗖𝗥𝗘𝗔𝗧𝗘 𝗬𝗢𝗨𝗥 𝗢𝗪𝗡 𝗕𝗢𝗧 (CYOB)", callback_data="m_cyob"),
        types.InlineKeyboardButton("📂 𝗠𝘆 𝗖𝗿𝗲𝗮𝘁𝗲𝗱 𝗕𝗼𝘁𝘀", callback_data="m_mybots")
    )
    master_bot.send_message(
        msg.chat.id,
        "👑 *WELCOME TO PRANAV FATHER DEV ENGINE* 👑\n\n"
        "यहाँ आप 1 सेकंड में **अपना खुद का Telegram SMM Reseller Bot** बना सकते हैं!\n\n"
        "नया बॉट लाइव करने के लिए नीचे बटन दबाएँ:",
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
            "1. @BotFather खोलें और `/newbot` भेजें।\n"
            "2. अपने बॉट का नाम और यूज़रनेम बनाएँ।\n"
            "3. मिला हुआ **HTTP API Token** यहाँ चैट में भेजें:",
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
            master_bot.send_message(cid, f"📂 *आपके सक्रिय बॉट्स:*\n\n{txt}\n\nअपने बॉट में जाकर `/admin` दबाएँ!", parse_mode="Markdown")
        else:
            master_bot.send_message(cid, "❌ आपका कोई बॉट नहीं है। CYOB दबाकर बनाएँ!")

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
            master_bot.send_message(cid, "❌ अमान्य टोकन! BotFather से सही टोकन भेजें।")
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
            master_bot.send_message(cid, "⚠️ यह टोकन पहले से सिस्टम में जुड़ा हुआ है!")
            conn.close()
            return
        conn.close()

        # नया चाइल्ड बॉट तुरंत लाइव चालू
        t = threading.Thread(target=run_child_bot, args=(bot_id, uid, token, bot_user, bot_name), daemon=True)
        t.start()
        active_child_bots[token] = t

        master_bot.send_message(
            cid,
            f"🎉 *आपका नया बॉट लाइव हो गया!*\n\n"
            f"🤖 बॉट: @{bot_user}\n"
            f"👑 मालिक: `{uid}`\n\n"
            f"👉 अभी @{bot_user} खोलें और **/admin** भेजकर अपना पूरा एडमिन पैनल इस्तेमाल करें!",
            parse_mode="Markdown"
        )

# ==============================================================================
# 6. रीस्टार्ट पर लोड व सर्वर
# ==============================================================================
def reload_all_bots():
    time.sleep(2)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT bot_id, owner_id, bot_token_enc, bot_username, bot_name FROM child_bots WHERE status='active'")
    rows = cur.fetchall()
    conn.close()

    for r in rows:
        try:
            token = cipher_suite.decrypt(r["bot_token_enc"].encode()).decode()
            t = threading.Thread(target=run_child_bot, args=(r["bot_id"], r["owner_id"], token, r["bot_username"], r["bot_name"]), daemon=True)
            t.start()
            active_child_bots[token] = t
        except Exception:
            pass

@app.route('/')
def home():
    return jsonify({"status": "live", "engine": "Pranav Father Dev Master Engine", "bots_online": len(active_child_bots)}), 200

if __name__ == "__main__":
    threading.Thread(target=reload_all_bots, daemon=True).start()
    if master_bot and MASTER_BOT_TOKEN:
        threading.Thread(target=lambda: master_bot.infinity_polling(skip_pending=True), daemon=True).start()
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)
