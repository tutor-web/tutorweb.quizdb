import transaction

from plone.app.testing import login, logout

from .base import IntegrationTestCase
from .base import MANAGER_ID, USER_A_ID, USER_B_ID, USER_C_ID


class QuestionStatsViewTest(IntegrationTestCase):
    def test_getStats(self):
        """Get counts of questions within lectures"""
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create test lecture with some initial stats
        testLec = self.createTestLecture(qnCount=2, qnOpts=lambda i: dict(
            timesanswered=5+i,
            timescorrect=2+i,
        ))
        transaction.commit()

        # Get whole-lecture stats...
        stats = testLec.restrictedTraverse('@@question-stats').getStats()
        self.assertEqual(stats, [
            dict(id='qn-0', timesAnswered=5, timesCorrect=2, title='Unittest tw_latexquestion 0', url='%s/qn-0' % testLec.absolute_url()),
            dict(id='qn-1', timesAnswered=6, timesCorrect=3, title='Unittest tw_latexquestion 1', url='%s/qn-1' % testLec.absolute_url()),
        ])

        # ...or just question stats
        stats = testLec.restrictedTraverse('qn-0/@@question-stats').getStats()
        self.assertEqual(stats, [
            dict(id='qn-0', timesAnswered=5, timesCorrect=2, title='Unittest tw_latexquestion 0', url='%s/qn-0' % testLec.absolute_url()),
        ])
        stats = testLec.restrictedTraverse('qn-1/@@question-stats').getStats()
        self.assertEqual(stats, [
            dict(id='qn-1', timesAnswered=6, timesCorrect=3, title='Unittest tw_latexquestion 1', url='%s/qn-1' % testLec.absolute_url()),
        ])

        # Update in-plone stats, has no effect on stats now stored in db
        testLec['qn-0'].timesanswered = 8
        testLec['qn-0'].timescorrect = 4
        testLec['qn-1'].timesanswered = 9
        testLec['qn-1'].timescorrect = 5
        self.notifyModify(testLec['qn-0'])
        self.notifyModify(testLec['qn-1'])
        self.notifyModify(testLec)
        transaction.commit()
        stats = testLec.restrictedTraverse('@@question-stats').getStats()
        self.assertEqual(stats, [
            dict(id='qn-0', timesAnswered=5, timesCorrect=2, title='Unittest tw_latexquestion 0', url='%s/qn-0' % testLec.absolute_url()),
            dict(id='qn-1', timesAnswered=6, timesCorrect=3, title='Unittest tw_latexquestion 1', url='%s/qn-1' % testLec.absolute_url()),
        ])
        stats = testLec.restrictedTraverse('qn-0/@@question-stats').getStats()
        self.assertEqual(stats, [
            dict(id='qn-0', timesAnswered=5, timesCorrect=2, title='Unittest tw_latexquestion 0', url='%s/qn-0' % testLec.absolute_url()),
        ])
