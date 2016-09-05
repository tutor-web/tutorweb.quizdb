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

        # Create an extra test tutorial
        portal['dept1'].invokeFactory(
            type_name="tw_tutorial",
            id="tut_extra",
            title="Unittest D1 tutExtra",
        )
        self.extra_lec = self.createTestLecture(qnCount=1)

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
            getSubscriptions(dict(add_lec='http://nohost/plone/dept1/tut1/lec2/quizdb-sync')),
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
            getSubscriptions(dict(add_lec='http://nohost/plone/dept1/tut1/lec2/quizdb-sync')),
            dict(children=[dict(title='Unittest D1 T1', children=[
                dict(uri='http://nohost/plone/dept1/tut1/lec1/quizdb-sync', title='Unittest D1 T1 L1'),
                dict(uri='http://nohost/plone/dept1/tut1/lec2/quizdb-sync', title='Unittest D1 T1 L2'),
            ])])
        )

        # Can add a second
        self.assertEqual(
            getSubscriptions(dict(add_lec=self.extra_lec.absolute_url())),
            dict(children=[
                dict(title=self.extra_lec.aq_parent.Title(), children=[
                    dict(uri=self.extra_lec.absolute_url() + '/quizdb-sync', title=self.extra_lec.Title()),
                ]),
                dict(title='Unittest D1 T1', children=[
                    dict(uri='http://nohost/plone/dept1/tut1/lec1/quizdb-sync', title='Unittest D1 T1 L1'),
                    dict(uri='http://nohost/plone/dept1/tut1/lec2/quizdb-sync', title='Unittest D1 T1 L2'),
                ]),
            ])
        )

        # Can remove lec1
        self.assertEqual(
            getSubscriptions(dict(del_lec='http://nohost/plone/dept1/tut1/lec2/quizdb-sync')),
            dict(children=[
                dict(title=self.extra_lec.aq_parent.Title(), children=[
                    dict(uri=self.extra_lec.absolute_url() + '/quizdb-sync', title=self.extra_lec.Title()),
                ]),
            ])
        )

        # Stays removed
        self.assertEqual(
            getSubscriptions(dict()),
            dict(children=[
                dict(title=self.extra_lec.aq_parent.Title(), children=[
                    dict(uri=self.extra_lec.absolute_url() + '/quizdb-sync', title=self.extra_lec.Title()),
                ]),
            ])
        )

        # Can put it back again (NB: Not using the same lecture)
        self.assertEqual(
            getSubscriptions(dict(add_lec='http://nohost/plone/dept1/tut1/lec1/quizdb-sync')),
            dict(children=[
                dict(title=self.extra_lec.aq_parent.Title(), children=[
                    dict(uri=self.extra_lec.absolute_url() + '/quizdb-sync', title=self.extra_lec.Title()),
                ]),
                dict(title='Unittest D1 T1', children=[
                    dict(uri='http://nohost/plone/dept1/tut1/lec1/quizdb-sync', title='Unittest D1 T1 L1'),
                    dict(uri='http://nohost/plone/dept1/tut1/lec2/quizdb-sync', title='Unittest D1 T1 L2'),
                ]),
            ])
        )

        # Can remove everything in one go
        self.assertEqual(
            getSubscriptions(dict(del_lec=[
                self.extra_lec.absolute_url() + '/quizdb-sync',
                'http://nohost/plone/dept1/tut1/lec1/quizdb-sync',
                'http://nohost/plone/dept1/tut1/lec2/quizdb-sync',
            ])),
            dict(children=[
            ])
        )

        # Stays removed
        self.assertEqual(
            getSubscriptions(dict()),
            dict(children=[
            ])
        )

        # Can put it all back in one go (NB: Multiple references to the same tutorial)
        self.assertEqual(
            getSubscriptions(dict(add_lec=[
                self.extra_lec.absolute_url() + '/quizdb-sync',
                'http://nohost/plone/dept1/tut1/lec1/quizdb-sync',
                'http://nohost/plone/dept1/tut1/lec2/quizdb-sync',
            ])),
            dict(children=[
                dict(title=self.extra_lec.aq_parent.Title(), children=[
                    dict(uri=self.extra_lec.absolute_url() + '/quizdb-sync', title=self.extra_lec.Title()),
                ]),
                dict(title='Unittest D1 T1', children=[
                    dict(uri='http://nohost/plone/dept1/tut1/lec1/quizdb-sync', title='Unittest D1 T1 L1'),
                    dict(uri='http://nohost/plone/dept1/tut1/lec2/quizdb-sync', title='Unittest D1 T1 L2'),
                ]),
            ])
        )

        # Can remove everything in one go
        self.assertEqual(
            getSubscriptions(dict(del_lec=[
                self.extra_lec.absolute_url() + '/quizdb-sync',
                'http://nohost/plone/dept1/tut1/lec1/quizdb-sync',
                'http://nohost/plone/dept1/tut1/lec2/quizdb-sync',
            ])),
            dict(children=[
            ])
        )
