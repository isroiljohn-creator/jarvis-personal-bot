"""
Developer moduli — GitHub va Railway bilan integratsiya.
Bot orqali loyihalarni kuzatish, loglarni ko'rish va buzilgan deploylarni tuzatish.
"""
import os
import json
import base64
import logging
import requests
from typing import Optional

logger = logging.getLogger("jarvis.developer")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
RAILWAY_TOKEN = os.environ.get("RAILWAY_API_TOKEN", "")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "isroiljohn-creator")

RAILWAY_API_URL = "https://backboard.railway.com/graphql/v2"
GITHUB_API_URL = "https://api.github.com"


# ─────────────────────────────────────────────
# GITHUB
# ─────────────────────────────────────────────

def _gh_headers() -> dict:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Jarvis-Bot/1.0",
    }


def github_list_repos(limit: int = 20) -> str:
    """GitHub'dagi barcha repolarni ro'yxatlash."""
    if not GITHUB_TOKEN:
        return "❌ GITHUB_TOKEN sozlanmagan."
    try:
        resp = requests.get(
            f"{GITHUB_API_URL}/user/repos",
            headers=_gh_headers(),
            params={"sort": "updated", "per_page": limit, "type": "owner"},
            timeout=15,
        )
        resp.raise_for_status()
        repos = resp.json()
        lines = []
        for r in repos:
            status = "🔴 arxivlangan" if r.get("archived") else "🟢 faol"
            lines.append(f"{status} {r['name']} — {r.get('description') or 'tavsif yo\'q'}")
        return "\n".join(lines) if lines else "Repolar topilmadi."
    except Exception as e:
        return f"❌ GitHub xatosi: {e}"


def github_read_file(repo: str, path: str, branch: str = "main") -> str:
    """GitHub'dagi faylni o'qish."""
    if not GITHUB_TOKEN:
        return "❌ GITHUB_TOKEN sozlanmagan."
    try:
        url = f"{GITHUB_API_URL}/repos/{GITHUB_USERNAME}/{repo}/contents/{path}"
        resp = requests.get(url, headers=_gh_headers(), params={"ref": branch}, timeout=15)
        if resp.status_code == 404:
            return f"❌ Fayl topilmadi: {repo}/{path}"
        resp.raise_for_status()
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        # Juda uzun bo'lsa qisqartir
        if len(content) > 4000:
            content = content[:4000] + "\n... [qolgan qismi qisqartirildi]"
        return content
    except Exception as e:
        return f"❌ Fayl o'qish xatosi: {e}"


def github_write_file(repo: str, path: str, content: str,
                      commit_message: str, branch: str = "main") -> str:
    """GitHub'ga fayl yozish (yangilash yoki yaratish)."""
    if not GITHUB_TOKEN:
        return "❌ GITHUB_TOKEN sozlanmagan."
    try:
        url = f"{GITHUB_API_URL}/repos/{GITHUB_USERNAME}/{repo}/contents/{path}"
        # Mavjud faylning SHA sini olish (yangilash uchun kerak)
        sha = None
        existing = requests.get(url, headers=_gh_headers(), params={"ref": branch}, timeout=10)
        if existing.status_code == 200:
            sha = existing.json().get("sha")

        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        resp = requests.put(url, headers=_gh_headers(), json=payload, timeout=20)
        resp.raise_for_status()
        action = "yangilandi" if sha else "yaratildi"
        return f"✅ {repo}/{path} {action}. Commit: {commit_message}"
    except Exception as e:
        return f"❌ Fayl yozish xatosi: {e}"


def github_get_recent_commits(repo: str, limit: int = 5) -> str:
    """So'nggi commitlarni olish."""
    if not GITHUB_TOKEN:
        return "❌ GITHUB_TOKEN sozlanmagan."
    try:
        url = f"{GITHUB_API_URL}/repos/{GITHUB_USERNAME}/{repo}/commits"
        resp = requests.get(url, headers=_gh_headers(), params={"per_page": limit}, timeout=15)
        if resp.status_code == 404:
            return f"❌ Repo topilmadi: {repo}"
        resp.raise_for_status()
        commits = resp.json()
        lines = []
        for c in commits:
            sha = c["sha"][:7]
            msg = c["commit"]["message"].split("\n")[0][:80]
            author = c["commit"]["author"]["name"]
            date = c["commit"]["author"]["date"][:10]
            lines.append(f"[{sha}] {date} — {author}: {msg}")
        return "\n".join(lines) if lines else "Commitlar topilmadi."
    except Exception as e:
        return f"❌ Commitlar xatosi: {e}"


# ─────────────────────────────────────────────
# RAILWAY
# ─────────────────────────────────────────────

def _rl_headers() -> dict:
    return {
        "Authorization": f"Bearer {RAILWAY_TOKEN}",
        "Content-Type": "application/json",
    }


def _railway_query(query: str, variables: dict = None) -> dict:
    """Railway GraphQL so'rovi."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(
        RAILWAY_API_URL,
        headers=_rl_headers(),
        json=payload,
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def railway_list_projects() -> str:
    """Barcha Railway proyektlarni ko'rsatish."""
    if not RAILWAY_TOKEN:
        return "❌ RAILWAY_API_TOKEN sozlanmagan."
    try:
        query = """
        query {
          me {
            projects {
              edges {
                node {
                  id
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
        if not projects:
            return "Proyektlar topilmadi."

        lines = []
        STATUS_EMOJI = {
            "SUCCESS": "✅", "FAILED": "❌", "DEPLOYING": "🔄",
            "CRASHED": "💥", "SLEEPING": "😴", "REMOVED": "🗑",
        }
        for p in projects:
            proj = p["node"]
            lines.append(f"\n📁 {proj['name']} (ID: {proj['id'][:8]}...)")
            for s in proj["services"]["edges"]:
                svc = s["node"]
                deployments = svc["deployments"]["edges"]
                if deployments:
                    status_raw = deployments[0]["node"]["status"]
                    emoji = STATUS_EMOJI.get(status_raw, "❓")
                    lines.append(f"  {emoji} {svc['name']} — {status_raw}")
                else:
                    lines.append(f"  ⚪ {svc['name']} — deploy yo'q")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Railway xatosi: {e}"


def railway_get_logs(service_id: str, limit: int = 50) -> str:
    """Servis loglarini olish."""
    if not RAILWAY_TOKEN:
        return "❌ RAILWAY_API_TOKEN sozlanmagan."
    try:
        query = """
        query($serviceId: String!, $limit: Int!) {
          deploymentLogs(serviceId: $serviceId, limit: $limit) {
            message
            severity
            timestamp
          }
        }
        """
        # Railway yangi API uchun deployment loglarini boshqa endpoint'dan olish
        # Avval so'nggi deployment ID sini topamiz
        dep_query = """
        query($serviceId: String!) {
          service(id: $serviceId) {
            deployments(first: 1) {
              edges {
                node {
                  id
                  status
                  createdAt
                }
              }
            }
          }
        }
        """
        dep_data = _railway_query(dep_query, {"serviceId": service_id})
        deployments = (dep_data.get("data", {}).get("service", {})
                       .get("deployments", {}).get("edges", []))
        if not deployments:
            return "❌ Deploy topilmadi."

        dep_id = deployments[0]["node"]["id"]
        dep_status = deployments[0]["node"]["status"]
        dep_date = deployments[0]["node"]["createdAt"][:19]

        log_query = """
        query($deploymentId: String!) {
          deploymentLogs(deploymentId: $deploymentId) {
            message
            severity
            timestamp
          }
        }
        """
        log_data = _railway_query(log_query, {"deploymentId": dep_id})
        logs = log_data.get("data", {}).get("deploymentLogs", [])

        if not logs:
            return f"Deploy ID: {dep_id[:8]}\nStatus: {dep_status} ({dep_date})\n\nLoglar topilmadi."

        lines = [f"Deploy: {dep_status} ({dep_date})\n"]
        for log in logs[-limit:]:
            severity = log.get("severity", "INFO")
            msg = log.get("message", "")
            prefix = "🔴" if severity in ("ERROR", "FATAL") else "⚪"
            lines.append(f"{prefix} {msg}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Log olish xatosi: {e}"


def railway_get_service_id_by_name(project_name: str, service_name: str) -> Optional[str]:
    """Proyekt va servis nomi bo'yicha servis ID sini topish."""
    if not RAILWAY_TOKEN:
        return None
    try:
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
        for p in projects:
            proj = p["node"]
            if project_name.lower() in proj["name"].lower():
                for s in proj["services"]["edges"]:
                    svc = s["node"]
                    if service_name.lower() in svc["name"].lower():
                        return svc["id"]
        return None
    except Exception:
        return None


def railway_redeploy(service_id: str) -> str:
    """Servisni qayta deploy qilish."""
    if not RAILWAY_TOKEN:
        return "❌ RAILWAY_API_TOKEN sozlanmagan."
    try:
        mutation = """
        mutation($serviceId: String!) {
          serviceInstanceRedeploy(serviceId: $serviceId)
        }
        """
        data = _railway_query(mutation, {"serviceId": service_id})
        if data.get("errors"):
            return f"❌ Redeploy xatosi: {data['errors'][0]['message']}"
        return f"✅ Servis qayta deploy qilindi. ID: {service_id[:8]}..."
    except Exception as e:
        return f"❌ Redeploy xatosi: {e}"


def railway_get_status(service_id: str) -> str:
    """Servis holati va so'nggi deploy ma'lumotlari."""
    if not RAILWAY_TOKEN:
        return "❌ RAILWAY_API_TOKEN sozlanmagan."
    try:
        query = """
        query($serviceId: String!) {
          service(id: $serviceId) {
            name
            deployments(first: 3) {
              edges {
                node {
                  id
                  status
                  createdAt
                  url
                }
              }
            }
          }
        }
        """
        data = _railway_query(query, {"serviceId": service_id})
        svc = data.get("data", {}).get("service", {})
        if not svc:
            return "❌ Servis topilmadi."

        lines = [f"Servis: {svc['name']}"]
        STATUS_EMOJI = {
            "SUCCESS": "✅", "FAILED": "❌", "DEPLOYING": "🔄",
            "CRASHED": "💥", "SLEEPING": "😴",
        }
        for d in svc["deployments"]["edges"]:
            dep = d["node"]
            emoji = STATUS_EMOJI.get(dep["status"], "❓")
            date = dep["createdAt"][:19]
            lines.append(f"{emoji} {dep['status']} — {date}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Status xatosi: {e}"


# ─────────────────────────────────────────────
# QULAYLIK FUNKSIYALARI
# ─────────────────────────────────────────────

# Barcha ma'lum proyektlar ro'yxati (config.json dan olindi)
KNOWN_PROJECTS = {
    "jarvis-personal-bot": {
        "project": "af5d5a82-37c6-45de-abe3-a12d9fb9c578",
        "service": "d2cd9188-1fcc-485f-9506-26929e382b49",
        "repo": "jarvis-personal-bot",
    },
    "jarvis-suite": {
        "project": "1194c82c-ce44-429e-8e7c-10984084a5a3",
        "service": "6c08081a-2d1d-4ab2-ac78-266530014dfe",
        "repo": "jarvis-suite",
    },
    "nuvi-academy-bot": {
        "project": "a656184f-af88-4371-b89a-9300f3d2932e",
        "service": "9d92b780-013b-4fa8-879f-4ed926db11b0",
        "repo": "nuvi-academy-bot",
    },
    "kurs-yordamchisi": {
        "project": "4e6ca2f3-5056-440f-b955-c536255e7fd1",
        "service": "996b15c5-eaff-42f3-b85e-5a62aff2e440",
        "repo": "kurs-yordamchisi",
    },
    "lead-magnet-bot": {
        "project": "13f16634-9a77-481d-9b3d-7d1374c1dfec",
        "service": "4a75c65b-6ad6-4a92-a392-9866a902f25e",
        "repo": "lead-magnet-bot",
    },
    "sendly": {
        "project": "6f528c3f-9b9b-4675-a18c-cdd2271b60a3",
        "service": "c86eefaf-8ba5-460b-93ff-536bac7e44a2",
        "repo": "sendly",
    },
}


def get_project_info(name: str) -> Optional[dict]:
    """Proyekt nomidan ma'lumot olish."""
    name_lower = name.lower()
    for key, val in KNOWN_PROJECTS.items():
        if name_lower in key:
            return {"name": key, **val}
    return None
