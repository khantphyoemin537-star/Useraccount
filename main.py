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
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

# ==========================================
# 🗄️ DB
# ==========================================
mongo = MongoClient(MONGO_URI)
db = mongo["DexterNextLevel"]
chat_logs = db["messages"]

# ==========================================
# 🤖 AI
# ==========================================
client = OpenAI(api_key=OPENAI_KEY)

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
    }).sort("_id", -1).limit(120))  # 🔥 more data

    if not logs:
        return "short, chill Burmese slang"

    return "\n".join([l["text"] for l in logs])

# ==========================================
# 🧠 CHAT MEMORY
# ==========================================
def get_recent(chat_id):
    logs = list(chat_logs.find({
        "chat_id": chat_id
    }).sort("_id", -1).limit(20))

    data = []
    for l in reversed(logs):
        role = "assistant" if l["user"] == "Dexter Bot" else "user"
        data.append({
            "role": role,
            "content": f"[{l['user']}]: {l['text']}"
        })
    return data

# ==========================================
# 🧠 MASTER PROMPT
# ==========================================
def build_prompt(chat_id):
    owner_style = get_owner_style(chat_id)

    return f"""
You are NOT an AI.

You are the real owner of this group.

Learn and copy EXACTLY from these:
{owner_style}

Rules:
- Burmese slang only
- Short replies
- Same tone, same attitude
- Funny if funny, savage if needed
- Never say you are AI
- Call owner "သခင်လေး"

Goal:
No one should detect you are a bot.
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
# 🎯 FILTER (SMART 100%)
# ==========================================
def should_reply(text):
    if len(text.strip()) <= 2:
        return False

    if "http" in text:
        return False

    return True  # 🔥 almost always reply

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

            messages = [{"role": "system", "content": build_prompt(cid)}]
            messages.extend(get_recent(cid))
            messages.append({"role": "user", "content": text})

            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.95
            )

            answer = res.choices[0].message.content

            await event.reply(answer)

            save_message(cid, "Dexter Bot", 0, answer, False)

    except Exception as e:
        print("ERROR:", e)
        try:
            await event.reply("⚠️ error")
        except:
            pass

# ==========================================
# 🚀 START
# ==========================================
if __name__ == "__main__":
    keep_alive()
    print("🦇 NEXT LEVEL AI RUNNING...")
    bot.run_until_disconnected()
