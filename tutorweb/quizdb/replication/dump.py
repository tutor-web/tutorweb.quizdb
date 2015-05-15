import calendar
import collections
import datetime
import uuid
import logging

from z3c.saconfig import Session

from sqlalchemy import and_
from tutorweb.quizdb import db

from Globals import DevelopmentMode
if DevelopmentMode:
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)


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
    matchingAnswers = (Session.query(db.Answer.lectureId, db.Answer.studentId)
        .filter(db.Answer.timeEnd.between(dateFrom, dateTo))
        .distinct()
        .subquery())
    matchingStudents = (Session.query(db.Answer.studentId)
        .filter(db.Answer.timeEnd.between(dateFrom, dateTo))
        .distinct()
        .subquery())
    matchingLectures = (Session.query(db.Answer.lectureId)
        .filter(db.Answer.timeEnd.between(dateFrom, dateTo))
        .distinct()
        .subquery())
    matchingQuestions = (Session.query(db.Answer.questionId)
        .filter(db.Answer.timeEnd.between(dateFrom, dateTo))
        .distinct()
        .subquery())
    matchingUgQuestions = (Session.query(db.Answer.ugQuestionGuid)
        .filter(db.Answer.timeEnd.between(dateFrom, dateTo))
        .distinct()
        .subquery())

    return dict(
        date_from=calendar.timegm(dateFrom.timetuple()),
        date_to=calendar.timegm(dateTo.timetuple()),
        host=[objDict(r) for r in Session.query(db.Host)],
        student=[objDict(r) for r in Session.query(db.Student)
            .join(matchingStudents, matchingStudents.c.studentId == db.Student.studentId)
            .order_by(db.Student.studentId)
            .distinct()],
        question=[dict(questionId=r.questionId, plonePath=r.plonePath) for r in Session.query(db.Question)
            .join(matchingQuestions, matchingQuestions.c.questionId == db.Question.questionId)
            .order_by(db.Question.questionId)
            .distinct()],
        lecture=[objDict(r) for r in Session.query(db.Lecture)
            .join(matchingLectures, matchingLectures.c.lectureId == db.Lecture.lectureId)
            .order_by(db.Lecture.lectureId)],
        answer=[objDict(r) for r in Session.query(db.Answer)
            .filter(db.Answer.timeEnd.between(dateFrom, dateTo))
            .order_by(db.Answer.lectureId, db.Answer.studentId, db.Answer.timeEnd)],
        # NB: Return data for all relevant lectures, regardless of host
        lecture_setting=[objDict(r) for r in Session.query(db.LectureSetting)
            .join(matchingAnswers, and_(
                matchingAnswers.c.lectureId == db.LectureSetting.lectureId,
                matchingAnswers.c.studentId == db.LectureSetting.studentId,
             ))
            .order_by(db.LectureSetting.lectureId, db.LectureSetting.studentId, db.LectureSetting.key)],
        coin_award=[objDict(r) for r in Session.query(db.CoinAward)
            .filter(db.CoinAward.awardTime.between(dateFrom, dateTo))
            .order_by(db.CoinAward.studentId, db.CoinAward.awardTime)],
        ug_question=[objDict(r) for r in Session.query(db.UserGeneratedQuestion)
            .join(matchingUgQuestions, matchingUgQuestions.c.ugQuestionGuid == db.UserGeneratedQuestion.ugQuestionGuid)
            .order_by(db.UserGeneratedQuestion.studentId, db.UserGeneratedQuestion.ugQuestionGuid)],
        ug_answer=[objDict(r) for r in Session.query(db.UserGeneratedAnswer)
            .join(matchingUgQuestions, matchingUgQuestions.c.ugQuestionGuid == db.UserGeneratedAnswer.ugQuestionGuid)
            .order_by(db.UserGeneratedAnswer.studentId, db.UserGeneratedAnswer.ugQuestionGuid)],
    )
