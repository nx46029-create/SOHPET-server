import os
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

# Aktif kullanıcılar: { "kullanici_adi": websocket }
online_users = {}
# Odalar: { "oda_adi": [websocket1, websocket2, ...] }
rooms = {}
MAX_USERS_PER_ROOM = 15

@app.get("/")
async def get():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

async def broadcast_state():
    room_info = {name: len(users) for name, users in rooms.items()}
    user_list = list(online_users.keys())
    payload = json.dumps({
        "type": "state_update",
        "rooms": room_info,
        "users": user_list
    })
    for ws in list(online_users.values()):
        try:
            await ws.send_text(payload)
        except:
            pass

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    username = None
    current_room = None

    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            action = data.get("action")

            # 1. GİRİŞ YAPMA
            if action == "login":
                req_user = data.get("username", "").strip()
                if not req_user:
                    continue
                if req_user in online_users:
                    await websocket.send_text(json.dumps({
                        "type": "login_error",
                        "message": "Bu kullanıcı adı şu an aktif! Başka bir isim seç."
                    }))
                    continue
                username = req_user
                online_users[username] = websocket
                await websocket.send_text(json.dumps({"type": "login_ok", "username": username}))
                await broadcast_state()

            # 2. ODA OLUŞTURMA VEYA KATILMA
            elif action == "join_room":
                room_name = data.get("room_name", "").strip()
                if not room_name:
                    continue

                is_new_room = room_name not in rooms
                if is_new_room:
                    rooms[room_name] = []

                if len(rooms[room_name]) >= MAX_USERS_PER_ROOM and websocket not in rooms[room_name]:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Bu oda dolu! (Maksimum 15 kişi)"
                    }))
                    continue

                # Önceki odadan çık
                if current_room and current_room in rooms and websocket in rooms[current_room]:
                    if current_room != room_name:
                        rooms[current_room].remove(websocket)
                        if len(rooms[current_room]) == 0:
                            del rooms[current_room]

                if websocket not in rooms[room_name]:
                    rooms[room_name].append(websocket)
                current_room = room_name

                await websocket.send_text(json.dumps({
                    "type": "joined_room",
                    "room_name": room_name,
                    "count": len(rooms[room_name])
                }))

                # Yeni oda kurulduysa herkese bildirim gönder
                if is_new_room:
                    notif = json.dumps({
                        "type": "room_created_notif",
                        "room_name": room_name,
                        "creator": username
                    })
                    for u_name, ws in online_users.items():
                        if u_name != username:
                            try:
                                await ws.send_text(notif)
                            except:
                                pass

                # Odaya katılım bilgisi
                join_msg = json.dumps({
                    "type": "room_system",
                    "room_name": room_name,
                    "message": f"{username} odaya katıldı.",
                    "count": len(rooms[room_name])
                })
                for ws in rooms[room_name]:
                    await ws.send_text(join_msg)

                await broadcast_state()

            # 3. ODA MESAJI GÖNDERME
            elif action == "room_message":
                room_name = data.get("room_name")
                text = data.get("text", "").strip()
                if room_name in rooms and text:
                    msg_payload = json.dumps({
                        "type": "room_chat",
                        "room_name": room_name,
                        "sender": username,
                        "text": text
                    })
                    for ws in rooms[room_name]:
                        await ws.send_text(msg_payload)

            # 4. ARKADAŞLIK İSTEĞİ / EKLEME BİLDİRİMİ
            elif action == "add_friend":
                target = data.get("target")
                if target in online_users and target != username:
                    await online_users[target].send_text(json.dumps({
                        "type": "friend_added_notif",
                        "from_user": username
                    }))

            # 5. ÖZEL MESAJ (ARKADAŞ SOHBETİ)
            elif action == "private_message":
                target = data.get("target")
                text = data.get("text", "").strip()
                if target in online_users and text:
                    payload = json.dumps({
                        "type": "private_chat",
                        "from_user": username,
                        "to_user": target,
                        "text": text
                    })
                    await online_users[target].send_text(payload)
                    await websocket.send_text(payload)

    except WebSocketDisconnect:
        if username and username in online_users:
            del online_users[username]
        if current_room and current_room in rooms and websocket in rooms[current_room]:
            rooms[current_room].remove(websocket)
            if len(rooms[current_room]) == 0:
                del rooms[current_room]
            else:
                leave_msg = json.dumps({
                    "type": "room_system",
                    "room_name": current_room,
                    "message": f"{username} ayrıldı.",
                    "count": len(rooms[current_room])
                })
                for ws in rooms[current_room]:
                    await ws.send_text(leave_msg)
        await broadcast_state()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
