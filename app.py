from flask import Flask, render_template, request, redirect, session, Response, url_for
from database import get_db_connection
from datetime import datetime
import base64, os, queue, json

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'smartdoor-secret-change-in-production')

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
    cursor = db.cursor()
    cursor.execute("SELECT id, status, image_path, time FROM logs ORDER BY id DESC")
    rows = cursor.fetchall()
    
    logs = []
    for row in rows:
        img_data = row[2]
        if img_data:
            try:
                # Konversi HEX BLOB → BASE64
                img_base64 = base64.b64encode(img_data).decode('utf-8')
            except:
                img_base64 = None
        else:
            img_base64 = None

        logs.append((row[0], row[1], img_base64, row[3]))

    return render_template("dashboard.html", logs=logs)


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')


@app.route('/api/alert', methods=['POST'])
def api_alert():
    try:
        status = request.form.get('status', 'unknown')
        image_blob = None

        if 'image' in request.files:
            image_blob = request.files['image'].read()
        elif request.data and len(request.data) > 50:
            image_blob = request.data

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO logs (status, image_path, time)
            VALUES (%s, %s, NOW())
        """, (status, image_blob))
        conn.commit()
        cur.close()
        conn.close()

        return "OK", 200

    except Exception as e:
        print("API ERROR:", e)
        return str(e), 500


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)

