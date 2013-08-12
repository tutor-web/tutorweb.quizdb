import cgi
import dateutil.parser
import json
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG) #TODO:

from zope.interface import implements
from zope.publisher.interfaces import IPublishTraverse, NotFound

from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from z3c.saconfig import Session

from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db

class JSONBrowserView(BrowserView):
    def asDict(self):
        """Return dict to be turned into JSON"""
        raise NotImplementedError

    def __call__(self):
        try:
            out = self.asDict()
            self.request.response.setStatus(200)
            self.request.response.setHeader("Content-type", "application/json")
            return json.dumps(out)
        except Exception, ex:
            self.request.response.setStatus(500)
            self.request.response.setHeader("Content-type", "application/json")
            return json.dumps(dict(
                error= ex.__class__.__name__,
                message= str(ex),
            ))

    def getCurrentStudent(self):
        #TODO: What if anonymous?
        mb = self.context.portal_membership.getAuthenticatedMember()
        return self.getDbStudent(mb.getUserName())

    ### Database operations (move these elsewhere?)

    def getDbStudent(self, username):
        """Return the datbase student, creating if necessary"""
        try:
            return Session.query(db.Student).filter(db.Student.userName == username).one()
        except NoResultFound:
            dbstudent = db.Student(userName=username)
            Session.add(dbstudent)
            return dbstudent


class GetQuestionView(JSONBrowserView):
    """Fetched the named allocated question"""
    implements(IPublishTraverse)

    def __init__(self, context, request):
        super(BrowserView, self).__init__(context, request)
        self.questionId = None

    def publishTraverse(self, request, name):
        if self.questionId is None:
            self.questionId = name
        else:
            raise NotFound(self, name, request)
        return self

    def asDict(self):
        if self.questionId is None:
            raise NotFound(self, None, self.request)

        #TODO: Filter by logged in user?
        try:
            dbQn = Session.query(db.Question) \
                .join(db.Allocation) \
                .filter(db.Allocation.publicId == self.questionId) \
                .one()
        except NoResultFound, MultipleResultsFound:
            raise NotFound(self, self.questionId, self.request)

        #NB: Unrestricted so we can see this even when direct access is banned
        portal = getToolByName(self.context, "portal_url").getPortalObject()
        #TODO: Where should answer obsfucation go?
        return portal.unrestrictedTraverse(str(dbQn.plonePath) + '/data').asDict()


class GetLectureQuestionsView(JSONBrowserView):
    """Fetch all questions for a lecture"""
    def asDict(self):
        parentPath = '/'.join(self.context.getPhysicalPath())

        # Get listing of all questions, insert them in the DB if not already there
        student = self.getCurrentStudent()

        # Get all questions from DB and their allocations
        dbAllocs = Session.query(db.Question, db.Allocation) \
            .filter(parentPath == parentPath) \
            .filter(db.Allocation.studentId == student.studentId) \
            .join(db.Allocation) \
            .all()

        # Render each question into a dict
        #TODO: Where should answer obsfucation go?
        portal = getToolByName(self.context, "portal_url").getPortalObject()
        return dict((
            portal.absolute_url() + '/quizdb-get-question/' + dbAlloc.publicId,
            portal.unrestrictedTraverse(str(dbQn.plonePath) + '/data').asDict()
        ) for (dbQn, dbAlloc) in dbAllocs)


class SyncLectureView(JSONBrowserView):
    def asDict(self):
        parentPath = '/'.join(self.context.getPhysicalPath())
        rootUrl = self.context.restrictedTraverse('@@plone_portal_state/navigation_root_url')()

        # Get listing of all questions, insert them in the DB if not already there
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
        subquery = aliased(db.Allocation, Session.query(db.Allocation).filter(db.Allocation.studentId == student.studentId).subquery())
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
                raise NotImplementedError #TODO:

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
                studentId= student.studentId,
                questionId= dbAllocs[i][0].questionId,
            )
            Session.add(dbAlloc)
            dbAllocs[i] = (dbAllocs[i][0], dbAlloc)
        Session.flush()

        return dict(
            uri=self.context.absolute_url() + '/sync',
            title=self.context.title,
            questions=[dict(
                uri=rootUrl + '/quizdb-get-question/' + dbAlloc.publicId,
                chosen=dbQn.timesAnswered,
                correct=dbQn.timesCorrect,
            ) for (dbQn, dbAlloc) in dbAllocs],
            histsel=(self.context.aq_parent.histsel if self.context.histsel < 0 else self.context.histsel),
        )
