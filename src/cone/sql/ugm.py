import base64
import hashlib
import itertools
import os
import uuid

from node.behaviors import Attributes, Nodify, Adopt, Nodespaces, NodeChildValidate, DefaultInit
from plumber import plumbing, Behavior, default, override
from sqlalchemy import Column, String, ForeignKey, JSON, cast
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base

from cone.sql.model import GUID, SQLRowNodeAttributes, SQLSession, UNICODE_TYPE
from cone.sql import SQLBase as Base

from sqlalchemy.orm import relationship, Session, object_session

from node.ext.ugm import (
    Principal as BasePrincipal,
    User as BaseUser,
    Group as BaseGroup,
    Users as BaseUsers,
    Groups as BaseGroups,
    Principals as BasePrincipals,
    Ugm as BaseUgm
)

####################################################
# SQLAlchemy model classes
####################################################

# Base = declarative_base()
from sqlalchemy.orm.exc import NoResultFound


class SQLPrincipal(Base):
    __tablename__ = 'principal'
    discriminator = Column(String)
    __mapper_args__ = {'polymorphic_on': discriminator}
    guid = Column(GUID, default=lambda: str(uuid.uuid4()), index=True, primary_key=True)
    data = Column(JSON, )
    principal_roles = Column(JSON, default=[])


class SQLGroup(SQLPrincipal):
    __mapper_args__ = {'polymorphic_identity': 'sqlgroup'}
    guid = Column(GUID, ForeignKey('principal.guid', deferrable=True), primary_key=True)
    __tablename__ = 'group'
    id = Column(String, unique=True)
    users = association_proxy("sqlgroupassignments", "users",
                              creator=lambda c: SQLGroupAssignment(users=c))
    sqlgroupassignments = relationship('SQLGroupAssignment', backref='groups',
                                       primaryjoin='SQLGroupAssignment.groups_guid == SQLGroup.guid')


class SQLGroupAssignment(Base):
    __tablename__ = 'group_assignment'
    groups_guid = Column(GUID, ForeignKey('group.guid', deferrable=True), primary_key=True, nullable=False)
    users_guid = Column(GUID, ForeignKey('user.guid', deferrable=True), primary_key=True, nullable=False)


class SQLUser(SQLPrincipal):
    __mapper_args__ = {'polymorphic_identity': 'sqluser'}
    guid = Column(GUID, ForeignKey('principal.guid', deferrable=True), primary_key=True)
    __tablename__ = 'user'
    login = Column(String, unique=True)
    id = Column(String, unique=True)
    hashed_pw = Column(String)
    groups = association_proxy("sqlgroupassignments", "groups",
                               creator=lambda c: SQLGroupAssignment(groups=c))
    sqlgroupassignments = relationship('SQLGroupAssignment', backref='users',
                                       primaryjoin='SQLGroupAssignment.users_guid == SQLUser.guid')


####################################################
# Node classes
####################################################

def has_autocommit():
    ac = os.environ.get("UGM_SQL_AUTOCOMMIT", "False").lower()
    if ac not in ["true", "false"]:
        raise ValueError(f"autocommit must be true/false, got {ac}")

    if ac == "true":
        return True
    else:
        return False


class PrincipalBehavior(Behavior):
    record = default(None)

    @default
    @property
    def id(self):
        return self.record.id

    @override
    def __init__(self, record):
        self.record = record

    @default
    def add_role(self, role):
        if role not in self.own_roles:
            self.own_roles = self.own_roles + [role]

    @default
    def remove_role(self, role):
        if role in self.own_roles:
            self.own_roles = [r for r in self.own_roles if r != role]  # to trigger the json field

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
    def attributes_factory(self, name, parent):
        return SQLRowNodeAttributes(name, parent, self.record)

    @default
    def __call__(self):
        if has_autocommit():
            self._session.commit()


class UserBehavior(PrincipalBehavior, BaseUser):
    @property
    def group_ids(self):
        return [g.id for g in self.groups]

    @property
    def groups(self):
        return [Group(g) for g in self.record.groups]

    @default
    @property
    def roles(self):
        """
        accumulate principal's roles + assigned groups' roles
        """
        my_roles = self.own_roles

        all_roles = itertools.chain(
            my_roles,
            *[
                g.principal_roles for g in self.record.groups
            ]
        )

        return set(all_roles)


ENCODING = 'utf-8'


class AuthenticationBehavior(Behavior):
    """
    handles password authentication for ugm
    contract:
    - the plumbed class implements the IUsers interface
    - the plumbed class implements get_hashed_pw(id: str) and set_hashed_pw(id: str, hpw: str)
    """
    salt_len = default(8)
    hash_func = default(hashlib.sha256)

    @override
    def authenticate(self, id=None, pw=None):
        # cannot authenticate user with unset password
        if id not in self:
            return False

        hpw = self.get_hashed_pw(id)
        if hpw:
            return self._chk_pw(pw, hpw)
        else:
            return False

    @default
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
        """must be implemented by plumbed class"""
        raise NotImplementedError("get_hashed_pw(id: str) -> str must be implemented")

    @default
    def set_hashed_pw(self, id, hpw):
        """must be implemented by plumbed class"""
        raise NotImplementedError("set_hashed_pw(id: str, hpw: str) must be implemented")


@plumbing(
    UserBehavior,
    Nodespaces,
    Attributes,
    Nodify,
    SQLSession
)
class User(object):
    pass


class GroupBehavior(PrincipalBehavior, BaseGroup):
    user_manager = default(None)
    """reference to IUsers instance"""

    @override
    def __init__(self, record, user_manager):
        self.record = record
        self.user_manager = user_manager

    @default
    @property
    def member_ids(self):
        return [u.id for u in self.record.users]

    @default
    def add(self, id):
        user = self.user_manager[id]
        self.record.users.append(user.record)

    @default
    def __getitem__(self, key):
        res = self.user_manager[key]

        if self.record not in res.record.groups:
            raise KeyError(key)

        return res

    @default
    def __delitem__(self, key):
        raise NotImplementedError(
            'Abstract ``Group`` does not implement ``__delitem__``')

    @default
    def __iter__(self):
        raise NotImplementedError(
            'Abstract ``Group`` does not implement ``__iter__``')

    @default
    @property
    def users(self):
        return [
            self.user_manager[id]
            for id in self.member_ids
        ]


@plumbing(
    GroupBehavior,
    Nodespaces,
    Attributes,
    Nodify,
    SQLSession
)
class Group(object):
    pass


class PrincipalsBehavior:

    @default
    def search(self, **kw):
        raise NotImplementedError

    @default
    def create(self, _id, **kw):
        raise NotImplementedError

    @default
    def __call__(self):
        if has_autocommit:
            self.session.commit()

    @default
    def invalidate(self, key=None):
        """
        ATM nothing to do here, when we start using caching principals we must remove them here
        """


class UsersBehavior(PrincipalsBehavior, BaseUsers):
    @default
    def id_for_login(self, login):
        try:
            searchterm = '"%s"' % login  # JSON field works so that the searchterm has to be enclosed in doublequotes
            if self.session.bind.dialect.name == 'sqlite':
                res = self.session.query(SQLUser).filter(
                    cast(SQLUser.data[cast("$." + SQLUser.login, String)], String) == searchterm
                ).one()
            else:
                res = self.session.query(SQLUser).filter(
                    cast(SQLUser.data[SQLUser.login], String) == searchterm
                ).one()
            return res.id
        except NoResultFound:
            raise KeyError(login)

    @default
    def __getitem__(self, id, default=None):
        try:
            sqluser = self.session.query(SQLUser).filter(SQLUser.id == id).one()
        except NoResultFound as ex:
            raise KeyError(id)
        return User(sqluser)

    @default
    def __delitem__(self, id):
        try:
            sqluser = self.session.query(SQLUser).filter(SQLUser.id == id).one()
            self.session.delete(sqluser)
        except NoResultFound as ex:
            raise KeyError(id)

    @default
    def __iter__(self):
        users = self.session.query(SQLUser)
        return map(lambda u: u.id, users)

    @default
    def __setitem__(self, key, value):
        raise NotImplementedError("users can only be added using the create() method")

    @default
    def create(self, _id, **kw):
        login = kw.pop("login", None)
        sqluser = SQLUser(id=_id, login=login, data=kw)
        self.session.add(sqluser)
        return self[_id]

    @default
    def get_hashed_pw(self, id):
        user = self[id]
        return user.record.hashed_pw

    @default
    def set_hashed_pw(self, id, hpw):
        user = self[id]
        user.record.hashed_pw = hpw


@plumbing(
    UsersBehavior,
    AuthenticationBehavior,
    NodeChildValidate,
    Nodespaces,
    Adopt,
    Attributes,
    Nodify,
    SQLSession
)
class Users(object):
    pass


class GroupsBehavior(PrincipalsBehavior, BaseGroups):
    user_manager = default(None)

    @override
    def __init__(self, users):
        self.user_manager = users

    @default
    def search(self, **kw):
        raise NotImplementedError

    @default
    def create(self, _id, **kw):
        sqlgroup = SQLGroup(id=_id, data=kw)
        self.session.add(sqlgroup)
        return self[_id]
        # return Group(sqlgroup, self.user_manager)  # when doing it so, I get weird join errors

    @default
    def __getitem__(self, id, default=None):
        try:
            sqlgroup = self.session.query(SQLGroup).filter(SQLGroup.id == id).one()
        except NoResultFound as ex:
            raise KeyError(id)
        return Group(sqlgroup, self.user_manager)

    @default
    def __delitem__(self, id):
        try:
            sqlgroup = self.session.query(SQLGroup).filter(SQLGroup.id == id).one()
            self.session.delete(sqlgroup)
        except NoResultFound as ex:
            raise KeyError(id)

    @default
    def __iter__(self):
        groups = self.session.query(SQLGroup)
        return map(lambda u: u.id, groups)

    @default
    def __setitem__(self, key, value):
        raise NotImplementedError("groups can only be added using the create() method")


@plumbing(
    GroupsBehavior,
    NodeChildValidate,
    Nodespaces,
    Adopt,
    Attributes,
    Nodify,
    SQLSession
)
class Groups(object):
    pass


class UgmBehavior(BaseUgm):
    users: Users = default(None)
    groups: Groups = default(None)

    @override
    def __init__(self):
        self.users = Users()
        self.groups = Groups(self.users)

    @default
    def __call__(self, *a):
        if has_autocommit():
            self.session.commit()

    @default
    def add_role(self, role, principal):
        raise NotImplementedError

    @default
    def remove_role(self, role, principal):
        raise NotImplementedError

    @default
    def roles(self, principal):
        raise NotImplementedError


@plumbing(
    UgmBehavior,
    Nodify)
class Ugm(object):
    pass
