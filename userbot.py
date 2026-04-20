"""Telethon Userbot — Telegram akkountni boshqarish, auto-reply, ovozli xabar."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

logger = logging.getLogger("jarvis.userbot")


class UserBot:
    """Telethon orqali Telegram akkountga kirish va boshqarish."""

    def __init__(self, api_id: int, api_hash: str, phone: str) -> None:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.connected = False
        self.auto_reply = False
        self.ai_callback: Callable | None = None
        self.notify_callback: Callable | None = None
        self._me_id: int | None = None

        session_string = os.environ.get("TG_SESSION_STRING", "")
        session = StringSession(session_string) if session_string else StringSession()
        self.client = TelegramClient(session, api_id, api_hash)

    async def connect(self) -> None:
        """Telegram'ga ulanish."""
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError(
                "Telegram sessiya yaroqsiz. TG_SESSION_STRING'ni yangilang."
            )
        self.connected = True
        me = await self.client.get_me()
        self._me_id = me.id
        logger.info(f"✅ Telegram: @{me.username} ({me.first_name})")

    def set_ai(self, ai_callback: Callable) -> None:
        """Gemini AI funksiyasini ulash."""
        self.ai_callback = ai_callback

    def set_notify(self, notify_callback: Callable) -> None:
        """Bot bildiruv funksiyasini ulash."""
        self.notify_callback = notify_callback

    # ─────────────────── Auto-Reply ───────────────────

    async def start_auto_reply(self) -> None:
        """Kiruvchi xabarlarga avtomatik javob berish."""
        from telethon import events

        @self.client.on(events.NewMessage(incoming=True))
        async def handler(event):
            if not self.auto_reply:
                return
            if event.is_group or event.is_channel:
                return
            if event.sender_id == self._me_id:
                return

            msg_text = event.message.text or ""
            if not msg_text.strip():
                return

            try:
                sender = await event.get_sender()
                sender_name = (
                    getattr(sender, "first_name", "Noma'lum") or "Noma'lum"
                )
                logger.info(f"📩 Yangi xabar ({sender_name}): {msg_text[:50]}")

                if self.ai_callback:
                    system = (
                        f"Sen {sender_name} bilan gaplashayotgan egangning "
                        f"AI yordamchisisisan. "
                        f"Egangning uslubida javob ber — qisqa, do'stona, o'zbekcha. "
                        f"Agar savol noaniq bo'lsa, qisqa va iltifotli javob ber."
                    )
                    reply = await self.ai_callback(msg_text, [], system)
                    await event.reply(reply)
                    logger.info(f"✅ Javob: {reply[:50]}")

                    if self.notify_callback:
                        await self.notify_callback(
                            f"💬 *{sender_name}* yozdi:\n{msg_text}\n\n"
                            f"🤖 *Jarvis javob berdi:*\n{reply}"
                        )
            except Exception as e:
                logger.error(f"Auto-reply xatosi: {e}")

        logger.info("🤖 Auto-reply handler o'rnatildi")

    # ─────────────────── Chat boshqaruvi ───────────────────

    async def get_dialogs(self, limit: int = 10) -> list[dict[str, Any]]:
        """So'nggi chatlar ro'yxati."""
        dialogs = []
        async for dialog in self.client.iter_dialogs(limit=limit):
            dialogs.append(
                {
                    "id": dialog.id,
                    "name": dialog.name,
                    "unread": dialog.unread_count,
                    "type": (
                        "guruh"
                        if dialog.is_group
                        else "kanal" if dialog.is_channel else "shaxsiy"
                    ),
                }
            )
        return dialogs

    async def get_messages(
        self, chat_id: int, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Chat xabarlarini o'qish."""
        messages = []
        async for msg in self.client.iter_messages(chat_id, limit=limit):
            sender = "Noma'lum"
            if msg.sender:
                if hasattr(msg.sender, "first_name"):
                    sender = msg.sender.first_name or "Noma'lum"
                elif hasattr(msg.sender, "title"):
                    sender = msg.sender.title or "Noma'lum"
            messages.append(
                {
                    "id": msg.id,
                    "from": sender,
                    "text": msg.text or "[Media xabar]",
                    "date": str(msg.date),
                }
            )
        return messages

    async def send_message(self, chat_id: int, text: str) -> None:
        """Xabar yuborish (chat_id bo'yicha)."""
        await self.client.send_message(chat_id, text)
        logger.info(f"📤 Xabar → {chat_id}")

    # ─────────────────── Kontakt qidirish ───────────────────

    async def find_contact(self, name: str) -> int | None:
        """Ism bo'yicha chat topish. Chat ID qaytaradi."""
        name_lower = name.lower().strip()

        # 1. Raqam bo'lsa — to'g'ridan-to'g'ri qaytarish
        try:
            return int(name_lower)
        except ValueError:
            pass

        # 2. @username bo'lsa
        if name_lower.startswith("@"):
            try:
                entity = await self.client.get_entity(name_lower)
                return entity.id
            except Exception:
                pass

        # 3. Ism bo'yicha qidirish (dialoglardan)
        async for dialog in self.client.iter_dialogs(limit=50):
            dialog_name = (dialog.name or "").lower()
            if name_lower in dialog_name or dialog_name in name_lower:
                logger.info(f"🔍 Topildi: {dialog.name} → {dialog.id}")
                return dialog.id

        # 4. Telegram global qidirish
        try:
            result = await self.client.get_entity(name)
            return result.id
        except Exception:
            pass

        return None

    # ─────────────────── Ovozli xabar ───────────────────

    async def send_voice(self, chat_id: int, ogg_path: str) -> None:
        """Ovozli xabar yuborish (OGG Opus fayl)."""
        try:
            await self.client.send_file(
                chat_id,
                ogg_path,
                voice_note=True,
            )
            logger.info(f"🎤 Ovozli xabar → {chat_id}")
        except Exception as e:
            logger.error(f"Ovozli xabar xatosi: {e}")
            raise

    # ─────────────────── O'qilmagan xabarlar ───────────────────

    async def get_unread(self) -> list[dict[str, Any]]:
        """O'qilmagan xabarlar."""
        unread = []
        async for dialog in self.client.iter_dialogs():
            if dialog.unread_count > 0:
                msgs = await self.get_messages(
                    dialog.id, limit=min(dialog.unread_count, 5)
                )
                unread.append(
                    {
                        "chat": dialog.name,
                        "chat_id": dialog.id,
                        "count": dialog.unread_count,
                        "messages": msgs,
                    }
                )
        return unread
