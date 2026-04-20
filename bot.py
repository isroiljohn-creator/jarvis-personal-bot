"""Jarvis Omni-Channel AI Bot — Telegram, Insta, Cloud, Memory integratsiyasi bilan."""

import asyncio
import logging
import os
import sys
import tempfile
import time
import datetime
import pytz

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
from cloud import CloudHub
from memory import load_memory, update_memory, format_memory_for_prompt, search_memory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("jarvis")

# ───────────────────────── SOZLAMALAR ──────────────────────────

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ.get("OWNER_TELEGRAM_ID", "1392501306"))
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TG_API_ID = os.environ.get("TG_API_ID", "")
TG_API_HASH = os.environ.get("TG_API_HASH", "")
TG_PHONE = os.environ.get("TG_PHONE", "")
VOICE_REPLY = os.environ.get("VOICE_REPLY", "true").lower() == "true"

ai = GeminiAI(GEMINI_API_KEY)
userbot: UserBot | None = None
cloud = CloudHub()

SYSTEM_PROMPT = """Sen — Jarvis. Foydalanuvchining shaxsiy Omni-Channel AI yordamchisisan.
Sening vazifang foydalanuvchining shaxsiy ishlari, rejalari va ijtimoiy tarmoqlarini bitta joydan avtomatlashtirish.

Senda quyidagi toollar (imkoniyatlar) bor:

📅 GOOGLE CALENDAR
- Uchrashuv kiritish (calendar_add_event)
- Kelgusi uchrashuvlarni o'qish (calendar_get_events)

✉️ GMAIL
- Elektron pochtadagi yangi/o'qilmagan xatlarni o'qish (gmail_read_unread)
- Kimgadir pochta orqali xat jo'natish (gmail_send_email)

📱 TELEGRAM (Boshqalarga xabar yozish / o'qish)
- Telegramda kimgadir xabar yuborish (send_telegram_message)
- Telegram ovozli xabar yuborish (send_telegram_voice)
- Chatlarni ko'rish (list_telegram_chats)
- Chat xabarlarini o'qish (read_telegram_chat)

📸 INSTAGRAM
- Kimningdir direktiga(DM) xabar yuborish (insta_send_dm)

🌐 INTERNET & 🧠 XOTIRA
- Internetdan qidirish (web_search)
- Meni ma'lumotlarimni xotiraga yozish (save_memory)

QOIDALAR:
1. Vaqt yoki sana haqida so'ralsa, avval calendar_get_events dan tekshir.
2. Foydalanuvchi "Instadan unga yoz", "Telegramdan unga yoz" deganida mos toollarni tanla.
3. Foydalanuvchi ma'lumot aytsa, darhol save_memory chaqir (menga aytishing shart emas, jim saqla).
4. O'zbek tilida, qisqa, do'stona, va ishonchli uslubda javob ber.
"""


def is_owner(update: Update) -> bool:
    env_id = int(os.environ.get("OWNER_TELEGRAM_ID", "1392501306"))
    if env_id != 0 and update.effective_user.id == env_id:
        return True
    if OWNER_ID == 0:
        return True
    return update.effective_user.id == OWNER_ID

async def check_auth(update: Update) -> bool:
    if is_owner(update):
        return True
    if update.effective_chat and update.effective_chat.type == "private":
        try:
            await update.message.reply_text("Assalomu alaykum. Men Xususiy AI Yordamchisiman va mendan faqatgina Isroiljon Abdullayev foydalana oladilar. Uzr, sizga xizmat ko'rsata olmayman 🤖")
        except: pass
    return False


# ───────────────────── TOOL EXECUTOR ─────────────────────

async def execute_tool(name: str, args: dict) -> str:
    """AI chaqirgan toolni Python funksiyasi orqali bajarish."""
    try:
        # TELEGRAM
        if name == "send_telegram_message":
            return await _tool_send_message(args.get("contact", ""), args.get("message", ""))
        elif name == "send_telegram_voice":
            return await _tool_send_voice(args.get("contact", ""), args.get("message", ""))
        elif name == "list_telegram_chats":
            return await _tool_list_chats(args.get("limit", 10))
        elif name == "read_telegram_chat":
            return await _tool_read_chat(args.get("contact", ""), args.get("limit", 5))
            
        # CLOUD (Notion & Calendar)
        elif name == "notion_add_task":
            return await cloud.notion_add_task(args.get("title", ""), args.get("status", "Kutilmoqda"))
        elif name == "notion_read_tasks":
            return await cloud.notion_read_tasks(args.get("limit", 10))
        elif name == "calendar_add_event":
            return await cloud.calendar_add_event(
                args.get("summary", ""), args.get("start_time", ""), 
                args.get("end_time", ""), args.get("description", "")
            )
        elif name == "calendar_get_events":
            return await cloud.calendar_get_events(args.get("max_results", 5))
            
        # INSTAGRAM
        elif name == "insta_send_dm":
            return await cloud.insta_send_dm(args.get("username", ""), args.get("message", ""))
            
        # GMAIL
        elif name == "gmail_read_unread":
            return await cloud.gmail_read_unread(args.get("limit", 5))
        elif name == "gmail_send_email":
            return await cloud.gmail_send_email(args.get("to_email", ""), args.get("subject", ""), args.get("body", ""))
            
        # OTHER
        elif name == "web_search":
            # Web search va komputer opsiyalari oldingi Cloud Hub emas oddiy duckduckgo ishlatardi hozir shu yerga kichik wrapper qo'shamiz
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(args.get("query", ""), max_results=3))
                return str(results) if results else "Natija topilmadi."
            except:
                return "Qidiruv tizimi ishlamadi."
        elif name == "save_memory":
            return update_memory(args.get("category", "notes"), args.get("key", ""), args.get("value", ""))
            
        elif name == "scrape_website":
            return await cloud.scrape_website(args.get("url", ""))
        elif name == "youtube_transcript":
            return await cloud.youtube_transcript(args.get("url", ""))
        else:
            return f"❌ Noma'lum tool: {name}"

    except Exception as e:
        logger.error(f"Tool xatosi ({name}): {e}", exc_info=True)
        return f"❌ {name} xatosi: {e}"


# ───────────────── Telegram Tool Helpers ─────────────────

async def _tool_send_message(contact: str, message: str) -> str:
    if not userbot or not userbot.connected:
        return "❌ Telegram userbot ulanmagan"
    chat_id = await userbot.find_contact(contact)
    if not chat_id:
        return f"❌ '{contact}' kontakti topilmadi"
    await userbot.send_message(chat_id, message)
    return f"✅ Xabar yuborildi → {contact}"


async def _tool_send_voice(contact: str, message: str) -> str:
    if not userbot or not userbot.connected:
        return "❌ Telegram userbot ulanmagan"
    chat_id = await userbot.find_contact(contact)
    if not chat_id:
        return f"❌ '{contact}' topilmadi"
    ogg_path = await ai.text_to_speech(message)
    if not ogg_path:
        await userbot.send_message(chat_id, message)
        return f"✅ Matnli xabar yuborildi (TTS ishlamadi)"
    try:
        await userbot.send_voice(chat_id, ogg_path)
        return f"✅ Ovozli xabar yuborildi → {contact}"
    finally:
        try: os.unlink(ogg_path)
        except OSError: pass


async def _tool_list_chats(limit: int = 10) -> str:
    if not userbot or not userbot.connected:
        return "❌ Userbot ulanmagan"
    dialogs = await userbot.get_dialogs(limit=limit)
    return "\n".join([f"• [{d['type']}] {d['name']} {d['unread']}" for d in dialogs])


async def _tool_read_chat(contact: str, limit: int = 5) -> str:
    if not userbot or not userbot.connected:
        return "❌ Userbot ulanmagan"
    chat_id = await userbot.find_contact(contact)
    if not chat_id:
        return f"❌ {contact} topilmadi"
    messages = await userbot.get_messages(chat_id, limit=limit)
    return "\n".join([f"{m['date'][:16]} {m['from']}: {m['text'][:100]}" for m in messages])


# ───────────────────── Build System Prompt ─────────────────────

def build_system_prompt(history: list | None = None, query: str = "") -> str:
    from datetime import datetime
    parts = []
    
    # ISO vaqt formatini ham berish muhim, cunki Calendar API ISO ga asoslanadi.
    now = datetime.now()
    parts.append(f"[HOZIRGI VAQT]: {now.strftime('%Y-%m-%d %H:%M, %A')} | ISO: {now.isoformat()[:19]}Z\n")

    mem = search_memory(query) if query else format_memory_for_prompt()
    if mem:
        parts.append(mem + "\n")

    parts.append(SYSTEM_PROMPT)

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
    if not await check_auth(update):
        return

    text = (
        f"🌐 *J.A.R.V.I.S — Omni-Channel AI*\n\n"
        f"Barcha xizmatlaringiz bitta joyda boshqariladi.\n"
        f"📱 Telegram\n📸 Instagram\n📝 Notion\n📅 Calendar\n\n"
        f"Qanday yordam bera olaman?"
    )
    keyboard = [
        [InlineKeyboardButton("🔁 Auto-javob YOQ", callback_data="autoon"), InlineKeyboardButton("⏸ To'xtatish", callback_data="autooff")],
        [InlineKeyboardButton("🧠 Xotira", callback_data="memory"), InlineKeyboardButton("ℹ️ Holat", callback_data="status")]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    context.application.bot_data["owner_chat_id"] = update.effective_chat.id


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    user_text = update.message.text or ""
    if not user_text.strip(): return

    await update.message.chat.send_action(ChatAction.TYPING)
    history = context.user_data.setdefault("history", [])
    history.append({"role": "user", "parts": [user_text]})
    if len(history) > 20: history.pop(0)

    sys_prompt = build_system_prompt(history[:-1], user_text)
    response = await ai.process_message(user_text, sys_prompt, execute_tool)

    history.append({"role": "model", "parts": [response]})
    await _send_reply(update, response)



async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    await update.message.reply_text("🎤 Eshityapman...")
    await update.message.chat.send_action(ChatAction.TYPING)

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    tmp_path = tempfile.mktemp(suffix=".ogg")
    
    try:
        await file.download_to_drive(tmp_path)
        text = await ai.transcribe(tmp_path)
        await update.message.reply_text(f"🎤 Siz: _{text}_", parse_mode="Markdown")

        history = context.user_data.setdefault("history", [])
        history.append({"role": "user", "parts": [text]})
        
        sys_prompt = build_system_prompt(history[:-1], text)
        response = await ai.process_message(text, sys_prompt, execute_tool)
        
        history.append({"role": "model", "parts": [response]})
        await _send_reply(update, response)

        if VOICE_REPLY and len(response) > 10 and len(response) < 2000:
            await _send_voice_reply(update, response)
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    await update.message.chat.send_action(ChatAction.TYPING)

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    tmp_path = tempfile.mktemp(suffix=".jpg")
    try:
        await file.download_to_drive(tmp_path)
        from pathlib import Path
        image_data = Path(tmp_path).read_bytes()

        caption = update.message.caption or "Bu rasmda nima bor?"
        history = context.user_data.setdefault("history", [])
        history.append({"role": "user", "parts": [f"[Rasm] {caption}"]})

        sys_prompt = build_system_prompt(history[:-1], caption)
        response = await ai.process_message(caption, sys_prompt, execute_tool, images=[("image/jpeg", image_data)])

        history.append({"role": "model", "parts": [response]})
        await _send_reply(update, response)
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass


async def _send_reply(update: Update, text: str) -> None:
    try: await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        try: await update.message.reply_text(text)
        except Exception as e: await update.message.reply_text(f"❌ Xato: {e}")


async def _send_voice_reply(update: Update, text: str) -> None:
    try:
        clean = text
        for ch in ("*", "_", "`", "[", "]", "(", ")", "#"): clean = clean.replace(ch, "")
        ogg_path = await ai.text_to_speech(clean)
        if ogg_path:
            try:
                with open(ogg_path, "rb") as f:
                    await update.message.reply_voice(voice=f)
            finally:
                try: os.unlink(ogg_path)
                except OSError: pass
    except Exception as e: logger.warning(f"Ovozli javob xatosi: {e}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "autoon":
        if userbot and userbot.connected:
            userbot.auto_reply = True
            await query.edit_message_text("🔁 *Auto-javob yoqildi!*", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Userbot ulanmagan.")
    elif query.data == "autooff":
        if userbot: userbot.auto_reply = False
        await query.edit_message_text("⏸ *Auto-javob o'chirildi.*", parse_mode="Markdown")
    elif query.data == "memory":
        mem = format_memory_for_prompt()
        await query.edit_message_text(mem if mem else "🧠 Xotira bo'sh.")
    elif query.data == "status":
        ub_status = "✅ Ulangan" if (userbot and userbot.connected) else "❌ Ulanmagan"
        auto = "✅" if (userbot and userbot.auto_reply) else "⏸"
        text = (
            f"📊 *Holat:*\n"
            f"🧠 AI: ✅\n📱 Telegram: {ub_status}\n🔁 Auto-javob: {auto}\n"
            f"☁️ Cloud: ✅\n🕒 Server: {time.strftime('%H:%M:%S')}"
        )
        await query.edit_message_text(text, parse_mode="Markdown")


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update): return
    context.user_data["history"] = []
    await update.message.reply_text("🗑 Suhbat tarixi tozalandi.")


async def post_init(application: Application) -> None:
    global userbot
    if TG_API_ID and TG_API_HASH and TG_PHONE:
        try:
            userbot = UserBot(api_id=int(TG_API_ID), api_hash=TG_API_HASH, phone=TG_PHONE)
            await userbot.connect()
            global OWNER_ID
            try:
                me = await userbot.client.get_me()
                if me:
                    OWNER_ID = me.id
                    logger.info(f"🔒 Bot xavfsizlik uchun faqat {OWNER_ID} ga qulflangan!")
            except Exception as ex:
                logger.warning(f"Owner ID olishda xato: {ex}")
            async def ai_for_autoreply(text, history, system):
                return await ai.process_message(text, system, execute_tool)
            userbot.set_ai(ai_for_autoreply)

            async def notify_owner(text: str):
                try:
                    owner = application.bot_data.get("owner_chat_id")
                    if owner: await application.bot.send_message(owner, text, parse_mode="Markdown")
                except: pass
            
            userbot.set_notify(notify_owner)
            await userbot.start_auto_reply()
        except Exception as e:
            logger.warning(f"⚠️ Userbot ulana olmadi: {e}")
            userbot = None

    try:
        import uvicorn
        from api import app as fastapi_app, BOT_CONTEXT
        BOT_CONTEXT["ai"] = ai
        BOT_CONTEXT["userbot"] = userbot
        BOT_CONTEXT["build_system_prompt"] = build_system_prompt
        BOT_CONTEXT["execute_tool"] = execute_tool
        
        port = int(os.environ.get("PORT", "8080"))
        config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port, log_level="warning")
        server = uvicorn.Server(config)
        asyncio.create_task(server.serve())
        logger.info(f"🚀 FastAPI Webhook serveri {port}-portida ishga tushdi.")
    except Exception as e:
        logger.error(f"FastAPI ishga tushmadi: {e}")


async def daily_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("⏱ Daily Digest jarayoni boshlandi...")
    if not userbot:
        return
    text_data = await userbot.get_daily_digest_messages(limit_dialogs=40)
    if not text_data:
        try: await userbot.send_message("me", "📭 Yordamchi Tahlili: Bugun o'qilmagan xabarlar yo'q.")
        except: pass
        return

    prompt = "Quyida foydalanuvchining bugungi barcha muhim chatlaridan yig'ilgan xabarlar ro'yxati berilgan. Bularni o'qib eng muhim, ahamiyatli qismlarini (priority boyicha) asosiy planga chiqarib, eng oxirida muhimlik darajasida o'zbekcha chiroyli hisobot qilib (Digest) ber:\n\n" + text_data
    
    try:
        sys_prompt = build_system_prompt([])
        response = await ai.process_message("Menga bugungi chatlar tahlilini ber!\n\n" + prompt, sys_prompt, execute_tool)
        report = f"📊 *Kunlik Kechki Telegram Tahlili (20:00)*\n\n{response}"
        # O'zining Saved Messages'iga yuborish
        await userbot.send_message("me", report)
    except Exception as e:
        logger.error(f"Digest yuborishda xato: {e}")

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))

    tz = pytz.timezone("Asia/Tashkent")
    t = datetime.time(hour=20, minute=0, tzinfo=tz)
    app.job_queue.run_daily(daily_digest_job, time=t)

    logger.info("✅ Jarvis tayyor! Polling boshlandi.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
