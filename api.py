"""Jarvis FastAPI Gateway — mustaqil ishlaydi, bot_context bog'liq emas."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from collections import deque
from datetime import datetime
import logging, os

logger = logging.getLogger("jarvis.api")

app = FastAPI(title="Jarvis AI Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic ────────────────────────────────────────────────
class SiriRequest(BaseModel):
    message: str

class PhoneCommand(BaseModel):
    type: str
    payload: Optional[str] = ""
    time: Optional[str] = ""

# ─── Bog'liqliklar (bot.py dan inject qilinadi) ─────────────
BOT_CONTEXT: dict = {}

# ─── iPhone Command Queue ────────────────────────────────────
COMMAND_QUEUE: deque = deque(maxlen=20)

def push_phone_command(cmd_type: str, payload: str = "", time: str = ""):
    COMMAND_QUEUE.append({"type": cmd_type, "payload": payload, "time": time})
    logger.info(f"📱 Telefon buyrug'i: {cmd_type} | {payload}")

# ─── Ichki yordamchi: AI va system prompt ───────────────────
def _get_sys_prompt(message: str = "") -> str:
    """BOT_CONTEXT da build_system_prompt bo'lsa ishlatadi, bo'lmasa SYSTEM_PROMPT ni."""
    builder = BOT_CONTEXT.get("build_system_prompt")
    if builder:
        try:
            from session import get_history
            hist = get_history()
            return builder(hist[:-1], message)
        except Exception:
            pass
    # Zaxira: to'liq SYSTEM_PROMPT ni o'zi yaratadi
    from datetime import datetime as dt
    now = dt.now()
    return f"""[HOZIRGI VAQT]: {now.strftime('%Y-%m-%d %H:%M, %A')}

Sen — Jarvis. Foydalanuvchi Isroiljon Abdullayevning shaxsiy Omni-Channel AI yordamchisisan.
Sening vazifang uning shaxsiy ishlari, rejalari va ijtimoiy tarmoqlarini bitta joydan boshqarish.

Imkoniyatlaring:
📅 Google Calendar — uchrashuv qo'sh, ko'r
✉️ Gmail — xatlarni o'qi, jo'nat
📱 Telegram — xabar yoz, chatlarni ko'r
🌐 Internet — web_search, sayt o'qi, YouTube subtitr
🧠 Xotira — save_memory bilan eslab qol
📱 iPhone — budilnik, musiqa, ilova ochish (phone_control)

QOIDALAR:
1. Faqat O'zbek tilida javob ber (agar Rus yoki boshqa tilda so'ralsa ham)
2. Qisqa, aniq, do'stona uslub
3. Foydalanuvchi ma'lumot aytsa — save_memory chaqir (jim saqla)
4. Hech qachon "Men AI man, bajara olmayman" dema — har doim urinib ko'r
"""

# ─── ENDPOINTS ───────────────────────────────────────────────

@app.post("/siri")
async def siri_post(req: SiriRequest):
    return await _process(req.message, source="siri-post")

@app.get("/siri")
async def siri_get(message: str = ""):
    if not message:
        return {"status": "error", "reason": "message bo'sh"}
    return await _process(message, source="ios")

async def _process(message: str, source: str = "ios"):
    """Ikki endpoint ham bir xil yerni chaqiradi — bitta miya."""
    ai       = BOT_CONTEXT.get("ai")
    executor = BOT_CONTEXT.get("execute_tool")
    userbot  = BOT_CONTEXT.get("userbot")

    if not ai:
        return {"status": "error", "reason": "Server hali tayyor emas, 1 daqiqa kuting."}

    try:
        from session import add_to_history, get_history

        add_to_history("user", message, source=source)
        sys_prompt = _get_sys_prompt(message)
        response = await ai.process_message(message, sys_prompt, executor)
        add_to_history("model", response, source=source)

        if userbot and userbot.connected:
            try:
                icon = "📱" if source == "ios" else "🎙"
                await userbot.send_message(
                    "me",
                    f"{icon} *{source.upper()}*:\n_{message}_\n\n🤖 *Jarvis*:\n{response}"
                )
            except Exception:
                pass

        return {"status": "success", "response": response}

    except Exception as e:
        logger.error(f"[{source}] Xatolik: {e}", exc_info=True)
        return {"status": "error", "reason": str(e)}


@app.get("/health")
async def health():
    ai_ready = bool(BOT_CONTEXT.get("ai"))
    return {"status": "ok", "ai_ready": ai_ready}

@app.get("/history")
async def get_hist():
    from session import get_history_display
    return {"history": get_history_display()}

@app.delete("/history")
async def del_hist():
    from session import clear_history
    clear_history()
    return {"status": "cleared"}

# ─── iPhone Command Queue ─────────────────────────────────────
@app.get("/commands")
async def get_commands():
    if not COMMAND_QUEUE:
        return {"commands": []}
    cmds = list(COMMAND_QUEUE)
    COMMAND_QUEUE.clear()
    return {"commands": cmds}

@app.post("/commands")
async def add_command(cmd: PhoneCommand):
    push_phone_command(cmd.type, cmd.payload, cmd.time)
    return {"status": "queued", "command": cmd.type}
