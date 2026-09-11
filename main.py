#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign System – ANY-GROUP TAUNT + MULTI-TASK FAST
- Taunt (ဖာသည်မသား) works in ANY group (not limited to SPAM_GROUPS)
- Admin cache preloaded for SPAM_GROUPS + all warmup_groups in DB
- /warmup command: register current group + scan admin cache
- Parallel admin scan, fire-and-forget taunt
- All commands accept @botusername
- Allowed users: both "ရပ်" and "/stop"
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

# ------------------------------------------------------------------
#  CONFIG
# ------------------------------------------------------------------
class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "6015356597"))
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true")
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "8111794244:AAGurFdkxV_KrahEYJemMo-hoQkN1mJJKlU")

    LEARNING_GROUP = int(os.getenv("LEARNING_GROUP", "-1003806830045"))
    SPAM_GROUPS = [
        -1004421587002,
        -1003819613443,
        -1004390542396,
        -1004358565293,
    ]

    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yangon"))
    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    SPAM_DELAY = 1
    TALK_DELAY = 1
    ADMIN_CACHE_TTL = 600
    MAX_RETRIES = 3

SPAM_TEXT = """ @Imjustkidding_bot , @GodMorgan_robot ,  @fuckyourwifey_bot rjsjsjsjssjsjjssjsjdjsjsjsjzjsjsjssnsnsnsndndndjsdjdndjdjdjdjdjsjdjdjdjdjdjsjsnsj """

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

        # Admin cache: chat_id -> (clients, expiry)
        self.chat_admin_cache: Dict[int, Tuple[List[TelegramClient], float]] = {}
        self.admin_cache_locks: Dict[int, asyncio.Lock] = {}

        self.sticker_spam_data = {}
        self.char_spam_data = {}
        self.admin_warned_sticker = set()
        self.admin_warned_char = set()
        self.admin_cache = {}

        # Talk per-group
        self.talk_active_groups: Set[int] = set()
        self.talk_workers_by_group: Dict[int, List[asyncio.Task]] = {}
        self.talk_phrase_pool: List[str] = []
        self.talk_phrases_loaded = False

        self.auto_cleanup = False
        self.msg_queues: Dict[int, List[int]] = {}
        self.queue_locks: Dict[int, asyncio.Lock] = {}

        # Warmup groups cache (loaded from DB)
        self.warmup_groups_cache: Set[int] = set()

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

    # ---------- WARMUP GROUPS ----------
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

    # ---------- ADMIN CACHE (parallel scan) ----------
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
        """Works for ANY chat_id. Cached for ADMIN_CACHE_TTL seconds."""
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
        """Preload SPAM_GROUPS + all warmup groups in DB."""
        targets = set(Config.SPAM_GROUPS) | self.warmup_groups_cache
        if not targets:
            return
        logger.info(f"⚡ Preloading admin caches for {len(targets)} groups...")
        await asyncio.gather(*[self._get_admin_clients(g) for g in targets], return_exceptions=True)
        logger.info("✅ Admin caches preloaded.")

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
                    self.ninja_clients.append(client)
                    name = doc.get("name", f"Ninja-{len(self.ninja_clients)}")
                    self.ninja_names.append(name)
                    self.ninja_ids.add(me.id)
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
        """Fast, admin-only taunt. Works in ANY chat_id."""
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

        # ===== TAUNT (works in ANY group) =====
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

            # Works in ANY chat_id
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

        # ===== STOP =====
        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop(?:@\w+)?)$"))
        async def stop_cmd(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id
            stopped = False

            for key in list(self.ninja_spam_tasks.keys()):
                if chat_id in key:
                    self.ninja_spam_tasks[key] = False
                    stopped = True

            if chat_id in Config.SPAM_GROUPS and chat_id in self.talk_active_groups:
                await self.stop_talk_group(chat_id)
                stopped = True
            elif event.sender_id == Config.OWNER_ID and self.talk_active_groups:
                await self.stop_talk_all()
                stopped = True

            if stopped:
                await event.reply("🛑 Stopped.")
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
                self.ninja_clients.append(client)
                self.ninja_names.append(name)
                self.ninja_ids.add(me.id)
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
            msg = (
                f"📊 **Status**\n"
                f"🤖 Ninja Pool: {len(self.ninja_clients)}\n"
                f"🔄 Cleanup: {'ON' if self.auto_cleanup else 'OFF'}\n"
                f"🗣️ Talk Groups: {len(self.talk_active_groups)}/{len(Config.SPAM_GROUPS)}\n"
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

            # Taunt targets – fire-and-forget, works in ANY chat
            if cid in self.delete_and_taunt_targets and sid in self.delete_and_taunt_targets[cid]:
                if event.text:
                    try:
                        target = await event.get_sender()
                        name = target.first_name if target else "Target"
                    except Exception:
                        name = "Target"
                    asyncio.create_task(self._taunt_user(cid, sid, event.id, name))
                return

            # Custom filters
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

            # Protect Sovereign
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
        if self.talk_active_groups:
            await self.stop_talk_all()
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
