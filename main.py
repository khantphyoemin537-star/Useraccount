#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Ninja System — Auto-Catch + /spam + /startspam + Taunt + /go + /adm
                          + /kill + /s (session)

🆕 FEATURES:
- /kill <uid...> [chat_id]  → ninja ဝိုင်းဆဲ (full name + phrase)
- /killstop / /killstatus
- /addkillphrase (bulk) · /listkillphrase · /clearkillphrase
- 🔑 /s <ninja_id>   → StringSession ပြန်ထုတ်
- 🔑 /sall           → Ninja အားလုံး session strings (DM file)
- ရပ် → spam + kill ၂ မျိုးလုံး ရပ်
"""

import asyncio, io, logging, os, random, re, sys, threading, time, unicodedata
from datetime import datetime, timedelta
from html import escape as escape_html
from typing import Dict, List, Optional, Set, Tuple

import pytz
from flask import Flask
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, OperationFailure
from telethon import TelegramClient, events, errors
from telethon.errors import (
    FloodWaitError,
    PeerIdInvalidError,
    ChannelPrivateError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    UserNotParticipantError,
)
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest


class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "6015356597"))
    MONGO_URI = os.getenv("MONGO_URI",
        "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true")
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "8824002850:AAELMmlNd_rxs-kJfX69usTrA86cr-z-Va4")

    SPAM_GROUPS = [-1004381473883, -1003836488351, -1003733625547, -1004358425408]

    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yangon"))
    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    ADMIN_CACHE_TTL = 600
    MAX_RETRIES = 3

    SPAWN_BOT_NEW_ID = 6157455819
    SPAWN_BOT_OLD_ID = 8999491734
    SPAWN_GROUP_2 = SPAM_GROUPS

    W_REPLY_COUNT = 2
    W_REPLY_DELAY_MIN = 0.5
    W_REPLY_DELAY_MAX = 1.5

    NINJA_IGNORED_EMOJIS = ["🪞", "✨", "⚜️", "💮", "❓"]

    SPAWN_PHRASES = (
        "A CHARACTER HAS SPAWNED",
        "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ",
        "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ɪɴ ᴛʜᴇ ᴄʜᴀᴛ",
    )

    START_SPAM_INTERVAL = 18000
    START_SPAM_MIN_DELAY = 5
    START_SPAM_MAX_DELAY = 15
    START_SPAM_JITTER = 0.10

    SPAM_GROUP_INTERVAL = 0.1
    SPAM_NINJA_COOLDOWN = 0.1
    SPAM_JITTER = 0.1
    SPAM_GLOBAL_DELAY = 0.1
    SPAM_PAUSE_AFTER_SPAWN = 3

    # 🆕 Blacklist TTLs
    BLACKLIST_PRIVATE_SEC = 3600
    BLACKLIST_ENTITY_SEC  = 300

    SPAM_TEXTS = [
        " @FLASH_SPAM_Bot | @fuckyourwifey_bot | @Imjustkidding_bot | @GodMorgan_robot | @enforcermorgan_11robot | fqcawqAaaaafbBsqqlqoျဘျဆငငေတငတုsahqBwqiqoaj#!11&$1(!92929*@*@>>",
        " @GodMorgan_robot | @Imjustkidding_bot | qwertyuiopASDFGHJKLzxcvbnm123rkrkeekekek4567890!@#$%",
        " @enforcermorgan_11robot | fqcawqAaaaafbBsqqlqo ျဘျဆငငေejejejejeejwjjeejတငတု 1234567890",
        " @FLASH_SPAM_Bot | @fuckyourwifey_bot | spam text alternative hshahahahahaahahajajsjsjsjsjsjsjsjsjversion here",
    ]

    # 🆕 KILL SWARM
    KILL_INTERVAL = 2.0
    KILL_JITTER = 0.30
    KILL_MIN_DELAY = 0.3

    # 💀 Default kill phrases — ကိုယ်တိုင် /addkillphrase နဲ့ ဖြည့်ပါ
    DEFAULT_KILL_PHRASES = [
        "မင်းကို ငါမသိချင်ဘူး",
        "သွားစမ်းကွာ",
        "နှုတ်ပိတ်ထားစမ်း",
        "ဒီနေရာက ထွက်သွား",
        "မင်းစကား မလိုချင်ဘူး",
    ]


SPAM_TEXT = Config.SPAM_TEXTS[0]

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


# ══════════════════════════════════════════════════════════════════
#  🧼 INVISIBLE CHARACTER CLEANER
# ══════════════════════════════════════════════════════════════════
def clean_invisible(text: str) -> str:
    if not text:
        return ""
    try:
        return ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    except Exception:
        return text


def strip_for_match(text: str) -> str:
    return clean_invisible(text).upper()


def looks_like_spawn(text: str) -> bool:
    if not text:
        return False
    cleaned = clean_invisible(text)
    upper = cleaned.upper()
    for ph in Config.SPAWN_PHRASES:
        if ph.upper() in upper:
            return True
    for sub in ("CHARACTER HAS SPAWNED", "ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ", "SPAWNED", "sᴘᴀᴡɴᴇᴅ"):
        if sub.upper() in upper:
            return True
    return False


def looks_like_catch_success(text: str) -> bool:
    if not text:
        return False
    cleaned = clean_invisible(text)
    upper = cleaned.upper()
    return (
        "YOU GOT A NEW CHARACTER" in upper
        or "ʏᴏᴜ ɢᴏᴛ ᴀ ɴᴇᴡ ᴄʜᴀʀᴀᴄᴛᴇʀ" in cleaned
        or "NEW CHARACTER" in upper
    )


# ══════════════════════════════════════════════════════════════════
#  🆕 ERROR REPORTER (DM to Owner, 30s dedup)
# ══════════════════════════════════════════════════════════════════
_error_dedup: Dict[str, float] = {}
_ERROR_DEDUP_SEC = 30


async def report_error(bot_client, context: str, exc: Exception, extra: str = ""):
    try:
        key = f"{context}:{type(exc).__name__}"
        now = time.time()
        if now - _error_dedup.get(key, 0) < _ERROR_DEDUP_SEC:
            return
        _error_dedup[key] = now

        msg = (
            f"🚨 **ERROR REPORT**\n"
            f"📍 **Where:** `{context}`\n"
            f"❌ **Type:** `{type(exc).__name__}`\n"
            f"💬 **Msg:** `{str(exc)[:300]}`\n"
        )
        if extra:
            msg += f"ℹ️ **Info:** `{extra[:300]}`\n"

        await bot_client.send_message(Config.OWNER_ID, msg)
    except Exception as e:
        print(f"⚠️ Failed to send error DM: {e}")


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
                    self.uri,
                    tlsAllowInvalidCertificates=True,
                    serverSelectionTimeoutMS=5000,
                )
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
            logger.info("MongoDB closed.")

    @property
    def system_col(self): return self.db["system_col"]
    @property
    def ninja_col(self): return self.db["ninja_col"]
    @property
    def taunt_targets(self): return self.db["taunt_targets"]
    @property
    def auto_catch_col(self): return self.db["auto_catch_col"]
    @property
    def kill_col(self): return self.db["kill_col"]


# ---------- Bot ----------
class SovereignBot:
    def __init__(self, db):
        self.db = db
        self.bot_client = TelegramClient(
            "bot_main_session", Config.API_ID, Config.API_HASH, flood_sleep_threshold=60
        )
        self.bot_id: Optional[int] = None

        self.ninja_clients: List[TelegramClient] = []
        self.ninja_names: List[str] = []
        self.ninja_ids: Set[int] = set()

        self.auto_catch_ids: Set[int] = set()

        self.ninja_spam_tasks: Dict[Tuple[int, ...], bool] = {}

        self.spam_ninja_last: Dict[int, float] = {}
        self.spam_chat_last: Dict[int, float] = {}
        self.spam_flood_until: Dict[int, float] = {}

        self.ninja_chat_blacklist: Dict[Tuple[int, int], float] = {}

        self.dialogs_populated: Set[int] = set()

        self.delete_and_taunt_targets: Dict[int, Set[int]] = {}
        self.phrase_lists: Dict[int, List[str]] = {}
        self.phrase_indices: Dict[int, int] = {}

        self.chat_admin_cache: Dict[int, Tuple[List[TelegramClient], float]] = {}
        self.admin_cache_locks: Dict[int, asyncio.Lock] = {}

        self.w_reply_picker = {"key": None, "selected": set()}
        self.latest_spawn_msg: Dict[int, int] = {}
        self.ninja_spawn_tracker: Dict[Tuple[int, int], int] = {}
        self.ninja_latest_spawn: Dict[int, int] = {}

        self.start_spam_tasks: Dict[int, asyncio.Task] = {}
        self.start_spam_target: Optional[str] = None
        self.start_spam_active: bool = False

        self.spam_pause_until: float = 0.0

        # 🆕 KILL SWARM
        self.kill_tasks: Dict[Tuple[int, int], bool] = {}
        self.kill_phrases: List[str] = []

        self._register_handlers()

    async def _report(self, context: str, exc: Exception, extra: str = ""):
        await report_error(self.bot_client, context, exc, extra)

    # ============================================================
    # AUTO-CATCH LIST (DB)
    # ============================================================
    async def _load_auto_catch_ids(self):
        doc = await self.db.auto_catch_col.find_one({"_id": "auto_ids"})
        if doc:
            self.auto_catch_ids = set(int(x) for x in doc.get("ids", []))
        logger.info(f"🎯 Auto-catch list: {len(self.auto_catch_ids)} IDs")

    async def _save_auto_catch_ids(self):
        await self.db.auto_catch_col.update_one(
            {"_id": "auto_ids"},
            {"$set": {"ids": sorted(self.auto_catch_ids)}},
            upsert=True,
        )

    # ============================================================
    # TAUNT TARGETS (DB)
    # ============================================================
    async def load_taunt_targets(self):
        async for doc in self.db.taunt_targets.find():
            cid = doc["chat_id"]
            tids = doc.get("target_ids", [])
            if tids:
                self.delete_and_taunt_targets[cid] = set(tids)

    async def _add_taunt_target(self, cid, tid):
        self.delete_and_taunt_targets.setdefault(cid, set()).add(tid)
        await self.db.taunt_targets.update_one(
            {"chat_id": cid}, {"$addToSet": {"target_ids": tid}}, upsert=True
        )

    async def _remove_taunt_target(self, cid, tid):
        if cid in self.delete_and_taunt_targets:
            self.delete_and_taunt_targets[cid].discard(tid)
            if not self.delete_and_taunt_targets[cid]:
                del self.delete_and_taunt_targets[cid]
                await self.db.taunt_targets.delete_one({"chat_id": cid})
            else:
                await self.db.taunt_targets.update_one(
                    {"chat_id": cid}, {"$pull": {"target_ids": tid}}
                )

    async def _clear_taunt_targets(self, cid):
        if cid in self.delete_and_taunt_targets:
            del self.delete_and_taunt_targets[cid]
            await self.db.taunt_targets.delete_one({"chat_id": cid})

    # ============================================================
    # 🆕 KILL PHRASES (DB)
    # ============================================================
    async def _load_kill_phrases(self):
        doc = await self.db.kill_col.find_one({"_id": "phrases"})
        if doc and doc.get("phrases"):
            self.kill_phrases = list(doc["phrases"])
        else:
            self.kill_phrases = list(Config.DEFAULT_KILL_PHRASES)
        logger.info(f"💀 Kill phrases: {len(self.kill_phrases)}")

    async def _save_kill_phrases(self):
        await self.db.kill_col.update_one(
            {"_id": "phrases"},
            {"$set": {"phrases": self.kill_phrases}},
            upsert=True,
        )

    # ============================================================
    # ADMIN CACHE
    # ============================================================
    async def _scan_admin_clients(self, cid):
        async def check(c):
            try:
                p = await c.get_permissions(cid, "me")
                if p and getattr(p, "is_admin", False):
                    return c
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except Exception:
                pass
            return None

        results = await asyncio.gather(*[check(c) for c in self.ninja_clients], return_exceptions=False)
        return [c for c in results if c is not None]

    async def _get_admin_clients(self, cid):
        now = time.time()
        cached = self.chat_admin_cache.get(cid)
        if cached and now < cached[1]:
            return cached[0]

        if cid not in self.admin_cache_locks:
            self.admin_cache_locks[cid] = asyncio.Lock()

        async with self.admin_cache_locks[cid]:
            cached = self.chat_admin_cache.get(cid)
            if cached and time.time() < cached[1]:
                return cached[0]
            admins = await self._scan_admin_clients(cid)
            self.chat_admin_cache[cid] = (admins, time.time() + Config.ADMIN_CACHE_TTL)
            logger.info(f"🔎 Admin scan {cid}: {len(admins)}/{len(self.ninja_clients)}")
            return admins

    async def preload_admin_caches(self):
        targets = set(Config.SPAM_GROUPS)
        if not targets:
            return
        logger.info(f"⚡ Preloading admin caches for {len(targets)} groups...")
        await asyncio.gather(*[self._get_admin_clients(g) for g in targets], return_exceptions=True)

    # ============================================================
    # AUTO-PROMOTE
    # ============================================================
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
                        me = await c.get_me()
                        uid = me.id
                        c.tg_user_id = uid
                    np = await self.bot_client.get_permissions(cid, uid)
                    if np and getattr(np, "is_admin", False):
                        already += 1
                        continue
                    await self.bot_client.edit_admin(
                        cid, uid,
                        change_info=False,
                        post_messages=False,
                        edit_messages=False,
                        delete_messages=False,
                        ban_users=False,
                        invite_users=False,
                        pin_messages=False,
                        add_admins=False,
                        anonymous=False,
                        manage_call=False,
                        other=True,
                    )
                    promoted += 1
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                    failed += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.4)
            try:
                await self.bot_client.send_message(
                    Config.OWNER_ID,
                    f"✅ Auto-Promote `{cid}` · promoted={promoted} already={already} failed={failed} (no perms)"
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"_auto_promote: {e}")

    # ============================================================
    # START-SPAM
    # ============================================================
    async def _start_spam_worker(self, ninja, uid, target):
        await asyncio.sleep(random.uniform(Config.START_SPAM_MIN_DELAY, Config.START_SPAM_MAX_DELAY))
        while self.start_spam_active and uid in self.start_spam_tasks:
            try:
                await asyncio.wait_for(ninja.send_message(target, "/start"), timeout=20)
                logger.info(f"🎯 [{uid}] /start → @{target}")
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"🎯 [{uid}]: {e}")
            jitter = Config.START_SPAM_INTERVAL * random.uniform(
                -Config.START_SPAM_JITTER, Config.START_SPAM_JITTER
            )
            wait = max(30, Config.START_SPAM_INTERVAL + jitter)
            waited = 0
            while waited < wait and self.start_spam_active:
                await asyncio.sleep(5)
                waited += 5

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
                    me = await c.get_me()
                    uid = me.id
                    c.tg_user_id = uid
                self.start_spam_tasks[uid] = asyncio.create_task(
                    self._start_spam_worker(c, uid, target)
                )
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

    # ============================================================
    # 🎯 AUTO-CATCH
    # ============================================================
    async def _ninja_spawn_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid:
                return
            if event.sender_id != Config.SPAWN_BOT_NEW_ID:
                return
            if event.chat_id not in Config.SPAM_GROUPS:
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

            if not looks_like_spawn(text):
                cleaned = clean_invisible(text)
                logger.info(
                    f"⚠️ Spawn Bot msg · no phrase match\n"
                    f"   RAW:     {text[:120]!r}\n"
                    f"   CLEANED: {cleaned[:120]!r}"
                )
                return

            cleaned = clean_invisible(text)
            if any(e in cleaned for e in Config.NINJA_IGNORED_EMOJIS):
                logger.info(f"⏭️ [spawn] emoji skip · chat={event.chat_id}")
                return

            skey = f"{event.chat_id}:{event.message.id}"

            if self.w_reply_picker.get("key") != skey:
                avail = list(self.ninja_ids)
                if not avail:
                    return
                if len(avail) <= Config.W_REPLY_COUNT:
                    picked = set(avail)
                else:
                    picked = set(random.sample(avail, Config.W_REPLY_COUNT))
                self.w_reply_picker["key"] = skey
                self.w_reply_picker["selected"] = picked
                self.latest_spawn_msg[event.chat_id] = event.message.id
                self.spam_pause_until = time.monotonic() + Config.SPAM_PAUSE_AFTER_SPAWN
                logger.info(f"🎯 Spawn {skey} · picked {len(picked)}/{len(avail)} for /w")

            if uid not in self.w_reply_picker["selected"]:
                return

            await asyncio.sleep(random.uniform(
                Config.W_REPLY_DELAY_MIN, Config.W_REPLY_DELAY_MAX
            ))
            try:
                r = await event.message.reply("/w")
                self.ninja_spawn_tracker[(uid, r.id)] = event.chat_id
                self.ninja_latest_spawn[uid] = event.chat_id
                logger.info(f"🥷 [{uid}] /w sent · spawn {skey}")
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds, 30))
            except Exception as e:
                logger.warning(f"🥷 [{uid}] /w failed: {e}")
        except Exception as e:
            await self._report("spawn_handler", e)

    async def _ninja_hint_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid:
                return
            if event.sender_id != Config.SPAWN_BOT_OLD_ID:
                return
            if event.chat_id not in Config.SPAM_GROUPS:
                return
            if uid not in self.auto_catch_ids:
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

            cleaned = clean_invisible(text)
            if any(e in cleaned for e in Config.NINJA_IGNORED_EMOJIS):
                return

            m = re.search(r"(/catch(?:@\w+)?\s+[^\n]+)", cleaned)
            if not m:
                return

            cmd = m.group(1).strip(" `\n\r")
            target_chat = event.chat_id
            spawn_msg_id = self.latest_spawn_msg.get(target_chat)

            try:
                if spawn_msg_id:
                    await event.client.send_message(target_chat, cmd, reply_to=spawn_msg_id)
                else:
                    await event.client.send_message(target_chat, cmd)
                logger.info(f"🎯 [{uid}] /catch → {target_chat} · {cmd[:60]}")
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds, 30))
            except Exception as e:
                await self._report("hint_handler", e, f"uid={uid}")
        except Exception as e:
            await self._report("hint_handler.outer", e)

    def _register_ninja_handlers(self, client):
        client.add_event_handler(
            self._ninja_spawn_handler,
            events.NewMessage(chats=Config.SPAM_GROUPS, from_users=Config.SPAWN_BOT_NEW_ID),
        )
        client.add_event_handler(
            self._ninja_hint_handler,
            events.NewMessage(chats=Config.SPAM_GROUPS, from_users=Config.SPAWN_BOT_OLD_ID),
        )
        client.add_event_handler(self._ninja_join_handler, events.ChatAction())

    # ============================================================
    # LOAD NINJAS
    # ============================================================
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

        count = 0
        async for doc in self.db.ninja_col.find():
            sess = doc.get("session")
            if not sess:
                continue
            try:
                c = TelegramClient(StringSession(sess), Config.API_ID, Config.API_HASH,
                                   flood_sleep_threshold=0)
                await c.start()
                if await c.is_user_authorized():
                    me = await c.get_me()
                    c.tg_user_id = me.id
                    self.ninja_clients.append(c)
                    self.ninja_names.append(doc.get("name", f"Ninja-{count+1}"))
                    self.ninja_ids.add(me.id)
                    self._register_ninja_handlers(c)
                    count += 1
                    logger.info(f"✅ Ninja #{count} loaded: @{me.username}")
                else:
                    await c.disconnect()
            except Exception as e:
                logger.error(f"❌ Ninja load failed: {e}")
        logger.info(f"🚀 Ninja Pool ready: {len(self.ninja_clients)} clients.")

    # ============================================================
    # HELPERS
    # ============================================================
    def format_mention(self, uid, name):
        return f"<a href='tg://user?id={uid}'>{escape_html(name)}</a>"

    def bq(self, text):
        return f"<blockquote><b>{text}</b></blockquote>"

    async def fetch_phrases(self):
        doc = await self.db.system_col.find_one({"key": "shadow_taunts"})
        if doc and doc.get("value"):
            return list(doc["value"])
        return ["မင်းရဲ့စကားတွေ ငါမှတ်ထားတယ်"]

    async def get_next_phrase(self, cid):
        if cid not in self.phrase_lists:
            p = await self.fetch_phrases()
            random.shuffle(p)
            self.phrase_lists[cid] = p
            self.phrase_indices[cid] = 0
        p = self.phrase_lists[cid]
        i = self.phrase_indices[cid]
        ph = p[i]
        self.phrase_indices[cid] = (i + 1) % len(p)
        return ph

    async def _get_full_name(self, uid) -> str:
        try:
            ent = await self.bot_client.get_entity(uid)
            first = getattr(ent, "first_name", "") or ""
            last = getattr(ent, "last_name", "") or ""
            full = f"{first} {last}".strip()
            if full:
                return full
            uname = getattr(ent, "username", None)
            if uname:
                return f"@{uname}"
            title = getattr(ent, "title", None)
            if title:
                return title
        except Exception:
            pass
        return "Target"

    def _find_ninja_by_id(self, uid):
        for i, c in enumerate(self.ninja_clients):
            if getattr(c, "tg_user_id", None) == uid:
                return i, c
        return None, None

    # ============================================================
    # 🆕 ENTITY FIX — populate dialogs
    # ============================================================
    async def _populate_dialogs(self, client, uid):
        try:
            dialogs = await client.get_dialogs(limit=None)
            count = len(dialogs)
            self.dialogs_populated.add(uid)
            logger.info(f"✅ [{uid}] dialogs populated · {count} chats")
            return count
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 30))
            return 0
        except Exception as e:
            logger.warning(f"⚠️ [{uid}] get_dialogs failed: {type(e).__name__}: {e}")
            return 0

    async def _warm_entities(self, chat_ids):
        logger.info(f"🔥 Warming entity cache · {len(self.ninja_clients)} ninjas × {len(chat_ids)} groups...")
        ok = fail = 0
        for c in self.ninja_clients:
            uid = getattr(c, "tg_user_id", "?")
            if uid not in self.dialogs_populated:
                await self._populate_dialogs(c, uid)
                await asyncio.sleep(0.1)
            for cid in chat_ids:
                try:
                    await c.get_input_entity(cid)
                    ok += 1
                except FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds, 20))
                    fail += 1
                except Exception as e:
                    logger.warning(f"⚠️ warm [{uid}] {cid}: {type(e).__name__}: {e}")
                    fail += 1
                await asyncio.sleep(0.05)
        logger.info(f"🔥 Entity cache done · ok={ok} fail={fail}")
        return ok, fail

    def _pick_ninja(self, cid: int, now: float) -> Optional[TelegramClient]:
        eligible = []
        for c in self.ninja_clients:
            uid = getattr(c, "tg_user_id", None)
            if not uid:
                continue
            if self.ninja_chat_blacklist.get((uid, cid), 0) > now:
                continue
            if self.spam_flood_until.get(uid, 0) > now:
                continue
            if now - self.spam_ninja_last.get(uid, 0) < Config.SPAM_NINJA_COOLDOWN:
                continue
            eligible.append(c)
        if not eligible:
            return None
        eligible.sort(key=lambda c: self.spam_ninja_last.get(
            getattr(c, "tg_user_id", 0), 0))
        return eligible[0]

    def _is_chat_ready(self, cid: int, now: float) -> bool:
        last = self.spam_chat_last.get(cid, 0)
        interval = Config.SPAM_GROUP_INTERVAL
        jitter = interval * random.uniform(-Config.SPAM_JITTER, Config.SPAM_JITTER)
        return now - last >= max(1.5, interval + jitter)

    async def _spam_watchdog(self, key, task):
        try:
            await task
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"🚨 spam loop crashed: {e}")
            await self._report("spam_watchdog", e, f"key={key}")
        if self.ninja_spam_tasks.get(key):
            logger.warning(f"🐕 watchdog restarting spam loop {key}")
            self.ninja_spam_tasks[key] = False
            await asyncio.sleep(2)
            await self._start_spam_loop(list(key))

    async def _send_with_retry(self, ninja, uid, cid, text) -> bool:
        try:
            await ninja.send_message(cid, text)
            return True

        except (ChannelPrivateError, ChatWriteForbiddenError,
                UserBannedInChannelError, UserNotParticipantError) as e:
            self.ninja_chat_blacklist[(uid, cid)] = (
                time.monotonic() + Config.BLACKLIST_PRIVATE_SEC
            )
            logger.warning(f"⛔ [{uid}→{cid}] {type(e).__name__} → blacklist 1h")
            return False

        except (PeerIdInvalidError, ValueError) as e:
            logger.warning(f"⚠️ Entity err [{uid}→{cid}]: {type(e).__name__}. Re-populating...")
            try:
                if uid not in self.dialogs_populated:
                    await self._populate_dialogs(ninja, uid)
                try:
                    await ninja.get_entity(cid)
                except Exception:
                    pass
                await asyncio.sleep(0.3)
                await ninja.send_message(cid, text)
                logger.info(f"✅ Retry OK [{uid}→{cid}]")
                return True
            except (ChannelPrivateError, ChatWriteForbiddenError) as e2:
                self.ninja_chat_blacklist[(uid, cid)] = (
                    time.monotonic() + Config.BLACKLIST_PRIVATE_SEC
                )
                logger.warning(f"⛔ [{uid}→{cid}] {type(e2).__name__} → blacklist 1h")
                return False
            except Exception as retry_e:
                self.ninja_chat_blacklist[(uid, cid)] = (
                    time.monotonic() + Config.BLACKLIST_ENTITY_SEC
                )
                logger.error(f"❌ Retry failed [{uid}→{cid}]: {type(retry_e).__name__}: {retry_e}")
                await self._report("spam_send_retry", retry_e, f"uid={uid} cid={cid}")
                return False

        except FloodWaitError:
            raise
        except Exception:
            raise

    async def _start_spam_loop(self, chat_ids):
        key = tuple(sorted(chat_ids))
        if self.ninja_spam_tasks.get(key):
            return
        self.ninja_spam_tasks[key] = True
        if not self.ninja_clients:
            return

        for cid in chat_ids:
            self.spam_chat_last.setdefault(cid, 0)
        for c in self.ninja_clients:
            uid = getattr(c, "tg_user_id", None)
            if uid:
                self.spam_ninja_last.setdefault(uid, 0)
                self.spam_flood_until.setdefault(uid, 0)

        await self._warm_entities(chat_ids)

        async def loop():
            logger.info(
                f"📢 Spam loop started · {len(chat_ids)} groups · "
                f"chat_interval={Config.SPAM_GROUP_INTERVAL}s · "
                f"ninja_cooldown={Config.SPAM_NINJA_COOLDOWN}s · "
                f"pool={len(self.ninja_clients)}"
            )
            send_count = 0
            err_count = 0

            while self.ninja_spam_tasks.get(key):
                try:
                    now = time.monotonic()
                    if now < self.spam_pause_until:
                        await asyncio.sleep(0.5)
                        continue

                    for cid in chat_ids:
                        now = time.monotonic()
                        if not self._is_chat_ready(cid, now):
                            continue

                        ninja = self._pick_ninja(cid, now)
                        if not ninja:
                            continue

                        uid = getattr(ninja, "tg_user_id", "?")
                        text = random.choice(Config.SPAM_TEXTS)

                        try:
                            ok = await self._send_with_retry(ninja, uid, cid, text)
                            ts = time.monotonic()
                            self.spam_ninja_last[uid] = ts
                            if ok:
                                self.spam_chat_last[cid] = ts
                                send_count += 1
                                if send_count % 20 == 0:
                                    logger.info(f"📊 sent={send_count} err={err_count} · last=[{uid} → {cid}]")
                            else:
                                err_count += 1
                        except FloodWaitError as e:
                            wait = min(e.seconds + 5, 600)
                            self.spam_flood_until[uid] = time.monotonic() + wait
                            logger.warning(f"⛔ [{uid}] flood {e.seconds}s → cooldown {wait}s")
                            err_count += 1
                        except Exception as e:
                            err_count += 1
                            logger.warning(f"❌ send err [{uid} → {cid}]: {type(e).__name__}: {e}")
                            await self._report("spam_send", e, f"uid={uid} cid={cid}")

                        await asyncio.sleep(Config.SPAM_GLOBAL_DELAY)

                    await asyncio.sleep(0.5)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"spam loop err: {e}")
                    await self._report("spam_loop", e)
                    await asyncio.sleep(2)

            logger.info(f"🛑 Spam stopped for {len(chat_ids)} groups · total sent={send_count} err={err_count}")

        task = asyncio.create_task(loop())
        asyncio.create_task(self._spam_watchdog(key, task))

    async def _taunt_user(self, cid, tid, msg_id, tname="Target"):
        admins = await self._get_admin_clients(cid)
        if not admins:
            return
        c = random.choice(admins)
        try:
            await c.delete_messages(cid, [msg_id])
        except Exception:
            pass
        mention = self.format_mention(tid, tname)
        phrase = await self.get_next_phrase(cid)
        try:
            await c.send_message(cid, f"{mention} {phrase}", parse_mode="html")
        except Exception as e:
            logger.error(f"Taunt: {e}")

    # ============================================================
    # 💀 KILL SWARM LOOP
    # ============================================================
    async def _kill_worker(self, ninja, cid, uid, tname, key):
        while self.kill_tasks.get(key):
            phrase = random.choice(self.kill_phrases) if self.kill_phrases else "…"
            mention = self.format_mention(uid, tname)
            try:
                await ninja.send_message(cid, f"{mention} {phrase}", parse_mode="html")
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds + 2, 60))
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            jitter = Config.KILL_INTERVAL * random.uniform(
                -Config.KILL_JITTER, Config.KILL_JITTER)
            await asyncio.sleep(max(Config.KILL_MIN_DELAY,
                                    Config.KILL_INTERVAL + jitter))

    async def start_kill(self, cid, uid, tname):
        key = (cid, uid)
        if self.kill_tasks.get(key):
            return 0
        if not self.ninja_clients or not self.kill_phrases:
            return 0
        self.kill_tasks[key] = True
        started = 0
        ninjas = list(self.ninja_clients)
        random.shuffle(ninjas)
        for c in ninjas:
            asyncio.create_task(self._kill_worker(c, cid, uid, tname, key))
            started += 1
            await asyncio.sleep(0.05)
        return started

    def stop_all_kills(self):
        n = 0
        for k in list(self.kill_tasks.keys()):
            if self.kill_tasks[k]:
                self.kill_tasks[k] = False
                n += 1
        return n

    # ============================================================
    # COMMAND HANDLERS
    # ============================================================
    def _register_handlers(self):

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/addninja(?:@\w+)?(?:\s+(.*?))?(?:\s+(.*))?$"
        ))
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
                c = TelegramClient(StringSession(sess), Config.API_ID, Config.API_HASH,
                                   flood_sleep_threshold=0)
                await c.start()
                me = await c.get_me()
                c.tg_user_id = me.id
                self.ninja_clients.append(c)
                self.ninja_names.append(name)
                self.ninja_ids.add(me.id)
                self._register_ninja_handlers(c)
                self.chat_admin_cache.clear()
                await event.reply(f"✅ '{name}' (ID: {me.id}) added. Total: {len(self.ninja_clients)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {e}")
                await self.db.ninja_col.delete_one({"session": sess})

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
                    tag = " 🎯" if me.id in self.auto_catch_ids else ""
                    lines.append(f"  {i+1}. **{full}** {u} (ID: `{me.id}`) ✅{tag}")
                except Exception:
                    lines.append(f"  {i+1}. **{n}** ❌")
            lines.append(f"\n📊 Online: {online}/{len(self.ninja_clients)}")
            lines.append(f"🎯 Auto-Catch: `{len(self.auto_catch_ids)}`")
            await event.reply("\n".join(lines), parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(pattern=r"^/removeninja(?:@\w+)?(?:\s+(\d+))?$"))
        async def remove_ninja(event):
            if event.sender_id != Config.OWNER_ID:
                return
            arg = event.pattern_match.group(1)

            if not arg and event.is_reply:
                r = await event.get_reply_message()
                if r and r.text:
                    m = re.search(r"(\d{5,})", r.text)
                    if m:
                        arg = m.group(1)

            if not arg:
                return await event.reply(
                    "❓ **Usage:** `/removeninja <user_id>`\n"
                    "ဥပမာ → `/removeninja 8538593411`",
                    parse_mode="markdown",
                )

            target_id = int(arg)

            idx = None
            for i, c in enumerate(self.ninja_clients):
                if getattr(c, "tg_user_id", None) == target_id:
                    idx = i
                    break

            if idx is None:
                return await event.reply(
                    f"❌ Ninja ID `{target_id}` pool ထဲမှာ မတွေ့ပါ။\n"
                    f"💡 `/listninja` နဲ့ စစ်ပါ။",
                    parse_mode="markdown",
                )

            doc = await self.db.ninja_col.find_one({"tg_user_id": target_id})
            if not doc:
                plist = await self.db.ninja_col.find().to_list(length=None)
                if idx < len(plist):
                    doc = plist[idx]
            if doc:
                await self.db.ninja_col.delete_one({"_id": doc["_id"]})

            c = self.ninja_clients.pop(idx)
            name = self.ninja_names.pop(idx) if idx < len(self.ninja_names) else "Ninja"
            self.ninja_ids.discard(target_id)
            try:
                await c.disconnect()
            except Exception:
                pass
            self.chat_admin_cache.clear()
            self.dialogs_populated.discard(target_id)
            for k in list(self.ninja_chat_blacklist.keys()):
                if k[0] == target_id:
                    self.ninja_chat_blacklist.pop(k, None)

            await event.reply(
                f"✅ Removed ninja\n"
                f"👤 Name: `{name}`\n"
                f"🆔 ID: `{target_id}`\n"
                f"👥 Pool left: `{len(self.ninja_clients)}`",
                parse_mode="markdown",
            )

        # ============================================================
        # 🔑 /s — StringSession ပြန်ထုတ်
        # ============================================================
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/s(?:@\w+)?(?:\s+(\d+))?$"
        ))
        async def s_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")

            arg = event.pattern_match.group(1)
            if not arg and event.is_reply:
                r = await event.get_reply_message()
                if r and r.text:
                    m = re.search(r"(\d{5,})", r.text)
                    if m:
                        arg = m.group(1)

            if not arg:
                return await event.reply(
                    "⚠️ **Usage**\n"
                    "• `/s <ninja_user_id>`\n"
                    "• reply → `/s`\n\n"
                    "💡 `/listninja` နဲ့ ID ကြည့်",
                    parse_mode="markdown",
                )

            uid = int(arg)
            idx, ninja = self._find_ninja_by_id(uid)
            if ninja is None:
                return await event.reply(
                    f"❌ ID `{uid}` ninja pool ထဲမှာ မရှိဘူး။",
                    parse_mode="markdown",
                )

            name = self.ninja_names[idx] if idx < len(self.ninja_names) else "Ninja"

            try:
                sess = StringSession.save(ninja.session)
            except Exception as e:
                return await event.reply(f"❌ Session extract failed: `{e}`")

            header = (
                f"🔑 **Session String**\n"
                f"👤 `{name}` (ID: `{uid}`)\n"
                f"📏 Length: `{len(sess)}`\n\n"
            )

            MAX = 3500
            if len(sess) + len(header) <= 4096:
                try:
                    await event.reply(header + f"`{sess}`", parse_mode="markdown")
                    return
                except Exception:
                    pass

            try:
                bio = io.BytesIO(sess.encode("utf-8"))
                bio.name = f"session_{uid}.txt"
                await self.bot_client.send_file(
                    Config.OWNER_ID,
                    bio,
                    caption=header,
                    parse_mode="markdown",
                )
                await event.reply(
                    f"📁 Session file DM ပို့ပြီး · `{name}` (`{uid}`)",
                    parse_mode="markdown",
                )
            except Exception as e:
                await event.reply(f"❌ Send failed: `{e}`")

        @self.bot_client.on(events.NewMessage(pattern=r"^/sall(?:@\w+)?$"))
        async def sall_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            if not self.ninja_clients:
                return await event.reply("❌ Ninja pool empty.")

            lines = []
            for i, c in enumerate(self.ninja_clients):
                uid = getattr(c, "tg_user_id", "?")
                name = self.ninja_names[i] if i < len(self.ninja_names) else "Ninja"
                try:
                    sess = StringSession.save(c.session)
                    lines.append(f"# {name} | id={uid}\n{sess}\n")
                except Exception as e:
                    lines.append(f"# {name} | id={uid} | ERROR: {e}\n")

            body = "\n".join(lines)
            try:
                bio = io.BytesIO(body.encode("utf-8"))
                bio.name = "ninja_sessions_all.txt"
                await self.bot_client.send_file(
                    Config.OWNER_ID,
                    bio,
                    caption=f"🔑 **All Ninja Sessions** ({len(self.ninja_clients)})",
                    parse_mode="markdown",
                )
                if not event.is_private:
                    await event.reply("📁 Session file DM ပို့ပြီး")
            except Exception as e:
                await event.reply(f"❌ Send failed: `{e}`")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/addauto(?:@\w+)?(?:\s+([\s\S]+))?$"
        ))
        async def addauto_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            raw = event.pattern_match.group(1) or ""
            r = await event.get_reply_message()
            if r and r.text:
                raw = raw + "\n" + r.text
            if not raw.strip():
                return await event.reply(
                    "⚠️ **Usage**\n"
                    "• `/addauto 123456789 987654321`\n"
                    "• သို့မဟုတ် ID list ကို reply → `/addauto`\n"
                    "Append mode (အရင် IDs မပျောက်)။",
                    parse_mode="markdown")
            ids = set()
            for tok in re.split(r"[\s,;]+", raw):
                tok = tok.strip()
                if not tok:
                    continue
                m = re.match(r"^(\d{5,})$", tok)
                if m:
                    ids.add(int(m.group(1)))
            if not ids:
                return await event.reply("❌ No valid IDs found.")
            before = len(self.auto_catch_ids)
            self.auto_catch_ids.update(ids)
            added = len(self.auto_catch_ids) - before
            await self._save_auto_catch_ids()
            in_pool = ids & self.ninja_ids
            not_in_pool = ids - self.ninja_ids
            msg = (
                f"✅ **Auto-Catch List Updated**\n"
                f"📥 Requested: `{len(ids)}`\n"
                f"➕ New added: `{added}`\n"
                f"🎯 Total now: `{len(self.auto_catch_ids)}`\n"
                f"✅ In pool: `{len(in_pool)}`\n"
            )
            if not_in_pool:
                preview = ", ".join(str(x) for x in list(not_in_pool)[:10])
                msg += f"⚠️ Not loaded ({len(not_in_pool)}): `{preview}`\n"
            await event.reply(msg, parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(pattern=r"^/listauto(?:@\w+)?$"))
        async def listauto_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.auto_catch_ids:
                return await event.reply("📭 Auto-catch list empty.")
            lines = [f"🎯 **Auto-Catch List ({len(self.auto_catch_ids)})**"]
            for i, uid in enumerate(sorted(self.auto_catch_ids)):
                tag = "✅" if uid in self.ninja_ids else "⚠️(not loaded)"
                lines.append(f"  {i+1}. `{uid}` {tag}")
            await event.reply("\n".join(lines), parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/removeauto(?:@\w+)?(?:\s+([\s\S]+))?$"
        ))
        async def removeauto_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            raw = event.pattern_match.group(1) or ""
            r = await event.get_reply_message()
            if r and r.text:
                raw = raw + "\n" + r.text
            if not raw.strip():
                return await event.reply("⚠️ Usage: `/removeauto 123 456`")
            ids = set()
            for tok in re.split(r"[\s,;]+", raw):
                tok = tok.strip()
                if not tok:
                    continue
                m = re.match(r"^(\d{5,})$", tok)
                if m:
                    ids.add(int(m.group(1)))
            if not ids:
                return await event.reply("❌ No valid IDs.")
            removed = self.auto_catch_ids & ids
            self.auto_catch_ids -= ids
            await self._save_auto_catch_ids()
            await event.reply(
                f"🗑️ Removed `{len(removed)}` · Total left `{len(self.auto_catch_ids)}`",
                parse_mode="markdown",
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/clearauto(?:@\w+)?$"))
        async def clearauto_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            n = len(self.auto_catch_ids)
            self.auto_catch_ids.clear()
            await self._save_auto_catch_ids()
            await event.reply(f"🗑️ Cleared {n} auto-catch IDs.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/autoninja(?:@\w+)?$"))
        async def autoninja_status(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await event.reply(
                f"🥷 **AUTO-CATCH CONFIG**\n"
                f"🆕 New Spawn Bot: `{Config.SPAWN_BOT_NEW_ID}`\n"
                f"🥷 Old Spawn Bot (Hint): `{Config.SPAWN_BOT_OLD_ID}`\n"
                f"📍 Groups: `{len(Config.SPAM_GROUPS)}`\n"
                f"👥 Pool: `{len(self.ninja_clients)}`\n"
                f"🎯 Auto-Catch List: `{len(self.auto_catch_ids)}`\n"
                f"✍️ /w Reply Count: `{Config.W_REPLY_COUNT}`\n"
                f"⏱️ /w Delay: `{Config.W_REPLY_DELAY_MIN}-{Config.W_REPLY_DELAY_MAX}s`\n"
                f"🚫 Ignored Emojis: `{' '.join(Config.NINJA_IGNORED_EMOJIS)}`",
                parse_mode="markdown",
            )

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/startspam(?:@\w+)?(?:\s+(@?\w+))?$"
        ))
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
                f"🎯 START SPAM ON → @{target} · {n} workers · {Config.START_SPAM_INTERVAL}s interval"
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/stopspam(?:@\w+)?$"))
        async def stopspam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            if not self.start_spam_active:
                return await event.reply("ℹ️ Not running.")
            target = self.start_spam_target
            n = await self.stop_start_spam()
            await event.reply(f"🛑 START SPAM OFF · @{target} · stopped {n}")

        @self.bot_client.on(events.NewMessage(pattern=r"^/spamstatus(?:@\w+)?$"))
        async def spamstatus_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            if self.start_spam_active:
                await event.reply(f"🎯 ON · @{self.start_spam_target} · {len(self.start_spam_tasks)} workers")
            else:
                await event.reply("🎯 OFF")

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
                        e = await self.bot_client.get_entity(uname)
                        target_chat = e.id
                    except Exception as ex:
                        return await event.reply(f"❌ {ex}")
                else:
                    return await event.reply("⚠️ Usage: /adm | /adm -100xxx | /adm @group")
            else:
                if event.is_private:
                    return await event.reply("⚠️ Usage in DM: /adm -100xxx")
                target_chat = event.chat_id

            if not target_chat:
                return await event.reply("❌ No target.")
            if not self.ninja_clients:
                return await event.reply("❌ Empty pool.")

            try:
                p = await self.bot_client.get_permissions(target_chat, "me")
            except Exception as e:
                return await event.reply(f"❌ {e}")
            if not (p and getattr(p, "is_admin", False)):
                return await event.reply("❌ Bot not admin.")
            if not (getattr(p, "add_admins", False) or getattr(p, "is_creator", False)):
                return await event.reply("❌ No Add Admins perm.")

            status = await event.reply(f"⏳ Promoting {len(self.ninja_clients)} ninjas in `{target_chat}` (no perms)...")
            promoted = already = failed = 0
            for c in self.ninja_clients:
                try:
                    uid = getattr(c, "tg_user_id", None)
                    if not uid:
                        me = await c.get_me()
                        uid = me.id
                        c.tg_user_id = uid
                    np = await self.bot_client.get_permissions(target_chat, uid)
                    if np and getattr(np, "is_admin", False):
                        already += 1
                        continue
                    await self.bot_client.edit_admin(
                        target_chat, uid,
                        change_info=False,
                        post_messages=False,
                        edit_messages=False,
                        delete_messages=False,
                        ban_users=False,
                        invite_users=False,
                        pin_messages=False,
                        add_admins=False,
                        anonymous=False,
                        manage_call=False,
                        other=True,
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
                f"✅ `/adm` `{target_chat}` · promoted={promoted} already={already} failed={failed}\n"
                f"🔒 All ninjas are admin with **NO permissions**."
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^ဖာသည်မသား$"))
        async def taunt(event):
            if event.sender_id != Config.OWNER_ID:
                return
            try:
                await event.delete()
            except Exception:
                pass
            r = await event.get_reply_message()
            if not r:
                return await event.reply("❌ Reply to a target.")
            t = await r.get_sender()
            if not t or t.id == Config.OWNER_ID:
                return
            cid = event.chat_id
            tid = t.id
            first = getattr(t, "first_name", "") or ""
            last = getattr(t, "last_name", "") or ""
            tname = f"{first} {last}".strip() or "Target"

            admins = await self._get_admin_clients(cid)
            if not admins:
                return await event.reply("⚠️ No ninja admin here.")

            mention = self.format_mention(tid, tname)
            try:
                await self.bot_client.delete_messages(cid, [r.id])
            except Exception:
                pass
            await self._add_taunt_target(cid, tid)
            c = random.choice(admins)
            phrase = await self.get_next_phrase(cid)
            try:
                await c.send_message(cid, f"{mention} {phrase}", parse_mode="html")
            except Exception as e:
                logger.error(f"Taunt: {e}")
            await event.reply(f"✅ Taunt enabled for {mention}", parse_mode="html")

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
                r = await event.get_reply_message()
                t = await r.get_sender()
                await self._remove_taunt_target(cid, t.id)
                await event.reply("✅ Removed")

        @self.bot_client.on(events.NewMessage(pattern=r"^/clear_taunts(?:@\w+)?(?:\s+(-?\d+))?$"))
        async def clear_taunts(event):
            if event.sender_id != Config.OWNER_ID:
                return
            cid = int(event.pattern_match.group(1)) if event.pattern_match.group(1) else event.chat_id
            await self._clear_taunt_targets(cid)
            await event.reply("🧹 Cleared.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/spam(?:@\w+)?$"))
        async def spam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.ninja_clients:
                return await event.reply("❌ Ninja pool empty.")
            await event.reply("⏳ Populating dialogs + warming cache...")
            await self._start_spam_loop(Config.SPAM_GROUPS)
            await event.reply(
                f"🗣️ Spam started on {len(Config.SPAM_GROUPS)} groups.\n"
                f"⏱️ Chat interval: `{Config.SPAM_GROUP_INTERVAL}s`\n"
                f"🛡️ Ninja cooldown: `{Config.SPAM_NINJA_COOLDOWN}s`\n"
                f"📊 Rate: ~`{len(Config.SPAM_GROUPS) * 60 / Config.SPAM_GROUP_INTERVAL:.0f}` msg/min total",
                parse_mode="markdown",
            )

        # ============================================================
        # 💀 /kill
        # ============================================================
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/kill(?:@\w+)?(?:\s+([\s\S]+))?$"
        ))
        async def kill_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            if not self.ninja_clients:
                return await event.reply("❌ Ninja pool empty.")
            if not self.kill_phrases:
                await self._load_kill_phrases()

            raw = event.pattern_match.group(1) or ""
            chat_id = event.chat_id if not event.is_private else None
            target_ids: Set[int] = set()

            if event.is_reply:
                try:
                    r = await event.get_reply_message()
                    s = await r.get_sender()
                    if s:
                        target_ids.add(s.id)
                except Exception:
                    pass

            for tok in re.split(r"[\s,;]+", raw):
                tok = tok.strip()
                if not tok:
                    continue
                if re.match(r"^-100\d+$", tok):
                    chat_id = int(tok)
                elif re.match(r"^\d{5,}$", tok):
                    target_ids.add(int(tok))

            if not target_ids:
                return await event.reply(
                    "⚠️ **Usage**\n"
                    "• `/kill <user_id> [user_id2 ...] [chat_id]`\n"
                    "• reply → `/kill`",
                    parse_mode="markdown",
                )
            if not chat_id:
                return await event.reply("❌ chat_id မသိပါ။ Group ထဲမှာ ရိုက်ပါ။")

            started = 0
            for uid in target_ids:
                tname = await self._get_full_name(uid)
                n = await self.start_kill(chat_id, uid, tname)
                if n:
                    started += 1
            await event.reply(
                f"💀 **KILL SWARM STARTED**\n"
                f"🎯 Targets: `{started}`\n"
                f"📍 Chat: `{chat_id}`\n"
                f"🥷 Ninjas: `{len(self.ninja_clients)}`\n"
                f"⏱️ Interval: `{Config.KILL_INTERVAL}s` / ninja\n"
                f"📜 Phrases: `{len(self.kill_phrases)}`",
                parse_mode="markdown",
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/killstop(?:@\w+)?$"))
        async def killstop_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            n = self.stop_all_kills()
            await event.reply(f"🛑 Kill stopped · {n} target(s)")

        @self.bot_client.on(events.NewMessage(pattern=r"^/killstatus(?:@\w+)?$"))
        async def killstatus_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            active = [k for k, v in self.kill_tasks.items() if v]
            if not active:
                return await event.reply("💀 No active kill.")
            lines = [f"💀 **Active Kills ({len(active)})**"]
            for cid, uid in active:
                name = await self._get_full_name(uid)
                lines.append(f"  • chat `{cid}` → `{uid}` ({name})")
            await event.reply("\n".join(lines), parse_mode="markdown")

        # ============================================================
        # 📜 BULK KILL PHRASES
        # ============================================================
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/addkillphrase(?:@\w+)?(?:\s+([\s\S]+))?$"
        ))
        async def addkillphrase_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            raw = event.pattern_match.group(1) or ""
            if event.is_reply:
                r = await event.get_reply_message()
                if r and r.text:
                    raw = (raw + "\n" + r.text).strip()
            if not raw.strip():
                return await event.reply(
                    "⚠️ **Usage**\n"
                    "• Reply → `/addkillphrase`\n"
                    "• inline multiline",
                    parse_mode="markdown",
                )
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            if not lines:
                return await event.reply("❌ Empty.")
            existing = set(self.kill_phrases)
            new_lines = [ln for ln in lines if ln not in existing]
            self.kill_phrases.extend(new_lines)
            await self._save_kill_phrases()
            await event.reply(
                f"✅ Added `{len(new_lines)}` phrase(s) · "
                f"skipped `{len(lines)-len(new_lines)}` dup · "
                f"Total `{len(self.kill_phrases)}`",
                parse_mode="markdown",
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/listkillphrase(?:@\w+)?$"))
        async def listkillphrase_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.kill_phrases:
                return await event.reply("📭 Empty.")
            cap = 60
            lines = [f"📜 **Kill Phrases ({len(self.kill_phrases)})**"]
            for i, p in enumerate(self.kill_phrases[:cap], 1):
                lines.append(f"{i}. {p}")
            if len(self.kill_phrases) > cap:
                lines.append(f"… +{len(self.kill_phrases)-cap} more")
            await event.reply("\n".join(lines), parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(pattern=r"^/clearkillphrase(?:@\w+)?$"))
        async def clearkillphrase_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            n = len(self.kill_phrases)
            self.kill_phrases = list(Config.DEFAULT_KILL_PHRASES)
            await self._save_kill_phrases()
            await event.reply(
                f"🗑️ Cleared `{n}` · reset to `{len(self.kill_phrases)}` defaults",
                parse_mode="markdown",
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop(?:@\w+)?)$"))
        async def stop_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            cid = event.chat_id
            stopped = 0
            for k in list(self.ninja_spam_tasks.keys()):
                if cid in k or event.sender_id == Config.OWNER_ID:
                    self.ninja_spam_tasks[k] = False
                    stopped += 1
            kill_stopped = self.stop_all_kills()
            await event.reply(
                f"🛑 Spam stopped: `{stopped}` · Kill stopped: `{kill_stopped}`",
                parse_mode="markdown",
            )

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
            self.chat_admin_cache.clear()
            self.dialogs_populated.clear()
            try:
                chat = await clients[0].get_entity(link)
                await event.reply(f"✅ Joined `{chat.title}` ({success} clients). ID: `{chat.id}`")
            except Exception:
                await event.reply(f"✅ Joined ({success} clients).")

        @self.bot_client.on(events.NewMessage(pattern=r"^/rewarm(?:@\w+)?$"))
        async def rewarm_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            status = await event.reply(
                f"🔥 **RE-WARMING DIALOGS**\n"
                f"Populating dialogs for {len(self.ninja_clients)} ninjas...\n"
                f"This may take 1-2 minutes."
            )
            self.dialogs_populated.clear()
            n_bl = len(self.ninja_chat_blacklist)
            self.ninja_chat_blacklist.clear()
            ok, fail = await self._warm_entities(Config.SPAM_GROUPS)
            await status.edit(
                f"✅ **Dialogs populated**\n"
                f"👥 Ninjas: `{len(self.ninja_clients)}`\n"
                f"📍 Groups: `{len(Config.SPAM_GROUPS)}`\n"
                f"✔️ OK: `{ok}`\n"
                f"✖️ Fail: `{fail}`\n"
                f"🧹 Blacklist cleared: `{n_bl}`\n\n"
                f"💡 `/spam` ပြန်ရိုက်ပါ"
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/status(?:@\w+)?$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            taunts = sum(len(s) for s in self.delete_and_taunt_targets.values())
            ss = f"ON → @{self.start_spam_target}" if self.start_spam_active else "OFF"
            spam_active = sum(1 for v in self.ninja_spam_tasks.values() if v)
            now = time.monotonic()
            flooded = sum(1 for uid, t in self.spam_flood_until.items() if t > now)
            bl = sum(1 for t in self.ninja_chat_blacklist.values() if t > now)
            kills = sum(1 for v in self.kill_tasks.values() if v)
            await event.reply(
                f"📊 **Status**\n"
                f"🤖 Pool: `{len(self.ninja_clients)}`\n"
                f"🎯 Auto-Catch: `{len(self.auto_catch_ids)}`\n"
                f"⛔ Flooded: `{flooded}`\n"
                f"🚫 Ninja×Chat blacklist: `{bl}`\n"
                f"🎯 /startspam: {ss}\n"
                f"🗣️ /spam loops: `{spam_active}`\n"
                f"💀 Active kills: `{kills}`\n"
                f"📜 Kill phrases: `{len(self.kill_phrases)}`\n"
                f"⏱️ Chat interval: `{Config.SPAM_GROUP_INTERVAL}s`\n"
                f"🛡️ Ninja cooldown: `{Config.SPAM_NINJA_COOLDOWN}s`\n"
                f"🔥 Dialogs populated: `{len(self.dialogs_populated)}`\n"
                f"👹 Taunts: `{taunts}`",
                parse_mode="markdown",
            )

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
                        t = await event.get_sender()
                        first = getattr(t, "first_name", "") or ""
                        last = getattr(t, "last_name", "") or ""
                        name = f"{first} {last}".strip() or "Target"
                    except Exception:
                        name = "Target"
                    asyncio.create_task(self._taunt_user(cid, sid, event.id, name))

    # ============================================================
    # START / STOP
    # ============================================================
    async def start(self):
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        me = await self.bot_client.get_me()
        self.bot_id = me.id
        logger.info(f"🤖 Bot started: @{me.username} ({self.bot_id})")

        await self._load_auto_catch_ids()
        await self._load_kill_phrases()

        await self.load_ninja_pools()
        await self.load_taunt_targets()

        logger.info("🔥 Auto-populating dialogs on startup...")
        await self._warm_entities(Config.SPAM_GROUPS)

        asyncio.create_task(self.preload_admin_caches())
        threading.Thread(target=run_flask, daemon=True).start()
        await self.bot_client.run_until_disconnected()

    async def stop(self):
        if self.start_spam_active:
            await self.stop_start_spam()
        self.stop_all_kills()
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
