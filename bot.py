"""
🎵 MusicBot + 🔐 SecretChat (Stealth Mode)
Railway.app deployment ready
"""

import asyncio
import logging
import os
import hashlib
import tempfile
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode, ChatAction
from aiogram.fsm.storage.memory import MemoryStorage

import yt_dlp

# ──────────────────────────── CONFIG ────────────────────────────
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID  = int(os.environ["ADMIN_ID"])
AUTO_DELETE_DELAY = 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ──────────────────────────── IN-MEMORY STORE ───────────────────
pairs: dict[str, dict] = {}
active_sessions: dict[int, str] = {}
stats = {"messages": 0, "music": 0}

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

def music_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🎵 Musiqa izlash")]],
        resize_keyboard=True,
        input_field_placeholder="Qo'shiq nomini yozing..."
    )

def secret_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚪 Chatdan chiqish")]],
        resize_keyboard=True,
        input_field_placeholder="Xabar yozing..."
    )

# ──────────────────────────── BOT SETUP ─────────────────────────
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp  = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ════════════════════════════════════════════════════════════════
#  /start
# ════════════════════════════════════════════════════════════════
@router.message(CommandStart())
async def cmd_start(message: Message):
    name = message.from_user.first_name
    await message.answer(
        f"🎵 Salom, <b>{name}</b>!\n\n"
        "Men musiqa botiman. Qo'shiq nomini yozing — MP3 yuboraman.\n\n"
        "<i>Masalan: Adele Hello | Shahzoda | G'ayrat Usmonov</i>",
        reply_markup=music_kb()
    )

# ════════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ════════════════════════════════════════════════════════════════
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    active  = sum(1 for r in pairs.values() if len(r["users"]) == 2)
    waiting = sum(1 for r in pairs.values() if len(r["users"]) == 1)
    await message.answer(
        "👑 <b>Admin Panel</b>\n\n"
        f"🟢 Faol chatlar: <b>{active}</b>\n"
        f"⏳ Kutayotganlar: <b>{waiting}</b>\n"
        f"👥 Ulangan users: <b>{len(active_sessions)}</b>\n"
        f"📨 Jami xabarlar: <b>{stats['messages']}</b>\n"
        f"🎵 Musiqa izlovlar: <b>{stats['music']}</b>\n\n"
        "<b>Buyruqlar:</b>\n"
        "/addpair &lt;parol&gt;\n"
        "/delpair &lt;parol&gt;\n"
        "/listpairs\n"
        "/kick &lt;user_id&gt;\n"
        "/broadcast &lt;xabar&gt;"
    )

@router.message(Command("addpair"))
async def cmd_addpair(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ /addpair &lt;parol&gt;")
        return
    password = parts[1].strip()
    pw_hash = hp(password)
    if pw_hash in pairs:
        await message.answer(f"⚠️ <code>{password}</code> allaqachon mavjud.")
        return
    pairs[pw_hash] = {
        "users": [],
        "hint": password[:2] + "***",
        "created": datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    await message.answer(
        f"✅ Parol yaratildi!\n\n"
        f"🔑 <code>{password}</code>\n\n"
        "Ikkala foydalanuvchiga yuboring.\n"
        "Ular botga bu parolni yozsalar — chat boshlanadi."
    )

@router.message(Command("delpair"))
async def cmd_delpair(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ /delpair &lt;parol&gt;")
        return
    pw_hash = hp(parts[1].strip())
    if pw_hash not in pairs:
        await message.answer("❌ Topilmadi.")
        return
    for uid in list(pairs[pw_hash]["users"]):
        active_sessions.pop(uid, None)
        try:
            await bot.send_message(uid, "⚠️ Chat xonasi yopildi.", reply_markup=music_kb())
        except Exception:
            pass
    del pairs[pw_hash]
    await message.answer("✅ Juft o'chirildi.")

@router.message(Command("listpairs"))
async def cmd_listpairs(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    if not pairs:
        await message.answer("📭 Faol juft yo'q.")
        return
    lines = ["👥 <b>Faol juftlar:</b>\n"]
    for i, (_, info) in enumerate(pairs.items(), 1):
        n = len(info["users"])
        status = "🟢 To'liq" if n == 2 else f"🟡 Kutmoqda ({n}/2)"
        lines.append(
            f"{i}. Hint: <code>{info['hint']}</code> | {status}\n"
            f"   Users: {', '.join(str(u) for u in info['users']) or '—'}\n"
            f"   Yaratilgan: {info['created']}"
        )
    await message.answer("\n\n".join(lines))

@router.message(Command("kick"))
async def cmd_kick(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("❌ /kick &lt;user_id&gt;")
        return
    uid = int(parts[1])
    pw_hash = active_sessions.pop(uid, None)
    if pw_hash and pw_hash in pairs:
        partner = next((u for u in pairs[pw_hash]["users"] if u != uid), None)
        try:
            pairs[pw_hash]["users"].remove(uid)
        except ValueError:
            pass
        try:
            await bot.send_message(uid, "⛔ Admin tomonidan chiqarildingiz.", reply_markup=music_kb())
        except Exception:
            pass
        if partner:
            active_sessions.pop(partner, None)
            try:
                pairs[pw_hash]["users"].remove(partner)
            except ValueError:
                pass
            try:
                await bot.send_message(partner, "🔴 Sherigingiz chiqarildi. Chat tugadi.", reply_markup=music_kb())
            except Exception:
                pass
        await message.answer(f"✅ {uid} chiqarildi.")
    else:
        await message.answer("❌ Foydalanuvchi chatda emas.")

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if message.from_user.id != ADMIN_ID:
        await handle_music(message, message.text or "")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ /broadcast &lt;xabar&gt;")
        return
    sent = 0
    for uid in list(active_sessions.keys()):
        try:
            await bot.send_message(uid, f"📢 <b>Admin:</b>\n\n{parts[1]}")
            sent += 1
        except Exception:
            pass
    await message.answer(f"✅ {sent} kishiga yuborildi.")

# ════════════════════════════════════════════════════════════════
#  LEAVE CHAT BUTTON
# ════════════════════════════════════════════════════════════════
@router.message(F.text == "🚪 Chatdan chiqish")
async def leave_chat(message: Message):
    uid = message.from_user.id
    if not in_chat(uid):
        await message.answer("Siz chatda emassiz.", reply_markup=music_kb())
        return

    pw_hash = active_sessions.pop(uid, None)
    partner_id = None

    if pw_hash and pw_hash in pairs:
        partner_id = next((u for u in pairs[pw_hash]["users"] if u != uid), None)
        try:
            pairs[pw_hash]["users"].remove(uid)
        except ValueError:
            pass

    await message.answer(
        "👋 Chatdan chiqdingiz.\n\nQo'shiq nomi yozing — musiqa topib beraman.",
        reply_markup=music_kb()
    )

    if partner_id:
        active_sessions.pop(partner_id, None)
        if pw_hash and pw_hash in pairs:
            try:
                pairs[pw_hash]["users"].remove(partner_id)
            except ValueError:
                pass
        try:
            await bot.send_message(
                partner_id,
                "🔴 Sherigingiz chatdan chiqdi. Chat tugadi.",
                reply_markup=music_kb()
            )
        except Exception:
            pass

    try:
        await bot.send_message(ADMIN_ID, f"🔴 <b>Chat yakunlandi</b>\n👤 Chiqdi: <code>{uid}</code>")
    except Exception:
        pass

# ════════════════════════════════════════════════════════════════
#  MAIN MESSAGE HANDLER — stealth core
# ════════════════════════════════════════════════════════════════
@router.message()
async def universal_handler(message: Message):
    uid  = message.from_user.id
    text = (message.text or "").strip()

    # ── Already in secret chat → relay ──────────────────────────
    if in_chat(uid):
        await relay_message(message)
        return

    # ── Check password (any non-command text) ───────────────────
    if text and not text.startswith("/"):
        pw_hash = hp(text)
        if pw_hash in pairs:
            await join_secret_chat(message, pw_hash)
            return

    # ── Music bot ───────────────────────────────────────────────
    if text == "🎵 Musiqa izlash":
        await message.answer(
            "🎵 Qo'shiq nomini yozing:\n\n"
            "<i>Masalan: Adele Hello | Billie Eilish</i>"
        )
        return

    if text and not text.startswith("/"):
        await handle_music(message, text)

# ════════════════════════════════════════════════════════════════
#  SECRET CHAT — JOIN
# ════════════════════════════════════════════════════════════════
async def join_secret_chat(message: Message, pw_hash: str):
    uid  = message.from_user.id
    room = pairs[pw_hash]

    if len(room["users"]) >= 2:
        # Room full — silently treat as music search
        await handle_music(message, message.text)
        return

    room["users"].append(uid)
    active_sessions[uid] = pw_hash

    if len(room["users"]) == 1:
        await message.answer(
            "🔐 <b>Yashirin chat xonasiga kirdingiz.</b>\n\n"
            "⏳ Ikkinchi kishi ulanishini kuting...\n"
            "<i>U ham shu parolni yozganda chat boshlanadi.</i>",
            reply_markup=secret_kb()
        )
        try:
            await bot.send_message(
                ADMIN_ID,
                f"📡 <b>Xonaga kirdi (1/2)</b>\n"
                f"👤 <code>{uid}</code> (@{message.from_user.username or '—'})\n"
                f"🔑 Hint: {room['hint']}"
            )
        except Exception:
            pass
    else:
        partner_id = room["users"][0]
        await message.answer(
            "🔐 <b>Chat boshlandi!</b>\n\n"
            "💬 Xabar yozing — sherigingizga yetkaziladi\n"
            "💣 Xabarlar 1 daqiqada o'chadi",
            reply_markup=secret_kb()
        )
        try:
            await bot.send_message(
                partner_id,
                "🟢 <b>Sherigingiz ulandi! Chat boshlandi.</b>\n\n"
                "💬 Xabar yozing\n"
                "💣 Xabarlar 1 daqiqada o'chadi"
            )
        except Exception:
            pass
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🟢 <b>Chat boshlandi!</b>\n"
                f"🔑 Hint: {room['hint']}\n"
                f"👤 User1: <code>{partner_id}</code>\n"
                f"👤 User2: <code>{uid}</code>"
            )
        except Exception:
            pass

# ════════════════════════════════════════════════════════════════
#  SECRET CHAT — RELAY
# ════════════════════════════════════════════════════════════════
async def relay_message(message: Message):
    uid        = message.from_user.id
    partner_id = partner_of(uid)

    if not partner_id:
        await message.answer("⏳ Sherigingiz hali ulanmagan, kuting...")
        return

    stats["messages"] += 1
    sent = None

    try:
        if message.text:
            sent = await bot.send_message(
                partner_id,
                f"{message.text}\n\n<i>💣 1 daqiqada o'chadi</i>"
            )
        elif message.photo:
            sent = await bot.send_photo(
                partner_id, message.photo[-1].file_id,
                caption=(message.caption or "") + "\n\n<i>💣 1 daqiqada o'chadi</i>"
            )
        elif message.voice:
            sent = await bot.send_voice(
                partner_id, message.voice.file_id,
                caption="<i>💣 1 daqiqada o'chadi</i>"
            )
        elif message.video:
            sent = await bot.send_video(
                partner_id, message.video.file_id,
                caption=(message.caption or "") + "\n\n<i>💣 1 daqiqada o'chadi</i>"
            )
        elif message.sticker:
            sent = await bot.send_sticker(partner_id, message.sticker.file_id)
        elif message.document:
            sent = await bot.send_document(
                partner_id, message.document.file_id,
                caption=(message.caption or "") + "\n\n<i>💣 1 daqiqada o'chadi</i>"
            )
        elif message.audio:
            sent = await bot.send_audio(
                partner_id, message.audio.file_id,
                caption=(message.caption or "") + "\n\n<i>💣 1 daqiqada o'chadi</i>"
            )
        elif message.video_note:
            sent = await bot.send_video_note(partner_id, message.video_note.file_id)
        else:
            await message.answer("⚠️ Bu turdagi xabar qo'llab-quvvatlanmaydi.")
            return

        confirm = await message.answer("✅  •  <i>💣 1 daqiqada o'chadi</i>")
        if sent:
            asyncio.create_task(auto_delete(
                partner_id, sent.message_id,
                message.chat.id, message.message_id,
                message.chat.id, confirm.message_id,
            ))

    except Exception as e:
        log.error(f"Relay error: {e}")
        await message.answer("❌ Xabar yetkazishda xato.")


async def auto_delete(*args):
    await asyncio.sleep(AUTO_DELETE_DELAY)
    for i in range(0, len(args), 2):
        try:
            await bot.delete_message(args[i], args[i + 1])
        except Exception:
            pass

# ════════════════════════════════════════════════════════════════
#  MUSIC SEARCH
# ════════════════════════════════════════════════════════════════
async def handle_music(message: Message, query: str):
    q = query.strip()
    if not q or len(q) < 2:
        return
    stats["music"] += 1

    searching = await message.answer(f"🔍 <b>{q}</b> izlanmoqda...")
    await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_AUDIO)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "outtmpl": f"{tmpdir}/%(title)s.%(ext)s",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "max_filesize": 49 * 1024 * 1024,
            }

            loop = asyncio.get_event_loop()

            def _dl():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch1:{q}", download=True)
                    if "entries" in info:
                        info = info["entries"][0]
                    return info

            info = await loop.run_in_executor(None, _dl)

            mp3 = next(
                (os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith(".mp3")),
                None
            )
            if not mp3:
                await searching.edit_text("❌ Topilmadi. Boshqa nom bilan urinib ko'ring.")
                return

            title   = info.get("title", q)
            artist  = info.get("uploader", "")
            dur     = info.get("duration", 0)
            dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else "—"

            await searching.edit_text(f"📤 <b>{title}</b> yuklanmoqda...")
            await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_AUDIO)

            with open(mp3, "rb") as f:
                await bot.send_audio(
                    message.chat.id,
                    audio=f,
                    title=title,
                    performer=artist,
                    caption=f"🎵 <b>{title}</b>\n👤 {artist}\n⏱ {dur_str}",
                )
            await searching.delete()

    except yt_dlp.utils.DownloadError:
        await searching.edit_text(
            "❌ Yuklab bo'lmadi.\n\n"
            "💡 Ijrochi + qo'shiq nomi yozing:\n"
            "<i>Adele Hello</i>"
        )
    except Exception as e:
        log.error(f"Music error: {e}")
        await searching.edit_text("❌ Xato. Qayta urinib ko'ring.")

# ════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════
async def main():
    log.info("🚀 Bot ishga tushdi")
    await dp.start_polling(bot, allowed_updates=["message"])

if __name__ == "__main__":
    asyncio.run(main())
