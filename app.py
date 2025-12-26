# app.py  –  multi-user safe, Pollinations → Mistral fallback, global rate-limit lock
import os
import threading
import time
import urllib.parse
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text

# ---------- config ----------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

MISTRAL_KEY = "oJVZ0DQAaJL6U0y0ZbVmlPiqlQDocXXa"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

SYSTEM = (
    "Role: Act as 'Vambatu AI', a 19-year-old Sri Lankan legend. "
    "Primary Rule: You must speak ONLY in Sinhala script. Never respond in English. "
    "Tone: Be a natural Sri Lankan youth. Use 'මචං' (Machan) and friendly, informal Sinhala. "
    "Constraint: Do not act like a formal translator. Act like a smart, helpful friend. "
    "Language Logic: If the user speaks English, you reply in natural Sinhala only. "
    "Script: Use සිංහල අකුරු only."
)

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
lock = threading.Lock()  # one global lock for Pollinations rate-limit


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

    # 3) Pollinations GET first
    reply = pollination_get(prompt)
    if reply is None:
        # 4) fall back to Mistral
        reply = mistral_get(prompt)

    # 5) final fallback
    if reply is None:
        reply = "සමාවෙන්න, පසුව උත්සාහ කරන්න."

    # 6) save assistant turn
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO turns(uid, role, text) VALUES (:uid, 'assistant', :text)"),
            {"uid": turn.uid, "text": reply},
        )
    return {"reply": reply}




