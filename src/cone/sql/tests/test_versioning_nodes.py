from cone.app import get_root
from cone.app import register_entry
from cone.sql import SQLBase
from cone.sql import testing
from cone.sql.versioning import VersionedMixin
from cone.sql.versioning import VersionedSQLRowNode
from cone.sql.versioning import VersionedSQLTableNode
from cone.sql.versioning import VersionRegistryMixin
from node.tests import NodeTestCase
from sqlalchemy import Column
from sqlalchemy import String
import uuid


###############################################################################
# Test records and nodes
###############################################################################

class NoteRegistryRecord(VersionRegistryMixin, SQLBase):
    __tablename__ = 'note_registry'


class NoteRecord(VersionedMixin, SQLBase):
    __tablename__ = 'notes'
    registry_class = NoteRegistryRecord

    title = Column(String)
    body = Column(String)


class NoteNode(VersionedSQLRowNode):
    record_class = NoteRecord


class NoteContainer(VersionedSQLTableNode):
    record_class = NoteRecord
    child_factory = NoteNode


def reset_entry_registry(fn):
    """Decorator for tests using the entry node registry.
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


###############################################################################
# Tests
###############################################################################

class TestVersioningNodes(NodeTestCase):
    layer = testing.sql_layer

    @property
    def session(self):
        return self.layer.sql_session

    def tearDown(self):
        session = self.session
        session.rollback()
        session.query(NoteRecord).delete()
        session.query(NoteRegistryRecord).delete()
        session.commit()

    def container(self):
        register_entry('notes', NoteContainer)
        return get_root()['notes']

    def add_note(self, container, name, **attrs):
        """Add a note the way an application add form does it: write the
        attributes, put the node into the container, call the node.
        """
        node = NoteNode()
        for key, value in attrs.items():
            node.attrs[key] = value
        container[name] = node
        node()
        return node

    @reset_entry_registry
    def test_add(self):
        container = self.container()
        name = str(uuid.uuid4())
        self.add_note(container, name, title='first', body='text')

        records = self.session.query(NoteRecord).all()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, 'first')
        self.assertEqual(str(records[0].object_id), name)

        # The node name is the object identity, not the row identity - a row
        # identity would change with every edit and take every URL and every
        # stored reference with it.
        self.assertNotEqual(str(records[0].id), name)

    @reset_entry_registry
    def test_add_persisted_by_container_call(self):
        # ``cone.sql`` documents persisting through the container. Both paths
        # have to work, and calling both must not write twice.
        container = self.container()
        name = str(uuid.uuid4())
        node = NoteNode()
        node.attrs['title'] = 'first'
        container[name] = node
        container()

        self.assertEqual(self.session.query(NoteRecord).count(), 1)

        node()
        self.assertEqual(self.session.query(NoteRecord).count(), 1)

    @reset_entry_registry
    def test_getitem(self):
        container = self.container()
        name = str(uuid.uuid4())
        self.add_note(container, name, title='first')

        node = container[name]
        self.assertIsInstance(node, NoteNode)
        self.assertEqual(node.name, name)
        self.assertEqual(node.attrs['title'], 'first')

        # Traversal expects a ``KeyError`` before looking up views.
        with self.assertRaises(KeyError):
            container[str(uuid.uuid4())]

    @reset_entry_registry
    def test_edit_creates_new_version(self):
        container = self.container()
        name = str(uuid.uuid4())
        self.add_note(container, name, title='first', body='kept')

        node = container[name]
        node.attrs['title'] = 'second'
        node()

        records = self.session.query(NoteRecord).all()
        self.assertEqual(len(records), 2)

        # The container still shows one child, and it carries the new state.
        self.assertEqual(container.keys(), [name])
        self.assertEqual(container[name].attrs['title'], 'second')

        # Untouched attributes are carried over.
        self.assertEqual(container[name].attrs['body'], 'kept')

    @reset_entry_registry
    def test_edit_without_change_writes_nothing(self):
        # Versioning unchanged objects would grow the table without gaining
        # information.
        container = self.container()
        name = str(uuid.uuid4())
        self.add_note(container, name, title='first')

        node = container[name]
        node()
        self.assertEqual(self.session.query(NoteRecord).count(), 1)

    @reset_entry_registry
    def test_assigning_the_same_value_writes_nothing(self):
        # The bookkeeping says "changed", the row says otherwise - and a
        # version that differs from its predecessor in nothing is a row without
        # information. Reached without anyone doing it on purpose:
        # ``repoze.workflow`` assigns the state attribute again after the
        # transition callback has persisted it, so the next call of the node
        # would write the same state a second time.
        container = self.container()
        name = str(uuid.uuid4())
        self.add_note(container, name, title='first')

        node = container[name]
        node.attrs['title'] = 'first'
        node()
        self.assertEqual(self.session.query(NoteRecord).count(), 1)

    @reset_entry_registry
    def test_one_changed_value_among_unchanged_ones_still_writes(self):
        container = self.container()
        name = str(uuid.uuid4())
        self.add_note(container, name, title='first', body='kept')

        node = container[name]
        node.attrs['title'] = 'first'
        node.attrs['body'] = 'changed'
        node()
        self.assertEqual(self.session.query(NoteRecord).count(), 2)
        self.assertEqual(container[name].attrs['body'], 'changed')
        self.assertEqual(container[name].attrs['title'], 'first')

    @reset_entry_registry
    def test_written_attribute_is_readable_before_call(self):
        container = self.container()
        name = str(uuid.uuid4())
        self.add_note(container, name, title='first')

        node = container[name]
        node.attrs['title'] = 'second'
        # Reading has to see the pending write, not the persisted row - a form
        # rendering its own input after ``data.write`` would show stale data.
        self.assertEqual(node.attrs['title'], 'second')

    @reset_entry_registry
    def test_versioning_attributes_are_read_only(self):
        container = self.container()
        name = str(uuid.uuid4())
        self.add_note(container, name, title='first')
        node = container[name]

        self.assertIsNotNone(node.attrs['version_created'])
        for attribute in ['id', 'object_id', 'version_created',
                          'version_superseded', 'version_deleted']:
            with self.assertRaises(KeyError):
                node.attrs[attribute] = 'nope'

    @reset_entry_registry
    def test_object_id_assignable_once(self):
        # ``UUIDAsName`` derives the node name from an attribute, so the object
        # id has to be writable before the node reaches its container - but
        # only while no version exists.
        container = self.container()
        object_id = uuid.uuid4()

        node = NoteNode()
        node.attrs['object_id'] = object_id
        self.assertEqual(node.attrs['object_id'], object_id)
        with self.assertRaises(KeyError):
            node.attrs['object_id'] = uuid.uuid4()

        node.attrs['title'] = 'first'
        container[str(object_id)] = node
        node()

        record = self.session.query(NoteRecord).one()
        self.assertEqual(record.object_id, object_id)

    @reset_entry_registry
    def test_delitem_tombstones(self):
        container = self.container()
        name = str(uuid.uuid4())
        self.add_note(container, name, title='first')

        del container[name]
        container()

        # Nothing is removed - the grave row is a new version.
        self.assertEqual(self.session.query(NoteRecord).count(), 2)
        self.assertEqual(container.keys(), [])
        with self.assertRaises(KeyError):
            container[name]

        # The registry row survives, external references keep resolving.
        self.assertEqual(self.session.query(NoteRegistryRecord).count(), 1)

    @reset_entry_registry
    def test_iter_lists_current_only(self):
        container = self.container()
        first = str(uuid.uuid4())
        second = str(uuid.uuid4())
        self.add_note(container, first, title='first')
        self.add_note(container, second, title='second')

        node = container[first]
        node.attrs['title'] = 'changed'
        node()
        del container[second]
        container()

        # Two versions of the first, two of the second - one child.
        self.assertEqual(self.session.query(NoteRecord).count(), 4)
        self.assertEqual(container.keys(), [first])

    @reset_entry_registry
    def test_name_must_match_object_id(self):
        container = self.container()
        node = NoteNode()
        node.attrs['title'] = 'first'
        with self.assertRaises(KeyError):
            container['no-uuid'] = node

        with self.assertRaises(KeyError):
            container['no-uuid']

        # An existing node carries its object id, and filing it under a
        # different name would silently write to the wrong object.
        name = str(uuid.uuid4())
        self.add_note(container, name, title='first')
        existing = container[name]
        with self.assertRaises(KeyError):
            container[str(uuid.uuid4())] = existing
