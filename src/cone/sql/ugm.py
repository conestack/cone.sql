from cone.sql import SQLBase as Base
from cone.sql import use_tm
from cone.sql.model import GUID
from cone.sql.model import SQLRowNodeAttributes
from cone.sql.model import SQLSession
from cone.sql.model import UNICODE_TYPE
from datetime import datetime
from node.behaviors import Adopt
from node.behaviors import Attributes
from node.behaviors import DefaultInit
from node.behaviors import NodeChildValidate
from node.behaviors import Nodespaces
from node.behaviors import Nodify
from node.ext.ugm import Group as BaseGroup
from node.ext.ugm import Groups as BaseGroups
from node.ext.ugm import Ugm as BaseUgm
from node.ext.ugm import User as BaseUser
from node.ext.ugm import Users as BaseUsers
from node.utils import UNSET
from operator import or_
from plumber import Behavior
from plumber import default
from plumber import override
from plumber import plumbing
from sqlalchemy import and_
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import inspect
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import NoResultFound
import base64
import hashlib
import itertools
import os
import uuid

# HACK: Force sqlite to alias JSONB as JSON. This allows to use JSONB for the
#       sqlalchemy variant, which is much more efficient when it comes to
#       indexing and searching.
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


###############################################################################
# SQLAlchemy model classes
###############################################################################

class SQLPrincipal(Base):
    __tablename__ = 'principal'
    discriminator = Column(String)
    __mapper_args__ = {'polymorphic_on': discriminator}
    guid = Column(
        GUID,
        default=lambda: str(uuid.uuid4()),
        index=True,
        primary_key=True
    )
    data = Column(JSONB)
    principal_roles = Column(JSONB, default=[])
    created = Column(DateTime, default=datetime.now)

    def get_attribute(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            return self.data.get(key)


class SQLGroup(SQLPrincipal):
    __tablename__ = 'group'
    __mapper_args__ = {'polymorphic_identity': 'sqlgroup'}
    guid = Column(
        GUID,
        ForeignKey('principal.guid', deferrable=True),
        primary_key=True
    )
    id = Column(String, unique=True)
    users = association_proxy(
        'group_assignments',
        'users',
        creator=lambda c: SQLGroupAssignment(users=c)
    )
    group_assignments = relationship(
        'SQLGroupAssignment',
        backref='groups',
        primaryjoin='SQLGroupAssignment.groups_guid == SQLGroup.guid',
        cascade='save-update, merge, delete, delete-orphan'
    )


class SQLGroupAssignment(Base):
    __tablename__ = 'group_assignment'
    groups_guid = Column(
        GUID,
        ForeignKey('group.guid', deferrable=True),
        primary_key=True,
        nullable=False
    )
    users_guid = Column(
        GUID,
        ForeignKey('user.guid', deferrable=True),
        primary_key=True,
        nullable=False
    )


class SQLUser(SQLPrincipal):
    __tablename__ = 'user'
    __mapper_args__ = {'polymorphic_identity': 'sqluser'}
    guid = Column(
        GUID,
        ForeignKey('principal.guid', deferrable=True),
        primary_key=True
    )
    login = Column(String)
    id = Column(String, unique=True)
    password = Column(String)
    first_login = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    groups = association_proxy(
        'group_assignments',
        'groups',
        creator=lambda c: SQLGroupAssignment(groups=c)
    )
    group_assignments = relationship(
        'SQLGroupAssignment',
        backref='users',
        primaryjoin='SQLGroupAssignment.users_guid == SQLUser.guid',
        cascade='save-update, merge, delete, delete-orphan'
    )


###############################################################################
# Node classes
###############################################################################

class PrincipalAttributes(SQLRowNodeAttributes):
    """Consists of field configured in .ini file or ugm.xml and the given SQL
    schema fields.
    """

    @property
    def ugm(self):
        return self.parent.ugm

    def __setitem__(self, name, value):
        if value is UNSET:
            value = ''
        if value and name in self.binary_attrs:
            value = base64.b64encode(value).decode()
        if name in self.schema_attrs:
            setattr(self.record, name, value)
        else:
            self.record.data[name] = value
            flag_modified(self.record, 'data')

    def __getitem__(self, name):
        value = self.record.get_attribute(name)
        if value and name in self.binary_attrs:
            value = base64.b64decode(value)
        return value

    @property
    def _columns(self):
        if self.configured_attrs:
            return self.configured_attrs
        else:
            return self.inspected_attrs

    @property
    def schema_attrs(self):
        """Fields that are in the record schema without the technical fields.
        """
        tech_attrs = [
            'group_assignments', 'discriminator', 'guid',
            'data', 'principal_roles', 'password'
        ]
        schema_attrs = [
            f for f in
            inspect(self.record.__class__).attrs.keys()
            if f not in tech_attrs
        ]
        return schema_attrs

    @property
    def inspected_attrs(self):
        """Fields that are in the record schema + keys from record.data without
        the technical fields.
        """
        return self.schema_attrs + list(self.record.data.keys())

    @property
    def binary_attrs(self):
        return self.ugm.binary_attrs


class UserAttributes(PrincipalAttributes):

    @property
    def configured_attrs(self):
        return self.ugm.user_attrs


class GroupAttributeFactory(PrincipalAttributes):

    @property
    def configured_attrs(self):
        return self.ugm.group_attrs


class PrincipalBehavior(Behavior):

    record = default(None)
    """Reference to sqlalchemy record instance."""

    @override
    def __init__(self, parent, record):
        self.__parent__ = parent
        self.record = record

    @default
    @property
    def __name__(self):
        return self.id

    @default
    @property
    def ugm(self):
        return self.parent.parent

    @default
    @property
    def id(self):
        return self.record.id

    @default
    def add_role(self, role):
        if role not in self.own_roles:
            self.own_roles = self.own_roles + [role]

    @default
    def remove_role(self, role):
        if role in self.own_roles:
            # to trigger the json field
            self.own_roles = [r for r in self.own_roles if r != role]

    @property
    def own_roles(self):
        return self.record.principal_roles

    @default
    @own_roles.setter
    def own_roles(self, roles):
        self.record.principal_roles = roles

    @default
    @property
    def roles(self):
        return self.own_roles

    @default
    def __call__(self):
        if use_tm():
            self.session.flush()
        else:
            self.session.commit()


class UserBehavior(PrincipalBehavior, BaseUser):

    @default
    @property
    def group_ids(self):
        return [g.id for g in self.groups]

    @default
    @property
    def groups(self):
        return [self.ugm.groups[g.id] for g in self.record.groups]

    @default
    @property
    def roles(self):
        """Accumulate principal's roles + assigned groups' roles.
        """
        my_roles = self.own_roles
        all_roles = itertools.chain(
            my_roles,
            *[g.principal_roles for g in self.record.groups]
        )
        return list(set(all_roles))

    @default
    def authenticate(self, pw):
        return self.ugm.users.authenticate(self.id, pw)

    @default
    def passwd(self, old, new):
        return self.ugm.users.passwd(self.id, old, new)

    @default
    def attributes_factory(self, name, parent):
        return UserAttributes(name, parent, self.record)


@plumbing(
    UserBehavior,
    Nodespaces,
    Attributes,
    Nodify,
    Adopt,
    SQLSession)
class User(object):
    pass


class GroupBehavior(PrincipalBehavior, BaseGroup):

    @default
    @property
    def member_ids(self):
        return [u.id for u in self.record.users]

    @default
    def add(self, id):
        user = self.ugm.users[id]
        self.record.users.append(user.record)

    @default
    def __getitem__(self, key):
        res = self.ugm.users[key]

        if self.record not in res.record.groups:
            raise KeyError(key)

        return res

    @default
    def __delitem__(self, key):
        self.record.users.remove(self.ugm.users[key].record)

    @default
    def __iter__(self):
        # XXX: for groups with many many members this should be implemented lazy
        return iter(self.member_ids)

    @default
    @property
    def users(self):
        return [
            self.ugm.users[id]
            for id in self.member_ids
        ]

    @default
    def attributes_factory(self, name, parent):
        return GroupAttributeFactory(name, parent, self.record)


@plumbing(
    GroupBehavior,
    Nodespaces,
    Attributes,
    Nodify,
    SQLSession)
class Group(object):
    pass


class PrincipalsBehavior(Behavior):

    @default
    @property
    def ugm(self):
        return self.parent

    @override
    def search(self, criteria=None, attrlist=None,
               exact_match=False, or_search=False):
        typemap = {
            str: String,
            int: Integer
        }
        if criteria is None:
            criteria = {}

        op = or_ if or_search else and_
        cls = self.record_class
        fixed_attrs = ['id', 'login']
        fixed_attr_comparators = [
            getattr(cls, key) == criteria[key] if exact_match
            else getattr(cls, key).like(('%s' % criteria[key]).replace('*', '%%'))
            for key in fixed_attrs
            if key in criteria
        ]
        for key in fixed_attrs:
            criteria = criteria.copy()
            criteria.pop(key, None)

        def literal(value):
            lit = ('"%s"' % value) if isinstance(value, str) else value
            if exact_match:
                return lit
            else:
                return lit.replace('*', '%%') if isinstance(lit, str) else lit

        def field_selector(key, value):
            return cls.data[key].cast(String).cast(typemap[type(value)])

        def field_comparator(key, value):
            if not exact_match and isinstance(value, str):
                return field_selector(key, value).like(literal(value))
            else:
                return field_selector(key, value) == literal(value)

        dynamic_comparators = [
            field_comparator(key, value)
            for (key, value) in criteria.items()
        ]

        comparators = fixed_attr_comparators + dynamic_comparators
        if len(comparators) >= 2:
            clause = op(*comparators)
        elif len(comparators) == 1:
            clause = comparators[0]
        else:
            clause = None

        basequery = self.ugm.users.session.query(cls)
        if clause is not None:
            query = basequery.filter(clause)
        else:
            query = basequery

        binary_attrs = self.ugm.binary_attrs

        def get_attribute(p, k):
            value = p.get_attribute(k)
            if value and k in binary_attrs:
                value = base64.b64decode(value)
            return value

        # XXX: should we be lazy here and yield?, would be nice for looong lists
        if attrlist is not None:
            if attrlist:
                res = [
                    (p.id, {k: get_attribute(p, k) for k in attrlist})
                    for p in query.all()
                ]
            # empty attrlist, so we take all attributes
            else:
                def merged_attrs(p):
                    # merge fixed attributes and dynamic attributes from ``data``
                    attrs = {k: get_attribute(p, k) for k in fixed_attrs if k != 'id'}
                    attrs.update(**{k: get_attribute(p, k) for k in p.data})
                    return attrs

                res = [(p.id, merged_attrs(p)) for p in query.all()]
            res
        else:
            res = [p.id for p in query.all()]

        if exact_match and not res:
            raise ValueError('no entries found')
        return res

    @default
    def create(self, _id, **kw):
        raise NotImplementedError()

    @default
    def __call__(self):
        if use_tm():
            self.session.flush()
        else:
            self.session.commit()


ENCODING = 'utf-8'


class AuthenticationBehavior(Behavior):
    """Handles password authentication for ugm contract:

    - the plumbed class implements the IUsers interface
    - the plumbed class implements get_hashed_pw(id: str) and
      set_hashed_pw(id: str, hpw: str)
    """
    salt_len = default(8)
    hash_func = default(hashlib.sha256)

    def on_authenticated(self, id, **kw):
        """Can be overriden to do after-authentication stuff.
        """

    @override
    def authenticate(self, id=None, pw=None):
        # cannot authenticate user with unset password.
        if not id or not pw:
            return False

        if id not in self:
            return False

        hpw = self.get_hashed_pw(id)
        if hpw:
            authenticated = self._chk_pw(pw, hpw)
            if authenticated:
                self.on_authenticated(id)

            return authenticated
        else:
            return False

    @override
    def passwd(self, id, oldpw, newpw):
        if id not in self:
            raise ValueError(u"User with id '{}' does not exist.".format(id))
        if oldpw is not None:
            if not self._chk_pw(oldpw, self.get_hashed_pw(id)):
                raise ValueError('Old password does not match.')
        hpw = self.hash_passwd(newpw)
        self.set_hashed_pw(id, hpw)
        self()

    @default
    def hash_passwd(self, newpw):
        salt = os.urandom(self.salt_len)
        newpw = newpw.encode(ENCODING) \
            if isinstance(newpw, UNICODE_TYPE) \
            else newpw
        hashed = base64.b64encode(self.hash_func(newpw + salt).digest() + salt)
        return hashed.decode()

    @default
    def _chk_pw(self, plain, hashed):
        hashed = base64.b64decode(hashed)
        salt = hashed[-self.salt_len:]
        plain = plain.encode(ENCODING) \
            if isinstance(plain, UNICODE_TYPE) \
            else plain
        return hashed == self.hash_func(plain + salt).digest() + salt

    @default
    def get_hashed_pw(self, id):
        msg = 'get_hashed_pw(id: str) -> str must be implemented'
        raise NotImplementedError(msg)

    @default
    def set_hashed_pw(self, id, hpw):
        msg = 'set_hashed_pw(id: str, hpw: str) must be implemented'
        raise NotImplementedError(msg)


class UsersBehavior(PrincipalsBehavior, BaseUsers):
    record_class = default(SQLUser)

    @default
    def id_for_login(self, login):
        try:
            # Searchterm has to be enclosed in doublequotes to work on JSON fields
            searchterm = '"%s"' % login
            field_name = SQLUser.login
            if self.session.bind.dialect.name == 'sqlite':
                # If the key to the json field is variable we need a special
                # treatment for sqlite
                field_name = ('$.' + field_name).cast(String)
            res = self.session.query(SQLUser).filter(
                SQLUser.data[field_name].cast(String) == searchterm
            ).one()
            return res.id
        except NoResultFound:
            # if we dont find a login field, fall back assuming id is login
            return login

    @default
    def __getitem__(self, id, default=None):
        try:
            sqluser = self.session.query(SQLUser).filter(SQLUser.id == id).one()
        except NoResultFound:
            raise KeyError(id)
        return User(self, sqluser)

    @default
    def __delitem__(self, id):
        try:
            sqluser = self.session.query(SQLUser).filter(SQLUser.id == id).one()
            self.session.delete(sqluser)
        except NoResultFound:
            raise KeyError(id)

    @default
    def __iter__(self):
        users = self.session.query(SQLUser)
        return iter(map(lambda u: u.id, users))

    @default
    def __setitem__(self, key, value):
        msg = 'users can only be added using the create() method'
        raise NotImplementedError(msg)

    @default
    def create(self, _id, **kw):
        login = kw.pop('login', None)
        for name, value in kw.items():
            if value and name in self.ugm.binary_attrs:
                kw[name] = base64.b64encode(value).decode()
        sqluser = SQLUser(id=_id, login=login, data=kw)
        self.session.add(sqluser)
        self.session.flush()
        return self[_id]

    @default
    def get_hashed_pw(self, id):
        user = self[id]
        return user.record.password

    @default
    def set_hashed_pw(self, id, hpw):
        user = self[id]
        user.record.password = hpw

    @default
    def passwd(self, id, old, new):
        self[id].passwd(old, new)

    @default
    def on_authenticated(self, id, **kw):
        if self.ugm.log_auth:
            user = self[id]
            now = datetime.now()
            if user.record.first_login is None:
                user.record.first_login = now
            user.record.last_login = now

    @default
    def invalidate(self, key=None, *a, **kw):
        self.parent.invalidate(key='users')


@plumbing(
    UsersBehavior,
    AuthenticationBehavior,
    NodeChildValidate,
    Nodespaces,
    Adopt,
    Attributes,
    Nodify,
    SQLSession,
    DefaultInit)
class Users(object):
    pass


class GroupsBehavior(PrincipalsBehavior, BaseGroups):
    record_class = default(SQLGroup)

    @default
    def create(self, _id, **kw):
        for name, value in kw.items():
            if value and name in self.ugm.binary_attrs:
                kw[name] = base64.b64encode(value).decode()
        sqlgroup = SQLGroup(id=_id, data=kw)
        self.session.add(sqlgroup)
        self.session.flush()
        return self[_id]

    @default
    def __getitem__(self, id, default=None):
        try:
            sqlgroup = self.session\
                .query(SQLGroup)\
                .filter(SQLGroup.id == id)\
                .one()
        except NoResultFound:
            raise KeyError(id)
        return Group(self, sqlgroup)

    @default
    def __delitem__(self, id):
        try:
            sqlgroup = self.session\
                .query(SQLGroup)\
                .filter(SQLGroup.id == id)\
                .one()
            self.session.delete(sqlgroup)
        except NoResultFound:
            raise KeyError(id)

    @default
    def __iter__(self):
        groups = self.session.query(SQLGroup)
        return iter(map(lambda u: u.id, groups))

    @default
    def __setitem__(self, key, value):
        msg = 'groups can only be added using the create() method'
        raise NotImplementedError(msg)

    @default
    def invalidate(self, key=None, *a, **kw):
        self.parent.invalidate(key='groups')


@plumbing(
    GroupsBehavior,
    NodeChildValidate,
    Nodespaces,
    Adopt,
    Attributes,
    Nodify,
    SQLSession,
    DefaultInit)
class Groups(object):
    pass


class UgmBehavior(BaseUgm):
    users = default(None)
    groups = default(None)
    user_attrs = default([])
    group_attrs = default([])
    binary_attrs = default([])
    log_auth = default(False)

    @override
    def __init__(self, name, parent, user_attrs,
                 group_attrs, binary_attrs, log_auth):
        self.__name__ = name
        self.__parent__ = parent
        self.users = Users('users', self)
        self.groups = Groups('groups', self)
        self.user_attrs = user_attrs
        self.group_attrs = group_attrs
        self.binary_attrs = binary_attrs
        self.log_auth = log_auth

    @default
    def __call__(self):
        if use_tm():
            self.session.flush()
        else:
            self.session.commit()

    @default
    def add_role(self, role, principal):
        principal.add_role(role)

    @default
    def remove_role(self, role, principal):
        principal.remove_role(role)

    @default
    def roles(self, principal):
        return principal.roles

    @default
    def __getitem__(self, k):
        return getattr(self, k)

    @default
    def __iter__(self, k):
        return iter(['users', 'groups'])

    @default
    def __setitem__(self, k, v):
        raise NotImplementedError('``__setitem__`` not in cone.sql.ugm.Ugm')

    @default
    def __delitem__(self, k, v):
        raise NotImplementedError('``__delitem__`` not in cone.sql.ugm.Ugm')

    @default
    def invalidate(self, key=None):
        if not key:
            self.users = Users('users', self)
            self.groups = Groups('groups', self)
            return
        if key == 'users':
            self.users = Users('users', self)
            return
        if key == 'groups':
            self.groups = Groups('groups', self)
            return
        raise KeyError(key)


@plumbing(
    UgmBehavior,
    Nodify,
    SQLSession)
class Ugm(object):
    pass
