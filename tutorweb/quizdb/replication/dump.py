import calendar
import collections
import datetime
import uuid
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)  # TODO: Disable

from z3c.saconfig import Session

from tutorweb.quizdb import db


def dumpDateRange(dateFrom, dateTo):
    def objDict(x):
        """Turn SQLAlchemy row object into a dict"""
        def enc(o):
            if isinstance(o, datetime.datetime):
                return calendar.timegm(o.timetuple())
            if isinstance(o, uuid.UUID):
                return str(o)
            return o

        return dict(
            (c.name, enc(getattr(x, c.name)))
            for c in x.__table__.columns
        )

    def atMidnight(d, dayDelta=0):
        """Return datetime at midnight"""
        return datetime.datetime(
            year=d.year,
            month=d.month,
            day=d.day + dayDelta,
        )

    # Parse dates to nearest day
    dateFrom = atMidnight(dateFrom)
    dateTo = atMidnight(dateTo, dayDelta=1)

    return dict(
        date_from=calendar.timegm(dateFrom.timetuple()),
        date_to=calendar.timegm(dateTo.timetuple()),
        host=[objDict(r) for r in Session.query(db.Host)],
        student=[objDict(r) for r in Session.query(db.Student)
            .join(db.Answer, db.Answer.studentId == db.Student.studentId)
            .filter(db.Answer.timeEnd.between(dateFrom, dateTo))
            .order_by(db.Student.studentId)
            .distinct()],
        question=[dict(questionId=r.questionId, plonePath=r.plonePath) for r in Session.query(db.Question)
            .join(db.Answer)
            .filter(db.Answer.timeEnd.between(dateFrom, dateTo))
            .order_by(db.Question.questionId)
            .distinct()],
        lecture=[objDict(r) for r in Session.query(db.Lecture)
            .join(db.Answer, db.Answer.lectureId == db.Lecture.lectureId)
            .filter(db.Answer.timeEnd.between(dateFrom, dateTo))],
        answer=[objDict(r) for r in Session.query(db.Answer)
            .filter(db.Answer.timeEnd.between(dateFrom, dateTo))
            .order_by(db.Answer.lectureId, db.Answer.studentId, db.Answer.timeEnd)],
        # NB: Return data for all relevant lectures, regardless of host
        lecture_setting=[objDict(r) for r in Session.query(db.LectureSetting)
            .join(db.Answer, db.Answer.lectureId == db.LectureSetting.lectureId)
            .filter(db.Answer.timeEnd.between(dateFrom, dateTo))
            .order_by(db.LectureSetting.lectureId, db.LectureSetting.studentId, db.LectureSetting.key)
            .distinct()],
        coin_award=[objDict(r) for r in Session.query(db.CoinAward)
            .filter(db.CoinAward.awardTime.between(dateFrom, dateTo))
            .order_by(db.CoinAward.studentId, db.CoinAward.awardTime)],
        ug_question=[objDict(r) for r in Session.query(db.UserGeneratedQuestion)
            # TODO: This is broken, chosenAnswer has '-' in it
            .join(db.Answer, db.Answer.chosenAnswer == db.UserGeneratedQuestion.ugQuestionGuid)
            .filter(db.Answer.studentId == db.UserGeneratedQuestion.studentId)
            .filter(db.Answer.timeEnd.between(dateFrom, dateTo))],
        ug_answer=[objDict(r) for r in Session.query(db.UserGeneratedAnswer)
            .join(db.Answer, db.Answer.chosenAnswer == db.UserGeneratedAnswer.ugQuestionGuid)
            .filter(db.Answer.studentId == db.UserGeneratedAnswer.studentId)
            .filter(db.Answer.timeEnd.between(dateFrom, dateTo))],
    )
