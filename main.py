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
BOT_TOKEN = '8738081667:AAHADgcDISntnOBwT3uj2yYw7n3XJUN2uZI'

OWNER_ID = 6015356597
ADMIN_ID = 0  # 👈 [FILL THIS IN] Captcha alert မှာ mention ခေါ်ရန် Admin ရဲ့ Telegram numeric user ID ကို ဒီနေရာမှာ ထည့်ပါ
SPECIFIC_GROUP = -1003999318284
MATRIX_GROUP_ID = -1003806830045  # 👈 [NEW] Matrix Group ID
COOLDOWN_TIME = 15

# 🎯 NEW CHAT & BOT CONFIGURATIONS
SPAWN_BOT_ID = 6157455819
HINT_BOT_ID = 8506436817
WAIFU_CHAT_ID = -1003999318284

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
HINT_REGEX = re.compile(r"(/catch\s+[^\n]+)") 
is_catch_stopped = False      # 👈 OWNER က Manual ထိန်းချုပ်ရန် စတိတ် (Default: အလုပ်လုပ်မည်)
is_copy_active = False

# 🚀 [NEW] Power Ranger Global States
is_powerranger_talking = False  # Talk On/Off Track လုပ်ရန်
powerranger_speed = 2           # စကားပြောနှုန်း Speed (1, 2, 3) Default: 2
powerranger_clients = []        # Unlimited Userbots Client များကို သိမ်းဆည်းရန် List
bot_last_send = {}              # 🆕 Per-bot cooldown အတွက် (client -> last_send_time)

# MongoDB Setup
client_mongo = AsyncIOMotorClient(MONGO_URI)
db = client_mongo["telegram_bot"]
reply_save_col = db["reply_save_col"]
target_bots_col = db["target_bots"]  
tomboy_col = db["tomboy_col"]  
marcuz_col = db["marcuz_col"]        # 👈 String Session / Useraccount လုပ်ဆောင်ချက်များအတွက် သီးသန့် Collection
powerranger_col = db["powerranger_col"]  # 👈 [NEW] အကန့်အသတ်မရှိ Userbots များအတွက် Database New Collection
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

# ⏱️ /catch command အား ၁ စက္ကန့်အကြာတွင် အလိုအလျောက် ပြန်ဖျက်ပေးမည့် သီးသန့် Task
async def delete_catch_message_delayed(client, chat_id, msg_id):
    try:
        await asyncio.sleep(1)
        await client.delete_messages(chat_id, msg_id)
        print(f"🗑️ Auto-deleted /catch message {msg_id} after 1 second.")
    except Exception as e:
        print(f"❌ Failed to delete /catch message: {e}")

# ==========================================
# ⚔️ NEW ANIME SPAWN DETECTOR & CATCHER HANDLERS (ULTRA SPEED OPTIMIZED)
# ==========================================
async def spawn_detector_handler(event):
    global last_spawn_chat_id, spawn_tracker
    """ Spawn Bot က ပုံ/ဗီဒီယိုနှင့် စာပို့လာပါက ဖမ်းဆီး၍ Forward ပို့မည့်စနစ် """
    if event.sender_id == SPAWN_BOT_ID and event.text:
        if "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ɪɴ ᴛʜᴇ ᴄʜᴀᴛ!" in event.text:
            
            # 🚫 Ban ခံရခြင်းမှ ကာကွယ်ရန် သတ်မှတ်ထားသော Group ID များဖြစ်ပါက လုံးဝ ငြိမ်နေစေရန်
            if event.chat_id in [-1001947407820, -1003067509608]:
                return  

            # 1. ⚡ 🔵 🟣 🟠 ပါဝင်လာပါက မည်သည့်အလုပ်မှ မလုပ်ဘဲ လုံးဝ ငြိမ်နေစေရန်
            if any(emoji in event.text for emoji in ["🔵", "🟣"]):
                return  

            # 2. ⚡ ကျန်တဲ့ အီမိုဂျီအမျိုးအစားအားလုံးအတွက် အလုပ်လုပ်မည့်အပိုင်း
            orig_chat_id = event.chat_id
            last_spawn_chat_id = orig_chat_id  
            
            try:
                # Waifu Chat ထံ တိုက်ရိုက် Forward ပို့ခြင်း
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
    global last_spawn_chat_id, spawn_tracker, is_catch_stopped
    """ Hint ပေးသော Bot ထံမှ /catch command ကို copy ယူပြီး မူရင်း Group ဆီသို့ အမြန်လှမ်းပို့မည့်စနစ် """
    
    # 🛑 OWNER က stop ထားပါက /catch သွားမပို့တော့ဘဲ Skip မည်
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
                if target_group in [-1001947407820, -1003067509608]:
                    return
                try:
                    delay_time = random.uniform(0.5, 0.7) 
                    
                    async with event.client.action(target_group, 'typing'):
                        await asyncio.sleep(delay_time)
                        
                    # 🎯 /catch လှမ်းပို့ပြီး ပို့လိုက်သော message object ကို ဖမ်းယူခြင်း
                    sent_msg = await event.client.send_message(target_group, catch_command)
                    print(f"🎯 Caught character with delay {delay_time:.2f}s")
                    
                    # 🗑️ ပို့ပြီးတာနဲ့ ၁ စက္ကန့်အကြာမှာ ထို /catch မက်ဆေ့ချ်ကို ပြန်ဖျက်ခိုင်းခြင်း
                    asyncio.create_task(delete_catch_message_delayed(event.client, target_group, sent_msg.id))
                    
                except Exception as e:
                    print(f"❌ Catch Error: {e}")

# 📦 မိမိကိုယ်တိုင် ဖမ်းမိတဲ့ ကတ် Report များကိုသာ Specific Group ထံ Forward ပေးမည့်စနစ်
async def catch_success_forwarder_handler(event):
    """ Spawn Bot က ကတ်မိသွားလို့ ʏᴏᴜ ɢᴏᴛ ᴀ ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀ! ဟု ပို့လာပြီး မိမိကို Mention ခေါ်ထားမှသာ Forward ပေးမည် """
    if event.sender_id == SPAWN_BOT_ID and event.text:
        
        # 🛠️ ပြင်ဆင်ချက် ၁ - မူလက "ေ" ပါနေသည်ကို အင်္ဂလိပ် Small Capital "ᴇ" (ʏᴏᴜ ɢᴏᴛ ᴀ ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀ!) သို့ အမှန်ပြင်ဆင်ထားသည်။
        if "ʏᴏᴜ ɢᴏᴛ ᴀ ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀ!" in event.text:
            try:
                # မိမိအကောင့်ရဲ့ လက်ရှိ Profile Name ကို လှမ်းယူခြင်း
                me = await event.client.get_me()
                first_name = me.first_name or ""
                last_name = me.last_name or ""
                full_name = f"{first_name} {last_name}".strip()
                
                # 🛠️ ပြင်ဆင်ချက် ၂ - Tag မိတာအပြင်၊ မိမိရဲ့ Full Name (သို့) First Name စာသားပါနေရင်ပါ အလုပ်လုပ်စေရန် စစ်ဆေးခြင်း
                if event.message.mentioned or (full_name and full_name in event.text) or (first_name and first_name in event.text):
                    await event.message.forward_to(SPECIFIC_GROUP)
                    print("📦 Forwarded YOUR OWN success catch card report to SPECIFIC_GROUP.")
                    
            except Exception as e:
                print(f"❌ Success Card Forward Error: {e}")


# ==========================================
# 🚨 CAPTCHA ALERT HANDLER (Owner/Admin ကို mention ခေါ်ရုံသာ — Bot က ကိုယ်တိုင် မဖြေပါ)
# ==========================================
async def captcha_alert_handler(event):
    """ Special Character Spawn အတွက် Captcha ပေါ်လာတာနဲ့ Owner + Admin ကို ချက်ချင်း
        mention ခေါ်ပြီး သတိပေးမည့်စနစ်။ 60 စက္ကန့်အတွင်း Captcha ကို လူကိုယ်တိုင်ပဲ
        ဝင်ဖြေရမည် — ဒီ handler က Bot ကို ဘာအမှန်ကိုမှ ညွှန်းပေး/ဖြေပေးခြင်း မလုပ်ပါ။ """
    if event.sender_id == SPAWN_BOT_ID and event.text:
        # 🚫 Ban ခံရနိုင်ချေရှိသော Group များတွင် လုံးဝ ငြိမ်နေစေရန် (spawn_detector_handler အတိုင်း)
        if event.chat_id in [-1001947407820, -1003067509608]:
            return

        if "captcha" in event.text.lower():
            try:
                # 🛡️ ADMIN_ID ကို မဖြည့်ရသေးရင်တောင် Owner mention ကတော့ ပုံမှန်ပို့နိုင်ရန်
                # (tg://user link မှားရင် message ပို့မှု တစ်ခုလုံး fail မဖြစ်စေရန်)
                mentions = [f'<a href="tg://user?id={OWNER_ID}">Owner</a>']
                if ADMIN_ID:
                    mentions.append(f'<a href="tg://user?id={ADMIN_ID}">Admin</a>')

                alert_text = (
                    "🚨 " + " ".join(mentions) +
                    " — Captcha ပေါ်ပါပြီ Chief! 60 စက္ကန့်အတွင်း ကိုယ်တိုင်ဝင်ဖြေပေးပါ 👆"
                )
                await event.reply(alert_text, parse_mode='html')
                print(f"🚨 Captcha alert sent, Owner/Admin mentioned in chat {event.chat_id}.")
            except Exception as e:
                print(f"❌ Captcha Alert Error: {e}")


# ==========================================
# 🗣️ [⚡ FIXED] ANTI-FLOOD GLOBAL TALKING TASK LOOP (Per-Bot Cooldown)
# ==========================================
async def start_global_talk_loop():
    """ အကောင့်တိုင်းအတွက် သီးသန့် cooldown သတ်မှတ်ပြီး Flood မကျအောင် စကားပြောစေမည့် Loop """
    global is_powerranger_talking, powerranger_speed, powerranger_clients, userbot, bot_last_send

    # Speed အလိုက် အနိမ့်ဆုံး ကြားကာလ (စက္ကန့်) - လိုသလို ပြင်ဆင်နိုင်ပါတယ်
    speed_interval = {
        1: 5.0,    # နှေး – လုံးဝဘေးကင်း
        2: 2.5,    # အလယ်အလတ် – အကောင်းဆုံး
        3: 2.5     # အမြန် – Flood မကျအောင် 2.5 ထားပါ (2.0 ထားရင် အန္တရာယ်ကင်းဆုံး အမြင့်ဆုံး)
    }

    while True:
        try:
            if is_powerranger_talking:
                all_bots = []
                if userbot:
                    all_bots.append(userbot)
                all_bots.extend(powerranger_clients)

                if all_bots:
                    now = time.time()
                    min_interval = speed_interval.get(powerranger_speed, 2.5)

                    # 📌 cooldown မကျော်သေးတဲ့ အကောင့်တွေကို ဖယ်ထုတ်
                    available = [
                        bot for bot in all_bots
                        if now - bot_last_send.get(bot, 0) >= min_interval
                    ]

                    if available:
                        current_bot = random.choice(available)

                        # DB ကနေ ကျပန်းစာတစ်ကြောင်း ယူ
                        pipeline = [{"$sample": {"size": 1}}]
                        cursor = talk_col.aggregate(pipeline)
                        docs = await cursor.to_list(length=1)
                        if docs:
                            reply_text = docs[0].get("text") or docs[0].get("word") or docs[0].get("message")
                            if reply_text:
                                try:
                                    await current_bot.send_message(MATRIX_GROUP_ID, reply_text)
                                    # ပို့ပြီးရင် ဒီအကောင့်ရဲ့ နောက်ဆုံးပို့ချိန်ကို သိမ်း
                                    bot_last_send[current_bot] = time.time()
                                except errors.rpcerrorlist.FloodWaitError as e:
                                    print(f"⚠️ FloodWait {e.seconds}s for this bot only. Cooling this bot down, others keep talking...")
                                    # 🛠️ FIX: FloodWait ကျရင် ဒီ Bot တစ်ကောင်တည်းကိုပဲ cooldown တိုးပေးလိုက်ပါ။
                                    # ယခင်က "await asyncio.sleep(e.seconds)" ကို Loop တစ်ခုလုံးနဲ့ share သုံးနေတဲ့
                                    # main loop ပေါ်မှာ ခေါ်ထားလို့ Bot တစ်ကောင်ရဲ့ FloodWait ကြောင့်
                                    # Bot 10 ကောင်လုံး တခြားအကောင့်တွေအားလုံးပါ ရပ်တန့်သွားခဲ့တာပါ (ပင်မ bug)
                                    bot_last_send[current_bot] = time.time() + e.seconds
                                except Exception as ce:
                                    print(f"❌ Send error: {ce}")

                        # 🛠️ FIX: message ပို့ပြီးတိုင်း Loop ကို လေးစားစွာ ခဏနားပေးရပါမယ်။
                        # ယခင်က ဒီနေရာမှာ sleep လုံးဝမပါလို့ cooldown ကျော်နေတဲ့ Bot တွေအားလုံး
                        # ခဏချင်းအတွင်း တခါတည်း စုပြီး Matrix Group ကို message တွေ burst အနေနဲ့
                        # ပစ်ပို့မိကာ Telegram ဘက်က Flood လို့ သတ်မှတ်ခံရတာပါ (ဒုတိယ bug)
                        # 🎯 ~50 msg/min ရအောင် pacing ကို 0.7–1.1s အထိ လျှော့ချထားသည် (Bot 5ကောင်စာ)
                        # ⚠️ ဒီထက်ပိုမြန်အောင် ထပ်လျှော့ရင် Flood ပြန်ကျနိုင်ချေ သိသိသာသာ တိုးလာမည်
                        await asyncio.sleep(random.uniform(0.7, 1.1))
                    else:
                        # အကောင့်အားလုံး cooldown ထဲဆိုရင် ခဏစောင့်
                        await asyncio.sleep(0.5)

            else:
                await asyncio.sleep(1.0)

        except Exception as e:
            print(f"❌ Global Talk Loop Error: {e}")
            await asyncio.sleep(3.0)

# ==========================================
# 🤖 OFFICIAL BOT COMMAND HANDLERS
# ==========================================
@bot.on(events.NewMessage(chats=[SPECIFIC_GROUP, MATRIX_GROUP_ID])) # 👈 [UPDAT.ED] Matrix Group မှ command များကိုပါ လက်ခံရန်
async def handle_bot_commands(event):
    global is_active, userbot, is_scraping, is_talker_active, is_catch_stopped, is_copy_active
    global is_powerranger_talking, powerranger_speed, powerranger_clients
    
    if event.sender_id != OWNER_ID:
        return

    cmd = event.message.text.strip() if event.message.text else ""

    # 🎯 /string သို့မဟုတ် /tom command ဖြင့် String Session လက်ခံပြီး marcuz_col ထဲသို့ သိမ်းဆည်းမည့်အပိုင်း
    if cmd.startswith("/marcuz") or cmd.startswith("/mc"):
        args = cmd.split(maxsplit=1)
        session_str = None
        
        if len(args) > 1:
            session_str = args[1].strip()
        elif event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg and reply_msg.text:
                session_str = reply_msg.text.strip()
                
        if not session_str:
            await event.reply("❌ **String Session မတွေ့ရှိပါ။**")
            return
            
        # tomboy_col အစား marcuz_col ထဲသို့ ပြောင်းလဲ သိမ်းဆည်းမည်
        await marcuz_col.update_one(
            {"key": "string_session"},
            {"$set": {"value": session_str}},
            upsert=True
        )
        await event.reply("✅ String Session ကို `marcuz_col` ထဲမှာ အောင်မြင်စွာ သိမ်းပြီးပါပြီ။ Userbot ချိတ်ဆက်နေသည်...")
        
        try:
            if userbot:
                await userbot.disconnect()
            userbot = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
            await userbot.start()
            await userbot.get_dialogs()
            
            # Register Handlers
            userbot.add_event_handler(spawn_detector_handler, events.NewMessage())
            userbot.add_event_handler(hint_solver_handler, events.NewMessage())
            userbot.add_event_handler(catch_success_forwarder_handler, events.NewMessage())
            userbot.add_event_handler(captcha_alert_handler, events.NewMessage()) 
            
            await event.reply("🚀 Userbot is Live with Manual Sniper Mod! မော်ဂန့်တပည့် မားကတ်ကတ်စကောက်ပါပီ")
        except Exception as e:
            await event.reply(f"❌ Userbot အလုပ်မလုပ်ပါ: {e}")

    # 🛑 /catch စနစ်အား ကိုယ်တိုင်ပိတ်မည့် Command
    elif cmd == "/stop":
        is_catch_stopped = True
        await event.reply("🛑 **Chief! `/catch` လုပ်ငန်းစဉ်ကို ရပ်ဆိုင်းလိုက်ပါပြီ။**\n(Detector နှင့် Forward စနစ်များတော့ ပုံမှန်အတိုင်း အလုပ်လုပ်ပေးနေပါမည်)")

    # ✅ /catch စနစ်အား ပြန်လည်စတင်မည့် Command
    elif cmd == "/start":
        is_catch_stopped = False
        await event.reply("✅ **Chief! `/catch` လုပ်ငန်းစဉ်ကို ပြန်လည်စတင်လိုက်ပါပြီ။**")
        # 🎯 [NEW] OWNER COPY ON/OFF COMMANDS (NO SLASH, NO DOT)
    elif cmd == "copyon":
        is_copy_active = True
        await event.reply("🎯 **Copy Mode: [ON]**\nယခုအချိန်မှစ၍ Matrix Group တွင် Chief ပြောသမျှကို Userbot များအားလုံး လိုက်အော်ပါမည်။")
        return

    elif cmd == "copyoff":
        is_copy_active = False
        await event.reply("🔇 **Copy Mode: [OFF]**\nUserbot များ လိုက်ပြောခြင်းကို ပိတ်လိုက်ပါပြီ။")
        return

    # 🗣️ [⚡ FIXED] OWNER MIMIC LOGIC (ပိုမိုစိတ်ချရသော ပုံစံသို့ ပြောင်းလဲထားသည်)
    if is_copy_active and cmd not in ["copyon", "copyoff"] and not cmd.startswith("$"):
        all_bots = []
        if userbot:
            all_bots.append(userbot)
        all_bots.extend(powerranger_clients)
        
        for client in all_bots:
            try:
                # MATRIX_GROUP_ID အစား လက်ရှိ Group ID (event.chat_id) သို့ တိုက်ရိုက်ပို့ခိုင်းခြင်း
                await client.send_message(event.chat_id, event.message.text)
                await asyncio.sleep(0.2) 
            except Exception as ce:
                print(f"❌ Copy Mode Error from a Userbot: {ce}")


    # ==========================================
    # ⚙️ [NEW] POWER RANGER COMMAND HANDLERS
    # ==========================================
    
    # ➕ Power Ranger Userbot အသစ်များကို အကန့်အသတ်မရှိ ထည့်သွင်းရန် command
    elif cmd.startswith("/addpr") or cmd.startswith("/pr"):
        args = cmd.split(maxsplit=1)
        session_str = None
        
        if len(args) > 1:
            session_str = args[1].strip()
        elif event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg and reply_msg.text:
                session_str = reply_msg.text.strip()
                
        if not session_str:
            await event.reply("❌ **Power Ranger အတွက် String Session မတွေ့ရှိပါ။**\nအသုံးပြုပုံစံ - `/addpr [session]` သို့မဟုတ် String Session စာသားကို Reply ထောက်၍ ပို့ပါ။")
            return
            
        # DB ထဲတွင် Duplicate ဖြစ်ခြင်းမှ ကာကွယ်ရန် စစ်ဆေးပြီး သိမ်းဆည်းခြင်း
        exists = await powerranger_col.find_one({"session": session_str})
        if not exists:
            await powerranger_col.insert_one({"session": session_str})
            
        await event.reply("⚙️ String Session ကို `powerranger_col` ထဲသို့ ဖြည့်သွင်းပြီးပါပြီ။ Client အား ချိတ်ဆက်နေသည်...")
        
        try:
            pr_client = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
            await pr_client.start()
            
            # Global List ထဲသို့ ထည့်ပြီး Loop စတင်ခြင်း
            powerranger_clients.append(pr_client)
             
            await event.reply(f"🚀 Power Ranger Bot #{len(powerranger_clients)} အောင်မြင်စွာ စတင်လိုက်ပါပြီ။ Matrix အဖွဲ့ဝင်အသစ် တိုးလာပါပြီ။")
        except Exception as e:
            await event.reply(f"❌ Power Ranger Bot ချိတ်ဆက်မှု ပျက်ကွက်ပါသည်- {e}")

    # 🗣️ Matrix Group တွင် စကားပြောခြင်း စတင်ရန် Command
    elif cmd == "/talkon":
        is_powerranger_talking = True
        await event.reply("🗣️ **Power Rangers များ Matrix Group တွင် Random စကားပြောခြင်း လုပ်ငန်းစဉ် စတင်ပါပြီ။**")

    # 🤐 စကားပြောခြင်း ရပ်တန့်ရန် Command
    elif cmd == "/talkoff":
        is_powerranger_talking = False
        await event.reply("🤐 **Power Rangers များ စကားပြောခြင်းကို ခေတ္တရပ်ဆိုင်းလိုက်ပါပြီ။**")

    # ⚡ အမြန်နှုန်း အရှိန်ချိန်ညှိရန် Command
    elif cmd.startswith("/spd"):
        args = cmd.split()
        if len(args) > 1 and args[1] in ["1", "2", "3"]:
            powerranger_speed = int(args[1])
            speed_labels = {1: "နှေး (Slow ~6s)", 2: "အလယ်အလတ် (Medium ~3s)", 3: "အမြန် (Fast ~2.5s)"}
            await event.reply(f"⚡ **Power Ranger စကားပြောနှုန်း အရှိန်ကို အဆင့် {powerranger_speed} ({speed_labels[powerranger_speed]}) သို့ ပြောင်းလဲသတ်မှတ်လိုက်ပါပြီ။**")
        else:
            await event.reply("❌ **အသုံးပြုပုံစံ မှားယွင်းနေပါသည်။**\n`/spd 1` (နှေး), `/spd 2` (ပုံမှန်) သို့မဟုတ် `/spd 3` (မြန်) ဟု ရွေးချယ်ပေးပါ။")
 
# ==========================================
# 🚀 SYSTEM STARTUP LOGIC
# ==========================================
async def startup():
    global is_active, userbot, powerranger_clients
    print("⏳ System starting up and loading configurations from MongoDB...")
    
    asyncio.create_task(start_dummy_web_server())
    asyncio.create_task(start_global_talk_loop())
    try:
        deleted = await reply_save_col.delete_many({"$expr": {"$lt": [{"$strLenCP": "$trigger"}, 3]}})
        if deleted.deleted_count > 0:
            print(f"🧹 Cleaned up {deleted.deleted_count} short garbage triggers from DB.")
    except Exception as clean_err:
        print(f"⚠️ DB Cleanup Warning: {clean_err}")

    status_doc = await marcuz_col.find_one({"key": "bot_status"})
    if status_doc and status_doc.get("value") == "active":
        is_active = True
        print("➡️ Auto-Reply Status: ACTIVE")

    # Startup မှာလည်း marcuz_col ထဲက string_session ကို ဆွဲထုတ်ပြီး အလုပ်လုပ်ခိုင်းခြင်း
    session_doc = await marcuz_col.find_one({"key": "string_session"})
    if session_doc:
        try:
            session_str = session_doc.get("value")
            userbot = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
            await userbot.start()
            await userbot.get_dialogs()
            
            userbot.add_event_handler(spawn_detector_handler, events.NewMessage())
            userbot.add_event_handler(hint_solver_handler, events.NewMessage())
            userbot.add_event_handler(catch_success_forwarder_handler, events.NewMessage())
            userbot.add_event_handler(captcha_alert_handler, events.NewMessage()) 
            
            print("🚀 Userbot Session Successfully Loaded from marcuz_col!")
        except Exception as e:
            print(f"⚠️ Failed to load existing Userbot Session: {e}")
    else:
        print("💡 No String Session found in marcuz_col yet.")

    # 🔄 [NEW] Startup တက်လာချိန်တွင် powerranger_col ထဲရှိ အကောင့်အားလုံးကို ဆွဲထုတ်ပြီး Auto Connect လုပ်ခြင်း
    print("⏳ Loading Power Ranger accounts from database...")
    async for pr_doc in powerranger_col.find():
        pr_session = pr_doc.get("session")
        if pr_session:
            try:
                pr_client = TelegramClient(StringSession(pr_session), APP_ID, APP_HASH)
                await pr_client.start()
                powerranger_clients.append(pr_client)
                # 💡 start_powerranger_talk_loop လိုင်းဟောင်းကို ဖျက်ပစ်လိုက်ပြီဖြစ်၍ စနစ်မအိုင်တော့ပါ
            except Exception as pr_err:
                print(f"⚠️ Failed to connect a Power Ranger account from DB: {pr_err}")

    print(f"🚀 Loaded {len(powerranger_clients)} Power Ranger Bot(s) completely!")

    await bot.start(bot_token=BOT_TOKEN)
    print("🤖 Official Bot is running...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(startup())
    
