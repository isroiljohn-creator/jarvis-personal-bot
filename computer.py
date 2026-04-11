"""Kompyuter boshqaruvi moduli."""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger("jarvis.computer")


class ComputerAgent:
    """Terminal va kompyuter boshqaruvi."""

    def __init__(self) -> None:
        self.os_type = platform.system()
        logger.info(f"💻 Kompyuter: {self.os_type}")

    async def run_command(self, command: str, timeout: int = 30) -> str:
        """Shell buyrug'ini bajar va natija qaytare."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(Path.home()),
                ),
            )
            output = result.stdout or result.stderr or "(bo'sh natija)"
            return output[:4000]
        except subprocess.TimeoutExpired:
            return "⏰ Buyruq vaqt limitini oshdi (30 soniya)"
        except Exception as e:
            return f"❌ Xato: {e}"

    async def screenshot(self) -> str:
        """Ekran rasmini olish."""
        try:
            tmp = tempfile.mktemp(suffix=".png")
            if self.os_type == "Darwin":
                await self.run_command(f"screencapture -x {tmp}")
            elif self.os_type == "Linux":
                await self.run_command(f"import -window root {tmp}")
            elif self.os_type == "Windows":
                import ctypes
                # Windows uchun PIL ishlatamiz
                from PIL import ImageGrab
                img = ImageGrab.grab()
                img.save(tmp)
            return tmp
        except Exception as e:
            raise RuntimeError(f"Screenshot xatosi: {e}")

    async def list_files(self, path: str = "~") -> str:
        """Fayl ro'yxati."""
        expanded = str(Path(path).expanduser())
        return await self.run_command(f"ls -la {expanded}")

    async def read_file(self, path: str) -> str:
        """Faylni o'qish."""
        expanded = str(Path(path).expanduser())
        try:
            content = Path(expanded).read_text(encoding="utf-8", errors="replace")
            return content[:3000]
        except Exception as e:
            return f"❌ Fayl o'qilmadi: {e}"

    async def system_info(self) -> str:
        """Tizim ma'lumotlari."""
        if self.os_type == "Darwin":
            cmd = "system_profiler SPHardwareDataType | head -20 && df -h | head -5"
        elif self.os_type == "Linux":
            cmd = "uname -a && free -h && df -h | head -5"
        else:
            cmd = "systeminfo | head -20"
        return await self.run_command(cmd)
