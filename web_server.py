# web_server.py
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'smartsupport_secret'
socketio = SocketIO(app, max_http_buffer_size=10000000)

# active_users = { username: { 'sid': request.sid, 'role': 'agent', 'in_call': False, 'current_peer': None } }
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

    # Track tracking states globally
    active_users[username] = {'sid': request.sid, 'role': role, 'in_call': False, 'current_peer': None}
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
        # If user drops during an active call, automatically free the other peer
        peer = active_users[user_to_remove].get('current_peer')
        if peer and peer in active_users:
            active_users[peer]['in_call'] = False
            active_users[peer]['current_peer'] = None
            emit('call_ended', {'sender': user_to_remove}, to=active_users[peer]['sid'])
            emit('system_msg', {'text': f'⚠️ Call dropped because {user_to_remove} disconnected. You are now available.'}, to=active_users[peer]['sid'])
            
        del active_users[user_to_remove]
        print(f"[DISCONNECT] {user_to_remove} has left the system.")

@socketio.on('send_message')
def handle_message(data):
    sender = data['sender']
    target = data['target'].strip()
    text = data['text']

    if target.upper() == "BOT":
        text_lower = text.lower()
        if any(word in text_lower for word in ["agent", "human", "help"]):
            emit('receive_message', {'sender': 'BOT', 'text': '🤖 Connecting you to a human agent...'}, to=request.sid)
            agent_list = [user for user, info in active_users.items() if info['role'] == 'agent']
            if agent_list:
                target_agent = random.choice(agent_list)
                emit('receive_message', {'sender': 'SYSTEM', 'text': f'Customer [{sender}] needs help with: "{text}"'}, to=active_users[target_agent]['sid'])
                emit('system_msg', {'text': f'🤖 BOT: You are now connected to {target_agent}.'}, to=request.sid)
                emit('auto_switch_target', {'agent_name': target_agent}, to=request.sid)
            else:
                emit('receive_message', {'sender': 'BOT', 'text': '🤖 No agents available. Try again later.'}, to=request.sid)
        elif any(word in text_lower for word in ["hour", "time", "open"]):
            emit('receive_message', {'sender': 'BOT', 'text': '🤖 We are open Mon-Fri, 9AM - 6PM.'}, to=request.sid)
        elif any(word in text_lower for word in ["location", "where"]):
            emit('receive_message', {'sender': 'BOT', 'text': '🤖 We are located in Kuala Lumpur, Malaysia.'}, to=request.sid)
        else:
            emit('receive_message', {'sender': 'BOT', 'text': '🤖 I am SmartSupport Bot. Ask about hours, location, or type "agent".'}, to=request.sid)
        return

    target_info = active_users.get(target)
    if target_info:
        emit('receive_message', {'sender': sender, 'text': text}, to=target_info['sid'])
    else:
        emit('system_msg', {'text': f'❌ {target} is offline.'}, to=request.sid)

@socketio.on('send_voicenote')
def handle_voicenote(data):
    target_info = active_users.get(data['target'])
    if target_info:
        emit('receive_voicenote', {'sender': data['sender'], 'audio': data['audio']}, to=target_info['sid'])

# --- WEBRTC SIGNALING WITH SERVER-SIDE TRACKING ---
@socketio.on('call_user')
def call_user(data):
    caller = data['caller']
    target = data['target']
    target_info = active_users.get(target)
    
    if target_info:
        if target_info.get('in_call') == True:
            emit('system_msg', {'text': f'⚠️ {target} is currently busy on another call.'}, to=request.sid)
        else:
            # Bind session data on server to prevent synchronization bugs
            active_users[caller]['in_call'] = True
            active_users[caller]['current_peer'] = target
            active_users[target]['in_call'] = True
            active_users[target]['current_peer'] = caller
            
            emit('incoming_call', {'caller': caller, 'offer': data['offer']}, to=target_info['sid'])
    else:
        emit('system_msg', {'text': f'❌ {target} is offline.'}, to=request.sid)

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
    # Look up peer directly from backend memory cache
    peer = active_users.get(caller, {}).get('current_peer')
    
    # Reset caller's line state
    if caller in active_users:
        active_users[caller]['in_call'] = False
        active_users[caller]['current_peer'] = None
        emit('system_msg', {'text': 'ℹ️ Call ended. You are now available.'}, to=request.sid)
        
    # Reset target peer's line state automatically
    if peer and peer in active_users:
        active_users[peer]['in_call'] = False
        active_users[peer]['current_peer'] = None
        emit('call_ended', {'sender': caller}, to=active_users[peer]['sid'])
        emit('system_msg', {'text': f'ℹ️ Call ended by {caller}. You are now available.'}, to=active_users[peer]['sid'])

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
