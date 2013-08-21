import datetime
import dateutil.parser
import json
import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

from sqlalchemy.orm import aliased

from z3c.saconfig import Session

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db
from .base import JSONBrowserView


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

            # Update per-question records, gathering real question ids as we go
            questionIds = dict()
            for a in answerQueue:
                if a['synced']:
                    continue
                if 'student_answer' not in a:
                    continue
                if '/quizdb-get-question/' not in a['uri']:
                    logging.warn("Question ID %s malformed" % a['uri'])
                    continue
                a['public_id'] = a['uri'].split('/quizdb-get-question/', 2)[1]
                dbQn = (Session.query(db.Question)
                    .with_lockmode('update')
                    .join(db.Allocation)
                    .filter(db.Allocation.studentId == student.studentId)
                    .filter(db.Allocation.publicId == a['public_id'])
                    .one())
                dbQn.timesAnswered += 1

                # Find Plone question
                listing = self.portalObject().portal_catalog.unrestrictedSearchResults(
                    path=dbQn.plonePath,
                    object_provides=IQuestion.__identifier__,
                )
                if len(listing) != 1:
                    logging.error("Cannot find Plone question at %s" % dbQn.plonePath)
                    continue
                ploneQn = listing[0].getObject()

                # Check against plone to ensure student was right
                try:
                    if ploneQn.choices[a['student_answer']]['correct']:
                        dbQn.timesCorrect += 1
                except KeyError, IndexError:
                    logging.error("Student answer %d out of range" % a['student_answer'])
                    continue

                # Write back stats to Plone whilst here
                ploneQn.timesanswered = dbQn.timesAnswered
                ploneQn.timescorrect = dbQn.timesCorrect

                # Everything worked, so add private ID (and insert this data into DB)
                a['private_id'] = dbQn.questionId
            Session.flush()

            # Insert records into DB
            for a in answerQueue:
                if 'private_id' not in a:
                    continue
                Session.add(db.Answer(
                    studentId=student.studentId,
                    questionId=a['private_id'],
                    chosenAnswer=a['student_answer'],
                    timeStart=datetime.datetime.fromtimestamp(a['quiz_time']),  #TODO: Timezone?
                    timeEnd=datetime.datetime.fromtimestamp(a['answer_time']),
                ))
                a['synced'] = True
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
