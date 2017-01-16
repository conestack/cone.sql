cone.sql.model
==============

Imports::

    >>> from cone.app import get_root
    >>> from cone.sql import get_session
    >>> from cone.sql.model import SQLRowNode
    >>> from cone.sql.model import SQLTableNode
    >>> from cone.sql.testing import TestRecord
    >>> import cone.app
    >>> import uuid

Define an application node which represents the SQL row and uses the SQLAlchemy
model::

    >>> class TestNode(SQLRowNode):
    ...     record_factory = TestRecord

Define an application node which represents the test table and acts as
container for the SQL row nodes::

    >>> class TestContainer(SQLTableNode):
    ...     record_class = TestRecord
    ...     child_factory = TestNode

Resgister application entry::

    >>> cone.app.register_plugin('container', TestContainer)

Get container from root::

    >>> root = get_root()
    >>> container = root['container']
    >>> container
    <TestContainer object 'container' at ...>

    >>> container.__parent__
    <AppRoot object 'None' at ...>

Add node to container::

    >>> node_uid = '6090411e-d249-4dc6-9da1-74172919f1ed'
    >>> node = container[node_uid] = TestNode()
    >>> node.attrs['field'] = 'Value'

Persist data::

    >>> container()

Query data record using SQLAlchemy::

    >>> request = layer.new_request()
    >>> session = get_session(request)
    >>> session.query(TestRecord).get(uuid.UUID(node_uid))
    <cone.sql.testing.TestRecord object at ...>
