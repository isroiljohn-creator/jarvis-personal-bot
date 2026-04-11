"""Gemini AI moduli."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from pathlib import Path

import google.generativeai as genai

logger = logging.getLogger("jarvis.ai")


class GeminiAI:
    """Google Gemini 1.5 Pro bilan ishlash."""

    def __init__(self, api_key: str) -> None:
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            generation_config={
                "temperature": 0.7,
                "top_p": 0.95,
                "max_output_tokens": 2048,
            },
        )
        self.vision_model = genai.GenerativeModel("gemini-2.0-flash")
        logger.info("✅ Gemini 2.0 Flash tayyor")

    async def ask(
        self,
        prompt: str,
        history: list[dict] | None = None,
        system_prompt: str = "",
    ) -> str:
        """Gemini'dan javob olish."""
        try:
            full_prompt = ""
            if system_prompt:
                full_prompt += f"{system_prompt}\n\n"

            # Tarix
            if history:
                for msg in history[-10:]:
                    role = "Siz" if msg["role"] == "user" else "Jarvis"
                    parts = msg.get("parts", [""])
                    full_prompt += f"{role}: {parts[0]}\n"

            full_prompt += f"\nFoydalanuvchi: {prompt}\nJarvis:"

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, lambda: self.model.generate_content(full_prompt)
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini xatosi: {e}")
            return f"❌ AI xatosi: {e}"

    async def transcribe(self, audio_path: str) -> str:
        """Ovozni matnга aylantirish (Gemini vision orqali)."""
        try:
            path = Path(audio_path)
            audio_data = path.read_bytes()
            encoded = base64.b64encode(audio_data).decode()

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.vision_model.generate_content(
                    [
                        {
                            "inline_data": {
                                "mime_type": "audio/ogg",
                                "data": encoded,
                            }
                        },
                        "Ushbu audio xabarni so'zma-so'z transkripsiya qil. Faqat matnni ber, boshqa hech narsa qo'shma.",
                    ]
                ),
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Transkriptsiya xatosi: {e}")
            return "[Ovozni aniqlash xatosi]"
