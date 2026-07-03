import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

app = Flask(__name__)

# 🔑 กำหนด Secret Key (สำคัญมากสำหรับการเข้ารหัสข้อมูลสถานะเกมลงใน Session)
app.secret_key = 'quiz_game_secure_session_key_production'

GOOGLE_CLIENT_ID = "969552580845-5fkmba3g0jt9d8bkdllkp1vsnodmgg0k.apps.googleusercontent.com"

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

# 📊 ตัวแปร Global สำรองสำหรับผู้เล่นทั่วไปดึงข้อมูล (จะ Sync ค่าจาก Session ของแอดมินเสมอ)
GLOBAL_GAME_STATE = {
    "is_started": False,
    "is_end": False,
    "current_index": 0,
    "is_time_up": False,
    "school_scores": {},  
    "player_scores": {},  
    "current_answers": {} 
}

def init_admin_session():
    """สร้างข้อมูลสถานะเริ่มต้นใน Session ของแอดมิน หากยังไม่มีอยู่"""
    if "is_started" not in session:
        session["is_started"] = False
        session["is_end"] = False
        session["current_index"] = 0
        session["is_time_up"] = False
        session["school_scores"] = {}
        session["player_scores"] = {}
        session["current_answers"] = {}
    sync_to_global()

def sync_to_global():
    """คัดลอกสถานะจาก Session ของแอดมินไปไว้ที่ Global ตัวกลาง เพื่อให้ผู้เล่นเข้าถึงได้"""
    global GLOBAL_GAME_STATE
    GLOBAL_GAME_STATE["is_started"] = session.get("is_started", False)
    GLOBAL_GAME_STATE["is_end"] = session.get("is_end", False)
    GLOBAL_GAME_STATE["current_index"] = session.get("current_index", 0)
    GLOBAL_GAME_STATE["is_time_up"] = session.get("is_time_up", False)
    GLOBAL_GAME_STATE["school_scores"] = session.get("school_scores", {})
    GLOBAL_GAME_STATE["player_scores"] = session.get("player_scores", {})
    GLOBAL_GAME_STATE["current_answers"] = session.get("current_answers", {})

def is_correct(ans1, ans2):
    return str(ans1).replace(" ", "").lower() == str(ans2).replace(" ", "").lower()


# ==========================================
# 🏠 เส้นทางหลัก (Routing Pages)
# ==========================================

@app.route('/')
def index():
    if 'role' not in session:
        return redirect(url_for('login_page'))
    
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    return render_template('user.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return "สิทธิ์การเข้าถึงถูกปฏิเสธ: หน้านี้สำหรับอาจารย์/ผู้ดูแลระบบเท่านั้น", 403
    init_admin_session()
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
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo.get('email', '').lower()
        name = idinfo.get('name')
        
        if email.endswith('@student.sru.ac.th') or email.endswith('@sru.ac.th'):
            session['role'] = 'admin'
        else:
            session['role'] = 'user'
        
        session['email'] = email
        session['name'] = name
        
        if session['role'] == 'admin':
            init_admin_session()
            
        return jsonify({"status": "success", "message": "ล็อกอินสำเร็จ"})
    except ValueError:
        return jsonify({"status": "error", "message": "Token ไม่ถูกต้องหรือหมดอายุ"}), 400


# ==========================================
# 🎮 ระบบควบคุมเกมและคำนวณคะแนน (API)
# ==========================================

@app.route('/api/start', methods=['POST'])
def start_game():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
    
    session["is_started"] = True
    session["is_end"] = False
    session["current_index"] = 0
    session["is_time_up"] = False
    session["current_answers"] = {}
    
    # บังคับอัปเดตสเตตัสลง Object ชั่วคราวเพื่อส่งคืน UI ทันที
    session.modified = True
    sync_to_global()
    
    current_q = questions[0]["q"]
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": False, "is_end": False,
            "current_number": 1, "question": current_q, "school_scores": session["school_scores"]
        }
    })

@app.route('/api/state')
def get_state():
    # ถ้าผู้ใช้เป็นแอดมิน ให้ดึงข้อมูลและอัปเดตผ่าน Session เสมอ
    if session.get('role') == 'admin':
        init_admin_session()
        if session["current_index"] >= len(questions):
            session["is_end"] = True
            session["current_index"] = len(questions) - 1
            session.modified = True
            sync_to_global()

        current_q = ""
        if session["is_started"] and not session["is_end"]:
            current_q = questions[session["current_index"]]["q"]
            
        return jsonify({
            "is_started": session["is_started"],
            "is_time_up": session["is_time_up"],
            "is_end": session["is_end"],
            "current_number": session["current_index"] + 1,
            "question": current_q,
            "school_scores": session["school_scores"]
        })
    else:
        # หากเป็นผู้เล่นทั่วไป ให้ดึงข้อมูลจากตัวแปรตัวกลาง Global 
        curr_idx = GLOBAL_GAME_STATE["current_index"]
        current_q = ""
        if GLOBAL_GAME_STATE["is_started"] and not GLOBAL_GAME_STATE["is_end"] and curr_idx < len(questions):
            current_q = questions[curr_idx]["q"]
            
        return jsonify({
            "is_started": GLOBAL_GAME_STATE["is_started"],
            "is_time_up": GLOBAL_GAME_STATE["is_time_up"],
            "is_end": GLOBAL_GAME_STATE["is_end"],
            "current_number": curr_idx + 1,
            "question": current_q,
            "school_scores": GLOBAL_GAME_STATE["school_scores"]
        })

@app.route('/api/timeout', methods=['POST'])
def trigger_timeout():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
    init_admin_session()
    if not session["is_started"]:
        return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
        
    session["is_time_up"] = True
    current_idx = session["current_index"]
    
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        answers = session.get("current_answers", {})
        school_scores = session.get("school_scores", {})
        player_scores = session.get("player_scores", {})
        
        for email, player_data in list(answers.items()):
            if player_data.get("evaluated", False):
                continue
                
            school = player_data["school"]
            if school not in school_scores:
                school_scores[school] = 0
                
            if is_correct(player_data["answer"], correct_answer):
                school_scores[school] += 1
                player_scores[email] = player_scores.get(email, 0) + 1
            
            player_data["evaluated"] = True
            
        session["school_scores"] = school_scores
        session["player_scores"] = player_scores
        session["current_answers"] = answers

    session.modified = True
    sync_to_global()
    
    current_q = questions[current_idx]["q"] if current_idx < len(questions) else ""
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": True, "is_end": session["is_end"],
            "current_number": current_idx + 1, "question": current_q, "school_scores": session["school_scores"]
        }
    })

@app.route('/api/next', methods=['POST'])
def next_question():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
    init_admin_session()
    if not session["is_started"]:
        return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
        
    current_idx = session["current_index"]
    answers = session.get("current_answers", {})
    school_scores = session.get("school_scores", {})
    player_scores = session.get("player_scores", {})
    
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        for email, player_data in list(answers.items()):
            if not player_data.get("evaluated", False):
                school = player_data["school"]
                if school not in school_scores:
                    school_scores[school] = 0
                    
                if is_correct(player_data["answer"], correct_answer):
                    school_scores[school] += 1
                    player_scores[email] = player_scores.get(email, 0) + 1
                player_data["evaluated"] = True

    if (current_idx + 1) >= len(questions):
        session["is_end"] = True
        session["school_scores"] = school_scores
        session["player_scores"] = player_scores
        session.modified = True
        sync_to_global()
        return jsonify({
            "status": "success", 
            "state": {
                "is_started": True, "is_time_up": True, "is_end": True,
                "current_number": current_idx + 1, "question": "", "school_scores": session["school_scores"]
            }
        })

    session["current_index"] = current_idx + 1
    session["is_time_up"] = False
    session["current_answers"] = {} 
    session["school_scores"] = school_scores
    session["player_scores"] = player_scores
    
    session.modified = True
    sync_to_global()
    
    next_q = questions[session["current_index"]]["q"]
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": False, "is_end": False,
            "current_number": session["current_index"] + 1, "question": next_q, "school_scores": session["school_scores"]
        }
    })

@app.route('/api/reset', methods=['POST'])
def reset_game():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
    session["is_started"] = False
    session["is_end"] = False
    session["current_index"] = 0
    session["is_time_up"] = False
    session["school_scores"] = {}
    session["player_scores"] = {}
    session["current_answers"] = {}
    
    session.modified = True
    sync_to_global()
    
    return jsonify({
        "status": "success",
        "state": {
            "is_started": False, "is_time_up": False, "is_end": False,
            "current_number": 1, "question": "รอแอดมินกดเริ่มเกม", "school_scores": {}
        }
    })

@app.route('/api/submit', methods=['POST'])
def submit_answer():
    if GLOBAL_GAME_STATE["is_time_up"] or GLOBAL_GAME_STATE["is_end"] or not GLOBAL_GAME_STATE["is_started"]:
        return jsonify({'status': 'error', 'message': 'ระบบไม่ได้เปิดรับคำตอบในขณะนี้'}), 400
        
    data = request.json or {}
    player_answer = data.get('answer', '')
    email = session.get('email') or data.get('player_id')
    school = session.get('name') or data.get('school') 
    name = session.get('name', 'ผู้เล่น')
    
    if not email:
        return jsonify({'status': 'error', 'message': 'ไม่พบข้อมูลผู้ใช้งาน กรุณาล็อกอินใหม่'}), 401
        
    GLOBAL_GAME_STATE["current_answers"][email] = {
        "answer": player_answer,
        "school": school, 
        "name": name,
        "evaluated": False
    }
    return jsonify({'status': 'success', 'message': 'ส่งคำตอบสำเร็จ'})

@app.route('/api/my-score')
def get_my_score():
    email = session.get('email')
    score = GLOBAL_GAME_STATE["player_scores"].get(email, 0)
    return jsonify({"score": score})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
