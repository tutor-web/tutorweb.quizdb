# import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

from z3c.saconfig import Session

from Products.CMFCore.utils import getToolByName

from tutorweb.quizdb import db
from .base import JSONBrowserView


class StudentUpdateView(JSONBrowserView):
    """Update all student email addresses"""

    def asDict(self, data):
        """For all students already in DB, update details"""
        mtool = getToolByName(self.context, 'portal_membership')
        for dbStudent in Session.query(db.Student).all():
            mb = mtool.getMemberById(dbStudent.userName)
            dbStudent.eMail = mb.getProperty('email')
        Session.flush()
        return dict(success=True)
