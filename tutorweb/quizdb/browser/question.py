import base64
import json

from AccessControl import getSecurityManager
from zope.interface import implements
from zope.publisher.interfaces import IPublishTraverse, NotFound
from z3c.saconfig import Session

from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from Products.CMFCore import permissions

from tutorweb.quizdb import db
from .base import JSONBrowserView


class QuestionView(JSONBrowserView):
    """Base class: fetches questions and obsfucates"""
    def getQuestionData(self, dbQn):
        """Fetch dict for question, obsfucating the answer"""
        try:
            #NB: Unrestricted so we can see this even when direct access is banned
            out = self.portalObject().unrestrictedTraverse(str(dbQn.plonePath) + '/@@data').asDict()
        except KeyError:
            raise NotFound(self, dbQn.plonePath, self.request)
        # Obsfucate answer
        if 'answer' in out:
            out['answer'] = base64.b64encode(json.dumps(out['answer']))
        return out


class GetQuestionView(QuestionView):
    """Fetched the named allocated question"""
    implements(IPublishTraverse)

    def __init__(self, context, request):
        super(QuestionView, self).__init__(context, request)
        self.questionId = None

    def publishTraverse(self, request, id):
        if self.questionId is None:
            self.questionId = id
        else:
            raise NotFound(self, id, request)
        return self

    def isAdmin(self):
        """Is the current user an admin?"""
        return getSecurityManager().checkPermission(
            permissions.ManagePortal,
            self.context,
        )

    def asDict(self):
        if self.questionId is None:
            raise NotFound(self, None, self.request)

        isAdmin = self.isAdmin()
        try:
            query = Session.query(db.Question) \
                .join(db.Allocation) \
                .filter(db.Allocation.publicId == self.questionId) \
                .filter(db.Question.active == True)
            # If not an admin, ensure we're the right user
            if not isAdmin:
                student = self.getCurrentStudent()
                query = query.filter(db.Allocation.studentId == student.studentId)
            dbQn = query.one()
        except NoResultFound:
            raise NotFound(self, self.questionId, self.request)
        except MultipleResultsFound:
            raise NotFound(self, self.questionId, self.request)

        try:
            qn = self.getQuestionData(dbQn)
        except NotFound:
            # Mask question plonePath
            raise NotFound(self, self.questionId, self.request)
        if isAdmin:
            qn['path'] = dbQn.plonePath
        return qn


class GetLectureQuestionsView(QuestionView):
    """Fetch all questions for a lecture"""
    def asDict(self):
        student = self.getCurrentStudent()

        # Get all questions from DB and their allocations
        dbAllocs = Session.query(db.Question, db.Allocation) \
            .join(db.Allocation) \
            .filter(db.Question.lectureId == self.getLectureId()) \
            .filter(db.Question.active == True) \
            .filter(db.Allocation.studentId == student.studentId) \
            .all()

        # Render each question into a dict
        portal = self.portalObject()
        out = dict()
        for (dbQn, dbAlloc) in dbAllocs:
            try:
                uri = portal.absolute_url() + '/quizdb-get-question/' + dbAlloc.publicId
                out[uri] = self.getQuestionData(dbQn)
            except NotFound:
                pass
        return out
