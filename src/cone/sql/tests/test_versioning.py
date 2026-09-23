from cone.sql import SQLBase
from cone.sql import testing
from cone.sql.model import GUID
from cone.sql.versioning import InPlaceMutation
from cone.sql.versioning import ObjectIsDeleted
from cone.sql.versioning import ObjectIsNotDeleted
from cone.sql.versioning import UnknownObject
from cone.sql.versioning import VersionedMixin
from cone.sql.versioning import VersionRegistryMixin
from cone.sql.versioning import _version_metadata_handlers
from cone.sql.versioning import version_metadata_handler
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from node.tests import NodeTestCase
from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import StatementError
import uuid


###############################################################################
# Test records
###############################################################################

class ThingRegistryRecord(VersionRegistryMixin, SQLBase):
    """Registry for ``ThingRecord``, with a natural key.
    """
    __tablename__ = 'thing_registry'

    code = Column(String, unique=True)


class ThingRecord(VersionedMixin, SQLBase):
    """Versioned record used throughout these tests.
    """
    __tablename__ = 'things'
    registry_class = ThingRegistryRecord

    title = Column(String)
    note = Column(String)


class LeafRecord(VersionedMixin, SQLBase):
    """Versioned record without registry - nothing references it by object id.
    """
    __tablename__ = 'leafs'

    title = Column(String)


###############################################################################
# Tests
###############################################################################

class TestVersioning(NodeTestCase):
    layer = testing.sql_layer

    @property
    def session(self):
        return self.layer.sql_session

    def tearDown(self):
        session = self.session
        session.rollback()
        for record_class in (ThingRecord, LeafRecord, ThingRegistryRecord):
            session.query(record_class).delete()
        session.commit()

    def test_create(self):
        # Create writes the registry row first - it is the foreign key target
        # for everything referencing the object identity.
        session = self.session
        record = ThingRecord.create(
            session,
            registry_values=dict(code='thing-1'),
            title='initial'
        )
        session.flush()

        self.assertEqual(session.query(ThingRecord).count(), 1)
        self.assertEqual(record.title, 'initial')
        self.assertFalse(record.version_deleted)
        self.assertIsNone(record.version_superseded)
        self.assertIsInstance(record.version_created, datetime)

        # Row identity and object identity are distinct from the start. Sharing
        # them would make the first version indistinguishable from the object.
        self.assertNotEqual(record.id, record.object_id)

        registry = session.query(ThingRegistryRecord).one()
        self.assertEqual(registry.object_id, record.object_id)
        self.assertEqual(registry.code, 'thing-1')

    def test_create_without_registry(self):
        # A record nobody references by object id needs no registry. Its
        # object id is stable regardless.
        session = self.session
        record = LeafRecord.create(session, title='leaf')
        session.flush()

        self.assertIsNotNone(record.object_id)
        self.assertEqual(session.query(LeafRecord).count(), 1)

    def test_new_version(self):
        # An update never mutates - it supersedes the predecessor and inserts
        # a successor carrying the same object identity.
        session = self.session
        first = ThingRecord.create(session, title='initial', note='kept')
        session.flush()
        first_id = first.id
        object_id = first.object_id

        second = ThingRecord.new_version(session, object_id, title='changed')
        session.flush()

        self.assertEqual(session.query(ThingRecord).count(), 2)
        self.assertEqual(second.object_id, object_id)
        self.assertNotEqual(second.id, first_id)

        # Data columns not passed are carried over. Only what actually changed
        # is stated at the call site.
        self.assertEqual(second.title, 'changed')
        self.assertEqual(second.note, 'kept')

        # I4 - the timeline per object is gapless and free of overlap: the
        # predecessor ends exactly where the successor begins.
        predecessor = session.query(ThingRecord).filter(
            ThingRecord.id == first_id
        ).one()
        self.assertEqual(predecessor.version_superseded, second.version_created)

        # The predecessor keeps its data. That is the whole point.
        self.assertEqual(predecessor.title, 'initial')

    def test_current_returns_newest_live_version(self):
        session = self.session
        first = ThingRecord.create(session, title='initial')
        session.flush()
        ThingRecord.new_version(session, first.object_id, title='changed')
        session.flush()

        current = session.query(ThingRecord).filter(ThingRecord.current()).all()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].title, 'changed')

    def test_tombstone(self):
        # A tombstone is a new row, never an in place flag. Set in place it
        # would claim the object had not existed at earlier points in time.
        session = self.session
        first = ThingRecord.create(session, title='initial', note='kept')
        session.flush()
        object_id = first.object_id
        second = ThingRecord.new_version(session, object_id, title='changed')
        session.flush()
        second_id = second.id

        grave = ThingRecord.tombstone(session, object_id)
        session.flush()

        self.assertEqual(session.query(ThingRecord).count(), 3)
        self.assertTrue(grave.version_deleted)
        self.assertIsNone(grave.version_superseded)

        # The grave row carries the last known state.
        self.assertEqual(grave.title, 'changed')
        self.assertEqual(grave.note, 'kept')

        predecessor = session.query(ThingRecord).filter(
            ThingRecord.id == second_id
        ).one()
        self.assertEqual(predecessor.version_superseded, grave.version_created)
        self.assertFalse(predecessor.version_deleted)

        # Gone is not current ...
        self.assertEqual(
            session.query(ThingRecord).filter(ThingRecord.current()).count(),
            0
        )
        # ... but it is answerable as its own state.
        gone = session.query(ThingRecord).filter(ThingRecord.gone()).one()
        self.assertEqual(gone.id, grave.id)

        # The registry row survives the tombstone. External foreign keys point
        # at it and must not break because an object went away.
        self.assertEqual(session.query(ThingRegistryRecord).count(), 1)

    def test_as_of(self):
        # The point in time query is a range check, which is what
        # ``version_superseded`` buys over a boolean valid flag.
        session = self.session
        first = ThingRecord.create(session, title='initial')
        session.flush()
        object_id = first.object_id
        before_change = first.version_created + timedelta(microseconds=1)

        second = ThingRecord.new_version(session, object_id, title='changed')
        session.flush()
        before_tombstone = second.version_created + timedelta(microseconds=1)

        ThingRecord.tombstone(session, object_id)
        session.flush()

        # Before the change the first version was in effect.
        at_first = session.query(ThingRecord).filter(
            ThingRecord.as_of(before_change)
        ).one()
        self.assertEqual(at_first.title, 'initial')

        # Before the tombstone the object still existed - the deletion of today
        # must not reach backwards into the past.
        at_second = session.query(ThingRecord).filter(
            ThingRecord.as_of(before_tombstone)
        ).one()
        self.assertEqual(at_second.title, 'changed')

        # Today it is gone.
        self.assertEqual(
            session.query(ThingRecord).filter(
                ThingRecord.as_of(datetime.now(timezone.utc))
            ).count(),
            0
        )

    def test_resurrect(self):
        # A tombstone is not a final state. Reappearance is a new version on
        # top of the grave row, keeping the object identity - which is exactly
        # what external references need.
        session = self.session
        first = ThingRecord.create(session, title='initial')
        session.flush()
        object_id = first.object_id
        ThingRecord.tombstone(session, object_id)
        session.flush()

        revived = ThingRecord.resurrect(session, object_id, title='back')
        session.flush()

        self.assertEqual(revived.object_id, object_id)
        self.assertFalse(revived.version_deleted)
        self.assertEqual(revived.title, 'back')
        self.assertEqual(session.query(ThingRecord).count(), 3)
        self.assertEqual(
            session.query(ThingRecord).filter(ThingRecord.current()).count(),
            1
        )

    def test_history(self):
        session = self.session
        first = ThingRecord.create(session, title='initial')
        session.flush()
        object_id = first.object_id
        ThingRecord.new_version(session, object_id, title='changed')
        session.flush()

        history = ThingRecord.history(session, object_id).all()
        self.assertEqual([r.title for r in history], ['initial', 'changed'])

    def test_operations_refuse_wrong_state(self):
        session = self.session
        unknown = uuid.uuid4()

        with self.assertRaises(UnknownObject):
            ThingRecord.new_version(session, unknown, title='nope')
        with self.assertRaises(UnknownObject):
            ThingRecord.tombstone(session, unknown)

        record = ThingRecord.create(session, title='initial')
        session.flush()
        object_id = record.object_id

        # Resurrecting a live object would insert a second live version.
        with self.assertRaises(ObjectIsNotDeleted):
            ThingRecord.resurrect(session, object_id, title='nope')

        ThingRecord.tombstone(session, object_id)
        session.flush()

        # Versioning a gone object would silently revive it without saying so.
        with self.assertRaises(ObjectIsDeleted):
            ThingRecord.new_version(session, object_id, title='nope')
        with self.assertRaises(ObjectIsDeleted):
            ThingRecord.tombstone(session, object_id)

    def test_in_place_mutation_refused(self):
        # The guard inspects what changed, not who changed it - so it also
        # covers code paths that do not exist yet.
        session = self.session
        record = ThingRecord.create(session, title='initial')
        session.flush()

        record.title = 'mutated'
        with self.assertRaises(InPlaceMutation) as cm:
            session.flush()
        # The message names the column, because the fix is always the same:
        # call one of the four operations instead of assigning.
        self.assertIn('title', str(cm.exception))

    def test_in_place_tombstone_refused(self):
        # The partial unique index does not catch this one: with zero
        # unsuperseded rows the index is trivially satisfied.
        session = self.session
        record = ThingRecord.create(session, title='initial')
        session.flush()

        record.version_deleted = True
        with self.assertRaises(InPlaceMutation):
            session.flush()

    def test_delete_refused(self):
        session = self.session
        record = ThingRecord.create(session, title='initial')
        session.flush()

        session.delete(record)
        with self.assertRaises(InPlaceMutation):
            session.flush()

    def test_superseding_is_allowed(self):
        # The one update the pattern permits.
        session = self.session
        record = ThingRecord.create(session, title='initial')
        session.flush()

        record.version_superseded = datetime.now(timezone.utc)
        session.flush()

    def test_single_current_version_enforced(self):
        # I1 - a forgotten ``version_superseded`` update must be an immediate
        # constraint error instead of silent data garbage.
        session = self.session
        record = ThingRecord.create(session, title='initial')
        session.flush()

        session.add(ThingRecord(
            id=uuid.uuid4(),
            object_id=record.object_id,
            version_created=datetime.now(timezone.utc),
            title='second live version'
        ))
        with self.assertRaises(IntegrityError):
            session.flush()

    def test_naive_timestamp_refused(self):
        # Timestamps are timezone aware, and a naive one is rejected rather
        # than assumed to be UTC - once the distinction is lost, nothing
        # downstream can recover it.
        session = self.session
        record = ThingRecord.create(session, title='initial')
        session.flush()

        record.version_superseded = datetime.now()
        # Raised by the column type on bind, which SQLAlchemy wraps.
        with self.assertRaises(StatementError) as cm:
            session.flush()
        self.assertIsInstance(cm.exception.orig, ValueError)
        self.assertIn('timezone aware', str(cm.exception))

    def test_timestamps_are_utc(self):
        session = self.session
        record = ThingRecord.create(session, title='initial')
        session.flush()
        session.expire(record)

        self.assertEqual(record.version_created.tzinfo, timezone.utc)

    def test_registry_natural_key_is_unique(self):
        # The natural key prevents two object identities for one and the same
        # business object.
        session = self.session
        ThingRecord.create(
            session,
            registry_values=dict(code='thing-1'),
            title='first'
        )
        session.flush()

        # Raised inside ``create`` already - the registry row is flushed there,
        # because it is the foreign key target of the version about to follow.
        with self.assertRaises(IntegrityError):
            ThingRecord.create(
                session,
                registry_values=dict(code='thing-1'),
                title='duplicate'
            )

    def test_object_id_is_guid(self):
        self.assertIsInstance(ThingRecord.__table__.c.object_id.type, GUID)
        self.assertIsInstance(ThingRecord.__table__.c.id.type, GUID)

    def test_version_metadata_handler_stamps_every_new_version(self):
        # Application specific columns - a creator taken from the request
        # being the typical case - are stamped through a hook, keeping
        # ``cone.sql`` free of any principal source.
        def stamp_note(record):
            record.note = f'stamped {record.title}'

        self.assertIs(version_metadata_handler(stamp_note), stamp_note)
        try:
            session = self.session
            first = ThingRecord.create(session, title='initial')
            session.flush()
            second = ThingRecord.new_version(
                session,
                first.object_id,
                title='changed'
            )
            session.flush()
        finally:
            _version_metadata_handlers.remove(stamp_note)

        self.assertEqual(first.note, 'stamped initial')
        self.assertEqual(second.note, 'stamped changed')

    def test_registry_mutation_refused(self):
        # The registry is what external foreign keys point at - it is
        # immutable as well.
        session = self.session
        ThingRecord.create(
            session,
            registry_values=dict(code='thing-1'),
            title='initial'
        )
        session.flush()
        registry = session.query(ThingRegistryRecord).one()

        registry.code = 'thing-2'
        with self.assertRaises(InPlaceMutation) as cm:
            session.flush()
        self.assertIn('Registry rows are immutable', str(cm.exception))
        self.assertIn('code', str(cm.exception))

    def test_registry_assigned_its_own_value_is_accepted(self):
        # An assignment is not a change - only changed columns are refused.
        session = self.session
        ThingRecord.create(
            session,
            registry_values=dict(code='thing-1'),
            title='initial'
        )
        session.flush()
        registry = session.query(ThingRegistryRecord).one()

        registry.code = 'thing-1'
        self.assertIn(registry, session.dirty)
        session.flush()
        self.assertEqual(registry.code, 'thing-1')
