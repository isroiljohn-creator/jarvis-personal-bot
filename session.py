"""
Jarvis Umumiy Sessiya Moduli.
Telegram Bot va iOS PWA bir xil suhbat tarixidan foydalanadi.
"""
from collections import deque
from datetime import datetime

# ─── Bitta global tarix — ikkala kanaldan to'ldiriladi ──────
SHARED_HISTORY: deque = deque(maxlen=30)  # So'nggi 30 ta xabar

def add_to_history(role: str, text: str, source: str = "telegram"):
    """Suhbat tarixiga yozuv qo'shadi. source: 'telegram' | 'ios'"""
    SHARED_HISTORY.append({
        "role": role,
        "parts": [text],
        "source": source,
        "time": datetime.now().strftime("%H:%M")
    })

def get_history() -> list:
    """Gemini formatiga mos tarixni qaytaradi."""
    return [{"role": h["role"], "parts": h["parts"]} for h in SHARED_HISTORY]

def get_history_display() -> list:
    """iOS/UI uchun to'liq ma'lumotli tarix."""
    return list(SHARED_HISTORY)

def clear_history():
    SHARED_HISTORY.clear()
