"""Jarvis FastAPI Gateway — mustaqil ishlaydi, bot_context bog'liq emas."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from collections import deque
from datetime import datetime
import logging, os

logger = logging.getLogger("jarvis.api")

app = FastAPI(title="Jarvis AI Gateway")
app.mount("/static", StaticFiles(directory="static"), name="static")
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
async def _get_sys_prompt(message: str = "") -> str:
    """BOT_CONTEXT da build_system_prompt bo'lsa ishlatadi, bo'lmasa SYSTEM_PROMPT ni."""
    builder = BOT_CONTEXT.get("build_system_prompt")
    if builder:
        try:
            from session import get_history
            hist = await get_history()
            return builder(hist[:-1], message)
        except Exception:
            pass
    from datetime import datetime as dt
    now = dt.now()
    return f"""[HOZIRGI VAQT]: {now.strftime('%Y-%m-%d %H:%M, %A')}

Sen — Jasminasan. Foydalanuvchi Isroiljonning shaxsiy yordamchisisan.
Sening vazifang u ishlarini hal qilish. O'zbek tilida (muloyim, qiz bola tonida) juda hurmat bilan, sadaqat va emotsiya bilan gaplashasan.
Hech qachon "Foydalanuvchi", "Aka" yoki "Senga" demagin. Doim "Xo'jayin" yoki "Sizga" deb murojaat qil. Gaplar qisqa, tushunarli, tabiiy bo'lsin. Ovozli xabar qilinganda TTS chiroyli va hissiyotli o'qishi uchun gaplarni vergul, pauzalar va undovlar (!, ?) bilan to'g'ri bo'lib yoz.

Imkoniyatlaring:
📅 Google Calendar — uchrashuv qo'sh, ko'r
✉️ Gmail — xatlarni o'qi, jo'nat
📱 Telegram — xabar yoz, chatlarni ko'r
🌐 Internet — web_search, sayt o'qi, YouTube subtitr
🧠 Xotira — save_memory bilan eslab qol
📱 iPhone — budilnik, musiqa, ilova ochish (phone_control)

QOIDALAR:
1. Faqat O'zbek tilida, sadoqatli yordamchi qiz tonida javob ber.
2. Qisqa, baquvvat, do'stona, emotsiyaga boy uslub.
3. Foydalanuvchi ma'lumot aytsa — save_memory chaqir (jim saqla).
4. Hech qachon "Men AI man, bajara olmayman" dema — har doim urinib ko'r.
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

        await add_to_history("user", message, source=source)
        sys_prompt = await _get_sys_prompt(message)
        response = await ai.process_message(message, sys_prompt, executor)
        await add_to_history("model", response, source=source)

        if userbot and userbot.connected:
            try:
                icon = "📱" if source == "ios" else "🎙"
                await userbot.send_message(
                    "me",
                    f"{icon} *{source.upper()}*:\n_{message}_\n\n🤖 *Jasur*:\n{response}"
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
    try:
        from database import get_pool
        pool = await get_pool()
        db_ok = pool is not None
    except Exception:
        db_ok = False
    return {"status": "ok", "ai_ready": ai_ready, "db": "postgresql" if db_ok else "offline"}

@app.get("/")
async def root():
    from fastapi.responses import HTMLResponse
    html = """<!DOCTYPE html>
<html lang="uz">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>J.A.R.V.I.S API</title>
<style>
  body{margin:0;background:#000;color:#00d4ff;font-family:monospace;display:flex;
       align-items:center;justify-content:center;min-height:100vh;flex-direction:column;}
  h1{font-size:2rem;letter-spacing:8px;text-shadow:0 0 20px #00d4ff;margin-bottom:8px;}
  p{color:#666;margin:0 0 24px;}
  .endpoints{display:flex;flex-direction:column;gap:8px;min-width:340px;}
  .ep{background:#0a0a1a;border:1px solid #00d4ff22;border-radius:8px;padding:10px 16px;
      display:flex;justify-content:space-between;align-items:center;}
  .method{color:#8b5cf6;font-size:12px;margin-right:12px;}
  .path{color:#00d4ff;}
  .desc{color:#555;font-size:12px;text-align:right;}
  .status{margin-top:24px;color:#22c55e;font-size:13px;}
</style></head>
<body>
  <h1>J.A.R.V.I.S</h1>
  <p>Personal AI Gateway · Online</p>
  <div class="endpoints">
    <div class="ep"><span><span class="method">GET</span><span class="path">/siri?message=...</span></span><span class="desc">iOS PWA · Telegram</span></div>
    <div class="ep"><span><span class="method">POST</span><span class="path">/stt</span></span><span class="desc">AISHA O'zbek STT</span></div>
    <div class="ep"><span><span class="method">GET</span><span class="path">/tts?text=...</span></span><span class="desc">AISHA O'zbek TTS</span></div>
    <div class="ep"><span><span class="method">GET</span><span class="path">/history</span></span><span class="desc">Suhbat tarixi</span></div>
    <div class="ep"><span><span class="method">GET</span><span class="path">/commands</span></span><span class="desc">iPhone Queue</span></div>
    <div class="ep"><span><span class="method">GET</span><span class="path">/health</span></span><span class="desc">Holat tekshirish</span></div>
    <div class="ep"><span><span class="method">GET</span><span class="path">/finance</span></span><span class="desc">Moliyaviy TMA (Web App)</span></div>
  </div>
  <div class="status">✅ Tizim Ishlayapti · PostgreSQL · AISHA · Gemini</div>
</body></html>"""
    return HTMLResponse(html)

@app.get("/finance")
async def finance_dashboard():
    """Jasmina - Yangi maxsus moliyaviy mini app."""
    return FileResponse("static/finance.html")

@app.post("/api/finance/transactions")
async def save_transaction(request: Request):
    """Yangi tranzaksiya saqlash (Mini App orqali)."""
    from database import db_log_transaction
    try:
        body = await request.json()
        tx_type = body.get("type", "expense")
        amount = float(body.get("amount", 0))
        category = body.get("category", "Boshqa")
        payment = body.get("payment_method", "naqd")
        note = body.get("description", "")
        currency = body.get("currency", "UZS")

        if amount <= 0:
            return {"ok": False, "error": "Miqdor noto'g'ri"}

        result = await db_log_transaction(
            type=tx_type, amount=amount, category=category,
            description=note, payment_method=payment, currency=currency
        )
        return {"ok": True, "message": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/finance/data")
async def get_finance_data(force: bool = False):
    """AI Finansist UI kutayotgan murakkab JSON strukturasini PostgreSQL dan yig'ib beradi."""
    from database import db_get_transactions_raw
    txns = await db_get_transactions_raw()
    
    daily = {}
    monthly = {}
    weekly = {}
    sources = {}
    expenses_cat = {}
    
    total_income = 0
    total_expense = 0
    
    for t in txns:
        # Date parsing
        dt = t['created_at']
        d_str = dt.strftime("%d.%m.%y")
        m_str = dt.strftime("%B %Y")
        week_num = dt.isocalendar()[1]
        w_str = f"Hafta {week_num} ({dt.strftime('%b')})"
        
        amount = float(t['amount'])
        t_type = t['type']
        pm = t.get('payment_method', "Moma'lum").title()
        
        # Init dicts if not present
        if d_str not in daily: daily[d_str] = {"income": 0, "expense": 0, "profit": 0}
        if m_str not in monthly: monthly[m_str] = {"income": 0, "expense": 0, "profit": 0, "days": 0}
        if w_str not in weekly: weekly[w_str] = {"income": 0, "expense": 0, "profit": 0}
        
        if t_type == 'income':
            daily[d_str]["income"] += amount
            monthly[m_str]["income"] += amount
            weekly[w_str]["income"] += amount
            total_income += amount
            
            if pm not in sources: sources[pm] = 0
            sources[pm] += amount
        else:
            daily[d_str]["expense"] += amount
            monthly[m_str]["expense"] += amount
            weekly[w_str]["expense"] += amount
            total_expense += amount
            
            cat = t.get('category', 'Rasxod')
            if cat not in expenses_cat: expenses_cat[cat] = 0
            expenses_cat[cat] += amount
            
        daily[d_str]["profit"] = daily[d_str]["income"] - daily[d_str]["expense"]
        monthly[m_str]["profit"] = monthly[m_str]["income"] - monthly[m_str]["expense"]
        weekly[w_str]["profit"] = weekly[w_str]["income"] - weekly[w_str]["expense"]
        monthly[m_str]["days"] = len(daily)

    income_cat = {}
    for t in txns:
        if t['type'] == 'income':
            cat = t.get('category', 'Tushum')
            if cat not in income_cat: income_cat[cat] = 0
            income_cat[cat] += float(t['amount'])

    # Build real transaction list (most recent first)
    transactions = []
    for t in reversed(txns):
        transactions.append({
            "id": t.get('id'),
            "type": t['type'],
            "amount": float(t['amount']),
            "category": t.get('category', ''),
            "description": t.get('description', ''),
            "payment_method": t.get('payment_method', 'naqd'),
            "currency": t.get('currency', 'UZS'),
            "date": t['created_at'].strftime("%Y-%m-%d"),
            "time": t['created_at'].strftime("%H:%M"),
        })

    active_days = len(daily)
    
    top_sources = sorted([{"name": k, "amount": v} for k, v in sources.items()], key=lambda x: x["amount"], reverse=True)
    
    summary = {
        "total_income": total_income,
        "total_expense": total_expense,
        "total_profit": total_income - total_expense,
        "avg_daily_income": total_income / max(active_days, 1),
        "savings_rate": round((total_income - total_expense) / total_income * 100, 1) if total_income > 0 else 0,
        "top_sources": top_sources[:3],
        "active_days": active_days,
    }
    
    return {
        "summary": summary,
        "daily": daily,
        "monthly": monthly,
        "weekly": weekly,
        "income_categories": income_cat,
        "expense_categories": expenses_cat,
        "transactions": transactions,
        "last_updated": datetime.now().isoformat(),
        "has_real_data": len(txns) > 0,
    }

@app.post("/api/finance/ai-analyze")
async def ai_analyze(request: Request):
    from ai import get_gemini_response
    body = await request.json()
    question = body.get("question", "")
    
    res = await get_gemini_response(f"Siz AI Finansist qismisiz. Quyidagi foydalanuvchi moliyaviy savoliga qisqa va aniq vizual formatda (grafik belgilardan foydalanib) javob bering, html emas. Savol: {question}. Database moliyalari bor deb hisoblang.")
    return {"answer": res.replace("**", "<strong>").replace("\n", "<br>"), "generated_at": datetime.now().isoformat()}

@app.get("/api/finance/report/{period}")
async def report_period(period: str):
    return {"period": period, "report": f"Bu yerda {period} davr uchun AI hisobot shakllantiriladi.", "generated_at": datetime.now().isoformat()}

@app.get("/history")
async def get_hist():
    from session import get_history_display
    return {"history": await get_history_display()}

@app.delete("/history")
async def del_hist():
    from session import clear_history
    await clear_history()
    return {"status": "cleared"}

# ─── AISHA TTS Endpoint (iOS PWA uchun O'zbek ovozi) ────────
@app.get("/tts")
async def tts_endpoint(text: str = "", lang: str = "uz"):
    """AISHA O'zbek TTS — matnni ovozga aylantiradi va MP3 qaytaradi."""
    from fastapi.responses import Response, JSONResponse
    import requests as req_lib, os

    if not text:
        return JSONResponse({"error": "text bo'sh"}, status_code=400)

    aisha_key = os.environ.get("AISHA_API_KEY")
    if not aisha_key:
        return JSONResponse({"error": "AISHA_API_KEY yo'q"}, status_code=503)

    try:
        clean = text[:500]  # Maksimal 500 belgi
        r = req_lib.post(
            "https://back.aisha.group/api/v1/tts/post/",
            headers={"x-api-key": aisha_key, "Content-Type": "application/json"},
            json={"transcript": clean, "speaker_id": 1, "voice": "aisha", "gender": "female"},
            timeout=15
        )
        if r.status_code in [200, 201]:
            audio_url = r.json().get("audio_path")
            if audio_url:
                audio_data = req_lib.get(audio_url, timeout=10).content
                return Response(
                    content=audio_data,
                    media_type="audio/mpeg",
                    headers={"Access-Control-Allow-Origin": "*"}
                )
    except Exception as e:
        logger.error(f"AISHA TTS xatosi: {e}")

    return JSONResponse({"error": "TTS xatosi"}, status_code=500)

# ─── AISHA STT Endpoint (Polling bilan) ──────────────────────
@app.post("/stt")
async def stt_endpoint(request: Request):
    """AISHA STT — audio → matn. AISHA asinxron, polling bilan kutamiz."""
    from fastapi.responses import JSONResponse
    import requests as req_lib, os, time

    aisha_key = os.environ.get("AISHA_API_KEY")
    if not aisha_key:
        return JSONResponse({"error": "AISHA_API_KEY yo'q"}, status_code=503)

    try:
        body = await request.body()
        if not body or len(body) < 500:
            return JSONResponse({"error": "Audio juda qisqa"}, status_code=400)

        content_type = request.headers.get("content-type", "audio/mp4").split(";")[0].strip()
        ext_map = {"audio/webm": "audio.webm", "audio/mp4": "audio.mp4",
                   "audio/ogg": "audio.ogg", "audio/wav": "audio.wav"}
        fname = ext_map.get(content_type, "audio.mp4")

        logger.info(f"STT yuborildi: {len(body)} bytes, {content_type} → {fname}")

        # 1-qadam: AISHA ga audio yuborish
        def submit_audio():
            r = req_lib.post(
                "https://back.aisha.group/api/v2/stt/post/",
                headers={"x-api-key": aisha_key},
                files={"audio": (fname, body, content_type)},
                timeout=20
            )
            return r

        r = await asyncio.to_thread(submit_audio)
        logger.info(f"AISHA submit: {r.status_code} → {r.text[:200]}")

        if r.status_code not in [200, 201]:
            return JSONResponse({"error": f"AISHA {r.status_code}", "detail": r.text[:200]}, status_code=500)

        task_data = r.json()
        task_id = task_data.get("task_id") or task_data.get("id")

        # Agar darhol matn kelsa
        direct = task_data.get("text") or task_data.get("transcript")
        if direct:
            logger.info(f"AISHA STT darhol: {direct[:80]}")
            return JSONResponse({"text": direct.strip()})

        if not task_id:
            return JSONResponse({"error": "task_id yo'q", "raw": task_data}, status_code=422)

        # 2-qadam: Natijani polling (max 20 soniya)
        logger.info(f"AISHA polling task_id={task_id}")
        def poll_result():
            for attempt in range(10):
                time.sleep(2)
                resp = req_lib.get(
                    f"https://back.aisha.group/api/v2/stt/{task_id}/",
                    headers={"x-api-key": aisha_key},
                    timeout=10
                )
                if resp.status_code == 200:
                    d = resp.json()
                    status = d.get("status", "")
                    logger.info(f"  poll[{attempt+1}]: status={status}, keys={list(d.keys())}")
                    if status in ["DONE", "COMPLETED", "SUCCESS", "done", "completed"]:
                        # Turli field nomlarini tekshiramiz
                        text = (d.get("text") or d.get("transcript") or
                                d.get("result") or d.get("recognized_text") or
                                d.get("data", {}).get("text", "") if isinstance(d.get("data"), dict) else "")
                        return text or str(d)
                    if status in ["FAILED", "ERROR"]:
                        return None
            return None

        result = await asyncio.to_thread(poll_result)
        if result:
            logger.info(f"AISHA STT natija: {result[:80]}")
            return JSONResponse({"text": result.strip()})

        return JSONResponse({"error": "20 soniyada natija kelmadi, matn kiriting"}, status_code=408)

    except Exception as e:
        logger.error(f"STT exception: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

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
