from flask import Flask, render_template, request, redirect, session, Response
from werkzeug.utils import secure_filename
from database import get_db_connection, init_db
from datetime import datetime
import os, queue, json

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'smartdoor-secret-change-in-production')

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

subscribers = []

def notify_all(message):
    """Kirim notifikasi ke semua subscriber (SSE)"""
    for q in list(subscribers):
        try:
            q.put_nowait(message)
        except:
            pass


# ======================
# LOGIN PAGE
# ======================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
            user = cur.fetchone()
            cur.close()
            conn.close()

            if user:
                session['user'] = username
                return redirect('/dashboard')
            else:
                return render_template('login.html', error="Login gagal!")
        except Exception as e:
            return render_template('login.html', error=f"Error: {str(e)}")

    return render_template('login.html')


# ======================
# DASHBOARD
# ======================
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, status, image_path, time FROM logs ORDER BY time DESC")
        logs = cur.fetchall()
        cur.close()
        conn.close()

        return render_template('dashboard.html', logs=logs)
    except Exception as e:
        return f"Error loading dashboard: {str(e)}"


# ======================
# LOGOUT
# ======================
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


# ======================
# API UNTUK ESP32 (MENERIMA GAMBAR JPEG RAW)
# ======================
@app.route('/api/alert', methods=['POST'])
def api_alert():
    try:
        # Status (OK atau FAIL)
        status = request.form.get('status', 'unknown')

        # Cek apakah ESP32 mengirim gambar
        raw = request.data
        image_url = None

        if raw and len(raw) > 0:
            filename = secure_filename(datetime.now().strftime("%Y%m%d%H%M%S") + ".jpg")
            save_path = os.path.join(UPLOAD_FOLDER, filename)

            with open(save_path, "wb") as f:
                f.write(raw)

            image_url = f"/{save_path.replace(os.path.sep, '/')}"

        # Simpan ke database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO logs (status, image_path) VALUES (%s, %s)", (status, image_url))
        conn.commit()
        cur.close()
        conn.close()

        # Kirim notifikasi real-time ke dashboard
        data = json.dumps({
            "status": status,
            "image": image_url,
            "time": datetime.now().strftime("%H:%M:%S")
        })

        notify_all(data)

        return "OK", 200
    
    except Exception as e:
        print(f"Error in /api/alert: {str(e)}")
        return f"Error: {str(e)}", 500


# ======================
# EVENT STREAM (Dashboard Real-time)
# ======================
@app.route('/events')
def events():
    def gen():
        q = queue.Queue()
        subscribers.append(q)
        try:
            while True:
                msg = q.get()
                yield f"data: {msg}\n\n"
        except GeneratorExit:
            subscribers.remove(q)

    return Response(gen(), mimetype='text/event-stream')


# ======================
# TEST ENDPOINT
# ======================
@app.route('/test')
def test():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DATABASE() as db, VERSION() as version")
        result = cur.fetchone()
        cur.close()
        conn.close()
        return f"✅ Database Connected!<br>DB: {result['db']}<br>Version: {result['version']}"
    except Exception as e:
        return f"❌ Database Error: {str(e)}"


if __name__ == '__main__':
    # Uncomment ini untuk init database pertama kali
    # init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
