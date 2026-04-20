"""Jarvis xotira tizimi — JSON-based uzoq muddatli xotira."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
import numpy as np
import google.generativeai as genai

logger = logging.getLogger("jarvis.memory")

MEMORY_FILE = Path(os.environ.get("MEMORY_PATH", "data/memory.json"))

def get_embedding(text: str) -> list[float]:
    """Gemini orqali matnning Embedding vektorini olish."""
    try:
        response = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_document"
        )
        return response.get('embedding', [])
    except Exception as e:
        logger.error(f"Embedding yaratishda xato: {e}")
        return []

def load_memory() -> list:
    """Xotirani yuklash."""
    if not MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # Old memory format migration
            new_data = []
            for cat, items in data.items():
                for k, v in items.items():
                    val = v["value"] if isinstance(v, dict) else v
                    new_data.append({
                        "category": cat,
                        "key": k,
                        "value": val,
                        "embedding": get_embedding(f"{cat} - {k}: {val}"),
                        "updated": datetime.now().isoformat()
                    })
            _save(new_data)
            return new_data
        return data
    except Exception:
        return []


def update_memory(category: str, key: str, value: str) -> str:
    """RAG Xotiraga vektor bilan saqlash."""
    mem = load_memory()
    text_content = f"{category} - {key}: {value}"
    emb = get_embedding(text_content)
    
    found = False
    for item in mem:
        if item.get("category") == category and item.get("key") == key:
            item["value"] = value
            item["embedding"] = emb
            item["updated"] = datetime.now().isoformat()
            found = True
            break
            
    if not found:
        mem.append({
            "category": category,
            "key": key,
            "value": value,
            "embedding": emb,
            "updated": datetime.now().isoformat()
        })
        
    _save(mem)
    logger.info(f"💾 Vector Xotira: {category}/{key} = {value}")
    return f"Saqlandi: {key} = {value}"


def search_memory(query: str, top_k: int = 5) -> str:
    """Cosine Similarity yordamida Vektor qidiruv (RAG)."""
    mem = load_memory()
    if not mem or not query:
        return ""
        
    q_emb = get_embedding(query)
    if not q_emb: return ""
    
    q_vec = np.array(q_emb)
    scores = []
    
    for item in mem:
        if "embedding" not in item or not item["embedding"]:
            continue
        item_vec = np.array(item["embedding"])
        # Cosine similarity
        score = np.dot(q_vec, item_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(item_vec) + 1e-9)
        scores.append((score, item))
        
    scores.sort(key=lambda x: x[0], reverse=True)
    
    # 0.5 dan yuqori yaqinlikka ega top xotiralar
    top_items = [x[1] for x in scores[:top_k] if x[0] > 0.55]
    
    if not top_items:
        return ""
        
    lines = ["[AI UCHUN XOTIRADAN TOPILGAN MA'LUMOTLAR]"]
    for it in top_items:
        lines.append(f"  - {it['category'].upper()} | {it['key']}: {it['value']}")
    return "\n".join(lines)


def format_memory_for_prompt() -> str:
    """Eski tizim (Bot qotib qolmasligi uchun)."""
    return search_memory("umumiy shaxsiy ma'lumotlar tavsif")


def _save(data: list) -> None:
    """JSON faylga saqlash."""
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
