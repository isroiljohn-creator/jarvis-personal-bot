"""Telethon Userbot — Telegram akkountni boshqarish."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("jarvis.userbot")


class UserBot:
    """Telethon orqali Telegram akkountga kirish."""

    def __init__(self, api_id: int, api_hash: str, phone: str) -> None:
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        self.api_id = api_id
        self.api_hash = api_hash
        self.phone = phone
        self.connected = False

        session_string = os.environ.get("TG_SESSION_STRING", "")
        session = StringSession(session_string) if session_string else StringSession()

        self.client = TelegramClient(session, api_id, api_hash)

    async def connect(self) -> None:
        """Telegram'ga ulaning."""
        await self.client.connect()
        if not await self.client.is_user_authorized():
            logger.warning("Telegram seansi yaroqsiz. Qayta login talab qilinadi.")
            raise RuntimeError(
                "Telegram sessiya yaroqsiz. TG_SESSION_STRING o'rnating."
            )
        self.connected = True
        me = await self.client.get_me()
        logger.info(f"✅ Telegram: @{me.username} ({me.first_name})")

    async def get_dialogs(self, limit: int = 10) -> list[dict[str, Any]]:
        """Oxirgi chatlar ro'yxati."""
        dialogs = []
        async for dialog in self.client.iter_dialogs(limit=limit):
            dialogs.append(
                {
                    "id": dialog.id,
                    "name": dialog.name,
                    "unread": dialog.unread_count,
                    "type": "guruh" if dialog.is_group else "kanal" if dialog.is_channel else "shaxsiy",
                }
            )
        return dialogs

    async def get_messages(self, chat_id: int, limit: int = 5) -> list[dict[str, Any]]:
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
        """Xabar yuborish."""
        await self.client.send_message(chat_id, text)
        logger.info(f"Xabar {chat_id} ga yuborildi")

    async def get_unread(self) -> list[dict[str, Any]]:
        """O'qilmagan xabarlar."""
        unread = []
        async for dialog in self.client.iter_dialogs():
            if dialog.unread_count > 0:
                msgs = await self.get_messages(dialog.id, limit=dialog.unread_count)
                unread.append(
                    {
                        "chat": dialog.name,
                        "chat_id": dialog.id,
                        "count": dialog.unread_count,
                        "messages": msgs,
                    }
                )
        return unread
