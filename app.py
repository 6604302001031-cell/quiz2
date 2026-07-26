import os
import json
import time
import csv
import io
import re
import urllib.request
import urllib.error
import base64
import threading
import requests

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from flask import Flask, request, jsonify

# 📌 ไลบรารีสำหรับอ่านไฟล์ Word
try:
    import docx
except ImportError:
    docx = None
    print("⚠️ แจ้งเตือน: ยังไม่ได้ติดตั้ง python-docx (รันคำสั่ง: pip install python-docx)")

# 📌 ไลบรารีสำหรับอ่านไฟล์ PDF
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
    print("⚠️ แจ้งเตือน: ยังไม่ได้ติดตั้ง PyMuPDF (รันคำสั่ง: pip install PyMuPDF)")

app = Flask(__name__)
app.secret_key = 'quiz_game_secure_session_key_production_fixed'

GOOGLE_CLIENT_ID = "969552580845-5fkmba3g0jt9d8bkdllkp1vsnodmgg0k.apps.googleusercontent.com"

# 🔒 เพิ่ม Lock เพื่อความปลอดภัยของข้อมูลใน Multi-threading
data_lock = threading.Lock()

active_users_memory = {}
QUESTIONS_FILE = "/tmp/questions.json"

# โจทย์เริ่มต้น
default_questions = [
    {"q": "5 + 5 เท่ากับเท่าไร?", "a": "10", "image_url": ""},
    {"q": "1 + 1 เท่ากับเท่าไร?", "a": "2", "image_url": ""},
    {"q": "7 + 7 เท่ากับเท่าไร?", "a": "14", "image_url": ""}
]
questions = list(default_questions)

# โหลดโจทย์ที่เคยอัปโหลดไว้
if os.path.exists(QUESTIONS_FILE):
    try:
        with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
            loaded_questions = json.load(f)
            if isinstance(loaded_questions, list) and len(loaded_questions) > 0:
                questions = loaded_questions
    except Exception as e:
        print("Error loading questions file:", e)

# 📌 ฟังก์ชันสร้าง State เริ่มต้น
def get_default_state():
    return {
        "is_started": False,
        "is_end": False,
        "current_index": 0,
        "is_time_up": False,
        "school_scores": {},  
        "player_scores": {},  
        "current_answers": {},
        "challenges": []  # 🎯 โครงสร้างเก็บคำขอโต้แย้ง (Challenge)
    }

# 🚀 สร้างตัวแปร Global เก็บสถานะเกม
game_state_memory = get_default_state()

def load_db():
    global game_state_memory
    return game_state_memory

def save_db(data):
    global game_state_memory
    game_state_memory = data

def is_correct(ans1, ans2):
    return str(ans1).replace(" ", "").lower() == str(ans2).replace(" ", "").lower()

def calculate_team_points(correct_count):
    sets_of_three = correct_count // 3
    remainder = correct_count % 3
    
    points = sets_of_three * 5
    if remainder == 2:
        points += 3
    elif remainder == 1:
        points += 1
    return points

def get_active_users_count():
    current_time = time.time()
    with data_lock:
        return sum(1 for t in list(active_users_memory.values()) if current_time - t < 10)

# 📌 ฟังก์ชันตรวจคำตอบและคำนวณคะแนนส่วนกลาง
def evaluate_current_answers(db):
    current_idx = db["current_index"]
    if current_idx >= len(questions):
        return 0, 0

    correct_answer = questions[current_idx]["a"]
    correct_count = 0
    incorrect_count = 0
    school_correct_counts = {}

    for email, player_data in list(db["current_answers"].items()):
        is_ans_correct = is_correct(player_data["answer"], correct_answer)
        
        if is_ans_correct:
            correct_count += 1
        else:
            incorrect_count += 1
        
        if not player_data.get("evaluated", False):
            school = player_data.get("school") or "ไม่ระบุสังกัด"
            
            if is_ans_correct:
                school_correct_counts[school] = school_correct_counts.get(school, 0) + 1
                db["player_scores"][email] = db["player_scores"].get(email, 0) + 1
            
            player_data["evaluated"] = True

    for school, count in school_correct_counts.items():
        if school not in db["school_scores"]:
            db["school_scores"][school] = 0
        
        earned_points = calculate_team_points(count)
        db["school_scores"][school] += earned_points

    return correct_count, incorrect_count

# 📌 ฟังก์ชันสำหรับ Text Parser
def parse_text_to_questions(text):
    parsed_questions = []
    lines = text.split('\n')
    
    current_q = []
    current_a = []
    state = None  
    
    for line in lines:
        line = line.strip()
        if not line: 
            continue
        
        q_match = re.search(r'^\s*(?:ข้อ\s*)?(\d+)\s*[\.\)]\s*(.*)', line)
        q_keyword_match = re.search(r'^\s*(?:q|question|โจทย์|คำถาม)\s*[\.:-]?\s*(.*)', line, re.IGNORECASE)
        a_match = re.search(r'^\s*(?:a|answer|เฉลย|คำตอบ|ตอบ)\s*[\.:-]?\s*(.*)', line, re.IGNORECASE)
        
        if q_match or q_keyword_match:
            if current_q and current_a:
                parsed_questions.append({
                    "q": " ".join(current_q).strip(),
                    "a": " ".join(current_a).strip(),
                    "image_url": ""
                })
            state = 'q'
            matched_text = q_match.group(2).strip() if q_match else q_keyword_match.group(1).strip()
            current_q = [matched_text] if matched_text else []
            current_a = []
            continue
            
        elif a_match:
            state = 'a'
            matched_text = a_match.group(1).strip()
            current_a = [matched_text] if matched_text else []
            continue
            
        if state == 'q':
            current_q.append(line)
        elif state == 'a':
            current_a.append(line)
            
    if current_q and current_a:
        parsed_questions.append({
            "q": " ".join(current_q).strip(),
            "a": " ".join(current_a).strip(),
            "image_url": ""
        })
        
    return parsed_questions


# ==========================================
# 🏫 API สำหรับรายชื่อโรงเรียนและการลงทะเบียน
# ==========================================
@app.route('/api/schools', methods=['GET', 'POST'])
@app.route('/api/get-schools', methods=['GET', 'POST']) 
def get_schools():
    province = request.args.get('province') or ""
    if request.method == 'POST' and request.is_json:
        data = request.json or {}
        province = data.get('province', province)
        
    province = province.strip()
    
    schools_database = {
        "ชุมพร": [
            "โรงเรียนศรียาภัย", "โรงเรียนสอาดเผดิมวิทยา", "โรงเรียนสวนกุหลาบวิทยาลัย ชุมพร",
            "โรงเรียนสวีวิทยา", "โรงเรียนหลังสวนวิทยา", "โรงเรียนเมืองชุมพร", "โรงเรียนสัจจศึกษา"
        ],
        "สุราษฎร์ธานี": [
            "โรงเรียนสุราษฎร์ธานี", "โรงเรียนสุราษฎร์พิทยา", "โรงเรียนเมืองสุราษฎร์ธานี",
            "โรงเรียนศึกษาสงเคราะห์สุราษฎร์ธานี", "โรงเรียนพุนพินพิทยาคม"
        ]
    }
    
    school_list = schools_database.get(province, [
        f"โรงเรียนประจำจังหวัด{province}", f"โรงเรียนมัธยม{province}", f"โรงเรียนอนุบาล{province}"
    ])
    
    return jsonify(school_list)


@app.route('/api/register-school', methods=['POST'])
def register_school():
    data = request.json or {}
    school = data.get('school', '').strip()
    
    if not school:
        return jsonify({'status': 'error', 'message': 'กรุณาระบุชื่อโรงเรียน'}), 400

    session['school'] = school
    email = session.get('email')
    name = session.get('name', 'ผู้เล่น')
    
    threading.Thread(target=send_to_gsheet, args=(email, name, school, 0, "เข้าร่วมเกม")).start()
    
    return jsonify({'status': 'success', 'message': 'บันทึกโรงเรียนและลงทะเบียนเรียบร้อยแล้ว'})


# ==========================================
# 🏠 เส้นทางหลัก & ระบบล็อกอิน
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
# 🔄 API สำหรับติดตามสถานะเกม
# ==========================================
@app.route('/api/state')
def get_state():
    with data_lock:
        db = load_db()
        email = (session.get('email') or '').strip().lower()
        if email and session.get('role') == 'user':
            active_users_memory[email] = time.time()
            
        if len(questions) > 0 and db["current_index"] >= len(questions):
            db["is_end"] = True
            db["current_index"] = max(0, len(questions) - 1)
            save_db(db)

        current_q = ""
        correct_ans = ""
        correct_count = 0
        incorrect_count = 0
        img_url = ""

        my_answer = ""
        has_submitted = False
        is_correct_val = False
        has_challenged = False

        if db["is_started"] and len(questions) > 0:
            current_idx = db["current_index"]
            current_q = questions[current_idx]["q"] if not db["is_end"] else ""
            correct_ans = questions[current_idx]["a"]
            img_url = questions[current_idx].get("image_url", "")
            
            # Check player answer
            player_data = db.get("current_answers", {}).get(email)
            if player_data is not None:
                has_submitted = True
                my_answer = player_data.get("answer", "")
                
                # 🔒 คำนวณผลตรวจเฉพาะเมื่อหมดเวลาแล้วเท่านั้น
                if db.get("is_time_up") or db.get("is_end"):
                    is_correct_val = is_correct(my_answer, correct_ans)

            # Check challenge status
            q_num = current_idx + 1
            has_challenged = any(
                c for c in db.get("challenges", [])
                if c.get('email', '').lower() == email and str(c.get('question_number')) == str(q_num)
            )

            for p_email, p_data in db.get("current_answers", {}).items():
                if is_correct(p_data.get("answer"), correct_ans):
                    correct_count += 1
                else:
                    incorrect_count += 1
        
        school_scores_copy = dict(db["school_scores"])
        pending_challenges_count = len([c for c in db.get("challenges", []) if c.get('status') == 'pending'])

        # 🔒 กำหนดสถานะ ถูก/ผิด จะเป็น True ได้ต่อเมื่อหมดเวลาแล้วเท่านั้น
        time_is_over = db.get("is_time_up") or db.get("is_end")
        show_correct = has_submitted and is_correct_val if time_is_over else False
        show_wrong = has_submitted and not is_correct_val if time_is_over else False

    return jsonify({
        "is_started": db["is_started"],
        "is_time_up": db["is_time_up"],
        "is_end": db["is_end"],
        "current_number": db["current_index"] + 1,
        "question": current_q,
        "answer": correct_ans,
        "image_url": img_url,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "school_scores": school_scores_copy,
        "active_users_count": get_active_users_count(),
        "pending_challenges_count": pending_challenges_count,
        "my_answer": my_answer,
        "has_submitted": has_submitted,
        "is_correct": show_correct,
        "is_wrong": show_wrong,
        "has_challenged": has_challenged
    })


# ==========================================
# ⚔️ API ระบบส่งและอนุมัติ ชาเลนจ์ (Challenge)
# ==========================================
@app.route('/api/challenge', methods=['POST'])
def submit_challenge():
    data = request.json or {}
    email = (session.get('email') or data.get('email', '')).strip().lower()
    name = session.get('name') or data.get('name', 'ผู้เล่น')
    school = data.get('school') or session.get('school', 'ไม่ระบุสังกัด')
    q_num = data.get('question_number')
    reason = data.get('reason', '').strip()

    if not email or q_num is None or not reason:
        return jsonify({'status': 'error', 'message': 'ข้อมูลไม่ครบถ้วน'}), 400

    with data_lock:
        db = load_db()
        # ตรวจสอบว่าเคยยื่นคำขอข้อนี้ไปหรือยัง
        existing = any(
            c for c in db.get("challenges", [])
            if c.get('email', '').lower() == email and str(c.get('question_number')) == str(q_num)
        )
        if existing:
            return jsonify({'status': 'error', 'message': 'คุณได้ส่งคำขอชาเลนจ์สำหรับข้อนี้ไปแล้ว'}), 400

        db["challenges"].append({
            "email": email,
            "name": name,
            "school": school,
            "question_number": int(q_num),
            "reason": reason,
            "status": "pending",
            "timestamp": time.time()
        })
        save_db(db)

    return jsonify({'status': 'success', 'message': 'ส่งคำขอชาเลนจ์เรียบร้อยแล้ว'})


@app.route('/api/resolve-challenge', methods=['POST'])
def resolve_challenge():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403

    data = request.json or {}
    email = data.get('email', '').strip().lower()
    q_num = data.get('question_number')
    action = data.get('action') # 'approve' หรือ 'reject'

    if not email or q_num is None or not action:
        return jsonify({'status': 'error', 'message': 'ข้อมูลไม่ครบถ้วน'}), 400

    with data_lock:
        db = load_db()
        challenges = db.get("challenges", [])
        
        target = next((c for c in challenges if c['email'].lower() == email and str(c['question_number']) == str(q_num)), None)
        
        if not target:
            return jsonify({'status': 'error', 'message': 'ไม่พบรายการคำขอโต้แย้งนี้'}), 404

        target['status'] = action

        # ถ้าแอดมินกดอนุมัติ (Approve) ให้เพิ่มคะแนนย้อนหลัง
        if action == 'approve':
            db["player_scores"][email] = db["player_scores"].get(email, 0) + 1
            school = target.get('school', 'ไม่ระบุสังกัด')
            db["school_scores"][school] = db["school_scores"].get(school, 0) + 1

        save_db(db)

    return jsonify({'status': 'success', 'message': f'ดำเนินการ {action} เรียบร้อยแล้ว'})


# ==========================================
# 🎮 ระบบควบคุมเกมและคำนวณคะแนน (API)
# ==========================================
@app.route('/api/upload-questions', methods=['POST'])
def upload_questions():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
        
    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({"status": "error", "message": "ไม่ได้เลือกไฟล์"}), 400
        
    filename = file.filename.lower()
    global questions

    if filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
        try:
            file_bytes = file.read()
            base64_encoded = base64.b64encode(file_bytes).decode('utf-8')
            mime_type = file.content_type or 'image/jpeg'
            
            image_data_uri = f"data:{mime_type};base64,{base64_encoded}"
            
            new_img_question = {
                "q": f"คำถามจากรูปภาพ ({file.filename})",
                "a": "กรุณาตั้งคำตอบระบบ",
                "image_url": image_data_uri
            }
            
            with data_lock:
                questions.append(new_img_question)
                with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
                    json.dump(questions, f, ensure_ascii=False, indent=4)
                
            return jsonify({
                "status": "success", 
                "message": f"อัปโหลดรูปภาพสำเร็จ! เพิ่มเข้าสู่ระบบเป็นโจทย์ข้อที่ {len(questions)} เรียบร้อยแล้ว"
            })
        except Exception as e:
            return jsonify({"status": "error", "message": f"เกิดข้อผิดพลาดในการแปลงรูปภาพ: {str(e)}"}), 500

    new_qs = []
    try:
        if filename.endswith('.json'):
            new_qs = json.load(file)
            if not isinstance(new_qs, list) or len(new_qs) == 0 or "q" not in new_qs[0]:
                return jsonify({"status": "error", "message": "รูปแบบ JSON ไม่ถูกต้อง"}), 400
                
        elif filename.endswith('.csv'):
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
            for row in csv.reader(stream):
                if len(row) >= 2:
                    q, a = row[0].strip(), row[1].strip()
                    img = row[2].strip() if len(row) > 2 else ""
                    if q.lower() in ['q', 'โจทย์', 'คำถาม'] and a.lower() in ['a', 'เฉลย', 'คำตอบ']: continue
                    if q and a: new_qs.append({"q": q, "a": a, "image_url": img})
                        
        elif filename.endswith('.md'):
            text = file.stream.read().decode("utf-8")
            new_qs = parse_text_to_questions(text)
            
        elif filename.endswith('.docx'):
            if docx is None:
                return jsonify({"status": "error", "message": "ระบบยังไม่รองรับไฟล์ Word กรุณาติดตั้ง python-docx"}), 500
            doc = docx.Document(file)
            text = "\n".join([para.text for para in doc.paragraphs])
            new_qs = parse_text_to_questions(text)
            
        elif filename.endswith('.pdf'):
            if fitz is None:
                return jsonify({"status": "error", "message": "ระบบยังไม่รองรับไฟล์ PDF กรุณาติดตั้ง PyMuPDF"}), 500
            
            file_bytes = file.read()
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text("text", sort=True) + "\n"
                
            new_qs = parse_text_to_questions(text)
            
        else:
            return jsonify({"status": "error", "message": "รองรับไฟล์ .json, .csv, .docx, .md, .pdf และไฟล์รูปภาพทั่วไปเท่านั้น"}), 400

        if len(new_qs) == 0:
            return jsonify({"status": "error", "message": "ไม่พบข้อมูลโจทย์ หรือพิมพ์รูปแบบไม่ถูกต้อง"}), 400

        for item in new_qs:
            if "image_url" not in item:
                item["image_url"] = ""

        with data_lock:
            questions = new_qs
            with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(questions, f, ensure_ascii=False, indent=4)
            save_db(get_default_state())
            
        return jsonify({"status": "success", "message": f"อัปโหลดสำเร็จ {len(questions)} ข้อ และรีเซ็ตระบบแล้ว"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"เกิดข้อผิดพลาดในการอ่านไฟล์: {str(e)}"}), 500


@app.route('/api/upload-image-question', methods=['POST'])
def upload_image_question():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
        
    file = request.files.get('file')
    question_text = request.form.get('question', '').strip()
    answer_text = request.form.get('answer', '').strip()
    question_number_str = request.form.get('question_number', '').strip()

    if not file or file.filename == '':
        return jsonify({"status": "error", "message": "ไม่ได้เลือกไฟล์รูปภาพ"}), 400
        
    filename = file.filename.lower()
    if not filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
        return jsonify({"status": "error", "message": "ระบบรองรับเฉพาะไฟล์รูปภาพ .jpg, .png, .webp เท่านั้น"}), 400

    global questions
    try:
        file_bytes = file.read()
        base64_encoded = base64.b64encode(file_bytes).decode('utf-8')
        mime_type = file.content_type or 'image/jpeg'
        
        image_data_uri = f"data:{mime_type};base64,{base64_encoded}"
        
        final_q = question_text if question_text else f"คำถามจากรูปภาพ ({file.filename})"
        final_a = answer_text if answer_text else "ไม่มีเฉลย"

        new_img_question = {
            "q": final_q,
            "a": final_a,
            "image_url": image_data_uri
        }
        
        with data_lock:
            insert_index = len(questions) 
            
            if question_number_str.isdigit():
                target_number = int(question_number_str)
                insert_index = target_number - 1 
                
                if insert_index < 0:
                    insert_index = 0
                elif insert_index > len(questions):
                    insert_index = len(questions)

            questions.insert(insert_index, new_img_question)
            
            with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(questions, f, ensure_ascii=False, indent=4)
            
        return jsonify({
            "status": "success", 
            "message": f"อัปโหลดรูปภาพสำเร็จ! แทรกเข้าสู่ระบบเป็นโจทย์ข้อที่ {insert_index + 1} เรียบร้อยแล้ว"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"เกิดข้อผิดพลาดในการแปลงรูปภาพ: {str(e)}"}), 500


@app.route('/api/import-gsheet', methods=['POST'])
def import_gsheet():
    if session.get('role') != 'admin':
        return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
    
    data = request.json or {}
    url = data.get('url', '')
    access_token = data.get('access_token', '')  
    
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
    if not match:
        return jsonify({"status": "error", "message": "ลิงก์ Google Sheet ไม่ถูกต้อง"}), 400
    
    sheet_id = match.group(1)
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    
    try:
        req = urllib.request.Request(csv_url)
        if access_token:
            req.add_header('Authorization', f'Bearer {access_token}')
            
        with urllib.request.urlopen(req) as response:
            csv_data = response.read().decode('utf-8')
            
        if "<html" in csv_data.lower() or "<doctype" in csv_data.lower():
            return jsonify({"status": "error", "message": "ดึงข้อมูลล้มเหลว: โปรดตรวจสอบว่าคุณได้แชร์ลิงก์ Google Sheet เป็น 'ทุกคนที่มีลิงก์มีสิทธิ์อ่าน' แล้ว"}), 400

        stream = io.StringIO(csv_data, newline=None)
        new_qs = []
        for row in csv.reader(stream):
            if len(row) >= 2:
                q, a = row[0].strip(), row[1].strip()
                img = row[2].strip() if len(row) > 2 else ""
                if q.lower() in ['q', 'โจทย์', 'คำถาม'] and a.lower() in ['a', 'เฉลย', 'คำตอบ']: continue
                if q and a: new_qs.append({"q": q, "a": a, "image_url": img})
                
        if len(new_qs) == 0:
            return jsonify({"status": "error", "message": "ไม่พบข้อมูลในแผ่นงาน"}), 400
            
        global questions
        with data_lock:
            questions = new_qs
            with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(questions, f, ensure_ascii=False, indent=4)
            save_db(get_default_state())
            
        return jsonify({"status": "success", "message": f"ดึงข้อมูลจาก Sheet สำเร็จจำนวน {len(questions)} ข้อ"})
        
    except urllib.error.HTTPError as e:
        if e.code in [401, 403]:
            return jsonify({"status": "error", "message": "ไม่มีสิทธิ์เข้าถึงไฟล์ (กรุณาปรับการตั้งค่าแชร์ใน Google Sheets ให้เป็นสาธารณะ)"}), 403
        return jsonify({"status": "error", "message": f"เกิดข้อผิดพลาด HTTP {e.code}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"ดึงข้อมูลไม่สำเร็จ: {str(e)}"}), 500


@app.route('/api/start', methods=['POST'])
def start_game():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
    
    if len(questions) == 0:
         return jsonify({"status": "error", "message": "ไม่มีโจทย์ในระบบ กรุณาอัปโหลดโจทย์ก่อน"}), 400

    with data_lock:
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
            "image_url": questions[0].get("image_url", ""),
            "correct_count": 0, "incorrect_count": 0,
            "school_scores": db["school_scores"],
            "active_users_count": get_active_users_count()
        }
    })


@app.route('/api/timeout', methods=['POST'])
def trigger_timeout():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
    with data_lock:
        db = load_db()
        if not db["is_started"]:
            return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
            
        db["is_time_up"] = True
        current_idx = db["current_index"]
        
        correct_count, incorrect_count = evaluate_current_answers(db)
        save_db(db)
        
        current_q = questions[current_idx]["q"] if current_idx < len(questions) else ""
        correct_ans = questions[current_idx]["a"] if current_idx < len(questions) else ""
        img_url = questions[current_idx].get("image_url", "") if current_idx < len(questions) else ""
        school_scores_copy = dict(db["school_scores"])
    
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": True, "is_end": db["is_end"],
            "current_number": current_idx + 1, "question": current_q, "answer": correct_ans,
            "image_url": img_url,
            "correct_count": correct_count, "incorrect_count": incorrect_count,
            "school_scores": school_scores_copy,
            "active_users_count": get_active_users_count()
        }
    })


@app.route('/api/next', methods=['POST'])
def next_question():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
    with data_lock:
        db = load_db()
        if not db["is_started"]:
            return jsonify({"status": "error", "message": "เกมยังไม่ได้เริ่ม"}), 400
            
        current_idx = db["current_index"]
        evaluate_current_answers(db)

        if (current_idx + 1) >= len(questions):
            db["is_end"] = True
            save_db(db)
            return jsonify({
                "status": "success", 
                "state": {
                    "is_started": True, "is_time_up": True, "is_end": True,
                    "current_number": current_idx + 1, "question": "", "answer": "-", "image_url": "",
                    "correct_count": 0, "incorrect_count": 0,
                    "school_scores": dict(db["school_scores"]),
                    "active_users_count": get_active_users_count()
                }
            })

        db["current_index"] = current_idx + 1
        db["is_time_up"] = False
        db["current_answers"] = {} 
        save_db(db)
        
        next_q = questions[db["current_index"]]["q"]
        next_a = questions[db["current_index"]]["a"]
        next_img = questions[db["current_index"]].get("image_url", "")
        school_scores_copy = dict(db["school_scores"])
    
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": False, "is_end": False,
            "current_number": db["current_index"] + 1, "question": next_q, "answer": next_a,
            "image_url": next_img,
            "correct_count": 0, "incorrect_count": 0,
            "school_scores": school_scores_copy,
            "active_users_count": get_active_users_count()
        }
    })


@app.route('/api/reset', methods=['POST'])
def reset_game():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
    with data_lock:
        save_db(get_default_state())
        
    return jsonify({
        "status": "success",
        "state": {
            "is_started": False, "is_time_up": False, "is_end": False,
            "current_number": 1, "question": "รอแอดมินกดเริ่มเกม", "answer": "-", "image_url": "",
            "correct_count": 0, "incorrect_count": 0,
            "school_scores": {},
            "active_users_count": get_active_users_count()
        }
    })


# 🛠️ ส่งข้อมูลผ่าน HTTP POST Webhook ไปยัง Google Sheet
def send_to_gsheet(email, name, school, question_number, answer):
    webhook_url = "https://script.google.com/macros/s/AKfycbw9Xeju85-zSYqmDcB9xwphkOLZaAwoEexvi-vU5nCRHWsgtSc_LLdJrOzEWri09bNt/exec"
    
    if not webhook_url.startswith("http"):
        return 
        
    data = {
        "email": email,
        "name": name,
        "school": school,
        "question_number": int(question_number),
        "answer": str(answer)
    }
    
    try:
        response = requests.post(webhook_url, json=data, timeout=5)
        print(f"Sync to Google Sheet complete. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending data to Google Sheet: {e}")


# API สำหรับการส่งคำตอบ
@app.route('/api/submit', methods=['POST'])
def submit_answer():
    with data_lock:
        db = load_db()
        if db["is_time_up"] or db["is_end"] or not db["is_started"]:
            return jsonify({'status': 'error', 'message': 'ระบบไม่ได้เปิดรับคำตอบในขณะนี้'}), 400
            
        data = request.json or {}
        player_answer = data.get('answer', '')
        email = session.get('email') or data.get('email') or data.get('player_id')
        
        school = data.get('school') or session.get('school') or session.get('name') or "ไม่ระบุสังกัด"
        name = session.get('name', 'ผู้เล่น')
        
        if not email:
            return jsonify({'status': 'error', 'message': 'ไม่พบข้อมูลผู้ใช้งาน'}), 401
            
        db["current_answers"][email] = {
            "answer": player_answer,
            "school": school, 
            "name": name,
            "evaluated": False
        }
        
        active_users_memory[email] = time.time()
        save_db(db)
        
        current_idx = db["current_index"]
        current_question_number = current_idx + 1
    
    # ส่งข้อมูลไปยัง Google Sheets เบื้องหลัง
    threading.Thread(
        target=send_to_gsheet, 
        args=(email, name, school, current_question_number, player_answer)
    ).start()
    
    return jsonify({
        'status': 'success', 
        'message': 'ส่งคำตอบเรียบร้อยแล้ว'
    })

@app.route('/api/my-score')
def get_my_score():
    with data_lock:
        db = load_db()
        email = session.get('email')
        score = db["player_scores"].get(email, 0)
    return jsonify({"score": score})


# API สำหรับรับการอัปเดตคะแนนตรงจากตัว Google Sheet แบบเรียลไทม์ (ส่วนที่ถูกตัดจบเดิม)
@app.route('/api/sheet-update-score', methods=['POST'])
def sheet_update_score():
    data = request.json or {}
    email = data.get('email', '').strip().lower()
    school = data.get('school', '').strip()
    new_score = data.get('new_score')
    
    if not email or new_score is None:
        return jsonify({"status": "error", "message": "ข้อมูลไม่ครบถ้วน"}), 400
        
    try:
        new_score = int(new_score)
        with data_lock:
            db = load_db()
            db["player_scores"][email] = new_score
            if school:
                db["school_scores"][school] = db["school_scores"].get(school, 0) + new_score
            save_db(db)
        return jsonify({"status": "success", "message": "อัปเดตคะแนนสำเร็จ"})
    except ValueError:
        return jsonify({"status": "error", "message": "รูปแบบคะแนนไม่ถูกต้อง"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"เกิดข้อผิดพลาด: {str(e)}"}), 500
# API สำหรับดึงรายการ Challenge ที่รอตรวจ (สำหรับแอดมิน)
@app.route('/api/admin/challenges', methods=['GET'])
def get_admin_challenges():
    # กรองเฉพาะรายการที่สถานะยังเป็น 'pending' (รอการอนุมัติ)
    pending_challenges = [c for c in challenges_db if c.get('status') == 'pending']
    return jsonify({'challenges': pending_challenges})

# API สำหรับแอดมินกด "อนุมัติ" หรือ "ปฏิเสธ"
@app.route('/api/admin/handle-challenge', methods=['POST'])
def handle_challenge():
    data = request.json
    challenge_id = data.get('challenge_id')
    action = data.get('action') # 'approve' หรือ 'reject'

    # ค้นหาคำขอชาเลนจ์จาก ID
    target_challenge = next((c for c in challenges_db if c['id'] == challenge_id), None)
    
    if not target_challenge:
        return jsonify({'status': 'error', 'message': 'ไม่พบรายการชาเลนจ์นี้'}), 404

    if action == 'approve':
        target_challenge['status'] = 'approved'
        
        # 1. ปรับสถานะคำตอบของผู้เล่นให้เป็น "ตอบถูก" (is_correct = True)
        # 2. เพิ่มคะแนนให้ผู้เล่น +1 คะแนน
        # (เขียน Logic อัปเดตคะแนนของผู้เล่นที่ target_challenge['email'] ในระบบของคุณที่นี่)
        update_player_score(target_challenge['email'], target_challenge['question_number'], is_correct=True)

        return jsonify({
            'status': 'success', 
            'message': f"อนุมัติคำขอของ {target_challenge['player_name']} เรียบร้อยแล้ว ระบบได้ปรับเป็นตอบถูกและเพิ่มคะแนนให้แล้ว"
        })

    elif action == 'reject':
        target_challenge['status'] = 'rejected'
        return jsonify({
            'status': 'success', 
            'message': f"ปฏิเสธคำขอเรียบร้อยแล้ว"
        })

    return jsonify({'status': 'error', 'message': 'คำสั่งไม่ถูกต้อง'}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
   
