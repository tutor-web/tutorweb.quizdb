import datetime
import dateutil.parser
import json
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)  #TODO:

from sqlalchemy.orm import aliased

from z3c.saconfig import Session

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db
from .base import JSONBrowserView


class SyncTutorialView(JSONBrowserView):
    def asDict(self):
        listing = self.context.restrictedTraverse('@@folderListing')(
            portal_type='tw_lecture',
        )
        return dict(
            uri=self.context.absolute_url() + '/quizdb-sync',
            title=self.context.title,
            lectures=[self.context.restrictedTraverse(l.id + '/quizdb-sync').asDict() for l in listing],
        )


class SyncLectureView(JSONBrowserView):
    def asDict(self):
        parentPath = '/'.join(self.context.getPhysicalPath())
        portalUrl = self.portalObject().absolute_url()
        student = self.getCurrentStudent()

        # Have we been handed a structure to update?
        answerQueue = []
        if self.request.getHeader('Content-Type') == 'application/json':
            self.request.stdin.seek(0)
            lecture = json.loads(self.request.stdin.read())
            answerQueue = lecture['answerQueue']

            # Get student's allocation for this lecture
            questionIds = dict(
                (dbAlloc.publicId, dbAlloc.questionId)
                for dbAlloc in Session.query(db.Allocation)
                    .join(db.Question)
                    .filter(db.Question.parentPath == parentPath)
                    .filter(db.Allocation.studentId == student.studentId)
            )

            # Insert records into DB
            for a in answerQueue:
                if a['synced']:
                    continue
                if 'student_answer' not in a:
                    continue
                if '/quizdb-get-question/' not in a['uri']:
                    logger.warn("Question ID %s malformed" % a['uri'])
                    continue
                publicId = a['uri'].split('/quizdb-get-question/', 2)[1]
                if publicId not in questionIds:
                    logger.warn("Allocation %s not in DB" % a['uri'])
                    continue
                Session.add(db.Answer(
                    studentId=student.studentId,
                    questionId=questionIds[publicId],
                    chosenAnswer=a['student_answer'],
                    timeStart=datetime.datetime.fromtimestamp(a['quiz_time']),  #TODO: Timezone?
                    timeEnd=datetime.datetime.fromtimestamp(a['answer_time']),
                ))
                a['synced'] = True
            #TODO: Update per-question records too
            Session.flush()

        # Get all plone questions, turn it into a dict by path
        listing = self.portalObject().portal_catalog.unrestrictedSearchResults(
            path={'query': '/'.join(self.context.getPhysicalPath()), 'depth': 1},
            object_provides=IQuestion.__identifier__
        )
        ploneQns = dict((l.getPath(), dict(
            plonePath=l.getPath(),
            parentPath=parentPath,
            lastUpdate=dateutil.parser.parse(l['ModificationDate']),
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
            .filter(db.Question.parentPath == parentPath) \
            .all()

        # Update / delete any existing questions
        for (dbQn, dbAlloc) in dbAllocs:
            if dbQn.plonePath in ploneQns:
                # Question already there, update lastUpdate
                #TODO: Do we do this all the time? Don't work anyway.
                # dbQn.lastUpdate = ploneQns[dbQn.plonePath]['lastUpdate']
                del ploneQns[dbQn.plonePath]
            else:
                # Question isn't in Plone, so shouldn't be in DB
                Session.delete(dbQn)

        # Add any questions missing from DB
        for qn in ploneQns.values():
            dbQn = db.Question(**qn)
            Session.add(dbQn)
            dbAllocs.append((dbQn, None))
        Session.flush()

        # Allocate any unallocated questions
        for i in xrange(len(dbAllocs)):
            if dbAllocs[i][1] is not None:
                continue
            dbAlloc = db.Allocation(
                studentId=student.studentId,
                questionId=dbAllocs[i][0].questionId,
            )
            Session.add(dbAlloc)
            dbAllocs[i] = (dbAllocs[i][0], dbAlloc)
        Session.flush()

        return dict(
            uri=self.context.absolute_url() + '/quizdb-sync',
            question_uri=self.context.absolute_url() + '/quizdb-all-questions',
            title=self.context.title,
            questions=[dict(
                uri=portalUrl + '/quizdb-get-question/' + dbAlloc.publicId,
                chosen=dbQn.timesAnswered,
                correct=dbQn.timesCorrect,
            ) for (dbQn, dbAlloc) in dbAllocs],
            histsel=(self.context.aq_parent.histsel
                     if self.context.histsel < 0
                     else self.context.histsel),
            answerQueue=answerQueue,
        )
