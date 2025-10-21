import os
import sqlite3
import qrcode
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, Response, jsonify
from werkzeug.utils import secure_filename
from config import Config
import csv
from io import StringIO
import zipfile
import smtplib
from email.message import EmailMessage

app = Flask(__name__)
app.config.from_object(Config)

# ----------------- Database Initialization -----------------
def init_db():
    conn = sqlite3.connect('vcard.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        dob TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone TEXT NOT NULL,
        address TEXT NOT NULL,
        photo TEXT,
        designation TEXT,
        company TEXT,
        gender TEXT,
        qrcode TEXT
    )
    ''')
    
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]

    new_fields = {
        "designation": "TEXT",
        "company": "TEXT",
        "gender": "TEXT",
        "qrcode": "TEXT"
    }
    for field, datatype in new_fields.items():
        if field not in columns:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {field} {datatype}")
    
    conn.commit()
    conn.close()

init_db()

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['QRCODE_FOLDER'], exist_ok=True)

def get_db():
    conn = sqlite3.connect('vcard.db')
    conn.row_factory = sqlite3.Row
    return conn

# Function to add logo to QR code
def add_logo_to_qr(qr_img, logo_path):
    # Open the logo image
    try:
        logo = Image.open(logo_path)
        
        # Calculate logo size (about 1/5 of QR code size)
        qr_width, qr_height = qr_img.size
        logo_size = min(qr_width, qr_height) // 5
        
        # Resize logo
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
        
        # Calculate position to center the logo
        pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
        
        # Create a transparent overlay for the logo
        qr_img = qr_img.convert("RGBA")
        overlay = Image.new('RGBA', qr_img.size, (255, 255, 255, 0))
        overlay.paste(logo, pos, mask=logo if logo.mode == 'RGBA' else None)
        
        # Composite the QR code with the logo overlay
        qr_img = Image.alpha_composite(qr_img, overlay)
        
        return qr_img
    except Exception as e:
        print(f"Error adding logo to QR code: {e}")
        return qr_img

# ----------------- Routes -----------------
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == app.config['ADMIN_USERNAME'] and password == app.config['ADMIN_PASSWORD']:
            session['admin'] = username 
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'danger')  

    return render_template('login.html', logo='static/logo.png')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash('You have been logged out successfully!', 'success') 
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'admin' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return render_template('dashboard.html', users=users, logo='static/logo.png')

@app.route('/create_user', methods=['GET', 'POST'])
def create_user():
    if 'admin' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':    
        name = request.form['name']
        dob = request.form['dob']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        designation = request.form.get('designation', '')
        company = request.form.get('company', '')
        gender = request.form.get('gender', '')

        # Handle photo
        file = request.files.get('photo')
        filename = None
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

        # Insert into DB
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (name, dob, email, phone, address, photo, designation, company, gender)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, dob, email, phone, address, filename, designation, company, gender))
        user_id = cur.lastrowid
        conn.commit()

        # vCard URL (points to vcard.html page, not download)
        vcard_url = url_for('vcard', user_id=user_id, _external=True)

        # Generate QR code with high error correction for logo
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction for logo
            box_size=10,
            border=4
        )
        qr.add_data(vcard_url)
        qr.make(fit=True)
        
        # Create QR code image
        qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGBA')
        
        # Add logo to QR code
        logo_path = os.path.join('static', 'company_logo.jpg')
        if os.path.exists(logo_path):
            qr_img = add_logo_to_qr(qr_img, logo_path)
        
        # Save QR code
        qr_path = os.path.join(app.config['QRCODE_FOLDER'], f"user_{user_id}.png")
        qr_img.save(qr_path)

        # Update DB with QR code filename
        conn.execute("UPDATE users SET qrcode=? WHERE id=?", (f"user_{user_id}.png", user_id))
        conn.commit()
        conn.close()

        return redirect(url_for('dashboard', message="User created successfully!"))

    return render_template('create_user.html', logo='static/logo.png')

@app.route('/vcard/<int:user_id>')
def vcard(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return render_template('vcard.html', user=user, logo='static/logo.png')

@app.route('/download_vcard/<int:user_id>')
def download_vcard(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    vcard_data = f"""BEGIN:VCARD
VERSION:3.0
FN:{user['name']}
TITLE:{user['designation'] or ''}
ORG:{user['company'] or ''}
TEL:{user['phone']}
EMAIL:{user['email']}
ADR:{user['address']}
NOTE:Gender - {user['gender'] or ''}
END:VCARD
"""
    filepath = os.path.join('static/uploads', f"{user['name']}.vcf")
    with open(filepath, 'w') as f:
        f.write(vcard_data)

    return send_file(filepath, as_attachment=True)

# New route to download QR code with logo
@app.route('/download_qr/<int:user_id>')
def download_qr(user_id):
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    
    if not user:
        flash('User not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    # vCard URL (points to vcard.html page, not download)
    vcard_url = url_for('vcard', user_id=user_id, _external=True)
    
    # Generate QR code with high error correction for logo
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction for logo
        box_size=10,
        border=4
    )
    qr.add_data(vcard_url)
    qr.make(fit=True)
    
    # Create QR code image
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGBA')
    
    # Add logo to QR code
    logo_path = os.path.join('static', 'company_logo.jpg')
    if os.path.exists(logo_path):
        qr_img = add_logo_to_qr(qr_img, logo_path)
    
    # Save QR code temporarily
    temp_qr_path = os.path.join(app.config['QRCODE_FOLDER'], f"temp_user_{user_id}.png")
    qr_img.save(temp_qr_path)
    
    # Send the file
    return send_file(temp_qr_path, as_attachment=True, download_name=f"{user['name']}_QR.png")

# ----------------- Delete User -----------------
@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    
    if user:
        # Delete photo if exists
        if user['photo']:
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], user['photo'])
            if os.path.exists(photo_path):
                os.remove(photo_path)
        
        # Delete QR code if exists
        if user['qrcode']:
            qr_path = os.path.join(app.config['QRCODE_FOLDER'], user['qrcode'])
            if os.path.exists(qr_path):
                os.remove(qr_path)
        
        # Delete user from database
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        flash('User deleted successfully!', 'success')
    else:
        flash('User not found!', 'danger')
    
    conn.close()
    return redirect(url_for('dashboard'))

# ----------------- Scanners Page -----------------
@app.route('/scanners')
def scanners():
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return render_template('scanners.html', users=users, logo='static/logo.png')

# ----------------- CSV & ZIP -----------------
@app.route('/export_users')
def export_users():
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Name', 'DOB', 'Email', 'Phone', 'Address', 'Designation', 'Company', 'Gender', 'Photo', 'QR Code'])
    for user in users:
        # Generate full URLs for photo and QR code
        photo_url = ""
        if user['photo']:
            photo_url = url_for('static', filename='uploads/' + user['photo'], _external=True)
        
        qr_code_url = ""
        if user['qrcode']:
            qr_code_url = url_for('static', filename='qrcodes/' + user['qrcode'], _external=True)
        
        cw.writerow([
            user['id'], user['name'], user['dob'], user['email'],
            user['phone'], user['address'], user['designation'],
            user['company'], user['gender'], photo_url, qr_code_url
        ])
    
    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition":"attachment;filename=all_users.csv"}
    )

@app.route('/download_all_vcards')
def download_all_vcards():
    if 'admin' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()

    zip_path = "static/uploads/all_vcards.zip"
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for user in users:
            vcard_data = f"""BEGIN:VCARD
VERSION:3.0
FN:{user['name']}
TITLE:{user['designation'] or ''}
ORG:{user['company'] or ''}
TEL:{user['phone']}
EMAIL:{user['email']}
ADR:{user['address']}
NOTE:Gender - {user['gender'] or ''}
END:VCARD"""
            vcard_filename = f"{user['name']}.vcf"
            temp_path = os.path.join('static/uploads', vcard_filename)
            with open(temp_path, 'w') as f:
                f.write(vcard_data)
            zipf.write(temp_path, arcname=vcard_filename)
    
    return send_file(zip_path, as_attachment=True)

# ----------------- Send vCard via Email -----------------
@app.route('/share_vcard/<int:user_id>', methods=['GET', 'POST'])
def share_vcard(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    if request.method == 'POST':
        recipient_email = request.form['email']

        # Prepare vCard
        vcard_data = f"""BEGIN:VCARD
VERSION:3.0
FN:{user['name']}
TITLE:{user['designation'] or ''}
ORG:{user['company'] or ''}
TEL:{user['phone']}
EMAIL:{user['email']}
ADR:{user['address']}
NOTE:Gender - {user['gender'] or ''}
END:VCARD
"""
        # Send email
        msg = EmailMessage()
        msg['Subject'] = f"vCard of {user['name']}"
        msg['From'] = app.config['MAIL_USERNAME']
        msg['To'] = recipient_email
        msg.set_content("Please find attached vCard.")
        msg.add_attachment(vcard_data.encode('utf-8'), maintype='text', subtype='vcard', filename=f"{user['name']}.vcf")

        try:
            with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                server.starttls()
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.send_message(msg)
            flash('vCard sent successfully!', 'success')
        except Exception as e:
            flash(f'Error sending email: {e}', 'danger')

        return redirect(url_for('dashboard'))

    return render_template('share_vcard.html', user=user, logo='static/logo.png')

# ----------------- Health Check -----------------
@app.route('/health')
def health():
    """Health check endpoint for Railway."""
    return jsonify({"status": "healthy"}), 200

# ----------------- End -----------------
if __name__ == '__main__':
    app.secret_key = app.config['SECRET_KEY']
    app.run(host='0.0.0.0', port=5000, debug=False)
