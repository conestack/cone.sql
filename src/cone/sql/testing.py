from cone.app.testing import Security
from cone.sql import SQLBase
from cone.sql import setup_session
from cone.sql import sql_session_setup
from cone.sql import initialize_sql
from cone.sql.model import GUID
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
import os
import pyramid_zcml
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
# Test SQL alchemy models
#
# cannot define test SQLAlchemy models in doctest, ``create_all`` won't
# recognize at initialization time.
###############################################################################

class UUIDAsPrimaryKeyRecord(SQLBase):
    """Record with UUID as primary key.
    """
    __tablename__ = 'uuid_as_primary_key'
    uid_key = Column(GUID, primary_key=True)
    field = Column(String)


class StringAsPrimaryKeyRecord(SQLBase):
    """Record with string as primary key.
    """
    __tablename__ = 'string_as_primary_key'
    string_key = Column(String, primary_key=True)
    field = Column(String)


class IntegerAsPrimaryKeyRecord(SQLBase):
    """Record with integer as primary key.
    """
    __tablename__ = 'integer_as_primary_key'
    integer_key = Column(Integer, primary_key=True)
    field = Column(String)


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
        engine = create_engine('sqlite:///:memory:', echo=False)
        initialize_sql(engine)
        maker = sessionmaker(bind=engine)
        session = maker()
        setup_session(session)
        self.sql_session = session
