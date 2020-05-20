from cone.app import get_root
from cone.app import register_entry
from cone.sql import get_session
from cone.sql import SQLBase
from cone.sql import testing
from cone.sql import use_tm
from cone.sql.model import GUID
from cone.sql.model import SQLRowNode
from cone.sql.model import SQLTableNode
from cone.sql.model import UNICODE_TYPE
from node.tests import NodeTestCase
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql.base import UUID
from sqlalchemy.engine import default
from sqlalchemy.orm.session import Session
from sqlalchemy.orm.unitofwork import UOWTransaction
from sqlalchemy.sql.sqltypes import CHAR
import os
import uuid


def reset_entry_registry(fn):
    """Decorator for tests using entry node registry
    """
    def wrapper(*a, **kw):
        root = get_root()
        factories = set(root.factories.keys())
        try:
            fn(*a, **kw)
        finally:
            for key in set(root.factories.keys()).difference(factories):
                del root.factories[key]
    return wrapper


class UUIDAsPrimaryKeyRecord(SQLBase):
    """Record with UUID as primary key.
    """
    __tablename__ = 'uuid_as_primary_key'
    uid_key = Column(GUID, primary_key=True)
    field = Column(String)


class UUIDAsKeyNode(SQLRowNode):
    record_class = UUIDAsPrimaryKeyRecord


class UUIDAsKeyContainer(SQLTableNode):
    record_class = UUIDAsPrimaryKeyRecord
    child_factory = UUIDAsKeyNode


class StringAsPrimaryKeyRecord(SQLBase):
    """Record with string as primary key.
    """
    __tablename__ = 'string_as_primary_key'
    string_key = Column(String, primary_key=True)
    field = Column(String)


class StringAsKeyNode(SQLRowNode):
    record_class = StringAsPrimaryKeyRecord


class StringAsKeyContainer(SQLTableNode):
    record_class = StringAsPrimaryKeyRecord
    child_factory = StringAsKeyNode


class IntegerAsPrimaryKeyRecord(SQLBase):
    """Record with integer as primary key.
    """
    __tablename__ = 'integer_as_primary_key'
    integer_key = Column(Integer, primary_key=True)
    field = Column(String)


class IntegerAsKeyNode(SQLRowNode):
    record_class = IntegerAsPrimaryKeyRecord


class IntegerAsKeyContainer(SQLTableNode):
    record_class = IntegerAsPrimaryKeyRecord
    child_factory = IntegerAsKeyNode


class TestModel(NodeTestCase):
    layer = testing.sql_layer

    def test_GUID(self):
        # Platform independent GUID data type

        # Define a dummy dialect
        class DummyDialect(default.DefaultDialect):
            name = None

        dialect = DummyDialect()

        # Instanciate ``GUID`` data type
        guid = GUID()

        # Test ``load_dialect_impl``
        dialect.name = 'postgresql'
        res = guid.load_dialect_impl(dialect)
        self.assertTrue(isinstance(res, UUID))

        dialect.name = 'other'
        res = guid.load_dialect_impl(dialect)
        self.assertTrue(isinstance(res, CHAR))

        # Test ``process_bind_param``
        dialect.name = 'postgresql'
        guid.process_bind_param(None, dialect)

        value = uuid.UUID('d8f1d964-9f2f-4df5-9f30-c5a90052576d')
        self.assertEqual(
            guid.process_bind_param(value, dialect),
            'd8f1d964-9f2f-4df5-9f30-c5a90052576d'
        )

        dialect.name = 'other'
        self.assertEqual(
            guid.process_bind_param(value, dialect),
            'd8f1d9649f2f4df59f30c5a90052576d'
        )

        value = str(value)
        self.assertEqual(
            guid.process_bind_param(value, dialect),
            'd8f1d9649f2f4df59f30c5a90052576d'
        )

        # Test ``process_result_value``
        guid.process_result_value(None, dialect)

        self.assertEqual(
            guid.process_result_value(value, dialect),
            uuid.UUID('d8f1d964-9f2f-4df5-9f30-c5a90052576d')
        )

    @reset_entry_registry
    def test_UUID_as_primary_key(self):
        # Resgister entry
        register_entry('uuid_as_key_container', UUIDAsKeyContainer)

        # Get container from root
        root = get_root()
        container = root['uuid_as_key_container']

        # Add node to container
        node_uid = '6090411e-d249-4dc6-9da1-74172919f1ed'
        node = container[node_uid] = UUIDAsKeyNode()
        node.attrs['field'] = u'Value'

        # Persist data
        container()

        # Query data record using SQLAlchemy directly
        request = self.layer.new_request()
        session = get_session(request)
        rec = session.query(UUIDAsPrimaryKeyRecord).get(uuid.UUID(node_uid))
        self.assertTrue(isinstance(rec, UUIDAsPrimaryKeyRecord))

        # Get children via node API
        node = container['6090411e-d249-4dc6-9da1-74172919f1ed']
        self.assertTrue(isinstance(node, UUIDAsKeyNode))
        self.assertEqual(
            container.keys(),
            ['6090411e-d249-4dc6-9da1-74172919f1ed']
        )
        self.assertEqual(len(container.values()), 1)
        self.assertEqual(
            container.values()[0].name,
            '6090411e-d249-4dc6-9da1-74172919f1ed'
        )
        self.assertEqual(len(container.items()), 1)
        self.assertEqual(
            container.items()[0][0],
            '6090411e-d249-4dc6-9da1-74172919f1ed'
        )
        self.assertEqual(
            container.items()[0][1].name,
            '6090411e-d249-4dc6-9da1-74172919f1ed'
        )
        self.assertEqual(
            sorted(node.attrs.items()),
            [
                ('field', u'Value'),
                ('uid_key', uuid.UUID('6090411e-d249-4dc6-9da1-74172919f1ed'))
            ]
        )

    @reset_entry_registry
    def test_string_as_primary_key(self):
        # Resgister entry.
        register_entry('string_as_key_container', StringAsKeyContainer)

        # Get container from root
        root = get_root()
        container = root['string_as_key_container']

        # Add node to container
        node = container[u'key'] = StringAsKeyNode()
        node.attrs['field'] = u'Value'

        # Persist data
        container()

        # Query data record using SQLAlchemy directly
        request = self.layer.new_request()
        session = get_session(request)
        rec = session.query(StringAsPrimaryKeyRecord).get(u'key')
        self.assertTrue(isinstance(rec, StringAsPrimaryKeyRecord))

        # Get children via node API
        node = container['key']
        self.assertTrue(isinstance(node, StringAsKeyNode))
        self.assertEqual(container.keys(), ['key'])
        self.assertEqual(len(container.values()), 1)
        self.assertEqual(container.values()[0].name, 'key')
        self.assertEqual(len(container.items()), 1)
        self.assertEqual(container.items()[0][0], 'key')
        self.assertEqual(container.items()[0][1].name, 'key')
        self.assertEqual(
            sorted(node.attrs.items()),
            [('field', u'Value'), ('string_key', u'key')]
        )

    @reset_entry_registry
    @testing.delete_table_records(IntegerAsPrimaryKeyRecord)
    def test_int_as_primary_key(self):
        # Resgister entry
        register_entry('integer_as_key_container', IntegerAsKeyContainer)

        # Get container from root
        root = get_root()
        container = root['integer_as_key_container']

        # Add node to container
        node = container['1234'] = IntegerAsKeyNode()
        node.attrs['field'] = u'Value'

        # Persist data
        container()

        # Query data record using SQLAlchemy directly
        request = self.layer.new_request()
        session = get_session(request)
        rec = session.query(IntegerAsPrimaryKeyRecord).get('1234')
        self.assertTrue(isinstance(rec, IntegerAsPrimaryKeyRecord))

        # Get children via node API
        node = container['1234']
        self.assertTrue(isinstance(node, IntegerAsKeyNode))
        self.assertEqual(container.keys(), ['1234'])
        self.assertEqual(len(container.values()), 1)
        self.assertEqual(container.values()[0].name, '1234')
        self.assertEqual(len(container.items()), 1)
        self.assertEqual(container.items()[0][0], '1234')
        self.assertEqual(container.items()[0][1].name, '1234')
        self.assertEqual(
            sorted(node.attrs.items()),
            [('field', u'Value'), ('integer_key', 1234)]
        )

    def test_data_type_converters(self):
        # SQLAlchemy data types for primary keys can be extended on
        # ``data_type_converters``
        converters = sorted(
            SQLTableNode.data_type_converters.items(),
            key=lambda x: x[0].__name__
        )
        self.assertEqual(converters, [
            (GUID, uuid.UUID),
            (Integer, int),
            (String, UNICODE_TYPE)
        ])

    @reset_entry_registry
    @testing.delete_table_records(IntegerAsPrimaryKeyRecord)
    def test_node_api(self):
        # Resgister entry
        register_entry('integer_as_key_container', IntegerAsKeyContainer)

        # ``__getitem__`` and ``__setitem__`` raise a ``KeyError`` if node name
        # cannot be converted to primary key data type
        root = get_root()
        container = root['integer_as_key_container']

        err = self.expect_error(KeyError, container.__getitem__, 'a')
        expected = (
            '"Failed to convert node name to expected primary key data type: '
            'invalid literal for int() with base 10: \'a\'"'
        )
        self.assertEqual(str(err), expected)

        err = self.expect_error(
            KeyError,
            container.__setitem__,
            'a',
            IntegerAsKeyNode()
        )
        expected = (
            '"Failed to convert node name to expected primary key data type: '
            'invalid literal for int() with base 10: \'a\'"'
        )
        self.assertEqual(str(err), expected)

        # If primary key attribute is set on node and given name on
        # ``__setitem__`` not matches attribute value, a ``KeyError`` is thrown.
        child = IntegerAsKeyNode()
        child.attrs['integer_key'] = 123
        err = self.expect_error(
            KeyError,
            container.__setitem__,
            '124',
            child
        )
        expected = "'Node name must match primary key attribute value: 124 != 123'"
        self.assertEqual(str(err), expected)

        # Access inexistent child
        err = self.expect_error(
            KeyError,
            container.__getitem__,
            '124'
        )
        self.assertEqual(str(err), "'124'")

        # If primary key attribute not set, it gets automatically set by name
        # on ``__setitem__``.
        child = IntegerAsKeyNode()
        container['123'] = child
        self.assertEqual(
            sorted(child.attrs.items()),
            [('field', None), ('integer_key', 123)]
        )

        # SQL model column values can be accessed and set via ``attrs``
        child.attrs['field'] = u'Value'
        self.assertEqual(
            sorted(child.attrs.items()),
            [('field', u'Value'), ('integer_key', 123)]
        )

        # SQL model gets persisted on ``__call__``.
        container()

        request = self.layer.new_request()
        session = get_session(request)
        res = session.query(IntegerAsPrimaryKeyRecord).all()
        self.assertEqual(len(res), 1)

        # Override child
        child = IntegerAsKeyNode()
        child.attrs['field'] = u'Other Value'
        container['123'] = child
        self.assertEqual(
            sorted(child.attrs.items()),
            [('field', u'Other Value'), ('integer_key', 123)]
        )

        container()
        request = self.layer.new_request()
        session = get_session(request)
        res = session.query(IntegerAsPrimaryKeyRecord).all()
        self.assertEqual(len(res), 1)

        # Delete child
        del container['123']

        request = self.layer.new_request()
        session = get_session(request)
        res = session.query(IntegerAsPrimaryKeyRecord).all()
        self.assertEqual(len(res), 0)

        # Other than most other node implementations, ``TableRowNodes`` can be
        # persisted without being hooked up to the tree directly.
        child = IntegerAsKeyNode()
        child.attrs['integer_key'] = 1234
        child.attrs['field'] = u'Value'
        child()

        self.assertEqual(container.keys(), ['1234'])

        # Update Child
        child = container['1234']
        child.attrs['field'] = u'Updated Value'
        child()

        request = self.layer.new_request()
        session = get_session(request)
        self.assertEqual(
            session.query(IntegerAsPrimaryKeyRecord).first().field,
            u'Updated Value'
        )

        # Access inexisting attributes
        err = self.expect_error(
            KeyError,
            child.attrs.__getitem__,
            'inexistent'
        )
        self.assertEqual(str(err), "'Unknown attribute: inexistent'")

        err = self.expect_error(
            KeyError,
            child.attrs.__setitem__,
            'inexistent',
            'Value'
        )
        self.assertEqual(str(err), "'Unknown attribute: inexistent'")

        # SQL row node attributes cannot be deleted
        err = self.expect_error(
            KeyError,
            child.attrs.__delitem__,
            'field'
        )
        self.assertEqual(str(err), "'Deleting of attributes not allowed'")

        # SQL row node is a leaf thus containment API always raises KeyError
        # and iter returns empty result.
        err = self.expect_error(
            KeyError,
            child.__setitem__,
            'foo',
            'foo'
        )
        self.assertEqual(str(err), "'foo'")

        err = self.expect_error(
            KeyError,
            child.__getitem__,
            'foo'
        )
        self.assertEqual(str(err), "'foo'")

        err = self.expect_error(
            KeyError,
            child.__delitem__,
            'foo'
        )
        self.assertEqual(str(err), "'foo'")

        self.assertEqual(list(iter(child)), [])

    @reset_entry_registry
    @testing.delete_table_records(IntegerAsPrimaryKeyRecord)
    def test_use_tm(self):
        # Resgister entry
        register_entry('integer_as_key_container', IntegerAsKeyContainer)

        root = get_root()
        container = root['integer_as_key_container']

        # create a base entry for direct node modification test
        request = self.layer.new_request()
        node = container['1'] = IntegerAsKeyNode()
        node.attrs['field'] = 'Value'
        node()

        # transaction manager used, calling nodes flushes session
        os.environ['CONE_SQL_USE_TM'] = '1'
        self.assertTrue(use_tm())

        # modify existing node
        node.attrs['field'] = 'New'
        node()

        # create new node
        container['2'] = IntegerAsKeyNode()
        container()

        session = get_session(request)
        res = session.query(IntegerAsPrimaryKeyRecord).all()
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].field, 'New')

        # rollback works, session was just flushed
        session.rollback()
        res = session.query(IntegerAsPrimaryKeyRecord).all()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].field, 'Value')

        # no transaction manager used, calling nodes commits session
        os.environ['CONE_SQL_USE_TM'] = '0'
        self.assertFalse(use_tm())

        # modify existing node
        node.attrs['field'] = 'New'
        node()

        # create new node
        container['2'] = IntegerAsKeyNode()
        container()

        session = get_session(request)
        res = session.query(IntegerAsPrimaryKeyRecord).all()
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].field, 'New')

        # rollback has not effect, session was commited
        session.rollback()
        res = session.query(IntegerAsPrimaryKeyRecord).all()
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].field, 'New')

    @reset_entry_registry
    @testing.delete_table_records(IntegerAsPrimaryKeyRecord)
    def test_sql_session_setup(self):
        # Resgister entry
        register_entry('integer_as_key_container', IntegerAsKeyContainer)

        # Test ``sql_session_setup``. The SQL session setup handler is defined
        # in ``cone.sql.testing`` and registers a callback to ``after_flush``
        # event. Patch desired callback reference and test whether it's called.
        class Callback(object):
            session = None
            flush_context = None

            def __call__(self, session, flush_context):
                self.session = session
                self.flush_context = flush_context

        callback = Callback()
        testing.test_after_flush = callback

        root = get_root()
        container = root['integer_as_key_container']
        node = container['1236'] = IntegerAsKeyNode()
        node.attrs['field'] = u'Value'
        container()

        self.assertTrue(isinstance(callback.session, Session))
        self.assertTrue(isinstance(callback.flush_context, UOWTransaction))

        testing.test_after_flush = None
