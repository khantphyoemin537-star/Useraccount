import os
import asyncio
import random
import time
import logging
import re
import unicodedata
from telethon import TelegramClient, events, errors, functions
from telethon.sessions import StringSession
from motor.motor_asyncio import AsyncIOMotorClient
from telethon.tl.types import UserStatusEmpty, UserStatusOffline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.errors import FloodWaitError
# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
MONGO_URI = "mongodb+srv://khantphyoemin537_db_user:9VRKiaeZkz7rJdpz@cluster0.w6tgi8j.mongodb.net/telegram_bot?appName=Cluster0&tlsAllowInvalidCertificates=true"
APP_ID = 39584681
APP_HASH = 'c8c0685d6dd5b9e546093ea90d27733b'
BOT_TOKEN = '8738081667:AAHADgcDISntnOBwT3uj2yYw7n3XJUN2uZI'

OWNER_ID = 6015356597
ADMIN_ID = 6015356597
MATRIX_GROUP_ID = None
COOLDOWN_TIME = 15

# Global States
is_active = False
is_scraping = False
is_adding_contacts = False
user_cooldowns = {}
is_talker_active = False
message_count = 0
spam_tasks = {}
is_copy_active = False
is_powerranger_talking = False
powerranger_speed = 2
powerranger_clients = []
bot_last_send = {}

# New globals for Group Management
target_group_id = None          # /go နဲ့ သတ်မှတ်ထားတဲ့ Group ID
bad_users = []                  # /check မှ စုစည်းထားတဲ့ User ID စာရင်း
check_in_progress = False       # /check လုပ်နေစဉ် ပြန်မခေါ်ရအောင်

# MongoDB Setup
client_mongo = AsyncIOMotorClient(MONGO_URI)
db = client_mongo["telegram_bot"]
reply_save_col = db["reply_save_col"]
target_bots_col = db["target_bots"]
tomboy_col = db["tomboy_col"]
marcuz_col = db["marcuz_col"]
powerranger_col = db["powerranger_col"]
talk_col = db["random_talk"]
filters_col = db["filters"]

# Initialize Clients
bot = TelegramClient('official_bot_session', APP_ID, APP_HASH)
userbot = None

# ==========================================
# 🌍 DUMMY HTTP SERVER
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
# 🗑️ DELETION HELPERS
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
# 🗣️ GLOBAL TALK LOOP
# ==========================================
async def start_global_talk_loop():
    global is_powerranger_talking, powerranger_speed, powerranger_clients, userbot, bot_last_send

    speed_interval = {
        1: 3.0,
        2: 1.5,
        3: 0.8
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
                    min_interval = speed_interval.get(powerranger_speed, 1.0)

                    available = [
                        b for b in all_bots
                        if now - bot_last_send.get(b, 0) >= min_interval
                    ]

                    if available:
                        current_bot = random.choice(available)

                        pipeline = [{"$sample": {"size": 1}}]
                        cursor = talk_col.aggregate(pipeline)
                        docs = await cursor.to_list(length=1)
                        if docs:
                            reply_text = docs[0].get("text") or docs[0].get("word") or docs[0].get("message")
                            if reply_text:
                                try:
                                    await current_bot.send_message(MATRIX_GROUP_ID, reply_text)
                                    bot_last_send[current_bot] = time.time()
                                except errors.rpcerrorlist.FloodWaitError as e:
                                    print(f"⚠️ FloodWait {e.seconds}s for this bot only. Cooling this bot down, others keep talking...")
                                    bot_last_send[current_bot] = time.time() + e.seconds
                                except Exception as ce:
                                    print(f"❌ Send error: {ce}")

                        await asyncio.sleep(random.uniform(0.3, 0.5))
                    else:
                        await asyncio.sleep(0.3)
            else:
                await asyncio.sleep(0.5)

        except Exception as e:
            print(f"❌ Global Talk Loop Error: {e}")
            await asyncio.sleep(3.0)

# ==========================================
# 🤖 OFFICIAL BOT COMMAND HANDLERS
# ==========================================
@bot.on(events.NewMessage)
async def handle_bot_commands(event):
    global is_active, userbot, is_scraping, is_talker_active, is_copy_active
    global is_powerranger_talking, powerranger_speed, powerranger_clients
    global target_group_id, bad_users, check_in_progress

    # Owner သာလျှင် command များကို လုပ်ဆောင်ခွင့်ရှိမည်
    if event.sender_id != OWNER_ID:
        return

    cmd = event.message.text.strip() if event.message.text else ""

    # ======== EXISTING COMMANDS ========
    # 🎯 copyon / copyoff
    if cmd == "copyon":
        is_copy_active = True
        await event.reply("🎯 **Copy Mode: [ON]**\nယခုအချိန်မှစ၍ Matrix Group တွင် Chief ပြောသမျှကို Userbot များအားလုံး လိုက်အော်ပါမည်။")
        return
    elif cmd == "copyoff":
        is_copy_active = False
        await event.reply("🔇 **Copy Mode: [OFF]**\nUserbot များ လိုက်ပြောခြင်းကို ပိတ်လိုက်ပါပြီ။")
        return

    # 🗣️ Copy Mode Logic
    if is_copy_active and cmd not in ["copyon", "copyoff"] and not cmd.startswith("$"):
        all_bots = []
        if userbot:
            all_bots.append(userbot)
        all_bots.extend(powerranger_clients)
        for client in all_bots:
            try:
                await client.send_message(event.chat_id, event.message.text)
                await asyncio.sleep(0.2)
            except Exception as ce:
                print(f"❌ Copy Mode Error from a Userbot: {ce}")

    # ➕ /addpr
    if cmd.startswith("/addpr") or cmd.startswith("/pr"):
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

        exists = await powerranger_col.find_one({"session": session_str})
        if not exists:
            await powerranger_col.insert_one({"session": session_str})

        await event.reply("⚙️ String Session ကို `powerranger_col` ထဲသို့ ဖြည့်သွင်းပြီးပါပြီ။ Client အား ချိတ်ဆက်နေသည်...")
        try:
            pr_client = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
            await pr_client.start()
            powerranger_clients.append(pr_client)
            bot_last_send[pr_client] = time.time() + random.uniform(0, 2.0)
            await event.reply(f"🚀 Power Ranger Bot #{len(powerranger_clients)} အောင်မြင်စွာ စတင်လိုက်ပါပြီ။ Matrix အဖွဲ့ဝင်အသစ် တိုးလာပါပြီ။")
        except Exception as e:
            await event.reply(f"❌ Power Ranger Bot ချိတ်ဆက်မှု ပျက်ကွက်ပါသည်- {e}")
        return

    # 🗣️ /talkon
    if cmd == "/talkon":
        is_powerranger_talking = True
        all_bots = []
        if userbot:
            all_bots.append(userbot)
        all_bots.extend(powerranger_clients)
        now = time.time()
        for b in all_bots:
            bot_last_send[b] = now + random.uniform(0.1, 0.5)
        await event.reply("🗣️ **Power Rangers များ Matrix Group တွင် Random စကားပြောခြင်း လုပ်ငန်းစဉ် စတင်ပါပြီ။**")
        return

    # 🤐 /talkoff
    if cmd == "/talkoff":
        is_powerranger_talking = False
        await event.reply("🤐 **Power Rangers များ စကားပြောခြင်းကို ခေတ္တရပ်ဆိုင်းလိုက်ပါပြီ။**")
        return

    # ⚡ /spd
    if cmd.startswith("/spd"):
        args = cmd.split()
        if len(args) > 1 and args[1] in ["1", "2", "3"]:
            powerranger_speed = int(args[1])
            speed_labels = {1: "နှေး (Slow ~3s)", 2: "အလယ်အလတ် (Medium ~1.5s)", 3: "အမြန် (Fast ~0.8s)"}
            await event.reply(f"⚡ **Power Ranger စကားပြောနှုန်း အရှိန်ကို အဆင့် {powerranger_speed} ({speed_labels[powerranger_speed]}) သို့ ပြောင်းလဲသတ်မှတ်လိုက်ပါပြီ။**")
        else:
            await event.reply("❌ **အသုံးပြုပုံစံ မှားယွင်းနေပါသည်။**\n`/spd 1` (နှေး), `/spd 2` (ပုံမှန်) သို့မဟုတ် `/spd 3` (မြန်) ဟု ရွေးချယ်ပေးပါ။")
        return

    # ======== NEW COMMANDS FOR GROUP MANAGEMENT ========

    # 🚪 /go – Group ဝင်ရန် (ပြင်ဆင်ထားသော ဗားရှင်း)
    if cmd == "/go":
        if not event.is_reply:
            await event.reply("❌ `/go` ကို Group invite link ပါတဲ့ message ကို reply လုပ်ပြီး သုံးပေးပါ။")
            return
        reply_msg = await event.get_reply_message()
        if not reply_msg.text:
            await event.reply("❌ Reply လုပ်ထားတဲ့ message မှာ link မပါပါ။")
            return

        # Link ကို extract လုပ် (joinchat/ နဲ့ + နှစ်မျိုးလုံး ဖမ်းမယ်)
        link_match = re.search(r'(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)', reply_msg.text)
        if not link_match:
            await event.reply("❌ တရားဝင် Telegram Group invite link မတွေ့ပါ။")
            return
        invite_link = link_match.group(0)

        # hash ကို ထုတ်ယူမယ်
        if 'joinchat/' in invite_link:
            hash_part = invite_link.split('joinchat/')[1].split('?')[0]
        elif '+' in invite_link:
            hash_part = invite_link.split('+')[1].split('?')[0]
        else:
            hash_part = None

        if not hash_part:
            await event.reply("❌ Link မှ hash ကို ထုတ်ယူမရပါ။")
            return

        # Power Ranger နဲ့ Userbot အားလုံးကို စုစည်း
        all_clients = []
        if userbot:
            all_clients.append(userbot)
        all_clients.extend(powerranger_clients)

        if not all_clients:
            await event.reply("❌ ဝင်ရန် အကောင့်မရှိပါ။ `/addpr` နဲ့ session ထည့်ပါ။")
            return

        await event.reply(f"⏳ Group ထဲ ဝင်နေပါပြီ… (Clients {len(all_clients)})")

        success_count = 0
        first_error = None

        for client in all_clients:
            try:
                # ImportChatInviteRequest ကို hash နဲ့ သုံးပါ
                await client(ImportChatInviteRequest(hash_part))
                success_count += 1
            except AlreadyParticipantError:
                # သွင်းပြီးသား အကောင့်ဖြစ်နေရင် အောင်မြင်ပြီးသား သတ်မှတ်
                success_count += 1
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
                # ပြန်ကြိုးစားမယ်
                try:
                    await client(ImportChatInviteRequest(hash_part))
                    success_count += 1
                except Exception as e2:
                    if first_error is None:
                        first_error = f"FloodWait ပြီးနောက် ပျက်ကွက်: {e2}"
            except Exception as e:
                if first_error is None:
                    first_error = str(e)
                print(f"Join error for {client}: {e}")

            await asyncio.sleep(0.3)  # flood ကာကွယ်

        if success_count == 0:
            error_msg = f"❌ ဘယ် client မှ မဝင်နိုင်ခဲ့ပါ။\n"
            if first_error:
                error_msg += f"ပထမဆုံး error: `{first_error}`"
            else:
                error_msg += "link မှားနိုင်သည် သို့မဟုတ် ပါဝင်ခွင့်မရှိပါ။"
            await event.reply(error_msg)
            return

        # Group ID ကို သိမ်းမယ် (ပထမဆုံး အောင်မြင်တဲ့ client က fetch)
        try:
            chat = await all_clients[0].get_entity(invite_link)
            target_group_id = chat.id
            await event.reply(f"✅ Group `{chat.title}` ထဲကို အကောင့် {success_count} ခု အောင်မြင်စွာ ဝင်ရောက်ပြီးပါပြီ။\nGroup ID: `{target_group_id}`")
        except Exception as e:
            # အထက်နည်းမရရင် dialog ထဲကရှာမယ်
            try:
                async for dialog in all_clients[0].iter_dialogs():
                    if dialog.is_group and dialog.name and (hash_part in str(dialog.id) or invite_link in str(dialog.id)):
                        target_group_id = dialog.id
                        await event.reply(f"✅ Group `{dialog.name}` ထဲကို အကောင့် {success_count} ခု အောင်မြင်စွာ ဝင်ရောက်ပြီးပါပြီ။\nGroup ID: `{target_group_id}`")
                        break
                else:
                    await event.reply(f"⚠️ Group ဝင်ပြီးသော်လည်း ID ရယူရာတွင် အမှားရှိသည်: {e}")
            except Exception as e2:
                await event.reply(f"⚠️ Group ID ရယူရန် မအောင်မြင်ပါ: {e2}")
        return

    # 🔍 /check – Member စစ်ဆေးခြင်း
    if cmd == "/check":
        if target_group_id is None:
            await event.reply("❌ ဦးစွာ `/go` နဲ့ Group ဝင်ပါ။")
            return
        if check_in_progress:
            await event.reply("⏳ လက်ရှိ check လုပ်နေဆဲဖြစ်သည်။ ပြီးမှ ထပ်ခေါ်ပါ။")
            return

        check_in_progress = True
        await event.reply("🔍 Group ထဲက Member အားလုံးကို စတင်စစ်ဆေးနေပါပြီ… (ကြာနိုင်ပါသည်)")

        # Admin ရှိသည့် client ကို ရွေးမယ်
        client_to_use = None
        all_clients = [userbot] + powerranger_clients if userbot else powerranger_clients
        for cl in all_clients:
            if cl is None:
                continue
            try:
                # Admin ဟုတ်မဟုတ် စမ်းကြည့် (participants ရယူနိုင်ရင် admin ဖြစ်နိုင်တယ်)
                await cl.get_participants(target_group_id, limit=1)
                client_to_use = cl
                break
            except Exception:
                continue

        if client_to_use is None:
            await event.reply("❌ ဘယ် client မှ admin မဟုတ်ပါ (သို့) Group ထဲမရှိပါ။")
            check_in_progress = False
            return

        bad_users = []
        total_members = 0
        try:
            async for participant in client_to_use.iter_participants(target_group_id):
                total_members += 1
                user = participant.user if hasattr(participant, 'user') else participant
                if user.deleted:
                    bad_users.append((user.id, user.first_name or "Deleted", "Deleted Account"))
                    continue
                # status ကို စစ်ဆေး
                status = getattr(user, 'status', None)
                if status is None:
                    continue
                # ၆ လကျော် inactive စစ်
                if isinstance(status, UserStatusOffline):
                    if status.was_online:
                        six_months_ago = time.time() - (6 * 30 * 24 * 3600)
                        if status.was_online.timestamp() < six_months_ago:
                            bad_users.append((user.id, user.first_name or "No Name", "Offline >6 months"))
                elif isinstance(status, UserStatusEmpty):
                    bad_users.append((user.id, user.first_name or "No Name", "Never seen"))
                # UserStatusRecently, LastWeek, LastMonth တွေက ၆ လထက် မကြာသေးဘူးလို့ ယူဆ
        except FloodWaitError as e:
            await event.reply(f"⏳ Flood wait {e.seconds} seconds ကြာမည်။ နောက်မှ ထပ်ကြည့်ပါ။")
            check_in_progress = False
            return
        except Exception as e:
            await event.reply(f"❌ Check လုပ်ရာတွင် အမှားရှိသည်: {e}")
            check_in_progress = False
            return

        check_in_progress = False

        # ရလဒ်ကို ပြပေးမယ်
        if bad_users:
            msg = f"📊 **စစ်ဆေးမှု ရလဒ်**\n\nအုပ်စုထဲရှိ စုစုပေါင်း Member: {total_members}\n"
            msg += f"**Deleted Account + Inactive (>6 months) စုစုပေါင်း: {len(bad_users)}**\n\n"
            # နာမည်စာရင်းကို အုပ်စုလိုက်ဖော်ပြမယ် (အကျဉ်းချုပ်)
            for uid, name, reason in bad_users[:50]:  # 50 ခုပဲ ပြမယ်
                msg += f"• {name} (ID: {uid}) – {reason}\n"
            if len(bad_users) > 50:
                msg += f"\n...နှင့် နောက်ထပ် {len(bad_users)-50} ဦး"
            await event.reply(msg)
            # စာရင်းကို file အနေနဲ့လည်း ပို့ပေးမယ်
            with open("bad_users.txt", "w", encoding="utf-8") as f:
                for uid, name, reason in bad_users:
                    f.write(f"{uid},{name},{reason}\n")
            await event.reply("📄 အပြည့်အစုံစာရင်းကို `bad_users.txt` ဖိုင်အနေနဲ့ တင်ပေးလိုက်ပါပြီ။")
            # global variable မှာ သိမ်းထားမယ်
            globals()['bad_users'] = bad_users
        else:
            await event.reply("✅ ဖယ်ရှားရန် လိုအပ်သည့် Account တစ်ခုမှ မတွေ့ပါ။")
        return

    # 🗑️ /remove – နှင်ထုတ်ခြင်း
    if cmd == "/remove":
        if target_group_id is None:
            await event.reply("❌ ဦးစွာ Group ဝင်ပါ (`/go`).")
            return
        if not bad_users:
            await event.reply("❌ `/check` ကို ဦးစွာ လုပ်ပါ။ ဖယ်ရှားရန် စာရင်း မရှိပါ။")
            return

        await event.reply(f"⏳ လူ {len(bad_users)} ဦးကို စတင်နှင်ထုတ်နေပါပြီ…")

        # Admin ရှိသော client ကို ရွေး (check လုပ်ခဲ့တဲ့ client ကိုပဲ သုံးမယ်)
        client_to_use = None
        all_clients = [userbot] + powerranger_clients if userbot else powerranger_clients
        for cl in all_clients:
            if cl is None:
                continue
            try:
                await cl.get_participants(target_group_id, limit=1)
                client_to_use = cl
                break
            except Exception:
                continue

        if client_to_use is None:
            await event.reply("❌ Admin ရှိသော client မတွေ့ပါ။")
            return

        removed = 0
        total = len(bad_users)
        report_interval = 100

        for i, (uid, name, reason) in enumerate(bad_users, 1):
            try:
                await client_to_use.kick_participant(target_group_id, uid)
                removed += 1
                if removed % report_interval == 0:
                    await event.reply(f"✅ {removed} ဦး နှင်ထုတ်ပြီးပါပြီ။ (လက်ကျန် {total-removed})")
                await asyncio.sleep(0.3)  # flood ကာကွယ်
            except FloodWaitError as e:
                await event.reply(f"⏳ Flood wait {e.seconds}s ကြာမည်။ စောင့်နေပါ…")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                print(f"Kick error for {uid}: {e}")

        await event.reply(f"✅ **ဖယ်ရှားခြင်း ပြီးဆုံးပါပြီ။**\nစုစုပေါင်း နှင်ထုတ်ခဲ့သူ {removed} ဦး။")

        # ထုတ်ပြီးသား စာရင်းကို ရှင်းမယ်
        bad_users = []
        return

# ==========================================
# 🚀 SYSTEM STARTUP
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

    # Load main userbot session
    session_doc = await marcuz_col.find_one({"key": "string_session"})
    if session_doc:
        try:
            session_str = session_doc.get("value")
            userbot = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
            await userbot.start()
            await userbot.get_dialogs()
            print("🚀 Userbot Session Successfully Loaded from marcuz_col!")
        except Exception as e:
            print(f"⚠️ Failed to load existing Userbot Session: {e}")
    else:
        print("💡 No String Session found in marcuz_col yet.")

    # Load Power Rangers from DB
    print("⏳ Loading Power Ranger accounts from database...")
    async for pr_doc in powerranger_col.find():
        pr_session = pr_doc.get("session")
        if pr_session:
            try:
                pr_client = TelegramClient(StringSession(pr_session), APP_ID, APP_HASH)
                await pr_client.start()
                powerranger_clients.append(pr_client)
                bot_last_send[pr_client] = time.time() + random.uniform(0, 2.0)
            except Exception as pr_err:
                print(f"⚠️ Failed to connect a Power Ranger account from DB: {pr_err}")

    print(f"🚀 Loaded {len(powerranger_clients)} Power Ranger Bot(s) completely!")

    await bot.start(bot_token=BOT_TOKEN)
    print("🤖 Official Bot is running...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(startup())
