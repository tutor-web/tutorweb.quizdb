import calendar
import collections
import datetime
import uuid
import logging

from z3c.saconfig import Session

from sqlalchemy import and_, func
from tutorweb.quizdb import db

from Globals import DevelopmentMode
if DevelopmentMode:
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)


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


def dumpData(stateIn={}):
    """
    stateIn is a Dict of the last-seen IDs we continue from
    NB: id Wrapping *shouldn't* be a problem after all:-
     * MySQL won't wrap autonum, it'll die.
     * PostgreSQL will only wrap if CYCLE is specified for the sequence
     * SQLite will wrap if there's gaps in our autonum.
    """
    # Recreate state, populating any missing entries
    state=dict(
        answerId=int(stateIn.get('answerId', 0)),
        coinAwardId=int(stateIn.get('coinAwardId', 0)),
    )
    maxVals = int(stateIn.get('maxVals', 10000))

    # NB: If answerId has skipped over maxVals values, we are in trouble.
    # However, that shouldn't happen, unless we make a mess of initalising autonums.
    answerFilter = db.Answer.answerId.between(state['answerId'], state['answerId'] + maxVals - 1)
    coinAwardFilter = db.CoinAward.coinAwardId.between(state['coinAwardId'], state['coinAwardId'] + maxVals - 1)

    matchingAnswers = (Session.query(db.Answer.lectureId, db.Answer.studentId)
        .filter(answerFilter)
        .distinct()
        .subquery())
    matchingStudents = (Session.query(db.Answer.studentId)
        .filter(answerFilter)
        .distinct()
        .subquery())
    matchingLectures = (Session.query(db.Answer.lectureId)
        .filter(answerFilter)
        .distinct()
        .subquery())
    matchingQuestions = (Session.query(db.Answer.questionId)
        .filter(answerFilter)
        .distinct()
        .subquery())
    matchingUgQuestions = (Session.query(db.Answer.ugQuestionGuid)
        .filter(answerFilter)
        .distinct()
        .subquery())

    return dict(
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
            .filter(answerFilter)
            .order_by(db.Answer.lectureId, db.Answer.studentId, db.Answer.timeEnd)],
        # NB: Return data for all relevant lectures, regardless of host
        lecture_setting=[objDict(r) for r in Session.query(db.LectureSetting)
            .join(matchingAnswers, and_(
                matchingAnswers.c.lectureId == db.LectureSetting.lectureId,
                matchingAnswers.c.studentId == db.LectureSetting.studentId,
             ))
            .order_by(db.LectureSetting.lectureId, db.LectureSetting.studentId, db.LectureSetting.key)],
        coin_award=[objDict(r) for r in Session.query(db.CoinAward)
            .filter(coinAwardFilter)
            .order_by(db.CoinAward.studentId, db.CoinAward.awardTime)],
        ug_question=[objDict(r) for r in Session.query(db.UserGeneratedQuestion)
            .join(matchingUgQuestions, matchingUgQuestions.c.ugQuestionGuid == db.UserGeneratedQuestion.ugQuestionGuid)
            .order_by(db.UserGeneratedQuestion.studentId, db.UserGeneratedQuestion.ugQuestionGuid)],
        ug_answer=[objDict(r) for r in Session.query(db.UserGeneratedAnswer)
            .join(matchingUgQuestions, matchingUgQuestions.c.ugQuestionGuid == db.UserGeneratedAnswer.ugQuestionGuid)
            .order_by(db.UserGeneratedAnswer.studentId, db.UserGeneratedAnswer.ugQuestionGuid)],
        state=dict(
            answerId=Session.query(func.max(db.Answer.answerId) + 1).filter(answerFilter).one()[0],
            coinAwardId=Session.query(func.max(db.CoinAward.coinAwardId) + 1).filter(coinAwardFilter).one()[0],
        )
    )
