import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

app = Flask(__name__)

# 🔑 กำหนด Secret Key สำหรับใช้ระบบ Session
app.secret_key = 'quiz_game_secret_key_change_in_production'

# 🔑 Google Client ID
GOOGLE_CLIENT_ID = "969552580845-5fkmba3g0jt9d8bkdllkp1vsnodmgg0k.apps.googleusercontent.com"

# 📝 ชุดคำถาม 15 ข้อ (เติมเต็มให้ครบถ้วน)
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
    {"q": "12 + 12 เท่ากับเท่าไร?", "a": "24"},
    {"q": "15 + 15 เท่ากับเท่าไร?", "a": "30"}
]

# 📊 ตัวแปรเก็บสถานะเกม (In-Memory Database)
game_state = {
    "is_started": False,
    "is_end": False,
    "current_index": 0,
    "is_time_up": False,
    "school_scores": {},  # เก็บข้อมูลคะแนนทีม/ชื่อผู้เล่น เพื่อโชว์หน้า Admin
    "player_scores": {},  # เก็บข้อมูลคะแนนแยกตาม Email เพื่อโชว์หน้า User
    "current_answers": {} # เก็บคำตอบของผู้เล่นในข้อนั้นๆ
}

# 🌟 ฟังก์ชันช่วยตรวจคำตอบ (แปลงเป็นพิมพ์เล็ก และตัดช่องว่างทิ้งทั้งหมด ป้องกันการกด spacebar เกิน)
def is_correct(ans1, ans2):
    return str(ans1).replace(" ", "").lower() == str(ans2).replace(" ", "").lower()


# ==========================================
# 🏠 เส้นทางหลัก (Routing Pages)
# ==========================================

@app.route('/')
def index():
    # ถ้ายังไม่ได้ล็อกอิน ให้ไปหน้า Login
    if 'role' not in session:
        return redirect(url_for('login_page'))
    
    # ถ้าเป็น Admin ให้ไปหน้าแอดมิน ถ้าเป็น User ให้ไปหน้าตอบคำถาม
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    return render_template('user.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/admin')
def admin_dashboard():
    # ตรวจสอบสิทธิ์แอดมินก่อนเข้าหน้าแผงควบคุม
    if session.get('role') != 'admin':
        return "สิทธิ์การเข้าถึงถูกปฏิเสธ", 403
    return render_template('admin.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


# ==========================================
# 🔐 ระบบยืนยันตัวตน (Authentication)
# ==========================================

@app.route('/api/google-login', methods=['POST'])
def google_login():
    data = request.json or {}
    token = data.get('token')
    
    if not token:
        return jsonify({"status": "error", "message": "ไม่พบ Token"}), 400
        
    try:
        # ตรวจสอบ Token กับเซิร์ฟเวอร์ของ Google
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        
        # ดึงข้อมูลผู้เล่น
        email = idinfo.get('email')
        name = idinfo.get('name')
        
        # ตั้งค่า Session
        session['role'] = 'user'
        session['email'] = email
        session['name'] = name
        
        return jsonify({"status": "success", "message": "ล็อกอินสำเร็จ"})
    except ValueError:
        return jsonify({"status": "error", "message": "Token ไม่ถูกต้องหรือหมดอายุ"}), 400


# ==========================================
# 🎮 ระบบควบคุมเกมและคำนวณคะแนน (API)
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
        "school_scores": game_state["school_scores"] # ส่งกลับไปให้ตาราง Admin อัปเดตคะแนนทีม
    })

@app.route('/api/timeout', methods=['POST'])
def trigger_timeout():
    if not game_state["is_started"]:
        return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
        
    game_state["is_time_up"] = True
    current_idx = game_state["current_index"]
    
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        for email, player_data in game_state["current_answers"].items():
            if player_data.get("evaluated", False):
                continue
                
            # ตรวจคำตอบตอนกดหมดเวลา
            if is_correct(player_data["answer"], correct_answer):
                school = player_data["school"]
                game_state["school_scores"][school] = game_state["school_scores"].get(school, 0) + 1
                game_state["player_scores"][email] = game_state["player_scores"].get(email, 0) + 1
            
            player_data["evaluated"] = True
            
    return jsonify({"status": "success", "message": "หมดเวลาข้อนี้และคำนวณคะแนนแล้ว"})

@app.route('/api/next', methods=['POST'])
def next_question():
    if not game_state["is_started"]:
        return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
        
    current_idx = game_state["current_index"]
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        for email, player_data in game_state["current_answers"].items():
            if not player_data.get("evaluated", False):
                # ตรวจคำตอบ (กรณีแอดมินกด Next ข้ามไปเลยโดยไม่ได้กดหมดเวลาก่อน)
                if is_correct(player_data["answer"], correct_answer):
                    school = player_data["school"]
                    game_state["school_scores"][school] = game_state["school_scores"].get(school, 0) + 1
                    game_state["player_scores"][email] = game_state["player_scores"].get(email, 0) + 1
                player_data["evaluated"] = True

    # เลื่อนไปข้อถัดไป
    game_state["current_index"] += 1
    game_state["is_time_up"] = False
    game_state["current_answers"] = {} 
    
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

@app.route('/api/submit', methods=['POST'])
def submit_answer():
    if session.get('role') != 'user':
        return jsonify({'status': 'error', 'message': 'ไม่มีสิทธิ์ส่งคำตอบ'}), 403
        
    if not game_state["is_started"] or game_state["is_time_up"] or game_state["is_end"]:
        return jsonify({'status': 'error', 'message': 'ระบบไม่ได้เปิดรับคำตอบในขณะนี้'}), 400
        
    data = request.json or {}
    player_answer = data.get('answer', '')
    
    # จับคู่ข้อมูลให้ตรงกับที่หน้าจอส่งมา
    email = data.get('player_id') or session.get('email')
    school = data.get('school') or session.get('name') 
    name = session.get('name', 'ผู้เล่น')
    
    game_state["current_answers"][email] = {
        "answer": player_answer,
        "school": school, # ชื่อผู้เล่น/ชื่อทีม
        "name": name,
        "evaluated": False
    }
    
    return jsonify({'status': 'success', 'message': 'ส่งคำตอบสำเร็จ'})

@app.route('/api/my-score')
def get_my_score():
    email = session.get('email')
    score = game_state["player_scores"].get(email, 0)
    return jsonify({"score": score})


if __name__ == '__main__':
    # รันบนพอร์ต 5000 โหมด Debug เพื่อให้ระบบคอมไพล์โค้ดใหม่อัตโนมัติเวลาแก้ไข
    app.run(debug=True, host='0.0.0.0', port=5000)
