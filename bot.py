"""Jarvis Personal AI Bot — Function Calling, Vision, Voice bilan."""

import asyncio
import logging
import os
import sys
import tempfile
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
from memory import load_memory, update_memory, format_memory_for_prompt

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
VOICE_REPLY = os.environ.get("VOICE_REPLY", "true").lower() == "true"

ai = GeminiAI(GEMINI_API_KEY)
userbot: UserBot | None = None
computer = ComputerAgent()

SYSTEM_PROMPT = """Sen — Jarvis. Foydalanuvchining shaxsiy AI yordamchisi.
Sen quyidagi imkoniyatlarga egasan:

🖥 KOMPYUTER BOSHQARUVI:
- Terminal buyruqlarini bajarish (run_command)
- Ekran rasmini olish va tahlil qilish (screenshot_analyze)
- Dasturlarni ochish (open_app)
- Fayllar bilan ishlash (file_operation)
- Tizim ma'lumotlarini ko'rish (system_info)

🌐 INTERNET:
- Web qidirish (web_search)

📱 TELEGRAM:
- Boshqa kishilarga xabar yuborish (send_telegram_message)
- Ovozli xabar yuborish (send_telegram_voice)
- Chatlar ro'yxatini ko'rish (list_telegram_chats)
- Chat xabarlarini o'qish (read_telegram_chat)

🧠 XOTIRA:
- Foydalanuvchi haqidagi ma'lumotlarni eslab qolish (save_memory)

QOIDALAR:
1. O'zbek tilida javob ber (agar foydalanuvchi boshqa tilda gaplashsa, o'sha tilda)
2. Qisqa va aniq javob ber
3. Buyruqlarni DOIM toollar orqali bajargina — hech qachon simulyatsiya qilma
4. Foydalanuvchi shaxsiy ma'lumot aytsa, jim save_memory chaqir
5. Agar foydalanuvchi kimgadir xabar yubor desa, send_telegram_message ishlatgina
6. Har doim do'stona va professional bo'l
"""


def is_owner(update: Update) -> bool:
    """Faqat egasi foydalanishi mumkin."""
    if OWNER_ID == 0:
        return True
    return update.effective_user.id == OWNER_ID


# ───────────────────── TOOL EXECUTOR ─────────────────────


async def execute_tool(name: str, args: dict) -> str:
    """Tool nomiga qarab funksiyani bajarish."""
    try:
        if name == "run_command":
            return await computer.run_command(args.get("command", "echo 'no command'"))

        elif name == "screenshot_analyze":
            img_data = await computer.screenshot()
            if img_data:
                question = args.get("question", "Ekranda nima bor?")
                return await ai.analyze_image(img_data, question)
            return "❌ Screenshot olishning imkoni yo'q (server muhitida)"

        elif name == "open_app":
            return await computer.open_app(args.get("app_name", ""))

        elif name == "web_search":
            return await computer.web_search(args.get("query", ""))

        elif name == "send_telegram_message":
            return await _tool_send_message(
                args.get("contact", ""), args.get("message", "")
            )

        elif name == "send_telegram_voice":
            return await _tool_send_voice(
                args.get("contact", ""), args.get("message", "")
            )

        elif name == "list_telegram_chats":
            return await _tool_list_chats(args.get("limit", 10))

        elif name == "read_telegram_chat":
            return await _tool_read_chat(
                args.get("contact", ""), args.get("limit", 5)
            )

        elif name == "file_operation":
            return await computer.file_operation(
                action=args.get("action", "list"),
                path=args.get("path", ""),
                content=args.get("content", ""),
                search_name=args.get("search_name", ""),
            )

        elif name == "save_memory":
            return update_memory(
                args.get("category", "notes"),
                args.get("key", ""),
                args.get("value", ""),
            )

        elif name == "system_info":
            return await computer.system_info()

        else:
            return f"❌ Noma'lum tool: {name}"

    except Exception as e:
        logger.error(f"Tool xatosi ({name}): {e}", exc_info=True)
        return f"❌ {name} xatosi: {e}"


# ───────────────── Telegram Tool Helpers ─────────────────


async def _tool_send_message(contact: str, message: str) -> str:
    """Telegram xabar yuborish tool."""
    if not userbot or not userbot.connected:
        return "❌ Telegram userbot ulanmagan"
    chat_id = await userbot.find_contact(contact)
    if not chat_id:
        return f"❌ '{contact}' kontakti topilmadi"
    await userbot.send_message(chat_id, message)
    return f"✅ Xabar yuborildi → {contact}"


async def _tool_send_voice(contact: str, message: str) -> str:
    """Telegram ovozli xabar yuborish tool."""
    if not userbot or not userbot.connected:
        return "❌ Telegram userbot ulanmagan"

    chat_id = await userbot.find_contact(contact)
    if not chat_id:
        return f"❌ '{contact}' kontakti topilmadi"

    ogg_path = await ai.text_to_speech(message)
    if not ogg_path:
        # TTS ishlamasa, oddiy matn yuboramiz
        await userbot.send_message(chat_id, message)
        return f"✅ Matnli xabar yuborildi → {contact} (TTS ishlamadi)"

    try:
        await userbot.send_voice(chat_id, ogg_path)
        return f"✅ Ovozli xabar yuborildi → {contact}"
    finally:
        try:
            os.unlink(ogg_path)
        except OSError:
            pass


async def _tool_list_chats(limit: int = 10) -> str:
    """Telegram chatlar ro'yxati tool."""
    if not userbot or not userbot.connected:
        return "❌ Telegram userbot ulanmagan"
    dialogs = await userbot.get_dialogs(limit=limit)
    if not dialogs:
        return "Chatlar topilmadi."
    lines = ["📱 So'nggi chatlar:\n"]
    for d in dialogs:
        unread = f" ({d['unread']} yangi)" if d["unread"] else ""
        lines.append(f"• [{d['type']}] {d['name']}{unread}  (ID: {d['id']})")
    return "\n".join(lines)


async def _tool_read_chat(contact: str, limit: int = 5) -> str:
    """Telegram chat xabarlarini o'qish tool."""
    if not userbot or not userbot.connected:
        return "❌ Telegram userbot ulanmagan"
    chat_id = await userbot.find_contact(contact)
    if not chat_id:
        return f"❌ '{contact}' topilmadi"
    messages = await userbot.get_messages(chat_id, limit=limit)
    if not messages:
        return "Xabarlar topilmadi."
    lines = [f"💬 {contact} — so'nggi {len(messages)} xabar:\n"]
    for m in messages:
        lines.append(f"[{m['date'][:16]}] {m['from']}: {m['text'][:200]}")
    return "\n".join(lines)


# ───────────────────── Build System Prompt ─────────────────────


def build_system_prompt(history: list | None = None) -> str:
    """Tizim ko'rsatmasini qurish — memory + tarix bilan."""
    from datetime import datetime

    parts = []

    # Vaqt konteksti
    now = datetime.now()
    parts.append(
        f"[HOZIRGI VAQT]: {now.strftime('%Y-%m-%d %H:%M, %A')}\n"
    )

    # Xotira
    mem = format_memory_for_prompt()
    if mem:
        parts.append(mem + "\n")

    # Asosiy prompt
    parts.append(SYSTEM_PROMPT)

    # Suhbat tarixi
    if history:
        parts.append("\n[SO'NGGI SUHBAT]:")
        for msg in history[-10:]:
            role = "Foydalanuvchi" if msg["role"] == "user" else "Jarvis"
            text = msg.get("parts", [""])[0]
            if text:
                parts.append(f"{role}: {text[:300]}")

    return "\n".join(parts)


# ───────────────────── MESSAGE HANDLERS ─────────────────────


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot boshlash."""
    if not is_owner(update):
        await update.message.reply_text("❌ Kirish taqiqlangan.")
        return

    ub_status = "✅ Ulangan" if (userbot and userbot.connected) else "❌ Ulanmagan"
    auto_status = "✅ Yoqiq" if (userbot and userbot.auto_reply) else "⏸ O'chiq"
    voice_status = "✅ Yoqiq" if VOICE_REPLY else "⏸ O'chiq"

    text = (
        f"👾 *J.A.R.V.I.S — Shaxsiy AI Yordamchi*\n\n"
        f"🧠 AI: Gemini 2.0 Flash ✅\n"
        f"📱 Telegram: {ub_status}\n"
        f"🔁 Auto-javob: {auto_status}\n"
        f"🔊 Ovozli javob: {voice_status}\n"
        f"💻 Kompyuter: ✅\n\n"
        f"Menga yozing — men hamma narsani bajara olaman!"
    )
    keyboard = [
        [
            InlineKeyboardButton("📱 Chatlar", callback_data="chats"),
            InlineKeyboardButton("💻 Tizim", callback_data="sysinfo"),
        ],
        [
            InlineKeyboardButton("🔁 Auto-javob YOQ", callback_data="autoon"),
            InlineKeyboardButton("⏸ To'xtatish", callback_data="autooff"),
        ],
        [
            InlineKeyboardButton("🧠 Xotira", callback_data="memory"),
            InlineKeyboardButton("ℹ️ Holat", callback_data="status"),
        ],
    ]
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    context.application.bot_data["owner_chat_id"] = update.effective_chat.id


async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Matnli xabarni qayta ishlash — Function Calling bilan."""
    if not is_owner(update):
        return

    user_text = update.message.text or ""
    if not user_text.strip():
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    # Suhbat tarixini olish
    history = context.user_data.setdefault("history", [])
    history.append({"role": "user", "parts": [user_text]})
    if len(history) > 20:
        history.pop(0)

    # System prompt qurish
    sys_prompt = build_system_prompt(history[:-1])  # Oxirgi xabar promptda emas

    # AI dan javob olish (function calling loop ichida)
    response = await ai.process_message(
        prompt=user_text,
        system_prompt=sys_prompt,
        tool_executor=execute_tool,
    )

    # Tarixga qo'shish
    history.append({"role": "model", "parts": [response]})

    # Matnli javob yuborish
    await _send_reply(update, response)

    # Ovozli javob (ixtiyoriy)
    if VOICE_REPLY and len(response) > 10 and len(response) < 2000:
        await _send_voice_reply(update, response)


async def handle_voice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Ovozli xabarni qayta ishlash."""
    if not is_owner(update):
        return

    await update.message.reply_text("🎤 Tinglayapman...")
    await update.message.chat.send_action(ChatAction.TYPING)

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)

    tmp_path = tempfile.mktemp(suffix=".ogg")
    try:
        await file.download_to_drive(tmp_path)

        # Transkripsiya
        text = await ai.transcribe(tmp_path)
        await update.message.reply_text(f"🎤 Siz: _{text}_", parse_mode="Markdown")

        # Xabarni qayta ishlash
        history = context.user_data.setdefault("history", [])
        history.append({"role": "user", "parts": [text]})
        if len(history) > 20:
            history.pop(0)

        sys_prompt = build_system_prompt(history[:-1])

        response = await ai.process_message(
            prompt=text,
            system_prompt=sys_prompt,
            tool_executor=execute_tool,
        )

        history.append({"role": "model", "parts": [response]})
        await _send_reply(update, response)

        # Ovozli javob
        if VOICE_REPLY and len(response) > 10 and len(response) < 2000:
            await _send_voice_reply(update, response)

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def handle_photo(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Rasm/foto xabarni qayta ishlash — Gemini Vision."""
    if not is_owner(update):
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    photo = update.message.photo[-1]  # Eng katta razmer
    file = await context.bot.get_file(photo.file_id)

    tmp_path = tempfile.mktemp(suffix=".jpg")
    try:
        await file.download_to_drive(tmp_path)
        from pathlib import Path

        image_data = Path(tmp_path).read_bytes()

        caption = update.message.caption or "Bu rasmda nima bor?"

        # Rasm + matn bilan AI ga yuborish
        history = context.user_data.setdefault("history", [])
        history.append({"role": "user", "parts": [f"[Rasm yuborildi] {caption}"]})

        sys_prompt = build_system_prompt(history[:-1])

        response = await ai.process_message(
            prompt=caption,
            system_prompt=sys_prompt,
            tool_executor=execute_tool,
            images=[("image/jpeg", image_data)],
        )

        history.append({"role": "model", "parts": [response]})
        await _send_reply(update, response)

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ───────────────────── Reply helpers ─────────────────────


async def _send_reply(update: Update, text: str) -> None:
    """Javobni yuborish (Markdown sinab ko'radi, xato bo'lsa oddiy matn)."""
    try:
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        try:
            await update.message.reply_text(text)
        except Exception as e:
            await update.message.reply_text(f"❌ Javob yuborishda xato: {e}")


async def _send_voice_reply(update: Update, text: str) -> None:
    """AI javobini ovozli xabar sifatida yuborish."""
    try:
        # Markdown belgilarini tozalash
        clean = text
        for ch in ("*", "_", "`", "[", "]", "(", ")", "#"):
            clean = clean.replace(ch, "")

        ogg_path = await ai.text_to_speech(clean)
        if ogg_path:
            try:
                with open(ogg_path, "rb") as f:
                    await update.message.reply_voice(voice=f)
            finally:
                try:
                    os.unlink(ogg_path)
                except OSError:
                    pass
    except Exception as e:
        logger.warning(f"Ovozli javob xatosi: {e}")


# ───────────────────── CALLBACK BUTTONS ─────────────────────


async def button_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Inline tugmalar."""
    query = update.callback_query
    await query.answer()

    if query.data == "chats":
        result = await _tool_list_chats(10)
        await query.edit_message_text(result)

    elif query.data == "sysinfo":
        result = await computer.system_info()
        await query.edit_message_text(result)

    elif query.data == "autoon":
        if userbot and userbot.connected:
            userbot.auto_reply = True
            await query.edit_message_text(
                "🔁 *Auto-javob yoqildi!*\n\n"
                "Jarvis shaxsiy chatlaringizga avtomatik javob beradi.\n"
                "To'xtatish: /autooff",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text("❌ Telegram userbot ulanmagan.")

    elif query.data == "autooff":
        if userbot:
            userbot.auto_reply = False
        await query.edit_message_text(
            "⏸ *Auto-javob o'chirildi.*", parse_mode="Markdown"
        )

    elif query.data == "memory":
        mem = format_memory_for_prompt()
        text = mem if mem else "🧠 Xotira bo'sh — hali hech narsa saqlanmagan."
        await query.edit_message_text(text)

    elif query.data == "status":
        ub_status = (
            "✅ Ulangan" if (userbot and userbot.connected) else "❌ Ulanmagan"
        )
        auto = "✅" if (userbot and userbot.auto_reply) else "⏸"
        text = (
            f"📊 *Holat:*\n\n"
            f"🧠 AI (Gemini 2.0 Flash): ✅\n"
            f"📱 Telegram userbot: {ub_status}\n"
            f"🔁 Auto-javob: {auto}\n"
            f"🔊 Ovozli javob: {'✅' if VOICE_REPLY else '⏸'}\n"
            f"💻 Kompyuter: ✅\n"
            f"🕒 Server vaqti: {time.strftime('%H:%M:%S')}"
        )
        await query.edit_message_text(text, parse_mode="Markdown")


# ───────────────────── COMMANDS ─────────────────────


async def auto_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-javobni yoqish."""
    if not is_owner(update):
        return
    if userbot and userbot.connected:
        userbot.auto_reply = True
        await update.message.reply_text(
            "🔁 Auto-javob yoqildi! Jarvis shaxsiy chatlaringizga javob beradi."
        )
    else:
        await update.message.reply_text("❌ Userbot ulanmagan.")


async def auto_off(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Auto-javobni o'chirish."""
    if not is_owner(update):
        return
    if userbot:
        userbot.auto_reply = False
    await update.message.reply_text("⏸ Auto-javob o'chirildi.")


async def clear_history(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Suhbat tarixini tozalash."""
    if not is_owner(update):
        return
    context.user_data["history"] = []
    await update.message.reply_text("🗑 Suhbat tarixi tozalandi.")


# ─────────────────────── MAIN ──────────────────────────


async def post_init(application: Application) -> None:
    """Bot tayyor — userbot'ni ulash."""
    global userbot
    if TG_API_ID and TG_API_HASH and TG_PHONE:
        try:
            userbot = UserBot(
                api_id=int(TG_API_ID),
                api_hash=TG_API_HASH,
                phone=TG_PHONE,
            )
            await userbot.connect()

            # Auto-reply uchun AI callback
            async def ai_for_autoreply(text, history, system):
                return await ai.process_message(
                    prompt=text,
                    system_prompt=system,
                    tool_executor=execute_tool,
                )

            userbot.set_ai(ai_for_autoreply)

            async def notify_owner(text: str) -> None:
                try:
                    owner = application.bot_data.get("owner_chat_id")
                    if owner:
                        await application.bot.send_message(
                            owner, text, parse_mode="Markdown"
                        )
                except Exception:
                    pass

            userbot.set_notify(notify_owner)
            await userbot.start_auto_reply()
            logger.info("✅ Telegram userbot ulandi")
        except Exception as e:
            logger.warning(f"⚠️ Userbot ulana olmadi: {e}")
            userbot = None
    else:
        logger.info("ℹ️ Userbot sozlanmagan (TG_API_ID/TG_API_HASH/TG_PHONE yo'q)")


def main() -> None:
    logger.info("🚀 Jarvis bot ishga tushmoqda...")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("autoon", auto_on))
    app.add_handler(CommandHandler("autooff", auto_off))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("✅ Jarvis tayyor! Polling boshlandi.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
