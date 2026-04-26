import os
import random
from datetime import datetime
from threading import Thread

from flask import Flask
from telethon import TelegramClient, events
from pymongo import MongoClient
from openai import OpenAI

# ==========================================
# 🌐 KEEP ALIVE (Render)
# ==========================================
app = Flask(__name__)

@app.route("/")
def home():
    return "🦇 Dexter NEXT LEVEL AI is Alive"

def run():
    app.run(host="0.0.0.0", port=10000)

def keep_alive():
    Thread(target=run).start()

# ==========================================
# ⚙️ ENV
# ==========================================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

MONGO_URI = os.getenv("MONGO_URI")

# ==========================================
# 🗄️ DB
# ==========================================
mongo = MongoClient(MONGO_URI)
db = mongo["DexterNextLevel"]
chat_logs = db["messages"]

# ==========================================
# 🤖 AI (Groq Setup)
# ==========================================
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"), 
    base_url="https://api.groq.com/openai/v1" 
)

# ==========================================
# 📡 TELEGRAM
# ==========================================
bot = TelegramClient(
    "dexter_next_session",
    API_ID,
    API_HASH
).start(bot_token=BOT_TOKEN)

# ==========================================
# 💾 SAVE
# ==========================================
def save_message(chat_id, user, user_id, text, is_owner):
    try:
        chat_logs.insert_one({
            "chat_id": chat_id,
            "user": user,
            "user_id": user_id,
            "text": text,
            "is_owner": is_owner,
            "time": datetime.now()
        })
    except:
        pass

# ==========================================
# 🧠 OWNER STYLE (HEAVY TRAIN)
# ==========================================
def get_owner_style(chat_id):
    logs = list(chat_logs.find({
        "chat_id": chat_id,
        "is_owner": True
    }).sort("_id", -1).limit(100)) 

    if not logs:
        return "short, chill Burmese slang"

    return "\n".join([f"- {l['text']}" for l in logs])

# ==========================================
# 🧠 CHAT MEMORY (Fixed API Array Error)
# ==========================================
def get_recent_history(chat_id):
    logs = list(chat_logs.find({
        "chat_id": chat_id
    }).sort("_id", -1).limit(15))

    history_text = ""
    for l in reversed(logs):
        history_text += f"[{l['user']}]: {l['text']}\n"
    return history_text

# ==========================================
# 🧠 MASTER PROMPT
# ==========================================
def build_prompt(chat_id):
    owner_style = get_owner_style(chat_id)
    chat_history = get_recent_history(chat_id)

    return f"""
# IDENTITY
You are "Dexter", the legendary owner and administrator of the Brotherhood of Dexter (BoD). 
You are NOT an AI assistant. Never admit to being an AI. You are a real human with a sharp mind, savage wit, and cool attitude.

# KNOWLEDGE
You are highly intelligent. Answer math questions (e.g., 1+1=2), logic, coding, and general knowledge accurately. 
Explain things clearly but talk like a normal person chatting on Telegram, not like a Wikipedia article.

# LANGUAGE & TONE (CRITICAL)
1. Use 100% informal, street-style spoken Burmese (ဗမာစကား). 
2. NEVER use formal ending words like "သည်။", "ပါသည်။", "၏", "၍". This is strictly forbidden.
3. End your sentences naturally with "တယ်", "တာ", "ပဲ", "ပေါ့", "ကွာ", "ဟ", "ဗျ". 
4. Keep replies concise and punchy. Don't be overly polite. Don't repeat the same phrases.

# MIMIC THE OWNER
Study these exact messages from the real owner and copy his exact vibe and vocabulary:
{owner_style}

# RECENT CHAT CONTEXT
Here is what happened recently in the group. Use this context to reply intelligently to the newest message:
{chat_history}
"""

# ==========================================
# ⏱️ COOLDOWN (ANTI-SPAM)
# ==========================================
last_reply = {}

def cooldown_ok(chat_id):
    now = datetime.now().timestamp()
    if chat_id not in last_reply:
        last_reply[chat_id] = now
        return True
    if now - last_reply[chat_id] > 3:
        last_reply[chat_id] = now
        return True
    return False

# ==========================================
# 🎯 FILTER
# ==========================================
def should_reply(text):
    if len(text.strip()) <= 1:
        return False
    if "http" in text:
        return False
    return True

# ==========================================
# 💬 MAIN
# ==========================================
@bot.on(events.NewMessage)
async def handler(event):
    try:
        if not event.raw_text:
            return

        text = event.raw_text

        if text.startswith("/"):
            return

        # 🔥 ကိုယ့်စာကိုယ် ပြန်မဖတ်အောင် တားခြင်း
        me = await bot.get_me()
        if getattr(event, 'sender_id', None) == me.id:
            return

        cid = event.chat_id
        uid = event.sender_id
        name = event.sender.first_name if event.sender else "User"
        is_owner = (uid == OWNER_ID)

        # save
        save_message(cid, name, uid, text, is_owner)

        # filters
        if not should_reply(text):
            return

        if not cooldown_ok(cid):
            return

        async with event.client.action(cid, "typing"):
            
            # 🔥 API Error မတက်အောင် System Prompt ထဲမှာပဲ အကုန်ထည့်လိုက်ပါပြီ
            messages = [
                {"role": "system", "content": build_prompt(cid)},
                {"role": "user", "content": f"Reply to this newest message from [{name}]: {text}"}
            ]

            res = client.chat.completions.create(
                model="llama-3.3-70b-versatile", 
                messages=messages,
                temperature=0.85,          # နည်းနည်းလျှော့လိုက်တယ်
                frequency_penalty=1.2,     # 🔥 စကားတွေ ထပ်မပြောအောင်
                presence_penalty=1.0       # 🔥 အကြောင်းအရာသစ်တွေ စဉ်းစားအောင်
            )

            answer = res.choices[0].message.content

            await event.reply(answer)

            # Bot ရဲ့ စာကို မှတ်တမ်းထဲ ထည့်သိမ်းမယ်
            save_message(cid, "Dexter Bot", me.id, answer, False)

    except Exception as e:
        # 🔥 Error အတိအကျကို ပြပေးမယ့် နေရာ
        error_msg = str(e)
        print("🔴 ERROR DETECTED:", error_msg)
        try:
            await event.reply(f"ဉာဏ်စမ်းနေတာလား... အခုခဏ Error တက်နေတယ်: {error_msg[:50]}...")
        except:
            pass

# ==========================================
# 🚀 START
# ==========================================
if __name__ == "__main__":
    keep_alive()
    print("🦇 NEXT LEVEL AI RUNNING...")
    bot.run_until_disconnected()

