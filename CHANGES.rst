Changes
=======

1.1.0 (2026-02-03)
------------------

- Refactor package layout to use ``pyproject.toml`` and implicit namespace packages.
  [rnix]

- Setup Makefile.
  [lenadax]

- Run tests with pytest.
  [lenadax]


0.9 (2025-10-25)
----------------

- Pin upper versions of dependencies.
  [rnix]

- Setup Makefile.
  [lenadax]

- Run tests with pytest.
  [lenadax]


0.8 (2024-02-12)
----------------

- Initialize SQL before calling ``setUp`` of super class in ``SQLLayer.setUp``,
  which itself calls ``make_app``. This ensures ``sql.session_factory`` is
  properly set if used in a cone ``main_hook``.
  [rnix]


0.7 (2022-12-05)
----------------

- Implement ``expires`` and ``expired`` on ``cone.sql.ugm.UserBehavior``.
  Extend ``cone.sql.ugm.UgmBehavior`` by ``user_expires_attr`` which
  enables used expiration support.
  [rnix]

- Add ``TestSQLSessionFactory`` and set to ``cone.sql.session_factory`` in
  ``SQLLayer.init_sql`` if not present.
  [rnix, toalba]


0.6 (2022-10-06)
----------------

- Remove usage of ``Nodespaces`` behavior.
  [rnix]

- Replace deprecated use of ``IStorage`` by ``IMappingStorage``.
  [rnix]

- Replace deprecated use of ``Nodify`` by ``MappingNode``.
  [rnix]

- Replace deprecated use of ``Adopt`` by ``MappingAdopt``.
  [rnix]

- Replace deprecated use of ``NodeChildValidate`` by ``MappingConstraints``.
  [rnix]

- Replace deprecated use of ``allow_non_node_children`` by ``child_constraints``.
  [rnix]


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
