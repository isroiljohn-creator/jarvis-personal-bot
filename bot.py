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
OWNER_ID = int(os.environ.get("OWNER_TELEGRAM_ID", "0"))  # Faqat siz foydalanishingiz uchun
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
- CMD:SCREENSHOT — ekran rasmini ol
"""

# ────────────────────────── GUARD ──────────────────────────────

def is_owner(update: Update) -> bool:
    """Faqat egasi foydalana olsin."""
    if OWNER_ID == 0:
        return True  # Hali sozlanmagan, hamma foydalana oladi
    return update.effective_user.id == OWNER_ID


# ────────────────────────── HANDLERS ───────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update):
        await update.message.reply_text("❌ Kirish taqiqlangan.")
        return

    userbot_status = "✅ Ulangan" if (userbot and userbot.connected) else "❌ Ulanmagan"
    text = (
        f"👾 *Jarvis — Shaxsiy AI Yordamchi*\n\n"
        f"🤖 AI: Gemini 1.5 Pro ✅\n"
        f"📱 Telegram: {userbot_status}\n"
        f"💻 Kompyuter: ✅\n\n"
        f"Menga xabar yozing — har qanday savolingizga javob beraman.\n\n"
        f"*Misol buyruqlar:*\n"
        f"• `So'nggi 5 chatimni ko'rsat`\n"
        f"• `Falonchiga 'salom' deb yoz`\n"
        f"• `ls ~/Documents bajar`\n"
        f"• `Bugun qanday ishlar bor?`"
    )
    keyboard = [
        [
            InlineKeyboardButton("📱 Chatlar", callback_data="chats"),
            InlineKeyboardButton("💻 Terminal", callback_data="terminal"),
        ],
        [InlineKeyboardButton("ℹ️ Holat", callback_data="status")],
    ]
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Barcha matnli xabarlarni qayta ishlash."""
    if not is_owner(update):
        return

    user_text = update.message.text or ""
    await update.message.chat.send_action(ChatAction.TYPING)

    # Kontekst tarixini saqlash
    history = context.user_data.setdefault("history", [])
    history.append({"role": "user", "parts": [user_text]})
    if len(history) > 20:
        history.pop(0)

    # AI javob olish
    response = await ai.ask(user_text, history, SYSTEM_PROMPT)

    # TG buyruqlari mavjudmi tekshirish
    if "TG:" in response and userbot and userbot.connected:
        result = await process_tg_command(response, update)
        if result:
            history.append({"role": "model", "parts": [response]})
            return

    # CMD buyruqlari mavjudmi tekshirish
    if "CMD:" in response:
        result = await process_cmd_command(response, update)
        if result:
            history.append({"role": "model", "parts": [response]})
            return

    # Oddiy javob
    history.append({"role": "model", "parts": [response]})
    await update.message.reply_text(response, parse_mode="Markdown")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ovozli xabarlarni qayta ishlash."""
    if not is_owner(update):
        return

    await update.message.reply_text("🎤 Ovozli xabaringizni eshikyapman...")
    await update.message.chat.send_action(ChatAction.TYPING)

    # Ovozli faylni yuklab olish
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    try:
        # Gemini orqali transkriptsiya
        text = await ai.transcribe(tmp_path)
        await update.message.reply_text(f"📝 *Siz:* {text}", parse_mode="Markdown")

        # Matn sifatida qayta ishlash
        context.user_data.setdefault("history", [])
        fake_update = update
        # Matnni message sifatida qayta yuboramiz
        history = context.user_data.setdefault("history", [])
        history.append({"role": "user", "parts": [text]})
        response = await ai.ask(text, history, SYSTEM_PROMPT)
        history.append({"role": "model", "parts": [response]})
        await update.message.reply_text(response, parse_mode="Markdown")
    finally:
        os.unlink(tmp_path)


async def process_tg_command(response: str, update: Update) -> bool:
    """Telegram buyruqlarini bajarish."""
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
                text = f"💬 *Chat {chat_id} — So'nggi xabarlar:*\n\n"
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
    """Kompyuter buyruqlarini bajarish."""
    try:
        if "CMD:SCREENSHOT" in response:
            path = await computer.screenshot()
            await update.message.reply_photo(open(path, "rb"), caption="📸 Ekran rasmi")
            return True

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
            text = "❌ Telegram userbot ulanmagan.\nAPI ID va Hash kerak."
        await query.edit_message_text(text, parse_mode="Markdown")

    elif query.data == "terminal":
        result = await computer.run_command("whoami && pwd && echo '---' && ls ~")
        await query.edit_message_text(
            f"💻 *Terminal:*\n```\n{result}\n```", parse_mode="Markdown"
        )

    elif query.data == "status":
        userbot_status = "✅ Ulangan" if (userbot and userbot.connected) else "❌ Ulanmagan"
        text = (
            f"📊 *Holat:*\n\n"
            f"🤖 AI (Gemini): ✅\n"
            f"📱 Telegram: {userbot_status}\n"
            f"💻 Kompyuter: ✅\n"
            f"🕒 Server vaqt: {time.strftime('%H:%M:%S')}"
        )
        await query.edit_message_text(text, parse_mode="Markdown")


# ─────────────────────────── MAIN ──────────────────────────────

async def main() -> None:
    global userbot

    logger.info("🚀 Jarvis bot ishga tushydi...")

    # Telethon userbot
    if TG_API_ID and TG_API_HASH and TG_PHONE:
        try:
            userbot = UserBot(
                api_id=int(TG_API_ID),
                api_hash=TG_API_HASH,
                phone=TG_PHONE,
            )
            await userbot.connect()
            logger.info("✅ Telegram userbot ulandi")
        except Exception as e:
            logger.warning(f"⚠️ Userbot ulana olmadi: {e}")
            userbot = None
    else:
        logger.info("ℹ️ Userbot sozlanmagan (TG_API_ID/HASH/PHONE yoq)")

    # Bot application
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("✅ Jarvis tayyor! Polling boshlandi.")
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
