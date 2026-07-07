import os
import json
import time  # 📌 นำเข้าโมดูล time สำหรับระบบนับคนออนไลน์
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

app = Flask(__name__)
app.secret_key = 'quiz_game_secure_session_key_production_fixed'

GOOGLE_CLIENT_ID = "969552580845-5fkmba3g0jt9d8bkdllkp1vsnodmgg0k.apps.googleusercontent.com"

# 📌 ตัวแปรเก็บเวลาล่าสุดที่ผู้เล่นแต่ละคน (user) มีการดึงข้อมูล
active_users_memory = {}

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

DB_FILE = "/tmp/game_database.json"

DEFAULT_STATE = {
    "is_started": False,
    "is_end": False,
    "current_index": 0,
    "is_time_up": False,
    "school_scores": {},  
    "player_scores": {},  
    "current_answers": {} 
}

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return DEFAULT_STATE.copy()
    return DEFAULT_STATE.copy()

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error writing to persistence layer: {e}")

def is_correct(ans1, ans2):
    return str(ans1).replace(" ", "").lower() == str(ans2).replace(" ", "").lower()

# 🌟 ฟังก์ชันคำนวณคะแนนโบนัสทีม (ตามโจทย์: 3 คน=5 แต้ม, 2 คน=3 แต้ม)
def calculate_team_points(correct_count):
    sets_of_three = correct_count // 3  # จับกลุ่มทีละ 3 คน
    remainder = correct_count % 3       # เศษที่เหลือ
    
    points = sets_of_three * 5
    if remainder == 2:
        points += 3
    elif remainder == 1:
        points += 1
    return points

# 📌 ฟังก์ชันดึงจำนวนผู้เล่นที่กำลังออนไลน์ (ภายใน 10 วินาทีล่าสุด)
def get_active_users_count():
    current_time = time.time()
    return sum(1 for t in active_users_memory.values() if current_time - t < 10)


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
    
    db = load_db()
    db["is_started"] = True
    db["is_end"] = False
    db["current_index"] = 0
    db["is_time_up"] = False
    db["current_answers"] = {}
    save_db(db)
    
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": False, "is_end": False,
            "current_number": 1, "question": questions[0]["q"], "answer": questions[0]["a"],
            "correct_count": 0, "incorrect_count": 0,
            "school_scores": db["school_scores"],
            "active_users_count": get_active_users_count() # 📌 แนบไปตอนเริ่มเกม
        }
    })

@app.route('/api/state')
def get_state():
    db = load_db()
    
    # 📌 บันทึกเวลาปัจจุบันของผู้ใช้ (ถ้าเป็นผู้เล่น)
    email = session.get('email')
    if email and session.get('role') == 'user':
        active_users_memory[email] = time.time()
        
    if db["current_index"] >= len(questions):
        db["is_end"] = True
        db["current_index"] = len(questions) - 1
        save_db(db)

    current_q = ""
    correct_ans = ""
    correct_count = 0
    incorrect_count = 0

    if db["is_started"] and not db["is_end"]:
        current_idx = db["current_index"]
        current_q = questions[current_idx]["q"]
        correct_ans = questions[current_idx]["a"]
        
        # 📌 นับจำนวนตอบถูก/ผิด ตลอดเวลาเพื่อดึงไปแสดงผล
        for p_email, player_data in db.get("current_answers", {}).items():
            if is_correct(player_data.get("answer"), correct_ans):
                correct_count += 1
            else:
                incorrect_count += 1
        
    return jsonify({
        "is_started": db["is_started"],
        "is_time_up": db["is_time_up"],
        "is_end": db["is_end"],
        "current_number": db["current_index"] + 1,
        "question": current_q,
        "answer": correct_ans,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "school_scores": db["school_scores"],
        "active_users_count": get_active_users_count() # 📌 แนบไปกับ API state
    })

@app.route('/api/timeout', methods=['POST'])
def trigger_timeout():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
    db = load_db()
    if not db["is_started"]:
        return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
        
    db["is_time_up"] = True
    current_idx = db["current_index"]
    
    correct_count = 0
    incorrect_count = 0
    
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        school_correct_counts = {}
        
        # นับจำนวนคนที่ตอบถูกในแต่ละโรงเรียนสำหรับข้อนี้ และรวมยอดสำหรับแสดงผล
        for email, player_data in list(db["current_answers"].items()):
            is_ans_correct = is_correct(player_data["answer"], correct_answer)
            
            # 📌 นับรวม
            if is_ans_correct:
                correct_count += 1
            else:
                incorrect_count += 1
            
            # 📌 คำนวณคะแนนเฉพาะคนที่ยังไม่ได้คิดคะแนน
            if not player_data.get("evaluated", False):
                school = player_data["school"] or "ไม่ระบุสังกัด"
                
                if is_ans_correct:
                    school_correct_counts[school] = school_correct_counts.get(school, 0) + 1
                    db["player_scores"][email] = db["player_scores"].get(email, 0) + 1 # ผู้เล่นรายคนยังได้ +1 เสมอ
                
                player_data["evaluated"] = True
                
        # นำจำนวนคนที่ตอบถูกมาคำนวณและบวกเข้าคะแนนทีม
        for school, count in school_correct_counts.items():
            if school not in db["school_scores"]:
                db["school_scores"][school] = 0
            
            earned_points = calculate_team_points(count)
            db["school_scores"][school] += earned_points
            
    save_db(db)
    current_q = questions[current_idx]["q"] if current_idx < len(questions) else ""
    correct_ans = questions[current_idx]["a"] if current_idx < len(questions) else ""
    
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": True, "is_end": db["is_end"],
            "current_number": current_idx + 1, "question": current_q, "answer": correct_ans,
            "correct_count": correct_count, "incorrect_count": incorrect_count,
            "school_scores": db["school_scores"],
            "active_users_count": get_active_users_count() # 📌
        }
    })

@app.route('/api/next', methods=['POST'])
def next_question():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
    db = load_db()
    if not db["is_started"]:
        return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
        
    current_idx = db["current_index"]
    
    # ประมวลผลเก็บตกคะแนน (กรณีที่แอดมินกด Next เลยโดยไม่ได้กด Timeout)
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        school_correct_counts = {}
        
        for email, player_data in list(db["current_answers"].items()):
            if not player_data.get("evaluated", False):
                school = player_data["school"] or "ไม่ระบุสังกัด"
                if is_correct(player_data["answer"], correct_answer):
                    school_correct_counts[school] = school_correct_counts.get(school, 0) + 1
                    db["player_scores"][email] = db["player_scores"].get(email, 0) + 1
                player_data["evaluated"] = True
                
        for school, count in school_correct_counts.items():
            if school not in db["school_scores"]:
                db["school_scores"][school] = 0
            
            earned_points = calculate_team_points(count)
            db["school_scores"][school] += earned_points

    if (current_idx + 1) >= len(questions):
        db["is_end"] = True
        save_db(db)
        return jsonify({
            "status": "success", 
            "state": {
                "is_started": True, "is_time_up": True, "is_end": True,
                "current_number": current_idx + 1, "question": "", "answer": "-",
                "correct_count": 0, "incorrect_count": 0,
                "school_scores": db["school_scores"],
                "active_users_count": get_active_users_count() # 📌
            }
        })

    db["current_index"] = current_idx + 1
    db["is_time_up"] = False
    db["current_answers"] = {} 
    save_db(db)
    
    next_q = questions[db["current_index"]]["q"]
    next_a = questions[db["current_index"]]["a"]
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": False, "is_end": False,
            "current_number": db["current_index"] + 1, "question": next_q, "answer": next_a,
            "correct_count": 0, "incorrect_count": 0,
            "school_scores": db["school_scores"],
            "active_users_count": get_active_users_count() # 📌
        }
    })

@app.route('/api/reset', methods=['POST'])
def reset_game():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
    save_db(DEFAULT_STATE)
    return jsonify({
        "status": "success",
        "state": {
            "is_started": False, "is_time_up": False, "is_end": False,
            "current_number": 1, "question": "รอแอดมินกดเริ่มเกม", "answer": "-",
            "correct_count": 0, "incorrect_count": 0,
            "school_scores": {},
            "active_users_count": get_active_users_count() # 📌
        }
    })

@app.route('/api/submit', methods=['POST'])
def submit_answer():
    db = load_db()
    if db["is_time_up"] or db["is_end"] or not db["is_started"]:
        return jsonify({'status': 'error', 'message': 'ระบบไม่ได้เปิดรับคำตอบในขณะนี้'}), 400
        
    data = request.json or {}
    player_answer = data.get('answer', '')
    email = session.get('email') or data.get('player_id')
    
    school = data.get('school') or session.get('name') or "ไม่ระบุสังกัด"
    name = session.get('name', 'ผู้เล่น')
    
    if not email:
        return jsonify({'status': 'error', 'message': 'ไม่พบข้อมูลผู้ใช้งาน'}), 401
        
    db["current_answers"][email] = {
        "answer": player_answer,
        "school": school, 
        "name": name,
        "evaluated": False
    }
    
    # 📌 อัปเดตสถานะว่าเพิ่งส่งคำตอบ = เพิ่งออนไลน์
    active_users_memory[email] = time.time()
    
    save_db(db)
    return jsonify({'status': 'success', 'message': 'ส่งคำตอบสำเร็จ'})

@app.route('/api/my-score')
def get_my_score():
    db = load_db()
    email = session.get('email')
    score = db["player_scores"].get(email, 0)
    return jsonify({"score": score})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
