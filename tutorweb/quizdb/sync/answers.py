import calendar
import datetime
import json
import logging
import random
import re
import time
import urlparse

from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import expression

from zope.publisher.interfaces import NotFound
from z3c.saconfig import Session

from tutorweb.quizdb import db
from tutorweb.quizdb.allocation.base import Allocation

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
logger = logging.getLogger(__package__)


def getAnswerSummary(lectureId, student):
    """Fetch answerSummary row for student"""
    try:
        dbAnsSummary = (Session.query(db.AnswerSummary)
            .with_lockmode('update')
            .filter(db.AnswerSummary.lectureId == lectureId)
            .filter(db.AnswerSummary.studentId == student.studentId)
            .one())
    except NoResultFound:
        dbAnsSummary = db.AnswerSummary(
            lectureId=lectureId,
            studentId=student.studentId,
            grade=0,
        )
        Session.add(dbAnsSummary)

    # Update based on answer table
    (
        dbAnsSummary.lecAnswered,
        dbAnsSummary.lecCorrect,
        dbAnsSummary.practiceAnswered,
        dbAnsSummary.practiceCorrect,
        maxTimeEnd,
    ) = Session.query(
        func.count(),
        func.ifnull(func.sum(db.Answer.correct), 0),
        func.ifnull(func.sum(db.Answer.practice), 0),
        func.ifnull(func.sum(expression.case([(db.Answer.practice & db.Answer.correct, 1)], else_=0)), 0),
        func.max(db.Answer.timeEnd),
    ).filter(db.Answer.lectureId == lectureId).filter(db.Answer.studentId == student.studentId).one()

    dbAnsSummary.lecAnswered = int(dbAnsSummary.lecAnswered)
    dbAnsSummary.lecCorrect = int(dbAnsSummary.lecCorrect)
    dbAnsSummary.practiceAnswered = int(dbAnsSummary.practiceAnswered)
    dbAnsSummary.practiceCorrect = int(dbAnsSummary.practiceCorrect)
    if not maxTimeEnd:
        maxTimeEnd = datetime.datetime.utcfromtimestamp(0)

    return (dbAnsSummary, maxTimeEnd)


def getCoinAward(dbLec, student, dbAnsSummary, dbQn, a, settings):
    """How many coins does this earn a student?"""
    def crossedGradeBoundary(boundary):
        """True iff student has crossed grade boundary for the first time"""
        return dbAnsSummary.gradeHighWaterMark < boundary and newGrade >= boundary

    newGrade = a.get('grade_after', None)
    out = 0

    # Are they ready to tutor this lecture?
    if 'chat_competent_grade' in settings and crossedGradeBoundary(settings['chat_competent_grade']):
        tutor = Session.query(db.Tutor).get(student.studentId)
        if tutor is None:
            tutor = db.Tutor(
                tutorId=student.studentId,
                name="tutor-%d" % random.randrange(1000, 9999),
            )
            Session.add(tutor)
        tutor.competentLectures.append(dbLec)
        Session.flush()

    # Got 8 questions right
    if crossedGradeBoundary(5.000):
        out += round(float(settings.get('award_lecture_answered', "1000")))

    # Has the lecture just been aced?
    if crossedGradeBoundary(9.750):
        out += round(float(settings.get('award_lecture_aced', "10000")))

        # Is every other lecture aced?
        # TODO: Bit ugly relying on plonePath structure here
        siblingLectures = [x[0] for x in Session.query(db.Lecture.lectureId)
            .filter(db.Lecture.hostId == dbLec.hostId)
            .filter(db.Lecture.lectureId != dbLec.lectureId)
            .filter(db.Lecture.plonePath.startswith(re.sub(r'/[^/]+/?$', '/', dbLec.plonePath)))
            .all()]

        if (Session.query(db.AnswerSummary)
                .join(db.Lecture)
                .filter(db.Lecture.lectureId.in_(siblingLectures))
                .filter(db.AnswerSummary.studentId == student.studentId)
                .filter(db.AnswerSummary.gradeHighWaterMark >= 9.750)
                .count() >= len(siblingLectures)):
            out += round(float(settings.get('award_tutorial_aced', "100000")))

    # Is this a review of a template question?
    if dbQn.qnType == 'tw_questiontemplate' and a.get('question_type', '') == 'usergenerated':
        # Did they grade it as 50 or more?
        ugAns = (Session.query(db.UserGeneratedAnswer)
            .filter(db.UserGeneratedAnswer.ugAnswerId == a['student_answer']['uganswer_id'])
            .filter(db.UserGeneratedAnswer.studentId == student.studentId)
            .one())
        if ugAns.questionRating >= 50:
            # Are the majority of reviews positive?
            if (Session.query(db.UserGeneratedAnswer)
                    .filter(db.UserGeneratedAnswer.ugQuestionGuid == ugAns.ugQuestionGuid)
                    .filter(db.UserGeneratedAnswer.questionRating >= 50)
                    .count()) >= round(float(settings.get('cap_template_qn_reviews', '10')) / 2):
                # Has the author received an award for this question yet?
                ugQn = (Session.query(db.UserGeneratedQuestion) # The question student answered
                    .filter(db.UserGeneratedQuestion.ugQuestionGuid == ugAns.ugQuestionGuid)
                    .one())
                ugQnAns = (Session.query(db.Answer)  # The Answer row of the original question
                    .filter(db.Answer.questionId == dbQn.questionId)
                    .filter(db.Answer.studentId == ugQn.studentId)
                    .filter(db.Answer.ugQuestionGuid == ugQn.ugQuestionGuid)
                    .one())
                if ugQnAns.coinsAwarded == 0:
                    # Has the author of the ugQuestion already received award_templateqn_aced the maximum number of times?
                    allQnsAwardedCoins = (Session.query(func.count(db.Answer.answerId))
                        .join(db.Question)
                        .filter(db.Answer.lectureId == ugQnAns.lectureId)
                        .filter(db.Answer.studentId == ugQnAns.studentId)
                        .filter(db.Question.qnType == 'tw_questiontemplate')
                        .filter(db.Answer.coinsAwarded > 0)
                        .one())[0]
                    # NB: Technically we should be using the other student's cap_template_qns. Meh.
                    if allQnsAwardedCoins < int(settings.get('cap_template_qns', '5')):
                        # Finally, update the original question a coin award
                        ugQnAns.coinsAwarded = float(settings.get('award_templateqn_aced', "10000"))

    return out


def parseAnswerQueue(dbLec, lectureObj, student, rawAnswerQueue, settings):
    alloc = Allocation.allocFor(
        student=student,
        dbLec=dbLec,
        urlBase=lectureObj.portal_url.getPortalObject().absolute_url(),
    )

    # Filter nonsense out of answerQueue
    answerQueue = []
    for a in rawAnswerQueue:
        if a.get('synced', False):
            continue
        if 'student_answer' not in a:
            continue
        if 'answer_time' not in a:
            logger.debug("Unanswered question passed to sync")
            continue
        parts = a['uri'].split('?', 1)
        answerQueue.append((
            parts[0],
            urlparse.parse_qs(parts[1]) if len(parts) > 1 else {},
            a,
        ))

    # Lock answers for this lecture/student, to stop any concurrent updates
    answerRows = {}
    for questionId, timeEnd in (Session.query(db.Answer.questionId, db.Answer.timeEnd)
            .filter(db.Answer.studentId == student.studentId)
            .filter(db.Answer.lectureId == dbLec.lectureId)
            .with_lockmode('update')):  # NB: FOR UPDATE gets us a fresh view of the data, SELECT doesn't necessarily? Who knows.
        answerRows['%d:%d' % (questionId, calendar.timegm(timeEnd.timetuple()))] = True

    dbQns = dict(alloc.getQuestions(
        uris=[uri for (uri, _, _) in answerQueue],
        lockForUpdate=True,
        active=None,  # NB: Might be writing historical answers
    ))

    for (questionUri, queryString, a) in answerQueue:
        # We have work to do, so get/create the summary
        # NB: On intial sync we do lots of lectures at once, creating the entry at this
        # point is wasted effort, and a cause of deadlocks as we try to sync whole tutorial
        try:
            dbAnsSummary
        except NameError:
            (dbAnsSummary, maxTimeEnd) = getAnswerSummary(dbLec.lectureId, student)

        # Fetch question for allocation
        dbQn = dbQns.get(questionUri, None)
        if dbQn is None:
            logger.error("No record of allocation %s for student %s" % (
                questionUri,
                student.userName,
            ))
            continue

        # Does this answer already exist in DB? if so, ignore it.
        if '%d:%d' % (dbQn.questionId, a['answer_time']) in answerRows:
            logger.debug("Ignoring answer for question %d at time %d --- already got one",
                dbQn.questionId,
                a['answer_time'],
            )
            continue
        else:
            answerRows['%d:%d' % (dbQn.questionId, a['answer_time'])] = True

        if dbQn.qnType == 'tw_questiontemplate' and a.get('question_type', '') == 'usergenerated':
            # Evaluated a user-generated question, write it to the DB
            if 'question_id' not in queryString:
                logger.warn("Missing ID of the question being answered")
                continue

            # Find matching ugQn, to make sure there is such a thing
            try:
                ugQn = (Session.query(db.UserGeneratedQuestion)
                    .filter(db.UserGeneratedQuestion.questionId == dbQn.questionId)
                    .filter(db.UserGeneratedQuestion.ugQuestionGuid == queryString['question_id'][0])
                    .one())
            except NoResultFound:
                raise ValueError("Cannot find matching question for %s" % queryString['question_id'][0])
            ugAns = db.UserGeneratedAnswer(
                    studentId=student.studentId,
                    ugQuestionGuid=ugQn.ugQuestionGuid,
                    chosenAnswer=a['student_answer'].get('choice', None),
                    questionRating=a['student_answer'].get('rating', None),
                    comments=a['student_answer'].get('comments', ""),
                    studentGrade=a.get('grade_after', None),
            )
            Session.add(ugAns)
            Session.flush()

            # Store GUID of question reviewed
            a['student_answer'] = dict(
                uganswer_id=ugAns.ugAnswerId,
                question_id=ugQn.ugQuestionGuid,
            )

        elif dbQn.qnType == 'tw_questiontemplate':
            if a.get('student_answer', None) and a['student_answer'].get('text', None):
                # Write question to database
                ugQn = db.UserGeneratedQuestion(
                    studentId=student.studentId,
                    questionId=dbQn.questionId,
                    text=a['student_answer']['text'],
                    explanation=a['student_answer']['explanation'],
                )
                for i, c in enumerate(a['student_answer']['choices']):
                    setattr(ugQn, 'choice_%d_answer' % i, c['answer'])
                    setattr(ugQn, 'choice_%d_correct' % i, c['correct'])
                Session.add(ugQn)

                # student_answer should contain the ID of our answer
                Session.flush()
                a['student_answer'] = dict(question_id=ugQn.ugQuestionGuid)

                # If this replaces an old question, note this in DB
                if 'question_id' in queryString:
                    dbUgQn = (Session.query(db.UserGeneratedQuestion)
                        .filter(db.UserGeneratedQuestion.ugQuestionGuid == queryString['question_id'][0])
                        .one())
                    a['correct'] = None # NB: Can't award yourself infinite corrects
                    (Session.query(db.UserGeneratedQuestion)
                        .filter(db.UserGeneratedQuestion.ugQuestionId == dbUgQn.ugQuestionId)
                        .filter(db.UserGeneratedQuestion.questionId == dbQn.questionId)
                        .filter(db.UserGeneratedQuestion.studentId == student.studentId)
                        .one()).superseded = ugQn.ugQuestionGuid
                    Session.flush()
                else:
                    a['correct'] = True

            elif 'question_id' in queryString:
                # Student tried to rewrite question, but skipped
                a['correct'] = None
                a['student_answer'] = None
            else:
                # Student skipped (and got an incorrect mark)
                a['correct'] = False
                a['student_answer'] = None

        else:  # A tw_latexquestion, probably
            # Check against plone to ensure student was right
            if a['student_answer'] is None:
                a['correct'] = False
            elif not(isinstance(a['student_answer'], int)):
                logger.warn("Student answer %s out of range" % a['student_answer'])
                continue
            else:
                a['correct'] = a['student_answer'] in json.loads(dbQn.correctChoices)
                if a['correct']:
                    dbQn.timesCorrect += 1
            dbQn.timesAnswered += 1  # NB: Do this once we know question is valid

        # Update student summary rows
        dbAnsSummary.lecAnswered += 1  # NB: Including practice questions is intentional
        if a.get('correct', None):
            dbAnsSummary.lecCorrect += 1
        if a.get('practice', False):
            dbAnsSummary.practiceAnswered += 1
            if a.get('correct', None):
                dbAnsSummary.practiceCorrect += 1

        # Does this earn the student any coins?
        coinsAwarded = getCoinAward(dbLec, student, dbAnsSummary, dbQn, a, settings)

        # Post-awards, update grade
        # NB: We're ignoring practice grades because a bug elsewhere is causing students to have 0
        # grades after returning to tutorweb after ~24hours and taking a practice question.
        if not(a.get('practice', False)) and a.get('grade_after', None) is not None:
            if datetime.datetime.utcfromtimestamp(a['answer_time']) > maxTimeEnd:
                dbAnsSummary.grade = a['grade_after']
            if a['grade_after'] > dbAnsSummary.gradeHighWaterMark:
                dbAnsSummary.gradeHighWaterMark = a['grade_after']

        # Update database with this answer
        Session.add(db.Answer(
            lectureId=dbLec.lectureId,
            studentId=student.studentId,
            questionId=dbQn.questionId,
            chosenAnswer=-1 if isinstance(a['student_answer'], dict) else a['student_answer'],
            correct=a.get('correct', None),
            grade=a.get('grade_after', None),
            timeStart=datetime.datetime.utcfromtimestamp(a['quiz_time']),
            timeEnd=datetime.datetime.utcfromtimestamp(a['answer_time']),
            practice=a.get('practice', False),
            coinsAwarded=coinsAwarded,
            ugQuestionGuid=a['student_answer'].get('question_id', None) if isinstance(a['student_answer'], dict) else None,
        ))
        a['synced'] = True
    Session.flush()

    # Get all previous real answers and send them back.
    dbAnswers = (Session.query(db.Answer)
        .filter(db.Answer.lectureId == dbLec.lectureId)
        .filter(db.Answer.studentId == student.studentId)
        .filter(db.Answer.practice == False)
        .order_by(db.Answer.timeEnd.desc())
        .with_lockmode('update')  # NB: Use FOR UPDATE, as otherwise we might get the table state at the start of the transaction
        .all())
    out = [dict(  # NB: Not fully recreating what JS creates, but shouldn't be a problem
        correct=dbAns.correct,
        quiz_time=calendar.timegm(dbAns.timeStart.timetuple()),
        answer_time=calendar.timegm(dbAns.timeEnd.timetuple()),
        student_answer=dict(question_id=str(dbAns.ugQuestionGuid)) if dbAns.ugQuestionGuid
                  else dbAns.chosenAnswer,
        grade_after=dbAns.grade,
        coins_awarded=dbAns.coinsAwarded,
        synced=True,
    ) for dbAns in reversed(dbAnswers)]

    return out
