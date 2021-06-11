import calendar
import collections
import datetime
import uuid
import logging

from z3c.saconfig import Session

from sqlalchemy import and_, func
from tutorweb.quizdb import db

from App.config import getConfiguration
if getConfiguration().debug_mode:
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


def dumpIsEmpty(dump):
    """Return true iff dump has no new interesting data"""
    for k in dump.keys():
        if k in ['state', 'host']:
            # These will always contain something
            continue
        if len(dump[k]) > 0:
            return False
    return True


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
        answerId=int(stateIn.get('answerId', None) or 0),
        coinAwardId=int(stateIn.get('coinAwardId', None) or 0),
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
        lecture_global_setting=[objDict(r) for r in Session.query(db.LectureGlobalSetting)
            .join(matchingAnswers, and_(
                matchingAnswers.c.lectureId == db.LectureGlobalSetting.lectureId,
             ))
            .order_by(db.LectureGlobalSetting.lectureId, db.LectureGlobalSetting.lectureVersion, db.LectureGlobalSetting.key)],
        lecture_student_setting=[objDict(r) for r in Session.query(db.LectureStudentSetting)
            .join(matchingAnswers, and_(
                matchingAnswers.c.lectureId == db.LectureStudentSetting.lectureId,
                matchingAnswers.c.studentId == db.LectureStudentSetting.studentId,
             ))
            .order_by(db.LectureStudentSetting.lectureId, db.LectureStudentSetting.lectureVersion, db.LectureStudentSetting.studentId, db.LectureStudentSetting.key)],
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
            answerId=Session.query(func.max(db.Answer.answerId) + 1).filter(answerFilter).one()[0] or state['answerId'],
            coinAwardId=Session.query(func.max(db.CoinAward.coinAwardId) + 1).filter(coinAwardFilter).one()[0] or state['coinAwardId'],
        )
    )
