import datetime
import logging
import re
import time
import urlparse

from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import expression

from zope.publisher.interfaces import NotFound
from z3c.saconfig import Session

from tutorweb.quizdb import db

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
logger = logging.getLogger(__package__)


def getAnswerSummary(portalObj, lectureId, lectureObj, student):
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
    ) = (int(x) for x in Session.query(
        func.count(),
        func.ifnull(func.sum(db.Answer.correct), 0),
        func.ifnull(func.sum(db.Answer.practice), 0),
        func.ifnull(func.sum(expression.case([(db.Answer.practice & db.Answer.correct, 1)], else_=0)), 0),
    ).filter(db.Answer.lectureId == lectureId).filter(db.Answer.studentId == student.studentId).one())
    return dbAnsSummary


def getCoinAward(portalObj, lectureId, lectureObj, student, dbAnsSummary, a, settings):
    """How many coins does this earn a student?"""
    newGrade = a.get('grade_after', None)
    out = 0

    # Got 8 questions right
    if dbAnsSummary.gradeHighWaterMark < 5.000 and newGrade >= 5.000:
        out += round(float(settings.get('award_lecture_answered', "1000")))

    # Has the lecture just been aced?
    if dbAnsSummary.gradeHighWaterMark < 9.998 and newGrade >= 9.998:
        out += round(float(settings.get('award_lecture_aced', "10000")))

        # Fetch all sibling lectures
        siblingPaths = [
            b.getPath()
            for b
            in lectureObj.aq_parent.restrictedTraverse('@@folderListing')(portal_type='tw_lecture')
            if b.getPath() != '/'.join(lectureObj.getPhysicalPath())
        ]

        # Is every other lecture aced?
        if (Session.query(db.AnswerSummary)
                .join(db.Lecture)
                .filter(db.AnswerSummary.studentId == student.studentId)
                .filter(db.Lecture.plonePath.in_(siblingPaths))
                .filter(db.AnswerSummary.gradeHighWaterMark >= 9.998)
                .count() >= len(siblingPaths)):
            out += round(float(settings.get('award_tutorial_aced', "100000")))
    return out


def parseAnswerQueue(portalObj, lectureId, lectureObj, student, rawAnswerQueue, settings):
    # Filter nonsense out of answerQueue
    answerQueue = []
    uriSplit = re.compile('\/quizdb-get-question\/|\?')
    for a in rawAnswerQueue:
        if a.get('synced', False):
            continue
        if 'student_answer' not in a:
            continue
        if 'answer_time' not in a:
            logger.debug("Unanswered question passed to sync")
            continue
        parts = uriSplit.split(a['uri'])
        if len(parts) < 2:
            logger.warn("Question ID %s malformed" % a['uri'])
            continue
        answerQueue.append((
            parts[1],
            urlparse.parse_qs(parts[2]) if len(parts) > 2 else {},
            a,
        ))

    # Fetch all questions for allocations, locking for update
    dbQns = {}
    if len(answerQueue) > 0:
        # NB: Not checking active, since might be writing historical answers.
        for (dbQn, publicId) in (Session.query(db.Question, db.Allocation.publicId)
                .with_lockmode('update')
                .join(db.Allocation)
                .filter(db.Allocation.studentId == student.studentId)
                .filter(db.Allocation.publicId.in_(publicId for (publicId, _, _) in answerQueue))
                .all()):
            dbQns[publicId] = dbQn

    # Fetch summary
    dbAnsSummary = getAnswerSummary(portalObj, lectureId, lectureObj, student)

    for (publicId, queryString, a) in answerQueue:
        # Fetch question for allocation
        dbQn = dbQns.get(publicId, None)
        if dbQn is None:
            logger.error("No record of allocation %s for student %s" % (
                publicId,
                student.userName,
            ))
            continue

        if dbQn.qnType == 'tw_questiontemplate' and a.get('question_type', '') == 'usergenerated':
            # Evaluated a user-generated question, write it to the DB
            if 'question_id' not in queryString:
                logger.warn("Missing ID of the question being answered")
                continue

            ugAns = db.UserGeneratedAnswer(
                    studentId=student.studentId,
                    ugQuestionId=queryString['question_id'][0],
                    chosenAnswer=a['student_answer'].get('choice', None),
                    questionRating=a['student_answer'].get('rating', None),
                    comments=a['student_answer'].get('comments', ""),
                    studentGrade=a.get('grade_after', None),
            )
            Session.add(ugAns)

            # Store ID of full answer row
            Session.flush()
            a['student_answer'] = ugAns.ugAnswerId

        elif dbQn.qnType == 'tw_questiontemplate':
            if a['correct']:
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
                a['student_answer'] = ugQn.ugQuestionId

                # If this replaces an old question, note this in DB
                if 'question_id' in queryString:
                    (Session.query(db.UserGeneratedQuestion)
                        .filter(db.UserGeneratedQuestion.ugQuestionId == queryString['question_id'][0])
                        .filter(db.UserGeneratedQuestion.questionId == dbQn.questionId)
                        .filter(db.UserGeneratedQuestion.studentId == student.studentId)
                        .one()).superseded = ugQn.ugQuestionId
                    Session.flush()

            else:
                # Student skipped (and got an incorrect mark)
                a['student_answer'] = None

        else:  # A tw_latexquestion, probably
            # Check against plone to ensure student was right
            try:
                ploneQn = portalObj.unrestrictedTraverse(str(dbQn.plonePath) + '/@@data')
                a['correct'] = True if a['student_answer'] is not None and ploneQn.allChoices()[a['student_answer']]['correct'] else False
                if a['correct']:
                    dbQn.timesCorrect += 1
                dbQn.timesAnswered += 1  # NB: Do this once we know question is valid
                # TODO: Recalculate grade at this point, instead of relying on JS?
                # Write back stats to Plone
                ploneQn.updateStats(dbQn.timesAnswered, dbQn.timesCorrect)
            except (KeyError, NotFound):
                logger.error("Cannot find Plone question at %s" % dbQn.plonePath)
                continue
            except (TypeError, IndexError):
                logger.warn("Student answer %d out of range" % a['student_answer'])
                continue

        # Update student summary rows
        dbAnsSummary.lecAnswered += 1  # NB: Including practice questions is intentional
        if a.get('correct', None):
            dbAnsSummary.lecCorrect += 1
        if a.get('practice', False):
            dbAnsSummary.practiceAnswered += 1
            if a.get('correct', None):
                dbAnsSummary.practiceCorrect += 1

        # Does this earn the student any coins?
        coinsAwarded = getCoinAward(portalObj, lectureId, lectureObj, student, dbAnsSummary, a, settings)

        # Post-awards, update grade
        if a.get('grade_after', None) is not None:
            dbAnsSummary.grade = a['grade_after']
            if a['grade_after'] > dbAnsSummary.gradeHighWaterMark:
                dbAnsSummary.gradeHighWaterMark = a['grade_after']

        # Update database with this answer
        Session.add(db.Answer(
            lectureId=lectureId,
            studentId=student.studentId,
            questionId=dbQn.questionId,
            chosenAnswer=a['student_answer'],
            correct=a.get('correct', None),
            grade=a.get('grade_after', None),
            timeStart=datetime.datetime.fromtimestamp(a['quiz_time']),
            timeEnd=datetime.datetime.fromtimestamp(a['answer_time']),
            practice=a.get('practice', False),
            coinsAwarded=coinsAwarded,
        ))
        a['synced'] = True
    Session.flush()

    # Get all previous real answers and send them back.
    dbAnswers = (Session.query(db.Answer)
        .filter(db.Answer.lectureId == lectureId)
        .filter(db.Answer.studentId == student.studentId)
        .filter(db.Answer.practice == False)
        .order_by(db.Answer.timeEnd.desc())
        .all())
    out = [dict(  # NB: Not fully recreating what JS creates, but shouldn't be a problem
        correct=dbAns.correct,
        quiz_time=int(time.mktime(dbAns.timeStart.timetuple())),
        answer_time=int(time.mktime(dbAns.timeEnd.timetuple())),
        student_answer=dbAns.chosenAnswer,
        grade_after=dbAns.grade,
        synced=True,
    ) for dbAns in reversed(dbAnswers)]

    # Tell student how many questions they have answered
    if len(out) > 0:
        out[-1]['lec_answered'] = dbAnsSummary.lecAnswered
        out[-1]['lec_correct'] = dbAnsSummary.lecCorrect
        out[-1]['practice_answered'] = dbAnsSummary.practiceAnswered
        out[-1]['practice_correct'] = dbAnsSummary.practiceCorrect

    return out
