import transaction

from plone.app.testing import login

from .base import FunctionalTestCase, IntegrationTestCase
from .base import USER_A_ID, USER_B_ID, USER_C_ID, MANAGER_ID

from ..sync.questions import syncPloneQuestions, getQuestionAllocation


class GetQuestionAllocationTest(FunctionalTestCase):
    maxDiff = None

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]

    def setUp(self):
        """Fetch student record for all users"""
        super(GetQuestionAllocationTest, self).setUp()
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        login(portal, USER_A_ID)
        self.studentA = portal.restrictedTraverse('dept1/tut1/lec1/@@quizdb-sync').getCurrentStudent()
        login(portal, USER_B_ID)
        self.studentB = portal.restrictedTraverse('dept1/tut1/lec1/@@quizdb-sync').getCurrentStudent()
        login(portal, USER_C_ID)
        self.studentC = portal.restrictedTraverse('dept1/tut1/lec1/@@quizdb-sync').getCurrentStudent()

        transaction.commit()

    def test_targetDifficutly(self):
        """Make sure we can influence the target difficulty"""
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        def getAllocStats(lectureId, student, targetDifficulty, settings = {}):
            (allocs, _) = getQuestionAllocation(lectureId, student, 'http://x', settings, targetDifficulty=targetDifficulty)
            difficulty = [float(qn['correct']) / qn['chosen'] for qn in allocs]
            mean = sum(difficulty) / len(difficulty)
            variance = sum((x - mean) **2 for x in difficulty) / len(difficulty)
            return dict(difficulty=difficulty, mean=mean, variance=variance)

        # Create a lecture that has a range of questions, put them in DB
        qnCount = 250
        def questionOpts(i):
            return dict(
                timesanswered=qnCount,
                timescorrect=qnCount - i,
            )
        lectureObj = self.createTestLecture(qnCount=qnCount, qnOpts=questionOpts)
        login(portal, USER_A_ID)
        lectureId = lectureObj.restrictedTraverse('@@quizdb-sync').getLectureId()
        syncPloneQuestions(portal, lectureId, lectureObj)

        # A should get an even spread, B focuses on easy, C focuses on hard
        statsA = getAllocStats(lectureId, self.studentA, None)
        statsB = getAllocStats(lectureId, self.studentB, 0.175)
        statsC = getAllocStats(lectureId, self.studentC, 0.925)
        self.assertTrue(abs(0.500 - statsA['mean']) < 0.15)
        self.assertTrue(abs(0.175 - statsB['mean']) < 0.15)
        self.assertTrue(abs(0.925 - statsC['mean']) < 0.15)
        self.assertTrue(abs(0.08 - statsA['variance']) < 0.05)
        self.assertTrue(abs(0.01 - statsB['variance']) < 0.05)
        self.assertTrue(abs(0.01 - statsC['variance']) < 0.05)
