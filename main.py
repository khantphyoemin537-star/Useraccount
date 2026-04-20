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
def home(): return "BoDx Sovereign Guard Active!"

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

shoot_tasks = {} # /ပစ်သတ် အတွက်
tracking_targets = {} # /ပစ် (Target Tracking) အတွက်
bot_ids = []

def is_allowed(user_id):
    if user_id == OWNER_ID: return True
    return allow_col.find_one({"user_id": user_id}) is not None

# ==========================================
# 🎯 PROTECTION & TRACKING WATCHER
# ==========================================

@main_bot.on(events.NewMessage())
async def global_watcher(event):
    if event.is_private or not event.text: return
    if event.sender_id in bot_ids: return

    chat_id = event.chat_id
    text = event.text.strip()

    # 1. Owner Protection (ခွင့်ပြုချက်မရှိသူ Cmd လာသုံးလျှင် ၄ ကောင်လုံးက မတူညီသောစာဖြင့် ဆဲဆိုခြင်း)
    protection_cmds = ["ချိန်ထား", "ပစ်သတ်", "ချီးမွမ်း"]
    if any(text.startswith(c) for c in protection_cmds):
        if not is_allowed(event.sender_id):
            intruder = await event.get_sender()
            name = escape_html(intruder.first_name)
            insults = [
                f"{name} မင်းက ငါတို့ Creator ရဲ့ စနစ်ကို လာထိတာလား? သေချင်နေပြီထင်တယ်!",
                f"အမိန့်ပေးရအောင် မင်းက ဘာကောင်မို့လို့လဲ? {name} ခွေးမသား... မင်းကိုပါ ချိန်ထားလိုက်ပြီ။",
                f"{name} လို အဆင့်မရှိတဲ့ကောင်က ငါတို့ Creator Command တွေကို လာကိုင်တာလား? သေမယ်နော်!",
                f"မင်းကို ငါတို့ ၄ ယောက် အသေသတ်ဖို့ အသင့်ပဲ။ နောက်တစ်ခါ လာစမ်းရင် မင်းအလှည့်ပဲ။"
            ]
            for i, bot in enumerate(bots):
                try:
                    await bot.send_message(chat_id, insults[i], reply_to=event.id)
                except: pass
            return

    # 2. Target Tracking (ပစ် အမိန့်ပေးခံထားရသူ စာပို့တိုင်း ၁ ကောင်စီ လိုက်ဆော်ခြင်း)
    if chat_id in tracking_targets and event.sender_id == tracking_targets[chat_id]:
        words = [w.get("text") for w in filters_col.find() if w.get("text")]
        if not words: words = []
        
        target = await event.get_sender()
        mention = f"<a href='tg://user?id={target.id}'>{escape_html(target.first_name)}</a>"
        
        attack_bot = random.choice(bots)
        try:
            await attack_bot.send_message(chat_id, f"{mention} {random.choice(words)}", parse_mode='html')
        except: pass

# ==========================================
# 🔫 FIRING SQUAD COMMANDS
# ==========================================

# --- ချိန်ထား ---
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

# --- ပစ်သတ် (Reply အမြန်ဆော်ခြင်း) ---
@main_bot.on(events.NewMessage(pattern=r'^ပစ်သတ်$'))
async def fire_target(event):
    if not is_allowed(event.sender_id): return
    reply = await event.get_reply_message()
    if not reply: return

    chat_id = event.chat_id
    target = await reply.get_sender()
    if not target: return
    
    shoot_tasks[chat_id] = True 
    mention = f"<a href='tg://user?id={target.id}'>{escape_html(target.first_name)}</a>"
    
    words = [w.get("text") for w in filters_col.find() if w.get("text")]
    if not words: words = []

    bot_index = 0
    while shoot_tasks.get(chat_id):
        try:
            current_bot = bots[bot_index % len(bots)]
            attack_msg = f"{mention} {random.choice(words)}"
            await current_bot.send_message(chat_id, attack_msg, parse_mode='html')
            bot_index += 1
            await asyncio.sleep(0.4) 
        except: break

# --- ပစ် (Target Tracking - စာပို့တိုင်း လိုက်ဆော်ခြင်း) ---
@main_bot.on(events.NewMessage(pattern=r'^ပစ်$'))
async def track_target(event):
    if not is_allowed(event.sender_id): return
    reply = await event.get_reply_message()
    if not reply: return

    target_id = reply.sender_id
    tracking_targets[event.chat_id] = target_id
    
    target = await reply.get_sender()
    name = escape_html(target.first_name)
    await event.respond(f"{name} ကို ပစ်မှတ်ထားလိုက်ပြီ။ သူစာပို့တိုင်း ငါတို့ လိုက်ပစ်မယ်။")

# --- ရပ် / အပစ်ရပ် ---
@main_bot.on(events.NewMessage(pattern=r'^(ရပ်|အပစ်ရပ်)$'))
async def stop_actions(event):
    if not is_allowed(event.sender_id): return
    chat_id = event.chat_id
    
    # ပစ်သတ် လုပ်နေတာ ရပ်မည်
    shoot_tasks[chat_id] = False
    
    # Tracking လုပ်နေတာ ရပ်မည်
    if chat_id in tracking_targets:
        del tracking_targets[chat_id]
        
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
    print("✅ BoDx Sovereign Guard & Firing Squad Online!")
    await asyncio.gather(*(bot.run_until_disconnected() for bot in bots))

if __name__ == "__main__":
    asyncio.run(start_system())

