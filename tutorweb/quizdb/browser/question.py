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

        def getQuestionDict(plonePath):
            try:
                #NB: Unrestricted so we can see this even when direct access is banned
                dataView = self.portalObject().unrestrictedTraverse(str(plonePath) + '/@@data')
            except KeyError:
                raise NotFound(self, str(plonePath), self.request)
            return dataView.asDict()

        # Is the student requesting a particular question they've done before?
        if not out and dbQn.qnType == 'tw_questiontemplate' and 'question_id' in self.request.form and 'author_qn' not in self.request.form:
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
                cap_template_qns=5,
                cap_template_qn_reviews=10,
            )
            for row in (Session.query(db.LectureSetting)
                    .filter(db.LectureSetting.lectureId == dbQn.lectureId)
                    .filter(db.LectureSetting.studentId == student.studentId)
                    .filter(db.LectureSetting.key.in_(settings.keys()))):
                settings[row.key] = float(row.value)

            # Should the user be reviewing a question?
            if self.request.form.get('author_qn', False):
                reviewQuestion = False
            elif (random.random() <= settings['prob_template_eval']):
                reviewQuestion = True
            elif settings['cap_template_qns'] > 0:
                reviewQuestion = (Session.query(db.UserGeneratedQuestion)
                    .filter(db.UserGeneratedQuestion.questionId == dbQn.questionId)
                    .filter(db.UserGeneratedQuestion.studentId == student.studentId)
                    .count()) >= settings['cap_template_qns']
            else:
                reviewQuestion = False

            if reviewQuestion:
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
                    .filter(db.UserGeneratedQuestion.superseded == None)
                    .order_by(func.random())
                    .first())
                if ugQn is not None:
                    # Found one, should return it
                    out = self.ugQuestionToJson(ugQn)
                else:
                    # Don't fall back to writing questions
                    raise BadRequest("No questions for student to review")
            else:
                # Author a question
                out = getQuestionDict(dbQn.plonePath)
                qnUri = self.request.getURL()
                if '?' in qnUri:
                    qnUri = qnUri.split('?')[0]
                out['uri'] = '%s?author_qn=yes' % self.request.getURL()
                if 'question_id' in self.request.form:
                    # Trying to rewrite a question, so add in what was written before
                    ugQn = (Session.query(db.UserGeneratedQuestion)
                        .filter(db.UserGeneratedQuestion.ugQuestionId == self.request.form['question_id'])
                        .filter(db.UserGeneratedQuestion.questionId == dbQn.questionId)
                        .filter(db.UserGeneratedQuestion.studentId == student.studentId)
                        .filter(db.UserGeneratedQuestion.superseded == None)
                        .first())
                    if ugQn is not None:
                        # Found one, add it to question
                        out['uri'] += '&question_id=%d' % ugQn.ugQuestionId
                        out['student_answer'] = dict(
                            text=ugQn.text,
                            choices=[dict(
                                    answer=getattr(ugQn, 'choice_%d_answer' % i, None),
                                    correct=getattr(ugQn, 'choice_%d_correct' % i, None),
                                ) for i in range(0, 10) if getattr(ugQn, 'choice_%d_correct' % i, None) is not None],
                            explanation=ugQn.explanation
                        )
                    else:
                        raise NotFound(self, self.request.form['question_id'], self.request)

        # No custom techniques, fetch question @@data
        if not out:
            out = getQuestionDict(dbQn.plonePath)

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
            .filter(db.Allocation.active == True) \
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
