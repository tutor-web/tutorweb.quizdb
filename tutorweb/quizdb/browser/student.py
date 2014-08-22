# import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

from sqlalchemy.sql import func
from z3c.saconfig import Session

from Products.CMFCore.utils import getToolByName

from tutorweb.quizdb import db
from .base import JSONBrowserView


class StudentUpdateView(JSONBrowserView):
    """Update all student email addresses"""

    def asDict(self):
        """For all students already in DB, update details"""
        mtool = getToolByName(self.context, 'portal_membership')
        for dbStudent in Session.query(db.Student).all():
            mb = mtool.getMemberById(dbStudent.userName)
            dbStudent.eMail = mb.getProperty('email')
        Session.flush()
        return dict(success=True)


class StudentAwardView(JSONBrowserView):
    """Show coins awarded to student"""

    def asDict(self):
        """Show coins given to student"""
        student = self.getCurrentStudent()
        vals = (Session.query(
            func.sum(db.Answer.coinsAwarded),
            func.max(db.Answer.timeEnd),
        )
            .filter(db.Answer.studentId == student.studentId)
            .filter(db.Answer.practice == False)
            .order_by(db.Answer.timeEnd)
            .first())

        return dict(
            totalAwarded=int(vals[0]),
            lastUpdate=vals[1].isoformat() if vals[1] else None,
        )
