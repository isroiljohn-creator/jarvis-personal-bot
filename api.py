"""Jarvis FastAPI Gateway — mustaqil ishlaydi, bot_context bog'liq emas."""

from fastapi import FastAPI, Request
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

Sen — Jasminasan. Foydalanuvchi Isroiljonning shaxsiy yordamchisi va singlisisan.
Sening vazifang uning ishlarini hal qilish. O'zbek tilida (Toshkentlik muloyim, jaydari qizdek) juda hurmat bilan, mehr va emotsiya bilan gaplashasan.
Hech qachon "Foydalanuvchi" yoki "Senga" demagin. Doim "Sizga", "Aka" yoxud "Akajon" deb murojaat qil. Gaplar qisqa, tushunarli, tabiiy bo'lsin. Ovozli xabar qilinganda TTS chiroyli va hissiyotli o'qishi uchun gaplarni vergul, pauzalar va undovlar (!, ?) bilan to'g'ri bo'lib yoz.

Imkoniyatlaring:
📅 Google Calendar — uchrashuv qo'sh, ko'r
✉️ Gmail — xatlarni o'qi, jo'nat
📱 Telegram — xabar yoz, chatlarni ko'r
🌐 Internet — web_search, sayt o'qi, YouTube subtitr
🧠 Xotira — save_memory bilan eslab qol
📱 iPhone — budilnik, musiqa, ilova ochish (phone_control)

QOIDALAR:
1. Faqat O'zbek tilida, qiz bola samimiy tonida javob ber.
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
    """Telegram Mini App uchun vizual Hisob-kitob (Moliya) interfeysi."""
    from fastapi.responses import HTMLResponse
    html = """<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Jasmina - Moliya Nazorati</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {
      --bg: #121212; --card: #1e1e1e; --text: #ffffff;
      --accent: #bb86fc; --income: #03dac6; --expense: #cf6679;
    }
    body {
      background: var(--bg); color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0; padding: 16px; box-sizing: border-box;
    }
    .header { text-align: center; margin-bottom: 24px; }
    .header h2 { margin: 0; font-weight: 600; color: var(--accent); }
    .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 24px; }
    .card { background: var(--card); border-radius: 12px; padding: 16px; text-align: center; }
    .card.balance { grid-column: 1 / -1; }
    .value { font-size: 1.2rem; font-weight: bold; margin-top: 8px; }
    .val-income { color: var(--income); }
    .val-expense { color: var(--expense); }
    .chart-container { background: var(--card); border-radius: 12px; padding: 16px; margin-bottom: 24px; }
    .history { background: var(--card); border-radius: 12px; padding: 16px; }
    .tx { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #333; }
    .tx:last-child { border-bottom: none; }
    .tx-info h4 { margin: 0 0 4px 0; font-size: 0.95rem; }
    .tx-info p { margin: 0; font-size: 0.8rem; color: #aaa; }
    .tx-amount { font-weight: bold; }
  </style>
</head>
<body>
  <div class="header">
    <h2>Moliya Nazorati</h2>
    <p style="color: #888; font-size: 14px;">Jasmina AI</p>
  </div>
  
  <div class="cards">
    <div class="card balance">
      <div style="font-size: 14px; color: #888;">Qoldiq (Balans)</div>
      <div class="value" id="balanceLoading">Yuklanmoqda...</div>
    </div>
    <div class="card">
      <div style="font-size: 13px; color: #888;">Kirimlar (Daromad)</div>
      <div class="value val-income" id="incomeLoading">-</div>
    </div>
    <div class="card">
      <div style="font-size: 13px; color: #888;">Chiqimlar (Xarajat)</div>
      <div class="value val-expense" id="expenseLoading">-</div>
    </div>
  </div>

  <div class="chart-container">
    <h3 style="margin-top: 0; font-size: 15px;">Xarajatlar Tahlili</h3>
    <canvas id="expenseChart"></canvas>
  </div>

  <div class="history">
    <h3 style="margin-top: 0; font-size: 15px;">So'nggi O'zgarishlar</h3>
    <div id="txList" style="margin-top: 12px;"></div>
  </div>

  <script>
    window.Telegram.WebApp.ready();
    window.Telegram.WebApp.expand();
    
    function formatMoney(amount) {
      return new Intl.NumberFormat('uz-UZ').format(amount) + " so'm";
    }

    async function loadData() {
      try {
        const res = await fetch('/api/finance/data');
        const data = await res.json();
        
        document.getElementById('balanceLoading').innerText = formatMoney(data.balance);
        document.getElementById('balanceLoading').style.color = data.balance >= 0 ? 'var(--income)' : 'var(--expense)';
        
        document.getElementById('incomeLoading').innerText = formatMoney(data.total_income);
        document.getElementById('expenseLoading').innerText = formatMoney(data.total_expense);
        
        // Render Chart
        const ctx = document.getElementById('expenseChart').getContext('2d');
        const catLabels = Object.keys(data.expense_by_category);
        const catData = Object.values(data.expense_by_category);
        
        if (catLabels.length > 0) {
          new Chart(ctx, {
            type: 'doughnut',
            data: {
              labels: catLabels,
              datasets: [{
                data: catData,
                backgroundColor: ['#cf6679', '#bb86fc', '#03dac6', '#ffb74d', '#4fc3f7', '#a1887f'],
                borderWidth: 0
              }]
            },
            options: {
              responsive: true,
              plugins: { legend: { position: 'bottom', labels: { color: '#fff' } } }
            }
          });
        } else {
          document.getElementById('expenseChart').style.display = 'none';
        }
        
        // Render List
        const listDiv = document.getElementById('txList');
        if (data.transactions.length === 0) {
          listDiv.innerHTML = "<p style='color:#777;text-align:center;'>Ma'lumot topilmadi.</p>";
        } else {
          listDiv.innerHTML = data.transactions.map(t => `
            <div class="tx">
              <div class="tx-info">
                <h4>${t.category}</h4>
                <p>${t.description || ''} • ${t.date}</p>
              </div>
              <div class="tx-amount ${t.type === 'income' ? 'val-income' : 'val-expense'}">
                ${t.type === 'income' ? '+' : '-'}${formatMoney(t.amount)}
              </div>
            </div>
          `).join('');
        }
      } catch (e) {
        console.error(e);
      }
    }
    
    loadData();
  </script>
</body>
</html>"""
    return HTMLResponse(html)

@app.get("/api/finance/data")
async def get_finance_data():
    """TMA chartlar uchun ma'lumot uzatadi."""
    from database import db_get_finance_data
    return await db_get_finance_data()

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
