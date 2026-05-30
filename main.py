import os  # 👈 Render ရဲ့ Port ကို ဖတ်ဖို့အတွက် ဒါလေး ထည့်ပေးပါ
import asyncio
import random
import time
import logging
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from motor.motor_asyncio import AsyncIOMotorClient

# ==========================================
# ⚙️ CONFIGURATION (မင်းပေးထားတဲ့ Credentials များ)
# ==========================================
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/telegram_bot?appName=Cluster0&tlsAllowInvalidCertificates=true"
APP_ID = 39584681
APP_HASH = 'c8c0685d6dd5b9e546093ea90d27733b'
BOT_TOKEN = '8111794244:AAGpkLE7h5x_IYFvjkVCbJosDC1TFbCGxcQ'

OWNER_ID = 7937055613
SPECIFIC_GROUP = -1003580630981
COOLDOWN_TIME = 15

# Global States
is_active = False
is_scraping = False
user_cooldowns = {}

# MongoDB Setup
client_mongo = AsyncIOMotorClient(MONGO_URI)
db = client_mongo["telegram_bot"]
reply_save_col = db["reply_save_col"]
target_bots_col = db["target_bots"]  # 👈 Auto-Delete လုပ်မည့် Bot ID များ သိမ်းဆည်းရန်
config_col = db["config_col"]

# Initialize Official Bot Client
bot = TelegramClient('official_bot_session', APP_ID, APP_HASH)
userbot = None  # String Session ရမှ ဖွင့်မည်
# ==========================================
# 🌍 DUMMY HTTP SERVER FOR RENDER HEALTH CHECK (ဝဘ်ဆိုက်အတုဖွင့်ခြင်း)
# ==========================================
async def handle_render_health_check(reader, writer):
    """ Render က လှမ်းစစ်ရင် 200 OK ပြန်ပေးမည့် Response """
    data = await reader.read(100)
    response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nOK"
    writer.write(response.encode('utf-8'))
    await writer.drain()
    writer.close()

async def start_dummy_web_server():
    """ Render က သတ်မှတ်ပေးတဲ့ Port မှာ Web Server အတုကို Run ပေးခြင်း """
    port = int(os.environ.get("PORT", 10000))
    try:
        server = await asyncio.start_server(handle_render_health_check, '0.0.0.0', port)
        print(f"🌍 Dummy HTTP Server started on port {port} for Render Health Check!")
        async with server:
            await server.serve_forever()
    except Exception as e:
        print(f"❌ Failed to start Dummy Web Server: {e}")

# ==========================================
# 🗑️ ANTI-FLOOD DELAYED DELETION TASK (စာဖျက်မည့်စနစ်)
# ==========================================
async def delete_bot_message_delayed(event, bot_msg_id, cmd_msg_id=0):
    """ နောက်ကွယ်ကနေ ၄ စက္ကန့်စောင့်ပြီး Floodမမိအောင် စာလှမ်းဖျက်ပေးမည့် စနစ် """
    try:
        await asyncio.sleep(4)
        
        # ဖျက်မည့် စာရင်းလုပ်ခြင်း (Command စာရှိရင် တွဲဖျက်မည်၊ မရှိရင် Bot စာပဲ ဖျက်မည်)
        to_delete = [bot_msg_id]
        if cmd_msg_id:
            to_delete.append(cmd_msg_id)
            
        await event.client.delete_messages(event.chat_id, to_delete)
        print(f"🗑️ Auto-deleted message {bot_msg_id} after 4s delay.")
        
    except errors.rpcerrorlist.FloodWaitError as e:
        print(f"⚠️ FloodWait Caught! Must wait {e.seconds} seconds.")
        await asyncio.sleep(e.seconds)
        try:
            await event.client.delete_messages(event.chat_id, to_delete)
        except Exception:
            pass
    except Exception as e:
        print(f"❌ Error during delayed deletion: {e}")

# ==========================================
# 🧠 USERBOT EVENT HANDLER (AUTO-REPLY & DELETE)
# ==========================================
async def handle_userbot_reply(event):
    global is_active, user_cooldowns
    
    # ------------------------------------------------------------------------
    # 🎯 အပိုင်း (၁) - Bot ID ကို အမြဲတမ်း Auto-Delete စာရင်းထဲ သွင်းခြင်း (Reply ပြီး /ဖျက်မည် ဟု ရိုက်ပါက)
    # ------------------------------------------------------------------------
    if event.sender_id == OWNER_ID and event.message.text.strip() == "/ဖျက်မည်":
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            reply_sender = await reply_msg.get_sender()
            
            if reply_sender and reply_sender.bot:
                bot_id = reply_sender.id
                # DB ထဲမှာ ဒီ Bot ID ကို အမြဲတမ်း မှတ်ထားလိုက်ခြင်း
                await target_bots_col.update_one(
                    {"bot_id": bot_id},
                    {"$set": {"bot_id": bot_id, "username": reply_sender.username}},
                    upsert=True
                )
                await event.reply(f"🎯 Bot ID: `{bot_id}` (@{reply_sender.username}) ကို စာရင်းသွင်းပြီးပါပြီ။ နောက်ဆို စာတက်လာတာနဲ့ ၄ စက္ကန့်အတွင်း အလိုအလျောက် ရှင်းလင်းပေးပါတော့မယ် ဆရာကြီး!")
                
                # လက်ရှိ Bot စာနဲ့ ကိုယ်ရိုက်တဲ့ Command စာကိုပါ တစ်ခါတည်း ဖျက်ပစ်မည်
                asyncio.create_task(delete_bot_message_delayed(event, reply_msg.id, event.id))
                return

    # ------------------------------------------------------------------------
    # 🤖 အပိုင်း (၂) - Chat ထဲ စာတက်လာတိုင်း သတ်မှတ်ထားတဲ့ Bot ဟုတ်မဟုတ် စစ်ပြီး Auto-Delete လုပ်ခြင်း
    # ------------------------------------------------------------------------
    sender = await event.get_sender()
    if sender and sender.bot:
        # DB ထဲမှာ ဒီ Bot ID ရှိ၊ မရှိ စစ်ဆေးခြင်း
        is_target = await target_bots_col.find_one({"bot_id": event.sender_id})
        if is_target:
            # စာရင်းထဲက ကောင်ဆိုရင် ဘာ Command မှ ရိုက်စရာမလိုဘဲ ၄ စက္ကန့် Task ဆီ တန်းလွှဲပေးလိုက်မည်
            asyncio.create_task(delete_bot_message_delayed(event, event.id, 0))
            return

    # ------------------------------------------------------------------------
    # 💬 အပိုင်း (၃) - မူရင်း Auto-Reply Logic (စာပြန်သည့်စနစ်)
    # ------------------------------------------------------------------------
    if not is_active:
        return

    if event.out or (sender and sender.bot):
        return

    user_text = event.message.text.strip().lower()
    if not user_text:
        return

    user_id = event.sender_id
    current_time = time.time()
    if user_id in user_cooldowns and (current_time - user_cooldowns[user_id] < COOLDOWN_TIME):
        return

    matched_doc = await reply_save_col.find_one({
        "$expr": {
            "$gt": [{"$indexOfCP": [user_text, "$trigger"]}, -1]
        }
    })

    if matched_doc:
        user_cooldowns[user_id] = current_time
        try:
            await event.client.send_read_acknowledge(event.chat_id, max_id=event.id)
            async with event.client.action(event.chat_id, 'typing'):
                await asyncio.sleep(random.uniform(2.5, 5.0))

            reply_text = random.choice(matched_doc["responses"])
            await event.reply(reply_text)
        except Exception as e:
            print(f"❌ Userbot Reply Error: {e}")


    # ------------------------------------------
    # 🤖 အောက်ကအပိုင်းကတော့ မူရင်း Auto-Reply Logic ဖြစ်ပါတယ်
    # ------------------------------------------
    if not is_active:
        return

    sender = await event.get_sender()
    if event.out or (sender and sender.bot):
        return

    user_text = event.message.text.strip().lower()
    if not user_text:
        return

    user_id = event.sender_id
    current_time = time.time()
    if user_id in user_cooldowns and (current_time - user_cooldowns[user_id] < COOLDOWN_TIME):
        return

    matched_doc = await reply_save_col.find_one({
        "$expr": {
            "$gt": [{"$indexOfCP": [user_text, "$trigger"]}, -1]
        }
    })

    if matched_doc:
        user_cooldowns[user_id] = current_time
        try:
            await event.client.send_read_acknowledge(event.chat_id, max_id=event.id)
            async with event.client.action(event.chat_id, 'typing'):
                await asyncio.sleep(random.uniform(2.5, 5.0))

            reply_text = random.choice(matched_doc["responses"])
            await event.reply(reply_text)
        except Exception as e:
            print(f"❌ Userbot Reply Error: {e}")

# ==========================================
# 📥 USERBOT SCRAIPING TASK (/replyမှတ်)
# ==========================================
async def scrape_history_task():
    global is_scraping, userbot
    if not userbot:
        await bot.send_message(SPECIFIC_GROUP, "❌ Userbot အသက်မဝင်သေးသဖြင့် စာမှတ်၍မရပါ။ /string အရင်လုပ်ပေးပါ။")
        return

    is_scraping = True
    await bot.send_message(SPECIFIC_GROUP, "📥 စာဟောင်း ၂ သိန်းမှတ်ခြင်း လုပ်ငန်းစဉ် စတင်ပါပြီ... ခေတ္တစောင့်ဆိုင်းပေးပါ။")
    
    try:
        msg_cache = {}
        total_saved = 0
        TARGET_LIMIT = 200000

        async for msg in userbot.iter_messages(SPECIFIC_GROUP, limit=400000):
            if msg and msg.text:
                msg_cache[msg.id] = msg.text.strip()

        async for msg in userbot.iter_messages(SPECIFIC_GROUP, limit=400000):
            if not is_scraping or total_saved >= TARGET_LIMIT:
                break

            if msg.reply_to and msg.text:
                parent_id = msg.reply_to.reply_to_msg_id
                parent_text = msg_cache.get(parent_id)
                reply_text = msg.text.strip()

                if parent_text and reply_text:
                    trigger = parent_text.lower()

                    if len(trigger) <= 3:
                        continue

                    if (trigger.startswith(('/', '.', 'မှတ်', 'reply')) or 
                        reply_text.startswith(('/', '.', 'မှတ်', 'reply')) or 
                        "http" in trigger or "http" in reply_text or "@" in trigger):
                        continue

                    existing_doc = await reply_save_col.find_one({"trigger": trigger})
                    if existing_doc:
                        if reply_text not in existing_doc.get("responses", []):
                            await reply_save_col.update_one(
                                {"trigger": trigger},
                                {"$push": {"responses": reply_text}}
                            )
                            total_saved += 1
                    else:
                        await reply_save_col.insert_one({"trigger": trigger, "responses": [reply_text]})
                        total_saved += 1

                    if total_saved % 5000 == 0:
                        await bot.send_message(SPECIFIC_GROUP, f"🚀 စာစောင် ပေါင်း {total_saved} ခု DB ထဲ မှတ်ပြီးပါပြီ Chief!")
                    
                    await asyncio.sleep(0.05)

        await bot.send_message(SPECIFIC_GROUP, f"🎉 အောင်မြင်စွာ စာစောင် {total_saved} ခုကို Pattern အဖြစ် သိမ်းဆည်းပြီးပါပြီ ဆရာကြီး!")
    except Exception as e:
        await bot.send_message(SPECIFIC_GROUP, f"❌ Scraping ပြဿနာတက်ခဲ့သည်: {e}")
    finally:
        is_scraping = False

# ==========================================
# 🤖 OFFICIAL BOT COMMAND HANDLERS
# ==========================================
@bot.on(events.NewMessage(chats=SPECIFIC_GROUP))
async def handle_bot_commands(event):
    global is_active, userbot, is_scraping
    
    if event.sender_id != OWNER_ID:
        return

    cmd = event.message.text.strip()

    if cmd == "/string" and event.is_reply:
        reply_msg = await event.get_reply_message()
        if reply_msg and reply_msg.text:
            session_str = reply_msg.text.strip()
            await config_col.update_one(
                {"key": "string_session"},
                {"$set": {"value": session_str}},
                upsert=True
            )
            await event.reply("✅ String Session ကို DB မှာ သိမ်းဆည်းပြီးပါပြီ။ Userbot ကို စတင် ချိတ်ဆက်နေပါတယ်...")
            
            try:
                if userbot:
                    await userbot.disconnect()
                userbot = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
                await userbot.start()
                userbot.add_event_handler(handle_userbot_reply, events.NewMessage(chats=SPECIFIC_GROUP))
                await event.reply("🚀 Userbot is Live!")
            except Exception as e:
                await event.reply(f"❌ Userbotအိပ်နေတယ်: {e}")

    elif cmd == "/ဟိုက်":
        is_active = True
        await config_col.update_one({"key": "bot_status"}, {"$set": {"value": "active"}}, upsert=True)
        await event.reply("စာလိုက်ထောက်ပီ")

    elif cmd == "/ဟိုက်း":
        is_active = False
        await config_col.update_one({"key": "bot_status"}, {"$set": {"value": "inactive"}}, upsert=True)
        await event.reply("စာလိုက်ထောက်တော့ဘူးမောတယ်")

    elif cmd == "/replyမှတ်":
        if is_scraping:
            await event.reply("⚠️ ယခုအချိန်တွင် စာမှတ်ခြင်းအလုပ် လုပ်ဆောင်နေဆဲဖြစ်သည်!")
            return
        asyncio.create_task(scrape_history_task())

# ==========================================
# 🚀 SYSTEM STARTUP LOGIC
# ==========================================
async def startup():
    global is_active, userbot
    print("⏳ System starting up and loading configurations from MongoDB...")
    
    # 🌍 Render Health Check အတွက် Web Server အတုကို Background Task အနေဖြင့် စတင်မောင်းနှင်ခြင်း
    asyncio.create_task(start_dummy_web_server())

    status_doc = await config_col.find_one({"key": "bot_status"})
    if status_doc and status_doc.get("value") == "active":
        is_active = True
        print("➡️ Auto-Reply Status: ACTIVE")

    session_doc = await config_col.find_one({"key": "string_session"})
    if session_doc:
        try:
            session_str = session_doc.get("value")
            userbot = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
            await userbot.start()
            userbot.add_event_handler(handle_userbot_reply, events.NewMessage(chats=SPECIFIC_GROUP))
            print("🚀 Userbot Session Successfully Loaded from DB!")
        except Exception as e:
            print(f"⚠️ Failed to load existing Userbot Session: {e}")
    else:
        print("💡 No String Session found in DB yet. Waiting for /string command in group.")

    await bot.start(bot_token=BOT_TOKEN)
    print("🤖 Official Bot is running...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(startup())
