import asyncio
import logging
import random
import os
import threading
from flask import Flask
from pymongo import MongoClient
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from html import escape as escape_html

# ==========================================
# 🌐 FLASK KEEP-ALIVE
# ==========================================
app = Flask('')
@app.route('/')
def home(): return "Userbot Sovereign Active!"

def run_flask(): 
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

logging.basicConfig(level=logging.ERROR)

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
API_ID = 30765851
API_HASH = '235b0bc6f03767302dc75763508f7b75'
OWNER_ID = 6015356597
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true"
SESSION_STR = "1BVtsOKEBu16EIhQUXghjELGgsrRuoCO7I6zfWzbjZfOPhXekopXekO4NdLynd2tWlX-syuXr4v4ilR2PTNXdj-jv0RJQSVQWwKGmH46E8wB22xPbUeDsroei1H1Rx75W_GFTev-jrZlTeCUe7JlLNKKiU24JLEnQfPzDBWMVI9iSmFW3SkssJyvYVyk6nwJrMzae_YsCwm5igewvv8BWer73oPBBMJqA5CXGpAdq_51q_MOXrmoWlJ6eVQslyIpohhdmRQfXEZWiYxxLZ8SAtDMPPYnlW8UqtDfkWQeOq6GlNaefvHoaGtgCLt6wCfPJQ4lGYXUDfArZ4KXb-cb_kSqKxs8ExSo="

# ==========================================
# 🗄️ DATABASE SETUP
# ==========================================
client_mongo = MongoClient(MONGO_URI)
db = client_mongo["telegram_bot"]
filters_col = db["filters"] 
allow_col = db["allowed_users"]

client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)

bully_tasks = {}
auto_delete_users = {}

def bq_format(text): 
    safe_text = escape_html(str(text))
    return f"<blockquote><b>{safe_text}</b></blockquote>"

def is_allowed(user_id):
    if user_id == OWNER_ID: return True
    return allow_col.find_one({"user_id": user_id}) is not None

# ==========================================
# 🛡️ CUSTOM COMMANDS (NO PREFIX)
# ==========================================

# [1] "သေမယ်နော်" - Bully Start
@client.on(events.NewMessage(pattern=r'^သေမယ်နော်$'))
async def userbot_bully(event):
    if not is_allowed(event.sender_id): return
    reply = await event.get_reply_message()
    if not reply: return 
    
    try: await event.delete()
    except: pass

    chat_id = event.chat_id
    t = await reply.get_sender()
    if not t or t.id == OWNER_ID: return

    bully_tasks[chat_id] = True
    mention = f"<a href='tg://user?id={t.id}'>{escape_html(t.first_name)}</a>"
    words = [w.get("text") for w in filters_col.find() if w.get("text")]
    if not words: words = ["စောက်ရူး", "ခွေးကောင်"]

    while bully_tasks.get(chat_id):
        try: 
            await client.send_message(chat_id, f"{mention} {bq_format(random.choice(words))}", reply_to=reply.id, parse_mode='html')
            await asyncio.sleep(0.2) 
        except: break

# [2] "ဆက်ကိုက်" - Stop Bully (ရပ်လိုက်မယ်)
@client.on(events.NewMessage(pattern=r'^ဆက်ကိုက်$'))
async def stop_bully(event):
    if not is_allowed(event.sender_id): return
    try: await event.delete()
    except: pass
    bully_tasks[event.chat_id] = False
    await event.respond(bq_format("အခုနားဆိုလို့နားလိုက်မယ်၊စောက်ချိုးမပြေရင်ထပ်ဆဲပေးမယ်"))

# [3] /bq, /delete, /undelete commands (ဒါတွေက prefix ပါမြဲပါပဲ)
@bot_client.on(events.NewMessage(outgoing=True))
async def auto_animate_bq(event):
    # Command တွေ (ဥပမာ /id, /gid) ဆိုရင် Animation မလုပ်အောင် skip မယ်
    if event.text.startswith('/') or event.text.startswith('.'):
        return

    original_text = event.text
    full_msg = ""
    
    # စာသားကို တစ်လုံးချင်းစီ ခွဲထုတ်ပြီး animation လုပ်မယ်
    # ဥပမာ - "ဟိုင်း" -> "ဟ", "ဟို", "ဟိုင်", "ဟိုင်း"
    frames = []
    for i in range(1, len(original_text) + 1):
        frames.append(original_text[:i])

    # Animation စတင်မယ်
    try:
        for frame in frames:
            # Blockquote format ထဲကို ထည့်တယ်
            animated_text = f"<blockquote><b>{escape_html(frame)}</b></blockquote>"
            
            # စာသားကို edit လုပ်ပြီး animation ပြမယ်
            await event.edit(animated_text, parse_mode='html')
            
            # Animation မြန်နှုန်း (0.1 စက္ကန့်)
            await asyncio.sleep(0.3)
            
    except Exception as e:
        # Error တက်ရင် (ဥပမာ စာတိုလွန်းရင်) နောက်ဆုံးစာသားကိုပဲ တန်းပြမယ်
        final_text = f"<blockquote><b>{escape_html(original_text)}</b></blockquote>"
        await event.edit(final_text, parse_mode='html')
@client.on(events.NewMessage(pattern=r'^/delete'))
async def del_cmd(event):
    if not is_allowed(event.sender_id): return
    reply = await event.get_reply_message()
    if reply:
        chat_id = event.chat_id
        if chat_id not in auto_delete_users: auto_delete_users[chat_id] = []
        auto_delete_users[chat_id].append(reply.sender_id)
        await event.respond(bq_format("သူ့စာတွေကို လိုက်ဖျက်ပါမယ်။"))

@client.on(events.NewMessage(pattern=r'^/undelete'))
async def undel_cmd(event):
    if not is_allowed(event.sender_id): return
    reply = await event.get_reply_message()
    if reply and event.chat_id in auto_delete_users:
        if reply.sender_id in auto_delete_users[event.chat_id]:
            auto_delete_users[event.chat_id].remove(reply.sender_id)
            await event.respond(bq_format("စာဖျက်တာ ရပ်လိုက်ပါပြီ။"))

# [4] Auto Deletion Watcher
@client.on(events.NewMessage())
async def watcher(event):
    chat_id = event.chat_id
    if chat_id in auto_delete_users and event.sender_id in auto_delete_users[chat_id]:
        await asyncio.sleep(3)
        try:
            u = await event.get_sender()
            is_bot = u.bot if u else False
            await event.delete()
            if is_bot:
                t = "Botစာတွေဖျက်ပြီ ငါ့စာလည်း 5sec နေရင်ပျက်ပြီ"
                n = await event.respond(f"{t}\n⏱ 5")
                for i in range(4, 0, -1):
                    await asyncio.sleep(1); await n.edit(f"{t}\n⏱ {i}")
                await asyncio.sleep(1); await n.delete()
        except: pass

# ==========================================
# 🚀 RUN
# ==========================================
async def main():
    threading.Thread(target=run_flask, daemon=True).start()
    await client.start()
    print("✅ Userbot Active: Commands changed to 'သေမယ်နော်' and 'ဆက်ကိုက်'")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())

