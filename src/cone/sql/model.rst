cone.sql.model
==============

Prepare environment::

    >>> from cone.app import get_root
    >>> from cone.sql import SQLBase
    >>> from cone.sql import get_session
    >>> from cone.sql.model import GUID
    >>> from cone.sql.model import SQLRowNode
    >>> from cone.sql.model import SQLTableNode
    >>> from sqlalchemy import Column
    >>> from sqlalchemy import String
    >>> import cone.app

    >>> class TestRecord(SQLBase):
    ...     __tablename__ = 'test'
    ...     uid = Column(GUID, primary_key=True)
    ...     field = Column(String)

    >>> class TestNode(SQLRowNode):
    ...     record_factory = TestRecord

    >>> class TestContainer(SQLTableNode):
    ...     record_class = TestRecord
    ...     child_factory = TestNode

    >>> cone.app.register_plugin('container', TestContainer)
    >>> root = get_root()
    >>> container = root['container']
    >>> container
    <TestContainer object 'container' at ...>

    >>> container.__parent__
    <AppRoot object 'None' at ...>

    >>> def record_by_uid(request, uid):
    ...     session = get_session(request)
    ...     return session.query(TestRecord).get(uid)
