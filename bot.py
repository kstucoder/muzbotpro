"""
🎵 VibeMusic Bot — Deezer + iTunes preview delivery
🔐 SecretChat — Encrypted relay messaging
Railway.app ready — No API keys needed
"""

import asyncio
import logging
import os
import hashlib
import aiohttp
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    CallbackQuery,
    URLInputFile,
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode, ChatAction
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# ──────────────────────────── CONFIG ────────────────────────────
BOT_TOKEN         = os.environ["BOT_TOKEN"]
ADMIN_ID          = int(os.environ["ADMIN_ID"])
SECRET_CODE       = os.environ.get("SECRET_CODE", "music2025")  # static pair
AUTO_DELETE_DELAY  = 60
INACTIVITY_TIMEOUT = 20 * 60   # 20 minutes in seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(__name__)

# ──────────────────────────── IN-MEMORY STORE ───────────────────
pairs: dict[str, dict]          = {}  # will be filled after SECRET_CODE is defined
pair_members: dict[str, set]     = {}  # pw_hash -> set of user_ids who ever used it
active_sessions: dict[int, str] = {}
recent_searches: list[str]      = []   # last 5 global queries
# uid -> list of (chat_id, msg_id) to delete on exit
chat_messages: dict[int, list]  = {}
# uid -> timestamp of last activity
last_activity: dict[int, float] = {}
stats = {"messages": 0, "music": 0, "users": set()}

# ──────────────────────────── HELPERS ───────────────────────────
def hp(pw: str) -> str:
    return hashlib.sha256(pw.strip().encode()).hexdigest()

def partner_of(uid: int) -> int | None:
    pw_hash = active_sessions.get(uid)
    if not pw_hash or pw_hash not in pairs:
        return None
    for u in pairs[pw_hash]["users"]:
        if u != uid:
            return u
    return None

def in_chat(uid: int) -> bool:
    return uid in active_sessions

def remember_msg(uid: int, chat_id: int, msg_id: int):
    """Store a message ID so it can be bulk-deleted on chat exit."""
    chat_messages.setdefault(uid, []).append((chat_id, msg_id))

def touch(uid: int):
    """Update last activity timestamp."""
    import time
    last_activity[uid] = time.time()

async def delete_chat_messages(uid: int):
    """Delete all stored chat messages for a user."""
    for chat_id, msg_id in chat_messages.pop(uid, []):
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

def track_search(query: str):
    """Keep last 5 unique searches for trending display."""
    q = query.strip().lower()
    if q in recent_searches:
        recent_searches.remove(q)
    recent_searches.insert(0, q)
    if len(recent_searches) > 5:
        recent_searches.pop()

# ──────────────────────────── KEYBOARDS ─────────────────────────
def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Search Music"), KeyboardButton(text="🔥 Trending")],
            [KeyboardButton(text="ℹ️ How it works"),  KeyboardButton(text="📊 Stats")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Type a song or artist name..."
    )

def secret_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚪 Leave playlist")]],
        resize_keyboard=True,
        input_field_placeholder="Type your message..."
    )

def genre_kb() -> InlineKeyboardMarkup:
    genres = [
        ("🎸 Rock",      "genre_rock"),
        ("🎤 Pop",       "genre_pop"),
        ("🎷 Jazz",      "genre_jazz"),
        ("🎻 Classical", "genre_classical"),
        ("🔥 Hip-Hop",   "genre_hiphop"),
        ("💃 Dance",     "genre_dance"),
    ]
    buttons = [
        [InlineKeyboardButton(text=g[0], callback_data=g[1]) for g in genres[i:i+2]]
        for i in range(0, len(genres), 2)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def track_action_kb(link: str, source: str) -> InlineKeyboardMarkup:
    buttons = []
    if link:
        icon = "🟢 Full track on Deezer" if source == "deezer" else "🍎 Full track on iTunes"
        buttons.append([InlineKeyboardButton(text=icon, url=link)])
    buttons.append([
        InlineKeyboardButton(text="🔍 Search again", callback_data="search_again"),
        InlineKeyboardButton(text="🔥 Trending",     callback_data="show_trending"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ──────────────────────────── STATIC PAIR INIT ──────────────────
def _init_static_pair():
    """Pre-create the static pair from SECRET_CODE so /addpair is not needed."""
    pw_hash = hp(SECRET_CODE)
    pairs[pw_hash] = {
        "users":   [],
        "hint":    SECRET_CODE[:2] + "***",
        "created": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "static":  True,   # never fully deleted — reset when both leave
    }

_init_static_pair()

# ──────────────────────────── BOT SETUP ─────────────────────────
bot    = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp     = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ════════════════════════════════════════════════════════════════
#  /start
# ════════════════════════════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message):
    uid  = message.from_user.id
    stats["users"].add(uid)
    name = message.from_user.first_name or "there"
    await message.answer(
        f"🎵 <b>Hey {name}, welcome to VibeMusic!</b>\n\n"
        "I find and send you <b>30-second previews</b> of any song — "
        "completely free, no sign-up needed.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Just <b>type any song or artist name</b> below.\n\n"
        "<i>Examples:</i>\n"
        "  • <code>Blinding Lights</code>\n"
        "  • <code>Drake God's Plan</code>\n"
        "  • <code>Coldplay Yellow</code>\n"
        "━━━━━━━━━━━━━━━━━━",
        reply_markup=main_kb()
    )

# ════════════════════════════════════════════════════════════════
#  CALLBACK HANDLERS
# ════════════════════════════════════════════════════════════════
@router.callback_query(F.data.startswith("genre_"))
async def cb_genre(call: CallbackQuery):
    genre_map = {
        "genre_rock":      "best rock songs",
        "genre_pop":       "best pop songs 2024",
        "genre_jazz":      "classic jazz",
        "genre_classical": "classical music",
        "genre_hiphop":    "best hip hop songs",
        "genre_dance":     "best dance music",
    }
    query = genre_map.get(call.data, "popular music")
    await call.answer(f"Searching {query}...")
    await handle_music(call.message, query)

@router.callback_query(F.data == "search_again")
async def cb_search_again(call: CallbackQuery):
    await call.answer()
    await call.message.answer(
        "🔍 <b>What song are you looking for?</b>\n\n"
        "<i>Type any song title or artist name:</i>"
    )

@router.callback_query(F.data == "show_trending")
async def cb_trending(call: CallbackQuery):
    await call.answer()
    await show_trending(call.message)

# ════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ════════════════════════════════════════════════════════════════
@router.message(Command("adminpanel"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    active  = sum(1 for r in pairs.values() if len(r["users"]) == 2)
    waiting = sum(1 for r in pairs.values() if len(r["users"]) == 1)
    await message.answer(
        "👑 <b>Admin Panel</b>\n\n"
        f"🟢 Active chats: <b>{active}</b>\n"
        f"⏳ Waiting: <b>{waiting}</b>\n"
        f"👥 Connected users: <b>{len(active_sessions)}</b>\n"
        f"🎵 Music searches: <b>{stats['music']}</b>\n"
        f"📨 Messages relayed: <b>{stats['messages']}</b>\n"
        f"🌍 Total users: <b>{len(stats['users'])}</b>\n\n"
        "<b>Commands:</b>\n"
        "/addpair &lt;code&gt; — Create secret pair\n"
        "/delpair &lt;code&gt; — Delete pair\n"
        "/listpairs — List active pairs\n"
        "/kick &lt;user_id&gt; — Remove user\n"
        "/broadcast &lt;message&gt; — Message all users"
    )

@router.message(Command("addpair"))
async def cmd_addpair(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Usage: /addpair &lt;code&gt;")
        return
    password = parts[1].strip()
    pw_hash  = hp(password)
    if pw_hash in pairs:
        await message.answer(f"⚠️ Code <code>{password}</code> already exists.")
        return
    pairs[pw_hash] = {
        "users":   [],
        "hint":    password[:2] + "***",
        "created": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    await message.answer(
        f"✅ <b>Secret pair created!</b>\n\n"
        f"🔑 Code: <code>{password}</code>\n\n"
        "Send this code to both users.\n"
        "When they both type it — chat begins automatically."
    )

@router.message(Command("delpair"))
async def cmd_delpair(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Usage: /delpair &lt;code&gt;")
        return
    pw_hash = hp(parts[1].strip())
    if pw_hash not in pairs:
        await message.answer("❌ Pair not found.")
        return
    for uid in list(pairs[pw_hash]["users"]):
        active_sessions.pop(uid, None)
        try:
            await bot.send_message(uid, "⚠️ Your chat room was closed by admin.", reply_markup=main_kb())
        except Exception:
            pass
    del pairs[pw_hash]
    await message.answer("✅ Pair deleted.")

@router.message(Command("listpairs"))
async def cmd_listpairs(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    if not pairs:
        await message.answer("📭 No active pairs.")
        return
    lines = ["👥 <b>Active Pairs:</b>\n"]
    for i, (_, info) in enumerate(pairs.items(), 1):
        n      = len(info["users"])
        status = "🟢 Full" if n == 2 else f"🟡 Waiting ({n}/2)"
        lines.append(
            f"{i}. Hint: <code>{info['hint']}</code> | {status}\n"
            f"   Users: {', '.join(str(u) for u in info['users']) or '—'}\n"
            f"   Created: {info['created']}"
        )
    await message.answer("\n\n".join(lines))

@router.message(Command("kick"))
async def cmd_kick(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("❌ Usage: /kick &lt;user_id&gt;")
        return
    uid     = int(parts[1])
    pw_hash = active_sessions.pop(uid, None)
    if pw_hash and pw_hash in pairs:
        partner = next((u for u in pairs[pw_hash]["users"] if u != uid), None)
        try:
            pairs[pw_hash]["users"].remove(uid)
        except ValueError:
            pass
        try:
            await bot.send_message(uid, "⛔ You were removed by admin.", reply_markup=main_kb())
        except Exception:
            pass
        if partner:
            active_sessions.pop(partner, None)
            try:
                pairs[pw_hash]["users"].remove(partner)
            except ValueError:
                pass
            try:
                await bot.send_message(partner, "🔴 Your partner was removed. Chat ended.", reply_markup=main_kb())
            except Exception:
                pass
        await message.answer(f"✅ User {uid} kicked.")
    else:
        await message.answer("❌ User is not in any chat.")

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ Usage: /broadcast &lt;message&gt;")
        return
    sent = 0
    for uid in list(active_sessions.keys()):
        try:
            await bot.send_message(uid, f"📢 <b>Admin announcement:</b>\n\n{parts[1]}")
            sent += 1
        except Exception:
            pass
    await message.answer(f"✅ Sent to {sent} users.")

# ════════════════════════════════════════════════════════════════
#  BUTTON HANDLERS
# ════════════════════════════════════════════════════════════════
@router.message(F.text == "🚪 Leave playlist")
async def leave_chat(message: Message):
    uid = message.from_user.id
    if not in_chat(uid):
        await message.answer("You are not in a chat.", reply_markup=main_kb())
        return
    try:
        await message.delete()
    except Exception:
        pass
    await close_chat(uid, reason="left")

@router.message(F.text == "🔍 Search Music")
async def btn_search(message: Message):
    await message.answer(
        "🔍 <b>Search for any song or artist:</b>\n\n"
        "<i>Just type the name below ↓</i>"
    )

@router.message(F.text == "🔥 Trending")
async def btn_trending(message: Message):
    await show_trending(message)

@router.message(F.text == "ℹ️ How it works")
async def btn_howto(message: Message):
    await message.answer(
        "🎵 <b>VibeMusic — How it works</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "1️⃣  Type any song or artist name\n"
        "2️⃣  I search Deezer & iTunes instantly\n"
        "3️⃣  You get a 30-second preview + cover art\n"
        "4️⃣  Tap the link to listen to the full track\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎸 <b>Or browse by genre:</b>",
        reply_markup=genre_kb()
    )

@router.message(F.text == "📊 Stats")
async def btn_stats(message: Message):
    trending     = recent_searches[:3]
    trending_str = "\n".join(f"  {i+1}. {q.title()}" for i, q in enumerate(trending)) or "  No searches yet"
    await message.answer(
        "📊 <b>Bot Statistics</b>\n\n"
        f"🎵 Songs found: <b>{stats['music']}</b>\n"
        f"🌍 Unique users: <b>{len(stats['users'])}</b>\n\n"
        "🔥 <b>Recent Searches:</b>\n"
        f"{trending_str}"
    )

async def show_trending(message: Message):
    if not recent_searches:
        popular = ["Blinding Lights", "Shape of You", "Bohemian Rhapsody", "God's Plan", "Levitating"]
        lines   = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(popular))
        await message.answer(
            "🔥 <b>Popular searches to try:</b>\n\n"
            f"{lines}\n\n"
            "<i>Type any name below to search!</i>"
        )
    else:
        lines = "\n".join(f"  {i+1}. {q.title()}" for i, q in enumerate(recent_searches))
        await message.answer(
            "🔥 <b>Recent searches:</b>\n\n"
            f"{lines}\n\n"
            "<i>Type any name below to search!</i>"
        )

# ════════════════════════════════════════════════════════════════
#  MAIN MESSAGE HANDLER — stealth core
# ════════════════════════════════════════════════════════════════
# Ignored button labels (should not trigger music search)
BUTTON_LABELS = {
    "🔍 Search Music", "🔥 Trending",
    "ℹ️ How it works", "📊 Stats", "🚪 Leave playlist"
}

@router.message()
async def universal_handler(message: Message):
    uid  = message.from_user.id
    text = (message.text or "").strip()
    stats["users"].add(uid)

    # — Secret chat relay —
    if in_chat(uid):
        await relay_message(message)
        return

    # Ignore keyboard buttons (handled above)
    if text in BUTTON_LABELS:
        return

    # — Secret chat password check —
    if text and not text.startswith("/"):
        pw_hash = hp(text)
        if pw_hash in pairs:
            await join_secret_chat(message, pw_hash)
            return

    # — Music search —
    if text and not text.startswith("/"):
        await handle_music(message, text)

# ════════════════════════════════════════════════════════════════
#  SECRET CHAT — JOIN
# ════════════════════════════════════════════════════════════════
async def close_chat(uid: int, reason: str = "left"):
    """
    Cleanly close the secret chat for uid (and their partner).
    reason: 'left' | 'timeout' | 'kicked'
    Deletes all stored chat messages for both sides.
    """
    import time
    pw_hash    = active_sessions.pop(uid, None)
    partner_id = None
    if pw_hash and pw_hash in pairs:
        partner_id = next((u for u in pairs[pw_hash]["users"] if u != uid), None)
        try: pairs[pw_hash]["users"].remove(uid)
        except ValueError: pass

    # Clean up partner
    if partner_id:
        active_sessions.pop(partner_id, None)
        last_activity.pop(partner_id, None)
        if pw_hash and pw_hash in pairs:
            try: pairs[pw_hash]["users"].remove(partner_id)
            except ValueError: pass
        # If static pair is now empty, reset it so it can be reused
        if pw_hash in pairs and pairs[pw_hash].get("static") and not pairs[pw_hash]["users"]:
            pairs[pw_hash]["users"] = []
        await delete_chat_messages(partner_id)
        try:
            await bot.send_message(partner_id, "🎵", reply_markup=main_kb())
        except Exception:
            pass

    # Clean up self
    last_activity.pop(uid, None)
    await delete_chat_messages(uid)
    try:
        await bot.send_message(uid, "🎵", reply_markup=main_kb())
    except Exception:
        pass




async def join_secret_chat(message: Message, pw_hash: str):
    uid  = message.from_user.id
    room = pairs[pw_hash]

    if uid in room["users"]:
        await message.answer(
            "🎵 Still searching for your track...\n"
            "Please wait a moment 🎧"
        )
        return

    if len(room["users"]) >= 2:
        # Room is full — treat as music search instead
        await handle_music(message, message.text)
        return

    room["users"].append(uid)
    active_sessions[uid] = pw_hash

    # Save this user to permanent members list
    pair_members.setdefault(pw_hash, set()).add(uid)

    # Notify past members (exclude current user and anyone already in room)
    past = pair_members.get(pw_hash, set()) - {uid} - set(room["users"])
    for past_uid in past:
        try:
            await bot.send_message(
                past_uid,
                "🎵 <b>New tracks just dropped!</b>\n\n"
                "🔥 Fresh music has been added to your playlist.\n"
                "🎧 Open it now to start listening!"
            )
        except Exception:
            pass

    if len(room["users"]) == 1:
        try:
            await message.delete()
        except Exception:
            pass
        touch(uid)
        join_msg = await message.answer(
            "🎵 <b>Searching for your track...</b>\n\n"
            "🔍 Hang tight, loading your music session...\n\n"
            "<i>Will start automatically in a moment.</i>",
            reply_markup=secret_kb()
        )
        remember_msg(uid, message.chat.id, join_msg.message_id)

    else:
        partner_id = room["users"][0]
        try:
            await message.delete()
        except Exception:
            pass
        touch(uid)
        touch(partner_id)
        join_msg = await message.answer(
            "🎶 <b>Track found! Now playing...</b>\n\n"
            "💬 Type your message below\n"
            "💣 Messages auto-delete after 1 minute\n"
            "🚪 Tap <b>Leave playlist</b> to exit anytime",
            reply_markup=secret_kb()
        )
        remember_msg(uid, message.chat.id, join_msg.message_id)
        try:
            # Delete partner's waiting message first
            await delete_chat_messages(partner_id)
            started_msg = await bot.send_message(
                partner_id,
                "🎶 <b>Track loaded! Ready to play.</b>\n\n"
                "💬 You can now type your message\n"
                "💣 Messages auto-delete in 60 seconds",
                reply_markup=secret_kb()
            )
            remember_msg(partner_id, partner_id, started_msg.message_id)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════
#  SECRET CHAT — RELAY
# ════════════════════════════════════════════════════════════════
async def relay_message(message: Message):
    uid        = message.from_user.id
    partner_id = partner_of(uid)

    if not partner_id:
        wait_msg = await message.answer(
            "🎵 <b>Still loading your track...</b>\n\n"
            "🎧 Please wait just a moment..."
        )
        remember_msg(uid, message.chat.id, wait_msg.message_id)
        remember_msg(uid, message.chat.id, message.message_id)
        return

    stats["messages"] += 1
    touch(uid)
    touch(partner_id)
    sent = None
    BURN = "\n\n<i>💣 Auto-deletes in 60s</i>"

    try:
        if message.text:
            sent = await bot.send_message(partner_id, f"{message.text}{BURN}")
        elif message.photo:
            sent = await bot.send_photo(
                partner_id, message.photo[-1].file_id,
                caption=(message.caption or "") + BURN
            )
        elif message.voice:
            sent = await bot.send_voice(
                partner_id, message.voice.file_id,
                caption=f"🎙 Voice message{BURN}"
            )
        elif message.video:
            sent = await bot.send_video(
                partner_id, message.video.file_id,
                caption=(message.caption or "") + BURN
            )
        elif message.sticker:
            sent = await bot.send_sticker(partner_id, message.sticker.file_id)
        elif message.document:
            sent = await bot.send_document(
                partner_id, message.document.file_id,
                caption=(message.caption or "") + BURN
            )
        elif message.audio:
            sent = await bot.send_audio(
                partner_id, message.audio.file_id,
                caption=(message.caption or "") + BURN
            )
        elif message.video_note:
            sent = await bot.send_video_note(partner_id, message.video_note.file_id)
        elif message.animation:
            sent = await bot.send_animation(
                partner_id, message.animation.file_id,
                caption=(message.caption or "") + BURN
            )
        else:
            await message.answer("⚠️ This message type is not supported.")
            return

        if sent:
            # Track for bulk-delete on Leave playlist
            remember_msg(uid,        message.chat.id, message.message_id)
            remember_msg(partner_id, partner_id,      sent.message_id)
            asyncio.create_task(auto_delete(
                partner_id,       sent.message_id,
                message.chat.id,  message.message_id,
            ))

    except Exception as e:
        log.error(f"Relay error: {e}")
        await message.answer("❌ Failed to deliver message. Please try again.")

async def auto_delete(*args):
    """Delete message pairs after AUTO_DELETE_DELAY seconds."""
    await asyncio.sleep(AUTO_DELETE_DELAY)
    for i in range(0, len(args), 2):
        try:
            await bot.delete_message(args[i], args[i + 1])
        except Exception:
            pass

# ════════════════════════════════════════════════════════════════
#  MUSIC — Deezer + iTunes fallback
# ════════════════════════════════════════════════════════════════
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

async def search_deezer(session: aiohttp.ClientSession, query: str) -> dict | None:
    """Deezer public API — 30s preview, cover art, track link."""
    try:
        async with session.get(
            "https://api.deezer.com/search",
            params={"q": query, "limit": 5},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                return None
            data = await r.json(content_type=None)

        for track in data.get("data", []):
            preview = track.get("preview", "")
            if not preview:
                continue
            dur = track.get("duration", 30)
            return {
                "source":      "deezer",
                "title":       track.get("title", query),
                "artist":      track.get("artist", {}).get("name", ""),
                "album":       track.get("album", {}).get("title", ""),
                "preview_url": preview,
                "cover_url":   track.get("album", {}).get("cover_big", ""),
                "duration":    dur,
                "link":        track.get("link", ""),
            }
    except Exception as e:
        log.warning(f"Deezer error: {e}")
    return None


async def search_itunes(session: aiohttp.ClientSession, query: str) -> dict | None:
    """Apple iTunes Search API — 30s preview, cover art."""
    try:
        async with session.get(
            "https://itunes.apple.com/search",
            params={"term": query, "media": "music", "entity": "song", "limit": 5},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                return None
            data = await r.json(content_type=None)

        for track in data.get("results", []):
            preview = track.get("previewUrl", "")
            if not preview:
                continue
            ms    = track.get("trackTimeMillis", 30000)
            cover = track.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
            return {
                "source":      "itunes",
                "title":       track.get("trackName", query),
                "artist":      track.get("artistName", ""),
                "album":       track.get("collectionName", ""),
                "preview_url": preview,
                "cover_url":   cover,
                "duration":    ms // 1000,
                "link":        track.get("trackViewUrl", ""),
            }
    except Exception as e:
        log.warning(f"iTunes error: {e}")
    return None


async def find_track(query: str) -> dict | None:
    """Try Deezer first, iTunes as fallback."""
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        track = await search_deezer(session, query)
        if track:
            return track
        log.info(f"Deezer miss → trying iTunes: {query}")
        return await search_itunes(session, query)


async def handle_music(message: Message, query: str):
    q = query.strip()
    if not q or len(q) < 2:
        return

    # Ignore keyboard button labels
    if q in BUTTON_LABELS:
        return

    stats["music"] += 1
    track_search(q)

    searching = await message.answer(
        f"🎵 Searching for <b>{q}</b>...\n"
        "<i>Checking Deezer & iTunes</i>"
    )
    await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)

    track = await find_track(q)

    if not track:
        await searching.edit_text(
            f"😔 <b>Nothing found for «{q}»</b>\n\n"
            "💡 <b>Tips:</b>\n"
            "  • Try <code>Artist + Song title</code>\n"
            "  • Check the spelling\n"
            "  • Use the English title if available\n\n"
            "🎸 Or browse by genre:",
            reply_markup=genre_kb()
        )
        return

    dur     = track["duration"]
    dur_str = f"{dur // 60}:{dur % 60:02d}"
    source  = "Deezer" if track["source"] == "deezer" else "iTunes"
    icon    = "🟢" if track["source"] == "deezer" else "🍎"

    await searching.edit_text(f"📤 Found it! Uploading <b>{track['title']}</b>...")
    await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)

    caption = (
        f"🎵 <b>{track['title']}</b>\n"
        f"👤 <b>{track['artist']}</b>\n"
        f"💿 {track['album']}\n"
        f"⏱ {dur_str}  ·  30s preview\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{icon} Source: <b>{source}</b>"
    )

    thumb = URLInputFile(track["cover_url"]) if track.get("cover_url") else None
    kb    = track_action_kb(track["link"], track["source"])

    try:
        await bot.send_audio(
            message.chat.id,
            audio        = URLInputFile(track["preview_url"], filename=f"{track['title']}.mp3"),
            title        = track["title"],
            performer    = track["artist"],
            duration     = dur,
            thumbnail    = thumb,
            caption      = caption,
            reply_markup = kb,
        )
        await searching.delete()

    except Exception as e:
        log.error(f"send_audio error: {e}")
        # Retry without thumbnail
        try:
            await bot.send_audio(
                message.chat.id,
                audio        = URLInputFile(track["preview_url"], filename=f"{track['title']}.mp3"),
                title        = track["title"],
                performer    = track["artist"],
                duration     = dur,
                caption      = caption,
                reply_markup = kb,
            )
            await searching.delete()
        except Exception as e2:
            log.error(f"Fallback audio error: {e2}")
            await searching.edit_text(
                "❌ <b>Failed to send audio.</b>\n\n"
                "The track may be geo-restricted. Try a different song.",
                reply_markup=genre_kb()
            )

# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════
async def inactivity_watcher():
    """Check every 60s; close chats idle for INACTIVITY_TIMEOUT seconds."""
    import time
    while True:
        await asyncio.sleep(60)
        now  = time.time()
        dead = [
            uid for uid, ts in list(last_activity.items())
            if now - ts > INACTIVITY_TIMEOUT and uid in active_sessions
        ]
        for uid in dead:
            log.info(f"Inactivity timeout for uid={uid}")
            await close_chat(uid, reason="timeout")


async def main():
    log.info("🚀 VibeMusic Bot started (Deezer + iTunes / SecretChat)")
    asyncio.create_task(inactivity_watcher())
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
