"""Gemini AI moduli — Omni-Channel (Telegram, Insta, Cloud, Memory) Function Calling bilan."""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

import google.generativeai as genai

logger = logging.getLogger("jarvis.ai")

# ───────────────────── Tool deklaratsiyalari ─────────────────────

TOOL_DECLARATIONS = [
    {
        "name": "web_search",
        "description": "Internetdan ochiq ma'lumot qidiradi (DuckDuckGo).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Qidiruv so'rovi"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "send_telegram_message",
        "description": "Telegram orqali matnli xabar yuboradi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "contact": {"type": "STRING", "description": "Qabul qiluvchi ismi/chat_id"},
                "message": {"type": "STRING", "description": "Xabar matni"},
            },
            "required": ["contact", "message"],
        },
    },
    {
        "name": "send_telegram_voice",
        "description": "Telegram orqali ovozli xabar yuboradi (TTS qilib).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "contact": {"type": "STRING", "description": "Qabul qiluvchi ismi/chat_id"},
                "message": {"type": "STRING", "description": "Ovozli xabar matni"},
            },
            "required": ["contact", "message"],
        },
    },
    {
        "name": "list_telegram_chats",
        "description": "Telegramdagi so'nggi chatlar ro'yxatini ko'rsatadi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "limit": {"type": "INTEGER", "description": "Nechta chat (default: 10)"}
            },
        },
    },
    {
        "name": "read_telegram_chat",
        "description": "Telegram chatdagi so'nggi xabarlarni o'qiydi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "contact": {"type": "STRING", "description": "Chat nomi yoki ism"},
                "limit": {"type": "INTEGER", "description": "Nechta xabar (default: 5)"},
            },
            "required": ["contact"],
        },
    },
    {
        "name": "save_memory",
        "description": "Foydalanuvchi ma'lumotlarini uzoq muddatli xotiraga saqlaydi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "identity | preferences | projects | relationships | notes"},
                "key": {"type": "STRING", "description": "Kalit(masalan: name, work)"},
                "value": {"type": "STRING", "description": "Qiymat"},
            },
            "required": ["category", "key", "value"],
        },
    },
    {
        "name": "notion_add_task",
        "description": "Notion Database (To-Do) ga yangi vazifa qo'shadi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Vazifa nomi"},
                "status": {"type": "STRING", "description": "Status (masalan: Kutilmoqda, Bajarildi)"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "notion_read_tasks",
        "description": "Notiondan so'nggi vazifalarni o'qib keladi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "limit": {"type": "INTEGER", "description": "Nechta vazifa o'qish kerak"}
            },
        },
    },
    {
        "name": "calendar_add_event",
        "description": "Google Calendar ga yangi uchrashuv yozadi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "summary": {"type": "STRING", "description": "Uchrashuv nomi"},
                "start_time": {"type": "STRING", "description": "Boshlanish vaqti (ISO 8601, masalan 2026-04-20T10:00:00)"},
                "end_time": {"type": "STRING", "description": "Tugash vaqti (ISO 8601, masalan 2026-04-20T11:00:00)"},
                "description": {"type": "STRING", "description": "Batafsil izoh"},
            },
            "required": ["summary", "start_time", "end_time"],
        },
    },
    {
        "name": "calendar_get_events",
        "description": "Google Calendardan kelgusi uchrashuv va rejalar ro'yxatini oladi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "max_results": {"type": "INTEGER", "description": "Nechta event qaytarsin"}
            },
        },
    },
    {
        "name": "insta_send_dm",
        "description": "Instagram orqali ko'rsatilgan akkauntga to'g'ridan-to'g'ri DM (xabar) yuboradi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "username": {"type": "STRING", "description": "Instagram username (shunchaki nom, @ siz)"},
                "message": {"type": "STRING", "description": "Yuboriladigan xabar matni"},
            },
            "required": ["username", "message"],
        },
    },
    {
        "name": "gmail_read_unread",
        "description": "Gmail dan so'nggi o'qilmagan xatlarni o'qib keladi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "limit": {"type": "INTEGER", "description": "Nechta xabar o'qish (default: 5)"}
            },
        },
    },
    {
        "name": "gmail_send_email",
        "description": "Kimgadir email yuborish.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "to_email": {"type": "STRING", "description": "Qabul qiluvchining email manzili"},
                "subject": {"type": "STRING", "description": "Xat mavzusi"},
                "body": {"type": "STRING", "description": "Xat matni"},
            },
            "required": ["to_email", "subject", "body"],
        },
    },
]


class GeminiAI:
    """Gemini 2.0 Flash + Function Calling + Omni-Channels."""

    def __init__(self, api_key: str) -> None:
        genai.configure(api_key=api_key)
        self._vision_model = None
        logger.info("✅ Gemini 2.0 Flash tayyor")

    def _create_model(self, system_prompt: str = ""):
        return genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=system_prompt or None,
            generation_config={"temperature": 0.7, "max_output_tokens": 4096},
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
        )

    @property
    def vision_model(self):
        if not self._vision_model:
            self._vision_model = genai.GenerativeModel("gemini-2.0-flash")
        return self._vision_model

    async def process_message(
        self,
        prompt: str,
        system_prompt: str,
        tool_executor,
        images: list[tuple[str, bytes]] | None = None,
    ) -> str:
        """Xabarni qayta ishlash — function calling loop."""
        try:
            model = self._create_model(system_prompt)
            chat = model.start_chat()

            parts = []
            if images:
                for mime_type, data in images:
                    parts.append(
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(data).decode(),
                            }
                        }
                    )
            parts.append(prompt)

            response = await chat.send_message_async(parts)

            for _ in range(8):
                text, fn_calls = self._parse_response(response)

                if not fn_calls:
                    return text or "..."

                fn_results = []
                for fc in fn_calls:
                    logger.info(f"🔧 Tool: {fc['name']}({fc['args']})")
                    try:
                        result = await tool_executor(fc["name"], fc["args"])
                    except Exception as e:
                        result = f"❌ Tool xatosi: {e}"
                    fn_results.append({"name": fc["name"], "result": str(result)})

                response_parts = []
                for fr in fn_results:
                    response_parts.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=fr["name"],
                                response={"result": fr["result"]},
                            )
                        )
                    )

                response = await chat.send_message_async(
                    genai.protos.Content(parts=response_parts)
                )

            text, _ = self._parse_response(response)
            return text or "Jarayonni bajara olmadim."

        except Exception as e:
            logger.error(f"Gemini xatosi: {e}", exc_info=True)
            return f"❌ AI xatosi: {e}"

    def _parse_response(self, response) -> tuple[str | None, list[dict] | None]:
        text = None
        fn_calls = []
        try:
            if not response.candidates:
                return None, None
            for part in response.candidates[0].content.parts:
                if (
                    hasattr(part, "function_call")
                    and part.function_call
                    and part.function_call.name
                ):
                    fn_calls.append(
                        {
                            "name": part.function_call.name,
                            "args": (
                                dict(part.function_call.args)
                                if part.function_call.args
                                else {}
                            ),
                        }
                    )
                elif hasattr(part, "text") and part.text:
                    text = (text or "") + part.text
        except Exception as e:
            logger.error(f"Parse xatosi: {e}")

        return text, fn_calls or None

    async def transcribe(self, audio_path: str) -> str:
        """OGG audio faylni matnga aylantirish."""
        try:
            audio_data = Path(audio_path).read_bytes()
            encoded = base64.b64encode(audio_data).decode()
            response = await self.vision_model.generate_content_async(
                [
                    {"inline_data": {"mime_type": "audio/ogg", "data": encoded}},
                    "Ushbu audio xabarni so'zma-so'z transkripsiya qil. "
                    "Faqat matnni ber, boshqa hech narsa qo'shma.",
                ]
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Transkriptsiya xatosi: {e}")
            return "[Ovozni aniqlash xatosi]"

    async def analyze_image(
        self, image_data: bytes, prompt: str = ""
    ) -> str:
        """Rasmni Gemini Vision bilan tahlil qilish."""
        try:
            encoded = base64.b64encode(image_data).decode()
            question = prompt or "Bu rasmda nima bor? O'zbek tilida batafsil tushuntir."
            response = await self.vision_model.generate_content_async(
                [
                    {"inline_data": {"mime_type": "image/jpeg", "data": encoded}},
                    question,
                ]
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Rasm tahlili xatosi: {e}")
            return f"❌ Rasm tahlili xatosi: {e}"

    async def text_to_speech(self, text: str, lang: str = "uz") -> str | None:
        """Matnni ovozga aylantirish (edge-tts)."""
        import os, tempfile
        try:
            import edge_tts
            voices = {
                "uz": "uz-UZ-SardorNeural",
                "ru": "ru-RU-DmitryNeural",
                "en": "en-US-GuyNeural",
            }
            voice = voices.get(lang, voices["uz"])

            mp3_path = tempfile.mktemp(suffix=".mp3")
            ogg_path = tempfile.mktemp(suffix=".ogg")

            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(mp3_path)

            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", mp3_path,
                "-c:a", "libopus", "-b:a", "64k",
                "-application", "voip",
                ogg_path, "-y",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()

            try:
                os.unlink(mp3_path)
            except OSError:
                pass

            if os.path.exists(ogg_path) and os.path.getsize(ogg_path) > 0:
                return ogg_path
            return None
        except Exception as e:
            logger.error(f"TTS xatosi: {e}")
            return None
