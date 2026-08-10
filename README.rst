.. image:: https://img.shields.io/pypi/v/cone.sql.svg
    :target: https://pypi.python.org/pypi/cone.sql
    :alt: Latest PyPI version

.. image:: https://img.shields.io/pypi/dm/cone.sql.svg
    :target: https://pypi.python.org/pypi/cone.sql
    :alt: Number of PyPI downloads

.. image:: https://github.com/conestack/cone.sql/actions/workflows/test.yml/badge.svg
    :target: https://github.com/conestack/cone.sql/actions/workflows/test.yml
    :alt: Test cone.sql

This package provides SQLAlchemy integration in ``cone.app`` and basic
application nodes for publishing SQLAlchemy models.


Installation
------------

Include ``cone.sql`` to install dependencies in your application's
``setup.py``.


Configure Database and WSGI
---------------------------

Adopt your application config ini file to define database location and hook
up the related elements to the WSGI pipeline.

.. code-block:: ini

    [app:my_app]
    use = egg:cone.app#main

    pyramid.includes =
        pyramid_retry
        pyramid_tm

    tm.commit_veto = pyramid_tm.default_commit_veto

    cone.plugins =
        cone.sql

    sql.db.url = sqlite:///%(here)s/var/sqlite/my_db.db

    [filter:remote_addr]
    # for use behind nginx
    use = egg:cone.app#remote_addr

    [filter:session]
    use = egg:cone.sql#session

    [pipeline:main]
    pipeline =
        remote_addr
        session
        my_app


Create Model and Nodes
----------------------

Define the SQLAlchemy model.

.. code-block:: python

    from cone.sql import SQLBase
    from cone.sql.model import GUID
    from sqlalchemy import Column
    from sqlalchemy import String

    class MyRecord(SQLBase):
        __tablename__ = 'my_table'
        uid_key = Column(GUID, primary_key=True)
        field = Column(String)

Define an application node which represents the SQL row and uses the SQLAlchemy
model. The class holds a reference to the related SQLAlchemy model.

.. code-block:: python

    from cone.sql.model import SQLRowNode

    class MyNode(SQLRowNode):
        record_class = MyRecord

Define an application node which represents the table and acts as container for
the SQL row nodes. The class holds a reference to the related SQLAlchemy model
and the related SQLRowNode.

.. code-block:: python

    from cone.sql.model import SQLTableNode

    class MyContainer(SQLTableNode):
        record_class = MyRecord
        child_factory = MyNode


Append-only versioning
----------------------

``cone.sql.versioning`` provides revision safe storage as an opt-in mixin.
Nothing is ever updated or deleted: a change inserts a new row and marks the
previous one superseded, a deletion inserts a grave row. ``SQLBase`` and
existing tables are untouched.

.. code-block:: python

    from cone.sql import SQLBase
    from cone.sql.versioning import VersionedMixin
    from cone.sql.versioning import VersionRegistryMixin
    from sqlalchemy import Column
    from sqlalchemy import String

    class MyRegistryRecord(VersionRegistryMixin, SQLBase):
        __tablename__ = 'my_registry'
        code = Column(String, unique=True)

    class MyRecord(VersionedMixin, SQLBase):
        __tablename__ = 'my_table'
        registry_class = MyRegistryRecord
        field = Column(String)

The mixin contributes ``id`` (row identity), ``object_id`` (object identity,
stable across versions), ``deleted``, ``created`` and ``superseded``, plus
a partial unique index enforcing at most one current version per object.

The registry is an immutable table with ``object_id`` as primary key. It exists
because ``object_id`` is not unique in the versioned table and therefore cannot
serve as a foreign key target. Classes nobody references by object identity can
omit it.

Four operations are the only write path:

.. code-block:: python

    record = MyRecord.create(session, registry_values=dict(code='a'), field='x')
    record = MyRecord.new_version(session, record.object_id, field='y')
    record = MyRecord.tombstone(session, record.object_id)
    record = MyRecord.resurrect(session, record.object_id, field='z')

Data columns not passed to ``new_version`` are carried over from the
predecessor. Queries use the filters, never a hand written condition:

.. code-block:: python

    session.query(MyRecord).filter(MyRecord.current())
    session.query(MyRecord).filter(MyRecord.as_of(timestamp))
    session.query(MyRecord).filter(MyRecord.gone())
    MyRecord.history(session, object_id)

A ``before_flush`` guard rejects any UPDATE touching anything but
``superseded`` and any DELETE on versioned rows, which makes the pattern
enforceable rather than a convention.

Two things the application owns: SQLite needs ``PRAGMA foreign_keys=ON`` for the
registry foreign key to be more than declarative, and application specific
columns such as a creator are stamped by handlers registered with
``version_metadata_handler``.

For publishing versioned records there are node classes mirroring
``SQLTableNode`` and ``SQLRowNode``:

.. code-block:: python

    from cone.sql.versioning import VersionedSQLRowNode
    from cone.sql.versioning import VersionedSQLTableNode

    class MyNode(VersionedSQLRowNode):
        record_class = MyRecord

    class MyContainer(VersionedSQLTableNode):
        record_class = MyRecord
        child_factory = MyNode

The node name is the **object identity**, not the primary key. A name bound to
the primary key would change on every edit and take every URL and every stored
reference with it, which is the opposite of what the pattern exists for.

Usage follows the same contract as the non versioned nodes:

.. code-block:: python

    node = MyNode()
    node.attrs['field'] = 'value'
    container[str(object_id)] = node
    node()

Attribute writes are buffered and turned into a version when the node is
called - creating the first one, or superseding the current one. Calling a node
without pending changes writes nothing. ``__delitem__`` writes a tombstone
instead of deleting, and the container lists and resolves current rows only.
Cascading over dependent objects stays application logic, since only the
application knows the aggregate.


Primary key handling
--------------------

The node name maps to the primary key of the SQLAlchemy model (currenly no
multiple primary keys are supported). Node names are converted to the
primary key data type automatically. The conversion factories are defined at
``SQLTableNode.data_type_converters`` which can be extended by more data types
if needed.

.. code-block:: python

    >>> SQLTableNode.data_type_converters
    {<class 'sqlalchemy.sql.sqltypes.String'>: <type 'unicode'>,
    <class 'cone.sql.model.GUID'>: <class 'uuid.UUID'>,
    <class 'sqlalchemy.sql.sqltypes.Integer'>: <type 'int'>}


Integrate to the Application Model
----------------------------------

In order to publish a SQL table node, the table node must be hooked up to the
application model. To hook up the at root level, register it as entry.

.. code-block:: python

    import cone.app

    cone.app.register_entry('container', MyContainer)


Session setup handlers
----------------------

There exists a ``sql_session_setup`` decorator which can be used to perform
session setup tasks like registering SQLAlchemy event listeners.

.. code-block:: python

    from cone.sql import sql_session_setup
    from sqlalchemy import event

    def after_flush(session, flush_context):
        """Do something after flush.
        """

    @sql_session_setup
    def bind_session_listener(session):
        """SQL session setup callback.
        """
        event.listen(session, 'after_flush', after_flush)


Query the database
------------------

Querying the database is done via SQLAlchemy. If you are in a request/response
cycle, you should acquire the session from request via ``get_session`` and
perform arbitrary operations on it. By reading the session from request we ensure
the transaction manager to work properly if configured.

.. code-block:: python

    from cone.sql import get_session

    session = get_session(request)
    result = session.query(MyRecord).all()

If you need a session outside a request/response cycle you can create one by using
the ``session_factory``.

.. code-block:: python

    from cone.sql import session_factory

    session = session_factory()
    result = session.query(MyRecord).all()
    session.close()


Principal ACL's
---------------

SQL based Principal ACL's are implemented in ``cone.sql.acl``. The related
table gets created as soon as you import from this module.

Using ``SQLPrincipalACL`` requires the model to implement ``node.interfaces.IUUID``.

.. code-block:: python

    from cone.sql.acl import SQLPrincipalACL
    from node.base import BaseNode
    from node.interfaces import IUUID
    from plumber import plumbing
    from pyramid.security import Allow
    from zope.interface import implementer
    import uuid as uuid_module

    @implementer(IUUID)
    @plumbing(SQLPrincipalACL)
    class SQLPrincipalACLNode(BaseNode):
        uuid = uuid_module.UUID('1a82fa87-08d6-4e48-8bc2-97ee5a52726d')

        @property
        def __acl__(self):
            return [
                (Allow, 'role:editor', ['edit']),
                (Allow, 'role:manager', ['manage']),
            ]


User and Group Management
-------------------------

``cone.sql.ugm`` contains an implementation of the UGM contracts defined at
``node.ext.ugm.interfaces``, using sql as backend storage:

.. code-block::

                           +------------+
                           |  Principal |
                           |(data: JSON)|
                           +------------+
                                 ^
                                 |
            +-----------------------------------------+
            |                                         |
            |                                         |
         +------+                                 +-------+
         | User |                                 | Group |
         +------+                                 +-------+
             1                                        1
             |                                        |
             |                                        |
             +-------------+            +-------------+
                           |            |
                           n            m
                           |            |
                        +-----------------+
                        | GroupAssignment |
                        +-----------------+

Currently SQLite and PostgreSQL are supported and tested, other DBs must
be evaluated concerning their JSON capabilities since users and groups
store additional payload data in a JSON field which brings the flexibility
to store arbitrary data as a dict in the JSON field.

To activate SQL based UGM backend, it needs to be configured via the application
ini config file.:

.. code-block:: ini

    ugm.backend = sql

    sql.user_attrs = id, mail, fullname, portrait
    sql.group_attrs = description
    sql.binary_attrs = portrait
    sql.log_auth = True
    sql.user_expires_attr = expires

UGM users and groups are stored in the same database as defined at
``sql.db.url`` in the config file.

UGM dedicated config options:

- ``sql.user_attrs`` is a comma separated list of strings defining the
  available user attributes stored in the user JSON data field.

- ``sql.group_attrs`` is a comma separated list of strings defining the
  available group attributes stored in the group JSON data field.

- ``sql.binary_attrs`` is a comma separated list of strings defining the
  attributes which are considered binary and get stored base 64 encoded in the
  JSON data field of users and groups.

- ``sql.log_auth`` defaults to False. If set, the first login timestamp will
  be stored during the first authentication and latest login timestamp will be
  updated for each successful authentication.

- ``sql.user_expires_attr`` defaults to None. If set, user expiration is
  enabled and the value given is the attribute name of the JSON data field
  where the expiration timestamp gets stored.

Users and groups can be managed with ``cone.ugm``. If activated,
``sql.user_attrs`` and ``sql.group_attrs`` can be omitted, relevant information
gets extracted from the ``ugm.xml`` config file.

.. code-block:: ini

    ugm.backend = sql
    ugm.config = %(here)s/ugm.xml

    sql.log_auth = True

    cone.plugins =
        cone.ugm
        cone.sql


TODO
----

- Support multiple primary keys.


Contributors
============

- Robert Niederreiter (Author)
- Phil Auersperg
