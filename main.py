import os
import asyncio
import random
import time
import re
from telethon import TelegramClient, events, errors, functions, types
from telethon.sessions import StringSession
from motor.motor_asyncio import AsyncIOMotorClient

# ==========================================
# ⚙️ CONFIGURATION (Credentials)
# ==========================================
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/telegram_bot?appName=Cluster0&tlsAllowInvalidCertificates=true"
APP_ID = 39584681
APP_HASH = 'c8c0685d6dd5b9e546093ea90d27733b'
BOT_TOKEN = '8111794244:AAGpkLE7h5x_IYFvjkVCbJosDC1TFbCGxcQ'

OWNER_ID = 6015356597
SPECIFIC_GROUP = -1003940667453

# 🎯 BOT & CHAT ID CONFIGURATIONS
SPAWN_BOT_ID = 6157455819
HINT_BOT_ID = 8506436817
WAIFU_CHAT_ID = -1003940667453

# Global Sniper States
spawn_tracker = {}            
last_spawn_chat_id = None     
HINT_REGEX = re.compile(r"(/catch\s+[^\n]+)") 
is_catch_stopped = False      
joined_chats_cache = set()    # Link အထပ်ထပ် Join ခြင်းမှ ကာကွယ်ရန် Cache Memory

# MongoDB Setup (သန့်စင်ပြီး Config တစ်ခုတည်းသာ ချန်ထားသည်)
client_mongo = AsyncIOMotorClient(MONGO_URI)
db = client_mongo["telegram_bot"]
config_col = db["config_col"]

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

# ⏱️ /catch command အား ၁ စက္ကန့်အကြာတွင် အလိုအလျောက် ပြန်ဖျက်ပေးမည့် Task
async def delete_catch_message_delayed(client, chat_id, msg_id):
    try:
        await asyncio.sleep(1)
        await client.delete_messages(chat_id, msg_id)
        print(f"🗑️ Auto-deleted /catch message {msg_id} after 1 second.")
    except Exception as e:
        print(f"❌ Failed to delete /catch message: {e}")

# ==========================================
# 🔗 [NEW] AUTO JOIN GROUPS & VERIFY SPAWN BOT HANDLER
# ==========================================
async def auto_link_joiner_and_verifier_handler(event):
    global joined_chats_cache
    if not event.text:
        return
    
    # Message ထဲမှာ ပါသမျှ Telegram Public Link နှင့် Private Link (Join Hash) များကို ဆွဲထုတ်ခြင်း
    links = re.findall(r'(?:t\.me|telegram\.me)/(joinchat/|\+|)?([a-zA-Z0-9_\-]{4,})', event.text)
    
    for prefix, invite_hash in links:
        if invite_hash in joined_chats_cache or invite_hash.lower() == "bot":
            continue
            
        joined_chats_cache.add(invite_hash)
        if len(joined_chats_cache) > 1000:
            joined_chats_cache.clear() # Cache Overflow မဖြစ်အောင် ရှင်းထုတ်ခြင်း
            
        try:
            chat_entity = None
            # 1. Link အမျိုးအစားအလိုက် အလိုအလျောက် ဝင်ရောက်ခြင်း (Auto Join)
            if prefix in ['joinchat/', '+']: 
                updates = await event.client(functions.messages.ImportChatInviteRequest(hash=invite_hash))
                if hasattr(updates, 'chats') and updates.chats:
                    chat_entity = updates.chats[0]
            else: 
                updates = await event.client(functions.channels.JoinChannelRequest(channel=invite_hash))
                if hasattr(updates, 'chats') and updates.chats:
                    chat_entity = updates.chats[0]
            
            # 2. Group ထဲ ရောက်သွားပြီဆိုလျှင် Spawn Bot ရှိမရှိ အဆင့်မြင့်နည်းလမ်းဖြင့် စစ်ဆေးခြင်း
            if chat_entity:
                # Channel/Broadcast ဖြစ်နေပါက Skip မည် (Group / Megagroup သာ ဖြစ်ရမည်)
                if hasattr(chat_entity, 'broadcast') and chat_entity.broadcast:
                    continue
                    
                try:
                    # ကန့်သတ်ချက်ကျော်လွန်မှု မရှိစေရန် Permissions Level ဖြင့် လှမ်းစစ်ဆေးခြင်း
                    await event.client.get_permissions(chat_entity, SPAWN_BOT_ID)
                    print(f"✅ Spawn Bot is already in: {chat_entity.title}")
                except errors.UserNotParticipantError:
                    # Spawn Bot မရှိပါက မိမိ၏ Saved Messages ဆီသို့ Link တန်းပို့မည်
                    full_url = f"https://t.me/+{invite_hash}" if prefix in ['joinchat/', '+'] else f"https://t.me/{invite_hash}"
                    await event.client.send_message(
                        'me', 
                        f"⚠️ **Spawn Bot မရှိသေးသော Group အသစ်ကို တွေ့ရှိရပါသည် Chief!**\n\n"
                        f"🏢 **Group Name:** {chat_entity.title}\n"
                        f"🔗 **Group Link:** {full_url}"
                    )
                    print(f"🎯 Reported Group without Spawn Bot: {chat_entity.title}")
                    
        except errors.rpcerrorlist.FloodWaitError as e:
            print(f"⚠️ Auto-Join FloodWait: Waiting {e.seconds}s")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"❌ Join/Verify Error for {invite_hash}: {e}")

# ==========================================
# ⚔️ ANIME SPAWN DETECTOR & CATCHER HANDLERS
# ==========================================
async def spawn_detector_handler(event):
    global last_spawn_chat_id, spawn_tracker
    if event.sender_id == SPAWN_BOT_ID and event.text:
        if "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ɪɴ ᴛʜᴇ ᴄʜᴀᴛ!" in event.text or "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ɪɴ ᴛʜᴇ ᴄʜᴀᴛ!" in event.text or "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ɪɴ ᴛʜᴇ ᴄʜᴀᴛ!" in event.text:
            
            # Ban ခံရခြင်းမှ ကာကွယ်ရန် တားမြစ်ထားသော Group ID များ
            if event.chat_id in [-1003067509608]:
                return  

            # 🔵 🟣 🟠 ပါဝင်လာပါက ငြိမ်နေစေရန်
            if any(emoji in event.text for emoji in ["🔵", "🟣", "🟠","🟡"]):
                return  

            orig_chat_id = event.chat_id
            last_spawn_chat_id = orig_chat_id  
            
            try:
                fwd_msg = await event.message.forward_to(WAIFU_CHAT_ID)
                reply_msg = await fwd_msg.reply("/waifu")
                
                spawn_tracker[fwd_msg.id] = orig_chat_id
                spawn_tracker[reply_msg.id] = orig_chat_id
                
                if len(spawn_tracker) > 100:
                    spawn_tracker.pop(next(iter(spawn_tracker)))
            except Exception:
                pass

async def hint_solver_handler(event):
    global last_spawn_chat_id, spawn_tracker, is_catch_stopped
    
    if is_catch_stopped:
        return

    if event.chat_id == WAIFU_CHAT_ID and event.sender_id == HINT_BOT_ID and event.text:
        match = HINT_REGEX.search(event.text)
        if match:
            catch_command = match.group(1).strip(" `\n\r")
            target_group = last_spawn_chat_id
            
            if event.reply_to_msg_id and event.reply_to_msg_id in spawn_tracker:
                target_group = spawn_tracker[event.reply_to_msg_id]
                
            if target_group:
                if target_group in [-1003067509608]:
                    return
                try:
                    delay_time = random.uniform(0.15, 0.25) 
                    async with event.client.action(target_group, 'typing'):
                        await asyncio.sleep(delay_time)
                        
                    sent_msg = await event.client.send_message(target_group, catch_command)
                    asyncio.create_task(delete_catch_message_delayed(event.client, target_group, sent_msg.id))
                except Exception as e:
                    print(f"❌ Catch Error: {e}")

# 📦 [FIXED & PERFECT] မိမိကိုယ်တိုင် ဖမ်းမိတဲ့ ကတ် Report များကိုသာ Forward မည့်စနစ်
async def catch_success_forwarder_handler(event):
    """ Mention Entities နှင့် Link Structure ပါမကျန် စစ်ဆေးပြီး အောင်မြင်မှုများကို 100% တိကျစွာ Forward ပို့ပေးမည့် စနစ်အမှန် """
    if event.sender_id == SPAWN_BOT_ID and event.text:
        if "ʏᴏᴜ ɢᴏᴛ ᴀ ᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀ!" in event.text:
            
            is_my_catch = False
            # 1. ရှင်းလင်းသော Mention Flag ပါဝင်မှု ရှိမရှိ စစ်ဆေးခြင်း
            if event.message.mentioned:
                is_my_catch = True
            # 2. Text ထဲတွင် မိမိ ID တိုက်ရိုက်ပါဝင်မှု ရှိမရှိ စစ်ဆေးခြင်း
            elif str(OWNER_ID) in event.text:
                is_my_catch = True
            # 3. Text Block Entities (Inline Link Tags) ထဲတွင် မိမိ ID ပါဝင်မှု ရှိမရှိ စစ်ဆေးခြင်း
            elif event.message.entities:
                for entity in event.message.entities:
                    if isinstance(entity, types.MessageEntityMentionName) and entity.user_id == OWNER_ID:
                        is_my_catch = True
                        break
                    elif hasattr(entity, 'url') and entity.url and f"tg://user?id={OWNER_ID}" in entity.url:
                        is_my_catch = True
                        break
            
            # မိမိဖမ်းမိတာ သေချာပြီဆိုလျှင် စနစ်မှန်ဖြင့် Forward လှမ်းပို့ခြင်း
            if is_my_catch:
                try:
                    # Userbot Event ဖြစ်သောကြောင့် event.client.forward_messages ကို အသုံးပြုရမည်
                    await event.client.forward_messages(SPECIFIC_GROUP, event.message)
                    print("📦 Successfully Forwarded YOUR OWN success catch report to SPECIFIC_GROUP.")
                except Exception as e:
                    print(f"❌ Success Card Forward Error: {e}")

# ==========================================
# 🤖 OFFICIAL BOT COMMAND HANDLERS
# ==========================================
@bot.on(events.NewMessage(chats=SPECIFIC_GROUP))
async def handle_bot_commands(event):
    global userbot, is_catch_stopped
    
    if event.sender_id != OWNER_ID:
        return

    cmd = event.message.text.strip() if event.message.text else ""

    # 🔑 [UPDATED] /pmk command ဖြင့် String Session အရှည်ကြီးကို Reply ထိုင်ပြီး သိမ်းဆည်းနိုင်မည့် စနစ်
    if cmd.startswith("/pmk"):
        args = cmd.split(maxsplit=1)
        session_str = None
        
        if len(args) > 1:
            session_str = args[1].strip()
        elif event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg and reply_msg.text:
                session_str = reply_msg.text.strip()
                
        if not session_str:
            await event.reply("❌ **String Session တန်ဖိုး မတွေ့ရှိပါ။ ပြန်လည်စစ်ဆေးပါ။**")
            return
            
        await config_col.update_one(
            {"key": "string_session"},
            {"$set": {"value": session_str}},
            upsert=True
        )
        await event.reply("✅ String Session ကို DB တွင် သိမ်းဆည်းလိုက်ပါပြီ။ Userbot ကို စတင်ချိတ်ဆက်နေပါသည်...")
        
        try:
            if userbot:
                await userbot.disconnect()
            userbot = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
            await userbot.start()
            
            # Core Handlers များကိုသာ သန့်ရှင်းစွာ Register ပြုလုပ်ခြင်း
            userbot.add_event_handler(spawn_detector_handler, events.NewMessage())
            userbot.add_event_handler(hint_solver_handler, events.NewMessage())
            userbot.add_event_handler(catch_success_forwarder_handler, events.NewMessage())
            userbot.add_event_handler(auto_link_joiner_and_verifier_handler, events.NewMessage()) # 🔗 Auto-Join Core
            
            await event.reply("🚀 **Userbot is Live & Connected Successfully! Sniper Mod Active.**")
        except Exception as e:
            await event.reply(f"❌ Userbot အသက်သွင်းမှု မအောင်မြင်ပါ: {e}")

    elif cmd == "/stop":
        is_catch_stopped = True
        await event.reply("🛑 **Chief! `/catch` လုပ်ငန်းစဉ်ကို ရပ်ဆိုင်းလိုက်ပါပြီ။**\n(Auto-Join နှင့် Forward စနစ်များတော့ ဆက်လက်အလုပ်လုပ်နေပါမည်)")

    elif cmd == "/start":
        is_catch_stopped = False
        await event.reply("✅ **Chief! `/catch` လုပ်ငန်းစဉ်ကို ပြန်လည်စတင်လိုက်ပါပြီ။**")

# ==========================================
# 🚀 SYSTEM STARTUP LOGIC
# ==========================================
async def startup():
    global userbot
    print("⏳ System starting up and loading session from MongoDB...")
    
    asyncio.create_task(start_dummy_web_server())

    session_doc = await config_col.find_one({"key": "string_session"})
    if session_doc:
        try:
            session_str = session_doc.get("value")
            userbot = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
            await userbot.start()
            
            # Startup တွင် Handlers များ အလိုအလျောက် သတ်မှတ်ခြင်း
            userbot.add_event_handler(spawn_detector_handler, events.NewMessage())
            userbot.add_event_handler(hint_solver_handler, events.NewMessage())
            userbot.add_event_handler(catch_success_forwarder_handler, events.NewMessage())
            userbot.add_event_handler(auto_link_joiner_and_verifier_handler, events.NewMessage()) # 🔗 Auto-Join Core
            
            print("🚀 Userbot Session Successfully Loaded from DB!")
        except Exception as e:
            print(f"⚠️ Failed to load existing Userbot Session: {e}")
    else:
        print("💡 No String Session found in DB yet. Use /pmk to setup.")

    await bot.start(bot_token=BOT_TOKEN)
    print("🤖 Official Bot is running smoothly...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(startup())
