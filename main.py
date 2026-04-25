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
# ==========================================
@bot.on(events.NewMessage)
async def chatgpt_style_handler(event):
    if event.is_private and event.sender_id != OWNER_ID: return
    if event.raw_text.startswith("/"): return

    cid = event.chat_id
    uid = event.sender_id
    text = event.raw_text
    user_name = event.sender.first_name if event.sender else "Unknown"
    is_owner = (uid == OWNER_ID)

    # Database ထဲကို လက်ရှိစာကို အရင်သိမ်းမယ် (မှတ်ဉာဏ်အတွက်)
    chat_logs.insert_one({
        "chat_id": cid, "user": user_name, "user_id": uid, "is_owner": is_owner, 
        "text": text, "time": datetime.now()
    })

    is_reply_to_me = False
    if event.is_reply:
        reply = await event.get_reply_message()
        if reply and reply.sender_id == (await bot.get_me()).id:
            is_reply_to_me = True

    # Bot ကို ခေါ်တာလား စစ်ဆေးခြင်း
    trigger_words = ["bot", "dexter", "လား", "လဲ", "ရေးပေး", "တွက်ပေး", "ဟေး"]
    is_mentioned = any(w in text.lower() for w in trigger_words)

    # Member တွေ စကားပြောနေရင် ၁၅% အခွင့်အရေးနဲ့ အလိုက်တသိ ဝင်ပါမယ်
    spontaneous_join = (random.random() < 0.15) and len(text) > 5

    if is_reply_to_me or is_mentioned or spontaneous_join:
        async with event.client.action(cid, 'typing'):
            # Group တစ်ခုလုံးရဲ့ နောက်ဆုံး စကားဝိုင်း flow ကို ဆွဲထုတ်မယ် (စာကြောင်း ၁၅ ကြောင်း)
            recent_chat = list(chat_logs.find({"chat_id": cid}).sort("_id", -1).limit(15))
            
            # OpenAI အတွက် History တည်ဆောက်မယ်
            messages = [{"role": "system", "content": get_dynamic_prompt(cid)}]
            for log in reversed(recent_chat):
                role = "assistant" if log['user'] == "Dexter Bot" else "user"
                content_prefix = "" if role == "assistant" else f"[{log['user']}]: "
                messages.append({"role": role, "content": f"{content_prefix}{log['text']}"})

            try:
                # GPT-4o ကို သုံးပြီး တုံ့ပြန်ချက်တောင်းမယ်
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    temperature=0.85 # လူလို ပိုပြီး ဖန်တီးဉာဏ်ကောင်းအောင်
                )
                answer = response.choices[0].message.content
                
                # Bot ရဲ့ စာကိုလည်း မှတ်ဉာဏ်ထဲ ပြန်သိမ်းမယ်
                chat_logs.insert_one({
                    "chat_id": cid, "user": "Dexter Bot", "user_id": 0, "is_owner": False, 
                    "text": answer, "time": datetime.now()
                })
                
                await event.reply(answer)
            except Exception as e:
                print(f"GPT Error: {e}")

# ==========================================
# 🚀 LAUNCH
# ==========================================
if __name__ == "__main__":
    keep_alive()
    print("🦇 Brotherhood Ultimate AI Core is Online and Learning!")
    bot.run_until_disconnected()
