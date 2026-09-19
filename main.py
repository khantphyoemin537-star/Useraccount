#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign System – ANY-GROUP TAUNT + PER-GROUP STOP + REPORT SYSTEM
- Taunt (ဖာသည်မသား) works in ANY group
- /talk per-group, "ရပ်" per-group stop
- /report, /reportbulk, /reportloop, /stopreport
- Ninja clients used in parallel for reporting
- 🥷 Auto Ninja for Spawn Bot 2 (Hint Bot) in -1003580630981
- 🎯 NEW: /startspam @BotUsername — Send /start to bot DM every 3 min
"""

import asyncio
import logging
import os
import random
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from html import escape as escape_html
from typing import Dict, List, Optional, Set, Tuple

import pytz
from flask import Flask
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, OperationFailure, DuplicateKeyError
from telethon import TelegramClient, events, errors
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsAdmins
from telethon.tl import functions as tl_funcs
from telethon.tl import types as tl_types

# ------------------------------------------------------------------
#  CONFIG
# ------------------------------------------------------------------
class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "7693106830"))
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true")
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "8824002850:AAGPtl7M0dw_gDVEZNxM3xxrYQazKvO5FKo")

    LEARNING_GROUP = int(os.getenv("LEARNING_GROUP", "-1003806830045"))
    SPAM_GROUPS = [
        -1004386559353,
        -1003977924930,
        -1004404645910,
        -1004485100583,
    ]

    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yangon"))
    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    SPAM_DELAY = 0.2
    TALK_DELAY = 1
    ADMIN_CACHE_TTL = 600
    MAX_RETRIES = 3

    # 🥷 AUTO NINJA (SPAWN BOT 2)
    SPAWN_BOT_2_ID = 8999491734
    SPAWN_GROUP_2 = -1003580630981
    NINJA_PICK_COUNT = 5
    NINJA_W_DELAY_MIN = 3.0
    NINJA_W_DELAY_MAX = 4.0
    NINJA_IGNORED_EMOJIS = ["🔵", "🟣", "🟠"]

    # 🎯 /START SPAM (Bot DM)
    START_SPAM_INTERVAL = 180        # 🔥 ၃ မိနစ် (180 စက္ကန့်)
    START_SPAM_MIN_DELAY = 5         # Ninja တစ်ခုချင်း စတင်ချိန် အနည်းဆုံး
    START_SPAM_MAX_DELAY = 15        # Ninja တစ်ခုချင်း စတင်ချိန် အများဆုံး
    START_SPAM_JITTER = 0.10         # ±10% jitter

SPAM_TEXT = """ @Imjustkidd , @GodMorgan,  @fucdHcမြတ​ြျ​​ေbsnsbsnkyrjsjsjsjssjsjjssjsjdjsjsjsjzjsjsjssnsnsnsndndndjsdjdndjdjdjdjdjsjdjdjdjdjdjsjsnsj """

# ------------------------------------------------------------------
#  REPORT REASONS
# ------------------------------------------------------------------
REPORT_REASONS = {
    "porn":      tl_types.InputReportReasonPornography(),
    "child":     tl_types.InputReportReasonChildAbuse(),
    "spam":      tl_types.InputReportReasonSpam(),
    "violence":  tl_types.InputReportReasonViolence(),
    "fake":      tl_types.InputReportReasonFake(),
    "drugs":     tl_types.InputReportReasonIllegalDrugs(),
    "personal":  tl_types.InputReportReasonPersonalDetails(),
    "copyright": tl_types.InputReportReasonCopyright(),
    "other":     tl_types.InputReportReasonOther(),
}

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("SovereignFast")

flask_app = Flask(__name__)

@flask_app.route("/")
def health_check() -> str:
    return "Sovereign Fast System is operational."

def run_flask() -> None:
    flask_app.run(host="0.0.0.0", port=Config.FLASK_PORT, threaded=True)

# ------------------------------------------------------------------
#  DATABASE
# ------------------------------------------------------------------
class DatabaseManager:
    def __init__(self, uri: str):
        self.uri = uri
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

    async def connect(self) -> None:
        for attempt in range(1, Config.MAX_RETRIES + 1):
            try:
                self.client = AsyncIOMotorClient(
                    self.uri,
                    tlsAllowInvalidCertificates=True,
                    serverSelectionTimeoutMS=5000,
                )
                await self.client.admin.command("ping")
                self.db = self.client["telegram_bot"]
                try:
                    await self.db.talk_phrases.create_index([("group_id", 1), ("text", 1)], unique=True, sparse=True)
                except Exception as e:
                    logger.warning(f"Index warning: {e}")
                logger.info("MongoDB connection established.")
                return
            except (ConnectionFailure, OperationFailure) as e:
                logger.warning(f"MongoDB attempt {attempt} failed: {e}")
                if attempt == Config.MAX_RETRIES:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def close(self) -> None:
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed.")

    @property
    def custom_filters(self): return self.db["custom_filters"]
    @property
    def allowed_users(self): return self.db["allowed_users"]
    @property
    def system_col(self): return self.db["system_col"]
    @property
    def ninja_col(self): return self.db["ninja_col"]
    @property
    def talk_phrases(self): return self.db["talk_phrases"]
    @property
    def taunt_targets(self): return self.db["taunt_targets"]
    @property
    def warmup_groups(self): return self.db["warmup_groups"]

# ------------------------------------------------------------------
#  MAIN BOT
# ------------------------------------------------------------------
class SovereignBot:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.bot_client = TelegramClient("bot_main_session", Config.API_ID, Config.API_HASH, flood_sleep_threshold=60)
        self.bot_id: Optional[int] = None

        self.ninja_clients: List[TelegramClient] = []
        self.ninja_names: List[str] = []
        self.ninja_ids: Set[int] = set()
        self.ninja_spam_tasks: Dict[Tuple[int, ...], bool] = {}

        self.delete_and_taunt_targets: Dict[int, Set[int]] = {}
        self.phrase_lists: Dict[int, List[str]] = {}
        self.phrase_indices: Dict[int, int] = {}

        self.chat_admin_cache: Dict[int, Tuple[List[TelegramClient], float]] = {}
        self.admin_cache_locks: Dict[int, asyncio.Lock] = {}

        self.sticker_spam_data = {}
        self.char_spam_data = {}
        self.admin_warned_sticker = set()
        self.admin_warned_char = set()
        self.admin_cache = {}

        self.talk_active_groups: Set[int] = set()
        self.talk_workers_by_group: Dict[int, List[asyncio.Task]] = {}
        self.talk_phrase_pool: List[str] = []
        self.talk_phrases_loaded = False

        self.auto_cleanup = False
        self.msg_queues: Dict[int, List[int]] = {}
        self.queue_locks: Dict[int, asyncio.Lock] = {}

        self.warmup_groups_cache: Set[int] = set()

        self.report_loop_tasks: Dict[Tuple[int, int], bool] = {}
        self.report_loop_reason: Dict[Tuple[int, int], str] = {}

        # 🥷 AUTO NINJA (SPAWN BOT 2) STATE
        self.ninja_spawn_marker = {"key": None, "selected": set()}
        self.ninja_spawn_tracker: Dict[Tuple[int, int], int] = {}
        self.ninja_latest_spawn: Dict[int, int] = {}
        self.ninja_w_msg_map: Dict[int, Set[int]] = {}

        # 🎯 /START SPAM STATE
        self.start_spam_tasks: Dict[int, asyncio.Task] = {}
        self.start_spam_target: Optional[str] = None
        self.start_spam_active: bool = False

        self._register_handlers()

    # ---------- TAUNT TARGETS ----------
    async def load_taunt_targets(self) -> None:
        async for doc in self.db.taunt_targets.find():
            chat_id = doc["chat_id"]
            target_ids = doc.get("target_ids", [])
            if target_ids:
                self.delete_and_taunt_targets[chat_id] = set(target_ids)

    async def _add_taunt_target(self, chat_id: int, target_id: int) -> None:
        if chat_id not in self.delete_and_taunt_targets:
            self.delete_and_taunt_targets[chat_id] = set()
        self.delete_and_taunt_targets[chat_id].add(target_id)
        await self.db.taunt_targets.update_one({"chat_id": chat_id}, {"$addToSet": {"target_ids": target_id}}, upsert=True)

    async def _remove_taunt_target(self, chat_id: int, target_id: int) -> None:
        if chat_id in self.delete_and_taunt_targets:
            self.delete_and_taunt_targets[chat_id].discard(target_id)
            if not self.delete_and_taunt_targets[chat_id]:
                del self.delete_and_taunt_targets[chat_id]
                await self.db.taunt_targets.delete_one({"chat_id": chat_id})
            else:
                await self.db.taunt_targets.update_one({"chat_id": chat_id}, {"$pull": {"target_ids": target_id}})

    async def _clear_taunt_targets(self, chat_id: int) -> None:
        if chat_id in self.delete_and_taunt_targets:
            del self.delete_and_taunt_targets[chat_id]
            await self.db.taunt_targets.delete_one({"chat_id": chat_id})

    # ---------- WARMUP ----------
    async def load_warmup_groups(self) -> None:
        async for doc in self.db.warmup_groups.find():
            gid = doc.get("chat_id")
            if gid:
                self.warmup_groups_cache.add(int(gid))
        logger.info(f"📋 Warmup groups loaded: {len(self.warmup_groups_cache)}")

    async def add_warmup_group(self, chat_id: int) -> None:
        self.warmup_groups_cache.add(chat_id)
        await self.db.warmup_groups.update_one({"chat_id": chat_id}, {"$set": {"chat_id": chat_id}}, upsert=True)

    async def remove_warmup_group(self, chat_id: int) -> None:
        self.warmup_groups_cache.discard(chat_id)
        await self.db.warmup_groups.delete_one({"chat_id": chat_id})

    # ---------- ADMIN CACHE ----------
    async def _scan_admin_clients(self, chat_id: int) -> List[TelegramClient]:
        async def check(client):
            try:
                perms = await client.get_permissions(chat_id, 'me')
                if perms and getattr(perms, 'is_admin', False):
                    return client
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except Exception:
                pass
            return None

        results = await asyncio.gather(*[check(c) for c in self.ninja_clients], return_exceptions=False)
        return [c for c in results if c is not None]

    async def _get_admin_clients(self, chat_id: int) -> List[TelegramClient]:
        now = time.time()
        cached = self.chat_admin_cache.get(chat_id)
        if cached and now < cached[1]:
            return cached[0]

        if chat_id not in self.admin_cache_locks:
            self.admin_cache_locks[chat_id] = asyncio.Lock()

        async with self.admin_cache_locks[chat_id]:
            cached = self.chat_admin_cache.get(chat_id)
            if cached and time.time() < cached[1]:
                return cached[0]

            admins = await self._scan_admin_clients(chat_id)
            self.chat_admin_cache[chat_id] = (admins, time.time() + Config.ADMIN_CACHE_TTL)
            logger.info(f"🔎 Admin scan for {chat_id}: {len(admins)}/{len(self.ninja_clients)}")
            return admins

    async def preload_admin_caches(self) -> None:
        targets = set(Config.SPAM_GROUPS) | self.warmup_groups_cache
        if not targets:
            return
        logger.info(f"⚡ Preloading admin caches for {len(targets)} groups...")
        await asyncio.gather(*[self._get_admin_clients(g) for g in targets], return_exceptions=True)
        logger.info("✅ Admin caches preloaded.")

    # --------------------------------------------------------------
    #  🎯 /START SPAM (Bot DM)
    # --------------------------------------------------------------
    async def _start_spam_worker(self, ninja_client: TelegramClient, ninja_id: int, target_bot: str):
        """Send /start to target bot every START_SPAM_INTERVAL seconds."""
        await asyncio.sleep(random.uniform(Config.START_SPAM_MIN_DELAY, Config.START_SPAM_MAX_DELAY))

        while self.start_spam_active and ninja_id in self.start_spam_tasks:
            try:
                await ninja_client.send_message(target_bot, "/start")
                logger.info(f"🎯 [{ninja_id}] → /start to @{target_bot}")
            except FloodWaitError as e:
                logger.warning(f"🎯 [{ninja_id}] flood wait {e.seconds}s")
                await asyncio.sleep(e.seconds + 1)
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"🎯 [{ninja_id}] /start failed (ignored): {e}")

            jitter = Config.START_SPAM_INTERVAL * random.uniform(-Config.START_SPAM_JITTER, Config.START_SPAM_JITTER)
            wait_time = max(30, Config.START_SPAM_INTERVAL + jitter)

            waited = 0
            while waited < wait_time and self.start_spam_active:
                await asyncio.sleep(5)
                waited += 5

    async def start_start_spam(self, target_bot: str) -> int:
        if self.start_spam_active:
            return 0
        if not self.ninja_clients:
            return 0

        self.start_spam_active = True
        self.start_spam_target = target_bot

        started = 0
        for client in self.ninja_clients:
            try:
                uid = getattr(client, 'tg_user_id', None)
                if not uid:
                    me = await client.get_me()
                    uid = me.id
                    client.tg_user_id = uid
                task = asyncio.create_task(
                    self._start_spam_worker(client, uid, target_bot)
                )
                self.start_spam_tasks[uid] = task
                started += 1
            except Exception as e:
                logger.warning(f"🎯 Failed to start spam worker for ninja: {e}")

        logger.info(f"🎯 /START SPAM started: {started} workers → @{target_bot}")
        return started

    async def stop_start_spam(self) -> int:
        if not self.start_spam_active:
            return 0
        self.start_spam_active = False

        stopped = 0
        for uid, task in list(self.start_spam_tasks.items()):
            if not task.done():
                task.cancel()
                stopped += 1
        self.start_spam_tasks.clear()
        self.start_spam_target = None

        logger.info(f"🎯 /START SPAM stopped: {stopped} workers")
        return stopped

    # ---------- 🥷 AUTO NINJA (SPAWN BOT 2) HANDLERS ----------
    async def _ninja_spawn_handler(self, event):
        """🥷 Detect spawn from Spawn Bot 2 in SPAWN_GROUP_2 and pick 5 ninjas."""
        try:
            uid = getattr(event.client, 'tg_user_id', None)
            if not uid:
                return

            if event.chat_id != Config.SPAWN_GROUP_2:
                return

            text_raw = event.text or ""
            if not text_raw:
                try:
                    if event.message and event.message.message:
                        text_raw = event.message.message
                except Exception:
                    pass
            if not text_raw:
                return

            upper = text_raw.upper()
            if not ("A CHARACTER HAS SPAWNED" in upper or "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ" in text_raw):
                return

            if any(e in text_raw for e in Config.NINJA_IGNORED_EMOJIS):
                logger.info(f"🥷 [skip emoji] ninja {uid}")
                return

            spawn_key = f"{event.chat_id}:{event.message.id}"

            if self.ninja_spawn_marker.get("key") != spawn_key:
                avail = list(self.ninja_ids)
                if not avail:
                    return
                if len(avail) <= Config.NINJA_PICK_COUNT:
                    picked = set(avail)
                else:
                    picked = set(random.sample(avail, Config.NINJA_PICK_COUNT))
                self.ninja_spawn_marker["key"] = spawn_key
                self.ninja_spawn_marker["selected"] = picked
                logger.info(f"🥷 New spawn → picked {len(picked)}/{len(avail)} ninjas")

            if uid not in self.ninja_spawn_marker["selected"]:
                return

            delay = random.uniform(Config.NINJA_W_DELAY_MIN, Config.NINJA_W_DELAY_MAX)
            await asyncio.sleep(delay)

            try:
                reply = await event.message.reply("/w")
                self.ninja_spawn_tracker[(uid, reply.id)] = event.chat_id
                self.ninja_latest_spawn[uid] = event.chat_id
                self.ninja_w_msg_map.setdefault(uid, set()).add(reply.id)
                logger.info(f"🥷 Ninja {uid} → /w (msg={reply.id}, delay={delay:.2f}s)")
            except Exception as e:
                logger.warning(f"🥷 Ninja {uid} /w failed (ignored): {e}")
        except Exception as e:
            logger.warning(f"🥷 spawn handler error (ignored): {e}")

    async def _ninja_hint_handler(self, event):
        """🥷 Read /catch from Spawn Bot 2 and reply in spawn group."""
        try:
            uid = getattr(event.client, 'tg_user_id', None)
            if not uid:
                return
            if event.chat_id != Config.SPAWN_GROUP_2:
                return
            if event.sender_id != Config.SPAWN_BOT_2_ID:
                return
            if not event.reply_to_msg_id:
                return

            if (uid, event.reply_to_msg_id) not in self.ninja_spawn_tracker:
                return

            text_raw = event.text or ""
            if not text_raw:
                try:
                    if event.message and event.message.message:
                        text_raw = event.message.message
                except Exception:
                    pass
            if not text_raw:
                return

            m = re.search(r"(/catch(?:@\w+)?\s+[^\n]+)", text_raw)
            if not m:
                return
            catch_cmd = m.group(1).strip(" `\n\r")

            target_group = self.ninja_spawn_tracker.get((uid, event.reply_to_msg_id))
            if not target_group:
                target_group = self.ninja_latest_spawn.get(uid)
            if not target_group:
                return

            try:
                await event.client.send_message(target_group, catch_cmd)
                logger.info(f"🥷 Ninja {uid} → {catch_cmd}")
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds, 30))
            except Exception as e:
                logger.warning(f"🥷 Ninja {uid} catch send failed (ignored): {e}")
        except Exception as e:
            logger.warning(f"🥷 hint handler error (ignored): {e}")

    def _register_ninja_handlers(self, client: TelegramClient) -> None:
        client.add_event_handler(
            self._ninja_spawn_handler,
            events.NewMessage(from_users=Config.SPAWN_BOT_2_ID),
        )
        client.add_event_handler(
            self._ninja_hint_handler,
            events.NewMessage(chats=Config.SPAWN_GROUP_2),
        )

    # ---------- NINJA POOL ----------
    async def load_ninja_pools(self) -> None:
        for client in self.ninja_clients:
            try:
                if client.is_connected():
                    await client.disconnect()
            except: pass
        self.ninja_clients.clear(); self.ninja_names.clear(); self.ninja_ids.clear()

        async for doc in self.db.ninja_col.find():
            session_str = doc.get("session")
            if not session_str:
                continue
            try:
                client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
                await client.start()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    client.tg_user_id = me.id
                    self.ninja_clients.append(client)
                    name = doc.get("name", f"Ninja-{len(self.ninja_clients)}")
                    self.ninja_names.append(name)
                    self.ninja_ids.add(me.id)
                    self._register_ninja_handlers(client)
                    logger.info(f"✅ Ninja – '{name}' loaded: @{me.username}")
                else:
                    await client.disconnect()
            except Exception as e:
                logger.error(f"❌ Ninja load failed: {e}")
        logger.info(f"🚀 Ninja Pool ready: {len(self.ninja_clients)} clients.")

    # ---------- HELPERS ----------
    async def check_admin(self, chat_id: int, user_id: int) -> bool:
        if user_id == Config.OWNER_ID:
            return True
        now = time.time()
        if chat_id in self.admin_cache and now < self.admin_cache[chat_id]["expiry"]:
            return user_id in self.admin_cache[chat_id]["ids"]
        try:
            admins = await self.bot_client(GetParticipantsRequest(channel=chat_id, filter=ChannelParticipantsAdmins(), offset=0, limit=200, hash=0))
            admin_ids = {p.user_id for p in admins.participants}
            self.admin_cache[chat_id] = {"ids": admin_ids, "expiry": time.time() + 300}
            return user_id in admin_ids
        except Exception as e:
            logger.error(f"Admin cache error: {e}")
            return False

    def format_mention(self, user_id: int, name: str) -> str:
        return f"<a href='tg://user?id={user_id}'>{escape_html(name)}</a>"

    def strip_html(self, text: str) -> str:
        if not text: return ""
        return re.sub(r'<[^>]+>', '', text)

    async def is_allowed(self, user_id: int) -> bool:
        if user_id == Config.OWNER_ID:
            return True
        doc = await self.db.allowed_users.find_one({"user_id": user_id})
        return doc is not None

    def bq(self, text: str) -> str:
        return f"<blockquote><b>{text}</b></blockquote>"

    # ---------- PHRASES ----------
    async def fetch_phrases(self) -> List[str]:
        doc = await self.db.system_col.find_one({"key": "shadow_taunts"})
        if doc and doc.get("value"):
            return list(doc["value"])
        return ["မင်းရဲ့စကားတွေ ငါမှတ်ထားတယ်"]

    async def get_next_phrase(self, chat_id: int) -> str:
        phrases = self.phrase_lists.get(chat_id)
        if not phrases:
            phrases = await self.fetch_phrases()
            random.shuffle(phrases)
            self.phrase_lists[chat_id] = phrases
            self.phrase_indices[chat_id] = 0
        idx = self.phrase_indices[chat_id]
        phrase = phrases[idx]
        idx = (idx + 1) % len(phrases)
        self.phrase_indices[chat_id] = idx
        return phrase

    # ---------- TALK ----------
    async def _load_talk_phrases(self):
        if self.talk_phrases_loaded and self.talk_phrase_pool:
            return
        docs = await self.db.talk_phrases.find({"group_id": 0}).to_list(length=10000)
        if docs:
            self.talk_phrase_pool = [d.get("text") for d in docs if d.get("text")]
        if not self.talk_phrase_pool:
            self.talk_phrase_pool = await self.fetch_phrases()
        random.shuffle(self.talk_phrase_pool)
        self.talk_phrases_loaded = True

    async def _talk_worker(self, client: TelegramClient, group_id: int):
        await asyncio.sleep(random.uniform(0, Config.TALK_DELAY))
        while group_id in self.talk_active_groups:
            try:
                if not self.talk_phrase_pool:
                    self.talk_phrases_loaded = False
                    await self._load_talk_phrases()
                    if not self.talk_phrase_pool:
                        await asyncio.sleep(1)
                        continue
                phrase = random.choice(self.talk_phrase_pool)
                await client.send_message(group_id, phrase)
                await asyncio.sleep(Config.TALK_DELAY)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Talk worker {group_id}: {e}")
                await asyncio.sleep(1)

    async def start_talk_group(self, group_id: int) -> bool:
        if group_id in self.talk_active_groups:
            return False
        if not self.ninja_clients:
            return False
        await self._load_talk_phrases()
        if not self.talk_phrase_pool:
            return False

        self.talk_active_groups.add(group_id)
        workers = [asyncio.create_task(self._talk_worker(c, group_id)) for c in self.ninja_clients]
        self.talk_workers_by_group[group_id] = workers
        logger.info(f"🚀 TALK started for {group_id} ({len(self.ninja_clients)} workers)")
        return True

    async def stop_talk_group(self, group_id: int) -> bool:
        if group_id not in self.talk_active_groups:
            return False
        self.talk_active_groups.discard(group_id)
        workers = self.talk_workers_by_group.pop(group_id, [])
        for t in workers:
            if not t.done():
                t.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        logger.info(f"🛑 TALK stopped for {group_id}")
        return True

    async def start_talk_all(self) -> List[int]:
        started = []
        for g in Config.SPAM_GROUPS:
            if await self.start_talk_group(g):
                started.append(g)
        return started

    async def stop_talk_all(self) -> int:
        count = 0
        for g in list(self.talk_active_groups):
            if await self.stop_talk_group(g):
                count += 1
        return count

    # ---------- AUTO CLEANUP ----------
    async def _handle_message_sent(self, chat_id: int, msg_id: Optional[int]):
        if not self.auto_cleanup or chat_id == Config.LEARNING_GROUP or msg_id is None:
            return
        if chat_id not in self.queue_locks:
            self.queue_locks[chat_id] = asyncio.Lock()
        async with self.queue_locks[chat_id]:
            if chat_id not in self.msg_queues:
                self.msg_queues[chat_id] = []
            self.msg_queues[chat_id].append(msg_id)
            if len(self.msg_queues[chat_id]) >= 100:
                ids = self.msg_queues[chat_id].copy()
                self.msg_queues[chat_id].clear()
                try:
                    await self.bot_client.delete_messages(chat_id, ids)
                except FloodWaitError as e:
                    asyncio.create_task(self._retry_delete_after(chat_id, ids, e.seconds))
                except Exception as e:
                    logger.error(f"Delete failed: {e}")

    async def _retry_delete_after(self, chat_id: int, ids: List[int], delay: int):
        await asyncio.sleep(delay + 1)
        try:
            await self.bot_client.delete_messages(chat_id, ids)
        except Exception as e:
            logger.error(f"Retry delete failed: {e}")

    # ---------- SPAM ----------
    async def _start_spam_loop(self, chat_ids: List[int]) -> None:
        key = tuple(sorted(chat_ids))
        if self.ninja_spam_tasks.get(key, False):
            return
        self.ninja_spam_tasks[key] = True
        if not self.ninja_clients:
            return

        flood_until: Dict[TelegramClient, datetime] = {}
        lock = asyncio.Lock()

        async def send(client, chat_id):
            async with lock:
                if client in flood_until and flood_until[client] > datetime.now():
                    return
            try:
                sent = await client.send_message(chat_id, SPAM_TEXT)
                await self._handle_message_sent(chat_id, sent.id)
            except FloodWaitError as e:
                async with lock:
                    flood_until[client] = datetime.now() + timedelta(seconds=e.seconds + 1)
            except Exception as e:
                logger.error(f"Spam error: {e}")

        async def loop():
            round_num = 0
            while self.ninja_spam_tasks.get(key, False):
                round_num += 1
                tasks = []
                for chat_id in chat_ids:
                    client = None
                    for _ in range(3):
                        c = random.choice(self.ninja_clients)
                        async with lock:
                            if c not in flood_until or flood_until[c] < datetime.now():
                                client = c
                                break
                    if client is None:
                        await asyncio.sleep(0.3)
                        continue
                    tasks.append(send(client, chat_id))
                if tasks:
                    await asyncio.gather(*tasks)
                await asyncio.sleep(0.05)
                if round_num % 100 == 0:
                    logger.info(f"Spam round {round_num}")
            logger.info(f"🛑 Spam stopped for {len(chat_ids)} groups")

        asyncio.create_task(loop())

    # ---------- SPAM FILTERS ----------
    async def sticker_spam_filter(self, event):
        if not event.sticker or event.is_private: return
        if event.sender_id == self.bot_id or event.sender_id in self.ninja_ids: return
        sid, cid = event.sender_id, event.chat_id
        now = datetime.now()
        d = self.sticker_spam_data.setdefault(sid, {"times": [], "ids": []})
        d["times"].append(now); d["ids"].append(event.id)
        cutoff = now - timedelta(seconds=60)
        valid = [(t, i) for t, i in zip(d["times"], d["ids"]) if t > cutoff]
        d["times"] = [x[0] for x in valid]; d["ids"] = [x[1] for x in valid]
        if len(d["times"]) >= 6:
            try:
                await self.bot_client.delete_messages(cid, d["ids"])
                if not await self.check_admin(cid, sid):
                    await self.bot_client.edit_permissions(cid, sid, send_stickers=False)
                del self.sticker_spam_data[sid]
            except Exception as e: logger.error(f"Sticker filter: {e}")
            return
        if len(d["times"]) >= 3 and (d["times"][-1] - d["times"][-3]).total_seconds() <= 1.0:
            try: await event.delete()
            except: pass

    async def short_text_spam_filter(self, event):
        if event.is_private or not event.text: return
        if event.sender_id == self.bot_id or event.sender_id in self.ninja_ids: return
        if len(event.text.strip()) > 3: return
        sid, cid = event.sender_id, event.chat_id
        now = datetime.now()
        d = self.char_spam_data.setdefault(sid, {"times": [], "ids": []})
        d["times"].append(now); d["ids"].append(event.id)
        cutoff = now - timedelta(seconds=60)
        valid = [(t, i) for t, i in zip(d["times"], d["ids"]) if t > cutoff]
        d["times"] = [x[0] for x in valid]; d["ids"] = [x[1] for x in valid]
        if len(d["times"]) >= 6:
            try:
                await self.bot_client.delete_messages(cid, d["ids"])
                if not await self.check_admin(cid, sid):
                    await self.bot_client.edit_permissions(cid, sid, until_date=datetime.now() + timedelta(minutes=5), send_messages=False)
                del self.char_spam_data[sid]
            except Exception as e: logger.error(f"Short text filter: {e}")

    async def bio_link_filter(self, event):
        if event.is_private or not event.text: return
        if event.sender_id in (Config.OWNER_ID, self.bot_id) or event.sender_id in self.ninja_ids:
            return
        if re.search(r'(https?://\S+|www\.\S+|t\.me/\S+)', event.text):
            if not await self.check_admin(event.chat_id, event.sender_id):
                try:
                    await event.delete()
                    sender = await event.get_sender()
                    m = self.format_mention(event.sender_id, sender.first_name or "User")
                    await event.respond(self.bq(f"🤺 {m}, links not allowed!"), parse_mode='html')
                except: pass

    FORBIDDEN_SCRIPTS = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff\u0e00-\u0e7f\u0600-\u06ff\uac00-\ud7af]')

    async def language_filter(self, event):
        if event.is_private or not event.text: return
        if event.sender_id in (Config.OWNER_ID, self.bot_id) or event.sender_id in self.ninja_ids:
            return
        if event.chat_id == Config.LEARNING_GROUP and not await self.check_admin(event.chat_id, event.sender_id):
            if self.FORBIDDEN_SCRIPTS.search(event.text):
                try: await event.delete()
                except: pass

    # ---------- TAUNT EXECUTION ----------
    async def _taunt_user(self, chat_id: int, target_id: int, msg_id: int, target_name: str = "Target"):
        admins = await self._get_admin_clients(chat_id)
        if not admins:
            return
        client = random.choice(admins)

        try:
            await client.delete_messages(chat_id, [msg_id])
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)
        except Exception:
            pass

        mention = self.format_mention(target_id, target_name)
        phrase = await self.get_next_phrase(chat_id)

        try:
            await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            logger.error(f"Taunt send error: {e}")

    # ---------- REPORT EXECUTION ----------
    async def _report_message(
        self,
        chat_id: int,
        msg_id: int,
        target_id: int,
        reason_key: str = "porn",
    ) -> Tuple[int, int]:
        reason = REPORT_REASONS.get(reason_key, tl_types.InputReportReasonSpam())

        ok = 0
        fail = 0
        lock = asyncio.Lock()
        flood_until: Dict[TelegramClient, float] = {}

        async def do_one(client: TelegramClient):
            nonlocal ok, fail
            try:
                wait = flood_until.get(client, 0) - time.time()
                if wait > 0:
                    await asyncio.sleep(wait)

                try:
                    await client(tl_funcs.messages.ReportRequest(
                        peer=chat_id,
                        id=[msg_id],
                        reason=reason,
                    ))
                except FloodWaitError as e:
                    flood_until[client] = time.time() + e.seconds + 1
                    raise

                try:
                    await client(tl_funcs.account.ReportPeerRequest(
                        peer=target_id,
                        reason=reason,
                        message="",
                    ))
                except Exception:
                    pass

                async with lock:
                    ok += 1
            except FloodWaitError as e:
                async with lock:
                    fail += 1
                await asyncio.sleep(min(e.seconds, 30))
            except Exception as e:
                logger.error(f"Report error on {target_id}: {e}")
                async with lock:
                    fail += 1

        await asyncio.gather(
            *[do_one(c) for c in self.ninja_clients],
            return_exceptions=True,
        )
        return ok, fail

    # --------------------------------------------------------------
    #  COMMAND HANDLERS
    # --------------------------------------------------------------
    def _register_handlers(self):

        # ===== ALLOW SYSTEM =====
        @self.bot_client.on(events.NewMessage(pattern=r"^/addallow(?:@\w+)?$"))
        async def add_allow(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            reply = await event.get_reply_message()
            if not reply:
                return await event.reply("❓ Reply to a user.")
            user = await reply.get_sender()
            if not user:
                return await event.reply("❌ User not found.")
            await self.db.allowed_users.update_one({"user_id": user.id}, {"$set": {"name": user.first_name or "Unnamed"}}, upsert=True)
            await event.reply(f"✅ {self.format_mention(user.id, user.first_name or 'User')} allowed.", parse_mode='html')

        @self.bot_client.on(events.NewMessage(pattern=r"^/allowlist(?:@\w+)?$"))
        async def allow_list(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            users = await self.db.allowed_users.find().to_list(length=None)
            if not users:
                return await event.reply("📭 Empty.")
            lines = [f"• {self.format_mention(u['user_id'], u.get('name','?'))} (<code>{u['user_id']}</code>)" for u in users]
            await event.reply("<b>👑 Allowed Users</b>\n\n" + "\n".join(lines), parse_mode="html")

        @self.bot_client.on(events.NewMessage(pattern=r"^/removeallow(?:@\w+)?\s+(\d+)$"))
        async def remove_allow(event):
            if event.sender_id != Config.OWNER_ID: return
            tid = int(event.pattern_match.group(1))
            r = await self.db.allowed_users.delete_one({"user_id": tid})
            await event.reply("✅ Removed" if r.deleted_count else "⚠️ Not found")

        # ===== /del =====
        @self.bot_client.on(events.NewMessage(pattern=r"^/del(?:@\w+)?$"))
        async def del_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            self.auto_cleanup = not self.auto_cleanup
            await event.reply(f"🔄 Auto-Cleanup: **{'ON' if self.auto_cleanup else 'OFF'}**", parse_mode='markdown')

        # ===== WARMUP =====
        @self.bot_client.on(events.NewMessage(pattern=r"^/warmup(?:@\w+)?$"))
        async def warmup_cmd(event):
            if not await self.is_allowed(event.sender_id):
                return await event.reply("⛔ Not allowed.")
            chat_id = event.chat_id
            if chat_id == event.sender_id:
                return await event.reply("⚠️ Use this inside a group.")
            await event.reply("⏳ Scanning admins...")
            admins = await self._get_admin_clients(chat_id)
            await self.add_warmup_group(chat_id)
            if admins:
                await event.reply(f"✅ Warmup OK. {len(admins)}/{len(self.ninja_clients)} ninja admin in this group.\nGroup saved for auto-reload.")
            else:
                await event.reply(f"⚠️ No ninja admin in this group. Group saved but taunt won't work until a ninja becomes admin.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/unwarmup(?:@\w+)?$"))
        async def unwarmup_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            chat_id = event.chat_id
            await self.remove_warmup_group(chat_id)
            await event.reply("✅ Removed from warmup list.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/listwarmup(?:@\w+)?$"))
        async def list_warmup(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            if not self.warmup_groups_cache:
                return await event.reply("📭 No warmup groups.")
            lines = ["📋 **Warmup Groups**"]
            for gid in self.warmup_groups_cache:
                admins = self.chat_admin_cache.get(gid, (None, 0))[0]
                count = len(admins) if admins is not None else "?"
                lines.append(f"  • `{gid}` — admins: {count}")
            await event.reply("\n".join(lines), parse_mode='markdown')

        # ===== SPAM =====
        @self.bot_client.on(events.NewMessage(pattern=r"^/spam(?:@\w+)?$"))
        async def spam_cmd(event):
            if not await self.is_allowed(event.sender_id): return
            groups = Config.SPAM_GROUPS
            await self._start_spam_loop(groups)
            await event.reply(f"🗣️ Spam started on {len(groups)} groups.")

        # ===== 🎯 /START SPAM =====
        @self.bot_client.on(events.NewMessage(pattern=r"^/startspam(?:@\w+)?(?:\s+(@?\w+))?$"))
        async def startspam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            arg = event.pattern_match.group(1)
            if not arg:
                return await event.reply(
                    "⚠️ **Usage:** `/startspam @BotUsername`\n"
                    "or `/startspam BotUsername`"
                )
            target = arg.lstrip("@").strip()
            if not target:
                return await event.reply("❌ Invalid username.")

            if self.start_spam_active:
                return await event.reply(
                    f"⚠️ Already running → @{self.start_spam_target}\n"
                    f"Send `/stopspam` to stop first."
                )

            if not self.ninja_clients:
                return await event.reply("❌ Ninja pool is empty.")

            n = await self.start_start_spam(target)
            await event.reply(
                f"🎯 **/START SPAM ON**\n"
                f"🤖 Target: @{target}\n"
                f"👥 Workers: `{n}`\n"
                f"⏱️ Interval: `{Config.START_SPAM_INTERVAL}s` (~{Config.START_SPAM_INTERVAL//60} min)\n"
                f"💡 Send `/stopspam` to stop."
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/stopspam(?:@\w+)?$"))
        async def stopspam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            if not self.start_spam_active:
                return await event.reply("ℹ️ Not running.")
            target = self.start_spam_target
            n = await self.stop_start_spam()
            await event.reply(f"🛑 **/START SPAM OFF**\n🤖 Target: @{target}\n👥 Stopped: `{n}`")

        @self.bot_client.on(events.NewMessage(pattern=r"^/spamstatus(?:@\w+)?$"))
        async def spamstatus_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            if self.start_spam_active:
                await event.reply(
                    f"🎯 **/START SPAM Status**\n"
                    f"✅ Status: **ON**\n"
                    f"🤖 Target: @{self.start_spam_target}\n"
                    f"👥 Active workers: `{len(self.start_spam_tasks)}`\n"
                    f"⏱️ Interval: `{Config.START_SPAM_INTERVAL}s`"
                )
            else:
                await event.reply("🎯 **/START SPAM Status**\n❌ Status: **OFF**")

        # ===== TAUNT =====
        @self.bot_client.on(events.NewMessage(pattern=r"^ဖာသည်မသား$"))
        async def taunt(event):
            if not await self.is_allowed(event.sender_id): return
            try: await event.delete()
            except: pass

            reply = await event.get_reply_message()
            if not reply:
                return await event.reply("❌ Reply to a target.")
            target = await reply.get_sender()
            if not target or target.id == Config.OWNER_ID: return

            chat_id = event.chat_id
            target_id = target.id
            target_name = target.first_name or "Target"

            admins = await self._get_admin_clients(chat_id)
            if not admins:
                return await event.reply("⚠️ No ninja is admin in this chat. Taunt won't work here.")

            mention = self.format_mention(target_id, target_name)

            try:
                await self.bot_client.delete_messages(chat_id, [reply.id])
            except: pass

            await self._add_taunt_target(chat_id, target_id)

            client = random.choice(admins)
            phrase = await self.get_next_phrase(chat_id)
            try:
                await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                logger.error(f"Taunt send failed: {e}")

            await event.reply(f"✅ Taunt enabled for {mention} ({len(admins)} admin).", parse_mode='html')

        @self.bot_client.on(events.NewMessage(pattern=r"^/remove_taunt(?:@\w+)?(?:\s+(\d+))?$"))
        async def remove_taunt(event):
            if not await self.is_allowed(event.sender_id): return
            cid = event.chat_id
            tid = event.pattern_match.group(1)
            if tid:
                await self._remove_taunt_target(cid, int(tid))
                await event.reply(f"✅ Removed {tid}")
            elif event.is_reply:
                reply = await event.get_reply_message()
                target = await reply.get_sender()
                await self._remove_taunt_target(cid, target.id)
                await event.reply(f"✅ Removed {self.format_mention(target.id, target.first_name or '?')}", parse_mode='html')

        @self.bot_client.on(events.NewMessage(pattern=r"^/clear_taunts(?:@\w+)?(?:\s+(-?\d+))?$"))
        async def clear_taunts(event):
            if not await self.is_allowed(event.sender_id): return
            tid = event.pattern_match.group(1)
            cid = int(tid) if tid else event.chat_id
            await self._clear_taunt_targets(cid)
            await event.reply("🧹 Cleared.")

        # ===== REPORT SYSTEM =====
        @self.bot_client.on(events.NewMessage(pattern=r"^/report(?:@\w+)?(?:\s+(\w+))?$"))
        async def report_cmd(event):
            if not await self.is_allowed(event.sender_id):
                return
            reason = (event.pattern_match.group(1) or "porn").lower()
            if reason not in REPORT_REASONS:
                keys = ", ".join(f"`{k}`" for k in REPORT_REASONS.keys())
                return await event.reply(f"❌ Unknown reason.\nOptions: {keys}", parse_mode='markdown')

            reply = await event.get_reply_message()
            if not reply:
                return await event.reply("❌ Reply to a target message.")

            chat_id = event.chat_id
            msg_id = reply.id
            target_id = reply.sender_id
            target_name = "Target"
            try:
                s = await reply.get_sender()
                if s:
                    target_name = s.first_name or "Target"
            except Exception:
                pass

            if target_id == Config.OWNER_ID:
                return await event.reply("❌ Cannot report Owner.")

            mention = self.format_mention(target_id, target_name)
            status = await event.reply(
                f"⏳ Reporting {mention} …\n"
                f"🎯 Target: `{target_id}`\n"
                f"📋 Reason: `{reason}`\n"
                f"👥 Accounts: **{len(self.ninja_clients)}**",
                parse_mode='html',
            )

            ok, fail = await self._report_message(chat_id, msg_id, target_id, reason)

            await status.edit(
                f"✅ **Report complete**\n"
                f"🎯 Target: {mention} (`{target_id}`)\n"
                f"📋 Reason: `{reason}`\n"
                f"✔️ Success: **{ok}**\n"
                f"✖️ Failed: **{fail}**",
                parse_mode='html',
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/reportbulk(?:@\w+)?(?:\s+(\d+))?(?:\s+(\w+))?$"))
        async def report_bulk_cmd(event):
            if not await self.is_allowed(event.sender_id):
                return
            count = int(event.pattern_match.group(1) or 10)
            reason = (event.pattern_match.group(2) or "porn").lower()
            if reason not in REPORT_REASONS:
                return await event.reply("❌ Unknown reason.")
            if count < 1 or count > 100:
                return await event.reply("❌ Count must be 1–100.")

            reply = await event.get_reply_message()
            if not reply:
                return await event.reply("❌ Reply to a message from the target.")

            chat_id = event.chat_id
            target_id = reply.sender_id
            if target_id == Config.OWNER_ID:
                return await event.reply("❌ Cannot report Owner.")

            status = await event.reply(
                f"⏳ Scanning last **{count}** messages from `{target_id}` …",
                parse_mode='markdown',
            )

            reader = None
            for c in self.ninja_clients:
                try:
                    await c.get_me()
                    reader = c
                    break
                except Exception:
                    continue
            if reader is None:
                return await status.edit("❌ No ninja available.")

            msg_ids: List[int] = []
            try:
                async for m in reader.iter_messages(chat_id, from_user=target_id, limit=count):
                    msg_ids.append(m.id)
            except Exception as e:
                return await status.edit(f"❌ Fetch failed: {e}")

            if not msg_ids:
                return await status.edit("❌ No messages found.")

            await status.edit(
                f"⏳ Reporting **{len(msg_ids)}** messages × **{len(self.ninja_clients)}** accounts …",
                parse_mode='markdown',
            )

            total_ok = 0
            total_fail = 0
            for mid in msg_ids:
                ok, fail = await self._report_message(chat_id, mid, target_id, reason)
                total_ok += ok
                total_fail += fail
                await asyncio.sleep(0.5)

            await status.edit(
                f"✅ **Bulk report done**\n"
                f"🎯 Target: `{target_id}`\n"
                f"📩 Messages: **{len(msg_ids)}**\n"
                f"📋 Reason: `{reason}`\n"
                f"✔️ Total success: **{total_ok}**\n"
                f"✖️ Total failed: **{total_fail}**",
                parse_mode='markdown',
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/reportloop(?:@\w+)?(?:\s+(\w+))?$"))
        async def report_loop_cmd(event):
            if not await self.is_allowed(event.sender_id):
                return
            reason = (event.pattern_match.group(1) or "porn").lower()
            if reason not in REPORT_REASONS:
                return await event.reply("❌ Unknown reason.")

            reply = await event.get_reply_message()
            if not reply:
                return await event.reply("❌ Reply to a message from the target.")

            chat_id = event.chat_id
            target_id = reply.sender_id
            if target_id == Config.OWNER_ID:
                return await event.reply("❌ Cannot report Owner.")

            key = (chat_id, target_id)
            if self.report_loop_tasks.get(key):
                return await event.reply("⚠️ Already looping for this target.")

            self.report_loop_tasks[key] = True
            self.report_loop_reason[key] = reason

            async def loop():
                logger.info(f"🔁 Report loop started: {target_id} in {chat_id} ({reason})")
                while self.report_loop_tasks.get(key, False):
                    try:
                        reader = None
                        for c in self.ninja_clients:
                            try:
                                await c.get_me()
                                reader = c
                                break
                            except Exception:
                                continue
                        if reader is None:
                            await asyncio.sleep(5)
                            continue

                        async for m in reader.iter_messages(chat_id, from_user=target_id, limit=5):
                            if not self.report_loop_tasks.get(key, False):
                                break
                            await self._report_message(chat_id, m.id, target_id, reason)
                            await asyncio.sleep(1)

                        await asyncio.sleep(3)
                    except Exception as e:
                        logger.error(f"Report loop error: {e}")
                        await asyncio.sleep(5)
                logger.info(f"🔁 Report loop stopped: {target_id}")

            asyncio.create_task(loop())

            await event.reply(
                f"🔁 **Report loop ON**\n"
                f"🎯 Target: `{target_id}`\n"
                f"📋 Reason: `{reason}`\n"
                f"💡 Send `ရပ်` in this chat to stop.",
                parse_mode='markdown',
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/stopreport(?:@\w+)?$"))
        async def stopreport_cmd(event):
            if event.sender_id != Config.OWNER_ID and not await self.is_allowed(event.sender_id):
                return
            cid = event.chat_id
            stopped = 0
            for key in list(self.report_loop_tasks.keys()):
                if key[0] == cid or event.sender_id == Config.OWNER_ID:
                    self.report_loop_tasks[key] = False
                    self.report_loop_reason.pop(key, None)
                    stopped += 1
            await event.reply(f"🛑 Stopped {stopped} report loop(s).")

        # ===== STOP (PER-GROUP) =====
        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop(?:@\w+)?)$"))
        async def stop_cmd(event):
            if not await self.is_allowed(event.sender_id):
                return
            chat_id = event.chat_id
            stopped_here = False

            for key in list(self.ninja_spam_tasks.keys()):
                if chat_id in key:
                    self.ninja_spam_tasks[key] = False
                    stopped_here = True

            for key in list(self.report_loop_tasks.keys()):
                if key[0] == chat_id or event.sender_id == Config.OWNER_ID:
                    self.report_loop_tasks[key] = False
                    self.report_loop_reason.pop(key, None)
                    stopped_here = True

            if chat_id in Config.SPAM_GROUPS:
                if chat_id in self.talk_active_groups:
                    await self.stop_talk_group(chat_id)
                    stopped_here = True
            else:
                if event.sender_id == Config.OWNER_ID and self.talk_active_groups:
                    await self.stop_talk_all()
                    stopped_here = True

            remaining = sorted(self.talk_active_groups)
            if stopped_here:
                tail = f"\n▶️ Still running in {len(remaining)} group(s)" if remaining else "\n▶️ No groups running."
                await event.reply(f"🛑 Stopped in this chat.{tail}")
            else:
                await event.reply("ℹ️ Nothing to stop here.")

        # ===== TALK =====
        @self.bot_client.on(events.NewMessage(pattern=r"^/talk(?:@\w+)?$"))
        async def talk_cmd(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id

            if chat_id in Config.SPAM_GROUPS:
                if chat_id in self.talk_active_groups:
                    return await event.reply("⚠️ Talk already running in this group.")
                ok = await self.start_talk_group(chat_id)
                if ok:
                    await event.reply(f"🗣️ Talk started here ({len(self.ninja_clients)} clients).")
                else:
                    await event.reply("❌ Cannot start.")
            else:
                if event.sender_id != Config.OWNER_ID:
                    return await event.reply("⛔ Only Owner can start all groups from here.")
                started = await self.start_talk_all()
                if started:
                    await event.reply(f"🗣️ Talk started on {len(started)} group(s).")
                else:
                    await event.reply("❌ No groups started.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/stoptalk(?:@\w+)?$"))
        async def stoptalk_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            if not self.talk_active_groups:
                return await event.reply("ℹ️ Not running.")
            n = await self.stop_talk_all()
            await event.reply(f"🛑 All talk stopped ({n} groups).")

        # ===== NINJA MANAGEMENT =====
        @self.bot_client.on(events.NewMessage(pattern=r"^/addninja(?:@\w+)?(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_ninja(event):
            if event.sender_id != Config.OWNER_ID: return
            cmd_args = event.pattern_match.group(1)
            session_str = event.pattern_match.group(2)
            name = cmd_args if cmd_args and not session_str else "Ninja"
            if not session_str:
                reply = await event.get_reply_message()
                if reply and reply.text:
                    session_str = reply.text.strip()
                    if cmd_args and not cmd_args.startswith("session"):
                        name = cmd_args
                else:
                    return await event.reply("❓ Usage: `/addninja <name> <session>`")
            if not session_str or len(session_str) < 10:
                return await event.reply("❌ Invalid session.")
            async for doc in self.db.ninja_col.find():
                if doc.get("session") == session_str:
                    return await event.reply("⚠️ Already exists.")
            await self.db.ninja_col.insert_one({"name": name, "session": session_str})
            client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            try:
                await client.start(); me = await client.get_me()
                client.tg_user_id = me.id
                self.ninja_clients.append(client)
                self.ninja_names.append(name)
                self.ninja_ids.add(me.id)
                self._register_ninja_handlers(client)
                self.chat_admin_cache.clear()
                await event.reply(f"✅ '{name}' (ID: {me.id}) added. Total: {len(self.ninja_clients)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {e}")
                await self.db.ninja_col.delete_one({"session": session_str})

        @self.bot_client.on(events.NewMessage(pattern=r"^/listninja(?:@\w+)?$"))
        async def list_ninja(event):
            if event.sender_id != Config.OWNER_ID: return
            if not self.ninja_clients:
                return await event.reply("📭 No ninjas.")
            online = 0
            lines = [f"👥 **Ninja Pool ({len(self.ninja_clients)} loaded)**"]
            for i, (client, name) in enumerate(zip(self.ninja_clients, self.ninja_names)):
                try:
                    me = await client.get_me()
                    online += 1
                    full = f"{me.first_name or ''} {me.last_name or ''}".strip() or "No Name"
                    user = f"(@{me.username})" if me.username else ""
                    lines.append(f"  {i+1}. **{full}** {user} (ID: `{me.id}`) ✅")
                except:
                    lines.append(f"  {i+1}. **{name}** – (offline) ❌")
            lines.append(f"\n📊 Online: {online}/{len(self.ninja_clients)}")
            await event.reply("\n".join(lines), parse_mode='markdown')

        @self.bot_client.on(events.NewMessage(pattern=r"^/removeninja(?:@\w+)?\s+(.+)$"))
        async def remove_ninja(event):
            if event.sender_id != Config.OWNER_ID: return
            target = event.pattern_match.group(1).strip()
            pr_list = await self.db.ninja_col.find().to_list(length=None)
            idx = None
            if target.isdigit(): idx = int(target) - 1
            else:
                for i, doc in enumerate(pr_list):
                    if doc.get("name") == target:
                        idx = i; break
            if idx is None or idx < 0 or idx >= len(pr_list):
                return await event.reply(f"❌ Not found: {target}")
            doc = pr_list[idx]
            await self.db.ninja_col.delete_one({"_id": doc["_id"]})
            if idx < len(self.ninja_clients):
                c = self.ninja_clients.pop(idx)
                self.ninja_names.pop(idx)
                try: await c.disconnect()
                except: pass
                self.chat_admin_cache.clear()
                await event.reply(f"✅ Removed '{doc.get('name')}'.")
            else:
                await event.reply("✅ Removed from DB.")

        # ===== 🥷 AUTO-NINJA STATUS =====
        @self.bot_client.on(events.NewMessage(pattern=r"^/autoninja(?:@\w+)?$"))
        async def autoninja_status(event):
            if event.sender_id != Config.OWNER_ID: return
            await event.reply(
                f"🥷 **AUTO-NINJA (Spawn Bot 2)**\n"
                f"🆔 Spawn Bot: `{Config.SPAWN_BOT_2_ID}`\n"
                f"📍 Spawn Group: `{Config.SPAWN_GROUP_2}`\n"
                f"👥 Pool Size: `{len(self.ninja_clients)}`\n"
                f"🎯 Picked per spawn: `{Config.NINJA_PICK_COUNT}`\n"
                f"⏱️ /w Delay: `{Config.NINJA_W_DELAY_MIN}–{Config.NINJA_W_DELAY_MAX}s`\n"
                f"🚫 Ignored Emojis: `{' '.join(Config.NINJA_IGNORED_EMOJIS)}`",
                parse_mode='markdown',
            )

        # ===== /go =====
        @self.bot_client.on(events.NewMessage(pattern=r"^/go(?:@\w+)?$"))
        async def go_group(event):
            if event.sender_id != Config.OWNER_ID: return
            if not event.is_reply:
                return await event.reply("❌ Reply to invite link.")
            reply = await event.get_reply_message()
            if not reply.text:
                return await event.reply("❌ No text.")
            m = re.search(r'(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)', reply.text)
            if not m:
                return await event.reply("❌ No valid link.")
            link = m.group(0)
            if 'joinchat/' in link:
                h = link.split('joinchat/')[1].split('?')[0]
            elif '+' in link:
                h = link.split('+')[1].split('?')[0]
            else:
                return await event.reply("❌ Bad link.")
            clients = self.ninja_clients.copy()
            if not clients:
                return await event.reply("❌ No clients.")
            await event.reply(f"⏳ Joining with {len(clients)} clients...")
            success = 0
            for c in clients:
                try:
                    await c(ImportChatInviteRequest(h)); success += 1
                except errors.rpcerrorlist.UserAlreadyParticipantError: success += 1
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                    try: await c(ImportChatInviteRequest(h)); success += 1
                    except: pass
                except Exception as e: logger.error(f"Join: {e}")
                await asyncio.sleep(0.3)
            self.chat_admin_cache.clear()
            try:
                chat = await clients[0].get_entity(link)
                await event.reply(f"✅ Joined `{chat.title}` with {success} clients. ID: `{chat.id}`")
            except:
                await event.reply(f"✅ Joined with {success} clients.")

        # ===== STATUS =====
        @self.bot_client.on(events.NewMessage(pattern=r"^/status(?:@\w+)?$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID: return
            taunts = sum(len(s) for s in self.delete_and_taunt_targets.values())
            active_list = ", ".join(str(g) for g in sorted(self.talk_active_groups)) or "none"
            report_loops = len(self.report_loop_tasks)
            start_spam_str = f"ON → @{self.start_spam_target}" if self.start_spam_active else "OFF"
            msg = (
                f"📊 **Status**\n"
                f"🤖 Ninja Pool: {len(self.ninja_clients)}\n"
                f"🥷 Auto-Ninja: {'ON' if self.ninja_clients else 'OFF'} "
                f"(picked={Config.NINJA_PICK_COUNT}, delay={Config.NINJA_W_DELAY_MIN}–{Config.NINJA_W_DELAY_MAX}s)\n"
                f"🎯 /startspam: {start_spam_str}\n"
                f"🔄 Cleanup: {'ON' if self.auto_cleanup else 'OFF'}\n"
                f"🗣️ Talk Active: {len(self.talk_active_groups)}/{len(Config.SPAM_GROUPS)}\n"
                f"   ↳ {active_list}\n"
                f"🚨 Report Loops: {report_loops}\n"
                f"🔥 Warmup Groups: {len(self.warmup_groups_cache)}\n"
                f"🛡️ Admin Caches: {len(self.chat_admin_cache)}\n"
                f"👹 Taunts: {taunts}"
            )
            await event.reply(msg, parse_mode='markdown')

        # ===== UNIVERSAL WATCHER =====
        @self.bot_client.on(events.NewMessage())
        async def watcher(event):
            if event.is_private: return
            if event.sender_id == self.bot_id or event.sender_id in self.ninja_ids:
                return
            cid, sid = event.chat_id, event.sender_id

            if cid in self.delete_and_taunt_targets and sid in self.delete_and_taunt_targets[cid]:
                if event.text:
                    try:
                        target = await event.get_sender()
                        name = target.first_name if target else "Target"
                    except Exception:
                        name = "Target"
                    asyncio.create_task(self._taunt_user(cid, sid, event.id, name))
                return

            if event.text:
                tl = event.text.lower().strip()
                async for f in self.db.custom_filters.find():
                    kw = f["keyword"].lower().strip()
                    if tl == kw or f" {kw} " in f" {tl} ":
                        try:
                            if f["type"] == "text":
                                await event.reply(self.strip_html(f["content"]))
                            else:
                                await event.reply(file=f["content"])
                            break
                        except: pass

            if event.text and event.text.startswith(("ချိန်ထား", "ပစ်သတ်")):
                reply = await event.get_reply_message()
                if reply and reply.sender_id == Config.OWNER_ID and event.sender_id != Config.OWNER_ID:
                    admins = await self._get_admin_clients(cid)
                    if admins:
                        client = random.choice(admins)
                        phrase = await self.get_next_phrase(cid)
                        try:
                            sender = await event.get_sender()
                            mention = self.format_mention(sid, sender.first_name or "Unknown")
                            await client.send_message(cid, f"{mention} {phrase}", parse_mode='html')
                        except: pass
                    return
                if not await self.is_allowed(sid):
                    try:
                        sender = await event.get_sender()
                        await self.bot_client.send_message(cid, f"⛔ {sender.first_name or 'User'}, no authority.")
                    except: pass

        # ===== FILTER HANDLERS =====
        @self.bot_client.on(events.NewMessage)
        async def sticker_filter(event): await self.sticker_spam_filter(event)
        @self.bot_client.on(events.NewMessage)
        async def short_filter(event): await self.short_text_spam_filter(event)
        @self.bot_client.on(events.NewMessage)
        async def bio_filter(event): await self.bio_link_filter(event)
        @self.bot_client.on(events.NewMessage(incoming=True))
        async def lang_filter(event): await self.language_filter(event)

    # ---------- START / STOP ----------
    async def start(self) -> None:
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        me = await self.bot_client.get_me()
        self.bot_id = me.id
        logger.info(f"🤖 Bot started: @{me.username} (ID: {self.bot_id})")
        await self.load_ninja_pools()
        await self.load_taunt_targets()
        await self.load_warmup_groups()
        asyncio.create_task(self.preload_admin_caches())
        threading.Thread(target=run_flask, daemon=True).start()
        await self.bot_client.run_until_disconnected()

    async def stop(self) -> None:
        # 🎯 Stop start-spam first
        if self.start_spam_active:
            await self.stop_start_spam()
        if self.talk_active_groups:
            await self.stop_talk_all()
        for key in list(self.report_loop_tasks.keys()):
            self.report_loop_tasks[key] = False
        if self.bot_client.is_connected():
            await self.bot_client.disconnect()
        for c in self.ninja_clients:
            try: await c.disconnect()
            except: pass
        await self.db.close()
        logger.info("🛑 Shutdown complete.")

# ------------------------------------------------------------------
#  MAIN
# ------------------------------------------------------------------
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
