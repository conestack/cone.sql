import unittest
from typing import Callable

from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from cone.sql.ugm.users import SQLPrincipal as Principal, SQLUser as User, Base, SQLGroup as Group

def temp_database(fn: Callable[[Session], None]):
    """
    This decorator creates an in-memory sqlite db for testing the user classes

    """
    def wrapper(self):
        engine = create_engine("sqlite:///")
        Base.metadata.create_all(engine)
        sm = sessionmaker(bind=engine)
        session=sm()
        fn(self, session)

    return wrapper


class UsersTestCase(unittest.TestCase):

    @temp_database
    def test_db(self, session):
        print(session)

    @temp_database
    def test_create_user(self, session):
        for name in ["phil", "donald", "dagobert", "daisy"]:
            session.add(User(id=name))

        session.flush()

        users = session.query(User).all()
        usernames = [u.id for u in users]
        assert "phil" in usernames

        for group in ["admins", "losers", "members", "editors", "phil"]:
            session.add(Group(id=group))

        session.flush()

        phil = session.query(User).filter(User.id == "phil").one()
        donald = session.query(User).filter(User.id == "donald").one()
        admins = session.query(Group).filter(Group.id == "admins").one()
        losers = session.query(Group).filter(Group.id == "losers").one()
        members = session.query(Group).filter(Group.id == "members").one()

        phil.roles = ["manager", "member"]

        phil.groups.append(admins)
        phil.groups.append(members)

        donald.groups.append(losers)
        donald.groups.append(members)
        session.flush()

        phil1 = session.query(User).filter(User.id == "phil").one()
        donald1 = session.query(User).filter(User.id == "donald").one()

        assert "manager" in phil1.roles

        assert admins in phil1.groups
        assert members in phil1.groups

        losers1 = session.query(Group).filter(Group.id == "losers").one()
        members = session.query(Group).filter(Group.id ==  "members").one()
        phil_group = session.query(Group).filter(Group.id ==  "phil").one()

        assert phil_group.id == phil.id
        assert phil_group.guid != phil.guid

        assert phil in members.users
        assert donald in members.users

        # now try