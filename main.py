import os
import asyncio
import json
from datetime import datetime
from typing import Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import hashlib
import secrets

from database import db, create_document

app = FastAPI(title="Nebula Trips API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple password hashing using scrypt from Python stdlib
# Returns (salt_hex, hash_hex)

def hash_password(password: str, salt_hex: str | None = None) -> Tuple[str, str]:
    if salt_hex is None:
        salt = secrets.token_bytes(16)
    else:
        salt = bytes.fromhex(salt_hex)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return salt.hex(), key.hex()


# Schemas
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


@app.get("/")
def root():
    return {"ok": True, "name": "Nebula Trips API"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# Auth endpoints
@app.post("/auth/register")
async def register(req: RegisterRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    existing = db["authuser"].find_one({"email": req.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    salt_hex, hash_hex = hash_password(req.password)
    doc = {
        "email": req.email,
        "password_salt": salt_hex,
        "password_hash": hash_hex,
        "provider": "email",
    }
    _id = create_document("authuser", doc)
    return {"id": _id, "email": req.email}


@app.get("/auth/google")
async def google_demo():
    # Demo endpoint simulating Google sign-in success
    return {"provider": "google", "status": "ok", "user": {"email": "demo@nebula.trips"}}


# Realtime deals via WebSocket
async def deals_streamer(websocket: WebSocket):
    await websocket.accept()
    cities = [
        ("NYC", "Paris"), ("Tokyo", "Seoul"), ("Berlin", "Rome"), ("SF", "Honolulu"), ("Dubai", "Sydney"), ("LA", "Mexico City")
    ]
    try:
        while True:
            dep, arr = cities[int(datetime.utcnow().timestamp()) % len(cities)]
            price = 199 + (int(datetime.utcnow().timestamp()) % 500)
            payload = {"route": f"{dep} → {arr}", "destination": arr, "price": price}
            await websocket.send_text(json.dumps({"type": "deal", "payload": payload}))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return


@app.websocket("/realtime/deals")
async def realtime_deals(websocket: WebSocket):
    await deals_streamer(websocket)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
