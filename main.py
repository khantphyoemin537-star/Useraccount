#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sovereign Ninja (fast · never-stop · in-memory bot session)"""

import asyncio, io, logging, os, random, re, sys, threading, time
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


# ══════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════
class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "7693106830"))
    MONGO_URI = os.getenv(
        "MONGO_URI",
        "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/"
        "?appName=Cluster0&tlsAllowInvalidCertificates=true")
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN",
                          "8824002850:AAELMmlNd_rxs-kJfX69usTrA86cr-z-Va4")

    SPAM_GROUPS = [
        -1004381473883,
        -1003836488351,
        -1003733625547,
        -1004358425408,
    ]

    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yangon"))
    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    MAX_RETRIES = 3
    BOT_START_TIMEOUT = 90

    SPAWN_GAME_BOT_ID = 6157455819
    SPAWN_HINT_BOT_ID = 8999491734
    SPAWN_HINT_BOT_USERNAME = os.getenv(
        "SPAWN_HINT_BOT_USERNAME", "YourHintBotUsername")

    NINJA_PICK_COUNT = 7
    NINJA_W_DELAY_MIN = 0.3
    NINJA_W_DELAY_MAX = 1.0
    NINJA_WHITELIST_EMOJIS = ["🟣", "🟠", "🟡"]
    SPAWN_PHRASES = (
        "A CHARACTER HAS SPAWNED",
        "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ",
        "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ɪɴ ᴛʜᴇ ᴄʜᴀᴛ",
    )

    SPAM_GROUP_INTERVAL    = 0.3
    SPAM_GLOBAL_DELAY      = 0.06
    SPAM_NINJA_COOLDOWN    = 1.5
    SPAM_CATCH_COOLDOWN    = 45
    SPAM_FLOOD_DEFAULT     = 30
    SPAM_FLOOD_MAX_CAP     = 90
    SPAM_PAUSE_AFTER_SPAWN = 2
    SPAM_LOOP_TICK         = 0.03
    SPAM_ENTITY_RETRY_WAIT = 30
    SPAM_WATCHDOG_INTERVAL = 15
    SPAM_STALL_THRESHOLD   = 45

    HINT_BOT_WARMUP_INTERVAL = 1800
    ENTITY_CACHE_INTERVAL    = 900

    START_SPAM_MIN_DELAY = 1
    START_SPAM_MAX_DELAY = 3
    START_SPAM_STAGGER   = 1.0
    START_SPAM_INTERVAL  = 240
    START_SPAM_JITTER    = 0.20


SPAM_TEXT = (
    " @FLASH_SPAM_Bot | @fuckyourwifey_bot | @Imjustkidding_bot | "
    "@GodMorgan_robot | @enforcermorgan_11robot | "
    "fqcawqAaaaafbBsqqlqoျဘျဆငငေတငတုsahqBwqiqoaj#!11&$1(!92929*@*@>>\n"
)


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
    try:
        flask_app.run(host="0.0.0.0", port=Config.FLASK_PORT, threaded=True)
    except Exception as e:
        logger.error(f"Flask failed: {e}")


# ══════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════
class DatabaseManager:
    def __init__(self, uri):
        self.uri = uri
        self.client = None
        self.db = None

    async def connect(self):
        for attempt in range(1, Config.MAX_RETRIES + 1):
            try:
                self.client = AsyncIOMotorClient(
                    self.uri,
                    tlsAllowInvalidCertificates=True,
                    serverSelectionTimeoutMS=5000)
                await self.client.admin.command("ping")
                self.db = self.client["telegram_bot"]
                logger.info("MongoDB connected.")
                return
            except (ConnectionFailure, OperationFailure) as e:
                logger.warning(f"MongoDB attempt {attempt}: {e}")
                if attempt == Config.MAX_RETRIES:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def close(self):
        if self.client:
            self.client.close()

    @property
    def ninja_col(self):
        return self.db["ninja_col"]

    @property
    def catch_col(self):
        return self.db["catch_col"]


# ══════════════════════════════════════════════════════════════════
#  MAIN BOT
# ══════════════════════════════════════════════════════════════════
class SovereignBot:
    def __init__(self, db: DatabaseManager):
        self.db = db

        # 🔥 StringSession = in-memory · user session မပါဝင်နိုင်
        self.bot_client = TelegramClient(
            StringSession(),
            Config.API_ID, Config.API_HASH,
            flood_sleep_threshold=60)
        self.bot_id = None

        self.ninja_clients: List[TelegramClient] = []
        self.ninja_names: List[str] = []
        self.ninja_ids: Set[int] = set()

        self.catch_ninja_ids: Set[int] = set()

        self.ninja_spawn_marker = {"key": None, "selected": set()}
        self.ninja_forward_tracker: Dict[int, dict] = {}

        self.flood_until: Dict = {}
        self.spam_last_used: Dict = {}
        self.spam_last_sent: Dict = {}
        self.spam_pause_until: float = 0.0

        self.ninja_spam_tasks: Dict = {}
        self.spam_active: bool = False

        self.start_spam_tasks: Dict = {}
        self.start_spam_target = None
        self.start_spam_active = False

        self._warmup_task: asyncio.Task = None
        self._watchdog_task: asyncio.Task = None
        self._entity_warm_task: asyncio.Task = None
        self._spam_loop_tasks: Dict = {}
        self._last_send_time: float = 0.0

        self._register_handlers()

    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _looks_like_spawn(text: str) -> bool:
        if not text:
            return False
        upper = text.upper()
        for ph in Config.SPAWN_PHRASES:
            if ph.upper() in upper:
                return True
        return False

    @staticmethod
    def _has_whitelist_emoji(text: str) -> bool:
        return any(e in text for e in Config.NINJA_WHITELIST_EMOJIS)

    def _mark_flood(self, client, seconds: int = None):
        sec = seconds if (seconds and seconds > 0) else Config.SPAM_FLOOD_DEFAULT
        if sec > Config.SPAM_FLOOD_MAX_CAP:
            sec = Config.SPAM_FLOOD_MAX_CAP
        self.flood_until[client] = time.monotonic() + sec
        uid = getattr(client, "tg_user_id", "?")
        logger.warning(f"⛔ [{uid}] flood {sec}s")

    def _hint_target_candidates(self):
        cands = []
        if (Config.SPAWN_HINT_BOT_USERNAME
                and Config.SPAWN_HINT_BOT_USERNAME not in
                ("YourHintBotUsername", "", "@")):
            cands.append(Config.SPAWN_HINT_BOT_USERNAME.lstrip("@"))
        cands.append(Config.SPAWN_HINT_BOT_ID)
        return cands

    # ─── Entity cache warm ──────────────────────────────────────
    async def _warm_entity_cache(self):
        if not self.ninja_clients:
            return
        logger.info(
            f"🔥 Entity cache · {len(self.ninja_clients)} ninjas × "
            f"{len(Config.SPAM_GROUPS)} groups")
        ok = fail = 0
        for c in self.ninja_clients:
            uid = getattr(c, "tg_user_id", "?")
            ninja_ok = 0
            for cid in Config.SPAM_GROUPS:
                try:
                    await c.get_entity(cid)
                    ninja_ok += 1
                    ok += 1
                except FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds, 20))
                    fail += 1
                except Exception:
                    fail += 1
                await asyncio.sleep(0.1)
            if ninja_ok < len(Config.SPAM_GROUPS):
                logger.warning(
                    f"  ⚠️ [{uid}] {ninja_ok}/{len(Config.SPAM_GROUPS)}")
        logger.info(f"🔥 Entity cache · ok={ok} fail={fail}")

    # ─── Auto-promote ───────────────────────────────────────────
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
            logger.info(f"🥷 {me_id} joined {cid} → promote")
            asyncio.create_task(self._auto_promote_ninjas(cid))
        except Exception as e:
            logger.warning(f"ninja_join: {e}")

    async def _auto_promote_ninjas(self, cid):
        try:
            perms = await self.bot_client.get_permissions(cid, "me")
            if not (perms and getattr(perms, "is_admin", False)):
                return
            if not (getattr(perms, "add_admins", False)
                    or getattr(perms, "is_creator", False)):
                return
            promoted = already = failed = 0
            for c in self.ninja_clients:
                try:
                    uid = getattr(c, "tg_user_id", None)
                    if not uid:
                        me = await c.get_me()
                        uid = me.id
                        c.tg_user_id = uid
                    np = await self.bot_client.get_permissions(cid, uid)
                    if np and getattr(np, "is_admin", False):
                        already += 1
                        continue
                    await self.bot_client.edit_admin(
                        cid, uid,
                        change_info=False, post_messages=True,
                        edit_messages=True, delete_messages=True,
                        ban_users=True, invite_users=True,
                        pin_messages=True, add_admins=False,
                        anonymous=False, manage_call=False)
                    promoted += 1
                except FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds, 60))
                    failed += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.4)
            try:
                await self.bot_client.send_message(
                    Config.OWNER_ID,
                    f"✅ Promote `{cid}` · +{promoted} ={already} x{failed}")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"_auto_promote: {e}")

    # ─── Warmup hint bot ────────────────────────────────────────
    async def _warmup_hint_bot(self):
        if not self.ninja_clients:
            return
        target = (Config.SPAWN_HINT_BOT_USERNAME.lstrip("@")
                  if Config.SPAWN_HINT_BOT_USERNAME
                  else Config.SPAWN_HINT_BOT_ID)
        logger.info(f"🔄 Warmup {len(self.ninja_clients)} → {target}")
        ok = fail = 0
        cands = self._hint_target_candidates()
        for c in self.ninja_clients:
            uid = getattr(c, "tg_user_id", "?")
            sent = False
            for t in cands:
                try:
                    await c.send_message(t, "/start")
                    sent = True
                    break
                except FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds, 30))
                except Exception:
                    pass
            if sent:
                ok += 1
                await asyncio.sleep(random.uniform(0.3, 0.6))
            else:
                fail += 1
        logger.info(f"✅ Warmup · ok={ok} fail={fail}")

    async def _periodic_warmup_loop(self):
        while True:
            try:
                await asyncio.sleep(Config.HINT_BOT_WARMUP_INTERVAL)
                await self._warmup_hint_bot()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"periodic warmup: {e}")
                await asyncio.sleep(60)

    async def _periodic_entity_warm_loop(self):
        while True:
            try:
                await asyncio.sleep(Config.ENTITY_CACHE_INTERVAL)
                await self._warm_entity_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"periodic entity: {e}")
                await asyncio.sleep(60)

    # ─── Watchdog ───────────────────────────────────────────────
    async def _watchdog_loop(self):
        while True:
            try:
                await asyncio.sleep(Config.SPAM_WATCHDOG_INTERVAL)
                for key, task in list(self._spam_loop_tasks.items()):
                    if not self.ninja_spam_tasks.get(key):
                        continue
                    if task.done():
                        logger.warning(f"🐕 loop died → restart")
                        self._spam_loop_tasks.pop(key, None)
                        await self._start_spam_loop(list(key))
                        continue
                    now = time.monotonic()
                    if (self._last_send_time > 0
                            and now - self._last_send_time
                            > Config.SPAM_STALL_THRESHOLD):
                        logger.warning(f"🐕 stall → restart all")
                        self._last_send_time = now
                        for k in list(self.ninja_spam_tasks.keys()):
                            self.ninja_spam_tasks[k] = False
                        await asyncio.sleep(1)
                        for k in list(self._spam_loop_tasks.keys()):
                            self._spam_loop_tasks.pop(k, None)
                        await self._start_spam_loop(Config.SPAM_GROUPS)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"watchdog: {e}")
                await asyncio.sleep(10)

    # ─── /startspam ─────────────────────────────────────────────
    async def _start_spam_worker(self, ninja, uid, target, initial_delay=None):
        if initial_delay is None:
            initial_delay = random.uniform(
                Config.START_SPAM_MIN_DELAY, Config.START_SPAM_MAX_DELAY)
        await asyncio.sleep(initial_delay)
        while self.start_spam_active and uid in self.start_spam_tasks:
            try:
                await asyncio.wait_for(
                    ninja.send_message(target, "/start"), timeout=20)
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds, 300) + 1)
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            jitter = Config.START_SPAM_INTERVAL * random.uniform(
                -Config.START_SPAM_JITTER, Config.START_SPAM_JITTER)
            wait = max(60, Config.START_SPAM_INTERVAL + jitter)
            waited = 0
            while waited < wait and self.start_spam_active:
                await asyncio.sleep(5)
                waited += 5

    async def start_start_spam(self, target):
        if self.start_spam_active or not self.ninja_clients:
            return 0
        self.start_spam_active = True
        self.start_spam_target = target
        started = 0
        for i, c in enumerate(self.ninja_clients):
            try:
                uid = getattr(c, "tg_user_id", None)
                if not uid:
                    me = await c.get_me()
                    uid = me.id
                    c.tg_user_id = uid
                stagger = i * Config.START_SPAM_STAGGER
                jitter = random.uniform(
                    Config.START_SPAM_MIN_DELAY, Config.START_SPAM_MAX_DELAY)
                self.start_spam_tasks[uid] = asyncio.create_task(
                    self._start_spam_worker(c, uid, target, stagger + jitter))
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
                t.cancel()
                stopped += 1
        self.start_spam_tasks.clear()
        self.start_spam_target = None
        return stopped

    # ─── Auto-catch ─────────────────────────────────────────────
    async def _ninja_spawn_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid or uid not in self.catch_ninja_ids:
                return
            if event.chat_id not in Config.SPAM_GROUPS:
                return
            if event.sender_id != Config.SPAWN_GAME_BOT_ID:
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
            if not self._looks_like_spawn(text):
                return
            if not self._has_whitelist_emoji(text):
                return
            skey = f"{event.chat_id}:{event.message.id}"
            if self.ninja_spawn_marker.get("key") != skey:
                avail = list(self.catch_ninja_ids & self.ninja_ids)
                if not avail:
                    return
                picked = (
                    set(avail) if len(avail) <= Config.NINJA_PICK_COUNT
                    else set(random.sample(avail, Config.NINJA_PICK_COUNT)))
                self.ninja_spawn_marker["key"] = skey
                self.ninja_spawn_marker["selected"] = picked
                self.spam_pause_until = (
                    time.monotonic() + Config.SPAM_PAUSE_AFTER_SPAWN)
                logger.info(f"🎯 Spawn {skey} · {len(picked)}")
            if uid not in self.ninja_spawn_marker["selected"]:
                return
            now = time.monotonic()
            if self.flood_until.get(event.client, 0) > now:
                return
            await asyncio.sleep(random.uniform(
                Config.NINJA_W_DELAY_MIN, Config.NINJA_W_DELAY_MAX))
            try:
                await event.message.forward_to(Config.SPAWN_HINT_BOT_ID)
            except FloodWaitError as e:
                self._mark_flood(event.client, e.seconds)
                return
            except Exception:
                return
            self.ninja_forward_tracker[uid] = {
                "chat_id": event.chat_id,
                "msg_id": event.message.id,
                "time": datetime.now(),
            }
        except Exception as e:
            logger.warning(f"spawn handler: {e}")

    async def _ninja_dm_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid or uid not in self.catch_ninja_ids:
                return
            if event.sender_id != Config.SPAWN_HINT_BOT_ID:
                return
            if event.is_group or event.is_channel:
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
            info = self.ninja_forward_tracker.get(uid)
            if not info:
                return
            grp = info.get("chat_id")
            if not grp:
                return
            try:
                await event.client.send_message(grp, cmd)
                self.ninja_forward_tracker.pop(uid, None)
            except FloodWaitError as e:
                self._mark_flood(event.client, e.seconds)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"dm handler: {e}")

    def _register_ninja_handlers(self, client):
        client.add_event_handler(
            self._ninja_spawn_handler,
            events.NewMessage(
                chats=Config.SPAM_GROUPS,
                from_users=Config.SPAWN_GAME_BOT_ID))
        client.add_event_handler(
            self._ninja_dm_handler,
            events.NewMessage(
                incoming=True,
                from_users=Config.SPAWN_HINT_BOT_ID,
                func=lambda e: not e.is_group and not e.is_channel))
        client.add_event_handler(
            self._ninja_join_handler, events.ChatAction())

    # ─── Pool load ──────────────────────────────────────────────
    async def _load_catch_ids(self):
        doc = await self.db.catch_col.find_one({"_id": "catch_ids"})
        if doc:
            self.catch_ninja_ids = set(int(x) for x in doc.get("ids", []))
        logger.info(f"🎯 Catch list: {len(self.catch_ninja_ids)}")

    async def _save_catch_ids(self):
        await self.db.catch_col.update_one(
            {"_id": "catch_ids"},
            {"$set": {"ids": sorted(self.catch_ninja_ids)}},
            upsert=True)

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
                    StringSession(sess),
                    Config.API_ID, Config.API_HASH,
                    flood_sleep_threshold=0)
                await c.start()
                if await c.is_user_authorized():
                    me = await c.get_me()
                    c.tg_user_id = me.id
                    self.ninja_clients.append(c)
                    self.ninja_names.append(
                        doc.get("name", f"Ninja-{len(self.ninja_clients)}"))
                    self.ninja_ids.add(me.id)
                    self._register_ninja_handlers(c)
            except Exception as e:
                logger.error(f"❌ ninja load: {type(e).__name__}: {e}")
        logger.info(f"🚀 Pool: {len(self.ninja_clients)}")

    # ─── Spam loop ──────────────────────────────────────────────
    def _pick_spam_client(self, now: float):
        eligible = []
        for c in self.ninja_clients:
            if self.flood_until.get(c, 0) > now:
                continue
            uid = getattr(c, "tg_user_id", None)
            cooldown = (Config.SPAM_CATCH_COOLDOWN
                        if uid in self.catch_ninja_ids
                        else Config.SPAM_NINJA_COOLDOWN)
            if now - self.spam_last_used.get(c, 0) < cooldown:
                continue
            eligible.append(c)
        if not eligible:
            return None
        non_catch = [
            c for c in eligible
            if getattr(c, "tg_user_id", None) not in self.catch_ninja_ids
        ]
        pool = non_catch if non_catch else eligible
        pool.sort(key=lambda c: self.spam_last_used.get(c, 0))
        return pool[0]

    async def _start_spam_loop(self, chat_ids):
        key = tuple(sorted(chat_ids))
        if self.ninja_spam_tasks.get(key):
            return
        self.ninja_spam_tasks[key] = True
        if not self.ninja_clients:
            return

        for cid in chat_ids:
            self.spam_last_sent.setdefault(cid, 0)
        for c in self.ninja_clients:
            self.spam_last_used.setdefault(c, 0)
            self.flood_until.setdefault(c, 0)

        async def loop():
            logger.info(
                f"📢 Spam loop · {len(chat_ids)} groups · "
                f"interval={Config.SPAM_GROUP_INTERVAL}s · "
                f"pool={len(self.ninja_clients)}")
            sent_total = 0
            err_total = 0

            while self.ninja_spam_tasks.get(key):
                try:
                    now = time.monotonic()
                    if now < self.spam_pause_until:
                        await asyncio.sleep(0.15)
                        continue

                    for cid in chat_ids:
                        try:
                            now = time.monotonic()
                            if (now - self.spam_last_sent.get(cid, 0)
                                    < Config.SPAM_GROUP_INTERVAL):
                                continue
                            client = self._pick_spam_client(now)
                            if not client:
                                continue
                            uid = getattr(client, "tg_user_id", "?")
                            try:
                                peer = await client.get_input_entity(cid)
                                await client.send_message(peer, SPAM_TEXT)
                                ts = time.monotonic()
                                self.spam_last_sent[cid] = ts
                                self.spam_last_used[client] = ts
                                self._last_send_time = ts
                                sent_total += 1
                                if sent_total % 50 == 0:
                                    logger.info(
                                        f"📊 spam={sent_total} err={err_total}")
                            except FloodWaitError as e:
                                self._mark_flood(client, e.seconds)
                            except ValueError:
                                try:
                                    ent = await client.get_entity(cid)
                                    await client.send_message(ent, SPAM_TEXT)
                                    ts = time.monotonic()
                                    self.spam_last_sent[cid] = ts
                                    self.spam_last_used[client] = ts
                                    self._last_send_time = ts
                                    sent_total += 1
                                except Exception:
                                    self.flood_until[client] = (
                                        time.monotonic()
                                        + Config.SPAM_ENTITY_RETRY_WAIT)
                            except Exception as e:
                                err_total += 1
                                self.flood_until[client] = (
                                    time.monotonic() + 5)
                                if err_total % 50 == 0:
                                    logger.warning(
                                        f"⚠️ err {err_total}: "
                                        f"{type(e).__name__}")
                            await asyncio.sleep(Config.SPAM_GLOBAL_DELAY)
                        except Exception as inner:
                            logger.warning(
                                f"inner: {type(inner).__name__}")
                            await asyncio.sleep(0.1)
                    await asyncio.sleep(Config.SPAM_LOOP_TICK)
                except asyncio.CancelledError:
                    break
                except Exception as outer:
                    logger.error(
                        f"🚨 loop crash: {type(outer).__name__}: {outer}")
                    await asyncio.sleep(2)
            logger.info(f"🛑 loop stop · sent={sent_total} err={err_total}")

        task = asyncio.create_task(loop())
        self._spam_loop_tasks[key] = task

    # ══════════════════════════════════════════════════════════════
    #  COMMANDS
    # ══════════════════════════════════════════════════════════════
    def _register_handlers(self):

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
                    return await event.reply(
                        "❓ /addninja <name> <session>")
            if not sess or len(sess) < 10:
                return await event.reply("❌ Invalid session.")
            async for d in self.db.ninja_col.find():
                if d.get("session") == sess:
                    return await event.reply("⚠️ Already exists.")
            await self.db.ninja_col.insert_one(
                {"name": name, "session": sess})
            try:
                c = TelegramClient(
                    StringSession(sess),
                    Config.API_ID, Config.API_HASH,
                    flood_sleep_threshold=0)
                await c.start()
                me = await c.get_me()
                c.tg_user_id = me.id
                self.ninja_clients.append(c)
                self.ninja_names.append(name)
                self.ninja_ids.add(me.id)
                self._register_ninja_handlers(c)
                await event.reply(
                    f"✅ '{name}' `{me.id}` added · "
                    f"total `{len(self.ninja_clients)}`")
                for t in self._hint_target_candidates():
                    try:
                        await c.send_message(t, "/start")
                        break
                    except Exception:
                        pass
                for cid in Config.SPAM_GROUPS:
                    try:
                        await c.get_entity(cid)
                    except Exception:
                        pass
            except Exception as e:
                await event.reply(f"❌ {e}")
                await self.db.ninja_col.delete_one({"session": sess})

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/listninja(?:@\w+)?$"))
        async def list_ninja(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.ninja_clients:
                return await event.reply("📭 No ninjas.")
            online = 0
            lines = [f"👥 **Pool ({len(self.ninja_clients)})**"]
            for i, (c, n) in enumerate(
                    zip(self.ninja_clients, self.ninja_names)):
                try:
                    me = await c.get_me()
                    online += 1
                    full = (
                        f"{me.first_name or ''} "
                        f"{me.last_name or ''}").strip() or "No Name"
                    u = f"(@{me.username})" if me.username else ""
                    tag = " 🎯" if me.id in self.catch_ninja_ids else ""
                    lines.append(
                        f"  {i+1}. **{full}** {u} `{me.id}` ✅{tag}")
                except Exception:
                    lines.append(f"  {i+1}. **{n}** ❌")
            lines.append(f"\n📊 {online}/{len(self.ninja_clients)}")
            await event.reply("\n".join(lines), parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/removeninja(?:@\w+)?\s+(.+)$"))
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
                return await event.reply(f"❌ {target}")
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

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/setcatch(?:@\w+)?(?:\s+([\s\S]+))?$"))
        async def setcatch_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            raw = event.pattern_match.group(1) or ""
            r = await event.get_reply_message()
            if r and r.text:
                raw = raw + "\n" + r.text
            if not raw.strip():
                return await event.reply("⚠️ /setcatch 123 456")
            ids = set()
            for tok in re.split(r"[\s,;]+", raw):
                m = re.match(r"^(\d{5,})$", tok.strip())
                if m:
                    ids.add(int(m.group(1)))
            if not ids:
                return await event.reply("❌ No valid IDs.")
            before = len(self.catch_ninja_ids)
            self.catch_ninja_ids.update(ids)
            added = len(self.catch_ninja_ids) - before
            await self._save_catch_ids()
            await event.reply(
                f"✅ +`{added}` · total `{len(self.catch_ninja_ids)}`",
                parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/listcatch(?:@\w+)?$"))
        async def listcatch_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.catch_ninja_ids:
                return await event.reply("📭 Empty.")
            lines = [f"🎯 **Catch ({len(self.catch_ninja_ids)})**"]
            for i, uid in enumerate(sorted(self.catch_ninja_ids)):
                tag = "✅" if uid in self.ninja_ids else "⚠️"
                lines.append(f"  {i+1}. `{uid}` {tag}")
            await event.reply("\n".join(lines), parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/clearcatch(?:@\w+)?$"))
        async def clearcatch_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            n = len(self.catch_ninja_ids)
            self.catch_ninja_ids.clear()
            await self._save_catch_ids()
            await event.reply(f"🗑️ Cleared {n}")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/autosession(?:@\w+)?$"))
        async def autosession_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            reply = await event.get_reply_message()
            if not reply or not reply.text:
                return await event.reply("⚠️ Reply to ID list.")
            ids = []
            for line in reply.text.splitlines():
                m = re.match(r"^(\d+)", line.strip())
                if m:
                    try:
                        n = int(m.group(1))
                        if n > 0:
                            ids.append(n)
                    except Exception:
                        pass
            seen = set()
            uniq = []
            for i in ids:
                if i not in seen:
                    seen.add(i)
                    uniq.append(i)
            if not uniq:
                return await event.reply("❌ No valid IDs.")
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
                    full = (
                        (me.first_name or "")
                        + (" " + me.last_name if me.last_name else "")
                    ).strip() or "No Name"
                    uname = f"@{me.username}" if me.username else "—"
                except Exception:
                    full, uname = "?", "—"
                lines.append(
                    f"# {uid} | {full} | {uname}\n{sess or '(unavailable)'}")
            body = "\n\n".join(lines)
            header = (
                f"# Session Export\n"
                f"# Requested: {len(uniq)}\n"
                f"# OK: {len(lines)}\n"
                f"# Missing: {len(missing)}\n"
                f"# Gen: {datetime.now(Config.TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            )
            buf = io.BytesIO((header + body).encode("utf-8"))
            buf.name = f"sessions_{int(time.time())}.txt"
            await event.reply(
                f"✅ `{len(uniq)}` → `{len(lines)}` · missing `{len(missing)}`",
                file=buf, parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/autoninja(?:@\w+)?$"))
        async def autoninja_status(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await event.reply(
                f"🥷 **AUTO-CATCH**\n"
                f"🎮 `{Config.SPAWN_GAME_BOT_ID}`\n"
                f"🥷 `{Config.SPAWN_HINT_BOT_USERNAME}`\n"
                f"📍 `{len(Config.SPAM_GROUPS)}` groups\n"
                f"👥 `{len(self.ninja_clients)}` pool\n"
                f"🎯 `{len(self.catch_ninja_ids)}` catch\n"
                f"⚡ `{Config.SPAM_GROUP_INTERVAL}s/group`",
                parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/warmup(?:@\w+)?$"))
        async def warmup_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await event.reply("🔄 Warming…")
            await self._warmup_hint_bot()
            await event.reply("✅ Done.")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/warmcache(?:@\w+)?$"))
        async def warmcache_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await event.reply("🔥 Cache warm…")
            await self._warm_entity_cache()
            await event.reply("✅ Done.")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/startspam(?:@\w+)?(?:\s+(@?\w+))?$"))
        async def startspam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            arg = event.pattern_match.group(1)
            if not arg:
                return await event.reply("⚠️ /startspam @Bot")
            target = arg.lstrip("@").strip()
            if self.start_spam_active:
                return await event.reply(
                    f"⚠️ Running → @{self.start_spam_target}")
            n = await self.start_start_spam(target)
            await event.reply(
                f"🎯 ON → @{target} · `{n}` · "
                f"stagger `{Config.START_SPAM_STAGGER}s`",
                parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/stopspam(?:@\w+)?$"))
        async def stopspam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.start_spam_active:
                return await event.reply("ℹ️ Not running.")
            n = await self.stop_start_spam()
            await event.reply(f"🛑 Stopped {n}")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/spamstatus(?:@\w+)?$"))
        async def spamstatus_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            now = time.monotonic()
            af = sum(1 for c in self.ninja_clients
                     if self.flood_until.get(c, 0) > now)
            await event.reply(
                f"🎯 {'ON' if self.start_spam_active else 'OFF'}\n"
                f"🗣️ loops `{len([k for k,v in self.ninja_spam_tasks.items() if v])}`\n"
                f"⛔ flooded `{af}/{len(self.ninja_clients)}`\n"
                f"⚡ `{Config.SPAM_GROUP_INTERVAL}s/group`\n"
                f"🎯 catch `{len(self.catch_ninja_ids)}`",
                parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/diag(?:@\w+)?$"))
        async def diag_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            now = time.monotonic()
            lines = ["🔍 **Diag**"]
            lines.append("\n**Ninjas:**")
            for c in self.ninja_clients[:15]:
                uid = getattr(c, "tg_user_id", "?")
                fl = max(0, self.flood_until.get(c, 0) - now)
                la = (now - self.spam_last_used.get(c, 0)
                      if self.spam_last_used.get(c) else -1)
                tag = "🎯" if uid in self.catch_ninja_ids else "  "
                lines.append(
                    f"  {tag}`{uid}` f=`{fl:.0f}` l=`{la:.0f}`")
            lines.append("\n**Groups:**")
            for cid in Config.SPAM_GROUPS:
                la = (now - self.spam_last_sent.get(cid, 0)
                      if self.spam_last_sent.get(cid) else -1)
                lines.append(f"  `{cid}` `{la:.1f}s`")
            lines.append("\n**State:**")
            lines.append(
                f"  pause `{max(0, self.spam_pause_until - now):.0f}s`")
            lines.append(f"  loops `{len(self._spam_loop_tasks)}`")
            lines.append(
                f"  last_send `{now - self._last_send_time:.0f}s`")
            await event.reply("\n".join(lines), parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/resetspam(?:@\w+)?$"))
        async def resetspam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            n = len(self.flood_until)
            self.flood_until.clear()
            self.spam_last_used.clear()
            self.spam_last_sent.clear()
            self.spam_pause_until = 0
            await event.reply(
                f"✅ Cleared `{n}` · `/spam` ပြန်ရိုက်ပါ",
                parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/panic(?:@\w+)?$"))
        async def panic_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await event.reply("🚨 Panic…")
            for k in list(self.ninja_spam_tasks.keys()):
                self.ninja_spam_tasks[k] = False
            for k in list(self._spam_loop_tasks.keys()):
                t = self._spam_loop_tasks.pop(k, None)
                if t and not t.done():
                    t.cancel()
            if self.start_spam_active:
                await self.stop_start_spam()
            self.flood_until.clear()
            self.spam_last_used.clear()
            self.spam_last_sent.clear()
            self.spam_pause_until = 0
            await asyncio.sleep(1)
            await self._warm_entity_cache()
            await self._warmup_hint_bot()
            await self._start_spam_loop(Config.SPAM_GROUPS)
            await event.reply("✅ Restarted.")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/spam(?:@\w+)?$"))
        async def spam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await self._start_spam_loop(Config.SPAM_GROUPS)
            await event.reply(
                f"🗣️ Spam ON · {len(Config.SPAM_GROUPS)} · "
                f"`{Config.SPAM_GROUP_INTERVAL}s/group`",
                parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^(ရပ်|/stop(?:@\w+)?)$"))
        async def stop_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            stopped = 0
            for k in list(self.ninja_spam_tasks.keys()):
                if self.ninja_spam_tasks.get(k):
                    self.ninja_spam_tasks[k] = False
                    stopped += 1
            await event.reply(f"🛑 {stopped}" if stopped else "ℹ️ none")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/go(?:@\w+)?$"))
        async def go_group(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not event.is_reply:
                return await event.reply("❌ Reply to invite.")
            r = await event.get_reply_message()
            if not r.text:
                return
            m = re.search(
                r"(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)", r.text)
            if not m:
                return await event.reply("❌ No link.")
            link = m.group(0)
            if "joinchat/" in link:
                h = link.split("joinchat/")[1].split("?")[0]
            elif "+" in link:
                h = link.split("+")[1].split("?")[0]
            else:
                return
            clients = self.ninja_clients.copy()
            await event.reply(f"⏳ Joining {len(clients)}…")
            success = 0
            for c in clients:
                try:
                    await asyncio.wait_for(
                        c(ImportChatInviteRequest(h)), timeout=20)
                    success += 1
                except errors.rpcerrorlist.UserAlreadyParticipantError:
                    success += 1
                except FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds, 30))
                except Exception:
                    pass
                await asyncio.sleep(0.3)
            await event.reply(f"✅ Joined · {success} clients")
            await self._warm_entity_cache()

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/status(?:@\w+)?$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            now = time.monotonic()
            af = sum(1 for c in self.ninja_clients
                     if self.flood_until.get(c, 0) > now)
            await event.reply(
                f"📊 **Status**\n"
                f"🤖 Pool `{len(self.ninja_clients)}`\n"
                f"🎯 Catch `{len(self.catch_ninja_ids)}`\n"
                f"⛔ Flooded `{af}`\n"
                f"🔄 Warmup `{'on' if self._warmup_task and not self._warmup_task.done() else 'off'}`\n"
                f"🐕 Watchdog `{'on' if self._watchdog_task and not self._watchdog_task.done() else 'off'}`\n"
                f"🗣️ Loops `{len(self._spam_loop_tasks)}`\n"
                f"⚡ `{Config.SPAM_GROUP_INTERVAL}s/group`",
                parse_mode="markdown")

    # ══════════════════════════════════════════════════════════════
    #  START / STOP
    # ══════════════════════════════════════════════════════════════
    async def start(self):
        # 🔥 Bot start with timeout
        try:
            await asyncio.wait_for(
                self.bot_client.start(bot_token=Config.BOT_TOKEN),
                timeout=Config.BOT_START_TIMEOUT)
        except asyncio.TimeoutError:
            logger.error("❌ Bot start TIMEOUT")
            raise
        me = await self.bot_client.get_me()
        self.bot_id = me.id
        logger.info(f"🤖 Bot: @{me.username} ({self.bot_id})")

        await self._load_catch_ids()
        await self.load_ninja_pools()
        await self._warm_entity_cache()
        await self._warmup_hint_bot()

        self._warmup_task = asyncio.create_task(
            self._periodic_warmup_loop())
        self._entity_warm_task = asyncio.create_task(
            self._periodic_entity_warm_loop())
        self._watchdog_task = asyncio.create_task(
            self._watchdog_loop())

        await self.bot_client.run_until_disconnected()

    async def stop(self):
        if self.start_spam_active:
            await self.stop_start_spam()
        for k in list(self.ninja_spam_tasks.keys()):
            self.ninja_spam_tasks[k] = False
        for t in [self._warmup_task, self._entity_warm_task,
                  self._watchdog_task]:
            if t and not t.done():
                t.cancel()
        try:
            if self.bot_client.is_connected():
                await self.bot_client.disconnect()
        except Exception:
            pass
        for c in self.ninja_clients:
            try:
                await c.disconnect()
            except Exception:
                pass
        await self.db.close()
        logger.info("🛑 Shutdown.")


# ══════════════════════════════════════════════════════════════════
#  ENTRY POINT — 🚨 Flask FIRST, then async
# ══════════════════════════════════════════════════════════════════
async def async_main():
    db = DatabaseManager(Config.MONGO_URI)
    await db.connect()
    bot = SovereignBot(db)
    try:
        await bot.start()
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        logger.info("Shutdown signal.")
    finally:
        await bot.stop()


def main():
    # ① Flask FIRST — Render port scan အောင်
    logger.info(f"🌐 Flask starting on port {Config.FLASK_PORT}…")
    threading.Thread(target=run_flask, daemon=True).start()
    time.sleep(2)  # port bind အောင်

    # ② Async work
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Interrupted.")


if __name__ == "__main__":
    main()
