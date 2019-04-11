cone.sql
========

Imports.

.. code-block:: pycon

    >>> from cone import sql
    >>> from pyramid.paster import get_app
    >>> import os
    >>> import shutil
    >>> import tempfile

Create temp directory containing test application config.

.. code-block:: pycon

    >>> temp_dir = tempfile.mkdtemp()
    >>> config_path = os.path.join(temp_dir, 'sql.ini')
    >>> config = """
    ... [app:my_app]
    ... use = egg:cone.app#main
    ... 
    ... cone.plugins =
    ...     cone.sql
    ... 
    ... cone.sql.dbinit.url = sqlite:///:memory:
    ... 
    ... [filter:remote_addr]
    ... # for use behind nginx
    ... use = egg:cone.app#remote_addr
    ... 
    ... [filter:tm]
    ... use = egg:repoze.tm2#tm
    ... commit_veto = repoze.tm:default_commit_veto
    ... 
    ... [filter:session]
    ... use = egg:cone.sql#session
    ... sqlalchemy.url = sqlite:///:memory:
    ... 
    ... [pipeline:main]
    ... pipeline =
    ...     remote_addr
    ...     egg:repoze.retry#retry
    ...     tm
    ...     session
    ...     my_app
    ... """

    >>> with open(config_path, 'w') as f:
    ...     f.write(config)

Create WSGI app.

.. code-block:: pycon

    >>> wsgi_app = get_app(config_path, 'main')
    >>> wsgi_app
    <cone.app.RemoteAddrFilter object at ...>

Dummy WSGI environment.

.. code-block:: pycon

    >>> environ = {
    ...     'REQUEST_METHOD': 'GET'
    ... }

Dummy ``start_response`` callback.

.. code-block:: pycon

    >>> def start_response(*args):
    ...     print args

Call WSGI app.

.. code-block:: pycon

    >>> wsgi_app(environ, start_response)
    ('200 OK', [('Content-Type', 'text/html; charset=UTF-8'), 
    ('Content-Length', '1108')], None)
    <generator object close_when_done_generator at ...>

SQL session has been hooked up to environment.

.. code-block:: pycon

    >>> environ[sql.session_key]
    <sqlalchemy.orm.session.Session object at ...>

Cleanup.

.. code-block:: pycon

    >>> shutil.rmtree(temp_dir)
