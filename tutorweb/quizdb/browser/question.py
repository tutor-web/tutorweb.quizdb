import base64
import json
import logging
import urlparse
import random

from AccessControl import getSecurityManager
from zope.interface import implements
from zope.publisher.interfaces import IPublishTraverse, NotFound
from z3c.saconfig import Session
from zExceptions import BadRequest

from sqlalchemy import and_, or_
from sqlalchemy.sql.expression import func
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from Products.CMFCore import permissions

from tutorweb.quizdb import db
from tutorweb.quizdb.allocation.base import Allocation
from .base import JSONBrowserView

from ..sync.student import getStudentSettings

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)


class QuestionView(JSONBrowserView):
    """Base class: fetches questions and obsfucates"""

    def ugQuestionToJson(self, ugQn):
        """Turn a db.ugQuestion object into a JSON representation"""

        qnUri = self.request.getURL()
        if '?' in qnUri:
            qnUri = qnUri.split('?')[0]
        qnUri = qnUri + '?question_id=%s' % ugQn.ugQuestionGuid

        out = dict(
            _type='usergenerated',
            uri=qnUri,
            question_id=str(ugQn.ugQuestionGuid),
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

    def getQuestionData(self, dbQn, dbLec):
        """Fetch dict for question, obsfucating the answer"""
        out = None

        def getQuestionDict(plonePath):
            if '?' in plonePath:
                (plonePath, querystring) = plonePath.split('?', 1)
                querystring = urlparse.parse_qs(querystring)
            else:
                querystring = {}

            try:
                #NB: Unrestricted so we can see this even when direct access is banned
                dataView = self.portalObject().unrestrictedTraverse(str(plonePath) + '/@@data')
            except KeyError:
                raise NotFound(self, str(plonePath), self.request)
            return dataView.asDict(querystring)

        # Is the student requesting a particular question they've done before?
        if not out and dbQn.qnType == 'tw_questiontemplate' and 'question_id' in self.request.form and 'author_qn' not in self.request.form:
            student = self.getCurrentStudent()

            ugQn = (Session.query(db.UserGeneratedQuestion)
                .filter(db.UserGeneratedQuestion.ugQuestionGuid == self.request.form['question_id'])
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
            settings = getStudentSettings(dbLec, student)
            setting_values = dict(
                prob_template_eval=float(settings.get('prob_template_eval', 0.8)),
                cap_template_qns=int(settings.get('cap_template_qns', 5)),
                cap_template_qn_reviews=int(settings.get('cap_template_qn_reviews', 10)),
                cap_template_qn_nonsense=int(settings.get('cap_template_qn_nonsense', 10)),
            )

            # Should the user be reviewing a question?
            if self.request.form.get('author_qn', False):
                reviewQuestion = False
            elif (random.random() <= setting_values['prob_template_eval']):
                reviewQuestion = True
            elif setting_values['cap_template_qns'] > 0:
                reviewQuestion = (Session.query(db.UserGeneratedQuestion)
                    .filter(db.UserGeneratedQuestion.questionId == dbQn.questionId)
                    .filter(db.UserGeneratedQuestion.studentId == student.studentId)
                    .count()) >= setting_values['cap_template_qns']
            else:
                reviewQuestion = False

            if reviewQuestion:
                # Generate query of all irrelevant questions; either the student already reviewed it
                ugAnswerQuery = (Session.query(db.UserGeneratedAnswer.ugQuestionGuid)
                    .filter(db.UserGeneratedAnswer.studentId == student.studentId)
                )
                # ...or that question has reached it's review cap
                ugAnswerQuery = ugAnswerQuery.union(Session.query(db.UserGeneratedAnswer.ugQuestionGuid)
                    .group_by(db.UserGeneratedAnswer.ugQuestionGuid)
                    .having(or_(
                        func.count(db.UserGeneratedAnswer.ugAnswerId) >= setting_values['cap_template_qn_reviews'],
                        and_(
                            func.count(db.UserGeneratedAnswer.ugAnswerId) >= setting_values['cap_template_qn_nonsense'],
                            func.sum(db.UserGeneratedAnswer.questionRating) < 0
                        )
                    )))

                ugAnswerQuery = aliased(db.UserGeneratedAnswer, ugAnswerQuery.subquery())
                ugQn = (Session.query(db.UserGeneratedQuestion)
                    .outerjoin(ugAnswerQuery)
                    .filter(ugAnswerQuery.ugQuestionGuid == None)
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
                        .filter(db.UserGeneratedQuestion.ugQuestionGuid == self.request.form['question_id'])
                        .filter(db.UserGeneratedQuestion.questionId == dbQn.questionId)
                        .filter(db.UserGeneratedQuestion.studentId == student.studentId)
                        .filter(db.UserGeneratedQuestion.superseded == None)
                        .first())
                    if ugQn is not None:
                        # Found one, add it to question
                        out['uri'] += '&question_id=%s' % ugQn.ugQuestionGuid
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
        questionUri = self.request.getURL()
        isAdmin = self.isAdmin()

        try:
            alloc = Allocation.allocFromUri(
                uri=questionUri,
                student=self.getCurrentStudent(),
                urlBase=self.portalObject().absolute_url(),
            )
            dbQn = alloc.getQuestion(questionUri, isAdmin=isAdmin)
            if not dbQn:
                raise NotFound(self, self.questionId, self.request)
            qnData = self.getQuestionData(dbQn, alloc.dbLec)
        except (NoResultFound, MultipleResultsFound) as e:
            # Mask question plonePath
            raise NotFound(self, self.questionId, self.request)
        if isAdmin:
            qnData['path'] = dbQn.plonePath
        return qnData


class GetLectureQuestionsView(QuestionView):
    """Fetch all questions for a lecture"""
    def asDict(self, data):
        dbLec = self.getDbLecture()
        alloc = Allocation.allocFor(
            student=self.getCurrentStudent(),
            dbLec=dbLec,
            urlBase=self.portalObject().absolute_url(),
        )

        out = {}
        for questionUri, dbQn in alloc.getAllQuestions():
            try:
                out[questionUri] = self.getQuestionData(dbQn, dbLec)
            except NotFound:
                pass
        return out
