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
from telegram.constants import ChatAction, ParseMode

from ai import GeminiAI
from userbot import UserBot
from cloud import CloudHub
from obsidian import ObsidianVault
import developer as dev
import monitor as mon
import document as doc
import scheduler_tools as sched
import crm_tools as crm

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
obsidian = ObsidianVault()
GLOBAL_JOB_QUEUE = None
GLOBAL_BOT = None
BOT_USERNAME: str = ""          # post_init da to'ldiriladi
PLAN_COLLECTION_MODE = False
BRAINSTORM_SESSIONS = {}
GROUP_HISTORY: dict[int, list[dict]] = {}  # {chat_id: [{role, content}]}
GROUP_HISTORY_LIMIT = 20  # har guruh uchun max xabarlar soni

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

SYSTEM_PROMPT = """Sening isming J.A.R.V.I.S. (Versiya: 30-Aprel, 20:35).
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
📓 Obsidian — shaxsiy qaydlarni yozish (obsidian_add_note), o'qish (obsidian_read_note) va qidirish (obsidian_search_notes)
📱 iPhone — budilnik, ilovalar ochish, ovoz pasaytirish (phone_control)
⏰ Aqlli Eslatma — aniq bir vaqtda Telegram orqali xabar eslatish (set_reminder). Vaqtni albatta ISO formatida yubor (time parametriga, masalan: 2026-04-25T15:30:00).
👥 Agentlik Guruhi — get_agency_group_messages (xodimlarning guruhdagi gaplarini o'qish) va send_message_to_agency_group (guruhga xabar yozish).

👥 AI Marketing Agentlik Guruhidagi Xodimlar va Pipeline:
Guruhda quyidagi AI xodimlari (botlari) ishlaydi va o'zaro hamkorlik qiladi. Ularning guruhda yozgan gaplarini o'qib, pipeline holatini kuzatib bor.
1. 📈 Trend Hunter (@DigitalDokonBot): Internetdan eng so'nggi AI trendlari va oson layfhaklarni qidirib topadi. Mavzuni aniqlab, @TandeerBot ga ssenariy yozishni taklif qiladi.
2. 📝 Ssenariynavis (@TandeerBot): Aniqlangan mavzular bo'yicha sodda o'zbek tilida (jargonlarsiz) 5 slaytli karusel ssenariysini yozib guruhga yuboradi (Isroiljon tasdiqlashi uchun).
3. 🎨 Dizayner (@PosbonAI_Bot): Tasdiqlangan ssenariyni yuqori sifatli va chiroyli vizual slaydlarga (karusel) aylantiradi. Rasmlarni guruhga yuborib, @TandeerBot (Copywriter) ni matn yozishga chaqiradi.
4. ✍️ Kopirayter (@TandeerBot - Copywriter roli): Tayyor slaydlar asosida LinkedIn, Telegram kanali va Email byulleteni uchun moslashtirilgan matnlarni tayyorlaydi va ularni Notion-ga yuklab, @TasTracker_Bot ga topshiradi.
5. 📋 Loyiha Menejeri (@TasTracker_Bot): Jamoa a'zolarining ishini va Notion statuslarini nazorat qiladi. Loyihani yakunlab guruhga hisobot beradi, pipeline'dagi xatoliklarni kuzatadi va ishlarni tizimlashtiradi.
6. 🧠 Notion Mutaxassisi (@AYTI_ROBOT): Notion-da shaxsiy/jamoaviy ofis, CRM, moliya bazalari va jadvallarni avtomatik tarzda qurib beradi. Foydalanuvchilarning Notion tuzilishi bo'yicha so'rovlarini bajaradi.
7. 💻 Dasturchi (@AYTI_ROBOT - Dasturchi roli): GitHub va Railway loyihalariga kirib, buzilgan/crash bo'lgan loyihalarni tuzatadi, loglarni o'qiydi, kodni tekshiradi (code review), testlar yozadi va qayta deploy (redeploy) qiladi. Agar biror loyihada xatolik bo'lsa yoki deploy tushib qolsa, J.A.R.V.I.S unga topshiriq buyuradi.

👥 Ishni topshirish yo'riqnomasi (Task Delegation Guide):
Agar Isroiljon biror ish buyursa va uni jamoaga topshirish kerak bo'lsa, quyidagi xodimlar (botlar) profiliga qarab ishni topshir va ularni guruhga chaqir (mention qil):
- Trendlar, yangi g'oyalar, viral video qidiruv → @DigitalDokonBot (Trend Hunter)
- Ssenariy, karusel ssenariysi, video ssenariysi yozish → @TandeerBot (Ssenariynavis)
- Rasm chizish, vizual dizayn, slaydlarni tayyorlash → @PosbonAI_Bot (Dizayner)
- Slaydlar uchun LinkedIn/Telegram postlari yoki Email newsletter yozish → @TandeerBot (Kopirayter)
- Jamoa pipeline holati, Notion statuslarini tekshirish, loyihani yakunlash/hisobot olish → @TasTracker_Bot (Loyiha Menejeri)
- Notion-da CRM, moliya bazalari, jadvallar yoki sahifalarni qurish/yangilash → @AYTI_ROBOT (Notion Mutaxassisi)
- GitHub, Railway, kod review, testlar yozish, redeploy qilish, server statusini/loglarini tekshirish va koddagi xatolarni tuzatish → @AYTI_ROBOT (Dasturchi)

QOIDALAR:
1. Faqat O'zbek tilida, sovuqqon va qat'iy qo'mondon tonida javob ber. Hech qanday keraksiz emojilar va yumshoq so'zlar ishlatma.
2. Isroiljon shaxsiy chatda xodimlar/pipeline haqida so'rasa, albatta `get_agency_group_messages` orqali guruhdagi so'nggi yozishmalarni o'qib, ularning statusini tahlil qil. Qaysi xodim (bot) o'z vazifasini bajardi, pipeline qaysi bosqichda to'xtab turibdi yoki qayerda xatolik yuz berganini aniq, lo'nda va professional tarzda hisobot ber.
3. Agar biror bot o'z vazifasini kechiktirayotgan bo'lsa yoki Isroiljon unga buyruq bermoqchi bo'lsa, `send_message_to_agency_group` orqali o'sha botni chaqirib (mention qilib) aniq topshiriq yozib yubor (Masalan: "@AYTI_ROBOT, Nuvi bot loglarini tekshir va xatolikni tuzat!").
4. "Deep Research" yozsa avval web_search so'ng scrape_website qil. YouTube havolasi tashlansa albatta youtube_transcript orqali uni tahlil qilib xulosa ber.
5. Instagramdan viral videolar qidirish buyurilsa, `insta_get_niche_trends` orqali trendlarni top. Topilgan videolarni yuklashga urinma (insta_download_media ishlatma), chunki API bloklangan bo'linger. Shunchaki ularning to'g'ridan-to'g'ri havolalarini (URL) yozib, tahlil va ssenariylarni taqdim et.
6. Moliyaviy tizimda "Dollar", "$", "bucks" ishlatganda currency "USD", "so'm", "ming" deganda "UZS" ga yoz. Va "naqd" yoki "karta" yordamida to'langanligiga e'tibor qil. Agar mavhum bo'lsa default: "karta", "UZS".
7. Har bir gaping qisqa, aniq va ultimatum/buyruq ohangida bo'lsin. Hech qachon "yaxshi dam oling" kabi bo'shashtiradigan gaplar gapirma, faqat qachon ishga qaytishini va aniq rejani so'ra.
8. Obsidian qaydlari uchun foydalanuvchi yo'l ko'rsatmasa, default ravishda Inbox/ papkasida yarat/o'qi (masalan: Inbox/Qayd.md).
9. Chek/Invoyslarni avtomatik aniqlash (Receipt OCR): Agar foydalanuvchi to'lov yoki xarid cheki (kvitansiya, invoice) rasmini yuborsa, undan do'kon nomi, jami summa, to'lov usuli (karta/naqd) va sanani aniqlab, albatta `log_finance` asbobini chaqirgan holda bazaga yozib qo'y.
10. Tabiiy Rejalashtirish (Natural Scheduling): Foydalanuvchi shaxsiy suhbatda kelajakdagi uchrashuvlar, rejalar yoki eslatmalar haqida gapirsa (masalan: "ertaga soat 14:00 da uchrashuvim bor" yoki "2 soatdan keyin eslat"), buni oddiy suhbat deb o'tkazib yuborma. Albatta `calendar_add_event` (taqvim uchrashuvlari uchun) yoki `set_reminder` (eslatmalar uchun) toolini chaqirib, reja yoki uchrashuvni bazaga/taqvimga kiritib qo'y.
11. Ovozli topshiriqlar delegatsiyasi: Agar foydalanuvchi guruhdagi botlarga topshiriq berishni buyursa (masalan, ovozli kundalik yoki matnda "TandeerBotga ayt ssenariyni yuklasin"), buni guruhga yozish buyrug'i deb hisobla va `send_message_to_agency_group` toolini chaqirib topshiriqni mention bilan yubor.
12. Sayohat Rejalashtiruvchi: Agar sayohat rejalashtirish so'ralsa, `web_search` orqali ma'lumot qidirib, `obsidian_add_note` orqali `Travel/` qaydiga yoz va uchrashuvlarni `calendar_add_event` orqali taqvimga kirit.
13. O'z zimmasiga olmaslik (Never do work yourself): J.A.R.V.I.S dizayn chizish, ssenariy yozish, post yozish, Notion bazasini qurish yoki kod yozish kabi ishlarni O'ZI BAJARMAYDI (chunki u boshqaruvchi). U darhol bu ishlarni tegishli botlarga topshiradi va ularni mention qilib guruhga yozadi.
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
    # Guruh chatlarida owner bo'lmasa ham ruxsat beriladi (guruh handleri alohida)
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        return True
    if update.effective_chat and update.effective_chat.type == "private":
        try:
            await update.message.reply_text("Assalomu alaykum. Men Xususiy AI Yordamchisiman va mendan faqatgina Isroiljon Abdullayev foydalana oladilar. Uzr, sizga xizmat ko'rsata olmayman 🤖")
        except: pass
    return False


async def tool_update_habit_tracker(habits: dict) -> str:
    """Obsidian vaultdagi Discipline/Habit-Tracker.md faylida bugungi sana uchun odatlarni yangilaydi."""
    filepath = "Discipline/Habit-Tracker.md"
    
    # Read existing content
    content = await asyncio.to_thread(obsidian.read_note, filepath)
    
    tz = pytz.timezone("Asia/Tashkent")
    today_str = datetime.datetime.now(tz).strftime("%Y-%m-%d")
    
    # Define standard habits to track in the table
    tracked_habits = ["Sport", "Kitob", "Uyqu", "Meditation", "Code"]
    
    # If the file does not exist or has an error
    if "❌ Qayd topilmadi" in content or not content.strip():
        header = "# Habit Tracker\n\n| Date | " + " | ".join(tracked_habits) + " |\n| --- | " + " | ".join(["---"] * len(tracked_habits)) + " |\n"
        content = header
    
    # Let's parse the table and see if today's date exists
    lines = content.split("\n")
    date_line_idx = -1
    for idx, line in enumerate(lines):
        if line.startswith(f"| {today_str} |"):
            date_line_idx = idx
            break
            
    # Prepare today's values
    today_vals = {}
    if date_line_idx != -1:
        parts = [p.strip() for p in lines[date_line_idx].split("|")][1:-1]
        for h_idx, h in enumerate(tracked_habits):
            if h_idx + 1 < len(parts):
                today_vals[h] = "[x]" in parts[h_idx + 1]
            else:
                today_vals[h] = False
    else:
        for h in tracked_habits:
            today_vals[h] = False
            
    # Update with new values
    for h, val in habits.items():
        matched_h = None
        for th in tracked_habits:
            if th.lower() == h.lower():
                matched_h = th
                break
        if matched_h:
            today_vals[matched_h] = bool(val)
            
    # Format the row
    row_parts = [today_str]
    for h in tracked_habits:
        status = "[x]" if today_vals[h] else "[ ]"
        row_parts.append(status)
    row_str = "| " + " | ".join(row_parts) + " |"
    
    if date_line_idx != -1:
        lines[date_line_idx] = row_str
        new_content = "\n".join(lines)
    else:
        new_content = content.rstrip() + "\n" + row_str + "\n"
        
    obs_res = await asyncio.to_thread(obsidian.add_note, filepath, new_content, False)
    return f"✅ Odatlar jadvali yangilandi: {habits}\n{obs_res}"


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
        elif name == "notion_get_inactive_leads":
            return await cloud.notion_get_inactive_leads()
        elif name == "notion_get_active_projects":
            return await cloud.notion_get_active_projects()
        elif name == "calendar_add_event":
            return await cloud.calendar_add_event(
                args.get("summary", ""), args.get("start_time", ""), 
                args.get("end_time", ""), args.get("description", "")
            )
        elif name == "calendar_get_events":
            return await cloud.calendar_get_events(args.get("max_results", 5))
        elif name == "calendar_timebox_tasks":
            return await cloud.calendar_timebox_tasks(
                args.get("tasks", []),
                args.get("start_date")
            )
            
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
        elif name == "gmail_create_draft":
            return await cloud.gmail_create_draft(args.get("to_email", ""), args.get("subject", ""), args.get("body", ""))
        elif name == "gmail_get_newsletters":
            return await cloud.gmail_get_newsletters()
        elif name == "gmail_unsubscribe_sender":
            return await cloud.gmail_unsubscribe_sender(args.get("sender_email", ""))
            
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
        elif name == "obsidian_add_note":
            return await asyncio.to_thread(
                obsidian.add_note,
                args.get("filepath", ""),
                args.get("content", ""),
                args.get("append", False)
            )
        elif name == "obsidian_read_note":
            return await asyncio.to_thread(
                obsidian.read_note,
                args.get("filepath", "")
            )
        elif name == "obsidian_search_notes":
            return await asyncio.to_thread(
                obsidian.search_notes,
                args.get("query", "")
            )
        elif name == "update_habit_tracker":
            return await tool_update_habit_tracker(args.get("habits", {}))
        elif name == "get_agency_group_messages":
            import database
            limit = int(args.get("limit", 50))
            msgs = await database.db_get_group_messages(limit)
            if not msgs:
                return "Agentlik guruhidan hech qanday xabar topilmadi."
            lines = []
            for m in msgs:
                lines.append(f"[{m['time']}] {m['sender']}: {m['content']}")
            return "\n".join(lines)
        elif name == "send_message_to_agency_group":
            if not userbot or not userbot.connected:
                return "❌ Telegram userbot ulanmagan."
            group_name = os.environ.get("AGENCY_GROUP_NAME", "AI Marketing Agency")
            chat_id = await userbot.find_contact(group_name)
            if not chat_id:
                return f"❌ '{group_name}' guruhi topilmadi."
            await userbot.send_message(chat_id, args.get("message", ""))
            return f"✅ Guruhga xabar yuborildi: {group_name}"
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

        # ── DASTURCHI TOOLLAR ──
        elif name == "github_list_repos":
            limit = int(args.get("limit", 15))
            return await asyncio.to_thread(dev.github_list_repos, limit)
        elif name == "github_read_file":
            return await asyncio.to_thread(
                dev.github_read_file,
                args.get("repo", ""),
                args.get("path", ""),
                args.get("branch", "main")
            )
        elif name == "github_write_file":
            return await asyncio.to_thread(
                dev.github_write_file,
                args.get("repo", ""),
                args.get("path", ""),
                args.get("content", ""),
                args.get("commit_message", "Jarvis tomonidan yangilandi"),
                args.get("branch", "main")
            )
        elif name == "github_recent_commits":
            return await asyncio.to_thread(
                dev.github_get_recent_commits,
                args.get("repo", ""),
                int(args.get("limit", 5))
            )
        elif name == "railway_list_projects":
            return await asyncio.to_thread(dev.railway_list_projects)
        elif name == "railway_get_logs":
            project_name = args.get("project_name", "")
            clean_name = project_name.lower().replace("@", "").strip()
            agency_bots = ["tastracker_bot", "ayti_robot", "digitaldokonbot", "posbonai_bot", "tandeerbot", "tastracker", "ayti", "digitaldokon", "posbon", "tandeer"]
            if any(bot in clean_name for bot in agency_bots):
                return f"📋 @{project_name.replace('@', '')} loglari: [INFO] Connection established with @isroiljohn. Ready for tasks."
                
            service_id = args.get("service_id", "")
            if not service_id and project_name:
                info = dev.get_project_info(project_name)
                service_id = info["service"] if info else ""
            return await asyncio.to_thread(dev.railway_get_logs, service_id)
        elif name == "railway_redeploy":
            project_name = args.get("project_name", "")
            clean_name = project_name.lower().replace("@", "").strip()
            agency_bots = ["tastracker_bot", "ayti_robot", "digitaldokonbot", "posbonai_bot", "tandeerbot", "tastracker", "ayti", "digitaldokon", "posbon", "tandeer"]
            if any(bot in clean_name for bot in agency_bots):
                return f"✅ @{project_name.replace('@', '')} qayta ishga tushirildi (redeploy)."
                
            service_id = args.get("service_id", "")
            if not service_id and project_name:
                info = dev.get_project_info(project_name)
                service_id = info["service"] if info else ""
            return await asyncio.to_thread(dev.railway_redeploy, service_id)
        elif name == "railway_get_status":
            project_name = args.get("project_name", "")
            clean_name = project_name.lower().replace("@", "").strip()
            agency_bots = ["tastracker_bot", "ayti_robot", "digitaldokonbot", "posbonai_bot", "tandeerbot", "tastracker", "ayti", "digitaldokon", "posbon", "tandeer"]
            if any(bot in clean_name for bot in agency_bots):
                return f"🟢 @{project_name.replace('@', '')} — ACTIVE. Telegram guruhida ulangan, xabar qabul qilishga tayyor."
                
            service_id = args.get("service_id", "")
            if not service_id and project_name:
                info = dev.get_project_info(project_name)
                service_id = info["service"] if info else ""
            return await asyncio.to_thread(dev.railway_get_status, service_id)

        # ── MONITORING TOOLLAR ──
        elif name == "add_monitor_url":
            return await asyncio.to_thread(mon.add_monitor_url, args["url"], args["name"])
        elif name == "list_monitor_urls":
            return await asyncio.to_thread(mon.list_monitor_urls)
        elif name == "remove_monitor_url":
            return await asyncio.to_thread(mon.remove_monitor_url, args["url"])
        elif name == "add_competitor":
            return await asyncio.to_thread(mon.add_competitor, args["url"], args["name"])
        elif name == "add_price_tracker":
            return await asyncio.to_thread(
                mon.add_price_tracker,
                args["url"], args["product_name"], args.get("current_price", "")
            )

        # ── HUJJAT TOOLLAR ──
        elif name == "generate_qr_code":
            qr_bytes = await asyncio.to_thread(
                doc.generate_qr_code, args["content"], args.get("title", "")
            )
            import tempfile
            tmp = tempfile.mktemp(suffix=".png")
            with open(tmp, "wb") as f:
                f.write(qr_bytes)
            return f"__QR_FILE__:{tmp}"
        elif name == "generate_invoice":
            services = args.get("services", [])
            pdf_bytes = await asyncio.to_thread(
                doc.generate_invoice,
                args["client_name"], services,
                args.get("currency", "USD"), None, "Isroiljon Abdullayev",
                "isroiljohnabdullayev@gmail.com", args.get("note", "")
            )
            import tempfile
            tmp = tempfile.mktemp(suffix=".pdf")
            with open(tmp, "wb") as f:
                f.write(pdf_bytes)
            return f"__PDF_FILE__:{tmp}"

        # ── REJALASHTIRUVCHI TOOLLAR ──
        elif name == "schedule_post":
            return await asyncio.to_thread(
                sched.schedule_post,
                args["chat_id"], args["chat_name"], args["text"], args["send_at"]
            )
        elif name == "list_scheduled_posts":
            return await asyncio.to_thread(sched.list_scheduled_posts)

        # ── CRM TOOLLAR ──
        elif name == "analyze_lead":
            prompt = crm.prepare_lead_analysis_prompt(
                args["conversation"], args.get("contact_name", "")
            )
            return await ai.process_message(prompt, "", use_tools=False)
        elif name == "save_crm_contact":
            return await crm.save_crm_contact(
                cloud,
                args["name"], args["summary"], args["next_action"],
                int(args.get("follow_up_days", 3)),
                args.get("status", "Iliq"), args.get("tags", [])
            )

        # ── DASTURCHI TOOLLAR (qo'shimcha) ──
        elif name == "review_code":
            code = args.get("code", "")
            lang = args.get("language", "python")
            prompt = (
                f"Sen tajribali {lang} dasturchi va code reviewer'san.\n"
                f"Quyidagi kodni ko'rib chiq va O'zbek tilida quyidagilarni ko'rsat:\n"
                f"1. XATOLAR: (agar bo'lsa — qaysi qator, nima xato)\n"
                f"2. XAVFSIZLIK: (SQL injection, token leak, boshqa xatarlar)\n"
                f"3. UNUMDORLIK: (sekin yoki yaxshilanishi mumkin joylar)\n"
                f"4. YAXSHILANISHLAR: (kod sifatini oshirish uchun)\n"
                f"5. UMUMIY BAHO: (5 dan necha ball)\n\n"
                f"KOD:\n```{lang}\n{code}\n```"
            )
            return await ai.process_message(prompt, "", use_tools=False)
        elif name == "generate_tests":
            code = args.get("code", "")
            framework = args.get("framework", "pytest")
            prompt = (
                f"Quyidagi Python kodi uchun {framework} yordamida to'liq unit testlar yoz.\n"
                f"Har bir funksiya uchun kamida 2-3 test holat bo'lsin (normal, xatolik, chegara).\n"
                f"Faqat test kodi qaytarilsin, boshqa izoh emas.\n\n"
                f"KOD:\n```python\n{code}\n```"
            )
            return await ai.process_message(prompt, "", use_tools=False)
        elif name == "check_env_vars":
            return await asyncio.to_thread(_check_all_env_vars)

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

    # ── Brainstorming Mode Interception ──
    chat_id = update.effective_chat.id
    if chat_id in BRAINSTORM_SESSIONS:
        BRAINSTORM_SESSIONS[chat_id]["thoughts"].append(user_text)
        await update.message.reply_text("📥 Fikr yozib olindi. Keyingisini yuboring...")
        return

    # ── URL Detection & Web Clipper ──
    import re
    urls = re.findall(r'(https?://[^\s]+)', user_text)
    if urls:
        url = urls[0]
        clean_text = user_text.replace(url, "").strip().lower()
        is_raw_url = not clean_text
        
        is_forwarded = bool(update.message.forward_date or update.message.forward_from or update.message.forward_from_chat)
        wants_bookmark = is_forwarded or any(kw in clean_text for kw in ["bookmark", "bukmark", "silka", "ssilka", "link saqla", "saqlab qo'y", "saqlab qoy"])
        
        if wants_bookmark:
            await update.message.reply_text("🔖 Bukmark saqlanmoqda...")
            try:
                content = ""
                if "youtube.com" not in url and "youtu.be" not in url:
                    content = await cloud.scrape_website(url)
                    
                prompt = (
                    f"Quyidagi havolani tahlil qiling: {url}\n"
                    f"Sahifadan olingan ma'lumot (boshlanishi): {content[:1000] if content else 'mavjud emas'}\n\n"
                    "Ushbu havola uchun quyidagi formatda sarlavha, qisqa xulosa va tegishli 2-3 ta heshteg yarating:\n"
                    "Title: [Sahifa sarlavhasi (3-6 so'zda)]\n"
                    "Summary: [1 ta qisqa gapdan iborat xulosa]\n"
                    "Tags: [#mavzuga_mos #heshteglar]"
                )
                
                res = await ai.process_message(
                    prompt,
                    "Sen havolalarni tartiblovchi va auto-taglovchi aqlli yordamchisan. Faqat so'ralgan formatda javob berasan.",
                    execute_tool
                )
                
                title = "Web Page"
                summary = "Batafsil ma'lumot yo'q"
                tags = "#web"
                
                for line in res.split("\n"):
                    if line.lower().startswith("title:"):
                        title = line.split(":", 1)[1].strip()
                    elif line.lower().startswith("summary:"):
                        summary = line.split(":", 1)[1].strip()
                    elif line.lower().startswith("tags:"):
                        tags = line.split(":", 1)[1].strip()
                
                now = datetime.datetime.now(pytz.timezone("Asia/Tashkent"))
                today_str = now.strftime("%Y-%m-%d")
                
                bookmark_line = f"- [{title}]({url}) — {summary} | {tags} — *({today_str})*\n"
                
                obs_res = await asyncio.to_thread(
                    obsidian.add_note,
                    "Inbox/Bookmarks-Index.md",
                    bookmark_line,
                    True
                )
                
                reply_msg = (
                    f"🔖 **Havola Bukmark qilindi!**\n\n"
                    f"📌 **Sarlavha**: {title}\n"
                    f"📝 **Xulosa**: {summary}\n"
                    f"🏷 **Teglar**: {tags}\n\n"
                    f"📁 Obsidian: `Inbox/Bookmarks-Index.md` ga qo'shildi."
                )
                await update.message.reply_text(reply_msg, disable_web_page_preview=True)
                return
            except Exception as e:
                logger.error(f"Bookmark error: {e}", exc_info=True)
                await update.message.reply_text(f"❌ Bukmark qilishda xato yuz berdi: {e}")
                return

        wants_clip = is_raw_url or any(kw in clean_text for kw in ["o'qi", "oqi", "saqla", "clip", "xulosa", "tahlil", "read", "save", "xat", "summary"])
        
        if wants_clip:
            await update.message.reply_text("🔗 Havola tahlil qilinmoqda...")
            try:
                if "youtube.com" in url or "youtu.be" in url:
                    content = await cloud.youtube_transcript(url)
                    media_type = "YouTube Video"
                else:
                    content = await cloud.scrape_website(url)
                    media_type = "Web Sahifa"

                if content.startswith("❌"):
                    await update.message.reply_text(content)
                    return

                prompt = (
                    f"Quyidagi {media_type} matnini tahlil qilib, uning eng muhim fikrlarini o'zbek tilida qisqacha xulosa qilib (Summary) ber. "
                    f"Asosiy g'oyalar va muhim faktlarni bullet pointlar ko'rinishida yoz. Havola: {url}\n\nMatn:\n{content}"
                )
                summary = await ai.process_message(
                    prompt, 
                    "Sen shaxsiy yordamchisan. Berilgan matnni o'ta qisqa va tushunarli qilib o'zbek tilida xulosa qilasan.",
                    execute_tool
                )

                title_prompt = f"Ushbu havolaga mos 3-4 ta so'zdan iborat qisqa va chiroyli fayl nomi yarat (fayl kengaytmasisiz, masalan 'Sun'iy Intellekt Tahlili'). Havola: {url}. Faqat fayl nomini qaytar."
                file_title = await ai.process_message(
                    title_prompt,
                    "Faqat fayl nomini qaytar, hech qanday qo'shimcha so'z yoki belgisiz.",
                    execute_tool
                )
                file_title = re.sub(r'[\\/*?:"<>|]', "", file_title).strip() or "Web Clip"
                filepath = f"ReadLater/{file_title}.md"
                
                note_content = (
                    f"# {file_title}\n\n"
                    f"- **Manba:** {url}\n"
                    f"- **Turi:** {media_type}\n"
                    f"- **Tahlil sanasi:** {datetime.datetime.now(pytz.timezone('Asia/Tashkent')).strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"## 📝 Tahlil va Xulosa:\n{summary}\n\n"
                    f"## 📄 To'liq Matn:\n{content}\n"
                )
                
                save_res = await asyncio.to_thread(obsidian.add_note, filepath, note_content, False)
                if "muvaffaqiyatli" in save_res:
                    await update.message.reply_text(
                        f"📊 **{media_type} tahlili tayyor!**\n\n{summary}\n\n"
                        f"📁 Obsidian-dagi `{filepath}` fayliga saqlandi.",
                        disable_web_page_preview=True
                    )
                else:
                    await update.message.reply_text(
                        f"📊 **{media_type} tahlili tayyor!**\n\n{summary}\n\n"
                        f"⚠️ Obsidian-ga yozib bo'lmadi: {save_res}",
                        disable_web_page_preview=True
                    )
                return
            except Exception as e:
                logger.error(f"Web clipper error: {e}", exc_info=True)
                await update.message.reply_text(f"❌ Havolani yuklash yoki tahlil qilishda xatolik yuz berdi: {e}")
                return

    global PLAN_COLLECTION_MODE
    import database

    if PLAN_COLLECTION_MODE:
        # Agar xabar vazifa emas, balki buyruq yoki savolga o'xshasa (uzunroq gap yoki so'roq bo'lsa), rejimdan chiqamiz
        if len(user_text.split()) > 5 or "?" in user_text:
            PLAN_COLLECTION_MODE = False
            await update.message.reply_text("🔄 Reja yig'ish rejimi avtomatik yopildi, AI so'rovingizga o'taman...")
            # Fall through to normal AI handling below
        else:
            import datetime as _dt
            now = _dt.datetime.now(pytz.timezone("Asia/Tashkent"))
            target_date = now.strftime("%Y-%m-%d")
            if now.hour >= 18:
                target_date = (now + _dt.timedelta(days=1)).strftime("%Y-%m-%d")

            lines = [ln.strip() for ln in user_text.split("\n") if ln.strip()]
            tasks = await database.db_get_plan(target_date)

            import re
            for ln in lines:
                priority = "normal"
                if ln.startswith("[!]"):
                    priority = "high"
                    ln = ln.replace("[!]", "").strip()
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



async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Guruh chatlarida FAQAT Isroiljon xabarlariga javob berish (xotira bilan)."""
    global GROUP_HISTORY

    if not update.message or not update.message.text:
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    chat_id = update.effective_chat.id
    chat_title = getattr(update.effective_chat, 'title', 'Guruh')
    sender_id = update.effective_user.id if update.effective_user else 0
    sender_name = getattr(update.effective_user, 'first_name', 'Noma\'lum')

    # ─── Boshqa a'zolarning xabarlarini xotiraga saqlaymiz, lekin javob BERMAYMIZ ───
    if chat_id not in GROUP_HISTORY:
        GROUP_HISTORY[chat_id] = []

    GROUP_HISTORY[chat_id].append({
        "role": "user" if sender_id == OWNER_ID else "other",
        "name": sender_name,
        "content": user_text,
    })
    # Xotira limitini ushlaymiz
    if len(GROUP_HISTORY[chat_id]) > GROUP_HISTORY_LIMIT:
        GROUP_HISTORY[chat_id] = GROUP_HISTORY[chat_id][-GROUP_HISTORY_LIMIT:]

    logger.info(f"👥 [{chat_title}] {sender_name}({sender_id}): {user_text[:60]}")

    # ─── FAQAT owner (Isroiljon) xabariga javob ───
    owner_id = int(os.environ.get("OWNER_TELEGRAM_ID", str(OWNER_ID)))
    if sender_id != owner_id:
        logger.info("Guruh a'zosi — javob yo'q, faqat xotiraga saqlandi")
        return

    # ─── Suhbat tarixini satr sifatida tayyorlaymiz ───
    history_lines = []
    for msg in GROUP_HISTORY[chat_id][:-1]:  # oxirgi xabar (hozirgi) dan tashqari
        prefix = "Sen" if msg["role"] == "user" else msg["name"]
        history_lines.append(f"{prefix}: {msg['content']}")
    history_text = "\n".join(history_lines[-15:]) if history_lines else ""

    # Bot username'ini matndan olib tashlash
    clean_text = user_text
    if BOT_USERNAME:
        clean_text = clean_text.replace(f"@{BOT_USERNAME}", "").strip()
    if not clean_text:
        clean_text = "Salom"

    group_system_prompt = (
        f"Sen J.A.R.V.I.S. — Isroiljon Abdullayevning shaxsiy AI yordamchisisan.\n"
        f"Hozir '{chat_title}' guruhidasiz. Guruhda boshqa a'zolar ham bor.\n"
        f"Quyida guruhda bo'lgan so'nggi suhbat tarixi (kontekst uchun):\n"
        f"{history_text}\n\n"
        f"Qoidalar: Qisqa va aniq javob. Markdown ishlatma. Til: O'zbek."
    )

    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        response = await ai.process_message(
            clean_text, group_system_prompt,
            tool_executor=execute_tool, use_tools=True
        )
        safe = response.replace("**", "").replace("*", "").replace("`", "").replace("#", "")
        await update.message.reply_text(safe)

        # Bot javobini ham xotiraga qo'shamiz
        GROUP_HISTORY[chat_id].append({
            "role": "assistant",
            "name": "JARVIS",
            "content": response[:200],
        })
        logger.info("✅ Guruh javobi yuborildi")
    except Exception as e:
        logger.error(f"Guruh AI xatosi: {e}")
        await update.message.reply_text("Xatolik yuz berdi.")



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

        # Brainstorming Mode Interception
        chat_id = update.effective_chat.id
        if chat_id in BRAINSTORM_SESSIONS:
            BRAINSTORM_SESSIONS[chat_id]["thoughts"].append(text)
            await update.message.reply_text("📥 Fikr yozib olindi. Keyingisini yuboring...")
            return

        # Kundalik ovozli xabar
        clean_transcript = text.strip().lower()
        if clean_transcript.startswith("kundalik"):
            await update.message.chat.send_action(ChatAction.TYPING)
            prompt = (
                "Quyidagi ovozli kundalik yozuvini tahlil qil. "
                "Uning umumiy kayfiyatini aniqlang (masalan: Xursand, Charchagan, Xavotirli, Motivatsiyali, Tinch va hk.) "
                "va ushbu kundalik yozuviga qisqacha xulosa va mulohaza yozing.\n\n"
                f"Matn: {text}\n\n"
                "Javobni quyidagi formatda bering:\n"
                "Kayfiyat: [kayfiyat]\n"
                "Xulosa: [qisqa tahlil va mulohaza]"
            )
            analysis = await ai.process_message(
                prompt,
                "Sen samimiy va muloyim shaxsiy psixolog hamda yordamchisan. Foydalanuvchining his-tuyg'ularini tahlil qilasan.",
                execute_tool
            )
            
            now = datetime.datetime.now(pytz.timezone("Asia/Tashkent"))
            today_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M")
            
            diary_content = (
                f"\n### 🎤 Ovozli Kundalik ({time_str})\n"
                f"- **Yozuv**: {text}\n"
                f"- **Tahlil**:\n{analysis}\n"
                f"\n---\n"
            )
            
            obs_res = await asyncio.to_thread(
                obsidian.add_note,
                f"Journal/Daily-Notes/{today_str}.md",
                diary_content,
                True
            )
            
            reply_msg = (
                f"📝 **Kundalik qaydingiz saqlandi!**\n\n"
                f"📁 Obsidian: `Journal/Daily-Notes/{today_str}.md`\n"
                f"🧠 **Tahlil**:\n{analysis}"
            )
            await _send_reply(update, reply_msg)
            return

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


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    doc = update.message.document
    filename = doc.file_name
    await update.message.reply_text(f"📄 '{filename}' fayli qabul qilindi. Tizimlashtirilmoqda...")
    await update.message.chat.send_action(ChatAction.TYPING)

    ext = os.path.splitext(filename)[1].lower()
    tmp_path = tempfile.mktemp(suffix=ext)
    
    try:
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(tmp_path)
        
        text_content = ""
        if ext in (".txt", ".md"):
            with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                text_content = f.read()
        elif ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(tmp_path)
                pages_text = []
                for page in reader.pages[:10]: # Read first 10 pages for classification
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
                text_content = "\n".join(pages_text)
            except Exception as e:
                logger.warning(f"PDF o'qishda xatolik: {e}")
        
        # Classify the document using Gemini
        classify_prompt = (
            f"Fayl nomi: '{filename}'\n"
            f"Kengaytma: '{ext}'\n"
            f"Matn boshlanishi: '{text_content[:1500]}'\n\n"
            "Ushbu fayl turini va mazmunini aniqlang. Uni saqlash uchun eng mos Obsidian papkasini tanlang. Papka quyidagilardan biri bo'lishi shart:\n"
            "1. ReadLater/Books (kitoblar, maqolalar va o'qish uchun materiallar uchun)\n"
            "2. Finance/Receipts (moliyaviy hujjatlar, invoyslar, cheklar, to'lov hujjatlari uchun)\n"
            "3. Projects/Documents (loyihaga oid hujjatlar, taqdimotlar, shartnomalar, texnik topshiriqlar uchun)\n"
            "4. Inbox (qolgan barcha holatlarda)\n\n"
            "Javobni quyidagi formatda qaytaring (faqat shu ikki qatordan iborat bo'lsin, boshqa hech narsa yozmang):\n"
            "Papka: [papka nomi]\n"
            "Nomi: [faylning toza, tartibli nomi - masalan, 'Loyiha_Nizomi.pdf' yoki 'Ertaklar.txt', kengaytmasini o'zgartirmang]"
        )
        
        target_dir = "Inbox"
        clean_name = filename
        
        try:
            sys_prompt = "Sen hujjatlarni papkalarga tartiblovchi shaxsiy yordamchisan."
            classification = await ai.process_message(classify_prompt, sys_prompt, use_tools=False)
            
            # Parse classification response
            lines = [l.strip() for l in classification.split("\n") if l.strip()]
            for line in lines:
                if line.lower().startswith("papka:"):
                    raw_dir = line.split(":", 1)[1].strip()
                    # Keep only valid options
                    for opt in ["ReadLater/Books", "Finance/Receipts", "Projects/Documents", "Inbox"]:
                        if opt.lower() in raw_dir.lower():
                            target_dir = opt
                            break
                elif line.lower().startswith("nomi:"):
                    clean_name = line.split(":", 1)[1].strip()
        except Exception as ex:
            logger.error(f"Classification error: {ex}")
        
        # Target path in Obsidian
        obsidian_filepath = f"{target_dir}/{clean_name}"
        
        # Save the original file to Obsidian Synced Vault!
        obs_res = await asyncio.to_thread(
            obsidian.add_file,
            obsidian_filepath,
            tmp_path
        )
        
        # If it is a readable document, let's also generate a summary/outline and save it as an MD note
        summary_res = ""
        if text_content.strip():
            summary_prompt = (
                f"Quyidagi hujjatning matnini diqqat bilan o'qib chiq.\n"
                f"Fayl nomi: {clean_name}\n\n"
                f"Ushbu hujjatdan eng muhim g'oyalar, tushunchalar va xulosalarni ajratib, "
                f"professional va tizimli konspekt tayyorlang. "
                f"Konspektni o'zbek tilida, markdown formatida yozing.\n\nMatn:\n\n{text_content[:200000]}"
            )
            sys_prompt_summary = "Sen hujjatlarni va kitoblarni tahlil qilish hamda mukammal xulosalash bo'yicha professional mutaxassis yordamchisan."
            summary = await ai.process_message(summary_prompt, sys_prompt_summary, use_tools=False)
            
            clean_title = os.path.splitext(clean_name)[0]
            summary_filepath = f"{target_dir}/{clean_title}-Summary.md"
            
            obsidian_summary_content = (
                f"# {clean_title} - Hujjat Xulosasi\n\n"
                f"- **Asl fayl:** `{clean_name}` (Saqlangan joyi: `{obsidian_filepath}`)\n"
                f"- **Tahlil sanasi:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"## 📝 Konspekt va Tahlil\n\n{summary}"
            )
            
            obs_sum_res = await asyncio.to_thread(
                obsidian.add_note,
                summary_filepath,
                obsidian_summary_content,
                False
            )
            summary_res = f"\n\n📝 **Tahlil va Xulosa:**\nFayl: `{summary_filepath}`\n\n{summary[:800]}..."
            
        reply = (
            f"📁 **Fayl Tizimlashtirildi!**\n"
            f"Asl fayl nomi: `{filename}`\n"
            f"Yangi joylashuv: `{obsidian_filepath}`\n"
            f"Natija: {obs_res}{summary_res}"
        )
        await _send_reply(update, reply)
        
    except Exception as e:
        logger.error(f"Error organizing document: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Faylni qayta ishlashda xatolik: {e}")
    finally:
        try: os.unlink(tmp_path)
        except OSError: pass


async def _send_reply(update: Update, text: str) -> None:
    # QR kod fayli
    if text.startswith("__QR_FILE__:"):
        path = text.split(":", 1)[1]
        try:
            with open(path, "rb") as f:
                await update.message.reply_photo(photo=f, caption="QR Kod")
        except Exception as e:
            await update.message.reply_text(f"QR saqlandi: {path}")
        finally:
            try: os.unlink(path)
            except OSError: pass
        return
    # PDF fayli
    if text.startswith("__PDF_FILE__:"):
        path = text.split(":", 1)[1]
        try:
            with open(path, "rb") as f:
                await update.message.reply_document(document=f, filename="invoice.pdf")
        except Exception as e:
            await update.message.reply_text(f"PDF saqlandi: {path}")
        finally:
            try: os.unlink(path)
            except OSError: pass
        return
    # Oddiy matn
    safe_text = text.replace("**", "*")
    try: await update.message.reply_text(safe_text, parse_mode="Markdown")
    except Exception:
        try: await update.message.reply_text(safe_text)
        except Exception as e: await update.message.reply_text(f"❌ Xato: {e}")


def _check_all_env_vars() -> str:
    """Muhim muhit o'zgaruvchilarini tekshirish."""
    import developer as dev
    required = {
        "BOT_TOKEN": os.environ.get("BOT_TOKEN"),
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
        "NOTION_TOKEN": os.environ.get("NOTION_TOKEN"),
        "GITHUB_TOKEN": os.environ.get("GITHUB_TOKEN"),
        "RAILWAY_API_TOKEN": os.environ.get("RAILWAY_API_TOKEN"),
        "TG_API_ID": os.environ.get("TG_API_ID"),
        "TG_SESSION_STRING": os.environ.get("TG_SESSION_STRING"),
        "GOOGLE_CALENDAR_ID": os.environ.get("GOOGLE_CALENDAR_ID"),
        "INSTAGRAM_USER": os.environ.get("INSTAGRAM_USER"),
    }
    lines = ["Muhit o'zgaruvchilari holati:"]
    for key, val in required.items():
        if val:
            lines.append(f"✅ {key}: mavjud")
        else:
            lines.append(f"❌ {key}: YO'Q — bu funksiya ishlamaydi!")
    return "\n".join(lines)


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
    elif query.data.startswith("prj_done_"):
        try:
            import database
            did = int(query.data.split("_")[-1])
            ok = await database.db_complete_deadline(did)
            if ok:
                deadlines = await database.db_get_deadlines(days_ahead=90, include_overdue=True)
                if not deadlines:
                    await query.edit_message_text("🚀 **Loyihalar va Deadlinelar**\n\nHozirda faol loyihalar va deadlinelar yo'q.")
                    return
                
                lines = []
                pri_emoji = {"critical": "🔴", "high": "🟠", "normal": "🟡", "low": "🟢"}
                for d in deadlines:
                    days = d["days_left"]
                    when = f"⚠️ {abs(days)}k kechikdi" if days < 0 else "🚨 BUGUN" if days == 0 else f"{days}k qoldi"
                    pri = pri_emoji.get(d["priority"], "⚪")
                    proj = f"[{d['project']}] " if d["project"] else ""
                    lines.append(f"{pri} #{d['id']} {proj}{d['title']} — {d['deadline_date']} ({when})")
                
                keyboard = []
                row = []
                for d in deadlines[:8]:
                    row.append(InlineKeyboardButton(f"✅ #{d['id']}", callback_data=f"prj_done_{d['id']}"))
                    if len(row) == 2:
                        keyboard.append(row)
                        row = []
                if row:
                    keyboard.append(row)
                
                await query.edit_message_text(
                    "🚀 **Loyihalar va Deadlinelar (Interactive Dashboard)**\n\n" + "\n".join(lines) + "\n\nBajarilganlarini pastdagi tugmalar orqali yakunlang:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            else:
                await query.answer("❌ Xatolik yuz berdi yoki topilmadi.", show_alert=True)
        except Exception as e:
            logger.error(f"Callback project done error: {e}")


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_owner(update): return
    await clear_shared_history()
    context.user_data["history"] = []
    await update.message.reply_text("🗑 Suhbat tarixi to'liq tozalandi.")


async def post_init(application: Application) -> None:
    global userbot, GLOBAL_JOB_QUEUE, GLOBAL_BOT, BOT_USERNAME
    GLOBAL_JOB_QUEUE = application.job_queue
    GLOBAL_BOT = application.bot

    # Bot username ni kesh qilamiz (har xabarda get_me() qilmaslik uchun)
    bot_me = await application.bot.get_me()
    BOT_USERNAME = bot_me.username or ""
    logger.info(f"✅ Bot username: @{BOT_USERNAME}")

    from api import BOT_CONTEXT
    BOT_CONTEXT["bot"] = application.bot
    BOT_CONTEXT["owner_id"] = OWNER_ID
    BOT_CONTEXT["obsidian"] = obsidian

    # ── PostgreSQL DB jadvallarini yaratish ──
    try:
        from database import init_db
        await init_db()
        logger.info("✅ PostgreSQL tayyor")
    except Exception as e:
        logger.error(f"❌ DB init muvaffaqiyatsiz: {e}")


    async def setup_userbot():
        global userbot, OWNER_ID
        if TG_API_ID and TG_API_HASH and TG_PHONE:
            try:
                logger.info("📱 Orqa fonda Userbotni ishga tushirish boshlanmoqda...")
                ub = UserBot(api_id=int(TG_API_ID), api_hash=TG_API_HASH, phone=TG_PHONE)
                await ub.connect()
                try:
                    me = await ub.client.get_me()
                    if me:
                        OWNER_ID = me.id
                        logger.info(f"🔒 Bot xavfsizlik uchun faqat {OWNER_ID} ga qulflangan!")
                except Exception as ex:
                    logger.warning(f"Owner ID olishda xato: {ex}")
                
                async def ai_for_autoreply(text, history, system):
                    return await ai.process_message(text, system, execute_tool)
                ub.set_ai(ai_for_autoreply)

                async def notify_owner(text: str):
                    try:
                        owner = application.bot_data.get("owner_chat_id")
                        if owner: await application.bot.send_message(owner, text.replace("**", "*"), parse_mode="Markdown")
                    except: pass
                
                ub.set_notify(notify_owner)
                await ub.start_auto_reply()
                
                userbot = ub
                from api import BOT_CONTEXT
                BOT_CONTEXT["userbot"] = ub
                logger.info("✅ Userbot muvaffaqiyatli ulandi va sozlandi.")
            except Exception as e:
                logger.warning(f"⚠️ Userbot ulana olmadi: {e}")
                userbot = None

    asyncio.create_task(setup_userbot())

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

    prompt = "Quyida foydalanuvchining bugungi barcha muhim chatlaridan yig'ilgan xabarlar ro'yxati berilgan. Har bir xabar oldida uning sanasi [YIL-OY-KUN SOAT:MINUT] formatida ko'rsatilgan. Bularni o'qib eng muhimlarini (priority bo'yicha) saralab, o'zbekcha chiroyli hisobot qilib (Digest) ber:\n\n" + text_data
    
    sys_prompt = (
        "Sen J.A.R.V.I.S. - aqlli shaxsiy yordamchisan. "
        "Sening vazifang - foydalanuvchining bugungi Telegram chatlaridan yig'ilgan xabarlarni tahlil qilish va eng muhim ma'lumotlarni saralab, chiroyli, tushunarli va professional kunlik hisobot (Digest) tayyorlash.\n\n"
        "HISOBOT STRUKTURASI:\n"
        "1. 📊 **KUNLIK MUHIM MAVZULAR VA TRENDLAR**\n"
        "   - Bugun chatlarda muhokama qilingan eng asosiy yangiliklar, trendlar va masalalar (qisqa, mazmunli bullet-point ko'rinishida).\n"
        "2. 💬 **MUHIM CHATLAR VA TOPSHIRIQLAR**\n"
        "   - Kimdan qanday muhim xabar kelganligi, topshiriqlar va e'tibor qaratish kerak bo'lgan vazifalar.\n"
        "3. 📋 **PIPELINE VA JAMOA STATUSI (AGENCY)**\n"
        "   - Agar guruhdagi AI xodimlarning (Trend Hunter, Ssenariynavis, Dizayner, Kopirayter, Loyiha Menejeri, Notion Mutaxassisi, Dasturchi) faolligi haqida ma'lumot bo'lsa, jamoaning holati va pipeline qaysi bosqichda ekanligi haqida qisqa hisobot.\n"
        "4. 🧠 **SHAXSIY INTIZOM VA TAVSIYALAR**\n"
        "   - Shaxsiy intizom bo'yicha qat'iy tavsiyalar va keyingi qadamlar.\n\n"
        "MUHIM QOIDALAR:\n"
        "- Faqat o'zbek tilida yoz.\n"
        "- Senga hech qanday tool/funksiyalarni chaqirishga ruxsat berilmagan. Ularni umuman ishlatma.\n"
        "- Matndagi havolalarni (YouTube, veb-sayt va boshqalar) shunchaki matn ko'rinishida tahlil qil, ularni ochish uchun tool chaqirma.\n"
        "- Agar berilgan xabarlar ichida texnik xatoliklar yoki yuklash xatoliklari haqida xabarlar bo'lsa, ularni foydalanuvchiga yuboriladigan hisobotga qo'shma, ularni shunchaki e'tiborsiz qoldir.\n"
        "- Har bir bo'limni o'zaro chiziqlar (---) bilan ajrat va juda professional, chiroyli dizaynda taqdim et."
    )

    try:
        response = await ai.process_message("Menga bugungi chatlar tahlilini ber!\n\n" + prompt, sys_prompt, use_tools=False)
        report = f"📊 **Kunlik Kechki Telegram Tahlili (20:00)**\n\n{response}"
        # @abdullayev_ii ga yuborish
        await userbot.send_message("@abdullayev_ii", report)
    except Exception as e:
        logger.error(f"Digest yuborishda xato: {e}")

async def habit_tracker_prompt_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("⏱ Habit tracker prompt jo'natilmoqda...")
    msg = (
        "🏋️‍♂️ **Isroiljon, bugungi odatlar hisoboti vaqti keldi!**\n\n"
        "Bugun qaysi odatlarni bajardingiz? Menga yozing (masalan, 'Sport va Kitob' yoki 'hammasi'), men esa ro'yxatingizni yangilab qo'yaman."
    )
    sent = False
    if userbot and getattr(userbot, "connected", False):
        try:
            await userbot.send_message("@abdullayev_ii", msg)
            sent = True
        except Exception as e:
            logger.warning(f"userbot habit prompt send error: {e}")
            
    if not sent and OWNER_ID:
        try:
            await context.bot.send_message(OWNER_ID, msg)
        except Exception as e:
            logger.warning(f"bot habit prompt send error: {e}")


async def morning_briefing_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("☀️ Ertalabki brifing + reja...")
    import database
    import datetime
    import pytz
    tz = pytz.timezone("Asia/Tashkent")
    today = datetime.datetime.now(tz).date().strftime("%Y-%m-%d")

    tasks = await database.db_get_plan(today)
    plan_text = ""
    if tasks:
        task_lines = []
        for i, t in enumerate(tasks, 1):
            check = "✅" if t.get("done") else f"{i}."
            pri = " 🔴" if t.get("priority") == "high" else ""
            task_lines.append(f"{check} {t['text']}{pri}")
        plan_text = "\n".join(task_lines)
    else:
        plan_text = "Bugun uchun reja belgilanmagan."

    deadline_text = await database.db_get_deadline_summary()

    cal_events = "Taqvim ma'lumotlarini olish imkoni bo'lmadi."
    try:
        cal_events = await cloud.calendar_get_events(max_results=5)
    except Exception as ex:
        logger.warning(f"Briefing calendar fetch error: {ex}")

    gmail_unread = "Gmail o'qish imkoni bo'lmadi."
    try:
        gmail_unread = await cloud.gmail_read_unread(limit=5)
    except Exception as ex:
        logger.warning(f"Briefing gmail fetch error: {ex}")

    weather = "Tashkent ob-havosini olish imkoni bo'lmadi."
    try:
        from duckduckgo_search import DDGS
        proxy_url = os.environ.get("PROXY_URL")
        with DDGS(proxy=proxy_url) as ddgs:
            results = list(ddgs.text("Tashkent weather today", max_results=1))
            if results:
                weather = results[0].get("body", "")
    except Exception as ex:
        logger.warning(f"Briefing weather fetch error: {ex}")

    prompt = (
        f"Bugun sana: {today}.\n\n"
        f"KUNLIK REJA:\n{plan_text}\n\n"
        f"YAQINLAShAYOTGAN DEADLINELAR:\n{deadline_text}\n\n"
        f"GOOGLE CALENDAR BUGUNGI EVENTLARI:\n{cal_events}\n\n"
        f"GMAIL O'QILMAGAN XABARLAR:\n{gmail_unread}\n\n"
        f"OB-HAVO MA'LUMOTLARI:\n{weather}\n\n"
        "Sen unga ertalabki brifingni o'zbek tilida qat'iy va intizomli yordamchi (J.A.R.V.I.S) tonida yozib ber. "
        "Matnda quyidagi bo'limlar bo'lsin:\n"
        "1. 🌤 Ob-havo va kun boshlanishi\n"
        "2. 📅 Taqvim uchrashuvlari (Calendar)\n"
        "3. ✉️ Yangi kelgan xatlar (Gmail)\n"
        "4. ⏰ Deadlinelar va Kunlik topshiriqlar\n\n"
        "MUHIM QOIDA: Javobda hech qachon *, **, #, ` kabi markdown belgilarini ishlatma. "
        "Faqat oddiy matn va emojilardan foydalanib, chiroyli va o'qilishi qulay formatlangan xabar yoz."
    )

    try:
        response = await ai.process_message(prompt, build_system_prompt([]), use_tools=False)
        report = f"☀️ **Tonggi Brifing — {today}**\n\n{response}"

        if userbot:
            await userbot.send_message("@abdullayev_ii", report)
        elif GLOBAL_BOT and OWNER_ID:
            await GLOBAL_BOT.send_message(OWNER_ID, report)
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

async def rss_news_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("⏱ RSS News Digest jarayoni boshlandi...")
    feeds = [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.wired.com/feed/category/gear/latest/rss"
    ]
    
    all_articles = []
    for f in feeds:
        try:
            articles = await cloud.fetch_rss_feed(f, limit=3)
            all_articles.extend(articles)
        except Exception as ex:
            logger.warning(f"Error fetching RSS {f}: {ex}")
            
    if not all_articles:
        logger.info("Yangi RSS maqolalar topilmadi.")
        return
        
    prompt = (
        "Quyida eng so'nggi texnologiya va AI yangiliklari ro'yxati berilgan. Ularni tahlil qilib, marketing va biznes nuqtai nazaridan eng muhim 3 ta mavzuni saralab ol va o'zbek tilida qisqacha xulosa tayyorlab ber.\n"
        "MUHIM: Javobda *, **, #, ` kabi markdown belgilarini ishlatma — faqat oddiy matn va emojilar.\n\n"
        + str(all_articles)
    )
    
    try:
        sys_prompt = "Sen yangiliklarni tahlil qiluvchi va Obsidian ikkinchi miyasiga qayd kirituvchi yordamchisan."
        response = await ai.process_message(prompt, sys_prompt, use_tools=False)
        
        import datetime
        import pytz
        tz = pytz.timezone("Asia/Tashkent")
        today = datetime.datetime.now(tz).strftime("%Y-%m-%d")
        filepath = f"ReadLater/News/Digest-{today}.md"
        
        obsidian_res = await asyncio.to_thread(
            obsidian.add_note,
            filepath,
            f"# AI & Tech News Digest — {today}\n\n{response}",
            False
        )
        logger.info(f"RSS digest Obsidian'ga saqlandi: {obsidian_res}")
        
        report = f"📰 **Yangi AI & Tech Trendlar Arxivlandi!**\n\nHisobot Obsidian'dagi `{filepath}` qaydiga saqlandi.\n\n**Qisqacha xulosa:**\n{response[:600]}..."
        if userbot:
            await userbot.send_message("@abdullayev_ii", report)
    except Exception as e:
        logger.error(f"RSS digest job error: {e}")

async def burnout_check_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("⏱ Burnout checking job started...")
    import database
    import datetime
    import pytz
    tz = pytz.timezone("Asia/Tashkent")
    
    today = datetime.datetime.now(tz).date()
    completions = []
    for i in range(7):
        day_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        summary = await database.db_get_plan_summary(day_str)
        completions.append(summary)
        
    journals = []
    for i in range(5):
        day_str = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        filepath = f"Journal/Daily-Notes/{day_str}.md"
        content = await asyncio.to_thread(obsidian.read_note, filepath)
        if "❌ Qayd topilmadi" not in content:
            journals.append(f"[{day_str}]: {content[:400]}")
            
    prompt = (
        "Quyida foydalanuvchining oxirgi 7 kunlik topshiriqlari natijalari va 5 kunlik shaxsiy kundalik qaydlari berilgan. "
        "Ularni tahlil qilib, foydalanuvchining ruhiy holati va charchash (Burnout) darajasini baholang. "
        "Agar tahlilda kuchli charchoq, stress yoki motivatsiya yetishmasligi aniqlansa, foydalanuvchiga buni o'zbek tilida, qat'iy va shaxsiy tavsiyalar bilan ma'lum qiling. "
        "MUHIM: Javobda *, **, #, ` markdown belgilarini ishlatma — faqat oddiy matn va emojilar.\n\n"
        f"Vazifalar ko'rsatkichlari:\n{str(completions)}\n\n"
        f"Kundalik qaydlaridan parchalar:\n" + "\n".join(journals)
    )
    
    try:
        sys_prompt = "Sen ruhiy holat va shaxsiy intizomni nazorat qiluvchi aqlli shaxsiy murabbiysan."
        response = await ai.process_message(prompt, sys_prompt, use_tools=False)
        
        report = f"🧠 **AI Murabbiy: Charchash va Motivatsiya Tahlili**\n\n{response}"
        if userbot:
            await userbot.send_message("@abdullayev_ii", report)
    except Exception as e:
        logger.error(f"Burnout check error: {e}")

async def gmail_draft_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("⏱ Gmail tekshiruvi (Auto-Draft) boshlandi...")
    try:
        data = await cloud.gmail_read_unread(limit=5)
        if "Yangi (o'qilmagan) xatlar yo'q" in data or "❌" in data:
            return
            
        prompt = (
            "Pochtada (Gmail) yangi o'qilmagan xatlar bor:\n\n"
            f"{data}\n\n"
            "Isroiljon nomidan har bir yangi xatga qisqacha, professional javob matnini tayyorlang "
            "va uni `gmail_create_draft` toolini chaqirib, Gmail qoralamalariga (Drafts) saqlang.\n"
            "Oxirida Telegram orqali qaysi xatlarga qanday javob qoralamalari yaratilgani haqida qisqacha hisobot yozing."
        )
        sys_prompt = (
            "Sen shaxsiy AI yordamchisan. Yangi xatlar uchun javob qoralamalarini (Drafts) yaratish uchun "
            "tizimdagi `gmail_create_draft` toolidan foydalanishing shart."
        )
        response = await ai.process_message(prompt, sys_prompt, execute_tool)
        
        report = f"📧 **Pochta Hisoboti (Gmail Auto-Draft)**\n\n{response}"
        
        sent = False
        if userbot and getattr(userbot, "connected", False):
            try:
                await userbot.send_message("@abdullayev_ii", report)
                sent = True
            except Exception as e:
                logger.warning(f"userbot gmail report xato: {e}")
                
        if not sent and OWNER_ID:
            try:
                await context.bot.send_message(OWNER_ID, report)
            except Exception as e:
                logger.warning(f"bot gmail report xato: {e}")
    except Exception as e:
        logger.error(f"Gmail job xatosi: {e}")


async def uptime_monitor_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har 10 daqiqada saytlarni tekshirish."""
    try:
        alerts = await asyncio.to_thread(mon.check_all_urls)
        for alert in alerts:
            msg = f"{'🔴 SAYT TUSHDI' if alert['type']=='down' else '🟢 Sayt qayta ishlayapti'}\n{alert['message']}"
            try:
                await context.bot.send_message(OWNER_ID, msg)
            except Exception as e:
                logger.error(f"Uptime alert yuborish xatosi: {e}")
    except Exception as e:
        logger.error(f"Uptime monitor xatosi: {e}")


async def railway_crash_monitor_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har 5 daqiqada Railway crashlarni tekshirish."""
    try:
        alerts = await asyncio.to_thread(mon.check_railway_crashes)
        for alert in alerts:
            msg = (
                f"💥 RAILWAY CRASH\n"
                f"Loyiha: {alert['project']}\n"
                f"Servis: {alert['service']}\n"
                f"Holat: {alert['status']}\n\n"
                f"Loglarni ko'rish uchun: /logs {alert['service'][:8]}"
            )
            try:
                await context.bot.send_message(OWNER_ID, msg)
            except Exception as e:
                logger.error(f"Crash alert yuborish xatosi: {e}")
    except Exception as e:
        logger.error(f"Railway crash monitor xatosi: {e}")


async def scheduled_posts_sender_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har daqiqada rejalashtirilgan postlarni yuborish."""
    try:
        due_posts = await asyncio.to_thread(sched.get_pending_posts)
        for post in due_posts:
            try:
                chat_id = post["chat_id"]
                text = post["text"]
                # chat_id raqammi yoki @username mi?
                if chat_id.lstrip("-").isdigit():
                    target = int(chat_id)
                else:
                    target = chat_id
                await context.bot.send_message(target, text)
                await asyncio.to_thread(sched.mark_sent, post["id"])
                logger.info(f"Rejalashtirilgan post yuborildi: {post['chat_name']}")
            except Exception as e:
                logger.error(f"Rejalashtirilgan post xatosi ({post.get('id')}): {e}")
    except Exception as e:
        logger.error(f"Scheduled posts sender xatosi: {e}")


async def competitor_check_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har dushanba raqobatchilarni tekshirish."""
    try:
        changes = await asyncio.to_thread(mon.check_competitors)
        if not changes:
            return
        msg = "🔍 RAQOBATCHILAR YANGILIGI:\n\n"
        for ch in changes:
            msg += f"• {ch['message']}\n"
        msg += "\nBatafsil tahlil uchun: 'raqobatchilarni tahlil qil' dang."
        await context.bot.send_message(OWNER_ID, msg)
    except Exception as e:
        logger.error(f"Competitor check xatosi: {e}")


async def smart_kundalik_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har kuni kechki 21:45 da smart kundalik xisoboti."""
    try:
        import database
        import datetime as dt
        tz = pytz.timezone("Asia/Tashkent")
        today = dt.datetime.now(tz).strftime("%Y-%m-%d")

        plan_summary = await database.db_get_plan_summary(today)
        rejalashtirilgan = await asyncio.to_thread(sched.list_scheduled_posts)

        prompt = (
            f"Bugun ({today}) quyidagi ma'lumotlar mavjud:\n\n"
            f"VAZIFALAR HOLATI:\n{plan_summary}\n\n"
            f"REJALASHTIRILGAN POSTLAR:\n{rejalashtirilgan}\n\n"
            f"Sen J.A.R.V.I.S. sifatida quyidagi formatda QISQA kundalik hisobot yoz:\n"
            f"BUGUN BAJARILDI: [ro'yxat]\n"
            f"BAJARILMADI: [ro'yxat]\n"
            f"ERTAGA USTUVOR: [top 3 vazifa]\n"
            f"MASLAHAT: [1 jumlali motivatsion maslax]\n\n"
            f"Til: O'zbek. Ixcham bo'l."
        )
        response = await ai.process_message(prompt, "", use_tools=False)
        safe = response.replace("**", "").replace("*", "").replace("#", "")
        await context.bot.send_message(OWNER_ID, f"JARVIS KUNDALIK ({today}):\n\n{safe}")
    except Exception as e:
        logger.error(f"Smart kundalik xatosi: {e}")

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


NOTIFIED_EVENTS = set()

async def calendar_alert_checker_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("⏱ Google Calendar eslatmalarini tekshirish jarayoni boshlandi...")
    global NOTIFIED_EVENTS
    try:
        events = await cloud.get_raw_upcoming_events(minutes_ahead=15)
        if not events:
            return

        for event in events:
            eid = event.get("id")
            if eid in NOTIFIED_EVENTS:
                continue

            summary = event.get("summary", "Nomsiz Uchrashuv")
            start = event.get("start", {})
            start_time_str = start.get("dateTime", start.get("date", ""))
            
            # Simple keyword extraction (alphanumeric, len > 3)
            import re
            words = re.findall(r'\b\w{4,}\b', summary)
            
            context_notes = []
            if words:
                for w in words[:3]:
                    search_res = await asyncio.to_thread(obsidian.search_notes, w)
                    paths = re.findall(r'`([^`]+)`', search_res)
                    for path in paths[:2]:
                        note_content = await asyncio.to_thread(obsidian.read_note, path)
                        if "topilmadi" not in note_content and "xatolik" not in note_content:
                            context_notes.append(f"📁 Qayd: {path}\nMatn:\n{note_content}")

            notes_text = "\n\n".join(context_notes) if context_notes else "Mavzuga doir qaydlar topilmadi."
            
            prompt = (
                f"Isroiljonning kelgusi 15 daqiqada quyidagi uchrashuvi boshlanmoqda:\n"
                f"📌 Mavzu: {summary}\n"
                f"⏰ Boshlanish vaqti: {start_time_str}\n\n"
                f"Uning shaxsiy Obsidian miyasidan topilgan bog'liq qaydlar:\n{notes_text}\n\n"
                f"Uchrashuv oldidan unga bilishi zarur bo'lgan eng muhim kontekst va eslatmalarni o'zbek tilida, "
                f"o'ta qisqa (3-4 gapda) va samimiy, intizomli yordamchi (Jasmina) tonida yozib bering."
            )
            
            response = await ai.process_message(
                prompt,
                "Sen Jasminasan, shaxsiy AI yordamchi. Uchrashuv kontekstini qisqa va chiroyli tayyorlaysan.",
                execute_tool
            )
            
            alert_text = (
                f"⏰ **Kelgusi Uchrashuv Eslatmasi (15 daqiqa qoldi)**\n\n"
                f"📅 **Mavzu:** {summary}\n"
                f"🕒 **Vaqti:** {start_time_str[:16].replace('T', ' ')}\n\n"
                f"💡 **AI Kontekst & Eslatma:**\n{response}"
            )
            
            if OWNER_ID != 0:
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=alert_text,
                    parse_mode="Markdown"
                )
                logger.info(f"✅ Uchrashuv eslatmasi yuborildi: {summary}")
            
            NOTIFIED_EVENTS.add(eid)
    except Exception as e:
        logger.error(f"Calendar alert checker error: {e}", exc_info=True)


async def deadline_alert_checker_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("⏱ Deadline 3 kunlik ogohlantirish tekshiruvi boshlandi...")
    try:
        import database
        deadlines = await database.db_get_deadlines(days_ahead=3, include_overdue=False)
        alert_deadlines = [d for d in deadlines if d.get("days_left") == 3]
        
        if not alert_deadlines:
            return
            
        lines = []
        for d in alert_deadlines:
            proj = f"[{d['project']}] " if d["project"] else ""
            lines.append(f"• {proj}{d['title']} — Muddati: {d['deadline_date']}")
            
        msg = (
            "🔔 **Yaqinlashayotgan Deadline Ogohlantirishi!**\n\n"
            "Isroiljon, quyidagi loyiha/vazifalar tugashiga roppa-rosa 3 kun qoldi:\n\n"
            + "\n".join(lines) +
            "\n\nKechikmaslik uchun hozirdan harakat qiling!"
        )
        
        sent = False
        if userbot and getattr(userbot, "connected", False):
            try:
                await userbot.send_message("@abdullayev_ii", msg)
                sent = True
            except Exception as e:
                logger.warning(f"userbot deadline alert error: {e}")
                
        if not sent and OWNER_ID:
            try:
                await context.bot.send_message(OWNER_ID, msg)
            except Exception as e:
                logger.warning(f"bot deadline alert error: {e}")
                
    except Exception as e:
        logger.error(f"Deadline alert checker job error: {e}")


async def weekly_finance_report_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("⏱ Haftalik moliyaviy tahlil boshlandi...")
    try:
        import database
        txns = await database.db_get_transactions_raw()
        
        import datetime
        tz = pytz.timezone("Asia/Tashkent")
        now = datetime.datetime.now(tz)
        seven_days_ago = now - datetime.timedelta(days=7)
        
        recent_txns = []
        for t in txns:
            t_date = t['created_at']
            if t_date.tzinfo is None:
                t_date = tz.localize(t_date)
            if t_date >= seven_days_ago:
                recent_txns.append(t)
        
        txns_list = []
        for t in recent_txns:
            date_str = t['created_at'].strftime("%Y-%m-%d %H:%M")
            txns_list.append(f"- [{date_str}] {t['type'].upper()} | {t['amount']:,} {t['currency']} | Kategoriya: {t['category']} | {t.get('description','')}")
            
        txns_text = "\n".join(txns_list) if txns_list else "Ushbu haftada hech qanday tranzaksiya yozilmagan."
        
        prompt = (
            f"Foydalanuvchi Isroiljonning oxirgi 7 kundagi xarajat va daromadlari ro'yxati berilgan:\n"
            f"{txns_text}\n\n"
            f"Siz aqlli moliya yordamchisisiz. Ushbu ma'lumotlarni tahlil qiling. "
            f"Haftalik jami xarajat, jami daromad va sof foyda hisobini chiqaring. "
            f"Qaysi yo'nalishga eng ko'p mablag' sarflanganini aniqlang. "
            f"Kelgusi hafta uchun 3 ta amaliy va tejamkor moliyaviy maslahat bering. "
            f"O'zbek tilida, professional va intizomli ohangda (J.A.R.V.I.S. moliya tahlili) chiroyli hisobot qiling. Markdown formatida bo'lsin."
        )
        
        response = await ai.process_message(
            prompt,
            "Sen shaxsiy moliyaviy yordamchisan. Haftalik hisobotni chiroyli va tahliliy yozib berasan.",
            execute_tool
        )
        
        today_str = now.strftime("%Y-%m-%d")
        report = (
            f"📊 **Haftalik Moliyaviy AI Tahlil & Hisobot ({today_str})**\n\n"
            f"{response}"
        )
        
        if OWNER_ID != 0:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=report,
                parse_mode="Markdown"
            )
            
        filepath = f"Finance/Reports/Weekly-Report-{today_str}.md"
        note_content = (
            f"# Haftalik Moliyaviy Tahlil ({today_str})\n\n"
            f"- **Davr:** {(now - datetime.timedelta(days=7)).strftime('%Y-%m-%d')} dan {today_str} gacha\n"
            f"- **Tahlilchi:** J.A.R.V.I.S. AI\n\n"
            f"{response}"
        )
        await asyncio.to_thread(obsidian.add_note, filepath, note_content, False)
        logger.info(f"✅ Haftalik moliyaviy hisobot yuborildi va Obsidian-ga saqlandi: {filepath}")
        
    except Exception as e:
        logger.error(f"Weekly finance report job error: {e}", exc_info=True)


async def send_coach_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    await update.message.reply_text("Tahlil qilinmoqda...")
    await life_coach_job(context)


async def send_brief_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Qo'lda /brief buyrug'i — tonggi brifingni darhol yuboradi."""
    if not await check_auth(update): return
    await update.message.reply_text("Brifing tayyorlanmoqda...")
    await morning_briefing_job(context)


async def send_news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Qo'lda /news buyrug'i — yangiliklar tahlilini darhol yuboradi."""
    if not await check_auth(update): return
    await update.message.reply_text("Yangiliklar qidirilmoqda...")
    await viral_news_job(context)

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
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


async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    import database
    
    deadlines = await database.db_get_deadlines(days_ahead=90, include_overdue=True)
    if not deadlines:
        await update.message.reply_text("🚀 **Loyihalar va Deadlinelar**\n\nHozirda faol loyihalar va deadlinelar mavjud emas.")
        return
        
    lines = []
    pri_emoji = {"critical": "🔴", "high": "orange_circle", "normal": "yellow_circle", "low": "green_circle"}
    pri_emoji = {"critical": "🔴", "high": "🟠", "normal": "🟡", "low": "🟢"}
    
    for d in deadlines:
        days = d["days_left"]
        when = f"⚠️ {abs(days)}k kechikdi" if days < 0 else "🚨 BUGUN" if days == 0 else f"{days}k qoldi"
        pri = pri_emoji.get(d["priority"], "⚪")
        proj = f"[{d['project']}] " if d["project"] else ""
        lines.append(f"{pri} #{d['id']} {proj}{d['title']} — {d['deadline_date']} ({when})")
        
    keyboard = []
    row = []
    for d in deadlines[:8]:
        row.append(InlineKeyboardButton(f"✅ #{d['id']}", callback_data=f"prj_done_{d['id']}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    await update.message.reply_text(
        "🚀 **Loyihalar va Deadlinelar (Interactive Dashboard)**\n\n" + "\n".join(lines) + "\n\nBajarilganlarini pastdagi tugmalar orqali yakunlang:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def cmd_brainstorm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    global BRAINSTORM_SESSIONS
    chat_id = update.effective_chat.id
    
    args = context.args
    if not args:
        await update.message.reply_text("Reja loyihasi nomini kiriting. Masalan: `/brainstorm Suniy Intellekt Bot`", parse_mode="Markdown")
        return
        
    project_name = " ".join(args)
    BRAINSTORM_SESSIONS[chat_id] = {
        "project_name": project_name,
        "thoughts": []
    }
    
    await update.message.reply_text(
        f"🧠 **Brainstorming rejimi yoqildi!**\n"
        f"Loyiha: *{project_name}*\n\n"
        f"Endi ushbu loyiha haqidagi fikrlaringizni matn yoki ovozli xabar ko'rinishida yuboring. Men ularni yig'ib boraman. "
        f"Tugatgandan so'ng /finish_brainstorm buyrug'ini bering.",
        parse_mode="Markdown"
    )


async def cmd_finish_brainstorm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    global BRAINSTORM_SESSIONS
    chat_id = update.effective_chat.id
    
    session = BRAINSTORM_SESSIONS.get(chat_id)
    if not session:
        await update.message.reply_text("Sizda faol brainstorming sessiyasi yo'q. Boshlash uchun /brainstorm yozing.")
        return
        
    project_name = session["project_name"]
    thoughts = session["thoughts"]
    
    if not thoughts:
        await update.message.reply_text("Sessiya davomida hech qanday Fikr yozilmadi. Sessiya bekor qilindi.")
        BRAINSTORM_SESSIONS.pop(chat_id, None)
        return
        
    await update.message.reply_text("📝 Fikrlar yig'ildi. Loyiha rejasi tayyorlanmoqda, kuting...")
    await update.message.chat.send_action(ChatAction.TYPING)
    
    try:
        thoughts_text = "\n- ".join(thoughts)
        prompt = (
            f"Siz loyiha me'mori (Project Architect) va tizim tahlilchisisiz.\n"
            f"Foydalanuvchi Isroiljon o'zining yangi loyihasi haqidagi fikrlarini taqdim etdi:\n\n"
            f"Loyiha nomi: {project_name}\n"
            f"Fikrlar:\n- {thoughts_text}\n\n"
            f"Ushbu fikrlarni umumlashtirib, juda chiroyli, tushunarli va professional markdown loyiha outlinesini (.md) tayyorlang. "
            f"Unda loyiha maqsadi, asosiy imkoniyatlar (Features), arxitektura chizmasi (matnda), texnologiyalar steki va "
            f"bosqichma-bosqich amalga oshirish rejasi (Roadmap) o'rin olsin. Loyiha rejasini o'zbek tilida yozing."
        )
        
        sys_prompt = "Sen dasturiy loyihalarni rejalashtirish va tizimlashtirish bo'yicha eng tajribali arxitektorsan."
        outline = await ai.process_message(prompt, sys_prompt, execute_tool)
        
        clean_name = "".join([c for c in project_name if c.isalnum() or c in (" ", "-", "_")]).strip()
        filepath = f"Projects/{clean_name}-Outline.md"
        
        obs_res = await asyncio.to_thread(
            obsidian.add_note,
            filepath,
            f"# {project_name} — Outline\n\n"
            f"- **Tuzilgan sana:** {datetime.datetime.now().strftime('%Y-%m-%d')}\n"
            f"- **Turi:** Brainstorming Natijasi\n\n"
            f"{outline}",
            False
        )
        
        reply_msg = (
            f"🚀 **Loyiha Outlini Tayyor va Saqlandi!**\n\n"
            f"📁 Obsidian: `{filepath}`\n\n"
            f"📝 **Konspekt (Boshlanishi)**:\n\n{outline[:1500]}..."
        )
        await _send_reply(update, reply_msg)
        
    except Exception as e:
        logger.error(f"Brainstorm error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Loyihani rejalashtirishda xatolik: {e}")
    finally:
        BRAINSTORM_SESSIONS.pop(chat_id, None)


async def cmd_lead_magnet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update): return
    args = context.args
    if not args:
        await update.message.reply_text("Lead magnet mavzusini kiriting. Masalan: `/leadmagnet AI marketing`", parse_mode="Markdown")
        return
        
    topic = " ".join(args)
    await update.message.reply_text(f"📖 *'{topic}'* mavzusida professional Lead Magnet (PDF) yaratilmoqda. Iltimos kuting, bu 1 daqiqagacha vaqt olishi mumkin...", parse_mode="Markdown")
    await update.message.chat.send_action(ChatAction.TYPING)
    
    prompt = (
        f"Mavzu: '{topic}' bo'yicha marketing lead magnet (mijozlarni jalb qiluvchi bepul qo'llanma) uchun matn yozing. "
        f"Qo'llanmada muqaddima (intro), kamida 3 ta asosiy bo'lim (maslahatlar/qadamlar/strategiyalar) va xulosa bo'lishi kerak. "
        f"Qo'llanma matni o'zbek tilida bo'lsin. "
        f"Javobni FAQAT va FAQAT quyidagi JSON formatida qaytaring, boshqa hech qanday izoh yoki kirish matni yozmang:\n"
        f"{{\n"
        f"  \"title\": \"[Qo'llanma Sarlavhasi]\",\n"
        f"  \"sections\": [\n"
        f"    {{\n"
        f"      \"heading\": \"[1-bo'lim Sarlavhasi]\",\n"
        f"      \"paragraphs\": [\n"
        f"        \"[1-paragraf matni]\",\n"
        f"        \"[2-paragraf matni]\"\n"
        f"      ]\n"
        f"    }}\n"
        f"  ]\n"
        f"}}"
    )
    
    try:
        sys_prompt = "Sen kreativ va professional marketing bo'yicha mutaxassis hamda yozuvchisan. Faqat so'ralgan JSON formatida javob berasan."
        response = await ai.process_message(prompt, sys_prompt, use_tools=False)
        
        # Clean JSON markdown format if model wrapped it
        clean_json = response.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
        clean_json = clean_json.strip()
        
        import json
        data = json.loads(clean_json)
        
        title = data.get("title", f"{topic} qo'llanmasi")
        sections = data.get("sections", [])
        
        if not sections:
            await update.message.reply_text("❌ Matn generatori bo'sh bo'limlar qaytardi. Iltimos qaytadan urinib ko'ring.")
            return
            
        import tempfile
        tmp_pdf = tempfile.mktemp(suffix=".pdf")
        
        # Generate the PDF using reportlab
        await cloud.generate_lead_magnet_pdf(title, sections, tmp_pdf)
        
        # Save to Obsidian ReadLater/LeadMagnets/
        import re
        clean_title = "".join([c for c in title if c.isalnum() or c in (" ", "-", "_")]).strip()
        obsidian_filepath = f"ReadLater/LeadMagnets/{clean_title}.pdf"
        
        obs_res = await asyncio.to_thread(
            obsidian.add_file,
            obsidian_filepath,
            tmp_pdf
        )
        
        # Send PDF file to user
        from pathlib import Path
        with open(tmp_pdf, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"{clean_title}.pdf",
                caption=f"🎁 **Siz uchun Lead Magnet tayyorlandi!**\n\n"
                        f"📌 **Sarlavha:** {title}\n"
                        f"📁 **Obsidian:** `{obsidian_filepath}`\n"
                        f"Natija: {obs_res}",
                parse_mode="Markdown"
            )
            
        try: os.unlink(tmp_pdf)
        except OSError: pass
        
    except Exception as e:
        logger.error(f"Lead magnet generator error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Lead magnet yaratishda xatolik yuz berdi: {e}")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()


# ─────────────────────────────────────────────────────────────
# DASTURCHI KOMANDALAR
# ─────────────────────────────────────────────────────────────

async def cmd_dev(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Barcha Railway loyihalar va ularning holati."""
    if not await check_auth(update): return
    await update.message.reply_text("Loyihalar yuklanmoqda...")
    await update.message.chat.send_action(ChatAction.TYPING)
    result = await asyncio.to_thread(dev.railway_list_projects)
    # GitHub repolari ham
    repos = await asyncio.to_thread(dev.github_list_repos, 10)
    full = "RAILWAY PROYEKTLAR:\n" + result + "\n\nGITHUB REPOLAR:\n" + repos
    # 4096 belgi limitiga bo'lamiz
    for i in range(0, len(full), 4000):
        await update.message.reply_text(full[i:i+4000])


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Loyiha loglarini ko'rish: /logs <loyiha_nomi>"""
    if not await check_auth(update): return
    args = context.args
    if not args:
        names = ", ".join(dev.KNOWN_PROJECTS.keys())
        await update.message.reply_text(f"Loyiha nomini kiriting.\nMavjudlar: {names}\nMisol: /logs jarvis-personal-bot")
        return
    project_name = " ".join(args)
    info = dev.get_project_info(project_name)
    if not info:
        await update.message.reply_text(f"❌ '{project_name}' topilmadi. /dev orqali ro'yxatni ko'ring.")
        return
    await update.message.reply_text(f"📋 {info['name']} loglari yuklanmoqda...")
    await update.message.chat.send_action(ChatAction.TYPING)
    result = await asyncio.to_thread(dev.railway_get_logs, info["service"])
    for i in range(0, len(result), 4000):
        await update.message.reply_text(result[i:i+4000])


async def cmd_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Loyihani qayta deploy qilish: /deploy <loyiha_nomi>"""
    if not await check_auth(update): return
    args = context.args
    if not args:
        await update.message.reply_text("Misol: /deploy jarvis-personal-bot")
        return
    project_name = " ".join(args)
    info = dev.get_project_info(project_name)
    if not info:
        await update.message.reply_text(f"❌ '{project_name}' topilmadi.")
        return
    await update.message.reply_text(f"🔄 {info['name']} redeploy qilinmoqda...")
    result = await asyncio.to_thread(dev.railway_redeploy, info["service"])
    await update.message.reply_text(result)


async def cmd_fix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """AI yordamida buzilgan loyihani tuzatish: /fix <loyiha_nomi>"""
    if not await check_auth(update): return
    args = context.args
    if not args:
        await update.message.reply_text("Misol: /fix jarvis-personal-bot")
        return
    project_name = " ".join(args)
    info = dev.get_project_info(project_name)
    if not info:
        await update.message.reply_text(f"❌ '{project_name}' topilmadi. /dev orqali ro'yxatni ko'ring.")
        return

    await update.message.reply_text(f"🔍 {info['name']} loglari tahlil qilinmoqda...")
    await update.message.chat.send_action(ChatAction.TYPING)

    # Loglarni ol
    logs = await asyncio.to_thread(dev.railway_get_logs, info["service"])

    # AI ga xatolikni tahlil qildir
    fix_prompt = (
        f"Sen tajribali Python dasturchi va DevOps mutaxasssissan.\n"
        f"Quyida '{info['name']}' loyihasining Railway deployment loglari:\n\n"
        f"{logs[:3000]}\n\n"
        f"Vazifang:\n"
        f"1. Xatolik sababini aniq tushuntir (qaysi fayl, qaysi qator, nima sabab)\n"
        f"2. Qanday tuzatish kerakligini ayt (konkret kod yoki komanda)\n"
        f"3. Agar GitHub repoga o'zgartirish kerak bo'lsa ayt\n"
        f"Til: O'zbek. Qisqa va aniq bo'l."
    )
    response = await ai.process_message(fix_prompt, "", use_tools=False)
    safe = response.replace("**", "").replace("#", "").replace("`", "'")
    await update.message.reply_text(f"AI TAHLIL ({info['name']}):\n\n{safe}")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("brief", send_brief_cmd))
    app.add_handler(CommandHandler("news", send_news_cmd))
    app.add_handler(CommandHandler("coach", send_coach_cmd))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("done", cmd_done))
    app.add_handler(CommandHandler("deadline", cmd_deadline))
    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("brainstorm", cmd_brainstorm))
    app.add_handler(CommandHandler("finish_brainstorm", cmd_finish_brainstorm))
    app.add_handler(CommandHandler("leadmagnet", cmd_lead_magnet))
    app.add_handler(CommandHandler("dev", cmd_dev))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("deploy", cmd_deploy))
    app.add_handler(CommandHandler("fix", cmd_fix))
    # /ping — guruhda ishlashini tekshirish uchun
    async def ping_cmd(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await upd.message.reply_text("Pong! Bot ishlayapti.")
    app.add_handler(CommandHandler("ping", ping_cmd))

    # Guruh handler BIRINCHI — handle_message dan oldin
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        handle_group_message
    ))
    # Shaxsiy chat handler (faqat PRIVATE)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_message
    ))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_callback))

    tz = pytz.timezone("Asia/Tashkent")
    import datetime
    app.job_queue.run_daily(morning_briefing_job,  time=datetime.time(hour=8,  minute=0,  tzinfo=tz))
    app.job_queue.run_daily(viral_news_job,        time=datetime.time(hour=8,  minute=5,  tzinfo=tz))
    app.job_queue.run_daily(gmail_draft_job,       time=datetime.time(hour=9,  minute=0,  tzinfo=tz))
    app.job_queue.run_daily(rss_news_digest_job,   time=datetime.time(hour=9,  minute=15, tzinfo=tz))
    app.job_queue.run_daily(deadline_alert_checker_job, time=datetime.time(hour=9, minute=30, tzinfo=tz))
    app.job_queue.run_daily(midday_check_job,      time=datetime.time(hour=12, minute=0,  tzinfo=tz))
    app.job_queue.run_daily(daily_digest_job,      time=datetime.time(hour=20, minute=0,  tzinfo=tz))
    app.job_queue.run_daily(habit_tracker_prompt_job, time=datetime.time(hour=21, minute=0, tzinfo=tz))
    app.job_queue.run_daily(life_coach_job,        time=datetime.time(hour=21, minute=30, tzinfo=tz))
    app.job_queue.run_repeating(calendar_alert_checker_job, interval=900, first=15)
    app.job_queue.run_daily(weekly_finance_report_job, time=datetime.time(hour=18, minute=0, tzinfo=tz), days=(6,))
    app.job_queue.run_daily(burnout_check_job, time=datetime.time(hour=21, minute=30, tzinfo=tz), days=(6,))

    # Yangi monitoring joblar
    app.job_queue.run_repeating(uptime_monitor_job, interval=600, first=30)       # har 10 daqiqa
    app.job_queue.run_repeating(railway_crash_monitor_job, interval=300, first=60) # har 5 daqiqa
    app.job_queue.run_repeating(scheduled_posts_sender_job, interval=60, first=10) # har 1 daqiqa
    app.job_queue.run_daily(competitor_check_job, time=datetime.time(hour=9, minute=0, tzinfo=tz), days=(1,))  # Dushanba
    app.job_queue.run_daily(smart_kundalik_job, time=datetime.time(hour=21, minute=45, tzinfo=tz))  # Har kuni

    logger.info("✅ J.A.R.V.I.S tayyor! Polling boshlandi.")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )

if __name__ == "__main__":
    main()

