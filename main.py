#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sovereign Ninja + Ninja Sync + Selective Auto-Catch
- 31 ninjas work for /spam AND /nsync
- AUTO-CATCH in the 4 hardcore SPAM_GROUPS only:
    * Spawn bot (6157455819) posts "spawned" text + 🔵/🟣/🟠 → accept
    * ONE ninja sends /w (fallback if flood)
    * Hint bot (8999491734) replies "/catch <name>"
    * ONLY /auto-selected IDs send /catch
- Everything runs concurrently with /spam
- /actest for diagnostics
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
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest


class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "7693106830"))
    MONGO_URI = os.getenv("MONGO_URI",
        "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true")
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "8824002850:AAGPtl7M0dw_gDVEZNxM3xxrYQazKvO5FKo")

    SPAM_GROUPS = [-1004381473883, -1003836488351, -1003733625547, -1004358425408]

    TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Asia/Yangon"))
    FLASK_PORT = int(os.getenv("PORT", "10000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    ADMIN_CACHE_TTL = 600
    MAX_RETRIES = 3

    # ═══ OLD auto-ninja on SPAWN_GROUP_2 (kept) ═══
    SPAWN_BOT_2_ID = 8999491734
    SPAWN_GROUP_2 = -1003580630981
    NINJA_PICK_COUNT = 5
    NINJA_W_DELAY_MIN = 3.0
    NINJA_W_DELAY_MAX = 4.0
    NINJA_IGNORED_EMOJIS = ["🔵", "🟣", "🟠"]

    START_SPAM_INTERVAL = 180
    START_SPAM_MIN_DELAY = 5
    START_SPAM_MAX_DELAY = 15
    START_SPAM_JITTER = 0.10

    # ═══ NINJA SYNC ═══
    SYNC_TARGET_BOT_USERNAME = os.getenv("SYNC_TARGET_BOT_USERNAME", "Character_Catcher_Bot")
    SYNC_TARGET_BOT_ID       = int(os.getenv("SYNC_TARGET_BOT_ID", "6157455819"))
    SYNC_CONTROL_GROUP_ID    = int(os.getenv("SPECIFIC_CONTROL_GROUP", "0"))
    SYNC_START_ID            = int(os.getenv("SYNC_START_ID", "1"))
    SYNC_END_ID              = int(os.getenv("SYNC_END_ID", "7203"))
    SYNC_SKIP_ALREADY_SYNCED = os.getenv("SYNC_SKIP_ALREADY_SYNCED", "true").lower() == "true"

    SYNC_WARMUP_TIMEOUT       = 15
    SYNC_WARMUP_DELAY         = 1.5
    SYNC_REPLY_TIMEOUT        = 30
    SYNC_COOLDOWN_BACKOFF     = 5
    SYNC_MAX_COOLDOWN_RETRIES = 3
    SYNC_NINJA_STAGGER        = 0.3
    SYNC_PACE_PER_CHECK       = 1.0
    SYNC_PROGRESS_INTERVAL    = 30
    SYNC_AUTO_WARMUP_ON_BOOT  = True

    # ═══ AUTO-CATCH (hardcore SPAM_GROUPS only) ═══
    AUTO_SPAWN_BOT_ID  = int(os.getenv("AUTO_SPAWN_BOT_ID", "6157455819"))
    AUTO_HINT_BOT_ID   = int(os.getenv("AUTO_HINT_BOT_ID",  "8999491734"))
    AUTO_CATCH_EMOJI_PREFIXES = ["🟠", "🟣", "🔵"]
    AUTO_CATCH_STATE_TTL = 90
    AUTO_CATCH_HINT_CACHE = 40


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
def health_check(): return "Sovereign Ninja System is operational."

def run_flask():
    flask_app.run(host="0.0.0.0", port=Config.FLASK_PORT, threaded=True)


# ---------- RARITY + CNFT ----------
_NON_CNFT_TIERS = ["SUPREME", "CATAPHRACT", "CROSSVERSE", "DIVINE", "MYSTICAL",
                   "LEGENDARY", "RARE", "UNCOMMON", "COMMON"]
RARITY_TIERS = _NON_CNFT_TIERS + ["CNFT SS", "CNFT S", "CNFT A"]
RARITY_TIER_TO_NUM = {t: str(i + 1) for i, t in enumerate(_NON_CNFT_TIERS)}
RARITY_EMOJI = {"SUPREME": "🪞", "CATAPHRACT": "✨", "CROSSVERSE": "⚡", "DIVINE": "⚜️",
                "MYSTICAL": "💮", "LEGENDARY": "🟡", "RARE": "🟠", "UNCOMMON": "🟣", "COMMON": "🔵"}
RARITY_DISPLAY_NAME = {"SUPREME": "Supreme", "CATAPHRACT": "Cataphract", "CROSSVERSE": "CrossVerse",
                       "DIVINE": "Divine", "MYSTICAL": "Mystical", "LEGENDARY": "Legendary",
                       "RARE": "Rare", "UNCOMMON": "Uncommon", "COMMON": "Common"}
_RARITY_VALUE_MAP = {"SUPREME": 100000, "CATAPHRACT": 70000, "CROSSVERSE": 50000, "DIVINE": 35000,
                     "MYSTICAL": 25000, "LEGENDARY": 15000, "RARE": 10000, "UNCOMMON": 6000, "COMMON": 3000}
CNFT_DEFAULT_VALUE = 100000


def _build_fancy_font_reverse_map():
    m = {}
    for cp in range(0x1D400, 0x1D800):
        try: name = unicodedata.name(chr(cp))
        except ValueError: continue
        if not name.startswith("MATHEMATICAL "): continue
        toks = name.split(); last = toks[-1]
        if "DIGIT" in toks:
            d = {"ZERO":"0","ONE":"1","TWO":"2","THREE":"3","FOUR":"4","FIVE":"5","SIX":"6","SEVEN":"7","EIGHT":"8","NINE":"9"}
            if last in d: m[chr(cp)] = d[last]
        elif "DOTLESS" in toks: m[chr(cp)] = last.lower()
        elif len(last) == 1 and last.isalpha():
            if "SMALL" in toks: m[chr(cp)] = last.lower()
            elif "CAPITAL" in toks: m[chr(cp)] = last.upper()
    return m


_FANCY_TO_PLAIN = str.maketrans(_build_fancy_font_reverse_map())


def is_cnft_rarity(r):
    return bool(r) and "CNFT" in r.translate(_FANCY_TO_PLAIN).upper()


def extract_cnft_tier(r):
    if not r: return None
    plain = r.translate(_FANCY_TO_PLAIN).upper()
    norm = re.sub(r'[_\-\u2013\u2014]+', ' ', plain)
    m = re.search(r'CNFT\s*([A-Z0-9]+(?:\s+[A-Z0-9]+)*)?', norm)
    if not m: return None
    suf = (m.group(1) or "").strip()
    suf = re.sub(r'\s+', ' ', suf)
    return f"CNFT {suf}".strip() if suf else "CNFT"


def resolve_rarity(rarity_raw, existing_doc=None):
    if not rarity_raw: return None
    if is_cnft_rarity(rarity_raw):
        return {"tier": extract_cnft_tier(rarity_raw) or "CNFT", "name": rarity_raw.strip(),
                "value": CNFT_DEFAULT_VALUE, "is_cnft": True}
    plain = rarity_raw.translate(_FANCY_TO_PLAIN).upper()
    for tier in sorted(_NON_CNFT_TIERS, key=len, reverse=True):
        if tier in plain:
            return {"tier": tier, "name": f"{RARITY_EMOJI[tier]} {RARITY_DISPLAY_NAME[tier]}",
                    "value": _RARITY_VALUE_MAP[tier], "is_cnft": False}
    if existing_doc and existing_doc.get("rarity_tier"):
        et = existing_doc["rarity_tier"]
        return {"tier": et, "name": existing_doc.get("rarity") or et,
                "value": existing_doc.get("currency_value", CNFT_DEFAULT_VALUE), "is_cnft": True}
    return None


def classify_rarity(s):
    if not s: return "OTHER"
    if is_cnft_rarity(s): return extract_cnft_tier(s) or "CNFT"
    plain = s.translate(_FANCY_TO_PLAIN).upper()
    for tier in sorted(_NON_CNFT_TIERS, key=len, reverse=True):
        if tier in plain: return tier
    return "OTHER"


# ---------- Parse catch_bot's .check reply ----------
_EMOJI_RANGES = ((0x2190,0x21FF),(0x2300,0x23FF),(0x25A0,0x27BF),(0x2900,0x29FF),(0x2B00,0x2BFF),(0x1F000,0x1FFFF))
_VARSEL = ("\uFE0F", "\uFE0E")


def _is_emoji_char(ch):
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


def _event_wrapper_emoji(line):
    if not line or not _is_emoji_char(line[0]) or not _is_emoji_char(line[-1]): return None
    lead, trail = "", ""
    for ch in line:
        if _is_emoji_char(ch): lead += ch
        else: break
    for ch in reversed(line):
        if _is_emoji_char(ch): trail += ch
        else: break
    trail = trail[::-1]
    inner = line[len(lead):len(line)-len(trail)]
    if not inner.strip(): return None
    ln = "".join(c for c in lead if c not in _VARSEL)
    tn = "".join(c for c in trail if c not in _VARSEL)
    return ln if ln and ln == tn else None


def parse_catchbot_check(text):
    if not text or not text.strip(): return None
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 3: return None
    id_idx, char_num, name = None, None, None
    for idx in range(min(4, len(lines))):
        m = re.match(r'^(\d+)\s*:\s*(.+)$', lines[idx])
        if m:
            id_idx, char_num, name = idx, int(m.group(1)), m.group(2).strip()
            break
    if id_idx is None or not name: return None
    category = lines[id_idx - 1] if id_idx > 0 else "Unknown"
    rarity_raw, rarity_idx = None, None
    for idx in range(id_idx + 1, len(lines)):
        plain = lines[idx].translate(_FANCY_TO_PLAIN).upper()
        if "RARITY" in plain and ":" in lines[idx]:
            raw = lines[idx].rsplit(":", 1)[1].strip()
            if raw.endswith(")"): raw = raw[:-1].strip()
            rarity_raw, rarity_idx = raw, idx
            break
    if not rarity_raw: return None
    event = None
    if rarity_idx + 1 < len(lines) and _event_wrapper_emoji(lines[rarity_idx + 1]):
        event = lines[rarity_idx + 1]
    return {"id": char_num, "name": name, "category": category,
            "rarity_raw": rarity_raw, "event": event}


# ---------- Perceptual hash ----------
PHASH_SIZE = 16


def _compute_dhash_sync(b, hash_size=PHASH_SIZE):
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(b)).convert("L").resize((hash_size+1, hash_size), Image.LANCZOS)
        px = list(img.getdata()); bits = []
        for row in range(hash_size):
            rp = px[row*(hash_size+1):(row+1)*(hash_size+1)]
            for col in range(hash_size):
                bits.append("1" if rp[col] > rp[col+1] else "0")
        return format(int("".join(bits), 2), f'0{hash_size*hash_size//4}x')
    except Exception:
        return None


async def compute_phash_for_message(msg):
    try:
        b = await msg.download_media(thumb=0, file=bytes)
        if not b: return None
        return await asyncio.get_running_loop().run_in_executor(None, _compute_dhash_sync, b)
    except Exception:
        return None


# ---------- Database ----------
class DatabaseManager:
    def __init__(self, uri):
        self.uri = uri
        self.client = None
        self.db = None

    async def connect(self):
        for attempt in range(1, Config.MAX_RETRIES + 1):
            try:
                self.client = AsyncIOMotorClient(self.uri, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=5000)
                await self.client.admin.command("ping")
                self.db = self.client["telegram_bot"]
                logger.info("MongoDB connected.")
                return
            except (ConnectionFailure, OperationFailure) as e:
                logger.warning(f"MongoDB attempt {attempt} failed: {e}")
                if attempt == Config.MAX_RETRIES: raise
                await asyncio.sleep(2 ** attempt)

    async def close(self):
        if self.client: self.client.close()

    @property
    def system_col(self): return self.db["system_col"]
    @property
    def ninja_col(self): return self.db["ninja_col"]
    @property
    def taunt_targets(self): return self.db["taunt_targets"]
    @property
    def characters_col(self): return self.db["characters_base_data"]


# ══════════════════════════════════════════════════════════════════
#  AUTO-CATCH (hardcore SPAM_GROUPS only)
# ══════════════════════════════════════════════════════════════════
class AutoCatchEngine:
    """
    Flow (mirrors main.auto.py behaviour):
      1. Spawn bot (6157455819) posts "spawned" text + 🔵/🟣/🟠 → accept
      2. ONE ninja sends /w (sequential fallback if flooded)
      3. Hint bot (8999491734) replies "/catch <name>"
      4. ONLY /auto-selected IDs send /catch
    """

    def __init__(self, bot):
        self.bot = bot
        self.selected_ids: Set[int] = set()
        self.spawn_state: Dict[Tuple[int, int], dict] = {}
        self.lock = asyncio.Lock()
        self.accepted = 0
        self.rejected = 0
        self.w_sent = 0
        self.catch_sent = 0
        self.w_failed = 0
        self.raw_log: List[str] = []   # last 20 spawn-bot msgs seen in SPAM_GROUPS

    # ---------- persistence ----------
    async def load_settings(self):
        try:
            doc = await self.bot.db.system_col.find_one({"key": "auto_catch_settings"})
            if doc and doc.get("selected_ids"):
                self.selected_ids = set(int(x) for x in doc["selected_ids"])
            logger.info(f"🎯 [auto-catch] loaded selected_ids = {len(self.selected_ids)}")
        except Exception as e:
            logger.warning(f"auto-catch load_settings: {e}")

    async def save_settings(self):
        try:
            await self.bot.db.system_col.update_one(
                {"key": "auto_catch_settings"},
                {"$set": {"selected_ids": sorted(self.selected_ids)}},
                upsert=True)
        except Exception as e:
            logger.warning(f"auto-catch save_settings: {e}")

    # ---------- helpers ----------
    @staticmethod
    def _clean_invisible(text: str) -> str:
        if not text: return ""
        try: return "".join(c for c in text if unicodedata.category(c) != "Cf")
        except Exception: return text

    @staticmethod
    def _get_text(event) -> str:
        t = event.text or ""
        if not t:
            try:
                if event.message and event.message.message:
                    t = event.message.message
            except Exception: pass
        return t or ""

    def _is_spawn_text(self, text_clean: str) -> bool:
        if not text_clean: return False
        tl = text_clean.lower()
        return ("spawned" in tl
                or "sᴘᴀᴡɴᴇᴅ" in tl
                or "a character has spawned" in tl
                or "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ" in text_clean)

    def _has_allowed_emoji(self, text_clean: str) -> bool:
        """Accept if 🔵/🟣/🟠 appears anywhere in the caption."""
        return any(e in text_clean for e in Config.AUTO_CATCH_EMOJI_PREFIXES)

    def _purge_old_states(self):
        now = time.time()
        for k in list(self.spawn_state.keys()):
            if now - self.spawn_state[k]["ts"] > Config.AUTO_CATCH_STATE_TTL:
                del self.spawn_state[k]

    # ---------- spawn handler ----------
    async def spawn_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid: return

            text = self._get_text(event)
            clean = self._clean_invisible(text)

            # log every spawn-bot msg seen in SPAM_GROUPS
            if event.chat_id in Config.SPAM_GROUPS:
                head = clean[:60].replace("\n", " ⏎ ")
                line = f"uid={uid} chat={event.chat_id} msg={event.message.id} text={head!r}"
                self.raw_log.append(line)
                if len(self.raw_log) > 20: self.raw_log.pop(0)
                logger.info(f"📡 [spawn-bot] {line}")

            if event.chat_id not in Config.SPAM_GROUPS: return
            if not text: return
            if not self._is_spawn_text(clean):
                return
            if not self._has_allowed_emoji(clean):
                self.rejected += 1
                logger.info(f"   ↳ reject: no 🔵🟣🟠 in text")
                return

            skey = (event.chat_id, event.message.id)
            async with self.lock:
                if skey in self.spawn_state:
                    return
                state = {
                    "chat_id": event.chat_id,
                    "spawn_msg_id": event.message.id,
                    "w_sent": False,
                    "w_reply_id": None,
                    "w_sender_uid": None,
                    "catch_cmd": None,
                    "catch_sent_by": set(),
                    "hint_seen": set(),
                    "ts": time.time(),
                }
                self.spawn_state[skey] = state
                self.accepted += 1
                self._purge_old_states()

            logger.info(f"✅ [auto-catch] ACCEPTED chat={event.chat_id} msg={event.message.id}")
            asyncio.create_task(self._w_worker(state))
        except Exception as e:
            logger.warning(f"auto-catch spawn_handler: {e}")

    async def _w_worker(self, state):
        """Try ninjas one at a time until ONE succeeds."""
        chat_id = state["chat_id"]; msg_id = state["spawn_msg_id"]
        candidates = list(self.bot.ninja_clients)
        random.shuffle(candidates)
        logger.info(f"🥷 [auto-catch] /w worker start — {len(candidates)} candidates")

        for client in candidates:
            if state["w_sent"]: return
            uid = getattr(client, "tg_user_id", None)
            if not uid: continue
            try:
                sent = await asyncio.wait_for(
                    client.send_message(chat_id, "/w", reply_to=msg_id), timeout=15)
                state["w_sent"] = True
                state["w_reply_id"] = sent.id
                state["w_sender_uid"] = uid
                self.w_sent += 1
                logger.info(f"🥷 [auto-catch {uid}] /w ✅ → chat={chat_id} reply_id={sent.id}")
                return
            except FloodWaitError as e:
                logger.warning(f"⏳ [{uid}] /w FloodWait {e.seconds}s → next")
                continue
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ [{uid}] /w timeout → next")
                continue
            except Exception as e:
                logger.warning(f"⚠️ [{uid}] /w {type(e).__name__}: {str(e)[:100]}")
                continue

        self.w_failed += 1
        logger.error(f"❌ [auto-catch] ALL ninjas failed /w for chat={chat_id}")

    # ---------- hint handler ----------
    async def hint_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid: return
            if event.chat_id not in Config.SPAM_GROUPS: return
            if event.sender_id != Config.AUTO_HINT_BOT_ID: return

            reply_to = event.reply_to_msg_id
            if not reply_to: return

            state = None
            async with self.lock:
                for st in self.spawn_state.values():
                    if st["chat_id"] != event.chat_id: continue
                    if st.get("w_reply_id") == reply_to or st.get("spawn_msg_id") == reply_to:
                        state = st; break
            if not state: return

            text = self._get_text(event)
            if not text: return
            clean = self._clean_invisible(text)
            m = re.search(r"(/catch(?:@\w+)?\s+[^\n]+)", clean)
            if not m: return
            catch_cmd = m.group(1).strip(" `\n\r")

            mid = event.message.id
            async with self.lock:
                if mid in state["hint_seen"]: return
                state["hint_seen"].add(mid)
                if state["catch_cmd"]: return
                state["catch_cmd"] = catch_cmd

            logger.info(f"🎯 [auto-catch] HINT chat={event.chat_id} cmd={catch_cmd!r}")
            await self._broadcast_catch(state, catch_cmd)
        except Exception as e:
            logger.warning(f"auto-catch hint_handler: {e}")

    async def _broadcast_catch(self, state, catch_cmd):
        if not self.selected_ids:
            logger.warning("⚠️ [auto-catch] no /auto IDs — skip")
            return
        chat_id = state["chat_id"]
        uid_map = {}
        for c in self.bot.ninja_clients:
            u = getattr(c, "tg_user_id", None)
            if u: uid_map[u] = c

        tasks = []
        for uid in self.selected_ids:
            if uid in state["catch_sent_by"]: continue
            client = uid_map.get(uid)
            if not client:
                logger.warning(f"   ↳ /auto ID {uid} not in pool"); continue
            state["catch_sent_by"].add(uid)
            tasks.append(self._send_catch(client, uid, chat_id, catch_cmd))
        if tasks:
            logger.info(f"📢 Broadcasting /catch to {len(tasks)} selected ninjas")
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_catch(self, client, uid, chat_id, catch_cmd):
        try:
            await asyncio.wait_for(client.send_message(chat_id, catch_cmd), timeout=20)
            self.catch_sent += 1
            logger.info(f"🥷 [{uid}] /catch ✅ → {chat_id}  cmd={catch_cmd!r}")
        except FloodWaitError as e:
            logger.warning(f"⏳ [{uid}] /catch FloodWait {e.seconds}s")
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ [{uid}] /catch timeout")
        except Exception as e:
            logger.warning(f"⚠️ [{uid}] /catch {type(e).__name__}: {str(e)[:100]}")

    # ---------- register ----------
    def register(self, client):
        client.add_event_handler(self.spawn_handler,
                                 events.NewMessage(from_users=Config.AUTO_SPAWN_BOT_ID))
        client.add_event_handler(self.hint_handler,
                                 events.NewMessage(from_users=Config.AUTO_HINT_BOT_ID))

    def stats_line(self) -> str:
        return (f"acc={self.accepted} rej={self.rejected} w={self.w_sent} "
                f"wf={self.w_failed} catch={self.catch_sent} sel={len(self.selected_ids)}")


# ══════════════════════════════════════════════════════════════════
#  NINJA SYNC
# ══════════════════════════════════════════════════════════════════
class NinjaSync:
    def __init__(self, bot):
        self.bot = bot
        self.stats_lock = asyncio.Lock()
        self.stats = {"checked": 0, "imported": 0, "updated": 0, "misses": 0, "errors": 0}
        self.running = False
        self.cancel_requested = False
        self.current_task = None
        self.ranges = []
        self.worker_progress = {}
        self.start_id = Config.SYNC_START_ID
        self.end_id = Config.SYNC_END_ID
        self.started_at = None
        self.control_group_id = Config.SYNC_CONTROL_GROUP_ID

    async def load_settings(self):
        try:
            doc = await self.bot.db.system_col.find_one({"key": "ninja_sync_settings"})
            if doc and isinstance(doc.get("control_group_id"), int) and doc["control_group_id"] != 0:
                self.control_group_id = doc["control_group_id"]
        except Exception as e:
            logger.warning(f"load_settings: {e}")

    async def save_control_group(self, chat_id):
        self.control_group_id = chat_id
        await self.bot.db.system_col.update_one(
            {"key": "ninja_sync_settings"}, {"$set": {"control_group_id": chat_id}}, upsert=True)

    async def start(self, start_id, end_id):
        if self.running:
            return False, "⚠️ Sync က အလုပ်လုပ်နေဆဲ။ /nsynccancel နဲ့ ရပ်ပါ။"
        if self.control_group_id == 0:
            return False, "❌ Control group ID မသတ်မှတ်ရသေး။ /nsyncsetgroup -100xxx"
        if not self.bot.ninja_clients:
            return False, "❌ Ninja pool မရှိ။ /addninja နဲ့ ထည့်ပါ။"

        self.running = True
        self.cancel_requested = False
        self.stats = {"checked": 0, "imported": 0, "updated": 0, "misses": 0, "errors": 0}
        self.start_id, self.end_id = start_id, end_id
        self.started_at = time.time()
        self.worker_progress = {}

        skip = set()
        if Config.SYNC_SKIP_ALREADY_SYNCED:
            cursor = self.bot.db.characters_col.find(
                {"synced_via_check": True, "char_id": {"$regex": r"^BOD\d+$"}}, {"char_id": 1})
            async for d in cursor:
                try: skip.add(int(d["char_id"][3:]))
                except Exception: pass
        all_ids = [i for i in range(start_id, end_id + 1) if i not in skip]
        total = len(all_ids)
        if total == 0:
            self.running = False
            return False, "✅ IDs အားလုံး already-synced ဖြစ်နေပြီ။"

        num_ninjas = len(self.bot.ninja_clients)
        chunk_size = (total + num_ninjas - 1) // num_ninjas
        self.ranges = []
        for i in range(num_ninjas):
            s = i * chunk_size
            e = min(s + chunk_size, total)
            if s < total:
                self.ranges.append(all_ids[s:e])

        self.current_task = asyncio.create_task(self._run())

        preview_pairs = list(zip(self.bot.ninja_clients, self.bot.ninja_names))[:8]
        preview_lines = []
        for idx, (_c, n) in enumerate(preview_pairs):
            if idx < len(self.ranges):
                r = self.ranges[idx]
                preview_lines.append(f"  {idx+1}. <code>{escape_html(n)}</code> → <code>{r[0]}..{r[-1]}</code> ({len(r)})")
        preview = "\n".join(preview_lines)

        return True, (
            f"🔄 <b>Ninja Sync Started</b>\n"
            f"📊 Total: <code>{total}</code> ids ({start_id}..{end_id})\n"
            f"⏭️ Skipped: <code>{len(skip)}</code>\n"
            f"🥷 Ninjas: <code>{num_ninjas}</code>\n"
            f"📦 Per ninja: ~<code>{chunk_size}</code>\n"
            f"📁 Group: <code>{self.control_group_id}</code>\n\n"
            f"<b>Preview (first 8):</b>\n{preview}\n\n"
            f"Progress: /nsyncstatus · Stop: /nsynccancel"
        )

    async def cancel(self):
        if not self.running: return "ℹ️ Sync မလုပ်နေပါ။"
        self.cancel_requested = True
        return "🛑 Cancel requested — ninjas က current ID ပြီးမှ ရပ်မယ်။"

    async def _progress_loop(self, total):
        while self.running and not self.cancel_requested:
            await asyncio.sleep(Config.SYNC_PROGRESS_INTERVAL)
            if not self.running: break
            async with self.stats_lock: s = dict(self.stats)
            elapsed = max(1, int(time.time() - (self.started_at or time.time())))
            rate = s["checked"] / elapsed
            remaining = max(0, total - s["checked"])
            eta = int(remaining / rate) if rate > 0 else 0
            worker_lines = []
            for i in range(min(6, len(self.ranges))):
                done = self.worker_progress.get(i, 0); tot = len(self.ranges[i])
                worker_lines.append(f"  [{i+1}] <code>{done}/{tot}</code>")
            try:
                await self.bot.bot_client.send_message(
                    Config.OWNER_ID,
                    f"📊 <b>Progress</b>\n✔️ <code>{s['checked']}/{total}</code>\n"
                    f"🆕 <code>{s['imported']}</code> · 🔄 <code>{s['updated']}</code> "
                    f"· ➖ <code>{s['misses']}</code> · ⚠️ <code>{s['errors']}</code>\n"
                    f"⏱️ <code>{rate:.2f}/s</code> · ETA <code>{eta//60}m{eta%60}s</code>\n\n"
                    + "\n".join(worker_lines),
                    parse_mode="html")
            except Exception as e:
                logger.warning(f"progress_loop send: {e}")

    async def _warmup(self, client, name):
        username = Config.SYNC_TARGET_BOT_USERNAME
        if not username.startswith("@"): username = "@" + username
        for target in (username, Config.SYNC_TARGET_BOT_ID):
            try:
                await asyncio.wait_for(client.send_message(target, "/start"),
                                       timeout=Config.SYNC_WARMUP_TIMEOUT)
                await asyncio.sleep(Config.SYNC_WARMUP_DELAY)
                return True
            except asyncio.TimeoutError: pass
            except FloodWaitError as e:
                logger.warning(f"⏳ [{name}] warmup FloodWait {e.seconds}s")
            except Exception: pass
        return False

    async def _check_one(self, client, name, num):
        for attempt in range(Config.SYNC_MAX_COOLDOWN_RETRIES + 1):
            if self.cancel_requested: return ("cancelled", None)
            try:
                recent = await asyncio.wait_for(
                    client.get_messages(Config.SYNC_TARGET_BOT_USERNAME, limit=1), timeout=10)
                last_id = recent[0].id if recent else 0
            except Exception:
                last_id = 0
            try:
                async with client.conversation(Config.SYNC_TARGET_BOT_USERNAME,
                                               timeout=Config.SYNC_REPLY_TIMEOUT) as conv:
                    await asyncio.wait_for(conv.send_message(f".check {num}"), timeout=15)
                    deadline = time.time() + Config.SYNC_REPLY_TIMEOUT
                    reply = None
                    while True:
                        rem = deadline - time.time()
                        if rem <= 0: break
                        try: msg = await conv.get_response(timeout=rem)
                        except asyncio.TimeoutError: break
                        if msg.sender_id == Config.SYNC_TARGET_BOT_ID and msg.id > last_id:
                            reply = msg; break
                    if reply is None: return ("miss", None)
                text = reply.raw_text or ""
                info = parse_catchbot_check(text)
                if not info:
                    low = text.lower()
                    if any(h in low for h in ("cooldown","please wait","slow down","too fast",
                                             "try again in","rate limit","flood")):
                        await asyncio.sleep(Config.SYNC_COOLDOWN_BACKOFF); continue
                    return ("miss", reply)
                if not (reply.photo or reply.video or reply.document):
                    return ("error", reply)
                return ("ok", reply)
            except FloodWaitError as e:
                if e.seconds > 60: return ("error", None)
                await asyncio.sleep(e.seconds + 1); continue
            except errors.ChatWriteForbiddenError:
                return ("error", None)
            except asyncio.TimeoutError:
                return ("miss", None)
            except Exception:
                await asyncio.sleep(2); continue
        return ("error", None)

    async def _store(self, client, name, info, reply_msg):
        char_id = f"BOD{info['id']}"
        try:
            existing = await self.bot.db.characters_col.find_one({"char_id": char_id})
            r_info = resolve_rarity(info["rarity_raw"], existing)
            if not r_info:
                r_info = {"tier": "COMMON", "name": f"{RARITY_EMOJI['COMMON']} {RARITY_DISPLAY_NAME['COMMON']}",
                          "value": _RARITY_VALUE_MAP["COMMON"], "is_cnft": False}
            fwd = await asyncio.wait_for(
                client.send_message(self.control_group_id, "", file=reply_msg.media), timeout=60)
            storage_id = fwd.id
            phash = await compute_phash_for_message(reply_msg)
            data = {
                "char_id": char_id, "name": info["name"], "category": info["category"],
                "rarity": r_info["name"], "rarity_tier": r_info["tier"],
                "storage_msg_id": storage_id, "currency_value": r_info["value"],
                "event": info["event"] or "General", "photo_phash": phash,
                "auto_imported_from": "catch_bot", "source_rarity": info["rarity_raw"],
                "synced_via_check": True, "last_synced_at": time.time(),
            }
            if r_info.get("is_cnft"): data["spawnable"] = False
            if existing:
                old_sid = existing.get("storage_msg_id")
                if old_sid and old_sid != storage_id:
                    try: await client.delete_messages(self.control_group_id, [old_sid])
                    except Exception: pass
                await self.bot.db.characters_col.update_one({"char_id": char_id}, {"$set": data})
                return "updated"
            else:
                data.update({"spawn_count": 0, "spawn_limit": 0, "created_at": time.time()})
                await self.bot.db.characters_col.insert_one(data)
                return "imported"
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1); return "error"
        except Exception as e:
            logger.error(f"❌ [{name}] store {char_id}: {type(e).__name__}: {e}")
            return "error"

    async def _worker(self, client, name, my_ids, worker_index):
        try:
            if not await self._warmup(client, name): return
            total = len(my_ids)
            for i, num in enumerate(my_ids, 1):
                if self.cancel_requested: return
                outcome, reply = await self._check_one(client, name, num)
                if outcome == "cancelled": return
                if outcome == "ok" and reply is not None:
                    info = parse_catchbot_check(reply.raw_text or "")
                    if info:
                        result = await self._store(client, name, info, reply)
                        async with self.stats_lock:
                            self.stats["checked"] += 1
                            if result == "imported":   self.stats["imported"] += 1
                            elif result == "updated":  self.stats["updated"] += 1
                            else:                       self.stats["errors"] += 1
                    else:
                        async with self.stats_lock:
                            self.stats["checked"] += 1; self.stats["errors"] += 1
                elif outcome == "miss":
                    async with self.stats_lock:
                        self.stats["checked"] += 1; self.stats["misses"] += 1
                else:
                    async with self.stats_lock:
                        self.stats["checked"] += 1; self.stats["errors"] += 1
                self.worker_progress[worker_index] = i
                await asyncio.sleep(Config.SYNC_PACE_PER_CHECK)
        except Exception as e:
            logger.exception(f"❌ [{name}] worker CRASHED: {e}")

    async def _run(self):
        total = sum(len(r) for r in self.ranges)
        progress_task = asyncio.create_task(self._progress_loop(total))
        worker_tasks = []
        try:
            for idx, (client, name) in enumerate(zip(self.bot.ninja_clients, self.bot.ninja_names)):
                if idx >= len(self.ranges) or self.cancel_requested: break
                my_ids = self.ranges[idx]
                if not my_ids: continue
                worker_tasks.append(asyncio.create_task(self._worker(client, name, my_ids, idx)))
                await asyncio.sleep(Config.SYNC_NINJA_STAGGER)
            await asyncio.gather(*worker_tasks, return_exceptions=True)
        except Exception as e:
            logger.exception(f"❌ _run error: {e}")
        finally:
            self.running = False
            progress_task.cancel()
            try: await progress_task
            except asyncio.CancelledError: pass
            async with self.stats_lock: s = dict(self.stats)
            elapsed = int(time.time() - (self.started_at or time.time()))
            header = "🛑 <b>Cancelled</b>" if self.cancel_requested else "🏁 <b>Finished</b>"
            try:
                await self.bot.bot_client.send_message(
                    Config.OWNER_ID,
                    f"{header} <b>Ninja Sync</b>\n\n"
                    f"✔️ Checked: <code>{s['checked']}</code>\n"
                    f"🆕 Imported: <code>{s['imported']}</code>\n"
                    f"🔄 Updated: <code>{s['updated']}</code>\n"
                    f"➖ Misses: <code>{s['misses']}</code>\n"
                    f"⚠️ Errors: <code>{s['errors']}</code>\n"
                    f"⏱️ Total: <code>{elapsed//60}m{elapsed%60}s</code>",
                    parse_mode="html")
            except Exception: pass
            self.cancel_requested = False


# ══════════════════════════════════════════════════════════════════
#  MAIN BOT
# ══════════════════════════════════════════════════════════════════
class SovereignBot:
    def __init__(self, db):
        self.db = db
        self.bot_client = TelegramClient("bot_main_session", Config.API_ID, Config.API_HASH,
                                          flood_sleep_threshold=60)
        self.bot_id = None
        self.ninja_clients = []
        self.ninja_names = []
        self.ninja_ids = set()
        self.ninja_warmed = {}
        self.ninja_spam_tasks = {}
        self.delete_and_taunt_targets = {}
        self.phrase_lists = {}
        self.phrase_indices = {}
        self.chat_admin_cache = {}
        self.admin_cache_locks = {}
        # old SPAWN_GROUP_2 auto-ninja
        self.ninja_spawn_marker = {"key": None, "selected": set()}
        self.ninja_spawn_tracker = {}
        self.ninja_latest_spawn = {}
        self.start_spam_tasks = {}
        self.start_spam_target = None
        self.start_spam_active = False
        self.sync = NinjaSync(self)
        self.auto_catch = AutoCatchEngine(self)
        self._register_handlers()

    # ---------- TAUNT DB ----------
    async def load_taunt_targets(self):
        async for doc in self.db.taunt_targets.find():
            cid = doc["chat_id"]; tids = doc.get("target_ids", [])
            if tids: self.delete_and_taunt_targets[cid] = set(tids)

    async def _add_taunt_target(self, cid, tid):
        self.delete_and_taunt_targets.setdefault(cid, set()).add(tid)
        await self.db.taunt_targets.update_one({"chat_id": cid}, {"$addToSet": {"target_ids": tid}}, upsert=True)

    async def _remove_taunt_target(self, cid, tid):
        if cid in self.delete_and_taunt_targets:
            self.delete_and_taunt_targets[cid].discard(tid)
            if not self.delete_and_taunt_targets[cid]:
                del self.delete_and_taunt_targets[cid]
                await self.db.taunt_targets.delete_one({"chat_id": cid})
            else:
                await self.db.taunt_targets.update_one({"chat_id": cid}, {"$pull": {"target_ids": tid}})

    async def _clear_taunt_targets(self, cid):
        if cid in self.delete_and_taunt_targets:
            del self.delete_and_taunt_targets[cid]
            await self.db.taunt_targets.delete_one({"chat_id": cid})

    # ---------- ADMIN CACHE ----------
    async def _scan_admin_clients(self, cid):
        async def check(c):
            try:
                p = await c.get_permissions(cid, "me")
                if p and getattr(p, "is_admin", False): return c
            except FloodWaitError as e: await asyncio.sleep(e.seconds + 1)
            except Exception: pass
            return None
        results = await asyncio.gather(*[check(c) for c in self.ninja_clients], return_exceptions=False)
        return [c for c in results if c is not None]

    async def _get_admin_clients(self, cid):
        now = time.time()
        cached = self.chat_admin_cache.get(cid)
        if cached and now < cached[1]: return cached[0]
        if cid not in self.admin_cache_locks: self.admin_cache_locks[cid] = asyncio.Lock()
        async with self.admin_cache_locks[cid]:
            cached = self.chat_admin_cache.get(cid)
            if cached and time.time() < cached[1]: return cached[0]
            admins = await self._scan_admin_clients(cid)
            self.chat_admin_cache[cid] = (admins, time.time() + Config.ADMIN_CACHE_TTL)
            return admins

    async def preload_admin_caches(self):
        targets = set(Config.SPAM_GROUPS)
        if not targets: return
        await asyncio.gather(*[self._get_admin_clients(g) for g in targets], return_exceptions=True)

    # ---------- AUTO-PROMOTE ----------
    async def _ninja_join_handler(self, event):
        try:
            me_id = getattr(event.client, "tg_user_id", None)
            if not me_id: return
            joined = False
            if event.user_joined or event.user_added:
                try:
                    if event.user_id == me_id: joined = True
                except Exception: pass
            if not joined: return
            cid = event.chat_id
            asyncio.create_task(self._auto_promote_ninjas(cid))
        except Exception: pass

    async def _auto_promote_ninjas(self, cid):
        try:
            perms = await self.bot_client.get_permissions(cid, "me")
            if not (perms and getattr(perms, "is_admin", False)): return
            if not (getattr(perms, "add_admins", False) or getattr(perms, "is_creator", False)): return
            promoted = already = failed = 0
            for c in self.ninja_clients:
                try:
                    uid = getattr(c, "tg_user_id", None)
                    if not uid:
                        me = await c.get_me(); uid = me.id; c.tg_user_id = uid
                    np = await self.bot_client.get_permissions(cid, uid)
                    if np and getattr(np, "is_admin", False): already += 1; continue
                    await self.bot_client.edit_admin(cid, uid, change_info=False, post_messages=True,
                        edit_messages=True, delete_messages=True, ban_users=True, invite_users=True,
                        pin_messages=True, add_admins=False, anonymous=False, manage_call=False)
                    promoted += 1
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1); failed += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.4)
        except Exception: pass

    # ---------- START-SPAM ----------
    async def _start_spam_worker(self, ninja, uid, target):
        await asyncio.sleep(random.uniform(Config.START_SPAM_MIN_DELAY, Config.START_SPAM_MAX_DELAY))
        while self.start_spam_active and uid in self.start_spam_tasks:
            try:
                await asyncio.wait_for(ninja.send_message(target, "/start"), timeout=20)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1); continue
            except asyncio.CancelledError: break
            except Exception: pass
            jitter = Config.START_SPAM_INTERVAL * random.uniform(-Config.START_SPAM_JITTER, Config.START_SPAM_JITTER)
            wait = max(30, Config.START_SPAM_INTERVAL + jitter); waited = 0
            while waited < wait and self.start_spam_active:
                await asyncio.sleep(5); waited += 5

    async def start_start_spam(self, target):
        if self.start_spam_active: return 0
        if not self.ninja_clients: return 0
        self.start_spam_active = True; self.start_spam_target = target; started = 0
        for c in self.ninja_clients:
            try:
                uid = getattr(c, "tg_user_id", None)
                if not uid:
                    me = await c.get_me(); uid = me.id; c.tg_user_id = uid
                self.start_spam_tasks[uid] = asyncio.create_task(self._start_spam_worker(c, uid, target))
                started += 1
            except Exception: pass
        return started

    async def stop_start_spam(self):
        if not self.start_spam_active: return 0
        self.start_spam_active = False; stopped = 0
        for uid, t in list(self.start_spam_tasks.items()):
            if not t.done(): t.cancel(); stopped += 1
        self.start_spam_tasks.clear(); self.start_spam_target = None
        return stopped

    # ---------- OLD SPAWN_GROUP_2 ----------
    async def _ninja_spawn_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid: return
            if event.chat_id != Config.SPAWN_GROUP_2: return
            if self.sync.running: return
            text = event.text or ""
            if not text:
                try:
                    if event.message and event.message.message: text = event.message.message
                except Exception: pass
            if not text: return
            upper = text.upper()
            if not ("A CHARACTER HAS SPAWNED" in upper or "ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs sᴘᴀᴡɴᴇᴅ" in text): return
            if any(e in text for e in Config.NINJA_IGNORED_EMOJIS): return
            skey = f"{event.chat_id}:{event.message.id}"
            if self.ninja_spawn_marker.get("key") != skey:
                avail = list(self.ninja_ids)
                if not avail: return
                picked = set(avail) if len(avail) <= Config.NINJA_PICK_COUNT else set(random.sample(avail, Config.NINJA_PICK_COUNT))
                self.ninja_spawn_marker["key"] = skey; self.ninja_spawn_marker["selected"] = picked
            if uid not in self.ninja_spawn_marker["selected"]: return
            await asyncio.sleep(random.uniform(Config.NINJA_W_DELAY_MIN, Config.NINJA_W_DELAY_MAX))
            try:
                r = await event.message.reply("/w")
                self.ninja_spawn_tracker[(uid, r.id)] = event.chat_id
                self.ninja_latest_spawn[uid] = event.chat_id
            except Exception: pass
        except Exception as e:
            logger.warning(f"spawn handler: {e}")

    async def _ninja_hint_handler(self, event):
        try:
            uid = getattr(event.client, "tg_user_id", None)
            if not uid or event.chat_id != Config.SPAWN_GROUP_2: return
            if event.sender_id != Config.SPAWN_BOT_2_ID or not event.reply_to_msg_id: return
            if (uid, event.reply_to_msg_id) not in self.ninja_spawn_tracker: return
            text = event.text or ""
            if not text:
                try:
                    if event.message and event.message.message: text = event.message.message
                except Exception: pass
            if not text: return
            m = re.search(r"(/catch(?:@\w+)?\s+[^\n]+)", text)
            if not m: return
            cmd = m.group(1).strip(" `\n\r")
            grp = self.ninja_spawn_tracker.get((uid, event.reply_to_msg_id)) or self.ninja_latest_spawn.get(uid)
            if grp:
                try: await event.client.send_message(grp, cmd)
                except Exception: pass
        except Exception: pass

    def _register_ninja_handlers(self, client):
        client.add_event_handler(self._ninja_spawn_handler, events.NewMessage(from_users=Config.SPAWN_BOT_2_ID))
        client.add_event_handler(self._ninja_hint_handler, events.NewMessage(chats=Config.SPAWN_GROUP_2))
        client.add_event_handler(self._ninja_join_handler, events.ChatAction())
        self.auto_catch.register(client)

    # ---------- LOAD NINJAS ----------
    async def load_ninja_pools(self):
        for c in self.ninja_clients:
            try:
                if c.is_connected(): await c.disconnect()
            except Exception: pass
        self.ninja_clients.clear(); self.ninja_names.clear(); self.ninja_ids.clear()
        async for doc in self.db.ninja_col.find():
            sess = doc.get("session")
            if not sess: continue
            try:
                c = TelegramClient(StringSession(sess), Config.API_ID, Config.API_HASH, flood_sleep_threshold=0)
                await c.start()
                if await c.is_user_authorized():
                    me = await c.get_me()
                    c.tg_user_id = me.id
                    self.ninja_clients.append(c)
                    self.ninja_names.append(doc.get("name", f"Ninja-{len(self.ninja_clients)}"))
                    self.ninja_ids.add(me.id)
                    self._register_ninja_handlers(c)
            except Exception as e:
                logger.error(f"❌ Ninja load failed: {e}")
        logger.info(f"🚀 Ninja Pool ready: {len(self.ninja_clients)} clients.")

    # ---------- HELPERS ----------
    def format_mention(self, uid, name):
        return f"<a href='tg://user?id={uid}'>{escape_html(name)}</a>"

    async def fetch_phrases(self):
        doc = await self.db.system_col.find_one({"key": "shadow_taunts"})
        return list(doc["value"]) if doc and doc.get("value") else ["မင်းရဲ့စကားတွေ ငါမှတ်ထားတယ်"]

    async def get_next_phrase(self, cid):
        if cid not in self.phrase_lists:
            p = await self.fetch_phrases(); random.shuffle(p)
            self.phrase_lists[cid] = p; self.phrase_indices[cid] = 0
        p = self.phrase_lists[cid]; i = self.phrase_indices[cid]
        ph = p[i]; self.phrase_indices[cid] = (i + 1) % len(p)
        return ph

    # ---------- SPAM ----------
    async def _start_spam_loop(self, chat_ids):
        key = tuple(sorted(chat_ids))
        if self.ninja_spam_tasks.get(key): return
        self.ninja_spam_tasks[key] = True
        if not self.ninja_clients: return
        flood_until = {}; lock = asyncio.Lock()
        async def send(c, cid):
            async with lock:
                if c in flood_until and flood_until[c] > datetime.now(): return
            try: await c.send_message(cid, SPAM_TEXT)
            except FloodWaitError as e:
                async with lock: flood_until[c] = datetime.now() + timedelta(seconds=e.seconds + 1)
            except Exception: pass
        async def loop():
            while self.ninja_spam_tasks.get(key):
                tasks = []
                for cid in chat_ids:
                    c = None
                    for _ in range(3):
                        cc = random.choice(self.ninja_clients)
                        async with lock:
                            if cc not in flood_until or flood_until[cc] < datetime.now():
                                c = cc; break
                    if c is None: await asyncio.sleep(0.3); continue
                    tasks.append(send(c, cid))
                if tasks: await asyncio.gather(*tasks)
                await asyncio.sleep(0.05)
        asyncio.create_task(loop())

    async def _taunt_user(self, cid, tid, msg_id, tname="Target"):
        admins = await self._get_admin_clients(cid)
        if not admins: return
        c = random.choice(admins)
        try: await c.delete_messages(cid, [msg_id])
        except Exception: pass
        mention = self.format_mention(tid, tname)
        phrase = await self.get_next_phrase(cid)
        try: await c.send_message(cid, f"{mention} {phrase}", parse_mode="html")
        except Exception: pass

    # ══════════════════════════════════════════════════════════════
    #  COMMANDS
    # ══════════════════════════════════════════════════════════════
    def _register_handlers(self):

        # -------- /auto --------
        @self.bot_client.on(events.NewMessage(pattern=r"^/auto(?:@\w+)?(?:\s+(.+))?$"))
        async def auto_cmd(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            arg = (event.pattern_match.group(1) or "").strip().lower()

            if arg == "clear":
                self.auto_catch.selected_ids.clear()
                await self.auto_catch.save_settings()
                return await event.reply("🧹 Auto-catch ID list cleared.")

            if arg == "list":
                ids = sorted(self.auto_catch.selected_ids)
                if not ids: return await event.reply("📭 Empty. Reply to an ID list with `/auto`.")
                pool = set()
                for c in self.ninja_clients:
                    u = getattr(c, "tg_user_id", None)
                    if u: pool.add(u)
                lines = [f"{i}. `{x}` {'✅' if x in pool else '❌'}" for i, x in enumerate(ids, 1)]
                return await event.reply(
                    f"📋 **Auto-Catch IDs ({len(ids)}):**\n" + "\n".join(lines),
                    parse_mode="markdown")

            reply = await event.get_reply_message()
            if not reply or not reply.text:
                return await event.reply(
                    "⚠️ **Usage:**\n"
                    "• Reply to a message with IDs (one per line) → `/auto`\n"
                    "• `/auto list` — show selected\n"
                    "• `/auto clear` — clear all"
                )

            ids = []
            for line in reply.text.splitlines():
                line = line.strip()
                m = re.match(r"^(\d+)", line)
                if m:
                    try:
                        n = int(m.group(1))
                        if n > 0: ids.append(n)
                    except Exception: pass

            if not ids: return await event.reply("❌ No valid IDs found in replied message.")

            seen = set(); uniq = []
            for i in ids:
                if i not in seen:
                    seen.add(i); uniq.append(i)

            self.auto_catch.selected_ids = set(uniq)
            await self.auto_catch.save_settings()

            pool = set()
            for c in self.ninja_clients:
                u = getattr(c, "tg_user_id", None)
                if u: pool.add(u)
            in_pool = [i for i in uniq if i in pool]
            missing = [i for i in uniq if i not in pool]

            msg = f"✅ **Auto-catch set**\n📋 Total: `{len(uniq)}`\n🥷 In pool: `{len(in_pool)}`\n"
            if missing:
                msg += f"⚠️ Not in pool: `{len(missing)}`\n"
                msg += "`" + "` `".join(str(m) for m in missing[:15]) + "`"
                if len(missing) > 15: msg += f" …+{len(missing)-15}"
            await event.reply(msg, parse_mode="markdown")

        # -------- /actest : diagnostic --------
        @self.bot_client.on(events.NewMessage(pattern=r"^/actest(?:@\w+)?$"))
        async def actest_cmd(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            ac = self.auto_catch
            raw_lines = ac.raw_log[-10:] if ac.raw_log else ["(none — no spawn-bot msg seen in SPAM_GROUPS yet)"]
            await event.reply(
                f"🔍 **AUTO-CATCH DIAG**\n\n"
                f"🎨 Allow: `{' '.join(Config.AUTO_CATCH_EMOJI_PREFIXES)}`\n"
                f"🤖 Spawn bot: `{Config.AUTO_SPAWN_BOT_ID}`\n"
                f"💡 Hint bot: `{Config.AUTO_HINT_BOT_ID}`\n"
                f"📁 SPAM groups: `{len(Config.SPAM_GROUPS)}`\n"
                f"🎯 Selected: `{len(ac.selected_ids)}`\n"
                f"📊 Stats: `{ac.stats_line()}`\n\n"
                f"**📡 Last {len(raw_lines)} spawn-bot msgs seen:**\n"
                + "\n".join(f"`{l}`" for l in raw_lines),
                parse_mode="markdown")

        # -------- ninja management --------
        @self.bot_client.on(events.NewMessage(pattern=r"^/addninja(?:@\w+)?(?:\s+(.*?))?(?:\s+(.*))?$"))
        async def add_ninja(event):
            if event.sender_id != Config.OWNER_ID: return
            cmd = event.pattern_match.group(1); sess = event.pattern_match.group(2)
            name = cmd if cmd and not sess else "Ninja"
            if not sess:
                r = await event.get_reply_message()
                if r and r.text:
                    sess = r.text.strip()
                    if cmd and not cmd.startswith("session"): name = cmd
                else: return await event.reply("❓ Usage: /addninja <name> <session>")
            if not sess or len(sess) < 10: return await event.reply("❌ Invalid session.")
            async for d in self.db.ninja_col.find():
                if d.get("session") == sess: return await event.reply("⚠️ Already exists.")
            await self.db.ninja_col.insert_one({"name": name, "session": sess})
            try:
                c = TelegramClient(StringSession(sess), Config.API_ID, Config.API_HASH, flood_sleep_threshold=0)
                await c.start()
                me = await c.get_me(); c.tg_user_id = me.id
                self.ninja_clients.append(c); self.ninja_names.append(name); self.ninja_ids.add(me.id)
                self._register_ninja_handlers(c); self.chat_admin_cache.clear()
                await event.reply(f"✅ '{name}' (ID: {me.id}) added. Total: {len(self.ninja_clients)}")
            except Exception as e:
                await event.reply(f"❌ Failed: {e}")
                await self.db.ninja_col.delete_one({"session": sess})

        @self.bot_client.on(events.NewMessage(pattern=r"^/listninja(?:@\w+)?$"))
        async def list_ninja(event):
            if event.sender_id != Config.OWNER_ID: return
            if not self.ninja_clients: return await event.reply("📭 No ninjas.")
            online = 0
            lines = [f"👥 **Ninja Pool ({len(self.ninja_clients)} loaded)**"]
            for i, (c, n) in enumerate(zip(self.ninja_clients, self.ninja_names)):
                try:
                    me = await c.get_me(); online += 1
                    full = f"{me.first_name or ''} {me.last_name or ''}".strip() or "No Name"
                    u = f"(@{me.username})" if me.username else ""
                    lines.append(f"  {i+1}. **{full}** {u} (ID: `{me.id}`) ✅")
                except Exception:
                    lines.append(f"  {i+1}. **{n}** ❌")
            lines.append(f"\n📊 Online: {online}/{len(self.ninja_clients)}")
            await event.reply("\n".join(lines), parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(pattern=r"^/removeninja(?:@\w+)?\s+(.+)$"))
        async def remove_ninja(event):
            if event.sender_id != Config.OWNER_ID: return
            target = event.pattern_match.group(1).strip()
            plist = await self.db.ninja_col.find().to_list(length=None)
            idx = None
            if target.isdigit(): idx = int(target) - 1
            else:
                for i, d in enumerate(plist):
                    if d.get("name") == target: idx = i; break
            if idx is None or idx < 0 or idx >= len(plist):
                return await event.reply(f"❌ Not found: {target}")
            doc = plist[idx]
            await self.db.ninja_col.delete_one({"_id": doc["_id"]})
            if idx < len(self.ninja_clients):
                c = self.ninja_clients.pop(idx); self.ninja_names.pop(idx)
                try: await c.disconnect()
                except Exception: pass
                self.chat_admin_cache.clear()
                await event.reply(f"✅ Removed '{doc.get('name')}'.")
            else: await event.reply("✅ Removed from DB.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/autoninja(?:@\w+)?$"))
        async def autoninja_status(event):
            if event.sender_id != Config.OWNER_ID: return
            ac = self.auto_catch
            sel_preview = ", ".join(str(x) for x in sorted(ac.selected_ids)[:12]) or "—"
            await event.reply(
                f"🥷 **AUTO-CATCH**\n"
                f"🤖 Spawn bot: `{Config.AUTO_SPAWN_BOT_ID}`\n"
                f"💡 Hint bot: `{Config.AUTO_HINT_BOT_ID}`\n"
                f"📍 Groups: `{len(Config.SPAM_GROUPS)}` (hardcore)\n"
                f"🎨 Allow: `{' '.join(Config.AUTO_CATCH_EMOJI_PREFIXES)}`\n"
                f"⏱️ Delay: `0.0s` (instant)\n"
                f"🎯 Selected IDs: `{len(ac.selected_ids)}`\n"
                f"📋 Preview: `{sel_preview}`\n\n"
                f"📊 Stats: `{ac.stats_line()}`",
                parse_mode="markdown")

        @self.bot_client.on(events.NewMessage(pattern=r"^/startspam(?:@\w+)?(?:\s+(@?\w+))?$"))
        async def startspam_cmd(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            arg = event.pattern_match.group(1)
            if not arg: return await event.reply("⚠️ Usage: /startspam @BotUsername")
            target = arg.lstrip("@").strip()
            if not target: return await event.reply("❌ Invalid username.")
            if self.start_spam_active: return await event.reply(f"⚠️ Already running → @{self.start_spam_target}")
            if not self.ninja_clients: return await event.reply("❌ Ninja pool empty.")
            n = await self.start_start_spam(target)
            await event.reply(f"🎯 START SPAM ON → @{target} · {n} workers · {Config.START_SPAM_INTERVAL}s interval")

        @self.bot_client.on(events.NewMessage(pattern=r"^/stopspam(?:@\w+)?$"))
        async def stopspam_cmd(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            if not self.start_spam_active: return await event.reply("ℹ️ Not running.")
            target = self.start_spam_target
            n = await self.stop_start_spam()
            await event.reply(f"🛑 START SPAM OFF · @{target} · stopped {n}")

        @self.bot_client.on(events.NewMessage(pattern=r"^/spamstatus(?:@\w+)?$"))
        async def spamstatus_cmd(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            if self.start_spam_active:
                await event.reply(f"🎯 ON · @{self.start_spam_target} · {len(self.start_spam_tasks)} workers")
            else: await event.reply("🎯 OFF")

        @self.bot_client.on(events.NewMessage(pattern=r"^/adm(?:@\w+)?(?:\s+(.+))?$"))
        async def adm_cmd(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            arg = event.pattern_match.group(1); target_chat = None
            if arg:
                raw = arg.strip()
                if re.match(r"^-?\d+$", raw): target_chat = int(raw)
                elif raw.startswith("@") or re.match(r"^[A-Za-z][A-Za-z0-9_]{3,}$", raw):
                    uname = raw.lstrip("@")
                    try:
                        e = await self.bot_client.get_entity(uname); target_chat = e.id
                    except Exception as ex: return await event.reply(f"❌ {ex}")
                else: return await event.reply("⚠️ Usage: /adm | /adm -100xxx | /adm @group")
            else:
                if event.is_private: return await event.reply("⚠️ Usage in DM: /adm -100xxx")
                target_chat = event.chat_id
            if not target_chat: return await event.reply("❌ No target.")
            if not self.ninja_clients: return await event.reply("❌ Empty pool.")
            try:
                p = await self.bot_client.get_permissions(target_chat, "me")
            except Exception as e: return await event.reply(f"❌ {e}")
            if not (p and getattr(p, "is_admin", False)): return await event.reply("❌ Bot not admin.")
            if not (getattr(p, "add_admins", False) or getattr(p, "is_creator", False)):
                return await event.reply("❌ No Add Admins perm.")
            status = await event.reply(f"⏳ Promoting {len(self.ninja_clients)} ninjas in `{target_chat}`...")
            promoted = already = failed = 0
            for c in self.ninja_clients:
                try:
                    uid = getattr(c, "tg_user_id", None)
                    if not uid:
                        me = await c.get_me(); uid = me.id; c.tg_user_id = uid
                    np = await self.bot_client.get_permissions(target_chat, uid)
                    if np and getattr(np, "is_admin", False): already += 1; continue
                    await self.bot_client.edit_admin(target_chat, uid, change_info=False,
                        post_messages=True, edit_messages=True, delete_messages=True, ban_users=True,
                        invite_users=True, pin_messages=True, add_admins=False, anonymous=False, manage_call=False)
                    promoted += 1
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1); failed += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.4)
            await status.edit(f"✅ `/adm` `{target_chat}` · promoted={promoted} already={already} failed={failed}")

        @self.bot_client.on(events.NewMessage(pattern=r"^ဖာသည်မသား$"))
        async def taunt(event):
            if event.sender_id != Config.OWNER_ID: return
            try: await event.delete()
            except Exception: pass
            r = await event.get_reply_message()
            if not r: return await event.reply("❌ Reply to a target.")
            t = await r.get_sender()
            if not t or t.id == Config.OWNER_ID: return
            cid = event.chat_id; tid = t.id; tname = t.first_name or "Target"
            admins = await self._get_admin_clients(cid)
            if not admins: return await event.reply("⚠️ No ninja admin here.")
            mention = self.format_mention(tid, tname)
            try: await self.bot_client.delete_messages(cid, [r.id])
            except Exception: pass
            await self._add_taunt_target(cid, tid)
            c = random.choice(admins); phrase = await self.get_next_phrase(cid)
            try: await c.send_message(cid, f"{mention} {phrase}", parse_mode="html")
            except Exception: pass
            await event.reply(f"✅ Taunt enabled for {mention}", parse_mode="html")

        @self.bot_client.on(events.NewMessage(pattern=r"^/remove_taunt(?:@\w+)?(?:\s+(\d+))?$"))
        async def remove_taunt(event):
            if event.sender_id != Config.OWNER_ID: return
            cid = event.chat_id; tid = event.pattern_match.group(1)
            if tid: await self._remove_taunt_target(cid, int(tid)); await event.reply(f"✅ Removed {tid}")
            elif event.is_reply:
                r = await event.get_reply_message(); t = await r.get_sender()
                await self._remove_taunt_target(cid, t.id); await event.reply("✅ Removed")

        @self.bot_client.on(events.NewMessage(pattern=r"^/clear_taunts(?:@\w+)?(?:\s+(-?\d+))?$"))
        async def clear_taunts(event):
            if event.sender_id != Config.OWNER_ID: return
            cid = int(event.pattern_match.group(1)) if event.pattern_match.group(1) else event.chat_id
            await self._clear_taunt_targets(cid); await event.reply("🧹 Cleared.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/spam(?:@\w+)?$"))
        async def spam_cmd(event):
            if event.sender_id != Config.OWNER_ID: return
            await self._start_spam_loop(Config.SPAM_GROUPS)
            await event.reply(f"🗣️ Spam started on {len(Config.SPAM_GROUPS)} groups.")

        @self.bot_client.on(events.NewMessage(pattern=r"^(ရပ်|/stop(?:@\w+)?)$"))
        async def stop_cmd(event):
            if event.sender_id != Config.OWNER_ID: return
            cid = event.chat_id; stopped = False
            for k in list(self.ninja_spam_tasks.keys()):
                if cid in k or event.sender_id == Config.OWNER_ID:
                    self.ninja_spam_tasks[k] = False; stopped = True
            await event.reply("🛑 Spam stopped." if stopped else "ℹ️ Nothing to stop.")

        @self.bot_client.on(events.NewMessage(pattern=r"^/go(?:@\w+)?$"))
        async def go_group(event):
            if event.sender_id != Config.OWNER_ID: return
            if not event.is_reply: return await event.reply("❌ Reply to invite link.")
            r = await event.get_reply_message()
            if not r.text: return await event.reply("❌ No text.")
            m = re.search(r"(https?://t\.me/(joinchat/|\+)[A-Za-z0-9_-]+)", r.text)
            if not m: return await event.reply("❌ No link.")
            link = m.group(0)
            h = link.split("joinchat/")[1].split("?")[0] if "joinchat/" in link else (link.split("+")[1].split("?")[0] if "+" in link else None)
            if not h: return await event.reply("❌ Bad link.")
            clients = self.ninja_clients.copy()
            if not clients: return await event.reply("❌ No clients.")
            await event.reply(f"⏳ Joining with {len(clients)} clients...")
            success = 0
            for c in clients:
                try:
                    await asyncio.wait_for(c(ImportChatInviteRequest(h)), timeout=20); success += 1
                except errors.rpcerrorlist.UserAlreadyParticipantError: success += 1
                except FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds, 30))
                    try: await c(ImportChatInviteRequest(h)); success += 1
                    except Exception: pass
                except Exception: pass
                await asyncio.sleep(0.3)
            self.chat_admin_cache.clear()
            try:
                chat = await clients[0].get_entity(link)
                await event.reply(f"✅ Joined `{chat.title}` ({success} clients). ID: `{chat.id}`")
            except Exception:
                await event.reply(f"✅ Joined ({success} clients).")

        @self.bot_client.on(events.NewMessage(pattern=r"^/status(?:@\w+)?$"))
        async def status_cmd(event):
            if event.sender_id != Config.OWNER_ID: return
            taunts = sum(len(s) for s in self.delete_and_taunt_targets.values())
            ss = f"ON → @{self.start_spam_target}" if self.start_spam_active else "OFF"
            sync_str = "RUNNING" if self.sync.running else "idle"
            await event.reply(
                f"📊 **Status**\n🤖 Pool: `{len(self.ninja_clients)}`\n"
                f"🎯 /startspam: `{ss}`\n🔄 Sync: `{sync_str}`\n"
                f"👹 Taunts: `{taunts}`\n"
                f"🕸️ Auto-Catch: `{self.auto_catch.stats_line()}`",
                parse_mode="markdown")

        @self.bot_client.on(events.NewMessage())
        async def watcher(event):
            if event.is_private: return
            if event.sender_id == self.bot_id or event.sender_id in self.ninja_ids: return
            cid, sid = event.chat_id, event.sender_id
            if cid in self.delete_and_taunt_targets and sid in self.delete_and_taunt_targets[cid]:
                if event.text:
                    try:
                        t = await event.get_sender(); name = t.first_name if t else "Target"
                    except Exception: name = "Target"
                    asyncio.create_task(self._taunt_user(cid, sid, event.id, name))

        # ═══ NINJA SYNC ═══
        @self.bot_client.on(events.NewMessage(pattern=r"^/nsync(?:@\w+)?(?:\s+(\d+))?(?:\s+(\d+))?$"))
        async def nsync_cmd(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            sa = event.pattern_match.group(1); ea = event.pattern_match.group(2)
            s = int(sa) if sa else Config.SYNC_START_ID
            e = int(ea) if ea else Config.SYNC_END_ID
            if s < 1 or e < s: return await event.reply("❌ Invalid range.")
            ok, msg = await self.sync.start(s, e)
            await event.reply(msg, parse_mode="html")

        @self.bot_client.on(events.NewMessage(pattern=r"^/nsyncsetgroup(?:@\w+)?\s+(-?\d+)$"))
        async def nsync_setgroup(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            cid = int(event.pattern_match.group(1))
            await self.sync.save_control_group(cid)
            await event.reply(f"✅ Control group set to <code>{cid}</code>", parse_mode="html")

        @self.bot_client.on(events.NewMessage(pattern=r"^/nsyncstatus(?:@\w+)?$"))
        async def nsync_status(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            if not self.sync.running:
                return await event.reply(
                    f"🔄 <b>idle</b>\n📁 Group: <code>{self.sync.control_group_id}</code>\n"
                    f"🥷 Ninjas: <code>{len(self.ninja_clients)}</code>\n"
                    f"🎯 Target: <code>@{Config.SYNC_TARGET_BOT_USERNAME}</code>",
                    parse_mode="html")
            async with self.sync.stats_lock: st = dict(self.sync.stats)
            total = sum(len(r) for r in self.sync.ranges)
            elapsed = int(time.time() - (self.sync.started_at or time.time()))
            wl = []
            for i in range(min(10, len(self.sync.ranges))):
                d = self.sync.worker_progress.get(i, 0); t = len(self.sync.ranges[i])
                pct = (d / t * 100) if t else 0; bf = int(pct / 10)
                wl.append(f"  [{i+1}] {'█'*bf}{'░'*(10-bf)} <code>{d}/{t}</code>")
            await event.reply(
                f"🔄 <b>RUNNING</b>\n📊 <code>{st['checked']}/{total}</code>\n"
                f"🆕 <code>{st['imported']}</code> 🔄 <code>{st['updated']}</code> "
                f"➖ <code>{st['misses']}</code> ⚠️ <code>{st['errors']}</code>\n"
                f"⏱️ <code>{elapsed//60}m{elapsed%60}s</code>\n\n" + "\n".join(wl),
                parse_mode="html")

        @self.bot_client.on(events.NewMessage(pattern=r"^/nsynccancel(?:@\w+)?$"))
        async def nsync_cancel(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            await event.reply(await self.sync.cancel())

        @self.bot_client.on(events.NewMessage(pattern=r"^/nsyncdebug(?:@\w+)?$"))
        async def nsync_debug(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            total = len(self.ninja_clients); alive = 0; lines = []
            ninja_pairs = list(zip(self.ninja_clients, self.ninja_names))[:15]
            for i, (c, n) in enumerate(ninja_pairs, 1):
                uid = getattr(c, "tg_user_id", "?")
                try:
                    conn = c.is_connected(); alive += 1 if conn else 0
                    lines.append(f"  {i}. <code>{uid}</code> {escape_html(n)} — conn={conn}")
                except Exception as e:
                    lines.append(f"  {i}. <code>{uid}</code> — <code>{type(e).__name__}</code>")
            synced = await self.db.characters_col.count_documents(
                {"synced_via_check": True, "char_id": {"$regex": r"^BOD\d+$"}})
            total_bod = await self.db.characters_col.count_documents(
                {"char_id": {"$regex": r"^BOD\d+$"}})
            await event.reply(
                f"🔍 <b>Debug</b>\n👥 ninja_clients: <code>{total}</code>\n"
                f"🟢 connected: <code>{alive}</code>\n🔄 sync.running: <code>{self.sync.running}</code>\n"
                f"📁 group: <code>{self.sync.control_group_id}</code>\n"
                f"🎯 target: <code>@{Config.SYNC_TARGET_BOT_USERNAME}</code>\n"
                f"🕸️ auto-catch: <code>{self.auto_catch.stats_line()}</code>\n"
                f"🎯 selected IDs: <code>{len(self.auto_catch.selected_ids)}</code>\n\n"
                f"📊 DB: <code>{synced}</code> synced / <code>{total_bod}</code> total BOD\n\n"
                f"<b>First 15:</b>\n" + "\n".join(lines) +
                (f"\n  …+{total - 15}" if total > 15 else ""),
                parse_mode="html")

        @self.bot_client.on(events.NewMessage(pattern=r"^/nsyncwarmup(?:@\w+)?$"))
        async def nsync_warmup(event):
            if event.sender_id != Config.OWNER_ID: return await event.reply("⛔ Owner only.")
            if not self.ninja_clients: return await event.reply("❌ Pool empty.")
            status = await event.reply(
                f"🔥 Background warm-up of <b>{len(self.ninja_clients)}</b> ninjas started...",
                parse_mode="html")
            asyncio.create_task(self._warmup_diagnostic_bg(status))

    async def _warmup_diagnostic_bg(self, status_msg):
        username = Config.SYNC_TARGET_BOT_USERNAME
        if not username.startswith("@"): username = "@" + username
        targets = [username, Config.SYNC_TARGET_BOT_ID]
        ok = fail = 0; lines = []
        ninja_pairs = list(zip(self.ninja_clients, self.ninja_names))
        for i, (c, n) in enumerate(ninja_pairs, 1):
            uid = getattr(c, "tg_user_id", "?")
            success = False; err = ""
            for target in targets:
                try:
                    await asyncio.wait_for(c.send_message(target, "/start"), timeout=Config.SYNC_WARMUP_TIMEOUT)
                    await asyncio.sleep(0.3); success = True
                    self.ninja_warmed[uid] = True; break
                except asyncio.TimeoutError: err = f"Timeout"
                except FloodWaitError as e: err = f"FloodWait({e.seconds}s)"
                except Exception as e: err = f"{type(e).__name__}"
            if success: ok += 1; lines.append(f"  {i}. ✅ <code>{uid}</code> — {escape_html(n)}")
            else:
                fail += 1; self.ninja_warmed[uid] = False
                lines.append(f"  {i}. ❌ <code>{uid}</code> — {escape_html(n)}\n      ↳ <code>{escape_html(err)}</code>")
            if i % 5 == 0 or i == len(ninja_pairs):
                try:
                    await status_msg.edit(
                        f"🔥 <b>Warm-up {i}/{len(ninja_pairs)}</b>\n✅ <b>{ok}</b> · ❌ <b>{fail}</b>\n\n"
                        + "\n".join(lines[-8:]), parse_mode="html")
                except Exception: pass
        chunk = "\n".join(lines)
        if len(chunk) > 3500: chunk = chunk[:3500] + "\n…"
        try:
            await status_msg.edit(
                f"🔥 <b>Report — DONE</b>\n✅ OK: <b>{ok}</b> · ❌ Fail: <b>{fail}</b>\n"
                f"Target: <code>{escape_html(username)}</code>\n\n{chunk}",
                parse_mode="html")
        except Exception: pass

    # ══════════════════════════════════════════════════════════════
    #  START / STOP
    # ══════════════════════════════════════════════════════════════
    async def start(self):
        await self.bot_client.start(bot_token=Config.BOT_TOKEN)
        me = await self.bot_client.get_me()
        self.bot_id = me.id
        logger.info(f"🤖 Bot started: @{me.username} ({self.bot_id})")

        await self.load_ninja_pools()
        await self.load_taunt_targets()
        await self.sync.load_settings()
        await self.auto_catch.load_settings()

        if Config.SYNC_AUTO_WARMUP_ON_BOOT and self.ninja_clients:
            logger.info(f"🔥 Auto-warmup {len(self.ninja_clients)} ninjas in background...")
            asyncio.create_task(self._boot_warmup())

        asyncio.create_task(self.preload_admin_caches())
        threading.Thread(target=run_flask, daemon=True).start()
        await self.bot_client.run_until_disconnected()

    async def _boot_warmup(self):
        username = Config.SYNC_TARGET_BOT_USERNAME
        if not username.startswith("@"): username = "@" + username
        targets = [username, Config.SYNC_TARGET_BOT_ID]
        ok = 0
        ninja_pairs = list(zip(self.ninja_clients, self.ninja_names))
        for c, n in ninja_pairs:
            uid = getattr(c, "tg_user_id", "?")
            for target in targets:
                try:
                    await asyncio.wait_for(c.send_message(target, "/start"), timeout=Config.SYNC_WARMUP_TIMEOUT)
                    await asyncio.sleep(0.3)
                    self.ninja_warmed[uid] = True; ok += 1
                    break
                except asyncio.TimeoutError: pass
                except FloodWaitError as e:
                    logger.warning(f"⏳ boot [{n}] FloodWait {e.seconds}s")
                except Exception: pass
        logger.info(f"🔥 Boot warm-up: {ok}/{len(ninja_pairs)} OK")

    async def stop(self):
        if self.start_spam_active: await self.stop_start_spam()
        if self.sync.running:
            await self.sync.cancel()
            if self.sync.current_task:
                try: await asyncio.wait_for(self.sync.current_task, timeout=15)
                except (asyncio.TimeoutError, asyncio.CancelledError): pass
        if self.bot_client.is_connected(): await self.bot_client.disconnect()
        for c in self.ninja_clients:
            try: await c.disconnect()
            except Exception: pass
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
