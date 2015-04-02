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
            plQns = [RealContentListingObject(self.context)]
            dbQns = dict((x.plonePath, x) for x in Session.query(db.Question)
                .filter(db.Question.plonePath == '/'.join(self.context.getPhysicalPath()))
                .filter(db.Question.active == True))
        else:
            # TODO: Batching, optimise query
            plQns = self.context.restrictedTraverse('@@folderListing')(
                object_provides=IQuestion.__identifier__,
                sort_on="id",
            )
            dbQns = dict((x.plonePath, x) for x in Session.query(db.Question)
                .filter(db.Question.lectureId == self.getLectureId())
                .filter(db.Question.active == True))

        out = []
        for l in plQns:
            out.append(dict(
                url=l.getURL(),
                id=l.getId(),
                title=l.Title(),
            ))

            dbQn = dbQns.get(l.getPath(), None)
            if dbQn is not None:
                # Use DB answers
                out[-1]['timesAnswered'] = dbQn.timesAnswered
                out[-1]['timesCorrect'] = dbQn.timesCorrect
            else:
                # Not in DB yet, fall back to initial values
                plQn = l.getObject()
                out[-1]['timesAnswered'] = getattr(plQn, 'timesanswered', 0)
                out[-1]['timesCorrect'] = getattr(plQn, 'timescorrect', 0)
        return out
