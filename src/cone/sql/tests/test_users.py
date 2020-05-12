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

        # create some users with attribute
        ids = ["phil", "donald", "dagobert", "mickey"]
        for id in ids:
            email = f"{id}@bluedynamics.net"
            users.create(id, height=12, email=email)

        # give phil a password
        users.set_hashed_pw("phil", users.hash_passwd("test123"))
        print("hashed pwd:", users["phil"].record.hashed_pw)

        assert "phil" in users
        assert not "zworkb" in users

        assert users.authenticate("phil", "test123")
        assert not users.authenticate("zworkb", "test123")

        # check user attributes
        assert users["phil"].record.data["height"] == 12

        # check __iter__
        ids1 = list(users)
        assert sorted(ids) == sorted(ids1)
        print(ids1)

        # check login attribute (lets take email)
        # schlumpf and schlumpfine with 2 different login fields
        users.create("schlumpf", email="schlumpf@bluedynamics.net", login="email")
        users.create("schlumpfine", nickname="schlumpfinchen", login="nickname")

        schlumpfid = users.id_for_login("schlumpf@bluedynamics.net")
        schlumpfineid = users.id_for_login("schlumpfinchen")

        assert schlumpfid == "schlumpf"
        assert schlumpfineid == "schlumpfine"

        users.set_hashed_pw(schlumpfid, users.hash_passwd("schlumpf1"))
        users.set_hashed_pw(schlumpfineid, users.hash_passwd("schlumpfine1"))

        print("schlumpf ID:", schlumpfid)
        print("schlumpfine ID:", schlumpfineid)

        assert users.authenticate(schlumpfid, "schlumpf1")
        assert users.authenticate(schlumpfineid, "schlumpfine1")

        users.session.commit()


        # check __setitem__

