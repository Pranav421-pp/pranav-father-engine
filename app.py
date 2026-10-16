import os
import random
import string
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pranav_live_secret_key_2026')

# इन-मेमोरी या सिंपल डिक्शनरी डेटाबेस (इसे SQLite से भी बड़ा कर सकते हैं)
users_db = {}  # {username: {"pin": "123456", "is_admin": False}}
bots_db = {}   # {bot_token: {"bot_name": name, "owner": username, "commands": {}}}
chats_db = []  # [{"sender": "...", "receiver": "...", "message": "..."}]

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('chat'))
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    username = request.form.get('username').strip()
    pin = request.form.get('pin').strip()
    
    if not username or len(pin) != 6:
        return "Invalid Username or 6-digit PIN!", 400
    
    if username in users_db:
        return "Username already taken! Choose another.", 400
    
    # पहला यूजर ऑटोमैटिक एडमिन बन जाएगा
    is_admin = len(users_db) == 0
    users_db[username] = {"pin": pin, "is_admin": is_admin, "banned": False}
    
    session['username'] = username
    return redirect(url_for('chat'))

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username').strip()
    pin = request.form.get('pin').strip()
    
    if username in users_db and users_db[username]["pin"] == pin:
        if users_db[username].get("banned", False):
            return "Your account has been banned by Admin!", 403
        session['username'] = username
        if users_db[username]["is_admin"]:
            return redirect(url_for('admin_panel'))
        return redirect(url_for('chat'))
    
    return "Wrong Username or 6-digit PIN!", 401

@app.route('/chat')
def chat():
    if 'username' not in session:
        return redirect(url_for('index'))
    return render_template('chat.html', username=session['username'], chats=chats_db)

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    msg = data.get('message')
    receiver = data.get('receiver', 'Global')
    
    chat_item = {"sender": session['username'], "receiver": receiver, "message": msg}
    chats_db.append(chat_item)
    return jsonify({"status": "success", "chat": chat_item})

# --- BOTFATHER SYSTEM (बॉट बनाने और टोकन देने का सिस्टम) ---
@app.route('/botfather', methods=['GET', 'POST'])
def botfather():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    token_msg = None
    if request.method == 'POST':
        bot_name = request.form.get('bot_name')
        # रैंडम बोट टोकन जनरेट करना जैसे Telegram BotFather करता है
        token = "bot_" + ''.join(random.choices(string.ascii_letters + string.digits, k=24))
        bots_db[token] = {"bot_name": bot_name, "owner": session['username'], "commands": {}}
        token_msg = f"Your Bot Token: {token}"
        
    return render_template('botfather.html', token_msg=token_msg, bots=bots_db)

# --- ADMIN PANEL (पूरा कंट्रोल, थीम, बैन, और ब्रॉडकास्ट) ---
@app.route('/admin')
def admin_panel():
    if 'username' not in session or not users_db.get(session['username'], {}).get("is_admin", False):
        return "Access Denied! Admins only.", 403
    return render_template('admin.html', users=users_db, bots=bots_db)

@app.route('/admin/ban/<username>')
def ban_user(username):
    if 'username' in session and users_db.get(session['username'], {}).get("is_admin", False):
        if username in users_db:
            users_db[username]["banned"] = True
    return redirect(url_for('admin_panel'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
