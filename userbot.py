"""Telethon Userbot — Telegram akkountni boshqarish, auto-reply, ovozli xabar."""

from __future__ import annotations

import logging
import os
import asyncio
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
            # ── SILENT GROUP MONITOR ──
            if event.is_group:
                try:
                    chat = await event.get_chat()
                    chat_title = getattr(chat, "title", "")
                    target_group = os.environ.get("AGENCY_GROUP_NAME", "AI Marketing Agency").strip()
                    
                    is_match = False
                    # Check if target_group is a numeric ID (with optional leading minus)
                    clean_id = target_group.lstrip('-')
                    if clean_id.isdigit():
                        # Telethon chat IDs can be matched directly or converted
                        is_match = (chat.id == int(target_group) or 
                                    getattr(chat, "migrated_to", None) == int(target_group))
                    else:
                        is_match = chat_title and (target_group.lower() in chat_title.lower())
                    
                    if is_match:
                        msg_text = event.message.text or ""
                        if msg_text.strip():
                            sender = await event.get_sender()
                            sender_name = getattr(sender, "first_name", getattr(sender, "title", "Noma'lum")) or "Noma'lum"
                            sender_username = getattr(sender, "username", "")
                            sender_label = f"{sender_name} (@{sender_username})" if sender_username else sender_name
                            
                            from database import db_add_message
                            await db_add_message(
                                role=sender_label,
                                content=msg_text,
                                source="telegram_group"
                            )
                            logger.info(f"👥 Guruh xabari log qilindi ({chat_title} | {sender_label}): {msg_text[:50]}")
                except Exception as ex:
                    logger.warning(f"Group monitor logging error: {ex}")

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
                sender_name = getattr(sender, "first_name", getattr(sender, "title", "Noma'lum")) or "Noma'lum"
                sender_username = (getattr(sender, "username", "") or "").lower()
                
                # ── AVTOMATIK MOLIYA TREKERI (Auto Finance) ──
                if sender_username in ["paymeuz_bot", "clickuz", "apelsin_bot", "uzumbank_bot", "plum_uz_bot"] or sender_name.lower() in ["click", "payme", "uzum bank"]:
                    logger.info(f"💰 Moliya xabari tushdi ({sender_name}): {msg_text[:50]}")
                    if self.ai_callback:
                        system = "Sen Aziza - aqlli moliya yordamchisisan. Berilgan to'lov/xarajat xabaridan summani aniqla va albatta 'log_finance' vositasi orqali bazaga kirit. 'payment_method'='karta'. So'ngra faqatgina bitta gap bilan (masalan: '15,000 UZS Uzum orqali xarajat bazaga yozildi') xabar ber."
                        reply = await self.ai_callback(f"Quyidagi tranzaksiyani log_finance orqali bazaga kirit:\n\n{msg_text}", [], system)
                        if self.notify_callback:
                            await self.notify_callback(f"🏦 **Avto-Moliya ({sender_name}):**\n{reply}")
                    return
                    
                logger.info(f"📩 Yangi xabar ({sender_name}): {msg_text[:50]}")

                if self.ai_callback:
                    system = (
                        f"Sen {sender_name} bilan gaplashayotgan egangning "
                        f"AI yordamchisisisan. "
                        f"Egangning uslubida javob ber — qisqa, do'stona, o'zbekcha. "
                        f"Agar savol noaniq bo'lsa, qisqa va iltifotli javob ber."
                    )
                    reply = await self.ai_callback(msg_text, [], system)
                    await event.reply(reply, parse_mode="md")
                    logger.info(f"✅ Javob: {reply[:50]}")

                    if self.notify_callback:
                        await self.notify_callback(
                            f"💬 **{sender_name}** yozdi:\n{msg_text}\n\n"
                            f"🤖 **Aziza javob berdi:**\n{reply}"
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

    async def get_daily_digest_messages(self, limit_dialogs: int = 40) -> str:
        """Kungi xabarlarni tahlil uchun to'plash."""
        # Ensure client is connected and active
        try:
            if not self.client.is_connected():
                logger.info("Userbot is not connected. Connecting...")
                await self.client.connect()
            else:
                # Test connection by fetching me
                await asyncio.wait_for(self.client.get_me(), timeout=5.0)
        except Exception as e:
            logger.warning(f"Userbot connection check failed: {e}. Reconnecting...")
            try:
                await self.client.disconnect()
            except:
                pass
            await self.client.connect()

        output = []
        try:
            async def fetch():
                async for dialog in self.client.iter_dialogs(limit=limit_dialogs):
                    is_news_channel = dialog.is_channel and not dialog.is_group
                    if is_news_channel:
                        continue
                        
                    unread = dialog.unread_count
                    if unread > 0:
                        output.append(f"\n--- Chat: {dialog.name} ({unread} ta o'qilmagan xabar) ---")
                        async for msg in self.client.iter_messages(dialog.id, limit=min(unread, 20)):
                            sender = "Noma'lum"
                            if msg.sender:
                                if hasattr(msg.sender, "first_name"):
                                    sender = msg.sender.first_name or "Noma'lum"
                                elif hasattr(msg.sender, "title"):
                                    sender = msg.sender.title or "Noma'lum"
                            text = msg.text or "[Media/Stiker]"
                            date_str = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else "Noma'lum vaqt"
                            output.append(f"[{date_str}] {sender}: {text}")
            
            await asyncio.wait_for(fetch(), timeout=25.0)
        except asyncio.TimeoutError:
            logger.error("Timeout fetching daily digest messages from Telegram. Reconnecting client...")
            try:
                await self.client.disconnect()
            except:
                pass
            await self.client.connect()
            
            # Try one more time after reconnecting
            output = []
            async for dialog in self.client.iter_dialogs(limit=limit_dialogs):
                is_news_channel = dialog.is_channel and not dialog.is_group
                if is_news_channel:
                    continue
                unread = dialog.unread_count
                if unread > 0:
                    output.append(f"\n--- Chat: {dialog.name} ({unread} ta o'qilmagan xabar) ---")
                    async for msg in self.client.iter_messages(dialog.id, limit=min(unread, 20)):
                        sender = "Noma'lum"
                        if msg.sender:
                            if hasattr(msg.sender, "first_name"):
                                sender = msg.sender.first_name or "Noma'lum"
                            elif hasattr(msg.sender, "title"):
                                sender = msg.sender.title or "Noma'lum"
                        text = msg.text or "[Media/Stiker]"
                        date_str = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else "Noma'lum vaqt"
                        output.append(f"[{date_str}] {sender}: {text}")

        return "\n".join(output) if output else ""


    @staticmethod
    def _clean_for_telegram(text: str) -> str:
        """Telegram plain-text uchun markdown belgilarini tozalaydi."""
        import re
        # **bold** → BOLD (Telethon md parse_mode bilan ham muammo bo'lgani uchun plain text ishlatamiz)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text, flags=re.DOTALL)
        # *italic* → oddiy matn
        text = re.sub(r'\*(.+?)\*', r'\1', text, flags=re.DOTALL)
        # `code` → oddiy matn
        text = re.sub(r'`(.+?)`', r'\1', text, flags=re.DOTALL)
        # [text](url) → text (url)
        text = re.sub(r'\[(.+?)\]\((.+?)\)', r'\1 (\2)', text)
        # ### Heading → Heading
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # ___underline___ → oddiy matn
        text = re.sub(r'_{1,3}(.+?)_{1,3}', r'\1', text, flags=re.DOTALL)
        # Qolgan yolg'iz yulduzchalarni tozalash
        text = text.replace('**', '').replace('*', '')
        return text.strip()

    async def send_message(self, chat_id, text: str) -> None:
        """Xabar yuborish — markdown tozalangan oddiy matn sifatida."""
        clean_text = self._clean_for_telegram(text)
        try:
            await self.client.send_message(chat_id, clean_text)
        except Exception as e:
            logger.warning(f"send_message xatosi ({chat_id}): {e}")
            # Fallback: raw matnni yuborish
            try:
                await self.client.send_message(chat_id, text[:4096])
            except Exception as e2:
                logger.error(f"send_message fallback ham ishlamadi: {e2}")
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
        async for dialog in self.client.iter_dialogs(limit=150):
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

    async def send_file(self, chat_id: int, file_path: str, caption: str = "") -> None:
        """Fayl yuborish (Video, Rasm, Dokument)."""
        try:
            await self.client.send_file(
                chat_id,
                file_path,
                caption=caption,
                parse_mode="md"
            )
            logger.info(f"📁 Fayl yuborildi → {chat_id}")
        except Exception as e:
            logger.error(f"Fayl yuborish xatosi: {e}")
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

    async def get_channels_from_folder(self, folder_name: str) -> list[Any]:
        """Folder nomi bo'yicha undagi barcha kanallarni qaytaradi."""
        from telethon.tl.functions.messages import GetDialogFiltersRequest
        from telethon.tl.types import DialogFilter, PeerChannel
        
        # Connection check
        if not self.client.is_connected():
            await self.client.connect()
            
        try:
            res = await self.client(GetDialogFiltersRequest())
        except Exception as e:
            logger.error(f"Error fetching dialog filters: {e}")
            return []
            
        target_filter = None
        for f in res.filters:
            if isinstance(f, DialogFilter) and f.title and str(f.title).lower() == folder_name.lower():
                target_filter = f
                break
                
        if not target_filter:
            logger.warning(f"Folder '{folder_name}' topilmadi.")
            return []
            
        # Extract explicit channel IDs from include_peers
        included_channel_ids = set()
        for peer in target_filter.include_peers:
            if isinstance(peer, PeerChannel):
                included_channel_ids.add(peer.channel_id)
                
        # Fetch all dialogs to resolve entities
        dialogs = await self.client.get_dialogs(limit=None)
        channels = []
        for dialog in dialogs:
            if dialog.is_channel and not dialog.is_group:
                # Check if explicitly included
                is_in_folder = dialog.entity.id in included_channel_ids
                
                # Check if folder matches broadcasts (channels) generally, and chat not explicitly excluded
                if not is_in_folder and getattr(target_filter, "broadcasts", False):
                    # Check if excluded
                    is_excluded = False
                    for ex_peer in target_filter.exclude_peers:
                        if isinstance(ex_peer, PeerChannel) and ex_peer.channel_id == dialog.entity.id:
                            is_excluded = True
                            break
                    if not is_excluded:
                        is_in_folder = True
                        
                if is_in_folder:
                    channels.append(dialog.entity)
                    
        return channels
