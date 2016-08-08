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

        # Fish out all subscribed tutorials/classes, organised by tutorial
        subs = dict(children=[])
        for (plonePath,) in Session.query(db.Subscription.plonePath).filter_by(student=student):
            obj = self.portalObject().restrictedTraverse(str(plonePath))

            if obj.portal_type == 'tw_tutorial':
                lectures = [l.getObject() for l in obj.restrictedTraverse('@@folderListing')(portal_type='tw_lecture')]
            elif obj.portal_type == 'tw_class':
                lectures = [l.to_object for l in obj.lectures]

            subs['children'].append(dict(
                id=plonePath,
                title=obj.Title(),
                children=[dict(
                    uri=self.lectureObjToUrl(l),
                    title=l.Title(),
                ) for l in lectures],
            ))

        return subs
