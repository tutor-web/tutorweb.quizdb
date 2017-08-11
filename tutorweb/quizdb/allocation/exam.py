import re
import urllib2

from z3c.saconfig import Session

from tutorweb.quizdb import db
from .base import Allocation as BaseAllocation


class ExamAllocation(BaseAllocation):
    def _questionUrl(self, dbQn):
        return u'%s/quizdb-get-question/%d:%s' % (
            self.urlBase,
            self.dbLec.lectureId,
            dbQn.plonePath.rsplit('/', 1)[-1],
        )

    def _decomposeUrl(self, url):
        url = urllib2.unquote(url.rsplit('/', 1)[-1])
        m = re.match(r'(\d+):(.*)$', url)
        if m:
            return dict(
                lectureId=int(m.group(1)),
                questionId=m.group(2),
            )
        return None

    def getQuestions(self, uris=None, lockForUpdate=False, isAdmin=False, active=True):
        query = Session.query(db.Question).order_by(db.Question.plonePath)
        query = query.filter(db.Question.lectures.contains(self.dbLec))
        # TODO: If you've already answered a question, not allowed to answer it again
        # TODO: Restrict right down to only returning the next question?

        if uris is not None:
            query = query.filter(db.Question.plonePath.in_(
                self.dbLec.plonePath + '/' + self._decomposeUrl(u)['questionId'] for u in uris
            ))
        else:
            query = query.filter(db.Question.onlineOnly == False)

        if lockForUpdate:
            query = query.with_lockmode('update')

        if active is not None:
            query = query.filter(db.Question.active == active)

        for dbQn in query:
            yield (self._questionUrl(dbQn), dbQn)

    def updateAllocation(self, settings, question_cap=0):
        # There isn't an allocation, just return all the questions
        for qnUrl, qn in self.getQuestions():
            yield (qnUrl, self.publicQnType(qn), qn)
