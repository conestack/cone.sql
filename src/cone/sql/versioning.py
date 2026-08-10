"""Append-only versioning with tombstones.

Nothing is ever updated or deleted. A change inserts a new row and marks the
previous one superseded; a deletion inserts a *grave* row. The only UPDATE the
pattern permits is ``SET version_superseded = :now`` on a predecessor.

Five columns carry it::

    id                  row identity - one state at one point in time
    object_id           object identity - stable across all versions
    version_deleted     tombstone: the object does not exist any more
    version_created     this version is in effect from
    version_superseded  replaced by a newer version; NULL means youngest

The ``version_`` prefix is deliberate. In a ``cone`` application ``created``
already means "when was this entry made", which is orthogonal to how many
versions of it exist - and ``deleted`` is an even more common application
column. Unprefixed, the mixin would collide with exactly those, and a concrete
class declaring its own would silently override the mixin's, taking the NOT
NULL constraint with it. The prefix also states at every query site which
mechanism a condition belongs to.

Three states, fully determined by two columns::

    current     version_superseded IS NULL AND NOT version_deleted
    gone        version_superseded IS NULL AND version_deleted
    historical  version_superseded IS NOT NULL

``version_superseded`` rather than a ``valid`` boolean, because it makes the
current query a NULL check and the point in time query a range check - both
directly indexable. With a boolean the point in time query would need GROUP BY
subqueries.

Invariants, enforced where the database can::

    I1  at most one row per object_id with version_superseded IS NULL
    I2  data columns of a superseded row are never changed
    I3  version_deleted is only ever set on a newly inserted row
    I4  the timeline per object_id is gapless and free of overlap:
        predecessor.version_superseded == successor.version_created

**There is no fifth operation.** Create, new version, tombstone and resurrect
are classmethods on :class:`VersionedMixin` and are the only write path onto a
versioned table.

Three guards, deliberately layered, because fewer are not enough:

1. **The operations themselves**, resolving the current row by ``object_id`` so
   a historical row can never be superseded by accident.
2. **The flush hook** :func:`forbid_in_place_mutation`, which rejects any UPDATE
   touching anything but ``version_superseded``, and any DELETE. It inspects
   *what* changed, not who changed it - so it also covers code paths that do
   not exist yet.
3. **The partial unique index** on ``(object_id) WHERE version_superseded IS
   NULL``. Note it does *not* catch an in place tombstone: with zero
   unsuperseded rows the index is trivially satisfied, which is why guard 2
   exists.

Timestamps are timezone aware and stored as UTC via
:class:`cone.sql.model.UTCDateTime`. Naive values are rejected. Local time
would make a point in time query ambiguous during the autumn DST fold, where
one wall clock hour repeats - and the timeline is what this whole module is
about.

Scope of this module - it is deliberately narrow, because ``cone.sql`` is a
generic package and knows no domain:

- **No tenant concept.** Applications add their own scoping column.
- **No principal source.** ``created_by`` and friends are stamped by handlers
  registered via :func:`version_metadata_handler`.
- **Opt in.** ``SQLBase`` is untouched; only classes mixing in
  :class:`VersionedMixin` are affected.

One setup requirement the application owns: **SQLite needs**
``PRAGMA foreign_keys=ON``. Without it the registry foreign key is declarative
only and buys nothing.
"""

from cone.sql.model import GUID
from cone.sql.model import UTCDateTime
from datetime import datetime
from datetime import timezone
from sqlalchemy import and_
from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import event
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import inspect
from sqlalchemy import text
from sqlalchemy.orm import declared_attr
from sqlalchemy.orm import Session
import uuid


###############################################################################
# Errors
###############################################################################

class VersioningError(Exception):
    """Base for every refusal of the write path.
    """


class UnknownObject(VersioningError):
    """No row exists for that object identity.
    """


class ObjectIsDeleted(VersioningError):
    """The object is tombstoned - use ``resurrect``.
    """


class ObjectIsNotDeleted(VersioningError):
    """The object is live - use ``new_version``.
    """


class InPlaceMutation(VersioningError):
    """Something tried to change or delete an existing versioned row.

    The message names the column, because the fix is always the same: call one
    of the four operations instead of assigning.
    """


###############################################################################
# Metadata handlers
###############################################################################

# Callables stamping application specific columns on newly written versions.
_version_metadata_handlers = list()


def version_metadata_handler(ob):
    """Decorator for registering a version metadata handler.

    The decorated callable accepts the newly created record and is supposed to
    stamp application specific columns on it - a creator taken from the request
    being the typical case. Keeping this a hook is what allows ``cone.sql`` to
    stay free of any principal source.
    """
    _version_metadata_handlers.append(ob)
    return ob


def apply_version_metadata(record):
    """Call all registered version metadata handlers for ``record``.
    """
    for handler in _version_metadata_handlers:
        handler(record)


###############################################################################
# Schema
###############################################################################

# Columns owned by the pattern. Everything else on a versioned record is a data
# column and gets carried over to the successor unless overwritten.
VERSION_COLUMNS = frozenset([
    'id',
    'object_id',
    'version_deleted',
    'version_created',
    'version_superseded'
])


def versioning_table_args(cls):
    """Return the indexes every versioned table needs.

    Classes defining their own ``__table_args__`` must include these, e.g.::

        @declared_attr
        def __table_args__(cls):
            return versioning_table_args(cls) + (Index(...),)

    The unique index is the important one: it turns a forgotten
    ``version_superseded`` update into an immediate constraint error instead of
    silent data garbage. Tombstone rows fall under it as well - there may only
    ever be one of them per object, too.

    Partial indexes exist in SQLite (>= 3.8) and PostgreSQL. Both dialect
    keywords are set; unknown ones are ignored.
    """
    tablename = cls.__tablename__
    unsuperseded = text('version_superseded IS NULL')
    return (
        # History of one object, and the point in time range check.
        Index(
            'ix_{}_object_id_version_created'.format(tablename),
            'object_id',
            'version_created'
        ),
        # Invariant I1.
        Index(
            'ix_{}_one_current'.format(tablename),
            'object_id',
            unique=True,
            sqlite_where=unsuperseded,
            postgresql_where=unsuperseded
        ),
    )


class VersionRegistryMixin:
    """Registry table for a versioned record class.

    ``object_id`` is not unique in the versioned table itself - there are
    several versions - and therefore cannot serve as a foreign key target. The
    registry provides one: an immutable table with ``object_id`` as primary
    key.

    Only classes referenced by their object identity need one. A pure leaf
    nobody points at can do without; its ``object_id`` is stable regardless.

    The registry row is written once, never changed, never deleted - not even
    on tombstone, because external foreign keys would break.

    Applications add their natural key as unique columns. It prevents two
    object identities for one and the same business object. Where there is no
    natural key, leave the registry without one; a unique constraint over
    nullable columns is no protection.

    ``created`` carries no ``version_`` prefix here: a registry row is the
    object identity itself and has no versions.
    """

    object_id = Column(GUID, primary_key=True)
    created = Column(UTCDateTime, nullable=False)


class VersionedMixin:
    """Append-only versioning for a record class.

    See the module docstring for the pattern. Mix in before the declarative
    base::

        class ThingRecord(VersionedMixin, SQLBase):
            __tablename__ = 'things'
            registry_class = ThingRegistryRecord

            title = Column(String)
    """

    # Registry providing the foreign key target for object references. ``None``
    # means nothing references this class by object identity.
    registry_class = None

    id = Column(GUID, primary_key=True, default=uuid.uuid4)
    version_deleted = Column(Boolean, nullable=False, default=False)
    version_created = Column(UTCDateTime, nullable=False)
    version_superseded = Column(UTCDateTime, nullable=True)

    @declared_attr
    def object_id(cls):
        # Declared late because the foreign key target is only known once the
        # concrete class states its registry. No ``index=True`` here - the
        # composite index from ``versioning_table_args`` has ``object_id`` as
        # its leftmost column and covers the lookups already.
        registry_class = cls.registry_class
        if registry_class is None:
            return Column(GUID, nullable=False)
        target = '{}.object_id'.format(registry_class.__tablename__)
        return Column(GUID, ForeignKey(target), nullable=False)

    @declared_attr
    def __table_args__(cls):
        return versioning_table_args(cls)

    ###########################################################################
    # Filters
    ###########################################################################

    @classmethod
    def current(cls):
        """Filter for the current state - the normal case.
        """
        return and_(
            cls.version_superseded.is_(None),
            cls.version_deleted.is_(False)
        )

    @classmethod
    def gone(cls):
        """Filter for objects that ceased to exist.
        """
        return and_(
            cls.version_superseded.is_(None),
            cls.version_deleted.is_(True)
        )

    @classmethod
    def as_of(cls, timestamp):
        """Filter for the state in effect at ``timestamp``.

        A range check, not a group by. With intact history (I1, I4) this yields
        exactly one row per object identity; more than one is an integrity
        error.

        ``timestamp`` must be timezone aware, like everything else the pattern
        compares against.
        """
        return and_(
            cls.version_created <= timestamp,
            cls.version_superseded.is_(None) |
            (cls.version_superseded > timestamp),
            cls.version_deleted.is_(False)
        )

    ###########################################################################
    # Queries
    ###########################################################################

    @classmethod
    def get_current(cls, session, object_id):
        """Return the youngest row for ``object_id``, live or gone.

        Returns the tombstone row for a gone object - the operations need to
        tell "does not exist" from "ceased to exist".
        """
        return session.query(cls).filter(
            cls.object_id == object_id,
            cls.version_superseded.is_(None)
        ).first()

    @classmethod
    def history(cls, session, object_id):
        """Return the full history of one object, oldest first.
        """
        return session.query(cls).filter(
            cls.object_id == object_id
        ).order_by(cls.version_created)

    ###########################################################################
    # The four operations
    ###########################################################################

    @classmethod
    def create(cls, session, object_id=None, registry_values=None, **data):
        """Create a new object and write its first version.
        """
        now = datetime.now(timezone.utc)
        if object_id is None:
            object_id = uuid.uuid4()
        registry_class = cls.registry_class
        if registry_class is not None:
            session.add(registry_class(
                object_id=object_id,
                created=now,
                **(registry_values or {})
            ))
            # The registry row is the foreign key target and has to exist
            # before the first version references it.
            session.flush()
        return cls._insert(session, object_id, now, False, data)

    @classmethod
    def new_version(cls, session, object_id, **data):
        """Supersede the current row and insert a successor.

        Data columns not passed are carried over, so a call site states only
        what actually changed. Versioning unchanged objects would grow the
        table without gaining information.
        """
        current = cls._resolve(session, object_id, deleted=False)
        now = cls._supersede(current)
        return cls._insert(session, object_id, now, False, data, current)

    @classmethod
    def tombstone(cls, session, object_id):
        """Record that the object ceased to exist.

        A new row, never an in place flag. Set in place, the current filter
        would claim the object had not existed at earlier points in time
        either - the deletion of today would reach backwards into the past.
        The grave row carries the last known state and is the youngest version,
        but not *current*.

        Dependent objects do not follow automatically. There is no
        ``ON DELETE CASCADE`` because nothing is deleted; the cascade is
        application logic and belongs in one function per aggregate.
        """
        current = cls._resolve(session, object_id, deleted=False)
        now = cls._supersede(current)
        return cls._insert(session, object_id, now, True, {}, current)

    @classmethod
    def resurrect(cls, session, object_id, **data):
        """Record that a gone object exists again.

        A tombstone is not a final state. The object identity is kept, so
        external references point at a live object again without any
        rematching - which is what the pattern exists for.
        """
        current = cls._resolve(session, object_id, deleted=True)
        now = cls._supersede(current)
        return cls._insert(session, object_id, now, False, data, current)

    ###########################################################################
    # Internals
    ###########################################################################

    @classmethod
    def _resolve(cls, session, object_id, deleted):
        """Return the current row, refusing the wrong lifecycle state.

        Resolving by ``object_id`` and ``version_superseded IS NULL`` is the
        first of the three guards: a historical row can never be superseded by
        accident, because it is never returned here.
        """
        current = cls.get_current(session, object_id)
        if current is None:
            raise UnknownObject('{}: {}'.format(cls.__name__, object_id))
        if current.version_deleted and not deleted:
            raise ObjectIsDeleted('{}: {}'.format(cls.__name__, object_id))
        if not current.version_deleted and deleted:
            raise ObjectIsNotDeleted('{}: {}'.format(cls.__name__, object_id))
        return current

    @classmethod
    def _supersede(cls, current):
        """Close the predecessor and return the timestamp both rows share.

        One timestamp for both writes, because I4 requires the predecessor to
        end exactly where the successor begins.
        """
        now = datetime.now(timezone.utc)
        current.version_superseded = now
        return now

    @classmethod
    def _insert(cls, session, object_id, now, deleted, data, predecessor=None):
        values = dict(data)
        if predecessor is not None:
            for name in cls.__table__.columns.keys():
                if name in VERSION_COLUMNS or name in values:
                    continue
                values[name] = getattr(predecessor, name)
        record = cls(
            id=uuid.uuid4(),
            object_id=object_id,
            version_created=now,
            version_deleted=deleted,
            **values
        )
        apply_version_metadata(record)
        session.add(record)
        return record


###############################################################################
# Mutation guard
###############################################################################

def _changed_columns(instance):
    """Return the names of data columns changed on ``instance``.
    """
    return [
        attr.key for attr in inspect(instance).attrs
        if attr.history.has_changes()
    ]


@event.listens_for(Session, 'before_flush')
def forbid_in_place_mutation(session, flush_context, instances):
    """Reject every write the pattern does not allow.

    This is what makes append-only enforceable rather than a convention. It
    inspects what changed, not who changed it, so it covers call sites that do
    not exist yet.

    Registered on ``Session`` globally, but only versioned classes are looked
    at - for everything else this is a type check per dirty instance.
    """
    for instance in session.dirty:
        if isinstance(instance, VersionRegistryMixin):
            changed = _changed_columns(instance)
            if changed:
                raise InPlaceMutation(
                    'Registry rows are immutable: {} {}'.format(
                        type(instance).__name__,
                        ', '.join(sorted(changed))
                    )
                )
            continue
        if not isinstance(instance, VersionedMixin):
            continue
        forbidden = [
            name for name in _changed_columns(instance)
            if name != 'version_superseded'
        ]
        if forbidden:
            raise InPlaceMutation(
                'Versioned rows are immutable, call one of create, '
                'new_version, tombstone or resurrect instead: {} {}'.format(
                    type(instance).__name__,
                    ', '.join(sorted(forbidden))
                )
            )
    for instance in session.deleted:
        if isinstance(instance, (VersionedMixin, VersionRegistryMixin)):
            raise InPlaceMutation(
                'Versioned rows are never deleted, use tombstone: {}'.format(
                    type(instance).__name__
                )
            )
