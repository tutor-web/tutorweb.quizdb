from z3c.saconfig import Session
from zope.interface import implements, Interface

from plone.app.layout.globals.interfaces import IViewView
from plone.app.contentlisting.realobject import RealContentListingObject

from Products.Five.browser import BrowserView

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db
from .base import BrowserViewHelpers

class QuestionStatsView(BrowserView, BrowserViewHelpers):
    implements(IViewView)  # NB: This ensures "Add new..." is visible in the edit bar

    def getStats(self):
        """Get statistics for all questions in the lecture"""

        if IQuestion.providedBy(self.context):
            # Return just the current question and it's DB object
            dbQns = (Session.query(db.Question)
                .filter(db.Question.plonePath == '/'.join(self.context.getPhysicalPath()))
                .filter(db.Question.active == True)
                .order_by(db.Question.plonePath))
        else:
            # TODO: Batching, optimise query
            dbQns = (Session.query(db.Question)
                .filter(db.Question.lectures.contains(self.getDbLecture()))
                .filter(db.Question.active == True)
                .order_by(db.Question.plonePath))

        out = []
        for dbQn in dbQns:
            plonePath = str(dbQn.plonePath)
            queryString = None
            if '?' in plonePath:
                (plonePath, queryString) = plonePath.split('?', 1)
            plQn = self.portalObject().unrestrictedTraverse(plonePath)

            out.append(dict(
                url=plQn.absolute_url() + ('?%s' % queryString if queryString else ""),
                id=plQn.getId() + ('?%s' % queryString if queryString else ""),
                title=plQn.Title(),
                timesAnswered=dbQn.timesAnswered,
                timesCorrect=dbQn.timesCorrect,
            ))
        return out
