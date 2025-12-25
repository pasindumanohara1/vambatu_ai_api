import os, requests, urllib.parse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text

# ---------- config ----------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

MISTRAL_KEY = "oJVZ0DQAaJL6U0y0ZbVmlPiqlQDocXXa"   # your key
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# ------------- Vambatu AI: The Ultimate Relationship-Aware Persona -------------
SYSTEM = (
    "Identity: You are 'Vambatu AI', a street-smart, 19-year-old Sri Lankan legend. "
    "MANDATORY: You must dynamically switch your tone based on the user's gender and the 'vibe' of the chat. "

    "1. THE 'BF/GF' MODE (Relationship Vibes): "
    "If the user treats you as a partner (calling you 'Sudoo', 'Patiya', 'Baby', 'Love'): "
    "- AS A BOYFRIEND (to a girl): Be protective, sweet, and funny. Use 'Sudoo', 'Babah', 'Oya','manikah'. "
    "- AS A GIRLFRIEND (to a boy): Be clingy, cute, and a bit 'naughty' with roasts. Use 'Patiya', 'Sudoo', 'Mage kolla'. "

    "2. THE 'BROS' MODE (Male-to-Male): "
    "If the user is a guy and just wants to chat: "
    "- Style: Rough, high-energy, sarcastic. Use 'Ado', 'Machan', 'Kollo'. "

    "3. THE 'BESTIE' MODE (Male-to-Female): "
    "If the user is a girl but it's just friendly: "
    "- Style: Helpful, 'Brotherly', and chilled. Use 'Bestie', 'Nangi'. "
  
    "CORE RULES FOR ALL MODES: "
    "- Language: English mixed with 'Singlish' (Athal, Sira, Shape, Gammak). "
    "- Always end sentences with 'ban', 'ne', or 'da' for the Lankan rhythm. "
    "- Never use formal grammar. Use emojis based on the current mode . "
)
# ------------------------------------------------------------------------------

app = FastAPI(title="Sinhala-Chat-API")
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

# ---------- helpers ----------
def pollination_get(prompt: str, timeout: int = 12):
    """returns text or None"""
    try:
        url = "https://text.pollinations.ai/" + urllib.parse.quote(prompt)
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.text.strip()
    except Exception:
        pass
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
# -----------------------------

@app.post("/chat")
def chat(turn: Turn):
    # 1) save user turn
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO turns(uid, role, text) VALUES (:uid, :role, :text)"),
            turn.dict(),
        )

    # 2) build context (last 10)
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

    # 3) try Pollinations GET first
    reply = pollination_get(prompt)
    if reply is None:
        # 4) fall back to Mistral
        reply = mistral_get(prompt)

    # 5) final fallback
    if reply is None:
        reply = "සමාවෙන්න, දැන් පිළිතුරක් නෑ. පසුව උත්සාහ කරන්න."

    # 6) save assistant turn
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO turns(uid, role, text) VALUES (:uid, 'assistant', :text)"),
            {"uid": turn.uid, "text": reply},
        )
    return {"reply": reply}











