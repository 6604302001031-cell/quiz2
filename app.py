import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

app = Flask(__name__)

# 🔑 กำหนด Secret Key สำหรับใช้ระบบ Session (ตั้งเป็นข้อความยาวๆ เพื่อความปลอดภัย)
app.secret_key = 'quiz_game_secret_key_change_in_production'

# 🔑 นำ Google Client ID ที่คุณได้มาจาก Google Cloud Console มาใส่ที่นี่
GOOGLE_CLIENT_ID = "969552580845-5fkmba3g0jt9d8bkdllkp1vsnodmgg0k.apps.googleusercontent.com"

# ชุดคำถาม 15 ข้อ
questions = [
    {"q": "5 + 5 เท่ากับเท่าไร?", "a": "10"},
    {"q": "1 + 1 เท่ากับเท่าไร?", "a": "2"},
    {"q": "7 + 7 เท่ากับเท่าไร?", "a": "14"},
    {"q": "2 + 2 เท่ากับเท่าไร?", "a": "4"},
    {"q": "9 + 9 เท่ากับเท่าไร?", "a": "18"},
    {"q": "6 + 7 เท่ากับเท่าไร?", "a": "13"},
    {"q": "6 + 6 เท่ากับเท่าไร?", "a": "12"},
    {"q": "4 + 4 เท่ากับเท่าไร?", "a": "8"},
    {"q": "9 + 5 เท่ากับเท่าไร?", "a": "14"},   
    {"q": "8 + 8 เท่ากับเท่าไร?", "a": "16"},
    {"q": "3 + 3 เท่ากับเท่าไร?", "a": "6"},
    {"q": "5 + 4 เท่ากับเท่าไร?", "a": "9"},
    {"q": "10 + 10 เท่ากับเท่าไร?", "a": "20"},
    {"q": "0 + 1 เท่ากับเท่าไร?", "a": "1"},
    {"q": "7 + 3 เท่ากับเท่าไร?", "a": "10"}
]

# ตัวแปรสถานะการทำงานของระบบเกม
game_state = {
    "is_started": False,
    "is_end": False,       # เพิ่มสถานะเพื่อเช็กว่าจบการแข่งขันหรือยัง
    "current_index": 0,
    "is_time_up": False,
    "school_scores": {},   # คะแนนรวมโรงเรียน {"ชื่อโรงเรียน": คะแนน}
    "player_scores": {},   # คะแนนแยกบุคคล {"อีเมล": คะแนน}
    "current_answers": {}  # พักคำตอบของข้อปัจจุบันเอาไว้ก่อน {"อีเมล": {"answer": "คำตอบ", "school": "โรงเรียน", "name": "ชื่อ"}}
}

# ==========================================
# 🔐 ระบบคัดกรองสิทธิ์ด้วย GOOGLE LOGIN & SESSION
# ==========================================

@app.route('/')
def login_page():
    if 'role' in session:
        if session['role'] == 'admin':
            return redirect(url_for('admin'))
        elif session['role'] == 'user':
            if 'school' not in session:
                return redirect(url_for('select_school_page'))
            return redirect(url_for('user'))
    return render_template('login.html', client_id=GOOGLE_CLIENT_ID)

@app.route('/api/auth', methods=['POST'])
def google_auth():
    data = request.json or {}
    token = data.get('credential')
    if not token:
        return jsonify({'status': 'error', 'message': 'ไม่พบข้อมูล Token จาก Google'}), 400
        
    try:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo.get('email', '').strip().lower()
        name = idinfo.get('name', 'ผู้เล่น')
        
        session['email'] = email
        session['name'] = name
        
        if email.endswith('@student.sru.ac.th') or email.endswith('@sru.ac.th'):
            session['role'] = 'admin'
            return jsonify({'status': 'success', 'redirect': '/admin'})
        else:
            session['role'] = 'user'
            return jsonify({'status': 'success', 'redirect': '/select-school'})
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Token ไม่ถูกต้องหรือหมดอายุการใช้งาน'}), 401

@app.route('/select-school')
def select_school_page():
    if session.get('role') != 'user':
        return redirect(url_for('login_page'))
    return render_template('select_school.html')

@app.route('/api/save-school', methods=['POST'])
def save_school():
    if session.get('role') != 'user':
        return jsonify({'status': 'error', 'message': 'ไม่มีสิทธิ์การใช้งาน'}), 403
        
    data = request.json or {}
    school_name = data.get('school', '').strip()
    
    if not school_name:
        return jsonify({'status': 'error', 'message': 'กรุณากรอกชื่อโรงเรียน'}), 400
        
    session['school'] = school_name
    return jsonify({'status': 'success', 'redirect': '/user'})

@app.route('/admin')
def admin():
    if session.get('role') != 'admin':
        return redirect(url_for('login_page'))
    return render_template('admin.html')

@app.route('/user')
def user():
    if session.get('role') != 'user':
        return redirect(url_for('login_page'))
    if 'school' not in session:
        return redirect(url_for('select_school_page'))
        
    return render_template('user.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# ==========================================
# 🎮 ระบบควบคุมเกมและคำนวณคะแนน (ส่วนที่แก้ไขและต่อเติม)
# ==========================================

@app.route('/api/start', methods=['POST'])
def start_game():
    game_state["is_started"] = True
    game_state["is_end"] = False
    game_state["current_index"] = 0
    game_state["is_time_up"] = False
    game_state["current_answers"] = {}
    return jsonify({"status": "success", "message": "เริ่มเกมเรียบร้อยแล้ว!"})

@app.route('/api/state')
def get_state():
    # ตรวจสอบว่าคำถามหมดหรือยัง ถ้าหมดแล้วให้เปลี่ยนสถานะเป็นจบเกม (is_end = True)
    is_end = game_state["is_end"] or (game_state["current_index"] >= len(questions))
    
    current_q = ""
    if game_state["is_started"] and game_state["current_index"] < len(questions):
        current_q = questions[game_state["current_index"]]["q"]
        
    return jsonify({
        "is_started": game_state["is_started"],
        "is_time_up": game_state["is_time_up"],
        "is_end": is_end,
        "current_number": game_state["current_index"] + 1,
        "question": current_q,
        "school_scores": game_state["school_scores"]
    })

@app.route('/api/timeout', methods=['POST'])
def trigger_timeout():
    if not game_state["is_started"]:
        return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
        
    game_state["is_time_up"] = True
    
    # 🏆 ส่วนคำนวณตรวจคำตอบและแจกคะแนนเมื่อหมดเวลาข้อนั้นๆ
    current_idx = game_state["current_index"]
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        
        for email, player_data in game_state["current_answers"].items():
            # ดักจับเพื่อป้องกันไม่ให้คิดคะแนนซ้ำหากแอดมินกดปุ่มซ้ำ
            if player_data.get("evaluated", False):
                continue
                
            # ถ้าคำตอบที่ผู้เล่นส่งมา ตรงกับคำตอบที่ถูกต้อง
            if player_data["answer"].strip() == correct_answer.strip():
                school = player_data["school"]
                
                # เพิ่มคะแนนให้โรงเรียน (บวกข้อละ 1 คะแนน)
                game_state["school_scores"][school] = game_state["school_scores"].get(school, 0) + 1
                # เพิ่มคะแนนแยกตามรายบุคคล
                game_state["player_scores"][email] = game_state["player_scores"].get(email, 0) + 1
            
            player_data["evaluated"] = True
            
    return jsonify({"status": "success", "message": "หมดเวลาข้อนี้และคำนวณคะแนนแล้ว"})

@app.route('/api/next', methods=['POST'])
def next_question():
    if not game_state["is_started"]:
        return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
        
    game_state["current_index"] += 1
    game_state["is_time_up"] = False
    game_state["current_answers"] = {}  # เคลียร์กล่องรับคำตอบเพื่อเตรียมรับคำตอบข้อถัดไป
    
    if game_state["current_index"] >= len(questions):
        game_state["is_end"] = True
        
    return jsonify({"status": "success", "message": "เปลี่ยนเป็นข้อถัดไปเรียบร้อย"})

@app.route('/api/reset', methods=['POST'])
def reset_game():
    game_state["is_started"] = False
    game_state["is_end"] = False
    game_state["current_index"] = 0
    game_state["is_time_up"] = False
    game_state["school_scores"] = {}
    game_state["player_scores"] = {}
    game_state["current_answers"] = {}
    return jsonify({"status": "success", "message": "รีเซ็ตระบบเกมทั้งหมดเรียบร้อยแล้ว"})

# 📥 API เพิ่มเติมสำหรับฝั่งผู้เล่น (user.html) ส่งข้อมูลคำตอบเข้ามา
@app.route('/api/submit', methods=['POST'])
def submit_answer():
    if session.get('role') != 'user':
        return jsonify({'status': 'error', 'message': 'ไม่มีสิทธิ์ส่งคำตอบ'}), 403
        
    if not game_state["is_started"] or game_state["is_time_up"] or game_state["is_end"]:
        return jsonify({'status': 'error', 'message': 'ระบบไม่ได้เปิดรับคำตอบในขณะนี้'}), 400
        
    data = request.json or {}
    player_answer = data.get('answer', '').strip()
    
    email = session.get('email')
    school = session.get('school', 'ไม่ระบุโรงเรียน')
    name = session.get('name', 'ผู้เล่น')
    
    # บันทึกคำตอบส่งเข้าสู่กล่องพักคำตอบกลาง
    game_state["current_answers"][email] = {
        "answer": player_answer,
        "school": school,
        "name": name,
        "evaluated": False
    }
    
    return jsonify({'status': 'success', 'message': 'ส่งคำตอบสำเร็จ'})

# 📥 API ดึงคะแนนส่วนบุคคล (สำหรับโชว์บนหน้าจอฝั่งผู้เล่น)
@app.route('/api/my-score')
def get_my_score():
    email = session.get('email')
    score = game_state["player_scores"].get(email, 0)
    return jsonify({"score": score})

if __name__ == '__main__':
    app.run(debug=True)
