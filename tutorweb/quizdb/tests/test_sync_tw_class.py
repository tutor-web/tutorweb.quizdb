import transaction
from zope.testing.loggingsupport import InstalledHandler

from plone.app.testing import login
from z3c.saconfig import Session

from tutorweb.quizdb import db
from tutorweb.content.tests.base import setRelations
from .base import IntegrationTestCase
from .base import MANAGER_ID, USER_A_ID, USER_B_ID, USER_C_ID


class SyncClassSubscriptionsTest(IntegrationTestCase):
    maxDiff = None

    def setUp(self):
        """Set up a class ready for testing"""
        super(SyncClassSubscriptionsTest, self).setUp()
        portal = self.layer['portal']

        self.loghandlers = dict(
            sqlalchemy=InstalledHandler('sqlalchemy.engine'),
            sync=InstalledHandler('tutorweb.quizdb.browser.sync')
        )

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]

    def test_syncSubscriptions(self):
        portal = self.layer['portal']

        def getSubscriptions(data={}, user=USER_A_ID):
            login(self.layer['portal'], user)
            return self.layer['portal'].unrestrictedTraverse('quizdb-subscriptions').asDict(data)

        # By default, no subscriptions
        self.assertEqual(
            getSubscriptions(),
            dict(children=[])
        )

        # Add class with A in it, but no students
        login(portal, MANAGER_ID)
        classObj = portal[portal.invokeFactory(
            type_name="tw_class",
            id="hard_knocks",
            title="Unittest Hard Knocks class",
            lectures=[portal['dept1']['tut1']['lec2']],
            students=None,
        )]
        setRelations(portal['hard_knocks'], 'lectures', [
            portal['dept1']['tut1']['lec2'],
        ]),
        # Don't get subscribed
        self.assertEqual(
            getSubscriptions(user=USER_A_ID),
            dict(children=[])
        )
        self.assertEqual(
            getSubscriptions(user=USER_B_ID),
            dict(children=[])
        )

        # Add student A, they get auto-subscribed
        classObj.students = [USER_A_ID, USER_C_ID]
        self.notifyModify(classObj)
        self.assertEqual(
            getSubscriptions(user=USER_A_ID),
            dict(children=[dict(title='Unittest Hard Knocks class', children=[
                dict(uri='http://nohost/plone/dept1/tut1/lec2/quizdb-sync', title='Unittest D1 T1 L2'),
            ])])
        )
        self.assertEqual(
            getSubscriptions(user=USER_B_ID),
            dict(children=[])
        )

        # Student C's e-mail address is set (which had to happen in syncSubscriptions)
        dbS = Session.query(db.Student).filter_by(userName=USER_C_ID).one()
        self.assertEqual(dbS.eMail, USER_C_ID + '@example.com')
