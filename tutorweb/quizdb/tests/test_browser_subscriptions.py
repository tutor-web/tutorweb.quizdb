import transaction
from zope.testing.loggingsupport import InstalledHandler

from plone.app.testing import login

from .base import IntegrationTestCase
from .base import MANAGER_ID, USER_A_ID, USER_B_ID, USER_C_ID


class StudentResultsViewTest(IntegrationTestCase):
    maxDiff = None

    def setUp(self):
        """Set up a class ready for testing"""
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        self.loghandlers = dict(
            sqlalchemy=InstalledHandler('sqlalchemy.engine'),
            sync=InstalledHandler('tutorweb.quizdb.browser.sync')
        )

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]

    def test_subscriptionview(self):
        def getSubscriptions(data={}, user=USER_A_ID):
            login(self.layer['portal'], user)
            return self.layer['portal'].unrestrictedTraverse('quizdb-subscriptions').asDict(data)

        # By default, no subscriptions
        self.assertEqual(
            getSubscriptions(),
            dict(children=[])
        )

        # Can add a subscription
        self.assertEqual(
            getSubscriptions(dict(add_lec='http://nohost/plone/dept1/tut1/lec2')),
            dict(children=[dict(title='Unittest D1 T1', children=[
                dict(uri='http://nohost/plone/dept1/tut1/lec1/quizdb-sync', title='Unittest D1 T1 L1'),
                dict(uri='http://nohost/plone/dept1/tut1/lec2/quizdb-sync', title='Unittest D1 T1 L2'),
            ])])
        )

        # Can get it a second time
        self.assertEqual(
            getSubscriptions(),
            dict(children=[dict(title='Unittest D1 T1', children=[
                dict(uri='http://nohost/plone/dept1/tut1/lec1/quizdb-sync', title='Unittest D1 T1 L1'),
                dict(uri='http://nohost/plone/dept1/tut1/lec2/quizdb-sync', title='Unittest D1 T1 L2'),
            ])])
        )

        # Adding again doesn't change anything
        self.assertEqual(
            getSubscriptions(dict(add_lec='http://nohost/plone/dept1/tut1/lec2')),
            dict(children=[dict(title='Unittest D1 T1', children=[
                dict(uri='http://nohost/plone/dept1/tut1/lec1/quizdb-sync', title='Unittest D1 T1 L1'),
                dict(uri='http://nohost/plone/dept1/tut1/lec2/quizdb-sync', title='Unittest D1 T1 L2'),
            ])])
        )
