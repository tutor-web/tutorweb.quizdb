import datetime
import dateutil.parser
import json
import logging
import random
import time

from sqlalchemy import func
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import NoResultFound

from AccessControl import Unauthorized
from zope.publisher.interfaces import NotFound
from z3c.saconfig import Session

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db
from .base import JSONBrowserView

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

DEFAULT_QUESTION_CAP = 100  # Maximum number of questions to assign to user


class SyncTutorialView(JSONBrowserView):
    def asDict(self):
        listing = self.context.restrictedTraverse('@@folderListing')(
            portal_type='tw_lecture',
            sort_on='id',
        )
        return dict(
            uri=self.context.absolute_url() + '/quizdb-sync',
            title=self.context.title,
            lectures=[self.context.restrictedTraverse(l.id + '/quizdb-sync').asDict() for l in listing],
        )


class SyncLectureView(JSONBrowserView):
    def getSetting(self, key, default=None):
        """Return the value for a lecture / tutorial setting"""
        for i in (self.context.settings or []):
            if i['key'] == key:
                return i['value']
        for i in (self.context.aq_parent.settings or []):
            if i['key'] == key:
                return i['value']
        return default

    def parseAnswerQueue(self, student, answerQueue):
        newGrade = None
        for a in answerQueue:
            if a.get('synced', False):
                continue
            if 'student_answer' not in a:
                continue
            if '/quizdb-get-question/' not in a['uri']:
                logger.warn("Question ID %s malformed" % a['uri'])
                continue

            # Fetch question for allocation
            publicId = a['uri'].split('/quizdb-get-question/', 2)[1]
            try:
                dbQn = (Session.query(db.Question)
                    .with_lockmode('update')
                    .join(db.Allocation)
                    .filter(db.Allocation.studentId == student.studentId)
                    .filter(db.Allocation.publicId == publicId)
                    .one())
            except NoResultFound:
                logger.error("No record of allocation %s for student %s" % (
                    publicId,
                    student.userName,
                ))
                continue
            dbQn.timesAnswered += 1

            # Check against plone to ensure student was right
            try:
                ploneQn = self.portalObject().unrestrictedTraverse(str(dbQn.plonePath) + '/@@data')
                a['correct'] = True if ploneQn.allChoices()[a['student_answer']]['correct'] else False
                if a['correct']:
                    dbQn.timesCorrect += 1
                #TODO: Recalculate grade at this point, instead of relying on JS?
                # Write back stats to Plone
                ploneQn.updateStats(dbQn.timesAnswered, dbQn.timesCorrect)
            except (KeyError, NotFound):
                logger.error("Cannot find Plone question at %s" % dbQn.plonePath)
                continue
            except (TypeError, IndexError):
                logger.warn("Student answer %d out of range" % a['student_answer'])
                continue

            # Everything worked, so add private ID and update DB
            Session.add(db.Answer(
                lectureId=self.getLectureId(),
                studentId=student.studentId,
                questionId=dbQn.questionId,
                chosenAnswer=a['student_answer'],
                correct=a['correct'],
                grade=a.get('grade_after', None),
                timeStart=datetime.datetime.fromtimestamp(a['quiz_time']),
                timeEnd=datetime.datetime.fromtimestamp(a['answer_time']),
                practice=a.get('practice', False),
            ))
            newGrade = a.get('grade_after', newGrade)
            a['synced'] = True
        Session.flush()

        # Get last 8 answers and send them back
        dbAnswers = (Session.query(db.Answer)
            .filter(db.Answer.lectureId == self.getLectureId())
            .filter(db.Answer.studentId == student.studentId)
            .filter(db.Answer.practice == False)
            .order_by(db.Answer.answerId.desc())
            .limit(8)
            .all())
        out = [dict(  # NB: Not fully recreating what JS creates, but shouldn't be a problem
            correct=dbAns.correct,
            quiz_time=int(time.mktime(dbAns.timeStart.timetuple())),
            answer_time=int(time.mktime(dbAns.timeEnd.timetuple())),
            student_answer=dbAns.chosenAnswer,
            grade_after=dbAns.grade,
            synced=True,
        ) for dbAns in reversed(dbAnswers)]

        # Fetch answerSummary row for student
        try:
            dbAnsSummary = (Session.query(db.AnswerSummary)
                .filter(db.AnswerSummary.lectureId == self.getLectureId())
                .filter(db.AnswerSummary.studentId == student.studentId)
                .one())
        except NoResultFound:
            dbAnsSummary = db.AnswerSummary(
                lectureId=self.getLectureId(),
                studentId=student.studentId,
            )
            Session.add(dbAnsSummary)

        # Update row if we need to
        if newGrade is not None:
            dbAnsSummary.grade = newGrade
            dbAnsSummary.lecAnswered = (Session.query(func.count())
                .filter(db.Answer.lectureId == self.getLectureId())
                .filter(db.Answer.studentId == student.studentId)
                .as_scalar())
            dbAnsSummary.lecCorrect = (Session.query(func.count())
                .filter(db.Answer.lectureId == self.getLectureId())
                .filter(db.Answer.studentId == student.studentId)
                .filter(db.Answer.correct == True)
                .as_scalar())
            Session.flush()

        # Tell student how many questions they have answered
        if len(out) > 0:
            out[-1]['lec_answered'] = dbAnsSummary.lecAnswered
            out[-1]['lec_correct'] = dbAnsSummary.lecCorrect

        return out

    def getQuestionAllocation(self, student, questions):
        removedQns = []

        # Get all plone questions, turn it into a dict by path
        listing = self.portalObject().portal_catalog.unrestrictedSearchResults(
            path={'query': '/'.join(self.context.getPhysicalPath()), 'depth': 1},
            object_provides=IQuestion.__identifier__
        )
        ploneQns = dict((l.getPath(), dict(
            plonePath=l.getPath(),
            lectureId=self.getLectureId(),
            lastUpdate=dateutil.parser.parse(l['ModificationDate']),
            timesAnswered=l.getObject().timesanswered,  #TODO: Don't make object twice
            timesCorrect=l.getObject().timescorrect,
        )) for l in listing)

        # Get all questions from DB and their allocations
        subquery = aliased(
            db.Allocation,
            Session.query(db.Allocation).filter(
                db.Allocation.studentId == student.studentId
            ).subquery(),
        )
        dbAllocs = Session.query(db.Question, subquery) \
            .outerjoin(subquery) \
            .filter(db.Question.lectureId == self.getLectureId()) \
            .all()

        # Update / delete any existing questions
        usedAllocs = []
        spareAllocs = []
        for (i, (dbQn, dbAlloc)) in enumerate(dbAllocs):
            if dbQn.plonePath in ploneQns:
                # Already have dbQn, don't need to create it
                del ploneQns[dbQn.plonePath]
                dbQn.active = True
                if dbAlloc is not None:
                    usedAllocs.append(i)
                else:
                    spareAllocs.append(i)
            else:
                # Question isn't in Plone, so deactivate in DB
                dbQn.active = False
                if dbAlloc:
                    # Remove allocation, so users don't take this question any more
                    removedQns.append(dbAlloc.publicId)
                    dbAllocs[i] = (dbQn, None)

        # Add any questions missing from DB
        for qn in ploneQns.values():
            dbQn = db.Question(**qn)
            Session.add(dbQn)
            spareAllocs.append(len(dbAllocs))
            dbAllocs.append((dbQn, None))
        Session.flush()

        # Count questions that aren't allocated, and allocate more if needed
        neededAllocs = min(
            int(self.getSetting('question_cap', DEFAULT_QUESTION_CAP)),
            len(usedAllocs) + len(spareAllocs),
        ) - len(usedAllocs)
        if neededAllocs > 0:
            # Need more questions, so assign randomly
            for i in random.sample(spareAllocs, neededAllocs):
                dbAlloc = db.Allocation(
                    studentId=student.studentId,
                    questionId=dbAllocs[i][0].questionId,
                )
                Session.add(dbAlloc)
                dbAllocs[i] = (dbAllocs[i][0], dbAlloc)
        elif neededAllocs < 0:
            # Need less questions
            for i in random.sample(usedAllocs, abs(neededAllocs)):
                removedQns.append(dbAllocs[i][1].publicId)
                Session.delete(dbAllocs[i][1])  # NB: Should probably mark as deleted instead
                dbAllocs[i] = (dbAllocs[i][0], None)
        Session.flush()

        # Return all active questions
        portalUrl = self.portalObject().absolute_url()
        return (
            [dict(
                uri=portalUrl + '/quizdb-get-question/' + dbAlloc.publicId,
                chosen=dbQn.timesAnswered,
                correct=dbQn.timesCorrect,
            ) for (dbQn, dbAlloc) in dbAllocs if dbAlloc is not None],
            [portalUrl + '/quizdb-get-question/' + id for id in removedQns],
        )

    def asDict(self):
        student = self.getCurrentStudent()

        # Have we been handed a structure to update?
        if self.request.get_header('content_length') > 0:
            # NB: Should be checking self.request.getHeader('Content-Type') ==
            # 'application/json' but zope.testbrowser cannae do that.
            self.request.stdin.seek(0)
            lecture = json.loads(self.request.stdin.read())
            if lecture.get('user', None) and lecture['user'] != student.userName:
                raise Unauthorized('Quiz for user ' + lecture['user'])
        else:
            lecture = dict()

        # Build lecture dict
        (questions, removedQuestions) = self.getQuestionAllocation(student, lecture.get('questions', []))
        return dict(
            uri=self.context.absolute_url() + '/quizdb-sync',
            user=student.userName,
            question_uri=self.context.absolute_url() + '/quizdb-all-questions',
            title=self.context.title,
            settings=dict(
                (i['key'], i['value'])
                for i
                in (self.context.aq_parent.settings or []) + (self.context.settings or [])
            ),
            answerQueue=self.parseAnswerQueue(student, lecture.get('answerQueue', [])),
            questions=questions,
            removed_questions=removedQuestions,
        )
