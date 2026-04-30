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
from session import add_to_history, get_history, clear_history as clear_shared_history

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
GLOBAL_JOB_QUEUE = None
GLOBAL_BOT = None
PLAN_COLLECTION_MODE = False

DICTATOR_PROMPT = """You are J.A.R.V.I.S, Isroiljon's Personal Productivity Partner and Discipline Commander.
Your mission is to ensure Isroiljon achieves his goals with maximum discipline and focus.

CORE PERSONALITY:
- Be firm, direct, and serious.
- Do not accept lazy excuses (tired, later, no mood).
- **CRITICAL**: Recognize that content research, viral video analysis, and trend searching are ESSENTIAL work tasks for growth. If Isroiljon asks for these, execute them immediately with high precision. Do NOT block them as "time wasting".
- Your goal is results. High-quality content research leads to high-quality results.

DISCIPLINE PROTOCOL:
- Use principles from "Atomic Habits", "Deep Work", and "Essentialism" to keep him focused.
- If he avoids a main task, bring him back.
- If he asks for creative research, support it fully as part of his "Deep Work".

I am Isroiljon. Your name is J.A.R.V.I.S. Address me strictly as "Isroiljon". Your language is Uzbek.
"""

SYSTEM_PROMPT = """Sening isming J.A.R.V.I.S. Sen Isroiljonning shaxsiy Hayot Murabbiyi va Nazoratchisisan (Discipline Commander).
Sening maqsading - uning rejalari, ishi va odatlarini nazorat qilish. 
MUHIM: Kontent tadqiqoti, viral videolarni tahlil qilish va trendlarni qidirish — bu foydali ish jarayonining bir qismi deb hisoblanadi. Agar Isroiljon shunday buyruq bersa, uni rad etma, aksincha, eng sifatli viral kontentni topib, yuklab ber va tahlil qil.
Unga doimo "Isroiljon" deb murojaat qil. So'zlaringda qat'iylik bo'lsin, lekin foydali buyruqlarni (masalan, viral video qidirishni) bekorchi ish deb hisoblama.
Bahonalarni (charchadim, ertaga qilaman) qabul qilma, lekin kreativ ish so'rovlarini bajar.

Imkoniyatlaring (Tools):
📅 Google Calendar — uchrashuv kiritish (calendar_add_event), o'qish (calendar_get_events)
✉️ Gmail — xatlarni o'qish (gmail_read_unread) va jo'natish (gmail_send_email)
📱 Telegram — yozish (send_telegram_message) yoki chatlarni o'qish (read_telegram_chat)
🌐 Internet — qidiruv (web_search) va saytlarni to'liq o'qish (scrape_website)
📹 YouTube — videolarning matnini o'qib xulosa qilish (youtube_transcript)
🧠 Xotira — muhim narsalarni saqlash (save_memory)
📱 iPhone — budilnik, ilovalar ochish, ovoz pasaytirish (phone_control)
⏰ Aqlli Eslatma — aniq bir vaqtda Telegram orqali xabar eslatish (set_reminder). Vaqtni albatta ISO formatida yubor (time parametriga, masalan: 2026-04-25T15:30:00).

QOIDALAR:
1. Faqat O'zbek tilida, sovuqqon va qat'iy qo'mondon tonida javob ber. Hech qanday keraksiz emojilar va yumshoq so'zlar ishlatma.
2. "Deep Research" yozsa avval web_search so'ng scrape_website qil. YouTube havolasi tashlansa albatta youtube_transcript orqali uni tahlil qilib xulosa ber.
3. Instagramdan viral videolar qidirish buyurilsa, `insta_get_niche_trends` orqali trendlarni top va har bir mos keladigan video uchun `insta_download_media` orqali videoni yuklab yubor. Shunchaki havola berish yetarli emas, videoning o'zi yuborilishi shart!
4. Moliyaviy tizimda "Dollar", "$", "bucks" ishlatganda currency "USD", "so'm", "ming" deganda "UZS" ga yoz. Va "naqd" yoki "karta" yordamida to'langanligiga e'tibor qil. Agar mavhum bo'lsa default: "karta", "UZS".
5. Har bir gaping qisqa, aniq va ultimatum/buyruq ohangida bo'lsin. Hech qachon "yaxshi dam oling" kabi bo'shashtiradigan gaplar gapirma, faqat qachon ishga qaytishini va aniq rejani so'ra.
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
        elif name == "insta_get_niche_trends":
            return await cloud.insta_get_niche_trends(args.get("hashtag", ""), args.get("limit", 3))
        elif name == "insta_download_media":
            return await _tool_insta_download(args.get("url", ""))
            
        # GMAIL
        elif name == "gmail_read_unread":
            return await cloud.gmail_read_unread(args.get("limit", 5))
        elif name == "gmail_send_email":
            return await cloud.gmail_send_email(args.get("to_email", ""), args.get("subject", ""), args.get("body", ""))
            
        # OTHER
        elif name == "web_search":
            try:
                from duckduckgo_search import DDGS
                proxy_url = os.environ.get("PROXY_URL")
                with DDGS(proxy=proxy_url) as ddgs:
                    results = list(ddgs.text(args.get("query", ""), max_results=3))
                return str(results) if results else "Natija topilmadi."
            except Exception as e:
                return f"Qidiruv tizimi ishlamadi: {e}"
        elif name == "save_memory":
            return update_memory(args.get("category", "notes"), args.get("key", ""), args.get("value", ""))
        elif name == "set_reminder":
            time_str = args.get("time", "")
            message  = args.get("message", "")
            try:
                import datetime as _dt
                import pytz as _pytz
                import json as _json

                dt = _dt.datetime.fromisoformat(time_str)
                if dt.tzinfo is None:
                    dt = _pytz.timezone("Asia/Tashkent").localize(dt)

                now = _dt.datetime.now(dt.tzinfo)
                if dt <= now:
                    return f"❌ Berilgan vaqt o'tib ketgan ({dt.strftime('%Y-%m-%d %H:%M')})."

                from api import push_phone_command
                # iOS Reminders ga yuboramiz (Shortcuts polling)
                push_phone_command("reminder_add", _json.dumps({
                    "title": message,
                    "due_date": dt.isoformat(),
                    "list_name": "J.A.R.V.I.S",
                    "priority": 5
                }))

                if GLOBAL_JOB_QUEUE:
                    GLOBAL_JOB_QUEUE.run_once(
                        reminder_job_callback,
                        when=dt,
                        data={"text": message}
                    )
                    return (
                        f"✅ Eslatma saqlandi!\n"
                        f"📱 iOS Reminders ga qo'shildi\n"
                        f"🔔 Telegram ham eslatadi: {dt.strftime('%Y-%m-%d %H:%M')}"
                    )
                else:
                    return f"✅ iOS Reminders ga qo'shildi: {dt.strftime('%Y-%m-%d %H:%M')}"

            except Exception as e:
                return f"❌ Vaqt formati noto'g'ri (ISO kutilyapti, masalan 2026-04-24T15:30:00): {e}"
            
        elif name == "log_finance":
            import database
            currency = args.get("currency", "UZS")
            amount = float(args.get("amount", 0))
            if currency == "USD":
                amount = amount * 12950
                currency = "UZS"
            return await database.db_log_transaction(
                args.get("type", "expense"),
                amount,
                args.get("category", "Boshqa"),
                args.get("description", ""),
                args.get("payment_method", "naqd"),
                currency
            )
        elif name == "get_finance_summary":
            import database
            data = await database.db_get_finance_data()
            try:
                msg = f"UZS: Daromad: {data['uzs']['income']}, Xarajat: {data['uzs']['expense']}, Qoldiq: {data['uzs']['balance']} UZS.\n"
                msg += f"USD: Daromad: {data['usd']['income']}, Xarajat: {data['usd']['expense']}, Qoldiq: {data['usd']['balance']} USD."
                return msg
            except:
                return "Ma'lumot topilmadi yoki hisoblashda xatolik."
            
        elif name == "scrape_website":
            return await cloud.scrape_website(args.get("url", ""))
        elif name == "youtube_transcript":
            return await cloud.youtube_transcript(args.get("url", ""))
        elif name == "phone_control":
            from api import push_phone_command
            action  = args.get("action", "url")
            payload = args.get("payload", "")
            time    = args.get("time", "")
            push_phone_command(action, payload, time)
            action_labels = {
                "alarm":    f"⏰ Budilnik qo'yildi: {time}",
                "music":    f"🎵 Musiqa navbatga qo'yildi: {payload}",
                "url":      f"🔗 Ilova/Havola ochiladi: {payload}",
                "reminder": f"🔔 Eslatma qo'yildi: {payload} | Vaqti: {time}",
                "call":     f"📞 Qo'ng'iroq qilinadi: {payload}",
                "message":  f"💬 SMS yuboriladi: {payload}",
                "wifi":     f"🛜 Wi-Fi boshqaruvi: {payload or 'off'}",
            }
            return action_labels.get(action, f"✅ Telefon buyrug'i yuborildi: {action}")
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


async def _tool_insta_download(url: str) -> str:
    if not userbot or not userbot.connected:
        return "❌ Userbot ulanmagan"
    
    # Userga bildirishnoma yuboramiz
    await userbot.send_message("me", "⏳ Instagramdan media yuklab olinmoqda, kuting...")
    
    file_path = await cloud.insta_download_media(url)
    if not file_path:
        return "❌ Media yuklab olishda xatolik yuz berdi. Havola noto'g'ri yoki proxy bloklangan bo'lishi mumkin."
    
    try:
        # Faylni egasiga yuboramiz
        await userbot.send_file("me", file_path, caption=f"✅ Instagramdan yuklandi:\n{url}")
        return "✅ Media muvaffaqiyatli yuklab olindi va yuborildi."
    except Exception as e:
        return f"❌ Faylni yuborishda xato: {e}"
    finally:
        # Faylni o'chiramiz (vaqtinchalik joyni tejash uchun)
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except:
            pass


# ───────────────────── Build System Prompt ─────────────────────

def build_system_prompt(history: list | None = None, query: str = "") -> str:
    from datetime import datetime
    import pytz
    parts = []
    
    # ISO vaqt formatini ham berish muhim, cunki Calendar API ISO ga asoslanadi.
    now = datetime.now(pytz.timezone("Asia/Tashkent"))
    parts.append(f"[HOZIRGI VAQT]: {now.strftime('%Y-%m-%d %H:%M, %A')} | ISO: {now.isoformat()[:19]}Z\n")

    try:
        mem = search_memory(query) if query else format_memory_for_prompt(load_memory())
        if mem:
            parts.append(mem + "\n")
    except Exception as e:
        logger.error(f"Memory parse xatosi: {e}")

    parts.append(SYSTEM_PROMPT)

    if history:
        parts.append("\n[SO'NGGI SUHBAT]:")
        for msg in history[-10:]:
            role = "Isroiljon" if msg["role"] == "user" else "J.A.R.V.I.S"
            text = msg.get("parts", [""])[0]
            if text:
                parts.append(f"{role}: {text[:300]}")

    return "\n".join(parts)


# ───────────────────── MESSAGE HANDLERS ─────────────────────

async def reminder_job_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.job: return
    text = context.job.data.get("text", "Eslatma!")
    try:
        if userbot:
            await userbot.send_message("@abdullayev_ii", f"🔔 **Eslatma:**\n\n{text}")
        elif GLOBAL_BOT and OWNER_ID:
            await GLOBAL_BOT.send_message(OWNER_ID, f"🔔 *Eslatma:*\n\n{text}".replace("**", "*"), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Reminder yuborishda xato: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update):
        return

    text = (
        f"🌐 *J.A.R.V.I.S — Omni-Channel AI*\n\n"
        f"Barcha xizmatlaringiz bitta joyda boshqariladi.\n"
        f"📱 Telegram\n📸 Instagram\n📝 Notion\n📅 Calendar\n\n"
        f"Qanday yordam bera olaman?"
    )
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "jarvis-personal-bot.up.railway.app")
    finance_url = f"https://{domain}/finance" if not domain.startswith("http") else f"{domain}/finance"
    
    from telegram import WebAppInfo
    keyboard = [
        [InlineKeyboardButton("🔁 Auto-javob YOQ", callback_data="autoon"), InlineKeyboardButton("⏸ To'xtatish", callback_data="autooff")],
        [InlineKeyboardButton("🧠 Xotira", callback_data="memory"), InlineKeyboardButton("ℹ️ Holat", callback_data="status")],
        [InlineKeyboardButton("💰 Moliya (Kirim/Chiqim)", web_app=WebAppInfo(url=finance_url))]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    context.application.bot_data["owner_chat_id"] = update.effective_chat.id


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    user_text = update.message.text or ""
    if not user_text.strip(): return

    global PLAN_COLLECTION_MODE
    import database

    if PLAN_COLLECTION_MODE:
        # Agar xabar vazifa emas, balki buyruq yoki savolga o'xshasa (uzunroq gap yoki so'roq bo'lsa), rejimdan chiqamiz
        if len(user_text.split()) > 5 or "?" in user_text:
            PLAN_COLLECTION_MODE = False
            await update.message.reply_text("🔄 Reja yig'ish rejimi avtomatik yopildi, AI so'rovingizga o'taman...")
        else:
            import datetime
            now = datetime.datetime.now(pytz.timezone("Asia/Tashkent"))
        target_date = now.strftime("%Y-%m-%d")
        if now.hour >= 18:
            target_date = (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        lines = [ln.strip() for ln in user_text.split("\n") if ln.strip()]
        tasks = await database.db_get_plan(target_date)
        
        for ln in lines:
            priority = "normal"
            if ln.startswith("[!]"):
                priority = "high"
                ln = ln.replace("[!]", "").strip()
            # raqamlash bilan kiritilsa (masalan 1. Qilish kerak), raqamni olib tashlash
            import re
            ln = re.sub(r'^\d+[\.\)\-]\s*', '', ln)
            tasks.append({"text": ln, "done": False, "priority": priority})
            
        await database.db_save_plan(target_date, tasks)
        await update.message.reply_text(
            f"✅ {len(lines)} ta vazifa {target_date} rejasiga qo'shildi!\n"
            f"(Yana kiritishda davom eting yoki tugatganda /done deng)"
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    # ── Umumiy (Telegram + iOS) tarix ──
    await add_to_history("user", user_text, source="telegram")
    history = await get_history()

    sys_prompt = build_system_prompt(history[:-1], user_text)
    response = await ai.process_message(user_text, sys_prompt, execute_tool)

    await add_to_history("model", response, source="telegram")
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

        await add_to_history("user", text, source="telegram")
        history = await get_history()
        
        sys_prompt = build_system_prompt(history[:-1], text)
        response = await ai.process_message(text, sys_prompt, execute_tool)
        
        await add_to_history("model", response, source="telegram")
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
        await add_to_history("user", f"[Rasm] {caption}", source="telegram")
        history = await get_history()

        sys_prompt = build_system_prompt(history[:-1], caption)
        response = await ai.process_message(caption, sys_prompt, execute_tool, images=[("image/jpeg", image_data)])

        await add_to_history("model", response, source="telegram")
        await _send_reply(update, response)
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass


async def _send_reply(update: Update, text: str) -> None:
    safe_text = text.replace("**", "*")
    try: await update.message.reply_text(safe_text, parse_mode="Markdown")
    except Exception:
        try: await update.message.reply_text(safe_text)
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
        mem = format_memory_for_prompt(load_memory())
        if not mem: return
        await query.edit_message_text(f"🧠 *Joriy Xotira:*\n\n{mem}", parse_mode="Markdown")
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
    global userbot, GLOBAL_JOB_QUEUE, GLOBAL_BOT
    GLOBAL_JOB_QUEUE = application.job_queue
    GLOBAL_BOT = application.bot

    # ── PostgreSQL DB jadvallarini yaratish ──
    try:
        from database import init_db
        await init_db()
        logger.info("✅ PostgreSQL tayyor")
    except Exception as e:
        logger.error(f"❌ DB init muvaffaqiyatsiz: {e}")


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
                    if owner: await application.bot.send_message(owner, text.replace("**", "*"), parse_mode="Markdown")
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
        try: await userbot.send_message("@abdullayev_ii", "📭 Yordamchi Tahlili: Bugun o'qilmagan xabarlar yo'q.")
        except: pass
        return

    prompt = "Quyida foydalanuvchining bugungi barcha muhim chatlaridan yig'ilgan xabarlar ro'yxati berilgan. Har bir xabar oldida uning sanasi [YIL-OY-KUN SOAT:MINUT] formatida ko'rsatilgan. Bularni o'qib eng muhimlarini (priority boyicha) asosiy planga chiqar. DIQQAT: Xabarlar sanasiga qara! Eski xabarlarda 'ertaga' deyilgan bo'lsa u kun o'tib ketgan bo'lishi mumkin. Eng oxirida o'zbekcha chiroyli hisobot qilib (Digest) ber:\n\n" + text_data
    
    try:
        sys_prompt = build_system_prompt([])
        response = await ai.process_message("Menga bugungi chatlar tahlilini ber!\n\n" + prompt, sys_prompt, execute_tool)
        report = f"📊 **Kunlik Kechki Telegram Tahlili (20:00)**\n\n{response}"
        # @abdullayev_ii ga yuborish
        await userbot.send_message("@abdullayev_ii", report)
    except Exception as e:
        logger.error(f"Digest yuborishda xato: {e}")

async def morning_briefing_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("☀️ Ertalabki brifing + reja...")
    import database
    import datetime
    today = datetime.datetime.now(pytz.timezone("Asia/Tashkent")).date().strftime("%Y-%m-%d")

    tasks = await database.db_get_plan(today)
    if tasks:
        task_lines = []
        for i, t in enumerate(tasks, 1):
            check = "✅" if t.get("done") else f"{i}."
            pri = " 🔴" if t.get("priority") == "high" else ""
            task_lines.append(f"{check} {t['text']}{pri}")
        plan_text = "\n".join(task_lines)
    else:
        plan_text = "Kecha reja kiritilmagan edi"

    deadline_text = await database.db_get_deadline_summary()

    prompt = (
        f"Ertalab (08:00). Bugun {today}.\n\n"
        f"BUGUNGI REJA:\n{plan_text}\n\n"
        f"DEADLINELAR:\n{deadline_text}\n\n"
        "Sen unga ertalabki brifingni shafqatsiz dictator ruhida yetkaz.\n"
        "1. Bugungi rejani bajarmasa oqibati yomon bo'lishini eslat.\n"
        "2. Eng muhim 1-2 deadlineni ta'kidlab, vaqt kam qolganini yuziga sol.\n"
        "Faqat qattiq, tahdidli, sovuqqon ultimatum.\n"
        "Javob qisqa bo'lsin (4-5 jumla)."
    )

    try:
        sys_prompt = DICTATOR_PROMPT
        response = await ai.process_message(prompt, sys_prompt, execute_tool)
        for ch in ("*", "_", "`", "#"):
            response = response.replace(ch, "")

        report = f"☀️ Tonggi Ultimatum — {today}\n\n"
        if tasks:
            report += f"Bugungi reja:\n{plan_text}\n\n"
        if deadline_text != "Yaqin 2 hafta ichida deadline yo'q":
            report += f"Deadlinelar:\n{deadline_text}\n\n"
        report += f"💬 {response}"

        if GLOBAL_BOT and OWNER_ID:
            await GLOBAL_BOT.send_message(OWNER_ID, report)
        elif userbot:
            await userbot.send_message("@abdullayev_ii", report)
    except Exception as e:
        logger.error(f"Morning briefing xatosi: {e}")

async def viral_news_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("⏱ Viral yangiliklar (Internet) izlash boshlandi...")
    try:
        from duckduckgo_search import DDGS
        import asyncio
        def fetch_news():
            with DDGS() as ddgs:
                try:
                    return list(ddgs.news("tech OR trending OR AI OR world", max_results=30))
                except:
                    return []
        
        news_data = await asyncio.to_thread(fetch_news)
        if not news_data:
            return
            
        prompt = "Sen internetdagi quyidagi yangiliklar ro'yxatini olding. Iltimos, ularni tahlil qilib, asosan eng qiziqarli, dunyoni larzaga keltiradigan yoki VIRAL (mashhur) bo'lishi aniq bo'lgan TOP 5 tasini saralab ol. Va ularni emoji va qiziqarli izohlar bilan 'Xo'jayin' degan tilda o'zbekcha yozib ber:\n\n" + str(news_data)
        
        sys_prompt = build_system_prompt([])
        response = await ai.process_message(prompt, sys_prompt, execute_tool)
        report = f"🔥 **TOP 5 Viral Yangiliklar!**\n\n{response}"
        
        if userbot:
            await userbot.send_message("@abdullayev_ii", report)
    except Exception as e:
        logger.error(f"Viral news yuborishda xato: {e}")

async def send_brief_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Ma'lumotlar yig'ilmoqda (Brifing)... Kuting.")
    await morning_briefing_job(context)
    
async def send_news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Viral yangiliklar tahlil qilinmoqda (Internet)... Kuting.")
    await viral_news_job(context)

async def instagram_ideas_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("⏱ Instagram Niche Ideas jarayoni boshlandi...")
    try:
        data = await cloud.insta_get_niche_trends("biznes", limit=3)
        
        if "❌" in data:
            # Xatolikni to'g'ridan-to'g'ri userga yetkazamiz (o'ylab topmasligi uchun)
            report = f"⚠️ **Instagram bilan muammo:**\n\n{data}\n\n**Izoh:** Bepul proxylar ishlamadi yoki IP bloklangan. Jonli videolarni olish uchun Pullik Proxy ulanishi shart."
            try:
                if context.job and context.job.chat_id:
                    await context.bot.send_message(context.job.chat_id, report.replace("**", "*"), parse_mode="Markdown")
                elif userbot:
                    await userbot.send_message("@abdullayev_ii", report)
            except:
                if context.job and context.job.chat_id:
                    await context.bot.send_message(context.job.chat_id, report)
            return

        prompt = (
            "Sen Instagramdan '#biznes' heshtegi bo'yicha so'nggi eng zo'r viral postlarni olding.\n"
            "VAZIFANG:\n"
            "1. Har bir viral post uchun `insta_download_media` toolini chaqirib, videoning o'zini Isroiljon uchun yuklab ber.\n"
            "2. Har bir video uchun virallik sababini tushuntir va shu asosida 1 tadan tayyor KONTENT PLAN (ssenariy) tuzib ber.\n"
            "Isroiljon kutib o'tirmasligi kerak, videolarni darhol yuklab yubor!\n\n"
            f"{data}"
        )
        
        sys_prompt = build_system_prompt([])
        response = await ai.process_message(prompt, sys_prompt, execute_tool)
        report = f"📱 **Instagram G'oyalar (Nisha: #biznes)**\n\n{response}"
        
        try:
            if context.job and context.job.chat_id:
                await context.bot.send_message(context.job.chat_id, report.replace("**", "*"), parse_mode="Markdown")
            elif userbot:
                await userbot.send_message("@abdullayev_ii", report)
        except Exception as e:
            logger.error(f"Markdown parse xatosi: {e}")
            if context.job and context.job.chat_id:
                await context.bot.send_message(context.job.chat_id, report.replace("**", "*"))
    except Exception as e:
        logger.error(f"Instagram ideas yuborishda xato: {e}")
        try:
            if context.job and context.job.chat_id:
                await context.bot.send_message(context.job.chat_id, f"Kechirasiz, xatolik yuz berdi: {e}")
        except:
            pass

async def send_insta_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Instagram g'oyalari qidirilmoqda... Bu biroz vaqt olishi mumkin, kuting.")
    context.job = context.job_queue.run_once(instagram_ideas_job, 1, chat_id=update.message.chat_id)

async def gmail_draft_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("⏱ Gmail tekshiruvi (Auto-Draft) boshlandi...")
    try:
        data = await cloud.gmail_read_unread(limit=5)
        if "Yangi (o'qilmagan) xatlar yo'q" in data or "❌" in data:
            return
            
        prompt = "Pochtada (Gmail) yangi xatlar bor. Ularni o'qib chiq, va eng muhimlarini asosiy planga olib chiqib, Isroiljon nomidan har biriga qisqacha, professional 'Avto-javob' varianti qoralama (Draft) shaklida taklif qil:\n\n" + data
        sys_prompt = build_system_prompt([])
        response = await ai.process_message(prompt, sys_prompt, execute_tool)
        
        report = f"📧 **Pochta Hisoboti (Gmail)**\n\n{response}"
        if userbot:
            await userbot.send_message("@abdullayev_ii", report)
    except Exception as e:
        logger.error(f"Gmail job xatosi: {e}")

async def life_coach_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    global PLAN_COLLECTION_MODE
    logger.info("⏱ Life Coach jarayoni boshlandi...")
    from api import BOT_CONTEXT as _ctx
    import database
    import datetime

    today = datetime.datetime.now(pytz.timezone("Asia/Tashkent")).date().strftime("%Y-%m-%d")

    health = _ctx.get("last_health")
    h_block = health["summary"] if health else "iOS Health ma'lumoti kelmadi"

    st = _ctx.get("last_screentime")
    if st:
        th = int(st.get("total_minutes", 0)) // 60
        tm = int(st.get("total_minutes", 0)) % 60
        top = ", ".join([f"{a['name']} ({int(a['minutes'])} daq)" for a in (st.get("top_apps") or [])[:3]])
        pk = f", {st['pickups']} marta ko'tarilgan" if st.get("pickups") else ""
        st_block = f"jami {th}s {tm}d{pk}, eng ko'p: {top}"
    else:
        st_block = "Screen Time kelmadi"

    try:
        fin = await database.db_get_finance_data()
        uzs = fin.get("uzs", {})
        f_block = f"Kirim {int(uzs.get('income',0)):,} | Xarajat {int(uzs.get('expense',0)):,} | Qoldiq {int(uzs.get('balance',0)):,} so'm"
    except Exception:
        f_block = "Moliya ma'lumoti yo'q"

    plan_summary = await database.db_get_plan_summary(today)
    if plan_summary["total"] > 0:
        plan_block = f"Bugungi reja: {plan_summary['done']}/{plan_summary['total']} bajarildi ({plan_summary['completion_pct']}%)"
        undone = [t["text"] for t in plan_summary["tasks"] if not t.get("done")]
        if undone:
            plan_block += f". Bajarilmadi: {', '.join(undone[:3])}"
    else:
        plan_block = "Bugun uchun reja kiritilmagan edi"

    deadline_summary = await database.db_get_deadline_summary()

    prompt = (
        f"Soat 21:30. Bugun {today}.\n\n"
        f"SOGLIQ: {h_block}\n"
        f"TELEFON: {st_block}\n"
        f"MOLIYA: {f_block}\n"
        f"BUGUNGI REJA: {plan_block}\n"
        f"DEADLINELAR: {deadline_summary}\n\n"
        "Vazifang:\n"
        "1. Uning bugungi natijalariga shafqatsiz sovuq baho ber (1-2 jumla).\n"
        "2. Nega bunchalik bo'shashib ketganini yuziga sol, dangasaligini haqorat qil (muloyimlashma!).\n"
        "3. Ertaga bajarishi shart bo'lgan 3 ta ultimatum buyrug'ini ber.\n"
        "Javob qisqa, qat'iy va shafqatsiz bo'lsin. Oxirida 'Ertangi rejangizni hoziroq yozing.' de."
    )

    try:
        sys_prompt = DICTATOR_PROMPT
        response = await ai.process_message(prompt, sys_prompt, execute_tool)
        for ch in ("*", "_", "`", "#"):
            response = response.replace(ch, "")

        report = f"🚨 Tahlil va Buyruq — {today}\n\n{response}"

        sent = False
        if GLOBAL_BOT and OWNER_ID:
            await GLOBAL_BOT.send_message(OWNER_ID, report)
            sent = True
        elif userbot:
            await userbot.send_message("@abdullayev_ii", report)
            sent = True

        if sent:
            PLAN_COLLECTION_MODE = True

    except Exception as e:
        logger.error(f"Life Coach xatosi: {e}")


async def midday_check_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("🕛 Yarim kun tekshiruvi...")
    import database
    import datetime
    today = datetime.datetime.now(pytz.timezone("Asia/Tashkent")).date().strftime("%Y-%m-%d")
    plan  = await database.db_get_plan_summary(today)

    if plan["total"] == 0:
        return

    pct  = plan["completion_pct"]
    done = plan["done"]
    total = plan["total"]
    undone = [t["text"] for t in plan["tasks"] if not t.get("done")]

    if pct >= 70:
        tone = "Bu normal holat, lekin maqtashga arzimaydi. Oxirigacha yetkaz."
    elif pct >= 40:
        tone = "Vaqt o'tyapti. Tezlashing, dangasalik qilmang!"
    else:
        tone = "Ahvolingiz achinarli. Kun yarmidan o'tdi, sizda esa nol natija. O'rningizdan turib ishlashni boshlang!"

    remaining = "\n".join([f"• {t}" for t in undone[:5]])
    prompt = (
        f"Kun yarmi (12:00). Bugungi reja bajarilishi: {pct}%. ({done}/{total} bajarildi).\n"
        f"Qolgan vazifalar:\n{remaining}\n\n"
        f"Mening bahoyim: {tone}\n\n"
        "Sen shuni unga yetkaz. O'ta qattiqqo'l, sovuqqon va tahdidli ruhda uning ish samaradorligi haqida gapir. 3-4 jumlada shafqatsiz xulosa qil."
    )

    try:
        sys_prompt = DICTATOR_PROMPT
        response = await ai.process_message(prompt, sys_prompt, execute_tool)
        for ch in ("*", "_", "`", "#"):
            response = response.replace(ch, "")

        report = f"🕛 Nazorat: {pct}% bajarildi\n\n{response}"

        if GLOBAL_BOT and OWNER_ID:
            await GLOBAL_BOT.send_message(OWNER_ID, report)
        elif userbot:
            await userbot.send_message("@abdullayev_ii", report)
    except Exception as e:
        logger.error(f"Midday check xatosi: {e}")

async def send_coach_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Tahlil qilinmoqda...")
    await life_coach_job(context)

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global PLAN_COLLECTION_MODE
    import database
    import datetime
    args = context.args
    today = datetime.datetime.now(pytz.timezone("Asia/Tashkent")).date().strftime("%Y-%m-%d")
    tomorrow = (datetime.datetime.now(pytz.timezone("Asia/Tashkent")).date() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    if not args:
        tasks = await database.db_get_plan(today)
        if not tasks:
            await update.message.reply_text("Reja yo'q.\nRejangizni yuboring, tugatganda /done yozing.")
            PLAN_COLLECTION_MODE = True
            return
        lines = []
        for i, t in enumerate(tasks, 1):
            check = "✅" if t.get("done") else f"{i}."
            pri = " 🔴" if t.get("priority") == "high" else ""
            lines.append(f"{check} {t['text']}{pri}")
        summary = await database.db_get_plan_summary(today)
        await update.message.reply_text(f"📋 Bugungi Reja ({summary['done']}/{summary['total']} bitdi)\n\n" + "\n".join(lines))
    elif args[0].lower() in ("ertaga", "tomorrow"):
        tasks = await database.db_get_plan(tomorrow)
        if not tasks:
            await update.message.reply_text("Ertangi reja hali kiritilmagan.")
        else:
            lines = [f"{i}. {t['text']}" for i, t in enumerate(tasks, 1)]
            await update.message.reply_text(f"📋 Ertangi Reja\n\n" + "\n".join(lines))

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global PLAN_COLLECTION_MODE
    import database
    import datetime
    today = datetime.datetime.now(pytz.timezone("Asia/Tashkent")).date().strftime("%Y-%m-%d")
    if PLAN_COLLECTION_MODE:
        PLAN_COLLECTION_MODE = False
        await update.message.reply_text("Reja qabul qilindi.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Qaysi vazifa? Masalan: /done 2")
        return
    try:
        idx = int(args[0]) - 1
        ok  = await database.db_update_task_status(today, idx, True)
        if ok:
            summary = await database.db_get_plan_summary(today)
            await update.message.reply_text(f"✅ Bajarildi! {summary['done']}/{summary['total']} ({summary['completion_pct']}%)")
        else:
            await update.message.reply_text("Bunday raqamli vazifa topilmadi.")
    except ValueError:
        await update.message.reply_text("Raqam kiriting. Masalan: /done 1")

async def cmd_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import database
    import datetime
    args = context.args
    if not args:
        deadlines = await database.db_get_deadlines(days_ahead=60)
        if not deadlines:
            await update.message.reply_text("Deadline yo'q.\n/deadline 2026-05-01 Loyiha")
            return
        lines = []
        for d in deadlines:
            days = d["days_left"]
            when = f"⚠️ {abs(days)}k kechikdi" if days < 0 else "🚨 BUGUN" if days == 0 else f"{days}k"
            lines.append(f"#{d['id']} {d['title']} — {d['deadline_date']} ({when})")
        await update.message.reply_text(f"📌 Deadlinelar:\n\n" + "\n".join(lines) + "\n\nBajarildi: /deadline done [ID]")
        return
    if args[0].lower() == "done" and len(args) >= 2:
        try:
            ok = await database.db_complete_deadline(int(args[1]))
            await update.message.reply_text("✅ Yakunlandi!" if ok else "Topilmadi.")
        except ValueError:
            pass
        return
    if len(args) >= 2:
        date_str = args[0]
        title = " ".join(args[1:])
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except:
            await update.message.reply_text("Xato sana formati.")
            return
        did = await database.db_add_deadline(title, date_str)
        if did > 0: await update.message.reply_text(f"📌 Qo'shildi! #{did}")

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("brief", send_brief_cmd))
    app.add_handler(CommandHandler("news", send_news_cmd))
    app.add_handler(CommandHandler("insta", send_insta_cmd))
    app.add_handler(CommandHandler("coach", send_coach_cmd))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("deadline", cmd_deadline))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))

    tz = pytz.timezone("Asia/Tashkent")
    import datetime
    app.job_queue.run_daily(morning_briefing_job,  time=datetime.time(hour=8,  minute=0,  tzinfo=tz))
    app.job_queue.run_daily(viral_news_job,        time=datetime.time(hour=8,  minute=5,  tzinfo=tz))
    app.job_queue.run_daily(gmail_draft_job,       time=datetime.time(hour=9,  minute=0,  tzinfo=tz))
    app.job_queue.run_daily(instagram_ideas_job,   time=datetime.time(hour=10, minute=0,  tzinfo=tz))
    app.job_queue.run_daily(midday_check_job,      time=datetime.time(hour=12, minute=0,  tzinfo=tz))
    app.job_queue.run_daily(daily_digest_job,      time=datetime.time(hour=20, minute=0,  tzinfo=tz))
    app.job_queue.run_daily(life_coach_job,        time=datetime.time(hour=21, minute=30, tzinfo=tz))

    logger.info("✅ J.A.R.V.I.S tayyor! Polling boshlandi.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

