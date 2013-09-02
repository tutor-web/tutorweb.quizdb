import datetime
import dateutil.parser
import json
import logging
import time

from sqlalchemy import func
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import NoResultFound

from zope.publisher.interfaces import NotFound
from z3c.saconfig import Session

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db
from .base import JSONBrowserView

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)


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
    def parseAnswerQueue(self, student, answerQueue):
        for a in answerQueue:
            if a['synced']:
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
            except KeyError, NotFound:
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
            ))
            a['synced'] = True
        Session.flush()

        # Get last 8 answers and send them back
        dbAnswers = (Session.query(db.Answer)
            .filter(db.Answer.lectureId == self.getLectureId())
            .filter(db.Answer.studentId == student.studentId)
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

        # Also tell the student how many they have answered at this point
        if len(out) > 0:
            dbTotals = (Session.query(db.Answer).add_columns(func.count())
                .filter(db.Answer.lectureId == self.getLectureId())
                .filter(db.Answer.studentId == student.studentId)
                .group_by(db.Answer.correct)
                .all())
            out[-1]['lec_answered'] = 0
            out[-1]['lec_correct'] = 0
            for t in dbTotals:
                out[-1]['lec_answered'] += t[1]
                if t[0].correct:
                    out[-1]['lec_correct'] += t[1]
        return out

    def getQuestionAllocation(self, student, questions):
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
        for (dbQn, dbAlloc) in dbAllocs:
            if dbQn.plonePath in ploneQns:
                # Already have dbQn, don't need to create it
                del ploneQns[dbQn.plonePath]
                dbQn.active = True
            else:
                # Question isn't in Plone, so deactivate in DB
                dbQn.active = False

        # Add any questions missing from DB
        for qn in ploneQns.values():
            dbQn = db.Question(**qn)
            Session.add(dbQn)
            dbAllocs.append((dbQn, None))
        Session.flush()

        # Allocate any unallocated questions
        for i in xrange(len(dbAllocs)):
            if dbAllocs[i][1] is not None:
                # Already got an allocation
                continue
            dbAlloc = db.Allocation(
                studentId=student.studentId,
                questionId=dbAllocs[i][0].questionId,
            )
            Session.add(dbAlloc)
            dbAllocs[i] = (dbAllocs[i][0], dbAlloc)
        Session.flush()

        # Return all active questions
        portalUrl = self.portalObject().absolute_url()
        return [dict(
            uri=portalUrl + '/quizdb-get-question/' + dbAlloc.publicId,
            chosen=dbQn.timesAnswered,
            correct=dbQn.timesCorrect,
        ) for (dbQn, dbAlloc) in dbAllocs if dbQn.active]

    def asDict(self):
        student = self.getCurrentStudent()

        # Have we been handed a structure to update?
        if self.request.get_header('content_length') > 0:
            # NB: Should be checking self.request.getHeader('Content-Type') ==
            # 'application/json' but zope.testbrowser cannae do that.
            self.request.stdin.seek(0)
            lecture = json.loads(self.request.stdin.read())
        else:
            lecture = dict()

        # Build lecture dict
        return dict(
            uri=self.context.absolute_url() + '/quizdb-sync',
            question_uri=self.context.absolute_url() + '/quizdb-all-questions',
            title=self.context.title,
            hist_sel=(self.context.aq_parent.histsel
                     if self.context.histsel < 0
                     else self.context.histsel),
            answerQueue=self.parseAnswerQueue(student, lecture.get('answerQueue', [])),
            questions=self.getQuestionAllocation(student, lecture.get('questions', [])),
        )
