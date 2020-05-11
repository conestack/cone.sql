import hashlib
import os
import uuid
from abc import ABC
from typing import List

from node.behaviors import Attributes, Nodify, Adopt, Nodespaces, NodeChildValidate
from plumber import plumbing, Behavior, default
from sqlalchemy import Column, String, ForeignKey, JSON
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base

from cone.sql.model import GUID, SQLRowNodeAttributes, SQLSession
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

Base = declarative_base()


class SQLPrincipal(Base):
    __tablename__ = 'principal'
    discriminator = Column(String)
    __mapper_args__ = {'polymorphic_on': discriminator}
    guid = Column(GUID, default=lambda: str(uuid.uuid4()), index=True, primary_key=True)
    data = Column(JSON)
    principal_roles = Column(JSON, default=[])


class SQLGroup(SQLPrincipal):
    __mapper_args__ = {'polymorphic_identity': 'sqlgroup'}
    guid = Column(GUID, ForeignKey('principal.guid', deferrable=True), primary_key=True)
    __tablename__ = 'group'
    id = Column(String)
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
    login = Column(String)
    id = Column(String)
    passwd_encrypted = Column(String)
    groups = association_proxy("sqlgroupassignments", "groups",
                               creator=lambda c: SQLGroupAssignment(groups=c))
    sqlgroupassignments = relationship('SQLGroupAssignment', backref='users',
                                       primaryjoin='SQLGroupAssignment.users_guid == SQLUser.guid')


####################################################
# Node classes
####################################################

autocommit = os.environ.get("UGM_SQL_AUTOCOMMIT", False)


class PrincipalBehavior(BasePrincipal):
    _model: SQLPrincipal = None

    def __init__(self, model):
        self._model = model

    @property
    def object_session(self):
        return object_session(self)

    def add_role(self, role: str):
        if role not in self.roles:
            self.roles = self.roles + [role]

    def remove_role(self, role: str):
        if role in self.roles:
            self.roles = [r for r in self.roles if r != role]  # to trigger the json field

    @property
    def roles(self) -> List[str]:
        return self._model.principal_roles
    
    @roles.setter
    def roles(self, roles: List[str]):
        self._model.principal_roles = roles

    def attributes_factory(self, name, parent):
        return SQLRowNodeAttributes(name, parent, self.record)

    def __call__(self):
        if autocommit:
            self._session.commit()


class UserBehavior(PrincipalBehavior):

    @property
    def group_ids(self):
        return [g.id for g in self.groups]

    # Leaf API hardening
    def __getitem__(self, key):
        raise NotImplementedError('User does not support ``__getitem__``')

    def __setitem__(self, key, value):
        raise NotImplementedError('User does not support ``__setitem__``')

    def __delitem__(self, key):
        raise NotImplementedError('User does not support ``__delitem__``')

    def __iter__(self):
        return iter([])


class AuthenticationBehavior(Behavior):
    """
    handles password authentication for ugm
    contract:
    assumes that the plumbed class implements the IUsers interface
    """
    salt_len = default(8)
    hash_func = default(hashlib.sha256)

    @default
    def authenticate(self, id=None, pw=None):
        if id not in self.storage:
            return False
        # cannot authenticate user with unset password
        if not self.storage[id]:
            return False
        return self._chk_pw(pw, self.storage[id])

    @default
    def passwd(self, id, oldpw, newpw):
        if id not in self.storage:
            raise ValueError(u"User with id '{}' does not exist.".format(id))
        if oldpw is not None:
            if not self._chk_pw(oldpw, self.storage[id]):
                raise ValueError('Old password does not match.')
        salt = os.urandom(self.salt_len)
        newpw = newpw.encode(ENCODING) \
            if isinstance(newpw, UNICODE_TYPE) \
            else newpw
        hashed = base64.b64encode(self.hash_func(newpw + salt).digest() + salt)
        self.storage[id] = hashed.decode()
        self()

    @default
    def _chk_pw(self, plain, hashed):
        hashed = base64.b64decode(hashed)
        salt = hashed[-self.salt_len:]
        plain = plain.encode(ENCODING) \
            if isinstance(plain, UNICODE_TYPE) \
            else plain
        return hashed == self.hash_func(plain + salt).digest() + salt

    @property
    def hashed_pw(self):
        ...

    @hashed_pw.setter
    def hashed_pw(self, hpw):
        ...


@plumbing(
    UserBehavior,
    Nodespaces,
    Attributes,
    Nodify,
    SQLSession
)
class User(object):
    pass


class GroupBehavior(PrincipalBehavior):
    def __setitem__(self, key, value):
        self.data[key] = value

    @property
    def member_ids(self):
        return [u.id for u in self.users]

    def add(self, id: str):
        raise NotImplementedError


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

    def search(self, **kw):
        raise NotImplementedError

    def create(self, _id, **kw):
        raise NotImplementedError

    def __call__(self):
        if autocommit:
            self.session.commit()

    def invalidate(self, key=None):
        """
        ATM nothing to do here, when we start using caching principals we must remove them here
        """


class UsersBehavior(PrincipalsBehavior, BaseUsers):

    def id_for_login(self, login):
        raise NotImplementedError

    def __getitem__(self, id, default=None):
        user = self.session.query(SQLUser).filter(SQLUser.id == id).one()
        return User

    def authenticate(self, id=None, pw=None):
        raise NotImplementedError

    def passwd(self, id, oldpw, newpw):
        raise NotImplementedError

    def create(self, _id, **kw):
        login = kw.pop("login", None)
        sqluser = SQLUser(id=_id, login=login, data=kw)
        self.session.add(sqluser)
        u = User(sqluser)


@plumbing(
    UsersBehavior,
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

    def search(self, **kw):
        raise NotImplementedError

    def create(self, _id: str, **kw):
        raise NotImplementedError

    def invalidate(self, key=None):
        raise NotImplementedError


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


class Ugm(BaseUgm):
    users: Users
    groups: Groups

    def __init__(self):
        # self.session = session
        self.groups = Groups()
        self.users = Users()

    def __call__(self):
        if autocommit:
            self.session.commit()

    def add_role(self, role, principal):
        raise NotImplementedError

    def remove_role(self, role, principal):
        raise NotImplementedError

    def roles(self, principal):
        raise NotImplementedError

