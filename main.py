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

# =========================
# 🌐 KEEP ALIVE
# =========================
app = Flask(__name__)
@app.route("/")
def home(): return "🦇 Brotherhood System Online"

def run(): app.run(host="0.0.0.0", port=10000)
def keep_alive(): Thread(target=run).start()

# =========================
# ⚙️ CONFIGURATIONS
# =========================
API_ID = 37675502 
API_HASH = "45955dc059f23ca5bfa3dcaff9c0f032"
BOT_TOKEN = "8738081667:AAGr7HkSxO6nC_QhPJJElKR2VKABTEDfNEo"
OWNER_ID = 6015356597
LOG_CHAT_ID = -1003933136412 # ဒီ Chat ထဲကနေ ပုံတွေကို ဆွဲထုတ်မှာပါ

MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true"

# =========================
# 🧠 DATABASE SETUP
# =========================
mongo = MongoClient(MONGO_URI)
db = mongo["Brotherhood_of_Dexter_DB"]
actress_db = db["actresses"]
users_db = db["users"]
spawn_db = db["spawns"]

bot = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
msg_count = {}

# =========================
# 🛠 UTILS
# =========================
def gen_id(prefix):
    return f"{prefix}-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_effect(r):
    return {"Common": "▫️", "Rare": "🔵✨", "Epic": "🟣🔥✨", "Legendary": "🟡⚡🔥✨", "Mythic": "🔴👑⚡🔥✨"}.get(r, "")

# =========================
# 🩸 1. DATABASE ADDING (/fuck)
# =========================
@bot.on(events.NewMessage(chats=LOG_CHAT_ID, pattern=r"^/fuck (.*)"))
async def add_to_db(event):
    if event.sender_id != OWNER_ID or not event.is_reply: return
    reply = await event.get_reply_message()
    if not reply.photo: return
    try:
        data = event.pattern_match.group(1).split('|')
        name = data[0].strip()
        rarity = data[1].strip() if len(data) > 1 else random.choices(["Common", "Rare", "Epic", "Legendary", "Mythic"], weights=[55, 25, 12, 6, 2])[0]
        actress_db.insert_one({
            "base_id": gen_id("BASE"), "name": name.lower(), "display_name": name,
            "rarity": rarity, "message_id": reply.id
        })
        await event.reply(f"✅ <b>Saved:</b> <code>{name}</code>")
    except Exception as e: await event.reply(f"❌ Error: {e}")

# =========================
# 🍷 2. SPAWN LOGIC (Auto/Manual)
# =========================
async def spawn_actress(chat_id):
    if spawn_db.find_one({"chat_id": chat_id, "active": True}): return
    all_data = list(actress_db.find())
    if not all_data: return
    target = random.choice(all_data)
    
    spawn_db.update_one({"chat_id": chat_id}, {"$set": {
        "base_id": target["base_id"], "name": target["name"], "display": target["display_name"],
        "rarity": target["rarity"], "active": True, "message_id": target["message_id"]
    }}, upsert=True)
    
    # ပုံကျလာရင် စာသားမပါဘူး (Mystery ဖြစ်အောင်)
    ui = "🩸 <b>A mysterious actress appeared!</b>\n\nUse <code>/wa</code> to see who she is."
    # Log Chat ထဲက ပုံကို Address သေချာပေးပြီး ပို့မယ်
    await bot.send_file(chat_id, file=target['message_id'], caption=ui, parse_mode='html', from_peer=LOG_CHAT_ID)

@bot.on(events.NewMessage)
async def auto_spawn(event):
    if event.is_private or event.raw_text.startswith("/"): return
    cid = event.chat_id
    msg_count[cid] = msg_count.get(cid, 0) + 1
    if msg_count[cid] >= 50:
        await spawn_actress(cid)
        msg_count[cid] = 0

@bot.on(events.NewMessage(pattern=r"^/waifu"))
async def manual_spawn(event): await spawn_actress(event.chat_id)

@bot.on(events.NewMessage(pattern=r"^/wa"))
async def what_is_it(event):
    data = spawn_db.find_one({"chat_id": event.chat_id, "active": True})
    if not data: return await event.reply("နတ်သမီးလေး ပေါ်မနေပါဘူးဟ။")
    hint = f"🎬 <b>Actress:</b> {data['display']}\n💎 <b>Rarity:</b> {data['rarity']} {get_effect(data['rarity'])}\n\nဖမ်းယူရန်: <code>/catch {data['display']}</code>"
    await event.reply(hint, parse_mode='html')

# =========================
# 🖤 3. CATCH SYSTEM
# =========================
@bot.on(events.NewMessage(pattern=r"^/catch (.+)"))
async def catch_actress(event):
    guess = event.pattern_match.group(1).strip().lower()
    data = spawn_db.find_one_and_update({"chat_id": event.chat_id, "active": True}, {"$set": {"active": False}})
    if not data: return await event.reply("❌ နောက်ကျသွားပါပြီ!")
    
    if guess == data["name"]:
        card_id = gen_id("CARD")
        users_db.insert_one({
            "user_id": event.sender_id, "card_id": card_id, "display_name": data["display"],
            "rarity": data["rarity"], "message_id": data["message_id"]
        })
        await event.reply(f"🏆 <b>Caught!</b>\n\n🎴 <b>{data['display']}</b>\n💎 {data['rarity']} {get_effect(data['rarity'])}\n🔖 ID: <code>{card_id}</code>", parse_mode='html')
    else:
        spawn_db.update_one({"chat_id": event.chat_id}, {"$set": {"active": True}})
        await event.reply("❌ နာမည်မှားနေပါတယ်ဟ။")

# =========================
# 👑 4. HAREM SYSTEM
# =========================
@bot.on(events.NewMessage(pattern=r"^/harem"))
async def view_harem(event):
    user_id = (await event.get_reply_message()).sender_id if event.is_reply else event.sender_id
    cards = list(users_db.find({"user_id": user_id}))
    if not cards: return await event.reply("🦇 Empty Harem.")
    
    c = cards[0]
    ui = f"🖤 <b>Harem Collection</b> (1/{len(cards)})\n\n🎴 <b>{c['display_name']}</b>\n💎 {c['rarity']} {get_effect(c['rarity'])}\n🔖 ID: <code>{c['card_id']}</code>"
    btns = [[Button.inline("Next ➡️", data=f"h_{user_id}_1")]]
    await bot.send_file(event.chat_id, file=c['message_id'], caption=ui, buttons=btns, parse_mode='html', from_peer=LOG_CHAT_ID)

@bot.on(events.CallbackQuery(pattern=re.compile(rb"h_(\d+)_(\d+)")))
async def harem_nav(event):
    uid, idx = int(event.data_match.group(1)), int(event.data_match.group(2))
    cards = list(users_db.find({"user_id": uid}))
    idx = idx % len(cards)
    c = cards[idx]
    ui = f"🖤 <b>Harem Collection</b> ({idx+1}/{len(cards)})\n\n🎴 <b>{c['display_name']}</b>\n💎 {c['rarity']} {get_effect(c['rarity'])}\n🔖 ID: <code>{c['card_id']}</code>"
    await event.edit(file=c['message_id'], caption=ui, buttons=[[Button.inline("⬅️ Prev", data=f"h_{uid}_{idx-1}"), Button.inline("Next ➡️", data=f"h_{uid}_{idx+1}")]], parse_mode='html', from_peer=LOG_CHAT_ID)

# =========================
# 🎁 5. GIFT & 🏆 TOP
# =========================
@bot.on(events.NewMessage(pattern=r"^/gift (.+)"))
async def gift_actress(event):
    if not event.is_reply: return await event.reply("⚠️ Reply user please.")
    cid = event.pattern_match.group(1).strip().upper()
    receiver = (await event.get_reply_message()).sender_id
    res = users_db.update_one({"user_id": event.sender_id, "card_id": cid}, {"$set": {"user_id": receiver}})
    if res.modified_count: await event.reply("🎁 အောင်မြင်စွာ လက်ဆောင်ပေးပြီးပါပြီ!")
    else: await event.reply("❌ Invalid Card ID.")

@bot.on(events.NewMessage(pattern=r"^/top"))
async def leaderboard(event):
    top_users = list(users_db.aggregate([{"$group": {"_id": "$user_id", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}, {"$limit": 10}]))
    text = "🏆 <b>Brotherhood Top 10 Collectors</b>\n\n"
    for i, u in enumerate(top_users, 1):
        try: name = (await bot.get_entity(u["_id"])).first_name
        except: name = "User"
        text += f"{i}. <b>{name}</b> — {u['count']} cards\n"
    await event.reply(text, parse_mode='html')

if __name__ == "__main__":
    keep_alive()
    print("🦇 Brotherhood System Online!")
    bot.run_until_disconnected()
