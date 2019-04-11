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

    tm.commit_veto = pyramid_tm.default_commit_veto

    cone.plugins =
        cone.sql

    cone.sql.dbinit.url = sqlite:///%(here)s/var/sqlite/my_db.db

    [filter:remote_addr]
    # for use behind nginx
    use = egg:cone.app#remote_addr

    [filter:session]
    use = egg:cone.sql#session
    sqlalchemy.url = sqlite:///%(here)s/var/sqlite/my_db.db

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

Querying the database is done via SQLAlchemy. You can acquire the session from
request via ``get_session`` and perform arbitrary operations on it.

.. code-block:: python

    from cone.sql import get_session

    session = get_session(request)
    result = session.query(MyRecord).all()


TODO
----

- Support multiple primary keys.


Test coverage
-------------

Summary of the test coverage report::

    lines   cov%   module
       50   100%   cone.sql.__init__
      186    99%   cone.sql.model
       57   100%   cone.sql.testing
       18   100%   cone.sql.tests


Contributors
============

- Robert Niederreiter (Author)
