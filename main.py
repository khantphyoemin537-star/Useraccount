import os
import logging
from datetime import datetime
from threading import Thread

from flask import Flask
from telethon import TelegramClient, events
from pymongo import MongoClient
from openai import OpenAI

# ==========================================
# 🧾 LOGGING
# ==========================================
logging.basicConfig(level=logging.INFO)

# ==========================================
# 🌐 KEEP ALIVE (Render)
# ==========================================
app = Flask(__name__)

@app.route("/")
def home():
    return "🦇 Dexter Gemini is Alive & Thinking"

def run():
    app.run(host="0.0.0.0", port=10000)

def keep_alive():
    Thread(target=run, daemon=True).start()

# ==========================================
# ⚙️ ENV SAFE LOAD
# ==========================================
def get_env(name, required=True, cast=None):
    val = os.getenv(name)
    if required and not val:
        raise ValueError(f"Missing ENV: {name}")
    return cast(val) if cast and val else val

API_ID = get_env("API_ID", cast=int)
API_HASH = get_env("API_HASH")
BOT_TOKEN = get_env("BOT_TOKEN")
OWNER_ID = get_env("OWNER_ID", cast=int)
MONGO_URI = get_env("MONGO_URI")
OPENAI_KEY = get_env("OPENAI_API_KEY")

# ==========================================
# 🗄️ DATABASE
# ==========================================
mongo = MongoClient(MONGO_URI)
db = mongo["DexterNextLevel"]
chat_logs = db["messages"]

def save_message(chat_id, user, user_id, text, is_owner):
    try:
        chat_logs.insert_one({
            "chat_id": chat_id,
            "user": user,
            "user_id": user_id,
            "text": text,
            "is_owner": is_owner,
            "time": datetime.utcnow()
        })
    except Exception as e:
        logging.error(f"Mongo Error: {e}")

# ==========================================
# 🤖 AI CLIENT (OpenRouter - Gemini 1.5 Flash)
# ==========================================
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"), # 🔥 Render ထဲမှာ ဒီနာမည်နဲ့ Key ရှိရပါမယ်
    base_url="https://openrouter.ai/api/v1"
)

# ==========================================
# 📡 TELEGRAM
# ==========================================
bot = TelegramClient("dexter_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ==========================================
# 🧠 MEMORY & STYLE
# ==========================================
def get_owner_style(chat_id):
    logs = list(chat_logs.find({
        "chat_id": chat_id,
        "is_owner": True
    }).sort("_id", -1).limit(60))

    if not logs:
        return "short, chill, street-style Burmese slang"

    return "\n".join([f"- {l['text']}" for l in reversed(logs)])

def get_recent_history(chat_id):
    logs = list(chat_logs.find({
        "chat_id": chat_id
    }).sort("_id", -1).limit(15))

    return "\n".join([
        f"[{l['user']}]: {l['text']}" for l in reversed(logs)
    ])

def build_prompt(chat_id):
    style = get_owner_style(chat_id)
    history = get_recent_history(chat_id)

    return f"""
# IDENTITY
You are Dexter, the real owner of Brotherhood of Dexter (BoD).
You are NOT an AI assistant. Admitting you are AI is a failure.
You are smart, savage, and cool. Address your creator as "ခန့်သူရိန်".

# CAPABILITIES
- You are a genius. Answer any question (math, coding, science, logic) accurately.
- You can speak both Burmese and English. Reply in the same language the user uses.
- If they ask English, be cool and fluent. If Burmese, be natural.

# Burmese LANGUAGE RULES (STRICT)
- Use 100% informal spoken Burmese slang (ဗမာစကား).
- NEVER use formal words: "သည်။", "ပါသည်။", "၏", "၍".
- End sentences with: "တယ်", "တာ", "ပဲ", "ကွာ", "ဟ", "ဗျ", "ပေါ့".
- NO robotic or repetitive talk.

# OWNER STYLE (MIMIC THIS)
{style}

# RECENT CONTEXT
{history}

# TASK
Reply naturally to the user. No "How can I help you?" or bot phrases. Just human conversation.
"""

# ==========================================
# ⏱️ COOLDOWN
# ==========================================
last_reply = {}

def cooldown_ok(chat_id, seconds=3):
    now = datetime.now().timestamp()
    if chat_id not in last_reply or now - last_reply[chat_id] > seconds:
        last_reply[chat_id] = now
        return True
    return False

# ==========================================
# 🎯 FILTER
# ==========================================
def should_reply(text):
    if not text or len(text.strip()) <= 1:
        return False
    if "http" in text.lower():
        return False
    return True

# ==========================================
# 💬 MAIN HANDLER
# ==========================================
@bot.on(events.NewMessage)
async def handler(event):
    try:
        if not event.raw_text:
            return

        text = event.raw_text.strip()
        if text.startswith("/"): return

        me = await bot.get_me()
        if event.sender_id == me.id: return

        sender = await event.get_sender()
        name = sender.first_name if sender else "User"
        cid, uid = event.chat_id, event.sender_id
        is_owner = (uid == OWNER_ID)

        save_message(cid, name, uid, text, is_owner)

        if not should_reply(text) or not cooldown_ok(cid):
            return

        async with event.client.action(cid, "typing"):
            messages = [
                {"role": "system", "content": build_prompt(cid)},
                {"role": "user", "content": text}
            ]

            # 🔥 Gemini Model on OpenRouter
            res = client.chat.completions.create(
                model="google/gemini-flash-1.5", 
                messages=messages,
                temperature=0.85,
                extra_headers={
                    "HTTP-Referer": "https://render.com", # Optional but good for OpenRouter
                    "X-Title": "Dexter AI Bot"
                }
            )

            if res.choices:
                answer = res.choices[0].message.content.strip()
                await event.reply(answer)
                save_message(cid, "Dexter", me.id, answer, False)

    except Exception as e:
        logging.error(f"Error: {e}")

# ==========================================
# 🚀 START
# ==========================================
if __name__ == "__main__":
    keep_alive()
    logging.info("🦇 Dexter Gemini (OpenRouter) Running...")
    bot.run_until_disconnected()
