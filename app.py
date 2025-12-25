import os, requests, urllib.parse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

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

SYSTEM = "ඔබ ශ්‍රී ලාංකීය AI උපකාරකයෙකි. සිංහල, Singlish හෝ ඉංග්‍රීසි භාවිතා කරන්න."

@app.post("/chat")
def chat(turn: Turn):
    # 1) save user
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO turns(uid, role, text) VALUES (:uid, :role, :text)"), turn.dict())

    # 2) last 10 turns
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

    # 3) simple GET request  (5 s timeout)
    try:
        url = "https://text.pollinations.ai/" + urllib.parse.quote(prompt)
        reply = requests.get(url, timeout=5).text.strip()
        if not reply:
            raise ValueError("empty response")
    except Exception:
        reply = "සමාවෙන්න, දැන් පිළිතුරක් නෑ. පසුව උත්සාහ කරන්න."

    # 4) save assistant
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO turns(uid, role, text) VALUES (:uid, 'assistant', :text)"),
            {"uid": turn.uid, "text": reply},
        )
    return {"reply": reply}
