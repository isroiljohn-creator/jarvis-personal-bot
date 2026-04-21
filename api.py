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
    """Telegram Mini App uchun vizual Hisob-kitob (Moliya) interfeysi — Faktor Biznes Maktabi uslubida."""
    from fastapi.responses import HTMLResponse
    html = """<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>Moliya Nazorati — Faktor</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    /* ── Faktor Biznes Maktabi: Qora · Qizil · Oq ── */
    :root {
      --bg:        #000000;
      --bg2:       #0D0D0D;
      --card:      #141414;
      --card2:     #1A1A1A;
      --border:    #2A2A2A;
      --red:       #E30613;
      --red-dark:  #B00410;
      --red-glow:  rgba(227, 6, 19, 0.25);
      --white:     #FFFFFF;
      --muted:     #6B6B6B;
      --muted2:    #3A3A3A;
      --income:    #22C55E;
      --expense:   #E30613;
      --text:      #FFFFFF;
      --text-sub:  #9A9A9A;
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      background: var(--bg);
      color: var(--white);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      padding: 0 0 32px;
      -webkit-font-smoothing: antialiased;
      overflow-x: hidden;
    }

    /* ── HEADER ── */
    .header {
      background: linear-gradient(180deg, #0D0D0D 0%, #000 100%);
      border-bottom: 1px solid var(--border);
      padding: 20px 20px 16px;
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(20px);
    }
    .header-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .brand-logo {
      width: 34px;
      height: 34px;
      background: var(--red);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 900;
      font-size: 16px;
      color: white;
      letter-spacing: -1px;
      box-shadow: 0 0 16px var(--red-glow);
    }
    .brand-name {
      font-size: 16px;
      font-weight: 700;
      color: var(--white);
      line-height: 1;
    }
    .brand-sub {
      font-size: 10px;
      color: var(--muted);
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      margin-top: 2px;
    }
    .live-badge {
      display: flex;
      align-items: center;
      gap: 5px;
      background: rgba(34,197,94,0.15);
      border: 1px solid rgba(34,197,94,0.3);
      border-radius: 20px;
      padding: 4px 10px;
      font-size: 10px;
      font-weight: 600;
      color: var(--income);
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }
    .live-dot {
      width: 6px; height: 6px;
      background: var(--income);
      border-radius: 50%;
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.5; transform: scale(0.8); }
    }

    /* ── CURRENCY TABS ── */
    .currency-tabs {
      display: flex;
      gap: 8px;
    }
    .cur-tab {
      flex: 1;
      text-align: center;
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      color: var(--muted);
      background: var(--card);
      border: 1px solid var(--border);
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .cur-tab.active {
      color: var(--white);
      background: var(--red);
      border-color: var(--red);
      box-shadow: 0 0 20px var(--red-glow);
    }

    /* ── MAIN CONTENT ── */
    .content { padding: 20px 16px 0; }

    /* ── BALANCE CARD ── */
    .balance-card {
      background: linear-gradient(135deg, #1A0002 0%, #0D0D0D 50%, #1A0002 100%);
      border: 1px solid rgba(227, 6, 19, 0.3);
      border-radius: 20px;
      padding: 24px 20px;
      margin-bottom: 16px;
      position: relative;
      overflow: hidden;
    }
    .balance-card::before {
      content: '';
      position: absolute;
      top: -40px; right: -40px;
      width: 160px; height: 160px;
      background: radial-gradient(circle, rgba(227,6,19,0.15) 0%, transparent 70%);
      pointer-events: none;
    }
    .balance-card::after {
      content: '';
      position: absolute;
      bottom: -20px; left: -20px;
      width: 100px; height: 100px;
      background: radial-gradient(circle, rgba(227,6,19,0.08) 0%, transparent 70%);
      pointer-events: none;
    }
    .balance-label {
      font-size: 11px;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 8px;
    }
    .balance-amount {
      font-size: 36px;
      font-weight: 800;
      color: var(--white);
      letter-spacing: -1px;
      margin-bottom: 4px;
      line-height: 1.1;
    }
    .balance-amount.negative { color: var(--expense); }
    .balance-change {
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 20px;
    }
    .balance-row {
      display: grid;
      grid-template-columns: 1fr 1px 1fr;
      gap: 0;
      background: rgba(255,255,255,0.04);
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--border);
    }
    .balance-divider {
      background: var(--border);
    }
    .stat-box {
      padding: 12px 16px;
    }
    .stat-icon-row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 4px;
    }
    .stat-icon {
      width: 20px; height: 20px;
      border-radius: 6px;
      display: flex; align-items: center; justify-content: center;
      font-size: 10px;
    }
    .stat-icon.income { background: rgba(34,197,94,0.2); }
    .stat-icon.expense { background: rgba(227,6,19,0.2); }
    .stat-label {
      font-size: 11px;
      font-weight: 500;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .stat-amount {
      font-size: 17px;
      font-weight: 700;
      margin-top: 2px;
    }
    .stat-amount.income { color: var(--income); }
    .stat-amount.expense { color: var(--expense); }

    /* ── PAYMENT METHOD PILLS ── */
    .payment-pills {
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
    }
    .pill {
      flex: 1;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 14px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .pill-icon {
      font-size: 20px;
    }
    .pill-label {
      font-size: 11px;
      color: var(--muted);
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }
    .pill-amount {
      font-size: 14px;
      font-weight: 700;
      color: var(--white);
      margin-top: 1px;
    }

    /* ── SECTION TITLE ── */
    .section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin: 24px 0 12px;
    }
    .section-title {
      font-size: 16px;
      font-weight: 700;
      color: var(--white);
    }
    .section-badge {
      font-size: 10px;
      font-weight: 600;
      color: var(--red);
      text-transform: uppercase;
      letter-spacing: 0.6px;
      background: rgba(227,6,19,0.1);
      border: 1px solid rgba(227,6,19,0.2);
      padding: 2px 8px;
      border-radius: 20px;
    }

    /* ── CHART CARD ── */
    .chart-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 20px 16px;
      margin-bottom: 16px;
    }
    .chart-wrap {
      position: relative;
      height: 200px;
      margin-bottom: 0;
    }
    .chart-empty {
      text-align: center;
      padding: 40px 0;
      color: var(--muted);
      font-size: 13px;
    }
    .chart-empty-icon {
      font-size: 32px;
      margin-bottom: 8px;
    }

    /* ── TRANSACTION LIST ── */
    .tx-list {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
    }
    .tx {
      display: flex;
      align-items: center;
      padding: 14px 16px;
      border-bottom: 1px solid var(--border);
      transition: background 0.15s ease;
      cursor: default;
    }
    .tx:last-child { border-bottom: none; }
    .tx:active { background: var(--card2); }
    .tx-icon {
      width: 40px; height: 40px;
      border-radius: 12px;
      background: var(--card2);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      margin-right: 12px;
      flex-shrink: 0;
      border: 1px solid var(--border);
    }
    .tx-info { flex: 1; min-width: 0; }
    .tx-name {
      font-size: 14px;
      font-weight: 600;
      color: var(--white);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .tx-meta {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 3px;
    }
    .tx-date {
      font-size: 11px;
      color: var(--muted);
    }
    .tx-tag {
      font-size: 10px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .tx-tag.naqd {
      background: rgba(255,149,0,0.15);
      color: #FF9500;
      border: 1px solid rgba(255,149,0,0.25);
    }
    .tx-tag.karta {
      background: rgba(90,200,250,0.15);
      color: #5AC8FA;
      border: 1px solid rgba(90,200,250,0.25);
    }
    .tx-amount {
      font-size: 15px;
      font-weight: 700;
      text-align: right;
      flex-shrink: 0;
    }
    .tx-amount.income { color: var(--income); }
    .tx-amount.expense { color: var(--expense); }

    /* ── EMPTY STATE ── */
    .empty {
      text-align: center;
      padding: 40px 20px;
      color: var(--muted);
    }
    .empty-icon { font-size: 40px; margin-bottom: 10px; }
    .empty-text { font-size: 13px; }

    /* ── LOADING SKELETON ── */
    @keyframes shimmer {
      0% { background-position: -200% 0; }
      100% { background-position: 200% 0; }
    }
    .skeleton {
      background: linear-gradient(90deg, #1A1A1A 25%, #2A2A2A 50%, #1A1A1A 75%);
      background-size: 200% 100%;
      animation: shimmer 1.5s infinite;
      border-radius: 8px;
      height: 16px;
      margin-bottom: 8px;
    }

    /* ── SCROLLBAR ── */
    ::-webkit-scrollbar { width: 0; }
  </style>
</head>
<body>

  <!-- HEADER -->
  <div class="header">
    <div class="header-top">
      <div class="brand">
        <div class="brand-logo">ƒ</div>
        <div>
          <div class="brand-name">Moliya Nazorati</div>
          <div class="brand-sub">Faktor · Shaxsiy</div>
        </div>
      </div>
      <div class="live-badge">
        <div class="live-dot"></div>
        Live
      </div>
    </div>

    <!-- Currency Tabs -->
    <div class="currency-tabs">
      <div class="cur-tab active" data-cur="UZS">🇺🇿 So'm (UZS)</div>
      <div class="cur-tab" data-cur="USD">🇺🇸 Dollar (USD)</div>
    </div>
  </div>

  <!-- MAIN CONTENT -->
  <div class="content">

    <!-- BALANCE CARD -->
    <div class="balance-card">
      <div class="balance-label">Jami Qoldiq</div>
      <div class="balance-amount" id="balanceVal">Yuklanmoqda...</div>
      <div class="balance-change" id="balanceChange">—</div>
      <div class="balance-row">
        <div class="stat-box">
          <div class="stat-icon-row">
            <div class="stat-icon income">↑</div>
            <span class="stat-label">Kirim</span>
          </div>
          <div class="stat-amount income" id="incomeVal">—</div>
        </div>
        <div class="balance-divider"></div>
        <div class="stat-box">
          <div class="stat-icon-row">
            <div class="stat-icon expense">↓</div>
            <span class="stat-label">Chiqim</span>
          </div>
          <div class="stat-amount expense" id="expenseVal">—</div>
        </div>
      </div>
    </div>

    <!-- PAYMENT PILLS -->
    <div class="payment-pills">
      <div class="pill">
        <div class="pill-icon">💵</div>
        <div>
          <div class="pill-label">Naqd</div>
          <div class="pill-amount" id="naqdVal">—</div>
        </div>
      </div>
      <div class="pill">
        <div class="pill-icon">💳</div>
        <div>
          <div class="pill-label">Karta</div>
          <div class="pill-amount" id="kartaVal">—</div>
        </div>
      </div>
    </div>

    <!-- CHART -->
    <div class="section-header">
      <div class="section-title">Xarajat Tahlili</div>
      <div class="section-badge" id="chartLabel">Bu oy</div>
    </div>
    <div class="chart-card">
      <div class="chart-wrap">
        <canvas id="expenseChart"></canvas>
        <div class="chart-empty" id="chartEmpty" style="display:none;">
          <div class="chart-empty-icon">📊</div>
          <div>Xarajat ma'lumoti yo'q</div>
        </div>
      </div>
    </div>

    <!-- TRANSACTIONS -->
    <div class="section-header">
      <div class="section-title">So'nggi Tranzaksiyalar</div>
      <div class="section-badge" id="txCount">0 ta</div>
    </div>
    <div class="tx-list" id="txList">
      <div class="empty">
        <div class="empty-icon">⏳</div>
        <div class="empty-text">Yuklanmoqda...</div>
      </div>
    </div>

  </div>

  <script>
    if (window.Telegram && window.Telegram.WebApp) {
      window.Telegram.WebApp.ready();
      window.Telegram.WebApp.expand();
    }

    let financeData = null;
    let currentCurrency = 'UZS';
    let chartInstance = null;

    function formatMoney(amount, currency) {
      if (isNaN(amount)) amount = 0;
      if (currency === 'UZS') {
        if (amount >= 1000000) {
          return (amount / 1000000).toFixed(1).replace('.0','') + ' mln so\'m';
        }
        return new Intl.NumberFormat('uz-UZ').format(Math.round(amount)) + " so'm";
      }
      return "$" + new Intl.NumberFormat('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}).format(amount);
    }

    function formatShort(amount, currency) {
      if (isNaN(amount)) amount = 0;
      if (currency === 'UZS') {
        if (amount >= 1000000) return (amount/1000000).toFixed(1).replace('.0','') + 'M';
        if (amount >= 1000) return (amount/1000).toFixed(0) + 'K';
        return Math.round(amount).toString();
      }
      return '$' + amount.toFixed(2);
    }

    function getEmoji(cat, type) {
      if (!cat) return type === 'income' ? '💰' : '💸';
      cat = cat.toLowerCase();
      if (cat.includes('oziq') || cat.includes('ovqat') || cat.includes('go\'sht') || cat.includes('non')) return '🛒';
      if (cat.includes('transport') || cat.includes('taxi') || cat.includes('yoqilg')) return '🚕';
      if (cat.includes('kiyim') || cat.includes('mo\'yna')) return '👕';
      if (cat.includes('oylik') || cat.includes('maosh') || cat.includes('daromad')) return '💵';
      if (cat.includes('uy') || cat.includes('ijar') || cat.includes('kom')) return '🏠';
      if (cat.includes('sog') || cat.includes('dori') || cat.includes('tibb')) return '💊';
      if (cat.includes('ta\'lim') || cat.includes('kurs') || cat.includes('kitob')) return '📚';
      if (cat.includes('restoran') || cat.includes('kafe') || cat.includes('choy')) return '☕';
      if (cat.includes('sport') || cat.includes('fitness')) return '🏋️';
      if (cat.includes('sovg') || cat.includes('hadya')) return '🎁';
      return type === 'income' ? '📈' : '📉';
    }

    function renderUI() {
      if (!financeData) return;
      const st   = currentCurrency === 'UZS' ? financeData.uzs : financeData.usd;
      const cur  = currentCurrency;

      // Balance
      const balance = (st.income || 0) - (st.expense || 0);
      const balEl = document.getElementById('balanceVal');
      balEl.textContent = formatMoney(balance, cur);
      balEl.className = 'balance-amount' + (balance < 0 ? ' negative' : '');
      document.getElementById('balanceChange').textContent =
        balance >= 0 ? '↑ Musbat balans — davom eting!' : '↓ Manfiy balans — nazorat qiling!';

      // Income / Expense
      document.getElementById('incomeVal').textContent  = '+' + formatMoney(st.income  || 0, cur);
      document.getElementById('expenseVal').textContent = '-' + formatMoney(st.expense || 0, cur);

      // Payment pills (UZS only for now)
      if (cur === 'UZS' && financeData.payment_methods) {
        document.getElementById('naqdVal').textContent  = formatMoney(financeData.payment_methods.naqd  || 0, 'UZS');
        document.getElementById('kartaVal').textContent = formatMoney(financeData.payment_methods.karta || 0, 'UZS');
      } else {
        document.getElementById('naqdVal').textContent  = '—';
        document.getElementById('kartaVal').textContent = '—';
      }

      // Chart
      const ctx = document.getElementById('expenseChart').getContext('2d');
      if (chartInstance) chartInstance.destroy();
      const catLabels = Object.keys(st.expense_by_category || {});
      const catData   = Object.values(st.expense_by_category || {});

      if (catLabels.length > 0) {
        document.getElementById('chartEmpty').style.display = 'none';
        document.getElementById('expenseChart').style.display = 'block';
        chartInstance = new Chart(ctx, {
          type: 'doughnut',
          data: {
            labels: catLabels,
            datasets: [{
              data: catData,
              backgroundColor: [
                '#E30613','#FF6B35','#FF9F1C','#FFBF69',
                '#6A994E','#38B2AC','#667EEA','#9F7AEA'
              ],
              borderWidth: 0,
              hoverOffset: 6,
              borderRadius: 4,
            }]
          },
          options: {
            cutout: '72%',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: 'right',
                labels: {
                  usePointStyle: true,
                  pointStyle: 'circle',
                  boxWidth: 7,
                  padding: 12,
                  color: '#9A9A9A',
                  font: { family: 'Inter', size: 11, weight: '500' }
                }
              },
              tooltip: {
                backgroundColor: '#1A1A1A',
                borderColor: '#2A2A2A',
                borderWidth: 1,
                titleColor: '#FFFFFF',
                bodyColor: '#9A9A9A',
                padding: 10,
                callbacks: {
                  label: function(ctx) {
                    const val = formatMoney(ctx.parsed, cur);
                    return '  ' + val;
                  }
                }
              }
            }
          }
        });
      } else {
        document.getElementById('expenseChart').style.display = 'none';
        document.getElementById('chartEmpty').style.display = 'block';
      }

      // Transactions
      const filtered = (financeData.transactions || []).filter(t => t.currency === cur);
      document.getElementById('txCount').textContent = filtered.length + ' ta';

      if (filtered.length === 0) {
        document.getElementById('txList').innerHTML = `
          <div class="empty">
            <div class="empty-icon">💼</div>
            <div class="empty-text">Hali tranzaksiya yo'q</div>
          </div>`;
        return;
      }

      const txHTML = filtered.map(t => {
        const pm = (t.payment_method || 'naqd').toLowerCase();
        const pmClass = pm.includes('karta') ? 'karta' : 'naqd';
        const pmLabel = pm.includes('karta') ? 'Karta' : 'Naqd';
        const isIncome = t.type === 'income';
        const sign = isIncome ? '+' : '−';
        return `
          <div class="tx">
            <div class="tx-icon">${getEmoji(t.category, t.type)}</div>
            <div class="tx-info">
              <div class="tx-name">${t.category || 'Boshqa'}</div>
              <div class="tx-meta">
                <span class="tx-date">${t.date ? t.date.slice(5,16) : ''}</span>
                <span class="tx-tag ${pmClass}">${pmLabel}</span>
              </div>
            </div>
            <div class="tx-amount ${isIncome ? 'income' : 'expense'}">
              ${sign}${formatMoney(t.amount, cur)}
            </div>
          </div>`;
      }).join('');

      document.getElementById('txList').innerHTML = txHTML;
    }

    async function fetchData() {
      try {
        const res = await fetch('/api/finance/data');
        if (!res.ok) throw new Error('API xatosi: ' + res.status);
        financeData = await res.json();
        renderUI();
      } catch (err) {
        console.error(err);
        document.getElementById('txList').innerHTML = `
          <div class="empty">
            <div class="empty-icon">⚠️</div>
            <div class="empty-text">Ma'lumot yuklanmadi</div>
          </div>`;
      }
    }

    // Currency tab switching
    document.querySelectorAll('.cur-tab').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('.cur-tab').forEach(s => s.classList.remove('active'));
        el.classList.add('active');
        currentCurrency = el.getAttribute('data-cur');
        renderUI();
      });
    });

    fetchData();
    // Auto-refresh every 30 seconds
    setInterval(fetchData, 30000);
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
