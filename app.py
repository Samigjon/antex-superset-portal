import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import urljoin

import requests
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
SUPERSET_URL = os.environ.get("SUPERSET_URL", "").rstrip("/")
SUPERSET_USERNAME = os.environ.get("SUPERSET_USERNAME", "")
SUPERSET_PASSWORD = os.environ.get("SUPERSET_PASSWORD", "")


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

        CREATE TABLE IF NOT EXISTS superset_datasets (
            superset_id INTEGER PRIMARY KEY,
            table_name TEXT NOT NULL,
            schema_name TEXT,
            database_id INTEGER,
            database_name TEXT,
            synced_at TEXT NOT NULL
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


class SupersetConnectionError(RuntimeError):
    pass


def fetch_superset_datasets():
    if not all((SUPERSET_URL, SUPERSET_USERNAME, SUPERSET_PASSWORD)):
        raise SupersetConnectionError("Superset ulanish sozlamalari kiritilmagan")

    try:
        login_response = requests.post(
            urljoin(f"{SUPERSET_URL}/", "api/v1/security/login"),
            json={
                "username": SUPERSET_USERNAME,
                "password": SUPERSET_PASSWORD,
                "provider": "db",
                "refresh": True,
            },
            timeout=20,
        )
        login_response.raise_for_status()
        access_token = login_response.json()["access_token"]
    except (requests.RequestException, KeyError, ValueError) as error:
        raise SupersetConnectionError("Superset tizimiga ulanib bo'lmadi") from error

    headers = {"Authorization": f"Bearer {access_token}"}
    datasets = []
    page = 0
    page_size = 100

    while True:
        query = f"(page:{page},page_size:{page_size})"
        try:
            response = requests.get(
                urljoin(f"{SUPERSET_URL}/", "api/v1/dataset/"),
                params={"q": query},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("result", [])
        except (requests.RequestException, ValueError) as error:
            raise SupersetConnectionError("Superset datasetlarini olib bo'lmadi") from error

        datasets.extend(batch)
        if not batch or len(datasets) >= int(payload.get("count", len(datasets))):
            break
        page += 1

    return datasets


def sync_superset_datasets():
    datasets = fetch_superset_datasets()
    synced_at = utc_now()
    db = get_db()

    for dataset in datasets:
        database = dataset.get("database") or {}
        db.execute(
            """
            INSERT INTO superset_datasets (
                superset_id, table_name, schema_name, database_id, database_name, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(superset_id) DO UPDATE SET
                table_name = excluded.table_name,
                schema_name = excluded.schema_name,
                database_id = excluded.database_id,
                database_name = excluded.database_name,
                synced_at = excluded.synced_at
            """,
            (
                dataset["id"],
                dataset.get("table_name", ""),
                dataset.get("schema"),
                database.get("id"),
                database.get("database_name"),
                synced_at,
            ),
        )

    db.commit()
    return len(datasets), synced_at


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


@app.get("/api/datasets")
@require_admin
def list_datasets():
    datasets = get_db().execute(
        """
        SELECT superset_id, table_name, schema_name, database_id, database_name, synced_at
        FROM superset_datasets
        ORDER BY table_name COLLATE NOCASE, superset_id
        """
    ).fetchall()
    return jsonify({"datasets": [dict(dataset) for dataset in datasets]})


@app.post("/api/datasets/sync")
@require_admin
def sync_datasets():
    try:
        count, synced_at = sync_superset_datasets()
    except SupersetConnectionError as error:
        app.logger.warning("Superset dataset sync failed: %s", error)
        return jsonify({"error": str(error)}), 502
    return jsonify({"ok": True, "count": count, "synced_at": synced_at})


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

