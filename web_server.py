# web_server.py
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'smartsupport_secret'
socketio = SocketIO(app, max_http_buffer_size=10000000)

active_users = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('login')
def handle_login(data):
    username = data['username'].strip()
    role = data['role']

    if not username:
        emit('system_msg', {'text': '❌ Username cannot be empty.'}, to=request.sid)
        return

    active_users[username] = {'sid': request.sid, 'role': role}
    emit('login_response', {'success': True, 'username': username, 'role': role}, to=request.sid)
    print(f"[LOGIN] {username} logged in as {role.upper()}.")

@socketio.on('disconnect')
def handle_disconnect():
    user_to_remove = None
    for username, info in active_users.items():
        if info['sid'] == request.sid:
            user_to_remove = username
            break
            
    if user_to_remove:
        del active_users[user_to_remove]
        print(f"[DISCONNECT] {user_to_remove} has left the system.")

@socketio.on('send_message')
def handle_message(data):
    sender = data['sender']
    target = data['target'].strip()
    text = data['text']

    if target.upper() == "BOT":
        if "agent" in text.lower() or "human" in text.lower() or "help" in text.lower():
            emit('receive_message', {'sender': 'BOT', 'text': '🤖 Connecting you to a human agent...'}, to=request.sid)
            agent_list = [user for user, info in active_users.items() if info['role'] == 'agent']
            
            if agent_list:
                target_agent = random.choice(agent_list)
                agent_sid = active_users[target_agent]['sid']
                emit('receive_message', {'sender': 'SYSTEM (Escalation)', 'text': f'Customer [{sender}] requested human assistance for: "{text}"'}, to=agent_sid)
                emit('system_msg', {'text': f'🤖 BOT: You are now connected to {target_agent}. Please change your Target to: {target_agent}'}, to=request.sid)
            else:
                emit('receive_message', {'sender': 'BOT', 'text': '🤖 Sorry, no agents are currently available. Please try again later.'}, to=request.sid)
        else:
            emit('receive_message', {'sender': 'BOT', 'text': '🤖 Please contact us for operating hours or type "agent" to speak with a human mechanic.'}, to=request.sid)
        return

    target_info = active_users.get(target)
    if target_info:
        emit('receive_message', {'sender': sender, 'text': text}, to=target_info['sid'])
        emit('system_msg', {'text': f'Message sent to {target}.'}, to=request.sid)
    else:
        emit('system_msg', {'text': f'❌ User {target} is currently offline.'}, to=request.sid)

# --- VOICE NOTE FUNCTION ---
@socketio.on('send_voicenote')
def handle_voicenote(data):
    sender = data['sender']
    target = data['target']
    audio_data = data['audio']

    target_info = active_users.get(target)
    if target_info:
        emit('receive_voicenote', {'sender': sender, 'audio': audio_data}, to=target_info['sid'])
        emit('system_msg', {'text': f'✅ Voice Note sent to {target}.'}, to=request.sid)
    else:
        emit('system_msg', {'text': f'❌ User {target} is offline. Voice Note failed.'}, to=request.sid)

# --- WEBRTC SIGNALING (LIVE CALL) ---
@socketio.on('call_user')
def call_user(data):
    caller = data['caller']
    target = data['target']
    offer = data['offer']
    
    target_info = active_users.get(target)
    if target_info:
        emit('incoming_call', {'caller': caller, 'offer': offer}, to=target_info['sid'])
    else:
        emit('system_msg', {'text': f'❌ Call failed. {target} is offline.'}, to=request.sid)

@socketio.on('answer_call')
def answer_call(data):
    target_info = active_users.get(data['target'])
    if target_info:
        emit('call_answered', {'answer': data['answer']}, to=target_info['sid'])

@socketio.on('ice_candidate')
def handle_ice(data):
    target_info = active_users.get(data['target'])
    if target_info:
        emit('ice_candidate', {'candidate': data['candidate']}, to=target_info['sid'])

@socketio.on('end_call')
def end_call(data):
    caller = data['caller']
    target = data['target']
    target_info = active_users.get(target)
    if target_info:
        emit('call_ended', {'sender': caller}, to=target_info['sid'])

if __name__ == '__main__':
    print("[STARTING] SmartSupport Web Server running on http://127.0.0.1:5000")
    socketio.run(app, debug=True, port=5000)
