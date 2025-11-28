# College Complaint Portal (Flask) - Beginner Hackathon Project

## Features
- Student register/login
- Submit complaints (category, description, optional image)
- Admin dashboard: view, assign, change status, comment
- Simple SQLite DB

## Quick start
1. Create a virtualenv: python -m venv venv
2. Activate it: Windows venv\Scripts\activate, Linux/Mac source venv/bin/activate
3. Install deps: pip install -r requirements.txt
4. Create uploads folder: mkdir uploads
5. Initialize DB: python app.py initdb
6. Run server: python app.py run
7. Open http://127.0.0.1:5000

Default admin created after initdb:
- email: admin@example.com
- password: adminpass
