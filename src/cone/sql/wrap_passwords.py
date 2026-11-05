"""Protect the password hashes of the former format in the database right away.

They would otherwise stay until the next login of each user, which might never
happen. Needs no password and no user has to change it. Keep a backup of the
table, an older version of this package cannot read the result. The URL of the
database comes from the environment, so it does not show up in the process list::

    SQL_DB_URL=postgresql://... python -m cone.sql.wrap_passwords
"""

from cone.sql.ugm import SQLUser
from node.ext.ugm.password import wrap_legacy_hash
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker
import os
import sys


def wrap_passwords(session):
    """Wrap the password hashes of all users.

    :param session: The SQLAlchemy session. Committing is up to the caller.
    :return: Tuple of the number of wrapped hashes, the number of users and a
        list containing the ids of users with a malformed value.
    """
    records = session.query(SQLUser).all()
    wrapped = 0
    malformed = []
    for record in records:
        if not record.password:
            continue
        try:
            value = wrap_legacy_hash(record.password)
        except ValueError:
            malformed.append(record.id)
            continue
        if value != record.password:
            record.password = value
            wrapped += 1
    return wrapped, len(records), malformed


def main():
    """Wrap the hashes in the database named by ``SQL_DB_URL``.

    :return: The exit code.
    """
    url = os.environ.get('SQL_DB_URL')
    if not url:
        print('Usage: SQL_DB_URL=... python -m cone.sql.wrap_passwords')
        return 2
    session = sessionmaker(bind=create_engine(url))()
    wrapped, total, malformed = wrap_passwords(session)
    session.commit()
    print(f'{wrapped} of {total} passwords wrapped.')
    if malformed:
        print(f'Malformed, left as they are: {", ".join(malformed)}')
        return 1
    return 0


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
