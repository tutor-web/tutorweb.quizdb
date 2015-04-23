Tutorweb (quiz database)
^^^^^^^^^^^^^^^^^^^^^^^^

Database application to manage tutorweb question assignment and scores.

See https://github.com/tutorweb/tutorweb.buildout for more information. 

Connnecting to unit test DB
---------------------------

During the unit tests, the database is available through::

    sqlite3 $(ls -1t /tmp/tmp*twquizdb.db | head -1)

MySQL query logging
-------------------

    SET global log_output = 'FILE';
    SET global general_log_file='/tmp/mysql_general.log';
    SET global general_log = 1;

Getting SQL to create a table
-----------------------------

Useful for upgrades, you can print out the SQL for a table using ``CreateTable``::

    >>> from sqlalchemy.schema import CreateTable
    >>> from tutorweb.quizdb import db
    >>> print CreateTable(db.Allocation.__table__).compile()
