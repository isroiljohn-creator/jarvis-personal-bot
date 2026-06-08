"""
monitor.py — Kuzatuv moduli:
1. Sayt uptime monitor
2. Railway crash alert
3. Raqobatchi kuzatuv
16. Narx kuzatuv
"""
import os
import json
import logging
import requests
from datetime import datetime
from typing import Optional

logger = logging.getLogger("jarvis.monitor")

MONITOR_DATA_FILE = "/data/monitor_data.json"
RAILWAY_TOKEN = os.environ.get("RAILWAY_API_TOKEN", "")
RAILWAY_API = "https://backboard.railway.com/graphql/v2"


# ─────────────────────────────────────────
# Ma'lumotlarni saqlash / yuklash
# ─────────────────────────────────────────

def _load_data() -> dict:
    try:
        with open(MONITOR_DATA_FILE) as f:
            return json.load(f)
    except Exception:
        default_data = {
            "urls": {
                "https://jarvis-personal-bot-production.up.railway.app/health": {
                    "name": "Jarvis Bot Health",
                    "last_status": None,
                    "added": "2026-06-09T03:00:00"
                }
            },
            "prices": {},
            "competitors": [],
            "crash_notified": {}
        }
        try:
            _save_data(default_data)
        except Exception:
            pass
        return default_data


def _save_data(data: dict) -> None:
    os.makedirs("/data", exist_ok=True)
    with open(MONITOR_DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────
# 1. UPTIME MONITOR
# ─────────────────────────────────────────

def add_monitor_url(url: str, name: str) -> str:
    """Kuzatiladigan URL qo'shish."""
    data = _load_data()
    data["urls"][url] = {"name": name, "last_status": None, "added": datetime.now().isoformat()}
    _save_data(data)
    return f"✅ '{name}' ({url}) kuzatuvga qo'shildi."


def remove_monitor_url(url: str) -> str:
    """URL kuzatuvdan olib tashlash."""
    data = _load_data()
    if url in data["urls"]:
        name = data["urls"].pop(url)["name"]
        _save_data(data)
        return f"✅ '{name}' kuzatuvdan olib tashlandi."
    return f"❌ {url} kuzatuvda topilmadi."


def list_monitor_urls() -> str:
    """Kuzatilayotgan URL'lar ro'yxati."""
    data = _load_data()
    if not data["urls"]:
        return "Hech qanday URL kuzatilmayapti. Qo'shish uchun: 'jarvis.uz saytini kuzat' dang."
    lines = []
    for url, info in data["urls"].items():
        status = info.get("last_status", "?")
        emoji = "🟢" if status == "ok" else ("🔴" if status == "down" else "⚪")
        lines.append(f"{emoji} {info['name']} — {url}")
    return "\n".join(lines)


def check_all_urls() -> list[dict]:
    """Barcha URL'larni tekshirish. Down bo'lganlari qaytariladi."""
    data = _load_data()
    alerts = []
    changed = False

    for url, info in data["urls"].items():
        try:
            resp = requests.get(url, timeout=10, allow_redirects=True)
            is_ok = resp.status_code < 400
        except Exception as e:
            is_ok = False
            logger.warning(f"Uptime check failed {url}: {e}")

        new_status = "ok" if is_ok else "down"
        old_status = info.get("last_status")

        if new_status != old_status:
            changed = True
            info["last_status"] = new_status
            info["last_change"] = datetime.now().isoformat()
            if new_status == "down":
                alerts.append({
                    "type": "down",
                    "name": info["name"],
                    "url": url,
                    "message": f"🔴 {info['name']} ({url}) ISHLAMAYAPTI!"
                })
            else:
                alerts.append({
                    "type": "up",
                    "name": info["name"],
                    "url": url,
                    "message": f"🟢 {info['name']} ({url}) qayta ishlayapti."
                })

    if changed:
        _save_data(data)
    return alerts


# ─────────────────────────────────────────
# 2. RAILWAY CRASH ALERT
# ─────────────────────────────────────────

def _railway_query(query: str, variables: dict = None) -> dict:
    headers = {"Authorization": f"Bearer {RAILWAY_TOKEN}", "Content-Type": "application/json"}
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    try:
        resp = requests.post(RAILWAY_API, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        res_json = resp.json()
        if "errors" in res_json and not res_json.get("data"):
            logger.warning(f"Railway API error: {res_json['errors']}")
            return {"data": {}}
        return res_json
    except Exception as e:
        logger.error(f"Railway API connection error: {e}")
        return {"data": {}}


def check_railway_crashes() -> list[dict]:
    """Barcha Railway servislarini tekshirib, crash bo'lganlarini qaytaradi."""
    if not RAILWAY_TOKEN:
        return []
    try:
        project_id = os.environ.get("RAILWAY_PROJECT_ID")
        projects = []
        
        if project_id:
            query = """
            query($projectId: String!) {
              project(id: $projectId) {
                name
                services {
                  edges {
                    node {
                      id
                      name
                      deployments(first: 1) {
                        edges {
                          node {
                            status
                            createdAt
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """
            data = _railway_query(query, {"projectId": project_id})
            project_node = data.get("data", {}).get("project")
            if project_node:
                projects = [{"node": project_node}]
                
        if not projects:
            query = """
            query {
              me {
                projects {
                  edges {
                    node {
                      name
                      services {
                        edges {
                          node {
                            id
                            name
                            deployments(first: 1) {
                              edges {
                                node {
                                  status
                                  createdAt
                                }
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """
            data = _railway_query(query)
            projects = data.get("data", {}).get("me", {}).get("projects", {}).get("edges", [])
            
        alerts = []
        monitor_data = _load_data()

        CRASH_STATUSES = {"FAILED", "CRASHED", "REMOVED"}

        for p in projects:
            proj = p["node"]
            for s in proj["services"]["edges"]:
                svc = s["node"]
                deps = svc["deployments"]["edges"]
                if not deps:
                    continue
                status = deps[0]["node"]["status"]
                key = f"{proj['name']}/{svc['name']}"

                if status in CRASH_STATUSES:
                    last_notified = monitor_data.get("crash_notified", {}).get(key)
                    dep_time = deps[0]["node"]["createdAt"]
                    if last_notified != dep_time:
                        alerts.append({
                            "project": proj["name"],
                            "service": svc["name"],
                            "status": status,
                            "service_id": svc["id"],
                            "message": f"💥 {proj['name']} / {svc['name']} — {status}"
                        })
                        monitor_data.setdefault("crash_notified", {})[key] = dep_time
                else:
                    monitor_data.setdefault("crash_notified", {}).pop(key, None)

        _save_data(monitor_data)
        return alerts
    except Exception as e:
        logger.error(f"Railway crash check xatosi: {e}")
        return []


# ─────────────────────────────────────────
# 3. RAQOBATCHI KUZATUV
# ─────────────────────────────────────────

def add_competitor(url: str, name: str) -> str:
    """Raqobatchi URL qo'shish."""
    data = _load_data()
    competitors = data.setdefault("competitors", [])
    for c in competitors:
        if c["url"] == url:
            return f"'{name}' allaqachon kuzatuvda."
    competitors.append({"url": url, "name": name, "last_content": "", "added": datetime.now().isoformat()})
    _save_data(data)
    return f"✅ Raqobatchi '{name}' ({url}) kuzatuvga qo'shildi."


def check_competitors() -> list[dict]:
    """Raqobatchilar saytini tekshirib, yangilik borligini aniqlash."""
    data = _load_data()
    changes = []
    for comp in data.get("competitors", []):
        try:
            resp = requests.get(comp["url"], timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            # Faqat matn uzunligini va asosiy tarkibni solishtirish
            content_hash = str(len(resp.text)) + resp.text[100:300] if len(resp.text) > 300 else resp.text
            if comp.get("last_content") and comp["last_content"] != content_hash:
                changes.append({
                    "name": comp["name"],
                    "url": comp["url"],
                    "message": f"🔍 {comp['name']} saytida o'zgarish aniqlandi: {comp['url']}"
                })
            comp["last_content"] = content_hash
        except Exception as e:
            logger.warning(f"Competitor check {comp['url']}: {e}")
    _save_data(data)
    return changes


# ─────────────────────────────────────────
# 16. NARX KUZATUV
# ─────────────────────────────────────────

def add_price_tracker(url: str, product_name: str, current_price: str = "") -> str:
    """Narx kuzatiladigan mahsulot URL qo'shish."""
    data = _load_data()
    data.setdefault("prices", {})[url] = {
        "name": product_name,
        "last_price": current_price,
        "added": datetime.now().isoformat()
    }
    _save_data(data)
    price_display = current_price if current_price else "noma'lum"
    return f"✅ '{product_name}' narxi kuzatuvga qo'shildi. Hozirgi narx: {price_display}"


def check_prices() -> list[dict]:
    """Mahsulot narxlarini tekshirish (AI orqali narxni ajratish kerak)."""
    data = _load_data()
    results = []
    for url, info in data.get("prices", {}).items():
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            # Narxni oddiy usulda qidirish (raqam + valyuta)
            import re
            text = resp.text
            # JSON-LD yoki og:price meta tegidan narx qidirish
            price_patterns = [
                r'"price":\s*"?([\d,\.]+)"?',
                r'itemprop="price"[^>]*content="([\d,\.]+)"',
                r'<span[^>]*class="[^"]*price[^"]*"[^>]*>([\$€£₽\d,\. ]+)<',
            ]
            found_price = None
            for pattern in price_patterns:
                match = re.search(pattern, text)
                if match:
                    found_price = match.group(1).strip()
                    break

            if found_price and found_price != info.get("last_price"):
                old = info.get("last_price", "noma'lum")
                results.append({
                    "name": info["name"],
                    "url": url,
                    "old_price": old,
                    "new_price": found_price,
                    "message": f"💰 {info['name']} narxi o'zgardi: {old} → {found_price}\n{url}"
                })
                info["last_price"] = found_price
        except Exception as e:
            logger.warning(f"Price check {url}: {e}")
    _save_data(data)
    return results
