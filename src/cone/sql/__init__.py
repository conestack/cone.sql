from sqlalchemy import engine_from_config
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker
import cone.app


###############################################################################
# initialization and WSGI
###############################################################################

SQLBase = declarative_base()
DBSession = scoped_session(sessionmaker())
metadata = SQLBase.metadata


def initialize_sql(engine):
    """Basic SQL initialization.
    """
    DBSession.configure(bind=engine)
    metadata.bind = engine
    metadata.create_all(engine)


# key used for storing SQL session on request environment
session_key = 'cone.sql.session'


def get_session(request):
    """Return request related SQL session.
    """
    return request.environ[session_key]


# session setup handler registry
_session_setup_handlers = list()

def sql_session_setup(ob):
    """Decorator for registering SQL session setup handlers.

    A function decorated with ``sql_session_setup`` must accept a ``session``
    argument and is supposed to register SQLAlchemy event handlers and other
    setup tasks in conjunction with the created SQL session.
    """
    _session_setup_handlers.append(ob)
    return ob


def setup_session(session):
    """Call all registered session setup handlers.
    """
    for session_setup_callback in _session_setup_handlers:
        session_setup_callback(session)


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
        setup_session(session)
        environ[self.session_key] = session
        try:
            result = self.next_app(environ, start_response)
            return result
        finally:
            session.close()


def make_app(next_app, global_conf, **local_conf):
    """Create ``WSGISQLSession``.
    """
    from cone import sql
    engine = engine_from_config(local_conf, prefix='sqlalchemy.')
    sql.SQLBase.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    sql.session_key = local_conf.get('session_key', sql.session_key)
    return WSGISQLSession(next_app, maker, sql.session_key)


def initialize_cone_sql(config, global_config, local_config):
    """Cone startup application initialization.
    """
    # database initialization
    prefix = 'cone.sql.dbinit.'
    if local_config.get('%surl' % prefix, None) is None:
        return
    engine = engine_from_config(local_config, prefix)
    initialize_sql(engine)

cone.app.register_main_hook(initialize_cone_sql)
