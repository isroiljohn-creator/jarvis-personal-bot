"""Cloud Services Hub — Barcha onlayn API ulanishlar markazi."""

import json
import logging
import os
import asyncio
import email
from email.message import EmailMessage
import imaplib
import smtplib
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

# Gmail (App Password orqali)
GMAIL_EMAIL = os.environ.get("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

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
        limit = int(limit)
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
        max_results = int(max_results)
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

    # ─────────────────── GMAIL (IMAP / SMTP) ───────────────────

    async def gmail_read_unread(self, limit: int = 5) -> str:
        """Gmail'dan o'qilmagan so'nggi xatlarni o'qib beradi."""
        limit = int(limit)
        if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
            return "❌ Gmail sozlanmagan (GMAIL_EMAIL yoki GMAIL_APP_PASSWORD yo'q)."
            
        try:
            def read_emails():
                mail = imaplib.IMAP4_SSL('imap.gmail.com')
                mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
                mail.select("inbox")
                
                status, messages = mail.search(None, 'UNSEEN')
                if status != 'OK' or not messages[0]:
                    return "Yangi (o'qilmagan) xatlar yo'q."
                    
                msg_nums = messages[0].split()
                # Olish kerak bo'lgan xatlar ro'yxatini shakllantiramiz (oxirgisidan)
                to_fetch = msg_nums[-limit:]
                
                results = ["✉️ O'qilmagan So'nggi Xatlar:"]
                for num in reversed(to_fetch):
                    res, msg_data = mail.fetch(num, '(RFC822)')
                    if res != 'OK': continue
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            # Subject
                            subject_tuple = email.header.decode_header(msg['Subject'])[0]
                            subject = subject_tuple[0]
                            if isinstance(subject, bytes):
                                try: subject = subject.decode(subject_tuple[1] or 'utf-8')
                                except: subject = str(subject)
                                
                            # Sender
                            sender = msg.get('From', 'Noma\'lum')
                            
                            results.append(f"• Kimdan: {sender}\n  Mavzu: {subject}")
                mail.logout()
                return "\n".join(results)
                
            return await asyncio.to_thread(read_emails)
        except Exception as e:
            return f"❌ Gmail o'qish xatosi: {e}"

    async def gmail_send_email(self, to_email: str, subject: str, body: str) -> str:
        """Kimgadir yangi elektron pochta(Gmail) yuboradi."""
        if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
            return "❌ Gmail sozlanmagan (GMAIL_EMAIL yoki GMAIL_APP_PASSWORD yo'q)."
            
        try:
            def send():
                msg = EmailMessage()
                msg.set_content(body)
                msg['Subject'] = subject
                msg['From'] = GMAIL_EMAIL
                msg['To'] = to_email

                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                    smtp.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
                    smtp.send_message(msg)
                    
            await asyncio.to_thread(send)
            return "✅ Email muvaffaqiyatli jo'natildi."
        except Exception as e:
            return f"❌ Email jo'natish xatosi: {e}"

    # ─────────────────── AGENT & WEB SCRAPING ───────────────────

    async def youtube_transcript(self, url: str) -> str:
        """Youtube videosi subtitrini o'qiydi."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            import urllib.parse
            
            # extract video ID
            parsed_url = urllib.parse.urlparse(url)
            if 'youtu.be' in parsed_url.netloc:
                video_id = parsed_url.path[1:]
            else:
                qs = urllib.parse.parse_qs(parsed_url.query)
                video_id = qs.get("v", [""])[0]
                
            if not video_id: return "❌ Youtube Linkdan ID topilmadi."
            
            def get_text():
                transcriptList = YouTubeTranscriptApi.get_transcript(video_id, languages=['uz', 'ru', 'en'])
                return " ".join([t['text'] for t in transcriptList])
                
            text = await asyncio.to_thread(get_text)
            return text[:4000] # Limiting context window
        except Exception as e:
            return f"❌ Youtube o'qishda xatolik: {e}"

    async def scrape_website(self, url: str) -> str:
        """Berilgan linkdagi sayt matnini o'qib keladi."""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            headers = {"User-Agent": "Mozilla/5.0"}
            def fetch():
                res = requests.get(url, headers=headers, timeout=10)
                res.raise_for_status()
                soup = BeautifulSoup(res.text, "html.parser")
                # keraksiz teglarni olib tashlaymiz
                for s in soup(["script", "style", "nav", "footer", "header"]):
                    s.decompose()
                return " ".join(soup.stripped_strings)
                
            text = await asyncio.to_thread(fetch)
            return text[:4000] # Limiting context window
        except Exception as e:
            return f"❌ Sayt o'qishda xatolik: {e}"
