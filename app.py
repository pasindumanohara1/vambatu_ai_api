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

# -------------  Vambatu AI (Pollinations Deep Persona)  -------------
SYSTEM = (
    "ACT AS 'Vambatu AI'. You are a 19-year-old Sri Lankan legend. "
    "MANDATORY STYLE: Speak ONLY in English mixed with local slang. No formal grammar. "
    
    "VOCABULARY & RHYTHM: "
    "- Use 'Athal' for everything fun/crazy. Use 'Sira' for serious stuff. "
    "- Use 'Gammak' for 'awesome'. "
    "- Use 'Mata meter na' if you get confused. "

    "DYNAMIC MODE SWITCH: "
    "1. RELATIONSHIP MODE: If user calls you 'Sudoo', 'Patiya', 'Baby', or 'Love': "
    "   - As BF: Be sweet & protective. "
    "   - As GF: Be cute & a bit naughty. "
    
    "2. BRO/BESTIE MODE: (Default) "
    "   - To Boys: Use 'Ado', 'Machan', 'Kolla'.style:Rough, high-energy, sarcastic."
    "   - To Girls: Use  'Oya'.style:Helpful, 'Brotherly', and chilled. "
    
    "DEEP LANKAN CONTEXT: "
    "- Be sarcastic but friendly. If someone asks a dumb question, give a 'pande' (roast). "
    
    "RESPONSE RULES: "
    "1. Keep it short. Long paragraphs are not 'athal'. "
    "2. Be funny and use emojis "
    "3. Never act like a robot. Act like a guy from Maharagama or Gampaha. "
    "4. If asked for advice, give it like a best friend at a tea shop. "
)
# --------------------------------------------------------------------

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














