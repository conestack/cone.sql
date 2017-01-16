from sqlalchemy import engine_from_config
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker
import cone.app


###############################################################################
# initialization and WSGI
###############################################################################

SQLBase = declarative_base(cls=IndexingBase)
DBSession = scoped_session(sessionmaker())
metadata = SQLBase.metadata


def initialize_sql(engine):
    DBSession.configure(bind=engine)
    metadata.bind = engine
    metadata.create_all(engine)


session_key = 'cone.sql.session'


def get_session(request):
    return request.environ[session_key]


class WSGISQLSession(object):
    """WSGI framework component that opens and closes a SQL session.

    Downstream applications will have the session in the environment,
    normally under the key 'cone.sql.session'.
    """

    def __init__(self, next_app, maker, session_key=session_key):
        self.next_app = next_app
        self.maker = maker
        self.session_key = session_key

    def __call__(self, environ, start_response):
        session = self.maker()
        bind_session_listeners(session)
        environ[self.session_key] = session
        try:
            result = self.next_app(environ, start_response)
            return result
        finally:
            session.close()


def make_app(next_app, global_conf, **local_conf):
    """Make a Session app.
    """
    from cone import sql
    engine = engine_from_config(local_conf, prefix='sqlalchemy.')
    sql.SQLBase.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    sql.session_key = local_conf.get('session_key', sql.session_key)
    return WSGISQLSession(next_app, maker, sql.session_key)


# application startup initialization
def initialize_cone_sql(config, global_config, local_config):
    # add translation
    config.add_translation_dirs('cone.sql:locales/')

    # database initialization
    prefix = 'cone.sql.dbinit.'
    if local_config.get('%surl' % prefix, None) is None:
        return
    engine = engine_from_config(local_config, prefix)
    initialize_db(engine)

cone.app.register_main_hook(initialize_cone_sql)
