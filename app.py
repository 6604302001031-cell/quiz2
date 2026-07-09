import os
import json
import time
import csv
import io
import re
import urllib.request
import urllib.error
import base64

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

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

# 📌 ใช้ฟังก์ชันสร้าง State เริ่มต้น
def get_default_state():
    return {
        "is_started": False,
        "is_end": False,
        "current_index": 0,
        "is_time_up": False,
        "school_scores": {},  
        "player_scores": {},  
        "current_answers": {} 
    }

# 🚀 [แก้ไขเพื่อ Vercel] สร้างตัวแปร Global เพื่อเก็บสถานะเกมแทนการบันทึกไฟล์
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
    return sum(1 for t in active_users_memory.values() if current_time - t < 10)


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
# 🏫 API สำหรับส่งรายชื่อโรงเรียนกลับไปที่หน้าเว็บ
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
            "โรงเรียนศรียาภัย", "โรงเรียนสะอาดเผดิมวิทยา", "โรงเรียนสวนกุหลาบวิทยาลัย ชุมพร",
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


# 🆕 [แก้ไขแล้ว] API สำหรับบันทึกโรงเรียนและส่งข้อมูลล็อกอินเข้า Google Sheet ทันที (ไม่ใช้ threading สำหรับ Serverless)
@app.route('/api/register-school', methods=['POST'])
def register_school():
    if 'role' not in session:
        return jsonify({'status': 'error', 'message': 'กรุณาล็อกอินด้วย Google ก่อน'}), 401
        
    data = request.json or {}
    school = data.get('school', '').strip()
    
    if not school:
        return jsonify({'status': 'error', 'message': 'กรุณาเลือกหรือระบุชื่อโรงเรียน'}), 400
        
    # บันทึกชื่อโรงเรียนลงใน Session ของ User คนนี้เพื่อใช้ผูกกับการส่งคำตอบ
    session['school'] = school
    
    email = session.get('email')
    name = session.get('name', 'ผู้เล่น')
    
    # 🛠️ แก้ไข: เปลี่ยนมาส่งข้อมูลแบบตรงๆ ไม่ผ่าน threading เพื่อรองรับสถาปัตยกรรมของ Vercel
    send_to_gsheet(email, name, school, "Login", "เข้าร่วมเกม")
    
    return jsonify({'status': 'success', 'message': 'บันทึกโรงเรียนและส่งข้อมูลเข้า Google Sheet เรียบร้อยแล้ว'})


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
    
    # 📌 1. รับค่าข้อที่ต้องการแทรกจาก Frontend
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
        
        # 📌 2. คำนวณตำแหน่งที่ต้องการแทรก (Index เริ่มต้นที่ 0)
        insert_index = len(questions) # ค่าเริ่มต้นคือต่อท้ายสุด (ถ้าไม่ได้ระบุเลข)
        
        if question_number_str.isdigit():
            target_number = int(question_number_str)
            insert_index = target_number - 1 # ลบ 1 เพราะข้อ 1 คือ index 0
            
            # ป้องกัน Index ติดลบ หรือเกินจำนวนโจทย์ที่มีอยู่
            if insert_index < 0:
                insert_index = 0
            elif insert_index > len(questions):
                insert_index = len(questions)

        # 📌 3. ใช้ .insert() เพื่อแทรกตรงกลางลิสต์ แทน .append()
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


@app.route('/api/state')
def get_state():
    db = load_db()
    email = session.get('email')
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

    if db["is_started"] and len(questions) > 0:
        current_idx = db["current_index"]
        current_q = questions[current_idx]["q"] if not db["is_end"] else ""
        correct_ans = questions[current_idx]["a"]
        img_url = questions[current_idx].get("image_url", "")
        
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
        "image_url": img_url,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "school_scores": db["school_scores"],
        "active_users_count": get_active_users_count()
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
            
    save_db(db)
    current_q = questions[current_idx]["q"] if current_idx < len(questions) else ""
    correct_ans = questions[current_idx]["a"] if current_idx < len(questions) else ""
    img_url = questions[current_idx].get("image_url", "") if current_idx < len(questions) else ""
    
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": True, "is_end": db["is_end"],
            "current_number": current_idx + 1, "question": current_q, "answer": correct_ans,
            "image_url": img_url,
            "correct_count": correct_count, "incorrect_count": incorrect_count,
            "school_scores": db["school_scores"],
            "active_users_count": get_active_users_count()
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
    
    if current_idx < len(questions):
        correct_answer = questions[current_idx]["a"]
        school_correct_counts = {}
        
        for email, player_data in list(db["current_answers"].items()):
            if not player_data.get("evaluated", False):
                school = player_data.get("school") or "ไม่ระบุสังกัด"
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
                "current_number": current_idx + 1, "question": "", "answer": "-", "image_url": "",
                "correct_count": 0, "incorrect_count": 0,
                "school_scores": db["school_scores"],
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
    
    return jsonify({
        "status": "success",
        "state": {
            "is_started": True, "is_time_up": False, "is_end": False,
            "current_number": db["current_index"] + 1, "question": next_q, "answer": next_a,
            "image_url": next_img,
            "correct_count": 0, "incorrect_count": 0,
            "school_scores": db["school_scores"],
            "active_users_count": get_active_users_count()
        }
    })


@app.route('/api/reset', methods=['POST'])
def reset_game():
    if session.get('role') != 'admin':
         return jsonify({"status": "error", "message": "ไม่มีสิทธิ์ทำรายการ"}), 403
         
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


# 📌 [แก้ไขแล้ว] ปรับเวลา Timeout ลงเหลือ 3 วินาที เพื่อไม่ให้เว็บค้างนานเกินไป
def send_to_gsheet(email, name, school, question_number, answer):
    # 👇 ลิงก์ Web App URL จาก Google Apps Script ของแอดมิน 👇
    webhook_url = "https://script.google.com/macros/s/AKfycbw9Xeju85-zSYqmDcB9xwphkOLZaAwoEexvi-vU5nCRHWsgtSc_LLdJrOzEWri09bNt/exec"
    
    if webhook_url == "ใส่_URL_WEB_APP_ของคุณที่นี่" or not webhook_url.startswith("http"):
        return # ข้ามถ้ายังไม่มีการตั้งค่า URL ของแอดมิน
        
    data = {
        "email": email,
        "name": name,
        "school": school,
        "question_number": question_number,
        "answer": answer
    }
    
    try:
        req = urllib.request.Request(webhook_url, method="POST")
        req.add_header('Content-Type', 'application/json')
        jsondata = json.dumps(data).encode('utf-8')
        # 🛠️ ปรับลด timeout เป็น 3 วินาที
        urllib.request.urlopen(req, data=jsondata, timeout=3)
    except Exception as e:
        print(f"Error sending data to Google Sheet: {e}")


# 🆕 [แก้ไขแล้ว] API สำหรับการส่งคำตอบ (เปลี่ยนมาส่งตรงๆ ไม่ผ่าน Threading เพื่อรองรับ Vercel)
@app.route('/api/submit', methods=['POST'])
def submit_answer():
    db = load_db()
    if db["is_time_up"] or db["is_end"] or not db["is_started"]:
        return jsonify({'status': 'error', 'message': 'ระบบไม่ได้เปิดรับคำตอบในขณะนี้'}), 400
        
    data = request.json or {}
    player_answer = data.get('answer', '')
    email = session.get('email') or data.get('player_id')
    
    # 📌 ให้อ่านจาก session['school'] ที่เคยลงทะเบียนเลือกโรงเรียนไว้ก่อนหน้าด้วย
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
    
    # สั่งส่งข้อมูลเข้าไปเก็บใน Google Sheets แบบเรียลไทม์หลังกดส่งคำตอบ
    current_question_number = db["current_index"] + 1
    
    # 🛠️ แก้ไข: เปลี่ยนมาส่งข้อมูลแบบตรงๆ ไม่ผ่าน threading เพื่อป้องกันเซิร์ฟเวอร์ฟรีตัดสายทิ้งกลางทาง
    send_to_gsheet(email, name, school, current_question_number, player_answer)
    
    return jsonify({'status': 'success', 'message': 'ส่งคำตอบสำเร็จ'})


@app.route('/api/my-score')
def get_my_score():
    db = load_db()
    email = session.get('email')
    score = db["player_scores"].get(email, 0)
    return jsonify({"score": score})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
