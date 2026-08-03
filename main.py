import os
import asyncio
import random
import time
import logging
import re
import unicodedata
import difflib
from telethon import TelegramClient, events, errors, functions
from telethon.sessions import StringSession
from motor.motor_asyncio import AsyncIOMotorClient
from telethon.tl.types import (
    UserStatusEmpty, UserStatusOffline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth,
    MessageEntityMention, MessageEntityMentionName
)
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.errors.rpcerrorlist import FloodWaitError, AlreadyParticipantError
# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
MONGO_URI = "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true"
APP_ID = 39584681
APP_HASH = 'c8c0685d6dd5b9e546093ea90d27733b'
BOT_TOKEN = ''

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

# Globals for Rose-style keyword learning / auto-reply (replaces pure random talk)
reply_source = "userbot"        # "userbot" = userbot/Power Ranger pool ကနေ ပြန်ပြော | "apibot" = official bot ကနေ ပြန်ပြော
own_account_ids = set()         # userbot/Power Ranger/api bot ကိုယ်ပိုင် user id များ (learn/reply လုပ်ရာမှာ ကိုယ့်စာကို ကိုယ် မမှတ်၊ မတုံ့ပြန်စေရန်)
learn_last_trigger = {}         # key တစ်ခုချင်းအတွက် နောက်ဆုံး တုံ့ပြန်ခဲ့ချိန် (spam loop ကာကွယ်ရန်)
reply_cooldown = 8              # key တစ်ခုတည်းကို ဒီစက္ကန့်အတွင်း ထပ်မတုံ့ပြန်စေရန် (/spd နဲ့ ချိန်ညှိနိုင်သည်)

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
# 🗣️ GLOBAL TALK LOOP (legacy — kept alive as a no-op)
# ==========================================
async def start_global_talk_loop():
    """
    ယခင်က talk_col ထဲက စာသားများကို random အချိန်ကြားချပြီး ပို့နေခဲ့ပါတယ်။
    ယခုနောက်ပိုင်း Power Ranger စကားပြောခြင်းကို event-driven keyword
    learn/reply system (group_watcher_handler) က အစားထိုးလုပ်ဆောင်နေပါပြီ
    — chat ထဲက key/value learned pair တွေကို matching ဖြစ်မှသာ ပြန်ပြောပါမည်။
    ဒီ loop ကို function အနေနဲ့ ဆက်ထားရုံပါ (task crash မဖြစ်စေရန်), ဘာမှ ပို့တော့မည် မဟုတ်ပါ။
    """
    while True:
        await asyncio.sleep(5.0)

# ==========================================
# 🧠 KEYWORD LEARN & REPLY SYSTEM (Rose-bot-filter style)
# ==========================================
def normalize_text(text: str) -> str:
    """Key matching အတွက် စာသားကို standardize လုပ်သည် — case/space/punctuation ကွာခြားမှုကြောင့်
    တူညီတဲ့ key ကို မတူသလို မမှတ်အောင်။"""
    if not text:
        return ""
    text = unicodedata.normalize('NFKC', text)
    text = text.strip().lower()
    text = re.sub(r'\s+', ' ', text)
    # စာလုံး/ဂဏန်း/မြန်မာစာနှင့် space များသာ ချန်ထား၊ punctuation ဖယ်
    text = re.sub(r'[^\w\s\u1000-\u109F]', '', text, flags=re.UNICODE)
    return text.strip()


def message_has_mention(message) -> bool:
    """HTML mention entity, @username mention ပါတဲ့ message ကို learn/reply ထဲ မထည့်ရန်။"""
    if not message:
        return False
    entities = getattr(message, 'entities', None)
    if entities:
        for ent in entities:
            if isinstance(ent, (MessageEntityMention, MessageEntityMentionName)):
                return True
    text = getattr(message, 'text', None) or getattr(message, 'raw_text', None)
    if text and re.search(r'@\w+', text):
        return True
    return False


async def save_learned_pair(key_text: str, value_text: str) -> None:
    """Chat ထဲက (original message -> ၎င်းကို reply လုပ်ထားတဲ့ message) စုံတွဲကို key/value အဖြစ် သိမ်းသည်။
    key တစ်ခုအတွက် value အများအပြား ဖြစ်နိုင်တာမို့ list ထဲ ထပ်ထည့်သွားမည် (တူညီသော value ထပ်မထည့်)။"""
    norm_key = normalize_text(key_text)
    if not norm_key or len(norm_key) < 2:
        return
    try:
        await filters_col.update_one(
            {"key": norm_key},
            {
                "$addToSet": {"responses": value_text},
                "$setOnInsert": {"original": key_text},
            },
            upsert=True,
        )
    except Exception as e:
        print(f"❌ Learn save error: {e}")


async def find_best_filter_match(text: str):
    """text ကို DB ထဲက learned key တွေနဲ့ တိုက်စစ်သည်။ တိတိကျကျ တူရင် အရင်ရှာ၊
    မတူလျှင် fuzzy (0.82 cutoff) သုံးပြီး အနီးစပ်ဆုံး key ကို ရှာသည် — key တိတိကျကျ
    ကြီးမှသာ value ပြန်တာမျိုး မဖြစ်စေရန်၊ ဒါပေမယ့် လုံးဝမဆိုင်တာကို မတိုက်စေရန် ဟန်ချက်ညီစေသည်။"""
    norm_text = normalize_text(text)
    if not norm_text:
        return None

    doc = await filters_col.find_one({"key": norm_text})
    if doc and doc.get("responses"):
        return doc

    try:
        cursor = filters_col.find({}, {"key": 1, "responses": 1}).limit(5000)
        keys_map = {}
        async for d in cursor:
            if d.get("key") and d.get("responses"):
                keys_map[d["key"]] = d
        if not keys_map:
            return None
        close = difflib.get_close_matches(norm_text, keys_map.keys(), n=1, cutoff=0.82)
        if close:
            return keys_map[close[0]]
    except Exception as e:
        print(f"❌ Filter match error: {e}")
    return None


def get_primary_watcher():
    """Chat ကို 'ကြည့်နေ' မည့် client တစ်ခုတည်း ရွေးသည် — userbot ရှိလျှင် userbot,
    မရှိလျှင် Power Ranger ပထမဆုံးတစ်ယောက်။ Client တွေအားလုံးမှာ handler ကို attach
    ထားပေမယ့် ဒီ client တစ်ခုတည်းကသာ တကယ် process လုပ်မည် (duplicate ဖြေရှင်းရန်)။"""
    if userbot:
        return userbot
    if powerranger_clients:
        return powerranger_clients[0]
    return None


async def pick_reply_client():
    """reply_source setting အလိုက် message ကို ဘယ် client က ပို့မလဲ ရွေးသည်။"""
    global reply_source
    if reply_source == "apibot":
        return bot
    candidates = []
    if userbot:
        candidates.append(userbot)
    candidates.extend(powerranger_clients)
    if not candidates:
        return None
    return random.choice(candidates)


def attach_group_watcher(client) -> None:
    """Client (userbot/Power Ranger) တစ်ခုအပေါ် group watcher handler ကို attach လုပ်သည်။
    Client အသစ်ရလာတိုင်း (startup, /addpr) ဒီ function ကို ခေါ်ပါ။"""
    client.add_event_handler(group_watcher_handler, events.NewMessage())


async def group_watcher_handler(event) -> None:
    """Matrix Group ထဲက message များကို စောင့်ကြည့်ပြီး:
    1) reply chain (key->value) များကို learn လုပ်သည်
    2) known key နဲ့ တိုက်ဆိုင်ရင် userbot/api bot ကနေ value ကို ပြန်ပြောသည်
    is_powerranger_talking (talkon/talkoff) က ဒီ feature ကို ဖွင့်/ပိတ် ထိန်းချုပ်သည်။"""
    global is_powerranger_talking, MATRIX_GROUP_ID, learn_last_trigger, reply_cooldown

    # Client အများနဲ့ group ထဲ ဝင်ထားနိုင်သော်လည်း ဒီ event ကို primary watcher တစ်ခုတည်းသာ process လုပ်မည်
    if event.client is not get_primary_watcher():
        return

    if not is_powerranger_talking:
        return
    if MATRIX_GROUP_ID is None or event.chat_id != MATRIX_GROUP_ID:
        return

    message = event.message
    if not message or not message.text:
        return
    if event.sender_id in own_account_ids:
        return
    if message_has_mention(message):
        return

    text = message.text.strip()
    if not text or text.startswith('/'):
        return

    try:
        # 1) reply chain ကနေ key/value learn
        if event.is_reply:
            try:
                reply_to = await event.get_reply_message()
            except Exception:
                reply_to = None
            if (
                reply_to and reply_to.text
                and reply_to.sender_id not in own_account_ids
                and not message_has_mention(reply_to)
            ):
                key_text = reply_to.text.strip()
                value_text = text
                if key_text and value_text and normalize_text(key_text) != normalize_text(value_text):
                    await save_learned_pair(key_text, value_text)

        # 2) key တိုက်ဆိုင်ရင် value ကို ပြန်ပြော
        match = await find_best_filter_match(text)
        if match:
            key = match["key"]
            now = time.time()
            if now - learn_last_trigger.get(key, 0) < reply_cooldown:
                return  # key တစ်ခုတည်းကို ခဏခဏ ထပ်မတုံ့ပြန်စေရန် (loop ကာကွယ်)
            learn_last_trigger[key] = now

            responses = match.get("responses") or []
            if not responses:
                return
            response_text = random.choice(responses)

            sender_client = await pick_reply_client()
            if sender_client is None:
                return
            try:
                await sender_client.send_message(MATRIX_GROUP_ID, response_text)
            except errors.rpcerrorlist.FloodWaitError as e:
                print(f"⚠️ FloodWait sending learned reply: {e.seconds}s")
            except Exception as e:
                print(f"❌ Learned reply send error: {e}")
    except Exception as e:
        print(f"❌ group_watcher_handler error: {e}")


# ==========================================
# 🤖 OFFICIAL BOT COMMAND HANDLERS
# ==========================================
@bot.on(events.NewMessage)
async def handle_bot_commands(event):
    global is_active, userbot, is_scraping, is_talker_active, is_copy_active
    global is_powerranger_talking, powerranger_speed, powerranger_clients
    global target_group_id, bad_users, check_in_progress, MATRIX_GROUP_ID, reply_source, reply_cooldown

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

    # 🔀 /replysource – learned key/value reply ကို ဘယ် client က ပြောမလဲ ရွေးရန်
    if cmd.startswith("/replysource") or cmd.startswith("/rs"):
        args = cmd.split(maxsplit=1)
        if len(args) < 2:
            await event.reply(
                f"🔀 **လက်ရှိ Reply Source:** `{reply_source}`\n"
                "အသုံးပြုပုံစံ: `/replysource userbot` (သို့) `/replysource apibot`"
            )
            return
        choice = args[1].strip().lower()
        if choice not in ("userbot", "apibot"):
            await event.reply("❌ `userbot` သို့မဟုတ် `apibot` ထဲက တစ်ခုကိုသာ ရွေးပါ။")
            return
        reply_source = choice
        await event.reply(f"✅ Reply Source ကို `{reply_source}` အဖြစ် ပြောင်းလိုက်ပါပြီ။")
        return

    # 📚 /learnstats – learn လုပ်ထားတဲ့ key/value အရေအတွက် ကြည့်ရန်
    if cmd == "/learnstats":
        try:
            total_keys = await filters_col.count_documents({})
            await event.reply(
                f"📚 **Learned Keywords:** {total_keys}\n"
                f"🔀 Reply Source: `{reply_source}`\n"
                f"🗣️ Talk/Learn Mode: {'🟢 ON' if is_powerranger_talking else '🔴 OFF'}"
            )
        except Exception as e:
            await event.reply(f"❌ Stats ရယူ၍ မရပါ- {e}")
        return

    # 🗑️ /forget – learn လုပ်ထားတဲ့ key တစ်ခုကို ဖျက်ရန် (reply လုပ်ပြီး /forget ရိုက်ပါ)
    if cmd == "/forget":
        if not event.is_reply:
            await event.reply("❌ ဖျက်ချင်တဲ့ key စာသားကို Reply ထောက်ပြီး `/forget` ရိုက်ပါ။")
            return
        reply_msg = await event.get_reply_message()
        if not reply_msg or not reply_msg.text:
            await event.reply("❌ Reply လုပ်ထားတဲ့ message မှာ စာသား မပါပါ။")
            return
        norm_key = normalize_text(reply_msg.text)
        result = await filters_col.delete_one({"key": norm_key})
        if result.deleted_count:
            await event.reply("🗑️ Key ကို DB ထဲက ဖျက်လိုက်ပါပြီ။")
        else:
            await event.reply("ℹ️ ဒီစာနဲ့ ကိုက်ညီတဲ့ learned key မတွေ့ပါ။")
        return

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
            try:
                me = await pr_client.get_me()
                own_account_ids.add(me.id)
            except Exception:
                pass
            attach_group_watcher(pr_client)
            await event.reply(f"🚀 Power Ranger Bot #{len(powerranger_clients)} အောင်မြင်စွာ စတင်လိုက်ပါပြီ။ Matrix အဖွဲ့ဝင်အသစ် တိုးလာပါပြီ။")
        except Exception as e:
            await event.reply(f"❌ Power Ranger Bot ချိတ်ဆက်မှု ပျက်ကွက်ပါသည်- {e}")
        return

    # 🗣️ /talkon
    if cmd == "/talkon":
        is_powerranger_talking = True
        await event.reply(
            "🗣️ **Power Rangers Keyword Learn/Reply System: [ON]**\n"
            "Matrix Group ထဲက reply chain တွေကနေ key/value learn လုပ်နေမည်၊ "
            "known keyword တွေ့ရင် userbot/api bot (setting: `/replysource`) ကနေ ပြန်ပြောပါမည်။"
        )
        return

    # 🤐 /talkoff
    if cmd == "/talkoff":
        is_powerranger_talking = False
        await event.reply("🤐 **Power Rangers Keyword Learn/Reply System: [OFF]**")
        return

    # ⚡ /spd – learned keyword reply ပြန်တုံ့ပြန်ချိန် (cooldown) ချိန်ညှိရန်
    if cmd.startswith("/spd"):
        args = cmd.split()
        if len(args) > 1 and args[1] in ["1", "2", "3"]:
            powerranger_speed = int(args[1])
            cooldown_map = {1: 15, 2: 8, 3: 3}
            reply_cooldown = cooldown_map[powerranger_speed]
            speed_labels = {1: f"နှေး ({reply_cooldown}s cooldown)", 2: f"အလယ်အလတ် ({reply_cooldown}s cooldown)", 3: f"အမြန် ({reply_cooldown}s cooldown)"}
            await event.reply(f"⚡ **Keyword Reply Cooldown ကို အဆင့် {powerranger_speed} ({speed_labels[powerranger_speed]}) သို့ ပြောင်းလဲသတ်မှတ်လိုက်ပါပြီ။**")
        else:
            await event.reply("❌ **အသုံးပြုပုံစံ မှားယွင်းနေပါသည်။**\n`/spd 1` (နှေး/cooldown ကြာ), `/spd 2` (ပုံမှန်) သို့မဟုတ် `/spd 3` (မြန်/cooldown တို) ဟု ရွေးချယ်ပေးပါ။")
        return

    # 📍 /setmatrix – Matrix Group ID သတ်မှတ်ရန် (talkon/copyon အလုပ်လုပ်ဖို့ လိုအပ်သည်)
    if cmd.startswith("/setmatrix"):
        args = cmd.split(maxsplit=1)
        if len(args) < 2:
            current = f"`{MATRIX_GROUP_ID}`" if MATRIX_GROUP_ID else "❌ **မသတ်မှတ်ရသေးပါ**"
            await event.reply(
                "❌ **အသုံးပြုပုံစံ:** `/setmatrix <group_id သို့မဟုတ် @username>`\n"
                f"လက်ရှိ Matrix Group ID: {current}"
            )
            return

        target = args[1].strip()
        resolver = userbot or (powerranger_clients[0] if powerranger_clients else None)
        if resolver is None:
            await event.reply("❌ Group ကို ဖြေရှင်းပေးနိုင်မည့် userbot/Power Ranger client တစ်ခုမှ မရှိပါ။ `/addpr` နဲ့ account အရင်ထည့်ပါ။")
            return

        try:
            entity_ref = int(target) if target.lstrip('-').isdigit() else target
            entity = await resolver.get_entity(entity_ref)
            MATRIX_GROUP_ID = entity.id
            await marcuz_col.update_one(
                {"key": "matrix_group_id"},
                {"$set": {"value": MATRIX_GROUP_ID}},
                upsert=True
            )
            title = getattr(entity, 'title', None) or getattr(entity, 'username', None) or str(MATRIX_GROUP_ID)
            await event.reply(f"✅ **Matrix Group** ကို `{title}` (ID: `{MATRIX_GROUP_ID}`) အဖြစ် သတ်မှတ်ပြီး DB ထဲ သိမ်းလိုက်ပါပြီ။")
        except Exception as e:
            await event.reply(f"❌ Group ID/username ကို ဖြေရှင်း၍ မရပါ- {e}")
        return

    # 📊 /status – Live connection/state စစ်ဆေးရန်
    if cmd == "/status":
        userbot_status = "✅ Connected" if userbot else "❌ Not connected (dead session or not loaded)"
        matrix_status = f"`{MATRIX_GROUP_ID}`" if MATRIX_GROUP_ID else "❌ **မသတ်မှတ်ရသေးပါ** — `/setmatrix` သုံးပါ"
        target_status = f"`{target_group_id}`" if target_group_id else "မသတ်မှတ်ရသေးပါ"
        msg = (
            "📊 **System Status**\n\n"
            f"🤖 Userbot: {userbot_status}\n"
            f"🦸 Power Rangers: {len(powerranger_clients)} connected\n"
            f"🗣️ Talk/Learn Mode: {'🟢 ON' if is_powerranger_talking else '🔴 OFF'}\n"
            f"🔀 Reply Source: `{reply_source}`\n"
            f"🎯 Copy Mode: {'🟢 ON' if is_copy_active else '🔴 OFF'}\n"
            f"📍 Matrix Group ID: {matrix_status}\n"
            f"🚪 /go Target Group ID: {target_status}"
        )
        await event.reply(msg)
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
    global is_active, userbot, powerranger_clients, MATRIX_GROUP_ID
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

    matrix_doc = await marcuz_col.find_one({"key": "matrix_group_id"})
    if matrix_doc:
        MATRIX_GROUP_ID = matrix_doc.get("value")
        print(f"📍 Matrix Group ID Loaded: {MATRIX_GROUP_ID}")
    else:
        print("⚠️ Matrix Group ID not set yet — /talkon will not be able to send messages until you run /setmatrix.")

    # Load main userbot session
    session_doc = await marcuz_col.find_one({"key": "string_session"})
    if session_doc:
        try:
            session_str = session_doc.get("value")
            temp_userbot = TelegramClient(StringSession(session_str), APP_ID, APP_HASH)
            await temp_userbot.start()
            if await temp_userbot.is_user_authorized():
                userbot = temp_userbot
                await userbot.get_dialogs()
                try:
                    me = await userbot.get_me()
                    own_account_ids.add(me.id)
                except Exception:
                    pass
                attach_group_watcher(userbot)
                print("🚀 Userbot Session Successfully Loaded from marcuz_col!")
            else:
                print("⚠️ Userbot session is DEAD (not authorized / logged out). Skipping — talkon/copyon will run without it.")
                await temp_userbot.disconnect()
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
                if await pr_client.is_user_authorized():
                    powerranger_clients.append(pr_client)
                    bot_last_send[pr_client] = time.time() + random.uniform(0, 2.0)
                    try:
                        me = await pr_client.get_me()
                        own_account_ids.add(me.id)
                    except Exception:
                        pass
                    attach_group_watcher(pr_client)
                else:
                    print("⚠️ A Power Ranger session is DEAD (banned/logged out). Skipping this account.")
                    await pr_client.disconnect()
            except Exception as pr_err:
                print(f"⚠️ Failed to connect a Power Ranger account from DB: {pr_err}")

    print(f"🚀 Loaded {len(powerranger_clients)} Power Ranger Bot(s) completely!")

    await bot.start(bot_token=BOT_TOKEN)
    try:
        bot_me = await bot.get_me()
        own_account_ids.add(bot_me.id)
    except Exception:
        pass
    print("🤖 Official Bot is running...")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(startup())
