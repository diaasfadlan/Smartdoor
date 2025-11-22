from flask import Flask, render_template, request, redirect, session, Response
from werkzeug.utils import secure_filename
from database import init_db
from datetime import datetime
import os, queue, json

app = Flask(__name__)
app.secret_key = "smartdoor-secret"
mysql = init_db(app)

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

subscribers = []

def notify_all(message):
    for q in list(subscribers):
        try:
            q.put_nowait(message)
        except:
            pass

@app.route('/', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s AND password=%s",(username,password))
        user = cur.fetchone()
        cur.close()

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
    cur = mysql.connection.cursor()
    cur.execute("SELECT id,status,image_path,time FROM logs ORDER BY time DESC")
    logs = cur.fetchall()
    cur.close()
    return render_template('dashboard.html', logs=logs)

@app.route('/api/alert', methods=['POST'])
def api_alert():
    status = request.form.get('status','unknown')
    image_url = None

    if 'image' in request.files:
        img = request.files['image']
        filename = secure_filename(datetime.now().strftime("%Y%m%d%H%M%S") + ".jpg")
        path = os.path.join(UPLOAD_FOLDER, filename)
        img.save(path)
        image_url = f"/{path.replace(os.path.sep, '/')}"

    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO logs (status,image_path) VALUES (%s,%s)", (status, image_url))
    mysql.connection.commit()
    cur.close()

    data = json.dumps({
        "status": status,
        "image": image_url,
        "time": datetime.now().strftime("%H:%M:%S")
    })

    notify_all(data)
    return "OK", 200

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
