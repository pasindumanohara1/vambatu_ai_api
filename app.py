from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine, text
import requests, os

DATABASE_URL = os.getenv("DATABASE_URL")   # injected by Render
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

app = FastAPI(title="Sinhala-Chat-API")

class Turn(BaseModel):
    uid: str
    role: str
    text: str

@app.post("/chat")
def chat(turn: Turn):
    # 1) save user turn
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO turns(uid, role, text)
            VALUES (:uid, :role, :text)
        """), turn.dict())

    # 2) last 10 turns for context
    with engine.connect() as conn:
        hist = conn.execute(text("""
            SELECT role, text FROM turns
            WHERE uid = :uid
            ORDER BY id DESC LIMIT 10
        """), {"uid": turn.uid}).fetchall()
    prompt = "\n".join([f"{h.role}: {h.text}" for h in reversed(hist)])

    # 3) call Pollinations
    reply = requests.post(
        "https://api.pollinations.ai/openai",
        json={"model": "openai",
              "messages": [
                  {"role": "system",
                   "content": "ඔබ ශ්‍රී ලාංකීය AI උපකාරකයෙකි. සිංහලෙන් හෝ Singlish හෝ පිළිතුරු දෙන්න."},
                  {"role": "user", "content": prompt}
              ]},
        timeout=25
    ).json()["choices"][0]["message"]["content"]

    # 4) save assistant turn
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO turns(uid, role, text)
            VALUES (:uid, 'assistant', :text)
        """), {"uid": turn.uid, "text": reply})

    return {"reply": reply}

# health check
@app.get("/")
def root():
    return {"message": "Sinhala Chat API alive"}
