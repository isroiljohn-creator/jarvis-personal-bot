"""
scheduler_tools.py — Rejalashtiruvchi moduli:
12. Telegram kanal scheduler
19. Post Scheduler (har qanday chat/guruh/kanal)
"""
import json
import logging
import os
from datetime import datetime
import pytz

logger = logging.getLogger("jarvis.scheduler")

SCHEDULE_FILE = "/data/scheduled_posts.json"
TZ = pytz.timezone("Asia/Tashkent")


def _load_posts() -> list:
    try:
        with open(SCHEDULE_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_posts(posts: list) -> None:
    os.makedirs("/data", exist_ok=True)
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def schedule_post(
    chat_id: str,
    chat_name: str,
    text: str,
    send_at: str,  # "2026-05-30T10:00:00" yoki "ertaga 10:00"
    post_type: str = "message",  # "message" | "channel"
) -> str:
    """Post rejalash."""
    # Vaqtni parse qilish
    try:
        if "T" in send_at:
            send_dt = datetime.fromisoformat(send_at)
        else:
            # Oddiy format: "ertaga 10:00", "yaqin 30 daqiqada"
            return "❌ Vaqtni ISO formatida bering: '2026-05-30T10:00:00'"

        # Timezone qo'shish
        if send_dt.tzinfo is None:
            send_dt = TZ.localize(send_dt)

        posts = _load_posts()
        post_id = f"post_{len(posts)+1}_{int(datetime.now().timestamp())}"
        posts.append({
            "id": post_id,
            "chat_id": str(chat_id),
            "chat_name": chat_name,
            "text": text,
            "send_at": send_dt.isoformat(),
            "type": post_type,
            "sent": False,
            "created_at": datetime.now(TZ).isoformat(),
        })
        _save_posts(posts)
        return (
            f"✅ Post rejalashtirildi.\n"
            f"Chat: {chat_name}\n"
            f"Vaqt: {send_dt.strftime('%d.%m.%Y %H:%M')}\n"
            f"Matn: {text[:100]}{'...' if len(text)>100 else ''}"
        )
    except Exception as e:
        return f"❌ Rejalashtirish xatosi: {e}"


def get_pending_posts() -> list:
    """Yuborilishi kerak bo'lgan postlarni olish."""
    now = datetime.now(TZ)
    posts = _load_posts()
    due = []
    for p in posts:
        if p.get("sent"):
            continue
        try:
            send_at = datetime.fromisoformat(p["send_at"])
            if send_at.tzinfo is None:
                send_at = TZ.localize(send_at)
            if send_at <= now:
                due.append(p)
        except Exception:
            continue
    return due


def mark_sent(post_id: str) -> None:
    """Postni yuborildi deb belgilash."""
    posts = _load_posts()
    for p in posts:
        if p["id"] == post_id:
            p["sent"] = True
            p["sent_at"] = datetime.now(TZ).isoformat()
            break
    _save_posts(posts)


def list_scheduled_posts() -> str:
    """Rejalashtirilgan postlar ro'yxati."""
    posts = [p for p in _load_posts() if not p.get("sent")]
    if not posts:
        return "Rejalashtirilgan post yo'q."
    lines = []
    for p in posts:
        try:
            dt = datetime.fromisoformat(p["send_at"])
            time_str = dt.strftime("%d.%m %H:%M")
        except Exception:
            time_str = p["send_at"]
        lines.append(f"📅 {time_str} → {p['chat_name']}: {p['text'][:50]}...")
    return "\n".join(lines)


def cancel_post(post_id: str) -> str:
    """Rejalashtirilgan postni bekor qilish."""
    posts = _load_posts()
    for p in posts:
        if p["id"] == post_id and not p.get("sent"):
            p["sent"] = True
            p["cancelled"] = True
            _save_posts(posts)
            return f"✅ Post bekor qilindi."
    return "❌ Post topilmadi yoki allaqachon yuborilgan."


def parse_schedule_prompt(user_text: str) -> str:
    """Tabiiy tildan rejalashtirish ma'lumotlarini ajratish prompti."""
    return (
        "Foydalanuvchi post rejalashtirishni so'rayapti. JSON formatida ajrat:\n"
        "{\n"
        '  "chat_name": "Guruh/kanal nomi",\n'
        '  "text": "Post matni",\n'
        '  "send_at": "2026-05-30T10:00:00",\n'
        '  "type": "message"\n'
        "}\n\n"
        f"Bugungi sana va vaqt: {datetime.now(TZ).strftime('%Y-%m-%d %H:%M')}\n"
        f"So'rov: {user_text}\n\n"
        "Faqat JSON qaytarilsin."
    )
