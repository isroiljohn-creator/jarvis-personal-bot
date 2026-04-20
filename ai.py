"""Gemini AI moduli — Function Calling, Vision, TTS bilan."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import google.generativeai as genai

logger = logging.getLogger("jarvis.ai")

# ───────────────────── Tool deklaratsiyalari ─────────────────────

TOOL_DECLARATIONS = [
    {
        "name": "run_command",
        "description": (
            "Kompyuterda terminal (shell) buyrug'ini bajaradi. "
            "macOS va Linux buyruqlarini qo'llab-quvvatlaydi. "
            "Misol: ls, pwd, whoami, df -h, brew list, pip list."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING", "description": "Terminal buyrug'i"}
            },
            "required": ["command"],
        },
    },
    {
        "name": "screenshot_analyze",
        "description": (
            "Kompyuter ekranining rasmini oladi va AI bilan tahlil qiladi. "
            "Foydalanuvchi 'ekranni ko'r', 'ekranda nima bor', 'screenshot' desa chaqir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "question": {
                    "type": "STRING",
                    "description": "Ekran haqida savol",
                }
            },
            "required": ["question"],
        },
    },
    {
        "name": "open_app",
        "description": "Kompyuterda dastur/ilovani ochadi (Chrome, Safari, VS Code, Spotify...).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {"type": "STRING", "description": "Dastur nomi"}
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Internetdan ma'lumot qidiradi. Har qanday savol, yangilik, "
            "narx, faktlar uchun shu toolni ishlatgan."
        ),
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
        "description": (
            "Telegram orqali matnli xabar yuboradi. "
            "Foydalanuvchining shaxsiy akkountidan boshqa kishiga yozadi."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "contact": {
                    "type": "STRING",
                    "description": "Qabul qiluvchi ismi yoki chat_id",
                },
                "message": {
                    "type": "STRING",
                    "description": "Xabar matni",
                },
            },
            "required": ["contact", "message"],
        },
    },
    {
        "name": "send_telegram_voice",
        "description": (
            "Telegram orqali ovozli xabar yuboradi. "
            "Matn ovozga aylantiriladi va voice message sifatida yuboriladi."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "contact": {
                    "type": "STRING",
                    "description": "Qabul qiluvchi ismi yoki chat_id",
                },
                "message": {
                    "type": "STRING",
                    "description": "Ovozli xabar matni",
                },
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
                "limit": {
                    "type": "INTEGER",
                    "description": "Nechta chat (default: 10)",
                }
            },
        },
    },
    {
        "name": "read_telegram_chat",
        "description": "Telegram chatdagi so'nggi xabarlarni o'qiydi.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "contact": {
                    "type": "STRING",
                    "description": "Chat nomi, username yoki ID",
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Nechta xabar (default: 5)",
                },
            },
            "required": ["contact"],
        },
    },
    {
        "name": "file_operation",
        "description": (
            "Fayl va papkalar bilan ishlaydi: "
            "list, read, create, delete, find, info."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "list | read | create | delete | find | info",
                },
                "path": {"type": "STRING", "description": "Fayl/papka yo'li"},
                "content": {
                    "type": "STRING",
                    "description": "Fayl tarkibi (create uchun)",
                },
                "search_name": {
                    "type": "STRING",
                    "description": "Fayl nomi (find uchun)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "save_memory",
        "description": (
            "Foydalanuvchi haqidagi muhim ma'lumotni xotiraga saqlaydi. "
            "Ism, yosh, shahar, kasb, sevimlilar, oila, rejalar va h.k. "
            "Bu toolni jim chaqir, foydalanuvchiga aytma."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": "identity | preferences | projects | relationships | notes",
                },
                "key": {"type": "STRING", "description": "Kalit (name, age, city)"},
                "value": {"type": "STRING", "description": "Qiymat"},
            },
            "required": ["category", "key", "value"],
        },
    },
    {
        "name": "system_info",
        "description": "Kompyuter tizimi haqida: CPU, RAM, disk, OS, uptime.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
]


# ───────────────────── AI Class ─────────────────────


class GeminiAI:
    """Gemini 2.0 Flash + Function Calling + Vision + TTS."""

    def __init__(self, api_key: str) -> None:
        genai.configure(api_key=api_key)
        self._vision_model = None
        logger.info("✅ Gemini 2.0 Flash tayyor")

    def _create_model(self, system_prompt: str = ""):
        """Har safar yangi model yaratish (system prompt bilan)."""
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

    # ─────────────── Asosiy chat + function calling ───────────────

    async def process_message(
        self,
        prompt: str,
        system_prompt: str,
        tool_executor,
        images: list[tuple[str, bytes]] | None = None,
    ) -> str:
        """
        Xabarni qayta ishlash — function calling loop bilan.

        Args:
            prompt: Foydalanuvchi xabari
            system_prompt: Tizim ko'rsatmasi (memory + qoidalar)
            tool_executor: async callable(name, args) -> str
            images: [(mime_type, bytes), ...] rasm ma'lumotlari

        Returns:
            AI javob matni
        """
        try:
            model = self._create_model(system_prompt)
            chat = model.start_chat()

            # Birinchi xabar
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

            # Function calling loop (max 8 marta)
            for _ in range(8):
                text, fn_calls = self._parse_response(response)

                if not fn_calls:
                    return text or "..."

                # Toollarni bajarish
                fn_results = []
                for fc in fn_calls:
                    logger.info(f"🔧 Tool: {fc['name']}({fc['args']})")
                    try:
                        result = await tool_executor(fc["name"], fc["args"])
                    except Exception as e:
                        result = f"❌ Tool xatosi: {e}"
                    fn_results.append({"name": fc["name"], "result": str(result)})

                # Natijalarni Gemini'ga qaytarish
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

            # Loop tugadi — oxirgi javobni qaytarish
            text, _ = self._parse_response(response)
            return text or "Jarayonni bajara olmadim."

        except Exception as e:
            logger.error(f"Gemini xatosi: {e}", exc_info=True)
            return f"❌ AI xatosi: {e}"

    def _parse_response(self, response) -> tuple[str | None, list[dict] | None]:
        """Gemini javobini tahlil qilish — matn va/yoki function calllar."""
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

    # ─────────────── Ovozni matnga aylantirish ───────────────

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

    # ─────────────── Rasm tahlili ───────────────

    async def analyze_image(
        self, image_data: bytes, prompt: str = ""
    ) -> str:
        """Rasmni Gemini Vision bilan tahlil qilish."""
        try:
            encoded = base64.b64encode(image_data).decode()
            question = (
                prompt or "Bu rasmda nima bor? O'zbek tilida batafsil tushuntir."
            )
            response = await self.vision_model.generate_content_async(
                [
                    {"inline_data": {"mime_type": "image/png", "data": encoded}},
                    question,
                ]
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Rasm tahlili xatosi: {e}")
            return f"❌ Rasm tahlili xatosi: {e}"

    # ─────────────── Matnni ovozga aylantirish (TTS) ───────────────

    async def text_to_speech(self, text: str, lang: str = "uz") -> str | None:
        """
        Matnni ovozga aylantirish — edge-tts bilan.
        OGG Opus fayl yo'lini qaytaradi (Telegram voice uchun).
        """
        try:
            import edge_tts

            voices = {
                "uz": "uz-UZ-SardorNeural",
                "ru": "ru-RU-DmitryNeural",
                "en": "en-US-GuyNeural",
                "tr": "tr-TR-AhmetNeural",
            }
            voice = voices.get(lang, voices["uz"])

            mp3_path = tempfile.mktemp(suffix=".mp3")
            ogg_path = tempfile.mktemp(suffix=".ogg")

            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(mp3_path)

            # MP3 → OGG Opus (Telegram voice uchun)
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", mp3_path,
                "-c:a", "libopus", "-b:a", "64k",
                "-application", "voip",
                ogg_path, "-y",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()

            # MP3 o'chirish
            try:
                os.unlink(mp3_path)
            except OSError:
                pass

            if os.path.exists(ogg_path) and os.path.getsize(ogg_path) > 0:
                return ogg_path
            return None

        except ImportError:
            logger.warning("edge-tts o'rnatilmagan, TTS ishlamaydi")
            return None
        except Exception as e:
            logger.error(f"TTS xatosi: {e}")
            return None
