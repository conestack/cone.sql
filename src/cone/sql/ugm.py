import base64
import hashlib
import itertools
import os
import uuid
from datetime import datetime
from operator import or_

from node.behaviors import Attributes, Nodify, Adopt, Nodespaces, NodeChildValidate, DefaultInit
from plumber import plumbing, Behavior, default, override
from sqlalchemy import Column, String, ForeignKey, JSON, cast, and_, Integer, DateTime
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

    def get_attribute(self, key, default=None):
        try:
            return getattr(self, key)
        except AttributeError:
            return self.data.get(key, default)


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
    """
    retrieve the autocommit flag from env
    only "True", "False" are allowed
    :return: bool
    """
    ac = os.environ.get("UGM_SQL_AUTOCOMMIT", "False").lower()
    if ac not in ["true", "false"]:
        raise ValueError(f"autocommit must be true/false, got {ac}")

    if ac == "true":
        return True
    else:
        return False


class PrincipalBehavior(Behavior):
    record = default(None)
    """reference to sqlalchemy record instance"""
    ugm = default(None)
    """reference to IUgm instance"""

    @override
    def __init__(self, record, ugm):
        self.record = record
        self.ugm = ugm

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

    @default
    def authenticate(self, pw):
        return self.ugm.users.authenticate(self.id, pw)


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
        # this one does not work, throws
        # AssertionError: Dependency rule tried to blank-out primary key column 'group_assignment.groups_guid' on instance '<SQLGroupAssignment at 0x10f831310>'
        # self.record.users.remove(self.ugm.users[key].record)

        user = self.ugm.users[key]
        assoc = self.ugm.users.session.query(SQLGroupAssignment).filter(
            and_(
                SQLGroupAssignment.groups_guid == self.record.guid,
                SQLGroupAssignment.users_guid == user.record.guid
            )
        ).one()
        self.ugm.users.session.delete(assoc)

    @default
    def __iter__(self):
        return iter(self.member_ids)  # XXX: for groups with many many members this should be implemented lazy

    @default
    @property
    def users(self):
        return [
            self.ugm.users[id]
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


class PrincipalsBehavior(Behavior):

    @override
    def search(self, criteria=None, attrlist=None,
               exact_match=False, or_search=False):
        if criteria is None:
            criteria = {}
        op = or_ if or_search else and_
        cls = self.record_class
        fixed_fields = ["id", "login"]
        fixed_field_comparators = [
            getattr(cls, key) == criteria[key] if exact_match \
                else getattr(cls, key).like(("%s" % criteria[key]).replace("*", "%%"))

            for key in fixed_fields
            if key in criteria
        ]
        for key in fixed_fields:
            criteria.pop(key, None)

        def literal(value):
            lit = ('"%s"' % value) if isinstance(value, str) else str(value)
            if exact_match:
                return lit
            else:
                return lit.replace("*", "%%")

        def field_selector(key, value):
            return cast(cls.data[key], String)

        def field_comparator(key, value):
            if not exact_match and isinstance(value, str):
                return field_selector(key, value).like(literal(value))
            else:
                return field_selector(key, value) == literal(value)

        dynamic_comparators = [
            field_comparator(key, value)
            for (key, value) in criteria.items()
        ]

        comparators = fixed_field_comparators + dynamic_comparators
        clause = op(*comparators)
        query = self.ugm.users.session.query(cls).filter(clause)

        # XXX: should we be lazy here and yield?, would be nice for looong lists
        if attrlist is not None:
            if attrlist:
                res = [
                    (
                        p.id,
                        {k: p.get_attribute(k) for k in attrlist}
                    )
                    for p in query.all()
                ]
            else:  # empty attrlist, so we take all attributes
                res = [
                    (
                        p.id,
                        {  # merge fixed attributes and dynamic attributes from ``data``
                            **{k: p.get_attribute(k) for k in fixed_fields if k != 'id'},
                            **p.data
                        }
                    )
                    for p in query.all()
                ]

            res
        else:
            res = [p.id for p in query.all()]

        if exact_match and not res:
            raise ValueError("no entries found")
        return res

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
    ugm = default(None)
    record_class = default(SQLUser)

    @override
    def __init__(self, ugm):
        self.ugm = ugm

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
                    SQLUser.data[SQLUser.login].cast(String) == searchterm
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
        return User(sqluser, self.ugm)

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

    # @default
    # def search(self, *a, **kw):
    #     """had to implement this, because search got routed to """
    #     return PrincipalsBehavior.search(self, *a, **kw)


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
    ugm = default(None)
    record_class = default(SQLGroup)

    @override
    def __init__(self, ugm):
        self.ugm = ugm

    @default
    def create(self, _id, **kw):
        sqlgroup = SQLGroup(id=_id, data=kw)
        self.session.add(sqlgroup)
        return self[_id]
        # return Group(sqlgroup, self.ugm)  # when doing it so, I get weird join errors

    @default
    def __getitem__(self, id, default=None):
        try:
            sqlgroup = self.session.query(SQLGroup).filter(SQLGroup.id == id).one()
        except NoResultFound as ex:
            raise KeyError(id)
        return Group(sqlgroup, self.ugm)

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
        self.users = Users(self)
        self.groups = Groups(self)

    @default
    def __call__(self, *a):
        if has_autocommit():
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


@plumbing(
    UgmBehavior,
    Nodify)
class Ugm(object):
    pass
