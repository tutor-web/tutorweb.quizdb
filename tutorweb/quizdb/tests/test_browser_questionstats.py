import transaction

from plone.app.testing import login, logout

from tutorweb.quizdb.sync.questions import syncPloneQuestions

from .base import IntegrationTestCase
from .base import MANAGER_ID, USER_A_ID, USER_B_ID, USER_C_ID


class QuestionStatsViewTest(IntegrationTestCase):

    def test_getStats(self):
        """Get counts of questions within lectures"""
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Set initial stats
        portal['dept1']['tut1']['lec1']['qn1'].timesanswered = 5
        portal['dept1']['tut1']['lec1']['qn1'].timescorrect = 2
        portal['dept1']['tut1']['lec1']['qn2'].timesanswered = 6
        portal['dept1']['tut1']['lec1']['qn2'].timescorrect = 3
        transaction.commit()

        # Get whole-lecture stats...
        stats = portal.restrictedTraverse('dept1/tut1/lec1/@@question-stats').getStats()
        self.assertEqual(stats, [
            dict(id='qn1', timesAnswered=5, timesCorrect=2, title='Unittest D1 T1 L1 Q1', url='http://nohost/plone/dept1/tut1/lec1/qn1'),
            dict(id='qn2', timesAnswered=6, timesCorrect=3, title='Unittest D1 T1 L1 Q2', url='http://nohost/plone/dept1/tut1/lec1/qn2'),
        ])

        # ...or just question stats
        stats = portal.restrictedTraverse('dept1/tut1/lec1/qn1/@@question-stats').getStats()
        self.assertEqual(stats, [
            dict(id='qn1', timesAnswered=5, timesCorrect=2, title='Unittest D1 T1 L1 Q1', url='http://nohost/plone/dept1/tut1/lec1/qn1'),
        ])
        stats = portal.restrictedTraverse('dept1/tut1/lec1/qn2/@@question-stats').getStats()
        self.assertEqual(stats, [
            dict(id='qn2', timesAnswered=6, timesCorrect=3, title='Unittest D1 T1 L1 Q2', url='http://nohost/plone/dept1/tut1/lec1/qn2'),
        ])

        # Sync plone questions, should store stats in DB
        syncPloneQuestions(
            portal.restrictedTraverse('dept1/tut1/lec1/@@question-stats').getLectureId(),
            portal['dept1']['tut1']['lec1'],
        )
        transaction.commit()

        # Update in-plone stats, has no effect on stats now stored in db
        portal['dept1']['tut1']['lec1']['qn1'].timesanswered = 8
        portal['dept1']['tut1']['lec1']['qn1'].timescorrect = 4
        portal['dept1']['tut1']['lec1']['qn2'].timesanswered = 9
        portal['dept1']['tut1']['lec1']['qn2'].timescorrect = 5
        transaction.commit()
        stats = portal.restrictedTraverse('dept1/tut1/lec1/@@question-stats').getStats()
        self.assertEqual(stats, [
            dict(id='qn1', timesAnswered=5, timesCorrect=2, title='Unittest D1 T1 L1 Q1', url='http://nohost/plone/dept1/tut1/lec1/qn1'),
            dict(id='qn2', timesAnswered=6, timesCorrect=3, title='Unittest D1 T1 L1 Q2', url='http://nohost/plone/dept1/tut1/lec1/qn2'),
        ])
        stats = portal.restrictedTraverse('dept1/tut1/lec1/qn1/@@question-stats').getStats()
        self.assertEqual(stats, [
            dict(id='qn1', timesAnswered=5, timesCorrect=2, title='Unittest D1 T1 L1 Q1', url='http://nohost/plone/dept1/tut1/lec1/qn1'),
        ])
