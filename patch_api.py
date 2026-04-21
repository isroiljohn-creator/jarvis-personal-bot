import re

with open('api.py', 'r') as f:
    content = f.read()

# Add StaticFiles import
content = content.replace("from fastapi.middleware.cors import CORSMiddleware", "from fastapi.middleware.cors import CORSMiddleware\nfrom fastapi.staticfiles import StaticFiles\nfrom fastapi.responses import FileResponse\nimport datetime")

# Mount static folder
content = content.replace("app = FastAPI(title=\"Jarvis AI Gateway\")", "app = FastAPI(title=\"Jarvis AI Gateway\")\napp.mount(\"/static\", StaticFiles(directory=\"static\"), name=\"static\")")

# Replace finance_dashboard and get_finance_data
pattern = re.compile(r'@app\.get\("/finance"\).*?@app\.get\("/api/finance/data"\)\nasync def get_finance_data\(\):\n.*?(?=@app\.get\("/history"\))', re.DOTALL)

replacement = """@app.get("/finance")
async def finance_dashboard():
    \"\"\"Telegram Mini App uchun vizual Hisob-kitob (Moliya) interfeysi (AI Finansist UI).\"\"\"
    return FileResponse("static/index.html")

@app.get("/api/finance/data")
async def get_finance_data(force: bool = False):
    \"\"\"AI Finansist UI kutayotgan murakkab JSON strukturasini PostgreSQL dan yig'ib beradi.\"\"\"
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
        pm = t.get('payment_method', 'Moma\'lum').title()
        
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

    active_days = len(daily)
    
    top_sources = sorted([{"name": k, "amount": v} for k, v in sources.items()], key=lambda x: x["amount"], reverse=True)
    
    summary = {
        "total_income": total_income,
        "total_expense": total_expense,
        "total_profit": total_income - total_expense,
        "avg_daily_income": total_income / max(active_days, 1),
        "profit_margin": round((total_income - total_expense) / total_income * 100, 2) if total_income > 0 else 0,
        "top_sources": top_sources[:3],
        "active_days": active_days,
        "commission_rate": 3.0
    }
    
    return {
        "summary": summary,
        "daily": daily,
        "monthly": monthly,
        "weekly": weekly,
        "source_totals": sources,
        "expense_categories": expenses_cat,
        "last_updated": datetime.datetime.now().isoformat(),
        "has_real_data": len(txns) > 0,
        "sheet_name": "PostgreSQL: transactions"
    }

@app.post("/api/finance/ai-analyze")
async def ai_analyze(request: Request):
    from ai import get_gemini_response
    body = await request.json()
    question = body.get("question", "")
    
    res = await get_gemini_response(f"Siz AI Finansist qismisiz. Quyidagi foydalanuvchi moliyaviy savoliga qisqa va aniq vizual formatda (grafik belgilardan foydalanib) javob bering, html emas. Savol: {question}. Database moliyalari bor deb hisoblang.")
    return {"answer": res.replace("**", "<strong>").replace("\n", "<br>"), "generated_at": datetime.datetime.now().isoformat()}

@app.get("/api/finance/report/{period}")
async def report_period(period: str):
    return {"period": period, "report": f"Bu yerda {period} davr uchun AI hisobot shakllantiriladi.", "generated_at": datetime.datetime.now().isoformat()}

"""

content = pattern.sub(replacement, content)

with open('api.py', 'w') as f:
    f.write(content)

print("api.py patched successfully.")
