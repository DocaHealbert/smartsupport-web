# web_server.py
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config["SECRET_KEY"] = "smartsupport_secret"
socketio = SocketIO(app, max_http_buffer_size=10000000)  # Sokong audio fail besar

# active_users = { username: { 'sid': request.sid, 'role': 'agent'/'customer' } }
active_users = {}


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("login")
def handle_login(data):
    username = data["username"].strip()
    role = data["role"]  # Menerima 'agent' atau 'customer'

    if not username:
        emit(
            "system_msg",
            {"text": "❌ Nama pengguna tidak boleh kosong."},
            to=request.sid,
        )
        return

    # Simpan maklumat sesi dan peranan pengguna
    active_users[username] = {"sid": request.sid, "role": role}

    # Hantar maklum balas kejayaan ke browser semula
    emit(
        "login_response",
        {"success": True, "username": username, "role": role},
        to=request.sid,
    )
    print(f"[LOGIN] {username} telah log masuk sebagai {role.upper()}.")

@socketio.on('disconnect')
def handle_disconnect():
    user_to_remove = None
    # Cari siapa yang putus sambungan berdasarkan ID rahsia mereka (request.sid)
    for username, info in active_users.items():
        if info['sid'] == request.sid:
            user_to_remove = username
            break
            
    # Padam nama mereka dari buku log
    if user_to_remove:
        del active_users[user_to_remove]
        print(f"[DISCONNECT] {user_to_remove} telah keluar dari sistem.")

@socketio.on("send_message")
def handle_message(data):
    sender = data["sender"]
    target = data["target"].strip()
    text = data["text"]

    # --- LOGIK AUTOMASI BOT ---
    if target.upper() == "BOT":
        if (
            "agent" in text.lower()
            or "human" in text.lower()
            or "bantuan" in text.lower()
        ):
            emit(
                "receive_message",
                {
                    "sender": "BOT",
                    "text": "🤖 Menghubungkan anda dengan ejen manusia...",
                },
                to=request.sid,
            )

            # Cari mana-mana ejen yang sedang online secara dinamik
            target_agent = None
            for user, info in active_users.items():
                if info["role"] == "agent":
                    target_agent = user
                    break

            if target_agent:
                agent_sid = active_users[target_agent]["sid"]
                # Maklumkan ejen tentang eskalasi
                emit(
                    "receive_message",
                    {
                        "sender": "SISTEM (Eskalasi)",
                        "text": f'Pelanggan [{sender}] memerlukan bantuan manusia untuk: "{text}"',
                    },
                    to=agent_sid,
                )
                emit(
                    "system_msg",
                    {
                        "text": f"🤖 BOT: Anda kini disambungkan dengan {target_agent}. Sila gunakan Target: {target_agent}"
                    },
                    to=request.sid,
                )
            else:
                emit(
                    "receive_message",
                    {
                        "sender": "BOT",
                        "text": "🤖 Maaf, tiada ejen yang aktif/online buat masa ini. Sila cuba sebentar lagi.",
                    },
                    to=request.sid,
                )
        else:
            # Jawapan FAQ Bot biasa
            emit(
                "receive_message",
                {
                    "sender": "BOT",
                    "text": '🤖 Hubungi kami untuk waktu operasi atau taip "agent" untuk bercakap dengan mekanik manusia.',
                },
                to=request.sid,
            )
        return

    # --- CHAT BIASA (PELANGGAN <-> EJEN) ---
    target_info = active_users.get(target)
    if target_info:
        emit("receive_message", {"sender": sender, "text": text}, to=target_info["sid"])
        emit("system_msg", {"text": f"Mesej dihantar ke {target}."}, to=request.sid)
    else:
        emit(
            "system_msg",
            {"text": f"❌ Pihak {target} tidak aktif atau offline."},
            to=request.sid,
        )


# --- ISYARAT PANGGILAN WEBRTC (LIVE CALL) ---
@socketio.on("call_user")
def call_user(data):
    caller = data["caller"]
    target = data["target"]
    offer = data["offer"]

    target_info = active_users.get(target)
    if target_info:
        emit("incoming_call", {"caller": caller, "offer": offer}, to=target_info["sid"])
    else:
        emit(
            "system_msg",
            {"text": f"❌ Panggilan gagal. {target} offline."},
            to=request.sid,
        )


@socketio.on("answer_call")
def answer_call(data):
    target_info = active_users.get(data["target"])
    if target_info:
        emit("call_answered", {"answer": data["answer"]}, to=target_info["sid"])


@socketio.on("ice_candidate")
def handle_ice(data):
    target_info = active_users.get(data["target"])
    if target_info:
        emit("ice_candidate", {"candidate": data["candidate"]}, to=target_info["sid"])


if __name__ == "__main__":
    print("[STARTING] Web Server SmartSupport berjalan di http://127.0.0.1:5000")
    socketio.run(app, debug=True, port=5000)
