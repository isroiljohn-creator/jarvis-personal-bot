"""Jarvis Personal AI Bot — asosiy fayl."""

import asyncio
import logging
import os
import sys
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatAction

from ai import GeminiAI
from userbot import UserBot
from computer import ComputerAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("jarvis")

# ───────────────────────── SOZLAMALAR ──────────────────────────

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ.get("OWNER_TELEGRAM_ID", "0"))
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TG_API_ID = os.environ.get("TG_API_ID", "")
TG_API_HASH = os.environ.get("TG_API_HASH", "")
TG_PHONE = os.environ.get("TG_PHONE", "")

ai = GeminiAI(GEMINI_API_KEY)
userbot: UserBot | None = None
computer = ComputerAgent()

SYSTEM_PROMPT = """Sen — Jarvis. Foydalanuvchining shaxsiy AI yordamchisi.
Sen Telegram akkountini va kompyuterini boshqarish imkoniyatlariga egasan.

Asosiy qoidalar:
1. Har doim o'zbek tilida javob ber (kimdir boshqa tilda gaplashsa, o'sha tilda javob ber)
2. Qisqa va aniq javob ber, keraksiz so'z ishlatma
3. Telegram buyruqlari uchun: TG: prefiksini ishlataman
4. Kompyuter buyruqlari uchun: CMD: prefiksini ishlataman
5. Ovozli xabarlarni matnга aylantirib qayta ishla

Buyruqlar:
- TG:LIST_CHATS — barcha chatlarni ko'rsat
- TG:READ:<chat_id> — chat xabarlarini o'qi
- TG:SEND:<chat_id>:<xabar> — xabar yubor
- TG:DIALOGS — so'nggi suhbatlar
- CMD:<buyruq> — terminal buyrug'i bajar
"""


def is_owner(update: Update) -> bool:
    if OWNER_ID == 0:
        return True
    return update.effective_user.id == OWNER_ID


# ────────────────────────── HANDLERS ───────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        await update.message.reply_text("❌ Kirish taqiqlangan.")
        return

    userbot_status = "✅ Ulangan" if (userbot and userbot.connected) else "❌ Ulanmagan"
    auto_status = "✅ Yoqiq" if (userbot and userbot.auto_reply) else "⏸ O'chiq"
    text = (
        f"👾 *Jarvis — Shaxsiy AI Yordamchi*\n\n"
        f"🤖 AI: Gemini 2.0 Flash ✅\n"
        f"📱 Telegram: {userbot_status}\n"
        f"🔁 Auto-javob: {auto_status}\n"
        f"💻 Kompyuter: ✅\n\n"
        f"Menga xabar yozing yoki quyidagi tugmalardan foydalaning:"
    )
    keyboard = [
        [
            InlineKeyboardButton("📱 Chatlar", callback_data="chats"),
            InlineKeyboardButton("💻 Terminal", callback_data="terminal"),
        ],
        [
            InlineKeyboardButton("🔁 Auto-javob YOQ", callback_data="autoon"),
            InlineKeyboardButton("⏸ To'xtatish", callback_data="autooff"),
        ],
        [InlineKeyboardButton("ℹ️ Holat", callback_data="status")],
    ]
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    # Egasining chat ID'sini saqlaymiz (bildiruv uchun)
    context.application.bot_data["owner_chat_id"] = update.effective_chat.id


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        return

    user_text = update.message.text or ""
    await update.message.chat.send_action(ChatAction.TYPING)

    history = context.user_data.setdefault("history", [])
    history.append({"role": "user", "parts": [user_text]})
    if len(history) > 20:
        history.pop(0)

    response = await ai.ask(user_text, history, SYSTEM_PROMPT)

    if "TG:" in response and userbot and userbot.connected:
        result = await process_tg_command(response, update)
        if result:
            history.append({"role": "model", "parts": [response]})
            return

    if "CMD:" in response:
        result = await process_cmd_command(response, update)
        if result:
            history.append({"role": "model", "parts": [response]})
            return

    history.append({"role": "model", "parts": [response]})
    # parse_mode ishlatmaymiz — Gemini javobidagi simbollar Telegram'ni xato chiqaradi
    try:
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(response)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        return

    await update.message.reply_text("🎤 Ovozli xabaringizni eshityapman...")
    await update.message.chat.send_action(ChatAction.TYPING)

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    try:
        text = await ai.transcribe(tmp_path)
        await update.message.reply_text(f"🎤 Siz: {text}")

        history = context.user_data.setdefault("history", [])
        history.append({"role": "user", "parts": [text]})
        response = await ai.ask(text, history, SYSTEM_PROMPT)
        history.append({"role": "model", "parts": [response]})
        try:
            await update.message.reply_text(response, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(response)
    finally:
        os.unlink(tmp_path)


async def process_tg_command(response: str, update: Update) -> bool:
    try:
        if "TG:LIST_CHATS" in response or "TG:DIALOGS" in response:
            dialogs = await userbot.get_dialogs(limit=10)
            text = "📱 *So'nggi chatlar:*\n\n"
            for d in dialogs:
                text += f"• `{d['id']}` — {d['name']}\n"
            await update.message.reply_text(text, parse_mode="Markdown")
            return True

        if "TG:READ:" in response:
            import re
            match = re.search(r"TG:READ:(-?\d+)", response)
            if match:
                chat_id = int(match.group(1))
                messages = await userbot.get_messages(chat_id, limit=5)
                text = f"💬 *Chat — So'nggi xabarlar:*\n\n"
                for m in messages:
                    text += f"*{m['from']}:* {m['text']}\n"
                await update.message.reply_text(text, parse_mode="Markdown")
                return True

        if "TG:SEND:" in response:
            import re
            match = re.search(r"TG:SEND:(-?\d+):(.+)", response, re.DOTALL)
            if match:
                chat_id = int(match.group(1))
                message = match.group(2).strip()
                await userbot.send_message(chat_id, message)
                await update.message.reply_text(
                    f"✅ Xabar jo'natildi: `{message}`", parse_mode="Markdown"
                )
                return True
    except Exception as e:
        await update.message.reply_text(f"❌ Telegram amali xatosi: {e}")
        return True
    return False


async def process_cmd_command(response: str, update: Update) -> bool:
    try:
        import re
        match = re.search(r"CMD:(.+)", response)
        if match:
            cmd = match.group(1).strip()
            result = await computer.run_command(cmd)
            await update.message.reply_text(
                f"💻 *Buyruq:* `{cmd}`\n\n```\n{result[:3000]}\n```",
                parse_mode="Markdown",
            )
            return True
    except Exception as e:
        await update.message.reply_text(f"❌ Kompyuter amali xatosi: {e}")
        return True
    return False


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "chats":
        if userbot and userbot.connected:
            dialogs = await userbot.get_dialogs(limit=10)
            text = "📱 *So'nggi 10 chat:*\n\n"
            for d in dialogs:
                text += f"• `{d['id']}` — {d['name']}\n"
        else:
            text = "❌ Telegram userbot ulanmagan."
        await query.edit_message_text(text, parse_mode="Markdown")

    elif query.data == "terminal":
        result = await computer.run_command("whoami && pwd && echo '---' && ls ~")
        await query.edit_message_text(
            f"💻 *Terminal:*\n```\n{result}\n```", parse_mode="Markdown"
        )

    elif query.data == "autoon":
        if userbot and userbot.connected:
            userbot.auto_reply = True
            await query.edit_message_text(
                "🔁 *Auto-javob yoqildi!*\n\n"
                "Endi Jarvis sizning shaxsiy chatlaringizga avtomatik javob beradi.\n"
                "Har bir javob haqida sizga bildiruv keladi.\n\n"
                "To'xtatish uchun: /autooff",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text("❌ Telegram userbot ulanmagan.")

    elif query.data == "autooff":
        if userbot:
            userbot.auto_reply = False
        await query.edit_message_text("⏸ *Auto-javob o'chirildi.*", parse_mode="Markdown")

    elif query.data == "status":
        userbot_status = "✅ Ulangan" if (userbot and userbot.connected) else "❌ Ulanmagan"
        text = (
            f"📊 *Holat:*\n\n"
            f"🤖 AI (Gemini): ✅\n"
            f"📱 Telegram: {userbot_status}\n"
            f"💻 Kompyuter: ✅\n"
            f"🕒 Server vaqti: {time.strftime('%H:%M:%S')}"
        )
        await query.edit_message_text(text, parse_mode="Markdown")


async def auto_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-javobni yoqish."""
    if not is_owner(update):
        return
    if userbot and userbot.connected:
        userbot.auto_reply = True
        await update.message.reply_text(
            "🔁 Auto-javob yoqildi! Shaxsiy chatlaringizga Jarvis javob bera boshlaydi."
        )
    else:
        await update.message.reply_text("❌ Userbot ulanmagan.")


async def auto_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-javobni o'chirish."""
    if not is_owner(update):
        return
    if userbot:
        userbot.auto_reply = False
    await update.message.reply_text("⏸ Auto-javob o'chirildi.")


# ─────────────────────────── MAIN ──────────────────────────────

async def post_init(application: Application) -> None:
    """Bot tayyor bo'lgandan so'ng userbot'ni ulang."""
    global userbot
    if TG_API_ID and TG_API_HASH and TG_PHONE:
        try:
            userbot = UserBot(
                api_id=int(TG_API_ID),
                api_hash=TG_API_HASH,
                phone=TG_PHONE,
            )
            await userbot.connect()

            # AI va bildiruv callbacklarini ulash
            userbot.set_ai(ai.ask)

            async def notify_owner(text: str) -> None:
                try:
                    owner = application.bot_data.get("owner_chat_id")
                    if owner:
                        await application.bot.send_message(owner, text, parse_mode="Markdown")
                except Exception:
                    pass

            userbot.set_notify(notify_owner)
            await userbot.start_auto_reply()
            logger.info("✅ Telegram userbot ulandi")
        except Exception as e:
            logger.warning(f"⚠️ Userbot ulana olmadi: {e}")
            userbot = None
    else:
        logger.info("ℹ️ Userbot sozlanmagan")


def main() -> None:
    logger.info("🚀 Jarvis bot ishga tushmoqda...")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("autoon", auto_on))
    app.add_handler(CommandHandler("autooff", auto_off))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("✅ Jarvis tayyor! Polling boshlandi.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
