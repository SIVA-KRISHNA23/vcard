import os
import sqlite3
import qrcode
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, Response
from werkzeug.utils import secure_filename
from config import Config
import csv
from io import StringIO
import zipfile
import smtplib
from email.message import EmailMessage

app = Flask(__name__)
app.config.from_object(Config)

# Make sure to set the secret key
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# ----------------- Database Initialization -----------------
def init_db():
    # Create database if it doesn't exist
    if not os.path.exists('vcard.db'):
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
        
        conn.commit()
        conn.close()
        print("Database initialized")
    else:
        # Check if new columns exist and add them if needed
        conn = sqlite3.connect('vcard.db')
        cursor = conn.cursor()
        
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

# Initialize database on startup
init_db()

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['QRCODE_FOLDER'], exist_ok=True)

def get_db():
    conn = sqlite3.connect('vcard.db')
    conn.row_factory = sqlite3.Row
    return conn

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

    return render_template('login.html')

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
    return render_template('dashboard.html', users=users)

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

        # vCard URL (using the actual domain)
        vcard_url = request.host_url + url_for('vcard', user_id=user_id)[1:]  # Remove leading slash

        # Generate QR code
        qr_img = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4
        )
        qr_img.add_data(vcard_url)
        qr_img.make(fit=True)
        img = qr_img.make_image(fill_color="black", back_color="white")
        qr_path = os.path.join(app.config['QRCODE_FOLDER'], f"user_{user_id}.png")
        img.save(qr_path)

        # Update DB with QR code filename
        conn.execute("UPDATE users SET qrcode=? WHERE id=?", (f"user_{user_id}.png", user_id))
        conn.commit()
        conn.close()

        flash("User created successfully!", "success")
        return redirect(url_for('dashboard'))

    return render_template('create_user.html')

@app.route('/vcard/<int:user_id>')
def vcard(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return render_template('vcard.html', user=user)

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
    cw.writerow(['ID', 'Name', 'DOB', 'Email', 'Phone', 'Address', 'Designation', 'Company', 'Gender'])
    for user in users:
        cw.writerow([
            user['id'], user['name'], user['dob'], user['email'],
            user['phone'], user['address'], user['designation'],
            user['company'], user['gender']
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

    return render_template('share_vcard.html', user=user)

# Health check endpoint for Railway
@app.route('/health')
def health():
    return {"status": "healthy"}

# ----------------- End -----------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
