# import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
from AccessControl import Unauthorized

from z3c.saconfig import Session

from Products.CMFCore.utils import getToolByName

from tutorweb.quizdb import db
from .base import JSONBrowserView, BrowserViewHelpers


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


class StudentUpdateDetailsView(JSONBrowserView, BrowserViewHelpers):
    """Update / return all current student details"""

    def asDict(self, data):
        """Retuun user details, optionally updating first"""
        mtool = getToolByName(self.context, 'portal_membership')
        if mtool.isAnonymousUser():
            raise Unauthorized('You are not logged in')
        mb = mtool.getAuthenticatedMember()

        # If we were given any data, update existing records
        if data:
            reg_tool = getToolByName(self.context, 'portal_registration')
            newProps = {}
            for d in data:
                if d['name'] == 'fullname':
                    newProps[d['name']] = d['value']
                elif d['name'] == 'email':
                    if not reg_tool.isValidEmail(d['value']):
                        raise ValueError("Email address %s not valid" % d['value'])
                    newProps[d['name']] = d['value']
                elif d['name'] == 'accept':
                    newProps[d['name']] = True

            # Update member & fetch DB entry (to update DB)
            mb.setMemberProperties(mapping=newProps)
            self.getCurrentStudent()

        # Display current data
        return dict(
            username = mb.getUserName(),
            fullname = mb.getProperty('fullname', ''),
            email = mb.getProperty('email', ''),
            accept = mb.getProperty('accept', False)
        )
