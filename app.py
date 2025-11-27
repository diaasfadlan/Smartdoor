from flask import Flask, render_template, request, redirect, session, Response
from werkzeug.utils import secure_filename
from database import get_db_connection
from datetime import datetime
import os, queue, json

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'smartdoor-secret-change-in-production')

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
    try:
        status = request.form.get('status') or request.args.get('status') or 'unknown'
        image_url = None

        # Filename berbasis waktu
        filename = datetime.now().strftime("%Y%m%d%H%M%S") + ".jpg"
        save_path = os.path.join(UPLOAD_FOLDER, filename)

        # === Prioritas file upload ===
        if "image" in request.files and request.files["image"].filename != "":
            file = request.files["image"]
            filename = secure_filename(filename)
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(save_path)
            image_url = f"/static/uploads/{filename}"

        # === Kalau raw bytes / ESP kamera kirim binary ===
        elif request.data:
            with open(save_path, "wb") as f:
                f.write(request.data)
            image_url = f"/static/uploads/{filename}"

        # Save ke database (image_url boleh NULL)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO logs (status, image_path, time)
            VALUES (%s, %s, NOW())
        """, (status, image_url))
        conn.commit()
        cur.close()
        conn.close()

        # Kirim ke client real-time
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
            subscribers.remove(q)

    return Response(gen(), mimetype='text/event-stream')


@app.route('/test')
def test():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DATABASE(), VERSION()")
        res = cur.fetchone()
        return f"DB OK<br>{res}"
    except Exception as e:
        return f"DB ERROR: {str(e)}"


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
