"""Admin-only review queue; company isolation is enforced in guest tokens."""
import hashlib
import json
import os

from flask import g, jsonify, request


def register_reviews(app, portal):
    db_get = portal['get_db']
    admin = portal['require_admin']
    connect = portal['superset_client']
    api = portal['superset_api']
    now = portal['utc_now']
    error_type = portal['SupersetConnectionError']
    database_id = int(os.environ.get('REVIEW_DATABASE_ID', '2'))
    origin = os.environ.get('REVIEW_EMBED_ORIGIN', 'https://antexpertinfo.uz').rstrip('/')
    superset_url = portal['SUPERSET_URL']

    with app.app_context():
        db_get().executescript('''
            CREATE TABLE IF NOT EXISTS report_reviews (
                dashboard_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'review'
                    CHECK(status IN ('review','changes','approved','published')),
                approved_hash TEXT,
                tested_hash TEXT,
                tested_company INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS report_review_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dashboard_id INTEGER NOT NULL REFERENCES report_reviews(dashboard_id),
                actor_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
        ''')
        db_get().commit()

    def remote(client, method, path, **kwargs):
        return api(client, method, path, 'Superset: hisobot tekshiruvi bajarilmadi', **kwargs)

    def all_objects(client, kind):
        result = []
        page = 0
        while True:
            payload = remote(client, 'GET', f'api/v1/{kind}/',
                             params={'q': f'(page:{page},page_size:100)'})
            batch = payload.get('result', [])
            result.extend(batch)
            if not batch or len(result) >= payload.get('count', len(result)):
                return result
            page += 1

    def custom_tags(dashboard):
        return [t for t in dashboard.get('tags', [])
                if t.get('type') in (1, '1', 'custom', 'TagType.custom')]

    def companies(client):
        payload = remote(client, 'POST', 'api/v1/sqllab/execute/', json={
            'database_id': database_id, 'schema': 'ad_reporting',
            'sql': 'SELECT id, company_name FROM ad_reporting.company FINAL ORDER BY company_name, id',
            'runAsync': False, 'select_as_cta': False, 'queryLimit': 10000,
        })
        if payload.get('status') not in ('success', None) or not isinstance(payload.get('data'), list):
            raise error_type('Kompaniyalar ro‘yxatini yuklab bo‘lmadi')
        return [{'id': int(r['id']), 'name': r['company_name']} for r in payload['data']]

    def row(did):
        item = db_get().execute('SELECT * FROM report_reviews WHERE dashboard_id=?', (did,)).fetchone()
        if not item:
            raise error_type('Tekshiruv ro‘yxatida hisobot topilmadi', 404)
        return dict(item)

    def event(did, action, note=''):
        db_get().execute('INSERT INTO report_review_events '
                         '(dashboard_id,actor_id,action,note,created_at) VALUES (?,?,?,?,?)',
                         (did, g.current_user['id'], action, note, now()))

    def snapshot(client, did):
        dashboard = remote(client, 'GET', f'api/v1/dashboard/{did}')['result']
        charts = remote(client, 'GET', f'api/v1/dashboard/{did}/charts')['result']
        if not charts:
            raise error_type('Dashboardda chart mavjud emas', 400)
        signature = {'dashboard': {k: dashboard.get(k) for k in
                     ('dashboard_title', 'position_json', 'json_metadata', 'css')}, 'charts': [], 'datasets': []}
        sources = set()
        def filter_sources(value):
            if isinstance(value, dict):
                if value.get('datasetId') is not None:
                    sources.add(int(value['datasetId']))
                for child in value.values():
                    filter_sources(child)
            elif isinstance(value, list):
                for child in value:
                    filter_sources(child)
        filter_sources(json.loads(dashboard.get('json_metadata') or '{}'))
        for chart in charts:
            detail = remote(client, 'GET', f"api/v1/chart/{chart['id']}")['result']
            params = json.loads(detail.get('params') or '{}')
            source = params.get('datasource', '')
            if not isinstance(source, str) or not source.endswith('__table'):
                raise error_type('Faqat company_id mavjud datasetlar tekshiriladi', 400)
            sources.add(int(source.split('__')[0]))
            signature['charts'].append({k: detail.get(k) for k in
                                       ('id', 'slice_name', 'params', 'query_context', 'viz_type')})
        for sid in sorted(sources):
            detail = remote(client, 'GET', f'api/v1/dataset/{sid}')['result']
            if detail.get('database', {}).get('id') != database_id or not any(
                    c.get('column_name') == 'company_id' for c in detail.get('columns', [])):
                raise error_type(f'Dataset #{sid}: kompaniya izolyatsiyasi tasdiqlanmagan', 400)
            signature['datasets'].append({k: detail.get(k) for k in
                                         ('id', 'sql', 'schema', 'table_name', 'columns', 'metrics', 'template_params')})
        signature['charts'].sort(key=lambda c: c['id'])
        digest = hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return dashboard, digest

    def ensure_hidden(dashboard):
        if custom_tags(dashboard):
            raise error_type('Hisobotda klientlar uchun tag mavjud. Tekshiruvga tagsiz nusxasini qo‘shing.', 409)

    def embed(client, did):
        # Explicit registration may enable embedding, but never publishes or assigns tags.
        response = client.get(f'{superset_url}/api/v1/dashboard/{did}/embedded', timeout=30)
        if response.status_code == 404:
            result = remote(client, 'POST', f'api/v1/dashboard/{did}/embedded',
                            json={'allowed_domains': [origin]})['result']
        else:
            response.raise_for_status()
            result = response.json()['result']
            domains = result.get('allowed_domains') or []
            if domains and origin not in domains:
                result = remote(client, 'PUT', f'api/v1/dashboard/{did}/embedded',
                                json={'allowed_domains': [*domains, origin]})['result']
        return result['uuid']

    def guarded(handler):
        from functools import wraps
        @wraps(handler)
        @admin
        def wrapped(*args, **kwargs):
            try:
                return handler(*args, **kwargs)
            except error_type as exc:
                return jsonify({'error': str(exc)}), exc.status_code
            except (ValueError, KeyError, TypeError):
                return jsonify({'error': 'Noto‘g‘ri so‘rov yoki Superset javobi'}), 400
        return wrapped

    @app.get('/api/report-reviews')
    @guarded
    def review_list():
        items = [dict(r) for r in db_get().execute('SELECT * FROM report_reviews ORDER BY updated_at DESC')]
        return jsonify({'reviews': items})

    @app.get('/api/report-reviews/options')
    @guarded
    def review_options():
        client = connect(write=True)
        return jsonify({'companies': companies(client),
                        'dashboards': [{'id': d['id'], 'title': d['dashboard_title']}
                                       for d in all_objects(client, 'dashboard') if not custom_tags(d)],
                        'tags': portal['fetch_superset_tags'](client)})

    @app.post('/api/report-reviews')
    @guarded
    def review_register():
        did = int(request.get_json()['dashboard_id'])
        client = connect(write=True)
        dashboard, _ = snapshot(client, did)
        ensure_hidden(dashboard)
        if db_get().execute('SELECT 1 FROM report_reviews WHERE dashboard_id=?', (did,)).fetchone():
            return jsonify({'error': 'Hisobot ro‘yxatga qo‘shilgan'}), 409
        embed(client, did)
        db_get().execute('INSERT INTO report_reviews (dashboard_id,title,created_at,updated_at) VALUES (?,?,?,?)',
                         (did, dashboard['dashboard_title'], now(), now()))
        event(did, 'registered')
        db_get().commit()
        return jsonify({'review': row(did)}), 201

    @app.get('/api/report-reviews/<int:did>/events')
    @guarded
    def review_events(did):
        row(did)
        events = [dict(r) for r in db_get().execute(
            'SELECT e.*, u.full_name AS actor FROM report_review_events e '
            'LEFT JOIN users u ON u.id=e.actor_id WHERE dashboard_id=? ORDER BY e.id DESC', (did,))]
        return jsonify({'events': events})

    @app.post('/api/report-reviews/<int:did>/preview')
    @guarded
    def review_preview(did):
        item = row(did)
        cid = int(request.get_json()['company_id'])
        client = connect(write=True)
        if cid not in {c['id'] for c in companies(client)}:
            return jsonify({'error': 'Kompaniya topilmadi'}), 400
        dashboard, digest = snapshot(client, did)
        if item['status'] != 'published':
            ensure_hidden(dashboard)
        uuid = embed(client, did)
        token = remote(client, 'POST', 'api/v1/security/guest_token/', json={
            'user': {'username': f"review-{g.current_user['id']}", 'first_name': 'Review', 'last_name': 'Admin'},
            'resources': [{'type': 'dashboard', 'id': uuid}],
            'rls': [{'clause': f'company_id = {cid}'}],
        })['token']
        response = jsonify({'uuid': uuid, 'token': token, 'superset_url': superset_url, 'version': digest})
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/api/report-reviews/<int:did>/action')
    @guarded
    def review_action(did):
        payload = request.get_json()
        action = payload.get('action')
        # Serialize transitions, including the external publish call, per portal DB.
        db_get().execute('BEGIN IMMEDIATE')
        item = row(did)
        if item['status'] == 'published':
            return jsonify({'error': 'Nashr qilingan hisobot o‘zgarmaydi. Tagsiz yangi nusxa yarating.'}), 409
        if action not in ('tested', 'changes', 'approve', 'publish', 'comment'):
            return jsonify({'error': 'Amal noto‘g‘ri'}), 400
        note = str(payload.get('note') or '').strip()[:4000]
        client = connect(write=True)
        dashboard, digest = snapshot(client, did)
        ensure_hidden(dashboard)
        if action == 'tested':
            if payload.get('version') != digest:
                return jsonify({'error': 'Hisobot o‘zgargan. Qayta ochib tekshiring.'}), 409
            cid = int(payload['company_id'])
            if cid not in {c['id'] for c in companies(client)}:
                return jsonify({'error': 'Kompaniya topilmadi'}), 400
            db_get().execute('UPDATE report_reviews SET tested_hash=?,tested_company=?,updated_at=? WHERE dashboard_id=?',
                             (digest, cid, now(), did))
            note = f'Company {cid}. {note}'
        elif action == 'approve':
            if item['tested_hash'] != digest:
                return jsonify({'error': 'Avval joriy versiyani ochib, tekshirilganini belgilang.'}), 409
            db_get().execute("UPDATE report_reviews SET status='approved',approved_hash=?,updated_at=? WHERE dashboard_id=?",
                             (digest, now(), did))
        elif action == 'changes':
            if not note:
                return jsonify({'error': 'Tuzatish sababini yozing'}), 400
            db_get().execute("UPDATE report_reviews SET status='changes',approved_hash=NULL,tested_hash=NULL,updated_at=? WHERE dashboard_id=?",
                             (now(), did))
        elif action == 'publish':
            if item['status'] != 'approved' or item['approved_hash'] != digest:
                return jsonify({'error': 'Joriy versiya tasdiqlanmagan'}), 409
            tag_id = int(payload['tag_id'])
            tags = portal['fetch_superset_tags'](client)
            if tag_id not in {int(t['id']) for t in tags}:
                return jsonify({'error': 'Tag topilmadi'}), 400
            remote(client, 'PUT', f'api/v1/dashboard/{did}', json={'tags': [tag_id], 'published': True})
            verified = remote(client, 'GET', f'api/v1/dashboard/{did}')['result']
            if tag_id not in {int(t['id']) for t in custom_tags(verified)} or not verified.get('published'):
                raise error_type('Nashr holati tasdiqlanmadi; administrator tekshiruvi kerak')
            db_get().execute("UPDATE report_reviews SET status='published',updated_at=? WHERE dashboard_id=?", (now(), did))
            note = f'Tag {tag_id}. {note}'
        elif not note:
            return jsonify({'error': 'Izohni yozing'}), 400
        event(did, action, note)
        db_get().commit()
        return jsonify({'review': row(did)})
