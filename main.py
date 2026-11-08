#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Ninja System — /spam + /startspam + /go + /adm + dynamic groups

FEATURES:
- /addgroup /listgroups /removegroup /cleargroups   (max 8)
- Auto-invite ninjas (slow mode, needs main bot admin + Invite Users)
- Silent expected errors (no owner DM spam)
- Slow pace to prevent flood
"""

import asyncio, io, logging, os, random, re, sys, threading, time
from typing import Dict, List, Optional, Set, Tuple

from flask import Flask
from motor.motor_asyncio import AsyncIOMotorClient
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

    SPAM_GROUPS_MAX = 8
    SPAM_GROUPS_MIN = 1

    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    MAX_RETRIES = 3

    # /startspam
    START_SPAM_INTERVAL = 18000
    START_SPAM_MIN_DELAY = 5
    START_SPAM_MAX_DELAY = 15
    START_SPAM_JITTER = 0.10

    # Spam pace (နှေးနှေး — flood မဖြစ်အောင်)
    SPAM_GROUP_INTERVAL = 2.5
    SPAM_NINJA_COOLDOWN = 2.0
    SPAM_JITTER = 0.25
    SPAM_GLOBAL_DELAY = 0.8

    BLACKLIST_PRIVATE_SEC = 3600
    BLACKLIST_ENTITY_SEC  = 300

    # Ninja auto-skip
    NINJA_MAX_ERRORS = 5
    NINJA_DEAD_TIME = 300

    # Auto-invite
    INVITE_JOIN_DELAY_MIN = 2.5
    INVITE_JOIN_DELAY_MAX = 4.5
    INVITE_LINK_CACHE_SEC = 3600
    INVITE_AUTO_ON_SPAM = True

    SPAM_TEXTS = [
        " @FLASH_SPAM_Bot | @fuckyourwifey_bot | @Imjustkidding_bot | @GodMorgan_robot | @enforcermorgan_11robot | fqcawqAaaaafbBsqqlqoျဘျဆငငေတငတုsahqBwqiqoaj#!11&$1(!92929*@*@>>",
        " @GodMorgan_robot | @Imjustkidding_bot | qwertyuiopASDFGHJKLzxcvbnm123rkrkeekekek4567890!@#$%",
        " @enforcermorgan_11robot | fqcawqAaaaafbBsqqlqo ျဘျဆငငေejejejejeejwjjeejတငတု 1234567890",
        " @FLASH_SPAM_Bot | @fuckyourwifey_bot | spam text alternative hshahahahahaahahajajsjsjsjsjsjsjsjsjversion here",
    ]


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


_error_dedup: Dict[str, float] = {}
_ERROR_DEDUP_SEC = 30


async def report_error(bot_client, context: str, exc: Exception, extra: str = ""):
    try:
        key = f"{context}:{type(exc).__name__}"
        now = time.time()
        if now - _error_dedup.get(key, 0) < _ERROR_DEDUP_SEC:
            return
        _error_dedup[key] = now

        # Expected errors → log only, no owner DM
        silent_types = (
            UserNotParticipantError,
            ChannelPrivateError,
            ChatWriteForbiddenError,
            UserBannedInChannelError,
            PeerIdInvalidError,
            ValueError,
        )
        if isinstance(exc, silent_types):
            logger.debug(f"🔇 suppressed {context}: {type(exc).__name__}: {exc}")
            return

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
    def ninja_col(self): return self.db["ninja_col"]

    @property
    def groups_col(self): return self.db["spam_groups_col"]


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

        # Spam groups (dynamic)
        self.spam_groups: List[int] = []

        self.ninja_spam_tasks: Dict[Tuple[int, ...], bool] = {}

        self.spam_ninja_last: Dict[int, float] = {}
        self.spam_chat_last: Dict[int, float] = {}
        self.spam_flood_until: Dict[int, float] = {}

        self.ninja_chat_blacklist: Dict[Tuple[int, int], float] = {}

        # Ninja skip-on-error
        self.ninja_error_count: Dict[int, int] = {}
        self.ninja_dead_until: Dict[int, float] = {}

        self.dialogs_populated: Set[int] = set()

        # Auto-invite cache
        self.invite_links: Dict[int, Tuple[str, float]] = {}

        self.start_spam_tasks: Dict[int, asyncio.Task] = {}
        self.start_spam_target: Optional[str] = None
        self.start_spam_active: bool = False

        self._register_handlers()

    async def _report(self, context: str, exc: Exception, extra: str = ""):
        await report_error(self.bot_client, context, exc, extra)

    # ============================================================
    # SPAM GROUPS (DB)
    # ============================================================
    async def _load_spam_groups(self):
        doc = await self.db.groups_col.find_one({"_id": "groups"})
        if doc:
            ids = [int(x) for x in doc.get("ids", [])]
            self.spam_groups = ids[: Config.SPAM_GROUPS_MAX]
        else:
            self.spam_groups = []
        logger.info(f"📍 Spam groups loaded: {len(self.spam_groups)} → {self.spam_groups}")

    async def _save_spam_groups(self):
        await self.db.groups_col.update_one(
            {"_id": "groups"},
            {"$set": {"ids": self.spam_groups}},
            upsert=True,
        )

    # ============================================================
    # AUTO-PROMOTE (on join)
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
                    f"✅ Auto-Promote `{cid}` · promoted={promoted} already={already} failed={failed}"
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
    # NINJA HANDLERS (only join)
    # ============================================================
    def _register_ninja_handlers(self, client):
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
    def _find_ninja_by_id(self, uid):
        for i, c in enumerate(self.ninja_clients):
            if getattr(c, "tg_user_id", None) == uid:
                return i, c
        return None, None

    # ============================================================
    # NINJA ERROR TRACKING
    # ============================================================
    def _mark_ninja_ok(self, uid):
        if uid in self.ninja_error_count:
            self.ninja_error_count[uid] = 0

    def _mark_ninja_error(self, uid):
        try:
            uid = int(uid)
        except Exception:
            return
        self.ninja_error_count[uid] = self.ninja_error_count.get(uid, 0) + 1
        if self.ninja_error_count[uid] >= Config.NINJA_MAX_ERRORS:
            self.ninja_dead_until[uid] = time.monotonic() + Config.NINJA_DEAD_TIME
            self.ninja_error_count[uid] = 0
            logger.warning(
                f"💀 Ninja {uid} → dead for {Config.NINJA_DEAD_TIME}s (too many errors)"
            )

    # ============================================================
    # ENTITY FIX
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
        if not chat_ids:
            logger.info("🔥 No groups to warm.")
            return 0, 0
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
                except (UserNotParticipantError, ChannelPrivateError):
                    fail += 1
                except (PeerIdInvalidError, ValueError) as e:
                    logger.debug(f"🔇 warm [{uid}] {cid}: {type(e).__name__}")
                    fail += 1
                except Exception as e:
                    logger.debug(f"🔇 warm [{uid}] {cid}: {type(e).__name__}: {e}")
                    fail += 1
                    self._mark_ninja_error(uid)
                await asyncio.sleep(0.1)
        logger.info(f"🔥 Entity cache done · ok={ok} fail={fail}")
        return ok, fail

    # ============================================================
    # AUTO-INVITE
    # ============================================================
    async def _get_invite_link(self, cid: int) -> Optional[str]:
        now = time.time()
        cached = self.invite_links.get(cid)
        if cached and now < cached[1]:
            return cached[0]

        from telethon.tl.functions.messages import (
            ExportChatInviteRequest,
            GetExportedChatInvitesRequest,
        )
        link = None

        try:
            r = await self.bot_client(ExportChatInviteRequest(cid))
            if r and getattr(r, "link", None):
                link = r.link
                logger.info(f"🔗 invite link created for {cid}")
        except errors.rpcerrorlist.ChatAdminRequiredError:
            logger.debug(f"🔇 no admin rights to create link {cid}")
        except FloodWaitError as e:
            logger.debug(f"🔇 flood on link create {cid}: {e.seconds}s")
        except Exception as e:
            logger.debug(f"🔇 link create fail {cid}: {type(e).__name__}")

        if not link:
            try:
                me = await self.bot_client.get_me()
                peer = await self.bot_client.get_input_entity(cid)
                r = await self.bot_client(GetExportedChatInvitesRequest(
                    peer=peer, admin_id=me.id, limit=1,
                ))
                if r and getattr(r, "invites", None):
                    link = r.invites[0].link
            except Exception as e:
                logger.debug(f"🔇 existing link fail {cid}: {type(e).__name__}")

        if link:
            self.invite_links[cid] = (link, now + Config.INVITE_LINK_CACHE_SEC)
        return link

    async def _ninja_in_chat(self, ninja, cid: int) -> bool:
        try:
            await ninja.get_permissions(cid, "me")
            return True
        except (UserNotParticipantError, ChannelPrivateError):
            return False
        except (PeerIdInvalidError, ValueError):
            try:
                await ninja.get_input_entity(cid)
                return True
            except Exception:
                return False
        except Exception:
            return False

    async def _ensure_ninja_in_chat(self, ninja, cid: int, invite_link: str) -> bool:
        uid = getattr(ninja, "tg_user_id", "?")

        if await self._ninja_in_chat(ninja, cid):
            return True
        if not invite_link:
            return False

        h = None
        if "joinchat/" in invite_link:
            h = invite_link.split("joinchat/")[1].split("?")[0]
        elif "+" in invite_link:
            h = invite_link.split("+")[1].split("?")[0]
        if not h:
            return False

        try:
            try:
                await asyncio.wait_for(
                    ninja(ImportChatInviteRequest(h)), timeout=30
                )
                logger.info(f"🥷 [{uid}] joined {cid}")
                return True
            except errors.rpcerrorlist.UserAlreadyParticipantError:
                return True
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds + 5, 120))
                return False
            except Exception as e:
                logger.debug(f"🔇 [{uid}] join {cid}: {type(e).__name__}")
                return False
        except Exception:
            return False

    async def _auto_invite_ninjas(self, cid: int, silent: bool = True) -> Tuple[int, int]:
        link = await self._get_invite_link(cid)
        if not link:
            if not silent:
                logger.info(f"📭 no invite link for {cid} — skip auto-invite")
            return 0, len(self.ninja_clients)

        joined = skipped = 0
        for c in self.ninja_clients:
            if await self._ninja_in_chat(c, cid):
                skipped += 1
            else:
                if await self._ensure_ninja_in_chat(c, cid, link):
                    joined += 1
                else:
                    skipped += 1
            await asyncio.sleep(random.uniform(
                Config.INVITE_JOIN_DELAY_MIN,
                Config.INVITE_JOIN_DELAY_MAX,
            ))

        if joined > 0:
            logger.info(f"📨 {cid}: joined={joined} already={skipped}")
        return joined, skipped

    def _pick_ninja(self, cid: int, now: float) -> Optional[TelegramClient]:
        eligible = []
        for c in self.ninja_clients:
            uid = getattr(c, "tg_user_id", None)
            if not uid:
                continue
            if self.ninja_dead_until.get(uid, 0) > now:
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
            self._mark_ninja_ok(uid)
            return True

        except (ChannelPrivateError, ChatWriteForbiddenError,
                UserBannedInChannelError, UserNotParticipantError) as e:
            self.ninja_chat_blacklist[(uid, cid)] = (
                time.monotonic() + Config.BLACKLIST_PRIVATE_SEC
            )
            logger.warning(f"⛔ [{uid}→{cid}] {type(e).__name__} → blacklist 1h")
            self._mark_ninja_error(uid)
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
                self._mark_ninja_ok(uid)
                return True
            except (ChannelPrivateError, ChatWriteForbiddenError) as e2:
                self.ninja_chat_blacklist[(uid, cid)] = (
                    time.monotonic() + Config.BLACKLIST_PRIVATE_SEC
                )
                logger.warning(f"⛔ [{uid}→{cid}] {type(e2).__name__} → blacklist 1h")
                self._mark_ninja_error(uid)
                return False
            except Exception as retry_e:
                self.ninja_chat_blacklist[(uid, cid)] = (
                    time.monotonic() + Config.BLACKLIST_ENTITY_SEC
                )
                logger.error(f"❌ Retry failed [{uid}→{cid}]: {type(retry_e).__name__}: {retry_e}")
                self._mark_ninja_error(uid)
                return False

        except FloodWaitError:
            raise
        except Exception:
            self._mark_ninja_error(uid)
            raise

    async def _start_spam_loop(self, chat_ids):
        if not chat_ids:
            logger.warning("⚠️ No groups to spam.")
            return
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

        # Auto-invite before spam
        if Config.INVITE_AUTO_ON_SPAM:
            logger.info(f"📨 Auto-inviting ninjas to {len(chat_ids)} groups (slow mode)...")
            for cid in chat_ids:
                await self._auto_invite_ninjas(cid, silent=True)

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

    # ============================================================
    # COMMAND HANDLERS
    # ============================================================
    def _register_handlers(self):

        # ══════════════════════════════════════════════════════════
        # GROUP MANAGEMENT
        # ══════════════════════════════════════════════════════════
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/addgroup(?:@\w+)?(?:\s+(-?\d+))?$"
        ))
        async def addgroup_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            arg = event.pattern_match.group(1)
            raw = arg

            if not raw and event.is_reply:
                r = await event.get_reply_message()
                if r and r.text:
                    m = re.search(r"(-100\d{6,})", r.text)
                    if m:
                        raw = m.group(1)
                    else:
                        link_m = re.search(
                            r"(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)",
                            r.text
                        )
                        if link_m:
                            try:
                                ent = await self.bot_client.get_entity(link_m.group(0))
                                raw = str(ent.id)
                            except Exception as e:
                                return await event.reply(f"❌ Resolve failed: `{e}`")

            if not raw:
                return await event.reply(
                    "⚠️ **Usage**\n"
                    "• `/addgroup -1001234567890`\n"
                    "• Group link/ID ပါတဲ့ message ကို reply → `/addgroup`\n\n"
                    f"📊 Max: `{Config.SPAM_GROUPS_MAX}` · Min: `{Config.SPAM_GROUPS_MIN}`",
                    parse_mode="markdown",
                )

            try:
                cid = int(raw)
            except ValueError:
                return await event.reply("❌ Invalid ID.")

            if cid in self.spam_groups:
                return await event.reply(f"⚠️ Already added: `{cid}`", parse_mode="markdown")
            if len(self.spam_groups) >= Config.SPAM_GROUPS_MAX:
                return await event.reply(
                    f"❌ Max `{Config.SPAM_GROUPS_MAX}` groups reached.\n"
                    f"🗑️ `/removegroup <id>` နဲ့ အရင်ဖျက်ပါ။",
                    parse_mode="markdown",
                )

            self.spam_groups.append(cid)
            await self._save_spam_groups()

            title = "?"
            try:
                ent = await self.bot_client.get_entity(cid)
                title = getattr(ent, "title", "?")
            except Exception:
                pass

            await event.reply(
                f"✅ **Group added**\n"
                f"🆔 `{cid}`\n"
                f"📛 {title}\n"
                f"📊 Total: `{len(self.spam_groups)}/{Config.SPAM_GROUPS_MAX}`\n"
                f"📨 Auto-invite running in background...",
                parse_mode="markdown",
            )
            asyncio.create_task(self._auto_invite_ninjas(cid, silent=True))

        @self.bot_client.on(events.NewMessage(pattern=r"^/listgroups(?:@\w+)?$"))
        async def listgroups_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.spam_groups:
                return await event.reply(
                    "📭 No groups.\n💡 `/addgroup -100...`",
                    parse_mode="markdown",
                )
            lines = [f"📍 **Spam Groups ({len(self.spam_groups)}/{Config.SPAM_GROUPS_MAX})**"]
            for i, g in enumerate(self.spam_groups, 1):
                title = "?"
                try:
                    ent = await self.bot_client.get_entity(g)
                    title = getattr(ent, "title", "?")
                except Exception:
                    pass
                lines.append(f"  {i}. `{g}` — {title}")
            await event.reply("\n".join(lines), parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(
            pattern=r"^/removegroup(?:@\w+)?(?:\s+(-?\d+))?$"
        ))
        async def removegroup_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            arg = event.pattern_match.group(1)
            if not arg:
                return await event.reply(
                    "⚠️ Usage: `/removegroup -1001234567890`",
                    parse_mode="markdown",
                )
            cid = int(arg)
            if cid not in self.spam_groups:
                return await event.reply(f"❌ Not in list: `{cid}`", parse_mode="markdown")
            self.spam_groups.remove(cid)
            await self._save_spam_groups()
            await event.reply(
                f"🗑️ Removed `{cid}` · Total: `{len(self.spam_groups)}`",
                parse_mode="markdown",
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/cleargroups(?:@\w+)?$"))
        async def cleargroups_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            n = len(self.spam_groups)
            self.spam_groups.clear()
            await self._save_spam_groups()
            await event.reply(f"🗑️ Cleared `{n}` groups.", parse_mode="markdown")

        # ══════════════════════════════════════════════════════════
        # NINJA MANAGEMENT
        # ══════════════════════════════════════════════════════════
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
            now = time.monotonic()
            lines = [f"👥 **Ninja Pool ({len(self.ninja_clients)} loaded)**"]
            for i, (c, n) in enumerate(zip(self.ninja_clients, self.ninja_names)):
                try:
                    me = await c.get_me()
                    online += 1
                    full = f"{me.first_name or ''} {me.last_name or ''}".strip() or "No Name"
                    u = f"(@{me.username})" if me.username else ""
                    dead = " 💀DEAD" if self.ninja_dead_until.get(me.id, 0) > now else ""
                    lines.append(f"  {i+1}. **{full}** {u} (ID: `{me.id}`) ✅{dead}")
                except Exception:
                    lines.append(f"  {i+1}. **{n}** ❌")
            lines.append(f"\n📊 Online: {online}/{len(self.ninja_clients)}")
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
            self.dialogs_populated.discard(target_id)
            for k in list(self.ninja_chat_blacklist.keys()):
                if k[0] == target_id:
                    self.ninja_chat_blacklist.pop(k, None)
            self.ninja_dead_until.pop(target_id, None)
            self.ninja_error_count.pop(target_id, None)

            await event.reply(
                f"✅ Removed ninja\n"
                f"👤 Name: `{name}`\n"
                f"🆔 ID: `{target_id}`\n"
                f"👥 Pool left: `{len(self.ninja_clients)}`",
                parse_mode="markdown",
            )

        # ══════════════════════════════════════════════════════════
        # /s — StringSession
        # ══════════════════════════════════════════════════════════
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

        # ══════════════════════════════════════════════════════════
        # START SPAM
        # ══════════════════════════════════════════════════════════
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

        # ══════════════════════════════════════════════════════════
        # /adm
        # ══════════════════════════════════════════════════════════
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

        # ══════════════════════════════════════════════════════════
        # /spam
        # ══════════════════════════════════════════════════════════
        @self.bot_client.on(events.NewMessage(pattern=r"^/spam(?:@\w+)?$"))
        async def spam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.ninja_clients:
                return await event.reply("❌ Ninja pool empty.")
            if not self.spam_groups:
                return await event.reply(
                    "❌ No groups configured.\n"
                    "💡 `/addgroup -100...` နဲ့ အရင်ထည့်ပါ။",
                    parse_mode="markdown",
                )
            await event.reply("⏳ Auto-invite + warming cache...")
            groups = list(self.spam_groups)
            await self._start_spam_loop(groups)
            await event.reply(
                f"🗣️ Spam started on `{len(groups)}` groups.\n"
                f"⏱️ Chat interval: `{Config.SPAM_GROUP_INTERVAL}s`\n"
                f"🛡️ Ninja cooldown: `{Config.SPAM_NINJA_COOLDOWN}s`\n"
                f"📊 Rate: ~`{len(groups) * 60 / Config.SPAM_GROUP_INTERVAL:.0f}` msg/min total",
                parse_mode="markdown",
            )

        # ══════════════════════════════════════════════════════════
        # /invite
        # ══════════════════════════════════════════════════════════
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/invite(?:@\w+)?(?:\s+(-?\d+))?$"
        ))
        async def invite_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            arg = event.pattern_match.group(1)
            cid = int(arg) if arg else (None if event.is_private else event.chat_id)
            if not cid:
                return await event.reply("⚠️ Usage: `/invite -100xxx`")
            status = await event.reply(f"📨 Inviting ninjas to `{cid}` (slow)...")
            j, s = await self._auto_invite_ninjas(cid, silent=False)
            await status.edit(
                f"✅ joined=`{j}` already=`{s}` · total=`{len(self.ninja_clients)}`"
            )

        # ══════════════════════════════════════════════════════════
        # STOP ALL
        # ══════════════════════════════════════════════════════════
        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop(?:@\w+)?)$"))
        async def stop_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            stopped = 0
            for k in list(self.ninja_spam_tasks.keys()):
                if self.ninja_spam_tasks[k]:
                    self.ninja_spam_tasks[k] = False
                    stopped += 1
            await event.reply(
                f"🛑 Spam loops stopped: `{stopped}`",
                parse_mode="markdown",
            )

        # ══════════════════════════════════════════════════════════
        # /go
        # ══════════════════════════════════════════════════════════
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
            await event.reply(f"⏳ Joining with {len(clients)} clients (slow mode)...")
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
                    logger.debug(f"🔇 join: {e}")
                await asyncio.sleep(random.uniform(
                    Config.INVITE_JOIN_DELAY_MIN,
                    Config.INVITE_JOIN_DELAY_MAX,
                ))
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
            if not self.spam_groups:
                return await event.reply("❌ No groups configured.")
            status = await event.reply(
                f"🔥 **RE-WARMING + AUTO-INVITE**\n"
                f"👥 Ninjas: {len(self.ninja_clients)}\n"
                f"📍 Groups: {len(self.spam_groups)}\n"
                f"⏳ Slow mode (2.5–4.5s/join)..."
            )
            self.dialogs_populated.clear()
            self.ninja_chat_blacklist.clear()
            self.invite_links.clear()

            inv_j = inv_s = 0
            for cid in self.spam_groups:
                j, s = await self._auto_invite_ninjas(cid, silent=True)
                inv_j += j
                inv_s += s

            ok, fail = await self._warm_entities(self.spam_groups)
            await status.edit(
                f"✅ **Done**\n"
                f"📨 Joined: `{inv_j}` · Already: `{inv_s}`\n"
                f"✔️ OK: `{ok}` · ✖️ Fail: `{fail}`\n\n"
                f"💡 `/spam` ပြန်ရိုက်ပါ"
            )

        @self.bot_client.on(events.NewMessage(pattern=r"^/status(?:@\w+)?$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            ss = f"ON → @{self.start_spam_target}" if self.start_spam_active else "OFF"
            spam_active = sum(1 for v in self.ninja_spam_tasks.values() if v)
            now = time.monotonic()
            flooded = sum(1 for uid, t in self.spam_flood_until.items() if t > now)
            bl = sum(1 for t in self.ninja_chat_blacklist.values() if t > now)
            dead = sum(1 for t in self.ninja_dead_until.values() if t > now)
            await event.reply(
                f"📊 **Status**\n"
                f"🤖 Pool: `{len(self.ninja_clients)}`\n"
                f"💀 Dead ninjas: `{dead}`\n"
                f"📍 Spam groups: `{len(self.spam_groups)}/{Config.SPAM_GROUPS_MAX}`\n"
                f"⛔ Flooded: `{flooded}`\n"
                f"🚫 Ninja×Chat blacklist: `{bl}`\n"
                f"🎯 /startspam: {ss}\n"
                f"🗣️ /spam loops: `{spam_active}`\n"
                f"⏱️ Chat interval: `{Config.SPAM_GROUP_INTERVAL}s`\n"
                f"🛡️ Ninja cooldown: `{Config.SPAM_NINJA_COOLDOWN}s`\n"
                f"🔥 Dialogs populated: `{len(self.dialogs_populated)}`",
                parse_mode="markdown",
            )

    # ============================================================
    # START / STOP
    # ============================================================
    async def start(self):
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        me = await self.bot_client.get_me()
        self.bot_id = me.id
        logger.info(f"🤖 Bot started: @{me.username} ({self.bot_id})")

        await self._load_spam_groups()
        await self.load_ninja_pools()

        if self.spam_groups:
            logger.info("🔥 Auto-populating dialogs on startup...")
            await self._warm_entities(self.spam_groups)
        else:
            logger.info("📍 No spam groups yet. Use /addgroup in bot DM.")

        threading.Thread(target=run_flask, daemon=True).start()
        await self.bot_client.run_until_disconnected()

    async def stop(self):
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
