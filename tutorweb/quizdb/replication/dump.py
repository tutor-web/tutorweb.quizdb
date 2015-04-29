import calendar
import collections
import datetime
# import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

from z3c.saconfig import Session

from tutorweb.quizdb import db


def dumpDateRange(dateFrom, dateTo):
    def objDict(x, excl=None):
        """Turn SQLAlchemy row object into a dict"""
        def enc(o):
            if isinstance(o, datetime.datetime):
                return calendar.timegm(o.timetuple())
            return o

        return dict(
            (c.name, enc(getattr(x, c.name)))
            for c in x.__table__.columns
            if excl is None or c.name != excl
        )

    def tableDict(table, key):
        """Turn table into a dict based on key"""
        out = dict()
        for x in Session.query(table):
            out[getattr(x, key)] = objDict(x, excl=key)
        return out

    def toDate(d, dayDelta=0):
        """Return datetime at midnight"""
        return datetime.datetime(
            year=d.year,
            month=d.month,
            day=d.day + dayDelta,
        )

    # Put lecture-settings into a dict-dict-dict tree.
    lectureSettings = collections.defaultdict(lambda: collections.defaultdict(dict))
    for dbS in Session.query(db.LectureSetting):
        if ':' not in dbS.key:
            lectureSettings[dbS.lectureId][dbS.studentId][dbS.key] = dbS.value

    # TODO: We could join everything and get what we need in one query. Worth it?
    return dict(
        date_from=calendar.timegm(dateFrom.timetuple()),
        date_to=calendar.timegm(dateTo.timetuple()),
        host=tableDict(db.Host, 'hostId'),
        student=tableDict(db.Student, 'studentId'),
        lecture=tableDict(db.Lecture, 'lectureId'),  # NB: Return data for all hosts, might be part of a chain
        lectureSetting=lectureSettings,
        answer=[objDict(r) for r in Session.query(db.Answer)
            .filter(db.Answer.timeEnd.between(toDate(dateFrom), toDate(dateTo, 1)))],
        coin_award=[objDict(r) for r in Session.query(db.CoinAward)
            .filter(db.CoinAward.awardTime >= toDate(dateFrom))
            .filter(db.CoinAward.awardTime < toDate(dateTo, 1))],
    )
