#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sovereign Ninja (clean · flood-safe)
- Ninjas work for /spam (flood-safe scheduler, catch-ninja priority)
- Auto-catch on SPAM_GROUPS: only IDs in catch_list forward to Hint Bot DM
- /setcatch (bulk add · append mode · persistent)
- /warmup (all ninjas /start hint bot)
- Flood tracking per client + spawn-priority pause
- Flask health check
"""

import asyncio, io, logging, os, random, re, sys, threading, time
from datetime import datetime, timedelta
from typing import Dict, List, Set

import pytz
from flask import Flask
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, OperationFailure
from telethon import TelegramClient, events, errors
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest


# ══════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════
class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "7693106830"))
    MONGO_URI = os.getenv(
        "MONGO_URI",
        "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/"
        "?appName=Cluster0&tlsAllowInvalidCertificates=true")
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN",
                          "8824002850:AAGPtl7M0dw_gDVEZNxM3xxrYQazKvO5FKo")

    # 📢 7 spam groups
    SPAM_GROUPS = [
        -1004381473883,
        -1003836488351,
        -1003733625547,
        -1004358425408,
        # TODO: သင့်ရဲ့ group 3 ခု ထပ်ထည့်ပါ
        # -100xxxxxxxxxx,
        # -100xxxxxxxxxx,
        # -100xxxxxxxxxx,
    ]

    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yangon"))
    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    MAX_RETRIES = 3

    # ── 🎮 Game Bot (spawn source) ─────────────────────────────
    SPAWN_GAME_BOT_ID = 6157455819

    # ── 🥷 Hint Bot (external · we only /start it) ─────────────
    SPAWN_HINT_BOT_ID = 8999491734

    # ── Auto-Catch ──────────────────────────────────────────────
    # (Catch ninja pool is DB-managed via /setcatch — NOT hardcoded)
    NINJA_PICK_COUNT = 5          # per spawn → how many to pick
    NINJA_W_DELAY_MIN = 3.0
    NINJA_W_DELAY_MAX = 4.0
    NINJA_WHITELIST_EMOJIS = ["🔵", "🟣", "🟠"]
    SPAWN_PHRASES = (
        "A CHARACTER HAS SPAWNED",
        "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ",
        "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ ɪɴ ᴛʜᴇ ᴄʜᴀᴛ",
    )

    # ── 🛡️ Flood-Safe Spam Timing ──────────────────────────────
    # 7 groups × 38 ninjas အတွက် တွက်ချက်ပြီး set ထားတယ်
    #
    # Target: 1 msg/group/20s → 21 msg/min (7 groups)
    # 38 ninjas → ~0.55 msg/ninja/min → 1 per ~110s per ninja
    # Telegram user flood threshold ≈ 1 msg/3s per chat (safe range)
    SPAM_GROUP_INTERVAL = 20      # target sec between msgs per group
    SPAM_GLOBAL_DELAY = 1.0       # min gap between any 2 sends
    SPAM_NINJA_COOLDOWN = 30      # min sec between 2 msgs from same ninja
    SPAM_CATCH_COOLDOWN = 90      # catch ninjas get longer cooldown
    SPAM_FLOOD_DEFAULT = 120      # fallback cooldown for unknown flood
    SPAM_PAUSE_AFTER_SPAWN = 12   # pause spam for X sec when spawn detected

    # ── Warmup ──────────────────────────────────────────────────
    HINT_BOT_WARMUP_INTERVAL = 3600   # periodic re-warmup (1h)

    # ── /startspam timing ───────────────────────────────────────
    START_SPAM_INTERVAL = 180
    START_SPAM_MIN_DELAY = 5
    START_SPAM_MAX_DELAY = 15
    START_SPAM_JITTER = 0.10


SPAM_TEXT = (
    " @FLASH_SPAM_Bot | @fuckyourwifey_bot | @Imjustkidding_bot | "
    "@GodMorgan_robot | @enforcermorgan_11robot | "
    "fqcawqAaaaafbBsqqlqoျဘျဆငငေတငတုsahqBwqiqoaj#!11&$1(!92929*@*@>>\n"
)


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
#  DATABASE
# ══════════════════════════════════════════════════════════════════
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
                    serverSelectionTimeoutMS=5000)
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

    @property
    def ninja_col(self):
        return self.db["ninja_col"]

    @property
    def catch_col(self):
        return self.db["catch_col"]


# ══════════════════════════════════════════════════════════════════
#  MAIN BOT
# ══════════════════════════════════════════════════════════════════
class SovereignBot:
    def __init__(self, db: DatabaseManager):
        self.db = db

        self.bot_client = TelegramClient(
            "bot_main_session", Config.API_ID, Config.API_HASH,
            flood_sleep_threshold=60)
        self.bot_id = None

        # ── Ninja pool (all) ────────────────────────────────────
        self.ninja_clients: List[TelegramClient] = []
        self.ninja_names: List[str] = []
        self.ninja_ids: Set[int] = set()

        # ── Catch ninja IDs (bulk-managed · persistent) ─────────
        self.catch_ninja_ids: Set[int] = set()

        # ── Spawn marker ────────────────────────────────────────
        self.ninja_spawn_marker = {"key": None, "selected": set()}
        self.ninja_forward_tracker: Dict[int, dict] = {}

        # ── Flood / rate tracking ───────────────────────────────
        # time.monotonic() based — per client
        self.flood_until: Dict = {}         # client → until_time
        self.spam_last_used: Dict = {}      # client → last_sent_time
        self.spam_last_sent: Dict = {}      # chat_id → last_sent_time
        self.spam_pause_until: float = 0.0  # spawn-priority pause

        # ── Spam state ──────────────────────────────────────────
        self.ninja_spam_tasks: Dict = {}
        self.spam_active: bool = False

        # ── /startspam state ────────────────────────────────────
        self.start_spam_tasks: Dict = {}
        self.start_spam_target = None
        self.start_spam_active = False

        # ── Warmup task ─────────────────────────────────────────
        self._warmup_task: asyncio.Task = None

        self._register_handlers()

    # ══════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════
    def _catch_clients(self) -> List[TelegramClient]:
        """Return clients whose tg_user_id ∈ catch_ninja_ids."""
        return [
            c for c in self.ninja_clients
            if getattr(c, "tg_user_id", None) in self.catch_ninja_ids
        ]

    @staticmethod
    def _looks_like_spawn(text: str) -> bool:
        if not text:
            return False
        upper = text.upper()
        for ph in Config.SPAWN_PHRASES:
            if ph.upper() in upper:
                return True
        return False

    @staticmethod
    def _has_whitelist_emoji(text: str) -> bool:
        return any(e in text for e in Config.NINJA_WHITELIST_EMOJIS)

    def _mark_flood(self, client, seconds: int = None):
        sec = seconds if (seconds and seconds > 0) else Config.SPAM_FLOOD_DEFAULT
        self.flood_until[client] = time.monotonic() + sec
        uid = getattr(client, "tg_user_id", "?")
        logger.warning(f"⛔ [{uid}] flood cooldown {sec}s")

    # ══════════════════════════════════════════════════════════════
    #  AUTO-PROMOTE
    # ══════════════════════════════════════════════════════════════
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
            if not (getattr(perms, "add_admins", False)
                    or getattr(perms, "is_creator", False)):
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
                        change_info=False, post_messages=True,
                        edit_messages=True, delete_messages=True,
                        ban_users=True, invite_users=True,
                        pin_messages=True, add_admins=False,
                        anonymous=False, manage_call=False)
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
                    f"✅ Auto-Promote `{cid}` · promoted={promoted} "
                    f"already={already} failed={failed}")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"_auto_promote: {e}")

    # ══════════════════════════════════════════════════════════════
    #  WARMUP (all ninjas → hint bot /start)
    # ══════════════════════════════════════════════════════════════
    async def _warmup_hint_bot(self):
        if not self.ninja_clients:
            logger.info("🔄 Warmup skipped: no ninja clients.")
            return
        logger.info(
            f"🔄 Warming up {len(self.ninja_clients)} ninjas → "
            f"Hint Bot {Config.SPAWN_HINT_BOT_ID}")
        ok = fail = 0
        for c in self.ninja_clients:
            try:
                uid = getattr(c, "tg_user_id", None)
                await c.send_message(Config.SPAWN_HINT_BOT_ID, "/start")
                ok += 1
                logger.info(f"  ✅ [{uid}] /start → hint bot")
                await asyncio.sleep(random.uniform(0.4, 0.9))
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
                fail += 1
            except Exception as e:
                logger.warning(f"  ❌ /start failed: {e}")
                fail += 1
        logger.info(f"✅ Warmup done · ok={ok} fail={fail}")
        try:
            await self.bot_client.send_message(
                Config.OWNER_ID,
                f"🚀 **Hint Bot Warm-up**\n"
                f"🥷 Hint Bot: `{Config.SPAWN_HINT_BOT_ID}`\n"
                f"✅ OK: `{ok}`\n"
                f"❌ Fail: `{fail}`\n"
                f"🥷 Pool: `{len(self.ninja_clients)}`\n"
                f"🕐 {datetime.now(Config.TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode="markdown")
        except Exception:
            pass

    async def _periodic_warmup_loop(self):
        while True:
            try:
                await asyncio.sleep(Config.HINT_BOT_WARMUP_INTERVAL)
                logger.info("🔁 Periodic warmup starting…")
                await self._warmup_hint_bot()
            except asyncio.CancelledError:
                logger.info("Periodic warmup cancelled.")
                break
            except Exception as e:
                logger.warning(f"periodic warmup: {e}")
                await asyncio.sleep(60)

    # ══════════════════════════════════════════════════════════════
    #  /startspam (ninja အားလုံး → /start @target)
    # ══════════════════════════════════════════════════════════════
    async def _start_spam_worker(self, ninja, uid, target):
        await asyncio.sleep(random.uniform(
            Config.START_SPAM_MIN_DELAY, Config.START_SPAM_MAX_DELAY))
        while self.start_spam_active and uid in self.start_spam_tasks:
            try:
                await asyncio.wait_for(
                    ninja.send_message(target, "/start"), timeout=20)
                logger.info(f"🎯 [{uid}] /start → @{target}")
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"🎯 [{uid}]: {e}")
            jitter = Config.START_SPAM_INTERVAL * random.uniform(
                -Config.START_SPAM_JITTER, Config.START_SPAM_JITTER)
            wait = max(30, Config.START_SPAM_INTERVAL + jitter)
            waited = 0
            while waited < wait and self.start_spam_active:
                await asyncio.sleep(5)
                waited += 5

    async def start_start_spam(self, target):
        if self.start_spam_active or not self.ninja_clients:
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
                    self._start_spam_worker(c, uid, target))
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

    # ══════════════════════════════════════════════════════════════
    #  AUTO-CATCH — spawn handler (catch_ninja_ids only)
    # ══════════════════════════════════════════════════════════════
    async def _ninja_spawn_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid:
                return

            # ① Catch list ထဲက ninja ပဲ
            if uid not in self.catch_ninja_ids:
                return

            # ② SPAM_GROUPS ထဲမှာပဲ
            if event.chat_id not in Config.SPAM_GROUPS:
                return

            # ③ Game Bot ဆီက message ပဲ
            if event.sender_id != Config.SPAWN_GAME_BOT_ID:
                return

            # ④ Text / caption ဖတ်
            text = event.text or ""
            if not text:
                try:
                    if event.message and event.message.message:
                        text = event.message.message
                except Exception:
                    pass
            if not text:
                return
            if not self._looks_like_spawn(text):
                return
            if not self._has_whitelist_emoji(text):
                return

            # ⑤ Per-spawn ninja ရွေး (catch ninjas ထဲကပဲ)
            skey = f"{event.chat_id}:{event.message.id}"
            if self.ninja_spawn_marker.get("key") != skey:
                avail = list(self.catch_ninja_ids
                             & self.ninja_ids)      # pool ထဲရှိမှ
                if not avail:
                    logger.warning("⚠️ No loaded catch ninjas!")
                    return
                picked = (
                    set(avail) if len(avail) <= Config.NINJA_PICK_COUNT
                    else set(random.sample(avail, Config.NINJA_PICK_COUNT)))
                self.ninja_spawn_marker["key"] = skey
                self.ninja_spawn_marker["selected"] = picked
                # 🛡️ spawn တွေ့ရင် spam ခဏ pause
                self.spam_pause_until = (
                    time.monotonic() + Config.SPAM_PAUSE_AFTER_SPAWN)
                logger.info(
                    f"🎯 Spawn {skey} · selected {len(picked)} catch ninjas "
                    f"· spam paused {Config.SPAM_PAUSE_AFTER_SPAWN}s")

            if uid not in self.ninja_spawn_marker["selected"]:
                return

            # ⑥ Flood ဖြစ်နေရင် skip (အခြား ninja တွေ ဆက်လုပ်)
            now = time.monotonic()
            if self.flood_until.get(event.client, 0) > now:
                logger.info(f"⏭️ [{uid}] in flood — skip this spawn")
                return

            # ⑦ 3–4s random delay
            await asyncio.sleep(random.uniform(
                Config.NINJA_W_DELAY_MIN, Config.NINJA_W_DELAY_MAX))

            # ⑧ Forward → Hint Bot DM
            try:
                await event.message.forward_to(Config.SPAWN_HINT_BOT_ID)
            except FloodWaitError as e:
                self._mark_flood(event.client, e.seconds)
                return
            except Exception as e:
                logger.warning(f"[{uid}] forward failed: {e}")
                return

            self.ninja_forward_tracker[uid] = {
                "chat_id": event.chat_id,
                "msg_id": event.message.id,
                "time": datetime.now(),
            }
            logger.info(
                f"➡️ [{uid}] spawn {skey} forwarded → Hint Bot DM")

        except Exception as e:
            logger.warning(f"spawn handler: {e}")

    async def _ninja_dm_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid or uid not in self.catch_ninja_ids:
                return
            if event.sender_id != Config.SPAWN_HINT_BOT_ID:
                return
            if event.is_group or event.is_channel:
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
            m = re.search(r"(/catch(?:@\w+)?\s+[^\n]+)", text)
            if not m:
                return
            cmd = m.group(1).strip(" `\n\r")
            info = self.ninja_forward_tracker.get(uid)
            if not info:
                return
            grp = info.get("chat_id")
            if not grp:
                return
            try:
                await event.client.send_message(grp, cmd)
                logger.info(f"🎯 [{uid}] → {grp} : {cmd}")
                self.ninja_forward_tracker.pop(uid, None)
            except FloodWaitError as e:
                self._mark_flood(event.client, e.seconds)
            except Exception as e:
                logger.warning(f"send catch [{uid}] failed: {e}")
        except Exception as e:
            logger.warning(f"dm handler: {e}")

    def _register_ninja_handlers(self, client):
        client.add_event_handler(
            self._ninja_spawn_handler,
            events.NewMessage(
                chats=Config.SPAM_GROUPS,
                from_users=Config.SPAWN_GAME_BOT_ID))
        client.add_event_handler(
            self._ninja_dm_handler,
            events.NewMessage(
                incoming=True,
                from_users=Config.SPAWN_HINT_BOT_ID,
                func=lambda e: not e.is_group and not e.is_channel))
        client.add_event_handler(
            self._ninja_join_handler, events.ChatAction())

    # ══════════════════════════════════════════════════════════════
    #  NINJA POOL + CATCH LIST LOAD
    # ══════════════════════════════════════════════════════════════
    async def _load_catch_ids(self):
        doc = await self.db.catch_col.find_one({"_id": "catch_ids"})
        if doc:
            self.catch_ninja_ids = set(int(x) for x in doc.get("ids", []))
        logger.info(
            f"🎯 Catch list loaded: {len(self.catch_ninja_ids)} IDs")

    async def _save_catch_ids(self):
        await self.db.catch_col.update_one(
            {"_id": "catch_ids"},
            {"$set": {"ids": sorted(self.catch_ninja_ids)}},
            upsert=True)

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

        async for doc in self.db.ninja_col.find():
            sess = doc.get("session")
            if not sess:
                continue
            try:
                c = TelegramClient(
                    StringSession(sess),
                    Config.API_ID, Config.API_HASH,
                    flood_sleep_threshold=0)
                await c.start()
                if await c.is_user_authorized():
                    me = await c.get_me()
                    c.tg_user_id = me.id
                    self.ninja_clients.append(c)
                    self.ninja_names.append(
                        doc.get("name", f"Ninja-{len(self.ninja_clients)}"))
                    self.ninja_ids.add(me.id)
                    self._register_ninja_handlers(c)
                    logger.info(
                        f"✅ Ninja '{doc.get('name')}' loaded: "
                        f"@{me.username}")
                else:
                    await c.disconnect()
            except Exception as e:
                logger.error(f"❌ Ninja load failed: {e}")
        logger.info(
            f"🚀 Ninja Pool ready: {len(self.ninja_clients)} clients.")

        # catch IDs ကို loaded pool နဲ့ စစ်
        if self.catch_ninja_ids:
            missing = self.catch_ninja_ids - self.ninja_ids
            if missing:
                logger.warning(
                    f"⚠️ {len(missing)} catch IDs not in loaded pool: "
                    f"{sorted(missing)[:5]}…")

    # ══════════════════════════════════════════════════════════════
    #  🛡️ FLOOD-SAFE SPAM
    # ══════════════════════════════════════════════════════════════
    def _pick_spam_client(self, now: float):
        """Eligible ninja ရွေး — catch ninja တွေကို နောက်ဆုံးမှ သုံး"""
        eligible = []
        for c in self.ninja_clients:
            if self.flood_until.get(c, 0) > now:
                continue
            uid = getattr(c, "tg_user_id", None)
            cooldown = (Config.SPAM_CATCH_COOLDOWN
                        if uid in self.catch_ninja_ids
                        else Config.SPAM_NINJA_COOLDOWN)
            if now - self.spam_last_used.get(c, 0) < cooldown:
                continue
            eligible.append(c)

        if not eligible:
            return None

        # non-catch အရင် (catch ninja တွေ spawn အတွက် အားထား)
        non_catch = [
            c for c in eligible
            if getattr(c, "tg_user_id", None) not in self.catch_ninja_ids
        ]
        pool = non_catch if non_catch else eligible

        # oldest-used အရင် (round-robin ဖြစ်စေ)
        pool.sort(key=lambda c: self.spam_last_used.get(c, 0))
        return pool[0]

    async def _start_spam_loop(self, chat_ids):
        key = tuple(sorted(chat_ids))
        if self.ninja_spam_tasks.get(key):
            return
        self.ninja_spam_tasks[key] = True
        if not self.ninja_clients:
            return

        # init
        now = time.monotonic()
        for cid in chat_ids:
            self.spam_last_sent.setdefault(cid, 0)
        for c in self.ninja_clients:
            self.spam_last_used.setdefault(c, 0)
            self.flood_until.setdefault(c, 0)

        async def loop():
            logger.info(
                f"📢 Spam loop started · {len(chat_ids)} groups · "
                f"interval={Config.SPAM_GROUP_INTERVAL}s · "
                f"pool={len(self.ninja_clients)}")
            while self.ninja_spam_tasks.get(key):
                now = time.monotonic()

                # spawn priority pause
                if now < self.spam_pause_until:
                    await asyncio.sleep(1)
                    continue

                for cid in chat_ids:
                    now = time.monotonic()
                    if (now - self.spam_last_sent.get(cid, 0)
                            < Config.SPAM_GROUP_INTERVAL):
                        continue
                    client = self._pick_spam_client(now)
                    if not client:
                        # pool အားလုံး flood/cooldown ဖြစ်နေတယ်
                        continue
                    try:
                        await client.send_message(cid, SPAM_TEXT)
                        ts = time.monotonic()
                        self.spam_last_sent[cid] = ts
                        self.spam_last_used[client] = ts
                    except FloodWaitError as e:
                        self._mark_flood(client, e.seconds)
                    except Exception as e:
                        logger.debug(f"spam send: {e}")
                    # global delay
                    await asyncio.sleep(Config.SPAM_GLOBAL_DELAY)

                await asyncio.sleep(1)
            logger.info(f"🛑 Spam loop stopped for {len(chat_ids)} groups")

        asyncio.create_task(loop())

    async def _stop_spam_loop(self, key):
        if key in self.ninja_spam_tasks:
            self.ninja_spam_tasks[key] = False

    # ══════════════════════════════════════════════════════════════
    #  OWNER COMMANDS
    # ══════════════════════════════════════════════════════════════
    def _register_handlers(self):

        # ── /addninja ─────────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/addninja(?:@\w+)?(?:\s+(.*?))?(?:\s+(.*))?$"))
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
                    return await event.reply(
                        "❓ Usage: /addninja <name> <session>")
            if not sess or len(sess) < 10:
                return await event.reply("❌ Invalid session.")
            async for d in self.db.ninja_col.find():
                if d.get("session") == sess:
                    return await event.reply("⚠️ Already exists.")
            await self.db.ninja_col.insert_one(
                {"name": name, "session": sess})
            try:
                c = TelegramClient(
                    StringSession(sess),
                    Config.API_ID, Config.API_HASH,
                    flood_sleep_threshold=0)
                await c.start()
                me = await c.get_me()
                c.tg_user_id = me.id
                self.ninja_clients.append(c)
                self.ninja_names.append(name)
                self.ninja_ids.add(me.id)
                self._register_ninja_handlers(c)
                await event.reply(
                    f"✅ '{name}' (ID: {me.id}) added. "
                    f"Total: {len(self.ninja_clients)}")
                try:
                    await c.send_message(
                        Config.SPAWN_HINT_BOT_ID, "/start")
                except Exception:
                    pass
            except Exception as e:
                await event.reply(f"❌ Failed: {e}")
                await self.db.ninja_col.delete_one({"session": sess})

        # ── /listninja ────────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/listninja(?:@\w+)?$"))
        async def list_ninja(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.ninja_clients:
                return await event.reply("📭 No ninjas.")
            online = 0
            lines = [f"👥 **Ninja Pool ({len(self.ninja_clients)} loaded)**"]
            for i, (c, n) in enumerate(
                    zip(self.ninja_clients, self.ninja_names)):
                try:
                    me = await c.get_me()
                    online += 1
                    full = (
                        f"{me.first_name or ''} "
                        f"{me.last_name or ''}").strip() or "No Name"
                    u = f"(@{me.username})" if me.username else ""
                    tag = " 🎯" if me.id in self.catch_ninja_ids else ""
                    lines.append(
                        f"  {i+1}. **{full}** {u} "
                        f"(ID: `{me.id}`) ✅{tag}")
                except Exception:
                    lines.append(f"  {i+1}. **{n}** ❌")
            lines.append(
                f"\n📊 Online: {online}/{len(self.ninja_clients)}")
            lines.append(
                f"🎯 Catch list: {len(self.catch_ninja_ids)} IDs")
            await event.reply("\n".join(lines), parse_mode="markdown")

        # ── /removeninja ──────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/removeninja(?:@\w+)?\s+(.+)$"))
        async def remove_ninja(event):
            if event.sender_id != Config.OWNER_ID:
                return
            target = event.pattern_match.group(1).strip()
            plist = await self.db.ninja_col.find().to_list(length=None)
            idx = None
            if target.isdigit():
                idx = int(target) - 1
            else:
                for i, d in enumerate(plist):
                    if d.get("name") == target:
                        idx = i
                        break
            if idx is None or idx < 0 or idx >= len(plist):
                return await event.reply(f"❌ Not found: {target}")
            doc = plist[idx]
            await self.db.ninja_col.delete_one({"_id": doc["_id"]})
            if idx < len(self.ninja_clients):
                c = self.ninja_clients.pop(idx)
                self.ninja_names.pop(idx)
                try:
                    await c.disconnect()
                except Exception:
                    pass
                await event.reply(f"✅ Removed '{doc.get('name')}'.")
            else:
                await event.reply("✅ Removed from DB.")

        # ── /setcatch (bulk add · append) ─────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/setcatch(?:@\w+)?(?:\s+([\s\S]+))?$"))
        async def setcatch_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")

            raw = event.pattern_match.group(1) or ""
            # reply မှာပါတဲ့ text ကိုပါ ဖတ်
            r = await event.get_reply_message()
            if r and r.text:
                raw = raw + "\n" + r.text

            if not raw.strip():
                return await event.reply(
                    "⚠️ **Usage**\n"
                    "• `/setcatch 123 456 789`\n"
                    "• သို့မဟုတ် IDs ပါတဲ့ message ကို reply → `/setcatch`\n\n"
                    "IDs များကို space / comma / newline နဲ့ ခွဲနိုင်တယ်။ "
                    "ထပ်ထည့်တိုင်း **append** ဖြစ်တယ် (အရင် ID တွေ မပျောက်)။",
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

            before = len(self.catch_ninja_ids)
            self.catch_ninja_ids.update(ids)
            added = len(self.catch_ninja_ids) - before
            await self._save_catch_ids()

            # pool ထဲရှိ/မရှိ report
            in_pool = ids & self.ninja_ids
            not_in_pool = ids - self.ninja_ids

            msg = (
                f"✅ **Catch List Updated**\n"
                f"📥 Requested : `{len(ids)}`\n"
                f"➕ New added : `{added}`\n"
                f"🎯 Total now : `{len(self.catch_ninja_ids)}`\n"
                f"✅ In pool   : `{len(in_pool)}`\n"
            )
            if not_in_pool:
                preview = ", ".join(str(x) for x in list(not_in_pool)[:10])
                msg += (
                    f"⚠️ Not loaded yet ({len(not_in_pool)}): `{preview}`\n"
                    f"_(pool ထဲ ရောက်တာနဲ့ auto-active ဖြစ်မယ်)_")
            await event.reply(msg, parse_mode="markdown")

        # ── /listcatch ────────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/listcatch(?:@\w+)?$"))
        async def listcatch_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not self.catch_ninja_ids:
                return await event.reply("📭 Catch list empty.")
            lines = [f"🎯 **Catch Ninja List ({len(self.catch_ninja_ids)})**"]
            for i, uid in enumerate(sorted(self.catch_ninja_ids)):
                tag = "✅" if uid in self.ninja_ids else "⚠️(not loaded)"
                lines.append(f"  {i+1}. `{uid}` {tag}")
            await event.reply("\n".join(lines), parse_mode="markdown")

        # ── /clearcatch ───────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/clearcatch(?:@\w+)?$"))
        async def clearcatch_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            n = len(self.catch_ninja_ids)
            self.catch_ninja_ids.clear()
            await self._save_catch_ids()
            await event.reply(f"🗑️ Cleared {n} catch IDs.")

        # ── /autosession ──────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/autosession(?:@\w+)?$"))
        async def autosession_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            reply = await event.get_reply_message()
            if not reply or not reply.text:
                return await event.reply(
                    "⚠️ **Usage:** Reply to a message containing IDs → "
                    "`/autosession`", parse_mode="markdown")
            ids = []
            for line in reply.text.splitlines():
                line = line.strip()
                m = re.match(r"^(\d+)", line)
                if m:
                    try:
                        n = int(m.group(1))
                        if n > 0:
                            ids.append(n)
                    except Exception:
                        pass
            seen = set()
            uniq = []
            for i in ids:
                if i not in seen:
                    seen.add(i)
                    uniq.append(i)
            if not uniq:
                return await event.reply("❌ No valid IDs found.")
            status = await event.reply(
                f"⏳ Exporting sessions for `{len(uniq)}` IDs…",
                parse_mode="markdown")
            uid_map = {}
            for c in self.ninja_clients:
                u = getattr(c, "tg_user_id", None)
                if u:
                    uid_map[u] = c
            lines = []
            missing = []
            for uid in uniq:
                client = uid_map.get(uid)
                if not client:
                    missing.append(uid)
                    continue
                try:
                    sess = client.session.save()
                except Exception:
                    sess = None
                try:
                    me = await client.get_me()
                    full = (
                        (me.first_name or "")
                        + (" " + me.last_name if me.last_name else "")
                    ).strip() or "No Name"
                    uname = f"@{me.username}" if me.username else "—"
                except Exception:
                    full, uname = "?", "—"
                lines.append(
                    f"# {uid} | {full} | {uname}\n"
                    f"{sess or '(session unavailable)'}")
            body = "\n\n".join(lines)
            header = (
                f"# ═══════════════════════════════════════════════\n"
                f"# Session Export\n"
                f"# Total requested  : {len(uniq)}\n"
                f"# Exported OK      : {len(lines)}\n"
                f"# Missing from pool: {len(missing)}\n"
                f"# Missing IDs      : "
                f"{', '.join(str(m) for m in missing) if missing else '—'}\n"
                f"# Generated        : "
                f"{datetime.now(Config.TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"# ═══════════════════════════════════════════════\n\n"
            )
            content = (header + body).encode("utf-8")
            buf = io.BytesIO(content)
            buf.name = f"sessions_{int(time.time())}.txt"
            try:
                await status.delete()
            except Exception:
                pass
            await event.reply(
                f"✅ **Sessions ready**\n"
                f"📋 Requested: `{len(uniq)}`\n"
                f"🥷 Exported: `{len(lines)}`\n"
                f"⚠️ Missing: `{len(missing)}`",
                file=buf, parse_mode="markdown")

        # ── /autoninja (info) ─────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/autoninja(?:@\w+)?$"))
        async def autoninja_status(event):
            if event.sender_id != Config.OWNER_ID:
                return
            loaded_catch = len(self.catch_ninja_ids & self.ninja_ids)
            await event.reply(
                f"🥷 **AUTO-CATCH (SPAM_GROUPS)**\n"
                f"🎮 Game Bot: `{Config.SPAWN_GAME_BOT_ID}`\n"
                f"🥷 Hint Bot: `{Config.SPAWN_HINT_BOT_ID}` (external)\n"
                f"📍 Groups: `{len(Config.SPAM_GROUPS)}`\n"
                f"👥 Pool: `{len(self.ninja_clients)}`\n"
                f"🎯 Catch list: `{len(self.catch_ninja_ids)}` "
                f"(loaded: `{loaded_catch}`)\n"
                f"🎯 Pick/spawn: `{Config.NINJA_PICK_COUNT}`\n"
                f"⏱️ Delay: `{Config.NINJA_W_DELAY_MIN}-"
                f"{Config.NINJA_W_DELAY_MAX}s`\n"
                f"✅ Whitelist: "
                f"`{' '.join(Config.NINJA_WHITELIST_EMOJIS)}`\n"
                f"🛡️ Spam: `{Config.SPAM_GROUP_INTERVAL}s/group` · "
                f"cooldown `{Config.SPAM_NINJA_COOLDOWN}s`",
                parse_mode="markdown")

        # ── /warmup (manual) ──────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/warmup(?:@\w+)?$"))
        async def warmup_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            await event.reply(
                f"🔄 Warming up `{len(self.ninja_clients)}` ninjas → "
                f"Hint Bot `{Config.SPAWN_HINT_BOT_ID}`…",
                parse_mode="markdown")
            await self._warmup_hint_bot()

        # ── /startspam ────────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/startspam(?:@\w+)?(?:\s+(@?\w+))?$"))
        async def startspam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            arg = event.pattern_match.group(1)
            if not arg:
                return await event.reply(
                    "⚠️ Usage: /startspam @BotUsername")
            target = arg.lstrip("@").strip()
            if not target:
                return await event.reply("❌ Invalid username.")
            if self.start_spam_active:
                return await event.reply(
                    f"⚠️ Already running → @{self.start_spam_target}")
            if not self.ninja_clients:
                return await event.reply("❌ Ninja pool empty.")
            n = await self.start_start_spam(target)
            await event.reply(
                f"🎯 START SPAM ON → @{target} · {n} workers · "
                f"{Config.START_SPAM_INTERVAL}s interval")

        # ── /stopspam ─────────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/stopspam(?:@\w+)?$"))
        async def stopspam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            if not self.start_spam_active:
                return await event.reply("ℹ️ Not running.")
            target = self.start_spam_target
            n = await self.stop_start_spam()
            await event.reply(
                f"🛑 START SPAM OFF · @{target} · stopped {n}")

        # ── /spamstatus ───────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/spamstatus(?:@\w+)?$"))
        async def spamstatus_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return await event.reply("⛔ Owner only.")
            now = time.monotonic()
            active_floods = sum(
                1 for c in self.ninja_clients
                if self.flood_until.get(c, 0) > now)
            msg = (
                f"🎯 /startspam: "
                f"{'ON → @' + str(self.start_spam_target) if self.start_spam_active else 'OFF'}\n"
                f"🗣️ /spam loops: `{len([k for k,v in self.ninja_spam_tasks.items() if v])}`\n"
                f"⛔ Flooded now: `{active_floods}/{len(self.ninja_clients)}`\n"
                f"🛡️ Spam interval: `{Config.SPAM_GROUP_INTERVAL}s/group`\n"
                f"🎯 Catch list: `{len(self.catch_ninja_ids)}`"
            )
            await event.reply(msg, parse_mode="markdown")

        # ── /spam ─────────────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/spam(?:@\w+)?$"))
        async def spam_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            await self._start_spam_loop(Config.SPAM_GROUPS)
            await event.reply(
                f"🗣️ Spam started on {len(Config.SPAM_GROUPS)} groups · "
                f"interval `{Config.SPAM_GROUP_INTERVAL}s/group`",
                parse_mode="markdown")

        # ── ရပ် / /stop ────────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^(ရပ်|/stop(?:@\w+)?)$"))
        async def stop_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            stopped = 0
            for k in list(self.ninja_spam_tasks.keys()):
                if self.ninja_spam_tasks.get(k):
                    self.ninja_spam_tasks[k] = False
                    stopped += 1
            await event.reply(
                f"🛑 Stopped {stopped} spam loop(s)."
                if stopped else "ℹ️ Nothing to stop.")

        # ── /go ───────────────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/go(?:@\w+)?$"))
        async def go_group(event):
            if event.sender_id != Config.OWNER_ID:
                return
            if not event.is_reply:
                return await event.reply("❌ Reply to invite link.")
            r = await event.get_reply_message()
            if not r.text:
                return await event.reply("❌ No text.")
            m = re.search(
                r"(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)", r.text)
            if not m:
                return await event.reply("❌ No link.")
            link = m.group(0)
            if "joinchat/" in link:
                h = link.split("joinchat/")[1].split("?")[0]
            elif "+" in link:
                h = link.split("+")[1].split("?")[0]
            else:
                h = None
            if not h:
                return await event.reply("❌ Bad link.")
            clients = self.ninja_clients.copy()
            if not clients:
                return await event.reply("❌ No clients.")
            await event.reply(
                f"⏳ Joining with {len(clients)} clients...")
            success = 0
            for c in clients:
                try:
                    await asyncio.wait_for(
                        c(ImportChatInviteRequest(h)), timeout=20)
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
            try:
                chat = await clients[0].get_entity(link)
                await event.reply(
                    f"✅ Joined `{chat.title}` ({success} clients). "
                    f"ID: `{chat.id}`")
            except Exception:
                await event.reply(f"✅ Joined ({success} clients).")

        # ── /status ───────────────────────────────────────────
        @self.bot_client.on(events.NewMessage(
            pattern=r"^/status(?:@\w+)?$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID:
                return
            now = time.monotonic()
            active_floods = sum(
                1 for c in self.ninja_clients
                if self.flood_until.get(c, 0) > now)
            ss = (f"ON → @{self.start_spam_target}"
                  if self.start_spam_active else "OFF")
            warmup_status = ("✅ running"
                             if self._warmup_task
                             and not self._warmup_task.done()
                             else "❌ stopped")
            await event.reply(
                f"📊 **Status**\n"
                f"🤖 Pool: `{len(self.ninja_clients)}`\n"
                f"🎯 Catch list: `{len(self.catch_ninja_ids)}` "
                f"(loaded: `{len(self.catch_ninja_ids & self.ninja_ids)}`)\n"
                f"⛔ Flooded: `{active_floods}`\n"
                f"🎮 Game Bot: `{Config.SPAWN_GAME_BOT_ID}`\n"
                f"🥷 Hint Bot: `{Config.SPAWN_HINT_BOT_ID}` (external)\n"
                f"🔄 Warmup loop: `{warmup_status}`\n"
                f"🎯 /startspam: `{ss}`\n"
                f"🗣️ /spam groups: `{len(Config.SPAM_GROUPS)}`",
                parse_mode="markdown")

    # ══════════════════════════════════════════════════════════════
    #  START / STOP
    # ══════════════════════════════════════════════════════════════
    async def start(self):
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        me = await self.bot_client.get_me()
        self.bot_id = me.id
        logger.info(f"🤖 Bot started: @{me.username} ({self.bot_id})")

        # load catch IDs (before pool — so pool load check works)
        await self._load_catch_ids()

        # load ninja pool
        await self.load_ninja_pools()

        # startup warmup
        await self._warmup_hint_bot()

        # periodic warmup task
        self._warmup_task = asyncio.create_task(
            self._periodic_warmup_loop())

        # flask
        threading.Thread(target=run_flask, daemon=True).start()

        await self.bot_client.run_until_disconnected()

    async def stop(self):
        if self.start_spam_active:
            await self.stop_start_spam()

        # stop spam loops
        for k in list(self.ninja_spam_tasks.keys()):
            self.ninja_spam_tasks[k] = False

        if self._warmup_task and not self._warmup_task.done():
            self._warmup_task.cancel()

        try:
            if self.bot_client.is_connected():
                await self.bot_client.disconnect()
        except Exception:
            pass

        for c in self.ninja_clients:
            try:
                await c.disconnect()
            except Exception:
                pass

        await self.db.close()
        logger.info("🛑 Shutdown.")


# ══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════
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
