import os
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.tl.types import DialogFilter

logger = logging.getLogger("jarvis.vacancy_scraper")

class VacancyScraper:
    """Telethon client dedicated to scraping vacancies from source channels."""
    
    def __init__(self, api_id: int, api_hash: str, session_string: str) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.connected = False
        
        session = StringSession(session_string)
        self.client = TelegramClient(session, api_id, api_hash)

    async def connect(self) -> None:
        """Connects and authorizes the scraper client."""
        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                logger.error("❌ Vacancy scraper Telegram session is NOT authorized.")
                self.connected = False
                return
            self.connected = True
            me = await self.client.get_me()
            logger.info(f"✅ Vacancy Scraper authorized successfully: @{me.username} ({me.first_name})")
        except Exception as e:
            logger.error(f"❌ Vacancy Scraper connection error: {e}")
            self.connected = False

    async def get_channels_from_folder(self, folder_name: str = "HR") -> list[int]:
        """Gets all channel/chat IDs inside a specified Telegram folder (filter)."""
        if not self.connected:
            return []
        try:
            r = await self.client(GetDialogFiltersRequest())
            for f in r.filters:
                if isinstance(f, DialogFilter) and f.title and str(f.title).lower() == folder_name.lower():
                    channel_ids = []
                    for peer in f.include_peers:
                        if hasattr(peer, 'channel_id'):
                            channel_ids.append(peer.channel_id)
                        elif hasattr(peer, 'chat_id'):
                            channel_ids.append(peer.chat_id)
                    return channel_ids
        except Exception as e:
            logger.error(f"Error reading dialog filter (folder) '{folder_name}': {e}")
        return []

    async def get_source_channels(self, folder_name: str = "HR") -> list:
        """Gets target source channels, fallback to config env if folder query is empty."""
        # Check env variable first
        sources_str = os.environ.get("VACANCY_SOURCES", "")
        if sources_str:
            res = []
            for s in sources_str.split(","):
                s = s.strip()
                if not s:
                    continue
                if s.replace("-", "").isdigit():
                    res.append(int(s))
                else:
                    res.append(s)
            return res
            
        # Fallback to dialog filter
        return await self.get_channels_from_folder(folder_name)

    async def get_latest_vacancies(self, channels: list, limit: int = 5) -> list[dict]:
        """Reads latest messages from sources and filters for potential vacancies."""
        vacancies = []
        if not self.connected:
            return vacancies

        for channel in channels:
            try:
                entity = await self.client.get_entity(channel)
                async for msg in self.client.iter_messages(entity, limit=limit):
                    if msg.text and len(msg.text.strip()) > 30:
                        text_lower = msg.text.lower()
                        # Keywords to detect vacancy descriptions
                        keywords = [
                            "vakansiya", "vacancy", "ishga taklif", "ishga", "ish bor",
                            "job", "lavozim", "talablar", "maosh", "oylik", "rezyume",
                            "kontakt", "aloqa", "kandidat", "salom"
                        ]
                        if any(kw in text_lower for kw in keywords):
                            channel_id = getattr(msg.peer_id, 'channel_id', None)
                            if not channel_id:
                                channel_id = getattr(entity, 'id', None)

                            if channel_id and msg.id:
                                vacancies.append({
                                    "channel_id": channel_id,
                                    "channel_name": getattr(entity, 'title', str(channel)),
                                    "msg_id": msg.id,
                                    "text": msg.text,
                                    "date": msg.date
                                })
            except Exception as e:
                logger.warning(f"Failed to fetch vacancies from channel {channel}: {e}")
        return vacancies
