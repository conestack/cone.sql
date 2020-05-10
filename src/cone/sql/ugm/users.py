import uuid

from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base

from cone.sql.model import GUID
from sqlalchemy.orm import relationship

Base = declarative_base()


class Role(Base):
    __tablename__ = "role"
    id = Column(String, index=True, primary_key=True)


class User(Base):
    __tablename__ = "user"
    # id = Column(GUID, default=lambda: str(uuid.uuid4()), index=True, primary_key=True)
    id = Column(String, nullable=False, index=True, primary_key=True)
    groups = association_proxy("group_assignments", "groups",
                              creator=lambda c: GroupAssignment(user=c))
    group_assignments = relationship(
        'GroupAssignment',
        backref='user',
        primaryjoin='GroupAssignment.user_id == User.id'
    )


class Group(Base):
    __tablename__ = "group"
    # id = Column(GUID, default=lambda: str(uuid.uuid4()), index=True, primary_key=True)
    id = Column(String, nullable=False, index=True, primary_key=True)
    users = association_proxy("group_assignments", "users",
                              creator=lambda c: GroupAssignment(group=c))
    group_assignments = relationship(
        'GroupAssignment',
        backref='group',
        primaryjoin='GroupAssignment.group_id == Group.id'
    )


class GroupAssignment(Base):
    __tablename__ = 'group_assignment'
    group_id = Column(String, ForeignKey('group.id', deferrable=True, ), nullable=False, primary_key=True)
    user_id = Column(String, ForeignKey('user.id', deferrable=True), nullable=False, primary_key=True)
