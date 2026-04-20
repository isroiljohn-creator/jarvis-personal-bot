"""Jarvis FastAPI Webhook Serveri — Siri, iOS PWA va iPhone Command Queue."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from collections import deque
import logging, json

logger = logging.getLogger("jarvis.api")

app = FastAPI(title="Jarvis AI Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SiriRequest(BaseModel):
    message: str

class PhoneCommand(BaseModel):
    type: str            # "alarm", "url", "music", "reminder", "notify"
    payload: Optional[str] = ""
    time: Optional[str] = ""

# ─── iPhone Command Queue ─────────────────────────────────────
COMMAND_QUEUE: deque = deque(maxlen=20)

def push_phone_command(cmd_type: str, payload: str = "", time: str = ""):
    """Bot yoki AI tomonidan chaqiriladi — navbatga buyruq qo'shadi."""
    COMMAND_QUEUE.append({"type": cmd_type, "payload": payload, "time": time})
    logger.info(f"📱 Yangi telefon buyrug'i: {cmd_type} | {payload}")

# Botga ham eksport qilamiz
BOT_CONTEXT = {"push_phone_command": push_phone_command}

@app.post("/siri")
async def siri_endpoint(req: SiriRequest):
    """Sivi (Siri) matnli xabari qabul qilinadi va Telegram orqali javob yuboriladi."""
    if not req.message:
        return {"status": "error", "reason": "No message"}
        
    ai = BOT_CONTEXT.get("ai")
    userbot = BOT_CONTEXT.get("userbot")
    builder = BOT_CONTEXT.get("build_system_prompt")
    executor = BOT_CONTEXT.get("execute_tool")
    
    if not userbot or not ai or not userbot.connected:
        return {"status": "error", "reason": "System is offline or not fully connected"}
    
    try:
        sys_prompt = builder([], req.message)
        response = await ai.process_message(req.message, sys_prompt, executor)
        
        await userbot.send_message("me", f"📱 *Siri orqali*:\n_{req.message}_\n\n🤖 *Javob*:\n{response}")
        return {"status": "success", "response": response}
    except Exception as e:
        logger.error(f"Siri webhook xatosi: {e}")
        return {"status": "error", "reason": str(e)}

@app.get("/siri")
async def siri_endpoint_get(message: str = ""):
    """iOS PWA va GET request uchun — to'liq Jarvis AI bilan ishlaydi."""
    if not message:
        return {"status": "error", "reason": "No message"}

    ai       = BOT_CONTEXT.get("ai")
    builder  = BOT_CONTEXT.get("build_system_prompt")
    executor = BOT_CONTEXT.get("execute_tool")
    userbot  = BOT_CONTEXT.get("userbot")

    if not ai:
        return {"status": "error", "reason": "AI hali ishga tushmagan, bir daqiqa kuting."}

    try:
        # To'liq Telegram bot bilan bir xil system prompt (bo'sh emas!)
        sys_prompt = builder([], message) if builder else ""
        response = await ai.process_message(message, sys_prompt, executor)

        # Agar userbot ulangan bo'lsa — Saved Messages ga ham nusxa jo'nat
        if userbot and userbot.connected:
            try:
                await userbot.send_message("me", f"📱 *iOS Ilova*:\n_{message}_\n\n🤖 *Javob*:\n{response}")
            except Exception:
                pass  # Telegram nusxasi bo'lmasa ham asosiy javob qaytadi

        return {"status": "success", "response": response}
    except Exception as e:
        logger.error(f"iOS PWA endpoint xatosi: {e}")
        return {"status": "error", "reason": str(e)}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# ─── iPhone Command Queue Endpoints ────────────────────────────

@app.get("/commands")
async def get_commands():
    """iPhone Shortcut har daqiqada shu endpointni tekshiradi.
    Yangi buyruq bo'lsa — qaytaradi va navbatdan o'chiradi."""
    if not COMMAND_QUEUE:
        return {"commands": []}
    
    # Barcha buyruqlarni olb navbatni tozalaymiz
    cmds = list(COMMAND_QUEUE)
    COMMAND_QUEUE.clear()
    return {"commands": cmds}

@app.post("/commands")
async def add_command(cmd: PhoneCommand):
    """Bot yoki boshqa manba telefonga buyruq qo'shadi."""
    push_phone_command(cmd.type, cmd.payload, cmd.time)
    return {"status": "queued", "command": cmd.type}
