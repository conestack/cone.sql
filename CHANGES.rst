Changes
=======

0.5 (2021-11-08)
----------------

- Rename deprecated ``SQLPrincipalRoles.allow_non_node_childs`` to
  ``allow_non_node_children``
  [rnix]

- Add ``cache_ok`` to ``GUID`` type decorator to prevent warning with
  SQLAlchemy 1.4
  [rnix]


0.4 (2020-11-12)
----------------

- Fix typo in ``SqlUGMFactory.__init__``.
  [rnix]


0.3 (2020-07-09)
----------------

- SQL database URL setting key in ini file changed from ``cone.sql.db.url``
  to ``sql.db.url``.
  [rnix]

- Add SQL based UGM implementation.
  [zworkb, rnix]

- Patch ``maker`` on ``cone.sql.session_factory`` if present in
  ``cone.sql.testing.SQLLayer`` to ensure working session factory when running
  tests.
  [rnix]


0.2 (2020-05-30)
----------------

- Introduce ``cone.sql.SQLSessionFactory``. Gets instanciated at application
  startup as singleton at ``cone.sql.session_factory``.
  [rnix]

- SQL database URL setting key in ini file changed from ``cone.sql.dbinit.url``
  to ``cone.sql.db.url``.
  [rnix]

- SQL database URL definition is only required once in the ``app`` section of
  the ini file. ``sqlalchemy.url`` can be removed from session filter.
  [rnix]

- Add SQL based principal ACL support.
  [rnix]

- Python 3 compatibility.
  [rnix]

- Fix hex formatting in ``cone.sql.model.GUID.process_bind_param``.
  [rnix]

- Register SQL session to transaction manager with ``zope.sqlalchemy.register``.
  [rnix]

- Use ``pyramid_tm`` instead of ``repoze.tm2``. Disabled by default, must be
  enabled explicitely via ``pyramid.includes``.
  [rnix]

- Use ``pyramid_retry`` instead of ``repoze.retry``. Disabled by default, must be
  enabled explicitely via ``pyramid.includes``.
  [rnix]

- Upgrade to ``cone.app`` 1.0b1.
  [rnix]


0.1 (2017-03-28)
----------------

- Initial work.
  [rnix]
