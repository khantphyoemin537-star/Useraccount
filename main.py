import os  # 👈 Render ရဲ့ Port ကို ဖတ်ဖို့အတွက်
import asyncio
import random
import time
import logging
import re  # 👈 Catch Command များကို Regex ဖြင့် တိကျစွာဆွဲထုတ်ရန်
from telethon import TelegramClient, events, errors, functions
from telethon.sessions import StringSession
from motor.motor_asyncio import AsyncIOMotorClient

# ==========================================
# ⚙️ CONFIGURATION (Credentials)
# ==========================================
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/telegram_bot?appName=Cluster0&tlsAllowInvalidCertificates=true"
APP_ID = 39584681
APP_HASH = 'c8c0685d6dd5b9e546093ea90d27733b'
BOT_TOKEN = '8111794244:AAGpkLE7h5x_IYFvjkVCbJosDC1TFbCGxcQ'

OWNER_ID = 7937055613
SPECIFIC_GROUP = -1003580630981
COOLDOWN_TIME = 15

# 🎯 NEW CHAT & BOT CONFIGURATIONS
SPAWN_BOT_ID = 6157455819
HINT_BOT_ID = 8506436817
WAIFU_CHAT_ID = -1003940667453
VOICE_TARGET_USER_ID = 6487086190

# Global States
is_active = False
is_scraping = False
is_adding_contacts = False  
user_cooldowns = {}
is_talker_active = False       
message_count = 0
spam_tasks = {}
spawn_tracker = {}            # Waifu Chat ထဲက ID တွေကို မူရင်း Group ID နဲ့ ချိတ်ဆက်ပေးမယ့် မြန်နှုန်းမြင့် Map
last_spawn_chat_id = None     # Hint Bot က Reply မပြန်ခဲ့ရင် သုံးမယ့် Fallback Group ID
HINT_REGEX = re.compile(r"(/catch\s+[^\n]+)") #

# MongoDB Setup
client_mongo = AsyncIOMotorClient(MONGO_URI)
db = client_mongo["telegram_bot"]
reply_save_col = db["reply_save_col"]
target_bots_col = db["target_bots"]  
config_col = db["config_col"]
talk_col = db["random_talk"]   
filters_col = db["filters"]

# Initialize Official Bot Client
bot = TelegramClient('official_bot_session', APP_ID, APP_HASH)
userbot = None  

# ==========================================
# 🌍 DUMMY HTTP SERVER FOR RENDER HEALTH CHECK
# ==========================================
async def handle_render_health_check(reader, writer):
    await reader.read(100)
    response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nOK"
    writer.write(response.encode('utf-8'))
    await writer.drain()
    writer.close()

async def start_dummy_web_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = await asyncio.start_server(handle_render_health_check, '0.0.0.0', port)
        print(f"🌍 Dummy HTTP Server started on port {port} for Render Health Check!")
        async with server:
            await server.serve_forever()
    except Exception as e:
        print(f"❌ Failed to start Dummy Web Server: {e}")

# ==========================================
# 🗑️ ANTI-FLOOD DELAYED DELETION TASK
# ==========================================
async def delete_bot_message_delayed(event, bot_msg_id, cmd_msg_id=0):
    try:
        await asyncio.sleep(3)
        to_delete = [bot_msg_id]
        if cmd_msg_id:
            to_delete.append(cmd_msg_id)
            
        await event.client.delete_messages(event.chat_id, to_delete)
        print(f"🗑️ Auto-deleted message {bot_msg_id} after delay.")
        
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
# ⚔️ ANTI-FLOOD RAID / SPAM TASK SYSTEM
# ==========================================
async def run_raid_spam_task(event, reply_msg_id, chat_id):
    try:
        while True:
            pipeline = [{"$sample": {"size": 1}}]
            cursor = filters_col.aggregate(pipeline)
            docs = await cursor.to_list(length=1)
            
            if docs:
                reply_text = docs[0].get("text") or docs[0].get("word") or "🎯"
                try:
                    await event.client.send_message(
                        chat_id, 
                        reply_text, 
                        reply_to=reply_msg_id
                    )
                    await asyncio.sleep(1.0)
                    
                except errors.rpcerrorlist.FloodWaitError as e:
                    print(f"⚠️ FloodWait မိသွားသဖြင့် {e.seconds} စက္ကန့် စောင့်ဆိုင်းနေသည်။")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    print(f"❌ Spam Error: {e}")
                    await asyncio.sleep(1.0)
            else:
                await asyncio.sleep(2.0)
                
    except asyncio.CancelledError:
        print(f"🛑 Chat ID: {chat_id} တွင် Raid လုပ်ငန်းစဉ် ရပ်တန့်ပြီး။")

# ==========================================
# ⚔️ NEW ANIME SPAWN DETECTOR & CATCHER HANDLERS (ULTRA SPEED OPTIMIZED)
# ==========================================
async def spawn_detector_handler(event):
    global last_spawn_chat_id, spawn_tracker
    """ Spawn Bot က ပုံ/ဗီဒီယိုနှင့် စာပို့လာပါက ဖမ်းဆီး၍ Forward ပို့မည့်စနစ် (မူရင်းစာကို မည်သည့် Group တွင်မှ ဖျက်ဆီးခြင်း မပြုတော့ပါ) """
    if event.sender_id == SPAWN_BOT_ID and event.text:
        if "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ɪɴ ᴛʜᴇ ᴄʜᴀᴛ!" in event.text:
            
            # 1. ⚡ 🔵 🟣 🟠 ပါဝင်လာပါက မည်သည့်အလုပ်မှ မလုပ်ဘဲ လုံးဝ ငြိမ်နေစေရန် (Forward မလုပ်၊ မဖျက်ပါ)
            if any(emoji in event.text for emoji in ["🔵", "🟣", "🟠"]):
                return  # 👈 ဒီနေရာမှာတင် လုပ်ငန်းစဉ် အားလုံးကို ရပ်တန့်ပစ်ပါတယ်။

            # 2. ⚡ ကျန်တဲ့ အီမိုဂျီအမျိုးအစားအားလုံးအတွက် အလုပ်လုပ်မည့်အပိုင်း (မဖျက်တော့ပါ)
            orig_chat_id = event.chat_id
            last_spawn_chat_id = orig_chat_id  # တခြား Group တွေအတွက်ပါ သိမ်းထားပေးခြင်း
            
            try:
                # ⚡ Ultra Speed: မူရင်းစာကို ဖျက်တဲ့စနစ် (del_task) ကို အပြီးတိုင်ဖြုတ်လိုက်ပြီး Waifu Chat ထံ တိုက်ရိုက် Forward ပို့ပါမည်
                fwd_msg = await event.message.forward_to(WAIFU_CHAT_ID)
                
                # Forward ပြီးတာနဲ့ /waifu လို့ ချက်ချင်း Reply ပြန်အော်မည်
                reply_msg = await fwd_msg.reply("/waifu")
                
                # Hint Solver အတွက် ID များကို အမြန်မှတ်သားခြင်း
                spawn_tracker[fwd_msg.id] = orig_chat_id
                spawn_tracker[reply_msg.id] = orig_chat_id
                
                if len(spawn_tracker) > 100:
                    spawn_tracker.pop(next(iter(spawn_tracker)))
                    
            except Exception:
                pass


async def hint_solver_handler(event):
    global last_spawn_chat_id, spawn_tracker
    """ Hint ပေးသော Bot ထံမှ /catch command ကို copy ယူပြီး မူရင်း Group ဆီသို့ အမြန်လှမ်းပို့မည့်စနစ် """
    if event.chat_id == WAIFU_CHAT_ID and event.sender_id == HINT_BOT_ID and event.text:
        # Pre-compiled Regex ဖြင့် စာသားကို အမြန်ဆုံး ဖြတ်ထုတ်ဖတ်ယူပါတယ်
        match = HINT_REGEX.search(event.text)
        if match:
            # ⚡ ပြင်ဆင်ချက် - ဘေးနားက ကပ်ပါလာတဲ့ Backtick ( ` ) တွေနဲ့ Space တွေကို အကုန် ရှင်းထုတ်ပစ်တာပါ Chief
            catch_command = match.group(1).strip(" `\n\r")
            
            # Default အနေနဲ့ နောက်ဆုံး Spawn ခဲ့တဲ့ Group ID ကို သတ်မှတ်မယ်
            target_group = last_spawn_chat_id
            
            # Hint Bot က Reply ပြန်ထားတဲ့ စာသား ID ရှိရင် အဆိုပါ ID ရဲ့ မူရင်း Group ကို ရှာဖွေမယ်
            if event.reply_to_msg_id and event.reply_to_msg_id in spawn_tracker:
                target_group = spawn_tracker[event.reply_to_msg_id]
                
            if target_group:
                try:
                    # ⚡ စက္ကန့်ပိုင်းအတွင်း မူရင်း Group ထံသို့ သန့်စင်ပြီးသား Command အမြန်လှမ်းပို့ခြင်း
                    await event.client.send_message(target_group, catch_command)
                except Exception:
                    pass



# ==========================================
# 🎙️ VOICE ARCHIVER SYSTEM (NEW & HISTORICAL)
# ==========================================
async def voice_archiver_handler(event):
    """ သတ်မှတ်ထားသော User ထံမှ အသစ်ဝင်လာသမျှ Voice Message များကို Saved Messages ထဲ အလိုအလျောက်သိမ်းဆည်းပေးခြင်း """
    if event.chat_id == SPECIFIC_GROUP and event.sender_id == VOICE_TARGET_USER_ID:
        if event.message.voice:
            try:
                await event.message.forward_to('me')
                print("🎙️ Saved new voice message to Saved Messages.")
            except Exception as e:
                print(f"❌ New Voice Archive Error: {e}")

async def archive_past_voices_task(client):
    """ Bot စတက်တက်ချင်း အဆိုပါ User ရဲ့ အရင်က ပို့ထားသမျှ Voice အဟောင်းများအားလုံးကို Saved Messages ထဲ သိမ်းဆည်းခြင်း """
    print("⏳ Archiving past voice messages from target user...")
    try:
        async for msg in client.iter_messages(SPECIFIC_GROUP, from_user=VOICE_TARGET_USER_ID):
            if msg.voice:
                try:
                    await msg.forward_to('me')
                    await asyncio.sleep(1.0)  # Flood wait မမိစေရန် Delay ထိန်းခြင်း
                except errors.rpcerrorlist.FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception:
                    pass
        print("✅ Historical voice messages archiving process completed!")
    except Exception as e:
        print(f"❌ Historical Voice Archiving Task Error: {e}")

# ==========================================
# 🧠 USERBOT EVENT HANDLER (COLLECTIVE & RAID SYSTEM)
# ==========================================
async def handle_userbot_reply(event):
    global is_active, user_cooldowns, is_talker_active, message_count, spam_tasks
    
    if not event.message or event.message.text is None:
        return

    cmd = event.message.text.strip()

    # ------------------------------------------------------------------------
    # ⚔️ USERBOT RAID COMMANDS (Chief ကိုယ်တိုင် ဘယ် Chat မှာမဆို သုံးနိုင်မည့်စနစ်)
    # ------------------------------------------------------------------------
    if event.out:  
        if cmd == "သေမယ်နော်" and event.is_reply:
            if event.chat_id in spam_tasks:
                spam_tasks[event.chat_id].cancel()
                
            reply_msg = await event.get_reply_message()
            task = asyncio.create_task(run_raid_spam_task(event, reply_msg.id, event.chat_id))
            spam_tasks[event.chat_id] = task
            
            await event.delete()  
            return
            
        elif cmd == "ဖာသည်မသား":
            if event.chat_id in spam_tasks:
                spam_tasks[event.chat_id].cancel()
                del spam_tasks[event.chat_id]
                
            await event.delete()  
            return

    # 🛡️ ကျန်တဲ့ Auto-Reply / Talker စနစ်များကို သတ်မှတ်ထားတဲ့ Group တစ်ခုတည်းမှာပဲ အလုပ်လုပ်စေရန် Lock ခတ်ခြင်း
    if event.chat_id != SPECIFIC_GROUP:
        return

    # ------------------------------------------------------------------------
    # 🎯 Bot ID ကို Auto-Delete စာရင်းထဲ သွင်းခြင်း
    # ------------------------------------------------------------------------
    if event.sender_id == OWNER_ID and cmd == "/ဖျက်မည်":
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            reply_sender = await reply_msg.get_sender()
            
            if reply_sender and reply_sender.bot:
                bot_id = reply_sender.id
                await target_bots_col.update_one(
                    {"bot_id": bot_id},
                    {"$set": {"bot_id": bot_id, "username": reply_sender.username}},
                    upsert=True
                )
                await event.reply(f"🎯 Bot ID: `{bot_id}` (@{reply_sender.username}) ကို မှတ်ပြီးပါပြီ။")
                asyncio.create_task(delete_bot_message_delayed(event, reply_msg.id, event.id))
                return

    sender = await event.get_sender()
    # 🤖 Target Bot ဟုတ်မဟုတ် စစ်ပြီး ဖျက်ခြင်း
    if sender and sender.bot:
        is_target = await target_bots_col.find_one({"bot_id": event.sender_id})
        if is_target:
            asyncio.create_task(delete_bot_message_delayed(event, event.id, 0))
            return

    # 🗣️ Talker စနစ် (Every 6 messages -> Send 1 random DB line)
    if is_talker_active:
        if event.out or (sender and sender.bot):
            return

        user_text = event.message.text.strip()
        if not user_text:
            return

        message_count += 1
        if message_count >= 8:
            message_count = 0
            pipeline = [{"$sample": {"size": 1}}]
            cursor = talk_col.aggregate(pipeline)
            random_docs = await cursor.to_list(length=1)

            if random_docs:
                reply_text = random_docs[0].get("text")
                if reply_text:
                    try:
                        await event.client.send_read_acknowledge(event.chat_id, max_id=event.id)
                        typing_delay = max(2.0, min(len(reply_text) * 0.1, 5.0))
                        async with event.client.action(event.chat_id, 'typing'):
                            await asyncio.sleep(typing_delay)
                        await event.respond(reply_text)
                    except Exception as e:
                        print(f"❌ Talker Error: {e}")
            return

    # 💬 Auto-Reply Logic
    if not is_active or event.out or (sender and sender.bot):
        return

    user_text = event.message.text.strip().lower()
    if not user_text:
        return

    user_id = event.sender_id
    current_time = time.time()
    if user_id in user_cooldowns and (current_time - user_cooldowns[user_id] < COOLDOWN_TIME):
        return

    user_cooldowns[user_id] = current_time

    try:
        reply_text = None
        match_pipeline = [
            {"$match": {
                "$and": [
                    {"$expr": {"$gte": [{"$strLenCP": "$trigger"}, 3]}},
                    {"trigger": {"$regex": user_text, "$options": "i"}}
                ]
            }},
            {"$sample": {"size": 1}}
        ]
        
        cursor_match = reply_save_col.aggregate(match_pipeline)
        matched_docs = await cursor_match.to_list(length=1)

        if matched_docs and matched_docs[0].get("responses"):
            reply_text = random.choice(matched_docs[0]["responses"])
        else:
            if random.random() < 0.20:  
                pipeline_fallback = [{"$sample": {"size": 1}}]
                cursor_fallback = reply_save_col.aggregate(pipeline_fallback)
                random_docs = await cursor_fallback.to_list(length=1)
                
                if random_docs and random_docs[0].get("responses"):
                    reply_text = random.choice(random_docs[0]["responses"])
                else:
                    cursor_talk = talk_col.aggregate(pipeline_fallback)
                    random_talk_docs = await cursor_talk.to_list(length=1)
                    reply_text = random_talk_docs[0].get("text") if random_talk_docs else None
            else:
                return

        if reply_text:
            await event.client.send_read_acknowledge(event.chat_id, max_id=event.id)
            async with event.client.action(event.chat_id, 'voice'):
                await asyncio.sleep(random.uniform(1.5, 3.5))
            await event.reply(reply_text)

    except Exception as e:
        print(f"❌ Auto-Reply Error: {e}")

# ==========================================
# 📢 USERBOT MASS BROADCAST SYSTEM (ANTI-LOOP & ANTI-FLOOD)
# ==========================================
# 🛠️ ပြင်ဆင်ချက် - `@userbot.on` Decorator အမှားအား ဖယ်ရှားပြီးပါပြီ
async def mass_broadcast_handler(event):
    # မိမိကိုယ်တိုင် စာတစ်ကြောင်းကို /ပို့ ဆိုပြီး Reply ပြန်မှ အလုပ်လုပ်မည်
    if event.text and event.text.strip() == '/ပို့' and event.is_reply:
        
        # Saved Messages ('me') သို့မဟုတ် SPECIFIC_GROUP ထဲမှာပဲ သုံးခွင့်ပေးရန် စစ်ဆေးခြင်း
        if event.chat_id == 'me' or event.chat_id == SPECIFIC_GROUP:
            
            # Reply ထားသော မူရင်းစာကို ရယူခြင်း
            target_msg = await event.get_reply_message()
            
            # စာပို့နေစဉ်အတွင်း Loop ထပ်မလည်စေရန် /ပို့ Command စာသားကို ချက်ချင်း ဖျက်ပစ်ခြင်း
            await event.delete()
            
            # လုပ်ငန်းစဉ် စတင်ကြောင်း Status ပြပေးရန် (Saved Messages သို့မဟုတ် မူရင်း Group ထဲသို့ ပို့ပေးမည်)
            status_msg = await event.client.send_message(event.chat_id, "🔄 **Mass Broadcast လုပ်ငန်းစဉ် စတင်နေပါပြီ...**")
            
            success_count = 0
            fail_count = 0
            
            # လက်ရှိအကောင့် ဝင်ထားသမျှ (အဟောင်း/အသစ်/Public/Private) Chat စာရင်းအားလုံးကို ဆွဲထုတ်ခြင်း
            dialogs = await event.client.get_dialogs()
            
            for dialog in dialogs:
                # Group နှင့် Supergroup များကိုသာ ရွေးထုတ်ပြီး စာပို့မည်
                if dialog.is_group:
                    
                    # စာပြန်အော်တဲ့ Loop ပတ်မနေစေရန် လက်ရှိ Command ပို့လိုက်တဲ့ Chat ID ကို ချန်လှပ်ခဲ့မည်
                    if dialog.id == event.chat_id:
                        continue
                        
                    try:
                        # မူရင်းစာကို သက်ဆိုင်ရာ Group ထဲသို့ လှမ်းပို့ခြင်း (Forward မဟုတ်ဘဲ စာအသစ်အနေဖြင့် ပို့ပေးမည်)
                        await event.client.send_message(dialog.id, target_msg)
                        success_count += 1
                        
                        # Flood Wait မမိစေရန် တစ်ခုနှင့်တစ်ခုကြား 2.5 စက္ကန့်မှ 4.5 စက္ကန့်အထိ ကျပန်း နားပြီးမှ ပို့မည်
                        await asyncio.sleep(random.uniform(2.5, 4.5))
                        
                    except errors.rpcerrorlist.FloodWaitError as e:
                        # တကယ်လို့ Telegram ဘက်က FloodWait ပေးခဲ့ရင် အဆိုပါ စက္ကန့်အတိုင်း စောင့်ဆိုင်းပြီးမှ ဆက်သွားမည်
                        print(f"⚠️ FloodWait မိသွားသဖြင့် {e.seconds} စက္ကန့် စောင့်ဆိုင်းနေရသည်။")
                        await asyncio.sleep(e.seconds)
                        try:
                            await event.client.send_message(dialog.id, target_msg)
                            success_count += 1
                        except Exception:
                            fail_count += 1
                            
                    except Exception as e:
                        # စာပို့ခွင့်ပိတ်ထားခံရခြင်း (ChatWriteForbidden)၊ အထုတ်ခံရခြင်း သို့မဟုတ် စာဖျက်ခံရခြင်းများကို ဖမ်းယူခြင်း
                        fail_count += 1
                        continue
            
            # 📊 လုပ်ငန်းစဉ်ပြီးဆုံးပါက ရလဒ်များကို သေချာတွက်ချက်ပြီး အစီရင်ခံစာ ထုတ်ပေးခြင်း
            report_text = (
                f"📊 **Broadcast လုပ်ငန်းစဉ် ပြီးဆုံးပါပြီ Chief!**\n\n"
                f"✅ ပို့ဆောင်မှု အောင်မြင်သော Group: `{success_count}` ခု\n"
                f"❌ စာဖျက်ခံရ/ပို့မရသော Group: `{fail_count}` ခု\n"
                f"📈 စုစုပေါင်း အောင်မြင်မှုအရေအတွက်: `{success_count}` ခု ရှိနေပါသည်။"
            )
            # အစောနက ပြထားတဲ့ Status စာသားနေရာမှာ ရလဒ်ကို အစားထိုး ပြောင်းလဲပေးမည်
            await status_msg.edit(report_text)

# ==========================================
# 📥 USERBOT SCRAPING TASK (Emoji Preserved & 50,000 Limit)
# ==========================================
async def scrape_history_task():
    global is_scraping, userbot
    if not userbot:
        await bot.send_message(SPECIFIC_GROUP, "❌ Userbot အသက်မဝင်သေးပါ။ /string အရင်လုပ်ပေးပါ။")
        return

    is_scraping = True
    await bot.send_message(SPECIFIC_GROUP, "📥 စာဟောင်းများမှ Reply များကို စတင်မှတ်သားနေပါပြီ (အီမိုဂျီများ အပြည့်အစုံပါဝင်ပါမည်)...")
    
    try:
        msg_cache = {}
        total_saved = 0
        TARGET_LIMIT = 50000    
        FETCH_LIMIT = 100000     

        try:
            async for msg in userbot.iter_messages(SPECIFIC_GROUP, limit=FETCH_LIMIT):
                if msg and msg.text:
                    msg_cache[msg.id] = msg.text.strip()
        except Exception as cache_err:
            print(f"⚠️ Cache warning: {cache_err}")

        async for msg in userbot.iter_messages(SPECIFIC_GROUP, limit=FETCH_LIMIT):
            if not is_scraping or total_saved >= TARGET_LIMIT:
                break
            
            try:
                if msg and msg.reply_to_msg_id and msg.text:
                    parent_id = msg.reply_to_msg_id
                    parent_text = msg_cache.get(parent_id)
                    reply_text = msg.text.strip()

                    if parent_text and reply_text:
                        trigger = parent_text.lower()
                        
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

                        if total_saved % 100 == 0:
                            await bot.send_message(SPECIFIC_GROUP, f"🚀 စာစောင် ပေါင်း {total_saved} ခု DB ထဲ မှတ်ပြီးပါပြီ!")
                        
                        await asyncio.sleep(0.04)  
            except Exception as single_msg_err:
                print(f"⚠️ Skipped a message due to: {single_msg_err}")
                continue

        await bot.send_message(SPECIFIC_GROUP, f"🎉 အောင်မြင်စွာ Reply စုစုပေါင်း {total_saved} ခုကို DB ထဲ သိမ်းဆည်းပြီးပါပြီ!")
    except Exception as e:
        await bot.send_message(SPECIFIC_GROUP, f"❌ Scraping ပြဿနာတက်ခဲ့သည်: {e}")
    finally:
        is_scraping = False

# ==========================================
# 👥 USERBOT CONTACT ADDING TASK (Anti-Frozen)
# ==========================================
async def add_contacts_task():
    global is_adding_contacts, userbot
    if not userbot:
        try: await bot.send_message(SPECIFIC_GROUP, "❌ Userbot အသက်မဝင်သေးသဖြင့် လူထည့်၍မရပါ။ /string အရင်လုပ်ပါ။")
        except Exception: pass
        return

    is_adding_contacts = True
    try: await bot.send_message(SPECIFIC_GROUP, "👥 Contact များကို Group ထဲသို့ စတင်ဖိတ်ခေါ်နေပါပြီ (Anti-Frozen စနစ်ဖြင့်)...")
    except Exception: pass

    try:
        contact_data = await userbot(functions.contacts.GetContactsRequest(hash=0))
        contacts = contact_data.users
        total_contacts = len(contacts)

        if total_contacts == 0:
            try: await bot.send_message(SPECIFIC_GROUP, "ℹ️ ဆွဲထည့်ရန် Contact တစ်ယောက်မှ မရှိပါ။")
            except Exception: pass
            return

        try: await bot.send_message(SPECIFIC_GROUP, f"🔍 စုစုပေါင်း Contact {total_contacts} ယောက် တွေ့ရှိသည်။ အန္တရာယ်ကင်းမည့် Delay များဖြင့် စထည့်ပါမည်...")
        except Exception: pass

        added_count = 0
        skipped_privacy = 0
        skipped_already_in = 0
        failed_count = 0

        for contact in contacts:
            if not is_adding_contacts:
                break
            
            try:
                await userbot(functions.channels.InviteToChannelRequest(channel=SPECIFIC_GROUP, users=[contact.id]))
                added_count += 1
                await asyncio.sleep(random.uniform(7.0, 15.0))  

            except errors.rpcerrorlist.UserPrivacyRestrictedError:
                skipped_privacy += 1
            except errors.rpcerrorlist.UserAlreadyParticipantError:
                skipped_already_in += 1
            except errors.rpcerrorlist.FloodWaitError as e:
                try: await bot.send_message(SPECIFIC_GROUP, f"⚠️ FloodWait မိသဖြင့် {e.seconds} စက္ကန့် ခေတ္တစောင့်ဆိုင်းပါမည်...")
                except Exception: pass
                await asyncio.sleep(e.seconds)
                try:
                    await userbot(functions.channels.InviteToChannelRequest(channel=SPECIFIC_GROUP, users=[contact.id]))
                    added_count += 1
                except Exception:
                    failed_count += 1
            except errors.rpcerrorlist.PeerFloodError:
                try: await bot.send_message(SPECIFIC_GROUP, f"❌ PeerFloodError: အကောင့် Frozen ဖြစ်ခြင်းမှ လုံးဝကာကွယ်ရန် လူသွင်းခြင်းကို ချက်ချင်း ရပ်တန့်လိုက်ပါပြီ Chief!\n\n📊 ရလဒ် - ထည့်ပြီး: {added_count} | Privacy ကျော်: {skipped_privacy}")
                except Exception: pass
                break
            except Exception:
                failed_count += 1
                await asyncio.sleep(2.0)

            if (added_count + skipped_privacy + skipped_already_in + failed_count) % 10 == 0:
                print(f"🔄 Add Progress Check: {(added_count + skipped_privacy + skipped_already_in + failed_count)}/{total_contacts}")

        try:
            await bot.send_message(
                SPECIFIC_GROUP,
                f"📊 **လူထည့်ခြင်းလုပ်ငန်းစဉ် ပြီးဆုံးပါပြီ**\n\n"
                f"✅ အောင်မြင်စွာထည့်ပြီး: {added_count}\n"
                f"🔒 Privacy ကျော်: {skipped_privacy}\n"
                f"👥 ရှိပြီးသားမို့ကျော်: {skipped_already_in}\n"
                f"❌ မအောင်မြင်/အခြား: {failed_count}"
            )
        except Exception: pass

    except Exception as e:
        try: await bot.send_message(SPECIFIC_GROUP, f"❌ Contact Add ပြဿနာတက်ခဲ့သည်: {e}")
        except Exception: pass
    finally:
        is_adding_contacts = False

# ==========================================
# 🤖 OFFICIAL BOT COMMAND HANDLERS
# ==========================================
@bot.on(events.NewMessage(chats=SPECIFIC_GROUP))
async def handle_bot_commands(event):
    global is_active, userbot, is_scraping, is_talker_active, is_adding_contacts
    
    if event.sender_id != OWNER_ID:
        return

    cmd = event.message.text.strip() if event.message.text else ""

    if cmd == "/string" and event.is_reply:
        reply_msg = await event.get_reply_message()
        if reply_msg and reply_msg.text:
            session_str = reply_msg.text.strip()
            await config_col.update_one(
                {"key": "string_session"},
                {"$set": {"value": session_str}},
                upsert=True
            )
            await event.reply("✅ String Session ကို DB မှာ သိမ်းပြီးပါပြီ။ Userbot ချက်ဆက်နေသည်...")
            
            try:
                if userbot:
                    await userbot.disconnect()
                userbot = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
                await userbot.start()
                await userbot.get_dialogs()
                
                # Register All Userbot Handlers
                userbot.add_event_handler(handle_userbot_reply, events.NewMessage())
                userbot.add_event_handler(spawn_detector_handler, events.NewMessage())
                userbot.add_event_handler(hint_solver_handler, events.NewMessage())
                userbot.add_event_handler(voice_archiver_handler, events.NewMessage())
                # 🛠️ ပြင်ဆင်ချက် - /string လုပ်ချိန်မှာ Mass Broadcast စနစ်ကိုပါ မှတ်ပုံတင်ပေးရန် ထည့်သွင်းထားသည်
                userbot.add_event_handler(mass_broadcast_handler, events.NewMessage(outgoing=True))
                
                # Start background voice archiving task
                asyncio.create_task(archive_past_voices_task(userbot))
                
                await event.reply("🚀 Userbot is Live with Sniper & Voice Archiver Mod!")
            except Exception as e:
                await event.reply(f"❌ Userbot အလုပ်မလုပ်ပါ: {e}")

    elif cmd == "/ဟိုက်":
        is_active = True
        await config_col.update_one({"key": "bot_status"}, {"$set": {"value": "active"}}, upsert=True)
        await event.reply("စာလိုက်ထောက်ပီ")

    elif cmd == "/ဟိုက်း":
        is_active = False
        await config_col.update_one({"key": "bot_status"}, {"$set": {"value": "inactive"}}, upsert=True)
        await event.reply("စာလိုက်ထောက်တော့ဘူးမောတယ်")

    elif cmd == "/ပြောမယ်":
        is_talker_active = True
        await event.reply("💬 Talker mode activated.")
     
    elif cmd == "/မပြောဘူး":
        is_talker_active = False
        await event.reply("🔇 Talker mode deactivated.")

    elif cmd == "/replyမှတ်":
        if is_scraping:
            await event.reply("⚠️ ယခုအချိန်တွင် စာမှတ်ခြင်းအလုပ် လုပ်ဆောင်နေဆဲဖြစ်သည်!")
            return
        asyncio.create_task(scrape_history_task())

    elif cmd == "/addcontact":
        if is_adding_contacts:
            await event.reply("⚠️ လူထည့်ခြင်းလုပ်ငန်းစဉ် နောက်ကွယ်မှာ လုပ်ဆောင်နေဆဲဖြစ်သည်!")
            return
        asyncio.create_task(add_contacts_task())

# ==========================================
# 🚀 SYSTEM STARTUP LOGIC
# ==========================================
async def startup():
    global is_active, userbot
    print("⏳ System starting up and loading configurations from MongoDB...")
    
    asyncio.create_task(start_dummy_web_server())

    # 🧹 DB ထဲရှိပြီးသား အမှိုက်စာလုံးတိုများ (Trigger အရှည် ၂ လုံးအောက်) ကို အလိုအလျောက် သန့်ရှင်းရေးလုပ်ခြင်း
    try:
        deleted = await reply_save_col.delete_many({"$expr": {"$lt": [{"$strLenCP": "$trigger"}, 3]}})
        if deleted.deleted_count > 0:
            print(f"🧹 Cleaned up {deleted.deleted_count} short garbage triggers from DB.")
    except Exception as clean_err:
        print(f"⚠️ DB Cleanup Warning: {clean_err}")

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
            await userbot.get_dialogs()
            
            # Register All Userbot Handlers at Startup
            userbot.add_event_handler(handle_userbot_reply, events.NewMessage())
            userbot.add_event_handler(spawn_detector_handler, events.NewMessage())
            userbot.add_event_handler(hint_solver_handler, events.NewMessage())
            userbot.add_event_handler(voice_archiver_handler, events.NewMessage())
            userbot.add_event_handler(mass_broadcast_handler, events.NewMessage(outgoing=True))

            # Start background voice archiving task
            asyncio.create_task(archive_past_voices_task(userbot))
            
            print("🚀 Userbot Session Successfully Loaded from DB!")
        except Exception as e:
            print(f"⚠️ Failed to load existing Userbot Session: {e}")
    else:
        print("💡 No String Session found in DB yet.")

    await bot.start(bot_token=BOT_TOKEN)
    print("🤖 Official Bot is running...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(startup())

