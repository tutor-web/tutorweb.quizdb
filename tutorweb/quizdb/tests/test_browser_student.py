from z3c.saconfig import Session
from zope.testing.loggingsupport import InstalledHandler

from plone.app.testing import login

from Products.CMFCore.utils import getToolByName

from tutorweb.quizdb import db
from .base import IntegrationTestCase, FunctionalTestCase
from .base import MANAGER_ID, USER_A_ID, USER_B_ID, USER_C_ID


class StudentUpdateViewTest(IntegrationTestCase):
    def setUp(self):
        """Set up a class ready for testing"""
        self.loghandlers = dict(
            sqlalchemy=InstalledHandler('sqlalchemy.engine'),
            sync=InstalledHandler('tutorweb.quizdb.browser.sync')
        )

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]

    def test_studentUpdate(self):
        """Should be able to update all student's email addresses in one go"""
        portal = self.layer['portal']

        # Login as user B and C, to get them in the DB
        login(portal, USER_A_ID)
        self.assertEqual(self.getCurrentStudent().userName, USER_A_ID)
        login(portal, USER_C_ID)
        self.assertEqual(self.getCurrentStudent().userName, USER_C_ID)

        # Change all email addresses, run update
        login(portal, MANAGER_ID)
        mtool = getToolByName(portal, 'portal_membership')
        mtool.getMemberById(USER_A_ID).setMemberProperties(dict(
            email='alfred@example.com',
        ))
        mtool.getMemberById(USER_B_ID).setMemberProperties(dict(
            email='bert@example.com',
        ))
        mtool.getMemberById(USER_C_ID).setMemberProperties(dict(
            email='catherine@example.com',
        ))
        update = portal.restrictedTraverse('quizdb-student-update').asDict(None)
        self.assertEqual(update['success'], True)

        # Email addresses have already changed, apart from B who wasn't there
        for dbStudent in Session.query(db.Student).all():
            self.assertEqual(
                'alfred@example.com' if dbStudent.userName == USER_A_ID
                else 'Betty@example.com' if dbStudent.userName == USER_B_ID
                else 'catherine@example.com',
                dbStudent.eMail,
            )
            pass

        # Set email addresses back again
        for id in [USER_A_ID, USER_B_ID, USER_C_ID]:
            mtool.getMemberById(id).setMemberProperties(dict(
                email=id + '@example.com',
            ))

    def getCurrentStudent(self):
        """Use getCurrentStudent() to create students"""
        lec = self.layer['portal']['dept1']['tut1']['lec1']
        return lec.restrictedTraverse('quizdb-sync').getCurrentStudent()
