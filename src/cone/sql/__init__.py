from cone.app import get_root
from cone.app import main_hook
from cone.app import ugm_backend
from cone.app.ugm import UGMFactory
from sqlalchemy import engine_from_config
from sqlalchemy import MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker
from zope.sqlalchemy import register
import os


###############################################################################
# Utils
###############################################################################

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


def use_tm():
    """Flag whether transaction manager is used.
    """
    return os.environ.get('CONE_SQL_USE_TM') == '1'


###############################################################################
# DB initialization
###############################################################################

metadata = MetaData()
SQLBase = declarative_base(metadata=metadata)
DBSession = scoped_session(sessionmaker())


def initialize_sql(engine):
    """Basic SQL initialization.
    """
    DBSession.configure(bind=engine)
    metadata.bind = engine
    metadata.create_all(engine)


###############################################################################
# Session Factory
###############################################################################

class SQLSessionFactory(object):
    """SQL session factory.
    """

    def __init__(self, settings, prefix):
        self.engine = engine_from_config(settings, prefix=prefix)
        self.maker = sessionmaker(bind=self.engine)

    def __call__(self):
        session = self.maker()
        setup_session(session)
        return session


# Global session factory singleton.
session_factory = None


###############################################################################
# WSGI
###############################################################################

class WSGISQLSession(object):
    """WSGI framework component that opens and closes a SQL session.

    Downstream applications will have the session in the environment,
    normally under the key 'cone.sql.session'.
    """

    def __init__(self, next_app, session_key=session_key):
        self.next_app = next_app
        self.session_key = session_key

    def __call__(self, environ, start_response):
        session = session_factory()
        register(session)
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
    sql.session_key = local_conf.get('session_key', sql.session_key)
    return WSGISQLSession(next_app, sql.session_key)


###############################################################################
# Cone startup integration
###############################################################################

@main_hook
def initialize_cone_sql(config, global_config, settings):
    """Cone startup application initialization.
    """
    # database initialization
    prefix = 'sql.db.'
    if settings.get('{}url'.format(prefix), None) is None:  # pragma: no cover
        return
    if settings.get('ugm.backend') == 'sql':
        # If SQL configured as UGM backend, import ugm module to ensure proper
        # table creation at initialize_sql time.
        import cone.sql.ugm  # noqa
    global session_factory
    session_factory = SQLSessionFactory(settings, prefix)
    initialize_sql(session_factory.engine)
    use_tm = settings.get('pyramid.includes', '').find('pyramid_tm') > -1
    os.environ['CONE_SQL_USE_TM'] = '1' if use_tm else '0'


###############################################################################
# UGM factory
###############################################################################

@ugm_backend('sql')
class SqlUGMFactory(UGMFactory):
    """UGM backend factory for SQL based UGM implementation.
    """

    def __init__(self, settings):
        # cone.ugm active, users and groups attributes are read from ugm config
        if settings.get('cone.plugins').find('cone.ugm') > -1:
            from cone.ugm.utils import general_settings
            model = get_root()
            ugm_settings = general_settings(model).attrs
            self.user_attrs = ugm_settings.users_form_attrmap.keys()
            self.group_attrs = ugm_settings.groups_form_attrmap.keys()
        # users and groups attributes are read from application ini file
        else:
            self.user_attrs = [
                attr.strip() for attr in
                settings.get('sql.user_attrs', '').split(',')
                if attr.strip()
            ]
            self.group_attrs = [
                attr.strip() for attr in
                settings.get('sql.group_attrs', '').split(',')
                if attr.strip()
            ]
        self.binary_attrs = [
            attr.strip() for attr in
            settings.get('sql.binary_attrs', '').split(',')
            if attr.strip()
        ]
        self.log_auth = settings.get('sql.log_auth') in ['true', 'True', '1']

    def __call__(self):
        from cone.sql.ugm import Ugm
        return Ugm(
            name="sql_ugm",
            parent=None,
            user_attrs=self.user_attrs,
            group_attrs=self.group_attrs,
            binary_attrs=self.binary_attrs,
            log_auth=self.log_auth
        )
