#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sovereign System – FULL VERSION (Ninja Pools 1, 2, 3 + Special Pool + Stealth Attack)
- Special Attack Trigger: "သေမယ်နော်" (Reply to target) – WORKS ON MAIN BOT & SPECIAL POOLS
- Special Stop: "ရပ်" or "/stop" (Works in any chat! No need for Saved Messages)
- Fixed HTML Mentions (Blue Link) in Special Attacks
- Owner gets DM notifications for every trigger/error
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
    SPAM_DELAY = 0.6
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
                await self.db.learned_new.create_index("text", unique=True, sparse=True)
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

        self.ninja_clients: List[TelegramClient] = []
        self.ninja_names: List[str] = []
        self.ninja_ids: Set[int] = set()
        self.ninja_bully_tasks: Dict[int, bool] = {}
        self.ninja_shoot_tasks: Dict[int, bool] = {}
        self.ninja_tracking_targets: Dict[int, int] = {}
        self.ninja_spam_tasks: Dict[int, bool] = {}

        self.ninja_clients2: List[TelegramClient] = []
        self.ninja_names2: List[str] = []
        self.ninja_ids2: Set[int] = set()
        self.ninja_bully_tasks2: Dict[int, bool] = {}
        self.ninja_shoot_tasks2: Dict[int, bool] = {}
        self.ninja_tracking_targets2: Dict[int, int] = {}
        self.ninja_spam_tasks2: Dict[int, bool] = {}

        self.ninja_clients3: List[TelegramClient] = []
        self.ninja_names3: List[str] = []
        self.ninja_ids3: Set[int] = set()
        self.ninja_bully_tasks3: Dict[int, bool] = {}
        self.ninja_shoot_tasks3: Dict[int, bool] = {}
        self.ninja_tracking_targets3: Dict[int, int] = {}
        self.ninja_spam_tasks3: Dict[int, bool] = {}

        self.special_clients: List[TelegramClient] = []
        self.special_names: List[str] = []
        self.special_ids: Set[int] = set()
        self.special_attack_active = False
        self.special_attack_task: Optional[asyncio.Task] = None
        self.special_target_chat: Optional[int] = None
        self.special_target_mention: Optional[str] = None
        self.special_spam_texts_list: List[str] = []
        self.special_save_mode = False

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
    #  POOL LOADING
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

    async def load_special_pool(self) -> None:
        for client in self.special_clients:
            try:
                client.remove_event_handler(self.special_event_handler, events.NewMessage)
                await client.disconnect()
            except: pass
        self.special_clients.clear(); self.special_names.clear(); self.special_ids.clear()
        async for doc in self.db.special_pool_col.find():
            session_str = doc.get("session")
            if not session_str: continue
            try:
                client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
                await client.start()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    self.special_clients.append(client)
                    self.special_names.append(doc.get("name", f"Special-{len(self.special_clients)}"))
                    self.special_ids.add(me.id)
                    logger.info(f"✅ Special Pool – {doc.get('name')} loaded")
                    client.add_event_handler(self.special_event_handler, events.NewMessage)
                else:
                    await client.disconnect()
            except Exception as e:
                logger.error(f"❌ Special Pool – failed: {e}")

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

    async def _get_special_client(self) -> Optional[TelegramClient]:
        if not self.special_clients: return None
        for client in self.special_clients:
            try: 
                await client.get_me()
                return client
            except: continue
        return None

    # --------------------------------------------------------------
    #  SPECIAL EVENT HANDLER (FIXED MENTION)
    # --------------------------------------------------------------
    async def special_event_handler(self, event):
        if event.sender_id in self.special_ids: return
        text = event.raw_text or ""
        owner_id = Config.OWNER_ID

        async def notify_owner(msg):
            try:
                await self.bot_client.send_message(owner_id, f"⚠️ <b>Special Attack Alert:</b>\n\n{msg}", parse_mode='html')
            except: pass

        if event.chat_id == event.sender_id and text == "ရပ်":
            if self.special_attack_active:
                self.special_attack_active = False
                if self.special_attack_task and not self.special_attack_task.done():
                    self.special_attack_task.cancel()
                await notify_owner("🛑 Special attack stopped via Saved Messages.")
            return

        if text == "သေမယ်နော်":
            await notify_owner(f"📍 Trigger received in chat {event.chat_id}\n<b>Is Reply?</b> {event.is_reply}")
            if not event.is_reply:
                await notify_owner("❌ Command must be a Reply!")
                return
            if not self.special_clients:
                await notify_owner("❌ No Special Pool accounts loaded!")
                return
            if self.special_attack_active:
                await notify_owner("⚠️ Special attack already running!")
                return

            reply_msg = await event.get_reply_message()
            target = await reply_msg.get_sender()
            if target.id == Config.OWNER_ID: return

            spam_texts = await self.db.special_spam_texts.find().to_list(length=None)
            if not spam_texts:
                await notify_owner("❌ No Special Spam Texts! Use /savespecial on")
                return

            self.special_attack_active = True
            self.special_target_chat = event.chat_id
            # FIXED MENTION HERE
            self.special_target_mention = f"<a href='tg://user?id={target.id}'>{escape_html(target.first_name or 'Target')}</a>"
            self.special_spam_texts_list = [doc["text"] for doc in spam_texts]

            client = random.choice(self.special_clients)
            if client:
                me = await client.get_me()
                await client.send_message(me.id, f"🔥 Special attack started on {self.special_target_mention} in chat {event.chat_id}", parse_mode='html')
            
            await notify_owner(f"✅ Special attack STARTED!\nTarget: {self.special_target_mention}\nSpam texts: {len(self.special_spam_texts_list)}")

            async def attack_loop():
                while self.special_attack_active:
                    client = random.choice(self.special_clients) if self.special_clients else None
                    if not client: await asyncio.sleep(1); continue
                    text_to_send = random.choice(self.special_spam_texts_list)
                    try:
                        # FIXED: Explicit parse_mode='html' for proper mention
                        await client.send_message(self.special_target_chat, f"{self.special_target_mention} {text_to_send}", parse_mode='html')
                        await asyncio.sleep(Config.SPAM_DELAY)
                    except FloodWaitError as e:
                        await asyncio.sleep(e.seconds + 1)
                    except Exception as e:
                        logger.error(f"Special attack error: {e}")
                        await notify_owner(f"❌ Attack Error: {e}")
                        await asyncio.sleep(2)
            self.special_attack_task = asyncio.create_task(attack_loop())

    # --------------------------------------------------------------
    #  HELPERS
    # --------------------------------------------------------------
    def format_mention(self, user_id: int, name: str) -> str:
        return f"<a href='tg://user?id={user_id}'>{escape_html(name)}</a>"

    async def notify_owner_to_dm(self, msg: str):
        try:
            await self.bot_client.send_message(Config.OWNER_ID, f"⚠️ <b>System Alert:</b>\n\n{msg}", parse_mode='html')
        except: pass

    async def get_shadow_taunts(self) -> List[str]:
        doc = await self.db.system_col.find_one({"key": "shadow_taunts"})
        return doc["value"] if doc and doc.get("value") else ["မင်းရဲ့စကားတွေက ဘယ်သူမှ မှတ်မိမှာမဟုတ်ဘူး"]

    async def check_admin(self, chat_id: int, user_id: int) -> bool:
        if user_id == Config.OWNER_ID: return True
        if chat_id in self.admin_cache:
            return user_id in self.admin_cache[chat_id]["ids"]
        await self._update_admin_cache(chat_id)
        return user_id in self.admin_cache.get(chat_id, {"ids": set()})["ids"]

    async def _update_admin_cache(self, chat_id: int):
        try:
            admins = await self.bot_client(GetParticipantsRequest(channel=chat_id, filter=ChannelParticipantsAdmins(), offset=0, limit=200, hash=0))
            self.admin_cache[chat_id] = {"ids": {p.user_id for p in admins.participants}, "expiry": time.time() + 300}
        except: self.admin_cache[chat_id] = {"ids": set(), "expiry": time.time() + 300}

    async def is_allowed(self, user_id: int) -> bool:
        if user_id == Config.OWNER_ID: return True
        doc = await self.db.allowed_users.find_one({"user_id": user_id})
        return doc is not None

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

    # --------------------------------------------------------------
    #  COMMAND HANDLERS
    # --------------------------------------------------------------
    def _register_handlers(self):

        # STOP COMMAND (User's Exact Code + Special Stop)
        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop)$"))
        async def stop_attack(event):
            if not await self.is_allowed(event.sender_id): return
            chat_id = event.chat_id
            stopped = False
            
            # ---- SPECIAL ATTACK STOP ----
            if self.special_attack_active:
                self.special_attack_active = False
                if self.special_attack_task and not self.special_attack_task.done():
                    self.special_attack_task.cancel()
                stopped = True

            if chat_id in self.ninja_bully_tasks: self.ninja_bully_tasks[chat_id] = False; stopped = True
            if chat_id in self.ninja_shoot_tasks: self.ninja_shoot_tasks[chat_id] = False; stopped = True
            if chat_id in self.ninja_tracking_targets: del self.ninja_tracking_targets[chat_id]; stopped = True
            if chat_id in self.ninja_spam_tasks: self.ninja_spam_tasks[chat_id] = False; stopped = True
            if chat_id in self.ninja_bully_tasks2: self.ninja_bully_tasks2[chat_id] = False; stopped = True
            if chat_id in self.ninja_shoot_tasks2: self.ninja_shoot_tasks2[chat_id] = False; stopped = True
            if chat_id in self.ninja_tracking_targets2: del self.ninja_tracking_targets2[chat_id]; stopped = True
            if chat_id in self.ninja_spam_tasks2: self.ninja_spam_tasks2[chat_id] = False; stopped = True
            if chat_id in self.ninja_bully_tasks3: self.ninja_bully_tasks3[chat_id] = False; stopped = True
            if chat_id in self.ninja_shoot_tasks3: self.ninja_shoot_tasks3[chat_id] = False; stopped = True
            if chat_id in self.ninja_tracking_targets3: del self.ninja_tracking_targets3[chat_id]; stopped = True
            if chat_id in self.ninja_spam_tasks3: self.ninja_spam_tasks3[chat_id] = False; stopped = True
            self.reset_phrase_cycle(chat_id)
            if stopped:
                await event.reply("🛑 All active attacks (bully/shoot/track/spam/special) stopped in this chat.")
            else:
                await event.reply("ℹ️ No active attacks to stop.")

        # SPECIAL SAVE
        @self.bot_client.on(events.NewMessage(pattern=r"^/savespecial (on|off)$"))
        async def save_special_cmd(event):
            if event.sender_id != Config.OWNER_ID: return
            self.special_save_mode = (event.pattern_match.group(1) == "on")
            await event.reply(f"✅ Special Save Mode: {'ON' if self.special_save_mode else 'OFF'}")

        # UNIVERSAL WATCHER (MAIN BOT) – TRIGGERS SPECIAL ATTACK + MENTION FIX
        @self.bot_client.on(events.NewMessage())
        async def watcher(event):
            if event.is_private: return
            all_ids = self.ninja_ids | self.ninja_ids2 | self.ninja_ids3
            if event.sender_id == self.bot_id or event.sender_id in all_ids: return
            chat_id = event.chat_id; sender_id = event.sender_id

            # Special Save Mode
            if self.special_save_mode and sender_id == Config.OWNER_ID:
                if event.text and not event.text.startswith('/'):
                    try:
                        await self.db.special_spam_texts.insert_one({"text": event.text.strip()})
                        await event.reply("✅ Special spam saved.")
                    except: await event.reply("⚠️ Duplicate text.")
                    return

            # SPECIAL TRIGGER ON MAIN BOT (FIXED MENTION!)
            if event.text == "သေမယ်နော်" and event.is_reply:
                if not self.special_clients:
                    await self.notify_owner_to_dm("❌ No Special Pool accounts loaded! Use /addspecial.")
                    return
                spam_texts = await self.db.special_spam_texts.find().to_list(length=None)
                if not spam_texts:
                    await self.notify_owner_to_dm("❌ No Special Spam Texts! Use /savespecial on.")
                    return
                if self.special_attack_active:
                    await self.notify_owner_to_dm("⚠️ Special Attack already active!")
                    return

                reply_msg = await event.get_reply_message()
                target = await reply_msg.get_sender()
                if target.id == Config.OWNER_ID: return

                self.special_attack_active = True
                self.special_target_chat = chat_id
                self.special_target_mention = f"<a href='tg://user?id={target.id}'>{escape_html(target.first_name or 'Target')}</a>"
                self.special_spam_texts_list = [doc["text"] for doc in spam_texts]

                async def attack_loop():
                    while self.special_attack_active:
                        client = random.choice(self.special_clients) if self.special_clients else None
                        if not client: await asyncio.sleep(1); continue
                        text_to_send = random.choice(self.special_spam_texts_list)
                        try:
                            # FIXED: Explicit parse_mode='html' for proper mention
                            await client.send_message(self.special_target_chat, f"{self.special_target_mention} {text_to_send}", parse_mode='html')
                            await asyncio.sleep(Config.SPAM_DELAY)
                        except Exception as e:
                            logger.error(f"Special attack error: {e}")
                            await asyncio.sleep(2)
                
                self.special_attack_task = asyncio.create_task(attack_loop())
                await self.notify_owner_to_dm(f"✅ Special Attack Started on {self.special_target_mention} via Main Bot!")
                return

            # Bully Commands (Pool 1, 2, 3)
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

            # Shoot Commands (Pool 1, 2, 3)
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

            # Spam Commands
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

            # Delete & Taunt
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

            # Add Ninja Commands
            if event.text.startswith("/addninja"):
                if event.sender_id != Config.OWNER_ID: return
                parts = event.text.split(maxsplit=2)
                if len(parts) < 3: return
                name, session_str = parts[1], parts[2]
                col = self.db.ninja_col
                if "/addninja2" in event.text: col = self.db.ninja_col2
                elif "/addninja3" in event.text: col = self.db.ninja_col3
                await col.insert_one({"name": name, "session": session_str})
                await self.load_ninja_pools()
                await event.reply(f"✅ Added {name}")

            # Add Special Commands
            if event.text.startswith("/addspecial"):
                if event.sender_id != Config.OWNER_ID: return
                parts = event.text.split(maxsplit=2)
                if len(parts) < 3: return
                name, session_str = parts[1], parts[2]
                await self.db.special_pool_col.insert_one({"name": name, "session": session_str})
                await self.load_special_pool()
                await event.reply(f"✅ Added {name}")

            # List Commands
            if event.text == "/listninja":
                if event.sender_id != Config.OWNER_ID: return
                lines = [f"👥 **Ninja Pool 1 ({len(self.ninja_clients)})**"]
                for i, (client, name) in enumerate(zip(self.ninja_clients, self.ninja_names)):
                    lines.append(f"  {i+1}. **{name}**")
                await event.reply("\n".join(lines), parse_mode='markdown')
            if event.text == "/listspecial":
                if event.sender_id != Config.OWNER_ID: return
                lines = [f"👥 **Special Pool ({len(self.special_clients)})**"]
                for i, (client, name) in enumerate(zip(self.special_clients, self.special_names)):
                    lines.append(f"  {i+1}. **{name}**")
                await event.reply("\n".join(lines), parse_mode='markdown')

            # /status
            if event.text == "/status":
                if event.sender_id != Config.OWNER_ID: return
                await event.reply(f"📊 **Status**\n🤖 Ninja Pool1: {len(self.ninja_clients)}\n🤖 Ninja Pool2: {len(self.ninja_clients2)}\n🤖 Ninja Pool3: {len(self.ninja_clients3)}\n🤖 Special: {len(self.special_clients)}\n💾 Save: {'ON' if self.save_status else 'OFF'}", parse_mode='markdown')

        # Spam Filters (Basic)
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

    def reset_phrase_cycle(self, chat_id: int):
        self.phrase_lists.pop(chat_id, None)
        self.phrase_indices.pop(chat_id, None)

    # --------------------------------------------------------------
    #  STARTUP
    # --------------------------------------------------------------
    async def start(self) -> None:
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        me = await self.bot_client.get_me()
        self.bot_id = me.id
        logger.info(f"🤖 Main bot started as @{me.username}")

        await self.load_ninja_pools()
        await self.load_special_pool()
        async for doc in self.db.taunt_targets.find():
            if doc.get("target_ids"):
                self.delete_and_taunt_targets[doc["chat_id"]] = set(doc["target_ids"])

        threading.Thread(target=run_flask, daemon=True).start()
        await self.bot_client.run_until_disconnected()

    async def stop(self) -> None:
        if self.bot_client.is_connected(): await self.bot_client.disconnect()
        for client in self.ninja_clients + self.ninja_clients2 + self.ninja_clients3 + self.special_clients:
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
