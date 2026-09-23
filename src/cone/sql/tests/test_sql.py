from cone import sql
from cone.app import RemoteAddrFilter
from cone.sql import initialize_cone_sql
from cone.sql import SqlUGMFactory
from cone.sql import SQLSessionFactory
from cone.sql import testing
from cone.sql.testing import after_flush
from node.tests import NodeTestCase
from pyramid.paster import get_app
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
import os
import shutil
import subprocess
import sys
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
        class StartResponse:
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

    def test_initialize_cone_sql(self):
        orgin_session_factory = sql.session_factory
        orgin_use_tm = os.environ.get('CONE_SQL_USE_TM', '0')
        try:
            initialize_cone_sql(None, {}, {
                'sql.db.url': 'sqlite:///:memory:',
                'ugm.backend': 'sql',
                'pyramid.includes': 'pyramid_tm'
            })
            self.assertIsInstance(sql.session_factory, SQLSessionFactory)
            self.assertFalse(sql.session_factory is orgin_session_factory)
            self.assertEqual(os.environ['CONE_SQL_USE_TM'], '1')
        finally:
            sql.session_factory = orgin_session_factory
            os.environ['CONE_SQL_USE_TM'] = orgin_use_tm

    def test_ugm_factory_reads_attrs_from_settings_without_cone_ugm(self):
        factory = SqlUGMFactory({
            'cone.plugins': 'cone.sql',
            'sql.user_attrs': 'phone, address',
            'sql.group_attrs': 'description,',
            'sql.binary_attrs': 'portrait',
            'sql.log_auth': 'true'
        })
        self.assertEqual(factory.user_attrs, ['phone', 'address'])
        self.assertEqual(factory.group_attrs, ['description'])
        self.assertEqual(factory.binary_attrs, ['portrait'])
        self.assertTrue(factory.log_auth)

    def test_test_session_factory_creates_set_up_session(self):
        engine = create_engine('sqlite:///:memory:')
        factory = testing.TestSQLSessionFactory(sessionmaker(bind=engine))
        session = factory()
        self.assertIsInstance(session, Session)
        self.assertTrue(event.contains(session, 'after_flush', after_flush))

    def test_testing_registers_ugm_tables(self):
        # ``SQLLayer`` configures ``sql`` as UGM backend and creates the tables
        # before the application imports ``cone.sql.ugm``. Checked in a fresh
        # interpreter, since test modules of this package import the module.
        code = (
            'from cone.sql import SQLBase\n'
            'import cone.sql.testing\n'
            'print("principal" in SQLBase.metadata.tables)\n'
        )
        result = subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True,
            text=True,
            check=True
        )
        self.assertEqual(result.stdout.strip(), 'True')
