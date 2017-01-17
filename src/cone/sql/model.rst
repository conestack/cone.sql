cone.sql.model
==============

Imports::

    >>> from cone.app import get_root
    >>> from cone.sql import get_session
    >>> from cone.sql.model import SQLRowNode
    >>> from cone.sql.model import SQLTableNode
    >>> from cone.sql.testing import IntegerAsPrimaryKeyRecord
    >>> from cone.sql.testing import StringAsPrimaryKeyRecord
    >>> from cone.sql.testing import UUIDAsPrimaryKeyRecord
    >>> import cone.app
    >>> import uuid


UUID as key
-----------

Define an application node which represents the SQL row and uses the SQLAlchemy
model::

    >>> class UUIDAsKeyNode(SQLRowNode):
    ...     record_factory = UUIDAsPrimaryKeyRecord

Define an application node which represents the test table and acts as
container for the SQL row nodes::

    >>> class UUIDAsKeyContainer(SQLTableNode):
    ...     record_class = UUIDAsPrimaryKeyRecord
    ...     child_factory = UUIDAsKeyNode

Resgister application entry::

    >>> cone.app.register_plugin('uuid_as_key_container', UUIDAsKeyContainer)

Get container from root::

    >>> root = get_root()
    >>> container = root['uuid_as_key_container']
    >>> container
    <UUIDAsKeyContainer object 'uuid_as_key_container' at ...>

    >>> container.__parent__
    <AppRoot object 'None' at ...>

Add node to container::

    >>> node_uid = '6090411e-d249-4dc6-9da1-74172919f1ed'
    >>> node = container[node_uid] = UUIDAsKeyNode()
    >>> node.attrs['field'] = 'Value'

Persist data::

    >>> container()

Query data record using SQLAlchemy::

    >>> request = layer.new_request()
    >>> session = get_session(request)
    >>> session.query(UUIDAsPrimaryKeyRecord).get(uuid.UUID(node_uid))
    <cone.sql.testing.UUIDAsPrimaryKeyRecord object at ...>
