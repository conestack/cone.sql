import os
import unittest

from node.tests import NodeTestCase
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from cone.sql.ugm import SQLPrincipal as Principal, SQLUser, Base, SQLGroup, Ugm, Group, User, Groups, Users

from cone.sql import testing


def temp_database(fn):
    """
    This decorator creates an in-memory sqlite db for testing the user classes

    """

    def wrapper(self):
        curdir = os.path.dirname(__file__)
        fname = "%s/test.db" % curdir
        if os.path.exists(fname):
            os.remove(fname)
        uri = "sqlite:///" + fname
        engine = create_engine(uri)
        Base.metadata.create_all(engine)
        sm = sessionmaker(bind=engine)
        session = sm()
        fn(self, session)

    return wrapper


class UsersTestCase(unittest.TestCase):

    @temp_database
    def test_db(self, session):
        print(session)

    @temp_database
    def test_create_user(self, session):
        for name in ["phil", "donald", "dagobert", "daisy"]:
            session.add(SQLUser(id=name))

        session.flush()

        users = session.query(SQLUser).all()
        usernames = [u.id for u in users]
        assert "phil" in usernames

        for group in ["admins", "losers", "members", "editors", "phil"]:
            session.add(SQLGroup(id=group))

        session.flush()

        phil = session.query(SQLUser).filter(SQLUser.id == "phil").one()
        donald = session.query(SQLUser).filter(SQLUser.id == "donald").one()
        admins = session.query(SQLGroup).filter(SQLGroup.id == "admins").one()
        losers = session.query(SQLGroup).filter(SQLGroup.id == "losers").one()
        members = session.query(SQLGroup).filter(SQLGroup.id == "members").one()

        phil.principal_roles = ["manager", "member"]

        phil.groups.append(admins)
        phil.groups.append(members)

        donald.groups.append(losers)
        donald.groups.append(members)
        session.flush()

        phil1 = session.query(SQLUser).filter(SQLUser.id == "phil").one()
        donald1 = session.query(SQLUser).filter(SQLUser.id == "donald").one()

        assert "manager" in phil1.principal_roles

        assert admins in phil1.groups
        assert members in phil1.groups

        losers1 = session.query(SQLGroup).filter(SQLGroup.id == "losers").one()
        members = session.query(SQLGroup).filter(SQLGroup.id == "members").one()
        phil_group = session.query(SQLGroup).filter(SQLGroup.id == "phil").one()

        assert phil_group.id == phil.id
        assert phil_group.guid != phil.guid

        assert phil in members.users
        assert donald in members.users

        session.commit()


class TestUserNodes(NodeTestCase):
    layer = testing.sql_layer

    def test_node_users(self):
        self.layer.new_request()
        ugm = Ugm()
        users = ugm.users
        groups = ugm.groups

        phil = users.create("phil")

        print("user:", phil)



