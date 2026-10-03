import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import quote, urljoin

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
METABASE_URL = os.environ.get("METABASE_URL", "").rstrip("/")
METABASE_USERNAME = os.environ.get("METABASE_USERNAME", "")
METABASE_PASSWORD = os.environ.get("METABASE_PASSWORD", "")
SUPERSET_FOLDERS = ("Дашборд", "Аналитика Отчеты", "Конструктор отчетов")


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
            tags_json TEXT NOT NULL DEFAULT '[]',
            folder_name TEXT,
            synced_at TEXT NOT NULL
        );
        """
    )
    dataset_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(superset_datasets)").fetchall()
    }
    if "tags_json" not in dataset_columns:
        db.execute(
            "ALTER TABLE superset_datasets ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'"
        )
    if "folder_name" not in dataset_columns:
        db.execute("ALTER TABLE superset_datasets ADD COLUMN folder_name TEXT")
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
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


class MetabaseConnectionError(RuntimeError):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def metabase_client():
    if not all((METABASE_URL, METABASE_USERNAME, METABASE_PASSWORD)):
        raise MetabaseConnectionError("Metabase ulanish sozlamalari kiritilmagan")
    client = requests.Session()
    try:
        response = client.post(
            urljoin(f"{METABASE_URL}/", "api/session"),
            json={"username": METABASE_USERNAME, "password": METABASE_PASSWORD},
            timeout=20,
        )
        response.raise_for_status()
        client.headers.update({"X-Metabase-Session": response.json()["id"]})
    except (requests.RequestException, KeyError, ValueError) as error:
        raise MetabaseConnectionError("Metabase tizimiga ulanib bo'lmadi") from error
    return client


def metabase_api(client, method, path, error_message, **kwargs):
    try:
        response = client.request(
            method,
            urljoin(f"{METABASE_URL}/", path.lstrip("/")),
            timeout=60,
            **kwargs,
        )
        if response.status_code == 404:
            raise MetabaseConnectionError("Metabase query topilmadi", 404)
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()
    except MetabaseConnectionError:
        raise
    except requests.HTTPError as error:
        detail = ""
        try:
            payload = error.response.json()
            detail = payload.get("message") or payload.get("error") or ""
        except (ValueError, AttributeError):
            pass
        message = f"{error_message}: {detail}" if detail else error_message
        status = 400 if error.response is not None and error.response.status_code < 500 else 502
        raise MetabaseConnectionError(message, status) from error
    except (requests.RequestException, ValueError) as error:
        raise MetabaseConnectionError(error_message) from error


def metabase_collections(client):
    tree = metabase_api(
        client,
        "GET",
        "api/collection/tree",
        "Metabase collectionlarini olib bo'lmadi",
        params={"exclude-archived": "true"},
    )
    collections = [
        {
            "id": None,
            "parent_id": None,
            "name": "Our analytics",
            "path": "Our analytics",
            "depth": 0,
            "can_write": True,
        }
    ]

    def walk(items, parents=(), parent_id=None):
        for item in items:
            names = (*parents, item.get("name") or "Nomsiz collection")
            collections.append(
                {
                    "id": int(item["id"]),
                    "parent_id": parent_id,
                    "name": names[-1],
                    "path": " / ".join(names),
                    "depth": len(parents) + 1,
                    "can_write": bool(item.get("can_write", False)),
                }
            )
            walk(item.get("children") or [], names, int(item["id"]))

    walk(tree)
    return collections


def metabase_native_sql(card):
    dataset_query = card.get("dataset_query") or {}
    stages = dataset_query.get("stages") or []
    if stages and isinstance(stages[0], dict):
        return stages[0].get("native")
    native = dataset_query.get("native") or {}
    return native.get("query")


def set_metabase_native_sql(dataset_query, sql):
    updated = deepcopy(dataset_query or {})
    stages = updated.get("stages") or []
    if stages and isinstance(stages[0], dict) and "native" in stages[0]:
        stages[0]["native"] = sql
        return updated
    if isinstance(updated.get("native"), dict):
        updated["native"]["query"] = sql
        return updated
    raise MetabaseConnectionError("Bu query SQL matnini portal orqali tahrirlab bo'lmaydi", 400)


def superset_client(write=False):
    if not all((SUPERSET_URL, SUPERSET_USERNAME, SUPERSET_PASSWORD)):
        raise SupersetConnectionError("Superset ulanish sozlamalari kiritilmagan")

    client = requests.Session()
    try:
        login_response = client.post(
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

    client.headers.update({"Authorization": f"Bearer {access_token}"})
    if write:
        try:
            csrf_response = client.get(
                urljoin(f"{SUPERSET_URL}/", "api/v1/security/csrf_token/"), timeout=20
            )
            csrf_response.raise_for_status()
            client.headers.update(
                {
                    "X-CSRFToken": csrf_response.json()["result"],
                    "Referer": f"{SUPERSET_URL}/",
                }
            )
        except (requests.RequestException, KeyError, ValueError) as error:
            raise SupersetConnectionError("Superset xavfsizlik tokenini olib bo'lmadi") from error
    return client


def superset_api(client, method, path, error_message, **kwargs):
    try:
        response = client.request(
            method,
            urljoin(f"{SUPERSET_URL}/", path.lstrip("/")),
            timeout=30,
            **kwargs,
        )
        if response.status_code == 404:
            raise SupersetConnectionError("Dataset Supersetda topilmadi", 404)
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()
    except SupersetConnectionError:
        raise
    except requests.HTTPError as error:
        detail = ""
        try:
            payload = error.response.json()
            detail = payload.get("message") or payload.get("error") or ""
            if isinstance(detail, dict):
                detail = "; ".join(str(value) for value in detail.values())
        except (ValueError, AttributeError):
            pass
        message = f"{error_message}: {detail}" if detail else error_message
        status = 400 if error.response is not None and error.response.status_code < 500 else 502
        raise SupersetConnectionError(message, status) from error
    except (requests.RequestException, ValueError) as error:
        raise SupersetConnectionError(error_message) from error


def fetch_superset_datasets(client=None):
    client = client or superset_client()
    datasets = []
    page = 0
    page_size = 100

    while True:
        query = f"(page:{page},page_size:{page_size})"
        payload = superset_api(
            client,
            "GET",
            "api/v1/dataset/",
            "Superset datasetlarini olib bo'lmadi",
            params={"q": query},
        )
        batch = payload.get("result", [])

        datasets.extend(batch)
        if not batch or len(datasets) >= int(payload.get("count", len(datasets))):
            break
        page += 1

    return datasets


def fetch_superset_tags(client):
    tags = []
    page = 0
    while True:
        payload = superset_api(
            client,
            "GET",
            "api/v1/tag/",
            "Superset taglarini olib bo'lmadi",
            params={"q": f"(page:{page},page_size:100)"},
        )
        batch = payload.get("result", [])
        tags.extend(tag for tag in batch if tag.get("type") in (1, "custom", "TagType.custom"))
        if not batch or (page + 1) * 100 >= int(payload.get("count", len(tags))):
            break
        page += 1
    return tags


def fetch_dataset_tag_map(client):
    tag_map = {}
    for tag in fetch_superset_tags(client):
        payload = superset_api(
            client,
            "GET",
            "api/v1/tag/get_objects/",
            "Dataset taglarini olib bo'lmadi",
            params={"tagIds": str(tag["id"])},
        )
        for item in payload.get("result", []):
            if item.get("type") == "dataset":
                tag_map.setdefault(int(item["id"]), []).append(tag["name"])
    return {key: sorted(set(value), key=str.casefold) for key, value in tag_map.items()}


def sync_superset_datasets(client=None):
    client = client or superset_client()
    datasets = fetch_superset_datasets(client)
    tag_map = fetch_dataset_tag_map(client)
    synced_at = utc_now()
    db = get_db()

    for dataset in datasets:
        database = dataset.get("database") or {}
        db.execute(
            """
            INSERT INTO superset_datasets (
                superset_id, table_name, schema_name, database_id, database_name, tags_json, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(superset_id) DO UPDATE SET
                table_name = excluded.table_name,
                schema_name = excluded.schema_name,
                database_id = excluded.database_id,
                database_name = excluded.database_name,
                tags_json = excluded.tags_json,
                synced_at = excluded.synced_at
            """,
            (
                dataset["id"],
                dataset.get("table_name", ""),
                dataset.get("schema"),
                database.get("id"),
                database.get("database_name"),
                json.dumps(tag_map.get(int(dataset["id"]), []), ensure_ascii=False),
                synced_at,
            ),
        )

    dataset_ids = [int(dataset["id"]) for dataset in datasets]
    if dataset_ids:
        placeholders = ",".join("?" for _ in dataset_ids)
        db.execute(
            f"DELETE FROM superset_datasets WHERE superset_id NOT IN ({placeholders})",
            dataset_ids,
        )
    else:
        db.execute("DELETE FROM superset_datasets")
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
        SELECT superset_id, table_name, schema_name, database_id, database_name,
               tags_json, folder_name, synced_at
        FROM superset_datasets
        ORDER BY table_name COLLATE NOCASE, superset_id
        """
    ).fetchall()
    result = []
    for dataset in datasets:
        item = dict(dataset)
        try:
            item["tags"] = json.loads(item.pop("tags_json"))
        except (TypeError, ValueError):
            item["tags"] = []
        result.append(item)
    return jsonify({"datasets": result, "folders": list(SUPERSET_FOLDERS)})


@app.put("/api/datasets/<int:dataset_id>/folder")
@require_admin
def move_dataset_folder(dataset_id):
    payload = request.get_json(silent=True) or {}
    folder_name = payload.get("folder_name")
    if folder_name in (None, ""):
        folder_name = None
    elif folder_name not in SUPERSET_FOLDERS:
        return jsonify({"error": "Superset papkasi noto'g'ri"}), 400
    cursor = get_db().execute(
        "UPDATE superset_datasets SET folder_name = ? WHERE superset_id = ?",
        (folder_name, dataset_id),
    )
    get_db().commit()
    if not cursor.rowcount:
        return jsonify({"error": "Dataset topilmadi"}), 404
    return jsonify({"ok": True})


@app.get("/api/superset/databases")
@require_admin
def list_superset_databases():
    try:
        client = superset_client()
        payload = superset_api(
            client,
            "GET",
            "api/v1/database/",
            "Superset database ro'yxatini olib bo'lmadi",
            params={"q": "(page:0,page_size:100)"},
        )
    except SupersetConnectionError as error:
        app.logger.warning("Superset database read failed: %s", error)
        return jsonify({"error": str(error)}), error.status_code
    databases = [
        {
            "id": int(database["id"]),
            "name": database.get("database_name") or database.get("name") or "",
            "backend": database.get("backend") or "",
        }
        for database in payload.get("result", [])
    ]
    return jsonify({"databases": databases})


@app.post("/api/datasets/sync")
@require_admin
def sync_datasets():
    try:
        count, synced_at = sync_superset_datasets()
    except SupersetConnectionError as error:
        app.logger.warning("Superset dataset sync failed: %s", error)
        return jsonify({"error": str(error)}), 502
    return jsonify({"ok": True, "count": count, "synced_at": synced_at})


def dataset_details(client, dataset_id):
    payload = superset_api(
        client,
        "GET",
        f"api/v1/dataset/{dataset_id}",
        "Dataset ma'lumotlarini olib bo'lmadi",
    )
    related = superset_api(
        client,
        "GET",
        f"api/v1/dataset/{dataset_id}/related_objects",
        "Dataset bog'lanishlarini olib bo'lmadi",
    )
    result = payload.get("result", {})
    database = result.get("database") or {}
    return {
        "superset_id": int(result.get("id", dataset_id)),
        "table_name": result.get("table_name") or result.get("name") or "",
        "schema_name": result.get("schema"),
        "database_id": database.get("id"),
        "database_name": database.get("database_name"),
        "description": result.get("description") or "",
        "sql": result.get("sql"),
        "is_sqllab_view": bool(result.get("is_sqllab_view")),
        "tags": fetch_dataset_tag_map(client).get(dataset_id, []),
        "charts_count": int((related.get("charts") or {}).get("count", 0)),
        "dashboards_count": int((related.get("dashboards") or {}).get("count", 0)),
        "superset_url": urljoin(f"{SUPERSET_URL}/", f"explore/?datasource_type=table&datasource_id={dataset_id}"),
    }


@app.get("/api/datasets/<int:dataset_id>")
@require_admin
def get_dataset(dataset_id):
    try:
        return jsonify({"dataset": dataset_details(superset_client(), dataset_id)})
    except SupersetConnectionError as error:
        app.logger.warning("Superset dataset read failed: %s", error)
        return jsonify({"error": str(error)}), error.status_code


def validate_dataset_payload(payload):
    table_name = str(payload.get("table_name", "")).strip()
    schema_name = str(payload.get("schema_name", "")).strip()
    description = str(payload.get("description", "")).strip()
    sql = payload.get("sql")
    if len(table_name) < 1 or len(table_name) > 250:
        return None, "Dataset nomi 1 dan 250 belgigacha bo'lishi kerak"
    if len(schema_name) > 250:
        return None, "Schema nomi 250 belgidan oshmasligi kerak"
    if len(description) > 5000:
        return None, "Tavsif 5000 belgidan oshmasligi kerak"
    if sql is not None:
        sql = str(sql).strip()
        if not sql:
            return None, "Virtual dataset SQL so'rovi bo'sh bo'lishi mumkin emas"
    raw_tags = payload.get("tags", [])
    if not isinstance(raw_tags, list):
        return None, "Taglar ro'yxati noto'g'ri"
    tags = []
    seen = set()
    for raw_tag in raw_tags:
        tag = str(raw_tag).strip()
        key = tag.casefold()
        if not tag or key in seen:
            continue
        if len(tag) > 250:
            return None, "Tag nomi 250 belgidan oshmasligi kerak"
        seen.add(key)
        tags.append(tag)
    if len(tags) > 50:
        return None, "Bitta datasetga 50 tadan ko'p tag biriktirib bo'lmaydi"
    return {
        "table_name": table_name,
        "schema": schema_name or None,
        "description": description or None,
        "sql": sql,
        "tags": tags,
    }, None


def validate_new_dataset_payload(payload):
    data, error = validate_dataset_payload(payload)
    if error:
        return None, error
    try:
        database_id = int(payload.get("database_id"))
    except (TypeError, ValueError):
        return None, "Ma'lumotlar bazasini tanlang"
    if database_id < 1:
        return None, "Ma'lumotlar bazasini tanlang"
    if data["sql"] is None:
        return None, "SQL so'rovini kiriting"
    data["database_id"] = database_id
    return data, None


@app.post("/api/datasets")
@require_admin
def create_dataset():
    data, error = validate_new_dataset_payload(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    dataset_id = None
    try:
        client = superset_client(write=True)
        created = superset_api(
            client,
            "POST",
            "api/v1/dataset/",
            "Datasetni Supersetda yaratib bo'lmadi",
            json={
                "database": data["database_id"],
                "schema": data["schema"],
                "table_name": data["table_name"],
                "sql": data["sql"],
            },
        )
        result = created.get("result") or {}
        dataset_id = created.get("id") or result.get("id")
        if not dataset_id:
            raise SupersetConnectionError("Superset yaratilgan dataset ID sini qaytarmadi")
        dataset_id = int(dataset_id)

        if data["description"]:
            superset_api(
                client,
                "PUT",
                f"api/v1/dataset/{dataset_id}",
                "Dataset tavsifini saqlab bo'lmadi",
                json={"description": data["description"]},
            )
        if data["tags"]:
            superset_api(
                client,
                "POST",
                f"api/v1/tag/4/{dataset_id}/",
                "Dataset taglarini qo'shib bo'lmadi",
                json={"properties": {"tags": data["tags"]}},
            )
        sync_superset_datasets(client)
    except SupersetConnectionError as superset_error:
        app.logger.warning("Superset dataset create failed: %s", superset_error)
        if dataset_id:
            try:
                sync_superset_datasets(client)
            except SupersetConnectionError:
                pass
            return jsonify(
                {
                    "error": (
                        f"Dataset Supersetda #{dataset_id} ID bilan yaratildi, "
                        f"ammo qo'shimcha ma'lumotlarni saqlashda xato yuz berdi: {superset_error}"
                    )
                }
            ), 502
        return jsonify({"error": str(superset_error)}), superset_error.status_code
    return jsonify({"ok": True, "id": dataset_id}), 201


@app.put("/api/datasets/<int:dataset_id>")
@require_admin
def update_dataset(dataset_id):
    data, error = validate_dataset_payload(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400
    try:
        client = superset_client(write=True)
        existing = dataset_details(client, dataset_id)
        update_payload = {
            "table_name": data["table_name"],
            "schema": data["schema"],
            "description": data["description"],
        }
        if existing["sql"] is not None:
            update_payload["sql"] = data["sql"]
        superset_api(
            client,
            "PUT",
            f"api/v1/dataset/{dataset_id}",
            "Datasetni Supersetda yangilab bo'lmadi",
            json=update_payload,
        )

        current_tags = set(existing["tags"])
        requested_tags = set(data["tags"])
        if requested_tags - current_tags:
            superset_api(
                client,
                "POST",
                f"api/v1/tag/4/{dataset_id}/",
                "Dataset taglarini qo'shib bo'lmadi",
                json={"properties": {"tags": sorted(requested_tags - current_tags)}},
            )
        for tag in current_tags - requested_tags:
            superset_api(
                client,
                "DELETE",
                f"api/v1/tag/4/{dataset_id}/{quote(tag, safe='')}/",
                "Dataset tagini olib tashlab bo'lmadi",
            )
        sync_superset_datasets(client)
    except SupersetConnectionError as superset_error:
        app.logger.warning("Superset dataset update failed: %s", superset_error)
        return jsonify({"error": str(superset_error)}), superset_error.status_code
    return jsonify({"ok": True})


@app.delete("/api/datasets/<int:dataset_id>")
@require_admin
def delete_dataset(dataset_id):
    try:
        client = superset_client(write=True)
        superset_api(
            client,
            "DELETE",
            f"api/v1/dataset/{dataset_id}",
            "Datasetni Supersetdan o'chirib bo'lmadi",
        )
    except SupersetConnectionError as error:
        app.logger.warning("Superset dataset delete failed: %s", error)
        return jsonify({"error": str(error)}), error.status_code
    get_db().execute("DELETE FROM superset_datasets WHERE superset_id = ?", (dataset_id,))
    get_db().commit()
    return jsonify({"ok": True})


def parse_collection_id(value):
    if value in (None, "", "null"):
        return None
    try:
        collection_id = int(value)
    except (TypeError, ValueError) as error:
        raise MetabaseConnectionError("Collection noto'g'ri", 400) from error
    if collection_id < 1:
        raise MetabaseConnectionError("Collection noto'g'ri", 400)
    return collection_id


def metabase_card_summary(card, collection_map, database_map):
    creator = card.get("creator") or {}
    creator_name = " ".join(
        part for part in (creator.get("first_name"), creator.get("last_name")) if part
    )
    collection_id = card.get("collection_id")
    collection = collection_map.get(collection_id) or {}
    return {
        "id": int(card["id"]),
        "name": card.get("name") or "Nomsiz query",
        "description": card.get("description") or "",
        "collection_id": collection_id,
        "collection_name": collection.get("path") or "Our analytics",
        "display": card.get("display") or "table",
        "query_type": card.get("query_type") or "query",
        "type": card.get("type") or "question",
        "database_id": card.get("database_id"),
        "database_name": database_map.get(card.get("database_id"), "-"),
        "updated_at": card.get("updated_at"),
        "creator_name": creator_name or "-",
        "metabase_url": urljoin(f"{METABASE_URL}/", f"question/{card['id']}"),
    }


@app.get("/api/metabase/queries")
@require_admin
def list_metabase_queries():
    try:
        client = metabase_client()
        cards = metabase_api(
            client,
            "GET",
            "api/card",
            "Metabase querylarini olib bo'lmadi",
            params={"f": "all"},
        )
        collections = metabase_collections(client)
        databases = metabase_api(
            client, "GET", "api/database", "Metabase bazalarini olib bo'lmadi"
        )
    except MetabaseConnectionError as error:
        app.logger.warning("Metabase query list failed: %s", error)
        return jsonify({"error": str(error)}), error.status_code
    collection_map = {item["id"]: item for item in collections}
    database_map = {
        item.get("id"): item.get("name") or item.get("details", {}).get("dbname") or "-"
        for item in databases.get("data", databases) if isinstance(item, dict)
    }
    queries = [
        metabase_card_summary(card, collection_map, database_map)
        for card in cards
        if not card.get("archived")
    ]
    queries.sort(key=lambda item: (item["collection_name"].casefold(), item["name"].casefold()))
    return jsonify(
        {
            "queries": queries,
            "collections": collections,
            "databases": [
                {
                    "id": int(item["id"]),
                    "name": item.get("name") or item.get("details", {}).get("dbname") or "-",
                    "engine": item.get("engine") or "",
                }
                for item in databases.get("data", databases)
                if isinstance(item, dict) and item.get("id")
            ],
        }
    )


@app.post("/api/metabase/collections")
@require_admin
def create_metabase_collection():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    description = str(payload.get("description", "")).strip()
    if not 1 <= len(name) <= 100:
        return jsonify({"error": "Papka nomi 1 dan 100 belgigacha bo'lishi kerak"}), 400
    if len(description) > 1000:
        return jsonify({"error": "Tavsif 1000 belgidan oshmasligi kerak"}), 400
    try:
        parent_id = parse_collection_id(payload.get("parent_id"))
        client = metabase_client()
        created = metabase_api(
            client,
            "POST",
            "api/collection",
            "Metabaseda papka yaratib bo'lmadi",
            json={
                "name": name,
                "description": description or None,
                "parent_id": parent_id,
            },
        )
    except MetabaseConnectionError as error:
        app.logger.warning("Metabase collection create failed: %s", error)
        return jsonify({"error": str(error)}), error.status_code
    return jsonify({"ok": True, "id": int(created["id"])}), 201


@app.post("/api/metabase/queries")
@require_admin
def create_metabase_query():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    description = str(payload.get("description", "")).strip()
    sql = str(payload.get("sql", "")).strip()
    if not 1 <= len(name) <= 250:
        return jsonify({"error": "Query nomi 1 dan 250 belgigacha bo'lishi kerak"}), 400
    if len(description) > 5000:
        return jsonify({"error": "Tavsif 5000 belgidan oshmasligi kerak"}), 400
    if not sql:
        return jsonify({"error": "SQL so'rovini kiriting"}), 400
    try:
        database_id = int(payload.get("database_id"))
        if database_id < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Ma'lumotlar bazasini tanlang"}), 400
    try:
        collection_id = parse_collection_id(payload.get("collection_id"))
        client = metabase_client()
        created = metabase_api(
            client,
            "POST",
            "api/card",
            "Metabaseda SQL query yaratib bo'lmadi",
            json={
                "name": name,
                "description": description or None,
                "collection_id": collection_id,
                "display": "table",
                "visualization_settings": {},
                "dataset_query": {
                    "lib/type": "mbql/query",
                    "database": database_id,
                    "stages": [
                        {"lib/type": "mbql.stage/native", "native": sql}
                    ],
                },
            },
        )
    except MetabaseConnectionError as error:
        app.logger.warning("Metabase query create failed: %s", error)
        return jsonify({"error": str(error)}), error.status_code
    return jsonify({"ok": True, "id": int(created["id"])}), 201


@app.get("/api/metabase/queries/<int:card_id>")
@require_admin
def get_metabase_query(card_id):
    try:
        client = metabase_client()
        card = metabase_api(
            client, "GET", f"api/card/{card_id}", "Metabase queryni olib bo'lmadi"
        )
        collections = metabase_collections(client)
    except MetabaseConnectionError as error:
        app.logger.warning("Metabase query read failed: %s", error)
        return jsonify({"error": str(error)}), error.status_code
    collection_map = {item["id"]: item for item in collections}
    query = metabase_card_summary(card, collection_map, {})
    query["sql"] = metabase_native_sql(card)
    query["can_edit_sql"] = query["query_type"] == "native" and query["sql"] is not None
    return jsonify({"query": query, "collections": collections})


@app.put("/api/metabase/queries/<int:card_id>")
@require_admin
def update_metabase_query(card_id):
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    description = str(payload.get("description", "")).strip()
    if not 1 <= len(name) <= 250:
        return jsonify({"error": "Query nomi 1 dan 250 belgigacha bo'lishi kerak"}), 400
    if len(description) > 5000:
        return jsonify({"error": "Tavsif 5000 belgidan oshmasligi kerak"}), 400
    try:
        collection_id = parse_collection_id(payload.get("collection_id"))
        client = metabase_client()
        card = metabase_api(
            client, "GET", f"api/card/{card_id}", "Metabase queryni olib bo'lmadi"
        )
        update_payload = {
            "name": name,
            "description": description or None,
            "collection_id": collection_id,
        }
        if card.get("query_type") == "native" and payload.get("sql") is not None:
            sql = str(payload.get("sql", "")).strip()
            if not sql:
                return jsonify({"error": "SQL so'rovi bo'sh bo'lishi mumkin emas"}), 400
            update_payload["dataset_query"] = set_metabase_native_sql(
                card.get("dataset_query"), sql
            )
        metabase_api(
            client,
            "PUT",
            f"api/card/{card_id}",
            "Metabase queryni yangilab bo'lmadi",
            json=update_payload,
        )
    except MetabaseConnectionError as error:
        app.logger.warning("Metabase query update failed: %s", error)
        return jsonify({"error": str(error)}), error.status_code
    return jsonify({"ok": True})


@app.put("/api/metabase/queries/<int:card_id>/move")
@require_admin
def move_metabase_query(card_id):
    try:
        collection_id = parse_collection_id(
            (request.get_json(silent=True) or {}).get("collection_id")
        )
        client = metabase_client()
        metabase_api(
            client,
            "PUT",
            f"api/card/{card_id}",
            "Metabase queryni ko'chirib bo'lmadi",
            json={"collection_id": collection_id},
        )
    except MetabaseConnectionError as error:
        app.logger.warning("Metabase query move failed: %s", error)
        return jsonify({"error": str(error)}), error.status_code
    return jsonify({"ok": True})


@app.post("/api/metabase/queries/<int:card_id>/copy")
@require_admin
def copy_metabase_query(card_id):
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    if name and len(name) > 250:
        return jsonify({"error": "Query nomi 250 belgidan oshmasligi kerak"}), 400
    try:
        collection_id = parse_collection_id(payload.get("collection_id"))
        client = metabase_client()
        copied = metabase_api(
            client,
            "POST",
            f"api/card/{card_id}/copy",
            "Metabase querydan nusxa olib bo'lmadi",
        )
        copied_id = copied.get("id")
        if not copied_id:
            raise MetabaseConnectionError("Metabase nusxa ID sini qaytarmadi")
        update_payload = {"collection_id": collection_id}
        if name:
            update_payload["name"] = name
        metabase_api(
            client,
            "PUT",
            f"api/card/{copied_id}",
            "Query nusxasini collectionga joylab bo'lmadi",
            json=update_payload,
        )
    except MetabaseConnectionError as error:
        app.logger.warning("Metabase query copy failed: %s", error)
        return jsonify({"error": str(error)}), error.status_code
    return jsonify({"ok": True, "id": int(copied_id)}), 201


@app.delete("/api/metabase/queries/<int:card_id>")
@require_admin
def delete_metabase_query(card_id):
    try:
        client = metabase_client()
        metabase_api(
            client,
            "DELETE",
            f"api/card/{card_id}",
            "Metabase queryni o'chirib bo'lmadi",
        )
    except MetabaseConnectionError as error:
        app.logger.warning("Metabase query delete failed: %s", error)
        return jsonify({"error": str(error)}), error.status_code
    return jsonify({"ok": True})


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

