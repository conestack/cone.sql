from cone.sql import get_session
from cone.sql import testing
from cone.sql.acl import PrincipalRoleRecord
from cone.sql.acl import SQLPrincipalACL
from cone.sql.acl import SQLPrincipalRoles
from node.base import BaseNode
from node.interfaces import IUUID
from node.tests import NodeTestCase
from plumber import plumbing
from pyramid.security import Allow
from zope.interface import implementer
import uuid as uuid_module


@plumbing(SQLPrincipalACL)
class InvalidSQLPrincipalACLNode(BaseNode):
    pass

    @property
    def __acl__(self):
        return []  # pragma nocover


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


class TestACL(NodeTestCase):
    layer = testing.sql_layer

    def test_SQLPrincipalACL(self):
        # Create request to ensure sql session available::
        request = self.layer.new_request()
        session = get_session(request)

        # Create invalid node and read ``principal_roles``
        node = InvalidSQLPrincipalACLNode()
        self.assertRaises(RuntimeError, lambda: node.principal_roles)

        # Create node and read ``principal_roles``
        node = SQLPrincipalACLNode()
        principal_roles = node.principal_roles

        self.assertTrue(isinstance(principal_roles, SQLPrincipalRoles))
        self.assertEqual(principal_roles.name, 'principal_roles')

        self.assertEqual([_ for _ in principal_roles], [])
        self.assertEqual(principal_roles._roles_for('someuser'), [])

        # check number of entries in table
        self.assertEqual(session.query(PrincipalRoleRecord).count(), 0)

        # check __acl__ on node
        self.assertEqual(node.__acl__, [
            ('Allow', 'role:editor', ['edit']),
            ('Allow', 'role:manager', ['manage'])
        ])

        # Set some local roles for node
        principal_roles['someuser'] = ['manager']
        principal_roles['otheruser'] = ['editor']
        principal_roles['group:some_group'] = ['editor', 'manager']

        # check number of entries in table
        self.assertEqual(session.query(PrincipalRoleRecord).count(), 4)

        # check principal roles via API
        self.assertEqual(
            sorted([_ for _ in principal_roles]),
            ['group:some_group', 'otheruser', 'someuser']
        )
        self.assertEqual(principal_roles['someuser'], ['manager'])
        self.assertEqual(
            sorted(principal_roles['group:some_group']),
            ['editor', 'manager']
        )

        # check __acl__ on node
        acl = node.__acl__
        self.assertEqual(len(acl), 5)
        self.assertEqual(acl[0][0], 'Allow')
        self.assertEqual(acl[0][1], 'someuser')
        self.assertEqual(acl[0][2], ['manage'])

        self.assertEqual(acl[1][0], 'Allow')
        self.assertEqual(acl[1][1], 'otheruser')
        self.assertEqual(acl[1][2], ['edit'])

        self.assertEqual(acl[2][0], 'Allow')
        self.assertEqual(acl[2][1], 'group:some_group')
        self.assertEqual(sorted(acl[2][2]), ['edit', 'manage'])

        self.assertEqual(acl[3][0], 'Allow')
        self.assertEqual(acl[3][1], 'role:editor')
        self.assertEqual(acl[3][2], ['edit'])

        self.assertEqual(acl[4][0], 'Allow')
        self.assertEqual(acl[4][1], 'role:manager')
        self.assertEqual(acl[4][2], ['manage'])

        # Modify some local roles
        principal_roles['group:some_group'] = ['viewer', 'admin', 'manager']

        # check number of entries in table
        self.assertEqual(session.query(PrincipalRoleRecord).count(), 5)

        # check principal roles via API
        self.assertEqual(
            sorted(principal_roles['group:some_group']),
            ['admin', 'manager', 'viewer']
        )
        self.assertEqual(
            sorted(principal_roles.keys()),
            ['group:some_group', 'otheruser', 'someuser']
        )
        self.assertEqual(
            sorted(principal_roles['group:some_group']),
            ['admin', 'manager', 'viewer']
        )
        self.assertEqual(principal_roles['otheruser'], ['editor'])
        self.assertEqual(principal_roles['someuser'], ['manager'])

        # Create another node and set some local roles for it
        node = SQLPrincipalACLNode()
        node.uuid = uuid_module.UUID('67140d49-6a4d-4d72-9171-ad764131c880')
        principal_roles = node.principal_roles
        principal_roles['otheruser'] = ['editor', 'admin']
        principal_roles['group:some_group'] = ['editor', 'manager']

        # check number of entries in table
        self.assertEqual(session.query(PrincipalRoleRecord).count(), 9)

        # check principal roles via API
        self.assertEqual(
            sorted(principal_roles.keys()),
            ['group:some_group', 'otheruser']
        )
        self.assertEqual(
            sorted(principal_roles['group:some_group']),
            ['editor', 'manager']
        )
        self.assertEqual(
            sorted(principal_roles['otheruser']),
            ['admin', 'editor']
        )

        # Delete local roles
        del principal_roles['group:some_group']
        self.assertEqual(principal_roles.keys(), ['otheruser'])

        # check number of entries in table
        self.assertEqual(session.query(PrincipalRoleRecord).count(), 7)

        # check principal roles via API
        self.assertEqual(
            sorted(principal_roles['otheruser']),
            ['admin', 'editor']
        )

        # Check if local roles of first node still sane
        node = SQLPrincipalACLNode()
        principal_roles = node.principal_roles
        self.assertEqual(
            sorted(principal_roles.keys()),
            ['group:some_group', 'otheruser', 'someuser']
        )
        self.assertEqual(
            sorted(principal_roles['group:some_group']),
            ['admin', 'manager', 'viewer']
        )
        self.assertEqual(principal_roles['otheruser'], ['editor'])
        self.assertEqual(principal_roles['someuser'], ['manager'])
