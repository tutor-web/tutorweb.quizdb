import collections

from sqlalchemy.orm.exc import NoResultFound

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
            try:
                dbSub = (Session.query(db.Subscription)
                    .filter_by(student=student)
                    .filter_by(plonePath=ploneTutPath)
                    .one())
                # Already there, so make sure it's available
                dbSub.hidden = False
            except NoResultFound:
                Session.add(db.Subscription(
                    student=student,
                    plonePath=ploneTutPath,
                ))
            Session.flush()

        # Fish out all subscribed tutorials/classes, organised by tutorial
        del_lec = data['del_lec'] if 'del_lec' in data else None
        subs = dict(children=[])
        for dbSub in Session.query(db.Subscription).filter_by(student=student).filter_by(hidden=False):
            obj = self.portalObject().restrictedTraverse(str(dbSub.plonePath))
            if obj.portal_type == 'tw_tutorial':
                lectures = (l.getObject() for l in obj.restrictedTraverse('@@folderListing')(portal_type='tw_lecture'))
            elif obj.portal_type == 'tw_class':
                lectures = (l.to_object for l in obj.lectures)
            else:
                raise ValueError("Unknown portal type!")

            lectures = [dict(
                    uri=self.lectureObjToUrl(l),
                    title=l.Title(),
            ) for l in lectures]

            if next((l for l in lectures if l['uri'] == del_lec), False):
                dbSub.hidden = True
                Session.flush()
            else:
                subs['children'].append(dict(
                    title=obj.Title(),
                    children=lectures,
                ))

        return subs
