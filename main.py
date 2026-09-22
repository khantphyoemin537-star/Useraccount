#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Ninja System (CLEAN)
- Ninja Pool management (/addninja, /listninja, /removeninja)
- 🥷 Auto-Ninja for Spawn Bot 2 (Hint Bot) in -1003580630981
- 🎯 /startspam @Bot  — Ninja DM /start every 3 min
- 🗣️ /spam — Ninja spam in SPAM_GROUPS
- 👹 Taunt (ဖာသည်မသား)
- 🛡️ /adm  — Promote all ninjas to admin (auto-promote on join)
- 💥 /go    — Ninja pool joins an invite link
- ⛔ /stop  — Stop spam per-group
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
from pymongo.errors import ConnectionFailure, OperationFailure
from telethon import TelegramClient, events, errors
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest


# ------------------------------------------------------------------
#  CONFIG
# ------------------------------------------------------------------
class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "7693106830"))
    MONGO_URI = os.getenv(
        "MONGO_URI",
        "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true",
    )
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "8824002850:AAGPtl7M0dw_gDVEZNxM3xxrYQazKvO5FKo")

    # 🎯 SPAM GROUPS
    SPAM_GROUPS = [
        -1004381473883,
        -1003836488351,
        -1003733625547,
        -1004358425408,
    ]

    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yangon"))
    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

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
def health_check() -> str:
    return "Sovereign Ninja System is operational."


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
    def system_col(self): return self.db["system_col"]
    @property
    def ninja_col(self): return self.db["ninja_col"]
    @property
    def taunt_targets(self): return self.db["taunt_targets"]


# ------------------------------------------------------------------
#  MAIN BOT
# ------------------------------------------------------------------
class SovereignBot:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.bot_client = TelegramClient(
            "bot_main_session", Config.API_ID, Config.API_HASH, flood_sleep_threshold=60
        )
        self.bot_id: Optional[int] = None

        # Ninja pool
        self.ninja_clients: List[TelegramClient] = []
        self.ninja_names: List[str] = []
        self.ninja_ids: Set[int] = set()

        # Spam state
        self.ninja_spam_tasks: Dict[Tuple[int, ...], bool] = {}

        # Taunt
        self.delete_and_taunt_targets: Dict[int, Set[int]] = {}
        self.phrase_lists: Dict[int, List[str]] = {}
        self.phrase_indices: Dict[int, int] = {}

        # Admin cache
        self.chat_admin_cache: Dict[int, Tuple[List[TelegramClient], float]] = {}
        self.admin_cache_locks: Dict[int, asyncio.Lock] = {}

        # 🥷 Auto-ninja state
        self.ninja_spawn_marker = {"key": None, "selected": set()}
        self.ninja_spawn_tracker: Dict[Tuple[int, int], int] = {}
        self.ninja_latest_spawn: Dict[int, int] = {}

        # 🎯 Start-spam state
        self.start_spam_tasks: Dict[int, asyncio.Task] = {}
        self.start_spam_target: Optional[str] = None
        self.start_spam_active: bool = False

        self._register_handlers()

    # ==============================================================
    #  TAUNT TARGETS (DB)
    # ==============================================================
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
        await self.db.taunt_targets.update_one(
            {"chat_id": chat_id}, {"$addToSet": {"target_ids": target_id}}, upsert=True
        )

    async def _remove_taunt_target(self, chat_id: int, target_id: int) -> None:
        if chat_id in self.delete_and_taunt_targets:
            self.delete_and_taunt_targets[chat_id].discard(target_id)
            if not self.delete_and_taunt_targets[chat_id]:
                del self.delete_and_taunt_targets[chat_id]
                await self.db.taunt_targets.delete_one({"chat_id": chat_id})
            else:
                await self.db.taunt_targets.update_one(
                    {"chat_id": chat_id}, {"$pull": {"target_ids": target_id}}
                )

    async def _clear_taunt_targets(self, chat_id: int) -> None:
        if chat_id in self.delete_and_taunt_targets:
            del self.delete_and_taunt_targets[chat_id]
            await self.db.taunt_targets.delete_one({"chat_id": chat_id})

    # ==============================================================
    #  ADMIN CACHE
    # ==============================================================
    async def _scan_admin_clients(self, chat_id: int) -> List[TelegramClient]:
        async def check(client):
            try:
                perms = await client.get_permissions(chat_id, "me")
                if perms and getattr(perms, "is_admin", False):
                    return client
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except Exception:
                pass
            return None

        results = await asyncio.gather(
            *[check(c) for c in self.ninja_clients], return_exceptions=False
        )
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
        targets = set(Config.SPAM_GROUPS)
        if not targets:
            return
        logger.info(f"⚡ Preloading admin caches for {len(targets)} groups...")
        await asyncio.gather(*[self._get_admin_clients(g) for g in targets], return_exceptions=True)
        logger.info("✅ Admin caches preloaded.")

    # ==============================================================
    #  🥷 AUTO-PROMOTE (ChatAction)
    # ==============================================================
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
            chat_id = event.chat_id
            logger.info(f"🥷 Ninja {me_id} joined {chat_id} → auto-promote")
            asyncio.create_task(self._auto_promote_ninjas(chat_id))
        except Exception as e:
            logger.warning(f"ninja_join error (ignored): {e}")

    async def _auto_promote_ninjas(self, chat_id: int):
        try:
            try:
                perms = await self.bot_client.get_permissions(chat_id, "me")
            except Exception as e:
                logger.warning(f"Auto-promote: bot perms failed in {chat_id}: {e}")
                return
            if not (perms and getattr(perms, "is_admin", False)):
                logger.warning(f"Auto-promote: bot not admin in {chat_id}")
                return
            if not (getattr(perms, "add_admins", False) or getattr(perms, "is_creator", False)):
                logger.warning(f"Auto-promote: bot lacks add_admins in {chat_id}")
                try:
                    await self.bot_client.send_message(
                        Config.OWNER_ID,
                        f"⚠️ **Auto-promote skipped** `{chat_id}`\n"
                        f"❌ Bot lacks **Add Admins** permission.",
                        parse_mode="markdown",
                    )
                except Exception:
                    pass
                return

            promoted = already = failed = 0
            for client in self.ninja_clients:
                try:
                    uid = getattr(client, "tg_user_id", None)
                    if not uid:
                        try:
                            me = await client.get_me()
                            uid = me.id
                            client.tg_user_id = uid
                        except Exception:
                            failed += 1
                            continue
                    try:
                        np = await self.bot_client.get_permissions(chat_id, uid)
                        if np and getattr(np, "is_admin", False):
                            already += 1
                            continue
                    except Exception:
                        pass
                    await self.bot_client.edit_admin(
                        chat_id, uid,
                        change_info=False, post_messages=True, edit_messages=True,
                        delete_messages=True, ban_users=True, invite_users=True,
                        pin_messages=True, add_admins=False, anonymous=False,
                        manage_call=False,
                    )
                    promoted += 1
                    logger.info(f"🥷 Promoted {uid} in {chat_id}")
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                    failed += 1
                except Exception as e:
                    logger.warning(f"Promote {uid} in {chat_id} failed: {e}")
                    failed += 1
                await asyncio.sleep(0.4)

            try:
                await self.bot_client.send_message(
                    Config.OWNER_ID,
                    f"✅ **Auto-Promote complete** `{chat_id}`\n"
                    f"✔️ Promoted: **{promoted}**\n"
                    f"ℹ️ Already: **{already}**\n"
                    f"✖️ Failed: **{failed}**",
                    parse_mode="markdown",
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"_auto_promote_ninjas error: {e}")

    # ==============================================================
    #  🎯 /START SPAM  (Bot DM)
    # ==============================================================
    async def _start_spam_worker(self, ninja_client: TelegramClient, ninja_id: int, target_bot: str):
        await asyncio.sleep(random.uniform(Config.START_SPAM_MIN_DELAY, Config.START_SPAM_MAX_DELAY))
        while self.start_spam_active and ninja_id in self.start_spam_tasks:
            try:
                await ninja_client.send_message(target_bot, "/start")
                logger.info(f"🎯 [{ninja_id}] → /start to @{target_bot}")
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"🎯 [{ninja_id}] /start failed (ignored): {e}")

            jitter = Config.START_SPAM_INTERVAL * random.uniform(
                -Config.START_SPAM_JITTER, Config.START_SPAM_JITTER
            )
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
                uid = getattr(client, "tg_user_id", None)
                if not uid:
                    me = await client.get_me()
                    uid = me.id
                    client.tg_user_id = uid
                task = asyncio.create_task(self._start_spam_worker(client, uid, target_bot))
                self.start_spam_tasks[uid] = task
                started += 1
            except Exception as e:
                logger.warning(f"🎯 start-spam worker failed: {e}")
        logger.info(f"🎯 /START SPAM: {started} workers → @{target_bot}")
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
        return stopped

    # ==============================================================
    #  🥷 AUTO-NINJA (Spawn Bot 2)
    # ==============================================================
    async def _ninja_spawn_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
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
            if not (
                "A CHARACTER HAS SPAWNED" in upper
                or "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ" in text_raw
            ):
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
                logger.info(f"🥷 New spawn → picked {len(picked)}/{len(avail)}")

            if uid not in self.ninja_spawn_marker["selected"]:
                return

            delay = random.uniform(Config.NINJA_W_DELAY_MIN, Config.NINJA_W_DELAY_MAX)
            await asyncio.sleep(delay)
            try:
                reply = await event.message.reply("/w")
                self.ninja_spawn_tracker[(uid, reply.id)] = event.chat_id
                self.ninja_latest_spawn[uid] = event.chat_id
                logger.info(f"🥷 Ninja {uid} → /w (msg={reply.id}, delay={delay:.2f}s)")
            except Exception as e:
                logger.warning(f"🥷 Ninja {uid} /w failed (ignored): {e}")
        except Exception as e:
            logger.warning(f"🥷 spawn handler error (ignored): {e}")

    async def _ninja_hint_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
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
            self._ninja_spawn_handler, events.NewMessage(from_users=Config.SPAWN_BOT_2_ID)
        )
        client.add_event_handler(
            self._ninja_hint_handler, events.NewMessage(chats=Config.SPAWN_GROUP_2)
        )
        client.add_event_handler(self._ninja_join_handler, events.ChatAction())

    # ==============================================================
    #  NINJA POOL LOAD
    # ==============================================================
    async def load_ninja_pools(self) -> None:
        for client in self.ninja_clients:
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass
        self.ninja_clients.clear()
        self.ninja_names.clear()
        self.ninja_ids.clear()

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

    # ==============================================================
    #  HELPERS
    # ==============================================================
    def format_mention(self, user_id: int, name: str) -> str:
        return f"<a href='tg://user?id={user_id}'>{escape_html(name)}</a>"

    def bq(self, text: str) -> str:
        return f"<blockquote><b>{text}</b></blockquote>"

    # ==============================================================
    #  PHRASES
    # ==============================================================
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

    # ==============================================================
    #  SPAM
    # ==============================================================
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
                await client.send_message(chat_id, SPAM_TEXT)
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

    # ==============================================================
    #  TAUNT EXECUTION
    # ==============================================================
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
            await client.send_message(chat_id, f"{mention} {phrase}", parse_mode="html")
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            logger.error(f"Taunt send error: {e}")

    # ==============================================================
    #  COMMAND HANDLERS
    # ==============================================================
    def _register_handlers(self):

        # ---------- /addninja ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/addninja(?:@\w+)?(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_ninja(event):
            if event.sender_id != Config.OWNER_ID:
                return
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
                await client.start()
                me = await client.get_me()
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

        # ---------- /listninja ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/listninja(?:@\w+)?$"))
        async def list_ninja(event):
            if event.sender_id != Config.OWNER_ID:
                return
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
                except Exception:
                    lines.append(f"  {i+1}. **{name}** – (offline) ❌")
            lines.append(f"\n📊 Online: {online}/{len(self.ninja_clients)}")
            await event.reply("\n".join(lines), parse_mode="markdown")

        # ---------- /removeninja ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/removeninja(?:@\w+)?\s+(.+)$"))
        async def remove_ninja(event):
            if event.sender_id != Config.OWNER_ID:
                return
            target = event.pattern_match.group(1).strip()
            pr_list = await self.db.ninja_col.find().to_list(length=None)
            idx = None
            if target.isdigit():
                idx = int(target) - 1
            else:
                for i, doc in enumerate(pr_list):
                    if doc.get("name") == target:
                        idx = i
                        break
            if idx is None or idx < 0 or idx >= len(pr_list):
                return await event.reply(f"❌ Not found: {target}")
            doc = pr_list[idx]
            await self.db.ninja_col.delete_one({"_id": doc["_id"]})
            if idx < len(self.ninja_clients):
                c = self.ninja_clients.pop(idx)
                self.ninja_names.pop(idx)
                try:
                    await c.disconnect()
                except Exception:
                    pass
                self.chat_admin_cache.clear()
                await event.reply(f"✅ Removed '{doc.get('name')}'.")
            else:
                await event.reply("✅ Removed from DB.")

        # ---------- /autoninja ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/autoninja(?:@\w+)?$"))
        async def autoninja_status(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await event.reply(
                f"🥷 **AUTO-NINJA (Spawn Bot 2)**\n"
                f"🆔 Spawn Bot: `{Config.SPAWN_BOT_2_ID}`\n"
                f"📍 Spawn Group: `{Config.SPAWN_GROUP_2}`\n"
                f"👥 Pool Size: `{len(self.ninja_clients)}`\n"
                f"🎯 Picked per spawn: `{Config.NINJA_PICK_COUNT}`\n"
                f"⏱️ /w Delay: `{Config.NINJA_W_DELAY_MIN}–{Config.NINJA_W_DELAY_MAX}s`\n"
                f"🚫 Ignored Emojis: `{' '.join(Config.NINJA_IGNORED_EMOJIS)}`",
                parse_mode="markdown",
            )

        # ---------- 🎯 /startspam ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/startspam(?:@\w+)?(?:\s+(@?\w+))?$"))
        async def startspam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            arg = event.pattern_match.group(1)
            if not arg:
                return await event.reply("⚠️ **Usage:** `/startspam @BotUsername`")
            target = arg.lstrip("@").strip()
            if not target:
                return await event.reply("❌ Invalid username.")
            if self.start_spam_active:
                return await event.reply(
                    f"⚠️ Already running → @{self.start_spam_target}\n"
                    f"Send `/stopspam` first."
                )
            if not self.ninja_clients:
                return await event.reply("❌ Ninja pool empty.")
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

        # ---------- 🛡️ /adm ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/adm(?:@\w+)?(?:\s+(.+))?$"))
        async def adm_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")

            arg = event.pattern_match.group(1)
            target_chat = None

            if arg:
                raw = arg.strip()
                if re.match(r"^-?\d+$", raw):
                    target_chat = int(raw)
                elif raw.startswith("@") or re.match(r"^[A-Za-z][A-Za-z0-9_]{3,}$", raw):
                    uname = raw.lstrip("@")
                    try:
                        ent = await self.bot_client.get_entity(uname)
                        target_chat = ent.id
                    except Exception as e:
                        return await event.reply(f"❌ Cannot find @{uname}: {e}")
                else:
                    return await event.reply(
                        "⚠️ **Usage:**\n"
                        "• Group: `/adm`\n"
                        "• DM: `/adm -100123456789`\n"
                        "• DM: `/adm @groupusername`"
                    )
            else:
                if event.is_private:
                    return await event.reply(
                        "⚠️ **Usage in DM:**\n"
                        "`/adm -100123456789`\n"
                        "`/adm @groupusername`"
                    )
                target_chat = event.chat_id

            if not target_chat:
                return await event.reply("❌ Could not determine target chat.")
            if not self.ninja_clients:
                return await event.reply("❌ Ninja pool is empty.")

            try:
                perms = await self.bot_client.get_permissions(target_chat, "me")
            except Exception as e:
                return await event.reply(f"❌ Cannot access `{target_chat}`: {e}")

            if not (perms and getattr(perms, "is_admin", False)):
                return await event.reply(
                    f"❌ Bot is **not admin** in `{target_chat}`"
                )
            if not (getattr(perms, "add_admins", False) or getattr(perms, "is_creator", False)):
                return await event.reply(
                    f"❌ Bot lacks **Add Admins** permission in `{target_chat}`."
                )

            status = await event.reply(
                f"⏳ **Promoting {len(self.ninja_clients)} ninjas** in `{target_chat}`..."
            )

            promoted = already = failed = 0
            for client in self.ninja_clients:
                try:
                    uid = getattr(client, "tg_user_id", None)
                    if not uid:
                        try:
                            me = await client.get_me()
                            uid = me.id
                            client.tg_user_id = uid
                        except Exception:
                            failed += 1
                            continue
                    try:
                        np = await self.bot_client.get_permissions(target_chat, uid)
                        if np and getattr(np, "is_admin", False):
                            already += 1
                            continue
                    except Exception:
                        pass
                    await self.bot_client.edit_admin(
                        target_chat, uid,
                        change_info=False, post_messages=True, edit_messages=True,
                        delete_messages=True, ban_users=True, invite_users=True,
                        pin_messages=True, add_admins=False, anonymous=False,
                        manage_call=False,
                    )
                    promoted += 1
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                    failed += 1
                except Exception as e:
                    logger.warning(f"/adm promote {uid} failed: {e}")
                    failed += 1
                await asyncio.sleep(0.4)

            await status.edit(
                f"✅ **/adm complete** `{target_chat}`\n"
                f"✔️ Promoted: **{promoted}**\n"
                f"ℹ️ Already: **{already}**\n"
                f"✖️ Failed: **{failed}**"
            )

        # ---------- 👹 Taunt ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^ဖာသည်မသား$"))
        async def taunt(event):
            if event.sender_id != Config.OWNER_ID:
                return
            try:
                await event.delete()
            except Exception:
                pass
            reply = await event.get_reply_message()
            if not reply:
                return await event.reply("❌ Reply to a target.")
            target = await reply.get_sender()
            if not target or target.id == Config.OWNER_ID:
                return
            chat_id = event.chat_id
            target_id = target.id
            target_name = target.first_name or "Target"

            admins = await self._get_admin_clients(chat_id)
            if not admins:
                return await event.reply("⚠️ No ninja is admin here.")

            mention = self.format_mention(target_id, target_name)
            try:
                await self.bot_client.delete_messages(chat_id, [reply.id])
            except Exception:
                pass
            await self._add_taunt_target(chat_id, target_id)
            client = random.choice(admins)
            phrase = await self.get_next_phrase(chat_id)
            try:
                await client.send_message(chat_id, f"{mention} {phrase}", parse_mode="html")
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                logger.error(f"Taunt send failed: {e}")
            await event.reply(f"✅ Taunt enabled for {mention} ({len(admins)} admin).", parse_mode="html")

        @self.bot_client.on(events.NewMessage(pattern=r"^/remove_taunt(?:@\w+)?(?:\s+(\d+))?$"))
        async def remove_taunt(event):
            if event.sender_id != Config.OWNER_ID:
                return
            cid = event.chat_id
            tid = event.pattern_match.group(1)
            if tid:
                await self._remove_taunt_target(cid, int(tid))
                await event.reply(f"✅ Removed {tid}")
            elif event.is_reply:
                reply = await event.get_reply_message()
                target = await reply.get_sender()
                await self._remove_taunt_target(cid, target.id)
                await event.reply(
                    f"✅ Removed {self.format_mention(target.id, target.first_name or '?')}",
                    parse_mode="html",
                )

        @self.bot_client.on(events.NewMessage(pattern=r"^/clear_taunts(?:@\w+)?(?:\s+(-?\d+))?$"))
        async def clear_taunts(event):
            if event.sender_id != Config.OWNER_ID:
                return
            tid = event.pattern_match.group(1)
            cid = int(tid) if tid else event.chat_id
            await self._clear_taunt_targets(cid)
            await event.reply("🧹 Cleared.")

        # ---------- 🗣️ /spam ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/spam(?:@\w+)?$"))
        async def spam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            groups = Config.SPAM_GROUPS
            await self._start_spam_loop(groups)
            await event.reply(f"🗣️ Spam started on {len(groups)} groups.")

        # ---------- ⛔ /stop ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop(?:@\w+)?)$"))
        async def stop_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            chat_id = event.chat_id
            stopped_here = False
            for key in list(self.ninja_spam_tasks.keys()):
                if chat_id in key or event.sender_id == Config.OWNER_ID:
                    self.ninja_spam_tasks[key] = False
                    stopped_here = True
            if stopped_here:
                await event.reply("🛑 Spam stopped in this chat.")
            else:
                await event.reply("ℹ️ Nothing to stop here.")

        # ---------- 💥 /go ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/go(?:@\w+)?$"))
        async def go_group(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not event.is_reply:
                return await event.reply("❌ Reply to invite link.")
            reply = await event.get_reply_message()
            if not reply.text:
                return await event.reply("❌ No text.")
            m = re.search(r"(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)", reply.text)
            if not m:
                return await event.reply("❌ No valid link.")
            link = m.group(0)
            if "joinchat/" in link:
                h = link.split("joinchat/")[1].split("?")[0]
            elif "+" in link:
                h = link.split("+")[1].split("?")[0]
            else:
                return await event.reply("❌ Bad link.")
            clients = self.ninja_clients.copy()
            if not clients:
                return await event.reply("❌ No clients.")
            await event.reply(f"⏳ Joining with {len(clients)} clients...")
            success = 0
            for c in clients:
                try:
                    await c(ImportChatInviteRequest(h))
                    success += 1
                except errors.rpcerrorlist.UserAlreadyParticipantError:
                    success += 1
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                    try:
                        await c(ImportChatInviteRequest(h))
                        success += 1
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Join: {e}")
                await asyncio.sleep(0.3)
            self.chat_admin_cache.clear()
            try:
                chat = await clients[0].get_entity(link)
                await event.reply(f"✅ Joined `{chat.title}` with {success} clients. ID: `{chat.id}`")
            except Exception:
                await event.reply(f"✅ Joined with {success} clients.")

        # ---------- 📊 /status ----------
        @self.bot_client.on(events.NewMessage(pattern=r"^/status(?:@\w+)?$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            taunts = sum(len(s) for s in self.delete_and_taunt_targets.values())
            start_spam_str = f"ON → @{self.start_spam_target}" if self.start_spam_active else "OFF"
            spam_groups_str = ", ".join(str(g) for g in Config.SPAM_GROUPS)
            msg = (
                f"📊 **Status**\n"
                f"🤖 Ninja Pool: `{len(self.ninja_clients)}`\n"
                f"🥷 Auto-Ninja: ON (pick={Config.NINJA_PICK_COUNT}, "
                f"delay={Config.NINJA_W_DELAY_MIN}–{Config.NINJA_W_DELAY_MAX}s)\n"
                f"🎯 /startspam: {start_spam_str}\n"
                f"👹 Taunts: `{taunts}`\n"
                f"🎯 SPAM_GROUPS:\n   {spam_groups_str}"
            )
            await event.reply(msg, parse_mode="markdown")

        # ---------- WATCHER: taunt-target auto-delete ----------
        @self.bot_client.on(events.NewMessage())
        async def watcher(event):
            if event.is_private:
                return
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

    # ==============================================================
    #  START / STOP
    # ==============================================================
    async def start(self) -> None:
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        me = await self.bot_client.get_me()
        self.bot_id = me.id
        logger.info(f"🤖 Bot started: @{me.username} (ID: {self.bot_id})")
        await self.load_ninja_pools()
        await self.load_taunt_targets()
        asyncio.create_task(self.preload_admin_caches())
        threading.Thread(target=run_flask, daemon=True).start()
        await self.bot_client.run_until_disconnected()

    async def stop(self) -> None:
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
