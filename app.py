import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, g, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", secrets.token_hex(32)),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
)

DATABASE_PATH = os.environ.get("DATABASE_PATH", "portal.sqlite3")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(os.path.abspath(DATABASE_PATH)), exist_ok=True)
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'editor', 'viewer')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    username = os.environ.get("ADMIN_USERNAME", "admin").strip()
    password = os.environ.get("ADMIN_PASSWORD")
    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if not existing:
        if not password:
            raise RuntimeError("ADMIN_PASSWORD must be set before first start")
        now = utc_now()
        db.execute(
            "INSERT INTO users (username, full_name, password_hash, role, is_active, created_at, updated_at) VALUES (?, ?, ?, 'admin', 1, ?, ?)",
            (username, "Administrator", generate_password_hash(password), now, now),
        )
        db.commit()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute(
        "SELECT id, username, full_name, role, is_active, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def require_auth(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or not user["is_active"]:
            session.clear()
            return jsonify({"error": "Avval tizimga kiring"}), 401
        g.current_user = user
        return handler(*args, **kwargs)

    return wrapped


def require_admin(handler):
    @wraps(handler)
    @require_auth
    def wrapped(*args, **kwargs):
        if g.current_user["role"] != "admin":
            return jsonify({"error": "Bu amal uchun ruxsat yo'q"}), 403
        return handler(*args, **kwargs)

    return wrapped


@app.before_request
def verify_csrf():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.endpoint != "login":
        expected = session.get("csrf_token", "")
        supplied = request.headers.get("X-CSRF-Token", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            return jsonify({"error": "Xavfsizlik tokeni yaroqsiz"}), 403


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'self'"
    )
    return response


@app.get("/")
def landing():
    return render_template("landing.html")


@app.get("/control_admin")
@app.get("/control_admin/")
def control_admin():
    return render_template("admin.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user or not user["is_active"] or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Login yoki parol noto'g'ri"}), 401
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    return jsonify({"ok": True, "csrf_token": csrf_token()})


@app.post("/api/auth/logout")
@require_auth
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/auth/me")
@require_auth
def me():
    return jsonify({"user": dict(g.current_user), "csrf_token": csrf_token()})


@app.get("/api/users")
@require_admin
def list_users():
    users = get_db().execute(
        "SELECT id, username, full_name, role, is_active, created_at, updated_at FROM users ORDER BY id"
    ).fetchall()
    return jsonify({"users": [dict(user) for user in users]})


def validate_user_payload(payload, editing=False):
    username = str(payload.get("username", "")).strip()
    full_name = str(payload.get("full_name", "")).strip()
    password = str(payload.get("password", ""))
    role = str(payload.get("role", "viewer"))
    if len(username) < 3 or len(username) > 40:
        return None, "Login 3 dan 40 belgigacha bo'lishi kerak"
    if len(full_name) < 2 or len(full_name) > 80:
        return None, "Ism 2 dan 80 belgigacha bo'lishi kerak"
    if role not in {"admin", "editor", "viewer"}:
        return None, "Rol noto'g'ri"
    if (not editing or password) and len(password) < 8:
        return None, "Parol kamida 8 belgidan iborat bo'lishi kerak"
    return {"username": username, "full_name": full_name, "password": password, "role": role}, None


@app.post("/api/users")
@require_admin
def create_user():
    data, error = validate_user_payload(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    now = utc_now()
    try:
        cursor = get_db().execute(
            "INSERT INTO users (username, full_name, password_hash, role, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
            (data["username"], data["full_name"], generate_password_hash(data["password"]), data["role"], now, now),
        )
        get_db().commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Bu login band"}), 409
    return jsonify({"id": cursor.lastrowid}), 201


@app.put("/api/users/<int:user_id>")
@require_admin
def update_user(user_id):
    payload = request.get_json(silent=True) or {}
    data, error = validate_user_payload(payload, editing=True)
    if error:
        return jsonify({"error": error}), 400
    target = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not target:
        return jsonify({"error": "Foydalanuvchi topilmadi"}), 404
    is_active = 1 if payload.get("is_active", True) else 0
    if user_id == g.current_user["id"] and (not is_active or data["role"] != "admin"):
        return jsonify({"error": "O'zingizning admin ruxsatingizni olib tashlay olmaysiz"}), 400
    password_hash = target["password_hash"]
    if data["password"]:
        password_hash = generate_password_hash(data["password"])
    try:
        get_db().execute(
            "UPDATE users SET username = ?, full_name = ?, password_hash = ?, role = ?, is_active = ?, updated_at = ? WHERE id = ?",
            (data["username"], data["full_name"], password_hash, data["role"], is_active, utc_now(), user_id),
        )
        get_db().commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Bu login band"}), 409
    return jsonify({"ok": True})


@app.delete("/api/users/<int:user_id>")
@require_admin
def delete_user(user_id):
    if user_id == g.current_user["id"]:
        return jsonify({"error": "O'zingizni o'chira olmaysiz"}), 400
    cursor = get_db().execute("DELETE FROM users WHERE id = ?", (user_id,))
    get_db().commit()
    if not cursor.rowcount:
        return jsonify({"error": "Foydalanuvchi topilmadi"}), 404
    return jsonify({"ok": True})


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)

