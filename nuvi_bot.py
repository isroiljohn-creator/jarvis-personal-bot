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

# Logger sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("nuvi_bot")

# ──────────────────────── SOZLAMALAR ─────────────────────────

NUVI_BOT_TOKEN = os.environ.get("NUVI_BOT_TOKEN")
if not NUVI_BOT_TOKEN:
    logger.error("NUVI_BOT_TOKEN env o'zgaruvchisi topilmadi! Bot ishga tusha olmaydi.")
    sys.exit(1)

OWNER_ID = int(os.environ.get("OWNER_TELEGRAM_ID", "1392501306"))
ADMIN_CHANNEL_ID = int(os.environ.get("NUVI_ADMIN_CHANNEL_ID", str(OWNER_ID)))
TARGET_CHANNEL = os.environ.get("NUVI_TARGET_CHANNEL", "@nuvi_jobs")
PROVIDER_TOKEN = os.environ.get("PAYMENT_PROVIDER_TOKEN") # Click/Payme Telegram billing uchun
VACANCY_PRICE = int(os.environ.get("NUVI_VACANCY_PRICE_UZS", "30000")) # 30,000 UZS default
CARD_DETAILS = os.environ.get("NUVI_VACANCY_CARD_DETAILS", "8600 0000 0000 0000 (Nuvi Jobs)")

# Conversation holatlari
(
    ASK_TITLE,
    ASK_COMPANY,
    ASK_SALARY,
    ASK_LOCATION,
    ASK_WORKING_HOURS,
    ASK_REQUIREMENTS,
    ASK_BENEFITS,
    ASK_CONTACT,
    CONFIRM_PREVIEW,
    CHOOSE_PAYMENT_METHOD,
    WAIT_MANUAL_RECEIPT,
) = range(11)

# Broadcast holatlari
(
    BROADCAST_ASK_MSG,
    BROADCAST_CONFIRM,
) = range(11, 13)

# ──────────────────────── YORDAMCHI FUNKSIYALAR ─────────────────────────

def clean_for_markdown(text: str) -> str:
    """Telegram Markdown uchun belgilarni tozalaydi."""
    if not text:
        return ""
    for ch in ("*", "_", "`", "#"):
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

def format_vacancy_text(data: dict) -> str:
    """Vakansiya ma'lumotlarini chiroyli shablonga soladi."""
    title = clean_for_markdown(data.get("title", ""))
    company = clean_for_markdown(data.get("company", ""))
    salary = clean_for_markdown(data.get("salary", ""))
    location = clean_for_markdown(data.get("location", ""))
    hours = clean_for_markdown(data.get("working_hours", ""))
    reqs = clean_for_markdown(data.get("requirements", ""))
    benefits = clean_for_markdown(data.get("benefits", ""))
    contact = clean_for_markdown(data.get("contact", ""))
    
    # Reqs va benefits'ni chiroyli formatlash
    req_lines = "\n".join([f"— {line.strip()}" for line in reqs.split("\n") if line.strip()])
    benefit_lines = "\n".join([f"— {line.strip()}" for line in benefits.split("\n") if line.strip()])
    
    text = f"📌 *{title}*\n\n"
    text += f"🏢 *Firma:* {company}\n"
    text += f"💵 *Maosh:* {salary}\n"
    text += f"📍 *Lokatsiya:* {location}\n"
    if hours:
        text += f"⏱️ *Ish vaqti:* {hours}\n"
        
    text += f"\n📝 *Talablar:*\n{req_lines}\n"
    if benefit_lines:
        text += f"\n🎁 *Taklif:*\n{benefit_lines}\n"
        
    text += f"\n📩 *Aloqa:* {contact}\n\n"
    text += f"[Nuvi Jobs](https://t.me/nuvi_jobs) - *ish va ishchi topishda bepul yordam beramiz!*"
    return text

async def calculate_next_post_time() -> datetime.datetime:
    """E'lonlar orasida 2 soatlik interval va 09:00 - 22:00 vaqt cheklovi bilan navbat hisoblaydi."""
    pool = await database.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT scheduled_for FROM nuvi_vacancies 
            WHERE status = 'approved' AND posted_at IS NULL 
            ORDER BY scheduled_for DESC 
            LIMIT 1
        """)
    
    tz = pytz.timezone("Asia/Tashkent")
    now_tz = datetime.datetime.now(tz)
    
    # Agar kelajakda allaqachon rejalashtirilgan post bo'lsa, undan 2 soat keyinga qo'yamiz
    if row and row["scheduled_for"]:
        base_time = row["scheduled_for"].astimezone(tz)
        if base_time > now_tz:
            next_time = base_time + datetime.timedelta(hours=2)
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
        # Hozirgi vaqtga joylaymiz
        scheduled_tz = now_tz
        
    return scheduled_tz

# ──────────────────────── FOYDALANUVCHI ZANJIRI (CONVERSATION) ─────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bot boshlanishi."""
    user = update.effective_user
    await database.db_upsert_nuvi_user(user.id, user.username, user.first_name)
    
    keyboard = [
        [InlineKeyboardButton("➕ Yangi vakansiya yaratish", callback_data="nuvi_create")],
        [InlineKeyboardButton("📊 Mening e'lonlarim", callback_data="nuvi_my_list")],
        [InlineKeyboardButton("ℹ️ Bot haqida / Qo'llanma", callback_data="nuvi_info")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = (
        f"Assalomu alaykum, {user.first_name}!\n"
        f"Nuvi Jobs e'lon berish botiga xush kelibsiz.\n\n"
        f"Bu yerda kanalda vakansiya e'lon qilish uchun ariza topshirishingiz, "
        f"to'lov qilishingiz va navbat asosida e'loningizni avtomatik chop etishingiz mumkin."
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(msg, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup)
    return ConversationHandler.END

async def cb_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Vakansiya yaratishni boshlash."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear() # Avvalgi ma'lumotlarni tozalash
    
    await query.message.reply_text(
        "Keling, vakansiyani shakllantiramiz.\n\n"
        "1-qadam: **Lavozim nomini** kiriting (masalan: *SMM mutaxassis*, *Python dasturchi*):",
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_TITLE

async def state_ask_company(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kompaniya nomini so'rash."""
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Lavozim nomi bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
        return ASK_TITLE
    context.user_data["title"] = title
    
    await update.message.reply_text(
        "2-qadam: **Kompaniya / Firma nomini** kiriting (masalan: *Adjaster .uz*):",
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_COMPANY

async def state_ask_salary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maoshni so'rash."""
    company = update.message.text.strip()
    if not company:
        await update.message.reply_text("Kompaniya nomi bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
        return ASK_COMPANY
    context.user_data["company"] = company
    
    await update.message.reply_text(
        "3-qadam: **Ish haqi / Maosh miqdorini** kiriting (masalan: *3 000 000 so'm* yoki *Kelishiladi*):",
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_SALARY

async def state_ask_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Lokatsiyani so'rash."""
    salary = update.message.text.strip()
    if not salary:
        await update.message.reply_text("Maosh bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return ASK_SALARY
    context.user_data["salary"] = salary
    
    await update.message.reply_text(
        "4-qadam: **Lokatsiya / Ish joyini** kiriting (masalan: *Toshkent shahri*, *Farg'ona* yoki *Masofaviy (Remote)*):",
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_LOCATION

async def state_ask_working_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ish vaqtini so'rash."""
    location = update.message.text.strip()
    if not location:
        await update.message.reply_text("Lokatsiya bo'sh bo'lishi mumkin emas. Qayta kiriting:")
        return ASK_LOCATION
    context.user_data["location"] = location
    
    await update.message.reply_text(
        "5-qadam: **Ish vaqtini / Grafikni** kiriting (masalan: *09:00 - 18:00* yoki *Moslashuvchan grafik*):",
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_WORKING_HOURS

async def state_ask_requirements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Talablarni so'rash."""
    hours = update.message.text.strip()
    context.user_data["working_hours"] = hours
    
    await update.message.reply_text(
        "6-qadam: Nomzodga qo'yiladigan **Talablarni** kiriting.\n"
        "Har bir talabni alohida yangi qatordan yozishingiz mumkin:",
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_REQUIREMENTS

async def state_ask_benefits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kompaniya takliflarini so'rash."""
    reqs = update.message.text.strip()
    if not reqs:
        await update.message.reply_text("Kamida bitta talab kiritishingiz kerak. Qayta kiriting:")
        return ASK_REQUIREMENTS
    context.user_data["requirements"] = reqs
    
    await update.message.reply_text(
        "7-qadam: Kompaniya tomonidan **Takliflar / Afzalliklarni** kiriting (masalan: *shinam ofis, bepul tushlik, o'sish imkoniyati*).\n"
        "Yangi qatordan yozishingiz mumkin:",
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_BENEFITS

async def state_ask_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Aloqani so'rash."""
    benefits = update.message.text.strip()
    context.user_data["benefits"] = benefits
    
    await update.message.reply_text(
        "8-qadam: **Aloqa uchun kontakt ma'lumotlarini** kiriting (masalan: *@ism_admin* yoki telefon raqam):",
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_CONTACT

async def state_generate_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Vakansiya preview'ini yaratish va ko'rsatish."""
    contact = update.message.text.strip()
    if not contact:
        await update.message.reply_text("Aloqa ma'lumotlari majburiy. Iltimos, qaytadan kiriting:")
        return ASK_CONTACT
    context.user_data["contact"] = contact
    
    # Kutib turish xabarini yuborish
    waiting_msg = await update.message.reply_text("⏳ Oblojka va e'lon matni tayyorlanmoqda, iltimos kuting...")
    
    formatted_text = format_vacancy_text(context.user_data)
    context.user_data["formatted_text"] = formatted_text
    
    # Surat yaratish
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"vacancy_preview_{update.effective_user.id}.png")
    
    img_success = generate_vacancy_cover(
        position=context.user_data["title"],
        company=context.user_data["company"],
        salary=context.user_data["salary"],
        output_path=temp_path
    )
    
    await waiting_msg.delete()
    
    if img_success and os.path.exists(temp_path):
        keyboard = [
            [InlineKeyboardButton("✅ Tasdiqlash va To'lovga o'tish", callback_data="preview_confirm")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="preview_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        with open(temp_path, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=f"Vakansiya e'loni kanalda quyidagicha ko'rinadi:\n\n{escape_telegram_markdown(formatted_text)}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        try:
            os.unlink(temp_path)
        except:
            pass
        return CONFIRM_PREVIEW
    else:
        # Rasmsiz oddiy matnli preview
        keyboard = [
            [InlineKeyboardButton("✅ Tasdiqlash va To'lovga o'tish", callback_data="preview_confirm")],
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="preview_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Vakansiya e'loni kanalda quyidagicha ko'rinadi (suratsiz):\n\n{escape_telegram_markdown(formatted_text)}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return CONFIRM_PREVIEW

async def cb_preview_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Preview tasdiqlangach, to'lov usulini tanlashni so'raydi."""
    query = update.callback_query
    await query.answer()
    
    # Bazaga e'lonni 'draft' holatida saqlaymiz
    vacancy_id = await database.db_create_nuvi_vacancy(
        user_id=update.effective_user.id,
        title=context.user_data["title"],
        company=context.user_data["company"],
        salary=context.user_data["salary"],
        location=context.user_data["location"],
        working_hours=context.user_data["working_hours"],
        requirements=context.user_data["requirements"],
        benefits=context.user_data["benefits"],
        contact=context.user_data["contact"],
        formatted_text=context.user_data["formatted_text"]
    )
    context.user_data["vacancy_id"] = vacancy_id
    
    keyboard = []
    # Telegram Click/Payme ulanishini tekshirish
    if PROVIDER_TOKEN:
        keyboard.append([InlineKeyboardButton("💳 Telegram orqali to'lash (Click/Payme)", callback_data="pay_telegram")])
    keyboard.append([InlineKeyboardButton("📎 Karta orqali qo'lda to'lash (Chek yuborish)", callback_data="pay_manual")])
    keyboard.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="preview_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = (
        f"Vakansiya qabul qilindi!\n\n"
        f"E'lon joylashtirish narxi: **{VACANCY_PRICE:,} so'm**.\n"
        f"Iltimos, to'lov turini tanlang:"
    )
    await query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    return CHOOSE_PAYMENT_METHOD

async def cb_preview_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Yaratishni bekor qilish."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Vakansiya yaratish bekor qilindi.")
    return await cmd_start(update, context)

# ──────────────────────── TO'LOVLAR TIZIMI ─────────────────────────

async def cb_pay_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Telegram Invoice yuborish."""
    query = update.callback_query
    await query.answer()
    
    vac_id = context.user_data.get("vacancy_id")
    title = f"Vakansiya e'loni #{vac_id}"
    description = f"Nuvi Jobs kanalida vakansiya e'lonini joylash to'lovi."
    payload = f"vacancy_payment_{vac_id}"
    currency = "UZS"
    # Telegram UZS ni tiyinlarda hisoblaydi (1 sum = 100 tiyin)
    prices = [LabeledPrice("Vakansiya e'loni", VACANCY_PRICE * 100)]
    
    # Bazada statusni o'zgartiramiz
    await database.db_update_nuvi_vacancy(vac_id, status="pending_payment", payment_method="telegram_billing")
    
    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token=PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        start_parameter="nuvi-jobs-payment"
    )
    return ConversationHandler.END

async def cb_pay_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Karta raqamini ko'rsatib, chek rasmini kutish."""
    query = update.callback_query
    await query.answer()
    
    vac_id = context.user_data.get("vacancy_id")
    await database.db_update_nuvi_vacancy(vac_id, status="pending_payment", payment_method="card_manual")
    
    msg = (
        f"Karta raqami: `{CARD_DETAILS}`\n"
        f"To'lov summasi: **{VACANCY_PRICE:,} so'm**\n\n"
        f"To'lovni amalga oshirgach, iltimos **to'lov chekini (skrinshot yoki rasmini)** shu yerga yuboring.\n"
        f"Admin to'lovni tasdiqlagandan so'ng ariza ko'rib chiqiladi."
    )
    await query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    return WAIT_MANUAL_RECEIPT

async def state_manual_receipt_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Karta to'lovi kvitansiyasi olinganda."""
    photo = update.message.photo
    if not photo:
        await update.message.reply_text("Iltimos, to'lov chekini faqat Rasm shaklida yuboring:")
        return WAIT_MANUAL_RECEIPT
    
    file_id = photo[-1].file_id
    vac_id = context.user_data.get("vacancy_id")
    
    # Bazani yangilaymiz
    await database.db_update_nuvi_vacancy(
        vac_id, 
        status="pending_approval", 
        payment_status="manual_pending", 
        payment_receipt=file_id
    )
    
    await update.message.reply_text(
        "Rahmat! To'lov cheki qabul qilindi. Admin tekshiruvidan so'ng e'loningiz rejalashtiriladi."
    )
    
    # Adminga tasdiqlash uchun xabar yuborish
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
    
    # Admin xabari matni
    msg = (
        f"🔔 **YANGI ARIZA TUSHDI**\n\n"
        f"🆔 Ariza ID: #{vacancy_id}\n"
        f"📌 Lavozim: {title}\n"
        f"🏢 Firma: {company}\n"
        f"💵 Maosh: {salary}\n"
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
        scheduled_for = await calculate_next_post_time()
        
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
        vac = await database.db_get_nuvi_vacancy(vac_id)
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
    if update.effective_user.id != OWNER_ID:
        return
        
    keyboard = [
        [InlineKeyboardButton("📊 Tizim Statistikasi", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Yangi Rassilka", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Nuvi Jobs Bot - Admin Boshqaruv Paneli:", reply_markup=reply_markup)

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
    keyboard = [
        [InlineKeyboardButton("📊 Tizim Statistikasi", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Yangi Rassilka", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⚙️ Sozlamalar", callback_data="admin_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text("Nuvi Jobs Bot - Admin Boshqaruv Paneli:", reply_markup=reply_markup)

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
    """Bot haqida ma'lumot."""
    query = update.callback_query
    await query.answer()
    
    msg = (
        f"ℹ️ **Nuvi Jobs Bot haqida:**\n\n"
        f"Ushbu bot orqali `@nuvi_jobs` kanaliga osongina vakansiya e'lonlarini joylashingiz mumkin.\n\n"
        f"💰 E'lon joylash narxi: **{VACANCY_PRICE:,} so'm**.\n\n"
        f"**Jarayon ketma-ketligi:**\n"
        f"1. So'rovnomadagi savollarga javob berasiz.\n"
        f"2. E'lon namunasi (oblojka surat va matn) sizga ko'rsatiladi.\n"
        f"3. Siz to'lovni Telegram (Click/Payme) yoki karta orqali bajarasiz.\n"
        f"4. Admin tekshiruvdan o'tkazgandan keyin ariza tasdiqlanadi va navbatga qo'yiladi.\n"
        f"5. Navbati kelganda e'loningiz avtomatik kanalga chiqadi va sizga xabar keladi."
    )
    keyboard = [[InlineKeyboardButton("⬅️ Menyuga qaytish", callback_data="nuvi_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# ──────────────────────── BOSHQA / ERROR HANDLERS ─────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hozirgi suhbatni bekor qilish."""
    await update.message.reply_text("Suhbat bekor qilindi.")
    return await cmd_start(update, context)

# ──────────────────────── MAIN ASSEMBLY ─────────────────────────

def main():
    """Bot ishga tushirish."""
    logger.info("🤖 Nuvi Jobs Bot ishga tushmoqda...")
    
    # DB initialization
    loop = asyncio.get_event_loop()
    loop.run_until_complete(database.init_db())
    
    app = Application.builder().token(NUVI_BOT_TOKEN).build()
    
    # ─── JOB QUEUE FOR AUTO-POSTING ───
    # Har 10 daqiqada auto-posting navbatini tekshirib boradi
    app.job_queue.run_repeating(nuvi_auto_post_job, interval=600, first=10)
    
    # ─── CONVERSATION HANDLER FOR VACANCY ───
    vacancy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_create_start, pattern="^nuvi_create$")],
        states={
            ASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_company)],
            ASK_COMPANY: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_salary)],
            ASK_SALARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_location)],
            ASK_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_working_hours)],
            ASK_WORKING_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_requirements)],
            ASK_REQUIREMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_benefits)],
            ASK_BENEFITS: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_ask_contact)],
            ASK_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, state_generate_preview)],
            CONFIRM_PREVIEW: [
                CallbackQueryHandler(cb_preview_confirm, pattern="^preview_confirm$"),
                CallbackQueryHandler(cb_preview_cancel, pattern="^preview_cancel$")
            ],
            CHOOSE_PAYMENT_METHOD: [
                CallbackQueryHandler(cb_pay_telegram, pattern="^pay_telegram$"),
                CallbackQueryHandler(cb_pay_manual, pattern="^pay_manual$"),
                CallbackQueryHandler(cb_preview_cancel, pattern="^preview_cancel$")
            ],
            WAIT_MANUAL_RECEIPT: [
                MessageHandler(filters.PHOTO, state_manual_receipt_received),
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
    
    # ─── ADMIN CALLBACKS ───
    app.add_handler(CallbackQueryHandler(admin_buttons_callback, pattern="^admin_"))
    
    # ─── ADMIN COMMANDS ───
    app.add_handler(CommandHandler("admin", cmd_admin))
    
    # ─── USER CALLBACKS ───
    app.add_handler(CallbackQueryHandler(cmd_start, pattern="^nuvi_menu$"))
    app.add_handler(CallbackQueryHandler(cb_my_vacancies, pattern="^nuvi_my_list$"))
    app.add_handler(CallbackQueryHandler(cb_bot_info, pattern="^nuvi_info$"))
    
    # ─── PUBLIC COMMANDS ───
    app.add_handler(CommandHandler("start", cmd_start))
    
    # Botni ishga tushirish (Polling yordamida)
    app.run_polling()

if __name__ == "__main__":
    main()
