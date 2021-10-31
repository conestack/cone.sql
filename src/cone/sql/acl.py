from cone.app.security import PrincipalACL
from cone.sql import get_session
from cone.sql import SQLBase
from cone.sql.model import GUID
from node.behaviors import Adopt
from node.behaviors import DefaultInit
from node.behaviors import NodeChildValidate
from node.behaviors import Nodify
from node.interfaces import IUUID
from node.utils import instance_property
from plumber import default
from plumber import plumbing
from pyramid.threadlocal import get_current_request
from sqlalchemy import and_
from sqlalchemy import Column
from sqlalchemy import String
import uuid


class PrincipalRoleRecord(SQLBase):
    __tablename__ = 'principal_roles'

    rec_id = Column(GUID, primary_key=True, default=lambda: uuid.uuid4())
    node_id = Column(GUID)
    principal_id = Column(String)
    role = Column(String)


@plumbing(
    NodeChildValidate,
    Adopt,
    DefaultInit,
    Nodify)
class SQLPrincipalRoles(object):
    """Principal roles from sql.
    """
    allow_non_node_children = True

    @property
    def session(self):
        return get_session(get_current_request())

    def _roles_for(self, principal_id):
        res = self.session\
            .query(PrincipalRoleRecord.role)\
            .filter(and_(
                PrincipalRoleRecord.node_id == self.parent.uuid,
                PrincipalRoleRecord.principal_id == principal_id
            ))\
            .distinct()
        return [rec.role for rec in res]

    def __getitem__(self, name):
        return self._roles_for(name)

    def __setitem__(self, name, value):
        session = self.session
        existing = self._roles_for(name)
        for role in value:
            if role not in existing:
                session.add(PrincipalRoleRecord(
                    node_id=self.parent.uuid,
                    principal_id=name,
                    role=role
                ))
        delete = list()
        for role in existing:
            if role not in value:
                delete.append(role)
        if delete:
            res = session\
                .query(PrincipalRoleRecord)\
                .filter(and_(
                    PrincipalRoleRecord.node_id == self.parent.uuid,
                    PrincipalRoleRecord.principal_id == name,
                    PrincipalRoleRecord.role.in_(delete)
                ))\
                .all()
            for record in res:
                session.delete(record)

    def __delitem__(self, name):
        session = self.session
        res = session\
            .query(PrincipalRoleRecord)\
            .filter(and_(
                PrincipalRoleRecord.node_id == self.parent.uuid,
                PrincipalRoleRecord.principal_id == name
            ))\
            .all()
        for record in res:
            session.delete(record)

    def __iter__(self):
        res = self.session\
            .query(PrincipalRoleRecord.principal_id)\
            .filter(PrincipalRoleRecord.node_id == self.parent.uuid)\
            .distinct()
        for rec in res:
            yield rec.principal_id


class SQLPrincipalACL(PrincipalACL):
    """Principal ACL stored in relational database.
    """

    @default
    @instance_property
    def principal_roles(self):
        if not IUUID.providedBy(self):
            raise RuntimeError(u"%s does not implement IUUID" % str(self))
        return SQLPrincipalRoles('principal_roles', parent=self)
