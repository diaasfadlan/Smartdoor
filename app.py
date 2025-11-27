from flask import Flask, render_template, request, redirect, session, url_for
from database import get_db_connection
import base64, os

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'smartdoor-secret')


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
    cur.execute("SELECT id, status, image_path, time FROM logs ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()

    logs = []
    for row in rows:
        img_blob = row.get("image_path")
        img_base64 = base64.b64encode(img_blob).decode('utf-8') if img_blob else None

        logs.append({
            "id": row.get("id"),
            "status": row.get("status"),
            "image": img_base64,
            "time": row.get("time")
        })

    return render_template('dashboard.html', logs=logs)


@app.route('/logout')
def logout():
    session.clear()
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
            INSERT INTO logs (status, image_path)
            VALUES (%s, %s)
        """, (status, image_blob))
        conn.commit()
        conn.close()

        return "OK", 200

    except Exception as e:
        print("API ERROR:", e)
        return str(e), 500


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080, debug=True)
