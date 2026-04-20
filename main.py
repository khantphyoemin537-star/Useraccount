import asyncio
import logging
import random
import os
import threading
from flask import Flask
from pymongo import MongoClient
from telethon import TelegramClient, events
from html import escape as escape_html

# ==========================================
# 🌐 FLASK KEEP-ALIVE
# ==========================================
app = Flask('')
@app.route('/')
def home(): return "BoDx Guard System Active!"

def run_flask(): 
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

logging.basicConfig(level=logging.ERROR)

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
OWNER_ID = 6015356597
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true"
APP_ID = 30765851
APP_HASH = '235b0bc6f03767302dc75763508f7b75'

TOKENS = [
    "7857238353:AAEkDQnXqxyvXOQufwJwzZ7tXlwrmzM6XyI",
    "8565944163:AAE5tew3A1a6GkOw69vMPYSgV2obyO-wPz4",
    "8704927120:AAFUIrQhFaly9yRkEhsD4Yu5FiIEfj1F7Oo",
    "7716597590:AAF4uR9g-cOBLssQcPfqe2ROIxnr3dd-PDQ"
]

# ==========================================
# 🗄️ DATABASE SETUP
# ==========================================
client_mongo = MongoClient(MONGO_URI)
db = client_mongo["telegram_bot"]
filters_col = db["filters"] 
allow_col = db["allowed_users"]

bots = [TelegramClient(f'session_bot_{i}', APP_ID, APP_HASH) for i in range(len(TOKENS))]
main_bot = bots[0]

shoot_tasks = {} 
bot_ids = []

def is_allowed(user_id):
    if user_id == OWNER_ID: return True
    return allow_col.find_one({"user_id": user_id}) is not None

# ==========================================
# 🎯 PROTECTION & ALERT LOGIC
# ==========================================

# --- [Watcher] Owner Protection & Intruder Warning ---
@main_bot.on(events.NewMessage())
async def protector_watcher(event):
    if event.is_private or not event.text: return
    if event.sender_id in bot_ids: return

    # 1. Owner ကို စော်ကားသူ/Reply ထောက်သူအား ကာကွယ်ခြင်း
    reply = await event.get_reply_message()
    if reply and reply.sender_id == OWNER_ID and event.sender_id != OWNER_ID:
        # Owner ကို Reply ထောက်ရင် Bot တွေက ဝိုင်းဆော်မည်
        words = [w.get("text") for w in filters_col.find() if w.get("text")]
        attack_word = random.choice(words) if words else "ငါတို့ရဲ့ Creator ကို မင်းက ဘာမှတ်နေလဲ ခွေးမသား!"
        for bot in bots:
            try:
                await bot.send_message(event.chat_id, f"မင်းက ငါတို့ Creator ကို လာစမ်းတာလား? {attack_word}", reply_to=event.id)
                await asyncio.sleep(0.3)
            except: pass
        return

    # 2. Allow user မဟုတ်သူ Cmd လာသုံးရင် သတိပေးခြင်း
    cmds = ["ချိန်ထား", "ပစ်သတ်", "အပစ်ရပ်"]
    if any(event.text.startswith(c) for c in cmds):
        if not is_allowed(event.sender_id):
            intruder = await event.get_sender()
            name = escape_html(intruder.first_name)
            warning = f"ဖာသည်မသား {name}... မင်းက ဘာကောင်မို့လို့ ငါတို့စီမှာ အမိန့်လာပေးနေတာလဲ? မင်းကိုပါ ငါတို့ 4 ယောက် ပစ်သတ်ဖို့ အသင့်ချိန်ထားလိုက်ပြီ။"
            for bot in bots:
                try:
                    await bot.send_message(event.chat_id, warning, reply_to=event.id)
                except: pass
            return

# ==========================================
# 🔫 COMMANDS (For Owner & Allowed Users)
# ==========================================

@main_bot.on(events.NewMessage(pattern=r'^ချိန်ထား$'))
async def aim_target(event):
    if not is_allowed(event.sender_id): return
    reply = await event.get_reply_message()
    if not reply: return

    sender = await event.get_sender()
    name = escape_html(sender.first_name)
    
    if event.sender_id == OWNER_ID:
        msg = f"<a href='tg://user?id={event.sender_id}'>{name}</a> ရဲ့ အမိန့်ပေးမှုအရ ဒီကောင့်ကို ပစ်သတ်ဖို့ အသင့်ချိန်ထားပါပြီ။"
    else:
        msg = f"ဗိုလ်ကြီး <a href='tg://user?id={event.sender_id}'>{name}</a> ရဲ့ အမိန့်ပေးမှုအရ ဒီကောင့်ကို ပစ်သတ်ဖို့ အသင့်ချိန်ထားပြီ ။"

    tasks = [bot.send_message(event.chat_id, msg, reply_to=reply.id, parse_mode='html') for bot in bots]
    await asyncio.gather(*tasks)

@main_bot.on(events.NewMessage(pattern=r'^ပစ်သတ်$'))
async def fire_target(event):
    if not is_allowed(event.sender_id): return
    reply = await event.get_reply_message()
    if not reply: return

    chat_id = event.chat_id
    shoot_tasks[chat_id] = True 
    sender = await event.get_sender()
    name = escape_html(sender.first_name)
    authority = f"<a href='tg://user?id={event.sender_id}'>{name}</a> အာဏာအရ ဒီကောင့်ကို အ​သေပစ်သတ်ပြီ"

    words = [w.get("text") for w in filters_col.find() if w.get("text")]
    if not words: words = []

    bot_index = 0
    while shoot_tasks.get(chat_id):
        try:
            current_bot = bots[bot_index % len(bots)]
            attack_msg = f"{authority}\n\n{random.choice(words)}"
            await current_bot.send_message(chat_id, attack_msg, reply_to=reply.id, parse_mode='html')
            bot_index += 1
            await asyncio.sleep(0.4) 
        except:
            break

@main_bot.on(events.NewMessage(pattern=r'^အပစ်ရပ်$'))
async def stop_fire(event):
    if not is_allowed(event.sender_id): return
    chat_id = event.chat_id
    if chat_id in shoot_tasks:
        shoot_tasks[chat_id] = False
        await event.reply("ငါတို့ 4 ယောက် ဒီခွေးမသားကို အ​သေသတ်ပေးထားတယ်။ပြန်ရှင်သန်ခွင့် မပေးဘူး")

# ==========================================
# 🚀 START SYSTEM
# ==========================================
async def start_system():
    threading.Thread(target=run_flask, daemon=True).start()
    for i, bot in enumerate(bots):
        await bot.start(bot_token=TOKENS[i])
        me = await bot.get_me()
        bot_ids.append(me.id)
    print("✅ BoDx Guard & Firing Squad System Online!")
    await asyncio.gather(*(bot.run_until_disconnected() for bot in bots))

if __name__ == "__main__":
    asyncio.run(start_system())
