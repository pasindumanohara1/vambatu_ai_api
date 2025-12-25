import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
app = FastAPI(title="Sinhala-Chat-API")

class Turn(BaseModel):
    uid: str
    role: str
    text: str

TEXT_MODELS = ["openai", "mistral", "searchgpt", "claude-hybridspace"]
SYSTEM_PROMPT = ("ඔබ ශ්‍රී ලාංකීය AI උපකාරකයෙකි. සිංහල, Singlish හෝ ඉංග්‍රීසි භාවිතා කරන්න. "
                 "කෙටියෙන්, උද්‍යානයෙන්, හා සාමාන්‍ය ලාංකීය උපමා දිය යුතුය.")

@app.post("/chat")
def chat(turn: Turn):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO turns(uid, role, text) VALUES (:uid, :role, :text)"), turn.dict())

    with engine.connect() as conn:
        hist = conn.execute(text("""
            SELECT role, text FROM turns WHERE uid = :uid ORDER BY id DESC LIMIT 10
        """), {"uid": turn.uid}).fetchall()
    prompt = "\n".join([f"{h.role}: {h.text}" for h in reversed(hist)])

    reply = None
    for model in TEXT_MODELS:
        try:
            r = requests.post("https://api.pollinations.ai/openai", json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 512
            }, timeout=18)
            if r.status_code == 200:
                reply = r.json()["choices"][0]["message"]["content"]
                break
        except Exception:
            continue

    if reply is None:
        reply = "සමාවෙන්න, මට දැන් පිළිතුරක් ලබා ගත නොහැක. කරුණාකර පසුව උත්සාහ කරන්න."

    with engine.begin() as conn:
        conn.execute(text("INSERT INTO turns(uid, role, text) VALUES (:uid, 'assistant', :text)"),
                     {"uid": turn.uid, "text": reply})
    return {"reply": reply}
