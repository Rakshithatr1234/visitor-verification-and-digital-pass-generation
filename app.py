from flask import Flask, render_template, request,redirect,send_file,url_for,flash,send_from_directory,session
import sqlite3
import barcode
from barcode.writer import ImageWriter
import os
import uuid
from datetime import datetime,timedelta
from html2image import Html2Image
import pytesseract
from PIL import Image
import cv2
import re
pytesseract.pytesseract.tesseract_cmd = 'tesseract'

app = Flask(__name__)
app.secret_key = "secret123"

def check_aadhaar(filepath):
    try:
        # Convert to absolute path and normalize for Windows
        filepath = os.path.abspath(filepath)
        print(f"Processing file: {filepath}")
        print(f"File exists: {os.path.exists(filepath)}")
        
        img = cv2.imread(filepath)
        if img is None:
            print(f"Failed to read image: {filepath}")
            return "Suspicious"
        
        # Improve image quality for better OCR
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Apply image enhancement for better OCR
        _, gray = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        
        text = pytesseract.image_to_string(gray)
        print(f"OCR Text found: {text}")

        # Find 12 digit number (handle spaces and dashes)
        # First try to find digits with spaces: 6641 2804 9316
        match = re.search(r"\d{4}\s*\d{4}\s*\d{4}", text)
        
        if match:
            # Remove all spaces and non-digit characters from the matched group
            aadhaar_number = re.sub(r"\D", "", match.group())
        else:
            # Fallback to original pattern for consecutive 12 digits
            match = re.search(r"\b\d{12}\b", text)
            if not match:
                print("No 12-digit number found")
                return "Suspicious"
            aadhaar_number = match.group()
        print(f"Aadhaar number extracted: {aadhaar_number}")

        if validate_aadhaar(aadhaar_number):
            print(f"Valid Aadhaar: {aadhaar_number}")
            return "Valid"
        else:
            print(f"Invalid Aadhaar checksum: {aadhaar_number}")
            return "Invalid"
    except Exception as e:
        print(f"Error checking Aadhaar: {e}")
        import traceback
        traceback.print_exc()
        return "Suspicious"
    
# Verhoeff Validation Tables
d = [
[0,1,2,3,4,5,6,7,8,9],
[1,2,3,4,0,6,7,8,9,5],
[2,3,4,0,1,7,8,9,5,6],
[3,4,0,1,2,8,9,5,6,7],
[4,0,1,2,3,9,5,6,7,8],
[5,9,8,7,6,0,4,3,2,1],
[6,5,9,8,7,1,0,4,3,2],
[7,6,5,9,8,2,1,0,4,3],
[8,7,6,5,9,3,2,1,0,4],
[9,8,7,6,5,4,3,2,1,0]
]

p = [
[0,1,2,3,4,5,6,7,8,9],
[1,5,7,6,2,8,3,0,9,4],
[5,8,0,3,7,9,6,1,4,2],
[8,9,1,6,0,4,3,5,2,7],
[9,4,5,3,1,2,6,8,7,0],
[4,2,8,6,5,7,3,9,0,1],
[2,7,9,3,8,0,6,4,1,5],
[7,0,4,6,9,1,3,2,5,8]
]

def validate_aadhaar(number):
    c = 0
    number = number[::-1]
    for i in range(len(number)):
        c = d[c][p[i % 8][int(number[i])]]
    return c == 0




# folder to store uploaded ID proofs
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
     

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS visitors(
            
            visitor_code TEXT UNIQUE,
            name TEXT,
            phone TEXT,
            purpose TEXT,
            person TEXT,
            file TEXT,
            status TEXT DEFAULT 'Pending',
            visit_date TEXT,
            id_status TEXT DEFAULT 'Pending'
        )
    """)
    
    conn.commit()
    conn.close()

init_db()


@app.route("/")
def dashboard():
    return render_template("dashboard.html")

# ---------------- LOGIN PAGE ----------------
@app.route("/visitor_login")
def login():
     
     return render_template("visitor_login.html")
    


# ---------------- VISITOR FORM PAGE ----------------
@app.route("/visitor_form")
def visitor():
    return render_template("visitor_form.html")


# ---------------- SUBMIT VISITOR ----------------
@app.route("/submit", methods=["POST"])
def submit():
   
    visitor_code = "VIS-" + str(uuid.uuid4())[:8].upper()
    name = request.form.get("name")
    phone = request.form.get("phone")
    if not phone.isdigit() or len(phone) != 10:
     return "Phone number must be exactly 10 digits"

    purpose = request.form.get("purpose")
    person = request.form.get("person")

    file = request.files.get("idproof")

    # check upload
    if not file or file.filename == "":
        return "Please upload ID proof"

    # save file
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    ai_result = check_aadhaar(filepath)
    print("AI RESULT:", ai_result)   

    # connect database
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    

    # insert data
    cursor.execute("""
        INSERT INTO visitors(visitor_code,name, phone, purpose, person, file,status,Visit_date,id_status)
        VALUES (?,?, ?, ?, ?, ?,'Pending',?,?)
    """, (visitor_code,name, phone, purpose, person, filepath,datetime.now().strftime("%Y-%m-%d"),ai_result))

    conn.commit()
    conn.close()

    return render_template("visitor_success.html", visitor_code=visitor_code)

@app.route("/admin",methods=["GET"])
def admin():

    if not session.get('admin'):
        return redirect(url_for("admin_login"))
    
    search = request.args.get("search")
    date = request.args.get("date")
    

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if search:
        cursor.execute("SELECT * FROM visitors WHERE visitor_code=?", (search,))
        data = cursor.fetchall()
    elif date:
        cursor.execute("SELECT * FROM visitors WHERE visit_date=?", (date,))
        data = cursor.fetchall()
    else:
        cursor.execute("SELECT * FROM visitors")
        data = cursor.fetchall()

    # compute totals for the current result set
    total_visitors = len(data)
    total_approved = sum(1 for v in data if len(v) > 7 and v[7] == 'Approved')
    total_rejected = sum(1 for v in data if len(v) > 7 and v[7] == 'Rejected')

    conn.close()

    return render_template("admin.html", visitors=data,
                           total_visitors=total_visitors,
                           total_approved=total_approved,
                           total_rejected=total_rejected,
                           filter_date=date)


@app.route("/delete/<int:vid>")
def delete(vid):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM visitors WHERE id=?", (vid,))

    conn.commit()
    conn.close()
      
    flash("Visitor deleted successfully")
    return redirect(url_for('admin'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('uploads', filename)


@app.route("/approve/<int:vid>")
def approve(vid):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE visitors SET status='Approved' WHERE id=?", (vid,))
    conn.commit()
    conn.close()

    return redirect(url_for('admin'))


@app.route("/reject/<int:vid>")
def reject(vid):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE visitors SET status='Rejected' WHERE id=?", (vid,))
    conn.commit()
    conn.close()

    return redirect(url_for('admin'))


@app.route("/update_id_status/<int:vid>/<status>")
def update_id_status(vid, status):
    if status not in ["Valid", "Invalid", "Suspicious"]:
        return redirect(url_for('admin'))
    
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE visitors SET id_status=? WHERE id=?", (status, vid))
    conn.commit()
    conn.close()

    flash(f"ID Status updated to {status}")
    return redirect(url_for('admin'))


@app.route("/recheck_aadhaar/<int:vid>")
def recheck_aadhaar(vid):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT file FROM visitors WHERE id=?", (vid,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        filepath = result[0]
        ai_result = check_aadhaar(filepath)
        
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE visitors SET id_status=? WHERE id=?", (ai_result, vid))
        conn.commit()
        conn.close()
        
        flash(f"Aadhaar rechecked. Status: {ai_result}")
    
    return redirect(url_for('admin'))


@app.route('/admin_login', methods=['GET','POST'])
def admin_login():
    error = None 
    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        # simple default admin login
        if username == "admin" and password == "admin123":
            session['admin'] = True
            return redirect('/admin')
        else:
             error = "Invalid login credentials"

    return render_template("admin_login.html", error=error)

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect('/admin_login')

@app.route("/admin_logout")
def admin_logout():
    session.pop("admin", None)   # remove admin session
    return redirect(url_for("admin_login"))

@app.route("/visitor_login", methods=["POST"])
def visitor_login():

    visitor_id = request.form.get("visitor_id")
    phone = request.form.get("phone")

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()

    
    cursor.execute(
        "SELECT * FROM visitors WHERE visitor_code=? AND phone=?",
        (visitor_id, phone)
    )

    data = cursor.fetchone()
    conn.close()

    if data:
        return render_template("visitor_status.html", visitor=data)
    else:
        error = "❌ Invalid Visitor ID or Phone Number! Please check and try again."
        return render_template("visitor_login.html", error=error)
    
@app.route("/view_pass/<visitor_code>")
def view_pass(visitor_code):

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM visitors WHERE visitor_code=?", (visitor_code,))
    visitor = cur.fetchone()
    conn.close()

    # CURRENT DATE & TIME
    now = datetime.now()

    current_date = now.strftime("%d-%m-%Y")
    current_time = now.strftime("%I:%M %p")

    # VALIDITY = +7 HOURS
    validity = (now + timedelta(hours=7)).strftime("%I:%M %p")

    # GENERATE BARCODE
    barcode_path = generate_barcode(visitor_code)

    return render_template(
        "visitor_pass.html",
        visitor=visitor,
        barcode_path=barcode_path,
        date=current_date,
        time=current_time,
        validity=validity
    )
       

@app.route("/download_pass/<visitor_code>")
def download_pass(visitor_code):

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM visitors WHERE visitor_code=?", (visitor_code,))
    visitor = cur.fetchone()
    conn.close()

    now = datetime.now()

    current_date = now.strftime("%d-%m-%Y")
    current_time = now.strftime("%I:%M %p")

    # VALIDITY = +7 HOURS
    validity = (now + timedelta(hours=7)).strftime("%I:%M %p")

    # GENERATE BARCODE
    barcode_path = generate_barcode(visitor_code)
    
    # Convert to file:// URL for Html2Image to access the barcode
    barcode_full_path = os.path.abspath(f"static/{barcode_path}")
    barcode_file_url = f"file:///{barcode_full_path}".replace("\\", "/")
  
    html = render_template(
        "visitor_pass.html",
        visitor=visitor,
        barcode_path=barcode_file_url,
        date=current_date,
        time=current_time,
        validity=validity
    )

    # convert to image
hti = Html2Image(output_path="static/passes")

    filename = f"{visitor_code}.png"

    hti.screenshot(
        html_str=html,
        save_as=filename,
        size=(600, 900)
    )

    return send_file(
        f"static/passes/{filename}",
        as_attachment=True
    )



def generate_barcode(code):

    folder = "static/barcodes"

    if not os.path.exists(folder):
        os.makedirs(folder)

    filename = f"{folder}/{code}"

    Code128 = barcode.get_barcode_class('code128')
    my_code = Code128(code, writer=ImageWriter())

    my_code.save(filename)

    return f"barcodes/{code}.png"


# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    if __name__ == "__main__":
    app.run(debug=True)



