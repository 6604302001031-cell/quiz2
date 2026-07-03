import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

app = Flask(__name__)

# 🔑 กำหนด Secret Key สำหรับใช้ระบบ Session
app.secret_key = 'quiz_game_secret_key_change_in_production'

# 🔑 Google Client ID
GOOGLE_CLIENT_ID = "969552580845-5fkmba3g0jt9d8bkdllkp1vsnodmgg0k.apps.googleusercontent.com"

# 📝 ชุดคำถาม 15 ข้อ
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

# 📊 ตัวแปรเก็บสถานะเกม
game_state = {
    "is_started": False,
    "is_end": False,
    "current_index": 0,
    "is_time_up": False,
    "school_scores": {},  
    "player_scores": {},  
    "current_answers": {} 
}

def is_correct(ans1, ans2):
    return str(ans1).replace(" ", "").lower() == str(ans2).replace(" ", "").lower()


# ==========================================
# 🏠 เส้นทางหลัก (Routing Pages)
# ==========================================

@app.route('/')
def index():
    if 'role' not in session:
        return redirect(url_for('login_page'))
    
    # 🔀 ระบบจะเด้งไปหน้า Admin หรือ User ตามสิทธิ์ที่ระบุไว้ใน Session ทันที
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
# 🔐 ระบบยืนยันตัวตน และแยกสิทธิ์ (Authentication)
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
        
        # 🔍 ตรวจสอบนามสกุลอีเมลเพื่อแบ่งกลุ่มผู้ใช้งาน
        if email.endswith('@student.sru.ac.th') or email.endswith('@sru.ac.th'):
            session['role'] = 'admin'  # สิทธิ์ผู้ดูแลระบบ
        else:
            session['role'] = 'user'   # สิทธิ์ผู้เล่นทั่วไป
        
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
    
    game_state["is_started"] = True
    game_state["is_end"] = False
    game_state["current_index"] = 0
    game_state["is_time_up"] = False
    game_state["current_answers"] = {}
    return jsonify({"status": "success", "message": "เริ่มเกมเรียบร้อยแล้ว!"})

@app.route('/api/state')
def get_state():
    # 🌟 แก้ไข: ล็อกขอบเขตดัชนีข้อให้ปลอดภัยและแม่นยำ ไม่ให้ทะลุความยาวของคำถามจริง
    if game_state["current_index"] >= len(questions):
        game_state["is_end"] = True
        game_state["current_index"] = len(questions) - 1

    current_q = ""
    if game_state["is_started"] and not game_state["is_end"]:
        current_q = questions[game_state["current_index"]]["q"]
        
    return jsonify({
        "is_started": game_state["is_started"],
        "is_time_up": game_state["is_time_up"],
        "is_end": game_state["is_end"],
        "current_number": game_state["current_index"] + 1,
        "question": current_q,
        "school_scores": game_state["school_scores"]
    })

@app.route('/api/timeout', methods=['POST'])
def trigger_timeout():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
    if not game_state["is_started"]:
        return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
        
    game_state["is_time_up"] = True
    current_idx = game_state["current_index"]
    
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        # 🌟 แก้ไข: ครอบด้วย list() เพื่อป้องกันปัญหา Error เมื่อข้อมูลขัดแย้งกันขณะวนลูปดึงข้อมูล (Race Condition)
        for email, player_data in list(game_state["current_answers"].items()):
            if player_data.get("evaluated", False):
                continue
                
            school = player_data["school"]
            if school not in game_state["school_scores"]:
                game_state["school_scores"][school] = 0
                
            if is_correct(player_data["answer"], correct_answer):
                game_state["school_scores"][school] += 1
                game_state["player_scores"][email] = game_state["player_scores"].get(email, 0) + 1
            
            player_data["evaluated"] = True
            
    return jsonify({"status": "success", "message": "หมดเวลาข้อนี้และคำนวณคะแนนแล้ว"})

@app.route('/api/next', methods=['POST'])
def next_question():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
    if not game_state["is_started"]:
        return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
        
    current_idx = game_state["current_index"]
    
    # 1. ตรวจคำตอบที่ตกค้าง (ถ้ามี) ก่อนข้ามข้อ
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        # 🌟 แก้ไข: ครอบด้วย list() เช่นกันเพื่อความสถียร
        for email, player_data in list(game_state["current_answers"].items()):
            if not player_data.get("evaluated", False):
                school = player_data["school"]
                if school not in game_state["school_scores"]:
                    game_state["school_scores"][school] = 0
                    
                if is_correct(player_data["answer"], correct_answer):
                    game_state["school_scores"][school] += 1
                    game_state["player_scores"][email] = game_state["player_scores"].get(email, 0) + 1
                player_data["evaluated"] = True

    # 2. 🌟 แก้ไขหลัก: เช็กขอบเขตคำถามก่อนขยับขึ้น หากเป็นข้อสุดท้ายแล้วให้เซ็ตจบการแข่งขันทันที ไม่ให้บวกเลขเพิ่มพลการ
    if (game_state["current_index"] + 1) >= len(questions):
        game_state["is_end"] = True
        return jsonify({"status": "success", "message": "สิ้นสุดการแข่งขันแล้ว", "is_end": True})

    # ขยับดัชนีข้อถัดไปกรณีที่ยังมีข้อเหลืออยู่
    game_state["current_index"] += 1
    game_state["is_time_up"] = False
    game_state["current_answers"] = {} 
        
    return jsonify({"status": "success", "message": "เปลี่ยนเป็นข้อถัดไปเรียบร้อย", "is_end": False})

@app.route('/api/reset', methods=['POST'])
def reset_game():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
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
        return jsonify({'status': 'error', 'message': 'ไม่มีสิทธิ์ส่งคำตอบ (หน้านี้สำหรับผู้เล่นทั่วไป)'}), 403
        
    if not game_state["is_started"] or game_state["is_time_up"] or game_state["is_end"]:
        return jsonify({'status': 'error', 'message': 'ระบบไม่ได้เปิดรับคำตอบในขณะนี้'}), 400
        
    data = request.json or {}
    player_answer = data.get('answer', '')
    
    email = session.get('email') or data.get('player_id')
    school = session.get('name') or data.get('school') 
    name = session.get('name', 'ผู้เล่น')
    
    if not email:
        return jsonify({'status': 'error', 'message': 'ไม่พบข้อมูลผู้ใช้งาน กรุณาล็อกอินใหม่'}), 401
        
    game_state["current_answers"][email] = {
        "answer": player_answer,
        "school": school, 
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
    # รันเซิร์ฟเวอร์แบบเปิด Debug mode ไว้สำหรับทดสอบในเครื่องคอมพิวเตอร์
    app.run(debug=True, host='0.0.0.0', port=5000)
