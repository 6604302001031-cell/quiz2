import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

app = Flask(__name__)

# 🔑 กำหนด Secret Key สำหรับใช้ระบบ Session (ตั้งเป็นข้อความยาวๆ เพื่อความปลอดภัย)
app.secret_key = 'quiz_game_secret_key_change_in_production'

# 🔑 นำ Google Client ID ที่คุณได้มาจาก Google Cloud Console มาใส่ที่นี่
GOOGLE_CLIENT_ID = "969552580845-5fkmba3g0jt9d8bkdllkp1vsnodmgg0k.apps.googleusercontent.com"

# 👑 ระบุอีเมลของคนที่จะให้สิทธิ์เป็น Admin (สามารถเพิ่มเข้าไปในลิสต์นี้ได้)
ADMIN_EMAILS = ["@student.sru.ac.th", "@sru.ac.th.com"]

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
    "current_index": 0,
    "is_time_up": False,
    "school_scores": {},   # คะแนนรวมโรงเรียน
    "player_scores": {},   # คะแนนแยกบุคคล
    "current_answers": {}  # พักคำตอบของข้อปัจจุบันเอาไว้ก่อน ยังไม่คิดคะแนนทันที
}

# ==========================================
# 🔐 ระบบคัดกรองสิทธิ์ด้วย GOOGLE LOGIN & SESSION
# ==========================================

@app.route('/')
def login_page():
    # ถ้าผู้ใช้งานเคยล็อกอินค้างไว้อยู่แล้ว ให้ส่งไปยังหน้าที่ถูกต้องทันทีโดยไม่ต้องล็อกอินซ้ำ
    if 'role' in session:
        if session['role'] == 'admin':
            return redirect(url_for('admin'))
        elif session['role'] == 'user':
            return redirect(url_for('user'))
    return render_template('login.html', client_id=GOOGLE_CLIENT_ID)

@app.route('/api/auth', methods=['POST'])
def google_auth():
    data = request.json or {}
    token = data.get('credential')
    if not token:
        return jsonify({'status': 'error', 'message': 'ไม่พบข้อมูล Token จาก Google'}), 400
        
    try:
        # ตรวจสอบความถูกต้องและความปลอดภัยของ Token โดยคุยกับเซิร์ฟเวอร์ Google
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo.get('email', '').strip().lower()
        name = idinfo.get('name', 'ผู้เล่น')
        
        # บันทึกข้อมูลพื้นฐานลงใน Session ของผู้ใช้รายนั้นๆ
        session['email'] = email
        session['name'] = name
        
        # จุดคัดกรอง: ตรวจสอบว่าอีเมลตรงกับรายชื่อแอดมินที่ตั้งไว้หรือไม่
        if email in [e.lower() for e in ADMIN_EMAILS]:
            session['role'] = 'admin'
            return jsonify({'status': 'success', 'redirect': '/admin'})
        else:
            session['role'] = 'user'
            return jsonify({'status': 'success', 'redirect': '/user'})
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Token ไม่ถูกต้องหรือหมดอายุการใช้งาน'}), 401

@app.route('/admin')
def admin():
    # เช็กสิทธิ์ว่าถ้าไม่ใช่ admin จริงๆ จะถูกเตะกลับไปหน้าแรก
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    return render_template('admin.html')

@app.route('/user')
def user():
    # เช็กสิทธิ์ว่าต้องเป็นผู้เล่นที่ผ่านการล็อกอินเข้ามาแล้วเท่านั้น
    if session.get('role') != 'user':
        return redirect(url_for('login_page'))
    return render_template('user.html')

@app.route('/logout')
def logout():
    session.clear()  # ล้างค่าจำเซสชันทั้งหมด
    return redirect(url_for('login_page'))  # ✨ แก้ไขจุดวงเล็บค้างที่ทำระบบพังเรียบร้อยครับ!

# ==========================================
# 🎮 ระบบควบคุมเกมและคำนวณคะแนน
# ==========================================

@app.route('/api/start', methods=['POST'])
def start_game():
    game_state["is_started"] = True
    return jsonify({"status": "success", "message": "Game has started!"})

@app.route('/api/state')
def get_state():
    idx = game_state["current_index"]
    is_end = idx >= len(questions)
    q_text = questions[idx]["q"] if not is_end else "จบเกมแล้ว!"
    
    return jsonify({
        "is_started": game_state["is_started"],
        "question": q_text,
        "is_end": is_end,
        "is_time_up": game_state["is_time_up"],
        "current_number": idx + 1 if not is_end else 15,
        "school_scores": game_state["school_scores"],
        "player_scores": game_state["player_scores"]
    })

@app.route('/api/submit', methods=['POST'])
def submit_answer():
    data = request.json
    school_name = data.get("school", "").strip()
    player_id = data.get("player_id", "")
    answer = data.get("answer", "").strip().lower()
    
    if not school_name:
        return jsonify({"status": "error", "message": "กรุณากรอกชื่อโรงเรียน"})
        
    idx = game_state["current_index"]
    if idx >= len(questions):
        return jsonify({"status": "game_over"})

    if school_name not in game_state["school_scores"]:
        game_state["school_scores"][school_name] = 0
    if school_name not in game_state["current_answers"]:
        game_state["current_answers"][school_name] = []

    # ป้องกันไม่ให้ผู้เล่นคนเดิมส่งคำตอบซ้ำซ้อนในข้อเดียวกัน
    already_submitted = any(item["player_id"] == player_id for item in game_state["current_answers"][school_name])
    if not already_submitted:
        game_state["current_answers"][school_name].append({
            "player_id": player_id,
            "answer": answer
        })
            
    return jsonify({"status": "success"})

@app.route('/api/timeout', methods=['POST'])
def timeout():
    if not game_state["is_time_up"]:
        game_state["is_time_up"] = True
        process_scores_for_current_question()
    return jsonify({"status": "success"})

@app.route('/api/next', methods=['POST'])
def next_question():
    if not game_state["is_time_up"]:
        process_scores_for_current_question()
        
    idx = game_state["current_index"]
    if idx < len(questions):
        game_state["current_index"] += 1
        game_state["is_time_up"] = False  
        game_state["current_answers"] = {}
        
    return jsonify({"status": "success"})

def process_scores_for_current_question():
    idx = game_state["current_index"]
    if idx >= len(questions):
        return
        
    correct_answer = questions[idx]["a"].lower()
    
    for school, answers_list in game_state["current_answers"].items():
        correct_count = 0
        
        for item in answers_list:
            if item["answer"] == correct_answer and item["answer"] != "":
                correct_count += 1
                pid = item["player_id"]
                game_state["player_scores"][pid] = game_state["player_scores"].get(pid, 0) + 1
        
        # กติกาคะแนนคิดตามขั้นบันได
        points_earned = 0
        if correct_count == 1:
            points_earned = 1
        elif correct_count == 2:
            points_earned = 3
        elif correct_count >= 3:
            points_earned = 5
            
        game_state["school_scores"][school] = game_state["school_scores"].get(school, 0) + points_earned

@app.route('/api/reset', methods=['POST'])
def reset_game():
    game_state["is_started"] = False
    game_state["current_index"] = 0
    game_state["is_time_up"] = False
    game_state["school_scores"] = {}
    game_state["player_scores"] = {}
    game_state["current_answers"] = {}
    return jsonify({"status": "success"})

if __name__ == '__main__':
    # เปิดเซิร์ฟเวอร์รันระบบ
    app.run(debug=True)
