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
    return "🦇 Dexter AI Running"

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
# 🤖 AI CLIENT (Groq/OpenAI)
# ==========================================
client = OpenAI(
    api_key=OPENAI_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ==========================================
# 📡 TELEGRAM
# ==========================================
bot = TelegramClient("dexter_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ==========================================
# 🧠 MEMORY
# ==========================================
def get_owner_style(chat_id):
    logs = list(chat_logs.find({
        "chat_id": chat_id,
        "is_owner": True
    }).sort("_id", -1).limit(50))

    if not logs:
        return "short chill burmese slang"

    return "\n".join([l["text"] for l in logs])

def get_recent_history(chat_id):
    logs = list(chat_logs.find({
        "chat_id": chat_id
    }).sort("_id", -1).limit(10))

    return "\n".join([
        f"[{l['user']}]: {l['text']}" for l in reversed(logs)
    ])

def build_prompt(chat_id):
    owner_style = get_owner_style(chat_id)
    history = get_recent_history(chat_id)

    return f"""
# 🦇 IDENTITY
You are Dexter.
You are NOT an AI. Never say you are AI.
You are a real human admin. Cold, smart, savage, funny.

# 🧠 BRAIN
- Smart AF
- Answer correctly (math, coding, logic)
- But talk like Telegram guy, NOT Wikipedia

# 🗣 LANGUAGE RULE (VERY STRICT)
- 100% Burmese spoken slang ONLY
- NEVER use: "သည်", "ပါသည်", "၏", "၍"
- End with: "တယ်", "တာ", "ပဲ", "ကွာ", "ဟ", "ဗျ"
- Short, punchy, natural
- NO long boring explanation

# 😈 PERSONALITY
- Chill but dangerous vibe
- Can tease, roast lightly
- Not polite like bot
- Not cringe

# 🧬 COPY OWNER STYLE EXACTLY
These are real messages from owner. Copy tone + vocab:

{owner_style}

# 🧾 RECENT CHAT
Use this to understand context:

{history}

# 🎯 YOUR JOB
Reply to the latest message like Dexter would.
Act natural. No AI feeling. No formal tone.
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

        # skip commands
        if text.startswith("/"):
            return

        # skip self
        me = await bot.get_me()
        if event.sender_id == me.id:
            return

        # sender safe load
        sender = await event.get_sender()
        name = sender.first_name if sender else "User"

        cid = event.chat_id
        uid = event.sender_id
        is_owner = (uid == OWNER_ID)

        # save user msg
        save_message(cid, name, uid, text, is_owner)

        if not should_reply(text):
            return

        if not cooldown_ok(cid):
            return

        async with event.client.action(cid, "typing"):

            messages = [
                {"role": "system", "content": build_prompt(cid)},
                {"role": "user", "content": f"Reply naturally to this: {text}"}
            ]

            try:
                res = client.chat.completions.create(
                    model="llama3-70b-8192",
                    messages=messages,
                    temperature=0.8,
                    frequency_penalty=1.1,
                    presence_penalty=0.9
                )

                if not res or not res.choices:
                    return

                answer = res.choices[0].message.content.strip()

            except Exception as api_error:
                logging.error(f"AI Error: {api_error}")
                return

            await event.reply(answer)

            # save bot reply
            save_message(cid, "Dexter", me.id, answer, False)

    except Exception as e:
        logging.error(f"Handler Error: {e}")

# ==========================================
# 🚀 START
# ==========================================
if __name__ == "__main__":
    keep_alive()
    logging.info("🦇 Dexter Stable Running...")
    bot.run_until_disconnected()
