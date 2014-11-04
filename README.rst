Tutorweb (quiz database)
^^^^^^^^^^^^^^^^^^^^^^^^

Database application to manage tutorweb question assignment and scores.

See https://github.com/tutorweb/tutorweb.buildout for more information. 

Connnecting to unit test DB
---------------------------

During the unit tests, the database is available through::

    sqlite3 $(ls -1t /tmp/tmp*twquizdb.db | head -1)
