.. image:: https://img.shields.io/pypi/v/cone.sql.svg
    :target: https://pypi.python.org/pypi/cone.sql
    :alt: Latest PyPI version

.. image:: https://img.shields.io/pypi/dm/cone.sql.svg
    :target: https://pypi.python.org/pypi/cone.sql
    :alt: Number of PyPI downloads

.. image:: https://travis-ci.org/bluedynamics/cone.sql.svg?branch=master
    :target: https://travis-ci.org/bluedynamics/cone.sql

.. image:: https://coveralls.io/repos/github/bluedynamics/cone.sql/badge.svg?branch=master
    :target: https://coveralls.io/github/bluedynamics/cone.sql?branch=master


cone.sql
========

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

    cone.sql.db.url = sqlite:///%(here)s/var/sqlite/my_db.db

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


TODO
----

- Support multiple primary keys.


Test coverage
-------------

Summary of the test coverage report::

    Name                               Stmts   Miss  Cover
    ------------------------------------------------------
    src/cone/sql/__init__.py              50      0   100%
    src/cone/sql/acl.py                   62      0   100%
    src/cone/sql/model.py                162      0   100%
    src/cone/sql/testing.py               36      0   100%
    src/cone/sql/tests/__init__.py        18      0   100%
    src/cone/sql/tests/test_acl.py        86      0   100%
    src/cone/sql/tests/test_model.py     225      0   100%
    src/cone/sql/tests/test_sql.py        38      0   100%
    ------------------------------------------------------
    TOTAL                                677      0   100%


Contributors
============

- Robert Niederreiter (Author)

cone.sql.ugm
============

Overview
--------

``cone.sql.ugm`` is an implementation of the ``node.ext.ugm.interfaces`` contract, where
principals, users and groups are stored in sql tables:

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

Users and groups can be managed with ``cone.ugm``. See documentation
on the basic configuration of ugm.xml there.

Configuration
-------------

``cone.sql.ugm`` uses the same database as it is configured in ``cone.sql``.
It can be activated using the .ini file with the following minimal setup:

.. code-block:: ini
    ...
    ugm.backend = sql
    ugm.config = %(here)s/ugm.xml
    ...

where the content of ``ugm.xml`` will be preconfigured during first startup and
can be edited later, especially configuring the custom fields for users and
groups.

Additionally options:

.. code-block:: ini
    ugm.log_authentication = True
    ugm.user_attr_names = id, login, schas
    ugm.group_attr_names = groupname, maxmembers

- ``ugm.log_authentication`` (default: False)
   if set the first login timestamp will be set during the first authentication
   and last login timestamp will be updated for each successful authentication
- ``ugm.user_attr_names`` and ``ugm.group_attr_names``:
   if not already configured in ``ugm.xml`` these can be set in the .ini file
    using a comma-separed list of strings.

