from zExceptions import Redirect

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

    def test_getDbHost(self):
        """Should get current host along with a key"""
        import socket
        portal = self.layer['portal']

        # dbHost should be current host, and have random key
        dbHost = self.getView().getDbHost()
        self.assertEqual(dbHost.fqdn, socket.getfqdn())
        self.assertEqual(len(dbHost.hostKey), 32)

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

        # User cannot get a quiz without accepting terms
        login(portal, MANAGER_ID)
        mtool = getToolByName(portal, 'portal_membership')
        mtool.getMemberById(USER_A_ID).setMemberProperties(dict(
            accept=False,
        ))
        login(portal, USER_A_ID)
        with self.assertRaisesRegexp(Redirect, '@@personal-information'):
            st = self.getView().getCurrentStudent()
        login(portal, MANAGER_ID)
        mtool = getToolByName(portal, 'portal_membership')
        mtool.getMemberById(USER_A_ID).setMemberProperties(dict(
            accept=True,
        ))
        login(portal, USER_A_ID)

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

    def test_getDbLecture(self):
        """Should get current lecture object"""
        import socket
        portal = self.layer['portal']

        # By default uses traversal to find lecture
        dbLec = self.getView().getDbLecture()
        dbHost = self.getView().getDbHost()
        self.assertEqual(dbLec.hostId, dbHost.hostId)
        self.assertEqual(dbLec.plonePath, '/plone/dept1/tut1/lec1')

        # Can use a string too
        dbLec = self.getView().getDbLecture("http://some:host/dept1/tut1/lec2")
        self.assertEqual(dbLec.hostId, dbHost.hostId)
        self.assertEqual(dbLec.plonePath, '/plone/dept1/tut1/lec2')

        # Variations work, and get the same object
        dbLec = self.getView().getDbLecture("http://some:host/dept1/tut1/lec1/@@quizdb-sync")
        self.assertEqual(dbLec.hostId, dbHost.hostId)
        self.assertEqual(dbLec.plonePath, '/plone/dept1/tut1/lec1')
        dbLec = self.getView().getDbLecture("http://host/plone/dept1/tut1/lec2/@@quizdb-sync")
        self.assertEqual(dbLec.hostId, dbHost.hostId)
        self.assertEqual(dbLec.plonePath, '/plone/dept1/tut1/lec2')
        dbLec = self.getView().getDbLecture("https://host/plone/dept1/tut1/lec2/@@quizdb-sync")
        self.assertEqual(dbLec.hostId, dbHost.hostId)
        self.assertEqual(dbLec.plonePath, '/plone/dept1/tut1/lec2')
        dbLec = self.getView().getDbLecture("//plone/dept1/tut1/lec1/@@quizdb-sync")
        self.assertEqual(dbLec.hostId, dbHost.hostId)
        self.assertEqual(dbLec.plonePath, '/plone/dept1/tut1/lec1')

        # We don't allow nonsense to be added
        with self.assertRaisesRegexp(ValueError, r'not-a-real-lec'):
            dbLec = self.getView().getDbLecture("http://some:host/dept1/super-tut/not-a-real-lec/@@quizdb-sync")

    def getView(self):
        """Look up view for class"""
        lec = self.layer['portal']['dept1']['tut1']['lec1']
        return lec.restrictedTraverse('quizdb-sync')
