import os
import json
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

app = Flask(__name__)

# 🔑 กำหนด Secret Key สำหรับเซสชัน
app.secret_key = 'quiz_game_secure_session_key_production_fixed'

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

# 📂 ใช้ path ไฟล์ที่มีสิทธิ์การเขียน/อ่านชดเชยที่ปลอดภัยที่สุดบนเซิร์ฟเวอร์สภาพแวดล้อมต่างๆ
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
    """โหลดข้อมูลสถานะเกมรวมถึงคะแนนจากฐานข้อมูลจำลองไฟล์ JSON"""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return DEFAULT_STATE.copy()
    return DEFAULT_STATE.copy()

def save_db(data):
    """บันทึกข้อมูลสถานะเกมและคะแนนทั้งหมดลงไฟล์ JSON ทันที"""
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error writing to persistence layer: {e}")

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
            "current_number": 1, "question": questions[0]["q"], "school_scores": db["school_scores"]
        }
    })

@app.route('/api/state')
def get_state():
    db = load_db()
    if db["current_index"] >= len(questions):
        db["is_end"] = True
        db["current_index"] = len(questions) - 1
        save_db(db)

    current_q = ""
    if db["is_started"] and not db["is_end"]:
        current_q = questions[db["current_index"]]["q"]
        
    return jsonify({
        "is_started": db["is_started"],
        "is_time_up": db["is_time_up"],
        "is_end": db["is_end"],
        "current_number": db["current_index"] + 1,
        "question": current_q,
        "school_scores": db["school_scores"]
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
    
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        
        for email, player_data in list(db["current_answers"].items()):
            if player_data.get("evaluated", False):
                continue
                
            school = player_data["school"]
            if not school:
                school = "ไม่ระบุสังกัด"
                
            if school not in db["school_scores"]:
                db["school_scores"][school] = 0
                
            if is_correct(player_data["answer"], correct_answer):
                db["school_scores"][school] += 1
                db["player_scores"][email] = db["player_scores"].get(email, 0) + 1
            
            player_data["evaluated"] = True
            
    save_db(db)
    current_q = questions[current_idx]["q"] if current_idx < len(questions) else ""
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": True, "is_end": db["is_end"],
            "current_number": current_idx + 1, "question": current_q, "school_scores": db["school_scores"]
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
    
    # ประมวลผลเก็บตกคะแนน
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        for email, player_data in list(db["current_answers"].items()):
            if not player_data.get("evaluated", False):
                school = player_data["school"] or "ไม่ระบุสังกัด"
                if school not in db["school_scores"]:
                    db["school_scores"][school] = 0
                    
                if is_correct(player_data["answer"], correct_answer):
                    db["school_scores"][school] += 1
                    db["player_scores"][email] = db["player_scores"].get(email, 0) + 1
                player_data["evaluated"] = True

    if (current_idx + 1) >= len(questions):
        db["is_end"] = True
        save_db(db)
        return jsonify({
            "status": "success", 
            "state": {
                "is_started": True, "is_time_up": True, "is_end": True,
                "current_number": current_idx + 1, "question": "", "school_scores": db["school_scores"]
            }
        })

    db["current_index"] = current_idx + 1
    db["is_time_up"] = False
    db["current_answers"] = {} 
    save_db(db)
    
    next_q = questions[db["current_index"]]["q"]
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": False, "is_end": False,
            "current_number": db["current_index"] + 1, "question": next_q, "school_scores": db["school_scores"]
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
            "current_number": 1, "question": "รอแอดมินกดเริ่มเกม", "school_scores": {}
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
    
    # 🌟 จุดสำคัญ: ดึงสังกัด (School) ของผู้เรียนมาบันทึก หากไม่พบคะแนนจะได้ไม่เป็นค่าว่าง
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
