import os
import tempfile
import shutil
import pyramid_zcml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from cone.app.testing import Security
from cone.sql import initialize_sql


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
        self.sql_session = session
