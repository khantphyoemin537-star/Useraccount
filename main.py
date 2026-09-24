#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sovereign Ninja (clean)
- 31 ninjas work for /spam
- Auto-ninja on SPAWN_GROUP_2 (/w + /catch forwarding)
- /autosession : reply to an ID list → export session strings
- Auto-warmup on startup
- Flask health check
"""

import asyncio, io, logging, os, random, re, sys, threading, time, unicodedata
from datetime import datetime, timedelta
from typing import Dict, List, Set

import pytz
from flask import Flask
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, OperationFailure
from telethon import TelegramClient, events, errors
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest


class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "7693106830"))
    MONGO_URI = os.getenv("MONGO_URI",
        "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true")
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "8824002850:AAGPtl7M0dw_gDVEZNxM3xxrYQazKvO5FKo")

    SPAM_GROUPS = [-1004381473883, -1003836488351, -1003733625547, -1004358425408]

    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yangon"))
    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    MAX_RETRIES = 3

    # Auto-ninja on SPAWN_GROUP_2
    SPAWN_BOT_2_ID = 8999491734
    SPAWN_GROUP_2 = -1003580630981
    NINJA_PICK_COUNT = 5
    NINJA_W_DELAY_MIN = 3.0
    NINJA_W_DELAY_MAX = 4.0
    NINJA_IGNORED_EMOJIS = ["🔵", "🟣", "🟠"]

    # /startspam timing
    START_SPAM_INTERVAL = 180
    START_SPAM_MIN_DELAY = 5
    START_SPAM_MAX_DELAY = 15
    START_SPAM_JITTER = 0.10


SPAM_TEXT = """ @FLASH_SPAM_Bot | @fuckyourwifey_bot | @Imjustkidding_bot | @GodMorgan_robot | @enforcermorgan_11robot | fqcawqAaaaafbBsqqlqoျဘျဆငငေတငတုsahqBwqiqoaj#!11&$1(!92929*@*@>>
"""

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("SovereignNinja")
flask_app = Flask(__name__)


@flask_app.route("/")
def health_check():
    return "Sovereign Ninja System is operational."


def run_flask():
    flask_app.run(host="0.0.0.0", port=Config.FLASK_PORT, threaded=True)


# ---------- Database ----------
class DatabaseManager:
    def __init__(self, uri):
        self.uri = uri
        self.client = None
        self.db = None

    async def connect(self):
        for attempt in range(1, Config.MAX_RETRIES + 1):
            try:
                self.client = AsyncIOMotorClient(
                    self.uri, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=5000)
                await self.client.admin.command("ping")
                self.db = self.client["telegram_bot"]
                logger.info("MongoDB connected.")
                return
            except (ConnectionFailure, OperationFailure) as e:
                logger.warning(f"MongoDB attempt {attempt} failed: {e}")
                if attempt == Config.MAX_RETRIES:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def close(self):
        if self.client:
            self.client.close()

    @property
    def ninja_col(self):
        return self.db["ninja_col"]


# ══════════════════════════════════════════════════════════════════
#  MAIN BOT
# ══════════════════════════════════════════════════════════════════
class SovereignBot:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.bot_client = TelegramClient(
            "bot_main_session", Config.API_ID, Config.API_HASH,
            flood_sleep_threshold=60)
        self.bot_id = None
        self.ninja_clients: List[TelegramClient] = []
        self.ninja_names: List[str] = []
        self.ninja_ids: Set[int] = set()
        self.ninja_warmed: Dict[int, bool] = {}
        self.ninja_spam_tasks: Dict = {}
        # Auto-ninja on SPAWN_GROUP_2
        self.ninja_spawn_marker = {"key": None, "selected": set()}
        self.ninja_spawn_tracker: Dict = {}
        self.ninja_latest_spawn: Dict = {}
        # /startspam
        self.start_spam_tasks: Dict = {}
        self.start_spam_target = None
        self.start_spam_active = False
        self._register_handlers()

    # ---------- AUTO-PROMOTE (ninja joins a group) ----------
    async def _ninja_join_handler(self, event):
        try:
            me_id = getattr(event.client, "tg_user_id", None)
            if not me_id:
                return
            joined = False
            if event.user_joined or event.user_added:
                try:
                    if event.user_id == me_id:
                        joined = True
                except Exception:
                    pass
            if not joined:
                return
            cid = event.chat_id
            logger.info(f"🥷 Ninja {me_id} joined {cid} → auto-promote")
            asyncio.create_task(self._auto_promote_ninjas(cid))
        except Exception as e:
            logger.warning(f"ninja_join: {e}")

    async def _auto_promote_ninjas(self, cid):
        try:
            perms = await self.bot_client.get_permissions(cid, "me")
            if not (perms and getattr(perms, "is_admin", False)):
                return
            if not (getattr(perms, "add_admins", False) or getattr(perms, "is_creator", False)):
                return
            promoted = already = failed = 0
            for c in self.ninja_clients:
                try:
                    uid = getattr(c, "tg_user_id", None)
                    if not uid:
                        me = await c.get_me(); uid = me.id; c.tg_user_id = uid
                    np = await self.bot_client.get_permissions(cid, uid)
                    if np and getattr(np, "is_admin", False):
                        already += 1; continue
                    await self.bot_client.edit_admin(
                        cid, uid, change_info=False, post_messages=True,
                        edit_messages=True, delete_messages=True, ban_users=True,
                        invite_users=True, pin_messages=True, add_admins=False,
                        anonymous=False, manage_call=False)
                    promoted += 1
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1); failed += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.4)
            try:
                await self.bot_client.send_message(
                    Config.OWNER_ID,
                    f"✅ Auto-Promote `{cid}` · promoted={promoted} already={already} failed={failed}")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"_auto_promote: {e}")

    # ---------- START-SPAM (/startspam @bot) ----------
    async def _start_spam_worker(self, ninja, uid, target):
        await asyncio.sleep(random.uniform(Config.START_SPAM_MIN_DELAY, Config.START_SPAM_MAX_DELAY))
        while self.start_spam_active and uid in self.start_spam_tasks:
            try:
                await asyncio.wait_for(ninja.send_message(target, "/start"), timeout=20)
                logger.info(f"🎯 [{uid}] /start → @{target}")
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1); continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"🎯 [{uid}]: {e}")
            jitter = Config.START_SPAM_INTERVAL * random.uniform(
                -Config.START_SPAM_JITTER, Config.START_SPAM_JITTER)
            wait = max(30, Config.START_SPAM_INTERVAL + jitter)
            waited = 0
            while waited < wait and self.start_spam_active:
                await asyncio.sleep(5); waited += 5

    async def start_start_spam(self, target):
        if self.start_spam_active:
            return 0
        if not self.ninja_clients:
            return 0
        self.start_spam_active = True
        self.start_spam_target = target
        started = 0
        for c in self.ninja_clients:
            try:
                uid = getattr(c, "tg_user_id", None)
                if not uid:
                    me = await c.get_me(); uid = me.id; c.tg_user_id = uid
                self.start_spam_tasks[uid] = asyncio.create_task(
                    self._start_spam_worker(c, uid, target))
                started += 1
            except Exception as e:
                logger.warning(f"start_spam worker: {e}")
        return started

    async def stop_start_spam(self):
        if not self.start_spam_active:
            return 0
        self.start_spam_active = False
        stopped = 0
        for uid, t in list(self.start_spam_tasks.items()):
            if not t.done():
                t.cancel(); stopped += 1
        self.start_spam_tasks.clear()
        self.start_spam_target = None
        return stopped

    # ---------- AUTO-NINJA on SPAWN_GROUP_2 ----------
    async def _ninja_spawn_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid:
                return
            if event.chat_id != Config.SPAWN_GROUP_2:
                return
            text = event.text or ""
            if not text:
                try:
                    if event.message and event.message.message:
                        text = event.message.message
                except Exception:
                    pass
            if not text:
                return
            upper = text.upper()
            if not ("A CHARACTER HAS SPAWNED" in upper
                    or "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ" in text):
                return
            if any(e in text for e in Config.NINJA_IGNORED_EMOJIS):
                return
            skey = f"{event.chat_id}:{event.message.id}"
            if self.ninja_spawn_marker.get("key") != skey:
                avail = list(self.ninja_ids)
                if not avail:
                    return
                picked = (set(avail) if len(avail) <= Config.NINJA_PICK_COUNT
                          else set(random.sample(avail, Config.NINJA_PICK_COUNT)))
                self.ninja_spawn_marker["key"] = skey
                self.ninja_spawn_marker["selected"] = picked
            if uid not in self.ninja_spawn_marker["selected"]:
                return
            await asyncio.sleep(random.uniform(
                Config.NINJA_W_DELAY_MIN, Config.NINJA_W_DELAY_MAX))
            try:
                r = await event.message.reply("/w")
                self.ninja_spawn_tracker[(uid, r.id)] = event.chat_id
                self.ninja_latest_spawn[uid] = event.chat_id
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"spawn handler: {e}")

    async def _ninja_hint_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid or event.chat_id != Config.SPAWN_GROUP_2:
                return
            if event.sender_id != Config.SPAWN_BOT_2_ID or not event.reply_to_msg_id:
                return
            if (uid, event.reply_to_msg_id) not in self.ninja_spawn_tracker:
                return
            text = event.text or ""
            if not text:
                try:
                    if event.message and event.message.message:
                        text = event.message.message
                except Exception:
                    pass
            if not text:
                return
            m = re.search(r"(/catch(?:@\w+)?\s+[^\n]+)", text)
            if not m:
                return
            cmd = m.group(1).strip(" `\n\r")
            grp = (self.ninja_spawn_tracker.get((uid, event.reply_to_msg_id))
                   or self.ninja_latest_spawn.get(uid))
            if grp:
                try:
                    await event.client.send_message(grp, cmd)
                except Exception:
                    pass
        except Exception:
            pass

    def _register_ninja_handlers(self, client):
        client.add_event_handler(
            self._ninja_spawn_handler,
            events.NewMessage(from_users=Config.SPAWN_BOT_2_ID))
        client.add_event_handler(
            self._ninja_hint_handler,
            events.NewMessage(chats=Config.SPAWN_GROUP_2))
        client.add_event_handler(self._ninja_join_handler, events.ChatAction())

    # ---------- LOAD NINJAS ----------
    async def load_ninja_pools(self):
        for c in self.ninja_clients:
            try:
                if c.is_connected():
                    await c.disconnect()
            except Exception:
                pass
        self.ninja_clients.clear()
        self.ninja_names.clear()
        self.ninja_ids.clear()
        async for doc in self.db.ninja_col.find():
            sess = doc.get("session")
            if not sess:
                continue
            try:
                c = TelegramClient(
                    StringSession(sess), Config.API_ID, Config.API_HASH,
                    flood_sleep_threshold=0)
                await c.start()
                if await c.is_user_authorized():
                    me = await c.get_me()
                    c.tg_user_id = me.id
                    self.ninja_clients.append(c)
                    self.ninja_names.append(doc.get("name", f"Ninja-{len(self.ninja_clients)}"))
                    self.ninja_ids.add(me.id)
                    self._register_ninja_handlers(c)
                    logger.info(f"✅ Ninja '{doc.get('name')}' loaded: @{me.username}")
                else:
                    await c.disconnect()
            except Exception as e:
                logger.error(f"❌ Ninja load failed: {e}")
        logger.info(f"🚀 Ninja Pool ready: {len(self.ninja_clients)} clients.")

    # ---------- /spam (hardcore groups) ----------
    async def _start_spam_loop(self, chat_ids):
        key = tuple(sorted(chat_ids))
        if self.ninja_spam_tasks.get(key):
            return
        self.ninja_spam_tasks[key] = True
        if not self.ninja_clients:
            return
        flood_until: Dict = {}
        lock = asyncio.Lock()

        async def send(c, cid):
            async with lock:
                if c in flood_until and flood_until[c] > datetime.now():
                    return
            try:
                await c.send_message(cid, SPAM_TEXT)
            except FloodWaitError as e:
                async with lock:
                    flood_until[c] = datetime.now() + timedelta(seconds=e.seconds + 1)
            except Exception:
                pass

        async def loop():
            while self.ninja_spam_tasks.get(key):
                tasks = []
                for cid in chat_ids:
                    c = None
                    for _ in range(3):
                        cc = random.choice(self.ninja_clients)
                        async with lock:
                            if cc not in flood_until or flood_until[cc] < datetime.now():
                                c = cc
                                break
                    if c is None:
                        await asyncio.sleep(0.3)
                        continue
                    tasks.append(send(c, cid))
                if tasks:
                    await asyncio.gather(*tasks)
                await asyncio.sleep(0.05)
            logger.info(f"🛑 Spam stopped for {len(chat_ids)} groups")

        asyncio.create_task(loop())

    # ══════════════════════════════════════════════════════════════
    #  COMMAND HANDLERS
    # ══════════════════════════════════════════════════════════════
    def _register_handlers(self):

        # ---------- /addninja ----------
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/addninja(?:@\w+)?(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_ninja(event):
            if event.sender_id != Config.OWNER_ID:
                return
            cmd = event.pattern_match.group(1)
            sess = event.pattern_match.group(2)
            name = cmd if cmd and not sess else "Ninja"
            if not sess:
                r = await event.get_reply_message()
                if r and r.text:
                    sess = r.text.strip()
                    if cmd and not cmd.startswith("session"):
                        name = cmd
                else:
                    return await event.reply("❓ Usage: /addninja <name> <session>")
            if not sess or len(sess) < 10:
                return await event.reply("❌ Invalid session.")
            async for d in self.db.ninja_col.find():
                if d.get("session") == sess:
                    return await event.reply("⚠️ Already exists.")
            await self.db.ninja_col.insert_one({"name": name, "session": sess})
            try:
                c = TelegramClient(
                    StringSession(sess), Config.API_ID, Config.API_HASH,
                    flood_sleep_threshold=0)
                await c.start()
                me = await c.get_me()
                c.tg_user_id = me.id
                self.ninja_clients.append(c)
                self.ninja_names.append(name)
                self.ninja_ids.add(me.id)
                self._register_ninja_handlers(c)
                await event.reply(f"✅ '{name}' (ID: {me.id}) added. Total: {len(self.ninja_clients)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {e}")
                await self.db.ninja_col.delete_one({"session": sess})

        # ---------- /listninja ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/listninja(?:@\w+)?$"))
        async def list_ninja(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.ninja_clients:
                return await event.reply("📭 No ninjas.")
            online = 0
            lines = [f"👥 **Ninja Pool ({len(self.ninja_clients)} loaded)**"]
            for i, (c, n) in enumerate(zip(self.ninja_clients, self.ninja_names)):
                try:
                    me = await c.get_me()
                    online += 1
                    full = f"{me.first_name or ''} {me.last_name or ''}".strip() or "No Name"
                    u = f"(@{me.username})" if me.username else ""
                    lines.append(f"  {i+1}. **{full}** {u} (ID: `{me.id}`) ✅")
                except Exception:
                    lines.append(f"  {i+1}. **{n}** ❌")
            lines.append(f"\n📊 Online: {online}/{len(self.ninja_clients)}")
            await event.reply("\n".join(lines), parse_mode="markdown")

        # ---------- /removeninja ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/removeninja(?:@\w+)?\s+(.+)$"))
        async def remove_ninja(event):
            if event.sender_id != Config.OWNER_ID:
                return
            target = event.pattern_match.group(1).strip()
            plist = await self.db.ninja_col.find().to_list(length=None)
            idx = None
            if target.isdigit():
                idx = int(target) - 1
            else:
                for i, d in enumerate(plist):
                    if d.get("name") == target:
                        idx = i
                        break
            if idx is None or idx < 0 or idx >= len(plist):
                return await event.reply(f"❌ Not found: {target}")
            doc = plist[idx]
            await self.db.ninja_col.delete_one({"_id": doc["_id"]})
            if idx < len(self.ninja_clients):
                c = self.ninja_clients.pop(idx)
                self.ninja_names.pop(idx)
                try:
                    await c.disconnect()
                except Exception:
                    pass
                await event.reply(f"✅ Removed '{doc.get('name')}'.")
            else:
                await event.reply("✅ Removed from DB.")

        # ---------- /autosession ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/autosession(?:@\w+)?$"))
        async def autosession_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")

            reply = await event.get_reply_message()
            if not reply or not reply.text:
                return await event.reply(
                    "⚠️ **Usage:** Reply to a message containing IDs (one per line) → `/autosession`\n\n"
                    "Example:\n```\n1234567890\n9876543210\n```",
                    parse_mode="markdown")

            ids = []
            for line in reply.text.splitlines():
                line = line.strip()
                m = re.match(r"^(\d+)", line)
                if m:
                    try:
                        n = int(m.group(1))
                        if n > 0:
                            ids.append(n)
                    except Exception:
                        pass

            # dedupe preserve order
            seen = set(); uniq = []
            for i in ids:
                if i not in seen:
                    seen.add(i); uniq.append(i)

            if not uniq:
                return await event.reply("❌ No valid IDs found in replied message.")

            status = await event.reply(
                f"⏳ Exporting sessions for `{len(uniq)}` IDs…",
                parse_mode="markdown")

            uid_map = {}
            for c in self.ninja_clients:
                u = getattr(c, "tg_user_id", None)
                if u:
                    uid_map[u] = c

            lines = []
            missing = []
            for uid in uniq:
                client = uid_map.get(uid)
                if not client:
                    missing.append(uid)
                    continue
                try:
                    sess = client.session.save()
                except Exception:
                    sess = None
                try:
                    me = await client.get_me()
                    full = ((me.first_name or "") + (" " + me.last_name if me.last_name else "")).strip() or "No Name"
                    uname = f"@{me.username}" if me.username else "—"
                except Exception:
                    full, uname = "?", "—"
                lines.append(
                    f"# {uid} | {full} | {uname}\n"
                    f"{sess or '(session unavailable)'}")

            body = "\n\n".join(lines)
            header = (
                f"# ═══════════════════════════════════════════════\n"
                f"# Session Export\n"
                f"# Total requested  : {len(uniq)}\n"
                f"# Exported OK      : {len(lines)}\n"
                f"# Missing from pool: {len(missing)}\n"
                f"# Missing IDs      : {', '.join(str(m) for m in missing) if missing else '—'}\n"
                f"# Generated        : {datetime.now(Config.TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"# ═══════════════════════════════════════════════\n\n"
            )
            content = (header + body).encode("utf-8")
            buf = io.BytesIO(content)
            buf.name = f"sessions_{int(time.time())}.txt"

            try:
                await status.delete()
            except Exception:
                pass

            await event.reply(
                f"✅ **Sessions ready**\n"
                f"📋 Requested: `{len(uniq)}`\n"
                f"🥷 Exported: `{len(lines)}`\n"
                f"⚠️ Missing: `{len(missing)}`",
                file=buf,
                parse_mode="markdown")

        # ---------- /autoninja (info) ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/autoninja(?:@\w+)?$"))
        async def autoninja_status(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await event.reply(
                f"🥷 **AUTO-NINJA (SPAWN_GROUP_2)**\n"
                f"🆔 Spawn Bot: `{Config.SPAWN_BOT_2_ID}`\n"
                f"📍 Group: `{Config.SPAWN_GROUP_2}`\n"
                f"👥 Pool: `{len(self.ninja_clients)}`\n"
                f"🎯 Pick: `{Config.NINJA_PICK_COUNT}`\n"
                f"⏱️ Delay: `{Config.NINJA_W_DELAY_MIN}-{Config.NINJA_W_DELAY_MAX}s`\n"
                f"🚫 Ignored emojis: `{' '.join(Config.NINJA_IGNORED_EMOJIS)}`",
                parse_mode="markdown")

        # ---------- /startspam ----------
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/startspam(?:@\w+)?(?:\s+(@?\w+))?$"))
        async def startspam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            arg = event.pattern_match.group(1)
            if not arg:
                return await event.reply("⚠️ Usage: /startspam @BotUsername")
            target = arg.lstrip("@").strip()
            if not target:
                return await event.reply("❌ Invalid username.")
            if self.start_spam_active:
                return await event.reply(f"⚠️ Already running → @{self.start_spam_target}")
            if not self.ninja_clients:
                return await event.reply("❌ Ninja pool empty.")
            n = await self.start_start_spam(target)
            await event.reply(
                f"🎯 START SPAM ON → @{target} · {n} workers · "
                f"{Config.START_SPAM_INTERVAL}s interval")

        # ---------- /stopspam ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/stopspam(?:@\w+)?$"))
        async def stopspam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            if not self.start_spam_active:
                return await event.reply("ℹ️ Not running.")
            target = self.start_spam_target
            n = await self.stop_start_spam()
            await event.reply(f"🛑 START SPAM OFF · @{target} · stopped {n}")

        # ---------- /spamstatus ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/spamstatus(?:@\w+)?$"))
        async def spamstatus_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            if self.start_spam_active:
                await event.reply(
                    f"🎯 ON · @{self.start_spam_target} · {len(self.start_spam_tasks)} workers")
            else:
                await event.reply("🎯 OFF")

        # ---------- /spam ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/spam(?:@\w+)?$"))
        async def spam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await self._start_spam_loop(Config.SPAM_GROUPS)
            await event.reply(f"🗣️ Spam started on {len(Config.SPAM_GROUPS)} groups.")

        # ---------- ရပ် / /stop ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop(?:@\w+)?)$"))
        async def stop_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            cid = event.chat_id
            stopped = False
            for k in list(self.ninja_spam_tasks.keys()):
                if cid in k or event.sender_id == Config.OWNER_ID:
                    self.ninja_spam_tasks[k] = False
                    stopped = True
            await event.reply("🛑 Spam stopped." if stopped else "ℹ️ Nothing to stop.")

        # ---------- /go (join invite link with all ninjas) ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/go(?:@\w+)?$"))
        async def go_group(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not event.is_reply:
                return await event.reply("❌ Reply to invite link.")
            r = await event.get_reply_message()
            if not r.text:
                return await event.reply("❌ No text.")
            m = re.search(r"(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)", r.text)
            if not m:
                return await event.reply("❌ No link.")
            link = m.group(0)
            if "joinchat/" in link:
                h = link.split("joinchat/")[1].split("?")[0]
            elif "+" in link:
                h = link.split("+")[1].split("?")[0]
            else:
                h = None
            if not h:
                return await event.reply("❌ Bad link.")
            clients = self.ninja_clients.copy()
            if not clients:
                return await event.reply("❌ No clients.")
            await event.reply(f"⏳ Joining with {len(clients)} clients...")
            success = 0
            for c in clients:
                try:
                    await asyncio.wait_for(c(ImportChatInviteRequest(h)), timeout=20)
                    success += 1
                except errors.rpcerrorlist.UserAlreadyParticipantError:
                    success += 1
                except FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds, 30))
                    try:
                        await c(ImportChatInviteRequest(h))
                        success += 1
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Join: {e}")
                await asyncio.sleep(0.3)
            try:
                chat = await clients[0].get_entity(link)
                await event.reply(f"✅ Joined `{chat.title}` ({success} clients). ID: `{chat.id}`")
            except Exception:
                await event.reply(f"✅ Joined ({success} clients).")

        # ---------- /status ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/status(?:@\w+)?$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            ss = (f"ON → @{self.start_spam_target}"
                  if self.start_spam_active else "OFF")
            await event.reply(
                f"📊 **Status**\n"
                f"🤖 Pool: `{len(self.ninja_clients)}`\n"
                f"🎯 /startspam: `{ss}`\n"
                f"🗣️ /spam groups: `{len(Config.SPAM_GROUPS)}`",
                parse_mode="markdown")

    # ══════════════════════════════════════════════════════════════
    #  START / STOP
    # ══════════════════════════════════════════════════════════════
    async def start(self):
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        me = await self.bot_client.get_me()
        self.bot_id = me.id
        logger.info(f"🤖 Bot started: @{me.username} ({self.bot_id})")

        await self.load_ninja_pools()

        threading.Thread(target=run_flask, daemon=True).start()
        await self.bot_client.run_until_disconnected()

    async def stop(self):
        if self.start_spam_active:
            await self.stop_start_spam()
        if self.bot_client.is_connected():
            await self.bot_client.disconnect()
        for c in self.ninja_clients:
            try:
                await c.disconnect()
            except Exception:
                pass
        await self.db.close()
        logger.info("🛑 Shutdown.")


async def main():
    db = DatabaseManager(Config.MONGO_URI)
    await db.connect()
    bot = SovereignBot(db)
    try:
        await bot.start()
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        logger.info("Shutdown signal.")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
