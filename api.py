"""Jarvis FastAPI Gateway — mustaqil ishlaydi, bot_context bog'liq emas."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from collections import deque
from datetime import datetime
import logging, os, asyncio

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

class HealthData(BaseModel):
    """iOS Sog'liq (Health) dasturidan kelgan ma'lumotlar."""
    steps: Optional[int] = None            # Qadam soni
    distance_km: Optional[float] = None   # Masofa (km)
    calories_active: Optional[float] = None  # Aktiv kaloriya
    calories_resting: Optional[float] = None # Dam olish kaloriyasi
    heart_rate_avg: Optional[float] = None   # O'rtacha yurak urishi
    heart_rate_min: Optional[float] = None
    heart_rate_max: Optional[float] = None
    hrv: Optional[float] = None            # Yurak urishi o'zgaruvchanligi
    sleep_hours: Optional[float] = None    # Uyqu soatlari
    sleep_deep_hours: Optional[float] = None  # Chuqur uyqu
    sleep_rem_hours: Optional[float] = None   # REM uyqu
    stand_hours: Optional[int] = None      # Turgan soatlar (Activity)
    exercise_minutes: Optional[int] = None # Mashq daqiqalari
    blood_oxygen: Optional[float] = None   # Qon kislorodi (%)
    respiratory_rate: Optional[float] = None  # Nafas olish tezligi
    noise_avg_db: Optional[float] = None   # O'rtacha shovqin (dB)
    weight_kg: Optional[float] = None      # Vazn (kg)
    body_fat_pct: Optional[float] = None   # Yog' foizi (%)
    mindful_minutes: Optional[int] = None  # Meditatsiya daqiqalari
    water_ml: Optional[int] = None         # Suvli ichimlik (ml)
    date: Optional[str] = None             # Sana (YYYY-MM-DD)

class ReminderItem(BaseModel):
    """Bitta iOS Reminders eslatmasi."""
    title: str
    due_date: Optional[str] = None         # ISO: "2026-04-26T10:00:00"
    completed: Optional[bool] = False
    list_name: Optional[str] = None        # Ro'yxat nomi
    notes: Optional[str] = None
    priority: Optional[int] = 0           # 0=yo'q, 1=past, 5=o'rta, 9=yuqori

class RemindersPayload(BaseModel):
    """iOS Reminders dan keluvchi eslatmalar to'plami."""
    reminders: list[ReminderItem]
    include_completed: Optional[bool] = False

class ScreenTimeApp(BaseModel):
    """Bitta ilovaning Screen Time ma'lumoti."""
    app_name: str
    category: Optional[str] = None        # "Social", "Productivity", "Entertainment"
    minutes: float

class ScreenTimePayload(BaseModel):
    """iOS Screen Time kunlik hisoboti."""
    apps: list[ScreenTimeApp]
    total_minutes: Optional[float] = None
    pickups: Optional[int] = None          # Telefon qo'lga olingan marta
    notifications: Optional[int] = None   # Bildirishnomalar soni
    date: Optional[str] = None

class MusicData(BaseModel):
    """Hozirgi musiqa holati."""
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    is_playing: Optional[bool] = None
    playlist: Optional[str] = None
    duration_seconds: Optional[int] = None
    position_seconds: Optional[int] = None

class MessagesData(BaseModel):
    """iOS Messages — o'qilmagan xabarlar holati."""
    unread_count: Optional[int] = None
    conversations: Optional[int] = None   # O'qilmagan suhbatlar soni
    date: Optional[str] = None


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


# ─── iOS Health Dasturi Ma'lumotlari ─────────────────────────

def _clean(text: str) -> str:
    """Telegram markdown belgilarini tozalaydi — xabar buzilmasligi uchun."""
    for ch in ("*", "_", "`", "[", "]", "#"):
        text = text.replace(ch, "")
    return text.strip()


@app.post("/ios-health")
async def ios_health_report(data: HealthData):
    """
    iOS Shortcuts automatsiyasi bu endpointga POST yuboradi.
    Health app ma'lumotlari Gemini tomonidan tahlil qilinib, Telegramga yuboriladi.
    """
    from fastapi.responses import JSONResponse

    ai       = BOT_CONTEXT.get("ai")
    executor = BOT_CONTEXT.get("execute_tool")
    userbot  = BOT_CONTEXT.get("userbot")
    bot      = BOT_CONTEXT.get("bot")
    owner_id = BOT_CONTEXT.get("owner_id")

    if not ai:
        return JSONResponse({"status": "error", "reason": "AI tayyor emas"}, status_code=503)

    # Faqat kelgan (None bo'lmagan) ma'lumotlarni qo'shamiz
    fields = [
        ("steps",            "👣",  "",        "qadam"),
        ("distance_km",      "📍",  " km",     "masofa"),
        ("calories_active",  "🔥",  " kkal",   "aktiv kaloriya"),
        ("heart_rate_avg",   "❤️",  " bpm",    "yurak (o'rt)"),
        ("heart_rate_min",   "❤️",  " bpm",    "yurak (min)"),
        ("heart_rate_max",   "❤️",  " bpm",    "yurak (max)"),
        ("hrv",              "📊",  " ms",     "HRV"),
        ("sleep_hours",      "😴",  " soat",   "uyqu"),
        ("sleep_deep_hours", "🛌",  " soat",   "chuqur"),
        ("sleep_rem_hours",  "💭",  " soat",   "REM"),
        ("stand_hours",      "🧍",  "/12",     "turish"),
        ("exercise_minutes", "🏃",  " daq",    "mashq"),
        ("blood_oxygen",     "🫁",  "%",       "O2"),
        ("respiratory_rate", "💨",  "/min",    "nafas"),
        ("weight_kg",        "⚖️",  " kg",     "vazn"),
        ("body_fat_pct",     "📉",  "%",       "yog'"),
        ("mindful_minutes",  "🧘",  " daq",    "med"),
        ("water_ml",         "💧",  " ml",     "suv"),
    ]
    raw = data.dict()
    lines = []
    ai_lines = []  # AI uchun qisqa format

    for field, emoji, unit, label in fields:
        val = raw.get(field)
        if val is not None:
            # int bo'lsa .0 ko'rsatmaslik
            display = int(val) if isinstance(val, float) and val == int(val) else val
            lines.append(f"{emoji} {label}: {display}{unit}")
            ai_lines.append(f"{label}: {display}{unit}")

    if not lines:
        return JSONResponse({"status": "error", "reason": "Ma'lumot yuborilmadi"}, status_code=400)

    date_str    = data.date or datetime.now().strftime("%Y-%m-%d")
    health_text = "  ".join(lines[:7]) + "\n" + "  ".join(lines[7:])  # 2 qatorda chiroyli
    ai_data     = ", ".join(ai_lines)

    # Ma'lumotlarni saqlaymiz — life_coach_job uchun
    BOT_CONTEXT["last_health"] = {"date": date_str, "data": raw, "summary": ai_data}

    logger.info(f"📱 iOS Health ma'lumoti keldi ({date_str}): {len(lines)} ko'rsatkich")

    # Qisqa, emoji-asosli prompt — sarlavha, ro'yxat, markdown YO'Q
    prompt = (
        f"Bugun {date_str}: {ai_data}. "
        "Sog'liq holatini 4-5 jumlada o'zbek tilida baholab ber. "
        "Faqat emoji va oddiy matn — sarlavha, ro'yxat, yulduzcha YO'Q. "
        "Eng muhim 1-2 maslahat bilan yakolla."
    )

    try:
        sys_prompt = await _get_sys_prompt("sog'liq")
        response   = await ai.process_message(prompt, sys_prompt, executor)
        # Markdown belgilarini tozalaymiz
        clean_resp = _clean(response)

        report = (
            f"🏥 Sog'liq — {date_str}\n\n"
            f"{health_text}\n\n"
            f"💬 {clean_resp}"
        )

        # Telegramga ODDIY MATN sifatida yuboramiz (parse_mode yo'q)
        sent = False
        if userbot and getattr(userbot, "connected", False):
            try:
                await userbot.send_message("me", report)
                sent = True
            except Exception as e:
                logger.warning(f"userbot health send xato: {e}")

        if not sent and bot and owner_id:
            try:
                await bot.send_message(owner_id, report)  # parse_mode yo'q!
                sent = True
            except Exception as e:
                logger.warning(f"bot health send xato: {e}")

        logger.info(f"iOS Health hisobot yuborildi: {sent}")
        return {"status": "ok", "sent": sent, "metrics_received": len(lines)}

    except Exception as e:
        logger.error(f"iOS Health tahlil xatosi: {e}", exc_info=True)
        return JSONResponse({"status": "error", "reason": str(e)}, status_code=500)



@app.get("/ios-health/last")
async def get_last_health():
    """Oxirgi kelgan Health ma'lumotini qaytaradi (bot_data ichida)."""
    last = BOT_CONTEXT.get("last_health_data")
    if not last:
        return {"status": "empty", "message": "Hali iOS dan hech qanday ma'lumot kelmagan."}
    return {"status": "ok", "data": last}


# ─── iOS Calendar Integratsiyasi ─────────────────────────────

class CalendarEvent(BaseModel):
    """iOS Kalendar voqeasi."""
    title: str
    start: str                        # ISO format: "2026-04-26T10:00:00"
    end: Optional[str] = None         # ISO format
    location: Optional[str] = None
    notes: Optional[str] = None
    calendar: Optional[str] = None    # Taqvim nomi (masalan: "Ishlar", "Shaxsiy")
    all_day: Optional[bool] = False

class CalendarSyncPayload(BaseModel):
    """iOS dan keluvchi voqealar ro'yxati."""
    events: list[CalendarEvent]
    range_start: Optional[str] = None  # Qaysi kundan
    range_end: Optional[str] = None    # Qaysi kungacha


@app.post("/ios-calendar/sync")
async def ios_calendar_sync(payload: CalendarSyncPayload):
    """
    iOS Shortcuts → Bu endpoint: iPhone taqvimidagi voqealarni Jasminaga yuboradi.
    Jasmina tahlil qilib kunlik reja yoki eslatmalar beradi.
    """
    from fastapi.responses import JSONResponse

    ai       = BOT_CONTEXT.get("ai")
    executor = BOT_CONTEXT.get("execute_tool")
    userbot  = BOT_CONTEXT.get("userbot")
    bot      = BOT_CONTEXT.get("bot")
    owner_id = BOT_CONTEXT.get("owner_id")

    if not ai:
        return JSONResponse({"status": "error", "reason": "AI tayyor emas"}, status_code=503)

    events = payload.events
    if not events:
        return JSONResponse({"status": "error", "reason": "Voqealar ro'yxati bo'sh"}, status_code=400)

    # Voqealarni matn ko'rinishiga o'tkazamiz
    lines = []
    for ev in events:
        start = ev.start[:16].replace("T", " ") if ev.start else "?"
        end   = ev.end[:16].replace("T", " ")   if ev.end   else ""
        loc   = f" | 📍 {ev.location}" if ev.location else ""
        cal   = f" [{ev.calendar}]"   if ev.calendar  else ""
        note  = f"\n   📝 {ev.notes}" if ev.notes      else ""
        time_str = f"{start}" + (f" – {end[11:]}" if end else "")
        lines.append(f"• {time_str}{cal} — {ev.title}{loc}{note}")

    events_text = "\n".join(lines)
    date_range = ""
    if payload.range_start:
        date_range = f"{payload.range_start}"
        if payload.range_end and payload.range_end != payload.range_start:
            date_range += f" – {payload.range_end}"

    logger.info(f"📅 iOS Calendar sync: {len(events)} voqea ({date_range})")

    prompt = (
        f"Xo'jayin Isroiljonning iOS taqvimidan {date_range or 'bugungi'} voqealar keldi:\n\n"
        f"{events_text}\n\n"
        "Ushbu jadval asosida:\n"
        "1. Eng muhim va shoshilinch voqealarni ajrat\n"
        "2. Vaqt to'qnashuvlari (conflict) bormi tekshir\n"
        "3. Har bir voqea uchun qisqa tayyorgarlik maslahatini ber\n"
        "4. Bugungi kun rejasini energiya va muhimlik bo'yicha tartiblash\n"
        "Javob qisqa, aniq, o'zbek tilida. Emoji bilan chiroyli formatlash."
    )

    try:
        sys_prompt = await _get_sys_prompt("taqvim voqealar")
        response = await ai.process_message(prompt, sys_prompt, executor)
        report = (
            f"📅 *iOS Taqvim Hisoboti*"
            + (f" — {date_range}" if date_range else "") +
            f"\n\n{events_text}\n\n"
            f"---\n"
            f"🤖 *Jasmina Tahlili:*\n{response}"
        )

        sent = False
        if userbot and getattr(userbot, "connected", False):
            try:
                await userbot.send_message("me", report)
                sent = True
            except Exception as e:
                logger.warning(f"userbot calendar send xato: {e}")

        if not sent and bot and owner_id:
            try:
                safe = report.replace("**", "*")
                await bot.send_message(owner_id, safe, parse_mode="Markdown")
                sent = True
            except Exception as e:
                logger.warning(f"bot calendar send xato: {e}")

        return {"status": "ok", "sent": sent, "events_received": len(events)}

    except Exception as e:
        logger.error(f"iOS Calendar sync xatosi: {e}", exc_info=True)
        return JSONResponse({"status": "error", "reason": str(e)}, status_code=500)


@app.get("/ios-calendar/pending")
async def ios_calendar_pending():
    """
    iOS Shortcuts shu endpointni polling qiladi.
    Bot 'Voqea qo'sh' desa — bu yerdan olib iOS Calendar ga qo'shadi.
    """
    cmds = [c for c in list(COMMAND_QUEUE) if c.get("type") == "calendar_add"]
    # Faqat calendar_add larni olamiz va qolganlarini qaytarib qo'yamiz
    other = [c for c in list(COMMAND_QUEUE) if c.get("type") != "calendar_add"]
    COMMAND_QUEUE.clear()
    for c in other:
        COMMAND_QUEUE.append(c)

    return {"events_to_add": cmds}


# ─── iOS Reminders ────────────────────────────────────────────

async def _send_to_telegram(report: str):
    """Yordamchi: xabarni Telegramga yuboradi."""
    userbot  = BOT_CONTEXT.get("userbot")
    bot      = BOT_CONTEXT.get("bot")
    owner_id = BOT_CONTEXT.get("owner_id")

    sent = False
    if userbot and getattr(userbot, "connected", False):
        try:
            await userbot.send_message("me", report)
            return True
        except Exception as e:
            logger.warning(f"userbot send xato: {e}")

    if bot and owner_id:
        try:
            safe = report.replace("**", "*")
            await bot.send_message(owner_id, safe, parse_mode="Markdown")
            return True
        except Exception as e:
            logger.warning(f"bot send xato: {e}")
    return False


@app.post("/ios-reminders/sync")
async def ios_reminders_sync(payload: RemindersPayload):
    """
    iOS Reminders dan kelgan eslatmalarni qabul qiladi.
    Jasmina muhimlarini ajratib Telegramga yuboradi.
    """
    from fastapi.responses import JSONResponse
    ai       = BOT_CONTEXT.get("ai")
    executor = BOT_CONTEXT.get("execute_tool")
    if not ai:
        return JSONResponse({"status": "error", "reason": "AI tayyor emas"}, status_code=503)

    reminders = [r for r in payload.reminders if not r.completed]
    if not reminders:
        return {"status": "ok", "message": "Bajarilmagan eslatmalar yo'q"}

    pri_map = {0: "", 1: "🟢", 5: "🟡", 9: "🔴"}
    lines = []
    for r in reminders:
        due   = f" ⏰ {r.due_date[:16].replace('T',' ')}" if r.due_date else ""
        lst   = f" [{r.list_name}]" if r.list_name else ""
        pri   = pri_map.get(r.priority or 0, "")
        note  = f"\n   💬 {r.notes}" if r.notes else ""
        lines.append(f"{pri}• {r.title}{due}{lst}{note}")

    reminders_text = "\n".join(lines)
    logger.info(f"🔔 iOS Reminders sync: {len(reminders)} ta bajarilmagan")

    prompt = (
        f"Xo'jayin Isroiljonning iOS Reminders eslatmalari ({len(reminders)} ta):\n\n"
        f"{reminders_text}\n\n"
        "Tahlil qil:\n"
        "1. Bugun bajarish kerak bo'lganlarni ajrat (🔴 qizil)\n"
        "2. Kechikkan (muddati o'tgan) eslatmalarni belgilab, ogohlantir!\n"
        "3. Yuqori prioritetli eslatmalar uchun konkret harakat tavsiya et\n"
        "4. Yaqin 2 kun uchun reja tuz\n"
        "O'zbek tilida, qisqa va aniq."
    )

    try:
        sys_prompt = await _get_sys_prompt("eslatmalar")
        response   = await ai.process_message(prompt, sys_prompt, executor)
        report = (
            f"🔔 *iOS Reminders Hisoboti*\n\n"
            f"{reminders_text}\n\n---\n"
            f"🤖 *Jasmina:*\n{response}"
        )
        sent = await _send_to_telegram(report)
        return {"status": "ok", "sent": sent, "reminders_count": len(reminders)}
    except Exception as e:
        logger.error(f"Reminders sync xatosi: {e}", exc_info=True)
        return JSONResponse({"status": "error", "reason": str(e)}, status_code=500)


@app.get("/ios-reminders/pending")
async def ios_reminders_pending():
    """iOS Shortcuts polling — bot qo'shgan eslatmalarni olish."""
    cmds  = [c for c in list(COMMAND_QUEUE) if c.get("type") == "reminder_add"]
    other = [c for c in list(COMMAND_QUEUE) if c.get("type") != "reminder_add"]
    COMMAND_QUEUE.clear()
    for c in other:
        COMMAND_QUEUE.append(c)
    return {"reminders_to_add": cmds}


# ─── iOS Screen Time ──────────────────────────────────────────

@app.post("/ios-screentime")
async def ios_screentime(payload: ScreenTimePayload):
    """iOS Screen Time kunlik hisobotini qabul qiladi."""
    from fastapi.responses import JSONResponse
    ai       = BOT_CONTEXT.get("ai")
    executor = BOT_CONTEXT.get("execute_tool")
    if not ai:
        return JSONResponse({"status": "error", "reason": "AI tayyor emas"}, status_code=503)

    apps = sorted(payload.apps, key=lambda x: x.minutes, reverse=True)
    lines = []
    for a in apps[:10]:  # Top 10 ta
        h, m = divmod(int(a.minutes), 60)
        time_str = f"{h}s {m}d" if h else f"{m}d"
        cat = f" ({a.category})" if a.category else ""
        lines.append(f"• {a.app_name}{cat}: {time_str}")

    total_h, total_m = divmod(int(payload.total_minutes or sum(a.minutes for a in payload.apps)), 60)
    summary_lines = [f"📱 Umumiy: {total_h}s {total_m}d"]
    if payload.pickups:     summary_lines.append(f"🤲 Qo'lga olish: {payload.pickups} marta")
    if payload.notifications: summary_lines.append(f"🔔 Bildirishnomalar: {payload.notifications} ta")

    date_str = payload.date or datetime.now().strftime("%Y-%m-%d")
    apps_text = "\n".join(lines)
    summary_text = " | ".join(summary_lines)

    # Ma'lumotlarni saqlaymiz — life_coach_job uchun
    BOT_CONTEXT["last_screentime"] = {
        "date": date_str,
        "total_minutes": payload.total_minutes or sum(a.minutes for a in apps),
        "pickups": payload.pickups,
        "top_apps": [{"name": a.app_name, "minutes": a.minutes, "category": a.category} for a in apps[:5]],
        "summary": summary_text,
    }

    logger.info(f"📊 iOS Screen Time: {len(apps)} ilova ({date_str})")

    prompt = (
        f"Xo'jayin Isroiljonning {date_str} kungi iPhone ishlatish statistikasi:\n\n"
        f"{summary_text}\n\nTop ilovalar:\n{apps_text}\n\n"
        "Raqamli hayot tahlili:\n"
        "1. Eng ko'p vaqt ketgan ilovalarni baholab, bu yaxshimi yoki yomonmi?\n"
        "2. Ijtimoiy tarmoqlar, o'yinlarga sarflangan vaqt ko'pmi?\n"
        "3. Produktivlik vs dam olish nisbati qanday?\n"
        "4. Ertangi kun uchun aniq maqsad (masalan: '2 soatdan kam Instagram')\n"
        "O'zbek tilida, motivatsion, qisqa."
    )

    try:
        sys_prompt = await _get_sys_prompt("screen time")
        response   = await ai.process_message(prompt, sys_prompt, executor)
        report = (
            f"📊 *Screen Time Hisoboti — {date_str}*\n\n"
            f"{summary_text}\n\n*Top Ilovalar:*\n{apps_text}\n\n---\n"
            f"🤖 *Jasmina:*\n{response}"
        )
        sent = await _send_to_telegram(report)
        return {"status": "ok", "sent": sent, "apps_count": len(apps)}
    except Exception as e:
        logger.error(f"Screen Time xatosi: {e}", exc_info=True)
        return JSONResponse({"status": "error", "reason": str(e)}, status_code=500)


# ─── iOS Music ────────────────────────────────────────────────

@app.post("/ios-music")
async def ios_music(data: MusicData):
    """Hozirgi ijro etilayotgan qo'shiq ma'lumotini qabul qiladi."""
    from fastapi.responses import JSONResponse
    ai       = BOT_CONTEXT.get("ai")
    executor = BOT_CONTEXT.get("execute_tool")
    if not ai:
        return JSONResponse({"status": "error", "reason": "AI tayyor emas"}, status_code=503)

    if not data.title and not data.artist:
        return JSONResponse({"status": "error", "reason": "Qo'shiq ma'lumoti yo'q"}, status_code=400)

    status = "▶️ Ijro etilmoqda" if data.is_playing else "⏸ Pauza"
    lines  = [f"{status}: **{data.title or '?'}**"]
    if data.artist:   lines.append(f"🎤 Ijrochi: {data.artist}")
    if data.album:    lines.append(f"💿 Album: {data.album}")
    if data.playlist: lines.append(f"📃 Playlist: {data.playlist}")
    if data.duration_seconds:
        m, s = divmod(data.duration_seconds, 60)
        lines.append(f"⏱ Davomiyligi: {m}:{s:02d}")

    music_text = "\n".join(lines)
    BOT_CONTEXT["current_music"] = data.dict()
    logger.info(f"🎵 iOS Music: {data.title} — {data.artist}")

    prompt = (
        f"Xo'jayin hozir shu qo'shiqni tinglayapti:\n{music_text}\n\n"
        "Unga yoqqan bu qo'shiq janri va kayfiyatiga qarab:\n"
        "1. Shu kayfiyatga mos 2-3 qo'shiq tavsiya qil (aniq nom va ijrochi)\n"
        "2. Bu qo'shiq/ijrochi haqida qiziqarli 1 fakt\n"
        "Javob juda qisqa va do'stona bo'lsin."
    )

    try:
        sys_prompt = await _get_sys_prompt("musiqa")
        response   = await ai.process_message(prompt, sys_prompt, executor)
        report = f"🎵 *Musiqa*\n\n{music_text}\n\n---\n🤖 *Jasmina:*\n{response}"
        sent = await _send_to_telegram(report)
        return {"status": "ok", "sent": sent}
    except Exception as e:
        logger.error(f"Music endpoint xatosi: {e}", exc_info=True)
        return JSONResponse({"status": "error", "reason": str(e)}, status_code=500)

@app.get("/ios-music/current")
async def get_current_music():
    """Hozir ijro etilayotgan qo'shiqni qaytaradi."""
    music = BOT_CONTEXT.get("current_music")
    if not music:
        return {"status": "empty", "message": "Hozir musiqa yo'q"}
    return {"status": "ok", "music": music}


# ─── iOS Messages ─────────────────────────────────────────────

@app.post("/ios-messages")
async def ios_messages(data: MessagesData):
    """iOS Messages o'qilmagan xabarlar hisobotini qabul qiladi."""
    from fastapi.responses import JSONResponse
    if data.unread_count is None:
        return JSONResponse({"status": "error", "reason": "unread_count yo'q"}, status_code=400)

    if data.unread_count == 0:
        logger.info("📬 iOS Messages: o'qilmagan xabar yo'q")
        return {"status": "ok", "message": "O'qilmagan SMS yo'q"}

    date_str = data.date or datetime.now().strftime("%Y-%m-%d")
    conv_str = f", {data.conversations} ta suhbatda" if data.conversations else ""
    msg_text = f"📬 O'qilmagan SMS: {data.unread_count} ta{conv_str}"

    logger.info(f"📬 iOS Messages: {data.unread_count} o'qilmagan ({date_str})")

    # Faqat 5 dan ko'p bo'lsa Jasminaga bildirish
    if data.unread_count < 5:
        return {"status": "ok", "notified": False, "reason": "5 dan kam, bildirish shart emas"}

    report = (
        f"📬 *iOS Messages*\n\n"
        f"{msg_text}\n\n"
        f"⚠️ Xo'jayin, {data.unread_count} ta o'qilmagan SMS bor! "
        f"Muhim xabar bo'lishi mumkin — tekshirib ko'ring."
    )
    sent = await _send_to_telegram(report)
    return {"status": "ok", "sent": sent, "unread": data.unread_count}
