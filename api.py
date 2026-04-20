"""Siri Shortcuts uchun FastAPI Webhook Serveri."""

from fastapi import FastAPI
from pydantic import BaseModel
import logging

logger = logging.getLogger("jarvis.api")

app = FastAPI(title="Jarvis Webhook (Siri)")

class SiriRequest(BaseModel):
    message: str

# Bizga bot instance va ai kerak, buni bot ishlayotganda update qilamiz.
BOT_CONTEXT = {}

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

@app.get("/health")
async def health_check():
    return {"status": "ok"}
