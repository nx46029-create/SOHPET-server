import os
import time
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bellek içi canlı veriler
users_last_seen = {}      # { "kullanici": timestamp }
rooms = {}                # { "oda_adi": ["user1", "user2"] }
events = []               # Tüm canlı olaylar listesi
MAX_USERS_PER_ROOM = 15

class LoginReq(BaseModel):
    username: str

class ActionReq(BaseModel):
    username: str
    action: str
    room_name: str = ""
    target: str = ""
    text: str = ""

def clean_inactive():
    now = time.time()
    dead = [u for u, t in users_last_seen.items() if now - t > 25]
    for u in dead:
        del users_last_seen[u]
        for r_name in list(rooms.keys()):
            if u in rooms[r_name]:
                rooms[r_name].remove(u)
                events.append({"id": len(events) + 1, "type": "room_system", "room_name": r_name, "message": f"{u} ayrıldı."})
                if len(rooms[r_name]) == 0:
                    del rooms[r_name]

@app.get("/")
async def home():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return {"status": "online"}

@app.post("/api/login")
async def api_login(req: LoginReq):
    clean_inactive()
    user = req.username.strip()
    if not user:
        return {"ok": False, "message": "Kullanıcı adı boş olamaz."}
    if user in users_last_seen:
        return {"ok": False, "message": "Bu kullanıcı adı şu an aktif! Başka isim seç."}
    users_last_seen[user] = time.time()
    return {"ok": True, "username": user, "last_id": len(events)}

@app.post("/api/action")
async def api_action(req: ActionReq):
    clean_inactive()
    user = req.username.strip()
    users_last_seen[user] = time.time()

    if req.action == "join_room":
        r_name = req.room_name.strip()
        if not r_name:
            return {"ok": False, "message": "Oda adı boş olamaz."}
        is_new = r_name not in rooms
        if is_new:
            rooms[r_name] = []
        if len(rooms[r_name]) >= MAX_USERS_PER_ROOM and user not in rooms[r_name]:
            return {"ok": False, "message": "Bu oda dolu! (Max 15 kişi)"}

        # Eski odalardan çıkar
        for old_r in list(rooms.keys()):
            if old_r != r_name and user in rooms[old_r]:
                rooms[old_r].remove(user)
                if len(rooms[old_r]) == 0:
                    del rooms[old_r]

        if user not in rooms[r_name]:
            rooms[r_name].append(user)
            events.append({"id": len(events) + 1, "type": "room_system", "room_name": r_name, "message": f"{user} odaya katıldı."})

        if is_new:
            events.append({"id": len(events) + 1, "type": "room_created_notif", "room_name": r_name, "creator": user})

        return {"ok": True, "room_name": r_name, "count": len(rooms[r_name])}

    elif req.action == "room_message":
        r_name = req.room_name.strip()
        if r_name in rooms and req.text.strip():
            events.append({"id": len(events) + 1, "type": "room_chat", "room_name": r_name, "sender": user, "text": req.text.strip()})
        return {"ok": True}

    elif req.action == "add_friend":
        if req.target:
            events.append({"id": len(events) + 1, "type": "friend_added_notif", "from_user": user, "to_user": req.target})
        return {"ok": True}

    elif req.action == "private_message":
        if req.target and req.text.strip():
            events.append({"id": len(events) + 1, "type": "private_chat", "from_user": user, "to_user": req.target, "text": req.text.strip()})
        return {"ok": True}

    return {"ok": True}

@app.get("/api/poll")
async def api_poll(username: str, last_id: int = 0):
    clean_inactive()
    if username:
        users_last_seen[username] = time.time()
    new_events = [e for e in events if e["id"] > last_id]
    room_counts = {name: len(members) for name, members in rooms.items()}
    return {
        "ok": True,
        "events": new_events,
        "last_id": events[-1]["id"] if events else last_id,
        "rooms": room_counts,
        "users": list(users_last_seen.keys())
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
