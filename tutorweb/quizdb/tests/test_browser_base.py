from zope.testing.loggingsupport import InstalledHandler

from plone.app.testing import login

from Products.CMFCore.utils import getToolByName

from .base import IntegrationTestCase
from .base import MANAGER_ID, USER_A_ID, USER_B_ID, USER_C_ID


class JSONBrowserViewTest(IntegrationTestCase):
    def setUp(self):
        """Set up a class ready for testing"""
        self.loghandlers = dict(
            sqlalchemy=InstalledHandler('sqlalchemy.engine'),
            sync=InstalledHandler('tutorweb.quizdb.browser.sync')
        )

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]

    def test_getCurrentStudent(self):
        """Should create users, and keep email addresses up to date"""
        portal = self.layer['portal']

        # Initial call will create
        login(portal, USER_A_ID)
        st = self.getView().getCurrentStudent()
        self.assertEqual(st.userName, 'Arnold')
        self.assertEqual(st.eMail, 'Arnold@example.com')

        # Second call didn't update student
        st = self.getView().getCurrentStudent()
        self.assertEqual(st.userName, 'Arnold')
        self.assertEqual(st.eMail, 'Arnold@example.com')
        self.assertTrue(len([
            x for x in self.logs()
            if 'update student' in x.lower()
        ]) == 0)

        # Updating email address caused an update
        login(portal, MANAGER_ID)
        mtool = getToolByName(portal, 'portal_membership')
        mtool.getMemberById(USER_A_ID).setMemberProperties(dict(
            email='aaaaaarnoold@example.com',
        ))
        login(portal, USER_A_ID)
        st = self.getView().getCurrentStudent()
        self.assertEqual(st.userName, 'Arnold')
        self.assertEqual(st.eMail, 'aaaaaarnoold@example.com')
        self.assertTrue(len([
            x for x in self.logs()
            if 'update student' in x.lower()
        ]) == 1)
        mtool.getMemberById(USER_A_ID).setMemberProperties(dict(
            email=USER_A_ID + '@example.com',
        ))

        # We can return other users, right?
        login(portal, USER_B_ID)
        st = self.getView().getCurrentStudent()
        self.assertEqual(st.userName, 'Betty')
        self.assertEqual(st.eMail, 'Betty@example.com')
        login(portal, USER_C_ID)
        st = self.getView().getCurrentStudent()
        self.assertEqual(st.userName, 'Caroline')
        self.assertEqual(st.eMail, 'Caroline@example.com')

    def getView(self):
        """Look up view for class"""
        lec = self.layer['portal']['dept1']['tut1']['lec1']
        return lec.restrictedTraverse('quizdb-sync')
