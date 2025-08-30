"""
iris_app.py

A single-file Python application that:
- Uses Flask + pywebview + docx2pdf + JSON persistence
- Different background images for user login vs. user dashboard, and a separate one for main/admin
- docx->pdf inline for .docx; inline <img> for .jpg/.png/.webp, etc.
- Safe file delete (PermissionError)
- Full exit with short delay
- All routes return valid responses
"""

import os
import json
import threading
import uuid
import time
import sys

import webview
from flask import (
    Flask, request, redirect, url_for, render_template_string,
    session, flash, send_from_directory, abort
)
from werkzeug.utils import secure_filename
from docx2pdf import convert

print("DEBUG: Starting iris_app.py...")

app = Flask(__name__)
app.secret_key = 'CHANGE_THIS_TO_SOMETHING_SECRET'  # Replace in production

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

USER_DATA_FILE = 'users.json'
USERS = {}

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'
ADMIN_IRIS_PATH = 'admin_iris.jpg'  # For admin's iris check

def load_users_from_json():
    global USERS
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
            USERS = json.load(f)
        print("DEBUG: Loaded user data from users.json")
    else:
        USERS = {}
        print("DEBUG: No users.json found, starting empty...")

def save_users_to_json():
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(USERS, f, indent=2)
    print("DEBUG: Saved user data to users.json")

load_users_from_json()

def iris_authenticate(uploaded_iris_path, stored_iris_path):
    # Basic placeholder check: filenames must match
    return os.path.basename(uploaded_iris_path) == os.path.basename(stored_iris_path)

# ------------------------------------------------------------------------------
# HTML Templates
# ------------------------------------------------------------------------------

# 1) Main + Admin pages => "myBackground.jpg"
MAIN_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Iris Secure Storage - Main Page</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {
      margin: 0; padding: 0;
      font-family: 'Poppins', sans-serif;
      color: #fff;
      display: flex; flex-direction: column; min-height: 100vh;
      background: url('/static/myBackground.jpg') no-repeat center center fixed;
      background-size: cover;
    }
    .centered-container {
      flex: 1; display: flex; justify-content: center; align-items: center;
    }
    .login-card {
      background-color: rgba(59, 51, 96, 0.9);
      border-radius: 8px; padding: 2rem;
      width: 100%; max-width: 400px; text-align: center;
    }
    .login-card h2 { color: #fff; margin-bottom: 0.5rem; }
    .login-card p { color: #ddd; margin-bottom: 2rem; }
    .btn-custom {
      background-color: #9F6BFF; border: none; color: #fff;
    }
    .btn-custom:hover { background-color: #8053cc; }
  </style>
</head>
<body>
  <div class="centered-container">
    <div class="login-card">
      <h2>Welcome</h2>
      <p>Iris Secure Storage system</p>
      <form action="{{ url_for('admin_login') }}" method="get" class="mb-3">
        <button class="btn btn-custom w-100" type="submit">Admin Login</button>
      </form>
      <form action="{{ url_for('user_login') }}" method="get" class="mb-3">
        <button class="btn btn-primary w-100" type="submit">User Login</button>
      </form>
      <form action="{{ url_for('exit_application') }}" method="post">
        <button class="btn btn-danger w-100" type="submit">Exit</button>
      </form>
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

ADMIN_LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Admin Login</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {
      margin: 0; padding: 0; font-family: 'Poppins', sans-serif; color: #fff;
      min-height: 100vh;
      background: url('/static/myBackground.jpg') no-repeat center center fixed;
      background-size: cover;
    }
    .login-container {
      background-color: rgba(59, 51, 96, 0.9);
      padding: 2rem; max-width: 600px;
      margin: 3rem auto; border-radius: 8px;
    }
    h2, label { color: #fff; }
  </style>
</head>
<body>
  <div class="login-container">
    <h2>Admin Login</h2>
    <form method="post" enctype="multipart/form-data">
      <div class="mb-3">
        <label>Password:</label>
        <input type="password" name="password" class="form-control" required>
      </div>
      <div class="mb-3">
        <label>Upload Admin Iris Image:</label>
        <input type="file" name="iris_image" accept="image/*" class="form-control" required>
      </div>
      <button class="btn btn-primary">Login</button>
    </form>
    <form action="{{ url_for('main_page') }}" method="get" class="mt-3">
      <button class="btn btn-secondary">Back</button>
    </form>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

ADMIN_DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>Admin Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {
      margin: 0; padding: 0; font-family: 'Poppins', sans-serif; color: #fff;
      min-height: 100vh;
      background: url('/static/myBackground.jpg') no-repeat center center fixed;
      background-size: cover;
    }
    .dashboard-container {
      background-color: rgba(59, 51, 96, 0.9);
      padding: 2rem; margin: 2rem auto; max-width: 1000px;
      border-radius: 8px;
    }
    h2, h5, label { color: #fff; }
    .table { background-color: #fff; color: #000; }
    .btn-secondary, .btn-danger, .btn-success {
      margin-top: 0.5rem;
    }
  </style>
</head>
<body>
  <div class="dashboard-container">
    <h2>Admin Dashboard</h2>
    <div class="mb-4">
      <h5>Add New User</h5>
      <form method="post" action="{{ url_for('add_user') }}" enctype="multipart/form-data">
        <div class="mb-3">
          <label>Name:</label>
          <input type="text" name="new_user_name" class="form-control" required>
        </div>
        <div class="mb-3">
          <label>Username:</label>
          <input type="text" name="new_user_username" class="form-control" required>
        </div>
        <div class="mb-3">
          <label>Iris Image:</label>
          <input type="file" name="new_user_iris" accept="image/*" class="form-control" required>
        </div>
        <button class="btn btn-success" type="submit">Add User</button>
      </form>
    </div>

    <div class="mb-4">
      <h5>Delete User</h5>
      <form method="post" action="{{ url_for('delete_user') }}">
        <div class="mb-3">
          <label>Username:</label>
          <input type="text" name="del_username" class="form-control" required>
        </div>
        <button class="btn btn-danger" type="submit">Delete User</button>
      </form>
    </div>

    <div class="mb-4">
      <h5>All Users</h5>
      <table class="table table-bordered">
        <thead>
          <tr>
            <th>Username</th>
            <th>Name</th>
            <th>Files</th>
            <th>Total Size</th>
          </tr>
        </thead>
        <tbody>
          {% for username, data in users.items() %}
          <tr>
            <td>{{ username }}</td>
            <td>{{ data.name }}</td>
            <td>{{ data.files|length }}</td>
            <td>{{ data.files|sum(attribute='1') }} bytes</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <form action="{{ url_for('logout') }}" method="post">
      <button class="btn btn-secondary">Logout</button>
    </form>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# 2) User pages => "userLogin.jpg" for user login, "userDashboard.jpg" for user dashboard

USER_LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>User Login</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {
      margin: 0; padding: 0;
      font-family: 'Poppins', sans-serif;
      color: #fff; min-height: 100vh;
      background: url('/static/userLogin.jpg') no-repeat center center fixed;
      background-size: cover;
    }
    .login-container {
      background-color: rgba(59, 51, 96, 0.9);
      padding: 2rem; max-width: 600px; margin: 3rem auto;
      border-radius: 8px;
    }
    h2, label { color: #fff; }
  </style>
</head>
<body>
  <div class="login-container">
    <h2>User Login</h2>
    <form method="post" enctype="multipart/form-data">
      <div class="mb-3">
        <label>Username:</label>
        <input type="text" name="username" class="form-control" required>
      </div>
      <div class="mb-3">
        <label>Upload Iris Image:</label>
        <input type="file" name="iris_image" accept="image/*" class="form-control" required>
      </div>
      <button class="btn btn-primary">Login</button>
    </form>

    <!-- Back to main page -->
    <form action="{{ url_for('main_page') }}" method="get" class="mt-3">
      <button class="btn btn-secondary">Back</button>
    </form>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

USER_DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>User Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {
      margin: 0; padding: 0;
      font-family: 'Poppins', sans-serif;
      color: #fff; min-height: 100vh;
      background: url('/static/userDashboard.jpg') no-repeat center center fixed;
      background-size: cover;
    }
    .dashboard-container {
      background-color: rgba(59, 51, 96, 0.9);
      padding: 2rem; margin: 2rem auto; max-width: 1000px;
      border-radius: 8px;
    }
    h2, h5, label { color: #fff; }
    .table { background-color: #fff; color: #000; }
    .btn-secondary, .btn-danger, .btn-primary, .btn-success {
      margin-top: 0.5rem;
    }
  </style>
</head>
<body>
  <div class="dashboard-container">
    <h2>User Dashboard</h2>
    <div class="mb-4">
      <h5>Upload File</h5>
      <form method="post" action="{{ url_for('user_upload_file') }}" enctype="multipart/form-data">
        <div class="mb-3">
          <label>Select File:</label>
          <input type="file" name="file" class="form-control" required>
        </div>
        <button class="btn btn-success">Upload</button>
      </form>
    </div>

    <div class="mb-4">
      <h5>Your Files</h5>
      <table class="table table-bordered">
        <thead>
          <tr><th>Filename</th><th>Size(bytes)</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {% for file_info in user_data.files %}
          <tr>
            <td>{{ file_info[0] }}</td>
            <td>{{ file_info[1] }}</td>
            <td>
              <a class="btn btn-primary btn-sm" href="{{ url_for('view_file_inline', filename=file_info[0]) }}">
                View
              </a>
              <a class="btn btn-danger btn-sm" href="{{ url_for('delete_file', filename=file_info[0]) }}">
                Delete
              </a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    <form method="post" action="{{ url_for('logout') }}">
      <button class="btn btn-secondary">Logout</button>
    </form>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ------------------------------------------------------------------------------
# 2) FLASK ROUTES
# ------------------------------------------------------------------------------
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # optional: 100MB upload limit

@app.route('/', methods=['GET'])
def main_page():
    return render_template_string(MAIN_PAGE_TEMPLATE)

@app.route('/exit', methods=['POST'])
def exit_application():
    def close_app():
        time.sleep(0.5)
        windows = webview.windows
        if windows:
            windows[0].destroy()
        sys.exit(0)
    threading.Thread(target=close_app, daemon=True).start()
    return "<html><body><h4>Closing application...</h4></body></html>"

@app.route('/admin_login', methods=['GET','POST'])
def admin_login():
    if request.method == 'GET':
        return render_template_string(ADMIN_LOGIN_TEMPLATE)
    else:
        pw = request.form.get('password')
        iris_image = request.files.get('iris_image')
        if not pw or not iris_image:
            flash("Missing admin credentials or iris image!")
            return redirect(url_for('admin_login'))

        iris_filename = secure_filename(iris_image.filename)
        iris_path = os.path.join(app.config['UPLOAD_FOLDER'], iris_filename)
        iris_image.save(iris_path)

        if pw == ADMIN_PASSWORD and iris_authenticate(iris_path, ADMIN_IRIS_PATH):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Admin authentication failed!")
            return redirect(url_for('admin_login'))

@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('main_page'))
    return render_template_string(ADMIN_DASHBOARD_TEMPLATE, 
                                  users=convert_users_to_template(USERS))

@app.route('/add_user', methods=['POST'])
def add_user():
    if not session.get('admin_logged_in'):
        return redirect(url_for('main_page'))

    new_user_name = request.form.get('new_user_name')
    new_user_username = request.form.get('new_user_username')
    new_user_iris = request.files.get('new_user_iris')

    if not (new_user_name and new_user_username and new_user_iris):
        flash("All fields are required!")
        return redirect(url_for('admin_dashboard'))

    if new_user_username in USERS:
        flash("User already exists!")
        return redirect(url_for('admin_dashboard'))

    iris_filename = secure_filename(new_user_iris.filename)
    iris_path = os.path.join(app.config['UPLOAD_FOLDER'], iris_filename)
    new_user_iris.save(iris_path)

    USERS[new_user_username] = {
        'name': new_user_name,
        'iris_path': iris_path,
        'files': []
    }
    save_users_to_json()
    flash(f"User '{new_user_username}' added.")
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_user', methods=['POST'])
def delete_user():
    if not session.get('admin_logged_in'):
        return redirect(url_for('main_page'))

    del_username = request.form.get('del_username')
    if del_username in USERS:
        del USERS[del_username]
        save_users_to_json()
        flash(f"User '{del_username}' deleted.")
    else:
        flash(f"User '{del_username}' not found.")
    return redirect(url_for('admin_dashboard'))

@app.route('/user_login', methods=['GET','POST'])
def user_login():
    if request.method == 'GET':
        return render_template_string(USER_LOGIN_TEMPLATE)
    else:
        username = request.form.get('username')
        iris_image = request.files.get('iris_image')
        if not (username and iris_image):
            flash("Missing username or iris image!")
            return redirect(url_for('user_login'))

        if username not in USERS:
            flash("No such user. Contact admin.")
            return redirect(url_for('user_login'))

        iris_filename = secure_filename(iris_image.filename)
        iris_path = os.path.join(app.config['UPLOAD_FOLDER'], iris_filename)
        iris_image.save(iris_path)

        stored_iris_path = USERS[username]['iris_path']
        if iris_authenticate(iris_path, stored_iris_path):
            session['user_logged_in'] = True
            session['username'] = username
            return redirect(url_for('user_dashboard'))
        else:
            flash("Iris authentication failed!")
            return redirect(url_for('user_login'))

@app.route('/user_dashboard')
def user_dashboard():
    if not session.get('user_logged_in'):
        return redirect(url_for('main_page'))
    username = session['username']
    user_data = USERS[username]
    return render_template_string(USER_DASHBOARD_TEMPLATE, user_data=user_data)

@app.route('/user_upload_file', methods=['POST'])
def user_upload_file():
    if not session.get('user_logged_in'):
        return redirect(url_for('main_page'))

    file = request.files.get('file')
    if not file:
        flash("No file selected!")
        return redirect(url_for('user_dashboard'))

    username = session['username']
    user_data = USERS[username]

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    file_size = os.path.getsize(file_path)
    user_data['files'].append((filename, file_size))
    save_users_to_json()

    flash(f"File '{filename}' uploaded.")
    return redirect(url_for('user_dashboard'))

@app.route('/view/<filename>')
def view_file_inline(filename):
    # Ensure user is logged in
    if not session.get('user_logged_in'):
        return redirect(url_for('main_page'))

    full_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(full_path):
        flash("File not found.")
        return redirect(url_for('user_dashboard'))

    ext = os.path.splitext(filename)[1].lower()
    if ext == '.pdf':
        # inline PDF
        return render_pdf_inline(filename)
    elif ext == '.docx':
        # convert docx->pdf
        converted_name = f"{uuid.uuid4()}.pdf"
        converted_path = os.path.join(app.config['UPLOAD_FOLDER'], converted_name)
        try:
            convert(full_path, converted_path)
            return render_pdf_inline(converted_name)
        except Exception as e:
            flash(f"Conversion failed: {e}")
            return redirect(url_for('user_dashboard'))

    # If image => .jpg, .png, .webp, .gif, etc. => show in <img>
    elif ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
        return render_image_inline(filename)

    else:
        flash("Unsupported file for inline view.")
        return redirect(url_for('user_dashboard'))

def render_pdf_inline(pdf_filename):
    pdf_url = url_for('inline_pdf_route', filename=pdf_filename)
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>View PDF Inline</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
      <style>
        body {{
          margin: 0; padding: 0; background-color: #000;
          display: flex; flex-direction: column; height: 100vh;
        }}
        .top-bar {{
          height: 3rem; background-color: #222;
          display: flex; align-items: center; padding: 0 1rem;
        }}
        .back-btn {{ margin: 0; }}
        iframe {{
          width: 100%; height: calc(100vh - 3rem);
          border: none;
        }}
      </style>
    </head>
    <body>
      <div class="top-bar">
        <a href="{url_for('user_dashboard')}" class="btn btn-secondary back-btn">Back</a>
      </div>
      <iframe src="{pdf_url}"></iframe>
    </body>
    </html>
    """
    return html

def render_image_inline(img_filename):
    # Serve the image via /inline-img/<filename>
    img_url = url_for('inline_img_route', filename=img_filename)
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>View Image Inline</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
      <style>
        body {{
          margin: 0; padding: 0; background-color: #000;
          display: flex; flex-direction: column; height: 100vh;
        }}
        .top-bar {{
          height: 3rem; background-color: #222;
          display: flex; align-items: center; padding: 0 1rem;
        }}
        .back-btn {{ margin: 0; }}
        .img-container {{
          flex: 1; display: flex; justify-content: center; align-items: center;
          background-color: #000;
        }}
        img {{
          max-width: 100%; max-height: 100%;
        }}
      </style>
    </head>
    <body>
      <div class="top-bar">
        <a href="{url_for('user_dashboard')}" class="btn btn-secondary back-btn">Back</a>
      </div>
      <div class="img-container">
        <img src="{img_url}" alt="inline image">
      </div>
    </body>
    </html>
    """
    return html

@app.route('/inline-pdf/<filename>')
def inline_pdf_route(filename):
    fp = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(fp):
        abort(404)
    resp = send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# Serve inline images
@app.route('/inline-img/<filename>')
def inline_img_route(filename):
    fp = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(fp):
        abort(404)
    # Serve the image directly, no as_attachment
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)

@app.route('/delete_file/<filename>')
def delete_file(filename):
    if not session.get('user_logged_in'):
        return redirect(url_for('main_page'))

    username = session['username']
    user_data = USERS[username]
    new_files = []
    for f, sz in user_data['files']:
        if f == filename:
            path = os.path.join(app.config['UPLOAD_FOLDER'], f)
            if os.path.exists(path):
                try:
                    os.remove(path)
                    flash(f"File '{f}' deleted.")
                except PermissionError:
                    flash(f"Cannot delete '{f}' because it's in use by another process.")
        else:
            new_files.append((f, sz))
    user_data['files'] = new_files
    save_users_to_json()
    return redirect(url_for('user_dashboard'))

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('main_page'))

def convert_users_to_template(users_dict):
    # For Jinja2 usage
    result = {}
    for uname, data in users_dict.items():
        result[uname] = type('Obj', (object,), {
            'name': data['name'],
            'files': data['files']
        })()
    return result

def run_flask():
    print("DEBUG: run_flask() - starting Flask on 127.0.0.1:5000")
    app.run(debug=False, port=5000, use_reloader=False)

if __name__ == '__main__':
    # Start Flask in a background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Create a pywebview window
    webview.create_window(
        title="Iris Secure Storage (Images + PDFs Inline, Multiple BGs)",
        url="http://127.0.0.1:5000",
        width=1000,
        height=700,
        resizable=True
    )
    webview.start()
    print("DEBUG: If you see this, the window closed or app ended.")
