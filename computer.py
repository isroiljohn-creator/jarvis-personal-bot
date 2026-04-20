"""Kompyuter boshqaruvi — terminal, screenshot, dastur ochish, web qidirish, fayl boshqaruvi."""

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
    """Kompyuter boshqaruvi — terminal, ekran, dastur, fayl, web."""

    def __init__(self) -> None:
        self.os_type = platform.system()  # Darwin / Linux / Windows
        logger.info(f"💻 Kompyuter: {self.os_type}")

    # ─────────────────── Terminal ───────────────────

    async def run_command(self, command: str, timeout: int = 30) -> str:
        """Shell buyrug'ini bajarish."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path.home()),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            output = (stdout or b"").decode(errors="replace")
            err = (stderr or b"").decode(errors="replace")
            result = output or err or "(bo'sh natija)"
            return result[:4000]
        except asyncio.TimeoutError:
            return "⏰ Buyruq vaqt limitini oshdi (30 soniya)"
        except Exception as e:
            return f"❌ Xato: {e}"

    # ─────────────────── Screenshot ───────────────────

    async def screenshot(self) -> bytes | None:
        """Ekran rasmini olish — PNG bytes qaytaradi."""
        try:
            tmp = tempfile.mktemp(suffix=".png")
            if self.os_type == "Darwin":
                proc = await asyncio.create_subprocess_exec(
                    "screencapture", "-x", tmp,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            elif self.os_type == "Linux":
                proc = await asyncio.create_subprocess_exec(
                    "import", "-window", "root", tmp,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            else:
                return None

            if os.path.exists(tmp):
                data = Path(tmp).read_bytes()
                os.unlink(tmp)
                return data
            return None
        except Exception as e:
            logger.error(f"Screenshot xatosi: {e}")
            return None

    # ─────────────────── Dastur ochish ───────────────────

    async def open_app(self, app_name: str) -> str:
        """Dasturni ochish."""
        try:
            if self.os_type == "Darwin":
                # macOS — open komandasi
                cmd = f"open -a '{app_name}'"
                result = await self.run_command(cmd, timeout=10)
                if "Unable to find" in result or "error" in result.lower():
                    # Spotlight qidirish bilan sinab ko'rish
                    cmd2 = f"mdfind 'kMDItemKind == Application' | grep -i '{app_name}' | head -1"
                    path = (await self.run_command(cmd2, timeout=5)).strip()
                    if path:
                        await self.run_command(f"open '{path}'", timeout=10)
                        return f"✅ {app_name} ochildi"
                    return f"❌ {app_name} topilmadi"
                return f"✅ {app_name} ochildi"
            elif self.os_type == "Linux":
                await self.run_command(f"xdg-open '{app_name}' &", timeout=5)
                return f"✅ {app_name} ochildi"
            else:
                return "❌ Bu OS uchun qo'llab-quvvatlanmaydi"
        except Exception as e:
            return f"❌ Dastur ochish xatosi: {e}"

    # ─────────────────── Web qidirish ───────────────────

    async def web_search(self, query: str) -> str:
        """DuckDuckGo orqali web qidirish."""
        try:
            from duckduckgo_search import DDGS

            loop = asyncio.get_event_loop()

            def _search():
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=5))
                return results

            results = await loop.run_in_executor(None, _search)

            if not results:
                return "Natija topilmadi."

            lines = [f"🔍 Qidiruv: {query}\n"]
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", "")
                lines.append(f"{i}. **{title}**\n   {body}\n   {href}\n")
            return "\n".join(lines)
        except ImportError:
            return "❌ duckduckgo-search o'rnatilmagan"
        except Exception as e:
            return f"❌ Qidiruv xatosi: {e}"

    # ─────────────────── Fayl boshqaruvi ───────────────────

    async def file_operation(
        self,
        action: str,
        path: str = "",
        content: str = "",
        search_name: str = "",
    ) -> str:
        """Fayl amallarini bajarish."""
        try:
            # Qisqa nomlarni kengaytirish
            shortcuts = {
                "desktop": str(Path.home() / "Desktop"),
                "downloads": str(Path.home() / "Downloads"),
                "documents": str(Path.home() / "Documents"),
                "home": str(Path.home()),
                "~": str(Path.home()),
            }
            if path.lower() in shortcuts:
                path = shortcuts[path.lower()]
            elif path.startswith("~"):
                path = str(Path(path).expanduser())
            elif not path:
                path = str(Path.home())

            p = Path(path)

            if action == "list":
                if not p.exists():
                    return f"❌ Yo'l topilmadi: {path}"
                items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
                lines = [f"📂 {path}:\n"]
                for item in items[:30]:
                    icon = "📁" if item.is_dir() else "📄"
                    size = ""
                    if item.is_file():
                        sz = item.stat().st_size
                        if sz > 1_000_000:
                            size = f" ({sz / 1_000_000:.1f} MB)"
                        elif sz > 1000:
                            size = f" ({sz / 1000:.1f} KB)"
                    lines.append(f"  {icon} {item.name}{size}")
                return "\n".join(lines)

            elif action == "read":
                if not p.exists():
                    return f"❌ Fayl topilmadi: {path}"
                text = p.read_text(encoding="utf-8", errors="replace")
                return text[:3000]

            elif action == "create":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content or "", encoding="utf-8")
                return f"✅ Fayl yaratildi: {path}"

            elif action == "delete":
                if not p.exists():
                    return f"❌ Topilmadi: {path}"
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                return f"✅ O'chirildi: {path}"

            elif action == "find":
                name = search_name or path
                cmd = f"find ~ -maxdepth 4 -iname '*{name}*' 2>/dev/null | head -15"
                return await self.run_command(cmd, timeout=10)

            elif action == "info":
                if not p.exists():
                    return f"❌ Topilmadi: {path}"
                stat = p.stat()
                return (
                    f"📄 {p.name}\n"
                    f"  Hajm: {stat.st_size:,} bytes\n"
                    f"  Turi: {'Papka' if p.is_dir() else p.suffix or 'Fayl'}\n"
                    f"  Yo'l: {p.absolute()}"
                )

            else:
                return f"❌ Noma'lum amal: {action}"

        except Exception as e:
            return f"❌ Fayl xatosi: {e}"

    # ─────────────────── Tizim ma'lumotlari ───────────────────

    async def system_info(self) -> str:
        """Tizim haqida ma'lumot."""
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            boot = psutil.boot_time()
            from datetime import datetime

            uptime = datetime.now() - datetime.fromtimestamp(boot)

            return (
                f"💻 Tizim ma'lumotlari:\n"
                f"  OS: {platform.system()} {platform.release()}\n"
                f"  CPU: {cpu}% band\n"
                f"  RAM: {mem.percent}% ({mem.used // (1024**3)}GB / {mem.total // (1024**3)}GB)\n"
                f"  Disk: {disk.percent}% ({disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB)\n"
                f"  Uptime: {str(uptime).split('.')[0]}"
            )
        except ImportError:
            # psutil yo'q — oddiy ma'lumot
            cmd = "uname -a && df -h / | tail -1"
            return await self.run_command(cmd)
        except Exception as e:
            return f"❌ Tizim xatosi: {e}"
