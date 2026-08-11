#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sovereign System – ULTIMATE FULL VERSION (Pool 1, 2, 3 + Spam + Auto-Cleanup)
- 3 Independent Power Ranger Pools (collections: powerranger_col, _col2, _col3)
- Commands: /addpr, /addpr2, /addpr3; /bully, /bully2, /bully3; etc.
- Spam commands: /spam, /spam2, /spam3 – sends hardcoded text only (NO DB).
- Auto-Cleanup (/del) uses in-memory cache (NO DB writes per message) for optimal performance.
- All original features: save, talk, catcher bot, watchlist, taunts, spam filters, moderation, etc.
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
from typing import Dict, List, Optional, Set

import pytz
from flask import Flask
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, OperationFailure, DuplicateKeyError
from telethon import TelegramClient, events, errors, Button
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsAdmins
from telethon.tl.functions.messages import ImportChatInviteRequest

# ------------------------------------------------------------------
#  CONFIGURATION
# ------------------------------------------------------------------
class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "6015356597"))
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true")
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "8111794244:AAGurFdkxV_KrahEYJemMo-hoQkN1mJJKlU")
    
    LEARNING_GROUP = int(os.getenv("LEARNING_GROUP", "-1003806830045"))
    TARGET_GROUP = -1003580630981
    
    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yangon"))
    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    BULLY_DELAY = 0.8
    SHOOT_DELAY = 0.4
    SPAM_DELAY = 0.8
    TALK_DELAY = 0.5
    MAX_RETRIES = 3

    SOURCE_GROUP_ID = int(os.getenv("SOURCE_GROUP_ID", "-1003877873337"))
    TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "-1003754813090"))
    CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/freevipallinone")

    CATCHER_CHAT = -1004437409107
    CATCHER_BOT_ID = 6157455819

# Hardcoded Spam Text
SPAM_TEXT = """Spam spam spam! 🚀 I am the Spam God, the Lord of Spam, the King of Keys! 
I spam like a turtle – slow but unstoppable! 🐢 
Spam spam spam, I spam all day, I spam all night! 
You can't stop me, I'm too fast, too furious, too spammy! 
Get ready for the spam tsunami! 🌊 
I am the master of spam, the legend of spam, the one and only Spam God! 
Spam spam spam, I love it! 😈 
If you see a turtle coming, you know it's me – the Spam Turtle King! 
Spam spam spam, spam spam spam, spam spam spam! 
Let's go! 🔥"""
# ------------------------------------------------------------------
#  LOGGING
# ------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("SovereignMerged")

# ------------------------------------------------------------------
#  FLASK KEEP‑ALIVE
# ------------------------------------------------------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def health_check() -> str:
    return "Sovereign Merged System is operational."

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
    def powerranger_col(self): return self.db["powerranger_col"]
    @property
    def powerranger_col2(self): return self.db["powerranger_col2"]
    @property
    def powerranger_col3(self): return self.db["powerranger_col3"]
    @property
    def target_bots_col(self): return self.db["target_bots_col"]
    @property
    def tomboy_col(self): return self.db["tomboy_col"]
    @property
    def taunt_targets(self): return self.db["taunt_targets"]
    @property
    def muted_registry(self): return self.db["muted_registry"]
    @property
    def channel_subscribers(self): return self.db["channel_subscribers"]
    @property
    def bot_watchlist(self): return self.db["bot_watchlist"]
    @property
    def talk_phrases(self): return self.db["talk_phrases"]

# ------------------------------------------------------------------
#  MAIN BOT CLASS
# ------------------------------------------------------------------
class SovereignBot:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.bot_client = TelegramClient("bot_main_session", Config.API_ID, Config.API_HASH, flood_sleep_threshold=60)
        self.bot_id: Optional[int] = None

        # ---------- POOL 1 ----------
        self.action_clients: List[TelegramClient] = []
        self.action_names: List[str] = []
        self.action_ids: Set[int] = set()
        self.bully_tasks: Dict[int, bool] = {}
        self.shoot_tasks: Dict[int, bool] = {}
        self.tracking_targets: Dict[int, int] = {}
        self.dark_passenger_targets: Dict[int, int] = {}
        self.spam_tasks: Dict[int, bool] = {}

        # ---------- POOL 2 ----------
        self.action_clients2: List[TelegramClient] = []
        self.action_names2: List[str] = []
        self.action_ids2: Set[int] = set()
        self.bully_tasks2: Dict[int, bool] = {}
        self.shoot_tasks2: Dict[int, bool] = {}
        self.tracking_targets2: Dict[int, int] = {}
        self.dark_passenger_targets2: Dict[int, int] = {}
        self.spam_tasks2: Dict[int, bool] = {}

        # ---------- POOL 3 ----------
        self.action_clients3: List[TelegramClient] = []
        self.action_names3: List[str] = []
        self.action_ids3: Set[int] = set()
        self.bully_tasks3: Dict[int, bool] = {}
        self.shoot_tasks3: Dict[int, bool] = {}
        self.tracking_targets3: Dict[int, int] = {}
        self.dark_passenger_targets3: Dict[int, int] = {}
        self.spam_tasks3: Dict[int, bool] = {}

        # Shared taunt targets
        self.delete_and_taunt_targets: Dict[int, Set[int]] = {}
        self.pool_lock = asyncio.Lock()
        self.learning_status = False
        self.save_status = False

        self.phrase_lists: Dict[int, List[str]] = {}
        self.phrase_indices: Dict[int, int] = {}

        self.is_copy_active = False
        self.matrix_group_id: Optional[int] = None
        self.target_group_id: Optional[int] = None
        self.bad_users: List[tuple] = []
        self.check_in_progress = False

        self.sticker_spam_data = {}
        self.char_spam_data = {}
        self.admin_warned_sticker = set()
        self.admin_warned_char = set()
        self.admin_cache = {}

        self.bot_watchlist_cache: Dict[int, Set[int]] = {}

        # Random Talk
        self.talk_tasks: Dict[int, bool] = {}
        self.talk_phrases_cache: Dict[int, List[str]] = {}
        self.talk_indices: Dict[int, int] = {}
        self.talk_source_group: Dict[int, int] = {}

        # Catcher bot
        self.catcher_processing: Set[int] = set()

        # AUTO CLEANUP (In-Memory Cache ONLY)
        self.auto_cleanup = False
        self.msg_queues: Dict[int, List[int]] = {}
        self.queue_locks: Dict[int, asyncio.Lock] = {}

        self._register_handlers()

    # --------------------------------------------------------------
    #  USERBOT POOL LOADING
    # --------------------------------------------------------------
    async def load_userbots(self) -> None:
        await self._load_pool(self.db.powerranger_col, self.action_clients, self.action_names, self.action_ids, "Pool 1")
    async def load_userbots2(self) -> None:
        await self._load_pool(self.db.powerranger_col2, self.action_clients2, self.action_names2, self.action_ids2, "Pool 2")
    async def load_userbots3(self) -> None:
        await self._load_pool(self.db.powerranger_col3, self.action_clients3, self.action_names3, self.action_ids3, "Pool 3")

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
                    name = pr_doc.get("name", f"PR-{len(clients_list)}")
                    names_list.append(name); ids_set.add(me.id)
                    logger.info(f"✅ {pool_name} – '{name}' loaded: @{me.username}")
                else:
                    await client.disconnect()
            except Exception as e:
                logger.error(f"❌ {pool_name} – failed: {e}")
        logger.info(f"🚀 {pool_name} ready: {len(clients_list)} clients.")

    async def close_action_clients(self) -> None:
        all_clients = self.action_clients + self.action_clients2 + self.action_clients3
        for client in all_clients:
            try:
                if client.is_connected():
                    await client.disconnect()
            except: pass
        self.action_clients.clear(); self.action_names.clear(); self.action_ids.clear()
        self.action_clients2.clear(); self.action_names2.clear(); self.action_ids2.clear()
        self.action_clients3.clear(); self.action_names3.clear(); self.action_ids3.clear()

    async def _get_action_client_from_pool(self, pool_clients) -> Optional[TelegramClient]:
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

    async def get_action_client(self) -> Optional[TelegramClient]:
        return await self._get_action_client_from_pool(self.action_clients)
    async def get_action_client2(self) -> Optional[TelegramClient]:
        return await self._get_action_client_from_pool(self.action_clients2)
    async def get_action_client3(self) -> Optional[TelegramClient]:
        return await self._get_action_client_from_pool(self.action_clients3)

    # --------------------------------------------------------------
    #  BOT WATCHLIST & TAUNTS
    # --------------------------------------------------------------
    async def load_bot_watchlist(self) -> None:
        doc = await self.db.bot_watchlist.find_one({"chat_id": Config.TARGET_GROUP})
        if doc:
            self.bot_watchlist_cache[Config.TARGET_GROUP] = set(doc.get("bot_ids", []))
        else:
            self.bot_watchlist_cache[Config.TARGET_GROUP] = set()

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

    async def check_ban_rights(self, chat_id: int, user_id: int) -> bool:
        if user_id == Config.OWNER_ID:
            return True
        try:
            permissions = await self.bot_client.get_permissions(chat_id, user_id)
            return permissions.is_admin and permissions.ban_users
        except:
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

    async def get_target_user(self, event, arg: Optional[str] = None):
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            return await event.client.get_entity(reply_msg.sender_id)
        if arg:
            try:
                return await event.client.get_entity(arg)
            except:
                await event.reply("⚠️ User not found.")
                return None
        await event.reply("⚠️ Reply to a user or provide username/ID.")
        return None

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
    #  PHRASE & TALK
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

    async def fetch_talk_phrases(self, source_group_id: int) -> List[str]:
        docs = await self.db.talk_phrases.find({"group_id": source_group_id}).to_list(length=10000)
        if docs:
            return [doc.get("text") for doc in docs if doc.get("text")]
        return []

    async def get_next_talk_phrase(self, source_group_id: int) -> str:
        if source_group_id not in self.talk_phrases_cache:
            phrases = await self.fetch_talk_phrases(source_group_id)
            if not phrases:
                return "စကားလုံးမရှိသေးပါ"
            random.shuffle(phrases)
            self.talk_phrases_cache[source_group_id] = phrases
            self.talk_indices[source_group_id] = 0
        phrases = self.talk_phrases_cache[source_group_id]
        idx = self.talk_indices.get(source_group_id, 0)
        phrase = phrases[idx]
        idx += 1
        if idx >= len(phrases):
            random.shuffle(phrases)
            idx = 0
        self.talk_indices[source_group_id] = idx
        return phrase

    async def start_talk_loop(self, chat_id: int, source_group_id: int):
        if chat_id in self.talk_tasks and self.talk_tasks[chat_id]:
            return
        self.talk_tasks[chat_id] = True
        self.talk_source_group[chat_id] = source_group_id
        if source_group_id not in self.talk_phrases_cache:
            await self.fetch_talk_phrases(source_group_id)
        async def talk_loop():
            while self.talk_tasks.get(chat_id, False):
                client = await self.get_action_client()
                if not client:
                    await asyncio.sleep(1)
                    continue
                phrase = await self.get_next_talk_phrase(source_group_id)
                try:
                    sent = await client.send_message(chat_id, phrase)
                    await self._handle_message_sent(chat_id, sent.id)
                    await asyncio.sleep(Config.TALK_DELAY)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                except Exception as e:
                    logger.error(f"Talk loop error: {e}")
                    await asyncio.sleep(2)
        asyncio.create_task(talk_loop())

    # --------------------------------------------------------------
    #  AUTO CLEANUP (In-Memory Cache ONLY)
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
    #  SPAM LOOPS (HARDCODED TEXT)
    # --------------------------------------------------------------
    async def _start_spam_loop(self, chat_id: int, pool: int):
        task_dicts = [self.spam_tasks, self.spam_tasks2, self.spam_tasks3]
        if task_dicts[pool-1].get(chat_id, False):
            return
        task_dicts[pool-1][chat_id] = True

        client_getters = [self.get_action_client, self.get_action_client2, self.get_action_client3]
        get_client = client_getters[pool-1]

        async def spam_loop():
            while task_dicts[pool-1].get(chat_id, False):
                client = await get_client()
                if not client:
                    await asyncio.sleep(1)
                    continue
                try:
                    sent = await client.send_message(chat_id, SPAM_TEXT)
                    await self._handle_message_sent(chat_id, sent.id)
                    await asyncio.sleep(Config.SPAM_DELAY)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                except Exception as e:
                    logger.error(f"Spam loop (Pool {pool}) error: {e}")
                    await asyncio.sleep(2)
            logger.info(f"🛑 Spam loop stopped for chat {chat_id} (Pool {pool})")
        asyncio.create_task(spam_loop())

    # --------------------------------------------------------------
    #  SPAM FILTERS (FULL)
    # --------------------------------------------------------------
    async def sticker_spam_filter(self, event):
        if not event.sticker or event.is_private:
            return
        all_ids = self.action_ids | self.action_ids2 | self.action_ids3
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
        all_ids = self.action_ids | self.action_ids2 | self.action_ids3
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
        all_ids = self.action_ids | self.action_ids2 | self.action_ids3
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
        all_ids = self.action_ids | self.action_ids2 | self.action_ids3
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
    #  MODERATION COMMANDS (FULL)
    # --------------------------------------------------------------
    async def mute_user(self, event):
        if not await self.check_admin(event.chat_id, event.sender_id):
            return
        target_id = None
        args_text = event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') else None
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            target_id = reply_msg.sender_id
        else:
            if args_text:
                target_str = args_text.strip().split()[0]
                if target_str.isdigit():
                    target_id = int(target_str)
                else:
                    try:
                        user_entity = await event.client.get_entity(target_str)
                        target_id = user_entity.id
                    except Exception:
                        await event.reply("⚠️ User not found.")
                        return
            else:
                await event.reply("⚠️ Usage: <code>/mute</code> (reply) or <code>/mute [@username]</code>")
                return
        if not target_id:
            return
        bot_me = await event.client.get_me()
        if target_id == bot_me.id or target_id == Config.OWNER_ID:
            await event.reply("❌ Cannot mute the bot or the owner.")
            return
        try:
            await event.client.edit_permissions(
                event.chat_id, target_id,
                send_messages=False, send_media=False, send_stickers=False, send_gifs=False
            )
            user_entity = await event.client.get_entity(target_id)
            target_name = f"{user_entity.first_name} {user_entity.last_name or ''}".strip()
            mention = self.format_mention(target_id, target_name)
            await event.reply(f"<b>MUTE OPERATION SUCCESS!</b>\n<b>{mention}</b> has been silenced <b>Permanently</b>.", parse_mode='html')
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")

    async def unmute_user(self, event):
        if not await self.check_ban_rights(event.chat_id, event.sender_id):
            return
        target_user = await self.get_target_user(event, event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') else None)
        if not target_user:
            return
        try:
            await self.bot_client.edit_permissions(event.chat_id, target_user.id, send_messages=True)
            await self.db.muted_registry.delete_one({"chat_id": event.chat_id, "user_id": target_user.id})
            target_name = f"{getattr(target_user, 'first_name', 'User')} {getattr(target_user, 'last_name', '') or ''}".strip()
            mention = self.format_mention(target_user.id, target_name)
            await event.reply(f"🌌 <b>UNMUTE OPERATION</b>\n🔊 <b>Target:</b> {mention}\n⚡ <b>Status:</b> <code>Voice Restored</code>", parse_mode='html')
        except Exception as e:
            logger.error(f"Unmute Error: {e}")

    async def ban_user(self, event):
        if not await self.check_ban_rights(event.chat_id, event.sender_id):
            return
        target_user = await self.get_target_user(event, event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') else None)
        if not target_user:
            return
        try:
            await self.bot_client.edit_permissions(event.chat_id, target_user.id, view_messages=False)
            target_name = f"{getattr(target_user, 'first_name', 'User')} {getattr(target_user, 'last_name', '') or ''}".strip()
            mention = self.format_mention(target_user.id, target_name)
            await event.reply(f"🌌 <b>BAN OPERATION</b>\n🚫 <b>Target:</b> {mention}\n⚡ <b>Status:</b> <code>Exiled / Perm-Banned</code>", parse_mode='html')
        except Exception as e:
            logger.error(f"Ban Error: {e}")

    async def unban_user(self, event):
        if not await self.check_ban_rights(event.chat_id, event.sender_id):
            return
        target_user = await self.get_target_user(event, event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') else None)
        if not target_user:
            return
        try:
            await self.bot_client.edit_permissions(event.chat_id, target_user.id, view_messages=True)
            target_name = f"{getattr(target_user, 'first_name', 'User')} {getattr(target_user, 'last_name', '') or ''}".strip()
            mention = self.format_mention(target_user.id, target_name)
            await event.reply(f"🌌 <b>UNBAN OPERATION</b>\n✅ <b>Target:</b> {mention}\n⚡ <b>Status:</b> <code>Ban Lifted</code>", parse_mode='html')
        except Exception as e:
            logger.error(f"Unban Error: {e}")

    async def kick_user(self, event):
        if not await self.check_ban_rights(event.chat_id, event.sender_id):
            return
        target_user = await self.get_target_user(event, event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') else None)
        if not target_user:
            return
        try:
            await self.bot_client.edit_permissions(event.chat_id, target_user.id, view_messages=False)
            await self.bot_client.edit_permissions(event.chat_id, target_user.id, view_messages=True)
            target_name = f"{getattr(target_user, 'first_name', 'User')} {getattr(target_user, 'last_name', '') or ''}".strip()
            mention = self.format_mention(target_user.id, target_name)
            await event.reply(f"🌌 <b>KICK OPERATION</b>\n💨 <b>Target:</b> {mention}\n⚡ <b>Status:</b> <code>Removed / Kicked</code>", parse_mode='html')
        except Exception as e:
            logger.error(f"Kick Error: {e}")

    # --------------------------------------------------------------
    #  CHANNEL ADMIN
    # --------------------------------------------------------------
    async def forward_media_to_channel(self, event):
        if event.sender_id != Config.OWNER_ID:
            return
        if event.chat_id != Config.SOURCE_GROUP_ID:
            return
        if not (event.photo or event.video):
            return
        caption = event.raw_text or ""
        bot_username = (await self.bot_client.get_me()).username or "YourBotUsername"
        buttons = [[Button.url("အသစ်တင်တိုင်းသိနိုင်ရန်နှိပ်ပါ", f"https://t.me/{bot_username}?start=channel_alert")]]
        try:
            await self.bot_client.send_message(Config.TARGET_CHANNEL_ID, caption, file=event.media, parse_mode='html', buttons=buttons)
        except Exception as e:
            logger.error(f"Forward error: {e}")

    async def start_handler(self, event):
        payload = event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') and event.pattern_match.group(1) else ""
        user_id = event.sender_id
        if payload == "channel_alert":
            await self.db.channel_subscribers.update_one({"user_id": user_id}, {"$set": {"user_id": user_id, "subscribed_at": time.time()}}, upsert=True)
            await event.reply("✅ သင်သည် Channel မှာ အသစ်တင်တိုင်း အသိပေးချက် ရရှိမည် ဖြစ်ပါသည်။\n📢 နောက်အသစ်များကို စောင့်မျှော်နေပါ။", parse_mode='html')
        else:
            await event.reply("👋 မင်္ဂလာပါ။\nChannel အသစ်များအတွက် အသိပေးချက် ရယူလိုပါက အောက်ပါ Link ကိုနှိပ်ပါ။\nhttps://t.me/YourBot?start=channel_alert", parse_mode='html')

    async def notify_all_subscribers(self, event):
        if event.sender_id != Config.OWNER_ID:
            return
        message = event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') and event.pattern_match.group(1) else None
        if not message:
            return await event.reply("⚠️ Usage: <code>/notifyall [message]</code>", parse_mode='html')
        subscribers = await self.db.channel_subscribers.find({}).to_list(length=None)
        if not subscribers:
            return await event.reply("❌ No subscribers yet.", parse_mode='html')
        buttons = [[Button.url("📢 ချန်နယ်သို့သွားရန်", Config.CHANNEL_LINK)]]
        success = 0
        for doc in subscribers:
            user_id = doc["user_id"]
            try:
                await self.bot_client.send_message(user_id, f"📢 <b>Channel Update</b>\n\n{message}", parse_mode='html', buttons=buttons)
                success += 1
                await asyncio.sleep(0.1)
            except Exception:
                pass
        await event.reply(f"✅ Notification sent to {success} subscribers.", parse_mode='html')

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
            await event.reply(f"🔄 Auto‑Cleanup is now **{status}**.\n• Deletion queue uses in-memory cache (No DB writes).\n• Every 100 messages sent by any Power Ranger will be bulk-deleted.", parse_mode='markdown')

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

        # ======== ATTACK COMMANDS – POOL 1 ========
        @self.bot_client.on(events.NewMessage(pattern=r"^(/bully|အနိုင်ကျင့်)$"))
        async def bot_bully(event):
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
            self.reset_phrase_cycle(chat_id); self.bully_tasks[chat_id] = True
            async def bully_loop():
                while self.bully_tasks.get(chat_id, False):
                    client = await self.get_action_client()
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
                self.shoot_tasks[chat_id] = True; self.reset_phrase_cycle(chat_id)
                async def shoot_loop():
                    while self.shoot_tasks.get(chat_id, False):
                        client = await self.get_action_client()
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
            self.tracking_targets[chat_id] = target.id
            mention = self.format_mention(target.id, target.first_name or "Target")
            self.reset_phrase_cycle(chat_id)
            sent = await event.reply(f"🔭 Tracking {mention}...", parse_mode='html')
            await self._handle_message_sent(chat_id, sent.id)

        # ======== ATTACK COMMANDS – POOL 2 ========
        @self.bot_client.on(events.NewMessage(pattern=r"^(/bully2|အနိုင်ကျင့်2)$"))
        async def bot_bully2(event):
            if not await self.is_allowed(event.sender_id): return
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"🔫 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used /bully2", parse_mode='html')
            try: await event.delete()
            except: pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply: return
            target = await reply.get_sender()
            if target.id == Config.OWNER_ID: return
            chat_id = event.chat_id; target_id = target.id; mention = self.format_mention(target_id, target.first_name or "Target")
            self.reset_phrase_cycle(chat_id); self.bully_tasks2[chat_id] = True
            async def bully_loop2():
                while self.bully_tasks2.get(chat_id, False):
                    client = await self.get_action_client2()
                    if not client: await asyncio.sleep(1); continue
                    phrase = await self.get_next_phrase(chat_id)
                    try:
                        sent = await client.send_message(chat_id, f"{mention} {phrase}", reply_to=reply.id, parse_mode='html')
                        await self._handle_message_sent(chat_id, sent.id)
                        await asyncio.sleep(Config.BULLY_DELAY)
                    except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
                    except Exception as e: logger.error(f"Bully2 error: {e}"); await asyncio.sleep(1)
            asyncio.create_task(bully_loop2())

        @self.bot_client.on(events.NewMessage(pattern=r"^(/mark2|မှတ်2|/shoot2|ပစ်2)$"))
        async def attack_cmds2(event):
            if not await self.is_allowed(event.sender_id): return
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"🔫 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used {event.text}", parse_mode='html')
            try: await event.delete()
            except: pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply or reply.sender_id == Config.OWNER_ID: return
            chat_id = event.chat_id; target = await reply.get_sender(); target_id = target.id; mention = self.format_mention(target_id, target.first_name or "Target")
            if event.text in ("/shoot2", "ပစ်2"):
                self.shoot_tasks2[chat_id] = True; self.reset_phrase_cycle(chat_id)
                async def shoot_loop2():
                    while self.shoot_tasks2.get(chat_id, False):
                        client = await self.get_action_client2()
                        if not client: await asyncio.sleep(1); continue
                        phrase = await self.get_next_phrase(chat_id)
                        try:
                            sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                            await self._handle_message_sent(chat_id, sent.id)
                            await asyncio.sleep(Config.SHOOT_DELAY)
                        except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
                        except Exception as e: logger.error(f"Shoot2 error: {e}"); await asyncio.sleep(1)
                asyncio.create_task(shoot_loop2())
            else:
                sender = await event.get_sender()
                sender_mention = self.format_mention(event.sender_id, sender.first_name or "Unknown")
                client = await self.get_action_client2()
                if client:
                    sent = await client.send_message(chat_id, f"🎯 {sender_mention} marked {mention} (pool2).", parse_mode='html')
                    await self._handle_message_sent(chat_id, sent.id)

        @self.bot_client.on(events.NewMessage(pattern=r"^(/track2|ခြေရာ2)$"))
        async def track2(event):
            if not await self.is_allowed(event.sender_id): return
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"🎯 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used /track2", parse_mode='html')
            try: await event.delete()
            except: pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply or reply.sender_id == Config.OWNER_ID: return
            target = await reply.get_sender(); chat_id = event.chat_id
            self.tracking_targets2[chat_id] = target.id
            mention = self.format_mention(target.id, target.first_name or "Target")
            self.reset_phrase_cycle(chat_id)
            client = await self.get_action_client2()
            if client:
                sent = await client.send_message(chat_id, f"🔭 Tracking {mention} (pool2)...", parse_mode='html')
                await self._handle_message_sent(chat_id, sent.id)

        # ======== ATTACK COMMANDS – POOL 3 ========
        @self.bot_client.on(events.NewMessage(pattern=r"^(/bully3|အနိုင်ကျင့်3)$"))
        async def bot_bully3(event):
            if not await self.is_allowed(event.sender_id): return
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"🔫 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used /bully3", parse_mode='html')
            try: await event.delete()
            except: pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply: return
            target = await reply.get_sender()
            if target.id == Config.OWNER_ID: return
            chat_id = event.chat_id; target_id = target.id; mention = self.format_mention(target_id, target.first_name or "Target")
            self.reset_phrase_cycle(chat_id); self.bully_tasks3[chat_id] = True
            async def bully_loop3():
                while self.bully_tasks3.get(chat_id, False):
                    client = await self.get_action_client3()
                    if not client: await asyncio.sleep(1); continue
                    phrase = await self.get_next_phrase(chat_id)
                    try:
                        sent = await client.send_message(chat_id, f"{mention} {phrase}", reply_to=reply.id, parse_mode='html')
                        await self._handle_message_sent(chat_id, sent.id)
                        await asyncio.sleep(Config.BULLY_DELAY)
                    except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
                    except Exception as e: logger.error(f"Bully3 error: {e}"); await asyncio.sleep(1)
            asyncio.create_task(bully_loop3())

        @self.bot_client.on(events.NewMessage(pattern=r"^(/mark3|မှတ်3|/shoot3|ပစ်3)$"))
        async def attack_cmds3(event):
            if not await self.is_allowed(event.sender_id): return
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"🔫 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used {event.text}", parse_mode='html')
            try: await event.delete()
            except: pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply or reply.sender_id == Config.OWNER_ID: return
            chat_id = event.chat_id; target = await reply.get_sender(); target_id = target.id; mention = self.format_mention(target_id, target.first_name or "Target")
            if event.text in ("/shoot3", "ပစ်3"):
                self.shoot_tasks3[chat_id] = True; self.reset_phrase_cycle(chat_id)
                async def shoot_loop3():
                    while self.shoot_tasks3.get(chat_id, False):
                        client = await self.get_action_client3()
                        if not client: await asyncio.sleep(1); continue
                        phrase = await self.get_next_phrase(chat_id)
                        try:
                            sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                            await self._handle_message_sent(chat_id, sent.id)
                            await asyncio.sleep(Config.SHOOT_DELAY)
                        except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
                        except Exception as e: logger.error(f"Shoot3 error: {e}"); await asyncio.sleep(1)
                asyncio.create_task(shoot_loop3())
            else:
                sender = await event.get_sender()
                sender_mention = self.format_mention(event.sender_id, sender.first_name or "Unknown")
                client = await self.get_action_client3()
                if client:
                    sent = await client.send_message(chat_id, f"🎯 {sender_mention} marked {mention} (pool3).", parse_mode='html')
                    await self._handle_message_sent(chat_id, sent.id)

        @self.bot_client.on(events.NewMessage(pattern=r"^(/track3|ခြေရာ3)$"))
        async def track3(event):
            if not await self.is_allowed(event.sender_id): return
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"🎯 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used /track3", parse_mode='html')
            try: await event.delete()
            except: pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply or reply.sender_id == Config.OWNER_ID: return
            target = await reply.get_sender(); chat_id = event.chat_id
            self.tracking_targets3[chat_id] = target.id
            mention = self.format_mention(target.id, target.first_name or "Target")
            self.reset_phrase_cycle(chat_id)
            client = await self.get_action_client3()
            if client:
                sent = await client.send_message(chat_id, f"🔭 Tracking {mention} (pool3)...", parse_mode='html')
                await self._handle_message_sent(chat_id, sent.id)

        # ======== SPAM COMMANDS ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/spam$"))
        async def spam_cmd(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id
            await self._start_spam_loop(chat_id, 1)
            await event.reply(f"🗣️ Spam (Pool 1) started. (Text: {SPAM_TEXT[:30]}...)")
        @self.bot_client.on(events.NewMessage(pattern=r"^/spam2$"))
        async def spam_cmd2(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id
            await self._start_spam_loop(chat_id, 2)
            await event.reply(f"🗣️ Spam (Pool 2) started. (Text: {SPAM_TEXT[:30]}...)")
        @self.bot_client.on(events.NewMessage(pattern=r"^/spam3$"))
        async def spam_cmd3(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id
            await self._start_spam_loop(chat_id, 3)
            await event.reply(f"🗣️ Spam (Pool 3) started. (Text: {SPAM_TEXT[:30]}...)")

        # ======== "ဖာသည်မသား" (Shared) ========
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
            client = await self.get_action_client()
            if client:
                phrase = await self.get_next_phrase(chat_id)
                try:
                    sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                    await self._handle_message_sent(chat_id, sent.id)
                except: pass

        # ======== REMOVE / CLEAR TAUNTS ========
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

        # ======== STOP COMMAND (UPDATED) ========
        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop)$"))
        async def stop_attack(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id
            stopped = False
            # Pool 1
            if chat_id in self.bully_tasks: self.bully_tasks[chat_id] = False; stopped = True
            if chat_id in self.shoot_tasks: self.shoot_tasks[chat_id] = False; stopped = True
            if chat_id in self.tracking_targets: del self.tracking_targets[chat_id]; stopped = True
            if chat_id in self.dark_passenger_targets: del self.dark_passenger_targets[chat_id]; stopped = True
            if chat_id in self.spam_tasks: self.spam_tasks[chat_id] = False; stopped = True
            # Pool 2
            if chat_id in self.bully_tasks2: self.bully_tasks2[chat_id] = False; stopped = True
            if chat_id in self.shoot_tasks2: self.shoot_tasks2[chat_id] = False; stopped = True
            if chat_id in self.tracking_targets2: del self.tracking_targets2[chat_id]; stopped = True
            if chat_id in self.dark_passenger_targets2: del self.dark_passenger_targets2[chat_id]; stopped = True
            if chat_id in self.spam_tasks2: self.spam_tasks2[chat_id] = False; stopped = True
            # Pool 3
            if chat_id in self.bully_tasks3: self.bully_tasks3[chat_id] = False; stopped = True
            if chat_id in self.shoot_tasks3: self.shoot_tasks3[chat_id] = False; stopped = True
            if chat_id in self.tracking_targets3: del self.tracking_targets3[chat_id]; stopped = True
            if chat_id in self.dark_passenger_targets3: del self.dark_passenger_targets3[chat_id]; stopped = True
            if chat_id in self.spam_tasks3: self.spam_tasks3[chat_id] = False; stopped = True
            # Talk
            if chat_id in self.talk_tasks: self.talk_tasks[chat_id] = False; stopped = True
            self.reset_phrase_cycle(chat_id)
            if stopped:
                await event.reply("🛑 All active attacks (bully/shoot/track/spam/talk) stopped in this chat for all pools.")
            else:
                await event.reply("ℹ️ No active attacks to stop.")

        # ======== POWER RANGER MANAGEMENT – POOL 1 ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/addpr(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_pr(event):
            if event.sender_id != Config.OWNER_ID: return
            cmd_args = event.pattern_match.group(1); session_str = event.pattern_match.group(2)
            name = cmd_args if cmd_args and not session_str else "PowerRanger"
            if not session_str:
                reply = await event.get_reply_message()
                if reply and reply.text:
                    session_str = reply.text.strip()
                    if cmd_args and not cmd_args.startswith("session"):
                        name = cmd_args
                else:
                    await event.reply("❓ Usage: `/addpr <name> <session_string>`")
                    return
            if not session_str or len(session_str) < 10:
                await event.reply("❌ Invalid session string.")
                return
            async for doc in self.db.powerranger_col.find():
                if doc.get("session") == session_str:
                    await event.reply("⚠️ This session already exists.")
                    return
            await self.db.powerranger_col.insert_one({"name": name, "session": session_str})
            client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            try:
                await client.start(); me = await client.get_me()
                self.action_clients.append(client); self.action_names.append(name); self.action_ids.add(me.id)
                await event.reply(f"✅ '{name}' (ID: {me.id}) added to Pool 1! Total: {len(self.action_clients)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {str(e)}")
                await self.db.powerranger_col.delete_one({"session": session_str})

        @self.bot_client.on(events.NewMessage(pattern=r"^/listpr$"))
        async def list_pr(event):
            if event.sender_id != Config.OWNER_ID: return
            if not self.action_clients:
                await event.reply("📭 No Power Rangers active in Pool 1.")
                return
            lines = [f"👥 **Pool 1 ({len(self.action_clients)})**"]
            for i, (client, name) in enumerate(zip(self.action_clients, self.action_names)):
                try:
                    me = await client.get_me()
                    lines.append(f"  {i+1}. **{name}** – @{me.username} (ID: {me.id})")
                except:
                    lines.append(f"  {i+1}. **{name}** – (offline)")
            await event.reply("\n".join(lines), parse_mode='markdown')

        @self.bot_client.on(events.NewMessage(pattern=r"^/removepr\s+(.+)$"))
        async def remove_pr(event):
            if event.sender_id != Config.OWNER_ID: return
            target = event.pattern_match.group(1).strip()
            pr_list = await self.db.powerranger_col.find().to_list(length=None)
            idx = None
            if target.isdigit(): idx = int(target) - 1
            else:
                for i, doc in enumerate(pr_list):
                    if doc.get("name") == target:
                        idx = i; break
            if idx is None or idx < 0 or idx >= len(pr_list):
                await event.reply(f"❌ Cannot find '{target}'.")
                return
            removed_doc = pr_list[idx]
            await self.db.powerranger_col.delete_one({"_id": removed_doc["_id"]})
            if idx < len(self.action_clients):
                client = self.action_clients.pop(idx); self.action_names.pop(idx)
                try: await client.disconnect()
                except: pass
                await event.reply(f"✅ Removed '{removed_doc.get('name')}' from Pool 1.")
            else:
                await event.reply(f"✅ Removed from DB.")

        # ======== POWER RANGER MANAGEMENT – POOL 2 ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/addpr2(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_pr2(event):
            if event.sender_id != Config.OWNER_ID: return
            cmd_args = event.pattern_match.group(1); session_str = event.pattern_match.group(2)
            name = cmd_args if cmd_args and not session_str else "PowerRanger2"
            if not session_str:
                reply = await event.get_reply_message()
                if reply and reply.text:
                    session_str = reply.text.strip()
                    if cmd_args and not cmd_args.startswith("session"):
                        name = cmd_args
                else:
                    await event.reply("❓ Usage: `/addpr2 <name> <session_string>`")
                    return
            if not session_str or len(session_str) < 10:
                await event.reply("❌ Invalid session string.")
                return
            async for doc in self.db.powerranger_col2.find():
                if doc.get("session") == session_str:
                    await event.reply("⚠️ This session already exists in Pool 2.")
                    return
            await self.db.powerranger_col2.insert_one({"name": name, "session": session_str})
            client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            try:
                await client.start(); me = await client.get_me()
                self.action_clients2.append(client); self.action_names2.append(name); self.action_ids2.add(me.id)
                await event.reply(f"✅ '{name}' (ID: {me.id}) added to Pool 2! Total: {len(self.action_clients2)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {str(e)}")
                await self.db.powerranger_col2.delete_one({"session": session_str})

        @self.bot_client.on(events.NewMessage(pattern=r"^/listpr2$"))
        async def list_pr2(event):
            if event.sender_id != Config.OWNER_ID: return
            if not self.action_clients2:
                await event.reply("📭 No Power Rangers active in Pool 2.")
                return
            lines = [f"👥 **Pool 2 ({len(self.action_clients2)})**"]
            for i, (client, name) in enumerate(zip(self.action_clients2, self.action_names2)):
                try:
                    me = await client.get_me()
                    lines.append(f"  {i+1}. **{name}** – @{me.username} (ID: {me.id})")
                except:
                    lines.append(f"  {i+1}. **{name}** – (offline)")
            await event.reply("\n".join(lines), parse_mode='markdown')

        @self.bot_client.on(events.NewMessage(pattern=r"^/removepr2\s+(.+)$"))
        async def remove_pr2(event):
            if event.sender_id != Config.OWNER_ID: return
            target = event.pattern_match.group(1).strip()
            pr_list = await self.db.powerranger_col2.find().to_list(length=None)
            idx = None
            if target.isdigit(): idx = int(target) - 1
            else:
                for i, doc in enumerate(pr_list):
                    if doc.get("name") == target:
                        idx = i; break
            if idx is None or idx < 0 or idx >= len(pr_list):
                await event.reply(f"❌ Cannot find '{target}' in Pool 2.")
                return
            removed_doc = pr_list[idx]
            await self.db.powerranger_col2.delete_one({"_id": removed_doc["_id"]})
            if idx < len(self.action_clients2):
                client = self.action_clients2.pop(idx); self.action_names2.pop(idx)
                try: await client.disconnect()
                except: pass
                await event.reply(f"✅ Removed '{removed_doc.get('name')}' from Pool 2.")
            else:
                await event.reply(f"✅ Removed from DB.")

        # ======== POWER RANGER MANAGEMENT – POOL 3 ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/addpr3(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_pr3(event):
            if event.sender_id != Config.OWNER_ID: return
            cmd_args = event.pattern_match.group(1); session_str = event.pattern_match.group(2)
            name = cmd_args if cmd_args and not session_str else "PowerRanger3"
            if not session_str:
                reply = await event.get_reply_message()
                if reply and reply.text:
                    session_str = reply.text.strip()
                    if cmd_args and not cmd_args.startswith("session"):
                        name = cmd_args
                else:
                    await event.reply("❓ Usage: `/addpr3 <name> <session_string>`")
                    return
            if not session_str or len(session_str) < 10:
                await event.reply("❌ Invalid session string.")
                return
            async for doc in self.db.powerranger_col3.find():
                if doc.get("session") == session_str:
                    await event.reply("⚠️ This session already exists in Pool 3.")
                    return
            await self.db.powerranger_col3.insert_one({"name": name, "session": session_str})
            client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            try:
                await client.start(); me = await client.get_me()
                self.action_clients3.append(client); self.action_names3.append(name); self.action_ids3.add(me.id)
                await event.reply(f"✅ '{name}' (ID: {me.id}) added to Pool 3! Total: {len(self.action_clients3)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {str(e)}")
                await self.db.powerranger_col3.delete_one({"session": session_str})

        @self.bot_client.on(events.NewMessage(pattern=r"^/listpr3$"))
        async def list_pr3(event):
            if event.sender_id != Config.OWNER_ID: return
            if not self.action_clients3:
                await event.reply("📭 No Power Rangers active in Pool 3.")
                return
            lines = [f"👥 **Pool 3 ({len(self.action_clients3)})**"]
            for i, (client, name) in enumerate(zip(self.action_clients3, self.action_names3)):
                try:
                    me = await client.get_me()
                    lines.append(f"  {i+1}. **{name}** – @{me.username} (ID: {me.id})")
                except:
                    lines.append(f"  {i+1}. **{name}** – (offline)")
            await event.reply("\n".join(lines), parse_mode='markdown')

        @self.bot_client.on(events.NewMessage(pattern=r"^/removepr3\s+(.+)$"))
        async def remove_pr3(event):
            if event.sender_id != Config.OWNER_ID: return
            target = event.pattern_match.group(1).strip()
            pr_list = await self.db.powerranger_col3.find().to_list(length=None)
            idx = None
            if target.isdigit(): idx = int(target) - 1
            else:
                for i, doc in enumerate(pr_list):
                    if doc.get("name") == target:
                        idx = i; break
            if idx is None or idx < 0 or idx >= len(pr_list):
                await event.reply(f"❌ Cannot find '{target}' in Pool 3.")
                return
            removed_doc = pr_list[idx]
            await self.db.powerranger_col3.delete_one({"_id": removed_doc["_id"]})
            if idx < len(self.action_clients3):
                client = self.action_clients3.pop(idx); self.action_names3.pop(idx)
                try: await client.disconnect()
                except: pass
                await event.reply(f"✅ Removed '{removed_doc.get('name')}' from Pool 3.")
            else:
                await event.reply(f"✅ Removed from DB.")

        # ======== COPY MODE ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/copyon$"))
        async def copyon(event):
            if event.sender_id != Config.OWNER_ID: return
            self.is_copy_active = True
            await event.reply("🎯 Copy Mode: ON")
        @self.bot_client.on(events.NewMessage(pattern=r"^/copyoff$"))
        async def copyoff(event):
            if event.sender_id != Config.OWNER_ID: return
            self.is_copy_active = False
            await event.reply("🔇 Copy Mode: OFF.")

        # ======== GROUP MANAGEMENT – POOL 1, 2, 3 ========
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
            all_clients = self.action_clients.copy()
            if not all_clients:
                await event.reply("❌ No action clients in Pool 1.")
                return
            await event.reply(f"⏳ Joining group with {len(all_clients)} clients (Pool 1)...")
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

        @self.bot_client.on(events.NewMessage(pattern=r"^/go2$"))
        async def go_group2(event):
            if event.sender_id != Config.OWNER_ID: return
            if not event.is_reply:
                await event.reply("❌ `/go2` must be used in reply to an invite link.")
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
            all_clients = self.action_clients2.copy()
            if not all_clients:
                await event.reply("❌ No action clients in Pool 2.")
                return
            await event.reply(f"⏳ Joining group with {len(all_clients)} clients (Pool 2)...")
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
                await event.reply(f"✅ Joined group `{chat.title}` with {success} clients (Pool 2). ID: `{chat.id}`")
            except:
                await event.reply(f"✅ Joined with {success} clients (Pool 2), but couldn't fetch ID.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/go3$"))
        async def go_group3(event):
            if event.sender_id != Config.OWNER_ID: return
            if not event.is_reply:
                await event.reply("❌ `/go3` must be used in reply to an invite link.")
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
            all_clients = self.action_clients3.copy()
            if not all_clients:
                await event.reply("❌ No action clients in Pool 3.")
                return
            await event.reply(f"⏳ Joining group with {len(all_clients)} clients (Pool 3)...")
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
                await event.reply(f"✅ Joined group `{chat.title}` with {success} clients (Pool 3). ID: `{chat.id}`")
            except:
                await event.reply(f"✅ Joined with {success} clients (Pool 3), but couldn't fetch ID.")

        # ======== SETMATRIX ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/setmatrix$"))
        async def set_matrix(event):
            if event.sender_id != Config.OWNER_ID: return
            args = event.message.text.split(maxsplit=1)
            if len(args) < 2:
                await event.reply(f"❌ Usage: `/setmatrix <group_id>`")
                return
            target = args[1].strip()
            resolver = self.action_clients[0] if self.action_clients else None
            if not resolver:
                await event.reply("❌ No action client.")
                return
            try:
                entity_ref = int(target) if target.lstrip('-').isdigit() else target
                entity = await resolver.get_entity(entity_ref)
                self.matrix_group_id = entity.id
                await self.db.marcuz_col.update_one({"key": "matrix_group_id"}, {"$set": {"value": self.matrix_group_id}}, upsert=True)
                await event.reply(f"✅ Matrix Group set to `{entity.title}` (ID: `{self.matrix_group_id}`)")
            except Exception as e:
                await event.reply(f"❌ Failed: {e}")

        # ======== STATUS ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/status$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID: return
            taunt_count = sum(len(s) for s in self.delete_and_taunt_targets.values())
            learned_count = await self.db.learned.count_documents({})
            talk_phrases_count = await self.db.talk_phrases.count_documents({})
            active_talk = len([c for c, r in self.talk_tasks.items() if r])
            msg = (
                f"📊 **Status**\n"
                f"🤖 Pool1: {len(self.action_clients)}\n"
                f"🤖 Pool2: {len(self.action_clients2)}\n"
                f"🤖 Pool3: {len(self.action_clients3)}\n"
                f"🗂️ Learned: {learned_count}\n"
                f"💾 Save: {'ON' if self.save_status else 'OFF'}\n"
                f"🔄 Cleanup: {'ON' if self.auto_cleanup else 'OFF'}\n"
                f"🗣️ Talk: {active_talk}\n"
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

        # ======== MODERATION HANDLERS ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/mute(?:\s+(.*))?$"))
        async def handler_mute(event): await self.mute_user(event)
        @self.bot_client.on(events.NewMessage(pattern=r"^/unmute(?:\s+(.*))?$"))
        async def handler_unmute(event): await self.unmute_user(event)
        @self.bot_client.on(events.NewMessage(pattern=r"^/ban(?:\s+(.*))?$"))
        async def handler_ban(event): await self.ban_user(event)
        @self.bot_client.on(events.NewMessage(pattern=r"^/unban(?:\s+(.*))?$"))
        async def handler_unban(event): await self.unban_user(event)
        @self.bot_client.on(events.NewMessage(pattern=r"^/kick(?:\s+(.*))?$"))
        async def handler_kick(event): await self.kick_user(event)

        # ======== CHANNEL ADMIN ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/start(?:\s+(\S+))?$"))
        async def handler_start(event): await self.start_handler(event)
        @self.bot_client.on(events.NewMessage(pattern=r"^/notifyall(?:\s+(.+))?$"))
        async def handler_notify(event): await self.notify_all_subscribers(event)
        @self.bot_client.on(events.NewMessage(incoming=True))
        async def handler_forward_media(event): await self.forward_media_to_channel(event)

        # ======== BOT WATCHLIST ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/delete\s+(\d+)$"))
        async def delete_bot_command(event):
            if event.sender_id != Config.OWNER_ID: return
            if event.chat_id != Config.TARGET_GROUP: return
            bot_id = int(event.pattern_match.group(1))
            await self.db.bot_watchlist.update_one({"chat_id": event.chat_id}, {"$addToSet": {"bot_ids": bot_id}}, upsert=True)
            if event.chat_id not in self.bot_watchlist_cache: self.bot_watchlist_cache[event.chat_id] = set()
            self.bot_watchlist_cache[event.chat_id].add(bot_id)
            await event.reply(f"✅ Bot ID `{bot_id}` will be deleted automatically (5s delay).")
        @self.bot_client.on(events.NewMessage(pattern=r"^/delete_remove\s+(\d+)$"))
        async def delete_bot_remove(event):
            if event.sender_id != Config.OWNER_ID: return
            if event.chat_id != Config.TARGET_GROUP: return
            bot_id = int(event.pattern_match.group(1))
            await self.db.bot_watchlist.update_one({"chat_id": event.chat_id}, {"$pull": {"bot_ids": bot_id}})
            if event.chat_id in self.bot_watchlist_cache: self.bot_watchlist_cache[event.chat_id].discard(bot_id)
            await event.reply(f"✅ Bot ID `{bot_id}` removed.")

        # ======== RANDOM TALK ========
        @self.bot_client.on(events.NewMessage(pattern=r"^/savetalk(?:\s+(.+))?$"))
        async def savetalk(event):
            if event.sender_id != Config.OWNER_ID: return
            link = event.pattern_match.group(1)
            if not link and event.is_reply:
                reply = await event.get_reply_message()
                if reply and reply.text:
                    link = reply.text.strip()
            if not link:
                await event.reply("❌ Usage: `/savetalk <group_link>`")
                return
            link_match = re.search(r'(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)', link)
            if not link_match:
                await event.reply("❌ Invalid invite link.")
                return
            invite_link = link_match.group(0)
            if 'joinchat/' in invite_link:
                hash_part = invite_link.split('joinchat/')[1].split('?')[0]
            elif '+' in invite_link:
                hash_part = invite_link.split('+')[1].split('?')[0]
            else:
                await event.reply("❌ Could not parse hash.")
                return
            all_clients = self.action_clients.copy()
            if not all_clients:
                await event.reply("❌ No action clients.")
                return
            group_id = None; group_title = None
            for client in all_clients:
                try:
                    chat = await client.get_entity(invite_link)
                    group_id = chat.id; group_title = chat.title; break
                except: continue
            if group_id is None:
                joined = 0
                for client in all_clients:
                    try:
                        await client(ImportChatInviteRequest(hash_part)); joined += 1
                    except errors.rpcerrorlist.UserAlreadyParticipantError: joined += 1
                    except: pass
                    await asyncio.sleep(0.3)
                if joined == 0:
                    await event.reply("❌ Could not join.")
                    return
                for client in all_clients:
                    try:
                        chat = await client.get_entity(invite_link)
                        group_id = chat.id; group_title = chat.title; break
                    except: continue
                if group_id is None:
                    await event.reply("❌ Joined but couldn't fetch info.")
                    return
            await event.reply(f"✅ Found `{group_title}`. Saving messages...")
            saved = 0
            try:
                client_to_use = None
                for client in all_clients:
                    try:
                        async for msg in client.iter_messages(group_id, limit=1):
                            break
                        client_to_use = client; break
                    except: continue
                if client_to_use is None:
                    await event.reply("❌ No client can read.")
                    return
                async for msg in client_to_use.iter_messages(group_id, limit=10000):
                    if msg.text and not msg.text.startswith('/'):
                        text = msg.text.strip()
                        if text:
                            try:
                                await self.db.talk_phrases.update_one({"group_id": group_id, "text": text}, {"$set": {"group_id": group_id, "text": text}}, upsert=True)
                                saved += 1
                            except DuplicateKeyError: pass
                            except Exception as e: logger.error(f"Talk save error: {e}")
                    if saved % 100 == 0: await asyncio.sleep(0.1)
            except Exception as e:
                await event.reply(f"⚠️ Error: {e}")
                return
            await event.reply(f"✅ Saved {saved} phrases from `{group_title}` (ID: {group_id}). Use `/talk {group_id}`")

        @self.bot_client.on(events.NewMessage(pattern=r"^/talk(?:\s+(-?\d+))?$"))
        async def talk_command(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id
            source_group_id = event.pattern_match.group(1)
            if not source_group_id:
                doc = await self.db.talk_phrases.find_one(sort=[("_id", -1)])
                if doc: source_group_id = doc.get("group_id")
                else:
                    await event.reply("❌ No talk phrases saved.")
                    return
            else: source_group_id = int(source_group_id)
            count = await self.db.talk_phrases.count_documents({"group_id": source_group_id})
            if count == 0:
                await event.reply(f"❌ No phrases for group {source_group_id}.")
                return
            await self.start_talk_loop(chat_id, source_group_id)
            await event.reply(f"🗣️ Talk started using group {source_group_id}.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/stoptalk$"))
        async def stoptalk(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id
            if chat_id in self.talk_tasks:
                self.talk_tasks[chat_id] = False
                await event.reply("🛑 Talk stopped.")
            else:
                await event.reply("ℹ️ No active talk.")

        # ======== UNIVERSAL WATCHER (FULL) ========
        @self.bot_client.on(events.NewMessage())
        async def watcher(event):
            if event.is_private: return
            all_ids = self.action_ids | self.action_ids2 | self.action_ids3
            if event.sender_id == self.bot_id or event.sender_id in all_ids:
                return
            chat_id = event.chat_id; sender_id = event.sender_id

            # 1. Bot Watchlist
            if chat_id in self.bot_watchlist_cache and sender_id in self.bot_watchlist_cache[chat_id]:
                if not event.text or not event.text.startswith('/'):
                    async def delete_after_delay(msg_id, t_chat_id, target_sender_id):
                        await asyncio.sleep(5)
                        client = await self.get_action_client()
                        deleter = client if client else self.bot_client
                        if deleter:
                            try:
                                await deleter.delete_messages(t_chat_id, [msg_id])
                                await deleter.send_message(t_chat_id, f"✅ Okay ငါဖျက်ပေးမယ် (Bot ID: {target_sender_id})")
                            except: pass
                    asyncio.create_task(delete_after_delay(event.id, chat_id, sender_id))
                    return

            # 2. Catcher Bot
            if chat_id == Config.CATCHER_CHAT and sender_id == Config.CATCHER_BOT_ID:
                if chat_id in self.catcher_processing: return
                self.catcher_processing.add(chat_id)
                try:
                    client = await self.get_action_client()
                    if client:
                        try: await client.pin_message(chat_id, event.id)
                        except: pass
                        async def delete_catcher():
                            ids = []
                            async for msg in client.iter_messages(chat_id, sender_id=Config.CATCHER_BOT_ID, limit=500):
                                if msg.id != event.id:
                                    ids.append(msg.id)
                                if len(ids) >= 100:
                                    await client.delete_messages(chat_id, ids); ids = []; await asyncio.sleep(0.5)
                            if ids: await client.delete_messages(chat_id, ids)
                        asyncio.create_task(delete_catcher())
                finally:
                    self.catcher_processing.discard(chat_id)
                return

            # 3. Dark Passenger (Pool 1, 2, 3)
            if chat_id in self.dark_passenger_targets and sender_id == self.dark_passenger_targets[chat_id]:
                if event.text and not event.text.startswith(('/', '.', 'မှတ်')):
                    client = await self.get_action_client()
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
            if chat_id in self.dark_passenger_targets2 and sender_id == self.dark_passenger_targets2[chat_id]:
                if event.text and not event.text.startswith(('/', '.', 'မှတ်')):
                    client = await self.get_action_client2()
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
            if chat_id in self.dark_passenger_targets3 and sender_id == self.dark_passenger_targets3[chat_id]:
                if event.text and not event.text.startswith(('/', '.', 'မှတ်')):
                    client = await self.get_action_client3()
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

            # 4. Delete and Taunt (Shared)
            if chat_id in self.delete_and_taunt_targets and sender_id in self.delete_and_taunt_targets[chat_id]:
                if event.text:
                    client = await self.get_action_client()
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

            # 5. Save System
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

            # 6. Tracking (Pool 1, 2, 3)
            if chat_id in self.tracking_targets and sender_id == self.tracking_targets[chat_id]:
                target = await event.get_sender()
                mention = self.format_mention(sender_id, target.first_name or "Target")
                client = await self.get_action_client()
                if client:
                    phrase = await self.get_next_phrase(chat_id)
                    try:
                        sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                        await self._handle_message_sent(chat_id, sent.id)
                    except: pass
            if chat_id in self.tracking_targets2 and sender_id == self.tracking_targets2[chat_id]:
                target = await event.get_sender()
                mention = self.format_mention(sender_id, target.first_name or "Target")
                client = await self.get_action_client2()
                if client:
                    phrase = await self.get_next_phrase(chat_id)
                    try:
                        sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                        await self._handle_message_sent(chat_id, sent.id)
                    except: pass
            if chat_id in self.tracking_targets3 and sender_id == self.tracking_targets3[chat_id]:
                target = await event.get_sender()
                mention = self.format_mention(sender_id, target.first_name or "Target")
                client = await self.get_action_client3()
                if client:
                    phrase = await self.get_next_phrase(chat_id)
                    try:
                        sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                        await self._handle_message_sent(chat_id, sent.id)
                    except: pass

            # 7. Copy Mode
            if self.is_copy_active and chat_id == self.matrix_group_id and sender_id == Config.OWNER_ID:
                text = event.text
                if text and not text.startswith('/'):
                    for client in self.action_clients:
                        try:
                            await client.send_message(chat_id, text)
                            await asyncio.sleep(0.2)
                        except: pass

            # 8. Custom Filters
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

            # 9. Protect Sovereign
            if event.text and event.text.startswith(("ချိန်ထား", "ပစ်သတ်")):
                reply = await event.get_reply_message()
                if reply and reply.sender_id == Config.OWNER_ID and event.sender_id != Config.OWNER_ID:
                    client = await self.get_action_client()
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

        await self.load_userbots()
        await self.load_userbots2()
        await self.load_userbots3()
        await self.load_taunt_targets()
        await self.load_bot_watchlist()

        threading.Thread(target=run_flask, daemon=True).start()
        await self.bot_client.run_until_disconnected()

    async def stop(self) -> None:
        if self.bot_client.is_connected():
            await self.bot_client.disconnect()
        await self.close_action_clients()
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
