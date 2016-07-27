import collections

from z3c.saconfig import Session
from tutorweb.quizdb import db

from .base import JSONBrowserView

class SubscriptionView(JSONBrowserView):
    """Get the student's current subscriptions"""

    def asDict(self, data):
        """Show coins given to student"""
        student = self.getCurrentStudent()

        # Add any additional subscriptions
        if data.get('add_lec', False):
            ploneLec = self.portalObject().restrictedTraverse(self.lectureUrlToPlonePath(data['add_lec']))
            ploneTutPath = '/'.join(ploneLec.aq_parent.getPhysicalPath())
            if (Session.query(db.Subscription)
                    .filter_by(student=student)
                    .filter_by(plonePath=ploneTutPath)
                    .count()) == 0:
                Session.add(db.Subscription(
                    student=student,
                    plonePath=ploneTutPath,
                ))
            Session.flush()

        # Fish out all subscribed lectures, organised by tutorial
        subs = dict(children=[])
        for dbSub in Session.query(db.Subscription).filter_by(student=student):
            ploneTut = self.portalObject().restrictedTraverse(str(dbSub.plonePath))
            subs['children'].append(dict(
                title=ploneTut.Title(),
                children=[
                    dict(
                        uri=self.lectureObjToUrl(l.getObject()),
                        title=l.Title(),
                    )
                    for l in ploneTut.restrictedTraverse('@@folderListing')(portal_type='tw_lecture')
                ],
            ))

        return subs
