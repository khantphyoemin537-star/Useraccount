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
API_ID = 33936355
API_HASH = 'f35be5538f9b722bd0de4d58cfb4cd98'
OWNER_ID = 5741569756
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/?retryWrites=true&w=majority&tlsAllowInvalidCertificates=true"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8338525059:AAEMDI6gBX0hzcCozymzVV7EmgDeh_73jeA")

# 🔑 Chief ပေးထားသော String Session အသစ်ကို တိုက်ရိုက် Hardcode ထည့်သွင်းထားသည် fr
STRING_SESSION = "1BVtsOIMBu7sFste9mzJP0evgBY40VOBd7PIxjaHd4Y8tLInNDGqkc98fRuF6lNV5_llUe7WW4zMaH_j9tTM9-CUHkPeaU0JCjDWzGsHJQmPT_aetRvziXNdItpQqh0xxqFjGDuhXE9pZ--hDn9usQUBvYfEX0R5-kttaC0Aic-OQxOnN-esT-y_hLgRkBwYAzA7n9UTn09gHYvYN9RV1ClCzCuY7TQEJmrYX9S-MoQ5TTD70QWOMB0L4lo2KgpSD0oqlFoYVKcXR8sOcTfBmsQr76ZfXkW_nHq7f_smdHeVZpLvCLvD7LKy2j5_U1zPthd0woT1emrShk9aY_puQPGUBlH15DYw="

# MongoDB Setup
db_client = MongoClient(MONGO_URI)
db = db_client['telegram_bot']
filters_col = db["filters"]
morgan_col = db["morgan"]

# သီးသန့် သတ်မှတ်ချက်များ (စာသိမ်းရန်အတွက်သာ)
TARGET_CHAT_ID = -1003771801157
TARGET_USER_ID = 7693106830

# 🌍 Multi-Chat State Dictionaries
is_running = {}          # 'သေမယ်နော်' အတွက်
haut_py_target = {}      # 'ဟုတ်ပီ' အတွက်
ase_yaik_running = {}    # 'အသေရိုက်' အတွက်

# --- [CLIENTS SETUP] ---
# ၁။ 🤖 Main Bot Client (Command တွေကို စောင့်ကြည့်ဖျက်ဆီးရန်)
bot1 = TelegramClient('main_bot_session', API_ID, API_HASH)

# ၂။ 👤 UserBot Client (စာထွက်ရိုက်မည့် အကောင့်)
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

# --- [RENDER PORT BINDING FIX] ---
def keep_alive():
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

# --- [🤖 MAIN BOT - TRACKING & COMMAND MONITORING] ---

@bot1.on(events.NewMessage())
async def handle_bot_monitoring(event):
    chat_id = event.chat_id
    sender_id = event.sender_id

    # ၁။ Target User ရဲ့ စာတွေကို "Morgan: " ခံပြီး DB ထဲ လှမ်းသိမ်းခြင်း
    if chat_id == TARGET_CHAT_ID and sender_id == TARGET_USER_ID:
        if event.text and not event.text.startswith(('/', '.')):
            formatted_text = f"Morgan: {event.text}"
            morgan_col.insert_one({"text": formatted_text})

    # ၂။ "ဟုတ်ပီ" ခြေရာခံခံရသူ စာရိုက်ရင် UserBot (client) ကနေ စာထွက်ရိုက်ပေးခြင်း
    if chat_id in haut_py_target and sender_id == haut_py_target[chat_id]:
        if event.text and not event.text.startswith(('/', '.', 'မှတ်')):
            db_text = get_random_text()
            try:
                await client.send_message(chat_id, db_text)
            except Exception as e:
                print(f"UserBot Send Error (Haut Py): {e}")

# --- [🤖 MAIN BOT - GLOBAL COMMANDS (SILENT & DELETE MODE)] ---

# သေမယ်နော် (Spam)
@bot1.on(events.NewMessage(pattern=r'^သေမယ်နော်'))
async def start_spam(event):
    if event.sender_id != OWNER_ID: return
    chat_id = event.chat_id
    reply = await event.get_reply_message()
    
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

# ရပ်လိုက်မယ်
@bot1.on(events.NewMessage(pattern=r'^ရပ်လိုက်မယ်$'))
async def stop_spam(event):
    if event.sender_id != OWNER_ID: return
    is_running[event.chat_id] = False
    await event.delete()

# ဟုတ်ပီ (၁:၁ စတင်ခြေရာခံခြင်း)
@bot1.on(events.NewMessage(pattern=r'^ဟုတ်ပီ$'))
async def cmd_haut_py(event):
    if event.sender_id != OWNER_ID: return
    chat_id = event.chat_id
    reply = await event.get_reply_message()
    if reply:
        haut_py_target[chat_id] = reply.sender_id
        await event.delete()

# အသေရိုက် (DB ထဲကစာတွေ ၁ စက္ကန့်တစ်ကြောင်းနှုန်းဖြင့် အကုန်ထုတ်ရိုက်ခြင်း)
@bot1.on(events.NewMessage(pattern=r'^အသေရိုက်$'))
async def cmd_ase_yaik(event):
    if event.sender_id != OWNER_ID: return
    chat_id = event.chat_id
    ase_yaik_running[chat_id] = True
    await event.delete()

    all_records = list(morgan_col.find())
    for record in all_records:
        if not ase_yaik_running.get(chat_id):
            break
        msg_text = record.get('text', '')
        if msg_text:
            try:
                await client.send_message(chat_id, msg_text)
            except Exception as e:
                print(f"UserBot Send Error (Ase Yaik): {e}")
            await asyncio.sleep(1)

# .. (လုပ်ဆောင်ချက်အားလုံး ရပ်တန့်ခြင်း)
@bot1.on(events.NewMessage(pattern=r'^\.\.$'))
async def cmd_stop_all(event):
    if event.sender_id != OWNER_ID: return
    chat_id = event.chat_id
    haut_py_target[chat_id] = None
    ase_yaik_running[chat_id] = False
    is_running[chat_id] = False
    await event.delete()

# --- [ASYNC STARTING LOOP] ---
async def main():
    print("🚀 Starting Main Bot (bot1)...")
    await bot1.start(bot_token=BOT_TOKEN)
    
    print("🚀 Starting UserBot Client with New Hardcoded String Session...")
    try:
        await client.start()
    except Exception as e:
        print(f"⚠️ UserBot Start Error: {e}")

    print("🔥 Setup complete! Both Clients are up and running smoothly fr!")
    await asyncio.gather(
        bot1.run_until_disconnected(),
        client.run_until_disconnected()
    )

if __name__ == '__main__':
    threading.Thread(target=keep_alive, daemon=True).start()
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
