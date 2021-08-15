from cone.app.model import AppNode
from cone.sql import get_session
from cone.sql import use_tm
from node.behaviors import Adopt
from node.behaviors import Attributes
from node.behaviors import DefaultInit
from node.behaviors import Lifecycle
from node.behaviors import NodeAttributes
from node.behaviors import Nodespaces
from node.behaviors import Nodify
from node.interfaces import ICallable
from node.interfaces import IStorage
from plumber import Behavior
from plumber import default
from plumber import finalize
from plumber import override
from plumber import plumbing
from pyramid.threadlocal import get_current_request
from sqlalchemy import inspect
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import CHAR
from sqlalchemy.types import TypeDecorator
from zope.interface import implementer
import sys
import uuid


###############################################################################
# Compat
###############################################################################

IS_PY2 = sys.version_info[0] < 3
UNICODE_TYPE = unicode if IS_PY2 else str


###############################################################################
# SQLAlchemy data types
###############################################################################

class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses Postgresql's UUID type, otherwise uses
    CHAR(32), storing as stringified hex values.

    http://docs.sqlalchemy.org/en/rel_0_8/core/types.html#backend-agnostic-guid-type
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(UUID())
        else:
            return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return "%.32x" % int(uuid.UUID(value))
            else:
                # hexstring
                return "%.32x" % int(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            return uuid.UUID(value)


###############################################################################
# SQL table storage
###############################################################################

@implementer(IStorage, ICallable)
class SQLTableStorage(Behavior):
    # SQL alchemy model class
    record_class = default(None)
    # SQL alchemy session
    session = default(None)
    # factory for node children
    child_factory = default(None)
    # map SQL alchemy data types to callables converting values to expected
    # type
    data_type_converters = default({
        GUID: uuid.UUID,
        String: UNICODE_TYPE,
        Integer: int,
    })

    @default
    @property
    def primary_key(self):
        if not hasattr(self, '_primary_key'):
            self._primary_key = inspect(self.record_class).primary_key
        return self._primary_key

    @default
    def _convert_primary_key(self, name):
        # XXX: multiple primary key support
        primary_key = self.primary_key[0]
        primary_key_type = primary_key.type.__class__
        try:
            converter = self.data_type_converters[primary_key_type]
            primary_key_value = converter(name)
            return primary_key_value
        except Exception as e:
            msg = (
                'Failed to convert node name to expected primary key '
                'data type: {}'
            ).format(e)
            raise KeyError(msg)

    @finalize
    def __setitem__(self, name, value):
        # XXX: multiple primary key support
        primary_key = self.primary_key[0]
        primary_key_value = self._convert_primary_key(name)
        attrs = value.attrs
        if not attrs[primary_key.name]:
            attrs[primary_key.name] = primary_key_value
        if primary_key_value != attrs[primary_key.name]:
            msg = (
                'Node name must match primary key attribute value: {} != {}'
            ).format(primary_key_value, attrs[primary_key.name])
            raise KeyError(msg)
        session = self.session
        query = session.query(self.record_class).filter(
            getattr(self.record_class, primary_key.name) == primary_key_value)
        if not session.query(query.exists()).scalar():
            session.add(value.record)
        else:
            record = query.first()
            for k, v in value.attrs.items():
                setattr(record, k, v)
            value.record = value.attrs.record = record

    @finalize
    def __getitem__(self, name):
        # XXX: multiple primary key support
        primary_key = self.primary_key[0]
        primary_key_value = self._convert_primary_key(name)
        session = self.session
        query = session.query(self.record_class)
        record = query.filter(
            getattr(self.record_class, primary_key.name) == primary_key_value
        ).first()
        if record is None:
            # traversal expects ``KeyError`` before looking up views.
            raise KeyError(name)
        return self.child_factory(name, self, record)

    @finalize
    def __delitem__(self, name):
        child = self[name]
        session = self.session
        session.delete(child.record)

    @finalize
    def __iter__(self):
        # XXX: multiple primary key support
        primary_key = self.primary_key[0]
        session = self.session
        result = session.query(getattr(self.record_class, primary_key.name))
        for recid in result.all():
            yield str(recid[0])

    @finalize
    def __call__(self):
        if use_tm():
            self.session.flush()
        else:
            self.session.commit()


###############################################################################
# SQL row storage
###############################################################################

class SQLRowNodeAttributes(NodeAttributes):

    def __init__(self, name, parent, record):
        NodeAttributes.__init__(self, name, parent)
        self.record = record

    @property
    def _columns(self):
        return inspect(self.record.__class__).attrs.keys()

    def __setitem__(self, name, value):
        if name in self:
            setattr(self.record, name, value)
        else:
            raise KeyError('Unknown attribute: {}'.format(name))

    def __getitem__(self, name):
        if name in self:
            return getattr(self.record, name)
        raise KeyError('Unknown attribute: {}'.format(name))

    def __delitem__(self, name):
        raise KeyError('Deleting of attributes not allowed')

    def __iter__(self):
        return iter(self._columns)

    def __contains__(self, name):
        return name in self._columns


@implementer(IStorage, ICallable)
class SQLRowStorage(Behavior):
    # SQL alchemy model class
    record_class = default(None)
    # SQL alchemy session
    session = default(None)

    @override
    def __init__(self, name=None, parent=None, record=None):
        self.__name__ = name
        self.__parent__ = parent
        self._new = False
        if record is None:
            self._new = True
            record = self.record_class()
        self.record = record

    @override
    def attributes_factory(self, name, parent):
        return SQLRowNodeAttributes(name, parent, self.record)

    @finalize
    def __setitem__(self, name, value):
        raise KeyError(name)

    @finalize
    def __getitem__(self, name):
        raise KeyError(name)

    @finalize
    def __delitem__(self, name):  # pragma: no cover
        # not reached by default SQLRowNode, KeyError already thrown in
        # Lifecycle plumbing Behavior
        raise KeyError(name)

    @finalize
    def __iter__(self):
        return iter([])

    @finalize
    def __call__(self):
        session = self.session
        if self._new:
            session.add(self.record)
            self._new = False
        if use_tm():
            self.session.flush()
        else:
            self.session.commit()


###############################################################################
# SQL session provider
###############################################################################

class SQLSession(Behavior):
    """Behavior providing SQLAlchemy session from pyramid request.
    """

    @finalize
    @property
    def session(self):
        return get_session(get_current_request())


###############################################################################
# Application node basics
###############################################################################

@plumbing(
    AppNode,
    Adopt,
    DefaultInit,
    Nodify,
    Lifecycle,
    SQLSession,
    SQLTableStorage)
class SQLTableNode(object):
    """Basic SQL table providing node.
    """


@plumbing(
    AppNode,
    Nodespaces,
    Attributes,
    Nodify,
    Lifecycle,
    SQLSession,
    SQLRowStorage)
class SQLRowNode(object):
    """Basic SQL row providing node.
    """
