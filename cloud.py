"""Cloud Services Hub — Barcha onlayn API ulanishlar markazi."""

import json
import logging
import os
import asyncio
from typing import Any

logger = logging.getLogger("jarvis.cloud")

# Notion
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
NOTION_DB_ID = os.environ.get("NOTION_DB_ID")

# Instagram
INSTA_USERNAME = os.environ.get("INSTAGRAM_USER")
INSTA_PASSWORD = os.environ.get("INSTAGRAM_PASS")

# Google Calendar (JSON credential yo'li)
GOOGLE_CRED_PATH = "credentials.json"
CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

class CloudHub:
    def __init__(self):
        self._notion = None
        self._insta = None
        self._calendar = None
        
        # Obyektlar yaratilganda ulanishlarni initsializatsiya qiladi.
        self._init_notion()
        self._init_google()

    def _init_notion(self):
        if NOTION_TOKEN:
            try:
                from notion_client import Client
                self._notion = Client(auth=NOTION_TOKEN)
                logger.info("✅ Notion ulandi.")
            except ImportError:
                logger.warning("❌ notion-client o'rnatilmagan.")
        else:
            logger.info("ℹ️ Notion sozlanmagan (NOTION_TOKEN yo'q).")

    def _init_google(self):
        if os.path.exists(GOOGLE_CRED_PATH):
            try:
                from google.oauth2.service_account import Credentials
                from googleapiclient.discovery import build
                
                creds = Credentials.from_service_account_file(
                    GOOGLE_CRED_PATH, 
                    scopes=['https://www.googleapis.com/auth/calendar']
                )
                self._calendar = build('calendar', 'v3', credentials=creds)
                logger.info("✅ Google Calendar ulandi.")
            except ImportError:
                logger.warning("❌ google-api-python-client yoki google-auth o'rnatilmagan.")
            except Exception as e:
                logger.error(f"❌ Google ulanishida xatolik: {e}")
        else:
            logger.info("ℹ️ Google Calendar sozlanmagan (credentials.json yo'q).")

    # Instagrapi har doim birdan ulanishni yomon ko'radi (block bo'lishi mumkin). 
    # Shuning uchun uni alohida async tarzda chaqirganimiz ma'qul.
    async def _init_instagram(self):
        if self._insta:
            return self._insta

        if not INSTA_USERNAME or not INSTA_PASSWORD:
            logger.info("ℹ️ Instagram sozlanmagan (INSTAGRAM_USER yoki INSTAGRAM_PASS yo'q).")
            return None

        try:
            from instagrapi import Client
            cl = Client()
            await asyncio.to_thread(cl.login, INSTA_USERNAME, INSTA_PASSWORD)
            self._insta = cl
            logger.info("✅ Instagram ulandi.")
            return cl
        except ImportError:
            logger.warning("❌ instagrapi o'rnatilmagan.")
            return None
        except Exception as e:
            logger.error(f"❌ Instagram login xatosi: {e}")
            return None

    # ─────────────────── NOTION ───────────────────
    
    async def notion_add_task(self, title: str, status: str = "Tugatilmadi") -> str:
        """Notion Database'ga yangi qator(vazifa) qo'shadi."""
        if not self._notion or not NOTION_DB_ID:
            return "❌ Notion ulanmagan yoki Database ID ko'rsatilmagan."
        
        try:
            def save_to_notion():
                return self._notion.pages.create(
                    parent={"database_id": NOTION_DB_ID},
                    properties={
                        "Name": {
                            "title": [
                                {"text": {"content": title}}
                            ]
                        },
                        "Status": {
                            "select": {
                                "name": status
                            }
                        }
                    }
                )
            
            await asyncio.to_thread(save_to_notion)
            return f"✅ '{title}' Notionga saqlandi."
        except Exception as e:
            return f"❌ Notionda xato: {e}"

    async def notion_read_tasks(self, limit: int = 10) -> str:
        """Notiondan so'nggi vazifalarni o'qib keladi."""
        if not self._notion or not NOTION_DB_ID:
            return "❌ Notion ulanmagan."
            
        try:
            def get_tasks():
                return self._notion.databases.query(
                    **{"database_id": NOTION_DB_ID, "page_size": limit}
                )
            
            results = await asyncio.to_thread(get_tasks)
            tasks = []
            for page in results.get("results", []):
                try:
                    title_prop = page["properties"].get("Name", {}).get("title", [])
                    title = title_prop[0]["plain_text"] if title_prop else "Nomsiz"
                    
                    status_prop = page["properties"].get("Status", {}).get("select")
                    status = status_prop["name"] if status_prop else "Status yo'q"
                    
                    tasks.append(f"- {title} [{status}]")
                except:
                    continue
            return "📋 Notion dagi so'nggi ma'lumotlar:\n" + "\n".join(tasks) if tasks else "Notion da hech narsa yo'q."
        except Exception as e:
            return f"❌ Notionda xato: {e}"

    # ─────────────────── GOOGLE CALENDAR ───────────────────
    
    async def calendar_add_event(self, summary: str, start_time: str, end_time: str, description: str = "") -> str:
        """Taqvimga yangi event(uchrashuv) qo'shadi. start_time va end_time ISO formatda bo'lishi kerak."""
        if not self._calendar:
            return "❌ Google Calendar ulanmagan."
            
        try:
            event = {
              'summary': summary,
              'description': description,
              'start': {
                'dateTime': start_time,
                'timeZone': 'Asia/Tashkent',
              },
              'end': {
                'dateTime': end_time,
                'timeZone': 'Asia/Tashkent',
              },
            }

            def add_event():
                return self._calendar.events().insert(calendarId=CALENDAR_ID, body=event).execute()
                
            res = await asyncio.to_thread(add_event)
            return f"✅ '{summary}' taqvimga kiritildi. Link: {res.get('htmlLink')}"
        except Exception as e:
            return f"❌ Calendar saqlash xatosi: {e}"

    async def calendar_get_events(self, max_results: int = 5) -> str:
        """Kelgusi eventlarni o'qib beradi."""
        if not self._calendar:
            return "❌ Google Calendar ulanmagan."
            
        from datetime import datetime
        try:
            now = datetime.utcnow().isoformat() + 'Z'
            
            def read_events():
                return self._calendar.events().list(
                    calendarId=CALENDAR_ID, timeMin=now,
                    maxResults=max_results, singleEvents=True,
                    orderBy='startTime').execute()
                    
            events_result = await asyncio.to_thread(read_events)
            events = events_result.get('items', [])
            
            if not events:
                return "Kelgusi uchrashuvlar yo'q."
                
            lines = ["📅 Uchrashuvlar:"]
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                lines.append(f"• {start[:16].replace('T', ' ')} - {event['summary']}")
                
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Calendar o'qish xatosi: {e}"

    # ─────────────────── INSTAGRAM ───────────────────

    async def insta_send_dm(self, username: str, message: str) -> str:
        """Instagramda yozilgan akkauntga to'g'ridan-to'g'ri DM orqali xabar jo'natadi."""
        cl = await self._init_instagram()
        if not cl:
            return "❌ Instagram ulanmagan yoki avtorizatsiya rad etildi."
            
        try:
            def send():
                # usernamedan user_id ni olamiz
                user_id = cl.user_id_from_username(username)
                cl.direct_send(message, user_ids=[user_id])
                
            await asyncio.to_thread(send)
            return f"✅ Instagram ({username}) ga xabar yuborildi."
        except Exception as e:
            return f"❌ Instagram xatosi: {e}"
