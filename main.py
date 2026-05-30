import os  # 👈 Render ရဲ့ Port ကို ဖတ်ဖို့အတွက်
import asyncio
import random
import time
import logging
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

# Global States
is_active = False
is_scraping = False
is_adding_contacts = False  
user_cooldowns = {}
is_talker_active = False       
message_count = 0

# MongoDB Setup
client_mongo = AsyncIOMotorClient(MONGO_URI)
db = client_mongo["telegram_bot"]
reply_save_col = db["reply_save_col"]
target_bots_col = db["target_bots"]  
config_col = db["config_col"]
talk_col = db["random_talk"]   

# Initialize Official Bot Client
bot = TelegramClient('official_bot_session', APP_ID, APP_HASH)
userbot = None  

# ==========================================
# 🌍 DUMMY HTTP SERVER FOR RENDER HEALTH CHECK
# ==========================================
async def handle_render_health_check(reader, writer):
    data = await reader.read(100)
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
        await asyncio.sleep(2)
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
# 🧠 USERBOT EVENT HANDLER (AUTO-REPLY - ULTRA UPGRADED)
# ==========================================
async def handle_userbot_reply(event):
    global is_active, user_cooldowns, is_talker_active, message_count
    
    if not event.message or event.message.text is None:
        return

    # ------------------------------------------------------------------------
    # 🎯 Bot ID ကို Auto-Delete စာရင်းထဲ သွင်းခြင်း
    # ------------------------------------------------------------------------
    if event.sender_id == OWNER_ID and event.message.text.strip() == "/ဖျက်မည်":
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
                await event.reply(f"🎯 Bot ID: `{bot_id}` (@{reply_sender.username}) ကို မှတ်ပြီးပါပြီ။ ၄ စက္ကန့်အတွင်း အလိုအလျောက် ရှင်းလင်းပေးပါတော့မယ်!")
                asyncio.create_task(delete_bot_message_delayed(event, reply_msg.id, event.id))
                return

    # ------------------------------------------------------------------------
    # 🤖 Target Bot ဟုတ်မဟုတ် စစ်ပြီး ဖျက်ခြင်း
    # ------------------------------------------------------------------------
    sender = await event.get_sender()
    if sender and sender.bot:
        is_target = await target_bots_col.find_one({"bot_id": event.sender_id})
        if is_target:
            asyncio.create_task(delete_bot_message_delayed(event, event.id, 0))
            return

    # ------------------------------------------------------------------------
    # 🗣️ Talker စနစ် (Every 6 messages -> Send 1 random DB line)
    # ------------------------------------------------------------------------
    if is_talker_active:
        if event.out or (sender and sender.bot):
            return

        user_text = event.message.text.strip()
        if not user_text:
            return

        message_count += 1

        if message_count >= 10:
            message_count = 0
            pipeline = [{"$sample": {"size": 1}}]
            cursor = talk_col.aggregate(pipeline)
            random_docs = await cursor.to_list(length=1)

            if random_docs:
                doc = random_docs[0]
                reply_text = doc.get("text")
                
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

    # ------------------------------------------------------------------------
    # 💬 ညှိနှိုင်းပြင်ဆင်ထားသော Auto-Reply Logic (စာမထပ်အောင် ပုံစံသစ်ပြောင်းလဲထားမှု)
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

    user_cooldowns[user_id] = current_time

    try:
        reply_text = None

        # 🔥 အဆင့် (၁) - စာသားပါဝင်မှုကို Regex အသုံးပြု၍ ရှာဖွေပြီး ကိုက်ညီသမျှထဲမှ Random နှိုက်ခြင်း
        # စာလုံးအလွန်တိုလွန်းသော Trigger အမှိုက်များကို ဤနေရာတွင် စစ်ထုတ်ထားပါသည် (စာလုံးအရှည် ၃ လုံးနှင့်အထက်မှသာ ယူမည်)
        match_pipeline = [
            {"$match": {
                "$and": [
                    {"$expr": {"$gte": [{"$strLenCP": "$trigger"}, 3]}},  # 👈 Trigger စာလုံးအရှည် ၃ လုံးအထက်ကိုပဲ စစ်မယ်
                    {"trigger": {"$regex": user_text, "$options": "i"}}   # 👈 လူရိုက်တဲ့စာထဲမှာ ကိုက်ညီတာကို စမတ်ကျကျရှာမယ်
                ]
            }},
            {"$sample": {"size": 1}}  # 👈 ကိုက်ညီတဲ့စာရင်းထဲကမှ ၁ ခုကို ထပ်မံ Random နှိုက်ပေးမည်
        ]
        
        cursor_match = reply_save_col.aggregate(match_pipeline)
        matched_docs = await cursor_match.to_list(length=1)

        if matched_docs and matched_docs[0].get("responses"):
            reply_text = random.choice(matched_docs[0]["responses"])
        else:
            # 🎯 နေရာတကာ လိုက်မအော်ဘဲ ၄၀% အခွင့်အရေးဖြင့် DB ထဲကစာများကို Random ပတ်ထောက်မည့်စနစ်
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

        # စာသားထွက်လာရင် စာဖတ်ပြီး Voice Action ပြကာ Reply ပြန်ပေးမည်
        if reply_text:
            await event.client.send_read_acknowledge(event.chat_id, max_id=event.id)
            async with event.client.action(event.chat_id, 'voice'):
                await asyncio.sleep(random.uniform(1.5, 3.5))
            await event.reply(reply_text)

    except Exception as e:
        print(f"❌ Auto-Reply Error: {e}")


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
        TARGET_LIMIT = 50000    # 👈 Chief တောင်းဆိုချက်အရ 50,000 သို့ ပြောင်းလဲထားပါသည်
        FETCH_LIMIT = 100000     # Target ပြည့်ရန် သင့်တော်သော လှမ်းဖတ်မှုပမာဏ

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
                        
                        # 🛡️ basic filtering (Command စာလုံးများ နှင့် လင့်ခ်များကိုသာ ကျော်မည်)
                        if (trigger.startswith(('/', '.', 'မှတ်', 'reply','@')) or 
                            reply_text.startswith(('/', '.', 'မှတ်', 'reply','@')) or 
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

                        if total_saved % 10000 == 0:
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
            await event.reply("✅ String Session ကို DB မှာ သိမ်းပြီးပါပြီ။ Userbot ချိတ်ဆက်နေသည်...")
            
            try:
                if userbot:
                    await userbot.disconnect()
                userbot = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
                await userbot.start()
                await userbot.get_dialogs()
                userbot.add_event_handler(handle_userbot_reply, events.NewMessage(chats=SPECIFIC_GROUP))
                await event.reply("🚀 Userbot is Live!")
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
            userbot.add_event_handler(handle_userbot_reply, events.NewMessage(chats=SPECIFIC_GROUP))
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

