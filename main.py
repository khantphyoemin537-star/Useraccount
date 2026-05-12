import os
import asyncio
import random
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from pymongo import MongoClient

# --- [CONFIGURATION FROM ENV] ---
# Render ရဲ့ Dashboard မှာ ဒီ Variables တွေကို သွားထည့်ပေးရပါမယ်
API_ID = int(os.getenv("API_ID", 35644327))
API_HASH = os.getenv("API_HASH", "9c885c25537d7ce27842021a54cb3b59")
STRING_SESSION = os.getenv("STRING_SESSION")
OWNER_ID = int(os.getenv("OWNER_ID", 8624130825))
MONGO_URI = os.getenv("MONGO_URI")

# MongoDB Setup
db_client = MongoClient(MONGO_URI)
db = db_client['telegram_bot']
filters_col = db["filters"]

# UserBot Client Setup
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

# Spam အခြေအနေကို စစ်ရန်
is_running = {}

def get_random_text():
    """DB ထဲက filters တွေကို ကျပန်းဆွဲထုတ်ခြင်း"""
    try:
        all_filters = list(filters_col.find())
        if all_filters:
            return random.choice(all_filters).get('text', 'သေမယ်နော်')
    except Exception as e:
        print(f"DB Error: {e}")
    return "သေမယ်နော်"

# --- [COMMANDS] ---

@client.on(events.NewMessage(pattern=r'^သေမယ်နော်'))
async def start_spam(event):
    if event.sender_id != OWNER_ID: return
    
    chat_id = event.chat_id
    reply = await event.get_reply_message()
    
    # Mention format ပြင်ဆင်ခြင်း
    mention = ""
    if reply:
        mention = f"<a href='tg://user?id={reply.sender_id}'>@{reply.sender.username or reply.sender.first_name}</a>"
    elif len(event.text.split()) > 1:
        mention = event.text.split(maxsplit=1)[1]

    is_running[chat_id] = True
    await event.delete() # 'သေမယ်နော်' ဆိုတဲ့ စာသားကို ဖျက်မယ်

    while is_running.get(chat_id):
        try:
            db_text = get_random_text()
            spam_msg = f"{mention} {db_text}" if mention else db_text
            
            await client.send_message(chat_id, spam_msg, parse_mode='html')
            await asyncio.sleep(2) # ၂ စက္ကန့်ခြား တစ်ခါ
        except Exception:
            break

@client.on(events.NewMessage(pattern=r'^ရပ်$'))
async def stop_spam(event):
    if event.sender_id != OWNER_ID: return
    
    chat_id = event.chat_id
    if is_running.get(chat_id):
        is_running[chat_id] = False
        await event.respond("<blockquote>အရှင်သခင်တို့၏အရှင်သခင်ဆိုတာ အခုလို ညှာတာမှုမရှိဘူး</blockquote>", parse_mode='html')

print("BoD UserBot is Running on Render...")
client.start()
client.run_until_disconnected()
