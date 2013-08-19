import base64
import json

from zope.interface import implements
from zope.publisher.interfaces import IPublishTraverse, NotFound
from z3c.saconfig import Session

from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from tutorweb.quizdb import db
from .base import JSONBrowserView


class QuestionView(JSONBrowserView):
    """Base class: fetches questions and obsfucates"""
    def getQuestionData(self, path):
        """Fetch dict for question, obsfucating the answer"""
        #NB: Unrestricted so we can see this even when direct access is banned
        out = self.portalObject().unrestrictedTraverse(path + '/data').asDict()
        # Obsfucate answer
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

    def asDict(self):
        if self.questionId is None:
            raise NotFound(self, None, self.request)
        student = self.getCurrentStudent()

        try:
            dbQn = Session.query(db.Question) \
                .join(db.Allocation) \
                .filter(db.Allocation.studentId == student.studentId) \
                .filter(db.Allocation.publicId == self.questionId) \
                .one()
        except NoResultFound:
            raise NotFound(self, self.questionId, self.request)
        except MultipleResultsFound:
            raise NotFound(self, self.questionId, self.request)

        return self.getQuestionData(str(dbQn.plonePath))


class GetLectureQuestionsView(QuestionView):
    """Fetch all questions for a lecture"""
    def asDict(self):
        parentPath = '/'.join(self.context.getPhysicalPath())
        student = self.getCurrentStudent()

        # Get all questions from DB and their allocations
        dbAllocs = Session.query(db.Question, db.Allocation) \
            .join(db.Allocation) \
            .filter(db.Question.parentPath == parentPath) \
            .filter(db.Allocation.studentId == student.studentId) \
            .all()

        # Render each question into a dict
        portal = self.portalObject()
        return dict((
            portal.absolute_url() + '/quizdb-get-question/' + dbAlloc.publicId,
            self.getQuestionData(str(dbQn.plonePath)),
        ) for (dbQn, dbAlloc) in dbAllocs)
