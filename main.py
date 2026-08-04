#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sovereign System – Merged Bot (attack.py + power_ranger.py + channel admin features)
- Removed KTR (ktr/ktrr) auto-reply
- Added spam filters, bio/link filter, language filter
- Added moderation commands: mute, unmute, ban, unban, kick
- Added media forwarder (group → channel) with subscribe button
- Added subscriber system (/start channel_alert) and /notifyall
- All existing attack, save, taunt, userbot pool features remain
"""

import asyncio
import logging
import os
import random
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from html import escape as escape_html
from typing import Dict, List, Optional, Set, Union

import pytz
from flask import Flask
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, OperationFailure, DuplicateKeyError
from telethon import TelegramClient, events, errors, Button
from telethon.errors import FloodWaitError, RPCError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import (
    ChannelParticipantsAdmins,
    UserStatusEmpty, UserStatusOffline, UserStatusRecently,
    UserStatusLastWeek, UserStatusLastMonth
)
from telethon.tl.functions.messages import ImportChatInviteRequest

# ------------------------------------------------------------------
#  CONFIGURATION
# ------------------------------------------------------------------
class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "6015356597"))
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true")
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "8111794244:AAHss6CTa8T2b4JP9_zxJrCVLWtGY0i_7yE")
    LEARNING_GROUP = int(os.getenv("LEARNING_GROUP", "-1003806830045"))
    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yangon"))
    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    BULLY_DELAY = 0.6
    SHOOT_DELAY = 0.6
    MAX_RETRIES = 3

    # Channel admin settings
    SOURCE_GROUP_ID = int(os.getenv("SOURCE_GROUP_ID", "-1003877873337"))
    TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "-1003754813090"))
    CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/freevipallinone")

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
#  DATABASE MANAGER (extended)
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
                # Create indexes
                try:
                    await self.db.learned.create_index("text", unique=True, sparse=True)
                except:
                    pass
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
    def custom_filters(self):
        return self.db["custom_filters"]

    @property
    def allowed_users(self):
        return self.db["allowed_users"]

    @property
    def system_col(self):
        return self.db["system_col"]

    @property
    def learned(self):
        return self.db["learned"]

    # Power Ranger collections
    @property
    def marcuz_col(self):
        return self.db["marcuz_col"]

    @property
    def powerranger_col(self):
        return self.db["powerranger_col"]

    @property
    def target_bots_col(self):
        return self.db["target_bots_col"]

    @property
    def tomboy_col(self):
        return self.db["tomboy_col"]

    @property
    def taunt_targets(self):
        return self.db["taunt_targets"]

    # Channel admin collections
    @property
    def muted_registry(self):
        return self.db["muted_registry"]

    @property
    def channel_subscribers(self):
        return self.db["channel_subscribers"]

# ------------------------------------------------------------------
#  MAIN BOT CLASS
# ------------------------------------------------------------------
class SovereignBot:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.bot_client = TelegramClient(
            "bot_main_session",
            Config.API_ID,
            Config.API_HASH,
            flood_sleep_threshold=60,
        )

        # Action clients: main userbot (if any) + all power rangers
        self.action_clients: List[TelegramClient] = []
        self.action_names: List[str] = []
        self.action_ids: Set[int] = set()
        self.pool_lock = asyncio.Lock()

        # State for attacks
        self.bully_tasks: Dict[int, bool] = {}
        self.shoot_tasks: Dict[int, bool] = {}
        self.tracking_targets: Dict[int, int] = {}
        self.dark_passenger_targets: Dict[int, int] = {}

        # Taunt targets (multiple per chat)
        self.delete_and_taunt_targets: Dict[int, Set[int]] = {}

        self.learning_status: bool = False
        self.save_status: bool = False

        # For cycling learned phrases without repetition per chat
        self.phrase_lists: Dict[int, List[str]] = {}
        self.phrase_indices: Dict[int, int] = {}

        # For copy mode (from power_ranger)
        self.is_copy_active: bool = False
        self.matrix_group_id: Optional[int] = None
        self.target_group_id: Optional[int] = None
        self.bad_users: List[tuple] = []
        self.check_in_progress: bool = False

        # Spam filter data
        self.sticker_spam_data = {}
        self.char_spam_data = {}
        self.admin_warned_sticker = set()
        self.admin_warned_char = set()

        # Admin cache
        self.admin_cache = {}

        self._register_handlers()

    # --------------------------------------------------------------
    #  USERBOT POOL MANAGEMENT (from power_ranger)
    # --------------------------------------------------------------
    async def load_userbots(self) -> None:
        """Load main userbot from marcuz_col and Power Rangers from powerranger_col."""
        await self.close_action_clients()

        # 1) Main userbot (string_session)
        doc = await self.db.marcuz_col.find_one({"key": "string_session"})
        if doc and doc.get("value"):
            session_str = doc["value"]
            try:
                client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
                await client.start()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    self.action_clients.append(client)
                    self.action_names.append("MainUserbot")
                    self.action_ids.add(me.id)
                    logger.info(f"✅ Main userbot loaded: @{me.username}")
                else:
                    await client.disconnect()
                    logger.warning("Main userbot session not authorized.")
            except Exception as e:
                logger.error(f"❌ Failed to load main userbot: {e}")

        # 2) Power Rangers
        async for pr_doc in self.db.powerranger_col.find():
            session_str = pr_doc.get("session")
            if not session_str:
                continue
            try:
                client = TelegramClient(StringSession(session_str), Config.API_ID, Config.API_HASH)
                await client.start()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    self.action_clients.append(client)
                    name = pr_doc.get("name", f"PR-{len(self.action_clients)}")
                    self.action_names.append(name)
                    self.action_ids.add(me.id)
                    logger.info(f"✅ Power Ranger '{name}' loaded: @{me.username}")
                else:
                    await client.disconnect()
                    logger.warning(f"Power Ranger session {session_str[:10]}... not authorized.")
            except Exception as e:
                logger.error(f"❌ Failed to load Power Ranger: {e}")

        logger.info(f"🚀 Action pool ready: {len(self.action_clients)} clients.")

    async def close_action_clients(self) -> None:
        for client in self.action_clients:
            try:
                if client.is_connected():
                    await client.disconnect()
            except:
                pass
        self.action_clients.clear()
        self.action_names.clear()
        self.action_ids.clear()

    async def get_action_client(self) -> Optional[TelegramClient]:
        """Return a random working action client, or None if none."""
        if not self.action_clients:
            return None

        # Try random clients until we find one that works
        candidates = self.action_clients.copy()
        random.shuffle(candidates)
        for client in candidates:
            try:
                await client.get_me()
                return client
            except Exception:
                # Try to reconnect
                try:
                    await client.connect()
                    await client.get_me()
                    return client
                except Exception:
                    continue
        logger.warning("All action clients are dead.")
        return None

    # --------------------------------------------------------------
    #  TAUNT TARGETS DB PERSISTENCE
    # --------------------------------------------------------------
    async def load_taunt_targets(self) -> None:
        """Load taunt targets from DB into memory on startup."""
        async for doc in self.db.taunt_targets.find():
            chat_id = doc["chat_id"]
            target_ids = doc.get("target_ids", [])
            if target_ids:
                self.delete_and_taunt_targets[chat_id] = set(target_ids)
                logger.info(f"📌 Loaded {len(target_ids)} taunt targets for chat {chat_id}")

    async def _add_taunt_target(self, chat_id: int, target_id: int) -> None:
        if chat_id not in self.delete_and_taunt_targets:
            self.delete_and_taunt_targets[chat_id] = set()
        self.delete_and_taunt_targets[chat_id].add(target_id)
        await self.db.taunt_targets.update_one(
            {"chat_id": chat_id},
            {"$addToSet": {"target_ids": target_id}},
            upsert=True
        )
        logger.info(f"➕ Added target {target_id} to taunt list in chat {chat_id}")

    async def _remove_taunt_target(self, chat_id: int, target_id: int) -> None:
        if chat_id in self.delete_and_taunt_targets:
            self.delete_and_taunt_targets[chat_id].discard(target_id)
            if not self.delete_and_taunt_targets[chat_id]:
                del self.delete_and_taunt_targets[chat_id]
                await self.db.taunt_targets.delete_one({"chat_id": chat_id})
            else:
                await self.db.taunt_targets.update_one(
                    {"chat_id": chat_id},
                    {"$pull": {"target_ids": target_id}}
                )
            logger.info(f"➖ Removed target {target_id} from taunt list in chat {chat_id}")

    async def _clear_taunt_targets(self, chat_id: int) -> None:
        if chat_id in self.delete_and_taunt_targets:
            del self.delete_and_taunt_targets[chat_id]
            await self.db.taunt_targets.delete_one({"chat_id": chat_id})
            logger.info(f"🧹 Cleared all taunt targets in chat {chat_id}")

    # --------------------------------------------------------------
    #  ADMIN CACHE HELPERS (from KTR bot)
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
            admins = await self.bot_client(GetParticipantsRequest(
                channel=chat_id, filter=ChannelParticipantsAdmins(),
                offset=0, limit=200, hash=0
            ))
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

    # --------------------------------------------------------------
    #  HELPER METHODS
    # --------------------------------------------------------------
    def format_mention(self, user_id: int, name: str) -> str:
        return f"<a href='tg://user?id={user_id}'>{escape_html(name)}</a>"

    def strip_html(self, text: str) -> str:
        if not text:
            return ""
        return re.sub(r'<[^>]+>', '', text)

    async def is_allowed(self, user_id: int) -> bool:
        if user_id == Config.OWNER_ID:
            return True
        doc = await self.db.allowed_users.find_one({"user_id": user_id})
        return doc is not None

    def strip_mentions(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'<a[^>]*>.*?</a>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'@\w+', '', text)
        return ' '.join(text.split())

    def bq(self, text: str) -> str:
        return f"<blockquote><b>{text}</b></blockquote>"

    # --------------------------------------------------------------
    #  PHRASE MANAGEMENT – from learned collection
    # --------------------------------------------------------------
    async def fetch_learned_phrases(self) -> List[str]:
        docs = await self.db.learned.find().to_list(length=10000)
        if docs:
            return [doc.get("text") for doc in docs if doc.get("text")]
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
    #  CHANNEL ADMIN FEATURES (Spam Filters, Moderation, Forwarder)
    # --------------------------------------------------------------

    # --- Sticker Spam Filter ---
    async def sticker_spam_filter(self, event):
        if not event.sticker or event.is_private:
            return
        if event.sender_id in self.action_ids or event.sender_id == self.bot_client.me.id:
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
                        action_msg = self.bq(f"⚠️ <b>Admin {mention}</b>, please refrain from spamming stickers. (⚠️ This is your only warning!)")
                        await event.respond(action_msg, parse_mode='html')
                        self.admin_warned_sticker.add(admin_key)
                else:
                    await self.bot_client.edit_permissions(chat_id, sender_id, send_stickers=False)
                    action_msg = self.bq(f"{mention} has been restricted from sending stickers due to spam.")
                    await event.respond(action_msg, parse_mode='html')
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
                        action_msg = self.bq(f"⚠️ <b>Admin {mention}</b>, please don't spam stickers. (Only warning!)")
                        await event.respond(action_msg, parse_mode='html')
                        self.admin_warned_sticker.add(admin_key)
                except Exception as e:
                    logger.error(f"Sticker spam early warning error: {e}")

    # --- Short Text Spam Filter ---
    async def short_text_spam_filter(self, event):
        if event.is_private or not event.text:
            return
        if event.sender_id in self.action_ids or event.sender_id == self.bot_client.me.id:
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
                        action_msg = self.bq(f"⚠️ <b>Admin {mention}</b>, please stop spamming short messages. (⚠️ This is your only warning!)")
                        await event.respond(action_msg, parse_mode='html')
                        self.admin_warned_char.add(admin_key)
                else:
                    await self.bot_client.edit_permissions(chat_id, sender_id, until_date=datetime.now() + timedelta(minutes=5), send_messages=False)
                    action_msg = self.bq(f"🚫 {mention} has been muted for 5 minutes due to spam.")
                    await event.respond(action_msg, parse_mode='html')
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
                        warn_msg = self.bq(f"⚠️ <b>Admin {mention}</b>, stop spam or you'll be warned! (Only warning!)")
                        await event.respond(warn_msg, parse_mode='html')
                        self.admin_warned_char.add(admin_key)
                else:
                    warn_msg = self.bq(f"⚠️ {mention}, stop spam or you’ll be muted for 5 minutes!")
                    await event.respond(warn_msg, parse_mode='html')
            except Exception as e:
                logger.error(f"Short text spam warning error: {e}")

    # --- Bio/Link Filter ---
    async def bio_link_filter(self, event):
        if event.is_private:
            return
        if not event.text or event.sender_id == Config.OWNER_ID or event.sender_id in self.action_ids or event.sender_id == self.bot_client.me.id:
            return
        text, chat_id, sender_id = event.text.strip(), event.chat_id, event.sender_id
        sender = await event.get_sender()

        # Bio filter
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

        # Link filter
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

    # --- Language Filter ---
    FORBIDDEN_SCRIPTS = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff\u0e00-\u0e7f\u0600-\u06ff\uac00-\ud7af]')

    async def global_traffic_processing_matrix(self, event):
        if event.is_private or not event.text:
            return
        if event.sender_id == Config.OWNER_ID or event.sender_id in self.action_ids or event.sender_id == self.bot_client.me.id:
            return
        chat_id = event.chat_id
        sender_id = event.sender_id
        # Only apply in learning group (SPECIFIC_GROUP from old code, we use LEARNING_GROUP)
        if chat_id == Config.LEARNING_GROUP and not await self.check_admin(chat_id, sender_id):
            if self.FORBIDDEN_SCRIPTS.search(event.text):
                try:
                    await event.delete()
                    sender = await event.get_sender()
                    mention = self.format_mention(sender_id, sender.first_name if sender else "User")
                    await event.respond(self.bq(f"⚠️ <b>LANGUAGE SECURITY</b>\n{mention}, only <b>Burmese, English</b> and <b>Numbers</b> ပဲ ပို့ခွင့်ရှိတယ်. တခြားသော ဘာသာစကားများ ရေးခွင့်မပြုဘူး."), parse_mode='html')
                except Exception:
                    pass

    # --- Moderation Commands ---
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

    # --- Media Forwarder (Group → Channel) with Subscribe Button ---
    async def forward_media_to_channel(self, event):
        # Only owner and from SOURCE_GROUP_ID
        if event.sender_id != Config.OWNER_ID:
            return
        if event.chat_id != Config.SOURCE_GROUP_ID:
            return
        if not (event.photo or event.video):
            return

        caption = event.raw_text or ""
        bot_username = (await self.bot_client.get_me()).username or "YourBotUsername"
        buttons = [
            [Button.url("အသစ်တင်တိုင်းသိနိုင်ရန်နှိပ်ပါ", f"https://t.me/{bot_username}?start=channel_alert")]
        ]

        try:
            await self.bot_client.send_message(
                Config.TARGET_CHANNEL_ID,
                caption,
                file=event.media,
                parse_mode='html',
                buttons=buttons
            )
            logger.info(f"✅ Media forwarded to channel {Config.TARGET_CHANNEL_ID} with subscribe button.")
        except Exception as e:
            logger.error(f"Forward error: {e}")

    # --- /start with channel_alert ---
    async def start_handler(self, event):
        payload = event.pattern_match.group(1) if hasattr(event.pattern_match, 'group') and event.pattern_match.group(1) else ""
        user_id = event.sender_id

        if payload == "channel_alert":
            await self.db.channel_subscribers.update_one(
                {"user_id": user_id},
                {"$set": {"user_id": user_id, "subscribed_at": time.time()}},
                upsert=True
            )
            await event.reply(
                "✅ သင်သည် Channel မှာ အသစ်တင်တိုင်း အသိပေးချက် ရရှိမည် ဖြစ်ပါသည်။\n"
                "📢 နောက်အသစ်များကို စောင့်မျှော်နေပါ။",
                parse_mode='html'
            )
        else:
            await event.reply(
                "👋 မင်္ဂလာပါ။\n"
                "Channel အသစ်များအတွက် အသိပေးချက် ရယူလိုပါက အောက်ပါ Link ကိုနှိပ်ပါ။\n"
                f"https://t.me/{ (await self.bot_client.get_me()).username or 'YourBot'}?start=channel_alert",
                parse_mode='html'
            )

    # --- /notifyall ---
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
                await self.bot_client.send_message(
                    user_id,
                    f"📢 <b>Channel Update</b>\n\n{message}",
                    parse_mode='html',
                    buttons=buttons
                )
                success += 1
                await asyncio.sleep(0.1)
            except Exception:
                pass

        await event.reply(f"✅ Notification sent to {success} subscribers.", parse_mode='html')

    # --------------------------------------------------------------
    #  COMMAND HANDLERS
    # --------------------------------------------------------------
    def _register_handlers(self):

        # ==================== SAVE SYSTEM ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^/save on$"))
        async def save_on(event):
            if event.chat_id != Config.LEARNING_GROUP or not await self.is_allowed(event.sender_id):
                return
            self.save_status = True
            try:
                await event.delete()
            except:
                pass
            await self.bot_client.send_message(
                Config.LEARNING_GROUP,
                f"✅ Save mode ON by {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')}",
                parse_mode='html'
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/save off$"))
        async def save_off(event):
            if event.chat_id != Config.LEARNING_GROUP or not await self.is_allowed(event.sender_id):
                return
            self.save_status = False
            try:
                await event.delete()
            except:
                pass
            await self.bot_client.send_message(
                Config.LEARNING_GROUP,
                f"⏸️ Save mode OFF by {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')}",
                parse_mode='html'
            )

        # ==================== ATTACK COMMANDS ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^/b(?:@\w+)?$"))
        async def bot_bully(event):
            if not await self.is_allowed(event.sender_id):
                return
            await self.bot_client.send_message(
                Config.LEARNING_GROUP,
                f"🔫 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used /b",
                parse_mode='html'
            )
            try:
                await event.delete()
            except:
                pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply:
                return
            target = await reply.get_sender()
            if target.id == Config.OWNER_ID:
                return
            chat_id = event.chat_id
            self.bully_tasks[chat_id] = True
            mention = self.format_mention(target.id, target.first_name or "Target")
            self.reset_phrase_cycle(chat_id)
            while self.bully_tasks.get(chat_id, False):
                client = await self.get_action_client()
                if not client:
                    await asyncio.sleep(1)
                    continue
                phrase = await self.get_next_phrase(chat_id)
                try:
                    await client.send_message(
                        chat_id,
                        f"{mention} {phrase}",
                        reply_to=reply.id,
                        parse_mode='html'
                    )
                    await asyncio.sleep(Config.BULLY_DELAY)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                except Exception as e:
                    logger.error(f"Bully error: {e}")
                    self.bully_tasks[chat_id] = False
                    break

        @self.bot_client.on(events.NewMessage(pattern=r"^(...|!)$"))
        async def attack_cmds(event):
            if not await self.is_allowed(event.sender_id):
                return
            await self.bot_client.send_message(
                Config.LEARNING_GROUP,
                f"🔫 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used {event.text}",
                parse_mode='html'
            )
            try:
                await event.delete()
            except:
                pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply or reply.sender_id == Config.OWNER_ID:
                return
            chat_id = event.chat_id
            if event.text.startswith("!"):
                self.shoot_tasks[chat_id] = True
                target = await reply.get_sender()
                mention = self.format_mention(target.id, target.first_name or "Target")
                self.reset_phrase_cycle(chat_id)
                while self.shoot_tasks.get(chat_id, False):
                    client = await self.get_action_client()
                    if not client:
                        await asyncio.sleep(1)
                        continue
                    phrase = await self.get_next_phrase(chat_id)
                    try:
                        await client.send_message(
                            chat_id,
                            f"{mention} {phrase}",
                            parse_mode='html'
                        )
                        await asyncio.sleep(Config.SHOOT_DELAY)
                    except FloodWaitError as e:
                        await asyncio.sleep(e.seconds + 1)
                    except Exception as e:
                        logger.error(f"Shoot error: {e}")
                        self.shoot_tasks[chat_id] = False
                        break
            else:
                target = await reply.get_sender()
                mention = self.format_mention(target.id, target.first_name or "Target")
                sender_mention = self.format_mention(event.sender_id, (await event.get_sender()).first_name or "Unknown")
                await self.bot_client.send_message(
                    chat_id,
                    f"🎯 {sender_mention} marked {mention} for termination.",
                    parse_mode='html'
                )

        @self.bot_client.on(events.NewMessage(pattern=r"^K$"))
        async def track(event):
            if not await self.is_allowed(event.sender_id):
                return
            await self.bot_client.send_message(
                Config.LEARNING_GROUP,
                f"🎯 {self.format_mention(event.sender_id, (await event.get_sender()).first_name or 'User')} used K",
                parse_mode='html'
            )
            try:
                await event.delete()
            except:
                pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply or reply.sender_id == Config.OWNER_ID:
                return
            target = await reply.get_sender()
            chat_id = event.chat_id
            self.tracking_targets[chat_id] = target.id
            mention = self.format_mention(target.id, target.first_name or "Target")
            self.reset_phrase_cycle(chat_id)
            await event.reply(
                f"🔭 Tracking {mention}...",
                parse_mode='html'
            )

        # ==================== "ဖာသည်မသား" with DB Persistence ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^ဖာသည်မသား$"))
        async def delete_and_taunt(event):
            if not await self.is_allowed(event.sender_id):
                return
            try:
                await event.delete()
            except:
                pass
            await event.reply("OK")
            reply = await event.get_reply_message()
            if not reply:
                return
            target = await reply.get_sender()
            if target.id == Config.OWNER_ID:
                return
            chat_id = event.chat_id
            try:
                await self.bot_client.delete_messages(chat_id, [reply.id])
            except Exception as e:
                logger.warning(f"Could not delete initial message: {e}")
            await self._add_taunt_target(chat_id, target.id)
            client = await self.get_action_client()
            if client:
                phrase = await self.get_next_phrase(chat_id)
                mention = self.format_mention(target.id, target.first_name or "Target")
                try:
                    await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                except Exception as e:
                    logger.error(f"First taunt send error: {e}")

        # ==================== REMOVE / CLEAR TAUNTS ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^/remove_taunt(?:\s+(\d+))?$"))
        async def remove_taunt(event):
            if not await self.is_allowed(event.sender_id):
                return
            chat_id = event.chat_id
            target_id = event.pattern_match.group(1)
            if target_id:
                target_id = int(target_id)
                await self._remove_taunt_target(chat_id, target_id)
                mention = self.format_mention(target_id, "User")
                await event.reply(
                    f"✅ {mention} (ID: `{target_id}`) ကို ဖာသည်မသားစာရင်းမှ ဖယ်ရှားလိုက်ပါပြီ။",
                    parse_mode='html'
                )
            else:
                if not event.is_reply:
                    await event.reply(
                        "❌ ဖယ်ရှားချင်တဲ့ ပစ်မှတ် ID ကို `/remove_taunt <ID>` နဲ့ထည့်ပါ သို့မဟုတ် သူ့စာကို Reply ထောက်ပါ။"
                    )
                    return
                reply = await event.get_reply_message()
                target = await reply.get_sender()
                await self._remove_taunt_target(chat_id, target.id)
                await event.reply(
                    f"✅ {self.format_mention(target.id, target.first_name or 'Target')} ကို ဖာသည်မသားစာရင်းမှ ဖယ်ရှားလိုက်ပါပြီ။",
                    parse_mode='html'
                )

        @self.bot_client.on(events.NewMessage(pattern=r"^/clear_taunts(?:\s+(-?\d+))?$"))
        async def clear_taunts(event):
            if not await self.is_allowed(event.sender_id):
                return
            target_chat_id = event.pattern_match.group(1)
            if target_chat_id:
                target_chat_id = int(target_chat_id)
                await self._clear_taunt_targets(target_chat_id)
                await event.reply(f"🧹 Chat ID `{target_chat_id}` ထဲက ဖာသည်မသား ပစ်မှတ်အားလုံးကို ရှင်းလိုက်ပါပြီ။")
            else:
                chat_id = event.chat_id
                await self._clear_taunt_targets(chat_id)
                await event.reply("🧹 ဒီ Chat ထဲက ဖာသည်မသား ပစ်မှတ်အားလုံးကို ရှင်းလိုက်ပါပြီ။")

        # ==================== STOP ATTACKS ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop)$"))
        async def stop_attack(event):
            if not await self.is_allowed(event.sender_id):
                return
            chat_id = event.chat_id
            stopped = False
            if chat_id in self.bully_tasks:
                self.bully_tasks[chat_id] = False
                stopped = True
            if chat_id in self.shoot_tasks:
                self.shoot_tasks[chat_id] = False
                stopped = True
            if chat_id in self.tracking_targets:
                del self.tracking_targets[chat_id]
                stopped = True
            if chat_id in self.dark_passenger_targets:
                del self.dark_passenger_targets[chat_id]
                stopped = True
            self.reset_phrase_cycle(chat_id)
            if stopped:
                await event.reply("🛑 Active attacks (bully/shoot/track) stopped in this chat. (Taunt targets remain active until removed with /remove_taunt or /clear_taunts)")
            else:
                await event.reply("ℹ️ No active attacks to stop in this chat.")

        # ==================== POWER RANGER MANAGEMENT ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^/addpr(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_pr(event):
            if event.sender_id != Config.OWNER_ID:
                return
            cmd_args = event.pattern_match.group(1)
            session_str = event.pattern_match.group(2)
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
                await client.start()
                me = await client.get_me()
                self.action_clients.append(client)
                self.action_names.append(name)
                self.action_ids.add(me.id)
                await event.reply(f"✅ Power Ranger '{name}' (ID: {me.id}) added! Total: {len(self.action_clients)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {str(e)}")
                await self.db.powerranger_col.delete_one({"session": session_str})

        @self.bot_client.on(events.NewMessage(pattern=r"^/listpr$"))
        async def list_pr(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.action_clients:
                await event.reply("📭 No Power Rangers active.")
                return
            lines = [f"👥 **Active Power Rangers ({len(self.action_clients)})**"]
            for i, (client, name) in enumerate(zip(self.action_clients, self.action_names)):
                try:
                    me = await client.get_me()
                    lines.append(f"  {i+1}. **{name}** – @{me.username} (ID: {me.id})")
                except:
                    lines.append(f"  {i+1}. **{name}** – (offline)")
            await event.reply("\n".join(lines), parse_mode='markdown')

        @self.bot_client.on(events.NewMessage(pattern=r"^/removepr\s+(.+)$"))
        async def remove_pr(event):
            if event.sender_id != Config.OWNER_ID:
                return
            target = event.pattern_match.group(1).strip()
            pr_list = await self.db.powerranger_col.find().to_list(length=None)
            idx = None
            if target.isdigit():
                idx = int(target) - 1
            else:
                for i, doc in enumerate(pr_list):
                    if doc.get("name") == target:
                        idx = i
                        break
            if idx is None or idx < 0 or idx >= len(pr_list):
                await event.reply(f"❌ Cannot find Power Ranger '{target}'.")
                return
            removed_doc = pr_list[idx]
            await self.db.powerranger_col.delete_one({"_id": removed_doc["_id"]})
            if idx < len(self.action_clients):
                client = self.action_clients.pop(idx)
                self.action_names.pop(idx)
                try:
                    await client.disconnect()
                except:
                    pass
                await event.reply(f"✅ Removed Power Ranger '{removed_doc.get('name')}'.")
            else:
                await event.reply(f"✅ Removed from DB.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/clearpr$"))
        async def clear_pr(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await self.db.powerranger_col.delete_many({})
            await self.close_action_clients()
            await event.reply("🗑️ All Power Rangers cleared.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/restartpr$"))
        async def restart_pr(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await event.reply("🔄 Restarting Power Rangers...")
            await self.close_action_clients()
            await self.load_userbots()
            await event.reply(f"✅ Restarted. Active: {len(self.action_clients)}")

        # ==================== COPY MODE ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^/copyon$"))
        async def copyon(event):
            if event.sender_id != Config.OWNER_ID:
                return
            self.is_copy_active = True
            await event.reply("🎯 Copy Mode: ON – Chief's messages will be copied by all userbots.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/copyoff$"))
        async def copyoff(event):
            if event.sender_id != Config.OWNER_ID:
                return
            self.is_copy_active = False
            await event.reply("🔇 Copy Mode: OFF.")

        # ==================== GROUP MANAGEMENT (go, check, remove) ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^/go$"))
        async def go_group(event):
            if event.sender_id != Config.OWNER_ID:
                return
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
                await event.reply("❌ No action clients available. Add a Power Ranger first.")
                return
            await event.reply(f"⏳ Joining group with {len(all_clients)} clients...")
            success = 0
            for client in all_clients:
                try:
                    await client(ImportChatInviteRequest(hash_part))
                    success += 1
                except errors.rpcerrorlist.UserAlreadyParticipantError:
                    success += 1
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                    try:
                        await client(ImportChatInviteRequest(hash_part))
                        success += 1
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Join error: {e}")
                await asyncio.sleep(0.3)
            group_id = None
            try:
                chat = await all_clients[0].get_entity(invite_link)
                group_id = chat.id
                self.target_group_id = group_id
                await event.reply(f"✅ Joined group `{chat.title}` with {success} clients. Group ID: `{group_id}`")
            except Exception:
                try:
                    async for dialog in all_clients[0].iter_dialogs():
                        if dialog.is_group and hash_part in str(dialog.id):
                            group_id = dialog.id
                            self.target_group_id = group_id
                            await event.reply(f"✅ Joined group `{dialog.name}` with {success} clients. Group ID: `{group_id}`")
                            break
                    else:
                        await event.reply(f"⚠️ Joined but could not determine group ID. Use /setmatrix manually.")
                except Exception as e2:
                    await event.reply(f"⚠️ Joined but failed to get ID: {e2}")

        @self.bot_client.on(events.NewMessage(pattern=r"^/setmatrix$"))
        async def set_matrix(event):
            if event.sender_id != Config.OWNER_ID:
                return
            args = event.message.text.split(maxsplit=1)
            if len(args) < 2:
                current = f"`{self.matrix_group_id}`" if self.matrix_group_id else "Not set"
                await event.reply(f"❌ Usage: `/setmatrix <group_id or @username>`\nCurrent: {current}")
                return
            target = args[1].strip()
            resolver = self.action_clients[0] if self.action_clients else None
            if not resolver:
                await event.reply("❌ No action client to resolve entity. Add a Power Ranger first.")
                return
            try:
                entity_ref = int(target) if target.lstrip('-').isdigit() else target
                entity = await resolver.get_entity(entity_ref)
                self.matrix_group_id = entity.id
                await self.db.marcuz_col.update_one(
                    {"key": "matrix_group_id"},
                    {"$set": {"value": self.matrix_group_id}},
                    upsert=True
                )
                await event.reply(f"✅ Matrix Group set to `{entity.title or entity.username or entity.id}` (ID: `{self.matrix_group_id}`)")
            except Exception as e:
                await event.reply(f"❌ Failed to resolve: {e}")

        @self.bot_client.on(events.NewMessage(pattern=r"^/check$"))
        async def check_members(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if self.target_group_id is None:
                await event.reply("❌ No target group. Use `/go` first or set manually.")
                return
            if self.check_in_progress:
                await event.reply("⏳ Check already in progress.")
                return
            self.check_in_progress = True
            await event.reply("🔍 Scanning members... (may take a while)")
            admin_client = None
            for client in self.action_clients:
                try:
                    await client.get_participants(self.target_group_id, limit=1)
                    admin_client = client
                    break
                except Exception:
                    continue
            if not admin_client:
                await event.reply("❌ No admin client found.")
                self.check_in_progress = False
                return
            bad = []
            total = 0
            try:
                async for participant in admin_client.iter_participants(self.target_group_id):
                    total += 1
                    user = participant.user if hasattr(participant, 'user') else participant
                    if user.deleted:
                        bad.append((user.id, user.first_name or "Deleted", "Deleted Account"))
                        continue
                    status = getattr(user, 'status', None)
                    if status is None:
                        continue
                    if isinstance(status, UserStatusOffline):
                        if status.was_online:
                            six_months_ago = time.time() - (6 * 30 * 24 * 3600)
                            if status.was_online.timestamp() < six_months_ago:
                                bad.append((user.id, user.first_name or "No Name", "Offline >6 months"))
                    elif isinstance(status, UserStatusEmpty):
                        bad.append((user.id, user.first_name or "No Name", "Never seen"))
            except FloodWaitError as e:
                await event.reply(f"⏳ Flood wait {e.seconds}s. Try again later.")
                self.check_in_progress = False
                return
            except Exception as e:
                await event.reply(f"❌ Check error: {e}")
                self.check_in_progress = False
                return
            self.check_in_progress = False
            self.bad_users = bad
            if bad:
                msg = f"📊 **Scan result**\nTotal members: {total}\nBad accounts: {len(bad)}\n\n"
                for uid, name, reason in bad[:50]:
                    msg += f"• {name} (ID: {uid}) – {reason}\n"
                if len(bad) > 50:
                    msg += f"\n... and {len(bad)-50} more."
                await event.reply(msg)
                with open("bad_users.txt", "w", encoding="utf-8") as f:
                    for uid, name, reason in bad:
                        f.write(f"{uid},{name},{reason}\n")
                await event.reply("📄 Full list saved to `bad_users.txt`.")
            else:
                await event.reply("✅ No bad accounts found.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/remove$"))
        async def remove_bad(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if self.target_group_id is None:
                await event.reply("❌ No target group.")
                return
            if not self.bad_users:
                await event.reply("❌ No bad users list. Run `/check` first.")
                return
            await event.reply(f"⏳ Removing {len(self.bad_users)} users...")
            admin_client = None
            for client in self.action_clients:
                try:
                    await client.get_participants(self.target_group_id, limit=1)
                    admin_client = client
                    break
                except Exception:
                    continue
            if not admin_client:
                await event.reply("❌ No admin client.")
                return
            removed = 0
            total = len(self.bad_users)
            for i, (uid, name, reason) in enumerate(self.bad_users, 1):
                try:
                    await admin_client.kick_participant(self.target_group_id, uid)
                    removed += 1
                    if removed % 50 == 0:
                        await event.reply(f"✅ Removed {removed}/{total}")
                    await asyncio.sleep(0.3)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                except Exception as e:
                    logger.error(f"Kick error: {e}")
            await event.reply(f"✅ Removal complete. {removed} users kicked.")
            self.bad_users = []

        # ==================== STATUS COMMAND ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^/status$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            taunt_count = sum(len(s) for s in self.delete_and_taunt_targets.values())
            subscribers_count = await self.db.channel_subscribers.count_documents({})
            msg = (
                f"📊 **System Status**\n"
                f"🤖 Action clients: {len(self.action_clients)}\n"
                f"🗂️ Learned phrases: {await self.db.learned.count_documents({})}\n"
                f"💾 Save mode: {'ON' if self.save_status else 'OFF'}\n"
                f"🎯 Copy mode: {'ON' if self.is_copy_active else 'OFF'}\n"
                f"📍 Matrix Group: {self.matrix_group_id or 'Not set'}\n"
                f"🚪 Target Group: {self.target_group_id or 'Not set'}\n"
                f"👹 Active Taunt Targets: {taunt_count}\n"
                f"📢 Subscribers: {subscribers_count}"
            )
            await event.reply(msg, parse_mode='markdown')

        # ==================== ALLOW / ADD / REMOVE ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^/addallow(?:@\w+)?$"))
        async def add_allow(event):
            if event.sender_id != Config.OWNER_ID:
                return
            reply = await event.get_reply_message()
            if not reply:
                await event.reply("❓ Reply to the target with `/addallow`.")
                return
            user = await reply.get_sender()
            await self.db.allowed_users.update_one(
                {"user_id": user.id},
                {"$set": {"name": user.first_name or "Unnamed"}},
                upsert=True,
            )
            await event.reply(
                f"✅ {self.format_mention(user.id, user.first_name or 'User')} granted access.",
                parse_mode='html'
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/removeallow(?:@\w+)?\s+(\d+)$"))
        async def remove_allow(event):
            if event.sender_id != Config.OWNER_ID:
                return
            target_id = int(event.pattern_match.group(1))
            result = await self.db.allowed_users.delete_one({"user_id": target_id})
            await event.reply("✅ Removed" if result.deleted_count else "⚠️ Not found")

        @self.bot_client.on(events.NewMessage(pattern=r"^/allowlist(?:@\w+)?$"))
        async def allow_list(event):
            if event.sender_id != Config.OWNER_ID:
                return
            users = await self.db.allowed_users.find().to_list(length=None)
            if not users:
                await event.reply("📭 Allow list empty.")
                return
            lines = [f"• {self.format_mention(u['user_id'], u.get('name', 'Unknown'))} (<code>{u['user_id']}</code>)" for u in users]
            await event.reply("<b>👑 Authorised Personnel</b>\n\n" + "\n".join(lines), parse_mode="html")

        # ==================== CHANNEL ADMIN: MODERATION COMMANDS ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^/mute(?:\s+(.*))?$"))
        async def handler_mute(event):
            await self.mute_user(event)

        @self.bot_client.on(events.NewMessage(pattern=r"^/unmute(?:\s+(.*))?$"))
        async def handler_unmute(event):
            await self.unmute_user(event)

        @self.bot_client.on(events.NewMessage(pattern=r"^/ban(?:\s+(.*))?$"))
        async def handler_ban(event):
            await self.ban_user(event)

        @self.bot_client.on(events.NewMessage(pattern=r"^/unban(?:\s+(.*))?$"))
        async def handler_unban(event):
            await self.unban_user(event)

        @self.bot_client.on(events.NewMessage(pattern=r"^/kick(?:\s+(.*))?$"))
        async def handler_kick(event):
            await self.kick_user(event)

        # ==================== CHANNEL ADMIN: /start, /notifyall, forward ====================
        @self.bot_client.on(events.NewMessage(pattern=r"^/start(?:\s+(\S+))?$"))
        async def handler_start(event):
            await self.start_handler(event)

        @self.bot_client.on(events.NewMessage(pattern=r"^/notifyall(?:\s+(.+))?$"))
        async def handler_notify(event):
            await self.notify_all_subscribers(event)

        @self.bot_client.on(events.NewMessage(incoming=True))
        async def handler_forward_media(event):
            await self.forward_media_to_channel(event)

        # ==================== UNIVERSAL WATCHER (existing) ====================
        @self.bot_client.on(events.NewMessage())
        async def watcher(event):
            if event.is_private:
                return
            if event.sender_id == self.bot_client.me.id or event.sender_id in self.action_ids:
                return

            chat_id = event.chat_id
            sender_id = event.sender_id

            # 1. Dark Passenger
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
                            await event.reply(taunt, parse_mode='html')
                        except Exception as e:
                            logger.error(f"Dark Passenger error: {e}")
                return

            # 2. Delete and Taunt
            if chat_id in self.delete_and_taunt_targets and sender_id in self.delete_and_taunt_targets[chat_id]:
                if event.text:
                    client = await self.get_action_client()
                    if client:
                        try:
                            await client.delete_messages(chat_id, [event.id])
                            target = await event.get_sender()
                            mention = self.format_mention(sender_id, target.first_name or "Target")
                            phrase = await self.get_next_phrase(chat_id)
                            await client.send_message(chat_id, f"{mention} {phrase}", parse_mode='html')
                        except Exception as e:
                            logger.error(f"Delete and taunt error: {e}")
                return

            # 3. Save System
            if chat_id == Config.LEARNING_GROUP and self.save_status:
                if await self.is_allowed(sender_id):
                    text = event.text
                    if event.message.forward and hasattr(event.message.forward, 'original'):
                        orig = event.message.forward.original
                        if hasattr(orig, 'text'):
                            text = orig.text
                    if text:
                        cleaned = self.strip_mentions(text)
                        if cleaned:
                            try:
                                await self.db.learned.insert_one({
                                    "group_id": chat_id,
                                    "user_id": sender_id,
                                    "text": cleaned,
                                    "timestamp": datetime.utcnow()
                                })
                            except DuplicateKeyError:
                                pass
                            except Exception as e:
                                logger.error(f"Save error: {e}")

            # 4. Tracking (K)
            if chat_id in self.tracking_targets and sender_id == self.tracking_targets[chat_id]:
                target = await event.get_sender()
                mention = self.format_mention(sender_id, target.first_name or "Target")
                client = await self.get_action_client()
                if client:
                    phrase = await self.get_next_phrase(chat_id)
                    try:
                        await client.send_message(
                            chat_id,
                            f"{mention} {phrase}",
                            parse_mode='html'
                        )
                    except:
                        pass

            # 5. Copy Mode
            if self.is_copy_active and chat_id == self.matrix_group_id:
                if sender_id == Config.OWNER_ID:
                    text = event.text
                    if text and not text.startswith('/'):
                        for client in self.action_clients:
                            try:
                                await client.send_message(chat_id, text)
                                await asyncio.sleep(0.2)
                            except Exception as e:
                                logger.error(f"Copy error: {e}")

            # 6. Custom Filters
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
                        except:
                            pass

            # 7. Protect Sovereign
            if event.text and event.text.startswith(("ချိန်ထား", "ပစ်သတ်")):
                reply = await event.get_reply_message()
                if reply and reply.sender_id == Config.OWNER_ID and event.sender_id != Config.OWNER_ID:
                    client = await self.get_action_client()
                    if client:
                        phrase = await self.get_next_phrase(chat_id)
                        mention = self.format_mention(event.sender_id, (await event.get_sender()).first_name or "Unknown")
                        await client.send_message(
                            chat_id,
                            f"{mention} {phrase}",
                            parse_mode='html'
                        )
                    return
                if not await self.is_allowed(sender_id):
                    await self.bot_client.send_message(
                        chat_id,
                        f"⛔ {await event.get_sender().first_name or 'User'}, you lack authority."
                    )

        # ==================== SPAM FILTERS (separate handlers) ====================
        @self.bot_client.on(events.NewMessage)
        async def sticker_spam_handler(event):
            await self.sticker_spam_filter(event)

        @self.bot_client.on(events.NewMessage)
        async def short_text_spam_handler(event):
            await self.short_text_spam_filter(event)

        @self.bot_client.on(events.NewMessage)
        async def bio_link_handler(event):
            await self.bio_link_filter(event)

        @self.bot_client.on(events.NewMessage(incoming=True))
        async def language_filter_handler(event):
            await self.global_traffic_processing_matrix(event)

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
        logger.info(f"🤖 Main bot started as @{me.username}")

        await self.load_userbots()
        await self.load_taunt_targets()

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
