import dateutil.parser
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)  #TODO:

from sqlalchemy.orm import aliased

from z3c.saconfig import Session

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db
from .base import JSONBrowserView


class SyncLectureView(JSONBrowserView):
    def asDict(self):
        parentPath = '/'.join(self.context.getPhysicalPath())
        rootUrl = self.context.restrictedTraverse(
            '@@plone_portal_state/navigation_root_url')()
        student = self.getCurrentStudent()

        # Get all plone questions, turn it into a dict by path
        #TODO: What about unpublished questions?
        listing = self.context.restrictedTraverse('@@folderListing')(
            object_provides=IQuestion.__identifier__,
        )
        ploneQns = dict((l.getPath(), dict(
            plonePath=l.getPath(),
            parentPath=parentPath,
            lastUpdate=dateutil.parser.parse(l.ModificationDate()),
        )) for l in listing)

        # Get all questions from DB and their allocations
        subquery = aliased(
            db.Allocation,
            Session.query(db.Allocation).filter(
                db.Allocation.studentId == student.studentId
            ).subquery(),
        )
        dbAllocs = Session.query(db.Question, subquery) \
            .filter(parentPath == parentPath) \
            .outerjoin(subquery) \
            .all()

        # Update / delete any existing questions
        for (dbQn, dbAlloc) in dbAllocs:
            if dbQn.plonePath in ploneQns:
                # Question already there, update lastUpdate
                #TODO: Do we do this all the time? Don't work anyway.
                # dbQn.lastUpdate = ploneQns[dbQn.plonePath]['lastUpdate']
                del ploneQns[dbQn.plonePath]
            else:
                # Question removed, so remove it here too
                raise NotImplementedError  #TODO:

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
                uri=rootUrl + '/quizdb-get-question/' + dbAlloc.publicId,
                chosen=dbQn.timesAnswered,
                correct=dbQn.timesCorrect,
            ) for (dbQn, dbAlloc) in dbAllocs],
            histsel=(self.context.aq_parent.histsel
                     if self.context.histsel < 0
                     else self.context.histsel),
        )
