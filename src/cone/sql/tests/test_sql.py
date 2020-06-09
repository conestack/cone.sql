from cone import sql
from cone.app import RemoteAddrFilter
from cone.sql import testing
from node.tests import NodeTestCase
from pyramid.paster import get_app
from sqlalchemy.orm.session import Session
import os
import shutil
import tempfile


def temp_directory(fn):
    """Decorator for tests needing a temporary directory.
    """
    def wrapper(*a, **kw):
        tempdir = tempfile.mkdtemp()
        kw['tempdir'] = tempdir
        try:
            fn(*a, **kw)
        finally:
            shutil.rmtree(tempdir)
    return wrapper


app_config = """
[app:my_app]
use = egg:cone.app#main

tm.commit_veto = pyramid_tm.default_commit_veto

cone.plugins =
    cone.sql

sql.db.url = sqlite:///:memory:

[filter:remote_addr]
# for use behind nginx
use = egg:cone.app#remote_addr

[filter:session]
use = egg:cone.sql#session

[pipeline:main]
pipeline =
    remote_addr
    session
    my_app
"""


class TestSQL(NodeTestCase):
    layer = testing.sql_layer

    @temp_directory
    def test_wsgi(self, tempdir):
        # Write test application config
        config_path = os.path.join(tempdir, 'sql.ini')
        with open(config_path, 'w') as f:
            f.write(app_config)

        # Create WSGI app
        wsgi_app = get_app(config_path, 'main')
        self.assertTrue(isinstance(wsgi_app, RemoteAddrFilter))

        # Dummy WSGI environment
        environ = {
            'REQUEST_METHOD': 'GET',
            'PATH_INFO': '/'
        }

        # Dummy ``start_response`` callback
        class StartResponse(object):
            args = None

            def __call__(self, *args):
                self.args = args

        # Call WSGI app
        start_response = StartResponse()
        wsgi_app(environ, start_response)
        result = start_response.args
        self.assertEqual(result[0], '200 OK')
        self.assertEqual(
            result[1][0],
            ('Content-Type', 'text/html; charset=UTF-8')
        )
        self.assertEqual(result[1][1][0], 'Content-Length')

        # SQL session has been hooked up to environment
        self.assertTrue(isinstance(environ[sql.session_key], Session))
