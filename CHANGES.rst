Changes
=======

1.2.0 (unreleased)
------------------

- Remove ``cone.sql.model.UNICODE_TYPE``. It was an alias for ``str`` left
  over from Python 2 support. Use ``str`` instead.
  [rnix]

- Modernise the code ruff flags as outdated: ``u''`` prefixes, ``class
  X(object)``, ``.format()`` over f-strings. Behaviour unchanged.
  ``super(Class, self)`` is kept, see ``cone.app``.
  [rnix]

- Add ``qa.ruff`` domain to Makefile and pin the ruff rule selection in
  ``pyproject.toml``, ``make check`` runs ``ruff check``.
  [rnix]

- ``testing.SQLLayer.make_app`` passes its settings to the application. It
  handed on only the keyword arguments, so the layer never configured ``sql``
  as UGM backend and the ``cone.ugm`` integration tests ran against the file
  backend.
  [rnix]

- Add ``testing.use_transaction_manager`` test decorator.
  [rnix]

- ``cone.sql.testing`` imports ``cone.sql.ugm``. ``SQLLayer`` configures
  ``sql`` as UGM backend, but created the tables before the UGM tables were
  known, so a downstream package using the layer failed with ``no such table:
  principal``.
  [rnix]

- Fix signatures of ``Ugm.__iter__`` and ``Ugm.__delitem__``. Both took a
  superfluous argument, so iterating the UGM raised ``TypeError`` and deleting
  from it raised ``TypeError`` instead of ``NotImplementedError``.
  [rnix]

- Remove ``UsersBehavior.passwd``. It was never called,
  ``AuthenticationBehavior.passwd`` overrides it.
  [rnix]

- Add ``cone.sql.versioning``, providing append-only versioning with tombstones
  as an opt-in mixin. A change inserts a new row and supersedes its
  predecessor, a deletion inserts a grave row; the four operations
  ``create``, ``new_version``, ``tombstone`` and ``resurrect`` are the only
  write path. Comes with a ``before_flush`` guard rejecting in place mutation
  and deletion of versioned rows, ``current()``/``as_of()`` filters, a registry
  mixin providing a foreign key target for object identity, and the partial
  unique index enforcing at most one current version per object. ``SQLBase``
  and existing tables are untouched. Columns carry a ``version_`` prefix
  (``version_created``, ``version_superseded``, ``version_deleted``), so they
  do not collide with the application meaning of ``created`` and ``deleted``.
  [rnix]

- Add ``VersionedSQLTableNode`` and ``VersionedSQLRowNode`` for publishing
  versioned records. The node name is the object identity rather than the
  primary key, so it survives edits. Attribute writes are buffered and applied
  as a version when the node is called, ``__delitem__`` writes a tombstone, and
  the container resolves and lists current rows only.
  [rnix]

- Add ``UTCDateTime`` column type. Timezone aware, normalized to UTC, naive
  values rejected. PostgreSQL gets ``TIMESTAMPTZ``, SQLite fixed width ISO-8601
  text - SQLite compares text byte by byte, so a variable fraction would make
  ``ORDER BY`` sort by punctuation rather than by time.
  [rnix]

- Drop the Python 2 branch behind ``UNICODE_TYPE``, which the supported Python
  versions cannot reach. The name is kept, ``cone.sql.ugm`` and downstream
  packages import it. Remove two unused imports from ``cone.sql.testing``.
  [rnix]

- Fix ``GUID.process_result_value`` on PostgreSQL. ``load_dialect_impl`` maps the
  type to a native ``uuid`` column there, so the driver already returns a
  ``uuid.UUID`` instance. Feeding it to ``uuid.UUID()`` raised
  ``AttributeError: 'UUID' object has no attribute 'replace'`` on every read.
  Values that already are ``uuid.UUID`` are now passed through unchanged, while
  the CHAR(32) hexstring path used by the other backends keeps working.
  [rnix]


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
