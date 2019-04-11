
Changes
=======

0.2 (unreleased)
----------------

- Fix hex formatting in ``cone.sql.model.GUID.process_bind_param``.
  [rnix]

- Register SQL session to transaction manager with ``zope.sqlalchemy.register``.
  [rnix]

- Use ``pyramid_tm`` instead of ``repoze.tm2``.
  [rnix]

- Use ``pyramid_retry`` instead of ``repoze.retry``.
  [rnix]

- Upgrade to ``cone.app`` 1.0b1.
  [rnix]


0.1 (2017-03-28)
----------------

- Initial work.
  [rnix, 2017-18-01]
