from cone.sql import testing
from cone.sql.ugm import AuthenticationBehavior
from cone.sql.ugm import Base
from cone.sql.ugm import Group
from cone.sql.ugm import PrincipalsBehavior
from cone.sql.ugm import SQLGroup
from cone.sql.ugm import SQLGroupAssignment
from cone.sql.ugm import SQLPrincipal
from cone.sql.ugm import SQLUser
from cone.sql.ugm import Ugm
from cone.sql.ugm import User
from datetime import datetime
from datetime import timedelta
from node.base import BaseNode
from node.tests import NodeTestCase
from plumber import plumbing
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified
import os
import shutil
import tempfile
import unittest


def temp_database(fn):
    def wrapper(self):
        tempdir = tempfile.mkdtemp()
        uri = f'sqlite:///{tempdir}/test.db'
        engine = create_engine(uri)
        Base.metadata.create_all(engine)
        sm = sessionmaker(bind=engine)
        session = sm()
        try:
            fn(self, session)
        finally:
            shutil.rmtree(tempdir)
    return wrapper


class TestSqlModel(unittest.TestCase):

    @temp_database
    def test_sql_model(self, session):
        for name in ['phil', 'donald', 'dagobert', 'daisy']:
            session.add(SQLUser(id=name))
        session.flush()

        users = session.query(SQLUser).all()
        self.assertEqual(
            sorted([u.id for u in users]),
            ['dagobert', 'daisy', 'donald', 'phil']
        )

        for group in ['admins', 'members', 'editors', 'phil']:
            session.add(SQLGroup(id=group))
        session.flush()

        phil = session.query(SQLUser).filter(SQLUser.id == 'phil').one()
        donald = session.query(SQLUser).filter(SQLUser.id == 'donald').one()
        admins = session.query(SQLGroup).filter(SQLGroup.id == 'admins').one()
        members = session.query(SQLGroup).filter(SQLGroup.id == 'members').one()

        phil.principal_roles = ['manager', 'member']
        phil.groups.append(admins)
        phil.groups.append(members)

        donald.groups.append(members)

        session.flush()

        phil1 = session.query(SQLUser).filter(SQLUser.id == 'phil').one()
        self.assertEqual(sorted(phil1.principal_roles), ['manager', 'member'])
        self.assertTrue(admins in phil1.groups)
        self.assertTrue(members in phil1.groups)

        members = session.query(SQLGroup).filter(SQLGroup.id == 'members').one()
        phil_group = session.query(SQLGroup).filter(SQLGroup.id == 'phil').one()
        phil_group.frunz = 42

        self.assertEqual(phil_group.id, phil.id)
        self.assertNotEqual(phil_group.guid, phil.guid)

        self.assertTrue(phil in members.users)
        self.assertTrue(donald in members.users)

        phil_group.users.append(phil)
        self.assertTrue(phil_group in phil.groups)

        session.commit()


class TestSqlUgm(NodeTestCase):
    layer = testing.sql_layer

    @testing.delete_table_records(SQLPrincipal)
    @testing.delete_table_records(SQLGroup)
    @testing.delete_table_records(SQLGroupAssignment)
    @testing.delete_table_records(SQLUser)
    def test_ugm(self):
        os.environ['CONE_SQL_USE_TM'] = '0'
        self.layer.new_request()

        ugm = Ugm(
            name='sql_ugm',
            parent=None,
            user_attrs=['phone', 'address'],
            group_attrs=['description'],
            binary_attrs=[],
            log_auth=True,
            user_expires_attr=None
        )
        users = ugm.users
        groups = ugm.groups

        self.assertTrue(users.ugm is ugm)
        self.assertTrue(groups.ugm is ugm)

        # create some users with attribute
        ids = ['phil', 'donald', 'dagobert', 'mickey']
        for count, id in enumerate(ids):
            users.create(
                id,
                height=count + 1,
                email='%s@conestack.org' % id,
                status='super%s' % (count + 1)
            )

        self.assertTrue('phil' in users)
        self.assertFalse('zworkb' in users)

        # give phil a password
        self.assertEqual(users['phil'].record.password, None)
        users.set_hashed_pw('phil', users.hash_passwd('test123'))
        self.assertNotEqual(users['phil'].record.password, None)

        self.assertEqual(users['donald'].record.password, None)
        users['donald'].passwd(None, 'test123')
        self.assertNotEqual(users['donald'].record.password, None)

        self.assertEqual(users['dagobert'].record.password, None)
        users.passwd('dagobert', None, 'test124')
        self.assertNotEqual(users['dagobert'].record.password, None)

        self.assertFalse(users.authenticate('zworkb', 'test123'))
        self.assertFalse(users.authenticate(None, "foo"))
        self.assertFalse(users.authenticate("foo", None))
        self.assertFalse(users.authenticate(None, None))

        self.assertTrue(users['phil'].authenticate('test123'))
        self.assertTrue(users.authenticate('phil', 'test123'))
        self.assertTrue(users.authenticate('donald', 'test123'))
        self.assertTrue(users.authenticate('dagobert', 'test124'))

        # check user attributes
        self.assertEqual(users['phil'].record.data['height'], 1)
        self.assertEqual(users['donald'].record.data['height'], 2)
        self.assertEqual(users['phil'].record.data['status'], 'super1')
        self.assertEqual(users['donald'].record.data['status'], 'super2')

        # check __iter__
        ids1 = list(users)
        self.assertEqual(sorted(ids), sorted(ids1))

        # check login attribute (lets take email)
        # schlumpf and schlumpfine with 2 different login fields
        users.create('schlumpf', email='schlumpf@conestack.org', login='email')
        users.create('schlumpfine', nickname='schlumpfinchen', login='nickname')

        schlumpfid = users.id_for_login('schlumpf@conestack.org')
        self.assertEqual(schlumpfid, 'schlumpf')

        schlumpfineid = users.id_for_login('schlumpfinchen')
        self.assertEqual(schlumpfineid, 'schlumpfine')

        users.session.commit()

        # Test groups
        managers = groups.create('managers', title='Masters of the Universe')
        members = groups.create('members', title='the normal ones')
        managers1 = groups['managers']

        self.assertEqual(
            managers1.record.data['title'],
            'Masters of the Universe'
        )
        self.assertTrue(groups.ugm is ugm)

        managers.add('phil')

        for id in ids:
            members.add(id)

        users.session.commit()

        self.assertEqual(set(ids), set(list(members)))
        self.assertEqual(sorted(members.member_ids), sorted(ids))
        self.assertEqual(managers.member_ids, ['phil'])

        phil2 = managers['phil']
        self.assertIsInstance(phil2, User)

        # non group members should raise a KeyError
        self.assertRaises(KeyError, managers.__getitem__, 'donald')

        # Test roles

        # roles for a user
        users['phil'].add_role('Editor')
        users['phil'].add_role('Spam')
        self.assertEqual(sorted(users['phil'].roles), ['Editor', 'Spam'])

        users['phil'].remove_role('Spam')
        self.assertEqual(users['phil'].roles, ['Editor'])

        users.session.commit()

        # removing non-existing roles is tolerated
        users['phil'].remove_role('Spam')

        # roles for group
        groups['managers'].add_role('Manager')
        self.assertEqual(groups['managers'].roles, ['Manager'])

        groups['members'].add_role('Member')
        self.assertEqual(groups['members'].roles, ['Member'])

        # cumulative roles for the user -> user has all roles by his groups
        self.assertEqual(
            sorted(users['phil'].roles),
            ['Editor', 'Manager', 'Member']
        )

        # get group instances of a user
        self.assertEqual(len(users['phil'].groups), 2)
        for g in users['phil'].groups:
            self.assertIsInstance(g, Group)

        # group_ids shall match group instances
        self.assertEqual(
            set(users['phil'].group_ids),
            set([g.id for g in users['phil'].groups])
        )

        # delete a group membership
        del managers['phil']
        users.session.commit()  # needs commit, flush() is not sufficient

        self.assertTrue(users['phil'] not in managers.users)  # needs refresh
        self.assertTrue(users['phil'] not in groups['managers'].users)
        self.assertTrue('phil' not in managers.member_ids)
        self.assertTrue('managers' not in users['phil'].group_ids)
        self.assertTrue(groups['managers'] not in users['phil'].groups)

        # ugm-level role management
        ugm.add_role('Snuff', users['phil'])
        self.assertTrue('Snuff' in users['phil'].roles)

        ugm.add_role('Smurf', groups['managers'])
        self.assertTrue('Smurf' in groups['managers'].roles)

        ugm.remove_role('Snuff', users['phil'])
        self.assertFalse('Snuff' in users['phil'].roles)

        ugm.remove_role('Smurf', groups['managers'])
        self.assertFalse('Smurf' in groups['managers'].roles)

        # searching

        # search by int
        r1 = users.search(criteria=dict(height=1))
        self.assertEqual(len(r1), 1)
        self.assertEqual(r1[0], 'phil')

        # search by string
        r2 = users.search(criteria=dict(status='super1'))
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0], 'phil')

        # search with or
        r3 = users.search(
            criteria=dict(
                status='super1',
                height=2
            ),
            or_search=True
        )
        self.assertEqual(len(r3), 2)
        self.assertEqual(set(r3), set(('phil', 'donald',)))

        # search with wildcards in dynamic fields
        r4 = users.search(criteria=dict(status='super*'), exact_match=False)
        self.assertEqual(len(r4), 4)
        self.assertEqual(set(r4), set(('phil', 'donald', 'dagobert', 'mickey')))

        r5 = users.search(criteria=dict(id='d*'), exact_match=False)
        self.assertEqual(len(r5), 2)
        self.assertEqual(set(r5), set(('donald', 'dagobert')))

        # blank search should return all entries
        r6 = users.search()
        self.assertEqual(len(r6), 6)  # simply all of them

        # search for login field
        r7 = users.search(criteria=dict(login='nickname'))
        self.assertEqual(set(r7), {'schlumpfine'})

        # search with attrlist
        r8 = users.search(attrlist=['login', 'height', 'status'])
        self.assertEqual(sorted(r8), sorted([
            ('donald', {'height': 2, 'login': None, 'status': 'super2'}),
            ('dagobert', {'height': 3, 'login': None, 'status': 'super3'}),
            ('mickey', {'height': 4, 'login': None, 'status': 'super4'}),
            ('schlumpf', {'height': None, 'login': 'email', 'status': None}),
            ('schlumpfine', {'height': None, 'login': 'nickname', 'status': None}),
            ('phil', {'height': 1, 'login': None, 'status': 'super1'})])
        )

        r9 = users.search(attrlist=[])
        self.assertEqual(sorted(r9), sorted([
            ('donald', {
                'email': 'donald@conestack.org',
                'height': 2,
                'login': None,
                'status': 'super2'
            }), ('dagobert', {
                'email': 'dagobert@conestack.org',
                'height': 3,
                'login': None,
                'status': 'super3'
            }), ('mickey', {
                'email': 'mickey@conestack.org',
                'height': 4,
                'login': None,
                'status': 'super4'
            }), ('schlumpf', {
                'email': 'schlumpf@conestack.org',
                'login': 'email'
            }), ('schlumpfine', {
                'login': 'nickname',
                'nickname': 'schlumpfinchen'
            }), ('phil', {
                'email': 'phil@conestack.org',
                'height': 1,
                'login': None,
                'status': 'super1'
            })
        ]))

        # Exact searches with empty result shall throw up
        self.assertRaises(ValueError, lambda: users.search(
            exact_match=True,
            criteria=dict(
                id='unobtainable'
            )
        ))

        r10 = users.search(
            exact_match=False,
            criteria=dict(
                id='unobtainable'
            )
        )
        self.assertEqual(list(r10), [])

        r11 = users.search(
            exact_match=False,
            criteria=dict(
                id='unobtainable'
            ),
            or_search=True
        )
        self.assertEqual(list(r11), [])

        # shall work with groups too
        gids = groups.search(criteria=dict(title='Masters*'))
        self.assertEqual(gids, ['managers'])

        self.assertEqual(len(groups.keys()), 2)
        gids = groups.search(criteria=dict(id='*foo*'), or_search=True)
        self.assertEqual(len(gids), 0)

        del os.environ['CONE_SQL_USE_TM']

        # change fields of a user
        ugm.session.commit()

        donald = users['donald']
        donald.record.login = 'mail'
        donald.record.data['mail'] = 'donald@duck.com'

        flag_modified(donald.record, 'data')
        ugm.session.commit()

        donald1 = users['donald']
        self.assertEqual(donald1.record.login, 'mail')
        self.assertEqual(donald1.record.data['mail'], 'donald@duck.com')

        # Test expires
        user = ugm.users['donald']
        self.assertTrue(users.authenticate('donald', 'test123'))
        self.assertFalse(user.expired)
        self.assertEqual(user.expires, None)
        user.expires = datetime.now()
        self.assertEqual(user.expires, None)

        ugm.user_expires_attr = 'expires'
        self.assertFalse(user.expired)
        with self.assertRaises(ValueError):
            user.expires = 'expires'

        user.expires = None
        self.assertEqual(user.attrs['expires'], None)
        self.assertFalse(user.expired)

        user.expires = datetime.now() + timedelta(1)
        self.assertFalse(user.expired)
        self.assertTrue(user.authenticate('test123'))
        self.assertTrue(ugm.users.authenticate('donald', 'test123'))

        user.expires = datetime.now()
        self.assertTrue(user.expired)
        self.assertFalse(user.authenticate('test123'))
        self.assertFalse(ugm.users.authenticate('donald', 'test123'))

        ugm.session.commit()
        donald = ugm.session.query(SQLUser)\
            .filter(SQLUser.id == 'donald')\
            .one()
        self.assertTrue('expires' in donald.data)
        self.assertEqual(
            sorted(users['donald'].attrs.keys()),
            ['address', 'phone']
        )


def create_ugm(user_attrs=None, group_attrs=None, binary_attrs=None):
    return Ugm(
        name='sql_ugm',
        parent=None,
        user_attrs=user_attrs or [],
        group_attrs=group_attrs or [],
        binary_attrs=binary_attrs or [],
        log_auth=False,
        user_expires_attr=None
    )


class TestSqlUgmDetails(NodeTestCase):
    layer = testing.sql_layer

    def setUp(self):
        self.layer.new_request()

    @testing.delete_table_records(SQLPrincipal)
    @testing.delete_table_records(SQLUser)
    def test_schema_attribute_is_written_to_record_column(self):
        ugm = create_ugm()
        user = ugm.users.create('phil')
        user.attrs['login'] = 'phil@example.com'
        self.assertEqual(user.record.login, 'phil@example.com')
        self.assertFalse('login' in user.record.data)

    @testing.delete_table_records(SQLPrincipal)
    @testing.delete_table_records(SQLUser)
    def test_attributes_without_configured_attrs_are_inspected(self):
        ugm = create_ugm()
        user = ugm.users.create('phil', email='phil@example.com')
        keys = list(user.attrs.keys())
        self.assertTrue('login' in keys)
        self.assertTrue('email' in keys)
        self.assertFalse('password' in keys)

    @testing.delete_table_records(SQLPrincipal)
    @testing.delete_table_records(SQLGroup)
    def test_group_attributes_are_configured_group_attrs(self):
        ugm = create_ugm(group_attrs=['description'])
        group = ugm.groups.create('admins', description='Admins')
        self.assertEqual(list(group.attrs.keys()), ['description'])

    @testing.delete_table_records(SQLPrincipal)
    @testing.delete_table_records(SQLGroup)
    @testing.delete_table_records(SQLUser)
    def test_binary_attrs_are_stored_base64_encoded(self):
        ugm = create_ugm(binary_attrs=['portrait'])
        user = ugm.users.create('phil', portrait=b'\x89PNG')
        self.assertEqual(user.record.data['portrait'], 'iVBORw==')
        self.assertEqual(
            ugm.users.search(criteria={'id': 'phil'}, attrlist=['portrait']),
            [('phil', {'portrait': b'\x89PNG'})]
        )
        group = ugm.groups.create('admins', portrait=b'\x89PNG')
        self.assertEqual(group.record.data['portrait'], 'iVBORw==')

    @testing.delete_table_records(SQLPrincipal)
    @testing.delete_table_records(SQLUser)
    def test_search_exact_match_on_data_attribute(self):
        ugm = create_ugm()
        ugm.users.create('phil', email='phil@example.com')
        ugm.users.create('donald', email='phil@example.com.au')
        self.assertEqual(
            ugm.users.search(
                criteria={'email': 'phil@example.com'},
                exact_match=True
            ),
            ['phil']
        )

    @testing.delete_table_records(SQLPrincipal)
    @testing.delete_table_records(SQLUser)
    def test_passwd_fails_for_unknown_user_and_wrong_old_password(self):
        ugm = create_ugm()
        users = ugm.users
        users.create('phil')
        users.passwd('phil', None, 'secret')
        with self.assertRaises(ValueError) as arc:
            users.passwd('donald', None, 'secret')
        self.assertEqual(
            str(arc.exception),
            "User with id 'donald' does not exist."
        )
        with self.assertRaises(ValueError) as arc:
            users.passwd('phil', 'wrong', 'new')
        self.assertEqual(str(arc.exception), 'Old password does not match.')
        self.assertTrue(users.authenticate('phil', 'secret'))

    def test_principals_are_added_by_create_only(self):
        ugm = create_ugm()
        with self.assertRaises(NotImplementedError) as arc:
            ugm.users['phil'] = BaseNode()
        self.assertEqual(
            str(arc.exception),
            'users can only be added using the create() method'
        )
        with self.assertRaises(NotImplementedError) as arc:
            ugm.groups['admins'] = BaseNode()
        self.assertEqual(
            str(arc.exception),
            'groups can only be added using the create() method'
        )

    def test_abstract_behavior_methods_must_be_implemented(self):
        @plumbing(PrincipalsBehavior)
        class Principals:
            pass

        @plumbing(AuthenticationBehavior)
        class Authentication:
            pass

        with self.assertRaises(NotImplementedError):
            Principals().create('phil')
        with self.assertRaises(NotImplementedError) as arc:
            Authentication().get_hashed_pw('phil')
        self.assertEqual(
            str(arc.exception),
            'get_hashed_pw(id: str) -> str must be implemented'
        )
        with self.assertRaises(NotImplementedError) as arc:
            Authentication().set_hashed_pw('phil', 'hashed')
        self.assertEqual(
            str(arc.exception),
            'set_hashed_pw(id: str, hpw: str) must be implemented'
        )

    @testing.delete_table_records(SQLPrincipal)
    @testing.delete_table_records(SQLGroup)
    @testing.delete_table_records(SQLUser)
    def test_ugm_roles_and_containers(self):
        ugm = create_ugm()
        user = ugm.users.create('phil')
        ugm.add_role('manager', user)
        self.assertEqual(ugm.roles(user), ['manager'])
        self.assertTrue(ugm['users'] is ugm.users)
        self.assertTrue(ugm['groups'] is ugm.groups)
        with self.assertRaises(NotImplementedError) as arc:
            ugm['users'] = object()
        self.assertEqual(
            str(arc.exception),
            '``__setitem__`` not in cone.sql.ugm.Ugm'
        )
        with self.assertRaises(NotImplementedError) as arc:
            del ugm['users']
        self.assertEqual(
            str(arc.exception),
            '``__delitem__`` not in cone.sql.ugm.Ugm'
        )
        self.assertEqual(list(ugm), ['users', 'groups'])

    def test_ugm_invalidate(self):
        ugm = create_ugm()
        users = ugm.users
        groups = ugm.groups
        ugm.invalidate()
        self.assertFalse(ugm.users is users)
        self.assertFalse(ugm.groups is groups)
        with self.assertRaises(KeyError):
            ugm.invalidate('inexistent')

    @testing.delete_table_records(SQLPrincipal)
    @testing.delete_table_records(SQLUser)
    @testing.use_transaction_manager
    def test_calling_with_transaction_manager_flushes_only(self):
        ugm = create_ugm()
        session = ugm.session
        # ``flush`` without ``commit`` - a rollback discards the change
        user = ugm.users.create('phil')
        user.attrs['email'] = 'phil@example.com'
        user()
        ugm.users()
        ugm()
        self.assertEqual(
            session.query(SQLUser).one().data,
            {'email': 'phil@example.com'}
        )
        session.rollback()
        self.assertEqual(session.query(SQLUser).count(), 0)
