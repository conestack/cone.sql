from cone.app.model import BaseNode
from cone.sql import get_session
from node.behaviors import NodeAttributes
from pyramid.i18n import TranslationStringFactory
from pyramid.threadlocal import get_current_request
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import CHAR
from sqlalchemy.types import TypeDecorator
import uuid


###############################################################################
# SQL model basics
###############################################################################

class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses Postgresql's UUID type, otherwise uses
    CHAR(32), storing as stringified hex values.

    http://docs.sqlalchemy.org/en/rel_0_8/core/types.html#backend-agnostic-guid-type
    """
    impl = CHAR

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
                return "%.32x" % uuid.UUID(value)
            else:
                # hexstring
                return "%.32x" % value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            return uuid.UUID(value)


###############################################################################
# application node basics
###############################################################################

class SQLTableNode(BaseNode):
    # SQL alchemy model class
    record_class = None
    # factory for node children
    child_factory = None
    # map SQL alchemy data types to callables converting values to expected
    # type
    data_type_converters = {
        GUID: uuid.UUID,
        String: unicode,
        Integer: int,
    }

    @property
    def primary_key(self):
        if not hasattr(self, '_primary_key'):
            self._primary_key = inspect(self.record_class).primary_key
        return self._primary_key

    def _convert_primary_key(self, name):
        # XXX: multiple primary key support
        primary_key = self.primary_key[0]
        primary_key_type = primary_key.type.__class__
        try:
            converter = self.data_type_converters[primary_key_type]
            primary_key_value = converter(name)
            return primary_key_value
        except Exception, e:
            msg = (
                'Failed to convert node name to expected primary key '
                'data type: {}'
            ).format(e)
            raise KeyError(msg)

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
        if value.name is None:
            value.__name__ = name
        session = get_session(get_current_request())
        session.add(value.record)

    def __getitem__(self, name):
        # XXX: multiple primary key support
        primary_key = self.primary_key[0]
        primary_key_value = self._convert_primary_key(name)
        session = get_session(get_current_request())
        query = session.query(self.record_class)
        # always expect uid attribute as primary key
        record = query.filter(
            getattr(self.record_class, primary_key.name) == primary_key_value
        ).first()
        if record is None:
            # traversal expects KeyError before looking up views.
            raise KeyError(name)
        return self.child_factory(name, self, record)

    def __delitem__(self, name):
        child = self[name]
        session = get_session(get_current_request())
        session.delete(child.record)

    def __iter__(self):
        # XXX: multiple primary key support
        session = get_session(get_current_request())
        result = session.query(getattr(self.record_class, primary_key.name))
        for recid in result.all():
            yield str(recid[0])

    def __call__(self):
        session = get_session(get_current_request())
        session.commit()


class SQLRowNodeAttributes(NodeAttributes):

    def __init__(self, name, parent, record):
        NodeAttributes.__init__(self, name, parent)
        self.record = record

    @property
    def _columns(self):
        return inspect(self.record.__class__).attrs.keys()

    def __getitem__(self, name):
        if name in self:
            return getattr(self.record, name)
        raise KeyError(name)

    def __setitem__(self, name, value):
        if name in self:
            setattr(self.record, name, value)
        else:
            raise KeyError(u'unknown attribute: %s' % name)

    def __delitem__(self):
        raise NotImplementedError

    def __iter__(self):
        return iter(self._columns)

    def __contains__(self, name):
        return name in self._columns


class SQLRowNode(BaseNode):
    record_factory = None

    def __init__(self, name=None, parent=None, record=None):
        self.__name__ = name
        self.__parent__ = parent
        self._new = False
        if record is None:
            self._new = True
            record = self.record_factory()
        self.record = record

    def attributes_factory(self, name, parent):
        return SQLRowNodeAttributes(name, parent, self.record)

    def __call__(self):
        session = get_session(get_current_request())
        if self._new:
            session.add(self.record)
            self._new = False
        session.commit()
