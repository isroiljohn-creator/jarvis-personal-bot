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
import random
import string
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

NUVI_BOT_TOKEN = os.environ.get("NUVI_BOT_TOKEN", "8713575188:AAGu5iCVtoBBlCIydf_gWwAzp9SCNDyO-4g")
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
    ENTER_PROMOCODE,
    CHOOSE_PAYMENT_METHOD,
    WAIT_MANUAL_RECEIPT,
) = range(16)

# Broadcast holatlari
(
    BROADCAST_ASK_MSG,
    BROADCAST_CONFIRM,
) = range(16, 18)

# Settings holatlari
(
    SETTING_ASK_PRICE,
    SETTING_ASK_CARD,
) = range(18, 20)

# Vacancy edit holatlari
(
    EDIT_VACANCY_TEXT_STATE,
) = range(20, 21)

# Pin payment holatlari
(
    WAIT_PIN_RECEIPT,
) = range(21, 22)

# Qo'shimcha yangilanishlar holatlari
(
    EDIT_BEFORE_SEND_CHOOSE_FIELD,
    EDIT_BEFORE_SEND_INPUT,
    ADMIN_CREATE_PROMOCODE,
    WAIT_BUMP_RECEIPT,
) = range(22, 26)

# Kengaytirilgan imkoniyatlar holatlari (CV, Alerts, ATS, Ratings)
(
    CV_ASK_NAME,
    CV_ASK_CONTACT,
    CV_ASK_SPECIALTY,
    CV_ASK_SKILLS,
    CV_ASK_EXPERIENCE,
    CV_ASK_EDUCATION,
    CV_ASK_ABOUT,
    
    PREF_ASK_KEYWORDS,
    PREF_ASK_LOCATION,
    
    APPLY_ASK_COVER_LETTER,
    APPLY_ASK_RESUME,
    
    EMPLOYER_INTERVIEW_MESSAGE,
    EMPLOYER_REJECT_REASON,
    
    RATING_ASK_STARS,
    RATING_ASK_COMMENT,
) = range(26, 41)


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

import html

# Inter fonts paths
inter_regular_path = os.path.join(os.path.dirname(__file__), "Inter-Regular.ttf")
inter_bold_path = os.path.join(os.path.dirname(__file__), "Inter-Bold.ttf")

try:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if os.path.exists(inter_regular_path) and os.path.exists(inter_bold_path):
        pdfmetrics.registerFont(TTFont("Inter", inter_regular_path))
        pdfmetrics.registerFont(TTFont("Inter-Bold", inter_bold_path))
        logger.info("✅ Inter fonts successfully registered in ReportLab.")
    else:
        logger.warning("⚠️ Inter font files not found, default Helvetica will be used.")
except Exception as fe:
    logger.error(f"Error registering Inter fonts: {fe}")

def escape_xml(text: str) -> str:
    """ReportLab Paragraph XML parsing xatolarini oldini olish uchun textni escape qiladi."""
    if not text:
        return ""
    return html.escape(text).replace("\n", "<br/>")

def generate_cv_pdf(cv_data: dict, output_path: str) -> None:
    """Foydalanuvchi ma'lumotlari asosida premium PDF rezyume yaratadi."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )
    
    story = []
    
    # Fontlarni aniqlash
    font_reg = "Inter" if os.path.exists(inter_regular_path) else "Helvetica"
    font_bold = "Inter-Bold" if os.path.exists(inter_bold_path) else "Helvetica-Bold"
    
    # Custom styles
    name_style = ParagraphStyle(
        "CVName",
        fontName=font_bold,
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#0F172A")
    )
    spec_style = ParagraphStyle(
        "CVSpec",
        fontName=font_bold,
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#2563EB"),
        spaceAfter=5
    )
    contact_style = ParagraphStyle(
        "CVContact",
        fontName=font_reg,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#475569")
    )
    h1_style = ParagraphStyle(
        "CVH1",
        fontName=font_bold,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=12,
        spaceAfter=4
    )
    body_style = ParagraphStyle(
        "CVBody",
        fontName=font_reg,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6
    )
    
    # Header Section
    story.append(Paragraph(escape_xml(cv_data.get("name", "Nomzod")), name_style))
    story.append(Paragraph(escape_xml(cv_data.get("specialty", "Mutaxassislik")), spec_style))
    
    contact_text = f"Aloqa: {escape_xml(cv_data.get('contact', '-'))}  |  Telegram orqali yaratilgan"
    story.append(Paragraph(contact_text, contact_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#E2E8F0"), spaceAfter=10))
    
    # About Section
    if cv_data.get("about"):
        story.append(Paragraph("O'ZIM HAQIMDA", h1_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceAfter=5))
        story.append(Paragraph(escape_xml(cv_data.get("about")), body_style))
        story.append(Spacer(1, 5))
        
    # Skills Section
    story.append(Paragraph("KO'NIKMALAR", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceAfter=5))
    
    skills_raw = cv_data.get("skills", "-")
    # Ensure there is a space after each comma to force ReportLab line wrapping
    skills_formatted = ", ".join([s.strip() for s in skills_raw.split(",") if s.strip()])
    story.append(Paragraph(escape_xml(skills_formatted), body_style))
    story.append(Spacer(1, 5))
    
    # Experience Section
    story.append(Paragraph("ISH TAJRIBASI", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceAfter=5))
    story.append(Paragraph(escape_xml(cv_data.get("experience", "-")), body_style))
    story.append(Spacer(1, 5))
    
    # Education Section
    story.append(Paragraph("MA'LUMOT / TA'LIM", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceAfter=5))
    story.append(Paragraph(escape_xml(cv_data.get("education", "-")), body_style))
    story.append(Spacer(1, 10))
    
    # Footer Note
    footer_note_style = ParagraphStyle(
        "CVFooterNote",
        fontName=font_reg,
        fontSize=8,
        textColor=colors.HexColor("#94A3B8"),
        alignment=1 # Center
    )
    story.append(Spacer(1, 15))
    story.append(Paragraph("Rezyume @nuvijobs_bot yordamida shakllantirildi", footer_note_style))
    
    doc.build(story)


def trim_to_fit_caption(text: str, max_chars: int = 1000) -> str:
    """Xabar caption limitdan oshsa, pastdan boshlab punktlarni o'chiradi."""
    if not text or len(text) <= max_chars:
        return text
        
    lines = text.split("\n")
    # Pastdan boshlab punkt (bullet points) qatorlarini qirqib tashlaymiz
    while len("\n".join(lines)) > max_chars:
        bullet_idx = -1
        for i in range(len(lines) - 1, -1, -1):
            stripped = lines[i].strip()
            if stripped.startswith("—") or stripped.startswith("-") or stripped.startswith("*"):
                # Slogan va footer'larni o'chirmaslik uchun tekshiramiz
                if "nuvi_jobs" not in stripped.lower() and "aloqa" not in stripped.lower():
                    bullet_idx = i
                    break
        if bullet_idx != -1:
            lines.pop(bullet_idx)
        else:
            break
            
    trimmed = "\n".join(lines)
    # Agar baribir uzun bo'lsa, oxirida majburiy kesamiz
    if len(trimmed) > max_chars:
        footer = ""
        # Contact info qismini saqlash
        for line in reversed(text.split("\n")):
            if "aloqa" in line.lower() or "nuvi_jobs" in line.lower():
                footer = "\n" + line + footer
        slice_idx = max(0, max_chars - len(footer) - 5)
        trimmed = trimmed[:slice_idx] + "..." + footer
        
    return trimmed

async def notify_shifted_vacancies(bot, shifted) -> None:
    """Navbati surilgan pullik e'lonlar egalarini xabardor qiladi."""
    if not shifted:
        return
    import pytz
    tz = pytz.timezone("Asia/Tashkent")
    for item in shifted:
        user_id = item["user_id"]
        vac_id = item["id"]
        title = item["title"]
        new_time = item["new_time"].astimezone(tz).strftime("%Y-%m-%d %H:%M")
        
        warning_clause = ""
        if item.get("tariff") == "premium":
            warning_clause = "\n⚠️ Eslatib o'tamiz, kelishilganidek, sizning postingiz to'lov tasdiqlanganidan so'ng **24-48 soat ichida** kanalga to'liq joylashtiriladi.\n"
            
        msg = (
            f"⚠️ **E'lon vaqti yangilandi**\n\n"
            f"Hurmatli foydalanuvchi! Yangi VIP/Premium e'lonlar tasdiqlanganligi sababli "
            f"Sizning #{vac_id} ({title}) vakansiyangiz navbati biroz surildi.\n\n"
            f"⏰ Yangi chop etilish vaqti: **{new_time}** (Toshkent vaqti bilan).\n"
            f"{warning_clause}\n"
            f"Tushunganingiz uchun rahmat!"
        )
        try:
            await bot.send_message(
                chat_id=user_id,
                text=msg,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Notification sent to user {user_id} for vacancy #{vac_id} shift.")
        except Exception as e:
            logger.error(f"Failed to notify user {user_id} of shift: {e}")


async def check_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.message and update.message.text:
        txt = update.message.text.strip()
        if txt in ("🚫 Bekor qilish", "Vakansiyani bekor qilish"):
            await update.message.reply_text("E'lon berish bekor qilindi.", reply_markup=ReplyKeyboardRemove())
            await cmd_start(update, context)
            return True
    return False

def get_contact_url(contact_text: str) -> Optional[str]:
    if not contact_text:
        return None
    contact_text = contact_text.strip()
    import re
    # Check for telegram username (@username)
    username_match = re.search(r"@([a-zA-Z0-9_]{5,32})", contact_text)
    if username_match:
        return f"https://t.me/{username_match.group(1)}"
    # Check for http URL
    url_match = re.search(r"(https?://[^\s]+)", contact_text)
    if url_match:
        return url_match.group(1)
    return None

def get_vacancy_reply_markup(bot_username: str, vac: dict) -> InlineKeyboardMarkup:
    keyboard = []
    contact_url = get_contact_url(vac.get("contact", ""))
    if contact_url:
        keyboard.append([InlineKeyboardButton("📩 Bog'lanish", url=contact_url)])
    else:
        # Fallback to starting the bot with apply parameter
        keyboard.append([InlineKeyboardButton("📝 Ariza topshirish", url=f"https://t.me/{bot_username}?start=apply_{vac['id']}")])
    return InlineKeyboardMarkup(keyboard)

async def format_vacancy_text(data: dict) -> str:
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
    
    # Ishonchli ish beruvchi / Reyting
    user_id = data.get("user_id")
    rating_str = ""
    if user_id:
        try:
            rating_info = await database.db_get_employer_rating(user_id)
            is_verified = await database.db_is_employer_verified(user_id)
            if rating_info["reviews_count"] > 0:
                rating_str = f" ⭐ {rating_info['avg_rating']:.1f} ({rating_info['reviews_count']} baholar)"
            if is_verified:
                rating_str += " 🛡️ [Ishonchli]"
        except Exception as e:
            logger.error(f"Error getting employer rating in format_vacancy_text: {e}")
            
    text = f"📌 *{title}*\n\n"
    text += f"🏢 *Firma:* {company}{rating_str}\n"
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

async def check_user_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Foydalanuvchi majburiy obuna kanaliga a'zo ekanligini tekshiradi."""
    user = update.effective_user
    if not user:
        return True
        
    user_id = user.id
    if user_id == OWNER_ID:
        return True
        
    target_channel = "@nuvi_jobs"
    try:
        member = await context.bot.get_chat_member(chat_id=target_channel, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True
    except Exception as e:
        logger.warning(f"Obunani tekshirishda xatolik ({user_id}): {e}")
        # Bot kanalda bo'lmasa yoki xato bersa, bot bloklanib qolmasligi uchun True qaytaramiz
        return True
        
    # Obuna bo'lmagan bo'lsa
    join_btn = InlineKeyboardButton("🔗 Kanalga a'zo bo'lish", url="https://t.me/nuvi_jobs")
    check_btn = InlineKeyboardButton("🔄 Tekshirish", callback_data="nuvi_check_sub")
    reply_markup = InlineKeyboardMarkup([[join_btn], [check_btn]])
    
    msg = (
        "🚀 **Botdan foydalanish uchun rasmiy kanalimizga a'zo bo'lishingiz lozim!**\n\n"
        "Iltimos, avval kanalimizga a'zo bo'ling va keyin **'Tekshirish'** tugmasini bosing."
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    elif update.message:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        
    return False

async def cb_check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Obunani tekshirish callback handler."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    user_id = user.id
    
    target_channel = "@nuvi_jobs"
    try:
        member = await context.bot.get_chat_member(chat_id=target_channel, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            try:
                await query.message.delete()
            except Exception:
                pass
            # Bosh menyuni ko'rsatamiz
            context.args = []
            await cmd_start(update, context)
            return
    except Exception as e:
        logger.error(f"Error checking sub callback: {e}")
        
    await query.message.reply_text(
        "❌ **Siz hali kanalga a'zo bo'lmadingiz!**\nIltimos, pastdagi tugma orqali a'zo bo'ling va qayta urinib ko'ring.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Kanalga a'zo bo'lish", url="https://t.me/nuvi_jobs")],
            [InlineKeyboardButton("🔄 Tekshirish", callback_data="nuvi_check_sub")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bot boshlanishi."""
    user = update.effective_user
    if not user:
        return ConversationHandler.END
        
    # Umumiy start bo'lsa (deep link param bo'lmasa) majburiy obunani tekshiramiz
    if not (update.message and context.args):
        if not await check_user_subscription(update, context):
            return ConversationHandler.END
            
    referred_by = None

    if update.message and context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referred_by = int(arg.split("_")[1])
                if referred_by == user.id:
                    referred_by = None
            except (IndexError, ValueError):
                pass
        elif arg.startswith("apply_"):
            try:
                vac_id = int(arg.split("_")[1])
                vac = await database.db_get_nuvi_vacancy(vac_id)
                if vac:
                    msg = (
                        f"📋 **VAKANSIYA MA'LUMOTLARI**\n\n"
                        f"📌 **Lavozim:** {clean_for_markdown(vac['title'])}\n"
                        f"🏢 **Firma:** {clean_for_markdown(vac['company'])}\n"
                        f"💵 **Maosh:** {clean_for_markdown(vac['salary'])}\n"
                        f"📍 **Lokatsiya:** {clean_for_markdown(vac['location'])}\n"
                    )
                    if vac.get('working_hours'):
                        msg += f"⏱️ **Ish vaqti:** {clean_for_markdown(vac['working_hours'])}\n"
                    if vac.get('requirements'):
                        msg += f"\n📝 **Vazifalar:**\n{clean_for_markdown(vac['requirements'])}\n"
                    if vac.get('skills'):
                        msg += f"\n⚙️ **Talablar:**\n{clean_for_markdown(vac['skills'])}\n"
                    if vac.get('benefits'):
                        msg += f"\n🎁 **Taklif (Qulayliklar):**\n{clean_for_markdown(vac['benefits'])}\n"
                    msg += (
                        f"\n📩 **Aloqa uchun ma'lumot:**\n"
                        f"`{clean_for_markdown(vac['contact'])}`\n\n"
                        f"Bog'lanish uchun yuqoridagi kontaktlardan foydalaning yoki bot orqali ariza topshirish uchun quyidagi tugmani bosing."
                    )
                    reply_markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton("📝 Ariza topshirish", callback_data=f"apply_vac_{vac_id}")
                    ]])
                    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
                    return ConversationHandler.END
            except Exception as e:
                logger.error(f"Error handling apply start parameter: {e}")
                
    await database.db_upsert_nuvi_user(user.id, user.username, user.first_name, referred_by)
    
    keyboard = [
        ["💼 E'lon berish", "📊 Mening e'lonlarim"],
        ["📝 Mening profilim / CV", "🔔 Mos vakansiyalar obunasi"],
        ["🏢 Ish beruvchini baholash", "ℹ️ Bot haqida"],
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
    if not await check_user_subscription(update, context):
        return ConversationHandler.END
        
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

async def show_confirm_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    waiting_msg = await update.message.reply_text("⏳ Oblojka va e'lon matni tayyorlanmoqda, iltimos kuting...")
    context.user_data["user_id"] = update.effective_user.id
    formatted_text = await format_vacancy_text(context.user_data)
    context.user_data["formatted_text"] = formatted_text
    
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"vacancy_preview_{update.effective_user.id}.png")
    
    img_success = generate_vacancy_cover(
        position=context.user_data["title"],
        company=context.user_data["company"],
        salary=context.user_data["salary"],
        output_path=temp_path
    )
    
    if waiting_msg:
        try:
            await waiting_msg.delete()
        except:
            pass
            
    keyboard = [
        ["✅ Ha, hammasi to'g'ri"],
        ["✏️ Tahrirlash"],
        ["❌ Bekor qilish"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    msg_text = (
        f"Vakansiya e'loni kanalda quyidagicha ko'rinadi:\n\n"
        f"{escape_telegram_markdown(formatted_text)}\n\n"
        f"Barcha ma'lumotlar to'g'rimi? Quyidagi tugmalardan tanlang 👇"
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

async def state_generate_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    benefits = update.message.text.strip()
    context.user_data["benefits"] = benefits
    
    return await show_confirm_preview(update, context)

async def state_confirm_preview_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    text = update.message.text.strip()
    if text == "✅ Ha, hammasi to'g'ri" or text == "✅ Ha":
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
    elif text == "✏️ Tahrirlash":
        return await show_edit_before_send_fields_menu(update, context)
    else:
        await update.message.reply_text("E'lon bekor qilindi.", reply_markup=ReplyKeyboardRemove())
        await cmd_start(update, context)
        return ConversationHandler.END

async def show_edit_before_send_fields_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        ["Sarlavha", "Tajriba"],
        ["Lokatsiya", "Kompaniya"],
        ["Maosh", "Ish vaqti"],
        ["Vazifalar", "Talablar"],
        ["Taklif (Qulayliklar)", "Aloqa"],
        ["⬅️ Orqaga"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Tahrirlash uchun kerakli maydonni tanlang:",
        reply_markup=reply_markup
    )
    return EDIT_BEFORE_SEND_CHOOSE_FIELD

async def state_edit_before_send_choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    text = update.message.text.strip()
    if text == "⬅️ Orqaga":
        return await show_confirm_preview(update, context)
        
    field_map = {
        "Sarlavha": ("title", "yangi lavozim nomini (Sarlavha)"),
        "Tajriba": ("experience", "yangi tajriba talabini (masalan: 1-3 yil)"),
        "Lokatsiya": ("location", "yangi ish joyi manzilini (Lokatsiya)"),
        "Kompaniya": ("company", "yangi kompaniya/firma nomini"),
        "Maosh": ("salary", "yangi maosh miqdorini (masalan: 5-8 mln so'm)"),
        "Ish vaqti": ("working_hours", "yangi ish vaqtini (masalan: 9:00 - 18:00)"),
        "Vazifalar": ("requirements", "yangi vazifalarni (batafsil)"),
        "Talablar": ("skills", "yangi nomzodga qo'yiladigan talablarni (ko'nikmalar)"),
        "Taklif (Qulayliklar)": ("benefits", "ish beruvchidan yangi taklif/qulayliklarni"),
        "Aloqa": ("contact", "yangi aloqa ma'lumotlarini (masalan: @username yoki telefon)")
    }
    
    if text not in field_map:
        await update.message.reply_text("Iltimos, ro'yxatdagi maydonlardan birini tanlang:")
        return EDIT_BEFORE_SEND_CHOOSE_FIELD
        
    db_field, prompt = field_map[text]
    context.user_data["editing_field"] = db_field
    context.user_data["editing_field_name"] = text
    
    await update.message.reply_text(
        f"Iltimos, {prompt} kiriting:",
        reply_markup=ReplyKeyboardMarkup([["⬅️ Orqaga"]], resize_keyboard=True)
    )
    return EDIT_BEFORE_SEND_INPUT

async def state_edit_before_send_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    text = update.message.text.strip()
    if text == "⬅️ Orqaga":
        return await show_edit_before_send_fields_menu(update, context)
        
    db_field = context.user_data.get("editing_field")
    if db_field:
        context.user_data[db_field] = text
        await update.message.reply_text(f"✅ {context.user_data.get('editing_field_name')} muvaffaqiyatli tahrirlandi!")
        
    return await show_confirm_preview(update, context)

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
    
    msg = (
        f"🎟 **Sizda promo-kod bormi?**\n\n"
        f"Agar mavjud bo'lsa, promo-kodni kiriting.\n"
        f"Bo'lmasa, **⏩ O'tkazib yuborish** tugmasini bosing:"
    )
    keyboard = [
        ["⏩ O'tkazib yuborish"],
        ["🚫 Bekor qilish"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    return ENTER_PROMOCODE

async def state_enter_promocode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await check_cancel(update, context):
        return ConversationHandler.END
        
    text = update.message.text.strip()
    vac_id = context.user_data.get("vacancy_id")
    tariff = context.user_data.get("tariff", "pro")
    original_price = await get_tariff_price(tariff)
    
    if text == "⏩ O'tkazib yuborish":
        price = original_price
        keyboard = []
        if PROVIDER_TOKEN:
            keyboard.append(["💳 Telegram orqali to'lov (Click/Payme)"])
        keyboard.append(["📎 Karta orqali to'lov (Chek yuborish)"])
        keyboard.append(["🚫 Bekor qilish"])
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        warning_text = ""
        if tariff == "premium":
            warning_text = "⚠️ **Eslatma:** Navbat tirbandligiga qarab, to'lov tasdiqlanganidan so'ng e'loningiz **24-48 soat ichida** kanalga to'liq joylashtiriladi.\n\n"
            
        msg = (
            f"Vakansiya qabul qilindi!\n\n"
            f"Tanlangan tarif: *{tariff.upper()}*\n"
            f"To'lov summasi: **{price:,} so'm**.\n\n"
            f"{warning_text}"
            f"Iltimos, to'lov usulini tanlang:"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        return CHOOSE_PAYMENT_METHOD
        
    promo = await database.db_validate_promocode(text)
    if not promo:
        await update.message.reply_text(
            "❌ Kiritilgan promo-kod yaroqsiz, muddati o'tgan yoki limiti tugagan.\n"
            "Iltimos, promo-kodni qaytadan yuboring yoki keyingi bosqichga o'tish uchun **⏩ O'tkazib yuborish** tugmasini bosing:",
            reply_markup=ReplyKeyboardMarkup([["⏩ O'tkazib yuborish"], ["🚫 Bekor qilish"]], resize_keyboard=True)
        )
        return ENTER_PROMOCODE
        
    discount_pct = promo.get("discount_pct", 0)
    discount_flat = promo.get("discount_flat", 0)
    
    discount = 0
    if discount_pct > 0:
        discount = (original_price * discount_pct) // 100
    elif discount_flat > 0:
        discount = discount_flat
        
    discounted_price = max(0, original_price - discount)
    
    await database.db_update_nuvi_vacancy(
        vac_id,
        promocode=promo["code"],
        discounted_price=discounted_price
    )
    
    await database.db_use_promocode(promo["code"])
    
    keyboard = []
    if PROVIDER_TOKEN:
        keyboard.append(["💳 Telegram orqali to'lov (Click/Payme)"])
    keyboard.append(["📎 Karta orqali to'lov (Chek yuborish)"])
    keyboard.append(["🚫 Bekor qilish"])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    warning_text = ""
    if tariff == "premium":
        warning_text = "⚠️ **Eslatma:** Navbat tirbandligiga qarab, to'lov tasdiqlanganidan so'ng e'loningiz **24-48 soat ichida** kanalga to'liq joylashtiriladi.\n\n"
        
    msg = (
        f"✅ **Promo-kod muvaffaqiyatli qo'llanildi!**\n"
        f"Promo-kod: `{promo['code']}`\n"
        f"Chegirma: *{discount_pct}%* ({discount:,} so'm)\n"
        f"Tanlangan tarif: *{tariff.upper()}*\n"
        f"Yakuniy to'lov summasi: **{discounted_price:,} so'm**.\n\n"
        f"{warning_text}"
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
    
    vac = await database.db_get_nuvi_vacancy(vac_id)
    if vac and vac.get("discounted_price") is not None:
        price = vac["discounted_price"]
    else:
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
        
        warning_text = ""
        if tariff == "premium":
            warning_text = "⚠️ **Eslatma:** Navbat tirbandligiga qarab, to'lov tasdiqlanganidan so'ng e'loningiz **24-48 soat ichida** kanalga to'liq joylashtiriladi.\n\n"
            
        msg = (
            f"💳 **Karta orqali to'lov:**\n\n"
            f"Karta: `{card}`\n"
            f"Summa: **{price:,} so'm**\n\n"
            f"{warning_text}"
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

async def trigger_payment_referral_check(bot, user_id: int, vacancy_id: int) -> None:
    try:
        referrer_id = await database.db_get_user_referrer(user_id)
        if not referrer_id:
            return
            
        paid_count = await database.db_get_user_paid_vacancies_count(user_id)
        if paid_count == 1:
            suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            promo_code = f"REF_{suffix}"
            
            await database.db_create_promocode(promo_code, discount_pct=10, max_uses=1)
            
            try:
                await bot.send_message(
                    chat_id=referrer_id,
                    text=(
                        f"🎉 **Tabriklaymiz!** Siz taklif qilgan do'stingiz botda o'zining birinchi pullik e'lonini joylashtirdi.\n\n"
                        f"Sizga navbatdagi e'loningiz uchun **10% chegirmali** shaxsiy promo-kod taqdim etiladi:\n"
                        f"`{promo_code}`\n\n"
                        f"Uni to'lov sahifasida kiritib chegirma olishingiz mumkin."
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"Referral reward promo-code {promo_code} sent to referrer {referrer_id}")
            except Exception as notify_err:
                logger.error(f"Failed to notify referrer {referrer_id}: {notify_err}")
                
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text="🎁 Do'stingiz taklifi bilan ro'yxatdan o'tganingiz uchun unga chegirma promo-kodi yuborildi. Rahmat!"
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"trigger_payment_referral_check error: {e}")

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
    
    if payload.startswith("vacancy_payment_"):
        vac_id = int(payload.split("_")[-1])
        
        await database.db_update_nuvi_vacancy(
            vac_id,
            status="pending_approval",
            payment_status="paid"
        )
        
        await update.message.reply_text(
            "To'lovingiz muvaffaqiyatli qabul qilindi! Vakansiya tasdiqlash uchun adminga yuborildi."
        )
        
        # Trigger referral check
        await trigger_payment_referral_check(context.bot, update.effective_user.id, vac_id)
        
        # Adminga tasdiqlash uchun yuborish
        await send_vacancy_to_admin(context.bot, vac_id)
        
    elif payload.startswith("pin_payment_"):
        vac_id = int(payload.split("_")[-1])
        pin_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
        
        await database.db_update_nuvi_vacancy(
            vac_id,
            pinned=True,
            pin_expires_at=pin_expires
        )
        
        vac = await database.db_get_nuvi_vacancy(vac_id)
        msg_id = vac.get("telegram_message_id") if vac else None
        if msg_id:
            try:
                await context.bot.pin_chat_message(chat_id=TARGET_CHANNEL, message_id=msg_id, disable_notification=False)
            except Exception as pin_err:
                logger.error(f"Failed to pin post {msg_id}: {pin_err}")
                
        await update.message.reply_text(
            f"🎉 To'lovingiz qabul qilindi! Sizning #{vac_id} e'loningiz kanalda 24 soatga pin qilindi."
        )
        
    elif payload.startswith("bump_payment_"):
        vac_id = int(payload.split("_")[-1])
        await update.message.reply_text(
            f"🎉 To'lovingiz qabul qilindi! Sizning #{vac_id} e'loningiz kanalda tepaga ko'tarildi (Bump)."
        )
        await bump_vacancy(context.bot, vac_id)

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
        
        # Trigger referral check
        await trigger_payment_referral_check(context.bot, vac["user_id"], vac_id)
        
    elif data.startswith("admin_approve_"):
        vac_id = int(data.split("_")[-1])
        # Bazani yangilaymiz
        await database.db_update_nuvi_vacancy(vac_id, status="approved")
        success, shifted = await database.db_align_vacancy_queue()
        await notify_shifted_vacancies(context.bot, shifted)
        
        vac = await database.db_get_nuvi_vacancy(vac_id)
        scheduled_for = vac["scheduled_for"] if (vac and vac["scheduled_for"]) else datetime.datetime.now()
        
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
        
    elif data.startswith("admin_pinconfirm_"):
        vac_id = int(data.split("_")[-1])
        vac = await database.db_get_nuvi_vacancy(vac_id)
        if vac:
            pin_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
            await database.db_update_nuvi_vacancy(vac_id, pinned=True, pin_expires_at=pin_expires)
            
            msg_id = vac.get("telegram_message_id")
            if msg_id:
                try:
                    await context.bot.pin_chat_message(chat_id=TARGET_CHANNEL, message_id=msg_id, disable_notification=False)
                except Exception as pin_err:
                    logger.error(f"Failed to pin post {msg_id}: {pin_err}")
                    
            await context.bot.send_message(
                chat_id=vac["user_id"],
                text=f"🎉 Tabriklaymiz! Sizning #{vac_id} e'loningiz uchun 24 soatlik pin xizmati tasdiqlandi va e'lon pin qilindi."
            )
            
            msg = query.message.caption if query.message.photo else query.message.text
            msg += "\n\n🟢 **PIN TO'LOVI TASDIQLANDI**"
            if query.message.photo:
                await query.message.edit_caption(caption=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
            else:
                await query.message.edit_text(text=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
                
    elif data.startswith("admin_pinreject_"):
        vac_id = int(data.split("_")[-1])
        vac = await database.db_get_nuvi_vacancy(vac_id)
        if vac:
            await context.bot.send_message(
                chat_id=vac["user_id"],
                text=f"❌ Kechirasiz, sizning #{vac_id} e'loningiz uchun 24 soatlik pin to'lovingiz admin tomonidan rad etildi."
            )
            
            msg = query.message.caption if query.message.photo else query.message.text
            msg += "\n\n🔴 **PIN TO'LOVI RAD ETILDI**"
            if query.message.photo:
                await query.message.edit_caption(caption=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
            else:
                await query.message.edit_text(text=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
                
    elif data.startswith("admin_bumpconfirm_"):
        vac_id = int(data.split("_")[-1])
        await bump_vacancy(context.bot, vac_id)
        
        msg = query.message.caption if query.message.photo else query.message.text
        msg += "\n\n🟢 **BUMP TO'LOVI TASDIQLANDI VA POST YANGILANDI**"
        if query.message.photo:
            await query.message.edit_caption(caption=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.edit_text(text=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
            
    elif data.startswith("admin_bumpreject_"):
        vac_id = int(data.split("_")[-1])
        vac = await database.db_get_nuvi_vacancy(vac_id)
        if vac:
            await context.bot.send_message(
                chat_id=vac["user_id"],
                text=f"❌ Kechirasiz, sizning #{vac_id} e'loningiz uchun tepaga ko'tarish (Bump) to'lovingiz admin tomonidan rad etildi."
            )
            
            msg = query.message.caption if query.message.photo else query.message.text
            msg += "\n\n🔴 **BUMP TO'LOVI RAD ETILDI**"
            if query.message.photo:
                await query.message.edit_caption(caption=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)
            else:
                await query.message.edit_text(text=msg, reply_markup=None, parse_mode=ParseMode.MARKDOWN)

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
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_vacancy_reply_markup(context.bot.username, vac)
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
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_vacancy_reply_markup(context.bot.username, vac)
                )
                post_success = True
                message_id = post_msg.message_id
            except Exception as e:
                logger.error(f"Text only post failed: {e}")
                
        if post_success:
            # Bazani yangilaymiz
            is_paid = vac.get("tariff") in ("vip", "premium", "pro")
            pin_expires = None
            if is_paid:
                pin_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
                
            await database.db_update_nuvi_vacancy(
                vac_id,
                status="posted",
                posted_at=datetime.datetime.now(datetime.timezone.utc),
                telegram_message_id=message_id,
                pinned=is_paid,
                pin_expires_at=pin_expires
            )
            logger.info(f"✅ Vakansiya #{vac_id} muvaffaqiyatli post qilindi (Msg ID: {message_id})")
            
            # Pinned message for paid tariffs (VIP, Premium, Pro)
            if is_paid:
                try:
                    await context.bot.pin_chat_message(
                        chat_id=TARGET_CHANNEL,
                        message_id=message_id,
                        disable_notification=False
                    )
                    logger.info(f"📌 Paid Vakansiya #{vac_id} ({vac.get('tariff')}) kanalda pin qilindi (Msg ID: {message_id})")
                except Exception as pin_err:
                    logger.error(f"Failed to pin paid vacancy #{vac_id}: {pin_err}")
            
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
            
            # Mos vakansiyalar obunachilarini xabardor qilish (Job Alerts)
            try:
                matched_user_ids = await database.db_get_matching_candidates(
                    vac_title=vac["title"],
                    vac_desc=vac["formatted_text"],
                    vac_skills=vac.get("skills", ""),
                    vac_loc=vac["location"]
                )
                for matched_uid in matched_user_ids:
                    if matched_uid == vac["user_id"]:
                        continue
                    try:
                        alert_msg = (
                            f"🔔 **Siz uchun yangi mos vakansiya topildi!**\n\n"
                            f"📌 **Lavozim:** {clean_for_markdown(vac['title'])}\n"
                            f"🏢 **Firma:** {clean_for_markdown(vac['company'])}\n"
                            f"📍 **Lokatsiya:** {clean_for_markdown(vac['location'])}\n"
                            f"💵 **Maosh:** {clean_for_markdown(vac['salary'])}\n\n"
                            f"🔗 **Batafsil ko'rish:** [Kanalda ko'rish]({post_link})\n"
                            f"🤖 **Ariza topshirish:** /start apply_{vac_id}"
                        )
                        await context.bot.send_message(
                            chat_id=matched_uid,
                            text=alert_msg,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception as notify_err:
                        logger.error(f"Failed to notify subscriber {matched_uid}: {notify_err}")
            except Exception as match_err:
                logger.error(f"Error matching job preferences: {match_err}")
            
            # Promo banner post logic
            try:
                posted_count = await database.db_get_posted_vacancies_count()
                if posted_count > 0 and posted_count % 10 == 0:
                    promo_banner_text = (
                        "🚀 **E'lon berishni xohlaysizmi?**\n\n"
                        "Bizning rasmiy botimiz orqali o'z vakansiyalaringizni tez va oson kanalga joylashingiz mumkin!\n\n"
                        "🤖 **Bot:** @nuvijobs_bot\n\n"
                        "🔹 **Qulayliklar:**\n"
                        "• Turli tarif rejalari (Pro, Premium, VIP)\n"
                        "• Tezkor to'lov tizimlari\n"
                        "• Navbat tizimi va tahrirlash imkoniyati\n\n"
                        "👉 Hozirroq botga o'ting va e'loningizni yarating!"
                    )
                    await context.bot.send_message(
                        chat_id=TARGET_CHANNEL,
                        text=promo_banner_text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    logger.info("Auto-promo banner posted to the channel.")
            except Exception as promo_err:
                logger.error(f"Failed to post auto-promo banner: {promo_err}")
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
        [InlineKeyboardButton("🎟 Yangi Promo-kod", callback_data="admin_create_promocode")],
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
    
    stats = await database.db_get_nuvi_detailed_stats()
    
    status_desc = {
        "draft": "Qoralama",
        "pending_payment": "To'lov kutilmoqda",
        "pending_approval": "Admindan tasdiq kutilmoqda",
        "approved": "Tasdiqlangan / Navbatda",
        "rejected": "Rad etilgan",
        "posted": "Kanalga joylangan",
        "closed": "Yopilgan"
    }
    
    status_str = ""
    for k, v in stats.get("status_breakdown", {}).items():
        desc = status_desc.get(k, k)
        status_str += f"  • {desc}: **{v}**\n"
        
    turnover = stats.get("total_turnover", 0)
    no_data_label = "  • Ma'lumot yo'q\n"
    
    msg = (
        f"📊 **BATAFSIL TIZIM STATISTIKASI**\n\n"
        f"👥 **Jami foydalanuvchilar:** {stats.get('total_users', 0)}\n"
        f"🔗 **Taklif orqali a'zo bo'lganlar:** {stats.get('referral_signups', 0)}\n"
        f"🎟 **Ishlatilgan promo-kodlar:** {stats.get('promocodes_used', 0)}\n\n"
        f"📝 **Jami vakansiyalar:** {stats.get('total_vacancies', 0)}\n"
        f"🟢 **Kanalga joylangan (posted):** {stats.get('total_posted', 0)}\n"
        f"⏳ **Kutilmoqda (pending):** {stats.get('total_pending', 0)}\n\n"
        f"⚙️ **Holatlar bo'yicha taqsimot:**\n{status_str or no_data_label}\n"
        f"💳 **Umumiy tushum (Turnover):** **{turnover:,} so'm**\n"
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
        [InlineKeyboardButton("🎟 Yangi Promo-kod", callback_data="admin_create_promocode")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("Nuvi Jobs Bot - Admin Boshqaruv Paneli:", reply_markup=reply_markup)

async def cb_admin_create_promocode_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Yangi promo-kod yaratishni boshlash."""
    query = update.callback_query
    if query.from_user.id != OWNER_ID:
        await query.answer("Ruxsat yo'q.")
        return ConversationHandler.END
    await query.answer()
    
    msg = (
        "🎟 **Yangi Promo-kod yaratish:**\n\n"
        "Iltimos, promo-kod ma'lumotlarini quyidagi formatda yuboring:\n"
        "`[KOD] [CHEGIRMA_FOIZI] [MAKSIMAL_FOYDALANISH]`\n\n"
        "Masalan: `NEWYEAR20 20 50` (Bu 20% chegirmali, 50 marta ishlatilishi mumkin bo'lgan NEWYEAR20 kodini yaratadi).\n\n"
        "Yuborish uchun pastdagi maydonga yozing:"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_CREATE_PROMOCODE

async def state_admin_promocode_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Promo-kod ma'lumotlari olindi."""
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Xato format! Iltimos quyidagi ko'rinishda yuboring:\n"
            "`KOD CHEGIRMA_FOIZI MAKSIMAL_FOYDALANISH` (masalan: `NEWYEAR20 20 50`):",
            parse_mode=ParseMode.MARKDOWN
        )
        return ADMIN_CREATE_PROMOCODE
        
    code = parts[0].upper()
    try:
        discount_pct = int(parts[1])
        max_uses = int(parts[2]) if len(parts) > 2 else 100
        
        if discount_pct < 0 or discount_pct > 100:
            await update.message.reply_text("❌ Xato! Chegirma foizi 0 va 100 oralig'ida bo'lishi kerak:")
            return ADMIN_CREATE_PROMOCODE
            
        success = await database.db_create_promocode(code, discount_pct=discount_pct, max_uses=max_uses)
        if success:
            await update.message.reply_text(
                f"✅ **Promo-kod muvaffaqiyatli yaratildi!**\n\n"
                f"🎟 Kod: `{code}`\n"
                f"💸 Chegirma: **{discount_pct}%**\n"
                f"⏳ Maksimal foydalanish: **{max_uses} marta**",
                parse_mode=ParseMode.MARKDOWN
            )
            # Send admin main menu again
            domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "jarvis-personal-bot-production.up.railway.app"
            web_app_url = f"https://{domain}/nuvi-stats"
            from telegram import WebAppInfo
            keyboard = [
                [InlineKeyboardButton("📊 Mini App (Statistika)", web_app=WebAppInfo(url=web_app_url))],
                [InlineKeyboardButton("📊 Tizim Statistikasi (Matnli)", callback_data="admin_stats")],
                [InlineKeyboardButton("📢 Yangi Rassilka", callback_data="admin_broadcast")],
                [InlineKeyboardButton("🎟 Yangi Promo-kod", callback_data="admin_create_promocode")],
                [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Nuvi Jobs Bot - Admin Boshqaruv Paneli:", reply_markup=reply_markup)
            return ConversationHandler.END
        else:
            await update.message.reply_text("❌ Bazaga yozishda xatolik yuz berdi. Iltimos qaytadan urining:")
            return ADMIN_CREATE_PROMOCODE
    except ValueError:
        await update.message.reply_text("❌ Xato! Chegirma foizi va maksimal foydalanish soni butun son (raqam) bo'lishi kerak:")
        return ADMIN_CREATE_PROMOCODE

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
    if not await check_user_subscription(update, context):
        return
        
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    vacs = await database.db_get_nuvi_vacancies_by_user(user_id)
    
    if not vacs:
        msg = "ℹ️ Sizda hali e'lonlar mavjud emas."
        keyboard = [[InlineKeyboardButton("⬅️ Menyuga qaytish", callback_data="nuvi_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        msg = "📊 **Sizning e'lonlaringiz:**\n\nBatafsil ko'rish va boshqarish uchun quyidagi tugmalardan birini tanlang:"
        keyboard = []
        for v in vacs[:10]:
            tariff_lbl = v.get("tariff", "pro").upper()
            status_lbl = v.get("status", "draft").upper()
            keyboard.append([InlineKeyboardButton(
                text=f"#{v['id']} | {v['title']} ({tariff_lbl} - {status_lbl})",
                callback_data=f"myvac_view_{v['id']}"
            )])
        keyboard.append([InlineKeyboardButton("⬅️ Menyuga qaytish", callback_data="nuvi_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def cb_bot_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot haqida ma'lumot (Legacy callback query support)."""
    if not await check_user_subscription(update, context):
        return
        
    query = update.callback_query
    await query.answer()
    
    price_pro = await get_tariff_price("pro")
    price_premium = await get_tariff_price("premium")
    price_vip = await get_tariff_price("vip")
    
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username or "nuvijobs_bot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{update.effective_user.id}"
    
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
        f"5. Navbati kelganda e'loningiz avtomatik kanalga chiqadi va sizga xabar keladi.\n\n"
        f"🎁 **Do'stlarni taklif qiling va chegirma oling!**\n"
        f"Sizning taklif havolangiz:\n"
        f"`{ref_link}`\n\n"
        f"Do'stingiz bot orqali o'zining birinchi pullik e'lonini berganda, sizga **10% chegirmali promo-kod** yuboriladi!"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Menyuga qaytish", callback_data="nuvi_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# ─── CV / REZYUME YARATUVCHI MODULI ───

async def cb_cv_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mening profilim / CV menyusi (Reply keyboard uchun)."""
    if not await check_user_subscription(update, context):
        return
        
    user_id = update.effective_user.id
    cv = await database.db_get_cv(user_id)
    
    keyboard = []
    if cv:
        msg = (
            f"👤 **Sizning CV ma'lumotlaringiz:**\n\n"
            f"✍️ **Ism:** {clean_for_markdown(cv['name'])}\n"
            f"📞 **Aloqa:** {clean_for_markdown(cv['contact'])}\n"
            f"💼 **Mutaxassislik:** {clean_for_markdown(cv['specialty'])}\n"
            f"⚙️ **Ko'nikmalar:** {clean_for_markdown(cv['skills'])}\n"
            f"🏫 **Ta'lim:** {clean_for_markdown(cv['education'])}\n"
            f"⏳ **Tajriba:** {clean_for_markdown(cv['experience'])}\n"
        )
        if cv.get("about"):
            msg += f"ℹ️ **O'zi haqida:** {clean_for_markdown(cv['about'])}\n"
            
        keyboard.append([InlineKeyboardButton("✏️ CVni tahrirlash", callback_data="cv_build_start")])
        keyboard.append([InlineKeyboardButton("📄 PDF yuklab olish", callback_data="cv_download_pdf")])
        keyboard.append([InlineKeyboardButton("🗑 CVni o'chirish", callback_data="cv_delete")])
    else:
        msg = (
            f"📝 **Sizda hali CV mavjud emas!**\n\n"
            f"Bot orqali bir necha daqiqada professional PDF formatidagi rezyume yaratishingiz va "
            f"uni to'g'ridan-to'g'ri vakansiyalarga ariza topshirishda foydalanishingiz mumkin."
        )
        keyboard.append([InlineKeyboardButton("✏️ Yangi CV yaratish", callback_data="cv_build_start")])
        
    keyboard.append([InlineKeyboardButton("⬅️ Bosh menyu", callback_data="nuvi_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def cb_cv_build_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """CV yaratish/tahrirlash FSM boshlanishi."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(
            "Keling, rezyumeingizni shakllantiramiz.\n\n"
            "Ism va familiyangizni kiriting:\n"
            "(Bekor qilish uchun /cancel deb yozing)",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text(
            "Keling, rezyumeingizni shakllantiramiz.\n\n"
            "Ism va familiyangizni kiriting:\n"
            "(Bekor qilish uchun /cancel deb yozing)",
            reply_markup=ReplyKeyboardRemove()
        )
    context.user_data["cv_draft"] = {}
    return CV_ASK_NAME

async def cv_state_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Iltimos, ism va familiyangizni to'g'ri kiriting:")
        return CV_ASK_NAME
    context.user_data["cv_draft"]["name"] = text
    await update.message.reply_text(
        "📞 Telefon raqamingiz yoki Telegram username (@) kiriting:"
    )
    return CV_ASK_CONTACT

async def cv_state_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Iltimos, aloqa ma'lumotingizni kiriting:")
        return CV_ASK_CONTACT
    context.user_data["cv_draft"]["contact"] = text
    await update.message.reply_text(
        "💼 Mutaxassisligingiz (Masalan: Python Developer, UI/UX Designer):"
    )
    return CV_ASK_SPECIALTY

async def cv_state_specialty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Iltimos, mutaxassisligingizni kiriting:")
        return CV_ASK_SPECIALTY
    context.user_data["cv_draft"]["specialty"] = text
    await update.message.reply_text(
        "⚙️ Ko'nikmalaringizni kiriting (vergul bilan ajrating, masalan: Python, SQL, Git):"
    )
    return CV_ASK_SKILLS

async def cv_state_skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Iltimos, ko'nikmalaringizni kiriting:")
        return CV_ASK_SKILLS
    context.user_data["cv_draft"]["skills"] = text
    await update.message.reply_text(
        "💼 Ish tajribangiz haqida yozing (masalan: 2 yil EPAM kompaniyasida, Freelance loyihalar):"
    )
    return CV_ASK_EXPERIENCE

async def cv_state_experience(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Iltimos, ish tajribangizni kiriting:")
        return CV_ASK_EXPERIENCE
    context.user_data["cv_draft"]["experience"] = text
    await update.message.reply_text(
        "🎓 Ma'lumotingiz yoki o'qish joyingiz (Masalan: TATU bakalavr, 2020-2024):"
    )
    return CV_ASK_EDUCATION

async def cv_state_education(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Iltimos, ta'lim ma'lumotini kiriting:")
        return CV_ASK_EDUCATION
    context.user_data["cv_draft"]["education"] = text
    await update.message.reply_text(
        "ℹ️ O'zingiz haqingizda qo'shimcha ma'lumot (Masalan: maqsadlaringiz, qiziqishlaringiz):"
    )
    return CV_ASK_ABOUT

async def cv_state_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["cv_draft"]["about"] = text
    
    waiting_msg = await update.message.reply_text("⏳ Rezyume tayyorlanmoqda, iltimos kuting...")
    user_id = update.effective_user.id
    
    cv_data = context.user_data["cv_draft"]
    
    # PDF fayl yaratish
    temp_dir = tempfile.gettempdir()
    pdf_path = os.path.join(temp_dir, f"cv_{user_id}.pdf")
    
    try:
        generate_cv_pdf(cv_data, pdf_path)
        
        # Telegramga yuklash
        with open(pdf_path, "rb") as pdf_file:
            doc_msg = await context.bot.send_document(
                chat_id=user_id,
                document=pdf_file,
                caption="✅ Sizning professional rezyumeingiz muvaffaqiyatli yaratildi va saqlandi!"
            )
            pdf_file_id = doc_msg.document.file_id
            
        # Bazaga yozish
        await database.db_save_cv(
            user_id=user_id,
            name=cv_data["name"],
            contact=cv_data["contact"],
            specialty=cv_data["specialty"],
            skills=cv_data["skills"],
            experience=cv_data["experience"],
            education=cv_data["education"],
            about=cv_data["about"],
            pdf_file_id=pdf_file_id
        )
        
        # Temp faylni o'chirish
        try:
            os.unlink(pdf_path)
        except:
            pass
            
        if waiting_msg:
            await waiting_msg.delete()
            
        # Orqaga bosh menyuni qaytarish
        keyboard = [
            ["💼 E'lon berish", "📊 Mening e'lonlarim"],
            ["📝 Mening profilim / CV", "🔔 Mos vakansiyalar obunasi"],
            ["🏢 Ish beruvchini baholash", "ℹ️ Bot haqida"],
        ]
        if user_id == OWNER_ID:
            keyboard.append(["⚙️ Admin panel"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("CV menyusiga qaytish uchun quyidagi tugmalardan foydalaning.", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error building CV PDF: {e}")
        await update.message.reply_text("❌ Rezyume yaratishda xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.")
        if waiting_msg:
            try:
                await waiting_msg.delete()
            except:
                pass
                
    return ConversationHandler.END

async def cb_cv_download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """PDF rezyumeni yuklab olish."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    cv = await database.db_get_cv(user_id)
    if not cv:
        await query.message.reply_text("❌ Rezyume topilmadi.")
        return
        
    if cv.get("pdf_file_id"):
        try:
            await context.bot.send_document(
                chat_id=user_id,
                document=cv["pdf_file_id"],
                caption=f"📄 **{clean_for_markdown(cv['name'])}** - Rezyume"
            )
            return
        except Exception as e:
            logger.warning(f"Could not send cached pdf_file_id: {e}. Regenerating...")
            
    # Regenerate PDF if file_id is lost or invalid
    temp_dir = tempfile.gettempdir()
    pdf_path = os.path.join(temp_dir, f"cv_{user_id}.pdf")
    try:
        generate_cv_pdf(cv, pdf_path)
        with open(pdf_path, "rb") as pdf_file:
            doc_msg = await context.bot.send_document(
                chat_id=user_id,
                document=pdf_file,
                caption=f"📄 **{clean_for_markdown(cv['name'])}** - Rezyume"
            )
            # Update file_id in database
            await database.db_save_cv(
                user_id=user_id,
                name=cv["name"],
                contact=cv["contact"],
                specialty=cv["specialty"],
                skills=cv["skills"],
                experience=cv["experience"],
                education=cv["education"],
                about=cv.get("about"),
                pdf_file_id=doc_msg.document.file_id
            )
        try:
            os.unlink(pdf_path)
        except:
            pass
    except Exception as err:
        logger.error(f"Error regenerating CV PDF: {err}")
        await query.message.reply_text("❌ Rezyumeni generatsiya qilishda xatolik yuz berdi.")

async def cb_cv_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rezyumeni o'chirish."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    try:
        pool = await database.get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM nuvi_cvs WHERE user_id = $1", user_id)
        await query.message.edit_text("🗑 Rezyumeingiz muvaffaqiyatli o'chirildi.", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Orqaga", callback_data="nuvi_menu")
        ]]))
    except Exception as e:
        logger.error(f"Error deleting CV: {e}")
        await query.message.reply_text("❌ Rezyumeni o'chirishda xatolik yuz berdi.")

async def cb_cv_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """CV yaratishni bekor qilish."""
    await cb_cv_menu(update, context)
    return ConversationHandler.END


# ─── JOB ALERTS / MOS VAKANSIYALAR OBUNASI MODULI ───

async def cb_pref_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Obuna menyusi (Reply keyboard uchun)."""
    if not await check_user_subscription(update, context):
        return
        
    user_id = update.effective_user.id
    pref = await database.db_get_preferences(user_id)
    
    keyboard = []
    if pref:
        status_str = "Faol 🟢" if pref["is_active"] else "Nofaol 🔴"
        msg = (
            f"🔔 **Sizning obuna sozlamalaringiz:**\n\n"
            f"🔑 **Kalit so'zlar:** {clean_for_markdown(pref['keywords'])}\n"
            f"📍 **Lokatsiya:** {clean_for_markdown(pref['location']) or 'Barchasi'}\n"
            f"🔔 **Holati:** {status_str}\n"
        )
        keyboard.append([InlineKeyboardButton("✏️ Obunani sozlash", callback_data="pref_setup_start")])
        toggle_lbl = "🔴 Obunani o'chirish" if pref["is_active"] else "🟢 Obunani yoqish"
        keyboard.append([InlineKeyboardButton(toggle_lbl, callback_data="pref_toggle")])
    else:
        msg = (
            f"🔔 **Mos vakansiyalar obunasi sozlanmagan!**\n\n"
            f"Kalit so'zlar va lokatsiyani kiriting, biz esa sizga mos vakansiya post "
            f"qilinganida darhol bot orqali xabar beramiz."
        )
        keyboard.append([InlineKeyboardButton("✏️ Obunani sozlash", callback_data="pref_setup_start")])
        
    keyboard.append([InlineKeyboardButton("⬅️ Bosh menyu", callback_data="nuvi_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def cb_pref_setup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Obunani sozlash FSM boshlanishi."""
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        "Mos vakansiyalarni filtrlash uchun kalit so'zlarni yuboring (vergul bilan ajratib, masalan: python, django, remote):\n"
        "(Bekor qilish uchun /cancel deb yozing)",
        reply_markup=ReplyKeyboardRemove()
    )
    return PREF_ASK_KEYWORDS

async def pref_state_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Iltimos, kalit so'zlarni kiriting:")
        return PREF_ASK_KEYWORDS
        
    context.user_data["pref_keywords"] = text
    
    keyboard = [
        ["Toshkent"],
        ["Masofaviy (Remote)"],
        ["Barchasi"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Istalgan lokatsiyani kiriting (masalan: Toshkent, Samarqand) yoki tanlang:",
        reply_markup=reply_markup
    )
    return PREF_ASK_LOCATION

async def pref_state_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Iltimos, lokatsiyani kiriting:")
        return PREF_ASK_LOCATION
        
    user_id = update.effective_user.id
    keywords = context.user_data["pref_keywords"]
    
    loc = text
    if text == "Barchasi":
        loc = ""
        
    # Save to database
    await database.db_save_preferences(user_id, keywords, loc, is_active=True)
    
    await update.message.reply_text("✅ Obuna sozlamalari muvaffaqiyatli saqlandi!")
    
    # Reset reply keyboard and show menu
    keyboard = [
        ["💼 E'lon berish", "📊 Mening e'lonlarim"],
        ["📝 Mening profilim / CV", "🔔 Mos vakansiyalar obunasi"],
        ["🏢 Ish beruvchini baholash", "ℹ️ Bot haqida"],
    ]
    if user_id == OWNER_ID:
        keyboard.append(["⚙️ Admin panel"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Asosiy menyuga qaytdik:", reply_markup=reply_markup)
    
    return ConversationHandler.END

async def cb_pref_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Obunani faollashtirish / o'chirish."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    pref = await database.db_get_preferences(user_id)
    if not pref:
        await query.message.reply_text("Mos obuna topilmadi.")
        return
        
    new_active = not pref["is_active"]
    await database.db_save_preferences(user_id, pref["keywords"], pref["location"], is_active=new_active)
    
    # Refresh preferences page
    await cb_pref_menu(update, context)

async def cb_pref_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Obuna sozlashni bekor qilish."""
    await cb_pref_menu(update, context)
    return ConversationHandler.END


# ─── NOMZODLARNI BOSHQARISH TIZIMI (ATS) ───

async def cb_apply_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ariza topshirish zanjiri boshlanishi (muqovali xat so'raladi)."""
    if not await check_user_subscription(update, context):
        return ConversationHandler.END
        
    query = update.callback_query
    await query.answer()
    
    vac_id = int(query.data.split("_")[-1])
    context.user_data["apply_vac_id"] = vac_id
    
    await query.message.reply_text(
        "Iltimos, ushbu vakansiya uchun muqovali xatingizni (o'zingiz haqingizda qisqacha ma'lumot va nega aynan siz munosibligingizni) yozib yuboring:\n"
        "(Bekor qilish uchun /cancel deb yozing)",
        reply_markup=ReplyKeyboardRemove()
    )
    return APPLY_ASK_COVER_LETTER

async def apply_state_cover_letter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Iltimos, muqovali xatingizni kiriting:")
        return APPLY_ASK_COVER_LETTER
        
    context.user_data["apply_cover_letter"] = text
    user_id = update.effective_user.id
    
    # Botda mavjud rezyume bor-yo'qligini tekshirish
    cv = await database.db_get_cv(user_id)
    
    keyboard = []
    if cv and cv.get("pdf_file_id"):
        keyboard.append([InlineKeyboardButton("📄 Botdagi rezyumeni yuborish", callback_data="apply_use_bot_cv")])
        
    keyboard.append([InlineKeyboardButton("❌ Rezyumesiz yuborish", callback_data="apply_no_cv")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Iltimos, rezyumeingizni (PDF formatida) yuklang yoki botdagi mavjud rezyumeingizni tanlang:",
        reply_markup=reply_markup
    )
    return APPLY_ASK_RESUME

async def apply_state_resume_doc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Nomzod o'zining PDF rezyumesini yuklaganda."""
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("Iltimos, faqat PDF formatidagi rezyume yuklang:")
        return APPLY_ASK_RESUME
        
    resume_file_id = doc.file_id
    return await submit_candidate_application(update, context, resume_file_id)

async def cb_apply_state_resume_btn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Nomzod mavjud rezyumeni tanlaganda yoki rezyumesiz topshirganda."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    action = query.data
    
    resume_file_id = None
    if action == "apply_use_bot_cv":
        cv = await database.db_get_cv(user_id)
        if cv and cv.get("pdf_file_id"):
            resume_file_id = cv["pdf_file_id"]
        else:
            await query.message.reply_text("Sizda hali botda rezyume yaratilmagan. Iltimos, rezyumeingizni PDF formatida yuklang:")
            return APPLY_ASK_RESUME
            
    return await submit_candidate_application(update, context, resume_file_id)

async def submit_candidate_application(update: Update, context: ContextTypes.DEFAULT_TYPE, resume_file_id: str = None) -> int:
    user = update.effective_user
    vac_id = context.user_data["apply_vac_id"]
    cover_letter = context.user_data["apply_cover_letter"]
    
    vac = await database.db_get_nuvi_vacancy(vac_id)
    if not vac:
        msg = "❌ Xatolik: Vakansiya topilmadi."
        if update.callback_query:
            await update.callback_query.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END
        
    # Arizani DBga yozish
    app_id = await database.db_create_application(
        vacancy_id=vac_id,
        candidate_id=user.id,
        cover_letter=cover_letter,
        resume_file_id=resume_file_id
    )
    
    if not app_id:
        msg = "❌ Arizani topshirishda xatolik yuz berdi."
        if update.callback_query:
            await update.callback_query.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
        return ConversationHandler.END
        
    success_msg = "✅ Arizangiz muvaffaqiyatli topshirildi! Ish beruvchi javobini bot orqali ma'lum qilamiz."
    if update.callback_query:
        await update.callback_query.message.reply_text(success_msg)
    else:
        await update.message.reply_text(success_msg)
        
    # Ish beruvchiga bildirishnoma yuborish
    try:
        employer_id = vac["user_id"]
        cand_name = clean_for_markdown(user.first_name)
        cand_username = f"@{user.username}" if user.username else "mavjud emas"
        
        emp_msg = (
            f"📩 **Yangi ariza kelib tushdi!**\n\n"
            f"📌 **Vakansiya:** {clean_for_markdown(vac['title'])} (#{vac_id})\n"
            f"👤 **Nomzod:** {cand_name} ({cand_username})\n\n"
            f"📝 **Muqovali xat:**\n"
            f"{clean_for_markdown(cover_letter)}\n"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Qabul qilish (Suhbat)", callback_data=f"app_accept_{app_id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"app_reject_{app_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if resume_file_id:
            await context.bot.send_document(
                chat_id=employer_id,
                document=resume_file_id,
                caption=emp_msg,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await context.bot.send_message(
                chat_id=employer_id,
                text=emp_msg,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as notify_err:
        logger.error(f"Error notifying employer of new application: {notify_err}")
        
    # Bosh menyuga qaytarish
    keyboard = [
        ["💼 E'lon berish", "📊 Mening e'lonlarim"],
        ["📝 Mening profilim / CV", "🔔 Mos vakansiyalar obunasi"],
        ["🏢 Ish beruvchini baholash", "ℹ️ Bot haqida"],
    ]
    if user.id == OWNER_ID:
        keyboard.append(["⚙️ Admin panel"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if update.callback_query:
        await update.callback_query.message.reply_text("Asosiy menyu:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Asosiy menyu:", reply_markup=reply_markup)
        
    return ConversationHandler.END

async def cb_app_accept_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ish beruvchi arizani qabul qilishni bosganda."""
    query = update.callback_query
    await query.answer()
    
    app_id = int(query.data.split("_")[-1])
    context.user_data["decision_app_id"] = app_id
    
    await query.message.reply_text(
        "Nomzodni suhbatga chaqirish uchun tafsilotlarni yozib yuboring (Masalan: sana, vaqt, joylashuv, manzil yoki havola):\n"
        "(Bekor qilish uchun /cancel deb yozing)",
        reply_markup=ReplyKeyboardRemove()
    )
    return EMPLOYER_INTERVIEW_MESSAGE

async def cb_app_reject_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ish beruvchi arizani rad etishni bosganda."""
    query = update.callback_query
    await query.answer()
    
    app_id = int(query.data.split("_")[-1])
    context.user_data["decision_app_id"] = app_id
    
    keyboard = [
        [InlineKeyboardButton("Standart rad etish xabari", callback_data="reject_default")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        "Nomzodga rad etish sababini yozib yuboring yoki standart matnni tanlang:",
        reply_markup=reply_markup
    )
    return EMPLOYER_REJECT_REASON

async def employer_state_interview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Iltimos, suhbat tafsilotlarini kiriting:")
        return EMPLOYER_INTERVIEW_MESSAGE
        
    app_id = context.user_data["decision_app_id"]
    
    # DBda statusni yangilash
    await database.db_update_application_status(app_id, "accepted")
    
    app = await database.db_get_application(app_id)
    if app:
        candidate_id = app["candidate_id"]
        # Nomzodni xabardor qilish
        try:
            msg = (
                f"🎉 **Xushxabar! Sizning arizangiz qabul qilindi!**\n\n"
                f"📌 **Vakansiya:** {clean_for_markdown(app['vacancy_title'])}\n"
                f"🏢 **Kompaniya:** {clean_for_markdown(app['vacancy_company'])}\n\n"
                f"⏱️ **Suhbat tafsilotlari:**\n"
                f"{clean_for_markdown(text)}"
            )
            await context.bot.send_message(
                chat_id=candidate_id,
                text=msg,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error notifying candidate: {e}")
            
    await update.message.reply_text("✅ Nomzodga suhbat taklifnomasi yuborildi.")
    
    # Asosiy menyu
    keyboard = [
        ["💼 E'lon berish", "📊 Mening e'lonlarim"],
        ["📝 Mening profilim / CV", "🔔 Mos vakansiyalar obunasi"],
        ["🏢 Ish beruvchini baholash", "ℹ️ Bot haqida"],
    ]
    if update.effective_user.id == OWNER_ID:
        keyboard.append(["⚙️ Admin panel"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Asosiy menyuga qaytdik:", reply_markup=reply_markup)
    
    return ConversationHandler.END

async def employer_state_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    app_id = context.user_data["decision_app_id"]
    
    reason = "Sizning nomzodingiz ushbu vakansiya talablariga to'liq mos kelmadi. Kelgusi faoliyatingizda muvaffaqiyatlar tilaymiz!"
    
    if query:
        await query.answer()
        await query.message.reply_text("✅ Standart rad etish xabari tanlandi.")
    else:
        reason = update.message.text.strip()
        
    # DBda statusni yangilash
    await database.db_update_application_status(app_id, "rejected")
    
    app = await database.db_get_application(app_id)
    if app:
        candidate_id = app["candidate_id"]
        # Nomzodni xabardor qilish
        try:
            msg = (
                f"🛑 **Arizangiz rad etildi**\n\n"
                f"📌 **Vakansiya:** {clean_for_markdown(app['vacancy_title'])}\n"
                f"🏢 **Kompaniya:** {clean_for_markdown(app['vacancy_company'])}\n\n"
                f"📝 **Sabab:**\n"
                f"{clean_for_markdown(reason)}"
            )
            await context.bot.send_message(
                chat_id=candidate_id,
                text=msg,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error notifying candidate: {e}")
            
    msg_text = "❌ Nomzodga rad etish xabari yuborildi."
    keyboard = [
        ["💼 E'lon berish", "📊 Mening e'lonlarim"],
        ["📝 Mening profilim / CV", "🔔 Mos vakansiyalar obunasi"],
        ["🏢 Ish beruvchini baholash", "ℹ️ Bot haqida"],
    ]
    if update.effective_user.id == OWNER_ID:
        keyboard.append(["⚙️ Admin panel"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if query:
        await query.message.reply_text(msg_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg_text, reply_markup=reply_markup)
        
    return ConversationHandler.END


# ─── REYTING VA BAHOLASH MODULI ───

async def cb_rate_employer_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ish beruvchini baholash FSM boshlanishi."""
    if not await check_user_subscription(update, context):
        return ConversationHandler.END
        
    user_id = update.effective_user.id
    apps = await database.db_get_candidate_applications(user_id)
    
    if not apps:
        await update.message.reply_text("Siz hali biror-bir vakansiyaga ariza topshirmagansiz, shuning uchun ish beruvchini baholay olmaysiz.")
        return ConversationHandler.END
        
    # Noyob ish beruvchilar ro'yxati
    seen = set()
    unique_employers = []
    for app in apps:
        emp_id = app["employer_id"]
        if emp_id not in seen and emp_id != user_id:
            seen.add(emp_id)
            unique_employers.append(app)
            
    if not unique_employers:
        await update.message.reply_text("Siz baholashingiz mumkin bo'lgan ish beruvchilar topilmadi.")
        return ConversationHandler.END
        
    keyboard = []
    for emp in unique_employers[:10]:
        keyboard.append([InlineKeyboardButton(
            text=emp["vacancy_company"],
            callback_data=f"rate_emp_{emp['employer_id']}"
        )])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Iltimos, baholamoqchi bo'lgan kompaniya / ish beruvchini tanlang:\n"
        "(Bekor qilish uchun /cancel deb yozing)",
        reply_markup=reply_markup
    )
    return RATING_ASK_STARS

async def cb_rate_employer_stars_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    employer_id = int(query.data.split("_")[-1])
    context.user_data["rate_employer_id"] = employer_id
    
    keyboard = [
        [
            InlineKeyboardButton("⭐ 1", callback_data="rate_star_1"),
            InlineKeyboardButton("⭐ 2", callback_data="rate_star_2"),
            InlineKeyboardButton("⭐ 3", callback_data="rate_star_3")
        ],
        [
            InlineKeyboardButton("⭐ 4", callback_data="rate_star_4"),
            InlineKeyboardButton("⭐ 5", callback_data="rate_star_5")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "Ushbu ish beruvchini necha yulduzcha bilan baholaysiz?",
        reply_markup=reply_markup
    )
    return RATING_ASK_STARS

async def cb_rate_employer_comment_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    stars = int(query.data.split("_")[-1])
    context.user_data["rate_stars"] = stars
    
    keyboard = [[InlineKeyboardButton("⏭️ Fikrsiz yuborish", callback_data="rate_comment_skip")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "Kompaniya haqida o'z fikringiz / izohingizni yozib yuboring:",
        reply_markup=reply_markup
    )
    return RATING_ASK_COMMENT

async def state_rate_employer_submit_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    comment = update.message.text.strip()
    return await submit_employer_review(update, context, comment)

async def cb_rate_employer_submit_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    return await submit_employer_review(update, context, None)

async def submit_employer_review(update: Update, context: ContextTypes.DEFAULT_TYPE, comment: str = None) -> int:
    user_id = update.effective_user.id
    employer_id = context.user_data["rate_employer_id"]
    stars = context.user_data["rate_stars"]
    
    # DBga yozish
    await database.db_save_review(employer_id, user_id, stars, comment)
    
    msg = "✅ Bahongiz muvaffaqiyatli qabul qilindi! Rahmat."
    
    # Kanaldagi postlarni tahrirlab verified badge va ratingni yangilash
    try:
        await update_employer_vacancies_in_channel(context, employer_id)
    except Exception as err:
        logger.error(f"Error updating employer vacancies in channel: {err}")
        
    keyboard = [
        ["💼 E'lon berish", "📊 Mening e'lonlarim"],
        ["📝 Mening profilim / CV", "🔔 Mos vakansiyalar obunasi"],
        ["🏢 Ish beruvchini baholash", "ℹ️ Bot haqida"],
    ]
    if user_id == OWNER_ID:
        keyboard.append(["⚙️ Admin panel"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if update.callback_query:
        await update.callback_query.message.reply_text(msg, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup)
        
    return ConversationHandler.END

async def update_employer_vacancies_in_channel(context: ContextTypes.DEFAULT_TYPE, employer_id: int) -> None:
    """Ish beruvchining kanaldagi barcha posted e'lonlarini yangi reyting bilan yangilaydi."""
    try:
        vacs = await database.db_get_nuvi_vacancies_by_user(employer_id)
        for vac in vacs:
            if vac.get("status") == "posted" and vac.get("telegram_message_id"):
                vac["user_id"] = employer_id
                new_text = await format_vacancy_text(vac)
                caption_text = escape_telegram_markdown(new_text)
                
                try:
                    await context.bot.edit_message_caption(
                        chat_id=TARGET_CHANNEL,
                        message_id=vac["telegram_message_id"],
                        caption=caption_text,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=get_vacancy_reply_markup(context.bot.username, vac)
                    )
                    logger.info(f"Dynamically updated channel message for vacancy #{vac['id']}")
                except Exception as edit_err:
                    logger.error(f"Failed to edit message {vac['telegram_message_id']}: {edit_err}")
    except Exception as e:
        logger.error(f"Error in update_employer_vacancies_in_channel: {e}")


# ─── REPLY KEYBOARD HELPERS FOR PUBLIC MENUS ───


async def cb_my_vacancies_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mening e'lonlarim ro'yxati (Reply keyboard uchun)."""
    if not await check_user_subscription(update, context):
        return
        
    user_id = update.effective_user.id
    vacs = await database.db_get_nuvi_vacancies_by_user(user_id)
    
    if not vacs:
        await update.message.reply_text("ℹ️ Sizda hali e'lonlar mavjud emas.")
    else:
        msg = "📊 **Sizning e'lonlaringiz:**\n\nBatafsil ko'rish va boshqarish uchun quyidagi tugmalardan birini tanlang:"
        keyboard = []
        for v in vacs[:10]:
            tariff_lbl = v.get("tariff", "pro").upper()
            status_lbl = v.get("status", "draft").upper()
            keyboard.append([InlineKeyboardButton(
                text=f"#{v['id']} | {v['title']} ({tariff_lbl} - {status_lbl})",
                callback_data=f"myvac_view_{v['id']}"
            )])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def cb_bot_info_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot haqida ma'lumot (Reply keyboard uchun)."""
    if not await check_user_subscription(update, context):
        return
        
    price_pro = await get_tariff_price("pro")
    price_premium = await get_tariff_price("premium")
    price_vip = await get_tariff_price("vip")
    
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username or "nuvijobs_bot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{update.effective_user.id}"
    
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
        f"5. Admin tekshiruvidan o'tgach, e'loningiz navbat bo'yicha avtomatik kanalga joylanadi.\n\n"
        f"🎁 *Do'stlarni taklif qiling va chegirma oling!*\n"
        f"Sizning taklif havolangiz:\n"
        f"`{ref_link}`\n\n"
        f"Do'stingiz bot orqali o'zining birinchi pullik e'lonini berganda, sizga **10% chegirmali promo-kod** yuboriladi!"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cb_my_vacancy_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Yakka vakansiyani ko'rish."""
    query = update.callback_query
    await query.answer()
    
    vac_id = int(query.data.split("_")[-1])
    vac = await database.db_get_nuvi_vacancy(vac_id)
    if not vac:
        await query.message.edit_text("❌ E'lon topilmadi.", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Orqaga", callback_data="nuvi_my_list")
        ]]))
        return
        
    p_status = vac["payment_status"]
    status = vac["status"]
    tariff = vac.get("tariff", "pro")
    
    status_map = {
        "draft": "Qoralama",
        "pending_payment": "To'lov kutilmoqda",
        "pending_approval": "Admindan tasdiq kutilmoqda",
        "approved": "Tasdiqlangan / Navbatda",
        "rejected": "Rad etilgan",
        "posted": "Kanalga joylangan ✅",
        "closed": "Yopilgan 🛑"
    }
    status_desc = status_map.get(status, status)
    
    tariff_map = {"pro": "Pro", "premium": "Premium", "vip": "VIP"}
    t_desc = tariff_map.get(tariff, "Pro")
    
    msg = (
        f"🆔 **Ariza #{vac['id']} ({t_desc})**\n\n"
        f"📌 **Lavozim:** {vac['title']}\n"
        f"🏢 **Firma:** {vac['company']}\n"
        f"💵 **Maosh:** {vac['salary']}\n"
        f"📍 **Hudud:** {vac['location']}\n"
        f"📈 **Holati:** {status_desc}\n"
        f"💳 **To'lov holati:** {p_status}\n"
    )
    if vac["pinned"]:
        msg += "📌 **Kanalda pin qilingan:** Ha ✅\n"
        if vac["pin_expires_at"]:
            tz = pytz.timezone("Asia/Tashkent")
            expires_tz = vac["pin_expires_at"].astimezone(tz)
            msg += f"⏳ **Pin tugash vaqti:** {expires_tz.strftime('%Y-%m-%d %H:%M')} (Toshkent vaqti)\n"
            
    if vac["rejection_reason"]:
        msg += f"\n⚠️ **Rad etish sababi:** {vac['rejection_reason']}\n"
        
    msg += f"\n**Ariza matni:**\n`{vac['formatted_text']}`"
    
    keyboard = []
    
    if status not in ("closed", "rejected"):
        keyboard.append([InlineKeyboardButton("✏️ Matnni tahrirlash", callback_data=f"myvac_edit_{vac_id}")])
        
    if status == "posted" and not vac["pinned"]:
        keyboard.append([InlineKeyboardButton("📌 24 soatga Pin qilish (15,000 so'm)", callback_data=f"myvac_pin_start_{vac_id}")])
        
    if status == "posted":
        keyboard.append([InlineKeyboardButton("🛑 Yopish (Nomzod topildi)", callback_data=f"myvac_close_{vac_id}")])
        keyboard.append([InlineKeyboardButton("🔄 Tepaga ko'tarish (5,000 so'm)", callback_data=f"myvac_bump_start_{vac_id}")])
        
    if status in ("posted", "closed") and vac.get("telegram_message_id"):
        keyboard.append([InlineKeyboardButton("🗑 Kanaldan o'chirish", callback_data=f"myvac_delete_{vac_id}")])
        
    keyboard.append([InlineKeyboardButton("⬅️ E'lonlar ro'yxatiga qaytish", callback_data="nuvi_my_list")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def cb_my_vacancy_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kanaldan o'chirish."""
    query = update.callback_query
    await query.answer()
    
    vac_id = int(query.data.split("_")[-1])
    vac = await database.db_get_nuvi_vacancy(vac_id)
    if not vac:
        await query.message.edit_text("❌ E'lon topilmadi.")
        return
        
    # Auth check: owner or admin
    if vac["user_id"] != query.from_user.id and query.from_user.id != OWNER_ID:
        await query.message.edit_text("❌ Ruxsat yo'q.")
        return
        
    msg_id = vac.get("telegram_message_id")
    if msg_id:
        try:
            await context.bot.delete_message(chat_id=TARGET_CHANNEL, message_id=msg_id)
            logger.info(f"Deleted vacancy #{vac_id} message {msg_id} from channel.")
        except Exception as e:
            logger.warning(f"Could not delete message {msg_id} from channel: {e}")
            
    await database.db_update_nuvi_vacancy(vac_id, status="closed", telegram_message_id=None, pinned=False)
    
    await query.message.edit_text(
        "🗑 E'lon kanaldan muvaffaqiyatli o'chirildi (Holati 'Yopilgan' deb o'zgartirildi).",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ E'lonlar ro'yxatiga qaytish", callback_data="nuvi_my_list")
        ]])
    )

async def cb_my_vacancy_bump_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tepaga ko'tarish (Bump) to'lovini boshlash."""
    query = update.callback_query
    await query.answer()
    
    vac_id = int(query.data.split("_")[-1])
    
    keyboard = []
    if PROVIDER_TOKEN:
        keyboard.append([InlineKeyboardButton("💳 Telegram orqali to'lov (Click/Payme)", callback_data=f"bump_pay_tg_{vac_id}")])
    keyboard.append([InlineKeyboardButton("📎 Karta orqali to'lov (Chek yuborish)", callback_data=f"bump_pay_manual_{vac_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Bekor qilish", callback_data=f"myvac_view_{vac_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = (
        f"🔄 **E'lonni tepaga ko'tarish (Bump):**\n\n"
        f"Xizmat narxi: **5,000 so'm**\n"
        f"E'loningiz kanaldan o'chirilib, yangidan chop etiladi. Natijada u kanal a'zolari feed'ining eng ostiga (ya'ni tepaga) tushadi.\n\n"
        f"Iltimos, to'lov usulini tanlang:"
    )
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def cb_bump_pay_tg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram billing orqali Bump to'lovi."""
    query = update.callback_query
    await query.answer()
    
    vac_id = int(query.data.split("_")[-1])
    await query.message.edit_text("To'lov hisobi tayyorlanmoqda, iltimos kuting...")
    
    title = f"Tepaga ko'tarish #{vac_id}"
    description = f"Nuvi Jobs kanalidagi #{vac_id} vakansiyani tepaga ko'tarish (Bump) to'lovi."
    payload = f"bump_payment_{vac_id}"
    currency = "UZS"
    prices = [LabeledPrice("Tepaga ko'tarish xizmati", 5000 * 100)]
    
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        start_parameter=f"bump_pay_{vac_id}"
    )

async def cb_bump_pay_manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Karta orqali Bump to'lovi boshlash."""
    query = update.callback_query
    await query.answer()
    
    vac_id = int(query.data.split("_")[-1])
    context.user_data["bump_vac_id"] = vac_id
    
    card = await get_card_details()
    msg = (
        f"💳 **Tepaga ko'tarish (Bump) to'lovi:**\n\n"
        f"Karta: `{card}`\n"
        f"Summa: **5,000 so'm**\n\n"
        f"To'lovni amalga oshirgach, to'lov chekini rasm shaklida shu yerga yuboring:"
    )
    keyboard = [[InlineKeyboardButton("🚫 Bekor qilish", callback_data=f"myvac_view_{vac_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return WAIT_BUMP_RECEIPT

async def cb_bump_pay_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bump to'lovini bekor qilish."""
    query = update.callback_query
    await query.answer()
    vac_id = context.user_data.get("bump_vac_id") or int(query.data.split("_")[-1])
    query.data = f"myvac_view_{vac_id}"
    await cb_my_vacancy_view(update, context)
    return ConversationHandler.END

async def state_bump_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bump to'lovi chekini olish."""
    photo = update.message.photo
    if not photo:
        await update.message.reply_text("Iltimos, to'lov chekini faqat Rasm shaklida yuboring:")
        return WAIT_BUMP_RECEIPT
        
    file_id = photo[-1].file_id
    vac_id = context.user_data.get("bump_vac_id")
    
    await update.message.reply_text(
        "Rahmat! To'lov cheki qabul qilindi. Admin tasdiqlagach, e'loningiz tepaga ko'tariladi (Bump).",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await cmd_start(update, context)
    await send_bump_payment_to_admin(context.bot, vac_id, file_id)
    return ConversationHandler.END

async def send_bump_payment_to_admin(bot, vacancy_id: int, receipt_file_id: str) -> None:
    """Admin kanaliga Bump to'lovini yuborish."""
    vac = await database.db_get_nuvi_vacancy(vacancy_id)
    if not vac:
        return
    msg = (
        f"🔄 **BUMP (TEPAGA KO'TARISH) UCHUN TO'LOV**\n\n"
        f"🆔 Ariza ID: #{vacancy_id}\n"
        f"📌 Lavozim: {vac['title']}\n"
        f"🏢 Firma: {vac['company']}\n"
        f"💵 Narx: 5,000 so'm (Bump / Up)\n"
        f"💳 To'lov turi: card_manual\n"
        f"📈 To'lov holati: manual_pending\n"
    )
    keyboard = [
        [InlineKeyboardButton("💳 Bump To'lovini Tasdiqlash", callback_data=f"admin_bumpconfirm_{vacancy_id}")],
        [InlineKeyboardButton("❌ Rad etish", callback_data=f"admin_bumpreject_{vacancy_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await bot.send_photo(
        chat_id=ADMIN_CHANNEL_ID,
        photo=receipt_file_id,
        caption=msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def bump_vacancy(bot, vacancy_id: int) -> bool:
    """E'lonni kanalda tepaga ko'taradi (Bump)."""
    try:
        vac = await database.db_get_nuvi_vacancy(vacancy_id)
        if not vac:
            return False
            
        old_msg_id = vac.get("telegram_message_id")
        
        if old_msg_id:
            try:
                await bot.delete_message(chat_id=TARGET_CHANNEL, message_id=old_msg_id)
                logger.info(f"Bump: Deleted old message {old_msg_id} for vacancy #{vacancy_id}")
            except Exception as delete_err:
                logger.warning(f"Bump: Could not delete old message {old_msg_id}: {delete_err}")
                
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"vacancy_bump_{vacancy_id}.png")
        
        img_success = generate_vacancy_cover(
            position=vac["title"],
            company=vac["company"],
            salary=vac["salary"],
            output_path=temp_path
        )
        
        caption_text = escape_telegram_markdown(vac["formatted_text"])
        post_success = False
        new_message_id = None
        
        bot_info = await bot.get_me()
        reply_markup = get_vacancy_reply_markup(bot_info.username, vac)
        
        if img_success and os.path.exists(temp_path):
            try:
                with open(temp_path, "rb") as photo:
                    post_msg = await bot.send_photo(
                        chat_id=TARGET_CHANNEL,
                        photo=photo,
                        caption=caption_text,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=reply_markup
                    )
                    post_success = True
                    new_message_id = post_msg.message_id
            except Exception as e:
                logger.error(f"Bump: Failed to post photo: {e}")
            try:
                os.unlink(temp_path)
            except:
                pass
                
        if not post_success:
            try:
                post_msg = await bot.send_message(
                    chat_id=TARGET_CHANNEL,
                    text=caption_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                post_success = True
                new_message_id = post_msg.message_id
            except Exception as e:
                logger.error(f"Bump text only failed: {e}")
                
        if post_success and new_message_id:
            await database.db_update_nuvi_vacancy(
                vacancy_id,
                telegram_message_id=new_message_id,
                posted_at=datetime.datetime.now(datetime.timezone.utc)
            )
            
            if vac["pinned"]:
                try:
                    await bot.pin_chat_message(
                        chat_id=TARGET_CHANNEL,
                        message_id=new_message_id,
                        disable_notification=False
                    )
                    logger.info(f"Bump: Re-pinned vacancy #{vacancy_id}")
                except Exception as pin_err:
                    logger.error(f"Bump: Failed to re-pin vacancy #{vacancy_id}: {pin_err}")
                    
            post_link = f"https://t.me/{TARGET_CHANNEL.replace('@', '')}/{new_message_id}"
            await bot.send_message(
                chat_id=vac["user_id"],
                text=(
                    f"🔄 E'loningiz kanalda muvaffaqiyatli tepaga ko'tarildi (Bump)!\n\n"
                    f"🔗 Yangi havola: [Nuvi Jobs Post]({post_link})"
                ),
                parse_mode=ParseMode.MARKDOWN
            )
            return True
            
        return False
    except Exception as err:
        logger.error(f"bump_vacancy error: {err}")
        return False

async def cb_my_vacancy_pin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pin qilish to'lovini boshlash."""
    query = update.callback_query
    await query.answer()
    
    vac_id = int(query.data.split("_")[-1])
    
    keyboard = []
    if PROVIDER_TOKEN:
        keyboard.append([InlineKeyboardButton("💳 Telegram orqali to'lov (Click/Payme)", callback_data=f"pin_pay_tg_{vac_id}")])
    keyboard.append([InlineKeyboardButton("📎 Karta orqali to'lov (Chek yuborish)", callback_data=f"pin_pay_manual_{vac_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Bekor qilish", callback_data=f"myvac_view_{vac_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = (
        f"📌 **E'lonni 24 soatga pin qilish:**\n\n"
        f"Xizmat narxi: **15,000 so'm**\n"
        f"E'loningiz Telegram kanalda 24 soat davomida eng yuqorida (pin) turadi.\n\n"
        f"Iltimos, to'lov usulini tanlang:"
    )
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def cb_pin_pay_tg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Telegram billing orqali Pin to'lovi."""
    query = update.callback_query
    await query.answer()
    
    vac_id = int(query.data.split("_")[-1])
    await query.message.edit_text("To'lov hisobi tayyorlanmoqda, iltimos kuting...")
    
    title = f"Pin qilish #{vac_id}"
    description = f"Nuvi Jobs kanalidagi #{vac_id} vakansiyani 24 soatga pin qilish to'lovi."
    payload = f"pin_payment_{vac_id}"
    currency = "UZS"
    prices = [LabeledPrice("24 soatlik Pin qilish xizmati", 15000 * 100)]
    
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        start_parameter=f"pin_pay_{vac_id}"
    )

async def cb_pin_pay_manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Karta orqali Pin to'lovi boshlash."""
    query = update.callback_query
    await query.answer()
    
    vac_id = int(query.data.split("_")[-1])
    context.user_data["pin_vac_id"] = vac_id
    
    card = await get_card_details()
    msg = (
        f"💳 **Pin xizmati to'lovi:**\n\n"
        f"Karta: `{card}`\n"
        f"Summa: **15,000 so'm**\n\n"
        f"To'lovni amalga oshirgach, to'lov chekini rasm shaklida shu yerga yuboring:"
    )
    keyboard = [[InlineKeyboardButton("🚫 Bekor qilish", callback_data=f"myvac_view_{vac_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return WAIT_PIN_RECEIPT

async def cb_pin_pay_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Pin to'lovini bekor qilish."""
    query = update.callback_query
    await query.answer()
    vac_id = context.user_data.get("pin_vac_id") or int(query.data.split("_")[-1])
    query.data = f"myvac_view_{vac_id}"
    await cb_my_vacancy_view(update, context)
    return ConversationHandler.END

async def state_pin_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Pin to'lovi chekini olish."""
    photo = update.message.photo
    if not photo:
        await update.message.reply_text("Iltimos, to'lov chekini faqat Rasm shaklida yuboring:")
        return WAIT_PIN_RECEIPT
        
    file_id = photo[-1].file_id
    vac_id = context.user_data.get("pin_vac_id")
    
    await update.message.reply_text(
        "Rahmat! Pin to'lovi cheki qabul qilindi. Admin tasdiqlagach, e'loningiz pin qilinadi.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    await cmd_start(update, context)
    await send_pin_payment_to_admin(context.bot, vac_id, file_id)
    return ConversationHandler.END

async def cb_my_vacancy_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Tahrirlashni boshlash."""
    query = update.callback_query
    await query.answer()
    
    vac_id = int(query.data.split("_")[-1])
    context.user_data["edit_vacancy_id"] = vac_id
    
    msg = (
        f"✏️ **Ariza #{vac_id} matnini tahrirlash:**\n\n"
        f"Iltimos, vakansiya uchun yangi to'liq matnni yuboring.\n"
        f"Eslatma: Yangi yuborilgan matn kanaldagi xabar matnini to'liq almashtiradi."
    )
    keyboard = [[InlineKeyboardButton("🚫 Bekor qilish", callback_data=f"myvac_view_{vac_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return EDIT_VACANCY_TEXT_STATE

async def cb_my_vacancy_edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Tahrirlashni bekor qilish."""
    query = update.callback_query
    await query.answer()
    vac_id = context.user_data.get("edit_vacancy_id") or int(query.data.split("_")[-1])
    query.data = f"myvac_view_{vac_id}"
    await cb_my_vacancy_view(update, context)
    return ConversationHandler.END

async def state_my_vacancy_edit_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Yangi tahrirlangan matnni qabul qilish."""
    new_text = update.message.text.strip()
    vac_id = context.user_data.get("edit_vacancy_id")
    
    if not vac_id:
        await update.message.reply_text("Xatolik yuz berdi. Tahrirlash bekor qilindi.")
        await cmd_start(update, context)
        return ConversationHandler.END
        
    await database.db_update_nuvi_vacancy(vac_id, formatted_text=new_text)
    
    vac = await database.db_get_nuvi_vacancy(vac_id)
    if vac and vac["status"] == "posted":
        await update_telegram_post(context.bot, vac)
        
    await update.message.reply_text(
        "✅ Vakansiya matni muvaffaqiyatli tahrirlandi!",
        reply_markup=ReplyKeyboardRemove()
    )
    await cmd_start(update, context)
    return ConversationHandler.END

async def cb_my_vacancy_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vakansiyani yopish."""
    query = update.callback_query
    await query.answer()
    
    vac_id = int(query.data.split("_")[-1])
    vac = await database.db_get_nuvi_vacancy(vac_id)
    if not vac:
        await query.message.edit_text("❌ Ariza topilmadi.")
        return
        
    new_formatted = f"🛑 NOMZOD TOPILDI\n\n{vac['formatted_text']}"
    await database.db_update_nuvi_vacancy(vac_id, formatted_text=new_formatted, status="closed", pinned=False)
    
    vac["formatted_text"] = new_formatted
    await update_telegram_post(context.bot, vac)
    
    msg_id = vac.get("telegram_message_id")
    if msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id=TARGET_CHANNEL, message_id=msg_id)
            logger.info(f"Unpinned closed vacancy #{vac_id}")
        except Exception as unpin_err:
            logger.warning(f"Failed to unpin closed vacancy #{vac_id}: {unpin_err}")
            
    await query.message.edit_text(
        f"🛑 E'lon #{vac_id} yopildi va kanaldagi xabar tahrirlandi (Nomzod topildi).",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ E'lonlar ro'yxati", callback_data="nuvi_my_list")
        ]])
    )

async def cb_my_vacancy_archive_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """14 kunlik arxiv so'rovnomasi tugmalari."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split("_")
    action = parts[1]
    vac_id = int(parts[2])
    
    if action == "archyes":
        vac = await database.db_get_nuvi_vacancy(vac_id)
        if vac:
            new_formatted = f"🛑 NOMZOD TOPILDI\n\n{vac['formatted_text']}"
            await database.db_update_nuvi_vacancy(vac_id, formatted_text=new_formatted, status="closed", pinned=False)
            
            vac["formatted_text"] = new_formatted
            await update_telegram_post(context.bot, vac)
            
            msg_id = vac.get("telegram_message_id")
            if msg_id:
                try:
                    await context.bot.unpin_chat_message(chat_id=TARGET_CHANNEL, message_id=msg_id)
                except:
                    pass
            await query.message.edit_text("🛑 E'lon yopildi va kanalda 'Nomzod topildi' deb belgilandi. Rahmat!")
    else:
        await query.message.edit_text("✅ Rahmat! E'loningiz kanalda faol holatda qoladi.")

async def send_pin_payment_to_admin(bot, vacancy_id: int, receipt_file_id: str) -> None:
    """Admin kanaliga Pin to'lovini yuborish."""
    vac = await database.db_get_nuvi_vacancy(vacancy_id)
    if not vac:
        return
    msg = (
        f"📌 **PIN XIZMATI UCHUN TO'LOV**\n\n"
        f"🆔 Ariza ID: #{vacancy_id}\n"
        f"📌 Lavozim: {vac['title']}\n"
        f"🏢 Firma: {vac['company']}\n"
        f"💵 Narx: 15,000 so'm (24 soatlik Pin)\n"
        f"💳 To'lov turi: card_manual\n"
        f"📈 To'lov holati: manual_pending\n"
    )
    keyboard = [
        [InlineKeyboardButton("💳 Pin To'lovini Tasdiqlash", callback_data=f"admin_pinconfirm_{vacancy_id}")],
        [InlineKeyboardButton("❌ Rad etish", callback_data=f"admin_pinreject_{vacancy_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await bot.send_photo(
        chat_id=ADMIN_CHANNEL_ID,
        photo=receipt_file_id,
        caption=msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def update_telegram_post(bot, vac: dict) -> None:
    """Telegram kanaldagi postni tahrirlash."""
    msg_id = vac.get("telegram_message_id")
    if not msg_id:
        return
    caption_text = escape_telegram_markdown(vac["formatted_text"])
    
    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username
    except Exception:
        bot_username = "nuvijobs_bot"
        
    reply_markup = get_vacancy_reply_markup(bot_username, vac)
    
    try:
        await bot.edit_message_caption(
            chat_id=TARGET_CHANNEL,
            message_id=msg_id,
            caption=caption_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        logger.info(f"Telegram post caption updated for vacancy #{vac['id']}")
    except Exception as e:
        logger.warning(f"Failed to edit caption, trying text edit: {e}")
        try:
            await bot.edit_message_text(
                chat_id=TARGET_CHANNEL,
                message_id=msg_id,
                text=caption_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            logger.info(f"Telegram post text updated for vacancy #{vac['id']}")
        except Exception as err2:
            logger.error(f"Failed to edit Telegram post for vacancy #{vac['id']}: {err2}")

async def nuvi_archive_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Chiqqaniga 14 kun bo'lgan e'lonlarni yopish haqida foydalanuvchidan so'raydi."""
    try:
        old_vacs = await database.db_get_nuvi_vacancies_to_archive()
        if not old_vacs:
            return
            
        for vac in old_vacs:
            vac_id = vac["id"]
            user_id = vac["user_id"]
            
            await database.db_mark_nuvi_vacancy_archive_prompted(vac_id)
            
            msg = (
                f"📋 Sizning **{vac['title']}** (*{vac['company']}*) bo'yicha e'loningiz kanalda chop etilganiga **14 kun** bo'ldi.\n\n"
                f"Ushbu vakansiya bo'yicha nomzod topildimi va e'lonni yopish kerakmi?"
            )
            keyboard = [
                [InlineKeyboardButton("🛑 Ha, yopilsin (Nomzod topildi)", callback_data=f"myvac_archyes_{vac_id}")],
                [InlineKeyboardButton("✅ Yo'q, hali ham faol", callback_data=f"myvac_archno_{vac_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=msg,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"Archive check query sent to user {user_id} for vacancy #{vac_id}")
            except Exception as notify_err:
                logger.warning(f"Failed to send archive query to user {user_id} for vacancy #{vac_id}: {notify_err}")
                
    except Exception as e:
        logger.error(f"nuvi_archive_job error: {e}")

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
6. QAT'IY RAVISHDA MATNNI QISQA QILING: Butun xabar matni o'ta ixcham va lo'nda bo'lishi shart. Talablar va takliflar ro'yxatida faqat eng asosiy 2-3 tadan ko'p bo'lmagan eng muhim punktlarni qoldiring, mayda gaplarni va ortiqcha tafsilotlarni kesib tashlang. Umumiy belgi soni 700 tadan oshmasligi kerak.
7. Har doim toza va chiroyli o'zbek tilida javob bering.
8. Javobingizda faqat tayyorlangan vakansiya matni bo'lsin, ortiqcha izoh yoki gap qo'shmang.
9. Shablon oxiridagi "[Nuvi Jobs](https://t.me/nuvi_jobs) - *ish va ishchi topishda yordam beramiz!*" qismini o'zgarishsiz, aynan qanday yozilgan bo'lsa shunday qoldiring.
10. Agar taqdim etilgan matn umuman vakansiya (ish yoki xodim e'loni) bo'lmasa, FAQAT 'NOT_A_VACANCY' deb javob bering. Boshqa hech qanday so'z yoki izoh yozmang.
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
            # Final sanity trim to guarantee fits in 1000 chars caption limit
            formatted = trim_to_fit_caption(formatted, max_chars=980)
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


async def save_scraped_vacancy_to_db(formatted_text: str, bot=None) -> Optional[int]:
    """Scraped vakansiyani bazaga saqlaydi va navbatni tekislaydi."""
    try:
        import database
        pos, comp, sal = extract_meta_for_cover(formatted_text)
        
        # System scraper userini yaratish/tekshirish
        await database.db_upsert_nuvi_user(1, "system_scraper", "Scraper")
        
        # Vakansiya yaratish
        vac_id = await database.db_create_nuvi_vacancy(
            user_id=1,
            title=pos,
            company=comp,
            salary=sal,
            location="Toshkent",
            working_hours="Shart emas",
            requirements="Shart emas",
            skills="Shart emas",
            benefits="Shart emas",
            contact="Kanalda ko'rsatilgan",
            formatted_text=formatted_text,
            tariff="scraped"
        )
        
        if vac_id:
            # Statusni tasdiqlangan va to'lovni free qilamiz
            await database.db_update_nuvi_vacancy(
                vac_id,
                status="approved",
                payment_status="free"
            )
            # Navbatni tekislaymiz
            success, shifted = await database.db_align_vacancy_queue()
            if bot and success and shifted:
                await notify_shifted_vacancies(bot, shifted)
            return vac_id
        return None
    except Exception as e:
        logger.error(f"save_scraped_vacancy_to_db error: {e}")
        return None


async def vacancy_scraper_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har soatda 8:00 dan 22:00 gacha yangi vakansiyalarni tekshiradi va bazadagi navbatga qo'shadi."""
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
            if not formatted or "xato" in formatted.lower() or "not_a_vacancy" in formatted.lower() or "kechirasiz" in formatted.lower() or "vakansiya emas" in formatted.lower():
                logger.warning(f"Non-vacancy or error response from AI vacancy formatting: {formatted[:60]}...")
                # Also mark it as processed in DB so we don't try to scrape it again and again
                await database.db_add_processed_vacancy(vac["channel_id"], vac["msg_id"])
                continue

            # Bazaga saqlash va navbatga qo'yish
            vac_id = await save_scraped_vacancy_to_db(formatted, bot=context.bot)
            if vac_id:
                # Mark as processed in DB
                await database.db_add_processed_vacancy(vac["channel_id"], vac["msg_id"])
                logger.info(f"✅ Scraped vacancy #{vac_id} saved to DB and queue aligned.")
                break
                
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
                f"1. Ikkinchi Telegram akkauntingizda Telegram sozlamalaridan '{folder_name}' nomli papka yarating va unga vakansiya o'qiladigan kanallarni qo'shing.\n"
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
            if not formatted or "xato" in formatted.lower() or "not_a_vacancy" in formatted.lower() or "kechirasiz" in formatted.lower() or "vakansiya emas" in formatted.lower():
                await database.db_add_processed_vacancy(vac["channel_id"], vac["msg_id"])
                await update.message.reply_text("⚠️ Ushbu matn vakansiya emas, o'tkazib yuborildi.")
                continue
                
            # Bazaga saqlash va navbatga qo'yish
            vac_id = await save_scraped_vacancy_to_db(formatted, bot=context.bot)
            if vac_id:
                await database.db_add_processed_vacancy(vac["channel_id"], vac["msg_id"])
                await update.message.reply_text(
                    f"✅ Vakansiya bazaga saqlandi va navbatga qo'shildi! (ID: #{vac_id})"
                )
                break
            else:
                await update.message.reply_text("❌ Vakansiyani bazaga saqlashda xatolik yuz berdi.")
            
        if not found_any:
            await update.message.reply_text("ℹ️ Barcha topilgan vakansiyalar oldin qayta ishlangan. Yangisi yo'q.")
            
    except Exception as e:
        logger.error(f"Manual scrape error: {e}")
        await update.message.reply_text(f"❌ Xatolik yuz berdi: {e}")


async def nuvi_vip_auto_approve_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """VIP tarifda bo'lgan va 15 daqiqa davomida admin ko'rib chiqmagan arizalarni auto-approve qiladi."""
    try:
        import database
        import datetime
        import pytz
        
        pool = await database.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, user_id, title, company 
                FROM nuvi_vacancies 
                WHERE tariff = 'vip' 
                  AND status = 'pending_approval' 
                  AND payment_status = 'paid' 
                  AND updated_at <= NOW() - INTERVAL '15 minutes'
            """)
            
            if not rows:
                return
                
            for r in rows:
                vac_id = r["id"]
                user_id = r["user_id"]
                logger.info(f"⏳ VIP Vakansiya #{vac_id} admin tasdiqlovini 15 daqiqa kutdi. Tizim avtomatik tasdiqlaydi...")
                
                await database.db_update_nuvi_vacancy(vac_id, status="approved")
                await database.db_align_vacancy_queue()
                
                vac = await database.db_get_nuvi_vacancy(vac_id)
                tz = pytz.timezone("Asia/Tashkent")
                scheduled_for = vac["scheduled_for"].astimezone(tz) if (vac and vac.get("scheduled_for")) else datetime.datetime.now(tz)
                time_str = scheduled_for.strftime("%Y-%m-%d %H:%M")
                
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"⚡️ Sizning VIP e'lon #{vac_id} 15 daqiqa ichida adminlar tomonidan tasdiqlanmaganligi sababli, "
                            f"tizim tomonidan **avtomatik tarzda tasdiqlandi** va navbatga qo'yildi!\n"
                            f"⏰ Taxminiy chop etish vaqti: **{time_str}** (Toshkent vaqti bilan)."
                        ),
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as user_err:
                    logger.error(f"Failed to notify user {user_id} of auto-approval: {user_err}")
                    
                try:
                    await context.bot.send_message(
                        chat_id=OWNER_ID,
                        text=(
                            f"⚠️ **VIP Auto-Approval**:\n"
                            f"E'lon #{vac_id} ({r['title']} - {r['company']}) 15 daqiqa ichida qo'lda ko'rib chiqilmadi.\n"
                            f"Tizim uni avtomatik tasdiqladi va **{time_str}** ga rejalashtirdi."
                        )
                    )
                except Exception as admin_err:
                    logger.error(f"Failed to notify admin of auto-approval: {admin_err}")
                    
    except Exception as e:
        logger.error(f"nuvi_vip_auto_approve_job error: {e}")


async def nuvi_unpin_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Post qilinganiga 1 soatdan oshgan pullik e'lonlarni unpin qiladi."""
    try:
        import database
        to_unpin = await database.db_get_pinned_nuvi_vacancies_to_unpin()
        if not to_unpin:
            return
            
        for vac in to_unpin:
            vac_id = vac["id"]
            msg_id = vac["telegram_message_id"]
            logger.info(f"⏰ Paid Vakansiya #{vac_id} pin qilinganiga 1 soat bo'ldi. Unpin qilinmoqda...")
            try:
                await context.bot.unpin_chat_message(
                    chat_id=TARGET_CHANNEL,
                    message_id=msg_id
                )
            except Exception as unpin_err:
                logger.warning(f"Failed to unpin message #{msg_id} on channel: {unpin_err} (already unpinned or chat issue)")
                
            # Update in DB
            await database.db_update_nuvi_vacancy(vac_id, pinned=False)
    except Exception as e:
        logger.error(f"nuvi_unpin_job error: {e}")


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
    app.job_queue.run_repeating(nuvi_auto_post_job, interval=60, first=10)
    app.job_queue.run_repeating(nuvi_vip_auto_approve_job, interval=60, first=30)
    app.job_queue.run_repeating(nuvi_unpin_job, interval=60, first=45)
    app.job_queue.run_repeating(vacancy_scraper_job, interval=3600, first=60)
    app.job_queue.run_repeating(nuvi_archive_job, interval=86400, first=3600)
    
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
            EDIT_BEFORE_SEND_CHOOSE_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_edit_before_send_choose_field)],
            EDIT_BEFORE_SEND_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_edit_before_send_input)],
            CHOOSE_TARIFF: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_choose_tariff_received)],
            ENTER_PROMOCODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_enter_promocode)],
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
    
    # ─── CONVERSATION HANDLER FOR CV BUILDER ───
    cv_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_cv_build_start, pattern="^cv_build_start$")
        ],
        states={
            CV_ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_state_name)],
            CV_ASK_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_state_contact)],
            CV_ASK_SPECIALTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_state_specialty)],
            CV_ASK_SKILLS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_state_skills)],
            CV_ASK_EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_state_experience)],
            CV_ASK_EDUCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_state_education)],
            CV_ASK_ABOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cv_state_about)]
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_cv_cancel, pattern="^cv_cancel$")
        ],
        allow_reentry=True
    )
    app.add_handler(cv_conv)
    
    # ─── CONVERSATION HANDLER FOR JOB ALERTS PREFERENCES ───
    pref_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_pref_setup_start, pattern="^pref_setup_start$")
        ],
        states={
            PREF_ASK_KEYWORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, pref_state_keywords)],
            PREF_ASK_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, pref_state_location)]
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_pref_cancel, pattern="^pref_cancel$")
        ],
        allow_reentry=True
    )
    app.add_handler(pref_conv)
    
    # ─── CONVERSATION HANDLER FOR ATS (APPLY) ───
    apply_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_apply_start, pattern="^apply_vac_\\d+$")
        ],
        states={
            APPLY_ASK_COVER_LETTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, apply_state_cover_letter)],
            APPLY_ASK_RESUME: [
                MessageHandler(filters.Document.PDF, apply_state_resume_doc),
                CallbackQueryHandler(cb_apply_state_resume_btn, pattern="^(apply_use_bot_cv|apply_no_cv)$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True
    )
    app.add_handler(apply_conv)
    
    # ─── CONVERSATION HANDLER FOR EMPLOYER DECISIONS ───
    employer_decision_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_app_accept_start, pattern="^app_accept_\\d+$"),
            CallbackQueryHandler(cb_app_reject_start, pattern="^app_reject_\\d+$")
        ],
        states={
            EMPLOYER_INTERVIEW_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, employer_state_interview)],
            EMPLOYER_REJECT_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, employer_state_reject),
                CallbackQueryHandler(employer_state_reject, pattern="^reject_default$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True
    )
    app.add_handler(employer_decision_conv)
    
    # ─── CONVERSATION HANDLER FOR CANDIDATE RATING ───
    rating_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🏢 Ish beruvchini baholash$"), cb_rate_employer_start)
        ],
        states={
            RATING_ASK_STARS: [
                CallbackQueryHandler(cb_rate_employer_stars_selection, pattern="^rate_emp_\\d+$"),
                CallbackQueryHandler(cb_rate_employer_comment_prompt, pattern="^rate_star_\\d+$")
            ],
            RATING_ASK_COMMENT: [
                CallbackQueryHandler(cb_rate_employer_submit_skip, pattern="^rate_comment_skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, state_rate_employer_submit_text)
            ]
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True
    )
    app.add_handler(rating_conv)

    
    # ─── CONVERSATION HANDLER FOR VACANCY EDIT ───
    edit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_my_vacancy_edit_start, pattern="^myvac_edit_(\d+)$")
        ],
        states={
            EDIT_VACANCY_TEXT_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, state_my_vacancy_edit_received),
                CallbackQueryHandler(cb_my_vacancy_edit_cancel, pattern="^myvac_view_")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_my_vacancy_edit_cancel, pattern="^myvac_view_")
        ],
        allow_reentry=True
    )
    app.add_handler(edit_conv)
    
    # ─── CONVERSATION HANDLER FOR PIN PAYMENT ───
    pin_pay_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_pin_pay_manual_start, pattern="^pin_pay_manual_(\d+)$")
        ],
        states={
            WAIT_PIN_RECEIPT: [
                MessageHandler(filters.PHOTO, state_pin_receipt_received),
                CallbackQueryHandler(cb_pin_pay_cancel, pattern="^myvac_view_")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_pin_pay_cancel, pattern="^myvac_view_")
        ],
        allow_reentry=True
    )
    app.add_handler(pin_pay_conv)
    
    # ─── CONVERSATION HANDLER FOR BUMP PAYMENT ───
    bump_pay_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_bump_pay_manual_start, pattern="^bump_pay_manual_(\\d+)$")
        ],
        states={
            WAIT_BUMP_RECEIPT: [
                MessageHandler(filters.PHOTO, state_bump_receipt_received),
                CallbackQueryHandler(cb_bump_pay_cancel, pattern="^myvac_view_")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_bump_pay_cancel, pattern="^myvac_view_")
        ],
        allow_reentry=True
    )
    app.add_handler(bump_pay_conv)
    
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
    
    # ─── CONVERSATION HANDLER FOR ADMIN PROMO CODE CREATION ───
    admin_create_promo_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_admin_create_promocode_start, pattern="^admin_create_promocode$")
        ],
        states={
            ADMIN_CREATE_PROMOCODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, state_admin_promocode_received)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CallbackQueryHandler(cb_admin_back, pattern="^admin_back$")
        ],
        allow_reentry=True
    )
    app.add_handler(admin_create_promo_conv)
    
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
    app.add_handler(MessageHandler(filters.Regex("^📝 Mening profilim / CV$"), cb_cv_menu))
    app.add_handler(MessageHandler(filters.Regex("^🔔 Mos vakansiyalar obunasi$"), cb_pref_menu))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ Bot haqida$"), cb_bot_info_text))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ Admin panel$"), cmd_admin))
    
    # ─── USER CALLBACKS ───
    app.add_handler(CallbackQueryHandler(cb_check_sub, pattern="^nuvi_check_sub$"))
    app.add_handler(CallbackQueryHandler(cmd_start, pattern="^nuvi_menu$"))
    app.add_handler(CallbackQueryHandler(cb_my_vacancies, pattern="^nuvi_my_list$"))
    app.add_handler(CallbackQueryHandler(cb_bot_info, pattern="^nuvi_info$"))
    app.add_handler(CallbackQueryHandler(cb_my_vacancy_view, pattern="^myvac_view_(\d+)$"))
    app.add_handler(CallbackQueryHandler(cb_my_vacancy_pin_start, pattern="^myvac_pin_start_(\d+)$"))
    app.add_handler(CallbackQueryHandler(cb_pin_pay_tg, pattern="^pin_pay_tg_(\d+)$"))
    app.add_handler(CallbackQueryHandler(cb_my_vacancy_close, pattern="^myvac_close_(\d+)$"))
    app.add_handler(CallbackQueryHandler(cb_my_vacancy_archive_decision, pattern="^myvac_arch(yes|no)_(\d+)$"))
    app.add_handler(CallbackQueryHandler(cb_my_vacancy_delete, pattern="^myvac_delete_(\d+)$"))
    app.add_handler(CallbackQueryHandler(cb_my_vacancy_bump_start, pattern="^myvac_bump_start_(\d+)$"))
    app.add_handler(CallbackQueryHandler(cb_bump_pay_tg, pattern="^bump_pay_tg_(\d+)$"))
    app.add_handler(CallbackQueryHandler(cb_cv_menu, pattern="^cv_menu$"))
    app.add_handler(CallbackQueryHandler(cb_cv_download, pattern="^cv_download_pdf$"))
    app.add_handler(CallbackQueryHandler(cb_cv_delete, pattern="^cv_delete$"))
    app.add_handler(CallbackQueryHandler(cb_pref_menu, pattern="^pref_menu$"))
    app.add_handler(CallbackQueryHandler(cb_pref_toggle, pattern="^pref_toggle$"))

    
    # ─── PUBLIC COMMANDS ───
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("scrape", cmd_scrape))
    
    app.run_polling()

if __name__ == "__main__":
    main()
