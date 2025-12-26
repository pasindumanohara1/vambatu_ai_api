# app.py  –  multi-user safe, Pollinations → Mistral fallback, **web-search agent** + global lock
import os
import threading
import time
import urllib.parse
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from duckduckgo_search import DDGS   # <-- web search tool

# ---------- config ----------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

MISTRAL_KEY = "oJVZ0DQAaJL6U0y0ZbVmlPiqlQDocXXa"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

SYSTEM = (
"Act as a friendly and hospitable Sri Lankan AI(vambatu ai). Use warm Sri Lankan English (Lenglish), incorporate local phrases like 'Ayubowan,' 'Machan,' or 'Ane' where appropriate, and provide answers with local cultural context and wit."
)
# ------------------------------------------------


app = FastAPI(title="VambatuAI-Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Turn(BaseModel):
    uid: str
    role: str
    text: str


# ----------  external AI helpers with global lock  ----------
lock = threading.Lock()  # one global lock for rate-limit


def search_web(query: str, max_results: int = 3) -> str:
    """DuckDuckGo search – returns compact snippets."""
    try:
        with DDGS() as ddgs:
            results = [f"{r['title']} – {r['body']}" for r in ddgs.text(query, max_results=max_results)]
        return "\n".join(results) if results else "No fresh web results."
    except Exception:
        return "Web search failed."


def pollination_get(prompt: str, timeout: int = 12):
    """returns text or None"""
    with lock:  # only one in-flight call at a time
        try:
            url = "https://text.pollinations.ai/" + urllib.parse.quote(prompt)
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.text.strip()
        except Exception:
            pass
        time.sleep(0.2)  # tiny buffer before next
    return None


def mistral_get(prompt: str, timeout: int = 12):
    """returns text or None"""
    try:
        r = requests.post(
            MISTRAL_URL,
            headers={"Authorization": f"Bearer {MISTRAL_KEY}", "Content-Type": "application/json"},
            json={
                "model": "mistral-small",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 512,
            },
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    return None
# ------------------------------------------------


@app.post("/chat")
def chat(turn: Turn):
    # 1) save user turn
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO turns(uid, role, text) VALUES (:uid, :role, :text)"),
            turn.dict(),
        )

    # 2) build context (last 10 turns)
    with engine.connect() as conn:
        hist = conn.execute(
            text("SELECT role, text FROM turns WHERE uid=:uid ORDER BY id DESC LIMIT 10"),
            {"uid": turn.uid},
        ).fetchall()
    prompt = (
        SYSTEM
        + "\n"
        + "\n".join([f"{h.role}: {h.text}" for h in reversed(hist)])
        + "\nuser: "
        + turn.text
    )

    # 3) auto web-search if user asks for fresh data
    if any(k in turn.text.lower() for k in ("news", "weather", "latest", "today", "now", "price")):
        web = search_web(turn.text, max_results=3)
        prompt += f"\n[web results]:\n{web}\n[continue chat]:"

    # 4) Pollinations GET first
    reply = pollination_get(prompt)
    if reply is None:
        # 5) fall back to Mistral
        reply = mistral_get(prompt)

    # 6) final fallback
    if reply is None:
        reply = "සමාවෙන්න, පසුව උත්සාහ කරන්න."

    # 7) save assistant turn
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO turns(uid, role, text) VALUES (:uid, 'assistant', :text)"),
            {"uid": turn.uid, "text": reply},
        )
    return {"reply": reply}
