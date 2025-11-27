from flask import Flask, render_template, request, redirect, session, Response, send_from_directory
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
# API UNTUK ESP32 (MENERIMA GAMBAR JPEG)
# - Accepts:
#   * multipart/form-data (field 'image')
#   * raw jpeg body (Content-Type: image/jpeg)
#   * header X-Status for status (FAIL / OK)
# ======================
@app.route('/api/alert', methods=['POST'])
def api_alert():
    try:
        # Prioritas: form 'status' -> query -> header X-Status -> default
        status = request.form.get('status') or request.args.get('status') or request.headers.get('X-Status') or 'unknown'

        image_url = None

        # 1) multipart file upload (common)
        if 'image' in request.files and request.files['image'].filename != '':
            file = request.files['image']
            filename = secure_filename(datetime.now().strftime("%Y%m%d%H%M%S") + "_" + file.filename)
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(save_path)
            image_url = f"/uploads/{filename}"

        else:
            # 2) raw body (ESP32 will send raw jpeg in body with content-type image/jpeg)
            raw = request.data
            if raw and len(raw) > 0:
                filename = secure_filename(datetime.now().strftime("%Y%m%d%H%M%S") + ".jpg")
                save_path = os.path.join(UPLOAD_FOLDER, filename)
                with open(save_path, "wb") as f:
                    f.write(raw)
                image_url = f"/uploads/{filename}"

        # Simpan ke database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO logs (status, image_path, time) VALUES (%s, %s, NOW())", (status, image_url))
        conn.commit()
        cur.close()
        conn.close()

        # Notify realtime ke dashboard (SSE)
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
# Serve uploaded images publicly
# ======================
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # Serve only from UPLOAD_FOLDER
    return send_from_directory(UPLOAD_FOLDER, filename)


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
            try:
                subscribers.remove(q)
            except:
                pass
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
    # init_db()  # uncomment if database not initialized yet
    app.run(host='0.0.0.0', port=5000, debug=True)
