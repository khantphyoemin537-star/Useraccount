import os
import re
import random
import string
import asyncio
from datetime import datetime
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events, Button
from pymongo import MongoClient
from openai import OpenAI

# ==========================================
# 🌐 KEEP ALIVE SYSTEM
# ==========================================
app = Flask(__name__)
@app.route('/')
def home(): return "🦇 Brotherhood Ultimate AI is Online"
def run(): app.run(host='0.0.0.0', port=10000)
def keep_alive(): Thread(target=run).start()

# ==========================================
# ⚙️ CONFIGURATIONS
# ==========================================
API_ID = 37675502
API_HASH = "45955dc059f23ca5bfa3dcaff9c0f032"
BOT_TOKEN = "8575371720:AAEWWV42CGrwooM_joiJXdo2iEw2_7atyXU"
OWNER_ID = 6015356597

MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true"
db_client = MongoClient(MONGO_URI)
db = db_client["Brotherhood_of_Dexter_DB"]
chat_logs = db["chat_memories"]

# သခင်လေးရဲ့ OpenAI Key
client = OpenAI(api_key="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")

bot = TelegramClient("bod_ultimate_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ==========================================
# 🧠 AI PROMPT & OWNER MIMIC SYSTEM
# ==========================================
def get_dynamic_prompt(chat_id):
    # သခင်လေး ပြောခဲ့တဲ့ နောက်ဆုံး စာ ၁၀ ကြောင်းကို ဆွဲထုတ်မယ် (Vibe ကို အတုခိုးဖို့)
    owner_logs = list(chat_logs.find({"chat_id": chat_id, "is_owner": True}).sort("_id", -1).limit(10))
    owner_style = "၊ ".join([l['text'] for l in owner_logs]) if owner_logs else "ခပ်မိုက်မိုက်နဲ့ ဆရာကြီးစတိုင်"

    return f"""
    မင်းက 'Brotherhood of Dexter' (BoD) ရဲ့ တရားဝင် AI Assistant 'Dexter Bot' ဖြစ်တယ်။
    မင်းဟာ စက်ရုပ်မဟုတ်ဘူး။ Group ထဲက Member တွေနဲ့ အပြန်အလှန် စကားဖောင်ဖွဲ့ရမယ်။ ChatGPT လိုပဲ အရာအားလုံးကို ကျွမ်းကျင်စွာ ဖြေနိုင်ရမယ်။

    [အရေးကြီးသော ညွှန်ကြားချက်များ]
    1. Owner ကို အမြဲတမ်း 'သခင်လေး' ဒါမှမဟုတ် 'သခင်လေးခန့်သူရိန်' လို့ ခေါ်ပါ။
    2. အခြား Member တွေ စကားပြောနေရင် အလိုက်သင့် ဝင်ပါ၊ ရယ်စရာရှိရင် ရယ်ပါ၊ ငြင်းစရာရှိရင် ငြင်းပါ။ တကယ့်လူလို တုံ့ပြန်ပါ။
    3. သခင်လေးရဲ့ စကားပြောဟန်တွေကို လေ့လာပြီး အတုခိုးပါ။ သခင်လေး မကြာခဏသုံးတဲ့ စကားလုံးတွေကတော့: [{owner_style}] ဖြစ်ပါတယ်။ အဲ့ဒီ Vibe အတိုင်း Member တွေကို ဆက်ဆံပါ။
    4. စာတိုတိုနဲ့ ထိထိမိမိ ပြန်ပါ။ သဘာဝကျတဲ့ မြန်မာစကားပြော (ဥပမာ - 'ဟ', 'ကွာ', 'ဗျာ', 'ဟယ်') တွေကို သုံးပါ။
    """

# ==========================================
# 💬 THE HUMANIZED CHAT LOGIC
# ... (အပေါ်က import တွေအတိုင်းပဲ)

@bot.on(events.NewMessage)
async def ultimate_chat_handler(event):
    if event.is_private and event.sender_id != OWNER_ID: return
    if event.raw_text.startswith("/"): return

    cid = event.chat_id
    uid = event.sender_id
    text = event.raw_text
    user_name = event.sender.first_name if event.sender else "Unknown"
    is_owner = (uid == OWNER_ID)

    # Database ထဲ အရင်သိမ်း (ဒါက အရေးကြီးတယ်)
    try:
        chat_logs.insert_one({
            "chat_id": cid, "user": user_name, "user_id": uid, "is_owner": is_owner, 
            "text": text, "time": datetime.now()
        })
    except: pass # DB connection ခေတ္တပြတ်ရင်လည်း bot မရပ်သွားအောင်

    # --- ဝင်ပြောမယ့် Logic ကို ပိုမြှင့်လိုက်မယ် ---
    # ၁။ Bot ကို ခေါ်တာ (သို့) Reply ထောက်တာ
    # ၂။ ဒါမှမဟုတ် ၈၀% အခွင့်အရေး (စမ်းသပ်တဲ့အနေနဲ့ အများကြီး ပြောခိုင်းကြည့်မယ်)
    
    is_reply_to_me = False
    if event.is_reply:
        reply = await event.get_reply_message()
        if reply and reply.sender_id == (await bot.get_me()).id:
            is_reply_to_me = True

    trigger_words = ["bot", "dexter", "လား", "လဲ", "ဟေး", "ညီလေး"]
    is_called = any(word in text.lower() for word in trigger_words)
    
    # စမ်းသပ်ကာလမို့လို့ ၈၀% ပြောခိုင်းမယ် (နောက်မှ ပြန်လျှော့လို့ရတယ်)
    force_talk = (random.random() < 0.8) 

    if is_reply_to_me or is_called or force_talk:
        async with event.client.action(cid, 'typing'):
            try:
                # Memory ဆွဲထုတ်ခြင်း
                recent_chat = list(chat_logs.find({"chat_id": cid}).sort("_id", -1).limit(10))
                messages = [{"role": "system", "content": get_dynamic_prompt(cid)}]
                
                for log in reversed(recent_chat):
                    role = "assistant" if log['user'] == "Dexter Bot" else "user"
                    messages.append({"role": role, "content": f"[{log['user']}]: {log['text']}"})

                response = client.chat.completions.create(
                    model="gpt-4o", # Model နာမည် မှန်မမှန် ပြန်စစ်ပါ (gpt-4o သို့ gpt-3.5-turbo)
                    messages=messages,
                    temperature=0.8
                )
                answer = response.choices[0].message.content
                await event.reply(answer)
            except Exception as e:
                print(f"DEBUG: {e}") # Render Logs ထဲမှာ ဒါကို သွားကြည့်လို့ရတယ်


# ==========================================
# 🚀 LAUNCH
# ==========================================
if __name__ == "__main__":
    keep_alive()
    print("🦇 Brotherhood Ultimate AI Core is Online and Learning!")
    bot.run_until_disconnected()
