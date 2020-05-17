import os

from cone.app.testing import Security
from cone.sql import initialize_sql
from cone.sql import setup_session
from cone.sql import sql_session_setup
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
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
# Test layer
###############################################################################

class SQLLayer(Security):

    def setUp(self, args=None):
        self.tempdir = tempfile.mkdtemp()
        super(SQLLayer, self).setUp()
        self.init_sql()
        self.new_request()

    def tearDown(self):
        super(SQLLayer, self).tearDown()
        shutil.rmtree(self.tempdir)

    def new_request(self):
        request = super(SQLLayer, self).new_request()
        request.environ['cone.sql.session'] = self.sql_session
        return request

    def init_sql(self):
        # engine = create_engine('sqlite:///:memory:', echo=True)

        # alternatively use postgresql - ditches db before start
        os.system("dropdb ugm; createdb ugm")
        engine = create_engine("postgresql:///ugm", echo=True)

        # sqlite persistent in package folder for post mortem analysis
        # curdir = os.path.dirname(__file__)
        # fname = "%s/test.db" % curdir
        # if os.path.exists(fname):
        #     os.remove(fname)
        # uri = "sqlite:///" + fname
        # engine = create_engine(uri)

        initialize_sql(engine)
        maker = sessionmaker(bind=engine)
        session = maker()
        setup_session(session)
        self.sql_session = session


sql_layer = SQLLayer()
