#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sovereign System – FINAL ERROR-FREE VERSION
- Parallel talk on all 4 groups using all clients.
- Only Owner can stop talk.
- /listninja shows full name and online count.
- No moderation commands, no pool 2/3 attack commands.
- All methods defined at class level to avoid AttributeError.
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
#  CONFIGURATION
# ------------------------------------------------------------------
class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "7693106830"))
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true")
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "8111794244:AAGurFdkxV_KrahEYJemMo-hoQkN1mJJKlU")
    
    LEARNING_GROUP = int(os.getenv("LEARNING_GROUP", "-1003806830045"))
    SPAM_GROUPS = [
        -1004421587002, #tar
        -1003819613443, #cat
        -1004390542396, #morgan
        -1004358565293 #jojo
    ]
    
    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yangon"))
    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    BULLY_DELAY = 0.8
    SHOOT_DELAY = 0.4
    SPAM_DELAY = 0.5
    TALK_DELAY = 0.6
    MAX_RETRIES = 3

SPAM_TEXT = """ @Imjustkidding_bot , @GodMorgan_robot ,  @fuckyourwifey_bot rjsjsjsjssjsjjssjsjdjsjsjsjzjsjsjssnsnsnsndndndjsdjdndjdjdjdjdjsjdjdjdjdjdjsjsnsj """

# ------------------------------------------------------------------
#  LOGGING
# ------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("SovereignFinal")

# ------------------------------------------------------------------
#  FLASK KEEP‑ALIVE
# ------------------------------------------------------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def health_check() -> str:
    return "Sovereign Final System is operational."

def run_flask() -> None:
    flask_app.run(host="0.0.0.0", port=Config.FLASK_PORT, threaded=True)

# ------------------------------------------------------------------
#  DATABASE MANAGER
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
                    await self.db.learned_new.create_index("text", unique=True, sparse=True)
                except Exception as e:
                    logger.warning(f"Index creation warning: {e}")
                try:
                    await self.db.talk_phrases.create_index([("group_id", 1), ("text", 1)], unique=True, sparse=True)
                except Exception as e:
                    logger.warning(f"Talk phrases index warning: {e}")
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
    def learned(self): return self.db["learned_new"]
    @property
    def marcuz_col(self): return self.db["marcuz_col"]
    @property
    def ninja_col(self): return self.db["ninja_col"]
    @property
    def ninja_col2(self): return self.db["ninja_col2"]
    @property
    def ninja_col3(self): return self.db["ninja_col3"]
    @property
    def special_pool_col(self): return self.db["special_pool_col"]
    @property
    def special_spam_texts(self): return self.db["special_spam_texts"]
    @property
    def talk_phrases(self): return self.db["talk_phrases"]
    @property
    def taunt_targets(self): return self.db["taunt_targets"]

# ------------------------------------------------------------------
#  MAIN BOT CLASS
# ------------------------------------------------------------------
class SovereignBot:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.bot_client = TelegramClient("bot_main_session", Config.API_ID, Config.API_HASH, flood_sleep_threshold=60)
        self.bot_id: Optional[int] = None

        # ---------- NINJA POOL 1 ----------
        self.ninja_clients: List[TelegramClient] = []
        self.ninja_names: List[str] = []
        self.ninja_ids: Set[int] = set()
        self.ninja_bully_tasks: Dict[int, bool] = {}
        self.ninja_shoot_tasks: Dict[int, bool] = {}
        self.ninja_tracking_targets: Dict[int, int] = {}
        self.ninja_dark_passenger_targets: Dict[int, int] = {}
        self.ninja_spam_tasks: Dict[Tuple[int, ...], bool] = {}

        # ---------- NINJA POOL 2 ----------
        self.ninja_clients2: List[TelegramClient] = []
        self.ninja_names2: List[str] = []
        self.ninja_ids2: Set[int] = set()
        self.ninja_spam_tasks2: Dict[Tuple[int, ...], bool] = {}

        # ---------- NINJA POOL 3 ----------
        self.ninja_clients3: List[TelegramClient] = []
        self.ninja_names3: List[str] = []
        self.ninja_ids3: Set[int] = set()
        self.ninja_spam_tasks3: Dict[Tuple[int, ...], bool] = {}

        # ---------- SPECIAL POOL ----------
        self.special_clients: List[TelegramClient] = []
        self.special_names: List[str] = []
        self.special_ids: Set[int] = set()
        self.special_attack_active = False
        self.special_attack_task: Optional[asyncio.Task] = None
        self.special_target_chat: Optional[int] = None
        self.special_target_mention: Optional[str] = None
        self.special_spam_texts_list: List[str] = []
        self.special_save_mode = False

        # Shared taunt targets
        self.delete_and_taunt_targets: Dict[int, Set[int]] = {}
        self.pool_lock = asyncio.Lock()
        self.learning_status = False
        self.save_status = False

        self.phrase_lists: Dict[int, List[str]] = {}
        self.phrase_indices: Dict[int, int] = {}

        self.sticker_spam_data = {}
        self.char_spam_data = {}
        self.admin_warned_sticker = set()
        self.admin_warned_char = set()
        self.admin_cache = {}

        # ---------- TALK SYSTEM ----------
        self.talk_running = False
        self.talk_workers: List[asyncio.Task] = []
        self.talk_phrase_pool: List[str] = []

        # AUTO CLEANUP
        self.auto_cleanup = False
        self.msg_queues: Dict[int, List[int]] = {}
        self.queue_locks: Dict[int, asyncio.Lock] = {}

        # Register handlers after everything is set up
        self._register_handlers()

    # --------------------------------------------------------------
    #  TAUNT TARGETS – CLASS METHODS
    # --------------------------------------------------------------
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

    # --------------------------------------------------------------
    #  NINJA POOL LOADING
    # --------------------------------------------------------------
    async def load_ninja_pools(self) -> None:
        await self._load_pool(self.db.ninja_col, self.ninja_clients, self.ninja_names, self.ninja_ids, "Ninja Pool 1")
        await self._load_pool(self.db.ninja_col2, self.ninja_clients2, self.ninja_names2, self.ninja_ids2, "Ninja Pool 2")
        await self._load_pool(self.db.ninja_col3, self.ninja_clients3, self.ninja_names3, self.ninja_ids3, "Ninja Pool 3")

    async def _load_pool(self, collection, clients_list, names_list, ids_set, pool_name):
        for client in clients_list:
            try:
                if client.is_connected():
                    await client.disconnect()
            except: pass
        clients_list.clear(); names_list.clear(); ids_set.clear()
        async for pr_doc in collection.find():
            session_str = pr_doc.get("session")
            if not session_str:
                continue
            try:
                client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
                await client.start()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    clients_list.append(client)
                    name = pr_doc.get("name", f"Ninja-{len(clients_list)}")
                    names_list.append(name); ids_set.add(me.id)
                    logger.info(f"✅ {pool_name} – '{name}' loaded: @{me.username}")
                else:
                    await client.disconnect()
            except Exception as e:
                logger.error(f"❌ {pool_name} – failed: {e}")
        logger.info(f"🚀 {pool_name} ready: {len(clients_list)} clients.")

    # --------------------------------------------------------------
    #  SPECIAL POOL LOADING
    # --------------------------------------------------------------
    async def load_special_pool(self) -> None:
        for client in self.special_clients:
            try:
                client.remove_event_handler(self.special_event_handler, events.NewMessage)
            except Exception:
                pass
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception:
                pass
        self.special_clients.clear()
        self.special_names.clear()
        self.special_ids.clear()

        async for doc in self.db.special_pool_col.find():
            session_str = doc.get("session")
            if not session_str:
                continue
            try:
                client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
                await client.start()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    self.special_clients.append(client)
                    self.special_names.append(doc.get("name", f"Special-{len(self.special_clients)}"))
                    self.special_ids.add(me.id)
                    logger.info(f"✅ Special Pool – '{doc.get('name')}' loaded: @{me.username}")
                    client.add_event_handler(self.special_event_handler, events.NewMessage)
                else:
                    await client.disconnect()
            except Exception as e:
                logger.error(f"❌ Special Pool – failed: {e}")
        logger.info(f"🚀 Special Pool ready: {len(self.special_clients)} clients.")

    # --------------------------------------------------------------
    #  CLIENT SELECTION
    # --------------------------------------------------------------
    async def _get_ninja_client(self, pool: int = 1) -> Optional[TelegramClient]:
        clients = [self.ninja_clients, self.ninja_clients2, self.ninja_clients3]
        pool_clients = clients[pool-1]
        if not pool_clients:
            return None
        candidates = pool_clients.copy()
        random.shuffle(candidates)
        for client in candidates:
            try:
                await client.get_me()
                return client
            except Exception:
                try:
                    await client.connect()
                    await client.get_me()
                    return client
                except Exception:
                    continue
        return None

    async def _get_special_client(self) -> Optional[TelegramClient]:
        if not self.special_clients:
            return None
        for client in self.special_clients:
            try:
                await client.get_me()
                return client
            except Exception:
                continue
        return random.choice(self.special_clients) if self.special_clients else None

    # --------------------------------------------------------------
    #  SPECIAL EVENT HANDLER (STEALTH)
    # --------------------------------------------------------------
    async def special_event_handler(self, event):
        if event.sender_id in self.special_ids:
            return

        chat_id = event.chat_id
        text = event.raw_text or ""

        if chat_id == event.sender_id and text == "ရပ်":
            if self.special_attack_active:
                self.special_attack_active = False
                if self.special_attack_task and not self.special_attack_task.done():
                    self.special_attack_task.cancel()
                client = await self._get_special_client()
                if client:
                    try:
                        await client.send_message(event.sender_id, "🛑 Special attack stopped.")
                    except Exception:
                        pass
                logger.info("Special attack stopped via Saved Messages.")
            return

        if text == "သေမယ်နော်" and event.is_reply:
            if not self.special_clients or self.special_attack_active:
                return
            reply_msg = await event.get_reply_message()
            if not reply_msg:
                return
            target = await reply_msg.get_sender()
            if not target or target.id == Config.OWNER_ID:
                return
            spam_texts = await self.db.special_spam_texts.find().to_list(length=None)
            if not spam_texts:
                return
            self.special_attack_active = True
            self.special_target_chat = chat_id
            self.special_target_mention = self.format_mention(target.id, target.first_name or "Target")
            self.special_spam_texts_list = [doc["text"] for doc in spam_texts]

            client = random.choice(self.special_clients)
            if client:
                try:
                    await client.send_message(client._self_id, f"🔥 Special attack started on {self.special_target_mention} in chat {chat_id}")
                except Exception:
                    pass

            async def attack_loop():
                while self.special_attack_active:
                    client = random.choice(self.special_clients) if self.special_clients else None
                    if not client:
                        await asyncio.sleep(1)
                        continue
                    text_to_send = random.choice(self.special_spam_texts_list)
                    try:
                        await client.send_message(self.special_target_chat, f"{self.special_target_mention} {text_to_send}", parse_mode='html')
                        await asyncio.sleep(Config.SPAM_DELAY)
                    except FloodWaitError as e:
                        await asyncio.sleep(e.seconds + 1)
                    except Exception as e:
                        logger.error(f"Special attack error: {e}")
                        await asyncio.sleep(2)
                logger.info("Special attack loop finished.")
            self.special_attack_task = asyncio.create_task(attack_loop())
            return

    # --------------------------------------------------------------
    #  ADMIN & HELPERS
    # --------------------------------------------------------------
    async def check_admin(self, chat_id: int, user_id: int) -> bool:
        if user_id == Config.OWNER_ID:
            return True
        now = time.time()
        if chat_id in self.admin_cache and now < self.admin_cache[chat_id]["expiry"]:
            return user_id in self.admin_cache[chat_id]["ids"]
        await self._update_admin_cache(chat_id)
        if chat_id in self.admin_cache:
            return user_id in self.admin_cache[chat_id]["ids"]
        return False

    async def _update_admin_cache(self, chat_id: int):
        try:
            admins = await self.bot_client(GetParticipantsRequest(channel=chat_id, filter=ChannelParticipantsAdmins(), offset=0, limit=200, hash=0))
            admin_ids = {p.user_id for p in admins.participants}
            self.admin_cache[chat_id] = {"ids": admin_ids, "expiry": time.time() + 300}
            return admin_ids
        except Exception as e:
            logger.error(f"Error updating admin cache for {chat_id}: {e}")
            return set()

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

    def strip_mentions(self, text: str) -> str:
        if not text: return ""
        text = re.sub(r'<a[^>]*>.*?</a>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'@\w+', '', text)
        return ' '.join(text.split())

    def bq(self, text: str) -> str:
        return f"<blockquote><b>{text}</b></blockquote>"

    # --------------------------------------------------------------
    #  PHRASE
    # --------------------------------------------------------------
    async def fetch_learned_phrases(self) -> List[str]:
        docs = await self.db.learned.find().to_list(length=10000)
        if docs:
            phrases = [doc.get("text") for doc in docs if doc.get("text")]
            if phrases:
                return phrases
        return ["မင်းက ဒီမှာ ပိုလျှံနေတဲ့ အရာပဲ", "ငါတို့ မင်းကို ဖယ်ရှားလိုက်ပြီ"]

    async def get_next_phrase(self, chat_id: int) -> str:
        phrases = self.phrase_lists.get(chat_id)
        if not phrases:
            phrases = await self.fetch_learned_phrases()
            if not phrases:
                phrases = ["မင်းက ဒီမှာ ပိုလျှံနေတဲ့ အရာပဲ"]
            random.shuffle(phrases)
            self.phrase_lists[chat_id] = phrases
            self.phrase_indices[chat_id] = 0
        idx = self.phrase_indices[chat_id]
        phrase = phrases[idx]
        idx += 1
        if idx >= len(phrases):
            random.shuffle(phrases)
            idx = 0
        self.phrase_indices[chat_id] = idx
        return phrase

    def reset_phrase_cycle(self, chat_id: int) -> None:
        self.phrase_lists.pop(chat_id, None)
        self.phrase_indices.pop(chat_id, None)

    # --------------------------------------------------------------
    #  OPTIMAL TALK SYSTEM (Parallel Workers per Client & Group)
    # --------------------------------------------------------------
    async def _load_talk_phrases(self):
        docs = await self.db.talk_phrases.find({"group_id": 0}).to_list(length=10000)
        if docs:
            self.talk_phrase_pool = [doc.get("text") for doc in docs if doc.get("text")]
        if not self.talk_phrase_pool:
            self.talk_phrase_pool = await self.fetch_learned_phrases()
        random.shuffle(self.talk_phrase_pool)

    async def _talk_worker(self, client: TelegramClient, group_id: int):
        while self.talk_running:
            if not self.talk_phrase_pool:
                await self._load_talk_phrases()
                if not self.talk_phrase_pool:
                    await asyncio.sleep(1)
                    continue
            phrase = random.choice(self.talk_phrase_pool)
            try:
                sent = await client.send_message(group_id, phrase)
                await self._handle_message_sent(group_id, sent.id)
                await asyncio.sleep(Config.TALK_DELAY)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                logger.error(f"Talk worker error for {group_id}: {e}")
                await asyncio.sleep(1)

    async def start_talk(self):
        if self.talk_running:
            return
        all_clients = self.ninja_clients + self.ninja_clients2 + self.ninja_clients3
        if not all_clients:
            logger.warning("No ninja clients available for talk.")
            return

        await self._load_talk_phrases()
        if not self.talk_phrase_pool:
            logger.warning("No talk phrases available.")
            return

        self.talk_running = True
        self.talk_workers = []
        groups = Config.SPAM_GROUPS
        if not groups:
            logger.warning("No SPAM_GROUPS defined for talk.")
            self.talk_running = False
            return

        logger.info(f"🚀 Starting TALK workers: {len(all_clients)} clients × {len(groups)} groups")
        for client in all_clients:
            for group in groups:
                task = asyncio.create_task(self._talk_worker(client, group))
                self.talk_workers.append(task)

    async def stop_talk(self):
        if not self.talk_running:
            return
        self.talk_running = False
        for task in self.talk_workers:
            if not task.done():
                task.cancel()
        if self.talk_workers:
            await asyncio.gather(*self.talk_workers, return_exceptions=True)
        self.talk_workers.clear()
        logger.info("🛑 TALK stopped.")

    # --------------------------------------------------------------
    #  AUTO CLEANUP
    # --------------------------------------------------------------
    async def _handle_message_sent(self, chat_id: int, msg_id: int):
        if not self.auto_cleanup:
            return
        if chat_id == Config.LEARNING_GROUP:
            return
        if chat_id not in self.queue_locks:
            self.queue_locks[chat_id] = asyncio.Lock()
        async with self.queue_locks[chat_id]:
            if chat_id not in self.msg_queues:
                self.msg_queues[chat_id] = []
            self.msg_queues[chat_id].append(msg_id)
            if len(self.msg_queues[chat_id]) >= 100:
                ids_to_delete = self.msg_queues[chat_id].copy()
                self.msg_queues[chat_id].clear()
                try:
                    await self.bot_client.delete_messages(chat_id, ids_to_delete)
                    logger.info(f"🗑️ Deleted {len(ids_to_delete)} messages in chat {chat_id}")
                except FloodWaitError as e:
                    asyncio.create_task(self._retry_delete_after(chat_id, ids_to_delete, e.seconds))
                except Exception as e:
                    logger.error(f"Failed to delete: {e}")

    async def _retry_delete_after(self, chat_id: int, ids: List[int], delay: int):
        await asyncio.sleep(delay + 1)
        try:
            await self.bot_client.delete_messages(chat_id, ids)
        except Exception as e:
            logger.error(f"Retry delete failed: {e}")

    # --------------------------------------------------------------
    #  SPAM LOOP (Parallel Fast Mode)
    # --------------------------------------------------------------
    async def _start_spam_loop(self, chat_ids: List[int], pool_number: int = 1) -> None:
        if pool_number == 1:
            task_dict = self.ninja_spam_tasks
            pool_clients = self.ninja_clients
        elif pool_number == 2:
            task_dict = self.ninja_spam_tasks2
            pool_clients = self.ninja_clients2
        else:
            task_dict = self.ninja_spam_tasks3
            pool_clients = self.ninja_clients3

        key = tuple(sorted(chat_ids))
        if task_dict.get(key, False):
            logger.info(f"Spam loop already running for groups {chat_ids} in Pool {pool_number}")
            return
        task_dict[key] = True

        if not pool_clients:
            logger.warning(f"No clients in Ninja Pool {pool_number}; cannot start spam.")
            return

        flood_until = {}
        lock = asyncio.Lock()

        async def send_with_client(client, chat_id):
            async with lock:
                now = datetime.now()
                if client in flood_until and flood_until[client] > now:
                    return False
            try:
                sent = await client.send_message(chat_id, SPAM_TEXT)
                await self._handle_message_sent(chat_id, sent.id)
                return True
            except FloodWaitError as e:
                async with lock:
                    flood_until[client] = datetime.now() + timedelta(seconds=e.seconds + 1)
                logger.warning(f"Flood on client for {e.seconds}s (Pool {pool_number})")
                return False
            except Exception as e:
                logger.error(f"Send error in Pool {pool_number}: {e}")
                return False

        async def spam_loop():
            logger.info(f"🚀 Spam started (Pool {pool_number}): {len(pool_clients)} clients × {len(chat_ids)} groups")
            round_num = 0
            while task_dict.get(key, False):
                round_num += 1
                tasks = []
                for chat_id in chat_ids:
                    client = None
                    for _ in range(3):
                        c = random.choice(pool_clients)
                        async with lock:
                            now = datetime.now()
                            if c not in flood_until or flood_until[c] < now:
                                client = c
                                break
                    if client is None:
                        await asyncio.sleep(0.3)
                        continue
                    tasks.append(send_with_client(client, chat_id))
                if tasks:
                    await asyncio.gather(*tasks)
                await asyncio.sleep(0.05)
                if round_num % 100 == 0:
                    logger.info(f"Spam round {round_num} completed (Pool {pool_number})")
            logger.info(f"🛑 Spam stopped (Pool {pool_number}) for {len(chat_ids)} groups")

        asyncio.create_task(spam_loop())

    # --------------------------------------------------------------
    #  SPAM FILTERS
    # --------------------------------------------------------------
    async def sticker_spam_filter(self, event):
        if not event.sticker or event.is_private:
            return
        all_ids = self.ninja_ids | self.ninja_ids2 | self.ninja_ids3
        if event.sender_id == self.bot_id or event.sender_id in all_ids:
            return
        sender_id = event.sender_id
        chat_id = event.chat_id
        now = datetime.now()
        if sender_id not in self.sticker_spam_data:
            self.sticker_spam_data[sender_id] = {"times": [], "ids": []}
        self.sticker_spam_data[sender_id]["times"].append(now)
        self.sticker_spam_data[sender_id]["ids"].append(event.id)
        one_minute_ago = now - timedelta(seconds=60)
        valid_data = [(t, i) for t, i in zip(self.sticker_spam_data[sender_id]["times"], self.sticker_spam_data[sender_id]["ids"]) if t > one_minute_ago]
        self.sticker_spam_data[sender_id]["times"] = [x[0] for x in valid_data]
        self.sticker_spam_data[sender_id]["ids"] = [x[1] for x in valid_data]
        recent_times = self.sticker_spam_data[sender_id]["times"]
        recent_ids = self.sticker_spam_data[sender_id]["ids"]
        is_admin = await self.check_admin(chat_id, sender_id)
        admin_key = (chat_id, sender_id)
        if len(recent_times) >= 6:
            try:
                await self.bot_client.delete_messages(chat_id, recent_ids)
                sender = await event.get_sender()
                mention = self.format_mention(sender_id, sender.first_name if sender else "User")
                if is_admin:
                    if admin_key not in self.admin_warned_sticker:
                        await event.respond(self.bq(f"⚠️ <b>Admin {mention}</b>, please refrain from spamming stickers. (Only warning!)"), parse_mode='html')
                        self.admin_warned_sticker.add(admin_key)
                else:
                    await self.bot_client.edit_permissions(chat_id, sender_id, send_stickers=False)
                    await event.respond(self.bq(f"{mention} has been restricted from sending stickers due to spam."), parse_mode='html')
                del self.sticker_spam_data[sender_id]
                return
            except Exception as e:
                logger.error(f"Sticker Spam Error: {e}")
        if len(recent_times) >= 3:
            time_diff = (recent_times[-1] - recent_times[-3]).total_seconds()
            if time_diff <= 1.0:
                try:
                    await event.delete()
                    if is_admin and admin_key not in self.admin_warned_sticker:
                        sender = await event.get_sender()
                        mention = self.format_mention(sender_id, sender.first_name if sender else "User")
                        await event.respond(self.bq(f"⚠️ <b>Admin {mention}</b>, please don't spam stickers. (Only warning!)"), parse_mode='html')
                        self.admin_warned_sticker.add(admin_key)
                except Exception as e:
                    logger.error(f"Sticker spam early warning error: {e}")

    async def short_text_spam_filter(self, event):
        if event.is_private or not event.text:
            return
        all_ids = self.ninja_ids | self.ninja_ids2 | self.ninja_ids3
        if event.sender_id == self.bot_id or event.sender_id in all_ids:
            return
        text = event.text.strip()
        if len(text) > 3:
            return
        sender_id = event.sender_id
        chat_id = event.chat_id
        now = datetime.now()
        if sender_id not in self.char_spam_data:
            self.char_spam_data[sender_id] = {"times": [], "ids": []}
        self.char_spam_data[sender_id]["times"].append(now)
        self.char_spam_data[sender_id]["ids"].append(event.id)
        one_minute_ago = now - timedelta(seconds=60)
        valid_data = [(t, i) for t, i in zip(self.char_spam_data[sender_id]["times"], self.char_spam_data[sender_id]["ids"]) if t > one_minute_ago]
        self.char_spam_data[sender_id]["times"] = [x[0] for x in valid_data]
        self.char_spam_data[sender_id]["ids"] = [x[1] for x in valid_data]
        recent_times = self.char_spam_data[sender_id]["times"]
        recent_ids = self.char_spam_data[sender_id]["ids"]
        is_admin = await self.check_admin(chat_id, sender_id)
        admin_key = (chat_id, sender_id)
        if len(recent_times) >= 6:
            try:
                await self.bot_client.delete_messages(chat_id, recent_ids)
                sender = await event.get_sender()
                mention = self.format_mention(sender_id, sender.first_name if sender else "User")
                if is_admin:
                    if admin_key not in self.admin_warned_char:
                        await event.respond(self.bq(f"⚠️ <b>Admin {mention}</b>, please stop spamming short messages. (Only warning!)"), parse_mode='html')
                        self.admin_warned_char.add(admin_key)
                else:
                    await self.bot_client.edit_permissions(chat_id, sender_id, until_date=datetime.now() + timedelta(minutes=5), send_messages=False)
                    await event.respond(self.bq(f"🚫 {mention} has been muted for 5 minutes due to spam."), parse_mode='html')
                del self.char_spam_data[sender_id]
                return
            except Exception as e:
                logger.error(f"Short text spam error: {e}")
        if len(recent_times) == 5:
            try:
                await self.bot_client.delete_messages(chat_id, recent_ids)
                sender = await event.get_sender()
                mention = self.format_mention(sender_id, sender.first_name if sender else "User")
                if is_admin:
                    if admin_key not in self.admin_warned_char:
                        await event.respond(self.bq(f"⚠️ <b>Admin {mention}</b>, stop spam or you'll be warned! (Only warning!)"), parse_mode='html')
                        self.admin_warned_char.add(admin_key)
                else:
                    await event.respond(self.bq(f"⚠️ {mention}, stop spam or you'll be muted for 5 minutes!"), parse_mode='html')
            except Exception as e:
                logger.error(f"Short text spam warning error: {e}")

    async def bio_link_filter(self, event):
        if event.is_private:
            return
        all_ids = self.ninja_ids | self.ninja_ids2 | self.ninja_ids3
        if not event.text or event.sender_id == Config.OWNER_ID or event.sender_id == self.bot_id or event.sender_id in all_ids:
            return
        text, chat_id, sender_id = event.text.strip(), event.chat_id, event.sender_id
        sender = await event.get_sender()
        if text:
            text_lower = text.lower()
            BIO_KEYWORDS = ["bio", "b i o", "biolink", "bio-link", "b-i-o", "tg bio",
                            "ဘိုင်အို", "ဘိုင်-အို", "ဘိုင်-o", "ဘီအိုင်အို", "b.i.o",
                            "ဘိုင်အိုလင့်", "ဘိုင်အိုလင့်ခ်"]
            if any(key in text_lower for key in BIO_KEYWORDS) and not await self.check_admin(chat_id, sender_id):
                try:
                    await event.delete()
                    first_name = sender.first_name if sender else "User"
                    mention = self.format_mention(sender_id, first_name)
                    await event.respond(self.bq(f"⚠️ <b>BIO ALERT</b>\n{mention}, bio links are not allowed.\n⚡ <b>Status:</b> <blockquote expandable>Message deleted 🗑️</blockquote>"), parse_mode='html')
                    return
                except Exception as e:
                    logger.error(f"Bio Filter Error: {e}")
        urls = re.findall(r'(https?://\S+|www\.\S+)', text)
        if urls and not (event.audio or event.voice):
            if await self.check_admin(chat_id, sender_id):
                try:
                    f_msg = await self.bot_client.forward_messages(event.chat_id, event.message)
                    mention = self.format_mention(sender_id, sender.first_name if sender else "User")
                    await f_msg.reply(f"<b>Link posted by Admin {mention}</b>", parse_mode='html')
                    await event.delete()
                except:
                    pass
            else:
                try:
                    await event.delete()
                    mention = self.format_mention(sender_id, sender.first_name if sender else "User")
                    await event.respond(self.bq(f"🤺 {mention}, no links allowed! Deleted."), parse_mode='html')
                except:
                    pass

    FORBIDDEN_SCRIPTS = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff\u0e00-\u0e7f\u0600-\u06ff\uac00-\ud7af]')

    async def global_traffic_processing_matrix(self, event):
        if event.is_private or not event.text:
            return
        all_ids = self.ninja_ids | self.ninja_ids2 | self.ninja_ids3
        if event.sender_id == Config.OWNER_ID or event.sender_id == self.bot_id or event.sender_id in all_ids:
            return
        chat_id = event.chat_id
        sender_id = event.sender_id
        if chat_id == Config.LEARNING_GROUP and not await self.check_admin(chat_id, sender_id):
            if self.FORBIDDEN_SCRIPTS.search(event.text):
                try:
                    await event.delete()
                    sender = await event.get_sender()
                    mention = self.format_mention(sender_id, sender.first_name if sender else "User")
                    await event.respond(self.bq(f"⚠️ <b>LANGUAGE SECURITY</b>\n{mention}, only <b>Burmese, English</b> and <b>Numbers</b> ပဲ ပို့ခွင့်ရှိတယ်. တခြားသော ဘာသာစကားများ ရေးခွင့်မပြုဘူး."), parse_mode='html')
                except Exception:
                    pass

    # --------------------------------------------------------------
    #  COMMAND HANDLERS
    # --------------------------------------------------------------
    def _register_handlers(self):

        # ======== ADDALLOW / ALLOWLIST ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/addallow(?:@\w+)?$"))
        async def add_allow(event):
            try:
                if event.sender_id != Config.OWNER_ID:
                    await event.reply("⛔ Owner သာ သုံးခွင့်ရှိပါတယ်။")
                    return
                reply = await event.get_reply_message()
                if not reply:
                    await event.reply("❓ User ရဲ့ စာကို Reply ထောက်ပြီး သုံးပါ။")
                    return
                user = await reply.get_sender()
                if not user:
                    await event.reply("❌ User မတွေ့ပါ။")
                    return
                await self.db.allowed_users.update_one({"user_id": user.id}, {"$set": {"name": user.first_name or "Unnamed"}}, upsert=True)
                await event.reply(f"✅ {self.format_mention(user.id, user.first_name or 'User')} ကို ခွင့်ပြုလိုက်ပါပြီ။", parse_mode='html')
            except Exception as e:
                logger.error(f"add_allow error: {e}")
                await event.reply(f"⚠️ Error: {str(e)}")

        @self.bot_client.on(events.NewMessage(pattern=r"^/allowlist(?:@\w+)?$"))
        async def allow_list(event):
            try:
                if event.sender_id != Config.OWNER_ID:
                    await event.reply("⛔ Owner သာ သုံးခွင့်ရှိပါတယ်။")
                    return
                users = await self.db.allowed_users.find().to_list(length=None)
                if not users:
                    await event.reply("📭 စာရင်းမရှိသေးပါ။")
                    return
                lines = [f"• {self.format_mention(u['user_id'], u.get('name', 'Unknown'))} (<code>{u['user_id']}</code>)" for u in users]
                await event.reply("<b>👑 ခွင့်ပြုထားသော စာရင်း</b>\n\n" + "\n".join(lines), parse_mode="html")
            except Exception as e:
                logger.error(f"allow_list error: {e}")
                await event.reply(f"⚠️ Error: {str(e)}")

        # ======== /del (AUTO CLEANUP) ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/del$"))
        async def del_command(event):
            if event.sender_id != Config.OWNER_ID:
                await event.reply("⛔ Owner သာ သုံးခွင့်ရှိပါတယ်။")
                return
            self.auto_cleanup = not self.auto_cleanup
            status = "ON" if self.auto_cleanup else "OFF"
            await event.reply(f"🔄 Auto‑Cleanup is now **{status}**.\n• Deletion queue uses in-memory cache (No DB writes).\n• Every 100 messages sent by any Ninja will be bulk-deleted.", parse_mode='markdown')

        # ======== SAVE SYSTEM ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/save on$"))
        async def save_on(event):
            if event.chat_id != Config.LEARNING_GROUP or not await self.is_allowed(event.sender_id):
                return
            self.save_status = True
            try: await event.delete()
            except: pass
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"✅ Save mode ON by {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')}", parse_mode='html')

        @self.bot_client.on(events.NewMessage(pattern=r"^/save off$"))
        async def save_off(event):
            if event.chat_id != Config.LEARNING_GROUP or not await self.is_allowed(event.sender_id):
                return
            self.save_status = False
            try: await event.delete()
            except: pass
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"⏸️ Save mode OFF by {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')}", parse_mode='html')

        @self.bot_client.on(events.NewMessage(pattern=r"^/clearlearned$"))
        async def clear_learned(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await event.reply("⚠️ Type `/clearlearned_confirm` to delete ALL learned phrases.")
        @self.bot_client.on(events.NewMessage(pattern=r"^/clearlearned_confirm$"))
        async def clear_learned_confirm(event):
            if event.sender_id != Config.OWNER_ID:
                return
            result = await self.db.learned.delete_many({})
            await event.reply(f"🗑️ Cleared {result.deleted_count} phrases.")
            self.phrase_lists.clear(); self.phrase_indices.clear()

        # ======== ATTACK COMMANDS – NINJA POOL 1 ========
        @self.bot_client.on(events.NewMessage(pattern=r"^(/bully|အနိုင်ကျင့်)$"))
        async def ninja_bully(event):
            if not await self.is_allowed(event.sender_id): return
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"🔫 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used /bully", parse_mode='html')
            try: await event.delete()
            except: pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply: return
            target = await reply.get_sender()
            if target.id == Config.OWNER_ID: return
            chat_id = event.chat_id; target_id = target.id; mention = self.format_mention(target_id, target.first_name or "Target")
            self.reset_phrase_cycle(chat_id); self.ninja_bully_tasks[chat_id] = True
            async def bully_loop():
                while self.ninja_bully_tasks.get(chat_id, False):
                    client = await self._get_ninja_client(1)
                    if not client: await asyncio.sleep(1); continue
                    phrase = await self.get_next_phrase(chat_id)
                    try:
                        sent = await client.send_message(chat_id, f"{mention} {phrase}", reply_to=reply.id, parse_mode='html')
                        await self._handle_message_sent(chat_id, sent.id)
                        await asyncio.sleep(Config.BULLY_DELAY)
                    except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
                    except Exception as e: logger.error(f"Bully error: {e}"); await asyncio.sleep(1)
            asyncio.create_task(bully_loop())

        @self.bot_client.on(events.NewMessage(pattern=r"^(/mark|မှတ်|/shoot|ပစ်)$"))
        async def attack_cmds(event):
            if not await self.is_allowed(event.sender_id): return
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"🔫 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used {event.text}", parse_mode='html')
            try: await event.delete()
            except: pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply or reply.sender_id == Config.OWNER_ID: return
            chat_id = event.chat_id; target = await reply.get_sender(); target_id = target.id; mention = self.format_mention(target_id, target.first_name or "Target")
            if event.text in ("/shoot", "ပစ်"):
                self.ninja_shoot_tasks[chat_id] = True; self.reset_phrase_cycle(chat_id)
                async def shoot_loop():
                    while self.ninja_shoot_tasks.get(chat_id, False):
                        client = await self._get_ninja_client(1)
                        if not client: await asyncio.sleep(1); continue
                        phrase = await self.get_next_phrase(chat_id)
                        try:
                            sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                            await self._handle_message_sent(chat_id, sent.id)
                            await asyncio.sleep(Config.SHOOT_DELAY)
                        except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
                        except Exception as e: logger.error(f"Shoot error: {e}"); await asyncio.sleep(1)
                asyncio.create_task(shoot_loop())
            else:
                sender = await event.get_sender()
                sender_mention = self.format_mention(event.sender_id, sender.first_name or "Unknown")
                sent = await self.bot_client.send_message(chat_id, f"🎯 {sender_mention} marked {mention} for termination.", parse_mode='html')
                await self._handle_message_sent(chat_id, sent.id)

        @self.bot_client.on(events.NewMessage(pattern=r"^(/track|ခြေရာ)$"))
        async def track(event):
            if not await self.is_allowed(event.sender_id): return
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"🎯 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used /track", parse_mode='html')
            try: await event.delete()
            except: pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply or reply.sender_id == Config.OWNER_ID: return
            target = await reply.get_sender(); chat_id = event.chat_id
            self.ninja_tracking_targets[chat_id] = target.id
            mention = self.format_mention(target.id, target.first_name or "Target")
            self.reset_phrase_cycle(chat_id)
            sent = await event.reply(f"🔭 Tracking {mention}...", parse_mode='html')
            await self._handle_message_sent(chat_id, sent.id)

        # ======== SPAM COMMANDS ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/spam$"))
        async def spam_cmd(event):
            if not await self.is_allowed(event.sender_id):
                return
            groups = Config.SPAM_GROUPS
            if not groups:
                await event.reply("❌ No spam groups defined in Config.SPAM_GROUPS.")
                return
            await self._start_spam_loop(groups, 1)
            await event.reply(f"🗣️ Spam started on {len(groups)} groups using Ninja Pool 1 (Fast Parallel Mode).")

        @self.bot_client.on(events.NewMessage(pattern=r"^/spam2$"))
        async def spam_cmd2(event):
            if not await self.is_allowed(event.sender_id):
                return
            groups = Config.SPAM_GROUPS
            if not groups:
                await event.reply("❌ No spam groups defined.")
                return
            await self._start_spam_loop(groups, 2)
            await event.reply(f"🗣️ Spam started on {len(groups)} groups using Ninja Pool 2 (Fast Parallel Mode).")

        @self.bot_client.on(events.NewMessage(pattern=r"^/spam3$"))
        async def spam_cmd3(event):
            if not await self.is_allowed(event.sender_id):
                return
            groups = Config.SPAM_GROUPS
            if not groups:
                await event.reply("❌ No spam groups defined.")
                return
            await self._start_spam_loop(groups, 3)
            await event.reply(f"🗣️ Spam started on {len(groups)} groups using Ninja Pool 3 (Fast Parallel Mode).")

        # ======== TAUNT ========
        @self.bot_client.on(events.NewMessage(pattern=r"^ဖာသည်မသား$"))
        async def delete_and_taunt(event):
            if not await self.is_allowed(event.sender_id): return
            try: await event.delete()
            except: pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply: return
            target = await reply.get_sender()
            if target.id == Config.OWNER_ID: return
            chat_id = event.chat_id; target_id = target.id; mention = self.format_mention(target_id, target.first_name or "Target")
            try: await self.bot_client.delete_messages(chat_id, [reply.id])
            except: pass
            await self._add_taunt_target(chat_id, target_id)
            client = await self._get_ninja_client(1)
            if client:
                phrase = await self.get_next_phrase(chat_id)
                try:
                    sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                    await self._handle_message_sent(chat_id, sent.id)
                except: pass

        @self.bot_client.on(events.NewMessage(pattern=r"^/remove_taunt(?:\s+(\d+))?$"))
        async def remove_taunt(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id; target_id = event.pattern_match.group(1)
            if target_id:
                target_id = int(target_id)
                await self._remove_taunt_target(chat_id, target_id)
                await event.reply(f"✅ {self.format_mention(target_id, 'User')} (ID: `{target_id}`) ကို ဖယ်ရှားလိုက်ပါပြီ။", parse_mode='html')
            else:
                if not event.is_reply:
                    await event.reply("❌ ဖယ်ရှားချင်တဲ့ ပစ်မှတ် ID ကို `/remove_taunt <ID>` နဲ့ထည့်ပါ သို့မဟုတ် သူ့စာကို Reply ထောက်ပါ။")
                    return
                reply = await event.get_reply_message(); target = await reply.get_sender()
                await self._remove_taunt_target(chat_id, target.id)
                await event.reply(f"✅ {self.format_mention(target.id, target.first_name or 'Target')} ကို ဖယ်ရှားလိုက်ပါပြီ။", parse_mode='html')

        @self.bot_client.on(events.NewMessage(pattern=r"^/clear_taunts(?:\s+(-?\d+))?$"))
        async def clear_taunts(event):
            if not await self.is_allowed(event.sender_id): return
            target_chat_id = event.pattern_match.group(1)
            if target_chat_id:
                target_chat_id = int(target_chat_id)
                await self._clear_taunt_targets(target_chat_id)
                await event.reply(f"🧹 Chat ID `{target_chat_id}` ထဲက အားလုံးကို ရှင်းလိုက်ပါပြီ။")
            else:
                chat_id = event.chat_id
                await self._clear_taunt_targets(chat_id)
                await event.reply("🧹 ဒီ Chat ထဲက အားလုံးကို ရှင်းလိုက်ပါပြီ။")

        # ======== STOP COMMAND (Owner can stop talk) ========
        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop)$"))
        async def stop_attack(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id
            stopped = False
            
            # Stop Pool 1 attacks
            if chat_id in self.ninja_bully_tasks: self.ninja_bully_tasks[chat_id] = False; stopped = True
            if chat_id in self.ninja_shoot_tasks: self.ninja_shoot_tasks[chat_id] = False; stopped = True
            if chat_id in self.ninja_tracking_targets: del self.ninja_tracking_targets[chat_id]; stopped = True
            if chat_id in self.ninja_dark_passenger_targets: del self.ninja_dark_passenger_targets[chat_id]; stopped = True
            for key in list(self.ninja_spam_tasks.keys()):
                if chat_id in key:
                    self.ninja_spam_tasks[key] = False
                    stopped = True
                    
            # Stop Pool 2 spam
            for key in list(self.ninja_spam_tasks2.keys()):
                if chat_id in key:
                    self.ninja_spam_tasks2[key] = False
                    stopped = True
                    
            # Stop Pool 3 spam
            for key in list(self.ninja_spam_tasks3.keys()):
                if chat_id in key:
                    self.ninja_spam_tasks3[key] = False
                    stopped = True

            # Stop TALK only if sender is OWNER
            if self.talk_running:
                if event.sender_id == Config.OWNER_ID:
                    await self.stop_talk()
                    stopped = True
                else:
                    await event.reply("ℹ️ Talk can only be stopped by Owner. Other attacks stopped for this chat.")

            self.reset_phrase_cycle(chat_id)
            
            if stopped:
                await event.reply("🛑 Stopped your active attacks (bully/shoot/track/spam) in this chat.")
            else:
                if not self.talk_running:
                    await event.reply("ℹ️ No active attacks to stop for you.")

        # ======== TALK PHRASE MANAGEMENT ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/addtalkphrase(?:\s+(.+))?$"))
        async def add_talk_phrase(event):
            if event.sender_id != Config.OWNER_ID:
                return
            text = event.pattern_match.group(1)
            if not text and event.is_reply:
                reply = await event.get_reply_message()
                if reply and reply.text:
                    text = reply.text.strip()
            if not text:
                await event.reply("❌ Usage: `/addtalkphrase <text>` or reply to a message.")
                return
            group_id = 0
            try:
                await self.db.talk_phrases.update_one({"group_id": group_id, "text": text}, {"$set": {"group_id": group_id, "text": text}}, upsert=True)
                await event.reply(f"✅ Talk phrase added (group {group_id}).")
                await self._load_talk_phrases()
            except DuplicateKeyError:
                await event.reply("⚠️ Phrase already exists.")
            except Exception as e:
                await event.reply(f"❌ Error: {e}")

        @self.bot_client.on(events.NewMessage(pattern=r"^/listtalkphrases$"))
        async def list_talk_phrases(event):
            if event.sender_id != Config.OWNER_ID:
                return
            group_id = 0
            docs = await self.db.talk_phrases.find({"group_id": group_id}).to_list(length=100)
            if not docs:
                await event.reply("📭 No talk phrases.")
                return
            lines = [f"{i+1}. {d['text']}" for i, d in enumerate(docs)]
            await event.reply("📝 **Talk Phrases (group 0)**\n\n" + "\n".join(lines[:30]), parse_mode='markdown')

        # ======== /talk ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/talk$"))
        async def talk_command(event):
            if not await self.is_allowed(event.sender_id):
                return
            if self.talk_running:
                await event.reply("⚠️ Talk is already running.")
                return
            groups = Config.SPAM_GROUPS
            if not groups:
                await event.reply("❌ No SPAM_GROUPS defined for talk.")
                return
            await self.start_talk()
            await event.reply(f"🗣️ Talk started on **{len(groups)} groups** (all ninja clients).\nOnly Owner can stop it using `ရပ်` or `/stoptalk`.")

        # ======== /stoptalk (Only Owner) ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/stoptalk$"))
        async def stoptalk_command(event):
            if event.sender_id != Config.OWNER_ID:
                await event.reply("⛔ Only owner can stop talk.")
                return
            if not self.talk_running:
                await event.reply("ℹ️ Talk is not running.")
                return
            await self.stop_talk()
            await event.reply("🛑 Talk stopped.")

        # ======== NINJA POOL MANAGEMENT – POOL 1 ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/addninja(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_ninja(event):
            if event.sender_id != Config.OWNER_ID: return
            cmd_args = event.pattern_match.group(1); session_str = event.pattern_match.group(2)
            name = cmd_args if cmd_args and not session_str else "Ninja"
            if not session_str:
                reply = await event.get_reply_message()
                if reply and reply.text:
                    session_str = reply.text.strip()
                    if cmd_args and not cmd_args.startswith("session"):
                        name = cmd_args
                else:
                    await event.reply("❓ Usage: `/addninja <name> <session_string>`")
                    return
            if not session_str or len(session_str) < 10:
                await event.reply("❌ Invalid session string.")
                return
            async for doc in self.db.ninja_col.find():
                if doc.get("session") == session_str:
                    await event.reply("⚠️ This session already exists in Ninja Pool 1.")
                    return
            await self.db.ninja_col.insert_one({"name": name, "session": session_str})
            client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            try:
                await client.start(); me = await client.get_me()
                self.ninja_clients.append(client); self.ninja_names.append(name); self.ninja_ids.add(me.id)
                await event.reply(f"✅ '{name}' (ID: {me.id}) added to Ninja Pool 1! Total: {len(self.ninja_clients)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {str(e)}")
                await self.db.ninja_col.delete_one({"session": session_str})

        @self.bot_client.on(events.NewMessage(pattern=r"^/listninja$"))
        async def list_ninja(event):
            if event.sender_id != Config.OWNER_ID: return
            if not self.ninja_clients:
                await event.reply("📭 No Ninjas active in Pool 1.")
                return
            online = 0
            lines = [f"👥 **Ninja Pool 1 ({len(self.ninja_clients)} loaded)**"]
            for i, (client, name) in enumerate(zip(self.ninja_clients, self.ninja_names)):
                try:
                    me = await client.get_me()
                    online += 1
                    full_name = f"{me.first_name or ''} {me.last_name or ''}".strip() or "No Name"
                    username = f"(@{me.username})" if me.username else ""
                    lines.append(f"  {i+1}. **{full_name}** {username} (ID: `{me.id}`) ✅")
                except:
                    lines.append(f"  {i+1}. **{name}** – (offline) ❌")
            lines.append(f"\n📊 Online: {online}/{len(self.ninja_clients)}")
            await event.reply("\n".join(lines), parse_mode='markdown')

        @self.bot_client.on(events.NewMessage(pattern=r"^/removeninja\s+(.+)$"))
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
                await event.reply(f"❌ Cannot find '{target}' in Ninja Pool 1.")
                return
            removed_doc = pr_list[idx]
            await self.db.ninja_col.delete_one({"_id": removed_doc["_id"]})
            if idx < len(self.ninja_clients):
                client = self.ninja_clients.pop(idx); self.ninja_names.pop(idx)
                try: await client.disconnect()
                except: pass
                await event.reply(f"✅ Removed '{removed_doc.get('name')}' from Ninja Pool 1.")
            else:
                await event.reply(f"✅ Removed from DB.")

        # ======== NINJA POOL MANAGEMENT – POOL 2 ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/addninja2(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_ninja2(event):
            if event.sender_id != Config.OWNER_ID: return
            cmd_args = event.pattern_match.group(1); session_str = event.pattern_match.group(2)
            name = cmd_args if cmd_args and not session_str else "Ninja2"
            if not session_str:
                reply = await event.get_reply_message()
                if reply and reply.text:
                    session_str = reply.text.strip()
                    if cmd_args and not cmd_args.startswith("session"):
                        name = cmd_args
                else:
                    await event.reply("❓ Usage: `/addninja2 <name> <session_string>`")
                    return
            if not session_str or len(session_str) < 10:
                await event.reply("❌ Invalid session string.")
                return
            async for doc in self.db.ninja_col2.find():
                if doc.get("session") == session_str:
                    await event.reply("⚠️ This session already exists in Ninja Pool 2.")
                    return
            await self.db.ninja_col2.insert_one({"name": name, "session": session_str})
            client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            try:
                await client.start(); me = await client.get_me()
                self.ninja_clients2.append(client); self.ninja_names2.append(name); self.ninja_ids2.add(me.id)
                await event.reply(f"✅ '{name}' (ID: {me.id}) added to Ninja Pool 2! Total: {len(self.ninja_clients2)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {str(e)}")
                await self.db.ninja_col2.delete_one({"session": session_str})

        @self.bot_client.on(events.NewMessage(pattern=r"^/removeninja2\s+(.+)$"))
        async def remove_ninja2(event):
            if event.sender_id != Config.OWNER_ID: return
            target = event.pattern_match.group(1).strip()
            pr_list = await self.db.ninja_col2.find().to_list(length=None)
            idx = None
            if target.isdigit(): idx = int(target) - 1
            else:
                for i, doc in enumerate(pr_list):
                    if doc.get("name") == target:
                        idx = i; break
            if idx is None or idx < 0 or idx >= len(pr_list):
                await event.reply(f"❌ Cannot find '{target}' in Ninja Pool 2.")
                return
            removed_doc = pr_list[idx]
            await self.db.ninja_col2.delete_one({"_id": removed_doc["_id"]})
            if idx < len(self.ninja_clients2):
                client = self.ninja_clients2.pop(idx); self.ninja_names2.pop(idx)
                try: await client.disconnect()
                except: pass
                await event.reply(f"✅ Removed '{removed_doc.get('name')}' from Ninja Pool 2.")
            else:
                await event.reply(f"✅ Removed from DB.")

        # ======== NINJA POOL MANAGEMENT – POOL 3 ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/addninja3(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_ninja3(event):
            if event.sender_id != Config.OWNER_ID: return
            cmd_args = event.pattern_match.group(1); session_str = event.pattern_match.group(2)
            name = cmd_args if cmd_args and not session_str else "Ninja3"
            if not session_str:
                reply = await event.get_reply_message()
                if reply and reply.text:
                    session_str = reply.text.strip()
                    if cmd_args and not cmd_args.startswith("session"):
                        name = cmd_args
                else:
                    await event.reply("❓ Usage: `/addninja3 <name> <session_string>`")
                    return
            if not session_str or len(session_str) < 10:
                await event.reply("❌ Invalid session string.")
                return
            async for doc in self.db.ninja_col3.find():
                if doc.get("session") == session_str:
                    await event.reply("⚠️ This session already exists in Ninja Pool 3.")
                    return
            await self.db.ninja_col3.insert_one({"name": name, "session": session_str})
            client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            try:
                await client.start(); me = await client.get_me()
                self.ninja_clients3.append(client); self.ninja_names3.append(name); self.ninja_ids3.add(me.id)
                await event.reply(f"✅ '{name}' (ID: {me.id}) added to Ninja Pool 3! Total: {len(self.ninja_clients3)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {str(e)}")
                await self.db.ninja_col3.delete_one({"session": session_str})

        @self.bot_client.on(events.NewMessage(pattern=r"^/removeninja3\s+(.+)$"))
        async def remove_ninja3(event):
            if event.sender_id != Config.OWNER_ID: return
            target = event.pattern_match.group(1).strip()
            pr_list = await self.db.ninja_col3.find().to_list(length=None)
            idx = None
            if target.isdigit(): idx = int(target) - 1
            else:
                for i, doc in enumerate(pr_list):
                    if doc.get("name") == target:
                        idx = i; break
            if idx is None or idx < 0 or idx >= len(pr_list):
                await event.reply(f"❌ Cannot find '{target}' in Ninja Pool 3.")
                return
            removed_doc = pr_list[idx]
            await self.db.ninja_col3.delete_one({"_id": removed_doc["_id"]})
            if idx < len(self.ninja_clients3):
                client = self.ninja_clients3.pop(idx); self.ninja_names3.pop(idx)
                try: await client.disconnect()
                except: pass
                await event.reply(f"✅ Removed '{removed_doc.get('name')}' from Ninja Pool 3.")
            else:
                await event.reply(f"✅ Removed from DB.")

        # ======== SPECIAL POOL MANAGEMENT ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/addspecial(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_special(event):
            if event.sender_id != Config.OWNER_ID:
                return
            cmd_args = event.pattern_match.group(1)
            session_str = event.pattern_match.group(2)
            name = cmd_args if cmd_args and not session_str else "SpecialPR"
            if not session_str:
                reply = await event.get_reply_message()
                if reply and reply.text:
                    session_str = reply.text.strip()
                    if cmd_args and not cmd_args.startswith("session"):
                        name = cmd_args
                else:
                    await event.reply("❓ Usage: `/addspecial <name> <session_string>`")
                    return
            if not session_str or len(session_str) < 10:
                await event.reply("❌ Invalid session string.")
                return
            async for doc in self.db.special_pool_col.find():
                if doc.get("session") == session_str:
                    await event.reply("⚠️ This session already exists in Special Pool.")
                    return
            await self.db.special_pool_col.insert_one({"name": name, "session": session_str})
            client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            try:
                await client.start()
                me = await client.get_me()
                self.special_clients.append(client)
                self.special_names.append(name)
                self.special_ids.add(me.id)
                client.add_event_handler(self.special_event_handler, events.NewMessage)
                await event.reply(f"✅ '{name}' (ID: {me.id}) added to Special Pool! Total: {len(self.special_clients)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {str(e)}")
                await self.db.special_pool_col.delete_one({"session": session_str})

        @self.bot_client.on(events.NewMessage(pattern=r"^/listspecial$"))
        async def list_special(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.special_clients:
                await event.reply("📭 No Special clients active.")
                return
            lines = [f"👥 **Special Pool ({len(self.special_clients)})**"]
            for i, (client, name) in enumerate(zip(self.special_clients, self.special_names)):
                try:
                    me = await client.get_me()
                    lines.append(f"  {i+1}. **{name}** – @{me.username} (ID: {me.id})")
                except:
                    lines.append(f"  {i+1}. **{name}** – (offline)")
            await event.reply("\n".join(lines), parse_mode='markdown')

        @self.bot_client.on(events.NewMessage(pattern=r"^/removespecial\s+(.+)$"))
        async def remove_special(event):
            if event.sender_id != Config.OWNER_ID:
                return
            target = event.pattern_match.group(1).strip()
            pr_list = await self.db.special_pool_col.find().to_list(length=None)
            idx = None
            if target.isdigit():
                idx = int(target) - 1
            else:
                for i, doc in enumerate(pr_list):
                    if doc.get("name") == target:
                        idx = i; break
            if idx is None or idx < 0 or idx >= len(pr_list):
                await event.reply(f"❌ Cannot find '{target}' in Special Pool.")
                return
            removed_doc = pr_list[idx]
            await self.db.special_pool_col.delete_one({"_id": removed_doc["_id"]})
            if idx < len(self.special_clients):
                client = self.special_clients.pop(idx)
                self.special_names.pop(idx)
                try:
                    client.remove_event_handler(self.special_event_handler, events.NewMessage)
                    await client.disconnect()
                except:
                    pass
                await event.reply(f"✅ Removed '{removed_doc.get('name')}' from Special Pool.")
            else:
                await event.reply(f"✅ Removed from DB.")

        # ======== SPECIAL SAVE MODE ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/savespecial (on|off)$"))
        async def save_special_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            mode = event.pattern_match.group(1)
            if mode == "on":
                self.special_save_mode = True
                await event.reply("✅ Special Save Mode: ON – Send me texts (forward or direct) to save as spam.")
            else:
                self.special_save_mode = False
                await event.reply("❌ Special Save Mode: OFF")

        # ======== /go (Join group using Ninja Pool 1) ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/go$"))
        async def go_group(event):
            if event.sender_id != Config.OWNER_ID: return
            if not event.is_reply:
                await event.reply("❌ `/go` must be used in reply to an invite link.")
                return
            reply = await event.get_reply_message()
            if not reply.text:
                await event.reply("❌ No text in reply.")
                return
            link_match = re.search(r'(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)', reply.text)
            if not link_match:
                await event.reply("❌ No valid invite link found.")
                return
            invite_link = link_match.group(0)
            if 'joinchat/' in invite_link:
                hash_part = invite_link.split('joinchat/')[1].split('?')[0]
            elif '+' in invite_link:
                hash_part = invite_link.split('+')[1].split('?')[0]
            else:
                hash_part = None
            if not hash_part:
                await event.reply("❌ Could not extract hash.")
                return
            all_clients = self.ninja_clients.copy()
            if not all_clients:
                await event.reply("❌ No ninja clients in Pool 1.")
                return
            await event.reply(f"⏳ Joining group with {len(all_clients)} clients (Ninja Pool 1)...")
            success = 0
            for client in all_clients:
                try:
                    await client(ImportChatInviteRequest(hash_part)); success += 1
                except errors.rpcerrorlist.UserAlreadyParticipantError: success += 1
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                    try:
                        await client(ImportChatInviteRequest(hash_part)); success += 1
                    except: pass
                except Exception as e: logger.error(f"Join error: {e}")
                await asyncio.sleep(0.3)
            try:
                chat = await all_clients[0].get_entity(invite_link)
                await event.reply(f"✅ Joined group `{chat.title}` with {success} clients. ID: `{chat.id}`")
            except:
                await event.reply(f"✅ Joined with {success} clients, but couldn't fetch ID.")

        # ======== STATUS ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/status$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID: return
            taunt_count = sum(len(s) for s in self.delete_and_taunt_targets.values())
            learned_count = await self.db.learned.count_documents({})
            talk_phrases_count = await self.db.talk_phrases.count_documents({})
            msg = (
                f"📊 **Status**\n"
                f"🤖 Ninja Pool1: {len(self.ninja_clients)}\n"
                f"🤖 Ninja Pool2: {len(self.ninja_clients2)}\n"
                f"🤖 Ninja Pool3: {len(self.ninja_clients3)}\n"
                f"🤖 Special: {len(self.special_clients)}\n"
                f"🗂️ Learned: {learned_count}\n"
                f"💾 Save: {'ON' if self.save_status else 'OFF'}\n"
                f"🔄 Cleanup: {'ON' if self.auto_cleanup else 'OFF'}\n"
                f"🗣️ Talk Running: {'✅' if self.talk_running else '❌'}\n"
                f"👹 Taunts: {taunt_count}"
            )
            await event.reply(msg, parse_mode='markdown')

        # ======== REMOVEALLOW ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/removeallow(?:@\w+)?\s+(\d+)$"))
        async def remove_allow(event):
            if event.sender_id != Config.OWNER_ID: return
            target_id = int(event.pattern_match.group(1))
            result = await self.db.allowed_users.delete_one({"user_id": target_id})
            await event.reply("✅ Removed" if result.deleted_count else "⚠️ Not found")

        # ======== UNIVERSAL WATCHER ========
        @self.bot_client.on(events.NewMessage())
        async def watcher(event):
            if event.is_private: return
            all_ids = self.ninja_ids | self.ninja_ids2 | self.ninja_ids3
            if event.sender_id == self.bot_id or event.sender_id in all_ids:
                return
            chat_id = event.chat_id; sender_id = event.sender_id

            # SPECIAL SAVE MODE
            if self.special_save_mode and sender_id == Config.OWNER_ID:
                if event.text and not event.text.startswith('/'):
                    text = event.text.strip()
                    if text:
                        try:
                            await self.db.special_spam_texts.insert_one({"text": text})
                            await event.reply(f"✅ Special spam saved: {text[:50]}...")
                        except DuplicateKeyError:
                            await event.reply("⚠️ This text already exists.")
                        except Exception as e:
                            await event.reply(f"❌ Error saving: {e}")
                        return

            # Dark Passenger (only pool 1)
            if chat_id in self.ninja_dark_passenger_targets and sender_id == self.ninja_dark_passenger_targets[chat_id]:
                if event.text and not event.text.startswith(('/', '.', 'မှတ်')):
                    client = await self._get_ninja_client(1)
                    if client:
                        try:
                            await client.delete_messages(chat_id, [event.id])
                            target = await event.get_sender()
                            mention = self.format_mention(sender_id, target.first_name or "Target")
                            taunt_list = await self.get_shadow_taunts()
                            taunt = random.choice(taunt_list).format(mention=mention)
                            sent = await event.reply(taunt, parse_mode='html')
                            await self._handle_message_sent(chat_id, sent.id)
                        except: pass
                return

            # Delete and Taunt
            if chat_id in self.delete_and_taunt_targets and sender_id in self.delete_and_taunt_targets[chat_id]:
                if event.text:
                    client = await self._get_ninja_client(1)
                    if client:
                        try:
                            await client.delete_messages(chat_id, [event.id])
                            target = await event.get_sender()
                            mention = self.format_mention(sender_id, target.first_name or "Target")
                            phrase = await self.get_next_phrase(chat_id)
                            sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                            await self._handle_message_sent(chat_id, sent.id)
                        except: pass
                return

            # Save System
            if chat_id == Config.LEARNING_GROUP and self.save_status:
                if not await self.is_allowed(sender_id): return
                text = None
                if event.text: text = event.text
                if event.message and event.message.forward:
                    try:
                        if hasattr(event.message.forward, 'original') and event.message.forward.original:
                            orig = event.message.forward.original
                            if hasattr(orig, 'text') and orig.text:
                                text = orig.text
                    except: pass
                if not text and event.raw_text: text = event.raw_text
                if text:
                    cleaned = re.sub(r'<[^>]+>', '', text)
                    cleaned = re.sub(r'@\w+', '', cleaned)
                    cleaned = re.sub(r't\.me/\S+', '', cleaned)
                    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
                    if cleaned and len(cleaned) >= 3:
                        try:
                            await self.db.learned.insert_one({"group_id": chat_id, "user_id": sender_id, "text": cleaned, "timestamp": datetime.utcnow()})
                        except DuplicateKeyError: pass
                        except Exception as e: logger.error(f"Save error: {e}")

            # Tracking (only pool 1)
            if chat_id in self.ninja_tracking_targets and sender_id == self.ninja_tracking_targets[chat_id]:
                target = await event.get_sender()
                mention = self.format_mention(sender_id, target.first_name or "Target")
                client = await self._get_ninja_client(1)
                if client:
                    phrase = await self.get_next_phrase(chat_id)
                    try:
                        sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                        await self._handle_message_sent(chat_id, sent.id)
                    except: pass

            # Custom Filters
            if event.text:
                text_lower = event.text.lower().strip()
                async for f in self.db.custom_filters.find():
                    kw = f["keyword"].lower().strip()
                    if text_lower == kw or f" {kw} " in f" {text_lower} ":
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
                    client = await self._get_ninja_client(1)
                    if client:
                        phrase = await self.get_next_phrase(chat_id)
                        mention = self.format_mention(event.sender_id, (await event.get_sender()).first_name or "Unknown")
                        sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                        await self._handle_message_sent(chat_id, sent.id)
                    return
                if not await self.is_allowed(sender_id):
                    sent = await self.bot_client.send_message(chat_id, f"⛔ {(await event.get_sender()).first_name or 'User'}, you lack authority.")
                    await self._handle_message_sent(chat_id, sent.id)

        # ======== SPAM FILTER HANDLERS ========
        @self.bot_client.on(events.NewMessage)
        async def sticker_spam_handler(event): await self.sticker_spam_filter(event)
        @self.bot_client.on(events.NewMessage)
        async def short_text_spam_handler(event): await self.short_text_spam_filter(event)
        @self.bot_client.on(events.NewMessage)
        async def bio_link_handler(event): await self.bio_link_filter(event)
        @self.bot_client.on(events.NewMessage(incoming=True))
        async def language_filter_handler(event): await self.global_traffic_processing_matrix(event)

    # --------------------------------------------------------------
    #  HELPER FOR SHADOW TAUNTS
    # --------------------------------------------------------------
    async def get_shadow_taunts(self) -> List[str]:
        doc = await self.db.system_col.find_one({"key": "shadow_taunts"})
        if doc and doc.get("value"):
            return doc["value"]
        return ["မင်းရဲ့စကားတွေက ဘယ်သူမှ မှတ်မိမှာမဟုတ်ဘူး"]

    # --------------------------------------------------------------
    #  STARTUP & SHUTDOWN
    # --------------------------------------------------------------
    async def start(self) -> None:
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        me = await self.bot_client.get_me()
        self.bot_id = me.id
        logger.info(f"🤖 Main bot started as @{me.username} (ID: {self.bot_id})")
        logger.info(f"📌 Learning Group: {Config.LEARNING_GROUP}")

        await self.load_ninja_pools()
        await self.load_special_pool()
        await self.load_taunt_targets()

        threading.Thread(target=run_flask, daemon=True).start()
        await self.bot_client.run_until_disconnected()

    async def stop(self) -> None:
        if self.talk_running:
            await self.stop_talk()
        if self.bot_client.is_connected():
            await self.bot_client.disconnect()
        for client in self.ninja_clients + self.ninja_clients2 + self.ninja_clients3:
            try:
                await client.disconnect()
            except:
                pass
        for client in self.special_clients:
            try:
                await client.disconnect()
            except:
                pass
        await self.db.close()
        logger.info("🛑 System shutdown complete.")

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
        logger.info("Shutdown signal received.")
    finally:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
