import unittest
from typing import Callable

from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from cone.sql.ugm.users import User, Base, Group


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
    def create_user(self, session):
        for name in ["phil", "donald", "dagobert", "daisy"]:
            session.add(User(name=name))

        session.flush()

        users = session.query(User).all()
        usernames = [u.name for u in users]
        assert "phil" in usernames

        for group in ["admins", "loosers", "members", "editors"]:
            session.add(Group(name=group))

        session.flush()

        phil = session.query(User).filter(User.name == "phil").one()
        donald = session.query(User).filter(User.name == "donald").one()
        admins = session.query(Group).filter(Group.name == "admins").one()
        losers = session.query(Group).filter(Group.name == "losers").one()
        members = session.query(Group).filter(Group.name == "members").one()

        phil.groups.append(admins)
        phil.groups.append(members)

        donald.groups.append(losers)
        donald.groups.append(members)
        session.flush()

        phil1 = session.query(User).filter(User.name == "phil").one()
        donald1 = session.query(User).filter(User.name == "donald").one()

        assert admins in phil1.groups
        assert members in phil1.groups

        losers1 = session.query(Group).filter(Group.name == "losers")
        members = session.query(Group).filter(Group.name ==  "members")

        assert phil in members.users
        assert donald in members.users