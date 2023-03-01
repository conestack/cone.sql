from cone import sql
from cone.app.testing import Security
from cone.app.ugm import ugm_backend
from cone.sql import get_session
from cone.sql import initialize_sql
from cone.sql import setup_session
from cone.sql import sql_session_setup
from cone.ugm import testing
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
import os
import shutil
import tempfile


###############################################################################
# Test session setup handler and event listener
###############################################################################

# override to test if event listener gets called properly
test_after_flush = None


def after_flush(session, flush_context):
    """Test event listener.
    """
    if test_after_flush is not None:
        test_after_flush(session, flush_context)


@sql_session_setup
def bind_session_listener(session):
    """Test SQL session setup callback.
    """
    event.listen(session, 'after_flush', after_flush)


###############################################################################
# Test decorators
###############################################################################

class delete_table_records(object):

    def __init__(self, record_cls):
        self.record_cls = record_cls

    def __call__(self, fn):
        def wrapper(inst):
            try:
                fn(inst)
            finally:
                request = inst.layer.new_request()
                session = get_session(request)
                session.query(self.record_cls).delete()
                session.commit()
        return wrapper


###############################################################################
# Test SQL session factory
###############################################################################

class TestSQLSessionFactory(object):

    def __init__(self, maker):
        self.maker = maker

    def __call__(self):
        session = self.maker()
        setup_session(session)
        return session


###############################################################################
# Test layer
###############################################################################

class SQLLayer(testing.UGMLayer):

    def make_app(self, **kw):
        settings = {
            'cone.plugins': '\n'.join([
                'cone.ugm',
                'cone.sql'
            ]),
            'ugm.backend': 'sql',
            'ugm.config': testing.ugm_config,
            'ugm.localmanager_config': testing.localmanager_config,
            'sql.binary_attrs': 'portrait'
        }
        settings.update(**kw)
        super(SQLLayer, self).make_app(**kw)

    def setUp(self, args=None):
        self.tempdir = tempfile.mkdtemp()
        # initialize SQL before calling setUp() of super class, which itself
        # calls make_app. This ensures sql.session_factory() is properly set
        # if used in a cone main hook.
        self.init_sql()
        super(SQLLayer, self).setUp()
        self.new_request()

    def tearDown(self):
        super(SQLLayer, self).tearDown()
        shutil.rmtree(self.tempdir)

    def new_request(self, type=None, xhr=False):
        request = super(SQLLayer, self).new_request(type=type, xhr=xhr)
        request.environ['cone.sql.session'] = self.sql_session
        return request

    def init_sql(self):
        sql_backend = os.environ.get('CONE_SQL_TEST_BACKEND')
        # sqlite memory is default test backend
        if not sql_backend:  # pragma no cover
            engine = create_engine('sqlite:///:memory:', echo=False)
        # sqlite persistent in package folder for post mortem analysis
        elif sql_backend == 'sqlite':  # pragma no cover
            curdir = os.path.dirname(__file__)
            fname = "%s/test.db" % curdir
            if os.path.exists(fname):
                os.remove(fname)
            uri = "sqlite:///" + fname
            engine = create_engine(uri)
        # alternatively use postgresql - ditches db before start
        elif sql_backend == 'postgres':  # pragma no cover
            os.system("dropdb ugm; createdb ugm")
            engine = create_engine("postgresql:///ugm", echo=False)
        initialize_sql(engine)
        maker = sessionmaker(bind=engine)
        if sql.session_factory:  # pragma no cover
            sql.session_factory.maker = maker
        else:
            sql.session_factory = TestSQLSessionFactory(maker)
        session = maker()
        setup_session(session)
        self.sql_session = session


sql_layer = SQLLayer()
