/**
 * AI FINANSIST — Full App
 * Backend API bilan ulangan real-time dashboard
 */

'use strict';

const API = '/api/finance';

// ─── STATE ───────────────────────────────
let State = {
  data: null,
  period: 'daily',
  currentPage: 'dashboard',
  currentReport: 'daily',
  charts: {},
  hasRealData: false,
  telegramToken: localStorage.getItem('tg_token') || '',
  telegramChatId: localStorage.getItem('tg_chat_id') || '',
};

// ─── FORMAT ──────────────────────────────
const fmt = (n) => {
  const abs = Math.abs(n || 0);
  if (abs >= 1_000_000_000) return (n / 1_000_000_000).toFixed(2) + ' mlrd';
  if (abs >= 1_000_000)     return (n / 1_000_000).toFixed(1)     + ' mln';
  if (abs >= 1_000)         return (n / 1_000).toFixed(0)         + ' ming';
  return (n || 0).toLocaleString('uz');
};
const fmtFull = (n) => `${Math.abs(n || 0).toLocaleString('uz-UZ')} so'm`;
const fmtSign = (n) => (n >= 0 ? '+' : '-') + fmtFull(Math.abs(n));

// ─── SVG ICONS ─────────────────────────
const SVGS = {
  check: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>`,
  x: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>`,
  info: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
  warn: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>`,
  trendUp: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg>`,
  money: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
  star: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/></svg>`,
  calendar: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>`,
  card: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/></svg>`,
  click: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"/></svg>`,
  uzum: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>`,
  bank: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8 14v3m4-3v3m4-3v3M3 21h18M3 10h18M3 7l9-4 9 4M4 10h16v11H4V10z"/></svg>`,
  cash: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z"/></svg>`,
  terminal: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>`,
  globe: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"/></svg>`,
  user: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>`,
  bot: `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h2v2H9V9zm4 0h2v2h-2V9z"/></svg>`,
  dotGreen: `<span style="display:inline-block;width:8px;height:8px;background:#10B981;border-radius:50%;margin-right:6px;"></span>`,
  dotYellow: `<span style="display:inline-block;width:8px;height:8px;background:#F59E0B;border-radius:50%;margin-right:6px;"></span>`,
  defaultSrc: `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>`
};

// ─── TOAST ───────────────────────────────
const toast = (type, title, msg = '', ms = 4000) => {
  const icons = { success: SVGS.check, error: SVGS.x, info: SVGS.info, warning: SVGS.warn };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type]}</span>
    <div class="toast-text"><strong>${title}</strong>${msg ? `<span>${msg}</span>` : ''}</div>`;
  document.getElementById('toastContainer').appendChild(el);
  setTimeout(() => { el.style.animation = 'toastIn .3s ease reverse'; setTimeout(() => el.remove(), 300); }, ms);
};

// ─── ANIMATE NUMBER ──────────────────────
const animNum = (id, to, formatter = fmtFull) => {
  const el = document.getElementById(id);
  if (!el) return;
  const start = performance.now();
  const dur = 900;
  (function tick(now) {
    const p = Math.min((now - start) / dur, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = formatter(Math.round(to * ease));
    if (p < 1) requestAnimationFrame(tick);
  })(start);
};

// ─── CHART DEFAULTS ──────────────────────
let CHART_OPTS = {};
const refreshChartOpts = () => {
  const style = getComputedStyle(document.documentElement);
  const textSec = style.getPropertyValue('--text-secondary').trim() || '#94A3B8';
  const textMuted = style.getPropertyValue('--text-muted').trim() || '#475569';
  const borderCol = style.getPropertyValue('--border-color').trim() || 'rgba(255,255,255,.04)';
  const textPri = style.getPropertyValue('--text-primary').trim() || '#F1F5F9';
  const bgGlass = style.getPropertyValue('--bg-glass').trim() || 'rgba(13,17,23,.96)';

  CHART_OPTS = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { color: textSec, font: { size: 12 }, boxWidth: 12, padding: 16 } },
      tooltip: {
        backgroundColor: bgGlass,
        borderColor: borderCol,
        borderWidth: 1,
        titleColor: textPri,
        bodyColor: textSec,
        padding: 12,
      }
    },
    scales: {
      x: { grid: { color: borderCol }, ticks: { color: textMuted, font: { size: 11 } } },
      y: { grid: { color: borderCol }, ticks: { color: textMuted, font: { size: 11 }, callback: v => fmt(v) } }
    }
  };
};

const destroyChart = (key) => {
  if (State.charts[key]) { State.charts[key].destroy(); delete State.charts[key]; }
};

// ─── API FETCH ───────────────────────────
const apiFetch = async (endpoint, opts = {}) => {
  try {
    const headers = opts.headers || {};
    if (window.Telegram?.WebApp?.initData) {
       headers['X-Telegram-Auth'] = window.Telegram.WebApp.initData;
    }

    const res = await fetch(API + endpoint, { ...opts, headers });
    
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    console.error('[API]', endpoint, e.message);
    return null;
  }
};

// ─── LOAD DATA ───────────────────────────
const loadData = async (force = false) => {
  document.getElementById('loadingOverlay').style.display = 'flex';
  const data = await apiFetch(`/data${force ? '?force=true' : ''}`);
  document.getElementById('loadingOverlay').style.display = 'none';

  if (!data) {
    toast('error', 'Server xato', 'Backend ishlamayapti. Sahifani yangilang.');
    return;
  }

  State.data = data;
  State.hasRealData = data.has_real_data;

  const badge = document.getElementById('dataBadge');
  if (badge) {
    badge.innerHTML = data.has_real_data ? `${SVGS.dotGreen} Real data` : `${SVGS.dotYellow} Demo`;
    badge.title = data.has_real_data
      ? 'Google Sheets dan real ma\'lumot'
      : 'Sheets bo\'sh — demo ma\'lumot ko\'rsatilmoqda';
  }

  const lastSync = document.getElementById('lastSyncTime');
  if (lastSync) {
    const d = new Date(data.last_updated);
    lastSync.textContent = d.toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' });
  }

  initDashboard();
};

// ─── DASHBOARD ───────────────────────────
const initDashboard = () => {
  const d = State.data;
  if (!d) return;
  const s = d.summary;

  // Data range computation
  const periodData = d[State.period] || d.daily || {};
  let labels = Object.keys(periodData);
  if (State.period === 'daily') labels = labels.slice(0, 30).reverse();
  else labels = labels.slice(-12);
  const incomeArr  = labels.map(k => periodData[k]?.income  || 0);
  const expenseArr = labels.map(k => periodData[k]?.expense || 0);
  const profitArr  = labels.map(k => periodData[k]?.profit  || 0);

  // KPI calculations based on active period selection (Last item = Current period)
  const pIncome = incomeArr.length ? incomeArr[incomeArr.length - 1] : 0;
  const pExpense = expenseArr.length ? expenseArr[expenseArr.length - 1] : 0;
  const pProfit = profitArr.length ? profitArr[profitArr.length - 1] : 0;
  
  // Dynamic card titles
  const pdTitles = { 'daily': 'BUGUN', 'weekly': 'SHU HAFTA', 'monthly': 'SHU OY' };
  const pSuffix = pdTitles[State.period] || '';
  
  const updateTitle = (id, base) => {
    const el = document.querySelector(`#${id} .kpi-label`);
    if (el) el.textContent = `${base} (${pSuffix})`;
  };
  updateTitle('kpi-income', 'JAMI TUSHUM');
  updateTitle('kpi-expense', 'JAMI CHIQIM');
  updateTitle('kpi-profit', 'SOF FOYDA');
  updateTitle('kpi-commission', 'KOMISSIYA XARAJAT');
  
  animNum('totalIncome',     pIncome,   v => fmt(v) + ' so\'m');
  animNum('totalExpense',    pExpense,  v => fmt(v) + ' so\'m');
  animNum('netProfit',       pProfit,   v => fmt(v) + ' so\'m');
  animNum('totalCommission', pExpense,  v => fmt(v) + ' so\'m'); // Expense equates to recorded commissions per daily log

  // Trends
  const setTrend = (id, pct, positive) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = `kpi-trend ${positive ? 'positive' : 'negative'}`;
    el.innerHTML = `<svg viewBox="0 0 16 16" fill="currentColor"><path d="${positive ? 'M8 3l5 5H3l5-5z' : 'M8 13L3 8h10l-5 5z'}"/></svg><span>${positive ? '+' : ''}${pct}% o'tgan davr</span>`;
  };
  setTrend('incomeTrend',     12.5, true);
  setTrend('expenseTrend',    -3.2, false);
  setTrend('profitTrend',     18.3, true);
  setTrend('commissionTrend', 1.1,  false);

  destroyChart('main');
  const ctx = document.getElementById('mainChart').getContext('2d');
  State.charts.main = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Tushum',
          data: incomeArr,
          borderColor: '#10B981',
          backgroundColor: 'rgba(16,185,129,.1)',
          borderWidth: 2.5,
          tension: 0.4,
          fill: true,
          pointRadius: 3,
          pointBackgroundColor: '#10B981'
        },
        {
          label: 'Chiqim',
          data: expenseArr,
          borderColor: '#EF4444',
          backgroundColor: 'rgba(239,68,68,.08)',
          borderWidth: 2.5,
          tension: 0.4,
          fill: true,
          pointRadius: 3,
          pointBackgroundColor: '#EF4444'
        }
      ]
    },
    options: {
      ...CHART_OPTS,
      plugins: {
        ...CHART_OPTS.plugins,
        tooltip: {
          ...CHART_OPTS.plugins.tooltip,
          callbacks: { label: ctx => ` ${ctx.dataset.label}: ${fmtFull(ctx.raw)}` }
        }
      }
    }
  });

  // Donut — payment sources
  const sources = d.source_totals || {};
  const srcLabels = Object.keys(sources);
  const srcVals   = Object.values(sources);
  const COLORS = ['#00B9F2','#FF6B35','#8B5CF6','#10B981','#F59E0B','#06B6D4','#6366F1','#EC4899'];

  destroyChart('donut');
  const dCtx = document.getElementById('paymentDonut').getContext('2d');
  State.charts.donut = new Chart(dCtx, {
    type: 'doughnut',
    data: {
      labels: srcLabels,
      datasets: [{ data: srcVals, backgroundColor: COLORS, borderColor: '#05070F', borderWidth: 3, hoverOffset: 8 }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${fmtFull(ctx.raw)}` } }
      }
    }
  });
  const totalSrc = srcVals.reduce((a, b) => a + b, 0);
  const donutEl = document.getElementById('donutTotal');
  if (donutEl) donutEl.textContent = fmt(totalSrc);

  // Sparklines
  mkSparkline('incomeSparkline',     incomeArr.slice(-9),  '#10B981');
  mkSparkline('expenseSparkline',    expenseArr.slice(-9), '#EF4444');
  mkSparkline('profitSparkline',     profitArr.slice(-9),  '#6366F1');
  mkSparkline('commissionSparkline', expenseArr.slice(-9), '#F59E0B');

  // AI Insights
  renderInsights(s);

  // Sources list
  renderSourcesList(sources, COLORS);

  // Breakdown
  renderBreakdown(d.expense_categories || {});
};

const mkSparkline = (id, data, color) => {
  const el = document.getElementById(id);
  if (!el) return;
  destroyChart(id);
  State.charts[id] = new Chart(el.getContext('2d'), {
    type: 'line',
    data: {
      labels: data.map((_, i) => i),
      datasets: [{ data, borderColor: color, backgroundColor: 'transparent', borderWidth: 2, pointRadius: 0, tension: 0.4 }]
    },
    options: {
      responsive: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } }
    }
  });
};

const renderInsights = (s) => {
  const items = [
    {
      type: s.profit_margin > 90 ? 'success' : 'warning',
      icon: s.profit_margin > 90 ? SVGS.trendUp : SVGS.warn,
      title: `Foyda Marginali: ${s.profit_margin}%`,
      text: s.profit_margin > 90
        ? `Sof foyda ${fmtFull(s.total_profit)} — ajoyib ko'rsatkich!`
        : `Margin past. Xarajatlarni kamaytirish kerak.`
    },
    {
      type: 'warning',
      icon: SVGS.money,
      title: 'Komissiya Xarajatlari',
      text: `To'lov tizimlari komissiyasi tushumning ~3-4% ni tashkil qiladi. Naqd+Bank o'tkazmasini oshiring.`
    },
    {
      type: 'info',
      icon: SVGS.star,
      title: s.top_sources?.[0]?.name ? `1-o'rin: ${s.top_sources[0].name}` : 'Tushum manbasi',
      text: s.top_sources?.[0]
        ? `${s.top_sources[0].name} — ${fmtFull(s.top_sources[0].amount)} bilan yetakchi.`
        : 'Ma\'lumot kiritilganda ko\'rinadi.'
    },
    {
      type: 'info',
      icon: SVGS.calendar,
      title: `Faol Kunlar: ${s.active_days}`,
      text: `Kunlik o'rtacha tushum: ${fmtFull(s.avg_daily_income)}.`
    }
  ];

  document.getElementById('insightsList').innerHTML = items.map(i => `
    <div class="insight-item ${i.type}">
      <div class="insight-icon">${i.icon}</div>
      <div class="insight-text"><strong>${i.title}</strong>${i.text}</div>
    </div>
  `).join('');
};

const renderSourcesList = (sources, colors) => {
  const total = Object.values(sources).reduce((a, b) => a + b, 0);
  const sorted = Object.entries(sources).sort((a, b) => b[1] - a[1]);
  const icons = { Payme: SVGS.card, Click: SVGS.click, Uzum: SVGS.uzum, Perechisleniya: SVGS.bank, 'Naqd Eduon': SVGS.cash, Terminal: SVGS.terminal, Paynet: SVGS.globe };

  document.getElementById('sourcesList').innerHTML = sorted.slice(0, 6).map(([name, amt], i) => {
    const pct = total ? (amt / total * 100).toFixed(1) : 0;
    const color = colors[i % colors.length];
    return `
      <div class="source-item">
        <div class="source-icon" style="background:${color}20;color:${color}">${icons[name] || SVGS.defaultSrc}</div>
        <div class="source-info">
          <div class="source-name">${name}</div>
          <div class="source-bar"><div class="source-bar-fill" style="width:${pct}%;background:${color}"></div></div>
        </div>
        <div style="text-align:right">
          <div class="source-amount">${fmt(amt)}</div>
          <div style="font-size:10px;color:var(--text-muted)">${pct}%</div>
        </div>
      </div>`;
  }).join('');
};

const renderBreakdown = (expenses) => {
  const COLORS = ['#00B9F2','#FF6B35','#8B5CF6','#EC4899','#EF4444','#F97316','#10B981'];
  const total = Object.values(expenses).reduce((a, b) => a + b, 0);
  const sorted = Object.entries(expenses).sort((a, b) => b[1] - a[1]);

  document.getElementById('breakdownList').innerHTML = sorted.slice(0, 6).map(([name, amt], i) => {
    const pct = total ? (amt / total * 100).toFixed(0) : 0;
    const color = COLORS[i % COLORS.length];
    return `
      <div class="source-item">
        <div class="source-icon" style="background:${color}20;color:${color}">${SVGS.money}</div>
        <div class="source-info">
          <div class="source-name">${name}</div>
          <div class="source-bar"><div class="source-bar-fill" style="width:${pct}%;background:${color}"></div></div>
        </div>
        <div style="text-align:right">
          <div style="font-size:13px;font-weight:600;color:#EF4444;font-family:'Space Grotesk',sans-serif">-${fmt(amt)}</div>
          <div style="font-size:10px;color:var(--text-muted)">${pct}%</div>
        </div>
      </div>`;
  }).join('');
};

// ─── ANALYTICS PAGE ──────────────────────
const initAnalytics = () => {
  const d = State.data;
  if (!d) return;

  // Monthly bar chart
  const monthly = d.monthly || {};
  const mLabels = Object.keys(monthly);
  const mIncome  = mLabels.map(k => monthly[k].income);
  const mExpense = mLabels.map(k => monthly[k].expense);
  const mProfit  = mLabels.map(k => monthly[k].profit);

  destroyChart('monthlyCompare');
  const ctx1 = document.getElementById('monthlyCompare');
  ctx1.style.height = '320px';
  State.charts.monthlyCompare = new Chart(ctx1.getContext('2d'), {
    type: 'bar',
    data: {
      labels: mLabels,
      datasets: [
        { label: 'Tushum',  data: mIncome,  backgroundColor: 'rgba(16,185,129,.8)',  borderRadius: 6 },
        { label: 'Chiqim',  data: mExpense, backgroundColor: 'rgba(239,68,68,.8)',   borderRadius: 6 },
        { label: 'Foyda',   data: mProfit,  backgroundColor: 'rgba(99,102,241,.8)',  borderRadius: 6 }
      ]
    },
    options: {
      ...CHART_OPTS,
      plugins: {
        ...CHART_OPTS.plugins,
        tooltip: { ...CHART_OPTS.plugins.tooltip, callbacks: { label: c => ` ${c.dataset.label}: ${fmtFull(c.raw)}` } }
      }
    }
  });

  // Weekly trend
  const weekly = d.weekly || {};
  const wLabels = Object.keys(weekly).slice(-10);
  destroyChart('weeklyTrend');
  State.charts.weeklyTrend = new Chart(document.getElementById('weeklyTrend').getContext('2d'), {
    type: 'line',
    data: {
      labels: wLabels,
      datasets: [{
        label: 'Haftalik Tushum',
        data: wLabels.map(k => weekly[k].income),
        borderColor: '#6366F1',
        backgroundColor: 'rgba(99,102,241,.1)',
        borderWidth: 2.5,
        tension: 0.4,
        fill: true,
        pointRadius: 4,
        pointBackgroundColor: '#6366F1'
      }]
    },
    options: { ...CHART_OPTS, plugins: { ...CHART_OPTS.plugins, tooltip: { ...CHART_OPTS.plugins.tooltip, callbacks: { label: c => ` ${fmtFull(c.raw)}` } } } }
  });

  // Commission horizontal bar
  const exp = d.expense_categories || {};
  const expLabels = Object.keys(exp);
  const expVals   = Object.values(exp);
  destroyChart('commissionChart');
  State.charts.commissionChart = new Chart(document.getElementById('commissionChart').getContext('2d'), {
    type: 'bar',
    data: {
      labels: expLabels,
      datasets: [{ label: 'Komissiya', data: expVals, backgroundColor: ['#00B9F2','#FF6B35','#8B5CF6','#EC4899','#EF4444','#F97316','#10B981'], borderRadius: 6 }]
    },
    options: {
      ...CHART_OPTS,
      indexAxis: 'y',
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${fmtFull(c.raw)}` } } }
    }
  });

  // Metrics
  const totalInc = mIncome.reduce((a, b) => a + b, 0);
  const avgMonthly = mLabels.length ? totalInc / mLabels.length : 0;
  const growth = mIncome.length >= 2 ? ((mIncome.at(-1) - mIncome[0]) / mIncome[0] * 100).toFixed(1) : 0;
  const s = d.summary;

  document.getElementById('metricsGrid').innerHTML = `
    <div class="metric-item">
      <div class="metric-value">${fmt(avgMonthly)}</div>
      <div class="metric-label">O'rtacha Oylik Tushum</div>
    </div>
    <div class="metric-item">
      <div class="metric-value" style="color:#10B981">${growth > 0 ? '+' : ''}${growth}%</div>
      <div class="metric-label">Umumiy O'sish</div>
    </div>
    <div class="metric-item">
      <div class="metric-value" style="color:#F59E0B">${s.profit_margin}%</div>
      <div class="metric-label">Foyda Marginali</div>
    </div>
    <div class="metric-item">
      <div class="metric-value" style="color:#6366F1">${s.active_days}</div>
      <div class="metric-label">Faol Kunlar</div>
    </div>
  `;
};

// ─── REPORTS PAGE ────────────────────────
const showReport = async (type) => {
  State.currentReport = type;
  document.querySelectorAll('.report-tab').forEach(t => t.classList.toggle('active', t.dataset.report === type));

  document.getElementById('reportContent').innerHTML = `
    <div style="display:flex;align-items:center;justify-content:center;height:200px;color:var(--text-muted)">
      <div class="loading-spinner" style="width:40px;height:40px;margin-right:12px">
        <div class="spinner-ring"></div><div class="spinner-ring"></div><div class="spinner-ring"></div>
      </div>Hisobot yuklanmoqda...
    </div>`;

  const result = await apiFetch(`/report/${type}`);
  if (!result) {
    document.getElementById('reportContent').innerHTML = `<p style="color:#EF4444;padding:20px">Xato yuz berdi</p>`;
    return;
  }

  const lines = result.report.split('\n');
  document.getElementById('reportContent').innerHTML = `
    <pre style="font-family:'Space Grotesk',monospace;font-size:13px;line-height:1.8;color:var(--text-secondary);white-space:pre-wrap">${
      result.report
        .replace(/📅.*|📊.*|📈.*/g, m => `<span style="color:#F1F5F9;font-weight:700;font-size:15px">${m}</span>`)
        .replace(/💚.*/g, m => `<span style="color:#10B981">${m}</span>`)
        .replace(/🔴.*/g, m => `<span style="color:#EF4444">${m}</span>`)
        .replace(/💙.*/g, m => `<span style="color:#6366F1">${m}</span>`)
        .replace(/🤖.*/g, m => `<span style="color:#A78BFA;font-weight:600">${m}</span>`)
        .replace(/─{5,}/g, m => `<span style="color:var(--border-color)">${m}</span>`)
    }</pre>`;
};

// ─── FORECAST PAGE ───────────────────────
const initForecast = () => {
  const d = State.data;
  if (!d) return;

  const daily = d.daily || {};
  const days   = Object.keys(daily).slice(0, 30).reverse();
  const vals   = days.map(k => daily[k]?.income || 0);

  // Linear regression
  const n = vals.length;
  if (n < 2) return;
  const sumX  = vals.reduce((_, __, i) => _ + i, 0);
  const sumY  = vals.reduce((a, b) => a + b, 0);
  const sumXY = vals.reduce((acc, v, i) => acc + i * v, 0);
  const sumX2 = vals.reduce((acc, _, i) => acc + i * i, 0);
  const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
  const inter = (sumY - slope * sumX) / n;

  const forecastDays = parseInt(document.getElementById('forecastPeriod')?.value || 30);
  const fLabels = [], fData = [];
  for (let i = 1; i <= forecastDays; i++) {
    const dd = new Date();
    dd.setDate(dd.getDate() + i);
    fLabels.push(`${dd.getDate()}.${String(dd.getMonth()+1).padStart(2,'0')}`);
    const raw = inter + slope * (n + i);
    fData.push(Math.max(0, Math.round(raw * (0.9 + Math.random() * 0.2))));
  }

  destroyChart('forecastChart');
  const ctx = document.getElementById('forecastChart');
  ctx.style.height = '320px';
  State.charts.forecastChart = new Chart(ctx.getContext('2d'), {
    type: 'line',
    data: {
      labels: [...days, ...fLabels],
      datasets: [
        {
          label: 'Haqiqiy',
          data: [...vals, ...new Array(forecastDays).fill(null)],
          borderColor: '#10B981',
          backgroundColor: 'rgba(16,185,129,.05)',
          borderWidth: 2.5,
          tension: 0.4,
          fill: true,
          pointRadius: 3,
          pointBackgroundColor: '#10B981'
        },
        {
          label: 'Bashorat',
          data: [...new Array(n).fill(null), ...fData],
          borderColor: '#6366F1',
          backgroundColor: 'rgba(99,102,241,.1)',
          borderDash: [6, 3],
          borderWidth: 2.5,
          tension: 0.4,
          fill: true,
          pointRadius: 3,
          pointBackgroundColor: '#6366F1'
        }
      ]
    },
    options: {
      ...CHART_OPTS,
      plugins: {
        ...CHART_OPTS.plugins,
        tooltip: { ...CHART_OPTS.plugins.tooltip, callbacks: { label: c => c.raw != null ? ` ${c.dataset.label}: ${fmtFull(c.raw)}` : '' } }
      }
    }
  });

  const avgH = vals.reduce((a, b) => a + b, 0) / n;
  const avgF = fData.reduce((a, b) => a + b, 0) / forecastDays;
  const growthRate = ((avgF - avgH) / avgH * 100).toFixed(1);

  document.getElementById('forecastCards').innerHTML = [
    { label: 'Kelajak hafta',   value: fData.slice(0, 7).reduce((a,b) => a+b, 0),  period: '7 kun' },
    { label: '2 hafta',         value: fData.slice(0, 14).reduce((a,b) => a+b, 0), period: '14 kun' },
    { label: `${forecastDays} kunlik`, value: fData.reduce((a,b) => a+b, 0),       period: 'Jami' },
    { label: "O'sish sur'ati",  value: null, period: 'AI bashorat', isRate: true },
  ].map(c => `
    <div class="forecast-card">
      <div class="forecast-card-date">${c.period}</div>
      <div class="forecast-card-value" style="${c.isRate ? (growthRate>0?'color:#10B981':'color:#EF4444') : ''}">
        ${c.isRate ? `${growthRate > 0 ? '+' : ''}${growthRate}%` : fmt(c.value)}
      </div>
      <div class="forecast-card-label">${c.label}</div>
    </div>`).join('');
};

// ─── TRANSACTIONS ────────────────────────
const renderTransactions = (filter = '') => {
  const d = State.data;
  if (!d) return;

  // Build transactions from daily data
  const txns = [];
  const daily = d.daily || {};
  const catFilter = document.getElementById('categoryFilter')?.value.toLowerCase() || '';
  const typeFilter = document.getElementById('typeFilter')?.value || '';
  const sources = d.source_totals || {};

  // Income rows
  Object.entries(daily).slice(0, 60).forEach(([date, vals]) => {
    if (vals.income > 0) {
      // Pick top source for the day
      const topSrc = Object.keys(sources)[0] || 'Payme';
      const tx = { date, category: topSrc, type: 'income', amount: vals.income, status: 'completed' };
      const match = (!filter || date.includes(filter) || tx.category.toLowerCase().includes(filter))
                 && (!catFilter || tx.category.toLowerCase().includes(catFilter))
                 && (!typeFilter || tx.type === typeFilter);
      if (match) txns.push(tx);
    }
    if (vals.expense > 0) {
      const tx = { date, category: 'Komissiya', type: 'expense', amount: -vals.expense, status: 'completed' };
      const match = (!filter || date.includes(filter) || tx.category.toLowerCase().includes(filter))
                 && (!catFilter || tx.category.toLowerCase().includes(catFilter))
                 && (!typeFilter || tx.type === typeFilter);
      if (match) txns.push(tx);
    }
  });

  const tbody = document.getElementById('transactionsBody');
  if (!txns.length) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:40px">Tranzaksiya topilmadi</td></tr>`;
    return;
  }

  tbody.innerHTML = txns.slice(0, 80).map(tx => `
    <tr>
      <td>${tx.date}</td>
      <td>${tx.category}</td>
      <td><span class="tx-badge ${tx.type}">${tx.type === 'income' ? '▲ Tushum' : '▼ Chiqim'}</span></td>
      <td class="tx-amount ${tx.amount >= 0 ? 'positive' : 'negative'}">${tx.amount >= 0 ? '+' : ''}${fmtFull(tx.amount)}</td>
      <td><span class="tx-status ${tx.status}">${tx.status === 'completed' ? 'Yakunlandi' : 'Kutilmoqda'}</span></td>
    </tr>`).join('');
};

// ─── AI CHAT ─────────────────────────────
const sendChat = async (msg) => {
  if (!msg.trim()) return;
  const messagesDiv = document.getElementById('chatMessages');

  messagesDiv.innerHTML += `
    <div class="chat-message user">
      <div class="message-avatar user-avatar">${SVGS.user}</div>
      <div class="message-content"><div class="message-bubble">${msg.replace(/</g,'&lt;')}</div></div>
    </div>`;
  document.getElementById('chatInput').value = '';
  messagesDiv.scrollTop = messagesDiv.scrollHeight;

  const typingDiv = document.getElementById('typingIndicator');
  typingDiv.style.display = 'flex';

  const result = await apiFetch('/ai-analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: msg })
  });

  typingDiv.style.display = 'none';

  const answer = result?.answer || '❌ Server xatosi';
  const formatted = answer
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/```([\s\S]*?)```/g, '<pre style="background:rgba(0,0,0,.3);padding:12px;border-radius:8px;font-size:12px;overflow-x:auto">$1</pre>')
    .replace(/\n/g, '<br>');

  messagesDiv.innerHTML += `
    <div class="chat-message ai">
      <div class="message-avatar ai-avatar">${SVGS.bot}</div>
      <div class="message-content"><div class="message-bubble">${formatted}</div></div>
    </div>`;
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
};

// ─── NAVIGATION ──────────────────────────
const navigate = (page) => {
  State.currentPage = page;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(`page-${page}`).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(i => i.classList.toggle('active', i.dataset.page === page));
  const labels = {
    dashboard: 'Dashboard', analytics: 'Moliyaviy Tahlil',
    reports: 'Hisobotlar', forecast: 'AI Prognoz',
    transactions: 'Tranzaksiyalar', sync: 'Google Sheets Sync', 'ai-chat': 'AI Maslahat'
  };
  document.getElementById('pageBreadcrumb').textContent = labels[page] || page;

  if (page === 'analytics')    initAnalytics();
  if (page === 'reports')      showReport(State.currentReport);
  if (page === 'forecast')     initForecast();
  if (page === 'transactions') renderTransactions();
};

// ─── SYNC / TELEGRAM ─────────────────────
const saveConfig = async () => {
  const token  = document.getElementById('botToken')?.value.trim()  || State.telegramToken;
  const chatId = document.getElementById('chatId')?.value.trim()   || State.telegramChatId;
  if (token) { State.telegramToken = token; localStorage.setItem('tg_token', token); }
  if (chatId){ State.telegramChatId = chatId; localStorage.setItem('tg_chat_id', chatId); }

  await apiFetch('/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ telegram_token: token, telegram_chat_id: chatId })
  });
  toast('success', 'Konfiguratsiya saqlandi', 'Telegram sozlamalari saqlandi');
};

const sendTelegramReport = async (period) => {
  if (!State.telegramToken || !State.telegramChatId) {
    toast('warning', 'Token kerak', 'Sync sahifasida Bot Token va Chat ID kiriting');
    navigate('sync');
    return;
  }
  const res = await apiFetch('/send-report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ period, token: State.telegramToken, chat_id: State.telegramChatId })
  });
  if (res?.ok) toast('success', 'Telegram ga yuborildi! 🚀', `${period} hisobot muvaffaqiyatli yetkazildi`);
  else toast('error', 'Yuborishda xato', res?.error || 'Token yoki chat_id noto\'g\'ri');
};

// ─── INIT ────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  refreshChartOpts();
  
  // Telegram WebApp theme check
  if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.expand();
  }
  
  await loadData();
  setTimeout(() => { 
      const overlay = document.getElementById('loadingOverlay');
      if(overlay) overlay.style.display = 'none'; 
  }, 300);

  // Theme init
  const savedTheme = localStorage.getItem('theme') || 'dark';
  const themeIcon = document.getElementById('themeIcon');
  if (savedTheme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
    if (themeIcon) themeIcon.innerHTML = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
  }

  document.getElementById('themeToggle')?.addEventListener('click', () => {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    if (themeIcon) {
      if (newTheme === 'light') {
        themeIcon.innerHTML = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
      } else {
        themeIcon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
      }
    }
    refreshChartOpts();
    if (State.currentPage === 'dashboard') initDashboard();
    if (State.currentPage === 'analytics') initAnalytics();
    if (State.currentPage === 'forecast') initForecast();
  });

  // Auth Login Check
  const doLogin = async () => {
    const pin = document.getElementById('authPin').value.trim();
    if (!pin) return;
    localStorage.setItem('app_pin', pin);
    const res = await fetch(API + '/status', { headers: { 'Authorization': `Bearer ${pin}` } });
    if (res.ok) {
      document.getElementById('authOverlay').style.display = 'none';
      document.getElementById('authErr').style.display = 'none';
      await loadData();
    } else {
      document.getElementById('authErr').style.display = 'block';
    }
  };

  document.getElementById('authBtn')?.addEventListener('click', doLogin);
  document.getElementById('authPin')?.addEventListener('keypress', e => e.key === 'Enter' && doLogin());

  // Check auth quickly
  if (!localStorage.getItem('app_pin')) {
    document.getElementById('authOverlay').style.display = 'flex';
  } else {
    document.getElementById('authOverlay').style.display = 'none';
    // Load data from backend
    await loadData();
    setTimeout(() => { document.getElementById('loadingOverlay').style.display = 'none'; }, 300);
  }

  // Date display

  // Nav
  document.querySelectorAll('.nav-item').forEach(item =>
    item.addEventListener('click', e => { e.preventDefault(); navigate(item.dataset.page); }));

  // Sidebar toggle
  document.getElementById('sidebarToggle')?.addEventListener('click', () =>
    document.getElementById('sidebar').classList.toggle('collapsed'));
  document.getElementById('menuBtn')?.addEventListener('click', () =>
    document.getElementById('sidebar').classList.toggle('mobile-open'));

  // Period selector
  document.querySelectorAll('.period-btn').forEach(btn =>
    btn.addEventListener('click', () => {
      document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      State.period = btn.dataset.period;
      initDashboard();
    }));

  // Refresh
  document.getElementById('refreshBtn')?.addEventListener('click', async () => {
    toast('info', 'Yangilanmoqda...', 'Sheets dan ma\'lumot olinmoqda');
    await loadData(true);
    toast('success', 'Yangilandi!', State.hasRealData ? 'Real data yuklandi' : 'Demo data yangilandi');
  });

  const dateDisplay = document.querySelector('.date-display');
  if (dateDisplay) {
    dateDisplay.style.cursor = 'pointer';
    dateDisplay.addEventListener('click', () => {
      toast('info', 'Tez orada!', 'Kengaytirilgan sana filtri tez orada qo\'shiladi');
    });
  }

  // Report tabs
  document.querySelectorAll('.report-tab').forEach(t =>
    t.addEventListener('click', () => showReport(t.dataset.report)));

  // Generate / Export / Telegram buttons
  document.getElementById('generateReport')?.addEventListener('click', () => showReport(State.currentReport));

  document.getElementById('exportReport')?.addEventListener('click', async () => {
    const res = await apiFetch(`/report/${State.currentReport}`);
    if (!res) return;
    const blob = new Blob([res.report], { type: 'text/plain;charset=utf-8' });
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(blob),
      download: `MLP_${State.currentReport}_${new Date().toISOString().slice(0,10)}.txt`
    });
    a.click();
    toast('success', 'Hisobot yuklandi', 'Fayl saqlandi');
  });

  document.getElementById('sendTelegram')?.addEventListener('click', () =>
    sendTelegramReport(State.currentReport));

  // Forecast period change
  document.getElementById('forecastPeriod')?.addEventListener('change', initForecast);
  document.getElementById('runForecast')?.addEventListener('click', () => {
    initForecast();
    toast('success', 'Prognoz yangilandi', 'AI bashorat qayta hisoblandi');
  });

  // Sync page — connect & save
  document.getElementById('connectSheets')?.addEventListener('click', async () => {
    await saveConfig();
    toast('info', 'Ma\'lumotlar yangilanmoqda...', '');
    await loadData(true);
    toast('success', data?.has_real_data ? 'Real data yuklandi!' : 'Demo data', '');
  });

  // Telegram config
  document.getElementById('telegramToggle')?.addEventListener('change', e => {
    const tc = document.getElementById('telegramConfig');
    if (tc) tc.style.display = e.target.checked ? 'flex' : 'none';
  });
  document.getElementById('saveTelegramBtn')?.addEventListener('click', saveConfig);

  // Transactions search
  const search = document.getElementById('transactionSearch');
  search?.addEventListener('input', () => renderTransactions(search.value.toLowerCase()));
  document.getElementById('categoryFilter')?.addEventListener('change', () => renderTransactions(search?.value || ''));
  document.getElementById('typeFilter')?.addEventListener('change',   () => renderTransactions(search?.value || ''));

  // AI Chat
  document.getElementById('sendBtn')?.addEventListener('click', () => {
    const v = document.getElementById('chatInput')?.value.trim();
    if (v) sendChat(v);
  });
  document.getElementById('chatInput')?.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(e.target.value.trim()); }
  });
  document.addEventListener('click', e => {
    if (e.target.classList.contains('quick-q')) sendChat(e.target.dataset.q);
  });

  // Insight refresh
  document.getElementById('insightRefresh')?.addEventListener('click', () => {
    if (State.data) renderInsights(State.data.summary);
  });

  // Chart type toggle
  document.querySelectorAll('.chart-btn').forEach(btn =>
    btn.addEventListener('click', () => {
      document.querySelectorAll('.chart-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (State.charts.main) { State.charts.main.config.type = btn.dataset.chartType; State.charts.main.update(); }
    }));

  // Auto re-fetch every 5 min
  setInterval(async () => {
    await loadData(true);
    if (State.currentPage === 'analytics')    initAnalytics();
    if (State.currentPage === 'forecast')     initForecast();
    if (State.currentPage === 'transactions') renderTransactions();
    toast('info', 'Avtomatik yangilash', 'Ma\'lumotlar yangilandi');
  }, 5 * 60 * 1000);

  toast('success', 'AI Finansist ishga tushdi! 🚀',
    State.hasRealData ? 'Real Sheets data yuklandi' : 'Demo rejim — Sheets bo\'sh');
});
