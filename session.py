"""
Jarvis Umumiy Sessiya — PostgreSQL ga asoslangan.
Telegram Bot va iOS PWA bir xil suhbat tarixini ko'radi.
"""
import asyncio, logging
from database import db_add_message, db_get_history, db_get_history_display, db_clear_history

logger = logging.getLogger("jarvis.session")

def add_to_history(role: str, text: str, source: str = "telegram"):
    """Suhbat tarixiga yozuv qo'shadi — PostgreSQL ga."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(db_add_message(role, text, source))
        else:
            loop.run_until_complete(db_add_message(role, text, source))
    except Exception as e:
        logger.error(f"add_to_history xatosi: {e}")

def get_history(limit: int = 30) -> list:
    """So'nggi xabarlarni Gemini formatida qaytaradi."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                fut = pool.submit(_run_async, db_get_history(limit))
                return fut.result(timeout=8)
        return loop.run_until_complete(db_get_history(limit))
    except Exception as e:
        logger.error(f"get_history xatosi: {e}")
        return []

def get_history_display(limit: int = 50) -> list:
    """UI uchun to'liq tarix."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                fut = pool.submit(_run_async, db_get_history_display(limit))
                return fut.result(timeout=8)
        return loop.run_until_complete(db_get_history_display(limit))
    except Exception as e:
        logger.error(f"get_history_display xatosi: {e}")
        return []

def clear_history():
    """Barcha suhbat tarixini o'chiradi."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(db_clear_history())
        else:
            loop.run_until_complete(db_clear_history())
    except Exception as e:
        logger.error(f"clear_history xatosi: {e}")

def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
