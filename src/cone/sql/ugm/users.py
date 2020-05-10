import uuid

from sqlalchemy import Column, String, ForeignKey, JSON
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base

from cone.sql.model import GUID
from sqlalchemy.orm import relationship

Base = declarative_base()


class SQLPrincipal(Base):

    __tablename__ = 'principal'
    discriminator = Column(String)
    __mapper_args__ = {'polymorphic_on':discriminator}
    guid = Column(GUID,default = lambda :str(uuid.uuid4()), index = True, primary_key = True)
    data = Column(JSON)
    principal_roles = Column(JSON,default = [])

class SQLGroup(SQLPrincipal):

    __mapper_args__ = {'polymorphic_identity':'sqlgroup'}
    guid = Column(GUID, ForeignKey('principal.guid', deferrable=True),primary_key = True)
    __tablename__ = 'group'
    id = Column(String)
    users = association_proxy("sqlgroupassignments", "users",
                                creator=lambda c: SQLGroupAssignment(users=c))
    sqlgroupassignments = relationship('SQLGroupAssignment', backref = 'groups', primaryjoin = 'SQLGroupAssignment.groups_guid == SQLGroup.guid')

class SQLGroupAssignment(Base):

    __tablename__ = 'group_assignment'
    groups_guid = Column(GUID, ForeignKey('group.guid', deferrable=True), primary_key = True, nullable = False)
    users_guid = Column(GUID, ForeignKey('user.guid', deferrable=True), primary_key = True, nullable = False)

class SQLUser(SQLPrincipal):

    __mapper_args__ = {'polymorphic_identity':'sqluser'}
    guid = Column(GUID, ForeignKey('principal.guid', deferrable=True),primary_key = True)
    __tablename__ = 'user'
    login = Column(String)
    id = Column(String)
    passwd_encrypted = Column(String)
    groups = association_proxy("sqlgroupassignments", "groups",
                                creator=lambda c: SQLGroupAssignment(groups=c))
    sqlgroupassignments = relationship('SQLGroupAssignment', backref = 'users', primaryjoin = 'SQLGroupAssignment.users_guid == SQLUser.guid')