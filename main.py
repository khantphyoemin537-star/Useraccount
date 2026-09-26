#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sovereign Ninja System  Auto-Catch + /spam + /startspam + Taunt + /go + /adm

 FINAL FIX for PeerIdInvalidError / Could not find input entity:
- _populate_dialogs() : get_dialogs() ကိုသုံးပြီး entity cache ဖြည့်
- _send_with_retry()   : dialogs ပြန်ဖြည့်ပြီး retry
- /rewarm              : manual cache fix
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
from telethon.errors import FloodWaitError, PeerIdInvalidError
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest


class Config:
    OWNER_ID = int(os.getenv("OWNER_ID", "6015356597"))
    MONGO_URI = os.getenv("MONGO_URI",
        "mongodb+srv://kkt:h1BdaMt7nxW9jTXa@cluster0.kb5fzfl.mongodb.net/?appName=Cluster0&tlsAllowInvalidCertificates=true")
    API_ID = int(os.getenv("API_ID", "35766004"))
    API_HASH = os.getenv("API_HASH", "d15b4226b81724722279bae6af69e22d")
    BOT_TOKEN = os.getenv("MAIN_BOT_TOKEN", "8824002850:AAELMmlNd_rxs-kJfX69usTrA86cr-z-Va4")

    SPAM_GROUPS = [-1004381473883, -1003836488351, -1003733625547, -1004358425408, -1003713845940, -1004368165756, -1003947715886]

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

    NINJA_IGNORED_EMOJIS = ["", "", "", "", "", ""]

    SPAWN_PHRASES = (
        "A CHARACTER HAS SPAWNED",
        "  s s",
        "  s s   ",
    )

    START_SPAM_INTERVAL = 1800
    START_SPAM_MIN_DELAY = 5
    START_SPAM_MAX_DELAY = 15
    START_SPAM_JITTER = 0.10

    SPAM_GROUP_INTERVAL = 0.5
    SPAM_NINJA_COOLDOWN = 0.6
    SPAM_JITTER = 0.30
    SPAM_GLOBAL_DELAY = 0.3
    SPAM_PAUSE_AFTER_SPAWN = 3

    SPAM_TEXTS = [
        " @FLASH_SPAM_Bot | @fuckyourwifey_bot ြြုမုဆ |ဈုးဆsjwjqgqq @Imjustkidding_bot | @GodMorgan_robot | @enforcermorgan_11robot | fqcawqAaaaafbBsqqlqoဘြဆြငငတေငတုsahqBwqiqoaj#!11&$1(!92929*@*@>>",
        " @GodMorgan_robot | @Imjustkidding_bot jrjwjwjql| qwertyuiopASDFGHJKLzxcvbnm1234567890!@#$%",
        " @enforcermorgan_11robot | fqcawqAaaaafbBsjajawjိြေုဆေုေြုsqqlqo ဘြဆြငငတေငတု 1234567890",
        " @FLASH_SPAM_Bot | @fuckyourwifey_bot | spamတတြဆုေူဆူတူတုဆ text alternative version here",
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


# 
#   INVISIBLE CHARACTER CLEANER
# 
def clean_invisible(text: str) -> str:
    if not text:
        return ""
    try:
        return ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    except Exception:
        return text


