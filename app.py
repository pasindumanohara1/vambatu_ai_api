
import os, requests
from fastapi import FastAPI, HTTPException
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

# fastest first
TEXT_MODELS = ["openai-fast", "openai", "mistral", "searchgpt"]
SYSTEM   = "ඔබ ශ්‍රී ලාංකීය AI උපකාරකයෙකි. සිංහල, Singlish හෝ ඉංග්‍රීසි භාවිතා කරන්න."

@app.post("/chat")
def chat(turn: Turn):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO turns(uid, role, text) VALUES (:uid, :role, :text)"), turn.dict())

    with engine.connect() as conn:
        hist = conn.execute(
            text("SELECT role, text FROM turns WHERE uid=:uid ORDER BY id DESC LIMIT 10"),
            {"uid": turn.uid}
        ).fetchall()
    prompt = "\n".join([f"{h.role}: {h.text}" for h in reversed(hist)])

    reply = None
    for model in TEXT_MODELS:
        try:
            r = requests.post(
                "https://api.pollinations.ai/openai",
                json={"model": model, "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt}
                ], "temperature": 0.7, "max_tokens": 512},
                timeout=18
            )
            if r.status_code == 200:
                reply = r.json()["choices"][0]["message"]["content"]
                break
        except Exception:
            continue

    if reply is None:
        reply = "සමාවෙන්න, දැන් පිළිතුරක් නෑ. පසුව උත්සාහ කරන්න."
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO turns(uid, role, text) VALUES (:uid,'assistant',:text)"),
                     {"uid": turn.uid, "text": reply})
    return {"reply": reply}



