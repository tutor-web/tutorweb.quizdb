import base64
import json
import logging
import random

from AccessControl import getSecurityManager
from zope.interface import implements
from zope.publisher.interfaces import IPublishTraverse, NotFound
from z3c.saconfig import Session
from zExceptions import BadRequest

from sqlalchemy.sql.expression import func
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from Products.CMFCore import permissions

from tutorweb.quizdb import db
from .base import JSONBrowserView

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)


class QuestionView(JSONBrowserView):
    """Base class: fetches questions and obsfucates"""

    def ugQuestionToJson(self, ugQn):
        """Turn a db.ugQuestion object into a JSON representation"""

        qnUri = self.request.getURL()
        if '?' in qnUri:
            qnUri = qnUri.split('?')[0]
        qnUri = qnUri + '?question_id=%d' % ugQn.ugQuestionId

        out = dict(
            _type='usergenerated',
            uri=qnUri,
            question_id=ugQn.ugQuestionId,
            text=self.texToHTML(ugQn.text),
            choices=[],
            shuffle=[],
            answer=dict(
                explanation=self.texToHTML(ugQn.explanation),
                correct=[],
            )
        )
        for i in range(0, 10):
            ans = getattr(ugQn, 'choice_%d_answer' % i, None)
            corr = getattr(ugQn, 'choice_%d_correct' % i, None)
            if ans is not None:
                out['choices'].append(self.texToHTML(ans))
                out['shuffle'].append(i)  # Shuffle everything
            if corr:
                out['answer']['correct'].append(i)
        return out

    def getQuestionData(self, dbQn):
        """Fetch dict for question, obsfucating the answer"""
        out = None

        # Is the student requesting a particular question they've done before?
        if not out and dbQn.qnType == 'tw_questiontemplate' and 'question_id' in self.request.form:
            student = self.getCurrentStudent()

            ugQn = (Session.query(db.UserGeneratedQuestion)
                .filter(db.UserGeneratedQuestion.ugQuestionId == self.request.form['question_id'])
                .filter(db.UserGeneratedQuestion.questionId == dbQn.questionId)
                .filter(db.UserGeneratedQuestion.studentId != student.studentId)
                .first())
            if ugQn is not None:
                # Found one, should return it
                out = self.ugQuestionToJson(ugQn)
            else:
                raise NotFound(self, self.request.form['question_id'], self.request)

        # If a questiontemplate, might want a student to evaluate a question
        if not out and dbQn.qnType == 'tw_questiontemplate':
            student = self.getCurrentStudent()

            # Fetch value of required settings
            settings = dict(
                prob_template_eval=0.8,
                cap_template_qns=0,
                cap_template_qn_reviews=5,
            )
            for row in (Session.query(db.LectureSetting)
                    .filter(db.LectureSetting.lectureId == dbQn.lectureId)
                    .filter(db.LectureSetting.studentId == student.studentId)
                    .filter(db.LectureSetting.key.in_(settings.keys()))):
                settings[row.key] = float(row.value)

            # Has the user answered enough questions aready?
            if settings['cap_template_qns'] > 0:
                hadFill = (Session.query(db.UserGeneratedQuestion)
                    .filter(db.UserGeneratedQuestion.questionId == dbQn.questionId)
                    .filter(db.UserGeneratedQuestion.studentId == student.studentId)
                    .count()) >= settings['cap_template_qns']
            else:
                hadFill = False

            if hadFill or (random.random() <= settings['prob_template_eval']):
                # Try and find a user-generated question that student hasn't answered before
                ugAnswerQuery = aliased(db.UserGeneratedAnswer, (Session.query(db.UserGeneratedAnswer.ugQuestionId)
                    .filter(db.UserGeneratedAnswer.studentId == student.studentId)
                ).union(Session.query(db.UserGeneratedAnswer.ugQuestionId)
                    .group_by(db.UserGeneratedAnswer.ugQuestionId)
                    .having(func.count(db.UserGeneratedAnswer.ugAnswerId) >= settings['cap_template_qn_reviews'])).subquery())

                ugQn = (Session.query(db.UserGeneratedQuestion)
                    .outerjoin(ugAnswerQuery)
                    .filter(ugAnswerQuery.ugQuestionId == None)
                    .filter(db.UserGeneratedQuestion.questionId == dbQn.questionId)
                    .filter(db.UserGeneratedQuestion.studentId != student.studentId)
                    .order_by(func.random())
                    .first())
                if ugQn is not None:
                    # Found one, should return it
                    out = self.ugQuestionToJson(ugQn)
                elif hadFill:
                    # Don't fall back to writing questions
                    raise BadRequest("User has written %d questions already" % settings['cap_template_qns'])

        # No custom techniques, fetch question @@data
        if not out:
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

    def asDict(self, data):
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
    def asDict(self, data):
        student = self.getCurrentStudent()

        # Get all questions from DB and their allocations
        dbAllocs = Session.query(db.Question, db.Allocation) \
            .join(db.Allocation) \
            .filter(db.Question.lectureId == self.getLectureId()) \
            .filter(db.Question.active == True) \
            .filter(db.Allocation.studentId == student.studentId) \
            .filter(db.Question.qnType != 'tw_questiontemplate') \
            .all() # NB: qnType != '...' ~== online_only = false

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
