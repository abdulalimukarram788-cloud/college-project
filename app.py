from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import sys
from datetime import datetime
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / 'data.db'
UPLOAD_FOLDER = BASE_DIR / 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-change-me'
app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)

def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    if not UPLOAD_FOLDER.exists():
        UPLOAD_FOLDER.mkdir()
    conn = get_db_conn()
    c = conn.cursor()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'student',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        category TEXT,
        description TEXT,
        image TEXT,
        status TEXT DEFAULT 'Pending',
        admin_comment TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(student_id) REFERENCES users(id)
    );
    ''')
    admin_email = 'admin@example.com'
    admin_pass = 'adminpass'
    try:
        c.execute('INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)', (
            'Admin', admin_email, generate_password_hash(admin_pass), 'admin'
        ))
    except sqlite3.IntegrityError:
        pass
    conn.commit()
    conn.close()
    print('Initialized DB and created default admin:', admin_email, admin_pass)

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        conn = get_db_conn()
        try:
            conn.execute('INSERT INTO users (name,email,password) VALUES (?,?,?)', (
                name, email, generate_password_hash(password)
            ))
            conn.commit()
            flash('Registered! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists.', 'danger')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db_conn()
        user = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['role'] = user['role']
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    role = session.get('role')
    conn = get_db_conn()
    if role == 'admin':
        complaints = conn.execute('SELECT c.*, u.name as student_name FROM complaints c LEFT JOIN users u ON c.student_id=u.id ORDER BY c.created_at DESC').fetchall()
        conn.close()
        return render_template('admin_dashboard.html', complaints=complaints)
    else:
        complaints = conn.execute('SELECT * FROM complaints WHERE student_id=? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
        conn.close()
        return render_template('student_dashboard.html', complaints=complaints)

@app.route('/submit', methods=['GET','POST'])
def submit_complaint():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        category = request.form['category']
        description = request.form['description']
        filename = None
        file = request.files.get('image')
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(f"{datetime.utcnow().timestamp()}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            try:
                img = Image.open(filepath)
                img.thumbnail((1024,1024))
                img.save(filepath)
            except Exception:
                pass
        conn = get_db_conn()
        conn.execute('INSERT INTO complaints (student_id,category,description,image) VALUES (?,?,?,?)', (
            session['user_id'], category, description, filename
        ))
        conn.commit()
        conn.close()
        flash('Complaint submitted', 'success')
        return redirect(url_for('dashboard'))
    return render_template('submit.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/complaint/<int:cid>', methods=['GET','POST'])
def complaint_detail(cid):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_conn()
    comp = conn.execute('SELECT c.*, u.name as student_name, u.email as student_email FROM complaints c LEFT JOIN users u ON c.student_id=u.id WHERE c.id=?', (cid,)).fetchone()
    if not comp:
        conn.close()
        flash('Not found', 'danger')
        return redirect(url_for('dashboard'))
    if request.method == 'POST' and session.get('role') == 'admin':
        status = request.form.get('status')
        comment = request.form.get('admin_comment')
        conn.execute('UPDATE complaints SET status=?, admin_comment=? WHERE id=?', (status, comment, cid))
        conn.commit()
        conn.close()
        flash('Updated', 'success')
        return redirect(url_for('dashboard'))
    conn.close()
    return render_template('complaint_detail.html', comp=comp)


@app.route('/complaint/<int:cid>/delete', methods=['POST'])
def delete_complaint(cid):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_conn()
    comp = conn.execute('SELECT * FROM complaints WHERE id=?', (cid,)).fetchone()
    if not comp:
        conn.close()
        flash('Complaint not found.', 'danger')
        return redirect(url_for('dashboard'))

    # Only admin or the owner can delete
    if not (session.get('role') == 'admin' or comp['student_id'] == session.get('user_id')):
        conn.close()
        flash('Not authorized to delete this complaint.', 'danger')
        return redirect(url_for('dashboard'))

    # remove image file if exists
    if comp['image']:
        try:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'], comp['image'])
            if os.path.exists(img_path):
                os.remove(img_path)
        except Exception:
            pass

    conn.execute('DELETE FROM complaints WHERE id=?', (cid,))
    conn.commit()
    conn.close()
    flash('Complaint deleted.', 'success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'initdb':
            init_db()
        elif cmd == 'run':
            app.run(debug=True)
        else:
            print('Unknown command')
    else:
        print('Usage: python app.py [initdb|run]')
