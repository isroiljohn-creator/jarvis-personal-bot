"""
Jarvis Umumiy Sessiya — PostgreSQL ga asoslangan.
Telegram Bot va iOS PWA bir xil suhbat tarixini ko'radi.
"""
import logging
from database import db_add_message, db_get_history, db_get_history_display, db_clear_history

logger = logging.getLogger("jarvis.session")

async def add_to_history(role: str, text: str, source: str = "telegram"):
    """Suhbat tarixiga yozuv qo'shadi — PostgreSQL ga."""
    try:
        await db_add_message(role, text, source)
    except Exception as e:
        logger.error(f"add_to_history xatosi: {e}")

async def get_history(limit: int = 30) -> list:
    """So'nggi xabarlarni Gemini formatida qaytaradi."""
    try:
        return await db_get_history(limit)
    except Exception as e:
        logger.error(f"get_history xatosi: {e}")
        return []

async def get_history_display(limit: int = 50) -> list:
    """UI uchun to'liq tarix."""
    try:
        return await db_get_history_display(limit)
    except Exception as e:
        logger.error(f"get_history_display xatosi: {e}")
        return []

async def clear_history():
    """Barcha suhbat tarixini o'chiradi."""
    try:
        await db_clear_history()
    except Exception as e:
        logger.error(f"clear_history xatosi: {e}")
