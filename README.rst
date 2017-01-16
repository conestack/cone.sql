cone.sql
========

This package provides ``SQLAlchemy`` integration in ``cone.app`` and basic
application nodes for SQL as backend.


Installation
------------

Include ``cone.sql`` to install dependencies in your application's ``setup.py``.


Configure Database and WSGI
---------------------------

Adopt your application config ini file to define database location and hook
up the related elements to the WSGI pipeline::

    ...

    [app:my_app]
    use = egg:cone.app#main

    ...

    cone.plugins =
        cone.sql
        ...

    ...

    cone.sql.dbinit.url = sqlite:///%(here)s/var/sqlite/my_db.db

    [filter:remote_addr]
    # for use behind nginx
    use = egg:cone.app#remote_addr

    [filter:tm]
    use = egg:repoze.tm2#tm
    commit_veto = repoze.tm:default_commit_veto

    [filter:session]
    use = egg:cone.sql#session
    sqlalchemy.url = sqlite:///%(here)s/var/sqlite/my_db.db

    [pipeline:main]
    pipeline =
        remote_addr
        egg:repoze.retry#retry
        tm
        session
        my_app
