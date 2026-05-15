import os
import asyncio
import random
import threading
import http.server
import socketserver
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from pymongo import MongoClient

# --- [CONFIGURATION - HARDCODED] ---
# ကိုကို့ရဲ့ အချက်အလက်များကို ဒီမှာပဲ တိုက်ရိုက်ထည့်ထားပါတယ်
API_ID = 33936355
API_HASH = 'f35be5538f9b722bd0de4d58cfb4cd98'
STRING_SESSION = '1BVtsOIMBuxjcz82O2hMnD6vHgFX8Zx7JagPEqCf2kEl0GXoGcJ_4FBnLrWPyGAoancBiTWREyzMmsHI3o3wV6KeOSlGqjNC8TlQJlpEqEhV3E-SroyUK6srteJorN0A5nSv3aIeFm5Z9RFfviC8NAALboOmkSZD_Yy_fgQasKUwLxkoXLL1wkhEB7B4Z_YB8Ws5uQbRXrxBc-duys2Ec41bjqIFVGgdVX7Q_QqBc-iHrczTNpAq6jMLqur9oSU5aiLZHLwj9t3T8EwZESGD1z3gPhwLxyER2xyM-gudSUD-arBn0Ol1NUjKuyJdOOJTxyjcWMA6E-pXxVy-36ujAAOVSklqbrPo='
OWNER_ID = 5741569756
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/?retryWrites=true&w=majority&tlsAllowInvalidCertificates=true"

# MongoDB Setup
db_client = MongoClient(MONGO_URI)
db = db_client['telegram_bot']
filters_col = db["filters"]

# UserBot Client
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

is_running = {}

# --- [RENDER PORT BINDING FIX] ---
def keep_alive():
    """Render မှာ 'No open ports' error မတက်အောင် dummy port တစ်ခု ဖွင့်ထားခြင်း"""
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        httpd.serve_forever()

def get_random_text():
    try:
        all_filters = list(filters_col.find())
        if all_filters:
            return random.choice(all_filters).get('text', 'သေမယ်နော်')
    except:
        pass
    return "သေမယ်နော်"

# --- [COMMANDS] ---

@client.on(events.NewMessage(pattern=r'^သေမယ်နော်'))
async def start_spam(event):
    if event.sender_id != OWNER_ID: return
    chat_id = event.chat_id
    reply = await event.get_reply_message()
    
    # Mention format
    mention = ""
    if reply:
        mention = f"<a href='tg://user?id={reply.sender_id}'>@{reply.sender.username or reply.sender.first_name}</a>"
    elif len(event.text.split()) > 1:
        mention = event.text.split(maxsplit=1)[1]

    is_running[chat_id] = True
    await event.delete()

    while is_running.get(chat_id):
        try:
            db_text = get_random_text()
            spam_msg = f"{mention} {db_text}" if mention else db_text
            await client.send_message(chat_id, spam_msg, parse_mode='html')
            await asyncio.sleep(2)
        except:
            break

@client.on(events.NewMessage(pattern=r'^ရပ်လိုက်မယ်$'))
async def stop_spam(event):
    if event.sender_id != OWNER_ID: return
    is_running[event.chat_id] = False
    await event.respond("<blockquote>🛑 Spam စစ်ဆင်ရေးကို ရပ်တန့်လိုက်ပါပြီ။</blockquote>", parse_mode='html')

print("Dexter's UserBot is starting on Render...")

# Port Fix ကို Background မှာ Run မယ်
threading.Thread(target=keep_alive, daemon=True).start()

client.start()
client.run_until_disconnected()
