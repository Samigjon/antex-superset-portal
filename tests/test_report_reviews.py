import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ReviewsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ.update(DATABASE_PATH=str(Path(cls.tmp.name) / 'test.sqlite3'),
                          ADMIN_PASSWORD='test-password', SECRET_KEY='test-key',
                          SUPERSET_URL='https://superset.example.test')
        cls.portal = importlib.import_module('app')
        cls.app = cls.portal.app
        cls.app.config['TESTING'] = True

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        with self.app.app_context():
            self.portal.get_db().execute('DELETE FROM report_review_events')
            self.portal.get_db().execute('DELETE FROM report_reviews')
            self.portal.get_db().commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['user_id'] = 1
            session['csrf_token'] = 'csrf-test'
        self.dashboard = {'id': 5, 'dashboard_title': 'Sales', 'tags': [], 'position_json': '{}', 'json_metadata': '{}', 'css': ''}
        self.chart = {'id': 9, 'slice_name': 'Sales', 'params': '{"datasource":"12__table"}'}
        self.dataset = {'id': 12, 'database': {'id': 2}, 'columns': [{'column_name': 'company_id'}], 'sql': 'SELECT company_id, amount FROM sales'}
        self.calls = []
        class Response:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {'result': {'uuid': 'review-uuid', 'allowed_domains': []}}
        class Client:
            def get(self, *args, **kwargs): return Response()
        def remote(session, method, path, message, **kwargs):
            path = path.lstrip('/')
            self.calls.append((method, path, kwargs.get('json')))
            if path == 'api/v1/sqllab/execute/': return {'status':'success','data':[{'id':290,'company_name':'Test'},{'id':261,'company_name':'UOS'}]}
            if path == 'api/v1/security/guest_token/': return {'token':'guest'}
            if path == 'api/v1/dashboard/5/charts': return {'result':[{'id':9}]}
            if path == 'api/v1/chart/9': return {'result':self.chart}
            if path.startswith('api/v1/dataset/'): return {'result':self.dataset}
            if path == 'api/v1/dashboard/5':
                if method == 'PUT': self.dashboard.update(kwargs['json'])
                if isinstance(self.dashboard.get('tags', [None])[0] if self.dashboard.get('tags') else None, int):
                    self.dashboard['tags']=[{'id':7,'name':'Sales','type':1}]
                return {'result':self.dashboard}
            if path == 'api/v1/tag/': return {'result':[{'id':7,'name':'Sales','type':1}],'count':1}
            raise AssertionError((method,path))
        class FakeSession(Client):
            headers = {}
            def post(self, url, **kwargs):
                class Login(Response):
                    def json(inner): return {'access_token':'access'}
                return Login()
            def get(self, url, **kwargs):
                if url.endswith('csrf_token/'):
                    class Csrf(Response):
                        def json(inner): return {'result':'csrf'}
                    return Csrf()
                return Response()
            def request(self, method, url, **kwargs):
                data = remote(self,method,url.split('example.test/')[1],'',**kwargs)
                class Result(Response):
                    content = b'json'
                    def json(inner): return data
                return Result()
        self.patcher = patch('app.requests.Session', FakeSession)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.portal.SUPERSET_USERNAME = 'service'
        self.portal.SUPERSET_PASSWORD = 'test'

    def post(self, path, payload):
        return self.client.post(path,json=payload,headers={'X-CSRF-Token':'csrf-test'})

    def register(self):
        self.assertEqual(self.post('/api/report-reviews', {'dashboard_id':5}).status_code,201)

    def test_auth_csrf_and_nonadmin(self):
        self.assertEqual(self.app.test_client().get('/api/report-reviews').status_code,401)
        self.assertEqual(self.client.post('/api/report-reviews',json={'dashboard_id':5}).status_code,403)
        with self.app.app_context():
            self.portal.get_db().execute("UPDATE users SET role='viewer' WHERE id=1")
            self.portal.get_db().commit()
        try:
            self.assertEqual(self.client.get('/api/report-reviews').status_code,403)
        finally:
            with self.app.app_context():
                self.portal.get_db().execute("UPDATE users SET role='admin' WHERE id=1")
                self.portal.get_db().commit()

    def test_registration_is_explicit_and_hidden(self):
        self.assertEqual(self.client.get('/api/report-reviews').json['reviews'],[])
        self.register()
        self.assertEqual(self.dashboard['tags'],[])
        self.assertEqual(self.post('/api/report-reviews', {'dashboard_id':5}).status_code,409)

    def test_tagged_and_unisolated_reports_rejected(self):
        self.dashboard['tags']=[{'id':7,'type':1}]
        self.assertEqual(self.post('/api/report-reviews',{'dashboard_id':5}).status_code,409)
        self.dashboard['tags']=[]
        self.dataset['columns']=[]
        self.assertEqual(self.post('/api/report-reviews',{'dashboard_id':5}).status_code,400)

    def test_company_isolation(self):
        self.register()
        for cid in (290,261):
            response=self.post('/api/report-reviews/5/preview',{'company_id':cid})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            token_call=next(c for c in reversed(self.calls) if c[1].endswith('guest_token/'))
            self.assertEqual(token_call[2]['rls'],[{'clause':f'company_id = {cid}'}])
            self.assertEqual(token_call[2]['resources'],[{'type':'dashboard','id':'review-uuid'}])
        for cid in ('290 OR 1=1',999):
            self.assertEqual(self.post('/api/report-reviews/5/preview',{'company_id':cid}).status_code,400)

    def test_approval_publish_and_changes(self):
        self.register()
        action='/api/report-reviews/5/action'
        self.assertEqual(self.post(action,{'action':'approve'}).status_code,409)
        preview=self.post('/api/report-reviews/5/preview',{'company_id':290}).json
        self.assertEqual(self.post(action,{'action':'tested','version':preview['version'],'company_id':290}).status_code,200)
        self.assertEqual(self.post(action,{'action':'approve'}).status_code,200)
        self.assertEqual(self.dashboard['tags'],[])
        self.dataset['sql'] += ' WHERE amount>0'
        self.assertEqual(self.post(action,{'action':'publish','tag_id':7}).status_code,409)
        preview=self.post('/api/report-reviews/5/preview',{'company_id':290}).json
        self.post(action,{'action':'tested','version':preview['version'],'company_id':290})
        self.post(action,{'action':'approve'})
        self.assertEqual(self.post(action,{'action':'publish','tag_id':7}).status_code,200)
        self.assertTrue(self.dashboard['published'])
        self.assertEqual(self.post(action,{'action':'changes','note':'fix'}).status_code,409)

    def test_changes_require_note_and_invalidate_test(self):
        self.register()
        action='/api/report-reviews/5/action'
        self.assertEqual(self.post(action,{'action':'changes'}).status_code,400)
        self.assertEqual(self.post(action,{'action':'changes','note':'Wrong total'}).json['review']['status'],'changes')
        self.assertEqual(self.client.get('/api/report-reviews/5/events').json['events'][0]['note'],'Wrong total')


if __name__ == '__main__':
    unittest.main()
