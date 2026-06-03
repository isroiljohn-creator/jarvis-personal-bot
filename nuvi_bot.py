#!/usr/bin/env python3
"""
Nuvi Jobs Bot — E'lonlarni qabul qilish, to'lovlar, admin tasdiqlashi va rejalashtirilgan navbat scheduler tizimi.
"""

import os
import sys
import logging
import asyncio
import datetime
import tempfile
import pytz
import re
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from telegram.constants import ParseMode

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database
from image_generator import generate_vacancy_cover
from vacancy_scraper import VacancyScraper
from ai import GeminiAI

# Logger sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("nuvi_bot")

# ──────────────────────── SOZLAMALAR ─────────────────────────

NUVI_BOT_TOKEN = os.environ.get("NUVI_BOT_TOKEN", "8713575188:AAERwI20zYqVdbIYaiLCUdXSNEjFAskf_rM")
OWNER_ID = int(os.environ.get("OWNER_TELEGRAM_ID", "1392501306"))
ADMIN_CHANNEL_ID = int(os.environ.get("NUVI_ADMIN_CHANNEL_ID", str(OWNER_ID)))
TARGET_CHANNEL = os.environ.get("NUVI_TARGET_CHANNEL", "-1003705561421")
PROVIDER_TOKEN = os.environ.get("PAYMENT_PROVIDER_TOKEN") # Click/Payme Telegram billing uchun

TG_API_ID = int(os.environ.get("TG_API_ID", "28124599"))
TG_API_HASH = os.environ.get("TG_API_HASH", "044479d6477a9daf554e660d3afce554")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

ai = GeminiAI(GEMINI_API_KEY)
vacancy_scraper: Optional[VacancyScraper] = None

async def get_tariff_price(tariff: str) -> int:
    """Tizimdagi tarif narxini bazadan oladi, bo'lmasa env/default qaytaradi."""
    key = f"tariff_{tariff}_price"
    price_str = await database.db_get_nuvi_setting(key)
    if price_str:
        try:
            return int(price_str)
        except ValueError:
            pass
    defaults = {
        "pro": 20000,
        "premium": 35000,
        "vip": 50000
    }
    return defaults.get(tariff, 20000)

async def get_vacancy_price() -> int:
    """Tizimdagi joriy e'lon narxini bazadan oladi, bo'lmasa env/default qaytaradi (Legacy fallback)."""
    return await get_tariff_price("pro")

async def get_card_details() -> str:
    """Karta ma'lumotlarini bazadan oladi, bo'lmasa env/default qaytaradi."""
    card = await database.db_get_nuvi_setting("vacancy_card_details")
    if card:
        return card
    return os.environ.get("NUVI_VACANCY_CARD_DETAILS", "8600 0000 0000 0000 (Nuvi Jobs)")

# Conversation holatlari
(
    ASK_SECTION,
    ASK_TITLE,
    ASK_EXPERIENCE,
    ASK_LOCATION,
    ASK_COMPANY,
    ASK_SALARY,
    ASK_CONTACT,
    ASK_WORKING_HOURS,
    ASK_REQUIREMENTS,
    ASK_SKILLS,
    ASK_BENEFITS,
    CONFIRM_PREVIEW,
    CHOOSE_TARIFF,
    CHOOSE_PAYMENT_METHOD,
    WAIT_MANUAL_RECEIPT,
) = range(15)

# Broadcast holatlari
(
    BROADCAST_ASK_MSG,
    BROADCAST_CONFIRM,
) = range(15, 17)

# Settings holatlari
(
    SETTING_ASK_PRICE,
    SETTING_ASK_CARD,
) = range(17, 19)

# ──────────────────────── YORDAMCHI FUNKSIYALAR ─────────────────────────

def clean_for_markdown(text: str) -> str:
    """Telegram Markdown uchun belgilarni tozalaydi."""
    if not text:
        return ""
    for ch in ("*", "`", "#"):
        text = text.replace(ch, "")
    return text

def escape_telegram_markdown(text: str) -> str:
    """Telegram Markdown uchun tagchiziqlar (_) ni escape qiladi, lekin URL va havolalarni buzmaydi."""
    if not text:
        return text
    # 1. URL'larni topib, vaqtinchalik placeholderlar bilan almashtiramiz
    urls = re.findall(r'https?://[^\s)]+', text)
    placeholders = {}
    for i, url in enumerate(urls):
        ph = f"URLPLACEHOLDER{i}"
        placeholders[ph] = url
        text = text.replace(url, ph)
        
    # 2. Qolgan matndagi barcha tagchiziqlarni escape qilamiz
    text = text.replace("_", "\\_")
    
    # 3. URL'larni asl holiga qaytaramiz
    for ph, url in placeholders.items():
        text = text.replace(ph, url)
        
    return text

async def check_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.message and update.message.text:
        txt = update.message.text.strip()
        if txt in ("🚫 Bekor qilish", "Vakansiyani bekor qilish"):
            await update.message.reply_text("E'lon berish bekor qilindi.", reply_markup=ReplyKeyboardRemove())
            await cmd_start(update, context)
            return True
    return False

def format_vacancy_text(data: dict) -> str:
    """Vakansiya ma'lumotlarini chiroyli shablonga soladi."""
    title = clean_for_markdown(data.get("title", ""))
    company = clean_for_markdown(data.get("company", ""))
    salary = clean_for_markdown(data.get("salary", ""))
    location = clean_for_markdown(data.get("location", ""))
    experience = clean_for_markdown(data.get("experience", ""))
    hours = clean_for_markdown(data.get("working_hours", ""))
    contact = clean_for_markdown(data.get("contact", ""))
    
    # Optional fields
    reqs = clean_for_markdown(data.get("requirements", ""))
    skills = clean_for_markdown(data.get("skills", ""))
    benefits = clean_for_markdown(data.get("benefits", ""))
    
    text = f"📌 *{title}*\n\n"
    text += f"🏢 *Firma:* {company}\n"
    text += f"💵 *Maosh:* {salary}\n"
    text += f"📍 *Lokatsiya:* {location}\n"
    
    if experience and experience.lower() != "shart emas" and experience.lower() != "➡️ shart emas":
        text += f"⬆️ *Tajriba:* {experience}\n"
        
    if hours and hours.lower() != "shart emas" and hours.lower() != "➡️ shart emas":
        text += f"⏱️ *Ish vaqti:* {hours}\n"
        
    # Formatting optional multi-line sections
    if reqs and reqs.lower() != "shart emas" and reqs.lower() != "➡️ shart emas":
        req_lines = "\n".join([f"— {line.strip()}" for line in reqs.split("\n") if line.strip()])
        text += f"\n📝 *Vazifalar:*\n{req_lines}\n"
        
    if skills and skills.lower() != "shart emas" and skills.lower() != "➡️ shart emas":
        skill_lines = "\n".join([f"— {line.strip()}" for line in skills.split("\n") if line.strip()])
        text += f"\n⚙️ *Talablar:*\n{skill_lines}\n"
        
    if benefits and benefits.lower() != "shart emas" and benefits.lower() != "➡️ shart emas":
        benefit_lines = "\n".join([f"— {line.strip()}" for line in benefits.split("\n") if line.strip()])
        text += f"\n🎁 *Taklif:*\n{benefit_lines}\n"
        
    text += f"\n📩 *Aloqa:* {contact}\n\n"
    text += f"[Nuvi Jobs](https://t.me/nuvi_jobs) - *ish va ishchi topishda yordam beramiz!*"
    return text

async def calculate_next_post_time(tariff: str) -> datetime.datetime:
    """E'lonlar orasida tarifga qarab interval bilan navbat hisoblaydi."""
    tz = pytz.timezone("Asia/Tashkent")
    now_tz = datetime.datetime.now(tz)
    
    if tariff == "vip":
        # VIP goes near-instantly (5 mins from now)
        return now_tz + datetime.timedelta(minutes=5)
        
    interval_hours = 1 if tariff == "premium" else 2
    
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT scheduled_for FROM nuvi_vacancies 
            WHERE status = 'approved' AND posted_at IS NULL 
            ORDER BY scheduled_for DESC 
            LIMIT 1
        """)
    
    # Agar kelajakda allaqachon rejalashtirilgan post bo'lsa, undan keyinga qo'yamiz
    if row and row["scheduled_for"]:
        base_time = row["scheduled_for"].astimezone(tz)
        if base_time > now_tz:
            next_time = base_time + datetime.timedelta(hours=interval_hours)
            # Agar keyingi vaqt 22:00 dan o'tib ketgan bo'lsa, ertasi kuni 09:00 ga o'tkazamiz
            if next_time.hour >= 22 or next_time.hour < 9:
                next_time = (next_time + datetime.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            return next_time
            
    # Agar navbat bo'sh bo'lsa
    if now_tz.hour < 9:
        scheduled_tz = now_tz.replace(hour=9, minute=0, second=0, microsecond=0)
    elif now_tz.hour >= 22:
        scheduled_tz = (now_tz + datetime.timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    else:
        scheduled_tz = now_tz
        
    return scheduled_tz

# ──────────────────────── FOYDALANUVCHI ZANJIRI (CONVERSATION) ─────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bot boshlanishi."""
    user = update.effective_user
    await database.db_upsert_nuvi_user(user.id, user.username, user.first_name)
    
    keyboard = [
        ["💼 E'lon berish"],
        ["📊 Mening e'lonlarim"],
        ["ℹ️ Bot haqida"],
    ]
    if user.id == OWNER_ID:
        keyboard.append(["⚙️ Admin panel"])
        
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    safe_name = clean_for_markdown(user.first_name)
    msg = (
        f"👋 *Assalomu alaykum, {safe_name}!* \n"
        f"🚀 *Nuvi Jobs* e'lon berish botiga xush kelibsiz!\n\n"
        f"💼 Bu yerda kanalda vakansiya e'lon qilish uchun *ariza topshirishingiz*, "
        f"💳 *to'lov qilishingiz* va ⏱ *navbat asosida* e'loningizni avtomatik chop etishingiz mumkin."
    )
    if update.callback_query:
        await update.callback_query.answer()
        # Clean inline buttons
        await update.callback_query.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END

async def cb_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Vakansiya yaratishni boshlash."""
    if update.callback_query:
        await update.callback_query.answer()
        message_func = update.callback_query.message.reply_text
    else:
        message_func = update.message.reply_text
        
    context.user_data.clear() # Avvalgi ma'lumotlarni tozalash
    
    keyboard = [
        ["💼 Doimiy ishchi kerak"],
        ["💻 Frilanser (Bir martalik ish)"],
        ["📄 Rezyume joylashtirish"],
        ["🔙 Orqaga"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await message_func(
        "Keling, e'loningizni shakllantiramiz.\n\n"
        "Bo'limni tanlang:",
        reply_markup=reply_markup
    )
    return ASK_SECTION

async def state_section_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    
    if text == "🔙 Orqaga":
        await update.message.reply_text("Bosh menyuga qaytildi.", reply_markup=ReplyKeyboardRemove())
        await cmd_start(update, context)
        return ConversationHandler.END
        
    sections = {
        "💼 Doimiy ishchi kerak": "doimiy",
        "💻 Frilanser (Bir martalik ish)": "frilans",
        "📄 Rezyume joylashtirish": "rezyume"
    }
    
    if text not in sections:
        await update.message.reply_text(
            "Iltimos, quyidagi tugmalardan birini tanlang yoki '🔙 Orqaga' tugmasini bosing:"
        )
        return ASK_SECTION
        
    context.user_data["section"] = sections[text]
    
    keyboard = [["🚫 Bekor qilish"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "❗ *E'tiborli bo'ling:* Siz kiritgan ma'lumotlar avtomatik ravishda chiroyli suratga joylanadi.\n\n"
        "Yo'nalishni kiriting (Masalan: *SMM mutaxassis*, *Grafik dizayner*):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    return ASK_TITLE

async def state_ask_experience(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Lavozim nomi bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return ASK_TITLE
    context.user_data["title"] = title
    
    keyboard = [
        ["👶 Junior"],
        ["🧑 Middle"],
        ["👨‍💻 Senior"],
        ["➡️ Shart emas"],
        ["🚫 Bekor qilish"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Ishchining tajribasini tanlang yoki qo'lda kiriting:",
        reply_markup=reply_markup
    )
    return ASK_EXPERIENCE

async def state_ask_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    exp = update.message.text.strip()
    context.user_data["experience"] = exp
    
    keyboard = [
        ["📍 Toshkent shahri"],
        ["💻 Masofaviy"],
        ["🚫 Bekor qilish"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Ofis manzilini kiriting:\n(Masalan: *Toshkent shahri* yoki *Masofaviy* deb yozing yoki tanlang):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    return ASK_LOCATION

async def state_ask_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    loc = update.message.text.strip()
    if not loc:
        await update.message.reply_text("Manzil bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return ASK_LOCATION
    context.user_data["location"] = loc
    
    keyboard = [["🚫 Bekor qilish"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Firma / Kompaniya nomini kiriting?",
        reply_markup=reply_markup
    )
    return ASK_COMPANY

async def state_ask_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    company = update.message.text.strip()
    if not company:
        await update.message.reply_text("Kompaniya nomi bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return ASK_COMPANY
    context.user_data["company"] = company
    
    keyboard = [
        ["💬 Suhbat asosida"],
        ["🎓 Amaliyotchi"],
        ["🚫 Bekor qilish"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Maoshni belgilang:\n(Masalan: *200 - 500 $* yoki *Suhbat asosida* deb tanlang/yozing):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    return ASK_SALARY

async def state_ask_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    salary = update.message.text.strip()
    if not salary:
        await update.message.reply_text("Maosh bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return ASK_SALARY
    context.user_data["salary"] = salary
    
    keyboard = [["🚫 Bekor qilish"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Aloqa vositasini kiriting:\n(Masalan: *@recruiter_name* yoki *+998901234567*):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    return ASK_CONTACT

async def state_ask_working_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    contact = update.message.text.strip()
    if not contact:
        await update.message.reply_text("Aloqa ma'lumotlari bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return ASK_CONTACT
    context.user_data["contact"] = contact
    
    keyboard = [
        ["➡️ Shart emas"],
        ["🚫 Bekor qilish"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Xodimning ishlash vaqtini kiriting:\n(Masalan: *09:00 - 18:00, 5/2* yoki *➡️ Shart emas*):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    return ASK_WORKING_HOURS

async def state_ask_requirements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    hours = update.message.text.strip()
    context.user_data["working_hours"] = hours
    
    keyboard = [
        ["➡️ Shart emas"],
        ["🚫 Bekor qilish"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Xodimning vazifalari nimalar?\n(Har birini yangi qatordan yozishingiz mumkin yoki *➡️ Shart emas* tugmasini bosing):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    return ASK_REQUIREMENTS

async def state_ask_skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    reqs = update.message.text.strip()
    context.user_data["requirements"] = reqs
    
    keyboard = [
        ["➡️ Shart emas"],
        ["🚫 Bekor qilish"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Xodimdan qanday bilimlar talab etiladi?\n(Masalan: *Photoshop, Illustrator* yoki *➡️ Shart emas*):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    return ASK_SKILLS

async def state_ask_benefits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    skills = update.message.text.strip()
    context.user_data["skills"] = skills
    
    keyboard = [
        ["➡️ Shart emas"],
        ["🚫 Bekor qilish"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Xodimga nimalar taklif etiladi?\n(Masalan: *Shinam ofis, bepul tushlik* yoki *➡️ Shart emas*):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
    return ASK_BENEFITS

async def state_generate_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    benefits = update.message.text.strip()
    context.user_data["benefits"] = benefits
    
    waiting_msg = await update.message.reply_text("⏳ Oblojka va e'lon matni tayyorlanmoqda, iltimos kuting...")
    
    formatted_text = format_vacancy_text(context.user_data)
    context.user_data["formatted_text"] = formatted_text
    
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"vacancy_preview_{update.effective_user.id}.png")
    
    img_success = generate_vacancy_cover(
        position=context.user_data["title"],
        company=context.user_data["company"],
        salary=context.user_data["salary"],
        output_path=temp_path
    )
    
    await waiting_msg.delete()
    
    keyboard = [
        ["✅ Ha"],
        ["❌ Yo'q"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    msg_text = (
        f"Vakansiya e'loni kanalda quyidagicha ko'rinadi:\n\n"
        f"{escape_telegram_markdown(formatted_text)}\n\n"
        f"Barcha ma'lumotlar to'g'rimi?\nHa yoki yoq tugmasini tanlang 👇"
    )
    
    if img_success and os.path.exists(temp_path):
        with open(temp_path, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=msg_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        try:
            os.unlink(temp_path)
        except:
            pass
    else:
        await update.message.reply_text(
            msg_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
    return CONFIRM_PREVIEW

async def state_confirm_preview_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    text = update.message.text.strip()
    if text == "✅ Ha":
        price_pro = await get_tariff_price("pro")
        price_premium = await get_tariff_price("premium")
        price_vip = await get_tariff_price("vip")
        
        msg = (
            f"Iltimos, e'lon joylashtirish tarifini tanlang:\n\n"
            f"🔹 *Pro* - Standard kanalga joylash: *{price_pro:,}* so'm\n"
            f"🔸 *Premium* - Tezlashtirilgan navbat va maxsus format: *{price_premium:,}* so'm\n"
            f"🚀 *VIP* - Birinchi navbatda joylash + 24 soatga pinned qilish: *{price_vip:,}* so'm"
        )
        keyboard = [
            ["🔹 Pro"],
            ["🔸 Premium"],
            ["🚀 VIP"],
            ["🚫 Bekor qilish"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        return CHOOSE_TARIFF
    else:
        await update.message.reply_text("E'lon bekor qilindi.", reply_markup=ReplyKeyboardRemove())
        await cmd_start(update, context)
        return ConversationHandler.END

async def state_choose_tariff_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    text = update.message.text.strip()
    tariff_map = {
        "🔹 Pro": "pro",
        "🔸 Premium": "premium",
        "🚀 VIP": "vip"
    }
    
    if text not in tariff_map:
        await update.message.reply_text("Iltimos, tariflardan birini tanlang:")
        return CHOOSE_TARIFF
        
    tariff = tariff_map[text]
    context.user_data["tariff"] = tariff
    
    vacancy_id = await database.db_create_nuvi_vacancy(
        user_id=update.effective_user.id,
        title=context.user_data["title"],
        company=context.user_data["company"],
        salary=context.user_data["salary"],
        location=context.user_data["location"],
        working_hours=context.user_data["working_hours"],
        requirements=context.user_data["requirements"],
        skills=context.user_data.get("skills", ""),
        benefits=context.user_data["benefits"],
        contact=context.user_data["contact"],
        formatted_text=context.user_data["formatted_text"],
        tariff=tariff
    )
    context.user_data["vacancy_id"] = vacancy_id
    
    price = await get_tariff_price(tariff)
    keyboard = []
    if PROVIDER_TOKEN:
        keyboard.append(["💳 Telegram orqali to'lov (Click/Payme)"])
    keyboard.append(["📎 Karta orqali to'lov (Chek yuborish)"])
    keyboard.append(["🚫 Bekor qilish"])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    msg = (
        f"Vakansiya qabul qilindi!\n\n"
        f"Tanlangan tarif: *{text}*\n"
        f"To'lov summasi: **{price:,} so'm**.\n\n"
        f"Iltimos, to'lov usulini tanlang:"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    return CHOOSE_PAYMENT_METHOD

async def state_payment_method_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    text = update.message.text.strip()
    vac_id = context.user_data.get("vacancy_id")
    tariff = context.user_data.get("tariff", "pro")
    price = await get_tariff_price(tariff)
    
    if text == "💳 Telegram orqali to'lov (Click/Payme)" and PROVIDER_TOKEN:
        title = f"Vakansiya e'loni #{vac_id}"
        description = f"Nuvi Jobs kanalida vakansiya e'lonini joylash to'lovi (Tarif: {tariff.upper()})."
        payload = f"vacancy_payment_{vac_id}"
        currency = "UZS"
        prices = [LabeledPrice("Vakansiya e'loni", price * 100)]
        
        await database.db_update_nuvi_vacancy(vac_id, status="pending_payment", payment_method="telegram_billing")
        
        await update.message.reply_text("To'lov hisobi tayyorlanmoqda, iltimos kuting...", reply_markup=ReplyKeyboardRemove())
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title=title,
            description=description,
            payload=payload,
            provider_token=PROVIDER_TOKEN,
            currency=currency,
            prices=prices,
            start_parameter=f"pay_{vac_id}"
        )
        return ConversationHandler.END
        
    elif text == "📎 Karta orqali to'lov (Chek yuborish)":
        card = await get_card_details()
        await database.db_update_nuvi_vacancy(vac_id, status="pending_payment", payment_method="card_manual")
        
        msg = (
            f"💳 **Karta orqali to'lov:**\n\n"
            f"Karta: `{card}`\n"
            f"Summa: **{price:,} so'm**\n\n"
            f"To'lovni amalga oshirganingizdan so'ng, to'lov chekini (kvitansiya) rasm formatida shu yerga yuboring:"
        )
        keyboard = [["🚫 Bekor qilish"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        return WAIT_MANUAL_RECEIPT
    else:
        await update.message.reply_text("Iltimos, to'lov usullaridan birini tanlang:")
        return CHOOSE_PAYMENT_METHOD

async def state_manual_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    photo = update.message.photo
    if not photo:
        await update.message.reply_text("Iltimos, to'lov chekini faqat Rasm shaklida yuboring:")
        return WAIT_MANUAL_RECEIPT
        
    file_id = photo[-1].file_id
    vac_id = context.user_data.get("vacancy_id")
    
    await database.db_update_nuvi_vacancy(
        vac_id,
        payment_status="manual_pending",
        payment_receipt=file_id,
        status="pending_approval"
    )
    
    await update.message.reply_text(
        "Rahmat! To'lov cheki qabul qilindi. Admin tekshiruvidan so'ng e'loningiz rejalashtiriladi.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await cmd_start(update, context)
    
    await send_vacancy_to_admin(context.bot, vac_id)
    return ConversationHandler.END

# ──────────────────────── PRECHECKOUT VA SUCCESSFUL PAYMENT ─────────────────────────

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram payment precheckout tekshiruvi."""
    query = update.pre_checkout_query
    # Hamma narsa to'g'ri bo'lsa ok qaytaramiz
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram billing orqali to'lov muvaffaqiyatli o'tganda."""
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    # Payload format: vacancy_payment_ID
    vac_id = int(payload.split("_")[-1])
    
    # Bazada statusni yangilaymiz
    await database.db_update_nuvi_vacancy(
        vac_id,
        status="pending_approval",
        payment_status="paid"
    )
    
    await update.message.reply_text(
        "To'lovingiz muvaffaqiyatli qabul qilindi! Vakansiya tasdiqlash uchun adminga yuborildi."
    )
    
    # Adminga tasdiqlash uchun yuborish
    await send_vacancy_to_admin(update.get_bot(), vac_id)

# ──────────────────────── ADMIN TASDIQLASH TIZIMI ─────────────────────────

async def send_vacancy_to_admin(bot, vacancy_id: int):
    """Admin kanaliga arizani inline tugmalar bilan yuboradi."""
    vac = await database.db_get_nuvi_vacancy(vacancy_id)
    if not vac:
        return
        
    title = vac["title"]
    company = vac["company"]
    salary = vac["salary"]
    method = vac["payment_method"]
    p_status = vac["payment_status"]
    tariff = vac.get("tariff", "pro")
    
    tariff_labels = {"pro": "Pro", "premium": "Premium", "vip": "VIP"}
    tariff_desc = tariff_labels.get(tariff, tariff.upper())
    
    # Admin xabari matni
    msg = (
        f"🔔 **YANGI ARIZA TUSHDI**\n\n"
        f"🆔 Ariza ID: #{vacancy_id}\n"
        f"📌 Lavozim: {title}\n"
        f"🏢 Firma: {company}\n"
        f"💵 Maosh: {salary}\n"
        f"🚀 Tarif: *{tariff_desc}*\n"
        f"💳 To'lov turi: {method}\n"
        f"📈 To'lov holati: {p_status}\n\n"
        f"**Matn:**\n{vac['formatted_text']}"
    )
    
    # Keyboard
    keyboard = []
    if p_status == "manual_pending":
        keyboard.append([InlineKeyboardButton("💳 To'lovni tasdiqlash", callback_data=f"admin_payconfirm_{vacancy_id}")])
    else:
        keyboard.append([InlineKeyboardButton("✅ Vakansiyani Tasdiqlash", callback_data=f"admin_approve_{vacancy_id}")])
    
    keyboard.append([
        InlineKeyboardButton("❌ Rad etish", callback_data=f"admin_rejectmenu_{vacancy_id}")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Agar kvitansiya rasm bo'lsa rasm bilan yuboramiz
    if vac["payment_receipt"]:
        await bot.send_photo(
            chat_id=ADMIN_CHANNEL_ID,
            photo=vac["payment_receipt"],
            caption=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        await bot.send_message(
            chat_id=ADMIN_CHANNEL_ID,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

async def admin_buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin inline tugmalarni bosganda."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    # admin_payconfirm_ID, admin_approve_ID, admin_rejectmenu_ID, admin_reject_ID_REASON
    
    if data.startswith("admin_payconfirm_"):
        vac_id = int(data.split("_")[-1])
        await database.db_update_nuvi_vacancy(vac_id, payment_status="paid")
        
        # Tugmalarni almashtiramiz: endi vakansiyani tasdiqlashi mumkin
        keyboard = [
            [InlineKeyboardButton("✅ Vakansiyani Tasdiqlash", callback_data=f"admin_approve_{vac_id}")],
            [InlineKeyboardButton("❌ Rad etish", callback_data=f"admin_rejectmenu_{vac_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        vac = await database.db_get_nuvi_vacancy(vac_id)
        msg = query.message.caption if query.message.photo else query.message.text
        msg = msg.replace("📈 To'lov holati: manual_pending", "📈 To'lov holati: paid (Qabul qilindi)")
        
        if query.message.photo:
            await query.message.edit_caption(caption=msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.edit_text(text=msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            
        # Foydalanuvchiga to'lov qabul qilingani haqida xabar beramiz
        await context.bot.send_message(
            chat_id=vac["user_id"],
            text=f"💳 Sizning e'lon #{vac_id} bo'yicha to'lovingiz admin tomonidan tasdiqlandi! Vakansiya ko'rib chiqilmoqda."
        )
        
    elif data.startswith("admin_approve_"):
        vac_id = int(data.split("_")[-1])
        vac = await database.db_get_nuvi_vacancy(vac_id)
        tariff = vac.get("tariff", "pro") if vac else "pro"
        scheduled_for = await calculate_next_post_time(tariff)
        
        # Bazani yangilaymiz
        await database.db_update_nuvi_vacancy(vac_id, status="approved", scheduled_for=scheduled_for)
        
        # Tashkent vaqti formatida ko'rsatish
        tz = pytz.timezone("Asia/Tashkent")
        scheduled_for_tz = scheduled_for.astimezone(tz)
        time_str = scheduled_for_tz.strftime("%Y-%m-%d %H:%M")
        
        msg = query.message.caption if query.message.photo else query.message.text
        msg += f"\n\n🟢 **TASDIQLANDI**\n⏰ Navbat vaqti: {time_str}"
        
        if query.message.photo:
            await query.message.edit_caption(caption=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.edit_text(text=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
            
        # Foydalanuvchini xabardor qilish
        if vac:
            await context.bot.send_message(
                chat_id=vac["user_id"],
                text=f"✅ Sizning e'lon #{vac_id} tasdiqlandi!\n⏰ Rejalashtirilgan chop etish vaqti: **{time_str}** (Toshkent vaqti bilan)."
            )
        
    elif data.startswith("admin_rejectmenu_"):
        vac_id = int(data.split("_")[-1])
        # Rad etish sabablari
        keyboard = [
            [InlineKeyboardButton("❌ Sifatsiz ma'lumot", callback_data=f"admin_rej_{vac_id}_sifatsiz")],
            [InlineKeyboardButton("❌ Boshqa kanallar reklamasi", callback_data=f"admin_rej_{vac_id}_reklama")],
            [InlineKeyboardButton("❌ Boshqa sabab", callback_data=f"admin_rej_{vac_id}_boshqa")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query.message.photo:
            await query.message.edit_caption(caption=query.message.caption, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.edit_text(text=query.message.text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            
    elif data.startswith("admin_rej_"):
        # admin_rej_ID_REASON
        parts = data.split("_")
        vac_id = int(parts[3])
        reason_code = parts[4]
        
        reasons = {
            "sifatsiz": "Vakansiya tafsilotlari yetarli emas yoki sifatsiz ma'lumot kiritilgan.",
            "reklama": "Boshqa raqobatchi guruh/kanallar havolasi va taqiqlangan reklamalar mavjud.",
            "boshqa": "Ariza talablarga javob bermaydi."
        }
        reason = reasons.get(reason_code, "Ariza talablarga javob bermaydi.")
        
        # Bazani yangilash
        await database.db_update_nuvi_vacancy(vac_id, status="rejected", rejection_reason=reason)
        
        msg = query.message.caption if query.message.photo else query.message.text
        msg += f"\n\n🔴 **RAD ETILDI**\n⚠️ Sababi: {reason}"
        
        if query.message.photo:
            await query.message.edit_caption(caption=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.edit_text(text=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
            
        # Foydalanuvchini xabardor qilish
        vac = await database.db_get_nuvi_vacancy(vac_id)
        await context.bot.send_message(
            chat_id=vac["user_id"],
            text=f"❌ Sizning e'lon #{vac_id} rad etildi.\n⚠️ Sababi: **{reason}**"
        )

# ──────────────────────── SCHEDULER: NAVBATDAGI POSTLARNI JOYLASHTIRISH ─────────────────────────

async def nuvi_auto_post_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har 10 daqiqada ishlaydi: navbati kelgan vakansiyani kanalga chop etadi."""
    try:
        vac = await database.db_get_next_scheduled_vacancy()
        if not vac:
            return
            
        vac_id = vac["id"]
        logger.info(f"Navbatdagi vakansiya aniqlandi: #{vac_id}. Kanalga joylanmoqda...")
        
        # Rasm yaratish
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"vacancy_post_{vac_id}.png")
        
        img_success = generate_vacancy_cover(
            position=vac["title"],
            company=vac["company"],
            salary=vac["salary"],
            output_path=temp_path
        )
        
        caption_text = escape_telegram_markdown(vac["formatted_text"])
        
        post_success = False
        message_id = None
        
        if img_success and os.path.exists(temp_path):
            try:
                with open(temp_path, "rb") as photo:
                    post_msg = await context.bot.send_photo(
                        chat_id=TARGET_CHANNEL,
                        photo=photo,
                        caption=caption_text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    post_success = True
                    message_id = post_msg.message_id
            except Exception as e:
                logger.error(f"Failed to send post with photo: {e}. Trying text only.")
                
            try:
                os.unlink(temp_path)
            except:
                pass
                
        if not post_success:
            # Rasmsiz chop etish fallback
            try:
                post_msg = await context.bot.send_message(
                    chat_id=TARGET_CHANNEL,
                    text=caption_text,
                    parse_mode=ParseMode.MARKDOWN
                )
                post_success = True
                message_id = post_msg.message_id
            except Exception as e:
                logger.error(f"Text only post failed: {e}")
                
        if post_success:
            # Bazani yangilaymiz
            await database.db_update_nuvi_vacancy(
                vac_id,
                status="posted",
                posted_at=datetime.datetime.now(datetime.timezone.utc)
            )
            logger.info(f"✅ Vakansiya #{vac_id} muvaffaqiyatli post qilindi (Msg ID: {message_id})")
            
            # Pinned message for VIP tariff
            if vac.get("tariff") == "vip":
                try:
                    await context.bot.pin_chat_message(
                        chat_id=TARGET_CHANNEL,
                        message_id=message_id,
                        disable_notification=False
                    )
                    logger.info(f"📌 VIP Vakansiya #{vac_id} kanalda pin qilindi (Msg ID: {message_id})")
                except Exception as pin_err:
                    logger.error(f"Failed to pin VIP vacancy #{vac_id}: {pin_err}")
            
            # Foydalanuvchini xabardor qilish va havolani yuborish
            post_link = f"https://t.me/{TARGET_CHANNEL.replace('@', '')}/{message_id}"
            await context.bot.send_message(
                chat_id=vac["user_id"],
                text=(
                    f"🎉 Xushxabar! Sizning e'lon #{vac_id} kanalda muvaffaqiyatli chop etildi!\n\n"
                    f"🔗 E'lon havolasi: [Nuvi Jobs Post]({post_link})"
                ),
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        logger.error(f"nuvi_auto_post_job error: {e}")

# ──────────────────────── ADMIN BUYRUQLARI (STATS / BROADCAST) ─────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin menyusi."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return
        
    from telegram import WebAppInfo
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "jarvis-personal-bot-production.up.railway.app"
    web_app_url = f"https://{domain}/nuvi-stats"
    
    keyboard = [
        [InlineKeyboardButton("📊 Mini App (Statistika)", web_app=WebAppInfo(url=web_app_url))],
        [InlineKeyboardButton("📊 Tizim Statistikasi (Matnli)", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Yangi Rassilka", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text("Nuvi Jobs Bot - Admin Boshqaruv Paneli:", reply_markup=reply_markup)
    else:
        # If triggered from back query
        pass

async def cb_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Statistika ko'rsatish."""
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("Ruxsat yo'q.")
        return
    await query.answer()
    
    stats = await database.db_get_nuvi_stats()
    msg = (
        f"📊 **NUVI JOBS BOT STATISTIKASI**\n\n"
        f"👥 Foydalanuvchilar: **{stats.get('total_users', 0)}**\n"
        f"📝 Jami arizalar: **{stats.get('total_vacancies', 0)}**\n"
        f"🟢 Tasdiqlangan (posted): **{stats.get('total_posted', 0)}**\n"
        f"⏳ Kutilmoqda (pending): **{stats.get('total_pending', 0)}**\n"
        f"⏰ Rejalashtirilgan (scheduled): **{stats.get('total_scheduled', 0)}**\n"
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def cb_admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin menyusiga qaytish."""
    query = update.callback_query
    await query.answer()
    from telegram import WebAppInfo
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "jarvis-personal-bot-production.up.railway.app"
    web_app_url = f"https://{domain}/nuvi-stats"
    
    keyboard = [
        [InlineKeyboardButton("📊 Mini App (Statistika)", web_app=WebAppInfo(url=web_app_url))],
        [InlineKeyboardButton("📊 Tizim Statistikasi (Matnli)", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Yangi Rassilka", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("Nuvi Jobs Bot - Admin Boshqaruv Paneli:", reply_markup=reply_markup)

async def cb_admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin sozlamalari menyusi."""
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("Ruxsat yo'q.")
        return ConversationHandler.END
    await query.answer()
    
    price_pro = await get_tariff_price("pro")
    price_premium = await get_tariff_price("premium")
    price_vip = await get_tariff_price("vip")
    card = await get_card_details()
    
    msg = (
        f"⚙️ **TIZIM SOZLAMALARI**\n\n"
        f"💵 **Tarif narxlari:**\n"
        f"🔹 Pro: **{price_pro:,} so'm**\n"
        f"🔸 Premium: **{price_premium:,} so'm**\n"
        f"🚀 VIP: **{price_vip:,} so'm**\n\n"
        f"💳 Karta ma'lumotlari: `{card}`\n\n"
        f"O'zgartirmoqchi bo'lgan sozlamani tanlang:"
    )
    keyboard = [
        [InlineKeyboardButton("🔹 Pro narxini o'zgartirish", callback_data="set_price_pro")],
        [InlineKeyboardButton("🔸 Premium narxini o'zgartirish", callback_data="set_price_premium")],
        [InlineKeyboardButton("🚀 VIP narxini o'zgartirish", callback_data="set_price_vip")],
        [InlineKeyboardButton("💳 Karta ma'lumotlarini o'zgartirish", callback_data="set_card")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END

async def cb_set_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("Ruxsat yo'q.")
        return ConversationHandler.END
    await query.answer()
    
    match = re.match(r"^set_price_(pro|premium|vip)$", query.data)
    if not match:
        await query.message.reply_text("Xatolik yuz berdi.")
        return ConversationHandler.END
    tariff = match.group(1)
    context.user_data["changing_tariff"] = tariff
    
    tariff_labels = {"pro": "Pro", "premium": "Premium", "vip": "VIP"}
    label = tariff_labels.get(tariff, tariff)
    await query.message.reply_text(f"*{label}* tarifi uchun yangi narxni kiriting (faqat raqamlarda, masalan: 35000):", parse_mode=ParseMode.MARKDOWN)
    return SETTING_ASK_PRICE

async def state_setting_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    tariff = context.user_data.get("changing_tariff", "pro")
    tariff_labels = {"pro": "Pro", "premium": "Premium", "vip": "VIP"}
    label = tariff_labels.get(tariff, tariff)
    try:
        price = int(text)
        await database.db_set_nuvi_setting(f"tariff_{tariff}_price", str(price))
        await update.message.reply_text(f"✅ *{label}* tarifi narxi muvaffaqiyatli o'zgartirildi: **{price:,} so'm**", parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        await update.message.reply_text(f"❌ Xato! Iltimos faqat raqam kiriting (masalan: 35000) for *{label}*:")
        return SETTING_ASK_PRICE
    return ConversationHandler.END

async def cb_set_card_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("Ruxsat yo'q.")
        return ConversationHandler.END
    await query.answer()
    await query.message.reply_text("Yangi karta ma'lumotlarini kiriting (masalan: 8600 0000 0000 0000 Nuvi Jobs MCH):")
    return SETTING_ASK_CARD

async def state_setting_card_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    card = update.message.text.strip()
    await database.db_set_nuvi_setting("vacancy_card_details", card)
    await update.message.reply_text(f"✅ Karta ma'lumotlari muvaffaqiyatli o'zgartirildi:\n`{card}`", parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END

# ─── BROADCAST (RASSILKA) CONVERSATION FLOW ───

async def cb_admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Rassilka xabarini so'rash."""
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("Ruxsat yo'q.")
        return ConversationHandler.END
    await query.answer()
    
    await query.message.reply_text(
        "Rassilka xabari matnini kiriting (rasm yoki tugma qo'shishingiz ham mumkin):"
    )
    return BROADCAST_ASK_MSG

async def state_broadcast_ask_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Matn olindi, tasdiqlash so'rash."""
    msg = update.message
    context.user_data["broadcast_msg"] = msg
    
    keyboard = [
        [InlineKeyboardButton("✅ Yuborish", callback_data="broadcast_confirm")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="broadcast_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Xabarni barcha bot foydalanuvchilariga yuborishni tasdiqlaysizmi?",
        reply_markup=reply_markup
    )
    return BROADCAST_CONFIRM

async def cb_broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Rassilkani boshlash."""
    query = update.callback_query
    await query.answer()
    
    msg = context.user_data.get("broadcast_msg")
    users = await database.db_get_all_nuvi_users()
    
    if not users:
        await query.message.reply_text("Tizimda foydalanuvchilar mavjud emas.")
        return ConversationHandler.END
        
    await query.message.reply_text(f"⏳ Rassilka boshlandi. Jami: {len(users)} foydalanuvchi...")
    
    success = 0
    failed = 0
    for u in users:
        try:
            # Xabarni nusxalash (copy) orqali yuboramiz
            await context.bot.copy_message(
                chat_id=u["user_id"],
                from_chat_id=msg.chat_id,
                message_id=msg.message_id
            )
            success += 1
            await asyncio.sleep(0.05) # Rate limiting
        except Exception:
            failed += 1
            
    await query.message.reply_text(
        f"📢 Rassilka yakunlandi!\n✅ Muvaffaqiyatli: **{success}**\n❌ Muammo: **{failed}**",
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END

async def cb_broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Rassilkani bekor qilish."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Rassilka bekor qilindi.")
    return ConversationHandler.END

# ──────────────────────── GENERAL CALLBACK HANDLER (MENU / INFO) ─────────────────────────

async def cb_my_vacancies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mening e'lonlarim ro'yxati."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    vacs = await database.db_get_nuvi_vacancies_by_user(user_id)
    
    if not vacs:
        msg = "ℹ️ Sizda hali e'lonlar mavjud emas."
    else:
        msg = "📊 **Sizning arizalaringiz holati:**\n\n"
        for v in vacs[:10]: # Oxirgi 10 tasini ko'rsatish
            p_status = v["payment_status"]
            status = v["status"]
            
            status_map = {
                "draft": "Qoralama",
                "pending_payment": "To'lov kutilmoqda",
                "pending_approval": "Admindan tasdiq kutilmoqda",
                "approved": "Tasdiqlangan / Navbatda",
                "rejected": "Rad etilgan",
                "posted": "Kanalga joylangan ✅"
            }
            status_desc = status_map.get(status, status)
            
            msg += (
                f"🆔 Ariza #{v['id']}\n"
                f"📌 Lavozim: **{v['title']}**\n"
                f"📈 Holati: *{status_desc}*\n"
                f"💳 To'lov holati: *{p_status}*\n"
            )
            if v["rejection_reason"]:
                msg += f"⚠️ Sabab: {v['rejection_reason']}\n"
            msg += "──────────────────\n"
            
    keyboard = [[InlineKeyboardButton("⬅️ Menyuga qaytish", callback_data="nuvi_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def cb_bot_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot haqida ma'lumot (Legacy callback query support)."""
    query = update.callback_query
    await query.answer()
    
    price_pro = await get_tariff_price("pro")
    price_premium = await get_tariff_price("premium")
    price_vip = await get_tariff_price("vip")
    
    msg = (
        f"ℹ️ **Nuvi Jobs Bot haqida:**\n\n"
        f"Ushbu bot orqali `@nuvi_jobs` kanaliga osongina vakansiya e'lonlarini joylashingiz mumkin.\n\n"
        f"💰 **E'lon joylash tariflari:**\n"
        f"🔹 Pro: **{price_pro:,} so'm**\n"
        f"🔸 Premium: **{price_premium:,} so'm**\n"
        f"🚀 VIP: **{price_vip:,} so'm**\n\n"
        f"**Jarayon ketma-ketligi:**\n"
        f"1. So'rovnomadagi savollarga javob berasiz.\n"
        f"2. E'lon namunasi (oblojka surat va matn) sizga ko'rsatiladi.\n"
        f"3. Tarif va to'lov usulini tanlaysiz.\n"
        f"4. Admin tekshiruvdan o'tkazgandan keyin ariza tasdiqlanadi va navbatga qo'yiladi.\n"
        f"5. Navbati kelganda e'loningiz avtomatik kanalga chiqadi va sizga xabar keladi."
    )
    keyboard = [[InlineKeyboardButton("⬅️ Menyuga qaytish", callback_data="nuvi_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# ─── REPLY KEYBOARD HELPERS FOR PUBLIC MENUS ───

async def cb_my_vacancies_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mening e'lonlarim ro'yxati (Reply keyboard uchun)."""
    user_id = update.effective_user.id
    vacs = await database.db_get_nuvi_vacancies_by_user(user_id)
    
    if not vacs:
        msg = "ℹ️ Sizda hali e'lonlar muzokaralari mavjud emas."
    else:
        msg = "📊 *Sizning arizalaringiz holati:*\n\n"
        for v in vacs[:10]:
            p_status = v["payment_status"]
            status = v["status"]
            tariff = v.get("tariff", "pro")
            
            status_map = {
                "draft": "Qoralama",
                "pending_payment": "To'lov kutilmoqda",
                "pending_approval": "Admindan tasdiq kutilmoqda",
                "approved": "Tasdiqlangan / Navbatda",
                "rejected": "Rad etilgan",
                "posted": "Kanalga joylangan ✅"
            }
            status_desc = status_map.get(status, status)
            
            tariff_map = {"pro": "Pro", "premium": "Premium", "vip": "VIP"}
            t_desc = tariff_map.get(tariff, "Pro")
            
            msg += (
                f"🆔 Ariza #{v['id']} (*{t_desc}*)\n"
                f"📌 Lavozim: *{v['title']}*\n"
                f"🏢 Firma: *{v['company']}*\n"
                f"📈 Holati: *{status_desc}*\n"
                f"💳 To'lov: *{p_status}*\n"
            )
            if v["rejection_reason"]:
                msg += f"⚠️ Sabab: {v['rejection_reason']}\n"
            msg += "──────────────────\n"
            
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cb_bot_info_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot haqida ma'lumot (Reply keyboard uchun)."""
    price_pro = await get_tariff_price("pro")
    price_premium = await get_tariff_price("premium")
    price_vip = await get_tariff_price("vip")
    
    msg = (
        f"ℹ️ *Nuvi Jobs Bot haqida:*\n\n"
        f"Ushbu bot orqali `@nuvi_jobs` kanaliga osongina vakansiya e'lonlarini joylashingiz mumkin.\n\n"
        f"💰 *E'lon joylash tariflari:*\n"
        f"🔹 *Pro:* {price_pro:,} so'm\n"
        f"🔸 *Premium:* {price_premium:,} so'm\n"
        f"🚀 *VIP:* {price_vip:,} so'm\n\n"
        f"*Jarayon ketma-ketligi:*\n"
        f"1. Bo'lim va lavozimni tanlaysiz.\n"
        f"2. So'rovnomadagi savollarga javob berasiz.\n"
        f"3. E'lon namunasi (surat va matn) ko'rsatiladi.\n"
        f"4. Tarif va to'lov usulini tanlaysiz.\n"
        f"5. Admin tekshiruvidan o'tgach, e'loningiz navbat bo'yicha avtomatik kanalga joylanadi."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ──────────────────────── BOSHQA / ERROR HANDLERS ─────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hozirgi suhbatni bekor qilish."""
    await update.message.reply_text("Suhbat bekor qilindi.", reply_markup=ReplyKeyboardRemove())
    await cmd_start(update, context)
    return ConversationHandler.END

# ──────────────────────── VACANCY SCRAPER SYSTEM ─────────────────────────

async def post_init(application: Application) -> None:
    """Initialize background services for Nuvi Jobs Bot."""
    global vacancy_scraper
    vac_session = os.environ.get("VACANCY_TG_SESSION_STRING") or os.environ.get("TG_SESSION_STRING")
    vac_api_id = os.environ.get("VACANCY_TG_API_ID") or os.environ.get("TG_API_ID") or "28124599"
    vac_api_hash = os.environ.get("VACANCY_TG_API_HASH") or os.environ.get("TG_API_HASH") or "044479d6477a9daf554e660d3afce554"
    
    if vac_session:
        try:
            logger.info("📱 Orqa fonda Vacancy Scraperni ishga tushirish boshlanmoqda...")
            vs = VacancyScraper(api_id=int(vac_api_id), api_hash=vac_api_hash, session_string=vac_session)
            await vs.connect()
            vacancy_scraper = vs
            logger.info("✅ Vacancy Scraper muvaffaqiyatli ulandi va sozlandi.")
        except Exception as e:
            logger.warning(f"⚠️ Vacancy Scraper ulana olmadi: {e}")
            vacancy_scraper = None
    else:
        logger.warning("⚠️ No TG_SESSION_STRING or VACANCY_TG_SESSION_STRING found. Scraper disabled.")


async def format_vacancy_with_ai(raw_text: str) -> str:
    """Vakansiya matnini Gemini yordamida shablonga soladi."""
    default_template = """
📌 *[Lavozim nomi]*

🏢 *Firma:* [Kompaniya nomi]
💵 *Maosh:* [Ish haqi miqdori]
📍 *Lokatsiya:* [Shahar/Masofaviy]
⏱️ *Ish vaqti:* [Ish grafigi/Vaqti]

📝 *Talablar:*
— [Talab 1]
— [Talab 2]
— ...

🎁 *Taklif:*
— [Taklif 1]
— [Taklif 2]
— ...

📩 *Aloqa:* [Telegram username yoki telefon]

[Nuvi Jobs](https://t.me/nuvi_jobs) - *ish va ishchi topishda yordam beramiz!*
"""
    custom_template = os.environ.get("VACANCY_TEMPLATE")
    template = custom_template if custom_template else default_template

    system_prompt = f"""
Siz professional HR assistentisiz. Vazifangiz quyidagi vakansiya matnini o'rganib chiqib, uni chiroyli, tartibli va imloviy xatolarsiz quyidagi shablon ko'rinishiga keltirishdir:

{template}

MUHIM QOIDALAR:
1. Matndagi asosiy so'zlar: Firma:, Maosh:, Lokatsiya:, Ish vaqti:, Talablar:, Taklif:, Aloqa: va bizning slogan: Nuvi Jobs - ish va ishchi topishda yordam beramiz! qismlari faqat yulduzcha (*) belgisi bilan o'ralib bold bo'lishi kerak.
2. Har bir ma'lumot sarlavhalari (masalan, Firma:, Maosh:) va ularning qiymatlari (masalan, Adjaster .uz jamoasi, 3 000 000 so'm) chiroyli tarzda taqdim etilsin.
3. Aloqa va kontakt ma'lumotlarini (nomzod murojaat qilishi kerak bo'lgan shaxsiy profil yoki telefon raqami) albatta saqlab qoling.
4. MUHIM TAQIQLAR: Hech qachon telegram bot foydalanuvchi nomini (masalan, oxiri '_bot' bilan tugaydigan usernamelar, xususan @Humanresourcesuz_bot kabi) yoki reklama kanallari havolalarini 'Aloqa' qismiga qo'ymang. FAQAT real insonlarning shaxsiy telegram profili (masalan, @ism_hr) yoki telefon raqamini ko'rsating. Agar bunday shaxsiy aloqa ma'lumoti matnda bo'lmasa, 'Aloqa' qismiga '[Ko'rsatilmagan]' deb yozing.
5. Agar biror ma'lumot matnda bo'lmasa, uni bo'sh qoldirmang, balki "[Ko'rsatilmagan]" deb yozing yoki mos qatorni olib tashlang.
6. Har doim toza va chiroyli o'zbek tilida javob bering.
7. Javobingizda faqat tayyorlangan vakansiya matni bo'lsin, ortiqcha izoh yoki gap qo'shmang.
8. Shablon oxiridagi "[Nuvi Jobs](https://t.me/nuvi_jobs) - *ish va ishchi topishda yordam beramiz!*" qismini o'zgarishsiz, aynan qanday yozilgan bo'lsa shunday qoldiring.
"""
    try:
        formatted = await ai.process_message(raw_text, system_prompt, use_tools=False)
        if formatted:
            expected_footer = "[Nuvi Jobs](https://t.me/nuvi_jobs) - *ish va ishchi topishda yordam beramiz!*"
            import re
            lines = formatted.split("\n")
            for idx, line in enumerate(lines):
                # 1. Clean the contact line from bot usernames
                if "aloqa" in line.lower():
                    # Remove usernames ending with _bot
                    clean_line = re.sub(r"@[a-zA-Z0-9_]+_bot\b", "", line, flags=re.IGNORECASE)
                    
                    # Extract the prefix and value
                    prefix = "📩 *Aloqa:*"
                    val = clean_line
                    parts = re.split(r"(?i)aloqa\s*:\s*\*?", clean_line)
                    if len(parts) > 1:
                        val = parts[1]
                        
                    val = val.replace("*", "").replace("📩", "").strip()
                    # Clean leading/trailing spaces, commas, dashes, and yokis
                    val = re.sub(r"^(?:\s*yoki\s*|\s*or\s*|\s*,\s*|\s*-\s*)+", "", val, flags=re.IGNORECASE)
                    val = re.sub(r"(?:\s*yoki\s*|\s*or\s*|\s*,\s*|\s*-\s*)+$", "", val, flags=re.IGNORECASE)
                    val = val.strip()
                    
                    if not val or val.lower() == "[ko'rsatilmagan]":
                        lines[idx] = f"{prefix} [Ko'rsatilmagan]"
                    else:
                        lines[idx] = f"{prefix} {val}"
                
                # 2. Enforce the correct footer
                if "[Nuvi Jobs](https://t.me/nuvi_jobs)" in line:
                    lines[idx] = expected_footer
                    
            formatted = "\n".join(lines)
        return formatted
    except Exception as e:
        logger.error(f"Gemini vacancy formatting error: {e}")
        return ""


def extract_meta_for_cover(text: str) -> tuple[str, str, str]:
    """Qayd qilingan shablondan kompaniya, lavozim va maoshni ajratib oladi."""
    import re
    company = "Ko'rsatilmagan"
    position = "Yangi Vakansiya"
    salary = "Kelishilgan holda"
    
    m_comp = re.search(r"🏢\s*\*?\*?(?:Firma|Kompaniya):\*?\*?\s*(.+)", text)
    if m_comp:
        company = m_comp.group(1).replace("**", "").replace("*", "").strip()
        
    m_pos = re.search(r"📌\s*\*?\*?([^\n]+)\*?\*?", text)
    if m_pos:
        position = m_pos.group(1).replace("**", "").replace("*", "").strip()
        
    m_sal = re.search(r"💰\s*\*?\*?Maosh:\*?\*?\s*(.+)", text)
    if m_sal:
        salary = m_sal.group(1).replace("**", "").replace("*", "").strip()
    else:
        m_sal = re.search(r"💵\s*\*?\*?Maosh:\*?\*?\s*(.+)", text)
        if m_sal:
            salary = m_sal.group(1).replace("**", "").replace("*", "").strip()
        
    return position, company, salary


async def vacancy_scraper_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har soatda 8:00 dan 22:00 gacha yangi vakansiyalarni tekshiradi."""
    try:
        # Check time range (8:00 - 22:00 Tashkent time)
        tz = pytz.timezone("Asia/Tashkent")
        now = datetime.datetime.now(tz)
        if not (8 <= now.hour <= 22):
            logger.info(f"Vacancy job skipped (outside 8:00-22:00, current: {now.strftime('%H:%M')})")
            return

        global vacancy_scraper
        if not vacancy_scraper or not vacancy_scraper.connected:
            logger.warning("Vacancy scraper is not initialized or not connected.")
            return

        logger.info("⏱ Vacancy Scraper checking source channels...")
        folder_name = os.environ.get("VACANCY_HR_FOLDER", "HR")
        channels = await vacancy_scraper.get_source_channels(folder_name)
        if not channels:
            logger.info("Vacancy source channels empty.")
            return

        # Get latest messages from sources
        latest_vacancies = await vacancy_scraper.get_latest_vacancies(channels, limit=5)
        if not latest_vacancies:
            logger.info("No vacancies found in sources.")
            return

        import database
        for vac in latest_vacancies:
            already_processed = await database.db_is_vacancy_processed(vac["channel_id"], vac["msg_id"])
            if already_processed:
                continue

            logger.info(f"Found new vacancy in {vac['channel_name']} (msg_id: {vac['msg_id']})")
            
            # Format vacancy
            formatted = await format_vacancy_with_ai(vac["text"])
            if not formatted or "xato" in formatted.lower():
                logger.warning("Empty or error response from AI vacancy formatting.")
                continue

            # Send post to target channel
            target_channel = os.environ.get("VACANCY_TARGET_CHANNEL", TARGET_CHANNEL)
            try:
                # Generate cover image
                from image_generator import generate_vacancy_cover
                import tempfile
                
                pos, comp, sal = extract_meta_for_cover(formatted)
                temp_dir = tempfile.gettempdir()
                temp_path = os.path.join(temp_dir, f"vacancy_{vac['msg_id']}.png")
                
                img_success = generate_vacancy_cover(pos, comp, sal, temp_path)
                
                if img_success and os.path.exists(temp_path):
                    try:
                        with open(temp_path, "rb") as photo:
                            await context.bot.send_photo(
                                chat_id=target_channel,
                                photo=photo,
                                caption=escape_telegram_markdown(formatted),
                                parse_mode="Markdown"
                            )
                        logger.info(f"✅ Vacancy photo post sent: {target_channel}")
                    except Exception as photo_err:
                        logger.warning(f"Failed sending cover photo to {target_channel}: {photo_err}. Trying split messages.")
                        short_caption = f"📢 *NUVI JOBS | YANGI VAKANSIYA*\n\n📌 *Lavozim:* {pos}\n🏢 *Firma:* {comp}\n💵 *Maosh:* {sal}"
                        try:
                            with open(temp_path, "rb") as photo:
                                await context.bot.send_photo(
                                    chat_id=target_channel,
                                    photo=photo,
                                    caption=escape_telegram_markdown(short_caption),
                                    parse_mode="Markdown"
                                )
                            await context.bot.send_message(
                                chat_id=target_channel,
                                text=escape_telegram_markdown(formatted),
                                parse_mode="Markdown"
                            )
                            logger.info(f"✅ Vacancy photo + text split posts sent: {target_channel}")
                        except Exception as split_err:
                            logger.error(f"Failed sending split posts: {split_err}")
                            await context.bot.send_message(
                                chat_id=target_channel,
                                text=escape_telegram_markdown(formatted),
                                parse_mode="Markdown"
                            )
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                else:
                    # Fallback to plain text if image generation fails
                    await context.bot.send_message(
                        chat_id=target_channel,
                        text=escape_telegram_markdown(formatted),
                        parse_mode="Markdown"
                    )
                
                # Mark as processed in DB
                await database.db_add_processed_vacancy(vac["channel_id"], vac["msg_id"])
                logger.info(f"✅ Vacancy yuborildi: {target_channel} (source: {vac['channel_name']})")
                
                # Break to send only ONE vacancy per hour
                break
            except Exception as e:
                logger.error(f"Failed to post vacancy to {target_channel}: {e}")
                
    except Exception as e:
        logger.error(f"Vacancy scraper job error: {e}")


async def cmd_scrape(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manual vacancy scraper trigger for testing."""
    if not update.message or update.message.from_user.id != OWNER_ID:
        return
        
    await update.message.reply_text("🔍 Vakansiyalarni skanerlash boshlandi, biroz kuting...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    global vacancy_scraper
    if not vacancy_scraper or not vacancy_scraper.connected:
        await update.message.reply_text("❌ Scraper Telegram akkauntiga ulanmagan. Bir ozdan keyin qayta urining.")
        return
    try:
        folder_name = os.environ.get("VACANCY_HR_FOLDER", "HR")
        channels = await vacancy_scraper.get_source_channels(folder_name)
        if not channels:
            await update.message.reply_text(
                f"⚠️ '{folder_name}' nomli papka (dialog filter) ikkinchi Telegram akkauntingizda topilmadi yoki bo'sh.\n\n"
                f"Tuzatish yo'llari:\n"
                f"1. Ikkinchi Telegram akkauntingizda (@soma_support) Telegram sozlamalaridan '{folder_name}' nomli papka yarating va unga vakansiya o'qiladigan kanallarni qo'shing.\n"
                f"2. Yoki Railway orqali `VACANCY_SOURCES` o'zgaruvchisiga kanallarni vergul bilan yozib qo'ying (masalan: `@channel1,@channel2`)."
            )
            return
            
        await update.message.reply_text(f"📁 {len(channels)} ta kanal topildi. Yangi xabarlarni tekshirmoqdaman...")
        latest_vacancies = await vacancy_scraper.get_latest_vacancies(channels, limit=5)
        
        if not latest_vacancies:
            await update.message.reply_text("ℹ️ Kanallarda yangi vakansiyalar topilmadi.")
            return
            
        import database
        found_any = False
        for vac in latest_vacancies:
            already_processed = await database.db_is_vacancy_processed(vac["channel_id"], vac["msg_id"])
            if already_processed:
                continue
                
            found_any = True
            await update.message.reply_text(f"💡 Yangi vakansiya topildi: {vac['channel_name']}. Formatlanmoqda...")
            
            # Format vacancy
            formatted = await format_vacancy_with_ai(vac["text"])
            if not formatted or "xato" in formatted.lower():
                await update.message.reply_text("⚠️ AI formatlashda xatolik yuz berdi.")
                continue
                
            # Send post to target channel
            target_channel = os.environ.get("VACANCY_TARGET_CHANNEL", TARGET_CHANNEL)
            
            # Generate cover image
            from image_generator import generate_vacancy_cover
            import tempfile
            
            pos, comp, sal = extract_meta_for_cover(formatted)
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"vacancy_manual_{vac['msg_id']}.png")
            
            img_success = generate_vacancy_cover(pos, comp, sal, temp_path)
            
            if img_success and os.path.exists(temp_path):
                try:
                    with open(temp_path, "rb") as photo:
                        await context.bot.send_photo(
                            chat_id=target_channel,
                            photo=photo,
                            caption=escape_telegram_markdown(formatted),
                            parse_mode="Markdown"
                        )
                    await update.message.reply_text(f"✅ Vakansiya muvaffaqiyatli yuborildi: {target_channel}")
                except Exception as tg_err:
                    logger.warning(f"Failed to send photo with full caption: {tg_err}. Retrying with split messages.")
                    short_caption = f"📢 *NUVI JOBS | YANGI VAKANSIYA*\n\n📌 *Lavozim:* {pos}\n🏢 *Firma:* {comp}\n💵 *Maosh:* {sal}"
                    try:
                        with open(temp_path, "rb") as photo:
                            await context.bot.send_photo(
                                chat_id=target_channel,
                                photo=photo,
                                caption=escape_telegram_markdown(short_caption),
                                parse_mode="Markdown"
                            )
                        await context.bot.send_message(
                            chat_id=target_channel,
                            text=escape_telegram_markdown(formatted),
                            parse_mode="Markdown"
                        )
                        await update.message.reply_text(f"✅ Vakansiya muvaffaqiyatli yuborildi (surat va matn alohida): {target_channel}")
                    except Exception as split_err:
                        logger.error(f"Failed to send split vacancy messages in cmd_scrape: {split_err}")
                        await context.bot.send_message(chat_id=target_channel, text=escape_telegram_markdown(formatted), parse_mode="Markdown")
                        await update.message.reply_text(f"✅ Vakansiya faqat matn ko'rinishida yuborildi: {target_channel}")
                try:
                    os.unlink(temp_path)
                except:
                    pass
            else:
                await context.bot.send_message(chat_id=target_channel, text=escape_telegram_markdown(formatted), parse_mode="Markdown")
                await update.message.reply_text(f"✅ Vakansiya faqat matn ko'rinishida yuborildi (oblojka xatosi): {target_channel}")
                
            # Mark as processed in DB
            await database.db_add_processed_vacancy(vac["channel_id"], vac["msg_id"])
            break
            
        if not found_any:
            await update.message.reply_text("ℹ️ Barcha topilgan vakansiyalar oldin qayta ishlangan. Yangisi yo'q.")
            
    except Exception as e:
        logger.error(f"Manual scrape error: {e}")
        await update.message.reply_text(f"❌ Xatolik yuz berdi: {e}")


# ──────────────────────── MAIN ASSEMBLY ─────────────────────────

def main():
    """Bot ishga tushirish."""
    logger.info("🤖 Nuvi Jobs Bot ishga tushmoqda...")
    
    # DB initialization
    loop = asyncio.get_event_loop()
    loop.run_until_complete(database.init_db())
    
    # Align database settings with new approved defaults
    async def update_db_prices():
        try:
            await database.db_set_nuvi_setting("tariff_pro_price", "20000")
            await database.db_set_nuvi_setting("tariff_premium_price", "35000")
            await database.db_set_nuvi_setting("tariff_vip_price", "50000")
            logger.info("✅ Database prices aligned to new defaults: Pro=20k, Premium=35k, VIP=50k")
        except Exception as e:
            logger.error(f"Failed to align database prices: {e}")
            
    loop.run_until_complete(update_db_prices())
    
    app = Application.builder().token(NUVI_BOT_TOKEN).post_init(post_init).build()
    
    # ─── JOB QUEUE FOR AUTO-POSTING ───
    app.job_queue.run_repeating(nuvi_auto_post_job, interval=600, first=10)
    app.job_queue.run_repeating(vacancy_scraper_job, interval=3600, first=60)
    
    # ─── CONVERSATION HANDLER FOR VACANCY ───
    vacancy_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^💼 E'lon berish$"), cb_create_start),
            CallbackQueryHandler(cb_create_start, pattern="^nuvi_create$")
        ],
        states={
            ASK_SECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_section_received)],
            ASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_experience)],
            ASK_EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_location)],
            ASK_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_company)],
            ASK_COMPANY: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_salary)],
            ASK_SALARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_contact)],
            ASK_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_working_hours)],
            ASK_WORKING_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_requirements)],
            ASK_REQUIREMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_skills)],
            ASK_SKILLS: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_benefits)],
            ASK_BENEFITS: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_generate_preview)],
            CONFIRM_PREVIEW: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_confirm_preview_received)],
            CHOOSE_TARIFF: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_choose_tariff_received)],
            CHOOSE_PAYMENT_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_payment_method_received)],
            WAIT_MANUAL_RECEIPT: [
                MessageHandler(filters.PHOTO, state_manual_receipt_received),
                MessageHandler(filters.TEXT & ~filters.COMMAND, state_manual_receipt_received),
                CommandHandler("cancel", cmd_cancel)
            ]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True
    )
    app.add_handler(vacancy_conv)
    
    # ─── CONVERSATION HANDLER FOR ADMIN BROADCAST ───
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_admin_broadcast, pattern="^admin_broadcast$")],
        states={
            BROADCAST_ASK_MSG: [
                MessageHandler(filters.ALL & ~filters.COMMAND, state_broadcast_ask_confirm)
            ],
            BROADCAST_CONFIRM: [
                CallbackQueryHandler(cb_broadcast_confirm, pattern="^broadcast_confirm$"),
                CallbackQueryHandler(cb_broadcast_cancel, pattern="^broadcast_cancel$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True
    )
    app.add_handler(broadcast_conv)
    
    # ─── PAYMENTS HANDLERS ───
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    
    # ─── ADMIN SETTINGS CONVERSATION AND CALLBACKS ───
    settings_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_set_price_start, pattern="^set_price_(pro|premium|vip)$"),
            CallbackQueryHandler(cb_set_card_start, pattern="^set_card$")
        ],
        states={
            SETTING_ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_setting_price_received)],
            SETTING_ASK_CARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_setting_card_received)]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True
    )
    app.add_handler(settings_conv)
    app.add_handler(CallbackQueryHandler(cb_admin_settings, pattern="^admin_settings$"))
    
    # ─── ADMIN SPECIFIC CALLBACKS ───
    app.add_handler(CallbackQueryHandler(cb_admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(cb_admin_back, pattern="^admin_back$"))
    
    # ─── ADMIN CALLBACKS ───
    app.add_handler(CallbackQueryHandler(admin_buttons_callback, pattern="^admin_"))
    
    # ─── ADMIN COMMANDS ───
    app.add_handler(CommandHandler("admin", cmd_admin))
    
    # ─── USER MENUS (REPLY KEYBOARDS) ───
    app.add_handler(MessageHandler(filters.Regex("^📊 Mening e'lonlarim$"), cb_my_vacancies_text))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ Bot haqida$"), cb_bot_info_text))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Admin panel$"), cmd_admin))
    
    # ─── USER CALLBACKS ───
    app.add_handler(CallbackQueryHandler(cmd_start, pattern="^nuvi_menu$"))
    app.add_handler(CallbackQueryHandler(cb_my_vacancies, pattern="^nuvi_my_list$"))
    app.add_handler(CallbackQueryHandler(cb_bot_info, pattern="^nuvi_info$"))
    
    # ─── PUBLIC COMMANDS ───
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("scrape", cmd_scrape))
    
    app.run_polling()

if __name__ == "__main__":
    main()
