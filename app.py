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
            # 🌟 เช็กเพิ่ม: ถ้าล็อกอินเป็น user แล้วแต่ยังไม่ได้ระบุโรงเรียน ให้บังคับไปหน้ากรอกโรงเรียนก่อน
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
        # ตรวจสอบความถูกต้องและความปลอดภัยของ Token โดยคุยกับเซิร์ฟเวอร์ Google
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        email = idinfo.get('email', '').strip().lower()
        name = idinfo.get('name', 'ผู้เล่น')
        
        # บันทึกข้อมูลพื้นฐานลงใน Session ของผู้ใช้รายนั้นๆ
        session['email'] = email
        session['name'] = name
        
        # ✨ จุดคัดกรอง: ตรวจสอบความลงท้ายของโดเมนอีเมลมหาวิทยาลัยเพื่อแจกสิทธิ์ Admin
        if email.endswith('@student.sru.ac.th') or email.endswith('@sru.ac.th'):
            session['role'] = 'admin'
            return jsonify({'status': 'success', 'redirect': '/admin'})
        else:
            session['role'] = 'user'
            # 🌟 สำหรับ User ทั่วไป บังคับส่งไปหน้าระบุชื่อโรงเรียนก่อนเข้าเกม
            return jsonify({'status': 'success', 'redirect': '/select-school'})
            
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Token ไม่ถูกต้องหรือหมดอายุการใช้งาน'}), 401

# 🌟 ROUTE ใหม่: หน้าแสดงฟอร์ม UI ให้กรอกชื่อโรงเรียน
@app.route('/select-school')
def select_school_page():
    if session.get('role') != 'user':
        return redirect(url_for('login_page'))
    return render_template('select_school.html')

# 🌟 API ใหม่: บันทึกชื่อโรงเรียนที่ผู้เล่นกรอกลงสู่ระบบ Session
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
    # 🌟 เช็กสิทธิ์ความปลอดภัยคูณสอง: ต้องล็อกอิน และต้องกรอกโรงเรียนแล้วเท่านั้น
    if session.get('role') != 'user':
        return redirect(url_for('login_page'))
    if 'school' not in session:
        return redirect(url_for('select_school_page'))
        
    return render_template('user.html')

@app.route('/logout')
def logout():
    session.clear()  # ล้างค่าจำเซสชันทั้งหมด
    return redirect(url_for('login_page'))

# ==========================================
# 🎮 ระบบควบคุมเกมและคำนวณคะแนน
# ==========================================

@app.route('/api/start', methods=['POST'])
def start_game():
    game_state["is_started"] = True
    return jsonify({"status": "success", "message": "Game has started!"})

@app.route('/api/state')
def get_state():
    idx = game_state
