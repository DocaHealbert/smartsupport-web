# web_server.py
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import random  # Added for random agent assignment

app = Flask(__name__)
app.config['SECRET_KEY'] = 'smartsupport_secret'
socketio = SocketIO(app, max_http_buffer_size=10000000) # Support large audio files

# active_users = { username: { 'sid': request.sid, 'role': 'agent'/'customer' } }
active_users = {}

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('login')
def handle_login(data):
    username = data['username'].strip()
    role = data['role'] # Accepts 'agent' or 'customer'

    if not username:
        emit('system_msg', {'text': '❌ Username cannot be empty.'}, to=request.sid)
        return

    # Save session info and role
    active_users[username] = {'sid': request.sid, 'role': role}
    
    # Send success response back to client
    emit('login_response', {'success': True, 'username': username, 'role': role}, to=request.sid)
    print(f"[LOGIN] {username} logged in as {role.upper()}.")

@socketio.on('disconnect')
def handle_disconnect():
    user_to_remove = None
    # Find who disconnected based on their session ID
    for username, info in active_users.items():
        if info['sid'] == request.sid:
            user_to_remove = username
            break
            
    # Remove them from the active list
    if user_to_remove:
        del active_users[user_to_remove]
        print(f"[DISCONNECT] {user_to_remove} has left the system.")

@socketio.on('send_message')
def handle_message(data):
    sender = data['sender']
    target = data['target'].strip()
    text = data['text']

    # --- BOT AUTOMATION LOGIC ---
    if target.upper() == "BOT":
        # Check for escalation keywords
        if "agent" in text.lower() or "human" in text.lower() or "help" in text.lower():
            emit('receive_message', {'sender': 'BOT', 'text': '🤖 Connecting you to a human agent...'}, to=request.sid)
            
            # Find ALL online agents
            agent_list = [user for user, info in active_users.items() if info['role'] == 'agent']
            
            if agent_list:
                # OPTION A: Choose one agent randomly from the list
                target_agent = random.choice(agent_list)
                agent_sid = active_users[target_agent]['sid']
                
                # Notify the chosen agent
                emit('receive_message', {'sender': 'SYSTEM (Escalation)', 'text': f'Customer [{sender}] requested human assistance for: "{text}"'}, to=agent_sid)
                # Notify the customer
                emit('system_msg', {'text': f'🤖 BOT: You are now connected to {target_agent}. Please change your Target to: {target_agent}'}, to=request.sid)
            else:
                emit('receive_message', {'sender': 'BOT', 'text': '🤖 Sorry, no agents are currently available. Please try again later.'}, to=request.sid)
        else:
            # Standard Bot FAQ response
            emit('receive_message', {'sender': 'BOT', 'text': '🤖 Please contact us for operating hours or type "agent" to speak with a human mechanic.'}, to=request.sid)
        return

    # --- NORMAL CHAT (CUSTOMER <-> AGENT) ---
    target_info = active_users.get(target)
    if target_info:
        emit('receive_message', {'sender': sender, 'text': text}, to=target_info['sid'])
        emit('system_msg', {'text': f'Message sent to {target}.'}, to=request.sid)
    else:
        emit('system_msg', {'text': f'❌ User {target} is currently offline.'}, to=request.sid)

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

if __name__ == '__main__':
    print("[STARTING] SmartSupport Web Server running on http://127.0.0.1:5000")
    socketio.run(app, debug=True, port=5000)
