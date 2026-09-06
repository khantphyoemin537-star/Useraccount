#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sovereign System – ORIGINAL FULL VERSION (Ninja Pools 1, 2, 3 + Group Management)
- Special Attack, Saved Messages Stop, /addspecial, Talk & Track REMOVED
- Full Group Management (Mute, Ban, Kick, Go, Copy, Setmatrix, etc.) INCLUDED
- Fixed MongoDB Index Error inside main.py
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
    SPAM_DELAY = 1
    MAX_RETRIES = 3

    SOURCE_GROUP_ID = int(os.getenv("SOURCE_GROUP_ID", "-1003877873337"))
    TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "-1003754813090"))
    CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/freevipallinone")

    CATCHER_CHAT = -1004437409107
    CATCHER_BOT_ID = 6157455819

SPAM_TEXT = """ @Imjustkidding_bot , @fuckyourwifey_bot rjsjsjsjssjsjjssjsjdjsjsjsjzjsjsjssnsnsnsndndndjsdjdndjdjdjdjdjsjdjdjdjdjdjsjsnsj """
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
                self.client = AsyncIOMotorClient(self.uri, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=5000)
                await self.client.admin.command("ping")
                self.db = self.client["telegram_bot"]
                
                # ✅ Fixed MongoDB Error here (No need to go to Atlas)
                try:
                    await self.db.learned_new.drop_index("text_1")
                    logger.info("Dropped old unique index 'text_1'")
                except Exception as e:
                    logger.info(f"No existing index to drop: {e}")
                
                await self.db.learned_new.create_index("text", unique=False, sparse=True)
                logger.info("Created new non-unique index 'text_1'")
                
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
    def taunt_targets(self): return self.db["taunt_targets"]
    @property
    def muted_registry(self): return self.db["muted_registry"]
    @property
    def channel_subscribers(self): return self.db["channel_subscribers"]
    @property
    def bot_watchlist(self): return self.db["bot_watchlist"]

# ------------------------------------------------------------------
#  MAIN BOT CLASS
# ------------------------------------------------------------------
class SovereignBot:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.bot_client = TelegramClient("bot_main_session", Config.API_ID, Config.API_HASH, flood_sleep_threshold=60)
        self.bot_id: Optional[int] = None

        # Ninja Pool 1
        self.ninja_clients: List[TelegramClient] = []
        self.ninja_names: List[str] = []
        self.ninja_ids: Set[int] = set()
        self.ninja_bully_tasks: Dict[int, bool] = {}
        self.ninja_shoot_tasks: Dict[int, bool] = {}
        self.ninja_spam_tasks: Dict[int, bool] = {}

        # Ninja Pool 2
        self.ninja_clients2: List[TelegramClient] = []
        self.ninja_names2: List[str] = []
        self.ninja_ids2: Set[int] = set()
        self.ninja_bully_tasks2: Dict[int, bool] = {}
        self.ninja_shoot_tasks2: Dict[int, bool] = {}
        self.ninja_spam_tasks2: Dict[int, bool] = {}

        # Ninja Pool 3
        self.ninja_clients3: List[TelegramClient] = []
        self.ninja_names3: List[str] = []
        self.ninja_ids3: Set[int] = set()
        self.ninja_bully_tasks3: Dict[int, bool] = {}
        self.ninja_shoot_tasks3: Dict[int, bool] = {}
        self.ninja_spam_tasks3: Dict[int, bool] = {}

        # Group Management & Other Features
        self.delete_and_taunt_targets: Dict[int, Set[int]] = {}
        self.save_status = False
        self.phrase_lists: Dict[int, List[str]] = {}
        self.phrase_indices: Dict[int, int] = {}
        self.is_copy_active = False
        self.matrix_group_id: Optional[int] = None

        self.sticker_spam_data = {}
        self.char_spam_data = {}
        self.admin_warned_sticker = set()
        self.admin_warned_char = set()
        self.admin_cache = {}
        self.bot_watchlist_cache: Dict[int, Set[int]] = {}
        self.catcher_processing: Set[int] = set()
        self.auto_cleanup = False
        self.msg_queues: Dict[int, List[int]] = {}
        self.queue_locks: Dict[int, asyncio.Lock] = {}

        self._register_handlers()

    # --------------------------------------------------------------
    #  NINJA POOL LOADING
    # --------------------------------------------------------------
    async def load_ninja_pools(self) -> None:
        await self._load_pool(self.db.ninja_col, self.ninja_clients, self.ninja_names, self.ninja_ids, "Ninja Pool 1")
        await self._load_pool(self.db.ninja_col2, self.ninja_clients2, self.ninja_names2, self.ninja_ids2, "Ninja Pool 2")
        await self._load_pool(self.db.ninja_col3, self.ninja_clients3, self.ninja_names3, self.ninja_ids3, "Ninja Pool 3")

    async def _load_pool(self, collection, clients_list, names_list, ids_set, pool_name):
        for client in clients_list:
            try: await client.disconnect()
            except: pass
        clients_list.clear(); names_list.clear(); ids_set.clear()
        async for pr_doc in collection.find():
            session_str = pr_doc.get("session")
            if not session_str: continue
            try:
                client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
                await client.start()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    clients_list.append(client)
                    names_list.append(pr_doc.get("name", f"Ninja-{len(clients_list)}"))
                    ids_set.add(me.id)
                    logger.info(f"✅ {pool_name} – {pr_doc.get('name')} loaded")
                else:
                    await client.disconnect()
            except Exception as e:
                logger.error(f"❌ {pool_name} – failed: {e}")

    async def _get_ninja_client(self, pool: int = 1) -> Optional[TelegramClient]:
        pools = [self.ninja_clients, self.ninja_clients2, self.ninja_clients3]
        clients = pools[pool-1]
        if not clients: return None
        for client in random.sample(clients, len(clients)):
            try:
                await client.get_me()
                return client
            except: continue
        return None

    # --------------------------------------------------------------
    #  HELPERS
    # --------------------------------------------------------------
    def format_mention(self, user_id: int, name: str) -> str:
        return f"<a href='tg://user?id={user_id}'>{escape_html(name)}</a>"

    async def check_admin(self, chat_id: int, user_id: int) -> bool:
        if user_id == Config.OWNER_ID: return True
        if chat_id in self.admin_cache:
            return user_id in self.admin_cache[chat_id]["ids"]
        await self._update_admin_cache(chat_id)
        return user_id in self.admin_cache.get(chat_id, {"ids": set()})["ids"]

    async def check_ban_rights(self, chat_id: int, user_id: int) -> bool:
        if user_id == Config.OWNER_ID: return True
        try:
            permissions = await self.bot_client.get_permissions(chat_id, user_id)
            return permissions.is_admin and permissions.ban_users
        except:
            return False

    async def _update_admin_cache(self, chat_id: int):
        try:
            admins = await self.bot_client(GetParticipantsRequest(channel=chat_id, filter=ChannelParticipantsAdmins(), offset=0, limit=200, hash=0))
            self.admin_cache[chat_id] = {"ids": {p.user_id for p in admins.participants}, "expiry": time.time() + 300}
        except: self.admin_cache[chat_id] = {"ids": set(), "expiry": time.time() + 300}

    async def is_allowed(self, user_id: int) -> bool:
        if user_id == Config.OWNER_ID: return True
        doc = await self.db.allowed_users.find_one({"user_id": user_id})
        return doc is not None

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

    async def fetch_learned_phrases(self) -> List[str]:
        docs = await self.db.learned.find().to_list(length=10000)
        return [d.get("text") for d in docs if d.get("text")] or ["မင်းက ဒီမှာ ပိုလျှံနေတဲ့ အရာပဲ"]
    
    async def get_next_phrase(self, chat_id: int) -> str:
        if chat_id not in self.phrase_lists:
            self.phrase_lists[chat_id] = await self.fetch_learned_phrases()
            random.shuffle(self.phrase_lists[chat_id])
            self.phrase_indices[chat_id] = 0
        idx = self.phrase_indices[chat_id]
        phrase = self.phrase_lists[chat_id][idx]
        self.phrase_indices[chat_id] = (idx + 1) % len(self.phrase_lists[chat_id])
        return phrase

    async def _handle_message_sent(self, chat_id: int, msg_id: int):
        if not self.auto_cleanup or chat_id == Config.LEARNING_GROUP: return
        if chat_id not in self.msg_queues: self.msg_queues[chat_id] = []
        self.msg_queues[chat_id].append(msg_id)
        if len(self.msg_queues[chat_id]) >= 100:
            ids = self.msg_queues[chat_id].copy(); self.msg_queues[chat_id].clear()
            try: await self.bot_client.delete_messages(chat_id, ids)
            except: pass

    def reset_phrase_cycle(self, chat_id: int):
        self.phrase_lists.pop(chat_id, None)
        self.phrase_indices.pop(chat_id, None)

    # --------------------------------------------------------------
    #  COMMAND HANDLERS (GROUP MANAGEMENT FULL)
    # --------------------------------------------------------------
    def _register_handlers(self):

        # STOP
        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop)$"))
        async def stop_attack(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id
            stopped = False
            if chat_id in self.ninja_bully_tasks: self.ninja_bully_tasks[chat_id] = False; stopped = True
            if chat_id in self.ninja_shoot_tasks: self.ninja_shoot_tasks[chat_id] = False; stopped = True
            if chat_id in self.ninja_spam_tasks: self.ninja_spam_tasks[chat_id] = False; stopped = True
            if chat_id in self.ninja_bully_tasks2: self.ninja_bully_tasks2[chat_id] = False; stopped = True
            if chat_id in self.ninja_shoot_tasks2: self.ninja_shoot_tasks2[chat_id] = False; stopped = True
            if chat_id in self.ninja_spam_tasks2: self.ninja_spam_tasks2[chat_id] = False; stopped = True
            if chat_id in self.ninja_bully_tasks3: self.ninja_bully_tasks3[chat_id] = False; stopped = True
            if chat_id in self.ninja_shoot_tasks3: self.ninja_shoot_tasks3[chat_id] = False; stopped = True
            if chat_id in self.ninja_spam_tasks3: self.ninja_spam_tasks3[chat_id] = False; stopped = True
            self.reset_phrase_cycle(chat_id)
            if stopped:
                await event.reply("🛑 All active attacks stopped in this chat.")
            else:
                await event.reply("ℹ️ No active attacks to stop.")

        # UNIVERSAL WATCHER
        @self.bot_client.on(events.NewMessage())
        async def watcher(event):
            if event.is_private: return
            all_ids = self.ninja_ids | self.ninja_ids2 | self.ninja_ids3
            if event.sender_id == self.bot_id or event.sender_id in all_ids: return
            chat_id = event.chat_id; sender_id = event.sender_id

            # SAVE SYSTEM
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

            # BULLY
            if event.text in ["/bully", "အနိုင်ကျင့်", "/bully2", "အနိုင်ကျင့်2", "/bully3", "အနိုင်ကျင့်3"]:
                if not await self.is_allowed(sender_id): return
                reply = await event.get_reply_message()
                if not reply: return
                target = await reply.get_sender()
                if target.id == Config.OWNER_ID: return
                pool = 1
                if "/bully2" in event.text or "အနိုင်ကျင့်2" in event.text: pool = 2
                elif "/bully3" in event.text or "အနိုင်ကျင့်3" in event.text: pool = 3
                self.reset_phrase_cycle(chat_id)
                if pool == 1: self.ninja_bully_tasks[chat_id] = True
                elif pool == 2: self.ninja_bully_tasks2[chat_id] = True
                else: self.ninja_bully_tasks3[chat_id] = True
                
                async def bully_loop(pool=pool):
                    task_dict = [self.ninja_bully_tasks, self.ninja_bully_tasks2, self.ninja_bully_tasks3][pool-1]
                    while task_dict.get(chat_id, False):
                        client = await self._get_ninja_client(pool)
                        if not client: await asyncio.sleep(1); continue
                        phrase = await self.get_next_phrase(chat_id)
                        try:
                            mention = self.format_mention(target.id, target.first_name or "Target")
                            sent = await client.send_message(chat_id, f"{mention} {phrase}", reply_to=reply.id, parse_mode='html')
                            await self._handle_message_sent(chat_id, sent.id)
                            await asyncio.sleep(Config.BULLY_DELAY)
                        except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
                        except Exception as e: logger.error(f"Bully error: {e}"); await asyncio.sleep(1)
                asyncio.create_task(bully_loop(pool))

            # SHOOT
            if event.text in ["/shoot", "ပစ်", "/shoot2", "ပစ်2", "/shoot3", "ပစ်3"]:
                if not await self.is_allowed(sender_id): return
                reply = await event.get_reply_message()
                if not reply: return
                target = await reply.get_sender()
                if target.id == Config.OWNER_ID: return
                pool = 1
                if "/shoot2" in event.text or "ပစ်2" in event.text: pool = 2
                elif "/shoot3" in event.text or "ပစ်3" in event.text: pool = 3
                self.reset_phrase_cycle(chat_id)
                if pool == 1: self.ninja_shoot_tasks[chat_id] = True
                elif pool == 2: self.ninja_shoot_tasks2[chat_id] = True
                else: self.ninja_shoot_tasks3[chat_id] = True
                
                async def shoot_loop(pool=pool):
                    task_dict = [self.ninja_shoot_tasks, self.ninja_shoot_tasks2, self.ninja_shoot_tasks3][pool-1]
                    while task_dict.get(chat_id, False):
                        client = await self._get_ninja_client(pool)
                        if not client: await asyncio.sleep(1); continue
                        phrase = await self.get_next_phrase(chat_id)
                        try:
                            mention = self.format_mention(target.id, target.first_name or "Target")
                            sent = await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                            await self._handle_message_sent(chat_id, sent.id)
                            await asyncio.sleep(Config.SHOOT_DELAY)
                        except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
                        except Exception as e: logger.error(f"Shoot error: {e}"); await asyncio.sleep(1)
                asyncio.create_task(shoot_loop(pool))

            # SPAM
            if event.text in ["/spam", "/spam2", "/spam3"]:
                if not await self.is_allowed(sender_id): return
                pool = 1
                if event.text == "/spam2": pool = 2
                elif event.text == "/spam3": pool = 3
                async def spam_loop(pool=pool):
                    task_dict = [self.ninja_spam_tasks, self.ninja_spam_tasks2, self.ninja_spam_tasks3][pool-1]
                    if task_dict.get(chat_id, False): return
                    task_dict[chat_id] = True
                    while task_dict.get(chat_id, False):
                        client = await self._get_ninja_client(pool)
                        if not client: await asyncio.sleep(1); continue
                        try:
                            sent = await client.send_message(chat_id, SPAM_TEXT)
                            await self._handle_message_sent(chat_id, sent.id)
                            await asyncio.sleep(Config.SPAM_DELAY)
                        except Exception as e: logger.error(f"Spam error: {e}"); await asyncio.sleep(2)
                asyncio.create_task(spam_loop(pool))

            # DELETE AND TAUNT
            if event.text == "ဖာသည်မသား":
                if not await self.is_allowed(sender_id): return
                reply = await event.get_reply_message()
                if not reply: return
                target = await reply.get_sender()
                if target.id == Config.OWNER_ID: return
                try: await self.bot_client.delete_messages(chat_id, [reply.id])
                except: pass
                if chat_id not in self.delete_and_taunt_targets: self.delete_and_taunt_targets[chat_id] = set()
                self.delete_and_taunt_targets[chat_id].add(target.id)
                await self.db.taunt_targets.update_one({"chat_id": chat_id}, {"$addToSet": {"target_ids": target.id}}, upsert=True)
                client = await self._get_ninja_client(1)
                if client:
                    phrase = await self.get_next_phrase(chat_id)
                    sent = await client.send_message(chat_id, f"{self.format_mention(target.id, target.first_name or 'Target')} {phrase}", parse_mode='html')
                    await self._handle_message_sent(chat_id, sent.id)

        # ADD NINJA
        @self.bot_client.on(events.NewMessage(pattern=r"^/addninja(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_ninja(event):
            if event.sender_id != Config.OWNER_ID: return
            cmd_args = event.pattern_match.group(1); session_str = event.pattern_match.group(2)
            name = cmd_args if cmd_args and not session_str else "Ninja"
            if not session_str:
                reply = await event.get_reply_message()
                if reply and reply.text: session_str = reply.text.strip()
                else: await event.reply("❓ Usage: `/addninja <name> <session_string>`"); return
            if not session_str or len(session_str) < 10: await event.reply("❌ Invalid session string."); return
            async for doc in self.db.ninja_col.find():
                if doc.get("session") == session_str: await event.reply("⚠️ This session already exists in Ninja Pool 1."); return
            await self.db.ninja_col.insert_one({"name": name, "session": session_str})
            client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            try:
                await client.start(); me = await client.get_me()
                self.ninja_clients.append(client); self.ninja_names.append(name); self.ninja_ids.add(me.id)
                await event.reply(f"✅ '{name}' added to Ninja Pool 1! Total: {len(self.ninja_clients)}")
            except Exception as e: await event.reply(f"❌ Failed: {str(e)}"); await self.db.ninja_col.delete_one({"session": session_str})

        @self.bot_client.on(events.NewMessage(pattern=r"^/addninja2(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_ninja2(event):
            if event.sender_id != Config.OWNER_ID: return
            cmd_args = event.pattern_match.group(1); session_str = event.pattern_match.group(2)
            name = cmd_args if cmd_args and not session_str else "Ninja2"
            if not session_str:
                reply = await event.get_reply_message()
                if reply and reply.text: session_str = reply.text.strip()
                else: await event.reply("❓ Usage: `/addninja2 <name> <session_string>`"); return
            if not session_str or len(session_str) < 10: await event.reply("❌ Invalid session string."); return
            async for doc in self.db.ninja_col2.find():
                if doc.get("session") == session_str: await event.reply("⚠️ This session already exists in Ninja Pool 2."); return
            await self.db.ninja_col2.insert_one({"name": name, "session": session_str})
            client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            try:
                await client.start(); me = await client.get_me()
                self.ninja_clients2.append(client); self.ninja_names2.append(name); self.ninja_ids2.add(me.id)
                await event.reply(f"✅ '{name}' added to Ninja Pool 2! Total: {len(self.ninja_clients2)}")
            except Exception as e: await event.reply(f"❌ Failed: {str(e)}"); await self.db.ninja_col2.delete_one({"session": session_str})

        @self.bot_client.on(events.NewMessage(pattern=r"^/addninja3(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_ninja3(event):
            if event.sender_id != Config.OWNER_ID: return
            cmd_args = event.pattern_match.group(1); session_str = event.pattern_match.group(2)
            name = cmd_args if cmd_args and not session_str else "Ninja3"
            if not session_str:
                reply = await event.get_reply_message()
                if reply and reply.text: session_str = reply.text.strip()
                else: await event.reply("❓ Usage: `/addninja3 <name> <session_string>`"); return
            if not session_str or len(session_str) < 10: await event.reply("❌ Invalid session string."); return
            async for doc in self.db.ninja_col3.find():
                if doc.get("session") == session_str: await event.reply("⚠️ This session already exists in Ninja Pool 3."); return
            await self.db.ninja_col3.insert_one({"name": name, "session": session_str})
            client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
            try:
                await client.start(); me = await client.get_me()
                self.ninja_clients3.append(client); self.ninja_names3.append(name); self.ninja_ids3.add(me.id)
                await event.reply(f"✅ '{name}' added to Ninja Pool 3! Total: {len(self.ninja_clients3)}")
            except Exception as e: await event.reply(f"❌ Failed: {str(e)}"); await self.db.ninja_col3.delete_one({"session": session_str})

        # MODERATION
        @self.bot_client.on(events.NewMessage(pattern=r"^/mute(?:\s+(.*))?$"))
        async def handler_mute(event):
            if not await self.check_admin(event.chat_id, event.sender_id): return
            target_id = None
            args_text = event.pattern_match.group(1)
            if event.is_reply:
                reply_msg = await event.get_reply_message(); target_id = reply_msg.sender_id
            else:
                if args_text:
                    target_str = args_text.strip().split()[0]
                    if target_str.isdigit(): target_id = int(target_str)
                    else:
                        try: target_id = (await event.client.get_entity(target_str)).id
                        except: await event.reply("⚠️ User not found."); return
                else: await event.reply("⚠️ Usage: /mute (reply) or /mute [@username]"); return
            if not target_id: return
            bot_me = await event.client.get_me()
            if target_id == bot_me.id or target_id == Config.OWNER_ID: await event.reply("❌ Cannot mute the bot or the owner."); return
            try:
                await event.client.edit_permissions(event.chat_id, target_id, send_messages=False, send_media=False, send_stickers=False, send_gifs=False)
                user_entity = await event.client.get_entity(target_id)
                mention = self.format_mention(target_id, f"{user_entity.first_name or 'User'}")
                await event.reply(f"<b>MUTE OPERATION SUCCESS!</b>\n<b>{mention}</b> has been silenced.", parse_mode='html')
            except Exception as e: await event.reply(f"❌ Error: {str(e)}")

        @self.bot_client.on(events.NewMessage(pattern=r"^/unmute(?:\s+(.*))?$"))
        async def handler_unmute(event):
            if not await self.check_ban_rights(event.chat_id, event.sender_id): return
            target_user = await self.get_target_user(event, event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') else None)
            if not target_user: return
            try:
                await self.bot_client.edit_permissions(event.chat_id, target_user.id, send_messages=True)
                await self.db.muted_registry.delete_one({"chat_id": event.chat_id, "user_id": target_user.id})
                mention = self.format_mention(target_user.id, target_user.first_name or 'User')
                await event.reply(f"🌌 <b>UNMUTE OPERATION</b>\n🔊 <b>Target:</b> {mention}\n⚡ <b>Status:</b> <code>Voice Restored</code>", parse_mode='html')
            except Exception as e: logger.error(f"Unmute Error: {e}")

        @self.bot_client.on(events.NewMessage(pattern=r"^/ban(?:\s+(.*))?$"))
        async def handler_ban(event):
            if not await self.check_ban_rights(event.chat_id, event.sender_id): return
            target_user = await self.get_target_user(event, event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') else None)
            if not target_user: return
            try:
                await self.bot_client.edit_permissions(event.chat_id, target_user.id, view_messages=False)
                mention = self.format_mention(target_user.id, target_user.first_name or 'User')
                await event.reply(f"🌌 <b>BAN OPERATION</b>\n🚫 <b>Target:</b> {mention}\n⚡ <b>Status:</b> <code>Exiled / Perm-Banned</code>", parse_mode='html')
            except Exception as e: logger.error(f"Ban Error: {e}")

        @self.bot_client.on(events.NewMessage(pattern=r"^/unban(?:\s+(.*))?$"))
        async def handler_unban(event):
            if not await self.check_ban_rights(event.chat_id, event.sender_id): return
            target_user = await self.get_target_user(event, event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') else None)
            if not target_user: return
            try:
                await self.bot_client.edit_permissions(event.chat_id, target_user.id, view_messages=True)
                mention = self.format_mention(target_user.id, target_user.first_name or 'User')
                await event.reply(f"🌌 <b>UNBAN OPERATION</b>\n✅ <b>Target:</b> {mention}\n⚡ <b>Status:</b> <code>Ban Lifted</code>", parse_mode='html')
            except Exception as e: logger.error(f"Unban Error: {e}")

        @self.bot_client.on(events.NewMessage(pattern=r"^/kick(?:\s+(.*))?$"))
        async def handler_kick(event):
            if not await self.check_ban_rights(event.chat_id, event.sender_id): return
            target_user = await self.get_target_user(event, event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') else None)
            if not target_user: return
            try:
                await self.bot_client.edit_permissions(event.chat_id, target_user.id, view_messages=False)
                await self.bot_client.edit_permissions(event.chat_id, target_user.id, view_messages=True)
                mention = self.format_mention(target_user.id, target_user.first_name or 'User')
                await event.reply(f"🌌 <b>KICK OPERATION</b>\n💨 <b>Target:</b> {mention}\n⚡ <b>Status:</b> <code>Removed / Kicked</code>", parse_mode='html')
            except Exception as e: logger.error(f"Kick Error: {e}")

        # JOIN GROUPS (GO)
        @self.bot_client.on(events.NewMessage(pattern=r"^/go$"))
        async def go_group(event):
            if event.sender_id != Config.OWNER_ID: return
            if not event.is_reply: await event.reply("❌ `/go` must be used in reply to an invite link."); return
            reply = await event.get_reply_message()
            if not reply.text: await event.reply("❌ No text in reply."); return
            link_match = re.search(r'(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)', reply.text)
            if not link_match: await event.reply("❌ No valid invite link found."); return
            invite_link = link_match.group(0)
            hash_part = invite_link.split('joinchat/')[1].split('?')[0] if 'joinchat/' in invite_link else invite_link.split('+')[1].split('?')[0]
            if not hash_part: await event.reply("❌ Could not extract hash."); return
            all_clients = self.ninja_clients.copy()
            if not all_clients: await event.reply("❌ No ninja clients in Pool 1."); return
            await event.reply(f"⏳ Joining group with {len(all_clients)} clients...")
            success = 0
            for client in all_clients:
                try: await client(ImportChatInviteRequest(hash_part)); success += 1
                except errors.rpcerrorlist.UserAlreadyParticipantError: success += 1
                except FloodWaitError as e: await asyncio.sleep(e.seconds + 1); try: await client(ImportChatInviteRequest(hash_part)); success += 1
                except: pass
                except: pass
                await asyncio.sleep(0.3)
            try:
                chat = await all_clients[0].get_entity(invite_link)
                await event.reply(f"✅ Joined group `{chat.title}` with {success} clients. ID: `{chat.id}`")
            except: await event.reply(f"✅ Joined with {success} clients.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/go2$"))
        async def go_group2(event):
            if event.sender_id != Config.OWNER_ID: return
            if not event.is_reply: await event.reply("❌ `/go2` must be used in reply to an invite link."); return
            reply = await event.get_reply_message()
            if not reply.text: await event.reply("❌ No text in reply."); return
            link_match = re.search(r'(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)', reply.text)
            if not link_match: await event.reply("❌ No valid invite link found."); return
            invite_link = link_match.group(0)
            hash_part = invite_link.split('joinchat/')[1].split('?')[0] if 'joinchat/' in invite_link else invite_link.split('+')[1].split('?')[0]
            if not hash_part: await event.reply("❌ Could not extract hash."); return
            all_clients = self.ninja_clients2.copy()
            if not all_clients: await event.reply("❌ No ninja clients in Pool 2."); return
            await event.reply(f"⏳ Joining group with {len(all_clients)} clients...")
            success = 0
            for client in all_clients:
                try: await client(ImportChatInviteRequest(hash_part)); success += 1
                except errors.rpcerrorlist.UserAlreadyParticipantError: success += 1
                except FloodWaitError as e: await asyncio.sleep(e.seconds + 1); try: await client(ImportChatInviteRequest(hash_part)); success += 1
                except: pass
                except: pass
                await asyncio.sleep(0.3)
            try:
                chat = await all_clients[0].get_entity(invite_link)
                await event.reply(f"✅ Joined group `{chat.title}` with {success} clients (Pool 2). ID: `{chat.id}`")
            except: await event.reply(f"✅ Joined with {success} clients.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/go3$"))
        async def go_group3(event):
            if event.sender_id != Config.OWNER_ID: return
            if not event.is_reply: await event.reply("❌ `/go3` must be used in reply to an invite link."); return
            reply = await event.get_reply_message()
            if not reply.text: await event.reply("❌ No text in reply."); return
            link_match = re.search(r'(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)', reply.text)
            if not link_match: await event.reply("❌ No valid invite link found."); return
            invite_link = link_match.group(0)
            hash_part = invite_link.split('joinchat/')[1].split('?')[0] if 'joinchat/' in invite_link else invite_link.split('+')[1].split('?')[0]
            if not hash_part: await event.reply("❌ Could not extract hash."); return
            all_clients = self.ninja_clients3.copy()
            if not all_clients: await event.reply("❌ No ninja clients in Pool 3."); return
            await event.reply(f"⏳ Joining group with {len(all_clients)} clients...")
            success = 0
            for client in all_clients:
                try: await client(ImportChatInviteRequest(hash_part)); success += 1
                except errors.rpcerrorlist.UserAlreadyParticipantError: success += 1
                except FloodWaitError as e: await asyncio.sleep(e.seconds + 1); try: await client(ImportChatInviteRequest(hash_part)); success += 1
                except: pass
                except: pass
                await asyncio.sleep(0.3)
            try:
                chat = await all_clients[0].get_entity(invite_link)
                await event.reply(f"✅ Joined group `{chat.title}` with {success} clients (Pool 3). ID: `{chat.id}`")
            except: await event.reply(f"✅ Joined with {success} clients.")

        # SETMATRIX & COPY
        @self.bot_client.on(events.NewMessage(pattern=r"^/setmatrix(?:\s+(.+))?$"))
        async def set_matrix(event):
            if event.sender_id != Config.OWNER_ID: return
            args = event.message.text.split(maxsplit=1)
            if len(args) < 2: await event.reply(f"❌ Usage: `/setmatrix <group_id>`"); return
            target = args[1].strip()
            resolver = self.ninja_clients[0] if self.ninja_clients else None
            if not resolver: await event.reply("❌ No ninja client available."); return
            try:
                entity_ref = int(target) if target.lstrip('-').isdigit() else target
                entity = await resolver.get_entity(entity_ref)
                self.matrix_group_id = entity.id
                await self.db.marcuz_col.update_one({"key": "matrix_group_id"}, {"$set": {"value": self.matrix_group_id}}, upsert=True)
                await event.reply(f"✅ Matrix Group set to `{entity.title}` (ID: `{self.matrix_group_id}`)")
            except Exception as e: await event.reply(f"❌ Failed: {e}")

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

        # SAVE / CLEAR
        @self.bot_client.on(events.NewMessage(pattern=r"^/save on$"))
        async def save_on(event):
            if event.chat_id != Config.LEARNING_GROUP or not await self.is_allowed(event.sender_id): return
            self.save_status = True
            try: await event.delete()
            except: pass
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"✅ Save mode ON", parse_mode='html')

        @self.bot_client.on(events.NewMessage(pattern=r"^/save off$"))
        async def save_off(event):
            if event.chat_id != Config.LEARNING_GROUP or not await self.is_allowed(event.sender_id): return
            self.save_status = False
            try: await event.delete()
            except: pass
            await self.bot_client.send_message(Config.LEARNING_GROUP, f"⏸️ Save mode OFF", parse_mode='html')

        @self.bot_client.on(events.NewMessage(pattern=r"^/clearlearned$"))
        async def clear_learned(event):
            if event.sender_id != Config.OWNER_ID: return
            await event.reply("⚠️ Type `/clearlearned_confirm` to delete ALL learned phrases.")
        
        @self.bot_client.on(events.NewMessage(pattern=r"^/clearlearned_confirm$"))
        async def clear_learned_confirm(event):
            if event.sender_id != Config.OWNER_ID: return
            result = await self.db.learned.delete_many({})
            await event.reply(f"🗑️ Cleared {result.deleted_count} phrases.")
            self.phrase_lists.clear(); self.phrase_indices.clear()

        # ALLOW
        @self.bot_client.on(events.NewMessage(pattern=r"^/addallow(?:@\w+)?$"))
        async def add_allow(event):
            if event.sender_id != Config.OWNER_ID: return
            reply = await event.get_reply_message()
            if not reply: await event.reply("❓ Reply to a user."); return
            user = await reply.get_sender()
            await self.db.allowed_users.update_one({"user_id": user.id}, {"$set": {"name": user.first_name or "Unnamed"}}, upsert=True)
            await event.reply(f"✅ {self.format_mention(user.id, user.first_name or 'User')} added.", parse_mode='html')

        @self.bot_client.on(events.NewMessage(pattern=r"^/allowlist(?:@\w+)?$"))
        async def allow_list(event):
            if event.sender_id != Config.OWNER_ID: return
            users = await self.db.allowed_users.find().to_list(length=None)
            if not users: await event.reply("📭 Empty."); return
            lines = [f"• {self.format_mention(u['user_id'], u.get('name', 'Unknown'))} (<code>{u['user_id']}</code>)" for u in users]
            await event.reply("<b>👑 Allowed List</b>\n\n" + "\n".join(lines), parse_mode="html")

        @self.bot_client.on(events.NewMessage(pattern=r"^/removeallow(?:@\w+)?\s+(\d+)$"))
        async def remove_allow(event):
            if event.sender_id != Config.OWNER_ID: return
            target_id = int(event.pattern_match.group(1))
            result = await self.db.allowed_users.delete_one({"user_id": target_id})
            await event.reply("✅ Removed" if result.deleted_count else "⚠️ Not found")

        # STATUS
        @self.bot_client.on(events.NewMessage(pattern=r"^/status$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID: return
            taunt_count = sum(len(s) for s in self.delete_and_taunt_targets.values())
            learned_count = await self.db.learned.count_documents({})
            msg = (f"📊 **Status**\n🤖 Ninja Pool1: {len(self.ninja_clients)}\n🤖 Ninja Pool2: {len(self.ninja_clients2)}\n🤖 Ninja Pool3: {len(self.ninja_clients3)}\n🗂️ Learned: {learned_count}\n💾 Save: {'ON' if self.save_status else 'OFF'}\n🔄 Cleanup: {'ON' if self.auto_cleanup else 'OFF'}\n👹 Taunts: {taunt_count}")
            await event.reply(msg, parse_mode='markdown')

        # AUTO CLEANUP
        @self.bot_client.on(events.NewMessage(pattern=r"^/del$"))
        async def del_command(event):
            if event.sender_id != Config.OWNER_ID: return
            self.auto_cleanup = not self.auto_cleanup
            status = "ON" if self.auto_cleanup else "OFF"
            await event.reply(f"🔄 Auto‑Cleanup is now **{status}**.", parse_mode='markdown')

        # SPAM FILTERS
        @self.bot_client.on(events.NewMessage)
        async def sticker_spam_handler(event):
            if event.sticker:
                if event.sender_id in self.ninja_ids or event.sender_id == self.bot_id: return
                if await self.check_admin(event.chat_id, event.sender_id): return
                try: await self.bot_client.delete_messages(event.chat_id, [event.id])
                except: pass
        @self.bot_client.on(events.NewMessage)
        async def short_text_spam_handler(event):
            if event.text and len(event.text) <= 3 and not event.is_private:
                if event.sender_id in self.ninja_ids or event.sender_id == self.bot_id: return
                if await self.check_admin(event.chat_id, event.sender_id): return
                try: await self.bot_client.delete_messages(event.chat_id, [event.id])
                except: pass
        @self.bot_client.on(events.NewMessage(incoming=True))
        async def language_filter_handler(event):
            if event.is_private or not event.text: return
            all_ids = self.ninja_ids | self.ninja_ids2 | self.ninja_ids3
            if event.sender_id == Config.OWNER_ID or event.sender_id == self.bot_id or event.sender_id in all_ids: return
            chat_id = event.chat_id; sender_id = event.sender_id
            if chat_id == Config.LEARNING_GROUP and not await self.check_admin(chat_id, sender_id):
                if re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff\u0e00-\u0e7f\u0600-\u06ff\uac00-\ud7af]').search(event.text):
                    try:
                        await event.delete()
                        sender = await event.get_sender()
                        mention = self.format_mention(sender_id, sender.first_name if sender else "User")
                        await event.respond(f"⚠️ **LANGUAGE SECURITY**\n{mention}, only **Burmese, English** and **Numbers** ပဲ ပို့ခွင့်ရှိတယ်.", parse_mode='html')
                    except: pass

    # --------------------------------------------------------------
    #  STARTUP
    # --------------------------------------------------------------
    async def start(self) -> None:
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        me = await self.bot_client.get_me()
        self.bot_id = me.id
        logger.info(f"🤖 Main bot started as @{me.username}")
        await self.load_ninja_pools()
        async for doc in self.db.taunt_targets.find():
            if doc.get("target_ids"): self.delete_and_taunt_targets[doc["chat_id"]] = set(doc["target_ids"])
        threading.Thread(target=run_flask, daemon=True).start()
        await self.bot_client.run_until_disconnected()

    async def stop(self) -> None:
        if self.bot_client.is_connected(): await self.bot_client.disconnect()
        for client in self.ninja_clients + self.ninja_clients2 + self.ninja_clients3:
            try: await client.disconnect()
            except: pass
        await self.db.close()

async def main():
    db = DatabaseManager(Config.MONGO_URI)
    await db.connect()
    bot = SovereignBot(db)
    try:
        await bot.start()
    finally:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
