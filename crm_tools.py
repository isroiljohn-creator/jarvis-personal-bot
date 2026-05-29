"""
crm_tools.py — Biznes va CRM moduli:
9. Mijoz suhbati tahlili
20. Kontakt CRM (Notion orqali)
"""
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("jarvis.crm")


# ─────────────────────────────────────────
# 9. MIJOZ SUHBATI TAHLILI
# ─────────────────────────────────────────

def prepare_lead_analysis_prompt(conversation_text: str, contact_name: str = "") -> str:
    """Mijoz suhbatini tahlil qilish uchun AI prompti."""
    return (
        f"Sen tajribali savdo mutaxasssissan. Quyidagi mijoz suhbatini tahlil qil:\n\n"
        f"{'Mijoz: ' + contact_name if contact_name else ''}\n"
        f"SUHBAT:\n{conversation_text}\n\n"
        f"Quyidagi formatda O'zbek tilida javob ber:\n\n"
        f"LEAD DARAJASI: [Sovuq/Iliq/Issiq] (0-100%)\n"
        f"ASOSIY E'TIROZLAR: [ro'yxat]\n"
        f"QIZIQISH SOHASI: [nima qiziqtirdi]\n"
        f"TAVSIYA: [keyingi qadam — nima deyish, qachon aloqa]\n"
        f"XAVF: [nima sabab yo'qotishi mumkin]\n"
        f"YUTISH STRATEGIYASI: [aniq taklif]"
    )


# ─────────────────────────────────────────
# 20. KONTAKT CRM
# ─────────────────────────────────────────

def prepare_crm_entry_prompt(note: str) -> str:
    """Tabiiy til eslatmasidan CRM ma'lumot ajratish prompti."""
    return (
        "Foydalanuvchi kontakt haqida eslatma qoldirdi. JSON formatida ajrat:\n"
        "{\n"
        '  "name": "Kontakt ismi",\n'
        '  "summary": "Nima haqida gaplashildi (qisqa)",\n'
        '  "next_action": "Keyingi qadam",\n'
        '  "follow_up_days": 3,\n'
        '  "status": "Iliq",\n'
        '  "tags": ["tag1", "tag2"]\n'
        "}\n\n"
        f"Eslatma: {note}\n\n"
        "Faqat JSON qaytarilsin."
    )


async def save_crm_contact(cloud, name: str, summary: str, next_action: str,
                            follow_up_days: int = 3, status: str = "Iliq",
                            tags: list = None) -> str:
    """Kontaktni Notion CRM ga saqlash."""
    try:
        follow_up_date = (datetime.now() + timedelta(days=follow_up_days)).strftime("%Y-%m-%d")
        title = f"{name} — {summary[:50]}"

        # Notion sahifasi yaratish
        result = await cloud.notion_add_page(
            title=title,
            content=(
                f"**Kontakt:** {name}\n"
                f"**Xulosa:** {summary}\n"
                f"**Keyingi qadam:** {next_action}\n"
                f"**Follow-up:** {follow_up_date}\n"
                f"**Status:** {status}\n"
                f"**Teglar:** {', '.join(tags or [])}\n"
            ),
            database_type="crm"
        )
        return (
            f"✅ {name} CRM ga qo'shildi.\n"
            f"Keyingi qadam: {next_action}\n"
            f"Follow-up: {follow_up_date}"
        )
    except Exception as e:
        logger.error(f"CRM saqlash xatosi: {e}")
        # Fallback: Notion task sifatida saqlash
        try:
            await cloud.notion_add_task(
                title=f"[CRM] {name}: {next_action}",
                status="Kutilmoqda"
            )
            return (
                f"✅ {name} Notion vazifasiga qo'shildi.\n"
                f"Keyingi qadam: {next_action}"
            )
        except Exception as e2:
            return f"❌ CRM saqlash xatosi: {e2}"
