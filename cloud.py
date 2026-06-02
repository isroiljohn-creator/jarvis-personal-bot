"""Cloud Services Hub — Barcha onlayn API ulanishlar markazi."""

from __future__ import annotations

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
        google_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if google_json:
            try:
                from google.oauth2.service_account import Credentials
                from googleapiclient.discovery import build
                import json
                
                info = json.loads(google_json)
                creds = Credentials.from_service_account_info(
                    info, 
                    scopes=['https://www.googleapis.com/auth/calendar']
                )
                self._calendar = build('calendar', 'v3', credentials=creds)
                logger.info("✅ Google Calendar ulandi (environment variable orqali).")
                return
            except Exception as e:
                logger.error(f"❌ Google ulanishida xatolik (env): {e}")

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
            logger.info("ℹ️ Google Calendar sozlanmagan (credentials.json yoki GOOGLE_CREDENTIALS_JSON yo'q).")

    # Instagrapi har doim birdan ulanishni yomon ko'radi (block bo'lishi mumkin). 
    # Shuning uchun uni alohida async tarzda chaqirganimiz ma'qul.
    async def _init_instagram(self):
        """Instagram sessiyasini boshlash (Login + Proxy)."""
        if self._insta:
            return self._insta

        if not INSTA_USERNAME or not INSTA_PASSWORD:
            logger.info("ℹ️ Instagram sozlanmagan (INSTAGRAM_USER yoki INSTAGRAM_PASS yo'q).")
            return None

        try:
            from instagrapi import Client
            cl = Client()
            
            # PROXY sozlash
            proxy_url = os.environ.get("PROXY_URL")
            if proxy_url:
                logger.info("🌐 Instagram uchun proksi o'rnatilmoqda...")
                cl.set_proxy(proxy_url)
            else:
                logger.warning("⚠️ PROXY_URL topilmadi. Instagram ulanishi bloklanishi mumkin.")
            
            # Login (to_thread orqali bloklanishdan qochamiz)
            logger.info(f"🔐 Instagramga kirish: {INSTA_USERNAME}...")
            await asyncio.to_thread(cl.login, INSTA_USERNAME, INSTA_PASSWORD)
            
            self._insta = cl
            logger.info("✅ Instagram ulandi.")
            return cl
        except ImportError:
            logger.warning("❌ instagrapi o'rnatilmagan yoki import xatosi.")
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

    async def notion_get_inactive_leads(self) -> str:
        """Notion database'da 7 kundan beri yangilanmagan (faol bo'lmagan) mijozlar/leadlarni aniqlaydi."""
        if not self._notion or not NOTION_DB_ID:
            return "❌ Notion ulanmagan."
            
        try:
            def query_db():
                return self._notion.databases.query(
                    **{"database_id": NOTION_DB_ID}
                )
            
            results = await asyncio.to_thread(query_db)
            inactive_leads = []
            
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            
            for page in results.get("results", []):
                try:
                    title_prop = page["properties"].get("Name", {}).get("title", [])
                    title = title_prop[0]["plain_text"] if title_prop else "Nomsiz"
                    
                    status_prop = page["properties"].get("Status", {}).get("select")
                    status = status_prop["name"] if status_prop else "Status yo'q"
                    
                    # Fallback to page level last_edited_time
                    let_str = page.get("last_edited_time")
                    if let_str:
                        let_dt = datetime.fromisoformat(let_str.replace("Z", "+00:00"))
                        delta = now - let_dt
                        if delta.days >= 7:
                            inactive_leads.append(f"- **{title}** (Status: {status}, {delta.days} kundan beri faol emas)")
                except Exception as ex:
                    logger.warning(f"Error parsing Notion page in inactive leads check: {ex}")
                    continue
                    
            if not inactive_leads:
                return "✅ Notion CRM'da barcha mijozlar/leadlar faol holatda. 7 kundan ko'p kechikkanlar yo'q."
            return "⚠️ **7 kundan beri faol bo'lmagan leadlar/mijozlar:**\n\n" + "\n".join(inactive_leads)
        except Exception as e:
            return f"❌ Notion CRM tahlilida xatolik: {e}"

    async def notion_get_active_projects(self) -> str:
        """Notion database'dan faol (bajarilayotgan yoki kutilayotgan) loyihalarni o'qib keladi."""
        if not self._notion or not NOTION_DB_ID:
            return "❌ Notion ulanmagan."
            
        try:
            def query_db():
                return self._notion.databases.query(
                    **{"database_id": NOTION_DB_ID}
                )
            
            results = await asyncio.to_thread(query_db)
            active_projects = []
            
            for page in results.get("results", []):
                try:
                    title_prop = page["properties"].get("Name", {}).get("title", [])
                    title = title_prop[0]["plain_text"] if title_prop else "Nomsiz"
                    
                    status_prop = page["properties"].get("Status", {}).get("select")
                    status = status_prop["name"] if status_prop else "Status yo'q"
                    
                    if status.lower() not in ["done", "bajarildi", "tugatildi", "completed"]:
                        active_projects.append(f"- **{title}** [{status}]")
                except:
                    continue
                    
            if not active_projects:
                return "📋 Hozirda Notionda faol loyihalar yoki kutilayotgan vazifalar mavjud emas."
            return "📋 **Notion CRM dagi faol loyihalar va vazifalar:**\n\n" + "\n".join(active_projects)
        except Exception as e:
            return f"❌ Notion faol loyihalarini olishda xatolik: {e}"

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

    async def get_raw_upcoming_events(self, minutes_ahead: int = 15) -> list[dict]:
        """Kelgusi minutes_ahead daqiqalar ichida boshlanadigan barcha uchrashuvlarni qaytaradi."""
        if not self._calendar:
            return []
            
        from datetime import datetime, timedelta
        import pytz
        
        try:
            tz = pytz.timezone("Asia/Tashkent")
            now_dt = datetime.now(tz)
            time_min = now_dt.isoformat()
            time_max = (now_dt + timedelta(minutes=minutes_ahead)).isoformat()
            
            def fetch():
                return self._calendar.events().list(
                    calendarId=CALENDAR_ID, 
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
            res = await asyncio.to_thread(fetch)
            return res.get('items', [])
        except Exception as e:
            logger.error(f"Error fetching raw calendar events: {e}")
            return []

    async def calendar_timebox_tasks(self, tasks: list[str], start_date: str | None = None) -> str:
        """Tasks ro'yxatini Google Calendar dagi bo'sh slotlarga avtomatik vaqt ajratib kiritadi."""
        if not self._calendar:
            return "❌ Google Calendar ulanmagan."
        
        from datetime import datetime, timedelta, date, time
        import pytz

        tz = pytz.timezone("Asia/Tashkent")
        
        if start_date:
            try:
                current_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except Exception:
                return "❌ Sana formati noto'g'ri (YYYY-MM-DD kutilmoqda)."
        else:
            current_date = datetime.now(tz).date()

        scheduled = []
        unresolved = list(tasks)
        
        day_offset = 0
        max_days = 3 # 3 kunlik rejalashtirish
        
        while unresolved and day_offset < max_days:
            target_date = current_date + timedelta(days=day_offset)
            target_date_str = target_date.strftime("%Y-%m-%d")
            
            # Target kun uchun barcha uchrashuvlarni olish
            time_min = tz.localize(datetime.combine(target_date, time.min)).isoformat()
            time_max = tz.localize(datetime.combine(target_date, time.max)).isoformat()
            
            def fetch_day_events():
                return self._calendar.events().list(
                    calendarId=CALENDAR_ID,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
            try:
                events_res = await asyncio.to_thread(fetch_day_events)
                day_events = events_res.get('items', [])
            except Exception as e:
                logger.error(f"Error fetching calendar events for timebox: {e}")
                day_events = []
                
            # Blocked times logic
            blocked_intervals = []
            for ev in day_events:
                ev_start = ev['start'].get('dateTime') or ev['start'].get('date')
                ev_end = ev['end'].get('dateTime') or ev['end'].get('date')
                if ev_start and ev_end:
                    try:
                        # Clean Z format for fromisoformat
                        clean_start = ev_start.replace('Z', '+00:00')
                        clean_end = ev_end.replace('Z', '+00:00')
                        # If date only (e.g. 2026-05-29)
                        if len(clean_start) == 10:
                            dt_start = tz.localize(datetime.strptime(clean_start, "%Y-%m-%d"))
                            dt_end = tz.localize(datetime.strptime(clean_end, "%Y-%m-%d"))
                        else:
                            dt_start = datetime.fromisoformat(clean_start).astimezone(tz)
                            dt_end = datetime.fromisoformat(clean_end).astimezone(tz)
                        blocked_intervals.append((dt_start, dt_end))
                    except Exception as ex:
                        logger.warning(f"Error parsing event times: {ex}")
                    
            # 09:00 dan 20:00 gacha 1 soatlik slotlarni tekshiramiz
            start_hour = 9
            if target_date == datetime.now(tz).date():
                now_hour = datetime.now(tz).hour
                if now_hour >= 9:
                    start_hour = now_hour + 1
            
            for hour in range(start_hour, 20):
                if not unresolved:
                    break
                    
                slot_start = tz.localize(datetime.combine(target_date, time(hour=hour, minute=0)))
                slot_end = slot_start + timedelta(hours=1)
                
                # Check overlap
                overlap = False
                for b_start, b_end in blocked_intervals:
                    if max(slot_start, b_start) < min(slot_end, b_end):
                        overlap = True
                        break
                        
                if not overlap:
                    task_to_schedule = unresolved.pop(0)
                    start_str = slot_start.isoformat()
                    end_str = slot_end.isoformat()
                    res = await self.calendar_add_event(
                        summary=task_to_schedule,
                        start_time=start_str,
                        end_time=end_str,
                        description="Auto-scheduled by Aziza Timeboxing"
                    )
                    if "✅" in res:
                        scheduled.append(f"• {target_date_str} {hour:02d}:00-{hour+1:02d}:00: {task_to_schedule}")
                    else:
                        unresolved.insert(0, task_to_schedule)
                        break
            
            day_offset += 1
            
        summary_msg = "📅 **Aziza Timeboxing Natijasi:**\n\n"
        if scheduled:
            summary_msg += "✅ Muvaffaqiyatli rejalashtirildi:\n" + "\n".join(scheduled) + "\n\n"
        if unresolved:
            summary_msg += "⚠️ Bo'sh vaqt yetishmasligi sababli rejalashtirilmagan vazifalar:\n" + "\n".join([f"• {t}" for t in unresolved])
            
        return summary_msg

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

    async def insta_get_niche_trends(self, hashtag: str, limit: int = 3) -> str:
        """Belgilangan hashtag bo'yicha eng zo'r postlarni topib analiz uchun beradi."""
        cl = await self._init_instagram()
        if not cl:
            return "❌ Instagram ulanmagan yoki avtorizatsiya rad etildi."
            
        try:
            def fetch_top_medias():
                # instagrapi hashtag_medias_top qaytaradi eng mashhur postlarni
                medias = cl.hashtag_medias_top(hashtag, amount=limit)
                results = []
                for m in medias:
                    # m.caption_text, m.like_count, m.comment_count
                    caption = m.caption_text or ""
                    likes = m.like_count
                    comments = m.comment_count
                    url = f"https://www.instagram.com/p/{m.code}/"
                    
                    results.append({
                        "url": url,
                        "likes": likes,
                        "comments": comments,
                        "caption": caption[:1000] # Matn uzun bo'lsa qisqartiramiz
                    })
                return results
                
            data = await asyncio.to_thread(fetch_top_medias)
            if not data:
                return f"#{hashtag} bo'yicha hech qanday post topilmadi."
                
            return f"#{hashtag} bo'yicha top {limit} postlar:\n\n" + str(data)
        except Exception as e:
            return f"❌ Instagram qidiruvida xato: {e}"

    async def insta_download_media(self, url: str) -> str | None:
        """Instagramdan video yoki rasmni yuklab oladi va fayl yo'lini qaytaradi."""
        cl = await self._init_instagram()
        if not cl:
            return None
            
        try:
            import tempfile
            from pathlib import Path
            
            # Vaqtinchalik papka yaratamiz
            temp_dir = Path(tempfile.gettempdir()) / "jarvis_insta"
            temp_dir.mkdir(exist_ok=True)
            
            def download():
                # instagrapi avtomatik video yoki photo ekanligini aniqlaydi va yuklaydi
                # video_download_by_url video yuklaydi, lekin agar rasta bo'lsa xato berishi mumkin
                # Shuning uchun media_info orqali tekshirish yaxshiroq, lekin by_url qulayroq.
                
                # Reels/Video uchun:
                if "/reels/" in url or "/p/" in url or "/tv/" in url:
                    try:
                        # video_download_by_url returns Path
                        path = cl.video_download_by_url(url, folder=temp_dir)
                        return str(path)
                    except Exception as e:
                        logger.warning(f"Video download xatosi, rasm sifatida urinib ko'ramiz: {e}")
                        path = cl.photo_download_by_url(url, folder=temp_dir)
                        return str(path)
                return None
                
            file_path = await asyncio.to_thread(download)
            return file_path
        except Exception as e:
            logger.error(f"❌ Instagram yuklashda xato: {e}")
            return None

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

    async def gmail_create_draft(self, to_email: str, subject: str, body: str) -> str:
        """Gmail drafts papkasiga yangi javob xati qoralamasini (Draft) saqlaydi."""
        if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
            return "❌ Gmail sozlanmagan (GMAIL_EMAIL yoki GMAIL_APP_PASSWORD yo'q)."
            
        try:
            import imaplib
            import time
            from email.mime.text import MIMEText
            
            def append_draft():
                msg = MIMEText(body, 'plain', 'utf-8')
                msg['To'] = to_email
                msg['Subject'] = subject
                msg['From'] = GMAIL_EMAIL
                raw_message = msg.as_bytes()
                
                mail = imaplib.IMAP4_SSL('imap.gmail.com')
                mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
                
                folder = '"[Gmail]/Drafts"'
                try:
                    mail.select(folder)
                except Exception:
                    try:
                        mail.select('Drafts')
                        folder = 'Drafts'
                    except Exception:
                        folder = '"[Gmail]/Drafts"'
                        
                res = mail.append(folder, '', imaplib.Time2Internaldate(time.time()), raw_message)
                mail.logout()
                return res
                
            res = await asyncio.to_thread(append_draft)
            return f"✅ Gmail qoralamasi muvaffaqiyatli saqlandi. Status: {res}"
        except Exception as e:
            logger.error(f"Gmail draft xatosi: {e}")
            return f"❌ Gmail draft xatosi: {e}"

    async def gmail_get_newsletters(self) -> str:
        """Inbox'dagi oxirgi 30 ta xatni skanerlab, reklama byulletenlari (newsletters) ro'yxatini va ularni tark etish (unsubscribe) havolalarini qaytaradi."""
        if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
            return "❌ Gmail sozlanmagan."
            
        try:
            def scan():
                mail = imaplib.IMAP4_SSL('imap.gmail.com')
                mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
                mail.select("inbox")
                
                status, messages = mail.search(None, 'ALL')
                if status != 'OK' or not messages[0]:
                    return "Xatlar topilmadi."
                    
                msg_nums = messages[0].split()
                to_fetch = msg_nums[-30:]
                
                newsletters = []
                for num in reversed(to_fetch):
                    res, msg_data = mail.fetch(num, '(RFC822)')
                    if res != 'OK': continue
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            unsub = msg.get('List-Unsubscribe')
                            sender = msg.get('From', 'Noma\'lum')
                            
                            subject_tuple = email.header.decode_header(msg['Subject'] or '')[0]
                            subject = subject_tuple[0]
                            if isinstance(subject, bytes):
                                try: subject = subject.decode(subject_tuple[1] or 'utf-8')
                                except: subject = str(subject)
                                
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode(errors='ignore')
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode(errors='ignore')
                                
                            is_newsletter = False
                            if unsub:
                                is_newsletter = True
                            elif "unsubscribe" in body.lower() or "newsletters" in body.lower() or "reklama" in body.lower():
                                is_newsletter = True
                                
                            if is_newsletter:
                                import re
                                email_match = re.search(r'<([^>]+)>', sender)
                                sender_email = email_match.group(1) if email_match else sender
                                newsletters.append({
                                    "sender": sender,
                                    "email": sender_email,
                                    "subject": subject,
                                    "unsub": unsub or "Mavjud emas"
                                })
                mail.logout()
                
                if not newsletters:
                    return "Inbox'da hech qanday reklama byulletenlari topilmadi."
                    
                lines = ["✉️ **Skanerlangan reklama byulletenlari (Newsletters):**\n"]
                for i, nl in enumerate(newsletters[:15], 1):
                    lines.append(f"{i}. **{nl['sender']}**\n   Mavzu: {nl['subject']}\n   Email: `{nl['email']}`\n   Unsubscribe: {nl['unsub']}")
                return "\n".join(lines)
                
            return await asyncio.to_thread(scan)
        except Exception as e:
            return f"❌ Reklamalarni skanerlashda xatolik: {e}"

    async def gmail_unsubscribe_sender(self, sender_email: str) -> str:
        """Berilgan email manzilidan kelgan xatlardagi List-Unsubscribe sarlavhasini topib, avtomatik ravishda obunani bekor qiladi."""
        if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
            return "❌ Gmail sozlanmagan."
            
        try:
            def unsubscribe():
                mail = imaplib.IMAP4_SSL('imap.gmail.com')
                mail.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
                mail.select("inbox")
                
                status, messages = mail.search(None, f'FROM "{sender_email}"')
                if status != 'OK' or not messages[0]:
                    mail.logout()
                    return f"❌ '{sender_email}' dan xatlar topilmadi."
                    
                msg_nums = messages[0].split()
                for num in reversed(msg_nums):
                    res, msg_data = mail.fetch(num, '(RFC822)')
                    if res != 'OK': continue
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            unsub = msg.get('List-Unsubscribe')
                            if unsub:
                                mail.logout()
                                return unsub
                mail.logout()
                return None
                
            unsub_header = await asyncio.to_thread(unsubscribe)
            
            if not unsub_header:
                body = "Please unsubscribe my email from your mailing list. Thank you."
                res = await self.gmail_send_email(sender_email, "Unsubscribe", body)
                return f"⚠️ '{sender_email}' dan List-Unsubscribe havolasi topilmadi. To'g'ridan-to'g'ri 'Unsubscribe' mavzusida email yuborildi."
                
            import re
            links = re.findall(r'<([^>]+)>', unsub_header)
            
            mailto_link = None
            web_link = None
            for link in links:
                if link.startswith("mailto:"):
                    mailto_link = link
                elif link.startswith("http"):
                    web_link = link
                    
            if web_link:
                import requests
                def fire_get():
                    r = requests.get(web_link, timeout=15)
                    return r.status_code
                status = await asyncio.to_thread(fire_get)
                return f"✅ '{sender_email}' dan muvaffaqiyatli chiqildi. Unsubscribe havolasi ochildi (HTTP {status}): {web_link}"
                
            elif mailto_link:
                mailto_clean = mailto_link.replace("mailto:", "")
                parts = mailto_clean.split("?")
                to_addr = parts[0]
                sub = "Unsubscribe"
                body = "Unsubscribe"
                if len(parts) > 1:
                    query = parts[1]
                    sub_match = re.search(r'subject=([^&]+)', query)
                    if sub_match:
                        import urllib.parse
                        sub = urllib.parse.unquote(sub_match.group(1))
                        
                await self.gmail_send_email(to_addr, sub, body)
                return f"✅ '{sender_email}' dan chiqish uchun '{to_addr}' manziliga so'rov yuborildi (Subject: {sub})."
                
            return f"❌ List-Unsubscribe sarlavhasini parse qilib bo'lmadi: `{unsub_header}`"
        except Exception as e:
            return f"❌ Obunani bekor qilishda xato yuz berdi: {e}"

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

    async def fetch_rss_feed(self, feed_url: str, limit: int = 5) -> list[dict]:
        """RSS tasmasini o'qiydi va title, link, summary, date ko'rinishida qaytaradi."""
        try:
            import urllib.request
            import xml.etree.ElementTree as ET
            
            def fetch():
                req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=15) as response:
                    return response.read()
                    
            xml_data = await asyncio.to_thread(fetch)
            root = ET.fromstring(xml_data)
            
            items = []
            for item in root.findall('.//item')[:limit]:
                title = item.find('title')
                link = item.find('link')
                description = item.find('description')
                pubDate = item.find('pubDate')
                
                desc_text = description.text if description is not None else ""
                if desc_text:
                    import re
                    desc_text = re.sub(r'<[^>]+>', '', desc_text)
                    
                items.append({
                    "title": title.text if title is not None else "Sarlavhasiz",
                    "link": link.text if link is not None else "",
                    "summary": desc_text[:300] if desc_text else "",
                    "date": pubDate.text if pubDate is not None else ""
                })
            return items
        except Exception as e:
            logger.error(f"Error fetching RSS feed {feed_url}: {e}")
            return []

    async def generate_lead_magnet_pdf(self, title: str, sections: list[dict], filepath: str) -> None:
        """Kiritilgan ma'lumotlar asosida chiroyli dizayndagi PDF Lead Magnet yaratadi."""
        import datetime
        import asyncio
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.pdfgen import canvas
        
        class NumberedCanvas(canvas.Canvas):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._saved_page_states = []

            def showPage(self):
                self._saved_page_states.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                num_pages = len(self._saved_page_states)
                for state in self._saved_page_states:
                    self.__dict__.update(state)
                    if self._pageNumber > 1:
                        self.saveState()
                        self.setFont("Helvetica", 9)
                        self.setFillColor(colors.HexColor("#4A5568"))
                        self.drawString(54, 750, title)
                        self.setStrokeColor(colors.HexColor("#CBD5E0"))
                        self.setLineWidth(0.5)
                        self.line(54, 742, letter[0] - 54, 742)
                        
                        page_text = f"Sahifa {self._pageNumber} / {num_pages}"
                        self.drawRightString(letter[0] - 54, 40, page_text)
                        self.drawString(54, 40, "© J.A.R.V.I.S. Marketing Lead Magnet")
                        self.line(54, 52, letter[0] - 54, 52)
                        self.restoreState()
                    super().showPage()
                super().save()

        def build_pdf():
            doc = SimpleDocTemplate(
                filepath,
                pagesize=letter,
                leftMargin=54,
                rightMargin=54,
                topMargin=72,
                bottomMargin=72
            )
            
            styles = getSampleStyleSheet()
            
            title_style = ParagraphStyle(
                'CoverTitle',
                parent=styles['Normal'],
                fontName='Helvetica-Bold',
                fontSize=28,
                leading=34,
                textColor=colors.HexColor("#1A365D"),
                alignment=1,
                spaceAfter=15
            )
            
            subtitle_style = ParagraphStyle(
                'CoverSubtitle',
                parent=styles['Normal'],
                fontName='Helvetica',
                fontSize=14,
                leading=18,
                textColor=colors.HexColor("#4A5568"),
                alignment=1,
                spaceAfter=40
            )
            
            h1_style = ParagraphStyle(
                'Heading1_Custom',
                parent=styles['Heading1'],
                fontName='Helvetica-Bold',
                fontSize=18,
                leading=22,
                textColor=colors.HexColor("#2B6CB0"),
                spaceBefore=15,
                spaceAfter=10,
                keepWithNext=True
            )
            
            body_style = ParagraphStyle(
                'Body_Custom',
                parent=styles['BodyText'],
                fontName='Helvetica',
                fontSize=10.5,
                leading=15,
                textColor=colors.HexColor("#2D3748"),
                spaceAfter=10
            )
            
            story = []
            story.append(Spacer(1, 150))
            story.append(Paragraph(title, title_style))
            story.append(Spacer(1, 10))
            story.append(Paragraph("J.A.R.V.I.S tomonidan avtomatik yaratilgan marketing qo'llanmasi (Lead Magnet)", subtitle_style))
            story.append(Spacer(1, 150))
            
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            meta_style = ParagraphStyle('CoverMeta', parent=body_style, alignment=1)
            story.append(Paragraph(f"<b>Tayyorlovchi:</b> Isroiljon Abdullayev<br/><b>Tahlilchi:</b> J.A.R.V.I.S. AI<br/><b>Sana:</b> {today_str}", meta_style))
            story.append(PageBreak())
            
            for section in sections:
                story.append(Paragraph(section.get('heading', ''), h1_style))
                for p in section.get('paragraphs', []):
                    story.append(Paragraph(p, body_style))
                story.append(Spacer(1, 15))
                
            doc.build(story, canvasmaker=NumberedCanvas)
            
        await asyncio.to_thread(build_pdf)
