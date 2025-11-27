from flask import Flask, render_template, request, redirect, session, Response
from werkzeug.utils import secure_filename
from database import get_db_connection
from datetime import datetime
import os, queue, json

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'smartdoor-secret-change-in-production')

# Pastikan folder upload berada di static/uploads sehingga dapat di-serve
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

subscribers = []

def notify_all(message):
    for q in list(subscribers):
        try:
            q.put_nowait(message)
        except:
            pass


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s AND password=%s",
                    (username, password))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            session['user'] = username
            return redirect('/dashboard')
        else:
            return render_template('login.html', error="Login gagal!")

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, status, image_path, time FROM logs ORDER BY id DESC LIMIT 50")
    logs = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('dashboard.html', logs=logs)


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


@app.route('/api/alert', methods=['POST'])
def api_alert():
    """
    Dapat menerima:
    - multipart/form-data dengan field 'image' (browser / form)
    - raw JPEG bytes di body (ESP32 mengirim image JPEG langsung)
    Status dapat dikirim sebagai:
    - form field 'status'
    - query param 'status'
    - header 'X-Status' (opsional)
    """
    try:
        # ambil status dari form / query / header
        status = request.form.get('status') or request.args.get('status') or request.headers.get('X-Status') or 'unknown'
        image_url = None

        # nama file berbasis timestamp
        filename = datetime.now().strftime("%Y%m%d%H%M%S") + ".jpg"
        save_path = os.path.join(UPLOAD_FOLDER, filename)

        # 1) Jika ada multipart file 'image'
        if 'image' in request.files and request.files['image'].filename != '':
            file = request.files['image']
            # gunakan nama file timestamp agar unik, tetapi simpan ekstensi asli jika perlu
            filename = secure_filename(filename)
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(save_path)

        else:
            # 2) Cek raw body (ESP32 biasanya kirim JPEG di request.data)
            raw = request.get_data()
            if raw and len(raw) > 0:
                # simpan raw bytes ke file
                with open(save_path, "wb") as f:
                    f.write(raw)
            else:
                # tidak ada gambar — biarkan image_url = None
                save_path = None

        # Jika file disimpan, buat URL absolut agar selalu bisa diakses
        if save_path:
            base_url = request.host_url.rstrip('/')  # contoh: https://smartdoor-production.up.railway.app
            image_url = f"{base_url}/static/uploads/{os.path.basename(save_path)}"
        else:
            image_url = None

        # Simpan record ke DB
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO logs (status, image_path, time)
            VALUES (%s, %s, NOW())
        """, (status, image_url))
        conn.commit()
        cur.close()
        conn.close()

        # Kirim SSE notifikasi ke dashboard
        msg = json.dumps({
            "status": status,
            "image": image_url,
            "time": datetime.now().strftime("%H:%M:%S")
        })
        notify_all(msg)

        return "OK", 200

    except Exception as e:
        print("API ERROR:", e)
        return str(e), 500


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


@app.route('/test')
def test():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DATABASE(), VERSION()")
        res = cur.fetchone()
        cur.close()
        conn.close()
        return f"DB OK<br>{res}"
    except Exception as e:
        return f"DB ERROR: {str(e)}"


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
