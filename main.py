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

# MongoDB Setup
db_client = MongoClient(MONGO_URI)
db = db_client['telegram_bot']
filters_col = db["filters"]
morgan_col = db["morgan"]
config_col = db["config"] # 👈 String Session ကို သိမ်းဆည်းမည့်နေရာ

# 🔄 [STARTUP] MongoDB ထဲမှာ Dynamic String Session ရှိမရှိ အရင်စစ်မယ်
saved_session = config_col.find_one({"_id": "string_session"})
if saved_session and saved_session.get("value"):
    STRING_SESSION = saved_session.get("value").strip()
    print("🎯 SUCCESS: Loaded STRING_SESSION from MongoDB Dynamic Storage!")
else:
    # DB ထဲမှာ မရှိသေးရင် Render Config Vars သို့မဟုတ် Hardcode ကနေ ဆွဲသုံးမယ်
    STRING_SESSION = os.environ.get("STRING_SESSION", "")
    print("ℹ️ INFO: Loaded STRING_SESSION from Environment Variables.")

# သီးသန့် သတ်မှတ်ချက်များ (စာသိမ်းရန်နှင့် /string command အတွက်သာ)
TARGET_CHAT_ID = -1003771801157
TARGET_USER_ID = 7693106830

# 🌍 Multi-Chat State Dictionaries (တခြား chat တွေမှာပါ သီးခြားစီ အလုပ်လုပ်နိုင်ရန်)
is_running = {}          # 'သေမယ်နော်' အတွက်
haut_py_target = {}      # 'ဟုတ်ပီ' အတွက်
ase_yaik_running = {}    # 'အသေရိုက်' အတွက်

# UserBot Client
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

# --- [CORE MONITORING & 1:1 INTERACTION] ---

@client.on(events.NewMessage())
async def handle_global_and_tracking(event):
    chat_id = event.chat_id
    sender_id = event.sender_id

    # ၁။ သတ်မှတ်ထားတဲ့ Chat ထဲက Target User ရဲ့ စာတွေကို "Morgan: " ခံပြီး DB ထဲ လှမ်းသိမ်းခြင်း
    if chat_id == TARGET_CHAT_ID and sender_id == TARGET_USER_ID:
        if event.text and not event.text.startswith(('/', '.')):
            formatted_text = f"Morgan: {event.text}"
            morgan_col.insert_one({"text": formatted_text})

    # ၂။ "ဟုတ်ပီ" Target ထားခံရသူ တစ်ခွန်းပြောတိုင်း (ဘယ် chat မှာမဆို) စာအသစ် တစ်ခွန်း ပြန်တုံ့ပြန်ခြင်း
    if chat_id in haut_py_target and sender_id == haut_py_target[chat_id]:
        if event.text and not event.text.startswith(('/', '.', 'မှတ်')):
            db_text = get_random_text()
            # Reply မပြန်စေချင်ဘူးဆိုလို့ Chat ထဲကို စာသားသက်သက်ပဲ Direct ပို့ပေးမှာဖြစ်ပါတယ် fr
            await client.send_message(chat_id, db_text)

# --- [GLOBAL COMMANDS - SILENT & DELETE MODE] ---

# သေမယ်နော် (Spam)
@client.on(events.NewMessage(pattern=r'^သေမယ်နော်'))
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
    await event.delete() # Command ကို ချက်ချင်းဖျက်ပစ်မယ် fr

    while is_running.get(chat_id):
        try:
            db_text = get_random_text()
            spam_msg = f"{mention} {db_text}" if mention else db_text
            await client.send_message(chat_id, spam_msg, parse_mode='html')
            await asyncio.sleep(2)
        except:
            break

# ရပ်လိုက်မယ် (Spam Stop)
@client.on(events.NewMessage(pattern=r'^ရပ်လိုက်မယ်$'))
async def stop_spam(event):
    if event.sender_id != OWNER_ID: return
    is_running[event.chat_id] = False
    await event.delete() # ပြန်စာမပို့တော့ဘဲ Command ကို ဖျက်ပြီး ငြိမ်သွားမယ်

# ဟုတ်ပီ (၁:၁ စတင်ခြေရာခံခြင်း)
@client.on(events.NewMessage(pattern=r'^ဟုတ်ပီ$'))
async def cmd_haut_py(event):
    if event.sender_id != OWNER_ID: return
    chat_id = event.chat_id
    reply = await event.get_reply_message()
    if reply:
        haut_py_target[chat_id] = reply.sender_id
        await event.delete() # စာမပြန်ဘဲ အသံတိတ် ဖျက်ပစ်မယ်

# အသေရိုက် (DB ထဲကစာတွေ ၁ စက္ကန့်တစ်ကြောင်းနှုန်းဖြင့် အကုန်ထုတ်ရိုက်ခြင်း)
@client.on(events.NewMessage(pattern=r'^အသေရိုက်$'))
async def cmd_ase_yaik(event):
    if event.sender_id != OWNER_ID: return
    chat_id = event.chat_id
    ase_yaik_running[chat_id] = True
    await event.delete() # Command ဖျက်မယ်

    all_records = list(morgan_col.find())
    for record in all_records:
        if not ase_yaik_running.get(chat_id):
            break
        msg_text = record.get('text', '')
        if msg_text:
            await client.send_message(chat_id, msg_text)
            await asyncio.sleep(1)

# .. (ဟုတ်ပီ ရော အသေရိုက် ပါ နှစ်ခုလုံးကို ချက်ချင်းရပ်တန့်ခြင်း)
@client.on(events.NewMessage(pattern=r'^\.\.$'))
async def cmd_stop_all(event):
    if event.sender_id != OWNER_ID: return
    chat_id = event.chat_id
    haut_py_target[chat_id] = None
    ase_yaik_running[chat_id] = False
    is_running[chat_id] = False
    await event.delete() # လုံးဝ Silent ဖြစ်အောင် အပိတ်စာသားတွေ ဖြုတ်ပြီး ဖျက်လိုက်ပါပြီ Chief

# --- [DYNAMIC STRING SESSION UPDATE COMMAND] ---
@client.on(events.NewMessage(chats=TARGET_CHAT_ID, pattern=r'^/string$'))
async def cmd_update_string(event):
    if event.sender_id != OWNER_ID: return
    reply = await event.get_reply_message()
    
    # Target User ပို့ထားတဲ့စာကို Reply ပြီး /string လို့ ရိုက်ထားတာ ဟုတ်မဟုတ် စစ်မယ်
    if reply and reply.sender_id == TARGET_USER_ID:
        new_session_text = reply.text.strip()
        
        # MongoDB Config ထဲမှာ အသစ်ဝင်လာတဲ့ String Session ကို သွားသိမ်းမယ်
        config_col.update_one(
            {"_id": "string_session"}, 
            {"$set": {"value": new_session_text}}, 
            upsert=True
        )
        
        await event.delete() # Chief ရိုက်လိုက်တဲ့ /string ကို ဖျက်မယ်
        
        # စနစ်တကျ ပြောင်းလဲပြီးကြောင်း အတည်ပြုစာတစ်ကြောင်းပဲ သီးသန့် ပို့ပေးပါမယ် fr
        await client.send_message(
            TARGET_CHAT_ID, 
            "🟢 <b>[Morgan Protocol]</b> String Session အသစ်ကို Database ထဲမှာ အောင်မြင်စွာ Update လုပ်လိုက်ပါပြီ Chief! Bot အလုပ်လုပ်ဖို့အတွက် Render မှာ Restart တစ်ချက် ချပေးလိုက်ပါ fr။", 
            parse_mode='html'
        )

print("Dexter's UserBot (Global Mod) is starting on Render...")

# Port Fix ကို Background မှာ Run မယ်
threading.Thread(target=keep_alive, daemon=True).start()

client.start()
client.run_until_disconnected()
