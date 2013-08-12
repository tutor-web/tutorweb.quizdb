from zope.interface import implements
from zope.publisher.interfaces import IPublishTraverse, NotFound
from z3c.saconfig import Session

from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from Products.CMFCore.utils import getToolByName

from tutorweb.quizdb import db
from .base import JSONBrowserView


class GetQuestionView(JSONBrowserView):
    """Fetched the named allocated question"""
    implements(IPublishTraverse)

    def __init__(self, context, request):
        super(JSONBrowserView, self).__init__(context, request)
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
        except NoResultFound:
            raise NotFound(self, self.questionId, self.request)
        except MultipleResultsFound:
            raise NotFound(self, self.questionId, self.request)

        #NB: Unrestricted so we can see this even when direct access is banned
        portal = getToolByName(self.context, "portal_url").getPortalObject()
        #TODO: Where should answer obsfucation go?
        return portal.unrestrictedTraverse(str(dbQn.plonePath) + '/data') \
                     .asDict()


class GetLectureQuestionsView(JSONBrowserView):
    """Fetch all questions for a lecture"""
    def asDict(self):
        parentPath = '/'.join(self.context.getPhysicalPath())

        # Get listing of all questions, insert them in the DB if not
        # already there
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
